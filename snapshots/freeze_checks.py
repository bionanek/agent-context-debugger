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


def freeze_one(src, snap, key):
    """Write one checks file into a snapshot's inputs and into its manifest."""
    raw = src.read_bytes()
    target = snap / "inputs" / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    manifest = tb._read_manifest(snap)
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
    if args.check and stale:
        sys.exit(f"{stale} checks file(s) not frozen into the baseline; run "
                 "python3 snapshots/freeze_checks.py")


if __name__ == "__main__":
    main()
