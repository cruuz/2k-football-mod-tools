"""Job b780 n8: the CPU coaches' club table (b780 c2-staff) goes into the coach AI kernel only after the kernel exists.

Found by n8's real Studio build of the SOFTDRINK pack recipe from the retail disc: "During the automatic CPU coach
profiles: Coach AI table needs the installed kernel". The build writes the coach profiles (PLAY resources) before its
patch space step installs the kernel, and c2's ``write_profiles`` installed the table at that same moment, so every
Experimental build from retail (coach AI is on in that preset and in the pack) stopped there. Now the profile step
defers the table (``defer_table=True``) and ``mod_build._install_coach_table`` writes it right after the patch space step.

Static (the retail USA ``default.xbe``): the old order refuses on an executable without the kernel; the deferred order
writes no executable byte at the profile step and installs the exact rows once the kernel is in; the build calls the
two in that order and labels the second step; the receipt carries the table. The PLAY archive and the disc executable
are stand-ins here (no disc is written); the real build proof is in the job report.
"""
from __future__ import annotations

import inspect
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_coach_ai as ai  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe  # noqa: E402


def swapped_rows():
    rows = ai.default_table()
    kc, lv = rows[9], rows[22]
    rows[9] = dict(lv, book_index=9, asset=kc["asset"])
    rows[22] = dict(kc, book_index=22, asset=lv["asset"])
    rows[21] = ai.vacant_row(21)
    return rows


class _Archive:
    """The PLAY archive stand-in: no profile to write (the table is what this test is about)."""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Prepared(list):
    table = None


class _Disc:
    """The image's executable, in memory (what nfl2k5_coach_ai._image_xbe reads and writes)."""

    def __init__(self, xbe):
        self.xbe, self.writes = xbe, 0

    def __call__(self, image, write=None):
        if write is None:
            return self.xbe
        self.xbe, self.writes = write, self.writes + 1
        return write


class TableOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_cpu_money_downs as money
        retail = retail_xbe()
        # the build's first space pass, then the patch space step's own order: Modern 2, then the coach AI kernel
        cls.reserved = space.apply(retail, money.REQUESTS + money.LATE_REQUESTS + ai.REQUESTS, scaleout=True)[0]
        cls.kernel = ai.apply(money.apply(cls.reserved, level="modern2")[0])[0]

    def write(self, disc, rows, **kwargs):
        from mod_editor.core import nfl2k5_playbook_pack as packs
        prepared = _Prepared()
        prepared.table = rows
        with mock.patch.object(packs._outer_image(), "OuterImage", return_value=_Archive()), \
                mock.patch.object(ai, "_image_xbe", disc):
            return ai.write_profiles("image.xiso.iso", prepared, **kwargs)

    def test_the_old_order_stops_on_an_executable_without_the_kernel(self):
        self.assertEqual(ai.installed_variant(self.reserved), None)
        with self.assertRaisesRegex(ai.CoachAIError, "Coach AI table needs the installed kernel"):
            self.write(_Disc(self.reserved), swapped_rows())

    def test_the_profile_step_defers_the_table_and_writes_no_executable_byte(self):
        disc = _Disc(self.reserved)
        result = self.write(disc, swapped_rows(), defer_table=True)
        self.assertEqual((disc.xbe, disc.writes), (self.reserved, 0))
        self.assertEqual(result["kernel_table"]["status"], "deferred")
        self.assertEqual(result["kernel_table_rows"], swapped_rows())
        with self.assertRaises(ai.CoachAIError):                     # junk rows still refuse at once
            self.write(_Disc(self.reserved), swapped_rows()[:31], defer_table=True)

    def test_the_table_goes_in_once_the_kernel_is_installed(self):
        disc = _Disc(self.kernel)
        with mock.patch.object(ai, "_image_xbe", disc):
            receipt = ai.install_table_to_image("image.xiso.iso", swapped_rows())
            again = ai.install_table_to_image("image.xiso.iso", swapped_rows())
        self.assertEqual((receipt["status"], disc.writes), ("applied", 1))
        self.assertEqual((again["status"], again["changed_bytes"], disc.writes), ("already_applied", 0, 1))
        self.assertEqual(ai.installed_table(disc.xbe), swapped_rows())
        self.assertEqual((ai.status(disc.xbe), space.status(disc.xbe)), ("applied", "applied"))

    def test_without_a_table_nothing_changes(self):
        disc = _Disc(self.reserved)
        result = self.write(disc, None, defer_table=True)
        self.assertNotIn("kernel_table", result)
        self.assertNotIn("kernel_table_rows", result)


class BuildOrderTests(unittest.TestCase):
    """mod_build: the coach profile step defers the table; it is installed after the patch space step."""

    def test_the_build_installs_the_table_after_the_patch_space_step(self):
        from mod_editor.core import mod_build
        source = inspect.getsource(mod_build._build)
        profiles = source.index("tt.coach_ai_patch.apply_profiles_to_image(")
        self.assertIn("defer_table=True", source[profiles:profiles + 300])
        space_step = source.index("patched, space_receipt = tt._apply_all(")
        table = source.index("_install_coach_table(target, coach_table_rows, receipt, progress)")
        verify = source.index('progress("Verifying the composed disc"')
        self.assertLess(profiles, space_step)
        self.assertLess(space_step, table)
        self.assertLess(table, verify)
        self.assertEqual(len(re.findall(r"_install_coach_table\(", source)), 1)

    def test_the_table_step_updates_the_profile_receipt(self):
        from mod_editor.core import mod_build
        receipt = {"steps": [{"step": "coach_ai_resources", "changed_bytes": 10,
                              "kernel_table": {"status": "deferred"}}]}
        fake = {"status": "applied", "changed_bytes": 138}
        with mock.patch.object(mod_build.tt.coach_ai_patch, "install_table_to_image", return_value=fake) as install:
            mod_build._install_coach_table(Path("image.xiso.iso"), swapped_rows(), receipt, lambda *a: None)
        install.assert_called_once_with(Path("image.xiso.iso"), swapped_rows())
        self.assertEqual(receipt["steps"][0]["kernel_table"], fake)
        self.assertEqual(receipt["steps"][0]["changed_bytes"], 148)


if __name__ == "__main__":
    unittest.main()
