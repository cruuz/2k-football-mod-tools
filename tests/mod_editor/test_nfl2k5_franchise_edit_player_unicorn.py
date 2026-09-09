"""Native Contracts selection, row filtering, every editor page and Desk return.

Only bounded CPU components execute. No emulator, game boot, GUI or audio.
The fixture documents all substituted services; menu/record logic runs native.
"""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_edit_player as edit
from mod_editor.core import nfl2k5_position_row as position
from mod_editor.core import nfl2k5_depth_locks as locks
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_franchise_edit_player_fixture import Machine


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("bounded native menu proof requires Unicorn")
        cls.retail = retail_xbe()
        cls.patched = edit.apply(cls.retail)[0]
        from tests.nfl2k5_allocator_stack import compose
        cls.composed = compose(locks.apply(cls.retail)[0])[0]

    def opened(self, payload=None, **options):
        m = Machine(payload or self.patched, **options)
        m.build_contracts()
        # Exercise a nondefault scroll origin as well as the selected player.
        m.put(m.table + 0xC8, 1)
        m.open()
        self.assertEqual(m.modals[-1][-1], ("Edit Player", 10))
        self.assertEqual(m.get(0xCB8B14), m.player)
        self.assertEqual(m.get(0xCB8BA0), 1)
        self.assertEqual(m.get(0xCB8BA8), m.contracts_depth + 1)
        self.assertEqual(m.get(0xCB8BA4), int(m.face))
        self.assertIn("Position", m.fields())
        self.assertGreater(m.calls[0x2B83F0], 0)
        self.assertEqual(m.calls[0x346730], 1)
        m.writes.clear()
        return m

    def assert_contracts(self, m, offsets=(), written_offsets=()):
        self.assertEqual(m.top(), edit.CONTRACTS_VA)
        self.assertEqual(m.depth(), m.contracts_depth)
        self.assertIn((edit.CONTRACTS_VA, 3), m.events)
        self.assertGreater(m.calls[0xF3430], 0)
        snapshot = tuple(m.get(0xCB8BBC + off) for off in (8, 12, 16, 20, 24, 28))
        self.assertEqual(m.cursor(), snapshot)
        m.preserved(offsets)
        for _, va, size, _ in m.writes:
            # Finish writes the unchanged birth-day word even without an edit.
            permitted = {m.player + off for off in (*offsets, *written_offsets, 0x18, 0x19, 0x1A, 0x1B)}
            self.assertTrue(set(range(va, va + size)) <= permitted, (hex(va), size))
        self.assertEqual(m.get(0xE3C278), 80500)
        self.assertEqual(bytes(m.uc.mem_read(m.player + 0x52, 2)), b"\xff\xff")

    def to_desk(self, m):
        m.frame(0x200)
        self.assertEqual(m.top(), m.OFFICE)
        m.frame(0x200)
        self.assertEqual(m.top(), m.DESK)
        self.assertEqual(m.depth(), m.contracts_depth - 2)
        self.assertIn((m.DESK, 3), m.events)
        self.assertGreater(m.calls[0x14FF80], 0)  # native Desk row rebuild
        self.assertEqual(m.calls[0x13F1B0], 0)
        self.assertEqual(m.calls[0xC5D60], 0)

    def test_open_back_and_front_office_back_reach_retained_desk(self):
        for payload in (self.patched, self.composed):
            for face in (False, True):
                for depth in (0, 1):
                    with self.subTest(composed=payload is self.composed, face=face, desk=depth):
                        m = self.opened(payload, face=face, desk_depth=depth)
                        self.assertEqual(m.top(), edit.REAL_EDITOR_VA if face else edit.CREATED_EDITOR_VA)
                        m.frame(0x200)
                        self.assertGreater(m.calls[0xF3690], 0)  # suppress generic second pop
                        self.assert_contracts(m)
                        self.to_desk(m)
                        m.preserved()

    def test_controller_edits_position_appearance_equipment_ratings_and_finishes(self):
        for payload in (self.patched, self.composed):
            for face in (False, True):
                with self.subTest(composed=payload is self.composed, face=face):
                    m = self.opened(payload, face=face)
                    self.assertEqual(m.change("Position"), 0x345560)
                    m.frame(0x10)
                    self.assertEqual(len(m.fields()), 3 if face else 5)
                    self.assertEqual(m.change("Height"), 0x345860)
                    m.frame(0x10)
                    self.assertEqual(len(m.fields()), 16)
                    self.assertEqual(m.change("Helmet"), 0x345A30)
                    m.frame(0x10)
                    self.assertEqual(len(m.fields()), 27)
                    self.assertEqual(m.change("Speed"), 0x343FD0)
                    m.frame(0x10)
                    self.assertEqual(m.calls[0x346C50], 1)
                    self.assert_contracts(m, (0x35, 0x2B, 0x0C, 0x36))
                    self.to_desk(m)
                    m.preserved((0x35, 0x2B, 0x0C, 0x36))

    def test_position_cycles_all_seventeen_both_directions_without_template_reset(self):
        for payload in (self.patched, self.composed):
            for face in (False, True):
                with self.subTest(composed=payload is self.composed, face=face):
                    m = self.opened(payload, face=face)
                    original = bytes(m.uc.mem_read(m.player, 84))
                    for reverse in (False, True):
                        for _ in range(17):
                            before = m.uc.mem_read(m.player + 0x35, 1)[0]
                            m.change("Position", reverse=reverse)
                            self.assertEqual(m.uc.mem_read(m.player + 0x35, 1)[0],
                                             (before + (-1 if reverse else 1)) % 17)
                            m.call(0x343460)  # native edit-mode template guard
                            m.preserved((0x35,))
                        self.assertEqual(bytes(m.uc.mem_read(m.player, 84)), original)
                    m.frame(0x200)
                    self.assert_contracts(m, written_offsets=(0x35,))

    def test_back_is_immediate_edit_and_can_reopen_without_losing_player(self):
        m = self.opened(self.composed)
        m.change("Position")
        changed = m.uc.mem_read(m.player + 0x35, 1)[0]
        m.frame(0x200)
        self.assert_contracts(m, (0x35,))
        m.open()
        self.assertEqual(m.uc.mem_read(m.player + 0x35, 1)[0], changed)
        self.assertEqual(m.get(0xCB8B14), m.player)
        m.change("Position", reverse=True)
        m.frame(0x200)
        self.assert_contracts(m, written_offsets=(0x35,))

    def test_back_from_each_later_page_stays_in_editor_then_returns_contracts(self):
        for face in (False, True):
            m = self.opened(face=face)
            pages = [m.top()]
            for _ in range(3):
                m.frame(0x10)
                pages.append(m.top())
            for expected in reversed(pages[:-1]):
                m.frame(0x200)
                self.assertEqual(m.top(), expected)
            m.frame(0x200)
            self.assert_contracts(m)
            self.to_desk(m)

    def test_popup_retains_native_phase_team_retirement_and_offer_filters(self):
        # The same native table supplies the player; vary only the predicate
        # globals after building it. Cancel executes the full native epilogue.
        for stage in range(1, 10):
            for team_kind in ("own", "other", "free", "offer"):
                with self.subTest(stage=stage, team=team_kind):
                    results = []
                    for payload in (self.retail, self.patched):
                        m = Machine(payload)
                        m.build_contracts()
                        m.put(0xE576A4, stage)
                        if team_kind == "other":
                            m.put(0xACECD4, 1)
                        elif team_kind == "free":
                            m.put(0xACECD4, 32)
                        elif team_kind == "offer":
                            m.put(0xE3C600, m.player)
                        m.choice = 7
                        m.open()
                        self.assertEqual(m.top(), edit.CONTRACTS_VA)
                        results.append(m.modals[-1] if m.modals else [])
                    expected = results[0] + ([("Edit Player", 10)] if team_kind == "own" else [])
                    self.assertEqual(results[1], expected)
        for retired in (False, True):
            m = Machine(self.patched, stage=1)
            m.uc.mem_write(m.player + 8, bytes([(m.uc.mem_read(m.player + 8, 1)[0] & ~8) | (8 if retired else 0)]))
            m.build_contracts(); m.choice = 7; m.open()
            self.assertIn(("Edit Player", 10), m.modals[-1])
            self.assertEqual(("Talk out of retirement", 4) in m.modals[-1], retired)

    def test_all_pages_match_real_rosters_callback_for_every_position(self):
        for face in (False, True):
            for pos in range(17):
                with self.subTest(face=face, position=pos):
                    chains = []
                    for from_rosters in (False, True):
                        m = Machine(self.patched, face=face)
                        m.uc.mem_write(m.player + 0x35, bytes([pos]))
                        m.build_contracts()
                        if from_rosters:
                            m.call(0x35F6C0, ecx=m.player, edx=m.MANAGER)
                        else:
                            m.open()
                        self.assertEqual(m.get(0xCB8B14), m.player)
                        pages = []
                        for _ in range(4):
                            pages.append((m.top(), tuple(m.fields())))
                            m.frame(0x10)
                        self.assertEqual(m.top(), edit.CONTRACTS_VA)
                        self.assertEqual(m.calls[0x346C50], 1)
                        m.preserved((0x35,))
                        chains.append(pages)
                    self.assertEqual(chains[0], chains[1])

    def test_empty_contracts_table_returns_with_balanced_stack(self):
        m = Machine(self.patched)
        m.call(edit.POPUP_VA, ecx=m.MANAGER, edx=m.table, args=(0,))
        self.assertFalse(m.modals)
        m.preserved()


if __name__ == "__main__":
    unittest.main()
