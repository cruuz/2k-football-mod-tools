"""Focused replacement ownership, epoch, source pins and native pool boundaries."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import copy
import datetime as dt
import struct
import unittest
from mod_editor.core import nfl2k5_franchise_history as fh, nfl2k5_career_stats as cs
from tests.mod_editor.test_nfl2k5_career_stats import make_body, row, SOURCE_HASH
from tests.mod_editor.test_nfl2k5_team_history import synthetic_body, entry, games


def spec(seasons=None):
    return dict(schema=fh.SCHEMA,base_year=2026,sources={'test':dict(sha256=SOURCE_HASH,updated_at='2026-09-29',url='synthetic:test')},players=[
        dict(pool='primary',index=0,first='Test',last='Player',birth_date='1976-03-24',gsis_id='test-id',identity_source='test',
             seasons=seasons if seasons is not None else [dict(year=2025,source='test',stats={'games':17,'passing_yards':3668})])])


class ReplacementTests(unittest.TestCase):
    def test_replacement_clears_all_donor_flags_and_current_season(self):
        body=make_body(stream=games([0,1,2,3,4],extra=(entry(3,8,999),entry(2,117,54321,deleted=True,folded=True))))
        out,r=fh.apply_body(body,spec())
        words=cs.decode_body(out).history_words['primary',0]
        self.assertEqual([(cs.Word(w).slot,cs.Word(w).field,w&65535) for w in words],[(3,0,17),(3,8,3668)])
        self.assertLess(r['used_after'],r['used_before'])
        self.assertEqual(fh.apply_body(out,spec())[0],out)
        self.assertEqual(cs.read_csv(cs.export_csv(out,base_year=2026))[-1].season,2025)

    def test_unrelated_stream_is_exactly_preserved_and_missing_source_clears(self):
        body=bytearray(synthetic_body([
            dict(first='Test',last='Player',birth=dt.date(1976,3,24),position=0,count=4,stream=games([3])),
            dict(first='Old',last='Legend',birth=dt.date(1976,3,24),position=0,count=4,stream=games([3],extra=(entry(3,117,54321,folded=True),)))]))
        struct.pack_into('<i',body,0x14,0x2D)
        before=cs.decode_body(body)
        out,r=fh.apply_body(bytes(body),spec([]));after=cs.decode_body(out)
        self.assertFalse(after.history_words['primary',0])
        self.assertEqual(before.history_words['primary',1],after.history_words['primary',1])
        self.assertEqual(r['preserved_players'],1)

    def test_bad_pins_current_season_duplicates_and_values_refuse(self):
        s=spec()
        variants=[]
        for field,value in [('first','Wrong'),('birth_date','1975-03-24'),('gsis_id','')]:
            x=copy.deepcopy(s);x['players'][0][field]=value;variants.append(x)
        x=copy.deepcopy(s);x['players']*=2;variants.append(x)
        x=spec([dict(year=2026,source='test',stats={'games':1})]);variants.append(x)
        x=spec([dict(year=2025,source='test',stats={'games':17,'passing_yards':32768})]);variants.append(x)
        x=spec();x['sources']['test']['sha256']='bad';variants.append(x)
        for x in variants:
            with self.subTest(x=x),self.assertRaises(cs.CareerStatsError):fh.apply_body(make_body(),x)

    def test_team_uses_created_slot_and_never_current_or_donor(self):
        s=spec();season=s['players'][0]['seasons'][0]
        season.update(team_index=3,team_source='test')
        out,_=fh.apply_body(make_body(),s)
        words=cs.decode_body(out).history_words['primary',0]
        self.assertEqual([(cs.Word(w).slot,w&65535) for w in words if cs.Word(w).field==87],[(3,4)])
        self.assertEqual(fh.apply_body(out,s)[0],out)
        season['team_index']=32
        with self.assertRaises(cs.CareerStatsError):fh.apply_body(make_body(),s)

    def test_modern_csv_epoch_is_explicit(self):
        out,_=cs.apply_body(make_body(),[row(season=2025)],base_year=2026)
        self.assertEqual(cs.read_csv(cs.export_csv(out,base_year=2026))[-2].season,2025)
        with self.assertRaises(cs.CareerStatsError):cs.apply_body(make_body(),[row(season=2026)],base_year=2026)


if __name__ == "__main__":
    unittest.main()
