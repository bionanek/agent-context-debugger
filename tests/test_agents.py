"""Tests for subagent runs: notification classification, spawn/return pairing,
lane assignment and the ordered row sequence the turns list walks.

A task-notification is the result half of an Agent tool call, delivered on the
user channel. Treating it as a prompt carved off phantom turns and stole the
tool calls that followed from the turn that earned them, so the classifier
tests here guard a bug fix, not a feature.
"""
import build_real_view as brv

from tests.test_turns import (
    _Args,
    _ts,
    _write_jsonl,
    assistant_text,
    assistant_tool_use,
    task_notification,
    user_text,
    user_tool_result,
)


def spawn(i, tool_id, description="audit", prompt="go look", name="Agent",
          subagent_type=None):
    input_ = {"description": description, "prompt": prompt}
    if subagent_type:
        input_["subagent_type"] = subagent_type
    return assistant_tool_use(name, input_, i, tool_id=tool_id)


def _runs(events):
    return brv.agent_runs(events, brv.split_into_turns(events))


def _row_agent_ids(rows):
    out = []
    for r in rows:
        if "ref" in r and r["kind"] != "turn":
            out.append(r["ref"])
        out.extend(r.get("refs", []))
    return out


# ---------- the classifier ----------

def test_notification_does_not_start_a_turn():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2, status="completed", result="done"),
        assistant_text("ok", 3),
        user_text("q2", 4),
        spawn(5, "a2"),
        task_notification("a2", 6, status="completed", result="done"),
        task_notification("a3", 7, status="completed", result="done"),
        assistant_text("ok", 8),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 2
    assert [t["userPrompt"] for t in turns] == ["q1", "q2"]


def test_tool_calls_after_a_notification_stay_in_the_enclosing_turn():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2, result="done"),
        assistant_tool_use("Read", {"file_path": "/tmp/x"}, 3, tool_id="r1"),
        user_tool_result("r1", "contents", 4),
        assistant_text("ok", 5),
    ]
    turns = brv.split_into_turns(events)
    assert len(turns) == 1
    assert turns[0]["startEventIdx"] == 0
    assert turns[0]["endEventIdx"] == len(events)


def test_list_shaped_notification_classifies_like_a_string_one():
    string_form = task_notification("a1", 1, result="done")
    body = string_form["message"]["content"]
    list_form = {"type": "user", "timestamp": _ts(1),
                 "message": {"content": [{"type": "text", "text": body}]}}
    assert brv._real_user_prompt_text(string_form) is None
    assert brv._real_user_prompt_text(list_form) is None


def test_a_prompt_quoting_the_tag_is_still_a_prompt():
    """Anchored at the start, so talking about notifications is not one."""
    e = user_text("why does <task-notification> steal my turns?", 0)
    assert brv._real_user_prompt_text(e) is not None


# ---------- pairing ----------

def test_agent_pairs_spawn_to_return_by_tool_use_id():
    events = [
        user_text("q1", 0),
        spawn(1, "a1", description="Visual audit", prompt="check the diff",
              subagent_type="explorer"),
        task_notification("a1", 2, task_id="t-1", status="completed",
                          summary='Agent "Visual audit" finished',
                          result="all clear", subagent_tokens=67439,
                          tool_uses=16, duration_ms=86634),
        assistant_text("ok", 3),
    ]
    out = _runs(events)
    assert len(out["agents"]) == 1
    a = out["agents"][0]
    assert a["id"] == "a1"
    assert a["type"] == "Agent"
    assert a["subagentType"] == "explorer"
    assert a["name"] == "Visual audit"
    assert a["prompt"] == "check the diff"
    assert a["promptPreview"]
    assert a["spawnTurnIndex"] == 0
    assert a["status"] == "returned"
    assert a["durationMs"] == 86634
    assert a["tokens"] == 67439
    assert a["toolUses"] == 16
    assert a["resultText"] == "all clear"
    assert out["unmatchedNotifications"] == 0


def test_missing_tags_are_unknown_never_an_exception():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2),
        assistant_text("ok", 3),
    ]
    a = _runs(events)["agents"][0]
    assert a["status"] == "returned"
    assert a["durationMs"] is None
    assert a["tokens"] is None
    assert a["toolUses"] is None
    assert a["resultText"] == ""


def test_two_notifications_for_one_spawn_are_one_agent():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2, task_id="t-1", result="first pass"),
        assistant_text("ok", 3),
        task_notification("a1", 4, task_id="t-1", result="second pass"),
        assistant_text("ok again", 5),
    ]
    out = _runs(events)
    assert len(out["agents"]) == 1
    a = out["agents"][0]
    assert len(a["returns"]) == 2
    assert [r["resultText"] for r in a["returns"]] == ["first pass", "second pass"]
    assert a["resultText"] == "second pass"
    assert len([r for r in out["turnRows"] if r["kind"] == "return"]) == 2


def test_notification_that_names_no_agent_is_not_assumed_to_be_one():
    """Narrowed deliberately. Counting every untieable notification warned on
    Monitor events, loop wake-ups and artifact housekeeping, which are not
    agents and never were. Only an agent-shaped summary that ties to no spawn
    is worth reporting - see
    test_agent_shaped_summary_with_no_matching_spawn_is_unmatched.
    """
    events = [
        user_text("q1", 0),
        task_notification(None, 1, task_id="t-9", result="orphan"),
        assistant_text("ok", 2),
    ]
    out = _runs(events)
    assert out["agents"] == []
    assert out["unmatchedNotifications"] == 0


def test_notification_for_a_background_bash_is_not_an_agent():
    """Background shell commands report through the same channel. They name a
    tool call that exists and is not a spawn, so they are neither an agent nor
    an unmatched notification."""
    events = [
        user_text("q1", 0),
        assistant_tool_use("Bash", {"command": "sleep 1"}, 1, tool_id="b1"),
        task_notification("b1", 2, result="done"),
        assistant_text("ok", 3),
    ]
    out = _runs(events)
    assert out["agents"] == []
    assert out["unmatchedNotifications"] == 0


def test_workflow_call_produces_an_agent():
    events = [
        user_text("q1", 0),
        spawn(1, "w1", name="Workflow", description="run phases"),
        task_notification("w1", 2, result="done"),
        assistant_text("ok", 3),
    ]
    out = _runs(events)
    assert [a["type"] for a in out["agents"]] == ["Workflow"]


def test_spawn_with_no_notification_is_open_and_dangles():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        assistant_text("ok", 2),
    ]
    out = _runs(events)
    assert out["agents"][0]["status"] == "open"
    assert out["agents"][0]["returns"] == []
    assert out["turnRows"][-1] == {"kind": "dangling", "ref": "a1"}


# ---------- lanes ----------

def test_overlapping_agents_take_distinct_lanes_and_a_freed_lane_is_reused():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        spawn(2, "a2"),
        task_notification("a1", 3, result="one"),
        spawn(4, "a3"),
        task_notification("a2", 5, result="two"),
        task_notification("a3", 6, result="three"),
        assistant_text("ok", 7),
    ]
    lanes = {a["id"]: a["lane"] for a in _runs(events)["agents"]}
    assert lanes["a1"] == 0
    assert lanes["a2"] == 1
    assert lanes["a3"] == 0


def test_colour_index_follows_spawn_order():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        spawn(2, "a2"),
        task_notification("a1", 3, result="one"),
        task_notification("a2", 4, result="two"),
        assistant_text("ok", 5),
    ]
    out = _runs(events)
    assert [a["colorIndex"] for a in out["agents"]] == [0, 1]


# ---------- row order and grouping ----------

def test_turn_rows_are_ordered_and_only_name_known_agents():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2, result="one"),
        assistant_text("ok", 3),
        user_text("q2", 4),
        spawn(5, "a2"),
        assistant_text("ok", 6),
    ]
    out = _runs(events)
    known = {a["id"] for a in out["agents"]}
    assert set(_row_agent_ids(out["turnRows"])) <= known
    assert [r["kind"] for r in out["turnRows"]] == [
        "turn", "spawn", "return", "turn", "spawn", "dangling"]
    assert [r["ref"] for r in out["turnRows"] if r["kind"] == "turn"] == [
        "turn-0", "turn-1"]


def test_a_batch_that_all_returns_before_the_next_turn_collapses():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        spawn(2, "a2"),
        spawn(3, "a3"),
        task_notification("a1", 4, result="one"),
        task_notification("a2", 5, result="two"),
        task_notification("a3", 6, result="three"),
        assistant_text("ok", 7),
        user_text("q2", 8),
        assistant_text("ok", 9),
    ]
    rows = _runs(events)["turnRows"]
    assert [r["kind"] for r in rows] == [
        "turn", "spawn-group", "return-group", "turn"]
    assert rows[1]["refs"] == ["a1", "a2", "a3"]
    assert rows[2]["refs"] == ["a1", "a2", "a3"]


def test_a_batch_straddling_a_turn_does_not_collapse():
    """The straggler is the thing worth seeing, so the rule keys on 'everyone
    returned before the next turn row', never on 'spawned together'."""
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        spawn(2, "a2"),
        spawn(3, "a3"),
        task_notification("a1", 4, result="one"),
        assistant_text("ok", 5),
        user_text("q2", 6),
        task_notification("a2", 7, result="two"),
        task_notification("a3", 8, result="three"),
        assistant_text("ok", 9),
    ]
    rows = _runs(events)["turnRows"]
    assert [r["kind"] for r in rows] == [
        "turn", "spawn", "spawn", "spawn", "return", "turn", "return", "return"]


def test_a_batch_with_an_open_member_does_not_collapse():
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        spawn(2, "a2"),
        task_notification("a1", 3, result="one"),
        assistant_text("ok", 4),
    ]
    rows = _runs(events)["turnRows"]
    assert [r["kind"] for r in rows] == ["turn", "spawn", "spawn", "return", "dangling"]


# ---------- payload wiring ----------

def test_process_session_bakes_agents_and_rows(tmp_path, monkeypatch):
    events = [
        user_text("q1", 0),
        spawn(1, "a1", description="audit one"),
        spawn(2, "a2", description="audit two"),
        task_notification("a1", 3, result="one", duration_ms=1000),
        task_notification("a2", 4, result="two", duration_ms=2000),
        assistant_text("ok", 5),
        user_text("q2", 6),
        spawn(7, "a3", description="audit three"),
        assistant_text("ok", 8),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())

    assert per_session["turnCount"] == 2
    assert summary["agentCount"] == 3
    assert [a["id"] for a in per_session["agents"]] == ["a1", "a2", "a3"]
    assert per_session["turnRows"][0] == {"kind": "turn", "ref": "turn-0"}
    assert per_session["turns"][0]["agentIds"] == ["a1", "a2"]
    assert per_session["turns"][1]["agentIds"] == ["a3"]


def test_session_without_agents_reports_none(tmp_path, monkeypatch):
    events = [user_text("q1", 0), assistant_text("ok", 1)]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    assert summary["agentCount"] == 0
    assert per_session["agents"] == []
    assert per_session["turnRows"] == [{"kind": "turn", "ref": "turn-0"}]
    assert per_session["turns"][0]["agentIds"] == []


def test_leading_whitespace_notification_is_classified_the_same_both_ways():
    """The turn classifier and the agent parser must agree: one accepting what
    the other rejects would carve a phantom turn around a real agent return."""
    e = task_notification("a1", 1, result="done")
    e["message"]["content"] = "\n  " + e["message"]["content"]
    assert brv._real_user_prompt_text(e) is None
    assert brv._task_notification_text(e) is not None


def test_subagent_transcript_path_is_baked(tmp_path, monkeypatch):
    events = [
        user_text("q1", 0),
        spawn(1, "a1"),
        task_notification("a1", 2, task_id="t1", result="one"),
        spawn(3, "a2"),
        assistant_text("ok", 4),
    ]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    _, per_session = brv.process_session(p, _Args())

    agents = {a["id"]: a for a in per_session["agents"]}
    expected = str(p.with_suffix("")) + "/subagents/agent-t1.jsonl"
    assert agents["a1"]["returns"][0]["transcriptPath"] == expected
    # Nothing came back for a2, so there is no task id and no file to name.
    assert agents["a2"]["returns"] == []


def test_return_without_task_id_names_no_transcript(tmp_path, monkeypatch):
    events = [user_text("q1", 0), spawn(1, "a1"), task_notification("a1", 2, result="one")]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    _, per_session = brv.process_session(p, _Args())
    assert per_session["agents"][0]["returns"][0]["transcriptPath"] == ""


# ---------- notifications that are not agent results ----------
#
# The `<task-type>` tag is not a discriminator worth filtering on: the shipped
# CLI describes its own label set as falling back "to the raw discriminant for
# unknown types", and only 2 of 365 real notifications carry the tag at all.
# So a notification is classified by shape - does it tie to a spawn, or does it
# name one - and everything else is simply not an agent's business.

def test_monitor_event_is_not_an_agent_and_not_unmatched():
    events = [
        user_text("q", 0),
        task_notification(None, 1, task_id="mon1",
                          summary='Monitor event: "develop CI + staging deploy"'),
        assistant_text("ok", 2),
    ]
    res = _runs(events)
    assert res["agents"] == []
    assert res["unmatchedNotifications"] == 0


def test_artifact_lifecycle_notification_is_not_unmatched():
    events = [
        user_text("q", 0),
        task_notification(None, 1,
                          summary='Stopped watching Artifact: "Context Audit" (connection lost)'),
        assistant_text("ok", 2),
    ]
    assert _runs(events)["unmatchedNotifications"] == 0


def test_background_shell_notification_is_not_unmatched():
    events = [
        user_text("q", 0),
        assistant_tool_use("Bash", {"command": "npm run dev"}, 1, tool_id="sh1"),
        task_notification("sh1", 2, summary="Background command finished"),
        assistant_text("ok", 3),
    ]
    res = _runs(events)
    assert res["agents"] == []
    assert res["unmatchedNotifications"] == 0


# ---------- pairing by name when no tool-use id was carried ----------

def test_agent_named_in_summary_pairs_without_a_tool_use_id():
    events = [
        user_text("q", 0),
        spawn(1, "a1", description="/code-review"),
        task_notification(None, 2, task_id="t1", status="completed",
                          summary='Agent "/code-review" finished',
                          result="found 2 issues"),
        assistant_text("ok", 3),
    ]
    res = _runs(events)
    assert res["unmatchedNotifications"] == 0
    (agent,) = res["agents"]
    assert agent["status"] == "returned"
    assert agent["resultText"] == "found 2 issues"


def test_stopped_background_agent_pairs_by_name():
    """The real shape that made a genuinely-reported agent look like it never
    replied: it reports that it was stopped, carrying no tool-use id."""
    events = [
        user_text("q", 0),
        spawn(1, "a1", description="Explore profile and settings structure"),
        task_notification(None, 2, task_id="t1", status="stopped",
                          summary=('No completion record was found for background '
                                   'agent "Explore profile and settings structure"')),
        assistant_text("ok", 3),
    ]
    (agent,) = _runs(events)["agents"]
    assert agent["status"] == "returned"
    assert agent["returns"][0]["status"] == "stopped"


def test_name_pairing_prefers_the_earliest_still_open_spawn():
    events = [
        user_text("q", 0),
        spawn(1, "a1", description="audit"),
        spawn(2, "a2", description="audit"),
        task_notification("a1", 3, status="completed", summary='Agent "audit" finished'),
        task_notification(None, 4, task_id="t2", status="completed",
                          summary='Agent "audit" finished', result="second"),
        assistant_text("ok", 5),
    ]
    by_id = {a["id"]: a for a in _runs(events)["agents"]}
    assert by_id["a1"]["resultText"] != "second"
    assert by_id["a2"]["resultText"] == "second"


def test_agent_shaped_summary_with_no_matching_spawn_is_unmatched():
    """Only a notification that looks like an agent's and ties to nothing is
    worth warning about. Staying silent here would hide a real pairing bug."""
    events = [
        user_text("q", 0),
        task_notification(None, 1, task_id="t1",
                          summary='Agent "never spawned here" finished'),
        assistant_text("ok", 2),
    ]
    res = _runs(events)
    assert res["agents"] == []
    assert res["unmatchedNotifications"] == 1


def test_tool_use_id_still_wins_over_the_name_fallback():
    events = [
        user_text("q", 0),
        spawn(1, "a1", description="same name"),
        spawn(2, "a2", description="same name"),
        task_notification("a2", 3, status="completed",
                          summary='Agent "same name" finished', result="for a2"),
        assistant_text("ok", 4),
    ]
    by_id = {a["id"]: a for a in _runs(events)["agents"]}
    assert by_id["a2"]["resultText"] == "for a2"
    assert by_id["a1"]["status"] == "open"
