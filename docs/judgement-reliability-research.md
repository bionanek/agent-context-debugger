# Judgement reliability: audit + research reference

Date: 2026-09-03. Produced by a full analysis pass over the verdict logic: code review of the
three core pillars, transcript audits of 14 real sessions across 4 projects (~3,900 block
verdicts, every reported finding verified against the raw `.jsonl`), and three deep research
tracks (instruction-following evaluation literature, stdlib-grade lexical matching, agent-trace
attribution). This file is the reference for any future work on the judging mechanism.

Status of the code at the time of this analysis: commit `3bc378e`.

---

## 1. How the current logic works (the three pillars)

### Pillar 1 - recognising rules in files
- `parse_claude_md` (build_real_view.py ~104) splits CLAUDE.md / rules / skills at H1/H2
  headings, skipping headings inside code fences. **The block is the unit of judgement**,
  never the individual sentence-level rule inside it.
- `classify_block` (~149) types blocks by crude keyword tests: "always"/"never"/"must" → rule,
  "trigger:" or a backticked `/cmd` → skill, "see "/"@"/".md)" → reference. English-only.

### Pillar 2 - turning rules into checkable items
- `derive_predicates` (~1790) extracts exactly **4 predicate kinds** from prose:
  - `trigger` (strong): "Trigger: /foo" or "When the user types `/foo`". BUG: the predicate
    lambda uses bare substring `c in user_prompt` (~1829-1830) while the moments builder uses
    the properly right-bounded `_is_triggered` (~1375) - the two disagree, see F-TRIGGER below.
  - `path-table` (strong): a markdown table matching "Project path contains" - literally the
    header of the author's own global CLAUDE.md gh-account table. Applicability = cwd contains
    a row token; satisfaction = the row's backticked command appears as a *substring of any
    bash command*.
  - `command-mention` (weak): every backticked token whose first word looks command-shaped
    (lowercase, ≥2 chars, small stopword list). Its `matches()` is **unconditionally true**
    (~1905).
  - `end-of-message` (strong): fires on the author's summary-rule phrasing ("user-facing
    summary", "1-3 sentences", "end your response"). Compliance = final paragraph ≤4
    sentences AND no file-extension / controller|service|schema|route words **anywhere in the
    whole final message**; applicability = any Edit/Write/MultiEdit call, `.md` docs included.
- `rule_checks.py`: the compiled-checks path. `.checks.json` beside a guideline doc
  (authored once via prompts/translate-rules.md in a Claude session, reviewed, committed),
  8-kind vocabulary (`forbidden_pattern`, `required_pattern`, `forbidden_co_occurrence`,
  `required_co_occurrence`, `required_order`, `forbidden_command`, `required_command`,
  `forbidden_path`), self-tests re-run at load, comment/string stripping, strict+stripped
  agreement required, `ctx-allow` suppression. Only this path may call a rule `violated`.
  Plus a narrow mechanical fallback (negation cue + backticked code-shaped token, low
  confidence, never turns a block red). **Well-designed but starving: none of the audited
  projects has a checks file.**

### Pillar 3 - judging usage
- `assess_block` (~2626): delivery gates first (`not-loaded`, `undelivered` from
  `delivered_ranges`); then strong predicate applicable+satisfied → `used`, unsatisfied →
  `ignored`, mixed → `used-partial`; weak hits only → `possibly-referenced`; predicates but
  none applicable → `dormant`; **no predicates → keyword fallback**: the block's FIRST 8
  five-plus-letter words, ≥2 appearing anywhere in `all_assistant_text` → `possibly-referenced`,
  else `unused`.
- Moments ("How the agent ended up here"): assistant text segments ranked by overlap with the
  block's first 12 "distinctive" tokens (`_block_keywords`, stopword list is small and
  English) plus a causal-phrase regex (`CAUSAL_RE`: "Let me", "because", ...). For weak
  verdicts the cards imply causality that does not exist.
- `combine_verdicts` (~495) ranks `ignored` > `used` > `used-partial` > `possibly-referenced`
  > NOT-USED. The session-scope `reason` is regenerated independently of the combined status.

### What the judging reads vs what it ignores
Reads: visible assistant text, bash command strings, Edit/Write tool-call presence, user
prompt, cwd, Read calls. **Never reads:** Skill tool invocations (used only for skill
*loading*), the content written via Write/Edit, writes to files a rule names by path,
bash-heredoc edits, tool-call *ordering*, thinking text (hardcoded to `""` at ~2874 - but in
a recent famigo transcript 43/82 thinking blocks carried readable text; availability is
mixed per model/version).

---

## 2. Audit findings (14 sessions, 4 projects, verified against raw transcripts)

Projects: famigo (3 sessions), formic-core (3), formicHMI (4 + spot-checks), reband (2),
agent-context-ide (2). Method: walk `--query` verdicts, verify every candidate finding by
grepping the raw jsonl for the actual assistant text and tool calls, report only with quoted
evidence from both sides.

Ground-truth sources for every finding in this section are the raw transcripts under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` for the encoded cwds
`-Users-jakuburban-Git-famigo`, `-Users-jakuburban-Git-formic-core`,
`-Users-jakuburban-Git-formic-formicHMI`, `-Users-jakuburban-reband` and
`-Users-jakuburban-Git-agent-context-ide`; the session-id prefixes are given per finding in
§7, so each one can be re-verified with `--query` plus a grep of the named jsonl.

### Error rates by status (sampled + verified)

| status | sampled | false/misleading | note |
|---|---|---|---|
| `used` (green) | ~18 | ~8 (**~45%**) | only clean slash-command triggers were reliable; in famigo 2/2 and formic-core 1/2 greens were false |
| `ignored` (red) | ~23 | ~16 (**~70%**) | least trustworthy status; formic-core 6/6 false, formicHMI 5/7 |
| `possibly-referenced` | ~57 | ~40% coincidental | honest reason text, misleading moment cards; ~15% were *under*-credits of demonstrable compliance |
| `dormant` / `unused` | ~27 | ~15% wrong | the honest-refusal side mostly works; misses are blocks whose compliance lives in tool calls / written content |

Distribution note: in every session the vast majority of blocks are `not-loaded` (correct,
delivery-based). The judged population per session is ~40–120 blocks.

### Measured after the work (Phase 14, re-measured in Phase 8 of the repair plan and again after the branch review)

The 8 anchor sessions were frozen (Phase 0), a ground truth was written per block from the
frozen transcripts before either report was read, and the same frozen inputs were re-baked at
the end. Full rows in [`snapshots/SCORECARD.md`](../snapshots/SCORECARD.md); the harness is
`snapshots/compare.py`.

The first version of this table was self-graded and an independent review round falsified it:
eight truth rows had been changed from `no-hard-verdict` to `used` *after* the after-run was
read, the corpus held zero `violated` truths and no session carried a compiled checks file, and
202 of the 226 "fixed" rows were skill blocks credited wholesale by one ruling. The numbers
below are the re-measurement, with the ground truth re-derived blind, the rulings written down
once in [`snapshots/expected/RULINGS.md`](../snapshots/expected/RULINGS.md), and the two halves
reported apart.

**Rule-document blocks - the half the judging mechanisms decide, one block at a time. This is
the number the reliability claim is about.**

| over 326 scored blocks | before | after |
|---|---|---|
| agrees with the ground truth | 250 (77%) | 273 (84%) |
| false green (`used` where nothing tied the block to the run) | 4 | **0** |
| false red (`ignored` with no citable violation) | 10 | **0** |
| under-credit (compliance the tool would not claim) | 50 | 53 |
| block never judged at all | 12 | **0** |

**Skill and command blocks - governed by the invoked-skill ruling (RULINGS.md 4), which
credits an invocation to the document's identity block alone, so every step is scored on
evidence of its own.**

| over 210 scored blocks | before | after |
|---|---|---|
| agrees with the ground truth | 68 | 126 |
| false green / false red | 0 / 0 | 1 / 0 |
| under-credit | 142 | 83 |
| block never judged at all | 0 | **0** |

The one false green is the formic-core `39b9e09e` `/grill-prd` Phase 1 block: the run read the
file it names inside the running command, but during Phase 0, and nothing structural tells one
section of a running document from another. It is named here rather than patched around.

Red-side coverage, stated because a false-red count of zero is otherwise unmeasurable: the
corpus carries **2 `violated` truths** (the famigo `5448a718` and `9dd3cc8a` commit-message
rules, cited at three and four `git commit` calls whose subjects run 73-83 characters against a
72-character limit, each with a paragraph body the same rule forbids) and **2 sessions carrying
a compiled checks file** (`snapshots/checks/famigo/*/…/CLAUDE.md.checks.json`, reviewed and
committed). Both `violated` rows are reached through that checks file, so their improvement
comes from a new judgement input as well as from the code, and the baseline could not have
reached them at all. Everything else in the two tables is the same frozen input judged by
different code.

**Regressed verdicts: 3.** One is the Phase 1 false green above. The other two are not
incidental: both are `~/.claude/CLAUDE.md` blocks in
the two formicHMI sessions whose skill really was invoked: the ctxlog hook's recorded size and
digest prove that file changed after it was loaded, so Phase 6 refuses to read any of its
wording as a rule and the block drops from `used` to `unused`. That is the cost of judging the
delivered text rather than the file on disk today, paid where it is visible.
`snapshots/compare.py` exits non-zero on them, as it should.

Three caveats on the numbers.

- The truth classes are deliberately coarse - `used` / `violated` / `no-hard-verdict` /
  `undecidable` - because `dormant` versus `unused` is not a reliability claim while a green
  over an untied rule is.
- 26 rows are excluded as `undecidable`, 14 of them because Phase 6 re-parsed one formic-core
  `AGENTS.md` from its delivered text, which has one section fewer than the frozen disk copy
  and therefore renumbers every block id after it. Those rows name sections of a document the
  session was never given.
- Every row not derived blind says so in its own line, under a `blind:` field the scorer
  refuses to let a `revised:` note omit. In this pass 27 rows carry `blind: no`: the 14
  renumbered ids above, the 12 rows added for the same sections under the ids the delivered
  text produces, and one more - the famigo `figma-design-system` redirect stub, moved *to*
  `used` against the reading that would have flattered the scorecard, because the review's
  finding was that the descriptive-block ruling had been applied only where the tool went
  green. The other 54 rows that moved in this pass were derived blind. The scorecard now
  prints the running total itself: 84 credited rows rest on a `blind: no` revision. Three
  further rows (`/grill-prd` Phases 1 and 2, `/implement-plan-workflow` Steps) were
  re-derived blind after the branch review, because their notes still said "only evidence was
  the invocation" while the tool had moved on to citing reads and a written template: two came
  back `used`, Phase 1 stayed `no-hard-verdict`.
- Two sessions (famigo `5448a718`, `9dd3cc8a`) had their compiled checks file frozen in after
  the baseline was baked; the scorecard names them and tags every moved row there.

### Failure mechanisms, ranked by damage (consistent across all four audits)

**F-PATHTABLE - the path-table predicate is wrong in both directions.**
- False green: `used` with zero gh commands because the account name `bionanek-x` from the
  table row substring-matched inside `git log --author="bionanek-x"` (formicHMI standup
  session). Also matched `grep ... CLAUDE.md` lines that merely contained the repo name.
- False red: sessions that ran the prescribed `gh auth switch -u bionanek-x` verbatim (one ran
  it 13 times) still scored `ignored`. The rule says "switch **if needed**"; the predicate
  demands the literal switch string before any gh command and cannot represent "status
  checked, account already correct" - so it cites the rule-mandated `gh auth status` as the
  violation.
- Applicability is keyed on cwd alone, so turns with zero gh activity score `ignored` instead
  of `dormant` ("No gh command this session, so no switch needed" - printed by its own moment
  while the status is red).
- In formic repos the row token "formic" substring-matches the cwd inside essentially every
  bash command, flooding moments with fake "[yes] Bash ran `formic`" cards (mkdir, sleep,
  wc - anything).

**F-COMBINE - `combine_verdicts` + independently regenerated session reason.**
One mis-scored turn paints a session red over a dozen provably compliant turns (ignored beats
used), and because the session-scope reason/moments are recomputed independently, one record
can describe three realities at once: status `ignored`, reason "applied **and were
satisfied**", moments `[yes]`. Observed in every multi-turn session inspected. Also the
inverse: `dormant` status above a possibly-referenced-style reason.

**F-TRIGGER - prefix bug, the largest source of false greens.**
`/implement-plan` fires on `/implement-plan-workflow` in **every project audited** (hyphen
defeats the boundary; the predicate lambda is bare substring while `_is_triggered` is
bounded). Verdict and its own moment card contradict each other on screen ("used" above
"[no] not invoked this run"). It also inverts credit: the actually-invoked sibling skill
(no `Trigger:` line in its SKILL.md → no strong predicate) scores `possibly-referenced` while
the non-invoked pointer scores `used`.

**F-EOM - end-of-message heuristic red-flags real compliance.**
- `has_tech` scans the whole final message: a textbook 3-sentence compliant summary failed
  because `setup_local_db.sh` appeared five paragraphs earlier; another failed on "CLAUDE.md"
  in a task that was *about* editing CLAUDE.md. Red in 4/4 formicHMI implementation sessions -
  a heuristic essentially no real summary passes.
- Applicability = `bool(t["edits"])`: doc-only Writes (plan markdown) count as "implementing a
  code change"; meanwhile **bash-heredoc edits are invisible** - a session that shipped a
  3-commit feature via `cat > file <<EOF` scored the rule `dormant` ("no code changed").
- Interactive turns that legitimately end with a question to the user score as violations.

**F-CMDMENTION - command-mention harvesting explodes on dense docs.**
One Architecture block in this repo derived **50 "command" predicates** - function names
(`agent_runs`, `load_transcript`), statuses (`ignored`, `unused`), payload keys (`id`, `data`,
`type`), plain English (`in`, `for`, `open`, `main`). The famigo Quality Gate block matched on
`at`, `from`, `runs`, `skips` (producing "[yes] Bash ran `from`" moments pointing at a python
heredoc) while never extracting its real command - `yarn type-check` is multi-token and
fenced, so 21 actual compliance runs stayed invisible. Fence languages (`bash`) and shell
builtins (`echo`, `printf`) from a rule's own example snippets guarantee blocks like "Copy to
clipboard" are `possibly-referenced` in virtually every session forever (no clipboard action
ever occurred; `echo` was a shell separator).

**F-BLINDSPOT - demonstrable compliance invisible, and actively denied.**
The most trust-damaging class. Rules the agent visibly followed scored `unused` /
`possibly-referenced` with reason text that *denies* compliance ("Common words match by
coincidence, so this is a hint, not compliance"):
- Error/Decision Memory: agent ran `tail -20 $M/ERRORS.md` at session start and appended
  entries in the rule's exact `**Decided:** / **Why:**` template to the exact files the rule
  names - invisible, because nothing joins tool-call file paths to paths a rule names.
- `/prd-to-plan` template blocks reproduced verbatim in a Written plan file - invisible,
  because the fallback searches only `all_assistant_text`, never Write/Edit content.
- A fully executed skill (`/create-pr`: gh auth status → learn convention → push → PR → watch
  checks, golden rules followed) scored `unused` - the Skill tool call feeds *loading* but
  never the *verdict*.
- An AGENTS.md "Commands" block whose every command (`just palletizer-hmi-lint`, `yarn test`)
  ran repeatedly, with the agent's reasoning mirroring the block's ":8088 already running"
  caveat, scored `dormant`.

**F-MOMENTS - causal narrative from coincidence.**
For weak/keyword verdicts the "How the agent ended up here" cards label unrelated reasoning
"(topical)": Figma design-system blocks citing rate-limiting review text (overlap: the word
"design"); a tech-stack table citing an Effect-vs-react-query discussion (overlap: "React",
"Native", "TypeScript" - table headers and stack names); Decision Memory citing YIN
pitch-detection math. The card's framing (TRIGGER→INTENT→ACTION) is a causal claim the
evidence cannot support.

**F-MISC (all verified):**
- CLAUDE.md *documentation examples* ("Trigger: /foo", "types `/x`") in this repo's own
  Architecture section become live predicates with nonsense "[no] /foo not invoked" moments.
- Invoked listing-only skills (`/grill-prd`, `/prd-to-plan` in reband - no SKILL.md on disk)
  render `not-loaded` despite driving ~15 turns.
- Block ids beginning with `-` cannot be passed to `--query` (argparse consumes them; `--`
  does not help).
- Session-scope reason can cite weak evidence ("`plan` in bash" - a filename inside an `mv`)
  under a green `used` status.

---

## 3. Research findings

Three independent tracks converge on one architecture: **interpret each rule once with a
model, compile it into typed atomic checks, execute those deterministically against
behaviour (the tool log), refuse honestly everywhere else.**

### 3.1 Instruction-following / compliance literature

- **The refusal design is validated.** Hard code-checkable constraints are ~22% of real
  instructions ([VerIF/VerInstruct](https://arxiv.org/html/2506.09942)); across 50 real
  agentic systems: formatting 38.5%, semantic 46.5%, tool 15%
  ([AgentIF](https://arxiv.org/abs/2505.16944), [taxonomy detail](https://www.themoonlight.io/en/review/agentif-benchmarking-instruction-following-of-large-language-models-in-agentic-scenarios)).
  Our observed 69% `not_checkable` from translate-rules.md matches the literature - it is the
  honest number.
- **Decompose blocks into atoms; report "k of n".** Decomposed binary criteria nearly double
  judge reliability vs holistic verdicts
  ([InFoBench/DRFR](https://arxiv.org/html/2401.03601v1): Fleiss' κ 0.532 vs 0.284;
  [CheckEval](https://arxiv.org/abs/2403.18771): +0.45 agreement, lower variance).
  Structurally kills fake narratives - a story built from named atoms cannot be coincidental
  the way a 2-of-8 word match is.
- **Judge behaviour, not prose.**
  [The Compliance Gap / BS-Bench](https://arxiv.org/pdf/2605.01771): agents verbally agree to
  process rules 10/10 times and bypass them 10/10 times; 0% default process compliance across
  six models; the gap is provably undetectable from text (their Theorem 2). CoT/self-report is
  unfaithful ([Turpin et al.](https://arxiv.org/abs/2305.04388);
  [Anthropic faithfulness work](https://www.anthropic.com/research/reasoning-models-dont-say-think):
  <20% verbalization of actually-used hints;
  [Measuring faithfulness in CoT](https://www.anthropic.com/research/measuring-faithfulness-in-chain-of-thought-reasoning)).
- **Conditional rules need two-stage verdicts** (antecedent fired? consequent satisfied? -
  reported separately). >30% of real conditional failures are wrong condition-checking
  ([AgentIF](https://arxiv.org/abs/2505.16944)); composition vocabulary
  (And / Chain / Selection) from [ComplexBench](https://arxiv.org/abs/2407.03978). This is
  exactly the gh-account fix.
- **Vocabulary source:** [IFEval](https://arxiv.org/abs/2311.07911)'s 25 verifiable types
  ([registry](https://raw.githubusercontent.com/google-research/google-research/master/instruction_following_eval/instructions_registry.py))
  / [IFBench](https://arxiv.org/html/2507.02833v1)'s 58 constraints in 7 categories (count,
  format, ratio, sentence, words, custom, copy);
  [RuLES](https://arxiv.org/html/2311.04235v2)' safety (must-not, string/regex) vs liveness
  (must) framing; [OpenAI Graders](https://developers.openai.com/api/docs/guides/graders)
  (`string_check`, `text_similarity`, `python`, `multigrader`) and
  [Guardrails AI's ~65-validator hub](https://guardrailsai.com/hub) as naming references;
  rail placement (input/dialog/execution/output) from
  [NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/about-nemo-guardrails-library/overview);
  NL-rule + AST-prefilter pattern from [GPTLint](https://github.com/gptlint/gptlint) and
  [MetaLint](https://arxiv.org/html/2507.11687v1). Multi-metric verdict split
  (satisfaction / instruction / session-stability) from
  [SysBench](https://arxiv.org/pdf/2408.10943); adherence decay with guardrail count from
  [RealGuardrails](https://arxiv.org/pdf/2502.12197).
- **Claude-Code-specific null result:** a 1,650-session study
  ([Instruction Adherence in Coding Agent Configuration Files](https://arxiv.org/abs/2605.10039))
  found NO effect of CLAUDE.md file size, instruction position, or cross-file contradictions
  on compliance after correction; the only robust effect is ~5.6% lower compliance odds per
  additional generated function within a session (per-turn drift - our per-turn scoping is the
  right substrate to surface it). This contradicts
  [lost-in-the-middle](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00638/119630/Lost-in-the-Middle-How-Language-Models-Use-Long)
  folklore; trust the domain-matched study, and do not build verdict logic on "the rule was
  buried" heuristics.
- **Anti-recommendations:** lexical overlap is never evidence of use at any threshold
  (no benchmark in the landscape uses it as a compliance signal; n-gram metrics correlate
  worst with human judgement -
  [BLEU/ROUGE limits](https://www.adaline.ai/blog/understanding-bleu-rouge-and-modern-nlp-metrics));
  embeddings measure "similar to the rule text", not "complied" (and break stdlib-only -
  [BERTScore limits](https://futureagi.com/blog/what-is-bleu-rouge-bertscore-2026/),
  [analysis](https://galileo.ai/blog/bert-score-explained-guide)); don't parse "never X" out
  of prose mechanically (RuLES hand-authors every prohibition; keep the fallback
  low-confidence, non-reddening); the authoring LLM must emit checks with self-tests, never
  scalar judgements (judge bias: [Judging the Judges](https://arxiv.org/abs/2406.07791),
  [reliability without validity](https://arxiv.org/pdf/2606.19544),
  [self-preference](https://arxiv.org/pdf/2506.02592));
  [IFDecorator](https://arxiv.org/pdf/2508.04632)-style "trip wires" (deliberately-failing
  trap cases in the checks file) catch a generator gaming its own self-tests. The
  compile-then-run split itself is independently arrived at by
  [Constitutional Classifiers](https://arxiv.org/pdf/2501.18837),
  [VerIF](https://arxiv.org/html/2506.09942) and [ARES](https://arxiv.org/abs/2311.09476).

### 3.2 Lexical matching under stdlib constraints

The keyword mechanism is not fixable by threshold tuning - the **vocabulary** must change.

- **Three background distributions**, all computable offline: D1 block-collection IDF (all
  blocks of all loaded context files across all baked sessions; use Lucene's non-negative
  `log(1 + (N-df+0.5)/(df+0.5))` form - textbook RSJ IDF goes negative at df>50%:
  [Lucene BM25Similarity](https://lucene.apache.org/core/7_0_1/core/org/apache/lucene/search/similarities/BM25Similarity.html),
  [Robertson 2004 on IDF](https://www.emerald.com/insight/content/doi/10.1108/00220410410560582/full/html));
  D2 general English (bake a Zipf-scale frequency list - [rspeer/wordfreq](https://github.com/rspeer/wordfreq)
  data, [plain-JSON export](https://github.com/aparrish/wordfreq-en-25000); drop zipf≥5 terms,
  ramp 3.0–5.0); D3 **project background from the transcript itself** - fraction of the
  session's assistant segments containing the term; ≥0.35 → weight 0. D3 alone kills
  "React"/"Framework"/"TypeScript" in a React repo, i.e. most observed false positives.
  Corpus-linguistics support for domain-matched reference corpora:
  [LADAL keyness](https://ladal.edu.au/tutorials/keywords/keywords.html),
  [Choosing a Reference Corpus](http://isli.khu.ac.kr/journal/content/data/28_1/13.pdf);
  the mechanical equivalent is [passim](https://github.com/dasmiq/passim)'s `--maxDF` ceiling.
- **`K(block)`** = top ~12 terms by combined weight (plus bigram/trigram pseudo-terms - a
  rule's identity usually lives in a phrase). **If |K| < 3 the block is
  `not-lexically-scorable`** - the correct verdict for tables and boilerplate; never score
  with whatever generic tokens survive.
- **Scoring:** BM25 with block-as-query, assistant turn text as document; k1=0.9 (short
  passages), b=0.75 (highly variable turn lengths) - parameter guidance:
  [Practical BM25 pt 3](https://www.elastic.co/blog/practical-bm25-part-3-considerations-for-picking-b-and-k1-in-elasticsearch);
  saturation semantics: [Robertson & Zaragoza, BM25 and Beyond](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf).
  Normalise to a coverage figure. Query text = assistant text and thinking segments ONLY -
  exclude tool inputs, tool results, fenced code, and spans copied from Read files (a read
  file's content in the query makes every block of that file self-match: the most likely new
  false-positive source).
- **Significance gate:** Dunning G² log-likelihood per term (2×2 vs the rest of the session's
  assistant text) - [Dunning 1993](https://www.microsoft.com/en-us/research/wp-content/uploads/2004/07/rare-events-final-rev.pdf);
  critical values 3.84/6.63/10.83/15.13 and effect-size bands from the
  [UCREL log-likelihood wizard](https://ucrel.lancs.ac.uk/llwizard.html); require observed
  count ≥2 per term; use the 15.13 bar per term given multiple testing. Block-level "topical"
  requires ≥2 distinct K-terms each clearing G²≥6.63 AND BM25 coverage ≥0.25 AND ≥1 term with
  zipf<4.
- **Quote detector** (the only lexical path near "strong"): 5-word shingle containment
  (containment, not Jaccard - length-asymmetric:
  [Broder, near-duplicate documents](https://cs.brown.edu/courses/cs253/papers/nearduplicate.pdf))
  ≥0.15 with ≥3 matched shingles each containing a distinctive term → `paraphrased`;
  `difflib.SequenceMatcher(autojunk=False)` longest common run ≥8 tokens or ≥50 chars
  containing ≥1 distinctive term → `quoted`. autojunk=False is mandatory (default discards
  frequent function words: [difflib docs](https://docs.python.org/3/library/difflib.html)).
  Threshold anchors: [passim](https://github.com/dasmiq/passim) defaults (25-char n-grams,
  ≥5 matches, ≥50 chars aligned), [PAN plagiarism n-grams](https://ceur-ws.org/Vol-1179/CLEF2013wn-PAN-ShresthaEt2013.pdf);
  the substring+shingle dual signal is standard in
  [text-reuse detection](https://aclanthology.org/C12-1011.pdf).
- **Rename labels to name the evidence, never the mechanism:** `echoed`, `topical-overlap`,
  `no-lexical-trace`, `not-lexically-scorable`. Lexical evidence can never establish
  causality, only co-occurrence; absence of overlap is not evidence of non-use (silent
  behavioural compliance leaves no lexical trace - vocabulary mismatch hits short texts
  hardest: [Sease](https://sease.io/2022/01/tackling-vocabulary-mismatch-with-document-expansion.html),
  [Kenter & de Rijke](https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/kenter-short-2015.pdf));
  even a verbatim quote is self-report ([Turpin et al.](https://arxiv.org/abs/2305.04388)).
- **Calibration:** hand-label 200–300 (block, turn) pairs (`quoted` / `topically-drawn-on` /
  `coincidental` / `undecidable`), sweep, pick a precision-first operating point (≥0.90
  precision, recall falls where it does -
  [precision-recall operating points](https://scikit-learn.org/stable/auto_examples/model_selection/plot_precision_recall.html)),
  commit the labelled set as a regression fixture, and add a **shuffled-pair test**: score
  every block against turns from an unrelated session; anything above threshold there is a
  generic block. No published precision figure exists for this exact task; well-built lexical
  retrieval is a strong zero-shot baseline but has a real ceiling
  ([BEIR](https://arxiv.org/abs/2104.08663)).

**Frozen operating point (measured, Phase 13).** The calibration above was run.
The set is [`tests/fixtures/lexical_pairs.json`](../tests/fixtures/lexical_pairs.json)
- 250 (block, session) pairs: 22 read out of the frozen §7 transcripts by hand
(including every pair the tier calls positive, so precision is measured rather
than sampled), 150 shuffled cross-project pairs and 46 uninvoked-skill pairs
that are `coincidental` by construction, and 32 self-contained synthetic pairs
that double as the contribution format.
[`tests/lexical_fixture.py`](../tests/lexical_fixture.py) is the scorer and
documents the labelling procedure;
[`tests/test_calibration.py`](../tests/test_calibration.py) gates on it.

The sweep, over the whole set (precision / recall / tp / fp):

| coverage floor | run chars | G² bar | precision | recall | tp | fp |
|---|---|---|---|---|---|---|
| 0.25 | 40 | 6.63 | 0.900 | 0.500 | 9 | 1 |
| 0.25 | 40 | 15.13 | 1.000 | 0.444 | 8 | 0 |
| 0.25 | 50 | 6.63 | 0.889 | 0.444 | 8 | 1 |
| **0.30** | **40** | **6.63** | **1.000** | **0.500** | **9** | **0** |
| 0.30 | 40 | 15.13 | 1.000 | 0.444 | 8 | 0 |
| 0.30 | 50 | 6.63 | 1.000 | 0.444 | 8 | 0 |
| 0.35 | 40 | 6.63 | 1.000 | 0.444 | 8 | 0 |
| 0.35 | 50 | 15.13 | 1.000 | 0.389 | 7 | 0 |

**coverage floor 0.30, run 8 tokens AND 40 chars, G² 6.63** is the only point
that reaches precision 1.0 without giving up a further true positive, so that
is the frozen point. Two notes on how it differs from the recommendation above:

- The two run-length bars are an **AND**, not the "≥8 tokens or ≥50 chars" of
  the anchors. Taken as alternatives, an eight-token run of seven function
  words and one content word qualifies, and the set contains that pair twice:
  "do you have a figma design for this" sits in two of one user's command
  files, one invoked and one not, so the same 35-character run was the evidence
  for a true positive and a false one at once. No threshold separates twins -
  precision-first means losing both. Before this change precision on the set
  was 0.833.
- The per-term G² bar stays at **6.63**, not the 15.13 suggested for multiple
  testing: at 15.13 the famigo `9dd3cc8a` backend-Database anchor loses one of
  its two significant terms and the pair goes from a true positive to a miss,
  with no false positive removed in exchange. The bar is worth revisiting when
  the set has more than nine positives behind it.

Recall at the frozen point is 0.500, and the misses are in the fixture with a
note each. Five of them are the §7 F-BLINDSPOT and F-CMDMENTION anchors, where
the compliance happened entirely in file writes and verbatim command runs and
left no trace in the prose at all - exactly the shape of miss the structural
predicates rather than the vocabulary exist to catch. The remaining shuffled
and uninvoked-skill halves produce zero positives, which is §3.2's
shuffled-pair check passing over 196 pairs.
- Anti: RAKE (no corpus contrast; [Rose et al. 2010](https://www.researchgate.net/publication/227988510_Automatic_Keyword_Extraction_from_Individual_Documents),
  beaten by [YAKE](https://www.sciencedirect.com/science/article/abs/pii/S0020025519308588)
  on all evaluated datasets), TextRank (blocks too small for the graph;
  [Mihalcea & Tarau 2004](https://www.researchgate.net/publication/200042361_TextRank_Bringing_Order_into_Text)),
  χ² (unreliable at expected<5 - [Dunning 1993](https://www.microsoft.com/en-us/research/wp-content/uploads/2004/07/rare-events-final-rev.pdf)),
  Jaccard (length asymmetry - [Broder](https://cs.brown.edu/courses/cs253/papers/nearduplicate.pdf)),
  hypergeometric p-values taken literally (independence violated -
  [overlap-significance discussion](https://www.gungorbudak.com/blog/2016/05/25/computing-significance-of-overlap/)),
  tuning k1/b before fixing vocabulary
  ([Practical BM25 pt 3](https://www.elastic.co/blog/practical-bm25-part-3-considerations-for-picking-b-and-k1-in-elasticsearch)),
  embeddings ([BEIR](https://arxiv.org/abs/2104.08663): dense models can underperform BM25
  out of domain).

### 3.3 Agent-trace attribution and Claude Code signals

- **No observability platform does per-prompt-section attribution** - all stop at "which
  prompt version ran": [LangSmith trajectory evals](https://docs.langchain.com/langsmith/trajectory-evals)
  / [agentevals](https://github.com/langchain-ai/agentevals),
  [Langfuse prompt-trace linking](https://langfuse.com/docs/prompt-management/features/link-to-traces),
  [Arize/OpenInference conventions](https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md),
  [W&B Weave](https://wandb.ai/site/weave/),
  [Braintrust online scoring](https://www.braintrust.dev/foundations/online-scoring),
  [OTel GenAI semconv](https://opentelemetry.io/blog/2026/genai-observability/)
  (`gen_ai.system_instructions` is one opaque blob). The real prior art is temporal-logic
  trace verification: [AgentLTL](https://arxiv.org/html/2607.02599) - FO-LTL constraints over
  typed tool signatures, six layers (branching, literal args, global ordering, pairwise
  ordering, call counts, exact args), deterministic and judge-free from recorded traces;
  **ordering constraints concentrate ~73% of real failures**. Plus process mining /
  conformance checking ([Agent Mentor](https://arxiv.org/pdf/2604.10513),
  [workflow fidelity](https://arxiv.org/pdf/2605.06457)); read-then-edit as a behavioural
  fingerprint: [cross-framework SWE-agent analysis](https://arxiv.org/pdf/2605.18332);
  governing principle ("process-level accountability without model internals"):
  [provenance survey](https://arxiv.org/html/2606.04990v1).
- **Transcript-native signals, Tier A (ground truth):** the `InstructionsLoaded` hook - fires
  per CLAUDE.md / rules file load with `file_path`, `load_reason`
  (session_start / nested_traversal / path_glob_match / include / compact), and **full
  `content` as loaded** ([hooks reference](https://code.claude.com/docs/en/hooks)). Fixes a
  live correctness bug: we score against the file on disk at analysis time, but mid-session
  edits never apply to the model ([memory docs](https://code.claude.com/docs/en/memory);
  path rules load on read, not write:
  [issue #23478](https://github.com/anthropics/claude-code/issues/23478)). Also `prompt_id`
  (authoritative turn segmentation - can replace `_real_user_prompt_text` edge cases),
  `tool_use_id`, `agent_id` + `SubagentStart/Stop` (replaces task-notification regex parsing),
  `tool_decision.source` (separates "agent complied" from "permission layer blocked the
  alternative"), `UserPromptExpansion` (authoritative slash-command trigger) - all documented
  in [hooks](https://code.claude.com/docs/en/hooks) and
  [monitoring usage](https://code.claude.com/docs/en/monitoring-usage). Natural extension of
  the existing ctxlog hook.
- **Cache accounting is prefix-stability evidence, not residency evidence** - "there is no
  per-file or per-segment caching"
  ([prompt caching docs](https://code.claude.com/docs/en/prompt-caching)); keep the
  largest-remainder split but label it allocation. Newly bakeable:
  `ephemeral_1h/5m_input_tokens` split; typed cache-break reasons (model switch, effort
  change, tool-set change, compaction, CLI upgrade - same doc).
- **Thinking text:** officially encrypted (empty `thinking` + signature:
  [issue #31143](https://github.com/anthropics/claude-code/issues/31143),
  [thinking encryption](https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-thinking-encryption.html)),
  but empirically mixed - 43/82 blocks readable in a recent famigo transcript (verified in
  this analysis, session `4ef9a6f4` under `-Users-jakuburban-Git-famigo`). Treat as optional
  weak corroboration when present, never an evidence tier (faithfulness <20%:
  [Anthropic](https://www.anthropic.com/research/reasoning-models-dont-say-think)); INTENT
  moment slots should be filled by structural antecedents (the load event, the expansion that
  fired, the read that triggered a path rule) instead.
- **Honest epistemic ceiling:** causal attribution needs ablations + logprobs
  ([ContextCite](https://arxiv.org/abs/2409.00729): 32–256 masked re-runs with logprob
  readout) - impossible offline. Attention is unavailable in logs AND unreliable
  ([Jain & Wallace, Attention is not Explanation](https://aclanthology.org/N19-1357/)).
  The defensible verdict ladder: **delivered → applicable → conformant / violated /
  not-exercised**, plus co-occurrence labels for everything weaker. "Used" is a causal word
  on a correlational measurement; a "How the agent ended up here" card is a causal claim -
  suppress or reframe it wherever the only evidence is lexical.

---

## 4. Open-source generalization (must-have, not polish)

The current strong predicates are reverse-engineered from **one user's** CLAUDE.md and do not
transfer:
- `path-table` matches the literal header "Project path contains"; `end-of-message` matches
  one rule's phrasing and encodes one user's summary style; the well-known-command list
  (`pbcopy`, `printf`, `echo`) exists because of one clipboard rule; `SUMMARY_KEYWORDS`,
  `NON_CMDS`, `classify_block` cues and the keyword tokenizer are English-only (CJK doesn't
  even tokenize).

Consequences for the plan:
1. **Retire the bespoke predicates, don't patch them.** Fold path-table and end-of-message
   into the compiled-checks vocabulary (a conditional check + a response-shape check) so each
   user's authoring run generates them from their own rules. Hardcode only harness-defined
   signals, identical for every user: slash-command triggers, Skill/Agent tool calls,
   tool-log ordering, file-path joins.
2. **The authoring step becomes the onboarding step** - a first-class guided flow (run
   `/compile-rules`-style command → review generated `<doc>.checks.json` → commit), not a
   README footnote. For an unknown user's rules it is the only mechanism that scales.
   User-facing shape: (a) tool works out of the box but says "not mechanically checkable"
   for most rules; (b) one Claude session compiles their rules into checks + not_checkable
   entries with reasons; (c) user reviews/edits the JSON like config; (d) analysis is then
   deterministic, offline, cited; stale checks are skipped when rule text changes.
3. **Language-neutral core:** derive stopwords/background frequencies from the user's own
   corpus (their blocks + transcripts); the English wordlist is an optional enhancement;
   rule-cue detection moves to authoring time (the model reads any language).
4. **Calibration set must be multi-user:** seed from these audited sessions (30+ verified
   wrong verdicts are ready-made labels), structure for community-contributed sanitized
   pairs, track precision per rule category, keep all label tooling local-only (the
   no-network guarantee is the tool's strongest property).
5. **Degrade, never worsen:** any optional signal (ctxlog, InstructionsLoaded, readable
   thinking) that is absent must degrade to "signal unavailable", never to a worse verdict.

---

## 5. Recommended plan (tiers by cost) - SUPERSEDED by §10

> This section predates the external-spec comparison (§8) and the LLM-at-audit / ast-grep
> decisions (§9). §10 is the current consolidated plan; this section is kept because its
> tier framing (cost ordering) and item details are referenced from §10.

**Tier 0 - universal bug fixes (days):**
- Trigger predicate: use `_is_triggered` (right-bounded) in the predicate lambdas.
- `combine_verdicts`: regenerate session reason from the combined status; stop letting one
  myopic red turn outrank verified compliance (or recompute at session scope).
- Command-mention: kill fence languages, English words, ≤3-char tokens; extract fenced
  multi-token commands.
- Stop parsing documentation examples into predicates (this repo's own Architecture block).
- CLI: accept block ids starting with `-` (argparse fix); listing-only invoked skills should
  not render `not-loaded`.

**Tier 1 - new evidence sources (biggest precision per effort):**
- Feed the verdict layer: Skill tool invocations, Write/Edit content, writes-to-rule-named-
  files (path join, both sides resolved like `_resolve_key`), bash-heredoc edits, readable
  thinking (weak corroboration, labelled).
- Add tool-log check kinds to `rule_checks.VOCABULARY` + translate-rules.md:
  `tool_required`, `tool_forbidden`, `tool_precedes`, `tool_never_without_prior`,
  `tool_arg_matches`, `writes_to_path`, call counts. Two-stage conditional reporting
  (antecedent / consequent). Pair findings with permission-decision source when available.

**Tier 2 - rebuild the weak tier + taxonomy:**
- Contrastive keyword weighting (D1×D2×D3), G² gate, BM25 coverage, quote detector;
  `not-lexically-scorable` for |K|<3.
- Rename: `possibly-referenced` → evidence-named labels (`echoed` / `topical-overlap` /
  `no-lexical-trace`); suppress or reframe the moments card wherever evidence is lexical-only.
- Retire bespoke predicates into compiled checks (see §4.1); atom decomposition ("k of n")
  in the authoring prompt; `InstructionsLoaded` hook next to ctxlog.

**Cross-cutting:** the calibration harness (hand-labelled pairs committed as a regression
fixture + shuffled-session coincidence test) before any threshold is chosen.

---

## 6. Example: onboarding output for a user's rules

User's CLAUDE.md:

```markdown
## Copy to clipboard
When copying text to the clipboard, always pipe through `printf` - never `echo`.

## Styling
Use React Native `StyleSheet.create()` - no styled-components.

## Quality gate
Run `yarn type-check` and `yarn lint` before committing.

## How to talk to me
Be direct and casual, zero fluff. Answer first.
```

Generated `CLAUDE.md.checks.json` (today's format; `tool_precedes` would strengthen the
third check once Tier 1 lands):

```json
{
  "source": "CLAUDE.md",
  "checks": [
    {
      "id": "clipboard-no-echo",
      "rule_ref": "Copy to clipboard",
      "rule_text": "always pipe through `printf` - never `echo`",
      "domain": "shell",
      "kind": "forbidden_command",
      "pattern": "\\becho\\b[^|]*\\|\\s*(pbcopy|xclip|xsel)",
      "confidence": "high",
      "message": "echo piped to clipboard - the rule requires printf.",
      "self_test": {
        "should_match": ["echo \"$msg\" | pbcopy"],
        "should_not_match": ["printf '%s' \"$msg\" | pbcopy", "echo done"]
      }
    },
    {
      "id": "no-styled-components",
      "rule_ref": "Styling",
      "rule_text": "no styled-components",
      "domain": "source",
      "kind": "forbidden_pattern",
      "pattern": "from ['\"]styled-components",
      "applies_to": ["**/*.tsx", "**/*.ts"],
      "confidence": "high",
      "message": "styled-components import - the rule mandates StyleSheet.create().",
      "self_test": {
        "should_match": ["import styled from 'styled-components'"],
        "should_not_match": ["const s = StyleSheet.create({})"]
      }
    },
    {
      "id": "typecheck-before-commit",
      "rule_ref": "Quality gate",
      "rule_text": "Run `yarn type-check` and `yarn lint` before committing.",
      "domain": "shell",
      "kind": "required_command",
      "trigger_pattern": "\\bgit commit\\b",
      "pattern": "yarn (type-check|lint)",
      "confidence": "medium",
      "message": "A commit ran without a preceding type-check/lint in this session.",
      "self_test": {
        "should_match": ["git commit -m 'fix'"],
        "should_not_match": ["git status"]
      }
    }
  ],
  "not_checkable": [
    {
      "rule_ref": "How to talk to me",
      "rule_text": "Be direct and casual, zero fluff. Answer first.",
      "why": "Tone and structure preferences require semantic judgment; no mechanical pattern can verify 'zero fluff'."
    }
  ]
}
```

---

## 7. Seed data for the calibration fixture

The audits produced 30+ fully verified wrong verdicts with session id, block id, given status,
category (A false-green / B coincidental-amber / C misleading moments / D false-red /
E invisible compliance / F extraction miss), and quoted transcript evidence. Representative
anchors (session-id prefix / block id / status → truth):

- famigo `9dd3cc8a` / `...claude-md-11-implement-plan` / used → `/implement-plan-workflow`
  was invoked, not `/implement-plan` (F-TRIGGER). Same in `0cfa1aa9`, formic-core `39b9e09e`
  turn-29, reband `113a0d2c` turn-14, agent-context-ide `9584a785` turn-5.
- formicHMI `8fd8526c` / `...claude-md-3-github-account-per-project` / used → zero gh
  commands; matched `git log --author="bionanek-x"` (F-PATHTABLE green).
- formicHMI `12f48cdb` / same block / ignored → `gh auth switch -u bionanek-x` ran 13×
  (F-PATHTABLE red + F-COMBINE). Also formic-core `4ebe50c0` (switch ran verbatim, turn 0
  `used`, session `ignored`), agent-context-ide `d5c3cc1a` (switch ran verbatim, `ignored`),
  reband `113a0d2c` + formic-core `39b9e09e`/`1b395e0b` (status-checked, already correct,
  `ignored`).
- famigo `9dd3cc8a` / `...claude-md-8-end-of-implementation-summary` / ignored → compliant
  3-sentence summary; `.sh` filename five paragraphs earlier tripped `has_tech` (F-EOM).
  Also reband `22c58939`, formicHMI `8e62abcd`, formic-core `4ebe50c0` (doc-only Write).
- famigo `5448a718` / same block / dormant → 3-commit feature shipped via bash heredocs;
  edit detector saw nothing (F-EOM applicability).
- famigo `5448a718` / `...famigo-claude-md-4-quality-gate-mandatory` / possibly-referenced on
  `at`/`from`/`runs` → 21 real `yarn type-check && yarn lint && yarn test` runs invisible
  (F-CMDMENTION both directions).
- famigo `5448a718` / error-memory + decision-memory / possibly-referenced ("coincidence, not
  compliance") → agent appended rule-templated entries to the exact files the rules name
  (F-BLINDSPOT). Same: reband `22c58939` decision-memory.
- formic-core `39b9e09e` / prd-to-plan template blocks 2–5 / unused → template reproduced
  verbatim in a Written plan file (F-BLINDSPOT).
- formic-core `39b9e09e` / palletizer-hmi AGENTS.md "Commands" / dormant → every documented
  command ran; agent's reasoning mirrored the block's caveat (F-BLINDSPOT).
- formicHMI `8e62abcd` / create-pr SKILL blocks / unused → skill invoked via Skill tool and
  executed end-to-end; the tool's own moment says "[yes] Skill tool invoked /create-pr"
  (F-BLINDSPOT).
- reband `22c58939` / grill-prd + prd-to-plan / not-loaded → both invoked via
  `<command-name>` wrappers and drove ~15 turns; no SKILL.md on disk (F-MISC).
- famigo turn-0 / figma-workflow "Tech Stack" table / possibly-referenced 5/8 keywords →
  table headers + stack names vs an unrelated Effect-library discussion (the finding that
  started this analysis; `not-lexically-scorable` is the correct verdict).

Counter-anchors (verdicts that were RIGHT and must stay right): clean slash-trigger greens
(`/standup`, `/pr-comments`); plain `dormant`/`unused` on untriggered skills and header
blocks (10/10 correct in the reband/ACI sample); all delivery-based statuses (`not-loaded`,
`undelivered`).

---

## 8. Comparison with the external "CLAUDE.md Compliance Audit Tool" spec

An independently written spec (two-stage: LLM rule extraction into a frozen reviewed
`rules.yaml`, then per-session audit with deterministic checks + narrowly-scoped LLM calls)
was compared against this analysis. Verdict: **same core architecture** - it independently
arrives at compile-then-run, frozen reviewed artifacts, self-test fixtures, source-hash drift
guarding (our `rule_key`), a mandatory "not applicable" verdict (our `not-exercised`), and
the false-green fixture guard (our load-time self-test rerun). It validates the direction;
the two proposals answer different questions and each has pieces the other lacks.

### Adopted from the external spec

- **Three rule buckets A/B/C.** A = deterministic (no LLM). **B = hybrid - the big idea we
  were missing:** candidates extracted deterministically (every new comment, every catch
  block, every commit command), each judged by an LLM in isolation with minimal context.
  This recovers a large share of the ~69% we currently refuse, in the only LLM-judge mode
  the literature rates reliable (narrow scope, single question - consistent with
  InFoBench/CheckEval in §3.1). C = pure semantic judgment, least reliable, display-capped.
  Fixture-verification failures demote a rule A→C visibly, never silently.
- **Violations by omission require active candidate search.** "Always implement the catch
  body" leaves no trace if the agent wrote nothing; the checker must enumerate candidates
  itself and ask about each. Our current checks only scan what was written - the audits
  showed the mirror-image bug (compliance invisible because nothing enumerated evidence).
  The external spec calls this the most common source of false "all clear"; agreed.
- **Judge the final diff, not the transcript, for code rules.** Our `build_corpus` currently
  collects *all* written tool-call content, so abandoned attempts can produce violations.
  Scope: code rules → final diff; communication/process rules → transcript.
- **`examples_negative` as a mandatory rule-record field.** We have should_match /
  should_not_match for the *pattern*; the *rule meaning* also needs positive and negative
  examples (generated at extraction even when the source doc has none) - it is what
  constrains an over-eager bucket-B/C judge. Keep examples separate from the statement text.
- **Rule-record format upgrades:** `statement` phrased as a testable question,
  `scope: code | communication | process`, `evidence: diff | files | transcript`,
  explicit bucket field.
- **AST over regex** for source checks - structure kills the comment/string false-positive
  class that `strip_comments_and_strings` only approximates, and makes omission checks
  expressible ("empty catch body", "both calls in one component" via relational rules).

### Rejected or amended

- **Required LLM at audit time** conflicted with the original no-LLM constraint; resolved as
  a decision in §9 (opt-in tier, deterministic core stays the default).
- **ast-grep as a hard runtime dependency** - amended to a consented, pinned, optional
  enhancer (§9). Absent binary → affected rules report `not-checkable (ast-grep not
  installed)`, never a regex approximation pretending to be the same check.
- **Process rules routed to bucket C (transcript + LLM) - wrong.** Process rules ("lint
  before commit", "gh auth before gh") are the *most* deterministic class: tool-log ordering
  checks (§3.3, AgentLTL - where ~73% of real failures live), no judge needed. Our planned
  `tool_precedes` family beats bucket-C treatment of process rules.
- **No display discipline for bucket C.** The spec caps nothing; our evidence-tier rule must
  extend to judge output: a bucket-C verdict on "be direct, zero fluff" informs but can never
  solely turn a block red or green.

### What the spec does not cover (everything stays from our plan)

It answers only "was rule X violated?". No notion of: delivery (`undelivered`, truncated
reads, compaction eviction), token attribution/cost, duplicate detection, skills/subagents,
per-turn scoping, the wasted-context question, or honest-verdict display caps. It is a spec
for a better `rule_checks.py`, not for the whole tool.

---

## 9. Decisions: LLM at audit time, ast-grep

### 9.1 LLM at audit time - ACCEPTED, as an opt-in tier

Rationale: deterministic checks can decide ~20-30% of real rules (§3.1); if the primary goal
is "which rules were violated / used", an LLM tier is the only way to cover the majority of
rules at all. Constraints that make it safe:

- **Three-tier audit:** (1) deterministic - default, fully offline, unchanged trust contract;
  (2) bucket-B candidate-scoped judging - opt-in; (3) bucket-C semantic judging - opt-in,
  display-capped like today's weak tier.
- **One rule × one candidate × one call**, with the rule's positive/negative examples and
  minimal context. Never "here is the session and 20 rules".
- **Citation or downgrade:** every judge verdict must carry file/line/snippet evidence or it
  degrades to `unclear` - same rule the deterministic layer already enforces.
- **Reproducibility via caching:** every verdict keyed on
  `(rule_key, candidate content hash, model id)`, stored in a local cache file. Re-runs are
  deterministic (same inputs = same report) and mostly free; a re-audit after a small change
  pays only for new candidates.
- **Runs on the user's existing Claude Code auth** (subagent or headless session) - no new
  key or account. Opt-in flag documented as changing the privacy contract ("session content
  is sent to the model"); default mode stays fully offline. This remains the strongest trust
  property for the open-source release.
- **Wasted-context contribution (secondary goal):** the structural facts (delivery,
  residency, attribution, duplicates) stay Python-computed; the one genuine LLM addition is
  scoped, cacheable *relevance* judgments per loaded file ("does this file pertain to
  anything this session did?"), upgrading "wasted" from token accounting to meaning.

### 9.2 ast-grep - ACCEPTED, as a pinned optional enhancer

- **Value (real):** structural matching properly kills the comment/string false-positive
  class; omission and co-occurrence checks become expressible; LLM-authored patterns that
  look like code are easier to review than regex. Single static Rust binary, ~10MB, no
  runtime deps - the cheapest possible dependency.
- **Not a guarantee:** patterns are still LLM-authored, so the fixture gate stays mandatory;
  language coverage is per-tree-sitter-grammar (strong for TS/JS/Python/Go, absent for niche
  languages); semantic rules remain out of reach. It upgrades bucket A precision and moves
  some rules C→A; it does not change the epistemics.
- **Distribution: never silently install to the user's PATH** (supply-chain and consent
  problem for an open-source audit tool). Onboarding offers a **checksum-pinned download into
  the tool's own directory**, used from there. Absent → affected rules report
  `not-checkable (ast-grep not installed)`, never a degraded regex fallback.

---

## 10. Consolidated implementation plan (current)

Supersedes §5. Each phase ships value on its own.

**Phase 0 - fix the verdict bugs that poison trust today (no architecture change)**
1. Trigger predicate: use the bounded `_is_triggered` in the predicate lambdas
   (kills F-TRIGGER).
2. `combine_verdicts`: regenerate session reason from the combined status; an `ignored`
   turn must itself have been exercised to propagate (kills F-COMBINE).
3. End-of-message: `has_tech` scoped to the final paragraph; doc-only Writes are not code
   edits; bash-heredoc writes ARE edits; question-ending interactive turns → not applicable
   (kills F-EOM).
4. Command-mention: drop fence languages, English words, ≤3-char tokens; extract fenced
   multi-token commands; stop parsing documentation examples into predicates
   (kills F-CMDMENTION, F-MISC doc-examples).
5. Misc: `-`-prefixed block ids in `--query`; invoked listing-only skills must not render
   `not-loaded`; `dormant` status above possibly-referenced reason.
   Deliverable: the §7 false verdicts flip to correct - add them as regression tests first.

**Phase 1 - feed the verdict layer the evidence it already has**
6. Skill/Agent tool invocations feed block verdicts (not just file loading).
7. New structural signals: writes to a rule-named file path, Write/Edit content matching,
   verbatim command echo (kills F-BLINDSPOT).
8. Read thinking text when present; labelled weak corroboration only.
9. Suppress the "How the agent ended up here" narrative wherever the only evidence is
   lexical; replace with a plainly-labelled "topical overlap - no causal link" card
   (kills F-MOMENTS).

**Phase 2 - rebuild the rule pipeline (onboarding becomes the product)**
10. Tool-log check kinds in the vocabulary: `tool_precedes`, `tool_never_without_prior`,
    `tool_required`, `tool_forbidden`, `tool_arg_matches`, `writes_to_path`, call counts -
    deterministic, from the baked ordered tool calls.
11. Rule-record format per §8: statement-as-question, scope, evidence source, bucket A/B/C,
    `examples_positive`/`examples_negative`, fixtures, source hash.
12. translate-rules.md becomes a guided onboarding flow (`/compile-rules`): extract →
    classify → generate patterns + fixtures → verify (failures demote to C visibly) →
    human review → commit.
13. Retire bespoke prose-derived predicates (path-table, end-of-message, clipboard word
    list) - regenerated per user via onboarding; hardcode only harness-defined predicates
    (slash triggers, Skill/Agent calls, tool ordering).
14. Omission-candidate enumeration from the **final diff** for code rules; transcript only
    for communication/process rules.
15. ast-grep integration per §9.2.

**Phase 3 - LLM audit tier (opt-in), per §9.1**
16. Bucket-B runner (one rule × one candidate × one call, citation required).
17. Verdict cache keyed `(rule_key, candidate hash, model id)`.
18. Bucket-C runner, display-capped.
19. Runs over the user's Claude Code auth; offline default; documented privacy flag.
20. Wasted-context relevance judgments per loaded file, cached.

**Phase 4 - rebuild the lexical tier + rename the taxonomy (per §3.2)**
21. Contrastive keyword weighting (D1×D2×D3); `not-lexically-scorable` for |K|<3.
22. G² significance gate + BM25 coverage; strict quote detector (`autojunk=False`).
23. Statuses renamed to name evidence, not causation: `echoed` / `topical-overlap` /
    `no-lexical-trace` / `not-lexically-scorable` replacing `possibly-referenced`; keep
    delivered → applicable → conformant/violated/not-exercised for strong verdicts.
    Payload-additive per the compatibility invariant.

**Phase 5 - calibration + open-source hardening (per §4)** - LANDED
24. Labelled fixture set seeded from §7 + ~250 hand-labelled pairs; precision ≥0.90 gate on
    every matching change; shuffled-session coincidence test. **Landed**: 250 pairs,
    precision 1.0 at the frozen operating point recorded in §3.2 above; the shuffled and
    uninvoked-skill halves (196 pairs) produce zero positives.
25. Language-neutral core: stopwords/backgrounds from the user's own corpus. **Landed** in
    the Phase 12 tier (D1 and D3 are the user's own corpus, D2 is optional) and asserted
    with the English list absent in `tests/test_calibration.py`.
26. Degradation contract: every optional signal (ctxlog, InstructionsLoaded, thinking,
    ast-grep, LLM tier) degrades to "signal unavailable", never to a worse verdict;
    documented trust model (offline by default, what each opt-in changes). **Landed** as
    `tests/test_degradation.py` (a matrix over a registry of the five signals, so a sixth
    cannot ship without a row) and the README's trust-model section.

Dependencies: Phases 0-1 independent, start immediately; Phase 3 needs items 11-14 (record
format + candidate enumeration are the judge's input); Phase 4 independent of 2-3; the
calibration set (24) starts during Phase 0 since its regression tests seed it.
