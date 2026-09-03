# Ground truth - formic-core `39b9e09e`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formic-core/39b9e09e/inputs/`, before either report was read.
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

- rmic-core-39b9e09e-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-2-verification-before-claiming-done :: used :: - :: `just palletizer-hmi-lint`, `yarn test` and `yarn test:browser:noUI` ran before reporting
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- rmic-core-39b9e09e-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: `gh auth status` ran and the account was already correct, which is what "switch if needed" asks for
  accept: the prose path-table predicate was retired in Phase 8b; the rule is expressible as a compiled `tool_never_without_prior` check (the worked example lives in tests/fixtures/global_rules.md.checks.json) and no checks file has been compiled for this user's own CLAUDE.md - the report says exactly that and names /compile-rules
- rmic-core-39b9e09e-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-7-decision-memory :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-8-end-of-implementation-summary :: undecidable :: F-EOM :: the rule applied (code shipped) but compliance is a judgement about the closing prose
  accept: a response-shape rule about prose; offline the tool can only say not-checkable, and the compiled record for it is a communication-scope judged one (Phase 8b worked example)
- rmic-core-39b9e09e-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: F-TRIGGER :: what was typed at event 413 is `/implement-plan-workflow`; `/implement-plan` was never invoked
- rmic-core-39b9e09e-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-39b9e09e-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-claude-md-0-claude-code-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-claude-md-1-memory :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-claude-md-2-talos-talos-core :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-0-formic-core-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-1-general-ai-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-2-what-this-application-is :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-3-repo-layout :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-4-human-review-and-documentation-policy :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-5-core-ai-agent-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-6-graphify-is-local-only :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-7-tools :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-8-available-commands-commands :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-9-git-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-10-things-to-avoid-doing :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-11-coding-guidelines :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-12-detailed-documentation :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-13-skills :: no-hard-verdict :: - :: no action in the session cites this block
- -39b9e09e-home-git-formic-core-agents-md-14-post-task-rule :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-0-graph-report-core-2026-08-11 :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-1-corpus-check :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-2-summary :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-3-graph-freshness :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-4-community-hubs-navigation :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-5-god-nodes-most-connected-your-core-abstractions :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-6-surprising-connections-you-probably-didn-t-know-these :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-7-hyperedges-group-relationships :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-8-communities-4935-total-2932-thin-omitted :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-9-ambiguous-edges-review-these :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-10-knowledge-gaps :: no-hard-verdict :: - :: no action in the session cites this block
- formic-core-graphify-out-graph-report-md-11-suggested-questions :: no-hard-verdict :: - :: no action in the session cites this block
- 9e09e-home-claude-skills-commit-skill-md-0-skill-commit :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-1-golden-rules :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e09e-home-claude-skills-commit-skill-md-7-step-6-report :: used :: - :: `/commit` typed at event 1712; Skill call 222
- 9e-home-claude-skills-create-pr-skill-md-0-skill-create-pr :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-1-golden-rules :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-2-step-1-match-the-github-account :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-3-step-2-learn-the-pr-convention :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-4-step-3-ask-when-unsure-or-media-is-warranted :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-5-step-4-determine-the-base-branch :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-6-step-5-compose-the-pr-from-the-diff-and-the-chat :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-7-step-6-push-and-open-the-pr :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-8-step-7-monitor-the-checks :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- listing-only-grill-prd-0-grill-prd :: used :: F-MISC :: `/grill-prd` typed at event 8; Skill call 1
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
  revised: missed in the first pass: the listing-only entry is the same skill as `~/.claude/commands/grill-prd.md`, which was judged `used` on the same evidence
- b9e09e-home-claude-commands-grill-prd-md-0-phase-0-figma-design-optional :: used :: - :: `/grill-prd` typed at event 8; Skill call 1
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- b9e09e-home-claude-commands-grill-prd-md-1-phase-1-grill-me :: used :: - :: `/grill-prd` typed at event 8; Skill call 1
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- b9e09e-home-claude-commands-grill-prd-md-2-phase-2-write-the-prd :: used :: - :: `/grill-prd` typed at event 8; Skill call 1
- e09e-home-claude-commands-prd-to-plan-md-0-prd-to-plan :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-1-process :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-2-plan-feature-name :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-3-approach :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-4-architectural-decisions :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-5-phase-1-title :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-prd-to-plan-md-6-phase-2-title :: used :: F-BLINDSPOT :: `/prd-to-plan` typed at event 368; the plan and design files under `plans/palletizer-cases-handling/` were written from its template
- e09e-home-claude-commands-write-a-prd-md-0-step-1-module-discovery :: used :: - :: Skill call 15 is `write-a-prd`; `prd-palletizer-cases-handling.md` written
- e09e-home-claude-commands-write-a-prd-md-1-step-2-write-the-prd :: used :: - :: Skill call 15 is `write-a-prd`; `prd-palletizer-cases-handling.md` written
- e09e-home-claude-commands-write-a-prd-md-2-prd-template :: used :: - :: Skill call 15 is `write-a-prd`; `prd-palletizer-cases-handling.md` written
- git-formic-core-palletizer-hmi-agents-md-0-palletizer-hmi :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-1-migration-status :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-2-documents-in-docs :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-3-architecture-at-a-glance :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-4-platform-adapter-layer-stage-1 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-5-stores-api-clients-and-sockets-stage-2 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-6-components-screens-stage-3 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-7-shared-components-stage-3a :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-8-routing-shell-stage-4 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-9-embeds-stage-5 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-10-suite-completion-cleanup-stage-6 :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-11-commands :: used :: F-BLINDSPOT :: `just palletizer-hmi-lint`, `just palletizer-hmi-dev` and `yarn test:browser:noUI` - commands this block and nothing else names - all ran verbatim
  accept: Phase 4's residency caveat: the AGENTS.md was read in one turn and its commands ran in later ones, so combining the per-turn statuses yields dormant
- git-formic-core-palletizer-hmi-agents-md-12-tests :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-13-ports :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-14-configuration :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-15-deployment :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-16-styling :: no-hard-verdict :: - :: no action in the session cites this block
- git-formic-core-palletizer-hmi-agents-md-17-import-aliases :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-create-component-md-0-skill-create-component :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-create-component-md-1-trigger :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-create-component-md-2-before-you-start :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-create-component-md-3-steps :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-skills-create-store-md-0-skill-create-store :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-skills-create-store-md-1-trigger :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-skills-create-store-md-2-before-you-start :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-skills-create-store-md-3-steps :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-skills-create-store-md-4-cross-store-access :: no-hard-verdict :: - :: no action in the session cites this block
- -git-formic-core-docs-skills-add-test-md-0-skill-add-test :: no-hard-verdict :: - :: no action in the session cites this block
- -git-formic-core-docs-skills-add-test-md-1-trigger :: no-hard-verdict :: - :: no action in the session cites this block
- -git-formic-core-docs-skills-add-test-md-2-before-you-start :: no-hard-verdict :: - :: no action in the session cites this block
- -git-formic-core-docs-skills-add-test-md-3-steps :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-add-api-endpoint-md-0-skill-add-api-endpoint :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-add-api-endpoint-md-1-trigger :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-add-api-endpoint-md-2-before-you-start :: no-hard-verdict :: - :: no action in the session cites this block
- mic-core-docs-skills-add-api-endpoint-md-3-steps :: no-hard-verdict :: - :: no action in the session cites this block
- t-formic-core-docs-skills-review-impl-md-0-skill-review-impl :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
- t-formic-core-docs-skills-review-impl-md-1-trigger :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- t-formic-core-docs-skills-review-impl-md-2-input :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- t-formic-core-docs-skills-review-impl-md-3-steps :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- -docs-rules-general-coding-guidelines-md-0-comments-docstrings-and-durable-docs :: no-hard-verdict :: - :: no action in the session cites this block
- -docs-rules-general-coding-guidelines-md-1-forbidden-changes :: no-hard-verdict :: - :: no action in the session cites this block
- -docs-rules-general-coding-guidelines-md-2-architecture-decisions-intentional-do-not-fix :: no-hard-verdict :: - :: no action in the session cites this block
- rules-frontend-components-hooks-utils-md-0-frontend-components-hooks-utils :: no-hard-verdict :: - :: no action in the session cites this block
- rules-frontend-components-hooks-utils-md-1-component-rules :: no-hard-verdict :: - :: no action in the session cites this block
- rules-frontend-components-hooks-utils-md-2-hook-rules :: no-hard-verdict :: - :: no action in the session cites this block
- rules-frontend-components-hooks-utils-md-3-utility-rules :: no-hard-verdict :: - :: no action in the session cites this block
- les-frontend-styling-constants-config-md-0-frontend-styling-constants-configuration :: no-hard-verdict :: - :: no action in the session cites this block
- les-frontend-styling-constants-config-md-1-styling :: no-hard-verdict :: - :: no action in the session cites this block
- les-frontend-styling-constants-config-md-2-constants :: no-hard-verdict :: - :: no action in the session cites this block
- les-frontend-styling-constants-config-md-3-tailwind-canonical-classes :: no-hard-verdict :: - :: no action in the session cites this block
- -formic-core-docs-rules-frontend-mobx-md-0-frontend-mobx-patterns :: no-hard-verdict :: - :: no action in the session cites this block
- c-core-docs-rules-frontend-api-errors-md-0-frontend-api-layer-error-handling :: no-hard-verdict :: - :: no action in the session cites this block
- c-core-docs-rules-frontend-typescript-md-0-frontend-typescript-conventions :: no-hard-verdict :: - :: no action in the session cites this block
- core-docs-rules-testing-frontend-apps-md-0-testing-frontend-apps-guide :: no-hard-verdict :: - :: no action in the session cites this block
- re-docs-rules-react-coding-guidelines-md-0-react-coding-guidelines :: no-hard-verdict :: - :: no action in the session cites this block
- -skills-implement-plan-workflow-skill-md-0-what-this-skill-does :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 413
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- -skills-implement-plan-workflow-skill-md-1-steps :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 413
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- -skills-implement-plan-workflow-skill-md-2-workflow-script :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 413
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- -skills-implement-plan-workflow-skill-md-3-rules :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 413
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-prd-to-plan-0-prd-to-plan :: used :: F-MISC :: `/prd-to-plan` typed at event 368
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-review-impl-0-review-impl :: used :: F-MISC :: `/review-impl` typed at event 1378
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- listing-only-write-a-prd-0-write-a-prd :: used :: F-MISC :: Skill call 15 is `write-a-prd`
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- 107-skills-figma-design-to-code-skill-md-0-implement-a-figma-design-as-code-design-code :: used :: - :: Skill call 6 is `figma:figma-design-to-code`; the figma spec files under plans/palletizer-cases-handling/designs/ were then written
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- 107-skills-figma-design-to-code-skill-md-1-direction-and-scope :: used :: - :: Skill call 6 is `figma:figma-design-to-code`; the figma spec files under plans/palletizer-cases-handling/designs/ were then written
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- 107-skills-figma-design-to-code-skill-md-2-workflow :: used :: - :: Skill call 6 is `figma:figma-design-to-code`; the figma spec files under plans/palletizer-cases-handling/designs/ were then written
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
- 107-skills-figma-design-to-code-skill-md-3-error-recovery :: used :: - :: Skill call 6 is `figma:figma-design-to-code`; the figma spec files under plans/palletizer-cases-handling/designs/ were then written
  revised: added after the after-run surfaced a block the baseline never judged; the evidence is the same frozen action list, but this line was not written blind
