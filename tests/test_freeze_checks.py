"""Freezing the reviewed checks files into the private baselines.

The checks file is a judgement input: the same prose scores differently with
and without it. It is committed under `snapshots/checks/` while the tree it is
frozen into is not, so this script is the only thing joining the two - and a
manifest entry it writes wrongly would make `verify` fail on a corpus nobody
can inspect from a clone.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))

import freeze_checks as fc  # noqa: E402
import take_baseline as tb  # noqa: E402


def _corpus(tmp_path, body='{"source": "x", "checks": []}'):
    checks = tmp_path / "checks" / "proj" / "abc12345" / "home" / "CLAUDE.md.checks.json"
    checks.parent.mkdir(parents=True)
    checks.write_text(body, encoding="utf-8")
    snap = tmp_path / "baseline" / "proj" / "abc12345"
    snap.mkdir(parents=True)
    (snap / "manifest.json").write_text(json.dumps(
        {"sessionId": "abc12345-x", "project": "proj",
         "inputs": [{"key": "home/CLAUDE.md", "stored": "home/CLAUDE.md",
                     "sha256": "0" * 64, "bytes": 3, "gz": False}]}), encoding="utf-8")
    return tmp_path / "checks", tmp_path / "baseline", checks, snap


def test_a_checks_file_not_yet_frozen_is_reported_as_pending(tmp_path):
    checks, baseline, src, snap = _corpus(tmp_path)
    rows = fc.pending(checks, baseline)
    assert [(r[2], r[3]) for r in rows] == [("home/CLAUDE.md.checks.json", False)]


def test_freezing_writes_the_file_and_records_it_in_the_manifest(tmp_path):
    checks, baseline, src, snap = _corpus(tmp_path)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    stored = snap / "inputs" / "home" / "CLAUDE.md.checks.json"
    assert stored.read_bytes() == src.read_bytes()
    entry = next(e for e in json.loads((snap / "manifest.json").read_text())["inputs"]
                 if e["key"] == "home/CLAUDE.md.checks.json")
    assert entry["sha256"] == tb.sha256(src.read_bytes())
    assert entry["bytes"] == len(src.read_bytes()) and entry["gz"] is False
    assert fc.pending(checks, baseline)[0][3] is True


def test_refreezing_an_edited_file_replaces_the_entry_rather_than_adding_one(tmp_path):
    """Two entries for one key would make `verify` hash the stale one."""
    checks, baseline, src, snap = _corpus(tmp_path)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    src.write_text('{"source": "x", "checks": [], "note": "edited"}', encoding="utf-8")
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    inputs = json.loads((snap / "manifest.json").read_text())["inputs"]
    keys = [e["key"] for e in inputs]
    assert keys == sorted(keys) and keys.count("home/CLAUDE.md.checks.json") == 1
    assert next(e for e in inputs if e["key"].endswith(".checks.json"))["sha256"] == \
        tb.sha256(src.read_bytes())


def test_an_edited_source_is_reported_stale_rather_than_frozen(tmp_path):
    """The `--check` gate has to be able to fail, or it reports clean forever."""
    checks, baseline, src, snap = _corpus(tmp_path)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    assert fc.pending(checks, baseline)[0][3] is True
    src.write_text('{"source": "x", "checks": [], "note": "drifted"}', encoding="utf-8")
    assert fc.pending(checks, baseline)[0][3] is False


def _with_payload(snap, **extra):
    m = json.loads((snap / "manifest.json").read_text())
    m["payload"] = {"file": "payload.json.gz", "sha256": "1" * 64, "bytes": 1}
    m.update(extra)
    (snap / "manifest.json").write_text(json.dumps(m))


def test_freezing_into_an_already_baked_snapshot_records_it_as_added_after(tmp_path):
    """The baseline payload never read this file, and the scorecard must know."""
    checks, baseline, src, snap = _corpus(tmp_path)
    _with_payload(snap)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    m = json.loads((snap / "manifest.json").read_text())
    assert m["addedAfterBake"] == ["home/CLAUDE.md.checks.json"]
    assert tb.inputs_added_after_bake(m) == ["home/CLAUDE.md.checks.json"]


def test_freezing_before_any_bake_records_nothing_as_added_after(tmp_path):
    checks, baseline, src, snap = _corpus(tmp_path)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    m = json.loads((snap / "manifest.json").read_text())
    assert "addedAfterBake" not in m
    assert tb.inputs_added_after_bake(m) == []


def test_a_legacy_entry_is_carried_into_the_new_record(tmp_path):
    """A manifest frozen before the field existed must not lose its earlier add."""
    checks, baseline, src, snap = _corpus(tmp_path)
    m = json.loads((snap / "manifest.json").read_text())
    m["inputs"].append({"key": "home/AGENTS.md.checks.json", "stored": "home/AGENTS.md.checks.json",
                        "origin": str(tmp_path / "repo" / "snapshots" / "checks" / "proj" /
                                      "abc12345" / "home" / "AGENTS.md.checks.json"),
                        "sha256": "0" * 64, "bytes": 1, "gz": False})
    (snap / "manifest.json").write_text(json.dumps(m))
    _with_payload(snap)
    fc.freeze_one(src, snap, "home/CLAUDE.md.checks.json")
    m = json.loads((snap / "manifest.json").read_text())
    assert m["addedAfterBake"] == ["home/AGENTS.md.checks.json", "home/CLAUDE.md.checks.json"]


def test_a_frozen_checks_file_with_no_committed_copy_is_reported_unreviewed(tmp_path):
    """The gate enumerates from the committed side, so an absent file was
    invisible to it: a red badge could rest on a pattern no reader of the repo
    can review, and `--check` would print clean.

    The control is the same file once it *is* committed - otherwise this passes
    whatever the code does.
    """
    checks, baseline, src, snap = _corpus(tmp_path)
    private = snap / "inputs" / "home" / "Git" / "CLIENT.md.checks.json"
    private.parent.mkdir(parents=True, exist_ok=True)
    private.write_text('{"source": "~/Git/CLIENT.md", "checks": []}', encoding="utf-8")
    assert fc.unreviewed(checks, baseline) == [
        ("proj/abc12345", "home/Git/CLIENT.md.checks.json")]

    mirror = checks / "proj" / "abc12345" / "home" / "Git" / "CLIENT.md.checks.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(private.read_text(), encoding="utf-8")
    assert fc.unreviewed(checks, baseline) == []
