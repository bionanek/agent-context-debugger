"""Phase 13: the degradation contract, as a test rather than a convention.

Five of the signals this tool reads are optional - the ctxlog hook log,
readable extended thinking, the English frequency list, the ast-grep backend
and the opt-in judge tier - and every one of them is absent on somebody's
machine. The contract for all five is the same: absent, they degrade to
"signal unavailable", never to a worse verdict.

The failure this guards against is not the obvious one. Nobody writes code that
says "no ctxlog, therefore ignored". It happens the other way round: a signal
present is what *lifts* a block, so the code that reads it grows a branch whose
else-arm quietly answers the question anyway - and a machine without the log
then reports the honest silence as an accusation. That is a false red nobody
can reproduce, on a rule that was followed.

**What "worse" means here**, since a weaker answer is exactly what an absent
signal is supposed to produce:

  * an accusation the signal's presence did not make (`ignored`, or a
    rule-check state of `violated` / `acknowledged`) is worse;
  * a hard verdict of any sign - `used` as much as `ignored` - reached only
    because the signal is missing is worse, because a green invented by an
    absent signal is as wrong as a red;
  * losing information is *not* worse. `dormant`, `unused`, `not-checkable`
    and `no-lexical-trace` are what "signal unavailable" looks like, and each
    of them says in its own reason text that it is not evidence the rule was
    broken.

`OPTIONAL_SIGNALS` is the registry, and a test asserts the matrix covers it -
a signal added without a row here is a signal with no degradation contract.
"""
import json
import stat
from pathlib import Path

import pytest

import build_real_view as brv
import judge_tier
import lexical
import rule_checks as rc

from tests import lexical_fixture as lf
from tests.test_turns import (assistant_text, assistant_thinking,
                              assistant_tool_use, user_text)

# Every optional signal, and the row of this matrix that holds it to the
# contract. `test_the_matrix_covers_every_optional_signal` checks each named
# test still exists, so a row cannot be deleted or renamed away quietly - it
# cannot make anyone register a sixth signal, which is why the README and
# CLAUDE.md both say this dict is the registry.
OPTIONAL_SIGNALS = {
    "ctxlog": "test_ctxlog_absent_never_worsens_a_verdict",
    "readable-thinking": "test_readable_thinking_absent_never_worsens_a_verdict",
    "english-wordlist": "test_the_english_wordlist_absent_never_worsens_a_label",
    "ast-grep": "test_ast_grep_absent_reports_not_checkable_never_violated",
    "judge-tier": "test_the_judge_tier_off_never_worsens_a_verdict",
}

ACCUSING_STATUSES = {"ignored"}
ACCUSING_RULE_STATES = {"violated", "acknowledged"}
HARD_STATUSES = {"used", "ignored"}


def assert_not_worse(on, off, where):
    """The whole contract, for one block, in three assertions."""
    on_status, off_status = on["status"], off["status"]
    if off_status in ACCUSING_STATUSES:
        assert on_status in ACCUSING_STATUSES, (
            f"{where}: absent signal accuses ({off_status}) where the signal "
            f"present did not ({on_status}): {off['reason']}")
    if off_status in HARD_STATUSES:
        assert on_status in HARD_STATUSES, (
            f"{where}: absent signal reached {off_status}, a hard verdict the "
            f"signal present did not reach ({on_status}): {off['reason']}")
    off_state = (off.get("ruleCheck") or {}).get("state")
    on_state = (on.get("ruleCheck") or {}).get("state")
    if off_state in ACCUSING_RULE_STATES:
        assert on_state in ACCUSING_RULE_STATES, (
            f"{where}: absent signal reports {off_state} where the signal "
            f"present reports {on_state}")


def test_the_matrix_covers_every_optional_signal():
    here = Path(__file__).read_text()
    for signal, test_name in OPTIONAL_SIGNALS.items():
        assert f"def {test_name}(" in here, (signal, test_name)


# ---------- the ctxlog hook log ----------

def _instruction(path):
    return {"path": str(path), "memory_type": "Project",
            "load_reason": "session_start", "globs": None,
            "trigger_file_path": None, "parent_file_path": None,
            "ts": "2026-09-01T10:00:00+00:00", "stats": {}}


class _Args:
    skills_dir = None


# A path-conditional rule file, because that is the only file kind whose
# delivery the log actually decides: a project CLAUDE.md is loaded
# unconditionally, so a log that omits it says nothing.
CTXLOG_RULES = """---
paths: ["**/*.css"]
---

# Style rules

## Use logical properties

Prefer `margin-inline` over `margin-left` in every stylesheet.

## Order

Declare custom properties before the rules that read them.
"""


def test_ctxlog_absent_never_worsens_a_verdict(tmp_path):
    """The log can only ever take a claim away, never add one.

    Present, it is the one signal that can say a file on disk was never
    delivered - which is a strictly more careful answer. Absent, the loader
    falls back to the path conventions, and the danger is that the fallback
    starts *concluding* something about a file it has no evidence for.
    """
    doc = tmp_path / ".claude" / "rules" / "style.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(CTXLOG_RULES)
    events = [user_text("tidy the stylesheet", 1),
              assistant_text("Switched the rule to `margin-inline`.", 2)]
    trace = brv.build_trace(events, brv.tool_calls(events),
                            brv.assistant_text_segments(events), "tidy the stylesheet")

    def verdicts(hook_facts):
        rc.checks_for_doc.cache_clear()
        files = brv.load_context_files(events, [], str(tmp_path), _Args(),
                                       "tidy the stylesheet", hook_facts=hook_facts)
        f = next(x for x in files if x["abs_path"] == str(doc.resolve()))
        return {b["title"]: brv.assess_block(b, f, trace) for b in f["blocks"]}

    off = verdicts(None)
    # Both shapes a log can take, because they are the two answers the absence
    # has to be not-worse than. A log that names the document is the easy one;
    # a log that records other loads and *not* this one is the interesting one,
    # since that is the only way the tool can say a file on disk was never
    # delivered - and it is the answer the fallback must not manufacture.
    other = tmp_path / "CLAUDE.md"
    other.write_text("# Project\n\nSome prose.\n")
    for label, hook_facts in (
            ("named", {"instructions": [_instruction(doc)], "compactions": []}),
            ("omitted", {"instructions": [_instruction(other)], "compactions": []})):
        on = verdicts(hook_facts)
        assert set(on) == set(off)
        for title in on:
            assert_not_worse(on[title], off[title], f"ctxlog/{label}/{title}")
    # The omitted case really did produce the more careful answer, or the loop
    # above compared two identical runs and asserted nothing.
    omitted = verdicts({"instructions": [_instruction(other)], "compactions": []})
    assert {v["status"] for v in omitted.values()} == {"not-loaded"}
    assert "not-loaded" not in {v["status"] for v in off.values()}


# ---------- readable extended thinking ----------

THINKING_RULES = """# How to work

## Clipboard

Never pipe `echo` into `pbcopy`; use `printf` so the trailing newline is stripped.

## Decision Memory

Append every significant decision to `~/.claude/DECISIONS.md` before ending the session.

## Plain language

Lead with the outcome, then the mechanism.
"""


def _thinking_session(with_thinking):
    events = [user_text("copy the summary to the clipboard", 1)]
    if with_thinking:
        events.append(assistant_thinking(
            "The clipboard rule says printf rather than echo, and I should append a "
            "line to ~/.claude/DECISIONS.md when I am done.", 2))
    events += [assistant_text("Piped it through `printf` so no newline is appended.", 3),
               assistant_tool_use("Bash", {"command": "printf '%s' \"$x\" | pbcopy"}, 4,
                                  tool_id="b1")]
    return events


def test_readable_thinking_absent_never_worsens_a_verdict(tmp_path):
    """Thinking is readable on some model and CLI versions and not others.

    So it may add a corroboration card and nothing else. A status that moved
    with it would make the same session report differently on two machines,
    with no way for the reader to tell which answer to believe.
    """
    doc = tmp_path / "CLAUDE.md"
    doc.write_text(THINKING_RULES)
    file = {"loaded": True, "kind": "global", "path": str(doc),
            "abs_path": str(doc), "name": None}

    def verdicts(with_thinking):
        rc.checks_for_doc.cache_clear()
        events = _thinking_session(with_thinking)
        trace = brv.build_trace(events, brv.tool_calls(events),
                                brv.assistant_text_segments(events),
                                "copy the summary to the clipboard")
        return {b["title"]: brv.assess_block(b, file, trace)
                for b in brv.parse_claude_md(THINKING_RULES)}

    on, off = verdicts(True), verdicts(False)
    for title in on:
        assert_not_worse(on[title], off[title], f"thinking/{title}")
        # Stronger than the contract, and deliberately so: an optional signal
        # that may or may not be in the transcript must not decide a status at
        # all, in either direction.
        assert on[title]["status"] == off[title]["status"], title
        assert on[title]["reason"] == off[title]["reason"], title


# ---------- the English frequency list ----------

@pytest.fixture
def no_wordlist(monkeypatch):
    monkeypatch.setattr(lexical, "ZIPF_PATH", Path("/nonexistent/wordfreq-en.json"))
    lexical.english_zipf.cache_clear()
    lf.snapshot_corpus.cache_clear()
    lf._inline_corpus.cache_clear()
    yield
    lexical.english_zipf.cache_clear()
    lf.snapshot_corpus.cache_clear()
    lf._inline_corpus.cache_clear()


def test_the_english_wordlist_absent_never_worsens_a_label(no_wordlist):
    """Measured over the labelled set, not argued from the code.

    Without D2 every English word looks as rare as a coined one, so more terms
    survive weighting and more pairs become scorable. That is allowed to cost
    recall and to cost precision - what it may not do is drop precision below
    the gate, which would mean the absence of a convenience file had started
    manufacturing claims.

    The set is whatever this machine can resolve: without the author-private
    corpus that is the inline pairs alone, so the resolved count is asserted
    too rather than letting a shrunken set post the same green.
    """
    fixture = lf.load()
    metrics = lf.evaluate(fixture)
    floor = fixture["operatingPoint"]["minPrecision"]
    assert metrics["resolved"] >= lf.inline_pair_count(fixture), lf.report(metrics)
    assert metrics["precision"] is not None, lf.report(metrics)
    assert metrics["precision"] >= floor, lf.report(metrics)


def test_the_english_wordlist_absent_invents_no_false_positive():
    """The same claim per pair rather than in aggregate.

    A ratio over hundreds of pairs can absorb a new false positive; the pairs
    the run provably never touched cannot.
    """
    fixture = lf.load()
    baseline = lf.evaluate(fixture)
    assert baseline["resolved"] >= lf.inline_pair_count(fixture), lf.report(baseline)
    with_list = {r["id"]: r["predicted"] for r in baseline["rows"]}
    original = lexical.ZIPF_PATH
    lexical.ZIPF_PATH = Path("/nonexistent/wordfreq-en.json")
    lexical.english_zipf.cache_clear()
    lf.snapshot_corpus.cache_clear()
    lf._inline_corpus.cache_clear()
    try:
        rows = lf.evaluate(fixture)["rows"]
    finally:
        lexical.ZIPF_PATH = original
        lexical.english_zipf.cache_clear()
        lf.snapshot_corpus.cache_clear()
        lf._inline_corpus.cache_clear()
    for row in rows:
        if row["predicted"] not in lf.PREDICTED_POSITIVE:
            continue
        assert row["label"] in lf.TRUTH_POSITIVE, (
            f"{row['id']}: scored {row['predicted']} with no English list "
            f"(it scores {with_list[row['id']]} with it), but it is labelled "
            f"{row['label']} - {row['note']}")


# ---------- the ast-grep backend ----------

AST_SHIM = """#!/usr/bin/env python3
import json, sys
target = sys.argv[-1]
text = open(target, encoding="utf-8").read()
i = text.find("catch (e) { }")
out = []
if i >= 0:
    out.append({"text": "catch (e) { }", "file": target, "language": "TypeScript",
                "range": {"byteOffset": {"start": i, "end": i + 13}}})
print(json.dumps(out))
"""

AST_CHECK = {
    "id": "catch-not-empty",
    "rule_ref": "Error handling",
    "rule_text": "Never leave a catch body empty.",
    "domain": "source",
    "kind": "ast_forbidden",
    "ast_pattern": "catch ($$$ARGS) { }",
    "applies_to": ["**/*.ts"],
    "confidence": "high",
    "message": "This catch body swallows the error.",
    "statement": "Is any catch body empty?",
    "scope": "code",
    "evidence": "diff",
    "bucket": "deterministic",
    "examples_positive": ["try { go(); } catch (e) { }"],
    "examples_negative": ["try { go(); } catch (e) { report(e); }"],
    "self_test": {"should_match": ["try { go(); } catch (e) { }\n"],
                  "should_not_match": ["try { go(); } catch (e) { report(e); }\n"]},
}

EMPTY_CATCH_SRC = "export function go() {\n  try { run(); } catch (e) { }\n}\n"


def _ast_verdict(tmp_path, monkeypatch, binary):
    doc = tmp_path / "RULES.md"
    doc.write_text("# Rules\n\n## Error handling\n\nNever leave a catch body empty.\n")
    (tmp_path / "RULES.md.checks.json").write_text(
        json.dumps({"source": str(doc), "checks": [AST_CHECK]}))
    rc.checks_for_doc.cache_clear()
    if binary is None:
        monkeypatch.delenv(rc.AST_GREP_ENV, raising=False)
        monkeypatch.setattr(rc, "AST_GREP_DIR", tmp_path / "no-vendor")
    else:
        monkeypatch.setenv(rc.AST_GREP_ENV, str(binary))
    events = [user_text("add the handler", 1),
              assistant_tool_use("Write", {"file_path": str(tmp_path / "a.ts"),
                                           "content": EMPTY_CATCH_SRC}, 2, tool_id="w1")]
    trace = brv.build_trace(events, brv.tool_calls(events),
                            brv.assistant_text_segments(events), "add the handler")
    file = {"loaded": True, "kind": "project", "path": str(doc),
            "abs_path": str(doc), "name": None}
    block = next(b for b in brv.parse_claude_md(doc.read_text())
                 if b["title"] == "Error handling")
    return brv.assess_block(block, file, trace)


def test_ast_grep_absent_reports_not_checkable_never_violated(tmp_path, monkeypatch):
    """The one signal whose absence is most tempting to paper over.

    A regex for an empty catch body exists and almost works, so the failure
    mode here is a fallback wearing the same check id: the reader sees a badge
    that says the structural question was answered when it was not.
    """
    shim = tmp_path / "vendor" / "ast-grep"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text(AST_SHIM)
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)

    on = _ast_verdict(tmp_path, monkeypatch, shim)
    off = _ast_verdict(tmp_path, monkeypatch, None)

    assert on["ruleCheck"]["state"] == "violated", on["reason"]
    assert off["ruleCheck"]["state"] == "not-checkable", off["ruleCheck"]
    assert off["status"] not in ACCUSING_STATUSES, off["reason"]
    why = " ".join(e.get("why", "") for e in off["ruleCheck"]["notCheckable"])
    assert rc.AST_GREP_INSTALL in why, why
    assert_not_worse(on, off, "ast-grep")


# ---------- the judge tier ----------

HYBRID_CHECK = {
    "id": "catch-body-meaningful",
    "rule_ref": "Error handling",
    "rule_text": "Always implement the catch body.",
    "statement": "Does this catch body handle the error rather than swallow it?",
    "domain": "source",
    "kind": "candidate_requires",
    "candidate": "catch_block",
    "pattern": r"\w",
    "applies_to": ["**/*.ts"],
    "confidence": "high",
    "message": "This catch body swallows the error.",
    "scope": "code",
    "evidence": "diff",
    "bucket": "hybrid",
    "examples_positive": ["catch (e) { report(e); }"],
    "examples_negative": ["catch (e) { }"],
    "self_test": {"should_match": ["catch (e) { report(e); }\n"],
                  "should_not_match": []},
}


class _AlwaysViolated:
    def __call__(self, prompt, model):
        # The quote has to appear in the content the judge was shown, or the
        # tier downgrades the answer to `unclear` - which would leave this test
        # comparing two non-accusations and asserting nothing.
        return json.dumps({"verdict": "violated",
                           "evidence": "catch (e) {",
                           "why": "the body is empty"})


def test_the_judge_tier_off_never_worsens_a_verdict(tmp_path):
    """Off is the default, so its answer is the one almost everyone sees.

    A hybrid record parked for the judge must report as unchecked with the
    bucket named. The trap is the opposite of the usual one: the enumeration
    that finds the candidate sites runs either way, so it would be easy for the
    deterministic half to answer the judged question on its own.
    """
    doc = tmp_path / "RULES.md"
    doc.write_text("# Rules\n\n## Error handling\n\nAlways implement the catch body.\n")
    (tmp_path / "RULES.md.checks.json").write_text(
        json.dumps({"source": str(doc), "checks": [HYBRID_CHECK]}))
    rc.checks_for_doc.cache_clear()
    events = [user_text("add the handler", 1),
              assistant_tool_use("Write", {"file_path": str(tmp_path / "a.ts"),
                                           "content": EMPTY_CATCH_SRC}, 2, tool_id="w1")]
    file = {"loaded": True, "kind": "project", "path": str(doc),
            "abs_path": str(doc), "name": None}
    block = next(b for b in brv.parse_claude_md(doc.read_text())
                 if b["title"] == "Error handling")

    def verdict(judge):
        trace = brv.build_trace(events, brv.tool_calls(events),
                                brv.assistant_text_segments(events), "add the handler")
        trace["judge"] = judge
        return brv.assess_block(block, file, trace)

    on = verdict(judge_tier.Judge(model="test-model",
                                  cache=tmp_path / "judge-cache.json",
                                  invoke=_AlwaysViolated()))
    off = verdict(None)

    assert on["ruleCheck"]["state"] == "violated", on["ruleCheck"]
    assert off["ruleCheck"]["state"] == "not-checkable", off["ruleCheck"]
    assert off["status"] not in ACCUSING_STATUSES, off["reason"]
    assert off["ruleCheck"]["judged"], "a parked record has to say it was parked"
    assert_not_worse(on, off, "judge-tier")


# ---------- the judge off, and a user-authorised action ----------

class _AlwaysAuthorised:
    def __call__(self, prompt, model):
        return json.dumps({"verdict": "authorised",
                           "reason": "the prompt instructs this push"})


def test_the_judge_tier_off_never_acknowledges_an_authorised_action(tmp_path):
    """Signal unavailable, not a worse verdict - and honest about the cost.

    This is the one row of the matrix where the absent signal leaves an
    accusation standing, and it is deliberate: offline the finding keeps its
    `violated` state and the report prints the governing prompt beside the
    cited call, so the reader settles it in one glance. What must not happen
    is the other direction - the offline path quietly excusing a violation it
    has no evidence was authorised.
    """
    from tests.test_rule_checks import push_block, trace_for

    src, block = push_block(tmp_path)
    file = {"loaded": True, "kind": "project", "path": str(src),
            "abs_path": str(src), "name": None}
    events = [user_text("/commit and push to master", 1),
              assistant_tool_use("Bash", {"command": "git push origin master"}, 2,
                                 tool_id="b1")]

    def verdict(judge):
        trace = trace_for(events, "/commit and push to master")
        trace["judge"] = judge
        return brv.assess_block(block, file, trace)

    on = verdict(judge_tier.Judge(model="test-model",
                                  cache=tmp_path / "judge-cache.json",
                                  invoke=_AlwaysAuthorised()))
    off = verdict(None)

    assert on["ruleCheck"]["findings"][0]["state"] == "acknowledged"
    assert off["ruleCheck"]["findings"][0]["state"] == "violated"
    assert all("authorisation" not in f for f in off["ruleCheck"]["findings"])
    # The prompt is on the finding either way: it is read off the turn
    # structure, so switching the judge off costs the reader nothing to look at.
    assert (off["ruleCheck"]["findings"][0]["governingPrompt"]
            == on["ruleCheck"]["findings"][0]["governingPrompt"])


class _AlwaysCompliant:
    def __call__(self, prompt, model):
        return json.dumps({"verdict": "compliant", "evidence": "catch (e) {",
                           "reason": "the body reports the error"})


def test_the_judge_tier_off_never_contests_a_block(tmp_path):
    """`contested` is the judge's whole voice, so with the judge off it is silent.

    Silence is the right degradation: a block nobody asked a second opinion
    about must not read as a block two readers agreed on. And the flag may
    never move a verdict, so the status has to be identical either way.
    """
    doc = tmp_path / "RULES.md"
    doc.write_text("# Rules\n\n## Error handling\n\nAlways implement the catch body.\n")
    (tmp_path / "RULES.md.checks.json").write_text(
        json.dumps({"source": str(doc), "checks": [dict(HYBRID_CHECK, bucket="judged")]}))
    rc.checks_for_doc.cache_clear()
    events = [user_text("add the handler", 1),
              assistant_tool_use("Write", {"file_path": str(tmp_path / "a.ts"),
                                           "content": EMPTY_CATCH_SRC}, 2, tool_id="w1")]
    file = {"loaded": True, "kind": "project", "path": str(doc),
            "abs_path": str(doc), "name": None}
    block = next(b for b in brv.parse_claude_md(doc.read_text())
                 if b["title"] == "Error handling")

    def verdict(judge):
        trace = brv.build_trace(events, brv.tool_calls(events),
                                brv.assistant_text_segments(events), "add the handler")
        trace["judge"] = judge
        return brv.assess_block(block, file, trace)

    on = verdict(judge_tier.Judge(model="test-model",
                                  cache=tmp_path / "judge-cache.json",
                                  invoke=_AlwaysCompliant()))
    off = verdict(None)

    assert on["contested"], "the judge read this block as used; the flag has to say so"
    assert "contested" not in off
    assert on["status"] == off["status"], "the flag must never move a verdict"
    assert_not_worse(on, off, "judge-tier")
