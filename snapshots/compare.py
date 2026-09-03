#!/usr/bin/env python3
"""Score the baseline and the after-run against the hand-written ground truth.

Three trees, one row per judged block:

    snapshots/baseline/<project>/<prefix>/   the payload as it was before the work
    snapshots/after/<project>/<prefix>/      the payload at the final commit
    snapshots/expected/<project>/<prefix>/   expected.md, written from the frozen
                                             inputs before either was read

    python3 snapshots/compare.py                     # print the scorecard
    python3 snapshots/compare.py --out snapshots/SCORECARD.md

A block agrees with the ground truth when the tool's status falls inside the
set that truth class allows. The classes are coarse on purpose: `dormant` vs
`unused` is not a reliability claim, but a green over a rule nothing tied to
the run, or a red over a rule nobody can cite a violation of, is exactly the
error the audit measured.

`regressed` (agreed before, wrong after) is a release blocker. `still-wrong`
rows are listed in full with the ground truth's own `accept:` note where the
miss is a known and accepted limit.
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

SNAPSHOTS_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE = SNAPSHOTS_DIR / "baseline"
DEFAULT_AFTER = SNAPSHOTS_DIR / "after"
DEFAULT_EXPECTED = SNAPSHOTS_DIR / "expected"

# Statuses that say nothing about the judging logic - the block never reached
# the model. Mirrors take_baseline.DELIVERY_STATUSES; duplicated rather than
# imported so this scorer stays readable on its own.
DELIVERY_STATUSES = frozenset({"not-loaded", "undelivered"})

# What each truth class allows the tool to say. `used-partial` is allowed under
# `violated` because a session that broke a rule in one turn and followed it in
# another honestly combines to it.
ALLOWED = {
    "used": frozenset({"used", "used-partial"}),
    "violated": frozenset({"ignored", "used-partial"}),
    "no-hard-verdict": frozenset({"dormant", "unused", "possibly-referenced",
                                  "undelivered", "not-loaded"}),
}
UNDECIDABLE = "undecidable"
TRUTHS = frozenset(ALLOWED) | {UNDECIDABLE}

GREENS = frozenset({"used", "used-partial"})
ABSENT = "(absent)"


def error_kind(truth, status):
    """Which way a disagreement points, from the audited rule's side."""
    if status in ALLOWED[truth]:
        return None
    if status == ABSENT:
        # Its own kind, not a missed compliance: the tool said nothing at all
        # about this block, and filing that under "did not credit the rule"
        # would describe a vanished block as a judgement that was made.
        return "absent"
    if truth == "no-hard-verdict":
        if status in GREENS:
            return "false-green"
        return "false-red" if status == "ignored" else "unexpected"
    if truth == "used":
        return "false-red" if status == "ignored" else "missed-compliance"
    return "false-green" if status in GREENS else "missed-violation"


# ---------- inputs ----------

def load_expected(path):
    """Parse one expected.md. Prose is ignored; verdict lines are the contract."""
    out = {}
    last = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- ") and " :: " in line:
            parts = [p.strip() for p in line[2:].split(" :: ", 3)]
            if len(parts) != 4:
                raise ValueError(f"{path}: malformed verdict line: {raw}")
            bid, truth, tag, evidence = parts
            if truth not in TRUTHS:
                # Never silently excluded: a misspelling would otherwise take
                # the `undecidable` path and drop a block out of the gate.
                raise ValueError(f"{path}: unknown truth class {truth!r} for {bid}")
            out[bid] = {"truth": truth, "tag": None if tag == "-" else tag,
                        "evidence": evidence, "accept": None, "revised": None}
            last = bid
        elif last:
            for key in ("accept", "revised"):
                if line.startswith(key + ":"):
                    out[last][key] = line[len(key) + 1:].strip()
    return out


def read_payload(snap_dir):
    """The baked payload of one snapshot, gzipped or plain."""
    snap_dir = Path(snap_dir)
    gz = snap_dir / "payload.json.gz"
    if gz.is_file():
        return json.loads(gzip.decompress(gz.read_bytes()).decode("utf-8"))
    return json.loads((snap_dir / "payload.json").read_text(encoding="utf-8"))


def judged_statuses(payload, session_id=None):
    """{block id: status} at session scope, delivery-only statuses dropped."""
    sessions = payload["perSession"]
    if session_id is None:
        session_id = next(iter(sessions))
    out = {}
    for f in sessions[session_id].get("contextFiles", []):
        for b in f.get("blocks", []):
            if b.get("status") in DELIVERY_STATUSES:
                continue
            out[b["id"]] = b.get("status")
    return out


def _session_id(snap_dir):
    manifest = Path(snap_dir) / "manifest.json"
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding="utf-8")).get("sessionId")
    return None


# ---------- scoring ----------

def compare_session(name, baseline_dir, after_dir, expected_file):
    """Returns (rows, unscored) - the second being blocks no truth class covers.

    A block either payload judges but the ground truth does not name is not
    scored, and saying nothing about it would let a green the after-run
    invented (a delivery reclassification adds a block, say) sit outside the
    gate entirely. A ground-truth id present in neither payload is the same
    problem pointed the other way - a stale line quietly scored as a miss.
    """
    expected = load_expected(expected_file)
    before = judged_statuses(read_payload(baseline_dir), _session_id(baseline_dir))
    after = judged_statuses(read_payload(after_dir), _session_id(after_dir))
    unscored = [f"{name} {bid}: judged `{before.get(bid) or after.get(bid)}` "
                f"with no ground truth" for bid in sorted(set(before) | set(after))
                if bid not in expected]
    unscored += [f"{name} {bid}: ground truth for a block neither payload judges"
                 for bid in sorted(expected)
                 if bid not in before and bid not in after]
    rows = []
    for bid, exp in expected.items():
        b = before.get(bid, ABSENT)
        a = after.get(bid, ABSENT)
        if exp["truth"] == UNDECIDABLE:
            rows.append({"session": name, "id": bid, "truth": exp["truth"],
                         "tag": exp["tag"], "before": b, "after": a,
                         "beforeError": None, "afterError": None,
                         "outcome": "excluded", "accept": exp["accept"],
                         "revised": exp["revised"], "evidence": exp["evidence"]})
            continue
        be = error_kind(exp["truth"], b)
        ae = error_kind(exp["truth"], a)
        if be is None and ae is None:
            outcome = "agreed"
        elif be is not None and ae is None:
            outcome = "fixed"
        elif be is None:
            outcome = "regressed"
        else:
            outcome = "still-wrong"
        rows.append({"session": name, "id": bid, "truth": exp["truth"], "tag": exp["tag"],
                     "before": b, "after": a, "beforeError": be, "afterError": ae,
                     "outcome": outcome, "accept": exp["accept"], "revised": exp["revised"],
                     "evidence": exp["evidence"]})
    return rows, unscored


def _tally(rows):
    t = {k: 0 for k in ("scored", "excluded", "agreed", "fixed", "regressed", "still-wrong",
                        "agreedBefore", "agreedAfter", "falseGreenBefore", "falseGreenAfter",
                        "falseRedBefore", "falseRedAfter", "missedBefore", "missedAfter",
                        "absentBefore", "absentAfter")}
    for r in rows:
        t[r["outcome"]] += 1
        if r["outcome"] == "excluded":
            continue
        t["scored"] += 1
        for half in ("before", "after"):
            err = r[half + "Error"]
            key = "Before" if half == "before" else "After"
            if err is None:
                t["agreed" + key] += 1
            elif err == "false-green":
                t["falseGreen" + key] += 1
            elif err == "false-red":
                t["falseRed" + key] += 1
            elif err == "absent":
                t["absent" + key] += 1
            else:
                t["missed" + key] += 1
    return t


def compare_all(baseline_dir=None, after_dir=None, expected_dir=None):
    baseline_dir = Path(baseline_dir or DEFAULT_BASELINE)
    after_dir = Path(after_dir or DEFAULT_AFTER)
    expected_dir = Path(expected_dir or DEFAULT_EXPECTED)
    rows, missing, unscored = [], [], []
    for exp in sorted(expected_dir.glob("*/*/expected.md")):
        project, prefix = exp.parent.parent.name, exp.parent.name
        name = f"{project}/{prefix}"
        b, a = baseline_dir / project / prefix, after_dir / project / prefix
        if not b.is_dir() or not a.is_dir():
            # Named, never skipped: a gate that quietly shrinks to the sessions
            # that still have both halves reports a better number than it earned.
            missing.append(name)
            continue
        session_rows, session_unscored = compare_session(name, b, a, exp)
        rows.extend(session_rows)
        unscored.extend(session_unscored)
    by_session, by_tag = {}, {}
    for r in rows:
        by_session.setdefault(r["session"], []).append(r)
        by_tag.setdefault(r["tag"] or "(untagged)", []).append(r)
    return {"rows": rows, "totals": _tally(rows), "missing": missing, "unscored": unscored,
            "bySession": {k: _tally(v) for k, v in by_session.items()},
            "byTag": {k: _tally(v) for k, v in by_tag.items()}}


def blockers(report):
    """Every regression, as `<session> <block>` - each one blocks the release."""
    return [f"{r['session']} {r['id']}" for r in report["rows"] if r["outcome"] == "regressed"]


# ---------- rendering ----------

def _row_line(r):
    line = (f"- `{r['session']}` **{r['id']}** - truth `{r['truth']}`"
            f"{' [' + r['tag'] + ']' if r['tag'] else ''}: "
            f"`{r['before']}` -> `{r['after']}`. {r['evidence']}")
    if r["accept"]:
        line += f"\n  - accepted: {r['accept']}"
    if r["revised"]:
        line += f"\n  - ground truth revised: {r['revised']}"
    return line


def render(report):
    t = report["totals"]
    out = ["# Verdict scorecard: baseline vs after vs ground truth", "",
           "Generated by `python3 snapshots/compare.py --out snapshots/SCORECARD.md`. Do not",
           "edit by hand - regenerate it, so the numbers stay the ones the snapshots hold.",
           "",
           "Both halves are baked from the *same* frozen inputs (`snapshots/baseline/*/inputs/`),",
           "so a verdict that moved moved because the judging code did. The ground truth in",
           "`snapshots/expected/` was written from those inputs before either payload was",
           "read. The rows that are exceptions - revised afterwards, or added for a block the",
           "baseline never judged - say so in their own line.",
           "",
           "A row agrees when the tool's status falls inside what the truth class allows.",
           "`no-hard-verdict` allows every not-used-family status and the co-occurrence label,",
           "so the two error columns that matter are a green over a rule nothing tied to the run",
           "and a red over a rule nobody can cite a violation of.",
           ""]
    if report.get("missing"):
        out += ["> Sessions with no matching baseline or after snapshot, and therefore",
                "> not scored: " + ", ".join(report["missing"]), ""]
    if report.get("unscored"):
        out += ["> Blocks outside the gate (no ground truth, or ground truth for a block",
                "> neither payload judges):"]
        out += [f"> - {u}" for u in report["unscored"]] + [""]
    out += [
        f"{t['scored']} judged blocks scored, {t['excluded']} excluded as `undecidable`.", "",
        "| | before | after |",
        "|---|---|---|",
        f"| agrees with ground truth | {t['agreedBefore']} | {t['agreedAfter']} |",
        f"| false green | {t['falseGreenBefore']} | {t['falseGreenAfter']} |",
        f"| false red | {t['falseRedBefore']} | {t['falseRedAfter']} |",
        f"| missed compliance / violation | {t['missedBefore']} | {t['missedAfter']} |",
        f"| block not judged at all | {t['absentBefore']} | {t['absentAfter']} |",
        "",
        f"**fixed {t['fixed']} · regressed {t['regressed']} · still wrong {t['still-wrong']} "
        f"· agreed throughout {t['agreed']}**", "",
        "## Per session", "",
        "| session | scored | agreed before | agreed after | fixed | regressed | still wrong |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in sorted(report["bySession"].items()):
        out.append(f"| {name} | {s['scored']} | {s['agreedBefore']} | {s['agreedAfter']} | "
                   f"{s['fixed']} | {s['regressed']} | {s['still-wrong']} |")
    out += ["", "## Per failure mechanism", "",
            "| mechanism | scored | agreed before | agreed after | fixed | regressed | still wrong |",
            "|---|---|---|---|---|---|---|"]
    for name, s in sorted(report["byTag"].items()):
        out.append(f"| {name} | {s['scored']} | {s['agreedBefore']} | {s['agreedAfter']} | "
                   f"{s['fixed']} | {s['regressed']} | {s['still-wrong']} |")
    out += ["", "## Regressed rows (release blockers)", ""]
    reg = [r for r in report["rows"] if r["outcome"] == "regressed"]
    out += [_row_line(r) for r in reg] or ["None."]
    out += ["", "## Rows that are still wrong", ""]
    sw = [r for r in report["rows"] if r["outcome"] == "still-wrong"]
    out += [_row_line(r) for r in sw] or ["None."]
    out += ["", "## Excluded as undecidable", ""]
    ex = [r for r in report["rows"] if r["outcome"] == "excluded"]
    out += [_row_line(r) for r in ex] or ["None."]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-dir", type=Path, default=None)
    p.add_argument("--after-dir", type=Path, default=None)
    p.add_argument("--expected-dir", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="write the scorecard here too")
    args = p.parse_args()
    report = compare_all(args.baseline_dir, args.after_dir, args.expected_dir)
    text = "\n".join(render(report)) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    if report["totals"]["regressed"]:
        sys.exit(f"{report['totals']['regressed']} regressed verdict(s): release blocker")


if __name__ == "__main__":
    main()
