"""Tests for Phase 7: session compare.

Alignment is content-based (difflib over tool-call name sequences), never by
index, so one inserted call must not cascade divergence through every later
step. The compare payload is opt-in: a default build must not carry it.
"""
import json

import build_real_view as brv

from tests.test_turns import (
    _Args,
    _ts,
    _write_jsonl,
    assistant_text,
    assistant_tool_use,
    user_text,
    user_tool_result,
)


# ---------- helpers ----------

def _kinds(steps):
    return [s["kind"] for s in steps]


def _block(bid, title, content, status="unused"):
    return {"id": bid, "title": title, "content": content, "status": status}


def _file(path, blocks, loaded=True):
    return {"path": path, "loaded": loaded, "blocks": blocks}


def _session(sid, prompt, turns=None, files=None, usage=None, counts=None):
    """A baked per_session dict trimmed to what the compare stage reads."""
    return {
        "session": {"id": sid, "userPrompt": prompt, "startTime": _ts(0),
                    "endTime": _ts(9)},
        "counts": counts or {"totalToolCalls": 0, "filesEdited": 0},
        "usage": usage or brv.usage_totals([]),
        "contextFiles": files or [],
        "turns": turns or [],
        "turnCount": len(turns or []),
    }


def _turn(index, prompt, names, usage=None, edits=0):
    return {
        "id": f"turn-{index}",
        "index": index,
        "userPrompt": prompt,
        "promptPreview": prompt,
        "counts": {"totalToolCalls": len(names), "filesEdited": edits},
        "usage": usage or brv.usage_totals([]),
        "timeline": [{"ts": _ts(i), "kind": "tool-use", "label": n, "text": n.lower()}
                     for i, n in enumerate(names)],
        "contextFiles": [],
    }


# ---------- align_actions ----------

def test_align_identical_sequences_all_match():
    names = ["Read", "Bash", "Edit", "Read"]
    steps = brv.align_actions(names, list(names))
    assert _kinds(steps) == ["match"] * 4
    assert [(s["a"], s["b"]) for s in steps] == [(0, 0), (1, 1), (2, 2), (3, 3)]


def test_align_single_insertion_leaves_every_later_step_paired():
    a = ["Read", "Bash", "Edit", "Read", "Bash"]
    b = ["Read", "Bash", "Grep", "Edit", "Read", "Bash"]
    steps = brv.align_actions(a, b)

    unmatched = [s for s in steps if s["kind"] != "match"]
    assert len(unmatched) == 1
    assert unmatched[0]["kind"] == "added"
    assert unmatched[0]["a"] is None
    assert unmatched[0]["b"] == 2

    # Everything after the insertion still pairs, shifted by one on the B side.
    later = [s for s in steps if s["kind"] == "match" and s["a"] >= 2]
    assert [(s["a"], s["b"]) for s in later] == [(2, 3), (3, 4), (4, 5)]


def test_align_removal_and_replacement():
    a = ["Read", "Bash", "Edit"]
    b = ["Read", "Edit"]
    assert _kinds(brv.align_actions(a, b)) == ["match", "removed", "match"]

    a2 = ["Read", "Bash", "Edit"]
    b2 = ["Read", "Grep", "Edit"]
    steps = brv.align_actions(a2, b2)
    assert _kinds(steps) == ["match", "changed", "match"]
    assert steps[1]["a"] == 1 and steps[1]["b"] == 1


def test_align_empty_sides():
    assert brv.align_actions([], []) == []
    assert _kinds(brv.align_actions([], ["Read"])) == ["added"]
    assert _kinds(brv.align_actions(["Read"], [])) == ["removed"]


# ---------- session-level step alignment ----------

def test_compare_sessions_marks_one_divergence_for_an_inserted_call():
    a = _session("aaa", "do the thing",
                 turns=[_turn(0, "do the thing", ["Read", "Bash", "Edit"])])
    b = _session("bbb", "do the thing",
                 turns=[_turn(0, "do the thing", ["Read", "Bash", "Grep", "Edit"])])
    cmp = brv.compare_sessions(a, b)

    assert _kinds(cmp["steps"]) == ["match", "match", "added", "match"]
    added = cmp["steps"][2]
    assert added["b"]["name"] == "Grep"
    assert added["a"] is None
    assert cmp["divergentSteps"] == 1


def test_compare_steps_carry_turn_index_and_names():
    a = _session("aaa", "p", turns=[_turn(0, "p", ["Read"]), _turn(1, "q", ["Bash"])])
    b = _session("bbb", "p", turns=[_turn(0, "p", ["Read"]), _turn(1, "q", ["Bash"])])
    cmp = brv.compare_sessions(a, b)
    assert [s["a"]["turn"] for s in cmp["steps"]] == [0, 1]
    assert [s["a"]["name"] for s in cmp["steps"]] == ["Read", "Bash"]


def test_compare_sessions_end_to_end(tmp_path, monkeypatch):
    base = [
        user_text("fix the bug", 0),
        assistant_tool_use("Read", {"file_path": "/tmp/a"}, 1, tool_id="t1"),
        user_tool_result("t1", "ac", 2),
        assistant_tool_use("Edit", {"file_path": "/tmp/a"}, 3, tool_id="t2"),
        user_tool_result("t2", "ok", 4),
        assistant_text("done", 5),
    ]
    extra = base[:3] + [
        assistant_tool_use("Grep", {"pattern": "x"}, 3, tool_id="t9"),
        user_tool_result("t9", "hit", 4),
    ] + base[3:]

    monkeypatch.chdir(tmp_path)
    pa = _write_jsonl(tmp_path, base, name="a.jsonl")
    pb = _write_jsonl(tmp_path, extra, name="b.jsonl")
    _, da = brv.process_session(pa, _Args())
    _, db = brv.process_session(pb, _Args())

    cmp = brv.compare_sessions(da, db)
    assert _kinds(cmp["steps"]) == ["match", "added", "match"]
    assert cmp["sameTask"] is True
    assert cmp["deltas"]["toolCalls"]["Grep"] == 1


# ---------- context diff ----------

def test_context_diff_reports_added_removed_and_changed_blocks():
    fa = _file("~/.claude/CLAUDE.md", [
        _block("claude-md-0-style", "Style", "be terse"),
        _block("claude-md-1-gone", "Gone", "old rule"),
    ])
    fb = _file("~/.claude/CLAUDE.md", [
        _block("claude-md-0-style", "Style", "be terse and direct"),
        _block("claude-md-2-new", "New", "a fresh rule"),
    ])
    diff = brv.compare_context_files([fa], [fb])
    assert len(diff) == 1
    d = diff[0]
    assert d["path"] == "~/.claude/CLAUDE.md"
    assert [b["id"] for b in d["added"]] == ["claude-md-2-new"]
    assert [b["title"] for b in d["added"]] == ["New"]
    assert [b["id"] for b in d["removed"]] == ["claude-md-1-gone"]
    assert [b["id"] for b in d["changed"]] == ["claude-md-0-style"]
    assert [b["title"] for b in d["changed"]] == ["Style"]


def test_context_diff_flags_drifted_file_and_leaves_identical_files_out():
    same = _file("a.md", [_block("a-0-x", "X", "same text")])
    drifted_a = _file("b.md", [_block("b-0-y", "Y", "before")])
    drifted_b = _file("b.md", [_block("b-0-y", "Y", "after")])
    diff = brv.compare_context_files([same, drifted_a], [same, drifted_b])
    assert [d["path"] for d in diff] == ["b.md"]
    assert diff[0]["drifted"] is True
    assert diff[0]["presence"] == "both"


def test_context_diff_reports_file_present_on_one_side_only():
    diff = brv.compare_context_files([_file("only-a.md", [_block("x-0-t", "T", "c")])], [])
    assert diff[0]["presence"] == "a-only"
    assert [b["id"] for b in diff[0]["removed"]] == ["x-0-t"]


def test_context_diff_reports_verdict_changes():
    fa = _file("a.md", [_block("a-0-x", "X", "same", status="unused")])
    fb = _file("a.md", [_block("a-0-x", "X", "same", status="used")])
    diff = brv.compare_context_files([fa], [fb])
    assert diff[0]["verdictChanges"] == [
        {"id": "a-0-x", "title": "X", "from": "unused", "to": "used"}]
    assert diff[0]["drifted"] is False


def test_compare_sessions_surfaces_verdict_changes_at_top_level():
    a = _session("aaa", "p", files=[_file("a.md", [_block("a-0-x", "X", "c", status="unused")])])
    b = _session("bbb", "p", files=[_file("a.md", [_block("a-0-x", "X", "c", status="used")])])
    cmp = brv.compare_sessions(a, b)
    assert cmp["verdictChanges"] == [
        {"path": "a.md", "id": "a-0-x", "title": "X", "from": "unused", "to": "used"}]


# ---------- different-task guard ----------

def test_different_first_prompts_flag_the_comparison():
    a = _session("aaa", "fix the login bug")
    b = _session("bbb", "write the release notes")
    cmp = brv.compare_sessions(a, b)
    assert cmp["sameTask"] is False
    assert "different" in cmp["note"].lower()


def test_same_first_prompt_is_not_flagged():
    a = _session("aaa", "  Fix the login bug\n")
    b = _session("bbb", "fix the login BUG")
    cmp = brv.compare_sessions(a, b)
    assert cmp["sameTask"] is True
    assert cmp["note"] == ""


# ---------- deltas ----------

def test_turn_rows_report_token_and_call_deltas():
    ua = brv.usage_totals([{"input": 10, "output": 5, "cacheRead": 0, "cacheCreation": 0,
                            "cacheCreation1h": 0, "cacheCreation5m": 0, "thinking": 0}])
    ub = brv.usage_totals([{"input": 30, "output": 9, "cacheRead": 0, "cacheCreation": 0,
                            "cacheCreation1h": 0, "cacheCreation5m": 0, "thinking": 0}])
    a = _session("aaa", "p", turns=[_turn(0, "p", ["Read"], usage=ua)])
    b = _session("bbb", "p", turns=[_turn(0, "p", ["Read", "Bash"], usage=ub)])
    cmp = brv.compare_sessions(a, b)
    row = cmp["turns"][0]
    assert row["promptMatch"] is True
    assert row["deltas"]["toolCalls"] == 1
    assert row["deltas"]["promptTokens"] == 20
    assert row["deltas"]["outputTokens"] == 4


def test_turn_rows_cover_an_unpaired_trailing_turn():
    a = _session("aaa", "p", turns=[_turn(0, "p", ["Read"])])
    b = _session("bbb", "p", turns=[_turn(0, "p", ["Read"]), _turn(1, "again", ["Bash"])])
    cmp = brv.compare_sessions(a, b)
    assert len(cmp["turns"]) == 2
    assert cmp["turns"][1]["a"] is None
    assert cmp["turns"][1]["b"]["index"] == 1


# ---------- payload gating ----------

def test_build_data_omits_compare_unless_requested():
    data = brv.build_data("/tmp/proj", [], {}, None)
    assert "compare" not in data
    assert set(data) == {"project", "sessions", "activeSessionId", "perSession"}


def test_build_data_includes_compare_when_given():
    data = brv.build_data("/tmp/proj", [], {}, None, compare={"steps": []})
    assert data["compare"] == {"steps": []}


def test_resolve_compare_session_by_id_prefix():
    per_session = {"abc12345": {}, "def67890": {}}
    assert brv.resolve_session_id(per_session, "abc") == "abc12345"


def test_resolve_compare_session_rejects_unknown_and_ambiguous():
    per_session = {"abc12345": {}, "abc99999": {}}
    for bad in ("zzz", "abc"):
        try:
            brv.resolve_session_id(per_session, bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_compare_flag_defaults_to_none(monkeypatch):
    monkeypatch.setattr("sys.argv", ["build_real_view.py"])
    assert brv.parse_args().compare is None


def test_compare_payload_is_json_serialisable():
    a = _session("aaa", "p", turns=[_turn(0, "p", ["Read"])],
                 files=[_file("a.md", [_block("a-0-x", "X", "c")])])
    b = _session("bbb", "p", turns=[_turn(0, "p", ["Read", "Bash"])],
                 files=[_file("a.md", [_block("a-0-x", "X", "d")])])
    json.dumps(brv.compare_sessions(a, b))
