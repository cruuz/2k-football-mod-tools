"""Seedless native input, CAP cancellation, fresh Franchise and cold reload.

No game boot, disc copy, executable recipe, prepared input Franchise or GUI.
Rendering, devices and entropy are explicit fixture services. Native menu
input/stack, CAP, roster/contract and complete league initialization run.
"""
from pathlib import Path
import hashlib
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career_save as career_save
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_mode_fixture import Machine
from tests.mod_editor.test_nfl2k5_roster_records import RETAIL_EXTRACTION


def retail_roster():
    from tools.nfl2k5_roster_reclassify import OuterImage, load_resources
    try:
        with OuterImage(RETAIL_EXTRACTION) as archive:
            if archive.entries[5].size > 1024**2:
                raise unittest.SkipTest("retail roster resource exceeds 1 MiB")
            body = load_resources(archive, historic=False)[0].body
    except (OSError, ValueError) as exc:
        raise unittest.SkipTest(f"retail roster resource unavailable: {exc}") from exc
    if hashlib.sha256(body).hexdigest() != "b1164eeed262988dc97d840ba59f6274c1f5d4505249474e4cafd4e322d9f7ae":
        raise unittest.SkipTest("retail roster resource pin differs")
    return body


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, retail ROST and Unicorn are required")
class FrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.roster = retail_roster()
        cls.payload = mode.apply(retail)[0]
        union = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        cls.second = mode.apply(mode.space.apply(retail, union, scaleout=True)[0])[0]

    def enter(self, m):
        m.frontend(self.roster)
        m.call(0x6E390, ecx=m.manager, edx=0x5015CC)
        m.select(1)
        self.assertEqual(m.top(), m.labels["entry_menu"])

    def complete_cap(self, m):
        position = m.uc.mem_read(m.get(0xCB8B14) + 0x35, 1)[0]
        attributes = 0x56A560 if position == 0 else (0x56B560 if position == 4 else None)
        for expected in (0x56ED80, 0x56EBA0, attributes, m.labels["team_menu"]):
            m.frame(0x10)
            if expected is not None:
                self.assertEqual(m.top(), expected)
        self.assertEqual(m.get(m.state + 2680), 2)

    def test_game_modes_input_draft_confirmation_cancel_and_only_explicit_exit(self):
        with Machine(self.payload) as m:
            self.enter(m)
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.dialog_answer = 1  # native Franchise confirmation: cancel
            m.select(0)
            self.assertEqual(m.get(mode.EXTRA_VA), 0)
            self.assertEqual(m.get(m.state + 2676), 0)
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels["entry_menu"])
            self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
            m.select(3)
            self.assertEqual(m.top(), 0x515660)
            self.assertEqual(m.get(m.state + 2672), 0)
            self.assertEqual(m.get(0xE576A0), 0)

    def test_all_positions_cancel_restores_entire_roster_and_names(self):
        for position in range(17):
            with self.subTest(position=position), Machine(self.payload) as m:
                self.enter(m)
                before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
                m.select(1)
                p = m.get(0xCB8B14)
                self.assertNotEqual(p, 0)
                # Model a native CAP field edit, not an executable player recipe.
                m.uc.mem_write(p + 0x35, bytes((position,)))
                m.call(0x343460)
                if position >= 12:
                    for offset in range(0x36, 0x52):
                        if offset not in (0x4B, 0x4D, 0x4F):
                            self.assertEqual(m.uc.mem_read(p + offset, 1), b"A")
                m.frame(0x200)
                self.assertEqual(m.top(), m.labels["entry_menu"])
                self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
                self.assertEqual(m.get(m.state + 2680), 0)
                self.assertEqual(m.get(0xCB8B14), 0)
                self.assertEqual(m.get(m.state), 0)

    def test_appearance_equipment_back_and_placement_cancel(self):
        with Machine(self.payload) as m:
            self.enter(m)
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.select(1)
            m.frame(0x10)
            m.frame(0x10)
            self.assertEqual(m.top(), 0x56EBA0)
            m.frame(0x200)
            self.assertEqual(m.top(), 0x56ED80)
            m.frame(0x200)
            self.assertEqual(m.top(), 0x56F050)
            self.complete_cap(m)
            self.assertEqual(m.get(m.root + 0x38), int.from_bytes(before[0x38:0x3C], "little") + 1)
            m.frame(0x200)
            self.assertEqual(m.top(), m.labels["entry_menu"])
            self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
            self.assertEqual(m.get(m.state + 2680), 0)

    def test_full_pool_and_full_fa_refuse_visibly_without_mutation(self):
        for reason in ("pool", "free_agents", "alias"):
            with self.subTest(reason=reason), Machine(self.payload) as m:
                self.enter(m)
                if reason == "pool":
                    for i in range(m.get(m.root)):
                        at = m.get(m.root + 4) + 84 * i + 8
                        m.uc.mem_write(at, bytes((m.uc.mem_read(at, 1)[0] | 4,)))
                elif reason == "free_agents":
                    m.put(m.root + 0x38, 2500)
                else:
                    p = m.call(0xBFF50)
                    m.put(m.get(m.root + 4) + 16, m.get(p + 16))
                before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
                m.select(1)
                self.assertEqual(m.top(), m.labels["entry_menu"])
                self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
                self.assertEqual(m.get(m.state + 2676), 0)
                self.assertIn(("notice", "Roster is full."), m.events)

    def test_signed_but_invalid_career_shows_error_and_keeps_entry_usable(self):
        from tests.mod_editor.test_nfl2k5_my_career_inline import block_for
        from tests.nfl2k5_my_career_fixture import draft_save
        source = draft_save()
        bad = source + block_for(source)[:-1] + b"\xff"
        with Machine(self.payload) as m:
            self.enter(m)
            m.native_load(bad)
            self.assertIn(("notice", "Career load failed."), m.events)
            self.assertEqual(m.get(m.state), 0)
            self.assertEqual(m.top(), m.labels["entry_menu"])
            m.dialog_answer = 1
            m.select(0)
            self.assertEqual(m.get(mode.EXTRA_VA), 0)
            self.assertEqual(m.top(), m.labels["entry_menu"])

    def test_team_limit_and_confirmation_cancel_leave_no_partial_franchise(self):
        with Machine(self.payload) as m:
            self.enter(m)
            m.select(1)
            self.complete_cap(m)
            m.select(0)
            self.assertEqual(m.top(), m.labels["club_menu"])
            self.assertEqual(m.get(m.state + 432 + 32 * 52), 3)
            m.select(0)
            self.assertEqual(m.get(m.state + 2684), 0)
            t = m.get(m.root + 0x1C)
            count = bytes(m.uc.mem_read(t + 0x11C, 1))
            m.uc.mem_write(t + 0x11C, b"6")
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.select(1)
            self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
            self.assertEqual(m.get(0xE576A0), 0)
            self.assertEqual(m.get(m.state), 0)
            m.uc.mem_write(t + 0x11C, count)
            before = bytes(m.uc.mem_read(m.root, len(self.roster) - 64))
            m.dialog_answer = 3
            m.select(1)
            self.assertEqual(m.uc.mem_read(m.root, len(before)), before)
            self.assertEqual(m.get(0xE576A0), 0)
            self.assertEqual(m.top(), m.labels["team_menu"])

    def test_two_fresh_careers_all_native_initialization_and_cold_disc_relocation(self):
        careers = []
        # Both clubs launch their own earliest fixture directly.
        for position, club, payload in ((0, 2, self.payload), (4, 31, self.second)):
            with self.subTest(position=position, club=club), Machine(payload) as m:
                self.enter(m)
                m.select(1)
                p = m.get(0xCB8B14)
                m.uc.mem_write(p + 0x35, bytes((position,)))
                m.call(0x343460)
                self.complete_cap(m)
                m.select(0)
                m.select(club)
                trace = []
                for va in (0x148C60, 0x10EA10, 0x13EE10, 0x246F00, 0x2BEC20,
                           0x3228A0, 0x2BD260, 0x13EC90, 0x13F1B0):
                    m.stubs.append(m.uc.hook_add(m.u.UC_HOOK_CODE,
                                                lambda _, at, *__: trace.append(at), begin=va, end=va))
                m.select(1, budget=500000000)
                self.assertEqual(m.top(), m.labels["apartment"])
                self.assertEqual(m.get(0xE576A0), 2)
                self.assertEqual(m.get(0xE576A4), 7)
                self.assertEqual(m.get(0xE6011C), 0)  # native Weekly Preparation off
                self.assertEqual(m.call("primary"), p)
                self.assertEqual(m.get(m.state + 56), club)
                self.assertTrue({0x148C60, 0x10EA10, 0x13EE10, 0x246F00, 0x2BEC20,
                                 0x3228A0, 0x2BD260, 0x13EC90, 0x13F1B0} <= set(trace))
                self.assertLess(trace.index(0x13EE10), trace.index(0x13F1B0))
                output = m.native_save(budget=500000000)
                self.assertEqual(len(output), 720172)
                self.assertEqual(career_save.read(output)[39], position)
                careers.append(output)
        # Both independent careers load on either build, with fresh CPU/RW each time.
        self.assertNotEqual(careers[0][-128:], careers[1][-128:])
        for payload in (self.payload, self.second):
            for career in careers:
                with Machine(payload) as cold:
                    cold.frontend(self.roster)
                    cold.native_load(career)
                    self.assertEqual(cold.get(cold.state + 2580), 2)
                    self.assertEqual(cold.get(cold.state + 2576), 0)
                    self.assertNotEqual(cold.call("primary"), 0)
                    self.assertEqual(cold.uc.mem_read(cold.state + 149, 1), career[-89:-88])
                    self.assertEqual(cold.get(0xBDBDA0), 7)
                    cold.loaded_menu()
                    cold.child_services()
                    self.assertEqual(cold.top(), cold.labels["apartment"])
                    self.assertEqual(cold.depth(), 0)
                    card = 0x535E70 if career[-89] == 0 else 0x5365A8
                    for row, child in ((1, cold.labels["practice_menu"]),
                                       (2, card), (4, 0x507EC8)):
                        cold.select(row)
                        self.assertEqual(cold.top(), child)
                        cold.frame(0x200)
                        self.assertEqual(cold.top(), cold.labels["apartment"])
                        self.assertEqual(cold.depth(), 0)
                    # Real Practice input/stack and pause/confirm/ended dispatch;
                    # the fixture supplies the engine/renderer service boundary.
                    balance = cold.get(cold.state + 64)
                    cold.select(1)
                    cold.frame(0x10)
                    self.assertEqual(cold.top(), 0x5275F8)
                    cold.frame(0x10)
                    self.assertEqual(cold.top(), 0x4E7EC0)
                    self.assertEqual(cold.depth(), 1)
                    cold.frame(0x10)
                    self.assertEqual(cold.top(), 0x4E9078)
                    cold.select(12)
                    self.assertEqual(cold.top(), 0x4E8D70)
                    cold.select(2)
                    cold.frame()
                    self.assertEqual(cold.top(), cold.labels["apartment"])
                    self.assertEqual(cold.get(cold.state + 64), balance)
                    if career[-89] == 0:
                        # Direct career fixture -> Team Select -> Game.
                        # Engine stepping is still a service seam, not a played
                        # match. The postgame parent must execute before return.
                        cold.dialog_answer = 0
                        cold.select(0)
                        self.assertEqual(cold.top(), 0x51B908)
                        cold.frame(0x10)
                        self.assertEqual(cold.top(), 0x4E7EC0)
                        self.assertEqual(cold.get(cold.manager + 8 * (cold.depth() - 1)), 0x4F19E8)
                        fixture_before_quit = cold.call(0xC4FD0, ecx=0, edx=0)
                        self.assertNotEqual(fixture_before_quit, 3)
                        cold.frame(0x10)
                        cold.select(12)
                        cold.select(2)
                        cold.frame()
                        self.assertEqual(cold.top(), 0x4F19E8)
                        cold.frame()
                        self.assertEqual(cold.top(), cold.labels["apartment"])
                        self.assertEqual(cold.depth(), 0)
                        self.assertEqual(cold.get(cold.state + 64), balance)
                        self.assertEqual(cold.call(0xC4FD0, ecx=0, edx=0), fixture_before_quit)
                        # Native failed scene-load unwind preserves the same
                        # postgame parent, then returns to a usable apartment.
                        cold.game_services(load=False)
                        cold.select(0)
                        self.assertEqual(cold.top(), 0x51B908)
                        cold.frame(0x10)
                        self.assertEqual(cold.top(), 0x4F19E8)
                        cold.frame()
                        self.assertEqual(cold.top(), cold.labels["apartment"])
                        self.assertEqual(cold.get(cold.state + 64), balance)
                        cold.select(2)
                        self.assertEqual(cold.top(), card)
                        cold.frame(0x200)
                        self.assertEqual(cold.top(), cold.labels["apartment"])


if __name__ == "__main__":
    unittest.main()
