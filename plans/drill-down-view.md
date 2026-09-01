# Plan: Drill-down Context View

> Design reference: interactive prototype, artboard "Variant 1 - drill-down"
> at https://claude.ai/code/artifact/f24afd30-7964-4de9-8327-01d6c3d3bcbe

## Approach

TDD throughout, same as [turn-aware-view.md](turn-aware-view.md): every phase starts with failing tests, then implements until green. Phases 2-4 are frontend-only and are verified by regenerating the HTML and clicking through it, since the template is not a stable contract and must never be asserted on.

The load-bearing decision is that **all new derived data is computed in Python and baked**, not computed in the frontend. `--query` renders only what is already baked so that the CLI and the page can never disagree; a rollup invented in JavaScript would break that guarantee the moment someone asks the CLI the same question.

Phase 1 is pure payload work and ships no UI. Phase 2 is the tracer bullet: a working four-level drill-down with placeholder rows. Phases 3-5 enrich it.

## Architectural decisions

Durable decisions that apply across all phases:

- **Scope of the change.** The drill-down replaces navigation *inside the Blocks view only*. The Timeline, Files, Duplicates and Compare tabs keep their current layout and keep reading `activeTurn()`.
- **The turn picker is removed; `activeTurnId` is not.** `activeTurnId` remains the app-wide scope variable that the other four tabs read. Descending into a turn in the drill-down sets it; ascending back to the session level resets it to `'all'`. Without this the tabs silently desync: you would drill into Turn 2, click Timeline, and see all turns.
- **Level is derived, never stored.** One state object `nav = {sessionId, turnId, filePath, blockId}` plus a single accessor that returns the deepest non-null level. No `currentLevel` variable to drift out of sync with the path.
- **Four levels, and a session-level entry point.** Sessions -> turns -> files -> blocks. `DATA.sessions` already carries everything the session list needs; no new session-level fetch.
- **Single-turn sessions skip the turn level.** Entering a session whose `turnCount === 1` descends straight to its file list, with the turn implied in the breadcrumb. Matches the existing rule that single-turn sessions get no picker chrome.
- **New payload fields are additive only.** Every existing key in `data`, `data.sessions[]`, `data.perSession[]` and each turn record keeps its current name, position and value. A test asserts this: the pre-change payload must be a subset of the post-change payload.
- **Active / Quiet is a baked classification, not a UI filter.** A file is *active* in a turn when it was read or edited in that turn, or when any of its blocks has a status in `{used, used-partial, ignored, possibly-referenced, undelivered}`. Everything else is *quiet*, including `not-loaded`. Both groups always render; there is no toggle.
- **Path joining happens once, in Python.** `file_activity` counts by the raw `file_path` from the tool input, which is absolute; `contextFiles[].path` is the display form (`~/.claude/CLAUDE.md`). Joining these in the frontend would silently fail and report every file as never touched. Normalise through the existing `_display_path` / `_short_path` helpers at bake time.
- **Deep links.** Location hash `#s=<session-prefix>&t=<turn-id>&f=<file-slug>&b=<block-id>`, read on load and rewritten on every navigation. This is PRD story 17, which the dropdown UI could not satisfy.

---

## Phase 1: Bake the per-file rollup

**Ships:** no visible change. The payload gains the fields the drill-down needs.

### Tests (write first - red)

New `tests/test_rollup.py`, in the existing in-memory event-builder style.

- A file read twice in a turn reports `activity.reads == 2` on that turn's record and `0` on a turn that did not read it.
- Activity joins correctly when the context file's path is the tilde display form and the tool call used the absolute path. This is the regression test for the path mismatch; assert on a `~/.claude/CLAUDE.md` file edited via its absolute path.
- A file with one `ignored` block classifies `active: true`.
- A file whose blocks are all `dormant` / `unused` classifies `active: false`.
- A file that was edited but whose blocks are all cold still classifies `active: true`.
- A `not-loaded` file classifies `active: false`.
- `rollup.statusCounts` sums to the file's block count, for every turn.
- `rollup.summary` picks the violation phrasing when any block is `ignored`, and the never-loaded phrasing when the file was not loaded.
- Additive-payload guard: build a payload for a fixture, and assert every key path present before the change is still present with the same value.

### Implementation (green)

In `_compute_payload`, after context files are assessed and `file_activity` has run, annotate each context-file record with:

```
"activity": {"reads": int, "edits": int}
"rollup": {
    "statusCounts": {status: count},
    "active": bool,
    "summary": str,
}
```

`summary` is chosen by first match, so it always names the most consequential thing that happened rather than a generic tally:

1. any `ignored` block -> `"N rules fired, M violated"`
2. else edited -> `"edited N times; K of T sections matched the trace"`
3. else read -> `"read this turn; K of T sections matched the trace"`
4. else any `used` / `used-partial` -> `"K of T sections matched the trace"`
5. else loaded -> `"in context, nothing referenced it"`
6. else -> `"on disk, never entered context"`

Add a `headline` string to each turn record and to each entry in `data.sessions` by the same first-match rule at its own level (`"5 rules violated"` / `"nothing violated"`).

Do not touch `assess_block`, `derive_predicates`, or the moments machinery. This phase only summarises verdicts that already exist.

### Acceptance criteria

- [ ] `pytest` green, including the additive-payload guard.
- [ ] `python3 build_real_view.py` produces a payload where every turn's context files carry `activity` and `rollup`.
- [ ] Regenerated HTML renders exactly as before, since nothing reads the new fields yet.

---

## Phase 2: Drill-down shell (tracer bullet)

**Ships:** the Blocks view navigates by drilling instead of by dropdown, end to end, with plain rows.

### Tests

Frontend, so no pytest. Verified by regenerating and clicking through. Add to the acceptance list rather than the suite.

### Implementation

In `HTML_TEMPLATE`:

1. Replace the `#turn-bar` markup and `renderTurnPicker` / `stepTurn` with a breadcrumb bar and a `nav` state object.
2. Add `currentLevel()` returning `'sessions' | 'turns' | 'files' | 'blocks'` from `nav`, and `navigate(patch)` which merges a patch, clears every deeper field, syncs `activeTurnId`, rewrites the hash, and calls `rerenderAll()`.
3. `renderBreadcrumb()` renders one clickable crumb per non-null level.
4. `renderAncestors()` renders the collapsed bar for each level above the current one, each clickable to pop back to it.
5. `renderLevel()` dispatches to one renderer per level. For this phase each renderer emits a plain list of rows with a title and a chevron.
6. Keep `renderDetail(blockId)` and the `#detail-pane` exactly as they are. Selecting a block at the deepest level calls it unchanged.
7. Delete `#session-select` and `#turn-select`, and the `.turn-bar` CSS that only they used.

The left `#file-tree` aside is removed from the Blocks view in this phase; the file list becomes a drill level. Its session card moves into the session-level ancestor bar.

### Acceptance criteria

- [ ] From a fresh open you can reach a block verdict in four clicks and return to any ancestor in one.
- [ ] Breadcrumb reflects the path at every level.
- [ ] Descending into a turn then switching to the Timeline tab shows that turn only. Returning to the session level and switching back shows all turns.
- [ ] A single-turn session opens straight at its file list.
- [ ] The detail pane still renders evidence, moments and rule checks unchanged.

---

## Phase 3: Level renderers and the Active / Quiet split

**Ships:** the view from the prototype.

### Implementation

- **Sessions level.** One row per `DATA.sessions` entry: prompt, id, when, duration, `headline`, and chips for turn count, tool calls, files edited.
- **Turns level.** One row per turn: `Message N`, prompt preview, duration, tool mix, `X of Y context files live`, and the top three status chips from the turn's counts. Row border goes red when the turn contains any `ignored` block.
- **Files level.** Two groups, `Active` and `Quiet`, each with a count in its header. Row shows the path, the baked `rollup.summary` as its subtitle, and up to three status chips. Quiet rows render at reduced opacity but stay clickable.
- **Blocks level.** Same split by the same rule applied to block statuses. Row shows the block title coloured by status, the block's `reason` as its subtitle, and its type tag.
- Preserve `statusFilter` and `loadFilter` as filters on the two deepest levels; drop `selectedFilePath`, which the file level now expresses structurally.

### Acceptance criteria

- [ ] On a real multi-turn session, the Files level shows a small Active group above a large Quiet group, and the counts add up to the turn's total context files.
- [ ] Every `rollup.summary` on screen says something specific to that file. A row reading like a template is a bug in Phase 1's first-match order, not a copy problem.
- [ ] Status chips at the turn level match the block-status totals you get after drilling in.

---

## Phase 4: Deep links, keyboard, and cross-tab scope

### Implementation

- Parse the hash on load; an unknown session, turn, file or block falls back to the nearest valid ancestor rather than erroring.
- Rewrite the hash on every `navigate()` with `history.replaceState`, so the back button is not flooded.
- `[` / `]` step between siblings at the current level; `Escape` ascends one level. Keep the existing shortcuts for the tab bar.
- Show the current scope in the other four tabs' headers using the existing `scopeBadgeHtml()`, so a turn-scoped Timeline is unmistakable.

### Acceptance criteria

- [ ] Copying the URL at a block and reopening it lands on the same block.
- [ ] A hash naming a deleted session opens at the session list instead of a blank pane.
- [ ] Timeline, Files and Duplicates headers show the active scope badge.

---

## Phase 5: Query-mode parity and docs

### Tests (write first - red)

Extend `tests/test_query.py`.

- `--query <sid> turn-N files` lists the turn's context files with their `rollup.summary` and active/quiet group.
- The listing prints the block-listing command for the next step down, matching the existing convention that each listing names the ids the next query needs.
- An unknown file id exits non-zero naming the command that lists valid ones.

### Implementation

- Add a `files` address to `run_query` between `turns` and `blocks`.
- Update the CLAUDE.md "Query mode" and "Architecture" sections: the drill-down levels, the new `activity` / `rollup` / `headline` fields, and the additive-payload invariant that replaces the old byte-identical-HTML invariant, which a deliberate UI change cannot satisfy.

### Acceptance criteria

- [ ] `pytest` green.
- [ ] `python3 build_real_view.py --query <sid> turn-0 files` prints the same grouping the page shows.
- [ ] CLAUDE.md describes the drill-down as the Blocks view's navigation.

---

## Risks

- **The per-file summary is the whole point of the File level and the easiest thing to get wrong.** If the first-match order is wrong, most rows collapse to "in context, nothing referenced it" and the level stops earning its space. Check this against a real session at the end of Phase 1, before any UI exists.
- **The path join fails silently.** An absolute-vs-tilde mismatch reports every file as untouched and every row as quiet, which looks plausible. The dedicated regression test exists for this.
- **Cross-tab desync.** If `activeTurnId` is not kept in step with `nav.turnId`, the Timeline shows a different turn than the verdict you just read. Phase 2's acceptance test covers it.

## Out of scope

- The nested-boxes variant (artboard "Variant 2"). It is a different navigation model; picking one is a prerequisite, not a follow-up.
- Duplicates stays session-scoped and keeps its current label.
- No change to the assessment engine: predicates, moments, rule checks and verdicts are untouched throughout.
