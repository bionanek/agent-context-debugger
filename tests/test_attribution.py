"""Tests for token attribution across context items.

Phase 5: attribute_request / attribute_usage / block_costs and the payload
fields they feed (per-file cumulative cost on every context file, per-block
estimates, attributed costs on duplicate pairs).
"""
import build_real_view as brv

from tests.test_turns import (_ts, _write_jsonl, _Args, user_text,
                              assistant_text, user_tool_result)
from tests.test_usage import usage, assistant_usage
from tests.test_skills import skill_listing


def _entry(i, inp=0, cache_read=0, cache_creation=0):
    return {"ts": _ts(i), "eventIndex": i, "requestId": f"m{i}",
            "input": inp, "output": 10, "cacheRead": cache_read,
            "cacheCreation": cache_creation, "cacheCreation1h": 0,
            "cacheCreation5m": 0, "thinking": 0}


# ---------- attribute_request ----------

def test_attribution_is_proportional_and_sums_to_total():
    per_item, history = brv.attribute_request([("a", 100), ("b", 300)], 1000)
    assert per_item == {"a": 250, "b": 750}
    assert history == 0
    assert sum(per_item.values()) + history == 1000


def test_attribution_sums_exactly_despite_rounding():
    per_item, history = brv.attribute_request([("a", 1), ("b", 1), ("c", 1)], 10)
    assert sum(per_item.values()) + history == 10
    assert max(per_item.values()) - min(per_item.values()) <= 1


def test_history_bucket_absorbs_its_share():
    per_item, history = brv.attribute_request([("a", 100)], 1000, history_chars=100)
    assert per_item == {"a": 500}
    assert history == 500


def test_all_tokens_go_to_history_when_no_items():
    per_item, history = brv.attribute_request([], 900, history_chars=0)
    assert per_item == {}
    assert history == 900


# ---------- attribute_usage ----------

def test_file_resident_for_every_request_reports_sent_count_and_cost():
    entries = [_entry(i, inp=10, cache_read=90) for i in (1, 3, 5)]
    out = brv.attribute_usage([("a", 100), ("b", 100)], entries)

    a = out["files"]["a"]
    assert a["sentCount"] == 3
    # 100 prompt tokens per request, split evenly by size, times 3 requests.
    assert a["tokens"] == 150
    # 90 of every 100 prompt tokens were cache reads.
    assert a["cached"] == 135
    assert a["fresh"] == 15
    assert a["cached"] + a["fresh"] == a["tokens"]
    assert out["requests"] == 3


def test_attribution_reconciles_with_session_usage_totals():
    entries = [_entry(1, inp=50, cache_read=1000, cache_creation=200),
               _entry(2, inp=7, cache_read=1234, cache_creation=0),
               _entry(3, inp=3, cache_read=0, cache_creation=999)]
    history = {e["eventIndex"]: 400 for e in entries}
    out = brv.attribute_usage([("a", 137), ("b", 260)], entries, history_chars=history)

    attributed = sum(f["tokens"] for f in out["files"].values()) + out["history"]["tokens"]
    assert attributed == brv.usage_totals(entries)["promptTokens"]
    assert out["attributedTokens"] == attributed


def test_nonresident_file_stops_accruing_cost():
    entries = [_entry(i, inp=100) for i in (1, 2, 3)]
    # "a" was evicted at the second request and never reloaded.
    nonresident = {2: {"a"}, 3: {"a"}}
    out = brv.attribute_usage([("a", 100), ("b", 100)], entries,
                              nonresident_by_request=nonresident)

    assert out["files"]["a"]["sentCount"] == 1
    assert out["files"]["a"]["tokens"] == 50
    # Its share goes to the remaining resident item, not into thin air.
    assert out["files"]["b"]["sentCount"] == 3
    assert out["files"]["b"]["tokens"] == 50 + 100 + 100


def test_item_never_resident_reports_zero_cost():
    entries = [_entry(1, inp=100)]
    out = brv.attribute_usage([("a", 100)], entries, nonresident_by_request={1: {"a"}})
    assert out["files"]["a"] == {"sentCount": 0, "tokens": 0, "cached": 0, "fresh": 0}
    assert out["history"]["tokens"] == 100


# ---------- block_costs ----------

def test_block_costs_split_file_cost_by_line_share_and_are_estimates():
    blocks = [{"content": "one\ntwo\nthree"}, {"content": "solo"}]
    costs = brv.block_costs({"tokens": 100, "cached": 90, "fresh": 10}, blocks)
    assert [c["tokens"] for c in costs] == [75, 25]
    assert all(c["estimated"] is True for c in costs)
    assert sum(c["tokens"] for c in costs) == 100


def test_block_costs_of_a_free_file_are_zero():
    costs = brv.block_costs({"tokens": 0, "cached": 0, "fresh": 0},
                            [{"content": "a"}, {"content": "b"}])
    assert [c["tokens"] for c in costs] == [0, 0]


# ---------- history sizing ----------

def test_history_chars_grow_with_the_conversation():
    events = [
        user_text("q" * 40, 0),
        assistant_usage("a", 1, usage(inp=1)),
        user_tool_result("t1", "r" * 400, 2),
        assistant_usage("b", 3, usage(inp=1)),
    ]
    series = brv.usage_series(events)
    hist = brv.history_chars_by_request(events, series)
    assert set(hist) == {1, 3}
    assert hist[3] > hist[1] > 0


# ---------- payload wiring ----------

def _session_events():
    return [
        user_text("q1", 0),
        assistant_usage("a1", 1, usage(inp=100, out=10, cache_read=900)),
        user_text("q2", 2),
        assistant_usage("a2", 3, usage(inp=200, out=10, cache_read=1800)),
    ]


def _fixture_file(per_session, tmp_path):
    """The fixture's own CLAUDE.md, told apart from the machine's real global one."""
    files = [f for f in per_session["contextFiles"]
             if f["path"].endswith("CLAUDE.md") and str(tmp_path) in f["path"]]
    assert files, "fixture CLAUDE.md should be a context file"
    return files[0]


def test_context_files_carry_cumulative_cost(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# One\nrule text\n\n# Two\nmore text\n")
    p = _write_jsonl(tmp_path, _session_events())
    monkeypatch.chdir(tmp_path)

    class Args(_Args):
        no_project = False

    summary, per_session = brv.process_session(p, Args())

    f = _fixture_file(per_session, tmp_path)
    assert f["cost"]["sentCount"] == 2
    assert f["cost"]["tokens"] > 0
    assert f["cost"]["cached"] + f["cost"]["fresh"] == f["cost"]["tokens"]
    # Per-block figures derive from the file's and are always labelled estimates.
    assert sum(b["cost"]["tokens"] for b in f["blocks"]) == f["cost"]["tokens"]
    assert all(b["cost"]["estimated"] is True for b in f["blocks"])

    assert per_session["attribution"]["attributedTokens"] == per_session["usage"]["promptTokens"]
    assert summary["contextTokens"] == sum(
        cf["cost"]["tokens"] for cf in per_session["contextFiles"])


def test_headingless_file_is_still_priced(tmp_path, monkeypatch):
    # No H1/H2 heading, so the file parses to zero blocks - it still cost real
    # tokens on every request and must not price as free.
    (tmp_path / "CLAUDE.md").write_text("just prose, no headings at all\n" * 20)
    p = _write_jsonl(tmp_path, _session_events())
    monkeypatch.chdir(tmp_path)

    class Args(_Args):
        no_project = False

    _, per_session = brv.process_session(p, Args())
    f = _fixture_file(per_session, tmp_path)
    assert f["blocks"] == []
    assert f["cost"]["tokens"] > 0


def test_listing_only_skill_is_still_priced(tmp_path, monkeypatch):
    # A skill the harness listed but whose file is nowhere on disk is built as a
    # phantom record, outside add_file - it must still carry a size.
    events = [skill_listing(["- ghostly: a skill with no file on disk"], 0),
              user_text("use /ghostly please", 1),
              assistant_usage("a1", 2, usage(inp=100, out=10, cache_read=900))]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)

    _, per_session = brv.process_session(p, _Args())
    f = next(f for f in per_session["contextFiles"] if f["path"].endswith("ghostly"))
    assert f["loaded"] is True
    assert f["cost"]["tokens"] > 0


def test_turn_costs_sum_to_the_session_cost(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_text("# One\nrule text\n\n# Two\nmore text\n")
    p = _write_jsonl(tmp_path, _session_events())
    monkeypatch.chdir(tmp_path)

    class Args(_Args):
        no_project = False

    _, per_session = brv.process_session(p, Args())
    if per_session["turnCount"] < 2:
        return
    per_turn = sum(t["attribution"]["attributedTokens"] for t in per_session["turns"])
    assert per_turn == per_session["attribution"]["attributedTokens"]


def test_duplicate_pairs_report_attributed_costs():
    shared = ("Always write the failing test first and only then the "
              "implementation that makes it pass, never the other way around, "
              "because tests written afterwards describe the code you wrote.")
    files_out = [
        {"path": "a.md", "kind": "global", "loaded": True,
         "blocks": [{"id": "a-0-rule", "title": "Rule", "content": shared,
                     "cost": {"tokens": 400, "estimated": True}}]},
        {"path": "b.md", "kind": "project", "loaded": True,
         "blocks": [{"id": "b-0-rule", "title": "Rule", "content": shared,
                     "cost": {"tokens": 100, "estimated": True}}]},
    ]
    trace = {"user_prompt": "", "segs": [], "all_assistant_text": "",
             "calls": [], "cwd": ""}
    pairs = brv.compute_duplicates(files_out, trace)
    assert len(pairs) == 1
    d = pairs[0]
    assert d["tokensA"] == 400
    assert d["tokensB"] == 100
    assert d["estimated"] is True
    # The duplicated cost cannot exceed the cheaper side of the pair.
    assert 0 < d["tokens"] <= 100
