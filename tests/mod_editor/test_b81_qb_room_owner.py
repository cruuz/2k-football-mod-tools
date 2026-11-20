"""b81 qb34: the quarterback room owner's fixed pages, byte authentication and Retail restore.

Allocator (DESIGN 5.1, test T14 in part): the owner takes 0x1529000..0x152BFFF in every request set, never advances the
pool cursor, and every other pool owner steps over the range whether or not the room is requested. Owner (T12 at
owner level, T15): Realistic then Retail is the source plus an empty reservation byte for byte; foreign bytes at any
hook site or in the page make status() read foreign and both levels refuse, with or without the page.
Real executables come from the private fixtures (b81 env.sh); those cases skip without them.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as budget  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

ROOM = ("nfl2k5_qb_room", "code", 0x3000, 0x1000)
HELMET_XBE_SHA = "98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e"
V09_XBE_SHA = "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"


def _room_row(rows):
    found = [r for r in rows if r["owner"] == ROOM[0]]
    return found[0] if len(found) == 1 else None


class AllocatorPlacementTests(unittest.TestCase):
    def test_constants_and_late_owner_order(self):
        self.assertEqual((space.QB_ROOM_OWNER, space.QB_ROOM_VA, space.QB_ROOM_SIZE), (ROOM[0], 0x1529000, 0x3000))
        self.assertEqual(space.QB_ROOM_REQUEST, ROOM)
        self.assertEqual(space.LATE_OWNERS[-1], ROOM[0])
        self.assertIn(ROOM, space.dormant_union())

    def test_the_room_alone_and_in_the_dormant_union_sits_at_its_fixed_pages(self):
        for name, requests in (("alone", [ROOM]), ("legacy flag", None), ("dormant union", list(space.dormant_union()))):
            with self.subTest(case=name):
                report = space.plan([ROOM], scaleout=False) if requests is None else space.plan(requests)
                row = _room_row(report["allocations"])
                self.assertEqual((row["va"], row["size"], row["align"]), (0x1529000, 0x3000, 0x1000))
                self.assertEqual(report["file_size"] - space.SCALE3_FILE_SIZE, 0x152C000 - space.POOL_VA)

    def test_adding_the_room_moves_no_row_and_does_not_advance_the_cursor(self):
        union = [r for r in space.dormant_union() if r[0] != ROOM[0]]
        before = space.plan(union)["allocations"]
        after = space.plan(union + [ROOM])["allocations"]
        self.assertEqual([r for r in before if r["owner"] != space.DIRECTORY_OWNER and r not in after], [])
        # A pool owner planned after the room still starts at the cursor below it, not above 0x152C000.
        later = ("zz_synthetic_after_room", "code", 0x100, 16)
        with_room = space.plan(union + [ROOM, later])["allocations"]
        without = space.plan(union + [later])["allocations"]
        self.assertEqual(next(r for r in with_room if r["owner"] == later[0])["va"],
                         next(r for r in without if r["owner"] == later[0])["va"])
        self.assertLess(next(r for r in with_room if r["owner"] == later[0])["va"], 0x1529000)

    def test_every_other_pool_owner_steps_over_the_range_even_without_the_room(self):
        # An owner that would straddle 0x1529000 is placed after the room's pages whether or not the room is requested,
        # so an owner installed first can never take the room's address. (On the old code it straddled the range.)
        filler = ("aa_synthetic_filler", "code", 0x1529000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        # Both are larger than the v3 code run holds, so both go whole to the pool, in name order.
        straddle = ("ab_synthetic_straddle", "code", 0x20000, 16)
        for requests in ([filler, straddle], [filler, straddle, ROOM]):
            with self.subTest(room=ROOM in requests):
                rows = space.plan(requests)["allocations"]
                placed = next(r for r in rows if r["owner"] == straddle[0])
                self.assertEqual(placed["va"], 0x152C000)
                for row in rows:
                    if row["owner"] != ROOM[0]:
                        self.assertFalse(row["va"] < 0x152C000 and row["va"] + row["size"] > 0x1529000, row)

    def test_an_owner_bumped_over_the_ownership_page_also_steps_over_the_room(self):
        ownership = (space.FRANCHISE_OWNERSHIP, "code", space.FRANCHISE_OWNERSHIP_SIZE, 16)
        filler = ("aa_synthetic_filler", "code", 0x1528000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        bumped = ("ab_synthetic_bumped", "code", 0x20000, 16)
        rows = space.plan([filler, bumped, ownership])["allocations"]
        self.assertEqual(next(r for r in rows if r["owner"] == bumped[0])["va"], 0x152C000)

    def test_a_foreign_room_request_is_refused(self):
        for request in (("nfl2k5_qb_room", "code", 0x2000, 0x1000), ("nfl2k5_qb_room", "data", 0x3000, 0x1000)):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, "quarterback room"):
                space.plan([request])

    def test_allocator_fixture_is_the_dormant_union(self):
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text(encoding="utf-8"))
        self.assertIn(list(ROOM), rows)
        self.assertEqual({tuple(r) for r in rows}, set(space.dormant_union()))


class MemoryBudgetTests(unittest.TestCase):
    def test_the_room_row_follows_the_quarterback_option_unless_named(self):
        needs = {"k128_memory": True, "depth_locks": True, "depth_chart_rows": True}
        cases = (({"sim_qb_injuries": "realistic", **needs}, True), ({"sim_qb_injuries": "custom", **needs}, True),
                 ({"sim_qb_injuries": "realistic", "k128_memory": True}, False),  # followed, needs missing: left out
                 ({"sim_qb_injuries": "retail", **needs}, False), (needs, False),
                 ({"sim_qb_injuries": "realistic", "qb_room": "retail", **needs}, False), ({"qb_room": "realistic"}, True))
        for opts, expected in cases:
            with self.subTest(opts=opts):
                self.assertEqual("qb_room" in budget.owners(opts, 128), expected)
        self.assertEqual(budget.BUILD_OWNER_BYTES["qb_room"], (0x3000, 0, 0, 0, 0))

    def test_the_resident_executable_reaches_the_end_of_the_room(self):
        base = {"k128_memory": True, "sim_qb_injuries": "realistic", "depth_locks": True, "depth_chart_rows": True}
        with_room = budget.xbe_resident(base, 128)
        without = budget.xbe_resident(dict(base, qb_room="retail"), 128)
        # The quarterback bank ends at 0x1528000; the room's pages end at 0x152C000.
        self.assertEqual(with_room - without, 0x152C000 - 0x1528000)


def _private(variable, sha):
    path = Path(os.environ.get(variable, ""))
    if not path.is_file():
        raise unittest.SkipTest(f"private fixture {variable} is absent")
    from mod_editor.core import mod_build
    data = mod_build._xbe_bytes(path)
    if hashlib.sha256(data).hexdigest() != sha:
        raise unittest.SkipTest(f"{variable} is not the pinned executable")
    return data


class OwnerTests(unittest.TestCase):
    """Owner level on the reviewed v0.10 helmet test executable (98dd7329) with slice 1 Realistic (9f435b38)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        cls.room, cls.code = room, room._code()
        cls.source = _private("NFL2K5_B81_REVIEWED_TEST_DISC", HELMET_XBE_SHA)
        cls.slice1, _ = qb.apply(cls.source, "realistic")
        cls.applied, cls.receipt = room.apply(cls.slice1, "realistic")

    def test_settings_and_status(self):
        room = self.room
        self.assertEqual(hashlib.sha256(self.slice1).hexdigest()[:8], "9f435b38")
        self.assertEqual(room.read_settings(self.slice1), {"status": "retail", "mode": "retail", "reserved": False,
                                                           "va": None})
        settings = room.read_settings(self.applied)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"], settings["va"]),
                         ("applied", room.REALISTIC_STAGES, room.SHADOW_DEFAULT, 0x1529000))
        # Stage 3a handover: D1 only, shadow off (3b, 3c and 4a stay off).
        self.assertEqual((room.REALISTIC_STAGES, room.SHADOW_DEFAULT), (self.code.STAGE_D1, False))
        self.assertEqual((settings["stages"], settings["shadow"]), (1, False))
        row = _room_row(space.layout(self.applied)["allocations"])
        self.assertEqual((row["va"], row["size"]), (0x1529000, 0x3000))

    def test_the_page_and_sites_hold_exactly_the_linked_template(self):
        code, image = self.code, XbeImage(self.applied)
        record = code.settings_record(self.room.REALISTIC_STAGES, shadow=self.room.SHADOW_DEFAULT)
        self.assertEqual(image.read(0x1529000, 0x3000), code.page_bytes(0x1529000, record))
        for label, at, original, patched in code.sites(0x1529000, self.room.REALISTIC_STAGES):
            self.assertEqual(image.read(at, 5), patched, label)
            self.assertEqual(XbeImage(self.slice1).read(at, 5), original, label)
        sign = next(h for h in code.HOOKS if h[2] == "sign_entry")
        self.assertEqual(image.read(sign[0], 5), sign[1])

    def test_realistic_then_retail_is_the_source_plus_the_empty_reservation(self):
        room = self.room
        retail, receipt = room.apply(self.applied, "retail")
        reserved, _ = space.extend_scaleout(self.slice1, room.REQUESTS)
        self.assertEqual(retail, reserved)
        self.assertEqual(receipt["status"], "retail")
        self.assertEqual(XbeImage(retail).read(0x1529000, 0x3000), b"\xcc" * 0x3000)
        self.assertEqual(room.read_settings(retail)["reserved"], True)
        self.assertEqual(room.apply(retail, "realistic")[0], self.applied)
        self.assertEqual(room.apply(self.slice1, "retail"), (self.slice1, room.apply(self.slice1, "retail")[1]))
        self.assertEqual(room.apply(self.slice1, "retail")[1]["changed_bytes"], 0)
        again, receipt = room.apply(self.applied, "realistic")
        self.assertEqual((again, receipt["status"]), (self.applied, "already_applied"))

    def test_a_calibration_record_is_recognized_and_replaced_by_the_studio_record(self):
        room, code = self.room, self.code
        record = code.settings_record(code.STAGE_D1 | code.STAGE_D2D3, shadow=False, h0_ppm=12500)
        page = code.page_bytes(0x1529000, record)
        custom = room._patch(self.applied, [(0x1529000, XbeImage(self.applied).read(0x1529000, 0x3000), page)])
        settings = room.read_settings(custom)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"], settings["h0_ppm"]),
                         ("applied", 3, False, 12500))
        self.assertEqual(room.apply(custom, "realistic")[0], self.applied)

    def test_a_signing_stage_page_links_the_ir_store_and_retail_restores_all_three_sites(self):
        from mod_editor.core import nfl2k5_injured_reserve as ir
        room, code = self.room, self.code
        stages = code.STAGE_D1 | code.STAGE_SIGN
        store = ir.store_va(self.applied)
        self.assertTrue(store)
        record = code.settings_record(stages, shadow=True)
        page = code.page_bytes(0x1529000, record, ir_store_va=store)
        self.assertEqual(page[code.LINK_IR_STORE:code.LINK_IR_STORE + 4], store.to_bytes(4, "little"))
        image = XbeImage(self.applied)
        edits = [(0x1529000, image.read(0x1529000, 0x3000), page)]
        edits += [(at, original, patched) for label, at, original, patched in code.sites(0x1529000, stages)
                  if label == "sign_entry"]
        self.assertEqual(len(edits), 2)
        signing = room._patch(self.applied, edits)
        settings = room.read_settings(signing)
        self.assertEqual((settings["status"], settings["stages"]), ("applied", stages))
        unlinked = code.page_bytes(0x1529000, record, ir_store_va=0)
        self.assertEqual(room.status(room._patch(signing, [(0x1529000, page, unlinked)])), "foreign")
        retail, _ = room.apply(signing, "retail")
        self.assertEqual(retail, room.apply(self.applied, "retail")[0])
        sign_at, sign_retail = next((h[0], h[1]) for h in code.HOOKS if h[2] == "sign_entry")
        self.assertEqual(XbeImage(retail).read(sign_at, 5), sign_retail)
        self.assertTrue(room.requirements(self.applied, stages))  # 4a needs modern IR and ownership applied
        with self.assertRaisesRegex(ValueError, "trade stage"):
            room.requirements(self.applied, code.STAGE_TRADE)

    def test_foreign_site_bytes_are_refused_with_and_without_the_page(self):
        room = self.room
        for name, image in (("no page", self.slice1), ("page", self.applied),
                            ("empty reservation", room.apply(self.applied, "retail")[0])):
            for at, original, label, _stage in self.code.HOOKS:
                with self.subTest(image=name, site=label):
                    xbe = XbeImage(image)
                    data = bytearray(image)
                    offset = xbe.offset(at + 1, 1)
                    data[offset] ^= 0x40
                    foreign = bytes(data)
                    self.assertEqual(room.status(foreign), "foreign")
                    for level in room.LEVELS:
                        with self.assertRaisesRegex(ValueError, "not recognized"):
                            room.apply(foreign, level)

    def test_foreign_page_bytes_are_refused(self):
        room = self.room
        xbe = XbeImage(self.applied)
        for name, va in (("code", 0x1529004), ("settings", 0x1529000 + self.code.SETTINGS_OFFSET + 12),
                         ("link word", 0x1529000 + self.code.LINK_IR_STORE), ("counters", 0x1529000 + 0x2040),
                         ("ring", 0x1529000 + 0x2400), ("tail", 0x152BFFF)):
            with self.subTest(span=name):
                data = bytearray(self.applied)
                data[xbe.offset(va, 1)] ^= 0x01
                foreign = bytes(data)
                self.assertEqual(room.status(foreign), "foreign")
                for level in room.LEVELS:
                    with self.assertRaises(ValueError):
                        room.apply(foreign, level)
        retail = room.apply(self.applied, "retail")[0]
        data = bytearray(retail)
        data[XbeImage(retail).offset(0x152A000, 1)] = 0x90
        self.assertEqual(room.status(bytes(data)), "foreign")

    def test_realistic_needs_the_standard_executable_and_its_dependencies(self):
        retail = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        if not retail.is_file():
            self.skipTest("the private retail default.xbe is absent")
        payload = retail.read_bytes()
        self.assertEqual(len(self.room.requirements(payload)), 3)
        self.assertEqual(self.room.status(payload), "retail")
        with self.assertRaisesRegex(ValueError, "128 MB standard executable"):
            self.room.apply(payload, "realistic")
        self.assertEqual(self.room.apply(payload, "retail")[0], payload)


class ReleasedV09OwnerTests(unittest.TestCase):
    def test_the_released_v09_executable_takes_and_returns_the_room(self):
        from mod_editor.core import nfl2k5_qb_room as room
        source = _private("NFL2K5_V09_XISO", V09_XBE_SHA)
        self.assertEqual(room.requirements(source), [])
        applied, receipt = room.apply(source, "realistic")
        self.assertEqual(room.status(applied), "applied")
        before = space.layout(source)["allocations"]
        after = space.layout(applied)["allocations"]
        self.assertEqual([r for r in before if r["owner"] != space.DIRECTORY_OWNER and r not in after], [])
        self.assertEqual(_room_row(after)["va"], 0x1529000)
        self.assertEqual(room.apply(applied, "retail")[0], space.extend_scaleout(source, room.REQUESTS)[0])


if __name__ == "__main__":
    unittest.main()
