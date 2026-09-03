"""The Phase 14 before/after scorecard, scored against a synthetic triple.

The regressed case is the one that matters: a `regressed` row is the release
blocker Phase 14 exists to catch, so a scorer that silently folded it into
`still-wrong` would let the whole gate pass while the judging got worse.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))

import compare  # noqa: E402


def _expected(entries):
    lines = ["# Ground truth - synthetic", "", "## Verdicts", ""]
    for bid, truth, tag, ev in entries:
        lines.append(f"- {bid} :: {truth} :: {tag} :: {ev}")
    return "\n".join(lines) + "\n"


def _payload(session_id, statuses):
    return {"perSession": {session_id: {"contextFiles": [
        {"path": "~/doc.md", "blocks": [{"id": bid, "title": bid, "status": st}
                                        for bid, st in statuses.items()]}]}}}


TRIPLE = [
    # (block, truth, tag, baseline status, after status, expected outcome)
    ("agreed-green", "used", "F-TRIGGER", "used", "used", "agreed"),
    ("agreed-quiet", "no-hard-verdict", "-", "dormant", "unused", "agreed"),
    ("fixed-false-green", "no-hard-verdict", "F-PATHTABLE", "used", "dormant", "fixed"),
    ("fixed-false-red", "no-hard-verdict", "F-EOM", "ignored", "dormant", "fixed"),
    ("fixed-missed", "used", "F-BLINDSPOT", "unused", "used", "fixed"),
    ("regressed", "used", "F-BLINDSPOT", "used", "unused", "regressed"),
    ("still-wrong", "used", "F-EOM", "dormant", "dormant", "still-wrong"),
    ("undecidable", "undecidable", "-", "ignored", "used", "excluded"),
]


def _triple_files(tmp_path):
    sid = "synthetic-session"
    root = tmp_path
    exp = root / "expected" / "proj" / "synth"
    exp.mkdir(parents=True)
    (exp / "expected.md").write_text(
        _expected([(b, t, g, "evidence") for b, t, g, _, _, _ in TRIPLE]), encoding="utf-8")
    for tree, idx in (("baseline", 3), ("after", 4)):
        d = root / tree / "proj" / "synth"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"sessionId": sid, "project": "proj"}))
        payload = _payload(sid, {row[0]: row[idx] for row in TRIPLE})
        (d / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def test_every_outcome_including_the_regressed_one_is_scored(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    got = {r["id"]: r["outcome"] for r in report["rows"]}
    assert got == {b: outcome for b, _, _, _, _, outcome in TRIPLE}


def test_the_regressed_row_is_reported_as_a_blocker(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["regressed"] == 1
    assert compare.blockers(report) == ["proj/synth regressed"]


def test_error_kinds_name_which_way_the_verdict_is_wrong(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    kinds = {r["id"]: (r["beforeError"], r["afterError"]) for r in report["rows"]}
    assert kinds["fixed-false-green"] == ("false-green", None)
    assert kinds["fixed-false-red"] == ("false-red", None)
    assert kinds["fixed-missed"] == ("missed-compliance", None)
    assert kinds["regressed"] == (None, "missed-compliance")
    assert kinds["agreed-quiet"] == (None, None)


def test_undecidable_blocks_are_excluded_from_the_totals(tmp_path):
    """Counting them either way would invent a measurement.

    The class exists because the frozen inputs could not settle the question,
    so scoring the tool against it would report agreement or error on the
    strength of a guess.
    """
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    t = report["totals"]
    assert t["excluded"] == 1
    assert t["scored"] == len(TRIPLE) - 1
    assert (t["agreedBefore"] + t["falseGreenBefore"] + t["falseRedBefore"]
            + t["missedBefore"] + t["absentBefore"]) == t["scored"]


def test_a_block_the_after_run_no_longer_judges_counts_as_absent_not_agreement(tmp_path):
    """Silence is not a verdict, and a vanished block must not read as a pass.

    A delivery reclassification can drop a block out of the judged set; folding
    that into `agreed` would hide it in exactly the run meant to detect it.
    """
    root = _triple_files(tmp_path)
    after = root / "after" / "proj" / "synth" / "payload.json"
    payload = json.loads(after.read_text())
    files = payload["perSession"]["synthetic-session"]["contextFiles"][0]
    files["blocks"] = [b for b in files["blocks"] if b["id"] != "agreed-green"]
    after.write_text(json.dumps(payload), encoding="utf-8")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    row = next(r for r in report["rows"] if r["id"] == "agreed-green")
    assert row["after"] == "(absent)"
    assert row["outcome"] == "regressed"
    assert row["afterError"] == "absent"
    assert report["totals"]["absentAfter"] == 1


def test_a_block_no_ground_truth_covers_is_reported_as_outside_the_gate(tmp_path):
    """A green the after-run invented must not escape scoring in silence.

    The ground truth is written from the baseline's judged set, so a block only
    the after-run judges has no line to score against - and without this it
    would simply not appear.
    """
    root = _triple_files(tmp_path)
    after = root / "after" / "proj" / "synth" / "payload.json"
    payload = json.loads(after.read_text())
    blocks = payload["perSession"]["synthetic-session"]["contextFiles"][0]["blocks"]
    blocks.append({"id": "brand-new", "title": "brand-new", "status": "used"})
    after.write_text(json.dumps(payload), encoding="utf-8")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert any("brand-new" in u and "no ground truth" in u for u in report["unscored"])
    assert "brand-new" in "\n".join(compare.render(report))


def test_ground_truth_for_a_block_neither_payload_judges_is_reported(tmp_path):
    """A stale id would otherwise be scored as a permanent miss with no cause."""
    root = _triple_files(tmp_path)
    exp = root / "expected" / "proj" / "synth" / "expected.md"
    exp.write_text(exp.read_text() + "- long-gone :: used :: - :: was here once\n",
                   encoding="utf-8")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert any("long-gone" in u and "neither payload judges" in u for u in report["unscored"])


def test_the_mechanism_breakdown_groups_by_tag(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    blindspot = report["byTag"]["F-BLINDSPOT"]
    assert (blindspot["fixed"], blindspot["regressed"]) == (1, 1)


def test_the_scorecard_renders_every_still_wrong_and_regressed_row(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert "still-wrong" in text and "regressed" in text
    assert "still-wrong" in text.split("## Rows that are still wrong")[1]


def test_a_gzipped_payload_is_read_like_a_plain_one(tmp_path):
    """The trees hold `payload.json.gz`; the tests write plain JSON."""
    import gzip
    root = _triple_files(tmp_path)
    plain = root / "after" / "proj" / "synth" / "payload.json"
    (plain.parent / "payload.json.gz").write_bytes(gzip.compress(plain.read_bytes()))
    plain.unlink()
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["regressed"] == 1


def test_expected_files_parse_with_their_accept_notes(tmp_path):
    path = tmp_path / "expected.md"
    path.write_text("## Verdicts\n"
                    "- b1 :: used :: F-EOM :: cited thing\n"
                    "  accept: needs a compiled communication-scope check\n"
                    "- b2 :: no-hard-verdict :: - :: nothing cites it\n", encoding="utf-8")
    got = compare.load_expected(path)
    assert got["b1"]["accept"].startswith("needs a compiled")
    assert got["b2"]["tag"] is None


def test_an_unknown_truth_class_is_refused_rather_than_scored(tmp_path):
    """A typo in a truth class would otherwise be silently excluded.

    The exclusion path exists for `undecidable` alone; letting a misspelling
    take it drops a block out of the gate with nothing saying so.
    """
    path = tmp_path / "expected.md"
    path.write_text("## Verdicts\n- b1 :: used-ish :: - :: typo\n", encoding="utf-8")
    try:
        compare.load_expected(path)
    except ValueError as e:
        assert "used-ish" in str(e)
    else:
        raise AssertionError("an unknown truth class must be refused")


def test_the_real_ground_truth_files_parse_and_cover_the_snapshots():
    """The committed corpus must stay loadable and complete.

    An expected.md that stopped covering a session would quietly shrink the
    gate to the sessions that still pass.
    """
    root = Path(__file__).resolve().parent.parent / "snapshots"
    if not (root / "expected").is_dir():
        return
    for manifest in sorted((root / "baseline").glob("*/*/manifest.json")):
        exp = root / "expected" / manifest.parent.parent.name / manifest.parent.name / "expected.md"
        assert exp.is_file(), f"no ground truth for {manifest.parent}"
        entries = compare.load_expected(exp)
        judged = compare.judged_statuses(compare.read_payload(manifest.parent))
        assert set(judged) <= set(entries), f"{exp}: blocks with no ground truth"
