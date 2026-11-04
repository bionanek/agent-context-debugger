---
description: Compile a guidelines document's rules into a reviewed <doc>.checks.json
argument-hint: [path to the guidelines document, e.g. CLAUDE.md]
---

Compile the rules in a guidelines document into machine-checkable records, so this
project's audits can decide them offline instead of reporting them as unchecked.

The document to compile: $ARGUMENTS

If no path was given, compile the first of these that exists, and say which you picked:
`./CLAUDE.md`, `~/.claude/CLAUDE.md`, `./AGENTS.md`, `./.claude/rules/*.md`.

Read @prompts/translate-rules.md and follow the flow in it exactly - it is the
authoritative specification of the record format, the vocabulary, the buckets and the
gates the consuming tool applies at load time. Do not paraphrase it from memory.

Two things it asks of you that are easy to skip:

- Verify every fixture against the vocabulary table before writing the file, and then say
  out loud that your verification does not count - the tool re-runs them with its own
  matcher and demotes what disagrees.
- Stop at the review gate. Name the file, report the per-bucket counts, and hand it to the
  user to read before committing. Do not commit it yourself.

After the file is written, the audit picks it up on the next run with no further setup:

```bash
# the `rules` line names the counts; `--query sessions` only carries the
# reminder, and that disappears once nothing is left to compile
python3 build_real_view.py --query sessions
python3 build_real_view.py --query <session-id-prefix>
```
