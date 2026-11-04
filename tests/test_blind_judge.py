"""The blind-judge harness: the one thing that can falsify the scorecard's judge row.

The row this scores used to be a transcript of a one-off run with no harness
behind it, so a change that made the judge worse left the published numbers
untouched. Everything here is the offline half - prompt construction, answer
parsing and scoring - because that is the half a test can hold. The model calls
are injected, so the suite never reaches a backend.

The scoring reads `compare.error_kind`, deliberately: a judge scored by a second
implementation of the truth classes would be measured against a different answer
key than the code tier printed beside it, and the pair of counts is the whole
argument.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "snapshots"))

import blind_judge as bj  # noqa: E402


def _block(bid, title="A rule", status=None):
    b = {"id": bid, "doc": "~/.claude/CLAUDE.md", "kind": "global",
         "title": title, "content": "Always run the tests before saying done."}
    if status is not None:
        b["status"] = status
    return b


def _views():
    return {"actions": "1 Bash `pytest`\n2 Write `src/a.py`",
            "joins": "block-1\tA rule\tran pytest",
            "rulings": "4. An invocation credits the identity block alone."}


# ---------- the prompt is blind ----------

def test_the_prompt_is_identical_whether_or_not_the_block_carries_a_verdict():
    """The withholding guarantee, asserted rather than trusted.

    A judge handed the tool's own status is not measuring anything: it is being
    asked to agree. The payload records a status on every block, so the harness
    reads block identity out of the same dicts - and the only thing stopping a
    status riding along is that nothing in the prompt builder reads the key.
    Comparing the two prompts is what makes that a property rather than a habit.
    """
    v = _views()
    bare = bj.prompt_for("famigo/9dd3cc8a", blocks=[_block("block-1")], **v)
    tainted = bj.prompt_for("famigo/9dd3cc8a",
                            blocks=[_block("block-1", status="used")], **v)
    assert bare == tainted
    # The word `status` legitimately appears in the answer instructions, so the
    # narrow claim is about the block's own section: the evidence the judge
    # reads must carry identity and text and nothing the tool concluded.
    section = bj._block_section([_block("block-1", status="used")])
    assert "status" not in section.lower()
    assert "used" not in section.lower()


def test_the_prompt_carries_every_block_it_asks_about():
    v = _views()
    p = bj.prompt_for("s", blocks=[_block("block-1"), _block("block-2", "Another")], **v)
    assert "block-1" in p and "block-2" in p
    assert "Another" in p


# ---------- the answer is a closed set ----------

def test_an_answer_outside_the_closed_set_is_dropped():
    """A fluent word that is not a status is not an answer.

    `compliant` is what the compiled tier's judge says, and coercing it to
    `used` here would silently score one question's vocabulary against another's.
    """
    text = "block-1: used\nblock-2: compliant\nblock-3: dormant"
    got = bj.parse_answers(text, ["block-1", "block-2", "block-3"])
    assert got == {"block-1": "used", "block-3": "dormant"}


def test_an_answer_about_a_block_that_was_not_asked_is_dropped():
    got = bj.parse_answers("block-1: used\nblock-9: used", ["block-1"])
    assert got == {"block-1": "used"}


def test_every_closed_set_answer_is_a_status_the_code_tier_can_also_give():
    """The two tiers answer in one vocabulary or their counts are not comparable."""
    import build_real_view as brv
    assert set(bj.STATUSES) == set(brv.COMBINED_TALLY_ORDER)


# ---------- scoring ----------

def test_the_four_way_split_counts_each_corner():
    truths = {"a": "used", "b": "used", "c": "no-hard-verdict", "d": "used"}
    judge = {"a": "used", "b": "used", "c": "used", "d": "unused"}
    code = {"a": "used", "b": "unused", "c": "unused", "d": "unused"}
    s = bj.score(truths, judge, code)
    assert (s["bothRight"], s["judgeOnly"], s["codeOnly"], s["neither"]) == (1, 1, 1, 1)
    assert s["agrees"] == 2
    assert s["codeAgrees"] == 2


def test_a_green_over_an_authorised_truth_is_a_false_green_for_either_tier():
    truths = {"a": "authorised"}
    s = bj.score(truths, {"a": "used"}, {"a": "unused"})
    assert s["falseGreen"] == 1 and s["codeFalseGreen"] == 0


def test_a_red_over_a_used_truth_is_a_false_red_for_either_tier():
    truths = {"a": "used"}
    s = bj.score(truths, {"a": "ignored"}, {"a": "ignored"})
    assert s["falseRed"] == 1 and s["codeFalseRed"] == 1


def test_a_not_used_status_over_a_used_truth_is_missed_compliance():
    truths = {"a": "used"}
    s = bj.score(truths, {"a": "unused"}, {"a": "used"})
    assert s["missed"] == 1 and s["codeMissed"] == 0


def test_an_undecidable_truth_is_not_scored_at_all():
    truths = {"a": "undecidable", "b": "used"}
    s = bj.score(truths, {"a": "used", "b": "used"}, {"a": "used", "b": "used"})
    assert s["blocks"] == 1


def test_a_block_the_judge_never_answered_is_not_scored_as_agreement():
    """An unanswered block is missing data, not a correct answer.

    111 of the original run's 532 calls failed and took three whole sessions
    out of the scored set. Counting those blocks as agreement would have turned
    a broken harness into the judge's best result.
    """
    truths = {"a": "used", "b": "used"}
    s = bj.score(truths, {"a": "used"}, {"a": "used", "b": "used"})
    assert s["blocks"] == 1
    assert s["unanswered"] == 1
    assert s["agrees"] == 1


# ---------- the run ----------

def _fake_corpus(tmp_path):
    """One session's truths, views and code statuses, with no snapshot on disk."""
    return {
        "session": "demo/1234abcd",
        "truths": {"block-1": "used", "block-2": "no-hard-verdict"},
        "code": {"block-1": "used", "block-2": "used"},
        "blocks": [_block("block-1"), _block("block-2", "Another")],
        **_views(),
    }


def test_measure_counts_a_failed_call_rather_than_dropping_it(tmp_path):
    calls = []

    def invoke(prompt, model):
        calls.append(prompt)
        return None  # the backend was unreachable

    rec = bj.measure([_fake_corpus(tmp_path)], invoke=invoke, model="m", chunk=2)
    assert rec["calls"] == 1 and rec["callsFailed"] == 1
    assert rec["blocks"] == 0 and rec["unanswered"] == 2


def test_measure_scores_the_answers_it_got(tmp_path):
    def invoke(prompt, model):
        return "block-1: used\nblock-2: used"

    rec = bj.measure([_fake_corpus(tmp_path)], invoke=invoke, model="m", chunk=2)
    assert rec["calls"] == 1 and rec["callsFailed"] == 0
    assert rec["blocks"] == 2
    assert rec["agrees"] == 1          # block-2 green over no-hard-verdict
    assert rec["falseGreen"] == 1
    assert rec["codeFalseGreen"] == 1  # the code tier said the same there
    assert rec["sessions"] == 1


def test_the_record_names_the_protocol_the_model_and_the_date(tmp_path):
    """A number nobody can place is the thing this harness replaces.

    The row is printed beside the code tier's, so the reader has to be able to
    see which judge, asked how, produced it - and `source` has to say that this
    harness, not a one-off transcript, is where it came from.
    """
    rec = bj.measure([_fake_corpus(tmp_path)],
                     invoke=lambda p, m: "block-1: used\nblock-2: dormant",
                     model="claude-test-1", chunk=2)
    assert rec["model"] == "claude-test-1"
    assert rec["chunk"] == 2
    assert "blind_judge.py" in rec["source"]
    assert rec["when"]
    # Every field compare.py renders has to be present, or the scorecard breaks
    # on a record this harness wrote.
    import compare
    assert set(compare.BLIND_JUDGE_FIELDS) <= set(rec)


def test_the_written_record_round_trips_through_the_scorecard_loader(tmp_path):
    import compare
    rec = bj.measure([_fake_corpus(tmp_path)],
                     invoke=lambda p, m: "block-1: used\nblock-2: dormant",
                     model="m", chunk=2)
    path = tmp_path / "blind_judge.json"
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    assert compare.load_blind_judge(path)["blocks"] == 2
