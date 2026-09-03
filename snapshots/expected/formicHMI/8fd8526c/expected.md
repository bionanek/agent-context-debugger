# Ground truth - formicHMI `8fd8526c`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formicHMI/8fd8526c/inputs/`, before either report was read.
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

- formichmi-8fd8526c-home-claude-claude-md-0-how-to-talk-to-me :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-1-global-claude-code-rules :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-2-verification-before-claiming-done :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-3-github-account-per-project :: no-hard-verdict :: F-PATHTABLE :: zero gh commands in the session; the only match for the row's account name is `git log --author="bionanek-x"`, which is not a gh command
- formichmi-8fd8526c-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-5-deep-thinking-for-hard-problems :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-6-error-memory :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-7-decision-memory :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-8-end-of-implementation-summary :: no-hard-verdict :: F-EOM :: no code was changed - the session only read git history
- formichmi-8fd8526c-home-claude-claude-md-9-graphify :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-10-cp :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-11-implement-plan :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-12-pr-comments :: no-hard-verdict :: - :: no action in the session cites this block
- formichmi-8fd8526c-home-claude-claude-md-13-standup :: used :: - :: prompt at event 3 is `/standup`; Skill call 1 is `standup`
- formichmi-8fd8526c-home-claude-claude-md-14-formic-create-release :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-0-formic-hmi-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-1-general-ai-agent-instructions :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-2-what-this-application-is :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-3-repo-layout :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-4-core-ai-agent-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-5-tools :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-6-available-commands :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-7-git-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-8-things-to-avoid-doing :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-9-coding-guidelines :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-10-detailed-documentation :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-git-formic-formichmi-agents-md-11-post-task-rule :: no-hard-verdict :: - :: no action in the session cites this block
- 526c-home-claude-skills-standup-skill-md-0-skill-standup :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-1-repos-to-scan :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-2-which-app-each-change-belongs-to :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-3-step-1-collect-the-raw-activity :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-4-step-2-cross-check-against-jira :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-5-step-3-the-list :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-6-step-4-the-slack-message :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
- 526c-home-claude-skills-standup-skill-md-7-output :: used :: F-BLINDSPOT :: the skill was invoked (Skill call 1, `/standup` typed) and its steps drove the whole session - `git log`, `git reflog`, `git status`, `git diff` in calls 2-4 are Step 1's own commands
