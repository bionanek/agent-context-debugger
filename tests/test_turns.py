"""Tests for turn-aware session view primitives.

Phase 1: split_into_turns, turn_slice, end-to-end smoke that process_session
emits per-turn data while preserving aggregate parity for single-turn sessions.
"""
import json

import pytest

import build_real_view as brv


# ---------- event builders ----------

def _ts(i):
    """Fake monotonic ISO timestamp keyed off an integer."""
    return f"2026-01-01T00:00:{i:02d}.000Z"


def user_text(text, i):
    return {"type": "user", "timestamp": _ts(i),
            "message": {"content": text}}


def user_meta(text, i):
    return {"type": "user", "timestamp": _ts(i), "isMeta": True,
            "message": {"content": text}}


def user_caveat(i, text="<local-command-caveat>caveat body</local-command-caveat>"):
    return {"type": "user", "timestamp": _ts(i),
            "message": {"content": text}}


def user_slash(name, args, i):
    body = f"<command-name>{name}</command-name><command-args>{args}</command-args>"
    return {"type": "user", "timestamp": _ts(i),
            "message": {"content": body}}


def user_tool_result(tool_use_id, text, i):
    return {"type": "user", "timestamp": _ts(i),
            "message": {"content": [{"type": "tool_result",
                                     "tool_use_id": tool_use_id,
                                     "content": text}]}}


def assistant_text(text, i):
    return {"type": "assistant", "timestamp": _ts(i),
            "message": {"content": [{"type": "text", "text": text}]}}


def assistant_tool_use(name, input_, i, tool_id="t1"):
    return {"type": "assistant", "timestamp": _ts(i),
            "message": {"content": [{"type": "tool_use", "name": name,
                                     "id": tool_id, "input": input_}]}}


# ---------- split_into_turns ----------

def test_split_empty():
    assert brv.split_into_turns([]) == []


def test_split_single_user_prompt():
    events = [
        user_text("hello", 0),
        assistant_text("hi back", 1),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["index"] == 0
    assert turns[0]["startEventIdx"] == 0
    assert turns[0]["endEventIdx"] == 2  # exclusive, partitions full event list
    assert turns[0]["userPrompt"] == "hello"
    assert turns[0]["startTime"] == _ts(0)
    assert turns[0]["endTime"] == _ts(1)


def test_split_three_turns():
    events = [
        user_text("first question", 0),
        assistant_text("first answer", 1),
        user_text("second question", 2),
        assistant_text("second answer", 3),
        user_text("third question", 4),
        assistant_text("third answer", 5),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 3
    # Ranges partition the event list with no gaps and no overlap.
    assert turns[0]["startEventIdx"] == 0 and turns[0]["endEventIdx"] == 2
    assert turns[1]["startEventIdx"] == 2 and turns[1]["endEventIdx"] == 4
    assert turns[2]["startEventIdx"] == 4 and turns[2]["endEventIdx"] == 6
    assert [t["userPrompt"] for t in turns] == [
        "first question", "second question", "third question"]


def test_split_tool_result_does_not_start_turn():
    """A user-typed tool_result message should not increment turn count."""
    events = [
        user_text("ask", 0),
        assistant_tool_use("Read", {"file_path": "/tmp/x"}, 1),
        user_tool_result("t1", "file contents", 2),
        assistant_text("answer", 3),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["startEventIdx"] == 0
    assert turns[0]["endEventIdx"] == 4


def test_split_meta_does_not_start_turn():
    events = [
        user_meta("system meta", 0),
        user_text("real prompt", 1),
        assistant_text("answer", 2),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["userPrompt"] == "real prompt"
    # Leading meta event is absorbed into turn 0 so ranges partition the event list.
    assert turns[0]["startEventIdx"] == 0
    assert turns[0]["endEventIdx"] == 3


def test_split_caveat_does_not_start_turn():
    events = [
        user_text("ask", 0),
        assistant_text("answer", 1),
        user_caveat(2),
        assistant_text("more", 3),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1


def test_split_slash_command_starts_turn():
    events = [
        user_text("warmup", 0),
        assistant_text("ack", 1),
        user_slash("graphify", "@some.md", 2),
        assistant_text("running", 3),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 2
    assert turns[1]["startEventIdx"] == 2
    # userPrompt for a slash-command turn includes the command name + args.
    assert "graphify" in turns[1]["userPrompt"]


def test_split_clear_then_real_prompt_is_a_turn_boundary():
    """Per PRD: /clear is a turn boundary, not a session split. The next real
    user prompt after /clear starts a new turn."""
    events = [
        user_text("first ask", 0),
        assistant_text("first answer", 1),
        user_slash("clear", "", 2),  # /clear shows up as a slash-command turn
        user_text("post-clear ask", 3),
        assistant_text("post-clear answer", 4),
    ]
    turns = brv.split_into_turns(events)
    # 3 turns: original ask, /clear itself, post-clear ask.
    assert len(turns) == 3


def test_split_ignores_non_user_non_assistant_events():
    events = [
        {"type": "summary", "timestamp": _ts(0)},
        user_text("ask", 1),
        assistant_text("answer", 2),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    # Range still partitions the full list — first (non-user) event absorbed into turn 0.
    assert turns[0]["startEventIdx"] == 0
    assert turns[0]["endEventIdx"] == 3


# ---------- turn_slice ----------

def test_turn_slice_filters_calls_and_segments():
    events = [
        user_text("q1", 0),
        assistant_tool_use("Read", {"file_path": "/a"}, 1),
        user_tool_result("t1", "a-content", 2),
        assistant_text("answer1", 3),
        user_text("q2", 4),
        assistant_tool_use("Read", {"file_path": "/b"}, 5),
        user_tool_result("t2", "b-content", 6),
        assistant_text("answer2", 7),
    ]
    calls = brv.tool_calls(events)
    asst_segs = brv.assistant_text_segments(events)
    turns = brv.split_into_turns(events)
    assert len(turns) == 2

    # Turn 0: events [0, 4) → 1 call (Read /a), 1 asst text ("answer1")
    e0, c0, s0 = brv.turn_slice(events, calls, asst_segs, turns[0])
    assert len(e0) == 4
    assert len(c0) == 1 and c0[0]["input"]["file_path"] == "/a"
    assert len(s0) == 1 and s0[0]["text"] == "answer1"

    # Turn 1: events [4, 8) → 1 call (Read /b), 1 asst text ("answer2")
    e1, c1, s1 = brv.turn_slice(events, calls, asst_segs, turns[1])
    assert len(e1) == 4
    assert len(c1) == 1 and c1[0]["input"]["file_path"] == "/b"
    assert len(s1) == 1 and s1[0]["text"] == "answer2"


def test_turn_slice_boundary_inclusivity():
    """endEventIdx is exclusive: the event at endEventIdx must NOT appear in
    the slice; the event at startEventIdx MUST appear."""
    events = [
        user_text("q1", 0),
        assistant_text("a1", 1),
        user_text("q2", 2),
        assistant_text("a2", 3),
    ]
    calls = brv.tool_calls(events)
    asst_segs = brv.assistant_text_segments(events)
    turns = brv.split_into_turns(events)
    e0, _, s0 = brv.turn_slice(events, calls, asst_segs, turns[0])
    # First event included, third event (the next user prompt) excluded.
    assert e0[0] is events[0]
    assert events[2] not in e0
    assert s0[0]["text"] == "a1"


# ---------- end-to-end smoke ----------

def _write_jsonl(tmp_path, events, name="t.jsonl"):
    p = tmp_path / name
    with p.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return p


class _Args:
    """Minimal args stub matching what process_session/load_context_files read."""
    claude_md = None
    skills_dir = None
    no_global = True
    no_skills = True
    no_project = True


def test_process_session_emits_turns_and_count(tmp_path, monkeypatch):
    events = [
        user_text("q1", 0),
        assistant_tool_use("Read", {"file_path": "/tmp/a"}, 1),
        user_tool_result("t1", "ac", 2),
        assistant_text("a1", 3),
        user_text("q2", 4),
        assistant_tool_use("Read", {"file_path": "/tmp/b"}, 5),
        user_tool_result("t2", "bc", 6),
        assistant_text("a2", 7),
        user_text("q3", 8),
        assistant_text("a3", 9),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())

    assert per_session["turnCount"] == 3
    assert "turns" in per_session
    assert len(per_session["turns"]) == 3

    # Per-turn shape mirrors today's per-session payload.
    t0 = per_session["turns"][0]
    for key in ("id", "index", "userPrompt", "promptPreview",
                "startTime", "endTime", "durationSec",
                "counts", "contextFiles", "timeline", "fileActivity"):
        assert key in t0, f"missing {key} on turn payload"

    # Turn ids are unique.
    ids = [t["id"] for t in per_session["turns"]]
    assert len(set(ids)) == len(ids)

    # Per-turn tool-call counts sum to the aggregate.
    per_turn_total = sum(t["counts"]["totalToolCalls"] for t in per_session["turns"])
    assert per_turn_total == per_session["counts"]["totalToolCalls"]


def test_combine_verdicts_single_turn_passthrough():
    """Per PRD: a single-turn session must produce the same verdict at aggregate
    scope as it does at per-turn scope, by construction."""
    for s in ("used", "used-partial", "ignored", "unused", "dormant", "not-loaded"):
        assert brv.combine_verdicts([s]) == s


def test_combine_verdicts_any_used_wins():
    assert brv.combine_verdicts(["used", "unused", "dormant"]) == "used"
    assert brv.combine_verdicts(["unused", "used", "not-loaded"]) == "used"


def test_combine_verdicts_ignored_propagates():
    """If the rule was loaded and applied but ignored in any turn, the aggregate
    must surface that — silently downgrading to 'used' would hide a violation."""
    assert brv.combine_verdicts(["used", "ignored"]) == "ignored"
    assert brv.combine_verdicts(["ignored", "unused"]) == "ignored"


def test_combine_verdicts_all_not_used():
    assert brv.combine_verdicts(["unused", "unused"]) == "unused"
    assert brv.combine_verdicts(["dormant", "not-loaded"]) == "dormant"
    assert brv.combine_verdicts(["not-loaded", "not-loaded"]) == "not-loaded"


def test_combine_verdicts_partial():
    assert brv.combine_verdicts(["used-partial", "unused"]) == "used-partial"


def test_combine_verdicts_empty():
    assert brv.combine_verdicts([]) == "not-loaded"


def test_aggregate_block_statuses_combine_from_turns(tmp_path, monkeypatch):
    """End-to-end: aggregate block statuses are derived from per-turn statuses,
    so aggregate and per-turn views can never disagree by construction."""
    events = [
        user_text("first ask", 0),
        assistant_text("ack", 1),
        user_text("second ask", 2),
        assistant_text("answer", 3),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    if per_session["turnCount"] < 2:
        pytest.skip("requires multi-turn fixture")
    # For every aggregate block, its status must equal combine_verdicts of the
    # matching per-turn statuses.
    import re as _re
    per_turn_by_stem = {}
    for tp in per_session["turns"]:
        for f in tp["contextFiles"]:
            for b in f["blocks"]:
                stem = _re.sub(r"^turn\d+-", "", b["id"])
                per_turn_by_stem.setdefault(stem, []).append(b["status"])
    for f in per_session["contextFiles"]:
        for b in f["blocks"]:
            stems = per_turn_by_stem.get(b["id"], [])
            if not stems:
                continue
            assert b["status"] == brv.combine_verdicts(stems), (
                f"aggregate status {b['status']} disagrees with combined "
                f"per-turn statuses {stems} for block {b['id']}")


def test_duplicates_stay_session_scoped(tmp_path, monkeypatch):
    """Per PRD: duplicates remain session-scoped and are NOT split per turn.
    The schema must surface them at session level so the UI's session-scope
    label has something honest to point at."""
    events = [
        user_text("first ask", 0),
        assistant_text("first answer", 1),
        user_text("second ask", 2),
        assistant_text("second answer", 3),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    # Duplicates is a top-level (session-scoped) key.
    assert "duplicates" in per_session
    # Per-turn payloads do NOT carry their own duplicates field — duplicates
    # are deliberately not turn-scoped per PRD #12.
    for tp in per_session["turns"]:
        assert "duplicates" not in tp


def test_process_session_single_turn_backcompat(tmp_path, monkeypatch):
    events = [
        user_text("just one ask", 0),
        assistant_tool_use("Read", {"file_path": "/tmp/x"}, 1),
        user_tool_result("t1", "xc", 2),
        assistant_text("answer", 3),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    assert per_session["turnCount"] == 1
    # Aggregate top-level keys still present.
    for key in ("counts", "contextFiles", "timeline", "fileActivity", "duplicates"):
        assert key in per_session


def task_notification(tool_use_id, i, **fields):
    """A completed-agent report, which the harness writes on the user channel.

    `fields` fill the optional tags (task_id, status, summary, result,
    subagent_tokens, tool_uses, duration_ms); omitted ones are left out so
    tests can exercise the missing-tag path. Pass tool_use_id=None for the
    real shape that carries no tool-use id at all.
    """
    tags = []
    if fields.get("task_id"):
        tags.append(f"<task-id>{fields['task_id']}</task-id>")
    if tool_use_id is not None:
        tags.append(f"<tool-use-id>{tool_use_id}</tool-use-id>")
    for tag, key in (("status", "status"), ("summary", "summary"), ("result", "result")):
        if key in fields:
            tags.append(f"<{tag}>{fields[key]}</{tag}>")
    usage = "".join(
        f"<{tag}>{fields[key]}</{tag}>"
        for tag, key in (("subagent_tokens", "subagent_tokens"),
                         ("tool_uses", "tool_uses"),
                         ("duration_ms", "duration_ms"))
        if key in fields)
    if usage:
        tags.append(f"<usage>{usage}</usage>")
    body = "<task-notification>\n" + "\n".join(tags) + "\n</task-notification>"
    return {"type": "user", "timestamp": _ts(i), "message": {"content": body}}
