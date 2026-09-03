# Ground truth - famigo `9dd3cc8a`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/famigo/9dd3cc8a/inputs/`, before either report was read.
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

- re-famigo-9dd3cc8a-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `yarn type-check` and `yarn test` ran before every report
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- re-famigo-9dd3cc8a-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: `gh auth status` ran and the account was checked before `gh pr view`/`gh pr checks`
  accept: the prose path-table predicate was retired in Phase 8b; the rule is expressible as a compiled `tool_never_without_prior` check (the worked example lives in tests/fixtures/global_rules.md.checks.json) and no checks file has been compiled for this user's own CLAUDE.md - the report says exactly that and names /compile-rules
- re-famigo-9dd3cc8a-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-7-decision-memory :: used :: F-BLINDSPOT :: the session wrote `~/.claude/projects/-Users-jakuburban-Git-famigo/memory/DECISIONS.md`, the exact path the rule names
- re-famigo-9dd3cc8a-home-claude-claude-md-8-end-of-implementation-summary :: used :: F-EOM :: the audit (research doc S7) verified this session's closing summary as a compliant three-sentence summary; the red came from a `.sh` filename five paragraphs above it
  accept: same as above - the honest offline answer is not-checkable
- re-famigo-9dd3cc8a-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: F-TRIGGER :: what was typed at event 250 is `/implement-plan-workflow`; `/implement-plan` was never invoked
- re-famigo-9dd3cc8a-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-9dd3cc8a-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- d3cc8a-home-git-famigo-backend-claude-md-0-backend-claude-code-context :: no-hard-verdict :: - :: no action in the session cites this block
- d3cc8a-home-git-famigo-backend-claude-md-1-architecture-reference :: no-hard-verdict :: - :: no action in the session cites this block
- d3cc8a-home-git-famigo-backend-claude-md-2-api-contracts :: no-hard-verdict :: - :: no action in the session cites this block
- d3cc8a-home-git-famigo-backend-claude-md-3-source-layout :: no-hard-verdict :: - :: no action in the session cites this block
- d3cc8a-home-git-famigo-backend-claude-md-4-database :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-9dd3cc8a-home-git-famigo-claude-md-0-famigo-claude-code :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-9dd3cc8a-home-git-famigo-claude-md-1-start-here :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-9dd3cc8a-home-git-famigo-claude-md-2-scope-based-context :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-9dd3cc8a-home-git-famigo-claude-md-3-commit-message-format :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-9dd3cc8a-home-git-famigo-claude-md-4-quality-gate-mandatory :: used :: F-CMDMENTION :: the block's fenced `yarn type-check` / `yarn test` ran repeatedly, including before the PR
- amigo-9dd3cc8a-home-git-famigo-claude-md-5-after-finishing :: used :: - :: the block prescribes `/sync-agent-docs`, which was run twice (events 130, 537)
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
- it-famigo-claude-rules-figma-workflow-md-2-tech-stack :: no-hard-verdict :: F-MOMENTS :: no Figma work happened this session; the only tie is table headers and stack names shared with an unrelated discussion
- it-famigo-claude-rules-figma-workflow-md-3-project-structure :: no-hard-verdict :: - :: no action in the session cites this block
- 3cc8a-home-claude-skills-commit-skill-md-0-skill-commit :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-1-golden-rules :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: used :: - :: `/commit` typed at event 250; Skill call 73
- 3cc8a-home-claude-skills-commit-skill-md-7-step-6-report :: used :: - :: `/commit` typed at event 250; Skill call 73
- -skills-implement-plan-workflow-skill-md-0-what-this-skill-does :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 250; Skill call 81
- -skills-implement-plan-workflow-skill-md-1-steps :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 250; Skill call 81
  accept: the skill was invoked by typing its name, with no Skill tool call behind it; Phase 4 refuses a prompt mention as proof a skill ran, because accepting it would green every block of a skill the user merely named
- -skills-implement-plan-workflow-skill-md-2-workflow-script :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 250; Skill call 81
- -skills-implement-plan-workflow-skill-md-3-rules :: used :: F-TRIGGER :: `/implement-plan-workflow` typed at event 250; Skill call 81
- git-famigo-claude-skills-review-skill-md-0-reviewer :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-1-role :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-2-step-1-load-context :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-3-step-2-confirm-understanding :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-4-step-3-run-checks-before-review :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-5-step-4-review :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-6-step-5-apply-fixes :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-7-step-6-verify-documentation :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-8-step-7-mark-task-done :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-9-output-format :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-10-review-summary :: used :: - :: `/review` typed at event 84
- git-famigo-claude-skills-review-skill-md-11-commit-message :: used :: - :: `/review` typed at event 84
- o-claude-skills-sync-agent-docs-skill-md-0-sync-agent-docs :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-1-role :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-2-step-1-understand-what-changed :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-3-step-2-discover-all-agent-facing-documentation :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-4-step-3-analyse-gaps-and-staleness :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-5-step-4-interview-if-uncertain :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-6-step-5-execute-updates :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- o-claude-skills-sync-agent-docs-skill-md-7-step-6-report :: used :: - :: `/sync-agent-docs` typed at events 130 and 537
- it-famigo-claude-skills-vps-ssh-skill-md-0-famigo-vps-ssh-access :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-1-connection-details :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-2-before-running-anything-destructive :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-3-what-s-running-on-the-server :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-4-quick-reference-commands :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-5-ci-cd :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-6-host-sizing-and-daemon-config :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-7-troubleshooting-dockerd-cpu :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-8-firewall :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-9-troubleshooting-the-proxy :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-10-staging-vs-production :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- it-famigo-claude-skills-vps-ssh-skill-md-11-safety-rules :: used :: F-BLINDSPOT :: Skill call 58 is `vps-ssh`; calls 160-162 then edit that same SKILL.md
- e-git-famigo-claude-agents-qa-runtime-md-0-non-negotiable-distinguish-broken-from-unverifiable :: no-hard-verdict :: - :: no action in the session cites this block
- e-git-famigo-claude-agents-qa-runtime-md-1-step-1-precondition-gate :: no-hard-verdict :: - :: no action in the session cites this block
- e-git-famigo-claude-agents-qa-runtime-md-2-step-2-exercise-the-criteria :: no-hard-verdict :: - :: no action in the session cites this block
- e-git-famigo-claude-agents-qa-runtime-md-3-step-3-report :: no-hard-verdict :: - :: no action in the session cites this block
- e-git-famigo-claude-agents-qa-runtime-md-4-out-of-scope-say-so-rather-than-guessing :: no-hard-verdict :: - :: no action in the session cites this block
