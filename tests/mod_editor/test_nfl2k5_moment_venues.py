"""Native text reads for all 51 rows, plus modern-mode isolation and guards."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_moment_venues as v
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_espn25_rosters as er
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
if HAVE_UNICORN:
    from nfl2k5_espn25_more_moments_native import MomentsCPU
    from nfl2k5_historic_quick_game_native import disc_evidence

SOURCE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')


class Data(unittest.TestCase):
    def test_all_names_match_existing_audit_with_inference_retained(self):
        audit = json.loads((ROOT / 'e2/moment_audit.json').read_text())['moments']
        for actual, original in zip(v.rows(), audit):
            self.assertEqual(actual['row'], original['row'])
            for field in ('venue', 'date', 'classification', 'sources'):
                self.assertEqual(actual[field], original['real'][field])

    def test_owner_only_selected_with_named_option(self):
        self.assertEqual(tt._selected_space_requests(espn25_more_moments=True), mm.REQUESTS)
        self.assertEqual(tt._selected_space_requests(espn25_more_moments=True, espn25_named_previews=True),
                         mm.REQUESTS + v.REQUESTS)
        with self.assertRaises(ValueError):
            tt._selected_space_requests(espn25_named_previews=True)

    def test_full_union_fits_without_moving_existing_owners(self):
        requests = space.dormant_union()
        before = space.plan(tuple(r for r in requests if r[0] != v.OWNER))['allocations']
        after = space.plan(requests)['allocations']
        self.assertEqual(before, [r for r in after if r['owner'] != v.OWNER])
        parts = [r for r in after if r['owner'] == v.OWNER]
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(v.code_for(parts[0]['va'], parts)[0]), v.CODE_SIZE)


@unittest.skipUnless(HAVE_UNICORN, 'Unicorn required for native moment-venue execution')
@unittest.skipUnless(SOURCE.is_file(), 'private retail source required')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources, cls.context, cls.ids = disc_evidence(SOURCE)
        data = mm.Data.load()
        cls.display_order = mm.display_order(data)
        with hs.Source(SOURCE) as src:
            main = cls.resources[5]
            templates = {key: src.get(mm.template_for(data.teams[key], mm._retail_descriptors(main))['filename'])
                         for key in data.team_order()}
        cls.collection = mm.compile_situ(cls.resources[22], data, main, named=True)
        cls.files = mm.compile_files(main, templates, data)
        cls.retail = er.read_xbe(SOURCE)
        base, _ = er.apply_xbe(cls.retail)
        base, _ = space.apply(base, space.dormant_union())
        cls.base, _ = mm.apply(base)
        cls.payload, _ = v.apply(cls.base)

    def cpu(self, payload=None):
        return MomentsCPU(payload or self.payload, self.resources, self.context, self.ids,
                          situ_chunk=self.collection[:32 + struct.unpack_from('<I', self.collection, 4)[0]],
                          extra_files=self.files)

    def test_all_51_native_previews_name_callback_and_report_text(self):
        cpu = self.cpu()
        trace = []
        # Execute each patched report CALL and the native name load, then stop.
        cpu.stubs[0x127188] = lambda: cpu.ret(cpu.reg('edx'))
        cpu.stubs[0x1271C8] = lambda: cpu.ret(cpu.reg('ecx'))
        cpu.stubs[0x31855F] = lambda: cpu.ret(cpu.reg('ecx'))
        self.assertEqual(len(v.rows()), 51)
        self.assertEqual(set(self.display_order), set(range(51)))
        for row in v.rows():
            cpu.events.clear()
            display_index = self.display_order.index(row['row'] - 1)
            cpu.select(display_index)
            self.assertEqual(cpu.r(0xBF1858), row['row'] - 1)
            self.assertEqual(cpu.r(0xE5FF80), 8)
            stadium = cpu.run(0x77460)
            untouched = cpu.read(stadium, 128)
            # Simulate u4's shared 2026 rename using a separate bounded text cell.
            modern = '2026 SHARED VENUE'
            cpu.write(0x2500800, (modern + '\0').encode('utf-16le'))
            cpu.w(stadium, 0x2500800)
            cpu.w(stadium + 0x10, 0x2500800)
            shared = cpu.read(stadium, 128)
            cpu.run(0x2C5A70, args=(0x2500000, 0, 0))
            names = dict(preview=cpu.text(0x2500000), menu=cpu.text(cpu.run(0x2C1640)),
                         report_without_player=cpu.text(cpu.run(0x127181)),
                         report_with_player=cpu.text(cpu.run(0x1271C1)),
                         venue_location_reader=cpu.text(cpu.run(0x318557)))
            cpu.run(0x1C0910, args=(0x2500000, 200))
            names['presentation'] = cpu.text(0x2500000)
            self.assertEqual(set(names.values()), {row['venue']}, row['row'])
            cpu.run(0x1C08D0, args=(0x2500000, 200))
            location = cpu.text(0x2500000)
            self.assertIn(row['venue'], location)
            self.assertNotIn(modern, location)
            self.assertEqual(cpu.run(0x77460), stadium)
            self.assertEqual(cpu.read(stadium, 128), shared)
            # Re-entry into Quick Game and franchise with a stale moment ordinal.
            for mode in (0, 1, 4, 5, 6):
                cpu.w(0xE5FF80, mode)
                self.assertEqual(cpu.text(cpu.run(0x77540)), modern)
                self.assertEqual(cpu.text(cpu.run(0x127181)), modern)
                self.assertEqual(cpu.text(cpu.run(0x1271C1)), modern)
                cpu.run(0x1C0910, args=(0x2500000, 200))
                self.assertEqual(cpu.text(0x2500000), modern)
                self.assertEqual(cpu.text(cpu.run(0x318557)), modern)
                self.assertEqual(cpu.read(stadium, 128), shared)
            trace.append(dict(row=row['row'], display_row=display_index + 1, venue=row['venue'], native_text=names,
                              presentation_location=location,
                              historical_classification=row['classification'], modern_modes=[0, 1, 4, 5, 6],
                              stadium_record_unchanged=True))
            cpu.write(stadium, untouched)
            cpu.w(0xE5FF80, 8)
            cpu.run(0x20C3C0)
        if os.environ.get('E2P3_VENUE_PROOF'):
            Path(os.environ['E2P3_VENUE_PROOF']).write_text(json.dumps(dict(
                classification='PROVED OFFLINE', runtime_witnessed=False,
                xbe_sha256=hashlib.sha256(self.payload).hexdigest(),
                boundary='Native SITU relocation, imports, text reads and wide formatter; archive and presentation stubs.',
                moments=trace), indent=2) + '\n')

    def test_invalid_ordinals_and_mode_transitions_do_not_leak(self):
        cpu = self.cpu()
        cpu.select(14)
        original = cpu.text(cpu.r(cpu.run(0x77460)))
        for index in (51, 0xFFFFFFFF, 0x80000000):
            cpu.w(0xBF1858, index)
            self.assertEqual(cpu.text(cpu.run(0x77540)), original)
        cpu.w(0xBF1858, 14)
        self.assertEqual(cpu.text(cpu.run(0x77540)), 'Tampa Stadium')
        cpu.w(0xE5FF80, 0)
        self.assertEqual(cpu.text(cpu.run(0x77540)), original)
        cpu.w(0xE5FF80, 8)
        self.assertEqual(cpu.text(cpu.run(0x77540)), 'Tampa Stadium')

    def test_guard_replay_reversal_and_m1_composition(self):
        self.assertEqual(mm.status(self.payload), 'applied')
        self.assertEqual(v.apply(self.payload)[0], self.payload)
        self.assertEqual(mm.apply(self.payload)[0], self.payload)
        disabled, _ = v.apply(self.payload, enabled=False)
        self.assertEqual(v.status(disabled), 'retail')
        self.assertEqual(v.apply(disabled)[0], self.payload)
        image = XbeImage(self.payload)
        for va in [h[1] for h in v.HOOKS] + [v.allocation(self.payload)['va'] + v.TABLE]:
            bad = bytearray(self.payload)
            bad[image.offset(va, 1)] ^= 1
            bad = v.seal(bad)
            self.assertEqual(v.status(bad), 'foreign')
            self.assertEqual(mm.status(bad), 'foreign')
            with self.assertRaises(ValueError):
                v.apply(bad)

    def test_off_keeps_previous_native_preview(self):
        cpu = self.cpu(self.base)
        cpu.select(14)
        cpu.run(0x2C5A70, args=(0x2500000, 0, 0))
        self.assertEqual(cpu.text(0x2500000), 'Tampa Bay Stadium')
        self.assertEqual(v.apply(self.base, enabled=False)[0], self.base)


if __name__ == '__main__':
    unittest.main()
