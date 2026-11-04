"""The external audit's session list.

The scorecard is calibrated on the anchors in `snapshots/sessions.json`, so an
audit that reached for one of them would be grading the tool on the sessions
its own thresholds were fitted to. These tests hold the two facts that make the
list an external gate: it is disjoint from the anchors, and it is complete.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))

import audit_sessions as aud  # noqa: E402


def test_no_audit_session_is_an_anchor():
    assert aud.overlap() == []


def test_the_list_is_the_sixteen_sessions_the_plan_names():
    counts = {project: len(sids) for project, sids in aud.AUDIT_SESSIONS.items()}
    assert counts == {"famigo": 4, "formic-core": 4, "formicHMI": 2,
                      "reband": 4, "agent-context-ide": 2}
    assert sum(counts.values()) == 16
    flat = [sid for sids in aud.AUDIT_SESSIONS.values() for sid in sids]
    assert len(set(flat)) == 16


def test_every_run_together_covers_every_project_exactly_once():
    """A project in two runs would be audited twice; one in none, never."""
    listed = [p for _, projects in aud.RUNS for p in projects]
    assert sorted(listed) == sorted(aud.AUDIT_SESSIONS)
    assert len(listed) == len(set(listed))


def test_every_audit_session_gets_a_runnable_command():
    """A query command needs the session's own cwd, or it resolves another
    project's CLAUDE.md and the audit reads the wrong rules."""
    for label, project, cwd, sid in aud.rows():
        assert cwd, f"{project} has no cwd in sessions.json"
        cmd = aud.query_command(cwd, sid)
        assert cmd.startswith(f"cd {cwd} && ")
        assert f"--query {sid} blocks --all --no-all-sessions" in cmd


def test_the_disjointness_gate_can_fail(tmp_path, monkeypatch, capsys):
    """A gate that cannot fail measures nothing: put an anchor in the list."""
    anchors = json.loads((Path(aud.DEFAULT_SESSIONS_FILE)).read_text(encoding="utf-8"))
    anchor_id = anchors["sessions"][0]["session"]
    monkeypatch.setitem(aud.AUDIT_SESSIONS, "famigo",
                        aud.AUDIT_SESSIONS["famigo"] + [anchor_id])
    assert aud.main(["--check"]) == 1
    assert anchor_id in capsys.readouterr().out
    monkeypatch.undo()
    assert aud.main(["--check"]) == 0


def test_the_footer_says_so_when_no_external_audit_is_recorded(monkeypatch):
    """A missing audit has to read as a missing audit. Rendering nothing would
    leave the self-graded tables as the last word on the page."""
    monkeypatch.setattr(aud, "LAST_AUDIT", None)
    text = "\n".join(aud.footer_lines())
    assert "## External re-audit" in text and "None recorded" in text
    assert "false greens" not in text


def test_a_recorded_audit_names_its_date_result_and_every_session(monkeypatch):
    monkeypatch.setattr(aud, "LAST_AUDIT", {
        "date": "2026-01-02", "runs": 3, "passed": True,
        "falseGreens": 0, "falseReds": 0, "redSide": "what a red needed",
        "note": "a note the footer carries"})
    text = "\n".join(aud.footer_lines())
    assert "2026-01-02" in text and "a note the footer carries" in text
    assert "0 false greens and 0 false reds" in text
    assert "passed" in text and "did not pass" not in text
    for sids in aud.AUDIT_SESSIONS.values():
        for sid in sids:
            assert sid in text
    for withheld in aud.WITHHELD:
        assert withheld in text


def test_a_failed_audit_says_so_rather_than_reading_as_no_audit(monkeypatch):
    """The one recording that flatters the tables is the one that omits a
    failure, so a non-passing audit has to render as a failure, not as None."""
    monkeypatch.setattr(aud, "LAST_AUDIT", {
        "date": "2026-01-02", "runs": 3, "passed": False,
        "falseGreens": 2, "falseReds": 0, "redSide": "what a red needed"})
    text = "\n".join(aud.footer_lines())
    assert "did not pass" in text and "None recorded" not in text
    assert "2 false greens and 0 false reds" in text


def test_the_false_red_count_never_stands_without_its_coverage():
    """A false-red count of zero over a corpus with no red path measures
    nothing, so the footer states what could have produced a red beside it."""
    text = "\n".join(aud.footer_lines())
    if aud.LAST_AUDIT is None:
        assert "false reds" not in text
        return
    assert "false reds" in text
    assert aud.LAST_AUDIT["redSide"] in text
    assert "compiled checks file" in text


def test_the_scorecard_carries_the_footer_the_recorded_audit_supports():
    """The scorecard is generated, so its footer and this record cannot drift -
    but a regenerated file could still predate the record, which is the one
    thing a reader has no way to see."""
    scorecard = Path(aud.REPO_ROOT) / "snapshots" / "SCORECARD.md"
    text = scorecard.read_text(encoding="utf-8")
    assert "## External re-audit" in text
    if aud.LAST_AUDIT:
        assert aud.LAST_AUDIT["date"] in text
        assert f"{aud.LAST_AUDIT['falseGreens']} false greens" in text
    else:
        assert "None recorded" in text


def test_the_withheld_list_names_every_answer_sheet():
    """An auditor that reads any of these is grading against the tool's own
    output rather than the transcript."""
    assert set(aud.WITHHELD) == {"snapshots/SCORECARD.md", "snapshots/expected/",
                                 "snapshots/after/", "snapshots/baseline/"}
