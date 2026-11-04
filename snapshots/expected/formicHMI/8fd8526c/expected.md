# Ground truth - formicHMI `8fd8526c`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/formicHMI/8fd8526c/inputs/`, before either report was read.
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
  accept: the tool reports `unused` because the ctxlog hook's recorded size and digest prove `~/.claude/CLAUDE.md` changed after it was loaded, so Phase 6 reads nothing in it as a rule. The invocation is real and the block was used; refusing to judge wording nobody can recover is the deliberate cost, and it is a regression against the baseline rather than a hidden one
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
