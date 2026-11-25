"""The pregame welcome skips stadiums whose recorded name the build replaced (b81 sb-booth, audit finding 1). No emulator.

Retail-free tests use a synthetic ``lines`` speech index holding the retail stadium list of key 14039 and a synthetic
disc image. Retail tests (skipped without the user-owned USA disc folder) check that the retail list is the pinned one,
that it belongs to key 14039 alone, that its values select the transcribed stadium welcomes, and that the retail
roster renames nothing (so a retail build keeps every welcome).
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import build_steps  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_stadium_welcome as w  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", ROOT / "extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"
HAVE_RETAIL = (RETAIL / "0").is_file()
RENAMED = {n: f"Renamed {n}" for n in w.STALE}                # every stale row shows another name


def synthetic_body() -> bytes:
    body = bytearray(w.SPCI_STORED)
    body[0x0C:0x10] = b"SPCI"
    name = w.SPCI_NAME.encode("utf-16-le")
    body[0x20:0x20 + len(name)] = name
    struct.pack_into(f"<H{w.LIST_COUNT}H", body, w.LIST_OFFSET, w.LIST_COUNT, *w.RETAIL_VALUES)
    return bytes(body)


def outer3(body: bytes, *, lead: int = 0x40) -> bytes:
    wrapper = b"SPCI" + struct.pack("<I", w.SPCI_STORED) + bytes(0x18)
    return bytes(lead) + wrapper + body + bytes(0x10)


class ListLogic(unittest.TestCase):
    def test_retail_values_and_stale_numbers(self):
        self.assertEqual(len(w.RETAIL_VALUES), w.LIST_COUNT)
        self.assertEqual(len(set(w.RETAIL_VALUES)), w.LIST_COUNT)
        self.assertEqual(sorted(w.STALE), [1, 3, 6, 7, 8, 11, 12, 14, 15, 17, 18, 19, 20, 22, 23, 24, 25, 28])
        self.assertTrue(set(w.STALE) <= set(w.RETAIL_VALUES))
        self.assertNotIn(w.SKIP, w.RETAIL_VALUES)

    def test_only_renamed_rows_are_skipped(self):
        self.assertEqual(w.stale_rows({n: retail for n, (_s, retail) in w.STALE.items()}), [])
        self.assertEqual(w.stale_rows(RENAMED), sorted(w.STALE))
        self.assertEqual(w.stale_rows({20: "Allegiant Stadium", 10: "Lambeau Field", 3: "Ralph Wilson Stadium"}), [20])

    def test_patch_and_states(self):
        body = synthetic_body()
        self.assertEqual(w.list_state(body), ("retail", []))
        once, receipt = w.patch_body(body, [20, 23])
        self.assertEqual(w.list_state(once), ("applied", [20, 23]))
        self.assertEqual(receipt["changed_bytes"], 4)
        twice, receipt = w.patch_body(once, sorted(w.STALE))                # a later build skips more
        self.assertEqual(w.list_state(twice), ("applied", sorted(w.STALE)))
        self.assertEqual(receipt["newly_skipped"], sorted(set(w.STALE) - {20, 23}))
        again, receipt = w.patch_body(twice, sorted(w.STALE))               # idempotent
        self.assertEqual((again, receipt["changed_bytes"]), (twice, 0))
        values = w.list_values(twice)
        for n, v in zip(w.RETAIL_VALUES, values):
            self.assertEqual(v, w.SKIP if n in w.STALE else n)

    def test_refusals(self):
        body = bytearray(synthetic_body())
        struct.pack_into("<H", body, w.LIST_OFFSET + 2 + 2 * w.RETAIL_VALUES.index(10), w.SKIP)   # a kept stadium
        self.assertEqual(w.list_state(bytes(body))[0], "foreign")
        with self.assertRaises(w.StadiumWelcomeError):
            w.patch_body(bytes(body), [20])
        with self.assertRaises(w.StadiumWelcomeError):
            w.patch_body(synthetic_body(), [10])                                 # not a stale stadium

    def test_found_by_content(self):
        raw = outer3(synthetic_body(), lead=0x1230)
        self.assertEqual(w.find_spci(raw), 0x1230)
        with self.assertRaises(w.StadiumWelcomeError):
            w.find_spci(raw + raw)


class Image(unittest.TestCase):
    def test_round_trip_on_a_synthetic_disc(self):
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as tmp:
            entries = [(0, b"\x00" * 16), (1, b"\x01" * 16), (2, b"\x02" * 16), (3, outer3(synthetic_body())),
                       (4, b"\x04" * 16)]
            image = SyntheticXiso(Path(tmp), entries, pack_sizes=(0x20000,), pack_sectors=(64,))
            before = image.path.read_bytes()
            with mock.patch.object(w, "_stadium_names", return_value={20: "Allegiant Stadium", 10: "Lambeau Field"}):
                receipt = w.apply_to_image(image.path)
                self.assertEqual((receipt["state"], receipt["skipped_stadiums"], receipt["changed_bytes"]),
                                 ("applied", [20], 2))
                after = image.path.read_bytes()
                self.assertEqual(sum(1 for x, y in zip(before, after) if x != y), 2)
                self.assertEqual(w.apply_to_image(image.path)["changed_bytes"], 0)
                self.assertEqual(image.path.read_bytes(), after)
            with mock.patch.object(w, "_stadium_names", return_value={n: r for n, (_s, r) in w.STALE.items()}):
                self.assertEqual(w.apply_to_image(image.path)["state"], "not_needed")   # retail names: nothing to do
            self.assertEqual(image.path.read_bytes(), after)

    def test_a_disc_without_readable_stadium_rows_is_left_alone(self):
        """Build never fails over a disc it does not recognise: no roster, or no renamed row, writes nothing."""
        from nfl2k5_xiso_fixture import SyntheticXiso
        with tempfile.TemporaryDirectory() as tmp:
            entries = [(i, bytes([i]) * 16) for i in range(6)]
            image = SyntheticXiso(Path(tmp), entries, pack_sizes=(0x8000,), pack_sectors=(64,))
            before = image.path.read_bytes()
            receipt = w.apply_to_image(image.path)
            self.assertEqual((receipt["state"], receipt["changed_bytes"]), ("skipped", 0))
            self.assertEqual(image.path.read_bytes(), before)


class BuildWiring(unittest.TestCase):
    def test_step_runs_on_every_disc_build_after_the_booth_lines(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        lines = source.splitlines()
        call = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "stadium_welcome")' in line]
        booth = [i for i, line in enumerate(lines) if '_optional(receipt, target, progress, "super_bowl_booth")' in line]
        self.assertEqual((len(call), len(booth)), (1, 1))
        self.assertLess(booth[0], call[0])
        gate = max(i for i in range(call[0]) if re.match(r"    if \S", lines[i]))
        self.assertEqual(lines[gate].strip(), "if tt.is_disc_image(target):")
        self.assertIn("stadium_welcome", mod_build.OPTIONAL_STEPS)
        self.assertIn("stadium_welcome", build_steps.STEP_LABELS)
        self.assertTrue(build_steps.KEPT["stadium_welcome"].startswith("Your "))


@unittest.skipUnless(HAVE_RETAIL, "needs the user-owned USA disc folder")
class Retail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage
        with OuterImage(RETAIL) as archive:
            raw = archive.read_entry(w.SPCI_OUTER_INDEX)
        at = w.find_spci(raw)
        cls.body = raw[at + 0x20:at + 0x20 + w.SPCI_STORED]

    def test_retail_list_is_pinned_and_belongs_to_14039_alone(self):
        self.assertEqual(w.list_state(self.body), ("retail", []))
        third = 0x38 + struct.unpack_from("<I", self.body, 0x38)[0] - 1
        lists = 0x3C + struct.unpack_from("<I", self.body, 0x3C)[0] - 1
        users = []
        for row in range(self.body[0x42]):
            at = third + 16 * row
            mask, count, variants = struct.unpack_from("<HHB", self.body, at + 8)
            keys_at = at + struct.unpack_from("<I", self.body, at)[0] - 1
            index_at = at + 4 + struct.unpack_from("<I", self.body, at + 4)[0] - 1
            keys = struct.unpack_from(f"<{count}H", self.body, keys_at)
            for p, key in enumerate(keys):
                for v in range(variants):
                    index = struct.unpack_from("<H", self.body, index_at + 2 * (variants * p + v))[0]
                    if lists + 2 * index == w.LIST_OFFSET:
                        users.append(key)
        self.assertEqual(users, [w.KEY])

    def test_the_retail_roster_renames_nothing(self):
        self.assertEqual(w.stale_rows(w._stadium_names(RETAIL)), [])


if __name__ == "__main__":
    unittest.main()
