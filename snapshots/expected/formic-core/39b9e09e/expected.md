# Ground truth - formic-core `39b9e09e`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formic-core/39b9e09e/inputs/`, before either report was read.
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
- -39b9e09e-home-git-formic-core-agents-md-4-human-review-and-documentation-policy :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-5-core-ai-agent-workflow :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-6-graphify-is-local-only :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-7-tools :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-8-available-commands-commands :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-9-git-workflow :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-10-things-to-avoid-doing :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-11-coding-guidelines :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-12-detailed-documentation :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-13-skills :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-14-post-task-rule :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
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
- 9e09e-home-claude-skills-commit-skill-md-1-golden-rules :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e09e-home-claude-skills-commit-skill-md-7-step-6-report :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 1712), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 9e-home-claude-skills-create-pr-skill-md-0-skill-create-pr :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-1-golden-rules :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-2-step-1-match-the-github-account :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-3-step-2-learn-the-pr-convention :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-4-step-3-ask-when-unsure-or-media-is-warranted :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-5-step-4-determine-the-base-branch :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-6-step-5-compose-the-pr-from-the-diff-and-the-chat :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-7-step-6-push-and-open-the-pr :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- 9e-home-claude-skills-create-pr-skill-md-8-step-7-monitor-the-checks :: used :: - :: `/create-pr` typed at event 1712; Skill call 232; `gh pr checks 1463 --watch` is Step 7
- listing-only-grill-prd-0-grill-prd :: used :: F-MISC :: Skill call 1 (ev 23) is `grill-prd`
  revised: the Phase 8 second pass: re-derived blind; the first pass recorded only the typed name, but the log carries a `Skill` tool call for it
  blind: yes
- b9e09e-home-claude-commands-grill-prd-md-0-phase-0-figma-design-optional :: used :: - :: `/grill-prd` typed at event 8; Skill call 1
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- b9e09e-home-claude-commands-grill-prd-md-1-phase-1-grill-me :: no-hard-verdict :: - :: the skill ran (`/grill-prd` typed at event 8), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- b9e09e-home-claude-commands-grill-prd-md-2-phase-2-write-the-prd :: no-hard-verdict :: - :: the skill ran (`/grill-prd` typed at event 8), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
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
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- t-formic-core-docs-skills-review-impl-md-2-input :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- t-formic-core-docs-skills-review-impl-md-3-steps :: used :: - :: `/review-impl` typed at event 1378, and its findings were then addressed
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- -docs-rules-general-coding-guidelines-md-0-comments-docstrings-and-durable-docs :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -docs-rules-general-coding-guidelines-md-1-forbidden-changes :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
- -docs-rules-general-coding-guidelines-md-2-architecture-decisions-intentional-do-not-fix :: undecidable :: - :: this id names a section of the frozen disk copy that is not a section of the text the session was given: the delivered AGENTS.md has no `Human Review and Documentation Policy` and calls the graphify section something else, so every later block renumbers. Ruling 2 makes the delivered text the subject, and there is no counterpart row to score this id against
  revised: the Phase 8 re-bake: seen while reading the after payload, not derived blind - the id shift is a fact about the two payloads, and the row is excluded rather than re-pointed at a block it was not written about
  blind: no
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
- -skills-implement-plan-workflow-skill-md-0-what-this-skill-does :: used :: F-TRIGGER :: `<command-name>/implement-plan-workflow</command-name>` at ev 413, with the skill body delivered at ev 414
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
- -skills-implement-plan-workflow-skill-md-1-steps :: no-hard-verdict :: - :: the skill ran (`<command-name>/implement-plan-workflow</command-name>` at ev 413, with the skill body delivered at ev 414), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- -skills-implement-plan-workflow-skill-md-2-workflow-script :: no-hard-verdict :: - :: the skill ran (`<command-name>/implement-plan-workflow</command-name>` at ev 413, with the skill body delivered at ev 414), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- -skills-implement-plan-workflow-skill-md-3-rules :: no-hard-verdict :: - :: the skill ran (`<command-name>/implement-plan-workflow</command-name>` at ev 413, with the skill body delivered at ev 414), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- listing-only-prd-to-plan-0-prd-to-plan :: used :: F-MISC :: `<command-name>/prd-to-plan</command-name>` at ev 368
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
- listing-only-review-impl-0-review-impl :: used :: F-MISC :: `<command-name>/review-impl</command-name>` at ev 1378
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
- listing-only-write-a-prd-0-write-a-prd :: used :: F-MISC :: Skill call 15 (ev 307) is `write-a-prd`
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
- 107-skills-figma-design-to-code-skill-md-0-implement-a-figma-design-as-code-design-code :: used :: - :: Skill call 6 (ev 68) is `figma:figma-design-to-code`
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
- 107-skills-figma-design-to-code-skill-md-1-direction-and-scope :: no-hard-verdict :: - :: the skill ran (Skill call 6 (ev 68) is `figma:figma-design-to-code`), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 107-skills-figma-design-to-code-skill-md-2-workflow :: no-hard-verdict :: - :: the skill ran (Skill call 6 (ev 68) is `figma:figma-design-to-code`), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 107-skills-figma-design-to-code-skill-md-3-error-recovery :: no-hard-verdict :: - :: the skill ran (Skill call 6 (ev 68) is `figma:figma-design-to-code`), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no

<!-- The same sections under the ids the delivered text produces (ruling 2). -->
- -39b9e09e-home-git-formic-core-agents-md-4-core-ai-agent-workflow :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-5-graphify-knowledge-graph :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-6-tools :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-7-available-commands-commands :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-8-git-workflow :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-9-things-to-avoid-doing :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-10-coding-guidelines :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-11-detailed-documentation :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-12-skills :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -39b9e09e-home-git-formic-core-agents-md-13-post-task-rule :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -docs-rules-general-coding-guidelines-md-0-forbidden-changes :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
- -docs-rules-general-coding-guidelines-md-1-architecture-decisions-intentional-do-not-fix :: no-hard-verdict :: - :: no action in the session cites this block; the evidence is the same frozen action list as the renumbered row above
  revised: added in the Phase 8 re-bake, once the delivered AGENTS.md was seen to renumber its sections; the verdict is the first pass's own reading of the same section, but the id was read off the after payload
  blind: no
