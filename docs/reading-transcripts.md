# Reading Claude Code transcripts by hand

Reference for anyone (human or agent) who has to establish **what actually happened** in a
session from its raw log, independently of what this tool reports about it.

The authority on how *this tool* parses transcripts is the pipeline description in the repo
root [`CLAUDE.md`](../CLAUDE.md) (sections 1-3 especially) and the code itself
(`_real_user_prompt_text`, `chronological_segments`, `tool_calls`, `usage_series`). This doc
is the by-hand companion: file layout, event shapes, the traps that produce confidently
wrong conclusions, and extraction recipes that do not melt your context.

Shapes vary by Claude Code version. Treat every field below as "present in transcripts
observed to date", tolerate absence, and never raise on an unfamiliar event type.

---

## 1. Where the logs live

```
~/.claude/projects/<encoded-cwd>/<session-id>.jsonl
```

The encoding replaces both `/` and `.` with `-`, so `/Users/x/famigo/.claude/worktrees`
becomes `-Users-x-famigo--claude-worktrees` (note the doubled dash where `/.` collapsed).

- **Only top-level `*.jsonl` files are sessions.** Subagent runs live in per-session
  subdirectories (`<session-id>/subagents/agent-<task-id>.jsonl`) and are not sessions.
- Sibling files may include a ctxlog under `~/.claude/ctxlog/<session>.jsonl` when the hook
  is installed.
- One line per event, JSON. Lines can be malformed or truncated (a killed session); skip
  what will not parse rather than aborting.
- Files routinely reach tens of megabytes. See §9 before you read one.

---

## 2. Event types

Observed on a real 26MB session:

| `type` | What it is |
|---|---|
| `user` | A user-channel event. **Not necessarily a human prompt** - see §4. |
| `assistant` | A model response event. One response may span several events. |
| `attachment` | Harness-injected context (skill listing, tool deltas, MCP instructions, queued commands). |
| `system` | Harness/system notices, including hook results (`hookCount`, `hookInfos`, `hookErrors`, `hookAdditionalContext`). |
| `last-prompt`, `custom-title`, `queue-operation` | UI/session bookkeeping. Not conversation content. |

Useful top-level keys seen alongside `message`: `timestamp`, `uuid`, `parentUuid`
(the event DAG), `sessionId`, `cwd`, `gitBranch`, `version`, `isMeta`, `isSidechain`,
`requestId`, `promptId`, `effort`, `toolUseResult`, `sourceToolAssistantUUID`,
`permissionMode`, `toolDenialKind`, `attributionMcpServer` / `attributionMcpTool`.

`cwd` is worth grabbing early: it tells you the project the session ran in, which several
rule types are conditional on.

---

## 3. `message.content` shapes

`message.content` is **either a string or a list**, and the list items are typed:

- `{"type": "text", "text": ...}` - assistant prose (or a user prompt in list form).
- `{"type": "thinking", "thinking": ..., "signature": ...}` - see §7.
- `{"type": "tool_use", "id": ..., "name": ..., "input": {...}}` - a tool call.
- `{"type": "tool_result", "tool_use_id": ..., "content": ...}` - its result, on a `user`
  event.

**Trap:** a list-shaped `user` content is not automatically a tool result. A prompt with a
pasted screenshot is also a list (an `image` item plus a `text` item). Distinguish by item
types, never by "is it a list".

---

## 4. Turn boundaries: what counts as a real human prompt

A turn spans one real user prompt to the next. Getting this wrong shifts every later
attribution, so it is the single most consequential judgement you make by hand.

A `user` event is **not** a human prompt when it is:

- a tool-result list (§3),
- `isMeta: true`,
- an interrupt marker or caveat wrapper,
- a `<local-command-stdout>` wrapper, or a `<command-name>` wrapper for a *local* command
  (`/model`, `/config` - recognised by the stdout wrapper that follows),
- **a `<task-notification>` block.**

That last one deserves its own line. A task-notification arrives on the user channel but it
is the *result half* of an `Agent` / `Task` / `Workflow` / background-Bash call - nothing a
human typed. Counting them as turns inflated one real session from 24 turns to 48 and stole
the tool calls that followed from the turn that earned them.

Skill and slash-command wrappers (`<command-name>/commit</command-name>`) **do** count:
a human typed those.

---

## 5. Tool calls, results, and what an edit looks like

- Pair a `tool_use` to its `tool_result` by `tool_use_id`. The `toolUseResult` top-level key
  on the result event often carries structured detail.
- Ordering matters for workflow rules ("lint before commit"). Read calls in event order and
  keep the index; do not assume a tidy interleaving.

**Files get modified in more than one way.** An analyst who counts only edit tools will
conclude "nothing changed" about a session that shipped a feature:

- `Edit` / `Write` / `MultiEdit` / `NotebookEdit` tool calls, and
- `Bash` commands that write: heredocs (`cat > f <<'EOF'`), `tee`, `>` / `>>` redirects,
  `sed -i`, `python - <<'PY'` blocks, `git apply`, patch commands.

Likewise "did the prescribed command run" means searching `Bash` command strings, and a
command can be buried mid-pipeline (`a && b; c | d`), not just at the start.

---

## 6. What was actually in context

- **`<system-reminder>` blocks** in string content carry harness-injected context, including
  memory/CLAUDE.md delivery and file-changed notices.
- **`attachment` events** carry the rest. Types observed: `skill_listing` (the available
  skills and their descriptions - this is how you know what the model could invoke),
  `deferred_tools_delta`, `agent_listing_delta`, `mcp_instructions_delta`, `task_reminder`,
  `queued_command`.
- A file's content reaching the model via a `Read` call is different from it being
  pre-loaded by the harness; both count as delivered, but only the first has a tool call to
  point at. A `Read` with `offset`/`limit` delivered only part of the file - blocks outside
  that range were never seen, and judging them is judging text the model never read.

**Where the delivered text itself lives.** The file on disk today is not evidence of what
the session was given, and a rule document that gained a sentence after the session ended
will otherwise be judged as if the model had read it. Three event shapes carry the text:

- A `Read` result's `toolUseResult` is `{"type": "text", "file": {filePath, content,
  startLine, numLines, totalLines}}`. `content` is the file's own text, no line-number
  gutter. It is the whole file only when `startLine` is 1 and `numLines` is not below
  `totalLines`; anything else is a slice, and the rest of the file is not in the transcript
  at all. Beware `file.base64` - an image read has the same envelope and no text.
- `attachment` events carry `nested_memory`, `already_read_file` and `file` contents
  verbatim. This is the strongest record there is, and it is also the one shape that says
  outright whether it differs from disk (`contentDiffersFromDisk`).
- An `Edit` result carries `originalFile`, the whole file **before** the edit, beside
  `oldString` / `newString`. That is the only record of what a document said before a
  session rewrote it, and a session that rewrites its own CLAUDE.md is exactly the one
  whose earlier turns must not be judged against the new wording. A `Write` result carries
  the post-write `content` the same way.

**Harness injection of CLAUDE.md is not in the transcript.** Across every audited session
the project and global memory files reach the model through the system prompt, which the
`.jsonl` does not store, and no `Contents of …` reminder appears. The only outside record
is the ctxlog hook's `InstructionsLoaded` entry, whose `stats` carry the file's line count,
byte size and a truncated sha256 **as loaded** - not the text, but enough to prove that
today's file is or is not the one the model was given.

---

## 7. Thinking blocks

Availability is mixed by model and version. In one recent transcript, 43 of 82 thinking
blocks carried readable text and the rest were empty with a `signature` (encrypted).

Two rules:

1. Never assume either state - handle both.
2. Even readable thinking is **self-report, not proof**. Models verbalize the influences
   they actually used well under half the time, and an agent stating it followed a rule is
   weak evidence next to a tool call showing it did. Use thinking as corroboration, never as
   the basis for a verdict.

---

## 8. Tokens and usage

Every `assistant` event carries a `usage` object, but **one model response is written as
several events sharing a `message.id`, each repeating the same usage verbatim.** Sum
per-event and you multiply the real cost. Dedupe on `message.id`: one entry per API request.

Fields include `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens` (sometimes split into `ephemeral_1h_input_tokens` /
`ephemeral_5m_input_tokens`). Cache figures prove **prefix stability**, not that a
particular file was resident: caching is prefix-exact, with no per-file granularity.

---

## 9. Surgical extraction (do not `cat` the file)

Stream it. Count first, read second.

Event-type census and turn candidates:

```bash
python3 - "$F" <<'PY'
import json, sys, collections
types = collections.Counter()
with open(sys.argv[1]) as fh:
    for line in fh:
        try: e = json.loads(line)
        except Exception: continue
        types[e.get("type")] += 1
print(dict(types))
PY
```

Every Bash command in order (the workflow-rule evidence):

```bash
python3 - "$F" <<'PY'
import json, sys
with open(sys.argv[1]) as fh:
    for i, line in enumerate(fh):
        try: e = json.loads(line)
        except Exception: continue
        c = (e.get("message") or {}).get("content")
        if isinstance(c, list):
            for it in c:
                if isinstance(it, dict) and it.get("type") == "tool_use":
                    inp = it.get("input") or {}
                    if it.get("name") == "Bash":
                        print(i, "|", (inp.get("command") or "")[:200].replace("\n", " ; "))
PY
```

Swap the filter for `("Edit", "Write", "MultiEdit")` and print `inp.get("file_path")` to see
edits, or for `("Skill", "Agent")` to see invocations.

Locating one thing fast: `grep -c` for a count, `grep -o` for the matches themselves, and
`grep -n` plus a targeted line read when you need the surrounding event. `jq -c 'select(...)'`
works too if you prefer it. What you must not do is pull whole tool results or file contents
into your own context - a single `Read` result can be hundreds of KB.

---

## 10. The trap checklist

Run through this before you commit to any conclusion:

- [ ] Did I treat a `<task-notification>` as a human turn?
- [ ] Did I miss edits made through Bash heredocs, `tee` or redirects?
- [ ] Did I assume list-shaped user content was a tool result (it may be a pasted image)?
- [ ] Did I sum `usage` per event instead of per `message.id`?
- [ ] Did I treat a partial `Read` (offset/limit) as full delivery?
- [ ] Did I treat thinking text, or the assistant's own claim, as proof of compliance?
- [ ] Did I check whether a command appears mid-pipeline, not just at the start of a line?
- [ ] Did I confuse a subagent transcript with the session transcript?
- [ ] Did I infer a violation from absence without enumerating the candidate sites?
- [ ] Did I resolve both sides of a path before deciding a file was untouched?

That last one is quietly the worst: an unresolved path join reports every file as untouched,
and the output looks entirely plausible.

---

## 11. Method: establishing ground truth for a session

1. Census the events (§9) and fix the turn boundaries (§4). Write them down.
2. List what was delivered into context and how (§6), noting partial reads.
3. Build the ordered action list: every tool call with its key arguments, every Bash command,
   every file written by any mechanism (§5).
4. Only then read the rule documents, and for each block ask: did this rule *apply* in this
   session, and does the action list show it followed or broken?
5. Cite evidence per conclusion - quoted command, file path, line. A conclusion you cannot
   cite is `undecidable`, and saying so is the correct answer far more often than it feels.
