"""Tests for Phase 6: the tool-log check vocabulary.

Ordering constraints are where the research says ~73% of real agent failures
live, and over 30% of real conditional failures are wrong condition-checking
rather than a wrong action. Both are invisible to a checker that can only look
at written code and an unordered bag of shell commands, which is what the
source/shell/path domains gave. These kinds read the session's tool calls as an
ordered, indexed log, and every conditional reports its two stages separately:
an antecedent that never fired is a different fact from a consequent that was
missed, and collapsing them is how "the rule was followed" gets printed over a
session that never did the thing the rule governs.
"""
import json
import pathlib

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import _ts, assistant_tool_use, user_text

from tests.test_rule_checks import bash, corpus_for, doc, rule_file, trace_for, write_call


# ---------- helpers ----------

def tool_check(**over):
    """A `tool_never_without_prior` check in the shape the authoring prompt emits."""
    base = {
        "id": "gh-auth-before-gh",
        "rule_ref": "GitHub account per project",
        "rule_text": "Before running any `gh` command, check the active account with "
                     "`gh auth status` and switch if needed.",
        "domain": "tool",
        "kind": "tool_never_without_prior",
        "pattern": r"\bgh\s+(?!auth\b)\w",
        "prior_pattern": r"\bgh\s+auth\s+(?:status|switch)\b",
        "applies_to": [],
        "confidence": "high",
        "message": "A `gh` command ran without checking the active account first.",
        "self_test": {
            "should_match": ["Bash gh pr create --fill"],
            "should_not_match": [
                "Bash gh auth status\nBash gh pr create --fill",
                "Bash gh auth switch -u bionanek\nBash gh pr list",
                'Bash git log --author="bionanek-x"',
                "Bash gh auth status",
            ],
        },
    }
    base.update(over)
    return base


def loaded_ok(*checks):
    loaded = rc.load_checks(doc(checks=list(checks)))
    assert loaded["rejected"] == [], loaded["rejected"]
    return loaded


def states(findings):
    return [f["state"] for f in findings]


def stages(findings):
    return [f.get("stage") for f in findings]


def read_call(path, i, tool_id="r1"):
    return assistant_tool_use("Read", {"file_path": path}, i, tool_id=tool_id)


# ---------- the ordered tool log ----------

def test_the_tool_log_is_ordered_and_indexed():
    events = [user_text("go", 1),
              bash("gh auth status", 2, tool_id="b1"),
              write_call("/repo/a.ts", "const a = 1;\n", 3, tool_id="w1"),
              bash("gh pr create", 4, tool_id="b2")]
    tools = corpus_for(events)["tools"]
    assert [t["index"] for t in tools] == [0, 1, 2]
    assert [t["name"] for t in tools] == ["Bash", "Write", "Bash"]
    assert tools[0]["text"] == "Bash gh auth status"
    assert tools[1]["path"] == "/repo/a.ts" and tools[1]["writes"] is True
    assert tools[2]["writes"] is False


def test_the_bash_description_is_prose_and_stays_out_of_the_tool_line():
    """Measured on the real anchors: with the description in the line, the Bash
    label "Check active gh account" matched `gh <word>` and condemned the very
    call that complied with the rule."""
    events = [user_text("go", 1),
              assistant_tool_use("Bash", {"command": "gh auth status | head -5",
                                          "description": "Check active gh account"},
                                 2, tool_id="b1")]
    entry = corpus_for(events)["tools"][0]
    assert entry["text"] == "Bash gh auth status | head -5"
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["not-exercised"]


def test_a_multiline_command_still_makes_one_tool_line():
    events = [user_text("go", 1), bash("set -e\ngh auth status\ngh pr list", 2)]
    entry = corpus_for(events)["tools"][0]
    assert entry["text"] == "Bash set -e gh auth status gh pr list"


def test_bulk_write_content_stays_out_of_the_tool_line():
    """A tool line must stay one line, or every span it cites is unreadable and
    the whole file's text turns up twice - once here, once in the code corpus."""
    events = [user_text("go", 1),
              write_call("/repo/a.ts", "const a = 1;\nconst b = 2;\n", 2)]
    entry = corpus_for(events)["tools"][0]
    assert "\n" not in entry["text"]
    assert "const a = 1" not in entry["text"]
    assert entry["text"] == "Write /repo/a.ts"


# ---------- tool_forbidden / tool_required ----------

def test_tool_forbidden_cites_the_call_that_ran():
    check = tool_check(id="no-force-push", kind="tool_forbidden",
                       pattern=r"git push\s+--force(?!-)", prior_pattern=None,
                       self_test={"should_match": ["Bash git push --force origin main"],
                                  "should_not_match": ["Bash git push origin main",
                                                       "Bash git push --force-with-lease"]})
    check.pop("prior_pattern")
    events = [user_text("ship it", 1), bash("git push --force origin main", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert findings[0]["path"] == "(tools)"
    assert findings[0]["match"] == "git push --force"
    assert findings[0]["line"] == 1


def test_tool_required_fires_only_when_its_trigger_fired():
    check = tool_check(id="edit-needs-typecheck", kind="tool_required",
                       trigger_pattern=r"^Edit\b", pattern=r"yarn type-check",
                       self_test={"should_match": ["Edit src/a.ts"],
                                  "should_not_match": ["Edit src/a.ts\nBash yarn type-check",
                                                       "Bash yarn build"]})
    check.pop("prior_pattern")
    edited = [user_text("go", 1),
              assistant_tool_use("Edit", {"file_path": "/repo/a.ts", "old_string": "x",
                                          "new_string": "y"}, 2, tool_id="e1")]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(edited))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]

    untouched = [user_text("go", 1), bash("yarn build", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(untouched))
    assert states(findings) == ["not-exercised"]
    assert stages(findings) == ["antecedent-not-fired"]


def test_tool_required_is_order_blind_and_the_prompt_has_to_say_so():
    """It asks only whether both things happened. An author who reaches for it
    to express "after" gets a green badge over a session that did them the wrong
    way round, which is why the authoring prompt sends "after" to
    `tool_precedes`, "before" to `tool_never_without_prior` and "after every
    edit" to `not_checkable`."""
    check = tool_check(id="edit-needs-typecheck", kind="tool_required",
                       trigger_pattern=r"^Edit\b", pattern=r"yarn type-check",
                       self_test={"should_match": ["Edit src/a.ts"],
                                  "should_not_match": ["Edit src/a.ts\nBash yarn type-check",
                                                       "Bash yarn build"]})
    check.pop("prior_pattern")
    backwards = [user_text("go", 1),
                 bash("yarn type-check", 2, tool_id="b1"),
                 assistant_tool_use("Edit", {"file_path": "/repo/a.ts", "old_string": "x",
                                             "new_string": "y"}, 3, tool_id="e1")]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(backwards))
    assert stages(findings) == ["satisfied"]


# ---------- ordering ----------

def precedes_check(**over):
    """"Run the tests after editing": an edit is the antecedent, a test run
    after it the obligation. A "before" rule is `tool_never_without_prior`."""
    base = tool_check(id="test-after-edit", kind="tool_precedes",
                      first_pattern=r"^Edit\b",
                      second_pattern=r"\byarn\s+test\b",
                      self_test={
                          "should_match": ["Bash yarn test\nEdit src/a.ts",
                                           "Edit src/a.ts"],
                          "should_not_match": [
                              "Edit src/a.ts\nBash yarn test",
                              "Bash yarn test",
                              "Bash git status"],
                      })
    base.pop("prior_pattern")
    base.update(over)
    return base


def edit(i, tool_id):
    return assistant_tool_use("Edit", {"file_path": "/repo/a.ts", "old_string": "x",
                                       "new_string": "y"}, i, tool_id=tool_id)


def test_tool_precedes_fails_when_the_order_is_reversed_even_though_both_ran():
    """Order is the point: a check that only asks whether both happened would
    pass the session that did them backwards, which is the failure class the
    research puts at ~73% of real ones."""
    events = [user_text("go", 1), bash("yarn test", 2, tool_id="b1"), edit(3, "e1")]
    findings = rc.evaluate_checks(loaded_ok(precedes_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]
    # The citation is the edit nothing followed up, the call the rule is about.
    assert findings[0]["match"] == "Edit"
    assert findings[0]["line"] == 2


def test_tool_precedes_passes_when_the_order_holds():
    events = [user_text("go", 1), edit(2, "e1"), bash("yarn test", 3, tool_id="b1")]
    findings = rc.evaluate_checks(loaded_ok(precedes_check())["checks"], corpus_for(events))
    assert states(findings) == ["clear"]
    assert stages(findings) == ["satisfied"]


def test_tool_precedes_edited_and_never_tested_is_a_missed_consequent():
    """The commonest way to break "test after editing" is to never test. This
    used to read `not-exercised`, because the antecedent wanted both sides."""
    events = [user_text("go", 1), edit(2, "e1")]
    findings = rc.evaluate_checks(loaded_ok(precedes_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]
    assert findings[0]["match"] == "Edit"


def test_tool_precedes_with_no_first_side_is_not_exercised():
    events = [user_text("go", 1), bash("yarn test", 2)]
    findings = rc.evaluate_checks(loaded_ok(precedes_check())["checks"], corpus_for(events))
    assert states(findings) == ["not-exercised"]
    assert stages(findings) == ["antecedent-not-fired"]


# ---------- tool_never_without_prior ----------

def test_tool_never_without_prior_passes_when_the_prior_ran_first():
    events = [user_text("open the PR", 1),
              bash("gh auth status", 2, tool_id="b1"),
              bash("gh pr create --fill", 3, tool_id="b2")]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["clear"]
    assert stages(findings) == ["satisfied"]


def test_tool_never_without_prior_fails_the_call_with_no_prior_check():
    events = [user_text("open the PR", 1), bash("gh pr create --fill", 2)]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]
    assert "gh p" in findings[0]["match"]


def test_a_prior_that_ran_after_does_not_excuse_the_call():
    events = [user_text("open the PR", 1),
              bash("gh pr create --fill", 2, tool_id="b1"),
              bash("gh auth status", 3, tool_id="b2")]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert findings[0]["line"] == 1


def test_a_prior_earlier_in_the_same_command_satisfies_the_check():
    """How formicHMI 12f48cdb actually writes it: the check and the gh command
    are one compound Bash call. Comparing call indices alone condemns the most
    compliant shape there is."""
    events = [user_text("go", 1),
              bash('gh auth status 2>&1 | grep -B1 "Active account: true"; '
                   "gh pr list --limit 5", 2)]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["clear"]
    assert stages(findings) == ["satisfied"]


def test_a_prior_later_in_the_same_command_does_not_satisfy_it():
    events = [user_text("go", 1),
              bash("gh pr list --limit 5; gh auth status", 2)]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]


def test_only_the_unaccompanied_calls_are_cited():
    events = [user_text("go", 1),
              bash("gh pr create --fill", 2, tool_id="b1"),
              bash("gh auth status", 3, tool_id="b2"),
              bash("gh pr merge", 4, tool_id="b3")]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert [f["line"] for f in findings] == [1]


# ---------- tool_arg_matches ----------

def arg_check(**over):
    base = tool_check(id="commit-no-signature", kind="tool_arg_matches",
                      tool_pattern=r"^Bash git commit\b", arg_pattern=r"^(?!.*Co-Authored-By)",
                      self_test={
                          "should_match": ["Bash git commit -m 'Add X' Co-Authored-By: Claude"],
                          "should_not_match": ["Bash git commit -m 'Add X'",
                                               "Bash git push origin main"],
                      })
    base.pop("prior_pattern")
    base.update(over)
    return base


def test_tool_arg_matches_flags_a_call_whose_args_do_not():
    events = [user_text("commit", 1),
              bash("git commit -m 'Add X\n\nCo-Authored-By: Claude'", 2)]
    findings = rc.evaluate_checks(loaded_ok(arg_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]


def test_tool_arg_matches_is_not_exercised_when_no_call_selects_it():
    events = [user_text("go", 1), bash("git push origin main", 2)]
    findings = rc.evaluate_checks(loaded_ok(arg_check())["checks"], corpus_for(events))
    assert stages(findings) == ["antecedent-not-fired"]


# ---------- call counts ----------

def count_check(**over):
    base = tool_check(id="one-commit-per-task", kind="tool_call_count",
                      pattern=r"^Bash git commit\b", max_calls=1,
                      self_test={
                          "should_match": ["Bash git commit -m a\nBash git commit -m b"],
                          "should_not_match": ["Bash git commit -m a", "Bash git status"],
                      })
    base.pop("prior_pattern")
    base.update(over)
    return base


def test_tool_call_count_flags_the_call_over_the_limit():
    events = [user_text("go", 1),
              bash("git commit -m a", 2, tool_id="b1"),
              bash("git commit -m b", 3, tool_id="b2")]
    findings = rc.evaluate_checks(loaded_ok(count_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    # The citation is the first call past the limit, not the first call.
    assert findings[0]["line"] == 2


def test_tool_call_count_min_calls_cites_the_last_call():
    check = count_check(id="test-twice", max_calls=None, min_calls=2,
                        pattern=r"^Bash pytest\b",
                        self_test={"should_match": ["Bash pytest -q"],
                                   "should_not_match": ["Bash pytest -q\nBash pytest -q",
                                                        "Bash yarn build"]})
    check.pop("max_calls")
    events = [user_text("go", 1), bash("pytest -q", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert findings[0]["line"] == 1


def test_tool_call_count_with_no_matching_call_is_not_exercised_never_violated():
    """A count rule has nothing to quote when the thing never happened, and a
    violation without a citable span is not reportable. `tool_required` with a
    trigger is the kind for "it must happen at all"."""
    check = count_check(id="test-twice", max_calls=None, min_calls=2,
                        pattern=r"^Bash pytest\b",
                        self_test={"should_match": ["Bash pytest -q"],
                                   "should_not_match": ["Bash pytest -q\nBash pytest -q",
                                                        "Bash yarn build"]})
    check.pop("max_calls")
    events = [user_text("go", 1), bash("yarn build", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(events))
    assert states(findings) == ["not-exercised"]
    assert stages(findings) == ["antecedent-not-fired"]


def test_a_count_check_must_bound_the_count():
    check = count_check()
    check.pop("max_calls")
    loaded = rc.load_checks(doc(checks=[check]))
    assert loaded["checks"] == []
    assert "min_calls" in loaded["rejected"][0]["reason"]


# ---------- writes_to_path ----------

def writes_check(**over):
    base = tool_check(id="log-errors", kind="writes_to_path",
                      trigger_pattern=r"^Bash git commit\b",
                      pattern=r"ERRORS\.md$",
                      self_test={
                          "should_match": ["Bash git commit -m a"],
                          "should_not_match": [
                              "Bash git commit -m a\nWrite /home/u/.claude/ERRORS.md",
                              "Bash yarn build"],
                      })
    base.pop("prior_pattern")
    base.update(over)
    return base


def test_writes_to_path_requires_a_write_to_a_matching_path():
    events = [user_text("go", 1), bash("git commit -m a", 2)]
    findings = rc.evaluate_checks(loaded_ok(writes_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert stages(findings) == ["consequent-missed"]

    satisfied = [user_text("go", 1),
                 write_call("/home/u/.claude/ERRORS.md", "## entry\n", 2, tool_id="w1"),
                 bash("git commit -m a", 3, tool_id="b1")]
    findings = rc.evaluate_checks(loaded_ok(writes_check())["checks"], corpus_for(satisfied))
    assert stages(findings) == ["satisfied"]


def test_reading_the_named_file_is_not_writing_to_it():
    events = [user_text("go", 1),
              read_call("/home/u/.claude/ERRORS.md", 2, tool_id="r1"),
              bash("git commit -m a", 3, tool_id="b1")]
    findings = rc.evaluate_checks(loaded_ok(writes_check())["checks"], corpus_for(events))
    assert states(findings) == ["violated"]


# ---------- two-stage conditional reporting ----------

def test_antecedent_not_fired_is_distinguishable_from_a_missed_consequent():
    """The two facts a single verdict used to collapse. >30% of real conditional
    failures are wrong condition-checking, so which stage failed is the finding."""
    check = tool_check()
    never = [user_text("go", 1), bash("yarn build", 2)]
    missed = [user_text("go", 1), bash("gh pr create", 2)]
    a = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(never))
    b = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(missed))
    assert (a[0]["stage"], a[0]["state"]) == ("antecedent-not-fired", "not-exercised")
    assert (b[0]["stage"], b[0]["state"]) == ("consequent-missed", "violated")
    # The unfired antecedent has nothing to quote, and inventing a span for it
    # would put a citation under a claim no call supports.
    assert a[0]["match"] == "" and a[0]["line"] == 0


def test_an_unfired_conditional_folds_to_not_exercised_not_clear():
    """`clear` reads as "the rule was followed"; a rule whose trigger never came
    up was not followed, it was never tested."""
    md = "## GitHub account per project\n\nAlways check the account before `gh`.\n"
    block = brv.parse_claude_md(md)[0]
    events = [user_text("go", 1), bash("yarn build", 2)]
    v = rc.check_block(block, loaded_ok(tool_check()), corpus_for(events))
    assert v["state"] == "not-exercised"


def test_a_fired_and_satisfied_conditional_is_clear():
    md = "## GitHub account per project\n\nAlways check the account before `gh`.\n"
    block = brv.parse_claude_md(md)[0]
    events = [user_text("go", 1),
              bash("gh auth status", 2, tool_id="b1"),
              bash("gh pr create", 3, tool_id="b2")]
    v = rc.check_block(block, loaded_ok(tool_check()), corpus_for(events))
    assert v["state"] == "clear"


# ---------- the self-test gate ----------

def test_every_new_kind_self_tests_at_load():
    every = [tool_check(), precedes_check(), arg_check(), count_check(), writes_check()]
    forbidden = tool_check(id="no-force-push", kind="tool_forbidden",
                           pattern=r"git push\s+--force(?!-)",
                           self_test={"should_match": ["Bash git push --force origin main"],
                                      "should_not_match": ["Bash git push origin main"]})
    forbidden.pop("prior_pattern")
    required = tool_check(id="edit-needs-typecheck", kind="tool_required",
                          trigger_pattern=r"^Edit\b", pattern=r"yarn type-check",
                          self_test={"should_match": ["Edit src/a.ts"],
                                     "should_not_match": ["Edit src/a.ts\nBash yarn type-check"]})
    required.pop("prior_pattern")
    every += [forbidden, required]
    loaded = rc.load_checks(doc(checks=every))
    assert loaded["rejected"] == []
    assert len(loaded["checks"]) == len(every)
    assert {c["kind"] for c in loaded["checks"]} == set(rc.TOOL_KINDS)


def test_a_tool_check_whose_selftests_disagree_is_refused():
    """The pilot's lesson, applied to the new kinds: the generator claiming its
    tests pass is not evidence, so the consumer re-runs them with its matcher."""
    backwards = precedes_check(self_test={
        # Encodes the compliant order as the violation.
        "should_match": ["Bash gh auth status\nBash gh auth switch -u a"],
        "should_not_match": ["Bash gh auth switch -u a\nBash gh auth status"],
    })
    loaded = rc.load_checks(doc(checks=[backwards]))
    assert loaded["checks"] == []
    assert "self-test" in loaded["rejected"][0]["reason"].lower()


def test_a_quiet_rule_cannot_spend_the_budget_a_violation_needs():
    """A tool kind reports its stage even when satisfied, so those notes must not
    count against the finding limit - twenty quiet rules would otherwise stop the
    twenty-first from ever being evaluated and the block would read as clean."""
    quiet = []
    for n in range(20):
        c = tool_check(id="quiet-%d" % n, kind="tool_forbidden",
                       pattern=r"\bnever-happens-%d\b" % n,
                       self_test={"should_match": ["Bash never-happens-%d" % n],
                                  "should_not_match": ["Bash true"]})
        c.pop("prior_pattern")
        quiet.append(c)
    loaded = loaded_ok(*(quiet + [tool_check()]))
    findings = rc.evaluate_checks(loaded["checks"],
                                  corpus_for(gh_session("gh pr create --fill")))
    assert "violated" in states(findings)


def test_a_cited_finding_budget_still_bounds_the_list():
    check = tool_check(id="no-bash", kind="tool_forbidden", pattern=r"^Bash\b",
                       self_test={"should_match": ["Bash echo hi"],
                                  "should_not_match": ["Read /repo/a.ts"]})
    check.pop("prior_pattern")
    findings = rc.evaluate_checks(loaded_ok(check)["checks"],
                                  corpus_for(gh_session(*["echo hi"] * 25)), limit=20)
    assert len(findings) == 20


def test_a_forbidden_call_is_not_reported_as_a_missed_obligation():
    """`consequent-missed` renders as "triggered, and what it asks for did not
    happen", which is the wrong claim about an action that was taken."""
    check = tool_check(id="no-force-push", kind="tool_forbidden",
                       pattern=r"git push\s+--force(?!-)",
                       self_test={"should_match": ["Bash git push --force origin main"],
                                  "should_not_match": ["Bash git push origin main"]})
    check.pop("prior_pattern")
    events = [user_text("ship it", 1), bash("git push --force origin main", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(events))
    assert states(findings) == ["violated"]
    assert "stage" not in findings[0]


def test_an_unsatisfiable_count_window_is_refused():
    check = count_check(id="impossible", min_calls=3, max_calls=1)
    loaded = rc.load_checks(doc(checks=[check]))
    assert loaded["checks"] == []
    assert "no session could satisfy" in loaded["rejected"][0]["reason"]


def test_the_leading_argument_is_the_one_the_call_is_about():
    """Anchored patterns are what the authoring prompt recommends, so the line
    cannot start with whichever key the transcript happened to serialise first."""
    events = [user_text("go", 1),
              assistant_tool_use("Bash", {"timeout": 600000,
                                          "command": "git commit -m x"}, 2, tool_id="b1")]
    assert corpus_for(events)["tools"][0]["text"].startswith("Bash git commit -m x")


def test_the_authoring_prompt_names_the_real_truncation_length():
    """The author reasons about the corpus this prompt describes. A stale number
    here sends a checkable rule to `not_checkable`, or the reverse, and nothing
    at check time can tell that it happened."""
    prompt = (pathlib.Path(brv.__file__).parent / "prompts" / "translate-rules.md")
    assert str(rc._MAX_ARG_CHARS) in prompt.read_text(encoding="utf-8")


def test_an_unknown_tool_kind_is_still_refused():
    loaded = rc.load_checks(doc(checks=[tool_check(kind="tool_vibes")]))
    assert loaded["checks"] == []
    assert "closed" in loaded["rejected"][0]["reason"]


def test_inline_suppression_downgrades_a_tool_violation():
    events = [user_text("go", 1), bash("gh pr create --fill  # ctx-allow", 2)]
    findings = rc.evaluate_checks(loaded_ok(tool_check())["checks"], corpus_for(events))
    assert states(findings) == ["acknowledged"]


# ---------- the acceptance criterion ----------

GH_RULE_MD = """## GitHub account per project

Before running any `gh` command (PR creation, issue management, etc.), check the
active GitHub account with `gh auth status` and switch if needed.
"""


def gh_session(*commands):
    events = [user_text("open the PR", 1)]
    for n, cmd in enumerate(commands):
        events.append(bash(cmd, n + 2, tool_id="b%d" % n))
    return events


def test_the_gh_rule_passes_every_compliant_anchor_shape():
    """The §7 anchors the old hardcoded path-table predicate got wrong. The rule
    says "switch if needed", which that predicate could not express at all: it
    demanded the switch command and so condemned a session that checked the
    account and found it already correct."""
    block = brv.parse_claude_md(GH_RULE_MD)[0]
    loaded = loaded_ok(tool_check())
    compliant = {
        # formicHMI 12f48cdb, formic-core 4ebe50c0, agent-context-ide d5c3cc1a
        "switch ran, then gh": ("gh auth switch -u bionanek", "gh pr create --fill"),
        # reband 113a0d2c, formic-core 39b9e09e / 1b395e0b
        "status checked, already correct": ("gh auth status", "gh pr list"),
        "status then switch then gh": ("gh auth status", "gh auth switch -u bionanek",
                                       "gh pr create"),
    }
    for label, cmds in compliant.items():
        v = rc.check_block(block, loaded, corpus_for(gh_session(*cmds)))
        assert v["state"] == "clear", (label, v)

    # formicHMI 8fd8526c: zero gh commands, and `git log --author="bionanek-x"`
    # is what the old predicate mistook for the prescribed command.
    quiet = rc.check_block(block, loaded,
                           corpus_for(gh_session('git log --author="bionanek-x"',
                                                 "yarn build")))
    assert quiet["state"] == "not-exercised"

    breach = rc.check_block(block, loaded, corpus_for(gh_session("gh pr create --fill")))
    assert breach["state"] == "violated"
    assert breach["findings"][0]["line"] == 1


def test_the_gh_rule_reaches_the_block_verdict_through_a_checks_file(tmp_path):
    src = tmp_path / "CLAUDE.md"
    src.write_text(GH_RULE_MD)
    (tmp_path / "CLAUDE.md.checks.json").write_text(json.dumps(doc(checks=[tool_check()])))
    rc.checks_for_doc.cache_clear()
    block = brv.parse_claude_md(GH_RULE_MD)[0]

    events = gh_session("gh pr create --fill")
    v = brv.assess_block(block, rule_file(src), trace_for(events, "open the PR"))
    assert v["status"] == "ignored"
    assert v["ruleCheck"]["state"] == "violated"
    assert "(tools):1" in v["reason"]

    ok = gh_session("gh auth status", "gh pr create --fill")
    v = brv.assess_block(block, rule_file(src), trace_for(ok, "open the PR"))
    assert v["status"] != "ignored"
    assert v["ruleCheck"]["state"] == "clear"


def test_an_unfired_stage_becomes_evidence_that_says_so_not_an_empty_citation(tmp_path):
    """`(tools):0 — ` in the evidence list reads as a span the reader can go and
    check, and there is no call behind it."""
    src = tmp_path / "CLAUDE.md"
    src.write_text(GH_RULE_MD)
    (tmp_path / "CLAUDE.md.checks.json").write_text(json.dumps(doc(checks=[tool_check()])))
    rc.checks_for_doc.cache_clear()
    block = brv.parse_claude_md(GH_RULE_MD)[0]

    v = brv.assess_block(block, rule_file(src), trace_for(gh_session("yarn build"), "go"))
    row = next(e for e in v["evidence"] if "gh-auth-before-gh" in e["label"])
    assert "antecedent-not-fired" in row["label"]
    assert "(tools):0" not in row["text"]
    assert "never tested" in row["text"]


def test_tool_precedes_counts_a_second_side_later_in_the_same_line():
    """`yarn build && yarn test` is the obligation met, in one call."""
    check = precedes_check(first_pattern=r"\byarn\s+build\b",
                           self_test={"should_match": ["Bash yarn build"],
                                      "should_not_match": ["Bash yarn build && yarn test"]})
    events = [user_text("go", 1), bash("yarn build && yarn test", 2)]
    findings = rc.evaluate_checks(loaded_ok(check)["checks"], corpus_for(events))
    assert stages(findings) == ["satisfied"]
