"""Tests for Phase 8a: the rule compiler's onboarding surface.

The claim under test is not about judging at all - it is about what a project
that has never run the compiler is told. A rule with no reviewed check reports
`not-checkable`, which reads as "this rule cannot be checked" when the truth is
that nobody has compiled it yet. The first report is the onboarding step, so it
has to say how many rules are uncompiled and name the one command that fixes
them - in the baked payload and in `--query` alike, or the CLI and the page
describe the same project differently.

The loader-side gates are re-tested here against a record shaped exactly as the
guided flow emits it (statement, scope, evidence, bucket, both example lists,
fixtures, `rule_key`), because those gates are what make the flow's output
trustworthy without a human re-deriving every pattern.
"""
import json
from pathlib import Path

import build_real_view as brv
import rule_checks as rc

from tests.test_turns import _Args, _write_jsonl, assistant_tool_use, user_text

from tests.test_rule_checks import bash, doc

REPO = Path(__file__).resolve().parent.parent

# Three rule-stating sections and one that states nothing, so a count of rules
# can be told apart from a count of blocks.
RULE_DOC = """# Project rules

## Copy to clipboard

Never pipe `echo` into `pbcopy`; always use `printf`.

## Reactions

Never call `reaction()` in a component.

## Commits

Always run `yarn lint` before you commit.

## Architecture

The pipeline runs in order: discovery, parsing, assessment.
"""


def _session(tmp_path, monkeypatch, doc_text=RULE_DOC, checks=None, events=None):
    """A one-turn session in a project whose CLAUDE.md carries `doc_text`.

    HOME is redirected into the temp tree: the loader reads the global
    `~/.claude/CLAUDE.md` whatever the args say, and counting the rules of
    whoever runs the suite would make every count machine-dependent.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    (tmp_path / "CLAUDE.md").write_text(doc_text)
    if checks is not None:
        (tmp_path / "CLAUDE.md.checks.json").write_text(json.dumps(checks))
    rc.checks_for_doc.cache_clear()
    events = events or [user_text("do the thing", 0),
                        assistant_tool_use("Bash", {"command": "ls"}, 1)]
    p = _write_jsonl(tmp_path, events)
    monkeypatch.chdir(tmp_path)
    return brv.process_session(p, _Args())


def _project_doc(session_data):
    return next(f for f in session_data["ruleCompile"]["docs"]
                if f["kind"] == "project")


def _block(session_data, title):
    for f in session_data["contextFiles"]:
        for b in f["blocks"]:
            if b.get("title") == title:
                return b
    raise AssertionError(f"no block titled {title!r}")


def _query(summary, per_session, address, **kw):
    data = brv.build_data(str(Path.cwd()), [summary],
                          {summary["id"]: per_session}, summary["id"])
    return "\n".join(brv.run_query(data, address, **kw))


# ---------- a project with rule docs and no checks files ----------

def test_uncompiled_rules_are_counted_and_the_command_is_named(tmp_path, monkeypatch):
    summary, per_session = _session(tmp_path, monkeypatch)
    roll = per_session["ruleCompile"]
    d = _project_doc(per_session)
    assert d["rules"] == 3 and d["uncompiled"] == 3 and d["compiled"] == 0
    assert not d["checksFile"]
    assert roll["uncompiled"] >= 3
    assert "not compiled" in roll["hint"]
    assert rc.COMPILE_COMMAND in roll["hint"]
    assert "CLAUDE.md" in roll["hint"]


def test_the_session_summary_carries_the_counts_for_the_picker(tmp_path, monkeypatch):
    summary, per_session = _session(tmp_path, monkeypatch)
    # Cheap roll-up in the summary, the per-document breakdown in per_session:
    # the picker reads summaries.
    assert summary["ruleCompile"]["uncompiled"] == per_session["ruleCompile"]["uncompiled"]
    assert summary["ruleCompile"]["hint"] == per_session["ruleCompile"]["hint"]
    assert "docs" not in summary["ruleCompile"]


def test_query_session_prints_the_count_and_the_command(tmp_path, monkeypatch):
    summary, per_session = _session(tmp_path, monkeypatch)
    out = _query(summary, per_session, [summary["id"]])
    assert "not compiled" in out and rc.COMPILE_COMMAND in out


def test_the_sessions_listing_names_the_command_too(tmp_path, monkeypatch):
    """A fresh user's first command is the listing, so the hint has to be there."""
    summary, per_session = _session(tmp_path, monkeypatch)
    out = _query(summary, per_session, ["sessions"])
    assert rc.COMPILE_COMMAND in out


def test_a_block_with_no_checks_file_says_which_command_compiles_it(tmp_path, monkeypatch):
    """`not-checkable` alone reads as a limit of the tool. Both the block that
    was refused outright and the one the mechanical fallback guessed at carry
    the command, because neither has a reviewed check behind it."""
    summary, per_session = _session(tmp_path, monkeypatch)
    for title in ("Commits", "Reactions"):
        b = _block(per_session, title)
        assert rc.COMPILE_COMMAND in b["ruleCheck"]["hint"]
        texts = " ".join(e["text"] for e in b["evidence"])
        assert rc.COMPILE_COMMAND in texts, title
    out = _query(summary, per_session, [summary["id"], _block(per_session, "Commits")["id"]])
    assert "[todo]" in out and rc.COMPILE_COMMAND in out


def test_the_hint_is_absent_once_every_rule_is_compiled_or_reviewed(tmp_path, monkeypatch):
    """Silence is the honest answer only when nothing is left to compile."""
    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard")],
                 not_checkable=[{"rule_ref": "Reactions", "rule_text": "…",
                                 "why": "needs cross-file resolution"},
                                {"rule_ref": "Commits", "rule_text": "…",
                                 "why": "order is not expressible here"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    d = _project_doc(per_session)
    assert (d["compiled"], d["refused"], d["uncompiled"]) == (1, 2, 0)
    assert per_session["ruleCompile"]["hint"] == ""
    rc.checks_for_doc.cache_clear()


def test_a_reviewed_refusal_is_not_reported_as_uncompiled(tmp_path, monkeypatch):
    """A rule the compiler looked at and honestly refused is done, not pending."""
    checks = doc(not_checkable=[{"rule_ref": "Reactions", "rule_text": "…",
                                 "why": "no mechanical signature"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    d = _project_doc(per_session)
    assert d["refused"] == 1 and d["uncompiled"] == 2
    rc.checks_for_doc.cache_clear()


def test_a_document_that_states_no_rules_is_not_counted(tmp_path, monkeypatch):
    summary, per_session = _session(tmp_path, monkeypatch,
                                    doc_text="# Notes\n\nThe pipeline has four stages.\n")
    assert per_session["ruleCompile"]["docs"] == []
    assert per_session["ruleCompile"]["hint"] == ""


def test_every_cue_the_fallback_reads_also_counts_as_a_rule(tmp_path, monkeypatch):
    """A block the mechanical fallback is willing to accuse has to be counted.

    Otherwise a document reports every rule compiled and no pending work while
    the block under it carries a `/compile-rules` hint of its own.
    """
    doc_text = "# Legacy\n\nWe no longer call `legacyInit()` anywhere.\n"
    summary, per_session = _session(tmp_path, monkeypatch, doc_text=doc_text)
    assert _project_doc(per_session)["rules"] == 1
    assert rc.COMPILE_COMMAND in _block(per_session, "Legacy")["ruleCheck"]["hint"]


# ---------- the record shape the flow emits ----------

def _flow_record(**over):
    """A complete v2 record, shaped as the guided flow is told to emit it."""
    base = {
        "id": "clipboard-no-echo",
        "rule_ref": "Copy to clipboard",
        "rule_text": "Never pipe `echo` into `pbcopy`; always use `printf`.",
        "statement": "Was pbcopy fed from echo rather than printf?",
        "scope": "process",
        "evidence": "transcript",
        "bucket": "deterministic",
        "domain": "shell",
        "kind": "forbidden_command",
        "pattern": r"\becho\b[^|]*\|\s*(?:pbcopy|xclip|xsel)",
        "confidence": "high",
        "message": "echo piped to the clipboard - the rule requires printf.",
        "examples_positive": ['echo "$msg" | pbcopy'],
        "examples_negative": ["printf '%s' \"$msg\" | pbcopy", "echo done"],
        "fixtures": {
            "should_match": ['echo "$msg" | pbcopy'],
            "should_not_match": ["printf '%s' \"$msg\" | pbcopy", "echo done"],
        },
    }
    base.update(over)
    return base


def test_a_record_from_the_flow_passes_every_loader_gate():
    loaded = rc.load_checks(doc(checks=[_flow_record()]))
    assert loaded["rejected"] == [] and loaded["demoted"] == [] and loaded["judged"] == []
    assert [c["id"] for c in loaded["checks"]] == ["clipboard-no-echo"]


def test_the_flows_fixtures_are_rerun_here_not_trusted(tmp_path, monkeypatch):
    """A generator's claim that its fixtures pass is not evidence: the pilot
    found a check that passed its author's verification and failed this
    matcher's, because the two disagreed about the vocabulary."""
    broken = _flow_record(pattern=r"\bprintf\b")  # matches the compliant form
    loaded = rc.load_checks(doc(checks=[broken]))
    assert loaded["checks"] == []
    (only,) = loaded["demoted"]
    assert only["bucket"] == "judged" and only["fromBucket"] == "deterministic"
    assert "fixtures did not reproduce" in only["why"]


def test_a_flow_record_whose_rule_text_changed_is_skipped_as_stale(tmp_path):
    src = tmp_path / "CLAUDE.md"
    src.write_text("## Copy to clipboard\n\nNever pipe `echo` into `pbcopy`.\n")
    block = brv.parse_claude_md(src.read_text())[0]
    pinned = _flow_record(rule_key=rc.rule_key(block["title"], block["content"]))
    stale = _flow_record(rule_key="0" * 16)

    loaded = rc.load_checks(doc(checks=[pinned]))
    corpus = rc.build_corpus(brv.tool_calls([bash('echo "x" | pbcopy', 1)]))
    fresh = rc.check_block(block, loaded, corpus, doc_path=str(src))
    assert fresh["state"] == "violated" and not fresh["stale"]

    loaded = rc.load_checks(doc(checks=[stale]))
    out = rc.check_block(block, loaded, corpus, doc_path=str(src))
    assert out["checksApplied"] == []
    assert out["state"] == "not-checkable"
    (entry,) = out["stale"]
    assert "changed" in entry["why"]
    assert rc.COMPILE_COMMAND in out["hint"] and "CLAUDE.md" in out["hint"]
    # The compiled rule is not nagged about; only the unchecked one is.
    assert fresh["hint"] == ""


def test_the_stale_check_reaches_the_block_evidence_and_the_cli(tmp_path, monkeypatch):
    summary, per_session = _session(
        tmp_path, monkeypatch,
        checks=doc(checks=[_flow_record(rule_key="0" * 16)]),
        events=[user_text("copy it", 0), bash('echo "x" | pbcopy', 1)])
    b = _block(per_session, "Copy to clipboard")
    # Never applied to wording it was not written for: no violation, and the
    # stale record is named rather than left as silence.
    assert b["status"] != "ignored"
    labels = " ".join(e["label"] for e in b["evidence"])
    texts = " ".join(e["text"] for e in b["evidence"])
    assert "stale" in labels and rc.COMPILE_COMMAND in texts

    out = _query(summary, per_session, [summary["id"], b["id"]])
    assert "[stale]" in out and rc.COMPILE_COMMAND in out
    assert per_session["ruleCompile"]["stale"] == 1
    rc.checks_for_doc.cache_clear()


def test_a_rule_parked_for_the_judge_counts_as_answered_not_pending(tmp_path, monkeypatch):
    """The compiler did its job on a `judged` rule: it classified it. Nagging
    the reader to re-compile it would send them round a loop with no exit."""
    judged = {
        "id": "answer-first", "rule_ref": "Reactions",
        "rule_text": "Never call `reaction()` in a component.",
        "statement": "Was a reaction used where the rule forbids it?",
        "bucket": "judged", "scope": "code", "confidence": "low",
        "message": "…",
        "examples_positive": ["reaction(() => s.v, run);"],
        "examples_negative": ["autorun(() => s.v);"],
    }
    summary, per_session = _session(tmp_path, monkeypatch, checks=doc(checks=[judged]))
    d = _project_doc(per_session)
    assert d["refused"] == 1 and d["uncompiled"] == 2
    b = _block(per_session, "Reactions")
    assert b["ruleCheck"]["hint"] == ""
    assert b["ruleCheck"]["judged"], "the parked record still has to be named"
    rc.checks_for_doc.cache_clear()


def test_a_record_the_loader_could_not_use_leaves_the_rule_uncompiled(tmp_path, monkeypatch):
    """A demoted record produced no answer about the rule, so re-compiling is
    the fix - counting it as reviewed would hide a broken check as coverage."""
    broken = _flow_record(rule_ref="Reactions", pattern=r"\bprintf\b")
    summary, per_session = _session(tmp_path, monkeypatch, checks=doc(checks=[broken]))
    d = _project_doc(per_session)
    assert d["uncompiled"] == 3 and d["refused"] == 0
    b = _block(per_session, "Reactions")
    assert rc.COMPILE_COMMAND in b["ruleCheck"]["hint"]
    assert b["ruleCheck"]["demoted"]
    rc.checks_for_doc.cache_clear()


def test_the_counts_and_every_block_hint_tell_the_same_story(tmp_path, monkeypatch):
    """One state function behind both, so a document reported fully compiled can
    never sit above a block asking the reader to compile that very rule."""
    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard"),
                         _flow_record(id="stale-one", rule_ref="Commits",
                                      rule_key="0" * 16)],
                 not_checkable=[{"rule_ref": "Reactions", "rule_text": "…",
                                 "why": "needs cross-file resolution"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    d = _project_doc(per_session)
    assert (d["compiled"], d["stale"], d["refused"], d["uncompiled"]) == (1, 1, 1, 0)
    hinted = {t for t in ("Copy to clipboard", "Commits", "Reactions")
              if _block(per_session, t)["ruleCheck"]["hint"]}
    assert hinted == {"Commits"}
    rc.checks_for_doc.cache_clear()


# ---------- the flow itself ----------

def test_the_hint_names_a_command_this_repo_actually_ships():
    """The hint is only honest if the command exists: a report telling the user
    to run something that is not there is worse than reporting the gap."""
    name = rc.COMPILE_COMMAND.lstrip("/")
    cmd = REPO / ".claude" / "commands" / f"{name}.md"
    assert cmd.is_file(), f"{cmd} is missing"
    assert "prompts/translate-rules.md" in cmd.read_text()


def test_the_authoring_prompt_documents_what_the_loader_enforces():
    """A prompt that names a field the loader does not know, or omits one it
    requires, compiles a record that is refused at load - and nothing at check
    time can tell that the prompt was the cause."""
    prompt = (REPO / "prompts" / "translate-rules.md").read_text()
    for name in ("statement", "scope", "evidence", "bucket",
                 "examples_positive", "examples_negative", "fixtures", "rule_key"):
        assert name in prompt, f"the prompt never mentions `{name}`"
    for value in rc.BUCKETS + rc.SCOPES + rc.EVIDENCE_SOURCES + rc.CANDIDATE_KINDS:
        assert value in prompt, f"the prompt never mentions `{value}`"
    # A kind the prompt does not name is a kind nobody can author: the
    # vocabulary is closed, so the compiler only ever emits what it was told
    # about, and the rule quietly lands in `not_checkable` instead.
    for kind in rc.VOCABULARY:
        assert f"`{kind}`" in prompt, f"the prompt never names the kind `{kind}`"
    # The review gate is the whole point of a reviewable artifact.
    assert "review" in prompt.lower()


# ---------- the onboarding line counts documents, and the compile-status screen ----------

def _judged_flow_record(**over):
    """A complete v2 record in the `judged` bucket, as the flow emits one."""
    base = {
        "id": "no-reaction-judged",
        "rule_ref": "Reactions",
        "rule_text": "Never call `reaction()` in a component.",
        "statement": "Does any component call reaction()?",
        "scope": "code",
        "evidence": "diff",
        "bucket": "judged",
        "examples_positive": ["reaction(() => store.value, run);"],
        "examples_negative": ["autorun(() => store.value);"],
    }
    base.update(over)
    return base


def test_the_sessions_listing_counts_uncompiled_documents_not_rules(tmp_path, monkeypatch):
    """The reader's next action is "compile a document", so that is the unit.

    A count of rules tells them how much prose is unchecked; a count of
    documents tells them how many times to run the command.
    """
    summary, per_session = _session(tmp_path, monkeypatch)
    out = _query(summary, per_session, ["sessions"])
    assert "1 rule document not compiled" in out
    assert rc.COMPILE_COMMAND in out and "CLAUDE.md" in out
    rc.checks_for_doc.cache_clear()


def test_the_sessions_listing_is_silent_once_nothing_is_left_to_compile(tmp_path, monkeypatch):
    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard")],
                 not_checkable=[{"rule_ref": "Reactions", "rule_text": "…",
                                 "why": "needs cross-file resolution"},
                                {"rule_ref": "Commits", "rule_text": "…",
                                 "why": "order is not expressible here"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    out = _query(summary, per_session, ["sessions"])
    assert rc.COMPILE_COMMAND not in out
    rc.checks_for_doc.cache_clear()


def test_the_per_document_breakdown_names_the_bucket_mix(tmp_path, monkeypatch):
    """A document compiled entirely into `judged` is not offline-decidable.

    Counting it as "compiled" would report progress toward a decidable report
    that the checks file cannot deliver without the opt-in tier switched on.
    """
    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard"),
                         _judged_flow_record()],
                 not_checkable=[{"rule_ref": "Commits", "rule_text": "…",
                                 "why": "order is not expressible here"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    d = _project_doc(per_session)
    assert (d["deterministic"], d["judged"], d["notCheckable"]) == (1, 1, 1)
    assert d["state"] == "compiled"
    roll = per_session["ruleCompile"]
    assert roll["deterministic"] == 1 and roll["judged"] == 1
    rc.checks_for_doc.cache_clear()


def test_compile_status_lists_every_document_its_state_and_its_bucket_mix(tmp_path, monkeypatch):
    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard"),
                         _judged_flow_record()],
                 not_checkable=[{"rule_ref": "Commits", "rule_text": "…",
                                 "why": "order is not expressible here"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    out = _query(summary, per_session, ["sessions"], compile_status=True)
    assert "CLAUDE.md" in out
    assert "1 deterministic" in out and "1 judged" in out
    assert "1 reviewed as not checkable" in out
    rc.checks_for_doc.cache_clear()


def test_compile_status_round_trips_when_a_document_is_compiled(tmp_path, monkeypatch):
    """The acceptance criterion: compile a document, re-run, the line moves."""
    summary, per_session = _session(tmp_path, monkeypatch)
    before = _query(summary, per_session, ["sessions"], compile_status=True)
    assert "uncompiled" in before
    assert rc.COMPILE_COMMAND in before and "CLAUDE.md" in before

    checks = doc(checks=[_flow_record(rule_ref="Copy to clipboard")],
                 not_checkable=[{"rule_ref": "Reactions", "rule_text": "…",
                                 "why": "needs cross-file resolution"},
                                {"rule_ref": "Commits", "rule_text": "…",
                                 "why": "order is not expressible here"}])
    summary, per_session = _session(tmp_path, monkeypatch, checks=checks)
    after = _query(summary, per_session, ["sessions"], compile_status=True)
    assert "uncompiled" not in after
    assert rc.COMPILE_COMMAND not in after
    rc.checks_for_doc.cache_clear()
