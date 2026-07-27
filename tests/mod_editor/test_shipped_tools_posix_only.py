"""Guards every SHIPPED command-line tool against POSIX-only ``os`` members.

This file exists because of a real, reported Windows failure. A user on
Windows tried the ordinary "export and replace field endzone" flow and got

    AttributeError: module 'os' has no attribute 'O_CLOEXEC'

from ``tools/apf_field_art_patch.py``. ``os.O_CLOEXEC`` does not exist in
CPython on Windows. The flag had been written as a bare attribute while the
Windows-only flag beside it on the same line was correctly written as
``getattr(os, "O_BINARY", 0)`` -- the POSIX-only half of the pair was simply
never converted when these writers were ported.

**Why the existing suite could not catch it.** Every test that exercises one
of these writers is gated on extracted retail game data
(``@unittest.skipUnless(DISC_AVAILABLE, ...)``), which no CI runner has. The
Windows job therefore never executed a single ``os.open`` inside any writer,
and still reported full parity with Linux and macOS. The defect lived
exclusively in the code path that runs only when you own the game -- which is
every real user and never CI.

So both tests here are deliberately **retail-data-free**: they run identically
on a bare CI runner and on a machine with the discs, on all three platforms.

1. :class:`OpenFlagLiteralTests` parses every file named in either release
   allowlist and fails on a bare POSIX-only ``os.O_*`` flag. ``os.open`` flags
   are OR-ed into one expression evaluated at call time, so ``getattr(os, ...,
   0)`` is the only correct form -- there is no legitimate branch-guarded
   idiom for them, which is what makes this static check exact rather than
   heuristic. It covers writers whose ``os.open`` needs real archive bytes to
   reach, and it covers tools that do not exist yet.

2. :class:`SimulatedWindowsWriterTests` deletes the POSIX-only names from
   :mod:`os` on this host and then really drives the output-reservation path of
   every shipped writer that has one, plus any shipped ``copy_fd_exact``. That
   is the reporter's exact crash, reproduced and asserted without a Windows
   box. On Windows the deletions are no-ops and the same real path runs.

Both discover their targets from the allowlists, so a writer added to a
release is covered without editing this file.
"""

from __future__ import annotations

import ast
import contextlib
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

_ALLOWLISTS = (
    _REPO_ROOT / "packaging" / "apf2k8-release-allowlist.txt",
    _REPO_ROOT / "packaging" / "release-allowlist.txt",
)

# ``os.open`` flags that CPython does not define on Windows. Passing any of
# these as a bare attribute is an unconditional AttributeError there.
POSIX_ONLY_OPEN_FLAGS = frozenset(
    {
        "O_CLOEXEC",
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "O_NOATIME",
        "O_PATH",
        "O_TMPFILE",
        "O_DSYNC",
        "O_RSYNC",
        "O_SYNC",
        "O_NDELAY",
        "O_ASYNC",
        "O_LARGEFILE",
        "O_NOCTTY",
        "O_DIRECT",
        "O_ACCMODE",
        "O_FSYNC",
        "O_SHLOCK",
        "O_EXLOCK",
    }
)

# Removed from ``os`` for the simulation. The three flags are what the writers
# OR into their ``os.open`` calls; ``copy_file_range`` is the Linux-only
# accelerated copy whose absence raises AttributeError rather than the OSError
# its fallback used to catch.
SIMULATED_ABSENT = ("O_CLOEXEC", "O_NOFOLLOW", "O_DIRECTORY", "copy_file_range")


def _shipped_python_tools() -> list[Path]:
    """Every ``tools/*.py`` named by a release allowlist, deduplicated."""
    shipped: dict[Path, None] = {}
    for allowlist in _ALLOWLISTS:
        if not allowlist.exists():
            continue
        for raw in allowlist.read_text(encoding="utf-8").splitlines():
            entry = raw.strip()
            if not entry or entry.startswith("#"):
                continue
            if not entry.startswith("tools/") or not entry.endswith(".py"):
                continue
            if entry.startswith("tools/vendor/"):
                continue
            path = _REPO_ROOT / entry
            if path.exists():
                shipped[path] = None
    return sorted(shipped)


def _bare_posix_open_flags(source: str) -> list[tuple[int, str]]:
    """Bare ``os.<POSIX-only flag>`` reads, ignoring the ``getattr`` form."""
    tree = ast.parse(source)
    guarded: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        # getattr(os, "O_CLOEXEC", 0): the module is a plain Name argument, so
        # remember its position and do not count it as an attribute read.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
        ):
            guarded.add((node.args[0].lineno, node.args[0].col_offset))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if not isinstance(node.value, ast.Name) or node.value.id != "os":
            continue
        if node.attr not in POSIX_ONLY_OPEN_FLAGS:
            continue
        if (node.value.lineno, node.value.col_offset) in guarded:
            continue
        found.append((node.lineno, f"os.{node.attr}"))
    return found


def _defines(path: Path, name: str) -> bool:
    """True if *path* defines a module-level function called *name*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


@contextlib.contextmanager
def simulated_non_posix():
    """Hide the POSIX-only ``os`` members Windows genuinely does not have.

    The writers resolve their flags at call time, so removing the names here
    makes this host take the real Windows branch. Anything already absent (on
    Windows itself, or on macOS for ``copy_file_range``) is left alone, so the
    same test body is meaningful on all three platforms.
    """
    saved = {name: getattr(os, name) for name in SIMULATED_ABSENT if hasattr(os, name)}
    for name in saved:
        delattr(os, name)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(os, name, value)


class ShippedToolDiscoveryTests(unittest.TestCase):
    """The allowlists must actually resolve, or both tests below vacuously pass."""

    def test_allowlists_name_real_python_tools(self) -> None:
        shipped = _shipped_python_tools()
        self.assertGreater(
            len(shipped), 20, "release allowlists resolved almost no tools/*.py"
        )
        for path in shipped:
            self.assertTrue(path.is_file(), f"allowlisted but missing: {path}")

    def test_the_reported_writers_are_in_scope(self) -> None:
        """The four files that carried the reported defect must be covered."""
        names = {path.name for path in _shipped_python_tools()}
        for expected in (
            "apf_field_art_patch.py",
            "apf_logo_patch.py",
            "apf_logocache_patch.py",
            "apf_texture_patch.py",
        ):
            self.assertIn(expected, names)


class OpenFlagLiteralTests(unittest.TestCase):
    """No shipped tool may name a POSIX-only open flag as a bare attribute."""

    def test_no_bare_posix_only_open_flags(self) -> None:
        offences: list[str] = []
        for path in _shipped_python_tools():
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:  # pragma: no cover - defensive
                continue
            for lineno, flag in _bare_posix_open_flags(source):
                offences.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}: {flag}")
        self.assertEqual(
            offences,
            [],
            "Shipped tools name POSIX-only os.open flags as bare attributes, which "
            "is an AttributeError on Windows. Use getattr(os, \"FLAG\", 0):\n  "
            + "\n  ".join(offences),
        )

    def test_the_check_would_have_caught_the_reported_crash(self) -> None:
        """A negative control: the exact pre-fix line must be rejected."""
        regressed = (
            "import os\n"
            "os.open(p, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC"
            ' | getattr(os, "O_BINARY", 0), 0o644)\n'
        )
        self.assertEqual(_bare_posix_open_flags(regressed), [(2, "os.O_CLOEXEC")])

    def test_the_check_accepts_the_guarded_form(self) -> None:
        """And the fixed line must pass, so the check is not simply always red."""
        repaired = (
            "import os\n"
            "os.open(p, os.O_RDWR | os.O_CREAT | os.O_EXCL"
            ' | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0), 0o644)\n'
        )
        self.assertEqual(_bare_posix_open_flags(repaired), [])


class SimulatedWindowsWriterTests(unittest.TestCase):
    """Really run the shipped writers' output paths with the flags absent."""

    def test_every_shipped_reservation_survives(self) -> None:
        """``_reserve_new`` is where the reporter's build died, before any write."""
        targets = [
            path for path in _shipped_python_tools() if _defines(path, "_reserve_new")
        ]
        self.assertGreaterEqual(
            len(targets), 3, "expected several shipped writers to reserve outputs"
        )
        exercised: list[str] = []
        with simulated_non_posix():
            for path in targets:
                module = importlib.import_module(path.stem)
                reserve = getattr(module, "_reserve_new")
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "manifest.json"
                    try:
                        reservation = reserve(target)
                    except AttributeError as exc:  # the reported failure mode
                        self.fail(
                            f"{path.name}._reserve_new is not portable: {exc}"
                        )
                    try:
                        self.assertTrue(target.exists())
                        commit = getattr(module, "_commit_reserved", None)
                        if commit is not None:
                            commit(target, reservation, b"{}\n")
                            self.assertEqual(target.read_bytes(), b"{}\n")
                    finally:
                        close = getattr(module, "_close_reserved", None)
                        if close is not None:
                            close(reservation)
                        else:  # pragma: no cover - every writer has one today
                            os.close(reservation.descriptor)
                exercised.append(path.name)
        self.assertEqual(sorted(exercised), sorted(p.name for p in targets))

    def test_reservation_still_refuses_an_existing_path(self) -> None:
        """The fail-closed guarantee must survive the portable flag form."""
        targets = [
            path for path in _shipped_python_tools() if _defines(path, "_reserve_new")
        ]
        with simulated_non_posix():
            for path in targets:
                module = importlib.import_module(path.stem)
                with tempfile.TemporaryDirectory() as directory:
                    occupied = Path(directory) / "manifest.json"
                    occupied.write_bytes(b"do not clobber me")
                    with self.assertRaises(Exception) as caught:
                        module._reserve_new(occupied)
                    self.assertNotIsInstance(
                        caught.exception,
                        AttributeError,
                        f"{path.name} refused for the wrong reason",
                    )
                    self.assertIn("refusing", str(caught.exception).lower())
                    self.assertEqual(occupied.read_bytes(), b"do not clobber me")

    def test_accelerated_copy_falls_back_instead_of_raising(self) -> None:
        """``copy_file_range`` is Linux-only; its absence must pick the fallback."""
        targets = [
            path for path in _shipped_python_tools() if _defines(path, "copy_fd_exact")
        ]
        if not targets:
            self.skipTest("no shipped tool defines copy_fd_exact")
        # Deliberately every byte value, so the payload contains 0x1A. On
        # Windows a descriptor opened without O_BINARY is a *text* stream: the
        # CRT translates newlines and treats 0x1A as end-of-file, so the copy
        # would stop early and the tool would fail its own short-read check.
        # These opens therefore mirror the product's own (both of its os.open
        # calls set getattr(os, "O_BINARY", 0)) -- do not drop the flag here.
        payload = bytes(range(256)) * 32
        binary = getattr(os, "O_BINARY", 0)
        with simulated_non_posix():
            for path in targets:
                module = importlib.import_module(path.stem)
                with tempfile.TemporaryDirectory() as directory:
                    source = Path(directory) / "source.bin"
                    source.write_bytes(payload)
                    output = Path(directory) / "output.bin"
                    source_fd = os.open(source, os.O_RDONLY | binary)
                    output_fd = os.open(output, os.O_RDWR | os.O_CREAT | binary, 0o644)
                    try:
                        method = module.copy_fd_exact(
                            source_fd, output_fd, len(payload)
                        )
                    except AttributeError as exc:
                        self.fail(f"{path.name}.copy_fd_exact is not portable: {exc}")
                    finally:
                        os.close(source_fd)
                        os.close(output_fd)
                    self.assertEqual(method, "pread_pwrite")
                    self.assertEqual(output.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
