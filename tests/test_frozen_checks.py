"""The reviewed checks files the corpus freezes, and the red path they exercise.

Until Phase 8 no anchor session carried a compiled checks file and no ground
truth row was `violated`, so "false reds 0" recorded that the tool had stopped
accusing rather than that it accuses correctly. These tests hold the other end:
the committed record really fires on the frozen session it was written for, and
really stands down on a session that never did the thing.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "snapshots"))

import rule_checks as rc  # noqa: E402

FAMIGO_CHECKS = (REPO / "snapshots" / "checks" / "famigo" / "5448a718"
                 / "home" / "Git" / "famigo" / "CLAUDE.md.checks.json")
BASELINE = REPO / "snapshots" / "baseline" / "famigo" / "5448a718"


def _loaded():
    return rc.load_checks(json.loads(FAMIGO_CHECKS.read_text(encoding="utf-8")))


def _check(loaded, check_id):
    return next(c for c in loaded["checks"] if c["id"] == check_id)


def test_the_famigo_record_loads_with_its_fixtures_reproduced():
    """A record whose fixtures fail here is demoted, and would decide nothing."""
    loaded = _loaded()
    assert [c["id"] for c in loaded["checks"]] == ["commit-subject-one-short-line",
                                                   "quality-gate-before-push"]
    assert loaded["rejected"] == [] and loaded["demoted"] == []
    assert _check(loaded, "commit-subject-one-short-line")["kind"] == "tool_arg_matches"


def _frozen_corpus():
    """The tool log of the frozen famigo 5448a718 session."""
    import take_baseline as tb
    import build_real_view as brv
    manifest = tb._read_manifest(BASELINE)
    root = tb.DEFAULT_RESTORE_ROOT / manifest["project"] / manifest["sessionId"][:8]
    tb.restore_inputs(BASELINE, root)
    transcript = tb._restored_path(manifest["transcriptKey"], root)
    return rc.build_corpus(brv.tool_calls(brv.load_transcript(transcript)))


@pytest.mark.skipif(not BASELINE.is_dir(),
                    reason="snapshots/baseline is the author's private corpus and is "
                           "gitignored, so the frozen famigo session is absent here")
def test_the_commit_rule_is_violated_three_times_on_the_frozen_famigo_session():
    """The corpus's first `violated` truth, with its three citable spans.

    The subjects are 76, 76 and 77 characters against a 72-character limit, and
    each carries a paragraph body the same rule forbids.
    """
    findings = rc.evaluate_checks(_loaded()["checks"], _frozen_corpus())
    violations = [f for f in findings
                  if f["checkId"] == "commit-subject-one-short-line"
                  and f["state"] == "violated"]
    assert len(violations) == 3
    for f in violations:
        assert f["path"] == rc.TOOLS_PATH
        assert f["line"] and f["match"].startswith("Bash git commit")
        assert f["confidence"] == "high"
    assert [f["line"] for f in violations] == sorted(f["line"] for f in violations)


@pytest.mark.skipif(not BASELINE.is_dir(),
                    reason="snapshots/baseline is the author's private corpus and is "
                           "gitignored, so the frozen famigo session is absent here")
def test_the_quality_gate_rule_is_satisfied_on_the_same_session():
    """The second record's job is to prove the first one is not accusing blindly.

    Both read the same tool log; one condemns and one clears, so a matcher that
    simply fired on everything would fail here.
    """
    findings = rc.evaluate_checks(_loaded()["checks"], _frozen_corpus())
    gate = [f for f in findings if f["checkId"] == "quality-gate-before-push"]
    assert [f["state"] for f in gate] == ["clear"]
    assert gate[0]["stage"] == rc.STAGE_SATISFIED


def _tool_log(lines):
    return {"code": [], "final_code": [], "commands": [], "paths": [],
            "tools": rc._selftest_tools("\n".join(lines))}


def test_the_commit_rule_is_not_exercised_on_a_session_with_no_commits():
    """No commit is not a clean commit: the antecedent never fired."""
    check = _check(_loaded(), "commit-subject-one-short-line")
    findings = rc.evaluate_checks([check], _tool_log([
        "Bash yarn type-check", "Bash git status --short", "Read /repo/CLAUDE.md"]))
    assert [f["state"] for f in findings] == ["not-exercised"]
    assert findings[0]["stage"] == rc.STAGE_ANTECEDENT
    # Nothing to cite: pointing at the `git status` would put a citation under a
    # claim no call supports.
    assert (findings[0]["line"], findings[0]["match"]) == (0, "")


def test_the_commit_rule_reads_both_spellings_of_the_message_flag():
    """`-F-` and `-F -` are the same flag, and the corpus uses both.

    A pattern that knew only the first condemned a 67-character subject in
    famigo 9dd3cc8a for its spacing - a false red on the one mechanism allowed
    to produce one.
    """
    check = _check(_loaded(), "commit-subject-one-short-line")
    findings = rc.evaluate_checks([check], _tool_log([
        "Bash git commit -F - <<'EOF' Fix auth token refresh on 401 EOF"]))
    assert [f["state"] for f in findings] == ["clear"]


def test_the_commit_rule_fires_on_a_short_subject_with_a_paragraph_body():
    """The rule's other half: `no paragraphs`, not only the 72-character line."""
    check = _check(_loaded(), "commit-subject-one-short-line")
    findings = rc.evaluate_checks([check], _tool_log([
        "Bash git commit -F - <<'EOF' Fix the pagination cursor And then a paragraph "
        "of explanation that pushes the whole message well past seventy-two "
        "characters. EOF"]))
    assert [f["state"] for f in findings] == ["violated"]


def test_the_commit_rule_clears_a_session_whose_commits_are_short():
    """The positive control for the two tests above.

    Without it, `not-exercised` and `violated` could both be produced by a
    pattern that never matches a compliant commit at all.
    """
    check = _check(_loaded(), "commit-subject-one-short-line")
    findings = rc.evaluate_checks([check], _tool_log([
        "Bash git commit -m \"036: Favorites controller and routes — add CRUD endpoints\"",
        "Bash git commit -F- <<'EOF' Fix auth token refresh on 401 EOF"]))
    assert [f["state"] for f in findings] == ["clear"]
