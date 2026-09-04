"""The Rosters page shows a read-only franchise summary for a franchise save and nothing for the rest."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_franchise_save import synthetic_franchise  # noqa: E402
from test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0  # noqa: E402


def write_container(root: Path, savegame: bytes) -> Path:
    folder = root / "53450030" / "0001"
    folder.mkdir(parents=True)
    (folder / "SAVEGAME.DAT").write_bytes(savegame)
    (folder / "EXTRA").write_bytes(rr.sign_save(savegame))
    (folder / "SaveMeta.xbx").write_bytes(b"\xff\xfe" + "Name=Franchise1\r\n".encode("utf-16-le"))
    return root


class FranchiseCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()

    def test_franchise_save_fills_the_card_and_a_roster_save_hides_it(self) -> None:
        self.assertFalse(self.panel.franchise_label.isVisibleTo(self.panel))
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "franchise", synthetic_franchise(year_field=7, user_team=0))
            self.assertTrue(self.panel.load_save(source))
            self.application.processEvents()
            summary = self.panel.franchise_summary
            assert summary is not None
            self.assertEqual((summary["display_year"], summary["stage_name"], summary["user_teams"]), (2011, "regular season", [0]))
            text = self.panel.franchise_label.text()
            self.assertTrue(self.panel.franchise_label.isVisibleTo(self.panel))
            for piece in ("Franchise save", "2011", "regular season", "week 3/17", "$80.5M", "1/2 grid games", "injured reserve: none"):
                self.assertIn(piece, text)
            self.assertEqual(self.panel.source_label.text(), "franchise (signature verified)")
            # the same page with a plain roster-arena save: no card
            plain = write_container(Path(td) / "roster", synthetic_save_v0(synthetic_body()))
            self.assertTrue(self.panel.load_save(plain))
            self.application.processEvents()
            self.assertIsNone(self.panel.franchise_summary)
            self.assertFalse(self.panel.franchise_label.isVisibleTo(self.panel))
            self.assertEqual(self.panel.franchise_label.text(), "")
        # and a bare body hides it too
        self.panel.load_document(rr.load_body(synthetic_body()), label="synthetic")
        self.assertFalse(self.panel.franchise_label.isVisibleTo(self.panel))

    def test_write_copy_keeps_the_franchise_blocks(self) -> None:
        payload = synthetic_franchise(year_field=9, user_team=1)
        with tempfile.TemporaryDirectory() as td:
            source = write_container(Path(td) / "franchise", payload)
            self.assertTrue(self.panel.load_save(source))
            assert self.panel.document is not None
            self.panel.document.players[0].record.set("speed", 77)
            receipt = self.panel.write_copy_to(Path(td) / "copy")
            self.assertTrue(receipt["signed"])
            written = (Path(td) / "copy" / "53450030" / "0001" / "SAVEGAME.DAT").read_bytes()
            self.assertEqual(len(written), len(payload))
            self.assertEqual(written[0x91320:], payload[0x91320:])          # season + front office untouched
            self.assertTrue(self.panel.load_save(Path(td) / "copy"))
            assert self.panel.franchise_summary is not None
            self.assertEqual(self.panel.franchise_summary["display_year"], 2013)


if __name__ == "__main__":
    unittest.main()
