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
| `required_order` | `pattern` appears before `before_pattern` is violated (i.e. wrong order) | pattern, before_pattern, applies_to |
| `forbidden_command` | `pattern` matches a shell command | pattern |
| `required_command` | a command matching `trigger_pattern` ran without a matching `pattern` | trigger_pattern, pattern |
| `forbidden_path` | a written file path matches `pattern` | pattern |

`applies_to` is a list of glob patterns matched against the file path.

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
