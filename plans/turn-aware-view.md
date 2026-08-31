# Plan: Turn-aware Session View

> Source PRD: [../PRD-turn-aware-view.md](../PRD-turn-aware-view.md)

## Approach

TDD throughout. Every phase starts by writing failing tests (red), then implements until they pass (green). No implementation code is written before its tests exist.

The load-bearing design choice is the "deep module" extraction: turn semantics live in two new pure functions (`split_into_turns`, `turn_slice`) and existing assessors stay turn-agnostic, fed sliced bundles. The HTML+inline-JS report is regenerated from Python; pre-compute every turn at generation time so the UI is a pure picker.

## Architectural decisions

Durable decisions that apply across all phases:

- **Turn boundary rule**: a new turn starts at every `user`-typed event whose message is not a tool-result and not a meta/caveat wrapper. Slash-command wrappers (`<command-name>` / `<command-args>`) start a turn. `/clear` is a turn boundary, not a session split.
- **Turn id**: stable string `turn-<index>` (zero-based or one-based — pick one and stick with it across data + UI).
- **Data schema**: `data.perSession[id]` gains `turns: [{ id, index, userPrompt, promptPreview, startTime, endTime, durationSec, counts, contextFiles, timeline, fileActivity }]` and `turnCount`. Existing top-level `counts`, `contextFiles`, `timeline`, `fileActivity`, `duplicates` keys are retained as the "All turns" aggregate — older UI keeps working.
- **Verdict aggregation rule**: a block is "used" at session scope if used in any turn; "not used" only if not used in every turn; else "unclear". Aggregates derive from per-turn verdicts (never re-assessed from the full session) so the two views can never disagree.
- **Duplicates scope**: session-scoped, unchanged. UI labels it as such.
- **Default scope on load and on session switch**: "All turns".
- **Single-turn rendering**: when `turnCount === 1`, picker chrome and scope badges are hidden; output is byte-identical to today.

---

## Phase 1: Turn primitives + per-turn data in the report payload

**User stories**: 1, 5, 18, 19, 20, 23, 24, 25, 26, 27, 28

### Tests (write first — red)

Pytest under `tests/`, with small `.jsonl` fixtures of synthetic transcripts.

- `split_into_turns` returns `[]` for empty events.
- Single user prompt → exactly one turn covering the full event range.
- Multi-prompt transcript → N turn descriptors with correct `(startEventIdx, endEventIdx)` pairs and ascending non-overlapping ranges that partition the event list.
- A `user` event whose content is a tool-result does **not** start a new turn.
- A `<local-command-caveat>` user message does **not** start a new turn.
- A `<command-name>`/`<command-args>` slash-command wrapper **does** start a new turn.
- `/clear` mid-session: the next real user prompt after `/clear` starts a new turn (no special case needed beyond the boundary rule).
- `turn_slice(events, calls, asst_segs, turn)` returns calls/segments whose event index lies in `[startEventIdx, endEventIdx)` — verify boundary inclusivity at both ends.
- End-to-end smoke: a 3-turn fixture run through `process_session` yields `turnCount === 3`, and per-turn `counts.toolCalls` sum to the aggregate `counts.toolCalls`.
- Backward-compat smoke: a 1-turn fixture yields `turnCount === 1` and identical aggregate values to pre-change output for `counts`, `fileActivity`, and `contextFiles` shape.

### Implementation (green)

Add two pure functions in `build_real_view.py`:

1. `split_into_turns(events) -> list[TurnDescriptor]` — single authority on turn semantics. Returns ordered descriptors `{index, startEventIdx, endEventIdx, userPrompt, startTime, endTime}` partitioning the event list.
2. `turn_slice(events, calls, asst_segs, turn) -> (events_slice, calls_slice, asst_segs_slice)` — filters `calls` and `asst_segs` by event index falling in `[startEventIdx, endEventIdx)`. Returned tuple has the same shape as today's per-session inputs so existing assessors consume it untouched.

Wire into `process_session`:

1. Call `split_into_turns(events)`.
2. For each turn: slice bundles, run the existing pipeline (`build_trace`, `assess_block` over context files, `assemble_moments`, `file_activity`, `build_timeline`), store a per-turn record matching today's per-session payload shape.
3. Compute the "All turns" aggregate from per-turn records: counts summed, file activity merged counters, timeline = concatenation. Verdict aggregation lands in Phase 3 — for now the aggregate keeps using today's session-level assessors so this phase introduces no behaviour change at the session level.
4. Emit `turns[]` and `turnCount` in `data.perSession[id]`. Keep all existing top-level keys.

### Acceptance criteria

- [ ] `tests/` directory with pytest fixtures and tests above; all green.
- [ ] `split_into_turns` and `turn_slice` are pure, no I/O, called from one place.
- [ ] Regenerating a report against an existing transcript produces identical aggregate `counts`, `fileActivity`, and `contextFiles` verdicts to the pre-change run.
- [ ] New `turns[]` array is present in `data.perSession[id]` with one entry per turn, each shaped like today's per-session payload.
- [ ] `turnCount` is present and matches `len(turns)`.

---

## Phase 2: Turn picker UI + scope-aware panels

**User stories**: 2, 3, 4, 6, 7, 8, 9, 14, 15, 16, 29, 30

### Tests (write first — red)

UI is exercised manually (per PRD: no HTML snapshot tests). Add a small Python-side test that the per-turn payload contains the fields the UI binds to:

- Each `turns[i]` has `promptPreview` (short, truncated), `durationSec`, `counts.toolCalls`, `userPrompt` (full), `startTime`, `endTime`.
- `id` is `turn-<index>` (or chosen stable form) and is unique within the session.

Manual verification checklist (recorded in the PR description, not automated):

- Picker appears beneath the session row for multi-turn sessions; absent for `turnCount === 1`.
- "All turns" is selected on initial load and after switching sessions.
- Selecting a turn updates Block Inspector, Run Timeline, File Activity, and the status-summary counts together — never out of sync.
- Run-bar header prompt updates to the active turn's prompt when a turn is picked.
- Each picker option shows the turn's tool-call count and a short prompt preview.
- Keyboard prev/next navigation steps through turns without mouse interaction.

### Implementation (green)

In the inlined HTML/JS:

- Add `activeTurn()` accessor that returns the picked turn's record or the aggregate (when "All turns").
- Add a sub-selector under the session row listing "All turns (default)" + "Turn k — <preview> (Ncalls)" for each turn.
- Retarget Block Inspector, Run Timeline, File Activity, and the block-status summary to read from `activeTurn()` instead of `active()`.
- Update the run-bar header prompt to bind to active scope's prompt.
- Hide picker chrome and scope-related markup when `turnCount === 1`.
- Reset picker to "All turns" on session switch and on initial load.
- Bind `[` / `]` (or arrow keys) to step prev/next through turns.

### Acceptance criteria

- [ ] Multi-turn session shows picker; single-turn session looks byte-identical to pre-change output.
- [ ] Switching turn updates all four panels in lockstep against the same underlying record.
- [ ] Initial load and session switch land on "All turns".
- [ ] Each turn option shows tool-call count and prompt preview.
- [ ] Prev/next keyboard navigation works.
- [ ] Run-bar prompt reflects active scope.

---

## Phase 3: Verdict aggregation rule + scope badges + per-turn context-file labels

**User stories**: 6, 10, 11, 21, 22

### Tests (write first — red)

- Verdict aggregation rule (pure function) cases:
  - all turns "used" → "used".
  - all turns "not used" → "not used".
  - mixed → "unclear" / "mixed".
  - single-turn passthrough returns the per-turn verdict unchanged.
- Per-turn context-file labelling: a block that is loaded but has no read/reference fire in the active turn produces a "loaded but not referenced in this turn" verdict — distinct from "not loaded" and from "used".
- Moments scoping: with a sliced bundle, `_moments_for_read_driven` and friends never produce a TRIGGER card whose source segment lies outside the active turn's event range. Synthetic two-turn fixture where turn 1 contains the only intent text and turn 2 contains the firing Read; per-turn moments for turn 2 must not pull turn 1's TRIGGER.

### Implementation (green)

- Extract verdict combine rule as a small pure function; use it to compute the aggregate "All turns" verdicts from per-turn verdicts in `process_session`. Aggregate no longer calls `assess_block` against the full session — it derives strictly from per-turn results.
- Add per-turn "loaded but not referenced this turn" verdict for context-file blocks; surface it in `turns[i].contextFiles[*].verdict` (or a sibling field) so the UI can render the distinction.
- Render a scope badge on every verdict in the UI: "All turns (N)" or "Turn k of N". Hidden when `turnCount === 1`.
- Verify (by test, not re-implement) that turn slicing alone is sufficient to keep TRIGGER cards inside their turn — `_moments_for_read_driven` already walks back to the nearest user prompt before the firing event.

### Acceptance criteria

- [ ] Aggregate verdicts in the report match the combine rule applied to per-turn verdicts.
- [ ] Aggregate and per-turn verdicts can never disagree by construction (aggregate is derived).
- [ ] Context-file blocks distinguish "loaded but not referenced in this turn" from "not loaded" and from "used".
- [ ] Scope badge is visible on every verdict in multi-turn sessions; hidden in single-turn sessions.
- [ ] TRIGGER cards in per-turn moments timelines never reference segments from other turns (verified by fixture test).

---

## Phase 4: Duplicates session-scope label & polish

**User stories**: 12, 13

### Tests (write first — red)

- Duplicates output is unchanged when switching turns: it always reflects session-scope content overlap regardless of active turn.
- Manual: duplicates panel renders a visible "session-scope" label and ignores the Turn picker.

### Implementation (green)

- `compute_duplicates` continues to run once at session scope; emit a `scope: "session"` field if the UI needs it for labelling.
- UI: duplicates panel reads from session scope (not `activeTurn()`) and renders a "session-scope" label/chip near its header.

### Acceptance criteria

- [ ] Duplicates panel content does not change when picking different turns.
- [ ] Duplicates panel shows a "session-scope" label.
- [ ] No regression in existing duplicates verdicts on a known fixture.

---

## Out of scope (per PRD)

- Per-turn duplicates, splitting `.jsonl` on `/clear`, deep-link/URL encoding (story 17), cross-turn diffing, turn-native assessor rewrites, live/streaming view, sidechain-as-turn.
