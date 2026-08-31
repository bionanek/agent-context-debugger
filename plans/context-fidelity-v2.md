# Plan: Context Fidelity v2

> Source: correctness analysis of `build_real_view.py` verified against 206 real transcripts, plus the unbox-ai mechanism review (both 2026-08-31, conversation record). No standalone PRD file exists; the findings below are restated where a phase depends on them.

## Approach

TDD throughout. Every phase starts by writing failing tests (red), then implements until they pass (green). No implementation code is written before its tests exist.

The repo already has a pytest suite under `tests/` with jsonl fixtures — new tests follow that pattern: build a small fixture transcript exercising the exact shape found in real data, assert on the pipeline's JSON output (not the HTML). Verifying a phase = `pytest` green + regenerate `agent-context-ide-real.html` and eyeball the affected panel.

## Architectural decisions

Durable decisions that apply across all phases:

- **Stdlib-only, single-file HTML output** — unchanged hard requirements. No dependencies, all UI inside `HTML_TEMPLATE`.
- **Data shape**: keep the `summary` (cheap, for the picker) vs `per_session` (heavy, for the active view) split. New heavy data (token series, compare payloads) goes in `per_session`; new cheap counters go in `summary`.
- **Status taxonomy** grows by one member: `possibly-referenced` joins the USED family (`used`, `used-partial`, `ignored`) as the weakest usage signal. `combine_verdicts` ranks it below `used-partial` and above the NOT-USED family. Existing statuses keep their meanings so old sessions render identically where behavior didn't change.
- **Block IDs stay stable** (`file_slug + index + title-slug`) — every phase must preserve them; the CLI and compare features address blocks by these IDs.
- **Token truth source**: the `usage` object on assistant events is ground truth. Char-based numbers may only appear as explicitly-labeled estimates (per-block attribution), never as the headline figure. Session-level and file-level figures come from `usage`.
- **Turn boundary definition** (extends the turn-aware PRD): a turn starts at a real user prompt, where "real" now includes list-content messages carrying text, and excludes interrupt markers, local-command wrappers, and stdout wrappers. Compaction boundaries unchanged.
- **Comparison alignment**: two sessions align turn-by-turn on tool-call name sequences using `difflib.SequenceMatcher` (stdlib LCS). Never align by index.
- **CLI contract**: read-only, TTY-agnostic, bounded output (~1500 chars per field) with the exact follow-up command printed for anything elided. Addressing scheme is `<session-prefix> [turn-N] [block-id]`.

Docs reviewed: `CLAUDE.md` needs updates in several phases (noted per phase); it is also already stale — it claims "no tests" while `tests/` exists, fixed in Phase 1. `PRD-turn-aware-view.md` and `changes/HANDOFF-context-fidelity.md` are historical records and stay untouched.

---

## Phase 1: Prompt & turn correctness

**Findings covered**: image-paste prompts invisible (174 real cases); interrupts and local commands create phantom turns; stdout wrappers counted as prompts.

### Tests (write first — red)

- A fixture session whose only prompt is `[{type:"image"...},{type:"text"...}]` list content produces one turn with that text as `userPrompt`, and the session summary shows the prompt preview.
- A list-content message containing only `[Request interrupted by user]` does not start a turn and is not a prompt.
- A `<command-name>/model</command-name>` wrapper for a local command (one with `<local-command-stdout>` in the same or adjacent message) does not start a turn; a skill-invoking wrapper (e.g. `/graphify`) still does.
- A string message containing `<local-command-stdout>` is never a turn boundary or prompt.
- Existing fixtures in `tests/` still pass unchanged (regression gate: string prompts, tool-result messages, meta messages behave exactly as before).

### Implementation (green)

Extend the single prompt classifier (the one shared by turn splitting and first-prompt extraction — they must stay in lockstep) to: extract and join `text` items from list content; reject interrupt markers and stdout wrappers; distinguish local-command wrappers from skill/command wrappers. Every consumer of the user prompt (run-bar, trigger detection, turn picker labels) benefits without further change.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — the "There are no tests" claim is already false; replace with a line describing the pytest suite and the fixture-transcript pattern. Update the pipeline section 3 description to mention list-content prompt handling.

### Acceptance criteria

- [ ] A real session starting with a pasted-screenshot prompt shows the prompt text in the run-bar and correct turn count
- [ ] `/model` invocations no longer appear as turns in the turn picker
- [ ] All pre-existing tests pass without modification

---

## Phase 2: Skill identity & loading

**Findings covered**: plugin skill names (`datadog:ddsetup`) truncated at the first colon, then collapsed by dedupe so skills vanish; skill "loaded" ignores Skill tool calls; substring/prefix prompt matching gives false triggers.

### Tests (write first — red)

- A skill-listing attachment containing `- datadog:ddsetup: description...` yields a skill named `datadog:ddsetup` with the right description; five `datadog:*` skills yield five distinct entries.
- A session where the model calls the Skill tool with `skill: "implement-plan-workflow"` and the user never typed a slash command marks that skill loaded, with a trigger moment citing the tool call.
- A prompt containing `/cpanel` does not trigger the `cp` skill; a prompt starting with the bare word "commit" does not trigger the `commit` skill; a prompt containing `/commit` (word-boundary) does.
- Phantom (listing-only) entries for two different plugin skills of the same plugin do not dedupe into one.

### Implementation (green)

Parse listing lines by splitting at the last `: ` that terminates a plausible name token (name charset already known), keeping plugin prefixes intact. Resolve plugin skill files under the plugin skill roots as well as `~/.claude/skills`. Compute loaded-ness in priority order: Skill tool call in the trace → command wrapper → word-boundary `/name` match in the prompt. The moments builder already knows about Skill calls; the loaded flag must agree with it.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — pipeline section 4 ("Context-file loading"): note that skill loading is call-driven first, prompt-driven as fallback.

### Acceptance criteria

- [ ] Regenerated HTML shows all plugin skills from the current listing with full names
- [ ] A session with a model-invoked skill shows it as loaded with the invocation as evidence
- [ ] No false "loaded" from substring prompt matches

---

## Phase 3: Small stat & discovery fixes

**Findings covered**: "user messages" stat inflated ~10× by tool results; cwd encoding misses `.` so dotted paths find no transcripts; sidechain first-line check is dead code.

### Tests (write first — red)

- A fixture with 2 real prompts and 10 tool-result user messages reports `userMessages: 2` in both the session summary and counts.
- Encoding `/Users/x/my.app` yields the folder name Claude Code actually uses (`.` → `-`), verified to match the observed convention (`famigo/.claude/worktrees` → `famigo--claude-worktrees`).
- Transcript discovery ignores subdirectories (where subagent transcripts now live) and doesn't crash on first lines lacking `isSidechain`.

### Implementation (green)

Count user messages with the same classifier Phase 1 hardened (real prompts only). Fix the encoder to replace both `/` and `.`. Replace the first-line sidechain check with what the current layout warrants: top-level `*.jsonl` only, keeping a cheap whole-file `isSidechain` guard only if a real legacy sidechain fixture justifies it — otherwise delete it and say so in the docstring.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — pipeline section 1 (Discovery): correct the encoding description and the sidechain note.

### Acceptance criteria

- [ ] Session picker "user messages" matches a hand count of real prompts
- [ ] A project path containing a dot discovers its transcripts
- [ ] Discovery code contains no dead branches

---

## Phase 4: Real token usage

**Findings covered**: every displayed token number is `chars ÷ 4`; transcripts carry exact per-request `usage` (input, output, cache_read, cache_creation with 1h/5m tiers, thinking tokens) on 100% of assistant events — unused.

### Tests (write first — red)

- A fixture with known `usage` objects yields session totals: input, output, cache-read, cache-created, thinking — each the sum over assistant events.
- Per-turn slices report the same fields summed over only that turn's events.
- An assistant event missing `usage` (defensive) contributes zeros without crashing.
- A cache-reset signature (a request whose `cache_read` drops to ~0 while `cache_creation` spikes after a prior high `cache_read`) is flagged as a cache-break marker with its timestamp.

### Implementation (green)

Extract a per-request usage series during transcript parsing; sum into session-level and per-turn totals stored in `per_session` (series) and `summary` (totals). Surface in the UI: token totals in the summary strip with a cached-vs-fresh split, a token row per turn in the turn picker, and cache-break markers spliced into the run timeline (same mechanism as compaction rows). Replace the "~N tokens" session-level figures with real ones; leave per-block figures to Phase 5.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — architecture pipeline list gains a step ("usage extraction") between transcript parsing and context-file loading; the per-session vs summary convention paragraph gains the token fields.

### Acceptance criteria

- [ ] Summary strip shows real input/output tokens and cached share for the active session
- [ ] Each turn option shows its own token cost
- [ ] Cache breaks appear on the timeline where `usage` shows the prefix was repaid

---

## Phase 5: Token attribution

**Findings covered**: duplicate-panel costs are guesses; no notion of "resent every request"; the unbox-ai scaling trick (distribute reported input tokens over context items proportionally by size) makes file-level numbers honest.

### Tests (write first — red)

- Given context files of known char sizes and a request reporting N input tokens, per-file attributed tokens sum to N and are proportional to size, and are labeled `estimated: true` at block granularity.
- A file resident for all K requests of a session reports `sentCount = K` and cumulative cost = per-request attribution × K, split cached vs fresh using the request-level cache figures.
- Duplicate pairs report attributed token cost (both sides), replacing the `chars × sim ÷ 4` figure.
- A file that became non-resident after compaction (per existing residency logic) stops accruing from that request onward.

### Implementation (green)

Attribute each request's fresh input tokens across the context items known to be resident (context files + a remainder bucket for conversation history, so file numbers aren't inflated by chat growth). Roll up per file: attributed cost per request × times resent, cached vs fresh. Feed the duplicate panel and add a cumulative-cost column to the file tree (the "dead context with a price tag" view: unused blocks × resend count). Per-block figures derive from file figures by line share and are always labeled estimates.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — duplicate-detection pipeline step description: costs now derive from `usage` attribution, not char counts.

### Acceptance criteria

- [ ] Duplicate panel shows attributed real-token costs, not char estimates
- [ ] File tree shows cumulative cost (size × resends, cached/fresh split) per context file
- [ ] Attribution sums reconcile with session `usage` totals

---

## Phase 6: Honest verdicts

**Findings covered**: command-mention predicates always "match", so any block naming a command that ran scores `used`; keyword fallback (2 of 8 common words) scores `used`; duplicate classification calls almost everything `referenced`; disjoint read ranges claim contiguous delivery.

### Tests (write first — red)

- A block that merely mentions `git` in prose, in a session where git ran for unrelated reasons, scores `possibly-referenced` (not `used`), with the reason naming the weak-evidence basis.
- A block with a real trigger predicate that fired still scores `used`; a violated negative rule still scores `ignored`.
- A block whose only signal is loose keyword overlap scores `possibly-referenced`; a block with zero signal stays `unused`/`dormant` as today.
- Duplicate classification: a pair whose blocks only carry never-fired negative rules or mere command mentions classifies `redundant`; a pair with a genuinely fired predicate or strong topical reference classifies `referenced`.
- A file read as lines 1–100 and 1900–2000 marks blocks in 101–1899 `undelivered`; blocks inside either range assess normally.
- `combine_verdicts` ranks the new status: any `used` turn beats `possibly-referenced`; `possibly-referenced` beats every NOT-USED status.

### Implementation (green)

Tier the evidence: strong (trigger fired, path-table satisfied, end-of-message compliance, negative rule outcome) keeps the current statuses; weak (command mention, keyword overlap) can at most yield `possibly-referenced`. Apply the same tiers in duplicate classification. Store delivered line ranges as a list of intervals instead of one min–max span, and extend the undelivered check to gaps. Frontend: new status color/dot, filter chip, and help-popover entry; status counts include it.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — verdict pipeline step: document the two evidence tiers and the 7-status taxonomy.
- [`plans/turn-aware-view.md`](plans/turn-aware-view.md) — no edit (historical), but the combine rule change lands with tests proving the documented PRD invariant still holds ("used in any turn → used at session scope").

### Acceptance criteria

- [ ] Green "used" appears only with strong evidence; weak evidence is visibly softer in the UI
- [ ] Duplicate panel's `redundant` count becomes non-trivial on real sessions
- [ ] Partially-read files no longer score blocks the model never saw

---

## Phase 7: Session compare

**Findings covered**: no way to answer "I edited CLAUDE.md — did behavior change?"; unbox-ai's action-content alignment (LCS over tool-call sequences) prevents one extra step from cascading divergence.

### Tests (write first — red)

- Two fixture sessions identical except one inserted tool call align with exactly one unmatched turn-step; all later steps still pair up.
- The context diff between two sessions reports blocks added/removed/changed per context file (by block ID and title), and flags files whose on-disk content drifted between the sessions' timestamps.
- A compared pair with different first prompts is flagged ("different tasks — deltas may mislead").
- Compare payload appears in the baked JSON only when compare mode is requested (size guard: default builds stay byte-comparable to today's).

### Implementation (green)

Backend: for any two baked sessions, reduce each turn to its tool-call name sequence, align with `difflib`, and emit paired/unpaired steps plus deltas (tool calls, edits, tokens from Phase 4, verdict changes per block from Phase 6). Diff the two sessions' context files block-wise. Frontend: a Compare tab — pick session A/B, see aligned turn rows with divergence markers, context-block diff beside behavior diff. Computed at build time (no runtime recompute), opt-in via a `--compare` flag or lazily for the two selected sessions if payload size demands.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — Running section: new compare invocation; architecture list gains the compare step.

### Acceptance criteria

- [ ] Comparing two real sessions of the same task shows aligned steps with divergences marked
- [ ] The context-file diff sits next to the behavior diff in one view
- [ ] Default (non-compare) output size is unchanged

---

## Phase 8: CLI read-mode

**Findings covered**: the tool is browser-only; agents auditing their own context can't consume it. Block IDs are already stable and addressable — half the work.

### Tests (write first — red)

- `--query sessions` prints one bounded line per session (id, when, turns, tokens, prompt preview).
- `--query <session> turns` lists turns; `--query <session> turn-2 blocks` lists block IDs with statuses; `--query <session> <block-id>` prints the verdict, reason, and moments.
- Any field over ~1500 chars is elided with the exact command that returns the full value appended.
- Query mode writes no HTML, never opens a browser, and exits non-zero with a usable message for unknown IDs.

### Implementation (green)

A query path through the existing pipeline that skips HTML emission and prints plain text. Reuse the baked-JSON structures verbatim so CLI and HTML can never disagree. Address space: sessions by ID prefix, turns by `turn-N`, blocks by their stable IDs. Every listing is itself the discovery mechanism (outputs contain the IDs the next query needs).

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) — Running section: query-mode examples alongside the existing flags.

### Acceptance criteria

- [ ] An agent can go from zero knowledge to a specific block's verdict in three bounded commands
- [ ] Elided output always names the command for the rest
- [ ] No HTML side effects in query mode

---

## Phase 9: Rule compilation and code-based violation checking

**Findings covered**: prose rules currently get no real verdict, and the "never X" extractor treats code constructs as shell commands, producing false red violations on real rule docs (verified: 4 of 8 formic rule files carried phantom violations). Research and a live pilot both point at the same architecture: interpret each rule once, ahead of time, into a deterministic check; never let a model judge at analysis time.

### Pilot results (already run, informs this phase)

The translation prompt lives at [`prompts/translate-rules.md`](prompts/translate-rules.md) and was validated against four real formic rule docs:

| doc | checks | not checkable | hits on real source |
|---|---|---|---|
| frontend_mobx | 7 | 9 | 2 / 522 files |
| frontend_components_hooks_utils | 7 | 11 | 3 / 522 |
| frontend_styling_constants_config | 9 | 14 | 9 / 522 |
| general_coding_guidelines | 9 | 37 | 9 / 197 python |

69% of rules were correctly refused as not mechanically checkable, matching the ~60% figure published for real coding standards. Genuine violations were found (`cn(className, ...)` where the rule requires className last; `60000` where the rule requires digit separators; `# type: ignore` in six files). Two defects surfaced that this phase must fix by construction, described below.

### Tests (write first - red)

- A checks file whose self-tests fail under *this tool's* matcher is rejected at load, and its rules report `not-checkable` rather than being applied. (The pilot found a check that passed the generator's own verification but failed the consumer's, because the two disagreed on what `required_order` meant. The generator's self-assessment is not evidence.)
- Comment and string content is stripped centrally before any pattern runs: an identifier inside a `/* ... */` block spanning several lines produces no violation, including on continuation lines that carry no comment marker. (The pilot's per-regex comment guards handled only marker-prefixed lines and false-positived on a CSS comment.)
- A violation is reported only when the strict match and the match over normalised text agree; disagreement yields `unclear`, never a violation.
- Every reported violation carries a citable span: file path, the matched text, and the id of the check that fired. A candidate without a span is not reportable.
- A rule marked `not_checkable` renders as its own verdict, distinct from both used and violated, and never contributes a violation.
- An inline suppression at the violation site (the deliberate-exception marker) downgrades the finding to acknowledged. Real-world case from the pilot: a component deliberately uses `reaction()` against the rule, with a documented rationale in the file.
- A rule doc with no checks file falls back to mechanical extraction (backticked identifiers plus globs plus negation cues) and every resulting verdict is capped at low confidence.
- Checks are keyed by a hash of the rule's heading path plus its text, so an unchanged rule reuses its cached check and an edited rule invalidates it.

### Implementation (green)

Authoring time, outside the Python tool: a Claude Code step applies `prompts/translate-rules.md` to each rule doc and writes a checks JSON next to it. That file is a reviewable repo artifact, not a black box. The tool never calls a model.

Analysis time, stdlib only: load the checks files, gate them through their own self-tests, strip comments and strings, then match against the code the agent wrote (`Write` content and `Edit` new text), the shell commands it ran, and the paths it touched. Route strictly by the objects a rule names, never by its verbs.

The predicate vocabulary is closed and its semantics must be specified unambiguously in the prompt, since the pilot proved ambiguity there silently produces broken checks. Verdicts are three-state: `violated` (span required), `unclear`, `not-checkable`.

### Docs to update

- [`CLAUDE.md`](CLAUDE.md) - document the authoring step, the checks-file format, and the rule that the tool itself never calls a model.
- [`prompts/translate-rules.md`](prompts/translate-rules.md) - tighten the `required_order` definition and replace per-pattern comment guards with a note that stripping happens centrally.

### Acceptance criteria

- [ ] Zero violations reported on rule docs whose rules the session did not actually break
- [ ] Every red badge cites the exact line that triggered it
- [ ] Rules that cannot be checked say so, and are never silently treated as followed
- [ ] A checks file that fails its own self-tests cannot produce a verdict
- [ ] The tool runs offline with no dependencies, exactly as before
