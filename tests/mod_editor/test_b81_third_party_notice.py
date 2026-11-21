"""b81-retail-free-art (coordinator, 2026-11-20): the Ravens dark alternate mark (data/nfl2k5_kit_rule_fill/
bal_dark_mark_2026.png) is cut from a Wikimedia Commons diagram under CC BY 4.0, so it ships only with its attribution in
NOTICE.md; every picture beside the kit fill rule's SOURCES.json needs its record there."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOLDER = "data/nfl2k5_kit_rule_fill/"
MARK = FOLDER + "bal_dark_mark_2026.png"


class ThirdPartyNoticeTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("release_check", ROOT / "packaging/check_2k5_mod_studio_release.py")
        self.release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.release)
        self.sources = json.loads((ROOT / FOLDER / "SOURCES.json").read_text(encoding="utf-8"))
        self.shipped = {"NOTICE.md", FOLDER + "SOURCES.json"} | {FOLDER + name for name in self.sources["files"]}
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / FOLDER).mkdir(parents=True)
        shutil.copy2(ROOT / "NOTICE.md", self.tmp / "NOTICE.md")
        shutil.copy2(ROOT / FOLDER / "SOURCES.json", self.tmp / FOLDER / "SOURCES.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self):
        self.release._check_third_party_notices(self.tmp, self.shipped)

    def test_the_mark_is_attributed_in_notice_and_the_release_lists_it(self):
        row = self.sources["files"]["bal_dark_mark_2026.png"]
        self.assertIn("CC BY 4.0", row["licence"])
        self.assertIn(MARK, row["notice"])
        notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
        for text in row["notice"] + ["TheGoodGeneral 1", "CC BY 4.0"]:
            self.assertIn(text, notice)
        allowlist = (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").split()
        self.assertIn(MARK, allowlist)
        self.assertIn(FOLDER + "SOURCES.json", allowlist)
        self.assertIn("NOTICE.md", allowlist)
        self.assertIn(FOLDER + "SOURCES.json", self.release.THIRD_PARTY_SOURCES)
        self.check()                                            # as shipped: passes

    def test_the_mark_cannot_ship_without_its_notice_entry(self):
        notice = (self.tmp / "NOTICE.md").read_text(encoding="utf-8")
        lines = [line for line in notice.splitlines(keepends=True) if "TheGoodGeneral 1" not in line]
        (self.tmp / "NOTICE.md").write_text("".join(lines), encoding="utf-8")
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "NOTICE.md attribution: " + MARK):
            self.check()
        self.shipped.discard("NOTICE.md")                       # no NOTICE.md shipped at all
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "NOTICE.md attribution"):
            self.check()

    def test_a_record_without_its_notice_list_or_a_picture_without_a_record_is_refused(self):
        sources = json.loads((self.tmp / FOLDER / "SOURCES.json").read_text(encoding="utf-8"))
        del sources["files"]["bal_dark_mark_2026.png"]["notice"]
        (self.tmp / FOLDER / "SOURCES.json").write_text(json.dumps(sources), encoding="utf-8")
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "NOTICE.md attribution"):
            self.check()
        del sources["files"]["bal_dark_mark_2026.png"]
        (self.tmp / FOLDER / "SOURCES.json").write_text(json.dumps(sources), encoding="utf-8")
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "without its source record: " + MARK):
            self.check()
        self.shipped.discard(FOLDER + "SOURCES.json")
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "without their source record"):
            self.check()


if __name__ == "__main__":
    unittest.main()
