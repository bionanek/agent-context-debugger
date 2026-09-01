# Rule translation prompt (v1)

You are compiling a natural-language guidelines document into machine-checkable rules.

Your output is consumed by an offline Python tool that has no AI available at check time. It knows only what you write here. It will use your output to decide whether an AI coding agent violated a rule during a recorded session, and it will show a red "violation" badge to a developer. A false violation is much worse than a missed one: it accuses the agent of misconduct it did not commit and destroys trust in the whole tool. When in doubt, mark a rule not checkable.

## What the checker can see

For each session it has:

- **written_code**: every edit the agent made, as `(file_path, text)` pairs. For a whole-file write this is the full file. For a partial edit this is ONLY the changed hunk, not the surrounding file. Assume you cannot see the rest of the file.
- **shell_commands**: the full text of every shell command the agent ran.
- **file_paths**: paths of files created, edited, or read.

It cannot parse an AST, resolve types, follow imports across files, or see the repository as a whole. It runs Python regular expressions over the text above. Design within that.

## Vocabulary

Emit only these predicate kinds. Do not invent others.

| kind | fires when | required fields |
|---|---|---|
| `forbidden_pattern` | `pattern` matches in a file matching `applies_to` | pattern, applies_to |
| `required_pattern` | `pattern` is ABSENT from a file matching `applies_to` | pattern, applies_to |
| `forbidden_co_occurrence` | `pattern` and `with_pattern` BOTH appear in the same file | pattern, with_pattern, applies_to |
| `required_co_occurrence` | `pattern` appears but `with_pattern` is absent | pattern, with_pattern, applies_to |
| `required_order` | both patterns are present AND the first match of `first_pattern` starts at a later offset than the first match of `second_pattern`, i.e. they are in the wrong order | first_pattern, second_pattern, applies_to |
| `forbidden_command` | `pattern` matches a shell command | pattern |
| `required_command` | a command matching `trigger_pattern` ran without a matching `pattern` | trigger_pattern, pattern |
| `forbidden_path` | a written file path matches `pattern` | pattern |

`applies_to` is a list of glob patterns matched against the file path.

For `required_order`, name the patterns in the order the rule demands. A rule reading "call `makePersistable` immediately after `makeAutoObservable`" gives `first_pattern` = `makeAutoObservable`, `second_pattern` = `makePersistable`, and fires when the file has them the other way round. Do not encode the violation itself; encode the required order and let the checker invert it.

Note the asymmetry: `required_pattern` and `required_co_occurrence` are dangerous on partial edits, because the required text may exist elsewhere in a file you cannot see. Only use them when the rule's own scope makes the requirement local to the hunk, and drop the rule's confidence to `low` when you do.

## Routing

Decide where a rule lives by **the concrete objects it names**, never by its verbs or its modal words.

- Names code identifiers, imports, syntax (`observer()`, `@action`, `useStore`) → source code
- Names shell commands or tools (`git commit`, `pbcopy`, `npm run build`) → shell commands
- Names file locations or naming conventions → file paths
- Names nothing concrete → not checkable

Words like "never", "always", "must" tell you how severe a rule is, not where to look. A rule saying "never import X" is about code, not about the shell, even though "import" could be a command name somewhere.

## Not checkable

Mark a rule `not_checkable` when any of these hold. This is the expected outcome for a large share of rules, often more than half. It is a correct answer, not a failure.

- It is a matter of judgment, taste, or degree ("prefer the simplest", "keep it readable", "wrap at leaf components")
- Verifying it needs information the checker cannot see (types, cross-file resolution, whole-file context, runtime behaviour)
- It states a positive practice with no detectable failure signature ("use Observable Maps for keyed state")
- Its key terms are subjective or comparative ("appropriate", "unnecessary", "too high")
- You would have to guess at the pattern

Give a one-line `why` for each. Do not stretch a rule into a check just to produce output.

## Self-tests (mandatory)

Every check must carry `should_match` (code that genuinely violates the rule) and `should_not_match` (code that does not). A check whose self-tests fail is discarded.

`should_not_match` must include the dominant false-positive sources. At minimum, wherever it applies:

- the identifier appearing inside a line comment or block comment
- the identifier appearing inside a string literal
- a longer identifier that merely contains the target as a substring
- the compliant form of the same code, which often mentions the same words

Write these as realistic code lines, not as toy strings. This is what stops the tool from accusing the agent because a word appeared in a comment.

Do NOT build comment or string guards into your patterns. The checker strips comments and string literals centrally before any pattern runs, and applies that same stripping to these snippets. A guard written into the regex only handles lines that carry a comment marker, which misses the continuation lines of a block comment and gives a false sense of safety. Keep the comment and string cases in `should_not_match` regardless: they verify the stripping, not your regex.

Your own verification of these tests does not count. The consuming tool re-runs every self-test with its own matcher and discards any check that fails, so write patterns whose behaviour follows from the vocabulary table above rather than from how you would implement it.

## What the consuming tool enforces

Assume none of this is negotiable at check time:

- Every check is re-run against its own `should_match` and `should_not_match` cases with the consumer's matcher. A check that disagrees with its own self-tests is discarded and its rule reported as not checkable. Both lists must be non-empty.
- `confidence` must be exactly `high`, `medium` or `low`; a missing or invented value discards the check.
- A violation is reported only when the pattern matches both the raw text and the comment- and string-stripped text. When the two disagree - the usual cause being a hit that lives only inside a comment - the result is `unclear` and nothing is reported.
- A violation must carry a citable span: file path, line, and the matched text. `required_pattern` fires on absence and so has nothing to quote; the consumer cites the first line of the hunk instead, which is weak. Prefer a kind that has something to point at.
- A `ctx-allow` marker in the code at the violation site (same line or the line above, optionally naming your check's `id`) downgrades a finding to acknowledged. Do not try to encode exceptions in your pattern.
- Optionally include `rule_key`: the consumer computes the same key from the rule's heading and text, and skips your check if the rule has since been edited. Omit it if you cannot compute it; the consumer then binds your check by `rule_ref` alone.

## Output

Return JSON only, no prose around it.

```json
{
  "source": "<path of the guidelines file>",
  "checks": [
    {
      "id": "kebab-case-stable-id",
      "rule_ref": "<line number or section heading in the source doc>",
      "rule_text": "<the rule, quoted or tightly paraphrased>",
      "domain": "source|shell|path",
      "kind": "<one of the vocabulary kinds>",
      "pattern": "<Python regex>",
      "applies_to": ["**/*.ts", "**/*.tsx"],
      "confidence": "high|medium|low",
      "rule_key": "<optional: 16-hex key of the rule's heading + text>",
      "message": "<what the developer is told when this fires>",
      "self_test": {
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

Confidence: `high` = the pattern is unambiguous and the false-positive cases are covered by your self-tests. `medium` = it works but relies on a naming convention or a heuristic. `low` = plausible but you expect false positives, or it depends on unseen file context.

Patterns are Python `re` syntax, applied with `re.MULTILINE` to the written text. Escape regex metacharacters in identifiers: `observer\(`, `@action\b`.
