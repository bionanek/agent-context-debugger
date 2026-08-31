"""Tests for hook facts overriding path conventions in load_context_files.

The distinction under test is *present on disk* versus *actually loaded*.
A conditional rule that never matched must read as `not-loaded`, not `dormant`
- and a session with no hook log must behave exactly as it did before.
"""
import json

import build_real_view as brv
import ctxlog_facts


class _Args:
    skills_dir = None


def make_rule(tmp_path, name="style.md", globs='["**/*.css"]'):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    p = rules / name
    p.write_text(
        f"---\npaths: {globs}\n---\n\n"
        "# Style rules\n\n"
        "## Use logical properties\n"
        "Prefer `margin-inline` over `margin-left`.\n"
    )
    return p


def instruction(path, load_reason="path_glob_match", **kw):
    rec = {
        "path": str(path),
        "memory_type": kw.get("memory_type", "Project"),
        "load_reason": load_reason,
        "globs": kw.get("globs"),
        "trigger_file_path": kw.get("trigger_file_path"),
        "parent_file_path": None,
        "ts": "2026-08-04T10:00:00+00:00",
        "stats": {},
    }
    return rec


def facts(*instructions):
    return {"instructions": list(instructions), "compactions": []}


def load_rule(tmp_path, hook_facts, rule_path):
    files = brv.load_context_files([], [], str(tmp_path), _Args(), "do the thing",
                                   hook_facts=hook_facts)
    return next(f for f in files if f["abs_path"] == str(rule_path.resolve()))


def statuses(tmp_path, hook_facts, rule_path):
    f = load_rule(tmp_path, hook_facts, rule_path)
    trace = brv.build_trace([], [], [], "do the thing")
    return [brv.assess_block(b, f, trace)["status"] for b in f["blocks"]]


# ---------- acceptance: the rule that never matched ----------

def test_rule_absent_from_the_log_is_not_loaded(tmp_path):
    p = make_rule(tmp_path)
    project_md = tmp_path / "CLAUDE.md"
    project_md.write_text("# Project\n\nSome prose.\n")
    hook_facts = facts(instruction(project_md, load_reason="session_start"))
    f = load_rule(tmp_path, hook_facts, p)
    assert f["loaded"] is False
    assert set(statuses(tmp_path, hook_facts, p)) == {"not-loaded"}


def test_rule_present_in_the_log_is_loaded_and_carries_its_reason(tmp_path):
    p = make_rule(tmp_path)
    trigger = tmp_path / "src" / "app.css"
    hook_facts = facts(instruction(p, globs=["**/*.css"], trigger_file_path=str(trigger)))
    f = load_rule(tmp_path, hook_facts, p)
    assert f["loaded"] is True
    assert f["hook"]["load_reason"] == "path_glob_match"
    assert f["hook"]["trigger_file_path"] == str(trigger)
    assert f["hook"]["globs"] == ["**/*.css"]
    assert "not-loaded" not in statuses(tmp_path, hook_facts, p)


# ---------- absence of hook data must change nothing ----------

def test_no_log_leaves_the_rule_loaded(tmp_path):
    p = make_rule(tmp_path)
    f = load_rule(tmp_path, None, p)
    assert f["loaded"] is True
    assert "hook" not in f
    assert "not-loaded" not in statuses(tmp_path, None, p)


def test_log_without_instruction_records_proves_nothing(tmp_path):
    p = make_rule(tmp_path)
    f = load_rule(tmp_path, facts(), p)
    assert f["loaded"] is True
    assert "hook" not in f


def test_project_claude_md_is_never_demoted_by_a_silent_log(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project\n\nSome prose.\n")
    other = tmp_path / ".claude" / "rules"
    other.mkdir(parents=True)
    (other / "other.md").write_text("# Other\n\nprose\n")
    hook_facts = facts(instruction(other / "other.md"))
    files = brv.load_context_files([], [], str(tmp_path), _Args(), "hi",
                                   hook_facts=hook_facts)
    proj = next(f for f in files if f["abs_path"] == str((tmp_path / "CLAUDE.md").resolve()))
    assert proj["loaded"] is True
    assert "hook" not in proj


def test_global_claude_md_is_never_demoted_by_a_silent_log(tmp_path):
    hook_facts = facts(instruction(tmp_path / "nothing.md"))
    files = brv.load_context_files([], [], str(tmp_path), _Args(), "hi",
                                   hook_facts=hook_facts)
    for f in files:
        if f["kind"] == "global":
            assert f["loaded"] is True


# ---------- payload shape ----------

def test_hook_block_is_emitted_only_when_a_fact_exists(tmp_path):
    p = make_rule(tmp_path)
    make_rule(tmp_path, name="quiet.md", globs='["**/*.ts"]')
    hook_facts = facts(instruction(p, trigger_file_path=str(tmp_path / "src" / "app.css")))
    payload = brv._compute_payload([], [], [], _Args(), tmp_path, hook_facts=hook_facts)
    by_path = {f["path"]: f for f in payload["contextFiles"]}
    matched = next(v for k, v in by_path.items() if k.endswith("style.md"))
    unmatched = next(v for k, v in by_path.items() if k.endswith("quiet.md"))
    assert matched["hook"] == {
        "memoryType": "Project",
        "loadReason": "path_glob_match",
        "globs": None,
        "triggerFile": "src/app.css",
    }
    assert "hook" not in unmatched
    assert unmatched["loaded"] is False


def test_hookless_payload_has_no_hook_keys(tmp_path):
    make_rule(tmp_path)
    payload = brv._compute_payload([], [], [], _Args(), tmp_path)
    assert all("hook" not in f for f in payload["contextFiles"])


def test_facts_read_from_a_real_log_file_match_by_resolved_path(tmp_path):
    p = make_rule(tmp_path)
    logs = tmp_path / "ctxlog"
    logs.mkdir()
    rec = dict(instruction(tmp_path / ".claude" / ".." / ".claude" / "rules" / "style.md",
                           trigger_file_path=str(tmp_path / "src" / "app.css")),
               event="InstructionsLoaded", session_id="s1")
    (logs / "s1.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    hook_facts = ctxlog_facts.load_facts("s1", ctxlog_dir=logs)
    f = load_rule(tmp_path, hook_facts, p)
    assert f["loaded"] is True
    assert f["hook"]["load_reason"] == "path_glob_match"


# ---------- session id derivation ----------

def test_session_facts_are_looked_up_by_transcript_stem(tmp_path, monkeypatch):
    seen = []

    def spy(session_id, ctxlog_dir=None):
        seen.append(session_id)
        return None

    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", spy)
    transcript = tmp_path / "abc-123.jsonl"
    transcript.write_text("")
    brv.process_session(transcript, _Args())
    assert seen == ["abc-123"]
