#!/usr/bin/env python3
"""The sessions the external re-audit runs on, and the commands that walk them.

The scorecard is self-graded: its ground truth and its thresholds were written
against the eight anchor sessions in `sessions.json`. A claim about reliability
is therefore only worth what it survives on sessions nobody calibrated against,
so the gate is an audit of these sixteen - and it is a gate only if the next
person can run the same one, which is what this list is for.

Every session here must stay *outside* `sessions.json`; the disjointness is
asserted by `tests/test_audit_sessions.py` and by `--check`, because an anchor
that drifted into this list would turn the external gate back into the
self-graded measurement it exists to check.

    python3 snapshots/audit_sessions.py            # the three runs and their commands
    python3 snapshots/audit_sessions.py --check    # disjointness gate, exits non-zero on overlap

The transcripts themselves are the author's own sessions and are not in the
repo (see `snapshots/sessions.json`), so a clone has this list and none of the
sessions it names.
"""
import argparse
import json
import os
import sys
from pathlib import Path

SNAPSHOTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SNAPSHOTS_DIR.parent
DEFAULT_SESSIONS_FILE = SNAPSHOTS_DIR / "sessions.json"

# Non-anchor sessions, by project. Named in the plan's architectural decisions
# as the acceptance test for the whole judgement-reliability rebuild.
AUDIT_SESSIONS = {
    "famigo": ["9e01f3df", "78c658bc", "139cf0b9", "3f8c828d"],
    "formic-core": ["919f9e32", "afe37732", "1916e68e", "5171447d"],
    "formicHMI": ["7eb46245", "13e972ee"],
    "reband": ["51fdcc25", "71c4d1ca", "f7136fed", "113a0d2c"],
    "agent-context-ide": ["9cf0b16d", "406bba1d"],
}

# One auditor run per group. Splitting the sixteen three ways keeps each run's
# context inside one agent's budget; pairing projects that share a rule style
# lets one auditor see the same mechanism twice.
RUNS = [
    ("famigo + agent-context-ide", ["famigo", "agent-context-ide"]),
    ("formic-core + formicHMI", ["formic-core", "formicHMI"]),
    ("reband", ["reband"]),
]

# The auditor derives ground truth from raw transcripts; reading any of these
# would let it grade the tool against the tool's own answer sheet.
WITHHELD = [
    "snapshots/SCORECARD.md",
    "snapshots/expected/",
    "snapshots/after/",
    "snapshots/baseline/",
]


# The last external re-audit, passed or failed, or None if none has run. It is
# written by hand because the gate is three agent reports read by a human, not
# something this repo can recompute - and the scorecard's footer is rendered
# from it, so a claim about an external audit cannot outlive the audit's own
# record here. `falseGreens` / `falseReds` are the counts the runs reported
# between them. A failed audit is recorded exactly like a passed one: dropping
# it would leave the self-graded tables above reading as unchallenged.
LAST_AUDIT = {
    "date": "2026-11-04",
    "runs": 3,
    "passed": False,
    "falseGreens": 1,
    "falseReds": 0,
    # The sessions an auditor could actually open; a transcript the harness
    # has since deleted cannot be audited, and the headline must not count it.
    "audited": 11,
    # Read by every auditor so both sides share one definition of `used`.
    "provided": ["snapshots/expected/RULINGS.md"],
    # A zero here is unmeasurable without saying what could have produced a
    # red, and none of the audited sessions could: every `ignored` verdict
    # needs a reviewed checks file beside the rule document, and no project in
    # this list has one. All three runs said so unprompted.
    "redSide": (
        "The zero false reds is not evidence the tool accuses correctly: none "
        "of the audited sessions has a compiled checks file, so no `ignored` "
        "verdict was reachable in any of them and all three runs said so. The "
        "red path is measured on the anchor corpus instead, where two sessions "
        "carry one."),
    "note": (
        "Only 11 of the 16 sessions could be audited: the transcripts of "
        "formic-core `919f9e32`, `1916e68e`, `5171447d` and formicHMI "
        "`7eb46245`, `13e972ee` are no longer on disk (their ctxlog files "
        "survive). Unlike the 2026-09-05 run, each auditor was given "
        "`snapshots/expected/RULINGS.md` so the two sides share one definition "
        "of `used`; everything else under `snapshots/expected/` stayed "
        "withheld. 30 greens were checked against the raw transcripts. The one "
        "false green is famigo `78c658bc`, the `/review` skill's Step 4 block: "
        "it reads `used` on a `grep` that searched `mobile/CLAUDE.md`, but the "
        "skill text the session was given named `mobile/AGENT.md` there (the "
        "tool judged the disk copy, because it does not recover a skill body "
        "delivered as an `isMeta` user event), and the grep was Step 6's "
        "documentation check rather than Step 4's review. It is the same "
        "mechanism as the anchor corpus's one false green: a read inside a "
        "running skill is credited to every step that names the file. The "
        "audit also found misreported context that is not a green or a red: "
        "`./AGENTS.md` and files a hook only suggested reading are marked "
        "loaded and priced (about 1.75M tokens in formic-core `afe37732`), "
        "and a skill read with `cat` is reported as never in context."),
}


def anchor_sessions(sessions_file=DEFAULT_SESSIONS_FILE):
    """The calibration set: {session id: project}."""
    data = json.loads(Path(sessions_file).read_text(encoding="utf-8"))
    return {s["session"]: s["project"] for s in data["sessions"]}


def project_cwds(sessions_file=DEFAULT_SESSIONS_FILE):
    """Working directory per project, read off the anchor list.

    The audit list carries session ids only: two lists of the same paths would
    be two things to keep in step, and a wrong cwd here resolves the project's
    CLAUDE.md somewhere else entirely.
    """
    data = json.loads(Path(sessions_file).read_text(encoding="utf-8"))
    return {s["project"]: os.path.expanduser(s["cwd"]) for s in data["sessions"]}


def overlap(sessions_file=DEFAULT_SESSIONS_FILE):
    """Audit sessions that are also anchors, worst case first: (project, session)."""
    anchors = anchor_sessions(sessions_file)
    return [(project, sid)
            for project, sids in sorted(AUDIT_SESSIONS.items())
            for sid in sids if sid in anchors]


def rows(sessions_file=DEFAULT_SESSIONS_FILE):
    """(run label, project, cwd, session id) for every audit session, in run order."""
    cwds = project_cwds(sessions_file)
    return [(label, project, cwds.get(project, ""), sid)
            for label, projects in RUNS
            for project in projects
            for sid in AUDIT_SESSIONS[project]]


def query_command(cwd, session):
    script = REPO_ROOT / "build_real_view.py"
    return (f"cd {cwd} && python3 {script} "
            f"--query {session} blocks --all --no-all-sessions")


def footer_lines():
    """The scorecard's external-audit footer.

    The numbers above it are self-graded: same author, same corpus, same
    thresholds. What they are worth is whatever survives an audit of sessions
    nobody calibrated against, so the footer names that audit's date, its
    result and every session it covered - and says plainly when there is none.
    """
    out = ["## External re-audit", ""]
    if not LAST_AUDIT:
        return out + [
            "None recorded. The numbers above are the author's own measurement of "
            "the author's own corpus; nothing here has been checked against "
            "sessions outside it.", ""]
    sessions = ", ".join(f"{project} `{sid}`"
                         for project in sorted(AUDIT_SESSIONS)
                         for sid in AUDIT_SESSIONS[project])
    note = [LAST_AUDIT["note"], ""] if LAST_AUDIT.get("note") else []
    outcome = ("passed" if LAST_AUDIT.get("passed") else
               "**did not pass**: the gate is zero of each")
    total = sum(len(v) for v in AUDIT_SESSIONS.values())
    audited = LAST_AUDIT.get("audited", total)
    scope = (f"the {total} non-anchor sessions below" if audited == total else
             f"{audited} of the {total} non-anchor sessions below")
    provided = LAST_AUDIT.get("provided") or []
    except_ = (" (except " + ", ".join(f"`{x}`" for x in provided) + ")"
               if provided else "")
    return out + [
        f"{LAST_AUDIT['date']}: {LAST_AUDIT['runs']} independent `verdict-auditor` "
        f"runs over {scope} - none of them in `sessions.json`, so none of them "
        f"calibrated against - reported "
        f"**{LAST_AUDIT['falseGreens']} false greens and "
        f"{LAST_AUDIT['falseReds']} false reds** between them, and so "
        f"{outcome}. {LAST_AUDIT['redSide']} Each run was withheld "
        + ", ".join(f"`{w}`" for w in WITHHELD) + except_ + ", and derived its ground truth "
        "from the raw transcripts. Re-run the list with "
        "`python3 snapshots/audit_sessions.py`.", ""] + note + [sessions, ""]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="fail if any audit session is also an anchor")
    ap.add_argument("--sessions-file", default=str(DEFAULT_SESSIONS_FILE))
    args = ap.parse_args(argv)

    clashes = overlap(args.sessions_file)
    if args.check:
        if clashes:
            for project, sid in clashes:
                print(f"ERROR: {project} {sid} is an anchor in "
                      f"{args.sessions_file} and cannot be an audit session")
            return 1
        total = sum(len(v) for v in AUDIT_SESSIONS.values())
        print(f"OK: {total} audit sessions, none of them an anchor")
        return 0

    if clashes:
        print("WARNING: some audit sessions are anchors; run --check\n")
    cwds = project_cwds(args.sessions_file)
    for label, projects in RUNS:
        print(f"## {label}")
        for project in projects:
            cwd = cwds.get(project, "<unknown cwd>")
            for sid in AUDIT_SESSIONS[project]:
                print(f"  {project} {sid}")
                print(f"    {query_command(cwd, sid)}")
        print()
    print("Withheld from every auditor run: " + ", ".join(WITHHELD))
    return 0


if __name__ == "__main__":
    sys.exit(main())
