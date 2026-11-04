# Plan: Make the judgement-reliability claim true

> Source: the independent review round of 2026-09-03 on branch `judgement-reliability` (commits a6dea90, 34d2c5b). No PRD file exists; the requirements are the reconciled findings of that round (verdict-auditor x2, verdict-ground-truth x2, test-weakening-detector, epistemic-honesty, privacy-supply-chain, generalization-reviewer, prompt-eval-designer). The claim under repair: "across 547 judged blocks, false greens 4 -> 0, false reds 11 -> 0, agreement 295 -> 521, 0 regressions."

## Approach

TDD throughout. Every phase starts by writing failing tests (red), then implements until they pass (green). No implementation code is written before its tests exist.

Two rules specific to this plan:

- **Fix the mechanism, then re-measure.** The scorecard is regenerated once, in Phase 8, after every predicate change has landed. Re-baking earlier measures the old bugs again.
- **Nothing in `snapshots/expected/` is edited after reading a payload.** Ground truth changes in Phase 8 are written from `snapshots/inventory.py` alone, by an agent that has not seen `snapshots/after/`, exactly as the expected.md header promises.

## Architectural decisions

Durable decisions that apply across all phases:

- **Snapshot corpus is private.** `snapshots/baseline/` and `snapshots/after/` never enter git. Every test and script that needs them skips with a loud message when they are absent, never fails and never silently shrinks to a smaller set without saying so.
- **Strong evidence needs a harness record of the block's own thing.** A green requires a `Skill` call or `<command-name>` wrapper, a write to a *file* the block names by path, the block's own template found in a written file, or a whole prescribed command that ran outside any string or heredoc body. A prompt mention, a directory name, a slash command read as a path, or a write to the block's own document is never strong evidence.
- **Block text is judged as delivered.** The rule text a verdict is about is the text the model saw in that session, taken from the transcript's file-read content and attachments, never from the file on disk today. When the delivered text cannot be recovered, the block is `undelivered`, not judged against today's wording.
- **Only a compiled check with a citable span renders red, anywhere on the page.** A low-confidence fallback finding renders as `unclear`. String and comment stripping is central and unconditional for every source-kind pattern; `ignore_strings` is removed as a per-check switch.
- **Truth classes stay coarse** (`used` / `violated` / `no-hard-verdict` / `undecidable`), and the corpus must contain at least one `violated` truth and one compiled checks file so the red path is measured, not assumed.
- **The acceptance test for the whole plan is external:** the same three verdict-auditor runs, on the same non-anchor sessions (famigo 9e01f3df, 78c658bc, 139cf0b9, 3f8c828d; formic-core 919f9e32, afe37732, 1916e68e, 5171447d; formicHMI 7eb46245, 13e972ee; reband 51fdcc25, 71c4d1ca, f7136fed, 113a0d2c; this repo 9cf0b16d, 406bba1d), report zero false greens and zero false reds.

Docs reviewed for staleness: `CLAUDE.md` (step 6 own-document exclusion, trigger-mention refusal, `_example_spans` claim, fallback-never-red claim, central string stripping claim), `README.md` trust-model section (same claims; snapshot privacy; calibration on a clone), `docs/judgement-reliability-research.md` §2 "Measured after the work", `snapshots/SCORECARD.md`, `snapshots/expected/*/expected.md` headers, `tests/test_regression_verdicts.py` module docstring. Each is attached to the phase that changes it below.

---

## Phase 1: Lock the door

**Findings addressed**: privacy-supply-chain (snapshots hold a production VPS address with ssh user, dev DB passwords, ~12k employer Jira references, a colleague's name, a personal email; not gitignored); test-weakening C2 and generalization A1 (a fresh clone fails `pytest`).

### Tests (write first - red)

- Test 1: with `snapshots/baseline/` renamed away, `pytest` reports the calibration corpus tests as *skipped* with a message naming the directory, and every other test passes.
- Test 2: `tests/test_scorecard.py`'s real-corpus test skips loudly (not silently returns) when `snapshots/expected/` or the baseline is absent.
- Test 3: the lexical fixture loader reports how many pairs it could resolve, and the calibration test fails if that number is below the inline-pair count (so a partial corpus cannot masquerade as the full one).
- Test 4: `git check-ignore snapshots/baseline snapshots/after` succeeds.

### Implementation (green)

Add both snapshot directories to `.gitignore`. Change the hard assertion on snapshot availability into a skip with a message, and make every early `return` / `continue` that depends on the corpus report itself the same way. Document in the README that the calibration corpus is the author's private sessions, that the scorecard is the author's measurement, and what a contributor can run without it.

### Docs to update

- [`README.md`](../../README.md) - trust-model section: the corpus is private, the scorecard cannot be regenerated by a contributor, calibration on a clone runs the inline pairs only.
- [`CLAUDE.md`](../../CLAUDE.md) - Tests section: same two facts in one sentence each.
- [`snapshots/sessions.json`](../../snapshots/sessions.json) - comment says `capture` needs the author's machine; keep, but add that the directories it captures into are gitignored.

### Acceptance criteria

- [ ] `git status` on a fresh clone shows no untracked snapshot directories after running `snapshots/take_baseline.py`.
- [ ] `pytest` on a checkout without the snapshot directories: 0 failed, skips named.
- [ ] `git log --all -- snapshots/baseline snapshots/after` is empty.

---

## Phase 2: A trigger needs an invocation

**Findings addressed**: formic auditor F5 (prompt "either /grill-prd or /prd-to-plan - you choose" greened the prd-to-plan skill via `trigger` while `skill-invocation` on the same record refused it); CLAUDE.md step 6 already states the rule the code does not follow.

### Tests (write first - red)

- Test 1: a block declaring `Trigger: `/foo`` in a session whose only record is `/foo` in a user prompt is `dormant` at every scope, and its moment card says the command was mentioned but not invoked.
- Test 2: the same block with a `Skill` call for `foo` is `used`; with a `<command-name>/foo</command-name>` wrapper is `used`.
- Test 3: a regression case for formic-core afe37732 turn 9 encoded as an in-memory event list (prompt mentions two commands, neither invoked): both pointer blocks `dormant`.
- Test 4: the existing "trigger agrees with the bounded matcher" tests still pass (bounded matching is unchanged; only the mention tier is demoted).

### Implementation (green)

The trigger predicate's applicability and match require the invocation kinds (`skill`, `wrapper`), exactly as `skill-invocation` does. A bare mention still produces the co-occurrence card it produces today, so the reader sees why nothing fired.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - step 6: the sentence about `_trigger_evidence` should say both predicates refuse a mention, not one.

### Acceptance criteria

- [ ] `cd ~/Git/formic/core && python3 <repo>/build_real_view.py --query afe37732 turn-9 blocks --no-all-sessions` shows no `used` on any prd-to-plan or grill-prd block.
- [ ] Every skill green the auditors verified as correct (the counter-anchors listed in `auditor-formic-reband.md`) is still `used`.

---

## Phase 3: A path join means a file

**Findings addressed**: famigo auditor F1, F7, F8; formic auditor F2, F3, F6, F7, F8; this session's survey (23 of 40 rule-doc greens across 21 non-anchor sessions rest on this predicate alone). Directory names (`docs/skills/`, `mobile/services/`, `app/src/`), slash commands (`/create-pr`) and headings are accepted as paths; any write beneath them greens the block; the block's own document is not excluded.

### Tests (write first - red)

- Test 1: a block naming `docs/skills/` in backticks is not `used` when the run writes `docs/skills/anything.md`.
- Test 2: a block naming `/create-pr` is not `used` when the run writes `~/.claude/skills/create-pr/SKILL.md`.
- Test 3: a block naming `CLAUDE.md` inside `~/Git/x/CLAUDE.md` is not `used` when the run edits `~/Git/x/CLAUDE.md` (own-document exclusion, matching what `template-echo` already does).
- Test 4: a block naming `docs/decisions/DECISIONS.md` is `used` when the run appends to `$M/DECISIONS.md` via heredoc (the memory-rule anchor must keep working); a block naming `backend/API_CONTRACT.md` is `used` when a python heredoc writes `API_CONTRACT.md` (`_shell_write_targets` learns `pathlib.Path(...).write_text` and `open(..., 'w')` inside `python3 - <<` bodies).
- Test 5: a heading token like `### `app/src/`` yields no named path.
- Test 6: the Polish/English twin fixture derives identical `writes-to-named-path` predicates before and after.

### Implementation (green)

Named paths require a final component that looks like a file (has an extension, or is a known dotfile) and must not begin with `/` followed by a known slash-command shape. The join requires the written path's final component to equal the named path's final component, then the contiguous-run rule applies to the directories above it. The block's own document is passed as `exclude_path` the way `template-echo` receives it. Shell write-target extraction gains the python-heredoc file-write shapes the famigo sessions use.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - step 6 "What the run did is evidence too": describe the file-only rule and the own-document exclusion for this predicate, and drop the sentence that claims the exclusion already exists.
- [`README.md`](../../README.md) - the evidence-tier paragraph, same correction.

### Acceptance criteria

- [ ] All nine greens the auditors ruled false (listed in `auditor-famigo.md` F1/F7 and `auditor-formic-reband.md` F2/F3/F6/F7) are no longer `used`.
- [ ] The Error Memory and Decision Memory greens in famigo 5448a718, 9dd3cc8a and reband 22c58939 are still `used`.
- [ ] famigo 5448a718 backend "API contracts" block is `used` (it was `dormant` while the session read and edited the file twice).

---

## Phase 4: Command echo reads commands, not strings

**Findings addressed**: formic auditor F1 (`just talos-hmi-lint` "ran verbatim" when its only occurrence was inside a PR-body heredoc in `gh pr create`); famigo auditor F11 (single-word fenced commands cannot reach `command-echo`, so 18 `pytest` runs did not credit the Tests block).

### Tests (write first - red)

- Test 1: a fenced `just foo` does not count as run when `just foo` appears only inside a heredoc body or a quoted string argument of another command.
- Test 2: the same fenced command counts when it runs as its own command, including as one segment of an `&&` chain.
- Test 3: a single-word fenced command (`pytest`) in a shell-tagged fence reaches `command-echo` when the session ran it as a whole command, and does not when it appears only as an argument of another command.
- Test 4: the reband "Build / run / test" block, whose commands sit in inline backticks in prose, stays where it is (this phase does not widen echo to inline spans; that is a separate, later decision).

### Implementation (green)

Command echo splits each bash command into segments and strips heredoc bodies and quoted strings before comparing; a fenced command matches only a whole segment. Single-word fenced commands are eligible for echo under the same whole-segment rule, and the weak `command-mention` tier no longer claims them when echo has already credited them.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - step 6 command-echo paragraph: whole-segment matching, heredoc and string exclusion, single-word eligibility.

### Acceptance criteria

- [ ] formic-core 919f9e32 "Available commands" block is not `used`.
- [ ] this repo's 9cf0b16d "Tests" block is `used` on the `pytest` runs.
- [ ] famigo Quality Gate greens (verbatim `yarn type-check && yarn lint && yarn test`) unchanged.

---

## Phase 5: Fallback never renders red, strings stripped centrally

**Findings addressed**: epistemic finding 2 and famigo auditor F4 (`rule violated (low confidence, fallback)` in red on famigo mobile "Key patterns", citing `expo.version` inside a template-literal string in the script the rule prescribes); this session's check that string stripping is opt-in per check (`ignore_strings`) while CLAUDE.md and README say it is central; the `fallback` negation ignores the rule's exception clause.

### Tests (write first - red)

- Test 1: a fallback finding is reported with state `unclear`, never `violated`, and the rendered rule line and page panel carry no red for it.
- Test 2: a source pattern matching only inside a JS template literal, a double-quoted string or a single-quoted string yields no `violated` finding for any check, with or without `ignore_strings` in the record (the field is accepted and ignored, for v1 files).
- Test 3: the strict-vs-stripped agreement rule is exercised: strict match present, stripped match absent, state `unclear`.
- Test 4: the page's rule-check renderer has one path for `unclear` and it is what a fallback finding takes (asserted on the baked `ruleCheck` record, not on HTML strings).

### Implementation (green)

`strip_comments_and_strings` strips strings unconditionally for source kinds, template literals included, offsets preserved. Fallback findings are constructed with state `unclear` and a message saying the pattern was mechanically extracted. Loader accepts `ignore_strings` for backward compatibility and does nothing with it.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - Rule checks "What load time enforces" bullet: now true; Fallback paragraph: says `unclear`, not "never turns a block red".
- [`README.md`](../../README.md) - same two statements.
- [`prompts/translate-rules.md`](../../prompts/translate-rules.md) - remove `ignore_strings` from the field list if present.

### Acceptance criteria

- [ ] famigo 9e01f3df "Key patterns" block: rule line `unclear`, no red anywhere in the rendered page for it.
- [ ] Every `tests/test_tool_checks.py` and `tests/test_rule_checks.py` violated case still violated.

---

## Phase 6: Judge block text as delivered

**Findings addressed**: famigo auditor F7 (two greens in this repo's session 406bba1d cite a CLAUDE.md sentence first committed eight hours after the session ended); both blind ground-truth analysts noted frozen rule docs are post-session versions; famigo auditor F4 (the rule line that produced the red was added by the session's own commit).

### Tests (write first - red)

- Test 1: a block whose text differs between the file on disk and the content the transcript shows the model read is judged on the transcript's content; the disk version's extra sentence derives no predicate.
- Test 2: a file the session itself edited is judged, for turns before the edit, on the pre-edit text and, for turns after, on the post-edit text the transcript shows.
- Test 3: when the delivered content of a range cannot be recovered (harness-injected file with no read record and no attachment), the block is judged on the disk text and the payload carries `textSource: "disk"` so the page and `--query` can say so.
- Test 4: block ids are stable across the two sources (slugs come from the heading, which is the same in both).

### Implementation (green)

Context-file loading records, per file and per turn, the text as delivered: from `Read` tool results, `nested_memory` / `file` attachments and the harness's instruction injection, falling back to disk with an explicit marker. Predicate derivation and the lexical tier read the delivered text. The block record carries `textSource` (`transcript` | `disk`), and the reason line for a disk-sourced block ends with one clause saying the wording may postdate the session.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - step 5 Context-file loading: delivered text vs disk text, the marker, the fallback.
- [`docs/reading-transcripts.md`](../../docs/reading-transcripts.md) - where delivered content lives in the event shapes, if not already covered.
- [`snapshots/expected/*/expected.md`](../../snapshots/expected/) - header note: verdicts are against the delivered text; the frozen file copies are for reference only.

### Acceptance criteria

- [ ] this repo's 406bba1d "Tests" and "Architecture" blocks are not `used`.
- [ ] `--query <sid> <block-id>` prints `text  disk` or `text  transcript` for every block.
- [ ] The eight anchor sessions re-bake without error.

---

## Phase 7: A regression harness that can fail

**Findings addressed**: test-weakening R1 (16 of 47 cases in `tests/test_regression_verdicts.py` derive zero predicates, so `status != "ignored"` passes regardless of implementation), R2 (two trigger cases test agreement, not correctness), C1 (the 0.90 precision gate never trips on a single loosened threshold; the real guard is the exact-count pin), and the `test_only_a_compiled_check_can_call_a_rule_violated` gap (no compiled check ever in the mix, no credit-only predicate ever applicable).

### Tests (write first - red)

This phase is about tests, so "red" means each rewritten case is shown to go red under a deliberate probe before the probe is reverted:

- Test 1: every `f_eom`, `f_pathtable` and `f_combine` case gets a fixture that derives at least one predicate or carries a compiled checks file beside it, and each is shown to fail under one of the recorded probes (P3, P6, P7, P13b from `test-weakening.md`).
- Test 2: the counter-anchor `eom` cases assert the exact status (`unused` with a stated reason), not a negation.
- Test 3: `test_only_a_compiled_check_can_call_a_rule_violated` copies the worked example *with* its checks file and includes a busy command that echoes a fenced command, so both a compiled check and a credit-only predicate are live in the run.
- Test 4: the calibration gate's precision assertion is accompanied by an exact false-positive count of zero on the labelled set (already present as a separate test; fold the two so a single loosened threshold trips the gate, and document the granularity in the test docstring).
- Test 5: the harness module docstring no longer promises `xfail(strict=True)` for unlanded fixes unless a live case uses it.

### Implementation (green)

Rewrite the fixtures; no production code changes in this phase. Every probe used to prove a case can fail is listed in the test file's docstring with the line it trips.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - Tests section paragraph on `tests/test_regression_verdicts.py`: state what a vacuous case is and that every case derives a predicate or carries a checks file.
- [`tests/test_regression_verdicts.py`](../../tests/test_regression_verdicts.py) - module docstring.

### Acceptance criteria

- [ ] For each of the 16 previously vacuous cases, a one-line probe recorded in the docstring turns it red; `git status` clean after.
- [ ] `pytest -k calibration` fails when `COVERAGE_FLOOR` is set to 0.0 on disk (probe reverted).
- [ ] Total test count is not the measure; every remaining case has a recorded way to fail.

---

## Phase 8: Blind ground truth, second pass, and the first real violation

**Findings addressed**: the 8 rows whose truth moved from `no-hard-verdict` to `used` after the after-run was read (under first-pass truth: 8 false greens, 7 regressions); the descriptive-block ruling applied where the tool went green and not elsewhere (famigo 5448a718 "API contracts"); zero `violated` truths and zero compiled checks files in the corpus, so "false reds 11 -> 0" measures nothing; the blind analyst's verified violation (famigo 5448a718 commits with 76-77 character subjects and paragraph bodies against "first line ≤ 72 chars; no paragraphs"); blind-vs-committed disagreement on 7 of 48 reband and 21 of 75 famigo rows, all `used` vs `no-hard-verdict` on descriptive or read blocks.

### Tests (write first - red)

- Test 1: `snapshots/compare.py` refuses to score an expected.md whose header does not state the descriptive-block ruling verbatim, and refuses a row carrying `revised:` that does not also carry `blind: yes|no`.
- Test 2: the scorer reports, as its own line, how many scored rows are `violated` truths and how many sessions carry a checks file; a corpus with zero of either prints a warning in the scorecard header saying the red side is unmeasured.
- Test 3: a compiled `tool_arg_matches` check for the famigo commit-message rule, with fixtures, loads and reports `violated` on the frozen famigo 5448a718 inputs with three citable spans (the three `git commit -F-` subjects).
- Test 4: the same check reports `not-exercised` on a session with no commits.

### Implementation (green)

1. Write the descriptive-block ruling once, as a numbered rule in a shared `snapshots/expected/RULINGS.md`, and make every expected.md header reference it. The ruling must say explicitly whether "a file created under a directory the table names" counts (the blind reband analyst ruled it does not; the committed reband truth ruled it does).
2. Re-derive ground truth blind for the eight revised rows and for every row the two blind analyses disputed, using the `verdict-ground-truth` agent on `snapshots/inventory.py` only. Where the blind analyst and the committed truth still disagree, the row becomes `undecidable` with both readings quoted.
3. Add `violated` to the corpus: famigo 5448a718 `commit-message-format` with the three cited subjects; check the other seven sessions' commits against their own commit-format rules the same way.
4. Compile one real checks file for the frozen famigo project CLAUDE.md (commit-message and quality-gate rules) via `/compile-rules`, review it, and freeze it into the famigo inputs so the after-run exercises the compiled red path.
5. Re-bake `snapshots/after/` and regenerate `snapshots/SCORECARD.md`. Report the skill-block half and the rule-document half as separate tables, because they measure different things.

### Docs to update

- [`snapshots/expected/RULINGS.md`](../../snapshots/expected/RULINGS.md) - new; the rulings every expected.md applies.
- [`snapshots/expected/*/expected.md`](../../snapshots/expected/) - headers reference RULINGS.md; revised rows carry `blind:`.
- [`snapshots/SCORECARD.md`](../../snapshots/SCORECARD.md) - regenerated; two tables; red-side coverage line.
- [`docs/judgement-reliability-research.md`](../../docs/judgement-reliability-research.md) - §2 "Measured after the work": replace the table with the regenerated numbers, split skill vs rule-document, name the number of `violated` truths and compiled files in the corpus, and drop "0 false reds" as a headline unless the red path was exercised.
- [`CLAUDE.md`](../../CLAUDE.md) - Tests section: the scorecard has two halves and why.

### Acceptance criteria

- [ ] Zero rows in `snapshots/expected/` carry `revised:` without `blind:`.
- [ ] The scorecard header states the count of `violated` truths (≥ 1) and compiled checks files (≥ 1) in the corpus.
- [ ] Regenerated scorecard: false green after = 0 and false red after = 0 *under the blind truth*, and the rule-document table is reported on its own.
- [ ] The famigo commit-message rule shows `ignored` with three cited spans in the after payload.

---

## Phase 9: External re-audit and claim rewrite

**Findings addressed**: the whole plan's acceptance test. The scorecard is self-graded by construction; the claim is safe only when sessions outside the calibration set stop producing false verdicts.

### Tests (write first - red)

- Test 1: a script under `snapshots/` lists the non-anchor audit sessions per project (the sixteen named in Architectural decisions) so the audit is repeatable, and a test asserts none of them appears in `snapshots/sessions.json`.
- Test 2: `tests/test_generalization.py::test_no_prose_derived_strong_predicate_survives_anywhere` and the structural-evidence positive controls still pass after Phases 2-6.

### Implementation (green)

Run the `verdict-auditor` agent three times (famigo + this repo; formic-core + formicHMI; reband) on the listed sessions with the same prohibitions as the review round (no access to `snapshots/SCORECARD.md`, `snapshots/expected/`, `snapshots/after/`, `snapshots/baseline/`). Run `epistemic-honesty` once on fresh `--query` output and a fresh report. File every verified finding; a false green or false red fails this phase and returns to the phase that owns the mechanism. When the gate passes, rewrite the public claim in the research doc and README in the form the numbers support: the rule-document improvement, the skill-block ruling stated as a ruling, the red side's coverage, and the external audit's result with its session list.

### Docs to update

- [`docs/judgement-reliability-research.md`](../../docs/judgement-reliability-research.md) - §2 claim paragraph and the two caveats.
- [`README.md`](../../README.md) - any sentence quoting the scorecard numbers.
- [`snapshots/SCORECARD.md`](../../snapshots/SCORECARD.md) - footer: date and session list of the last external audit that passed.

### Acceptance criteria

- [ ] Three auditor reports, each stating explicitly: zero false greens, zero false reds, on the listed sessions.
- [ ] Epistemic report: no overclaiming finding above "minor wording".
- [ ] No sentence anywhere in the repo states "0 false reds" without the red-side coverage beside it.
- [ ] `pytest` green; `git status` clean; snapshot directories still untracked.
