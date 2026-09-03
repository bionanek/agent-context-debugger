"""The lexical tier: term weighting, the significance gate, the quote detector.

The anchor that started this work is `test_tech_stack_table_is_not_lexically_scorable`:
a table of column headers and stack names scored 5/8 keyword hits against an
unrelated discussion of the Effect library. It must come out
`not-lexically-scorable`, because the honest answer for a table is that there
is nothing there to score.
"""
import pathlib

import pytest

import build_real_view as brv
import lexical

from tests.test_turns import assistant_text, user_text, _ts


def bg_from(blocks, segments):
    """A background over one synthetic document plus the session's own prose."""
    files = [{"abs_path": "/doc.md",
              "blocks": [{"title": f"b{i}", "content": c} for i, c in enumerate(blocks)]}]
    return lexical.build_background(files, segments)


# ---------- D1 x D2 x D3 term weighting ----------

def test_a_term_ambient_in_the_session_weights_zero():
    """D3: the project's own vocabulary is not the block's."""
    block = "Telemetry ownership belongs to the platform squad, paged via grafana."
    ambient = [f"Wired the telemetry exporter for service {i}." for i in range(10)]
    bg = bg_from([block], ambient)
    terms = [t["term"] for t in lexical.block_terms(block, bg)]
    assert "telemetry" not in terms
    # A word the session never says survives the same weighting.
    assert "grafana" in terms


def test_everyday_english_weights_zero():
    """D2: zipf >= 5 is what any English sentence contains."""
    zipf = lexical.english_zipf()
    assert zipf, "the baked frequency list should ship with the repo"
    assert zipf["always"] >= 5.0 and zipf["never"] >= 5.0
    bg = bg_from(["Always remember never to change something before."], [])
    terms = [t["term"] for t in lexical.block_terms(
        "Always remember never to change something before.", bg)]
    assert "always" not in terms
    assert "never" not in terms


def test_a_thin_collection_never_pushes_a_block_to_unscorable():
    """Each background stands down when it has no sample to speak from.

    D1 over a handful of blocks puts every term in "most" of them and IDF
    crushes the lot; D3 over three assistant segments calls any shared term
    ambient. Either one, applied to a sample that small, would zero a block's
    whole vocabulary - an optional background making the label worse.
    """
    block = ("Always pipe clipboard content through printf so terminal-injected "
             "trailing whitespace is stripped before pbcopy sees it.")
    prose = ["I piped it through printf before pbcopy."]
    bg = bg_from([block], prose)
    assert bg["blocks"] < lexical.MIN_COLLECTION
    assert bg["segments"] < lexical.MIN_AMBIENT_SEGMENTS
    terms = [t["term"] for t in lexical.block_terms(block, bg)]
    assert "printf" in terms and "pbcopy" in terms
    assert lexical.score(block, bg, lexical.query_stats(prose))["label"] != lexical.UNSCORABLE


def test_a_missing_english_list_falls_back_to_d1_by_d3(monkeypatch):
    """An optional signal degrades to unavailable, never to a worse label."""
    monkeypatch.setattr(lexical, "ZIPF_PATH", "/nonexistent/wordfreq.json")
    lexical.english_zipf.cache_clear()
    try:
        assert lexical.english_zipf() == {}
        bg = bg_from(["Always remember never to change something."], [])
        terms = [t["term"] for t in lexical.block_terms(
            "Always remember never to change something.", bg)]
        # Without D2 the everyday words survive - that is the honest
        # degradation: fewer terms are excluded, none is invented.
        assert "always" in terms
    finally:
        lexical.english_zipf.cache_clear()


TECH_STACK_TABLE = """| Layer | Choice | Notes |
| --- | --- | --- |
| Framework | React Native (Expo) | managed workflow |
| Language | TypeScript | strict mode |
| State | Zustand | |
| Navigation | Expo Router | |
"""

EFFECT_DISCUSSION = (
    "I looked at whether to keep react-query here or move the whole data layer "
    "to Effect. Effect gives us typed errors and a real dependency graph, but "
    "react-query already owns the cache invalidation and every screen in this "
    "React Native app is written against its hooks. The TypeScript ergonomics "
    "of Effect are better; the migration cost is not worth it this sprint."
)


# A React Native session says "React Native", "TypeScript", "Expo" and
# "Zustand" constantly - that is what makes them the project's vocabulary
# rather than the table's.
STACK_SESSION = [
    EFFECT_DISCUSSION,
    "Rewrote the React Native list screen in TypeScript.",
    "The React Native navigation stack now goes through Expo Router.",
    "Checked the TypeScript types across the React Native app.",
    "Moved the filter state into the Zustand store instead of Expo Router params.",
    "The Zustand slice is persisted, so the Expo reload keeps the TypeScript shape.",
    "Ran the React Native bundler again after the TypeScript change.",
    "Expo Router needs the Zustand provider above the React Native navigator.",
    "TypeScript flagged the Zustand selector, so the React Native screen now narrows it.",
]


def test_tech_stack_table_is_not_lexically_scorable():
    """The anchor: a stack table has no vocabulary of its own to score.

    Its terms are the project's ambient vocabulary (React, Native, TypeScript,
    Expo, Zustand in a React Native repo) plus table furniture (Layer, Choice,
    Notes). Under the old first-eight-words rule it scored 5 of 8 against a
    discussion of the Effect library that had nothing to do with it.
    """
    bg = bg_from([TECH_STACK_TABLE], STACK_SESSION)
    q = lexical.query_stats([EFFECT_DISCUSSION])
    result = lexical.score(TECH_STACK_TABLE, bg, q)
    assert result["label"] == lexical.UNSCORABLE
    assert len(result["terms"]) < lexical.MIN_TERMS


def test_fewer_than_three_terms_is_unscorable_not_unused():
    """The reason must not read as a claim about the block being ignored."""
    bg = bg_from(["Notes"], ["some prose about other things entirely"])
    result = lexical.score("Notes", bg, lexical.query_stats(["unrelated prose"]))
    assert result["label"] == lexical.UNSCORABLE
    assert "followed" in result["reason"]


# ---------- G^2 significance and the three-condition gate ----------

def test_g2_needs_two_observations():
    """One occurrence of a rare word is not a pattern."""
    block = "Zustand hydration guards the persisted slice against schema drift."
    once = "We touched the zustand hydration path."
    bg = bg_from([block], [once])
    result = lexical.score(block, bg, lexical.query_stats([once]))
    assert result["significant"] == []
    assert result["label"] == lexical.NO_TRACE


def test_topical_needs_all_three_conditions():
    """Each condition alone is satisfiable by coincidence, so all three hold."""
    block = ("Hydration guards protect the persisted zustand slice. Rehydrate "
             "the slice through the migration shim, never directly.")
    prose = ("I added the hydration guard around the persisted zustand slice, "
             "then ran the migration shim so rehydrate goes through it. The "
             "hydration path now rejects a stale persisted slice, and the "
             "migration shim reports what it dropped.")
    bg = bg_from([block], [prose])
    result = lexical.score(block, bg, lexical.query_stats([prose]))
    assert result["label"] == lexical.TOPICAL
    assert len(result["significant"]) >= lexical.MIN_SIGNIFICANT
    assert result["coverage"] >= lexical.COVERAGE_FLOOR


def test_an_unrelated_session_scores_no_trace():
    """The shuffled-pair check: a block against another session's prose."""
    block = ("Hydration guards protect the persisted zustand slice. Rehydrate "
             "the slice through the migration shim, never directly.")
    other = ("I rewrote the invoice reconciliation job so it batches by ledger "
             "period and retries the failed postings against the accrual table.")
    bg = bg_from([block], [other])
    result = lexical.score(block, bg, lexical.query_stats([other]))
    assert result["label"] == lexical.NO_TRACE
    assert "silence" in result["reason"]


# ---------- quote detector ----------

def test_a_verbatim_run_with_a_distinctive_term_is_echoed():
    block = ("Always pipe clipboard content through printf so terminal-injected "
             "trailing whitespace is stripped before pbcopy sees it.")
    prose = ("I set it up so we pipe clipboard content through printf so "
             "terminal-injected trailing whitespace is stripped, which is what "
             "the guideline asks for.")
    bg = bg_from([block], [prose])
    result = lexical.score(block, bg, lexical.query_stats([prose]))
    assert result["label"] == lexical.ECHOED
    assert result["quote"]["kind"] == lexical.ECHOED
    assert result["quote"]["tokens"] >= lexical.RUN_TOKENS


def test_a_generic_function_word_run_is_not_a_quote():
    """The longest common run between any two English passages is filler."""
    block = ("It is one of the things that you would have to do in order to be "
             "able to get the results that we want from this.")
    prose = ("It is one of the things that you would have to do in order to be "
             "able to ship the migration on time.")
    bg = bg_from([block], [prose])
    result = lexical.score(block, bg, lexical.query_stats([prose]))
    assert result["label"] != lexical.ECHOED


def test_the_quote_detector_disables_autojunk():
    """difflib's default discards the frequent words a quoted sentence needs."""
    src = pathlib.Path(lexical.__file__).read_text(encoding="utf-8")
    assert "autojunk=False" in src
    assert "SequenceMatcher(None," in src


# ---------- query text ----------

def test_a_blocks_code_spans_are_stripped_like_the_querys_are():
    """Both sides must mean the same thing by "a token".

    The gh-account rule's whole vocabulary is backticked account and repo
    names. Kept on the block side and stripped on the query side, its terms
    could never match anything and the block was guaranteed `no-lexical-trace`
    - which reads as a finding when it is an artefact.
    """
    block = ("Before running any `gh` command, check the active account with "
             "`gh auth status` and switch to `bionanek-x` if needed.")
    bg = bg_from([block], [])
    terms = {t["term"] for t in lexical.block_terms(block, bg)}
    assert not {t for t in terms if "bionanek" in t or "auth" in t}


def test_terms_are_unicode_letters_not_ascii():
    """A rule document in another language is scored, not silently emptied."""
    block = "Zawsze uruchamiaj testy jednostkowe przed wysłaniem gałęzi do przeglądu."
    bg = bg_from([block], [])
    terms = {t["term"] for t in lexical.block_terms(block, bg)}
    assert "jednostkowe" in terms
    assert "wysłaniem" in terms


def test_query_text_drops_fenced_code_and_inline_code():
    text = "Here is the fix:\n\n```python\nzustand hydration shim rehydrate\n```\n\nDone with `zustand hydration`."
    cleaned = lexical.clean_query_segments([text])
    joined = " ".join(cleaned)
    assert "rehydrate" not in joined
    assert "zustand" not in joined
    assert "Here is the fix" in joined


def test_query_text_drops_lines_copied_out_of_a_read_file():
    """A read file's content in the query makes every block of it self-match."""
    line = "Never import another store's singleton from a sibling feature module."
    cleaned = lexical.clean_query_segments(
        ["As the guide says:\n" + line + "\nSo I moved the import."],
        copied=["...file body...\n" + line + "\n...more..."])
    joined = " ".join(cleaned)
    assert line not in joined
    assert "So I moved the import." in joined


def test_tool_inputs_and_results_never_reach_the_trace_query():
    """build_trace's query comes off assistant text segments only."""
    events = [
        user_text("do the thing", 1),
        {"type": "assistant", "timestamp": _ts(2),
         "message": {"content": [
             {"type": "text", "text": "Running it."},
             {"type": "tool_use", "name": "Bash", "id": "t1",
              "input": {"command": "grep zustandhydrationtoken ."}}]}},
        {"type": "user", "timestamp": _ts(3),
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                  "content": "zustandhydrationtoken found"}]}},
    ]
    calls = brv.tool_calls(events)
    trace = brv.build_trace(events, calls, brv.assistant_text_segments(events), "do the thing")
    joined = " ".join(trace["query_segments"])
    assert "zustandhydrationtoken" not in joined
    assert "Running it." in joined


# ---------- taxonomy wiring ----------

def _score_one(block_content, prose, doc="/Users/dev/proj/CLAUDE.md"):
    paragraphs = [prose] if isinstance(prose, str) else list(prose)
    events = [user_text("go", 1)]
    events += [assistant_text(p, i + 2) for i, p in enumerate(paragraphs)]
    calls = brv.tool_calls(events)
    trace = brv.build_trace(events, calls, brv.assistant_text_segments(events), "go")
    file = {"path": doc, "abs_path": doc, "kind": "project", "loaded": True,
            "name": None, "blocks": []}
    block = {"title": "Guideline", "content": block_content, "level": 2, "kind": "rule"}
    file["blocks"] = [block]
    trace["lexical_bg"] = lexical.build_background([file], trace["query_segments"])
    return brv.assess_block(block, file, trace)


def test_assess_block_bakes_the_evidence_label():
    v = _score_one("Hydration guards protect the persisted zustand slice. "
                   "Rehydrate the slice through the migration shim, never directly.",
                   "I rewrote the invoice reconciliation job for the accrual ledger.")
    assert v["evidenceLabel"] == lexical.NO_TRACE
    assert v["lexical"]["label"] == lexical.NO_TRACE
    assert v["status"] == "unused"


def test_lexical_evidence_never_reaches_a_hard_verdict():
    """Even a verbatim quote caps at possibly-referenced."""
    block = ("Always pipe clipboard content through printf so terminal-injected "
             "trailing whitespace is stripped before pbcopy sees it.")
    v = _score_one(block,
                   "I made it pipe clipboard content through printf so "
                   "terminal-injected trailing whitespace is stripped.")
    assert v["evidenceLabel"] == lexical.ECHOED
    assert v["status"] == "possibly-referenced"


def test_the_badge_and_the_card_read_one_result():
    """One question, one matcher: the moment card quotes the baked record."""
    v = _score_one("Hydration guards protect the persisted zustand slice. "
                   "Rehydrate the slice through the migration shim, never directly.",
                   "I rewrote the invoice reconciliation job for the accrual ledger.")
    kinds = {m["kind"] for m in v["moments"]}
    assert kinds == {"non-event"}
    assert v["lexical"]["reason"] in " ".join(m["text"] for m in v["moments"])


def test_an_unscorable_block_says_so_rather_than_claiming_disuse():
    v = _score_one(TECH_STACK_TABLE, STACK_SESSION)
    assert v["evidenceLabel"] == lexical.UNSCORABLE
    assert "too few to score" in v["reason"]


def test_the_cli_prints_the_same_label_the_page_shows():
    """The chip and the `lexical` line read one baked field."""
    block = {"id": "b1", "title": "Guideline", "type": "rule", "level": 2,
             "content": "body", "status": "unused", "reason": "nothing",
             "evidence": [], "moments": [],
             "evidenceLabel": lexical.NO_TRACE,
             "lexical": {"label": lexical.NO_TRACE, "terms": ["rehydrate"],
                         "coverage": 0.04, "significant": [], "quote": None,
                         "reason": "nothing"}}
    session = {"contextFiles": [{"id": "f1", "path": "CLAUDE.md", "loaded": True,
                                 "blocks": [block]}], "turns": []}
    out = "\n".join(brv.query_block("sid", session, "b1"))
    assert "lexical  no-lexical-trace" in out
    assert "rehydrate" in out


# ---------- shuffled sessions ----------

UNRELATED_SESSIONS = [
    ["I rewrote the invoice reconciliation job so it batches by ledger period.",
     "The accrual table now carries the posting date, so retries are idempotent.",
     "Reconciliation runs nightly and writes a ledger digest for the finance team."],
    ["Tuned the kerning on the marketing headline and swapped the hero photograph.",
     "The print bleed was wrong, so the brochure margins moved by three millimetres.",
     "Sent the revised brochure to the printer with the new pantone swatch."],
    ["Traced a memory leak in the audio ring buffer to a missing free on the error path.",
     "The ring buffer now recycles its frames, and the profiler shows a flat heap.",
     "Added a soak test that plays sixty minutes of tone through the buffer."],
]

SHUFFLE_BLOCKS = [
    "Hydration guards protect the persisted zustand slice. Rehydrate the slice "
    "through the migration shim, never directly.",
    "Always pipe clipboard content through printf so terminal-injected trailing "
    "whitespace is stripped before pbcopy sees it.",
    TECH_STACK_TABLE,
    "Every pull request must name the jira ticket in its branch prefix and run "
    "the storybook snapshot suite before review.",
]


def test_no_block_scores_topical_against_an_unrelated_session():
    """The coincidence check: shared subject matter has to be shared.

    Anything above threshold here is a block generic enough to match anything,
    which is the failure the whole tier was rebuilt to stop.
    """
    for prose in UNRELATED_SESSIONS:
        bg = bg_from(SHUFFLE_BLOCKS, prose)
        q = lexical.query_stats(prose)
        for content in SHUFFLE_BLOCKS:
            result = lexical.score(content, bg, q)
            assert result["label"] in (lexical.NO_TRACE, lexical.UNSCORABLE), (
                content[:40], prose[0][:40], result)


def test_the_labels_are_a_closed_set():
    assert set(lexical.LABELS) == {"echoed", "topical-overlap",
                                   "no-lexical-trace", "not-lexically-scorable"}
