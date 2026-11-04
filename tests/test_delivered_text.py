"""Tests for judging a block against the text the model was actually given.

Phase 6. A verdict about a rule has to be a verdict about the rule as the
session received it: the file on disk today may carry sentences committed after
the session ended, and crediting the agent with following one of those is a
green nobody can defend.
"""
import build_real_view as brv

from tests.test_turns import (_Args, _write_jsonl, assistant_text,
                              assistant_tool_use, user_text, user_tool_result)


# ---------- event builders ----------

def read_result(tool_use_id, path, text, i, *, start_line=1, total_lines=None):
    """The harness's own record of what a `Read` handed the model."""
    lines = len(text.splitlines())
    return {
        "type": "user", "timestamp": f"2026-01-01T00:00:{i:02d}.000Z",
        "message": {"content": [{"type": "tool_result",
                                 "tool_use_id": tool_use_id,
                                 "content": text}]},
        "toolUseResult": {"type": "text", "file": {
            "filePath": str(path), "content": text,
            "startLine": str(start_line), "numLines": str(lines),
            "totalLines": str(total_lines if total_lines is not None else lines)}},
    }


def edit_result(tool_use_id, path, original, old, new, i):
    """An `Edit` result: the whole pre-edit file plus the hunk that replaced."""
    return {
        "type": "user", "timestamp": f"2026-01-01T00:00:{i:02d}.000Z",
        "message": {"content": [{"type": "tool_result",
                                 "tool_use_id": tool_use_id, "content": "ok"}]},
        "toolUseResult": {"filePath": str(path), "originalFile": original,
                          "oldString": old, "newString": new,
                          "replaceAll": False, "userModified": False,
                          "structuredPatch": []},
    }


def _run(tmp_path, monkeypatch, events, *, project_md=None, global_md=None,
         name="t.jsonl"):
    """Run one transcript against a fixture home and project directory.

    Re-runnable in the same `tmp_path`: block ids carry the project path, so a
    test comparing two runs' ids has to run both in one directory.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    if global_md is not None:
        (home / ".claude" / "CLAUDE.md").write_text(global_md)
    if project_md is not None:
        (proj / "CLAUDE.md").write_text(project_md)
    monkeypatch.setenv("HOME", str(home))
    p = _write_jsonl(proj, events, name=name)
    monkeypatch.chdir(proj)
    return brv.process_session(p, _Args())


def _block(scope, needle, title):
    f = next(f for f in scope["contextFiles"] if needle in f["path"])
    return next(b for b in f["blocks"] if b["title"] == title)


# The rule text as the session received it: it says nothing about any file.
DELIVERED = "# Docs\n\nkeep the docs honest\n"
# The rule as it stands on disk now, with a sentence added after the session.
# The added half prescribes a command rather than naming a file: a path a plain
# rule document names credits nothing any more (see `_document_executed`), so a
# noun would make this fixture's positive control unreachable for a reason that
# has nothing to do with delivered text.
ON_DISK = ("# Docs\n\nkeep the docs honest, and finish with:\n\n"
           "```bash\npytest -q\n```\n")


def _events(proj_md):
    """One turn: read the project CLAUDE.md, then run the command the disk
    version of it prescribes."""
    return [
        user_text("tidy the docs", 0),
        assistant_tool_use("Read", {"file_path": str(proj_md)}, 1, tool_id="r1"),
        read_result("r1", proj_md, DELIVERED, 2),
        assistant_tool_use("Bash", {"command": "pytest -q"}, 3, tool_id="w1"),
        user_tool_result("w1", "ok", 4),
        assistant_text("done", 5),
    ]


# ---------- test 1: the transcript's copy wins over the disk copy ----------

def test_a_block_is_judged_on_the_text_the_transcript_shows_delivered(
        tmp_path, monkeypatch):
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    _, per = _run(tmp_path, monkeypatch, _events(proj_md), project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["textSource"] == "transcript"
    assert b["content"].strip() == "keep the docs honest"
    # The disk sentence prescribes `pytest -q`, which the session really did
    # run. Judged on the delivered text there is no command to join to, so no
    # predicate.
    assert b["status"] != "used"
    assert "pytest" not in b["content"]


def test_the_same_run_against_the_delivered_wording_on_disk_does_score_used(
        tmp_path, monkeypatch):
    """Positive control: the predicate the case above must not derive really is
    derivable from the same run when the wording was the delivered one."""
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    events = _events(proj_md)
    events[2] = read_result("r1", proj_md, ON_DISK, 2)
    _, per = _run(tmp_path, monkeypatch, events, project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["textSource"] == "transcript"
    assert b["status"] == "used"
    assert "ran verbatim" in b["reason"]


# ---------- test 2: a document the session itself rewrote ----------

BEFORE_EDIT = "# House style\n\nwrite short commit messages\n"
AFTER_EDIT = "# House style\n\nwrite short commit messages, and run `pytest`\n"


def test_turns_before_and_after_an_edit_read_their_own_version(
        tmp_path, monkeypatch):
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    events = [
        user_text("first, just talk", 0),
        assistant_text("talking", 1),
        user_text("now rewrite the house style", 2),
        assistant_tool_use("Edit", {"file_path": str(proj_md),
                                    "old_string": "write short commit messages",
                                    "new_string": "write short commit messages, "
                                                  "and run `pytest`"}, 3, tool_id="e1"),
        edit_result("e1", proj_md, BEFORE_EDIT,
                    "write short commit messages",
                    "write short commit messages, and run `pytest`", 4),
        assistant_text("rewritten", 5),
        user_text("and now carry on", 6),
        assistant_text("carrying on", 7),
    ]
    _, per = _run(tmp_path, monkeypatch, events, project_md=AFTER_EDIT)
    turns = per["turns"]
    assert len(turns) == 3
    # A turn is given the version in effect when it started, so the turn that
    # does the rewriting is still working from the wording it was handed.
    contents = [_block(t, "CLAUDE.md", "House style")["content"] for t in turns]
    sources = [_block(t, "CLAUDE.md", "House style")["textSource"] for t in turns]
    assert sources == ["transcript"] * 3
    assert "pytest" not in contents[0]
    assert "pytest" not in contents[1]
    assert "pytest" in contents[2]


# ---------- test 3: nothing to recover, so the disk text with a marker ----------

def test_a_file_with_no_read_and_no_attachment_is_marked_as_disk_text(
        tmp_path, monkeypatch):
    events = [user_text("hello", 0), assistant_text("hi", 1)]
    _, per = _run(tmp_path, monkeypatch, events, project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["textSource"] == "disk"
    assert b["reason"].endswith(brv.DISK_TEXT_CAVEAT.strip())


def test_every_block_of_every_scope_names_its_text_source(tmp_path, monkeypatch):
    """The CLI prints this line for every block, so every block must carry it."""
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    _, per = _run(tmp_path, monkeypatch, _events(proj_md), project_md=ON_DISK)
    scopes = [per] + per["turns"]
    total = 0
    for scope in scopes:
        for f in scope["contextFiles"]:
            for b in f["blocks"]:
                assert b["textSource"] in ("transcript", "disk", "stale"), b["id"]
                total += 1
    assert total


def test_the_early_returns_carry_the_text_source_too():
    """A block that was never loaded, and one outside the delivered range, both
    return before the verdict is computed - and the CLI prints the line for
    them as well."""
    block = {"title": "Docs", "content": "body", "level": 1, "start_line": 900}
    trace = {"user_prompt": "hi"}
    not_loaded = brv.assess_block(
        block, {"loaded": False, "text_source": "disk"}, trace)
    assert not_loaded["status"] == "not-loaded"
    assert not_loaded["textSource"] == "disk"
    undelivered = brv.assess_block(block, {
        "loaded": True, "text_source": "transcript", "delivery": "truncated",
        "delivered_from": 1, "delivered_to": 100, "total_lines": 1000,
        "delivered_ranges": [(1, 100)]}, trace)
    assert undelivered["status"] == "undelivered"
    assert undelivered["textSource"] == "transcript"


# ---------- test 4: ids do not move with the text source ----------

def test_block_ids_are_the_same_whichever_source_the_text_came_from(
        tmp_path, monkeypatch):
    """The slug comes from the heading, and the heading is the same in both.

    Both runs share one project directory on purpose: a block id carries the
    file's path, so two directories would differ for a reason this test is not
    about.
    """
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    _, from_disk = _run(tmp_path, monkeypatch,
                        [user_text("hello", 0), assistant_text("hi", 1)],
                        project_md=ON_DISK)
    _, from_transcript = _run(tmp_path, monkeypatch, _events(proj_md),
                              project_md=ON_DISK, name="t2.jsonl")

    def ids(scope):
        f = next(f for f in scope["contextFiles"] if "CLAUDE.md" in f["path"])
        return f["blocks"][0]["textSource"], [b["id"] for b in f["blocks"]]

    disk_source, disk_ids = ids(from_disk)
    tr_source, tr_ids = ids(from_transcript)
    assert (disk_source, tr_source) == ("disk", "transcript")
    assert disk_ids == tr_ids


# ---------- the ledger itself ----------

def test_a_partial_read_is_not_taken_as_the_whole_file():
    """A slice is delivered text, but putting it back inside the rest of the
    file needs the rest, and the only copy of that is the disk file this exists
    to stop trusting."""
    proj_md = "/tmp/does-not-matter/CLAUDE.md"
    events = [read_result("r1", proj_md, "# A\n\nbody\n", 0,
                          start_line=40, total_lines=900)]
    assert brv.delivered_versions(events) == {}


def test_a_read_that_stops_at_the_line_cap_is_not_taken_as_the_whole_file():
    events = [read_result("r1", "/tmp/x/CLAUDE.md", "# A\n\nbody\n", 0,
                          total_lines=2000)]
    assert brv.delivered_versions(events) == {}


def test_a_read_record_that_does_not_say_how_much_it_carried_is_refused():
    """Fails closed: a record that cannot be shown to carry the whole file
    falls back to the disk text with its marker, which is a limit the reader
    can see, rather than a verdict about a document nobody read."""
    ev = read_result("r1", "/tmp/x/CLAUDE.md", "# A\n\nbody\n", 0)
    del ev["toolUseResult"]["file"]["totalLines"]
    assert brv.delivered_versions([ev]) == {}


def test_a_read_record_whose_start_line_will_not_parse_is_refused():
    """An unparseable `startLine` is not a `startLine` of 1."""
    ev = read_result("r1", "/tmp/x/CLAUDE.md", "# A\n\nbody\n", 0)
    ev["toolUseResult"]["file"]["startLine"] = "not a number"
    assert brv.delivered_versions([ev]) == {}


def test_the_first_recorded_version_covers_the_turns_before_it():
    """A file read at turn 7 and never edited was the same file at turn 1, and
    that read is the only record of what the harness injected."""
    events = [user_text("q", 0),
              read_result("r1", "/tmp/x/CLAUDE.md", "# A\n\nbody\n", 1)]
    versions = brv.delivered_versions(events)
    (entries,) = versions.values()
    assert entries[0][0] == 0
    assert brv.delivered_at(versions, 0)


def test_an_edit_whose_old_string_is_absent_from_the_pre_edit_text_invents_nothing():
    """The two halves of the record disagree, so only the half we can trust -
    the pre-edit file - becomes a version."""
    events = [edit_result("e1", "/tmp/x/CLAUDE.md", BEFORE_EDIT,
                          "a line that is not in the file", "something else", 0)]
    (entries,) = brv.delivered_versions(events).values()
    assert [o for _, _, o in entries] == ["pre-write"]


def test_a_stale_hook_record_refuses_to_derive_a_rule_from_the_disk_wording(
        tmp_path, monkeypatch):
    """The ctxlog hook recorded the file's size and digest at load time. Where
    those disagree with the file today, the disk wording is provably not the
    wording the model was given."""
    proj = tmp_path / "proj"
    events = _events(proj / "CLAUDE.md")
    # Drop the read so the only text available is the disk file.
    events = [e for e in events if "toolUseResult" not in e]
    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: {
        "instructions": [{"path": str((proj / "CLAUDE.md").resolve()),
                          "stats": {"lines": 3, "size_bytes": 11,
                                    "sha256": "0" * 16}}],
        "compactions": [],
    })
    _, per = _run(tmp_path, monkeypatch, events, project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["textSource"] == "stale"
    assert b["status"] != "used"
    assert "no longer matches" in b["reason"]


def test_a_matching_hook_record_leaves_the_disk_wording_usable(
        tmp_path, monkeypatch):
    """Positive control for the case above: the same fixture with a digest that
    does match still derives its predicate."""
    import hashlib
    proj = tmp_path / "proj"
    events = [e for e in _events(proj / "CLAUDE.md") if "toolUseResult" not in e]
    digest = hashlib.sha256(ON_DISK.encode()).hexdigest()[:16]
    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: {
        "instructions": [{"path": str((proj / "CLAUDE.md").resolve()),
                          "stats": {"lines": len(ON_DISK.splitlines()),
                                    "size_bytes": len(ON_DISK),
                                    "sha256": digest}}],
        "compactions": [],
    })
    _, per = _run(tmp_path, monkeypatch, events, project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["textSource"] == "disk"
    assert b["status"] == "used"


def test_a_stale_file_gets_no_mechanically_extracted_rule_check(
        tmp_path, monkeypatch):
    """The fallback derives its patterns from the block's own wording, and this
    wording is provably not the rule the session was given."""
    proj = tmp_path / "proj"
    md = "# Imports\n\nnever use `require()` in this codebase\n"
    events = [
        user_text("write the module", 0),
        assistant_tool_use("Write", {"file_path": str(proj / "a.js"),
                                     "content": "const x = require('y');\n"},
                           1, tool_id="w1"),
        user_tool_result("w1", "written", 2),
        assistant_text("done", 3),
    ]
    facts = {"instructions": [{"path": str((proj / "CLAUDE.md").resolve()),
                              "stats": {"lines": 3, "size_bytes": 11,
                                        "sha256": "0" * 16}}],
             "compactions": []}
    monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: facts)
    _, stale = _run(tmp_path, monkeypatch, events, project_md=md)
    b = _block(stale, "CLAUDE.md", "Imports")
    assert b["textSource"] == "stale"
    assert not (b.get("ruleCheck") or {}).get("findings")

    # Positive control: the same run with a matching digest does extract the
    # pattern and reports the candidate.
    import hashlib
    facts["instructions"][0]["stats"] = {
        "lines": 3, "size_bytes": len(md),
        "sha256": hashlib.sha256(md.encode()).hexdigest()[:16]}
    _, live = _run(tmp_path, monkeypatch, events, project_md=md, name="t2.jsonl")
    b2 = _block(live, "CLAUDE.md", "Imports")
    assert b2["textSource"] == "disk"
    assert (b2["ruleCheck"] or {}).get("findings")


def test_a_created_file_is_not_back_dated_to_the_start_of_the_session():
    """A file whose earliest record is the write that created it did not exist
    before that write; claiming otherwise would say the model held text nobody
    had written yet."""
    events = [
        user_text("make the notes file", 0),
        {"type": "user", "timestamp": "2026-01-01T00:00:01.000Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "w1",
                                  "content": "created"}]},
         "toolUseResult": {"type": "create", "filePath": "/tmp/x/notes.md",
                           "content": "# Notes\n\nfresh\n"}},
    ]
    versions = brv.delivered_versions(events)
    (entries,) = versions.values()
    assert entries[0][0] == 1
    assert brv.delivered_at(versions, 0) == {}
    assert brv.delivered_at(versions, 1)


def test_an_overruled_aggregate_reason_keeps_its_text_source_clause(
        tmp_path, monkeypatch):
    """Where the combine rule overrules the aggregate, its reason is rewritten
    from the turn statuses - and the clause saying which text the verdict is
    about has to survive that, or a session-scope verdict sits above a sentence
    that no longer says it.

    The overrule is forced rather than engineered: what is under test is the
    rewrite path, not the arithmetic that reaches it.
    """
    proj_md = tmp_path / "proj" / "CLAUDE.md"
    events = [
        user_text("nothing to do here", 0),
        assistant_text("idle", 1),
        user_text("now write the notes", 2),
        assistant_tool_use("Write", {"file_path": str(proj_md.parent / "notes.md"),
                                     "content": "notes"}, 3, tool_id="w1"),
        user_tool_result("w1", "written", 4),
        assistant_text("done", 5),
    ]
    monkeypatch.setattr(brv, "combine_verdicts", lambda statuses: "possibly-referenced")
    _, per = _run(tmp_path, monkeypatch, events, project_md=ON_DISK)
    b = _block(per, "CLAUDE.md", "Docs")
    assert b["status"] == "possibly-referenced"
    assert b["reason"].startswith("Combined from")
    assert b["textSource"] == "disk"
    assert b["reason"].endswith(brv.DISK_TEXT_CAVEAT.strip())


def test_stale_text_is_not_compared_with_the_run_by_wording(monkeypatch):
    """A coincidental word match with text the model never saw is about nothing."""
    def boom(*a, **k):
        raise AssertionError("lexical tier consulted on stale text")
    monkeypatch.setattr(brv, "_lexical_result", boom)
    block = brv.parse_claude_md("## Style\n\nPrefer terse distinctive phrasing.\n")[0]
    file = {"loaded": True, "kind": "project", "path": "CLAUDE.md",
            "abs_path": "/tmp/CLAUDE.md", "text_source": "stale",
            "text_note": "The file no longer matches what was loaded.", "blocks": [block]}
    events = [user_text("q", 0)]
    trace = brv.build_trace(events, [], brv.assistant_text_segments(events), "q")
    v = brv.assess_block(block, file, trace)
    assert v["status"] == "unused"
    assert "evidenceLabel" not in v and "lexical" not in v
    assert v["reason"].endswith("The file no longer matches what was loaded.")


def test_a_rule_check_verdict_keeps_the_text_caveat_and_drops_the_lexical_label(
        monkeypatch):
    monkeypatch.setattr(brv, "_rule_check_for", lambda *a: {
        "source": "checks-file", "state": "violated", "notCheckable": [],
        "findings": [{"state": "violated", "confidence": "high", "checkId": "c1",
                      "path": "a.py", "line": 3, "match": "bad()", "message": "",
                      "ruleText": "never bad"}]})
    block = brv.parse_claude_md("## Style\n\nNever call bad in production code.\n")[0]
    file = {"loaded": True, "kind": "project", "path": "CLAUDE.md",
            "abs_path": "/tmp/CLAUDE.md", "text_source": "disk", "blocks": [block]}
    events = [user_text("q", 0)]
    trace = brv.build_trace(events, [], brv.assistant_text_segments(events), "q")
    trace["lexical_bg"] = brv.lexical.build_background([file], trace["query_segments"])
    v = brv.assess_block(block, file, trace)
    assert v["status"] == "ignored"
    assert v["reason"].endswith(brv.DISK_TEXT_CAVEAT)
    assert "evidenceLabel" not in v and "lexical" not in v
