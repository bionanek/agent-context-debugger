# Rule compilation prompt (v2)

You are compiling a natural-language guidelines document into machine-checkable rule records. This is the `/compile-rules` flow: you interpret the prose once, here, and the result is a reviewed JSON file that an offline Python tool reads for every later audit.

Your output is consumed by a tool that has no AI available at check time. It knows only what you write here. It will use your output to decide whether an AI coding agent violated a rule during a recorded session, and it will show a red "violation" badge to a developer. A false violation is much worse than a missed one: it accuses the agent of misconduct it did not commit and destroys trust in the whole tool. When in doubt, put the rule in a bucket that refuses to decide.

## The flow

Work through these steps in order, and report each step's result to the user as you go.

1. **Read the document** the user named (or, with no argument, `./CLAUDE.md`, then `~/.claude/CLAUDE.md`, then any `.claude/rules/*.md`). Compile one document per run and write one output file per document.
2. **Extract every rule** as its own record. A section that states three obligations is three records, not one - the tool reports per rule, and a record covering three obligations can only ever report the first. Give each a `rule_ref` (the exact section heading, or a line number when the rule has no heading of its own) and a `statement` phrased as a question with a yes/no answer.
3. **Classify each rule into a bucket** (see *Buckets* below): `deterministic`, `hybrid` or `judged`. Expect most rules not to be deterministic. Across four real guideline documents the earlier version of this prompt produced 32 checks and correctly refused 69% of rules; that refusal rate is the design working.
4. **Generate the record.** For a deterministic rule: patterns, `applies_to`, `fixtures`, and both example lists. For a hybrid or judged rule: the statement, the examples, and (for hybrid) the candidate kind. Every bucket needs `examples_positive` AND `examples_negative` - positive examples expand the region of meaning, negative ones constrain it, and the negatives are what stop an over-eager judge from reading the rule wider than it is.
5. **Verify the fixtures yourself** before writing the file - reason through each pattern against each snippet by the vocabulary table, not by how you would implement the matcher. Then say plainly that your verification does not count: the consuming tool re-runs every fixture with its own matcher and demotes any record that disagrees.
6. **Write `<doc>.checks.json`** beside the document (e.g. `CLAUDE.md.checks.json`; `<stem>.checks.json` also resolves).
7. **Stop and ask for review.** Name the file you wrote, report the counts (how many records per bucket, how many rules refused), and tell the user to read the file before committing it. Its patterns run as written, with no timeout, on every later audit - a pathological regex would hang their build, and a wrong pattern accuses their agent. Do not commit it yourself.

## What the checker can see

For each session it has:

- **written_code**: what the agent's writes left behind, as `(file_path, text)` pairs. For a whole-file write this is the full file. For a partial edit this is ONLY the changed hunk, not the surrounding file. Assume you cannot see the rest of the file. It is the **net** effect: the writes are replayed against each other, so text the agent wrote and then edited away is not here. A source pattern therefore cannot catch an abandoned attempt, and should not try to - a violation the reader cannot find in the tree is worse than none.
- **shell_commands**: the full text of every shell command the agent ran.
- **file_paths**: paths of files created, edited, or read.
- **tool_log**: every tool call the agent made, in call order, each numbered from 0. One call is one LINE, written `<ToolName> <arguments>`, e.g. `Bash gh auth status | head -5`, `Write src/store.ts`, `Read /repo/CLAUDE.md`, `Skill commit`. Arguments are the call's short inputs, whitespace-collapsed onto that one line and truncated at 2000 characters. The input the call is *about* leads (a Bash command, a write's path), and the call's other short inputs follow it - a `timeout`, a `run_in_background`, a `replace_all` - so `Bash git commit -m 'x' 600000` is a line you will really see. Never anchor a pattern with `$`: it would pass your fixtures, whose snippets you wrote yourself, and match nothing at all in a real session. Written file contents are NOT in the line (they are in written_code), and neither is the human-facing `description` the agent attaches to a Bash call - that is prose about the call, and a rule pattern run over prose accuses the wrong thing.
- **candidate sites**: for the omission kinds only, the tool enumerates the places a rule could apply to and asks about each one - `catch_block` (every error handler, with its body) and `comment` (every comment it can read). Nothing else is enumerable today.

The tool log is the only shape that carries order. shell_commands and file_paths are unordered sets of facts, so a rule about sequence ("check the account before running `gh`") cannot be expressed over them at all - use a tool kind.

It cannot parse an AST, resolve types, follow imports across files, or see the repository as a whole. It runs Python regular expressions over the text above. Design within that.

## Buckets

Every record declares one, in `bucket`:

- **`deterministic`** - a pattern over the corpora above decides it, with fixtures that prove the pattern's behaviour. This is the only bucket the tool can decide today, and the only one that can ever mark a rule violated.
- **`hybrid`** - the *sites* are enumerable but the question about each one is semantic ("does this catch body actually handle the error?"). Name the `candidate` kind; the tool extracts the sites deterministically and asks one question per site. This needs the opt-in judge tier (`--judge`): with the tier off - the default - the rule is reported as unchecked, never as followed; with it on, the tool enumerates the sites and asks your statement about each one.
- **`judged`** - purely semantic ("be direct, zero fluff"). No pattern, no sites. Reported as unchecked with the tier off; with it on the verdict is **advisory** - it can flag the rule for a reader but never call it violated or mark it followed.

A rule that fits none of these is not a record at all: put it in `not_checkable` with a one-line `why`.

Prefer `deterministic` only where the pattern is genuinely decisive. A rule forced into `deterministic` with a hopeful regex is the failure mode this whole architecture exists to remove; `hybrid` and `judged` are honest answers offline and are what the opt-in judge tier reads.

## Vocabulary

A `deterministic` record's `kind` must be one of these. Do not invent others.

| kind | fires when | required fields |
|---|---|---|
| `forbidden_pattern` | `pattern` matches in a file matching `applies_to` | pattern, applies_to |
| `required_pattern` | `pattern` is ABSENT from a file matching `applies_to` | pattern, applies_to |
| `forbidden_co_occurrence` | `pattern` and `with_pattern` BOTH appear in the same file | pattern, with_pattern, applies_to |
| `required_co_occurrence` | `pattern` appears but `with_pattern` is absent | pattern, with_pattern, applies_to |
| `required_order` | both patterns are present AND the first match of `first_pattern` starts at a later offset than the first match of `second_pattern`, i.e. they are in the wrong order | first_pattern, second_pattern, applies_to |
| `candidate_requires` | an enumerated site's own text does NOT match `pattern` | candidate, pattern, applies_to |
| `ast_forbidden` | `ast_pattern` matches the syntax tree of a file matching `applies_to` (needs ast-grep; see below) | ast_pattern, applies_to |
| `forbidden_command` | `pattern` matches a shell command | pattern |
| `required_command` | a command matching `trigger_pattern` ran without a matching `pattern` | trigger_pattern, pattern |
| `forbidden_path` | a written file path matches `pattern` | pattern |
| `tool_forbidden` | `pattern` matches a tool-log line | pattern |
| `tool_required` | a line matching `trigger_pattern` exists and NO line matches `pattern` - anywhere in the log, before or after | trigger_pattern, pattern |
| `tool_precedes` | both patterns match some line, but the first match of `second_pattern` comes at a LOWER call number than the first match of `first_pattern` | first_pattern, second_pattern |
| `tool_never_without_prior` | a line matching `pattern` has no earlier match of `prior_pattern` - in an earlier line, or earlier in the same line | pattern, prior_pattern |
| `tool_arg_matches` | a line matching `tool_pattern` whose arguments do NOT match `arg_pattern` | tool_pattern, arg_pattern |
| `tool_call_count` | the number of lines matching `pattern` is above `max_calls` or below `min_calls` | pattern, and at least one of max_calls / min_calls |
| `writes_to_path` | a line matches `trigger_pattern` and no write tool wrote a path matching `pattern` | trigger_pattern, pattern |

`applies_to` is a list of glob patterns matched against the file path. It is required for the source and candidate kinds and ignored by the shell, path and tool kinds, which are not scoped by file.

### Writing tool patterns

Every tool pattern is matched against the whole line, `<ToolName> <arguments>`. So `^Edit\b` selects Edit calls, `\bgh\s+auth\s+status\b` selects a shell command wherever it sits in the line, and `^Bash git commit\b` selects both at once. `arg_pattern` is the one exception: it is matched against the arguments alone, without the tool name.

Two things the tool kinds do that the shell kinds cannot, and which are the reason to reach for them:

- **Order.** `tool_precedes` and `tool_never_without_prior` decide sequence. A rule reading "check the active account with `gh auth status` and switch if needed, before running any `gh` command" is `tool_never_without_prior` with `pattern` = `\bgh\s+(?!auth\b)\w` and `prior_pattern` = `\bgh\s+auth\s+(?:status|switch)\b`. Note what that expresses and a `required_command` could not: **either** branch of "switch if needed" satisfies it, so a session that checked and found the account already correct is compliant rather than accused. A prior earlier *within the same line* counts too: an agent routinely writes the check and the command as one compound call (`gh auth status; gh pr list`), and it would be perverse to condemn the shape that complies most tightly.
- **Any tool, not just Bash.** `Skill`, `Read`, `Task`, `Write` and the rest all appear in the log, so "if you use `Skill`, read the skill file first" is a real check.

Mind which of the two you reach for. `tool_required` is **order-blind**: it asks only whether both things happened. Encode "run the tests after editing source" as `tool_required` and a session that type-checked, then edited, then stopped is reported satisfied - the rule was broken and the block reads as green. Use `tool_precedes` when the rule says before or after, and note its limit honestly: it anchors on the *first* match of each side, so it can say "the tests never ran before any edit" but not "the tests ran after the last edit". A rule that means "after every edit" is not expressible in this vocabulary - put it in `not_checkable` and say why.

For `required_order`, name the patterns in the order the rule demands. A rule reading "call `makePersistable` immediately after `makeAutoObservable`" gives `first_pattern` = `makeAutoObservable`, `second_pattern` = `makePersistable`, and fires when the file has them the other way round. Do not encode the violation itself; encode the required order and let the checker invert it.

Note the asymmetry: `required_pattern` and `required_co_occurrence` are dangerous on partial edits, because the required text may exist elsewhere in a file you cannot see. Only use them when the rule's own scope makes the requirement local to the hunk, and drop the rule's confidence to `low` when you do.

### Rules broken by omission

A rule like "always implement the catch body" is broken by writing *nothing*, so the pattern that would catch it is absent by definition - and a pattern is why "all clear" is the most common wrong answer for this rule shape. Use `candidate_requires` with a `candidate` of `catch_block` or `comment`: the tool enumerates every such site in the written code and cites the site whose own text fails your `pattern`. Where the question about a site needs meaning rather than a pattern ("does this comment explain *why*?"), the record is `hybrid` with the same candidate kind, and no pattern at all.

### Structural rules, and when they are worth the dependency

`ast_forbidden` matches a syntax tree rather than characters, through the optional ast-grep binary. Its `ast_pattern` is code in the target language with ast-grep's metavariables (`$X` for one node, `$$$ARGS` for a list), not a regex: `catch ($$$ARGS) { }` is every empty catch body, in a way no regex can be, because a regex cannot tell a `catch` in a documentation string from one in the code, and cannot tell a body holding only a comment from a body holding a statement.

Reach for it only where the structural question *is* the rule. It costs something real: a reader who has not installed ast-grep gets `not-checkable` for that rule, with the install command, and every other check in the file is unaffected. So a rule a regex decides correctly stays a regex kind.

The fixture gate applies unchanged - patterns are LLM-authored either way, and ast-grep's own coverage is per-grammar (strong for TS/JS/Python/Go, absent for niche languages). Write the fixtures in the language `applies_to` names, and expect the loader to re-run them through ast-grep itself.

## Record format

Every record carries these, whatever its bucket:

- `id` - kebab-case, stable across re-compiles. A changed id looks like a new rule.
- `rule_ref` - the section heading, or a line number in the source document. **This is what binds the record to the rule**; a record that binds to nothing is invisible in every view, so it is refused at load.
- `rule_text` - the rule, quoted or tightly paraphrased.
- `statement` - the question the record answers, phrased so that "yes" means the rule was broken. "Was `pbcopy` fed from `echo` rather than `printf`?"
- `scope` - `code`, `communication` or `process`. What the rule governs.
- `evidence` - `diff`, `files` or `transcript`. Which corpus decides it. Source and candidate kinds read `diff` (the net effect of the writes; the default) or `files` (every hunk the session wrote, including abandoned ones - only ask for this when the rule is about the act of writing rather than about the resulting code). Shell, path and tool kinds read `transcript`. A record declaring an `evidence` its kind cannot read is refused.
- `bucket` - `deterministic`, `hybrid` or `judged`.
- `examples_positive` / `examples_negative` - realistic code or command lines that do and do not break the rule. Mandatory for every bucket. These are about the rule's *meaning*; `fixtures` below are about the *pattern's behaviour*, and they are not the same thing even when the strings coincide.
- `confidence` - exactly `high`, `medium` or `low`.
- `message` - what the developer is told when it fires.
- `rule_key` - optional but recommended: a key over the rule's heading and text. The consumer recomputes it and **skips your record when the rule has since been edited**, rather than applying a check to wording it never read. Omit it if you cannot compute it (the tool's own `rule_checks.rule_key(heading, text)` is the definition); the consumer then binds by `rule_ref` alone.

A `deterministic` record adds its `kind`, its pattern fields, `applies_to` where the kind needs it, and `fixtures`. A `hybrid` record adds `candidate`. A `judged` record adds nothing more.

## Routing

Decide where a rule lives by **the concrete objects it names**, never by its verbs or its modal words.

- Names code identifiers, imports, syntax (`observer()`, `@action`, `useStore`) → source code
- Names a sequence, a condition on the agent's actions, or a count of them ("before", "after", "first", "then", "if needed", "always run X when Y", "only once") → the tool log
- Names shell commands or tools with no order between them (`git commit`, `pbcopy`, `npm run build`) → shell commands
- Names file locations or naming conventions → file paths
- Names a site that has to be there before the rule can be broken (a catch block, a comment) → a candidate kind
- Names nothing concrete → `judged`, or `not_checkable`

Words like "never", "always", "must" tell you how severe a rule is, not where to look. A rule saying "never import X" is about code, not about the shell, even though "import" could be a command name somewhere.

## Not checkable

Put a rule in `not_checkable` when no bucket can carry it. This is a correct answer, not a failure. Typical cases:

- Verifying it needs information nothing in the flow can see (types, cross-file resolution, whole-file context, runtime behaviour)
- It states a positive practice with no detectable failure signature and no enumerable site ("use Observable Maps for keyed state")
- Its key terms are comparative in a way even a judge cannot pin down ("appropriate", "unnecessary", "too high")
- It is a meta-rule about the guidelines themselves rather than about the work

Give a one-line `why` for each. A rule that is subjective but *does* have an enumerable site or a single answerable question is `hybrid` or `judged`, not `not_checkable` - reach for the buckets first, and refuse only what neither can hold.

## Fixtures (mandatory for `deterministic`)

Every deterministic record must carry `fixtures` with `should_match` (code that genuinely violates the rule) and `should_not_match` (code that does not). A record whose fixtures do not reproduce with the consumer's matcher is demoted to the `judged` bucket, visibly, and reported as unchecked (or, with the judge tier on, judged advisorily).

`should_not_match` must include the dominant false-positive sources. At minimum, wherever it applies:

- the identifier appearing inside a line comment or block comment
- the identifier appearing inside a string literal
- a longer identifier that merely contains the target as a substring
- the compliant form of the same code, which often mentions the same words

Write these as realistic code lines, not as toy strings. This is what stops the tool from accusing the agent because a word appeared in a comment.

**For a tool kind, a fixture snippet is a tool log**: one call per line, in order, in exactly the `<ToolName> <arguments>` form above. A multi-line snippet is a sequence, which is the only way an ordering check can be tested at all. So the gh rule above gives `should_match` = `["Bash gh pr create --fill"]` and `should_not_match` = `["Bash gh auth status\nBash gh pr create --fill", "Bash gh auth switch -u me\nBash gh pr list", "Bash git log --author=\"me\""]`. Cover, wherever it applies:

- the compliant order, and the same two calls in the wrong order
- the other branch of a conditional ("switch if needed" has two compliant branches)
- a session that never triggers the rule at all
- a command that merely contains the target as a substring

Do NOT build comment or string guards into your patterns. The checker strips comments and string literals centrally before any pattern runs, and applies that same stripping to these snippets. A guard written into the regex only handles lines that carry a comment marker, which misses the continuation lines of a block comment and gives a false sense of safety. Keep the comment and string cases in `should_not_match` regardless: they verify the stripping, not your regex.

Your own verification of these fixtures does not count. The consuming tool re-runs every one of them with its own matcher, so write patterns whose behaviour follows from the vocabulary table above rather than from how you would implement it.

## What the consuming tool enforces

Assume none of this is negotiable at check time:

- Every deterministic record is re-run against its own `fixtures` with the consumer's matcher. A record that disagrees with its own fixtures is demoted to `judged` and its rule reported as unchecked. Both lists must be non-empty.
- `confidence` must be exactly `high`, `medium` or `low`; a missing or invented value refuses the record. So does a `scope`, `evidence` or `bucket` outside its set, an `evidence` the kind cannot read, a `bucket` with no `rule_ref`, and both `self_test` and `fixtures` on one record (`fixtures` is only the v2 name for `self_test`; two names for one field is two copies that drift).
- A violation is reported only when the pattern matches both the raw text and the comment- and string-stripped text. When the two disagree - the usual cause being a hit that lives only inside a comment - the result is `unclear` and nothing is reported.
- A violation must carry a citable span: file path, line, and the matched text. `required_pattern` fires on absence and so has nothing to quote; the consumer cites the first line of the hunk instead, which is weak. Prefer a kind that has something to point at. A tool finding cites `(tools)` and the 1-based call number, and the tool kinds are built so that the cited call is always the one that went wrong: the `gh` command with no prior check, the call that jumped the queue, the first call past a `max_calls` limit, or the trigger call whose obligation went unmet.
- **Every conditional tool kind reports its two stages separately**, and a conditional whose antecedent never fired is `not-exercised`, never `clear`. Over 30% of real conditional failures are wrong condition-checking rather than a wrong action, so which stage failed is the finding: `antecedent-not-fired` (nothing in the session triggered the rule - no span, because no call supports one), `consequent-missed` (it triggered and the obligation went unmet - this is the violation), `satisfied` (it triggered and was met). You do not write the stage; it follows from the kind. `tool_forbidden` is the one kind with no stage at all: it is not conditional, the call happening is the whole finding, and calling that a missed obligation would describe it wrongly.
- A `candidate_requires` record with no sites in the session is `not-exercised`, never `clear`: nothing was written for the rule to be tested against.
- `tool_call_count` needs `min_calls`, `max_calls` or both, and a `min_calls` above `max_calls` is refused: no session could satisfy it, and no fixture can catch it (a `should_not_match` snippet passes by never firing the pattern). It also cannot accuse a session in which the pattern matched **nothing**: there would be no call to cite, so it reports `antecedent-not-fired`. Use `tool_required` with a `trigger_pattern` for "this must happen at all", and `tool_call_count` for "at most / at least this many times, given that it happened".
- A `ctx-allow` marker in the code at the violation site (same line or the line above, optionally naming your record's `id`) downgrades a finding to acknowledged. Do not try to encode exceptions in your pattern.
- A rule with no record at all is reported as uncompiled, naming this command. A rule the tool cannot decide is never rendered as one that was followed.

## Output

Write JSON only into the file, no prose around it.

```json
{
  "source": "<path of the guidelines file>",
  "checks": [
    {
      "id": "kebab-case-stable-id",
      "rule_ref": "<section heading, or line number, in the source doc>",
      "rule_text": "<the rule, quoted or tightly paraphrased>",
      "statement": "<the question, phrased so yes means the rule was broken>",
      "scope": "code|communication|process",
      "evidence": "diff|files|transcript",
      "bucket": "deterministic|hybrid|judged",
      "domain": "source|shell|path|tool",
      "kind": "<one of the vocabulary kinds; deterministic records only>",
      "candidate": "catch_block|comment",
      "pattern": "<Python regex>",
      "applies_to": ["**/*.ts", "**/*.tsx"],
      "confidence": "high|medium|low",
      "rule_key": "<optional: 16-hex key of the rule's heading + text>",
      "message": "<what the developer is told when this fires>",
      "examples_positive": ["<a line that breaks the rule>"],
      "examples_negative": ["<a line that does not>"],
      "fixtures": {
        "should_match": ["..."],
        "should_not_match": ["..."]
      }
    }
  ],
  "not_checkable": [
    { "rule_ref": "...", "rule_text": "...", "why": "..." }
  ]
}
```

Confidence: `high` = the pattern is unambiguous and the false-positive cases are covered by your fixtures. `medium` = it works but relies on a naming convention or a heuristic. `low` = plausible but you expect false positives, or it depends on unseen file context.

Patterns are Python `re` syntax, applied with `re.MULTILINE` to the written text. Escape regex metacharacters in identifiers: `observer\(`, `@action\b`.

## After writing the file

Report, in this order:

1. The path you wrote.
2. Counts: records per bucket, rules refused as `not_checkable`, and the total rules you found in the document (they must add up - a rule that appears in neither list is a rule you silently dropped).
3. The records you are least sure about, by id, and why.
4. That the file is now a reviewable repo artifact and the user should read it before committing: every pattern in it will run, as written, against their own code on every later audit.
