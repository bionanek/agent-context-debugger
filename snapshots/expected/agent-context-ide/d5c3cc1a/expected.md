# Ground truth - agent-context-ide `d5c3cc1a`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/agent-context-ide/d5c3cc1a/inputs/`, before either report was read.
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
- c1a-home-git-agent-context-ide-claude-md-1-what-this-project-is :: used :: - :: the README written at call 8 (ev 75) reproduces this block's own sentence almost verbatim: `parses a real Claude Code transcript (.jsonl under ~/.claude/projects/<encoded-cwd>/) plus the relevant CLAUDE.md and skill files, and emits one self-contained HTML file with all the data baked in`
  revised: the Phase 8 second pass: re-derived blind and confirmed on the block's own text appearing in the file the run wrote, which is ruling 3's own-text branch rather than the same-subject one
  blind: yes
- c1a-home-git-agent-context-ide-claude-md-2-running :: used :: - :: the same README write reproduces this block's own prose: `Each listing prints the ids the next query needs, so three commands take you from zero knowledge to one block's verdict` and the address-resolution sentence about `agent-foo.md`
  revised: the Phase 8 second pass: re-derived blind; the tie is the block's own wording in the written file
  blind: yes
- c1a-home-git-agent-context-ide-claude-md-3-tests :: no-hard-verdict :: - :: no action in the session cites this block
- c1a-home-git-agent-context-ide-claude-md-4-architecture :: used :: - :: the same README write quotes this block unchanged: `a generator's claim that its tests pass is not evidence`, `disagreement is unclear, never a violation`, `used in any turn -> used at session scope`
  revised: the Phase 8 second pass: re-derived blind; the tie is three of the block's own sentences in the written file
  blind: yes
