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
        # A v1 field this tool no longer reads. It stays in the fixture on
        # purpose: string stripping is central and unconditional now, and a
        # checks file written against the old format must still load.
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


def test_string_contents_are_stripped_on_the_source_path():
    """Strings are blanked unconditionally now: leaving them standing was an
    opt-in nobody set, and a rule's own identifier quoted inside a string
    literal was reported as a violation of that rule, in red. The cost is
    stated in `strip_comments_and_strings`: a rule about what is *in* a string
    (an import path, a `className`) needs the syntax tree, not characters."""
    src = "import { rootStore } from '../stores/rootStore';"
    out = rc.strip_comments_and_strings(src, "Panel.tsx")
    assert "rootStore'" not in out
    assert out.startswith("import { rootStore } from ")
    assert len(out) == len(src)
    assert 'bg-[#f8f9f9]' not in rc.strip_comments_and_strings(
        '<div className="bg-[#f8f9f9]">', "Panel.tsx")


def test_only_the_comment_span_caller_keeps_string_contents():
    """`strip_strings=False` exists for `_comment_candidates` alone: it reads
    back what the stripper blanked, so blanking string contents with the same
    sentinel would report every string literal as a comment."""
    src = 'const s = "reaction(() => x, y)";'
    assert "reaction(" not in rc.strip_comments_and_strings(src, "a.tsx")
    assert "reaction(" in rc.strip_comments_and_strings(src, "a.tsx", strip_strings=False)


def test_a_url_inside_a_string_is_not_a_line_comment():
    """`//` in a URL used to blank the rest of the line, hiding real code from
    the checker. Boundaries are tracked, so blanking a string ends where the
    string does and the code after it survives."""
    src = "const url = 'https://api.example.com'; reaction(() => x, y);"
    assert "reaction(" in rc.strip_comments_and_strings(src, "a.ts")


def test_template_interpolations_are_code_not_string_content():
    """`${...}` holds executable code, so a template literal's interpolations
    stand while the literal text around them is blanked."""
    src = "const url = `wss://${import.meta.env.VITE_HOST}/ws`;"
    out = rc.strip_comments_and_strings(src, "a.ts")
    assert "import.meta.env.VITE_HOST" in out
    assert "wss://" not in out


def test_a_v1_record_reports_a_string_hit_as_unclear_through_the_loader():
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
    # The whole path, loader included: the strict view still sees the text
    # inside the string, so the two views disagree and the finding stays
    # `unclear`. The record's retired `ignore_strings` changes nothing either
    # way - stripping is unconditional now.
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


# ---------- strings are stripped centrally, for every check ----------

STRING_SHAPES = {
    "template literal": "const doc = `reaction(() => x, y)`;\n",
    "double quoted": 'const doc = "reaction(() => x, y)";\n',
    "single quoted": "const doc = 'reaction(() => x, y)';\n",
}


def test_a_match_only_inside_a_string_is_never_a_violation():
    """famigo F4: the rule's own identifier, quoted inside the very script the
    rule prescribes, reported in red. Stripping is unconditional now, so the
    strict and stripped views disagree and the finding is a candidate."""
    for shape, src in STRING_SHAPES.items():
        for record in (check(), check(ignore_strings=False)):
            events = [user_text("go", 1), write_call("/repo/src/P.tsx", src, 2)]
            findings = rc.evaluate_checks([record], corpus_for(events))
            assert [f["state"] for f in findings] == ["unclear"], (shape, record)


def test_the_same_pattern_outside_a_string_is_still_a_violation():
    """The positive control: without it the test above would pass on a pattern
    that matches nothing at all."""
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "reaction(() => x, y);\n", 2)]
    assert [f["state"] for f in rc.evaluate_checks([check()], corpus_for(events))] \
        == ["violated"]


def test_a_v1_record_carrying_a_retired_field_still_loads():
    """The retired fields are accepted and do nothing. Refusing one would turn
    every checks file written against the old format into unchecked rules."""
    loaded = rc.load_checks(doc(checks=[check(ignore_strings=True)]))
    assert [c["id"] for c in loaded["checks"]] == ["no-reaction"]
    assert loaded["rejected"] == []


def test_a_strict_match_the_stripped_view_loses_is_unclear():
    """The agreement rule, exercised directly: strict sees it, stripped does
    not, so nothing is called a violation."""
    src = 'const doc = "reaction(() => x, y)";\n'
    entry = {"path": "src/P.tsx", "text": src}
    assert "reaction(" in src
    assert "reaction(" not in rc.strip_comments_and_strings(src, entry["path"])
    assert rc._evaluate_source(check(), entry)["state"] == "unclear"


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


def test_a_fallback_finding_is_a_candidate_never_a_violation():
    """Nobody reviewed the pattern: it is a backticked token lifted out of the
    rule's own prose, and the exception clause two sentences later may well
    permit exactly what it matched. `unclear` is as far as that can go."""
    block = brv.parse_claude_md(FALLBACK_MD)[0]
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "AuthStore.load();\n", 2)]
    rcheck = rc.check_block(block, None, corpus_for(events))
    assert rcheck["source"] == "fallback"
    assert [f["state"] for f in rcheck["findings"]] == ["unclear"]
    assert rcheck["state"] == "unclear"
    assert "extracted mechanically" in rcheck["findings"][0]["message"]


def test_a_fallback_finding_leaves_the_block_out_of_the_red_states(tmp_path):
    """The badge and the rule line agree, at the baked-payload level: a
    mechanically extracted candidate neither turns the block `ignored` nor puts
    it in a rule-check state the page paints red."""
    src = tmp_path / "GUIDELINES.md"
    src.write_text(FALLBACK_MD)
    rc.checks_for_doc.cache_clear()
    events = [user_text("go", 1),
              write_call("/repo/src/P.tsx", "AuthStore.load();\n", 2)]
    v = brv.assess_block(brv.parse_claude_md(FALLBACK_MD)[0], rule_file(src),
                         trace_for(events))
    assert v["status"] != "ignored"
    assert v["ruleCheck"]["state"] == "unclear"
    assert not [f for f in v["ruleCheck"]["findings"]
                if f["state"] in ("violated", "acknowledged")]


def test_only_the_violated_rule_check_state_is_painted_red():
    """A vocabulary check, not a layout one: the page keys its red off the
    rule-check state, and `unclear` - the strongest thing a fallback finding
    can be - must not be one of the states that gets it."""
    red = [line.strip() for line in brv.HTML_TEMPLATE.splitlines()
           if ".rc-" in line and "var(--red)" in line]
    assert red, "no rule-check state is styled red; this check would pass vacuously"
    assert all(".rc-violated" in line for line in red), red


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


# ---------- review round: heading binding, suppression lines, dialects ----------

def test_a_rule_ref_binds_to_the_exact_heading_before_a_containing_one(tmp_path):
    """"Rules" is contained in "Global Claude Code Rules", but with an exact
    "Rules" heading in the document the record binds there alone."""
    src = tmp_path / "RULES.md"
    src.write_text("# Global Claude Code Rules\n\nNever call reaction().\n\n"
                   "## Rules\n\nNever call reaction() in a component.\n")
    (tmp_path / "RULES.md.checks.json").write_text(
        json.dumps(doc(checks=[check(rule_ref="Rules")])))
    rc.checks_for_doc.cache_clear()
    loaded = rc.checks_for_doc(str(src))
    glob_block, rules_block = brv.parse_claude_md(src.read_text())
    corpus = corpus_for([user_text("go", 1)])
    assert rc.check_block(rules_block, loaded, corpus)["checksApplied"] == ["no-reaction"]
    assert rc.check_block(glob_block, loaded, corpus)["checksApplied"] == []


def test_a_rule_ref_still_binds_by_containment_when_no_heading_is_exact(tmp_path):
    src = tmp_path / "RULES.md"
    src.write_text("## Reactions in components\n\nNever call reaction().\n")
    (tmp_path / "RULES.md.checks.json").write_text(json.dumps(doc(checks=[check()])))
    rc.checks_for_doc.cache_clear()
    loaded = rc.checks_for_doc(str(src))
    block = brv.parse_claude_md(src.read_text())[0]
    out = rc.check_block(block, loaded, corpus_for([user_text("go", 1)]))
    assert out["checksApplied"] == ["no-reaction"]


def test_suppression_is_found_on_the_line_the_finding_cites():
    """Line numbers count `\\n` only; a stray form feed must not shift which
    line the marker is looked for on."""
    text = "a\x0cb\x0cc\nd\n// ctx-allow: no-reaction\nreaction(x);\n"
    offset = text.index("reaction(")
    assert rc._line_of(text, offset) == 4
    assert rc._suppressed(text, offset, "no-reaction")


def test_a_css_url_is_not_a_line_comment():
    src = "a { background: url(http://x/y.png); } /* gone */\n"
    out = rc.strip_comments_and_strings(src, "a.css")
    assert "y.png" in out and "gone" not in out


def test_scss_keeps_its_line_comments():
    assert "gone" not in rc.strip_comments_and_strings("a { b: c; } // gone\n", "a.scss")


def test_shell_parameter_hashes_are_not_comments():
    src = 'echo "$#" $# args ${#v} kept # gone\n'
    out = rc.strip_comments_and_strings(src, "run.sh")
    assert "args" in out and "kept" in out and "gone" not in out


def test_code_written_by_a_heredoc_is_in_the_corpus_a_source_check_reads():
    """The structural joins credit a heredoc write; a source check has to be
    able to see the same code or it can never flag it."""
    events = [bash("cat > src/app.py <<'EOF'\nprint('debug')\nEOF", 1)]
    calls = brv.tool_calls(events)
    t = brv.build_trace(events, calls, brv.assistant_text_segments(events), "q")
    corpus = t["rule_corpus"]
    assert [e["path"] for e in corpus["code"]] == ["src/app.py"]
    assert "print('debug')" in corpus["final_code"][0]["text"]


# ---------- the governing prompt behind a cited call ----------
#
# `ctx-allow` lets written code carry a deliberate exception at the violation
# site. A transcript has no such marker, so the strongest rationale there is -
# the user typed the action in the prompt that caused the call - was invisible
# to the checker, and a reviewed, high-confidence rule red-badged an agent for
# doing what it was told. The join is positional: turns already run
# prompt-to-prompt and a tool finding already cites a call, so the prompt is
# the one of the turn the call falls in. Nothing here reads the prompt's words.

PUSH_RULE = "## Hard rules\n\n`master` takes code only through a PR with green CI.\n"


def push_check(**over):
    """The shape of the real `no-push-to-master` record this mechanism exists for."""
    base = {
        "id": "no-push-to-master",
        "rule_ref": "Hard rules",
        "rule_text": "`master` takes code only through a PR with green CI.",
        "domain": "tool",
        "kind": "tool_forbidden",
        "pattern": r"\bgit\s+push\b[^\n]*\bmaster\b",
        "applies_to": [],
        "confidence": "high",
        "message": "master is protected: land code through a PR, never a direct push.",
        "self_test": {
            "should_match": ["Bash git push origin master"],
            "should_not_match": ["Bash git push -u origin feat/posts"],
        },
    }
    base.update(over)
    return base


def push_block(tmp_path, checks=None):
    src = tmp_path / "GUIDELINES.md"
    src.write_text(PUSH_RULE)
    (tmp_path / "GUIDELINES.md.checks.json").write_text(
        json.dumps(doc(checks=checks or [push_check()])))
    rc.checks_for_doc.cache_clear()
    return src, brv.parse_claude_md(src.read_text())[0]


def test_a_finding_names_the_prompt_of_the_turn_its_call_falls_in(tmp_path):
    """Turn containment, not the nearest earlier prompt by event index.

    The first push here runs *before* any prompt was typed, which is the shape
    the two readings disagree about: the nearest earlier prompt is none at all,
    while the turn the call falls in is the first one, because a turn absorbs
    everything before its own prompt.
    """
    src, block = push_block(tmp_path)
    events = [bash("git push origin master", 0, tool_id="b0"),
              user_text("/commit and push to master", 1),
              bash("git push origin master", 2, tool_id="b1"),
              user_text("teraz wypchnij poprawke", 3),
              bash("git push --force origin master", 4, tool_id="b2")]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    findings = v["ruleCheck"]["findings"]
    assert [f["governingPrompt"]["text"] for f in findings] == [
        "/commit and push to master", "/commit and push to master",
        "teraz wypchnij poprawke"]
    assert [f["governingPrompt"]["turnIndex"] for f in findings] == [0, 0, 1]
    assert [f["governingPrompt"]["callIndex"] for f in findings] == [0, 1, 2]
    # Offline the finding is unchanged: the reader is shown the prompt and
    # settles it, and nothing downgrades itself without being asked.
    assert [f["state"] for f in findings] == ["violated"] * 3
    assert v["status"] == "ignored"


def test_a_call_in_a_turn_with_no_user_prompt_names_no_governing_prompt(tmp_path):
    """Absence must not read as authorisation.

    A task-notification arrives on the user channel but is the result half of a
    spawn, so it starts no turn. A session driven entirely by one has no prompt
    to cite, and the finding stays a violation with nothing beside it.
    """
    src, block = push_block(tmp_path)
    push = bash("git push origin master", 2)
    notified = [user_text("<task-notification><status>done</status></task-notification>", 1),
                push]
    # The control: the identical call under a real prompt does carry one, so
    # the assertion below cannot pass merely because the mechanism is absent.
    prompted = [user_text("push it", 1), push]
    assert (brv.assess_block(block, rule_file(src), trace_for(prompted))
            ["ruleCheck"]["findings"][0]["governingPrompt"]["text"] == "push it")

    v = brv.assess_block(block, rule_file(src), trace_for(notified, prompt=""))
    finding = v["ruleCheck"]["findings"][0]
    assert "governingPrompt" not in finding
    assert finding["state"] == "violated"
    assert v["status"] == "ignored"


def test_a_shell_finding_names_its_governing_prompt_too(tmp_path):
    """A `forbidden_command` red is as capable of being a false red as a tool one."""
    shell = push_check(id="no-push-shell", domain="shell", kind="forbidden_command",
                       pattern=r"\bgit\s+push\b[^\n]*\bmaster\b",
                       self_test={"should_match": ["git push origin master"],
                                  "should_not_match": ["git push -u origin feat/posts"]})
    src, block = push_block(tmp_path, checks=[shell])
    events = [user_text("push to master", 1), bash("git push origin master", 2)]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    governing = v["ruleCheck"]["findings"][0]["governingPrompt"]
    assert governing["text"] == "push to master"
    assert governing["turnIndex"] == 0 and governing["callIndex"] == 0


def test_a_forbidden_pattern_may_not_span_two_commands_in_one_call(tmp_path):
    """The false red this corpus was frozen to measure.

    The agent pushed a branch and then opened a PR against master. `&&` joins
    two commands that each stand on their own, and the call log renders a call
    as one line, so `git push \u2026 master` matched across the join and the run was
    accused of the one action it did not take. A pattern is about a command, so
    it may not span the point where one command ends and the next begins.
    """
    src, block = push_block(tmp_path)
    compound = ("git push -u origin docs/admin-posts-crud-spec 2>&1 | tail -2 "
                "&& git ls-remote --heads origin master | head -1 "
                "&& GH_TOKEN=$(gh auth token --user me) gh pr create --base master")
    v = brv.assess_block(block, rule_file(src),
                         trace_for([user_text("open the PR", 1), bash(compound, 2)]))
    assert [f["state"] for f in v["ruleCheck"]["findings"]] == ["not-exercised"]
    assert v["status"] != "ignored"

    # The control: the forbidden command on its own still reds, so the
    # assertion above cannot pass merely because the check stopped working.
    red = brv.assess_block(block, rule_file(src),
                           trace_for([user_text("push it", 1),
                                      bash("git push origin master", 2)]))
    assert red["ruleCheck"]["findings"][0]["state"] == "violated"
    assert red["status"] == "ignored"


def test_a_shell_pattern_may_not_span_two_commands_either(tmp_path):
    """The shell kinds read the same compound line and need the same bound."""
    shell = push_check(id="no-push-shell", domain="shell", kind="forbidden_command",
                       pattern=r"\bgit\s+push\b[^\n]*\bmaster\b",
                       self_test={"should_match": ["git push origin master"],
                                  "should_not_match": ["git push -u origin feat/posts"]})
    src, block = push_block(tmp_path, checks=[shell])
    compound = "git push -u origin feat/x && gh pr create --base master"
    v = brv.assess_block(block, rule_file(src),
                         trace_for([user_text("open the PR", 1), bash(compound, 2)]))
    assert [f["state"] for f in v["ruleCheck"]["findings"]] == []
    assert v["status"] != "ignored"

    red = brv.assess_block(block, rule_file(src),
                           trace_for([user_text("push it", 1),
                                      bash("git push origin master", 2)]))
    assert red["ruleCheck"]["findings"][0]["state"] == "violated"


# ---------- the join reads the same turns the rest of the payload does ----------

class _SessionArgs:
    claude_md = None
    skills_dir = None
    no_global = True
    no_skills = True
    no_project = False


def _compaction_session(tmp_path, monkeypatch):
    """A real session with a compaction between two pushes and a later prompt.

    A compaction carves an extra turn boundary, so the turn a call falls in is
    not the one a prompt-only split reports. The payload splits with the
    compaction; a join that splits without it numbers every later turn low and
    reports a turn number the drill-down and `--query` contradict.
    """
    (tmp_path / "CLAUDE.md").write_text(PUSH_RULE)
    (tmp_path / "CLAUDE.md.checks.json").write_text(
        json.dumps(doc(checks=[push_check()], source="CLAUDE.md")))
    rc.checks_for_doc.cache_clear()
    events = [user_text("/commit and push to master", 1),
              assistant_text("on it", 2),
              bash("git push origin master", 3, tool_id="b0"),
              assistant_text("pushed", 5),
              bash("git push origin master", 6, tool_id="b1"),
              user_text("now tidy the branch", 7),
              bash("git push --force origin master", 8, tool_id="b2")]
    p = tmp_path / "t.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in events))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: {
        "instructions": [],
        "compactions": [{"event": "PreCompact", "ts": "2026-01-01T00:00:04+00:00",
                         "trigger": "auto"}]})
    return brv.process_session(p, _SessionArgs())


def _push_findings(payload):
    for f in payload["contextFiles"]:
        for b in f.get("blocks") or []:
            for finding in (b.get("ruleCheck") or {}).get("findings") or []:
                yield finding


def test_the_governing_turn_number_is_the_one_the_payload_splits(tmp_path, monkeypatch):
    """The cited turn has to be the turn the drill-down shows, compaction and all."""
    _, per_session = _compaction_session(tmp_path, monkeypatch)
    # Four turns' worth of boundaries: two prompts plus the compaction.
    assert [t["index"] for t in per_session["turns"]] == [0, 1, 2]
    assert per_session["turns"][1]["afterCompaction"] is True
    findings = list(_push_findings(per_session))
    assert [f["governingPrompt"]["turnIndex"] for f in findings] == [0, 1, 2]


def test_a_compaction_carved_turn_still_names_the_prompt_in_flight(tmp_path, monkeypatch):
    """A carved turn holds no prompt of its own but is governed by one.

    Reporting nothing there is the "absence must not read as authorisation"
    case firing on a turn that *was* authorised - the prompt in flight is the
    one the payload already shows on the turn.
    """
    _, per_session = _compaction_session(tmp_path, monkeypatch)
    carved = per_session["turns"][1]
    assert carved["userPrompt"] == "/commit and push to master"
    findings = list(_push_findings(carved))
    assert len(findings) == 1
    assert findings[0]["governingPrompt"] == {
        "text": "/commit and push to master", "turnIndex": 1, "callIndex": 0}
