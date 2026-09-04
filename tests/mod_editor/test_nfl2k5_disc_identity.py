"""A refusal has to say WHICH disc image this is.

Two failures arrived from one user on one image named ``ESPN NFL 2K5 (USA).iso``:

    ValueError: pack-0 schedule template is foreign: ROST stored size is not retail
    MISMATCH: 2802 run(s) hold bytes that are neither the expected base nor the
    patched bytes

Both messages are true and neither is actionable, because both are the same
sentence for four different images: an ``.xiso``, a raw dump with the video
partition still in front, a **repack** (retail file bytes, rebuilt at other
sectors) and a **pre-modded** disc.  Two of those are fine, one builds but can
never take a byte-run patch, and one has to be thrown away -- and the run count
does not tell them apart.

The images here are synthetic: an XDVDFS directory plus only the files the
checks read, at four different layouts, with the retail digests and the retail
layout table pointed at the fixture so the *classification* is what is under
test rather than 6.3 GB of game data.
"""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
import nfl2k5_franchise_schedule as fs  # noqa: E402
from mod_editor.core import mod_build, modpack  # noqa: E402
from mod_editor.core import nfl2k5_disc_identity as identity  # noqa: E402
from nfl2k5_xiso_fixture import dir_node  # noqa: E402

SECTOR = 2048
RAW_BASE = 0x02080000          # a real raw-dump base (XGD3), small enough for a temp file

XBE_SECTOR, XBE_SIZE = 60, 0x1000
PACK0_SECTOR, PACK0_SIZE = 80, 0x2000
PACK9_SECTOR, PACK9_SIZE = 100, 0x800
UPDATE_SECTOR, UPDATE_SIZE = 50, 0x400
ROOT_SECTOR = (xiso.XDVDFS_HEADER_OFFSET // SECTOR) + 1
SUBDIR_SECTOR = 40
END_SECTOR = 128

ROST_AT = 0x800                # where the fixture keeps its "roster resource"
ROST_LEN = 0x400

FIXTURE_LAYOUT = (
    ("update.xbe", UPDATE_SECTOR * SECTOR, UPDATE_SIZE),
    ("default.xbe", XBE_SECTOR * SECTOR, XBE_SIZE),
    ("vc_53450030/0", PACK0_SECTOR * SECTOR, PACK0_SIZE),
    ("vc_53450030/9", PACK9_SECTOR * SECTOR, PACK9_SIZE),
)


def _filler(seed: int, length: int) -> bytes:
    return bytes((index * 7 + seed) & 0xFF for index in range(length))


RETAIL_FILES = {
    "update.xbe": _filler(1, UPDATE_SIZE),
    "default.xbe": b"XBEH" + _filler(2, XBE_SIZE - 4),
    "vc_53450030/0": _filler(3, PACK0_SIZE),
    "vc_53450030/9": _filler(4, PACK9_SIZE),
}


def build_image(path: Path, *, base: int = 0, shift: int = 0,
                files: dict[str, bytes] | None = None) -> Path:
    """One synthetic disc image.

    ``base`` puts a video partition in front (a raw dump); ``shift`` moves every
    file and the sub-directory to other sectors (a repack); ``files`` overrides
    file content (a pre-modded disc).
    """

    content = dict(RETAIL_FILES if files is None else files)
    places = {
        "update.xbe": UPDATE_SECTOR + shift,
        "default.xbe": XBE_SECTOR + shift,
        "vc_53450030/0": PACK0_SECTOR + shift,
        "vc_53450030/9": PACK9_SECTOR + shift,
    }
    subdir_sector = SUBDIR_SECTOR + shift
    subdir = dir_node([(places["vc_53450030/0"], PACK0_SIZE, 0x80, "0"),
                       (places["vc_53450030/9"], PACK9_SIZE, 0x80, "9")])
    root = dir_node([(places["update.xbe"], UPDATE_SIZE, 0x80, "update.xbe"),
                     (places["default.xbe"], XBE_SIZE, 0x80, "default.xbe"),
                     (subdir_sector, len(subdir), 0x10, "vc_53450030")])
    header = bytearray(SECTOR)
    header[:20] = xiso.XDVDFS_MAGIC
    struct.pack_into("<II", header, 20, ROOT_SECTOR, len(root))
    header[-20:] = xiso.XDVDFS_MAGIC

    with path.open("wb") as stream:
        if base:
            # a raw dump keeps the video partition, and that partition is itself an XDVDFS
            # filesystem: the decoy that makes "assume the file starts at the game" go wrong
            video_root = dir_node([(60, 0x800, 0x80, "openingmovie.xmv")])
            video = bytearray(SECTOR)
            video[:20] = xiso.XDVDFS_MAGIC
            struct.pack_into("<II", video, 20, ROOT_SECTOR, len(video_root))
            video[-20:] = xiso.XDVDFS_MAGIC
            stream.seek(xiso.XDVDFS_HEADER_OFFSET)
            stream.write(bytes(video))
            stream.seek(ROOT_SECTOR * SECTOR)
            stream.write(video_root)
        stream.seek(base + xiso.XDVDFS_HEADER_OFFSET)
        stream.write(bytes(header))
        stream.seek(base + ROOT_SECTOR * SECTOR)
        stream.write(root)
        stream.seek(base + subdir_sector * SECTOR)
        stream.write(subdir)
        for name, payload in content.items():
            stream.seek(base + places[name] * SECTOR)
            stream.write(payload)
        stream.truncate(base + (END_SECTOR + shift) * SECTOR)
    return path


def fixture_pins():
    """Point the identifier's retail pins at the fixture instead of the 6.3 GB disc."""

    return mock.patch.multiple(
        identity,
        RETAIL_LAYOUT=FIXTURE_LAYOUT,
        RETAIL_XBE_SIZE=XBE_SIZE,
        RETAIL_XBE_SHA256=hashlib.sha256(RETAIL_FILES["default.xbe"]).hexdigest(),
        RETAIL_PACK0_SIZE=PACK0_SIZE,
        RETAIL_PACK0_SHA256=hashlib.sha256(RETAIL_FILES["vc_53450030/0"]).hexdigest(),
        ROST_OFFSET_IN_PACK0=ROST_AT,
        ROST_OUTER_SIZE=ROST_LEN,
        RETAIL_ROST_SHA256=hashlib.sha256(
            RETAIL_FILES["vc_53450030/0"][ROST_AT: ROST_AT + ROST_LEN]).hexdigest(),
    )


class DiscIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="disc-identity-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.xiso = build_image(self.tmp / "a_xiso.iso")
        self.raw = build_image(self.tmp / "b_raw.iso", base=RAW_BASE)
        self.repack = build_image(self.tmp / "c_repack.iso", shift=0x100)
        modded = dict(RETAIL_FILES)
        pack = bytearray(modded["vc_53450030/0"])
        pack[ROST_AT + 4: ROST_AT + 8] = b"\x11\x22\x33\x44"      # somebody else's roster mod
        modded["vc_53450030/0"] = bytes(pack)
        self.modded = build_image(self.tmp / "d_modded.iso", files=modded)
        self.pins = fixture_pins()
        self.pins.start()
        self.addCleanup(self.pins.stop)

    # -- the five answers -------------------------------------------------
    def test_an_xiso_is_named_a_retail_xiso(self) -> None:
        found = identity.identify(self.xiso)
        self.assertEqual(found.kind, "retail-xiso")
        self.assertEqual(found.headline, identity.RETAIL_XISO)
        self.assertEqual(found.partition_base, 0)
        self.assertTrue(found.retail_files and found.can_build and found.can_take_a_byte_run_patch)

    def test_a_raw_dump_is_named_a_raw_dump_and_not_read_at_zero(self) -> None:
        found = identity.identify(self.raw)
        self.assertEqual(found.kind, "retail-raw")
        self.assertEqual(found.headline, identity.RETAIL_RAW)
        # the video partition in front carries its own XDVDFS header; the game one is the answer
        self.assertEqual(found.partition_base, RAW_BASE)
        self.assertTrue(found.can_take_a_byte_run_patch)
        self.assertIn("Build and Apply both work", found.line())

    def test_a_repack_is_named_a_repack_and_keeps_build_but_loses_apply(self) -> None:
        found = identity.identify(self.repack)
        self.assertEqual(found.kind, "repack")
        self.assertEqual(found.headline, identity.REPACK)
        self.assertTrue(found.retail_files)          # the file bytes ARE retail
        self.assertTrue(found.can_build)             # every writer resolves through the directory
        self.assertFalse(found.can_take_a_byte_run_patch)
        self.assertIn("extract-xiso -r", found.line())
        self.assertIn("Build", found.detail)

    def test_a_repack_still_resolves_its_files_so_build_can_run(self) -> None:
        """"Build works on a repack" is a claim about the resolver, so check the resolver."""

        import os as _os
        fd = _os.open(self.repack, _os.O_RDONLY | getattr(_os, "O_BINARY", 0))   # Windows opens text-mode by default
        try:
            size = _os.fstat(fd).st_size
            self.assertEqual(xiso.xbe_extent(fd, size), ((XBE_SECTOR + 0x100) * SECTOR, XBE_SIZE))
            self.assertEqual(xiso.pack_extent(fd, size, "0"), ((PACK0_SECTOR + 0x100) * SECTOR, PACK0_SIZE))
            self.assertEqual(xiso.read_exact(fd, (PACK0_SECTOR + 0x100) * SECTOR, PACK0_SIZE),
                             RETAIL_FILES["vc_53450030/0"])
        finally:
            _os.close(fd)

    def test_a_pre_modded_disc_is_named_modified_and_says_which_file(self) -> None:
        found = identity.identify(self.modded)
        self.assertEqual(found.kind, "modified")
        self.assertEqual(found.headline, identity.MODIFIED)
        self.assertFalse(found.retail_files)
        self.assertIn("vc_53450030/0", found.detail)
        self.assertIn("default.xbe still does", found.detail)

    def test_a_deep_look_hashes_the_whole_pack(self) -> None:
        shallow = identity.identify(self.modded)
        deep = identity.identify(self.modded, deep=True)
        self.assertFalse(shallow.checked_pack0_fully)
        self.assertTrue(deep.checked_pack0_fully)
        self.assertEqual(deep.kind, "modified")

    def test_supplied_pack_bytes_are_used_instead_of_a_second_read(self) -> None:
        pack = RETAIL_FILES["vc_53450030/0"]
        found = identity.identify(self.xiso, pack0=pack)
        self.assertEqual(found.kind, "retail-xiso")
        self.assertTrue(found.checked_pack0_fully)

    def test_something_that_is_not_a_disc_is_not_called_a_bad_dump(self) -> None:
        other = self.tmp / "notes.txt"
        other.write_bytes(b"this is not a disc image" * 100)
        found = identity.identify(other)
        self.assertEqual(found.kind, "not-a-disc")
        self.assertEqual(found.headline, identity.UNKNOWN)

    def test_a_trimmed_dump_is_still_a_dump(self) -> None:
        """Images that drop update.xbe are common and change nothing the studio reads."""

        # a retail layout that expects dashupdate.xbe, on an image whose directory has no such file
        with mock.patch.object(identity, "RETAIL_LAYOUT",
                               FIXTURE_LAYOUT[:1] + (("dashupdate.xbe", 0xDAE000, 100),) + FIXTURE_LAYOUT[1:]):
            found = identity.identify(self.xiso)
        self.assertEqual(found.kind, "retail-xiso")
        self.assertTrue(found.can_take_a_byte_run_patch)
        self.assertIn("dashupdate.xbe is missing", found.detail)

    def test_a_pack_of_the_wrong_size_is_unknown_not_modified(self) -> None:
        """A pack the studio reads that is not its retail size is not a mod, it is untrustworthy."""

        with mock.patch.object(identity, "RETAIL_LAYOUT",
                               FIXTURE_LAYOUT[:3] + (("vc_53450030/9", PACK9_SECTOR * SECTOR, PACK9_SIZE * 2),)):
            found = identity.identify(self.xiso)
        self.assertEqual(found.kind, "unknown")
        self.assertIn("vc_53450030/9", found.detail)
        self.assertEqual(found.layout, "unknown")

    def test_a_disc_without_the_game_is_unknown_not_modified(self) -> None:
        with mock.patch.object(identity, "RETAIL_PACK0_PATH", "vc_53450030/2"):
            found = identity.identify(self.xiso)
        self.assertEqual(found.kind, "unknown")
        self.assertIn("vc_53450030/2", found.detail)

    # -- the refusals quote it -------------------------------------------
    def test_a_build_refusal_names_the_disc(self) -> None:
        raised = ValueError("pack-0 schedule template is foreign: ROST stored size is not retail")
        message = str(mod_build._with_identity(raised, self.modded, True))
        self.assertIn("This image is:", message)
        self.assertIn(identity.MODIFIED, message)
        # and never twice
        again = str(mod_build._with_identity(ValueError(message), self.modded, True))
        self.assertEqual(again, message)

    def test_a_non_image_refusal_is_left_alone(self) -> None:
        raised = ValueError("the 2026 season needs a disc image")
        self.assertIs(mod_build._with_identity(raised, self.xiso, False), raised)


class ApplyMessageTests(unittest.TestCase):
    """What Apply says for each format, using a patch exported from the xiso."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="disc-identity-apply-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.xiso = build_image(self.tmp / "a_xiso.iso")
        self.raw = build_image(self.tmp / "b_raw.iso", base=RAW_BASE)
        self.repack = build_image(self.tmp / "c_repack.iso", shift=0x100)
        modded = dict(RETAIL_FILES)
        pack = bytearray(modded["vc_53450030/0"])
        pack[ROST_AT + 0x40: ROST_AT + 0x60] = b"\x5a" * 0x20
        modded["vc_53450030/0"] = bytes(pack)
        self.modded = build_image(self.tmp / "d_modded.iso", files=modded)
        self.pins = fixture_pins()
        self.pins.start()
        self.addCleanup(self.pins.stop)

        # a patch that changes bytes in default.xbe and in the pack's roster resource
        patched = dict(RETAIL_FILES)
        xbe = bytearray(patched["default.xbe"])
        xbe[0x200: 0x210] = b"\xa5" * 0x10
        patched["default.xbe"] = bytes(xbe)
        pack = bytearray(patched["vc_53450030/0"])
        pack[ROST_AT + 0x40: ROST_AT + 0x60] = b"\x3c" * 0x20
        patched["vc_53450030/0"] = bytes(pack)
        self.patched_image = build_image(self.tmp / "patched.iso", files=patched)
        self.pack_path = self.tmp / "fixture.2k5patch"
        modpack.export(self.xiso, self.patched_image, self.pack_path, {"name": "fixture"})

    def test_the_xiso_and_the_raw_dump_are_both_ready(self) -> None:
        for image in (self.xiso, self.raw):
            with self.subTest(image=image.name):
                report = modpack.check(self.pack_path, image)
                self.assertEqual(report["state"], "ready")
                self.assertIsNone(report["identity"])       # nothing to explain when it works

    def test_a_repack_says_repack_instead_of_a_run_count(self) -> None:
        report = modpack.check(self.pack_path, self.repack)
        self.assertEqual(report["state"], "mismatch")
        self.assertEqual(report["identity"]["kind"], "repack")
        self.assertIn("This image is:", report["explanation"])
        self.assertIn("extract-xiso -r", report["explanation"])
        self.assertFalse(report["identity"]["can_take_a_byte_run_patch"])

    def test_a_pre_modded_disc_says_modified(self) -> None:
        report = modpack.check(self.pack_path, self.modded)
        self.assertEqual(report["state"], "mismatch")
        self.assertEqual(report["identity"]["kind"], "modified")
        self.assertIn(identity.MODIFIED, report["explanation"])


class RetailEquivalenceTests(unittest.TestCase):
    """A pack built on a working copy should not frighten people who hold retail."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="disc-identity-export-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.retail = build_image(self.tmp / "retail.iso")
        self.pins = fixture_pins()
        self.pins.start()
        self.addCleanup(self.pins.stop)

    def _export(self, base_files: dict[str, bytes], patched_files: dict[str, bytes],
                name: str, **kwargs) -> dict:
        base = build_image(self.tmp / f"{name}-base.iso", files=base_files)
        patched = build_image(self.tmp / f"{name}-patched.iso", files=patched_files)
        return modpack.export(base, patched, self.tmp / f"{name}.2k5patch", {"name": name}, **kwargs)

    def test_a_working_copy_whose_edits_miss_every_run_is_retail_equivalent(self) -> None:
        base_files = dict(RETAIL_FILES)
        other = bytearray(base_files["vc_53450030/9"])
        other[0x100: 0x120] = b"\x77" * 0x20          # the working copy's own edit, far from any run
        base_files["vc_53450030/9"] = bytes(other)
        patched_files = dict(base_files)
        xbe = bytearray(patched_files["default.xbe"])
        xbe[0x300: 0x310] = b"\xa5" * 0x10
        patched_files["default.xbe"] = bytes(xbe)

        receipt = self._export(base_files, patched_files, "equivalent", retail_image=self.retail)
        self.assertTrue(receipt["base"]["is_retail_equivalent"])
        self.assertFalse(receipt["base"]["is_retail"])
        self.assertIn("retail-equivalent", receipt["base"]["label"])
        self.assertEqual(receipt["retail_equivalence"]["differing"], 0)
        # and the loader keeps the claim
        info = modpack.inspect(receipt["pack"])
        self.assertTrue(info["base"]["is_retail_equivalent"])
        # the pack really does apply to a retail dump
        self.assertEqual(modpack.check(receipt["pack"], self.retail)["state"], "ready")

    def test_a_working_copy_edited_inside_a_run_is_not_called_equivalent(self) -> None:
        base_files = dict(RETAIL_FILES)
        xbe = bytearray(base_files["default.xbe"])
        xbe[0x300: 0x310] = b"\x11" * 0x10            # the base already differs where the run lands
        base_files["default.xbe"] = bytes(xbe)
        patched_files = dict(base_files)
        xbe = bytearray(patched_files["default.xbe"])
        xbe[0x300: 0x310] = b"\xa5" * 0x10
        patched_files["default.xbe"] = bytes(xbe)

        receipt = self._export(base_files, patched_files, "custom", retail_image=self.retail)
        self.assertFalse(receipt["base"]["is_retail_equivalent"])
        self.assertIn("custom base", receipt["base"]["label"])
        self.assertGreater(receipt["retail_equivalence"]["differing"], 0)

    def test_without_a_retail_image_nothing_is_claimed(self) -> None:
        patched_files = dict(RETAIL_FILES)
        xbe = bytearray(patched_files["default.xbe"])
        xbe[0x300: 0x310] = b"\xa5" * 0x10
        patched_files["default.xbe"] = bytes(xbe)
        receipt = self._export(RETAIL_FILES, patched_files, "unclaimed")
        self.assertFalse(receipt["base"]["is_retail_equivalent"])
        self.assertIsNone(receipt["retail_equivalence"])

    def test_a_repack_offered_as_the_retail_proof_is_refused(self) -> None:
        repack = build_image(self.tmp / "repack.iso", shift=0x100)
        patched_files = dict(RETAIL_FILES)
        xbe = bytearray(patched_files["default.xbe"])
        xbe[0x300: 0x310] = b"\xa5" * 0x10
        patched_files["default.xbe"] = bytes(xbe)
        receipt = self._export(RETAIL_FILES, patched_files, "badproof", retail_image=repack)
        self.assertFalse(receipt["base"]["is_retail_equivalent"])
        self.assertIn("not a retail dump", receipt["retail_equivalence"]["reason"])


class ScheduleResourceTests(unittest.TestCase):
    """The schedule template is a resource, not an address."""

    def test_the_roster_resource_is_found_where_it_actually_is(self) -> None:
        pack = fs.synthetic_pack(fs.PACK_ROST_OFFSET)
        self.assertEqual(fs.locate_pack_rost(pack), fs.PACK_ROST_OFFSET)
        status = fs.pack_status(pack)
        self.assertEqual(status["rost_offset"], f"0x{fs.PACK_ROST_OFFSET:x}")
        self.assertFalse(status["rost_relocated"])
        template_reason = status["reason"]

        # the same resource 64 KiB further in: read there, and refused for the same reason as
        # before rather than for "ROST stored size is not retail", which would be a claim about
        # byte 0x392804 and not about the pack
        moved = fs.synthetic_pack(fs.PACK_ROST_OFFSET + 0x10000)
        self.assertEqual(fs.locate_pack_rost(moved), fs.PACK_ROST_OFFSET + 0x10000)
        status = fs.pack_status(moved)
        self.assertEqual(status["rost_offset"], f"0x{fs.PACK_ROST_OFFSET + 0x10000:x}")
        self.assertTrue(status["rost_relocated"])
        self.assertEqual(status["reason"], template_reason)

    def test_a_pack_with_no_roster_resource_is_still_foreign(self) -> None:
        pack = bytearray(fs.synthetic_pack(fs.PACK_ROST_OFFSET))
        struct.pack_into("<I", pack, fs.PACK_ROST_OFFSET + 4, fs.ROST_BODY_SIZE + 0x400)
        self.assertIsNone(fs.locate_pack_rost(bytes(pack)))
        status = fs.pack_status(bytes(pack))
        self.assertEqual(status["state"], "foreign")
        self.assertEqual(status["reason"], "ROST stored size is not retail")


class PanelTests(unittest.TestCase):
    """The panels say it before the user presses anything."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="disc-identity-panel-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.repack = build_image(self.tmp / "c_repack.iso", shift=0x100)
        self.pins = fixture_pins()
        self.pins.start()
        self.addCleanup(self.pins.stop)

    def test_the_apply_panel_names_the_disc_before_any_check(self) -> None:
        from mod_editor.gui.share_panel_qt import SharePanel
        panel = SharePanel()
        try:
            panel.source_field.setText(str(self.repack))
            text = panel.describe_source()
            self.assertIn(identity.REPACK, text)
            self.assertIn("Use the Build tab", text)
            self.assertEqual(panel.source_identity.text(), text)
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_the_build_header_leads_with_the_disc(self) -> None:
        from mod_editor.gui.build_panel_qt import BuildPanel
        panel = BuildPanel()
        try:
            panel.apply_state({"path": str(self.repack), "container": "xiso",
                               "disc_identity_line": identity.identify(self.repack).line()})
            self.assertIn(identity.REPACK, panel.source_status.text())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
