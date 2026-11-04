# Ground truth - reband `22c58939`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/reband/22c58939/inputs/`, before either report was read.
`snapshots/inventory.py` is the only view used: `actions` (the ordered action
list of docs/reading-transcripts.md S11 step 3), `blocks` (block identity, no
verdict fields) and `joins` (over-generous substring candidates to confirm or
reject). Event and call numbers below are that view's numbering.

A verdict here is about the block text as the session received it. The frozen
copies of the rule documents under `inputs/` were captured after the session
ran, so where the transcript carries the delivered text - a `Read` result, an
attachment, the pre-edit half of a write - that text is the one a row is about,
and the frozen copy is reference only. Where nothing recovers it, the row is
still about the frozen copy and the tool says so on the block (`text disk`, or
`text stale` where the ctxlog hook's recorded size and digest prove the file
changed since it was loaded).

## The rulings this file applies

They are written once, in [`snapshots/expected/RULINGS.md`](../../RULINGS.md), and every
row here is scored under them. The four truth classes (`used`, `violated`,
`no-hard-verdict`, `undecidable`) are ruling 1; the delivered-text rule above is
ruling 2; the descriptive-block rule is ruling 3, and its disputed half in
particular: **A file created under a directory the block names does not count.**
Invoking a skill or command file makes only that document's own first block -
its identity block - `used`; every other block has to earn its verdict from its
own evidence (ruling 4), and everything not listed below with its own evidence
is `no-hard-verdict` by default (ruling 5).

This file is the ground truth itself, not a report about it: edit it by hand
when a judgement is wrong, and say in the line why it changed. A row corrected
after a payload was read carries a `revised:` note and a `blind:` line saying
whether the correction itself was derived blind (ruling 7); the scorer refuses
one without the other.

## Verdicts

Format: `- <block id> :: <truth> :: <mechanism tag or ->  :: <evidence>`

- re-reband-22c58939-home-claude-claude-md-0-how-to-talk-to-me :: undecidable :: - :: tone, length and format rule with no observable action; the frozen transcript has the prose but nothing in a tool log settles it
  revised: the Phase 8 second pass: a rule that can only be followed invisibly is `undecidable`, not `no-hard-verdict`
  blind: yes
- re-reband-22c58939-home-claude-claude-md-1-global-claude-code-rules :: undecidable :: - :: asking before acting did happen (AskUserQuestion calls 19-33) but inside the grill-me skill; the comment rule would need the code the five phase agents wrote, and those transcripts are not frozen
  revised: the Phase 8 second pass: there is evidence on both sides and it does not settle the question
  blind: yes
- re-reband-22c58939-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `npm run typecheck`, `npm run lint` and `npx jest`/`npm test` run before every report (calls 51, 69, 76, 85, 104, 113, 126, 144)
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- re-reband-22c58939-home-claude-claude-md-3-github-account-per-project :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-5-deep-thinking-for-hard-problems :: undecidable :: - :: extended-thinking use is not observable as an action; the 109 thinking items in the log are a model and CLI property, not compliance
  revised: the Phase 8 second pass: a rule that cannot be observed is `undecidable`
  blind: yes
- re-reband-22c58939-home-claude-claude-md-6-error-memory :: used :: F-BLINDSPOT :: call 116 appends to `ERRORS.md` under the memory dir with the rule's own `**What failed:** / **What worked:** / **Next time:**` template
- re-reband-22c58939-home-claude-claude-md-7-decision-memory :: used :: F-BLINDSPOT :: call 38 appends to `DECISIONS.md` with the rule's `**Decided:**` template
- re-reband-22c58939-home-claude-claude-md-8-end-of-implementation-summary :: undecidable :: F-EOM :: every implementation turn's closing prose carries a user-facing summary (ev 393, 467, 482), but each of those responses ends on a question, so whether `end your response with` is satisfied is a judgement about prose
  revised: the Phase 8 second pass: the first pass called this `used` on the audit's own reading; the blind pass found the responses end on a question, and ruling 6 refuses a prose judgement either way
  blind: yes
- re-reband-22c58939-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-11-implement-plan :: used :: - :: `/implement-plan` typed in the prompt at event 233; Skill call 42 is `implement-plan`
- re-reband-22c58939-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-0-agents-md-codebase-guide-for-ai-agents :: used :: - :: the block says `read this first ... keep it accurate when you change the code`: read in full at call 44 (ev 250) before the phase agents were spawned, and kept accurate at calls 149-152 after the code changed
  accept: the tie is a write to the block's own document, which the tool excludes by design - a memory file otherwise matches its own template and marks every older entry in it used - so this compliance is one the tool cannot see
  revised: the Phase 8 second pass: the first pass missed both halves of what this block asks
  blind: yes
- re-reband-22c58939-home-reband-agents-md-1-what-this-is :: used :: - :: the block's own wording (`bare **React Native 0.86**`, `NOT Expo`, `react-native-audio-api` 0.12.2) was reproduced into every phase-agent prompt at calls 46-50
  revised: the Phase 8 second pass: the block's own text was reproduced in something the run wrote, which ruling 3 counts
  blind: yes
- re-reband-22c58939-home-reband-agents-md-2-mental-model-the-invariants-do-not-break-these :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-3-where-things-live :: used :: - :: the run rewrote this table to keep it true: call 149 (ev 769) inserts the `tuner/` row, call 150 adds `TunerScreen`/`ArcMeter`/`StringRow`, call 151 changes the tab list
  accept: the tie is a write to the block's own document, which the tool excludes by design - a memory file otherwise matches its own template and marks every older entry in it used - so this compliance is one the tool cannot see
  revised: the Phase 8 second pass: the first pass credited this to files landing under directories the table names, which ruling 3 rejects; the blind pass found the stronger tie, the rewrite of the table itself, so the verdict stands on new evidence
  blind: yes
- re-reband-22c58939-home-reband-agents-md-4-build-run-test :: used :: F-CMDMENTION :: `npm run typecheck`, `npm run lint`, `npm test` and `npx react-native run-ios --device "BobPhone13" --mode Release` all ran verbatim
  accept: the commands sit in inline backticks in prose rather than a fenced block, and command-echo reads fences only - filed as a follow-up
- re-reband-22c58939-home-reband-agents-md-5-gotchas-learned-the-hard-way-see-also-claude-projects-memory-errors-md :: used :: - :: call 152 (ev 779) inserts the tuner mic-capture bullet into this block's own list, and two of its listed gotchas were reproduced into the phase-1 prompt at call 46
  accept: the tie is a write to the block's own document, which the tool excludes by design - a memory file otherwise matches its own template and marks every older entry in it used - so this compliance is one the tool cannot see
  revised: the Phase 8 second pass: the first pass credited the tuner files landing under a named directory, which ruling 3 rejects; the tie that survives is the rewrite of the block itself
  blind: yes
- re-reband-22c58939-home-reband-agents-md-6-git-branches :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-7-conventions :: used :: F-CMDMENTION :: the block's "Run typecheck + lint + test before claiming done" is satisfied by calls 51, 69, 76, 104, 144
  accept: same as Build / run / test: the commands this block asks for are named in prose, not fenced
- me-claude-skills-implement-plan-skill-md-0-what-this-skill-does :: used :: F-BLINDSPOT :: skill invoked - Skill call 42, `/implement-plan` typed at event 233
- me-claude-skills-implement-plan-skill-md-1-steps :: no-hard-verdict :: - :: the skill ran (skill invoked - Skill call 42, `/implement-plan` typed at event 233), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- me-claude-skills-implement-plan-skill-md-2-rules :: no-hard-verdict :: - :: the skill ran (skill invoked - Skill call 42, `/implement-plan` typed at event 233), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- c58939-home-claude-commands-grill-prd-md-0-phase-0-figma-design-optional :: used :: F-MISC :: `/grill-prd` typed at event 73; its two phases ran as Skill calls 17 (`grill-me`) and 34 (`write-a-prd`)
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- c58939-home-claude-commands-grill-prd-md-1-phase-1-grill-me :: used :: F-MISC :: `/grill-prd` typed at event 73; its two phases ran as Skill calls 17 (`grill-me`) and 34 (`write-a-prd`)
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- c58939-home-claude-commands-grill-prd-md-2-phase-2-write-the-prd :: used :: F-MISC :: `/grill-prd` typed at event 73; its two phases ran as Skill calls 17 (`grill-me`) and 34 (`write-a-prd`)
- 8939-home-claude-commands-prd-to-plan-md-0-prd-to-plan :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-1-process :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-2-plan-feature-name :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-3-approach :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-4-architectural-decisions :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-5-phase-1-title :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-prd-to-plan-md-6-phase-2-title :: used :: F-MISC :: `/prd-to-plan` typed at event 211; call 41 writes `plans/guitar-tuner/plan-guitar-tuner.md`
- 8939-home-claude-commands-write-a-prd-md-0-step-1-module-discovery :: used :: F-BLINDSPOT :: Skill call 34 is `write-a-prd`; call 36 writes `plans/guitar-tuner/prd-guitar-tuner.md`
- 8939-home-claude-commands-write-a-prd-md-1-step-2-write-the-prd :: used :: F-BLINDSPOT :: Skill call 34 is `write-a-prd`; call 36 writes `plans/guitar-tuner/prd-guitar-tuner.md`
- 8939-home-claude-commands-write-a-prd-md-2-prd-template :: used :: F-BLINDSPOT :: Skill call 34 is `write-a-prd`; call 36 writes `plans/guitar-tuner/prd-guitar-tuner.md`
- rs-jakuburban-reband-memory-decisions-md-0-decisions-reband :: no-hard-verdict :: - :: no action in the session cites this block
- rs-jakuburban-reband-memory-decisions-md-1-2026-07-01-host-backgrounding-fix-keeps-the-lan-host-alive-never-steers-to-cloud-mode :: no-hard-verdict :: - :: no action in the session cites this block
- rs-jakuburban-reband-memory-decisions-md-2-2026-06-11-react-native-over-flutter-supersedes-same-day-flutter-decision :: no-hard-verdict :: - :: no action in the session cites this block
- rs-jakuburban-reband-memory-decisions-md-3-2026-06-11-local-audio-files-are-the-precision-sync-path-spotify-youtube-are-loose-sync-tiers :: no-hard-verdict :: - :: no action in the session cites this block
- rs-jakuburban-reband-memory-decisions-md-4-2026-06-11-custom-node-js-ws-backend-over-firebase-rtdb :: no-hard-verdict :: - :: no action in the session cites this block
- rs-jakuburban-reband-memory-decisions-md-5-2026-06-18-react-native-track-player-v5-migration-merged-to-main-v4-patches-preserved-license-flag :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-readme-md-4-project-layout :: used :: - :: call 153 (ev 783) rewrites this table: it inserts the `app/src/tuner/` row and adds `Tuner` to the screens row
  accept: the tie is a write to the block's own document, which the tool excludes by design - a memory file otherwise matches its own template and marks every older entry in it used - so this compliance is one the tool cannot see
  revised: the Phase 8 second pass: same correction as the AGENTS.md table - the directory join is rejected, the rewrite of the block is what stands
  blind: yes
- re-reband-22c58939-home-reband-readme-md-5-tests-quality-gates :: used :: F-CMDMENTION :: the three commands the block names (`npm run typecheck`, `npm run lint`, `npm test`) ran repeatedly
  accept: same as Build / run / test: the commands are named in an inline span, not a fenced block
- re-reband-22c58939-home-reband-readme-md-6-status :: used :: - :: call 154 (ev 787) adds the tuner line to this block's own status list
  accept: the tie is a write to the block's own document, which the tool excludes by design - a memory file otherwise matches its own template and marks every older entry in it used - so this compliance is one the tool cannot see
  revised: the Phase 8 second pass: the first pass missed the edit to the block's own text
  blind: yes
- listing-only-grill-me-0-grill-me :: used :: - :: Skill call 17 (ev 93) is `grill-me`
  revised: added after the after-run surfaced a block the baseline never judged
  blind: yes
- listing-only-grill-prd-0-grill-prd :: used :: F-MISC :: `<command-name>/grill-prd</command-name>` at ev 73, with the command body delivered at ev 74
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind
  blind: yes
- listing-only-prd-to-plan-0-prd-to-plan :: used :: F-MISC :: `<command-name>/prd-to-plan</command-name>` at ev 211, with the command body delivered at ev 212
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind
  blind: yes
- listing-only-write-a-prd-0-write-a-prd :: used :: - :: Skill call 34 (ev 177) is `write-a-prd`
  revised: added after the after-run surfaced a block the baseline never judged
  blind: yes
- listing-only-engineering-code-review-0-engineering-code-review :: used :: - :: `<command-name>/engineering:code-review</command-name>` at ev 670
  revised: added after the after-run surfaced a block the baseline never judged
  blind: yes
- listing-only-code-review-0-code-review :: no-hard-verdict :: - :: what was typed at ev 670 is `/engineering:code-review`; the unprefixed `/code-review` was never invoked
  revised: added after the after-run surfaced a block the baseline never judged
  blind: yes
