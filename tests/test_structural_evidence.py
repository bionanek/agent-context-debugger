"""Structural evidence: what the agent *did* feeds the verdict.

Phase 4 of the judgement-reliability work (kills F-BLINDSPOT, §2 of
`docs/judgement-reliability-research.md`). Three harness-defined signals join
behaviour to a block: the Skill tool call that executed a skill, a write to a
path the block names, and a prescribed command that ran verbatim. Plus one
content signal: a template the block spells out, reproduced in a file the scope
wrote.

Style follows the repo convention: in-memory events from tests/test_turns.py,
assertions on returned dicts, never on HTML.
"""
from pathlib import Path

import pytest

import build_real_view as brv

from tests.test_turns import (
    assistant_text,
    assistant_tool_use,
    user_slash,
    user_text,
)


# ---------- helpers ----------

def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def block_from(md, title=None):
    blocks = brv.parse_claude_md(md)
    if title is None:
        return blocks[0]
    return next(b for b in blocks if b["title"] == title)


def rule_file(loaded=True, kind="global", name=None, path="CLAUDE.md"):
    return {"loaded": loaded, "kind": kind, "path": path,
            "abs_path": f"/tmp/{path}", "name": name}


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


def verdict(md, events, prompt="do the thing", file=None, title=None):
    return brv.assess_block(block_from(md, title), file or rule_file(),
                            trace_for(events, prompt))


def kinds(md, events, prompt="do the thing", file=None, title=None):
    return sorted(p["kind"] for p in
                  brv.derive_predicates(block_from(md, title), file))


def fired(md, events, prompt="do the thing", file=None, title=None):
    """Kinds of predicate that fired strongly on this trace."""
    t = trace_for(events, prompt)
    return sorted(p["kind"] for p in brv.derive_predicates(block_from(md, title), file)
                  if brv._fired_strongly(p, t))


# ---------- writes to a path the block names ----------

MEMORY_MD = """## Error Memory

Log wrong-direction approaches to `~/.claude/ERRORS.md` before ending the
session. Project-specific ones go to `docs/decisions/DECISIONS.md`.
"""


def test_tilde_path_in_the_block_joins_an_absolute_write():
    abs_errors = str(Path.home() / ".claude" / "ERRORS.md")
    events = [user_text("wrap up", 1),
              assistant_tool_use("Edit", {"file_path": abs_errors,
                                          "old_string": "", "new_string": "note"}, 2),
              assistant_text("Logged it.", 3)]
    assert "writes-to-named-path" in fired(MEMORY_MD, events)


def test_relative_path_in_the_block_joins_an_absolute_write():
    events = [user_text("log the decision", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/proj/docs/decisions/DECISIONS.md",
                                           "content": "note"}, 2)]
    assert "writes-to-named-path" in fired(MEMORY_MD, events)


def test_a_write_elsewhere_does_not_join_the_named_path():
    events = [user_text("edit the loader", 1),
              assistant_tool_use("Edit", {"file_path": "/Users/dev/proj/src/loader.ts",
                                          "old_string": "a", "new_string": "b"}, 2)]
    assert "writes-to-named-path" not in fired(MEMORY_MD, events)


def test_a_named_path_never_written_cannot_accuse_the_block():
    """Nothing to log is not a violation: this signal only ever gives credit."""
    events = [user_text("just answer a question", 1),
              assistant_text("Here's the answer.", 2)]
    v = verdict(MEMORY_MD, events)
    assert v["status"] not in ("ignored", "used-partial")


def test_a_placeholder_path_is_not_joined():
    md = ("## Error Memory\n\nWrite to "
          "`~/.claude/projects/<encoded-project-path>/memory/ERRORS.md`.\n")
    events = [user_text("wrap up", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/x/memory/ERRORS.md",
                                           "content": "note"}, 2)]
    assert "writes-to-named-path" not in fired(md, events)


# ---------- template reproduced in written content ----------

DECISION_TEMPLATE_MD = """## Decision log entry

Append one entry per significant decision, in this exact shape:

    ## [YYYY-MM-DD] Short title
    **Decided:** what was chosen
    **Why:** the reason
    **Rejected:** alternatives and why they were dropped
"""


def test_a_template_reproduced_in_write_content_is_strong_evidence():
    written = ("## [2026-01-01] Bake the rollup in Python\n"
               "**Decided:** compute every rollup in Python and bake it\n"
               "**Why:** the CLI and the page must not disagree\n"
               "**Rejected:** deriving it in JavaScript\n")
    events = [user_text("write up the decision", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/DECISIONS.md",
                                           "content": written}, 2)]
    assert "template-echo" in fired(DECISION_TEMPLATE_MD, events)


def test_template_headings_reproduced_in_a_written_plan_are_strong_evidence():
    """The prd-to-plan anchor: the plan template's own headings, in the file."""
    md = """## Phase 1: <Title>

**User stories**: <list from PRD>

### Tests (write first — red)

- Test 1: what user-visible behaviour this verifies

### Implementation (green)

A concise description of what to build.

### Acceptance criteria

- [ ] Criterion 1
"""
    written = ("## Phase 1: Structural evidence\n\n### Tests (write first — red)\n\n- one\n\n"
               "### Implementation (green)\n\nbuild it\n\n### Acceptance criteria\n\n- [ ] two\n")
    events = [user_text("write the plan", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/plans/plan-x.md",
                                           "content": written}, 2)]
    assert "template-echo" in fired(md, events)


def test_one_matching_literal_is_not_enough():
    """A single common heading is coincidence, not a reproduced template."""
    md = ("## Docs\n\nEvery doc uses this shape:\n\n"
          "    ## Architectural decisions\n"
          "    <the decisions>\n")
    events = [user_text("write a doc", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/a.md",
                                           "content": "## Architectural decisions\n\nnone\n"}, 2)]
    assert "template-echo" not in fired(md, events)


def test_a_template_never_reproduced_gives_no_evidence():
    events = [user_text("write up the decision", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/notes.md",
                                           "content": "Some prose, no template.\n"}, 2)]
    assert "template-echo" not in fired(DECISION_TEMPLATE_MD, events)


def test_editing_the_rule_document_itself_is_not_a_template_echo():
    """A rule file contains its own template, so editing it proves nothing."""
    events = [user_text("update the rules", 1),
              assistant_tool_use("Edit", {"file_path": "/tmp/CLAUDE.md", "old_string": "x",
                                          "new_string": DECISION_TEMPLATE_MD}, 2)]
    assert "template-echo" not in fired(DECISION_TEMPLATE_MD, events,
                                       file=rule_file(path="CLAUDE.md"))


def test_appending_to_the_rule_document_by_a_relative_shell_path_is_not_an_echo():
    """`cd <dir> && cat >> DECISIONS.md` is still that document writing itself.

    The exclusion used to compare resolved paths, and a relative path resolves
    against this process's cwd - so a memory file appended to by the agent
    matched its own template and marked every older entry in it `used`.
    """
    events = [user_text("log the decision", 1),
              assistant_tool_use("Bash", {"command": "cd /tmp/memory && cat >> DECISIONS.md "
                                                     "<<'EOF'\n" + DECISION_TEMPLATE_MD + "\nEOF"}, 2)]
    assert "template-echo" not in fired(DECISION_TEMPLATE_MD, events,
                                        file=rule_file(path="memory/DECISIONS.md"))


def test_written_content_covers_multiedit_and_notebook_edits():
    t = trace_for([user_text("edit", 1),
                   assistant_tool_use("MultiEdit", {"file_path": "/tmp/a.md", "edits": [
                       {"old_string": "x", "new_string": "**Decided:** this"},
                       {"old_string": "y", "new_string": "**Why:** that"}]}, 2)])
    assert "**Decided:** this" in t["written_text"]
    assert "**Why:** that" in t["written_text"]


# ---------- verbatim command echo ----------

COMMANDS_MD = """## Commands

Run these from the workspace root:

```bash
just palletizer-hmi-lint
yarn test
```
"""


def test_a_fenced_command_that_ran_verbatim_is_strong_evidence():
    events = [user_text("lint and test", 1),
              bash("just palletizer-hmi-lint", 2, tool_id="b1"),
              bash("yarn test", 3, tool_id="b2")]
    assert "command-echo" in fired(COMMANDS_MD, events)


def test_a_fenced_command_that_never_ran_is_not_evidence():
    events = [user_text("lint and test", 1), bash("git status", 2)]
    assert "command-echo" not in fired(COMMANDS_MD, events)


def test_a_multi_token_command_is_not_also_a_weak_mention():
    """One command, one predicate: the weak tier keeps the single-word ones."""
    preds = brv.derive_predicates(block_from(COMMANDS_MD))
    mentions = [p["cmd"] for p in preds if p["kind"] == "command-mention"]
    assert "yarn test" not in mentions
    assert "just palletizer-hmi-lint" not in mentions


def test_command_echo_evidence_counts_the_runs():
    events = [user_text("gate it", 1),
              bash("yarn test", 2, tool_id="b1"),
              bash("yarn test --watch=false", 3, tool_id="b2")]
    t = trace_for(events)
    p = next(p for p in brv.derive_predicates(block_from(COMMANDS_MD))
             if p["kind"] == "command-echo" and p["cmd"] == "yarn test")
    assert "2×" in p["describe"](t)


# ---------- an executed skill ----------

CREATE_PR_SKILL_MD = """# create-pr

Open a GitHub pull request that matches the repository's existing style.
"""


def _skill_file():
    return rule_file(kind="skill", name="create-pr", path="skills/create-pr/SKILL.md")


def test_a_skill_tool_call_lifts_its_own_blocks():
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1"),
              bash("gh pr create --fill", 3)]
    assert "skill-invocation" in fired(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                                       file=_skill_file())


def test_a_slash_command_wrapper_lifts_the_skill_blocks():
    events = [user_slash("create-pr", "", 1),
              bash("gh pr create --fill", 2)]
    assert "skill-invocation" in fired(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                                       file=_skill_file())


def test_a_prompt_mention_alone_is_not_a_record_of_execution():
    """The prompt is a guess about intent; only a record may carry the verdict."""
    events = [user_text("/create-pr please", 1), assistant_text("Sure.", 2)]
    assert "skill-invocation" not in fired(CREATE_PR_SKILL_MD, events,
                                          prompt="/create-pr please", file=_skill_file())


def test_a_rule_document_gets_no_skill_predicate():
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1")]
    assert "skill-invocation" not in kinds(CREATE_PR_SKILL_MD, events, file=rule_file())


# ---------- the reason and cards never deny what a signal shows ----------

def test_the_reason_never_calls_a_structural_match_a_coincidence():
    abs_errors = str(Path.home() / ".claude" / "ERRORS.md")
    events = [user_text("wrap up", 1),
              assistant_tool_use("Edit", {"file_path": abs_errors, "old_string": "",
                                          "new_string": "**What failed:** x"}, 2),
              assistant_text("Logged it.", 3)]
    v = verdict(MEMORY_MD, events)
    assert "coincidence" not in v["reason"].lower()
    assert v["status"] == "used"


def test_a_structural_verdict_gets_an_action_card_not_a_topical_one():
    events = [user_text("lint and test", 1),
              bash("just palletizer-hmi-lint", 2, tool_id="b1"),
              bash("yarn test", 3, tool_id="b2")]
    v = verdict(COMMANDS_MD, events, file=rule_file(kind="project", path="AGENTS.md"))
    actions = [m for m in v["moments"] if m["kind"] == "action" and m["verdict"] == "yes"]
    assert actions
    assert v["status"] == "used"


# ---------- predicate contract ----------

@pytest.mark.parametrize("kind", ["writes-to-named-path", "template-echo", "command-echo"])
def test_credit_only_predicates_never_report_unsatisfied(kind):
    """Absence of the signal is not evidence of a violation, so it must never
    be applicable-and-unsatisfied - that combination is what scores `ignored`."""
    md = MEMORY_MD + "\n" + DECISION_TEMPLATE_MD + "\n" + COMMANDS_MD
    block = {"title": "All three", "content": md, "level": 2}
    for events in ([user_text("nothing happens", 1)],
                   [user_text("something else", 1),
                    assistant_tool_use("Write", {"file_path": "/tmp/x.ts",
                                                 "content": "const a = 1;"}, 2)]):
        t = trace_for(events)
        for p in brv.derive_predicates(block):
            if p["kind"] != kind:
                continue
            assert not (p["applicable"](t) and not p["matches"](t))
