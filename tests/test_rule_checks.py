"""Tests for Phase 9: rule compilation and code-based violation checking.

The architecture under test: a rule is interpreted ONCE, outside this tool, into
a reviewable checks JSON that lives beside the rule document. At analysis time
the tool loads that file, re-runs every check's self-tests with its own matcher,
and applies the survivors to what the session actually wrote and ran. No model
is consulted here, and a check whose semantics the generator got wrong is
refused rather than believed.
"""
import json
from pathlib import Path

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import _ts, assistant_text, assistant_tool_use, user_text


# ---------- helpers ----------

def write_call(path, content, i, tool_id="w1"):
    return assistant_tool_use("Write", {"file_path": path, "content": content}, i,
                              tool_id=tool_id)


def edit_call(path, new_string, i, tool_id="e1"):
    return assistant_tool_use("Edit", {"file_path": path, "old_string": "x",
                                       "new_string": new_string}, i, tool_id=tool_id)


def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def corpus_for(events):
    return rc.build_corpus(brv.tool_calls(events))


def check(**over):
    base = {
        "id": "no-reaction",
        "rule_ref": "Reactions",
        "rule_text": "Never call reaction() in a component.",
        "domain": "source",
        "kind": "forbidden_pattern",
        "pattern": r"\breaction\(",
        "applies_to": ["**/*.tsx"],
        "confidence": "high",
        "message": "reaction() is forbidden in components.",
        # A should_not_match case puts the identifier inside a string literal,
        # which is the check declaring that strings are not code for it.
        "ignore_strings": True,
        "self_test": {
            "should_match": ["    reaction(() => store.value, run);"],
            "should_not_match": [
                "    // reaction() is not allowed here",
                '    const label = "reaction(";',
                "    useReactionless(store);",
                "    autorun(() => store.value);",
            ],
        },
    }
    base.update(over)
    return base


def doc(checks=None, not_checkable=None, source="RULES.md"):
    return {"source": source, "checks": checks or [], "not_checkable": not_checkable or []}


# ---------- central comment and string stripping ----------

def test_block_comment_continuation_lines_are_stripped():
    """The pilot's per-regex guards missed continuation lines of a block comment."""
    text = "const a = 1;\n/* keeping this note:\n   reaction(() => x, y) was removed\n*/\nconst b = 2;\n"
    out = rc.strip_comments_and_strings(text, "src/a.tsx")
    assert "reaction(" not in out
    assert "const a = 1;" in out and "const b = 2;" in out
    # Offsets must survive so spans and line numbers stay truthful.
    assert len(out) == len(text)
    assert out.count("\n") == text.count("\n")


def test_hash_comments_respect_the_language():
    assert "secret" not in rc.strip_comments_and_strings("x = 1  # secret\n", "a.py")
    # '#' is not a comment marker in TypeScript, so a hex colour survives.
    assert "#fff" in rc.strip_comments_and_strings("const c = 0; const d = 1; /* */ #fff\n", "a.tsx")


def test_string_contents_survive_by_default():
    """Stripping strings blinds the checker to the most common rule shape there
    is: in JS and TS a module path is a string literal, so `never import from X`
    could never match. Comments were the pilot's actual false-positive source."""
    src = "import { rootStore } from '../stores/rootStore';"
    assert "rootStore'" in rc.strip_comments_and_strings(src, "Panel.tsx")
    assert 'bg-[#f8f9f9]' in rc.strip_comments_and_strings(
        '<div className="bg-[#f8f9f9]">', "Panel.tsx")


def test_strings_are_stripped_only_when_a_check_opts_in():
    src = 'const s = "reaction(() => x, y)";'
    assert "reaction(" in rc.strip_comments_and_strings(src, "a.tsx")
    assert "reaction(" not in rc.strip_comments_and_strings(src, "a.tsx", strip_strings=True)


def test_a_url_inside_a_string_is_not_a_line_comment():
    """`//` in a URL used to blank the rest of the line, hiding real code from
    the checker. String boundaries are tracked even when contents are kept."""
    src = "const url = 'https://api.example.com'; reaction(() => x, y);"
    assert "reaction(" in rc.strip_comments_and_strings(src, "a.ts")


def test_template_interpolations_are_code_not_string_content():
    """`${...}` holds executable code, so blanking it hides real matches even
    when a check has asked for strings to be stripped."""
    src = "const url = `wss://${import.meta.env.VITE_HOST}/ws`;"
    out = rc.strip_comments_and_strings(src, "a.ts", strip_strings=True)
    assert "import.meta.env.VITE_HOST" in out
    assert "wss://" not in out


def test_opting_in_to_string_stripping_suppresses_a_match_inside_a_string():
    events = [user_text("tidy up", 1),
              write_call("/repo/src/Panel.tsx", 'const s = "reaction(() => x, y)";\n', 2)]
    check = {
        "id": "no-reaction", "kind": "forbidden_pattern", "pattern": r"reaction\(",
        "applies_to": ["**/*.tsx"], "confidence": "high", "ignore_strings": True,
        "rule_ref": "1", "rule_text": "Never call reaction() in a component.",
        "self_test": {"should_match": ["  return reaction(() => s.v, run);"],
                      "should_not_match": ['const s = "reaction(";']},
    }
    loaded = rc.load_checks(doc(checks=[check]))
    assert not loaded["rejected"]
    corpus = rc.build_corpus(brv.tool_calls(events))
    findings = rc.evaluate_checks(loaded["checks"], corpus)
    # The strict view still sees the text inside the string, so the two views
    # disagree and the finding stays `unclear`. What matters is that it is never
    # `violated`: the check asked for string contents to be ignored.
    assert [f["state"] for f in findings] == ["unclear"]


def test_identifier_inside_a_block_comment_produces_no_violation():
    events = [user_text("tidy the store", 1),
              write_call("/repo/src/Panel.tsx",
                         "const a = 1;\n/* legacy notes:\n   reaction(() => s.v, run)\n*/\n", 2)]
    findings = rc.evaluate_checks([check()], corpus_for(events))
    assert not [f for f in findings if f["state"] == "violated"]


# ---------- strict vs normalised agreement ----------

def test_violation_requires_strict_and_normalised_to_agree():
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx", "reaction(() => s.v, run);\n", 2)]
    findings = rc.evaluate_checks([check()], corpus_for(events))
    assert [f["state"] for f in findings] == ["violated"]


def test_disagreement_yields_unclear_never_a_violation():
    """Present in the raw text, gone once comments are stripped: not provable."""
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx", "// reaction(() => s.v, run);\n", 2)]
    findings = rc.evaluate_checks([check()], corpus_for(events))
    assert [f["state"] for f in findings] == ["unclear"]


# ---------- citable spans ----------

def test_every_violation_carries_a_citable_span():
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx", "const x = 1;\nreaction(() => s.v, run);\n", 2)]
    f = [x for x in rc.evaluate_checks([check()], corpus_for(events))
         if x["state"] == "violated"][0]
    assert f["path"] == "/repo/src/Panel.tsx"
    assert f["match"].startswith("reaction(")
    assert f["checkId"] == "no-reaction"
    assert f["line"] == 2


def absence_check():
    return check(id="needs-observer", kind="required_pattern",
                 pattern=r"\bobserver\(", confidence="low",
                 self_test={"should_match": ["export const P = () => <div/>;"],
                            "should_not_match": ["export const P = observer(() => <div/>);"]})


def test_an_absence_candidate_cites_the_hunk_it_judged():
    """`required_pattern` fires on absence, so the only honest anchor is the
    hunk itself - but a finding with nothing at all to quote is not reportable."""
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "\nexport const P = () => <div/>;\n", 2)]
    f = rc.evaluate_checks([absence_check()], corpus_for(events))[0]
    assert f["state"] == "violated"
    assert f["match"] == "export const P = () => <div/>;"
    assert f["line"] == 2


def test_a_candidate_without_a_matched_span_is_not_a_violation():
    events = [user_text("go", 1), write_call("/repo/src/P.tsx", "   \n\n", 2)]
    findings = rc.evaluate_checks([absence_check()], corpus_for(events))
    assert all(f["state"] != "violated" for f in findings)


# ---------- the self-test gate ----------

def test_a_check_whose_self_tests_fail_is_rejected_at_load():
    """The generator's own claim that its tests pass is not evidence."""
    broken = check(id="order-wrong", kind="required_order",
                   first_pattern=r"makeAutoObservable", second_pattern=r"makePersistable",
                   self_test={
                       # Encodes the violation rather than the required order:
                       # the consumer's matcher reads this the other way round.
                       "should_match": ["makeAutoObservable(this);\nmakePersistable(this);"],
                       "should_not_match": ["makePersistable(this);\nmakeAutoObservable(this);"],
                   })
    loaded = rc.load_checks(doc(checks=[broken]))
    assert loaded["checks"] == []
    assert loaded["rejected"][0]["id"] == "order-wrong"
    assert "self-test" in loaded["rejected"][0]["reason"].lower()


def test_a_correct_required_order_check_survives_the_gate():
    ok = check(id="persist-after-observable", kind="required_order",
               first_pattern=r"makeAutoObservable", second_pattern=r"makePersistable",
               self_test={
                   "should_match": ["makePersistable(this);\nmakeAutoObservable(this);"],
                   "should_not_match": ["makeAutoObservable(this);\nmakePersistable(this);"],
               })
    loaded = rc.load_checks(doc(checks=[ok]))
    assert [c["id"] for c in loaded["checks"]] == ["persist-after-observable"]
    assert loaded["rejected"] == []


def test_a_rejected_check_reports_not_checkable_rather_than_being_applied():
    broken = check(id="order-wrong", kind="required_order",
                   first_pattern=r"makeAutoObservable", second_pattern=r"makePersistable",
                   self_test={"should_match": ["makeAutoObservable(this);\nmakePersistable(this);"],
                              "should_not_match": ["makePersistable(this);\nmakeAutoObservable(this);"]})
    loaded = rc.load_checks(doc(checks=[broken]))
    block = brv.parse_claude_md("## Reactions\n\nStores must persist after observing.\n")[0]
    events = [user_text("go", 1),
              write_call("/repo/src/s.ts", "makeAutoObservable(this);\nmakePersistable(this);\n", 2)]
    rcheck = rc.check_block(block, loaded, corpus_for(events))
    assert rcheck["state"] == "not-checkable"
    assert not rcheck["findings"]


def test_a_malformed_check_is_rejected_without_crashing():
    bad = [check(id="no-kind", kind="invent_your_own"),
           check(id="bad-regex", pattern="reaction(("),
           check(id="no-tests", self_test={"should_match": [], "should_not_match": []})]
    loaded = rc.load_checks(doc(checks=bad))
    assert loaded["checks"] == []
    assert {r["id"] for r in loaded["rejected"]} == {"no-kind", "bad-regex", "no-tests"}


# ---------- not_checkable rules ----------

def test_not_checkable_rule_renders_as_its_own_verdict():
    loaded = rc.load_checks(doc(not_checkable=[
        {"rule_ref": "Simplicity", "rule_text": "Prefer the simplest solution.",
         "why": "Matter of judgment."}]))
    block = brv.parse_claude_md("## Simplicity\n\nPrefer the simplest solution.\n")[0]
    events = [user_text("go", 1), write_call("/repo/src/a.ts", "const x = 1;\n", 2)]
    rcheck = rc.check_block(block, loaded, corpus_for(events))
    assert rcheck["state"] == "not-checkable"
    assert rcheck["findings"] == []
    assert "judgment" in rcheck["notCheckable"][0]["why"]


# ---------- inline suppression ----------

SUPPRESSED = ('// ctx-allow: no-reaction - deliberate, see ADR-14\n'
              'reaction(() => s.v, run);\n')


def test_inline_suppression_downgrades_a_violation_to_acknowledged():
    events = [user_text("go", 1), write_call("/repo/src/Panel.tsx", SUPPRESSED, 2)]
    findings = rc.evaluate_checks([check()], corpus_for(events))
    assert [f["state"] for f in findings] == ["acknowledged"]
    assert findings[0]["match"].startswith("reaction(")


def test_suppression_naming_a_different_check_does_not_apply():
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx",
                         "// ctx-allow: some-other-check\nreaction(() => s.v, run);\n", 2)]
    findings = rc.evaluate_checks([check()], corpus_for(events))
    assert [f["state"] for f in findings] == ["violated"]


def test_acknowledged_findings_do_not_make_the_block_violated():
    loaded = rc.load_checks(doc(checks=[check()]))
    block = brv.parse_claude_md("## Reactions\n\nNever call `reaction()` in a component.\n")[0]
    events = [user_text("go", 1), write_call("/repo/src/Panel.tsx", SUPPRESSED, 2)]
    rcheck = rc.check_block(block, loaded, corpus_for(events))
    assert rcheck["state"] == "acknowledged"


# ---------- fallback for docs with no checks file ----------

FALLBACK_MD = """## Store rules

Never import `AuthStore` directly into a component - go through the root store.
Applies to `*.tsx` files.
"""


def test_fallback_extraction_caps_confidence_at_low():
    block = brv.parse_claude_md(FALLBACK_MD)[0]
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "import { AuthStore } from './auth';\n", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert rcheck["source"] == "fallback"
    assert rcheck["findings"]
    assert all(f["confidence"] == "low" for f in rcheck["findings"])


def test_fallback_needs_a_backticked_identifier():
    block = brv.parse_claude_md("## Prose\n\nNever be careless about the details.\n")[0]
    events = [user_text("go", 1), write_call("/repo/src/P.tsx", "careless();\n", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert rcheck["state"] == "not-checkable"
    assert rcheck["findings"] == []


def test_fallback_ignores_a_backticked_word_that_is_not_code_shaped():
    """"Never guess a block into `undelivered`" is prose about a status name;
    matching it against source text is how a doc violates itself."""
    block = brv.parse_claude_md(
        "## Invariants\n\nNever guess a block into `undelivered`.\n")[0]
    events = [user_text("go", 1),
              write_call("/repo/a.py", "status = 'undelivered'\nundelivered = 1\n", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert rcheck["state"] == "not-checkable"


def test_fallback_can_be_refused_for_documents_that_are_not_guidelines():
    block = brv.parse_claude_md(FALLBACK_MD)[0]
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "import { AuthStore } from './auth';\n", 2)]
    assert rc.check_block(block, None, corpus_for(events), fallback=False) is None


def test_fallback_never_treats_a_code_identifier_as_a_shell_command():
    """The phantom-violation bug: `import` matched inside a ripgrep command."""
    block = brv.parse_claude_md(FALLBACK_MD)[0]
    events = [user_text("go", 1), bash("rg 'import AuthStore' src/", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert not [f for f in rcheck["findings"] if f["state"] == "violated"]


# ---------- rule keys ----------

def test_rule_key_is_stable_for_unchanged_text_and_changes_when_edited():
    a = rc.rule_key("Store rules", "Never import AuthStore directly.")
    assert a == rc.rule_key("Store rules", "Never import AuthStore directly.")
    assert a != rc.rule_key("Store rules", "Never import AuthStore lazily.")
    assert a != rc.rule_key("Other heading", "Never import AuthStore directly.")


def test_a_stale_rule_key_invalidates_its_check():
    block = brv.parse_claude_md("## Reactions\n\nNever call `reaction()` here.\n")[0]
    fresh = rc.rule_key(block["title"], block["content"])
    loaded_fresh = rc.load_checks(doc(checks=[check(rule_key=fresh)]))
    loaded_stale = rc.load_checks(doc(checks=[check(rule_key="deadbeefdeadbeef")]))
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx", "reaction(() => s.v, run);\n", 2)]
    corpus = corpus_for(events)
    assert rc.check_block(block, loaded_fresh, corpus)["state"] == "violated"
    stale = rc.check_block(block, loaded_stale, corpus)
    assert stale["state"] != "violated"
    assert stale["stale"]


# ---------- shell and path domains ----------

def test_forbidden_command_matches_only_shell_commands():
    shell_check = check(id="no-force-push", domain="shell", kind="forbidden_command",
                        pattern=r"git push\s+--force(?!-)", applies_to=[],
                        self_test={"should_match": ["git push --force origin main"],
                                   "should_not_match": ["git push origin main",
                                                        "git push --force-with-lease origin main"]})
    loaded = rc.load_checks(doc(checks=[shell_check]))
    events = [user_text("go", 1), bash("git push --force origin main", 2)]
    findings = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    assert [f["state"] for f in findings] == ["violated"]
    assert findings[0]["path"] == "(shell)"


def test_forbidden_path_matches_written_paths():
    path_check = check(id="no-tests-in-src", domain="path", kind="forbidden_path",
                       pattern=r"src/.*\.test\.ts$", applies_to=[],
                       self_test={"should_match": ["src/a.test.ts"],
                                  "should_not_match": ["tests/a.test.ts", "src/a.ts"]})
    loaded = rc.load_checks(doc(checks=[path_check]))
    events = [user_text("go", 1), write_call("src/a.test.ts", "it('x', () => {});\n", 2)]
    findings = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    assert [f["state"] for f in findings] == ["violated"]


def test_applies_to_globs_scope_source_checks():
    events = [user_text("go", 1),
              write_call("/repo/src/store.ts", "reaction(() => s.v, run);\n", 2)]
    assert rc.evaluate_checks([check()], corpus_for(events)) == []


# ---------- corpus construction ----------

def test_corpus_reads_write_content_edit_hunks_and_commands():
    events = [user_text("go", 1),
              write_call("/repo/a.ts", "const a = 1;\n", 2, tool_id="w1"),
              edit_call("/repo/a.ts", "const b = 2;\n", 3, tool_id="e1"),
              bash("pytest -q", 4)]
    c = corpus_for(events)
    texts = {e["path"]: e["text"] for e in c["code"]}
    assert "const a = 1;" in texts["/repo/a.ts"] and "const b = 2;" in texts["/repo/a.ts"]
    assert c["commands"] == ["pytest -q"]
    assert c["paths"] == ["/repo/a.ts"]


# ---------- a realistic checks file on disk ----------

def test_a_realistic_checks_file_loads_and_gates(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()` in a component.\n")
    payload = doc(checks=[check(), check(id="broken", kind="required_order",
                                         first_pattern="a", second_pattern="b",
                                         self_test={"should_match": ["a\nb"],
                                                    "should_not_match": ["b\na"]})],
                  not_checkable=[{"rule_ref": "Taste", "rule_text": "Keep it readable.",
                                  "why": "Judgment."}])
    (tmp_path / "GUIDELINES.md.checks.json").write_text(json.dumps(payload))
    loaded = rc.checks_for_doc(str(src))
    assert [c["id"] for c in loaded["checks"]] == ["no-reaction"]
    assert [r["id"] for r in loaded["rejected"]] == ["broken"]
    assert loaded["notCheckable"][0]["rule_ref"] == "Taste"


def test_no_checks_file_yields_none(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()`.\n")
    assert rc.checks_for_doc(str(src)) is None


# ---------- wiring into the block verdict ----------

def rule_file(abs_path, loaded=True):
    return {"loaded": loaded, "kind": "global", "path": "GUIDELINES.md",
            "abs_path": str(abs_path), "name": None}


def trace_for(events, prompt="do the thing"):
    return brv.build_trace(events, brv.tool_calls(events),
                           brv.assistant_text_segments(events), prompt)


def test_a_confirmed_violation_makes_the_block_ignored_and_cites_the_span(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()` in a component.\n")
    (tmp_path / "GUIDELINES.md.checks.json").write_text(json.dumps(doc(checks=[check()])))
    rc.checks_for_doc.cache_clear()
    events = [user_text("build the panel", 1),
              write_call("/repo/src/Panel.tsx", "reaction(() => s.v, run);\n", 2)]
    block = brv.parse_claude_md(src.read_text())[0]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    assert v["status"] == "ignored"
    assert v["ruleCheck"]["state"] == "violated"
    assert "Panel.tsx" in v["reason"]
    assert v["ruleCheck"]["findings"][0]["match"].startswith("reaction(")


def test_a_clean_run_against_the_same_check_is_not_a_violation(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()` in a component.\n")
    (tmp_path / "GUIDELINES.md.checks.json").write_text(json.dumps(doc(checks=[check()])))
    rc.checks_for_doc.cache_clear()
    events = [user_text("build the panel", 1),
              write_call("/repo/src/Panel.tsx", "autorun(() => s.v);\n", 2)]
    block = brv.parse_claude_md(src.read_text())[0]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    assert v["status"] != "ignored"
    assert v["ruleCheck"]["state"] == "clear"


def test_a_never_rule_about_code_no_longer_fires_off_a_shell_command():
    """The phantom violation this phase exists to kill: the word `import`
    appearing inside a ripgrep command is not a broken import rule."""
    md = "## Store rules\n\nNever import another store's singleton directly.\n"
    events = [user_text("find the usages", 1), bash("rg 'import' src/", 2)]
    block = brv.parse_claude_md(md)[0]
    v = brv.assess_block(block, {"loaded": True, "kind": "global", "path": "R.md",
                                 "abs_path": "/tmp/does-not-exist/R.md", "name": None},
                         trace_for(events, "find the usages"))
    assert v["status"] != "ignored"


def test_a_low_confidence_fallback_finding_never_paints_the_block_red(tmp_path):
    md = FALLBACK_MD
    src = tmp_path / "R.md"
    src.write_text(md)
    rc.checks_for_doc.cache_clear()
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "import { AuthStore } from './auth';\n", 2)]
    block = brv.parse_claude_md(md)[0]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    assert v["status"] != "ignored"
    assert v["ruleCheck"]["source"] == "fallback"
    assert v["ruleCheck"]["confidence"] == "low"


# ---------- a checks file in the shape the authoring prompt emits ----------

FIXTURE = Path(__file__).parent / "fixtures" / "frontend_mobx.md"


def mobx_checks():
    rc.checks_for_doc.cache_clear()
    return rc.checks_for_doc(str(FIXTURE))


def mobx_block(title):
    blocks = brv.parse_claude_md(FIXTURE.read_text())
    return next(b for b in blocks if b["title"] == title)


def test_the_fixture_checks_file_survives_the_gate_intact():
    loaded = mobx_checks()
    assert loaded["rejected"] == []
    assert {c["id"] for c in loaded["checks"]} == {
        "no-observer-with-memo", "persist-after-observable",
        "no-cross-store-singleton-import"}
    assert len(loaded["notCheckable"]) == 2


def test_the_fixture_finds_a_real_violation_with_a_span():
    events = [user_text("wrap the panel", 1),
              write_call("/repo/src/Panel.tsx",
                         "import { observer } from 'mobx-react-lite';\n"
                         "import { memo } from 'react';\n"
                         "export default memo(observer(Panel));\n", 2)]
    v = rc.check_block(mobx_block("Observer components"), mobx_checks(), corpus_for(events))
    assert v["state"] == "violated"
    f = v["findings"][0]
    assert f["checkId"] == "no-observer-with-memo"
    assert f["path"].endswith("Panel.tsx") and f["line"] == 3


def test_the_fixture_stays_quiet_on_compliant_code():
    events = [user_text("wrap the panel", 1),
              write_call("/repo/src/Panel.tsx",
                         "import { observer } from 'mobx-react-lite';\n"
                         "export default observer(Panel);\n", 2)]
    v = rc.check_block(mobx_block("Observer components"), mobx_checks(), corpus_for(events))
    assert v["state"] == "clear"


def test_the_fixture_downgrades_a_comment_only_mention_to_unclear():
    """The forbidden shape survives only in a comment, so the two views of the
    file disagree and nothing is reported as a violation."""
    events = [user_text("wrap the panel", 1),
              write_call("/repo/src/Panel.tsx",
                         "/* memo(observer(Panel)) was the old shape\n"
                         "   and is not allowed any more */\n"
                         "export default observer(Panel);\n", 2)]
    v = rc.check_block(mobx_block("Observer components"), mobx_checks(), corpus_for(events))
    assert v["state"] == "unclear"
    assert not [f for f in v["findings"] if f["state"] == "violated"]


def test_the_fixture_reports_its_not_checkable_rules_as_such():
    events = [user_text("go", 1), write_call("/repo/src/a.ts", "const x = 1;\n", 2)]
    v = rc.check_block(mobx_block("Keyed state"), mobx_checks(), corpus_for(events))
    assert v["state"] == "not-checkable"
    assert "failure signature" in v["notCheckable"][0]["why"]


# ---------- refusals that keep the checker honest ----------

def test_a_source_check_without_applies_to_is_refused():
    """With no globs every written file is in scope, including the .py and .md
    the rule never meant."""
    loaded = rc.load_checks(doc(checks=[check(applies_to=[])]))
    assert loaded["checks"] == []
    assert "applies_to" in loaded["rejected"][0]["reason"]


def test_a_non_dict_entry_in_the_checks_array_is_rejected_not_fatal():
    loaded = rc.load_checks({"source": "R.md", "checks": ["todo: write this"]})
    assert loaded["checks"] == []
    assert loaded["rejected"][0]["id"] == "(unnamed)"


def test_an_unreadable_checks_file_is_reported_on_every_block(tmp_path):
    src = tmp_path / "R.md"
    src.write_text("## Reactions\n\nNever call `reaction()` here.\n")
    (tmp_path / "R.md.checks.json").write_text("{ this is not json")
    rc.checks_for_doc.cache_clear()
    loaded = rc.checks_for_doc(str(src))
    block = brv.parse_claude_md(src.read_text())[0]
    events = [user_text("go", 1), write_call("/repo/src/a.tsx", "const x = 1;\n", 2)]
    v = rc.check_block(block, loaded, corpus_for(events))
    assert v["state"] == "not-checkable"
    assert "unreadable" in v["notCheckable"][0]["why"]


def test_prose_files_are_not_stripped_as_if_they_were_code():
    text = "See https://example.com/guide - don't skip it. reaction(x)\n"
    assert rc.strip_comments_and_strings(text, "notes.md") == text


def test_a_low_confidence_violation_is_not_promoted_by_a_high_confidence_bystander():
    """The red badge must follow the finding that fired, not the block's max."""
    quiet = check(id="high-but-quiet", confidence="high", pattern=r"\bautorun\(",
                  self_test={"should_match": ["autorun(() => s.v);"],
                             "should_not_match": ["reaction(() => s.v, run);"]})
    loud = check(id="low-and-firing", confidence="low", pattern=r"\breaction\(")
    loaded = rc.load_checks(doc(checks=[quiet, loud]))
    block = brv.parse_claude_md("## Reactions\n\nNever call `reaction()`.\n")[0]
    events = [user_text("go", 1),
              write_call("/repo/src/Panel.tsx", "reaction(() => s.v, run);\n", 2)]
    v = rc.check_block(block, loaded, corpus_for(events))
    assert v["state"] == "violated"
    assert v["confidence"] == "low"
    verdict = {"status": "dormant", "reason": "", "evidence": []}
    brv._apply_rule_check(verdict, v)
    assert verdict["status"] == "dormant"


def test_fallback_checks_never_run_against_prose_files():
    """An extracted identifier is most likely to be discussed in the very docs
    that state the rule, so unscoped fallback checks look only at code files."""
    block = brv.parse_claude_md(
        "## Store rules\n\nNever import `AuthStore` directly.\n")[0]
    events = [user_text("go", 1),
              write_call("/repo/notes/decisions.md",
                         "We decided to import AuthStore nowhere.\n", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert rcheck["findings"] == []
    assert rcheck["state"] == "not-exercised"


def test_a_rule_the_checks_file_does_not_cover_says_exactly_that():
    loaded = rc.load_checks(doc(checks=[check()]))
    block = brv.parse_claude_md("## Naming\n\nAlways name things well.\n")[0]
    events = [user_text("go", 1), write_call("/repo/src/a.tsx", "const x = 1;\n", 2)]
    v = rc.check_block(block, loaded, corpus_for(events))
    assert v["state"] == "not-checkable"
    assert "checks file says nothing about this rule" in v["notCheckable"][0]["why"]
