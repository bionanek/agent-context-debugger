# Ground truth - formic-core `4ebe50c0`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formic-core/4ebe50c0/inputs/`, before either report was read.
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

- rmic-core-4ebe50c0-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-2-verification-before-claiming-done :: used :: - :: `npx vitest run --config=vitest.config.ts --project=unit` ran before reporting
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- rmic-core-4ebe50c0-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: `gh auth status` runs, then `gh auth switch -u bionanek-x && gh pr view ...` - the rule's check-then-switch for the formic row
  accept: the prose path-table predicate was retired in Phase 8b; the rule is expressible as a compiled `tool_never_without_prior` check (the worked example lives in tests/fixtures/global_rules.md.checks.json) and no checks file has been compiled for this user's own CLAUDE.md - the report says exactly that and names /compile-rules
- rmic-core-4ebe50c0-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-7-decision-memory :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-8-end-of-implementation-summary :: no-hard-verdict :: F-EOM :: nothing but docs was written this session, so the rule's precondition (a code change) was not met
- rmic-core-4ebe50c0-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-12-pr-comments :: used :: - :: `/pr-comments` typed at event 6; Skill call 3
- rmic-core-4ebe50c0-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- rmic-core-4ebe50c0-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-claude-md-0-claude-code-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-claude-md-1-memory :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-claude-md-2-talos-talos-core :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-0-formic-core-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-1-general-ai-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-2-what-this-application-is :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-3-repo-layout :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-4-human-review-and-documentation-policy :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-5-core-ai-agent-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-6-graphify-is-local-only :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-7-tools :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-8-available-commands-commands :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-9-git-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-10-things-to-avoid-doing :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-11-coding-guidelines :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-12-detailed-documentation :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-13-skills :: no-hard-verdict :: - :: no action in the session cites this block
- -4ebe50c0-home-git-formic-core-agents-md-14-post-task-rule :: no-hard-verdict :: - :: no action in the session cites this block
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
- e50c0-home-claude-skills-commit-skill-md-0-skill-commit :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-1-golden-rules :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- e50c0-home-claude-skills-commit-skill-md-7-step-6-report :: used :: F-BLINDSPOT :: `/commit` typed at event 91, followed by the commit and push
- -home-claude-skills-pr-comments-skill-md-0-skill-pr-comments :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-1-golden-rules :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-2-step-1-match-the-github-account :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-3-step-2-resolve-the-pr :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-4-step-3-fetch-unresolved-review-threads :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-5-step-4-evaluate-each-comment-against-the-current-code :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-6-step-5-output-the-triage-list :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- -home-claude-skills-pr-comments-skill-md-7-notes :: used :: F-BLINDSPOT :: `/pr-comments` typed at event 6; Skill call 3; the triage list followed
- re-static-assets-system-images-readme-md-0-system-images :: no-hard-verdict :: - :: no action in the session cites this block
