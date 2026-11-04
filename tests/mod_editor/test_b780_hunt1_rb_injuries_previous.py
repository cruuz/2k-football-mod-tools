"""b780 hunt1: a beta-79 / SOFTDRINK 2K28 v0.8 simulated RB injury install ("previous") upgraded in place is exactly the
fresh install: on retail the upgraded image equals a fresh install byte for byte; on the released v0.8 default.xbe it
equals that image with the owner's current cave code and current hook bytes written in and the allocator's own seals
recomputed, and nothing else moves (every other owner reads as before).

Written so it holds for any later revision of the owner that keeps the in-place upgrade (b780 db2 re-points the carrier
call): the expected image is built from the owner's own ``code_for`` and ``sites``."""

from __future__ import annotations

import importlib
import os
import struct
import unittest
from pathlib import Path

from tests.nfl2k5_supersim_draft_fixture import retail_bytes

from mod_editor.core import nfl2k5_sim_rb_injuries as inj
from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


def expected_upgrade(payload: bytes) -> bytes:
    """``payload`` with the owner's current code in its cave and its current hook bytes at its sites, then sealed."""
    row = inj.allocation(payload)
    image = XbeImage(payload)
    out = bytearray(payload)
    out[row["raw"]:row["raw"] + inj.CODE_SIZE] = inj.code_for(row["va"])
    for _name, va, _before, after in inj.sites(row["va"]):
        off = image.offset(va, len(after))
        out[off:off + len(after)] = after
    _, _, requests = space._validate(payload)
    space._seal_scaleout(out, requests)
    return bytes(out)


class RetailTests(unittest.TestCase):
    def test_a_beta79_install_upgraded_in_place_equals_a_fresh_install(self):
        data = retail_bytes()
        previous, _ = b779.apply(data)
        fresh, _ = inj.apply(data)
        self.assertEqual(inj.status(previous), "previous")
        upgraded, receipt = inj.apply(previous)
        self.assertEqual((receipt["status"], receipt.get("upgraded_from")), ("applied", "previous"))
        self.assertEqual(upgraded, fresh)
        self.assertEqual(upgraded, expected_upgrade(previous))


class ReleasedV08Tests(unittest.TestCase):
    OTHERS = ("sim_cb_tackles", "sim_realism", "pass_rush_stats", "weekly_progression", "practice_injuries", "star_career",
              "star_retention", "return_coverage", "ball_carrier_ai", "force_out", "qb_accuracy", "run_blocking",
              "pass_protection", "clock_led", "option_defaults")

    @classmethod
    def setUpClass(cls):
        path = Path(os.environ.get("NFL2K5_V08_XBE", "/nonexistent"))
        if not path.is_file():
            raise unittest.SkipTest("the released v0.8 extraction is not in this scratch")
        cls.v08 = path.read_bytes()
        cls.upgraded, cls.receipt = inj.apply(cls.v08)

    def test_v08_reads_previous_and_upgrades_to_applied(self):
        self.assertEqual(inj.status(self.v08), "previous")
        row = inj.allocation(self.v08)
        self.assertEqual(self.v08[row["raw"]:row["raw"] + inj.CODE_SIZE], b779.code_for(row["va"]))
        self.assertEqual((self.receipt["status"], self.receipt.get("upgraded_from")), ("applied", "previous"))
        self.assertEqual(inj.status(self.upgraded), "applied")
        again, second = inj.apply(self.upgraded)
        self.assertEqual((again, second["status"]), (self.upgraded, "already_applied"))

    def test_the_upgrade_is_the_current_owner_written_into_v08_and_sealed(self):
        self.assertEqual(self.upgraded, expected_upgrade(self.v08))
        self.assertEqual(len(self.upgraded), len(self.v08))
        self.assertEqual(space.layout(self.upgraded)["allocations"], space.layout(self.v08)["allocations"])

    def test_nothing_outside_the_owner_and_the_allocator_seals_moves(self):
        row = inj.allocation(self.v08)
        image = XbeImage(self.v08)
        allowed = [(row["raw"], row["raw"] + inj.CODE_SIZE)]
        for _name, va, _before, after in inj.sites(row["va"]):
            off = image.offset(va, len(after))
            allowed.append((off, off + len(after)))
        _, _, requests = space._validate(self.v08)
        allowed += [(a["raw"], a["raw"] + a["size"]) for a in space._scale_allocations(requests)
                    if a["owner"] == space.DIRECTORY_OWNER]
        headers = struct.unpack_from("<I", self.v08, 0x108)[0]
        changed = [i for i in range(len(self.v08)) if self.v08[i] != self.upgraded[i]]
        self.assertTrue(changed)
        stray = [i for i in changed if i >= headers and not any(a <= i < b for a, b in allowed)]
        self.assertEqual(stray, [])

    def test_every_other_owner_reads_as_before(self):
        for name in self.OTHERS:
            module = importlib.import_module(f"mod_editor.core.nfl2k5_{name}")
            with self.subTest(owner=name):
                self.assertEqual(module.status(self.upgraded), module.status(self.v08))


if __name__ == "__main__":
    unittest.main()
