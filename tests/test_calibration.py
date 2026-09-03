"""Phase 13: the lexical tier's operating point is frozen and measured.

The tier is the only judging path with a tunable number in it, which makes it
the only one a plausible-looking edit can quietly make worse. Nothing else in
this repo can be loosened without a test going red; a threshold can, because
every threshold has a defensible-sounding story behind it.

So the numbers are pinned twice over: once in `lexical.py` where they are used
and once in the labelled set that justifies them, and this module fails if the
two disagree or if the measurement moves. The gate is **precision** - a false
`topical-overlap` claims engagement that never happened and reads exactly like
a real one, whereas a miss costs an honest `no-lexical-trace` whose own text
says a rule can be followed in silence. Recall is reported, never gated.

The labelling procedure, the provenance of each pair and why real pairs
reference the frozen baselines instead of copying session prose into `tests/`
are all in `tests/lexical_fixture.py`.
"""
from pathlib import Path

import pytest

import build_real_view as brv
import lexical
import rule_checks as rc

from tests import lexical_fixture as lf
from tests.test_turns import assistant_text, user_text


@pytest.fixture(scope="module")
def fixture():
    return lf.load()


@pytest.fixture(scope="module")
def metrics(fixture):
    return lf.evaluate(fixture)


# ---------- the set itself ----------

def test_the_calibration_corpus_is_present():
    """A missing corpus is a missing gate, so it fails here rather than later.

    196 of the 250 pairs reference the frozen baselines under
    `snapshots/baseline/`. Strip those and the precision gate goes on passing
    over the 32 inline pairs alone, which is a much easier set - so the absence
    is reported once, by name, instead of surfacing three tests later as a row
    count nobody can interpret.
    """
    assert lf.snapshots_available(), (
        f"{lf.SNAPSHOT_ROOT} is missing, so most of the calibration set cannot "
        "be scored and the precision gate is measuring the inline pairs only")


def test_the_fixture_is_well_formed(fixture):
    # The fixture declares the label set it was written against. If the scorer's
    # closed set drifts from it, a label goes on being written into pairs and
    # silently stops being counted.
    assert tuple(fixture["labels"]) == lf.LABELS
    seen = set()
    for pair in fixture["pairs"]:
        assert pair["label"] in lf.LABELS, pair
        assert pair["provenance"], pair
        assert pair.get("note"), f"{pair['id']} has no note saying how it was labelled"
        assert pair["id"] not in seen, pair["id"]
        seen.add(pair["id"])
        ref = pair["corpus"]
        if "inline" in ref:
            assert ref["inline"] in fixture["corpora"], pair["id"]
        else:
            assert "snapshot" in ref, pair["id"]


def test_every_pair_resolves_to_a_block_and_a_corpus(fixture):
    """A pair that cannot be resolved is a pair that silently stops counting.

    The snapshot half of the set names blocks by document and heading, so a
    re-captured baseline that renames a heading would otherwise drop those
    pairs out of the metric rather than failing.
    """
    for pair in fixture["pairs"]:
        if "content" not in pair["block"] and not lf.snapshots_available():
            continue
        assert lf.block_content(pair, fixture).strip(), pair["id"]
        corpus = lf.corpus_for(pair, fixture)
        assert corpus["q"]["segments"], pair["id"]


def test_the_set_is_big_enough_to_measure(fixture):
    assert len(fixture["pairs"]) >= 250
    labels = {}
    for pair in fixture["pairs"]:
        labels[pair["label"]] = labels.get(pair["label"], 0) + 1
    # Both truth-positive labels have to be represented or the recall figure is
    # about one kind of evidence only.
    assert labels.get("quoted", 0) >= 5, labels
    assert labels.get("topically-drawn-on", 0) >= 5, labels
    assert labels.get("coincidental", 0) >= 100, labels


# ---------- the gate ----------

def test_precision_on_the_labelled_set_holds_the_frozen_operating_point(fixture, metrics):
    point = fixture["operatingPoint"]
    assert metrics["precision"] is not None, (
        "the tier predicted no positive at all, so there is no precision to "
        "measure:\n" + lf.report(metrics))
    assert metrics["precision"] >= point["minPrecision"], lf.report(metrics)
    # A tier that answered `no-lexical-trace` to everything would post a
    # perfect precision on an empty numerator, so the gate needs a floor under
    # the numerator as well as over the ratio.
    assert metrics["truePositives"] >= point["minTruePositives"], lf.report(metrics)


def test_the_measured_figures_are_the_ones_the_fixture_records(fixture, metrics):
    """The fixture is the record of what was measured, so it has to still be true.

    Without this the `measured` block becomes a claim about a past state of the
    code, which is worse than no claim: a reader would trust it.
    """
    recorded = fixture["operatingPoint"]["measured"]
    for key in ("truePositives", "falsePositives", "falseNegatives", "scored"):
        assert metrics[key] == recorded[key], (key, lf.report(metrics))


def test_the_thresholds_in_the_code_are_the_ones_the_set_was_swept_at(fixture):
    """Moving a threshold without re-measuring is the failure mode this stops."""
    point = fixture["operatingPoint"]
    assert lexical.COVERAGE_FLOOR == point["coverageFloor"]
    assert lexical.RUN_TOKENS == point["runTokens"]
    assert lexical.RUN_CHARS == point["runChars"]
    assert lexical.G2_CRITICAL == point["g2Critical"]
    assert lexical.MIN_SIGNIFICANT == point["minSignificant"]
    assert lexical.MIN_TERMS == point["minTerms"]


def test_no_pair_the_run_never_saw_scores_positive(fixture, metrics):
    """§3.2's shuffled-pair check, as a standing assertion.

    A block scored against a session that never loaded its document, or one
    belonging to a skill the session never invoked, cannot have been drawn on.
    Anything positive there is a block generic enough to match anything, which
    is the failure the whole tier was rebuilt to remove - and it is worth
    asserting separately from the aggregate, because 196 easy pairs can absorb
    a single new false positive inside a rounded ratio.
    """
    for row in metrics["rows"]:
        if row["provenance"] in ("shuffled", "uninvoked-skill"):
            assert row["predicted"] not in lf.PREDICTED_POSITIVE, row


def test_precision_is_not_carried_by_the_easy_half(fixture, metrics):
    """The pairs read out of real transcripts have to clear the gate alone."""
    per = lf.by_provenance(metrics)
    inspected = per["inspection"]
    assert inspected["precision"] is not None, lf.report(inspected)
    assert inspected["precision"] >= fixture["operatingPoint"]["minPrecision"], (
        lf.report(inspected))


# ---------- the scorer ----------

def test_a_tier_that_answers_nothing_has_no_precision():
    rows = [{"id": "a", "label": "coincidental", "provenance": "x",
             "predicted": lexical.NO_TRACE, "result": {}, "note": ""}]
    assert lf.summarise(rows)["precision"] is None


def test_an_undecidable_pair_counts_in_neither_metric():
    rows = [{"id": "u", "label": "undecidable", "provenance": "x",
             "predicted": lexical.ECHOED, "result": {}, "note": ""}]
    metrics = lf.summarise(rows)
    assert metrics["scored"] == 0
    assert metrics["precision"] is None and metrics["recall"] is None


def test_a_false_positive_is_counted_as_one():
    rows = [{"id": "f", "label": "coincidental", "provenance": "x",
             "predicted": lexical.TOPICAL, "result": {}, "note": ""},
            {"id": "t", "label": "quoted", "provenance": "x",
             "predicted": lexical.ECHOED, "result": {}, "note": ""}]
    metrics = lf.summarise(rows)
    assert metrics["falsePositives"] == 1 and metrics["truePositives"] == 1
    assert metrics["precision"] == 0.5


# ---------- language neutrality ----------

POLISH_IDS = ("synthetic-polish-rules-00", "synthetic-polish-rules-01",
              "synthetic-polish-rules-04")


@pytest.fixture
def no_english_wordlist(monkeypatch):
    """The optional D2 background, gone.

    It is optional by design: a user whose rules are not in English gets no
    value from an English frequency list, and the tier has to work for them
    with D1 x D3 alone.
    """
    monkeypatch.setattr(lexical, "ZIPF_PATH", Path("/nonexistent/wordfreq-en.json"))
    lexical.english_zipf.cache_clear()
    lf.snapshot_corpus.cache_clear()
    lf._inline_corpus.cache_clear()
    yield
    lexical.english_zipf.cache_clear()
    lf.snapshot_corpus.cache_clear()
    lf._inline_corpus.cache_clear()


def test_the_english_wordlist_is_really_absent(no_english_wordlist):
    assert lexical.english_zipf() == {}


def test_a_polish_rule_derives_its_terms_from_its_own_corpus(fixture, no_english_wordlist):
    """No English word is load-bearing for a Polish rule's vocabulary."""
    pair = next(p for p in fixture["pairs"] if p["id"] == "synthetic-polish-rules-00")
    corpus = lf.corpus_for(pair, fixture)
    terms = lexical.block_terms(lf.block_content(pair, fixture), corpus["bg"])
    assert terms, "a Polish rule with no terms of its own is a tokenizer failure"
    words = {w for t in terms for w in t["term"].split(" ")}
    assert {"przekazuj", "usunac"} & words, sorted(words)
    # Every one of them is scored with no English rate available at all.
    assert all(t["zipf"] is None for t in terms), terms


def test_a_polish_rule_reaches_the_same_verdict_with_and_without_the_wordlist(
        fixture, monkeypatch):
    """For a document the list does not know, its absence must change nothing."""
    with_list = {}
    for pid in POLISH_IDS:
        pair = next(p for p in fixture["pairs"] if p["id"] == pid)
        with_list[pid] = lf.score_pair(pair, fixture)["label"]

    monkeypatch.setattr(lexical, "ZIPF_PATH", Path("/nonexistent/wordfreq-en.json"))
    lexical.english_zipf.cache_clear()
    lf._inline_corpus.cache_clear()
    try:
        for pid in POLISH_IDS:
            pair = next(p for p in fixture["pairs"] if p["id"] == pid)
            assert lf.score_pair(pair, fixture)["label"] == with_list[pid], pid
    finally:
        lexical.english_zipf.cache_clear()
        lf._inline_corpus.cache_clear()


def test_a_polish_rule_doc_reaches_honest_verdicts_without_the_wordlist(
        tmp_path, no_english_wordlist):
    """End to end, not just the label: no English word decides anything.

    `tests/fixtures/rules_pl.md` states real rules over real paths and
    commands, in Polish. With the frequency list gone as well, nothing English
    is left in the path at all - so if any block came out accused, or came out
    green on wording alone, an English assumption would still be load-bearing.
    """
    doc = tmp_path / "CLAUDE.md"
    doc.write_text((Path(__file__).parent / "fixtures" / "rules_pl.md").read_text(),
                   encoding="utf-8")
    rc.checks_for_doc.cache_clear()
    events = [user_text("policz pliki w katalogu", 1),
              assistant_text("Policzylem pliki: jest ich czterdziesci dwa.", 2)]
    trace = brv.build_trace(events, brv.tool_calls(events),
                            brv.assistant_text_segments(events),
                            "policz pliki w katalogu")
    file = {"loaded": True, "kind": "global", "path": str(doc),
            "abs_path": str(doc), "name": None}
    for block in brv.parse_claude_md(doc.read_text(encoding="utf-8")):
        v = brv.assess_block(block, file, trace)
        assert v["status"] != "ignored", (block["title"], v["reason"])
        assert v.get("evidenceLabel") in (None,) + lexical.LABELS, v
        if v.get("evidenceLabel"):
            assert v["evidenceLabel"] not in ("echoed", "topical-overlap"), (
                block["title"], v["lexical"])


def test_a_polish_rule_is_labelled_honestly_without_the_wordlist(fixture,
                                                                 no_english_wordlist):
    """Honest means: the quotation is seen, and the unrelated rules are not."""
    labels = {}
    for pid in POLISH_IDS:
        pair = next(p for p in fixture["pairs"] if p["id"] == pid)
        labels[pid] = lf.score_pair(pair, fixture)["label"]
    assert labels["synthetic-polish-rules-00"] == lexical.ECHOED, labels
    for pid in POLISH_IDS[1:]:
        assert labels[pid] not in lf.PREDICTED_POSITIVE, labels


# ---------- the contribution path ----------

def test_the_labelling_tool_stays_local_only():
    """The label workflow is not allowed to be the exception to the no-network rule.

    A calibration set is only worth having if other people's rule documents get
    into it, and the obvious way to collect those is a server. There is none:
    the tool reads local transcripts, writes one file, and stops.
    """
    src = (Path(__file__).resolve().parent / "label_pairs.py").read_text()
    for reach in ("urllib", "http.client", "socket", "requests"):
        assert reach not in src, f"the labelling tool reaches for {reach}"


def test_a_contributed_file_is_scorable_by_the_same_scorer():
    """A contribution is the same shape as the committed set, or it is dead weight.

    The pairs carry their corpus inline, so a reviewer scores them without ever
    seeing the contributor's transcripts - and the scorer has to accept them
    unchanged, or reviewing one means hand-editing it first.
    """
    from tests import label_pairs

    contributed = {
        "version": 1,
        "corpora": {"c1": {
            "documents": ["Never pipe echo into pbcopy; use printf so the trailing "
                          "newline the terminal appends is stripped.",
                          "Every migration ships with a rollback script."],
            "segments": ["I switched the clipboard helper to printf so the trailing "
                         "newline the terminal appends is stripped.",
                         "No migration in this change."],
        }},
        "pairs": [{"id": "c1-000", "label": "quoted", "provenance": "contributed",
                   "note": "The reply reuses the rule's own wording.",
                   "block": {"content": "Never pipe echo into pbcopy; use printf so the "
                                        "trailing newline the terminal appends is "
                                        "stripped."},
                   "corpus": {"inline": "c1"}}],
    }
    metrics = lf.evaluate(contributed)
    assert metrics["scored"] == 1
    assert metrics["rows"][0]["predicted"] in lexical.LABELS
    # And an unlabelled pair is refused rather than counted as anything.
    contributed["pairs"][0]["label"] = label_pairs.LABEL_TODO
    assert lf.evaluate(contributed)["scored"] == 0


def test_an_unlabelled_pair_never_counts_toward_the_gate():
    rows = [{"id": "t", "label": "TODO", "provenance": "contributed",
             "predicted": lexical.TOPICAL, "result": {}, "note": ""}]
    metrics = lf.summarise(rows)
    assert metrics["scored"] == 0
    assert metrics["falsePositives"] == 0


def test_a_harvested_pair_rescores_to_the_label_its_note_claims(tmp_path, monkeypatch):
    """The note and the reviewer's own run have to agree, or neither is evidence.

    Each note tells the labeller what the tier currently says about the pair,
    and a reviewer re-scores it from the inline corpus. The emitted corpus is
    truncated per block and capped in segments, so it is not the background the
    harvesting session itself was judged against - which is why the harvester
    builds the corpus first and scores against *that*. Score against the live
    background and the two numbers can differ, with nothing in the file saying
    which one to believe.
    """
    from tests import label_pairs
    from tests.test_turns import _write_jsonl

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text(
        "# Rules\n\n## Clipboard\n\n"
        "Never pipe `echo` into `pbcopy`; use `printf` so the trailing newline "
        "the terminal appends is stripped before the clipboard sees it.\n\n"
        "## Migrations\n\n"
        "Every migration ships with a rollback script, or it does not pass "
        "review, because a migration nobody can undo is a decision nobody can "
        "revisit.\n")
    monkeypatch.setenv("HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    events = [user_text("copy the summary", 1),
              assistant_text("Piped it through `printf` so the trailing newline the "
                             "terminal appends is stripped before the clipboard sees "
                             "it.", 2),
              assistant_text("No migration in this change, so nothing to roll back.", 3)]
    transcript = _write_jsonl(tmp_path, events)
    monkeypatch.setattr(brv, "discover_all_transcripts", lambda cwd: [transcript])

    out = label_pairs.harvest(limit=10)
    assert out["pairs"], "nothing harvested, so the round trip proves nothing"
    for pair in out["pairs"]:
        claimed = pair["note"].split("scores this ")[1].split(" (")[0]
        assert lf.score_pair(pair, out)["label"] == claimed, pair["id"]
