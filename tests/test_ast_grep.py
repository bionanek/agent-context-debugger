"""Tests for Phase 9: ast-grep as a pinned, consented, optional enhancer.

Three claims, and each one is a trust property rather than a feature:

* Structural matching answers a structural question. A regex asked "is this
  catch body empty" either accuses a documentation string or refuses to decide
  a body that holds a comment; the structural backend gets both right and
  cites the span.
* An optional signal degrades to "not checked", never to an approximation
  wearing the same badge. With the binary absent the affected rule reports
  `not-checkable` and names the command that installs it - it never falls back
  to a regex that answers a different question under the same check id.
* The binary is consented, pinned and local. Resolution never walks `PATH`,
  and the fetch verifies a pinned digest before anything is written.
"""
import json
import os
import re
import stat
import tarfile
from io import BytesIO
from pathlib import Path

import build_real_view as brv
import install_ast_grep as ig
import rule_checks as rc

from tests.test_turns import user_text

from tests.test_rule_checks import (check, corpus_for, doc, rule_file,
                                    trace_for, write_call)


# ---------- a stand-in for the binary ----------

# The shim stands in for ast-grep itself: these tests are about which backend
# decides a rule, what it cites and how the tool behaves when it is absent -
# not about tree-sitter, which is the one part of this that no test here can
# meaningfully re-implement.
SHIM = r'''#!/usr/bin/env python3
"""Emulates `ast-grep run -p '<empty catch>' --json=compact FILE`."""
import json, re, sys

args = sys.argv[1:]
pattern = args[args.index("--pattern") + 1] if "--pattern" in args else ""
target = args[-1]
raw = open(target, "rb").read()
text = raw.decode("utf-8")

out = []
if "catch" in pattern:
    # A string literal is not code, so its contents are not sites - which is
    # the whole difference from the regex the rule would otherwise use.
    masked = re.sub(r'"[^"\n]*"', lambda m: " " * len(m.group(0)), text)
    for m in re.finditer(r"\bcatch\b[^\n{]*\{", masked):
        depth, i, n = 1, m.end(), len(masked)
        while i < n and depth:
            depth += (masked[i] == "{") - (masked[i] == "}")
            i += 1
        body = re.sub(r"//[^\n]*", "", masked[m.end():i - 1])
        if body.strip():
            continue
        out.append({
            "text": text[m.start():i],
            "range": {"byteOffset": {
                "start": len(text[:m.start()].encode("utf-8")),
                "end": len(text[:i].encode("utf-8")),
            }},
            "file": target,
            "language": "TypeScript",
        })
print(json.dumps(out))
'''

BROKEN_SHIM = "#!/usr/bin/env python3\nimport sys\nsys.stderr.write('boom\\n')\nsys.exit(2)\n"


def shim(tmp_path, body=SHIM, name="ast-grep"):
    """An executable stand-in, in a directory of its own."""
    d = tmp_path / "vendor"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def use_shim(monkeypatch, path):
    monkeypatch.setenv(rc.AST_GREP_ENV, str(path))


def no_binary(monkeypatch, tmp_path):
    monkeypatch.delenv(rc.AST_GREP_ENV, raising=False)
    monkeypatch.setattr(rc, "AST_GREP_DIR", tmp_path / "empty")


# ---------- records ----------

EMPTY_CATCH = "catch ($$$ARGS) { }"


def ast_check(**over):
    base = {
        "id": "catch-not-empty",
        "rule_ref": "Error handling",
        "rule_text": "Never leave a catch body empty.",
        "domain": "source",
        "kind": "ast_forbidden",
        "ast_pattern": EMPTY_CATCH,
        "applies_to": ["**/*.ts"],
        "confidence": "high",
        "message": "This catch body swallows the error.",
        "statement": "Is any catch body empty?",
        "scope": "code",
        "evidence": "diff",
        "bucket": "deterministic",
        "examples_positive": ["try { go(); } catch (e) { }"],
        "examples_negative": ["try { go(); } catch (e) { report(e); }"],
        "self_test": {
            "should_match": ["try { go(); } catch (e) { }\n"],
            "should_not_match": ["try { go(); } catch (e) { report(e); }\n"],
        },
    }
    base.update(over)
    return base


# The regex a compiler would reach for without a structural backend, and the
# two shapes it gets wrong.
REGEX_EQUIVALENT = check(
    id="catch-not-empty-regex",
    rule_ref="Error handling",
    rule_text="Never leave a catch body empty.",
    kind="forbidden_pattern",
    pattern=r"catch\s*\([^)]*\)\s*\{\s*\}",
    applies_to=["**/*.ts"],
    ignore_strings=False,
    self_test={"should_match": ["try { go(); } catch (e) { }\n"],
               "should_not_match": ["try { go(); } catch (e) { report(e); }\n"]},
)

REAL_EMPTY = "try {\n  go();\n} catch (e) { }\n"
IN_A_STRING = 'const doc = "try { go(); } catch (e) { }";\nreport(doc);\n'
COMMENT_ONLY = "try {\n  go();\n} catch (e) {\n  // nothing to do\n}\n"


def code_corpus(text, path="/repo/src/run.ts"):
    return corpus_for([user_text("write it", 1), write_call(path, text, 2)])


# ---------- resolution ----------

def test_resolution_never_walks_the_path(monkeypatch, tmp_path):
    """A binary the user never consented to must not decide their verdicts.

    An audit tool that runs whatever `ast-grep` a $PATH entry happens to
    provide has handed its judgements to something nobody reviewed.
    """
    on_path = shim(tmp_path / "elsewhere")
    monkeypatch.setenv("PATH", str(on_path.parent) + os.pathsep + os.environ["PATH"])
    no_binary(monkeypatch, tmp_path)
    assert rc.ast_grep_binary() is None


def test_the_tools_own_directory_resolves(monkeypatch, tmp_path):
    p = shim(tmp_path)
    monkeypatch.delenv(rc.AST_GREP_ENV, raising=False)
    monkeypatch.setattr(rc, "AST_GREP_DIR", p.parent)
    assert rc.ast_grep_binary() == p


def test_the_env_override_resolves(monkeypatch, tmp_path):
    p = shim(tmp_path)
    monkeypatch.setattr(rc, "AST_GREP_DIR", tmp_path / "empty")
    use_shim(monkeypatch, p)
    assert rc.ast_grep_binary() == p


def test_a_broken_override_does_not_fall_back_to_the_vendored_binary(monkeypatch, tmp_path):
    """An override that does not resolve is a configuration error the user has
    to see; running a different binary instead hides it."""
    p = shim(tmp_path)
    monkeypatch.setattr(rc, "AST_GREP_DIR", p.parent)
    use_shim(monkeypatch, tmp_path / "nope" / "ast-grep")
    assert rc.ast_grep_binary() is None


def test_a_non_executable_file_is_not_a_binary(monkeypatch, tmp_path):
    d = tmp_path / "vendor"
    d.mkdir()
    (d / "ast-grep").write_text("not executable")
    monkeypatch.delenv(rc.AST_GREP_ENV, raising=False)
    monkeypatch.setattr(rc, "AST_GREP_DIR", d)
    assert rc.ast_grep_binary() is None


# ---------- with the binary present ----------

def test_a_v2_record_may_carry_an_ast_pattern_and_produces_a_citable_span(monkeypatch, tmp_path):
    use_shim(monkeypatch, shim(tmp_path))
    loaded = rc.load_checks(doc(checks=[ast_check()]))
    assert loaded["rejected"] == [] and loaded["demoted"] == []
    findings = rc.evaluate_checks(loaded["checks"], code_corpus(REAL_EMPTY))
    assert [f["state"] for f in findings] == ["violated"]
    f = findings[0]
    assert f["path"] == "/repo/src/run.ts"
    assert f["line"] == 3
    assert f["match"].startswith("catch (e)")
    assert f["checkId"] == "catch-not-empty"


def test_the_span_is_a_character_offset_not_a_byte_offset(monkeypatch, tmp_path):
    """ast-grep reports byte offsets; slicing the text at one quotes the wrong
    code the moment a file holds a single non-ASCII character."""
    use_shim(monkeypatch, shim(tmp_path))
    text = 'const label = "✓ ✓ ✓ ✓";\ntry { go(); } catch (e) { }\n'
    findings = rc.evaluate_checks([ast_check()], code_corpus(text))
    assert findings[0]["match"].startswith("catch (e)")
    assert findings[0]["line"] == 2


def test_a_suppression_marker_downgrades_a_structural_finding(monkeypatch, tmp_path):
    use_shim(monkeypatch, shim(tmp_path))
    text = "try { go(); } catch (e) { } // ctx-allow: catch-not-empty\n"
    findings = rc.evaluate_checks([ast_check()], code_corpus(text))
    assert [f["state"] for f in findings] == ["acknowledged"]


def test_a_backend_failure_is_unclear_never_clear(monkeypatch, tmp_path):
    """A backend that could not run must not report the rule as followed."""
    use_shim(monkeypatch, shim(tmp_path, body=BROKEN_SHIM))
    findings = rc.evaluate_checks([ast_check()], code_corpus(REAL_EMPTY))
    assert [f["state"] for f in findings] == ["unclear"]
    # Nothing to quote, so nothing is quoted: a span here would put a citation
    # under a claim no match supports.
    assert findings[0]["match"] == ""
    assert "ast-grep" in findings[0]["message"]


# ---------- what the structural backend buys ----------

def test_the_structural_check_is_right_where_the_regex_is_wrong(monkeypatch, tmp_path):
    """The acceptance case: a documentation string and a comment-only body.

    The regex accuses the string (both views agree on text that is not code)
    and cannot decide the comment-only body (the two views disagree, because
    stripping the comment is what empties it). The structural check reads the
    string as data and the comment-only body as the empty body it is.
    """
    use_shim(monkeypatch, shim(tmp_path))
    structural, regex = ast_check(), REGEX_EQUIVALENT

    in_string = code_corpus(IN_A_STRING)
    assert [f["state"] for f in rc.evaluate_checks([regex], in_string)] == ["violated"]
    assert rc.evaluate_checks([structural], in_string) == []

    comment_only = code_corpus(COMMENT_ONLY)
    assert [f["state"] for f in rc.evaluate_checks([regex], comment_only)] == ["unclear"]
    structural_findings = rc.evaluate_checks([structural], comment_only)
    assert [f["state"] for f in structural_findings] == ["violated"]
    assert structural_findings[0]["line"] == 3


# ---------- with the binary absent ----------

def test_an_absent_binary_reports_not_checkable_and_names_the_installer(monkeypatch, tmp_path):
    no_binary(monkeypatch, tmp_path)
    block = {"title": "Error handling", "content": "Never leave a catch body empty."}
    loaded = rc.load_checks(doc(checks=[ast_check()]))
    out = rc.check_block(block, loaded, code_corpus(REAL_EMPTY))
    assert out["state"] == "not-checkable"
    assert out["findings"] == []
    assert out["checksApplied"] == []
    why = " ".join(nc["why"] for nc in out["notCheckable"])
    assert "ast-grep" in why and rc.AST_GREP_INSTALL in why


def test_an_absent_binary_never_falls_back_to_a_regex(monkeypatch, tmp_path):
    """The whole point of the backend is that the regex answers a different
    question; running it under the same check id would report the false
    positive as if the structural check had confirmed it."""
    no_binary(monkeypatch, tmp_path)
    assert rc.evaluate_checks([ast_check()], code_corpus(IN_A_STRING)) == []
    assert rc.evaluate_checks([ast_check()], code_corpus(REAL_EMPTY)) == []


def test_every_other_check_is_unaffected_when_the_binary_is_absent(monkeypatch, tmp_path):
    no_binary(monkeypatch, tmp_path)
    events = [user_text("build the panel", 1),
              write_call("/repo/src/Panel.tsx", "reaction(() => s.v, run);\n", 2)]
    findings = rc.evaluate_checks(rc.load_checks(doc(checks=[check()]))["checks"],
                                  corpus_for(events))
    assert [f["state"] for f in findings] == ["violated"]


def test_a_mixed_document_still_checks_its_other_rules(monkeypatch, tmp_path):
    """An unavailable backend must not take the rest of the block with it."""
    no_binary(monkeypatch, tmp_path)
    block = {"title": "Error handling", "content": "Never leave a catch body empty."}
    other = check(id="no-reaction", rule_ref="Error handling", applies_to=["**/*.ts"])
    loaded = rc.load_checks(doc(checks=[ast_check(), other]))
    out = rc.check_block(block, loaded,
                         code_corpus("reaction(() => s.v, run);\n"))
    assert out["state"] == "violated"
    assert out["checksApplied"] == ["no-reaction"]
    assert any("ast-grep" in nc["why"] for nc in out["notCheckable"])


def test_the_verdict_carries_the_gap_into_the_page_and_the_cli(monkeypatch, tmp_path):
    """The block's own evidence has to say the rule went unchecked: silence
    there reads as a rule that was followed."""
    no_binary(monkeypatch, tmp_path)
    src = tmp_path / "GUIDELINES.md"
    src.write_text("## Error handling\n\nNever leave a catch body empty.\n")
    (src.parent / "GUIDELINES.md.checks.json").write_text(
        json.dumps(doc(checks=[ast_check()], source=str(src))))
    rc.checks_for_doc.cache_clear()
    events = [user_text("write it", 1), write_call("/repo/src/run.ts", REAL_EMPTY, 2)]
    block = brv.parse_claude_md(src.read_text())[0]
    v = brv.assess_block(block, rule_file(src), trace_for(events))
    assert v["status"] != "ignored"
    assert v["ruleCheck"]["state"] == "not-checkable"
    assert any("ast-grep" in e["text"] for e in v["evidence"])


# ---------- the loader gate ----------

def test_a_broken_ast_record_is_demoted_by_its_own_fixtures(monkeypatch, tmp_path):
    """Structural patterns are LLM-authored too, so the fixture gate stays."""
    use_shim(monkeypatch, shim(tmp_path))
    bad = ast_check(id="catch-broken",
                    self_test={"should_match": ["try { go(); } catch (e) { report(e); }\n"],
                               "should_not_match": ["try { go(); } catch (e) { }\n"]})
    loaded = rc.load_checks(doc(checks=[bad]))
    assert loaded["checks"] == []
    assert [d["id"] for d in loaded["demoted"]] == ["catch-broken"]


def test_a_demotion_says_what_the_backend_complained_about(monkeypatch, tmp_path):
    """A record whose language the backend has no grammar for must not be
    demoted with "your should_match case did not fire", which sends the author
    off to rewrite a pattern that was never the problem."""
    use_shim(monkeypatch, shim(tmp_path, body=BROKEN_SHIM))
    loaded = rc.load_checks(doc(checks=[ast_check()]))
    assert [d["id"] for d in loaded["demoted"]] == ["catch-not-empty"]
    assert "ast-grep exited 2" in loaded["demoted"][0]["why"]


def test_an_ast_record_loads_unverified_when_the_backend_is_absent(monkeypatch, tmp_path):
    """Refusing it would report the rule as inexpressible when installing one
    optional binary is what it actually needs."""
    no_binary(monkeypatch, tmp_path)
    loaded = rc.load_checks(doc(checks=[ast_check()]))
    assert [c["id"] for c in loaded["checks"]] == ["catch-not-empty"]
    assert loaded["rejected"] == [] and loaded["demoted"] == []


def test_an_ast_pattern_is_not_validated_as_a_regex(monkeypatch, tmp_path):
    """`catch ($$$A) { }` is code, not a regex; refusing it for failing to
    compile as one would reject exactly the patterns this backend exists for."""
    no_binary(monkeypatch, tmp_path)
    assert rc._validate(ast_check(ast_pattern="foo(($$$A)")) is None


def test_a_non_string_ast_pattern_is_refused(monkeypatch, tmp_path):
    """Skipping the regex compile for this field also skipped the only thing
    that insisted it was a string, and a list reaches subprocess as argv."""
    no_binary(monkeypatch, tmp_path)
    reason = rc._validate(ast_check(ast_pattern=["catch ($A) { }"]))
    assert reason and "ast_pattern" in reason


def test_an_ast_check_must_name_the_files_it_governs(monkeypatch, tmp_path):
    no_binary(monkeypatch, tmp_path)
    reason = rc._validate(ast_check(applies_to=[]))
    assert reason and "applies_to" in reason


def test_an_ast_check_cannot_declare_transcript_evidence(monkeypatch, tmp_path):
    no_binary(monkeypatch, tmp_path)
    reason = rc._validate(ast_check(evidence="transcript"))
    assert reason and "transcript" in reason


# ---------- the pinned, consented fetch ----------

def tarball(members):
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
    return buf.getvalue()


BINARY = b"#!/bin/sh\necho ast-grep 0.0.0\n"


def pin_for(data, digest=None):
    import hashlib
    return {"url": "https://example.invalid/ast-grep.tgz",
            "sha512": digest or hashlib.sha512(data).hexdigest()}


def test_a_matching_digest_installs_an_executable(tmp_path):
    data = tarball({"package/README.md": b"hi", "package/ast-grep": BINARY})
    dest = tmp_path / "vendor"
    out = ig.install(pin_for(data), dest, fetch=lambda url: data)
    assert out.read_bytes() == BINARY
    assert os.access(out, os.X_OK)
    assert out.parent == dest


def test_a_wrong_digest_aborts_and_writes_nothing(tmp_path):
    data = tarball({"package/ast-grep": BINARY})
    dest = tmp_path / "vendor"
    try:
        ig.install(pin_for(data, digest="00" * 64), dest, fetch=lambda url: data)
    except ig.InstallError as e:
        assert "checksum" in str(e).lower()
    else:
        raise AssertionError("a digest mismatch must abort the install")
    assert not (dest / "ast-grep").exists()


def test_an_archive_without_the_binary_aborts(tmp_path):
    data = tarball({"package/README.md": b"hi"})
    try:
        ig.install(pin_for(data), tmp_path / "vendor", fetch=lambda url: data)
    except ig.InstallError as e:
        assert "ast-grep" in str(e)
    else:
        raise AssertionError("an archive with no binary in it must abort")


def test_every_pin_is_well_formed():
    """The url and the key must agree: a crossed pair would verify one
    platform's digest against another platform's download and always abort."""
    assert set(ig.PINS) >= {"darwin-arm64", "darwin-x64", "linux-x64-gnu",
                            "linux-arm64-gnu", "win32-x64-msvc"}
    for key, pin in ig.PINS.items():
        assert pin["url"].startswith("https://") and key in pin["url"]
        assert len(pin["sha512"]) == 128 and int(pin["sha512"], 16) >= 0
        assert ig.AST_GREP_VERSION in pin["url"]


def test_an_unpinned_platform_says_so_rather_than_guessing(monkeypatch, capsys):
    """Downloading some other platform's build would install a binary that
    cannot run, which reports as a backend failure rather than as no backend."""
    monkeypatch.setattr(ig, "platform_key", lambda: "haiku-sparc")
    monkeypatch.setattr(ig, "_fetch", _refuse)
    assert ig.main([]) != 0
    out = capsys.readouterr().out
    assert "haiku-sparc" in out and rc.AST_GREP_ENV in out


def test_printing_the_pin_touches_no_network(monkeypatch, capsys):
    monkeypatch.setattr(ig, "_fetch", _refuse)
    assert ig.main(["--print-pin"]) == 0
    assert ig.AST_GREP_VERSION in capsys.readouterr().out


def test_the_install_never_runs_without_consent(monkeypatch, capsys):
    """Never a silent install: an unattended run stops and says what to pass."""
    monkeypatch.setattr(ig, "_fetch", _refuse)
    monkeypatch.setattr(ig, "_consented", lambda: False)
    assert ig.main([]) != 0
    assert "--yes" in capsys.readouterr().out


def _refuse(url):
    raise AssertionError(f"the default analysis path must not fetch {url}")


def test_no_analysis_module_can_reach_the_network():
    """The offline guarantee is structural: the installer is a separate module
    nothing on the analysis path imports, so no code path in default mode can
    reach the network by accident."""
    for name in ("rule_checks.py", "build_real_view.py", "ctxlog_facts.py", "lexical.py"):
        src = (Path(__file__).resolve().parents[1] / name).read_text()
        assert "urllib" not in src, f"{name} reaches for the network"
        assert not re.search(r"^\s*(import|from) install_ast_grep", src, re.M), \
            f"{name} imports the installer"
