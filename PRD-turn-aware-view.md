# PRD: Turn-aware Session View

## Problem Statement

A single Claude session frequently contains many distinct user prompts and agent answers — five different questions in one `.jsonl` is normal, not an edge case. The real-view tool currently treats each session as one logical Q&A:

- The run-bar header shows one prompt per session (`first_real_user_prompt`), even when the user asked five different things.
- File Activity, Run Timeline, block status totals, and context-file verdicts all aggregate across the entire session.
- The "How the agent ended up here" timeline does some local scoping (it walks back to the nearest user prompt for a given Read/predicate fire), but every other panel is session-level.

The result: when a user investigates a specific question — for example, "did the agent use my brand-voice skill when I asked about brand voice?" — they see a verdict that mixes evidence from every turn in the session. The signal they came for is buried under aggregate noise. For long, multi-turn sessions the tool stops being useful as an investigative instrument.

## Solution

Slice each session into its constituent turns and let the user inspect any individual turn (or the whole session) with the same panels they have today.

A **turn** is the span from one real user message up to (but not including) the next real user message. Tool-result user messages, `<local-command-caveat>` messages, and meta messages do not start a new turn. Slash-command wrappers (`<command-name>` + `<command-args>`) do.

A **Turn picker** appears in the run-bar alongside the existing session picker. Its options are:

- **All turns** (default) — identical to today's behaviour. Aggregate counts, aggregate file activity, aggregate verdicts. This preserves backward compatibility for users who don't yet think in turns.
- **Turn 1 of N**, **Turn 2 of N**, … — each option scopes Block Inspector verdicts, Run Timeline, File Activity, and the per-block "How the agent ended up here" moments to that turn only.

Duplicate detection stays session-scoped (it's about file content overlap across the whole investigation, not per-turn behaviour) with a small label clarifying its scope.

A scope badge near each verdict makes it visually obvious whether you're looking at "Turn 3 of 5" evidence or "All turns (aggregated, 5 turns)" evidence.

## User Stories

1. As an investigator, I want to see how many turns a session contains, so that I know whether aggregate stats are meaningful.
2. As an investigator, I want a Turn picker next to the session picker, so that I can narrow the view to one Q&A inside a long session.
3. As an investigator, I want "All turns" to be the default selection, so that the tool behaves exactly like today until I opt in to per-turn slicing.
4. As an investigator, I want each turn option to show a short preview of that turn's user prompt, so that I can find the question I care about without reading the full transcript.
5. As an investigator, I want each turn to show its own start time and duration, so that I can see how long the agent took on that specific question.
6. As an investigator, I want Block Inspector verdicts to recompute against only the active turn's events, so that a "Skill used: yes/no" answer reflects only the turn I'm asking about.
7. As an investigator, I want the Run Timeline to show only the active turn's tool calls, so that the timeline I read corresponds to the verdict I just saw.
8. As an investigator, I want File Activity (reads / edits) to be filtered to the active turn, so that I can answer "which files did the agent touch when answering this question?".
9. As an investigator, I want the block status summary (counts of used / not-used / unclear) to match the active turn, so that totals never disagree with the panel they summarise.
10. As an investigator, I want a visible scope badge on every verdict, so that I cannot mistake an aggregated verdict for a turn-scoped one.
11. As an investigator, I want the "How the agent ended up here" moments timeline to remain scoped to the turn that contains the firing Read/predicate, so that TRIGGER cards are never pulled from an unrelated turn.
12. As an investigator, I want duplicate detection to remain session-scoped, so that I can still see content overlap between files even when I'm looking at a single turn.
13. As an investigator, I want the duplicates panel to be labelled "session-scope", so that I'm not confused by it ignoring my Turn picker.
14. As an investigator, I want the run-bar header prompt to update to the active turn's prompt when I pick a turn, so that the header always reflects the active scope.
15. As an investigator, I want sessions with exactly one turn to look identical to today (no extra picker chrome, no scope badges), so that the simple case stays simple.
16. As an investigator, I want switching sessions to preserve "All turns" as the default scope, so that I'm not jumped into Turn 1 of an unfamiliar session.
17. As an investigator, I want the URL or some persistable handle to encode the active turn, so that I can share a link to "session X, turn 3" with a colleague. (Nice-to-have; see Out of Scope.)
18. As an investigator, I want `/clear` mid-conversation to be treated as a turn boundary (not a session split), so that the file boundary stays aligned with the `.jsonl` on disk.
19. As an investigator, I want tool-result user messages to never start a new turn, so that turn counts reflect human prompts, not internal plumbing.
20. As an investigator, I want slash-command invocations (`<command-name>`/`<command-args>` wrappers) to count as turns, so that `/loop`, `/graphify`, etc. show up as their own slices.
21. As an investigator, I want each turn's verdict for a context-file block to indicate "this block was loaded but not referenced in this turn", so that I can distinguish loaded-and-used from loaded-but-cold-on-this-question.
22. As an investigator, I want the moments timeline of a per-turn verdict to never reach earlier turns for its TRIGGER card, so that I cannot be misled by a TRIGGER from a previous question.
23. As an investigator, I want the aggregate "All turns" view to sum counts honestly (sum of per-turn counts, not double-counted), so that aggregates are trustworthy.
24. As an investigator, I want generation of the static HTML to pre-compute every turn's data, so that switching turn in the UI is instant and offline-safe.
25. As an investigator, I want existing one-shot sessions in old reports to keep working when I regenerate, so that no data migration is needed.
26. As a tool maintainer, I want a single pure function that defines turn boundaries, so that turn semantics are not silently re-implemented in three places.
27. As a tool maintainer, I want the existing assessment functions (`assess_block`, `assemble_moments`, `file_activity`, etc.) to keep their input shape, so that turn-awareness is achieved by feeding them a sliced bundle rather than rewriting them.
28. As a tool maintainer, I want per-turn data to be addressable by a stable turn id (e.g. `turn-<index>`), so that the UI and any future deep links have something to anchor on.
29. As an investigator, I want the Turn picker to show the count of tool calls per turn next to each option, so that I can spot the heavyweight turn at a glance.
30. As an investigator, I want a keyboard-friendly way to step through turns (e.g. previous/next), so that I don't have to mouse into the dropdown for every turn.

## Implementation Decisions

**Turn boundary definition.** A new pure function `split_into_turns(events)` is the single authority on turn semantics. Boundary rule: a new turn starts at every `user`-typed event whose message is **not** a tool-result and **not** a meta/caveat wrapper. Slash-command wrappers (`<command-name>` / `<command-args>`) **do** start a turn. Tool-result user messages and `<local-command-caveat>` content do **not**. The function returns an ordered list of turn descriptors `{index, startEventIdx, endEventIdx (exclusive), userPrompt, startTime, endTime}`.

**Slicing primitive.** A second pure function `turn_slice(events, calls, asst_segs, turn)` returns turn-scoped versions of the four bundles already used downstream. `calls` and `asst_segs` are filtered by their event index falling within `[startEventIdx, endEventIdx)`. The returned tuple has the same shape as the existing per-session inputs.

**Existing assessment functions are unchanged.** `assess_block`, `assemble_moments`, `file_activity`, `chronological_segments`, `build_trace`, `build_timeline` continue to consume a single bundle. They are simply called once per turn (and once for the aggregate). This is a deliberate "deep-module" choice: we localise the new concept (turns) inside two new functions and let the rest of the pipeline stay turn-agnostic.

**Verdict aggregation.** For the "All turns" scope, per-turn verdicts are combined with this rule:
- A block is "used" at session scope if it is "used" in **any** turn.
- A block is "not used" only if it is "not used" in **every** turn.
- Otherwise it is "unclear" / "mixed".

This is computed from per-turn verdicts rather than re-running the assessor on the full session, so aggregates and per-turn views can never disagree by construction. (Backward note: a single-turn session produces an identical verdict either way.)

**Pipeline change in `process_session`.** After loading events/calls/segments, the function now:
1. Calls `split_into_turns(events)`.
2. For each turn: slices bundles, runs the existing pipeline, stores a per-turn record.
3. Computes the aggregate "All turns" record from the per-turn records (counts summed; verdicts combined per the rule above; timeline = concatenation; file activity = merged counters).
4. Runs `compute_duplicates` once at session scope (unchanged).

**Output schema (HTML data).** `data.perSession[id]` gains:
- `turns`: an array of `{ id, index, userPrompt, promptPreview, startTime, endTime, durationSec, counts, contextFiles, timeline, fileActivity }`. Each entry has the **same shape** as today's per-session payload.
- `turnCount`: integer.

The existing top-level `counts`, `contextFiles`, `timeline`, `fileActivity`, `duplicates` keys are retained and represent the "All turns" aggregate. This is what guarantees backward compatibility: an older UI sees today's data; the new UI prefers `turns[activeIndex]` when a specific turn is picked.

**UI contract.**
- A new `activeTurn()` accessor returns either the picked turn's record or the aggregate record.
- All panels (Block Inspector, Run Timeline, File Activity, block status summary) read from `activeTurn()` instead of `active()`.
- The Duplicates panel continues to read from session scope and renders a "session-scope" label.
- The Turn picker is a sub-selector beneath the session row, with options "All turns (default)" + "Turn 1 — <preview>" … "Turn N — <preview>". Each option shows the turn's tool-call count.
- Each verdict carries a small scope badge: either "All turns (N)" or "Turn k of N".
- For sessions with `turnCount === 1`, the picker and badges are hidden — the view is byte-identical to today.

**Default selection.** "All turns" on initial load. Switching sessions resets the picker to "All turns".

**Moments scoping.** `_moments_for_read_driven` and friends already walk back to the nearest user prompt before the firing event. When called with a turn-sliced bundle, the search space is naturally bounded by the turn — TRIGGER cards cannot leak across turn boundaries. This is verified rather than re-implemented.

**`/clear` handling.** Treated as a turn boundary, not a session split. The `.jsonl` boundary stays the session boundary. If `/clear` produces a meta event, the next real user message after it starts a new turn under the existing rule, so no special case is needed.

**Performance.** All turn data is pre-computed at HTML generation time. Reports are static; the UI is a pure picker. This is acceptable because turn count per session is small (typically <20).

## Testing Decisions

**What makes a good test here.** Tests assert observable behaviour — given a set of events, the boundary function returns the expected turn ranges; given a sliced bundle, an assessor returns the expected verdict. Tests do **not** assert on internal data structures, function call counts, or HTML markup details. The deep modules (`split_into_turns`, `turn_slice`, the verdict-aggregation rule) have small, stable interfaces and are the right test surface.

**Modules to test.**

1. **`split_into_turns(events)`** — primary target. Cases: zero turns (empty), one turn (today's typical short session), many turns (multi-question session), tool-result user messages between assistant messages must not start turns, meta/caveat messages must not start turns, slash-command wrappers must start turns, `/clear` mid-session produces a turn boundary at the next real prompt.
2. **`turn_slice(events, calls, asst_segs, turn)`** — given a synthetic events list with known indices, returns the right subset of `calls` and `asst_segs`. Boundary inclusivity is the load-bearing detail.
3. **Verdict aggregation rule** — a small pure function that combines per-turn verdicts into an "All turns" verdict. Cases: all-used → used; all-not-used → not-used; mixed → unclear; single-turn passthrough.
4. **End-to-end smoke**: a fixture transcript with three known turns, run through `process_session`, asserts `turnCount === 3` and that per-turn `counts.toolCalls` sum to the aggregate `counts.toolCalls`.

**Prior art.** The repo doesn't currently ship a unit-test suite for `build_real_view.py`. We follow the same lightweight style used elsewhere in similar tooling: a `tests/` folder with pytest-style functions, fixture transcripts checked in as small `.jsonl` files. No mocking — these are pure functions on plain data.

**Out of test scope.** The HTML/JS UI layer is not unit-tested; it's exercised manually by regenerating reports against known fixtures and clicking through. Snapshot-testing the HTML is explicitly avoided because it couples tests to markup.

## Out of Scope

- **Per-turn duplicate detection.** Duplicates are a content-overlap concept across the whole investigation; sharding them by turn loses signal. Stays session-scoped.
- **Splitting one `.jsonl` into multiple "logical sessions"** (e.g. on `/clear`). The on-disk file remains the unit of session identity; `/clear` is a turn boundary, not a session split.
- **Deep-link / URL encoding of the active turn.** Listed as a user story (#17) for completeness but deferred to a follow-up; the static HTML doesn't currently encode any state in the URL.
- **Cross-turn diffing** (e.g. "show me what changed between turn 2 and turn 4"). Out of scope; user can switch the picker manually.
- **Re-architecting the assessors to be turn-native.** They stay turn-agnostic and we feed them sliced bundles. Turn-native rewrites are explicitly avoided.
- **Live / streaming view.** Reports remain static.
- **Sub-agent / sidechain transcripts being treated as their own turns.** Out of scope; sidechain detection is unchanged.

## Further Notes

- The two design alternatives the user weighed (full turn-aware view vs. per-turn evidence in moments only) were considered. Recommendation: **full turn-aware view**. Justification: the user's stated investigative goal ("did the agent use my brand-voice skill when I asked about brand voice?") is meaningful only when the *verdict itself* is turn-scoped. Keeping rollups session-level while only narrowing moments would still display a "yes/no/unclear" badge that aggregates across unrelated turns — which is the exact failure mode the user described.
- The "deep module" extraction (`split_into_turns` + `turn_slice`) is the load-bearing design choice. It keeps turn semantics in one place, leaves every existing assessor untouched, and makes the new concept independently testable. If a future iteration wants to redefine turn boundaries (e.g. treating `/compact` as a boundary), only one function changes.
- Backward compatibility is preserved at three layers: (1) the data schema retains today's top-level keys as the aggregate; (2) the UI hides turn chrome when `turnCount === 1`; (3) the default picker value is "All turns".
- Visual indicator wording for the scope badge: "All turns (N)" and "Turn k of N". Short, unambiguous, and identifies the aggregation cardinality so a "used" verdict on an "All turns (5)" badge cannot be confused for a focused single-turn finding.
- Open question resolution: turn picker is a **sub-selector beneath the session row** (not a separate top-level dropdown, not radio buttons) — chosen because it keeps two related selectors visually grouped without crowding the run-bar header.
