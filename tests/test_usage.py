"""Tests for real token usage extracted from `message.usage`.

Phase 4: usage_series / usage_totals / cache_breaks, and the payload fields
they feed (session totals in the summary, the series in per_session, per-turn
totals on each turn payload, cache-break rows on the timeline).
"""
import build_real_view as brv

from tests.test_turns import (_ts, _write_jsonl, _Args, user_text,
                              assistant_text, assistant_tool_use,
                              user_tool_result)


# ---------- builders ----------

def usage(inp=0, out=0, cache_read=0, cache_creation=0,
          eph_1h=None, eph_5m=None, thinking=None):
    u = {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
    }
    if eph_1h is not None or eph_5m is not None:
        u["cache_creation"] = {
            "ephemeral_1h_input_tokens": eph_1h or 0,
            "ephemeral_5m_input_tokens": eph_5m or 0,
        }
    if thinking is not None:
        u["output_tokens_details"] = {"thinking_tokens": thinking}
    return u


def assistant_usage(text, i, u, msg_id=None):
    """Assistant text event carrying a usage object (and a request id)."""
    e = assistant_text(text, i)
    e["message"]["usage"] = u
    e["message"]["id"] = msg_id or f"msg_{i}"
    return e


# ---------- usage_series ----------

def test_series_one_entry_per_assistant_event():
    events = [
        user_text("q", 0),
        assistant_usage("a", 1, usage(inp=5, out=50, cache_read=100, cache_creation=200,
                                      eph_1h=200, eph_5m=0, thinking=7)),
    ]
    series = brv.usage_series(events)
    assert len(series) == 1
    e = series[0]
    assert e["ts"] == _ts(1)
    assert e["input"] == 5
    assert e["output"] == 50
    assert e["cacheRead"] == 100
    assert e["cacheCreation"] == 200
    assert e["cacheCreation1h"] == 200
    assert e["cacheCreation5m"] == 0
    assert e["thinking"] == 7


def test_series_dedupes_repeated_request_ids():
    """One API response is written as several assistant events sharing a
    message id and repeating the same usage object - counting each would
    roughly double every figure on real transcripts."""
    u = usage(inp=2, out=100, cache_read=1000, cache_creation=300)
    events = [
        user_text("q", 0),
        assistant_usage("thinking out loud", 1, u, msg_id="msg_A"),
        assistant_usage("still the same response", 2, u, msg_id="msg_A"),
        assistant_usage("next response", 3, usage(inp=1, out=20), msg_id="msg_B"),
    ]
    series = brv.usage_series(events)
    assert [s["requestId"] for s in series] == ["msg_A", "msg_B"]
    assert brv.usage_totals(series)["outputTokens"] == 120


def test_series_skips_user_events():
    events = [
        user_text("q", 0),
        user_tool_result("t1", "out", 1),
        assistant_usage("a", 2, usage(inp=1, out=2)),
    ]
    assert len(brv.usage_series(events)) == 1


def test_series_missing_usage_contributes_zeros():
    events = [
        user_text("q", 0),
        assistant_text("no usage at all", 1),
        assistant_tool_use("Read", {"file_path": "/x"}, 2),
    ]
    series = brv.usage_series(events)
    totals = brv.usage_totals(series)
    for key in ("inputTokens", "outputTokens", "cacheReadTokens",
                "cacheCreationTokens", "thinkingTokens"):
        assert totals[key] == 0


# ---------- usage_totals ----------

def test_totals_sum_every_field():
    events = [
        user_text("q", 0),
        assistant_usage("a1", 1, usage(inp=1, out=10, cache_read=100, cache_creation=1000,
                                       eph_1h=600, eph_5m=400, thinking=5), msg_id="m1"),
        assistant_usage("a2", 2, usage(inp=2, out=20, cache_read=200, cache_creation=2000,
                                       eph_1h=0, eph_5m=2000, thinking=6), msg_id="m2"),
    ]
    t = brv.usage_totals(brv.usage_series(events))
    assert t["requests"] == 2
    assert t["inputTokens"] == 3
    assert t["outputTokens"] == 30
    assert t["cacheReadTokens"] == 300
    assert t["cacheCreationTokens"] == 3000
    assert t["cacheCreation1hTokens"] == 600
    assert t["cacheCreation5mTokens"] == 2400
    assert t["thinkingTokens"] == 11
    # Prompt tokens are what the request actually paid for as input.
    assert t["promptTokens"] == 3 + 300 + 3000


def test_totals_empty_series():
    t = brv.usage_totals([])
    assert t["requests"] == 0 and t["inputTokens"] == 0 and t["promptTokens"] == 0


# ---------- cache breaks ----------

def _entry(i, cache_read, cache_creation):
    return {"ts": _ts(i), "eventIndex": i, "requestId": f"m{i}", "input": 2, "output": 10,
            "cacheRead": cache_read, "cacheCreation": cache_creation,
            "cacheCreation1h": 0, "cacheCreation5m": 0, "thinking": 0}


def test_cache_break_detected():
    series = [
        _entry(1, 0, 40000),
        _entry(2, 40000, 500),
        _entry(3, 41000, 500),
        _entry(4, 0, 42000),     # prefix repaid: the cache was broken
        _entry(5, 42000, 300),
    ]
    breaks = brv.cache_breaks(series)
    assert len(breaks) == 1
    assert breaks[0]["ts"] == _ts(4)
    assert breaks[0]["priorCacheRead"] == 41000
    assert breaks[0]["cacheCreation"] == 42000


def test_no_cache_break_on_steady_reads():
    series = [_entry(1, 40000, 500), _entry(2, 41000, 600), _entry(3, 42000, 700)]
    assert brv.cache_breaks(series) == []


def test_no_cache_break_when_prior_prefix_is_small():
    """Below a real prefix there is nothing to lose, so an ordinary cold start
    must not be reported as a break."""
    series = [_entry(1, 200, 100), _entry(2, 0, 3000)]
    assert brv.cache_breaks(series) == []


def test_cache_break_first_request_never_flags():
    assert brv.cache_breaks([_entry(1, 0, 90000)]) == []


# ---------- per-turn slicing ----------

def test_usage_for_turn_partitions_by_event_range():
    series = [_entry(1, 0, 100), _entry(3, 100, 50), _entry(5, 150, 50)]
    early = {"startEventIdx": 0, "endEventIdx": 4}
    late = {"startEventIdx": 4, "endEventIdx": 6}
    assert [e["eventIndex"] for e in brv.usage_for_turn(series, early)] == [1, 3]
    assert [e["eventIndex"] for e in brv.usage_for_turn(series, late)] == [5]


def test_request_straddling_a_turn_boundary_counted_once():
    """A response written as several events can be split by a compaction-driven
    turn boundary. Slicing the one deduped series by event range keeps it in a
    single turn, so per-turn totals still sum to the session total."""
    u = usage(inp=2, out=100, cache_read=1000)
    events = [
        user_text("q", 0),
        assistant_usage("part one", 1, u, msg_id="msg_A"),
        assistant_usage("part two", 2, u, msg_id="msg_A"),
    ]
    series = brv.usage_series(events)
    first = {"startEventIdx": 0, "endEventIdx": 2}
    second = {"startEventIdx": 2, "endEventIdx": 3}
    per_turn = [brv.usage_totals(brv.usage_for_turn(series, t))["outputTokens"]
                for t in (first, second)]
    assert per_turn == [100, 0]
    assert sum(per_turn) == brv.usage_totals(series)["outputTokens"]


# ---------- payload wiring ----------

def _usage_session_events():
    return [
        user_text("q1", 0),
        assistant_usage("a1", 1, usage(inp=1, out=10, cache_read=0, cache_creation=30000,
                                       thinking=3), msg_id="m1"),
        user_text("q2", 2),
        assistant_usage("a2", 3, usage(inp=2, out=20, cache_read=30000, cache_creation=500,
                                       thinking=4), msg_id="m2"),
        user_text("q3", 4),
        assistant_usage("a3", 5, usage(inp=3, out=30, cache_read=0, cache_creation=31000,
                                       thinking=5), msg_id="m3"),
    ]


def test_process_session_exposes_usage(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path, _usage_session_events())
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())

    t = per_session["usage"]
    assert t["inputTokens"] == 6
    assert t["outputTokens"] == 60
    assert t["cacheReadTokens"] == 30000
    assert t["cacheCreationTokens"] == 61500
    assert t["thinkingTokens"] == 12

    # Heavy series lives in per_session only; cheap totals ride on the summary.
    assert len(per_session["usageSeries"]) == 3
    assert "usageSeries" not in summary
    assert summary["usage"] == t


def test_per_turn_usage_sums_only_that_turn(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path, _usage_session_events())
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    turns = per_session["turns"]
    assert len(turns) == 3
    assert [t["usage"]["outputTokens"] for t in turns] == [10, 20, 30]
    assert [t["usage"]["inputTokens"] for t in turns] == [1, 2, 3]
    assert [t["usage"]["thinkingTokens"] for t in turns] == [3, 4, 5]
    # Per-turn totals reconcile with the session totals.
    assert sum(t["usage"]["outputTokens"] for t in turns) == per_session["usage"]["outputTokens"]


def test_cache_break_row_on_timeline(tmp_path, monkeypatch):
    p = _write_jsonl(tmp_path, _usage_session_events())
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    rows = [r for r in per_session["timeline"] if r["kind"] == "cache-break"]
    assert len(rows) == 1
    assert rows[0]["ts"] == _ts(5)
    # The break lands inside the turn it happened in, not just the aggregate.
    turn_rows = [r for t in per_session["turns"] for r in t["timeline"]
                 if r["kind"] == "cache-break"]
    assert len(turn_rows) == 1


def test_session_without_usage_still_builds(tmp_path, monkeypatch):
    events = [user_text("q", 0), assistant_text("a", 1)]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    assert per_session["usage"]["promptTokens"] == 0
    # The request still happened, so it keeps a (zeroed) series entry.
    assert [e["output"] for e in per_session["usageSeries"]] == [0]
    assert not [r for r in per_session["timeline"] if r["kind"] == "cache-break"]


def test_summarize_transcript_carries_usage(tmp_path):
    p = _write_jsonl(tmp_path, _usage_session_events())
    s = brv.summarize_transcript(p)
    assert s["usage"]["outputTokens"] == 60
