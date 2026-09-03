"""Tests for Phase 7: rule-record format v2, omission candidates, diff scoping.

Three separate claims are under test here, and each one is a failure the audits
or the external spec named:

* A record may declare what it is - a testable question, the scope it governs,
  the evidence it reads, the bucket that can decide it - and a v1 file that
  declares none of that keeps reporting exactly what it reported before.
* A rule violated by *omission* leaves no trace, so the pattern that would
  catch it is absent by definition. The sites have to be enumerated.
* A code rule reads the net effect of the session's writes, not every hunk it
  ever wrote: an attempt written and then reverted is not in the tree, and
  accusing the agent of it is a false violation.
"""
import json
from pathlib import Path

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import assistant_tool_use, user_text

from tests.test_rule_checks import (FIXTURE, bash, check, corpus_for, doc,
                                    edit_call, rule_file, trace_for, write_call)


# ---------- helpers ----------

def v2(**over):
    """A minimal, valid, deterministic v2 record."""
    base = check()
    base.update({
        "id": "no-reaction-v2",
        "statement": "Does any component call reaction()?",
        "scope": "code",
        "evidence": "diff",
        "bucket": "deterministic",
        "examples_positive": ["reaction(() => store.value, run);"],
        "examples_negative": ["autorun(() => store.value);"],
    })
    base.update(over)
    return base


def omission_check(**over):
    """`candidate_requires`: every catch site must do something with the error."""
    base = {
        "id": "catch-must-handle",
        "rule_ref": "Error handling",
        "rule_text": "Always implement the catch body.",
        "domain": "source",
        "kind": "candidate_requires",
        "candidate": "catch_block",
        "pattern": r"\b(logger|throw|return|report)\b",
        "applies_to": ["**/*.ts"],
        "confidence": "high",
        "message": "This catch body swallows the error.",
        "self_test": {
            "should_match": ["try { go(); } catch (e) { }\n"],
            "should_not_match": ["try { go(); } catch (e) { logger.warn(e); }\n"],
        },
    }
    base.update(over)
    return base


def ids(entries):
    return [e.get("id") for e in entries]


# ---------- v2 records load, v1 records are untouched ----------

def test_a_v2_record_loads_with_every_new_field():
    loaded = rc.load_checks(doc(checks=[v2()]))
    assert not loaded["rejected"] and not loaded["demoted"] and not loaded["judged"]
    (only,) = loaded["checks"]
    assert only["statement"].endswith("?")
    assert only["scope"] == "code" and only["evidence"] == "diff"
    assert only["bucket"] == "deterministic"
    assert only["examples_negative"]


def test_the_committed_v1_checks_file_loads_exactly_as_before():
    """The v1 fixture is the whole compatibility claim: same accepted, nothing new."""
    data = json.loads(FIXTURE.with_name(FIXTURE.name + ".checks.json").read_text())
    loaded = rc.load_checks(data)
    assert len(loaded["checks"]) == len(data["checks"])
    assert loaded["rejected"] == [] and loaded["demoted"] == [] and loaded["judged"] == []
    for c in loaded["checks"]:
        assert "bucket" not in c and "scope" not in c


def test_fixtures_is_accepted_as_the_v2_name_for_self_test():
    rec = v2()
    rec["fixtures"] = rec.pop("self_test")
    loaded = rc.load_checks(doc(checks=[rec]))
    assert loaded["checks"] and not loaded["rejected"]


def test_a_record_carrying_both_field_names_is_refused_not_silently_halved():
    """Gating on a stale copy would load a check whose real cases fail."""
    rec = v2()
    rec["fixtures"] = {"should_match": ["nope"], "should_not_match": ["nope"]}
    loaded = rc.load_checks(doc(checks=[rec]))
    assert not loaded["checks"] and not loaded["demoted"]
    assert "one field under two names" in loaded["rejected"][0]["reason"]


def test_a_record_carrying_neither_fixtures_nor_self_test_is_refused():
    rec = v2()
    rec.pop("self_test")
    loaded = rc.load_checks(doc(checks=[rec]))
    assert not loaded["checks"]
    assert "should_match" in loaded["rejected"][0]["reason"]


def test_an_unknown_scope_evidence_or_bucket_is_refused_not_guessed_at():
    for field, bad in (("scope", "vibes"), ("evidence", "telepathy"), ("bucket", "C")):
        loaded = rc.load_checks(doc(checks=[v2(**{field: bad})]))
        assert not loaded["checks"], field
        assert field in loaded["rejected"][0]["reason"], field


def test_a_source_kind_cannot_declare_transcript_evidence():
    loaded = rc.load_checks(doc(checks=[v2(evidence="transcript")]))
    assert not loaded["checks"]
    assert "cannot read" in loaded["rejected"][0]["reason"]


def test_a_tool_kind_cannot_declare_diff_evidence():
    rec = {
        "id": "gh-after-check", "rule_ref": "Accounts", "rule_text": "Check first.",
        "domain": "tool", "kind": "tool_never_without_prior",
        "pattern": r"^Bash gh\b", "prior_pattern": r"gh auth status",
        "confidence": "high", "message": "no", "bucket": "deterministic",
        "evidence": "diff",
        "self_test": {"should_match": ["Bash gh pr list"],
                      "should_not_match": ["Bash gh auth status\nBash gh pr list"]},
    }
    loaded = rc.load_checks(doc(checks=[rec]))
    assert not loaded["checks"]
    assert "cannot read" in loaded["rejected"][0]["reason"]


def test_a_v2_record_with_no_rule_ref_is_refused_not_left_unbindable():
    """A record that binds to no block is invisible on every screen, which is
    exactly the silent drop the demotion path exists to remove."""
    for rec in (v2(rule_ref=""), judged_record(rule_ref="  ")):
        loaded = rc.load_checks(doc(checks=[rec]))
        assert not loaded["checks"] and not loaded["judged"]
        assert "rule_ref" in loaded["rejected"][0]["reason"]


def test_examples_must_be_lists_of_strings():
    loaded = rc.load_checks(doc(checks=[v2(examples_negative="just one")]))
    assert not loaded["checks"]
    assert "examples_negative" in loaded["rejected"][0]["reason"]


# ---------- fixture verification demotes, it does not drop ----------

def broken_deterministic(**over):
    """A v2 record whose pattern does not do what its own fixtures claim."""
    return v2(id="broken", pattern=r"\bnever_appears\b", **over)


def test_a_v2_record_whose_fixtures_fail_is_demoted_to_judged_visibly():
    loaded = rc.load_checks(doc(checks=[broken_deterministic()]))
    assert not loaded["checks"]
    # Not a silent drop and not an anonymous refusal: it names the record, the
    # bucket it fell to, and the fixture that did not reproduce.
    (d,) = loaded["demoted"]
    assert d["id"] == "broken"
    assert d["fromBucket"] == "deterministic" and d["bucket"] == "judged"
    assert "fixture" in d["why"].lower()
    assert loaded["rejected"] == []


def test_a_v1_record_whose_selftests_fail_is_still_refused_not_demoted():
    """Demotion is the v2 path. Taking it for v1 would change every existing file."""
    rec = check(id="v1-broken", pattern=r"\bnever_appears\b")
    assert "bucket" not in rec
    loaded = rc.load_checks(doc(checks=[rec]))
    assert not loaded["checks"] and loaded["demoted"] == []
    assert ids(loaded["rejected"]) == ["v1-broken"]


def test_a_demoted_record_reaches_the_block_saying_it_was_demoted(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()` in a component.\n")
    (tmp_path / "GUIDELINES.md.checks.json").write_text(
        json.dumps(doc(checks=[broken_deterministic(rule_ref="Reactions")])))
    rc.checks_for_doc.cache_clear()
    block = brv.parse_claude_md(src.read_text())[0]
    events = [user_text("build it", 1), write_call("/repo/src/P.tsx", "const a = 1;\n", 2)]
    loaded = rc.checks_for_doc(str(src))
    out = rc.check_block(block, loaded, corpus_for(events))
    assert out["state"] == "not-checkable"
    assert ids(out["demoted"]) == ["broken"]
    rc.checks_for_doc.cache_clear()


# ---------- the judged buckets are parked, never rendered as followed ----------

def judged_record(**over):
    base = {
        "id": "be-direct", "rule_ref": "How to talk to me",
        "rule_text": "Answer first, zero fluff.",
        "bucket": "judged",
        "scope": "communication",
        "evidence": "transcript",
        "statement": "Does the reply open with a one-sentence answer?",
        "examples_positive": ["Yes - the cache was never invalidated."],
        "examples_negative": ["Great question! Let me walk you through the layers."],
    }
    base.update(over)
    return base


def test_a_judged_record_is_parked_and_says_the_judge_is_off():
    loaded = rc.load_checks(doc(checks=[judged_record()]))
    assert not loaded["checks"] and not loaded["rejected"]
    (j,) = loaded["judged"]
    assert j["bucket"] == "judged"
    assert "judge" in j["why"].lower()


def test_a_parked_record_makes_the_block_not_checkable_never_clear(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## How to talk to me\n\nAlways answer first, with zero fluff.\n")
    (tmp_path / "GUIDELINES.md.checks.json").write_text(
        json.dumps(doc(checks=[judged_record()])))
    rc.checks_for_doc.cache_clear()
    block = brv.parse_claude_md(src.read_text())[0]
    out = rc.check_block(block, rc.checks_for_doc(str(src)), corpus_for([]))
    assert out["state"] == "not-checkable"
    assert ids(out["judged"]) == ["be-direct"]
    rc.checks_for_doc.cache_clear()


def test_a_judged_record_with_no_negative_example_is_refused():
    loaded = rc.load_checks(doc(checks=[judged_record(examples_negative=[])]))
    assert not loaded["judged"]
    assert "examples_negative" in loaded["rejected"][0]["reason"]


def test_a_judged_record_with_no_statement_is_refused():
    loaded = rc.load_checks(doc(checks=[judged_record(statement="  ")]))
    assert not loaded["judged"]
    assert "statement" in loaded["rejected"][0]["reason"]


def test_a_hybrid_record_must_name_a_candidate_kind():
    loaded = rc.load_checks(doc(checks=[judged_record(bucket="hybrid")]))
    assert not loaded["judged"]
    assert "candidate" in loaded["rejected"][0]["reason"]
    ok = rc.load_checks(doc(checks=[judged_record(bucket="hybrid",
                                                  candidate="catch_block")]))
    assert ids(ok["judged"]) == ["be-direct"]


# ---------- candidate enumeration ----------

def entry(text, path="src/a.ts"):
    return [{"path": path, "text": text}]


def test_every_catch_block_is_a_candidate_with_a_citable_span():
    text = ("try { a(); } catch (e) { }\n"
            "function f() {\n"
            "  try { b(); } catch (err) {\n"
            "    logger.warn(err);\n"
            "  }\n"
            "}\n")
    cands = rc.enumerate_candidates("catch_block", entry(text))
    assert len(cands) == 2
    assert [c["line"] for c in cands] == [1, 3]
    assert all(c["path"] == "src/a.ts" for c in cands)
    # A site is citable: the header is quotable text at a real line.
    assert cands[0]["match"].startswith("catch (e)")
    # And the body is what a rule about the body gets to look at.
    assert not cands[0]["text"].strip()
    assert "logger.warn" in cands[1]["text"]


def test_a_python_except_block_is_a_candidate():
    text = ("def f():\n"
            "    try:\n"
            "        go()\n"
            "    except ValueError:\n"
            "        pass\n"
            "    return 1\n")
    (cand,) = rc.enumerate_candidates("catch_block", entry(text, "tool.py"))
    assert cand["line"] == 4
    assert "pass" in cand["text"]
    # The body stops at the dedent: `return 1` belongs to the function.
    assert "return 1" not in cand["text"]


def test_a_commented_out_catch_is_not_a_candidate():
    """The extractor reads the stripped view, so dead code is not a site."""
    text = "// try { a(); } catch (e) { }\nconst x = 1;\n"
    assert rc.enumerate_candidates("catch_block", entry(text)) == []


def test_a_comment_only_catch_body_is_still_an_empty_body():
    text = "try { a(); } catch (e) { /* nothing to do */ }\n"
    (cand,) = rc.enumerate_candidates("catch_block", entry(text))
    assert not cand["text"].strip()


def test_every_comment_is_a_candidate_including_continuation_lines():
    text = ("const a = 1; // first\n"
            "/* a block\n"
            "   spanning lines */\n"
            "const b = 2;\n")
    cands = rc.enumerate_candidates("comment", entry(text))
    # One site per line, so every site has a line a reader can go and check -
    # the block comment's continuation line included.
    assert [c["line"] for c in cands] == [1, 2, 3]
    assert cands[0]["text"] == "// first"
    assert "spanning lines" in cands[2]["text"]
    # A comment's own internal spaces stay inside its site rather than
    # splitting it into one candidate per word.
    assert cands[1]["text"] == "/* a block"


def test_a_nul_byte_in_the_source_is_not_read_as_one_long_comment():
    """The extractor's sentinel must be checked against the original text."""
    text = "const a = '\x00';\nconst b = 2; // real\n"
    cands = rc.enumerate_candidates("comment", entry(text))
    assert [c["text"] for c in cands] == ["// real"]


def test_a_handler_this_extractor_cannot_read_is_missed_not_guessed_at():
    """An un-enumerated site is `not-exercised`; a guessed body is an accusation."""
    assert rc.enumerate_candidates("catch_block",
                                   entry("try:\n    go()\nexcept E: pass\n", "t.py")) == []


def test_a_file_whose_language_is_unknown_yields_no_comment_candidates():
    """Guessing at comment syntax is how prose got read as code before."""
    assert rc.enumerate_candidates("comment", entry("# heading\n", "NOTES.md")) == []


def test_candidates_are_scoped_by_the_globs_the_check_names():
    entries = entry("try { a(); } catch (e) { }\n") + entry(
        "try { a(); } catch (e) { }\n", "test/a.spec.ts")
    assert len(rc.enumerate_candidates("catch_block", entries)) == 2
    scoped = rc.enumerate_candidates("catch_block", entries, ["src/**"])
    assert [c["path"] for c in scoped] == ["src/a.ts"]


def test_sites_from_two_dialects_are_still_reported_in_file_order():
    """The two extractors are scanned separately; unsorted, a finding list
    holding both would not run down the file the reader is following."""
    text = ("try:\n"
            "    go()\n"
            "except ValueError:\n"
            "    pass\n"
            "# catch (e) { } would be dead code here\n")
    text = "try { a(); } catch (e) { }\n" + text
    cands = rc.enumerate_candidates("catch_block", entry(text, "tool.py"))
    assert [c["line"] for c in cands] == sorted(c["line"] for c in cands)


def test_an_unknown_candidate_kind_enumerates_nothing_rather_than_guessing():
    assert rc.enumerate_candidates("dragons", entry("try {} catch (e) {}\n")) == []


def test_candidate_requires_cites_the_site_that_omitted_the_body():
    loaded = rc.load_checks(doc(checks=[omission_check()]))
    assert loaded["checks"], loaded["rejected"]
    events = [user_text("wire it up", 1),
              write_call("/repo/src/net.ts",
                         "try { go(); } catch (e) { }\n"
                         "try { go2(); } catch (e) { logger.warn(e); }\n", 2)]
    findings = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    (f,) = [f for f in findings if f["state"] == "violated"]
    assert f["path"] == "/repo/src/net.ts" and f["line"] == 1
    assert "catch (e)" in f["match"]


def test_candidate_requires_is_clear_when_every_site_complies():
    loaded = rc.load_checks(doc(checks=[omission_check()]))
    events = [user_text("wire it up", 1),
              write_call("/repo/src/net.ts",
                         "try { go(); } catch (e) { report(e); }\n", 2)]
    corpus = corpus_for(events)
    assert rc.evaluate_checks(loaded["checks"], corpus) == []
    assert rc._in_scope(loaded["checks"], corpus)


def test_candidate_requires_with_no_sites_is_not_exercised_not_clear():
    """No catch block written means the rule was never tested, not obeyed."""
    loaded = rc.load_checks(doc(checks=[omission_check()]))
    events = [user_text("wire it up", 1),
              write_call("/repo/src/net.ts", "const a = 1;\n", 2)]
    assert not rc._in_scope(loaded["checks"], corpus_for(events))


def test_a_candidate_check_naming_an_unknown_candidate_kind_is_refused():
    loaded = rc.load_checks(doc(checks=[omission_check(candidate="dragons")]))
    assert not loaded["checks"]
    assert "candidate" in loaded["rejected"][0]["reason"]


def test_an_acknowledged_omission_is_not_a_violation():
    loaded = rc.load_checks(doc(checks=[omission_check()]))
    events = [user_text("wire it up", 1),
              write_call("/repo/src/net.ts",
                         "try { go(); } catch (e) { } // ctx-allow: catch-must-handle\n", 2)]
    (f,) = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    assert f["state"] == "acknowledged"


# ---------- evidence scoping: the net diff, not every hunk ----------

def net_paths(events):
    return {e["path"]: e["text"] for e in corpus_for(events)["final_code"]}


def test_a_write_superseded_by_a_later_write_leaves_only_the_later_one():
    events = [user_text("go", 1),
              write_call("/repo/a.ts", "const bad = 1;\n", 2, tool_id="w1"),
              write_call("/repo/a.ts", "const good = 1;\n", 3, tool_id="w2")]
    assert net_paths(events) == {"/repo/a.ts": "const good = 1;\n"}
    # Every hunk is still available to a check that asks for it.
    assert "const bad" in corpus_for(events)["code"][0]["text"]


def test_content_written_then_reverted_is_not_in_the_final_diff():
    events = [
        user_text("go", 1),
        assistant_tool_use("Edit", {"file_path": "/repo/a.ts", "old_string": "x",
                                        "new_string": "reaction(() => s.v, run);"}, 2,
                               tool_id="e1"),
        assistant_tool_use("Edit", {"file_path": "/repo/a.ts",
                                        "old_string": "reaction(() => s.v, run);",
                                        "new_string": "autorun(() => s.v);"}, 3,
                               tool_id="e2"),
    ]
    net = net_paths(events)["/repo/a.ts"]
    assert "reaction(" not in net and "autorun(" in net


def test_a_file_written_and_then_emptied_drops_out_of_the_final_diff():
    events = [
        user_text("go", 1),
        write_call("/repo/a.ts", "const bad = 1;\n", 2, tool_id="w1"),
        assistant_tool_use("Edit", {"file_path": "/repo/a.ts",
                                        "old_string": "const bad = 1;\n",
                                        "new_string": ""}, 3, tool_id="e1"),
    ]
    assert net_paths(events) == {}


def test_the_two_code_corpora_cover_the_same_set_of_paths():
    """`final_code` is `code` after replay, so it must not key itself
    differently - a check switching corpora would change its own scope."""
    events = [
        user_text("go", 1),
        write_call("/repo/a.ts", "const a = 1;\n", 2, tool_id="w1"),
        assistant_tool_use("NotebookEdit", {"notebook_path": "/repo/nb.ipynb",
                                            "new_source": "print(1)"}, 3, tool_id="n1"),
        bash("ls", 4),
    ]
    corpus = corpus_for(events)
    assert ([e["path"] for e in corpus["final_code"]]
            == [e["path"] for e in corpus["code"]])


def test_a_code_rule_does_not_fire_on_an_abandoned_attempt():
    """The acceptance criterion: a reverted attempt is not in the tree."""
    loaded = rc.load_checks(doc(checks=[check()]))
    events = [
        user_text("go", 1),
        assistant_tool_use("Edit", {"file_path": "/repo/src/P.tsx", "old_string": "x",
                                        "new_string": "reaction(() => s.v, run);"}, 2,
                               tool_id="e1"),
        assistant_tool_use("Edit", {"file_path": "/repo/src/P.tsx",
                                        "old_string": "reaction(() => s.v, run);",
                                        "new_string": "autorun(() => s.v);"}, 3,
                               tool_id="e2"),
    ]
    corpus = corpus_for(events)
    assert rc.evaluate_checks(loaded["checks"], corpus) == []
    # The reverted text is still in `code`, which is why the default had to move.
    assert "reaction(" in corpus["code"][0]["text"]


def test_evidence_files_opts_back_into_every_hunk_the_session_wrote():
    loaded = rc.load_checks(doc(checks=[v2(evidence="files")]))
    events = [
        user_text("go", 1),
        assistant_tool_use("Edit", {"file_path": "/repo/src/P.tsx", "old_string": "x",
                                        "new_string": "reaction(() => s.v, run);"}, 2,
                               tool_id="e1"),
        assistant_tool_use("Edit", {"file_path": "/repo/src/P.tsx",
                                        "old_string": "reaction(() => s.v, run);",
                                        "new_string": "autorun(() => s.v);"}, 3,
                               tool_id="e2"),
    ]
    (f,) = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    assert f["state"] == "violated"


def test_a_reverted_catch_block_is_not_a_candidate_site():
    """Candidate enumeration reads the same net diff the checks do."""
    loaded = rc.load_checks(doc(checks=[omission_check()]))
    events = [
        user_text("go", 1),
        write_call("/repo/src/net.ts", "try { go(); } catch (e) { }\n", 2, tool_id="w1"),
        write_call("/repo/src/net.ts", "try { go(); } catch (e) { report(e); }\n", 3,
                   tool_id="w2"),
    ]
    corpus = corpus_for(events)
    assert rc.evaluate_checks(loaded["checks"], corpus) == []
    assert len(rc.enumerate_candidates("catch_block", corpus["code"])) == 2


def test_in_scope_reads_the_same_corpus_the_check_does():
    """A check whose net diff is empty is not-exercised, never clear."""
    loaded = rc.load_checks(doc(checks=[check()]))
    events = [
        user_text("go", 1),
        write_call("/repo/src/P.tsx", "reaction(() => s.v, run);\n", 2, tool_id="w1"),
        assistant_tool_use("Edit", {"file_path": "/repo/src/P.tsx",
                                        "old_string": "reaction(() => s.v, run);\n",
                                        "new_string": ""}, 3, tool_id="e1"),
    ]
    corpus = corpus_for(events)
    assert corpus["code"] and not corpus["final_code"]
    assert not rc._in_scope(loaded["checks"], corpus)


def test_a_shell_rule_still_reads_the_transcript(tmp_path):
    """Scoping moved the code corpus only; a command is a transcript fact."""
    shell = {
        "id": "no-echo-pbcopy", "rule_ref": "Copy to clipboard",
        "rule_text": "Never pipe echo into pbcopy.",
        "domain": "shell", "kind": "forbidden_command",
        "pattern": r"echo[^|]*\|\s*pbcopy", "confidence": "high",
        "message": "Use printf, not echo.",
        "bucket": "deterministic", "scope": "process", "evidence": "transcript",
        "statement": "Was pbcopy fed by echo?",
        "examples_positive": ['echo "x" | pbcopy'],
        "examples_negative": ["printf '%s' \"$x\" | pbcopy"],
        "self_test": {"should_match": ['echo "x" | pbcopy'],
                      "should_not_match": ["printf '%s' \"$x\" | pbcopy"]},
    }
    loaded = rc.load_checks(doc(checks=[shell]))
    assert loaded["checks"], loaded["rejected"]
    events = [user_text("copy it", 1), bash('echo "x" | pbcopy', 2)]
    (f,) = rc.evaluate_checks(loaded["checks"], corpus_for(events))
    assert f["state"] == "violated"


# ---------- the block's own evidence says it too ----------

def test_a_demoted_and_a_parked_record_both_reach_the_block_evidence(tmp_path):
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Reactions\n\nNever call `reaction()` in a component.\n")
    (tmp_path / "GUIDELINES.md.checks.json").write_text(
        json.dumps(doc(checks=[broken_deterministic(rule_ref="Reactions"),
                               judged_record(rule_ref="Reactions")])))
    rc.checks_for_doc.cache_clear()
    events = [user_text("build it", 1), write_call("/repo/src/P.tsx", "const a = 1;\n", 2)]
    block = brv.parse_claude_md(src.read_text())[0]
    verdict = brv.assess_block(block, rule_file(src), trace_for(events))
    labels = " ".join(e["label"] for e in verdict["evidence"])
    assert "broken" in labels and "demoted" in labels
    assert "be-direct" in labels
    rc.checks_for_doc.cache_clear()
