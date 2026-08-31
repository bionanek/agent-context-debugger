import json

import ctxlog_facts


SID = "sess-1"


def write_log(tmp_path, records, session_id=SID):
    p = tmp_path / f"{session_id}.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records))
    return p


def instr(path, **kw):
    rec = {
        "ts": kw.pop("ts", "2026-08-04T10:00:00+00:00"),
        "event": "InstructionsLoaded",
        "session_id": SID,
        "path": path,
        "memory_type": "User",
        "load_reason": "session_start",
        "globs": None,
        "trigger_file_path": None,
        "parent_file_path": None,
        "stats": {"size_bytes": 10, "lines": 2, "sha256": "abc"},
    }
    rec.update(kw)
    return rec


def test_missing_log_returns_none(tmp_path):
    assert ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path) is None


def test_missing_dir_returns_none(tmp_path):
    assert ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path / "nope") is None


def test_empty_session_id_returns_none(tmp_path):
    assert ctxlog_facts.load_facts("", ctxlog_dir=tmp_path) is None


def test_empty_log_returns_empty_facts(tmp_path):
    write_log(tmp_path, [])
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    assert facts is not None
    assert facts["instructions"] == []
    assert facts["compactions"] == []
    for key in ("nested_memories", "hook_directives", "skill_listing",
                "preloaded_files", "user_attached_files"):
        assert facts[key] == []
    assert facts["skill_listing_present"] is False
    assert facts["skill_count"] is None


def test_malformed_lines_are_skipped(tmp_path):
    p = tmp_path / f"{SID}.jsonl"
    good = json.dumps(instr(str(tmp_path / "A.md")))
    p.write_text(good + "\n{not json\n\n[1,2,3]\n" + good + "\n")
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    assert len(facts["instructions"]) == 2


def test_instruction_fields_present(tmp_path):
    target = tmp_path / "P.md"
    trigger = tmp_path / "src.py"
    parent = tmp_path / "root.md"
    write_log(tmp_path, [instr(
        str(target),
        memory_type="Project",
        load_reason="path_glob_match",
        globs=["src/**"],
        trigger_file_path=str(trigger),
        parent_file_path=str(parent),
        ts="2026-08-04T11:22:33+00:00",
    )])
    rec = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)["instructions"][0]
    assert rec["path"] == str(target.resolve())
    assert rec["memory_type"] == "Project"
    assert rec["load_reason"] == "path_glob_match"
    assert rec["globs"] == ["src/**"]
    assert rec["trigger_file_path"] == str(trigger.resolve())
    assert rec["parent_file_path"] == str(parent.resolve())
    assert rec["ts"] == "2026-08-04T11:22:33+00:00"
    assert rec["stats"]["lines"] == 2


def test_paths_are_resolved_and_absent_ones_stay_none(tmp_path):
    # A path that does not exist on disk must still normalise, not crash.
    write_log(tmp_path, [instr(str(tmp_path / "sub" / ".." / "ghost.md"))])
    rec = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)["instructions"][0]
    assert rec["path"] == str((tmp_path / "ghost.md").resolve())
    assert rec["trigger_file_path"] is None
    assert rec["parent_file_path"] is None


def test_missing_stats_becomes_empty_dict(tmp_path):
    rec = instr(str(tmp_path / "A.md"))
    del rec["stats"]
    write_log(tmp_path, [rec])
    out = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)["instructions"][0]
    assert out["stats"] == {}


def test_subagent_records_excluded(tmp_path):
    main = instr(str(tmp_path / "main.md"))
    sub = instr(str(tmp_path / "sub.md"), agent_id="a1", agent_type="explore")
    write_log(tmp_path, [main, sub])
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    paths = [r["path"] for r in facts["instructions"]]
    assert paths == [str((tmp_path / "main.md").resolve())]


def test_repeated_loads_preserved_in_order(tmp_path):
    path = str(tmp_path / "A.md")
    write_log(tmp_path, [
        instr(path, ts="2026-08-04T10:00:00+00:00"),
        instr(str(tmp_path / "B.md"), ts="2026-08-04T10:01:00+00:00"),
        instr(path, load_reason="compact", ts="2026-08-04T10:02:00+00:00"),
    ])
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    assert [r["load_reason"] for r in facts["instructions"]] == [
        "session_start", "session_start", "compact"]

    latest = ctxlog_facts.latest_by_path(facts)
    assert set(latest) == {str((tmp_path / "A.md").resolve()),
                           str((tmp_path / "B.md").resolve())}
    assert latest[str((tmp_path / "A.md").resolve())]["load_reason"] == "compact"


def test_latest_by_path_tolerates_none_and_empty():
    assert ctxlog_facts.latest_by_path(None) == {}
    assert ctxlog_facts.latest_by_path({}) == {}
    assert ctxlog_facts.latest_by_path({"instructions": []}) == {}


def test_compactions_collected(tmp_path):
    write_log(tmp_path, [
        instr(str(tmp_path / "A.md")),
        {"ts": "2026-08-04T10:05:00+00:00", "event": "PreCompact", "trigger": "auto"},
        {"ts": "2026-08-04T10:05:30+00:00", "event": "PostCompact", "trigger": "auto"},
    ])
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    assert facts["compactions"] == [
        {"event": "PreCompact", "ts": "2026-08-04T10:05:00+00:00", "trigger": "auto"},
        {"event": "PostCompact", "ts": "2026-08-04T10:05:30+00:00", "trigger": "auto"},
    ]


def test_compactions_empty_when_none(tmp_path):
    write_log(tmp_path, [instr(str(tmp_path / "A.md"))])
    assert ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)["compactions"] == []


def test_other_events_ignored(tmp_path):
    write_log(tmp_path, [
        {"ts": "t", "event": "SessionStart", "source": "startup"},
        {"ts": "t", "event": "UserPromptSubmit", "prompt_preview": "hi"},
        {"ts": "t", "event": "PostToolUse", "tool": "Read", "path": "/x"},
    ])
    facts = ctxlog_facts.load_facts(SID, ctxlog_dir=tmp_path)
    assert facts["instructions"] == []
    assert facts["compactions"] == []


def test_ctxlog_dir_env_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CTXLOG_DIR", str(tmp_path))
    write_log(tmp_path, [instr(str(tmp_path / "A.md"))])
    facts = ctxlog_facts.load_facts(SID)
    assert len(facts["instructions"]) == 1
