# Ground truth - agent-context-ide `d5c3cc1a`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/agent-context-ide/d5c3cc1a/inputs/`, before either report was read.
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

- ntext-ide-d5c3cc1a-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-2-verification-before-claiming-done :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: call 16 `gh auth status ...`, then call 17 `gh auth switch -u bionanek && git push origin main` - the rule's check-then-switch, run verbatim for the agent-context-ide row
  accept: the prose path-table predicate was retired in Phase 8b; the rule is expressible as a compiled `tool_never_without_prior` check (the worked example lives in tests/fixtures/global_rules.md.checks.json) and no checks file has been compiled for this user's own CLAUDE.md - the report says exactly that and names /compile-rules
- ntext-ide-d5c3cc1a-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-7-decision-memory :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-8-end-of-implementation-summary :: no-hard-verdict :: F-EOM :: the only files written are CLAUDE.md and README.md, so the rule's precondition (a code change) was never met
- ntext-ide-d5c3cc1a-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: F-TRIGGER :: `/implement-plan` was never typed and no Skill call names it
- ntext-ide-d5c3cc1a-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-13-standup :: no-hard-verdict :: - :: no action in the session cites this block
- ntext-ide-d5c3cc1a-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- c1a-home-git-agent-context-ide-claude-md-0-claude-md :: no-hard-verdict :: - :: no action in the session cites this block
- c1a-home-git-agent-context-ide-claude-md-1-what-this-project-is :: used :: - :: the README written at call 8 is built from this document; the Write's content carries this block's own description of the tool
  revised: listed no-hard-verdict in the first pass; corrected after checking the README the session wrote (transcript Write call 8) and finding this block's text in it
- c1a-home-git-agent-context-ide-claude-md-2-running :: used :: - :: the README written at call 8 reproduces this block's command comments verbatim (`# List all sessions discoverable for this cwd`)
  revised: same correction as above - the README reproduces this block's command comments verbatim
- c1a-home-git-agent-context-ide-claude-md-3-tests :: no-hard-verdict :: - :: no action in the session cites this block
- c1a-home-git-agent-context-ide-claude-md-4-architecture :: used :: - :: the README written at call 8 restates this block's pipeline description
  revised: same correction as above
