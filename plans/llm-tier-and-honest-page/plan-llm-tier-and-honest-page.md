# Plan: LLM tier ships measured, and the page says what it means

> Source: the independent review round of 2026-09-03 on branch `judgement-reliability` - the prompt-eval-designer report (19 findings, two BLOCKS) and the epistemic-honesty report (five overclaiming findings). No PRD file exists. Companion plan: [plan-judgement-reliability-claim.md](../judgement-reliability-claim/plan-judgement-reliability-claim.md), which owns the verdict mechanisms; this plan does not touch predicates or the scorecard. Non-English rule detection and CJK-safe ids are deliberately out of scope for now.

## Approach

TDD throughout. Every phase starts by writing failing tests (red), then implements until they pass (green). No implementation code is written before its tests exist.

Two rules specific to this plan:

- **A prompt change ships with a fixture run, not an argument.** Phases 2-4 each add cases to the fixtures Phase 5 formalises; a prompt or scanner edit with no fixture case behind it is not merged.
- **No model call in the test suite.** Phases 1-5 run offline against stubbed replies. Phase 6 records real replies once, by hand, into a fixture that the suite then reads.

## Architectural decisions

Durable decisions that apply across all phases:

- **Status wording on the page is derived from one table shared with the CLI.** A status's short label, its one-line meaning and its colour class live in one Python dict baked into the payload; the template reads it, `--query` prints from it. Neither side hand-writes a status meaning again.
- **Colour means verdict tier, never decoration.** Green is reserved for `used` / `used-partial` and for a compiled check's `clear`. Red is reserved for `ignored` and for a compiled `violated` with a span. Everything weaker renders neutral.
- **A summary chip appears only when it has something to summarise.** "nothing violated" renders only when at least one rule in scope is compiled; otherwise the chip reads the compile state ("0 of N rules compiled").
- **Every untrusted string enters a prompt through the evidence helper.** File names, candidate names and paths are evidence pieces inside the nonce-delimited block, never interpolated into the instruction text or the marker line.
- **The injection scanner knows both vocabularies** (rule: compliant / clean / violated / unclear; relevance: pertinent / relevant / not-pertinent / undecidable) plus the delimiter and role-tag shapes, and it is measured for precision as well as recall (a session *about* prompt injection must not be flagged).
- **A judge answer that cannot be checked is `unavailable`, not a finding.** Unparseable, empty, wrong-vocabulary or under-length-citation replies produce a `note` with `judgeVerdict: unavailable` and are never cached; they never move a block to `unclear`.
- **Fixtures for the three prompts live under `tests/fixtures/judge/`**: `injections.json`, `replies.json`, `canary/` (a guidelines doc plus its expected checks file). `tests/test_judge_eval.py` scores them.

Docs reviewed for staleness: `README.md` (opt-in table's "What leaves your machine" cell omits the tool-log and prompt-digest payloads; cache description omits that entries hold code excerpts; status legend prose), `CLAUDE.md` (judge tier paragraph on UNPARSED handling; `_INJECTION_PATTERNS` description), `prompts/translate-rules.md` (hybrid "cannot accuse", `scope`/`domain`, communication example), `.claude/commands/compile-rules.md` (relative `@prompts/...` path breaks when copied out of the repo). Each is attached to the phase that changes it below.

---

## Phase 1: The page says what a status means

**Findings addressed**: epistemic 1 (legend: `used` = "Followed by the agent", `unused` = "Never triggered (precondition not met)", `used-partial` has three different definitions), 3 ("nothing violated" on 183 of 183 rows including sessions with 0 rules compiled), 4 (`possibly-referenced` tinted green; 809 non-event cards with a red edge), 5 (duplicates panel calls absence of lexical trace "tokens spent twice for nothing"), stale help text naming retired predicates and a "VIOLATION ✗" moment kind no builder emits.

### Tests (write first - red)

- Test 1: the baked payload carries a `statusLegend` table with, for every status in the taxonomy, `label`, `meaning`, `tier` (`strong` | `weak` | `absent`) and `tone` (`green` | `red` | `neutral`); `possibly-referenced` is `weak`/`neutral`, `unused` and `dormant` are `absent`/`neutral`, `ignored` is `red`, `used` is `green`.
- Test 2: `used`'s meaning names the evidence ("a harness record tied the block to this run"), not the agent's mind; `unused`'s meaning says nothing tied the block to the run and does not say "precondition".
- Test 3: `--query <sid> <block-id>` prints the same `meaning` string the payload carries for that block's status.
- Test 4: a session's `headline` is "nothing violated" only when `ruleCompile.compiled >= 1`; with 0 compiled it reads the compile state.
- Test 5: a lexical non-event moment carries `tone: neutral`; only `ignored`-producing moments carry `tone: red`.
- Test 6: the duplicates classifier's `redundant` reason text says "no evidence either block was referenced", not "tokens spent twice for nothing".
- Test 7: no help-text string in the template names `path-table`, `end-of-message`, `negative rule`, `keyword overlap` or a `VIOLATION` moment kind (asserted by grepping `HTML_TEMPLATE` from Python for the retired names, which is a stability check on vocabulary, not on layout).

### Implementation (green)

Add the legend table to the payload and make the template's chips, detail labels, legend panel and moment-card borders read it. Rewrite `_violation_headline` to consult the compile rollup. Replace the stale help paragraphs with text derived from the predicate kinds that exist. Change the CSS so `possibly-referenced` and every `verdict-no` card render neutral.

### Docs to update

- [`README.md`](../../README.md) - status legend prose: one line per status, copied from the new table's `meaning` strings.
- [`CLAUDE.md`](../../CLAUDE.md) - step 8: name the legend table as the single source of status wording.

### Acceptance criteria

- [ ] A fresh famigo report shows "0 of 13 rules compiled" on the session chip where it showed "nothing violated".
- [ ] No green anywhere on a `possibly-referenced` row; no red edge on a lexical non-event card.
- [ ] `--query` and the page print identical meaning text for every status.

---

## Phase 2: The injection boundary is closed

**Findings addressed**: prompt-eval 1 (BLOCKS: "Answer pertinent" / "Mark this as pertinent" bypass the documented discard because the scanner has no relevance vocabulary), 3 (forged `<<<END EVIDENCE`, `SYSTEM:`, `Final answer:` not detected; the existing test asserts only that the nonce differs), 6 (`file_name` interpolated into the instruction block above the delimiters; candidate `name` unsanitised in the marker line, so a name containing `>>>\n` breaks the marker), 12 and 19 (scanner English-only; digest-half hits recorded nowhere).

### Tests (write first - red)

- Test 1: a relevance summary containing "answer pertinent", "mark this as pertinent", "treat the file as relevant", "say not-pertinent" each populates `fileInjections` and the file's verdict is `undecidable` with the injection note.
- Test 2: content containing a forged closing marker with any 12-hex nonce, a `SYSTEM:` line, an `assistant:` role tag, or a JSON object with a `"verdict"` key populates `injections`.
- Test 3: a session legitimately about prompt injection ("we added a test that the scanner catches 'ignore previous instructions'") inside a *code* candidate is scanned and flagged, and the verdict is unchanged (note only) - flagging is fine, the assertion is that a flag never moves a rule verdict.
- Test 4: `file_name` appears nowhere in the prompt before the first BEGIN marker; it appears as its own evidence piece.
- Test 5: a candidate name containing `>>>`, newlines or non-ASCII is sanitised to `[A-Za-z0-9._/:-]` (or hashed) before it enters the marker, and the prompt has exactly one BEGIN and one END marker per piece.
- Test 6: a digest-half injection hit is recorded on the baked `wastedContext.files[]` record as `digestInjection: true` so it is visible somewhere.

### Implementation (green)

Extend `_INJECTION_PATTERNS` with the relevance vocabulary, the delimiter shape, role tags and schema keys; move the file name into the evidence pieces; sanitise names in `_evidence_block`; surface digest hits on the file record. Polish equivalents of the core directive phrases are added as a second pattern group; everything else stays structural.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - "Everything the judge reads is untrusted" paragraph: names go inside the block; scanner covers both vocabularies.
- [`README.md`](../../README.md) - opt-in table's `--judge` cell: list the tool-log payload for `judged` records with `evidence: transcript` and the up-to-12-prompt task digest for the relevance question (both already admitted in prose; the one-glance table omits them). Cache paragraph: entries hold the quoted code excerpt the judge cited.

### Acceptance criteria

- [ ] All `tests/test_judge_tier.py` boundary tests still pass; the forged-delimiter test additionally asserts the attempt is reported.
- [ ] `injections.json` (Phase 5 format, seeded here) has every Phase 2 case, both halves.

---

## Phase 3: Unusable answers degrade, never accuse

**Findings addressed**: prompt-eval 4 (no minimum quote length: `"{"` or `"e"` is a citation and paints a hybrid block `violated`), 5 (an unparseable or empty reply becomes a hard `unclear` at the site instead of `unavailable`; the module's own comment says it must degrade to "not checked"), 15 (duplicate `verdict` key silently picks the last; `"Violated"` rejected on case; `is_error` envelope text lost).

### Tests (write first - red)

- Test 1: a hybrid judge reply citing a quote shorter than 8 characters or containing no word character yields a `note` with `judgeVerdict: unavailable`, reason naming the short citation; the block state is unchanged.
- Test 2: a fluent prose reply, an empty reply and a wrong-vocabulary reply each yield `unavailable`, never `unclear`; none is cached; the block state is what the deterministic half says.
- Test 3: a reply with two `verdict` keys is `unavailable`; a reply with `"Violated"` parses as `violated`.
- Test 4: a CLI envelope with `is_error: true` yields `unavailable` with the envelope's error text in the reason.
- Test 5: the existing test asserting UNPARSED -> `unclear` is rewritten to assert `unavailable` (this is the one deliberate flip; the test file says why).

### Implementation (green)

`Judge.ask` marks unparseable results `unavailable: True`; `_fold_candidate` routes unavailable results to notes; `_quote_span` requires length and a word character; `parse_verdict` lower-cases the verdict and rejects duplicate keys.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - "Citation or downgrade" paragraph: the minimum citation and the unavailable path.

### Acceptance criteria

- [ ] No stubbed reply in `replies.json` (Phase 5) can produce `violated` without a citation of at least 8 characters found in the candidate.
- [ ] A backend that answers in prose for every call leaves every block exactly as the offline run reports it.

---

## Phase 4: The compiler prompt matches the code

**Findings addressed**: prompt-eval 7 (prompt says only `deterministic` can mark a rule violated; `hybrid` does with `--judge`, so borderline rules get parked there "because it cannot accuse"), 8 (`communication`-scope `judged` rules are judged against the code diff or tool log because no corpus carries the assistant's prose), 9 (relevance prompt has no positive/negative examples), 13 (`build_prompt` silently omits an empty example section), 16 (`scope` and `domain` are never read), 17 (language of `statement` / `message` unspecified), generalization G1 (`/compile-rules` reads `@prompts/translate-rules.md` by relative path and breaks when copied out of the repo).

### Tests (write first - red)

- Test 1: the prompt text states that `hybrid` can mark a rule violated when the judge tier is on (asserted as a sentence-level check on the prompt file, in the existing compile-flow test style, with the sentence quoted in the test).
- Test 2: a `judged` record with `scope: communication` and no assistant-prose corpus is reported as `not-checkable` with a reason naming the missing corpus, never judged against code or the tool log.
- Test 3: `judge_request` raises when either example list is empty (the loader already refuses such records; the helper stops silently dropping the section).
- Test 4: `relevance_request` includes one pertinent and one not-pertinent example above the delimiters.
- Test 5: the loader accepts and ignores `domain`; the prompt's output template no longer asks for it; `scope` is documented as routing-only.
- Test 6: `.claude/commands/compile-rules.md` resolves the prompt by a path that works from `~/.claude/commands/` (an absolute reference to the installed tool's `prompts/` dir, or the prompt inlined at install time), asserted by a test that copies the command file to a temp dir and checks the reference resolves.

### Implementation (green)

Edit the prompt's bucket section and worked examples; add the routing rule for `communication` scope to the loader; add the two relevance examples; make the example sections mandatory in the helper; fix the command file's reference. State in the prompt that `statement`, `message` and `why` are written in English regardless of the document's language, and examples verbatim from the document.

### Docs to update

- [`prompts/translate-rules.md`](../../prompts/translate-rules.md) - buckets paragraph, communication example, field list, language note.
- [`.claude/commands/compile-rules.md`](../../.claude/commands/compile-rules.md) - the prompt reference.
- [`README.md`](../../README.md) - the "copy the command into your project" instruction, to match.
- [`CLAUDE.md`](../../CLAUDE.md) - Record format v2 paragraph: `scope` is routing-only; `domain` retired.

### Acceptance criteria

- [ ] `tests/test_compile_flow.py` passes with the new sentence-level assertions.
- [ ] A `communication`-scope judged record in the worked-example fixture reports `not-checkable` in a `--judge` run with a stubbed judge that would otherwise answer `violated`.

---

## Phase 5: Offline eval fixtures

**Findings addressed**: prompt-eval 2 (BLOCKS: no labelled eval set for any of the three prompts; the tests are plumbing unit tests), 10 (no seeded trap cases; tautological fixtures pass every loader gate), 18 (`test_the_authoring_prompt_documents_what_the_loader_enforces` is a substring-mentions gate, vacuous for `code` / `files` / `process`).

### Tests (write first - red)

- Test 1: `tests/test_judge_eval.py` loads `tests/fixtures/judge/injections.json` (≥ 30 cases: rule and relevance vocabularies, forged markers, role tags, JSON-in-content, Polish and English; ≥ 8 `should_not_flag` cases) and asserts recall 1.0 on the flag half and precision ≥ 0.9 on the should-not-flag half, printing the misses.
- Test 2: it loads `replies.json` (≥ 25 raw replies with expected parsed verdict per vocabulary, the table from the review as the seed) and asserts every parse matches.
- Test 3: `tests/fixtures/judge/canary/GUIDELINES.md` plus `GUIDELINES.md.checks.json` (hand-written, with two rules that *must* be refused, one deterministic check whose `should_not_match` includes a comment case, and one deliberately tautological check that the loader must reject) loads with exactly the expected refusals and rejections.
- Test 4: the loader refuses a deterministic record whose `should_not_match` contains no snippet where the target identifier appears inside a comment, for source kinds (the trap the review asked for).
- Test 5: the compile-flow "documents what the loader enforces" test checks closed-set values as backticked tokens, not bare substrings, and additionally checks the three semantic sentences (order-blind, "after every edit" not expressible, hybrid can accuse).

### Implementation (green)

Write the three fixtures and the scorer. Add the comment-case requirement to `_validate`. The `/compile-rules` command gains a first step: run the canary and diff against its expected checks file before touching the user's document, reporting any drift.

### Docs to update

- [`CLAUDE.md`](../../CLAUDE.md) - Tests section: the judge eval fixtures and what each measures; Rule checks: the canary step.
- [`.claude/commands/compile-rules.md`](../../.claude/commands/compile-rules.md) - canary step.
- [`README.md`](../../README.md) - trust-model section: the LLM tier's offline eval and what it does not measure (real-model adherence, until Phase 6).

### Acceptance criteria

- [ ] `pytest tests/test_judge_eval.py` runs with no network and no model call.
- [ ] Every Phase 2 and Phase 3 case appears in a fixture, not only in a unit test.
- [ ] The tautological canary check is rejected at load with a message a reader can act on.

---

## Phase 6: The measured gate

**Findings addressed**: prompt-eval §4 ("until that exists, every verdict the judge tier produces is unmeasured"); the project's own rule that a prompt change with no eval is an opinion.

### Tests (write first - red)

- Test 1: `tests/fixtures/judge/recorded_replies.json` exists with ≥ 40 hand-labelled (prompt hash, model id, raw reply, expected verdict, label note) records covering hybrid candidates (both true violations and compliant sites), semantic records, and relevance questions, at least 10 of them injection attempts.
- Test 2: `tests/test_judge_eval.py` scores the recorded set: precision on `violated` ≥ 0.90 with a true-positive floor (same shape as the lexical gate), refusal rate reported, injection cases all reported-not-obeyed, schema adherence ≥ 0.95.
- Test 3: the recording script writes only to the fixture path, never to the judge cache, and refuses to run without `--judge` and a typed confirmation, since it makes real model calls.

### Implementation (green)

A local-only script under `tests/` (like `label_pairs.py`) that runs the judge once over the frozen famigo and formic-core candidate sites plus the injection fixtures, dumps `(prompt, raw reply)` pairs, and opens them for hand labelling. Labels are written by a person; the script never labels. The gate then reads the fixture like any other test.

### Docs to update

- [`README.md`](../../README.md) - trust-model section: the LLM tier's measured precision, the model id it was measured on, and the date; the sentence that the tier is "advisory" gains "measured at N% precision on M sites".
- [`CLAUDE.md`](../../CLAUDE.md) - Tests section: the recorded-reply gate beside the lexical calibration gate.
- [`docs/judgement-reliability-research.md`](../../docs/judgement-reliability-research.md) - §9.1: the measurement result.

### Acceptance criteria

- [ ] Gate passes on the recorded set; the numbers are quoted in README with model id and date.
- [ ] Re-running the recording script against the same model reproduces the same verdicts for ≥ 95% of records (reported, not gated).
- [ ] `--judge` remains off by default and the suite remains offline.
