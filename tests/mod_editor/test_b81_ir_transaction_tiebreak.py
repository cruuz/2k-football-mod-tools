"""Execute the actual load-repair bank on native resolved transaction rows and mixed roster memberships."""
import struct
import unittest

from tests.mod_editor.test_b81_ir_load_ownership import HAVE_UC, LoadedLeague


LAST = 1 << 31
CURSOR, EVENTS = 0xE3F06C, 0xE3F070


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the compiled franchise ownership handler')
class TransactionTieBreak(unittest.TestCase):
    def machine(self, cursor, clubs=(2, 21)):
        m = LoadedLeague()
        for club in clubs:
            m.set_club(club, [100 + club, 10, 200 + club])
        m.word(CURSOR, cursor)
        return m

    def put_event(self, m, slot, packed, player, club):
        m.put(EVENTS + 12 * slot, struct.pack('<III', packed,
              m.player(player) if player is not None else 0, m.club(club) if club is not None else 0))

    def check_owner(self, m, target, clubs=(2, 21)):
        ring = m.read(CURSOR, 4 + 600 * 12)
        players = m.read(m.PLAYERS, m.PRIMARY_COUNT * 84)
        m.repair()
        for club in clubs:
            self.assertEqual(m.lists(club)[0], [100 + club, *([10] if club == target else []), 200 + club])
        self.assertEqual(m.read(CURSOR, len(ring)), ring)
        self.assertEqual(m.read(m.PLAYERS, len(players)), players)
        first = m.snapshot()
        m.repair()
        self.assertEqual(m.snapshot(), first)

    def test_latest_reliable_acquisition_and_failed_later_moves(self):
        for kind in (1, 4):
            with self.subTest(kind=kind):
                m = self.machine(1, (2, 14, 21))
                self.put_event(m, 597, LAST | 1, 10, 2)
                self.put_event(m, 598, LAST | kind, 10, 21)
                self.put_event(m, 599, LAST | 10, 10, 2)   # medical event
                self.put_event(m, 0, LAST | 1, 11, 2)      # another player
                self.check_owner(m, 21, (2, 14, 21))
        for newer in (0, 2, 8, 9, 1, 4, 7, 29):
            with self.subTest(stale_after=newer):
                m = self.machine(3)
                self.put_event(m, 1, LAST | 1, 10, 21)
                self.put_event(m, 2, LAST | newer, 10, 29)
                self.check_owner(m, 2)

    def test_trade_names_outgoing_club_and_wraps_in_both_scan_directions(self):
        for start in (0, 19, 597, 598, 599):
            for partner in ('player', 'pick'):
                for target_row in ((0, 1) if partner == 'player' else (0,)):
                    with self.subTest(start=start, partner=partner, target_row=target_row):
                        m = self.machine((start + 2) % 600)
                        pick = (2 << 5) | (3 << 21)
                        rows = [(7, 10, 2), (7 | (pick if partner == 'pick' else 0),
                                None if partner == 'pick' else 14, 21)]
                        if target_row:
                            rows.reverse()
                        for i, (packed, player, club) in enumerate(rows):
                            self.put_event(m, (start + i) % 600, packed | (LAST if i else 0), player, club)
                        self.check_owner(m, 21)

    def test_ambiguous_stale_invalid_and_overwritten_groups_keep_first_owner(self):
        trade_cases = {
            'single side': [(LAST | 7, 10, 2)], 'no end marker': [(7, 10, 2), (7, 11, 21)],
            'three clubs': [(7, 10, 2), (7, 11, 5), (LAST | 7, 12, 21)],
            'repeated player': [(7, 10, 2), (LAST | 7, 10, 21)],
            'bad pick': [(7, 10, 2), (LAST | 7, None, 21)],
            'pick before player': [(7 | (2 << 5), None, 21), (LAST | 7, 10, 2)],
            'invalid reference or actor': [(7, 10, 2), (LAST | 7, 11, None)],
            'display actor': [(7, 10, 32), (LAST | 7, 11, 21)],
            'player with pick arguments': [(7 | (1 << 5), 10, 2), (LAST | 7, 11, 21)],
            'no acquiring claimant': [(7, 10, 2), (LAST | 7, 11, 29)],
            'retired or cleared row': [(0x80000000, 10, 21)],
            'other identity': [(7, 12, 2), (LAST | 7, 13, 21)],
            'invalid singleton': [(1, 10, 21)],
            'non-franchise singleton': [(LAST | 4, 10, 32)],
            'no retained event': [],
        }
        for title, rows in trade_cases.items():
            with self.subTest(case=title):
                m = self.machine(10 + len(rows))
                for i, vals in enumerate(rows):
                    self.put_event(m, 10 + i, *vals)
                self.check_owner(m, 2)
        m = self.machine(10)
        self.put_event(m, 10, 7, 10, 2)
        self.put_event(m, 11, LAST | 7, 11, 21)
        self.check_owner(m, 2)  # Oldest physical row can be the tail of an overwritten group.
        m = self.machine(601)
        self.put_event(m, 0, LAST | 1, 10, 21)
        self.check_owner(m, 2)

    def test_full_native_trade_and_impossible_thirteenth_or_fourth_same_side_item(self):
        players = [(7, p, club) for p, club in zip((10, 11, 12, 13, 14, 15), (2, 21) * 3)]
        picks = [(7 | (round_id << 5) | (15 << 21), None, club)
                 for round_id, club in zip((1, 2, 3, 4, 5, 63), (2, 21) * 3)]
        for rows, expected in ((players + picks, 21), (players + picks + [picks[0]], 2),
                               (players[:1] + [(7, p, 21) for p in range(11, 15)], 2)):
            with self.subTest(length=len(rows)):
                start = 596
                m = self.machine((start + len(rows)) % 600)
                for i, (packed, player, club) in enumerate(rows):
                    last = LAST if i == len(rows) - 1 else 0
                    self.put_event(m, (start + i) % 600, packed | last, player, club)
                self.check_owner(m, expected)

    def test_newest_of_adjacent_trades_and_reused_player_pointer_after_a_clear(self):
        # Two real boundaries, separate acquiring clubs. The intervening high bit is essential.
        for old, new in ((2, 21), (21, 2)):
            with self.subTest(latest=new):
                m = self.machine(2)
                for slot, row in zip((598, 599, 0, 1), (
                        (7, 10, 5), (7 | LAST, 14, old), (7, 10, old), (7 | LAST, 16, new))):
                    self.put_event(m, slot, *row)
                self.check_owner(m, new)
        m = self.machine(2)
        self.put_event(m, 0, 1 | LAST, 10, 21)
        self.put_event(m, 1, LAST, 10, 2)  # Retail clears the kind but leaves both old pointers.
        self.check_owner(m, 2)

    def test_latest_retained_acquisition_can_predate_the_two_week_markers(self):
        m = self.machine(500)
        m.word(0xE3F064, 470)
        m.word(0xE3F068, 450)
        self.put_event(m, 130, 1 | LAST, 10, 21)
        self.put_event(m, 482, 10 | LAST, 10, 2)
        self.check_owner(m, 21)

    def test_primary_index_does_not_identify_the_same_numbered_secondary_record(self):
        m = LoadedLeague()
        m.set_club(2, [8, 5001])
        m.set_club(21, [5001, 9])
        m.word(CURSOR, 1)
        self.put_event(m, 0, 1 | LAST, 1, 21)
        m.repair()
        self.assertEqual(m.lists(2)[0], [8, 5001])
        self.assertEqual(m.lists(21)[0], [9])

    def test_clean_rosters_do_not_read_the_ledger_or_change_any_ownership_data(self):
        from unicorn import UC_HOOK_MEM_READ

        m = LoadedLeague()
        m.set_club(2, [10, 11])
        m.set_club(21, [12, 13])
        self.put_event(m, 598, 1 | LAST, 10, 21)
        m.word(CURSOR, 599)
        before = m.snapshot()
        reads = []
        m.cpu.hook_add(UC_HOOK_MEM_READ, lambda _u, _op, address, *_rest: reads.append(address),
                       begin=CURSOR, end=EVENTS + 600 * 12 - 1)
        m.repair()
        self.assertEqual(reads, [])
        self.assertEqual(m.snapshot(), before)

    def test_reversed_owner_stably_reseats_roles_and_seals_a_v2_reserve_overflow(self):
        m = self.machine(1)
        m.set_club(2, [10, *range(450, 502)], list(range(200, 216)), version=2)
        m.put(m.club(2)+0x194, bytes([0, 1, 2, 6, 52, 255]))
        self.put_event(m, 0, LAST | 1, 10, 21)
        m.repair()
        self.assertEqual(m.lists(2), (list(range(450, 502)), list(range(200, 216))))
        self.assertTrue(m.block_crc())
        self.assertEqual(m.read(m.club(2)+0x194, 6), bytes([255, 0, 1, 5, 51, 255]))
        self.assertEqual(m.lists(21)[0], [121, 10, 221])


if __name__ == '__main__':
    unittest.main()
