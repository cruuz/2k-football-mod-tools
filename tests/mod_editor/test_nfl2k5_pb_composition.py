"""PROVED OFFLINE: production owner contracts for the 64 authored team packs."""
import copy
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pb.phase4 import ROOT, compile_books, certify_screens
from pb.recipes.compose import compose, KEYS
from mod_editor.core import nfl2k5_play_intents as intents
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_screen_timing as timing
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_nfl2k5_screen_archive import MemoryArchive
from pb.defense.verify import IMAGE, OuterImage, BOOK_ENTRIES


@unittest.skipUnless(IMAGE.is_file(), f"private retail XISO absent: {IMAGE}")
class Composition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=compile_books()

    def test_all_64_versioned_receipts_and_real_spy(self):
        pairs=[]
        for team,off,a,b in self.rows:
            self.assertEqual(a.report['spy_intent'],dict(schema=spy.INTENT_SCHEMA,records=[]))
            self.assertEqual(intents.intent_requests(a.replacement,a.report),[])
            for c in (a,b):
                pairs.append((c.replacement,c.report))
                self.assertEqual(c.report['spy_intent']['schema'],spy.INTENT_SCHEMA)
            records=b.report['spy_intent']['records']
            self.assertEqual(len(records),int(team=='KC'))
        table,receipt=spy.compile_intent_table(pairs)
        self.assertEqual(spy.validate_intent_table(table),1)
        self.assertEqual(receipt['records'][0]['asset_id'],'book:KC')
        a=self.rows[0][2]
        forged=copy.deepcopy(a.report)
        forged['spy_intent']['records']=[dict(play_index=0,slot=5,intent='spy')]
        with self.assertRaisesRegex(intents.PlayIntentError,'complete offense cannot declare'):
            intents.intent_requests(a.replacement,forged)
        missing=copy.deepcopy(a.report);del missing['spy_intent']
        with self.assertRaisesRegex(spy.QbSpyError,'versioned'):
            spy.compile_intent_table([(a.replacement,missing)])
        with self.assertRaisesRegex(spy.QbSpyError,'pairing'):
            spy.compile_intent_table([(a.replacement[:-1]+bytes([a.replacement[-1]^1]),a.report)])

    def test_all_authored_screens_are_declared_D_and_owner_idempotent(self):
        for team,off,a,b in self.rows:
            with self.subTest(team=team):
                certify_screens(a.replacement,off)
                certify_screens(b.replacement,off)
                for c in (a,b):
                    actual,receipt=timing.apply(c.replacement,'D')
                    self.assertEqual(actual,c.replacement)
                    self.assertEqual(receipt['status'],'applied')
                    self.assertEqual(receipt['authored_level'],'D')
                    self.assertEqual(receipt['changed_bytes'],0)
                    for level in 'ABC':
                        self.assertEqual(timing.status(c.replacement,level),'foreign')

    def test_spy_resolves_against_final_pooled_personnel_and_depth_roles(self):
        from mod_editor.core import nfl2k5_depth_roles as roles
        from mod_editor.core.nfl2k5_formation_play_writer import compile_personnel_categories
        from mod_editor.core import nfl2k5_playbook_pack as packs
        recode=packs._outer_image()
        retained=[(c.replacement,c.report) for _,_,a,b in self.rows for c in (a,b)]
        b=next(b for t,_,_,b in self.rows if t=='KC')
        body=b.replacement[32:]
        pooled=compile_personnel_categories(b.replacement,{
            c.index:recode.recode_codes(lib.category_positions(body,c.index),
                body[ip.CATEGORY_BASE+c.index*ip.CATEGORY_SIZE+4])[0]
            for c in b.parsed_replacement.categories},asset_id='book:KC')
        final=roles.normalise(pooled).replacement
        entries=[SimpleNamespace(size=0) for _ in range(344)]
        entries[BOOK_ENTRIES['KC']]=SimpleNamespace(size=len(final))
        archive=SimpleNamespace(entries=entries,read_entry=lambda index:final)
        provider=SimpleNamespace(BOOK_ENTRIES=BOOK_ENTRIES,OuterImage=lambda _:nullcontext(archive))
        with patch.object(packs,'_outer_image',return_value=provider):
            # Recompilation also needs the real category recoder.
            provider.recode_codes=recode.recode_codes
            pairs=intents.resolve_final_pairs('memory',retained)
            table,receipt=spy.compile_intent_table(pairs)
        self.assertEqual(len(pairs),1)
        self.assertEqual(pairs[0][0],final)
        self.assertEqual(spy.validate_intent_table(table),1)
        self.assertEqual(receipt['records'][0]['resource_sha256'],hashlib.sha256(final).hexdigest())

    def test_foreign_partial_or_renamed_authored_screens_refuse(self):
        raw=self.rows[0][3].replacement
        book=ip.parse_playbook_resource(raw)
        p=next(p for p in book.plays if 'screen' in p.name.casefold())
        # PROVED OFFLINE: change one timing byte, header byte, or screen name.
        qb=p.assignments[0]
        body=raw[32:];field=ip.PLAY_BASE+p.index*ip.PLAY_SIZE
        name=field+struct.unpack_from('<i',body,field)[0]-1
        for offset in (32+ip.NODE_BASE+qb.chain_start_index*8+qb.declared_length*8-1,
                       32+field+4,32+name):
            changed=bytearray(raw);changed[offset]^=1
            self.assertEqual(timing.status(bytes(changed),'D'),'foreign')
            with self.assertRaises(ValidationError):timing.apply(bytes(changed),'D')

    def test_full_37_book_screen_transaction_with_retail_utilities(self):
        with OuterImage(IMAGE) as source:
            resources={i:source.read_entry(i) for i in range(307,344)}
        for team,_,_,b in self.rows:resources[BOOK_ENTRIES[team]]=b.replacement
        archive=MemoryArchive(resources)
        receipt=timing.apply_to_archive(archive,'D')
        self.assertEqual(receipt['status'],'applied')
        self.assertEqual(len(receipt['books']),37)
        self.assertEqual(timing.inspect_archive(archive,'D')['status'],'applied')
        again=timing.apply_to_archive(archive,'D')
        self.assertEqual(again['changed_bytes'],0)


class Recipe(unittest.TestCase):
    def test_merge_preserves_all_unrelated_options_and_metadata(self):
        base=json.loads((ROOT/'pb/lab/defense.recipe.json').read_text())
        fragment=json.loads((ROOT/'pb/recipes/final_playbooks.json').read_text())
        source=copy.deepcopy(base)
        source['overrides'].update(qb_spy=True,screen_timing='D',xemu_display_list_fix=True)
        original=copy.deepcopy(source);result=compose(source,fragment)
        self.assertEqual(source,original)
        for key in KEYS:result['overrides'][key]=original['overrides'][key]
        self.assertEqual(result,original)
        bad=copy.deepcopy(fragment);bad['overrides']['qb_spy']=False
        with self.assertRaises(ValueError):compose(source,bad)


if __name__=='__main__':unittest.main()
