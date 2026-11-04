"""Tests for the baseline snapshot harness (snapshots/take_baseline.py).

The property under test is not "the snapshot ran" but "the snapshot is still
the same experiment months later": every input the analysis reads is frozen,
and a re-run consumes the frozen copies rather than whatever the machine now
has on disk. A snapshot that silently re-reads the live rule docs would report
a judgement change that was really a rule edit, which is the exact confusion
this harness exists to prevent - so drift of the live tree is simulated here.
"""
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))
import take_baseline as tb  # noqa: E402

from tests.test_turns import _ts, assistant_text, assistant_tool_use, user_text  # noqa: E402


SESSION_ID = "aaaa1111-2222-3333-4444-555566667777"


def _assistant_with_usage(text, i):
    ev = assistant_text(text, i)
    ev["message"]["id"] = f"msg_{i}"
    ev["message"]["usage"] = {"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 100,
                              "cache_creation_input_tokens": 20}
    return ev


def _fake_home(root):
    """A miniature ~/.claude tree plus one project, mirroring the real layout."""
    home = root / "home"
    claude = home / ".claude"
    (claude / "skills" / "demo").mkdir(parents=True)
    (claude / "ctxlog").mkdir(parents=True)
    (claude / "CLAUDE.md").write_text(
        "# How to talk to me\n\nAnswer first, no preamble.\n\n"
        "## Copy to clipboard\n\nAlways pipe through `printf`, never `echo`.\n")
    (claude / "skills" / "demo" / "SKILL.md").write_text(
        "# demo\n\n## Steps\n\nRun the thing. Trigger: /demo\n")

    project = home / "Git" / "demo-project"
    project.mkdir(parents=True)
    (project / "CLAUDE.md").write_text(
        "# Project rules\n\n## Tests\n\nRun `pytest` before claiming done.\n")
    notes = project / "NOTES.md"
    notes.write_text("# Notes\n\n## Layout\n\nOne module, no build system.\n")

    events = [
        user_text("/demo please run the thing", 0),
        assistant_tool_use("Read", {"file_path": str(notes)}, 1, tool_id="t1"),
        _assistant_with_usage("Ran it. All green.", 2),
        user_text("now write the summary", 3),
        _assistant_with_usage("Done - three sentences, no jargon.", 4),
    ]
    encoded = tb.encode_cwd(str(project))
    tdir = claude / "projects" / encoded
    tdir.mkdir(parents=True)
    transcript = tdir / f"{SESSION_ID}.jsonl"
    transcript.write_text("".join(json.dumps(e) + "\n" for e in events))

    (claude / "ctxlog" / f"{SESSION_ID}.jsonl").write_text(json.dumps({
        "event": "InstructionsLoaded", "path": str(claude / "CLAUDE.md"),
        "memory_type": "user", "load_reason": "startup", "ts": _ts(0),
    }) + "\n")
    return home, project


@pytest.fixture
def captured(tmp_path):
    home, project = _fake_home(tmp_path)
    spec = {"project": "demo-project", "cwd": str(project), "session": SESSION_ID[:8]}
    snap_dir = tb.capture_session(
        spec, home=home,
        baseline_dir=tmp_path / "baseline",
        restore_root=tmp_path / "restore")
    return {"home": home, "project": project, "snap_dir": snap_dir,
            "restore_root": tmp_path / "restore", "tmp": tmp_path}


def _manifest(snap_dir):
    return json.loads((snap_dir / "manifest.json").read_text())


# ---------- the inputs, frozen ----------

def test_manifest_records_the_transcript_and_every_rule_doc(captured):
    m = _manifest(captured["snap_dir"])
    origins = {e["origin"] for e in m["inputs"]}
    assert str(captured["home"] / ".claude" / "CLAUDE.md") in origins
    assert str(captured["project"] / "CLAUDE.md") in origins
    assert str(captured["home"] / ".claude" / "skills" / "demo" / "SKILL.md") in origins
    assert str(captured["project"] / "NOTES.md") in origins
    assert str(captured["home"] / ".claude" / "ctxlog" / f"{SESSION_ID}.jsonl") in origins
    assert m["transcript"].endswith(f"{SESSION_ID}.jsonl")
    assert m["sessionId"] == SESSION_ID
    assert m["tool"]["commit"]


def test_manifest_hashes_match_the_frozen_bytes(captured):
    snap_dir = captured["snap_dir"]
    m = _manifest(snap_dir)
    assert m["inputs"]
    for entry in m["inputs"]:
        stored = snap_dir / "inputs" / entry["stored"]
        raw = gzip.decompress(stored.read_bytes()) if entry["gz"] else stored.read_bytes()
        assert tb.sha256(raw) == entry["sha256"], entry["stored"]
        assert len(raw) == entry["bytes"]


def test_verify_reports_ok_right_after_capture(captured):
    report = tb.verify_session(captured["snap_dir"], restore_root=captured["restore_root"])
    assert report["problems"] == []
    assert report["inputsVerified"] == len(_manifest(captured["snap_dir"])["inputs"])
    assert report["payloadMatched"] is True


def test_verify_flags_a_rotten_baseline_payload(captured):
    snap_dir = captured["snap_dir"]
    (snap_dir / "payload.json.gz").write_bytes(gzip.compress(b'{"perSession": {}}'))
    report = tb.verify_session(snap_dir, restore_root=captured["restore_root"])
    assert any("payload.json.gz" in p for p in report["problems"])


def test_verify_flags_a_half_written_snapshot(captured):
    snap_dir = captured["snap_dir"]
    m = _manifest(snap_dir)
    m.pop("payload")
    (snap_dir / "manifest.json").write_text(json.dumps(m))
    report = tb.verify_session(snap_dir, restore_root=captured["restore_root"])
    assert any("incomplete snapshot" in p for p in report["problems"])


def test_verify_flags_a_tampered_frozen_input(captured):
    snap_dir = captured["snap_dir"]
    entry = next(e for e in _manifest(snap_dir)["inputs"]
                 if e["origin"].endswith(".claude/CLAUDE.md"))
    stored = snap_dir / "inputs" / entry["stored"]
    body = b"# Tampered\n"
    stored.write_bytes(gzip.compress(body) if entry["gz"] else body)
    report = tb.verify_session(snap_dir, restore_root=captured["restore_root"])
    assert any("hash mismatch" in p for p in report["problems"])


# ---------- re-runnability ----------

def test_rerun_from_frozen_inputs_is_byte_identical(captured):
    m = _manifest(captured["snap_dir"])
    again = tb.bake_from_frozen(captured["snap_dir"], restore_root=captured["restore_root"])
    assert tb.sha256(again) == m["payload"]["sha256"]
    assert len(again) == m["payload"]["bytes"]


def test_rerun_ignores_a_drifted_live_rule_doc(captured):
    """The whole point: the after-run must not read today's rules."""
    (captured["home"] / ".claude" / "CLAUDE.md").write_text(
        "# Completely different rules\n\n## Nothing\n\nEverything changed.\n")
    (captured["project"] / "CLAUDE.md").unlink()
    m = _manifest(captured["snap_dir"])
    again = tb.bake_from_frozen(captured["snap_dir"], restore_root=captured["restore_root"])
    assert tb.sha256(again) == m["payload"]["sha256"]


def test_restore_materialises_the_frozen_tree_with_relocated_paths(captured):
    home, cwd = tb.restore_inputs(captured["snap_dir"], captured["restore_root"])
    assert (home / ".claude" / "CLAUDE.md").read_text().startswith("# How to talk to me")
    assert (cwd / "CLAUDE.md").is_file()
    # The transcript carries absolute paths as data, so relocation has to reach
    # inside it: left verbatim, every Read path would point outside the tree.
    transcript = home / ".claude" / "projects" / \
        tb.encode_cwd(str(captured["project"])) / f"{SESSION_ID}.jsonl"
    text = transcript.read_text()
    assert str(captured["home"]) not in text
    assert str(home) in text


def test_restore_is_idempotent(captured):
    tb.restore_inputs(captured["snap_dir"], captured["restore_root"])
    home, _ = tb.restore_inputs(captured["snap_dir"], captured["restore_root"])
    assert (home / ".claude" / "CLAUDE.md").read_text().startswith("# How to talk to me")


def test_restore_clears_files_no_longer_frozen(captured):
    """A leftover skill would be globbed back into the re-bake's context set."""
    home, _ = tb.restore_inputs(captured["snap_dir"], captured["restore_root"])
    stale = home / ".claude" / "skills" / "leftover" / "SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("# leftover\n\n## Stale\n\nFrom an earlier capture.\n")
    tb.restore_inputs(captured["snap_dir"], captured["restore_root"])
    assert not stale.exists()


def test_a_symlinked_root_still_lands_under_the_restored_home(tmp_path):
    """The loader resolves the paths it reports; the transcript does not.

    Reading only one spelling filed every rule doc outside the restored home,
    and the re-bake then judged the session as if it had no rules at all.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    home, project = _fake_home(link)
    spec = {"project": "demo-project", "cwd": str(project), "session": SESSION_ID[:8]}
    snap_dir = tb.capture_session(spec, home=home,
                                  baseline_dir=tmp_path / "baseline",
                                  restore_root=tmp_path / "restore")
    keys = {e["key"] for e in _manifest(snap_dir)["inputs"]}
    assert "home/.claude/CLAUDE.md" in keys
    assert "home/.claude/skills/demo/SKILL.md" in keys
    restored_home, _ = tb.restore_inputs(snap_dir, tmp_path / "restore")
    assert (restored_home / ".claude" / "CLAUDE.md").is_file()


# ---------- the output ----------

def test_stored_payload_is_free_of_the_restore_root(captured):
    snap_dir = captured["snap_dir"]
    raw = gzip.decompress((snap_dir / "payload.json.gz").read_bytes()).decode()
    assert str(captured["restore_root"].resolve()) not in raw
    assert tb.RESTORE_ROOT_TOKEN in raw
    data = json.loads(raw.replace(tb.RESTORE_ROOT_TOKEN, "/restored"))
    assert list(data["perSession"])[0] == SESSION_ID


def test_query_dumps_are_written_and_describe_the_session(captured):
    qdir = captured["snap_dir"] / "query"
    turns = (qdir / "turns.txt").read_text()
    assert SESSION_ID in turns
    assert (qdir / "blocks.txt").read_text().strip()
    verdicts = (qdir / "verdicts.txt").read_text()
    # One verdict record per non-delivery block, addressed by the same block id
    # the page and --query use.
    assert "block " in verdicts
    m = _manifest(captured["snap_dir"])
    assert set(m["queries"]) == {"query/turns.txt", "query/blocks.txt",
                                 "query/verdicts.txt"}


# ---------- what is frozen beside a rule doc, and inputs added after the bake ----------

def test_only_the_checks_file_the_tool_reads_is_frozen(tmp_path):
    """With both spellings beside a doc the tool reads the first one only.

    Freezing the second too would put a file in the baseline that no bake ever
    read, under a manifest claiming it is a judgement input.
    """
    doc = tmp_path / "CLAUDE.md"
    doc.write_text("# r\n")
    first = tmp_path / "CLAUDE.md.checks.json"
    second = tmp_path / "CLAUDE.checks.json"
    for p in (first, second):
        p.write_text('{"source": "CLAUDE.md", "checks": []}')
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("")
    paths = tb._loaded_inputs([str(doc)], tmp_path, transcript, "sid")
    assert first in paths and second not in paths


def test_verify_names_an_input_added_after_the_bake_as_the_reason(captured):
    """A mismatch caused by a later-frozen input is not a broken snapshot."""
    snap_dir = captured["snap_dir"]
    m = _manifest(snap_dir)
    m["payload"]["sha256"] = "0" * 64
    m["addedAfterBake"] = ["Git/demo-project/CLAUDE.md.checks.json"]
    (snap_dir / "manifest.json").write_text(json.dumps(m))
    report = tb.verify_session(snap_dir, restore_root=captured["restore_root"])
    differs = [p for p in report["problems"] if p.startswith("payload differs")]
    assert len(differs) == 1
    assert "added after the baseline was baked" in differs[0]
    assert "Git/demo-project/CLAUDE.md.checks.json" in differs[0]
