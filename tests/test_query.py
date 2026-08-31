"""Tests for Phase 8: CLI read-mode.

The query path answers from the baked JSON, so the CLI and the HTML can never
disagree. Every listing is a discovery step: its output must carry the ids the
next query needs. Output is bounded, and anything elided names the exact
command that returns the rest.
"""
import pytest

import build_real_view as brv

from tests.test_turns import (
    _Args,
    _ts,
    _write_jsonl,
    assistant_text,
    assistant_tool_use,
    user_text,
    user_tool_result,
)


# ---------- helpers ----------

def _moment(label, text, verdict="yes", kind="trigger"):
    return {"t": _ts(1), "kind": kind, "verdict": verdict, "label": label, "text": text}


def _blk(bid, title, status="unused", reason="no signal", content="body",
         moments=None):
    return {
        "id": bid,
        "title": title,
        "type": "rule",
        "level": 2,
        "content": content,
        "status": status,
        "reason": reason,
        "evidence": [],
        "moments": moments or [],
    }


def _file(path, blocks, loaded=True, kind="global"):
    return {"path": path, "kind": kind, "loaded": loaded, "group": "global",
            "blocks": blocks}


def _turn(index, prompt, files=None, calls=0):
    return {
        "id": f"turn-{index}",
        "index": index,
        "userPrompt": prompt,
        "promptPreview": prompt,
        "startTime": _ts(index),
        "endTime": _ts(index + 1),
        "durationSec": 60,
        "counts": {"totalToolCalls": calls, "filesEdited": 0},
        "usage": brv.usage_totals([]),
        "contextFiles": files or [],
        "timeline": [],
    }


def _session(sid, prompt="fix the parser", files=None, turns=None):
    return {
        "session": {"id": sid, "project": "proj", "cwd": "/cwd", "branch": "main",
                    "version": "1", "userPrompt": prompt, "startTime": _ts(0),
                    "endTime": _ts(9), "durationSec": 540,
                    "transcriptPath": f"/tmp/{sid}.jsonl"},
        "counts": {"events": 10, "totalToolCalls": 4, "userMessages": 2,
                   "filesEdited": 1},
        "usage": brv.usage_totals([]),
        "contextFiles": files or [],
        "turns": turns or [],
        "turnCount": len(turns or []),
    }


def _summary(sid, prompt="fix the parser"):
    return {"id": sid, "path": f"/tmp/{sid}.jsonl", "promptPreview": prompt,
            "startTime": _ts(0), "endTime": _ts(9), "durationSec": 540,
            "events": 10, "toolCalls": 4, "usage": brv.usage_totals([])}


def _data(*pairs):
    """pairs are (summary, per_session) tuples; the first is active."""
    sessions = [s for s, _ in pairs]
    per = {s["id"]: d for s, d in pairs}
    return brv.build_data("/cwd", sessions, per, sessions[0]["id"])


SID = "aaaaaaaa-1111-2222-3333-444444444444"
SID2 = "bbbbbbbb-1111-2222-3333-444444444444"


def _simple_data():
    b1 = _blk("claude-md-0-talk", "How to talk to me", status="used",
              reason="Rule fired", moments=[_moment("TRIGGER", "user typed /cp")])
    b2 = _blk("claude-md-1-tests", "Tests", status="dormant")
    tb = _blk("turn1-claude-md-0-talk", "How to talk to me", status="possibly-referenced")
    files = [_file("~/.claude/CLAUDE.md", [b1, b2])]
    turns = [_turn(1, "fix the parser", [_file("~/.claude/CLAUDE.md", [tb])], calls=3),
             _turn(2, "now the tests", calls=1)]
    return _data((_summary(SID), _session(SID, files=files, turns=turns)),
                 (_summary(SID2, "other run"), _session(SID2)))


def _joined(lines):
    return "\n".join(lines)


# ---------- sessions listing ----------

def test_query_sessions_prints_one_line_per_session():
    out = brv.run_query(_simple_data(), ["sessions"])
    body = [ln for ln in out if ln.startswith(SID) or ln.startswith(SID2)]
    assert len(body) == 2


def test_session_line_carries_id_time_turns_tokens_and_prompt():
    out = brv.run_query(_simple_data(), ["sessions"])
    line = next(ln for ln in out if ln.startswith(SID))
    assert "2 turns" in line
    assert "fix the parser" in line
    assert _ts(0)[:10] in line
    assert "in" in line and "out" in line


def test_token_formatting_matches_the_pages_fmt_tokens():
    assert brv._fmt_tokens(0) == "0"
    assert brv._fmt_tokens(950) == "950"
    assert brv._fmt_tokens(7_100) == "7.1k"
    assert brv._fmt_tokens(164_376) == "164k"
    assert brv._fmt_tokens(4_090_194) == "4.1M"


def test_session_listing_names_the_next_command():
    out = brv.run_query(_simple_data(), ["sessions"])
    text = _joined(out)
    assert f"--query {SID} turns" in text


def test_every_query_line_is_bounded():
    data = _simple_data()
    for address in (["sessions"], [SID], [SID, "turns"], [SID, "blocks"]):
        for line in brv.run_query(data, address):
            assert len(line) <= brv.QUERY_FIELD_LIMIT + 200


# ---------- turns ----------

def test_query_turns_lists_every_turn_with_its_id():
    out = brv.run_query(_simple_data(), [SID, "turns"])
    text = _joined(out)
    assert "turn-1" in text and "turn-2" in text
    assert "now the tests" in text


def test_query_turns_names_the_block_listing_command():
    out = brv.run_query(_simple_data(), [SID, "turns"])
    assert f"--query {SID} turn-1 blocks" in _joined(out)


def test_unknown_turn_raises_with_the_listing_command():
    with pytest.raises(brv.QueryError) as e:
        brv.run_query(_simple_data(), [SID, "turn-9", "blocks"])
    assert f"--query {SID} turns" in str(e.value)


# ---------- blocks ----------

def test_query_turn_blocks_lists_ids_with_statuses():
    out = brv.run_query(_simple_data(), [SID, "turn-1", "blocks"])
    text = _joined(out)
    assert "turn1-claude-md-0-talk" in text
    assert "possibly-referenced" in text


def test_query_session_blocks_lists_session_scope_ids():
    out = brv.run_query(_simple_data(), [SID, "blocks"])
    text = _joined(out)
    assert "claude-md-0-talk" in text and "claude-md-1-tests" in text
    assert "used" in text and "dormant" in text


def test_block_listing_is_capped_and_names_the_all_flag():
    blocks = [_blk(f"claude-md-{i}-b", f"Block {i}") for i in range(brv.QUERY_ROW_LIMIT + 5)]
    data = _data((_summary(SID), _session(SID, files=[_file("~/.claude/CLAUDE.md", blocks)])))
    out = brv.run_query(data, [SID, "blocks"])
    text = _joined(out)
    assert f"--query {SID} blocks --all" in text
    rows = [ln for ln in out if "claude-md-" in ln and "[" in ln]
    assert len(rows) == brv.QUERY_ROW_LIMIT

    full = brv.run_query(data, [SID, "blocks"], show_all=True)
    rows = [ln for ln in full if "claude-md-" in ln and "[" in ln]
    assert len(rows) == brv.QUERY_ROW_LIMIT + 5


def test_query_block_prints_verdict_reason_and_moments():
    out = brv.run_query(_simple_data(), [SID, "claude-md-0-talk"])
    text = _joined(out)
    assert "used" in text
    assert "Rule fired" in text
    assert "user typed /cp" in text
    assert "~/.claude/CLAUDE.md" in text


def test_turn_scoped_block_resolves_from_the_session_address():
    out = brv.run_query(_simple_data(), [SID, "turn1-claude-md-0-talk"])
    text = _joined(out)
    assert "turn-1" in text
    assert "possibly-referenced" in text


def test_unknown_block_raises_with_the_listing_command():
    with pytest.raises(brv.QueryError) as e:
        brv.run_query(_simple_data(), [SID, "no-such-block"])
    assert f"--query {SID} blocks" in str(e.value)


def test_unknown_block_under_a_turn_names_that_turns_listing():
    with pytest.raises(brv.QueryError) as e:
        brv.run_query(_simple_data(), [SID, "turn-1", "no-such-block"])
    assert f"--query {SID} turn-1 blocks" in str(e.value)


# ---------- bounding and elision ----------

def test_long_reason_is_elided_with_the_exact_full_command():
    long_reason = "x" * (brv.QUERY_FIELD_LIMIT + 500)
    blk = _blk("claude-md-0-talk", "Talk", status="used", reason=long_reason)
    data = _data((_summary(SID), _session(SID, files=[_file("~/.claude/CLAUDE.md", [blk])])))
    text = _joined(brv.run_query(data, [SID, "claude-md-0-talk"]))
    assert f"--query {SID} claude-md-0-talk --field reason" in text
    assert long_reason not in text


def test_field_flag_prints_the_whole_value_unbounded():
    content = "y" * (brv.QUERY_FIELD_LIMIT + 500)
    blk = _blk("claude-md-0-talk", "Talk", content=content)
    data = _data((_summary(SID), _session(SID, files=[_file("~/.claude/CLAUDE.md", [blk])])))
    out = brv.run_query(data, [SID, "claude-md-0-talk"], field="content")
    assert _joined(out) == content


def test_verdictless_moment_prints_a_dash_not_none():
    blk = _blk("claude-md-0-talk", "Talk",
               moments=[{"t": None, "kind": "non-event", "verdict": None,
                         "label": "Agent reasoning", "text": "thinking"}])
    data = _data((_summary(SID), _session(SID, files=[_file("~/.claude/CLAUDE.md", [blk])])))
    text = _joined(brv.run_query(data, [SID, "claude-md-0-talk"]))
    assert "[None]" not in text
    assert "[-] Agent reasoning" in text


def test_field_on_a_listing_raises():
    with pytest.raises(brv.QueryError):
        brv.run_query(_simple_data(), [SID, "blocks"], field="content")


def test_unknown_field_raises_and_names_the_valid_fields():
    with pytest.raises(brv.QueryError) as e:
        brv.run_query(_simple_data(), [SID, "claude-md-0-talk"], field="nope")
    assert "content" in str(e.value)


# ---------- session addressing ----------

def test_session_prefix_resolves():
    out = brv.run_query(_simple_data(), [SID[:8]])
    assert any(SID in ln for ln in out)


def test_unknown_session_prefix_raises_with_the_sessions_command():
    with pytest.raises(brv.QueryError) as e:
        brv.run_query(_simple_data(), ["zzzzzzzz", "turns"])
    assert "--query sessions" in str(e.value)


def test_ambiguous_session_prefix_raises():
    data = _data((_summary("abc11111"), _session("abc11111")),
                 (_summary("abc22222"), _session("abc22222")))
    with pytest.raises(brv.QueryError):
        brv.run_query(data, ["abc"])


def test_empty_address_raises():
    with pytest.raises(brv.QueryError):
        brv.run_query(_simple_data(), [])


# ---------- acceptance: three bounded commands ----------

def test_three_commands_reach_a_block_verdict():
    data = _simple_data()
    listing = brv.run_query(data, ["sessions"])
    sid = next(ln.split()[0] for ln in listing if ln.startswith(SID))

    blocks = brv.run_query(data, [sid, "blocks"])
    bid = next(ln.split()[0] for ln in blocks if ln.strip().startswith("claude-md-"))

    detail = _joined(brv.run_query(data, [sid, bid]))
    assert "status" in detail and "used" in detail


# ---------- end to end: no HTML side effects ----------

def _fixture_transcript(tmp_path):
    events = [
        user_text("first prompt", 0),
        assistant_tool_use("Read", {"file_path": "/tmp/a"}, 1),
        user_tool_result("t1", "ac", 2),
        assistant_text("done", 3),
        user_text("second prompt", 4),
        assistant_text("done again", 5),
    ]
    return _write_jsonl(tmp_path, events, name="cafe1234-0000-0000-0000-000000000000.jsonl")


class _QueryArgs(_Args):
    def __init__(self, transcript, out, query, field=None, all=False, claude_md=None):
        self.claude_md = claude_md
        self.transcript = transcript
        self.out = out
        self.query = query
        self.field = field
        self.all = all
        self.session = None
        self.all_sessions = False
        self.max_sessions = 0
        self.projects_dir = transcript.parent if transcript is not None else None
        self.compare = None


def test_cmd_query_writes_no_html_and_prints_the_answer(tmp_path, monkeypatch, capsys):
    p = _fixture_transcript(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.html"
    brv.cmd_query(_QueryArgs(p, out, ["sessions"]))

    assert not out.exists()
    printed = capsys.readouterr().out
    assert "turns" in printed
    assert "first prompt" in printed


def test_cmd_query_refuses_a_missing_claude_md(tmp_path, monkeypatch):
    p = _fixture_transcript(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = _QueryArgs(p, tmp_path / "out.html", ["sessions"],
                      claude_md=tmp_path / "nope.md")
    with pytest.raises(brv.QueryError) as e:
        brv.cmd_query(args)
    assert "CLAUDE.md not found" in str(e.value)


def test_cmd_query_refuses_an_ambiguous_session_prefix(tmp_path, monkeypatch):
    """Scoping to one session must not turn ambiguity into a silent pick."""
    projects = tmp_path / "projects"
    cwd = tmp_path / "work"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    proj_dir = projects / brv.encode_cwd_for_projects(str(cwd))
    proj_dir.mkdir(parents=True)
    events = [user_text("p", 0), assistant_text("a", 1)]
    _write_jsonl(proj_dir, events, name="dupe1111-aaaa.jsonl")
    _write_jsonl(proj_dir, events, name="dupe2222-bbbb.jsonl")

    args = _QueryArgs(None, cwd / "out.html", ["dupe", "turns"])
    args.projects_dir = projects
    with pytest.raises(brv.QueryError) as e:
        brv.cmd_query(args)
    assert "matches 2 sessions" in str(e.value)


def test_cmd_query_end_to_end_reaches_a_block(tmp_path, monkeypatch, capsys):
    p = _fixture_transcript(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.html"
    sid = p.stem

    brv.cmd_query(_QueryArgs(p, out, [sid, "turns"]))
    turns = capsys.readouterr().out
    assert "turn-0" in turns and "turn-1" in turns

    brv.cmd_query(_QueryArgs(p, out, [sid, "turn-0", "blocks"]))
    blocks = capsys.readouterr().out
    assert not out.exists()
    assert "[" in blocks
