"""Slice 2 signed franchises cross between the Realistic and Retail executables (pos2/DESIGN.md section 6, test 5).

This is the slice 1 exchange (qb-system/slice1_signed_compat.py) on the repo's own native machine,
tests/nfl2k5_my_career_mode_fixture.Machine (the generic save, sign and cold-load fixture on top of
tests/nfl2k5_my_career_fixture.Machine), with no file from outside the repo but the private inputs below.

Both executables are made here by the Studio route from the private reviewed standard executable:
Realistic = nfl2k5_sim_qb_injuries.apply(source, 'realistic'), Retail = apply(Realistic, 'retail').
Two signed franchises cross in both directions:

- the authenticated opening of 2026 (cpu-sim/d16-catalog-128-2026, regular season week 0, 119 IR entries);
- the same franchise after regular-season week 1 simulated natively on Realistic (the game's own weekly scheduler
  0x247D40; only the progress display and informational dialogs are substituted, as in
  tools/franchise_sim/season_probe.py). That save must hold at least one slice 2 injury, meaning an injury commit
  at the game's 0x10285F whose selector frame returns inside the bank's positions piece, to a player who was healthy
  at the opening and is still hurt when the week is saved; and at least one IR entry.

In each case Realistic writes and signs the franchise; Retail cold-loads it and all 4,096 player records (the health
words +0x20, +0x24 and +0x28 named separately), the IR entries, the 32 club rows and the practice-squad block equal
the writer's; Retail writes and signs it again; Realistic cold-loads Retail's save, compares the same state, and
writes it a last time byte for byte equal to Retail's write, signature included. Every signature is checked with
nfl2k5_roster_records.verify_extra. Retail's write equals Realistic's own write at the opening; after the week it
differs only in the transaction-ledger boundary cursors (front office +0x3324), which the simulating machine keeps
and a cold load restarts at 0 on either executable.

Slice 3 (pos3/DESIGN.md section 6, test 5): the same exchange after native regular-season weeks whose save holds a
slice 3 injury (receiver, tight end, fullback, defensive tackle, linebacker, cornerback or safety) on each side of the
ball, still hurt when saved, and one in slot 28 (the second free safety). The slot 28 condition depends on the frozen
constants; until a week range that reaches it is chosen after calibration, that one condition skips with the counts
(TODO for the build lead, see SLICE3_WEEKS).

Private inputs come from /home/noah/2k-worktrees/.b77-scratch/b81/env.sh: NFL2K5_B81_REVIEWED_TEST_DISC (the
standard executable, 98dd7329) and NFL2K5_B81_OWNERSHIP_FIXTURES (roster d5e02a52 and the signed opening 8bc786af).
The test skips when they are absent and fails when they are present but differ from their pins.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_franchise_save as saves
from mod_editor.core import nfl2k5_injured_reserve as reserve
from mod_editor.core import nfl2k5_roster_records as records
from mod_editor.core import nfl2k5_sim_qb_injuries as medical
from mod_editor.core import nfl2k5_sim_qb_injuries_code as code
from mod_editor.core import nfl2k5_xbe_space as space
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

SOURCE_SHA256 = '98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e'
ROSTER_SHA256 = 'd5e02a5237424ba3fb3f53ec0b45d32efc8f0324fb24cb7d4a2ac814707fbc68'
OPENING_SHA256 = '8bc786af9372fc5ddeb45ab2811db9fe5da774894ceff017a1744786f037fb2c'
ROSTER = 'cpu-sim/verified-complete-v010-128.body'
OPENING = 'cpu-sim/d16-catalog-128-2026/signed'

BANK_VA = 0x1524000                       # the quarterback bank's fixed address (DESIGN section 4)
PLAYERS_ROOT = 0xB72918                  # league root: player count, pool, ..., clubs at +0x1C
STATE = {'stage': 0xE576A4, 'week': 0xE576B4, 'year': 0xE576B8}
WEEKLY_SCHEDULER = 0x247D40               # one ordinary franchise week (tools/franchise_sim/season_probe.py)
COMMIT_PC = 0x10285F                      # the game's injury commit (health write and substitution)
SELECTOR_RETURN = 0x34                    # [ESP+0x34] at COMMIT_PC: return address of the selector frame
SIDE = 0x14                               # [ESP+0x14] at COMMIT_PC: the match side; EBP is the player's match copy
RECORD = 84
# Slice 3: classes 5 to 11 of code.POSITION_CLASSES are new; these are read from the defensive side.
DEFENSIVE_CLASSES = {'end', 'defensive_tackle', 'linebacker', 'cornerback', 'safety'}
SECOND_FREE_SAFETY = 28
SLICE3_WEEKS = 4      # TODO(build lead): set after the freeze to a range in which the seed's save holds a slot 28 injury


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def healthy(record):
    """The positions piece's own test (DESIGN section 2, step 3): no injured bit, weeks or status."""
    return struct.unpack_from('<I', record, 0x20)[0] & 0xBFC00000 == 0 and record[0x27] & 0x70 == 0


def census(machine, executable):
    """Everything a franchise save carries about players, clubs and injured reserve, read from game memory."""
    read = lambda at, size: bytes(machine.uc.mem_read(at, size))
    root = machine.get(PLAYERS_ROOT)
    count, pool, teams = machine.get(root), machine.get(root + 4), machine.get(root + 0x1C)
    players = read(pool, count * RECORD)
    store = reserve.store_va(executable)
    entries = []
    for club in range(32):
        at = store + 64 + 164 * club
        size = read(at, 1)[0]
        assert size <= 20, (club, size)
        for slot in range(size):
            pointer, status = struct.unpack('<II', read(at + 4 + 8 * slot, 8))
            index, rest = divmod(pointer - pool, RECORD)
            assert not rest and 0 <= index < count, (club, slot, hex(pointer))
            entries.append((club, index, status))
    return {
        'state': {name: machine.get(address) for name, address in STATE.items()},
        'count': count,
        'players': players,
        'health': [struct.unpack_from('<3I', players, RECORD * i + 0x20) for i in range(count)],
        'ir': entries,
        'clubs': [read(teams + 500 * club, 500) for club in range(32)],
        'practice_block': read(root + machine.get(0xB72808) - 0x400, 352),
    }


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the native franchise save, load and week')
class SignedSlice2Exchange(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import mod_build
        from tests.nfl2k5_my_career_fixture import XBE as RETAIL_XBE

        disc = os.environ.get('NFL2K5_B81_REVIEWED_TEST_DISC')
        fixtures = os.environ.get('NFL2K5_B81_OWNERSHIP_FIXTURES')
        if not disc or not fixtures:
            raise unittest.SkipTest('private standard executable, roster and signed opening are absent (env.sh)')
        root = Path(fixtures)
        needed = (Path(disc), root / ROSTER, root / OPENING / 'SAVEGAME.DAT', root / OPENING / 'EXTRA', RETAIL_XBE)
        missing = [str(path) for path in needed if not path.is_file()]
        if missing:
            raise unittest.SkipTest(f'private inputs are absent: {missing}')
        cls.source = mod_build._xbe_bytes(Path(disc))
        cls.roster = (root / ROSTER).read_bytes()
        cls.opening = (root / OPENING / 'SAVEGAME.DAT').read_bytes()
        pins = {'source': (sha256(cls.source), SOURCE_SHA256), 'roster': (sha256(cls.roster), ROSTER_SHA256),
                'opening': (sha256(cls.opening), OPENING_SHA256)}
        wrong = {name: got for name, (got, pin) in pins.items() if got != pin}
        if wrong:
            raise AssertionError(f'private inputs differ from their pins: {wrong}')
        if not records.verify_extra(cls.opening, (root / OPENING / 'EXTRA').read_bytes()):
            raise AssertionError('the opening franchise is not signed by the game')
        # The branch's own Studio route, on bytes read from the private disc; nothing is patched by hand.
        cls.realistic, _ = medical.apply(cls.source, 'realistic')
        cls.retail, _ = medical.apply(cls.realistic, 'retail')
        cls.bank = next(row['va'] for row in space.layout(cls.realistic)['allocations']
                        if row['owner'] == medical.OWNER and row['kind'] == 'code')

    # -- native machine ---------------------------------------------------------------------------------------------

    def boot(self, executable, save):
        """Cold-load a signed franchise as qb-system/slice1_signed_compat.py did (frontend, game PRNGs, native load)."""
        from tests.nfl2k5_my_career_mode_fixture import Machine

        machine = Machine(executable)
        machine.frontend(self.roster)
        machine.call(0x77D20, stop=0x77D45, budget=2_000_000)
        machine.live_league_prng()
        for generator in (0xB12680, 0xE5FCA0):
            machine.call(0x48BE0, ecx=generator, edx=2501)
        machine.put(0xE5FF80, 4)
        machine.native_load(save, requested=False)
        machine.loaded_menu()
        return machine

    def sign(self, machine):
        raw = machine.native_save(budget=500_000_000)
        self.assertTrue(raw, 'the native save produced no franchise')
        extra = machine.native_signature(raw)
        self.assertEqual(len(extra or b''), 20)
        self.assertTrue(records.verify_extra(raw, extra), 'the native signature does not verify')
        return raw, extra

    def simulate_week(self, machine):
        """One native franchise week; return the master index of every player hurt by a positions-piece commit."""
        commits, other = self.simulate_weeks(machine, 1)
        return [index for index, _, _ in commits], other

    def simulate_weeks(self, machine, weeks, *, enough=None):
        """Native franchise weeks (stop early once enough(commits) holds); every positions-piece commit as (master
        index, class index, lineup slot) and the selector return address of every other injury commit."""
        start, end = code.LABELS.get('positions'), code.LABELS.get('depth_hook')
        slice2, other = [], []

        def commit(*_):
            esp = machine.reg('ESP')
            back = machine.get(esp + SELECTOR_RETURN)
            if start is None or not self.bank + start <= back < self.bank + end:
                other.append(back)
                return
            # The match side holds the master club and, through its sheet, the parallel list of match copies.
            side = machine.get(esp + SIDE)
            master_club, copy_club = machine.get(side), machine.get(machine.get(side + 4))
            count = machine.uc.mem_read(master_club + 0x11C, 1)[0]
            copies = [machine.get(copy_club + 4 * i) for i in range(count)]
            copy = machine.reg('EBP')
            master = machine.get(master_club + 4 * copies.index(copy))
            same = bytes(machine.uc.mem_read(copy + 0x10, 8)) == bytes(machine.uc.mem_read(master + 0x10, 8))
            pool = machine.get(machine.get(PLAYERS_ROOT) + 4)
            klass = slot = None
            if 'pos_class' in code.LABELS:   # the piece sets both before it calls its copy of the selector
                klass = machine.get(self.bank + code.LABELS['pos_class'])
                slot = machine.get(self.bank + code.LABELS['victim_slot'])
            slice2.append(((master - pool) // RECORD if same else None, klass, slot))

        def decision(*_):
            raise RuntimeError(f'unexpected decision dialog from {machine.get(machine.reg("ESP")):#x}')

        machine.replace_stub(0x177990, lambda: machine.ret(pop=4))     # progress display
        machine.replace_stub(0x14E520, lambda: machine.ret())          # acknowledge an informational dialog
        machine.uc.hook_add(machine.u.UC_HOOK_CODE, decision, begin=0x14E440, end=0x14E440)
        machine.uc.hook_add(machine.u.UC_HOOK_CODE, commit, begin=COMMIT_PC, end=COMMIT_PC)
        machine.uc.ctl_flush_tb()
        for _ in range(weeks):
            machine.call(WEEKLY_SCHEDULER, ecx=machine.manager, budget=0)
            if enough is not None and enough(slice2):
                break
        self.assertNotIn(None, [index for index, _, _ in slice2], 'a positions commit hurt a match copy with no master')
        if 'pos_commits' in code.LABELS:
            classes = len(code.POSITION_CLASSES)
            counters = struct.unpack(f'<{classes}I', bytes(machine.uc.mem_read(self.bank + code.LABELS['pos_commits'],
                                                                                4 * classes)))
            self.assertEqual(sum(counters), len(slice2), 'hooked positions commits differ from the bank counters')
            for klass in range(classes):
                self.assertEqual(counters[klass], sum(1 for _, c, _ in slice2 if c == klass),
                                 f'class {code.POSITION_CLASSES[klass].name}: hooked commits differ from its counter')
        return slice2, other

    # -- comparison -------------------------------------------------------------------------------------------------

    def assertSameFranchise(self, expected, actual, label):
        self.assertEqual(actual['state'], expected['state'], label)
        self.assertEqual(actual['count'], 4096, label)
        self.assertEqual(actual['count'], expected['count'], label)
        changed = [i for i, (a, b) in enumerate(zip(expected['health'], actual['health'])) if a != b]
        self.assertEqual(changed, [], f'{label}: health words +0x20/+0x24/+0x28 differ for these players')
        changed = [i for i in range(expected['count'])
                   if expected['players'][RECORD * i:RECORD * (i + 1)] != actual['players'][RECORD * i:RECORD * (i + 1)]]
        self.assertEqual(changed, [], f'{label}: player records differ')
        self.assertEqual(actual['ir'], expected['ir'], f'{label}: IR entries differ')
        changed = [club for club in range(32) if expected['clubs'][club] != actual['clubs'][club]]
        self.assertEqual(changed, [], f'{label}: club rows differ')
        self.assertEqual(actual['practice_block'], expected['practice_block'], f'{label}: practice block differs')

    def exchange(self, written, expected, label):
        """Realistic's signed write -> Retail cold load and signed write -> Realistic cold load and signed write."""
        machine = self.boot(self.retail, written)
        try:
            self.assertSameFranchise(expected, census(machine, self.retail), f'{label}: Realistic save on Retail')
            by_retail = self.sign(machine)
        finally:
            machine.close()
        machine = self.boot(self.realistic, by_retail[0])
        try:
            self.assertSameFranchise(expected, census(machine, self.realistic), f'{label}: Retail save on Realistic')
            again = self.sign(machine)
        finally:
            machine.close()
        self.assertEqual(again, by_retail, f'{label}: Realistic re-wrote Retail\'s save differently')
        return by_retail

    # -- tests ------------------------------------------------------------------------------------------------------

    def test_studio_route_makes_the_two_executables(self):
        self.assertEqual(medical.read_settings(self.realistic), {
            'status': 'applied', 'mode': 'realistic', 'custom_rate': medical.REALISTIC_RATE / 1000,
            'revision': medical.REVISION, 'positions': True})
        self.assertEqual(medical.read_settings(self.retail)['mode'], 'retail')
        self.assertEqual(medical.apply(self.retail, 'realistic')[0], self.realistic)
        self.assertEqual(self.bank, BANK_VA)
        empty = next(row for row in space.layout(self.retail)['allocations']
                     if row['owner'] == medical.OWNER and row['kind'] == 'code')
        self.assertEqual(empty['va'], self.bank)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(XbeImage(self.retail).read(self.bank, empty['size']), b'\xcc' * empty['size'])

    def test_opening_franchise_crosses_both_ways(self):
        machine = self.boot(self.realistic, self.opening)
        try:
            opening = census(machine, self.realistic)
            written = self.sign(machine)
        finally:
            machine.close()
        self.assertEqual(opening['state'], {'stage': 8, 'week': 0, 'year': 0})
        self.assertTrue(opening['ir'], 'the opening franchise has no IR entry')
        by_retail = self.exchange(written[0], opening, 'opening')
        self.assertEqual(by_retail, written, 'opening: Retail wrote the franchise differently from Realistic')

    def test_week_one_franchise_with_a_slice_2_injury_crosses_both_ways(self):
        machine = self.boot(self.realistic, self.opening)
        try:
            opening = census(machine, self.realistic)
            victims, native = self.simulate_week(machine)
            week = census(machine, self.realistic)
            written = self.sign(machine)
        finally:
            machine.close()
        self.assertEqual(week['state'], {'stage': 8, 'week': 1, 'year': 0})
        record = lambda state, i: state['players'][RECORD * i:RECORD * (i + 1)]
        still_hurt = sorted({i for i in victims if not healthy(record(week, i))})
        self.assertTrue(still_hurt, f'no slice 2 injury is in the week 1 save ({len(victims)} slice 2 commits, '
                                    f'{len(native)} other injury commits)')
        for i in still_hurt:
            self.assertTrue(healthy(record(opening, i)), f'player {i} was already hurt at the opening')
        self.assertTrue(week['ir'], 'the week 1 franchise has no IR entry')
        by_retail = self.exchange(written[0], week, 'week 1')
        # The machine that simulated the week saves its transaction-ledger boundary cursor (0xE3F064); a cold load
        # starts it at 0 on both executables. Every other byte of Retail's write equals Realistic's week save.
        ledger = saves.FranchiseSave(written[0]).front_office_block + saves.F_LEDGER_BOUNDARIES
        self.assertEqual(len(by_retail[0]), len(written[0]))
        moved = [i for i, (a, b) in enumerate(zip(written[0], by_retail[0])) if a != b]
        self.assertEqual([i for i in moved if not ledger <= i < ledger + 8], [],
                         'week 1: Retail\'s write differs from Realistic\'s outside the ledger boundary cursors')

    def test_weeks_with_slice_3_injuries_on_both_sides_and_slot_28_cross_both_ways(self):
        names = [position.name for position in code.POSITION_CLASSES]
        self.assertEqual(len(names), 12, 'slice 3 has twelve position classes')
        machine = self.boot(self.realistic, self.opening)
        record = lambda state, i: state['players'][RECORD * i:RECORD * (i + 1)]
        try:
            opening = census(machine, self.realistic)
            hurt_at_opening = {i for i in range(opening['count']) if not healthy(record(opening, i))}
            new = lambda commits: [(i, names[c], slot) for i, c, slot in commits if c is not None and c >= 5
                                   and i not in hurt_at_opening]
            sides = lambda commits: {name in DEFENSIVE_CLASSES for _, name, _ in new(commits)}
            enough = lambda commits: sides(commits) == {False, True} and any(
                slot == SECOND_FREE_SAFETY for _, _, slot in new(commits))
            commits, native = self.simulate_weeks(machine, SLICE3_WEEKS, enough=enough)
            weeks = census(machine, self.realistic)
            written = self.sign(machine)
        finally:
            machine.close()
        still = [(i, name, slot) for i, name, slot in new(commits) if not healthy(record(weeks, i))]
        counts = f'{len(commits)} positions commits, {len(new(commits))} slice 3, {len(native)} other, ' \
                 f'{weeks["state"]["week"]} weeks: {sorted({name for _, name, _ in new(commits)})}'
        self.assertTrue(any(name not in DEFENSIVE_CLASSES for _, name, _ in still),
                        f'no offensive slice 3 injury is in the save ({counts})')
        self.assertTrue(any(name in DEFENSIVE_CLASSES for _, name, _ in still),
                        f'no defensive slice 3 injury is in the save ({counts})')
        self.assertTrue(weeks['ir'], 'the franchise has no IR entry')
        target = os.environ.get('NFL2K5_B81_POS_SIGNED_RECORD')   # optional evidence: what the save holds
        if target:
            Path(target).write_text(json.dumps({
                'weeks': weeks['state']['week'], 'positions_commits': len(commits), 'other_commits': len(native),
                'slice3_commits': new(commits), 'slice3_still_hurt_when_saved': still,
                'save_sha256': sha256(written[0])}, indent=1) + '\n', encoding='utf-8')
        by_retail = self.exchange(written[0], weeks, 'slice 3 weeks')
        ledger = saves.FranchiseSave(written[0]).front_office_block + saves.F_LEDGER_BOUNDARIES
        moved = [i for i, (a, b) in enumerate(zip(written[0], by_retail[0])) if a != b]
        self.assertEqual([i for i in moved if not ledger <= i < ledger + 8], [],
                         'slice 3 weeks: Retail\'s write differs from Realistic\'s outside the ledger boundary cursors')
        if not any(slot == SECOND_FREE_SAFETY for _, _, slot in still):
            self.skipTest(f'TODO(build lead): no slot 28 injury in the save within {SLICE3_WEEKS} weeks at these '
                          f'constants ({counts}); choose SLICE3_WEEKS after the freeze')
