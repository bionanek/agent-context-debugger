"""The lexical tier: how much of a block's distinctive wording the run reused.

Lexical overlap is co-occurrence and nothing more. It cannot establish that a
block caused anything, and its absence is not evidence of non-use - silent
behavioural compliance leaves no lexical trace at all. So everything here
produces a label naming the *evidence* (`echoed`, `topical-overlap`,
`no-lexical-trace`, `not-lexically-scorable`), never the mechanism, and the
caller caps whatever it does with that label well below a hard verdict.

The vocabulary is the whole problem. Counting a block's first eight five-letter
words anywhere in the assistant's text scored a tech-stack table 5/8 against an
unrelated discussion of the Effect library, because "Framework", "React",
"Native" and "TypeScript" are ambient in a React Native repo and will match
almost any turn of it. No threshold fixes that; the terms have to be weighted
against what is ordinary *here* before anything is counted. Three backgrounds
do it, all computable offline:

  D1  block-collection IDF - how many of the loaded context blocks use the term
      at all, in Lucene's non-negative form (textbook RSJ IDF goes negative
      above df 50%, which is exactly where the boilerplate lives).
  D2  general English - a baked Zipf list; zipf >= 5 weights zero, 3.0-5.0
      ramps down. Optional: absent, the tier runs on D1 x D3, which is what
      keeps it language-neutral.
  D3  the session's own background - the fraction of the session's assistant
      segments containing the term; >= 0.35 weights zero. This is the one that
      kills "React" in a React repo, i.e. most of the observed false positives.

The three backgrounds are session-wide by construction, so a block's term set
is identical at turn scope and session scope. That is deliberate: computing it
per turn would let the same block be "distinctive" in turn 3 and boilerplate in
turn 4 purely because the denominator moved.
"""

import functools
import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

# The four labels. They name what was observed, never why: even a verbatim
# quote is self-report, and a block with no trace may have been obeyed in
# silence.
ECHOED = "echoed"
TOPICAL = "topical-overlap"
NO_TRACE = "no-lexical-trace"
UNSCORABLE = "not-lexically-scorable"
LABELS = (ECHOED, TOPICAL, NO_TRACE, UNSCORABLE)

ZIPF_PATH = Path(__file__).resolve().parent / "data" / "wordfreq-en.json"

# D3: a term in this fraction of the session's assistant segments is the way
# this project talks, not something the block put there. It needs a sample to
# say that, though: in a three-paragraph session every term the run and the
# block share sits in 33% of the segments, so D3 would zero exactly the terms
# that matched. Below the floors it stands down and the tier runs on D1 x D2.
AMBIENT_FLOOR = 0.35
MIN_AMBIENT_SEGMENTS = 8
MIN_AMBIENT_HITS = 3
# D2: the ramp from "rare enough to mean something" to "everyday English".
ZIPF_RARE = 3.0
ZIPF_COMMON = 5.0
# The third condition of the topical gate: at least one term the reader would
# not expect to meet in ordinary prose.
ZIPF_DISTINCTIVE = 4.0

K_SIZE = 12
# Below this a block has no vocabulary of its own - a table of column headers,
# a heading with a sentence under it - and scoring it on whatever generic
# tokens survive is how boilerplate ends up "topical" with everything.
MIN_TERMS = 3
# A term has to clear this to be one of the block's own. It is tied to
# ZIPF_DISTINCTIVE through the D2 ramp: with the other two backgrounds silent,
# exactly the terms at or below zipf 4 survive. Anything looser kept "layer",
# "framework" and "mode" - the words a table is made of.
MIN_WEIGHT = 0.5
# A collection this small says nothing about what is ordinary: with a handful
# of blocks every term sits in "most" of them and IDF crushes the lot. Below
# it D1 stands down rather than pushing blocks toward `not-lexically-scorable`,
# because an optional background must never make a label worse.
MIN_COLLECTION = 20
# Only the first N tokens of a block are read. A block's identity is in its
# opening; letting a long appendix contribute terms both costs time on every
# block of every turn and dilutes what the block is actually about.
BLOCK_TOKEN_CAP = 400

# Dunning's G^2 against a reference corpus, at the 99% critical value, with the
# >= 2 observation guard: one occurrence of a rare word is not a pattern, and
# the statistic is unreliable there whatever it reports.
G2_CRITICAL = 6.63
MIN_OBSERVATIONS = 2
MIN_SIGNIFICANT = 2
# The reference is general English AND the loaded documents, whichever uses the
# term more - a term has to be over-represented against both to count. Notional
# corpus size, since the English side is a rate rather than a count.
REFERENCE_TOKENS = 1_000_000
# A collection smaller than this is not a corpus; using it as one lets a
# 13-token document decide what an ordinary rate is.
MIN_REFERENCE = 2000
# Neither English nor the documents know this term, so treat it as rare rather
# than as impossible - a zero reference rate makes every second occurrence
# overwhelmingly significant.
UNKNOWN_ZIPF = 2.5

# BM25 tuned for short passages (k1) against highly variable turn lengths (b).
# Not swept: tuning k1/b before the vocabulary is fixed optimises the wrong
# thing.
BM25_K1 = 0.9
BM25_B = 0.75
# Swept on the labelled set in `tests/fixtures/lexical_pairs.json`, not chosen:
# at 0.25 a standup skill that was never invoked scored `topical-overlap` on
# "toggling" from a badge-layout reply and "flagging" from a Notion enum
# discussion, at coverage 0.258. The nearest true positive sits at 0.331, so
# the bar moves to the round number between them. `tests/test_calibration.py`
# pins this figure and re-measures precision, because the next person to nudge
# it will have a plausible reason too.
COVERAGE_FLOOR = 0.30

SHINGLE_N = 5
CONTAINMENT_FLOOR = 0.15
MIN_MATCHED_SHINGLES = 3
# A run has to clear BOTH bars, not either one. Taken as alternatives, an
# eight-token run of seven function words and one content word qualifies, and
# the calibration set has exactly that pair twice over: "do you have a figma
# design for this" appears in two of the user's command files, one invoked and
# one not, so the same 35-character run was the evidence for a true positive
# and a false one at once. Requiring the characters as well is the
# precision-first reading of the two bars, and it costs the true half of that
# twin - which no threshold could have kept without the false half.
RUN_TOKENS = 8
RUN_CHARS = 40
# The window of query tokens the run detector aligns against, either side of a
# matched shingle. SequenceMatcher is quadratic, and a whole session's prose
# against every block of every turn is not a comparison anyone can afford.
RUN_WINDOW = 60
RUN_BLOCK_CAP = 600
RUN_ANCHORS = 8
# Shorter than this and a line the agent and a tool result share is a coincidence
# ("Done.", a bare path), not something copied out of a file.
COPIED_LINE_LEN = 40

# Unicode letters, not ASCII: the tier has to work on a rule document written
# in another language, where D2 simply does not know the words and they weight
# as the rare terms they are. The 4-character floor is still a Latin-script
# assumption and is the one place this tier is not language-neutral.
_TOKEN_RE = re.compile(r"[^\W\d_][\w-]*")
# The one definition of a code fence, shared with build_real_view: groups are
# the marker, the info string and the body. An unclosed fence runs to the end.
FENCE_RE = re.compile(r"^[ \t]*(```|~~~)([^\n]*)\n?(.*?)(?:^[ \t]*\1|\Z)", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_MIN_TOKEN_LEN = 4


@functools.lru_cache(maxsize=1)
def english_zipf():
    """The baked Zipf list, or {} when it is not shipped or not readable.

    Missing, D2 is simply 1.0 everywhere and the tier runs on D1 x D3. That is
    a degradation, not an error: an optional signal must never make a verdict
    worse, and a hard failure here would take the whole audit down over a
    convenience file.
    """
    try:
        with open(ZIPF_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def tokens(text):
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def strip_code(text):
    """Drop fenced blocks and inline code spans from a passage of prose.

    Code the agent printed is not the agent talking about a rule, and a fence
    is routinely a slab of the very file whose blocks are being scored.
    """
    return _INLINE_CODE_RE.sub(" ", FENCE_RE.sub(" ", text or ""))


def clean_query_segments(texts, copied=()):
    """The only text the tier reads: assistant prose, with the borrowings removed.

    Tool inputs and tool results never get here - the caller passes assistant
    text segments - but the agent also quotes what it just read, and a Read'd
    file's content inside the query makes every block of that file match
    itself. That is the most likely new false positive in the whole tier, so
    fenced code, inline code and any long line that also appears in a tool
    result are all dropped.

    Extended thinking is deliberately absent. Its availability is mixed per
    model and CLI version, and a signal a transcript may or may not carry must
    not decide a status.
    """
    # A set of whole lines, not a substring scan over the joined text: the
    # results run to hundreds of kilobytes and this is called once per scope,
    # so the scan is a quadratic cost nothing in a test would show.
    borrowed = {ln.strip() for text in copied for ln in text.splitlines()
                if len(ln.strip()) >= COPIED_LINE_LEN}
    out = []
    for text in texts:
        kept = []
        for line in strip_code(text).splitlines():
            if line.strip() in borrowed:
                continue
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        if cleaned:
            out.append(cleaned)
    return out


def scored_tokens(text):
    """The tokens both the length model and the term counts are built from.

    One function, because `_coverage` divides a scope's token count by the
    session's average segment length: counting all tokens on one side and only
    the >= 4-character ones on the other silently halved the length ratio and
    with it BM25's length penalty.
    """
    return [t for t in tokens(text) if len(t) >= _MIN_TOKEN_LEN]


def block_tokens(content):
    """A block's tokens, read the same way the query's are.

    Code spans are stripped from both sides or the two disagree about what a
    token is: the gh-account rule's whole vocabulary is backticked account and
    repo names, so with code kept on the block side and stripped on the query
    side its terms could never match anything and the block was guaranteed
    `no-lexical-trace` - a measurement dressed up as a finding, where the
    honest answer is that its prose has nothing to score.
    """
    return tokens(strip_code(content))[:BLOCK_TOKEN_CAP]


def _terms_of(toks):
    """Unigrams and bigrams of a token list, deduplicated, order preserved.

    Bigrams are in because a rule's identity usually lives in a phrase
    ("decision memory", "task notification") whose halves are each ordinary.
    Trigrams are out: they add a third n-gram index over every block of every
    loaded file for a phrase a bigram has already made distinctive.

    "Adjacent" means adjacent after the short words are dropped, so "pipe it
    through printf" yields "through printf" and a bigram can bridge a sentence
    break. That is loose, but the block and the query are tokenized by this one
    function, so both sides mean the same thing by it.
    """
    words = [t for t in toks if len(t) >= _MIN_TOKEN_LEN]
    out = list(dict.fromkeys(words))
    seen = set(out)
    for a, b in zip(words, words[1:]):
        bigram = a + " " + b
        if bigram not in seen:
            seen.add(bigram)
            out.append(bigram)
    return out


def _segment_presence(segments):
    """term -> how many of these segments contain it (D3's numerator)."""
    counts = Counter()
    for seg in segments:
        counts.update(set(_terms_of(tokens(seg))))
    return counts


def build_background(context_files, segments):
    """The three backgrounds, computed once for a whole session.

    `context_files` are the loader's records (each with `blocks`); `segments`
    are the session's cleaned query segments. Both are session-wide on purpose
    - see the module docstring on why the denominators must not move per turn.
    """
    df = Counter()
    ref = Counter()
    ref_total = 0
    blocks = 0
    seen_paths = set()
    for f in context_files or ():
        key = f.get("abs_path") or f.get("path")
        if key in seen_paths:
            continue
        seen_paths.add(key)
        for b in f.get("blocks") or ():
            toks = block_tokens(b.get("content") or "")
            if not toks:
                continue
            blocks += 1
            words = [t for t in toks if len(t) >= _MIN_TOKEN_LEN]
            ref.update(words)
            ref_total += len(words)
            # Document frequency over unigrams only. A bigram index over the
            # whole loaded collection is millions of keys for a number that
            # `_idf` can bound from its own words.
            df.update(set(words))
    ambient = _segment_presence(segments or [])
    return {
        "df": df,
        "blocks": blocks,
        "ref": ref,
        "refTotal": ref_total,
        "ambient": ambient,
        "segments": len(segments or []),
        "avgSegmentTokens": (sum(len(scored_tokens(s)) for s in segments) / len(segments)
                             if segments else 0.0),
        "terms": {},
    }


def empty_background():
    """A background that knows nothing - every term is maximally distinctive.

    Used where no collection was built (a hand-assembled trace in a test, a
    scope that loaded nothing). D1 and D3 fall silent rather than pushing a
    block toward `no-lexical-trace`, which would be an optional signal making a
    verdict worse.
    """
    return {"df": Counter(), "blocks": 0, "ref": Counter(), "refTotal": 0,
            "ambient": Counter(), "segments": 0, "avgSegmentTokens": 0.0, "terms": {}}


def _idf(term, bg):
    """Lucene's non-negative IDF, normalised into (0, 1]."""
    n = bg["blocks"]
    if n < MIN_COLLECTION:
        return 1.0
    if " " in term:
        # A phrase is at least as rare as its rarest word, and cheaper to bound
        # that way than to carry a second document-frequency index.
        return max(_idf(w, bg) for w in term.split(" "))
    df = bg["df"].get(term, 0)
    top = math.log(1 + (n + 0.5) / 0.5)
    return min(1.0, math.log(1 + (n - df + 0.5) / (df + 0.5)) / top)


def _english(term, zipf):
    """D2: 1.0 for a term ordinary English does not have, 0.0 for one it uses daily."""
    if not zipf:
        return 1.0, None
    words = term.split(" ")
    # The *most* ordinary member decides: a phrase built out of an everyday
    # word is an everyday phrase. Bounding by the rarest member instead - the
    # correct estimate of the phrase's own frequency, and what `_reference_rate`
    # and `_idf` do, because those two ask that question - would let one rare
    # word mint a pseudo-term for every phrase it sits in.
    best = max(zipf.get(w, ZIPF_RARE - 1.0) for w in words)
    if best >= ZIPF_COMMON:
        return 0.0, best
    if best <= ZIPF_RARE:
        return 1.0, best
    return (ZIPF_COMMON - best) / (ZIPF_COMMON - ZIPF_RARE), best


def _ambient(term, bg):
    """D3: 1.0 for a term the session never says, 0.0 at the ambient floor."""
    total = bg["segments"]
    hits = bg["ambient"].get(term, 0)
    if total < MIN_AMBIENT_SEGMENTS or hits < MIN_AMBIENT_HITS:
        return 1.0
    share = hits / total
    return max(0.0, 1.0 - share / AMBIENT_FLOOR)


def block_terms(content, bg):
    """K(block): the block's own vocabulary, strongest first.

    Cached on the background because the three weights are session-wide, so the
    same block content answers identically in every turn - which is also what
    stops a term set drifting between the aggregate and the turns it is
    combined from.
    """
    cache = bg.setdefault("terms", {})
    hit = cache.get(content)
    if hit is not None:
        return hit
    zipf = english_zipf()
    scored = []
    for term in _terms_of(block_tokens(content)):
        d2, z = _english(term, zipf)
        if d2 <= 0:
            continue
        d3 = _ambient(term, bg)
        if d3 <= 0:
            continue
        weight = _idf(term, bg) * d2 * d3
        if weight < MIN_WEIGHT:
            continue
        scored.append({"term": term, "weight": weight, "zipf": z})
    scored.sort(key=lambda t: -t["weight"])
    out = scored[:K_SIZE]
    cache[content] = out
    return out


def query_stats(segments):
    """Per-scope counts the scoring reads. Built once, from the cleaned segments."""
    toks = []
    for seg in segments or ():
        toks.extend(tokens(seg))
    words = [t for t in toks if len(t) >= _MIN_TOKEN_LEN]
    # `words` is `scored_tokens` over the joined segments - the same unit
    # `avgSegmentTokens` is measured in, which is what makes the length ratio
    # in `_coverage` mean anything.
    counts = Counter(words)
    counts.update(a + " " + b for a, b in zip(words, words[1:]))
    return {
        "tokens": toks,
        "counts": counts,
        "total": len(words),
        "segments": len(segments or []),
        "shingles": None,
    }


def empty_query():
    return {"tokens": [], "counts": Counter(), "total": 0, "segments": 0, "shingles": None}


def _g2(a, b, c, d):
    """Dunning log-likelihood for a term at rate a/b against a reference c/d.

    One-sided: a term the run uses *less* than the reference is not evidence
    the run was about it, and reporting the statistic either way would let
    under-use clear a gate named "significance".
    """
    if not b or not d or a <= 0:
        return 0.0
    if a / b <= c / d:
        return 0.0
    exp_a = b * (a + c) / (b + d)
    exp_c = d * (a + c) / (b + d)
    total = a * math.log(a / exp_a) if exp_a else 0.0
    if c and exp_c:
        total += c * math.log(c / exp_c)
    return 2 * total


def _reference_rate(term, bg, zipf):
    """How often ordinary text uses this term, per token."""
    words = term.split(" ")
    # A phrase is at most as frequent as its rarest word. Bounding it that way
    # overstates the reference rate, which is the conservative direction: it
    # can only make the term harder to call significant.
    rates = [min(10 ** (zipf.get(w, UNKNOWN_ZIPF) - 9) for w in words)] if zipf else []
    if bg["refTotal"] >= MIN_REFERENCE:
        rates.append(min(bg["ref"].get(w, 0) for w in words) / bg["refTotal"])
    return max(rates) if rates else 10 ** (UNKNOWN_ZIPF - 9)


def _coverage(terms, bg, q):
    """BM25 with the block as query, normalised into [0, 1].

    The raw score is unbounded and means nothing to a reader; what the gate
    needs is "how much of this block's weighted vocabulary did the run actually
    reach", so each term's saturating term-frequency factor is divided back out
    by its own ceiling and the weighted mean is taken.

    The length `b` scales against is the session's own average segment length,
    not a constant: a scope is as long as the number of things the agent said
    in it, so comparing a whole session against a fixed notional turn size
    would penalise the aggregate for being an aggregate.
    """
    if not terms or not q["total"]:
        return 0.0
    per_segment = bg["avgSegmentTokens"] or (q["total"] / max(1, q["segments"]))
    expected = per_segment * max(1, q["segments"])
    norm = BM25_K1 * (1 - BM25_B + BM25_B * (q["total"] / expected if expected else 1.0))
    got = 0.0
    want = 0.0
    for t in terms:
        want += t["weight"]
        tf = q["counts"].get(t["term"], 0)
        if tf:
            got += t["weight"] * (tf / (tf + norm))
    return got / want if want else 0.0


def _shingles(toks, n=SHINGLE_N):
    return [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]


def _query_shingles(q):
    if q["shingles"] is None:
        index = {}
        for i, sh in enumerate(_shingles(q["tokens"])):
            # First occurrence wins. A repeated shingle gives several equally
            # good anchors and the run detector only needs one window per
            # anchor, so keeping them all would cost memory for nothing.
            index.setdefault(sh, i)
        q["shingles"] = index
    return q["shingles"]


def _quote(content, terms, q):
    """Verbatim reuse of the block's wording, or None.

    Two signals, both requiring a distinctive term inside the matched text: a
    run of generic function words is the most common long match between any two
    English passages and says nothing. Containment rather than Jaccard because
    the two sides are wildly different lengths.
    """
    distinctive = set()
    for t in terms:
        distinctive.update(t["term"].split(" "))
    if not distinctive or not q["tokens"]:
        return None
    block_toks = block_tokens(content)[:RUN_BLOCK_CAP]
    block_sh = _shingles(block_toks)
    if not block_sh:
        return None
    index = _query_shingles(q)
    matched = [(sh, index[sh]) for sh in block_sh if sh in index]
    if not matched:
        return None

    # An >= 8-token exact run is the stronger claim, so it is tried first, and
    # only against the window around a match - SequenceMatcher is quadratic and
    # this runs per block per turn. autojunk=False is mandatory: the default
    # discards exactly the frequent words that hold a quoted sentence together.
    # Anchors spread across the matched shingles, not the first eight: matched
    # shingles cluster at the block's opening, and a block whose quoted
    # sentence is at the end would be aligned against eight windows that cannot
    # contain it.
    step = max(1, len(matched) // RUN_ANCHORS)
    for _sh, pos in matched[::step][:RUN_ANCHORS]:
        lo = max(0, pos - RUN_WINDOW)
        window = q["tokens"][lo:pos + len(block_toks) + RUN_WINDOW]
        match = SequenceMatcher(None, block_toks, window, autojunk=False).find_longest_match(
            0, len(block_toks), 0, len(window))
        if not match.size:
            continue
        run = block_toks[match.a:match.a + match.size]
        text = " ".join(run)
        if (match.size >= RUN_TOKENS and len(text) >= RUN_CHARS) and distinctive & set(run):
            return {"kind": ECHOED, "text": text[:300], "tokens": match.size,
                    "containment": round(len(matched) / len(block_sh), 3)}

    strong = [sh for sh, _ in matched if distinctive & set(sh)]
    containment = len(matched) / len(block_sh)
    if containment >= CONTAINMENT_FLOOR and len(strong) >= MIN_MATCHED_SHINGLES:
        return {"kind": "paraphrased", "text": " ".join(strong[0])[:300],
                "tokens": len(strong), "containment": round(containment, 3)}
    return None


def score(content, bg, q):
    """Label one block against one scope's prose.

    Returns the baked record: the label, the terms it was scored on, the
    coverage figure, the terms that cleared significance, and the quote if
    there was one. Nothing here decides a status - the caller does, and caps it.
    """
    bg = bg or empty_background()
    q = q or empty_query()
    terms = block_terms(content, bg)
    out = {"label": UNSCORABLE, "terms": [t["term"] for t in terms],
           "coverage": 0.0, "significant": [], "quote": None, "reason": ""}
    # Counted over distinct words, not term slots: one distinctive word fills
    # three slots through the phrases it sits in, and "workflow", "managed
    # workflow" is not three-term vocabulary.
    distinct = {w for t in terms for w in t["term"].split(" ")}
    if len(terms) < MIN_TERMS or len(distinct) < MIN_TERMS:
        out["reason"] = (f"Only {len(distinct)} distinctive term(s) after weighting against "
                         "the loaded documents, everyday English and this session's own "
                         "vocabulary - too few to score. Not a statement about whether the "
                         "block was followed.")
        return out
    if not q["total"]:
        out["reason"] = ("The run produced no assistant prose to score against, so the "
                         "lexical tier has nothing to measure.")
        return out

    out["coverage"] = round(_coverage(terms, bg, q), 3)
    zipf = english_zipf()
    significant = []
    for t in terms:
        observed = q["counts"].get(t["term"], 0)
        if observed < MIN_OBSERVATIONS:
            continue
        expected = _reference_rate(t["term"], bg, zipf) * REFERENCE_TOKENS
        if _g2(observed, q["total"], expected, REFERENCE_TOKENS) >= G2_CRITICAL:
            significant.append(t["term"])
    out["significant"] = significant

    quote = _quote(content, terms, q)
    if quote:
        # Both detector outcomes land on `echoed`: the four labels are a closed
        # set, and 15% five-word containment is reused wording however loosely
        # it was reworded. Which of the two fired is in the reason, because the
        # reader deserves to know whether it was a quote or a paraphrase.
        out["quote"] = quote
        out["label"] = ECHOED
        out["reason"] = (
            f"The run reproduced the block's wording "
            + (f"verbatim ({quote['tokens']} tokens)"
               if quote["kind"] == ECHOED
               else f"closely ({quote['tokens']} shared 5-word runs, "
                    f"containment {quote['containment']})")
            + ". Reuse of wording is not proof the block caused the behaviour.")
        return out

    rare = any(t["zipf"] is None or t["zipf"] < ZIPF_DISTINCTIVE for t in terms)
    if len(significant) >= MIN_SIGNIFICANT and out["coverage"] >= COVERAGE_FLOOR and rare:
        out["label"] = TOPICAL
        out["reason"] = (f"{len(significant)} of the block's distinctive terms are "
                         f"over-represented in the run's prose ({', '.join(significant[:6])}) "
                         f"at coverage {out['coverage']}. Shared subject matter only - "
                         "nothing ties the behaviour back to the block.")
        return out

    out["label"] = NO_TRACE
    out["reason"] = (f"None of the block's {len(terms)} distinctive terms are "
                     "over-represented in the run's prose "
                     f"({len(significant)} significant, coverage {out['coverage']}). "
                     "A rule can be followed in silence, so this is not evidence "
                     "the block was ignored.")
    return out
