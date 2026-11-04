# Ground truth - formicHMI `12f48cdb`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formicHMI/12f48cdb/inputs/`, before either report was read.
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

- formichmi-12f48cdb-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `pnpm lint:all` and `pnpm test` run before the commit
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- formichmi-12f48cdb-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: `gh auth status` and `gh auth switch -u bionanek-x` run repeatedly before every gh call (the audit counted 13 switches)
  accept: the prose path-table predicate was retired in Phase 8b; the rule is expressible as a compiled `tool_never_without_prior` check (the worked example lives in tests/fixtures/global_rules.md.checks.json) and no checks file has been compiled for this user's own CLAUDE.md - the report says exactly that and names /compile-rules
- formichmi-12f48cdb-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-7-decision-memory :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-8-end-of-implementation-summary :: undecidable :: F-EOM :: the rule applied (code shipped) but whether the closing paragraph satisfies it is a judgement about prose that the frozen log cannot settle
  accept: a response-shape rule about prose; offline the tool can only say not-checkable, and the compiled record for it is a communication-scope judged one (Phase 8b worked example)
- formichmi-12f48cdb-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: F-TRIGGER :: what was typed at event 222 is `/implement-plan-workflow`; `/implement-plan` was never invoked
- formichmi-12f48cdb-home-claude-claude-md-12-pr-comments :: used :: - :: `<command-name>/pr-comments</command-name>` at ev 907, with the skill body delivered at ev 908 - the invocation record ruling 4 requires
  accept: the tool reports `unused` because the ctxlog hook's recorded size and digest prove `~/.claude/CLAUDE.md` changed after it was loaded, so Phase 6 reads nothing in it as a rule. The invocation is real and the block was used; refusing to judge wording nobody can recover is the deliberate cost, and it is a regression against the baseline rather than a hidden one
  revised: the Phase 8 second pass: re-derived blind and confirmed: the record is a slash-command wrapper, not a mention in prose
  blind: yes
- formichmi-12f48cdb-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-12f48cdb-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-0-formic-hmi-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-1-general-ai-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-2-what-this-application-is :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-3-repo-layout :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-4-core-ai-agent-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-5-tools :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-6-available-commands :: used :: F-CMDMENTION :: `pnpm lint:all`, the block's own validation command, ran verbatim
- 8cdb-home-git-formic-formichmi-agents-md-7-git-workflow :: used :: - :: the branch created is `feature/RBT-8135-crowder-reset-block`, exactly the prescribed `feature|bugfix|hotfix/PROJ-123-description` shape, and validation ran before the commit
  accept: branch naming is a compiled-check question (a `tool_arg_matches` over the branch command), not a harness-defined signal
- 8cdb-home-git-formic-formichmi-agents-md-8-things-to-avoid-doing :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-9-coding-guidelines :: used :: F-BLINDSPOT :: both files the no-hardcoded-strings rule names were written: `src/translations/en.json` and `src/translations/es_MX.json`
- 8cdb-home-git-formic-formichmi-agents-md-10-detailed-documentation :: no-hard-verdict :: - :: no action in the session cites this block
- 8cdb-home-git-formic-formichmi-agents-md-11-post-task-rule :: no-hard-verdict :: - :: no action in the session cites this block
- 48cdb-home-claude-skills-commit-skill-md-0-skill-commit :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-1-golden-rules :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- 48cdb-home-claude-skills-commit-skill-md-7-step-6-report :: used :: F-BLINDSPOT :: `/commit` typed at event 765; Skill call 200; two commits followed
- db-home-claude-skills-create-pr-skill-md-0-skill-create-pr :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-1-golden-rules :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-2-step-1-match-the-github-account :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-3-step-2-learn-the-pr-convention :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-4-step-3-ask-when-unsure-or-media-is-warranted :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-5-step-4-determine-the-base-branch :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-6-step-5-compose-the-pr-from-the-diff-and-the-chat :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-7-step-6-push-and-open-the-pr :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- db-home-claude-skills-create-pr-skill-md-8-step-7-monitor-the-checks :: used :: F-BLINDSPOT :: `/create-pr` typed at event 830; PR 578 opened and `gh pr checks 578 --watch` run, which is Step 7
- -skills-implement-plan-workflow-skill-md-0-what-this-skill-does :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 222; Skill call 61
- -skills-implement-plan-workflow-skill-md-1-steps :: used :: - :: step 2 says to read the project's `CLAUDE.md` files, `AGENTS.md` / `AGENTS.override.md` and every file in `.claude/rules/`: call 62 (event 233, the first call after the Skill call) cats `AGENTS.md`, lists `.claude/rules` and checks for a root `CLAUDE.md`, and call 69 (event 261) cats `AGENTS.override.md`
  revised: the read join: this step's evidence is the run reading the files it names, which nothing recorded until now. Re-derived from the frozen action list after the read join landed, and after the after payload had been read, so not blind.
  blind: no
- -skills-implement-plan-workflow-skill-md-2-workflow-script :: no-hard-verdict :: - :: the skill ran (`/implement-plan-workflow` typed at event 222), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- -skills-implement-plan-workflow-skill-md-3-rules :: no-hard-verdict :: - :: the skill ran (`/implement-plan-workflow` typed at event 222), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- -home-claude-skills-pr-comments-skill-md-0-skill-pr-comments :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-1-golden-rules :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-2-step-1-match-the-github-account :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-3-step-2-resolve-the-pr :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-4-step-3-fetch-unresolved-review-threads :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-5-step-4-evaluate-each-comment-against-the-current-code :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-6-step-5-output-the-triage-list :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- -home-claude-skills-pr-comments-skill-md-7-notes :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 907; the skill's GraphQL review-thread queries ran
- listing-only-grill-prd-0-grill-prd :: used :: F-MISC :: `/grill-prd` typed at event 6, and the skill has no SKILL.md on disk
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- listing-only-write-a-prd-0-write-a-prd :: used :: F-MISC :: Skill call 43 is `write-a-prd`, and the skill has no SKILL.md on disk
- f48cdb-home-claude-commands-grill-prd-md-0-phase-0-figma-design-optional :: used :: F-MISC :: `/grill-prd` typed at event 6
  accept: the invocation record here is the `<command-name>` wrapper a typed slash command leaves, not a `Skill` tool call. Both are invocations under ruling 4 and the tool reads both; what it refuses - and what this note used to describe wrongly - is a bare `/name` mentioned in a prompt's prose, which is not one of the two
- f48cdb-home-claude-commands-grill-prd-md-1-phase-1-grill-me :: no-hard-verdict :: - :: the skill ran (`/grill-prd` typed at event 6), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- f48cdb-home-claude-commands-grill-prd-md-2-phase-2-write-the-prd :: no-hard-verdict :: - :: the skill ran (`/grill-prd` typed at event 6), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8cdb-home-claude-commands-prd-to-plan-md-0-prd-to-plan :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-1-process :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-2-plan-feature-name :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-3-approach :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-4-architectural-decisions :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-5-phase-1-title :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-prd-to-plan-md-6-phase-2-title :: used :: F-MISC :: `/prd-to-plan` typed at event 191; `plans/crowder-calibration-reset-required/plan-*.md` written
- 8cdb-home-claude-commands-write-a-prd-md-0-step-1-module-discovery :: used :: F-BLINDSPOT :: Skill call 43 is `write-a-prd`; the prd file under plans/ was written
- 8cdb-home-claude-commands-write-a-prd-md-1-step-2-write-the-prd :: used :: F-BLINDSPOT :: Skill call 43 is `write-a-prd`; the prd file under plans/ was written
- 8cdb-home-claude-commands-write-a-prd-md-2-prd-template :: used :: F-BLINDSPOT :: Skill call 43 is `write-a-prd`; the prd file under plans/ was written
- listing-only-prd-to-plan-0-prd-to-plan :: used :: F-MISC :: `<command-name>/prd-to-plan</command-name>` at ev 191
  revised: added after the after-run surfaced a block the baseline never judged; the invocation record was re-derived blind in the Phase 8 second pass
  blind: yes
