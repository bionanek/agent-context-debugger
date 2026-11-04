# standup

- **standup** (`~/.claude/skills/standup/SKILL.md`) - scan today's git activity
  and draft the standup update.
  Trigger: `/standup`

# Error Memory

When an approach turns out to be wrong in direction, log it in
`~/.claude/ERRORS.md` before ending the session.

**What failed:** the approach and why it seemed reasonable
**What worked:** the replacement approach

# Clipboard

Never pipe `echo` into `pbcopy`; use `printf` so the trailing newline is
stripped.

# Quality gate

Before reporting a task done, run the suite from the repo root:

```bash
pytest -q
```
