# Plan: the judge as a second opinion, not an overruler

> Source measurement: the blind-judge experiment of 2026-11-04. A judge was handed exactly
> what the human ground-truth author was handed (`snapshots/inventory.py`'s three views plus
> `snapshots/expected/RULINGS.md`) and never the tool's verdict, then scored against the same
> answer key on the same block set.
>
> | | agrees with ground truth |
> |---|---|
> | deterministic tier | 274/399 = 68.7% |
> | blind judge | 296/399 = 74.2% |
>
> | error kind | judge | code |
> |---|---|---|
> | false-green | **53** | **2** |
> | false-red | 11 | 0 |
> | missed-compliance | 28 | 84 |
>
> judge right / code wrong: 94. code right / judge wrong: 72. They disagree at all on
> 173/399 = 43.4%.
>
> Caveat carried into Phase 0: 111 of 532 calls failed, taking three whole sessions
> (reband `22c58939`, formicHMI `8fd8526c`, `12f48cdb`) out of the scored set, and those
> failures skewed toward `used` truths (60 of 111). The 74.2% is five sessions, not eight.

## The conclusion this plan implements

The judge is better at noticing a rule **was** followed and far worse at not inventing
compliance that never happened. So it may inform a reader and must never award a badge.
Where the code is weak - 84 missed compliances - the fix that actually scales is a compiled
check, not a model: 457 of 510 blocks in the corpus carry no compiled record at all, which is
the real reason the code stays silent.

Ordered by what moves reliability most per unit of work: **Phase 0 and Phase 1 first**.
Phases 2-3 are worth nothing until Phase 0 says what "worse" even means.

Phase 0 was rewritten on 2026-11-04 after its own premise failed: a scan of all 1,093
transcripts found no clean rule violation, because this author authorises the actions that
trip a rule. What it found instead was a false-red generator in the first checks file ever
compiled, which is a more urgent problem than the one it went looking for.

## Architectural decisions

- **The judge runs by default; the offline path stays complete and testable.** This is a
  deliberate change to the trust contract, made for usability: the tool is for this author's
  daily use and a tier nobody switches on is a tier that does not exist. The cost is stated
  plainly rather than softened - **by default, session content (prompts, code, rule
  documents) is sent to Anthropic through the user's own Claude Code CLI.** What survives is
  not the no-network claim but the two things that made it worth having: `--no-judge`
  produces a byte-identical offline report, and no judge answer can ever award a badge.
- **No judge verdict may produce a green or a red badge.** `_apply_rule_check` already
  filters advisory findings before deciding a badge; that stays, and Phase 2's `contested`
  flag is a *third* thing shown beside the badge, never a replacement for it.
- **Payload remains additive only** (`tests/test_rollup.py::test_payload_is_purely_additive`).
  `contested` and the relevance/consent fields are appended keys.
- **Anything the page shows is computed in Python and baked**, so `--query` and the page
  cannot describe one session two ways.
- **A measurement with no red path measures nothing.** Phase 0 is a blocker for the claims
  Phases 1-3 will want to make.

---

## Phase 0: user-authorised overrides, and the false-red corpus

**Rewritten on 2026-11-04 after the candidate hunt failed.** The original premise was "add
3-4 sessions that break a rule". A scan of all 1,093 transcripts found **zero** clean ones,
and the reason is structural rather than bad luck: this author works with the agent in the
loop, so the actions that trip a rule are the ones they asked for.

Every push-to-master candidate was explicitly ordered in the prompt that caused it:

| session | the prompt that caused the push |
|---|---|
| `c37b4f96` | "/commit and push to master" |
| `9061535d` | "/commit and push to master" |
| `a0f594f9` | "/commit and push" |
| `3a705721` | "use /commit and force push to master" |
| `d37263c9` | "push" |
| `1efb73f1` | "/commit and push" |

The one gh candidate (`9cf0b16d`) ran `gh repo view` / `gh api` against a public repo whose
URL the user pasted - which RULINGS.md already cites for something narrower (a wrongly
credited `used`), not for a violation.

**So the corpus gains a false-red set instead of a red one**, and it is more valuable: the
OZZ `no-push-to-master` record compiled on 2026-11-04 - confidence `high` - fires on all six
sessions above and red-badges an agent for doing what it was told. A false red is the
failure this entire architecture exists to prevent, and one is sitting in the first checks
file ever generated.

### The gap

`ctx-allow` lets *code* carry a deliberate exception at the violation site. There is no
transcript equivalent, so "the user typed `push to master` in the prompt that caused this
call" - the strongest rationale there is - is invisible to the checker.

### The design

`acknowledged` already exists as a block state and already means "a violation the site
deliberately suppresses". A user-authorised action is the same shape, so it reuses the state
rather than inventing a status:

- **Offline**: the finding stays `violated`, and the report shows **the governing prompt
  verbatim** beside the cited call - the prompt of the turn the call belongs to. No prose
  matching, no language assumption: turns are already prompt-to-prompt and findings already
  cite a call index, so the join is positional. The reader settles it in one glance.
- **With the judge**: one narrow question per finding - *did the user, in this turn, instruct
  the action this call performs?* - with the prompt and the command and nothing else. A yes
  downgrades the finding to `acknowledged` and names the prompt as the rationale. This is the
  judge doing what it is genuinely good at and what no pattern can do language-neutrally.

Deciding authorisation by matching English in the prompt is explicitly rejected: it is the
single-user prose matching this project retired in step 6, and it would read a Polish prompt
as silence.

### Tests (write first - red)

- `tests/test_rule_checks.py`: a finding carries `governingPrompt` (text, turn index, call
  index), and it is the prompt of the turn the cited call falls in - not the nearest earlier
  prompt by event index, which differs whenever a turn opens with tool calls.
- `tests/test_rule_checks.py`: a finding whose cited call sits in a turn with no real user
  prompt (an agent-driven or notification-driven turn) carries no `governingPrompt` and stays
  `violated`. Absence must not read as authorisation.
- `tests/test_judge_tier.py`: the authorisation question is asked once per finding, carries
  only the prompt and the command, and a `yes` yields `acknowledged` with the prompt quoted
  as the rationale.
- `tests/test_judge_tier.py`: a `no`, an unparseable answer, or an unreachable judge all
  leave the finding `violated`. Only an affirmative answer may downgrade.
- `tests/test_generalization.py`: no English word list decides authorisation - the offline
  path reads only turn structure, and a Polish-prompt fixture produces the identical
  `governingPrompt` join as its English twin.
- `tests/test_degradation.py`: with the judge off, no finding is ever `acknowledged` by this
  mechanism, and that is "signal unavailable", not a worse verdict.

### The false-red corpus

Freeze the six sessions above plus `9cf0b16d`. Their ground truth is **not** a `violated`
row: each is a new truth class, `authorised`, meaning the rule's action happened and the user
asked for it. `snapshots/compare.py` scores a red badge on an `authorised` row as a
**false red**, which is already a release blocker.

Privacy, since three of these are a real client's repo: transcripts stay gitignored
(`tests/test_privacy.py` holds it). Evidence prose cites the call number and the command
shape only - no document filenames, no commit-message text, no spec content. The governing
prompt is quoted in the *report*, which is generated locally and never committed; what lands
in git is the ground-truth row, and those quote nothing from OZZ's documents.

### Docs to update

- `snapshots/expected/RULINGS.md`: add the `authorised` truth class and why it is not
  `violated` - the rule's action happened, and the agent obeying an explicit instruction is
  not misconduct.
- `CLAUDE.md` rule-checks section: the `governingPrompt` join and the judged authorisation
  question, including the explicit refusal to decide authorisation by matching prose.
- The OZZ worked example: note that `no-push-to-master` at confidence `high` is correct as a
  pattern and still needs this mechanism, because the pattern is not what was wrong.

### Acceptance criteria

- All seven sessions frozen with `authorised` ground truth, and `compare.py` scoring a red
  badge on any of them as a false red.
- Offline: every one of the six still reads `violated`, and every report shows the governing
  prompt beside the cited call.
- Judge on: all six downgrade to `acknowledged`, each naming the prompt, and the corpus's
  false-red count returns to zero.
- A finding in a turn with no user prompt is never downgraded, proved by a test.
- **Still open, and named rather than hidden**: the corpus has no genuine unsupervised
  violation. Until one exists, "the tool produces no false reds" is measured against
  authorised actions only, and the scorecard header must say so. Candidate hunting ground for
  a later phase: subagent and workflow runs, where no human authorised each step.

---


## Phase 1: make compiling rules the normal first run

**Why**: 457 of 510 corpus blocks have no compiled record. The OZZ pilot turned 46 prose
rules into 17 deterministic checks, 9 judged and 20 honestly refused, with **0 rejected and
0 demoted** at the loader gate. That is where the 84 missed compliances actually go away.

### Tests (write first - red)

- `tests/test_compile_flow.py`: `--query sessions` names `/compile-rules` with the count of
  *uncompiled rule documents in this project*, not a generic hint, and the line disappears
  when nothing is left to compile.
- `tests/test_rule_checks.py`: a checks file that exists but whose records are all `judged`
  reports the document as `refused`, never as `compiled` - a reader must not read "compiled"
  as "decidable".
- `tests/test_generalization.py`: the two ast-only rule shapes (an import path, a UI string)
  report `not-checkable` with the install command rather than being approximated.

### Implementation (green)

1. Extend `_rule_compile_rollup` so the per-document breakdown names the *bucket mix*
   (`deterministic` / `judged` / refused), not only the compiled count. A document that
   compiled entirely into `judged` is not progress toward offline decidability and the
   report should say so.
2. Add `--compile-status` to `--query`: one screen listing every rule document in the
   project, its state, its bucket mix, and the exact command to compile the next one.
3. Ship the OZZ checks file as a worked example under `docs/` (redacted of anything
   project-specific) so a new user sees what a good one looks like before writing theirs.
4. Document the two string-literal traps found in the pilot, because they will bite everyone:
   a rule about an **import path** or about **UI text in code** cannot be matched by
   characters (`strip_comments_and_strings` blanks string literals unconditionally), so it is
   `ast_forbidden` or it is `not_checkable`.

### Docs to update

- `CLAUDE.md` Rule-checks section: the bucket-mix reporting and the string-literal trap.
- `prompts/translate-rules.md`: name the string-literal trap in the Routing section, with the
  two concrete rule shapes it kills. The pilot hit it on three separate rules.

### Acceptance criteria

- `--query sessions` on a project with uncompiled rules names the command and the count;
  on a fully compiled one it says nothing.
- The compile-status screen round-trips: compile a document, re-run, the line moves.
- Re-scoring the corpus with the new checks files reduces `missed-compliance` below the
  current 84, measured, with the number in `SCORECARD.md`.

---

## Phase 2: the `contested` flag, scoped narrowly

**Why narrow**: judge and code disagree on 43.4% of blocks. Flagging all of that is noise
with a confidence score attached. The disagreement worth a reader's attention is the one
pointing at the code's known hole: the judge sees compliance where the code is silent.

### The rule

A block is `contested` when **all** of:

- the code's status is in the NOT-USED family (`unused` / `dormant`), and
- the judge, asked blind, answered `used`, and
- the judge's answer carries a quoted span that `_quote_span` resolves in the evidence it was
  given.

Nothing else is contested. In particular a judge `violated` answer never contests a code
green: that direction is where its 11 false reds live, and the code's red path requires a
citation by construction.

### Tests (write first - red)

- `tests/test_judge_tier.py`: a judge `used` against a code `dormant` sets `contested` and
  leaves `status` untouched.
- `tests/test_judge_tier.py`: a judge `violated` against a code `used` sets nothing at all.
- `tests/test_judge_tier.py`: a judge answer whose quote is not in the handed evidence is
  discarded, not contested - same rule the relevance question already applies.
- `tests/test_rollup.py`: `contested` is an appended key and the golden payload still passes
  the additive check.
- `tests/test_degradation.py`: with the judge off, no block is ever `contested`, and that is
  "signal unavailable", not a worse verdict.

### Implementation (green)

1. Bake `contested: {judgeVerdict, quote, reason}` on the block record. Computed in Python.
2. Render it as a distinct chip beside the badge, with text that says what it is: *the judge,
   asked without seeing this verdict, read this block as used*. It is not a badge and must
   not be coloured like one.
3. `--query <block-id>` prints a `contested` line with the same three fields.
4. Count contested blocks in the session rollup so a reader can see at a glance whether this
   session has a judging disagreement problem.

### Docs to update

- `CLAUDE.md` step 8: `contested` is not a status, cannot combine, and never reaches
  `combine_verdicts`.
- `README.md`: one paragraph on what a contested chip licenses the reader to conclude
  (go look), and what it does not (the verdict is wrong).

### Acceptance criteria

- On the corpus, contested fires on a bounded fraction of blocks - target under 15%, measured
  and recorded. If it lands near 43% the scoping rule is wrong and this phase stops.
- No block's `status` differs between a judge-on and judge-off run
  (`tests/test_degradation.py` covers it).

---

## Phase 3: the judge on by default, and degradation as a feature

**Decision**: the judge runs without a flag. The no-network-by-default claim is retired
deliberately, in favour of a tool that is useful without remembering a flag. Cost is not the
objection it looked like: only `judged`-bucket records are asked (9 for all of OZZ), one call
each, cached by `(rule_key, question hash, candidate content hash, model id)`, so a re-audit
pays only for what changed. The experiment's 6.8M tokens came from judging every block and
re-sending the whole action list each time; the production tier sends one candidate site,
capped at `MAX_TOTAL_CHARS` (12k).

**What replaces the retired guarantee.** Three properties, each with a test, because
"default-on" must not quietly mean "the offline path rots":

1. `--no-judge` produces a report **byte-identical** to the pre-change offline build.
2. A judge that cannot be reached - no auth, no CLI, no network - degrades to exactly the
   offline report plus a visible note, never to a failed bake and never to a worse verdict.
3. No judge answer awards a badge, in either direction.

The structural import-graph test is **replaced, not deleted**. Deleting a guarantee's test
and calling the guarantee retired is how a suite goes green while the behaviour rots; the
replacement asserts properties 1 and 2, which is what the import test was really protecting.

### Tests (write first - red)

- `tests/test_judge_tier.py`: a default run with parked `judged` records asks the judge, with
  no flag. (The inversion of the current default-off test.)
- `tests/test_judge_tier.py`: `--no-judge` yields a payload byte-identical to the offline
  build - the replacement for `test_the_default_path_never_imports_the_tier`, comparing
  payloads rather than asserting on imports.
- `tests/test_judge_tier.py`: an unauthenticated CLI (the real failure seen on 2026-11-04,
  `exited 1: no output`) produces the full offline report plus a `judgeUnavailable` note, a
  zero exit code, and **no** status different from the offline run.
- `tests/test_judge_tier.py`: a judge timeout mid-bake leaves every already-cached answer on
  disk and the remaining blocks reading as unasked, not as doubted.
- `tests/test_degradation.py`: the judge tier is tested in both directions - its absence must
  not make a verdict worse, and the *default* report must not depend on it.
- `tests/test_privacy.py`: the first run on a machine prints what will be sent and where,
  once, and records that it was shown. A notice, not a gate.

### Implementation (green)

1. `make_judge` builds a runner unless `--no-judge`. `build_real_view` may now import
   `judge_tier` at module level; `CLAUDE.md`'s conventions section is rewritten to match
   rather than left stating a property the code no longer has.
2. Every judge failure path returns the offline answer with a note. No bake fails because the
   judge did; the exit code is unchanged.
3. A one-time notice (not a prompt) on first run per machine: what gets sent, to whom, the
   model, where the cache lives, and the `--no-judge` flag. Recorded in
   `~/.claude/ctxide/config.json` so it prints once.
4. Every report names its mode - `judged`, `offline (--no-judge)`, or
   `offline (judge unavailable: <reason>)` - in the page header and in `--query`. A reader
   must never have to guess whether a model was behind a verdict.
5. `hybrid` candidate judging is on by default too, under the same degradation rules. It is
   the path that can leave a block `clear`, so its existing guard stands: a record with any
   unexamined site reads `not-checkable`, never `clear`.

### Docs to update

- `CLAUDE.md` conventions: **delete** the "never call an LLM and never make a network request
  in default mode" rule and replace it with what is true - the judge runs by default,
  `--no-judge` is the offline path, the judge never awards a badge, and failure degrades to
  the offline report. A stale guarantee in the project's own instructions is worse than no
  guarantee.
- `README.md` trust model: rewritten and demoted from a headline claim to an honest
  description, stating plainly that session content is sent by default and how to turn it off.
- `docs/judgement-reliability-research.md` §9.1: note that the opt-in framing was superseded
  on 2026-11-04 and why, so the research doc does not contradict the code.

### Acceptance criteria

- A default run with no flag asks the judge and names the mode in the report.
- `--no-judge` is byte-identical to the pre-change offline payload.
- With the CLI logged out, the bake succeeds, exits 0, reports every offline verdict
  unchanged, and says why the judge is missing.
- No verdict in the corpus differs between judge-on and judge-off
  (`tests/test_degradation.py`).

---


## Phase 4: re-measure and publish

### Implementation

1. Re-run `snapshots/compare.py` over the enlarged corpus with the new checks files.
2. Re-run the blind-judge harness and recompute the four-way split (both right / judge only /
   code only / neither).
3. Write the results into `SCORECARD.md` with the false-green and false-red counts for **both**
   tiers side by side, since that pair is the whole argument for the architecture.

### Acceptance criteria

- `missed-compliance` down against the pre-Phase-1 baseline, with the number stated.
- Code false-greens still ≤ 2, and false-reds 0 across both the original corpus **and** the
  seven `authorised` sessions Phase 0 adds. **If compiling more rules raises either, that is
  a release blocker**, not a trade to accept: the compiled path is the only thing allowed to
  accuse, so a false red there is the worst failure this tool has.
- The scorecard header states that no genuine unsupervised violation is in the corpus yet, so
  a reader never mistakes "no false reds over authorised actions" for "no false reds".
- The contested rate stated, and the judge's own false-green count stated beside it, so a
  reader can see why the judge does not get a badge.

---

## What this plan deliberately does not do

- **It does not let the judge overrule a code verdict in either direction.** 53 false greens
  against 2 is the measurement; no confidence threshold rescues that, because the judge is
  confident when it is wrong.
- **It does not add a second judge to break ties.** Judges handed each other's output agree
  with each other, not with the truth - the same mechanism `snapshots/inventory.py` exists to
  prevent on the human side.
- **It does not try to judge every block.** The experiment did, and that is where the 6.8M
  tokens went. Production asks about parked records only.
