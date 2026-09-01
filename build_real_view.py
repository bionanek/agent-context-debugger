#!/usr/bin/env python3
"""
Parse a real Claude Code transcript + CLAUDE.md (global + project + skills)
and emit a self-contained HTML view with the data baked in.
"""
import argparse
import difflib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ctxlog_facts
import rule_checks

DEFAULT_CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"
DEFAULT_SKILLS_DIR = Path.home() / ".claude" / "skills"
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def encode_cwd_for_projects(cwd):
    """Claude Code stores transcripts under ~/.claude/projects/<encoded>/.

    Encoding: replace both '/' and '.' with '-'. The dot is easy to miss because
    most project paths have none, but any that does (a dotfile directory, a
    dotted app name) lands in a differently-named folder: /x/famigo/.claude/
    worktrees encodes as -x-famigo--claude-worktrees, with the doubled hyphen
    coming from the slash and the dot in a row.
    """
    return cwd.replace("/", "-").replace(".", "-")


def discover_all_transcripts(cwd, projects_dir=DEFAULT_PROJECTS_DIR):
    """Return this cwd's top-level transcript paths, newest first.

    Only top-level *.jsonl files count. Subagent transcripts now live in
    per-session subdirectories, so they are excluded by not recursing. The old
    per-file `isSidechain` probe that used to filter them is gone: it read only
    line 1, which in real transcripts is an event type that never carries the
    flag, so it excluded nothing while costing an open() per candidate.
    """
    encoded = encode_cwd_for_projects(str(cwd))
    project_dir = projects_dir / encoded
    if not project_dir.is_dir():
        return []
    candidates = [p for p in project_dir.glob("*.jsonl") if p.is_file()]
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)


def discover_transcript(cwd, projects_dir=DEFAULT_PROJECTS_DIR):
    """Most recent transcript for this cwd, or None."""
    paths = discover_all_transcripts(cwd, projects_dir)
    return paths[0] if paths else None


def summarize_transcript(path):
    """Lightweight metadata pass — used for the session picker list."""
    events = load_transcript(path)
    if not events:
        return None
    calls = tool_calls(events)
    user_prompt = first_real_user_prompt(events) or ""
    session_id = next((e.get("sessionId") for e in events if e.get("sessionId")), path.stem)
    branch = next((e.get("gitBranch") for e in events if e.get("gitBranch")), "")
    timestamps = [e.get("timestamp") for e in events if e.get("timestamp")]
    start = timestamps[0] if timestamps else ""
    end = timestamps[-1] if timestamps else ""

    def _pts(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    s_dt, e_dt = _pts(start), _pts(end)
    duration_sec = int((e_dt - s_dt).total_seconds()) if s_dt and e_dt else 0

    return {
        "id": session_id,
        "path": str(path),
        "promptPreview": (user_prompt[:140] + "…") if len(user_prompt) > 140 else user_prompt,
        "startTime": start,
        "endTime": end,
        "durationSec": duration_sec,
        "branch": branch,
        "events": len(events),
        "toolCalls": len(calls),
        "userMessages": count_real_user_prompts(events),
        "usage": usage_totals(usage_series(events)),
    }


def file_slug(path):
    """Slug for a context-file path, used to namespace block IDs."""
    s = re.sub(r"[^a-z0-9]+", "-", str(path).lower()).strip("-")
    return s[-40:]  # tail is more identifying than head

# ---------- 1. parse CLAUDE.md into blocks ----------

def parse_claude_md(text):
    """Split CLAUDE.md into blocks at H1/H2 headings (ignoring those inside fenced code blocks).

    `start_line` / `end_line` are 1-based and inclusive, spanning the heading
    through the block's last content line. They exist so a block can be checked
    against the byte range its file actually delivered to the model.
    """
    lines = text.splitlines()
    blocks, current_title, current_lines, current_level = [], None, [], None
    current_start = None
    in_fence = False

    def flush(end_line):
        if current_title is not None:
            content = "\n".join(current_lines).strip()
            blocks.append({
                "title": current_title.strip(),
                "level": current_level,
                "content": content,
                "start_line": current_start,
                "end_line": end_line,
            })

    for lineno, line in enumerate(lines, 1):
        # Toggle code-fence state on ``` or ~~~ at start of line
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            current_lines.append(line)
            continue
        if in_fence:
            current_lines.append(line)
            continue
        m = re.match(r"^(#{1,2})\s+(.*?)\s*$", line)
        if m:
            flush(lineno - 1)
            current_lines = []
            current_title = m.group(2)
            current_level = len(m.group(1))
            current_start = lineno
        else:
            current_lines.append(line)
    flush(len(lines))
    return blocks


def classify_block(title, content):
    """Heuristic block typing."""
    t = title.lower()
    c = content.lower()
    if "rules" in t and "global" in t:
        return "overview"
    if "skill" in t or "trigger:" in c or re.search(r"`/[a-z]+`", content):
        return "skill"
    if re.search(r"\brule:\b", content, re.I) or "always" in c or "never" in c or "must" in c:
        return "rule"
    if "see " in c or "@" in content or ".md)" in content:
        return "reference"
    return "instruction"


# ---------- 2. parse transcript ----------

def load_transcript(path):
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def assistant_text_segments(events):
    """All raw assistant text in order."""
    out = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message", {})
        content = msg.get("content", [])
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    out.append({"ts": e.get("timestamp"), "text": c.get("text", "")})
        elif isinstance(content, str):
            out.append({"ts": e.get("timestamp"), "text": content})
    return out


def tool_calls(events):
    out = []
    for e in events:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message", {})
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                out.append({
                    "ts": e.get("timestamp"),
                    "name": c.get("name"),
                    "input": c.get("input", {}),
                    "id": c.get("id"),
                })
    return out


COMMAND_NAME_RE = re.compile(r"<command-name>(.*?)</command-name>", re.DOTALL)
COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
LOCAL_COMMAND_STDOUT_RE = re.compile(r"<local-command-stdout>", re.DOTALL)
# The CLI writes these markers as the whole user message when a run is cancelled.
# Anchored so a prompt that merely quotes the marker still counts as typed text.
INTERRUPT_MARKER_RE = re.compile(r"^\[Request interrupted by user[^\]]*\]$")


def _user_message_text(event):
    """Flatten a user event's message content to plain text, or None.

    List content is the shape a pasted screenshot produces (an `image` item plus
    a `text` item), and it is a real prompt. Tool-result lists are the agent
    speaking back to itself, never a prompt, so they short-circuit to None
    rather than contributing their result text.
    """
    msg = event.get("message", {}) if isinstance(event.get("message"), dict) else {}
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if not isinstance(c, list):
        return None
    parts = []
    for item in c:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "tool_result":
            return None
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts)


def _is_local_command_stdout(event):
    if not isinstance(event, dict) or event.get("type") != "user":
        return False
    text = _user_message_text(event)
    return bool(text) and bool(LOCAL_COMMAND_STDOUT_RE.search(text))


def _real_user_prompt_text(event, next_event=None):
    """If this event is a real user prompt that should start a turn, return
    the prompt text. Otherwise return None.

    Mirrors first_real_user_prompt's classifier so turn boundaries and the
    "first prompt" extraction can never disagree on what counts as user-typed.

    `next_event` is what separates a local command from a skill or slash
    command: both arrive as the same `<command-name>` wrapper, and only a local
    command is followed by a `<local-command-stdout>` message. Local commands
    (`/model`, `/config`, …) change the harness, not the task, so they must not
    carve off a phantom turn with no assistant activity in it.
    """
    if event.get("type") != "user":
        return None
    if event.get("isMeta"):
        return None
    c = _user_message_text(event)
    if not isinstance(c, str):
        return None
    if LOCAL_COMMAND_STDOUT_RE.search(c):
        return None
    args_match = COMMAND_ARGS_RE.search(c)
    name_match = COMMAND_NAME_RE.search(c)
    if args_match or name_match:
        if _is_local_command_stdout(next_event):
            return None
        name = name_match.group(1).strip() if name_match else ""
        args = args_match.group(1).strip() if args_match else ""
        return f"{name} {args}".strip() or None
    if c.startswith("<local-command-caveat>"):
        return None
    c = c.strip()
    if not c or INTERRUPT_MARKER_RE.match(c):
        return None
    return c


def _real_user_prompts(events):
    """Yield (index, prompt_text) for every event the classifier accepts."""
    for i, e in enumerate(events):
        text = _real_user_prompt_text(e, events[i + 1] if i + 1 < len(events) else None)
        if text is not None:
            yield i, text


def count_real_user_prompts(events):
    """How many times the human actually spoke.

    The harness stores tool output as `user`-type events, so counting user
    events directly overstates this roughly tenfold. Routes through the same
    classifier as turn splitting so the two figures can never disagree.
    """
    return sum(1 for _ in _real_user_prompts(events))


def first_real_user_prompt(events):
    """Text of the first event `_real_user_prompt_text` accepts as a prompt.

    Skill and slash-command wrappers count (their name and args become the
    prompt text); local-command wrappers, tool results, meta events, interrupt
    markers and stdout wrappers do not.
    """
    for _, text in _real_user_prompts(events):
        return text
    return None


def split_into_turns(events, compaction_times=None):
    """Slice an event list into ordered turn descriptors.

    A turn starts at every real user prompt (per `_real_user_prompt_text`) and
    spans up to the event before the next real user prompt. Tool-result user
    messages, meta events, and `<local-command-caveat>` wrappers do NOT start
    turns. Slash-command wrappers (`<command-name>` + `<command-args>`) DO.

    `compaction_times` (ISO strings) adds one extra boundary per compaction, at
    the first event on or after it: what the model can see changes there even
    without a new prompt. Omitting them splits exactly as before.

    Events that precede the first real user prompt (e.g. summary headers, leading
    meta events) are absorbed into the first turn so the returned ranges
    partition the full event list with no gaps.

    Returns a list of dicts with keys:
      index, startEventIdx, endEventIdx (exclusive), userPrompt, startTime,
      endTime, afterCompaction
    """
    boundaries = []  # [event_idx, prompt_text, after_compaction]
    for i, text in _real_user_prompts(events):
        boundaries.append([i, text, False])

    if not boundaries:
        return []

    # First turn absorbs anything before the first real user prompt.
    if boundaries[0][0] != 0:
        boundaries[0][0] = 0

    by_idx = {b[0]: b for b in boundaries}
    for ts in compaction_times or []:
        idx = _first_event_index_at_or_after(events, ts)
        # A compaction landing before the first prompt or after the last event
        # carves off no turn of its own; the earlier one already covers it.
        if idx is None or idx <= boundaries[0][0]:
            continue
        if idx in by_idx:
            by_idx[idx][2] = True
            continue
        # The carved-off half belongs to whatever prompt was in flight. Taken by
        # max index, not list order: earlier compactions already appended out of
        # order behind the prompt boundaries.
        prior = max((b for b in boundaries if b[0] < idx), key=lambda b: b[0])
        entry = [idx, prior[1], True]
        boundaries.append(entry)
        by_idx[idx] = entry
    boundaries.sort(key=lambda b: b[0])

    turns = []
    for idx, (start, prompt, after_compaction) in enumerate(boundaries):
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(events)
        slice_ = events[start:end]
        ts = [e.get("timestamp") for e in slice_ if e.get("timestamp")]
        turns.append({
            "index": idx,
            "startEventIdx": start,
            "endEventIdx": end,
            "userPrompt": prompt,
            "startTime": ts[0] if ts else "",
            "endTime": ts[-1] if ts else "",
            "afterCompaction": after_compaction,
        })
    return turns


def compactions_from_transcript(events):
    """Compaction boundaries recorded in the transcript itself.

    Deliberately always empty: no compacted transcript was available to verify
    what a compaction entry looks like, and guessing a marker shape would ship
    code that passes its own synthetic test and never fires in reality. The
    ctxlog PreCompact/PostCompact records are the only verified source today.
    Fill this in once a real compacted transcript can be inspected.
    """
    return []


def _first_event_index_at_or_after(events, ts):
    """Index of the first event timestamped at or after `ts`, or None."""
    target = _as_utc(_parse_iso_safe(ts))
    if target is None:
        return None
    for i, e in enumerate(events):
        dt = _as_utc(_parse_iso_safe(e.get("timestamp")))
        if dt is not None and dt >= target:
            return i
    return None


def compute_residency(turns, compactions, hook_facts):
    """Work out which files stopped being resident in context, and when.

    Returns `(nonresident_by_turn, compaction_records)`:
      * `nonresident_by_turn` maps a turn index to the set of absolute paths
        that were not in context for that turn.
      * `compaction_records` is one dict per compaction (`ts`, `event`,
        `trigger`, `evicted`) for the timeline.

    At compaction, files loaded at session start are re-injected, so they stay
    resident. A file pulled in by a path glob match is not, and stays out until
    another InstructionsLoaded record names it. Anything the hook log never
    observed - and every session with no compaction records - is treated as
    resident: missing data must never remove a block from assessment.
    """
    comp_dts = sorted({d for d in (_as_utc(_parse_iso_safe(c.get("ts"))) for c in (compactions or [])) if d})
    if not comp_dts:
        return {}, []

    loads_by_path = {}
    for rec in (hook_facts or {}).get("instructions") or []:
        path, dt = rec.get("path"), _as_utc(_parse_iso_safe(rec.get("ts")))
        if path and dt:
            loads_by_path.setdefault(path, []).append((dt, rec.get("load_reason")))

    evicted_at = {dt: [] for dt in comp_dts}
    nonresident = {}
    for path, loads in loads_by_path.items():
        # A load sharing a timestamp with a compaction wins: it is the newer fact.
        merged = sorted([(dt, "load", reason) for dt, reason in loads]
                        + [(dt, "compact", None) for dt in comp_dts],
                        key=lambda x: (x[0], x[1] != "compact"))
        resident, last_reason, transitions = True, None, []
        for dt, kind, reason in merged:
            if kind == "load":
                resident, last_reason = True, reason
            elif resident and last_reason == "path_glob_match":
                resident = False
                evicted_at[dt].append(path)
            else:
                continue  # already gone, or re-injected wholesale
            transitions.append((dt, resident))

        for t in turns:
            tdt = _as_utc(_parse_iso_safe(t.get("startTime")))
            if tdt is None:
                continue
            resident = True
            for dt, state in transitions:
                if dt > tdt:
                    break
                resident = state
            if not resident:
                nonresident.setdefault(t["index"], set()).add(path)

    records = []
    for c in compactions or []:
        dt = _as_utc(_parse_iso_safe(c.get("ts")))
        # No usable timestamp means nowhere to place it on the timeline, and it
        # already contributed no eviction; showing it would be worse than not.
        if dt is None:
            continue
        records.append({
            "ts": c.get("ts"),
            "event": c.get("event"),
            "trigger": c.get("trigger"),
            "evicted": sorted(evicted_at.get(dt, [])),
        })
    return nonresident, records


def combine_verdicts(statuses):
    """Combine a block's per-turn statuses into a single 'All turns' status.

    Per PRD: "A block is 'used' at session scope if it is 'used' in any turn.
    A block is 'not used' only if it is 'not used' in every turn."

    The 7-status taxonomy used by `assess_block` partitions cleanly into:
      USED family    : 'used', 'used-partial', 'ignored', 'possibly-referenced'
      NOT-USED family: 'undelivered', 'unused', 'dormant', 'not-loaded'

    'ignored' takes precedence over 'used' because an ignored verdict is a
    rule violation — silently aggregating it into 'used' would hide signal
    the investigator came for. 'used' beats 'used-partial', which beats
    'possibly-referenced': the weak-evidence status is the least the block
    could have done, so any turn with real evidence outranks it. Within the
    NOT-USED family we prefer the most informative label that appears.

    Single-turn input passes through unchanged so single-turn sessions
    remain byte-identical to the pre-turn-aware build.
    """
    if not statuses:
        return "not-loaded"
    if len(statuses) == 1:
        return statuses[0]
    if "ignored" in statuses:
        return "ignored"
    if "used" in statuses:
        return "used"
    if "used-partial" in statuses:
        return "used-partial"
    if "possibly-referenced" in statuses:
        return "possibly-referenced"
    for fallback in ("undelivered", "unused", "dormant", "not-loaded"):
        if fallback in statuses:
            return fallback
    return statuses[0]


def turn_slice(events, calls, asst_segs, turn):
    """Return the (events, calls, asst_segs) bundle restricted to one turn.

    The returned tuple has the same shape as today's per-session inputs so
    every existing assessor can consume it unchanged.

    `calls` and `asst_segs` are re-derived from the sliced events list rather
    than filtered by event index — both functions are pure and cheap, and this
    avoids needing to plumb event indices through their outputs.
    """
    start, end = turn["startEventIdx"], turn["endEventIdx"]
    events_slice = events[start:end]
    calls_slice = tool_calls(events_slice)
    asst_slice = assistant_text_segments(events_slice)
    return events_slice, calls_slice, asst_slice


# ---------- 2b. token usage from message.usage ----------

# Below this much cached prefix there is nothing worth losing, so a cold start
# or a short warm-up must not be reported as a break.
CACHE_BREAK_MIN_PRIOR_READ = 5000
# The read has to actually collapse, not merely dip: a request that still reads
# most of the prefix kept its cache.
CACHE_BREAK_READ_RATIO = 0.2
# ...and the prefix has to be visibly repaid as fresh writes, which is what
# separates a broken cache from a request that simply sent very little.
CACHE_BREAK_CREATION_RATIO = 0.5


def _usage_int(d, key):
    """A usage counter as an int, defaulting to 0 for anything unexpected."""
    v = d.get(key)
    return int(v) if isinstance(v, (int, float)) else 0


def usage_series(events):
    """Per-request token usage, in transcript order.

    One entry per API request, not per assistant event: the harness writes a
    single response as several assistant events that share a `message.id` and
    repeat the same usage object verbatim (165 events / 83 requests on a real
    transcript), so summing events would roughly double every figure. The first
    event of a request wins; later ones are dropped. An event with no id keeps
    its own entry - there is nothing to dedupe it against, and dropping it would
    lose real tokens.

    Each entry carries the index of the event it came from, which is what lets
    a turn take its share of the series by event range instead of re-deriving a
    series per slice - a request whose events straddle a turn boundary would
    otherwise be counted in both turns.

    Missing or malformed usage yields zeros rather than an omission, so the
    series stays aligned with the requests the model actually made.
    """
    out = []
    seen_ids = set()
    for idx, e in enumerate(events):
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        req_id = msg.get("id")
        if req_id:
            if req_id in seen_ids:
                continue
            seen_ids.add(req_id)
        u = msg.get("usage") or {}
        creation = u.get("cache_creation") or {}
        details = u.get("output_tokens_details") or {}
        out.append({
            "ts": e.get("timestamp"),
            "eventIndex": idx,
            "requestId": req_id,
            "input": _usage_int(u, "input_tokens"),
            "output": _usage_int(u, "output_tokens"),
            "cacheRead": _usage_int(u, "cache_read_input_tokens"),
            "cacheCreation": _usage_int(u, "cache_creation_input_tokens"),
            "cacheCreation1h": _usage_int(creation, "ephemeral_1h_input_tokens"),
            "cacheCreation5m": _usage_int(creation, "ephemeral_5m_input_tokens"),
            "thinking": _usage_int(details, "thinking_tokens"),
        })
    return out


def usage_totals(series):
    """Sum a usage series into the headline figures.

    `promptTokens` is the honest "what this session sent" number: fresh input
    plus cache reads plus cache writes. Output and thinking are reported
    separately because they are generated, not sent.
    """
    totals = {
        "requests": len(series),
        "inputTokens": sum(e["input"] for e in series),
        "outputTokens": sum(e["output"] for e in series),
        "cacheReadTokens": sum(e["cacheRead"] for e in series),
        "cacheCreationTokens": sum(e["cacheCreation"] for e in series),
        "cacheCreation1hTokens": sum(e["cacheCreation1h"] for e in series),
        "cacheCreation5mTokens": sum(e["cacheCreation5m"] for e in series),
        "thinkingTokens": sum(e["thinking"] for e in series),
    }
    totals["promptTokens"] = (totals["inputTokens"] + totals["cacheReadTokens"]
                              + totals["cacheCreationTokens"])
    return totals


def usage_for_turn(series, turn):
    """The session's usage entries belonging to one turn.

    Sliced out of the one session-wide series by event range, so every request
    is counted in exactly one turn and per-turn totals always sum back to the
    session totals.
    """
    start, end = turn["startEventIdx"], turn["endEventIdx"]
    return [e for e in series if start <= e["eventIndex"] < end]


def cache_breaks(series):
    """Requests where the prompt cache was lost and the prefix repaid.

    The signature is a cache read that collapses against the previous request's
    read while cache creation spikes to roughly the size of the prefix that was
    being read. Compared against the previous request only: a break is a
    transition, and comparing against a running maximum would keep re-reporting
    the same one on every later request.

    Detection is a heuristic over reported numbers, not a recorded event - the
    transcript carries no cache-invalidation marker - so the thresholds are
    deliberately conservative and the marker says what it inferred.
    """
    out = []
    for i in range(1, len(series)):
        prev, cur = series[i - 1], series[i]
        prior = prev["cacheRead"]
        if prior < CACHE_BREAK_MIN_PRIOR_READ:
            continue
        if cur["cacheRead"] > prior * CACHE_BREAK_READ_RATIO:
            continue
        if cur["cacheCreation"] < prior * CACHE_BREAK_CREATION_RATIO:
            continue
        out.append({
            "ts": cur["ts"],
            "eventIndex": cur["eventIndex"],
            "priorCacheRead": prior,
            "cacheRead": cur["cacheRead"],
            "cacheCreation": cur["cacheCreation"],
        })
    return out


# ---------- 2c. token attribution across context items ----------

def _largest_remainder(weights, total):
    """Split `total` into integer parts proportional to `weights`.

    Floors every share, then hands the leftover units to the largest fractional
    parts. The parts always sum back to `total` exactly: attribution that
    reconciles with the API's own figures is the whole point of this phase, and
    a rounding drift of a few tokens per request would compound over thousands
    of requests into a number nobody can check.
    """
    denom = sum(weights)
    if total <= 0 or denom <= 0:
        return [0] * len(weights)
    exact = [total * w / denom for w in weights]
    parts = [int(x) for x in exact]
    leftover = total - sum(parts)
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - parts[i]), i))
    for i in order[:leftover]:
        parts[i] += 1
    return parts


def attribute_request(items, total_tokens, history_chars=0):
    """Split one request's reported prompt tokens across the context it carried.

    `items` is a sequence of `(key, chars)` for the items resident in this
    request. `history_chars` sizes a remainder bucket standing for the
    conversation itself. Without that bucket every token the chat log costs
    would be charged to the instruction files, and a long session would price a
    20-line rule at tens of thousands of tokens.

    Character size is the only proxy available for an item's share - the API
    reports one number for the whole prompt - so the split is proportional by
    size. The total being split is ground truth; only the division is estimated.

    Returns `(per_item, history)`, which together sum to `total_tokens`.
    """
    keys = [k for k, _ in items]
    weights = [max(int(c), 0) for _, c in items] + [max(int(history_chars), 0)]
    total = max(int(total_tokens), 0)
    # Nothing measurable was resident, so whatever the request sent was
    # conversation. Charging it to zero-size items would be arbitrary.
    if sum(weights) <= 0:
        return {k: 0 for k in keys}, total
    parts = _largest_remainder(weights, total)
    return dict(zip(keys, parts)), parts[-1]


def attribute_usage(items, entries, nonresident_by_request=None, history_chars=None):
    """Roll per-request attribution up into a cumulative cost per item.

    `entries` is a usage series (see `usage_series`); every request it contains
    resends the whole resident context, which is what turns a small file into a
    large bill. `nonresident_by_request` maps a request's event index to the
    keys that were not in context for it, so a file evicted by a compaction
    stops accruing from that request onward. `history_chars` maps a request's
    event index to the size of the conversation prefix at that point.

    The cached/fresh split is taken from the request's own figures rather than
    guessed per file: a resident file sits in the same prefix as everything
    else, so it was cached in exactly the proportion the request reports.

    Returns `{"requests", "attributedTokens", "files": {key: {...}}, "history"}`.
    """
    nonresident_by_request = nonresident_by_request or {}
    history_chars = history_chars or {}
    files = {k: {"sentCount": 0, "tokens": 0, "cached": 0, "fresh": 0} for k, _ in items}
    history = {"tokens": 0, "cached": 0, "fresh": 0}

    for e in entries:
        prompt = e["input"] + e["cacheRead"] + e["cacheCreation"]
        idx = e.get("eventIndex")
        gone = nonresident_by_request.get(idx) or ()
        resident = [(k, c) for k, c in items if k not in gone]
        per_item, hist = attribute_request(resident, prompt, history_chars.get(idx, 0))
        cache_read = e["cacheRead"]
        for k, _ in resident:
            files[k]["sentCount"] += 1
        for bucket, tokens in [(files[k], per_item[k]) for k, _ in resident] + [(history, hist)]:
            cached = (tokens * cache_read) // prompt if prompt else 0
            bucket["tokens"] += tokens
            bucket["cached"] += cached
            bucket["fresh"] += tokens - cached

    attributed = sum(f["tokens"] for f in files.values()) + history["tokens"]
    return {
        "requests": len(entries),
        "attributedTokens": attributed,
        "files": files,
        "history": history,
    }


def block_costs(file_cost, blocks):
    """Per-block share of a file's attributed cost, by line count.

    Line share is the crudest possible split - a block's lines say nothing
    about their token density - so every figure returned carries
    `estimated: True` and the UI must label it. Only the file-level number is
    defensible; this exists so a reader can rank blocks within one file.
    """
    weights = [len((b.get("content") or "").splitlines()) or 1 for b in blocks]
    parts = _largest_remainder(weights, file_cost.get("tokens", 0))
    return [{"tokens": p, "estimated": True} for p in parts]


def _event_chars(event):
    """Rough character size of one transcript event's message content."""
    content = (event.get("message") or {}).get("content")
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    try:
        return len(json.dumps(content))
    except Exception:
        return len(str(content))


def history_chars_by_request(events, series):
    """Size of the conversation prefix at each request, keyed by event index.

    Counts every event before the request, instruction attachments included:
    the bucket only has to stop the files from absorbing the conversation's
    growth, and being exact about which prefix bytes are "history" would need
    the prompt the API actually received, which the transcript does not carry.
    """
    out = {}
    wanted = {e["eventIndex"] for e in series}
    running = 0
    for idx, e in enumerate(events):
        if idx in wanted:
            out[idx] = running
        running += _event_chars(e)
    return out


def _nonresident_by_request(series, turns, nonresident_by_turn):
    """Lift per-turn non-residency onto the requests inside each turn.

    Matched by event index, never by timestamp - adjacent events can share a
    millisecond, which would place one request in two turns.
    """
    if not nonresident_by_turn:
        return {}
    out = {}
    for t in turns:
        gone = nonresident_by_turn.get(t["index"])
        if not gone:
            continue
        for e in series:
            if t["startEventIdx"] <= e["eventIndex"] < t["endEventIdx"]:
                out[e["eventIndex"]] = gone
    return out


# ---------- 3. context-file loading ----------

REF_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_./-]+\.md)\b")

# The Read tool returns the first 2000 lines when no explicit limit is passed.
READ_DEFAULT_LINE_CAP = 2000


def _merge_intervals(intervals):
    """Sorted, non-overlapping (start, end) pairs. Adjacent runs are joined."""
    out = []
    for s, e in sorted(intervals):
        if e < s:
            continue
        if out and s <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _delivery_range(abs_path, content, kind, source, read_ranges=None):
    """How much of a context file actually reached the model.

    Returns total_lines / delivered_from / delivered_to / delivered_ranges /
    delivery. Never guesses a shortfall: anything that can't be established from
    disk plus the recorded call arguments comes back as "unknown", which
    downstream treats as full.

    `delivered_ranges` is the authoritative field, and delivered_from/_to are
    only its outer bounds: two disjoint reads of one file (lines 1-100 and
    1900-2000) span everything in between without having delivered any of it,
    so collapsing them to a single min-to-max span scored the unread middle as
    though the model had seen it.
    """
    unknown = {"total_lines": None, "delivered_from": 1, "delivered_to": None,
               "delivered_ranges": [], "delivery": "unknown"}
    try:
        total_lines = len(Path(abs_path).read_text(errors="replace").splitlines())
    except Exception:
        return unknown
    full = {"total_lines": total_lines, "delivered_from": 1,
            "delivered_to": total_lines, "delivered_ranges": [(1, total_lines)],
            "delivery": "full"}

    if source == "transcript":
        # The attachment content *is* what the harness handed the model.
        got = len((content or "").splitlines())
        if got < total_lines:
            return {"total_lines": total_lines, "delivered_from": 1,
                    "delivered_to": got, "delivered_ranges": [(1, got)],
                    "delivery": "truncated"}
        return full

    if kind == "read":
        intervals, hit_cap = [], False
        for off, lim in (read_ranges or [(None, None)]):
            if off is None and lim is None:
                intervals.append((1, min(READ_DEFAULT_LINE_CAP, total_lines)))
                hit_cap = hit_cap or total_lines > READ_DEFAULT_LINE_CAP
            else:
                s = max(1, int(off or 1))
                e = (s + int(lim) - 1) if lim else total_lines
                intervals.append((s, min(e, total_lines)))
        merged = _merge_intervals(intervals)
        # Every recorded offset sat past the end of the file as it is on disk
        # now, so the file changed since the read and the arguments no longer
        # describe anything. That is exactly the "can't be established" case.
        if not merged:
            return unknown
        if len(merged) == 1 and merged[0][0] <= 1 and merged[0][1] >= total_lines:
            return full
        return {"total_lines": total_lines,
                "delivered_from": merged[0][0],
                "delivered_to": merged[-1][1],
                "delivered_ranges": merged,
                "delivery": "truncated" if hit_cap else "partial-by-request"}

    # Instruction files injected by the harness bypass the Read tool's line cap.
    return full

# A listing line is "- <name>: <description>", and a plugin skill's name carries
# its own colon ("datadog:ddsetup"). Only a colon *followed by whitespace* ends
# the name, so the prefix survives; the description part is optional because
# some listed skills carry no description at all.
SKILL_LISTING_RE = re.compile(r"^-\s+([A-Za-z0-9][\w:.-]*?)(?::\s+(.*))?$")
HOOK_PATH_RE = re.compile(r"\b([A-Za-z0-9_][\w./-]*\.md)\b")


def extract_attachments(events):
    """Walk transcript events and pull out context-loading metadata recorded by the harness.

    Returns:
      {
        "nested_memories":      [{path, content, differs_from_disk, type}],
        "hook_directives":      [str, ...],
        "skill_listing":        [{name, description}, ...]   # empty if attachment absent
        "skill_listing_present": bool,
        "skill_count":          int | None,
        "preloaded_files":      [{path, content}],
        "user_attached_files":  [{path, content}],
      }
    """
    out = {
        "nested_memories": [],
        "hook_directives": [],
        "skill_listing": [],
        "skill_listing_present": False,
        "skill_count": None,
        "preloaded_files": [],
        "user_attached_files": [],
    }
    for e in events:
        if e.get("type") != "attachment":
            continue
        a = e.get("attachment") or {}
        atype = a.get("type")

        if atype == "nested_memory":
            c = a.get("content") or {}
            if isinstance(c, dict) and c.get("path") and c.get("content") is not None:
                out["nested_memories"].append({
                    "path": c["path"],
                    "content": c["content"],
                    "differs_from_disk": bool(c.get("contentDiffersFromDisk")),
                    "type": c.get("type") or "",
                })

        elif atype == "hook_additional_context":
            c = a.get("content")
            if isinstance(c, list):
                out["hook_directives"].extend(str(x) for x in c)
            elif isinstance(c, str):
                out["hook_directives"].append(c)

        elif atype == "skill_listing":
            out["skill_listing_present"] = True
            out["skill_count"] = a.get("skillCount")
            text = a.get("content") or ""
            if isinstance(text, str):
                for line in text.splitlines():
                    m = SKILL_LISTING_RE.match(line.strip())
                    if m:
                        out["skill_listing"].append({
                            "name": m.group(1),
                            "description": (m.group(2) or "").strip(),
                        })

        elif atype in ("already_read_file", "file"):
            c = a.get("content") or {}
            f = c.get("file") if isinstance(c, dict) else None
            if isinstance(f, dict) and f.get("filePath") and f.get("content") is not None:
                entry = {"path": f["filePath"], "content": f["content"]}
                if atype == "file":
                    out["user_attached_files"].append(entry)
                else:
                    out["preloaded_files"].append(entry)
    return out


def hook_directive_paths(hook_directives, project_dir):
    """Extract candidate .md filenames from SessionStart hook directives.
    Resolve relative to project_dir; return absolute Paths that exist on disk."""
    out = []
    seen = set()
    proj = Path(project_dir) if project_dir else None
    for line in hook_directives:
        for m in HOOK_PATH_RE.finditer(line):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            # Try absolute, then relative to project_dir, then relative to home
            candidates = []
            p = Path(name)
            if p.is_absolute():
                candidates.append(p)
            else:
                if proj:
                    candidates.append(proj / p)
                candidates.append(Path.home() / p)
            for c in candidates:
                if c.exists() and c.suffix == ".md":
                    out.append(c.resolve())
                    break
    return out


def _display_path(p):
    """Pretty path: ~/... if under HOME, else absolute."""
    s = str(p)
    home = str(Path.home())
    if s.startswith(home):
        return "~" + s[len(home):]
    return s


def _short_path(p, project_dir=None):
    """Project-relative path when it sits under the project, else _display_path."""
    if not p:
        return None
    if project_dir:
        try:
            return str(Path(p).relative_to(Path(project_dir)))
        except ValueError:
            pass
    return _display_path(p)


def _collect_md_units(base_dir):
    """Find skill/command/agent units under a directory.
    Returns list of (name, path) where path is either <name>.md or <name>/SKILL.md.
    """
    units = []
    if not base_dir or not Path(base_dir).is_dir():
        return units
    base = Path(base_dir)
    for entry in sorted(base.iterdir()):
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                units.append((entry.name, skill_md))
        elif entry.is_file() and entry.suffix == ".md":
            units.append((entry.stem, entry))
    return units


def _subagent_types_used(calls):
    """Set of subagent_type values seen in Agent tool calls."""
    out = set()
    for c in calls:
        if c["name"] == "Agent":
            t = c["input"].get("subagent_type")
            if t:
                out.add(t)
    return out


def _is_triggered(name, user_prompt):
    """Did the prompt type `/name` as a token of its own?

    Bounded on both sides: without the lookahead `/cp` matched `/cpanel`, and
    without the lookbehind any path ending in the name (`~/.claude/skills/cp`)
    counted as an invocation. A bare first word is no longer accepted at all -
    "commit the change" is a request, not an invocation of the `commit` skill.
    """
    if not user_prompt or not name:
        return False
    pattern = r"(?<![\w./:-])/" + re.escape(name) + r"(?![\w:-])"
    return re.search(pattern, user_prompt, re.I) is not None


def _skill_tool_names(calls):
    """Names the model passed to the `Skill` tool, lowercased.

    A Skill call is the strongest loading evidence there is: the skill really
    was pulled into context, whatever the prompt happened to say.
    """
    out = set()
    for c in calls:
        if c["name"] != "Skill":
            continue
        s = (c["input"].get("skill") or "").strip().lstrip("/").lower()
        if s:
            out.add(s)
    return out


def _command_wrapper_names(events):
    """Names of slash commands the user typed, lowercased.

    Mirrors chronological_segments' command-wrapper detection; kept separate so
    the context loader does not have to build the whole segment list.
    """
    out = set()
    for e in events:
        if e.get("type") != "user" or e.get("isMeta"):
            continue
        text = _user_message_text(e)
        if not isinstance(text, str):
            continue
        for m in COMMAND_NAME_RE.finditer(text):
            n = m.group(1).strip().lstrip("/").lower()
            if n:
                out.add(n)
    return out


def _is_loaded(name, user_prompt, skill_call_names=(), wrapper_names=()):
    """Loading evidence in descending strength: the model invoked the skill,
    the user typed it as a slash command, or the prompt mentions `/name`.

    The prompt is the weakest and last source on purpose - it is a guess about
    intent, while the other two are records of what happened.
    """
    n = (name or "").lower()
    if not n:
        return False
    if n in skill_call_names or n in wrapper_names:
        return True
    return _is_triggered(n, user_prompt)


DEFAULT_PLUGIN_CACHE_DIR = Path.home() / ".claude" / "plugins" / "cache"


def _resolve_plugin_skill(name, cache_dir=None):
    """Locate a `plugin:skill` listing entry's SKILL.md under the plugin cache.

    Layout is <cache>/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md.
    Several versions of one plugin sit side by side, and their directory names
    are sometimes commit hashes rather than semver, so the newest mtime decides
    instead of any attempt to order the version strings.
    """
    plugin, sep, skill = (name or "").partition(":")
    if not sep or not plugin or not skill:
        return None
    root = Path(cache_dir) if cache_dir else DEFAULT_PLUGIN_CACHE_DIR
    if not root.is_dir():
        return None
    candidates = []
    for pattern in (f"*/{plugin}/*/skills/{skill}/SKILL.md",
                    f"*/{plugin}/*/skills/{skill}.md"):
        candidates.extend(p for p in root.glob(pattern) if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _resolve_at_refs(blocks, search_roots):
    """Find @path references in block content; resolve to existing .md files."""
    refs = set()
    for b in blocks:
        for m in REF_RE.finditer(b["content"]):
            refs.add(m.group(1))
    resolved = []
    for ref in refs:
        for root in search_roots:
            candidate = (Path(root) / ref).resolve()
            if candidate.exists() and candidate.suffix == ".md":
                resolved.append(candidate)
                break
    return resolved


def load_context_files(events, calls, project_dir, args, user_prompt, hook_facts=None):
    """Transcript-first loader. Use harness-recorded attachments where present;
    fall back to filesystem path conventions otherwise.

    `hook_facts` is the ctxlog log for this session (None when the session
    predates the hooks). Where it names a file, it is ground truth and beats
    the path convention; where it is silent, the convention stands - except for
    .claude/rules/*.md, the one source whose whole point is conditional loading.

    Sources merged here (deduped by absolute path):
      - global ~/.claude/CLAUDE.md, ~/.claude/AGENTS.md
      - nested_memory attachments (project CLAUDE.md including sub-directory ones)
      - <cwd>/CLAUDE.md, <cwd>/AGENTS.md, <cwd>/AGENTS.override.md
      - hook_directive .md paths
      - <cwd>/.claude/rules/*.md
      - skills (skill_listing if present, else path-conventions)
      - commands (path-conventions; commands aren't surfaced in attachments distinctly)
      - subagents (path-conventions)
      - already_read_file / file (preloaded with content)
      - @-references from any project/global file
      - Read tool calls for .md files (kind=read, dynamic mid-session)
    """
    home = Path.home()
    proj = Path(project_dir) if project_dir else None
    proj_claude_dir = (proj / ".claude") if proj else None
    subagents_used = _subagent_types_used(calls)
    attach = extract_attachments(events)

    hook_loads = ctxlog_facts.latest_by_path(hook_facts)
    # An empty log proves nothing about what was loaded, so only a log that
    # actually recorded instruction loads may be read as "and nothing else".
    hook_evidence = hook_facts is not None and bool(hook_loads)

    def hook_fact(path):
        if not hook_loads:
            return None
        try:
            key = str(Path(path).resolve())
        except Exception:
            key = str(path)
        return hook_loads.get(key)

    files = []
    seen_paths = set()  # by abs_path string

    def add_file(*, path=None, abs_path=None, kind, loaded, content=None,
                 source="disk", drift=False, read_ranges=None, hook=None, **extra):
        """Append a context file record. If content is provided, use it as-is
        (transcript-derived); otherwise read from disk."""
        # Resolve abs_path if not given
        if abs_path is None and path is not None:
            try:
                abs_path = str(Path(path).resolve())
            except Exception:
                abs_path = str(path)
        if not abs_path:
            return
        if abs_path in seen_paths:
            return
        if content is None:
            p = Path(abs_path)
            if not p.exists():
                return
            try:
                content = p.read_text(errors="replace")
            except Exception:
                return
        # If content is provided but disk also exists and differs, mark drift
        actual_drift = drift
        if content is not None and source == "transcript":
            try:
                disk_text = Path(abs_path).read_text(errors="replace")
                if disk_text != content:
                    actual_drift = True
            except Exception:
                pass
        delivery = _delivery_range(abs_path, content, kind, source, read_ranges)
        blocks_text = content
        if delivery["delivery"] == "truncated" and source == "transcript":
            # The attachment is a prefix of the file. Parse the on-disk text instead
            # so the withheld headings still appear as blocks (flagged `undelivered`)
            # rather than vanishing from the panel as if they never existed.
            try:
                blocks_text = Path(abs_path).read_text(errors="replace")
            except Exception:
                blocks_text = content
        seen_paths.add(abs_path)
        files.append({
            "path": _display_path(abs_path),
            "abs_path": abs_path,
            "kind": kind,
            "loaded": loaded,
            "source": source,
            "drift": actual_drift,
            # Size of what was actually delivered, which is what token
            # attribution divides by. Not derivable from `blocks`: a file with
            # no H1/H2 heading parses to zero blocks and would price as free.
            "chars": len(content or ""),
            "blocks": parse_claude_md(blocks_text),
            **delivery,
            **extra,
            # Key omitted entirely when there is no fact, so hookless sessions
            # serialise exactly as they did before.
            **({"hook": hook} if hook else {}),
        })

    # ===== Global instructions =====
    for fn in ("CLAUDE.md", "AGENTS.md"):
        p = home / ".claude" / fn
        add_file(path=p, kind="global", loaded=True, source="disk", hook=hook_fact(p))

    # ===== Project instructions =====
    # 1. nested_memory attachments — authoritative content
    for nm in attach["nested_memories"]:
        # Only count as "project" kind if path lives under project_dir
        is_project = bool(proj) and str(nm["path"]).startswith(str(proj))
        if is_project:
            kind = "project"
        else:
            # Could be parent-dir CLAUDE.md or reference outside cwd; tag as global
            kind = "global"
        add_file(
            abs_path=str(Path(nm["path"]).resolve()),
            kind=kind,
            loaded=True,
            content=nm["content"],
            source="transcript",
            drift=nm["differs_from_disk"],
            # This site claims the path before the convention loop below, so the
            # fact has to be attached here or it is lost to the dedupe.
            hook=hook_fact(nm["path"]),
        )

    # 2. ./CLAUDE.md, ./AGENTS.md, ./AGENTS.override.md (path-convention)
    if proj:
        for fn in ("CLAUDE.md", "AGENTS.md", "AGENTS.override.md"):
            p = proj / fn
            add_file(path=p, kind="project", loaded=True, source="disk", hook=hook_fact(p))

    # 3. Hook-directive paths (e.g., "Read AGENTS.md ...")
    for hp in hook_directive_paths(attach["hook_directives"], project_dir):
        is_project = bool(proj) and str(hp).startswith(str(proj))
        add_file(abs_path=str(hp), kind="project" if is_project else "global",
                 loaded=True, source="hook")

    # ===== Project rules =====
    if proj_claude_dir and (proj_claude_dir / "rules").is_dir():
        for md in sorted((proj_claude_dir / "rules").glob("*.md")):
            hf = hook_fact(md)
            # Rules load conditionally (path globs). With a log to check against,
            # a rule the harness never reported loading really was not loaded.
            loaded = bool(hf) if hook_evidence else True
            add_file(path=md, kind="rule", loaded=loaded, source="disk", hook=hf)

    # ===== Skills =====
    skill_call_names = _skill_tool_names(calls)
    wrapper_names = _command_wrapper_names(events)
    if attach["skill_listing_present"]:
        # Authoritative: only show skills the harness listed.
        for entry in attach["skill_listing"]:
            name = entry["name"]
            md_path = None
            for cand in (
                home / ".claude" / "skills" / name / "SKILL.md",
                home / ".claude" / "skills" / f"{name}.md",
                (proj_claude_dir / "skills" / name / "SKILL.md") if proj_claude_dir else None,
                (proj_claude_dir / "skills" / f"{name}.md") if proj_claude_dir else None,
            ):
                if cand and cand.exists():
                    md_path = cand
                    break
            if md_path is None:
                md_path = _resolve_plugin_skill(name)
            scope = "global" if (md_path and str(md_path).startswith(str(home))) else "project"
            triggered = _is_loaded(name, user_prompt, skill_call_names, wrapper_names)
            if md_path:
                add_file(path=md_path, kind="skill", loaded=triggered,
                         name=name, scope=scope, source="listing")
            else:
                # Listing-only phantom (file moved or unresolved) — show description as content
                phantom = (f"# {name}\n\n{entry['description']}\n\n"
                           "_(This skill was listed by the harness but its source file could not be located on disk.)_")
                phantom_path = f"<listing-only:{name}>"
                if phantom_path not in seen_paths:
                    seen_paths.add(phantom_path)
                    files.append({
                        "path": f"(listing-only) {name}",
                        "abs_path": phantom_path,
                        "kind": "skill",
                        "loaded": triggered,
                        "source": "listing-only",
                        "drift": False,
                        "name": name,
                        "scope": "global",
                        # What the listing put in context is one line, not a
                        # file; sizing it by the phantom text keeps it in the
                        # same units as every other item, and small either way.
                        "chars": len(phantom),
                        "blocks": parse_claude_md(phantom),
                    })
    else:
        # Fallback: glob filesystem
        skill_bases = []
        if args.skills_dir and Path(args.skills_dir).is_dir():
            skill_bases.append(("global", Path(args.skills_dir)))
        if proj_claude_dir and (proj_claude_dir / "skills").is_dir():
            skill_bases.append(("project", proj_claude_dir / "skills"))
        for scope, base in skill_bases:
            for name, md in _collect_md_units(base):
                add_file(path=md, kind="skill",
                         loaded=_is_loaded(name, user_prompt, skill_call_names, wrapper_names),
                         name=name, scope=scope, source="disk")

    # ===== Commands (path-conventions) =====
    cmd_dirs = [("global", home / ".claude" / "commands")]
    if proj_claude_dir:
        cmd_dirs.append(("project", proj_claude_dir / "commands"))
    for scope, base in cmd_dirs:
        if base.is_dir():
            for md in sorted(base.glob("*.md")):
                name = md.stem
                add_file(path=md, kind="command",
                         loaded=_is_loaded(name, user_prompt, skill_call_names, wrapper_names),
                         name=name, scope=scope, source="disk")

    # ===== Subagents (path-conventions) =====
    agent_dirs = [("global", home / ".claude" / "agents")]
    if proj_claude_dir:
        agent_dirs.append(("project", proj_claude_dir / "agents"))
    for scope, base in agent_dirs:
        if base.is_dir():
            for md in sorted(base.glob("*.md")):
                name = md.stem
                add_file(path=md, kind="agent", loaded=name in subagents_used,
                         name=name, scope=scope, source="disk")

    # ===== Pre-loaded files (already_read_file + user-attached file) =====
    for entry in attach["preloaded_files"]:
        add_file(abs_path=str(Path(entry["path"]).resolve()),
                 kind="preloaded", loaded=True, content=entry["content"],
                 source="transcript")
    for entry in attach["user_attached_files"]:
        add_file(abs_path=str(Path(entry["path"]).resolve()),
                 kind="attached", loaded=True, content=entry["content"],
                 source="transcript")

    # ===== Read tool calls — dynamic mid-session reads of .md files =====
    read_paths = []
    read_ranges_by_path = {}
    for c in calls:
        if c.get("name") != "Read":
            continue
        inp = c.get("input") or {}
        fp = inp.get("file_path")
        if not fp or not str(fp).endswith(".md"):
            continue
        try:
            ap = str(Path(fp).resolve())
        except Exception:
            ap = str(fp)
        if ap not in read_ranges_by_path:
            read_ranges_by_path[ap] = []
            read_paths.append(ap)
        # Repeat reads of the same file each deliver their own slice; the union
        # is what the model ended up holding.
        read_ranges_by_path[ap].append((inp.get("offset"), inp.get("limit")))

    for ap in read_paths:
        if ap in seen_paths:
            continue  # already shown under another kind; skip duplicate row
        if not Path(ap).exists():
            continue
        add_file(abs_path=ap, kind="read", loaded=True, source="disk",
                 read_ranges=read_ranges_by_path[ap])

    # ===== @-references from any project/global file (one hop) =====
    for f in list(files):
        if f["kind"] not in ("global", "project"):
            continue
        roots = [Path(f["abs_path"]).parent] if Path(f["abs_path"]).is_absolute() else []
        if proj:
            roots.append(proj)
        for ref_path in _resolve_at_refs(f["blocks"], roots):
            if str(ref_path) in seen_paths:
                continue
            add_file(abs_path=str(ref_path), kind="reference", loaded=True,
                     source="disk", referenced_by=f["path"])

    return files


# ---------- 4. predicate-based block assessment ----------

CODE_EXT = re.compile(r"\.(?:ts|tsx|js|jsx|py|md|go|rs|rb|java|css|html|json|sh)\b")
SUMMARY_KEYWORDS = ("summary", "files changed", "what changed", "in summary", "to recap")


def _extract_backtick_tokens(text):
    """Return tokens inside backticks that look like commands or command fragments."""
    out = []
    for m in re.finditer(r"`([^`]+)`", text):
        token = m.group(1).strip()
        if not token:
            continue
        out.append(token)
    return out


def derive_predicates(block):
    """Inspect block content and return a list of predicate dicts.

    Each predicate has:
      kind: descriptive name
      strength: "strong" or "weak" (see below)
      applicable(trace) -> bool   (was the rule's precondition met this run?)
      matches(trace) -> bool      (did the agent's behavior follow the rule?)
      label: short label for evidence cards
      describe(trace) -> str      (human-readable evidence text)

    `strength` tiers the evidence. A strong predicate ties the block to a
    specific observable outcome - the command it names was typed, the cwd row
    it selects also ran its command, the response shape it demands appeared,
    the thing it forbids did or did not happen - so it can carry the full
    verdict range. A weak predicate only observes that something the block
    happens to name occurred, with no causal link back to the block: a
    command-mention `matches` unconditionally, so before tiering, any block
    naming a command that ran anywhere in the session scored `used`. Weak
    evidence is capped at `possibly-referenced` by `assess_block`.
    """
    content = block["content"]
    title = block["title"]
    title_l = title.lower()
    content_l = content.lower()
    predicates = []

    # ----- trigger phrase: "Trigger: /foo" or "When the user types `/foo`"
    trigger_cmds = set()
    for m in re.finditer(r"trigger:\s*`?(/[a-z][\w-]*)`?", content, re.I):
        trigger_cmds.add(m.group(1).lower())
    for m in re.finditer(r"types\s+`(/[a-z][\w-]*)`", content, re.I):
        trigger_cmds.add(m.group(1).lower())
    for cmd in trigger_cmds:
        predicates.append({
            "kind": "trigger",
            "strength": "strong",
            "cmd": cmd,
            "label": f"trigger {cmd}",
            "applicable": (lambda t, c=cmd: bool(t["user_prompt"]) and c in t["user_prompt"].lower()),
            "matches":    (lambda t, c=cmd: bool(t["user_prompt"]) and c in t["user_prompt"].lower()),
            "describe":   (lambda t, c=cmd: f"User prompt: `{(t['user_prompt'] or '')[:100]}` — "
                                            + ("contains" if (t["user_prompt"] and c in t["user_prompt"].lower()) else "does not contain")
                                            + f" `{c}`"),
        })

    # ----- path table: cwd-conditional rules
    # Detect markdown tables that look like the project-routing pattern.
    if re.search(r"\|\s*Project path contains\s*\|", content, re.I) or re.search(r"project path contains", content_l):
        # parse table rows
        rows = []
        for line in content.splitlines():
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) >= 3 and not all(set(c) <= set("-: ") for c in cols):
                rows.append(cols)
        # drop header + separator
        data_rows = []
        for cols in rows:
            joined = " ".join(cols).lower()
            if "project path contains" in joined or "required" in joined or "switch command" in joined:
                continue
            # extract path-token from first col (between backticks if present)
            m = re.search(r"`([^`]+)`", cols[0])
            path_token = m.group(1) if m else cols[0]
            # extract a shell command from any cell
            cmd = ""
            for c in cols:
                cm = re.search(r"`([^`]+)`", c)
                if cm and any(s in cm.group(1) for s in [" ", "-"]):
                    cmd = cm.group(1)
                    break
            data_rows.append({"path_token": path_token, "cmd": cmd})

        if data_rows:
            tokens = [r["path_token"] for r in data_rows]
            cmds = [r["cmd"] for r in data_rows if r["cmd"]]
            predicates.append({
                "kind": "path-table",
                "strength": "strong",
                "label": "cwd vs path table",
                "applicable": (lambda t, toks=tokens: any(tok and tok in t["cwd"] for tok in toks)),
                "matches":    (lambda t, cs=cmds: any(c and any(c in bc for bc in t["bash_cmds"]) for c in cs)),
                "describe":   (lambda t, toks=tokens, cs=cmds:
                               f"cwd `{t['cwd']}` matches: " +
                               (", ".join(tk for tk in toks if tk and tk in t["cwd"]) or "(none)") +
                               f"; matching commands ran: " +
                               (", ".join(c for c in cs if any(c in bc for bc in t["bash_cmds"])) or "(none)")),
            })

    # ----- command mention: backtick'd command tokens, or known shell commands in prose
    cmd_tokens = set()
    for tok in _extract_backtick_tokens(content):
        # only care about things that look like commands (single word, lowercase, no slashes-leading)
        first = tok.split()[0]
        if first.startswith("/"):
            continue
        if re.fullmatch(r"[a-z][\w.-]*", first) and len(first) >= 2:
            cmd_tokens.add(first)
    # well-known command words even without backticks
    for word in ("pbcopy", "xclip", "xsel", "printf", "echo"):
        if re.search(rf"\b{word}\b", content):
            cmd_tokens.add(word)
    # drop things that aren't commands
    NON_CMDS = {"the", "a", "an", "and", "or", "if", "see", "use", "any", "all", "rule", "always",
                "never", "must", "i", "you", "we", "it", "is", "are", "was", "were", "this",
                "that", "these", "those", "trigger", "yaml", "json", "md", "ts", "tsx", "py",
                "argparse", "claude.md", "skill.md"}
    cmd_tokens = {c for c in cmd_tokens if c.lower() not in NON_CMDS}
    for cmd in sorted(cmd_tokens):
        predicates.append({
            "kind": "command-mention",
            "strength": "weak",
            "cmd": cmd,
            "label": f"`{cmd}` in bash",
            "applicable": (lambda t, c=cmd: any(re.search(rf"\b{re.escape(c)}\b", bc) for bc in t["bash_cmds"])),
            "matches":    (lambda t, c=cmd: True),  # if it ran at all, the rule about that command had a chance
            "describe":   (lambda t, c=cmd: (
                              f"`{c}` ran "
                              + str(sum(1 for bc in t['bash_cmds'] if re.search(rf"\b{re.escape(c)}\b", bc)))
                              + "× this session"
                              if any(re.search(rf"\b{re.escape(c)}\b", bc) for bc in t['bash_cmds'])
                              else f"`{c}` did not run this session")),
        })

    # ----- end-of-message rule: summary-after-edits etc.
    if (re.search(r"end\s+your\s+response", content_l)
            or re.search(r"\b\d-\d\s+sentences?\b", content)
            or re.search(r"\buser-facing summary\b", content_l)
            or "end-of-implementation" in title_l):
        def _fires(t):
            la = t["last_assistant"]
            if not la:
                return False
            has_summary = any(k in la.lower() for k in SUMMARY_KEYWORDS) or len(la.strip().split("\n\n")[-1]) > 0
            paras = [p.strip() for p in la.strip().split("\n\n") if p.strip()]
            final_para = paras[-1] if paras else ""
            sentences = len(re.findall(r"[.!?]+", final_para))
            has_tech = bool(CODE_EXT.search(la)) or bool(re.search(r"\b(controller|service|schema|route)\b", la.lower()))
            return has_summary and sentences <= 4 and not has_tech

        predicates.append({
            "kind": "end-of-message",
            "strength": "strong",
            "label": "summary at end of response",
            "applicable": (lambda t: bool(t["edits"])),
            "matches":    _fires,
            "describe":   (lambda t: (
                              f"{len(t['edits'])} edit(s) made; "
                              + f"final message: {len(t['last_assistant'])} chars, "
                              + f"final paragraph ~{len(re.findall(r'[.!?]+', (t['last_assistant'].strip().split(chr(10)+chr(10))[-1] if t['last_assistant'].strip() else '')))} sentences")),
        })

    # A "never X" rule used to become a shell-command predicate here: the word
    # after `never` was looked up among the session's bash commands, so a rule
    # reading "never import another store's singleton" reported a violation
    # because `import` appeared inside a ripgrep command. Prose negations are
    # now the job of `rule_checks`, which routes a rule by the objects it names
    # and demands a citable span in the code before it accuses anyone.

    return predicates


def _windows_around(haystack, needle, window=140, max_hits=3):
    """Return up to `max_hits` text windows centered on case-insensitive matches of `needle`."""
    if not haystack or not needle:
        return []
    out = []
    pat = re.compile(re.escape(needle), re.I)
    for m in pat.finditer(haystack):
        start = max(0, m.start() - window)
        end = min(len(haystack), m.end() + window)
        snippet = haystack[start:end].strip()
        if start > 0: snippet = "…" + snippet
        if end < len(haystack): snippet = snippet + "…"
        # collapse runs of whitespace for compactness
        snippet = re.sub(r"[ \t]+", " ", snippet)
        out.append(snippet)
        if len(out) >= max_hits:
            break
    return out


def _block_keywords(content, prompt=""):
    """Distinctive 5+ char tokens from block content, minus stopwords + words present in user prompt."""
    stop = {"about", "above", "after", "again", "always", "before", "below", "between",
            "could", "every", "first", "have", "having", "their", "there", "these", "those",
            "through", "under", "until", "where", "which", "while", "would", "should", "claude",
            "rules", "rule", "block", "section", "files", "file", "code", "task", "tasks"}
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{4,}\b", content)
    prompt_words = set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{4,}\b", prompt or "")) | stop
    out, seen = [], set()
    for t in tokens:
        tl = t.lower()
        if tl in prompt_words or tl in seen:
            continue
        seen.add(tl)
        out.append(tl)
        if len(out) >= 12:
            break
    return out


def _is_topical(text, keywords, threshold=1):
    if not text or not keywords:
        return False
    tl = text.lower()
    return sum(1 for k in keywords if k in tl) >= threshold


def _last_sentence_with_causal(text):
    """Pick the most causally-loaded sentence in a passage (or first sentence)."""
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    sentences = [s for s in sentences if len(s) > 8]
    if not sentences:
        return text.strip()[:280]
    causal = [s for s in sentences if CAUSAL_RE.search(s)]
    pick = causal[0] if causal else sentences[0]
    return pick[:280]


def _moment(t, kind, verdict, label, text="", **extra):
    return {"t": t, "kind": kind, "verdict": verdict, "label": label, "text": text, **extra}


def _find_intent_before(seg_idx, segs, keywords, max_back=6):
    """Walk backwards in segs from seg_idx to find an assistant text segment that's topical to the block.
    Returns (text, ts) or (None, None)."""
    i = seg_idx - 1
    steps = 0
    while i >= 0 and steps < max_back:
        s = segs[i]
        if s["role"] == "assistant" and s["kind"] == "text":
            if _is_topical(s["text"], keywords) or CAUSAL_RE.search(s["text"]):
                return _last_sentence_with_causal(s["text"]), s["t"]
            steps += 1
        i -= 1
    return None, None


def _ranked_topical_segments(segs, keywords, limit=3):
    """Rank assistant text segments by topical+causal score; return top N."""
    if not keywords:
        return []
    scored = []
    for s in segs:
        if s["role"] != "assistant" or s["kind"] != "text":
            continue
        tl = s["text"].lower()
        overlap = sum(1 for k in keywords if k in tl)
        if overlap == 0:
            continue
        score = overlap
        if CAUSAL_RE.search(s["text"]):
            score += 2
        if "claude.md" in tl or "the rule" in tl or "global rules" in tl:
            score += 1
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for sc, s in scored[:limit] if sc >= 2]


def _moments_for_skill_or_command(block, file, trace, segs, kind_hint):
    """Emit moments for skill or command blocks."""
    name = (file.get("name") or "").lower()
    moments = []
    user_prompt = trace["user_prompt"] or ""
    triggered_in_prompt = _is_triggered(name, user_prompt)
    triggered_via_wrapper = any(w["name"].lower() == name for w in trace["cmd_wrappers"])
    skill_calls = [c for c in trace["calls"]
                   if c["name"] == "Skill"
                   and (c["input"].get("skill") or "").strip().lstrip("/").lower() == name]

    if triggered_in_prompt or triggered_via_wrapper or skill_calls:
        # TRIGGER ✓
        if skill_calls:
            sc = skill_calls[0]
            moments.append(_moment(sc.get("ts"), "trigger", "yes",
                                   f"`Skill` tool invoked /{name}",
                                   text=json.dumps(sc.get("input", {}))[:400]))
        elif triggered_via_wrapper:
            w = next(w for w in trace["cmd_wrappers"] if w["name"].lower() == name)
            moments.append(_moment(w["t"], "trigger", "yes",
                                   f"User invoked /{name} via slash-command",
                                   text=w["text"]))
        else:
            moments.append(_moment(None, "trigger", "yes",
                                   f"User prompt mentioned /{name}",
                                   text=user_prompt[:400]))

        # Topical assistant segments after trigger → INTENT
        keywords = _block_keywords(block["content"], user_prompt)
        intents = _ranked_topical_segments(segs, keywords, limit=2)
        for s in intents:
            moments.append(_moment(s["t"], "intent", None,
                                   "Agent reasoning",
                                   text=_last_sentence_with_causal(s["text"])))
    else:
        # NON-EVENT explaining
        reason = (f"This {kind_hint} only loads when the user invokes `/{name}` "
                  f"(in prompt or as a slash command). The user's prompt was: "
                  f"\"{(user_prompt or '(empty)')[:160]}\".")
        moments.append(_moment(None, "non-event", "no",
                               f"`/{name}` was not invoked",
                               text=reason))
    return moments


def _moments_for_subagent(block, file, trace, segs):
    name = (file.get("name") or "")
    name_l = name.lower()
    moments = []
    agent_calls = [c for c in trace["calls"]
                   if c["name"] == "Agent" and (c["input"].get("subagent_type") or "").lower() == name_l]
    if not agent_calls:
        moments.append(_moment(None, "non-event", "no",
                               f"Subagent `{name}` was not invoked",
                               text=f"This subagent only loads when an `Agent` tool call uses subagent_type=\"{name}\". "
                                    f"No such call this session."))
        return moments
    for c in agent_calls:
        moments.append(_moment(c.get("ts"), "trigger", "yes",
                               f"Agent tool used subagent_type \"{name}\"",
                               text=(c["input"].get("description") or "")[:160]))
        moments.append(_moment(c.get("ts"), "action", "yes",
                               f"Subagent prompt",
                               text=(c["input"].get("prompt") or "")[:600]))
    return moments


def _moments_for_path_table(block, file, trace, segs, predicates):
    """Path-table rule: list each row's match status against cwd."""
    moments = []
    cwd = trace["cwd"] or "(unknown)"
    table_pred = next((p for p in predicates if p["kind"] == "path-table"), None)
    if not table_pred:
        return moments
    # Re-extract rows from content (mirrors derive_predicates)
    rows = []
    for line in block["content"].splitlines():
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) >= 3 and not all(set(c) <= set("-: ") for c in cols):
            joined = " ".join(cols).lower()
            if "project path contains" in joined or "switch command" in joined:
                continue
            m = re.search(r"`([^`]+)`", cols[0])
            tok = m.group(1) if m else cols[0]
            cmd_m = ""
            for col in cols:
                cm = re.search(r"`([^`]+)`", col)
                if cm and any(s in cm.group(1) for s in [" ", "-"]):
                    cmd_m = cm.group(1)
                    break
            rows.append((tok, cmd_m))
    matched_rows = [(tok, cmd) for tok, cmd in rows if tok and tok in cwd]

    moments.append(_moment(None, "condition", "yes" if matched_rows else "no",
                           f"cwd vs path table",
                           text=f"cwd: {cwd}\nrows: " + ", ".join(f"`{t}`" for t, _ in rows)))

    if not matched_rows:
        moments.append(_moment(None, "non-event", "no",
                               "Rule had no chance to fire",
                               text=f"None of the table rows ({', '.join(f'`{t}`' for t, _ in rows)}) "
                                    f"matched cwd `{cwd}`. Consider scoping this as a path-rule "
                                    "instead of a global rule."))
        return moments

    for tok, cmd in matched_rows:
        # Did the prescribed command run?
        ran = next((bc for bc in trace["bash_cmds"] if cmd and cmd in bc), None)
        if ran:
            moments.append(_moment(None, "action", "yes",
                                   f"prescribed command for `{tok}` ran",
                                   text=ran[:400]))
        else:
            # Was *something* (e.g., gh) attempted that should have been preceded by it?
            related = next((bc for bc in trace["bash_cmds"] if "gh " in bc or bc.startswith("gh ")), None)
            if related:
                moments.append(_moment(None, "violation", "no",
                                       f"`{tok}` matched but switch command not run",
                                       text=f"Found a `gh` command without preceding switch:\n{related[:400]}"))
            else:
                moments.append(_moment(None, "omission", None,
                                       f"`{tok}` matched but command was unnecessary",
                                       text=f"No `gh` command this session, so no switch needed."))
    return moments


def _moments_for_command_mention(block, file, trace, segs, predicates):
    """Emit ACTION moments for each Bash call invoking a mentioned command. Pair with intent."""
    moments = []
    cmds = sorted({p["cmd"] for p in predicates if p["kind"] == "command-mention"})
    keywords = _block_keywords(block["content"], trace["user_prompt"])

    bash_calls_in_segs = [(i, s) for i, s in enumerate(segs)
                          if s["kind"] == "tool_use" and s.get("name") == "Bash"]
    seen = set()
    for cmd in cmds:
        for i, s in bash_calls_in_segs:
            bc = s["input"].get("command", "")
            if not re.search(rf"\b{re.escape(cmd)}\b", bc):
                continue
            key = (cmd, s["t"], bc[:80])
            if key in seen: continue
            seen.add(key)
            # intent before
            intent_text, intent_t = _find_intent_before(i, segs, keywords)
            if intent_text:
                moments.append(_moment(intent_t, "intent", None,
                                       "Agent reasoning",
                                       text=intent_text))
            desc = s["input"].get("description") or ""
            text = (f"$ {bc[:400]}" + (f"\n# {desc}" if desc else ""))
            moments.append(_moment(s["t"], "action", "yes", f"Bash ran `{cmd}`", text=text))
            if len(moments) > 30:
                break
    return moments


def _moments_for_end_of_message(block, file, trace, segs):
    moments = []
    if not trace["edits"]:
        moments.append(_moment(None, "non-event", "no",
                               "No edits → rule didn't apply",
                               text="The rule applies only when code is modified. No Edit/Write/MultiEdit "
                                    "calls in this session, so the rule had no chance to fire."))
        return moments
    moments.append(_moment(None, "applicability", "yes",
                           f"{len(trace['edits'])} code edits → rule applies",
                           text=f"Edits across {len(set(c['input'].get('file_path','') for c in trace['edits']))} files."))
    la = trace["last_assistant"]
    if la:
        paras = [p.strip() for p in la.strip().split("\n\n") if p.strip()]
        final_para = paras[-1] if paras else ""
        sentences = len(re.findall(r"[.!?]+", final_para))
        has_summary = any(k in la.lower() for k in SUMMARY_KEYWORDS) or sentences > 0
        has_tech = bool(CODE_EXT.search(la)) or bool(re.search(r"\b(controller|service|schema|route)\b", la.lower()))
        compliant = has_summary and sentences <= 4 and not has_tech
        last_ts = next((s["t"] for s in reversed(segs) if s["role"] == "assistant" and s["kind"] == "text"), None)
        moments.append(_moment(last_ts,
                               "compliance" if compliant else "violation",
                               "yes" if compliant else "no",
                               "Final assistant message",
                               text=la.strip()[-700:]))
    return moments


def _normalize_path(p):
    if not p:
        return ""
    try:
        return str(Path(p).expanduser().resolve(strict=False))
    except Exception:
        return str(p)


def _intent_text_between(prev_user_seg_idx, read_seg_idx, segs):
    for s in reversed(segs[prev_user_seg_idx + 1:read_seg_idx]):
        if s["role"] == "assistant" and s["kind"] == "text":
            return s["text"], s["t"]
    return None, None


def _find_user_prompt_seg_before(seg_idx, segs):
    for i in range(seg_idx - 1, -1, -1):
        s = segs[i]
        if s["role"] == "user" and s["kind"] in ("text", "command-wrapper"):
            return i
    return 0


def _moments_for_read_driven(block, file, trace, segs):
    moments = []
    user_prompt = trace["user_prompt"] or ""
    abs_target = _normalize_path(file.get("abs_path") or file.get("path"))

    trigger_seg = next(
        (s for s in segs if s["role"] == "user" and s["kind"] in ("text", "command-wrapper")),
        None,
    )
    moments.append(_moment(
        trigger_seg["t"] if trigger_seg else None,
        "trigger", "yes",
        "User prompt",
        text=user_prompt[:1000] if user_prompt else "(no user prompt captured)",
    ))

    matching_reads = [
        r for r in trace.get("read_calls", [])
        if _normalize_path((r.get("input") or {}).get("file_path", "")) == abs_target
    ]

    if not matching_reads:
        kind_label = file["kind"]
        moments.append(_moment(
            None, "non-event", None,
            f"File loaded as `{kind_label}` but never explicitly Read",
            text=("This file's content was placed in the context window by the harness "
                  "(via attachment, preload, or @-reference) without a Read tool call. "
                  "The agent had access to it from the start of the turn."),
        ))
        return moments

    for r in matching_reads:
        prev_user_idx = _find_user_prompt_seg_before(r["seg_idx"], segs)
        intent_text, intent_t = _intent_text_between(prev_user_idx, r["seg_idx"], segs)
        if intent_text and len(intent_text.strip()) >= 20:
            moments.append(_moment(
                intent_t, "intent", None,
                "Agent narration before Read",
                text=_last_sentence_with_causal(intent_text),
            ))

        # Encrypted-thinking hint: count thinking blocks between the user prompt
        # and this Read. Their content is empty (Anthropic encrypts extended-
        # thinking), but presence + duration is meaningful.
        thinking_segs = [s for s in segs[prev_user_idx + 1:r["seg_idx"]]
                         if s.get("kind") == "thinking"]
        if thinking_segs and not (intent_text and len(intent_text.strip()) >= 20):
            # Compute duration from first thinking timestamp to the Read timestamp.
            t0 = parse_iso(thinking_segs[0].get("t"))
            t1 = parse_iso(r.get("t"))
            dur = ""
            if t0 and t1:
                secs = max(0, int((t1 - t0).total_seconds()))
                dur = f", ~{secs}s" if secs else ""
            moments.append(_moment(
                thinking_segs[0].get("t"), "thinking-gap", None,
                f"{len(thinking_segs)} encrypted thinking block{'s' if len(thinking_segs) > 1 else ''}{dur}",
                text="",  # nothing readable to show
            ))

        fp = (r.get("input") or {}).get("file_path", "")
        action_text = f"Read({fp})"
        result = trace.get("tool_results_by_call_id", {}).get(r.get("id"))
        if result:
            action_text += f"  →  {result['line_count']} lines, {result['char_count']} chars"
        moments.append(_moment(
            r["t"], "action", "yes",
            "Read tool call",
            text=action_text,
        ))

    return moments


def _moments_for_loose_keyword(block, file, trace, segs):
    moments = []
    keywords = _block_keywords(block["content"], trace["user_prompt"])
    intents = _ranked_topical_segments(segs, keywords, limit=3)
    if not intents:
        moments.append(_moment(None, "non-event", "no",
                               "No topical reasoning detected",
                               text="No assistant text segment had ≥2 distinctive keywords from this block."))
        return moments
    for s in intents:
        moments.append(_moment(s["t"], "intent", None,
                               "Agent reasoning (topical)",
                               text=_last_sentence_with_causal(s["text"])))
    return moments


def assemble_moments(block, file, trace, predicates):
    """Per-block ordered list of {t, kind, verdict, label, text} moments."""
    segs = trace["segs"]
    file_kind = file["kind"]
    moments = []

    if not file["loaded"]:
        moments.append(_moment(None, "non-event", "no",
                               "Not loaded into context",
                               text=f"File on disk but not loaded — see file's load condition. "
                                    f"User prompt was: \"{(trace['user_prompt'] or '')[:160]}\"."))
        return moments

    if file_kind == "skill":
        moments.extend(_moments_for_skill_or_command(block, file, trace, segs, "skill"))
    elif file_kind == "command":
        moments.extend(_moments_for_skill_or_command(block, file, trace, segs, "command"))
    elif file_kind == "agent":
        moments.extend(_moments_for_subagent(block, file, trace, segs))
    elif file_kind in ("read", "preloaded", "attached"):
        moments.extend(_moments_for_read_driven(block, file, trace, segs))
    else:
        # global / project / rule / reference: derive from predicates
        if any(p["kind"] == "path-table" for p in predicates):
            moments.extend(_moments_for_path_table(block, file, trace, segs, predicates))
        if any(p["kind"] == "command-mention" for p in predicates):
            moments.extend(_moments_for_command_mention(block, file, trace, segs, predicates))
        if any(p["kind"] == "end-of-message" for p in predicates):
            moments.extend(_moments_for_end_of_message(block, file, trace, segs))
        # Trigger predicate (e.g., # graphify registration in CLAUDE.md): defer to skill-style detection
        if any(p["kind"] == "trigger" for p in predicates):
            for p in [p for p in predicates if p["kind"] == "trigger"]:
                cmd = p.get("cmd", "")
                # Same evidence order as the skill files themselves, so a
                # CLAUDE.md pointer to `/foo` and foo's own SKILL.md can never
                # disagree about whether foo fired.
                bare = cmd.lstrip("/")
                fired = _is_triggered(bare, trace["user_prompt"])
                wrapper = any(f"/{w['name'].lower()}" == cmd for w in trace["cmd_wrappers"])
                called = bare in _skill_tool_names(trace["calls"])
                if fired or wrapper or called:
                    moments.append(_moment(None, "trigger", "yes",
                                           f"`{cmd}` was invoked",
                                           text=trace["user_prompt"][:400]))
                else:
                    moments.append(_moment(None, "non-event", "no",
                                           f"`{cmd}` not invoked this run",
                                           text=f"User prompt: \"{(trace['user_prompt'] or '')[:160]}\""))
        # If nothing matched → loose keyword fallback (skipped for read-style kinds, handled above)
        if not moments:
            if file_kind == "reference":
                moments.extend(_moments_for_read_driven(block, file, trace, segs))
            else:
                moments.extend(_moments_for_loose_keyword(block, file, trace, segs))

    # Dedup by (kind, label, t, text first 200 chars) preserving first occurrence.
    seen = set()
    deduped = []
    for m in moments:
        key = (m["kind"], m.get("label", ""), m.get("t") or "", (m.get("text") or "")[:200])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(m)

    # Stable chronological sort: moments without t go to the top in declaration order.
    indexed = list(enumerate(deduped))
    indexed.sort(key=lambda x: (parse_iso(x[1]["t"]) is None and -1 or 1,
                                parse_iso(x[1]["t"]) or datetime.min,
                                x[0]))
    return [m for _, m in indexed]


# ---------- 5. duplicate detection across context files ----------

def _normalize_for_similarity(text):
    """Strip code/URLs/inline-code; lowercase and collapse whitespace."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).lower().strip()
    return text


_SHINGLE_STOP = {"the", "and", "for", "are", "was", "with", "that", "this", "from", "have",
                 "you", "your", "all", "any", "but", "not", "use", "into", "onto", "out", "use"}


def _shingles(text, n=3):
    """Word n-grams. Drop tokens shorter than 3 chars and common stopwords to reduce noise."""
    words = [w for w in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
             if w not in _SHINGLE_STOP]
    if len(words) < n:
        return set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _containment(a, b):
    """Containment coefficient: how much of the smaller set is contained in the larger.
    Better than Jaccard for asymmetric block sizes (one short rule, one long restatement).
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _word_count(text):
    return len(re.findall(r"\w+", text))


def _shared_phrase(shingles_a, shingles_b):
    """Pick a representative shared 5-gram for the UI."""
    common = shingles_a & shingles_b
    if not common:
        return ""
    return sorted(common, key=len, reverse=True)[0]


def compute_duplicates(files_out, trace, similarity_threshold=0.30, min_words=15):
    """Pairwise near-duplicate detection across blocks from different files.
    Returns list of {idA, idB, similarity, sharedPhrase, tokens, classification}.

    Costs come from each block's attributed share of its file's real token bill
    (`cost`, written by `_annotate_costs`), so a pair's price already includes
    every request that resent both blocks. Blocks with no cost - a file that was
    never sent - price at zero.
    """
    # Pre-compute normalized shingles per block
    indexed = []
    for f in files_out:
        # A listing-only entry has no file on disk, so its "content" is the
        # placeholder this tool writes: a heading, the harness's description,
        # and one boilerplate sentence identical across every such entry. Those
        # match each other at 1.0 and cost nothing, so comparing them reports
        # duplication in text that was never sent to the model - on a real
        # roster of 50-odd unresolved skills, hundreds of pairs of it.
        if f.get("source") == "listing-only":
            continue
        for b in f["blocks"]:
            normalized = _normalize_for_similarity(b["content"])
            wc = _word_count(normalized)
            shingles = _shingles(normalized) if wc >= min_words else set()
            indexed.append({
                "id": b["id"],
                "title": b["title"],
                "content": b["content"],
                "file_path": f["path"],
                "abs_path_or_path": f.get("abs_path") or f["path"],
                "loaded": f["loaded"],
                "kind": f["kind"],
                "name": f.get("name"),
                "referenced_by": f.get("referencedBy"),
                "shingles": shingles,
                "wc": wc,
                "cost": b.get("cost") or {},
            })

    pairs = []
    n = len(indexed)
    for i in range(n):
        a = indexed[i]
        if not a["shingles"]:
            continue
        for j in range(i + 1, n):
            b = indexed[j]
            if not b["shingles"]:
                continue
            # Same file → skip (intra-file duplication is a different concern)
            if a["file_path"] == b["file_path"]:
                continue
            # @-reference relationship (one file is referenced by the other) → skip
            if (a.get("referenced_by") and b["file_path"] in a["referenced_by"]) or \
               (b.get("referenced_by") and a["file_path"] in b["referenced_by"]):
                continue

            sim = _containment(a["shingles"], b["shingles"])
            if sim < similarity_threshold:
                continue

            shared = _shared_phrase(a["shingles"], b["shingles"])
            tokens_a = a["cost"].get("tokens", 0)
            tokens_b = b["cost"].get("tokens", 0)
            # What the duplication actually cost: the cheaper side is the part
            # that could have been deleted, and only its overlapping share.
            tokens = int(min(tokens_a, tokens_b) * sim)

            # Classification — only meaningful when both files were loaded into context
            if not (a["loaded"] and b["loaded"]):
                classification = "not-loaded"
            else:
                classification = _classify_pair(a, b, trace)

            pairs.append({
                "idA": a["id"],
                "idB": b["id"],
                "titleA": a["title"],
                "titleB": b["title"],
                "fileA": a["file_path"],
                "fileB": b["file_path"],
                "loadedA": a["loaded"],
                "loadedB": b["loaded"],
                "similarity": round(sim, 3),
                "sharedPhrase": shared,
                "tokens": tokens,
                "tokensA": tokens_a,
                "tokensB": tokens_b,
                "estimated": True,
                "classification": classification,
            })

    # Cost first, similarity only to break ties: a 100%-similar pair between two
    # files that were never sent cost nothing, and burying the pairs that did
    # cost real tokens under hundreds of those is what the old char-based
    # ordering did.
    pairs.sort(key=lambda p: (-p["tokens"], -p["similarity"]))
    return pairs


def _is_strong(predicate):
    """Whether a predicate carries strong evidence. See `derive_predicates`."""
    return predicate.get("strength", "strong") == "strong"


def _fired_strongly(predicate, trace):
    """A strong predicate whose precondition was met and whose rule was followed.

    The three conditions are inseparable: `matches` alone is unconditionally
    true for a command mention and true-by-default for an unfired negative
    rule, so testing it on its own is what made almost every duplicate pair
    look `referenced`.
    """
    return (_is_strong(predicate)
            and predicate["applicable"](trace)
            and predicate["matches"](trace))


def _classify_pair(a, b, trace):
    """Decide whether a session-loaded duplicate pair was used or wasted."""
    keywords = _block_keywords(a["content"] + "\n" + b["content"], trace["user_prompt"])
    relevance = _ranked_topical_segments(trace["segs"], keywords, limit=1)
    if relevance:
        return "referenced"
    # Predicate-based fall-through, restricted to the strong tier for the same
    # reason `assess_block` restricts it: weak evidence is not usage.
    a_block = {"title": a["title"], "content": a["content"], "level": 2}
    b_block = {"title": b["title"], "content": b["content"], "level": 2}
    a_fires = any(_fired_strongly(p, trace) for p in derive_predicates(a_block))
    b_fires = any(_fired_strongly(p, trace) for p in derive_predicates(b_block))
    if a_fires or b_fires:
        return "referenced"
    return "redundant"


def _block_undelivered(block, file):
    """True when this block's heading sits outside every range its file delivered."""
    if file.get("delivery") not in ("truncated", "partial-by-request"):
        return False
    start = block.get("start_line")
    delivered_to = file.get("delivered_to")
    if not start or not delivered_to:
        return False
    ranges = file.get("delivered_ranges")
    if ranges:
        return not any(s <= start <= e for s, e in ranges)
    return start > delivered_to or start < (file.get("delivered_from") or 1)


def _delivery_gap(start, ranges):
    """The (before, after) delivered ranges a line falls between, if any."""
    before = next((r for r in reversed(ranges) if r[1] < start), None)
    after = next((r for r in ranges if r[0] > start), None)
    return before, after


def assess_block(block, file, trace):
    """Evaluate a single block. Returns dict with status, reason, evidence, moments."""
    title = block["title"]
    content = block["content"]
    block_type = classify_block(title, content)
    file_loaded = file["loaded"]

    if not file_loaded:
        not_loaded_moments = [_moment(None, "non-event", "no",
                                      "Not loaded into context this run",
                                      text=(f"User prompt: \"{(trace['user_prompt'] or '')[:160]}\". "
                                            f"This file's load condition didn't fire."))]
        return {
            "title": title,
            "type": block_type,
            "level": block["level"],
            "content": content,
            "status": "not-loaded",
            "reason": "Skill/command/agent was not invoked this run — its blocks were not loaded into context.",
            "evidence": [],
            "moments": not_loaded_moments,
        }

    if _block_undelivered(block, file):
        start = block["start_line"]
        before, after = _delivery_gap(start, file.get("delivered_ranges") or [])
        if start > (file.get("delivered_to") or 0):
            reason = (f"File was truncated at line {file['delivered_to']} of "
                      f"{file['total_lines']}; this block starts at line {start} "
                      f"and never reached the model.")
        elif before and after:
            reason = (f"File was read as separate ranges; lines "
                      f"{before[1] + 1}–{after[0] - 1} of {file['total_lines']} were "
                      f"skipped, and this block starts at line {start} "
                      f"inside that gap, so it never reached the model.")
        else:
            reason = (f"File was read from line {file['delivered_from']} of "
                      f"{file['total_lines']}; this block starts at line {start} "
                      f"and never reached the model.")
        # Predicates deliberately do not run: scoring a block the model never saw
        # would report `unused`, which reads as "Claude ignored your rule".
        return {
            "title": title,
            "type": block_type,
            "level": block["level"],
            "content": content,
            "status": "undelivered",
            "reason": reason,
            "evidence": [],
            "moments": [_moment(None, "non-event", "no",
                                "Never reached the model", text=reason)],
        }

    predicates = derive_predicates(block)
    strong = [p for p in predicates if _is_strong(p)]
    weak = [p for p in predicates if not _is_strong(p)]
    applicable = [p for p in strong if p["applicable"](trace)]
    fired_applicable = [p for p in applicable if p["matches"](trace)]
    unfired_applicable = [p for p in applicable if not p["matches"](trace)]
    weak_hits = [p for p in weak if p["applicable"](trace) and p["matches"](trace)]

    evidence = []
    for p in predicates:
        try:
            evidence.append({"label": p["label"], "text": p["describe"](trace)})
        except Exception as e:
            evidence.append({"label": p["label"], "text": f"(error: {e})"})

    # Only strong predicates can reach the used/ignored end of the scale.
    if applicable:
        if fired_applicable and not unfired_applicable:
            status = "used"
            reason = (f"{len(fired_applicable)} predicate(s) applied and were satisfied: "
                      + ", ".join(p["label"] for p in fired_applicable))
        elif fired_applicable:
            status = "used-partial"
            reason = (f"Mixed: {len(fired_applicable)} satisfied "
                      f"({', '.join(p['label'] for p in fired_applicable)}); "
                      f"{len(unfired_applicable)} applied but unsatisfied "
                      f"({', '.join(p['label'] for p in unfired_applicable)}).")
        else:
            status = "ignored"
            reason = (f"{len(applicable)} predicate(s) applied but none were satisfied: "
                      + ", ".join(p["label"] for p in applicable))
    elif weak_hits:
        status = "possibly-referenced"
        reason = ("Weak evidence only — "
                  + ", ".join(p["label"] for p in weak_hits)
                  + ". The block names something that happened this run, but nothing "
                    "ties the behaviour back to the block.")
    elif predicates:
        status = "dormant"
        reason = ("No predicate's preconditions were met this run — the rule didn't apply. "
                  "Block was loaded into context but could not have fired.")
    else:
        keywords = [w.lower() for w in re.findall(r"\b[a-zA-Z]{5,}\b", content)][:8]
        hits_per_kw = {k: trace["all_assistant_text"].lower().count(k) for k in keywords}
        hits = sum(1 for k, n in hits_per_kw.items() if n > 0)
        if keywords and hits >= 2:
            status = "possibly-referenced"
            reason = (f"Weak evidence only — loose keyword match, {hits}/{len(keywords)} "
                      "keywords from the block appear in the assistant's reasoning. Common "
                      "words match by coincidence, so this is a hint, not compliance.")
            evidence.append({"label": "keyword overlap", "text": f"{hits}/{len(keywords)} keywords matched"})
        else:
            status = "unused"
            reason = "No predicate derivable and no keyword overlap with the assistant's reasoning."

    moments = assemble_moments(block, file, trace, predicates)

    out = {
        "title": title,
        "type": block_type,
        "level": block["level"],
        "content": content,
        "status": status,
        "reason": reason,
        "evidence": evidence,
        "moments": moments,
    }

    rule_check = _rule_check_for(block, file, trace)
    if rule_check:
        out["ruleCheck"] = rule_check
        _apply_rule_check(out, rule_check)
    return out


def _rule_check_for(block, file, trace):
    """Run this block's compiled checks, if its document has any."""
    corpus = trace.get("rule_corpus") or {"code": [], "commands": [], "paths": []}
    loaded = rule_checks.checks_for_doc(file.get("abs_path") or "")
    # Mechanical extraction only makes sense on a guidelines document. Reading
    # a file does not make its prose a rule the agent agreed to follow.
    fallback = file.get("kind") in ("global", "project", "rule")
    return rule_checks.check_block(block, loaded, corpus, fallback=fallback)


def _apply_rule_check(verdict, rule_check):
    """Fold a rule-check result into the block's status, reason and evidence.

    Only a violation an author signed off on turns the block red, and the
    confidence consulted is that of the violating finding itself - never the
    block's aggregate, which a bystander check could have raised. A mechanically
    extracted fallback finding is low confidence by construction and stays a
    note: a false red badge accuses the agent of misconduct it did not commit,
    which is the failure this whole phase exists to prevent.
    """
    findings = rule_check["findings"]
    violations = [f for f in findings
                  if f["state"] == "violated" and f["confidence"] in ("high", "medium")]
    if violations:
        first = violations[0]
        verdict["status"] = "ignored"
        verdict["reason"] = (f"Rule check `{first['checkId']}` fired: "
                             f"{first['path']}:{first['line']} — `{first['match'][:120]}`. "
                             + (first["message"] or "This rule was broken in code written this run."))
    for f in findings:
        verdict["evidence"].append({
            "label": f"rule check `{f['checkId']}` — {f['state']}",
            "text": f"{f['path']}:{f['line']} — {f['match'][:200]}",
        })
    for nc in rule_check["notCheckable"]:
        verdict["evidence"].append({
            "label": "not mechanically checkable",
            "text": nc.get("why", ""),
        })


CAUSAL_RE = re.compile(
    r"\b(I'?ll|I'?m going to|Let me|Let's|I should|I need to|I want to|I'?ve|"
    r"because|since|per\b|as the rule|the rule says|"
    r"in line with|to comply|to follow|skipping|ignoring|"
    r"following|noting|so I|so let)\b",
    re.I,
)


def chronological_segments(events):
    """Ordered list of segments preserving cross-event order. Each segment:
       {t, role, kind, text, name?, input?, idx}
       kinds: 'text' (assistant text), 'tool_use' (assistant), 'tool_result' (user),
              'command-wrapper' (user invoked a slash command).
       Used to reconstruct the causal sequence for a block.
    """
    out = []
    for ev_idx, e in enumerate(events):
        ts = e.get("timestamp")
        et = e.get("type")
        msg = e.get("message", {}) if isinstance(e.get("message"), dict) else {}
        content = msg.get("content")
        if et == "user" and not e.get("isMeta"):
            if isinstance(content, str):
                # Detect <command-name>...</command-name> wrapper
                m = re.search(r"<command-name>(.*?)</command-name>", content, re.DOTALL)
                if m:
                    args_m = re.search(r"<command-args>(.*?)</command-args>", content, re.DOTALL)
                    name = m.group(1).strip().lstrip("/")
                    args = (args_m.group(1).strip() if args_m else "")
                    out.append({"t": ts, "role": "user", "kind": "command-wrapper",
                                "text": f"/{name} {args}".strip(),
                                "name": name, "idx": ev_idx})
                else:
                    out.append({"t": ts, "role": "user", "kind": "text",
                                "text": content, "idx": ev_idx})
            elif isinstance(content, list):
                # A list can be a pasted-screenshot prompt or a tool-result
                # batch, never both: _user_message_text returns None for the
                # latter, so the two branches below are mutually exclusive.
                prompt_text = _user_message_text(e)
                if prompt_text:
                    out.append({"t": ts, "role": "user", "kind": "text",
                                "text": prompt_text, "idx": ev_idx})
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        rc = c.get("content")
                        text = ""
                        if isinstance(rc, str):
                            text = rc
                        elif isinstance(rc, list):
                            for x in rc:
                                if isinstance(x, dict) and x.get("type") == "text":
                                    text = x.get("text", "")
                                    break
                        out.append({"t": ts, "role": "user", "kind": "tool_result",
                                    "text": text[:600], "idx": ev_idx,
                                    "tool_use_id": c.get("tool_use_id"),
                                    "full_text_len": len(text) if isinstance(text, str) else 0,
                                    "line_count": text.count("\n") + 1 if text else 0})
        elif et == "assistant" and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text":
                    text = c.get("text", "").strip()
                    if text:
                        out.append({"t": ts, "role": "assistant", "kind": "text",
                                    "text": text, "idx": ev_idx})
                elif c.get("type") == "tool_use":
                    out.append({"t": ts, "role": "assistant", "kind": "tool_use",
                                "text": "", "name": c.get("name"),
                                "input": c.get("input", {}), "idx": ev_idx,
                                "id": c.get("id")})
                elif c.get("type") == "thinking":
                    # Claude's extended-thinking blocks. Content is encrypted in
                    # transcripts (empty `thinking` field + signature), but their
                    # presence + count + duration is meaningful — useful for
                    # surfacing "agent reasoned here, even if we can't read it".
                    out.append({"t": ts, "role": "assistant", "kind": "thinking",
                                "text": "", "idx": ev_idx,
                                "encrypted": bool(c.get("signature"))})
    return out


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def session_start_dt(segs):
    for s in segs:
        d = parse_iso(s.get("t"))
        if d:
            return d
    return None


def fmt_offset(start_dt, ts):
    """Render +Hh Mm Ss offset relative to session start."""
    d = parse_iso(ts)
    if not d or not start_dt:
        return ""
    secs = max(0, int((d - start_dt).total_seconds()))
    if secs < 60: return f"+{secs}s"
    m, s = divmod(secs, 60)
    if m < 60: return f"+{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"+{h}h{m:02d}m"


def build_trace(events, calls, asst_segments, user_prompt):
    """Bundle everything predicates and moment-assemblers need to introspect."""
    bash_cmds = [c["input"].get("command", "") for c in calls if c["name"] == "Bash"]
    edits = [c for c in calls if c["name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit")]
    all_assistant_text = "\n\n".join(s["text"] for s in asst_segments)
    last_assistant = asst_segments[-1]["text"] if asst_segments else ""
    cwd = next((e.get("cwd") for e in events if e.get("cwd")), "")
    segs = chronological_segments(events)
    start_dt = session_start_dt(segs)
    # Detect command-wrapper invocations: e.g., {"name": "graphify", ...}
    cmd_wrappers = [s for s in segs if s["kind"] == "command-wrapper"]
    tool_results_by_call_id = {
        s["tool_use_id"]: {
            "line_count": s.get("line_count", 0),
            "char_count": s.get("full_text_len", 0),
            "preview": s["text"],
            "t": s["t"],
            "seg_idx": idx,
        }
        for idx, s in enumerate(segs)
        if s["kind"] == "tool_result" and s.get("tool_use_id")
    }
    read_calls_with_seg = [
        {"id": s.get("id"), "t": s["t"], "input": s.get("input", {}), "seg_idx": idx}
        for idx, s in enumerate(segs)
        if s["kind"] == "tool_use" and s.get("name") == "Read"
    ]
    return {
        "bash_cmds": bash_cmds,
        "edits": edits,
        "rule_corpus": rule_checks.build_corpus(calls),
        "all_assistant_text": all_assistant_text,
        "last_assistant": last_assistant,
        "cwd": cwd,
        "user_prompt": user_prompt or "",
        "calls": calls,
        "segs": segs,
        "start_dt": start_dt,
        "cmd_wrappers": cmd_wrappers,
        "tool_results_by_call_id": tool_results_by_call_id,
        "read_calls": read_calls_with_seg,
    }


# ---------- 4. timeline of events ----------

def build_timeline(events):
    timeline = []
    for e in events:
        ts = e.get("timestamp")
        et = e.get("type")
        if et == "user" and not e.get("isMeta"):
            c = e.get("message", {}).get("content")
            if isinstance(c, str):
                # Searched, not prefix-matched: real wrappers lead with a
                # <command-message> line, and requiring the message to start
                # with <command-name> dumped the raw XML into the timeline.
                name_match = COMMAND_NAME_RE.search(c)
                if name_match:
                    args_match = COMMAND_ARGS_RE.search(c)
                    label = name_match.group(1).strip()
                    args = (args_match.group(1) if args_match else "").strip()
                    text = f"{label} {args}".strip()
                    timeline.append({"ts": ts, "kind": "user-command", "label": label, "text": text})
                else:
                    timeline.append({"ts": ts, "kind": "user", "label": "user", "text": c.strip()[:300]})
            elif isinstance(c, list):
                # See chronological_segments: a list is a prompt or tool
                # results, never both.
                prompt_text = _user_message_text(e)
                if prompt_text:
                    timeline.append({"ts": ts, "kind": "user", "label": "user",
                                     "text": prompt_text[:300]})
                for x in c:
                    if isinstance(x, dict) and x.get("type") == "tool_result":
                        out_text = ""
                        rc = x.get("content")
                        if isinstance(rc, str):
                            out_text = rc[:200]
                        elif isinstance(rc, list):
                            for y in rc:
                                if isinstance(y, dict) and y.get("type") == "text":
                                    out_text = y.get("text", "")[:200]
                                    break
                        timeline.append({"ts": ts, "kind": "tool-result", "label": "tool result", "text": out_text})
        elif et == "assistant":
            content = e.get("message", {}).get("content", [])
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            t = c.get("text", "").strip()
                            if t:
                                timeline.append({"ts": ts, "kind": "assistant-text", "label": "assistant", "text": t[:400]})
                        elif c.get("type") == "tool_use":
                            inp = c.get("input", {})
                            name = c.get("name", "")
                            if name == "Read":
                                detail = inp.get("file_path", "")
                            elif name == "Edit":
                                detail = inp.get("file_path", "")
                            elif name == "Bash":
                                detail = inp.get("command", "")[:160]
                            elif name == "Glob":
                                detail = inp.get("pattern", "")
                            else:
                                detail = json.dumps(inp)[:160]
                            timeline.append({"ts": ts, "kind": "tool-use", "label": name, "text": detail})
    return timeline


# ---------- 5. file-activity stats ----------

def file_activity(calls):
    reads = Counter()
    edits = Counter()
    for c in calls:
        fp = c["input"].get("file_path")
        if not fp:
            continue
        if c["name"] == "Read":
            reads[fp] += 1
        elif c["name"] in ("Edit", "Write", "MultiEdit"):
            edits[fp] += 1
    return reads, edits


# ---------- 6. session compare ----------

def turn_actions(turn):
    """The ordered tool calls of one baked turn payload.

    Read back off the turn's own timeline rather than stored as a second copy:
    the timeline already carries every tool_use in order with its detail
    string, and a parallel field would be one more thing to keep in sync for
    the sake of a payload that is only ever built in compare mode.
    """
    out = []
    for row in turn.get("timeline") or []:
        if row.get("kind") == "tool-use":
            out.append({
                "turn": turn.get("index"),
                "name": row.get("label") or "",
                "detail": (row.get("text") or "")[:120],
                "ts": row.get("ts"),
            })
    return out


def session_actions(data):
    """Every tool call of a baked session, in order, tagged with its turn.

    Falls back to the aggregate timeline for a session that produced no turns
    (a transcript with no real user prompt), so comparing one never yields an
    empty sequence that would read as "the agent did nothing".
    """
    turns = data.get("turns") or []
    if turns:
        actions = [a for t in turns for a in turn_actions(t)]
    else:
        actions = turn_actions({"index": None, "timeline": data.get("timeline")})
    for i, a in enumerate(actions):
        a["step"] = i
    return actions


def align_actions(names_a, names_b):
    """Align two tool-call name sequences by content, returning step records.

    Uses difflib's LCS rather than pairing by ordinal: one extra call early in
    a run shifts every later index, so an index-wise comparison reports the
    whole tail as divergent when only one step actually differs.

    `autojunk` is off on purpose. It treats any element occurring in more than
    1% of a sequence of 200+ items as junk, and tool names are exactly that
    kind of high-frequency token - with it on, Read and Bash stop being
    matchable on any long session and the alignment collapses.

    Each record is {kind, a, b} where a/b are indices into the respective
    sequence (None on the side that has no counterpart). `kind` is one of
    match, changed (both sides have a step here but the tool differs),
    added (B only), removed (A only).
    """
    a, b = list(names_a), list(names_b)
    matcher = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    steps = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                steps.append({"kind": "match", "a": i1 + k, "b": j1 + k})
        elif tag == "replace":
            # Pair the overlapping head so a substituted call reads as one
            # changed step rather than a removal followed by an addition.
            overlap = min(i2 - i1, j2 - j1)
            for k in range(overlap):
                steps.append({"kind": "changed", "a": i1 + k, "b": j1 + k})
            for k in range(i1 + overlap, i2):
                steps.append({"kind": "removed", "a": k, "b": None})
            for k in range(j1 + overlap, j2):
                steps.append({"kind": "added", "a": None, "b": k})
        elif tag == "delete":
            for k in range(i1, i2):
                steps.append({"kind": "removed", "a": k, "b": None})
        elif tag == "insert":
            for k in range(j1, j2):
                steps.append({"kind": "added", "a": None, "b": k})
    return steps


def compare_actions(actions_a, actions_b):
    """Aligned step rows carrying each side's action record (or None)."""
    steps = align_actions([a["name"] for a in actions_a], [b["name"] for b in actions_b])
    return [{
        "kind": s["kind"],
        "a": actions_a[s["a"]] if s["a"] is not None else None,
        "b": actions_b[s["b"]] if s["b"] is not None else None,
    } for s in steps]


def _blocks_by_id(file_rec):
    return {b["id"]: b for b in (file_rec.get("blocks") or [])}


def _block_ref(block):
    return {"id": block["id"], "title": block.get("title", "")}


def compare_context_files(files_a, files_b):
    """Block-wise diff of two sessions' context files, keyed by block id.

    Only files with something to report are returned - an identical file on
    both sides is noise in a diff view, and the pair of sessions typically
    shares dozens of them.

    `drifted` means the file's own content changed between the two runs
    (blocks added, removed, or their text edited), which for a CLAUDE.md or a
    skill is the edit the comparison exists to attribute behaviour to. A
    verdict that moved without any content change is reported separately: the
    file is the same, the agent treated it differently.

    Known consequence of the id scheme (`file_slug + index + title-slug`):
    inserting a block shifts the index of every block below it, so that edit
    reports as one added block plus a run of added/removed pairs rather than a
    single insertion. Matching on title instead would be wrong in the other
    direction - titles repeat across a file - and the ids are the addressing
    scheme the rest of the tool depends on, so they stay the key.
    """
    by_path_a = {f["path"]: f for f in files_a}
    by_path_b = {f["path"]: f for f in files_b}
    out = []
    for path in sorted(set(by_path_a) | set(by_path_b)):
        fa, fb = by_path_a.get(path), by_path_b.get(path)
        blocks_a = _blocks_by_id(fa) if fa else {}
        blocks_b = _blocks_by_id(fb) if fb else {}
        added = [_block_ref(blocks_b[i]) for i in blocks_b if i not in blocks_a]
        removed = [_block_ref(blocks_a[i]) for i in blocks_a if i not in blocks_b]
        changed, verdict_changes = [], []
        for bid, ba in blocks_a.items():
            bb = blocks_b.get(bid)
            if bb is None:
                continue
            if ba.get("content") != bb.get("content"):
                changed.append(_block_ref(ba))
            if ba.get("status") != bb.get("status"):
                verdict_changes.append({"id": bid, "title": ba.get("title", ""),
                                        "from": ba.get("status"), "to": bb.get("status")})
        loaded_a = bool(fa and fa.get("loaded"))
        loaded_b = bool(fb and fb.get("loaded"))
        presence = "both" if (fa and fb) else ("a-only" if fa else "b-only")
        if not (added or removed or changed or verdict_changes
                or presence != "both" or loaded_a != loaded_b):
            continue
        out.append({
            "path": path,
            "presence": presence,
            "loadedA": loaded_a,
            "loadedB": loaded_b,
            "drifted": bool(added or removed or changed),
            "added": added,
            "removed": removed,
            "changed": changed,
            "verdictChanges": verdict_changes,
        })
    return out


def _normalize_prompt(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _turn_brief(turn):
    if turn is None:
        return None
    return {
        "id": turn.get("id"),
        "index": turn.get("index"),
        "promptPreview": turn.get("promptPreview") or "",
        "toolCalls": (turn.get("counts") or {}).get("totalToolCalls", 0),
        "edits": (turn.get("counts") or {}).get("filesEdited", 0),
        "usage": turn.get("usage") or {},
    }


def _turn_metric(brief, key):
    if brief is None:
        return 0
    if key in ("toolCalls", "edits"):
        return brief.get(key, 0)
    return (brief.get("usage") or {}).get(key, 0)


def compare_turn_rows(turns_a, turns_b):
    """Turn-by-turn deltas, paired by ordinal.

    Turns pair by position while steps pair by content, and the asymmetry is
    deliberate: a turn is anchored to a human prompt, so turn N of both runs is
    the same instruction being answered, whereas the agent's steps inside a
    turn are exactly what a CLAUDE.md edit is expected to shift. An unpaired
    trailing turn (one run needed a follow-up prompt the other did not) is
    itself the finding, so it is emitted with the missing side null.
    """
    rows = []
    for i in range(max(len(turns_a), len(turns_b))):
        a = _turn_brief(turns_a[i]) if i < len(turns_a) else None
        b = _turn_brief(turns_b[i]) if i < len(turns_b) else None
        rows.append({
            "index": i,
            "a": a,
            "b": b,
            "promptMatch": bool(
                a and b and _normalize_prompt(turns_a[i].get("userPrompt"))
                == _normalize_prompt(turns_b[i].get("userPrompt"))),
            "deltas": {k: _turn_metric(b, k) - _turn_metric(a, k)
                       for k in ("toolCalls", "edits", "promptTokens", "outputTokens")},
        })
    return rows


def compare_sessions(data_a, data_b):
    """Compare two baked per-session payloads. Computed once, at build time.

    Consumes only the baked JSON (turn timelines, context files, usage totals)
    so the compare view can never disagree with the panels it sits beside.
    """
    actions_a, actions_b = session_actions(data_a), session_actions(data_b)
    steps = compare_actions(actions_a, actions_b)
    context = compare_context_files(data_a.get("contextFiles") or [],
                                    data_b.get("contextFiles") or [])

    counts_a = Counter(a["name"] for a in actions_a)
    counts_b = Counter(b["name"] for b in actions_b)
    tool_delta = {name: counts_b.get(name, 0) - counts_a.get(name, 0)
                  for name in sorted(set(counts_a) | set(counts_b))
                  if counts_b.get(name, 0) != counts_a.get(name, 0)}

    usage_a = data_a.get("usage") or {}
    usage_b = data_b.get("usage") or {}
    prompt_a = (data_a.get("session") or {}).get("userPrompt", "")
    prompt_b = (data_b.get("session") or {}).get("userPrompt", "")
    same_task = _normalize_prompt(prompt_a) == _normalize_prompt(prompt_b)

    verdict_changes = [dict(c, path=f["path"])
                       for f in context for c in f["verdictChanges"]]

    def side(data, prompt):
        s = data.get("session") or {}
        return {
            "id": s.get("id", ""),
            "prompt": prompt,
            "startTime": s.get("startTime", ""),
            "turnCount": data.get("turnCount", 0),
            "usage": data.get("usage") or {},
            "counts": data.get("counts") or {},
        }

    return {
        "a": side(data_a, prompt_a),
        "b": side(data_b, prompt_b),
        "sameTask": same_task,
        # Deltas are only meaningful when both runs answered the same question.
        "note": "" if same_task else (
            "The two sessions opened with different prompts - these are different "
            "tasks, so the deltas below may mislead."),
        "steps": steps,
        "divergentSteps": sum(1 for s in steps if s["kind"] != "match"),
        "turns": compare_turn_rows(data_a.get("turns") or [], data_b.get("turns") or []),
        "contextFiles": context,
        "verdictChanges": verdict_changes,
        "deltas": {
            "toolCalls": tool_delta,
            "totalToolCalls": len(actions_b) - len(actions_a),
            "filesEdited": ((data_b.get("counts") or {}).get("filesEdited", 0)
                            - (data_a.get("counts") or {}).get("filesEdited", 0)),
            "promptTokens": usage_b.get("promptTokens", 0) - usage_a.get("promptTokens", 0),
            "outputTokens": usage_b.get("outputTokens", 0) - usage_a.get("outputTokens", 0),
        },
    }


def resolve_session_id(per_session_data, prefix):
    """One baked session id matching `prefix`. Raises ValueError otherwise."""
    matches = [sid for sid in per_session_data if sid.startswith(prefix)]
    if not matches:
        raise ValueError(f"no baked session id starts with `{prefix}`")
    if len(matches) > 1:
        raise ValueError(f"`{prefix}` matches {len(matches)} sessions: "
                         + ", ".join(s[:10] for s in sorted(matches)))
    return matches[0]


# ---------- main ----------

def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--transcript", type=Path, default=None,
                   help="Path to a single .jsonl transcript. If set, only this session is processed.")
    p.add_argument("--session", type=str, default=None,
                   help="Pick the active session by id prefix (default: most recent).")
    p.add_argument("--list", action="store_true",
                   help="List all sessions for the current cwd's project and exit.")
    p.add_argument("--all-sessions", action=argparse.BooleanOptionalAction, default=True,
                   help="Bake multiple sessions into the HTML for in-browser switching (default: on).")
    p.add_argument("--max-sessions", type=int, default=20,
                   help="Cap on number of sessions baked (most recent first). 0 = unlimited. Default: 20.")
    p.add_argument("--claude-md", type=Path, default=DEFAULT_CLAUDE_MD,
                   help="Global CLAUDE.md path (default: ~/.claude/CLAUDE.md)")
    p.add_argument("--project-claude-md", type=Path, default=Path.cwd() / "CLAUDE.md",
                   help="Project CLAUDE.md path (default: ./CLAUDE.md)")
    p.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR,
                   help="Skills directory (default: ~/.claude/skills)")
    p.add_argument("--out", type=Path, default=Path.cwd() / "agent-context-ide-real.html",
                   help="Output HTML path (default: ./agent-context-ide-real.html)")
    p.add_argument("--projects-dir", type=Path, default=DEFAULT_PROJECTS_DIR,
                   help="Claude projects dir for auto-discovery (default: ~/.claude/projects)")
    p.add_argument("--compare", nargs=2, metavar=("SESSION_A", "SESSION_B"), default=None,
                   help="Bake a Compare tab for two sessions (id prefixes). "
                        "Off by default: the compare payload is only emitted when asked for.")
    p.add_argument("--query", nargs="+", metavar="ADDRESS", default=None,
                   help="Read-only text query instead of an HTML build. Address: "
                        "`sessions` | <session-id> [turn-N] [turns|blocks|<block-id>].")
    p.add_argument("--field", type=str, default=None,
                   help="With --query: print one field in full, unbounded "
                        "(block: title/status/reason/content/moments; session or turn: prompt).")
    p.add_argument("--all", action="store_true",
                   help="With --query: print every row of a listing instead of the first "
                        f"{QUERY_ROW_LIMIT}.")
    return p.parse_args()


def _fmt_dur(sec):
    if sec < 60: return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60: return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def cmd_list(args):
    """Print summaries of all sessions for cwd and exit."""
    paths = discover_all_transcripts(os.getcwd(), args.projects_dir)
    if not paths:
        sys.exit(f"No transcripts found under {args.projects_dir}/{encode_cwd_for_projects(os.getcwd())}/")
    print(f"{'SESSION':10s}  {'WHEN':16s}  {'DUR':>7s}  {'EV':>4s}  {'TOOLS':>5s}  PROMPT")
    print("-" * 90)
    for path in paths:
        s = summarize_transcript(path)
        if not s:
            continue
        when = (s["startTime"] or "")[:16].replace("T", " ")
        print(f"{s['id'][:10]}  {when:16s}  {_fmt_dur(s['durationSec']):>7s}  "
              f"{s['events']:>4d}  {s['toolCalls']:>5d}  {s['promptPreview']}")


# ---------- 7. CLI query mode ----------
#
# A read-only text view of the same baked JSON the page renders. Nothing here
# re-derives a fact: the CLI and the HTML must never be able to disagree.

QUERY_CMD = "python3 build_real_view.py"
# Roughly a screenful of context for an agent reading its own audit: long
# enough for a real verdict reason, short enough that a listing of 60 blocks
# plus one block's detail still fits in a single tool result.
QUERY_FIELD_LIMIT = 1500
QUERY_ROW_LIMIT = 60
QUERY_BLOCK_FIELDS = ("title", "status", "reason", "content", "moments")


class QueryError(Exception):
    """An address that does not resolve, carrying the message the CLI prints.

    Always phrased with the exact command that lists the valid ids at that
    level, so a wrong guess is one command away from the right one.
    """


def _query_cmd(*parts):
    return " ".join((QUERY_CMD, "--query") + tuple(str(p) for p in parts))


def _fmt_tokens(n):
    """Mirror of the page's `fmtTokens`, down to the rounding.

    The same figure has to read the same in both views: a session the page
    calls 7.1k must not be 7k on the command line.
    """
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k" if n < 10_000 else f"{n / 1000:.0f}k"
    return f"{n / 1_000_000:.1f}M"


def _usage_brief(usage):
    u = usage or {}
    return f"{_fmt_tokens(u.get('promptTokens'))} in / {_fmt_tokens(u.get('outputTokens'))} out"


def _when(ts):
    return (ts or "")[:16].replace("T", " ")


def _bounded(value, full_cmd):
    """A field trimmed to the output bound, naming the command that returns the rest."""
    text = "" if value is None else str(value)
    if len(text) <= QUERY_FIELD_LIMIT:
        return text
    return (text[:QUERY_FIELD_LIMIT]
            + f" … [{len(text) - QUERY_FIELD_LIMIT} more chars — full value: {full_cmd}]")


def _bounded_rows(rows, full_cmd, show_all):
    if show_all or len(rows) <= QUERY_ROW_LIMIT:
        return list(rows)
    return list(rows[:QUERY_ROW_LIMIT]) + [
        f"… {len(rows) - QUERY_ROW_LIMIT} more rows — full listing: {full_cmd}"]


def _resolve_query_session(data, prefix):
    per = data.get("perSession") or {}
    try:
        sid = resolve_session_id(per, prefix)
    except ValueError as e:
        raise QueryError(f"error: {e}. List sessions with: {_query_cmd('sessions')}")
    return sid, per[sid]


def _resolve_query_turn(session_data, sid, token):
    for t in session_data.get("turns") or []:
        if t["id"] == token:
            return t
    raise QueryError(f"error: session {sid} has no {token}. "
                     f"List turns with: {_query_cmd(sid, 'turns')}")


def _find_query_block(session_data, block_id):
    """(scope label, file record, block) for a block id, at any scope.

    Turn-scoped ids carry a `turnN-` prefix, so one id is enough to address a
    block anywhere in the session: the caller never has to know which scope it
    came from to ask about it.
    """
    for f in session_data.get("contextFiles") or []:
        for b in f["blocks"]:
            if b["id"] == block_id:
                return "session", f, b
    for t in session_data.get("turns") or []:
        for f in t.get("contextFiles") or []:
            for b in f["blocks"]:
                if b["id"] == block_id:
                    return t["id"], f, b
    return None


def _moment_verdict(moment):
    """A moment's verdict, readable when it has none.

    Informational moments (agent reasoning, non-events) carry `verdict: null`,
    which would otherwise print as the literal `None`.
    """
    return moment.get("verdict") or "-"


def _query_field(obj, field, valid):
    if field not in valid:
        raise QueryError(f"error: unknown field `{field}`. Valid fields: {', '.join(valid)}")
    value = obj.get(field)
    if field == "moments":
        return [f"[{_moment_verdict(m)}] {m.get('label', '')} — {m.get('text', '')}"
                for m in (value or [])]
    return [str(value if value is not None else "")]


def query_sessions(data, show_all=False):
    per = data.get("perSession") or {}
    rows = []
    for s in data.get("sessions") or []:
        sd = per.get(s["id"]) or {}
        rows.append(f"{s['id']}  {_when(s.get('startTime'))}  "
                    f"{sd.get('turnCount', 0)} turns  {_usage_brief(s.get('usage'))}  "
                    f"{_bounded(s.get('promptPreview'), _query_cmd(s['id'], '--field prompt'))}")
    lines = [f"{len(rows)} session(s) in {(data.get('project') or {}).get('cwd', '')}"]
    lines += _bounded_rows(rows, _query_cmd("sessions", "--all"), show_all)
    if rows:
        first = (data.get("sessions") or [{}])[0].get("id", "")
        lines.append(f"next: {_query_cmd(first, 'turns')}")
    return lines


def query_session(sid, session_data, field=None):
    sess = session_data.get("session") or {}
    if field:
        return _query_field({"prompt": sess.get("userPrompt")}, field, ("prompt",))
    counts = session_data.get("counts") or {}
    return [
        f"session  {sid}",
        f"when     {_when(sess.get('startTime'))}",
        f"turns    {session_data.get('turnCount', 0)}",
        f"calls    {counts.get('totalToolCalls', 0)} tool calls, "
        f"{counts.get('filesEdited', 0)} files edited",
        f"tokens   {_usage_brief(session_data.get('usage'))}",
        f"prompt   {_bounded(sess.get('userPrompt'), _query_cmd(sid, '--field prompt'))}",
        f"next: {_query_cmd(sid, 'turns')}",
        f"      {_query_cmd(sid, 'blocks')}",
    ]


def query_turns(sid, session_data, show_all=False):
    turns = session_data.get("turns") or []
    rows = []
    for t in turns:
        rows.append(f"{t['id']}  {_when(t.get('startTime'))}  "
                    f"{(t.get('counts') or {}).get('totalToolCalls', 0)} calls  "
                    f"{_usage_brief(t.get('usage'))}  "
                    f"{_bounded(t.get('promptPreview'), _query_cmd(sid, t['id'], '--field prompt'))}")
    lines = [f"session {sid} — {len(turns)} turn(s)"]
    lines += _bounded_rows(rows, _query_cmd(sid, "turns", "--all"), show_all)
    if turns:
        lines.append(f"next: {_query_cmd(sid, turns[0]['id'], 'blocks')}")
    return lines


def query_turn(sid, turn, field=None):
    if field:
        return _query_field({"prompt": turn.get("userPrompt")}, field, ("prompt",))
    counts = turn.get("counts") or {}
    return [
        f"turn     {turn['id']} of session {sid}",
        f"when     {_when(turn.get('startTime'))}",
        f"calls    {counts.get('totalToolCalls', 0)} tool calls, "
        f"{counts.get('filesEdited', 0)} files edited",
        f"tokens   {_usage_brief(turn.get('usage'))}",
        f"prompt   {_bounded(turn.get('userPrompt'), _query_cmd(sid, turn['id'], '--field prompt'))}",
        f"next: {_query_cmd(sid, turn['id'], 'blocks')}",
    ]


def _blocks_listing_cmd(sid, turn, *extra):
    return (_query_cmd(sid, turn["id"], "blocks", *extra) if turn is not None
            else _query_cmd(sid, "blocks", *extra))


def query_blocks(sid, session_data, turn=None, show_all=False):
    scope = turn if turn is not None else session_data
    label = turn["id"] if turn is not None else "session scope"
    rows = []
    first_id = None
    for f in scope.get("contextFiles") or []:
        for b in f["blocks"]:
            rows.append(f"{b['id']}  [{b.get('status', '')}]  {f['path']}: {b.get('title', '')}")
            first_id = first_id or b["id"]
    lines = [f"session {sid} — {label} — {len(rows)} block(s)"]
    lines += _bounded_rows(rows, _blocks_listing_cmd(sid, turn, "--all"), show_all)
    if first_id:
        lines.append(f"next: {_query_cmd(sid, first_id)}")
    return lines


def query_block(sid, session_data, block_id, turn=None, field=None):
    found = _find_query_block(session_data, block_id)
    if not found:
        # The listing named is the one the caller addressed, so the suggested
        # command lists exactly the ids that would have worked here.
        raise QueryError(f"error: session {sid} has no block `{block_id}`. "
                         f"List blocks with: {_blocks_listing_cmd(sid, turn)}")
    scope, file_rec, block = found
    if field:
        return _query_field(block, field, QUERY_BLOCK_FIELDS)
    reason_cmd = _query_cmd(sid, block_id, "--field reason")
    moments_cmd = _query_cmd(sid, block_id, "--field moments")
    lines = [
        f"block    {block_id}",
        f"scope    {scope}",
        f"file     {file_rec['path']} ({'loaded' if file_rec.get('loaded') else 'not loaded'})",
        f"title    {block.get('title', '')}",
        f"status   {block.get('status', '')}",
        f"reason   {_bounded(block.get('reason'), reason_cmd)}",
    ]
    # A rule that could not be checked has to say so here too: the CLI is the
    # agent-facing view, and silence there reads as "the rule was followed".
    rule_check = block.get("ruleCheck")
    if rule_check:
        lines.append(f"rule     {rule_check['state']} ({rule_check['confidence']} "
                     f"confidence, {rule_check['source']})")
        for f in rule_check.get("findings") or []:
            lines.append(f"  [{f['state']}] {f['checkId']} — "
                         f"{f['path']}:{f['line']} {f['match'][:120]}")
        for nc in rule_check.get("notCheckable") or []:
            lines.append(f"  [why] {nc.get('why', '')}")
    lines.append(f"moments  {len(block.get('moments') or [])}")
    for m in block.get("moments") or []:
        text = _bounded(f"{m.get('label', '')} — {m.get('text', '')}", moments_cmd)
        lines.append(f"  [{_moment_verdict(m)}] {text}")
    lines.append(f"next: {_query_cmd(sid, block_id, '--field content')}")
    return lines


def run_query(data, address, field=None, show_all=False):
    """Answer one address against the baked payload. Returns the lines to print.

    Read-only by construction: it touches nothing but `data`, which is why the
    query path can never leave an HTML artifact behind.
    """
    if not address:
        raise QueryError(f"error: --query needs an address. Start with: {_query_cmd('sessions')}")
    head = address[0]
    if head == "sessions":
        if len(address) > 1:
            raise QueryError(f"error: `sessions` takes no further address. "
                             f"Try: {_query_cmd('sessions')}")
        return query_sessions(data, show_all=show_all)

    sid, session_data = _resolve_query_session(data, head)
    rest = list(address[1:])
    turn = None
    if rest and rest[0].startswith("turn-"):
        turn = _resolve_query_turn(session_data, sid, rest.pop(0))
    if not rest:
        return (query_turn(sid, turn, field=field) if turn is not None
                else query_session(sid, session_data, field=field))
    token = rest.pop(0)
    if rest:
        raise QueryError(f"error: unexpected address `{' '.join(rest)}`. "
                         f"An address is <session> [turn-N] [blocks|turns|<block-id>].")
    if token in ("turns", "blocks"):
        if field:
            raise QueryError(f"error: --field addresses one session, turn or block, "
                             f"not the `{token}` listing.")
        if token == "turns":
            return query_turns(sid, session_data, show_all=show_all)
        return query_blocks(sid, session_data, turn=turn, show_all=show_all)
    return query_block(sid, session_data, token, turn=turn, field=field)


def cmd_query(args):
    """Print the answer to one query. Never writes HTML and never opens a browser."""
    address = list(args.query)
    # Same guard as the HTML build: without the global CLAUDE.md the context
    # set is silently short a file, and a block listing that omits it reads as
    # "those rules were never there" rather than "I couldn't find them".
    if args.claude_md is not None and not args.claude_md.exists():
        raise QueryError(f"error: CLAUDE.md not found: {args.claude_md}. "
                         f"Pass --claude-md or skip with /dev/null.")
    if address and address[0] != "sessions" and args.transcript is None:
        # Bake only the addressed session: every non-listing query is scoped to
        # one session, and processing twenty of them to answer about one is
        # pure latency. Resolved against the transcript filenames (which are
        # the session ids) so a typo fails before anything is parsed, and
        # through the same helper the payload uses so an ambiguous prefix is
        # refused here rather than silently answered for the newest match.
        stems = {p.stem: None for p in discover_all_transcripts(os.getcwd(), args.projects_dir)}
        try:
            args.session = resolve_session_id(stems, address[0])
        except ValueError as e:
            raise QueryError(f"error: {e}. List sessions with: {_query_cmd('sessions')}")
        args.all_sessions = False

    all_paths, active_path = select_transcripts(args)
    sessions, per_session_data, active_id = bake_sessions(all_paths, active_path, args)
    data = build_data(os.getcwd(), sessions, per_session_data, active_id)
    for line in run_query(data, address, field=args.field, show_all=args.all):
        print(line)


def _parse_iso_safe(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _as_utc(dt):
    """Make a datetime comparable with the others in this file.

    Transcript and hook timestamps both carry an offset, but a naive one from a
    hand-written fixture would raise on comparison, so assume UTC for those.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _annotate_costs(file_items, entries, nonresident_by_request=None, history_chars=None):
    """Price every context file and its blocks, in place.

    `file_items` is `(abs_path, chars, rec)` per context file, in payload order.
    Only files that were loaded take part in the attribution: a file on disk
    that never reached the model cost nothing, and giving it a share would make
    the totals stop reconciling with the API's own figures.
    """
    items = [(p, c) for p, c, rec in file_items if rec["loaded"]]
    result = attribute_usage(items, entries or [],
                             nonresident_by_request=nonresident_by_request,
                             history_chars=history_chars)
    for path, _chars, rec in file_items:
        cost = result["files"].get(path) or {"sentCount": 0, "tokens": 0, "cached": 0, "fresh": 0}
        rec["cost"] = cost
        for block, block_cost in zip(rec["blocks"], block_costs(cost, rec["blocks"])):
            block["cost"] = block_cost
    return result


def _compute_payload(events, calls, asst_segs, args, project_dir, id_prefix="", hook_facts=None,
                     nonresident_paths=None, usage_entries=None, history_chars=None,
                     nonresident_by_request=None):
    """Run the assessment pipeline against an event/call/segment bundle.

    Used twice in process_session: once over the full session (the aggregate)
    and once per turn (with a sliced bundle). Returns a dict with the same
    shape as today's per-session payload (counts, contextFiles, timeline,
    fileActivity), plus prompt and timing fields the caller composes into the
    final per-session / per-turn record.

    `id_prefix` is prepended to every block id so per-turn block ids never
    collide with the aggregate's ids in the rendered DOM.

    `nonresident_paths` drops files that were not in context for this turn.
    They are omitted rather than scored, so `combine_verdicts` judges their
    blocks only on the turns where the model could actually see them.

    `usage_entries` (with `history_chars` and, at session scope, the per-request
    `nonresident_by_request`) prices the files: pass the whole session's series
    for the aggregate and the turn's slice for a turn, and per-turn costs sum
    back to the session's.
    """
    user_prompt = first_real_user_prompt(events)
    timeline = build_timeline(events)
    reads, edits_counter = file_activity(calls)
    trace = build_trace(events, calls, asst_segs, user_prompt)

    context_files = load_context_files(events, calls, project_dir, args, user_prompt,
                                       hook_facts=hook_facts)
    files_out = []
    file_items = []  # (abs_path, chars, rec) parallel to files_out, for pricing
    for f in context_files:
        if nonresident_paths and f["abs_path"] in nonresident_paths:
            continue
        slug = file_slug(f["abs_path"])
        assessed = []
        for idx, b in enumerate(f["blocks"]):
            title_slug = re.sub(r"[^a-z0-9]+", "-", b["title"].lower()).strip("-") or "block"
            verdict = assess_block(b, f, trace)
            verdict["id"] = f"{id_prefix}{slug}-{idx}-{title_slug}"
            assessed.append(verdict)
        if f["kind"] == "read":
            group = "read"
        elif f["kind"] in ("project", "rule"):
            group = "project"
        elif f["kind"] in ("preloaded", "attached"):
            group = "project" if (project_dir and Path(project_dir).as_posix() in f["abs_path"]) else "global"
        elif f.get("scope") == "project":
            group = "project"
        elif f["kind"] == "reference":
            group = "project" if (project_dir and str(project_dir) in f["abs_path"]) else "global"
        else:
            group = "global"
        rec = {
            "path": f["path"],
            "kind": f["kind"],
            "loaded": f["loaded"],
            "group": group,
            "source": f.get("source", "disk"),
            "drift": f.get("drift", False),
            "name": f.get("name"),
            "scope": f.get("scope"),
            "referencedBy": f.get("referenced_by"),
            "blocks": assessed,
        }
        # Emitted only when content was actually withheld, so a session with no
        # truncation serialises exactly as it did before this field existed.
        if f.get("delivery") in ("truncated", "partial-by-request"):
            rec["delivery"] = {
                "mode": f["delivery"],
                "totalLines": f.get("total_lines"),
                "from": f.get("delivered_from"),
                "to": f.get("delivered_to"),
                "ranges": [list(r) for r in (f.get("delivered_ranges") or [])],
            }
        # Same rule as `delivery`: present only when the hook log actually
        # recorded this file, so hookless sessions serialise unchanged.
        if f.get("hook"):
            h = f["hook"]
            rec["hook"] = {
                "memoryType": h.get("memory_type"),
                "loadReason": h.get("load_reason"),
                "globs": h.get("globs"),
                "triggerFile": _short_path(h.get("trigger_file_path"), project_dir),
            }
        files_out.append(rec)
        file_items.append((f["abs_path"], f.get("chars", 0), rec))

    attribution = _annotate_costs(file_items, usage_entries,
                                  nonresident_by_request=nonresident_by_request,
                                  history_chars=history_chars)

    timestamps = [e.get("timestamp") for e in events if e.get("timestamp")]
    start = (timestamps[0] if timestamps else "") or (timeline[0]["ts"] if timeline else "")
    end = (timestamps[-1] if timestamps else "") or (timeline[-1]["ts"] if timeline else "")
    s_dt, e_dt = _parse_iso_safe(start), _parse_iso_safe(end)
    duration_sec = int((e_dt - s_dt).total_seconds()) if s_dt and e_dt else 0

    tool_counts = Counter(c["name"] for c in calls)
    counts = {
        "events": len(events),
        "userMessages": count_real_user_prompts(events),
        "assistantMessages": sum(1 for e in events if e.get("type") == "assistant"),
        "toolCalls": dict(tool_counts.most_common()),
        "totalToolCalls": sum(tool_counts.values()),
        "filesRead": len(reads),
        "filesEdited": len(edits_counter),
    }

    return {
        "userPrompt": user_prompt or "",
        "promptPreview": ((user_prompt[:140] + "…") if user_prompt and len(user_prompt) > 140 else (user_prompt or "")),
        "startTime": start,
        "endTime": end,
        "durationSec": duration_sec,
        "counts": counts,
        "attribution": attribution,
        "contextFiles": files_out,
        "timeline": timeline,
        "fileActivity": {
            "reads": reads.most_common(),
            "edits": edits_counter.most_common(),
        },
        "trace": trace,  # caller uses this for compute_duplicates; not emitted
    }


def _insert_timeline_row(timeline, row):
    """Splice one marker row into a timeline, in place, at its timestamp."""
    dt = _as_utc(_parse_iso_safe(row.get("ts")))
    pos = len(timeline)
    # An unparseable marker timestamp can't be ordered against the rest, so it
    # lands at the end rather than taking the whole build down.
    if dt is not None:
        for i, existing in enumerate(timeline):
            edt = _as_utc(_parse_iso_safe(existing.get("ts")))
            if edt is not None and edt >= dt:
                pos = i
                break
    timeline.insert(pos, row)


def _insert_compaction_rows(timeline, compaction_records):
    """Splice compaction markers into a timeline, in place and in order."""
    for c in compaction_records:
        n = len(c["evicted"])
        text = f"{n} file(s) no longer resident" if n else "no path-scoped files were resident"
        head = " ".join(x for x in (c.get("event"), c.get("trigger")) if x)
        _insert_timeline_row(timeline, {
            "ts": c["ts"], "kind": "compaction", "label": "compaction",
            "text": f"{head} - {text}" if head else text})


def _insert_cache_break_rows(timeline, breaks):
    """Splice cache-break markers into a timeline, in place and in order."""
    for b in breaks:
        _insert_timeline_row(timeline, {
            "ts": b["ts"], "kind": "cache-break", "label": "cache break",
            "text": (f"prompt cache lost - previous request read "
                     f"{b['priorCacheRead']:,} cached tokens, this one read "
                     f"{b['cacheRead']:,} and rewrote {b['cacheCreation']:,}")})


def _breaks_within(breaks, turn):
    """Cache breaks belonging to one turn, by event range.

    Matched on the event index rather than the timestamp so a break sitting on
    a turn boundary lands in exactly one turn - two adjacent events can share a
    timestamp, and a marker shown in both turns would read as two breaks.
    """
    start, end = turn["startEventIdx"], turn["endEventIdx"]
    return [b for b in breaks if start <= b["eventIndex"] < end]


def process_session(transcript_path, args):
    """Run the full pipeline for one transcript. Returns (session_summary, per_session_data)."""
    events = load_transcript(transcript_path)
    calls = tool_calls(events)
    asst_segs = assistant_text_segments(events)
    project_dir = Path.cwd()
    # The transcript filename is the session UUID, which is also the ctxlog log
    # name. Resolved per transcript so each session reads its own log, not the
    # active one's.
    hook_facts = ctxlog_facts.load_facts(transcript_path.stem)

    # Token usage is derived once, session-wide, and sliced per turn from there:
    # deduping requests inside each turn slice would count a request twice if a
    # compaction boundary ever split one response's events across two turns.
    series = usage_series(events)
    session_usage = usage_totals(series)
    history_chars = history_chars_by_request(events, series)

    # Turns and residency are derived before the aggregate payload because the
    # aggregate prices files over the whole series, and a file evicted by a
    # compaction must stop being billed from that request on.
    compactions = ((hook_facts or {}).get("compactions") or []) + compactions_from_transcript(events)
    turns = split_into_turns(events, [c.get("ts") for c in compactions])
    nonresident_by_turn, compaction_records = compute_residency(turns, compactions, hook_facts)
    nonresident_by_request = _nonresident_by_request(series, turns, nonresident_by_turn)

    # Aggregate ("All turns") payload: keeps today's exact shape and behaviour.
    aggregate = _compute_payload(events, calls, asst_segs, args, project_dir,
                                 hook_facts=hook_facts, usage_entries=series,
                                 history_chars=history_chars,
                                 nonresident_by_request=nonresident_by_request)
    _insert_compaction_rows(aggregate["timeline"], compaction_records)
    # Detected once over the whole session: a break is a transition between two
    # consecutive requests, and a per-turn series would miss every break that
    # happens across a turn boundary.
    breaks = cache_breaks(series)
    _insert_cache_break_rows(aggregate["timeline"], breaks)
    turn_payloads = []
    for t in turns:
        e_slice, c_slice, s_slice = turn_slice(events, calls, asst_segs, t)
        p = _compute_payload(e_slice, c_slice, s_slice, args, project_dir,
                             id_prefix=f"turn{t['index']}-", hook_facts=hook_facts,
                             nonresident_paths=nonresident_by_turn.get(t["index"]),
                             usage_entries=usage_for_turn(series, t),
                             history_chars=history_chars)
        _insert_cache_break_rows(p["timeline"], _breaks_within(breaks, t))
        turn_payloads.append({
            "id": f"turn-{t['index']}",
            "index": t["index"],
            "userPrompt": p["userPrompt"] or t["userPrompt"],
            "promptPreview": p["promptPreview"] or (
                (t["userPrompt"][:140] + "…") if len(t["userPrompt"]) > 140 else t["userPrompt"]),
            "startTime": p["startTime"] or t["startTime"],
            "endTime": p["endTime"] or t["endTime"],
            "durationSec": p["durationSec"],
            "counts": p["counts"],
            "usage": usage_totals(usage_for_turn(series, t)),
            "attribution": p["attribution"],
            "contextFiles": p["contextFiles"],
            "timeline": p["timeline"],
            "fileActivity": p["fileActivity"],
        })
        # Same rule as `delivery` and `hook`: keys appear only when there is
        # something to report, so sessions without compaction serialise as before.
        if t["afterCompaction"]:
            turn_payloads[-1]["afterCompaction"] = True
            turn_payloads[-1]["nonResidentCount"] = len(nonresident_by_turn.get(t["index"]) or ())

    # Per PRD: the aggregate's per-block status must be derived from per-turn
    # statuses (combine rule), so the "All turns" view can never disagree with
    # any individual turn's verdict. We patch statuses in place on the aggregate
    # block records — the rest of the verdict object (moments, evidence, title,
    # content) keeps its session-wide assessment, which is the most informative
    # view at aggregate scope.
    if turn_payloads:
        per_block_statuses = {}
        for tp in turn_payloads:
            for f in tp["contextFiles"]:
                for b in f["blocks"]:
                    stem = re.sub(r"^turn\d+-", "", b["id"])
                    per_block_statuses.setdefault(stem, []).append(b["status"])
        for f in aggregate["contextFiles"]:
            for b in f["blocks"]:
                statuses = per_block_statuses.get(b["id"])
                if statuses:
                    b["status"] = combine_verdicts(statuses)

    # Pull aggregate values back out for the existing top-level keys.
    user_prompt = aggregate["userPrompt"] or None
    timeline = aggregate["timeline"]
    files_out = aggregate["contextFiles"]
    counts = aggregate["counts"]
    start = aggregate["startTime"]
    end = aggregate["endTime"]
    duration_sec = aggregate["durationSec"]
    trace = aggregate["trace"]
    reads_list = aggregate["fileActivity"]["reads"]
    edits_list = aggregate["fileActivity"]["edits"]

    cwd = trace["cwd"]
    branch = next((e.get("gitBranch") for e in events if e.get("gitBranch")), "")
    session_id = next((e.get("sessionId") for e in events if e.get("sessionId")), transcript_path.stem)
    version = next((e.get("version") for e in events if e.get("version")), "")

    duplicates = compute_duplicates(files_out, trace)

    summary = {
        "id": session_id,
        "path": str(transcript_path),
        "promptPreview": (user_prompt[:140] + "…") if user_prompt and len(user_prompt) > 140 else (user_prompt or ""),
        "startTime": start,
        "endTime": end,
        "durationSec": duration_sec,
        "branch": branch,
        "events": counts["events"],
        "toolCalls": counts["totalToolCalls"],
        "userMessages": counts["userMessages"],
        "filesEdited": counts["filesEdited"],
        "usage": session_usage,
        # Cheap enough for the picker; the per-file breakdown stays in per_session.
        "contextTokens": sum(f["cost"]["tokens"] for f in files_out),
    }
    per_session = {
        "session": {
            "id": session_id,
            "project": Path(cwd).name if cwd else "",
            "cwd": cwd,
            "branch": branch,
            "version": version,
            "userPrompt": user_prompt or "",
            "startTime": start,
            "endTime": end,
            "durationSec": duration_sec,
            "transcriptPath": str(transcript_path),
        },
        "counts": counts,
        "usage": session_usage,
        "usageSeries": series,
        "attribution": aggregate["attribution"],
        "contextFiles": files_out,
        "timeline": timeline,
        "fileActivity": {
            "reads": reads_list,
            "edits": edits_list,
        },
        "duplicates": duplicates,
        "turns": turn_payloads,
        "turnCount": len(turn_payloads),
    }
    summary["duplicatePairs"] = len(duplicates)
    summary["redundantPairs"] = sum(1 for d in duplicates if d["classification"] == "redundant")
    summary["duplicateTokens"] = sum(d["tokens"] for d in duplicates)
    return summary, per_session


def build_data(cwd, sessions, per_session_data, active_id, compare=None):
    """Assemble the object baked into the page.

    The `compare` key is omitted entirely when no comparison was requested, so
    a default build serialises byte-for-byte as it did before compare existed.
    """
    data = {
        "project": {
            "cwd": cwd,
            "name": Path(cwd).name,
        },
        "sessions": sessions,
        "activeSessionId": active_id,
        "perSession": per_session_data,
    }
    if compare is not None:
        data["compare"] = compare
    return data


def select_transcripts(args):
    """Which transcripts to process, and which of them is the active one.

    Shared by the HTML build and the query path so both address exactly the
    same set of sessions: a query that could see a session the page cannot
    would print ids the page has no answer for.
    """
    if args.transcript is not None:
        if not args.transcript.exists():
            sys.exit(f"error: transcript not found: {args.transcript}")
        all_paths = [args.transcript]
        active_path = args.transcript
    else:
        all_paths = discover_all_transcripts(os.getcwd(), args.projects_dir)
        if not all_paths:
            sys.exit(f"error: no transcripts found under {args.projects_dir}/{encode_cwd_for_projects(os.getcwd())}/. "
                     f"Pass --transcript explicitly.")
        active_path = all_paths[0]
        if args.session:
            matches = [p for p in all_paths if Path(p).stem.startswith(args.session)]
            if not matches:
                sys.exit(f"error: no session id starting with `{args.session}` "
                         f"under {args.projects_dir}. Use --list to see available sessions.")
            active_path = matches[0]
        if not args.all_sessions:
            all_paths = [active_path]
        elif args.max_sessions > 0 and len(all_paths) > args.max_sessions:
            # Keep most recent N, but make sure the active session is included
            kept = list(all_paths[:args.max_sessions])
            if active_path not in kept:
                kept[-1] = active_path
            print(f"note: {len(all_paths)} sessions found; baking {len(kept)} (use --max-sessions 0 for all, or --no-all-sessions for active only)",
                  file=sys.stderr)
            all_paths = kept
    return all_paths, active_path


def bake_sessions(all_paths, active_path, args):
    """Run the pipeline over every path. Returns (sessions, per_session, active_id).

    A transcript that fails to parse is skipped with a warning rather than
    aborting the run: one unreadable session should not cost the other 19.
    """
    sessions = []
    per_session_data = {}
    active_id = None
    for path in all_paths:
        try:
            summary, data = process_session(path, args)
        except Exception as e:
            print(f"warning: skipping {path.name}: {e}", file=sys.stderr)
            continue
        sessions.append(summary)
        per_session_data[summary["id"]] = data
        if str(path) == str(active_path):
            active_id = summary["id"]
    if active_id is None and sessions:
        active_id = sessions[0]["id"]
    return sessions, per_session_data, active_id


def main():
    args = parse_args()

    if args.list:
        cmd_list(args)
        return

    if args.query:
        try:
            cmd_query(args)
        except QueryError as e:
            sys.exit(str(e))
        return

    if not args.claude_md.exists():
        sys.exit(f"error: CLAUDE.md not found: {args.claude_md}. Pass --claude-md or skip with /dev/null.")

    all_paths, active_path = select_transcripts(args)

    def compare_id(pool, prefix):
        try:
            return resolve_session_id(pool, prefix)
        except ValueError as e:
            sys.exit(f"error: --compare: {e}. Both sessions must be baked into this "
                     f"page: use --list to see what exists, --max-sessions to widen "
                     f"how many are baked, and drop --no-all-sessions.")

    if args.compare:
        # Checked against the transcript filenames (which are the session ids)
        # before anything is parsed: resolving only after the loop would make a
        # typo cost a full multi-session build before failing.
        stems = {p.stem: None for p in all_paths}
        for prefix in args.compare:
            compare_id(stems, prefix)

    sessions, per_session_data, active_id = bake_sessions(all_paths, active_path, args)

    compare = None
    if args.compare:
        # Re-resolved against what actually got baked: a session that failed to
        # process was skipped above, so the pre-check alone is not enough.
        id_a = compare_id(per_session_data, args.compare[0])
        id_b = compare_id(per_session_data, args.compare[1])
        compare = compare_sessions(per_session_data[id_a], per_session_data[id_b])

    data = build_data(os.getcwd(), sessions, per_session_data, active_id, compare=compare)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Escape sequences that would otherwise break out of the surrounding <script> tag.
    # `\/` is a valid JSON escape (for `/`), so `</` → `<\/` survives JSON.parse.
    # `\!` is NOT a valid JSON escape, so escape `<` in `<!--` via its \uXXXX form.
    payload = (json.dumps(data)
               .replace("</", "<\\/")
               .replace("<!--", "\\u003c!--"))
    html = HTML_TEMPLATE.replace("__DATA_JSON__", payload)
    args.out.write_text(html)

    print(f"Wrote {args.out}")
    print(f"Sessions: {len(sessions)} (active: {(active_id or '')[:10]})")
    for s in sessions:
        marker = "▶" if s["id"] == active_id else " "
        when = (s["startTime"] or "")[:16].replace("T", " ")
        print(f"  {marker} {s['id'][:10]}  {when}  {_fmt_dur(s['durationSec']):>7s}  "
              f"{s['events']:>4d} ev  {s['toolCalls']:>3d} tools  {s['promptPreview'][:60]}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Agent Context IDE — Real Session</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d1117; --panel: #161b22; --panel-2: #1c2128; --border: #30363d;
    --text: #c9d1d9; --text-dim: #8b949e; --text-bright: #f0f6fc;
    --accent: #58a6ff; --green: #3fb950; --amber: #d29922; --red: #f85149;
    --gray: #6e7681; --purple: #bc8cff;
    /* Muted twin of --green: weak evidence must not read as confident use. */
    --green-soft: #6d9773;
  }
  html, body { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg); color: var(--text); font-size: 13px; line-height: 1.5; overflow: hidden;
  }
  header {
    height: 50px; background: var(--panel); border-bottom: 1px solid var(--border);
    display: flex; align-items: center; padding: 0 20px; gap: 30px;
  }
  header h1 { font-size: 14px; font-weight: 600; color: var(--text-bright); letter-spacing: 0.5px; }
  .badge {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 12px;
    padding: 2px 8px; font-size: 11px; color: var(--text-dim); margin-left: 8px; font-weight: 400;
  }
  .badge.real { color: var(--green); border-color: var(--green); }
  nav { display: flex; gap: 4px; }
  nav button {
    background: transparent; border: none; color: var(--text-dim);
    padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; font-family: inherit;
  }
  nav button:hover { background: var(--panel-2); color: var(--text); }
  nav button.active { background: var(--panel-2); color: var(--text-bright); }
  main { height: calc(100vh - 50px); display: flex; }
  .view { flex: 1; display: flex; height: 100%; }
  .view[hidden] { display: none; }

  .file-tree { width: 260px; background: var(--panel); border-right: 1px solid var(--border); padding: 14px; overflow-y: auto; }
  .file-tree h3 { font-size: 10px; text-transform: uppercase; color: var(--text-dim); letter-spacing: 0.5px; margin-bottom: 8px; }
  .session-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin-bottom: 14px; font-size: 11px; }
  .session-card .row { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0; color: var(--text-dim); }
  .session-card .row strong { color: var(--text); font-family: monospace; font-size: 10px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .blocks-pane { flex: 1; overflow-y: auto; padding: 22px; }
  .pane-header { margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
  .pane-header h2 { font-size: 16px; color: var(--text-bright); margin-bottom: 4px; }
  .pane-header .subtitle { font-size: 12px; color: var(--text-dim); }

  .run-bar { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-bottom: 14px; }
  .run-bar .label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .run-bar .prompt { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; color: var(--text-bright); word-break: break-word; }
  .run-bar .meta { font-size: 11px; color: var(--text-dim); margin-top: 10px; display: flex; gap: 14px; flex-wrap: wrap; }
  .run-bar .meta span { white-space: nowrap; }

  .summary-strip { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; margin-bottom: 16px; }
  .stat { background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
  .stat .v { font-size: 18px; font-weight: 600; color: var(--text-bright); font-family: monospace; }
  .stat .k { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }

  .block { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; margin-bottom: 10px; cursor: pointer; transition: all 0.12s; }
  .block:hover { border-color: var(--accent); }
  .block.selected { border-color: var(--accent); background: var(--panel-2); }

  .block-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
  .block-title { color: var(--text-bright); font-weight: 600; font-size: 13px; }
  .block-type { font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 6px; border-radius: 3px; font-weight: 700; }
  .block-type.rule { background: rgba(188,140,255,0.15); color: var(--purple); }
  .block-type.skill { background: rgba(63,185,80,0.15); color: var(--green); }
  .block-type.overview { background: rgba(210,153,34,0.15); color: var(--amber); }
  .block-type.instruction { background: rgba(110,118,129,0.2); color: var(--gray); }
  .block-type.reference { background: rgba(88,166,255,0.15); color: var(--accent); }

  .block-status { margin-left: auto; display: flex; align-items: center; gap: 6px; font-size: 11px; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; }
  .status-used .status-dot { background: var(--green); }
  .status-used { color: var(--green); }
  .status-used-partial .status-dot { background: var(--amber); }
  .status-used-partial { color: var(--amber); }
  .status-possibly-referenced .status-dot { background: var(--green-soft); opacity: 0.7; }
  .status-possibly-referenced { color: var(--green-soft); }
  .status-ignored .status-dot { background: var(--red); }
  .status-ignored { color: var(--red); }
  .status-unused .status-dot { background: var(--gray); }
  .status-unused { color: var(--gray); }
  .status-dormant .status-dot { background: var(--gray); border: 1px dashed var(--text-dim); width: 10px; height: 10px; }
  .status-dormant { color: var(--text-dim); }
  .status-not-loaded .status-dot { background: transparent; border: 1px dashed var(--gray); }
  .status-not-loaded { color: var(--gray); opacity: 0.65; }
  /* Distinct from the greys of the other NOT-USED statuses on purpose: "never
     arrived" is a different finding from "arrived and was ignored". */
  .status-undelivered .status-dot { background: var(--purple); }
  .status-undelivered { color: var(--purple); }
  .file-tree-item { font-family:monospace;font-size:11px;color:var(--text);padding:5px 8px;cursor:pointer;border-radius:4px;margin-bottom:3px;display:flex;justify-content:space-between;align-items:center;gap:6px; }
  .file-tree-item:hover { background: var(--panel-2); }
  .file-tree-item.active { background: var(--panel-2); color: var(--text-bright); }
  .file-tree-item.not-loaded { opacity: 0.55; }
  .file-tree-item .kind-tag { font-size: 9px; text-transform: uppercase; letter-spacing: 0.4px; padding: 1px 5px; border-radius: 3px; background: var(--panel); color: var(--text-dim); }
  .file-tree-item .kind-tag.global { color: var(--accent); }
  .file-tree-item .kind-tag.project { color: var(--green); }
  .file-tree-item .kind-tag.skill { color: var(--purple); }
  .file-tree-item .kind-tag.command { color: var(--amber); }
  .file-tree-item .kind-tag.agent { color: #ff7b72; }
  .file-tree-item .kind-tag.rule { color: var(--green); }
  .file-tree-item .kind-tag.reference { color: var(--text-dim); }
  .file-tree-item .kind-tag.read { color: #79c0ff; }       /* cyan */
  .file-tree-item .kind-tag.preloaded { color: #79c0ff; }
  .file-tree-item .kind-tag.attached { color: #ffa657; }   /* user-attached */

  /* Rule-check states. A red card is reserved for a violation that a reviewed
     checks file produced and that carries a citable span; everything softer
     must look softer, because a false accusation is the worst failure here. */
  .rulecheck { border-radius: 6px; border: 1px solid var(--border); padding: 10px 12px; margin-bottom: 8px; background: var(--panel-2); }
  .rulecheck .rc-state { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }
  .rulecheck .rc-note { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
  .rulecheck .rc-span { font-family: monospace; font-size: 11px; margin-top: 6px; padding: 6px 8px; border-radius: 4px; background: var(--panel); border-left: 3px solid var(--border); white-space: pre-wrap; word-break: break-all; }
  .rulecheck .rc-span .rc-path { color: var(--text-dim); }
  .rc-violated { border-color: var(--red); }
  .rc-violated .rc-state { color: var(--red); }
  .rc-violated .rc-span { border-left-color: var(--red); }
  .rc-acknowledged { border-color: var(--amber); }
  .rc-acknowledged .rc-state { color: var(--amber); }
  .rc-acknowledged .rc-span { border-left-color: var(--amber); }
  .rc-unclear .rc-state { color: var(--amber); }
  .rc-clear .rc-state { color: var(--green); }
  .rc-not-exercised .rc-state, .rc-not-checkable .rc-state { color: var(--text-dim); }
  .rc-not-checkable { border-style: dashed; }
  .rc-conf { font-size: 9px; text-transform: uppercase; letter-spacing: 0.4px; border: 1px solid var(--border); color: var(--text-dim); padding: 0 4px; border-radius: 3px; margin-left: 6px; vertical-align: middle; }

  .drift-badge {
    display: inline-block; font-size: 9px; color: var(--amber);
    border: 1px solid var(--amber); padding: 0 4px; border-radius: 3px;
    margin-left: 4px; font-family: monospace; vertical-align: middle;
    cursor: help;
  }
  .source-tag {
    display: inline-block; font-size: 9px; color: var(--text-dim);
    margin-left: 4px; font-family: monospace; opacity: 0.7;
  }
  .cost-tag {
    font-family: monospace; font-size: 10px; color: var(--text-dim);
    flex-shrink: 0; margin-left: 6px; cursor: help;
  }
  .est-badge {
    display: inline-block; font-size: 9px; color: var(--text-dim);
    border: 1px solid var(--border); padding: 0 4px; border-radius: 3px;
    margin-left: 6px; font-family: monospace; vertical-align: middle; cursor: help;
  }

  /* Loaded indicator dot, left of the kind badge */
  .loaded-dot { display:inline-block; width:8px; height:8px; border-radius:50%;
    margin-right: 6px; vertical-align: middle; flex-shrink: 0; }
  .loaded-dot.on  { background: var(--green); box-shadow: 0 0 0 1px var(--green); }
  .loaded-dot.off { background: transparent; box-shadow: inset 0 0 0 1px var(--gray); }

  /* Group subheaders inside file tree */
  .file-tree-group {
    font-size: 9px; text-transform: uppercase; letter-spacing: 0.6px;
    color: var(--text-dim); margin: 14px 0 4px; padding: 0 4px;
    display: flex; justify-content: space-between; align-items: baseline;
  }
  .file-tree-group .count { font-family: monospace; font-size: 10px; color: var(--text-dim); }
  .file-tree-group:first-of-type { margin-top: 6px; }

  /* Load filter chips */
  .load-filter {
    display: flex; gap: 4px; margin: 6px 0 10px;
    background: var(--panel-2); border: 1px solid var(--border);
    border-radius: 6px; padding: 3px;
  }
  .load-filter button {
    flex: 1; background: transparent; border: none; cursor: pointer;
    color: var(--text-dim); font-size: 11px; font-family: inherit;
    padding: 4px 6px; border-radius: 4px;
    display: flex; align-items: center; justify-content: center; gap: 4px;
  }
  .load-filter button:hover { color: var(--text); }
  .load-filter button.active {
    background: var(--panel); color: var(--text-bright);
    box-shadow: 0 0 0 1px var(--border);
  }
  .load-filter button .loaded-dot { width: 7px; height: 7px; margin-right: 2px; }

  .status-chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 14px; }
  .status-chips .caption { font-size: 11px; color: var(--text-dim); }
  .status-chip {
    display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
    font-family: inherit; font-size: 11px; padding: 3px 9px; border-radius: 999px;
    background: var(--panel-2); border: 1px solid var(--border);
  }
  .status-chip:hover { border-color: var(--text-dim); }
  .status-chip.active { border-color: currentColor; background: var(--panel); }
  .file-section-header { font-family:monospace; font-size:11px; color:var(--text-dim); margin: 18px 0 6px; padding-bottom: 4px; border-bottom: 1px dashed var(--border); display:flex; justify-content:space-between; }
  .file-section-header .name { color: var(--text-bright); }
  .file-hook-note { font-size: 11px; color: var(--text-dim); margin: -2px 0 8px; }
  .file-hook-note code { font-family: monospace; color: var(--text-bright); }

  /* Help tooltip */
  .help-trigger {
    display: inline-flex; align-items: center; justify-content: center;
    width: 14px; height: 14px; border-radius: 50%; background: var(--panel-2);
    border: 1px solid var(--border); color: var(--text-dim);
    font-size: 9px; font-weight: 700; cursor: help; margin-left: 4px;
    user-select: none; vertical-align: middle;
  }
  .help-trigger:hover { color: var(--accent); border-color: var(--accent); }
  .help-popover {
    position: absolute; z-index: 100; background: var(--panel-2);
    border: 1px solid var(--border); border-radius: 6px;
    padding: 12px 14px; max-width: 320px; font-size: 11px;
    color: var(--text); line-height: 1.55; text-transform: none; letter-spacing: 0;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  }
  .help-popover h5 { font-size: 11px; color: var(--text-bright); margin: 8px 0 3px; font-weight: 600; }
  .help-popover h5:first-child { margin-top: 0; }
  .help-popover code { font-size: 10px; }
  .help-popover .kind-tag { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: var(--panel); margin-right: 4px; }
  .help-popover ul { padding-left: 16px; margin: 3px 0; }
  .help-popover li { margin-bottom: 2px; }
  .help-popover .close { float: right; cursor: pointer; color: var(--text-dim); font-size: 14px; line-height: 1; }
  .help-popover .close:hover { color: var(--text-bright); }

  /* Session picker */
  .session-picker { display:flex; align-items:center; gap:10px; margin-left:auto; }
  .session-picker select { background: var(--panel-2); color: var(--text-bright); border: 1px solid var(--border); border-radius: 6px; padding: 5px 10px; font-family: monospace; font-size: 11px; cursor: pointer; max-width: 380px; }
  .session-picker select:hover { border-color: var(--accent); }
  .session-picker .count { font-size: 11px; color: var(--text-dim); }
  .turn-bar { display:flex; align-items:center; gap:10px; padding: 6px 18px; border-bottom: 1px solid var(--border); background: var(--panel); font-size: 11px; }
  .turn-bar .label { color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; font-size: 10px; }
  .turn-bar select { background: var(--panel-2); color: var(--text-bright); border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; font-family: monospace; font-size: 11px; cursor: pointer; max-width: 540px; }
  .turn-bar select:hover { border-color: var(--accent); }
  .turn-bar button { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 3px 8px; font-family: monospace; font-size: 11px; cursor: pointer; }
  .turn-bar button:hover { border-color: var(--accent); }
  .turn-bar .hint { color: var(--text-dim); font-size: 10px; }
  .turn-bar.hidden { display: none; }
  .scope-badge { display: inline-block; padding: 2px 7px; border-radius: 10px; background: var(--panel-2); border: 1px solid var(--border); font-size: 10px; color: var(--text-dim); font-family: monospace; letter-spacing: 0.3px; }
  .scope-badge.turn { color: var(--accent); border-color: var(--accent); }
  .block .scope-badge { margin-left: 6px; }
  .session-list { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px; margin-bottom: 14px; max-height: 220px; overflow-y: auto; }
  .session-row { display: grid; grid-template-columns: 90px 110px 60px 50px 1fr; gap: 10px; padding: 6px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; align-items: center; }
  .session-row:hover { background: var(--panel-2); }
  .session-row.active { background: var(--panel-2); border-left: 3px solid var(--accent); padding-left: 7px; }
  .session-row .id { font-family: monospace; color: var(--text-bright); }
  .session-row .when { color: var(--text-dim); font-family: monospace; }
  .session-row .dur, .session-row .tools { font-family: monospace; color: var(--text); text-align: right; }
  .session-row .prompt { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .session-list-toggle { font-size: 11px; color: var(--accent); cursor: pointer; user-select: none; padding: 6px 0; }
  .session-list-toggle:hover { text-decoration: underline; }

  .block-content { font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 12px; color: var(--text); white-space: pre-wrap; word-break: break-word; max-height: 80px; overflow: hidden; position: relative; }
  .block.selected .block-content { max-height: none; }
  .block-content::after { content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 24px; background: linear-gradient(transparent, var(--panel)); pointer-events: none; }
  .block.selected .block-content::after { display: none; }

  .detail-pane { width: 420px; background: var(--panel); border-left: 1px solid var(--border); overflow-y: auto; padding: 22px; }
  .detail-pane.empty { display: flex; align-items: center; justify-content: center; color: var(--text-dim); font-size: 12px; text-align: center; padding: 40px; }
  .detail-section { margin-bottom: 22px; }
  .detail-section h4 { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 8px; }
  .detail-section .reason { background: var(--panel-2); padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 1.55; border-left: 3px solid var(--border); }
  .detail-section .reason.used { border-left-color: var(--green); }
  .detail-section .reason.used-partial { border-left-color: var(--amber); }
  .detail-section .reason.possibly-referenced { border-left-color: var(--green-soft); }
  .detail-section .reason.ignored { border-left-color: var(--red); }
  .detail-section .reason.dormant { border-left-color: var(--text-dim); }
  .detail-section .reason.not-loaded { border-left-color: var(--gray); }
  .detail-section .reason.undelivered { border-left-color: var(--purple); }
  .ev-card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
  .ev-card .label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px; }
  .ev-card .text { font-family: monospace; font-size: 11px; color: var(--text); word-break: break-word; white-space: pre-wrap; max-height: 220px; overflow-y: auto; }
  .ev-card.excerpt-bash { border-left: 3px solid var(--green); }
  .ev-card.excerpt-user-prompt { border-left: 3px solid var(--accent); }
  .ev-card.excerpt-assistant, .ev-card.excerpt-assistant-final { border-left: 3px solid var(--purple); }
  .ev-card.excerpt-violation { border-left: 3px solid var(--red); }
  .ev-card.excerpt-cwd { border-left: 3px solid var(--text-dim); }

  /* Causal timeline (moments) */
  .moments { position: relative; padding-left: 18px; }
  .moments::before {
    content: ''; position: absolute; left: 6px; top: 4px; bottom: 4px;
    width: 2px; background: var(--border);
  }
  .moment {
    position: relative; padding: 8px 12px; margin-bottom: 8px;
    background: var(--panel-2); border: 1px solid var(--border);
    border-radius: 6px;
  }
  .moment::before {
    content: ''; position: absolute; left: -16px; top: 14px;
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--gray); box-shadow: 0 0 0 2px var(--panel);
  }
  .moment.kind-trigger::before { background: var(--accent); }
  .moment.kind-intent::before  { background: var(--purple); }
  .moment.kind-action::before  { background: var(--green); }
  .moment.kind-condition::before, .moment.kind-applicability::before { background: var(--amber); }
  .moment.kind-compliance::before { background: var(--green); }
  .moment.kind-violation::before  { background: var(--red); }
  .moment.kind-non-event::before  { background: var(--gray); border: 1px dashed var(--text-dim); }
  .moment.kind-omission::before   { background: transparent; box-shadow: 0 0 0 1px var(--gray) inset, 0 0 0 2px var(--panel); }

  /* Encrypted-thinking gap: distinct purple-tinted card with lock icon */
  .moment.kind-thinking-gap {
    background: rgba(188, 140, 255, 0.08);
    border: 1px dashed rgba(188, 140, 255, 0.45);
    border-left: 3px solid var(--purple);
    padding: 8px 12px; margin-bottom: 8px;
  }
  .moment.kind-thinking-gap::before {
    content: '🔒';
    background: transparent; box-shadow: none;
    width: auto; height: auto;
    left: -22px; top: 8px;
    font-size: 12px;
    border-radius: 0;
  }
  .moment.kind-thinking-gap .moment-kind {
    background: rgba(188, 140, 255, 0.18);
    color: var(--purple);
  }
  .moment.kind-thinking-gap .moment-label {
    color: var(--text-bright);
    font-weight: 500;
  }
  .moment.kind-thinking-gap .moment-text { display: none; }
  .moment.verdict-no { border-left: 3px solid var(--red); }
  .moment.verdict-yes { border-left: 3px solid var(--green); }
  .moment.kind-non-event { border-left: 3px solid var(--text-dim); opacity: 0.9; }
  .moment.kind-intent { border-left: 3px solid var(--purple); }
  .moment.kind-action { border-left: 3px solid var(--green); }
  .moment.kind-condition, .moment.kind-applicability { border-left: 3px solid var(--amber); }

  .moment-head {
    display: flex; align-items: center; gap: 8px;
    font-size: 11px; margin-bottom: 4px;
  }
  .moment-time {
    font-family: monospace; font-size: 10px; color: var(--text-dim);
    min-width: 64px;
  }
  .moment-kind {
    font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px;
    font-weight: 700; padding: 2px 6px; border-radius: 3px;
    background: var(--panel); color: var(--text-dim);
  }
  .moment.kind-trigger .moment-kind     { color: var(--accent); }
  .moment.kind-intent .moment-kind      { color: var(--purple); }
  .moment.kind-action .moment-kind      { color: var(--green); }
  .moment.kind-condition .moment-kind,
  .moment.kind-applicability .moment-kind { color: var(--amber); }
  .moment.kind-compliance .moment-kind  { color: var(--green); }
  .moment.kind-violation .moment-kind   { color: var(--red); }
  .moment.kind-non-event .moment-kind   { color: var(--gray); }
  .moment-verdict { font-size: 12px; font-weight: 700; }
  .moment-verdict.yes { color: var(--green); }
  .moment-verdict.no  { color: var(--red); }
  .moment-label { color: var(--text); flex: 1; min-width: 0; word-break: break-word; }
  .moment-text {
    font-family: 'SF Mono', Menlo, monospace; font-size: 11px;
    color: var(--text); white-space: pre-wrap; word-break: break-word;
    background: var(--panel); padding: 6px 8px; border-radius: 4px;
    margin-top: 4px; max-height: 200px; overflow-y: auto;
  }

  /* Near-duplicate cards (inline + tab) */
  .dup-card {
    background: var(--panel-2); border: 1px solid var(--border);
    border-left: 3px solid var(--amber); border-radius: 6px;
    padding: 10px 12px; margin-bottom: 8px;
  }
  .dup-card.classification-redundant { border-left-color: var(--red); }
  .dup-card.classification-referenced { border-left-color: var(--amber); }
  .dup-card.classification-not-loaded { border-left-color: var(--gray); opacity: 0.7; }
  .dup-card .dup-head {
    display: flex; align-items: center; gap: 8px;
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px;
    color: var(--text-dim); margin-bottom: 6px;
  }
  .dup-card .dup-similarity { font-family: monospace; font-size: 11px; color: var(--text-bright); }
  .dup-card .dup-tokens { font-family: monospace; color: var(--text-dim); }
  .dup-card .dup-status { padding: 1px 6px; border-radius: 3px; font-weight: 700; }
  .dup-card .dup-status.classification-redundant { background: rgba(248,81,73,0.15); color: var(--red); }
  .dup-card .dup-status.classification-referenced { background: rgba(210,153,34,0.15); color: var(--amber); }
  .dup-card .dup-status.classification-not-loaded { background: var(--panel); color: var(--text-dim); }
  .dup-card .dup-target {
    font-family: monospace; font-size: 12px; color: var(--text-bright);
    margin-bottom: 4px; word-break: break-word;
  }
  .dup-card .dup-target .file-path { color: var(--text-dim); font-size: 11px; }
  .dup-card .dup-shared {
    font-family: monospace; font-size: 11px; color: var(--text);
    background: var(--panel); padding: 4px 6px; border-radius: 3px; margin-top: 4px;
  }
  .dup-card .dup-shared .label { color: var(--text-dim); font-size: 9px; text-transform: uppercase; }
  .dup-card .dup-open {
    margin-top: 8px; display: inline-block; cursor: pointer;
    background: var(--panel); border: 1px solid var(--border);
    color: var(--accent); padding: 4px 10px; border-radius: 4px;
    font-size: 11px; user-select: none;
  }
  .dup-card .dup-open:hover { border-color: var(--accent); background: var(--panel-2); }

  /* Duplications tab */
  /* Compare tab: behaviour diff on the left, context diff on the right */
  .cmp-pane { flex: 1; overflow-y: auto; padding: 22px; }
  .cmp-note {
    background: rgba(210,153,34,0.12); border: 1px solid var(--amber);
    border-radius: 6px; padding: 10px 14px; margin-bottom: 16px;
    font-size: 12px; color: var(--amber);
  }
  .cmp-summary {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 16px; margin-bottom: 16px; font-size: 12px; color: var(--text);
  }
  .cmp-summary strong { color: var(--text-bright); font-family: monospace; }
  .cmp-side { font-family: monospace; color: var(--text-bright); }
  .cmp-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }
  @media (max-width: 1100px) { .cmp-cols { grid-template-columns: 1fr; } }
  .cmp-cols h3 {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-dim); margin-bottom: 8px;
  }
  .cmp-table { width: 100%; border-collapse: collapse; font-size: 11px; }
  .cmp-table th, .cmp-table td {
    text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .cmp-table th { color: var(--text-dim); font-weight: 600; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.4px; }
  .cmp-table td.cmp-cell { font-family: monospace; color: var(--text); word-break: break-word; }
  .cmp-table td.cmp-cell .cmp-detail { color: var(--text-dim); display: block; font-size: 10px; }
  .cmp-table td.cmp-empty { color: var(--gray); }
  .cmp-table td.cmp-mark { width: 68px; font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.4px; font-weight: 700; }
  .cmp-row.kind-match td.cmp-mark { color: var(--text-dim); font-weight: 400; }
  .cmp-row.kind-added td.cmp-mark { color: var(--green); }
  .cmp-row.kind-removed td.cmp-mark { color: var(--red); }
  .cmp-row.kind-changed td.cmp-mark { color: var(--amber); }
  .cmp-row.kind-added, .cmp-row.kind-removed, .cmp-row.kind-changed { background: var(--panel-2); }
  .cmp-file { border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px;
    margin-bottom: 8px; background: var(--panel-2); }
  .cmp-file .cmp-file-path { font-family: monospace; font-size: 12px; color: var(--text-bright);
    word-break: break-all; }
  .cmp-file .cmp-flags { font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px;
    color: var(--text-dim); margin: 4px 0 6px; }
  .cmp-file .cmp-flags .drift { color: var(--amber); font-weight: 700; }
  .cmp-blocks { list-style: none; font-size: 11px; }
  .cmp-blocks li { padding: 2px 0; font-family: monospace; word-break: break-word; }
  .cmp-blocks li .op { display: inline-block; width: 14px; font-weight: 700; }
  .cmp-blocks li.added .op { color: var(--green); }
  .cmp-blocks li.removed .op { color: var(--red); }
  .cmp-blocks li.changed .op { color: var(--amber); }
  .cmp-blocks li.verdict .op { color: var(--accent); }
  .cmp-blocks li .block-id { color: var(--text-dim); font-size: 10px; }
  .cmp-empty-note { font-size: 12px; color: var(--text-dim); }

  .dup-pane { flex: 1; overflow-y: auto; padding: 22px; }
  .dup-summary {
    background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 16px; margin-bottom: 16px; font-size: 12px; color: var(--text);
  }
  .dup-summary strong { color: var(--text-bright); font-family: monospace; }
  .dup-table {
    width: 100%; border-collapse: collapse; font-size: 12px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
    overflow: hidden;
  }
  .dup-table th, .dup-table td {
    text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  .dup-table th {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-dim); background: var(--panel-2);
  }
  .dup-table tr { cursor: pointer; }
  .dup-table tr:hover td { background: var(--panel-2); }
  .dup-table .col-sim { font-family: monospace; color: var(--text-bright); width: 70px; }
  .dup-table .col-tok { font-family: monospace; color: var(--text-dim); width: 80px; text-align: right; }
  .dup-table .col-status { width: 130px; }
  .dup-table .block-cell { font-family: monospace; }
  .dup-table .block-cell .file-path { color: var(--text-dim); font-size: 11px; display: block; }
  .dup-table .block-cell .title { color: var(--text-bright); }

  /* Timeline view */
  .timeline-pane { flex: 1; overflow-y: auto; padding: 22px; }
  .timeline-row { display: grid; grid-template-columns: 70px 110px 1fr; gap: 12px; padding: 6px 8px; border-bottom: 1px solid var(--border); font-size: 12px; align-items: start; }
  .timeline-row:hover { background: var(--panel-2); }
  .timeline-row .when { color: var(--text-dim); font-family: monospace; font-size: 10px; }
  .timeline-row .kind { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 2px 6px; border-radius: 3px; font-weight: 600; height: fit-content; text-align: center; }
  .kind-user { background: rgba(88,166,255,0.15); color: var(--accent); }
  .kind-user-command { background: rgba(88,166,255,0.25); color: var(--accent); }
  .kind-assistant-text { background: rgba(188,140,255,0.15); color: var(--purple); }
  .kind-tool-use { background: rgba(63,185,80,0.15); color: var(--green); }
  .kind-tool-result { background: rgba(110,118,129,0.2); color: var(--gray); }
  .kind-compaction { background: rgba(188,140,255,0.25); color: var(--purple); }
  .kind-cache-break { background: rgba(248,81,73,0.22); color: var(--red); }
  .timeline-row .text { font-family: monospace; font-size: 11px; word-break: break-word; white-space: pre-wrap; color: var(--text); max-height: 80px; overflow: hidden; }
  .timeline-row.expanded .text { max-height: none; }
  .timeline-filter { background: var(--panel-2); border: 1px solid var(--border); padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 11px; }
  .timeline-filter label { display: flex; gap: 4px; align-items: center; cursor: pointer; }

  /* File activity view */
  .file-pane { flex: 1; overflow-y: auto; padding: 22px; }
  .file-list { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px; margin-bottom: 16px; }
  .file-row { display: grid; grid-template-columns: 40px 1fr; gap: 10px; padding: 5px 8px; align-items: center; font-size: 12px; }
  .file-row:hover { background: var(--panel-2); border-radius: 4px; }
  .file-row .count { font-family: monospace; color: var(--text-bright); font-weight: 600; text-align: right; }
  .file-row .path { font-family: monospace; font-size: 11px; color: var(--text); word-break: break-all; }
  .file-row .path .basename { color: var(--text-bright); }
  .file-row .path .dir { color: var(--text-dim); }

  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--gray); }

  code { font-family: 'SF Mono', Menlo, monospace; font-size: 11px; background: var(--panel-2); padding: 1px 4px; border-radius: 3px; }
</style>
</head>
<body>

<header>
  <h1>Agent Context IDE <span class="badge real">real session</span></h1>
  <nav>
    <button data-view="blocks" class="active">Block Inspector</button>
    <button data-view="timeline">Run Timeline</button>
    <button data-view="files">File Activity</button>
    <button data-view="duplications">Duplications</button>
    <button data-view="compare" id="compare-tab" hidden>Compare</button>
  </nav>
  <div class="session-picker">
    <span class="count" id="session-count"></span>
    <select id="session-select"></select>
  </div>
</header>
<div class="turn-bar hidden" id="turn-bar">
  <span class="label">Turn</span>
  <select id="turn-select"></select>
  <button id="turn-prev" title="Previous turn ([)">&larr;</button>
  <button id="turn-next" title="Next turn (])">&rarr;</button>
  <span class="hint">[ / ] to step · Aggregate &amp; per-turn views</span>
</div>

<main>
  <section id="blocks-view" class="view">
    <aside class="file-tree" id="file-tree"></aside>
    <div class="blocks-pane" id="blocks-pane"></div>
    <aside class="detail-pane empty" id="detail-pane">
      <div>Click a block to see how the agent treated it in this run.</div>
    </aside>
  </section>

  <section id="timeline-view" class="view" hidden>
    <div class="timeline-pane" id="timeline-pane"></div>
  </section>

  <section id="files-view" class="view" hidden>
    <div class="file-pane" id="file-pane"></div>
  </section>

  <section id="duplications-view" class="view" hidden>
    <div class="dup-pane" id="dup-pane"></div>
  </section>

  <section id="compare-view" class="view" hidden>
    <div class="cmp-pane" id="cmp-pane"></div>
  </section>
</main>

<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
let activeSessionId = DATA.activeSessionId;
let activeTurnId = 'all';
function active() { return DATA.perSession[activeSessionId]; }

// activeTurn returns the scope-aware view used by Block Inspector, Run Timeline,
// File Activity, and the block-status totals. When `activeTurnId === 'all'`
// it returns the per-session aggregate (today's behaviour). When a specific
// turn is picked, panel-shaped fields (counts, contextFiles, timeline,
// fileActivity) come from the turn record while session metadata (id, cwd,
// branch, project, version) stays session-level. Duplicates is always
// session-scoped and reads from `active()` directly.
// Short text describing the current scope, surfaced in the run-bar and on
// each block's verdict. PRD: "I want a visible scope badge on every verdict,
// so that I cannot mistake an aggregated verdict for a turn-scoped one."
// Returns null for single-turn sessions so callers can hide the badge.
function scopeLabel() {
  const A = active();
  if ((A.turnCount || 0) <= 1) return null;
  if (activeTurnId === 'all') return `All turns (${A.turnCount})`;
  const t = (A.turns || []).find(x => x.id === activeTurnId);
  if (!t) return `All turns (${A.turnCount})`;
  return `Turn ${t.index + 1} of ${A.turnCount}`;
}

function scopeBadgeHtml(extraClass) {
  const label = scopeLabel();
  if (!label) return '';
  const turnCls = activeTurnId === 'all' ? '' : 'turn';
  return `<span class="scope-badge ${turnCls} ${extraClass||''}">${escapeHtml(label)}</span>`;
}

function activeTurn() {
  const A = active();
  if (activeTurnId === 'all' || !A.turns) return A;
  const t = A.turns.find(x => x.id === activeTurnId);
  if (!t) return A;
  return {
    session: { ...A.session,
               userPrompt: t.userPrompt,
               durationSec: t.durationSec,
               startTime: t.startTime,
               endTime: t.endTime },
    counts: t.counts,
    usage: t.usage,
    contextFiles: t.contextFiles,
    timeline: t.timeline,
    fileActivity: t.fileActivity,
    duplicates: A.duplicates,
    turns: A.turns,
    turnCount: A.turnCount,
  };
}
function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function fmtDuration(sec) {
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec/60), s = sec%60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m/60); return `${h}h ${m%60}m`;
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n < 1000) return String(n);
  if (n < 1000000) return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k';
  return (n / 1000000).toFixed(1) + 'M';
}

// Every figure here comes from the API's own `usage` reporting, never a
// char-count estimate.
function usageOf(scope) {
  return scope.usage || {requests: 0, inputTokens: 0, outputTokens: 0,
                         cacheReadTokens: 0, cacheCreationTokens: 0,
                         thinkingTokens: 0, promptTokens: 0};
}

// A file's cumulative bill: its size-proportional share of every request that
// carried it. The total being divided is the API's own figure; the division
// across files is proportional by character size.
function costOf(f) {
  return f.cost || {sentCount: 0, tokens: 0, cached: 0, fresh: 0};
}

function costTitle(c) {
  return `${c.tokens.toLocaleString()} tokens over ${c.sentCount} request${c.sentCount === 1 ? '' : 's'}`
    + ` — ${c.cached.toLocaleString()} cached, ${c.fresh.toLocaleString()} fresh.`
    + ` Share of each request's reported prompt tokens, proportional to size.`;
}

function cachedSharePct(u) {
  if (!u.promptTokens) return 0;
  return Math.round(100 * u.cacheReadTokens / u.promptTokens);
}

function fmtTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toISOString().substr(11, 8);
}

// Disjoint reads deliver several ranges; naming only the outer bounds would
// claim the unread middle was delivered.
function deliveredLinesLabel(d) {
  const ranges = (d.ranges && d.ranges.length) ? d.ranges : [[d.from, d.to]];
  return `lines ${ranges.map(r => r[0] + '–' + r[1]).join(', ')} of ${d.totalLines} delivered`;
}

let selectedBlockId = null;
let selectedFilePath = null; // null = show all
let showSessionList = false;
let loadFilter = 'all'; // 'all' | 'loaded' | 'not-loaded'
let statusFilter = null;  // null = every status; otherwise one status name

const STATUS_ORDER = ['used', 'used-partial', 'possibly-referenced', 'ignored',
                      'unused', 'dormant', 'not-loaded', 'undelivered'];
const STATUS_CHIP_LABEL = {
  'used': 'used',
  'used-partial': 'partial',
  'possibly-referenced': 'possibly referenced',
  'ignored': 'ignored',
  'unused': 'never triggered',
  'dormant': 'dormant',
  'not-loaded': 'not loaded',
  'undelivered': 'never delivered'
};

function filteredFiles() {
  const files = activeTurn().contextFiles;
  if (loadFilter === 'loaded') return files.filter(f => f.loaded);
  if (loadFilter === 'not-loaded') return files.filter(f => !f.loaded);
  return files;
}

function renderSessionPicker() {
  const sel = document.getElementById('session-select');
  const count = document.getElementById('session-count');
  count.textContent = `${DATA.sessions.length} session${DATA.sessions.length===1?'':'s'} for ${DATA.project.name}`;
  sel.innerHTML = '';
  DATA.sessions.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    const when = (s.startTime || '').slice(0, 16).replace('T', ' ');
    const prev = (s.promptPreview || '').slice(0, 60);
    const su = usageOf(s);
    opt.textContent = `${s.id.slice(0,8)} · ${when} · ${fmtDuration(s.durationSec)} · `
      + `${fmtTokens(su.promptTokens)} in / ${fmtTokens(su.outputTokens)} out · ${prev}`;
    if (s.id === activeSessionId) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.onchange = () => {
    activeSessionId = sel.value;
    selectedBlockId = null;
    selectedFilePath = null;
    activeTurnId = 'all';  // Per PRD: reset to "All turns" on session switch.
    renderTurnPicker();
    rerenderAll();
  };
}

function renderTurnPicker() {
  const bar = document.getElementById('turn-bar');
  const sel = document.getElementById('turn-select');
  const A = active();
  const turns = A.turns || [];
  // Hide chrome entirely for single-turn sessions — view stays byte-identical
  // to the pre-turn-aware UI for the simple case.
  if ((A.turnCount || turns.length) <= 1) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');
  sel.innerHTML = '';
  const optAll = document.createElement('option');
  optAll.value = 'all';
  const au = usageOf(A);
  optAll.textContent = `All turns (${A.turnCount}, aggregated) · `
    + `${fmtTokens(au.promptTokens)} in / ${fmtTokens(au.outputTokens)} out`;
  if (activeTurnId === 'all') optAll.selected = true;
  sel.appendChild(optAll);
  turns.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.id;
    const calls = t.counts && t.counts.totalToolCalls != null ? t.counts.totalToolCalls : 0;
    const tu = usageOf(t);
    const prev = (t.promptPreview || t.userPrompt || '').slice(0, 80);
    opt.textContent = `Turn ${t.index + 1} of ${A.turnCount} · ${calls} call${calls===1?'':'s'} · `
      + `${fmtTokens(tu.promptTokens)} in / ${fmtTokens(tu.outputTokens)} out · ${prev}`;
    if (t.id === activeTurnId) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.onchange = () => {
    activeTurnId = sel.value;
    selectedBlockId = null;
    selectedFilePath = null;
    rerenderAll();
  };
}

function stepTurn(direction) {
  const A = active();
  const turns = A.turns || [];
  if (turns.length <= 1) return;
  // Order: 'all', turn-0, turn-1, ..., turn-(N-1).
  const order = ['all', ...turns.map(t => t.id)];
  const cur = order.indexOf(activeTurnId);
  if (cur === -1) return;
  const next = (cur + direction + order.length) % order.length;
  activeTurnId = order[next];
  selectedBlockId = null;
  selectedFilePath = null;
  renderTurnPicker();
  rerenderAll();
}

function rerenderAll() {
  renderFileTree();
  renderBlocks();
  renderDetail(null);
  // re-render whichever view is currently visible
  if (!document.getElementById('timeline-view').hidden) renderTimeline();
  if (!document.getElementById('files-view').hidden) renderFiles();
  if (!document.getElementById('duplications-view').hidden) renderDuplications();
}

function renderFileTree() {
  const el = document.getElementById('file-tree');
  const A = activeTurn();
  const s = A.session;
  let html = `
    <h3>Session</h3>
    <div class="session-card">
      <div class="row"><span>project</span><strong title="${escapeHtml(s.cwd)}">${escapeHtml(s.project)}</strong></div>
      <div class="row"><span>branch</span><strong title="${escapeHtml(s.branch)}">${escapeHtml((s.branch||'').slice(0,28))}</strong></div>
      <div class="row"><span>session</span><strong>${escapeHtml((s.id||'').slice(0,8))}…</strong></div>
      <div class="row"><span>cli version</span><strong>${escapeHtml(s.version)}</strong></div>
      <div class="row"><span>duration</span><strong>${fmtDuration(s.durationSec)}</strong></div>
    </div>
    <h3 style="display:flex;align-items:center">
      <span>Context files</span>
      <span class="help-trigger" data-help="context-files" title="What are these files?">?</span>
    </h3>
    <div class="load-filter" id="load-filter">
      <button data-load="all" class="${loadFilter==='all'?'active':''}" title="Show all files">All</button>
      <button data-load="loaded" class="${loadFilter==='loaded'?'active':''}" title="Only files loaded into context this run">
        <span class="loaded-dot on"></span>Loaded
      </button>
      <button data-load="not-loaded" class="${loadFilter==='not-loaded'?'active':''}" title="Only files on disk but not loaded this run">
        <span class="loaded-dot off"></span>Not loaded
      </button>
    </div>
    <div class="file-tree-item ${selectedFilePath===null?'active':''}" data-file="">
      <span>📂 all files</span>
      <span style="color:var(--text-dim)">${filteredFiles().reduce((a,f)=>a+f.blocks.length,0)}</span>
    </div>
  `;

  const visible = filteredFiles();
  const groups = [
    { id: 'project', label: 'Project', files: visible.filter(f => f.group === 'project') },
    { id: 'global',  label: 'Global',  files: visible.filter(f => f.group === 'global') },
    { id: 'read',    label: 'Read this run', files: visible.filter(f => f.group === 'read') },
  ];
  groups.forEach(g => {
    if (!g.files.length) return;
    const loadedCount = g.files.filter(f => f.loaded).length;
    const groupTokens = g.files.reduce((a, f) => a + costOf(f).tokens, 0);
    html += `
      <div class="file-tree-group">
        <span>${g.label}</span>
        <span class="count">${loadedCount}/${g.files.length} loaded${groupTokens ? ' · ' + fmtTokens(groupTokens) : ''}</span>
      </div>
    `;
    g.files.forEach(f => {
      const cls = f.loaded ? '' : 'not-loaded';
      const active = selectedFilePath === f.path ? 'active' : '';
      const dotCls = f.loaded ? 'on' : 'off';
      const dotTitle = f.loaded ? 'Loaded into context this run' : 'On disk but not loaded this run';
      const drift = f.drift ? `<span class="drift-badge" title="Disk has changed since this session — content shown reflects the snapshot the agent saw.">⚠ drift</span>` : '';
      const titleAttr = `${escapeHtml(f.path)}${f.loaded?'':' (not loaded this run)'}${f.source ? ' · source: '+f.source : ''}${f.drift?' · disk drifted from session snapshot':''}`;
      const c = costOf(f);
      const costTag = c.tokens
        ? `<span class="cost-tag" title="${costTitle(c)}">${fmtTokens(c.tokens)}</span>`
        : '';
      html += `
        <div class="file-tree-item ${cls} ${active}" data-file="${escapeHtml(f.path)}" title="${titleAttr}">
          <span style="display:inline-flex;align-items:center;min-width:0">
            <span class="loaded-dot ${dotCls}" title="${dotTitle}"></span>
            <span class="kind-tag ${f.kind}">${f.kind}</span>
            <span style="margin-left:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(f.path.split('/').pop())}</span>
            ${drift}
          </span>
          <span style="display:inline-flex;align-items:center;flex-shrink:0;margin-left:6px">
            ${costTag}
            <span style="color:var(--text-dim);margin-left:6px">${f.blocks.length}</span>
          </span>
        </div>
      `;
    });
  });
  el.innerHTML = html;
  el.querySelectorAll('.file-tree-item').forEach(item => {
    item.addEventListener('click', () => {
      const fp = item.dataset.file;
      selectedFilePath = fp || null;
      renderFileTree();
      renderBlocks();
    });
  });
  el.querySelectorAll('#load-filter button').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      loadFilter = btn.dataset.load;
      // If the currently selected file is no longer visible, clear the file filter.
      if (selectedFilePath) {
        const stillVisible = filteredFiles().some(f => f.path === selectedFilePath);
        if (!stillVisible) selectedFilePath = null;
      }
      renderFileTree();
      renderBlocks();
    });
  });
  attachHelpTriggers(el);
}

const HELP_CONTENT = {
  'context-files': `
    <h5>What are these files?</h5>
    <div>Every place Claude Code pulled instructions from for this run. We read what was loaded directly from the session transcript (the harness records it as <code>attachment</code> events) — and fall back to filesystem path conventions for anything missing or in older sessions.</div>
    <h5>The kinds you'll see</h5>
    <ul>
      <li><span class="kind-tag" style="color:var(--accent)">global</span><code>~/.claude/CLAUDE.md</code> and <code>~/.claude/AGENTS.md</code></li>
      <li><span class="kind-tag" style="color:var(--green)">project</span><code>./CLAUDE.md</code>, <code>./AGENTS.md</code>, sub-directory CLAUDE.mds the harness loaded (transcript-derived)</li>
      <li><span class="kind-tag" style="color:var(--green)">rule</span>files in <code>./.claude/rules/</code></li>
      <li><span class="kind-tag" style="color:var(--purple)">skill</span><code>~/.claude/skills/</code> and <code>./.claude/skills/</code> (filtered to skills the harness's <code>skill_listing</code> actually advertised this session)</li>
      <li><span class="kind-tag" style="color:var(--amber)">command</span>slash commands from <code>~/.claude/commands/</code> and <code>./.claude/commands/</code></li>
      <li><span class="kind-tag" style="color:#ff7b72">agent</span>subagents from <code>~/.claude/agents/</code> and <code>./.claude/agents/</code></li>
      <li><span class="kind-tag" style="color:var(--text-dim)">reference</span><code>@path.md</code> files mentioned inside CLAUDE.md</li>
      <li><span class="kind-tag" style="color:#79c0ff">read</span>files the agent fetched <em>during</em> the session via the Read tool — these weren't pre-loaded but they functioned as context for at least part of the session</li>
      <li><span class="kind-tag" style="color:#79c0ff">preloaded</span>files the harness pre-attached with content (tool results, edited files etc.)</li>
      <li><span class="kind-tag" style="color:#ffa657">attached</span>files you drag-and-dropped or pasted into the chat</li>
    </ul>
    <h5>Three groups</h5>
    <div>Files are split into:
    <ul>
      <li><b>Project</b> — anything inside the current project (<code>./CLAUDE.md</code>, <code>./.claude/</code>, sub-directory CLAUDE.mds).</li>
      <li><b>Global</b> — everything in <code>~/.claude/</code>, available to every project.</li>
      <li><b>Read this run</b> — .md files the agent dynamically fetched via the Read tool during the session.</li>
    </ul>
    The header for each group shows <code>N/M loaded</code> and the group's total token cost.</div>
    <h5>The ⚠ drift badge</h5>
    <div>Means the file's current content on disk differs from the snapshot the agent saw during the session — usually because you edited it after the session ran. The block content shown reflects the snapshot the agent actually used, not the current disk state.</div>
    <h5>The dot on the left</h5>
    <div>
      <span class="loaded-dot on" style="margin-right:6px"></span>filled green = loaded into context this run<br>
      <span class="loaded-dot off" style="margin-right:6px"></span>hollow = on disk but not loaded
    </div>
    <h5>The colored badge</h5>
    <div>Marks the file's <em>source</em> — which part of the agent's context surface it belongs to.</div>
    <h5>The numbers on the right</h5>
    <div>The file's cumulative token cost, then how many blocks (H1/H2 sections) it contains. The cost is the file's size-proportional share of the prompt tokens the API reported, summed over every request that carried it — hover it for the request count and the cached/fresh split. A loaded file is resent on every request, so a rule that never fires still bills on every one of them. Click the file to filter the block list to just that file.</div>
    <h5>Why some are grayed out</h5>
    <div>Grayed = the file was on disk but <em>not loaded into context</em> for this session.
    <ul>
      <li><b>Skills</b> only load when their trigger (e.g. <code>/graphify</code>) appears in the user prompt.</li>
      <li><b>Commands</b> only load when invoked by name.</li>
      <li><b>Subagents</b> only load when an <code>Agent</code> tool call uses that subagent_type.</li>
      <li><b>Global / project CLAUDE.md / rules / @-references</b> are always loaded — they never appear grayed.</li>
    </ul>
    A grayed file means tokens spent (or not) on context that couldn't have fired this run — useful for spotting dead context.</div>
  `,
  'block': `
    <h5>The block content</h5>
    <div>The raw markdown of this section as it appears in your <code>CLAUDE.md</code>, <code>SKILL.md</code>, or other source file. No interpretation — just the literal text.</div>
    <h5>How to use it</h5>
    <div>Read this <em>before</em> trusting the verdict. Sometimes the rule is more nuanced than our heuristics capture, and you'll want to judge for yourself whether the agent really followed it.</div>
    <h5>Example</h5>
    <div>Verdict says <code>used-partial</code> on a "Copy to clipboard" rule because the agent ran <code>echo</code>. Read the block and you'll see the rule actually says <em>"never <code>echo</code> when piping to <code>pbcopy</code>"</em> — which the agent didn't actually do. The verdict is too strict; the timeline below confirms.</div>
  `,
  'rulecheck': `
    <h5>Where this comes from</h5>
    <div>A rule document can carry a <em>checks file</em> beside it (<code>&lt;doc&gt;.checks.json</code>): each prose rule compiled once, ahead of time, into a deterministic pattern with its own self-tests. This tool never asks a model anything — at build time it re-runs every check's self-tests with its own matcher and throws out any check that fails, then applies the survivors to the code the agent wrote, the commands it ran, and the paths it touched.</div>
    <h5>The states</h5>
    <ul>
      <li><b style="color:var(--red)">rule violated</b> — a check fired on written code, with the file, line and matched text cited below. Comments and string literals are stripped before any pattern runs, and the match must hold both with and without that stripping.</li>
      <li><b style="color:var(--amber)">acknowledged</b> — the same match, but the code carries a <code>ctx-allow</code> marker at the site: a deliberate, documented exception.</li>
      <li><b style="color:var(--amber)">unclear</b> — the strict and stripped views disagree (typically the only hit was inside a comment). Never counted as a violation.</li>
      <li><b style="color:var(--green)">checked, no violation</b> — checks ran over code in their scope and found nothing.</li>
      <li><b>checked nothing</b> — the session wrote none of the code this rule governs.</li>
      <li><b>not mechanically checkable</b> — the rule needs judgment, types, or whole-file context. Most rules land here, by design. It does <em>not</em> mean the rule was followed.</li>
    </ul>
    <h5>Confidence</h5>
    <div>Only a <code>high</code> or <code>medium</code> confidence violation from a reviewed checks file turns the block's verdict red. Patterns extracted mechanically from a document with no checks file are low confidence and stay a note.</div>
  `,
  'verdict': `
    <h5>The verdict</h5>
    <div>Our automatic conclusion about whether the agent followed this block this run. Evidence comes in two tiers: <em>strong</em> (a trigger the user actually typed, a path-table row whose command ran, an end-of-message rule) and <em>weak</em> (a command the block merely names, loose keyword overlap). Only strong evidence can produce a green <code>used</code>. One of:</div>
    <ul>
      <li><b style="color:var(--green)">used</b> — at least one applicable predicate fired</li>
      <li><b style="color:var(--amber)">used-partial</b> — some applicable predicates fired, others didn't</li>
      <li><b style="color:var(--green-soft)">possibly-referenced</b> — only weak evidence: the block names a command that ran, or a few of its words show up in the assistant's text. Suggestive, not proof. Never promoted to <code>used</code>.</li>
      <li><b style="color:var(--red)">ignored</b> — predicates applied but none fired (rule was relevant but skipped)</li>
      <li><b style="color:var(--text-dim)">dormant</b> — rule was loaded but no precondition was met (couldn't have fired)</li>
      <li><b style="color:var(--text-dim)">unused</b> — no predicates derivable, no keyword overlap</li>
      <li><b style="color:var(--gray)">not-loaded</b> — file wasn't in context this run (skill/command not invoked)</li>
      <li><b style="color:var(--purple)">undelivered</b> — the file was loaded but this block sat outside the delivered line range, so the model never saw it. Not the same as being ignored.</li>
    </ul>
    <h5>How to use it</h5>
    <div>The reason line tells you which predicates drove the verdict. If it surprises you, scroll to <em>How the agent ended up here</em> for the literal evidence.</div>
    <h5>Example</h5>
    <div>A rule marked <code>dormant</code> with reason <em>"No predicate's preconditions were met"</em> suggests dead context — the rule sat in your CLAUDE.md but couldn't fire this run. If it's <code>dormant</code> across many sessions, consider scoping it differently or deleting it.</div>
  `,
  'evidence': `
    <h5>Predicate evidence</h5>
    <div>Each card is one predicate we derived from the block's content, with a one-line summary of what we found in the trace. Predicates include:</div>
    <ul>
      <li><b>Command mention</b> — backticked commands like <code>\`gh\`</code>, <code>\`pbcopy\`</code></li>
      <li><b>Trigger phrase</b> — <code>Trigger: /foo</code> or <code>"When the user types /foo"</code></li>
      <li><b>Path table</b> — markdown tables routing by cwd</li>
      <li><b>End-of-message</b> — rules about how the final response should look</li>
      <li><b>Negative rule</b> — <code>"never X"</code> phrasing</li>
      <li><b>Keyword overlap</b> — fallback when no other predicate fits</li>
    </ul>
    <h5>How to use it</h5>
    <div>Skim this for a quick read of all the angles we considered. If one looks wrong (false positive), look at the timeline below to see the literal text/command that drove it.</div>
    <h5>Example</h5>
    <div>Card says <em>"<code>echo</code> ran 3× this session"</em> — that's a command-mention predicate firing. The next section will quote the actual three bash commands so you can verify they were really clipboard-related (or not).</div>
  `,
  'thinking-gap': `
    <h5>Why is the thinking content empty?</h5>
    <div>This marker means the agent ran one or more <em>extended thinking</em> blocks at this point — Claude's internal chain-of-thought reasoning. The agent did reason, but the content is not readable.</div>
    <h5>Where the content went</h5>
    <div>For Claude 4.x models (Opus 4.x, Sonnet 4.x, Haiku 4.x), Anthropic encrypts the thinking trace server-side. The transcript only stores an opaque <code>signature</code> — a tamper-proof token used to round-trip the reasoning back to the API on the next turn. The plaintext never leaves Anthropic's servers.</div>
    <h5>Why encrypted</h5>
    <ul>
      <li>Prevents distillation / scraping of reasoning traces (Anthropic IP).</li>
      <li>Tamper-detection: if you modified the signature, the API would refuse to resume.</li>
    </ul>
    <h5>Older transcripts</h5>
    <div>Claude 3.7 Sonnet and earlier returned full plaintext thinking. Claude Code stopped persisting the summary in v2.1.69+. So unless you have very old logs, every thinking block from your sessions will look like this — empty content, signature only.</div>
    <h5>What this card tells you anyway</h5>
    <div>The presence + count + duration of thinking blocks. If you see "1 encrypted thinking block, ~2s" between the prompt and the Read, it means: <em>the agent paused for ~2 seconds to reason, then went straight to the action.</em> A long thinking gap (e.g. 10+s) suggests substantial reasoning. We can't read it, but we can see it happened.</div>
    <h5>Sources</h5>
    <div><a href="https://docs.claude.com/en/docs/build-with-claude/extended-thinking" target="_blank" style="color:var(--accent)">Anthropic — Building with extended thinking</a></div>
  `,
  'duplicates-section': `
    <h5>Near-duplicate detection</h5>
    <div>This block shares substantial phrasing with one or more blocks in other files. Each card shows the partner block, similarity (containment on 3-word shingles — robust to paraphrasing and asymmetric block sizes), an estimated token cost, and a session-aware classification.</div>
    <h5>Status</h5>
    <ul>
      <li><b style="color:var(--red)">confirmed redundant</b> — both files were loaded but neither block was topically referenced in the trace, and no predicate fired. Tokens spent twice for nothing.</li>
      <li><b style="color:var(--amber)">topic referenced</b> — at least one of the two blocks had topical activity in the session. We don't claim which copy mattered — both were live in the model's context.</li>
      <li><b style="color:var(--gray)">partner not loaded</b> — the other block exists on disk but wasn't loaded this session (e.g. an inactive skill).</li>
    </ul>
    <h5>Why some pairs aren't shown</h5>
    <div>We filter: pairs from the same file, blocks under 15 words (likely registrations/headers), code-only overlap, and pairs where one file <code>@</code>-references the other.</div>
    <h5>How to use it</h5>
    <div>Click <em>Open partner block →</em> to jump to the partner. Look at both blocks' content — if they really say the same thing, consolidate. <code>confirmed redundant</code> across many sessions is the strongest signal that a duplicate is dead weight.</div>
  `,
  'duplicates-tab': `
    <h5>The Duplications tab</h5>
    <div>Project-wide list of near-duplicate block pairs across the loaded context surface for this session. Sorted by duplicated cost, then similarity — a 100% match between two files that were never sent cost nothing.</div>
    <h5>Columns</h5>
    <ul>
      <li><b>Similarity</b> — containment coefficient on 3-word shingles (0–100%). Threshold 30%. Higher means more of the shorter block's distinctive phrases appear in the longer one.</li>
      <li><b>Status</b> — see the inline help on a duplicate card for the session-aware classification.</li>
      <li><b>Duplicated</b> — the overlapping share of the cheaper side's real token cost. Each block's cost is its file's share of the tokens the API actually reported, across every request that carried it, split across the file's blocks by line count. The file total is real; the per-block split is an estimate.</li>
      <li><b>Block A / B</b> — block title, its own attributed cost, and the source file path.</li>
    </ul>
    <h5>Empty list = useful info</h5>
    <div>"No near-duplicates" tells you the loaded context surface for this session is clean of obvious redundancy at the threshold we use. Lowering the threshold or expanding the corpus would surface more, but with more noise.</div>
    <h5>Click a row</h5>
    <div>Opens the partner blocks in Block Inspector so you can inspect content side-by-side.</div>
  `,
  'moments': `
    <h5>The causal timeline</h5>
    <div>Chronological narrative of <em>what actually happened</em> with respect to this block this run. Each card is one moment with timestamp, kind, ✓/✗ verdict, and the literal trace text underneath.</div>
    <h5>Moment kinds</h5>
    <ul>
      <li><b style="color:var(--accent)">TRIGGER</b> — precondition: did the user invoke <code>/skill</code>, did cwd match the path-table, was a subagent called?</li>
      <li><b style="color:var(--amber)">CONDITION / APPLICABILITY</b> — does the rule's domain even apply this run?</li>
      <li><b style="color:var(--purple)">INTENT</b> — a sentence from the agent's text where it expresses a related decision (with causal language like "Let me…", "I'll…", "since…")</li>
      <li><b style="color:var(--green)">ACTION ✓</b> — the actual tool call that enacted the rule, with timestamp + bash description</li>
      <li><b style="color:var(--green)">COMPLIANCE ✓</b> — the outcome matches what the rule asks</li>
      <li><b style="color:var(--red)">VIOLATION ✗</b> — the rule was broken; literal violating command/text shown</li>
      <li><b style="color:var(--text-dim)">NON-EVENT</b> — nothing happened that was relevant; the popover explains <em>what would have made this fire</em></li>
    </ul>
    <h5>How to use it</h5>
    <div>This is the receipts. When the verdict surprises you, walk down the timeline to see the actual passages and tool calls that drove it. Timestamps are offsets from session start (also visible in the Run Timeline view).</div>
    <h5>Example</h5>
    <div>The <code>/graphify</code> block in CLAUDE.md shows a single <b>NON-EVENT</b>: <em>"<code>/graphify</code> not invoked this run — User prompt: 'explore files…'"</em> — that directly answers "why didn't this fire?". Whereas the <code>Copy to clipboard</code> rule shows real <b>VIOLATION</b> cards with the literal <code>echo</code> commands at exact timestamps.</div>
  `,
};

function attachHelpTriggers(scope) {
  (scope || document).querySelectorAll('.help-trigger[data-help]').forEach(t => {
    if (t.dataset.bound) return;
    t.dataset.bound = '1';
    t.addEventListener('click', toggleHelpPopover);
  });
}

function toggleHelpPopover(e) {
  e.stopPropagation();
  const existing = document.getElementById('help-popover');
  const triggerKey = e.currentTarget.dataset.help;
  if (existing) {
    const wasFor = existing.dataset.for;
    existing.remove();
    if (wasFor === triggerKey) return;
  }
  const content = HELP_CONTENT[triggerKey];
  if (!content) return;
  const trigger = e.currentTarget;
  const rect = trigger.getBoundingClientRect();
  const pop = document.createElement('div');
  pop.id = 'help-popover';
  pop.dataset.for = triggerKey;
  pop.className = 'help-popover';
  // Anchor: prefer right-aligning to viewport so popover doesn't overflow
  const popWidth = 340;
  let left = rect.left;
  if (left + popWidth > window.innerWidth - 12) {
    left = Math.max(12, window.innerWidth - popWidth - 12);
  }
  pop.style.left = left + 'px';
  pop.style.top = (rect.bottom + 6) + 'px';
  pop.innerHTML = `<span class="close">×</span>${content}`;
  document.body.appendChild(pop);
  setTimeout(() => {
    document.addEventListener('click', dismissHelpPopover, { once: true });
  }, 0);
  pop.querySelector('.close').addEventListener('click', (ev) => {
    ev.stopPropagation();
    pop.remove();
  });
}

function dismissHelpPopover(e) {
  const pop = document.getElementById('help-popover');
  if (pop && !pop.contains(e.target)) pop.remove();
}

const RULECHECK_LABEL = {
  'violated': 'rule violated',
  'acknowledged': 'violation acknowledged in the code',
  'unclear': 'unclear — could not be confirmed',
  'clear': 'checked, no violation found',
  'not-exercised': 'checked nothing — the session wrote none of the code this rule governs',
  'not-checkable': 'not mechanically checkable'
};

// A rule's verdict comes from a checks file authored beside the rule document
// and re-validated against its own self-tests at build time. Anything that is
// not a confirmed, citable violation must read as exactly that: a rule we
// could not check is never shown as one that was followed.
function renderRuleCheck(rc) {
  const label = RULECHECK_LABEL[rc.state] || rc.state;
  const conf = `<span class="rc-conf" title="Confidence of the check that produced this.">${escapeHtml(rc.confidence)} confidence</span>`;
  let inner = `<div class="rc-state">${escapeHtml(label)}${rc.state === 'not-checkable' ? '' : conf}</div>`;
  if (rc.source === 'fallback') {
    inner += `<div class="rc-note">No checks file beside this document — these patterns were extracted mechanically from the rule's own backticked identifiers, so they are low confidence and never mark the block as violated.</div>`;
  }
  (rc.findings || []).forEach(f => {
    const verb = f.state === 'violated' ? 'fired' : f.state === 'acknowledged' ? 'fired, suppressed at the site' : 'candidate, not confirmed';
    inner += `<div class="rc-note"><code>${escapeHtml(f.checkId)}</code> ${escapeHtml(verb)}${f.message ? ' — ' + escapeHtml(f.message) : ''}</div>
      <div class="rc-span"><span class="rc-path">${escapeHtml(f.path)}:${f.line}</span>  ${escapeHtml(f.match)}</div>`;
  });
  (rc.notCheckable || []).forEach(nc => {
    inner += `<div class="rc-note">${escapeHtml(nc.ruleRef || '')}${nc.ruleRef ? ' — ' : ''}${escapeHtml(nc.why || '')}</div>`;
  });
  (rc.stale || []).forEach(st => {
    inner += `<div class="rc-note"><code>${escapeHtml(st.id)}</code> skipped — ${escapeHtml(st.why)}</div>`;
  });
  return `<div class="detail-section">
    <h4 style="display:flex;align-items:center">
      <span>Rule check</span>
      <span class="help-trigger" data-help="rulecheck" title="Where does this come from?">?</span>
    </h4>
    <div class="rulecheck rc-${escapeHtml(rc.state)}">${inner}</div>
  </div>`;
}

function renderBlocks() {
  const el = document.getElementById('blocks-pane');
  const A = activeTurn();
  const c = A.counts;
  const u = usageOf(A);
  const visibleFiles = filteredFiles();
  const filteredFilesList = selectedFilePath
    ? visibleFiles.filter(f => f.path === selectedFilePath)
    : visibleFiles;
  const allBlocks = filteredFilesList.flatMap(f => f.blocks);
  const statusCounts = {};
  STATUS_ORDER.forEach(st => { statusCounts[st] = allBlocks.filter(b => b.status === st).length; });

  let html = `
    <div class="pane-header">
      <h2>Your CLAUDE.md, evaluated against this run</h2>
      <div class="subtitle">Real data from <code>${escapeHtml(A.session.id)}</code> · click a block for the trace evidence</div>
    </div>
    <div class="run-bar">
      <div class="label">User prompt ${scopeBadgeHtml()}</div>
      <div class="prompt">${escapeHtml(A.session.userPrompt || '(no user prompt — likely a /clear or system-init session)')}</div>
      <div class="meta">
        <span>📁 ${escapeHtml(A.session.cwd)}</span>
        <span>🌿 ${escapeHtml(A.session.branch || 'no branch')}</span>
        <span>⏱ ${fmtDuration(A.session.durationSec)}</span>
      </div>
    </div>
    <div class="summary-strip">
      <div class="stat"><div class="v">${c.events}</div><div class="k">events</div></div>
      <div class="stat"><div class="v">${c.assistantMessages}</div><div class="k">assistant turns</div></div>
      <div class="stat"><div class="v">${c.totalToolCalls}</div><div class="k">tool calls</div></div>
      <div class="stat"><div class="v">${c.filesRead}</div><div class="k">files read</div></div>
      <div class="stat"><div class="v">${c.filesEdited}</div><div class="k">files edited</div></div>
      <div class="stat" title="Prompt tokens actually reported by the API: fresh input + cache reads + cache writes, over ${u.requests} request${u.requests===1?'':'s'}">
        <div class="v">${fmtTokens(u.promptTokens)}</div>
        <div class="k">tokens in · ${cachedSharePct(u)}% cached</div>
      </div>
      <div class="stat" title="Output tokens reported by the API${u.thinkingTokens ? `, including ${u.thinkingTokens.toLocaleString()} thinking tokens` : ''}">
        <div class="v">${fmtTokens(u.outputTokens)}</div>
        <div class="k">tokens out</div>
      </div>
    </div>
    <div class="status-chips">
      <span class="caption">Block status summary:</span>
      ${statusFilter ? `<button class="status-chip" data-status="">clear filter</button>` : ''}
      ${STATUS_ORDER.filter(st => statusCounts[st] > 0).map(st => `
        <button class="status-chip status-${st} ${statusFilter === st ? 'active' : ''}" data-status="${st}"
                title="Show only blocks with status ${st}">
          <span class="status-dot"></span>${statusCounts[st]} ${STATUS_CHIP_LABEL[st]}
        </button>`).join('')}
    </div>
  `;

  // In per-turn scope, "unused" / "dormant" mean the block was loaded but
  // not referenced *in this turn* — the same block may have been used in a
  // different turn. Relabel so users don't mistake a per-turn cold reading
  // for a session-wide "never triggered" verdict.
  const inTurn = activeTurnId !== 'all' && (active().turnCount || 0) > 1;
  const statusLabel = {
    'used': 'used',
    'used-partial': 'partial compliance',
    'possibly-referenced': 'possibly referenced — weak evidence',
    'ignored': 'rule applied but ignored',
    'unused': inTurn ? 'loaded — not referenced in this turn' : 'never triggered',
    'dormant': inTurn ? 'loaded — preconditions unmet this turn' : 'dormant — preconditions unmet',
    'not-loaded': 'not loaded into context',
    'undelivered': 'never reached the model — file truncated'
  };

  // Plain-English "why is this file here", from the harness's own load record.
  function hookNote(f) {
    if (!f.hook) return '';
    const h = f.hook;
    const code = s => `<code>${escapeHtml(s)}</code>`;
    const globs = Array.isArray(h.globs) ? h.globs.join(', ') : h.globs;
    let text;
    if (h.loadReason === 'path_glob_match') {
      text = h.triggerFile
        ? `This rule loaded because Claude touched ${code(h.triggerFile)}`
        : (globs ? `This rule loaded because a file matching ${code(globs)} was touched`
                 : 'This rule loaded because a file it watches was touched');
    } else if (h.loadReason === 'session_start') {
      text = 'Loaded at session start';
    } else if (h.loadReason === 'nested_traversal') {
      text = h.triggerFile
        ? `Loaded on the way to ${code(h.triggerFile)}`
        : 'Loaded while walking the directory tree';
    } else if (h.loadReason === 'include') {
      text = 'Pulled in by another instruction file';
    } else if (h.loadReason === 'compact') {
      text = 'Reloaded after the context was compacted';
    } else if (h.loadReason) {
      text = `Loaded (${escapeHtml(h.loadReason)})`;
    } else {
      text = 'Recorded as loaded by the harness';
    }
    if (h.memoryType) text += ` · ${escapeHtml(h.memoryType)} memory`;
    return `<div class="file-hook-note">${text}</div>`;
  }

  filteredFilesList.forEach(f => {
    const blocks = statusFilter ? f.blocks.filter(b => b.status === statusFilter) : f.blocks;
    if (!blocks.length) return;
    if (filteredFilesList.length > 1 || !selectedFilePath) {
      const notLoadedHint = f.loaded ? '' : (
        f.kind === 'skill'   ? ' · skill not invoked' :
        f.kind === 'command' ? ' · command not invoked' :
        f.kind === 'agent'   ? ' · subagent not used' :
        f.kind === 'rule'    ? ' · rule never loaded this session' : ' · not loaded'
      );
      const scope = f.scope ? `${f.scope} ` : '';
      const dotCls = f.loaded ? 'on' : 'off';
      html += `
        <div class="file-section-header">
          <span class="name">
            <span class="loaded-dot ${dotCls}" style="margin-right:6px"></span>
            <span class="kind-tag ${f.kind}" style="margin-right:6px;padding:1px 5px;border-radius:3px;background:var(--panel-2);font-size:9px;text-transform:uppercase">${scope}${f.kind}</span>${escapeHtml(f.path)}
          </span>
          <span>${blocks.length}${statusFilter ? ` of ${f.blocks.length}` : ''} blocks${notLoadedHint}${f.delivery ? ` · <span style="color:var(--purple)">${deliveredLinesLabel(f.delivery)}</span>` : ''}</span>
        </div>
        ${hookNote(f)}
      `;
    }
    blocks.forEach(b => {
      const sel = selectedBlockId === b.id ? 'selected' : '';
      html += `
        <div class="block ${sel}" data-block="${b.id}">
          <div class="block-header">
            <span class="block-type ${b.type}">${b.type}</span>
            <span class="block-title">${escapeHtml(b.title)}</span>
            <span class="block-status status-${b.status}">
              <span class="status-dot"></span>${statusLabel[b.status] || b.status}
            </span>
            ${scopeBadgeHtml()}
          </div>
          <div class="block-content">${escapeHtml(b.content)}</div>
        </div>
      `;
    });
  });
  el.innerHTML = html;
}

function renderDetail(blockId) {
  const el = document.getElementById('detail-pane');
  if (!blockId) {
    el.classList.add('empty');
    el.innerHTML = '<div>Click a block to see how the agent treated it in this run.</div>';
    return;
  }
  const allBlocks = activeTurn().contextFiles.flatMap(f => f.blocks);
  const b = allBlocks.find(x => x.id === blockId);
  if (!b) return;
  el.classList.remove('empty');

  const statusLabel = {
    'used': 'Followed by the agent',
    'used-partial': 'Followed in spirit, not to the letter',
    'possibly-referenced': 'Possibly referenced — weak evidence only',
    'ignored': 'Rule applied but agent did not follow it',
    'unused': 'Never triggered (precondition not met)',
    'dormant': 'Dormant — could not have fired this run',
    'not-loaded': 'Skill block — not loaded into context this run',
    'undelivered': 'Never reached the model — outside the delivered range'
  }[b.status] || b.status;

  let html = `
    <div class="detail-section">
      <h4 style="display:flex;align-items:center">
        <span>${escapeHtml(b.title)}</span>
        <span class="help-trigger" data-help="block" title="What's in this section?">?</span>
      </h4>
      <div style="background:var(--panel-2);padding:10px 12px;border-radius:6px;font-family:monospace;font-size:12px;white-space:pre-wrap;border-left:3px solid var(--border)">${escapeHtml(b.content)}</div>
    </div>
    <div class="detail-section">
      <h4 style="display:flex;align-items:center">
        <span>Verdict</span>
        <span class="help-trigger" data-help="verdict" title="How is the verdict computed?">?</span>
      </h4>
      <div class="block-status status-${b.status}" style="font-size:13px;margin-bottom:8px">
        <span class="status-dot"></span>${statusLabel}
      </div>
      <div class="reason ${b.status}">${escapeHtml(b.reason)}</div>
    </div>
  `;

  if (b.ruleCheck) html += renderRuleCheck(b.ruleCheck);

  const ownerFile = activeTurn().contextFiles.find(f => f.blocks.some(x => x.id === b.id));
  const fileCost = costOf(ownerFile || {});
  if (fileCost.tokens) {
    const bt = (b.cost && b.cost.tokens) || 0;
    html += `
      <div class="detail-section">
        <h4><span>Cost</span></h4>
        <div class="reason">${fmtTokens(bt)} tokens of this file's ${fmtTokens(fileCost.tokens)},
          resent over ${fileCost.sentCount} request${fileCost.sentCount === 1 ? '' : 's'}
          (${fmtTokens(fileCost.cached)} cached, ${fmtTokens(fileCost.fresh)} fresh).<span class="est-badge" title="The file total is its share of the API's reported prompt tokens; the per-block split is by line share.">block figure is an estimate</span></div>
      </div>
    `;
  }

  // Near-duplicates section
  const dupes = (active().duplicates || []).filter(d => d.idA === b.id || d.idB === b.id);
  if (dupes.length) {
    html += `<div class="detail-section">
      <h4 style="display:flex;align-items:center">
        <span>Near-duplicates (${dupes.length})</span>
        <span class="help-trigger" data-help="duplicates-section" title="What does this mean?">?</span>
      </h4>`;
    dupes.forEach(d => {
      const otherId = d.idA === b.id ? d.idB : d.idA;
      const otherTitle = d.idA === b.id ? d.titleB : d.titleA;
      const otherFile = d.idA === b.id ? d.fileB : d.fileA;
      const cls = d.classification;
      const statusLabel = {
        'redundant': 'confirmed redundant',
        'referenced': 'topic referenced',
        'not-loaded': 'partner not loaded',
      }[cls] || cls;
      html += `
        <div class="dup-card classification-${cls}">
          <div class="dup-head">
            <span class="dup-similarity">${(d.similarity * 100).toFixed(0)}% similar</span>
            <span class="dup-tokens" title="Overlapping share of the cheaper side's attributed cost.">${fmtTokens(d.tokens)} tokens</span>
            <span class="dup-status classification-${cls}">${statusLabel}</span>
          </div>
          <div class="dup-target">
            <span class="title">${escapeHtml(otherTitle)}</span><br>
            <span class="file-path">${escapeHtml(otherFile)}</span>
          </div>
          ${d.sharedPhrase ? `<div class="dup-shared"><span class="label">shared phrase:</span> "${escapeHtml(d.sharedPhrase)}"</div>` : ''}
          <span class="dup-open" data-open-block="${escapeHtml(otherId)}">Open partner block →</span>
        </div>
      `;
    });
    html += `</div>`;
  }

  if (b.evidence && b.evidence.length) {
    html += `<div class="detail-section">
      <h4 style="display:flex;align-items:center">
        <span>Evidence from the trace</span>
        <span class="help-trigger" data-help="evidence" title="What is each card?">?</span>
      </h4>`;
    b.evidence.forEach(ev => {
      html += `<div class="ev-card">
        <div class="label">${escapeHtml(ev.label)}</div>
        <div class="text">${escapeHtml(ev.text)}</div>
      </div>`;
    });
    html += `</div>`;
  }

  if (b.moments && b.moments.length) {
    html += `<div class="detail-section">
      <h4 style="display:flex;align-items:center">
        <span>How the agent ended up here</span>
        <span class="help-trigger" data-help="moments" title="How to read the timeline?">?</span>
      </h4>
      <div class="moments">`;
    const sessStart = active().session.startTime ? new Date(active().session.startTime).getTime() : 0;
    b.moments.forEach(mt => {
      const verdict = mt.verdict === 'yes' ? '✓' : mt.verdict === 'no' ? '✗' : '';
      const verdictCls = mt.verdict ? ('verdict-' + mt.verdict) : '';
      let timeLabel = '—';
      if (mt.t && sessStart) {
        const off = Math.max(0, Math.floor((new Date(mt.t).getTime() - sessStart) / 1000));
        if (off < 60) timeLabel = `+${off}s`;
        else if (off < 3600) timeLabel = `+${Math.floor(off/60)}m${(off%60).toString().padStart(2,'0')}s`;
        else timeLabel = `+${Math.floor(off/3600)}h${Math.floor((off%3600)/60).toString().padStart(2,'0')}m`;
      }
      const inlineHelp = mt.kind === 'thinking-gap'
        ? `<span class="help-trigger" data-help="thinking-gap" title="Why no readable content?">?</span>`
        : '';
      html += `
        <div class="moment kind-${mt.kind} ${verdictCls}">
          <div class="moment-head">
            <span class="moment-time">${timeLabel}</span>
            <span class="moment-kind">${escapeHtml(mt.kind.replace('-',' '))}</span>
            ${verdict ? `<span class="moment-verdict ${mt.verdict}">${verdict}</span>` : ''}
            <span class="moment-label">${escapeHtml(mt.label || '')}</span>
            ${inlineHelp}
          </div>
          ${mt.text ? `<div class="moment-text">${escapeHtml(mt.text)}</div>` : ''}
        </div>
      `;
    });
    html += `</div></div>`;
  }

  el.innerHTML = html;
  attachHelpTriggers(el);
  el.querySelectorAll('[data-open-block]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      openBlock(btn.dataset.openBlock);
    });
  });
}

function openBlock(blockId) {
  // Find which file owns this block; expand its filter view, switch to Block Inspector,
  // scroll to the block, render its detail. Block ids may be aggregate-style
  // (no prefix) or per-turn (`turn{N}-...`). The Duplicates panel is session-
  // scoped and emits aggregate ids, so jumping into a turn-scoped view would
  // show stale chrome — switch back to "All turns" to land on the right block.
  const aggregateBlock = !/^turn\d+-/.test(blockId);
  if (aggregateBlock && activeTurnId !== 'all') {
    activeTurnId = 'all';
    renderTurnPicker();
  }
  const A = activeTurn();
  let owningFile = null;
  for (const f of A.contextFiles) {
    if (f.blocks.some(b => b.id === blockId)) { owningFile = f; break; }
  }
  if (!owningFile) return;
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.querySelector('nav button[data-view="blocks"]').classList.add('active');
  document.getElementById('blocks-view').hidden = false;
  document.getElementById('timeline-view').hidden = true;
  document.getElementById('files-view').hidden = true;
  if (document.getElementById('duplications-view')) document.getElementById('duplications-view').hidden = true;
  if (document.getElementById('compare-view')) document.getElementById('compare-view').hidden = true;
  selectedBlockId = blockId;
  selectedFilePath = null; // show all so we can scroll to it
  // If the load filter would hide this block's owning file, drop the filter so we can navigate.
  if ((loadFilter === 'loaded' && !owningFile.loaded) ||
      (loadFilter === 'not-loaded' && owningFile.loaded)) {
    loadFilter = 'all';
  }
  const target = owningFile.blocks.find(b => b.id === blockId);
  if (statusFilter && target && target.status !== statusFilter) statusFilter = null;
  renderFileTree();
  renderBlocks();
  renderDetail(blockId);
  setTimeout(() => {
    const node = document.querySelector(`.block[data-block="${CSS.escape(blockId)}"]`);
    if (node) node.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 50);
}

function renderTimeline() {
  const el = document.getElementById('timeline-pane');
  const tl = activeTurn().timeline;
  const startTs = tl.length ? new Date(tl[0].ts).getTime() : 0;

  let html = `
    <div class="pane-header">
      <h2>Run timeline (${tl.length} events)</h2>
      <div class="subtitle">Chronological trace of every assistant message and tool call. Click a row to expand.</div>
    </div>
    <div class="timeline-filter" id="filter">
      Show:
      <label><input type="checkbox" data-kind="user" checked>user</label>
      <label><input type="checkbox" data-kind="user-command" checked>commands</label>
      <label><input type="checkbox" data-kind="assistant-text" checked>assistant text</label>
      <label><input type="checkbox" data-kind="tool-use" checked>tool calls</label>
      <label><input type="checkbox" data-kind="tool-result">tool results</label>
      ${tl.some(r => r.kind === 'compaction') ? '<label><input type="checkbox" data-kind="compaction" checked>compaction</label>' : ''}
      ${tl.some(r => r.kind === 'cache-break') ? '<label><input type="checkbox" data-kind="cache-break" checked>cache breaks</label>' : ''}
    </div>
    <div id="timeline-list"></div>
  `;
  el.innerHTML = html;
  drawTimelineList(startTs);

  document.querySelectorAll('#filter input').forEach(cb => {
    cb.addEventListener('change', () => drawTimelineList(startTs));
  });
}

function drawTimelineList(startTs) {
  const enabled = new Set(Array.from(document.querySelectorAll('#filter input:checked')).map(cb => cb.dataset.kind));
  const list = document.getElementById('timeline-list');
  let html = '';
  activeTurn().timeline.forEach((row, idx) => {
    if (!enabled.has(row.kind)) return;
    const t = startTs ? Math.floor((new Date(row.ts).getTime() - startTs) / 1000) : 0;
    const when = `+${t}s`;
    html += `
      <div class="timeline-row" data-idx="${idx}">
        <div class="when">${when}</div>
        <div class="kind kind-${row.kind}">${escapeHtml(row.label)}</div>
        <div class="text">${escapeHtml(row.text)}</div>
      </div>
    `;
  });
  list.innerHTML = html;
  list.querySelectorAll('.timeline-row').forEach(r => {
    r.addEventListener('click', () => r.classList.toggle('expanded'));
  });
}

// A side that cost nothing (its file was never sent) says so by staying silent
// rather than printing a 0 next to every title.
function sideCost(tokens) {
  return tokens ? ` · ${fmtTokens(tokens)}` : '';
}

function renderDuplications() {
  const el = document.getElementById('dup-pane');
  const A = active();
  const dupes = A.duplicates || [];
  const totalTokens = dupes.reduce((s, d) => s + d.tokens, 0);
  const redundant = dupes.filter(d => d.classification === 'redundant').length;
  const referenced = dupes.filter(d => d.classification === 'referenced').length;

  // Per PRD: duplicates are session-scoped (content overlap is meaningful
  // across the whole investigation, not per-turn). The label tells users why
  // this panel ignores the turn picker on purpose.
  const sessionScopeBadge = (A.turnCount || 0) > 1
    ? `<span class="scope-badge" title="Duplicate detection runs across the whole session — the turn picker doesn't apply here.">session-scope</span>`
    : '';
  let html = `
    <div class="pane-header">
      <h2 style="display:flex;align-items:center;gap:8px">
        <span>Near-duplicate context</span>
        ${sessionScopeBadge}
        <span class="help-trigger" data-help="duplicates-tab" title="What is this tab?">?</span>
      </h2>
      <div class="subtitle">Pairs of blocks across files that share substantial phrasing — these may cost tokens twice for the same instruction. Costs are each block's share of the real tokens its file was billed, across every request that carried it.</div>
    </div>
  `;

  if (!dupes.length) {
    html += `
      <div class="dup-summary">
        <strong>No near-duplicates detected for this session.</strong><br>
        Searched ${A.contextFiles.length} loaded context files at similarity threshold 30% (containment coefficient on 3-word shingles). Pairs from the same file, short blocks (&lt; 15 words), code-only overlap, and <code>@</code>-referenced files are filtered out.
      </div>
    `;
    el.innerHTML = html;
    attachHelpTriggers(el);
    return;
  }

  html += `
    <div class="dup-summary">
      <strong>${dupes.length}</strong> duplicate pair${dupes.length === 1 ? '' : 's'} ·
      <strong>${fmtTokens(totalTokens)}</strong> token${totalTokens === 1 ? '' : 's'} duplicated this session<span class="est-badge" title="Block-level figures divide a file's real token cost by line share.">estimate</span> ·
      <span style="color:var(--red)">${redundant} confirmed redundant</span> ·
      <span style="color:var(--amber)">${referenced} topic referenced</span>
    </div>
    <table class="dup-table">
      <thead>
        <tr>
          <th class="col-sim">Similarity</th>
          <th class="col-status">Status</th>
          <th class="col-tok">Duplicated</th>
          <th>Block A</th>
          <th>Block B</th>
        </tr>
      </thead>
      <tbody>
  `;
  dupes.forEach(d => {
    const cls = d.classification;
    const statusLabel = {
      'redundant': 'confirmed redundant',
      'referenced': 'topic referenced',
      'not-loaded': 'partner not loaded',
    }[cls] || cls;
    html += `
      <tr data-open-block="${escapeHtml(d.idA)}">
        <td class="col-sim">${(d.similarity * 100).toFixed(0)}%</td>
        <td class="col-status"><span class="dup-status classification-${cls}">${statusLabel}</span></td>
        <td class="col-tok" title="Overlapping share of the cheaper side. A cost ${fmtTokens(d.tokensA||0)}, B cost ${fmtTokens(d.tokensB||0)}.">${fmtTokens(d.tokens)}</td>
        <td class="block-cell"><span class="title">${escapeHtml(d.titleA)}${sideCost(d.tokensA)}</span><span class="file-path">${escapeHtml(d.fileA)}</span></td>
        <td class="block-cell"><span class="title">${escapeHtml(d.titleB)}${sideCost(d.tokensB)}</span><span class="file-path">${escapeHtml(d.fileB)}</span></td>
      </tr>
    `;
  });
  html += `</tbody></table>`;
  el.innerHTML = html;
  attachHelpTriggers(el);
  el.querySelectorAll('tr[data-open-block]').forEach(row => {
    row.addEventListener('click', () => openBlock(row.dataset.openBlock));
  });
}

function renderFiles() {
  const el = document.getElementById('file-pane');
  const fmt = (path) => {
    const idx = path.lastIndexOf('/');
    const dir = idx >= 0 ? path.slice(0, idx + 1) : '';
    const base = idx >= 0 ? path.slice(idx + 1) : path;
    return `<span class="dir">${escapeHtml(dir)}</span><span class="basename">${escapeHtml(base)}</span>`;
  };
  let html = `
    <div class="pane-header">
      <h2>File activity</h2>
      <div class="subtitle">Which files the agent read and edited during this run.</div>
    </div>
    <h3 style="font-size:11px;text-transform:uppercase;color:var(--text-dim);letter-spacing:0.5px;margin-bottom:8px">Reads (${activeTurn().fileActivity.reads.length} unique files)</h3>
    <div class="file-list">
  `;
  activeTurn().fileActivity.reads.forEach(([fp, n]) => {
    html += `<div class="file-row"><div class="count">×${n}</div><div class="path">${fmt(fp)}</div></div>`;
  });
  html += `</div><h3 style="font-size:11px;text-transform:uppercase;color:var(--text-dim);letter-spacing:0.5px;margin-bottom:8px">Edits (${activeTurn().fileActivity.edits.length} unique files)</h3><div class="file-list">`;
  activeTurn().fileActivity.edits.forEach(([fp, n]) => {
    html += `<div class="file-row"><div class="count">×${n}</div><div class="path">${fmt(fp)}</div></div>`;
  });
  html += `</div>`;
  el.innerHTML = html;
}

// The compare payload is baked only when --compare was passed, so the tab
// stays hidden on a default build rather than opening onto an empty pane.
function renderCompare() {
  const el = document.getElementById('cmp-pane');
  const C = DATA.compare;
  if (!C) { el.innerHTML = `<div class="cmp-empty-note">No comparison was baked into this page. Rebuild with <code>--compare &lt;session-a&gt; &lt;session-b&gt;</code>.</div>`; return; }

  const signed = (n) => (n > 0 ? '+' : '') + n;
  const sideLine = (s) => `<span class="cmp-side">${escapeHtml((s.id || '').slice(0, 10))}</span> · ${s.turnCount} turn${s.turnCount === 1 ? '' : 's'} · ${s.counts.totalToolCalls || 0} calls · ${fmtTokens((s.usage || {}).promptTokens || 0)} in / ${fmtTokens((s.usage || {}).outputTokens || 0)} out`;

  let html = `
    <div class="pane-header">
      <h2>Compare two runs</h2>
      <div class="subtitle">Steps are aligned on what the agent actually did (longest common subsequence over tool-call names), so one extra call marks one row instead of shifting every row after it. Re-run the build with different ids to compare another pair.</div>
    </div>
  `;
  if (C.note) html += `<div class="cmp-note">${escapeHtml(C.note)}</div>`;
  html += `
    <div class="cmp-summary">
      <div><strong>A</strong> ${sideLine(C.a)}</div>
      <div><strong>B</strong> ${sideLine(C.b)}</div>
      <div style="margin-top:8px">
        <strong>${C.divergentSteps}</strong> divergent step${C.divergentSteps === 1 ? '' : 's'} of ${C.steps.length} ·
        tool calls <strong>${signed(C.deltas.totalToolCalls)}</strong> ·
        files edited <strong>${signed(C.deltas.filesEdited)}</strong> ·
        prompt tokens <strong>${signed(C.deltas.promptTokens)}</strong> ·
        output tokens <strong>${signed(C.deltas.outputTokens)}</strong> ·
        <strong>${C.verdictChanges.length}</strong> block verdict change${C.verdictChanges.length === 1 ? '' : 's'}
      </div>
    </div>
  `;

  const MARK = { match: '=', added: '+ b only', removed: '− a only', changed: '~ changed' };
  let stepRows = '';
  C.steps.forEach(s => {
    const cell = (x) => {
      if (!x) return `<td class="cmp-empty">—</td>`;
      // A session with no real user prompt produces no turns, so its actions
      // carry a null turn — show the detail regardless, it's the only context.
      const where = (x.turn === null || x.turn === undefined) ? '' : `turn ${x.turn + 1} · `;
      return `<td class="cmp-cell">${escapeHtml(x.name)} <span class="cmp-detail">${where}${escapeHtml(x.detail || '')}</span></td>`;
    };
    stepRows += `<tr class="cmp-row kind-${s.kind}"><td class="cmp-mark">${MARK[s.kind] || s.kind}</td>${cell(s.a)}${cell(s.b)}</tr>`;
  });

  let turnRows = '';
  C.turns.forEach(t => {
    const label = (x) => x ? escapeHtml(x.promptPreview.slice(0, 60)) : '—';
    const kind = !t.b ? 'removed' : (!t.a ? 'added' : (t.promptMatch ? 'match' : 'changed'));
    turnRows += `
      <tr class="cmp-row kind-${kind}">
        <td class="cmp-mark">turn ${t.index + 1}</td>
        <td class="cmp-cell">${label(t.a)}</td>
        <td class="cmp-cell">${label(t.b)}</td>
        <td class="cmp-cell">${signed(t.deltas.toolCalls)} calls · ${signed(t.deltas.promptTokens)} in · ${signed(t.deltas.outputTokens)} out</td>
      </tr>`;
  });

  let fileHtml = '';
  C.contextFiles.forEach(f => {
    const flags = [];
    if (f.presence !== 'both') flags.push(f.presence === 'a-only' ? 'only in A' : 'only in B');
    if (f.drifted) flags.push('<span class="drift">content drifted</span>');
    if (f.loadedA !== f.loadedB) flags.push(f.loadedB ? 'loaded in B only' : 'loaded in A only');
    let items = '';
    f.added.forEach(b => { items += `<li class="added"><span class="op">+</span>${escapeHtml(b.title)} <span class="block-id">${escapeHtml(b.id)}</span></li>`; });
    f.removed.forEach(b => { items += `<li class="removed"><span class="op">−</span>${escapeHtml(b.title)} <span class="block-id">${escapeHtml(b.id)}</span></li>`; });
    f.changed.forEach(b => { items += `<li class="changed"><span class="op">~</span>${escapeHtml(b.title)} <span class="block-id">${escapeHtml(b.id)}</span></li>`; });
    f.verdictChanges.forEach(v => { items += `<li class="verdict"><span class="op">→</span>${escapeHtml(v.title)}: ${escapeHtml(v.from)} → ${escapeHtml(v.to)} <span class="block-id">${escapeHtml(v.id)}</span></li>`; });
    fileHtml += `
      <div class="cmp-file">
        <div class="cmp-file-path">${escapeHtml(f.path)}</div>
        <div class="cmp-flags">${flags.join(' · ') || 'same content, different treatment'}</div>
        <ul class="cmp-blocks">${items}</ul>
      </div>`;
  });
  if (!fileHtml) fileHtml = `<div class="cmp-empty-note">Both runs saw the same context files, block for block, with the same verdicts.</div>`;

  html += `
    <div class="cmp-cols">
      <div>
        <h3>Behaviour — aligned steps</h3>
        <table class="cmp-table">
          <thead><tr><th></th><th>A</th><th>B</th></tr></thead>
          <tbody>${stepRows || `<tr><td colspan="3" class="cmp-empty">Neither run made a tool call.</td></tr>`}</tbody>
        </table>
        <h3 style="margin-top:18px">Behaviour — per turn</h3>
        <table class="cmp-table">
          <thead><tr><th></th><th>A prompt</th><th>B prompt</th><th>B − A</th></tr></thead>
          <tbody>${turnRows || `<tr><td colspan="4" class="cmp-empty">No turns.</td></tr>`}</tbody>
        </table>
      </div>
      <div>
        <h3>Context — block diff</h3>
        ${fileHtml}
      </div>
    </div>
  `;
  el.innerHTML = html;
}

document.querySelectorAll('nav button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const v = btn.dataset.view;
    document.getElementById('blocks-view').hidden       = v !== 'blocks';
    document.getElementById('timeline-view').hidden     = v !== 'timeline';
    document.getElementById('files-view').hidden        = v !== 'files';
    document.getElementById('duplications-view').hidden = v !== 'duplications';
    document.getElementById('compare-view').hidden      = v !== 'compare';
    if (v === 'timeline') renderTimeline();
    if (v === 'files') renderFiles();
    if (v === 'duplications') renderDuplications();
    if (v === 'compare') renderCompare();
  });
});

if (DATA.compare) document.getElementById('compare-tab').hidden = false;

document.getElementById('blocks-pane').addEventListener('click', e => {
  const chip = e.target.closest('.status-chip');
  if (chip) {
    const st = chip.dataset.status;
    statusFilter = (!st || statusFilter === st) ? null : st;
    renderBlocks();
    return;
  }
  const b = e.target.closest('.block');
  if (b) {
    selectedBlockId = b.dataset.block;
    document.querySelectorAll('.block').forEach(x => x.classList.toggle('selected', x.dataset.block === selectedBlockId));
    renderDetail(selectedBlockId);
  }
});

renderSessionPicker();
renderTurnPicker();
renderFileTree();
renderBlocks();
renderDetail(null);

document.getElementById('turn-prev').addEventListener('click', () => stepTurn(-1));
document.getElementById('turn-next').addEventListener('click', () => stepTurn(1));

document.addEventListener('keydown', (e) => {
  // Don't hijack typing in form fields.
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === '[') { e.preventDefault(); stepTurn(-1); }
  else if (e.key === ']') { e.preventDefault(); stepTurn(1); }
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
