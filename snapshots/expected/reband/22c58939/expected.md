# Ground truth - reband `22c58939`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/reband/22c58939/inputs/`, before either report was read.
`snapshots/inventory.py` is the only view used: `actions` (the ordered action
list of docs/reading-transcripts.md S11 step 3), `blocks` (block identity, no
verdict fields) and `joins` (over-generous substring candidates to confirm or
reject). Event and call numbers below are that view's numbering.

## The four truth classes

- `used` - a specific cited action satisfies what the block asks for.
- `violated` - a citable span (file, line, matched text) shows it broken.
- `no-hard-verdict` - nothing observable ties the block to this run, or the
  rule's precondition never came up. Every not-used-family status is honest
  here, and so is a co-occurrence label; a green is a false green and a red is
  a false red.
- `undecidable` - ground truth could not be established from the frozen inputs
  (S11 step 5). Excluded from the scorecard's totals.

A descriptive block - a layout table, a repo tour - counts as `used` when the
run produced or modified something the block specifically names, or reproduced
its text. `used` in this taxonomy means the block was used, not that a rule was
obeyed, and prose being copied into a written file is exactly that.

A skill or command file that the session invoked is `used` in all its blocks:
the invocation is a harness-defined record tying that document to the run.
That is a ruling, not a measurement - a reader who disagrees should say so here
rather than in the tool.

Everything not listed with its own evidence below is `no-hard-verdict` by that
default, which is what the verdict ladder says when nothing cites a tie.

This file is the ground truth itself, not a report about it: edit it by hand
when a judgement is wrong, and say in the line why it changed.

## Verdicts

Format: `- <block id> :: <truth> :: <mechanism tag or ->  :: <evidence>`

- re-reband-22c58939-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `npm run typecheck`, `npm run lint` and `npx jest`/`npm test` run before every report (calls 51, 69, 76, 85, 104, 113, 126, 144)
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- re-reband-22c58939-home-claude-claude-md-3-github-account-per-project :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-6-error-memory :: used :: F-BLINDSPOT :: call 116 appends to `ERRORS.md` under the memory dir with the rule's own `**What failed:** / **What worked:** / **Next time:**` template
- re-reband-22c58939-home-claude-claude-md-7-decision-memory :: used :: F-BLINDSPOT :: call 38 appends to `DECISIONS.md` with the rule's `**Decided:**` template
- re-reband-22c58939-home-claude-claude-md-8-end-of-implementation-summary :: used :: F-EOM :: code shipped and the closing message summarised it; the audit (research doc S7) verified this session's summary as compliant
  accept: a response-shape rule about prose; offline the tool can only say not-checkable, and the compiled record for it is a communication-scope judged one (Phase 8b worked example)
- re-reband-22c58939-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-11-implement-plan :: used :: - :: `/implement-plan` typed in the prompt at event 233; Skill call 42 is `implement-plan`
- re-reband-22c58939-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-0-agents-md-codebase-guide-for-ai-agents :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-1-what-this-is :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-2-mental-model-the-invariants-do-not-break-these :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-3-where-things-live :: used :: - :: AGENTS.md was read at call 44 and the session then created `app/src/tuner/*` and `app/src/components/ArcMeter.tsx` - the directories this table assigns those responsibilities to
  revised: listed no-hard-verdict in the first pass; corrected under the descriptive-block rule below - AGENTS.md was read at call 44 and the new files landed in the directories this table assigns them to
- re-reband-22c58939-home-reband-agents-md-4-build-run-test :: used :: F-CMDMENTION :: `npm run typecheck`, `npm run lint`, `npm test` and `npx react-native run-ios --device "BobPhone13" --mode Release` all ran verbatim
  accept: the commands sit in inline backticks in prose rather than a fenced block, and command-echo reads fences only - filed as a follow-up
- re-reband-22c58939-home-reband-agents-md-5-gotchas-learned-the-hard-way-see-also-claude-projects-memory-errors-md :: used :: - :: the session wrote the tuner files this block names
  revised: same correction as above
- re-reband-22c58939-home-reband-agents-md-6-git-branches :: no-hard-verdict :: - :: no action in the session cites this block
- re-reband-22c58939-home-reband-agents-md-7-conventions :: used :: F-CMDMENTION :: the block's "Run typecheck + lint + test before claiming done" is satisfied by calls 51, 69, 76, 104, 144
  accept: same as Build / run / test: the commands this block asks for are named in prose, not fenced
- me-claude-skills-implement-plan-skill-md-0-what-this-skill-does :: used :: F-BLINDSPOT :: skill invoked - Skill call 42, `/implement-plan` typed at event 233
- me-claude-skills-implement-plan-skill-md-1-steps :: used :: F-BLINDSPOT :: skill invoked - Skill call 42, `/implement-plan` typed at event 233
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- me-claude-skills-implement-plan-skill-md-2-rules :: used :: F-BLINDSPOT :: skill invoked - Skill call 42, `/implement-plan` typed at event 233
- c58939-home-claude-commands-grill-prd-md-0-phase-0-figma-design-optional :: used :: F-MISC :: `/grill-prd` typed at event 73; its two phases ran as Skill calls 17 (`grill-me`) and 34 (`write-a-prd`)
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- c58939-home-claude-commands-grill-prd-md-1-phase-1-grill-me :: used :: F-MISC :: `/grill-prd` typed at event 73; its two phases ran as Skill calls 17 (`grill-me`) and 34 (`write-a-prd`)
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
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
- re-reband-22c58939-home-reband-readme-md-4-project-layout :: used :: - :: the session wrote the files and updated the layout this block describes
  revised: same correction as above
- re-reband-22c58939-home-reband-readme-md-5-tests-quality-gates :: used :: F-CMDMENTION :: the three commands the block names (`npm run typecheck`, `npm run lint`, `npm test`) ran repeatedly
  accept: same as Build / run / test: the commands are named in an inline span, not a fenced block
- re-reband-22c58939-home-reband-readme-md-6-status :: no-hard-verdict :: - :: no action in the session cites this block
- listing-only-grill-me-0-grill-me :: used :: - :: Skill call 17 is `grill-me`
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-grill-prd-0-grill-prd :: used :: F-MISC :: `/grill-prd` typed at event 73
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-prd-to-plan-0-prd-to-plan :: used :: F-MISC :: `/prd-to-plan` typed at event 211
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-write-a-prd-0-write-a-prd :: used :: - :: Skill call 34 is `write-a-prd`
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-engineering-code-review-0-engineering-code-review :: used :: - :: `/engineering:code-review diff` typed at event 670
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-code-review-0-code-review :: no-hard-verdict :: - :: what was typed at event 670 is `/engineering:code-review`; the unprefixed `/code-review` was never invoked
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
