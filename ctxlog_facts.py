"""Read the ctxlog hook log for a session into context-loading facts.

The hook log is the harness's own record of which instruction files it loaded
and why - ground truth that the transcript does not carry. This module only
reads that log; the transcript stays the single source for the trace.
"""

import json
import os
from pathlib import Path


def _default_dir():
    # Mirrors log_dir() in ctxlog.py, which lives outside this repo and so
    # cannot be imported. Unlike it, never create the directory: reading is
    # not a reason to leave a folder behind.
    d = os.environ.get("CTXLOG_DIR") or (Path.home() / ".claude" / "ctxlog")
    return Path(d)


def _norm_path(p):
    if not p:
        return p
    try:
        return str(Path(p).resolve())
    except Exception:
        return str(p)


def _empty_facts():
    return {
        "nested_memories": [],
        "hook_directives": [],
        "skill_listing": [],
        "skill_listing_present": False,
        "skill_count": None,
        "preloaded_files": [],
        "user_attached_files": [],
        "instructions": [],
        "compactions": [],
    }


def load_facts(session_id, ctxlog_dir=None):
    """Loading facts for one session, or None when no log was recorded for it.

    None means "no hook data" and must leave every caller on its existing
    behaviour - sessions predating the hooks have to keep working.

    The attachment-shaped keys mirror extract_attachments() so this is a
    drop-in companion, but the hook log carries no attachment data: they are
    always empty. The payload is `instructions` (every InstructionsLoaded
    record, chronological, subagent records dropped) and `compactions`.
    """
    if not session_id:
        return None
    log_path = (Path(ctxlog_dir) if ctxlog_dir else _default_dir()) / f"{session_id}.jsonl"
    try:
        # ctxlog.py writes the log as UTF-8 regardless of locale.
        raw = log_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    facts = _empty_facts()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        # agent_id is written only inside a subagent; those loads never
        # entered the main thread's context.
        if rec.get("agent_id"):
            continue

        event = rec.get("event")
        if event == "InstructionsLoaded":
            stats = rec.get("stats")
            facts["instructions"].append({
                "path": _norm_path(rec.get("path")),
                "memory_type": rec.get("memory_type"),
                "load_reason": rec.get("load_reason"),
                "globs": rec.get("globs"),
                "trigger_file_path": _norm_path(rec.get("trigger_file_path")),
                "parent_file_path": _norm_path(rec.get("parent_file_path")),
                "ts": rec.get("ts"),
                "stats": stats if isinstance(stats, dict) else {},
            })
        elif event in ("PreCompact", "PostCompact"):
            facts["compactions"].append({
                "event": event,
                "ts": rec.get("ts"),
                "trigger": rec.get("trigger"),
            })
    return facts


def latest_by_path(facts):
    """Most recent instruction record per absolute path.

    A path can be loaded several times in a session (session_start, then a
    reload after compaction); callers that only want "how was this file
    loaded" take the last one.
    """
    out = {}
    if not facts:
        return out
    for rec in facts.get("instructions") or []:
        path = rec.get("path")
        if path:
            out[path] = rec
    return out
