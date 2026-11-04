# How to talk to me

ANSWER FIRST. Open every response with one plain-language sentence that answers
the question. No preamble.

## Copy to clipboard

When copying any text to the clipboard, always pipe it through `printf` - never
`echo` - so that terminal-injected trailing whitespace is stripped.

```bash
printf '%s' "$content" | pbcopy
```

## GitHub account per project

Before running any `gh` command (PR creation, issue management, etc.), check the
active GitHub account with `gh auth status` and switch if needed:

| Project path contains | Required account | Switch command |
|-----------------------|-----------------|----------------|
| `figma` | `bionanek` | `gh auth switch -u bionanek` |
| `formic` | `bionanek-x` | `gh auth switch -u bionanek-x` |

**Rule:** If the active account doesn't match the project, run the switch
command silently before proceeding.

## End-of-implementation summary

After implementing any code change (bug fix, feature, refactor, or anything that
modifies behavior), always end your response with a brief user-facing summary:
what changed from the user's perspective. Keep it to 1-3 sentences. Focus on
observable behavior, not technical details.
