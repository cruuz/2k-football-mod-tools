"""Standalone bounded proofs of real page dispatch and the native move wrapper."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import unittest

from tests.nfl2k5_practice_squad_screen_fixture import ScreenMachine, screen, ps


class BindingsTests(ScreenMachine):
    def test_real_rebuild_dispatches_both_pages_and_clamps_last_row(self):
        self.demote()
        self.page()
        self.assertEqual(self.word(self.UI + 0xA4), 52)
        self.page(True)
        self.assertEqual(self.word(self.UI + 0xA4), 1)
        player = self.word(self.word(self.UI + 0x40))
        self.assertEqual(player, self.word(self.team + 52 * 4))
        self.move()
        self.assertEqual(self.byte(self.team + ps.ACTIVE_COUNT), 53)
        self.assertEqual(self.byte(self.team + ps.COUNT), 0)
        self.assertEqual(self.word(self.UI + 0xA4), 0)
        self.assertEqual(self.word(self.UI + 0xBC), 0)
        self.assertEqual(self.dialogs[-1][0], self.labels["promote_menu"])


    def test_native_binding_argument_expansion_and_getter_ret4(self):
        self.demote()
        self.page(True)
        self.put(self.UI + 0xB4, 0)
        count = self.call(0x172930, extra=((self.r.UC_X86_REG_ESI, self.labels["reserve_page"] + 0x30),
                                          (self.r.UC_X86_REG_EDI, self.UI)))
        self.assertEqual(count, 1)
        player = self.call(0x172930, extra=((self.r.UC_X86_REG_ESI, self.labels["reserve_page"] + 0x48),
                                           (self.r.UC_X86_REG_EDI, self.UI)))
        self.assertEqual(player, self.word(self.team + 52 * 4))
        original, state = self.snapshot(), bytes(self.uc.mem_read(self.data["va"], 256))
        for row in (-1, 1, 12, 65, 0x7fffffff):
            self.assertEqual(self.call(self.labels["reserve_get"], edx=row, args=(17,)), 0)
        for selector, position in ((-1, 17), (1, 17), (0, 0), (0, 18)):
            self.assertEqual(self.call(self.labels["reserve_count"], ecx=selector, edx=position), 0)
            self.assertEqual(self.call(self.labels["reserve_get"], ecx=selector, args=(position,)), 0)
        self.assertEqual(self.snapshot(), original)
        self.assertEqual(bytes(self.uc.mem_read(self.data["va"], 256)), state)

    def test_current_human_team_guards_and_no_first_coach_fallback(self):
        self.demote()
        before = self.snapshot()
        for address, value in ((0xE576A0, 0), (0xE576A0, 2), (0xE3C0A0, 0),
                               (0xE3C0A0, self.team + 1), (0xE3C0A0, self.other),
                               (0xE5775C, 0), (self.root + 0x18, 129),
                               (self.root + 4, 0), (0xB72918, 0)):
            with self.subTest(address=hex(address), value=value):
                old = self.word(address)
                self.put(address, value)
                self.assertEqual(self.call(self.labels["reserve_count"], edx=17), 0)
                self.assertEqual(self.call(self.labels["reserve_get"], args=(17,)), 0)
                self.put(address, old)
        self.assertEqual(self.snapshot(), before)
        # Team two is human too, but entering while it is selected must use it.
        self.put(0xE57760, 1)
        self.put(0xE3C0A0, self.other)
        self.call(self.labels["enter"], ecx=self.MANAGER)
        self.assertEqual(self.call(self.labels["selector"]), 1)
        self.assertEqual(self.call(self.labels["active_count"], ecx=1, edx=17), 53)
        self.assertEqual(self.call(self.labels["active_get"], ecx=1, args=(17,)), self.word(self.other))

    def test_metadata_null_primary_bounds_and_duplicate_owners_fail_closed(self):
        self.demote()
        player = self.word(self.team + 52 * 4)
        for at, raw in ((self.team + ps.VERSION_OFFSET, b"\x02"),
                        (self.team + ps.MARKER_OFFSET, b"\x00"),
                        (self.team + ps.COUNT, b"\x0d"),
                        (self.team + ps.ACTIVE_COUNT, b"\x41"),
                        (self.team + 52 * 4, b"\0" * 4),
                        (self.team + 52 * 4, (player + 1).to_bytes(4, "little")),
                        (self.other, player.to_bytes(4, "little")),
                        (self.word(self.root + 0x3c), player.to_bytes(4, "little")),
                        (0xE421E0, player.to_bytes(4, "little"))):
            with self.subTest(at=hex(at)):
                old = bytes(self.uc.mem_read(at, len(raw)))
                self.uc.mem_write(at, raw)
                candidate = self.snapshot()
                self.assertEqual(self.call(self.labels["reserve_count"], edx=17), 0)
                self.assertEqual(self.call(self.labels["reserve_get"], args=(17,)), 0)
                self.assertEqual(self.snapshot(), candidate)
                self.uc.mem_write(at, old)
        self.assertEqual(self.call(self.labels["reserve_count"], edx=17), 1)

    def test_sorted_player_identity_demotion_salary_flags_and_slot_repair(self):
        self.page()
        # A sorted first row points at original slot 20, never slot zero.
        player = self.word(self.team + 20 * 4)
        first = self.word(self.team)
        rows = self.word(self.UI + 0x40)
        self.put(rows, player)
        self.put(rows + 20 * 4, first)
        self.uc.mem_write(player + 0x25, b"\xe7")
        self.uc.mem_write(player + 0x52, b"\xff")
        self.uc.mem_write(self.team + 0x194, bytes((19, 20, 21, 52, 255, 128)))
        contract = bytes(self.uc.mem_read(player + 0x2c, 8))
        self.move()
        self.assertEqual(self.dialogs[-1][0], self.labels["demote_menu"])
        self.assertEqual(self.word(self.team), first)
        self.assertEqual(self.word(self.team + 52 * 4), player)
        self.assertEqual(self.byte(self.team + ps.ACTIVE_COUNT), 52)
        self.assertEqual(self.byte(self.team + ps.COUNT), 1)
        self.assertEqual(self.byte(player + 0x25), 7)
        self.assertEqual(self.byte(player + 0x52), 0xe0)
        self.assertEqual(bytes(self.uc.mem_read(self.team + 0x194, 6)), bytes((19, 255, 20, 51, 255, 128)))
        self.assertEqual(bytes(self.uc.mem_read(player + 0x2c, 8)), contract)
        salary = sum(ps.player_salary(bytes(self.uc.mem_read(self.word(self.team + i * 4), 84)))
                     for i in range(52))
        self.assertEqual(self.word(self.team + 0x124), salary)
        self.assertEqual(self.word(self.UI + 0xA4), 52)

    def test_53_12_65_limits_cancel_and_refusal_preserve_roster_selection(self):
        self.demote(12, fill=True)
        self.page(True, row=11)
        before, selected = self.snapshot(), self.word(self.UI + 0xBC)
        self.move(11)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.word(self.UI + 0xBC), selected)
        self.assertEqual(self.dialogs[-1][0], 0x5042FC)
        self.page(False, row=52)
        self.move(52)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.word(self.UI + 0xBC), 52)
        self.assertEqual(self.dialogs[-1][0], 0x5042FC)
        # Cancel never invokes either transaction, even when a move would fit.
        self.dialog_result = 0
        self.move(0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.byte(self.team + ps.ACTIVE_COUNT) + self.byte(self.team + ps.COUNT), 65)

    def test_success_at_11_reserves_and_last_active_row_clamped(self):
        self.demote(11)
        self.page(False, row=41)
        self.move(41)
        self.assertEqual(self.byte(self.team + ps.COUNT), 12)
        self.assertEqual(self.word(self.UI + 0xA4), 41)
        self.assertEqual(self.word(self.UI + 0xBC), 40)
        self.page(True, row=11)
        self.move(11)
        self.assertEqual(self.byte(self.team + ps.COUNT), 11)
        self.assertEqual(self.word(self.UI + 0xBC), 10)

    def test_owner_change_during_popup_is_rechecked_and_refused(self):
        self.demote()
        self.page(True)
        for change, restore in (
                (lambda: self.put(0xE5775C, 0), lambda: self.put(0xE5775C, 1)),
                (lambda: self.put(0xE3C0A0, self.other), lambda: self.put(0xE3C0A0, self.team)),
                (lambda: self.put(self.UI + 0x5c, self.labels["active_binding"]),
                 lambda: self.put(self.UI + 0x5c, self.labels["reserve_binding"])),
                (lambda: self.put(self.data["va"] + 4, 0), lambda: self.put(self.data["va"] + 4, self.MANAGER))):
            self.dialog_effect = change
            before, rebuilds = self.snapshot(), self.rebuilds
            self.move()
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.rebuilds, rebuilds)
            self.assertEqual(self.dialogs[-1][0], 0x5042FC)
            self.assertEqual(self.word(self.data["va"] + 8), 0)
            restore()

    def test_empty_pages_are_valid_and_never_open_an_action(self):
        self.uc.mem_write(self.team, bytes(260))
        for off in (ps.ACTIVE_COUNT, ps.VERSION_OFFSET, ps.MARKER_OFFSET, ps.COUNT):
            self.uc.mem_write(self.team + off, b"\0")
        for reserve in (False, True):
            self.page(reserve)
            before = self.snapshot()
            self.move()
            self.assertEqual(self.word(self.UI + 0xA4), 0)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.dialogs, [])

    def test_tab_cycle_and_teardown_free_native_sheet_buffers(self):
        self.demote()
        self.page()
        self.call(0x174CB0, ecx=self.UI)
        self.assertEqual(self.word(self.UI + 0x5c), self.labels["reserve_binding"])
        self.assertEqual(self.word(self.UI + 0xA4), 1)
        self.call(0x174CB0, ecx=self.UI)
        self.assertEqual(self.word(self.UI + 0x5c), self.labels["active_binding"])
        self.assertEqual(self.word(self.UI + 0xA4), 52)
        self.call(0x1707F0, ecx=self.UI)
        self.assertEqual(self.heap_live, set())
        self.call(self.labels["leave"], ecx=self.MANAGER)
        self.assertEqual(bytes(self.uc.mem_read(self.data["va"], 256)), bytes(256))
        self.assertEqual(self.call(self.labels["active_count"], edx=17), 0)
        self.call(self.labels["enter"], ecx=self.MANAGER)
        self.assertEqual(self.call(self.labels["active_count"], edx=17), 52)


    def test_native_entry_constructor_back_and_teardown_events(self):
        # These six services perform menu art/resource setup; event routing,
        # frame walking, sheet construction and destructor all execute native.
        self.menu_art_stubs = {0xf2920, 0xf3cd0, 0xf3d60, 0xf2d40, 0xf3680, 0xf3180}
        self.UI = self.word(self.MANAGER + 0x10c) + 0x65c
        self.put(self.MANAGER, self.MANAGER + 0x800)  # empty previous screen
        self.put(self.MANAGER + 8, self.labels["descriptor"])
        self.put(self.MANAGER + 0x100, 1)
        self.call(self.labels["row"], ecx=self.MANAGER)
        self.assertEqual(self.word(0xAA2408), self.labels["descriptor"])
        self.call(0x6E4E0, ecx=self.MANAGER, args=(1,))
        self.assertEqual(self.word(self.data["va"]), self.team)
        self.call(0x6E4E0, ecx=self.MANAGER, args=(3,))
        self.assertEqual(self.word(self.UI + 0xA4), 53)
        self.assertEqual(self.word(self.UI + 0x58), self.labels["sheet"])
        self.assertEqual(len(self.heap_live), 6)
        self.call(0x6E4E0, ecx=self.MANAGER, args=(10,))
        self.assertEqual(self.word(self.MANAGER + 0x100), 0)
        self.assertEqual(self.heap_live, set())
        self.assertEqual(bytes(self.uc.mem_read(self.data["va"], 256)), bytes(256))

    def test_real_activation_binding_passes_manager_sheet_and_row(self):
        self.page()
        player = self.word(self.team + 7 * 4)
        self.put(self.UI + 0xB4, 7)
        self.call(0x1727F0, extra=((self.r.UC_X86_REG_ESI, self.labels["sheet"] + 0xC4),
                                 (self.r.UC_X86_REG_EDI, self.UI)))
        self.assertEqual(self.word(self.team + 52 * 4), player)
        self.assertEqual(self.dialogs[-1][0], self.labels["demote_menu"])

    def test_ineligible_player_and_missing_context_refuse_without_mutation(self):
        self.page()
        player = self.word(self.team)
        for at, values in ((player + 8, (0, 8, 16, 28)), (player + 0x28, (0xee,))):
            old = self.byte(at)
            for value in values:
                self.uc.mem_write(at, bytes((value,)))
                before = self.snapshot()
                self.move()
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.dialogs[-1][0], 0x5042FC)
            self.uc.mem_write(at, bytes((old,)))
        self.put(0xE3C0A0, 0)
        self.put(0xAA2408, 0)
        self.call(self.labels["row"], ecx=self.MANAGER)
        self.assertEqual(self.word(0xAA2408), 0)
        self.assertEqual(self.dialogs[-1], (0x5042FC, self.labels["invalid_text"]))

    def test_page_reads_make_only_stack_writes(self):
        self.demote()
        writes = []
        handle = self.uc.hook_add(self.u.UC_HOOK_MEM_WRITE,
            lambda _u, _a, va, n, _v, _d: writes.append((va, n)))
        try:
            self.assertEqual(self.call(self.labels["reserve_count"], edx=17), 1)
            self.assertNotEqual(self.call(self.labels["reserve_get"], args=(17,)), 0)
        finally:
            self.uc.hook_del(handle)
        self.assertTrue(writes)
        self.assertTrue(all(0x3000000 <= va < va + n <= 0x3010000 for va, n in writes))


if __name__ == "__main__":
    unittest.main()
