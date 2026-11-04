#!/usr/bin/env python3
"""Copy the reviewed checks files into the frozen baseline inputs.

A `<doc>.checks.json` is a judgement input, not a derived artifact: the same
prose scores differently with and without it. The baselines were captured
before any anchor project had one, and the frozen trees are gitignored, so the
reviewed files live here instead, under the same storage keys the manifest
uses:

    snapshots/checks/<project>/<prefix>/<storage key>

This copies each one into `snapshots/baseline/<project>/<prefix>/inputs/` and
records it in the manifest, so `verify` re-hashes it and `after` re-bakes
against it. Committing the file here and the private tree nowhere is what lets
a reader see the patterns that produced a red badge without the transcripts.

The reverse direction is checked too: a checks file frozen into a baseline with
no committed copy is reported UNREVIEWED and fails `--check`, because the gate
enumerating only from the committed side is blind to exactly the file whose
patterns nobody can review. The OZZ `CLAUDE.md.checks.json` behind the
`authorised` rows is one today - it carries a client's rule prose, so the one
record that produces those badges is quoted in `snapshots/expected/RULINGS.md`
instead of the whole file being published here.

    python3 snapshots/freeze_checks.py            # freeze all, report what moved
    python3 snapshots/freeze_checks.py --check    # fail if any is missing or stale
"""
import argparse
import sys
from pathlib import Path

SNAPSHOTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SNAPSHOTS_DIR))

import take_baseline as tb  # noqa: E402

DEFAULT_CHECKS_DIR = SNAPSHOTS_DIR / "checks"


def pending(checks_dir=None, baseline_dir=None):
    """(source, snapshot dir, storage key, already frozen and identical?) per file."""
    checks_dir = Path(checks_dir or DEFAULT_CHECKS_DIR)
    baseline_dir = Path(baseline_dir or tb.DEFAULT_BASELINE_DIR)
    out = []
    for src in sorted(checks_dir.glob("*/*/**/*.checks.json")):
        rel = src.relative_to(checks_dir)
        key = "/".join(rel.parts[2:])
        snap = baseline_dir / rel.parts[0] / rel.parts[1]
        raw = src.read_bytes()
        target = snap / "inputs" / key
        frozen = target.is_file() and target.read_bytes() == raw
        out.append((src, snap, key, frozen))
    return out


def unreviewed(checks_dir=None, baseline_dir=None):
    """(snapshot, storage key) per frozen checks file with no committed copy.

    `pending` enumerates from the committed side, so a checks file that exists
    only in the private tree is invisible to it and `--check` prints clean -
    while every red badge that file produces rests on a pattern no reader of
    the repo can review. Enumerating from the baselines as well is what turns
    that silence into a line.
    """
    checks_dir = Path(checks_dir or DEFAULT_CHECKS_DIR)
    baseline_dir = Path(baseline_dir or tb.DEFAULT_BASELINE_DIR)
    out = []
    for frozen in sorted(baseline_dir.glob("*/*/inputs/**/*.checks.json")):
        project, prefix, _, *rest = frozen.relative_to(baseline_dir).parts
        key = "/".join(rest)
        if not (checks_dir / project / prefix / key).is_file():
            out.append((f"{project}/{prefix}", key))
    return out


def freeze_one(src, snap, key):
    """Write one checks file into a snapshot's inputs and into its manifest."""
    raw = src.read_bytes()
    target = snap / "inputs" / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest = tb._read_manifest(snap)
    if "payload" in manifest:
        manifest["addedAfterBake"] = sorted(set(tb.inputs_added_after_bake(manifest)) | {key})
    entry = {"stored": key, "key": key, "origin": str(src),
             "sha256": tb.sha256(raw), "bytes": len(raw), "gz": False}
    inputs = [e for e in manifest.get("inputs", []) if e.get("key") != key]
    inputs.append(entry)
    manifest["inputs"] = sorted(inputs, key=lambda e: e["key"])
    tb._write_manifest(snap, manifest)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checks-dir", type=Path, default=None)
    p.add_argument("--baseline-dir", type=Path, default=None)
    p.add_argument("--check", action="store_true",
                   help="report drift and exit non-zero instead of writing")
    args = p.parse_args()
    rows = pending(args.checks_dir, args.baseline_dir)
    missing = unreviewed(args.checks_dir, args.baseline_dir)
    for where, key in missing:
        print(f"UNREVIEWED {where}  {key}: frozen into the private tree with no "
              "committed copy under snapshots/checks/", file=sys.stderr)
    if not rows:
        sys.exit(f"error: no checks files under {args.checks_dir or DEFAULT_CHECKS_DIR}")
    stale = 0
    for src, snap, key, frozen in rows:
        if not snap.is_dir():
            print(f"skip  {src}: no baseline snapshot at {snap}", file=sys.stderr)
            continue
        if frozen:
            print(f"ok    {snap.parent.name}/{snap.name}  {key}")
            continue
        stale += 1
        if args.check:
            print(f"STALE {snap.parent.name}/{snap.name}  {key}", file=sys.stderr)
            continue
        freeze_one(src, snap, key)
        print(f"froze {snap.parent.name}/{snap.name}  {key}")
    if args.check and (stale or missing):
        parts = []
        if stale:
            parts.append(f"{stale} checks file(s) not frozen into the baseline; run "
                         "python3 snapshots/freeze_checks.py")
        if missing:
            parts.append(f"{len(missing)} frozen checks file(s) have no committed "
                         "copy, so the patterns behind their badges are not "
                         "reviewable from a clone")
        sys.exit("; ".join(parts))


if __name__ == "__main__":
    main()
