"""Phase 8b: only harness-defined signals are hardcoded.

Every strong predicate the tool used to derive from prose was reverse-engineered
from one user's CLAUDE.md (§4 of `docs/judgement-reliability-research.md`): the
path table matched the literal header "Project path contains", the summary rule
matched one rule's phrasing and encoded one author's writing style, and the
well-known-command list existed because of one clipboard rule. None of it
transfers to a user whose rules are worded differently, let alone written in
another language.

What may stay hardcoded is what the harness itself defines and every user
shares: a slash command being invoked, a `Skill` call, a file path a tool call
carried, a command that ran verbatim. Everything read out of one author's
wording now has to come from a compiled checks file, which each user generates
from their own rules through `/compile-rules`.

These tests hold both halves of that line: the bespoke predicates derive
nothing and the affected rules report honestly, *and* the same rules still
resolve correctly once their compiled equivalents are present - the migration
preserves coverage rather than dropping it.
"""
import json
from pathlib import Path

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import (
    assistant_text,
    assistant_tool_use,
    user_text,
)


# ---------- helpers ----------

FIXTURES = Path(__file__).parent / "fixtures"
WORKED_EXAMPLE = FIXTURES / "global_rules.md"

# The predicate kinds that survive: each is a record the harness writes, joined
# to something the block itself names. Nothing here reads a rule's phrasing.
HARNESS_KINDS = {"trigger", "skill-invocation", "writes-to-named-path",
                 "template-echo", "command-echo"}


def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def write_call(path, content, i, tool_id="w1"):
    return assistant_tool_use("Write", {"file_path": path, "content": content}, i,
                              tool_id=tool_id)


def with_cwd(events, cwd):
    return [dict(e, cwd=cwd) for e in events]


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


def rule_file(abs_path, kind="global", name=None):
    return {"loaded": True, "kind": kind, "path": str(abs_path),
            "abs_path": str(abs_path), "name": name}


def blocks_of(md):
    return brv.parse_claude_md(md)


def block_named(md, title):
    return next(b for b in blocks_of(md) if b["title"] == title)


def predicates_of(md, title, file=None):
    return brv.derive_predicates(block_named(md, title), file)


def kinds_of(md, title, file=None):
    return sorted({p["kind"] for p in predicates_of(md, title, file)})


def strong_kinds_of(md, title, file=None):
    return sorted({p["kind"] for p in predicates_of(md, title, file)
                   if brv._is_strong(p)})


def mention_cmds(md, title):
    return sorted(p["cmd"] for p in predicates_of(md, title)
                  if p["kind"] == "command-mention")


def worked_example_verdict(title, events, prompt="do the thing", cwd=None):
    """A block of the worked-example document, with its checks file in play."""
    rc.checks_for_doc.cache_clear()
    if cwd:
        events = with_cwd(events, cwd)
    return brv.assess_block(block_named(WORKED_EXAMPLE.read_text(), title),
                            rule_file(WORKED_EXAMPLE), trace_for(events, prompt))


def uncompiled_verdict(tmp_path, md, title, events, prompt="do the thing", cwd=None):
    """The same block in a document nobody has compiled - no checks file."""
    doc = tmp_path / "CLAUDE.md"
    doc.write_text(md)
    rc.checks_for_doc.cache_clear()
    if cwd:
        events = with_cwd(events, cwd)
    return brv.assess_block(block_named(md, title), rule_file(doc),
                            trace_for(events, prompt))


FORMIC_CWD = "/Users/dev/Git/formic-core"


# ---------- the bespoke predicates derive nothing ----------

PATH_TABLE_MD = """## GitHub account per project

Before running any `gh` command, check the active GitHub account with
`gh auth status` and switch if needed:

| Project path contains | Required account | Switch command |
|-----------------------|-----------------|----------------|
| `figma` | `bionanek` | `gh auth switch -u bionanek` |
| `formic` | `bionanek-x` | `gh auth switch -u bionanek-x` |

**Rule:** If the active account doesn't match the project, run the switch
command silently before proceeding.
"""

EOM_MD = """## End-of-implementation summary

After implementing any code change, always end your response with a brief
user-facing summary: what changed from the user's perspective. Keep it to 1-3
sentences. Focus on observable behavior, not technical details.
"""


def test_a_path_conditional_table_derives_no_strong_predicate():
    """"Project path contains" was one user's table header, not a syntax."""
    assert "path-table" not in kinds_of(PATH_TABLE_MD, "GitHub account per project")
    assert strong_kinds_of(PATH_TABLE_MD, "GitHub account per project") == []


def test_a_summary_rule_derives_no_strong_predicate():
    """The response-shape rule was matched by its author's own phrasing."""
    assert "end-of-message" not in kinds_of(EOM_MD, "End-of-implementation summary")
    assert strong_kinds_of(EOM_MD, "End-of-implementation summary") == []


def test_no_prose_derived_strong_predicate_survives_anywhere():
    """The acceptance criterion, over every rule document the suite carries.

    A strong predicate carries the full verdict range, `ignored` included, so
    one derived from a turn of phrase is an accusation resting on wording. The
    kinds left are the ones a second user's differently-worded rules produce
    identically.
    """
    docs = [PATH_TABLE_MD, EOM_MD, WORKED_EXAMPLE.read_text(),
            (FIXTURES / "rules_pl.md").read_text(),
            Path("CLAUDE.md").read_text()]
    seen = set()
    for md in docs:
        for block in blocks_of(md):
            seen |= {p["kind"] for p in brv.derive_predicates(block)
                     if brv._is_strong(p)}
    assert seen <= HARNESS_KINDS, sorted(seen - HARNESS_KINDS)


def test_an_uncompiled_path_rule_reports_honestly_with_the_compile_hint(tmp_path):
    """Nobody compiled this rule, so the report says that and names the fix.

    The old predicate guessed instead, and guessed wrong in both directions:
    `used` for a session with no `gh` command at all, `ignored` for one that
    switched accounts exactly as told.
    """
    v = uncompiled_verdict(tmp_path, PATH_TABLE_MD, "GitHub account per project",
                           [user_text("open a PR", 1), bash("gh pr create --fill", 2)],
                           prompt="open a PR", cwd=FORMIC_CWD)
    assert v["status"] not in ("used", "used-partial", "ignored"), v["reason"]
    assert v["ruleCheck"]["state"] == "not-checkable"
    assert rc.COMPILE_COMMAND in v["ruleCheck"]["hint"]


def test_an_uncompiled_summary_rule_reports_honestly_with_the_compile_hint(tmp_path):
    v = uncompiled_verdict(tmp_path, EOM_MD, "End-of-implementation summary",
                           [user_text("ship it", 1),
                            assistant_tool_use("Edit", {"file_path": "/p/a.ts",
                                                        "old_string": "a",
                                                        "new_string": "b"}, 2),
                            assistant_text("Done. I moved the parser over and "
                                           "rewired AuthController.ts to it.", 3)],
                           prompt="ship it")
    assert v["status"] not in ("used", "used-partial", "ignored"), v["reason"]
    assert rc.COMPILE_COMMAND in v["ruleCheck"]["hint"]


# ---------- the author-specific token lists are gone ----------

CLIPBOARD_PROSE_MD = """## Copy to clipboard

When copying text, always use printf rather than echo, and never reach for
pbcopy, xclip or xsel without stripping the trailing newline first.
"""


def test_the_clipboard_word_list_no_longer_manufactures_command_mentions():
    """Five shell words were hardcoded because of this one rule.

    Backtick-free prose about them is prose: the block is talking about
    clipboards, and a session that piped something into `pbcopy` for its own
    reasons is not evidence about it.
    """
    assert mention_cmds(CLIPBOARD_PROSE_MD, "Copy to clipboard") == []


def test_no_author_specific_token_survives_in_the_non_command_list():
    """`NON_CMDS` had to grow an entry per false positive in one repo's docs.

    A list curated against one project's vocabulary is the same
    reverse-engineering as the predicates: this tool's own payload keys and
    verdict statuses mean nothing to the next user's rules, and the shape test
    is what carries the filter.
    """
    author_specific = {"argparse", "claude.md", "skill.md",
                       "used", "unused", "ignored", "dormant", "undelivered",
                       "activesessionid", "turnrows", "possibly-referenced"}
    assert not (author_specific & set(brv.NON_CMDS)), sorted(
        author_specific & set(brv.NON_CMDS))


# ---------- coverage is preserved through the migration ----------
# The compiled equivalents of the two retired predicates, authored through the
# 8a flow from the same rules, against the §7 anchors the predicates got wrong.

def test_the_worked_example_checks_file_survives_the_gate_intact():
    rc.checks_for_doc.cache_clear()
    loaded = rc.checks_for_doc(str(WORKED_EXAMPLE))
    assert loaded["rejected"] == [], loaded["rejected"]
    assert loaded["demoted"] == [], loaded["demoted"]
    assert {c["id"] for c in loaded["checks"]} == {"gh-auth-before-gh",
                                                   "no-echo-into-clipboard"}
    assert [j["id"] for j in loaded["judged"]] == ["closing-summary-shape"]


def test_anchor_pathtable_false_green_is_not_exercised_with_the_compiled_check():
    """formicHMI 8fd8526c: zero `gh` commands, matched `git log --author=`.

    The account name in the table's second column was extracted as the
    prescribed command and substring-matched a git flag. The compiled check
    asks the tool log instead, and a session that never ran `gh` never
    triggered the rule.
    """
    v = worked_example_verdict("GitHub account per project",
                               [user_text("what did I ship today", 1),
                                bash('git log --author="bionanek-x" --oneline', 2),
                                assistant_text("Here is today's work.", 3)],
                               prompt="what did I ship today", cwd=FORMIC_CWD)
    assert v["ruleCheck"]["state"] == "not-exercised"
    assert v["status"] not in ("used", "ignored", "used-partial"), v["reason"]


def test_anchor_pathtable_the_verbatim_switch_reads_as_compliance():
    """formicHMI 12f48cdb / formic-core 4ebe50c0 / ACI d5c3cc1a: the switch ran."""
    v = worked_example_verdict("GitHub account per project",
                               [user_text("open a PR", 1),
                                bash("gh auth switch -u bionanek-x", 2, tool_id="b1"),
                                bash("gh pr create --fill", 3, tool_id="b2")],
                               prompt="open a PR", cwd=FORMIC_CWD)
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] == "used", v["reason"]


def test_anchor_pathtable_status_checked_and_already_correct_is_compliance():
    """reband 113a0d2c / formic-core 39b9e09e: checked, nothing needed switching.

    The rule says switch *if needed*. The predicate demanded the literal switch
    string, so the session that obeyed it by checking scored `ignored` and cited
    the rule-mandated check itself as the violation.
    """
    v = worked_example_verdict("GitHub account per project",
                               [user_text("open a PR", 1),
                                bash("gh auth status", 2, tool_id="b1"),
                                bash("gh pr create --fill", 3, tool_id="b2")],
                               prompt="open a PR", cwd=FORMIC_CWD)
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] == "used", v["reason"]


def test_a_compound_check_and_run_in_one_call_is_still_compliance():
    """Agents write "check, then run" as one Bash line."""
    v = worked_example_verdict("GitHub account per project",
                               [user_text("open a PR", 1),
                                bash("gh auth status; gh pr create --fill", 2)],
                               prompt="open a PR", cwd=FORMIC_CWD)
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] == "used", v["reason"]


def test_a_real_violation_still_turns_the_block_red_with_a_citation():
    """The gate the whole architecture rests on: a cited span, or no violation."""
    v = worked_example_verdict("GitHub account per project",
                               [user_text("open a PR", 1),
                                bash("gh pr create --fill", 2)],
                               prompt="open a PR", cwd=FORMIC_CWD)
    assert v["status"] == "ignored"
    finding = next(f for f in v["ruleCheck"]["findings"] if f["state"] == "violated")
    assert finding["checkId"] == "gh-auth-before-gh"
    assert "gh pr" in finding["match"]
    assert finding["path"] == "(tools)" and finding["line"] == 1


def test_the_clipboard_rule_still_finds_its_violation_once_compiled():
    v = worked_example_verdict("Copy to clipboard",
                               [user_text("copy it", 1),
                                bash('echo "$content" | pbcopy', 2)],
                               prompt="copy it")
    assert v["status"] == "ignored"
    assert v["ruleCheck"]["findings"][0]["checkId"] == "no-echo-into-clipboard"


def test_the_summary_rule_says_it_needs_a_judge_and_never_accuses(tmp_path):
    """The honest compiled answer for a rule about meaning.

    Its checkable half is a sentence count; the half that matters ("observable
    behaviour, not technical details") is a judgement, so the compile step
    parks it. The retired predicate answered anyway, and red-flagged a
    compliant three-sentence summary in every implementation session audited.
    """
    v = worked_example_verdict("End-of-implementation summary",
                               [user_text("ship it", 1),
                                assistant_tool_use("Edit", {"file_path": "/p/a.ts",
                                                            "old_string": "a",
                                                            "new_string": "b"}, 2),
                                assistant_text("Refactored AuthController to "
                                               "delegate to MagicLinkService.", 3)],
                               prompt="ship it")
    assert v["status"] != "ignored", v["reason"]
    assert v["ruleCheck"]["state"] == "not-checkable"
    parked = v["ruleCheck"]["judged"]
    assert [p["id"] for p in parked] == ["closing-summary-shape"]
    assert parked[0]["bucket"] == "judged"
    # A parked rule is an answer the compiler gave, so it is not nagged about.
    assert v["ruleCheck"]["hint"] == ""


def test_a_satisfied_check_from_the_mechanical_fallback_never_turns_a_block_green(tmp_path):
    """Credit is as gated as blame: low confidence stays a note either way."""
    doc = tmp_path / "CLAUDE.md"
    doc.write_text("## Store boundaries\n\n"
                   "Never import `AuthStore` directly in a component.\n")
    rc.checks_for_doc.cache_clear()
    events = [user_text("add the panel", 1),
              write_call("/repo/src/Panel.tsx", "export const Panel = () => null;\n", 2)]
    v = brv.assess_block(block_named(doc.read_text(), "Store boundaries"),
                         rule_file(doc), trace_for(events, "add the panel"))
    assert v["ruleCheck"]["source"] == "fallback"
    assert v["ruleCheck"]["state"] == "clear"
    assert v["status"] != "used", v["reason"]


# ---------- the same tool for a user whose rules are in another language ----------

PL = FIXTURES / "rules_pl.md"
EN = FIXTURES / "rules_en.md"

# One session, driving both twins: the skill was invoked, the file the rule
# names was written with the rule's own template in it, and the documented
# command ran verbatim.
def _twin_session():
    return [user_text("/standup", 1),
            assistant_tool_use("Skill", {"skill": "standup"}, 2, tool_id="s1"),
            write_call(str(Path.home() / ".claude" / "ERRORS.md"),
                       "## 2026-09-03 Wrong join\n"
                       "**What failed:** resolving one side only\n"
                       "**Co zawiodło:** resolving one side only\n"
                       "**What worked:** resolving both\n"
                       "**Co zadziałało:** resolving both\n", 3, tool_id="w1"),
            bash("pytest -q", 4, tool_id="b1")]


def _twin_verdicts(doc, title):
    rc.checks_for_doc.cache_clear()
    md = doc.read_text()
    events = _twin_session()
    return brv.assess_block(block_named(md, title), rule_file(doc),
                            trace_for(events, "/standup"))


def test_a_foreign_language_rule_doc_derives_the_same_predicates_as_its_twin():
    """No English phrase may be the reason a rule is judged at all.

    The two fixtures state the same rules over the same paths, templates and
    commands; only the prose language differs. A predicate set that differs
    between them is an English assumption still in the extractor.
    """
    for en_title, pl_title in (("Error Memory", "Pamięć błędów"),
                               ("standup", "standup")):
        assert (kinds_of(EN.read_text(), en_title)
                == kinds_of(PL.read_text(), pl_title)), (en_title, pl_title)


def test_a_foreign_language_trigger_declaration_still_fires():
    """`Wyzwalacz: /standup` is the same declaration as `Trigger: /standup`.

    The command is a harness-defined identifier; the label in front of it is
    the user's own language. Keying on the English label meant a Polish (or
    Japanese) skill pointer derived nothing and scored `unused` while the
    skill was demonstrably running.
    """
    assert "trigger" in kinds_of(PL.read_text(), "standup")
    assert _twin_verdicts(PL, "standup")["status"] == "used"


def test_a_foreign_language_doc_reaches_the_same_verdicts():
    for en_title, pl_title in (("Error Memory", "Pamięć błędów"),
                               ("standup", "standup")):
        assert (_twin_verdicts(EN, en_title)["status"]
                == _twin_verdicts(PL, pl_title)["status"]), (en_title, pl_title)


def test_a_foreign_language_rule_is_never_accused_by_prose_alone():
    """An uncompiled foreign-language rule is honestly unchecked, not broken."""
    rc.checks_for_doc.cache_clear()
    md = PL.read_text()
    events = [user_text("policz pliki", 1), bash("ls -la", 2)]
    for block in blocks_of(md):
        v = brv.assess_block(block, rule_file(PL), trace_for(events, "policz pliki"))
        assert v["status"] != "ignored", (block["title"], v["reason"])


def test_a_compiled_check_carries_the_verdict_for_a_foreign_language_rule():
    """Coverage for such a user comes from their own compile run, not from cues."""
    rc.checks_for_doc.cache_clear()
    md = PL.read_text()
    checks = {
        "source": str(PL),
        "checks": [{
            "id": "no-echo-do-schowka",
            "rule_ref": "Schowek",
            "rule_text": "Nigdy nie przekazuj `echo` do `pbcopy`.",
            "domain": "shell",
            "kind": "forbidden_command",
            "pattern": r"\becho\b[^|]*\|\s*pbcopy",
            "applies_to": [],
            "confidence": "high",
            "message": "`echo` dokleja znak nowej linii; regula wymaga `printf`.",
            "self_test": {"should_match": ['echo "$x" | pbcopy'],
                          "should_not_match": ["printf '%s' \"$x\" | pbcopy"]},
        }],
    }
    (Path(str(PL) + ".checks.json.tmp")).write_text(json.dumps(checks))
    try:
        loaded = rc.load_checks(checks)
        assert loaded["rejected"] == []
        corpus = rc.build_corpus(brv.tool_calls([bash('echo "$x" | pbcopy', 1)]))
        v = rc.check_block(block_named(md, "Schowek"), loaded, corpus)
        assert v["state"] == "violated"
        assert v["findings"][0]["checkId"] == "no-echo-do-schowka"
    finally:
        Path(str(PL) + ".checks.json.tmp").unlink()


def test_a_deciding_rule_check_gets_a_moment_card():
    """The badge and the cards are two claims about one run.

    A check that painted the block green or red used to leave only the lexical
    card, whose own text says "nothing in the trace ties the behaviour back to
    the block" - a card denying the badge above it.
    """
    v = worked_example_verdict("GitHub account per project",
                               [user_text("open a PR", 1),
                                bash("gh auth status", 2, tool_id="b1"),
                                bash("gh pr create --fill", 3, tool_id="b2")],
                               prompt="open a PR", cwd=FORMIC_CWD)
    assert v["status"] == "used"
    card = next(m for m in v["moments"] if m["kind"] == "compliance")
    assert "gh-auth-before-gh" in card["label"]

    red = worked_example_verdict("GitHub account per project",
                                 [user_text("open a PR", 1),
                                  bash("gh pr create --fill", 2)],
                                 prompt="open a PR", cwd=FORMIC_CWD)
    assert red["status"] == "ignored"
    violation = next(m for m in red["moments"] if m["kind"] == "violation")
    assert "gh pr" in violation["text"]
    assert not [m for m in red["moments"] if m["kind"] == "compliance"]
