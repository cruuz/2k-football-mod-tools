#!/usr/bin/env python3
"""PROVED OFFLINE: all-team pack validation, retained semantics and native menu pages."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import mod_build, nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_playbook_inspector as insp
from pb.verify import native_receipt
from pb.build_league import semantic_digest
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES

class Overlay:
    """PROVED OFFLINE: every write is held in memory; retail handle is read-only."""
    def __init__(self, source):
        self.source=source; self.entries=source.entries; self.pending={}
    def read_entry(self,index):
        return self.pending[index] if index in self.pending else self.source.read_entry(index)
    def write(self,offset,payload):
        index=next(e.index for e in self.entries if e.virtual_offset==offset)
        self.pending[index]=bytes(payload);return len(payload)
    def entries_with_head(self,head):return self.source.entries_with_head(head)
    def __enter__(self):return self
    def __exit__(self,*args):return False


def menu_gate(image,overlay):
    proxy=SimpleNamespace(_outer_image=lambda:SimpleNamespace(OuterImage=lambda _:overlay))
    original=mod_build._core_module
    with patch.object(mod_build,'_core_module',side_effect=lambda name:proxy if name=='nfl2k5_playbook_pack' else original(name)):
        return mod_build._check_playbook_menus(image,lambda *args:None)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image',type=Path,required=True);ap.add_argument('--xbe',type=Path,required=True)
    args=ap.parse_args();xbe=args.xbe.read_bytes();digest=lambda b:hashlib.sha256(b).hexdigest()
    assert digest(xbe)=='73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
    manifest=json.loads((ROOT/'pb/league_manifest.json').read_text())['teams']
    result=dict(status='PROVED OFFLINE',runtime_witness=False,scope='retail Unicorn menu functions; six UI calls stubbed; no gameplay',xbe_sha256=digest(xbe),teams={})
    with OuterImage(args.image) as source:
        overlay=Overlay(source)
        for entry in manifest:
            team=entry['team']; path=ROOT/entry['pack']; pack=packs.load_pack(path)
            check=packs.check_pack(pack);assert check.ok,check.text()
            compile_receipts=[]
            install=packs.apply_packs_to_archive(overlay,[(entry['pack'],pack)],book_entries=BOOK_ENTRIES,collector=compile_receipts,xbe=xbe)
            raw=overlay.read_entry(BOOK_ENTRIES[team]);walk=native_receipt(xbe,raw)
            rows=json.loads((ROOT/f'pb/catalogs/{team}.json').read_text())
            result['teams'][team]=dict(pack=entry['pack'],pack_sha256=digest(path.read_bytes()),semantic_sha256=semantic_digest(pack),
                check=check.text(),compile=compile_receipts[0][1],install=install,
                formations=len(walk),pages=sum(len(r['pages']) for r in walk),menu_entries=sum(len(r['plays']) for r in walk),
                unique_plays=len({pi for r in walk for pi in r['plays']}),walks=walk,
                concepts=dict(Counter(r['concept'] for r in rows)),personnel=dict(Counter(r['personnel'] for r in rows)),
                primary_roles=dict(Counter('run' if r['primary_slot'] is None else str(r['primary_slot']) for r in rows)))
            print(team,len(walk),result['teams'][team]['pages'],'PASS',flush=True)
            (ROOT/'pb/receipts/league-offline.partial.json').write_text(json.dumps(result,indent=2)+'\n')
        result['build_menu_gate']=menu_gate(args.image,overlay)
        result['unchanged_utility_books']=[t for t,idx in BOOK_ENTRIES.items() if t not in packs.TEAM_BOOKS and overlay.read_entry(idx)==source.read_entry(idx)]
        assert len(overlay.pending)==32
        assert len({r['semantic_sha256'] for r in result['teams'].values()})==32
    (ROOT/'pb/receipts/league-offline.json').write_text(json.dumps(result,indent=2)+'\n')
    (ROOT/'pb/receipts/league-offline.partial.json').unlink()
    print(json.dumps(result['build_menu_gate']))

if __name__=='__main__':main()
