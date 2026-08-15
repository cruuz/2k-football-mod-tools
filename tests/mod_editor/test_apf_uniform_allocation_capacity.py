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
from unittest import mock


WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE / "tools") not in sys.path:
    sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_texture_patch as archive_patch  # noqa: E402
import apf_helmet_color_transport as helmet  # noqa: E402
import apf_pants_color_transport as pants  # noqa: E402
import apf_shoulder_color_transport as shoulder  # noqa: E402

from mod_editor.apf_studio import uniform_targets  # noqa: E402


def _apf_index_0a() -> Path:
    candidates = (
        WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A",
        Path(
            "/media/noah/Storage/for codex 1.0/extracted/"
            "All-Pro Football 2K8 (USA)/0A"
        ),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


INDEX = _apf_index_0a()

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
        jersey_row = {
            "asset_index": 6,
            "outer_table_index": 875,
            "outer_name": "uniform_jersey_06.iff",
        }
        self.assertEqual(
            uniform_targets.target_label("jersey", jersey_row),
            "Jersey slot 6 (outer 875, uniform_jersey_06.iff)",
        )

    def test_a_malformed_row_still_produces_a_usable_label(self) -> None:
        for module in (shoulder, helmet, pants):
            with self.subTest(module=module.__name__):
                self.assertTrue(module.target_label({}).endswith("target"))
        self.assertEqual(uniform_targets.target_label("jersey", {}), "Jersey target")

    def test_jersey_overflow_names_the_slot_not_a_generic_package(self) -> None:
        error = uniform_targets.jersey_allocation_overflow(
            {
                "asset_index": 6,
                "outer_table_index": 875,
                "outer_name": "uniform_jersey_06.iff",
                "outer_allocation": {"size": 32_768},
            },
            overflow_bytes=4_096,
            budget_bytes=30_000,
            retail_bytes=28_000,
        )
        message = str(error)
        self.assertIn("Jersey slot 6", message)
        self.assertIn("outer 875", message)
        self.assertIn("uniform_jersey_06.iff", message)
        self.assertIn("4,096 bytes over", message)
        self.assertIn("32,768-byte fixed allocation", message)
        self.assertNotIn("package full", message.lower())
        self.assertEqual(
            error.target,
            "Jersey slot 6 (outer 875, uniform_jersey_06.iff)",
        )
        self.assertIsInstance(error, archive_patch.AllocationOverflowError)

    def test_the_generic_jersey_writer_overflow_is_rewritten(self) -> None:
        row = {
            "asset_index": 6,
            "outer_table_index": 875,
            "outer_name": "uniform_jersey_06.iff",
            "outer_allocation": {"size": 32_768},
        }
        generic = uniform_targets.apf_uniform_mip_patch.UniformPatchError(
            "rebuilt uniform IFF exceeds its fixed outer allocation by "
            "4096 bytes; refusing output"
        )
        inspected = {
            "compressed_budget_bytes": 30_000,
            "retail_compressed_bytes": 28_000,
        }
        with mock.patch.object(
            uniform_targets, "_inspect_family_capacity", return_value=inspected
        ):
            remapped = uniform_targets._jersey_overflow_from_writer(
                generic, row, Path("0A")
            )
        self.assertIsInstance(remapped, archive_patch.AllocationOverflowError)
        assert remapped is not None
        self.assertEqual(remapped.overflow_bytes, 4_096)
        self.assertEqual(remapped.allocation_size, 32_768)
        self.assertEqual(remapped.budget_bytes, 30_000)
        self.assertIn("Jersey slot 6", str(remapped))
        self.assertIsNone(
            uniform_targets._jersey_overflow_from_writer(
                RuntimeError("PNG is 1x1; target is 1024x1024"),
                row,
                Path("0A"),
            )
        )


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

    def test_jersey_is_a_capacity_family(self) -> None:
        self.assertIn("jersey", uniform_targets.CAPACITY_FAMILIES)
        self.assertIn("shoulder", uniform_targets.CAPACITY_FAMILIES)
        self.assertEqual(
            uniform_targets.JERSEY_CAPACITY_SCHEMA, "apf_jersey_color_capacity/v1"
        )

    def test_jersey_inspection_relabels_the_shared_two_block_model(self) -> None:
        row = {
            "asset_index": 6,
            "outer_table_index": 875,
            "outer_name": "uniform_jersey_06.iff",
        }
        fake = {
            "schema": "apf_shoulder_color_transport/v1",
            "target": "Shoulder slot 6 (outer 875, uniform_jersey_06.iff)",
            "asset_index": 6,
            "outer_table_index": 875,
            "compressed_budget_bytes": 12_000,
        }
        with mock.patch.object(
            uniform_targets.apf_shoulder_color_transport,
            "inspect_capacity",
            return_value=fake,
        ):
            jersey = uniform_targets._inspect_family_capacity(
                "jersey", Path("0A"), row
            )
            shoulder_row = uniform_targets._inspect_family_capacity(
                "shoulder", Path("0A"), row
            )
        self.assertEqual(jersey["schema"], "apf_jersey_color_capacity/v1")
        self.assertEqual(
            jersey["target"],
            "Jersey slot 6 (outer 875, uniform_jersey_06.iff)",
        )
        self.assertEqual(jersey["compressed_budget_bytes"], 12_000)
        self.assertEqual(shoulder_row["schema"], "apf_shoulder_color_transport/v1")
        self.assertTrue(str(shoulder_row["target"]).startswith("Shoulder slot"))

    def test_capacity_bands_split_the_24_slots_into_measured_thirds(self) -> None:
        path = Path("__jersey_band_fixture__")

        def fake_inspect(family: str, index_0a: Path, row: dict[str, object]):
            index = int(row["asset_index"])
            return {
                "schema": uniform_targets.JERSEY_CAPACITY_SCHEMA,
                "target": uniform_targets.target_label("jersey", row),
                "asset_index": index,
                "outer_table_index": index,
                "compressed_budget_bytes": 2_400 - index,
            }

        try:
            with mock.patch.object(
                uniform_targets, "_inspect_family_capacity", side_effect=fake_inspect
            ):
                table = uniform_targets.capacity_table(path, "jersey")
            ranked = sorted(table, key=lambda item: int(item["capacity_rank"]))
            self.assertEqual([str(item["band"]) for item in ranked[:8]], ["detailed"] * 8)
            self.assertEqual(
                [str(item["band"]) for item in ranked[8:16]], ["moderate"] * 8
            )
            self.assertEqual([str(item["band"]) for item in ranked[16:]], ["simple"] * 8)
        finally:
            with uniform_targets._CAPACITY_LOCK:
                uniform_targets._CAPACITY_CACHE.pop((str(path), "jersey"), None)

    def test_compile_rewrites_the_generic_jersey_writer_overflow(self) -> None:
        row = uniform_targets.target_record("jersey", 6)
        generic = uniform_targets.apf_uniform_mip_patch.UniformPatchError(
            "rebuilt uniform IFF exceeds its fixed outer allocation by "
            "4096 bytes; refusing output"
        )
        with mock.patch.object(
            uniform_targets.apf_uniform_mip_patch,
            "build_patch",
            side_effect=generic,
        ):
            with self.assertRaises(archive_patch.AllocationOverflowError) as ctx:
                uniform_targets.compile_uniform_patch(
                    Path("missing-0A"), Path("x.png"), "jersey", 6
                )
        message = str(ctx.exception)
        self.assertIn(f"Jersey slot {int(row['asset_index'])}", message)
        self.assertIn(str(row["outer_name"]), message)
        self.assertIn(f"outer {int(row['outer_table_index'])}", message)
        self.assertNotIn("package full", message.lower())
        self.assertEqual(ctx.exception.overflow_bytes, 4_096)
        allocation = row["outer_allocation"]
        assert isinstance(allocation, dict)
        self.assertEqual(ctx.exception.allocation_size, int(allocation["size"]))

    def test_compile_leaves_non_overflow_jersey_errors_alone(self) -> None:
        err = uniform_targets.apf_uniform_mip_patch.UniformPatchError(
            "PNG is 1x1; target is 1024x1024"
        )
        with mock.patch.object(
            uniform_targets.apf_uniform_mip_patch,
            "build_patch",
            side_effect=err,
        ):
            with self.assertRaises(
                uniform_targets.apf_uniform_mip_patch.UniformPatchError
            ) as ctx:
                uniform_targets.compile_uniform_patch(
                    Path("missing-0A"), Path("x.png"), "jersey", 6
                )
        self.assertIs(ctx.exception, err)

    def test_a_family_without_a_capacity_model_says_so(self) -> None:
        self.assertEqual(uniform_targets.capacity_table(Path("0A"), "pants"), ())
        self.assertIsNone(uniform_targets.slot_capacity(Path("0A"), "helmet", 0))
        self.assertEqual(uniform_targets.capacity_summary(None), "")
        self.assertEqual(
            uniform_targets.team_capacity_line(
                Path("0A"), jersey_index=0, shoulder_index=0
            ),
            "",
        )


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


@unittest.skipUnless(INDEX.is_file(), "private APF source is unavailable")
class RealJerseyCapacityTests(unittest.TestCase):
    """Jersey uses the same two-block budget model; ranks come from the disc."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.table = uniform_targets.capacity_table(INDEX, "jersey")

    def test_every_jersey_slot_is_ranked_exactly_once(self) -> None:
        self.assertEqual(len(self.table), 24)
        self.assertEqual(
            sorted(int(row["asset_index"]) for row in self.table), list(range(24))
        )
        self.assertEqual(
            sorted(int(row["capacity_rank"]) for row in self.table),
            list(range(1, 25)),
        )
        self.assertEqual(
            {str(row["band"]) for row in self.table},
            {"detailed", "moderate", "simple"},
        )
        bands = [str(row["band"]) for row in self.table]
        self.assertEqual(bands.count("detailed"), 8)
        self.assertEqual(bands.count("moderate"), 8)
        self.assertEqual(bands.count("simple"), 8)
        for row in self.table:
            with self.subTest(slot=int(row["asset_index"])):
                catalog = uniform_targets.target_record(
                    "jersey", int(row["asset_index"])
                )
                self.assertEqual(row["schema"], uniform_targets.JERSEY_CAPACITY_SCHEMA)
                self.assertEqual(
                    row["target"],
                    uniform_targets.target_label("jersey", catalog),
                )
                self.assertGreater(int(row["compressed_budget_bytes"]), 0)

    def test_the_summary_is_an_aid_not_a_runtime_claim(self) -> None:
        summary = uniform_targets.capacity_summary(
            uniform_targets.slot_capacity(INDEX, "jersey", 0)
        )
        self.assertIn("Replacement budget", summary)
        self.assertIn("roomiest of 24", summary)
        self.assertIn("region masks", summary)
        self.assertNotIn("look", summary.lower())

    def test_ranks_follow_the_measured_budget_not_a_hardcoded_order(self) -> None:
        ordered = sorted(self.table, key=lambda row: int(row["capacity_rank"]))
        budgets = [int(row["compressed_budget_bytes"]) for row in ordered]
        self.assertEqual(budgets, sorted(budgets, reverse=True))
        self.assertEqual(len({int(row["asset_index"]) for row in ordered}), 24)

    def test_combined_team_line_names_both_family_ranks(self) -> None:
        line = uniform_targets.team_capacity_line(
            INDEX, jersey_index=0, shoulder_index=0
        )
        self.assertRegex(
            line, r"jersey rank \d+/24, shoulder rank \d+/24"
        )
        jersey = uniform_targets.slot_capacity(INDEX, "jersey", 0)
        shoulder = uniform_targets.slot_capacity(INDEX, "shoulder", 0)
        assert jersey is not None and shoulder is not None
        self.assertEqual(
            line,
            (
                f"jersey rank {jersey['capacity_rank']}/24, "
                f"shoulder rank {shoulder['capacity_rank']}/24"
            ),
        )


if __name__ == "__main__":
    unittest.main()
