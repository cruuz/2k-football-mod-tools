#!/usr/bin/env python3
"""PROVED OFFLINE: compile, Build menu gate, native menu replay; never start xemu."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import mod_build, nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_depth_roles as roles
from tests.nfl2k5_play_menu_walk_native import MenuWalker
import nfl2k5_playbook_position_recode as recode


def native_receipt(xbe, raw):
    machine = MenuWalker(xbe, raw)
    rows = []
    for f in insp.parse_playbook_resource(raw).formations:
        expected = [link.play_index for link in f.play_links]
        order, ended = machine.walk(f.index)
        assert ended and order == expected, (f.index, order, expected)
        pages = []
        for n in range((len(expected)+2)//3):
            returned, items = machine.page_builder(f.index, n)
            assert returned and items == expected[n*3:n*3+3], (f.index,n,items)
            pages.append(dict(page=n, returned=True, plays=items))
        rows.append(dict(formation=f.index, name=f.name.strip(), ended=True, plays=order, pages=pages))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--xbe', type=Path, required=True)
    args = ap.parse_args()
    pack_path = ROOT/'data/playbooks/softdrink_giants_modern.2k5book'
    pack = packs.load_pack(pack_path)
    xbe = args.xbe.read_bytes()
    digest = lambda b: hashlib.sha256(b).hexdigest()
    assert digest(xbe) == '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
    with recode.OuterImage(args.image) as source:
        class Overlay:
            entries = source.entries
            pending = {}
            def read_entry(self, index):
                return self.pending[index] if index in self.pending else source.read_entry(index)
            def write(self, offset, payload):
                index = next(e.index for e in self.entries if e.virtual_offset == offset)
                self.pending[index] = bytes(payload)
                return len(payload)
            def entries_with_head(self, head):
                return source.entries_with_head(head)
            def __enter__(self): return self
            def __exit__(self, *args): return False
        overlay = Overlay()
        check = packs.check_pack(pack)
        assert check.ok, check.text()
        pairs = []
        install = packs.apply_packs_to_archive(overlay, [(str(pack_path.relative_to(ROOT)),pack)],
                                             book_entries=recode.BOOK_ENTRIES, collector=pairs, xbe=xbe)
        raw = overlay.read_entry(recode.BOOK_ENTRIES['NYG'])
        proxy = SimpleNamespace(_outer_image=lambda: SimpleNamespace(OuterImage=lambda _:overlay))
        original_core = mod_build._core_module
        with patch.object(mod_build, '_core_module', side_effect=lambda name:
                          proxy if name=='nfl2k5_playbook_pack' else original_core(name)):
            gate = mod_build._check_playbook_menus(args.image, lambda *args:None)
        walked = native_receipt(xbe, raw)
        # PROVED OFFLINE: subsequent optional personnel passes accept the new book.
        entry = source.entries[recode.BOOK_ENTRIES['NYG']]
        book = recode.parse_book('NYG',entry,raw)
        assert recode.book_state(book) == 'retail'
        table, changes = recode.recoded_table(book)
        recoded = bytearray(raw)
        offset = 32 + insp.CATEGORY_BASE
        recoded[offset:offset+len(table)] = table
        normal = roles.normalise(bytes(recoded))
        composed_walk = native_receipt(xbe,normal.replacement)
        assert [r['plays'] for r in composed_walk] == [r['plays'] for r in walked]
        output = dict(status='PROVED OFFLINE', runtime_witness=False,
                      recipe_sha256=digest(pack_path.read_bytes()), xbe_sha256=digest(xbe),
                      install=install, compile=pairs[0][1], build_menu_gate=gate,
                      native_functions=['0xE1320','0xE1360','0xACCE0'],
                      native_scope='Retail instructions under Unicorn; menu UI calls stubbed; no gameplay',
                      formations=len(walked), pages=sum(len(r['pages']) for r in walked),
                      menu_entries=sum(len(r['plays']) for r in walked),
                      unique_plays=len({p for r in walked for p in r['plays']}), walks=walked,
                      composition=dict(position_recode_accepted=True, depth_roles_accepted=True,
                                       changed_defensive_groups=len(changes),
                                       depth_roles_changed_bytes=normal.report['changed_bytes'],
                                       native_replay_passed=True))
    (ROOT/'pb/receipts/offline.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('walks','install','compile')}))


if __name__ == '__main__': main()
