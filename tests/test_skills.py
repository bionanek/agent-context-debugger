"""Tests for skill identity (listing names, plugin prefixes) and loading evidence.

Phase 2: the skill roster must keep plugin prefixes intact, and "loaded" must
be driven by what actually invoked the skill (Skill tool call, then command
wrapper, then a word-boundary slash in the prompt).
"""
import argparse

import build_real_view as brv

from tests.test_turns import (
    _ts,
    assistant_text,
    assistant_tool_use,
    user_slash,
    user_text,
)


# ---------- event builders ----------

def skill_listing(lines, i, skill_count=None):
    return {"type": "attachment", "timestamp": _ts(i),
            "attachment": {"type": "skill_listing",
                           "skillCount": skill_count if skill_count is not None else len(lines),
                           "content": "\n".join(lines)}}


def _args(skills_dir):
    return argparse.Namespace(skills_dir=skills_dir)


def _write_skill(base, name, body="# Skill\n\nSome instructions.\n"):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body)
    return d / "SKILL.md"


# ---------- listing parsing ----------

def test_plugin_skill_line_keeps_prefix():
    events = [skill_listing(
        ["- datadog:ddsetup: First-time initialization of the plugin's MCP server."], 1)]
    out = brv.extract_attachments(events)
    assert out["skill_listing"] == [{
        "name": "datadog:ddsetup",
        "description": "First-time initialization of the plugin's MCP server.",
    }]


def test_five_sibling_plugin_skills_stay_distinct():
    names = ["ddsetup", "ddconfig", "ddtoolsets", "ddviz", "datadog-app"]
    events = [skill_listing([f"- datadog:{n}: description for {n}" for n in names], 1)]
    out = brv.extract_attachments(events)
    assert [e["name"] for e in out["skill_listing"]] == [f"datadog:{n}" for n in names]
    assert out["skill_listing"][3]["description"] == "description for ddviz"


def test_listing_line_without_description():
    events = [skill_listing(["- anthropic-skills:explain-usage"], 1)]
    out = brv.extract_attachments(events)
    assert out["skill_listing"] == [{"name": "anthropic-skills:explain-usage",
                                     "description": ""}]


def test_listing_description_containing_colon_does_not_split_the_name():
    events = [skill_listing(["- commit: Create a commit: right account, right style."], 1)]
    out = brv.extract_attachments(events)
    assert out["skill_listing"][0]["name"] == "commit"
    assert out["skill_listing"][0]["description"] == "Create a commit: right account, right style."


# ---------- prompt matching ----------

def test_longer_slash_token_does_not_trigger_shorter_skill():
    assert brv._is_triggered("cp", "run /cpanel now") is False


def test_bare_first_word_does_not_trigger_skill():
    assert brv._is_triggered("commit", "commit the change for me") is False


def test_word_boundary_slash_triggers():
    assert brv._is_triggered("commit", "please /commit this") is True
    assert brv._is_triggered("cp", "/cp") is True


def test_plugin_prefix_slash_does_not_trigger_the_plugin_name():
    assert brv._is_triggered("datadog", "/datadog:ddsetup please") is False
    assert brv._is_triggered("datadog:ddsetup", "/datadog:ddsetup please") is True


def test_path_mentioning_skill_name_does_not_trigger():
    assert brv._is_triggered("cp", "look at ~/.claude/skills/cp/SKILL.md") is False


# ---------- loading evidence ----------

def _skill_file(files, name):
    return next(f for f in files if f.get("name") == name)


def test_model_invoked_skill_counts_as_loaded(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "graphify")
    events = [
        user_text("build me a knowledge graph of this repo", 1),
        assistant_tool_use("Skill", {"skill": "graphify"}, 2),
    ]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _args(skills),
                                   brv.first_real_user_prompt(events))
    assert _skill_file(files, "graphify")["loaded"] is True


def test_skill_not_invoked_at_all_is_not_loaded(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "graphify")
    events = [user_text("graphify the repo", 1), assistant_text("no", 2)]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _args(skills),
                                   brv.first_real_user_prompt(events))
    assert _skill_file(files, "graphify")["loaded"] is False


def test_command_wrapper_marks_skill_loaded(tmp_path):
    skills = tmp_path / "skills"
    _write_skill(skills, "graphify")
    events = [user_slash("/graphify", "this repo", 1), assistant_text("ok", 2)]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _args(skills),
                                   brv.first_real_user_prompt(events))
    assert _skill_file(files, "graphify")["loaded"] is True


def test_model_invoked_skill_produces_trigger_moment_citing_the_call(tmp_path):
    events = [
        user_text("build me a knowledge graph of this repo", 1),
        assistant_tool_use("Skill", {"skill": "graphify"}, 2),
        assistant_text("Running the graph build.", 3),
    ]
    calls = brv.tool_calls(events)
    prompt = brv.first_real_user_prompt(events)
    trace = brv.build_trace(events, calls, brv.assistant_text_segments(events), prompt)
    block = {"title": "graphify", "content": "Turn any input into a knowledge graph."}
    file = {"name": "graphify", "kind": "skill", "abs_path": "/x/graphify/SKILL.md"}
    moments = brv._moments_for_skill_or_command(block, file, trace, trace["segs"], "skill")
    trigger = moments[0]
    assert trigger["kind"] == "trigger"
    assert trigger["verdict"] == "yes"
    assert "Skill" in trigger["label"]
    assert "graphify" in trigger["text"]


def test_substring_prompt_match_does_not_produce_a_trigger_moment(tmp_path):
    events = [user_text("open /cpanel for me", 1), assistant_text("ok", 2)]
    calls = brv.tool_calls(events)
    prompt = brv.first_real_user_prompt(events)
    trace = brv.build_trace(events, calls, brv.assistant_text_segments(events), prompt)
    block = {"title": "cp", "content": "Copy the last response to the clipboard."}
    file = {"name": "cp", "kind": "skill", "abs_path": "/x/cp/SKILL.md"}
    moments = brv._moments_for_skill_or_command(block, file, trace, trace["segs"], "skill")
    assert [m["kind"] for m in moments] == ["non-event"]


# ---------- listing-driven file resolution ----------

def test_two_plugin_skills_of_one_plugin_stay_separate_phantoms(tmp_path):
    events = [
        skill_listing(["- fakeplug:alpha: does alpha", "- fakeplug:beta: does beta"], 1),
        user_text("hello", 2),
    ]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _args(tmp_path / "skills"),
                                   brv.first_real_user_prompt(events))
    phantoms = [f for f in files if f["source"] == "listing-only"]
    assert sorted(f["name"] for f in phantoms) == ["fakeplug:alpha", "fakeplug:beta"]


def test_plugin_skill_resolves_under_the_plugin_cache(tmp_path):
    cache = tmp_path / "cache"
    skill_dir = cache / "marketplace" / "datadog" / "0.7.17" / "skills" / "ddsetup"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ddsetup\n")
    found = brv._resolve_plugin_skill("datadog:ddsetup", cache_dir=cache)
    assert found == skill_dir / "SKILL.md"


def test_plugin_skill_resolution_prefers_the_newest_version(tmp_path):
    cache = tmp_path / "cache"
    older = cache / "m" / "datadog" / "0.7.14" / "skills" / "ddsetup"
    newer = cache / "m" / "datadog" / "0.7.17" / "skills" / "ddsetup"
    for d in (older, newer):
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# ddsetup\n")
    import os
    os.utime(older / "SKILL.md", (1000, 1000))
    os.utime(newer / "SKILL.md", (2000, 2000))
    assert brv._resolve_plugin_skill("datadog:ddsetup", cache_dir=cache) == newer / "SKILL.md"


def test_non_plugin_name_is_not_looked_up_in_the_plugin_cache(tmp_path):
    assert brv._resolve_plugin_skill("commit", cache_dir=tmp_path) is None


def test_listed_plugin_skill_uses_its_resolved_file(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    skill_dir = cache / "m" / "datadog" / "0.7.17" / "skills" / "ddsetup"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# ddsetup\n\nSet up the MCP server.\n")
    monkeypatch.setattr(brv, "DEFAULT_PLUGIN_CACHE_DIR", cache)
    events = [
        skill_listing(["- datadog:ddsetup: First-time initialization."], 1),
        user_text("hello", 2),
        assistant_tool_use("Skill", {"skill": "datadog:ddsetup"}, 3),
    ]
    calls = brv.tool_calls(events)
    files = brv.load_context_files(events, calls, str(tmp_path), _args(tmp_path / "skills"),
                                   brv.first_real_user_prompt(events))
    entry = _skill_file(files, "datadog:ddsetup")
    assert entry["source"] == "listing"
    assert entry["abs_path"] == str(skill_dir / "SKILL.md")
    assert entry["loaded"] is True
