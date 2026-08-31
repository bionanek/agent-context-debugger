#!/usr/bin/env python3
"""
ctxlog - see what actually entered Claude Code's context in a session.

Three subcommands:
  collect   read a hook payload on stdin, append one record to the session log
  report    render a session log as a readable timeline + coverage check
  install   print (or merge) the hook config for ~/.claude/settings.json

Design constraints that matter:
  - collect NEVER writes to stdout. On SessionStart / UserPromptSubmit,
    Claude Code feeds hook stdout into the model's context. Printing there
    would pollute the very thing we're trying to measure.
  - collect always exits 0 and never raises. A crashing observability hook
    that blocks a session is worse than no observability.
  - Nothing here parses ~/.claude/projects/*.jsonl. That format is internal
    to Claude Code and changes between releases. Hook payloads are the
    documented surface.

Log location: $CTXLOG_DIR or ~/.claude/ctxlog/<session_id>.jsonl
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Read tool returns the first 2000 lines when no explicit limit is passed.
DEFAULT_READ_LINE_CAP = 2000
# Don't line-count files bigger than this; not worth the IO on every read.
MAX_STAT_BYTES = 20 * 1024 * 1024

# Files we consider "guidance Claude was supposed to know about".
# Used by the coverage section of the report. Override with CTXLOG_GUIDE_GLOBS.
DEFAULT_GUIDE_GLOBS = [
    "CLAUDE.md",
    "*/CLAUDE.md",
    "**/CLAUDE.md",
    ".claude/rules/**/*.md",
    ".claude/skills/**/*.md",
    "docs/**/*.md",
    "doc/**/*.md",
    "adr/**/*.md",
    "docs/adr/**/*.md",
    "**/AGENTS.md",
    "**/CONTRIBUTING.md",
]

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "vendor",
             ".venv", "venv", "__pycache__", ".turbo", "coverage"}


# ---------------------------------------------------------------- collect ----

def log_dir() -> Path:
    d = os.environ.get("CTXLOG_DIR") or (Path.home() / ".claude" / "ctxlog")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_stats(path: str) -> dict:
    """Line count + size + content hash, so we can flag truncation and
    detect that a guide file changed between sessions."""
    out = {}
    try:
        st = os.stat(path)
        out["size_bytes"] = st.st_size
        if st.st_size > MAX_STAT_BYTES:
            out["lines"] = None
            return out
        h = hashlib.sha256()
        newlines = 0
        last = b""
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                newlines += chunk.count(b"\n")
                last = chunk[-1:]
        if st.st_size == 0:
            out["lines"] = 0
        else:
            # A trailing newline terminates the last line, it doesn't start
            # a new one. Without this check every count is one too high.
            out["lines"] = newlines if last == b"\n" else newlines + 1
        out["sha256"] = h.hexdigest()[:16]
    except Exception:
        pass
    return out


def response_text(payload: dict) -> str:
    """PostToolUse carries the tool result, but its exact shape is version
    dependent. Flatten whatever is there to a string so we can look for a
    truncation notice without depending on the schema."""
    for key in ("tool_response", "tool_result", "response"):
        if key in payload:
            v = payload[key]
            if isinstance(v, str):
                return v
            try:
                return json.dumps(v)
            except Exception:
                return str(v)
    return ""


def truncation_verdict(tool_input: dict, stats: dict, resp: str) -> dict:
    """Three independent signals, because none of them alone is reliable."""
    offset = tool_input.get("offset")
    limit = tool_input.get("limit")
    total = stats.get("lines")
    low = resp.lower()

    reported = any(m in low for m in
                   ("partial view", "partial]", "truncated", "exceeds maximum"))

    if offset is not None or limit is not None:
        start = int(offset or 1)
        end = start + int(limit) - 1 if limit else None
        return {"kind": "partial_by_request", "from_line": start,
                "to_line": end, "total_lines": total,
                "tool_reported_partial": reported}

    if total and total > DEFAULT_READ_LINE_CAP:
        return {"kind": "likely_truncated", "from_line": 1,
                "to_line": DEFAULT_READ_LINE_CAP, "total_lines": total,
                "tool_reported_partial": reported}

    return {"kind": "reported_partial" if reported else "full",
            "from_line": 1, "to_line": total, "total_lines": total,
            "tool_reported_partial": reported}


def build_record(payload: dict) -> dict:
    event = payload.get("hook_event_name", "unknown")
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "session_id": payload.get("session_id"),
        "prompt_id": payload.get("prompt_id"),
        "cwd": payload.get("cwd"),
    }
    # Present only inside subagents. Without this, subagent reads get
    # wrongly merged into the main thread's view of "what Claude knows".
    for k in ("agent_id", "agent_type"):
        if payload.get(k):
            rec[k] = payload[k]

    if event == "InstructionsLoaded":
        path = payload.get("file_path")
        rec.update({
            "path": path,
            "memory_type": payload.get("memory_type"),
            "load_reason": payload.get("load_reason"),
            "globs": payload.get("globs"),
            "trigger_file_path": payload.get("trigger_file_path"),
            "parent_file_path": payload.get("parent_file_path"),
            "stats": file_stats(path) if path else {},
        })

    elif event in ("PostToolUse", "PostToolUseFailure"):
        ti = payload.get("tool_input") or {}
        tool = payload.get("tool_name")
        rec["tool"] = tool
        rec["tool_use_id"] = payload.get("tool_use_id")
        resp = response_text(payload)
        rec["response_chars"] = len(resp)
        if tool == "Read":
            path = ti.get("file_path")
            stats = file_stats(path) if path else {}
            rec["path"] = path
            rec["stats"] = stats
            rec["coverage"] = truncation_verdict(ti, stats, resp)
        elif tool == "Grep":
            rec["pattern"] = ti.get("pattern")
            rec["path"] = ti.get("path") or ti.get("glob")
        elif tool == "Glob":
            rec["pattern"] = ti.get("pattern")
        else:
            rec["tool_input_keys"] = sorted(ti.keys())

    elif event == "SessionStart":
        rec["source"] = payload.get("source")
        rec["model"] = payload.get("model")
        rec["session_title"] = payload.get("session_title")

    elif event == "UserPromptSubmit":
        p = payload.get("prompt") or ""
        # First line only. Enough to label a turn, no need to hoard prompts.
        rec["prompt_preview"] = p.strip().splitlines()[0][:160] if p.strip() else ""

    elif event in ("PreCompact", "PostCompact"):
        rec["trigger"] = payload.get("trigger")

    elif event in ("SubagentStart", "SubagentStop"):
        rec["subagent"] = payload.get("agent_type")

    return rec


def cmd_collect(argv) -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        rec = build_record(payload)
        sid = rec.get("session_id") or "unknown-session"
        target = log_dir() / f"{sid}.jsonl"
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        # Diagnostics go to stderr, which is not fed to the model on the
        # events we hook. Never stdout.
        print(f"ctxlog: {type(e).__name__}: {e}", file=sys.stderr)
    return 0


# ----------------------------------------------------------------- report ----

def load_session(sid: str | None) -> tuple[str, list[dict]]:
    d = log_dir()
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise SystemExit(f"ctxlog: no logs in {d}. Are the hooks installed?")
    if sid:
        match = [f for f in files if f.stem.startswith(sid)]
        if not match:
            raise SystemExit(f"ctxlog: no session matching '{sid}' in {d}")
        chosen = match[0]
    else:
        chosen = files[0]
    recs = []
    for line in chosen.read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except Exception:
            continue
    return chosen.stem, recs


def rel(path: str | None, root: str | None) -> str:
    if not path:
        return "?"
    if root and path.startswith(root):
        return path[len(root):].lstrip("/") or path
    return path


def coverage_label(cov: dict) -> str:
    if not cov:
        return ""
    kind = cov.get("kind")
    total = cov.get("total_lines")
    if kind == "full":
        return f"full ({total} lines)" if total else "full"
    if kind == "partial_by_request":
        end = cov.get("to_line") or "?"
        return f"lines {cov.get('from_line')}-{end} of {total or '?'}  PARTIAL (by request)"
    if kind == "likely_truncated":
        return f"lines 1-{cov.get('to_line')} of {total}  TRUNCATED - Claude never saw the rest"
    if kind == "reported_partial":
        return "tool reported a partial view  PARTIAL"
    return kind or ""


def find_guides(root: str) -> list[str]:
    globs = os.environ.get("CTXLOG_GUIDE_GLOBS")
    patterns = globs.split(",") if globs else DEFAULT_GUIDE_GLOBS
    rootp = Path(root)
    found: set[str] = set()
    for pat in patterns:
        try:
            for p in rootp.glob(pat.strip()):
                if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
                    found.add(str(p.resolve()))
        except Exception:
            continue
    return sorted(found)


def cmd_report(argv) -> int:
    sid_arg = None
    show_all_tools = "--all-tools" in argv
    args = [a for a in argv if not a.startswith("--")]
    if args:
        sid_arg = args[0]

    sid, recs = load_session(sid_arg)
    if not recs:
        print("ctxlog: session log is empty")
        return 0

    root = next((r.get("cwd") for r in recs if r.get("cwd")), None)
    start = next((r for r in recs if r["event"] == "SessionStart"), None)

    print(f"session   {sid}")
    print(f"cwd       {root or '?'}")
    if start:
        bits = [b for b in (start.get("source"), start.get("model")) if b]
        print(f"started   {start['ts']}  ({', '.join(bits)})" if bits
              else f"started   {start['ts']}")
    print()

    # --- instruction files ---------------------------------------------------
    instr = [r for r in recs if r["event"] == "InstructionsLoaded"]
    print("INSTRUCTION FILES LOADED  (CLAUDE.md and .claude/rules)")
    if not instr:
        print("  none - if you expected a global or project CLAUDE.md here,")
        print("  that is your answer.")
    else:
        for r in instr:
            scope = r.get("memory_type") or "?"
            why = r.get("load_reason") or "?"
            lines = (r.get("stats") or {}).get("lines")
            size = f"{lines} lines" if lines else "?"
            tag = f" [in {r['agent_type']}]" if r.get("agent_type") else ""
            print(f"  {scope:<8} {rel(r.get('path'), root):<48} {size:>10}  ({why}){tag}")
            if r.get("trigger_file_path"):
                print(f"           ^ pulled in by {rel(r['trigger_file_path'], root)}")
    print()

    # --- reads ---------------------------------------------------------------
    reads = [r for r in recs if r.get("tool") == "Read"]

    def group(rows):
        seen: dict[str, dict] = {}
        for r in rows:
            p = r.get("path") or "?"
            seen.setdefault(p, {"n": 0, "worst": None})
            seen[p]["n"] += 1
            cov = r.get("coverage") or {}
            partial = cov.get("kind") in ("likely_truncated", "partial_by_request",
                                          "reported_partial")
            if partial or seen[p]["worst"] is None:
                seen[p]["worst"] = cov
        return seen

    def render(seen, indent="  "):
        for p, meta in sorted(seen.items()):
            name = rel(p, root)
            times = f" x{meta['n']}" if meta["n"] > 1 else ""
            print(f"{indent}{name:<52}{times}" if times else f"{indent}{name}")
            label = coverage_label(meta["worst"])
            if label:
                print(f"{indent}  {label}")

    # A subagent reads into its own context window and returns only a summary,
    # so its reads are NOT things the main thread knows. Keep them apart.
    main = [r for r in reads if not r.get("agent_id")]
    print(f"FILES READ IN MAIN THREAD  ({len(main)} Read calls)")
    if not main:
        print("  none")
    render(group(main))
    print()

    sub_reads = [r for r in reads if r.get("agent_id")]
    if sub_reads:
        by_agent: dict[str, list] = {}
        for r in sub_reads:
            by_agent.setdefault(r.get("agent_type") or "?", []).append(r)
        print(f"FILES READ INSIDE SUBAGENTS  ({len(sub_reads)} Read calls)")
        print("  These never entered the main context window.")
        for agent, rows in sorted(by_agent.items()):
            print(f"  {agent}:")
            render(group(rows), indent="    ")
        print()

    # --- searches ------------------------------------------------------------
    greps = [r for r in recs if r.get("tool") in ("Grep", "Glob")]
    if greps:
        print(f"SEARCHES  ({len(greps)})")
        for r in greps[:20]:
            where = rel(r.get("path"), root) if r.get("path") else ""
            print(f"  {r['tool']:<5} {r.get('pattern') or '?':<40} {where}")
        if len(greps) > 20:
            print(f"  ... and {len(greps) - 20} more")
        print()

    # --- compaction ----------------------------------------------------------
    compacts = [r for r in recs if r["event"] in ("PreCompact", "PostCompact")]
    if compacts:
        print("COMPACTION")
        for r in compacts:
            print(f"  {r['ts']}  {r['event']}  (trigger: {r.get('trigger') or '?'})")
        print("  Anything read before this point may no longer be in context.")
        print("  Project-root CLAUDE.md and unscoped rules reload from disk;")
        print("  path-scoped rules do not, until a matching file is read again.")
        print()

    # --- subagents -----------------------------------------------------------
    subs = [r for r in recs if r["event"] == "SubagentStart"]
    if subs:
        kinds = {}
        for r in subs:
            kinds[r.get("subagent") or "?"] = kinds.get(r.get("subagent") or "?", 0) + 1
        summary = ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items()))
        print(f"SUBAGENTS  {summary}")
        print("  Each ran in its own context window and returned only a summary.")
        print()

    # --- coverage gap --------------------------------------------------------
    if root and os.path.isdir(root):
        guides = find_guides(root)
        touched = {r.get("path") for r in recs if r.get("path")}
        touched = {os.path.realpath(p) for p in touched if p}
        missed = [g for g in guides if os.path.realpath(g) not in touched]
        print(f"NEVER TOUCHED  ({len(missed)} of {len(guides)} guidance files)")
        if not missed:
            print("  nothing - every guidance file was loaded or read")
        for g in missed[:30]:
            print(f"  {rel(g, root)}")
        if len(missed) > 30:
            print(f"  ... and {len(missed) - 30} more")
        print()

    if show_all_tools:
        other = [r for r in recs
                 if r["event"] == "PostToolUse"
                 and r.get("tool") not in ("Read", "Grep", "Glob")]
        print(f"OTHER TOOL CALLS  ({len(other)})")
        for r in other:
            print(f"  {r.get('tool')}  {r.get('tool_input_keys')}")
    return 0


def cmd_sessions(argv) -> int:
    d = log_dir()
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"ctxlog: no logs in {d}")
        return 0
    for f in files[:20]:
        mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        label = ""
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                if r.get("prompt_preview"):
                    label = r["prompt_preview"]
                    break
        except Exception:
            pass
        print(f"{mt}  {f.stem}  {label}")
    return 0


# ---------------------------------------------------------------- install ----

def hook_block(script_path: str) -> dict:
    """One async command hook per event. async so a slow stat never stalls a
    turn. timeout kept small as a second line of defence."""
    def h():
        return [{"type": "command", "command": sys.executable,
                 "args": [script_path, "collect"], "async": True, "timeout": 10}]

    return {
        "hooks": {
            "SessionStart": [{"matcher": "*", "hooks": h()}],
            "InstructionsLoaded": [{"matcher": "*", "hooks": h()}],
            "UserPromptSubmit": [{"hooks": h()}],
            "PostToolUse": [{"matcher": "Read|Grep|Glob", "hooks": h()}],
            "PreCompact": [{"matcher": "*", "hooks": h()}],
            "PostCompact": [{"matcher": "*", "hooks": h()}],
            "SubagentStart": [{"matcher": "*", "hooks": h()}],
            "SubagentStop": [{"matcher": "*", "hooks": h()}],
        }
    }


def cmd_install(argv) -> int:
    script = str(Path(__file__).resolve())
    block = hook_block(script)
    settings = Path.home() / ".claude" / "settings.json"

    if "--write" not in argv:
        print("# Merge this into ~/.claude/settings.json under \"hooks\":")
        print(json.dumps(block, indent=2))
        print("\n# Or let ctxlog merge it for you (a .bak backup is written first):")
        print(f"#   python3 {script} install --write")
        return 0

    existing = {}
    if settings.exists():
        backup = settings.with_suffix(".json.bak")
        backup.write_bytes(settings.read_bytes())
        try:
            existing = json.loads(settings.read_text(encoding="utf-8") or "{}")
        except Exception as e:
            print(f"ctxlog: {settings} is not valid JSON ({e}). Not touching it.",
                  file=sys.stderr)
            return 1
        print(f"backed up {settings} -> {backup}")

    hooks = existing.setdefault("hooks", {})
    for event, groups in block["hooks"].items():
        hooks.setdefault(event, [])
        # Don't duplicate on re-run.
        already = any(
            hh.get("args", [None])[0] == script
            for g in hooks[event] for hh in g.get("hooks", [])
        )
        if not already:
            hooks[event].extend(groups)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(f"wrote hooks into {settings}")
    print("Restart Claude Code, or run /hooks to confirm they registered.")
    return 0


# ------------------------------------------------------------------- main ----

USAGE = """ctxlog - what actually entered Claude Code's context

  ctxlog.py install [--write]     set up the hooks
  ctxlog.py sessions              list logged sessions, newest first
  ctxlog.py report [SID]          timeline for a session (default: newest)
  ctxlog.py report --all-tools    include non-file tool calls
  ctxlog.py collect               internal; called by hooks via stdin

env:
  CTXLOG_DIR           log location (default ~/.claude/ctxlog)
  CTXLOG_GUIDE_GLOBS   comma-separated globs for the coverage check
"""


def main() -> int:
    if len(sys.argv) < 2:
        print(USAGE)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    table = {"collect": cmd_collect, "report": cmd_report,
             "install": cmd_install, "sessions": cmd_sessions}
    fn = table.get(cmd)
    if not fn:
        print(USAGE)
        return 1
    return fn(rest)


if __name__ == "__main__":
    sys.exit(main())
