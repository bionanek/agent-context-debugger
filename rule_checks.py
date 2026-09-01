#!/usr/bin/env python3
"""Deterministic rule checking from a checks file authored ahead of time.

The interpretation of a prose rule happens ONCE, outside this tool, by applying
`prompts/translate-rules.md` to a guideline document. Its output is a checks
JSON committed next to the document, reviewable by a human. This module only
loads that file, gates it, and applies it to what a recorded session actually
wrote and ran. Nothing here calls a model or the network.

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
}

SOURCE_KINDS = ("forbidden_pattern", "required_pattern", "forbidden_co_occurrence",
                "required_co_occurrence", "required_order")
SHELL_KINDS = ("forbidden_command", "required_command")
PATH_KINDS = ("forbidden_path",)

CONFIDENCES = ("high", "medium", "low")

SHELL_PATH = "(shell)"
PATH_PATH = "(path)"


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


def strip_comments_and_strings(text, path="", strip_strings=False):
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
    """
    d = _dialect(path)
    if not text or d is None:
        return text
    out = list(text)
    n = len(text)

    def blank(a, b):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

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

def build_corpus(calls):
    """What the session actually did, in the three shapes a check can match.

    `code` groups every hunk written to a path into one entry in write order.
    An Edit carries only its changed hunk, never the surrounding file, so this
    is the whole of the file's text that is knowable from the transcript.
    """
    code, order, commands, paths = {}, [], [], []
    for c in calls:
        name, inp = c.get("name"), (c.get("input") or {})
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


def _finding(check, path, text, span, state):
    start, end = span
    matched = text[start:end].strip()
    return {
        "checkId": check["id"],
        "state": state,
        "confidence": check.get("confidence", "low"),
        "path": path,
        "line": _line_of(text, start),
        "match": matched,
        "message": check.get("message", ""),
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


def evaluate_checks(checks, corpus, limit=20):
    """Apply loaded checks to a session corpus and return findings.

    Stripping is done once per corpus entry rather than once per check: it is a
    character-by-character scan, and every check on a document would otherwise
    repeat it over the same files.
    """
    findings = []
    normalised = {}
    for check in checks:
        if check["kind"] in SHELL_KINDS:
            findings.extend(_evaluate_shell(check, corpus))
        elif check["kind"] in PATH_KINDS:
            findings.extend(_evaluate_path(check, corpus))
        else:
            drop_strings = bool(check.get("ignore_strings"))
            for idx, entry in enumerate(corpus.get("code") or []):
                # Keyed on the variant too: checks differ on whether string
                # contents are stripped, so one cached view cannot serve both.
                key = (idx, drop_strings)
                if key not in normalised:
                    normalised[key] = strip_comments_and_strings(
                        entry["text"], entry["path"], strip_strings=drop_strings)
                f = _evaluate_source(check, entry, normalised[key])
                if f:
                    findings.append(f)
        if len(findings) >= limit:
            return findings[:limit]
    return findings


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


def _selftest_corpus(check, snippet):
    if check["kind"] in SHELL_KINDS:
        return {"code": [], "commands": [snippet], "paths": []}
    if check["kind"] in PATH_KINDS:
        return {"code": [], "commands": [], "paths": [snippet]}
    return {"code": [{"path": _selftest_path(check), "text": snippet}],
            "commands": [], "paths": []}


def _violates(check, snippet):
    return any(f["state"] == "violated"
               for f in evaluate_checks([check], _selftest_corpus(check, snippet)))


def _validate(check):
    """Structural reason this check cannot be used, or None."""
    if not isinstance(check, dict) or not check.get("id"):
        return "check is missing an id"
    kind = check.get("kind")
    if kind not in VOCABULARY:
        return f"unknown kind `{kind}` - the predicate vocabulary is closed"
    if kind in SOURCE_KINDS and not check.get("applies_to"):
        # Without globs every written file is in scope, including the .py and
        # .md the rule never meant, which is how an under-specified check
        # accuses the agent in a language the rule does not govern.
        return f"kind `{kind}` requires a non-empty `applies_to`"
    for field in VOCABULARY[kind]:
        if not check.get(field):
            return f"kind `{kind}` requires `{field}`"
        try:
            re.compile(check[field])
        except re.error as e:
            return f"`{field}` is not a valid Python regex ({e})"
    if check.get("confidence") not in CONFIDENCES:
        return "confidence must be high, medium or low"
    tests = check.get("self_test") or {}
    if not tests.get("should_match") or not tests.get("should_not_match"):
        return "self-test must carry both should_match and should_not_match cases"
    return None


def _self_test_failure(check):
    """The first self-test this tool's own matcher disagrees with, or None."""
    tests = check["self_test"]
    for snippet in tests["should_match"]:
        if not _violates(check, snippet):
            return f"self-test failed: should_match case did not fire ({snippet[:80]!r})"
    for snippet in tests["should_not_match"]:
        if _violates(check, snippet):
            return f"self-test failed: should_not_match case fired ({snippet[:80]!r})"
    return None


def _rejection(check_id, reason, rule_ref="", rule_text=""):
    """A refused check, carrying `rule_ref` so it binds to its block like any
    other entry, and `ruleRef` for the frontend's camelCase records."""
    return {"id": check_id, "reason": reason, "rule_ref": rule_ref,
            "ruleRef": rule_ref, "ruleText": rule_text}


def load_checks(data):
    """Validate and gate a checks payload. Returns accepted, rejected, not-checkable.

    A check only survives if this tool's matcher reproduces the check's own
    self-tests, so a check whose author misread the vocabulary is refused
    rather than pointed at a developer's code.
    """
    checks, rejected = [], []
    for raw in (data or {}).get("checks") or []:
        entry = raw if isinstance(raw, dict) else {}
        reason = _validate(raw)
        if reason is None:
            reason = _self_test_failure(raw)
        if reason:
            rejected.append(_rejection(entry.get("id") or "(unnamed)", reason,
                                       entry.get("rule_ref", ""),
                                       entry.get("rule_text", "")))
        else:
            checks.append(raw)
    return {
        "source": (data or {}).get("source", ""),
        "checks": checks,
        "rejected": rejected,
        "notCheckable": list((data or {}).get("not_checkable") or []),
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
                "rejected": [_rejection("(file)", f"checks file unreadable: {e}")]}
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


RULE_CUE_RE = re.compile(r"\b(never|always|must|don't|do not|avoid)\b", re.I)


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
        if c["kind"] in SHELL_KINDS:
            if corpus.get("commands"):
                return True
        elif c["kind"] in PATH_KINDS:
            if corpus.get("paths"):
                return True
        else:
            if any(_path_matches(e["path"], c.get("applies_to") or [])
                   for e in corpus.get("code") or []):
                return True
    return False


def _state_from(findings, applied, not_checkable, stale, in_scope):
    if any(f["state"] == "violated" for f in findings):
        return "violated"
    if any(f["state"] == "acknowledged" for f in findings):
        return "acknowledged"
    if any(f["state"] == "unclear" for f in findings):
        return "unclear"
    if applied:
        return "clear" if in_scope else "not-exercised"
    return "not-checkable"


def check_block(block, loaded, corpus, fallback=True):
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
    """
    applied, stale, not_checkable, rejected = [], [], [], []
    source = "none"

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

    findings = evaluate_checks(applied, corpus) if applied else []
    if not applied and not not_checkable and not stale:
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

    state = _state_from(findings, applied, not_checkable, stale, _in_scope(applied, corpus))
    # When something fired, the reported confidence is that of the findings
    # that fired - never a bystander's. A caller deciding whether to paint the
    # block red must not inherit an unrelated check's high confidence.
    scored = [f for f in findings if f["state"] == "violated"] or findings
    confidences = ([f["confidence"] for f in scored]
                   or [c.get("confidence", "low") for c in applied])
    confidence = next((c for c in ("high", "medium", "low") if c in confidences), "low")
    return {
        "state": state,
        "source": source,
        "confidence": confidence,
        "findings": findings,
        "notCheckable": not_checkable,
        "rejected": rejected,
        "stale": stale,
        "checksApplied": [c["id"] for c in applied],
    }
