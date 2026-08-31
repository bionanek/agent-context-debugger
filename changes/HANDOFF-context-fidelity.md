# Handoff: context-fidelity upgrades for `build_real_view.py`

Target repo: `~/Git/agent-context-ide`
Companion artifact: `ctxlog.py` (hook-based session collector, see Appendix A)

## What this is

`build_real_view.py` reconstructs a Claude Code session from the transcript JSONL,
splits every instruction file into heading-scoped blocks, derives predicates from
each block, and assigns one of six statuses (`used`, `used-partial`, `ignored`,
`unused`, `dormant`, `not-loaded`).

The predicate engine is sound. Three things upstream of it are not, and each one
produces a **wrong verdict** rather than a missing one:

1. **Truncation is invisible.** A rule past line 2000 of a long guide was never
   delivered to the model. The evaluator scores it `unused`, which reads as
   "Claude ignored your rule" when the truth is "your rule never arrived".
2. **Load detection is assumed, not observed.** Three `add_file(..., loaded=True,
   source="disk")` calls hardcode the assumption. For `.claude/rules/*.md` this is
   often wrong: rules with `paths:` frontmatter load only when Claude touches a
   matching file. There is no frontmatter handling in the file, so unconditional
   and conditional rules are treated identically.
3. **Compaction is not modelled.** After compaction, path-scoped rules drop out of
   context and do not return until a matching file is read again. A block scored
   `dormant` after that point may simply have been evicted.

Work the tasks in order. Task 1 is self-contained. Task 2 depends on Step 0's outcome.

---

## Step 0 (do this first, it branches the plan)

The transcript entry format is internal to Claude Code and changes between
releases. The embedded sample session in `agent-context-ide-real.html` was built
on Claude Code **2.1.132**; current builds are past 2.1.214. Verify the ingestion
still works before changing anything:

```bash
cd ~/Git/agent-context-ide
python3 build_real_view.py --list
python3 build_real_view.py --out /tmp/probe.html
```

Then check that `extract_attachments` (line 341) still returns non-empty
`nested_memories` and `skill_listing` on a current session. Add a temporary print
or use a debugger; do not commit the probe.

- **If both are populated:** ingestion is healthy. Do Task 1, then Task 2 as an
  accuracy improvement.
- **If either is empty:** the transcript shape has drifted and `load_context_files`
  is silently falling back to path conventions for everything. Task 2 becomes the
  repair rather than an improvement. Do Task 2 first, and report which specific
  keys went missing before writing the adapter.

Report the outcome before proceeding past Task 1.

---

## Task 1: `undelivered` status for truncated blocks

**Goal:** a block that lives outside the delivered byte range of its file must not
be scored as if the model saw it.

### Background

The Read tool returns the first 2000 lines when no explicit `limit` is passed, and
truncates individual lines at 2000 characters. When a whole-file read exceeds the
token limit, Read returns the first page with a PARTIAL view notice. None of this
is recoverable from the transcript alone: you need the file's real line count from
disk to know what was withheld.

### Changes

1. **Per-file delivered range.** In `load_context_files` (line 500), extend the
   record built by the inner `add_file` helper with:

   ```
   "total_lines":     int    # line count on disk at build time
   "delivered_from":  int    # 1-based first line the model received
   "delivered_to":    int    # 1-based last line, or None if unknown
   "delivery":        str    # "full" | "truncated" | "partial-by-request" | "unknown"
   ```

   Derive these per source kind:
   - `source="transcript"` (nested_memory attachments carry authoritative content):
     the content in the attachment *is* what was delivered. Compare its line count
     against disk. Fewer lines than disk means truncated.
   - `kind="read"` (the `.md` files picked up from Read tool calls near line 708):
     use the call's `offset` / `limit` when present. Absent both, treat lines
     `1..min(2000, total_lines)` as delivered.
   - `source="disk"` for the eagerly-loaded CLAUDE.md files: these are injected by
     the harness, not read through the Read tool, so no 2000-line cap applies.
     Mark `delivery="full"`.

   When the line count cannot be established, use `delivery="unknown"` and treat it
   as full. Never guess a block into `undelivered`.

2. **Block-level line spans.** `parse_claude_md` (line 98) already walks headings.
   Have it record `start_line` and `end_line` on each block. A block is undelivered
   when `start_line > delivered_to`.

3. **Gate in `assess_block`** (line 1513). Insert the check immediately after the
   existing `if not file_loaded:` early return and before `derive_predicates`:

   ```python
   if _block_undelivered(block, file):
       return {..., "status": "undelivered",
               "reason": f"File was truncated at line {file['delivered_to']} of "
                         f"{file['total_lines']}; this block starts at line "
                         f"{block['start_line']} and never reached the model.",
               "evidence": [...], "moments": [_moment(...)]}
   ```

   Predicates must not run. Running them and reporting `unused` is the bug.

4. **Precedence in `combine_verdicts`** (line 282). `undelivered` joins the
   NOT-USED family. Insert it ahead of the others in the fallback loop, since it is
   the most informative label available:

   ```python
   for fallback in ("undelivered", "unused", "dormant", "not-loaded"):
   ```

   Do not touch the `ignored` / `used` / `used-partial` precedence above it.

5. **UI.** Add the status to the legend and filter chips in the HTML template with
   a visually distinct colour from `unused`. The distinction the user cares about is
   *never arrived* versus *arrived and ignored*; if those two look alike the feature
   has no value.

### Acceptance

- A repo with a 2400-line `docs/gotchas.md` whose final heading contains a rule:
  that block reports `undelivered` naming both line numbers, and no predicate
  evidence is attached.
- The same rule moved above line 2000 reverts to normal predicate assessment.
- A single-turn session with no truncated files produces **byte-identical** HTML to
  before the change. This invariant is already documented in `combine_verdicts`;
  preserve it.

---

## Task 2: hook-fed loading facts

**Goal:** replace three assumptions with observations, and correctly classify
conditionally-loaded rules.

### Background

Claude Code has an `InstructionsLoaded` hook event that fires whenever a
`CLAUDE.md` or `.claude/rules/*.md` file is loaded into context, at session start
and again on lazy loads mid-session. It is documented as running asynchronously for
observability and has no decision control, so it cannot affect a session. Payload:

| Field | Meaning |
|---|---|
| `file_path` | absolute path of the instruction file |
| `memory_type` | `User` / `Project` / `Local` / `Managed` |
| `load_reason` | `session_start` / `nested_traversal` / `path_glob_match` / `include` / `compact` |
| `globs` | the `paths:` frontmatter patterns, on `path_glob_match` loads |
| `trigger_file_path` | the file whose access caused a lazy load |
| `parent_file_path` | the including file, on `include` loads |

`ctxlog.py` already captures this into `~/.claude/ctxlog/<session_id>.jsonl`, one
JSON object per line, keyed by `session_id` and `event`.

### Changes

1. **Adapter, not surgery.** Write `ctxlog_facts.py` exposing:

   ```python
   def load_facts(session_id: str, ctxlog_dir: Path | None = None) -> dict | None
   ```

   Returning `None` when no log exists for that session. On success, return the
   same shape `extract_attachments` produces, plus a new `instructions` list
   carrying the fields above. Returning `None` must leave current behaviour exactly
   as it is today - the tool has to keep working on sessions recorded before the
   hooks were installed.

2. **Wire it in `load_context_files`.** Where a hook fact exists for a path, it
   wins over the path convention. Concretely:
   - lines 570-571 (global `CLAUDE.md`, `AGENTS.md`)
   - line 595 (project `CLAUDE.md`, `AGENTS.md`, `AGENTS.override.md`)
   - line 606 (`.claude/rules/*.md`) - **this is the one that is actually wrong
     today.** A rule present on disk but absent from the hook log was not loaded:
     `loaded=False`, which routes its blocks to `not-loaded` instead of `dormant`.

   Carry `memory_type`, `load_reason`, `globs` and `trigger_file_path` onto the file
   record and surface them in the Context files panel. "This rule loaded because
   Claude touched `src/index.test.ts`" is the sentence worth showing.

3. **Add a `session_id` argument** so `build_real_view.py` can find the matching
   ctxlog file. The transcript filename is already the session UUID, so derive it
   from `--transcript` / `--session` rather than adding a flag.

### Do not

- Do not replace transcript ingestion with hooks. The `trace` dict needs
  `all_assistant_text` for the loose-keyword fallback in `assess_block` and for
  `_moments_for_read_driven` / `_find_intent_before`, which depend on assistant
  commentary *between* tool calls. The `Stop` hook exposes `last_assistant_message`
  per turn, which is close but misses intra-turn text. Hooks feed loading facts;
  the transcript keeps feeding the trace.
- Do not parse the transcript JSONL in the adapter. It already has one parser.

### Acceptance

- A `.claude/rules/style.md` with `paths: ["**/*.css"]` frontmatter, in a session
  that touched no CSS, reports `not-loaded` with all its blocks, not `dormant`.
- The same rule in a session that edited a `.css` file reports loaded, with
  `load_reason: path_glob_match` and the triggering file named.
- A session with no ctxlog log produces byte-identical output to before.

---

## Task 3: compaction fence

**Goal:** stop scoring blocks against turns where their file was not resident.

### Background

At compaction, anything loaded from disk at startup is re-injected and anything
that arrived through the conversation is folded into a summary. Project-root
`CLAUDE.md` and unscoped rules survive because they reload. Path-scoped rules do
not, until Claude reads a matching file again. Skill bodies are re-injected but
truncated to a per-skill cap, and the oldest invoked skills are dropped once the
total budget is exceeded.

`ctxlog.py` records `PreCompact` and `PostCompact` with their `trigger`. The
transcript also carries compaction entries; prefer the hook records when available
since they are unambiguous.

### Changes

1. Treat each compaction as a turn boundary in `split_into_turns` (line 238).
2. Track per-turn residency per file. After a compaction, a file whose
   `load_reason` was `path_glob_match` is non-resident until a subsequent
   `InstructionsLoaded` with `load_reason: compact` or a fresh lazy load says
   otherwise.
3. In the per-turn loop, skip assessment for non-resident files rather than scoring
   them. `combine_verdicts` already collapses per-turn statuses, so a block resident
   in turns 1-3 and evicted for 4-8 is judged only on 1-3.
4. Show the compaction boundary in the timeline with the count of files that went
   non-resident.

### Acceptance

- A session that compacted mid-run, containing a path-scoped rule loaded before the
  boundary and never re-triggered: that rule is assessed only against pre-boundary
  turns, and the timeline shows the boundary.

---

## Invariants

- Single-turn sessions with no truncation, no ctxlog log and no compaction must
  produce byte-identical HTML. This is the regression test for all three tasks.
- The `ignored` > `used` > `used-partial` precedence in `combine_verdicts` is
  deliberate: a violation in any turn must not be averaged away. Do not reorder it.
- Never promote a block into `undelivered` or demote a file to `loaded=False` on
  missing data. Absence of evidence routes to the existing behaviour.
- `predicates` in `derive_predicates` (line 748) and everything in the moments
  machinery (lines 906-1376) should not need to change. If a task seems to require
  editing them, stop and say so - it means the design above is wrong.

## Appendix A: ctxlog.py

Single-file Python collector, stdlib only. `install --write` merges eight hook
events into `~/.claude/settings.json` with a backup, idempotently. Log lands in
`~/.claude/ctxlog/<session_id>.jsonl`.

It writes nothing to stdout by design: on `SessionStart` and `UserPromptSubmit`,
Claude Code feeds hook stdout into the model's context, so a chatty collector would
contaminate the measurement. `collect` always exits 0 so a bug in it cannot stall a
session. Keep both properties if you modify it.

For Task 3 you may want `Bash|Edit|Write` added to its `PostToolUse` matcher and a
`Stop` hook for `last_assistant_message`. Both are one-line changes in
`hook_block()`.
