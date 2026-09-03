"""Harvest candidate (block, session) pairs from your own sessions, for labelling.

The calibration set in `tests/fixtures/lexical_pairs.json` is what stops a
plausible threshold edit from quietly making the lexical tier worse, and it is
only as good as the range of rule documents behind it. Right now that range is
one author's. This script is how somebody else contributes theirs.

**It never touches the network, and nothing on the analysis path imports it.**
The no-network guarantee is this tool's strongest property, so the labelling
workflow does not get to be the exception: this reads your local transcripts,
writes one JSON file, and stops. Sharing that file is a separate, manual act.

The output is self-contained - each pair carries its own corpus inline, so a
reviewer can score it without your transcripts. That is also why it has to be
read before it is shared: the corpus *is* your assistant's prose and your rule
documents, mechanically de-identified and nothing more.

    python3 tests/label_pairs.py --out my-pairs.json
    python3 tests/label_pairs.py --session 9dd3cc8a --out my-pairs.json --limit 40

Then open the file, replace every `"label": "TODO"` with one of `quoted`,
`topically-drawn-on`, `coincidental` or `undecidable`, and write the `note`
saying how you decided. `tests/lexical_fixture.py` documents what each label
means; a pair with no note is not a labelled pair, it is a guess.
"""
import argparse
import getpass
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_real_view as brv          # noqa: E402
import lexical                         # noqa: E402

LABEL_TODO = "TODO"
# Enough prose for a reviewer to judge the pair, and few enough segments that
# one contribution is reviewable by hand. D3 and the length model both need a
# real sample, so this is a floor as much as a cap - below roughly this many
# segments the session background stands down and the pair scores differently
# than it did in your own report.
SEGMENT_CAP = 60
BLOCK_CHARS = 1200


def _redactions():
    """The mechanical substitutions. Deliberately few, and deliberately named.

    A regex cannot de-identify prose, and pretending otherwise is worse than
    not trying: a contributor who believes the output is sanitised will not
    read it. So this replaces the home directory, and the account name when it
    is long enough to match safely, and the printed output says plainly that
    the rest is your own text.
    """
    subs = [(re.escape(str(Path.home())), "~")]
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    # Whole word only, and never a short one: an account name like "sam" or
    # "ana" is a substring of ordinary prose, and rewriting every occurrence
    # would corrupt the text a reviewer has to read to label the pair.
    if len(user) >= 4:
        subs.append((r"\b" + re.escape(user) + r"\b", "user"))
    return [(re.compile(pattern), replacement) for pattern, replacement in subs]


def sanitise(text, subs):
    for pattern, replacement in subs:
        text = pattern.sub(replacement, text)
    return text


def harvest(session_prefix=None, limit=30):
    transcripts = brv.discover_all_transcripts(Path.cwd())
    if session_prefix:
        transcripts = [t for t in transcripts if t.stem.startswith(session_prefix)]
    if not transcripts:
        raise SystemExit("no transcript found - run this from a directory that has "
                         "Claude Code sessions, or pass --session")
    path = transcripts[0]
    events = brv.load_transcript(path)
    calls = brv.tool_calls(events)
    segments = lexical.clean_query_segments(
        [s["text"] for s in brv.assistant_text_segments(events)],
        copied=[s["text"] for s in brv.chronological_segments(events)
                if s["kind"] == "tool_result"])[:SEGMENT_CAP]

    class _Args:
        skills_dir = None

    files = brv.load_context_files(events, calls, str(Path.cwd()), _Args(),
                                   brv.first_real_user_prompt(events) or "")

    subs = _redactions()
    # The corpus is emitted first and the pairs are scored against *it*, not
    # against the session's live background. The emitted documents are
    # truncated and the segments capped, which moves the term weighting - so
    # scoring against the live background can print a label in each pair's note
    # that the reviewer's own re-score contradicts, with neither number wrong
    # and nothing in the file saying which to believe. Every block goes in,
    # including the short ones no pair is made from, because the document count
    # is D1's denominator.
    documents = [(b.get("content") or "")[:BLOCK_CHARS]
                 for f in files if f.get("loaded")
                 for b in f.get("blocks") or ()]
    emitted = [{"path": f"/corpus/{i}.md", "abs_path": f"/corpus/{i}.md",
                "blocks": [{"title": f"b{i}", "content": text}]}
               for i, text in enumerate(documents)]
    bg = lexical.build_background(emitted, segments)
    q = lexical.query_stats(segments)

    candidates = []
    for f in files:
        if not f.get("loaded"):
            continue
        for block in f.get("blocks") or ():
            content = (block.get("content") or "")[:BLOCK_CHARS]
            if len(content.split()) < 20:
                continue
            candidates.append({"file": f.get("path"), "title": block.get("title"),
                               "content": content,
                               "result": lexical.score(content, bg, q)})

    # Everything the tier calls positive comes first: those are the pairs that
    # decide precision, so a contribution that skipped them would be labelling
    # only the easy half.
    positive, rest = [], []
    for c in candidates:
        target = (positive if c["result"]["label"] in (lexical.ECHOED, lexical.TOPICAL)
                  else rest)
        target.append(c)
    # `--limit` bounds the sample of the rest, never the positives: dropping
    # one would hide the pair that decides precision.
    step = max(1, len(rest) // max(1, limit - len(positive)))
    picked = positive + rest[::step][:max(0, limit - len(positive))]

    corpus_id = "contributed-" + re.sub(r"[^a-z0-9]", "", path.stem.lower())[:12]
    pairs = []
    for c in picked:
        pairs.append({
            "id": f"{corpus_id}-{len(pairs):03d}",
            "label": LABEL_TODO,
            "provenance": "contributed",
            "note": f"TODO: say how you decided. The tier currently scores this "
                    f"{c['result']['label']} (coverage {c['result']['coverage']}, "
                    f"significant terms {c['result']['significant'][:4]}).",
            "source": {"file": sanitise(c["file"] or "", subs),
                       "title": sanitise(c["title"] or "", subs)},
            "block": {"content": sanitise(c["content"], subs)},
            "corpus": {"inline": corpus_id},
        })
    return {
        "version": 1,
        "note": "Contributed calibration pairs. Every `label` and `note` marked TODO "
                "needs a human answer before this file is worth anything. Read the "
                "whole file before sharing it - the corpus below is your own prose, "
                "with only home paths and your account name replaced.",
        "corpora": {corpus_id: {
            "documents": [sanitise(d, subs) for d in documents],
            "segments": [sanitise(s, subs) for s in segments],
        }},
        "pairs": pairs,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", help="session id prefix (default: the most recent)")
    ap.add_argument("--limit", type=int, default=30, help="candidate pairs to emit")
    ap.add_argument("--out", default="contributed-pairs.json")
    args = ap.parse_args(argv)
    out = harvest(args.session, args.limit)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    todo = sum(1 for p in out["pairs"] if p["label"] == LABEL_TODO)
    size = Path(args.out).stat().st_size
    print(f"wrote {args.out}: {len(out['pairs'])} candidate pairs, {todo} to label, "
          f"{size // 1024} KB - the corpus is this session's own blocks and prose, "
          f"mechanically de-identified and nothing more")
    print("Read it before you share it. Nothing was sent anywhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
