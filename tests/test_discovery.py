"""Tests for Phase 3: user-message counting, cwd encoding, transcript discovery."""
import json

import build_real_view as brv

from tests.test_turns import (_ts, _write_jsonl, _Args, assistant_text,
                              assistant_tool_use, user_meta, user_text,
                              user_tool_result)


# ---------- user-message counting ----------

def _session_with_tool_results():
    """2 real prompts, 10 tool-result user messages, 1 meta event."""
    events = [user_text("first real prompt", 0)]
    for i in range(5):
        events.append(assistant_tool_use("Read", {"file_path": f"/a/{i}.py"}, 1 + i, tool_id=f"t{i}"))
        events.append(user_tool_result(f"t{i}", "file body", 10 + i))
    events.append(user_text("second real prompt", 20))
    for i in range(5, 10):
        events.append(assistant_tool_use("Read", {"file_path": f"/a/{i}.py"}, 21 + i, tool_id=f"t{i}"))
        events.append(user_tool_result(f"t{i}", "file body", 40 + i))
    events.append(user_meta("meta note", 60))
    events.append(assistant_text("done", 61))
    return events


def test_summary_user_messages_counts_only_real_prompts(tmp_path):
    p = _write_jsonl(tmp_path, _session_with_tool_results())
    summary = brv.summarize_transcript(p)
    assert summary["userMessages"] == 2


def test_counts_user_messages_counts_only_real_prompts(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path, _session_with_tool_results())
    monkeypatch.chdir(tmp_path)
    _summary, per_session = brv.process_session(p, _Args())
    assert per_session["counts"]["userMessages"] == 2


# ---------- cwd encoding ----------

def test_encode_cwd_replaces_slashes():
    assert brv.encode_cwd_for_projects("/Users/x/y") == "-Users-x-y"


def test_encode_cwd_replaces_dots():
    assert brv.encode_cwd_for_projects("/Users/x/my.app") == "-Users-x-my-app"


def test_encode_cwd_matches_observed_worktree_convention():
    assert (brv.encode_cwd_for_projects("/Users/x/famigo/.claude/worktrees")
            == "-Users-x-famigo--claude-worktrees")


# ---------- discovery ----------

def _write_events(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def test_discovery_finds_top_level_transcripts(tmp_path):
    projects = tmp_path / "projects"
    encoded = brv.encode_cwd_for_projects("/w/proj")
    _write_events(projects / encoded / "a.jsonl", [user_text("hi", 0)])
    _write_events(projects / encoded / "b.jsonl", [user_text("hi", 0)])
    found = brv.discover_all_transcripts("/w/proj", projects)
    assert {p.name for p in found} == {"a.jsonl", "b.jsonl"}


def test_discovery_ignores_subdirectories(tmp_path):
    projects = tmp_path / "projects"
    encoded = brv.encode_cwd_for_projects("/w/proj")
    _write_events(projects / encoded / "a.jsonl", [user_text("hi", 0)])
    _write_events(projects / encoded / "subagents" / "sub.jsonl", [user_text("hi", 0)])
    found = brv.discover_all_transcripts("/w/proj", projects)
    assert [p.name for p in found] == ["a.jsonl"]


def test_discovery_survives_first_line_without_sidechain_flag(tmp_path):
    projects = tmp_path / "projects"
    encoded = brv.encode_cwd_for_projects("/w/proj")
    _write_events(projects / encoded / "a.jsonl",
                  [{"type": "file-history-snapshot", "timestamp": _ts(0)},
                   user_text("hi", 1)])
    found = brv.discover_all_transcripts("/w/proj", projects)
    assert [p.name for p in found] == ["a.jsonl"]


def test_discovery_handles_dotted_project_path(tmp_path):
    projects = tmp_path / "projects"
    encoded = brv.encode_cwd_for_projects("/w/my.app")
    _write_events(projects / encoded / "a.jsonl", [user_text("hi", 0)])
    assert [p.name for p in brv.discover_all_transcripts("/w/my.app", projects)] == ["a.jsonl"]
