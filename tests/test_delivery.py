"""Tests for the `undelivered` status: blocks that never reached the model.

The distinction under test is *never arrived* versus *arrived and ignored*.
Scoring a truncated-away block as `unused` is the bug these guard against.
"""
import build_real_view as brv


# ---------- helpers ----------

def read_call(path, offset=None, limit=None):
    inp = {"file_path": str(path)}
    if offset is not None:
        inp["offset"] = offset
    if limit is not None:
        inp["limit"] = limit
    return {"type": "assistant", "timestamp": "2026-01-01T00:00:00.000Z",
            "message": {"content": [{"type": "tool_use", "name": "Read",
                                     "id": "t1", "input": inp}]}}


def gotchas(tmp_path, total_lines, rule_heading_at):
    """A long .md whose only H2 heading sits at `rule_heading_at`."""
    lines = ["# Gotchas", ""] + ["filler prose line." for _ in range(total_lines)]
    lines[rule_heading_at - 1] = "## Never run migrations by hand"
    lines[rule_heading_at] = "Always use `npm run migrate` instead."
    p = tmp_path / "gotchas.md"
    p.write_text("\n".join(lines[:total_lines]))
    return p


class _Args:
    skills_dir = None


def load_one(tmp_path, events):
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _Args(), "do the thing")
    return next(f for f in files if f["abs_path"].endswith("gotchas.md"))


def trace_for(events):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), "do the thing")


# ---------- parse_claude_md line spans ----------

def test_blocks_carry_line_spans():
    blocks = brv.parse_claude_md("# One\na\n\n## Two\nb\nc\n")
    assert [(b["title"], b["start_line"], b["end_line"]) for b in blocks] == [
        ("One", 1, 3), ("Two", 4, 6)]


def test_headings_inside_fences_do_not_start_blocks():
    text = "# One\n```\n## Not a heading\n```\n## Two\nx\n"
    blocks = brv.parse_claude_md(text)
    assert [b["title"] for b in blocks] == ["One", "Two"]
    assert blocks[1]["start_line"] == 5


# ---------- delivered range ----------

def test_unbounded_read_of_long_file_is_truncated_at_the_cap(tmp_path):
    p = gotchas(tmp_path, 2400, 2380)
    f = load_one(tmp_path, [read_call(p)])
    assert f["delivery"] == "truncated"
    assert f["total_lines"] == 2400
    assert f["delivered_to"] == brv.READ_DEFAULT_LINE_CAP


def test_short_file_read_whole_is_full(tmp_path):
    p = gotchas(tmp_path, 120, 100)
    f = load_one(tmp_path, [read_call(p)])
    assert f["delivery"] == "full"
    assert f["delivered_to"] == f["total_lines"] == 120


def test_repeat_reads_union_their_ranges(tmp_path):
    p = gotchas(tmp_path, 2400, 2380)
    f = load_one(tmp_path, [read_call(p, offset=1, limit=50),
                            read_call(p, offset=2300, limit=100)])
    assert (f["delivered_from"], f["delivered_to"]) == (1, 2399)
    assert f["delivery"] == "partial-by-request"


# ---------- the acceptance criteria ----------

def test_rule_past_the_cap_reports_undelivered_with_both_line_numbers(tmp_path):
    p = gotchas(tmp_path, 2400, 2380)
    events = [read_call(p)]
    f = load_one(tmp_path, events)
    block = next(b for b in f["blocks"] if b["title"].startswith("Never run"))

    v = brv.assess_block(block, f, trace_for(events))
    assert v["status"] == "undelivered"
    assert "2000" in v["reason"] and "2400" in v["reason"] and "2380" in v["reason"]
    assert v["evidence"] == []


def test_same_rule_above_the_cap_gets_normal_assessment(tmp_path):
    p = gotchas(tmp_path, 2400, 1500)
    events = [read_call(p)]
    f = load_one(tmp_path, events)
    block = next(b for b in f["blocks"] if b["title"].startswith("Never run"))

    v = brv.assess_block(block, f, trace_for(events))
    assert v["status"] != "undelivered"


def test_missing_line_count_never_promotes_a_block():
    """Absence of evidence must route to existing behaviour, not to `undelivered`."""
    d = brv._delivery_range("/no/such/file.md", "x", "read", "disk", [(None, None)])
    assert d["delivery"] == "unknown"
    assert not brv._block_undelivered({"start_line": 9999}, d)


# ---------- precedence ----------

def test_undelivered_wins_over_the_other_not_used_statuses():
    assert brv.combine_verdicts(["unused", "undelivered"]) == "undelivered"
    assert brv.combine_verdicts(["dormant", "undelivered", "not-loaded"]) == "undelivered"


def test_undelivered_does_not_outrank_the_used_family():
    assert brv.combine_verdicts(["undelivered", "used"]) == "used"
    assert brv.combine_verdicts(["undelivered", "ignored"]) == "ignored"
    assert brv.combine_verdicts(["undelivered", "used-partial"]) == "used-partial"
