#!/usr/bin/env python3
"""The working material for the ground-truth pass, with every verdict withheld.

`expected.md` has to be written from the frozen transcript and the frozen rule
docs, not from what the tool says about them - a ground truth written after
reading the report silently ratifies whatever the report claims. So this prints
the two halves the reader legitimately needs and nothing else:

  actions   what the session did, in call order - prompts, slash commands,
            Skill/Agent calls, Bash commands, the paths written by any
            mechanism (edit tools and shell writes alike), the paths read
  blocks    the judged blocks' identity: id, document, kind, title
  joins     candidate ties between the two, by plain substring - a block whose
            text mentions something the session invoked, ran or wrote. These
            are candidates for the reader to confirm or reject, never verdicts.

The block *identity* is read off the baseline payload because a block id is the
join key the comparison needs, and re-slugging it here would be a second
implementation of the one thing that must agree. It is the baseline's judged
set, so a block only the after-run judges is not listed here - `compare.py`
reports those as outside the gate rather than letting them escape it. Nothing
else is read from the payload: `status`, `reason`, `evidence`, `moments` and
`ruleCheck` never leave this module, and the only verdict field it consults is
the delivery status, to skip the blocks that never reached the model.

    python3 snapshots/inventory.py actions 9dd3cc8a
    python3 snapshots/inventory.py blocks 9dd3cc8a
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_real_view as brv  # noqa: E402
import take_baseline as tb  # noqa: E402  (same directory)

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _snap_dir(prefix, baseline_dir=None):
    baseline_dir = Path(baseline_dir or tb.DEFAULT_BASELINE_DIR)
    hits = [p.parent for p in baseline_dir.glob("*/*/manifest.json")
            if p.parent.name.startswith(prefix) or prefix.startswith(p.parent.name)]
    if len(hits) != 1:
        sys.exit(f"error: `{prefix}` matches {len(hits)} snapshots under {baseline_dir}")
    return hits[0]


def _payload(snap_dir):
    m = tb._read_manifest(snap_dir)
    if "payload" not in m:
        # The manifest is written before the bake, so an interrupted capture
        # leaves one with no payload recorded.
        sys.exit(f"error: {snap_dir} has no baked payload; re-capture it")
    raw = gzip.decompress((snap_dir / m["payload"]["file"]).read_bytes())
    return m, json.loads(raw.decode("utf-8"))


def judged_blocks(session_data):
    """Every block the tool had an opinion about, identity only.

    Delivery statuses are the one verdict field read here: a block that never
    reached the model has no judgement to be right or wrong about, and the
    audit found the delivery-based statuses correct in every session.
    """
    for f in session_data.get("contextFiles", []):
        for b in f.get("blocks", []):
            if b.get("status") in tb.DELIVERY_STATUSES:
                continue
            yield {"id": b["id"], "doc": f.get("path"), "kind": f.get("kind"),
                   "title": b.get("title"), "content": b.get("content") or ""}


def _cmd_blocks(args):
    snap_dir = _snap_dir(args.session, args.baseline_dir)
    m, data = _payload(snap_dir)
    for b in judged_blocks(data["perSession"][m["sessionId"]]):
        print(f"{b['id']}\t{b['doc']}\t{b['kind']}\t{b['title']}")


def actions(transcript):
    """The ordered action list §11 step 3 of docs/reading-transcripts.md asks for."""
    events = brv.load_transcript(transcript)
    calls = brv.tool_calls(events)
    lines = ["# [n] is the event index on PROMPT lines and the call ordinal on the rest",
             "# - two different numbering spaces, both 1-based only for calls."]
    for i, e in enumerate(events):
        text = brv._real_user_prompt_text(e)
        if text:
            lines.append(f"[{i}] PROMPT  {text.strip()[:400]!r}")
    for n, c in enumerate(calls, 1):
        name = c.get("name")
        inp = c.get("input") or {}
        if name == "Bash":
            lines.append(f"[{n}] BASH    {(inp.get('command') or '')[:400]!r}")
        elif name in ("Skill", "Agent", "Task"):
            label = inp.get("skill") or inp.get("command") or inp.get("subagent_type") or ""
            lines.append(f"[{n}] {name.upper():7s} {label}")
        elif name in WRITE_TOOLS:
            lines.append(f"[{n}] {name.upper():7s} "
                         f"{inp.get('file_path') or inp.get('notebook_path')}")
        elif name == "Read":
            span = ""
            if inp.get("offset") or inp.get("limit"):
                span = f"  (offset={inp.get('offset')} limit={inp.get('limit')})"
            lines.append(f"[{n}] READ    {inp.get('file_path')}{span}")
    # Shell writes are invisible to a census of the edit tools, and a session
    # that shipped a feature through heredocs otherwise reads as one that
    # changed nothing - the trap docs/reading-transcripts.md §5 names.
    written = {"edits": [c for c in calls if c["name"] in WRITE_TOOLS],
               "bash_cmds": [(c["input"] or {}).get("command", "")
                             for c in calls if c["name"] == "Bash"]}
    for path in sorted(set(p for p in brv._written_paths(written) if p)):
        lines.append(f"[-] WROTE   {path}")
    return lines


def _cmd_actions(args):
    snap_dir = _snap_dir(args.session, args.baseline_dir)
    m = tb._read_manifest(snap_dir)
    restore_root = tb.DEFAULT_RESTORE_ROOT / m["project"] / m["sessionId"][:8]
    tb.restore_inputs(snap_dir, restore_root)
    transcript = tb._restored_path(m["transcriptKey"], restore_root)
    for line in actions(transcript):
        print(line)


def _needles(calls):
    """The observable facts a rule block could be tied to, as plain strings.

    Deliberately not brv's own extractors: if the candidate finder shared the
    tool's notion of what a rule names, a tie the tool cannot see would be
    invisible to the ground truth too, and the comparison would score the two
    as agreeing while both were wrong. A plain over-generous substring sweep
    errs the other way - it hands the reader candidates to reject.
    """
    out = []
    for c in calls:
        inp = c.get("input") or {}
        name = c.get("name")
        if name == "Bash":
            # `&&` and `;` only, deliberately not `|`: a heredoc body arrives
            # inside the command string, and splitting it on pipes turns prose
            # into hundreds of two-word "commands" that bury the real ones.
            # A command buried mid-pipeline is a miss the reader catches by
            # reading the `actions` list, which prints the whole command.
            for piece in (inp.get("command") or "").replace("&&", "\n").replace(";", "\n").split("\n"):
                words = piece.split()
                if words:
                    out.append(("ran", " ".join(words[:2])))
        elif name in ("Skill", "Agent", "Task"):
            label = inp.get("skill") or inp.get("command") or ""
            if label:
                out.append(("invoked", label.lstrip("/")))
        elif name in WRITE_TOOLS:
            path = inp.get("file_path") or inp.get("notebook_path") or ""
            if path:
                out.append(("wrote", Path(path).name))
    return sorted(set(out))


def _cmd_joins(args):
    snap_dir = _snap_dir(args.session, args.baseline_dir)
    m, data = _payload(snap_dir)
    restore_root = tb.DEFAULT_RESTORE_ROOT / m["project"] / m["sessionId"][:8]
    tb.restore_inputs(snap_dir, restore_root)
    transcript = tb._restored_path(m["transcriptKey"], restore_root)
    events = brv.load_transcript(transcript)
    calls = brv.tool_calls(events)
    prompts = "\n".join(brv._real_user_prompt_text(e) or "" for e in events)
    needles = _needles(calls) + [("typed", w.lstrip("/")) for w in prompts.split()
                                 if w.startswith("/") and len(w) > 3]
    for b in judged_blocks(data["perSession"][m["sessionId"]]):
        hay = b["content"].lower()
        hits = sorted({f"{how} {what}" for how, what in needles
                       if what and what.lower() in hay})
        if hits:
            print(f"{b['id']}\t{b['title']}\t{' | '.join(hits)}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-dir", type=Path, default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, func in (("actions", _cmd_actions), ("blocks", _cmd_blocks),
                       ("joins", _cmd_joins)):
        s = sub.add_parser(name)
        s.add_argument("session", help="session id prefix")
        s.set_defaults(func=func)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
