#!/usr/bin/env python3
"""Consented, checksum-pinned installer for the optional ast-grep binary.

This is the one place in the repo that touches the network, and it is not on
the analysis path: nothing in `build_real_view.py`, `rule_checks.py` or
`ctxlog_facts.py` imports it, so a default audit cannot reach the network even
by accident. Run it by hand, once, if you want structural rule checks:

    python3 install_ast_grep.py            # asks before downloading anything
    python3 install_ast_grep.py --yes      # same, pre-consented
    python3 install_ast_grep.py --print-pin

Three properties, in the order they matter for an audit tool people are asked
to trust with their transcripts:

* **Never a silent install.** The download is a separate command that names the
  URL, the digest and the destination and waits for a typed yes. A tool whose
  job is to tell you what your agent did must not modify your machine as a side
  effect of telling you.
* **Never the user's PATH.** The binary lands in the tool's own directory and is
  run from there. Installing to `/usr/local/bin` would leave a binary behind
  that outlives the tool and that other software would pick up.
* **Pinned.** Each platform's archive is pinned to a sha512 taken from the npm
  registry's own `dist.integrity`, and a mismatch aborts before anything is
  written to disk. Bump `AST_GREP_VERSION` and the digests together, never one
  alone.
"""
import argparse
import hashlib
import io
import os
import platform
import stat
import sys
import tarfile
import urllib.request
from pathlib import Path

import rule_checks

AST_GREP_VERSION = "0.45.3"

# The npm platform packages of `@ast-grep/cli`, each a gzipped tarball holding
# the single static binary. sha512 is the registry's own `dist.integrity` for
# that exact tarball, hex-encoded. npm is the pinning source because it
# publishes a per-artifact digest that can be re-read and compared later; the
# GitHub release assets carry no published checksum at all.
_BASE = f"https://registry.npmjs.org/@ast-grep/cli-%s/-/cli-%s-{AST_GREP_VERSION}.tgz"
PINS = {
    "darwin-arm64": {
        "url": _BASE % ("darwin-arm64", "darwin-arm64"),
        "sha512": "e91660e2044c25c489b4426e696e73df7a9fc170fb9110c66744f4753c55c6c2"
                  "d2c390647808d1f11132b315303d6667fa83a4ccfc99df2effa8d9d223f76220",
    },
    "darwin-x64": {
        "url": _BASE % ("darwin-x64", "darwin-x64"),
        "sha512": "e33e999274cc4a54e2ad0b89e318a15e82df1bb63000ec450aa90ab860310223"
                  "fe2bbd338af89bf11d7dbd4a05243cb8b3eae3c8634376b9b8e7f0a50b9b484d",
    },
    "linux-x64-gnu": {
        "url": _BASE % ("linux-x64-gnu", "linux-x64-gnu"),
        "sha512": "1dbc48cbab596bcce7e09da11bc295228f67e3e20d020541f25d83c87a98c462"
                  "b19e877cbb607885f4c6c5b326f818c1bd8c4a5b8a062d9b58a889cccb189dc9",
    },
    "linux-arm64-gnu": {
        "url": _BASE % ("linux-arm64-gnu", "linux-arm64-gnu"),
        "sha512": "4ff37e165fe932a363bb23d5f4f6d3491d9b4e566b2ca882c87cc96b1e9035a3"
                  "8e56f8978c4b1c44eac073a7349457dcf99d3b816ed1b77a1929974b104c6eb5",
    },
    "win32-x64-msvc": {
        "url": _BASE % ("win32-x64-msvc", "win32-x64-msvc"),
        "sha512": "519ae955b8cb42a4084715aa78c730c8b4888650d9ca161bf128a7b2c337f0ea"
                  "3a9840768cc7c7084a2281acbd50e6537d4476ebc9fbd81055e3c9d6da1f90c0",
    },
}

_ARCH = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}


class InstallError(Exception):
    """Anything that stops the install, raised before anything is written."""


def platform_key():
    """This machine's key into `PINS`, whether or not one is pinned for it."""
    arch = _ARCH.get(platform.machine().lower(), platform.machine().lower())
    system = platform.system().lower()
    if system == "darwin":
        return f"darwin-{arch}"
    if system == "linux":
        return f"linux-{arch}-gnu"
    if system == "windows":
        return f"win32-{arch}-msvc"
    return f"{system}-{arch}"


def _fetch(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def _binary_member(tar):
    """The tar entry that is the binary, by basename.

    Matched by name rather than by position: the archive layout is npm's, not
    ours, and a wrong guess would install a README as an executable.
    """
    for info in tar.getmembers():
        if info.isfile() and os.path.basename(info.name) in rule_checks.AST_GREP_NAMES:
            return info
    return None


def install(pin, dest_dir, fetch=None):
    """Download, verify against the pinned digest, extract. Returns the path.

    Nothing reaches the filesystem before the digest matches: a partially
    written binary from a corrupted or substituted download is exactly what
    the pin exists to prevent, and a half-installed one would then be run.

    `fetch` is resolved at call time rather than bound as a default, so a test
    that replaces the module's fetcher really does stop the network - bound as
    a default it would keep the original and download for real.
    """
    data = (fetch or _fetch)(pin["url"])
    digest = hashlib.sha512(data).hexdigest()
    if digest != pin["sha512"]:
        raise InstallError(
            "checksum mismatch - refusing to install.\n"
            f"  expected sha512 {pin['sha512']}\n"
            f"  downloaded      {digest}\n"
            f"  from            {pin['url']}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        info = _binary_member(tar)
        if info is None:
            raise InstallError(
                f"no ast-grep binary in {pin['url']} - the archive holds "
                + ", ".join(m.name for m in tar.getmembers()[:10]))
        # Extracted a member at a time rather than with `extractall`, which
        # would let a crafted archive write outside the destination.
        payload = tar.extractfile(info).read()
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / os.path.basename(info.name)
    # Written under a temp name and moved into place: a write interrupted by a
    # full disk would otherwise leave a truncated binary that still resolves as
    # installed, and every structural rule would then report a backend failure
    # rather than a missing backend.
    staged = out.with_name(out.name + ".part")
    staged.write_bytes(payload)
    staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(staged, out)
    return out


def _describe(pin, dest):
    return "\n".join([
        f"ast-grep {AST_GREP_VERSION} ({platform_key()})",
        f"  download   {pin['url']}",
        f"  sha512     {pin['sha512']}",
        f"  install to {dest}",
        "",
        "Nothing outside that directory is touched, and nothing is added to your PATH.",
    ])


def _consented():
    """Ask, and take only a typed yes. Never assume consent from a non-tty."""
    if not sys.stdin.isatty():
        return False
    return input("Download and install it? [y/N] ").strip().lower() in ("y", "yes")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--yes", action="store_true",
                    help="consent up front, for a scripted setup")
    ap.add_argument("--print-pin", action="store_true",
                    help="print what would be downloaded and exit; no network access")
    ap.add_argument("--dir", default=str(rule_checks.AST_GREP_DIR),
                    help="where to install (default: the tool's own directory)")
    args = ap.parse_args(argv)

    key = platform_key()
    pin = PINS.get(key)
    if pin is None:
        print(f"No pinned ast-grep build for {key}. Structural rule checks stay "
              f"unavailable, and every other check is unaffected.\n"
              f"You can point the tool at your own binary with "
              f"{rule_checks.AST_GREP_ENV}=/path/to/ast-grep.")
        return 1
    print(_describe(pin, args.dir))
    if args.print_pin:
        return 0
    if not (args.yes or _consented()):
        print("Nothing was downloaded. Re-run with --yes to consent up front.")
        return 1
    try:
        out = install(pin, args.dir)
    except (InstallError, OSError, tarfile.TarError) as e:
        print(f"install failed: {e}")
        return 1
    print(f"Installed {out}")
    if Path(args.dir).resolve() != Path(rule_checks.AST_GREP_DIR).resolve():
        # Resolution never searches PATH, so a binary installed anywhere but
        # the tool's own directory is invisible until it is pointed at - and a
        # silently unused install looks exactly like no install at all.
        print(f"That is not the tool's own directory, so point it there with "
              f"{rule_checks.AST_GREP_ENV}={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
