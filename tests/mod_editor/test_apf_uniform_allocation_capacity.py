"""A refused uniform replacement has to say which target refused it.

davidhbui staged several shoulder replacements against Beta 38 and got, after
about forty seconds per target::

    rebuilt shoulder IFF exceeds fixed allocation by 9231 bytes

Nothing in that names a team, slot, outer entry, or source PNG, so fixing one
file and rebuilding produced ``9292 -> 9231`` -- an apparent 61-byte improvement
that was actually a *different* slot failing.  He also measured why the refusal
is not about free space: a slot's budget is retail's own compressed payload plus
a small sector slack, and the payload dominates, so the slot with the most
visible slack (outer 182, 2,590 bytes) is one of the least able to accept a
detailed mask while outer 184 and 198 take the same PNG.

These tests hold both ends: the message names its target and its budget, and the
capacity model ranks those three slots the way the disc actually behaved.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE / "tools") not in sys.path:
    sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_texture_patch as archive_patch  # noqa: E402
import apf_helmet_color_transport as helmet  # noqa: E402
import apf_pants_color_transport as pants  # noqa: E402
import apf_shoulder_color_transport as shoulder  # noqa: E402

from mod_editor.apf_studio import uniform_targets  # noqa: E402


INDEX = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"

# The three slots davidhbui built the same detailed mask against.
FAILED_SLOT = 4      # outer 182 -- 12,373 bytes over, and the most sector slack
FIT_SLOTS = (11, 5)  # outer 184 and 198 -- same PNG, both fit


class OverflowMessageTests(unittest.TestCase):
    def test_the_message_names_the_target_and_its_budget(self) -> None:
        error = archive_patch.allocation_overflow(
            target="Shoulder slot 9 (outer 1373, uniform_shoulder_09.iff)",
            overflow_bytes=9231,
            allocation_size=772_096,
            budget_bytes=773_201,
            retail_bytes=772_885,
        )
        message = str(error)
        self.assertIn("Shoulder slot 9", message)
        self.assertIn("outer 1373", message)
        self.assertIn("9,231 bytes over", message)
        self.assertIn("772,096-byte fixed allocation", message)
        self.assertIn("773,201", message)
        self.assertIn("anti-aliasing", message)

    def test_it_is_a_patch_error_that_carries_its_numbers(self) -> None:
        error = archive_patch.allocation_overflow(
            target="Pants slot 3 (outer 1052)",
            overflow_bytes=64,
            allocation_size=1_024,
        )
        self.assertIsInstance(error, archive_patch.PatchError)
        self.assertIsInstance(error, archive_patch.AllocationOverflowError)
        self.assertEqual(error.target, "Pants slot 3 (outer 1052)")
        self.assertEqual(error.overflow_bytes, 64)
        self.assertEqual(error.allocation_size, 1_024)
        self.assertIsNone(error.budget_bytes)

    def test_every_mask_transport_labels_its_own_family(self) -> None:
        row = {
            "asset_index": 4,
            "outer_table_index": 182,
            "outer_name": "uniform_shoulder_04.iff",
        }
        self.assertEqual(
            shoulder.target_label(row),
            "Shoulder slot 4 (outer 182, uniform_shoulder_04.iff)",
        )
        self.assertTrue(helmet.target_label(row).startswith("Helmet slot 4 "))
        self.assertTrue(pants.target_label(row).startswith("Pants slot 4 "))

    def test_a_malformed_row_still_produces_a_usable_label(self) -> None:
        for module in (shoulder, helmet, pants):
            with self.subTest(module=module.__name__):
                self.assertTrue(module.target_label({}).endswith("target"))


class CapacityModelTests(unittest.TestCase):
    def test_a_budget_is_the_allocation_minus_everything_that_cannot_move(self) -> None:
        class _Entry:
            size = 1_000

        class _Footer:
            payload_size = 12

        class _Record:
            header_size = 100
            footer = _Footer()

        capacity = shoulder.slot_capacity(
            _Entry(), _Record(), [b"\0" * 200, b"\0" * 600]
        )
        self.assertEqual(capacity["fixed_overhead_bytes"], 100 + 200 + 20)
        self.assertEqual(capacity["compressed_budget_bytes"], 1_000 - 320)
        self.assertEqual(capacity["retail_compressed_bytes"], 600)
        self.assertEqual(capacity["headroom_bytes"], 80)

    def test_a_family_without_a_capacity_model_says_so(self) -> None:
        self.assertEqual(uniform_targets.capacity_table(Path("0A"), "jersey"), ())
        self.assertIsNone(uniform_targets.slot_capacity(Path("0A"), "jersey", 0))
        self.assertEqual(uniform_targets.capacity_summary(None), "")


@unittest.skipUnless(INDEX.is_file(), "private APF source is unavailable")
class RealShoulderCapacityTests(unittest.TestCase):
    """The ranking has to agree with what the disc did, not with intuition."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.table = uniform_targets.capacity_table(INDEX, "shoulder")

    def test_every_shoulder_slot_is_ranked_exactly_once(self) -> None:
        self.assertEqual(len(self.table), 24)
        self.assertEqual(
            sorted(int(row["asset_index"]) for row in self.table), list(range(24))
        )
        self.assertEqual(
            sorted(int(row["capacity_rank"]) for row in self.table),
            list(range(1, 25)),
        )
        self.assertEqual({str(row["band"]) for row in self.table},
                         {"detailed", "moderate", "simple"})

    def test_the_slot_that_refused_the_mask_ranks_below_the_two_that_took_it(
        self,
    ) -> None:
        ranked = {int(row["asset_index"]): row for row in self.table}
        failed = ranked[FAILED_SLOT]
        self.assertEqual(int(failed["outer_table_index"]), 182)
        for slot in FIT_SLOTS:
            with self.subTest(slot=slot):
                self.assertGreater(
                    int(ranked[slot]["compressed_budget_bytes"]),
                    int(failed["compressed_budget_bytes"]),
                )
                self.assertLess(
                    int(ranked[slot]["capacity_rank"]),
                    int(failed["capacity_rank"]),
                )

    def test_sector_slack_alone_would_have_ranked_them_backwards(self) -> None:
        """The metric the report called misleading must not be the one shown."""

        ranked = {int(row["asset_index"]): row for row in self.table}
        slack = {
            slot: int(row["allocation_size"])
            - int(row["fixed_overhead_bytes"])
            - int(row["retail_compressed_bytes"])
            for slot, row in ranked.items()
        }
        # Outer 182 has more free space than either slot that accepted the
        # same PNG, which is exactly the trap a slack-based picker sets.
        for slot in FIT_SLOTS:
            self.assertGreater(slack[FAILED_SLOT], slack[slot])

    def test_the_summary_tells_a_user_which_way_to_go(self) -> None:
        summary = uniform_targets.capacity_summary(
            uniform_targets.slot_capacity(INDEX, "shoulder", FAILED_SLOT)
        )
        self.assertIn("Replacement budget", summary)
        self.assertIn("roomiest of 24", summary)
        self.assertIn("anti-aliasing", summary)


if __name__ == "__main__":
    unittest.main()
