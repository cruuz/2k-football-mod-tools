"""Source fidelity and fail-closed Build tests, without proprietary fixtures."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
import nfl2k5_historic_rosters_build as g
import nfl2k5_historic_rosters_author as author
from mod_editor.core import nfl2k5_historic_rosters as h
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as saved


class SourceTests(unittest.TestCase):
    def test_same_printed_name_keeps_article_disambiguation_and_both_players(self):
        text=('==Roster==\n|Running Backs=\n{{NFLplayer|36|Bob Smith|d=fullback}}\n'
              '|Defensive Backs=\n{{NFLplayer|40|Bob Smith|d=defensive back, born 1925}} CB/P\n')
        rows=g.wiki_rows(text,'offline:test')
        merged=[dict(name='Bob Smith',aliases=['Bob Smith'],reserve=False,
                     sources=[dict(kind='wikipedia_roster')],birth_date='1925-08-20')]
        split=author.active_people(merged,rows)
        self.assertEqual([p['wiki_jersey'] for p in split],[36,40])
        self.assertEqual(len({p['name'] for p in split}),2)
        self.assertEqual({p['display_name'] for p in split},{'Bob Smith'})
        self.assertTrue(all(p['birth_date'] is None for p in split))

    def test_authored_same_name_players_keep_separate_sourced_measurements(self):
        team=next(t for t in h.require_build_ready()['teams'] if t['name']=="Lions '53")
        players=[p for p in team['players'] if p['first']=='Bob' and p['last']=='Smith']
        self.assertEqual({(p['jersey'],p['height'],p['weight']) for p in players},
                         {(36,72,204),(40,73,191)})
        self.assertTrue(all(p['fields']['identity_disambiguation']['label']=='INFERRED' for p in players))

    def test_inline_groups_and_singular_defensive_back(self):
        text = ('==Roster==\n{{NFL final roster\n|Quarterbacks=\n'
                '{{NFLplayer|12|A Quarter}}|Tight Ends={{NFLplayer|82|B End}}\n'
                '|defensive_back =\n{{NFLplayer|21|C Back|d=American football|CB}}\n}}\n')
        rows = g.wiki_rows(text, 'offline:test')
        self.assertEqual([(r['jersey'],r['positions']) for r in rows], [(12,['QB']),(82,['TE']),(21,['CB'])])
        self.assertEqual(rows[1]['sources'][0]['line'], 4)

    def test_final_roster_excludes_training_camp(self):
        text = ('==Roster==\n===Opening training camp roster===\n|Quarterbacks=\n'
                '{{NFLplayer|1|Camp Only}}\n===Final roster===\n|Quarterbacks=\n'
                '{{NFLplayer|2|Season Player}}\n==Schedule==\n')
        self.assertEqual([r['name'] for r in g.wiki_rows(text,'offline:test')], ['Season Player'])

    def test_plain_bullets_html_and_display_links(self):
        text = ("==1979 roster==\n'''Quarterbacks'''\n"
                '* <span>16</span> [[Len Dawson]]\n'
                "'''Defensive backs'''\n* {{player|24}} [[Roosevelt Taylor|Rosey Taylor]] FS\n")
        rows = g.wiki_rows(text,'offline:test')
        self.assertEqual([(r['name'],r['positions']) for r in rows], [('Len Dawson',['QB']),('Rosey Taylor',['FS'])])

    def test_baseball_article_never_supplies_football_players(self):
        text = "==Roster==\n'''Pitchers'''\n{{MLBplayer|45|[[Bob Gibson]]}}\n"
        self.assertEqual(g.wiki_rows(text,'offline:test'), [])
        self.assertEqual(g.wiki_rows('{{Infobox baseball team season}}\n==Roster==\n'
                                     '* 45 [[Bob Gibson]] P\n','offline:test'), [])

    def test_abbreviated_identity_match_retains_review_requirement(self):
        row = dict(jersey_number='12', full_name='William Player',first_name='William',last_name='Player',
                   depth_chart_position='QB',position='QB',height='72',weight='200',birth_date='',
                   status='ACT',source_file='roster_1960.csv',source_line=2)
        wiki=[dict(name='W. Player',jersey=12,positions=['QB'],reserve=False,sources=[])]
        merged=g.merge_sources(wiki,[row],1960)[0]
        self.assertEqual(merged['identity_reviews'][0]['label'],'INFERRED')

    def test_source_position_disagreement_is_retained_for_review(self):
        row = dict(jersey_number='12', full_name='Real Player',first_name='Real',last_name='Player',
                   depth_chart_position='QB',position='QB',height='72',weight='200',birth_date='',
                   status='ACT',source_file='roster_1960.csv',source_line=2)
        wiki=[dict(name='Real Player',jersey=12,positions=['HB','FB'],reserve=False,sources=[])]
        merged=g.merge_sources(wiki,[row],1960)[0]
        self.assertEqual(merged['conflicts'],[dict(field='position',nflverse=['QB'],wikipedia=['HB','FB'])])

    def test_legacy_end_uses_the_source_group(self):
        text = ('==Roster==\n|Defensive linemen=\n{{NFLplayer|80|Defense End|E}}\n'
                '|Wide receivers=\n{{NFLplayer|81|Offense End|E}}\n')
        rows=g.wiki_rows(text,'offline:test')
        self.assertEqual([r['positions'] for r in rows],[['DE'],['WR']])

    def test_zero_nflverse_number_stays_missing(self):
        row = dict(jersey_number='0', full_name='Real Player',first_name='Real',last_name='Player',
                   depth_chart_position='QB',position='QB',height='72',weight='200',birth_date='',
                   status='ACT',source_file='roster_1960.csv',source_line=2)
        player = g.merge_sources([], [row], 1960)[0]
        self.assertIsNone(player['jersey'])
        self.assertEqual(player['height'],72)

    def test_starters_use_explicit_markup_and_game_lineup_citations(self):
        text = ("==Roster==\n|Quarterbacks=\n{{NFLplayer|'''12'''|Named Starter}}\n"
                "Starters in bold\n==Game==\n{|\n! Starting Lineups\n"
                "| QB || [[Named Starter]]\n|}\n"
                "|QB_Starter = 12 [[Named Starter]]\n")
        people = [dict(name='Named Starter',aliases=['Named Starter'])]
        rows = g.wiki_rows(text,'offline:test')
        starters = g.wiki_starters(text,'offline:test',people,rows)
        self.assertEqual(len(starters),1)
        self.assertEqual(starters[0]['name'],'Named Starter')
        self.assertEqual({s['kind'] for s in starters[0]['sources']},
                         {'wikipedia_starter','wikipedia_bold_starter','wikipedia_game_start'})

    def test_sources_are_bounded_to_the_exact_season(self):
        data = h.dataset()
        self.assertEqual(len(data['teams']),75)
        for team in data['teams']:
            self.assertEqual([p['slot'] for p in team['players']],list(range(len(team['players']))))
            self.assertTrue(30 <= len(team['players']) <= 65)
            names = [g.norm(p['player']) for p in team['players'] if p.get('player')]
            self.assertEqual(len(names),len(set(names)))
            for p in team['players']:
                if not p.get('player'):
                    self.assertTrue(p['blockers'])
                    continue
                self.assertTrue(p['sources'])
                for s in p['sources']:
                    if s['kind']=='nflverse':
                        self.assertIn(f"roster_{team['season']}.csv",s['url'])
                self.assertEqual(set(p['ratings']),set(rr.RATING_BYTE_ORDER))


class RatingTests(unittest.TestCase):
    @staticmethod
    def team(year, values, position='QB'):
        return dict(year=year,slots=[dict(slot=i,position=position,match='unique_number_position',
                    ratings={k:v for k in rr.RATING_BYTE_ORDER}) for i,v in enumerate(values)])

    def test_same_era_and_position_excludes_modern_extremes(self):
        teams = [self.team(1962,list(range(40,48))),self.team(2003,[100]*8),self.team(1962,[99]*8,'T')]
        ratings, basis = h.era_ratings(teams,1963,'QB')
        self.assertEqual(set(ratings.values()),{44})
        self.assertEqual((basis['era'],basis['donors']),([1960,1964],8))
        starter,_ = h.era_ratings(teams,1963,'QB',True)
        self.assertEqual(set(starter.values()),{45})

    def test_sparse_era_widens_symmetrically_and_is_deterministic(self):
        teams = [self.team(1968,list(range(60,68)))]
        one = h.era_ratings(teams,1963,'QB')
        self.assertEqual(one,h.era_ratings(teams,1963,'QB'))
        self.assertEqual(one[1]['era'],[1955,1969])

    def test_unmatched_retail_slots_are_not_donors(self):
        team = self.team(1963,[99]*8)
        for s in team['slots']:
            s['match']='unmatched'
        with self.assertRaises(h.HistoricRostersError):
            h.era_ratings([team],1963,'QB')


@unittest.skipUnless((g.DEFAULT_RETAIL/'default.xbe').is_file(),'local retail extraction absent')
class WriterEquipmentTests(unittest.TestCase):
    def test_alias_bytes_do_not_depend_on_helmets_writer_order(self):
        from mod_editor.core import nfl2k5_modern_helmets as hm
        edits=hm.historic_edits()
        checked=0
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(g.DEFAULT_RETAIL)
        with rr._outer_image()(g.DEFAULT_RETAIL) as archive:
            for team in h.require_build_ready()['teams']:
                if team['outer'] not in edits:
                    continue
                with self.subTest(team=team['name']):
                    raw=archive.read_entry(team['outer'])
                    classic=hm.compile_historic(raw,team['outer'],edits)
                    self.assertEqual(h.compile_team(raw,team),h.compile_team(classic,team))
                    doc=rr.RosterDocument(h.compile_team(raw,team)[32:])
                    self.assertEqual({p.record.get('helmet') for p in doc.players},{0})
                    self.assertTrue({p.record.get('face_mask') for p in doc.players}<=set(range(12)))
                    checked+=1
        self.assertEqual(checked,9)


class BuildTests(unittest.TestCase):
    def test_off_everywhere_and_saved(self):
        self.assertFalse(mod_build.BuildPlan('','').historic_rosters_2026)
        self.assertIn('historic_rosters_2026',saved.FEATURE_KEYS)
        self.assertTrue(all(p['historic_rosters_2026'] is False for p in mod_build.PRESETS.values()))

    def test_incomplete_draft_refuses_before_build(self):
        data=copy.deepcopy(h.dataset())
        data['teams'][0]['players'][0]['blockers']=['missing source']
        with patch.object(h,'dataset',return_value=data):
            with self.assertRaisesRegex(h.HistoricRostersError,'unresolved slots'):
                h.require_build_ready()

    def test_ready_flag_cannot_hide_gaps(self):
        data = copy.deepcopy(h.dataset())
        data['ready']=True
        for t in data['teams']:
            t['ready']=True
        data['teams'][0]['players'][0]['blockers']=['missing source']
        with patch.object(h,'dataset',return_value=data):
            with self.assertRaisesRegex(h.HistoricRostersError,'unresolved slots'):
                h.require_build_ready()

    def test_no_silent_shared_moment_overwrite_after_data_gate(self):
        data=h.require_build_ready()
        self.assertEqual(len({t['alias'] for t in data['teams']}),75)
        self.assertFalse({t['alias'] for t in data['teams']} & {t['filename'] for t in data['teams']})

    def test_ready_cannot_bypass_citation_or_numeric_validation(self):
        data=copy.deepcopy(h.dataset())
        data['teams'][0]['players'][0]['fields']['height']={}
        with patch.object(h,'dataset',return_value=data):
            with self.assertRaisesRegex(h.HistoricRostersError,'uncited height'):
                h.require_build_ready()

    def test_inline_metadata_before_group_does_not_make_quarterbacks_reserves(self):
        text=('==Roster==\n|Reserve Lists=\n{{NFLplayer|59|A Reserve|LB|IR}}'
              '|Active=47|Inactive=11|Quarterbacks={{NFLplayer|7|A Starter}}\n')
        rows=g.wiki_rows(text,'offline:test')
        self.assertFalse(rows[-1]['reserve'])
        self.assertEqual(rows[-1]['positions'],['QB'])

    def test_outside_template_two_way_roles_survive(self):
        rows=g.wiki_rows('==Roster==\n|Defensive Backs=\n{{NFLplayer|28|A Safety}} S/P\n','offline:test')
        self.assertEqual(rows[0]['positions'],['FS','P','SS'])


if __name__=='__main__':
    unittest.main()
