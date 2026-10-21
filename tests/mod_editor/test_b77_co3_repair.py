"""b77 co3: the native repair writes exactly the two portrait spans, from the module's own compile.

The always-on tests read only the repository. The disc checks read (never write) the untouched v0.6.1 disc and skip
without it (point NFL2K5_CO3_BASE at it).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_modern_coaches as mc  # noqa: E402

SPEC = importlib.util.spec_from_file_location("co3_repair", ROOT / "tools/b77/co3_repair.py")
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)
BASE = Path(os.environ.get("NFL2K5_CO3_BASE", str(ROOT / "SOFTDRINK 2K28 v0.6.1.xiso.iso")))


class Contract(unittest.TestCase):
    def test_it_refuses_an_unknown_original_before_touching_the_image(self):
        with tempfile.TemporaryDirectory(prefix="co3-repair-") as raw:
            folder = Path(raw)
            original, image = folder / "original.iso", folder / "image.iso"
            original.write_bytes(b"\0" * 4096)
            image.write_bytes(b"\1" * 4096)
            with self.assertRaisesRegex(SystemExit, "REFUSED: --original is"):
                repair.main(["--image", str(image), "--original", str(original), "--retail", str(original),
                             "--receipts", str(folder / "r")])
            self.assertEqual(image.read_bytes(), b"\1" * 4096)
            with self.assertRaisesRegex(SystemExit, "must be a copy"):
                repair.main(["--image", str(original), "--original", str(original), "--retail", str(original),
                             "--receipts", str(folder / "r")])

    def test_the_pinned_input_is_the_v061_shortcut_disc(self):
        self.assertEqual(repair.INPUT_SHA256, "520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4")
        self.assertEqual(repair.INPUT_SIZE, 6_004_408_320)


@unittest.skipUnless(BASE.is_file(), "the v0.6.1 disc is not present (NFL2K5_CO3_BASE)")
class OnTheV061Disc(unittest.TestCase):
    def test_the_co3_picture_repair_is_superseded_by_pr2_and_cm1(self):
        """b773 i4: co3 planned the two authored Coach Matchup pictures onto the v0.6.1 disc. pr2 moved those pictures
        to the SOFTDRINK league project (the module keeps the slots and writes nothing), and cm1 changed the coach
        scenes themselves, so the v0.6.1 scenes now read as an earlier version that needs the retail source."""
        before = BASE.stat()
        states = mc.resource_states(BASE)
        self.assertEqual({k: v for k, v in states.items() if k.startswith("portrait:")},
                         {"portrait:DAL": "kept", "portrait:WAS": "kept"})
        self.assertIn("previous", {v for k, v in states.items() if not k.startswith("portrait:")})
        with self.assertRaisesRegex(mc.ModernCoachesError, "rebuild from a supported USA source"):
            mc.plan_image(BASE)
        after = BASE.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns), (after.st_size, after.st_mtime_ns))


if __name__ == "__main__":
    unittest.main()
