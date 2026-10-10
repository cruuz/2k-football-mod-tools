"""Beta 77 E1: a verified install is never refused because the source's file details moved.

A Windows 11 tester installed SOFTDRINK 2K28 from Build & Share with the source
disc and the output both under OneDrive. After the whole 6 GB image was rebuilt,
read back and proved against the pack's SHA-256 values, the last statement of
``modpack_files.apply`` compared a stat tuple (device, file ID, size, mtime and
st_ctime) taken when the install began with one taken at the end, found a
difference and threw the finished image away: "Source changed during
installation".

No byte had changed. The tuple is metadata, and the metadata of a file inside a
OneDrive folder is rewritten by the sync client while it works (Files
On-Demand hydration, upload bookkeeping), by antivirus and by search indexers.
On Windows st_ctime is not even a change time: CPython 3.12 reports the file's
CREATION time there, which sync software can reset. Beta 72.1 had already
ruled that a stat comparison can neither prove nor disprove a content change
(tests/mod_editor/test_b721_change_time_identity.py); the Format 3 install
brought the gate back.

The contract these tests pin:

* metadata that moves under an open source (a real ``os.utime`` on every
  platform, and a Windows-style creation-time reset through the stat call) never
  refuses an install, a check, an author proof or an export whose bytes were all
  proved against SHA-256 values;
* what refuses is content, and the proof sees it even when every stat field is
  restored (same size, same mtime, same file ID);
* nothing is published and no ``.part`` is left when content differs.

Synthetic images only; no retail bytes.
"""
import contextlib
import hashlib
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(Path(__file__).parent)]
from test_modpack_files import image, m, f, xc

# The creation time a Windows sync client might write over the real one.
RESET_CREATION_NS = 1_700_000_000_000_000_000
# What the receipt calls st_ctime_ns on this platform (creation time on Windows, change time elsewhere).
CTIME_LABEL = "creation time" if os.name == "nt" else "change time"


def make_fixture(root: Path):
    """A small retail-like source, a finished disc and the pack between them."""
    rng = random.Random(77)
    original = {"default.xbe": b"XBEH" + rng.randbytes(5000), "a": rng.randbytes(300_000),
                "same": b"unchanged " * 900}
    edited = bytearray(original["a"])
    edited[10:15] = b"EDIT!"
    finished = dict(original, a=bytes(edited), grow=b"new" * 4000)
    original["grow"] = b"old"
    base = image(root / "base.iso", original)
    built_raw = image(root / "built-raw.iso", finished, order=list(reversed(finished)))
    built = root / "built.iso"
    xc.compact_copy(built_raw, built)
    pack = root / "e1.2k5patch"
    f.export(base, built, pack, require_retail=False)
    return original, base, built, pack


def touch_mtime(path: Path, seconds: int = 7) -> None:
    """A real metadata write that leaves every byte alone."""
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + seconds * 1_000_000_000))


def fd_stat(path: Path) -> os.stat_result:
    """os.fstat of a fresh descriptor: the stat family the install reads, never a path stat."""
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def windows_creation_time(path: Path):
    """Report st_ctime_ns the way Windows does: a creation time a sync client can reset.

    Every os.fstat answer for ``path`` carries ``state["created"]``; the test moves it
    mid-install the way OneDrive rewriting a placeholder would, while size, mtime and
    file ID stay as they were. Only fd stats are patched, and the file is recognised by
    an fd stat too: the install reads through one descriptor, and on Windows a path stat
    and an fd stat do not agree on device, file ID or st_ctime
    (platform_compat.supports_change_time_identity).
    """
    real_fstat = os.fstat
    identity = fd_stat(path)
    state = {"created": identity.st_ctime_ns}

    def with_creation(info):
        if (info.st_dev, info.st_ino) != (identity.st_dev, identity.st_ino):
            return info
        extra = {name: getattr(info, name) for name in (
            "st_atime_ns", "st_mtime_ns", "st_blksize", "st_blocks", "st_rdev", "st_flags",
            "st_gen", "st_birthtime", "st_file_attributes", "st_reparse_tag") if hasattr(info, name)}
        extra["st_ctime_ns"] = state["created"]
        return os.stat_result(tuple(info)[:10], extra)

    with mock.patch.object(os, "fstat", lambda *a, **k: with_creation(real_fstat(*a, **k))):
        yield state


class SourceMetadataDriftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original, self.base, self.built, self.pack = make_fixture(self.root)
        self.expected = self.built.read_bytes()

    def hook_once(self, stage, action):
        """A progress sink that runs ``action`` once, the first time ``stage`` reports."""
        fired = []

        def progress(name, done, total):
            if name == stage and not fired:
                fired.append(True)
                action()

        progress.fired = fired
        return progress

    def assertNoPartFiles(self):
        self.assertFalse(list(self.root.glob(".2k5-*.part")), "a refused install leaves no .part file")

    # --- install -------------------------------------------------------------------------

    def test_install_survives_the_source_mtime_moving_during_the_install(self):
        out = self.root / "out.iso"
        source_bytes = self.base.read_bytes()
        progress = self.hook_once("Verifying installed files", lambda: touch_mtime(self.base))
        receipt = m.apply(self.pack, self.base, out, progress=progress)
        self.assertTrue(progress.fired, "the touch happened mid-install")
        self.assertEqual(out.read_bytes(), self.expected)
        self.assertTrue(receipt["target"]["matches_author_result"])
        self.assertTrue(receipt["target"]["all_game_files_verified"])
        self.assertIn("modified time", receipt["source_metadata_changed"])
        self.assertEqual(self.base.read_bytes(), source_bytes, "the source is never modified")
        self.assertNoPartFiles()

    def test_install_survives_a_windows_creation_time_reset_during_the_install(self):
        out = self.root / "out.iso"
        with windows_creation_time(self.base) as state:
            progress = self.hook_once("Verifying installed files",
                                      lambda: state.update(created=RESET_CREATION_NS))
            receipt = m.apply(self.pack, self.base, out, progress=progress)
        self.assertTrue(progress.fired)
        self.assertEqual(out.read_bytes(), self.expected)
        self.assertEqual(receipt["source_metadata_changed"], [CTIME_LABEL])
        self.assertNoPartFiles()

    def test_an_untouched_source_reports_no_metadata_change(self):
        out = self.root / "out.iso"
        receipt = m.apply(self.pack, self.base, out)
        self.assertEqual(out.read_bytes(), self.expected)
        self.assertEqual(receipt["source_metadata_changed"], [])

    def test_changed_content_is_refused_even_when_every_stat_field_is_restored(self):
        """The stat gate is gone because the hashes already decide, in the direction that matters."""
        out = self.root / "out.iso"
        info = os.stat(self.base)
        layout_entry = None
        with self.base.open("rb", buffering=0) as stream:
            layout_entry = xc.read_layout(stream).entries["same"]

        def flip_one_byte_and_restore_the_stat():
            with self.base.open("r+b") as stream:
                stream.seek(layout_entry.byte_offset + 5)
                value = stream.read(1)
                stream.seek(layout_entry.byte_offset + 5)
                stream.write(bytes([value[0] ^ 0xFF]))
            os.utime(self.base, ns=(info.st_atime_ns, info.st_mtime_ns))

        # The last "Checking clean game files" report is after every required file was hashed,
        # so the flipped byte is read by the install itself, not by the up-front check.
        total = sum(r["before"]["size"] for r in m.inspect(self.pack)["files"])
        fired = []

        def progress(name, done, total_bytes):
            if name == "Checking clean game files" and done == total and not fired:
                fired.append(True)
                flip_one_byte_and_restore_the_stat()

        with windows_creation_time(self.base):
            with self.assertRaisesRegex(m.ModpackError, "SHA-256 differs"):
                m.apply(self.pack, self.base, out, progress=progress)
        self.assertTrue(fired)
        after = os.stat(self.base)
        self.assertEqual((after.st_size, after.st_mtime_ns), (info.st_size, info.st_mtime_ns),
                         "the stat really was restored: only the hashes can see this change")
        self.assertFalse(out.exists())
        self.assertNoPartFiles()

    # --- check -----------------------------------------------------------------------------

    def test_check_stays_ready_when_the_source_mtime_moves_while_it_runs(self):
        progress = self.hook_once("Checking pack payloads", lambda: touch_mtime(self.base))
        report = m.check(self.pack, self.base, progress=progress)
        self.assertTrue(progress.fired)
        self.assertEqual(report["state"], "ready", report["explanation"])

    def test_check_stays_ready_through_a_windows_creation_time_reset(self):
        with windows_creation_time(self.base) as state:
            progress = self.hook_once("Checking pack payloads",
                                      lambda: state.update(created=RESET_CREATION_NS))
            report = m.check(self.pack, self.base, progress=progress)
        self.assertTrue(progress.fired)
        self.assertEqual(report["state"], "ready", report["explanation"])

    # --- author tools (same shared gate) ----------------------------------------------------

    def test_pack_proof_does_not_refuse_on_input_metadata(self):
        loaded = m.load(self.pack)
        progress = self.hook_once("Proving exported files", lambda: touch_mtime(self.built))
        result = f.verify_against(loaded, self.base, self.built, progress=progress)
        self.assertTrue(progress.fired)
        self.assertTrue(result["all_files_byte_equal"])

    def test_export_does_not_refuse_on_input_metadata(self):
        again = self.root / "again.2k5patch"
        progress = self.hook_once("Hashing finished image", lambda: touch_mtime(self.base))
        result = f.export(self.base, self.built, again, require_retail=False, progress=progress)
        self.assertTrue(progress.fired)
        self.assertTrue(result["replay"]["all_files_byte_equal"])
        self.assertEqual(m.check(again, self.base)["state"], "ready")


if __name__ == "__main__":
    unittest.main()
