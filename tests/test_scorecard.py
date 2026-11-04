"""The Phase 14 before/after scorecard, scored against a synthetic triple.

The regressed case is the one that matters: a `regressed` row is the release
blocker Phase 14 exists to catch, so a scorer that silently folded it into
`still-wrong` would let the whole gate pass while the judging got worse.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))

import compare  # noqa: E402


RULINGS_LINK = "snapshots/expected/RULINGS.md"
DIRECTORY_RULING = "A file created under a directory the block names does not count."


def _header(link=RULINGS_LINK, ruling=DIRECTORY_RULING):
    """A minimal expected.md header carrying both things the scorer insists on."""
    return (f"# Ground truth - synthetic\n\nThe rulings this file applies are in\n"
            f"`{link}`. In particular: {ruling}\n\n## Verdicts\n\n")


def _expected(entries):
    lines = _header().splitlines()
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


def test_a_block_the_after_run_reports_undelivered_is_scored_on_that_answer(tmp_path):
    """`not-loaded` is the tool's answer about a block, not silence, and the
    totals count the delivery change so it is not hidden in `agreed`."""
    root = _triple_files(tmp_path)
    after = root / "after" / "proj" / "synth" / "payload.json"
    payload = json.loads(after.read_text())
    for b in payload["perSession"]["synthetic-session"]["contextFiles"][0]["blocks"]:
        if b["id"] in ("agreed-quiet", "agreed-green"):
            b["status"] = "not-loaded"
    after.write_text(json.dumps(payload), encoding="utf-8")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    quiet = next(r for r in report["rows"] if r["id"] == "agreed-quiet")
    green = next(r for r in report["rows"] if r["id"] == "agreed-green")
    assert (quiet["after"], quiet["outcome"]) == ("not-loaded", "agreed")
    assert (green["afterError"], green["outcome"]) == ("missed-compliance", "regressed")
    assert report["totals"]["nowUndelivered"] == 2


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
    path.write_text(_header()
                    + "- b1 :: used :: F-EOM :: cited thing\n"
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
    path.write_text(_header() + "- b1 :: used-ish :: - :: typo\n", encoding="utf-8")
    try:
        compare.load_expected(path)
    except ValueError as e:
        assert "used-ish" in str(e)
    else:
        raise AssertionError("an unknown truth class must be refused")


def test_the_real_ground_truth_files_parse_and_declare_what_they_cover():
    """The committed corpus must stay loadable, and never shrink in silence.

    A ground truth that stopped covering a session would quietly shrink the
    gate to the sessions that still pass. That is still what this asserts - a
    file is complete unless it *says* it is partial, in its own header, where
    a reviewer reading the file sees it and the scorecard counts what it left
    out. The Phase 0 false-red set is partial by design: its question is one
    block's red badge, and bulk rows nobody derived would swamp the corpus
    that was derived.

    A partial file still has to name blocks the payload actually judges, or a
    stale line would be scored as a miss. The frozen transcripts are the
    author's own and are gitignored, so on a clone this skips by name - a bare
    `return` here would report the same green as a full run.
    """
    root = Path(__file__).resolve().parent.parent / "snapshots"
    for needed in (root / "expected", root / "baseline"):
        if not needed.is_dir():
            pytest.skip(f"{needed} is absent, so the real ground truth cannot "
                        "be checked against the frozen payloads it scores")
    for manifest in sorted((root / "baseline").glob("*/*/manifest.json")):
        exp = root / "expected" / manifest.parent.parent.name / manifest.parent.name / "expected.md"
        assert exp.is_file(), f"no ground truth for {manifest.parent}"
        entries = compare.load_expected(exp)
        judged = compare.judged_statuses(compare.read_payload(manifest.parent))
        if compare.partial_scope(exp):
            assert entries, f"{exp}: declares a partial scope and covers nothing"
            assert set(entries) <= set(judged), f"{exp}: rows for unjudged blocks"
        else:
            assert set(judged) <= set(entries), f"{exp}: blocks with no ground truth"


def test_a_partial_ground_truth_is_counted_not_named(tmp_path):
    """Naming them would publish a client repository's document names.

    A block id carries its document's path, so listing the out-of-scope blocks
    of a 111-block session writes those paths into `SCORECARD.md`, which is
    committed - while the transcripts they come from are gitignored precisely
    to keep them out.
    """
    root = _authorised_files(tmp_path, "ignored", "ignored")
    exp = root / "expected" / "ozz" / "auth" / "expected.md"
    payload = json.loads((root / "after" / "ozz" / "auth" / "payload.json").read_text())
    blocks = payload["perSession"]["authorised-session"]["contextFiles"][0]["blocks"]
    blocks.append({"id": "secret-client-doc-md-0-pricing", "title": "x", "status": "unused"})
    for tree in ("baseline", "after"):
        (root / tree / "ozz" / "auth" / "payload.json").write_text(json.dumps(payload))

    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert "secret-client-doc" not in text
    assert "1 judged block(s) outside this ground truth's declared scope" in text

    # Without the marker the same corpus names them, so the collapse is the
    # declaration's doing and not a silent change of behaviour.
    exp.write_text(exp.read_text().replace(compare.PARTIAL_MARKER, "It is complete."),
                   encoding="utf-8")
    plain = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert "secret-client-doc" in "\n".join(compare.render(plain))


# ---------- Phase 8: the header contract, and what the corpus does not measure ----------

def _expected_with_header(entries, header=None):
    body = "\n".join(f"- {bid} :: {truth} :: {tag} :: {ev}" for bid, truth, tag, ev in entries)
    return (header if header is not None else _header()) + body + "\n"


def test_an_expected_file_that_does_not_reference_the_rulings_is_refused(tmp_path):
    """Two readings of `used` are two corpora, and the totals would mix them."""
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")],
                                          header="## Verdicts\n\n"), encoding="utf-8")
    with pytest.raises(ValueError) as e:
        compare.load_expected(path)
    assert "RULINGS.md" in str(e.value)


def test_an_expected_file_that_omits_the_disputed_ruling_is_refused(tmp_path):
    """The directory sentence is the one the corpus was scored two ways under.

    A header that links the rulings file without quoting it can be a header
    written before the ruling existed, which is exactly the corpus this phase
    had to repair.
    """
    path = tmp_path / "expected.md"
    header = f"# h\n\nRulings: `{RULINGS_LINK}`.\n\n## Verdicts\n\n"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")], header=header),
                    encoding="utf-8")
    with pytest.raises(ValueError) as e:
        compare.load_expected(path)
    assert "directory" in str(e.value)


def test_a_header_carrying_both_loads(tmp_path):
    """The positive control: the refusals above are not refusing everything."""
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")]), encoding="utf-8")
    assert compare.load_expected(path)["b1"]["truth"] == "used"


def test_a_revised_row_without_a_blind_line_is_refused(tmp_path):
    """A correction made while looking at the answer has to be visible as one."""
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")])
                    + "  revised: corrected after the run\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        compare.load_expected(path)
    assert "blind:" in str(e.value) and "b1" in str(e.value)


def test_a_revised_row_with_a_blind_line_records_it(tmp_path):
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")])
                    + "  revised: re-derived under ruling 3\n  blind: yes\n", encoding="utf-8")
    got = compare.load_expected(path)["b1"]
    assert got["revised"].startswith("re-derived") and got["blind"] == "yes"


def test_a_blind_line_outside_the_closed_set_is_refused(tmp_path):
    """`blind: partly` is a claim nobody can check; the answer is yes or no."""
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")])
                    + "  revised: x\n  blind: partly\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        compare.load_expected(path)
    assert "partly" in str(e.value)


def _coverage_files(tmp_path, truths, checks_file=False):
    sid = "synthetic-session"
    exp = tmp_path / "expected" / "proj" / "synth"
    exp.mkdir(parents=True)
    entries = [(bid, truth, "-", "evidence") for bid, truth in truths.items()]
    (exp / "expected.md").write_text(_expected_with_header(entries), encoding="utf-8")
    for tree in ("baseline", "after"):
        d = tmp_path / tree / "proj" / "synth"
        d.mkdir(parents=True)
        manifest = {"sessionId": sid, "project": "proj"}
        if checks_file and tree == "baseline":
            manifest["inputs"] = [{"key": "home/CLAUDE.md"},
                                  {"key": "home/CLAUDE.md.checks.json"}]
        (d / "manifest.json").write_text(json.dumps(manifest))
        statuses = {bid: ("ignored" if truth == "violated" else "used")
                    for bid, truth in truths.items()}
        (d / "payload.json").write_text(json.dumps(_payload(sid, statuses)), encoding="utf-8")
    return tmp_path


def test_the_scorecard_counts_violated_truths_and_compiled_checks_files(tmp_path):
    root = _coverage_files(tmp_path, {"v": "violated", "u": "used"}, checks_file=True)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["violatedTruths"] == 1
    assert report["checksFiles"] == ["proj/synth"]
    text = "\n".join(compare.render(report))
    assert "1 `violated` truth" in text and "1 session carries a compiled checks file" in text


def test_a_corpus_with_no_red_side_says_so_in_the_header(tmp_path):
    """Without a violated truth or a checks file, "false reds: 0" measures nothing."""
    root = _coverage_files(tmp_path, {"u": "used"}, checks_file=False)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["violatedTruths"] == 0 and report["checksFiles"] == []
    text = "\n".join(compare.render(report))
    assert "the red side of this corpus is unmeasured" in text


def test_the_two_halves_are_tallied_separately(tmp_path):
    """Skill blocks and rule-document blocks measure different things.

    A ruling that greens every block of an invoked skill can carry the headline
    on its own, which is how a rule-document agreement that barely moved was
    reported as a corpus-wide improvement.
    """
    sid = "s"
    exp = tmp_path / "expected" / "proj" / "synth"
    exp.mkdir(parents=True)
    (exp / "expected.md").write_text(_expected_with_header(
        [("skill-b", "used", "-", "invoked"), ("rule-b", "no-hard-verdict", "-", "quiet")]),
        encoding="utf-8")
    for tree, rule_status in (("baseline", "used"), ("after", "dormant")):
        d = tmp_path / tree / "proj" / "synth"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"sessionId": sid, "project": "proj"}))
        payload = {"perSession": {sid: {"contextFiles": [
            {"path": "~/s/SKILL.md", "kind": "skill",
             "blocks": [{"id": "skill-b", "title": "s", "status": "used"}]},
            {"path": "~/CLAUDE.md", "kind": "global",
             "blocks": [{"id": "rule-b", "title": "r", "status": rule_status}]}]}}}
        (d / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    report = compare.compare_all(tmp_path / "baseline", tmp_path / "after",
                                 tmp_path / "expected")
    assert report["byHalf"]["skill"]["agreedAfter"] == 1
    assert report["byHalf"]["skill"]["fixed"] == 0
    assert report["byHalf"]["rule-document"]["fixed"] == 1
    text = "\n".join(compare.render(report))
    assert "## Skill and command blocks" in text and "## Rule-document blocks" in text


# ---------- a block the baseline never judged, and truth revised with sight ----------

def _two_tree_files(tmp_path, rows, baseline_manifest=None):
    """rows: (block, truth, before status or None for absent, after status or None)."""
    sid = "s"
    exp = tmp_path / "expected" / "proj" / "synth"
    exp.mkdir(parents=True)
    (exp / "expected.md").write_text(
        _expected_with_header([(b, t, "-", "ev") for b, t, _, _ in rows]),
        encoding="utf-8")
    for tree, idx in (("baseline", 2), ("after", 3)):
        d = tmp_path / tree / "proj" / "synth"
        d.mkdir(parents=True)
        manifest = {"sessionId": sid, "project": "proj"}
        if tree == "baseline" and baseline_manifest:
            manifest.update(baseline_manifest)
        (d / "manifest.json").write_text(json.dumps(manifest))
        payload = _payload(sid, {r[0]: r[idx] for r in rows if r[idx] is not None})
        (d / "payload.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def _report(root):
    return compare.compare_all(root / "baseline", root / "after", root / "expected")


def test_a_block_the_baseline_never_judged_gets_its_own_outcome(tmp_path):
    """Absent before is not an error the after-run fixed or kept.

    Filed as `fixed` it inflates the improvement; filed as `still-wrong` a new
    false green never reaches the release gate.
    """
    root = _two_tree_files(tmp_path, [
        ("new-right", "no-hard-verdict", None, "dormant"),
        ("new-green", "no-hard-verdict", None, "used"),
    ])
    report = _report(root)
    got = {r["id"]: r["outcome"] for r in report["rows"]}
    assert got == {"new-right": "new-agreed", "new-green": "new-wrong"}
    t = report["totals"]
    assert (t["new-agreed"], t["new-wrong"], t["fixed"], t["still-wrong"]) == (1, 1, 0, 0)


def test_a_new_wrong_row_is_a_release_blocker(tmp_path):
    root = _two_tree_files(tmp_path, [("new-green", "no-hard-verdict", None, "used")])
    report = _report(root)
    assert compare.blockers(report) == ["proj/synth new-green"]
    text = "\n".join(compare.render(report))
    blockers_section = text.split("## Release blockers")[1].split("\n## ")[0]
    assert "new-green" in blockers_section
    assert "new agreed 0" in text and "new wrong 1" in text


def test_rows_resting_on_a_non_blind_revision_are_counted(tmp_path):
    """A correction made while looking at the answer can ratify the tool."""
    root = _two_tree_files(tmp_path, [
        ("fixed-seen", "used", "unused", "used"),
        ("agreed-seen", "used", "used", "used"),
        ("new-seen", "used", None, "used"),
        ("fixed-blind", "used", "unused", "used"),
        ("wrong-seen", "used", "unused", "unused"),
    ])
    exp = root / "expected" / "proj" / "synth" / "expected.md"
    lines = exp.read_text().splitlines()
    out = []
    for line in lines:
        out.append(line)
        for bid, blind in (("fixed-seen", "no"), ("agreed-seen", "no"),
                           ("new-seen", "no"), ("fixed-blind", "yes"),
                           ("wrong-seen", "no")):
            if line.startswith(f"- {bid} ::"):
                out += ["  revised: re-derived", f"  blind: {blind}"]
    exp.write_text("\n".join(out) + "\n", encoding="utf-8")
    report = _report(root)
    assert report["totals"]["nonBlindCredited"] == 3
    text = "\n".join(compare.render(report))
    assert "3 of the fixed / agreed / new-agreed rows rest on a truth revised with `blind: no`" in text


def test_a_repeated_block_id_is_refused(tmp_path):
    """The second line would silently overwrite the first's truth."""
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "a"),
                                           ("b1", "no-hard-verdict", "-", "b")]),
                    encoding="utf-8")
    with pytest.raises(ValueError) as e:
        compare.load_expected(path)
    assert "b1" in str(e.value)


def test_a_note_in_a_later_prose_section_does_not_attach_to_the_last_row(tmp_path):
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")])
                    + "\n## Notes\n\naccept: this is prose about something else\n",
                    encoding="utf-8")
    assert compare.load_expected(path)["b1"]["accept"] is None


def test_an_indented_note_still_attaches_after_a_blank_line(tmp_path):
    path = tmp_path / "expected.md"
    path.write_text(_expected_with_header([("b1", "used", "-", "cited")])
                    + "\n  accept: known limit\n", encoding="utf-8")
    assert compare.load_expected(path)["b1"]["accept"] == "known limit"


# ---------- an input frozen into the baseline after its payload was baked ----------

def test_an_input_added_after_the_bake_is_named_on_the_session_and_its_moved_rows(tmp_path):
    """The after-run reads the added file and the baseline payload never did.

    A verdict that moved there may have moved because of the input, so the
    header's "same inputs" claim has to stop being made about that session.
    """
    root = _two_tree_files(tmp_path, [
        ("moved", "used", "unused", "used"),
        ("still", "used", "used", "used"),
    ], baseline_manifest={"payload": {"sha256": "x"},
                          "addedAfterBake": ["home/CLAUDE.md.checks.json"]})
    report = _report(root)
    assert report["inputChanged"] == {"proj/synth": ["home/CLAUDE.md.checks.json"]}
    flags = {r["id"]: r["inputChanged"] for r in report["rows"]}
    assert flags == {"moved": True, "still": False}
    text = "\n".join(compare.render(report))
    assert "input changed after baseline" in text
    per_session = text.split("## Per session")[1].split("\n## ")[0]
    assert "proj/synth (input changed after baseline)" in per_session


def test_a_legacy_manifest_is_read_off_the_origin_freeze_checks_wrote(tmp_path):
    """Manifests frozen before `addedAfterBake` existed still say so.

    `capture` rewrites the manifest and bakes in one call, so an entry whose
    origin is the committed checks tree can only have been added afterwards.
    """
    root = _two_tree_files(tmp_path, [("moved", "used", "unused", "used")],
                           baseline_manifest={"payload": {"sha256": "x"}, "inputs": [
                               {"key": "home/CLAUDE.md", "origin": "/h/CLAUDE.md"},
                               {"key": "home/CLAUDE.md.checks.json",
                                "origin": "/x/repo/snapshots/checks/proj/synth/home/"
                                          "CLAUDE.md.checks.json"}]})
    assert _report(root)["inputChanged"] == {"proj/synth": ["home/CLAUDE.md.checks.json"]}


def test_a_session_with_unchanged_inputs_keeps_the_same_inputs_claim(tmp_path):
    root = _triple_files(tmp_path)
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["inputChanged"] == {}
    assert "input changed after baseline" not in "\n".join(compare.render(report))


# ---------- exit status ----------

def _run_main(monkeypatch, root, *extra):
    monkeypatch.setattr(sys, "argv", ["compare.py", "--baseline-dir", str(root / "baseline"),
                                      "--after-dir", str(root / "after"),
                                      "--expected-dir", str(root / "expected"), *extra])
    compare.main()


def _clean_two_sessions(tmp_path):
    root = _two_tree_files(tmp_path, [("ok", "used", "used", "used")])
    second = root / "expected" / "proj" / "other"
    second.mkdir(parents=True)
    (second / "expected.md").write_text(
        (root / "expected" / "proj" / "synth" / "expected.md").read_text())
    return root


def test_a_partial_corpus_exits_non_zero(tmp_path, monkeypatch, capsys):
    """A gate scored over fewer sessions than it names reports a number it did not earn."""
    root = _clean_two_sessions(tmp_path)
    with pytest.raises(SystemExit) as e:
        _run_main(monkeypatch, root)
    assert e.value.code not in (0, None)
    assert "proj/other" in str(e.value.code)


def test_a_partial_corpus_passes_only_when_allowed_explicitly(tmp_path, monkeypatch, capsys):
    root = _clean_two_sessions(tmp_path)
    _run_main(monkeypatch, root, "--allow-partial")
    assert "proj/other" in capsys.readouterr().out


# ---------- the `authorised` truth class ----------
#
# The corpus holds no clean unsupervised violation: every candidate action was
# ordered in the prompt that caused it. So the red side is measured against
# `authorised` rows, where the rule's action demonstrably happened and the user
# asked for it. A red badge there is a false red - the worst failure this tool
# has - and the header has to say that this is what the false-red count is
# measured against, because a reader who thinks it covers unsupervised
# violations is reading a number the corpus cannot produce.

def _authorised_files(tmp_path, before, after):
    sid = "authorised-session"
    exp = tmp_path / "expected" / "ozz" / "auth"
    exp.mkdir(parents=True)
    (exp / "expected.md").write_text(
        _expected([("push-rule", "authorised", "F-AUTHORISED", "call 12 pushed, prompt said to")])
        + f"\n{compare.PARTIAL_MARKER}\n",
        encoding="utf-8")
    for tree, status in (("baseline", before), ("after", after)):
        d = tmp_path / tree / "ozz" / "auth"
        d.mkdir(parents=True)
        (d / "manifest.json").write_text(json.dumps({"sessionId": sid, "project": "ozz"}))
        (d / "payload.json").write_text(json.dumps(_payload(sid, {"push-rule": status})),
                                        encoding="utf-8")
    return tmp_path


def test_a_red_badge_on_an_authorised_row_is_a_false_red(tmp_path):
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["falseRedBefore"] == 1
    assert report["totals"]["falseRedAfter"] == 1


def test_an_authorised_row_the_tool_stops_accusing_is_fixed(tmp_path):
    root = _authorised_files(tmp_path, "ignored", "dormant")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["falseRedAfter"] == 0
    assert [r["outcome"] for r in report["rows"]] == ["fixed"]


def test_a_green_on_an_authorised_row_is_still_a_false_green(tmp_path):
    """The downgrade is to `acknowledged`, never to credit for the rule."""
    root = _authorised_files(tmp_path, "used", "used")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["falseGreenAfter"] == 1


def test_the_header_says_the_red_side_is_measured_against_authorised_rows(tmp_path):
    root = _authorised_files(tmp_path, "ignored", "dormant")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert "authorised" in text
    assert compare.NO_UNSUPERVISED_VIOLATION in text


def test_the_header_says_how_many_reds_stand_on_authorised_rows(tmp_path):
    """The headline a reader quotes went 0 -> 6 false reds, and that number is
    the offline design working: offline the finding stays `violated` and only
    the judged run downgrades it. A header that reports the count without
    saying what it is made of reads as the tool having got worse."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    assert report["totals"]["falseRedAuthorisedAfter"] == 1
    text = "\n".join(compare.render(report))
    assert compare.OFFLINE_RED_ON_AUTHORISED in text
    assert "1 of the 1 red" in text


def test_the_header_names_the_acceptance_criteria_this_corpus_does_not_meet(tmp_path):
    """Three criteria this corpus is measured against are unmet, and each was
    disclosed in a different file. A reader quoting `false red 6` from the gate
    itself met the explanation of what the sixth is made of, but not the fact
    that two criteria the corpus was built to satisfy are still open - the
    judged run clears five of six rather than six, and the frozen set is four
    `authorised` of six with a seventh session left out.

    Named here, in the generated file, because that is where the number lives.
    """
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert compare.CRITERIA_UNMET in text
    assert compare.FROZEN_SET_SHORTFALL in text
