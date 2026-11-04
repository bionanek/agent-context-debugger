# Ground truth - famigo `5448a718`

Written from the frozen transcript and the frozen rule documents under
`snapshots/baseline/famigo/5448a718/inputs/`, before either report was read.
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

- re-famigo-5448a718-home-claude-claude-md-0-how-to-talk-to-me :: undecidable :: - :: tone and response-shape rule; em-dashes do appear in the assistant prose (ev 631, 731, 744) against `never use em-dashes`, but the delivered file (14168 B) is not the frozen one (14687 B), so it is not established that the clause was delivered
  revised: the Phase 8 second pass: the first pass called this `no-hard-verdict`; the blind pass found observable but inconclusive evidence on both sides, which is what `undecidable` is for
  blind: yes
- re-famigo-5448a718-home-claude-claude-md-1-global-claude-code-rules :: undecidable :: - :: behavioural block; conformant samples exist (why-comments written at calls 31 and 41, a question before acting at ev 107) but neither compliance nor breach can be enumerated from the frozen inputs
  revised: the Phase 8 second pass: `no-hard-verdict` understated it - there is evidence, it just does not settle the question
  blind: yes
- re-famigo-5448a718-home-claude-claude-md-2-verification-before-claiming-done :: used :: F-BLINDSPOT :: `yarn type-check`, `yarn lint` and `yarn test` ran before every report
  accept: a prose rule that names no command, so nothing harness-defined ties it to the lint and test runs; a compiled `tool_precedes` check would decide it
- re-famigo-5448a718-home-claude-claude-md-3-github-account-per-project :: used :: F-PATHTABLE :: the first `gh` command of the session is the check itself: `gh auth status` at call 192 (ev 691), then `gh auth switch -u bionanek` at call 194
  revised: the Phase 8 second pass: the first pass missed the check-before-`gh` ordering, which is a cited action satisfying the rule
  blind: yes
- re-famigo-5448a718-home-claude-claude-md-4-copy-to-clipboard :: no-hard-verdict :: - :: no action in the session cites this block
- re-famigo-5448a718-home-claude-claude-md-5-deep-thinking-for-hard-problems :: undecidable :: - :: extended-thinking use is not observable from the log; no tool evidence is possible either way
  revised: the Phase 8 second pass: a rule that cannot be observed is `undecidable`, not `no-hard-verdict` - the precondition did come up
  blind: yes
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
- 48a718-home-git-famigo-backend-claude-md-1-architecture-reference :: used :: - :: the block names `backend/AGENT.md`; calls 167 and 180 read it and call 185 (ev 662) edits it
  revised: the Phase 8 second pass: a file the block names by path was modified, which ruling 3 counts
  blind: yes
- 48a718-home-git-famigo-backend-claude-md-2-api-contracts :: used :: - :: the block names `API_CONTRACT.md`; call 77 (ev 272) edits it to match the new params and call 141 (ev 510) edits it again when they were removed
  revised: the Phase 8 second pass: a file the block names by path was modified, which ruling 3 counts
  blind: yes
- 48a718-home-git-famigo-backend-claude-md-3-source-layout :: no-hard-verdict :: - :: files were modified under the directories this tree names (`src/middleware/`, `src/services/`), which ruling 3 explicitly does not count; the block names no file the run touched
  revised: the Phase 8 second pass: the blind pass read this as `used` on the directory join; ruling 3 rejects that join, so the first pass's answer stands and the disagreement is resolved rather than carried
  blind: yes
- 48a718-home-git-famigo-backend-claude-md-4-database :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-0-famigo-claude-code :: no-hard-verdict :: - :: no action in the session cites this block
- amigo-5448a718-home-git-famigo-claude-md-1-start-here :: undecidable :: - :: the block names `.cursor/PROJECT.md` and call 187 (ev 667) edits it - but the block asks for it to be read *first*, and it was not read until T10
  revised: the Phase 8 second pass: a named file was touched, which ruling 3 counts, but for the opposite of what the block asks; the two readings are both defensible, so ruling 8 applies
  blind: yes
- amigo-5448a718-home-git-famigo-claude-md-2-scope-based-context :: used :: - :: the block prescribes the `famigo-admin` MCP tools with an explicit `environment` per call; calls 17 (ev 68) and 19 (ev 74) pass `"environment":"staging"`
  revised: the Phase 8 second pass: a cited action does exactly what the block prescribes
  blind: yes
- amigo-5448a718-home-git-famigo-claude-md-3-commit-message-format :: violated :: F-REDPATH :: `git commit -F-` at calls 200, 202 and 204 carries a 76-, 76- and 77-character subject against `first line <= 72 chars`, each followed by a multi-paragraph body against `no paragraphs`
  accept: the corpus's first `violated` truth. The after-run reaches it through the reviewed `snapshots/checks/famigo/5448a718/.../CLAUDE.md.checks.json`, frozen into the inputs in Phase 8 - so this row's improvement comes from a new judgement input as well as from the code, and the baseline could not have reached it at all
  revised: the Phase 8 second pass: the first pass called this `no-hard-verdict`; the blind pass measured the three subjects
  blind: yes
- amigo-5448a718-home-git-famigo-claude-md-4-quality-gate-mandatory :: used :: F-CMDMENTION :: the block's own fenced commands ran: `yarn type-check`, `yarn lint`, `yarn test` (the audit counted 21 gate runs across the session)
- amigo-5448a718-home-git-famigo-claude-md-5-after-finishing :: used :: - :: the block prescribes `/sync-agent-docs`, which was run at event 636
  accept: the block prescribes a slash command, but the trigger predicate only fires for a block that declares the trigger for its own skill; a compiled check would decide it
- migo-claude-rules-figma-design-system-md-0-figma-design-system-famigo-mobile :: used :: F-MOMENTS :: this block is a redirect whose whole content is two paths, and the session wrote both: `.claude/rules/figma-workflow.md` (calls 173, 175) and `.claude/rules/figma-tokens.md`, during the `/sync-agent-docs` turn
  accept: the dissent, recorded rather than dropped: the first pass and the blind pass both read this as `no-hard-verdict` because no Figma work happened this session, and the stub was plainly not consulted. Ruling 3 counts a file the block names being modified, and the plan's own finding was that the ruling had been applied only where the tool went green - so it is applied here too, against the reading that would have suited the scorecard better
  revised: the Phase 8 re-bake: seen while reading the after payload. Ruling 3 applied uniformly makes this `used`; leaving it `no-hard-verdict` would have kept a ruling the corpus applies elsewhere from applying here
  blind: no
- -git-famigo-claude-rules-figma-tokens-md-0-figma-design-tokens-patterns-famigo-mobile :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-1-design-tokens :: undecidable :: - :: the cluster style written at call 41 uses the palette's exact values (`#fa5f1c`, the iOS shadow pattern), which is either this block's tokens being reproduced or the repo-wide convention they describe
  revised: the Phase 8 second pass: the blind reading was `used` at low confidence; two readings of the same hex literals is what ruling 8 calls undecidable
  blind: yes
- -git-famigo-claude-rules-figma-tokens-md-2-styling-approach :: used :: - :: call 41 appends into the file's existing `StyleSheet.create`, the approach this block prescribes, and no styling library it rules out appears in any written chunk
  revised: the Phase 8 second pass: a cited write follows the approach the block prescribes
  blind: yes
- -git-famigo-claude-rules-figma-tokens-md-3-icon-system :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-4-component-patterns :: used :: - :: call 41's `ClusterMarker` is the functional-component pattern the block prescribes, keeping `accessibilityRole` and a translated `accessibilityLabel`
  revised: the Phase 8 second pass: a cited write follows the pattern the block prescribes
  blind: yes
- -git-famigo-claude-rules-figma-tokens-md-5-asset-handling :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-6-data-architecture :: used :: - :: hooks and services this block's tables name by path were modified: `hooks/useUserLocation.ts` (calls 42, 168), `hooks/useMapPlaces.ts` (45, 142), `services/location.ts` (38, 39)
  revised: the Phase 8 second pass: files the block names by path were modified, which ruling 3 counts
  blind: yes
- -git-famigo-claude-rules-figma-tokens-md-7-responsive-design :: no-hard-verdict :: - :: no action in the session cites this block
- -git-famigo-claude-rules-figma-tokens-md-8-testing-requirements :: used :: - :: component tests landed where the block requires them (`components/<feature>/__tests__/`) using `@testing-library/react-native`: calls 57, 97, 103, 155
  revised: the Phase 8 second pass: cited writes do what the block requires
  blind: yes
- -git-famigo-claude-rules-figma-tokens-md-9-figma-to-code-translation-checklist :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-0-figma-mcp-workflow-famigo-mobile :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-1-required-figma-to-code-workflow :: no-hard-verdict :: - :: no action in the session cites this block
- it-famigo-claude-rules-figma-workflow-md-2-tech-stack :: no-hard-verdict :: F-MOMENTS :: no Figma work happened this session
- it-famigo-claude-rules-figma-workflow-md-3-project-structure :: used :: - :: the block's own tree was edited at calls 173 and 175 after `utils/distance.ts` was created at call 127, and files it names by path were modified from call 47 onward
  revised: the Phase 8 second pass: files the block names by path were modified, which ruling 3 counts
  blind: yes
- 8a718-home-claude-skills-commit-skill-md-0-skill-commit :: used :: - :: `/commit` typed at event 682; Skill call 191
- 8a718-home-claude-skills-commit-skill-md-1-golden-rules :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-2-step-1-match-the-github-account :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-3-step-2-learn-the-commit-convention :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-4-step-3-check-the-branch :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-5-step-4-run-tests-lints :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-6-step-5-stage-and-commit :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- 8a718-home-claude-skills-commit-skill-md-7-step-6-report :: no-hard-verdict :: - :: the skill ran (`/commit` typed at event 682), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-0-reviewer :: used :: - :: `/review` typed at event 583
- git-famigo-claude-skills-review-skill-md-1-role :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-2-step-1-load-context :: used :: - :: the step says to read `CLAUDE.md` and, by scope, the `AGENT.md` files; call 167 (event 597, inside the `/review` turn) runs `sed -n '65,72p;95,100p' AGENT.md` and greps `../backend/AGENT.md`, and call 179 greps `CLAUDE.md`
  revised: the read join: this step's evidence is the run reading the files it names, which nothing recorded until now. Derived from the frozen action list after the after payload had been read, so not blind.
  blind: no
- git-famigo-claude-skills-review-skill-md-3-step-2-confirm-understanding :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-4-step-3-run-checks-before-review :: used :: - :: the three commands this step spells out ran verbatim - `yarn type-check` 18x, `yarn lint` 16x, `yarn test` 51x
  revised: ruling 4's change dropped this row to no-hard-verdict on the old evidence line, which named only the invocation. The step's own fenced commands did run, which is evidence of its own, so the row is `used` again on that ground rather than on the invocation. Found by reading the after payload, then confirmed against the frozen SKILL.md and the tool log.
  blind: no
- git-famigo-claude-skills-review-skill-md-5-step-4-review :: used :: - :: the step's item 1 asks whether the implementation aligns with `API_CONTRACT.md` and `AGENT.md`, and item 7 asks about swallowed errors: call 167 (event 597) reads `AGENT.md` and `../backend/AGENT.md`, call 76 reads `API_CONTRACT.md`, and call 166 (event 596) prints the `catch (err)` body of `hooks/useUserLocation.ts`
  revised: the read join: this step's evidence is the run reading the files it names, which nothing recorded until now. Derived from the frozen action list after the after payload had been read, so not blind.
  blind: no
- git-famigo-claude-skills-review-skill-md-6-step-5-apply-fixes :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-7-step-6-verify-documentation :: used :: - :: the step names `backend/AGENT.md`, `mobile/AGENT.md` and `README.md` and asks whether they are complete: calls 164, 167 and 170 grep `AGENT.md` for the entries the change would need, and calls 171 and 172 apply the doc fix
  revised: the read join: this step's evidence is the run reading the files it names, which nothing recorded until now. Derived from the frozen action list after the after payload had been read, so not blind.
  blind: no
- git-famigo-claude-skills-review-skill-md-8-step-7-mark-task-done :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-9-output-format :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-10-review-summary :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- git-famigo-claude-skills-review-skill-md-11-commit-message :: no-hard-verdict :: - :: the skill ran (`/review` typed at event 583), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-0-sync-agent-docs :: used :: - :: `/sync-agent-docs` typed at event 636
- o-claude-skills-sync-agent-docs-skill-md-1-role :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-2-step-1-understand-what-changed :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-3-step-2-discover-all-agent-facing-documentation :: used :: - :: the step says to re-scan for every agent-facing document and read the ones the change could affect: call 178 (event 641) lists `.cursor/`, `*/AGENT.md`, `*/CLAUDE.md`, `.cursor/PROJECT.md`, `.claude/rules/` and `.claude/skills/`, and call 179 (event 643) greps `CLAUDE.md`, `backend/CLAUDE.md`, `backend/AGENT.md`, `.cursor/PROJECT.md` and `README.md`
  revised: the read join: this step's evidence is the run reading the files it names, which nothing recorded until now. Derived from the frozen action list after the after payload had been read, so not blind.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-4-step-3-analyse-gaps-and-staleness :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-5-step-4-interview-if-uncertain :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-6-step-5-execute-updates :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- o-claude-skills-sync-agent-docs-skill-md-7-step-6-report :: no-hard-verdict :: - :: the skill ran (`/sync-agent-docs` typed at event 636), but nothing in the run cites this step
  revised: ruling 4 changed - an invocation records that the document ran, not that this step was carried out, so the identity block keeps the green and every other block has to earn one. This row's only evidence was the invocation.
  blind: no
- e-limiting-research-api-rate-limiting-md-0-api-rate-limiting-research-findings-implementation-brief :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-1-0-read-this-first-the-framing :: used :: - :: the agent verified this block's named claims with calls 112, 114, 115 and 116 before acting on them
  revised: the Phase 8 second pass: cited actions do what the block asks
  blind: yes
- e-limiting-research-api-rate-limiting-md-2-1-current-state-verified-in-this-repo :: used :: - :: call 116 checks this block's claim about the limiter regression test; ev 415 reports the result back
  revised: the Phase 8 second pass: a cited action tests the block's own claim
  blind: yes
- e-limiting-research-api-rate-limiting-md-3-1-5-work-already-applied-by-a-previous-agent-uncommitted-read-before-starting :: used :: - :: the block's five steps were executed in T8: calls 128, 130, 141, 142, 145, 146
  revised: the Phase 8 second pass: cited actions execute the block's own steps
  blind: yes
- e-limiting-research-api-rate-limiting-md-4-2-findings-from-published-sources :: no-hard-verdict :: - :: no action in the session cites this block
- e-limiting-research-api-rate-limiting-md-5-3-recommended-actions :: used :: - :: phase 1.0 was executed as listed (calls 127, 128, 141, 142, 145, 146) and verified live at call 208
  revised: the Phase 8 second pass: cited actions execute the block's own steps
  blind: yes
