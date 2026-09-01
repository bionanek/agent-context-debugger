"""Tests for the per-file rollup baked onto every context-file record.

Phase 1 of the drill-down view: the `activity` counts, the active/quiet
classification, the status rollup and its summary line, plus the `headline`
string on every turn and session summary. Nothing in the UI reads these yet.
"""
import json
from pathlib import Path

import build_real_view as brv

from tests.test_turns import (_Args, _write_jsonl, assistant_text,
                              assistant_tool_use, user_text, user_tool_result)

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "rollup_payload_golden.json"


def _root(tmp_path):
    """Fixture root under pytest's tmp_path.

    Long and fixed on purpose: block ids end in the last 40 characters of the
    file's path slug, so a short root would leak pytest's per-test directory
    name into every id and make the golden payload unreproducible.
    """
    return tmp_path / "agent-context-ide-rollup-fixture-root"


def _run(tmp_path, monkeypatch, events, *, global_md=None, project_md=None):
    """Run process_session against a fixture home and project directory.

    HOME is redirected so the machine's real ~/.claude/CLAUDE.md cannot leak
    into the payload and so a fixture file genuinely renders as `~/...`, which
    is the display form the activity join has to survive.
    """
    home = _root(tmp_path) / "home"
    (home / ".claude").mkdir(parents=True)
    proj = _root(tmp_path) / "proj"
    proj.mkdir()
    if global_md is not None:
        (home / ".claude" / "CLAUDE.md").write_text(global_md)
    if project_md is not None:
        (proj / "CLAUDE.md").write_text(project_md)
    monkeypatch.setenv("HOME", str(home))
    p = _write_jsonl(proj, events)
    monkeypatch.chdir(proj)
    return brv.process_session(p, _Args())


def _file(files, needle):
    return next(f for f in files if needle in f["path"])


# ---------- activity counts ----------

def test_reads_are_counted_per_turn(tmp_path, monkeypatch):
    md = _root(tmp_path) / "proj" / "CLAUDE.md"
    events = [
        user_text("q1", 0),
        assistant_tool_use("Read", {"file_path": str(md)}, 1, tool_id="t1"),
        user_tool_result("t1", "body", 2),
        assistant_tool_use("Read", {"file_path": str(md)}, 3, tool_id="t2"),
        user_tool_result("t2", "body", 4),
        user_text("q2", 5),
        assistant_text("done", 6),
    ]
    _, per_session = _run(tmp_path, monkeypatch, events,
                          project_md="# One\nsome rule text\n")

    turns = per_session["turns"]
    assert len(turns) == 2
    assert _file(turns[0]["contextFiles"], "CLAUDE.md")["activity"]["reads"] == 2
    assert _file(turns[1]["contextFiles"], "CLAUDE.md")["activity"]["reads"] == 0


def test_activity_joins_a_tilde_path_to_an_absolute_tool_call(tmp_path, monkeypatch):
    """Regression: the counters are keyed by the raw absolute `file_path` while
    the record's path is the `~/...` display form. Joining on the display form
    alone reports every file as untouched, which looks plausible."""
    abs_md = _root(tmp_path) / "home" / ".claude" / "CLAUDE.md"
    events = [
        user_text("fix the rules", 0),
        assistant_tool_use("Edit", {"file_path": str(abs_md)}, 1, tool_id="t1"),
        user_tool_result("t1", "ok", 2),
        assistant_text("edited", 3),
    ]
    _, per_session = _run(tmp_path, monkeypatch, events,
                          global_md="# Talking\nbe direct and brief\n")

    f = _file(per_session["contextFiles"], ".claude/CLAUDE.md")
    assert f["path"].startswith("~"), "fixture must exercise the display form"
    assert f["activity"]["edits"] == 1
    assert f["rollup"]["active"] is True


# ---------- classification ----------

def _rec(statuses, *, loaded=True, reads=0, edits=0):
    return {
        "path": "~/.claude/CLAUDE.md",
        "loaded": loaded,
        "activity": {"reads": reads, "edits": edits},
        "blocks": [{"status": s} for s in statuses],
    }


def test_ignored_block_makes_a_file_active():
    rec = _rec(["ignored", "dormant"])
    brv._annotate_rollup(rec)
    assert rec["rollup"]["active"] is True


def test_all_cold_blocks_make_a_file_quiet():
    rec = _rec(["dormant", "unused"])
    brv._annotate_rollup(rec)
    assert rec["rollup"]["active"] is False


def test_edited_file_is_active_even_with_cold_blocks():
    rec = _rec(["dormant", "unused"], edits=1)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["active"] is True


def test_not_loaded_file_is_quiet():
    rec = _rec(["not-loaded", "not-loaded"], loaded=False)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["active"] is False


# ---------- summary phrasing ----------

def test_violation_phrasing_wins_over_everything_else():
    rec = _rec(["ignored", "used", "dormant"], reads=1, edits=2)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "2 rules fired, 1 violated"


def test_never_loaded_phrasing():
    rec = _rec(["not-loaded"], loaded=False)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "on disk, never entered context"


def test_edit_phrasing_beats_read_phrasing():
    rec = _rec(["used", "dormant"], reads=1, edits=2)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "edited 2 times; 1 of 2 sections matched the trace"


def test_read_phrasing():
    rec = _rec(["used", "dormant"], reads=1)
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "read this turn; 1 of 2 sections matched the trace"


def test_match_phrasing_without_any_file_activity():
    rec = _rec(["used-partial", "dormant"])
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "1 of 2 sections matched the trace"


def test_loaded_but_untouched_phrasing():
    rec = _rec(["dormant", "unused"])
    brv._annotate_rollup(rec)
    assert rec["rollup"]["summary"] == "in context, nothing referenced it"


# ---------- payload-wide invariants ----------

def _fixture_events(tmp_path):
    proj_md = _root(tmp_path) / "proj" / "CLAUDE.md"
    home_md = _root(tmp_path) / "home" / ".claude" / "CLAUDE.md"
    return [
        user_text("read the project rules", 0),
        assistant_tool_use("Read", {"file_path": str(proj_md)}, 1, tool_id="t1"),
        user_tool_result("t1", "body", 2),
        assistant_text("read them", 3),
        user_text("now tighten the global ones", 4),
        assistant_tool_use("Edit", {"file_path": str(home_md)}, 5, tool_id="t2"),
        user_tool_result("t2", "ok", 6),
        assistant_text("tightened", 7),
    ]


def _fixture_payload(tmp_path, monkeypatch):
    summary, per_session = _run(
        tmp_path, monkeypatch, _fixture_events(tmp_path),
        global_md="# Talking\nbe direct and brief\n\n# Commits\nnever sign commits\n",
        project_md="# Build\nrun the build before claiming done\n\n# Tests\nrun pytest\n")
    return brv.build_data(str(_root(tmp_path) / "proj"), [summary],
                          {summary["id"]: per_session}, summary["id"])


def test_status_counts_sum_to_the_block_count_everywhere(tmp_path, monkeypatch):
    data = _fixture_payload(tmp_path, monkeypatch)
    scopes = [data["perSession"][data["activeSessionId"]]]
    scopes += scopes[0]["turns"]
    assert len(scopes) > 1, "fixture must be multi-turn"
    for scope in scopes:
        for f in scope["contextFiles"]:
            counts = f["rollup"]["statusCounts"]
            assert sum(counts.values()) == len(f["blocks"])


def test_every_context_file_carries_the_id_its_blocks_are_namespaced_under(
        tmp_path, monkeypatch):
    """The CLI addresses a file by this id, so a block must name its own file."""
    data = _fixture_payload(tmp_path, monkeypatch)
    scopes = [data["perSession"][data["activeSessionId"]]]
    scopes += scopes[0]["turns"]
    for scope in scopes:
        ids = [f["id"] for f in scope["contextFiles"]]
        assert all(ids) and len(set(ids)) == len(ids)
        for f in scope["contextFiles"]:
            for b in f["blocks"]:
                assert b["id"].startswith(f["id"] + "-")


def test_headlines_are_present_at_turn_and_session_level(tmp_path, monkeypatch):
    data = _fixture_payload(tmp_path, monkeypatch)
    assert data["sessions"][0]["headline"] == "nothing violated"
    for t in data["perSession"][data["activeSessionId"]]["turns"]:
        assert t["headline"] == "nothing violated"


def test_violation_headline_counts_ignored_blocks():
    assert brv._violation_headline([]) == "nothing violated"
    files = [{"blocks": [{"status": "ignored"}, {"status": "used"}]},
             {"blocks": [{"status": "ignored"}]}]
    assert brv._violation_headline(files) == "2 rules violated"
    assert brv._violation_headline(files[1:]) == "1 rule violated"


# ---------- additive-payload guard ----------

def _assert_subset(golden, actual, path="data"):
    """Every key path in the pre-change payload must survive with its value."""
    if isinstance(golden, dict):
        assert isinstance(actual, dict), f"{path}: expected an object"
        for k, v in golden.items():
            assert k in actual, f"{path}.{k} disappeared from the payload"
            _assert_subset(v, actual[k], f"{path}.{k}")
    elif isinstance(golden, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        assert len(golden) == len(actual), f"{path}: length changed"
        for i, v in enumerate(golden):
            _assert_subset(v, actual[i], f"{path}[{i}]")
    else:
        assert golden == actual, f"{path}: value changed"


def _normalised(data, tmp_path):
    """Payload JSON with the fixture's temp paths masked, so the golden file is
    portable between machines and runs."""
    text = json.dumps(data, sort_keys=True)
    for p in {str(tmp_path), str(Path(tmp_path).resolve())}:
        text = text.replace(p, "<TMP>")
    return json.loads(text)


def test_payload_is_purely_additive(tmp_path, monkeypatch):
    golden = json.loads(GOLDEN.read_text())
    actual = _normalised(_fixture_payload(tmp_path, monkeypatch), tmp_path)
    _assert_subset(golden, actual)
