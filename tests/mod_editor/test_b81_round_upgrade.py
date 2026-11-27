"""b81 integration (#45 + #46 round; coordinator ruling (a), 11/27): which executables upgrade in place to the merged
build, through the product's own in-place route (mod_build._team_building_edit_payload: the economy to its current
revision when it reads legacy, then CPU team building with its pace page).

- The released v0.9 and v0.8 executables still upgrade: v0.9 fully (economy and team building), v0.8 its economy
  (its draft AI is older than team building needs, and the route says so).
- The #46-only executable (20ebabf3, the kp76e Studio in-place build of ed2c849e4) upgrades fully.
- An internal beta 81 executable from before #46 (the before arm 8f4bd09c) was never released: #46 rewrote 14
  revision-10 economy windows in place and added 6, so its economy reads foreign and the route refuses it cleanly, with
  the same words a player's own build without the economy gets (they say what to do).
An upgraded executable carries every economy window, every team-building window and the pace page exactly as this
build's templates have them, and a second pass changes nothing.
"""
import hashlib
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_franchise_economy as economy  # noqa: E402
from mod_editor.core import nfl2k5_franchise_economy_code as economy_code  # noqa: E402
from mod_editor.core import nfl2k5_team_building as team_building  # noqa: E402
from mod_editor.core import nfl2k5_team_building_code as team_building_code  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

BEFORE_ARM = "8f4bd09c"
KP46_ONLY = "20ebabf3"


def _fixture(name, prefix=None):
    path = Path(os.environ.get(name, "") or "/nonexistent")
    if not path.is_file():
        raise unittest.SkipTest(f"{name} is not set or absent (b81/env.sh)")
    payload = path.read_bytes()
    if prefix and not hashlib.sha256(payload).hexdigest().startswith(prefix):
        raise unittest.SkipTest(f"{name} is not the {prefix} executable")
    return payload


def _template_mismatches(payload):
    image = XbeImage(payload)
    out = []
    for label, windows in (("economy", economy_code.WINDOWS), ("team building", team_building_code.WINDOWS)):
        for va, window in windows.items():
            blob = bytes(window[0] if isinstance(window, tuple) else window)
            if image.read(va, len(blob)) != blob:
                out.append(f"{label} {va:#x}")
    if image.read(team_building_code.PAGE_VA, len(team_building_code.PAGE)) != team_building_code.PAGE:
        out.append("pace page")
    return out


class UpgradesInPlace(unittest.TestCase):
    def assert_full_upgrade(self, source):
        upgraded, economy_receipt, _receipt = mod_build._team_building_edit_payload(source)
        self.assertEqual((economy.status(upgraded), team_building.status(upgraded), draft.status(upgraded)),
                         ("applied", "applied", "applied"))
        self.assertEqual(_template_mismatches(upgraded), [])
        self.assertEqual(mod_build._team_building_edit_payload(upgraded)[0], upgraded)      # a second pass is a no-op
        return economy_receipt

    def test_the_46_only_executable_upgrades_fully(self):
        source = _fixture("NFL2K5_B81_KP46_ONLY_XBE", KP46_ONLY)
        self.assertEqual((economy.status(source), team_building.status(source)), ("legacy", "previous"))
        self.assertIsNotNone(self.assert_full_upgrade(source))

    def test_the_released_v09_executable_upgrades_fully(self):
        source = _fixture("NFL2K5_V09_RELEASED_XBE")
        self.assertEqual((economy.status(source), team_building.status(source)), ("legacy", "retail"))
        self.assertIsNotNone(self.assert_full_upgrade(source))

    def test_the_v08_executable_upgrades_its_economy_and_team_building_says_what_to_do(self):
        source = _fixture("NFL2K5_V08_XBE")
        self.assertEqual(economy.status(source), "legacy")
        upgraded, _ = economy.apply(source)
        self.assertEqual(economy.status(upgraded), "applied")
        image = XbeImage(upgraded)
        for va, window in economy_code.WINDOWS.items():
            blob = bytes(window[0] if isinstance(window, tuple) else window)
            self.assertEqual(image.read(va, len(blob)), blob, hex(va))
        with self.assertRaises(ValueError) as caught:
            mod_build._team_building_edit_payload(source)
        self.assertIn("Build a new disc with CPU team building on", str(caught.exception))


class RefusedCleanly(unittest.TestCase):
    def test_an_internal_pre_46_build_is_refused_with_words_that_say_what_to_do(self):
        source = _fixture("NFL2K5_B81_KP_IMAGE_XBE", BEFORE_ARM)
        self.assertEqual(economy.status(source), "foreign")
        with self.assertRaises(ValueError) as caught:
            mod_build._team_building_edit_payload(source)
        self.assertEqual(str(caught.exception), mod_build.TEAM_BUILDING_NEEDS_ECONOMY)
        self.assertIn("Build a new disc", mod_build.TEAM_BUILDING_NEEDS_ECONOMY)


if __name__ == "__main__":
    unittest.main()
