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


def test_the_scorecard_puts_both_tiers_false_counts_side_by_side(tmp_path):
    """The pair is the whole argument for the architecture: the compiled path
    may accuse and the judge may not, and the only thing that justifies that
    asymmetry is the two false-green counts next to each other. Split across
    two documents a reader quotes one of them."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    t = report["totals"]
    j = compare.load_blind_judge()
    assert "## Both tiers, side by side" in text
    if compare.reproducible(j):
        # Both rows come off the record, which scored the two tiers over one
        # block set. The pair is the argument; a pair over two sets is not one.
        assert (f"| compiled checks (this corpus, after, {j['blocks']} blocks) | "
                f"{j['codeFalseGreen']} | {j['codeFalseRed']} | "
                f"{j['codeMissed']} |") in text
        assert (f"| blind judge ({j['when']}, {j['blocks']} blocks, "
                f"`{j['model']}`) | "
                f"{j['falseGreen']} | {j['falseRed']} | {j['missed']} |") in text
    else:
        assert (f"| compiled checks (this corpus, after) | {t['falseGreenAfter']} | "
                f"{t['falseRedAfter']} | {t['missedAfter']} |") in text
        assert (f"| blind judge ({j['when']}, {j['blocks']} blocks) | "
                f"{j['falseGreen']} | {j['falseRed']} | {j['missed']} |") in text


def test_the_judge_tier_row_says_it_was_not_re_measured(tmp_path):
    """Those numbers are a dated experiment, not a reading of this corpus. A
    table that prints them in the same shape as the measured row has to say
    so in its own prose, or the pair reads as one run."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert compare.blind_judge_provenance(compare.load_blind_judge()) in text


def test_the_scorecard_states_the_contested_rate_beside_the_judges_false_greens(tmp_path):
    """Why the judge gets a chip and never a badge, in one place: how often it
    contests at all, and how often it is wrong when it says `used`."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    j = compare.load_blind_judge()
    assert compare.CONTESTED_RATE in text
    assert str(j["falseGreen"]) in compare.contested_rate_line(j)


def test_the_scorecard_states_missed_compliance_against_the_pre_plan_baseline(tmp_path):
    """The criterion is a direction, so the number it is measured from has to
    be in the file. Printed whichever way it moved: a re-measurement that only
    prints an improvement is not a measurement."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    t = report["totals"]
    assert compare.MISSED_BASELINE_NOTE in text
    assert str(compare.PRE_PLAN_MISSED["all"]) in compare.MISSED_BASELINE_NOTE
    assert f"Missed compliance in the after column is {t['missedAfter']}" in text


def test_the_missed_compliance_line_names_the_direction_it_moved(tmp_path):
    """A re-measurement that prints two numbers and leaves the reader to
    subtract them is how an unchanged number gets quoted as an improvement.
    The direction is computed from the rows, so it cannot flatter them."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    missed = report["totals"]["missedAfter"]
    base = compare.PRE_PLAN_MISSED["all"]
    word = "unchanged" if missed == base else ("down" if missed < base else "up")
    assert compare.missed_direction(missed) == word
    assert word in text


def test_the_judge_row_says_whether_anything_can_falsify_it(tmp_path):
    """Replaces `..._says_nothing_can_falsify_it`, which pinned one answer.

    The guarantee it held is unchanged and is the one asserted here: a reader
    is told, in the file itself, whether the number beside the code tier's can
    be contradicted by anything in this repo. What changed is that the answer
    is now a property of the record - a record `blind_judge.py` wrote can be
    re-run, a transcript of a one-off cannot - so pinning the "nothing can"
    sentence would make a true file fail and keep a stale claim in a published
    one. Both branches are asserted, so neither can go missing.
    """
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    j = compare.load_blind_judge()
    expected = (compare.JUDGE_ROW_FALSIFIABLE if compare.reproducible(j)
                else compare.JUDGE_ROW_NOT_FALSIFIABLE)
    assert expected in text
    other = (compare.JUDGE_ROW_NOT_FALSIFIABLE if compare.reproducible(j)
             else compare.JUDGE_ROW_FALSIFIABLE)
    assert other not in text


def _blind(**over):
    """A minimal blind-judge record, harness-written unless told otherwise."""
    rec = {"source": "Generated by `python3 snapshots/blind_judge.py`.",
           "when": "2026-01-01", "model": "m", "blocks": 100, "sessions": 2,
           "calls": 10, "callsFailed": 0, "unanswered": 0,
           "agrees": 80, "falseGreen": 10, "falseRed": 5, "missed": 5,
           "codeAgrees": 70, "codeFalseGreen": 2, "codeFalseRed": 3,
           "codeMissed": 25, "bothRight": 60, "judgeOnly": 20, "codeOnly": 10,
           "neither": 10}
    rec.update(over)
    return rec


def test_the_four_way_split_states_the_false_red_comparison_it_measured():
    """The sentence may not assert a direction the numbers do not carry.

    It was written when the judge posted eleven false reds against the code
    tier's zero, and read as "the judge is worse in both directions". A
    re-measurement that puts the judge *below* the code tier on false reds
    leaves that phrasing describing the opposite of its own figures - and the
    one next to it, the false-green gap, is the claim the architecture actually
    rests on, so a reader who catches the contradiction discounts both.
    """
    for jr, cr, want in ((11, 0, "against the code tier's"),
                         (4, 4, "the same"),
                         (3, 4, "fewer false reds")):
        j = dict(_blind(), falseRed=jr, codeFalseRed=cr)
        line = " ".join(compare._four_way_lines(j))
        assert want in line, (jr, cr, line)


def test_the_false_green_gap_is_stated_whichever_way_the_reds_went():
    """The gap that licenses the chip has to survive the reds moving."""
    for jr, cr in ((11, 0), (3, 4)):
        j = dict(_blind(), falseGreen=21, codeFalseGreen=2,
                 falseRed=jr, codeFalseRed=cr)
        line = " ".join(compare._four_way_lines(j))
        assert "21 false greens against the code tier's 2" in line


def test_a_harness_written_record_is_reported_as_reproducible():
    """`reproducible` reads the record's own `source`, not the file's presence."""
    assert compare.reproducible({"source": "Generated by `python3 "
                                           "snapshots/blind_judge.py`."})
    assert not compare.reproducible({"source": "one-off agent run, no harness"})
    assert not compare.reproducible({})


def test_both_tier_rows_are_scored_over_the_same_blocks(tmp_path):
    """The pair of false-green counts is the whole argument for the chip, and a
    pair taken over two different block sets is not a pair.

    The record carries the code tier's counts over its own scored blocks for
    exactly this reason, so where the record is reproducible the table reads
    them from there rather than from the whole-corpus totals, which cover a few
    blocks the judge was never asked about.
    """
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    j = compare.load_blind_judge()
    if not compare.reproducible(j):
        pytest.skip("the committed record predates the harness")
    row = next(l for l in text.splitlines()
               if l.startswith("| compiled checks"))
    assert f"| {j['codeFalseGreen']} | {j['codeFalseRed']} | {j['codeMissed']} |" in row
    assert str(j["blocks"]) in row


def test_the_scorecard_never_claims_the_judge_row_describes_this_tree(tmp_path):
    """Replaces the sha256 pin and its stale path. The pin was taken when the
    row was published, not when the experiment ran, so the strongest thing it
    could support was "unchanged since I was written" while the sentence it
    rendered claimed "unchanged since the experiment" - a claim the repo holds
    no evidence for, about a file that has been edited since. The guarantee
    kept is the one that mattered: a reader is never told these numbers
    describe the tier in this tree."""
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report)).lower()
    for claim in ("byte-identical", "that experiment measured",
                  "still describes the tier"):
        assert claim not in text, claim


# ---------- the judge row is a recorded dataset, not a generator constant ----------

def _judge_record(**over):
    rec = {"when": "2020-01-02", "sessions": 5, "blocks": 10, "calls": 20,
           "callsFailed": 3, "falseGreen": 7, "falseRed": 1, "missed": 2,
           "agrees": 6, "codeAgrees": 5, "codeFalseGreen": 0, "codeFalseRed": 0,
           "codeMissed": 4, "bothRight": 4, "judgeOnly": 2, "codeOnly": 1,
           "neither": 3}
    rec.update(over)
    return rec


def _write_record(tmp_path, rec):
    path = tmp_path / "blind_judge.json"
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def test_the_judge_row_is_rendered_from_the_committed_record(tmp_path, monkeypatch):
    """The row's numbers must come from a dated record this repo holds, not
    from constants inside the generator. A generated file whose own header
    says "do not edit by hand" cannot be the place its numbers are written
    down: nothing then relates the published row to any artifact, so editing
    the record is the only way the row can be made to change."""
    rec = _judge_record()
    monkeypatch.setattr(compare, "BLIND_JUDGE_RECORD", _write_record(tmp_path, rec))
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert (f"| blind judge ({rec['when']}, {rec['blocks']} blocks) | "
            f"{rec['falseGreen']} | {rec['falseRed']} | {rec['missed']} |") in text
    assert "both right 4, judge right and code wrong 2" in text


def test_a_judge_record_whose_four_way_split_does_not_add_up_is_refused(tmp_path):
    """The split is the one thing in the record that can be checked here: its
    four cells have to sum to the block count and to each tier's agreement
    count. A transcription error that silently renders is a published number
    with nothing behind it."""
    path = _write_record(tmp_path, _judge_record(neither=99))
    with pytest.raises(ValueError) as e:
        compare.load_blind_judge(path)
    assert "neither" in str(e.value) or "blocks" in str(e.value)


def test_a_judge_record_that_contradicts_its_agreement_totals_is_refused(tmp_path):
    path = _write_record(tmp_path, _judge_record(agrees=99))
    with pytest.raises(ValueError):
        compare.load_blind_judge(path)


def test_without_the_record_the_scorecard_omits_the_judge_row_and_says_so(tmp_path,
                                                                          monkeypatch):
    """No record, no row. Printing the numbers anyway is what made them
    unfalsifiable in the first place."""
    monkeypatch.setattr(compare, "BLIND_JUDGE_RECORD", tmp_path / "absent.json")
    root = _authorised_files(tmp_path, "ignored", "ignored")
    report = compare.compare_all(root / "baseline", root / "after", root / "expected")
    text = "\n".join(compare.render(report))
    assert "| blind judge" not in text
    assert "no blind-judge record" in text.lower()


def test_the_committed_judge_record_loads_and_its_split_adds_up():
    rec = compare.load_blind_judge()
    assert rec is not None
    assert rec["bothRight"] + rec["judgeOnly"] + rec["codeOnly"] + rec["neither"] \
        == rec["blocks"]
