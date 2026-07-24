"""Retail-free contract tests for the APF 32x53 planning workspace."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.apf_studio.roster_workspace import (
    MASTER_ROSTER_SLOTS,
    PROJECT_RESERVE_SLOTS,
    ReserveRosterPlan,
    RosterWorkspaceError,
    STOCK_ACTIVE_SLOTS,
    TEAM_COUNT,
    bind_membership_rows,
    bind_reserve_plan,
    decode_reserve_plan,
    encode_reserve_plan,
    load_reserve_plan,
    save_reserve_plan,
    stock_active_from_memberships,
)


def _active_mapping() -> dict[int, tuple[int, ...]]:
    return {
        team: tuple(
            team * STOCK_ACTIVE_SLOTS + slot
            for slot in range(STOCK_ACTIVE_SLOTS)
        )
        for team in range(TEAM_COUNT)
    }


def _membership_rows() -> list[dict[str, int]]:
    return [
        {
            "team_index": team,
            "roster_slot": slot,
            "player_index": team * STOCK_ACTIVE_SLOTS + slot,
        }
        for team in range(TEAM_COUNT)
        for slot in range(STOCK_ACTIVE_SLOTS)
    ]


def _complete_plan() -> ReserveRosterPlan:
    plan = ReserveRosterPlan.empty()
    player = TEAM_COUNT * STOCK_ACTIVE_SLOTS
    for team in range(TEAM_COUNT):
        for reserve_slot in range(PROJECT_RESERVE_SLOTS):
            plan = plan.assign(team, reserve_slot, player)
            player += 1
    return plan


class ReservePlanContractTests(unittest.TestCase):
    def test_empty_plan_is_exact_canonical_and_contains_no_source_memberships(self) -> None:
        plan = ReserveRosterPlan.empty()
        self.assertEqual(len(plan.teams), 32)
        self.assertEqual(plan.assigned_count, 0)
        self.assertEqual(plan.open_slot_count, 352)
        payload = encode_reserve_plan(plan)
        self.assertEqual(decode_reserve_plan(payload), plan)
        document = json.loads(payload)
        self.assertEqual(
            set(document),
            {"distribution", "game", "schema", "scope", "team_count", "teams"},
        )
        self.assertEqual(
            document["distribution"],
            {
                "contains_executable_patch": False,
                "contains_retail_bytes": False,
                "contains_source_active_memberships": False,
                "payload": "user-authored reserve player indices only",
            },
        )
        self.assertNotIn("active_player_indices", payload.decode())
        self.assertNotIn("source_value", payload.decode())
        self.assertNotIn("preimage", payload.decode())
        self.assertNotIn("record_bytes", payload.decode())

    def test_assign_is_immutable_bounded_and_globally_unique(self) -> None:
        empty = ReserveRosterPlan.empty()
        first = empty.assign(0, 0, 2_253)
        self.assertIsNone(empty.team(0).reserve_player_indices[0])
        self.assertEqual(first.team(0).reserve_player_indices[0], 2_253)
        self.assertEqual(first.assign(0, 0, None), empty)
        for args, message in (
            ((-1, 0, 1), "Team index"),
            ((32, 0, 1), "Team index"),
            ((0, -1, 1), "reserve slot"),
            ((0, 11, 1), "reserve slot"),
            ((0, 0, -1), "player index"),
            ((0, 0, 2_254), "player index"),
            ((0, 0, True), "player index"),
        ):
            with self.subTest(args=args):
                with self.assertRaisesRegex(RosterWorkspaceError, message):
                    empty.assign(*args)  # type: ignore[arg-type]
        with self.assertRaisesRegex(RosterWorkspaceError, "two different teams"):
            first.assign(1, 0, 2_253)

    def test_noncanonical_extra_fields_and_false_distribution_are_refused(self) -> None:
        payload = encode_reserve_plan(ReserveRosterPlan.empty())
        document = json.loads(payload)
        malformed: list[dict[str, object]] = []
        extra = json.loads(json.dumps(document))
        extra["source_memberships"] = []
        malformed.append(extra)
        false_boundary = json.loads(json.dumps(document))
        false_boundary["distribution"]["contains_retail_bytes"] = True
        malformed.append(false_boundary)
        short = json.loads(json.dumps(document))
        short["teams"][0]["reserve_player_indices"].pop()
        malformed.append(short)
        boolean = json.loads(json.dumps(document))
        boolean["teams"][0]["reserve_player_indices"][0] = True
        malformed.append(boolean)
        reordered = json.loads(json.dumps(document))
        reordered["teams"][0], reordered["teams"][1] = (
            reordered["teams"][1],
            reordered["teams"][0],
        )
        malformed.append(reordered)
        for row in malformed:
            with self.subTest(keys=set(row)):
                data = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
                with self.assertRaises(RosterWorkspaceError):
                    decode_reserve_plan(data)

    def test_complete_352_assignment_plan_stays_small_and_roundtrips(self) -> None:
        plan = _complete_plan()
        payload = encode_reserve_plan(plan)
        self.assertEqual(plan.assigned_count, 352)
        self.assertEqual(plan.completed_team_count, 32)
        self.assertLess(len(payload), 8 * 1024)
        self.assertEqual(decode_reserve_plan(payload), plan)
        document = json.loads(payload)
        self.assertEqual(
            sum(
                value is not None
                for team in document["teams"]
                for value in team["reserve_player_indices"]
            ),
            352,
        )

    def test_save_load_is_atomic_private_and_never_overwrites(self) -> None:
        plan = ReserveRosterPlan.empty().assign(0, 0, 1_344)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "league.apf2k8roster"
            self.assertEqual(save_reserve_plan(plan, destination), destination)
            self.assertEqual(load_reserve_plan(destination), plan)
            # "Private" means the mode bits on POSIX -- 0o600, unchanged -- and
            # the per-user profile root's inherited ACL on Windows, where the
            # same file honestly reports 0o666 because that OS implements no
            # group/other bits to remove.  Assert each platform's real contract
            # instead of one number that would be a lie on the other.
            expected_mode = 0o666 if platform_compat.IS_WINDOWS else 0o600
            self.assertEqual(platform_compat.private_file_mode(), expected_mode)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), expected_mode)
            before = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                save_reserve_plan(ReserveRosterPlan.empty(), destination)
            self.assertEqual(destination.read_bytes(), before)
            with self.assertRaisesRegex(RosterWorkspaceError, ".apf2k8roster"):
                save_reserve_plan(plan, root / "wrong.json")
            link = root / "linked.apf2k8roster"
            link.symlink_to(destination)
            with self.assertRaisesRegex(RosterWorkspaceError, "regular file"):
                load_reserve_plan(link)


class BoundWorkspaceTests(unittest.TestCase):
    def test_complete_32_by_53_view_keeps_only_42_runtime_visible(self) -> None:
        plan = _complete_plan()
        workspace = bind_reserve_plan(plan, _active_mapping())
        self.assertEqual(len(workspace.teams), 32)
        self.assertEqual(workspace.summary.source_active_player_count, 1_344)
        self.assertEqual(workspace.summary.assigned_project_reserve_count, 352)
        self.assertEqual(workspace.summary.open_project_reserve_count, 0)
        self.assertEqual(workspace.summary.complete_master_team_count, 32)
        self.assertEqual(workspace.summary.runtime_visible_player_count, 1_344)
        self.assertEqual(workspace.summary.runtime_visible_reserve_count, 0)
        for team in workspace.teams:
            self.assertEqual(len(team.slots), MASTER_ROSTER_SLOTS)
            self.assertTrue(all(slot.runtime_visible for slot in team.slots[:42]))
            self.assertTrue(all(not slot.runtime_visible for slot in team.slots[42:]))
            self.assertTrue(
                all(
                    slot.status == "project_only_not_written_to_game"
                    for slot in team.slots[42:]
                )
            )
            self.assertTrue(team.master_complete)
        self.assertEqual(workspace.teams[23].selection_status, "stock_offline_team")
        self.assertEqual(
            workspace.teams[24].selection_status,
            "populated_online_placeholder_offline_selector_unproved",
        )
        self.assertEqual(
            workspace.teams[31].selection_status,
            "populated_online_placeholder_offline_selector_unproved",
        )

    def test_source_membership_rows_bind_but_never_enter_serialized_plan(self) -> None:
        rows = _membership_rows()
        active = stock_active_from_memberships(rows)
        self.assertEqual(active, _active_mapping())
        plan = ReserveRosterPlan.empty().assign(0, 0, 1_344)
        workspace = bind_membership_rows(plan, rows)
        self.assertEqual(workspace.teams[0].slots[42].player_index, 1_344)
        document = json.loads(encode_reserve_plan(workspace.plan))
        self.assertNotIn("memberships", document)
        self.assertNotIn("active", document)

    def test_reserve_collision_with_stock_active_is_refused(self) -> None:
        plan = ReserveRosterPlan.empty().assign(0, 0, 41)
        with self.assertRaisesRegex(
            RosterWorkspaceError, "already one of the 1,344 source-active"
        ):
            bind_reserve_plan(plan, _active_mapping())

    def test_incomplete_duplicate_and_out_of_range_source_views_are_refused(self) -> None:
        rows = _membership_rows()
        with self.assertRaisesRegex(RosterWorkspaceError, "expected exactly 1344"):
            stock_active_from_memberships(rows[:-1])
        duplicate_slot = list(rows)
        duplicate_slot[-1] = dict(duplicate_slot[0])
        with self.assertRaisesRegex(RosterWorkspaceError, "duplicated"):
            stock_active_from_memberships(duplicate_slot)
        shared_player = list(rows)
        shared_player[-1] = {**shared_player[-1], "player_index": 0}
        with self.assertRaisesRegex(RosterWorkspaceError, "more than one"):
            stock_active_from_memberships(shared_player)
        outside_team = list(rows)
        outside_team[-1] = {**outside_team[-1], "team_index": 32}
        with self.assertRaisesRegex(RosterWorkspaceError, "0 to 31"):
            stock_active_from_memberships(outside_team)


if __name__ == "__main__":
    unittest.main()
