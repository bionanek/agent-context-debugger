#!/usr/bin/env python3
"""Deterministic rule checking from a checks file authored ahead of time.

The interpretation of a prose rule happens ONCE, outside this tool, by applying
`prompts/translate-rules.md` to a guideline document. Its output is a checks
JSON committed next to the document, reviewable by a human. This module only
loads that file, gates it, and applies it to what a recorded session actually
wrote and ran. Nothing here calls a model or the network by itself: the opt-in
judge tier is a runner the caller passes in (`check_block(..., judge=)`), from
a module this one imports only inside the functions that use it, so the default
path cannot reach a model even by accident.

The one external program this module will run is ast-grep, and only when the
user has already installed it with `install_ast_grep.py`: it is resolved from
the tool's own directory, never from PATH, and its absence downgrades the
structural checks to `not-checkable` rather than to a regex that answers a
different question.

Two failures from the live pilot shape the design and must not regress:

* The generating model reported that all of its self-tests passed; one did not,
  because it and the consumer disagreed about `required_order`. So every check
  is re-run against its own self-tests with *this* matcher at load time, and a
  check that fails is refused. A generator's self-assessment is not evidence.
* Every generated pattern carried its own comment guard, and one still matched
  inside a CSS block comment on a continuation line with no comment marker,
  which a line-anchored regex cannot see. So comment and string stripping
  happens once, centrally, before any pattern runs - self-test snippets
  included - and patterns are expected to carry no guards of their own.
"""
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

# An inline marker at the violation site downgrades a finding to acknowledged.
# Bare form suppresses every check on that line; the id form suppresses one.
# Real code deliberately breaks rules with a documented rationale, and calling
# that a violation is the same trust-destroying accusation as a false positive.
SUPPRESS_RE = re.compile(r"ctx-allow(?:\s*:\s*([A-Za-z0-9_-]+))?", re.I)

# Required fields per predicate kind. The vocabulary is closed: an unknown kind
# is refused rather than guessed at, because the pilot showed that ambiguity
# here silently produces broken checks.
VOCABULARY = {
    "forbidden_pattern": ("pattern",),
    "required_pattern": ("pattern",),
    "forbidden_co_occurrence": ("pattern", "with_pattern"),
    "required_co_occurrence": ("pattern", "with_pattern"),
    "required_order": ("first_pattern", "second_pattern"),
    "forbidden_command": ("pattern",),
    "required_command": ("trigger_pattern", "pattern"),
    "forbidden_path": ("pattern",),
    # Tool-log kinds. `tool_required` and `writes_to_path` take a
    # `trigger_pattern` rather than standing alone because an obligation that
    # simply never happened has no call to quote, and a violation without a
    # citable span is not reportable - the trigger call is the span.
    "tool_precedes": ("first_pattern", "second_pattern"),
    "tool_never_without_prior": ("pattern", "prior_pattern"),
    "tool_required": ("trigger_pattern", "pattern"),
    "tool_forbidden": ("pattern",),
    "tool_arg_matches": ("tool_pattern", "arg_pattern"),
    "tool_call_count": ("pattern",),
    "writes_to_path": ("trigger_pattern", "pattern"),
    # The omission kind. It scans nothing: a rule like "always implement the
    # catch body" is broken by writing *nothing*, so the pattern that would
    # catch it is absent by definition. It asks the enumerated sites instead.
    "candidate_requires": ("candidate", "pattern"),
    # The structural kind, and the only one that needs a program this tool did
    # not ship. Its field is an ast-grep pattern - code, not a regex.
    "ast_forbidden": ("ast_pattern",),
}

SOURCE_KINDS = ("forbidden_pattern", "required_pattern", "forbidden_co_occurrence",
                "required_co_occurrence", "required_order")
SHELL_KINDS = ("forbidden_command", "required_command")
PATH_KINDS = ("forbidden_path",)
TOOL_KINDS = ("tool_precedes", "tool_never_without_prior", "tool_required",
              "tool_forbidden", "tool_arg_matches", "tool_call_count",
              "writes_to_path")
CANDIDATE_CHECK_KINDS = ("candidate_requires",)
AST_KINDS = ("ast_forbidden",)

CONFIDENCES = ("high", "medium", "low")

# Record-format v2 (research doc §8). Every field is optional, so a v1 checks
# file keeps loading and reporting exactly what it did: the fields say what a
# record *is*, and a file that says nothing is read the way it always was.
SCOPES = ("code", "communication", "process")
EVIDENCE_SOURCES = ("diff", "files", "transcript")
# `deterministic` is the only bucket this tool can decide. `hybrid` (candidates
# enumerated here, each judged in isolation) and `judged` need the opt-in judge
# tier; until it exists they are parked and reported as unchecked, because a
# rule nobody could check must never render as one that was followed.
BUCKETS = ("deterministic", "hybrid", "judged")

# Which corpus each kind is able to read. A source pattern means nothing over
# the tool log and a tool pattern means nothing over a file's text, so a
# declared `evidence` the kind cannot read is refused at load rather than
# quietly ignored: a check that reads nothing reports as a rule nothing
# triggered, which looks like honest silence instead of a broken record.
_KIND_EVIDENCE = dict(
    [(k, ("diff", "files")) for k in SOURCE_KINDS + CANDIDATE_CHECK_KINDS + AST_KINDS]
    + [(k, ("transcript",)) for k in SHELL_KINDS + PATH_KINDS + TOOL_KINDS])

SHELL_PATH = "(shell)"
PATH_PATH = "(path)"
TOOLS_PATH = "(tools)"

# Two-stage conditional reporting. An antecedent that never fired and a
# consequent that was missed are different facts about the session, and the
# single verdict that used to carry both is how "the rule was followed" got
# printed over a run that never did the thing the rule governs.
STAGE_ANTECEDENT = "antecedent-not-fired"
STAGE_MISSED = "consequent-missed"
STAGE_SATISFIED = "satisfied"
# `tool_forbidden` has no second stage: the call happening *is* the finding.
# Reporting it as a missed consequent tells the reader an obligation went unmet
# under a badge that is actually about an action being taken.
STAGE_UNCONDITIONAL = None


# ---------- comment and string stripping ----------

_HASH_LANG_EXT = {".py", ".sh", ".bash", ".zsh", ".rb", ".yml", ".yaml", ".toml",
                  ".cfg", ".ini", ".pl", ".r"}
_TRIPLE_QUOTE_EXT = {".py"}
_C_LANG_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
               ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp",
               ".hpp", ".cs", ".m", ".mm", ".php", ".scala", ".dart", ".css",
               ".scss", ".less", ".sass", ".vue", ".svelte", ".json5", ".proto"}


def _dialect(path):
    """Comment and quote rules for a path, or None when the file has neither.

    Only known code extensions get a dialect. Applying C rules to prose was a
    real regression: `//` inside a URL swallowed the rest of a markdown line
    and an apostrophe in "don't" opened a string, which made the strict and
    stripped views disagree about files that were perfectly compliant.
    """
    ext = os.path.splitext(path or "")[1].lower()
    if ext in _HASH_LANG_EXT:
        return {"line": ("#",), "block": False, "quotes": ('"', "'"),
                "triple": ext in _TRIPLE_QUOTE_EXT}
    if ext in _C_LANG_EXT:
        return {"line": ("//",), "block": True, "quotes": ('"', "'", "`"),
                "triple": False}
    return None


def strip_comments_and_strings(text, path="", strip_strings=False, fill=" "):
    """Blank out comments, and string literals too when asked, preserving length.

    Offsets are preserved so a match found in the stripped text can be quoted
    from the original and reported at the right line. Comment markers are
    chosen by file extension: `#` starts a comment in Python and shell but is a
    hex colour or a private field in the C family, and treating it as a comment
    everywhere would silently blind the checker to real code. A file whose
    extension names no known language is returned untouched (see `_dialect`).

    String contents survive unless a check sets `ignore_strings`. Blanking them
    by default cost far more than it bought: in JS and TS a module path is a
    string literal, so `never import from X` - the most common architectural
    rule there is - could never match, and every rule about `className` content
    died with it. Comments, not strings, were the false-positive source this
    stripping exists to remove.

    `fill` is what blanked-out text is replaced with. A caller that needs to
    know *which* characters were removed passes a sentinel instead of a space:
    with a space, a comment's own internal spaces are indistinguishable from
    the code that survived, and `_comment_candidates` would report one site per
    word of every comment.
    """
    d = _dialect(path)
    if not text or d is None:
        return text
    out = list(text)
    n = len(text)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = fill

    i = 0
    while i < n:
        ch = text[i]
        if d["block"] and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            blank(i, end)
            i = end
            continue
        marker = next((m for m in d["line"] if text.startswith(m, i)), None)
        if marker:
            end = text.find("\n", i)
            end = n if end < 0 else end
            blank(i, end)
            i = end
            continue
        if d["triple"] and (text.startswith('"""', i) or text.startswith("'''", i)):
            quote = text[i:i + 3]
            end = text.find(quote, i + 3)
            end = n if end < 0 else end + 3
            if strip_strings:
                blank(i, end)
            i = end
            continue
        if ch in d["quotes"]:
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == ch:
                    j += 1
                    break
                # `${...}` inside a template literal is executable code, not
                # string content, so it is left standing.
                if ch == "`" and text.startswith("${", j):
                    depth, k = 1, j + 2
                    while k < n and depth:
                        depth += (text[k] == "{") - (text[k] == "}")
                        k += 1
                    if strip_strings:
                        blank(i, j)
                    i = j = k
                    continue
                # An unterminated quote is far more likely an apostrophe in
                # prose than a string, so it is bounded to its own line.
                if text[j] == "\n" and ch != "`":
                    break
                j += 1
            # Strings are always parsed, even when their contents are kept: a
            # `//` inside one is part of a URL, not the start of a comment, and
            # treating it as one blanked the rest of the line.
            if strip_strings:
                blank(i, min(j, n))
            i = min(j, n)
            continue
        i += 1
    return "".join(out)


# ---------- rule keys ----------

def rule_key(heading_path, rule_text):
    """Stable id for a rule: its heading path plus its text.

    An unchanged rule keeps its key and so reuses the check authored for it; an
    edited rule gets a new key, which invalidates a check written against the
    old wording rather than applying it to something it never read.
    """
    def norm(s):
        return re.sub(r"\s+", " ", (s or "")).strip().lower()
    digest = hashlib.sha256((norm(heading_path) + "\0" + norm(rule_text)).encode("utf-8"))
    return digest.hexdigest()[:16]


# ---------- corpus ----------

_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# Excluded from a tool line because they belong to the `code` corpus. A tool
# line has to stay one line: it is the unit an ordering finding cites, and a
# whole written file pasted into it makes every such citation unreadable.
_BULK_ARG_FIELDS = ("content", "new_string", "old_string", "new_source", "edits", "prompt")
# Prose the agent wrote *about* the call, not part of the invocation. Keeping it
# put a sentence into a line that command patterns run over, and on real
# sessions the Bash description "Check active gh account" read as a `gh`
# command - condemning the very call that complied with the rule.
_PROSE_ARG_FIELDS = ("description",)
# Generous, because a truncated line is a false-violation generator: cut the
# `gh auth status` off the end of a long compound command and the `gh` call it
# authorised is reported as unaccompanied. The cost of the other direction is
# that a heredoc body inside a command becomes searchable text, which is text
# the agent really did hand to the shell.
_MAX_ARG_CHARS = 2000


def _call_args(inp):
    """The scalar inputs of one call, collapsed to a single searchable line.

    The field a call is *about* leads, whatever order the transcript happened to
    serialise the input in. Every pattern the authoring prompt recommends is
    anchored (`^Bash git commit\\b`), and a `timeout` that sorted itself first
    would leave such a check matching nothing at all - reported as a rule
    nothing triggered, which reads as honest silence rather than a bug.
    """
    inp = inp or {}
    lead = [k for k in ("command", "file_path", "notebook_path") if k in inp]
    parts = []
    for key in lead + [k for k in inp if k not in lead]:
        value = inp[key]
        if key in _BULK_ARG_FIELDS or key in _PROSE_ARG_FIELDS:
            continue
        if isinstance(value, (str, int, float)):
            parts.append(str(value))
        elif isinstance(value, list):
            parts.extend(v for v in value if isinstance(v, str))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:_MAX_ARG_CHARS]


def _apply_edit(buf, old, new, replace_all=False):
    """One write folded into the text accumulated for its path so far.

    An `old_string` the buffer already holds is *substituted*, which is what
    makes a revert visible as a revert: write the bad line, then edit it away,
    and the bad line is gone from the net text rather than sitting beside its
    own replacement. An `old_string` the buffer does not hold belonged to the
    file before the session touched it, and the transcript never carries that
    text, so the new hunk can only be appended - the same partial view `code`
    has always had, no worse.
    """
    if old and old in buf:
        return buf.replace(old, new) if replace_all else buf.replace(old, new, 1)
    if not new:
        return buf
    return (buf + "\n" + new) if buf else new


def _net_code(calls):
    """Net text per written path after replaying every write in order.

    This is the "final diff" a code rule is judged against. `code` carries
    every hunk the session ever wrote, so an attempt written and then reverted
    is still in it, and a check scanning it accuses the agent of code that is
    not in the tree - a violation the reader cannot find when they go looking,
    which is the most trust-destroying kind there is.
    """
    state, order = {}, []
    for c in calls:
        name, inp = c.get("name"), (c.get("input") or {})
        if name not in _WRITE_TOOLS:
            continue
        # `file_path` only, exactly as `code` keys itself. Taking
        # `notebook_path` here too would put a file in the net diff that the
        # all-hunks corpus does not have, and the two are meant to describe one
        # set of paths - a check switching between them would change scope.
        path = inp.get("file_path") or ""
        if not path:
            continue
        if path not in state:
            state[path] = ""
            order.append(path)
        if name == "Write":
            state[path] = inp.get("content") or ""
        elif name == "Edit":
            state[path] = _apply_edit(state[path], inp.get("old_string") or "",
                                      inp.get("new_string") or "",
                                      bool(inp.get("replace_all")))
        elif name == "MultiEdit":
            for e in inp.get("edits") or []:
                e = e or {}
                state[path] = _apply_edit(state[path], e.get("old_string") or "",
                                          e.get("new_string") or "",
                                          bool(e.get("replace_all")))
        else:  # NotebookEdit carries a cell's new source, with no file context
            state[path] = _apply_edit(state[path], "", inp.get("new_source") or "")
    return [{"path": p, "text": state[p]} for p in order if state[p].strip()]


def build_corpus(calls):
    """What the session actually did, in the shapes a check can match.

    `code` groups every hunk written to a path into one entry in write order.
    An Edit carries only its changed hunk, never the surrounding file, so this
    is the whole of the file's text that is knowable from the transcript.
    `final_code` is the same set of paths after the writes are replayed against
    each other - the net effect, which is what a code rule is judged against
    (see `_net_code` and `_source_entries`).

    `tools` is every call in call order, each carrying its own index, so an
    ordering or count constraint is decidable. `commands` and `paths` are sets
    of facts with no order between them, which is why a rule like "check the
    account before running gh" could not be expressed over them at all.
    """
    code, order, commands, paths, tools = {}, [], [], [], []
    for c in calls:
        name, inp = c.get("name"), (c.get("input") or {})
        args = _call_args(inp)
        entry_path = inp.get("file_path") or inp.get("notebook_path") or ""
        tools.append({
            "index": len(tools),
            "name": name or "",
            "args": args,
            "text": ((name or "") + " " + args).strip(),
            "path": entry_path,
            "writes": name in _WRITE_TOOLS,
        })
        if name == "Bash":
            cmd = inp.get("command") or ""
            if cmd:
                commands.append(cmd)
            continue
        path = inp.get("file_path") or ""
        texts = []
        if name == "Write":
            texts.append(inp.get("content") or "")
        elif name == "Edit":
            texts.append(inp.get("new_string") or "")
        elif name == "MultiEdit":
            for e in inp.get("edits") or []:
                texts.append((e or {}).get("new_string") or "")
        elif name == "NotebookEdit":
            texts.append(inp.get("new_source") or "")
        else:
            continue
        if path and path not in code:
            code[path] = []
            order.append(path)
            paths.append(path)
        for t in texts:
            if t:
                code.setdefault(path, []).append(t)
    return {
        "code": [{"path": p, "text": "\n".join(code[p])} for p in order if code.get(p)],
        "commands": commands,
        "paths": paths,
        "tools": tools,
        "final_code": _net_code(calls),
    }


# ---------- matching ----------

def _path_matches(path, globs):
    if not globs:
        return True
    base = os.path.basename(path)
    for g in globs:
        variants = [g, g[3:]] if g.startswith("**/") else [g]
        for v in variants:
            if fnmatch.fnmatch(path, v) or fnmatch.fnmatch(base, v):
                return True
    return False


def _search(pattern, text):
    return re.search(pattern, text, re.MULTILINE)


def _first_line_span(text):
    """Anchor for absence-based kinds: the first non-blank line of the hunk."""
    for m in re.finditer(r"^(.*\S.*)$", text, re.MULTILINE):
        return m.start(), m.end()
    return None


def _candidate_span(check, text):
    """(start, end) of the text to cite when this check fires here, else None."""
    kind = check["kind"]
    if kind == "forbidden_pattern":
        m = _search(check["pattern"], text)
        return (m.start(), m.end()) if m else None
    if kind == "required_pattern":
        if _search(check["pattern"], text):
            return None
        return _first_line_span(text)
    if kind == "forbidden_co_occurrence":
        m = _search(check["pattern"], text)
        if m and _search(check["with_pattern"], text):
            return m.start(), m.end()
        return None
    if kind == "required_co_occurrence":
        m = _search(check["pattern"], text)
        if m and not _search(check["with_pattern"], text):
            return m.start(), m.end()
        return None
    if kind == "required_order":
        first = _search(check["first_pattern"], text)
        second = _search(check["second_pattern"], text)
        if first and second and first.start() > second.start():
            return first.start(), first.end()
        return None
    return None


def _line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# ---------- evidence scoping ----------

def _evidence_source(check):
    """`diff`, `files` or `transcript` - declared, or implied by the kind."""
    return check.get("evidence") or _KIND_EVIDENCE.get(check.get("kind"), ("files",))[0]


def _source_entries(check, corpus):
    """The written-code entries this check reads: the net diff, or every hunk.

    The default is the net diff, for every check including a v1 one. A rule
    about code is a rule about the code that ended up in the tree, and the
    all-hunks corpus lets an attempt the agent already abandoned manufacture a
    violation. `evidence: "files"` opts back in, for the rare rule that is
    about what was written at all rather than what survived.

    A corpus with no `final_code` key at all is a hand-built one (a self-test,
    a test fixture); it is read as it always was rather than as an empty diff,
    because an empty diff would report every such check as never exercised.
    """
    if _evidence_source(check) == "files" or "final_code" not in corpus:
        return corpus.get("code") or []
    return corpus.get("final_code") or []


# ---------- candidate sites for omission rules ----------

def _brace_catch_candidates(text):
    for m in re.finditer(r"\bcatch\b[^\n{]*\{", text):
        depth, i, n = 1, m.end(), len(text)
        while i < n and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        yield (m.start(), m.end()), text[m.end():i - 1 if depth == 0 else n]


def _indented_catch_candidates(text):
    for m in re.finditer(r"^([ \t]*)except\b[^\n]*:[ \t]*$", text, re.MULTILINE):
        indent = len(m.group(1).expandtabs())
        body = []
        for line in text[m.end():].splitlines(True):
            if line.strip():
                depth = len(line[:len(line) - len(line.lstrip(" \t"))].expandtabs())
                if depth <= indent:
                    break
            body.append(line)
        yield (m.start(), m.end()), "".join(body)


def _catch_candidates(text, path):
    """Every catch/except site, read from the comment-stripped view.

    Stripping first is what keeps a commented-out `catch` from being a site,
    and it is why a comment-only body reads as an empty body - which it is, for
    a rule about handling the error. Offsets survive the stripping, so the
    citation is still quoted from the original text.

    Sorted, because the two dialects are scanned separately: unsorted, a file
    holding both would report its sites out of file order, and a reader
    following a finding list expects it to run down the file.

    Both extractors want the handler's opening on one line - `catch (e) {`, or
    an `except ...:` whose body is indented beneath it. A one-line
    `except E: pass`, or a `catch` whose brace sits on the next line, is not
    enumerated. That is the direction to miss in: an un-enumerated site is a
    rule reported `not-exercised`, where a mis-enumerated one would be an
    accusation about a body this function guessed at.
    """
    view = strip_comments_and_strings(text, path)
    return sorted(list(_brace_catch_candidates(view))
                  + list(_indented_catch_candidates(view)))


_COMMENT_FILL = "\x00"


def _comment_candidates(text, path):
    """Every comment, derived from the central stripper rather than re-parsed.

    The stripper is the one place that knows what a comment looks like in each
    dialect and it preserves offsets, so the characters it blanked *are* the
    comments. Re-parsing them here would be a second matcher for one question,
    which is how a block comment's continuation lines were missed the first
    time. A file whose extension names no language yields nothing: guessing at
    comment syntax is how prose got read as code.

    A run stops at the end of its line, so a block comment is one site per
    line. That is deliberate: a site is only citable if it has a line, and
    "the comment on line 40" is what a reader can go and check.
    """
    view = strip_comments_and_strings(text, path, fill=_COMMENT_FILL)
    if view == text:
        return []
    out, start = [], None
    for i, ch in enumerate(view):
        # The sentinel has to be absent from the *original* at this offset, or
        # a source file that happens to hold a NUL byte would read as one long
        # comment - a site the reader would open the file and not find.
        if ch == _COMMENT_FILL and text[i] != _COMMENT_FILL:
            if start is None:
                start = i
            continue
        if start is not None:
            out.append(((start, i), text[start:i]))
            start = None
    if start is not None:
        out.append(((start, len(text)), text[start:]))
    return out


_CANDIDATE_EXTRACTORS = {
    "catch_block": _catch_candidates,
    "comment": _comment_candidates,
}
CANDIDATE_KINDS = tuple(sorted(_CANDIDATE_EXTRACTORS))


def enumerate_candidates(kind, entries, globs=None):
    """Every site in the written code where an omission rule could apply.

    A rule broken by omission leaves no trace: "always implement the catch
    body" is violated by writing nothing, so no pattern can find it. The
    checker has to enumerate the sites and ask about each one - the external
    spec (§8) calls a missing candidate search the most common source of a
    false "all clear". Each site carries the path, the line and the text to
    quote, so a finding about it is citable, and its own body separately, which
    is what the rule gets to look at.

    The opt-in judge tier asks its question about these same records: one
    enumeration, or the deterministic half and the judged half disagree about
    which sites exist.
    """
    extract = _CANDIDATE_EXTRACTORS.get(kind)
    if extract is None:
        return []
    out = []
    for e in entries or []:
        path = e.get("path") or ""
        if not _path_matches(path, globs or []):
            continue
        text = e.get("text") or ""
        for span, body in extract(text, path):
            out.append({
                "kind": kind,
                "path": path,
                "line": _line_of(text, span[0]),
                "span": [span[0], span[1]],
                "match": text[span[0]:span[1]].strip(),
                "text": body,
            })
    return out


def _evaluate_candidates(check, corpus):
    """One finding per enumerated site whose own text does not satisfy the rule."""
    out = []
    globs = check.get("applies_to") or []
    for entry in _source_entries(check, corpus):
        text = entry["text"]
        for cand in enumerate_candidates(check["candidate"], [entry], globs):
            if _search(check["pattern"], cand["text"]):
                continue
            start, end = cand["span"]
            state = ("acknowledged" if _suppressed(text, start, check["id"])
                     else "violated")
            out.append(_finding(check, entry["path"], text, (start, end), state))
    return out


def _suppressed(text, offset, check_id):
    """True when a suppression marker sits on the match's line or the one above."""
    lines = text.splitlines()
    idx = text.count("\n", 0, offset)
    for ln in (idx, idx - 1):
        if 0 <= ln < len(lines):
            m = SUPPRESS_RE.search(lines[ln])
            if m and (not m.group(1) or m.group(1) == check_id):
                return True
    return False


def _finding(check, path, text, span, state, line=None, message=None):
    start, end = span
    matched = text[start:end].strip()
    return {
        "checkId": check["id"],
        "state": state,
        "confidence": check.get("confidence", "low"),
        "path": path,
        "line": _line_of(text, start) if line is None else line,
        "match": matched,
        # `message` is overridden only when the finding is about the check
        # itself rather than about the code - a backend that failed has to say
        # what failed, not restate what the rule forbids.
        "message": check.get("message", "") if message is None else message,
        "ruleRef": check.get("rule_ref", ""),
        "ruleText": check.get("rule_text", ""),
        "kind": check["kind"],
    }


def _evaluate_source(check, entry, normalised=None):
    """Strict and normalised must agree before anything is called a violation."""
    if not _path_matches(entry["path"], check.get("applies_to") or []):
        return None
    strict = entry["text"]
    if normalised is None:
        normalised = strip_comments_and_strings(
            strict, entry["path"], strip_strings=bool(check.get("ignore_strings")))
    strict_span = _candidate_span(check, strict)
    norm_span = _candidate_span(check, normalised)
    if strict_span and norm_span:
        span = norm_span
        if not strict[span[0]:span[1]].strip():
            # The normalised hit landed on text the stripper blanked; nothing
            # citable survives, so it is not reportable as a violation.
            return _finding(check, entry["path"], strict, strict_span, "unclear")
        state = "acknowledged" if _suppressed(strict, span[0], check["id"]) else "violated"
        return _finding(check, entry["path"], strict, span, state)
    if strict_span or norm_span:
        return _finding(check, entry["path"], strict, strict_span or norm_span, "unclear")
    return None


# ---------- the optional ast-grep backend ----------

# The one scoped exception to this repo's stdlib-only rule: an external binary
# the user installs on purpose, verified against a pinned digest and used from
# the tool's own directory. It buys the thing regex cannot do - deciding a
# question about the syntax tree rather than about the characters - which is
# what kills the comment/string false positives that `strip_comments_and_strings`
# can only approximate.
AST_GREP_ENV = "CTXIDE_AST_GREP"
AST_GREP_DIR = Path(__file__).resolve().parent / "vendor"
AST_GREP_NAMES = ("ast-grep.exe", "ast-grep") if os.name == "nt" else ("ast-grep",)
AST_GREP_INSTALL = "python3 install_ast_grep.py"
AST_GREP_MISSING = ("this rule needs ast-grep to check its structural pattern, and "
                    "ast-grep is not installed, so the rule was not checked - "
                    + AST_GREP_INSTALL)
# A pathological pattern against a large file must not hang a build the way a
# pathological regex can; a backend that times out reports `unclear`.
AST_GREP_TIMEOUT = 30


def ast_grep_binary():
    """The consented binary, or None when the backend is unavailable.

    PATH is deliberately never searched. An audit tool that runs whatever
    `ast-grep` some PATH entry happens to provide has handed its verdicts to a
    program nobody reviewed, on a machine whose owner never agreed to it.

    An override that does not resolve returns None rather than falling through
    to the vendored binary: it is a configuration error the user has to see,
    and quietly running a different binary is how they would not.
    """
    override = os.environ.get(AST_GREP_ENV, "").strip()
    candidates = ([Path(override)] if override
                  else [Path(AST_GREP_DIR) / name for name in AST_GREP_NAMES])
    for p in candidates:
        if p.is_file() and os.access(str(p), os.X_OK):
            return p
    return None


def unavailable_reason(check):
    """Why an optional backend cannot run this check, or None.

    A missing optional signal degrades to "not checked", never to a different
    matcher wearing the same check id: an approximation that answers a textual
    question where a structural one was asked would bring back the very false
    positives this backend exists to kill, under a badge saying they had been
    ruled out.
    """
    if check.get("kind") in AST_KINDS and ast_grep_binary() is None:
        return AST_GREP_MISSING
    return None


def _ast_grep_matches(binary, pattern, path, text):
    """(spans, error): character spans of the pattern's matches in `text`.

    The text is written to a temp file keeping the original extension, because
    that is how ast-grep picks a grammar - a hand-maintained extension-to-
    language table here would be a second answer to a question the binary
    already answers.

    One process per file. A session that wrote a hundred files pays a hundred
    spawns for each structural check, which is the price of not maintaining a
    temp-path-to-real-path mapping whose one wrong entry would cite the wrong
    file.
    """
    suffix = os.path.splitext(path or "")[1] or ".txt"
    try:
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / ("target" + suffix)
            target.write_text(text, encoding="utf-8", errors="surrogatepass")
            proc = subprocess.run(
                [str(binary), "run", "--pattern", pattern, "--json=compact",
                 # ast-grep honours ignore files, including the user's global
                 # gitignore. A rule silently skipped because someone ignores
                 # `*.ts` globally would report `clear`, which reads as "the
                 # rule was followed" over a file nothing ever looked at.
                 "--no-ignore", "hidden", "--no-ignore", "global",
                 "--no-ignore", "parent", str(target)],
                capture_output=True, timeout=AST_GREP_TIMEOUT,
                # ast-grep emits UTF-8; decoding it with whatever the machine's
                # locale happens to be turns a non-ASCII match into a decode
                # error, i.e. a working check reporting itself broken.
                text=True, encoding="utf-8", errors="replace")
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        return None, f"ast-grep could not be run ({type(e).__name__}: {e})"
    out = (proc.stdout or "").strip()
    detail = (proc.stderr or "").strip().splitlines()
    if not out and proc.returncode != 0:
        # `ast-grep run` exits 0 whether or not it matched, so a failing exit
        # with nothing on stdout is the binary refusing the job - reading that
        # as "no matches" is how a broken backend would report a clean file.
        return None, ("ast-grep exited " + str(proc.returncode)
                      + (f" ({detail[0][:200]})" if detail else ""))
    try:
        matches = json.loads(out) if out else []
    except ValueError:
        return None, ("ast-grep returned no usable JSON"
                      + (f" ({detail[0][:200]})" if detail else ""))
    if not isinstance(matches, list):
        return None, "ast-grep returned no usable JSON"
    raw = text.encode("utf-8", errors="surrogatepass")
    spans = []
    for m in matches:
        offsets = ((m or {}).get("range") or {}).get("byteOffset") or {}
        start, end = offsets.get("start"), offsets.get("end")
        if not isinstance(start, int) or not isinstance(end, int) \
                or not 0 <= start <= end <= len(raw):
            return None, "ast-grep reported a match with no usable byte range"
        # Byte offsets, not character ones. Slicing the text at a byte offset
        # quotes the wrong code the moment a file holds one non-ASCII
        # character, and a citation the reader cannot find is worse than none.
        spans.append((len(raw[:start].decode("utf-8", "ignore")),
                      len(raw[:end].decode("utf-8", "ignore"))))
    return spans, None


def _evaluate_ast(check, corpus):
    """Structural findings, or an uncitable `unclear` note when the run failed.

    A backend that could not answer must never leave the check reporting
    nothing: no findings is `clear`, which reads as "the rule was followed".
    The note carries no span because no match supports one.
    """
    binary = ast_grep_binary()
    out = []
    for entry in _source_entries(check, corpus):
        if not _path_matches(entry["path"], check.get("applies_to") or []):
            continue
        text = entry["text"]
        spans, error = _ast_grep_matches(binary, check["ast_pattern"],
                                         entry["path"], text)
        if error:
            out.append(_finding(check, entry["path"], text, (0, 0), "unclear",
                                message=error))
            continue
        for start, end in spans:
            state = ("acknowledged" if _suppressed(text, start, check["id"])
                     else "violated")
            out.append(_finding(check, entry["path"], text, (start, end), state))
    return out


def _evaluate_shell(check, corpus):
    out = []
    commands = corpus.get("commands") or []
    if check["kind"] == "forbidden_command":
        for cmd in commands:
            m = _search(check["pattern"], cmd)
            if m:
                state = "acknowledged" if _suppressed(cmd, m.start(), check["id"]) else "violated"
                out.append(_finding(check, SHELL_PATH, cmd, (m.start(), m.end()), state))
    else:  # required_command
        satisfied = any(_search(check["pattern"], c) for c in commands)
        if not satisfied:
            for cmd in commands:
                m = _search(check["trigger_pattern"], cmd)
                if m:
                    state = ("acknowledged" if _suppressed(cmd, m.start(), check["id"])
                             else "violated")
                    out.append(_finding(check, SHELL_PATH, cmd, (m.start(), m.end()), state))
    return out


def _evaluate_path(check, corpus):
    out = []
    for path in corpus.get("paths") or []:
        m = _search(check["pattern"], path)
        if m:
            out.append(_finding(check, PATH_PATH, path, (m.start(), m.end()), "violated"))
    return out


# ---------- the tool log ----------

def _matching_calls(entries, pattern):
    """(entry, match) for every call whose line the pattern hits, in call order."""
    out = []
    for e in entries:
        m = _search(pattern, e["text"])
        if m:
            out.append((e, m))
    return out


def _tool_finding(check, entry, span, stage):
    """A finding citing one call, by its position in the log rather than a line.

    A tool line has no line number of its own, so `line` carries the 1-based
    ordinal of the call. That is the citation a reader can actually check: it
    says which call in the session, which is what an ordering claim rests on.
    """
    text = entry["text"]
    state = "acknowledged" if _suppressed(text, span[0], check["id"]) else "violated"
    f = _finding(check, TOOLS_PATH, text, span, state, line=entry["index"] + 1)
    if stage is not None:
        f["stage"] = stage
    f["toolIndex"] = entry["index"]
    return f


def _stage_note(check, stage, state, detail):
    """A stage report with nothing to cite, for a conditional that never fired.

    An antecedent that never happened has no call to quote, and picking some
    other call to point at would put a citation under a claim no call supports.
    `line` 0 says "no call" rather than naming the first one.
    """
    return {
        "checkId": check["id"],
        "state": state,
        "confidence": check.get("confidence", "low"),
        "path": TOOLS_PATH,
        "line": 0,
        "match": "",
        "message": detail,
        "ruleRef": check.get("rule_ref", ""),
        "ruleText": check.get("rule_text", ""),
        "kind": check["kind"],
        "stage": stage,
    }


def _antecedent(check, entries):
    """The calls that make this check applicable at all, in call order.

    Every tool kind is conditional on something having happened, and this is
    the half that decides `not-exercised` from `clear`. Reporting `clear` for a
    rule whose trigger never came up reads as "the rule was followed" when the
    truth is that it was never tested.
    """
    kind = check["kind"]
    if kind == "tool_precedes":
        firsts = _matching_calls(entries, check["first_pattern"])
        seconds = _matching_calls(entries, check["second_pattern"])
        # Both sides must be present for an order to exist between them.
        return firsts + seconds if firsts and seconds else []
    if kind == "tool_arg_matches":
        return _matching_calls(entries, check["tool_pattern"])
    if kind in ("tool_required", "writes_to_path"):
        return _matching_calls(entries, check["trigger_pattern"])
    return _matching_calls(entries, check["pattern"])


def _evaluate_tools(check, corpus):
    entries = corpus.get("tools") or []
    kind = check["kind"]
    fired = _antecedent(check, entries)
    if not fired:
        return [_stage_note(check, STAGE_ANTECEDENT, "not-exercised",
                            "nothing in this session triggered this rule, so it was "
                            "never tested")]
    satisfied = [_stage_note(check, STAGE_SATISFIED, "clear",
                             "this rule was triggered and satisfied")]

    if kind == "tool_forbidden":
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_UNCONDITIONAL)
                for e, m in fired]

    if kind == "tool_precedes":
        first_at = _matching_calls(entries, check["first_pattern"])[0][0]["index"]
        early = [(e, m) for e, m in _matching_calls(entries, check["second_pattern"])
                 if e["index"] < first_at]
        if not early:
            return satisfied
        # Cite the call that jumped the queue: it is the event that went wrong.
        e, m = early[0]
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)]

    if kind == "tool_never_without_prior":
        priors = [(e["index"], pm.start())
                  for e, pm in _matching_calls(entries, check["prior_pattern"])]
        # A prior earlier *within the same line* counts. `gh auth status; gh pr
        # list` in one Bash call is how an agent naturally writes "check, then
        # run", and comparing call indices alone condemns it - a false
        # accusation on the most compliant shape there is.
        out = [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)
               for e, m in fired
               if not any(i < e["index"] or (i == e["index"] and off < m.start())
                          for i, off in priors)]
        return out or satisfied

    if kind == "tool_required":
        if _matching_calls(entries, check["pattern"]):
            return satisfied
        e, m = fired[0]
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)]

    if kind == "writes_to_path":
        if any(e["writes"] and _search(check["pattern"], e["path"]) for e in entries):
            return satisfied
        e, m = fired[0]
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)]

    if kind == "tool_arg_matches":
        out = [_tool_finding(check, e, (0, len(e["text"])), STAGE_MISSED)
               for e, _ in fired if not _search(check["arg_pattern"], e["args"])]
        return out or satisfied

    # tool_call_count. A count over zero calls is unreachable here (the
    # antecedent is a matching call), which is deliberate: a session that never
    # did the thing has nothing to quote, so `tool_required` with a trigger is
    # the kind for "it must happen at all".
    n = len(fired)
    ceiling, floor = check.get("max_calls"), check.get("min_calls")
    if ceiling is not None and n > ceiling:
        e, m = fired[ceiling]
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)]
    if floor is not None and n < floor:
        e, m = fired[-1]
        return [_tool_finding(check, e, (m.start(), m.end()), STAGE_MISSED)]
    return satisfied


def evaluate_checks(checks, corpus, limit=20):
    """Apply loaded checks to a session corpus and return findings.

    Stripping is done once per corpus entry rather than once per check: it is a
    character-by-character scan, and every check on a document would otherwise
    repeat it over the same files.

    The limit counts only findings that report something about a call or a hunk.
    A tool kind always says which stage it reached, satisfied included, so
    letting those notes spend the budget would let twenty quiet rules stop the
    twenty-first from ever being evaluated - dropping the one real violation and
    leaving the block reading as if nothing happened.
    """
    findings = []
    normalised = {}
    for check in checks:
        if unavailable_reason(check):
            # Skipped rather than approximated. `check_block` is where the
            # reader is told the rule went unchecked; producing findings from
            # some other matcher here would report it as decided.
            continue
        if check["kind"] in AST_KINDS:
            findings.extend(_evaluate_ast(check, corpus))
        elif check["kind"] in TOOL_KINDS:
            findings.extend(_evaluate_tools(check, corpus))
        elif check["kind"] in CANDIDATE_CHECK_KINDS:
            findings.extend(_evaluate_candidates(check, corpus))
        elif check["kind"] in SHELL_KINDS:
            findings.extend(_evaluate_shell(check, corpus))
        elif check["kind"] in PATH_KINDS:
            findings.extend(_evaluate_path(check, corpus))
        else:
            drop_strings = bool(check.get("ignore_strings"))
            reads = _evidence_source(check)
            for idx, entry in enumerate(_source_entries(check, corpus)):
                # Keyed on the variant and the corpus too: checks differ on
                # whether string contents are stripped, and on whether they
                # read the net diff or every hunk, so one cached view cannot
                # serve both - and index 0 is a different file in each corpus.
                key = (reads, idx, drop_strings)
                if key not in normalised:
                    normalised[key] = strip_comments_and_strings(
                        entry["text"], entry["path"], strip_strings=drop_strings)
                f = _evaluate_source(check, entry, normalised[key])
                if f:
                    findings.append(f)
        if sum(1 for f in findings if f["match"]) >= limit:
            break
    return _capped(findings, limit)


def _capped(findings, limit):
    """Keep at most `limit` cited findings, and every stage note besides.

    A note carries no span and is one per check, so it cannot run away; a cited
    finding is one per matching call and can.
    """
    out, cited = [], 0
    for f in findings:
        if f["match"]:
            cited += 1
            if cited > limit:
                continue
        out.append(f)
    return out


# ---------- the opt-in judge tier ----------

# One rule x one candidate x one call, and a ceiling on how many candidates one
# record may spend. A rule with two hundred sites would otherwise turn a single
# audit into two hundred model calls before the reader saw anything.
JUDGE_CANDIDATE_LIMIT = 20

# What a bucket-C verdict is worth, said in the record itself rather than left
# to a legend: judge reliability without validity, position bias and
# self-preference are all documented, so a semantic verdict annotates and never
# decides.
JUDGE_ADVISORY_NOTE = ("judged semantically by the opt-in LLM tier, so this verdict is "
                       "advisory: it can flag a rule for a reader but never call it "
                       "violated on its own")
JUDGE_RAN_NOTE = ("answered by the opt-in LLM judge tier, once per site this tool "
                  "enumerated itself")
# The tier is on and this record still went unasked. Saying "the tier is off"
# here would send the reader to turn on something that is already on, and
# saying nothing would report an unasked rule as an answered one.
JUDGE_NOTHING_TO_ASK = ("the opt-in judge tier is on, but this session produced nothing "
                        "this rule could be asked about")
JUDGE_NO_SPAN = ("the judge reported a violation but quoted nothing that appears in the "
                 "content it was given, so it is not reportable as one")


def _unanswered(record, answer, path, advisory):
    """A question the judge never got to answer, reported as unchecked.

    Not `unclear`: an optional signal going missing must degrade to "not
    checked", never to "there might be something here". A budget that ran out
    and a backend that was down are facts about the run, not about the code.
    """
    return _judge_finding(record, path, "", (0, 0), "note",
                          answer.get("reason", ""), "unavailable", advisory, line=0)


def _record_key(record):
    """The rule identity a cached verdict is keyed on."""
    return (record.get("rule_key")
            or rule_key(record.get("rule_ref", ""),
                        record.get("rule_text") or record.get("statement") or ""))


def _judge_finding(record, path, text, span, state, message, verdict, advisory,
                   line=None):
    """A judge verdict in the same shape every deterministic finding uses.

    Same shape on purpose: a reader should not have to learn a second record
    format to see what was found, and every consumer that already knows how to
    cite a finding cites this one too. `advisory` is the display cap, read by
    `_state_from` and by the caller that paints the block.
    """
    shim = dict(record)
    shim.setdefault("kind", record.get("bucket") or "judged")
    # A semantic verdict is always `low`, whatever the record claims: the
    # author's confidence is in the rule being checkable, not in a model's read
    # of a whole file, and a `high` badge beside an advisory note would invite
    # exactly the trust the display cap exists to withhold. A bucket-B verdict
    # keeps the record's own confidence - the site was enumerated here and the
    # question is narrow - but never rises above `medium`, which is what decides
    # whether a finding may paint a block red.
    if advisory:
        shim["confidence"] = "low"
    elif shim.get("confidence") == "high":
        shim["confidence"] = "medium"
    elif shim.get("confidence") not in CONFIDENCES:
        # Undeclared is `low`, and `low` never paints a block. A judged record
        # is not put through the fixture gate that makes `confidence` mandatory
        # everywhere else, so an author who left it out must not get a red badge
        # they never asked for.
        shim["confidence"] = "low"
    f = _finding(shim, path, text, span, state, line=line, message=message)
    f["judge"] = True
    f["judgeVerdict"] = verdict
    if advisory:
        f["advisory"] = True
    return f


def _injection_findings(record, request, advisory):
    """One note per attempt, inside the judged content, to instruct the judge.

    Reported and never obeyed. For a tool whose only output is trust verdicts,
    content that talks the judge into a green is the one attack that turns the
    product against its user, so the attempt is a finding in its own right -
    with state `note`, because the verdict it tried to change must not move.
    """
    import judge_tier
    out = []
    where = request["evidence"][0][0] if request["evidence"] else ""
    for excerpt in (request.get("injections") or [])[:3]:
        # No span: the excerpt is quoted in the message instead, because a
        # citation pointing at line 0 is one the reader cannot go and check,
        # and the offsets here are into content that was clipped for the model.
        out.append(_judge_finding(
            record, where, "", (0, 0), "note",
            f"{judge_tier.INJECTION_NOTE} — {excerpt}", "injection-attempt",
            advisory, line=0))
    return out


def _quote_span(text, quote, near=0):
    """Where the judge's quoted evidence sits in the content, or None.

    A verdict the reader cannot go and look at is not reportable, so a quote
    that is not in what the judge was given downgrades the finding rather than
    citing a line that says something else.
    """
    if not quote:
        return None
    pos = text.find(quote, near)
    if pos == -1:
        pos = text.find(quote)
    return (pos, pos + len(quote)) if pos != -1 else None


def _candidate_evidence(cand):
    """The site as the judge sees it: its own opening line plus its body.

    The body alone is not enough. An omission rule is broken by a body that is
    *empty*, and a judge given nothing has nothing it could quote - which the
    citation gate would then read as a hallucination and throw away the one
    verdict the rule exists for. The opening line is the quotable half. A
    candidate whose body already is its whole text (a comment) is not doubled.
    """
    head, body = cand.get("match") or "", cand.get("text") or ""
    if body.strip() and body.strip() in head:
        return head
    return head + body


def _judge_candidates(record, corpus, judge):
    """Bucket B: this tool enumerates the sites, the judge answers about each one.

    The deterministic half is the enumeration, which is why a bucket-B verdict
    is not display-capped: the site, its path and its line are facts this tool
    established, and the only thing asked of the model is the narrow question
    the record states.

    Returns the findings and how many sites were actually *answered* - a site
    the budget or a dead backend swallowed is not one the rule was checked
    against, and counting it would let the block read `clear`.
    """
    import judge_tier
    out, asked, answered = [], 0, 0
    globs = record.get("applies_to") or []
    for entry in _source_entries(record, corpus):
        for cand in enumerate_candidates(record["candidate"], [entry], globs):
            if asked >= JUDGE_CANDIDATE_LIMIT:
                return out, answered
            asked += 1
            request = judge_tier.judge_request(
                _record_key(record), record.get("statement", ""),
                record.get("examples_positive"), record.get("examples_negative"),
                [(f"{cand['path']}:{cand['line']}", _candidate_evidence(cand))],
                judge.model)
            answer = judge.ask(request)
            if not answer.get("unavailable"):
                answered += 1
            out.extend(_injection_findings(record, request, False))
            out.append(_fold_candidate(record, entry, cand, answer))
    return out, answered


def _fold_candidate(record, entry, cand, answer):
    if answer.get("unavailable"):
        return _unanswered(record, answer, cand["path"], False)
    text = entry["text"]
    start, end = cand["span"]
    verdict = answer["verdict"]
    reason = answer.get("reason") or record.get("message", "")
    if verdict == "violated":
        quote = answer.get("evidence", "")
        # The quote has to be in what the judge was *given*, not merely
        # somewhere in the file: a model that quotes a line from the `try`
        # block would otherwise have the rule about the `catch` cited against
        # code it does not govern. The offset is then taken from the file, at
        # or after the site, so the line number is the real one.
        span = (_quote_span(text, quote, start)
                if quote and quote in _candidate_evidence(cand) else None)
        if span is None or span[0] < start:
            return _judge_finding(record, cand["path"], text, (start, end), "unclear",
                                  f"{JUDGE_NO_SPAN}. {reason}".strip(), verdict, False)
        state = ("acknowledged" if _suppressed(text, span[0], record.get("id", ""))
                 else "violated")
        return _judge_finding(record, cand["path"], text, span, state, reason,
                              verdict, False)
    if verdict == "unclear":
        return _judge_finding(record, cand["path"], text, (start, end), "unclear",
                              reason, verdict, False)
    # Compliant. It carries no span because there is nothing wrong to point at,
    # so it is a note: the block reads `clear` from the sites having been
    # examined, not from this one finding.
    return _judge_finding(record, cand["path"], text, (start, end), "note",
                          reason, verdict, False)


def _judged_evidence(record, corpus):
    """The minimal session content a bucket-C record's question is about."""
    if _evidence_source(record) == "transcript":
        log = "\n".join(e["text"] for e in corpus.get("tools") or [])
        return [("(tools)", log)] if log else []
    globs = record.get("applies_to") or []
    return [(e["path"], e["text"]) for e in _source_entries(record, corpus)
            if _path_matches(e["path"], globs)]


def _judge_semantic(record, corpus, judge):
    """Bucket C: one question about the session's own evidence, display-capped."""
    import judge_tier
    pieces = _judged_evidence(record, corpus)
    if not pieces:
        # Nothing the rule is about happened, so there is nothing to ask. A
        # call here would buy an answer about an empty page.
        return []
    request = judge_tier.judge_request(
        _record_key(record), record.get("statement", ""),
        record.get("examples_positive"), record.get("examples_negative"),
        pieces, judge.model)
    answer = judge.ask(request)
    out = _injection_findings(record, request, True)
    if answer.get("unavailable"):
        out.append(_unanswered(record, answer, pieces[0][0], True))
        return out
    reason = answer.get("reason") or ""
    quote = answer.get("evidence", "")
    for name, text in request["evidence"]:
        span = _quote_span(text, quote)
        if span is None:
            continue
        state = "unclear" if answer["verdict"] == "violated" else "note"
        out.append(_judge_finding(record, name, text, span, state, reason,
                                  answer["verdict"], True))
        return out
    # No citable span. A violation without one is not reportable as one, and a
    # compliant answer never had anything to cite in the first place.
    message = f"{JUDGE_NO_SPAN}. {reason}".strip() if answer["verdict"] == "violated" else reason
    out.append(_judge_finding(record, pieces[0][0], "", (0, 0), "note", message,
                              answer["verdict"], True, line=0))
    return out


def judge_records(records, corpus, judge):
    """Ask the opt-in judge about the records this tool cannot decide itself.

    Returns the findings, the records that genuinely ran (so the block can read
    `clear` rather than `not-checkable` when the judge examined its sites),
    whether anything was in scope at all, and one note per record saying what
    became of it - a record the tier was on for but never asked about must not
    report itself as answered, nor keep telling the reader the tier is off.
    """
    findings, ran, in_scope, notes = [], [], False, {}
    for record in records:
        rid = record.get("id")
        if record.get("bucket") == "hybrid" and record.get("candidate") in CANDIDATE_KINDS:
            f, asked = _judge_candidates(record, corpus, judge)
            findings.extend(f)
            notes[rid] = JUDGE_RAN_NOTE if asked else JUDGE_NOTHING_TO_ASK
            if asked:
                ran.append(record)
                in_scope = True
        else:
            f = _judge_semantic(record, corpus, judge)
            findings.extend(f)
            notes[rid] = JUDGE_ADVISORY_NOTE if f else JUDGE_NOTHING_TO_ASK
    return findings, ran, in_scope, notes


# ---------- loading and the self-test gate ----------

def _selftest_path(check):
    globs = check.get("applies_to") or []
    if not globs:
        return "src/selftest.ts"
    g = globs[0]
    if g.startswith("**/"):
        g = g[3:]
    name = g.replace("*", "selftest").lstrip("/")
    return name if "/" in name else "src/" + name


def _selftest_tools(snippet):
    """One tool call per non-blank line of the snippet, in the order given.

    A tool-kind self-test has to be able to express a *sequence*, or an
    ordering check could never be tested at all - which is the one thing the
    load-time gate exists to catch.
    """
    entries = []
    for line in (snippet or "").splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, args = line.partition(" ")
        args = args.strip()
        entries.append({
            "index": len(entries),
            "name": name,
            "args": args,
            "text": line,
            # A write's path is its first argument, which is how the harness
            # spells every write tool's input.
            "path": args.split(" ")[0] if name in _WRITE_TOOLS and args else "",
            "writes": name in _WRITE_TOOLS,
        })
    return entries


def _selftest_corpus(check, snippet):
    if check["kind"] in TOOL_KINDS:
        return {"code": [], "commands": [], "paths": [], "tools": _selftest_tools(snippet)}
    if check["kind"] in SHELL_KINDS:
        return {"code": [], "commands": [snippet], "paths": []}
    if check["kind"] in PATH_KINDS:
        return {"code": [], "commands": [], "paths": [snippet]}
    return {"code": [{"path": _selftest_path(check), "text": snippet}],
            "commands": [], "paths": []}


def _selftest_findings(check, snippet):
    return evaluate_checks([check], _selftest_corpus(check, snippet))


def _violates(check, snippet):
    return any(f["state"] == "violated" for f in _selftest_findings(check, snippet))


def _backend_complaint(findings, check):
    """What an external backend said about a fixture, if it said anything.

    Without this a record whose language ast-grep has no grammar for is
    demoted with "your should_match case did not fire", which sends the author
    off to rewrite a pattern that was never the problem.
    """
    for f in findings:
        if f["state"] == "unclear" and f["message"] != check.get("message", ""):
            return f" - {f['message']}"
    return ""


def _fixtures(check):
    """The record's fixture cases, under either the v1 or the v2 field name.

    Carrying both is refused in `_validate_declaration`, so this never has to
    pick between two versions of one thing.
    """
    return check.get("self_test") or check.get("fixtures") or {}


def _validate_declaration(check, kind):
    """Structural reason a record's v2 declaration is unusable, or None.

    Every field here is optional so a v1 file is unaffected, but a value
    outside its closed set is refused rather than ignored: a record that names
    a bucket or an evidence source this tool does not have is a record whose
    author believed something about it that is not true.
    """
    for field, allowed in (("scope", SCOPES), ("bucket", BUCKETS)):
        if check.get(field) is not None and check[field] not in allowed:
            return f"`{field}` must be one of {', '.join(allowed)}"
    if check.get("bucket") is not None and not str(check.get("rule_ref") or "").strip():
        # `rule_ref` is what binds a record to a block. A demoted or parked
        # record that binds to nothing is invisible on every screen, which is
        # the silent drop this phase exists to remove - so a v2 record has to
        # say which rule it is about before it can be reported as unchecked.
        return "a record declaring a `bucket` requires a `rule_ref` to bind to"
    if check.get("self_test") is not None and check.get("fixtures") is not None:
        # `fixtures` is only the v2 name for `self_test`. Two copies of one
        # thing drift, and gating a record on the stale copy would let a check
        # whose real cases fail load as if it had reproduced them.
        return "carries both `self_test` and `fixtures`; they are one field under two names"
    source = check.get("evidence")
    if source is not None:
        if source not in EVIDENCE_SOURCES:
            return f"`evidence` must be one of {', '.join(EVIDENCE_SOURCES)}"
        readable = _KIND_EVIDENCE.get(kind or "", ())
        if kind and source not in readable:
            return (f"kind `{kind}` cannot read `{source}` evidence; it reads "
                    + " or ".join(readable))
    if check.get("statement") is not None and not str(check["statement"]).strip():
        return "`statement` must not be empty"
    for field in ("examples_positive", "examples_negative"):
        value = check.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or not all(
                isinstance(x, str) and x.strip() for x in value):
            return f"`{field}` must be a list of non-empty strings"
    return None


def _validate_judged(check):
    """Structural reason a hybrid or judged record is unusable, or None.

    Such a record carries no pattern for the load-time gate to re-run, so its
    examples are the whole of what constrains the judge that will read it. The
    literature rates exactly one judge mode reliable - one narrow question with
    a positive and a negative case - and a record carrying neither would hand
    the judge back the prose the compilation step existed to replace.
    """
    if not isinstance(check, dict) or not check.get("id"):
        return "check is missing an id"
    reason = _validate_declaration(check, None)
    if reason:
        return reason
    if not str(check.get("statement") or "").strip():
        return f"bucket `{check['bucket']}` requires a `statement` to ask"
    for field in ("examples_positive", "examples_negative"):
        if not (check.get(field) or []):
            return f"bucket `{check['bucket']}` requires `{field}`"
    if check["bucket"] == "hybrid" and check.get("candidate") not in CANDIDATE_KINDS:
        # Hybrid means the sites are enumerated here and only the question is
        # judged. Without a candidate kind there is no deterministic half.
        return ("bucket `hybrid` extracts its candidates deterministically, so it "
                f"requires a `candidate` from {', '.join(CANDIDATE_KINDS)}")
    return None


def _validate(check):
    """Structural reason this check cannot be used, or None."""
    if not isinstance(check, dict) or not check.get("id"):
        return "check is missing an id"
    kind = check.get("kind")
    if kind not in VOCABULARY:
        return f"unknown kind `{kind}` - the predicate vocabulary is closed"
    if (kind in SOURCE_KINDS or kind in CANDIDATE_CHECK_KINDS
            or kind in AST_KINDS) and not check.get("applies_to"):
        # Without globs every written file is in scope, including the .py and
        # .md the rule never meant, which is how an under-specified check
        # accuses the agent in a language the rule does not govern.
        return f"kind `{kind}` requires a non-empty `applies_to`"
    reason = _validate_declaration(check, kind)
    if reason:
        return reason
    for field in VOCABULARY[kind]:
        if not check.get(field):
            return f"kind `{kind}` requires `{field}`"
        if field == "ast_pattern":
            # An ast-grep pattern is code, not a regex. Compiling it as one
            # would refuse `catch ($$$A) { }` - exactly the patterns this
            # backend exists for - for failing at a language it is not written
            # in. What validates it is its own fixtures, re-run below. The type
            # check is not free-standing pedantry: skipping the compile also
            # skipped the only thing that insisted the field was a string, and
            # a list here reaches `subprocess` as an argv entry and raises.
            if not isinstance(check[field], str):
                return "`ast_pattern` must be a string"
            continue
        if field == "candidate":
            if check[field] not in CANDIDATE_KINDS:
                return (f"`candidate` must be one of {', '.join(CANDIDATE_KINDS)} - "
                        "the enumerable site kinds are a closed set")
            continue
        try:
            re.compile(check[field])
        except re.error as e:
            return f"`{field}` is not a valid Python regex ({e})"
    if kind == "tool_call_count":
        bounds = [check.get(f) for f in ("min_calls", "max_calls")]
        if all(b is None for b in bounds):
            return "kind `tool_call_count` requires `min_calls`, `max_calls` or both"
        for b in bounds:
            if b is not None and (not isinstance(b, int) or isinstance(b, bool) or b < 0):
                return "`min_calls` and `max_calls` must be non-negative integers"
        floor, ceiling = bounds
        # No self-test can catch this: a `should_not_match` snippet passes by
        # never firing the pattern at all, so an unsatisfiable window loads
        # cleanly and then accuses every session in which the pattern fires.
        if floor is not None and ceiling is not None and floor > ceiling:
            return "`min_calls` is above `max_calls`, so no session could satisfy this check"
    if check.get("confidence") not in CONFIDENCES:
        return "confidence must be high, medium or low"
    tests = _fixtures(check)
    if not tests.get("should_match") or not tests.get("should_not_match"):
        return "self-test must carry both should_match and should_not_match cases"
    return None


def _self_test_failure(check):
    """The first self-test this tool's own matcher disagrees with, or None."""
    if unavailable_reason(check):
        # The fixtures are the gate, and with the backend absent they cannot
        # run. Refusing the record here would report the rule as inexpressible
        # when installing one optional binary is what it actually needs; the
        # block says `not-checkable` either way, so nothing is claimed about it.
        return None
    tests = _fixtures(check)
    for snippet in tests["should_match"]:
        findings = _selftest_findings(check, snippet)
        if not any(f["state"] == "violated" for f in findings):
            return (f"self-test failed: should_match case did not fire "
                    f"({snippet[:80]!r})" + _backend_complaint(findings, check))
    for snippet in tests["should_not_match"]:
        if _violates(check, snippet):
            return f"self-test failed: should_not_match case fired ({snippet[:80]!r})"
    return None


def _rejection(check_id, reason, rule_ref="", rule_text=""):
    """A refused check, carrying `rule_ref` so it binds to its block like any
    other entry, and `ruleRef` for the frontend's camelCase records."""
    return {"id": check_id, "reason": reason, "rule_ref": rule_ref,
            "ruleRef": rule_ref, "ruleText": rule_text}


def _parked(entry, why, bucket, from_bucket=None):
    """A record this tool cannot decide, named so the reader can see it is unchecked."""
    out = {
        "id": entry.get("id") or "(unnamed)",
        "rule_ref": entry.get("rule_ref", ""),
        "ruleRef": entry.get("rule_ref", ""),
        "ruleText": entry.get("rule_text", ""),
        "statement": entry.get("statement", ""),
        "bucket": bucket,
        "why": why,
    }
    if from_bucket:
        out["fromBucket"] = from_bucket
    return out


def _reworded(entry, notes):
    """A parked entry whose reason for being parked no longer holds."""
    why = notes.get(entry.get("id"))
    return dict(entry, why=why) if why else entry


_JUDGE_OFF = "the opt-in judge tier is off, so this rule was not checked"

# The command that compiles a guideline document's rules into a reviewed checks
# file. Named in every report that finds an uncompiled rule: the analysis side
# never runs it, but a gap the reader cannot act on is a dead end.
COMPILE_COMMAND = "/compile-rules"


def compile_hint(docs, stale=False):
    """The command that compiles these documents, named so the reader can run it."""
    names = [str(d) for d in docs if d]
    listed = ", ".join(names[:3])
    if len(names) > 3:
        listed += f" and {len(names) - 3} more"
    verb = "re-run" if stale else "run"
    return f"{verb} {COMPILE_COMMAND}" + (f" on {listed}" if listed else "")


# The four states a rule can be in with respect to the compiler. The counts and
# the per-block hint read the same function, or the report would tell a reader
# a rule is compiled while the block under it asks them to compile it.
COMPILE_STATES = ("compiled", "stale", "refused", "uncompiled")


def compile_state(block, loaded):
    """This rule's compile state, from its document's loaded checks payload.

    `refused` is an answer the compiler gave and this tool can report - an
    explicit not-checkable, or a bucket parked for the opt-in judge. A record
    that did not survive the loader (demoted, rejected) is `uncompiled`, not
    refused: it produced no answer about the rule, and re-compiling is the fix.
    """
    if not loaded:
        return "uncompiled"
    key = rule_key(block.get("title"), block.get("content"))
    applied = stale = False
    for c in loaded.get("checks") or []:
        if not _entry_matches_block(c, block):
            continue
        if c.get("rule_key") and c["rule_key"] != key:
            stale = True
        else:
            applied = True
    if applied:
        return "compiled"
    if stale:
        return "stale"
    answered = ((loaded.get("notCheckable") or []) + (loaded.get("judged") or []))
    if any(_entry_matches_block(e, block) for e in answered):
        return "refused"
    return "uncompiled"


def compile_status(blocks, loaded):
    """How many of a document's rules the compiler has answered, and how many not.

    Counted per rule-stating block, not per check: a checks file that compiled
    two rules out of thirty is mostly uncompiled, and counting its checks would
    report the document as covered.
    """
    out = {"rules": 0, "checksFile": (loaded or {}).get("source", "")}
    out.update({state: 0 for state in COMPILE_STATES})
    for block in blocks:
        if not _looks_like_a_rule(block):
            continue
        out["rules"] += 1
        out[compile_state(block, loaded)] += 1
    return out


def load_checks(data):
    """Validate and gate a checks payload. Returns accepted, rejected, not-checkable.

    A check only survives if this tool's matcher reproduces the check's own
    fixtures, so a check whose author misread the vocabulary is refused rather
    than pointed at a developer's code.

    Two v2 outcomes sit beside the accepted and refused lists. `demoted` holds
    a deterministic record whose fixtures did not reproduce: it falls to the
    `judged` bucket and *says so*, rather than disappearing into a generic
    refusal, because the whole point of re-running fixtures is that a broken
    check must be visible as a broken check. `judged` holds the records that
    were never deterministic to begin with. Neither is applied.
    """
    checks, rejected, demoted, judged, judgeable = [], [], [], [], []
    for raw in (data or {}).get("checks") or []:
        entry = raw if isinstance(raw, dict) else {}
        bucket = entry.get("bucket")
        reason = None
        if bucket is not None and bucket not in BUCKETS:
            reason = f"`bucket` must be one of {', '.join(BUCKETS)}"
        elif bucket in ("hybrid", "judged"):
            reason = _validate_judged(entry)
            if reason is None:
                judged.append(_parked(
                    entry, f"bucket `{bucket}` needs a judge, and " + _JUDGE_OFF, bucket))
                judgeable.append(entry)
        else:
            reason = _validate(raw)
            failure = _self_test_failure(raw) if reason is None else None
            if reason is None and failure and bucket:
                # A record that declares its bucket takes the v2 path and is
                # demoted. One that does not is a v1 record, refused exactly as
                # it always was: moving it would change what every existing
                # checks file reports about itself.
                demoted.append(_parked(
                    entry, f"its fixtures did not reproduce here ({failure}), so it "
                           "was demoted to the `judged` bucket; " + _JUDGE_OFF,
                    "judged", from_bucket="deterministic"))
                # Only if the judge could actually read it: a demoted record
                # that carries no statement and no examples would hand the
                # judge back the prose the compile step existed to replace.
                if _validate_judged(dict(entry, bucket="judged")) is None:
                    judgeable.append(entry)
            elif reason is None and failure:
                reason = failure
            elif reason is None:
                checks.append(raw)
        if reason:
            rejected.append(_rejection(entry.get("id") or "(unnamed)", reason,
                                       entry.get("rule_ref", ""),
                                       entry.get("rule_text", "")))
    return {
        "source": (data or {}).get("source", ""),
        "checks": checks,
        "rejected": rejected,
        "notCheckable": list((data or {}).get("not_checkable") or []),
        "demoted": demoted,
        "judged": judged,
        # The full records behind `demoted` and `judged`, for the opt-in judge
        # tier. Deliberately not on any block payload: they carry the whole rule
        # text and both example lists, and the parked entries above are what a
        # reader needs to see.
        "judgeable": judgeable,
    }


def find_checks_file(doc_path):
    """`<doc>.checks.json` beside the document, or `<stem>.checks.json`."""
    if not doc_path:
        return None
    p = Path(doc_path)
    for candidate in (p.with_name(p.name + ".checks.json"),
                      p.with_name(p.stem + ".checks.json")):
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=256)
def checks_for_doc(doc_path):
    """Loaded, gated checks for a rule document, or None when it has no file.

    Cached per path: checks files do not change during a run, and the same
    document is re-assessed once per turn.
    """
    path = find_checks_file(doc_path)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {"source": str(path), "checks": [], "notCheckable": [],
                "rejected": [_rejection("(file)", f"checks file unreadable: {e}")],
                "demoted": [], "judged": [], "judgeable": []}
    loaded = load_checks(data)
    loaded["source"] = loaded.get("source") or str(path)
    return loaded


# ---------- fallback for documents with no checks file ----------

NEGATION_RE = re.compile(r"\b(never|don't|do not|avoid|must not|no longer)\b[^.\n]{0,40}?"
                         r"`([A-Za-z_][A-Za-z0-9_.]{2,}(?:\(\))?)`", re.I)
GLOB_RE = re.compile(r"`(\*{1,2}[^`\s]*\.\w+|[\w*/.-]+\.\w+)`")
# A bare lowercase word in backticks is as likely to be a status name or an
# English word as an identifier, and matching one against source text is how
# "Never guess a block into `undelivered`" became a violation of itself.
CODE_SHAPED_RE = re.compile(r"[A-Z_.]|\(\)$")

MAX_FALLBACK_CHECKS = 5
# An extracted rule names no globs of its own most of the time, and leaving
# `applies_to` empty would put every written file in scope - including the
# markdown where the rule's own identifier is quite likely to be discussed.
# Mechanical extraction therefore looks only at files whose language it knows.
CODE_GLOBS = tuple(sorted("**/*" + ext for ext in _HASH_LANG_EXT | _C_LANG_EXT))


def fallback_checks(block):
    """Mechanically extracted checks for a rule doc that has no checks file.

    Deliberately narrow: a negation cue followed closely by a backticked token
    that is shaped like code, scoped by the globs the block names or, failing
    that, to known code files only. Bare prose
    ("never be careless") yields nothing, and nothing is ever routed to the
    shell - reading a code identifier as a shell command is exactly the phantom
    violation this architecture replaces. Low confidence by construction.
    """
    content = block.get("content") or ""
    globs = [g for g in GLOB_RE.findall(content) if "*" in g or g.startswith(".")]
    out = []
    seen = set()
    for _cue, ident in NEGATION_RE.findall(content):
        if ident.lower() in seen or not CODE_SHAPED_RE.search(ident):
            continue
        seen.add(ident.lower())
        if len(out) >= MAX_FALLBACK_CHECKS:
            break
        out.append({
            "id": "fallback-" + re.sub(r"[^a-z0-9]+", "-", ident.lower()).strip("-"),
            "rule_ref": block.get("title", ""),
            "rule_text": (content or "").strip()[:200],
            "domain": "source",
            "kind": "forbidden_pattern",
            "pattern": r"\b" + re.escape(ident.rstrip("()")) + r"\b",
            "applies_to": globs or list(CODE_GLOBS),
            "confidence": "low",
            "message": f"`{ident}` appears in written code, and this rule forbids it.",
        })
    return out


# ---------- per-block verdict ----------

def _normalise_ref(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _entry_matches_block(entry, block):
    """Bind a checks-file entry to a block by heading, or by source line number."""
    ref = (entry.get("rule_ref") or "").strip()
    if not ref:
        return False
    if re.fullmatch(r"\d+", ref):
        start, end = block.get("start_line"), block.get("end_line")
        return bool(start and end and start <= int(ref) <= end)
    ref_n, title_n = _normalise_ref(ref), _normalise_ref(block.get("title"))
    if not ref_n or not title_n:
        return False
    return ref_n == title_n or title_n in ref_n or ref_n in title_n


# Every cue the mechanical fallback reads (NEGATION_RE) has to be in here too:
# a block the fallback is willing to accuse is a rule, and one the counts skip
# while its own hint asks for a re-compile is the report describing one thing
# two ways. `Rule:` is here for the same reason from the other direction:
# `classify_block` already types a block as a rule on that label, and a
# self-labelled rule that the counts do not see is a rule nobody is ever told
# to compile - which is how the retired path-table block ended up reporting
# nothing at all once its predicate was gone. The colon is matched loosely
# because the label is routinely written `**Rule:**`.
RULE_CUE_RE = re.compile(r"\b(never|always|must|don't|do not|avoid|no longer)\b"
                         r"|\brule\s*:", re.I)


def _looks_like_a_rule(block):
    """Whether a block states a rule at all, so silence about it can be honest."""
    return bool(RULE_CUE_RE.search(block.get("content") or ""))


def _in_scope(applied, corpus):
    """True when the session produced anything an applied check could look at.

    Without this, a check that ran against an empty corpus would report `clear`,
    which reads as "the rule was followed" when the truth is that the session
    never wrote the kind of thing the rule governs.
    """
    for c in applied:
        if c["kind"] in TOOL_KINDS:
            # A tool kind is exercised only when its own antecedent fired: the
            # log being non-empty says nothing about whether the rule came up.
            if _antecedent(c, corpus.get("tools") or []):
                return True
        elif c["kind"] in SHELL_KINDS:
            if corpus.get("commands"):
                return True
        elif c["kind"] in PATH_KINDS:
            if corpus.get("paths"):
                return True
        elif c["kind"] in CANDIDATE_CHECK_KINDS:
            # No site means the rule was never tested, not that it was obeyed.
            if enumerate_candidates(c["candidate"], _source_entries(c, corpus),
                                    c.get("applies_to") or []):
                return True
        else:
            # The same corpus the check itself reads: a net diff that came out
            # empty must not report `clear`, which reads as "followed".
            if any(_path_matches(e["path"], c.get("applies_to") or [])
                   for e in _source_entries(c, corpus)):
                return True
    return False


def _state_from(findings, applied, not_checkable, stale, in_scope):
    """The block's state, with the judge tier's semantic verdicts capped.

    An advisory finding may weaken a green but can never manufacture a red: a
    semantic judgement has no fixtures behind it and no site this tool
    enumerated, so the strongest honest thing it can say alone is that the rule
    is not settled.
    """
    hard = [f for f in findings if not f.get("advisory")]
    if any(f["state"] == "violated" for f in hard):
        return "violated"
    if any(f["state"] == "acknowledged" for f in hard):
        return "acknowledged"
    if any(f["state"] == "unclear" for f in hard):
        return "unclear"
    if any(f["state"] == "unclear" for f in findings):
        return "unclear"
    if applied:
        return "clear" if in_scope else "not-exercised"
    return "not-checkable"


def check_block(block, loaded, corpus, fallback=True, doc_path="", judge=None):
    """Rule-check verdict for one block, or None when nothing is checkable.

    `loaded` is the gated checks payload for the block's document, or None when
    the document has no checks file - in which case the mechanical fallback
    runs, if `fallback` allows it, and every finding it produces is low
    confidence. Callers pass `fallback=False` for documents that are not
    guidelines (a file the agent merely read), where extracting rules from
    prose would invent them.

    States: `violated` (a citable span, strict and normalised agreeing),
    `acknowledged` (a violation the code deliberately suppresses at the site),
    `unclear` (a candidate the two views disagree about), `clear` (checks ran
    over code in their scope and found nothing), `not-exercised` (checks ran but
    the session wrote nothing they apply to), `not-checkable` (the rule was
    refused, its check failed its own self-tests, or its check no longer
    matches the rule's text).

    `demoted` and `judged` list the records that were not applied and why - a
    deterministic check whose fixtures stopped reproducing here, and a bucket
    that needs the opt-in judge tier. They are reported separately from
    `notCheckable` because they name different things to fix.

    `doc_path` is the document's own path, used only to name it in the
    re-compile hint: a rule reported unchecked has to say which file to compile.

    `judge` is the opt-in LLM tier (§9.1), and is None on the default path -
    where nothing here calls a model, makes a network request, or even imports
    the module that could. With it, the parked buckets are answered instead of
    reported unanswered: bucket B about the sites this tool enumerated, bucket C
    about the session's own evidence and display-capped.
    """
    applied, stale, not_checkable, rejected = [], [], [], []
    demoted, judged = [], []
    source = "none"
    hint_target = [doc_path or (loaded or {}).get("source", "")]

    if loaded:
        source = "checks-file"
        block_key = rule_key(block.get("title"), block.get("content"))
        for c in loaded.get("checks") or []:
            if not _entry_matches_block(c, block):
                continue
            if c.get("rule_key") and c["rule_key"] != block_key:
                stale.append({"id": c["id"], "ruleRef": c.get("rule_ref", ""),
                              "why": "the rule's text changed since this check was authored"})
                continue
            applied.append(c)
        # Demoted and parked records are listed in their own right rather than
        # folded into `notCheckable`: "its fixtures are broken" and "no judge
        # ran it" are different facts from "this rule cannot be expressed", and
        # a reader who cannot tell them apart cannot tell which one to fix.
        for entry in loaded.get("demoted") or []:
            if _entry_matches_block(entry, block):
                demoted.append(entry)
        for entry in loaded.get("judged") or []:
            if _entry_matches_block(entry, block):
                judged.append(entry)
        for entry in loaded.get("notCheckable") or []:
            if _entry_matches_block(entry, block):
                not_checkable.append({"ruleRef": entry.get("rule_ref", ""),
                                      "ruleText": entry.get("rule_text", ""),
                                      "why": entry.get("why", "")})
        for entry in loaded.get("rejected") or []:
            # A file-level rejection (unreadable JSON) names no rule, so it
            # belongs on every block of the document: the alternative is a
            # document that quietly looks unchecked.
            if entry.get("id") == "(file)" or _entry_matches_block(entry, block):
                rejected.append(entry)
                not_checkable.append({"ruleRef": entry.get("ruleRef", ""),
                                      "ruleText": entry.get("ruleText", ""),
                                      "why": entry.get("reason", "")})
    elif fallback:
        applied = fallback_checks(block)
        if applied:
            source = "fallback"
    else:
        # A document nobody wrote checks for and which is not a guideline doc
        # has nothing to say about rules; staying silent beats guessing.
        return None

    # A check whose optional backend is missing is moved out of `applied` and
    # named as unchecked. Leaving it in would report `clear` - "the rule was
    # followed" - over a rule nothing ever looked at, and dropping it silently
    # would say nothing at all about a rule the reader compiled on purpose.
    runnable = []
    for c in applied:
        why = unavailable_reason(c)
        if why:
            not_checkable.append({"ruleRef": c.get("rule_ref", ""),
                                  "ruleText": c.get("rule_text", ""),
                                  "why": why})
        else:
            runnable.append(c)
    applied = runnable

    findings = evaluate_checks(applied, corpus) if applied else []
    in_scope = _in_scope(applied, corpus)

    # A judged record is pinned to its rule's text by the same key a
    # deterministic check is. Skipping that gate here would ask a model a
    # question compiled from wording the rule no longer carries, and the answer
    # would look exactly as authoritative as a current one.
    judgeable, jnotes = [], {}
    if judge is not None and loaded:
        for r in loaded.get("judgeable") or []:
            if not _entry_matches_block(r, block):
                continue
            if r.get("rule_key") and r["rule_key"] != block_key:
                why = "the rule's text changed since this check was authored"
                stale.append({"id": r.get("id", ""), "ruleRef": r.get("rule_ref", ""),
                              "why": why})
                jnotes[r.get("id")] = why
                continue
            judgeable.append(r)
    if judgeable:
        jfindings, jran, jscope, notes = judge_records(judgeable, corpus, judge)
        jnotes.update(notes)
        findings.extend(jfindings)
        # A hybrid record that ran counts as applied: its sites were enumerated
        # here and each was examined, which is the same thing the deterministic
        # path means by `clear`.
        applied = applied + jran
        in_scope = in_scope or jscope

    if jnotes:
        # A parked entry keeps its place in the list but stops saying the tier
        # is off: reporting a rule as unanswered directly above its answer, or
        # telling the reader to switch on something already on, is the same
        # record describing itself two ways.
        judged = [_reworded(e, jnotes) for e in judged]
        demoted = [_reworded(e, jnotes) for e in demoted]

    if not applied and not not_checkable and not stale and not demoted and not judged:
        # Silence for a block that states no rule; an unextractable rule still
        # gets a verdict, so it is never mistaken for one that was followed.
        if not _looks_like_a_rule(block):
            return None
        why = ("this document's checks file says nothing about this rule"
               if loaded else
               "no checks file beside this document, and nothing in the rule "
               "could be extracted mechanically")
        not_checkable.append({
            "ruleRef": block.get("title", ""),
            "ruleText": (block.get("content") or "").strip()[:200],
            "why": why,
        })

    state = _state_from(findings, applied, not_checkable, stale, in_scope)
    # When something fired, the reported confidence is that of the findings
    # that fired - never a bystander's. A caller deciding whether to paint the
    # block red must not inherit an unrelated check's high confidence.
    scored = [f for f in findings if f["state"] == "violated"] or findings
    confidences = ([f["confidence"] for f in scored]
                   or [c.get("confidence", "low") for c in applied])
    confidence = next((c for c in ("high", "medium", "low") if c in confidences), "low")
    # One hint per block, from the same state function the session-wide counts
    # read: a report that calls a rule compiled while the block under it asks
    # the reader to compile it is describing one thing two ways. Empty for a
    # rule the compiler answered - including one it honestly refused, or parked
    # for the judge - so a compiled rule is not nagged about for ever.
    hint = ("" if compile_state(block, loaded) in ("compiled", "refused")
            else compile_hint(hint_target, stale=bool(loaded)))
    return {
        "state": state,
        "source": source,
        "confidence": confidence,
        "findings": findings,
        "notCheckable": not_checkable,
        "rejected": rejected,
        "stale": stale,
        "checksApplied": [c["id"] for c in applied],
        "demoted": demoted,
        "judged": judged,
        "hint": hint,
    }
