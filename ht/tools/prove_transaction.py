#!/usr/bin/env python3
"""Bounded archive transaction proof using real ROST slices, not a full build."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BUILD=Path('/media/noah/Storage/.b76-research/ht/astra-build')
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tests/mod_editor')]
from test_nfl2k5_espn25_rosters import RetailTests,RETAIL
from nfl2k5_xiso_fixture import SyntheticXiso
from nfl_outer import HEADER_SIZE,align_up
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_historic_rosters as h
from mod_editor.core import nfl2k5_historic_teams_quick_game as h1
from mod_editor.core import nfl2k5_historic_styles as styles
from mod_editor.core import nfl2k5_modern_helmets as hm
from mod_editor.core import nfl2k5_roster_records as rr


def run():
    RetailTests.setUpClass()
    with tempfile.TemporaryDirectory(prefix='ht-transaction-',dir=BUILD/'tmp') as directory:
        # The production archive writer requires all sixteen packs. Keep real
        # resources in pack 0 and one harmless page in each remaining pack.
        ids={d['outer']:d['id'] for d in RetailTests.descriptors}
        entries=[(ids.get(i,i),RetailTests.context.get(i,RetailTests.all_rosters.get(i,bytes(32))))
                 for i in range(189)]
        entries += [(0xA0000000+i,bytes(2048)) for i in range(15)]
        first=align_up(HEADER_SIZE+12*len(entries))+sum(align_up(len(raw)) for _,raw in entries[:189])
        sizes=(first,)+(2048,)*15
        sectors=[];cursor=80
        for size in sizes:
            sectors.append(cursor);cursor+=size//2048
        fixture=SyntheticXiso(Path(directory),entries,pack_sizes=sizes,pack_sectors=tuple(sectors))
        path=fixture.path
        payload,_=e.apply_xbe((RETAIL/'default.xbe').read_bytes())
        payload,_=h1.apply(payload)
        # The fixture's root has one executable node. Give it the expanded test
        # executable before exercising the production fixed-span writer.
        with path.open('r+b') as stream:
            at=(path.stat().st_size+2047)//2048*2048
            stream.seek(at);stream.write(payload)
            stream.seek(33*2048+4);stream.write(struct.pack('<II',at//2048,len(payload)))
        e.apply_to_image(path)
        with rr._outer_image()(path) as archive:
            canonical={t['outer']:archive.read_entry(t['outer']) for t in h.dataset()['teams']}
        receipt=h.apply_to_image(path)
        assert h.image_status(path)==e.image_status(path)=='applied'
        first=hashlib.sha256(path.read_bytes()).hexdigest()
        assert h.apply_to_image(path)['status']=='already_applied'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==first
        with rr._outer_image()(path,writable=True) as archive:
            assert all(archive.read_entry(i)==raw for i,raw in canonical.items())
            for outer in hm.historic_edits():
                archive.write(archive.entries[outer].virtual_offset,
                              hm.compile_historic(archive.read_entry(outer),outer))
        assert h.image_status(path)==e.image_status(path)=='applied'
        with rr._outer_image()(path,writable=True) as archive:
            ids={entry.name_id:entry.index for entry in archive.entries}
            index=ids[styles.name_id(h.dataset()['teams'][0]['alias'])]
            raw=bytearray(archive.read_entry(index));doc=rr.RosterDocument(raw[32:])
            raw[32+doc.players[0].offset+rr.FIELD_BY_NAME['jersey'].offset]^=1
            archive.write(archive.entries[index].virtual_offset,raw)
        assert h.image_status(path)=='foreign'
        corrupt=hashlib.sha256(path.read_bytes()).hexdigest()
        try:
            h.apply_to_image(path)
        except h.HistoricRostersError:
            pass
        else:
            raise AssertionError('Corrupt alias was accepted')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==corrupt
        result=dict(label='PROVED OFFLINE',receipt=receipt,canonical_resources_preserved=75,
            owner_states_after_hm={'historic_rosters_2026':'applied','espn25_rosters':'applied'},
            replay_identical=True,corruption_refused_before_write=True,fixture_bytes=path.stat().st_size,
            manifest_sha256=hashlib.sha256((h.DATA_DIR/'manifest.json').read_bytes()).hexdigest(),
            writer_sha256=hashlib.sha256(Path(h.__file__).read_bytes()).hexdigest(),
            scope='Bounded fixture with real ROST slices and executable. Not the requested full candidate build.')
    result['fixture_deleted']=not path.exists()
    return result


if __name__=='__main__':
    result=run()
    (ROOT/'ht/evidence/phase2_transaction.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
