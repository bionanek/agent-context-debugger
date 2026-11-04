"""Regression harness: the audit's verified-wrong verdicts, as executable cases.

This module is the specification of *wrong*. Every case here was verified by
hand against a real transcript (see §7 of
`docs/judgement-reliability-research.md` for the session-id / block-id anchors
and §2 for the failure mechanisms), reconstructed from in-memory events that
reproduce the mechanism rather than the session.

Each test's name carries its mechanism tag as a prefix - `test_f_trigger_*`,
`test_f_pathtable_*`, `test_f_combine_*`, `test_f_eom_*`, `test_f_cmdmention_*`,
`test_f_blindspot_*`, `test_f_moments_*`, `test_f_misc_*` - so a later phase can
name exactly what it flips (`pytest -k f_trigger`). Counter-anchors, the
verdicts the audit found *correct*, are tagged `test_counter_anchor_*` and must
keep passing through every phase.

**Every case here has to be able to fail.** A case is *vacuous* when its
fixture derives no predicate and its document has no checks file: nothing in
`assess_block` can then reach a hard verdict, so `status != "ignored"` passes
whatever the implementation does. Sixteen cases were vacuous in exactly that
way, because the two rules they are about - the GitHub-account table and the
closing-summary rule - lost their bespoke prose predicates when those were
retired, and nothing replaced them here. Both are now driven through
`tests/fixtures/global_rules.md` and the reviewed checks file beside it, which
is the only mechanism left that can reach either verdict, and each case asserts
the exact status and the exact rule-check state instead of a negation.

The probes that prove they can fail, one line each. Every one was run against
this file and reverted; the cases each turns red are named beside it, and a
case no probe reaches does not belong here.

- **P1** `build_real_view._apply_rule_check`: `violations = []`. The red path
  vanishes - `f_pathtable_a_gh_command_with_no_prior_check`, both
  `f_combine` cases that read the violating turn.
- **P2** `build_real_view._apply_rule_check`: `satisfied = []`. A reviewed
  check that ran and was met stops giving credit - both `f_pathtable`
  compliance cases and all three `f_combine` cases.
- **P3** `build_real_view._apply_rule_check`: `elif (rule_check["state"] ==
  "not-exercised"` -> `elif (False and ...`. A rule nothing triggered stops
  saying so - both `f_pathtable` not-exercised cases and `f_combine`
  `an_unexercised_turn`.
- **P4** `build_real_view.combine_verdicts`: `if "used" in statuses or
  "used-partial" in statuses:` -> `if False:`. One violating turn repaints the
  session - `f_combine` `one_violating_turn` and
  `session_status_and_reason_describe_the_same_reality`.
- **P5** `rule_checks.load_checks`: `elif bucket in ("hybrid", "judged"):` ->
  `elif False:`. A rule parked for a judge is reported as one that was
  checked - all nine `f_eom` cases and both
  `counter_anchor_eom_captured_output` cases.
- **P6** `build_real_view._strip_table_rows`: `return text`. Table cells become
  commands again - `f_pathtable` `row_path_token`, `row_token` and
  `no_gh_activity`.
- **P7** `build_real_view._redirect_write_targets`: `cmd.split("\\n", 1)[0]` ->
  `cmd`. Captured output reads as a file being authored -
  `counter_anchor_eom_captured_output`.
- **P8** `rule_checks.compile_hint`: return `""`. The gap stops being
  actionable - `counter_anchor_eom_an_uncompiled_copy_asks_to_be_compiled`.

A probe inside `rule_checks._evaluate_tools` itself is caught one layer
earlier: the check's own fixtures stop reproducing under this tool's matcher,
the loader refuses it, and every `f_pathtable` and `f_combine` case goes red
with the rule reported as not checkable. That gate is deliberate, so those
probes prove the cases can fail without isolating a single mechanism, which is
why the eight above are the recorded ones.
"""
from pathlib import Path

import pytest

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


def with_cwd(events, cwd):
    """Stamp a cwd on every event, the way the harness writes transcripts.

    `build_trace` takes the first cwd it finds, so a test that forgets this
    scores every path-conditional rule against an empty cwd - which reads as
    "the rule did not apply" no matter what the rule says.
    """
    return [dict(e, cwd=cwd) for e in events]


def block_from(md, title=None):
    """One block of a markdown snippet - the first, or the one named."""
    blocks = brv.parse_claude_md(md)
    if title is None:
        return blocks[0]
    return next(b for b in blocks if b["title"] == title)


def rule_file(loaded=True, kind="global", name=None, path="CLAUDE.md", md=None):
    # `blocks` is what a real context-file record always carries, and
    # `_is_identity_block` reads it to tell a skill's title block from its
    # steps. A record without it can answer nothing, so a test about that
    # distinction has to supply the document.
    return {"loaded": loaded, "kind": kind, "path": path,
            "abs_path": f"/tmp/{path}", "name": name,
            "blocks": brv.parse_claude_md(md) if md else []}


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


def verdict(md, events, prompt="do the thing", file=None, title=None):
    return brv.assess_block(block_from(md, title), file or rule_file(),
                            trace_for(events, prompt))


def mention_cmds(md, title=None):
    return sorted(p["cmd"] for p in brv.derive_predicates(block_from(md, title))
                  if p["kind"] == "command-mention")


def predicate_kinds(md, title=None):
    return sorted(p["kind"] for p in brv.derive_predicates(block_from(md, title)))


# ---------- the compiled document the retired predicates were about ----------
# Two of this file's mechanisms - the GitHub-account table and the closing
# summary - are rules whose bespoke prose predicates were retired. A checks file
# is the only thing that can reach a hard verdict on either now, so their cases
# are driven through the worked example, which carries one beside it.

WORKED_EXAMPLE = Path(__file__).parent / "fixtures" / "global_rules.md"
WORKED_CHECKS = WORKED_EXAMPLE.with_name(WORKED_EXAMPLE.name + ".checks.json")
WORKED_MD = WORKED_EXAMPLE.read_text()

GH_RULE = "GitHub account per project"
EOM_RULE = "End-of-implementation summary"

FORMIC_CWD = "/Users/dev/Git/formic-core"


def compiled_verdict(title, events, prompt, cwd=FORMIC_CWD):
    """One block of the worked example, with its reviewed checks file live."""
    rc.checks_for_doc.cache_clear()
    file = {"loaded": True, "kind": "global", "path": str(WORKED_EXAMPLE),
            "abs_path": str(WORKED_EXAMPLE), "name": None}
    return brv.assess_block(block_from(WORKED_MD, title), file,
                            trace_for(with_cwd(events, cwd), prompt))


def compiled_session(tmp_path, monkeypatch, events):
    """The worked example as the project's own CLAUDE.md, baked session-wide.

    `HOME` and the skills directory are redirected, or the real machine's own
    global CLAUDE.md is loaded too - and it carries a rule with this same
    heading, so the block the assertions find would depend on whose laptop the
    suite runs on.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(brv, "DEFAULT_PLUGIN_CACHE_DIR", tmp_path / "no-plugins")
    (tmp_path / "CLAUDE.md").write_text(WORKED_MD)
    (tmp_path / "CLAUDE.md.checks.json").write_text(WORKED_CHECKS.read_text())
    p = _write_jsonl(tmp_path, with_cwd(events, str(tmp_path)))
    monkeypatch.chdir(tmp_path)
    rc.checks_for_doc.cache_clear()

    class _CompiledArgs(_Args):
        skills_dir = tmp_path / "no-skills-here"

    return brv.process_session(p, _CompiledArgs())[1]


def gh_block(scope):
    """The path-table block of a baked scope - session or turn."""
    project = next(f for f in scope["contextFiles"] if f["kind"] == "project")
    return next(b for b in project["blocks"] if b["title"] == GH_RULE)


# ---------- F-TRIGGER: `/implement-plan` fires on `/implement-plan-workflow` ----------
# Anchor: famigo 9dd3cc8a / ...claude-md-11-implement-plan / used. Same in
# 0cfa1aa9, formic-core 39b9e09e turn-29, reband 113a0d2c turn-14,
# agent-context-ide 9584a785 turn-5.

TRIGGER_POINTER_MD = """# implement-plan

- **implement-plan** (`~/.claude/skills/implement-plan/SKILL.md`) - orchestrate a
  multi-phase implementation plan. Trigger: `/implement-plan`
"""

SIBLING_PROMPT = "/implement-plan-workflow with the plan below"


def test_f_trigger_sibling_skill_name_does_not_satisfy_the_shorter_trigger():
    v = verdict(TRIGGER_POINTER_MD,
                [user_text(SIBLING_PROMPT, 1), assistant_text("Starting phase 1.", 2)],
                prompt=SIBLING_PROMPT)
    assert v["status"] != "used"


def test_f_trigger_verdict_never_contradicts_its_own_moment_card():
    """`used` printed above "[no] `/implement-plan` not invoked this run"."""
    v = verdict(TRIGGER_POINTER_MD,
                [user_text(SIBLING_PROMPT, 1), assistant_text("Starting phase 1.", 2)],
                prompt=SIBLING_PROMPT)
    denials = [m for m in v["moments"]
               if m["verdict"] == "no" and "not invoked" in m["label"]]
    assert not (v["status"] == "used" and denials)


def test_f_trigger_predicate_agrees_with_the_bounded_matcher():
    """One matcher, or the page and the CLI can disagree about the same prompt."""
    pred = next(p for p in brv.derive_predicates(block_from(TRIGGER_POINTER_MD))
                if p["kind"] == "trigger")
    trace = trace_for([user_text(SIBLING_PROMPT, 1)], SIBLING_PROMPT)
    assert pred["matches"](trace) == brv._is_triggered("implement-plan", SIBLING_PROMPT)


# ---------- F-TRIGGER-MENTION: an offered command is not an invoked one ----------
# Anchor: formic-core afe37732 turn-9. The prompt offered a choice between two
# skills and ran neither; both pointer blocks scored `used` off the trigger
# predicate while `skill-invocation` on the same records refused them.

CHOICE_PROMPT = ("write the requirements down first - either /grill-prd or "
                 "/prd-to-plan, you choose which fits")

GRILL_PRD_MD = """# grill-prd

- **grill-prd** (`~/.claude/skills/grill-prd/SKILL.md`) - interview the user
  about a plan, then write the PRD. Trigger: `/grill-prd`
"""

PRD_TO_PLAN_MD = """# prd-to-plan

- **prd-to-plan** (`~/.claude/skills/prd-to-plan/SKILL.md`) - turn a PRD into a
  phased implementation plan. Trigger: `/prd-to-plan`
"""


@pytest.mark.parametrize("md", [GRILL_PRD_MD, PRD_TO_PLAN_MD])
def test_f_trigger_an_offered_command_never_greens_its_pointer(md):
    events = [user_text(CHOICE_PROMPT, 1),
              assistant_text("I'll write the requirements down.", 2)]
    v = verdict(md, events, prompt=CHOICE_PROMPT)
    assert v["status"] == "dormant"
    assert not [m for m in v["moments"] if m["kind"] == "trigger"]


@pytest.mark.parametrize("events", [
    [user_slash("grill-prd", "the plan", 1), assistant_text("On it.", 2)],
    [user_text("write the requirements down", 1),
     assistant_tool_use("Skill", {"skill": "grill-prd"}, 2),
     assistant_text("On it.", 3)],
])
def test_counter_anchor_either_invocation_record_still_greens_the_pointer(events):
    """The two records the demotion must leave alone: the wrapper and the call."""
    v = verdict(GRILL_PRD_MD, events, prompt=brv.first_real_user_prompt(events))
    assert v["status"] == "used"
    assert [m for m in v["moments"] if m["kind"] == "trigger" and m["verdict"] == "yes"]


# ---------- F-PATHTABLE: the path-table predicate is wrong in both directions ----------
# Anchors: formicHMI 8fd8526c (false green, matched `git log --author="bionanek-x"`),
# formicHMI 12f48cdb + formic-core 4ebe50c0 + agent-context-ide d5c3cc1a (false red,
# the switch ran verbatim), reband 113a0d2c + formic-core 39b9e09e/1b395e0b (false
# red, status checked and the account was already correct).

def test_f_pathtable_row_token_inside_an_unrelated_command_is_not_compliance():
    """The account name in the table's second column matched a `git` flag.

    The compiled check asks the tool log whether a `gh` command ran at all, so
    a session that never ran one never triggered the rule - and nothing may
    cite the `git log` as if it had.
    """
    v = compiled_verdict(GH_RULE,
                         [user_text("what did I ship today", 1),
                          bash('git log --author="bionanek-x" --oneline', 2),
                          assistant_text("Here is today's work.", 3)],
                         "what did I ship today")
    assert v["ruleCheck"]["state"] == "not-exercised"
    assert v["status"] == "dormant", v["reason"]
    findings = v["ruleCheck"]["findings"]
    assert [f["stage"] for f in findings] == [rc.STAGE_ANTECEDENT], findings
    # An antecedent that never fired is the one finding with nothing to cite.
    # Pointing at some other call - the `git log`, here - would put a citation
    # under a claim no call supports, which is the anchor itself.
    assert findings[0]["line"] == 0 and findings[0]["match"] == "", findings


def test_f_pathtable_status_checked_and_already_correct_is_compliance():
    """The rule says switch *if needed*; nothing needed switching here."""
    v = compiled_verdict(GH_RULE,
                         [user_text("open a PR", 1),
                          bash("gh auth status", 2, tool_id="b1"),
                          bash("gh pr create --fill", 3, tool_id="b2"),
                          assistant_text("PR opened.", 4)],
                         "open a PR")
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] == "used", v["reason"]
    # The card the reader sees says compliance, and names the check that said
    # so. The predicate scored this session `ignored` and cited the very
    # `gh auth status` the rule demanded, so the card is half the anchor.
    cards = [m for m in v["moments"] if m["kind"] in ("compliance", "violation")]
    assert [(m["kind"], m["verdict"]) for m in cards] == [("compliance", "yes")]
    assert "gh-auth-before-gh" in cards[0]["label"]


def test_f_pathtable_the_prescribed_switch_running_verbatim_is_compliance():
    v = compiled_verdict(GH_RULE,
                         [user_text("open a PR", 1),
                          bash("gh auth switch -u bionanek-x", 2, tool_id="b1"),
                          bash("gh pr create --fill", 3, tool_id="b2")],
                         "open a PR")
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] == "used", v["reason"]


def test_f_pathtable_no_gh_activity_at_all_is_not_exercised_not_ignored():
    """A rule whose trigger never came up is dormant, and says why in as many
    words: `clear` would read as "the rule was followed"."""
    v = compiled_verdict(GH_RULE,
                         [user_text("count the files", 1),
                          bash("ls -la src", 2),
                          assistant_text("There are 12 files.", 3)],
                         "count the files")
    assert v["ruleCheck"]["state"] == "not-exercised"
    assert v["status"] == "dormant", v["reason"]
    assert "never did the kind of thing this rule governs" in v["reason"]


def test_f_pathtable_a_gh_command_with_no_prior_check_is_a_cited_violation():
    """The red path, exercised: without it every case above is a green nobody
    could have flipped, and "no false reds" would measure nothing."""
    v = compiled_verdict(GH_RULE,
                         [user_text("open a PR", 1),
                          bash("gh pr create --fill", 2)],
                         "open a PR")
    assert v["status"] == "ignored", v["reason"]
    finding = next(f for f in v["ruleCheck"]["findings"] if f["state"] == "violated")
    assert finding["checkId"] == "gh-auth-before-gh"
    assert "gh pr" in finding["match"]
    assert finding["path"] == "(tools)" and finding["line"] == 1
    # One card, and it condemns: nothing may excuse a block the status condemns.
    cards = [m for m in v["moments"] if m["kind"] in ("compliance", "violation")]
    assert [(m["kind"], m["verdict"]) for m in cards] == [("violation", "no")]


def test_f_pathtable_row_path_token_is_not_a_shell_command():
    """`mkdir formic-x` is not evidence about a GitHub-account rule.

    Exact on both halves: the block harvests no command at all, and a run whose
    only call names a table row is a rule nothing triggered. A negation over
    two names would pass with any third table cell harvested.
    """
    assert mention_cmds(WORKED_MD, GH_RULE) == []
    v = compiled_verdict(GH_RULE,
                         [user_text("make the dir", 1),
                          bash("mkdir formic-x", 2),
                          assistant_text("Done.", 3)],
                         "make the dir")
    assert v["ruleCheck"]["state"] == "not-exercised"
    assert v["status"] == "dormant", v["reason"]


# ---------- F-COMBINE: one mis-scored turn paints the session ----------
# Anchors: formic-core 4ebe50c0 (turn 0 `used`, session `ignored`), and every
# multi-turn session inspected.

COMPLIANT_THEN_UNRELATED = [
    user_text("open a PR", 1),
    bash("gh auth status", 2, tool_id="b1"),
    bash("gh pr create --fill", 3, tool_id="b2"),
    assistant_text("PR opened.", 4),
    user_text("now count the files", 5),
    bash("ls -la src", 6, tool_id="b3"),
    assistant_text("There are 12 files.", 7),
]

VIOLATING_THEN_COMPLIANT = [
    user_text("open a PR", 1),
    bash("gh pr create --fill", 2, tool_id="b1"),
    assistant_text("PR opened.", 3),
    user_text("list the PRs", 4),
    bash("gh auth status", 5, tool_id="b2"),
    bash("gh pr list", 6, tool_id="b3"),
    assistant_text("Three are open.", 7),
]


def test_f_combine_an_unexercised_turn_does_not_paint_the_session_red(
        tmp_path, monkeypatch):
    """Turn 1 never runs `gh`, so it has nothing to say about the rule.

    The retired predicate scored it `ignored` on the cwd alone, and `ignored`
    then outranked turn 0's `used` at session scope.
    """
    per_session = compiled_session(tmp_path, monkeypatch, COMPLIANT_THEN_UNRELATED)
    assert gh_block(per_session)["status"] == "used"
    assert [gh_block(t)["status"] for t in per_session["turns"]] == ["used", "dormant"]


def test_f_combine_one_violating_turn_does_not_condemn_the_session(
        tmp_path, monkeypatch):
    """`ignored` at session scope has to mean "satisfied nowhere"."""
    per_session = compiled_session(tmp_path, monkeypatch, VIOLATING_THEN_COMPLIANT)
    assert [gh_block(t)["status"] for t in per_session["turns"]] == ["ignored", "used"]
    assert gh_block(per_session)["status"] == "used-partial"


def test_f_combine_session_status_and_reason_describe_the_same_reality(
        tmp_path, monkeypatch):
    """The aggregate assesses itself; the combine rule can overrule it.

    One real record read status `ignored` above the reason "1 predicate(s)
    applied and were satisfied" - three realities in one row - so the reason
    has to be regenerated from the combined status wherever the two part.
    """
    block = gh_block(compiled_session(tmp_path, monkeypatch, VIOLATING_THEN_COMPLIANT))
    assert block["status"] == "used-partial"
    assert "1 used, 1 ignored" in block["reason"], block["reason"]


# ---------- F-EOM: the end-of-message heuristic red-flags real compliance ----------
# Anchors: famigo 9dd3cc8a (`.sh` filename five paragraphs earlier), reband
# 22c58939, formicHMI 8e62abcd, formic-core 4ebe50c0 (doc-only Write), famigo
# 5448a718 (heredoc edits invisible).

# The same rule as the worked example's, standing alone in a document nobody
# has compiled - the other half of the pair the counter-anchor below asserts.
EOM_ONLY_MD = """## End-of-implementation summary

After implementing any code change (bug fix, feature, refactor, or anything that
modifies behavior), always end your response with a brief **user-facing summary**:
what changed from the user's perspective. Keep it to 1-3 sentences. Focus on
observable behavior, not technical details.
"""

COMPLIANT_TAIL = ("You can now sign in with a magic link instead of a password. "
                  "The old password form still works for existing accounts. "
                  "Nothing else about the flow changed.")

TECH_MENTION_EARLY = (
    "I traced the failure to the seed step and rewrote it.\n\n"
    "The seeding is driven by setup_local_db.sh, which was re-running the "
    "migrations in the wrong order.\n\n"
    "I reordered the calls and re-ran the suite.\n\n"
    "Everything passes now.\n\n"
    + COMPLIANT_TAIL
)


# Every trace shape the anchors are about, each one a turn whose wording the
# retired heuristic judged. The rule is about the *meaning* of a closing
# paragraph, which is why its compiled record sits in the `judged` bucket - and
# what these cases hold is that no shape of work, and no shape of prose, moves
# a rule nobody can check offline.
EOM_TRACES = [
    # famigo 9dd3cc8a: a `.sh` filename five paragraphs before a compliant tail.
    ("tech detail earlier in the message", "fix the seeding",
     [user_text("fix the seeding", 1),
      assistant_tool_use("Edit", {"file_path": "/tmp/seed.ts",
                                  "old_string": "a", "new_string": "b"}, 2),
      assistant_text(TECH_MENTION_EARLY, 3)]),
    # formic-core 4ebe50c0: the task was about a document, so the summary names it.
    ("the summary names the doc the task was about", "tidy up CLAUDE.md",
     [user_text("tidy up CLAUDE.md", 1),
      assistant_tool_use("Edit", {"file_path": "/tmp/CLAUDE.md",
                                  "old_string": "a", "new_string": "b"}, 2),
      assistant_text("CLAUDE.md now says what the tool actually does. "
                     "The stale line numbers are gone. Nothing else moved.", 3)]),
    # famigo 5448a718: the whole session edited through heredocs.
    ("heredoc edits", "ship the feature",
     [user_text("ship the feature", 1),
      bash("cat > src/api/auth.ts <<'EOF'\nexport const x = 1;\nEOF", 2),
      bash("git commit -am 'add auth'", 3, tool_id="b2"),
      assistant_text(COMPLIANT_TAIL, 4)]),
    ("tee writes", "add the endpoint",
     [user_text("add the endpoint", 1),
      bash("tee src/api/health.ts <<'EOF'\nexport const ok = 1;\nEOF", 2),
      assistant_text(COMPLIANT_TAIL, 3)]),
    # formic-core 4ebe50c0: a doc-only Write is not a code change.
    ("a doc-only write", "write the plan",
     [user_text("write the plan", 1),
      assistant_tool_use("Write", {"file_path": "/tmp/plans/phase-1.md",
                                   "content": "# Phase 1\n"}, 2),
      assistant_text("Phase 1 covers the parser rewrite, phase 2 the renderer. "
                     "The plan lives in plans/phase-1.md and lists the "
                     "acceptance criteria per phase.", 3)]),
    ("a turn that ends in a question", "start on the migration",
     [user_text("start on the migration", 1),
      assistant_tool_use("Edit", {"file_path": "/tmp/db.ts",
                                  "old_string": "a", "new_string": "b"}, 2),
      assistant_text("I moved the first table across. The second one has a "
                     "foreign key into the legacy schema.\n\n"
                     "Do you want me to drop that column or migrate it?", 3)]),
    ("a summary that names the doc it just wrote", "add retries and document them",
     [user_text("add retries and document them", 1),
      assistant_tool_use("Edit", {"file_path": "/p/parser.ts",
                                  "old_string": "a", "new_string": "b"}, 2),
      assistant_tool_use("Edit", {"file_path": "/p/README.md",
                                  "old_string": "a", "new_string": "b"}, 3),
      assistant_text("Failed uploads now retry on their own. "
                     "I documented the new behaviour in README.md.", 4)]),
    ("a turn with no closing message at all", "start the refactor",
     [user_text("start the refactor", 1),
      assistant_tool_use("Edit", {"file_path": "/p/a.ts",
                                  "old_string": "a", "new_string": "b"}, 2)]),
    # reband 22c58939 / formicHMI 8e62abcd: nothing was implemented at all.
    ("no edits at all", "what do you think of this design",
     [user_text("what do you think of this design", 1),
      assistant_text("It is sound; the cache boundary is the risk.", 2)]),
]


@pytest.mark.parametrize("tag,prompt,events",
                         EOM_TRACES, ids=[t[0] for t in EOM_TRACES])
def test_f_eom_no_trace_shape_moves_a_rule_parked_for_the_judge(tag, prompt, events):
    """The compiled answer for a rule about meaning, held against every anchor.

    Its checkable half is a sentence count; the half that matters ("observable
    behaviour, not technical details") is a judgement, so the compile step
    parks it in the `judged` bucket and the offline tool reports it unchecked.
    The retired predicate answered anyway, and red-flagged each of these.

    The state is asserted exactly rather than as "not ignored": the record
    being parked is the whole finding, and a case that only denied a red would
    pass just as well if the checks file had never loaded. That it *can* still
    load and accuse on this same document is
    `test_f_pathtable_a_gh_command_with_no_prior_check_is_a_cited_violation`.
    """
    v = compiled_verdict(EOM_RULE, events, prompt)
    assert v["status"] == "unused", (tag, v["reason"])
    assert v["ruleCheck"]["state"] == "not-checkable", tag
    parked = v["ruleCheck"]["judged"]
    assert [j["id"] for j in parked] == ["closing-summary-shape"], tag
    assert parked[0]["bucket"] == "judged", tag
    # Nothing narrates it either: the only card is the lexical tier's non-event.
    # A causal card here would be a story about a rule nothing checked.
    assert [m["kind"] for m in v["moments"]] == ["non-event"], v["moments"]


@pytest.mark.parametrize("cmd", [
    "python3 - <<'PY'\nprint(1)\nPY > /tmp/out.json",
    "yarn build 2>&1 | tee build.log",
])
def test_counter_anchor_eom_captured_output_is_not_a_code_change(cmd):
    """A redirect is far more often captured output than a file being authored.

    Counting one exercised a rule about summarising code changes in a turn that
    changed nothing, and the turn was then judged on its wording. The
    response-shape predicate is retired, so the distinction now decides the
    structural predicates rather than this rule's status, and is asserted
    directly alongside the exact status the block does reach.
    """
    assert brv._shell_write_targets(cmd) == []
    events = [user_text("check the build", 1), bash(cmd, 2),
              assistant_text("Build is green.", 3)]
    v = compiled_verdict(EOM_RULE, events, "check the build")
    assert v["status"] == "unused", v["reason"]
    assert v["ruleCheck"]["state"] == "not-checkable"
    assert [j["id"] for j in v["ruleCheck"]["judged"]] == ["closing-summary-shape"]
    assert "A rule can be followed in silence" in v["reason"]


def test_counter_anchor_eom_an_uncompiled_copy_asks_to_be_compiled(tmp_path):
    """The same rule with no checks file beside it: honest, and actionable.

    `refused` and `uncompiled` are different facts - one is an answer the
    compiler gave, the other is a question nobody has asked - and only the
    second carries the command that closes the gap.

    The document goes in `tmp_path` rather than the shared `/tmp/CLAUDE.md` the
    other helpers use, because "no checks file beside it" is the premise: a
    stray `/tmp/CLAUDE.md.checks.json` on somebody's machine would answer the
    question this case is about.
    """
    doc = tmp_path / "CLAUDE.md"
    doc.write_text(EOM_ONLY_MD)
    rc.checks_for_doc.cache_clear()
    v = verdict(EOM_ONLY_MD,
                [user_text("what do you think of this design", 1),
                 assistant_text("It is sound; the cache boundary is the risk.", 2)],
                prompt="what do you think of this design",
                file=dict(rule_file(), path=str(doc), abs_path=str(doc)))
    assert v["status"] == "unused", v["reason"]
    assert v["ruleCheck"]["judged"] == []
    assert rc.COMPILE_COMMAND in v["ruleCheck"]["hint"]


# ---------- F-CMDMENTION: command harvesting explodes on dense docs ----------
# Anchor: famigo 5448a718 / ...famigo-claude-md-4-quality-gate-mandatory /
# possibly-referenced on `at`/`from`/`runs` while 21 real `yarn type-check` runs
# stayed invisible.

QUALITY_GATE_MD = """## Quality gate (mandatory)

Before you report a task done, the gate `runs` `from` the repo root. Anything
that fails `at` this step blocks the handoff:

```bash
yarn type-check && yarn lint && yarn test
```

Nothing skips it.
"""

CLIPBOARD_MD = """## Copy to clipboard

When copying any text to the clipboard, always pipe it through `printf` so the
terminal's trailing newline is stripped.

```bash
# wrong
echo "$content" | pbcopy
```
"""


def test_f_cmdmention_english_words_are_not_shell_commands():
    cmds = mention_cmds(QUALITY_GATE_MD)
    assert not ({"at", "from", "runs"} & set(cmds)), cmds


def test_f_cmdmention_a_fence_language_is_not_a_command():
    assert "bash" not in mention_cmds(QUALITY_GATE_MD)


def test_f_cmdmention_the_real_fenced_command_is_extracted():
    events = [user_text("finish the task", 1),
              bash("yarn type-check && yarn lint && yarn test", 2),
              assistant_text("Gate is green.", 3)]
    v = verdict(QUALITY_GATE_MD, events, prompt="finish the task")
    haystack = " ".join(e["label"] + " " + e["text"] for e in v["evidence"])
    assert "yarn type-check" in haystack


PAYLOAD_KEYS_MD = """## Architecture

Each agent record carries `id`, `type`, `name`, `data` and `status`, and the
turn rows are walked `in` order `at` build time.
"""


def test_f_cmdmention_payload_keys_are_not_shell_commands():
    cmds = set(mention_cmds(PAYLOAD_KEYS_MD))
    assert not ({"data", "type", "name", "status"} & cmds), sorted(cmds)


def test_f_cmdmention_short_tokens_derive_no_predicate():
    cmds = set(mention_cmds(PAYLOAD_KEYS_MD))
    assert not ({"id", "in", "at"} & cmds), sorted(cmds)


def test_f_cmdmention_a_command_only_in_the_blocks_own_example_is_not_harvested():
    """`echo` appears here as the thing the rule forbids, in an example."""
    assert "echo" not in mention_cmds(CLIPBOARD_MD)


# ---------- F-BLINDSPOT: demonstrable compliance invisible, and actively denied ----------
# Anchors: famigo 5448a718 error-memory + decision-memory, reband 22c58939
# decision-memory, formic-core 39b9e09e prd-to-plan template blocks 2-5 and the
# palletizer-hmi AGENTS.md "Commands" block, formicHMI 8e62abcd create-pr blocks.

ERROR_MEMORY_MD = """## Error Memory

When an approach turns out to be wrong in direction, log it before ending the
session. Universal failures go to `~/.claude/ERRORS.md`; stack-specific ones to
the project's own memory directory.

Entry format:

    ## [YYYY-MM-DD] Short title
    **What failed:** the approach and why it seemed reasonable
    **What worked:** the replacement approach
"""

DECISION_TEMPLATE_MD = """## Decision log entry

Append one entry per significant decision, in this exact shape:

    ## [YYYY-MM-DD] Short title
    **Decided:** what was chosen
    **Why:** the reason
    **Rejected:** alternatives and why they were dropped
"""

AGENTS_COMMANDS_MD = """## Commands

Run these from the workspace root:

```bash
just palletizer-hmi-lint
yarn test
```

If the dev server is already running on :8088, do not start a second one.
"""

CREATE_PR_SKILL_MD = """# create-pr

Open a GitHub pull request that matches the repository's existing style: the
right account, a description synthesised from the last five pull requests,
screenshots when the convention wants them, and CI checks watched after opening.
"""


# Both F-BLINDSPOT path cases below were written against a plain rule document,
# and a later blind audit falsified that form of them: a filename lifted out of
# prose carries no direction, so a reband "Gotchas" note *warning* that
# `app.json` does not propagate was credited by an edit to `app.json`, and a
# famigo "read `.cursor/PROJECT.md`" step by a commit turn that edited that file
# and never read it. The blindspot these cases exist for is still real, so each
# keeps its run and asserts it twice: the join still sees what the agent did
# inside a document the harness recorded as running, and is honestly quiet on
# the same run against a rule document nothing invoked.

def _memory_skill(md):
    """The same rules, delivered as a `/memlog` command the session invoked."""
    return rule_file(kind="command", name="memlog",
                     path="commands/memlog.md", md=md)


def _invocation(i=0):
    return assistant_tool_use("Skill", {"skill": "memlog"}, i, tool_id="s1")


def test_f_blindspot_writing_to_the_exact_file_the_rule_names_is_not_denied():
    # The tool input carries an absolute path while the rule names a tilde one,
    # which is the whole join problem - so the absolute side is expanded here
    # rather than hardcoded, or the join can only ever work on one machine.
    errors_md = str(Path.home() / ".claude" / "ERRORS.md")
    events = [user_text("wrap up the session", 1),
              bash("tail -20 ~/.claude/ERRORS.md", 2),
              assistant_tool_use(
                  "Edit",
                  {"file_path": errors_md,
                   "old_string": "",
                   "new_string": "## [2026-01-01] Wrong root cause\n"
                                 "**What failed:** patching the view layer\n"
                                 "**What worked:** fixing the loader\n"},
                  3, tool_id="e1"),
              assistant_text("Logged the wrong-direction approach to ERRORS.md.", 4)]
    ran = [events[0], _invocation(1)] + events[1:]
    v = verdict(ERROR_MEMORY_MD, ran, prompt="/memlog wrap up the session",
                file=_memory_skill(ERROR_MEMORY_MD))
    assert "coincidence" not in v["reason"].lower()
    assert v["status"] not in ("unused", "possibly-referenced")
    # The same write, under a rule document nothing invoked, credits nothing.
    quiet = verdict(ERROR_MEMORY_MD, events, prompt="wrap up the session")
    assert quiet["status"] not in ("used", "used-partial", "ignored")


def test_f_blindspot_a_template_reproduced_in_written_content_is_visible():
    written = ("## [2026-01-01] Bake the rollup in Python\n"
               "**Decided:** compute every rollup in Python and bake it\n"
               "**Why:** the CLI and the page must not disagree\n"
               "**Rejected:** deriving it in JavaScript\n")
    events = [user_text("write up the decision", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/DECISIONS.md",
                                           "content": written}, 2),
              assistant_text("Done.", 3)]
    ran = [events[0], _invocation(1)] + events[1:]
    v = verdict(DECISION_TEMPLATE_MD, ran, prompt="/memlog write up the decision",
                file=_memory_skill(DECISION_TEMPLATE_MD))
    assert v["status"] == "used"
    quiet = verdict(DECISION_TEMPLATE_MD, events, prompt="write up the decision")
    assert quiet["status"] not in ("used", "used-partial", "ignored")


def test_f_blindspot_an_executed_skill_call_is_not_scored_unused():
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1"),
              bash("gh auth status", 3, tool_id="b1"),
              bash("gh pr create --fill", 4, tool_id="b2"),
              assistant_text("PR is open and CI is green.", 5)]
    v = verdict(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                file=rule_file(kind="skill", name="create-pr",
                               path="skills/create-pr/SKILL.md",
                               md=CREATE_PR_SKILL_MD))
    assert v["status"] not in ("unused", "possibly-referenced", "dormant")


def test_f_blindspot_a_commands_block_whose_commands_all_ran_is_not_dormant():
    events = [user_text("lint and test it", 1),
              bash("just palletizer-hmi-lint", 2, tool_id="b1"),
              bash("yarn test", 3, tool_id="b2"),
              assistant_text("Lint and tests pass.", 4)]
    v = verdict(AGENTS_COMMANDS_MD, events, prompt="lint and test it",
                file=rule_file(kind="project", path="AGENTS.md"))
    assert v["status"] not in ("dormant", "unused")


# ---------- F-MOMENTS: causal narrative built from coincidence ----------
# Anchor: famigo turn-0 / figma-workflow "Tech Stack" table / possibly-referenced
# on 5/8 keywords, citing an unrelated Effect-vs-react-query discussion.

TECH_STACK_MD = """## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | TypeScript |
| Runtime | React Native |
| Styling | Tailwind |
"""

UNRELATED_STACK_TALK = (
    "I'll compare Effect with react-query here. Effect gives typed errors in "
    "TypeScript, and React Native does not change that calculus. The Tailwind "
    "config is untouched either way."
)


def test_f_moments_keyword_only_evidence_gets_no_causal_narrative():
    events = [user_text("effect or react-query", 1),
              assistant_text(UNRELATED_STACK_TALK, 2)]
    v = verdict(TECH_STACK_MD, events, prompt="effect or react-query")
    causal = [m for m in v["moments"] if m["kind"] in ("intent", "trigger", "action")]
    assert not causal, [m["label"] for m in causal]


# ---------- F-MISC ----------
# Anchors: this repo's own Architecture section (documentation examples become
# live predicates), reband 22c58939 grill-prd + prd-to-plan (invoked
# listing-only skills render not-loaded), block ids beginning with `-`.

DOC_ABOUT_TRIGGERS_MD = """## Conventions specific to this codebase

Predicate extraction pulls structured triggers out of prose. A skill pointer
carries a line like `Trigger: /foo`, and a registration block says "When the
user types `/x`" - both become predicates. Documentation *about* that shape is
not itself a rule.
"""


def test_f_misc_documentation_examples_derive_no_trigger_predicate():
    assert "trigger" not in predicate_kinds(DOC_ABOUT_TRIGGERS_MD)


UNBALANCED_QUOTE_MD = '''# skill-x

He said "one thing and never closed the quote.

- **x** (`~/.claude/skills/x/SKILL.md`) - does a thing. Trigger: `/x`
''' + 'padding "quoted" text ' * 20


def test_counter_anchor_a_stray_quote_does_not_delete_a_real_trigger():
    """Losing a declaration is a worse error than reading a doc example.

    The quoted-example filter pairs `"` characters, so one unbalanced quote
    could otherwise reach forward into a later paragraph and swallow the
    `Trigger:` line inside its span.
    """
    pred = [p["cmd"] for p in brv.derive_predicates(block_from(UNBALANCED_QUOTE_MD))
            if p["kind"] == "trigger"]
    assert pred == ["/x"]


# 22 `a`s is the shortest path whose slug tail begins on a separator; the tail
# slice in `file_slug` is taken after the strip, so the hyphen survives.
LEADING_HYPHEN_PATH = "/Users/u/Git/" + "a" * 22 + "/rules/x.md"


def test_f_misc_a_block_id_really_can_begin_with_a_hyphen():
    """Premise check for the next case - `file_slug` slices after stripping."""
    assert brv.file_slug(LEADING_HYPHEN_PATH).startswith("-")


def test_f_misc_a_leading_hyphen_block_id_is_addressable(monkeypatch):
    block_id = f"{brv.file_slug(LEADING_HYPHEN_PATH)}-0-quality-gate"
    monkeypatch.setattr("sys.argv",
                        ["build_real_view.py", "--query", "abc12345", block_id])
    args = brv.parse_args()
    assert args.query == ["abc12345", block_id]


TRIGGER_IN_SECOND_TURN_MD = """# standup

- **standup** (`~/.claude/skills/standup/SKILL.md`) - scan today's git activity
  and draft the Slack update. Trigger: `/standup`
"""


def test_f_misc_a_session_status_is_never_printed_above_another_status_reason(
        tmp_path, monkeypatch):
    """The aggregate is assessed session-wide, the status is combined per turn.

    The aggregate trace carries only the session's *first* prompt, so a trigger
    typed in a later turn leaves the aggregate with nothing but keyword overlap
    while the combine rule reads `used` off the turn that fired - which is how
    a green badge came to sit above "Weak evidence only".
    """
    (tmp_path / "CLAUDE.md").write_text(TRIGGER_IN_SECOND_TURN_MD)
    p = _write_jsonl(tmp_path, [
        user_text("bump the version", 1),
        assistant_text("Bumped to 1.4.2.", 2),
        user_slash("standup", "", 3),
        assistant_text("Here is today's update.", 4),
    ])
    monkeypatch.chdir(tmp_path)
    _, per_session = brv.process_session(p, _Args())
    project = next(f for f in per_session["contextFiles"] if f["kind"] == "project")
    block = project["blocks"][0]
    assert block["status"] == "used"
    assert "weak evidence" not in block["reason"].lower(), block["reason"]
    assert "no predicate derivable" not in block["reason"].lower(), block["reason"]


def skill_listing(lines, i):
    return {"type": "attachment", "timestamp": _ts(i),
            "attachment": {"type": "skill_listing", "skillCount": len(lines),
                           "content": "\n".join(lines)}}


def test_f_misc_a_listing_only_skill_invoked_in_a_later_turn_is_loaded(tmp_path, monkeypatch):
    """The session-scope path: the listing arrives once, the skill later.

    A skill with no SKILL.md exists only in the harness's listing, so before
    the listing was lifted to the session it appeared in the payload of the one
    turn carrying that attachment - turn 0, before it was invoked - and the
    per-turn combine then reported a skill that drove the rest of the session
    as never loaded.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(brv, "DEFAULT_PLUGIN_CACHE_DIR", tmp_path / "no-plugins")
    (tmp_path / "CLAUDE.md").write_text(HEADER_PROSE_MD)
    p = _write_jsonl(tmp_path, [
        skill_listing(["- grill-prd: Interview then write a PRD."], 0),
        user_text("what do you think of this design", 1),
        assistant_text("It is sound.", 2),
        user_slash("grill-prd", "", 3),
        assistant_text("Starting the interview.", 4),
    ])
    monkeypatch.chdir(tmp_path)

    class _ListingArgs(_Args):
        skills_dir = tmp_path / "no-skills-here"

    _, per_session = brv.process_session(p, _ListingArgs())
    f = next(x for x in per_session["contextFiles"] if x.get("source") == "listing-only")
    assert f["blocks"][0]["status"] != "not-loaded", f["blocks"][0]["reason"]


def test_f_misc_an_invoked_listing_only_skill_is_not_reported_not_loaded(tmp_path, monkeypatch):
    """No SKILL.md on disk is a lookup failure, not evidence it never ran."""
    # Both lookup roots are redirected, or whether this skill resolves depends
    # on what the machine running the tests happens to have installed.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(brv, "DEFAULT_PLUGIN_CACHE_DIR", tmp_path / "no-plugins")

    class _SkillArgs:
        skills_dir = tmp_path / "no-skills-here"

    events = [skill_listing(["- grill-prd: Interview then write a PRD."], 0),
              user_slash("grill-prd", "", 1),
              assistant_text("Starting the interview.", 2)]
    files = brv.load_context_files(events, brv.tool_calls(events), str(tmp_path),
                                   _SkillArgs, "/grill-prd")
    f = next(x for x in files if x.get("source") == "listing-only")
    v = brv.assess_block(f["blocks"][0], f, trace_for(events, "/grill-prd"))
    assert v["status"] != "not-loaded"


# ---------- counter-anchors: the verdicts that were right ----------

STANDUP_MD = """# standup

- **standup** (`~/.claude/skills/standup/SKILL.md`) - scan today's git activity
  and draft the Slack update. Trigger: `/standup`
"""

PR_COMMENTS_MD = """# pr-comments

- **pr-comments** (`~/.claude/skills/pr-comments/SKILL.md`) - fetch unresolved PR
  review comments and triage them. Trigger: `/pr-comments`
"""

HEADER_PROSE_MD = """## How to talk to me

Answer first, in one plain sentence. Keep it short unless depth is asked for.
"""


@pytest.mark.parametrize("md,name,args", [
    (STANDUP_MD, "standup", ""),
    (PR_COMMENTS_MD, "pr-comments", "for this branch"),
])
def test_counter_anchor_clean_slash_trigger_is_used(md, name, args):
    """The record a typed slash command really leaves is the wrapper.

    Phase 2 demoted the bare `/name` mention this case used to stand in with,
    so the anchor is driven through the harness record it always described.
    """
    events = [user_slash(name, args, 1), assistant_text("On it.", 2)]
    prompt = brv.first_real_user_prompt(events)
    assert verdict(md, events, prompt=prompt)["status"] == "used"


@pytest.mark.parametrize("md,mention", [
    (STANDUP_MD, "/standup"),
    (PR_COMMENTS_MD, "/pr-comments"),
])
def test_f_trigger_a_mentioned_but_uninvoked_command_is_dormant(md, mention):
    """F5: "either /grill-prd or /prd-to-plan - you choose" greened both."""
    prompt = f"either {mention} or something else - you choose"
    events = [user_text(prompt, 1), assistant_text("On it.", 2)]
    assert verdict(md, events, prompt=prompt)["status"] == "dormant"


def test_counter_anchor_untriggered_trigger_block_is_dormant():
    events = [user_text("just fix the test", 1), assistant_text("Fixed.", 2)]
    assert verdict(STANDUP_MD, events, prompt="just fix the test")["status"] == "dormant"


def test_counter_anchor_a_header_prose_block_with_no_overlap_is_unused():
    events = [user_text("bump the version", 1),
              assistant_text("Bumped to 1.4.2.", 2)]
    assert verdict(HEADER_PROSE_MD, events, prompt="bump the version")["status"] == "unused"


def test_counter_anchor_an_uninvoked_skill_file_is_not_loaded():
    events = [user_text("just fix the test", 1)]
    v = verdict(STANDUP_MD, events, prompt="just fix the test",
                file=rule_file(loaded=False, kind="skill", name="standup",
                               path="skills/standup/SKILL.md"))
    assert v["status"] == "not-loaded"


def test_counter_anchor_a_block_past_the_truncation_point_is_undelivered():
    file = dict(rule_file(), delivery="truncated", delivered_from=1,
                delivered_to=100, delivered_ranges=[(1, 100)], total_lines=500)
    block = dict(block_from(EOM_ONLY_MD), start_line=300, end_line=320)
    v = brv.assess_block(block, file,
                         trace_for([user_text("go", 1)], "go"))
    assert v["status"] == "undelivered"
    assert v["evidence"] == []


# ---------- shape of the two extractors, as unit-level anchors ----------

@pytest.mark.parametrize("cmd,expected", [
    # Both spellings of a heredoc write are real shell.
    ("cat > src/a.ts <<'EOF'\nx\nEOF", ["src/a.ts"]),
    ("cat <<'EOF' > src/a.ts\nx\nEOF", ["src/a.ts"]),
    ("tee -a src/b.ts <<'EOF'\nx\nEOF", ["src/b.ts"]),
    # The redirect on a heredoc's closing line captures output, not source.
    ("python3 - <<'PY'\nprint(1)\nPY > /tmp/out.json", []),
    ("yarn build 2>&1 | tee build.log", []),
    ("git diff > /tmp/p.patch", []),
])
def test_shell_write_targets(cmd, expected):
    assert brv._shell_write_targets(cmd) == expected


def test_fenced_shell_keywords_are_not_commands():
    """`done` closing a fenced loop is not a program the rule is about."""
    assert brv._extract_fenced_commands("```bash\nfor f in *; do echo $f; done\n```") == []


def test_only_shell_tagged_fences_yield_commands():
    assert brv._extract_fenced_commands("```python\nimport re\n```") == []
    assert brv._extract_fenced_commands("```\nimport re\n```") == []
    assert brv._extract_fenced_commands("```bash\nyarn type-check && yarn lint\n```") == [
        "yarn type-check", "yarn lint"]
