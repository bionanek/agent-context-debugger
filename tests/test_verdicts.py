"""Tests for evidence tiering in the verdict pipeline (Phase 6).

The distinction under test is *strong* evidence (a trigger that fired, a
structural record of what the run did, a reviewed compiled check that ran)
versus *weak* evidence (a bare command mention, loose keyword overlap). Weak
evidence may only ever produce `possibly-referenced`; handing out the green
`used` for it is the bug these guard against.
"""
import json
from pathlib import Path

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import (
    _Args,
    _ts,
    _write_jsonl,
    assistant_text,
    assistant_tool_use,
    user_slash,
    user_text,
)


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


def test_a_single_passing_mention_is_not_lexical_evidence():
    """The >= 2 observation guard: one mention of a term is not a pattern.

    This used to be enough - two of the block's first eight five-letter words
    appearing anywhere scored `possibly-referenced` - which is the mechanism
    that made almost every loaded block "possibly referenced".
    """
    events = [user_text("ship it", 1),
              assistant_text("The staging pipeline runs before the production "
                             "release, so deployment is safe.", 2)]
    v = brv.assess_block(block_from(KEYWORD_MD), rule_file(),
                         trace_for(events, "ship it"))
    assert v["status"] == "unused"
    assert v["evidenceLabel"] == "no-lexical-trace"


def test_lexical_evidence_tops_out_at_possibly_referenced():
    """Sustained shared vocabulary is co-occurrence, and co-occurrence is weak."""
    md = ("## Store hydration\n\nHydration guards protect the persisted zustand "
          "slice. Rehydrate the slice through the migration shim, never directly.\n")
    events = [user_text("fix hydration", 1),
              assistant_text("I added the hydration guard around the persisted "
                             "zustand slice, then ran the migration shim so "
                             "rehydrate goes through it. The hydration path now "
                             "rejects a stale persisted slice, and the migration "
                             "shim reports what it dropped.", 2)]
    v = brv.assess_block(block_from(md), rule_file(), trace_for(events, "fix hydration"))
    assert v["status"] == "possibly-referenced"
    assert v["evidenceLabel"] == "topical-overlap"


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
    """The turn-aware view's documented invariant, re-proved after the
    taxonomy grew: a block used in any turn is used at session scope."""
    for others in (["unused"], ["dormant", "not-loaded"], ["possibly-referenced"],
                   ["undelivered", "possibly-referenced", "used-partial"]):
        assert brv.combine_verdicts(others + ["used"]) == "used"


def test_single_turn_status_passes_through_unchanged():
    assert brv.combine_verdicts(["possibly-referenced"]) == "possibly-referenced"


# ---------- one trigger matcher for the predicate and the moment card ----------
# The predicate used a bare substring test of its own, so a prompt reading
# `/implement-plan-workflow` scored the `/implement-plan` pointer `used` while
# the moment card beside it said the command was never invoked (F-TRIGGER).

TRIGGER_POINTER_MD = """# implement-plan

- **implement-plan** (`~/.claude/skills/implement-plan/SKILL.md`) - orchestrate a
  multi-phase implementation plan. Trigger: `/implement-plan`
"""


def _trigger_fired(events, prompt):
    pred = next(p for p in brv.derive_predicates(block_from(TRIGGER_POINTER_MD))
                if p["kind"] == "trigger")
    return pred["matches"](trace_for(events, prompt))


def test_a_longer_sibling_command_never_fires_the_shorter_trigger():
    """Hyphen and colon continuations are both bounded, in every evidence order."""
    for prompt in ("/implement-plan-workflow with the plan below",
                   "/implement-plan:v2 please"):
        assert not _trigger_fired([user_text(prompt, 1)], prompt)
    wrapper = [user_slash("implement-plan-workflow", "the plan", 1)]
    assert not _trigger_fired(wrapper, brv.first_real_user_prompt(wrapper))
    call = [user_text("run it", 1),
            assistant_tool_use("Skill", {"skill": "implement-plan-workflow"}, 2)]
    assert not _trigger_fired(call, "run it")


def test_the_trigger_fires_on_every_record_of_a_real_invocation():
    """Counter-anchor: the three evidence orders the moment card reads from."""
    assert _trigger_fired([user_text("/implement-plan go", 1)], "/implement-plan go")
    wrapper = [user_slash("implement-plan", "the plan", 1)]
    assert _trigger_fired(wrapper, brv.first_real_user_prompt(wrapper))
    call = [user_text("run it", 1),
            assistant_tool_use("Skill", {"skill": "implement-plan"}, 2)]
    assert _trigger_fired(call, "run it")


def test_trigger_verdict_and_its_moment_card_agree():
    """Two matchers for one question is how a green badge ended up above a
    "not invoked this run" card; assert they cannot disagree again - including
    on the records only one of the two used to read."""
    cases = [
        ("/implement-plan-workflow with the plan below", []),
        ("/implement-plan go", []),
        ("have a look at ~/.claude/skills/implement-plan", []),
        ("run it", [assistant_tool_use("Skill", {"skill": "implement-plan"}, 2)]),
        ("run it", [assistant_tool_use("Skill", {"skill": "implement-plan-workflow"}, 2)]),
    ]
    for prompt, extra in cases:
        events = [user_text(prompt, 1)] + extra + [assistant_text("Starting.", 3)]
        v = brv.assess_block(block_from(TRIGGER_POINTER_MD),
                             rule_file(), trace_for(events, prompt))
        denied = any(m["verdict"] == "no" and "not invoked" in m["label"]
                     for m in v["moments"])
        assert (v["status"] == "used") is not denied, (prompt, extra)


# ---------- a compiled workflow check drives the scale ----------
# The gh-account rule was a hardcoded `path-table` predicate until Phase 8b
# retired it (one user's table header was the only shape it knew). The same
# rule now lives in a checks file as `tool_never_without_prior`, and these
# cases are the F-PATHTABLE / F-COMBINE anchors driven through it: a rule whose
# trigger never came up, a real violation, and the session-scope combine.

PATH_TABLE_MD = """## GitHub account per project

Before running any `gh` command, check the active GitHub account with
`gh auth status` and switch if needed.

**Rule:** If the active account doesn't match the project, run the switch
command silently before proceeding.
"""

GH_CHECK = {
    "source": "CLAUDE.md",
    "checks": [{
        "id": "gh-auth-before-gh",
        "rule_ref": "GitHub account per project",
        "rule_text": "Before running any `gh` command, check the active account.",
        "domain": "tool",
        "kind": "tool_never_without_prior",
        "pattern": r"\bgh\s+(?!auth\b)\S+",
        "prior_pattern": r"\bgh\s+auth\s+(?:status|switch)\b",
        "applies_to": [],
        "confidence": "high",
        "message": "A `gh` command ran without checking the active account first.",
        "self_test": {
            "should_match": ["Bash gh pr create --fill"],
            "should_not_match": ["Bash gh auth status\nBash gh pr create --fill",
                                 "Bash gh auth status"],
        },
    }],
}

FORMIC_CWD = "/Users/dev/Git/formic-core"


def _with_cwd(events, cwd=FORMIC_CWD):
    return [dict(e, cwd=cwd) for e in events]


def _gh_doc(tmp_path):
    """The rule document plus its reviewed checks file, on disk."""
    doc = tmp_path / "CLAUDE.md"
    doc.write_text(PATH_TABLE_MD)
    (tmp_path / "CLAUDE.md.checks.json").write_text(json.dumps(GH_CHECK))
    rc.checks_for_doc.cache_clear()
    return doc


def _path_table_verdict(tmp_path, events, prompt):
    doc = _gh_doc(tmp_path)
    return brv.assess_block(block_from(PATH_TABLE_MD),
                            {"loaded": True, "kind": "global", "path": str(doc),
                             "abs_path": str(doc), "name": None},
                            trace_for(_with_cwd(events), prompt))


def test_a_rule_whose_subject_never_came_up_is_dormant_not_ignored(tmp_path):
    """Applicability is not exercise: the rule's trigger never fired here.

    Without the distinction a turn that ran no `gh` command at all was reported
    as a GitHub-account violation, which is how a dozen compliant turns ended
    up under a red session badge. The conditional check reports the stage it
    reached, so the block says the rule was never tested rather than broken.
    """
    v = _path_table_verdict(tmp_path,
                            [user_text("count the files", 1),
                             bash("ls -la src", 2),
                             assistant_text("There are 12 files.", 3)],
                            "count the files")
    assert v["status"] == "dormant"
    assert v["ruleCheck"]["state"] == "not-exercised"
    assert v["ruleCheck"]["findings"][0]["stage"] == rc.STAGE_ANTECEDENT


def test_ignored_still_reachable_once_the_rule_was_exercised(tmp_path):
    """Counter-anchor: the gate must not swallow real violations - `gh` ran
    here, so the missing account check is a genuine finding."""
    v = _path_table_verdict(tmp_path,
                            [user_text("open a PR", 1),
                             bash("gh pr create --fill", 2)],
                            "open a PR")
    assert v["status"] == "ignored"


def test_a_satisfied_compiled_check_is_strong_enough_for_used(tmp_path):
    """The other half of the same record: the run did the thing and complied.

    Retiring the prose predicate would otherwise leave a demonstrably
    compliant session reading `unused`, and one violating turn would then
    repaint the session `ignored` at the combine.
    """
    v = _path_table_verdict(tmp_path,
                            [user_text("open a PR", 1),
                             bash("gh auth switch -u bionanek-x", 2, tool_id="b1"),
                             bash("gh pr create --fill", 3, tool_id="b2")],
                            "open a PR")
    assert v["status"] == "used", v["reason"]
    assert v["ruleCheck"]["state"] == "clear"


# ---------- session scope: one status, one reason ----------

def _gh_session_file(tmp_path, monkeypatch, turns):
    """The fixture's own CLAUDE.md record, baked at session scope.

    Selected as the *project* document, not by block title: the loader also
    picks up the real `~/.claude/CLAUDE.md`, whose own GitHub-account rule
    carries the same heading, so matching on the title alone would score
    whichever file came first on the machine running the tests.
    """
    _gh_doc(tmp_path)
    p = _write_jsonl(tmp_path, _with_cwd(turns))
    monkeypatch.chdir(tmp_path)
    summary, per_session = brv.process_session(p, _Args())
    for f in per_session["contextFiles"]:
        if f["kind"] == "project" and Path(f["path"]).name == "CLAUDE.md":
            return summary, f
    raise AssertionError("the fixture's CLAUDE.md was not baked")


def _gh_session_block(tmp_path, monkeypatch, turns):
    _, f = _gh_session_file(tmp_path, monkeypatch, turns)
    return next(b for b in f["blocks"]
                if b["title"] == "GitHub account per project")


def test_one_unexercised_turn_does_not_paint_a_compliant_session_red(tmp_path, monkeypatch):
    block = _gh_session_block(tmp_path, monkeypatch, [
        user_text("open a PR", 1),
        bash("gh auth switch -u bionanek-x", 2, tool_id="b1"),
        bash("gh pr create --fill", 3, tool_id="b2"),
        assistant_text("PR opened.", 4),
        user_text("now count the files", 5),
        bash("ls -la src", 6, tool_id="b3"),
        assistant_text("There are 12 files.", 7),
    ])
    assert block["status"] == "used"


def _twelve_compliant_turns_then_one_violation():
    """Twelve turns checking the account before `gh`, then one that does not."""
    events = []
    i = 0
    for n in range(12):
        i += 1
        events.append(user_text(f"open PR {n}", i))
        i += 1
        events.append(bash("gh auth switch -u bionanek-x", i, tool_id=f"s{n}"))
        i += 1
        events.append(bash("gh pr create --fill", i, tool_id=f"p{n}"))
        i += 1
        events.append(assistant_text(f"PR {n} opened.", i))
    i += 1
    events.append(user_text("open one more", i))
    i += 1
    events.append(bash("gh pr create --fill", i, tool_id="last"))
    i += 1
    events.append(assistant_text("Done.", i))
    return events


def test_one_violating_turn_among_compliant_ones_reads_as_mixed(tmp_path, monkeypatch):
    """A dozen compliant turns must not be repainted by one red turn, and the
    violation must stay visible: `used-partial`, not `used` and not `ignored`."""
    block = _gh_session_block(tmp_path, monkeypatch,
                              _twelve_compliant_turns_then_one_violation())
    assert block["status"] == "used-partial"


def test_session_scope_reason_describes_the_combined_status(tmp_path, monkeypatch):
    """The aggregate's reason was recomputed independently of the combine rule,
    so one record read "status ignored / 1 predicate(s) applied and were
    satisfied" - three realities in one row. Wherever the combine rule
    overrules the aggregate's own assessment, the sentence is rewritten from
    the statuses the status itself came from."""
    block = _gh_session_block(tmp_path, monkeypatch,
                              _twelve_compliant_turns_then_one_violation())
    assert "turns" in block["reason"].lower()
    assert "none were satisfied" not in block["reason"].lower()


def test_mixed_combine_beats_neither_used_nor_ignored():
    assert brv.combine_verdicts(["used", "ignored"]) == "used-partial"
    assert brv.combine_verdicts(["ignored", "used-partial"]) == "used-partial"
    assert brv.combine_verdicts(["ignored", "dormant", "unused"]) == "ignored"


def test_a_downgraded_session_still_reports_the_violation(tmp_path, monkeypatch):
    """`used-partial` is not "nothing violated": the file rollup and the
    session headline must still name the turn that broke the rule."""
    summary, rec = _gh_session_file(tmp_path, monkeypatch,
                                    _twelve_compliant_turns_then_one_violation())
    block = next(b for b in rec["blocks"]
                 if b["title"] == "GitHub account per project")
    assert block["status"] == "used-partial"
    assert block["violatingTurns"] == 1
    assert "violated" in rec["rollup"]["summary"]
    assert summary["headline"] != "nothing violated"


def test_a_clean_session_bakes_no_violating_turns_key(tmp_path, monkeypatch):
    _, rec = _gh_session_file(tmp_path, monkeypatch, [
        user_text("open a PR", 1),
        bash("gh auth switch -u bionanek-x", 2, tool_id="b1"),
        bash("gh pr create --fill", 3, tool_id="p1"),
        assistant_text("PR opened.", 4),
        user_text("open another", 5),
        bash("gh auth switch -u bionanek-x", 6, tool_id="b2"),
        bash("gh pr create --fill", 7, tool_id="p2"),
        assistant_text("PR opened.", 8),
    ])
    for b in rec["blocks"]:
        assert "violatingTurns" not in b
    assert "violated" not in rec["rollup"]["summary"]
