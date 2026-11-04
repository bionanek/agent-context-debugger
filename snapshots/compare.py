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

`regressed` (agreed before, wrong after) and `new-wrong` (not judged before,
wrong after) are release blockers. `still-wrong` rows are listed in full with
the ground truth's own `accept:` note where the miss is a known and accepted
limit. A session missing either half fails the run unless `--allow-partial`.
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

SNAPSHOTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SNAPSHOTS_DIR))

import audit_sessions  # noqa: E402
import take_baseline as tb  # noqa: E402

DEFAULT_BASELINE = SNAPSHOTS_DIR / "baseline"
DEFAULT_AFTER = SNAPSHOTS_DIR / "after"
DEFAULT_EXPECTED = SNAPSHOTS_DIR / "expected"

# What each truth class allows the tool to say. `used-partial` is allowed under
# `violated` because a session that broke a rule in one turn and followed it in
# another honestly combines to it.
ALLOWED = {
    "used": frozenset({"used", "used-partial"}),
    "violated": frozenset({"ignored", "used-partial"}),
    "no-hard-verdict": frozenset({"dormant", "unused", "possibly-referenced",
                                  "undelivered", "not-loaded"}),
    # `authorised`: the rule's action demonstrably happened and the user asked
    # for it in the prompt that caused it. Allows exactly what
    # `no-hard-verdict` allows, so a red badge here is a false red and a green
    # is a false green - but it is its own class because the fact is not
    # "nothing tied the block to the run". Something did, and it was not
    # misconduct. See RULINGS.md 9.
    "authorised": frozenset({"dormant", "unused", "possibly-referenced",
                             "undelivered", "not-loaded"}),
}
UNDECIDABLE = "undecidable"
TRUTHS = frozenset(ALLOWED) | {UNDECIDABLE}

GREENS = frozenset({"used", "used-partial"})
ABSENT = "(absent)"

# What a header has to say before its rows are scored. The corpus was written
# under two readings of `used` for descriptive blocks, and totals that mix them
# are not one measurement - so the pointer to the rulings file and the one
# sentence the two readings differed on are both required, whitespace-normalised
# so a rewrap does not break the check.
RULINGS_LINK = "snapshots/expected/RULINGS.md"
DIRECTORY_RULING = "A file created under a directory the block names does not count."

# A ground truth may cover one question rather than a whole session - the
# Phase 0 false-red set covers the one block a compiled record governs. Naming
# every other block of such a session would print hundreds of ids into this
# committed file, and a block id carries its document's path, so for a client
# repository it would publish the names of documents the transcripts are
# gitignored to keep out. A file that says this of itself gets a count instead.
PARTIAL_MARKER = "This file is deliberately partial."


def partial_scope(path):
    """Whether this ground truth declares itself partial, so its unscored
    blocks are counted rather than named."""
    return _norm(PARTIAL_MARKER) in _norm(Path(path).read_text(encoding="utf-8"))


# A `revised:` note is the one edit that can ratify the tool, so the row has to
# say whether the correction itself was derived blind. Yes or no: anything else
# is a claim nobody can check.
BLIND_ANSWERS = ("yes", "no")

# File kinds governed by the invoked-skill ruling (RULINGS.md 4). They outnumber
# the rest and one ruling decides how their identity blocks are credited, so a
# headline that mixes them with rule-document blocks reports that ruling as a
# measurement of the judging.
SKILL_KINDS = frozenset({"skill", "command", "agent"})


def _norm(text):
    return " ".join(text.split())


def error_kind(truth, status):
    """Which way a disagreement points, from the audited rule's side."""
    if status in ALLOWED[truth]:
        return None
    if status == ABSENT:
        # Its own kind, not a missed compliance: the tool said nothing at all
        # about this block, and filing that under "did not credit the rule"
        # would describe a vanished block as a judgement that was made.
        return "absent"
    if truth in ("no-hard-verdict", "authorised"):
        if status in GREENS:
            return "false-green"
        return "false-red" if status == "ignored" else "unexpected"
    if truth == "used":
        return "false-red" if status == "ignored" else "missed-compliance"
    return "false-green" if status in GREENS else "missed-violation"


# ---------- inputs ----------

def load_expected(path):
    """Parse one expected.md. Prose is ignored; verdict lines are the contract.

    Two things in the prose are not ignored: the header has to reference the
    rulings and quote the disputed one, and a `revised:` note has to carry a
    `blind:` answer. Both are refusals rather than warnings, because a row
    scored under an unstated ruling and a correction made while looking at the
    answer are the two ways this corpus has already been wrong.
    """
    text = Path(path).read_text(encoding="utf-8")
    flat = _norm(text)
    if RULINGS_LINK not in flat:
        raise ValueError(f"{path}: header does not reference {RULINGS_LINK}")
    if _norm(DIRECTORY_RULING) not in flat:
        raise ValueError(f"{path}: header does not state the descriptive-block "
                         f"ruling about a directory verbatim: {DIRECTORY_RULING!r}")
    out = {}
    last = None
    for raw in text.splitlines():
        line = raw.strip()
        if line and raw[0] not in " \t" and not (line.startswith("- ") and " :: " in line):
            # A note belongs to the row it is indented under; an `accept:` in a
            # later prose section is about something else.
            last = None
            continue
        if line.startswith("- ") and " :: " in line:
            parts = [p.strip() for p in line[2:].split(" :: ", 3)]
            if len(parts) != 4:
                raise ValueError(f"{path}: malformed verdict line: {raw}")
            bid, truth, tag, evidence = parts
            if bid in out:
                raise ValueError(f"{path}: block {bid} has two verdict lines")
            if truth not in TRUTHS:
                # Never silently excluded: a misspelling would otherwise take
                # the `undecidable` path and drop a block out of the gate.
                raise ValueError(f"{path}: unknown truth class {truth!r} for {bid}")
            out[bid] = {"truth": truth, "tag": None if tag == "-" else tag,
                        "evidence": evidence, "accept": None, "revised": None,
                        "blind": None}
            last = bid
        elif last:
            for key in ("accept", "revised", "blind"):
                if line.startswith(key + ":"):
                    out[last][key] = line[len(key) + 1:].strip()
    for bid, entry in out.items():
        if entry["blind"] is not None and entry["blind"] not in BLIND_ANSWERS:
            raise ValueError(f"{path}: {bid}: `blind:` must be one of "
                             f"{', '.join(BLIND_ANSWERS)}, not {entry['blind']!r}")
        if entry["revised"] and entry["blind"] is None:
            raise ValueError(f"{path}: {bid}: a `revised:` note requires a `blind:` "
                             "line saying whether the correction was derived blind")
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
            if b.get("status") in tb.DELIVERY_STATUSES:
                continue
            out[b["id"]] = b.get("status")
    return out


def delivery_statuses(payload, session_id=None):
    """{block id: status} for the blocks the payload says never reached the model.

    `judged_statuses` leaves these out because a block nobody offered for
    judging has no verdict. A block the truth *does* cover is different: a
    `not-loaded` there is the tool's answer about it, and `ALLOWED` already
    names it as honest for `no-hard-verdict`. Read as absent instead, the fix
    that stopped a file being reported in context when it never was scored as
    51 regressions.
    """
    sessions = payload["perSession"]
    if session_id is None:
        session_id = next(iter(sessions))
    return {b["id"]: b.get("status")
            for f in sessions[session_id].get("contextFiles", [])
            for b in f.get("blocks", []) if b.get("status") in tb.DELIVERY_STATUSES}


def judged_halves(payload, session_id=None):
    """{block id: "skill" | "rule-document"}, from the file each block sits in.

    Read off the payload's own `kind` rather than guessed from the path: the
    loader already decided what a document is, and a second classifier here
    would put a block in one half of the scorecard and the other half of the
    tool.
    """
    sessions = payload["perSession"]
    if session_id is None:
        session_id = next(iter(sessions))
    out = {}
    for f in sessions[session_id].get("contextFiles", []):
        half = "skill" if f.get("kind") in SKILL_KINDS else "rule-document"
        for b in f.get("blocks", []):
            out[b["id"]] = half
    return out


def _manifest(snap_dir):
    if not (Path(snap_dir) / "manifest.json").is_file():
        return {}
    return tb._read_manifest(snap_dir)


def has_checks_file(snap_dir):
    """Whether this snapshot froze a reviewed `<doc>.checks.json` alongside its rules.

    Without one, no compiled check ran, so the corpus says nothing about the
    only mechanism allowed to call a rule violated.
    """
    return any(str(e.get("key", "")).endswith(".checks.json")
               for e in _manifest(snap_dir).get("inputs") or [])


def _session_id(snap_dir):
    return _manifest(snap_dir).get("sessionId")


# ---------- scoring ----------

def compare_session(name, baseline_dir, after_dir, expected_file, input_changed=False):
    """Returns (rows, unscored) - the second being blocks no truth class covers.

    A block either payload judges but the ground truth does not name is not
    scored, and saying nothing about it would let a green the after-run
    invented (a delivery reclassification adds a block, say) sit outside the
    gate entirely. A ground-truth id present in neither payload is the same
    problem pointed the other way - a stale line quietly scored as a miss.

    `input_changed` marks every row whose verdict moved: the after-run read an
    input the baseline payload never did, so the move is not evidence about
    the judging code alone.
    """
    expected = load_expected(expected_file)
    before_payload, after_payload = read_payload(baseline_dir), read_payload(after_dir)
    before = judged_statuses(before_payload, _session_id(baseline_dir))
    after = judged_statuses(after_payload, _session_id(after_dir))
    halves = dict(judged_halves(after_payload, _session_id(after_dir)))
    halves.update(judged_halves(before_payload, _session_id(baseline_dir)))
    outside = [bid for bid in sorted(set(before) | set(after)) if bid not in expected]
    if partial_scope(expected_file):
        unscored = ([f"{name}: {len(outside)} judged block(s) outside this ground "
                     f"truth's declared scope, not named here"] if outside else [])
    else:
        unscored = [f"{name} {bid}: judged `{before.get(bid) or after.get(bid)}` "
                    f"with no ground truth" for bid in outside]
    unscored += [f"{name} {bid}: ground truth for a block neither payload judges"
                 for bid in sorted(expected)
                 if bid not in before and bid not in after]
    before_undelivered = delivery_statuses(before_payload, _session_id(baseline_dir))
    after_undelivered = delivery_statuses(after_payload, _session_id(after_dir))
    rows = []
    for bid, exp in expected.items():
        b = before.get(bid) or before_undelivered.get(bid, ABSENT)
        a = after.get(bid) or after_undelivered.get(bid, ABSENT)
        if exp["truth"] == UNDECIDABLE:
            rows.append({"session": name, "id": bid, "truth": exp["truth"],
                         "tag": exp["tag"], "before": b, "after": a,
                         "beforeError": None, "afterError": None,
                         "outcome": "excluded", "accept": exp["accept"],
                         "revised": exp["revised"], "blind": exp["blind"],
                         "evidence": exp["evidence"],
                         "half": halves.get(bid, "rule-document"),
                         "inputChanged": input_changed and b != a})
            continue
        be = error_kind(exp["truth"], b)
        ae = error_kind(exp["truth"], a)
        if b == ABSENT:
            # Nothing was judged before, so there is no error to have fixed or
            # kept: counted as `fixed` it inflates the improvement, as
            # `still-wrong` a new false green never reaches the gate.
            outcome = "new-agreed" if ae is None else "new-wrong"
        elif be is None and ae is None:
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
                     "blind": exp["blind"], "evidence": exp["evidence"],
                     "half": halves.get(bid, "rule-document"),
                     "inputChanged": input_changed and b != a})
    return rows, unscored


def _tally(rows):
    t = {k: 0 for k in ("scored", "excluded", "agreed", "fixed", "regressed", "still-wrong",
                        "new-agreed", "new-wrong", "nonBlindCredited", "agreedBefore", "agreedAfter", "falseGreenBefore", "falseGreenAfter",
                        "falseRedBefore", "falseRedAfter", "missedBefore", "missedAfter",
                        "absentBefore", "absentAfter", "violatedTruths",
                        "authorisedTruths", "falseRedAuthorisedAfter",
                        "nowUndelivered")}
    for r in rows:
        t[r["outcome"]] += 1
        if r["outcome"] == "excluded":
            continue
        t["scored"] += 1
        if r["blind"] == "no" and r["outcome"] in ("fixed", "agreed", "new-agreed"):
            t["nonBlindCredited"] += 1
        if r["truth"] == "violated":
            t["violatedTruths"] += 1
        if r["truth"] == "authorised":
            t["authorisedTruths"] += 1
            # Offline a red on an authorised row is the design working, not a
            # regression: the finding stays `violated` and the reader is shown
            # the prompt. Counting these apart is what keeps the headline from
            # reading as the tool having started accusing the innocent.
            if r["afterError"] == "false-red":
                t["falseRedAuthorisedAfter"] += 1
        if (r["after"] in tb.DELIVERY_STATUSES
                and r["before"] not in tb.DELIVERY_STATUSES and r["before"] != ABSENT):
            t["nowUndelivered"] += 1
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
    rows, missing, unscored, checks_files = [], [], [], []
    input_changed = {}
    for exp in sorted(expected_dir.glob("*/*/expected.md")):
        project, prefix = exp.parent.parent.name, exp.parent.name
        name = f"{project}/{prefix}"
        b, a = baseline_dir / project / prefix, after_dir / project / prefix
        if not b.is_dir() or not a.is_dir():
            # Named, never skipped: a gate that quietly shrinks to the sessions
            # that still have both halves reports a better number than it earned.
            missing.append(name)
            continue
        added = tb.inputs_added_after_bake(_manifest(b))
        if added:
            input_changed[name] = added
        session_rows, session_unscored = compare_session(name, b, a, exp, bool(added))
        rows.extend(session_rows)
        unscored.extend(session_unscored)
        if has_checks_file(b):
            checks_files.append(name)
    by_session, by_tag, by_half = {}, {}, {}
    for r in rows:
        by_session.setdefault(r["session"], []).append(r)
        by_tag.setdefault(r["tag"] or "(untagged)", []).append(r)
        by_half.setdefault(r["half"], []).append(r)
    for half in ("skill", "rule-document"):
        by_half.setdefault(half, [])
    return {"rows": rows, "totals": _tally(rows), "missing": missing, "unscored": unscored,
            "checksFiles": checks_files, "inputChanged": input_changed,
            "bySession": {k: _tally(v) for k, v in by_session.items()},
            "byTag": {k: _tally(v) for k, v in by_tag.items()},
            "byHalf": {k: _tally(v) for k, v in by_half.items()}}


BLOCKING = ("regressed", "new-wrong")


def blockers(report):
    """Every regression or new wrong verdict, as `<session> <block>`."""
    return [f"{r['session']} {r['id']}" for r in report["rows"] if r["outcome"] in BLOCKING]


# ---------- rendering ----------

def _row_line(r):
    line = (f"- `{r['session']}` **{r['id']}** - truth `{r['truth']}`"
            f"{' [' + r['tag'] + ']' if r['tag'] else ''}: "
            f"`{r['before']}` -> `{r['after']}`"
            f"{' [input changed after baseline]' if r.get('inputChanged') else ''}. "
            f"{r['evidence']}")
    if r["accept"]:
        line += f"\n  - accepted: {r['accept']}"
    if r["revised"]:
        line += (f"\n  - ground truth revised (blind: {r['blind']}): {r['revised']}")
    return line


def _half_table(report, half, title, note):
    t = report["byHalf"].get(half) or {}
    if not t.get("scored") and not t.get("excluded"):
        return [f"## {title}", "", "No rows in this half.", ""]
    return [f"## {title}", "", note, "",
            "| | before | after |", "|---|---|---|",
            f"| agrees with ground truth | {t['agreedBefore']} | {t['agreedAfter']} |",
            f"| false green | {t['falseGreenBefore']} | {t['falseGreenAfter']} |",
            f"| false red | {t['falseRedBefore']} | {t['falseRedAfter']} |",
            f"| missed compliance / violation | {t['missedBefore']} | {t['missedAfter']} |",
            f"| block not judged at all | {t['absentBefore']} | {t['absentAfter']} |",
            "",
            f"**{t['scored']} scored · fixed {t['fixed']} · regressed {t['regressed']} "
            f"· still wrong {t['still-wrong']} · new agreed {t['new-agreed']} "
            f"· new wrong {t['new-wrong']}**", ""]


# Said in the header, every time, because the false-red count is the number a
# reader is most likely to quote and the one most likely to be over-read. A
# scan of all 1,093 of this author's transcripts found no clean unsupervised
# violation: every candidate action was ordered in the prompt that caused it,
# because this author works with the agent in the loop. So the red side is
# measured against actions the user authorised, not against misconduct.
NO_UNSUPERVISED_VIOLATION = (
    "The corpus holds no genuine unsupervised violation, so a false-red count "
    "of zero is measured against authorised actions only - the rule's action "
    "happened and the user asked for it in the prompt that caused it. Whether "
    "the tool accuses correctly when nobody authorised the action is still "
    "unmeasured; subagent and workflow runs are the candidate hunting ground.")


OFFLINE_RED_ON_AUTHORISED = (
    "Offline that is the design working rather than a regression: the finding "
    "stays `violated` and the report prints the governing prompt beside the "
    "cited call, and only the judged run may downgrade it to `acknowledged`. "
    "These payloads are baked offline, so the judged outcome is not in this "
    "table; asked the authorisation question over each of these calls, the "
    "judge answered `authorised` for every one, which is what downgrades the "
    "finding and returns the judged false-red count to zero.")


# The criteria this corpus was built to satisfy and does not. They were each
# disclosed somewhere - in the plan's report, in RULINGS.md - but a reader
# quotes the number from this file, so the shortfalls belong beside it.
CRITERIA_UNMET = (
    "**Acceptance criteria this corpus does not meet**, named rather than "
    "redefined. *Seven sessions frozen with `authorised` truth*: see the next "
    "paragraph. And none of these reds existed before this corpus was frozen, "
    "so both the after column's false-red total and its `still wrong` total "
    "rose against the pre-corpus numbers - these sessions were added precisely "
    "to give the red side something to measure. One shortfall recorded here "
    "earlier is closed rather than restated: the judged run used to clear five "
    "of six, and the sixth red was a pattern reaching across `&&` into a "
    "command the rule is not about. A pattern may no longer span a command "
    "join, so those two sessions carry no red at all and the four that remain "
    "are the authorised ones the judge clears.")


FROZEN_SET_SHORTFALL = (
    "Of the six frozen push sessions only four carry `authorised` truth - in "
    "two the rule's action never happened, so their truth is `no-hard-verdict` "
    "- and one further session named in the plan was deliberately not frozen, "
    "because no rule it loads is compiled and a row over it could only confirm "
    "the absence of an accusation that was never reachable. See RULINGS.md 9.")


def _coverage_lines(report):
    """What the corpus can and cannot measure, said before any number is read."""
    t = report["totals"]
    files = report.get("checksFiles") or []
    out = [f"Red-side coverage: {t['violatedTruths']} `violated` truth"
           f"{'' if t['violatedTruths'] == 1 else 's'} in the scored rows, and "
           f"{len(files)} session{'' if len(files) == 1 else 's'} "
           f"carr{'ies' if len(files) == 1 else 'y'} a compiled checks file"
           + (" (" + ", ".join(files) + ")." if files else ".")]
    if t["authorisedTruths"]:
        out += ["", f"{t['authorisedTruths']} `authorised` truth"
                    f"{'' if t['authorisedTruths'] == 1 else 's'} in the scored rows. "
                + NO_UNSUPERVISED_VIOLATION,
                "", CRITERIA_UNMET,
                "", FROZEN_SET_SHORTFALL]
        if t["falseRedAuthorisedAfter"]:
            out += ["", f"{t['falseRedAuthorisedAfter']} of the "
                        f"{t['falseRedAfter']} red badge"
                        f"{'' if t['falseRedAfter'] == 1 else 's'} in the after "
                        "column stand"
                        f"{'s' if t['falseRedAuthorisedAfter'] == 1 else ''} on an "
                        "`authorised` row. " + OFFLINE_RED_ON_AUTHORISED]
    if (not t["violatedTruths"] and not t["authorisedTruths"]) or not files:
        out += ["",
                "> **Warning: the red side of this corpus is unmeasured.** With no "
                "`violated` or `authorised` truth, or with no compiled checks file for "
                "any session, nothing here could have produced a red badge - so a "
                "false-red count of zero records that the tool stopped accusing, not "
                "that it accuses correctly."]
    return out + [""]


BLIND_JUDGE_RECORD = SNAPSHOTS_DIR / "blind_judge.json"

BLIND_JUDGE_FIELDS = ("when", "sessions", "blocks", "calls", "callsFailed",
                      "falseGreen", "falseRed", "missed", "agrees", "codeAgrees",
                      "codeFalseGreen", "codeFalseRed", "codeMissed",
                      "bothRight", "judgeOnly", "codeOnly", "neither")


def load_blind_judge(path=None):
    """The dated blind-judge experiment, read from its own committed record.

    The numbers deliberately do not live in this generator: the file it writes
    says "do not edit by hand", so a row whose values were written down here
    would be a published number related to no artifact at all. Read from a
    record, editing that record is the only way the row can move, and a reader
    can diff it.

    The three sums are re-checked on every load. They are the only part of the
    experiment this repo can falsify - no harness for it is committed - so a
    transcription error raises here rather than rendering.
    """
    path = Path(path or BLIND_JUDGE_RECORD)
    if not path.is_file():
        return None
    rec = json.loads(path.read_text(encoding="utf-8"))
    missing = [f for f in BLIND_JUDGE_FIELDS if f not in rec]
    if missing:
        raise ValueError(f"{path}: blind-judge record is missing {', '.join(missing)}")
    split = rec["bothRight"] + rec["judgeOnly"] + rec["codeOnly"] + rec["neither"]
    for label, got, want in (
            ("bothRight + judgeOnly + codeOnly + neither", split, rec["blocks"]),
            ("bothRight + judgeOnly", rec["bothRight"] + rec["judgeOnly"], rec["agrees"]),
            ("bothRight + codeOnly", rec["bothRight"] + rec["codeOnly"],
             rec["codeAgrees"])):
        if got != want:
            raise ValueError(f"{path}: {label} is {got}, not {want} - the four-way "
                             "split contradicts the totals it was derived from")
    return rec


NO_BLIND_JUDGE_RECORD = (
    "**There is no blind-judge record in this tree, so no judge row is "
    "printed.** The experiment's numbers are published only from "
    "`snapshots/blind_judge.json`; with that file absent this scorecard has "
    "nothing to say about the judge tier, and printing remembered figures "
    "would be a number with no artifact behind it.")


# A record this harness wrote says so in its own `source`. The distinction is
# the whole difference between a number a reader can contradict and one they
# can only take on trust, so it is read off the record rather than assumed from
# the file being present.
HARNESS = "snapshots/blind_judge.py"


def reproducible(j):
    """Whether this record came from the committed harness."""
    return HARNESS.rsplit("/", 1)[-1] in (j.get("source") or "")


def blind_judge_provenance(j):
    """Said at the row, because the table prints it in the measured row's shape."""
    if reproducible(j):
        unanswered = j.get("unanswered")
        return (
            "The judge row **is a reading of this corpus**, produced by "
            f"`{HARNESS}` on {j['when']} with `{j.get('model')}` over "
            f"{j['blocks']} of the corpus's scored blocks. The judge was handed "
            "exactly what the ground-truth author was handed - `inventory.py`'s "
            "actions and joins views plus `RULINGS.md` - and never the tool's "
            "verdict, and both columns of this table are scored over those same "
            f"{j['blocks']} blocks with the same `error_kind`, so the two are "
            "comparable with each other. They are not comparable with the "
            "before/after tables above, which score "
            + (f"a few more blocks: {j['calls']} call(s) were made, "
               f"{j['callsFailed']} failed")
            + (f" and {unanswered} block(s) went unanswered" if unanswered else "")
            + ". The code column here is this corpus baked offline, as everywhere "
            "else in this file.")
    return (
        "The judge row is **not a reading of this corpus**. It is the "
        f"blind-judge experiment of {j['when']} over {j['blocks']} blocks from "
        f"{j['sessions']} sessions, recorded in `snapshots/blind_judge.json` and "
        f"not re-run for this scorecard: the harness was a one-off, "
        f"{j['callsFailed']} of its {j['calls']} calls failed - taking three "
        "whole sessions out of the scored set, skewed toward `used` truths - and "
        "re-running it would send a client's rule text and transcripts to a "
        "model. The code row beside it is this corpus, baked offline. Two "
        "different block sets, printed together because the pair of false-green "
        "counts is the whole argument; neither row is a control for the other.")


# Said plainly because the table prints the judge row in the same shape as the
# measured one. The blind-judge harness was not re-run for this scorecard and
# no harness for it exists here, so neither the row nor the four-way split
# below it can be reproduced or contradicted by anything in this repo.
JUDGE_ROW_FALSIFIABLE = (
    "**The judge row can be reproduced and contradicted.** Re-run it with "
    f"`python3 {HARNESS}`, which asks the question again and rewrites the "
    "record; a change that makes the judge worse moves these numbers. Three "
    "limits stay, and none of them is the one this replaced. The frozen corpus "
    "is gitignored, so only its author can re-run it. The protocol is this "
    "harness's, not the 2026-11-04 one-off's - that run left nothing behind, "
    "so its wording, batching and retries are unrecoverable and its numbers "
    "are history rather than a baseline this can be diffed against. And the "
    "model is named on the row rather than pinned: a judge is re-measured "
    "against whatever model answers today, so a row read a year from now "
    "describes that model and not this one.")

JUDGE_ROW_NOT_FALSIFIABLE = (
    "**Nothing in this repo can reproduce or falsify the judge row, or the "
    "four-way split below it.** The record it is read from is a transcript of "
    "a one-off run, no harness for that run is committed here, and it was not "
    "re-run for this scorecard: both are dated history, and a later change "
    "that makes the judge worse will leave these numbers unchanged. Nor do "
    "they describe the tier in this tree - the repo records no copy of "
    "`judge_tier.py` as the experiment measured it, and the file has been "
    "edited since (the judge now runs by default), so no check here can tell a "
    "reader when the row stopped applying. Re-measuring needs a harness, and "
    "that is a phase of its own.")


def _false_red_clause(j):
    """The false-red comparison, said whichever way it came out.

    This sentence was written when the judge posted eleven false reds against
    the code tier's zero, and it asserted a direction rather than reporting
    one. A re-measurement that puts the judge below the code tier leaves the
    phrasing describing the opposite of its own figures - and the claim beside
    it, the false-green gap, is what the whole architecture rests on, so a
    reader who catches the contradiction discounts both. The false-green gap is
    the argument; the reds are reported, not argued from.
    """
    jr, cr = j["falseRed"], j["codeFalseRed"]
    if jr > cr:
        return f"It also posted {jr} false reds against the code tier's {cr}."
    if jr == cr:
        return (f"On false reds the two are level, at the same {jr} - a count "
                "this corpus measures only against authorised actions, since "
                "it holds no genuine unsupervised violation.")
    return (f"On false reds it did better: fewer false reds than the code tier, "
            f"{jr} against {cr}. That column is not like for like. The code "
            "tier's reds here are the authorised rows, standing because these "
            "payloads are baked offline and only the judged run may downgrade "
            "one to `acknowledged` - and the corpus holds no genuine "
            "unsupervised violation for either tier to be measured on. It is "
            "not evidence that a model accuses more carefully than a compiled "
            "check with a citable span.")


def _four_way_lines(j):
    """The experiment's four-way split, which is what the architecture rests on."""
    where = "this corpus's" if reproducible(j) else "that experiment's own"
    return [
        f"On {where} {j['blocks']} blocks the two tiers split four "
        f"ways: both right {j['bothRight']}, judge right and code wrong "
        f"{j['judgeOnly']}, code right and judge wrong {j['codeOnly']}, neither "
        f"{j['neither']}. The judge agreed with the ground truth more often "
        f"({j['agrees']} against {j['codeAgrees']}) and was wrong in the one "
        f"direction that cannot be shown to a reader as a verdict: "
        f"{j['falseGreen']} false greens against the code tier's "
        f"{j['codeFalseGreen']}. " + _false_red_clause(j)
        + " Where it is better is the missed compliance - "
        f"{j['missed']} against {j['codeMissed']} - which is exactly what the "
        f"contested chip surfaces without letting it decide anything."]


# How often the judge contests at all, measured over the frozen corpus in the
# phase that added the chip. A ceiling rather than an observed rate: it counts
# every block eligible to be contested, and each still has to clear the quote
# gate. Stated beside the false-green count because the two together are the
# answer to "why does the judge not get a badge".
CONTESTED_RATE = (
    "Contested rate: at most 18 of the 11,991 session-scope blocks in the "
    "frozen corpus (0.2%) can carry the chip at all - a block is eligible only "
    "where its status is `unused` or `dormant` and its document parked a "
    "record for the judge, and only 48 blocks (0.4%) have a parked record of "
    "any kind.")


def contested_rate_line(j):
    """The contested ceiling, and - where the record is here - what it answers."""
    if j is None:
        return CONTESTED_RATE
    return (CONTESTED_RATE + " Beside it stands the judge's own false-green count "
            f"of {j['falseGreen']}: that is why a contested block keeps its badge "
            "and gains a chip instead.")


# The scorecard the plan's later phases are measured against, read off this
# file at the commit before Phase 1 (`112cff0`). Carried here because the
# criterion is a direction, and a direction needs the number it moved from.
PRE_PLAN_MISSED = {"all": 122, "skill": 73, "ruleDocument": 49}


MISSED_BASELINE_NOTE = (
    "Measured against the pre-Phase-1 reading of this same corpus - 122 over "
    "all blocks, 73 in the skill half, 49 in the rule-document half.")


def missed_direction(missed):
    """Which way missed compliance moved against the pre-plan reading.

    Computed from the rows rather than written down, because the criterion is
    a direction and a hand-written one survives the measurement that falsifies
    it.
    """
    base = PRE_PLAN_MISSED["all"]
    return "unchanged" if missed == base else ("down" if missed < base else "up")


# Why the number can be unchanged without anything having gone wrong, and why
# that is still a criterion unmet rather than a result. Said at the number,
# because this is the file the number is quoted from.
MISSED_UNCHANGED_NOTE = (
    "Unchanged is the honest reading, not a null result dressed up: the work "
    "between those two readings added reporting surfaces - the compile-status "
    "screen, the bucket mix, the contested chip, the judge mode - and no "
    "verdict path, and no new checks file entered the corpus. Missed "
    "compliance moves when rules get compiled, which is the one thing none of "
    "it did. **Acceptance criterion unmet**, named rather than redefined.")


def _tier_lines(report):
    """Both tiers' false counts in one table, and what each row is made of."""
    t = report["totals"]
    j = load_blind_judge()
    # Where the record is this harness's, both rows are read from it: it scored
    # the code tier over the same blocks it asked the judge about, and the pair
    # of false-green counts is the whole argument for the chip. A pair taken
    # over two different block sets is not a pair, and the whole-corpus totals
    # cover blocks the judge was never asked about.
    paired = j is not None and reproducible(j)
    code_row = (f"| compiled checks (this corpus, after, {j['blocks']} blocks) | "
                f"{j['codeFalseGreen']} | {j['codeFalseRed']} | {j['codeMissed']} |"
                if paired else
                f"| compiled checks (this corpus, after) | {t['falseGreenAfter']} | "
                f"{t['falseRedAfter']} | {t['missedAfter']} |")
    out = ["## Both tiers, side by side", "",
           "The compiled path may accuse and the judge may not. These two rows "
           "are the reason.", "",
           "| tier | false green | false red | missed compliance |",
           "|---|---|---|---|",
           code_row]
    if j is None:
        out += ["", NO_BLIND_JUDGE_RECORD, ""]
    else:
        out += [f"| blind judge ({j['when']}, {j['blocks']} blocks"
                + (f", `{j['model']}`)" if paired else ")") + " | "
                f"{j['falseGreen']} | {j['falseRed']} | {j['missed']} |",
                "", blind_judge_provenance(j), "",
                JUDGE_ROW_FALSIFIABLE if reproducible(j)
                else JUDGE_ROW_NOT_FALSIFIABLE,
                ""] + _four_way_lines(j) + [""]
    return out + [
        contested_rate_line(j), "",
        f"Missed compliance in the after column is {t['missedAfter']} over all "
        f"scored blocks, {report['byHalf']['skill']['missedAfter']} in the skill "
        f"half and {report['byHalf']['rule-document']['missedAfter']} in the "
        f"rule-document half, {missed_direction(t['missedAfter'])} against the "
        f"baseline the criterion names. " + MISSED_BASELINE_NOTE
        + (" " + MISSED_UNCHANGED_NOTE
           if missed_direction(t["missedAfter"]) == "unchanged" else ""), ""]


TABLE_HEAD = ("| {} | scored | agreed before | agreed after | fixed | regressed | still wrong "
              "| new agreed | new wrong |")
TABLE_RULE = "|---|---|---|---|---|---|---|---|---|"


def _table_row(label, s):
    return (f"| {label} | {s['scored']} | {s['agreedBefore']} | {s['agreedAfter']} | "
            f"{s['fixed']} | {s['regressed']} | {s['still-wrong']} | {s['new-agreed']} | "
            f"{s['new-wrong']} |")


def render(report):
    t = report["totals"]
    out = ["# Verdict scorecard: baseline vs after vs ground truth", "",
           "Generated by `python3 snapshots/compare.py --out snapshots/SCORECARD.md`. Do not",
           "edit by hand - regenerate it, so the numbers stay the ones the snapshots hold.",
           "",
           "Both halves are baked from the *same* frozen inputs (`snapshots/baseline/*/inputs/`),",
           "so a verdict that moved moved because the judging code did"
           + (" - except in the sessions marked *input changed after baseline* below."
              if report.get("inputChanged") else "."),
           "The ground truth in",
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
    if report.get("inputChanged"):
        out += ["> Input changed after baseline: in these sessions the baseline payload was",
                "> baked before the inputs named here were frozen in, so the after-run read",
                "> something the baseline did not and a verdict that moved there may have",
                "> moved because of the input:"]
        out += [f"> - {name}: " + ", ".join(f"`{k}`" for k in keys)
                for name, keys in sorted(report["inputChanged"].items())] + [""]
    out += _coverage_lines(report)
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
        f"· agreed throughout {t['agreed']} · new agreed {t['new-agreed']} "
        f"· new wrong {t['new-wrong']}**", "",
        "`new agreed` / `new wrong` are blocks the baseline never judged: there was no "
        "earlier error to fix, so they are kept out of `fixed` and `still wrong`.", "",
        f"{t['nonBlindCredited']} of the fixed / agreed / new-agreed rows rest on a truth "
        "revised with `blind: no` - the edit that can ratify the tool.", "",
        f"{t['nowUndelivered']} scored rows the baseline judged are reported by the "
        "after-run as never having reached the model (`not-loaded` / `undelivered`). "
        "They are scored on that answer, so a delivery change is counted here rather "
        "than hidden in the agreement column.", "",
    ]
    out += _half_table(report, "skill", "Skill and command blocks",
                       "Governed by the invoked-skill ruling (RULINGS.md 4), which credits "
                       "an invocation to the document's identity block alone, so a step here "
                       "is scored on evidence of its own.")
    out += _half_table(report, "rule-document", "Rule-document blocks",
                       "The half the judging mechanisms actually decide, one block at a "
                       "time. This is the number the reliability claim is about.")
    out += _tier_lines(report)
    out += [
        "## Per session", "",
        TABLE_HEAD.format("session"), TABLE_RULE,
    ]
    changed = report.get("inputChanged") or {}
    for name, s in sorted(report["bySession"].items()):
        label = f"{name} (input changed after baseline)" if name in changed else name
        out.append(_table_row(label, s))
    out += ["", "## Per failure mechanism", "", TABLE_HEAD.format("mechanism"), TABLE_RULE]
    for name, s in sorted(report["byTag"].items()):
        out.append(_table_row(name, s))
    out += ["", "## Release blockers (regressed and new-wrong rows)", ""]
    reg = [r for r in report["rows"] if r["outcome"] in BLOCKING]
    out += [_row_line(r) for r in reg] or ["None."]
    out += ["", "## Rows that are still wrong", ""]
    sw = [r for r in report["rows"] if r["outcome"] == "still-wrong"]
    out += [_row_line(r) for r in sw] or ["None."]
    out += ["", "## Excluded as undecidable", ""]
    ex = [r for r in report["rows"] if r["outcome"] == "excluded"]
    out += [_row_line(r) for r in ex] or ["None."]
    out += [""] + audit_sessions.footer_lines()
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline-dir", type=Path, default=None)
    p.add_argument("--after-dir", type=Path, default=None)
    p.add_argument("--expected-dir", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None, help="write the scorecard here too")
    p.add_argument("--allow-partial", action="store_true",
                   help="exit 0 even when some sessions have no baseline or after snapshot")
    args = p.parse_args()
    # Every session lands in `missing` when a whole tree is absent, and the
    # scorecard then renders zero rows and exits 0 - a clone would read that as
    # a clean gate rather than as no gate at all.
    for label, given, default in (("baseline", args.baseline_dir, DEFAULT_BASELINE),
                                  ("after", args.after_dir, DEFAULT_AFTER),
                                  ("expected", args.expected_dir, DEFAULT_EXPECTED)):
        path = Path(given or default)
        if not path.is_dir():
            sys.exit(f"error: no {label} tree at {path}. The frozen corpus is "
                     "the author's own sessions and is gitignored, so a clone "
                     "cannot regenerate the scorecard; see the trust-model "
                     "section of README.md.")
    report = compare_all(args.baseline_dir, args.after_dir, args.expected_dir)
    text = "\n".join(render(report)) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    blocked = blockers(report)
    if blocked:
        sys.exit(f"{len(blocked)} regressed or new-wrong verdict(s): release blocker")
    if report["missing"] and not args.allow_partial:
        sys.exit(f"{len(report['missing'])} session(s) not scored ("
                 + ", ".join(report["missing"]) + "); pass --allow-partial to accept "
                 "a scorecard over fewer sessions than the ground truth names")


if __name__ == "__main__":
    main()
