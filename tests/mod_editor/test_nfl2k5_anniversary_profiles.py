"""PROVED OFFLINE: named-profile rejection and archive-directory growth invariants."""
from pathlib import Path
import struct
from types import SimpleNamespace as NS
import unittest

from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_espn25_rosters as er
from tools.nfl_outer import HEADER_SIZE

SOURCE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')


class DirectoryGrowth(unittest.TestCase):
    def test_directory_growth_moves_offsets_and_preserves_cross_pack_bytes(self):
        # The second original resource straddles packs 0 and F.
        original = bytes(2048) + b'A' * 2048 + b'B' * 2048 + b'C' * 2048
        entries = [NS(name_id=1, size=2048, virtual_offset=2048),
                   NS(name_id=2, size=4096, virtual_offset=4096)]
        packs = [NS(name='0', ordinal=0, virtual_start=0, size=6144),
                 NS(name='F', ordinal=1, virtual_start=6144, size=2048)]
        disc = NS(archive_entries=entries, packs=packs, header=bytes(HEADER_SIZE),
                  pack_extents={p.name: NS(byte_offset=p.virtual_start) for p in packs},
                  read=lambda size, offset: original[offset:offset+size])
        additions = [('capacity-%03d.bin' % i, bytes([i % 256]) * 2048) for i in range(180)]
        plan = hs.rewrite_plan(disc, {}, additions)
        self.assertEqual(plan['directory_growth'], 2048)
        self.assertEqual(plan['rows'][:2], [(1, 2048, 4096), (2, 4096, 6144)])
        result = b''.join(b''.join(hs.pack_stream(disc, p, plan, {}, additions)) for p in packs)
        self.assertEqual(len(result), sum(plan['sizes']))
        for i, old in enumerate(entries):
            _identity, size, offset = plan['rows'][i]
            self.assertEqual(result[offset:offset+size], original[old.virtual_offset:old.virtual_offset+old.size])
        for (name, raw), (_n, offset, size) in zip(additions, plan['placed']):
            self.assertEqual(result[offset:offset+size], raw, name)
        self.assertEqual(struct.unpack_from('<I', result)[0], 182)


@unittest.skipUnless(SOURCE.is_file(), 'private USA disc required')
class NamedProfile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with hs.Source(SOURCE) as src:
            cls.situ = src.get(identity=mm.SITU_ID)
            cls.main = src.archive.read_entry(5)
            cls.entries = src.archive.entries
        cls.data = mm.Data.load()

    def test_two_known_profiles_and_scalar_or_selector_corruption_refused(self):
        for named in (False, True):
            compiled = mm.compile_situ(self.situ, self.data, self.main, named=named)
            self.assertEqual(mm.situ_rows(compiled, self.data), 'applied')
            for offset in (20, 24):
                changed = bytearray(compiled)
                at = 32 + mm.sc.rel(compiled[32:], mm.sc.RECORDS + offset)
                changed[at] ^= 1
                self.assertEqual(mm.situ_rows(bytes(changed), self.data), 'foreign')
            changed = bytearray(compiled)
            changed[32 + mm.sc.RECORDS + 0x20] ^= 1
            self.assertEqual(mm.situ_rows(bytes(changed), self.data), 'foreign')

    def test_all_200_strings_round_trip_and_super_bowl_numerals(self):
        compiled = mm.compile_situ(self.situ, self.data, self.main, named=True)
        body = compiled[32:]
        sb = 0
        for i, authored in enumerate(mm.named_previews()):
            for field, offset in mm.sc.TEXT.items():
                text = mm.sc.utf16(body, mm.sc.rel(body, mm.sc.RECORDS + i * mm.sc.STRIDE + offset))
                self.assertEqual(text, authored['text'][field])
            if authored.get('super_bowl'):
                sb += 1
                self.assertIn('Super Bowl ' + authored['super_bowl'], authored['text']['description'])
        self.assertEqual(sb, 17)
        self.assertEqual(len(mm.named_previews()), 50)

    def test_original_roster_context_accepts_only_known_expanded_profiles(self):
        expected = er.context_sha(er.describe_context(self.main, self.situ, self.entries))
        for named in (False, True):
            compiled = mm.compile_situ(self.situ, self.data, self.main, named=named)
            context = er.describe_context(self.main, compiled, self.entries)
            self.assertEqual(er.context_sha(context), expected)
            self.assertEqual(len(context['descriptors']), 75)
            self.assertEqual(len(context['moments']), 25)
            for offset in (0, 20, 24):
                changed = bytearray(compiled)
                at = 32 + mm.sc.rel(compiled[32:], mm.sc.RECORDS + offset)
                changed[at] ^= 1
                with self.assertRaises(ValueError):
                    er.describe_context(self.main, bytes(changed), self.entries)

    def test_named_rosters_recognize_only_the_exact_spare_style_transform(self):
        manifest, _ = er.dataset()
        resources = er.read_resources(SOURCE)
        applied, _ = er.apply(resources)
        with hs.Source(SOURCE) as src:
            styles = hs.franchise_styles(src.get(identity=hs.ROSTER_OUTER_ID))
            taken = hs.taken_styles(src, styles)
        self.assertEqual(er.HISTORIC_SPARES, {c: hs.spare_style(c, styles, taken) for c in styles})
        for target in manifest['resources']:
            raw = applied[target['outer']]
            for one_pool in (False, True):
                before = mm._one_pool(raw) if one_pool else raw
                after = hs.with_spare(before, er.HISTORIC_SPARES[target['code']])
                self.assertEqual(er.resource_status(after, target),
                                 'one_pool_applied' if one_pool else 'applied')
                bad = bytearray(after)
                bad[16] ^= 1  # normalization never masks foreign wrapper/player bytes
                self.assertEqual(er.resource_status(bytes(bad), target), 'foreign')

    def test_screen_scope_accepts_only_a_complete_pinned_stock_bank(self):
        from mod_editor.core import nfl2k5_stock_books as stock, nfl2k5_screen_timing as screens
        from mod_editor.core.errors import ValidationError
        with hs.Source(SOURCE) as source:
            modern = [source.archive.entries[i] for i in range(307, 344)]
            original = {entry.index: source.archive.read_entry(entry.index) for entry in modern}
        for one_pool in (False, True):
            bank, _ = stock.preserve(SOURCE, one_pool=one_pool)
            extras = [NS(index=5000+i, name_id=row['alias_name_id'], size=row['bytes'])
                      for i, row in enumerate(stock.aliases())]
            blobs = {**original, **{entry.index: bank[row['alias']]
                     for entry, row in zip(extras, stock.aliases())}}
            entries = [*modern, *extras]
            archive = NS(entries_with_head=lambda _head: entries, read_entry=lambda i: blobs[i])
            self.assertEqual([entry.index for entry, _raw in screens._archive_books(archive)], list(range(307, 344)))
            entries.pop()
            with self.assertRaises(ValidationError):
                screens._archive_books(archive)
            entries.append(extras[-1])
            bad = bytearray(blobs[extras[0].index]); bad[-1] ^= 1
            blobs[extras[0].index] = bytes(bad)
            with self.assertRaises(ValidationError):
                screens._archive_books(archive)


if __name__ == '__main__':
    unittest.main()
