"""Small synthetic seven-bank XISO, real session transactions, no retail audio."""
from dataclasses import replace
import hashlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tools'))
import nfl2k5_commentary_swap as cs
from nfl_outer import ALIGNMENT, HEADER_SIZE, ENTRY_SIZE, PACK_SLOT_COUNT, parse_archive
from tests.nfl2k5_commentary_swap_test import _dir_node
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture
from tests.mod_editor.test_nfl2k5_ausb_build_adapter import _origin_inventories
from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5AudioService, Nfl2k5StreamingAudioBank, Nfl2k5StreamingAudioRange
from mod_editor.core.nfl2k5_music_catalog import BANKS
from mod_editor.studio.session import StudioSession
from mod_editor.studio.music_service import MusicService


def wav_bytes(channels=2, frames=128, sample=2000):
    pcm = struct.pack('<h',sample)*(frames*channels)
    return (b'RIFF'+struct.pack('<I',len(pcm)+36)+b'WAVEfmt '+
            struct.pack('<IHHIIHH',16,1,channels,22050,22050*channels*2,channels*2,16)+
            b'data'+struct.pack('<I',len(pcm))+pcm)


class MusicDisc:
    def __init__(self, root):
        self.root = root
        self.path = root/'music.iso'
        self.pack_dir = root/'packs'
        self.pack_dir.mkdir()
        self.descriptors = tuple(d for d in cs.PINNED_DESCRIPTORS if d[-1] in BANKS)
        count = 3137
        sizes = [32]*count
        sizes[-1] = 2048
        names = [0x70000000+i for i in range(count)]
        for outer,chunk,offset,size,name in self.descriptors:
            sizes[outer] = max(sizes[outer], offset+32+size)
        for name,(n,ch,outer,chunk,external,label) in BANKS.items():
            sizes[external] = n*72*ch
            names[external] = zlib.crc32(f'{name}.bin'.upper().encode('utf-16le')) & 0xffffffff
        starts=[]
        cursor=cs.align_up(HEADER_SIZE+count*ENTRY_SIZE)
        for size in sizes:
            starts.append(cursor)
            cursor=cs.align_up(cursor+size)
        # Put a pack seam inside a middle crib22 stream; this also tests
        # byte spans that cut across a codec block.
        seam = starts[3122]+2048
        pack_sizes=(seam, cursor-seam)
        virtual=bytearray(cursor)
        struct.pack_into('<III',virtual,0,count,0,2)
        struct.pack_into(f'<{PACK_SLOT_COUNT}I',virtual,12,*(s//2048 for s in pack_sizes),*([0]*(PACK_SLOT_COUNT-2)))
        for i,(name,size,start) in enumerate(zip(names,sizes,starts)):
            struct.pack_into('<III',virtual,HEADER_SIZE+i*12,name,size,start//2048)
            virtual[start:start+4]=b'FILL'
        for outer,chunk,offset,size,name in self.descriptors:
            n,ch,_o,_c,external,_label=BANKS[name]
            body=bytearray(size)
            body[12:16]=b'AUSB'
            struct.pack_into('<i',body,16,0x11)
            title=(name+'\0').encode('utf-16le')
            body[0x20:0x20+len(title)]=title
            title=(name+'.bin\0').encode('utf-16le')
            body[0x40:0x40+len(title)]=title
            struct.pack_into('<5I',body,0x80,n,0,ch,22050,0x12000)
            struct.pack_into(f'<{n+1}I',body,0x98,*(i*72*ch for i in range(n+1)))
            at=starts[outer]+offset
            virtual[at:at+32]=struct.pack('<4sI6I',b'AUSB',size,0,0,0,0,0,0)
            virtual[at+32:at+32+size]=body
            # Constant valid PCM baseline, independent synthetic originals.
            block=struct.pack('<hBB',6000,0,0)+bytes(32)
            virtual[starts[external]:starts[external]+sizes[external]]=block*(2*ch*n)
        pack_sectors=(64,64+seam//2048)
        rootdir=_dir_node([(35,16,0x80,'default.xbe'),(34,64,0x10,'vc_53450030')])
        sub=_dir_node([(sector,size,0x80,str(i)) for i,(sector,size) in enumerate(zip(pack_sectors,pack_sizes))])
        rootdir=_dir_node([(35,16,0x80,'default.xbe'),(34,len(sub),0x10,'vc_53450030')])
        image=bytearray(64*2048+len(virtual))
        image[0x10000:0x10014]=cs.xiso.XDVDFS_MAGIC
        struct.pack_into('<II',image,0x10014,33,len(rootdir))
        image[0x107ec:0x10800]=cs.xiso.XDVDFS_MAGIC
        image[33*2048:33*2048+len(rootdir)]=rootdir
        image[34*2048:34*2048+len(sub)]=sub
        image[35*2048:35*2048+16]=b'XBEH'+bytes(12)
        image[64*2048:]=virtual
        self.path.write_bytes(image)
        (self.pack_dir/'0').write_bytes(virtual[:seam])
        (self.pack_dir/'1').write_bytes(virtual[seam:])

    def catalog_banks(self):
        with cs.DiscBanks(self.path, descriptors=self.descriptors) as disc:
            result=[]
            for name,b in disc.banks.items():
                d=next(d for d in self.descriptors if d[-1]==name)
                owner=disc.archive_entries[d[0]]
                result.append(Nfl2k5StreamingAudioBank(
                    asset_id=f'nfl2k5.audio.ausb.o{d[0]:04d}.c{d[1]:04d}',
                    name=name,role_class='soundtrack',outer_index=d[0],
                    outer_id=f'0x{owner.name_id:08x}',outer_head='FILL',outer_size=owner.size,
                    chunk_index=d[1],chunk_offset=d[2],stored_size=d[3],
                    external_filename=b.external_filename,external_outer_index=b.external_outer_index,
                    external_outer_id=f'0x{b.entry.name_id:08x}',external_size=b.external_size,
                    entry_count=b.count,sample_rate=22050,channel_word=b.channels,
                    unknown_word=0,unit_word=0x12000,boundaries=b.boundaries,
                    descriptor_sha256=hashlib.sha256(disc.read_entry_range(owner,d[2],d[3]+32)).hexdigest(),
                    shared_external_descriptor_count=1))
            return tuple(result)


class FixtureAudio(Nfl2k5AudioService):
    # Real sealed authorizations against deliberately small synthetic origin
    # inventories. All WAV parsing, source slot decode and session I/O are real.
    def load_private_origin_inventories(self):
        self._source_fingerprints, self._containment_fingerprints = _origin_inventories()
        return self._source_fingerprints, self._containment_fingerprints


def music_session(root, disc, name='session'):
    fixture_root=root/'audio-fixture'
    if not fixture_root.exists():
        fixture_root.mkdir()
    fixture=AudioFixture(fixture_root)
    catalog=fixture.catalog()
    banks=disc.catalog_banks()
    catalog.streaming_banks=banks
    catalog._streaming_by_id={b.asset_id:b for b in banks}
    ranges=tuple(Nfl2k5StreamingAudioRange(b,i,*b.boundaries[i:i+2]) for b in banks for i in range(b.entry_count))
    catalog.streaming_ranges=ranges
    catalog._streaming_range_by_id={r.asset_id:r for r in ranges}
    audio=FixtureAudio(fixture.cache,catalog)
    audio._archive=parse_archive(disc.pack_dir/'0')
    session=StudioSession(fixture.cache,object(),root=root/'sessions',session_id=name)
    session.attach_audio_service(audio)
    return MusicService(session), fixture
