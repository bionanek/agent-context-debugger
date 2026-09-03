# standup

- **standup** (`~/.claude/skills/standup/SKILL.md`) - przejrzyj dzisiejsze zmiany
  w gicie i przygotuj notatkę na standup.
  Wyzwalacz: `/standup`

# Pamięć błędów

Gdy podejście okaże się błędne kierunkowo, zapisz je w
`~/.claude/ERRORS.md` przed zakończeniem sesji.

**Co zawiodło:** podejście i dlaczego wydawało się sensowne
**Co zadziałało:** podejście zastępcze

# Schowek

Nigdy nie przekazuj `echo` do `pbcopy`; użyj `printf`, aby usunąć znak nowej
linii na końcu.

# Bramka jakości

Przed zgłoszeniem zadania jako gotowego uruchom testy z katalogu głównego:

```bash
pytest -q
```
