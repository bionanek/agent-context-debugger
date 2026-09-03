# Ground truth - famigo `5448a718`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/famigo/5448a718/inputs/`, before either report was read.
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

- re-famigo-5448a718-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `yarn type-check`, `yarn lint` and `yarn test` ran before every report
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- re-famigo-5448a718-home-claude-claude-md-3-github-account-per-project :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-6-error-memory :: used :: F-BLINDSPOT :: the session appended to `$M/ERRORS.md`, the file the rule names
- re-famigo-5448a718-home-claude-claude-md-7-decision-memory :: used :: F-BLINDSPOT :: the session appended to `$M/DECISIONS.md`, the file the rule names
- re-famigo-5448a718-home-claude-claude-md-8-end-of-implementation-summary :: undecidable :: F-EOM :: the rule applied - a three-commit feature shipped, partly through bash heredocs - but whether the closing paragraph satisfies it is a judgement about prose
  accept: a response-shape rule about prose; offline the tool can only say not-checkable, and the compiled record for it is a communication-scope judged one (Phase 8b worked example)
- re-famigo-5448a718-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: F-TRIGGER :: `/implement-plan` was never typed
- re-famigo-5448a718-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- 48a718-home-git-famigo-backend-claude-md-0-backend-claude-code-context :: no-hard-verdict :: - :: no action in the session cites this block
- 48a718-home-git-famigo-backend-claude-md-1-architecture-reference :: no-hard-verdict :: - :: no action in the session cites this block
- 48a718-home-git-famigo-backend-claude-md-2-api-contracts :: no-hard-verdict :: - :: no action in the session cites this block
- 48a718-home-git-famigo-backend-claude-md-3-source-layout :: no-hard-verdict :: - :: no action in the session cites this block
- 48a718-home-git-famigo-backend-claude-md-4-database :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-0-famigo-claude-code :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-1-start-here :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-2-scope-based-context :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-3-commit-message-format :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-4-quality-gate-mandatory :: used :: F-CMDMENTION :: the block's own fenced commands ran: `yarn type-check`, `yarn lint`, `yarn test` (the audit counted 21 gate runs across the session)
- amigo-5448a718-home-git-famigo-claude-md-5-after-finishing :: used :: - :: the block prescribes `/sync-agent-docs`, which was run at event 636
  accept: the block prescribes a slash command, but the trigger predicate only fires for a block that declares the trigger for its own skill; a compiled check would decide it
- migo-claude-rules-figma-design-system-md-0-figma-design-system-famigo-mobile :: no-hard-verdict :: F-MOMENTS :: no Figma work happened this session
- -git-famigo-claude-rules-figma-tokens-md-0-figma-design-tokens-patterns-famigo-mobile :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-1-design-tokens :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-2-styling-approach :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-3-icon-system :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-4-component-patterns :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-5-asset-handling :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-6-data-architecture :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-7-responsive-design :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-8-testing-requirements :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-9-figma-to-code-translation-checklist :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-0-figma-mcp-workflow-famigo-mobile :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-1-required-figma-to-code-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-2-tech-stack :: no-hard-verdict :: F-MOMENTS :: no Figma work happened this session
- it-famigo-claude-rules-figma-workflow-md-3-project-structure :: no-hard-verdict :: - :: no action in the session cites this block
- 8a718-home-claude-skills-commit-skill-md-0-skill-commit :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-1-golden-rules :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-7-step-6-report :: used :: - :: `/commit` typed at event 682; Skill call 191
- git-famigo-claude-skills-review-skill-md-0-reviewer :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-1-role :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-2-step-1-load-context :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-3-step-2-confirm-understanding :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-4-step-3-run-checks-before-review :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-5-step-4-review :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-6-step-5-apply-fixes :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-7-step-6-verify-documentation :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-8-step-7-mark-task-done :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-9-output-format :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-10-review-summary :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-11-commit-message :: used :: - :: `/review` typed at event 583
- o-claude-skills-sync-agent-docs-skill-md-0-sync-agent-docs :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-1-role :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-2-step-1-understand-what-changed :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-3-step-2-discover-all-agent-facing-documentation :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-4-step-3-analyse-gaps-and-staleness :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-5-step-4-interview-if-uncertain :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-6-step-5-execute-updates :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-7-step-6-report :: used :: - :: `/sync-agent-docs` typed at event 636
- e-limiting-research-api-rate-limiting-md-0-api-rate-limiting-research-findings-implementation-brief :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-1-0-read-this-first-the-framing :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-2-1-current-state-verified-in-this-repo :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-3-1-5-work-already-applied-by-a-previous-agent-uncommitted-read-before-starting :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-4-2-findings-from-published-sources :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-5-3-recommended-actions :: no-hard-verdict :: - :: no action in the session cites this block
