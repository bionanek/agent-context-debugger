"""Tests for the shared real-user-prompt classifier.

Phase 1 of plans/context-fidelity-v2.md: list-content prompts (pasted
screenshots), interrupt markers, local-command wrappers and stdout wrappers.
"""
import json

import build_real_view as brv

from tests.test_turns import (
    _ts,
    assistant_text,
    assistant_tool_use,
    user_meta,
    user_slash,
    user_text,
    user_tool_result,
)


# ---------- event builders specific to this area ----------

def user_list(items, i):
    return {"type": "user", "timestamp": _ts(i), "message": {"content": items}}


def user_image_prompt(text, i):
    return user_list([
        {"type": "image", "source": {"type": "base64",
                                     "media_type": "image/png", "data": "AAAA"}},
        {"type": "text", "text": text},
    ], i)


def user_stdout(text, i):
    body = f"<local-command-stdout>{text}</local-command-stdout>"
    return {"type": "user", "timestamp": _ts(i), "message": {"content": body}}


# ---------- list-content prompts ----------

def test_image_paste_prompt_starts_a_turn():
    events = [
        user_image_prompt("what is wrong with this screen?", 0),
        assistant_text("looks fine", 1),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["userPrompt"] == "what is wrong with this screen?"
    assert brv.first_real_user_prompt(events) == "what is wrong with this screen?"


def test_image_paste_prompt_shows_in_session_summary(tmp_path):
    path = tmp_path / "sess.jsonl"
    events = [
        dict(user_image_prompt("fix the header spacing", 0), sessionId="abc123"),
        assistant_text("on it", 1),
    ]
    path.write_text("\n".join(json.dumps(e) for e in events))
    summary = brv.summarize_transcript(path)
    assert summary["promptPreview"] == "fix the header spacing"


def test_text_only_list_prompt_starts_a_turn():
    events = [user_list([{"type": "text", "text": "run the suite"}], 0)]
    assert brv.first_real_user_prompt(events) == "run the suite"


def test_multiple_text_items_are_joined():
    events = [user_list([
        {"type": "text", "text": "first part"},
        {"type": "text", "text": "second part"},
    ], 0)]
    assert brv.first_real_user_prompt(events) == "first part\nsecond part"


def test_image_only_list_is_not_a_prompt():
    events = [user_list([{"type": "image", "source": {"data": "AAAA"}}], 0)]
    assert brv.first_real_user_prompt(events) is None


# ---------- interrupt markers ----------

def test_list_interrupt_marker_is_not_a_prompt():
    events = [
        user_text("do the thing", 0),
        user_list([{"type": "text", "text": "[Request interrupted by user]"}], 1),
        assistant_text("stopped", 2),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["userPrompt"] == "do the thing"


def test_string_interrupt_marker_is_not_a_prompt():
    events = [
        user_text("do the thing", 0),
        user_text("[Request interrupted by user for tool use]", 1),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1


def test_interrupt_marker_inside_a_longer_prompt_still_counts():
    events = [user_text("[Request interrupted by user] actually do this instead", 0)]
    assert brv.first_real_user_prompt(events) == (
        "[Request interrupted by user] actually do this instead")


# ---------- local-command vs skill wrappers ----------

def test_local_command_wrapper_does_not_start_a_turn():
    events = [
        user_text("real prompt", 0),
        assistant_text("answer", 1),
        user_slash("/model", "claude-opus-5", 2),
        user_stdout("Set model to claude-opus-5", 3),
        assistant_text("continuing", 4),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["userPrompt"] == "real prompt"


def test_skill_wrapper_still_starts_a_turn():
    events = [
        user_text("real prompt", 0),
        assistant_text("answer", 1),
        user_slash("/graphify", "how does auth work", 2),
        assistant_text("graphing", 3),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 2
    assert turns[1]["userPrompt"] == "/graphify how does auth work"


def test_stdout_wrapper_is_never_a_prompt():
    events = [
        user_stdout("Set model to claude-opus-5", 0),
        user_text("real prompt", 1),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["userPrompt"] == "real prompt"
    assert brv.first_real_user_prompt(events) == "real prompt"


def test_caveat_then_local_command_yields_no_turn():
    events = [
        user_text("real prompt", 0),
        user_meta("<local-command-caveat>Caveat: …</local-command-caveat>", 1),
        user_slash("/model", "claude-opus-5", 2),
        user_stdout("Set model to claude-opus-5", 3),
    ]
    assert len(brv.split_into_turns(events)) == 1


# ---------- consumers must agree with the classifier ----------

def test_timeline_shows_a_list_content_prompt():
    events = [
        user_image_prompt("why is this button misaligned?", 0),
        assistant_text("looking", 1),
    ]
    rows = brv.build_timeline(events)
    user_rows = [r for r in rows if r["kind"] == "user"]
    assert len(user_rows) == 1
    assert user_rows[0]["text"] == "why is this button misaligned?"
    # The prompt must precede the reply it caused.
    assert rows[0]["kind"] == "user"


def test_timeline_user_row_count_matches_turn_count():
    events = [
        user_image_prompt("first ask", 0),
        assistant_text("first answer", 1),
        user_text("second ask", 2),
        assistant_text("second answer", 3),
    ]
    rows = brv.build_timeline(events)
    prompt_rows = [r for r in rows if r["kind"] in ("user", "user-command")]
    assert len(prompt_rows) == len(brv.split_into_turns(events)) == 2


def test_timeline_tool_result_list_still_renders_as_tool_result():
    events = [
        user_text("ask", 0),
        assistant_tool_use("Read", {"file_path": "/a"}, 1),
        user_tool_result("t1", "file contents", 2),
    ]
    rows = brv.build_timeline(events)
    assert any(r["kind"] == "tool-result" for r in rows)
    assert sum(1 for r in rows if r["kind"] == "user") == 1


def test_timeline_detects_a_prefixed_command_wrapper():
    """Real wrappers lead with <command-message>, so the timeline must search
    for <command-name> rather than require the message to start with it."""
    body = ("<command-message>graphify</command-message>\n"
            "<command-name>/graphify</command-name>"
            "<command-args>how does auth work</command-args>")
    events = [{"type": "user", "timestamp": _ts(0), "message": {"content": body}}]
    rows = brv.build_timeline(events)
    assert len(rows) == 1
    assert rows[0]["kind"] == "user-command"
    assert rows[0]["label"] == "/graphify"
    assert rows[0]["text"] == "/graphify how does auth work"


def test_chronological_segments_include_a_list_content_prompt():
    events = [
        user_image_prompt("the pins render off-centre", 0),
        assistant_text("checking", 1),
    ]
    segs = brv.chronological_segments(events)
    user_text_segs = [s for s in segs
                      if s["role"] == "user" and s["kind"] == "text"]
    assert len(user_text_segs) == 1
    assert user_text_segs[0]["text"] == "the pins render off-centre"
    assert user_text_segs[0]["idx"] == 0


def test_chronological_segments_tool_result_unchanged():
    events = [
        user_text("ask", 0),
        assistant_tool_use("Read", {"file_path": "/a"}, 1),
        user_tool_result("t1", "file contents", 2),
    ]
    segs = brv.chronological_segments(events)
    kinds = [(s["role"], s["kind"]) for s in segs]
    assert ("user", "tool_result") in kinds
    assert sum(1 for r, k in kinds if r == "user" and k == "text") == 1


# ---------- regressions the classifier must not break ----------

def test_tool_result_list_is_still_not_a_prompt():
    events = [
        user_text("prompt", 0),
        user_tool_result("t1", "file contents", 1),
    ]
    assert len(brv.split_into_turns(events)) == 1


def test_empty_string_message_is_not_a_prompt():
    events = [
        {"type": "user", "timestamp": _ts(0), "message": {"content": "   "}},
        user_text("real prompt", 1),
    ]
    assert brv.first_real_user_prompt(events) == "real prompt"
