"""Which files actually entered context, and which text they carried."""
import build_real_view as brv
from tests.test_turns import (_Args, _write_jsonl, assistant_tool_use, user_text,
                              user_tool_result, _ts)


def bash(cmd, i, tool_id="b1"):
    return assistant_tool_use("Bash", {"command": cmd}, i, tool_id=tool_id)


def hook_says(text, i):
    return {"type": "attachment", "timestamp": _ts(i),
            "attachment": {"type": "hook_additional_context", "content": [text]}}


def meta(text, i):
    return {"type": "user", "isMeta": True, "timestamp": _ts(i),
            "message": {"content": [{"type": "text", "text": text}]}}


class Args(_Args):
    no_skills = False


def run(tmp_path, monkeypatch, events, files=()):
    home = tmp_path / "home"
    (home / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    for rel, text in files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(proj)
    args = Args()
    args.skills_dir = str(home / ".claude" / "skills")
    _summary, per = brv.process_session(_write_jsonl(proj, events), args)
    return per


def loaded(per, needle):
    return next(f for f in per["contextFiles"] if needle in f["path"])["loaded"]


AGENTS = ("proj/AGENTS.md", "## Build\n\nRun the build.\n")


def test_an_agents_file_that_exists_is_not_in_context_by_existing(tmp_path, monkeypatch):
    per = run(tmp_path, monkeypatch, [user_text("hi", 0)], [AGENTS])
    assert loaded(per, "AGENTS.md") is False


def test_an_agents_file_printed_with_cat_is_in_context(tmp_path, monkeypatch):
    per = run(tmp_path, monkeypatch, [user_text("hi", 0), bash("cat AGENTS.md", 1)], [AGENTS])
    assert loaded(per, "AGENTS.md") is True


def test_a_file_a_hook_only_suggested_is_not_in_context(tmp_path, monkeypatch):
    report = ("proj/graphify-out/GRAPH_REPORT.md", "# Graph\n\nnodes\n")
    events = [hook_says("Read graphify-out/GRAPH_REPORT.md before answering.", 0),
              user_text("hi", 1)]
    per = run(tmp_path, monkeypatch, events, [report])
    assert loaded(per, "GRAPH_REPORT.md") is False
    assert per["wastedContext"]["loadedFiles"] == 0


def test_a_skill_printed_with_cat_is_in_context_and_a_head_slice_is_not(tmp_path, monkeypatch):
    skills = [("home/.claude/skills/cp/SKILL.md", "# cp\n\nCopy.\n"),
              ("home/.claude/skills/pr/SKILL.md", "# pr\n\nReview.\n")]
    events = [user_text("hi", 0), bash("cat ~/.claude/skills/cp/SKILL.md", 1),
              bash("cat ~/.claude/skills/pr/SKILL.md | head -40", 2, tool_id="b2")]
    per = run(tmp_path, monkeypatch, events, skills)
    assert loaded(per, "skills/cp/") is True
    assert loaded(per, "skills/pr/") is False


# ---------- the body a skill or command delivers when it runs ----------

def test_a_skill_body_is_recovered_under_its_skill_file(tmp_path):
    body = "# Reviewer\n\nRead `mobile/AGENT.md`.\n"
    events = [meta(f"Base directory for this skill: {tmp_path}/review\n\n{body}"
                   "\n\nARGUMENTS: the branch", 0)]
    versions = brv.delivered_versions(events)
    (key,) = versions
    assert key.endswith("review/SKILL.md")
    assert versions[key][0][1] == body


def test_a_command_body_is_recovered_under_the_name_it_was_invoked_with(tmp_path):
    events = [assistant_tool_use("Skill", {"skill": "prd-to-plan"}, 0, tool_id="s1"),
              user_tool_result("s1", "Launching skill: prd-to-plan", 1),
              meta("# PRD to Plan\n\nBreak a PRD into phases.\n", 2)]
    versions = brv.delivered_versions(events)
    assert versions[brv.INVOKED_KEY + "prd-to-plan"][0][1].startswith("# PRD to Plan")


def test_an_already_loaded_notice_is_not_a_body():
    events = [assistant_tool_use("Skill", {"skill": "commit"}, 0, tool_id="s1"),
              user_tool_result("s1", "Launching skill: commit", 1),
              meta("Skill /commit is already loaded above; instructions unchanged.", 2)]
    assert brv.delivered_versions(events) == {}


def test_an_invoked_skill_is_judged_on_the_text_it_delivered(tmp_path, monkeypatch):
    on_disk = "# cp\n\nCopy with `pbcopy`.\n"
    delivered = "# cp\n\nCopy with `xclip`.\n"
    events = [user_text("hi", 0),
              assistant_tool_use("Skill", {"skill": "cp"}, 1, tool_id="s1"),
              user_tool_result("s1", "Launching skill: cp", 2),
              meta(f"Base directory for this skill: {tmp_path}/home/.claude/skills/cp"
                   f"\n\n{delivered}", 3)]
    per = run(tmp_path, monkeypatch, events, [("home/.claude/skills/cp/SKILL.md", on_disk)])
    f = next(f for f in per["contextFiles"] if "skills/cp/" in f["path"])
    assert f["blocks"][0]["textSource"] == "transcript"
    assert "xclip" in f["blocks"][0]["content"]


# ---------- an invoked skill stays in context in later turns ----------

MEMLOG_SKILL = ("# memlog\n\nKeep the decision log.\n\n"
                "## Decision log entry\n\n"
                "Append one entry per significant decision, in this exact shape:\n\n"
                "    ## [YYYY-MM-DD] Short title\n"
                "    **Decided:** what was chosen\n"
                "    **Why:** the reason\n"
                "    **Rejected:** alternatives and why they were dropped\n")
OTHER_SKILL = "# other\n\nDo something else.\n"
ENTRY = ("## [2026-01-01] Bake the rollup in Python\n"
         "**Decided:** compute every rollup in Python and bake it\n"
         "**Why:** the CLI and the page must not disagree\n"
         "**Rejected:** deriving it in JavaScript\n")


def _invoke(name, i, tool_id):
    return [assistant_tool_use("Skill", {"skill": name}, i, tool_id=tool_id),
            user_tool_result(tool_id, f"Launching skill: {name}", i + 1)]


def _write_entry(i):
    return assistant_tool_use("Write", {"file_path": "/tmp/DECISIONS.md", "content": ENTRY},
                              i, tool_id=f"w{i}")


def _step(payload):
    f = next(f for f in payload["contextFiles"] if "skills/memlog/" in f["path"])
    return f, next(b for b in f["blocks"] if b["title"] == "Decision log entry")


def _run_skill(tmp_path, monkeypatch, events, hook_facts=None):
    if hook_facts is not None:
        monkeypatch.setattr(brv.ctxlog_facts, "load_facts", lambda *a, **k: hook_facts)
    return run(tmp_path, monkeypatch, events,
               [("home/.claude/skills/memlog/SKILL.md", MEMLOG_SKILL),
                ("home/.claude/skills/other/SKILL.md", OTHER_SKILL)])


def test_a_skill_invoked_in_one_turn_is_loaded_and_running_in_the_next(tmp_path, monkeypatch):
    events = ([user_text("start the log", 0)] + _invoke("memlog", 1, "s1")
              + [user_text("now write the entry", 5), _write_entry(6)])
    per = _run_skill(tmp_path, monkeypatch, events)
    f1, step1 = _step(per["turns"][1])
    assert f1["loaded"] is True
    assert step1["status"] == "used"
    assert _step(per)[1]["status"] == "used"


def test_a_different_skill_invoked_in_between_ends_the_procedure(tmp_path, monkeypatch):
    events = ([user_text("start the log", 0)] + _invoke("memlog", 1, "s1")
              + [user_text("do the other thing", 5)] + _invoke("other", 6, "s2")
              + [user_text("now write the entry", 10), _write_entry(11)])
    per = _run_skill(tmp_path, monkeypatch, events)
    f2, step2 = _step(per["turns"][2])
    # Still in context: being resident is not being the procedure that runs.
    assert f2["loaded"] is True
    assert step2["status"] != "used"
    assert _step(per)[1]["status"] != "used"


def test_a_compaction_that_evicts_the_skill_ends_its_credit(tmp_path, monkeypatch):
    skill = tmp_path / "home/.claude/skills/memlog/SKILL.md"
    hook_ts = "2026-01-01T00:00:{:02d}+00:00".format
    facts = {"instructions": [{"path": str(skill.resolve()), "memory_type": "Project",
                               "load_reason": "path_glob_match", "globs": [],
                               "trigger_file_path": None, "parent_file_path": None,
                               "ts": hook_ts(1), "stats": {}}],
             "compactions": [{"event": "PreCompact", "ts": hook_ts(4), "trigger": "auto"}]}
    events = ([user_text("start the log", 0)] + _invoke("memlog", 1, "s1")
              + [user_text("now write the entry", 5), _write_entry(6)])
    per = _run_skill(tmp_path, monkeypatch, events, hook_facts=facts)
    assert not any("skills/memlog/" in f["path"] for f in per["turns"][1]["contextFiles"])
    assert _step(per)[1]["status"] != "used"


def test_a_different_skill_invoked_inside_the_later_turn_closes_the_window(tmp_path, monkeypatch):
    events = ([user_text("start the log", 0)] + _invoke("memlog", 1, "s1")
              + [user_text("do the other thing, then write", 5)] + _invoke("other", 6, "s2")
              + [_write_entry(8)])
    per = _run_skill(tmp_path, monkeypatch, events)
    f1, step1 = _step(per["turns"][1])
    assert f1["loaded"] is True
    assert step1["status"] != "used"


READER_SKILL = ("# reader\n\nRead the spec.\n\n"
                "## Load context\n\nRead `docs/spec.md` before anything else.\n")


def _reader_step(payload):
    f = next(f for f in payload["contextFiles"] if "skills/reader/" in f["path"])
    return next(b for b in f["blocks"] if b["title"] == "Load context")


def test_a_read_in_a_later_turn_is_not_credited_to_the_carried_skill(tmp_path, monkeypatch):
    """Nothing records when a procedure finished, so a later turn's read is the
    work at hand rather than the step. The same read in the invoking turn is."""
    read = assistant_tool_use("Read", {"file_path": str(tmp_path / "proj/docs/spec.md")}, 6,
                              tool_id="r1")
    files = [("home/.claude/skills/reader/SKILL.md", READER_SKILL),
             ("proj/docs/spec.md", "spec\n")]
    later = ([user_text("load it", 0)] + _invoke("reader", 1, "s1")
             + [user_text("new task", 5), read])
    per = run(tmp_path, monkeypatch, later, files)
    assert _reader_step(per["turns"][1])["status"] != "used"
    same = [user_text("load it", 0)] + _invoke("reader", 1, "s1") + [read]
    per = run(tmp_path, monkeypatch, same, files)
    assert _reader_step(per["turns"][0])["status"] == "used"
