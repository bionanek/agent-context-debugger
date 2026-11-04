"""The labelled calibration set for the lexical tier, and the scorer over it.

The lexical tier is the only judging path with a tunable threshold, so it is
the only one that can be made quietly worse by a plausible-looking edit. This
module is the guard: a frozen set of (block, session) pairs with a hand-checked
label each, plus the metric the suite gates on.

**Precision-first, deliberately.** A false `topical-overlap` claims the run
engaged with a rule it never touched, and the reader has no way to tell it from
a real one. A miss costs an honest `no-lexical-trace`, which says out loud that
a rule can be followed in silence. So the gate is precision, and recall falls
where it does - which on this set is roughly half, because the audit's own
anchors include compliance that happened entirely in file writes and left no
trace in the prose at all. Those pairs are in the set as positives on purpose:
they are the shape of miss the tier is expected to make, and the structural
predicates rather than the vocabulary are what catch them.

**Where the pairs come from.** Real pairs reference the Phase 0 frozen
baselines under `snapshots/baseline/` rather than copying session prose into
`tests/`: a second copy of a real transcript is a second thing to sanitise and
a second thing to keep in step. Contributed pairs carry their corpus inline
instead (see `tests/label_pairs.py`), which is what makes them shareable.

Those baselines are the author's own sessions and are gitignored, so a clone
does not have them: `resolvable` says which pairs survive their absence, and
the tests that need the full set skip by name rather than quietly measuring
the inline third.

**Ground truth, and how each label was arrived at**, since a calibration set is
worthless if nobody can tell how it was labelled:

  `quoted`              the run reproduced the block's wording
  `topically-drawn-on`  the run demonstrably engaged with the block's subject,
                        whether or not it reused any wording
  `coincidental`        the run did not draw on the block; any overlap is chance
  `undecidable`         no defensible ground truth exists for this pair -
                        excluded from every metric, kept so the reason is on
                        the record

`provenance` says which of those judgements is an inspection and which is a
construction, and the scorer reports the metrics per provenance so a headline
number cannot be carried by the easy half:

  `inspection`      read out of the frozen transcript by hand (the §7 audit
                    anchors and every pair the tier currently calls positive)
  `shuffled`        a block from a document the target session never loaded;
                    `coincidental` by construction, since a run cannot draw on
                    a file it never had - §3.2's shuffled-pair check
  `uninvoked-skill` a skill listed for the session but never invoked (checked
                    with the tool's own `_trigger_evidence`), so its
                    instructions were not followed
  `synthetic`       written by hand to exercise one label, with its corpus
                    inline; also the worked example of the contribution format
  `contributed`     somebody else's pairs, produced by `tests/label_pairs.py`
                    and labelled by them; inline for the same reason
"""
import functools
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lexical                                                     # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "lexical_pairs.json"
SNAPSHOT_ROOT = REPO / "snapshots" / "baseline"

LABELS = ("quoted", "topically-drawn-on", "coincidental", "undecidable")
# The two labels that assert the run drew on the block. The tier's own two
# positive labels are `echoed` and `topical-overlap`; it never claims to know
# which of the two truths it is looking at, so both fold together here.
TRUTH_POSITIVE = ("quoted", "topically-drawn-on")
PREDICTED_POSITIVE = (lexical.ECHOED, lexical.TOPICAL)


def load(path=FIXTURE):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def snapshots_available():
    return SNAPSHOT_ROOT.is_dir()


CORPUS_ABSENT = (
    f"the frozen calibration corpus at {SNAPSHOT_ROOT} is absent. It is the "
    "author's own sessions and is deliberately not distributable, so a clone "
    "scores the inline pairs only")


# ---------- corpora ----------

def _read_input(sdir, inp):
    raw = (sdir / "inputs" / inp["stored"]).read_bytes()
    if inp.get("gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


@functools.lru_cache(maxsize=None)
def snapshot_corpus(session):
    """The background and query stats for one frozen session.

    Built from the frozen inputs through the tool's own helpers - not from the
    baked payload, which predates the lexical tier. `build_real_view` is
    imported here rather than at module scope so a contributor with no
    snapshots can still load the fixture and score its inline pairs.

    The returned background carries `lexical.block_terms`'s own term cache, so
    a test that changes a weighting constant or hides the English list MUST
    `snapshot_corpus.cache_clear()` (and `_inline_corpus.cache_clear()`) first.
    Without it the terms come back weighted the old way and the test measures
    the state it was trying to change.
    """
    import build_real_view as brv

    sdir = SNAPSHOT_ROOT / session
    manifest = json.loads((sdir / "manifest.json").read_text())
    by_key = {i["key"]: i for i in manifest["inputs"]}
    events = []
    for line in _read_input(sdir, by_key[manifest["transcriptKey"]]).splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
    segments = lexical.clean_query_segments(
        [s["text"] for s in brv.assistant_text_segments(events)],
        copied=[s["text"] for s in brv.chronological_segments(events)
                if s["kind"] == "tool_result"])
    files = []
    for key, inp in by_key.items():
        if not key.endswith(".md"):
            continue
        blocks = brv.parse_claude_md(_read_input(sdir, inp))
        if blocks:
            files.append({"path": key, "abs_path": key, "blocks": blocks})
    return {"bg": lexical.build_background(files, segments),
            "q": lexical.query_stats(segments),
            "files": {f["path"]: f for f in files}}


@functools.lru_cache(maxsize=None)
def _inline_corpus(fixture_id, documents, segments):
    files = [{"path": f"/{fixture_id}/{i}.md",
              "abs_path": f"/{fixture_id}/{i}.md",
              "blocks": [{"title": f"b{i}", "content": text}]}
             for i, text in enumerate(documents)]
    return {"bg": lexical.build_background(files, list(segments)),
            "q": lexical.query_stats(list(segments)),
            "files": {}}


def corpus_for(pair, fixture):
    ref = pair["corpus"]
    if "snapshot" in ref:
        return snapshot_corpus(ref["snapshot"])
    inline = fixture["corpora"][ref["inline"]]
    return _inline_corpus(ref["inline"], tuple(inline["documents"]),
                          tuple(inline["segments"]))


def block_content(pair, fixture):
    blk = pair["block"]
    if "content" in blk:
        return blk["content"]
    corpus = snapshot_corpus(blk["snapshot"])
    doc = corpus["files"].get(blk["doc"])
    if doc is None:
        raise KeyError(f"{pair['id']}: {blk['doc']} is not in {blk['snapshot']}")
    for candidate in doc["blocks"]:
        if candidate["title"] == blk["title"]:
            return candidate["content"]
    raise KeyError(f"{pair['id']}: no block titled {blk['title']!r} in {blk['doc']}")


# ---------- scoring ----------

def score_pair(pair, fixture):
    corpus = corpus_for(pair, fixture)
    return lexical.score(block_content(pair, fixture), corpus["bg"], corpus["q"])


def resolvable(pair):
    """Whether both halves of the pair can be read without the frozen corpus.

    Both halves, not just the block: a pair whose corpus is a snapshot cannot
    be scored however the block is stored, and scoring one against a corpus
    that is not there is how a shrunken set passes as the full one.
    """
    inline = "content" in pair["block"] and "inline" in pair["corpus"]
    return inline or snapshots_available()


def inline_pair_count(fixture):
    """The floor under `resolved`: what a clone with no corpus must still score."""
    return sum(1 for p in fixture["pairs"]
               if "content" in p["block"] and "inline" in p["corpus"])


def evaluate(fixture):
    """Score every resolvable pair and return the confusion figures.

    `resolved` / `unresolved` are reported alongside them because the corpus is
    private: on a clone without it 218 of the pairs cannot be read at all, and
    a ratio over the remaining 32 must not be mistaken for the frozen one.

    `precision` is over predicted positives; `undecidable` pairs are scored so
    their result is visible but are counted in neither metric - a pair with no
    ground truth cannot be evidence either way. `truePositives` rides along
    because a tier that answered `no-lexical-trace` to everything would
    otherwise post a perfect precision on an empty numerator.
    """
    rows = []
    for pair in fixture["pairs"]:
        if not resolvable(pair):
            continue
        result = score_pair(pair, fixture)
        rows.append({"id": pair["id"], "label": pair["label"],
                     "provenance": pair["provenance"],
                     "predicted": result["label"], "result": result,
                     "note": pair.get("note", "")})
    metrics = summarise(rows)
    metrics["unresolved"] = len(fixture["pairs"]) - len(rows)
    return metrics


def summarise(rows):
    # A label outside the closed set is not a label. A contributed file arrives
    # full of `TODO`s, and counting one as "not a positive" would let an
    # unanswered pair absorb a real false positive - the pair would vanish from
    # precision while still inflating the row count someone reads as coverage.
    unlabelled = [r for r in rows if r["label"] not in LABELS]
    scored = [r for r in rows
              if r["label"] in LABELS and r["label"] != "undecidable"]
    tp = [r for r in scored if r["predicted"] in PREDICTED_POSITIVE
          and r["label"] in TRUTH_POSITIVE]
    fp = [r for r in scored if r["predicted"] in PREDICTED_POSITIVE
          and r["label"] == "coincidental"]
    fn = [r for r in scored if r["predicted"] not in PREDICTED_POSITIVE
          and r["label"] in TRUTH_POSITIVE]
    positives = len(tp) + len(fp)
    truth_pos = len(tp) + len(fn)
    return {
        "rows": rows,
        # How many pairs were read at all, as opposed to how many carry a
        # scorable label: a set that shrank because its corpus is missing and
        # one that shrank because its pairs are undecidable are different
        # facts, and a single count would report them as the same.
        "resolved": len(rows),
        "scored": len(scored),
        "unlabelled": len(unlabelled),
        "truePositives": len(tp),
        "falsePositives": len(fp),
        "falseNegatives": len(fn),
        # None, not 1.0: a tier that predicted nothing has no precision, and
        # reporting a perfect one would let the gate pass on an empty numerator.
        "precision": (len(tp) / positives) if positives else None,
        "recall": (len(tp) / truth_pos) if truth_pos else None,
        "tp": tp, "fp": fp, "fn": fn,
    }


def report(metrics):
    """The one-screen summary, printed by a failing gate and by the CLI."""
    lines = [f"resolved {metrics['resolved']} pairs",
             f"scored {metrics['scored']} pairs (undecidable excluded: "
             f"{len(metrics['rows']) - metrics['scored'] - metrics['unlabelled']}, "
             f"unlabelled excluded: {metrics['unlabelled']})",
             f"  precision {metrics['precision']}  recall {metrics['recall']}",
             f"  tp {metrics['truePositives']}  fp {metrics['falsePositives']}  "
             f"fn {metrics['falseNegatives']}"]
    if metrics.get("unresolved"):
        lines.insert(1, f"  {metrics['unresolved']} pairs unresolved: "
                        f"{CORPUS_ABSENT}")
    for kind, label in (("fp", "FALSE POSITIVE"), ("fn", "miss")):
        for row in metrics[kind]:
            lines.append(f"  {label}: {row['id']} labelled {row['label']}, "
                         f"scored {row['predicted']} "
                         f"(coverage {row['result']['coverage']}, "
                         f"significant {row['result']['significant'][:4]})")
    return "\n".join(lines)


def by_provenance(metrics):
    out = {}
    for row in metrics["rows"]:
        out.setdefault(row["provenance"], []).append(row)
    return {k: summarise(v) for k, v in sorted(out.items())}


if __name__ == "__main__":
    fx = load()
    overall = evaluate(fx)
    print(report(overall))
    for prov, metrics in by_provenance(overall).items():
        print(f"\n[{prov}]")
        print(report(metrics))
