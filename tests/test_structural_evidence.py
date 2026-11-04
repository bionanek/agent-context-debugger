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


# The path and template joins credit a block only inside a document the harness
# recorded as *running* (`_document_executed`). A filename lifted out of a plain
# rule document's prose carries no direction - the sentence that made it a
# target, a warning or an example is gone by the time the token meets a path the
# run touched - and five verified false greens came from exactly that. The cases
# below are about the joins' mechanics (a tilde against an absolute path, a
# heredoc append, a python rewrite), so they run inside an invoked `/memlog`
# command; the gate itself is held by the `..._a_rule_document_...` cases.

def memlog_file(md=MEMORY_MD, path="commands/memlog.md", name="memlog"):
    return rule_file(kind="command", name=name, path=path, md=md)


def invoked(events, name="memlog"):
    """The same run, with the harness's record that the document ran."""
    return [assistant_tool_use("Skill", {"skill": name}, 0, tool_id="s0")] + events


def test_tilde_path_in_the_block_joins_an_absolute_write():
    abs_errors = str(Path.home() / ".claude" / "ERRORS.md")
    events = [user_text("wrap up", 1),
              assistant_tool_use("Edit", {"file_path": abs_errors,
                                          "old_string": "", "new_string": "note"}, 2),
              assistant_text("Logged it.", 3)]
    assert "writes-to-named-path" in fired(MEMORY_MD, invoked(events),
                                           file=memlog_file())


def test_relative_path_in_the_block_joins_an_absolute_write():
    events = [user_text("log the decision", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/proj/docs/decisions/DECISIONS.md",
                                           "content": "note"}, 2)]
    assert "writes-to-named-path" in fired(MEMORY_MD, invoked(events),
                                           file=memlog_file())


def test_a_rule_document_gets_no_credit_for_a_write_to_a_path_it_names():
    """The reband anchor. `Info.plist` is edited directly *because* a native
    `ios/` dir exists, so `app.json` does not propagate - and the session that
    edited `app.json` and never touched `Info.plist` was scored `used`."""
    md = ("## Gotchas\n\n`Info.plist` is edited directly - a native `ios/` dir "
          "exists, so `app.json` infoPlist entries do not propagate.\n")
    events = [user_text("add the permission string", 1),
              assistant_tool_use("Edit", {"file_path": "/Users/dev/proj/app.json",
                                          "old_string": "a", "new_string": "b"}, 2)]
    assert "writes-to-named-path" not in fired(md, events,
                                               file=rule_file(kind="project",
                                                              path="AGENTS.md"))
    assert verdict(md, events,
                   file=rule_file(kind="project", path="AGENTS.md"))["status"] \
        not in ("used", "used-partial")


def test_a_command_document_that_did_not_run_gets_no_write_credit():
    """The gate is the invocation record, not the document's kind."""
    events = [user_text("log the decision", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/proj/docs/decisions/DECISIONS.md",
                                           "content": "note"}, 2)]
    assert "writes-to-named-path" not in fired(MEMORY_MD, events,
                                               file=memlog_file())


def test_a_write_elsewhere_does_not_join_the_named_path():
    events = [user_text("edit the loader", 1),
              assistant_tool_use("Edit", {"file_path": "/Users/dev/proj/src/loader.ts",
                                          "old_string": "a", "new_string": "b"}, 2)]
    assert "writes-to-named-path" not in fired(MEMORY_MD, invoked(events),
                                               file=memlog_file())


def test_a_named_path_never_written_cannot_accuse_the_block():
    """Nothing to log is not a violation: this signal only ever gives credit."""
    events = [user_text("just answer a question", 1),
              assistant_text("Here's the answer.", 2)]
    v = verdict(MEMORY_MD, invoked(events), file=memlog_file())
    assert v["status"] not in ("ignored", "used-partial")


def test_a_placeholder_path_is_not_joined():
    md = ("## Error Memory\n\nWrite to "
          "`~/.claude/projects/<encoded-project-path>/memory/ERRORS.md`.\n")
    events = [user_text("wrap up", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/x/memory/ERRORS.md",
                                           "content": "note"}, 2)]
    assert "writes-to-named-path" not in fired(md, invoked(events),
                                               file=memlog_file(md))


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
    assert "template-echo" in fired(DECISION_TEMPLATE_MD, invoked(events),
                                    file=memlog_file(DECISION_TEMPLATE_MD))


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
    events = [user_text("/prd-to-plan turn the PRD into phases", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/plans/plan-x.md",
                                           "content": written}, 2)]
    plan_cmd = memlog_file(md, path="commands/prd-to-plan.md", name="prd-to-plan")
    assert "template-echo" in fired(md, invoked(events, "prd-to-plan"),
                                    file=plan_cmd)
    # The same write against the command file nobody invoked - the formic-core
    # false green, where the session was editing a second copy of the command
    # document itself and `exclude_path` (a path comparison) could not see it.
    assert "template-echo" not in fired(md, events, file=plan_cmd)


def test_one_matching_literal_is_not_enough():
    """A single common heading is coincidence, not a reproduced template."""
    md = ("## Docs\n\nEvery doc uses this shape:\n\n"
          "    ## Architectural decisions\n"
          "    <the decisions>\n")
    events = [user_text("write a doc", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/a.md",
                                           "content": "## Architectural decisions\n\nnone\n"}, 2)]
    assert "template-echo" not in fired(md, invoked(events), file=memlog_file(md))


def test_a_template_never_reproduced_gives_no_evidence():
    events = [user_text("write up the decision", 1),
              assistant_tool_use("Write", {"file_path": "/tmp/notes.md",
                                           "content": "Some prose, no template.\n"}, 2)]
    assert "template-echo" not in fired(DECISION_TEMPLATE_MD, invoked(events),
                                        file=memlog_file(DECISION_TEMPLATE_MD))


def test_editing_the_rule_document_itself_is_not_a_template_echo():
    """A rule file contains its own template, so editing it proves nothing."""
    events = [user_text("update the rules", 1),
              assistant_tool_use("Edit", {"file_path": "/tmp/CLAUDE.md", "old_string": "x",
                                          "new_string": DECISION_TEMPLATE_MD}, 2)]
    # `memlog_file(path=...)` puts the document at /tmp/<path>, so this edit is
    # the document editing itself.
    assert "template-echo" not in fired(
        DECISION_TEMPLATE_MD, invoked(events),
        file=memlog_file(DECISION_TEMPLATE_MD, path="CLAUDE.md"))


def test_appending_to_the_rule_document_by_a_relative_shell_path_is_not_an_echo():
    """`cd <dir> && cat >> DECISIONS.md` is still that document writing itself.

    The exclusion used to compare resolved paths, and a relative path resolves
    against this process's cwd - so a memory file appended to by the agent
    matched its own template and marked every older entry in it `used`.
    """
    events = [user_text("log the decision", 1),
              assistant_tool_use("Bash", {"command": "cd /tmp/memory && cat >> DECISIONS.md "
                                                     "<<'EOF'\n" + DECISION_TEMPLATE_MD + "\nEOF"}, 2)]
    assert "template-echo" not in fired(
        DECISION_TEMPLATE_MD, invoked(events),
        file=memlog_file(DECISION_TEMPLATE_MD, path="memory/DECISIONS.md"))


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
    """One command, one predicate - the strong row, not both rows."""
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


# ---------- a pipeline is one prescribed command, not its stages ----------
# The clipboard anchor. Splitting a documented pipeline on `|` made `pbcopy`
# the prescribed command, so the very shape the rule forbids - `echo` piped
# into `pbcopy` - scored the rule as followed, in green.

CLIPBOARD_MD = """## Copy to clipboard

Always pipe through `printf` - never `echo` - so injected trailing whitespace
is stripped.

```bash
printf '%s' "$content" | pbcopy
```
"""


def test_a_downstream_stage_of_a_prescribed_pipeline_is_not_prescribed():
    assert "pbcopy" not in brv._fenced_commands(CLIPBOARD_MD, None)
    events = [user_text("copy it", 1), bash('echo "x" | pbcopy', 2)]
    assert "command-echo" not in fired(CLIPBOARD_MD, events)
    assert verdict(CLIPBOARD_MD, events)["status"] not in ("used", "used-partial")


def test_a_conjunction_still_prescribes_each_of_its_commands():
    """`&&`, `||` and `;` join commands that each stand on their own, so the
    famigo quality gate is still credited by one of its three running."""
    md = "## Quality gate\n\n```bash\nyarn type-check && yarn lint && yarn test\n```\n"
    assert brv._fenced_commands(md, None) == ["yarn type-check", "yarn lint", "yarn test"]
    assert "command-echo" in fired(md, [user_text("gate it", 1),
                                        bash("yarn type-check", 2)])


def test_a_whole_prescribed_pipeline_that_ran_verbatim_still_counts():
    md = "## Counting\n\n```bash\ngit status --short | wc -l\n```\n"
    assert "git status --short | wc -l" in brv._fenced_commands(md, None)
    assert "command-echo" in fired(md, [user_text("count it", 1),
                                        bash("git status --short|wc -l", 2)])
    # ...and not by the same last stage under a different pipeline.
    assert "command-echo" not in fired(md, [user_text("count it", 1),
                                            bash("cat notes.md | wc -l", 2)])


def test_a_fenced_command_inside_a_heredoc_body_did_not_run():
    """A command pasted into a PR body is text about the command, not a run."""
    events = [user_text("open the PR", 1),
              bash("gh pr create --body-file - <<'EOF'\n"
                   "Ran just palletizer-hmi-lint before pushing.\n"
                   "EOF", 2)]
    assert "command-echo" not in fired(COMMANDS_MD, events)


def test_a_fenced_command_inside_a_command_substitution_heredoc_did_not_run():
    """The shape the PR-body false green really had."""
    events = [user_text("open the PR", 1),
              bash("gh pr create --body \"$(cat <<'EOF'\n"
                   "just palletizer-hmi-lint\n"
                   "EOF\n)\"", 2)]
    assert "command-echo" not in fired(COMMANDS_MD, events)


def test_a_command_after_a_heredoc_terminator_still_counts():
    """The body is skipped, not the rest of the call."""
    events = [user_text("write and test", 1),
              bash("cat <<EOF > notes.md\njust palletizer-hmi-lint\nEOF\nyarn test", 2)]
    t = trace_for(events)
    assert brv._command_echo_count("yarn test", t["bash_cmds"]) == 1
    assert brv._command_echo_count("just palletizer-hmi-lint", t["bash_cmds"]) == 0


def test_a_fenced_command_inside_a_quoted_argument_did_not_run():
    events = [user_text("say it", 1),
              bash("printf '%s' 'just palletizer-hmi-lint' | pbcopy", 2)]
    assert "command-echo" not in fired(COMMANDS_MD, events)


def test_a_fenced_command_in_an_and_chain_did_run():
    events = [user_text("lint", 1),
              bash("cd hmi && just palletizer-hmi-lint", 2)]
    assert "command-echo" in fired(COMMANDS_MD, events)


PYTEST_MD = """## Tests

```bash
pytest
```
"""


def test_a_single_word_fenced_command_reaches_echo_when_it_ran():
    events = [user_text("run the suite", 1), bash("pytest", 2)]
    assert "command-echo" in fired(PYTEST_MD, events)
    assert brv.assess_block(block_from(PYTEST_MD), rule_file(),
                            trace_for(events))["status"] == "used"


def test_a_single_word_fenced_command_as_an_argument_is_not_an_echo():
    events = [user_text("where is it used", 1),
              bash("grep -rn pytest tests/", 2)]
    assert "command-echo" not in fired(PYTEST_MD, events)


def test_echo_credit_replaces_the_weak_mention_of_the_same_command():
    """Two evidence rows for one run would read as two facts."""
    ran = trace_for([user_text("run the suite", 1), bash("pytest", 2)])
    argued = trace_for([user_text("where is it used", 1),
                        bash("grep -rn pytest tests/", 2)])
    preds = brv.derive_predicates(block_from(PYTEST_MD), rule_file())
    mention = next(p for p in preds
                   if p["kind"] == "command-mention" and p["cmd"] == "pytest")
    assert not mention["applicable"](ran)
    assert mention["applicable"](argued)


def test_echo_credit_also_silences_the_weak_card_for_that_command():
    events = [user_text("run the suite", 1), bash("pytest", 2)]
    block, file = block_from(PYTEST_MD), rule_file()
    t = trace_for(events)
    moments = brv.assemble_moments(block, file, t,
                                   brv.derive_predicates(block, file))
    kinds_seen = {m["kind"] for m in moments}
    assert "co-occurrence" not in kinds_seen
    assert any("verbatim" in m["label"] for m in moments)


def test_one_run_is_one_evidence_row():
    events = [user_text("run the suite", 1), bash("pytest", 2)]
    v = verdict(PYTEST_MD, events)
    counted = [e for e in v["evidence"] if "×" in e["text"]]
    assert len(counted) == 1
    assert counted[0]["text"].startswith("`pytest` ran verbatim")
    weak = next(e for e in v["evidence"] if e["label"] == "`pytest` in bash")
    assert "command-echo" in weak["text"]


INLINE_COMMANDS_MD = """## Build / run / test

Install with `yarn install`, then start the app with `yarn start`. The test
suite is `yarn test`.
"""


def test_commands_in_inline_prose_backticks_are_not_echo_candidates():
    """This phase does not widen echo to inline spans - that is a later call."""
    events = [user_text("test it", 1), bash("yarn test", 2)]
    preds = brv.derive_predicates(block_from(INLINE_COMMANDS_MD), rule_file())
    assert not [p for p in preds if p["kind"] == "command-echo"]
    assert "yarn" in [p["cmd"] for p in preds if p["kind"] == "command-mention"]
    assert brv.assess_block(block_from(INLINE_COMMANDS_MD), rule_file(),
                            trace_for(events))["status"] == "possibly-referenced"


# ---------- an executed skill ----------

CREATE_PR_SKILL_MD = """# create-pr

Open a GitHub pull request that matches the repository's existing style.

## Step 1 - match the GitHub account

Check the active account against `docs/accounts.md` and switch before any
other `gh` command.

## Step 2 - open the PR

```bash
gh pr create --fill
```
"""


def _skill_file():
    return rule_file(kind="skill", name="create-pr",
                     path="skills/create-pr/SKILL.md", md=CREATE_PR_SKILL_MD)


def test_a_skill_tool_call_lifts_its_identity_block():
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1"),
              bash("gh pr create --fill", 3)]
    assert "skill-invocation" in fired(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                                       file=_skill_file())


def test_a_slash_command_wrapper_lifts_the_identity_block():
    events = [user_slash("create-pr", "", 1),
              bash("gh pr create --fill", 2)]
    assert "skill-invocation" in fired(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                                       file=_skill_file())


def test_an_invocation_does_not_lift_a_step_of_the_same_skill():
    """The invocation proves the document ran, not that this step happened."""
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1"),
              bash("gh pr create --fill", 3)]
    step = "Step 1 - match the GitHub account"
    assert "skill-invocation" not in fired(CREATE_PR_SKILL_MD, events,
                                           prompt="/create-pr", file=_skill_file(),
                                           title=step)
    v = brv.assess_block(block_from(CREATE_PR_SKILL_MD, step), _skill_file(),
                         trace_for(events, "/create-pr"))
    # The step names a file, so it has a predicate; nothing this run made it
    # applicable, which is exactly what `dormant` says.
    assert v["status"] == "dormant"


def test_a_step_whose_command_really_ran_keeps_its_green():
    """The other predicates are untouched: `gh pr create --fill` ran verbatim."""
    events = [user_text("/create-pr", 1),
              assistant_tool_use("Skill", {"skill": "create-pr"}, 2, tool_id="s1"),
              bash("gh pr create --fill", 3)]
    step = "Step 2 - open the PR"
    kinds_fired = fired(CREATE_PR_SKILL_MD, events, prompt="/create-pr",
                        file=_skill_file(), title=step)
    assert "skill-invocation" not in kinds_fired
    assert "command-echo" in kinds_fired
    v = brv.assess_block(block_from(CREATE_PR_SKILL_MD, step), _skill_file(),
                         trace_for(events, "/create-pr"))
    assert v["status"] == "used"


def test_the_identity_block_of_an_uninvoked_skill_stays_dormant():
    """A bare `/name` in the prompt greens nothing, identity block included."""
    events = [user_text("maybe /create-pr later", 1), assistant_text("Not yet.", 2)]
    assert fired(CREATE_PR_SKILL_MD, events, prompt="maybe /create-pr later",
                 file=_skill_file()) == []


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
    v = verdict(MEMORY_MD, invoked(events), file=memlog_file())
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

@pytest.mark.parametrize("kind", ["reads-named-path", "writes-to-named-path",
                                  "template-echo", "command-echo"])
def test_credit_only_predicates_never_report_unsatisfied(kind):
    """Absence of the signal is not evidence of a violation, so it must never
    be applicable-and-unsatisfied - that combination is what scores `ignored`."""
    md = MEMORY_MD + "\n" + DECISION_TEMPLATE_MD + "\n" + COMMANDS_MD
    block = {"title": "All three", "content": md, "level": 2}
    # Through an invoked document, or the two path/template kinds are never
    # derived at all and their parameters assert nothing.
    file = memlog_file(md)
    for events in ([user_text("nothing happens", 1)],
                   [user_text("something else", 1),
                    assistant_tool_use("Write", {"file_path": "/tmp/x.ts",
                                                 "content": "const a = 1;"}, 2)]):
        t = trace_for(invoked(events))
        for p in brv.derive_predicates(block, file):
            if p["kind"] != kind:
                continue
            assert not (p["applicable"](t) and not p["matches"](t))


# ---------- Phase 3: a path join means a file ----------

def test_a_directory_the_block_names_is_not_a_path_join():
    """`docs/skills/` is where work happens, not a file a rule points at.

    Any write beneath it used to satisfy the block, which is where most of
    the audited false greens came from.
    """
    md = ("## Skill docs\n\nEvery skill gets a document under `docs/skills/`, "
          "kept in step with `mobile/services/`.\n")
    assert brv._named_paths(md) == []
    events = [user_text("add a doc", 1),
              assistant_tool_use("Write", {"file_path": "/repo/docs/skills/anything.md",
                                           "content": "notes"}, 2)]
    assert "writes-to-named-path" not in fired(md, invoked(events),
                                               file=memlog_file(md))


def test_a_slash_command_the_block_names_is_not_a_path():
    md = ("## Pull requests\n\nOpen every PR with `/create-pr` so the "
          "description matches the repo's style.\n")
    assert brv._named_paths(md) == []
    events = [user_text("open a PR", 1),
              assistant_tool_use("Write", {"file_path": str(Path.home() / ".claude" / "skills"
                                                            / "create-pr" / "SKILL.md"),
                                           "content": "---\nname: create-pr\n---\n"}, 2)]
    assert "writes-to-named-path" not in fired(md, invoked(events),
                                               file=memlog_file(md))


def test_a_heading_token_naming_a_directory_yields_no_named_path():
    assert brv._named_paths("### `app/src/`\n\nThe app lives here.\n") == []


def test_the_blocks_own_document_is_not_evidence_it_was_followed():
    """Editing CLAUDE.md is not obeying CLAUDE.md - the `template-echo` rule."""
    md = ("## House style\n\nKeep this file, `CLAUDE.md`, the single source "
          "of truth for the architecture.\n")
    own = str(Path.home() / "Git" / "x" / "CLAUDE.md")
    # An *invoked* document, or the join is gated off before the exclusion this
    # case is about is ever consulted and the assertion proves nothing.
    file = {"loaded": True, "kind": "command", "path": "~/Git/x/CLAUDE.md",
            "abs_path": own, "name": "memlog",
            "blocks": brv.parse_claude_md(md)}
    events = [user_text("document the change", 1),
              assistant_tool_use("Edit", {"file_path": own, "old_string": "a",
                                          "new_string": "b"}, 2)]
    assert "writes-to-named-path" not in fired(md, invoked(events), file=file)


def test_a_write_to_another_file_the_block_names_still_joins():
    """The exclusion is the block's own document, not every write."""
    md = ("## House style\n\n`CLAUDE.md` is the architecture; decisions go to "
          "`docs/decisions/DECISIONS.md`.\n")
    own = str(Path.home() / "Git" / "x" / "CLAUDE.md")
    file = {"loaded": True, "kind": "command", "path": "~/Git/x/CLAUDE.md",
            "abs_path": own, "name": "memlog",
            "blocks": brv.parse_claude_md(md)}
    events = [user_text("log the decision", 1),
              assistant_tool_use("Write", {"file_path": str(Path.home() / "Git" / "x"
                                                            / "docs" / "decisions"
                                                            / "DECISIONS.md"),
                                           "content": "entry"}, 2)]
    assert "writes-to-named-path" in fired(md, invoked(events), file=file)


def test_a_heredoc_append_to_the_named_memory_file_still_joins():
    """The memory-rule anchor: `cat >> $M/DECISIONS.md <<'EOF'`."""
    md = ("## Decision Memory\n\nAppend the entry to "
          "`docs/decisions/DECISIONS.md`.\n")
    cmd = ("M=~/.claude/projects/-Users-dev-proj/memory; "
           "cat >> $M/DECISIONS.md <<'EOF'\n"
           "## [2026-09-05] Something\nEOF")
    assert "writes-to-named-path" in fired(
        md, invoked([user_text("log it", 1), bash(cmd, 2)]), file=memlog_file(md))


def test_a_python_heredoc_rewrite_joins_the_named_path():
    """famigo edits markdown through `python3 - <<'PY'`, not the Edit tool."""
    md = ("## API contracts\n\nEvery endpoint change updates "
          "`backend/API_CONTRACT.md` in the same commit.\n")
    cmd = ("python3 - <<'PY'\n"
           "import pathlib\n"
           "p = pathlib.Path('API_CONTRACT.md')\n"
           "s = p.read_text()\n"
           "s = s.replace('old', 'new', 1)\n"
           "p.write_text(s)\n"
           "PY")
    assert "writes-to-named-path" in fired(
        md, invoked([user_text("update it", 1), bash(cmd, 2)]), file=memlog_file(md))


def test_a_python_heredoc_open_for_writing_joins_the_named_path():
    md = "## API contracts\n\nUpdate `backend/API_CONTRACT.md`.\n"
    cmd = ("python3 - <<'PY'\n"
           "with open('API_CONTRACT.md', 'w') as fh:\n"
           "    fh.write('text')\n"
           "PY")
    assert "writes-to-named-path" in fired(
        md, invoked([user_text("update it", 1), bash(cmd, 2)]), file=memlog_file(md))


def test_a_python_heredoc_that_only_reads_the_named_file_does_not_join():
    """The binding is tracked so a script that reads one file and writes
    another cites the one it wrote."""
    md = "## API contracts\n\nUpdate `backend/API_CONTRACT.md`.\n"
    cmd = ("python3 - <<'PY'\n"
           "import pathlib\n"
           "src = pathlib.Path('API_CONTRACT.md')\n"
           "out = pathlib.Path('summary.md')\n"
           "out.write_text(src.read_text()[:100])\n"
           "PY")
    assert "writes-to-named-path" not in fired(
        md, invoked([user_text("summarise", 1), bash(cmd, 2)]), file=memlog_file(md))


def test_a_python_heredoc_body_is_not_read_as_the_files_content():
    """The script is a program, not the document it rewrote.

    Treating the body as written text would let the *removed* half of a
    `s.replace(old, new)` count as a template the run reproduced.
    """
    cmd = ("python3 - <<'PY'\n"
           "import pathlib\n"
           "p = pathlib.Path('DECISIONS.md')\n"
           "p.write_text(p.read_text().replace('''"
           "## [2026-01-01] Bake the rollup in Python\n"
           "**Decided:** compute every rollup in Python and bake it\n"
           "**Why:** the CLI and the page must not disagree\n"
           "**Rejected:** deriving it in JavaScript''', ''))\n"
           "PY")
    events = [user_text("drop the entry", 1), bash(cmd, 2)]
    assert "template-echo" not in fired(DECISION_TEMPLATE_MD, events)


def test_a_python_heredoc_that_rebinds_the_name_cites_each_file_it_wrote():
    """One script, two files: the value at the time of the write is the file.

    Harvesting the bindings and the writes separately named the second file
    twice and never named the first.
    """
    cmd = ("python3 - <<'PY'\n"
           "import pathlib\n"
           "p = pathlib.Path('first.md')\n"
           "p.write_text('a')\n"
           "p = pathlib.Path('second.md')\n"
           "p.write_text('b')\n"
           "PY")
    assert brv._python_write_targets(cmd) == ["first.md", "second.md"]


def test_a_python_snippet_inside_a_documentation_heredoc_is_not_a_write():
    """`cat > README.md <<'EOF'` carrying an example is prose, not a program."""
    cmd = ("cat > README.md <<'EOF'\n"
           "Write the config like this:\n\n"
           "    pathlib.Path('config.json').write_text('{}')\n"
           "EOF")
    assert brv._python_write_targets(cmd) == []
    assert brv._shell_write_targets(cmd) == ["README.md"]


# ---------- reads of a path the block names ----------
# The write join used to stand in for a read. A famigo `/review` step saying
# "read CLAUDE.md, then load backend/AGENT.md" scored `used` on writes to those
# files - some of them a later turn's unrelated documentation sweep - while the
# honest evidence, the `sed -n` and `grep` calls that actually read them inside
# the review turn, was recorded nowhere.

LOAD_CONTEXT_MD = """## Step 1 - Load context

1. **Read `CLAUDE.md`** (project root) for project conventions.
2. **Load by scope**: Backend-only -> `backend/AGENT.md`
"""


REVIEW_SKILL = rule_file(kind="skill", name="review", path="SKILL.md")


def _describe(md, events, kind, file=None, prompt="do the thing"):
    t = trace_for(events, prompt)
    p = next(p for p in brv.derive_predicates(block_from(md), file)
             if p["kind"] == kind)
    return p["describe"](t)


def test_a_named_file_the_run_only_read_is_used_and_the_evidence_names_the_read():
    events = [user_slash("review", "/review", 1),
              bash("sed -n '1,40p' backend/AGENT.md", 2)]
    v = verdict(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)
    assert v["status"] == "used"
    read_rows = [e for e in v["evidence"]
                 if e["label"] == "read a file the block names"]
    assert read_rows, v["evidence"]
    assert "read `backend/AGENT.md`" in read_rows[0]["text"]


def test_the_read_join_reads_the_Read_tool_too():
    events = [user_slash("review", "/review", 1),
              assistant_tool_use("Read", {"file_path": "/repo/backend/AGENT.md"}, 2)]
    assert "reads-named-path" in fired(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)


def test_a_read_outside_a_procedure_that_ran_is_not_evidence():
    """A file gets read because the work needed it, not because a block named
    it. Over the corpus a bare read join turned a tech-stack table green
    because the session opened one of the files it lists."""
    md = ("## Tech stack\n\nThe client talks to the API through "
          "`services/api.ts`.\n")
    events = [user_text("look into the map bug", 1),
              bash("cat services/api.ts", 2)]
    assert "reads-named-path" not in fired(md, events, file=rule_file(kind="rule"))


def test_a_skill_document_that_did_not_run_gets_no_read_credit():
    events = [user_text("read the agent guide", 1),
              bash("cat backend/AGENT.md", 2)]
    assert "reads-named-path" not in fired(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)


def test_a_named_file_the_run_only_wrote_is_still_used_by_the_write_join():
    """Removing the write join's stand-in must not cost the case it was for."""
    events = [user_text("log the decision", 1),
              assistant_tool_use("Write", {"file_path": "/Users/dev/proj/docs/decisions/DECISIONS.md",
                                           "content": "entry"}, 2)]
    v = verdict(MEMORY_MD, invoked(events), file=memlog_file())
    assert v["status"] == "used"
    assert "writes-to-named-path" in fired(MEMORY_MD, invoked(events),
                                           file=memlog_file())
    assert "reads-named-path" not in fired(MEMORY_MD, invoked(events),
                                           file=memlog_file())


def test_a_file_both_read_and_written_is_cited_as_a_read_not_as_a_write():
    """One interaction with one file, reported as the claim that is supported.

    The write to `backend/AGENT.md` may be any other work the session did; the
    read is what shows the step's own instruction being carried out.
    """
    events = [user_slash("review", "/review", 1),
              bash("grep -n 'hooks' backend/AGENT.md", 2),
              assistant_tool_use("Edit", {"file_path": "/repo/backend/AGENT.md",
                                          "old_string": "a", "new_string": "b"}, 3,
                                 tool_id="e1")]
    fired_kinds = fired(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)
    assert "reads-named-path" in fired_kinds
    assert "writes-to-named-path" not in fired_kinds
    v = verdict(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)
    assert not any("wrote `" in e["text"] for e in v["evidence"]), v["evidence"]


def test_a_second_named_file_that_was_only_written_still_gets_its_write_row():
    """The precedence is per path, not per block."""
    md = ("## Step 1 - Load context\n\nRead `backend/AGENT.md`, then record the "
          "outcome in `docs/decisions/DECISIONS.md`.\n")
    events = [user_slash("review", "/review", 1),
              bash("cat backend/AGENT.md", 2),
              assistant_tool_use("Write", {"file_path": "/repo/docs/decisions/DECISIONS.md",
                                           "content": "entry"}, 3, tool_id="w9")]
    assert "reads-named-path" in fired(md, events, file=REVIEW_SKILL)
    assert "writes-to-named-path" in fired(md, events, file=REVIEW_SKILL)
    written = _describe(md, events, "writes-to-named-path", file=REVIEW_SKILL)
    assert "DECISIONS.md" in written
    assert "AGENT.md" not in written


def test_reading_the_blocks_own_document_is_not_evidence_it_was_followed():
    """Reading CLAUDE.md is not obeying CLAUDE.md, exactly as editing it is not."""
    md = ("## House style\n\nKeep this file, `CLAUDE.md`, the single source "
          "of truth for the architecture.\n")
    own = str(Path.home() / "Git" / "x" / "CLAUDE.md")
    file = {"loaded": True, "kind": "skill", "path": "~/Git/x/CLAUDE.md",
            "abs_path": own, "name": "house-style"}
    events = [user_slash("house-style", "/house-style", 1),
              assistant_tool_use("Read", {"file_path": own}, 2)]
    assert "reads-named-path" not in fired(md, events, file=file)


def test_a_directory_the_block_names_is_not_joined_by_a_read():
    md = ("## Skill docs\n\nEvery skill gets a document under `docs/skills/`, "
          "kept in step with `mobile/services/`.\n")
    events = [user_slash("review", "/review", 1),
              bash("cat docs/skills/anything.md", 2)]
    assert "reads-named-path" not in fired(md, events, file=REVIEW_SKILL)


def test_a_slash_command_the_block_names_is_not_joined_by_a_read():
    md = ("## Pull requests\n\nOpen every PR with `/create-pr` so the "
          "description matches the repo's style.\n")
    events = [user_slash("review", "/review", 1),
              assistant_tool_use("Read", {"file_path": str(Path.home() / ".claude" / "skills"
                                                           / "create-pr" / "SKILL.md")}, 2)]
    assert "reads-named-path" not in fired(md, events, file=REVIEW_SKILL)


def test_a_grep_pattern_is_not_read_as_a_path():
    """The quoted argument is content the command carried, not a file."""
    assert brv._shell_read_targets("grep -n 'API_CONTRACT.md' src/app.ts") == ["src/app.ts"]


def test_a_heredoc_write_whose_program_is_a_reader_is_not_a_read():
    """`cat > README.md <<'EOF'` authors the file; nothing read it."""
    assert brv._shell_read_targets("cat > README.md <<'EOF'\nhello\nEOF") == []
    assert brv._shell_read_targets("cat >> $M/ERRORS.md <<'EOF'\nx\nEOF") == []


def test_a_path_in_another_programs_arguments_is_not_a_read():
    """The reader has to be the program a segment runs."""
    assert brv._shell_read_targets("git add backend/AGENT.md") == []
    assert brv._shell_read_targets("git add x.md && cat backend/AGENT.md") == \
        ["backend/AGENT.md"]


def test_a_named_path_never_read_gives_no_credit():
    """The signal is the read, so a run that read nothing earns nothing."""
    events = [user_slash("review", "/review", 1),
              assistant_text("Here's the answer.", 2)]
    assert "reads-named-path" not in fired(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)


def test_the_read_card_appears_beside_the_badge_it_earned():
    """A skill step lifted by a read must say so in its cards.

    The skill/command branch of `assemble_moments` drew only the invocation
    cards, so the badge read "read a file the block names" above a card list
    that mentioned no read at all.
    """
    events = [user_slash("review", "/review", 1),
              bash("sed -n '1,40p' backend/AGENT.md", 2)]
    v = verdict(LOAD_CONTEXT_MD, events, file=REVIEW_SKILL)
    labels = [m["label"] for m in v["moments"]]
    assert any("Read `backend/AGENT.md`" in l for l in labels), labels


def test_the_write_row_does_not_claim_a_file_was_never_written():
    """The precedence must not turn the write row into a false statement.

    `none of ... was written this run` is untrue when the run did write one and
    the read row is citing it instead.
    """
    events = [user_slash("review", "/review", 1),
              bash("grep -n 'hooks' backend/AGENT.md", 2),
              assistant_tool_use("Edit", {"file_path": "/repo/backend/AGENT.md",
                                          "old_string": "a", "new_string": "b"}, 3,
                                 tool_id="e2")]
    text = _describe(LOAD_CONTEXT_MD, events, "writes-to-named-path", file=REVIEW_SKILL)
    assert "none of" not in text, text
    assert "read rather than written" in text
