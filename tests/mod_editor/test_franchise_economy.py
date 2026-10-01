"""PROVED OFFLINE: byte guards, import refusal and native economic primitives.

Synthetic player cases test behavior, not real NFL contracts or UI coverage.
The full native season probe is a separate, bounded command.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tools.franchise_economy.contracts import fit_schedule, charges, FIELDS
from tools.franchise_economy.import_contracts import cap_schedule, millions, normalize
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes, retail_roster, HAVE_UC

ROOT = Path(__file__).resolve().parents[2]


class ImportTests(unittest.TestCase):
    def test_millions_not_dollars_and_total_row_not_a_season(self):
        self.assertEqual(millions('1.005'), 1005000)
        row = {'season_history': [{'year': '2026', 'base_salary': 1.005, 'cap_number': 2.5},
                                  {'year': '2027', 'base_salary': 1.05, 'cap_number': 3},
                                  {'year': '2028', 'base_salary': 0, 'cap_number': 1},
                                  {'year': 'Total', 'base_salary': 2.055, 'cap_number': 6.5}]}
        schedule, excluded = cap_schedule(row)
        self.assertEqual(schedule, [2500000, 3000000])
        self.assertEqual(len(excluded), 2)

    def test_missing_schedule_is_not_replaced_with_apy(self):
        for row in ({'apy': 30}, {'season_history': [{'year': 2027, 'base_salary': 1, 'cap_number': 2}]}):
            with self.assertRaises(ValueError):
                cap_schedule(row)
        for bad in (float('nan'), None, -1):
            with self.assertRaises(ValueError):
                millions(bad)

    def test_consecutive_years_and_duplicates_are_required(self):
        for years in ((2026, 2028), (2026, 2026)):
            with self.assertRaises(ValueError):
                cap_schedule({'season_history': [{'year': y, 'base_salary': 1, 'cap_number': 2} for y in years]})
        self.assertEqual(normalize('A.J. Brown Jr.'), normalize('AJ Brown'))

    def test_fits_only_contract_fields_and_reports_loss(self):
        fit = fit_schedule([885000, 930000, 975000, 1020000])
        self.assertEqual(set(fit['fields']), FIELDS)
        self.assertEqual(fit['represented_cap_dollars'], [v * 4000 for v in charges(fit['fields'])])
        self.assertEqual(fit['errors_dollars'], [a - b for a, b in zip(fit['represented_cap_dollars'], fit['source_cap_dollars'])])
        with self.assertRaises(ValueError):
            fit_schedule([10**12])
        with self.assertRaises(ValueError):
            fit_schedule([1] * 16)

    def test_opening_priority_keeps_today_within_native_rounding(self):
        fit = fit_schedule([44228000, 56148000, 62364000, 89189000, 82840000],
                           opening_priority=True)
        self.assertLessEqual(abs(fit['errors_dollars'][0]), 20000)
        self.assertNotEqual(fit['errors_dollars'][1:], [0] * 4)

    def test_pinned_conversion_refuses_unreviewed_rows(self):
        import tempfile
        from tools.franchise_economy.import_contracts import read_rows
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'contracts.json'
            p.write_text('{"meta": {}, "rows": []}')
            with self.assertRaisesRegex(ValueError, 'reviewed September 24'):
                read_rows(p)

    def test_build_option_is_off_in_every_preset(self):
        from mod_editor.core.mod_build import BuildPlan, PRESETS, apply_preset
        self.assertFalse(BuildPlan('s', 't').franchise_economy)
        for key in PRESETS:
            self.assertFalse(apply_preset(BuildPlan('s', 't', franchise_economy=True), key).franchise_economy, key)
        self.assertTrue(BuildPlan('s', 't', franchise_economy=True).wants_xbe_patch)
        from mod_editor.core import nfl2k5_build_settings as settings
        saved = settings.from_plan(BuildPlan('s', 't', franchise_economy=True))
        self.assertTrue(settings.to_plan(saved, 's2', 't2').franchise_economy)


@unittest.skipUnless(HAVE_UC, 'Unicorn is not installed')
class NativeEconomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched, cls.receipt = economy.apply(cls.retail)
        cls.m = Machine(cls.patched, trace_writes=False)
        cls.m.load_retail_roster(retail_roster())
        cls.m.seed(12345)
        for a, v in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 5), (0xE60010, 5)):
            cls.m.put(a, v)
        cls.m.call(0x13EE10, budget=150_000_000)
        cls.p = cls.m.ARENA + 0x190000
        cls.m.leaf(0x14E540, lambda: cls.m.ret(1), reason='user confirmation only; CPU trade decision stays native')
        cls.m.leaf(0x14E520, lambda: cls.m.ret(), reason='informational rejection display only')

    def player(self, *, pos=0, pro=3, rating=85, value=1000, years=4, bonus=0, kind=2):
        b = bytearray(84)
        b[8] = 4
        struct.pack_into('<H', b, 10, value)
        b[0x24:0x28] = bytes((years, pro, kind | bonus << 4, years))
        b[0x35] = pos
        b[0x38:] = bytes([rating] * (84 - 0x38))
        self.m.uc.mem_write(self.p, bytes(b))
        self.m.put(0xE3C278, economy.GAME_CAP)
        self.m.put(0xE576B8, 0)
        return self.p

    def value(self, **kwargs):
        p = self.player(**kwargs)
        value = self.m.call(0x2BD440, ecx=p, args=(1, 1, kwargs.get('years', 4)))
        self.assertEqual(self.m.reg('ESP'), self.m.STACK + 16)
        for name, expected in (('EBX', 0x11111111), ('ESI', 0x22222222), ('EDI', 0x33333333), ('EBP', 0x44444444)):
            self.assertEqual(self.m.reg(name), expected)
        return value

    def test_guards_are_atomic_and_idempotent(self):
        self.assertEqual(economy.status(self.retail), 'retail')
        self.assertEqual(economy.status(self.patched), 'applied')
        self.assertEqual(economy.apply(self.patched)[0], self.patched)
        image = XbeImage(self.retail)
        for site in economy.sites():
            foreign = bytearray(self.retail)
            foreign[image.offset(site.va)] ^= 1
            with self.assertRaises(economy.EconomyError):
                economy.apply(bytes(foreign))
        mixed = bytearray(self.retail)
        site = economy.sites()[0]
        offset = image.offset(site.va)
        mixed[offset:offset + len(site.patched)] = site.patched
        self.assertEqual(economy.status(bytes(mixed)), 'foreign')
        with self.assertRaises(economy.EconomyError):
            economy.apply(bytes(mixed))

    def test_section_digests_and_default_build_writer(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        from mod_editor.core import nfl2k5_throw_tuning as tt
        for section in _sections(self.patched):
            if section.index in self.receipt['sections_repinned']:
                self.assertEqual(self.patched[section.header_offset + 36:section.header_offset + 56], section_digest(self.patched, section))
        built, receipt = tt._apply_all(self.retail, None, False, draft_ai=True, progression=True, franchise_economy=True)
        self.assertEqual(tt.draft_ai_patch.status(built), "applied")
        self.assertEqual(tt.progression_patch.status(built), "applied")
        self.assertEqual(economy.status(built), 'applied')
        self.assertIn('franchise_economy_patch', receipt)

    def test_complete_build_copy_reports_the_option(self):
        import tempfile
        from mod_editor.core import mod_build
        from tests.nfl2k5_supersim_draft_fixture import XBE
        with tempfile.TemporaryDirectory(prefix='fc-build-test-') as directory:
            target = Path(directory) / 'economy.xbe'
            receipt = mod_build.build(mod_build.BuildPlan(str(XBE), str(target), franchise_economy=True))
            self.assertEqual(economy.status(target.read_bytes()), 'applied')
            self.assertEqual(receipt['result']['franchise_economy'], 'applied')
            self.assertEqual(hashlib.sha256(XBE.read_bytes()).hexdigest(), hashlib.sha256(self.retail).hexdigest())

    def test_position_age_and_surplus_direction_without_wrap(self):
        qb = self.value(pos=0)
        rb = self.value(pos=7)
        self.assertGreater(qb, rb)
        self.assertGreater(qb, self.value(pos=0, pro=20))
        self.assertGreater(self.value(pos=0, value=500), self.value(pos=0, value=15000))
        self.assertLessEqual(self.value(pos=0, rating=127, value=1, years=7), 60000)
        self.assertEqual(self.value(pos=255), 0)

    def test_native_current_charge_matches_host_curve_port(self):
        for kind in range(8):
            for bonus in range(8):
                self.player(value=1450, years=4, kind=kind, bonus=bonus)
                f = dict(contract_value=1450, contract_length=4, contract_remaining=4,
                         contract_type=kind, contract_bonus=bonus)
                for i, expected in enumerate(charges(f)):
                    self.m.uc.mem_write(self.p + 0x24, bytes((4 - i,)))
                    base = self.m.call(0xE6380, ecx=self.p)
                    annual_bonus = self.m.call(0xE6020, ecx=1450, edx=bonus, args=(4,))
                    self.assertEqual(base + annual_bonus, expected)

    def test_eight_year_native_contract_is_not_truncated(self):
        fit = fit_schedule([34653888, 90353892, 85839000, 82939000,
                            74640000, 65750000, 68000000, 70000000], opening_priority=True)
        f = fit['fields']
        p = self.player(value=f['contract_value'], years=8, kind=f['contract_type'],
                        bonus=f['contract_bonus'])
        for year, expected in enumerate(charges(f)):
            self.m.uc.mem_write(p + 0x24, bytes((8 - year,)))
            salary = self.m.call(0xe6380, ecx=p)
            bonus = self.m.call(0xe6020, ecx=f['contract_value'], edx=f['contract_bonus'], args=(8,))
            self.assertEqual(salary + bonus, expected)

    def test_shared_money_formatter_and_all_direct_calls(self):
        from tools.franchise_economy.money_probe import census, wide
        self.assertEqual(len(census(self.retail)['direct_calls']), 51)
        out = self.m.ARENA + 0x180000
        for amount, expected in ((75300, '301.20m'), (13750, '55.00m'), (249, '996k'),
                                 (250, '1.00m'), (-1, '-4k'), (-75300, '-301.20m'),
                                 (655350, '2621.40m')):
            self.m.uc.mem_write(out, b'\xa5' * 128)
            self.m.call(0x31e580, ecx=amount, edx=out)
            self.assertEqual(wide(self.m, out), expected)
            self.assertEqual(bytes(self.m.uc.mem_read(out + 64, 64)), b'\xa5' * 64)
            self.assertEqual(self.m.reg('ESP'), self.m.STACK + 4)
            for name, value in (('EBX',0x11111111), ('ESI',0x22222222),
                                ('EDI',0x33333333), ('EBP',0x44444444)):
                self.assertEqual(self.m.reg(name), value)

    def test_native_ir_return_then_reconciliation_keeps_gate_unchanged(self):
        # DESIGN: bounded IR fixture using retail player records; no real NFL
        # injury event is claimed. Rollover proof uses the full modern season.
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), self.patched)
        team, donor = m.team_base, m.team_base + 500
        m.put(0xe3c278, 200000)  # isolate the actual roster-capacity failure
        for slot in range(3):
            player = m.get(donor)
            m.call(0xc3eb0, ecx=donor, edx=player)
            m.put(0xe421e0 + slot * 4, player)
        m.call(0x246f90)
        self.assertEqual(m.uc.mem_read(team + 0x11c, 1)[0], 56)
        self.assertEqual(m.call(0x2bf950, ecx=team), 0)
        free_before = m.get(m.root + 0x38)
        m.call(0x2bfbe0, ecx=team, budget=10000000)
        self.assertEqual(m.uc.mem_read(team + 0x11c, 1)[0], 54)
        self.assertEqual(m.call(0x2bf950, ecx=team), 1)
        self.assertEqual(m.get(m.root + 0x38), free_before + 2)

    def test_generated_deals_respect_minimum_and_preserve_identity(self):
        floors = json.loads((ROOT / 'data/nfl2k5_franchise_economy.json').read_text())['minimums']['dollars']
        for pro in range(8):
            self.player(pro=pro, rating=1)
            before = bytes(self.m.uc.mem_read(self.p, 84))
            self.m.call(0x3228A0, ecx=self.p, edx=1, args=(7, 0))
            after = bytes(self.m.uc.mem_read(self.p, 84))
            self.assertEqual(self.m.reg('ESP'), self.m.STACK + 12)
            self.assertGreaterEqual(self.m.call(0xE6380, ecx=self.p) * 4000, floors[pro])
            self.assertTrue(1 <= after[0x24] <= 7)
            allowed = {10, 11, 0x24, 0x26, 0x27}
            self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))

    def test_rookie_four_year_terms_and_cap_growth(self):
        for ordinal in (0, 31, 32, 100, 223):
            self.player()
            self.m.call(0x322980, ecx=self.p, edx=ordinal, args=(1,))
            b = bytes(self.m.uc.mem_read(self.p, 84))
            value = struct.unpack_from('<H', b, 10)[0]
            self.assertEqual((b[0x24] & 15, b[0x27] & 15), (4, 4))
            self.assertEqual(self.m.reg('ESP'), self.m.STACK + 8)
            self.m.put(0xE3C278, int(economy.GAME_CAP * economy.CAP_GROWTH))
            self.m.call(0x322980, ecx=self.p, edx=ordinal, args=(1,))
            self.assertGreater(struct.unpack('<H', self.m.uc.mem_read(self.p + 10, 2))[0], value)

    def test_every_draft_slot_and_future_discount(self):
        chart = json.loads((ROOT / 'data/nfl2k5_franchise_economy.json').read_text())['draft_chart']['values']
        self.m.put(0xE576A4, 5)
        for index, value in enumerate(chart):
            pick = (index // 32 + 1) | (index % 32 << 6)
            self.m.uc.mem_write(self.p, struct.pack('<H', pick))
            self.assertEqual(self.m.call(0x2BAB20, args=(self.p,)), value * 2)
        self.m.uc.mem_write(self.p, struct.pack('<H', 1 | 0x1000))
        self.assertEqual(self.m.call(0x2BAB20, args=(self.p,)), chart[15] * 2 * 3 // 4)
        self.m.uc.mem_write(self.p, struct.pack('<H', 63))
        self.assertEqual(self.m.call(0x2BAB20, args=(self.p,)), 0)

    def test_cap_penalty_saturation_blocks_spending(self):
        team = self.m.team_base
        self.m.call(0xC4D30, ecx=team, edx=1)
        self.player(value=65535, years=7, bonus=7)
        self.m.uc.mem_write(team + 0x19C, struct.pack('<H', 65000))
        self.m.call(0x13ED30, ecx=team, edx=self.p, args=(0,))
        self.assertEqual(struct.unpack('<H', self.m.uc.mem_read(team + 0x19C, 2))[0], 65535)
        self.assertEqual(self.m.call(0x13ECA0, ecx=team, edx=1, args=(0,)), 0)
        self.m.uc.mem_write(team + 0x19C, b'\0\0')
        self.assertEqual(self.m.call(0x13ECA0, ecx=team, edx=1, args=(0,)), economy.GAME_CAP)
        self.assertEqual(self.m.call(0x13ECA0, ecx=team, edx=1, args=(7,)), 0)

    def test_resigning_and_free_agency_execute_and_cap_rejects(self):
        from tools.franchise_economy.probe import start
        from mod_editor.core import nfl2k5_roster_records as rr
        body = retail_roster()
        m = start(body, self.patched)
        doc = rr.RosterDocument(body)
        menu, team = m.ARENA + 0x1A0000, m.team_base
        offer, result = menu + 0x400, menu + 0x430
        m.leaf(0x14E520, lambda: m.ret(), reason='informational offer result only')
        m.put(0xE576A4, 3)
        for slot in range(m.uc.mem_read(team + 0x11C, 1)[0]):
            m.uc.mem_write(m.get(team + slot * 4) + 10, b'\0\0')
        m.call(0xC3F00, ecx=team)
        player = m.get(team)
        free_agent = m.ARENA + 0x300 + doc.free_agents[0]
        for p, kind, value, years, expected, count in (
                (player, 1, 60000, 1, 0, 53),
                (player, 1, 10000, 4, 1, 53),
                (free_agent, 3, 10000, 4, 1, 54)):
            word = (kind << 26) | (2 << 29) | (1 << 24) | (years << 16)
            m.uc.mem_write(offer, struct.pack('<IIIHH', p, team, word, value, 0))
            # force=0: native player-acceptance and cap checks both execute.
            self.assertEqual(m.call(0x323D80, ecx=offer, edx=result, args=(0, menu), budget=10000000), expected)
            self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], count)
            if expected:
                self.assertEqual(struct.unpack('<H', m.uc.mem_read(p + 10, 2))[0], value)
                self.assertEqual(m.uc.mem_read(p + 0x24, 1)[0] & 15, years)
        self.assertEqual(m.get(team + 0x124), 50000)

    def test_actual_native_acceptance_not_noninteractive_bypass(self):
        m, trade = self.m, self.m.ARENA + 0x1A0000
        m.put(0xE576A4, 5)
        for team in range(32):
            m.put(m.team_base + team * 500 + 0x124, 10000)
        for offered, requested, expected in ((1, 7, 1), (7, 1, 0), (1, 1, 0), (1, 2, 1)):
            m.uc.mem_write(trade, bytes(0x100))
            m.put(trade + 8, m.team_base)
            m.put(trade + 0x20, m.team_base + 500)
            m.uc.mem_write(trade + 0x18, struct.pack('<H', offered))
            m.uc.mem_write(trade + 0x30, struct.pack('<H', requested))
            self.assertEqual(m.call(0x2BC380, args=(1,), ebx=trade, budget=5_000_000), expected)

    def test_cpu_signing_preserves_cap_roster_and_new_offer_terms(self):
        from tools.franchise_economy.probe import start
        from mod_editor.core import nfl2k5_roster_records as rr
        m = start(retail_roster(), self.patched)
        team = m.team_base
        m.put(0xE576A4, 3)
        m.call(0xC4D30, ecx=team, edx=0)
        for slot in range(m.uc.mem_read(team + 0x11C, 1)[0]):
            m.uc.mem_write(m.get(team + slot * 4) + 10, b'\0\0')
        m.call(0xC3F00, ecx=team)
        doc = rr.RosterDocument(retail_roster())
        p = m.ARENA + 0x300 + doc.free_agents[0]
        offer, result = m.ARENA + 0x1A0400, m.ARENA + 0x1A0430
        m.uc.mem_write(p + 0x26, b'\x75')  # Expired, unrelated prior curve and bonus.
        word = (3 << 26) | (2 << 29) | (1 << 24) | (4 << 16) | (4 << 8) | 2
        m.uc.mem_write(offer, struct.pack('<IIIHH', p, team, word, 10000, 0))
        response = m.call(0x3232A0, ecx=offer, edx=result, args=(1,))
        self.assertGreater(m.get(result), 80)
        self.assertGreater(4, 4 - response)
        before = bytes(m.uc.mem_read(p, 84))
        free_before = m.get(m.root + 0x38)
        m.put(0xE3C278, 1)
        # Both entry points must reject before removing a free agent or writing a deal.
        self.assertEqual(m.call(0x322BB0, args=(team, 0, 65535, 0)), 0)
        self.assertEqual(m.reg('ESP'), m.STACK + 20)
        m.call(0x323B30, eax=offer, budget=10000000)
        self.assertEqual(bytes(m.uc.mem_read(p, 84)), before)
        self.assertEqual(m.get(m.root + 0x38), free_before)
        self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], 53)
        m.put(0xE3C278, economy.GAME_CAP)
        # Native consent is untouched. Successful timed acceptance copies all terms.
        m.call(0x323B30, eax=offer, budget=10000000)
        self.assertEqual(m.uc.mem_read(p + 0x26, 1)[0], 0x22)
        self.assertEqual(m.uc.mem_read(p + 0x24, 1)[0] & 15, 4)
        self.assertEqual(m.get(team + 0x124), 25000)
        self.assertEqual(m.get(m.root + 0x38), free_before - 1)
        self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], 54)
        self.assertEqual(m.call(0x2BF950, ecx=team), 1)
        self.assertEqual(m.call(0x322BB0, args=(team, 0, 65535, 0)), 0)
        self.assertEqual(m.reg('ESP'), m.STACK + 20)
        for name, expected in (('EBX', 0x11111111), ('ESI', 0x22222222),
                               ('EDI', 0x33333333), ('EBP', 0x44444444)):
            self.assertEqual(m.reg(name), expected)

    def test_automatic_cpu_renewal_checks_room_before_mutation(self):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), self.patched)
        team, p = m.team_base, m.get(m.team_base)
        before = bytes(m.uc.mem_read(p, 84))
        payroll = m.get(team + 0x124)
        m.put(0xE3C278, 1)
        m.call(0x322EB0, esi=p, edi=team)
        self.assertEqual(bytes(m.uc.mem_read(p, 84)), before)
        self.assertEqual(m.get(team + 0x124), payroll)
        self.assertEqual(m.reg('ESP'), m.STACK + 4)
        m.put(0xE3C278, 200000)
        m.call(0x322EB0, esi=p, edi=team)
        self.assertNotEqual(bytes(m.uc.mem_read(p, 84)), before)
        self.assertEqual(m.call(0x2BF950, ecx=team), 1)
        # Credit the old charge: a renewal can be affordable even when almost
        # no unallocated room remains. This is a contract-arithmetic fixture.
        m.uc.mem_write(p + 10, struct.pack('<H', 10000))
        m.uc.mem_write(p + 0x24, bytes(((m.uc.mem_read(p + 0x24, 1)[0] & 0xF0) | 4,)))
        m.uc.mem_write(p + 0x26, b'\x02')
        m.uc.mem_write(p + 0x27, bytes(((m.uc.mem_read(p + 0x27, 1)[0] & 0xF0) | 4,)))
        m.call(0xC3F00, ecx=team)
        payroll = m.get(team + 0x124)
        before = bytes(m.uc.mem_read(p, 84))
        m.put(0xE3C278, payroll + 10)
        m.call(0x322EB0, esi=p, edi=team)
        self.assertNotEqual(bytes(m.uc.mem_read(p, 84)), before)
        self.assertLessEqual(m.get(team + 0x124), payroll + 10)
        self.assertEqual(m.call(0x2BF950, ecx=team), 1)


if __name__ == '__main__':
    unittest.main()
