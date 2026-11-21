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
        # The floor rides with injuries above zero (coordinator's rule); piece 3 where its handed-over bits apply.
        from mod_editor.core import nfl2k5_qb_room as room
        piece3 = room.REALISTIC_STAGES & room.PIECE3_BITS
        needs = {"k128_memory": True, "depth_locks": True, "depth_chart_rows": True}
        cases = (({"sim_qb_injuries": "realistic", **needs}, True), ({"sim_qb_injuries": "custom", **needs}, True),
                 ({"sim_qb_injuries": "realistic", "k128_memory": True}, True),
                 ({"sim_qb_injuries": "custom", "sim_qb_injury_rate": 0.0, **needs}, bool(piece3)),
                 ({"sim_qb_injuries": "custom", "sim_qb_injury_rate": 0.0, "k128_memory": True}, False),
                 ({"sim_qb_injuries": "retail", **needs}, False), (needs, False),
                 ({"sim_qb_injuries": "realistic", "qb_room": "retail", **needs}, True),
                 ({"qb_room": "realistic"}, bool(piece3)))
        for opts, expected in cases:
            with self.subTest(opts=opts):
                self.assertEqual("qb_room" in budget.owners(opts, 128), expected)
        self.assertEqual(budget.BUILD_OWNER_BYTES["qb_room"], (0x3000, 0, 0, 0, 0))

    def test_the_resident_executable_reaches_the_end_of_the_room(self):
        base = {"k128_memory": True, "sim_qb_injuries": "realistic", "depth_locks": True, "depth_chart_rows": True}
        with_room = budget.xbe_resident(base, 128)
        # Custom 0 keeps slice 1's bank but needs no floor, and without depth locks piece 3 is left out: no room.
        without = budget.xbe_resident(dict(base, sim_qb_injuries="custom", sim_qb_injury_rate=0.0, depth_locks=False), 128)
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
    """Owner level on the reviewed v0.10 helmet test executable (98dd7329) with the injury option Realistic (slices 1 to 3
    since the merge of 5854e5144: 501b8412; with scoring and revision 4 at the integration merge: f3a22805; slice 1
    alone gave 9f435b38)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        cls.room, cls.code = room, room._code()
        cls.source = _private("NFL2K5_B81_REVIEWED_TEST_DISC", HELMET_XBE_SHA)
        cls.slice1, _ = qb.apply(cls.source, "realistic")
        # Page mechanics on a D1 page through the calibration path (the Studio installs no piece 3 bit at the floor
        # handover, and its Realistic needs modern IR, which this executable lacks).
        cls.applied, cls.receipt = room.install_stages(cls.slice1, cls.code.STAGE_D1)

    def test_settings_and_status(self):
        room = self.room
        # b81 integration merge of qb34 (scoring + stability revision 4): f3a22805 (was 501b8412 at 5854e5144, 9f435b38
        # for slice 1 alone)
        self.assertEqual(hashlib.sha256(self.slice1).hexdigest()[:8], "f3a22805")
        self.assertEqual(room.read_settings(self.slice1), {"status": "retail", "mode": "retail", "reserved": False,
                                                           "va": None})
        settings = room.read_settings(self.applied)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"], settings["va"]),
                         ("applied", self.code.STAGE_D1, False, 0x1529000))
        # D1 + D2 handover (designer's addendum 2): D1 and D2 ship, D3 (256) and D4 stay off; the floor comes from the
        # injury level and is bit 64 alone since the floor review (F1(b): no over-cap rung), so Realistic installs 67.
        self.assertEqual((room.REALISTIC_STAGES, room.SHADOW_DEFAULT), (self.code.STAGE_D1 | self.code.STAGE_D2, False))
        self.assertEqual((room.FLOOR_STUDIO_STAGES, room.realistic_stages()), (64, 67))
        self.assertEqual(room.stage_names(67), ["D1 veteran or rookie", "D2 the kid's turn", "floor"])
        self.assertFalse(room.REALISTIC_STAGES & (self.code.STAGE_D3 | self.code.STAGE_D4))
        self.assertEqual(settings["stage_names"], ["D1 veteran or rookie"])
        row = _room_row(space.layout(self.applied)["allocations"])
        self.assertEqual((row["va"], row["size"]), (0x1529000, 0x3000))

    def test_the_page_and_sites_hold_exactly_the_linked_template(self):
        code, image = self.code, XbeImage(self.applied)
        record = code.settings_record(code.STAGE_D1, shadow=False)
        self.assertEqual(image.read(0x1529000, 0x3000), code.page_bytes(0x1529000, record))
        for label, at, original, patched in code.sites(0x1529000, code.STAGE_D1):
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
        self.assertEqual(room.install_stages(retail, self.code.STAGE_D1)[0], self.applied)
        self.assertEqual(room.apply(self.slice1, "retail"), (self.slice1, room.apply(self.slice1, "retail")[1]))
        self.assertEqual(room.apply(self.slice1, "retail")[1]["changed_bytes"], 0)
        again, receipt = room.install_stages(self.applied, self.code.STAGE_D1)
        self.assertEqual((again, receipt["status"]), (self.applied, "already_applied"))

    def test_a_calibration_record_is_recognized_and_replaced_by_the_studio_record(self):
        room, code = self.room, self.code
        record = code.settings_record(code.STAGE_D1 | code.STAGE_D2D3, shadow=False, h0_ppm=12500)
        page = code.page_bytes(0x1529000, record)
        custom = room._patch(self.applied, [(0x1529000, XbeImage(self.applied).read(0x1529000, 0x3000), page)])
        settings = room.read_settings(custom)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"], settings["h0_ppm"]),
                         ("applied", 3, False, 12500))
        self.assertEqual(room.install_stages(custom, code.STAGE_D1)[0], self.applied)

    def test_a_signing_stage_page_links_the_ir_store_and_retail_restores_all_three_sites(self):
        from mod_editor.core import nfl2k5_injured_reserve as ir
        room, code = self.room, self.code
        stages = code.STAGE_D1 | code.STAGE_SIGN | code.STAGE_E2  # only E2 reads the IR store link
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
        self.assertEqual(room._ir_store_va(self.applied, code.STAGE_D1 | code.STAGE_SIGN), 0)
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
        self.assertEqual(len(self.room.requirements(payload, self.code.STAGE_D1)), 3)
        self.assertEqual(self.room.status(payload), "retail")
        with self.assertRaisesRegex(ValueError, "128 MB standard executable"):
            self.room.apply(payload, "realistic")
        self.assertEqual(self.room.apply(payload, "retail")[0], payload)


class FloorOwnerTests(unittest.TestCase):
    """The floor's owner side (DESIGN addendum F1 to F8): stage bit 64, the 0x248010 site for bit 8 or 64, the native
    signing routine the last resort enters (F7.5) authenticated, the floor's needs, Retail restoring everything."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        cls.room, cls.code = room, room._code()
        cls.source = _private("NFL2K5_B81_REVIEWED_TEST_DISC", HELMET_XBE_SHA)
        cls.slice1, _ = qb.apply(cls.source, "realistic")

    def _changed(self, payload, va, data):
        image, out = XbeImage(payload), bytearray(payload)
        at = image.offset(va, len(data))
        out[at:at + len(data)] = data
        return bytes(out)

    def test_star_retention_reads_the_same_with_the_signing_call(self):
        # nfl2k5_star_retention authenticates the weekly advance's stage-6 caller window 0x247FD7..0x248015, which holds
        # the 0x248010 call the floor (and stage 4a) replaces; only the room's own call into its page is accepted.
        from mod_editor.core import nfl2k5_injured_reserve as ir, nfl2k5_star_retention as retention
        room = self.room
        base, _ = ir.apply(self.slice1, "modern", standard_guard=True)
        floor, _ = room.apply(base, "realistic", stages=room.STAGE_FLOOR | 1)
        self.assertEqual(retention.status(base), retention.status(floor))
        self.assertEqual(retention.status(floor), "applied")
        self.assertEqual(retention.apply(floor)[1]["status"], "already_applied")
        other = room._patch(floor, [(0x248010, XbeImage(floor).read(0x248010, 5), bytes.fromhex("e800000000"))])
        self.assertEqual(retention.status(other), "foreign")

    def test_the_floor_bit_and_its_site(self):
        room, code = self.room, self.code
        self.assertEqual((room.STAGE_FLOOR, room.STAGE_OVER_CAP), (64, 128))
        self.assertEqual((code.STAGE_FLOOR, code.STAGE_OVER_CAP, code.STAGE_MASK), (64, 128, 511))  # D3 = 256
        labels = {label: at for label, at, _o, _p in room._sites(0x1529000, code.STAGE_D1)}
        # Floor review step 2: 0x24807A enters end_entry (room_entry's pass, then the end-of-advance floor) and the
        # floor adds the stage advance's 0x248687.
        self.assertEqual(labels, {"pregame_entry": 0x247DCA, "end_entry": 0x24807A})
        self.assertEqual({label: at for label, at, *_ in room._sites(0x1529000, room.STAGE_FLOOR)},
                         {"pregame_entry": 0x247DCA, "end_entry": 0x24807A, "sign_entry": 0x248010,
                          "stage_entry": 0x248687})
        self.assertEqual(room._site_stages(room.STAGE_FLOOR) & code.STAGE_SIGN, code.STAGE_SIGN)
        self.assertEqual(room._site_stages(code.STAGE_D1), code.STAGE_D1)
        self.assertFalse(room.REALISTIC_STAGES & room.STAGE_FLOOR)  # set only at the floor handover, by the lead

    def test_over_the_cap_is_retired_and_the_ungated_entry_is_not_read(self):
        # Floor review F1(b), route A: the floor signs only through the gated routine and never over the cap, so bit 128
        # is refused for new installs and the native signing routine 0x322BB0..0x322DF1 is no longer the owner's to read.
        from mod_editor.core import nfl2k5_injured_reserve as ir
        room = self.room
        base, _ = ir.apply(self.slice1, "modern", standard_guard=True)
        for stages in (room.STAGE_OVER_CAP, room.STAGE_FLOOR | room.STAGE_OVER_CAP):
            with self.subTest(stages=stages):
                with self.assertRaisesRegex(ValueError, "over the cap is retired"):
                    room.apply(base, "realistic", stages=stages)
        floor, _ = room.apply(base, "realistic")
        for name, va in (("entry", 0x322BB0), ("body start", 0x322BB6), ("body", 0x322C40), ("return", 0x322DEE)):
            with self.subTest(case=name):
                changed = room._patch(floor, [(va, XbeImage(floor).read(va, 1), b"\xcc")])
                self.assertEqual(room.status(changed), "applied")
                self.assertEqual(room.apply(changed, "retail")[0],
                                 room._patch(room.apply(floor, "retail")[0],
                                             [(va, XbeImage(floor).read(va, 1), b"\xcc")]))
                self.assertFalse(any("native signing routine" in line
                                     for line in room.requirements(changed, room.STAGE_FLOOR)))

    def test_the_stage_advance_site(self):
        # Floor review step 2 (01535a35b): 0x248687, the stage advance's call 0x27EDF0 where every case converges, enters
        # stage_entry for bit 64 only. It is authenticated with the other sites and Retail restores it.
        from mod_editor.core import nfl2k5_injured_reserve as ir
        room, code = self.room, self.code
        site, retail = 0x248687, bytes.fromhex("e864670300")
        self.assertIn((site, retail, "stage_entry", room.STAGE_FLOOR), code.HOOKS)
        base, _ = ir.apply(self.slice1, "modern", standard_guard=True)
        empty = space.extend_scaleout(base, room.REQUESTS)[0]
        floor, receipt = room.apply(base, "realistic", stages=room.STAGE_FLOOR)
        self.assertIn(hex(site), receipt["sites"])
        call = XbeImage(floor).read(site, 5)
        self.assertEqual(call[0], 0xE8)
        self.assertEqual(site + 5 + int.from_bytes(call[1:], "little", signed=True), room.VA + code.LABELS["stage_entry"])
        piece3, _ = room.apply(base, "realistic", stages=code.STAGE_D1 | code.STAGE_D2)
        self.assertEqual(XbeImage(piece3).read(site, 5), retail)  # no floor, no stage advance call
        self.assertEqual(room.apply(floor, "retail")[0], empty)
        self.assertEqual(XbeImage(empty).read(site, 5), retail)
        foreign_call = bytes.fromhex("e800000000")
        for name, payload in (("floor page", floor), ("empty reservation", empty), ("piece 3 page", piece3)):
            with self.subTest(case=name):
                changed = room._patch(payload, [(site, XbeImage(payload).read(site, 5), foreign_call)])
                self.assertEqual(room.status(changed), "foreign")
                for level in ("retail", "realistic"):
                    with self.assertRaisesRegex(ValueError, "not recognized"):
                        room.apply(changed, level)

    def test_the_economy_routines_the_floor_calls_are_authenticated(self):
        room = self.room
        self.assertIsNone(room.floor_economy_problem(self.slice1))
        retail = Path(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        if retail.is_file():
            self.assertIn("restructure", room.floor_economy_problem(retail.read_bytes()))
        for name, va, data, word in (("restructure", 0x3B9F60, b"\xc3", "restructure"),
                                     ("cut-down jump", room.SMART_CUT + 1, b"\x00", "smart cut"),
                                     ("smart cut body", 0x3E21D4, b"\xcc", "smart cut")):
            with self.subTest(case=name):
                self.assertIn(word, room.floor_economy_problem(self._changed(self.slice1, va, data)))

    def test_the_floors_needs(self):
        room, code = self.room, self.code
        self.assertEqual(room.requirements(self.slice1, code.STAGE_D1), [])
        needs = room.requirements(self.slice1, code.STAGE_D1 | room.STAGE_FLOOR)
        # The helmet test executable has the economy and the practice squad but not modern IR or the ownership page.
        self.assertEqual(needs, ["Emergency quarterback signings need modern injured reserve.",
                                 "Emergency quarterback signings need the franchise ownership safeguards."])
        foreign = self._changed(self.slice1, 0x3B9F60, b"\xc3")
        self.assertIn("The quarterback floor found unrecognized code in the economy's restructure (0x3B9F60).",
                      room.requirements(foreign, code.STAGE_D1 | room.STAGE_FLOOR))
        # Without the floor bit the economy's routines are not the owner's business (the changed byte also breaks the
        # section digest the other owners check, so only the floor's own line is compared).
        self.assertFalse(any("restructure" in line for line in room.requirements(foreign, code.STAGE_D1)))
        with self.assertRaisesRegex(ValueError, "over the cap is retired"):
            room.requirements(self.slice1, code.STAGE_D1 | room.STAGE_FLOOR | room.STAGE_OVER_CAP)

    def test_install_stages_needs_modern_ir_and_ownership_and_round_trips(self):
        from mod_editor.core import nfl2k5_injured_reserve as ir
        room, code = self.room, self.code
        stages = code.STAGE_D1 | room.STAGE_FLOOR
        with self.assertRaisesRegex(ValueError, "modern injured reserve"):
            room.install_stages(self.slice1, stages)
        upgraded, _ = ir.apply(self.slice1, "modern", standard_guard=True)  # the real IR installer adds ownership
        floor, receipt = room.install_stages(upgraded, stages)
        settings = room.read_settings(floor)
        self.assertEqual((settings["status"], settings["stages"], settings["shadow"]), ("applied", stages, False))
        self.assertEqual(receipt["sites"], ["0x247dca", "0x24807a", "0x248010", "0x248687"])
        empty = space.extend_scaleout(upgraded, room.REQUESTS)[0]
        self.assertEqual(room.apply(floor, "retail")[0], empty)
        self.assertEqual(room.install_stages(empty, stages)[0], floor)
        self.assertEqual(room.apply(floor, "realistic")[0], room.apply(empty, "realistic")[0])  # Studio record wins
        self.assertEqual(room.status(self._changed(floor, 0x3B9F60, b"\xc3")), "foreign")

    def test_a_floor_page_installs_the_signing_site_and_retail_restores_everything(self):
        room, code = self.room, self.code
        if not hasattr(code, "STAGE_FLOOR"):
            self.skipTest("the page template has no floor yet ([native] commits it)")
        applied, _ = room.install_stages(self.slice1, code.STAGE_D1)
        stages = code.STAGE_D1 | room.STAGE_FLOOR
        record = code.settings_record(stages)
        page = code.page_bytes(0x1529000, record, ir_store_va=room._ir_store_va(applied, stages))
        edits = [(0x1529000, XbeImage(applied).read(0x1529000, 0x3000), page)]
        edits += [(at, original, patched) for label, at, original, patched in room._sites(0x1529000, stages)
                  if label in ("sign_entry", "stage_entry")]
        self.assertEqual(len(edits), 3)
        floor = room._patch(applied, edits)
        self.assertEqual((room.read_settings(floor)["status"], room.read_settings(floor)["stages"]), ("applied", stages))
        self.assertEqual(room.apply(floor, "retail")[0], room.apply(applied, "retail")[0])
        restructure = room._patch(floor, [(0x3B9F60, XbeImage(floor).read(0x3B9F60, 1), b"\xc3")])
        self.assertEqual(room.status(restructure), "foreign")



class PreviousRevisionTests(unittest.TestCase):
    """Pages an earlier revision's Studio wrote ([validator]'s finding at c8683ea7e, lead's request): the floor handover
    (template 75257128, stage set 192; the P2a candidate c93f6c0d), the reviewed stage 0 + 3a page (78d3633d3, stage
    set 1; candidate 4af354d7) and the D1 + D2 handover (template 65259084 at 692062151, 195; the P6 candidate
    72a78fce). They read "previous"; Realistic upgrades them in place to the current template
    (the bytes of a fresh install on the same source, no allocator row moves); Retail restores the source plus the
    empty reservation; any other page is still foreign. The previous executables are rebuilt here from the frozen
    templates and must equal the hashes recorded when those revisions were built."""

    # b81 merge of 5854e5144 (slices 2 and 3): the injury option's Realistic now writes slices 1 to 3, so every rebuilt
    # previous executable differs from the one its panel ran (on slice 1 alone). Re-pinned to the rebuilds at the merged
    # head; the panel executables were, in order: 72a78fce (P6 candidate at 692062151), 9e1f2b83 (P6-final at
    # 66d8a7e1b), 58462a62 (P2a-final at 66d8a7e1b), c93f6c0d / a0a81494 (floor handover), 4af354d7 / 6aef88eb (3a).
    # Integration merge of qb34 (scoring + stability revision 4 under the room): re-pinned again; every rebuild differs
    # from its 5854e5144 rebuild only where its source (the injury option's executable) differs, plus the shared registry
    # and header fields; the room's page and sites are unchanged. The 5854e5144 values were D1D2 52f4d9fe, REVIEW_67
    # 1c68a15f, REVIEW_64 e6928baf, FLOOR ab292056 / 6e14638a, STAGE_3A 449e651e / e3270c1b.
    D1D2_SHA = "cdb2fd96b7385b744c6389fcccb532f1edddddf7b8bc0233d93c6b389461957c"
    REVIEW_67_SHA = "e0acccbd619deffff42f19db0c9d04e607d1fe7c7ba0a2b695a0f0f6947178ff"
    REVIEW_64_SHA = "15a779c54c040f8b353e664e042e28187ce7fec03168b212412cedca0294ff9d"
    FLOOR_SHA = "5087b8d3260e6c855ce0b8173429ffce4e31f74e15b124425a231e5246d68d1f"
    FLOOR_EMPTY_SHA = "5a798bf10ffa901d854b65aeaca3815869139a7e337b7f2d50f0a5a1876cd300"
    STAGE_3A_SHA = "cd746c09fe8db307fb317a8cf201c0d2e66b4ab6ee27a2baeb1c2ee3a1ae22a4"
    STAGE_3A_EMPTY_SHA = "33b007d0191e8ddf0d25814c98cebf5b00d6aa592d77b494aac5ed21d22c3c37"

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_injured_reserve as ir, nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        cls.room = room
        source = _private("NFL2K5_B81_REVIEWED_TEST_DISC", HELMET_XBE_SHA)
        cls.slice1, _ = qb.apply(source, "realistic")
        cls.base, _ = ir.apply(cls.slice1, "modern", standard_guard=True)
        cls.floor_empty, cls.floor = cls._written_by("nfl2k5_qb_room_code_b81_floor", cls.base, 192)
        cls.stage_3a_empty, cls.stage_3a = cls._written_by("nfl2k5_qb_room_code_b81_3a", cls.slice1, 1)
        _empty, cls.d1d2 = cls._written_by("nfl2k5_qb_room_code_b81_d1d2", cls.base, 195)
        _empty, cls.review67 = cls._written_by("nfl2k5_qb_room_code_b81_floor_review", cls.base, 67)
        _empty, cls.review64 = cls._written_by("nfl2k5_qb_room_code_b81_floor_review", cls.base, 64)

    @classmethod
    def _written_by(cls, template, source, stages):
        """(empty reservation, what that revision's Studio wrote): its whole page and its calls, byte for byte."""
        import importlib
        old, room = importlib.import_module(f"mod_editor.core.{template}"), cls.room
        empty = space.extend_scaleout(source, room.REQUESTS)[0]
        page = old.page_bytes(room.VA, old.settings_record(stages), ir_store_va=0)
        edits = [(room.VA, b"\xcc" * room.SIZE, page)]
        edits += [(at, o, p) for _l, at, o, p in old.sites(room.VA, stages | 8 if stages & 64 else stages)]
        return empty, room._patch(empty, edits)

    @staticmethod
    def _rows(payload):
        return [(r["owner"], r["kind"], r["va"], r["size"]) for r in space.layout(payload)["allocations"]]

    def _changed(self, payload, va, data):
        image, out = XbeImage(payload), bytearray(payload)
        at = image.offset(va, len(data))
        out[at:at + len(data)] = data
        return bytes(out)

    def test_the_rebuilt_previous_executables_are_the_recorded_ones(self):
        sha = lambda data: hashlib.sha256(data).hexdigest()
        self.assertEqual((sha(self.floor), sha(self.floor_empty)), (self.FLOOR_SHA, self.FLOOR_EMPTY_SHA))
        self.assertEqual((sha(self.stage_3a), sha(self.stage_3a_empty)), (self.STAGE_3A_SHA, self.STAGE_3A_EMPTY_SHA))
        self.assertEqual(sha(self.d1d2), self.D1D2_SHA)
        self.assertEqual((sha(self.review67), sha(self.review64)), (self.REVIEW_67_SHA, self.REVIEW_64_SHA))

    def test_status_reads_previous(self):
        room = self.room
        for payload, revision, stages in ((self.floor, "b81 floor handover", 192), (self.stage_3a, "b81 stage 3a", 1),
                                          (self.d1d2, "b81 D1 + D2 handover", 195),
                                          (self.review67, "b81 floor review", 67), (self.review64, "b81 floor review", 64)):
            with self.subTest(revision=revision):
                settings = room.read_settings(payload)
                self.assertEqual((settings["status"], settings.get("revision"), settings.get("stages")),
                                 ("previous", revision, stages))
                self.assertEqual(room.status(payload), "previous")

    def test_realistic_upgrades_the_floor_page_in_place(self):
        room = self.room
        for stages in (None, 64):
            with self.subTest(stages=stages):
                upgraded, receipt = room.apply(self.floor, "realistic", stages=stages)
                fresh, _ = room.apply(self.base, "realistic", stages=stages)
                self.assertEqual(upgraded, fresh)
                self.assertEqual(receipt["upgraded_from"], "b81 floor handover")
                self.assertEqual(self._rows(upgraded), self._rows(self.floor))
                self.assertEqual(room.read_settings(upgraded)["status"], "applied")

    def test_the_d1_d2_page_upgrades_and_restores(self):
        room = self.room
        upgraded, receipt = room.apply(self.d1d2, "realistic")
        self.assertEqual(upgraded, room.apply(self.base, "realistic")[0])
        self.assertEqual((receipt["upgraded_from"], self._rows(upgraded)), ("b81 D1 + D2 handover", self._rows(self.d1d2)))
        self.assertEqual(room.apply(self.d1d2, "retail")[0], self.floor_empty)  # 87346291 + the empty reservation

    def test_the_floor_review_pages_upgrade_and_restore(self):
        # The page 66d8a7e1b's Studio wrote (P6-final and P2a-final; the witnesses there) differs from the current one
        # (the pool-free choose, 5ff30d9f8): it reads previous, upgrades to a fresh install and restores.
        room = self.room
        for payload, stages in ((self.review67, None), (self.review64, 64)):
            with self.subTest(stages=stages):
                upgraded, receipt = room.apply(payload, "realistic", stages=stages)
                self.assertEqual(upgraded, room.apply(self.base, "realistic", stages=stages)[0])
                self.assertEqual(receipt["upgraded_from"], "b81 floor review")
                self.assertEqual(self._rows(upgraded), self._rows(payload))
                self.assertEqual(room.apply(payload, "retail")[0], self.floor_empty)

    def test_retail_restores_the_floor_page(self):
        restored, receipt = self.room.apply(self.floor, "retail")
        self.assertEqual(restored, self.floor_empty)
        self.assertEqual((receipt["restored_stages"], receipt["restored_revision"]), (192, "b81 floor handover"))

    def test_the_stage_3a_page_upgrades_and_restores(self):
        room = self.room
        self.assertEqual(room.apply(self.stage_3a, "retail")[0], self.stage_3a_empty)
        self.assertEqual(room.apply(self.stage_3a, "realistic", stages=3)[0],
                         room.apply(self.stage_3a_empty, "realistic", stages=3)[0])
        # The current Realistic carries the floor, whose needs this executable lacks: refused with the needs.
        with self.assertRaisesRegex(ValueError, "modern injured reserve"):
            room.apply(self.stage_3a, "realistic")

    def test_star_retention_accepts_the_floor_pages_signing_call(self):
        from mod_editor.core import nfl2k5_star_retention as retention
        self.assertEqual(retention.status(self.base), "applied")
        self.assertEqual(retention.status(self.floor), "applied")
        self.assertEqual(retention.apply(self.floor)[1]["status"], "already_applied")

    def test_anything_else_is_still_foreign(self):
        import importlib
        room = self.room
        old = importlib.import_module("mod_editor.core.nfl2k5_qb_room_code_b81_floor")
        current_calls = {at: p for _l, at, _o, p in room._code().sites(room.VA, 64 | 8)}
        _empty, unwritten = self._written_by("nfl2k5_qb_room_code_b81_floor", self.base, 64)  # a set no Studio wrote
        cases = {"page code byte": self._changed(self.floor, room.VA + 0x10, b"\x90"),
                 "settings record": self._changed(self.floor, room.VA + old.SETTINGS_OFFSET + 8, b"\x41"),
                 "old page, current call": self._changed(self.floor, 0x248010, current_calls[0x248010]),
                 "stage set no Studio wrote": unwritten,
                 "3a page with a changed byte": self._changed(self.stage_3a, room.VA + 0x20, b"\x90"),
                 # The floor handover never wrote the stage advance site (floor review step 2); a call there is foreign.
                 "floor handover page, stage advance call": room._patch(
                     self.floor, [(0x248687, XbeImage(self.floor).read(0x248687, 5), current_calls[0x248687])])}
        for name, payload in cases.items():
            with self.subTest(case=name):
                self.assertEqual(room.status(payload), "foreign")
                for level in ("retail", "realistic"):
                    with self.assertRaisesRegex(ValueError, "not recognized"):
                        room.apply(payload, level)

class TestOnlyInstallTests(unittest.TestCase):
    """install_stages(test_without_needs=True) replays recorded seasons on executables made before modern IR and the
    ownership page; it skips only the dependency checks, and nothing in the Studio can reach it."""

    def test_the_studio_never_reaches_the_calibration_path(self):
        import re
        hits = []
        for path in [*(ROOT / "mod_editor").rglob("*.py"), ROOT / "tools/nfl2k5_modpack.py"]:
            if path.name in ("nfl2k5_qb_room.py",):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"install_stages|test_without_needs", text):
                hits.append(str(path.relative_to(ROOT)))
        self.assertEqual(hits, [])

    def test_the_floor_without_its_needs_on_9f435b38(self):
        from mod_editor.core import nfl2k5_qb_room as room, nfl2k5_sim_qb_injuries as qb
        source = _private("NFL2K5_B81_REVIEWED_TEST_DISC", HELMET_XBE_SHA)
        slice1, _ = qb.apply(source, "realistic")
        stages = room.STAGE_FLOOR
        with self.assertRaisesRegex(ValueError, "modern injured reserve"):
            room.install_stages(slice1, stages)
        replay, receipt = room.install_stages(slice1, stages, test_without_needs=True)
        self.assertTrue(receipt["test_without_needs"])
        self.assertEqual((room.read_settings(replay)["stages"], room.read_settings(replay)["shadow"]), (64, False))
        self.assertEqual(room.apply(replay, "retail")[0], space.extend_scaleout(slice1, room.REQUESTS)[0])
        with self.assertRaisesRegex(ValueError, "over the cap is retired"):
            room.install_stages(slice1, stages | room.STAGE_OVER_CAP, test_without_needs=True)
        # Authentication still applies (the byte is changed with resealed digests, so only the routine differs).
        changed = room._patch(slice1, [(0x3B9F60, XbeImage(slice1).read(0x3B9F60, 1), b"\xc3")])
        with self.assertRaisesRegex(ValueError, "restructure"):
            room.install_stages(changed, stages, test_without_needs=True)


class ReleasedV09OwnerTests(unittest.TestCase):
    def test_the_released_v09_executable_takes_and_returns_the_room(self):
        from mod_editor.core import nfl2k5_qb_room as room
        source = _private("NFL2K5_V09_XISO", V09_XBE_SHA)
        self.assertEqual(room.requirements(source, room._code().STAGE_D1), [])
        applied, receipt = room.install_stages(source, room._code().STAGE_D1)
        self.assertEqual(room.status(applied), "applied")
        before = space.layout(source)["allocations"]
        after = space.layout(applied)["allocations"]
        self.assertEqual([r for r in before if r["owner"] != space.DIRECTORY_OWNER and r not in after], [])
        self.assertEqual(_room_row(after)["va"], 0x1529000)
        self.assertEqual(room.apply(applied, "retail")[0], space.extend_scaleout(source, room.REQUESTS)[0])


if __name__ == "__main__":
    unittest.main()
