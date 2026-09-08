"""Small synthetic discs with real executable-only evidence; no retail audio."""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_music_banks import fixture, tone
from tests.mod_editor.test_nfl2k5_music_playlist import XBE, repin
from mod_editor.core import nfl2k5_music_banks as banks
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core import platform_compat as io
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


def options(records):
    rows = playlist.catalog_for_counts(dict(playlist.BANK_COUNTS, femusic=200, cribmusic=200))
    checked = [i for i,r in enumerate(rows) if (r['bank'],r['index']) in records]
    selected = playlist.Selection(tuple((r['bank'],r['index']) for i,r in enumerate(rows) if i in checked))
    return dict(schema=2,music_shuffle=True,include_outtakes=True,include_beds=False,
                catalog=rows,checked=checked,records=[list(r) for r in selected.records],enabled=list(selected.enabled))


class DocumentTests(unittest.TestCase):
    def test_200_bank_choices_are_independent_of_100_record_storage(self):
        value = options({('femusic',i) for i in range(100,200)})
        selected = playlist.from_options(value)
        self.assertEqual(len(selected.records),100)
        self.assertEqual(selected.records[-1],('femusic',199))
        self.assertEqual(playlist._decode_ro(playlist.ro_for(selected,0x1506000),0x1506000),selected)
        with self.assertRaisesRegex(ValueError,'100-record'):
            playlist.from_options(options({('femusic',i) for i in range(101)}))

    def test_reject_malformed_fields_and_detach_project_copies(self):
        value = options({('cribmusic',199)})
        state = playlist.build_settings(dict(music_shuffle=True,music_shuffle_selection=value))
        state['music_shuffle_selection']['catalog'][0]['title']='Changed'
        self.assertNotEqual(state['music_shuffle_selection'],value)
        self.assertEqual(playlist.from_options(json.loads(json.dumps(value))).records,(('cribmusic',199),))
        for bad in (dict(value, checked=[True]),dict(value, enabled=[False]),dict(value, surprise='x'),
                    dict(value, records=[['cribmusic',False]]),dict(value,catalog=[dict(value['catalog'][0],bed=True)])):
            with self.subTest(bad=list(bad)):
                with self.assertRaises(ValueError):playlist.copy_options(bad)
        with self.assertRaisesRegex(ValueError,'disagree'):
            playlist.build_settings(dict(music_shuffle=False,music_shuffle_selection=value))


@unittest.skipUnless(XBE.is_file(), 'USA retail XBE absent; installed playlist publication proof unavailable')
class RebuiltPlaylistTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.fixture=fixture(self.root);self.source=self.fixture.path
        self.output=self.root/'output.iso';self.wav=tone(self.root/'tone.wav',frames=65)

    def install(self, selected=None, payload=None):
        if payload is None:
            payload=playlist.apply(XBE.read_bytes(),selection=selected)[0]
        with archive.Disc(self.source) as disc:
            partition=disc.partition
        fd=os.open(self.source,os.O_RDWR | getattr(os,'O_BINARY',0))
        try:
            archive.write_named(fd,lambda n,at:io.pread(fd,n,at),partition,'default.xbe',
                                lambda n,at:payload[at:at+n],len(payload))
        finally:os.close(fd)

    def recipe(self,count,bank='femusic'):
        return dict(schema=banks.SCHEMA,bank=bank,tracks=[dict(wav=str(self.wav),title=f'Song {i}',artist='Test') for i in range(count)])

    def test_rebuilt_200_bank_revalidates_actual_installed_100_high_indices(self):
        value=options({('femusic',i) for i in range(100,200)})
        selected=playlist.from_options(value)
        self.install(selected)
        self.assertEqual(banks.read_descriptor_counts(self.source)['femusic'],7)
        with self.assertRaisesRegex(ValueError,'invalid index'):
            banks.revalidate_playlist(self.source)
        plan=banks.plan(self.source,self.recipe(200))
        actual,preflight=banks.playlist_preflight(self.source,value,library_plan=plan)
        self.assertEqual(actual,selected)
        self.assertFalse(preflight['revalidated_after_rebuild'])
        receipt=banks.rebuild(self.source,self.output,self.recipe(200),expected_plan=plan)
        checked=receipt['verification']['music_shuffle']
        self.assertTrue(checked['revalidated_after_rebuild'])
        self.assertEqual((checked['records'],checked['descriptor_counts']['femusic']),(100,200))
        self.assertEqual(banks.revalidate_playlist(self.output,expected=value),checked)
        with self.assertRaisesRegex(ValueError,'differs from Build'):
            banks.revalidate_playlist(self.output,expected=playlist.Selection(playlist.CORE[:1]))

    def test_rebuilt_200_jukebox_twins_and_actual_titles_browse(self):
        self.install(playlist.Selection((('cribmusic',199),)))
        receipt=banks.rebuild(self.source,self.output,self.recipe(200,'cribmusic'))
        counts=banks.read_descriptor_counts(self.output)
        self.assertEqual((counts['cribmusic'],counts['crib22']),(200,200))
        self.assertTrue(receipt['verification']['music_shuffle']['revalidated_after_rebuild'])
        rows=banks.read_playlist_catalog(self.output)
        row=next(r for r in rows if (r['bank'],r['index'])==('cribmusic',199))
        self.assertEqual(row['title'],'Song 199 / Test')
        self.assertFalse(any(r['spoken'] for r in rows))

    def test_shrink_refuses_before_publication_and_closes_all_readers(self):
        self.install(playlist.Selection((('femusic',6),)))
        before=archive.file_hash(self.source)
        self.output.write_bytes(b'previous output')
        with self.assertRaisesRegex(ValueError,'invalid index: femusic:6'):
            banks.rebuild(self.source,self.output,self.recipe(3),overwrite=True)
        self.assertEqual(self.output.read_bytes(),b'previous output')
        self.assertEqual(archive.file_hash(self.source),before)
        self.assertFalse(list(self.root.glob('.archive-*')))
        # Immediate replace exercises close-before-publication on Windows too.
        other=self.root/'renamed.iso';os.replace(self.source,other);os.replace(other,self.source)

    def test_preflight_uses_reopened_source_and_invalid_installed_bytes_refuse(self):
        self.install(playlist.Selection((('femusic',0),)))
        selected,receipt=banks.playlist_preflight(self.source,options({('femusic',0)}))
        self.assertEqual(selected.records,(('femusic',0),))
        self.assertEqual(receipt['descriptor_counts']['femusic'],7)
        with archive.Disc(self.source) as disc:payload=banks._xbe(disc)
        raw=bytearray(payload);image=XbeImage(payload);ro=playlist.sites(payload)[2]
        raw[image.offset(ro['va'])]^=1
        self.install(payload=repin(raw))
        with self.assertRaises(ValueError):banks.revalidate_playlist(self.source)

    def test_no_playlist_reports_absence_and_real_descriptor_geometry_is_checked(self):
        self.install(payload=XBE.read_bytes())
        checked=banks.revalidate_playlist(self.source)
        self.assertFalse(checked['installed'])
        self.assertFalse(checked['revalidated_after_rebuild'])
        with self.assertRaisesRegex(ValueError,'differs from Build'):
            banks.revalidate_playlist(self.source,expected=playlist.Selection())
        with archive.Disc(self.source) as disc:
            r=disc.banks['femusic'];outer=disc.archive_entries[r.outer]
            virtual=outer.virtual_offset+r.offset+0xA0
            packs=disc.packs
            # Resolve the descriptor through the actual current outer, not a retail physical offset.
            pack=next(p for p in packs if p.virtual_start<=virtual<p.virtual_end)
            offset=disc.pack_extents[pack.name].byte_offset+virtual-pack.virtual_start
        fd=os.open(self.source,os.O_RDWR | getattr(os,'O_BINARY',0))
        try:io.pwrite(fd,(65536).to_bytes(4,'little'),offset)
        finally:os.close(fd)
        with self.assertRaisesRegex(ValueError,'boundaries'):
            banks.read_descriptor_counts(self.source)


if __name__=='__main__':unittest.main()
