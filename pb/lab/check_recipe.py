#!/usr/bin/env python3
"""PROVED OFFLINE: compose lab packs in memory and run the real Build menu gate."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from pb.verify_league import Overlay,menu_gate,OuterImage,BOOK_ENTRIES
from mod_editor.core import nfl2k5_playbook_pack as p

def main():
    recipe=json.loads((ROOT/'pb/lab/v7.pb.json').read_text())
    paths=[ROOT/v.removeprefix('<stack>/') for v in recipe['overrides']['playbook_packs']]
    packs=[(str(path),p.load_pack(path)) for path in paths]
    packs.sort(key=lambda v:v[1].schema!=p.OFFENSE_SCHEMA)
    image=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
    with OuterImage(image) as source:
        overlay=Overlay(source)
        result=p.apply_packs_to_archive(overlay,packs,book_entries=BOOK_ENTRIES,xbe=image)
        gate=menu_gate(image,overlay)
    (ROOT/'pb/receipts/lab-composition.json').write_text(json.dumps(dict(status='PROVED OFFLINE',runtime_witness=False,install=result,build_menu_gate=gate),indent=2)+'\n')
    print(gate)
if __name__=='__main__':main()
