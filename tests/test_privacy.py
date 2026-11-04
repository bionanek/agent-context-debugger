"""The snapshot corpus is private, and git has to know it.

`snapshots/baseline/` and `snapshots/after/` are frozen raw transcripts of the
author's own sessions: a production host and ssh user, dev database passwords,
thousands of employer ticket references, a colleague's name and a personal
email. They are the calibration corpus, so they cannot be sanitised away
without destroying what they measure - which leaves exactly one control, that
they are never committed. This module is that control, expressed as a test
rather than as a line in a README nobody re-reads.
"""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# Named with the trailing slash the ignore rules carry: without it `git
# check-ignore` cannot tell a directory-only pattern applies to a path that is
# not on this machine, and the test would report a clone as unprotected.
PRIVATE = ("snapshots/baseline/", "snapshots/after/")


def _git(*args):
    try:
        proc = subprocess.run(("git",) + args, cwd=REPO, capture_output=True,
                              text=True)
    except FileNotFoundError:
        pytest.skip("git is not installed, so the ignore rules cannot be read")
    if proc.returncode == 128:
        # An unpacked tarball has no ignore rules to check and no history to
        # search, so every assertion below would report a private corpus at
        # risk when there is no repository at all.
        pytest.skip(f"git cannot read {REPO} as a repository: "
                    f"{proc.stderr.strip()}")
    return proc


def test_both_snapshot_trees_are_ignored():
    for path in PRIVATE:
        proc = _git("check-ignore", "-v", path)
        assert proc.returncode == 0, (
            f"{path} is not gitignored, so a `git add -A` would publish the "
            f"private calibration corpus: {proc.stderr.strip()}")


def test_the_ignore_rule_is_not_the_kind_that_still_stages_the_contents():
    """`git status` seeing nothing is the property, not the .gitignore line.

    An ignore rule that misses (a trailing-slash or anchoring mistake, a later
    negation) leaves the trees invisible in the ignore file and perfectly
    visible to `git add`.
    """
    proc = _git("status", "--porcelain", "--untracked-files=all", "snapshots")
    assert proc.returncode == 0, proc.stderr
    for line in proc.stdout.splitlines():
        assert not any(p in line for p in PRIVATE), line


def test_no_commit_has_ever_carried_them():
    """An ignore rule added after the fact would leave the history intact."""
    proc = _git("log", "--all", "--oneline", "--", *PRIVATE)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", (
        "the private corpus is in the history, so ignoring it now is not "
        f"enough:\n{proc.stdout}")


def test_no_committed_snapshot_file_carries_a_home_path():
    """A home path names the author and lays out their machine.

    `sessions.json` is read with `~` expanded where it is used, so nothing
    committed under snapshots/ has a reason to carry one.
    """
    proc = _git("grep", "-n", "/Users/", "--", "snapshots")
    assert proc.returncode in (0, 1), proc.stderr
    assert proc.stdout.strip() == "", (
        f"a committed file under snapshots/ carries a home path:\n{proc.stdout}")
