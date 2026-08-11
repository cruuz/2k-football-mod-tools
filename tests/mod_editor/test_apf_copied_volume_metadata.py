"""Portability tests for the copied-volume metadata step of the APF writers.

A Windows user could not build a copied ``0A`` volume at all::

    File "...\\tools\\apf_logo_patch.py", line 1828, in _copy_fd_metadata
        os.utime(output_descriptor, ns=(...))
    TypeError: utime: path should be string, bytes or os.PathLike, not int

``os.utime`` accepts a descriptor only where CPython recorded it in
``os.supports_fd`` (built from ``HAVE_FUTIMENS`` / ``HAVE_FUTIMES``), and Windows
defines neither.  The usual ``hasattr(os, ...)`` probe that guards the rest of
this file's metadata step cannot catch that, because ``os.utime`` *does* exist
there -- it only rejects the int.  The fix is
:func:`platform_compat.utime_ns`, capability-tested against ``os.supports_fd``.

Windows cannot be run here, so it is *simulated in-process* in the shape the
sibling ``test_platform_compat_durability.py`` established: ``os.supports_fd``
is reduced to what Windows really publishes, ``os.utime`` is replaced with one
that refuses an int exactly as the CRT does, and the ``os`` attributes Windows
does not have at all (``fchmod``, the ``xattr`` family, ``pread``/``pwrite``,
``O_CLOEXEC``/``O_NOFOLLOW``/``O_DIRECTORY``) are deleted.  Each test then
asserts twice: that the *old* idiom really fails under that simulation, and that
the shipped path now completes -- which is what proves the fix takes the Windows
branch rather than passing by accident.

What is asserted about the product, not just the helper:

* the copy still produces the right bytes and the right mode on a host with no
  descriptor form of either ``utime`` or ``chmod``;
* a raising ``utime`` can never escape the copy, because the timestamps are
  cosmetic and must never fail a transaction whose bytes and mode are correct;
* the narrow path-based fallback refuses a name that no longer resolves to the
  descriptor's inode, so the one place a name is consulted cannot be redirected
  into stamping some other file; and
* every one of the five call sites -- including the two cross-module reaches
  that have no local definition to patch -- passes the output path the fallback
  needs.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import inspect
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Iterator
import unittest

from mod_editor.core import platform_compat

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_field_art_patch  # noqa: E402
import apf_jersey_selector_patch  # noqa: E402
import apf_logo_patch  # noqa: E402
import apf_logocache_patch  # noqa: E402
import apf_outer  # noqa: E402
import apf_texture_patch  # noqa: E402


# The three byte-identical definitions of the metadata step.  Each is exercised
# directly rather than trusting that they stayed identical.
COPY_MODULES = (apf_logo_patch, apf_texture_patch, apf_field_art_patch)

# Every module that calls it, including the two that import the symbol from a
# sibling and so have no local body to fix.
CALL_SITE_MODULES = COPY_MODULES + (apf_logocache_patch, apf_jersey_selector_patch)

# Absent from the ``os`` module on Windows, so deleting them makes every
# ``getattr(os, ...)`` probe in the shipped code take the branch it takes there.
# ``O_BINARY`` is the mirror image: absent on POSIX, present on Windows.
WINDOWS_ABSENT_OS_NAMES = (
    "O_CLOEXEC",
    "O_DIRECTORY",
    "O_NOFOLLOW",
    "fchmod",
    "getxattr",
    "listxattr",
    "pread",
    "pwrite",
    "setxattr",
)

# CPython adds ``os.stat`` to ``supports_fd`` unconditionally ("fstat always
# works") and everything else behind a ``HAVE_*`` macro, so this set is what a
# Windows build really publishes.
WINDOWS_SUPPORTS_FD = frozenset({os.stat})

# The exact message CPython's argument clinic raises for the reported crash.
FD_REJECTED_MESSAGE = "utime: path should be string, bytes or os.PathLike, not int"

SOURCE_MODE = 0o640
OUTPUT_CREATE_MODE = 0o600
# Distinct, comfortably in the past, and far enough apart that a stamp that
# silently did nothing cannot pass by coincidence.
SOURCE_ATIME_NS = 1_111_111_111_000_000_000
SOURCE_MTIME_NS = 1_222_222_222_000_000_000

VOLUME_SIZE = 4096
ENTRY_OFFSET = 1024
REPLACEMENT = b"replacement entry bytes; not the retail ones\x00\xff" * 4


def _volume_body() -> bytes:
    """Deterministic filler that is not uniform, so a misplaced write shows."""

    return bytes((index * 7 + 11) & 0xFF for index in range(VOLUME_SIZE))


def _entry(pack_offset: int, size: int) -> apf_outer.Entry:
    """The only fields the copied-volume writers read off an entry."""

    segment = apf_outer.Segment(
        pack_ordinal=0, pack_name="0A", pack_offset=pack_offset, size=size
    )
    return apf_outer.Entry(
        table_index=0,
        name_id=0,
        offset_blocks=0,
        size_blocks=0,
        virtual_offset=0,
        size=size,
        head_hex="",
        segments=(segment,),
    )


def _host_records_posix_modes() -> bool:
    """Whether this filesystem stores the permission bits the copy propagates.

    Asked by writing a file rather than by naming an OS, because that is the
    only thing the assertions below actually depend on.  Windows records just
    the read-only attribute -- ``os.chmod`` honours ``S_IWRITE`` and drops the
    rest -- so ``0o640`` reads back as ``0o666`` and no copy can be made to
    compare equal to its source.  The bytes, which are the product, are still
    checked everywhere.
    """

    with tempfile.TemporaryDirectory() as directory:
        probe = Path(directory) / "probe"
        probe.write_bytes(b"")
        os.chmod(probe, SOURCE_MODE)
        return stat.S_IMODE(os.stat(probe).st_mode) == SOURCE_MODE


HOST_RECORDS_POSIX_MODES = _host_records_posix_modes()


def _write_source_volume(directory: Path) -> Path:
    source = directory / "source" / "0A"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(_volume_body())
    os.chmod(source, SOURCE_MODE)
    os.utime(source, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS))
    return source


@contextlib.contextmanager
def simulated_windows() -> Iterator[None]:
    """Make this process refuse descriptors the way Windows does.

    Only the capability surface this metadata step touches is simulated; the
    point is that the shipped code cannot tell the difference, so whatever it
    does under this block is what it will do on the user's machine.
    """

    real_utime = os.utime
    saved_attributes = {
        name: getattr(os, name)
        for name in WINDOWS_ABSENT_OS_NAMES
        if hasattr(os, name)
    }
    saved_supports_fd = os.supports_fd
    saved_supports_dir_fd = os.supports_dir_fd
    saved_binary = getattr(os, "O_BINARY", None)
    saved_windows_flag = platform_compat.IS_WINDOWS

    def windows_utime(path, times=None, **kwargs):  # noqa: ANN001, ANN202
        if isinstance(path, int):
            raise TypeError(FD_REJECTED_MESSAGE)
        if kwargs.pop("dir_fd", None) is not None:
            raise NotImplementedError("utime: dir_fd unavailable on this platform")
        return real_utime(path, times, **kwargs)

    os.utime = windows_utime  # type: ignore[assignment]
    os.supports_fd = WINDOWS_SUPPORTS_FD  # type: ignore[assignment]
    os.supports_dir_fd = frozenset()  # type: ignore[assignment]
    for name in saved_attributes:
        delattr(os, name)
    if saved_binary is None:
        # Give the simulation the attribute Windows really publishes, so a
        # writer that reaches for it takes the same branch here.  Where the
        # host already has one, leave it alone: forcing it to 0 on real Windows
        # downgrades every O_BINARY open in the shipped writers to a text-mode
        # open, and os.read then stops at the first 0x1A in a binary volume.
        os.O_BINARY = 0  # type: ignore[attr-defined]
    platform_compat.IS_WINDOWS = True
    try:
        yield
    finally:
        platform_compat.IS_WINDOWS = saved_windows_flag
        if saved_binary is None:
            del os.O_BINARY  # type: ignore[attr-defined]
        else:
            os.O_BINARY = saved_binary  # type: ignore[attr-defined]
        for name, value in saved_attributes.items():
            setattr(os, name, value)
        os.supports_dir_fd = saved_supports_dir_fd  # type: ignore[assignment]
        os.supports_fd = saved_supports_fd  # type: ignore[assignment]
        os.utime = real_utime  # type: ignore[assignment]


@contextlib.contextmanager
def utime_always_raising(error: BaseException) -> Iterator[list[object]]:
    """A host whose ``utime`` fails however it is addressed.

    The replacement is advertised in ``os.supports_fd``, so the descriptor form
    is genuinely attempted and genuinely raises before the path form it falls
    back to raises as well -- the worst case the copy has to absorb.  Yields the
    list of arguments each attempt was made with, so a test can prove both forms
    were tried rather than inferring it from the absence of an exception.
    """

    real_utime = os.utime
    saved_supports_fd = os.supports_fd
    attempts: list[object] = []

    def failing_utime(path, *_args, **_kwargs):  # noqa: ANN001, ANN002, ANN003
        attempts.append(path)
        raise error

    os.utime = failing_utime  # type: ignore[assignment]
    os.supports_fd = frozenset(saved_supports_fd) | {failing_utime}  # type: ignore[assignment]
    try:
        yield attempts
    finally:
        os.supports_fd = saved_supports_fd  # type: ignore[assignment]
        os.utime = real_utime  # type: ignore[assignment]


class DescriptorTimeCapabilityTests(unittest.TestCase):
    """The probe itself: why ``hasattr`` was the wrong question."""

    def test_probe_answers_the_os_capability_table(self) -> None:
        self.assertEqual(
            platform_compat.supports_descriptor_times(), os.utime in os.supports_fd
        )

    def test_a_hasattr_probe_would_have_passed_where_the_call_fails(self) -> None:
        # This is the whole reason the bug shipped: the guard idiom used three
        # lines above the crash reports "available" on the platform that raises.
        with simulated_windows():
            self.assertTrue(hasattr(os, "utime"))
            self.assertFalse(platform_compat.supports_descriptor_times())

    def test_the_pre_fix_call_still_raises_under_the_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = _write_source_volume(Path(directory))
            descriptor = os.open(source, os.O_RDONLY)
            try:
                with simulated_windows():
                    with self.assertRaises(TypeError) as caught:
                        os.utime(descriptor, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS))
            finally:
                os.close(descriptor)
        self.assertEqual(str(caught.exception), FD_REJECTED_MESSAGE)


class UtimeNsTests(unittest.TestCase):
    """The helper's own contract, on this host and on a simulated Windows."""

    @contextlib.contextmanager
    def _pair(self) -> Iterator[tuple[Path, Path, int]]:
        """Own the descriptor and the directory together.

        Windows refuses to delete a file that still has an open handle, so the
        descriptor has to close before the temporary directory is torn down.
        ``addCleanup`` runs at the end of the test method, which is after the
        directory context has already exited and failed.
        """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _write_source_volume(root)
            output = root / "copied" / "0A"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(_volume_body())
            descriptor = os.open(output, os.O_RDWR | getattr(os, "O_BINARY", 0))
            try:
                yield source, output, descriptor
            finally:
                os.close(descriptor)

    @unittest.skipUnless(
        platform_compat.supports_descriptor_times(),
        "this host has no descriptor form of os.utime; the path form is covered "
        "by the simulated-Windows sibling below",
    )
    def test_stamps_through_the_descriptor_where_supported(self) -> None:
        with self._pair() as (_, output, descriptor):
            applied = platform_compat.utime_ns(
                descriptor, None, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS)
            )
            self.assertTrue(applied)
            self.assertEqual(os.stat(output).st_mtime_ns, SOURCE_MTIME_NS)

    def test_stamps_through_the_path_when_the_descriptor_form_is_absent(self) -> None:
        with self._pair() as (_, output, descriptor):
            with simulated_windows():
                applied = platform_compat.utime_ns(
                    descriptor, output, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS)
                )
            self.assertTrue(applied)
            self.assertEqual(os.stat(output).st_mtime_ns, SOURCE_MTIME_NS)

    def test_reports_a_skip_when_no_path_can_be_consulted(self) -> None:
        with self._pair() as (_, output, descriptor):
            untouched = os.stat(output).st_mtime_ns
            with simulated_windows():
                applied = platform_compat.utime_ns(
                    descriptor, None, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS)
                )
            # False, not an exception and not a pretended success.
            self.assertFalse(applied)
            self.assertEqual(os.stat(output).st_mtime_ns, untouched)

    def test_a_failing_utime_is_reported_rather_than_raised(self) -> None:
        for error in (
            TypeError(FD_REJECTED_MESSAGE),
            OSError(errno.EPERM, "Operation not permitted"),
        ):
            with self.subTest(error=type(error).__name__):
                with self._pair() as (_, output, descriptor):
                    with utime_always_raising(error) as attempts:
                        applied = platform_compat.utime_ns(
                            descriptor, output, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS)
                        )
                    self.assertFalse(applied)
                    # Both forms were really tried, and neither escaped.
                    self.assertIn(descriptor, attempts)
                    self.assertIn(output, attempts)

    def test_the_path_fallback_refuses_a_name_that_is_no_longer_the_file(self) -> None:
        # The one place a name is consulted must not be redirectable: a decoy
        # moved into the output's name between open and stamp is skipped, not
        # stamped, because its (st_dev, st_ino) is not the descriptor's.
        with self._pair() as (_, output, descriptor):
            root = output.parent.parent
            decoy = root / "decoy"
            decoy.write_bytes(b"decoy contents")
            decoy_before = os.stat(decoy).st_mtime_ns
            try:
                os.replace(decoy, output)
            except PermissionError as exc:
                # Windows will not rename over a name whose file this process
                # still holds open, so the substitution this guards against
                # cannot be staged there at all while the descriptor lives.
                self.skipTest(f"this platform refuses the substitution: {exc}")
            with simulated_windows():
                applied = platform_compat.utime_ns(
                    descriptor, output, ns=(SOURCE_ATIME_NS, SOURCE_MTIME_NS)
                )
            self.assertFalse(applied)
            self.assertEqual(os.stat(output).st_mtime_ns, decoy_before)


class CopyFdMetadataTests(unittest.TestCase):
    """The shipped metadata step, driven directly in all three copies."""

    def _prepared(self, directory: Path) -> tuple[Path, Path]:
        source = _write_source_volume(directory)
        output = directory / "copied" / "0A"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(_volume_body())
        os.chmod(output, OUTPUT_CREATE_MODE)
        return source, output

    def _copy(self, module, source: Path, output: Path) -> None:  # noqa: ANN001
        source_descriptor = os.open(source, os.O_RDONLY)
        try:
            output_descriptor = os.open(output, os.O_RDWR)
            try:
                module._copy_fd_metadata(
                    source_descriptor,
                    output_descriptor,
                    os.fstat(source_descriptor),
                    output,
                )
            finally:
                os.close(output_descriptor)
        finally:
            os.close(source_descriptor)

    def test_copies_mode_and_times_on_this_host(self) -> None:
        for module in COPY_MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    source, output = self._prepared(Path(directory))
                    self._copy(module, source, output)
                    if HOST_RECORDS_POSIX_MODES:
                        self.assertEqual(
                            stat.S_IMODE(os.stat(output).st_mode), SOURCE_MODE
                        )
                    self.assertEqual(output.read_bytes(), _volume_body())
                    if platform_compat.supports_descriptor_times():
                        self.assertEqual(
                            os.stat(output).st_mtime_ns, os.stat(source).st_mtime_ns
                        )

    def test_completes_under_simulated_windows(self) -> None:
        # Both descriptor forms this step used are gone under the simulation --
        # os.fchmod does not exist and os.utime refuses the int -- so this is
        # the whole reported failure, and the output must still be correct.
        for module in COPY_MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    source, output = self._prepared(Path(directory))
                    with simulated_windows():
                        self._copy(module, source, output)
                    self.assertEqual(output.read_bytes(), _volume_body())
                    if HOST_RECORDS_POSIX_MODES:
                        self.assertEqual(
                            stat.S_IMODE(os.stat(output).st_mode), SOURCE_MODE
                        )
                    self.assertEqual(
                        os.stat(output).st_mtime_ns, os.stat(source).st_mtime_ns
                    )

    def test_a_raising_utime_never_escapes_the_copy(self) -> None:
        for module in COPY_MODULES:
            for error in (
                TypeError(FD_REJECTED_MESSAGE),
                OSError(errno.EPERM, "Operation not permitted"),
            ):
                with self.subTest(module=module.__name__, error=type(error).__name__):
                    with tempfile.TemporaryDirectory() as directory:
                        source, output = self._prepared(Path(directory))
                        with utime_always_raising(error) as attempts:
                            self._copy(module, source, output)
                        self.assertTrue(attempts, "utime was never attempted")
                        # The two things that actually matter survive intact.
                        self.assertEqual(output.read_bytes(), _volume_body())
                        if HOST_RECORDS_POSIX_MODES:
                            self.assertEqual(
                                stat.S_IMODE(os.stat(output).st_mode), SOURCE_MODE
                            )


class CopiedVolumeTransactionTests(unittest.TestCase):
    """End to end through the writers the Windows user actually invoked."""

    def _build(self, module, source: Path, output: Path) -> None:  # noqa: ANN001
        module._write_copied_volume(
            source, output, _entry(ENTRY_OFFSET, len(REPLACEMENT)), REPLACEMENT
        )

    def _assert_copied(self, source: Path, output: Path) -> None:
        expected = bytearray(_volume_body())
        expected[ENTRY_OFFSET : ENTRY_OFFSET + len(REPLACEMENT)] = REPLACEMENT
        self.assertEqual(output.read_bytes(), bytes(expected))
        if HOST_RECORDS_POSIX_MODES:
            self.assertEqual(stat.S_IMODE(os.stat(output).st_mode), SOURCE_MODE)
        self.assertEqual(os.stat(source).st_mtime_ns, SOURCE_MTIME_NS)

    def test_copied_volume_builds_under_simulated_windows(self) -> None:
        # The fixture is built on the real host and only the writer runs under
        # the simulation, exactly as a Windows user meets an existing source 0A.
        for module in COPY_MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = _write_source_volume(root)
                    output = root / "build" / "0A"
                    with simulated_windows():
                        self._build(module, source, output)
                    self._assert_copied(source, output)
                    self.assertEqual(os.stat(output).st_mtime_ns, SOURCE_MTIME_NS)

    def test_copied_volume_builds_when_utime_always_fails(self) -> None:
        for module in COPY_MODULES:
            with self.subTest(module=module.__name__):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = _write_source_volume(root)
                    output = root / "build" / "0A"
                    with utime_always_raising(OSError(errno.EROFS, "Read-only")):
                        self._build(module, source, output)
                    self._assert_copied(source, output)

    def test_logocache_extent_volume_builds_under_simulated_windows(self) -> None:
        # The fourth reach: this module has no local metadata step, it imports
        # apf_logo_patch's, so it is only fixed if the shared definition is.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _write_source_volume(root)
            output = root / "build" / "0A"
            extent = apf_logocache_patch.Extent(
                label="test", offset=ENTRY_OFFSET, replacement=REPLACEMENT
            )
            with simulated_windows():
                apf_logocache_patch._write_copied_volume_extents(
                    source, output, [extent]
                )
            self._assert_copied(source, output)
            self.assertEqual(os.stat(output).st_mtime_ns, SOURCE_MTIME_NS)


class CallSiteTests(unittest.TestCase):
    """Every reach into the shared step must supply the path it can fall back to."""

    def test_the_shared_definitions_take_an_output_path(self) -> None:
        for module in COPY_MODULES:
            with self.subTest(module=module.__name__):
                parameters = inspect.signature(module._copy_fd_metadata).parameters
                self.assertIn("output_path", parameters)

    def test_every_call_site_passes_an_output_path(self) -> None:
        for module in CALL_SITE_MODULES:
            source_path = Path(module.__file__)
            tree = ast.parse(source_path.read_text(encoding="utf-8"))
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and _called_name(node.func) == "_copy_fd_metadata"
            ]
            with self.subTest(module=module.__name__):
                self.assertTrue(calls, "expected at least one call site")
                for call in calls:
                    self.assertEqual(
                        len(call.args) + len(call.keywords),
                        4,
                        f"{source_path.name}:{call.lineno} drops the output path",
                    )

    def test_the_cross_module_reaches_share_the_fixed_definition(self) -> None:
        # Neither of these has a body of its own to patch, so identity with the
        # module that does is the only thing that makes them fixed.
        self.assertIs(
            apf_logocache_patch._copy_fd_metadata, apf_logo_patch._copy_fd_metadata
        )
        self.assertIs(apf_jersey_selector_patch.transport, apf_texture_patch)


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


if __name__ == "__main__":
    unittest.main()
