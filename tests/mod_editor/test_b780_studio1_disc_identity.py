"""b780 studio1 (Q67): a disc the Studio built says what it is, not "unknown image".

The released SOFTDRINK 2K28 discs (and any Customize build) carry a grown default.xbe and resized packs, so the retail size
check failed and the Build tab's first line read "unknown image. This is an xiso holding ESPN NFL 2K5, but default.xbe, ... is
missing or not its retail size. Neither Build nor Apply can trust it; use a dump of your own retail disc." above the very boxes
it marks Needs update.  A recognised grown executable now makes a disc "studio-built"; the released list names the release.
Synthetic images only (the layout, retail pins and XDVDFS helpers of test_nfl2k5_disc_identity).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl_uniform_color_xiso_direct_patch as xiso  # noqa: E402
import test_nfl2k5_disc_identity as base  # noqa: E402
from mod_editor.core import nfl2k5_depth_chart_storage as storage  # noqa: E402
from mod_editor.core import nfl2k5_disc_identity as identity  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from nfl2k5_xiso_fixture import dir_node  # noqa: E402

SECTOR = base.SECTOR
GROWN_XBE_SIZE = 0x1800                     # not the fixture's retail 0x1000
GROWN_PACK9_SIZE = 0x1000                   # not the fixture's retail 0x800
GROWN_XBE = b"XBEH" + bytes((index * 11 + 5) & 0xFF for index in range(GROWN_XBE_SIZE - 4))
GROWN_PACK9 = bytes((index * 3 + 9) & 0xFF for index in range(GROWN_PACK9_SIZE))


def build_studio_image(path: Path, *, xbe: bytes = GROWN_XBE, pack9: bytes | None = GROWN_PACK9) -> Path:
    """The fixture disc with a resized default.xbe and (unless ``pack9`` is None) a resized and then a missing pack 9."""

    pack9_sector = base.PACK9_SECTOR + 8
    subdir_rows = [(base.PACK0_SECTOR, base.PACK0_SIZE, 0x80, "0")]
    if pack9 is not None:
        subdir_rows.append((pack9_sector, len(pack9), 0x80, "9"))
    subdir = dir_node(subdir_rows)
    root = dir_node([(base.UPDATE_SECTOR, base.UPDATE_SIZE, 0x80, "update.xbe"),
                     (base.XBE_SECTOR, len(xbe), 0x80, "default.xbe"),
                     (base.SUBDIR_SECTOR, len(subdir), 0x10, "vc_53450030")])
    header = bytearray(SECTOR)
    header[:20] = xiso.XDVDFS_MAGIC
    struct.pack_into("<II", header, 20, base.ROOT_SECTOR, len(root))
    header[-20:] = xiso.XDVDFS_MAGIC
    with path.open("wb") as stream:
        stream.seek(xiso.XDVDFS_HEADER_OFFSET)
        stream.write(bytes(header))
        stream.seek(base.ROOT_SECTOR * SECTOR)
        stream.write(root)
        stream.seek(base.SUBDIR_SECTOR * SECTOR)
        stream.write(subdir)
        for sector, payload in ((base.UPDATE_SECTOR, base.RETAIL_FILES["update.xbe"]), (base.XBE_SECTOR, xbe),
                                (base.PACK0_SECTOR, base.RETAIL_FILES["vc_53450030/0"])):
            stream.seek(sector * SECTOR)
            stream.write(payload)
        if pack9 is not None:
            stream.seek(pack9_sector * SECTOR)
            stream.write(pack9)
        stream.truncate((base.END_SECTOR + 16) * SECTOR)
    return path


class StudioBuiltIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="studio-built-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.pins = base.fixture_pins()
        self.pins.start()
        self.addCleanup(self.pins.stop)
        grown = mock.patch.object(space, "accepted_file_sizes", return_value=(GROWN_XBE_SIZE,))
        recognised = mock.patch.object(storage, "recognized_grown_xbe", return_value=True)
        for patch in (grown, recognised):
            patch.start()
            self.addCleanup(patch.stop)

    def disc(self, **kwargs) -> Path:
        return build_studio_image(self.tmp / "studio.xiso.iso", **kwargs)

    def test_a_recognised_grown_executable_is_a_disc_built_with_the_studio(self) -> None:
        found = identity.identify(self.disc())
        self.assertEqual(found.kind, identity.KIND_STUDIO_BUILT)
        self.assertEqual(found.headline, identity.STUDIO_BUILT)
        self.assertNotIn("unknown", found.line().lower())
        self.assertIn("default.xbe and 1 other game file", found.line())            # the resized pack 9
        self.assertIn("2K5 Mod Studio wrote its changes", found.line())
        self.assertIn("dump of your own retail disc", found.line())
        # it is still not a starting point for a build or a byte-run patch, and not "retail files"
        self.assertFalse(found.can_build or found.can_take_a_byte_run_patch or found.retail_files or found.is_retail_image)
        self.assertEqual(found.as_json()["kind"], "studio-built")

    def test_the_released_list_names_the_release(self) -> None:
        path = self.disc()
        record = {"name": "SOFTDRINK 2K28 v9.9",
                  "files": {"default.xbe": {"sha256": hashlib.sha256(GROWN_XBE).hexdigest(), "size": GROWN_XBE_SIZE}}}
        with mock.patch("mod_editor.core.nfl2k5_disc_check.load_releases", return_value=[record]):
            found = identity.identify(path)
        self.assertEqual(found.kind, identity.KIND_STUDIO_BUILT)
        self.assertEqual(found.headline, "SOFTDRINK 2K28 v9.9 (a released disc)")
        with mock.patch("mod_editor.core.nfl2k5_disc_check.load_releases", side_effect=OSError("no list in this build")):
            self.assertEqual(identity.identify(path).headline, identity.STUDIO_BUILT)       # unnamed, still described

    def test_only_the_executable_resized_reads_in_the_singular(self) -> None:
        found = identity.identify(self.disc(pack9=base.RETAIL_FILES["vc_53450030/9"]))
        self.assertEqual(found.kind, identity.KIND_STUDIO_BUILT)
        self.assertIn("default.xbe is not the retail size because 2K5 Mod Studio wrote its changes into it", found.line())

    def test_an_executable_nobody_recognises_stays_an_unknown_image(self) -> None:
        with mock.patch.object(storage, "recognized_grown_xbe", return_value=False):
            found = identity.identify(self.disc())
        self.assertEqual(found.kind, identity.KIND_UNKNOWN)
        self.assertEqual(found.headline, identity.UNKNOWN)
        with mock.patch.object(space, "accepted_file_sizes", return_value=()):               # a size the space owner never wrote
            self.assertEqual(identity.identify(self.disc()).kind, identity.KIND_UNKNOWN)

    def test_a_game_file_that_is_gone_is_a_damaged_copy_not_a_studio_disc(self) -> None:
        found = identity.identify(self.disc(pack9=None))
        self.assertEqual(found.kind, identity.KIND_UNKNOWN)
        self.assertIn("vc_53450030/9", found.detail)

    def test_the_retail_answers_are_unchanged(self) -> None:
        retail = base.build_image(self.tmp / "retail.xiso.iso")
        self.assertEqual(identity.identify(retail).kind, identity.KIND_RETAIL_XISO)
        wrong = dict(base.RETAIL_FILES, **{"vc_53450030/9": base.RETAIL_FILES["vc_53450030/9"][:-16]})
        with mock.patch.object(storage, "recognized_grown_xbe", return_value=True):
            # a retail-size executable is never studio-built, whatever else is off
            self.assertNotEqual(identity.identify(base.build_image(self.tmp / "retail2.xiso.iso", files=wrong)).kind,
                                identity.KIND_STUDIO_BUILT)

    def test_the_refusal_notes_name_the_disc(self) -> None:
        from mod_editor.core import mod_build
        path = self.disc()
        error = mod_build._with_identity(ValueError("pack-0 schedule template is foreign"), path, True)
        self.assertIn("This image is: " + identity.STUDIO_BUILT, str(error))
        self.assertNotIn("unknown image", str(error))


class StudioWindowTextTests(unittest.TestCase):
    """The header pill and the Share page say the same thing the Build tab does."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_the_header_pill_says_a_disc_was_built_with_the_studio(self) -> None:
        from types import SimpleNamespace
        from PyQt5.QtWidgets import QLabel
        from mod_editor.gui.studio_qt import StudioMainWindow
        for kind, badge in (("studio-built", "built with the Studio"), ("retail-xiso", "original"), ("unknown", "")):
            window = SimpleNamespace(facade=SimpleNamespace(source_display_name="v0.8.iso"), source_pill=QLabel())
            self.addCleanup(window.source_pill.deleteLater)
            StudioMainWindow._describe_source_pill(window, {"disc_identity": {"kind": kind}, "disc_identity_line": "a line"})
            self.assertEqual(window.source_pill.text(), "\u25cf  Disc: v0.8.iso" + (f" \u00b7 {badge}" if badge else ""), kind)

    def test_the_share_page_does_not_send_a_studio_disc_back_to_the_build_tab(self) -> None:
        from mod_editor.gui.share_panel_qt import SharePanel
        studio = identity.DiscIdentity(kind=identity.KIND_STUDIO_BUILT, headline=identity.STUDIO_BUILT, detail="Read as an xiso.")
        repack = identity.DiscIdentity(kind=identity.KIND_REPACK, headline=identity.REPACK, detail="moved.")
        panel = SharePanel()
        self.addCleanup(panel.deleteLater)
        panel.source_field.setText("disc.iso")
        with mock.patch.object(identity, "identify", return_value=studio):
            text = panel.describe_source()
        self.assertIn(identity.STUDIO_BUILT, text)
        self.assertNotIn("Use the Build tab", text)
        with mock.patch.object(identity, "identify", return_value=repack):
            self.assertIn("Use the Build tab", panel.describe_source())


if __name__ == "__main__":
    unittest.main()
