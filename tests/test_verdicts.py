"""Tests for evidence tiering in the verdict pipeline (Phase 6).

The distinction under test is *strong* evidence (a trigger that fired, a
satisfied path-table row, end-of-message compliance)
versus *weak* evidence (a bare command mention, loose keyword overlap). Weak
evidence may only ever produce `possibly-referenced`; handing out the green
`used` for it is the bug these guard against.
"""
import build_real_view as brv

from tests.test_turns import _ts, assistant_text, assistant_tool_use, user_text


# ---------- helpers ----------

def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def block_from(md):
    """The single block of a one-heading markdown snippet."""
    return brv.parse_claude_md(md)[0]


def rule_file(loaded=True, kind="global"):
    return {"loaded": loaded, "kind": kind, "path": "CLAUDE.md",
            "abs_path": "/tmp/CLAUDE.md", "name": None}


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


# ---------- weak evidence: bare command mention ----------

WEAK_MENTION_MD = """## Copy to clipboard

When copying text, pipe it through `pbcopy` so the result lands on the
clipboard ready to paste.
"""


def test_bare_command_mention_only_scores_possibly_referenced():
    """`pbcopy` ran for its own reasons; naming it in prose is not compliance."""
    events = [user_text("do the thing", 1),
              bash("printf '%s' hello | pbcopy", 2)]
    v = brv.assess_block(block_from(WEAK_MENTION_MD), rule_file(), trace_for(events))
    assert v["status"] == "possibly-referenced"
    assert "weak evidence" in v["reason"].lower()


def test_command_mention_that_never_ran_stays_dormant():
    events = [user_text("do the thing", 1), bash("ls -la", 2)]
    v = brv.assess_block(block_from(WEAK_MENTION_MD), rule_file(), trace_for(events))
    assert v["status"] == "dormant"


# ---------- strong evidence keeps its verdicts ----------

TRIGGER_MD = """## graphify

- **graphify** turns any input into a knowledge graph. Trigger: `/graphify`
"""

NEGATIVE_MD = """## Copy to clipboard

Never `echo` into a clipboard command - the shell appends a trailing newline.
"""


def test_fired_trigger_still_scores_used():
    events = [user_text("/graphify this repo", 1), assistant_text("On it.", 2)]
    v = brv.assess_block(block_from(TRIGGER_MD), rule_file(),
                         trace_for(events, "/graphify this repo"))
    assert v["status"] == "used"


def test_a_prose_negation_never_scores_ignored_on_its_own():
    """Phase 9 removed the "never X" shell predicate: the word after `never`
    was matched against bash commands, which turned code rules into phantom
    violations. A prose negation now only reaches a verdict through a compiled
    checks file (see tests/test_rule_checks.py)."""
    events = [user_text("copy it", 1), bash("echo hi | pbcopy", 2)]
    v = brv.assess_block(block_from(NEGATIVE_MD), rule_file(),
                         trace_for(events, "copy it"))
    assert v["status"] == "possibly-referenced"
    # `echo` is a bare English-shaped word, so mechanical extraction refuses it
    # rather than matching it against source text.
    assert v["ruleCheck"]["state"] == "not-checkable"


MIXED_MD = """## graphify

Trigger: `/graphify`. The skill shells out to `python3` for the parse step.
"""


def test_a_weak_mention_alongside_strong_evidence_does_not_soften_the_verdict():
    events = [user_text("/graphify it", 1), bash("python3 parse.py", 2)]
    v = brv.assess_block(block_from(MIXED_MD), rule_file(),
                         trace_for(events, "/graphify it"))
    assert v["status"] == "used"


# ---------- weak evidence: loose keyword overlap ----------

KEYWORD_MD = """## Deployment notes

Deployment happens through the staging pipeline before production release.
"""


def test_loose_keyword_overlap_only_scores_possibly_referenced():
    events = [user_text("ship it", 1),
              assistant_text("The staging pipeline runs before the production "
                             "release, so deployment is safe.", 2)]
    v = brv.assess_block(block_from(KEYWORD_MD), rule_file(),
                         trace_for(events, "ship it"))
    assert v["status"] == "possibly-referenced"
    assert "weak evidence" in v["reason"].lower()


def test_no_signal_at_all_stays_unused():
    events = [user_text("ship it", 1), assistant_text("Nothing to report.", 2)]
    v = brv.assess_block(block_from(KEYWORD_MD), rule_file(),
                         trace_for(events, "ship it"))
    assert v["status"] == "unused"


# ---------- duplicate classification uses the same tiers ----------

SHARED_PARAGRAPH = ("Always prefer the simplest solution that could possibly work "
                    "and never introduce an abstraction nobody asked for today.")


def dup_files(extra_a="", extra_b=""):
    a_md = f"## Simplicity\n\n{SHARED_PARAGRAPH}\n{extra_a}\n"
    b_md = f"## Simplicity again\n\n{SHARED_PARAGRAPH}\n{extra_b}\n"
    out = []
    for path, md in (("A.md", a_md), ("B.md", b_md)):
        blocks = brv.parse_claude_md(md)
        for idx, blk in enumerate(blocks):
            blk["id"] = f"{path}-{idx}"
        out.append({"path": path, "abs_path": f"/tmp/{path}", "loaded": True,
                    "kind": "global", "name": None, "blocks": blocks})
    return out


def test_weak_only_duplicate_pair_is_redundant():
    """A never-fired negative rule plus a bare command mention is not usage."""
    events = [user_text("unrelated work", 1), bash("ls -la", 2)]
    pairs = brv.compute_duplicates(dup_files(extra_a="Never `rimraf` anything."),
                                   trace_for(events, "unrelated work"))
    assert pairs and pairs[0]["classification"] == "redundant"


def test_duplicate_pair_with_a_fired_predicate_is_referenced():
    events = [user_text("/graphify it", 1), bash("ls -la", 2)]
    pairs = brv.compute_duplicates(dup_files(extra_a="Trigger: `/graphify`"),
                                   trace_for(events, "/graphify it"))
    assert pairs and pairs[0]["classification"] == "referenced"


def test_duplicate_pair_with_a_strong_topical_reference_is_referenced():
    events = [user_text("clean it up", 1),
              assistant_text("I'll keep the simplest solution and avoid any "
                             "abstraction nobody asked for.", 2)]
    pairs = brv.compute_duplicates(dup_files(), trace_for(events, "clean it up"))
    assert pairs and pairs[0]["classification"] == "referenced"


def phantom_files(*names):
    """Listing-only entries, the shape load_context_files synthesises for a
    skill the harness listed but whose file it could not find on disk."""
    out = []
    for name in names:
        md = (f"# {name}\n\nA short description of {name}.\n\n"
              "_(This skill was listed by the harness but its source file "
              "could not be located on disk.)_")
        blocks = brv.parse_claude_md(md)
        for idx, blk in enumerate(blocks):
            blk["id"] = f"{name}-{idx}"
        out.append({"path": f"(listing-only) {name}", "abs_path": f"<listing-only:{name}>",
                    "loaded": False, "kind": "skill", "source": "listing-only",
                    "name": name, "blocks": blocks})
    return out


def test_listing_only_phantoms_are_not_compared_to_each_other():
    """Their shared text is boilerplate this tool wrote, not context that was sent."""
    events = [user_text("unrelated work", 1)]
    pairs = brv.compute_duplicates(phantom_files("alpha", "beta", "gamma"),
                                   trace_for(events, "unrelated work"))
    assert pairs == []


def test_phantom_boilerplate_does_not_bury_a_real_duplicate():
    events = [user_text("unrelated work", 1), bash("ls -la", 2)]
    files = dup_files(extra_a="Never `rimraf` anything.") + phantom_files(*(
        f"skill-{i}" for i in range(8)))
    pairs = brv.compute_duplicates(files, trace_for(events, "unrelated work"))
    assert len(pairs) == 1
    assert pairs[0]["classification"] == "redundant"


# ---------- disjoint delivered ranges ----------

def spaced_md(tmp_path, total_lines, heading_lines):
    lines = ["# Doc", ""] + ["filler prose line." for _ in range(total_lines)]
    lines = lines[:total_lines]
    for n, title in heading_lines.items():
        lines[n - 1] = f"## {title}"
    p = tmp_path / "doc.md"
    p.write_text("\n".join(lines))
    return p


def read_call(path, offset=None, limit=None, i=2, tool_id="t1"):
    inp = {"file_path": str(path)}
    if offset is not None:
        inp["offset"] = offset
    if limit is not None:
        inp["limit"] = limit
    return assistant_tool_use("Read", inp, i, tool_id=tool_id)


class _Args:
    skills_dir = None


def two_range_read(tmp_path):
    p = spaced_md(tmp_path, 2400, {50: "Early rule", 1200: "Middle rule",
                                   1950: "Late rule"})
    events = [user_text("look at the doc", 1),
              read_call(p, offset=1, limit=100, i=2, tool_id="t1"),
              read_call(p, offset=1900, limit=101, i=3, tool_id="t2")]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _Args(),
                                   "look at the doc")
    f = next(x for x in files if x["abs_path"].endswith("doc.md"))
    return f, events


def test_delivered_ranges_are_kept_as_intervals(tmp_path):
    f, _ = two_range_read(tmp_path)
    assert f["delivered_ranges"] == [(1, 100), (1900, 2000)]
    assert (f["delivered_from"], f["delivered_to"]) == (1, 2000)


def test_block_in_the_gap_between_two_reads_is_undelivered(tmp_path):
    f, events = two_range_read(tmp_path)
    block = next(b for b in f["blocks"] if b["title"] == "Middle rule")
    v = brv.assess_block(block, f, trace_for(events, "look at the doc"))
    assert v["status"] == "undelivered"
    assert "1200" in v["reason"]


def test_blocks_inside_either_range_assess_normally(tmp_path):
    f, events = two_range_read(tmp_path)
    trace = trace_for(events, "look at the doc")
    for title in ("Early rule", "Late rule"):
        block = next(b for b in f["blocks"] if b["title"] == title)
        assert brv.assess_block(block, f, trace)["status"] != "undelivered"


def test_a_read_offset_past_the_end_of_the_file_reports_unknown(tmp_path):
    """The file shrank since the read, so its arguments describe nothing."""
    p = spaced_md(tmp_path, 40, {30: "Only rule"})
    events = [user_text("look", 1), read_call(p, offset=900, limit=20)]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _Args(), "look")
    f = next(x for x in files if x["abs_path"].endswith("doc.md"))
    assert f["delivery"] == "unknown"
    block = next(b for b in f["blocks"] if b["title"] == "Only rule")
    assert not brv._block_undelivered(block, f)


def test_a_single_full_read_still_reports_one_covering_range(tmp_path):
    p = spaced_md(tmp_path, 120, {100: "Only rule"})
    events = [user_text("look", 1), read_call(p)]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _Args(), "look")
    f = next(x for x in files if x["abs_path"].endswith("doc.md"))
    assert f["delivery"] == "full"
    assert f["delivered_ranges"] == [(1, 120)]


# ---------- combine_verdicts ranking ----------

def test_used_in_any_turn_beats_possibly_referenced():
    assert brv.combine_verdicts(["possibly-referenced", "used"]) == "used"
    assert brv.combine_verdicts(["possibly-referenced", "used-partial"]) == "used-partial"
    assert brv.combine_verdicts(["possibly-referenced", "ignored"]) == "ignored"


def test_possibly_referenced_beats_every_not_used_status():
    for weaker in ("undelivered", "unused", "dormant", "not-loaded"):
        assert brv.combine_verdicts([weaker, "possibly-referenced"]) == "possibly-referenced"


def test_prd_invariant_holds_used_in_any_turn_is_used_at_session_scope():
    """plans/turn-aware-view.md's documented invariant, re-proved after the
    taxonomy grew: a block used in any turn is used at session scope."""
    for others in (["unused"], ["dormant", "not-loaded"], ["possibly-referenced"],
                   ["undelivered", "possibly-referenced", "used-partial"]):
        assert brv.combine_verdicts(others + ["used"]) == "used"


def test_single_turn_status_passes_through_unchanged():
    assert brv.combine_verdicts(["possibly-referenced"]) == "possibly-referenced"
