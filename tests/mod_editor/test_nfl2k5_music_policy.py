"""Standalone exact-pin/data-span/digest tests. Retail evidence is read only."""
from pathlib import Path
import itertools
import os
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_music_policy as music
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest
XBE=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'/'default.xbe'

class InvalidTests(unittest.TestCase):
    def test_malformed_and_options(self):
        for p in (b'',b'XBEH'+bytes(100),b'foreign'):
            self.assertEqual(music.status(p),'foreign')
            with self.assertRaises(ValueError): music.apply(p)
        for options in ({'music_policy':'all_songs'},{'music_unlock':1},{'music_userlist':'yes'}):
            with self.assertRaises(ValueError): music.apply(b'',**options)

@unittest.skipUnless(XBE.is_file(),'retail default.xbe evidence is absent')
class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.retail=XBE.read_bytes()

    def test_all_legal_selections_and_idempotence(self):
        self.assertEqual(music.status(self.retail),'retail')
        for menu,unlock,userlist in itertools.product((False,True),repeat=3):
            if userlist and not menu: continue
            options=dict(music_policy='jukebox_menus' if menu else 'retail',music_unlock=unlock,music_userlist=userlist)
            patched,receipt=music.apply(self.retail,**options)
            self.assertEqual(receipt['field_bytes'],4*menu+56*unlock+12*userlist)
            again,second=music.apply(patched,**options)
            self.assertEqual(again,patched)
            self.assertEqual(second['changed_bytes'],0)
            self.assertFalse(receipt['runtime_witnessed'])

    def test_exact_write_union_and_digest(self):
        patched,receipt=music.apply(self.retail,music_unlock=True,music_userlist=True)
        image=XbeImage(patched)
        allowed=set()
        for site in music.SITES:
            offset=image.offset(site.va,len(site.after))
            allowed.update(range(offset,offset+len(site.after)))
            self.assertEqual(image.read(site.va,len(site.after)),site.after)
            self.assertEqual(image.section(site.va,len(site.after)).name,'.data')
        for section in _sections(patched):
            if section.index in receipt['sections_repinned']:
                allowed.update(range(section.header_offset+36,section.header_offset+56))
                self.assertEqual(section.stored_digest,section_digest(patched,section))
        changed={i for i,(a,b) in enumerate(zip(self.retail,patched)) if a!=b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(patched),len(self.retail))
        self.assertEqual(receipt['field_bytes'],72)

    def test_partial_unlocks_and_userlist_refused_before_mutation(self):
        for site in music.SITES[1:]:
            data=bytearray(self.retail)
            offset=XbeImage(data).offset(site.va,len(site.after))
            data[offset:offset+len(site.after)]=site.after
            frozen=bytes(data)
            self.assertEqual(music.status(frozen),'foreign')
            with self.assertRaises(music.MusicPolicyError): music.apply(frozen,music_unlock=True)
            self.assertEqual(bytes(data),frozen)
        data,_=music.apply(self.retail)
        offset=XbeImage(data).offset(music.USERLIST_VA,12)
        mixed=data[:offset]+b'\1'+data[offset+1:]
        self.assertEqual(music.status(mixed),'foreign')

    def test_foreign_unselected_option_and_context_refused(self):
        for va in (music.MENU_VA,music.USERLIST_VA,0xAC9C94,0xAC9C90,0xE92A34):
            data=bytearray(self.retail)
            data[XbeImage(data).offset(va,1)]^=0x80
            with self.assertRaises(ValueError): music.apply(bytes(data),music_policy='retail')

    def test_dispatcher_selection_does_not_skip_unrequested_independent_state(self):
        unlocked,_=music.apply(self.retail,music_policy='retail',music_unlock=True)
        selection=music.Selection(music_policy='jukebox_menus')
        self.assertEqual(music.status(unlocked),'applied')
        self.assertEqual(selection.status(unlocked),'retail')
        composed,receipt=selection.apply(unlocked)
        self.assertEqual(selection.status(composed),'applied')
        self.assertEqual(receipt['changed_bytes'],receipt['changed_byte_count'])

    def test_real_title_artist_collection_transcriptions(self):
        import struct
        from mod_editor.core.nfl2k5_music_catalog import TRACKS
        image=XbeImage(self.retail)
        def text(va):
            data=bytearray()
            for i in range(256):
                code=image.read(va+i*2,2)
                if code==bytes(2):return data.decode('utf-16le')
                data.extend(code)
            self.fail('unterminated title string')
        recovered={}
        for index in range(18):
            va=0xAC9C80+32*index
            label,_,stereo,mono,enabled,key,count,tracks=struct.unpack('<8I',image.read(va,32))
            self.assertEqual(enabled,1)
            for n in range(count):
                stream,title,artist,_duration=struct.unpack('<4I',image.read(tracks+n*16,16))
                recovered[stream]=(text(title),text(artist),text(label))
        self.assertEqual(tuple(recovered[i] for i in range(59)),TRACKS)

    def test_independent_composition_preserves_existing_options(self):
        unlocked,_=music.apply(self.retail,music_policy='retail',music_unlock=True)
        menus,_=music.apply(unlocked)
        both,_=music.apply(self.retail,music_unlock=True)
        self.assertEqual(menus,both)
        self.assertEqual(music.apply(both,music_policy='retail')[0],both)
        with self.assertRaises(ValueError): music.apply(self.retail,music_policy='retail',music_userlist=True)

if __name__=='__main__': unittest.main()
