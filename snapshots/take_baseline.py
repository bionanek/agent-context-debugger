#!/usr/bin/env python3
"""Freeze a real session's inputs and its judgement output, so a later run can
be compared against the same experiment.

A verdict change is only evidence about the judging code if nothing else moved.
The tool reads its rule docs, skills and ctxlog from disk at analysis time, so
a snapshot that stored only the report would, months later, be re-derived from
edited rules - and a rule edit would read as a judging improvement. Every input
the run loaded is therefore copied here alongside the baked payload.

    python3 snapshots/take_baseline.py capture           # all sessions in sessions.json
    python3 snapshots/take_baseline.py capture --session 9dd3cc8a
    python3 snapshots/take_baseline.py verify            # re-bake from frozen inputs
    python3 snapshots/take_baseline.py after             # re-bake into snapshots/after/
    python3 snapshots/take_baseline.py list

Re-running consumes the frozen copies: `restore_inputs` materialises the
snapshot into a scratch tree and the bake is pointed at that tree instead of
the live home. Paths under the scratch root are replaced by RESTORE_ROOT_TOKEN
in the stored payload, so the bytes do not depend on where the checkout lives.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import build_real_view as brv  # noqa: E402
import rule_checks as rc  # noqa: E402

SNAPSHOTS_DIR = REPO_ROOT / "snapshots"
DEFAULT_BASELINE_DIR = SNAPSHOTS_DIR / "baseline"
DEFAULT_AFTER_DIR = SNAPSHOTS_DIR / "after"
DEFAULT_RESTORE_ROOT = SNAPSHOTS_DIR / ".restore"
DEFAULT_SESSIONS_FILE = SNAPSHOTS_DIR / "sessions.json"

# Placeholder for the scratch tree's absolute path inside the stored payload and
# query dumps. Without it the artifacts would only ever be byte-comparable on
# the machine that wrote them, which makes the determinism check untestable
# anywhere else. Block ids are the one thing it cannot normalise: they are
# slugged from the tail of a file's path, so an unusually short scratch root
# would leak part of the checkout path into them. The default root is deep
# enough that it never does.
RESTORE_ROOT_TOKEN = "__RESTORE_ROOT__"

# Above this, a frozen input is stored gzipped. Transcripts run to tens of MB
# and are the only inputs that reach it; rule docs stay plain text so a
# reviewer can read and diff the exact rules a baseline was judged against.
GZIP_THRESHOLD = 64 * 1024

# Statuses that say nothing about the judging logic - the block never reached
# the model, so there is no verdict to compare. Dumping their records would
# bury the ones that matter.
DELIVERY_STATUSES = frozenset({"not-loaded", "undelivered"})

encode_cwd = brv.encode_cwd_for_projects


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _gzip(data):
    """Deterministic gzip: the header's mtime would otherwise churn the stored
    bytes on every capture, so a re-capture of unchanged content would show up
    as a diff. Written the long way because `gzip.compress(mtime=...)` needs
    Python 3.11 and this tool has no version floor beyond the stdlib.
    """
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as fh:
        fh.write(data)
    return buf.getvalue()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tool_commit():
    """Commit the snapshot was taken at, marked when the tree was dirty.

    A baseline taken over uncommitted edits cannot be reproduced from the
    commit alone, and a manifest that hid that would invite exactly that
    comparison.
    """
    def git(*a):
        return subprocess.run(["git", "-C", str(REPO_ROOT), *a],
                              capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


# ---------- relocation ----------
#
# A frozen input is stored under a key that survives being moved: everything
# beneath the original home keeps its home-relative path, anything else keeps
# its absolute path minus the leading slash. Restoring is then a plain copy
# into <restore root>/<key>.

def _spellings(path):
    """A path as given and fully resolved, deduped.

    The two differ as soon as any component is a symlink (/tmp -> /private/tmp
    on macOS). The loader resolves the paths it reports, while the transcript
    and the ctxlog record whichever spelling the harness happened to see, so a
    snapshot that knew only one of them would file the rule docs under a key
    the restored transcript never points at - and the re-bake would judge the
    session with no rules loaded, which reads as a session that had none.
    """
    p = Path(path)
    out = [p]
    try:
        resolved = p.resolve()
    except OSError:
        return out
    if resolved != p:
        out.append(resolved)
    return out


def _storage_key(abs_path, homes):
    p = Path(abs_path)
    for home in homes:
        try:
            return "home/" + p.relative_to(home).as_posix()
        except ValueError:
            continue
    return "abs/" + p.as_posix().lstrip("/")


def _restored_home(restore_root):
    return Path(restore_root) / "home"


def _restored_path(key, restore_root):
    return Path(restore_root) / key


def _rewrites(homes, cwd, restore_root):
    """Original prefix -> restored prefix, for the inputs that carry paths as data.

    Only the transcript and the ctxlog are rewritten. Rule docs are restored
    verbatim: their prose is the text under judgement, and quietly editing it
    to fit the scratch tree would change what the baseline measures.
    """
    restored_home = str(_restored_home(restore_root))
    pairs = {str(h): restored_home for h in homes}
    for spelling in _spellings(cwd):
        key = _storage_key(spelling, homes)
        if not key.startswith("home/"):
            pairs[str(spelling)] = str(_restored_path(key, restore_root))
    # Longest first, so a nested prefix cannot be shadowed by its parent.
    return sorted(pairs.items(), key=lambda kv: -len(kv[0]))


def _apply_rewrites(text, rewrites):
    for original, restored in rewrites:
        text = text.replace(original, restored)
    return text


# ---------- the child bake ----------

def _bake(transcript, home, cwd, out_payload, record_loads=None):
    """Bake one session in a child process rooted at `home`.

    A child, not an import: the tool binds its ~/.claude defaults at import
    time, so the only way to point a bake at a different home is to set HOME
    before the interpreter starts. PYTHONHASHSEED is pinned because a couple of
    the loader's intermediate sets are iterated, and per-process string hashing
    would reorder the context files - a determinism check that failed at random
    would teach the reader to ignore it.
    """
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PYTHONHASHSEED"] = "0"
    # Would otherwise point every session at the live hook log.
    env.pop("CTXLOG_DIR", None)
    cmd = [sys.executable, str(Path(__file__).resolve()), "_bake",
           "--transcript", str(transcript), "--out-payload", str(out_payload)]
    if record_loads:
        cmd += ["--record-loads", str(record_loads)]
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"bake failed for {Path(transcript).name}:\n"
                           f"{proc.stdout}\n{proc.stderr}")
    # Passed through, never swallowed: the pipeline warns on stderr about the
    # things a snapshot most needs to disclose - a task notification that
    # matched no spawn, a session it declined to parse.
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), file=sys.stderr)


def _cmd_bake(args):
    """Child mode: run the real pipeline and write the payload it would bake."""
    loads = []
    if args.record_loads:
        original = brv.load_context_files

        def spy(*a, **kw):
            files = original(*a, **kw)
            loads.extend(f["abs_path"] for f in files)
            return files

        brv.load_context_files = spy

    sys.argv = ["build_real_view.py", "--transcript", str(args.transcript)]
    bake_args = brv.parse_args()
    all_paths, active_path = brv.select_transcripts(bake_args)
    sessions, per_session, active_id = brv.bake_sessions(all_paths, active_path, bake_args)
    if not sessions:
        # bake_sessions skips an unparseable transcript with a warning, which is
        # right for a 20-session page and wrong here: a snapshot of nothing
        # would verify byte-identically forever.
        sys.exit(f"error: {args.transcript} produced no session")
    data = brv.build_data(os.getcwd(), sessions, per_session, active_id)
    Path(args.out_payload).write_text(json.dumps(data), encoding="utf-8")
    if args.record_loads:
        Path(args.record_loads).write_text(json.dumps(loads), encoding="utf-8")


# ---------- freezing ----------

def _freeze(paths, homes, inputs_dir):
    """Copy each path into inputs_dir under its relocatable key.

    Returns the manifest entries, hashed over the original bytes: the stored
    file may be gzipped, and hashing the compressed form would make the
    manifest useless for answering "are these still the rules I judged?".
    """
    entries = []
    seen = set()
    for path in paths:
        p = Path(path)
        if not p.is_file():
            # Every path here is one the loader just read, so a miss means the
            # file went away mid-capture. Said out loud, because a rule doc
            # silently missing from the baseline makes the re-bake judge that
            # session as if the rule had never been written.
            print(f"warning: vanished before freezing, not in the baseline: {p}",
                  file=sys.stderr)
            continue
        key = _storage_key(p, homes)
        if key in seen:
            continue
        seen.add(key)
        raw = p.read_bytes()
        gz = len(raw) > GZIP_THRESHOLD
        stored = key + ".gz" if gz else key
        target = inputs_dir / stored
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_gzip(raw) if gz else raw)
        entries.append({"stored": stored, "key": key, "origin": str(p),
                        "sha256": sha256(raw), "bytes": len(raw), "gz": gz})
    return sorted(entries, key=lambda e: e["key"])


def _loaded_inputs(loads, home, transcript, session_id):
    """Every file the run read: transcript, ctxlog, rule docs, skills, checks.

    `loads` comes from the loader itself rather than from a walk of ~/.claude,
    so a plugin-cache skill or a mid-session `Read` of a project doc is frozen
    too. Entries that are not absolute paths are the loader's listing-only
    placeholders for a skill with no file on disk - there is nothing to freeze.
    """
    paths = [Path(transcript)]
    ctxlog = Path(home) / ".claude" / "ctxlog" / f"{session_id}.jsonl"
    if ctxlog.is_file():
        paths.append(ctxlog)
    for raw in loads:
        if not raw or not Path(raw).is_absolute():
            continue
        paths.append(Path(raw))
        # Part of the judgement input, not a derived artifact: the same prose
        # scores differently with and without it.
        checks = rc.find_checks_file(raw)
        if checks is not None:
            paths.append(checks)
    return paths


# ---------- restoring and re-baking ----------

def restore_inputs(snap_dir, restore_root):
    """Materialise a snapshot's frozen inputs. Returns (home, cwd) to bake in."""
    snap_dir = Path(snap_dir)
    m = _read_manifest(snap_dir)
    restore_root = Path(restore_root).resolve()
    rewrites = [(o, r.replace(RESTORE_ROOT_TOKEN, str(restore_root)))
                for o, r in m["rewrites"]]
    rewritten_keys = set(m["rewriteInside"])
    # Cleared, not overwritten: the loader globs the skills directory, so a
    # skill left behind by an earlier capture of the same session would be
    # loaded again and the re-bake would stop matching a clean restore
    # elsewhere - a determinism failure that only shows up on someone else's
    # machine.
    for bucket in ("home", "abs"):
        shutil.rmtree(restore_root / bucket, ignore_errors=True)
    for entry in m["inputs"]:
        stored = snap_dir / "inputs" / entry["stored"]
        raw = gzip.decompress(stored.read_bytes()) if entry["gz"] else stored.read_bytes()
        if entry["key"] in rewritten_keys:
            # surrogateescape, so bytes that are not valid UTF-8 survive the
            # round trip instead of being silently replaced: the transcript is
            # an input, and a lossy copy of it is a different experiment.
            raw = _apply_rewrites(raw.decode("utf-8", "surrogateescape"),
                                  rewrites).encode("utf-8", "surrogateescape")
        target = _restored_path(entry["key"], restore_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    home = _restored_home(restore_root)
    cwd = Path(_apply_rewrites(m["originalCwd"], rewrites))
    if restore_root not in cwd.parents:
        # A cwd that did not relocate is still the live project directory, and
        # the mkdir below would write into it.
        raise RuntimeError(f"snapshot cwd {cwd} does not sit under {restore_root}; "
                           f"manifest rewrites are incomplete")
    cwd.mkdir(parents=True, exist_ok=True)
    return home, cwd


def _normalize(text, restore_root):
    return text.replace(str(Path(restore_root).resolve()), RESTORE_ROOT_TOKEN)


def bake_from_frozen(snap_dir, restore_root):
    """Restore a snapshot and re-bake it. Returns the normalized payload bytes."""
    snap_dir = Path(snap_dir)
    m = _read_manifest(snap_dir)
    restore_root = Path(restore_root).resolve()
    home, cwd = restore_inputs(snap_dir, restore_root)
    transcript = _restored_path(m["transcriptKey"], restore_root)
    out = restore_root / "payload.json"
    _bake(transcript, home, cwd, out)
    return _normalize(out.read_text(encoding="utf-8"), restore_root).encode("utf-8")


# ---------- query dumps ----------

def _non_delivery_block_ids(session_data):
    for f in session_data.get("contextFiles", []):
        for b in f.get("blocks", []):
            if b.get("status") not in DELIVERY_STATUSES:
                yield b["id"]


def _write_query_dumps(payload_bytes, session_id, qdir):
    """The human-readable half of the snapshot, rendered from the payload only.

    Nothing is recomputed here: the dumps go through the same `run_query` the
    CLI uses, so a snapshot can never describe a session differently than the
    tool does.
    """
    data = json.loads(payload_bytes.decode("utf-8"))
    session_data = data["perSession"][session_id]
    qdir.mkdir(parents=True, exist_ok=True)

    def dump(name, lines):
        (qdir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    dump("turns.txt", brv.run_query(data, [session_id, "turns"], show_all=True))
    dump("blocks.txt", brv.run_query(data, [session_id, "blocks"], show_all=True))
    verdicts = []
    for block_id in _non_delivery_block_ids(session_data):
        verdicts.extend(brv.run_query(data, [session_id, block_id]))
        verdicts.append("")
    dump("verdicts.txt", verdicts)
    return ["query/turns.txt", "query/blocks.txt", "query/verdicts.txt"]


# ---------- capture ----------

def _read_manifest(snap_dir):
    return json.loads((Path(snap_dir) / "manifest.json").read_text(encoding="utf-8"))


def inputs_added_after_bake(manifest):
    """Keys frozen into a snapshot after its baseline payload was baked.

    The baseline never read them and the after-run does, so a verdict that
    moved in that session may have moved because of the input rather than the
    judging code. Manifests written before `addedAfterBake` existed are read off
    the origin instead: `capture` rewrites the manifest and bakes in one call,
    so an entry whose origin is the committed checks tree was added afterwards.
    """
    if "addedAfterBake" in manifest:
        return sorted(manifest["addedAfterBake"])
    if "payload" not in manifest:
        return []
    return sorted(e["key"] for e in manifest.get("inputs") or []
                  if _under_checks_tree(e.get("origin", "")))


def _under_checks_tree(origin):
    parts = Path(origin).parts
    return any(parts[i:i + 2] == ("snapshots", "checks") for i in range(len(parts) - 1))


def _write_manifest(snap_dir, manifest):
    (Path(snap_dir) / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _find_transcript(cwd, session_prefix, home):
    projects = Path(home) / ".claude" / "projects" / encode_cwd(str(cwd))
    matches = sorted(p for p in projects.glob(f"{session_prefix}*.jsonl") if p.is_file())
    if not matches:
        raise FileNotFoundError(f"no transcript starting with `{session_prefix}` under {projects}")
    if len(matches) > 1:
        raise ValueError(f"`{session_prefix}` matches {len(matches)} transcripts under {projects}")
    return matches[0]


def capture_session(spec, *, home=None, baseline_dir=None, restore_root=None):
    """Freeze one session's inputs, then bake the baseline from those copies.

    The baseline is deliberately baked from the frozen tree rather than from
    the live one: if capture and re-run used different roots, the very first
    comparison would show a difference that no code change caused.
    """
    home = Path(home) if home else Path.home()
    homes = _spellings(home)
    baseline_dir = Path(baseline_dir) if baseline_dir else DEFAULT_BASELINE_DIR
    cwd = Path(os.path.expanduser(spec["cwd"]))
    transcript = _find_transcript(cwd, spec["session"], home)
    session_id = transcript.stem
    snap_dir = baseline_dir / spec["project"] / session_id[:8]
    restore_root = Path(restore_root or (DEFAULT_RESTORE_ROOT / spec["project"] / session_id[:8]))
    restore_root = restore_root.resolve()
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1, against the live tree: the only way to know which rule docs and
    # skills this session loaded is to let the loader decide.
    scratch = snap_dir / ".discovery"
    scratch.mkdir(exist_ok=True)
    loads_file = scratch / "loads.json"
    _bake(transcript, home, cwd, scratch / "payload.json", record_loads=loads_file)
    loads = json.loads(loads_file.read_text(encoding="utf-8"))

    inputs_dir = snap_dir / "inputs"
    shutil.rmtree(inputs_dir, ignore_errors=True)
    entries = _freeze(_loaded_inputs(loads, home, transcript, session_id), homes, inputs_dir)
    transcript_key = _storage_key(transcript, homes)
    ctxlog_key = _storage_key(Path(home) / ".claude" / "ctxlog" / f"{session_id}.jsonl", homes)
    keys = {e["key"] for e in entries}

    manifest = {
        "capturedAt": _now(),
        "tool": _tool_commit(),
        "project": spec["project"],
        "sessionId": session_id,
        "originalHome": str(home),
        "originalCwd": str(cwd),
        "transcript": str(transcript),
        "transcriptKey": transcript_key,
        # Recorded with the scratch root as a token so the manifest, like the
        # payload, does not pin the snapshot to one checkout location.
        "rewrites": [(o, r.replace(str(restore_root), RESTORE_ROOT_TOKEN))
                     for o, r in _rewrites(homes, cwd, restore_root)],
        "rewriteInside": sorted(k for k in (transcript_key, ctxlog_key) if k in keys),
        "inputs": entries,
    }
    _write_manifest(snap_dir, manifest)

    # Pass 2, from the frozen copies.
    payload = bake_from_frozen(snap_dir, restore_root)
    (snap_dir / "payload.json.gz").write_bytes(_gzip(payload))
    manifest["payload"] = {"file": "payload.json.gz", "sha256": sha256(payload),
                           "bytes": len(payload)}
    manifest["queries"] = _write_query_dumps(payload, session_id, snap_dir / "query")
    _write_manifest(snap_dir, manifest)
    shutil.rmtree(scratch, ignore_errors=True)
    return snap_dir


# ---------- the after-run ----------

def _repo_relative(path):
    """Repo-relative where possible - a baseline dir outside the checkout is legal."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def rerun_session(snap_dir, after_dir=None, restore_root=None):
    """Re-bake one snapshot from its frozen inputs into the after tree.

    Deliberately not a second capture: the inputs stay the ones the baseline
    was judged against, so a verdict that moved moved because the judging code
    did. The after manifest records the tool commit and points back at the
    baseline it is paired with, because a scorecard whose two halves came from
    different frozen trees would be comparing two experiments.
    """
    snap_dir = Path(snap_dir)
    m = _read_manifest(snap_dir)
    after_dir = Path(after_dir or DEFAULT_AFTER_DIR) / m["project"] / m["sessionId"][:8]
    if restore_root is None:
        restore_root = DEFAULT_RESTORE_ROOT / m["project"] / m["sessionId"][:8]
    after_dir.mkdir(parents=True, exist_ok=True)
    payload = bake_from_frozen(snap_dir, restore_root)
    (after_dir / "payload.json.gz").write_bytes(_gzip(payload))
    manifest = {
        "ranAt": _now(),
        "tool": _tool_commit(),
        "project": m["project"],
        "sessionId": m["sessionId"],
        "baseline": {"dir": _repo_relative(snap_dir),
                     "capturedAt": m["capturedAt"], "tool": m["tool"],
                     "payloadSha256": m["payload"]["sha256"]},
        "payload": {"file": "payload.json.gz", "sha256": sha256(payload),
                    "bytes": len(payload)},
    }
    manifest["queries"] = _write_query_dumps(payload, m["sessionId"], after_dir / "query")
    _write_manifest(after_dir, manifest)
    return after_dir


def _cmd_after(args):
    dirs = _snap_dirs(args.baseline_dir)
    if args.session:
        dirs = [d for d in dirs if _matches(d.name, args.session)]
    if not dirs:
        sys.exit(f"error: no snapshots under {args.baseline_dir}")
    failed = 0
    for d in dirs:
        try:
            out = rerun_session(d, after_dir=args.after_dir)
        except Exception as e:
            failed += 1
            print(f"FAIL  {d.parent.name}/{d.name}: {e}", file=sys.stderr)
            continue
        m = _read_manifest(out)
        same = m["payload"]["sha256"] == m["baseline"]["payloadSha256"]
        print(f"ok    {m['project']}/{m['sessionId'][:8]}  "
              f"payload {m['payload']['bytes'] // 1024}k, "
              f"{'identical to' if same else 'differs from'} the baseline")
    if failed:
        sys.exit(f"{failed} session(s) failed to re-run")


# ---------- verify ----------

def verify_session(snap_dir, restore_root=None):
    """Re-hash the frozen inputs and re-bake from them. Returns a report dict."""
    snap_dir = Path(snap_dir)
    m = _read_manifest(snap_dir)
    problems = []
    if "payload" not in m:
        # The manifest is written before the bake so the frozen inputs are
        # recorded even if the bake dies. Half a snapshot has nothing to verify
        # against, and saying so beats raising through the other snapshots.
        return {"sessionId": m.get("sessionId", "?"), "project": m.get("project", "?"),
                "inputsVerified": 0, "payloadMatched": False,
                "problems": ["incomplete snapshot: no baseline payload recorded; re-capture it"]}
    stored_payload = snap_dir / m["payload"]["file"]
    if not stored_payload.is_file():
        problems.append(f"missing baseline payload: {m['payload']['file']}")
    elif sha256(gzip.decompress(stored_payload.read_bytes())) != m["payload"]["sha256"]:
        # The re-bake below is compared against the manifest hash, so a rotten
        # stored payload would otherwise pass unnoticed and the artifact anyone
        # actually reads would no longer be the one that was verified.
        problems.append(f"hash mismatch: {m['payload']['file']}")
    for entry in m["inputs"]:
        stored = snap_dir / "inputs" / entry["stored"]
        if not stored.is_file():
            problems.append(f"missing frozen input: {entry['stored']}")
            continue
        raw = gzip.decompress(stored.read_bytes()) if entry["gz"] else stored.read_bytes()
        if sha256(raw) != entry["sha256"]:
            problems.append(f"hash mismatch: {entry['stored']}")
    if restore_root is None:
        restore_root = DEFAULT_RESTORE_ROOT / m["project"] / m["sessionId"][:8]
    payload = bake_from_frozen(snap_dir, restore_root)
    matched = sha256(payload) == m["payload"]["sha256"]
    if not matched:
        problem = (f"payload differs from baseline ({m['payload']['sha256'][:12]} "
                   f"-> {sha256(payload)[:12]})")
        added = inputs_added_after_bake(m)
        if added:
            problem += ("; expected, input(s) added after the baseline was baked: "
                        + ", ".join(added))
        problems.append(problem)
    return {"sessionId": m["sessionId"], "project": m["project"],
            "inputsVerified": len(m["inputs"]), "payloadMatched": matched,
            "problems": problems}


# ---------- CLI ----------

def load_specs(path=None):
    path = Path(path) if path else DEFAULT_SESSIONS_FILE
    return json.loads(path.read_text(encoding="utf-8"))["sessions"]


def _matches(session_id, wanted):
    """Either side may be the shorter prefix, so a full id selects too.

    `capture` takes 8-char prefixes from sessions.json while a caller reading a
    report has the full uuid; accepting only one direction makes `verify
    --session <full id>` quietly select nothing.
    """
    return any(session_id.startswith(w) or w.startswith(session_id) for w in wanted)


def _select(specs, wanted):
    if not wanted:
        return specs
    picked = [s for s in specs if _matches(s["session"], wanted)]
    if not picked:
        sys.exit(f"error: no session in {DEFAULT_SESSIONS_FILE.name} matches {wanted}")
    return picked


def _snap_dirs(baseline_dir):
    baseline_dir = Path(baseline_dir)
    if not baseline_dir.is_dir():
        return []
    return sorted(p.parent for p in baseline_dir.glob("*/*/manifest.json"))


def _cmd_capture(args):
    specs = _select(load_specs(args.sessions_file), args.session)
    for spec in specs:
        try:
            snap_dir = capture_session(spec, home=args.home, baseline_dir=args.baseline_dir)
        except Exception as e:
            print(f"FAIL  {spec['project']}/{spec['session']}: {e}", file=sys.stderr)
            continue
        m = _read_manifest(snap_dir)
        print(f"ok    {spec['project']}/{m['sessionId'][:8]}  "
              f"{len(m['inputs'])} inputs, payload {m['payload']['bytes'] // 1024}k")


def _cmd_verify(args):
    dirs = _snap_dirs(args.baseline_dir)
    if args.session:
        dirs = [d for d in dirs if _matches(d.name, args.session)]
    if not dirs:
        sys.exit(f"error: no snapshots under {args.baseline_dir}")
    failed = 0
    for d in dirs:
        try:
            report = verify_session(d)
        except Exception as e:
            # One unreadable snapshot must not hide the verdict on the rest.
            failed += 1
            print(f"FAIL  {d.parent.name}/{d.name}: {e}")
            continue
        if report["problems"]:
            failed += 1
            print(f"FAIL  {report['project']}/{report['sessionId'][:8]}")
            for p in report["problems"]:
                print(f"      {p}")
        else:
            print(f"ok    {report['project']}/{report['sessionId'][:8]}  "
                  f"{report['inputsVerified']} inputs verified, payload byte-identical")
    if failed:
        sys.exit(f"{failed} snapshot(s) failed verification")


def _cmd_list(args):
    for d in _snap_dirs(args.baseline_dir):
        m = _read_manifest(d)
        print(f"{m['project']:20s}  {m['sessionId'][:8]}  {m['capturedAt']}  "
              f"{m['tool']['commit'][:8]}{'-dirty' if m['tool']['dirty'] else ''}  "
              f"{len(m['inputs'])} inputs")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    sub = p.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="freeze inputs and bake the baseline")
    cap.add_argument("--session", action="append", default=[],
                     help="session id prefix (repeatable; default: all in sessions.json)")
    cap.add_argument("--sessions-file", type=Path, default=None)
    cap.add_argument("--home", type=Path, default=None,
                     help="root to read ~/.claude and the projects dir from (default: $HOME)")
    cap.set_defaults(func=_cmd_capture)

    ver = sub.add_parser("verify", help="re-bake every snapshot from its frozen inputs")
    ver.add_argument("--session", action="append", default=[])
    ver.set_defaults(func=_cmd_verify)

    aft = sub.add_parser("after", help="re-bake every snapshot from its frozen inputs "
                                       "into snapshots/after/")
    aft.add_argument("--session", action="append", default=[])
    aft.add_argument("--after-dir", type=Path, default=None)
    aft.set_defaults(func=_cmd_after)

    lst = sub.add_parser("list", help="list captured snapshots")
    lst.set_defaults(func=_cmd_list)

    bake = sub.add_parser("_bake", help=argparse.SUPPRESS)
    bake.add_argument("--transcript", type=Path, required=True)
    bake.add_argument("--out-payload", type=Path, required=True)
    bake.add_argument("--record-loads", type=Path, default=None)
    bake.set_defaults(func=_cmd_bake)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
