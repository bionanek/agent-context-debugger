"""Tests for the compaction fence.

A compaction is a turn boundary, and anything that was pulled in by a path glob
match is gone after it. Blocks in an evicted file must be judged only on the
turns where the model could still see them - and must never vanish entirely.
"""
import json

import pytest

import build_real_view as brv


class _Args:
    claude_md = None
    skills_dir = None
    no_global = True
    no_skills = True
    no_project = True


def _ts(i):
    return f"2026-01-01T00:00:{i:02d}.000Z"


def user_text(text, i):
    return {"type": "user", "timestamp": _ts(i), "message": {"content": text}}


def assistant_text(text, i):
    return {"type": "assistant", "timestamp": _ts(i),
            "message": {"content": [{"type": "text", "text": text}]}}


def _write_jsonl(tmp_path, events, name="t.jsonl"):
    p = tmp_path / name
    with p.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return p


def _hook_ts(i):
    return f"2026-01-01T00:00:{i:02d}+00:00"


def instruction(path, load_reason, i):
    return {"path": str(path), "memory_type": "Project", "load_reason": load_reason,
            "globs": ["**/*.css"], "trigger_file_path": None, "parent_file_path": None,
            "ts": _hook_ts(i), "stats": {}}


def compaction(i, trigger="auto"):
    return {"event": "PreCompact", "ts": _hook_ts(i), "trigger": trigger}


def facts(instructions=(), compactions=()):
    return {"instructions": list(instructions), "compactions": list(compactions)}


def make_rule(tmp_path, name="style.md"):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    p = rules / name
    p.write_text(
        '---\npaths: ["**/*.css"]\n---\n\n'
        "# Style rules\n\n"
        "## Use logical properties\n"
        "Prefer `margin-inline` over `margin-left`.\n"
    )
    return p


def four_turn_events():
    ev = []
    for n in range(4):
        ev.append(user_text(f"q{n}", n * 2))
        ev.append(assistant_text(f"a{n}", n * 2 + 1))
    return ev


# ---------- split_into_turns ----------

def test_no_compactions_splits_exactly_as_before():
    events = four_turn_events()
    base = brv.split_into_turns(events)
    for arg in (None, [], [None], [""]):
        got = brv.split_into_turns(events, arg)
        assert [(t["startEventIdx"], t["endEventIdx"], t["userPrompt"]) for t in got] == \
               [(t["startEventIdx"], t["endEventIdx"], t["userPrompt"]) for t in base]
        assert all(t["afterCompaction"] is False for t in got)


def test_compaction_splits_a_turn_in_two():
    events = four_turn_events()
    # Mid-way through turn 1 (its prompt is event 2, its reply event 3).
    turns = brv.split_into_turns(events, [_ts(3)])
    assert len(turns) == 5
    assert [t["startEventIdx"] for t in turns] == [0, 2, 3, 4, 6]
    assert [t["afterCompaction"] for t in turns] == [False, False, True, False, False]
    # The carved-off half keeps the prompt it belongs to.
    assert turns[2]["userPrompt"] == "q1"


def test_compaction_on_an_existing_boundary_adds_no_turn():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(4)])
    assert len(turns) == 4
    assert [t["afterCompaction"] for t in turns] == [False, False, True, False]


def test_compaction_before_the_first_prompt_is_ignored():
    events = four_turn_events()
    turns = brv.split_into_turns(events, ["2025-01-01T00:00:00.000Z"])
    assert len(turns) == 4
    assert all(t["afterCompaction"] is False for t in turns)


def test_unparseable_compaction_timestamp_is_ignored():
    events = four_turn_events()
    assert len(brv.split_into_turns(events, ["not a timestamp"])) == 4


def test_compactions_out_of_order_keep_the_right_prompt():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(7), _ts(3)])
    assert [t["userPrompt"] for t in turns] == ["q0", "q1", "q1", "q2", "q3", "q3"]
    assert [t["afterCompaction"] for t in turns] == [False, False, True, False, False, True]


def test_pre_and_post_compact_on_the_same_event_make_one_boundary():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(3), _ts(3)])
    assert len(turns) == 5


def test_duplicate_compaction_timestamps_evict_once():
    turns = brv.split_into_turns(four_turn_events(), [_ts(4)])
    comp = [compaction(4, "auto"), {"event": "PostCompact", "ts": _hook_ts(4), "trigger": "auto"}]
    _, records = brv.compute_residency(
        turns, comp, facts([instruction("/x.md", "path_glob_match", 0)], comp))
    assert [r["evicted"] for r in records] == [["/x.md"], ["/x.md"]]


def test_a_second_compaction_does_not_re_evict_an_already_gone_file():
    turns = brv.split_into_turns(four_turn_events(), [_ts(2), _ts(6)])
    comp = [compaction(2), compaction(6)]
    nonres, records = brv.compute_residency(
        turns, comp, facts([instruction("/x.md", "path_glob_match", 0)], comp))
    assert [r["evicted"] for r in records] == [["/x.md"], []]
    assert nonres[1] == {"/x.md"} and nonres[3] == {"/x.md"}


def test_compaction_without_a_usable_timestamp_is_dropped():
    turns = brv.split_into_turns(four_turn_events(), [_ts(4)])
    comp = [compaction(4), {"event": "PreCompact", "ts": None, "trigger": None}]
    _, records = brv.compute_residency(
        turns, comp, facts([instruction("/x.md", "path_glob_match", 0)], comp))
    assert len(records) == 1


def test_transcript_compaction_source_is_an_unimplemented_stub():
    """No compacted transcript was available, so this must stay empty rather
    than pretend to parse a marker shape nobody has verified."""
    assert brv.compactions_from_transcript(four_turn_events()) == []


# ---------- compute_residency ----------

def test_no_compactions_means_nothing_is_non_resident():
    turns = brv.split_into_turns(four_turn_events())
    nonres, records = brv.compute_residency(turns, [], facts([instruction("/x.md", "path_glob_match", 0)]))
    assert nonres == {} and records == []


def test_glob_loaded_file_goes_non_resident_after_compaction():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(4)])
    nonres, records = brv.compute_residency(
        turns, [compaction(4)], facts([instruction("/x.md", "path_glob_match", 0)], [compaction(4)]))
    assert nonres.get(0) is None and nonres.get(1) is None
    assert nonres[2] == {"/x.md"} and nonres[3] == {"/x.md"}
    assert records == [{"ts": _hook_ts(4), "event": "PreCompact", "trigger": "auto",
                        "evicted": ["/x.md"]}]


def test_session_start_file_survives_compaction():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(4)])
    nonres, records = brv.compute_residency(
        turns, [compaction(4)], facts([instruction("/x.md", "session_start", 0)], [compaction(4)]))
    assert nonres == {}
    assert records[0]["evicted"] == []


def test_reload_after_compaction_restores_residency():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(4)])
    comp = [compaction(4)]
    nonres, _ = brv.compute_residency(turns, comp, facts(
        [instruction("/x.md", "path_glob_match", 0), instruction("/x.md", "compact", 5)], comp))
    assert nonres[2] == {"/x.md"}
    assert nonres.get(3) is None


def test_file_the_log_never_mentions_stays_resident():
    events = four_turn_events()
    turns = brv.split_into_turns(events, [_ts(4)])
    nonres, _ = brv.compute_residency(turns, [compaction(4)], facts([], [compaction(4)]))
    assert nonres == {}


def test_missing_hook_facts_never_evicts():
    turns = brv.split_into_turns(four_turn_events(), [_ts(4)])
    nonres, records = brv.compute_residency(turns, [compaction(4)], None)
    assert nonres == {}
    assert records[0]["evicted"] == []


# ---------- end to end ----------

def _run(tmp_path, monkeypatch, hook_facts, events=None):
    events = events or four_turn_events()
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: hook_facts)
    return brv.process_session(p, _Args())


def test_evicted_rule_is_assessed_only_on_pre_boundary_turns(tmp_path, monkeypatch):
    rule = make_rule(tmp_path)
    comp = [compaction(4)]
    _, per_session = _run(tmp_path, monkeypatch,
                          facts([instruction(rule.resolve(), "path_glob_match", 0)], comp))

    turns = per_session["turns"]
    assert len(turns) == 4
    present = [any(f["kind"] == "rule" for f in t["contextFiles"]) for t in turns]
    assert present == [True, True, False, False]
    assert turns[2]["afterCompaction"] is True
    assert turns[2]["nonResidentCount"] == 1
    # The aggregate still carries the file and its blocks.
    agg_rule = next(f for f in per_session["contextFiles"] if f["kind"] == "rule")
    assert agg_rule["blocks"]


def test_session_start_rule_stays_in_every_turn(tmp_path, monkeypatch):
    rule = make_rule(tmp_path)
    comp = [compaction(4)]
    _, per_session = _run(tmp_path, monkeypatch,
                          facts([instruction(rule.resolve(), "session_start", 0)], comp))
    assert all(any(f["kind"] == "rule" for f in t["contextFiles"]) for t in per_session["turns"])


def test_block_with_zero_assessable_turns_still_appears(tmp_path, monkeypatch):
    """Evicted from the very first turn onwards: the block must keep its
    session-scope status rather than disappear from the panel."""
    rule = make_rule(tmp_path)
    # Both the glob load and the compaction predate every event, so the rule is
    # already gone by the time the first turn starts.
    load = instruction(rule.resolve(), "path_glob_match", 0)
    load["ts"] = "2025-12-31T23:59:00+00:00"
    comp = [{"event": "PreCompact", "ts": "2025-12-31T23:59:30+00:00", "trigger": "auto"}]
    _, per_session = _run(tmp_path, monkeypatch, facts([load], comp))

    assert all(not any(f["kind"] == "rule" for f in t["contextFiles"])
               for t in per_session["turns"])
    agg_rule = next(f for f in per_session["contextFiles"] if f["kind"] == "rule")
    assert agg_rule["blocks"]
    assert all(b["status"] for b in agg_rule["blocks"])


def test_compaction_row_lands_in_the_aggregate_timeline(tmp_path, monkeypatch):
    rule = make_rule(tmp_path)
    comp = [compaction(4)]
    _, per_session = _run(tmp_path, monkeypatch,
                          facts([instruction(rule.resolve(), "path_glob_match", 0)], comp))
    rows = [r for r in per_session["timeline"] if r["kind"] == "compaction"]
    assert len(rows) == 1
    assert "1 file(s) no longer resident" in rows[0]["text"]
    # Chronological: it sits between the events it separates.
    idx = per_session["timeline"].index(rows[0])
    assert per_session["timeline"][idx - 1]["text"] == "a1"
    assert per_session["timeline"][idx + 1]["text"] == "q2"


def test_hookless_session_payload_has_no_compaction_keys(tmp_path, monkeypatch):
    _, per_session = _run(tmp_path, monkeypatch, None)
    assert not any(r["kind"] == "compaction" for r in per_session["timeline"])
    for t in per_session["turns"]:
        assert "afterCompaction" not in t
        assert "nonResidentCount" not in t
    assert json.dumps(per_session)  # payload stays serialisable


# ---------- malformed hook data ----------

@pytest.mark.parametrize("bad_ts", [None, "not-a-date", ""])
def test_compaction_with_unorderable_timestamp_does_not_break_the_timeline(bad_ts):
    """A compaction record whose ts can't be parsed must not take the build down.

    Compaction records are unverified against real data, so a shape surprise here
    is likely rather than hypothetical.
    """
    timeline = [{"ts": _ts(5), "kind": "x", "label": "a", "text": "b"}]
    brv._insert_compaction_rows(
        timeline, [{"ts": bad_ts, "evicted": [], "event": "PreCompact", "trigger": "auto"}])
    assert [r["kind"] for r in timeline].count("compaction") == 1
