"""Fast player-CSV regression with generated records only, including real-save layouts."""
import csv
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests/mod_editor', ROOT / 'tests', ROOT / 'tools'):
    sys.path.insert(0, str(path))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QDialog, QDialogButtonBox
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel, PlayerCsvPreviewDialog
from test_nfl2k5_roster_records import synthetic_body, synthetic_save_v0, league_body, SAMPLE
from test_nfl2k5_franchise_save import synthetic_franchise
from test_roster_editor_panel_franchise import write_container


def change_csv(text, index=0, **changes):
    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames
    rows = list(reader)
    rows[index].update(changes)
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


TOOL_HEADER = ("#Position,fname,lname,JerseyNumber,Speed,Agility,Strength,Jumping,Coverage,"
               "PassRush,RunCoverage,PassBlocking,RunBlocking,Catch,RunRoute,BreakTackle,"
               "HoldOntoBall,PowerRunStyle,PassAccuracy,PassArmStrength,PassReadCoverage,Tackle,"
               "KickPower,KickAccuracy,Stamina,Durability,Leadership,Scramble,Composure,"
               "Consistency,Aggressiveness,College,DOB,PBP,Photo,YearsPro,Hand,Weight,Height,"
               "BodyType,Skin,Face,Dreads,Helmet,FaceMask,Visor,EyeBlack,MouthPiece,LeftGlove,"
               "RightGlove,LeftWrist,RightWrist,LeftElbow,RightElbow,Sleeves,LeftShoe,RightShoe,"
               "NeckRoll,Turtleneck,")


def compact(value):
    return str(value).replace(' ', '').replace('/', '')


def tool_shoe(value):
    return 'Taped' if value == 6 else f'Shoe{value + 1}'


def tool_row(document, player):
    row = rr._csv_row(document, player)
    birth = rr.dt.date.fromisoformat(row['birth_date'])
    return [
        row['position'], player.first, player.last, str(row['jersey']),
        *[str(row[column]) for column in
          ('speed', 'agility', 'strength', 'jumping', 'coverage', 'pass_rush', 'run_coverage',
           'pass_blocking', 'run_blocking', 'catch', 'run_route', 'break_tackle', 'hold_onto_ball')],
        str(row['power_run_style']),
        *[str(row[column]) for column in
          ('pass_accuracy', 'pass_arm_strength', 'pass_read_coverage', 'tackle', 'kick_power',
           'kick_accuracy', 'stamina', 'durability', 'leadership', 'scramble', 'composure',
           'consistency', 'aggressiveness')],
        row['college'], f'{birth.month}/{birth.day}/{birth.year}',
        f"{row['pbp_id']:04d}", f"{row['photo_id']:04d}", str(row['years_pro']),
        row['hand'], str(row['weight']), f"{row['height'] // 12}'{row['height'] % 12}\"",
        compact(row['body']), compact(rr.SKINS[row['skin']]), compact(rr.FACES[row['face']]),
        row['dreads'], row['helmet'], compact(rr.FACE_MASKS[row['face_mask']]),
        row['face_shield'], row['eye_black'], row['mouthpiece'],
        compact(rr.GLOVES[row['left_glove']]), compact(rr.GLOVES[row['right_glove']]),
        compact(rr.WRISTS[row['left_wrist']]), compact(rr.WRISTS[row['right_wrist']]),
        compact(rr.ELBOWS[row['left_elbow']]), compact(rr.ELBOWS[row['right_elbow']]),
        row['sleeves'], tool_shoe(row['left_shoe']), tool_shoe(row['right_shoe']),
        row['neck_roll'], row['turtleneck'],
    ]


TOOL_FIELDS = [name.lstrip('#') for name in TOOL_HEADER.rstrip(',').split(',')]
TOOL_INDEX = {name: index for index, name in enumerate(TOOL_FIELDS)}


def tool_export_one(document, player, **columns):
    """One real tool row with selected columns replaced, ready for a one-team section."""
    values = tool_row(document, player)
    for name, value in columns.items():
        values[TOOL_INDEX[name]] = str(value)
    return (TOOL_HEADER + '\n' + f"Team = {rr._csv_row(document, player)['team']}    Players:1\n"
            + ','.join(values) + ',\n')


def tool_export(document):
    lines = [TOOL_HEADER]
    for team in document.teams:
        members = [document.by_offset[offset] for offset in team.slots
                   if offset in document.by_offset]
        if not members:
            continue
        lines.append(f'Team = {team.abbreviation}    Players:{len(members)}')
        lines.extend(','.join(tool_row(document, player)) + ',' for player in members)
    free_agents = [document.by_offset[offset] for offset in document.free_agents
                   if offset in document.by_offset]
    if free_agents:
        lines.append(f'Team = FreeAgents    Players:{len(free_agents)}')
        lines.extend(','.join(tool_row(document, player)) + ',' for player in free_agents)
    return '\n'.join(lines) + '\n'


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.doc = rr.load_body(synthetic_body())

    def test_every_page_field_and_rating_has_a_column(self):
        self.assertTrue(set(sum(rr.ATTRIBUTE_CARDS.values(), ())) <= set(rr.CSV_COLUMNS))
        self.assertTrue(set(rr.RATING_BYTE_ORDER) <= set(rr.CSV_COLUMNS))
        self.assertEqual(len(rr.CSV_COLUMNS), len(set(rr.CSV_COLUMNS)))

    def test_one_cell_is_one_edit_preview_never_mutates_then_readback_matches(self):
        before = self.doc.to_body()
        text = rr.export_csv(self.doc)
        noop = rr.preview_csv(self.doc, text)
        self.assertEqual((noop.receipt['changed'], noop.receipt['fields']), (0, 0))
        edited = change_csv(text, speed='77')
        preview = rr.preview_csv(self.doc, edited)
        self.assertEqual(self.doc.to_body(), before)
        self.assertEqual((preview.receipt['changed'], preview.receipt['fields']), (1, 1))
        self.assertEqual(preview.receipt['changes'][0]['changes'], [{'field': 'speed', 'before': 66, 'after': 77}])
        rr.apply_csv_preview(self.doc, preview)
        self.assertEqual(rr.load_body(self.doc.to_body()).players[0].record.get('speed'), 77)
        self.assertEqual(rr.import_csv(self.doc, edited)['fields'], 0)

    def test_no_name_fallback_and_duplicate_pins_are_all_refused(self):
        with self.assertRaisesRegex(rr.RosterRecordError, 'pool \\+ index'):
            rr.preview_csv(self.doc, 'first,last,speed\nPeyton,Manning,77\n')
        for pins in ('primary,999', 'primary,-1', 'primary,1.0', 'unknown,0', 'primary,'):
            receipt = rr.import_csv(self.doc, 'pool,index,first,last,speed\n' + pins + ',Peyton,Manning,77\n')
            self.assertEqual(receipt['changed'], 0)
            self.assertEqual(len(receipt['refused']), 1)
        duplicate = 'pool,index,speed\nprimary,0,77\nprimary,00,80\n'
        receipt = rr.import_csv(self.doc, duplicate)
        self.assertEqual((receipt['changed'], len(receipt['refused'])), (0, 2))

    def test_nfl2k5tool_fixture_imports_retail_ratings(self):
        before = self.doc.to_body()
        players = len(self.doc.players)
        text = ("#Position,fname,lname,JerseyNumber,Speed,Agility,Strength,Consistency,PowerRunStyle,\n"
                "Team = IND    Players:3\n"
                "QB,Peyton,Manning,18,77,78,60,80,Power,\n"
                "WR,Marvin,Harrison,88,88,48,53,73,Balanced,\n"
                "HB,Edgerrin,James,32,85,51,56,76,Finesse,\n")
        self.assertEqual(rr.detect_csv_format(text), rr.NFL2K5TOOL_CSV)
        preview = rr.preview_csv(self.doc, text)
        self.assertEqual(self.doc.to_body(), before)
        self.assertEqual((preview.receipt['rows'], preview.receipt['changed']), (3, 3))
        self.assertEqual(preview.receipt['fields'], 9)
        self.assertFalse(preview.receipt['refused'])
        changes = {change['row']: {field['field']: field for field in change['changes']}
                   for change in preview.receipt['changes']}
        self.assertEqual(set(changes[3]), {'speed', 'agility', 'strength', 'consistency',
                                           'power_run_style'})
        self.assertEqual((changes[3]['speed']['before'], changes[3]['speed']['after']), (66, 77))
        self.assertEqual(changes[4]['power_run_style']['after'], 50)
        self.assertEqual(changes[5]['power_run_style']['after'], 1)
        rr.apply_csv_preview(self.doc, preview)
        reread = rr.load_body(self.doc.to_body())
        self.assertEqual(len(reread.players), players)
        manning = reread.players[0].record
        self.assertEqual((manning.get('speed'), manning.get('agility'), manning.get('strength'),
                          manning.get('consistency'), manning.get('power_run_style')),
                         (77, 78, 60, 80, 99))
        self.assertEqual(reread.players[1].record.get('power_run_style'), 50)
        self.assertEqual(reread.players[2].record.get('power_run_style'), 1)

    def test_nfl2k5tool_full_export_round_trips_every_column(self):
        self.assertTrue(set(rr.NFL2K5TOOL_COLUMNS.values()) <= set(rr.CSV_COLUMNS))
        self.assertEqual(len(rr.NFL2K5TOOL_RATING_COLUMNS), 27)
        self.assertTrue({rr.NFL2K5TOOL_COLUMNS[name]
                         for name in rr.NFL2K5TOOL_RATING_COLUMNS} <= set(rr.CSV_COLUMNS))
        before = self.doc.to_body()
        text = tool_export(self.doc)
        self.assertNotIn('Team = DraftClass', text)
        receipt = rr.import_csv(self.doc, text)
        self.assertEqual(receipt['format'], rr.NFL2K5TOOL_CSV)
        self.assertFalse(receipt['refused'])
        self.assertTrue(receipt['rating_only'])
        self.assertEqual(len(receipt['ignored_columns']),
                         len(rr.NFL2K5TOOL_COLUMNS) - 27)
        self.assertEqual((receipt['rows'], receipt['changed'], receipt['fields']), (7, 0, 0))
        self.assertEqual(self.doc.to_body(), before)
        receipt = rr.import_csv(self.doc, text, include_appearance=True)
        self.assertFalse(receipt['rating_only'])
        self.assertEqual(receipt['ignored_columns'], [])
        self.assertEqual((receipt['rows'], receipt['changed'], receipt['fields']), (7, 0, 0))
        self.assertEqual(self.doc.to_body(), before)

    def test_nfl2k5tool_default_ignores_appearance_photo_pbp_and_reports_them(self):
        player = self.doc.players[0]
        initial = dict(player.record.values)
        initial_college, initial_birth = player.college, player.record.birth_date
        initial_weight, initial_position = player.record.weight, player.record.position_code
        initial_skin = player.record.skin
        text = tool_export_one(
            self.doc, player,
            Position='WR', JerseyNumber='99', Speed='99',
            College='Nowhere', DOB='not-a-date', PBP='8888', Photo='9999',
            Height='tall', Weight='250', Skin='Skin23', Face='Face99')
        preview = rr.preview_csv(self.doc, text)
        self.assertEqual(preview.receipt['format'], rr.NFL2K5TOOL_CSV)
        self.assertTrue(preview.receipt['rating_only'])
        self.assertEqual((preview.receipt['rows'], preview.receipt['changed'],
                          preview.receipt['fields']), (1, 1, 1))
        self.assertFalse(preview.receipt['refused'])
        self.assertEqual(preview.receipt['changes'][0]['changes'],
                         [{'field': 'speed', 'before': 66, 'after': 99}])
        ignored = preview.receipt['ignored_columns']
        self.assertEqual(len(ignored), len(rr.NFL2K5TOOL_NON_RATING_COLUMNS))
        self.assertTrue({'position', 'jerseynumber', 'college', 'dob', 'pbp', 'photo',
                         'height', 'weight', 'skin', 'face'} <= set(ignored))
        rr.apply_csv_preview(self.doc, preview)
        reread = rr.load_body(self.doc.to_body()).players[0]
        self.assertEqual(reread.record.get('speed'), 99)
        for name in ('jersey', 'pbp_id', 'photo_id', 'height', 'face'):
            self.assertEqual(reread.record.values[name], initial[name], name)
        self.assertEqual(reread.record.weight, initial_weight)
        self.assertEqual(reread.record.skin, initial_skin)
        self.assertEqual(reread.record.position_code, initial_position)
        self.assertEqual(reread.college, initial_college)
        self.assertEqual(reread.record.birth_date, initial_birth)

    def test_nfl2k5tool_appearance_opt_in_imports_them(self):
        player = self.doc.players[0]
        self.assertNotEqual(player.college, 'Michigan')
        text = tool_export_one(
            self.doc, player,
            Position='WR', JerseyNumber='99', Speed='97',
            College='Michigan', DOB='1/1/1990', PBP='8888', Photo='9999',
            Height='5\'5"', Weight='250', Skin='Skin4', Face='Face3')
        preview = rr.preview_csv(self.doc, text, include_appearance=True)
        self.assertFalse(preview.receipt['rating_only'])
        self.assertEqual(preview.receipt['ignored_columns'], [])
        self.assertFalse(preview.receipt['refused'])
        fields = {field['field'] for change in preview.receipt['changes']
                  for field in change['changes']}
        self.assertTrue({'speed', 'position', 'jersey', 'college', 'birth_date', 'pbp_id',
                         'photo_id', 'height', 'weight', 'skin', 'face'} <= fields)
        rr.apply_csv_preview(self.doc, preview)
        reread = rr.load_body(self.doc.to_body()).players[0]
        self.assertEqual(reread.record.get('speed'), 97)
        self.assertEqual(reread.record.values['jersey'], 99)
        self.assertEqual(reread.record.values['photo_id'], 9999)
        self.assertEqual(reread.record.values['pbp_id'], 8888)
        self.assertEqual(reread.record.values['height'], 65)
        self.assertEqual(reread.record.weight, 250)
        self.assertEqual(reread.record.skin, 3)
        self.assertEqual(reread.record.values['face'], 2)
        self.assertEqual(reread.college, 'Michigan')
        self.assertEqual(reread.record.birth_date, rr.dt.date(1990, 1, 1))

    def test_nfl2k5tool_fixture_imports_into_the_retail_roster(self):
        from test_nfl2k5_roster_records import RETAIL_EXTRACTION, retail_body
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs

        require_nfl_retail_packs(RETAIL_EXTRACTION)
        document = rr.load_body(retail_body())
        team = document.teams[0]
        player = document.by_offset[team.slots[0]]
        values = tool_row(document, player)
        speed = int(values[4])
        values[4] = str(speed + 1 if speed < 99 else speed - 1)
        text = (TOOL_HEADER + "\n" + f"Team = {team.abbreviation}    Players:1\n"
                + ",".join(values) + ",\n")
        receipt = rr.import_csv(document, text)
        self.assertEqual((receipt['rows'], receipt['changed'], receipt['fields']), (1, 1, 1))
        self.assertFalse(receipt['refused'])
        self.assertEqual(player.record.get('speed'), int(values[4]))
        self.assertEqual((player.first, player.last), ('Ahmed', 'Plummer'))

    def test_nfl2k5tool_face_high_bits_use_the_studio_low_nibble(self):
        text = ("#Position,fname,lname,JerseyNumber,Face,\n"
                "Team = IND    Players:3\n"
                "QB,Peyton,Manning,18,21,\n"
                "WR,Marvin,Harrison,88,Face17,\n"
                "HB,Edgerrin,James,32,Face16,\n")
        receipt = rr.import_csv(self.doc, text, include_appearance=True)
        self.assertEqual((receipt['changed'], receipt['fields']), (1, 1))
        self.assertFalse(receipt['refused'])
        self.assertEqual(receipt['changes'][0]['changes'],
                         [{'field': 'face', 'before': 0, 'after': 5}])
        self.assertEqual(self.doc.players[0].record.values['face'], 5)
        self.assertEqual(self.doc.players[1].record.values['face'], 0)
        self.assertEqual(self.doc.players[2].record.values['face'], 0)

    def test_nfl2k5tool_unmatched_ambiguous_and_unknown_teams_refuse(self):
        second = ('Peyton', 'Manning', 0, 19, 7, 230, 77, rr.dt.date(1976, 3, 24), 0, 66, 0)
        doc = rr.load_body(synthetic_body([SAMPLE[0], second, SAMPLE[1]]))
        text = ("#Position,fname,lname,JerseyNumber,Speed,\n"
                "Team = IND    Players:3\n"
                "QB,Peyton,Manning,,80,\n"
                "QB,Peyton,Manning,19,81,\n"
                "QB,Nobody,Here,5,80,\n"
                "Team = Atlantis\n"
                "QB,Peyton,Manning,18,80,\n"
                "Team = DraftClass\n"
                "QB,Draft,Prospect,99,60,\n")
        receipt = rr.import_csv(doc, text)
        self.assertEqual(receipt['format'], rr.NFL2K5TOOL_CSV)
        self.assertEqual((receipt['changed'], receipt['fields']), (1, 1))
        self.assertEqual(len(receipt['refused']), 4)
        reasons = [row['reason'] for row in receipt['refused']]
        self.assertTrue(any('ambiguous' in reason for reason in reasons))
        self.assertTrue(any('no City0 Team0 player named Nobody Here' in reason for reason in reasons))
        self.assertTrue(any('not in this loaded roster' in reason for reason in reasons))
        self.assertTrue(any('DraftClass' in reason for reason in reasons))
        self.assertEqual(len(doc.players), 3)
        self.assertEqual(doc.players[0].record.get('speed'), 66)
        self.assertEqual(doc.players[1].record.get('speed'), 81)

    def test_nfl2k5tool_duplicate_rows_refuse_every_occurrence(self):
        text = ("#Position,fname,lname,JerseyNumber,Speed,\n"
                "Team = IND\n"
                "QB,Peyton,Manning,18,80,\n"
                "QB,Peyton,Manning,18,81,\n")
        receipt = rr.import_csv(self.doc, text)
        self.assertEqual((receipt['changed'], receipt['fields']), (0, 0))
        self.assertEqual(len(receipt['refused']), 2)
        self.assertTrue(all('duplicate player' in row['reason'] for row in receipt['refused']))
        self.assertEqual(self.doc.players[0].record.get('speed'), 66)

    def test_nfl2k5tool_header_and_cell_errors_refuse_cleanly(self):
        for text, message in [
                ('#Position,fname,lname,Mystery,\nQB,Pat,Player,1,\n', 'not recognized'),
                ('#Position,fname,lname,Depth,\nQB,Pat,Player,1,\n', 'no Studio CSV field'),
                ('#Position,Speed,\nQB,77,\n', 'fname and lname'),
                ('#Position,fname,lname,Speed,Speed,\nQB,Pat,Player,1,2,\n', 'Duplicate')]:
            with self.subTest(text=text), self.assertRaisesRegex(rr.RosterRecordError, message):
                rr.preview_csv(self.doc, text)
        for header, value in [('Speed', 'fast'), ('Height', 'tall'), ('DOB', 'not-a-date')]:
            with self.subTest(header=header):
                text = (f"#Position,fname,lname,{header},\n"
                        "Team = IND    Players:1\n"
                        f"QB,Peyton,Manning,{value},\n")
                receipt = rr.import_csv(self.doc, text, include_appearance=True)
                self.assertEqual((receipt['changed'], receipt['fields']), (0, 0))
                self.assertEqual(len(receipt['refused']), 1)
                self.assertIn(header.casefold(), receipt['refused'][0]['reason'].casefold())

    def test_nfl2k5tool_bom_semicolons_and_crlf_are_safe(self):
        text = ("\ufeff#Position;fname;lname;JerseyNumber;Speed;\r\n"
                "Team = IND    Players:1\r\n"
                "QB;Peyton;Manning;18;77;\r\n"
                "KR1;WR2\r\nKR2;HB1\r\nPR;CB3\r\nLS;TE1\r\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'the1wam-ratings.csv'
            path.write_text(text, encoding='utf-8', newline='')
            loaded = path.read_text(encoding='utf-8-sig')
        receipt = rr.import_csv(self.doc, loaded)
        self.assertEqual((receipt['rows'], receipt['changed'], receipt['fields']), (1, 1, 1))
        self.assertFalse(receipt['refused'])
        self.assertEqual(self.doc.players[0].record.get('speed'), 77)
        prefixed = text.replace('#Position', 'Key=Position', 1)
        self.assertEqual(rr.detect_csv_format(prefixed), rr.NFL2K5TOOL_CSV)

    def test_studio_csv_round_trip_is_unchanged_and_not_mistaken_for_the_tool(self):
        text = rr.export_csv(self.doc)
        self.assertEqual(rr.detect_csv_format(text), rr.STUDIO_CSV)
        before = self.doc.to_body()
        receipt = rr.import_csv(self.doc, text)
        self.assertEqual((receipt['changed'], receipt['fields'], receipt['refused']), (0, 0, []))
        self.assertEqual(self.doc.to_body(), before)
        self.assertNotIn('format', receipt)

    def test_secondary_pool_and_duplicate_names_have_exact_identity(self):
        body = bytearray(synthetic_body([SAMPLE[0], SAMPLE[0]]))
        # Both records have the same name and index zero in different pools.
        struct.pack_into('<I', body, rr.OBJ_OFF, 1)
        struct.pack_into('<I', body, rr.OBJ_OFF + 8, 1)
        field = rr.OBJ_OFF + 12
        target = 0xAFA8 + rr.PLAYER_SIZE
        struct.pack_into('<i', body, field, target - field + 1)
        doc = rr.load_body(body)
        receipt = rr.import_csv(doc, 'pool,index,speed\nsecondary,0,77\n')
        self.assertEqual(receipt['fields'], 1)
        self.assertEqual([p.record.get('speed') for p in doc.players], [66, 77])

    def test_bad_cells_refuse_entire_row_and_good_rows_still_preview(self):
        for field, value in [('jersey', '100'), ('height', '59'), ('weight', '406'),
                             ('speed', '128'), ('years_pro', '32'), ('hand', '2'),
                             ('contract_value', '65536'), ('contract_type', '8'),
                             ('birth_month', '13'), ('birth_year', '9999'), ('skin', '32'),
                             ('throw_style', '2'), ('power_run_style_bucket', '3'),
                             ('photo_id', '12345678901234567890')]:
            with self.subTest(field=field):
                before = self.doc.to_body()
                receipt = rr.import_csv(self.doc, f'pool,index,first,{field}\nprimary,0,Pat,{value}\n')
                self.assertEqual(self.doc.to_body(), before)
                self.assertEqual((receipt['changed'], len(receipt['refused'])), (0, 1))
                self.assertIn(field, receipt['refused'][0]['reason'])
        preview = rr.preview_csv(self.doc, 'pool,index,speed\nprimary,0,999\nprimary,1,80\n')
        self.assertEqual((preview.receipt['changed'], len(preview.receipt['refused'])), (1, 1))

    def test_headers_width_bom_and_quoting(self):
        for text in ('pool,index,speed,speed\nprimary,0,1,2\n',
                     'pool,index,mystery\nprimary,0,3\n', 'pool,index,first\nprimary,0,"unterminated'):
            with self.assertRaises(rr.RosterRecordError):
                rr.preview_csv(self.doc, text)
        for text in ('pool,index,speed\nprimary,0,2,3\n', 'pool,index,speed\nprimary,0\n'):
            self.assertEqual(len(rr.preview_csv(self.doc, text).receipt['refused']), 1)
        self.assertEqual(rr.import_csv(self.doc, '\ufeff' + rr.export_csv(self.doc))['fields'], 0)

    def test_excel_text_protection_is_reversible_and_no_formulas_are_emitted(self):
        sample = list(SAMPLE)
        sample[0] = ('007', '12345678901234567890', *sample[0][2:])
        sample[1] = ('=1+1', "'Label", *sample[1][2:])
        sample[2] = ('Éd', 'Comma,Quote"', *sample[2][2:])
        doc = rr.load_body(synthetic_body(sample))
        exported = rr.export_csv(doc)
        rows = list(csv.DictReader(io.StringIO(exported)))
        self.assertEqual(rows[0]['first'], "'007")
        self.assertEqual(rows[0]['last'], "'12345678901234567890")
        self.assertEqual(rows[1]['first'], "'=1+1")
        self.assertEqual(rows[1]['last'], "''Label")
        self.assertEqual(rows[2]['last'], 'Comma,Quote"')
        self.assertEqual(rr.import_csv(doc, exported)['fields'], 0)
        self.assertEqual(doc.to_body(), synthetic_body(sample))

    def test_stale_preview_refuses_and_out_of_range_unchanged_bytes_stay(self):
        self.doc.players[0].record.set('speed', 255)
        self.assertEqual(rr.import_csv(self.doc, rr.export_csv(self.doc))['fields'], 0)
        preview = rr.preview_csv(self.doc, 'pool,index,jersey\nprimary,0,12\n')
        self.doc.players[1].record.set('speed', 77)
        with self.assertRaisesRegex(rr.RosterRecordError, 'changed after'):
            rr.apply_csv_preview(self.doc, preview)

    def test_raw_and_derived_style_conflicts_refuse_regardless_of_column_order(self):
        for header, values in [('power_run_style,power_run_style_bucket', '10,2'),
                               ('power_run_style_bucket,power_run_style', '2,10'),
                               ('scramble,throw_style', '10,1')]:
            doc = rr.load_body(synthetic_body())
            doc.players[0].record.set('power_run_style', 50)
            doc.players[0].record.set('scramble', 50)
            before = doc.to_body()
            receipt = rr.import_csv(doc, f'pool,index,{header}\nprimary,0,{values}\n')
            self.assertEqual(len(receipt['refused']), 1)
            self.assertEqual(doc.to_body(), before)

    def test_returner_transfer_previews_the_previous_owner_too(self):
        self.doc.set_depth_lock(self.doc.players[1], 'kr1', True)
        preview = rr.preview_csv(self.doc, 'pool,index,lock_kr1\nprimary,2,1\n')
        self.assertEqual(preview.receipt['changed'], 2)
        self.assertEqual({r['index'] for r in preview.receipt['changes']}, {1, 2})
        self.assertTrue(self.doc.players[1].record.depth_locks['kr1'])

    def test_full_sheet_unchanged_later_row_does_not_reclaim_a_transferred_lock(self):
        self.doc.set_depth_lock(self.doc.players[2], 'kr1', True)
        text = change_csv(rr.export_csv(self.doc), index=1, lock_kr1='1')
        receipt = rr.import_csv(self.doc, text)
        self.assertFalse(receipt['refused'])
        self.assertTrue(self.doc.players[1].record.depth_locks['kr1'])
        self.assertFalse(self.doc.players[2].record.depth_locks['kr1'])
        self.assertEqual(receipt['changed'], 2)


class CsvCheckpointEquivalenceTests(unittest.TestCase):
    """b779 rv1: the cheap college rollback must give exactly the old whole-document checkpoint's result.

    The reviewer's 1,696-row file took 638.8 s with the box ticked because every college row deep-copied
    the roster. ``_full_checkpoints=True`` is that old behaviour, kept as the reference.
    """

    def setUp(self):
        self.doc = rr.load_body(league_body())

    def _mixed_sheet(self):
        text = rr.export_csv(self.doc)
        reader = csv.DictReader(io.StringIO(text))
        columns = reader.fieldnames
        rows = list(reader)
        self.assertGreater(columns.index('speed'), columns.index('college'))
        colleges = self.doc.colleges
        self.assertGreaterEqual(len(colleges), 3)
        for i, row in enumerate(rows):
            kind = i % 6
            if kind == 0:      # a valid college change alone
                row['college'] = colleges[(self.doc.players[i].college_index + 1) % len(colleges)]
            elif kind == 1:    # a college the roster does not have: refused before anything changes
                row['college'] = 'Nowhere State'
            elif kind == 2:    # college applied, then a later column fails: the whole row must roll back
                row['college'] = colleges[(self.doc.players[i].college_index + 2) % len(colleges)]
                row['speed'] = '999'
            elif kind == 3:    # a name change takes the full checkpoint path
                row['first'] = 'Zed' + str(i)
                row['college'] = colleges[(self.doc.players[i].college_index + 1) % len(colleges)]
            elif kind == 4:    # scalar only
                row['agility'] = str((int(row['agility']) + 3) % 100)
            # kind 5: untouched
        out = io.StringIO(newline='')
        writer = csv.DictWriter(out, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        return out.getvalue()

    def test_college_rollback_matches_the_full_checkpoint_byte_for_byte(self):
        text = self._mixed_sheet()
        old = rr.preview_csv(self.doc, text, _full_checkpoints=True)
        new = rr.preview_csv(self.doc, text)
        self.assertGreater(len(old.receipt['refused']), 0)
        self.assertGreater(old.receipt['changed'], 0)
        self.assertEqual(old.before, new.before)
        self.assertEqual(old.after, new.after)
        self.assertEqual(old.receipt, new.receipt)
        self.assertTrue(any('speed' in item['reason'] for item in new.receipt['refused']))
        self.assertTrue(any('Nowhere State' in item['reason'] for item in new.receipt['refused']))
        first, second = rr.load_body(league_body()), rr.load_body(league_body())
        rr.apply_csv_preview(first, old)
        rr.apply_csv_preview(second, new)
        self.assertEqual(first.to_body(), second.to_body())

    def test_a_refused_college_row_leaves_no_trace(self):
        text = self._mixed_sheet()
        preview = rr.preview_csv(self.doc, text)
        refused_rows = {item['index'] for item in preview.receipt['refused'] if item.get('pool') == 'primary'}
        changed = {change['index'] for change in preview.receipt['changes']}
        self.assertFalse(refused_rows & changed)

    def test_the_tool_export_with_the_box_ticked_matches_the_full_checkpoint(self):
        document = self.doc
        lines = tool_export(document).splitlines()
        colleges = document.colleges
        out, n = [], 0
        for line in lines:
            if line.startswith(('#', 'Team =')) or not line.strip():
                out.append(line)
                continue
            cells = line.split(',')
            index = TOOL_INDEX['College']
            n += 1
            if n % 4 == 0:
                cells[index] = colleges[(colleges.index(cells[index]) + 1) % len(colleges)] \
                    if cells[index] in colleges else colleges[0]
            elif n % 4 == 1:
                cells[index] = 'Nowhere State'
            elif n % 4 == 2:
                cells[TOOL_INDEX['Speed']] = str((int(cells[TOOL_INDEX['Speed']]) + 5) % 100)
            out.append(','.join(cells))
        text = '\n'.join(out) + '\n'
        old = rr.preview_csv(document, text, include_appearance=True, _full_checkpoints=True)
        new = rr.preview_csv(document, text, include_appearance=True)
        self.assertEqual((old.before, old.after), (new.before, new.after))
        self.assertEqual(old.receipt, new.receipt)
        self.assertGreater(new.receipt['changed'], 0)
        self.assertTrue(any('Nowhere State' in item['reason'] for item in new.receipt['skipped']))

    def test_the_cheap_path_makes_no_document_copy_for_college_rows(self):
        from unittest import mock
        text = self._mixed_sheet()
        reader = csv.DictReader(io.StringIO(text))
        college_only = sum(1 for _ in reader)
        calls = []
        real = rr.copy.deepcopy

        def counting(value, *args, **kwargs):
            if isinstance(value, rr.RosterDocument):
                calls.append(1)
            return real(value, *args, **kwargs)

        with mock.patch.object(rr.copy, 'deepcopy', side_effect=counting):
            rr.preview_csv(self.doc, text)
            cheap = len(calls)
            calls.clear()
            rr.preview_csv(self.doc, text, _full_checkpoints=True)
            full = len(calls)
        self.assertGreater(college_only, 20)
        # working + verified copies, plus one checkpoint per name-change row (every sixth row, offset 3)
        names = sum(1 for i in range(len(self.doc.players)) if i % 6 == 3)
        self.assertEqual(cheap, 2 + names)
        self.assertGreater(full, cheap)


class CsvSkippedAppearanceTests(unittest.TestCase):
    """b779 rv1 (R1 minor 4): one appearance or bio value the roster cannot take no longer costs the row its ratings."""

    def setUp(self):
        self.doc = rr.load_body(league_body())

    def _row(self, index, **columns):
        player = self.doc.players[index]
        speed = int(rr._csv_row(self.doc, player)['speed'])
        return player, tool_export_one(self.doc, player, Speed=str((speed + 7) % 100), **columns)

    def test_a_college_the_roster_lacks_skips_only_the_college(self):
        player, text = self._row(0, College='Nowhere State')
        before_college = player.college
        before_speed = player.record.get('speed')
        preview = rr.preview_csv(self.doc, text, include_appearance=True)
        receipt = preview.receipt
        self.assertEqual(receipt['refused'], [])
        fields = {f['field'] for change in receipt['changes'] for f in change['changes']}
        self.assertIn('speed', fields)
        self.assertNotIn('college', fields)
        self.assertEqual(len(receipt['skipped']), 1)
        skipped = receipt['skipped'][0]
        self.assertEqual((skipped['field'], skipped['pool'], skipped['index']), ('college', player.pool, player.index))
        self.assertIn('Nowhere State', skipped['reason'])
        self.assertIsInstance(skipped['row'], int)
        self.assertTrue(skipped['label'])
        self.assertTrue(any('skipped college' in line for line in receipt['log']))
        rr.apply_csv_preview(self.doc, preview)
        reread = rr.load_body(self.doc.to_body()).players[0]
        self.assertEqual(reread.college, before_college)
        self.assertNotEqual(reread.record.get('speed'), before_speed)

    def test_the_default_ratings_only_import_has_no_skip_and_still_refuses_nothing_new(self):
        player, text = self._row(0, College='Nowhere State')
        receipt = rr.preview_csv(self.doc, text).receipt
        self.assertNotIn('skipped', receipt)
        self.assertEqual(receipt['refused'], [])

    def test_a_row_whose_only_real_change_is_the_bad_value_changes_nothing_and_says_so(self):
        player = self.doc.players[0]
        text = tool_export_one(self.doc, player, College='Nowhere State')
        preview = rr.preview_csv(self.doc, text, include_appearance=True)
        receipt = preview.receipt
        self.assertEqual(receipt['changed'], 0)
        self.assertEqual(preview.before, preview.after)
        self.assertEqual(receipt['refused'], [])
        self.assertEqual([item['field'] for item in receipt['skipped']], ['college'])

    def test_a_hard_failure_in_a_ratings_column_still_refuses_the_whole_row(self):
        player = self.doc.players[0]
        text = tool_export_one(self.doc, player, College='Nowhere State', Speed='250')
        receipt = rr.preview_csv(self.doc, text, include_appearance=True).receipt
        self.assertEqual(receipt['changed'], 0)
        self.assertEqual(len(receipt['refused']), 1)
        self.assertIn('speed', receipt['refused'][0]['reason'].lower())
        self.assertNotIn('skipped', receipt)

    def test_the_skip_path_matches_the_full_checkpoint_path(self):
        lines = []
        for index in range(0, 24):
            player, text = self._row(index, College='Nowhere State' if index % 3 == 0 else tool_college(self.doc, index))
            body = text.splitlines()
            lines.append((body[1], body[2]))
        header = TOOL_HEADER
        text = header + '\n' + '\n'.join(a + '\n' + b for a, b in lines) + '\n'
        old = rr.preview_csv(self.doc, text, include_appearance=True, _full_checkpoints=True)
        new = rr.preview_csv(self.doc, text, include_appearance=True)
        self.assertEqual((old.before, old.after), (new.before, new.after))
        self.assertEqual(old.receipt, new.receipt)
        self.assertGreater(len(new.receipt.get('skipped', ())), 0)


def tool_college(document, index):
    colleges = document.colleges
    return colleges[(document.players[index].college_index + 1) % len(colleges)]


class GuiCsvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(league_body()), label='synthetic')

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def test_noop_has_no_undo_and_complete_import_undo_redo_preserves_prior_edit(self):
        player = self.panel.document.players[0]
        self.panel.set_field(player, 'speed', 77)
        before = self.panel.document.to_body()
        dirty = set(self.panel._dirty)
        text = self.panel.export_csv_text(True)
        self.panel.import_csv_text(text)
        self.assertEqual(self.panel.undo_stack.depth, (1, 0))
        edited = change_csv(text, first='Ed', speed='78', team='ATL', contract_value='500', skin='4')
        receipt = self.panel.import_csv_text(edited)
        self.assertFalse(receipt['refused'])
        after = self.panel.document.to_body()
        self.assertEqual(self.panel.undo_stack.depth, (2, 0))
        self.panel.undo()
        self.assertEqual(self.panel.document.to_body(), before)
        self.assertEqual(self.panel._dirty, dirty)
        self.panel.redo()
        self.assertEqual(self.panel.document.to_body(), after)
        self.assertEqual(player.first, 'Ed')
        self.panel.undo()
        self.panel.undo()
        self.assertFalse(self.panel._dirty)

    def test_preview_dialog_lists_every_field_and_refusal_and_cancel_keeps_document(self):
        before = self.panel.document.to_body()
        preview = self.panel.preview_csv_text('pool,index,speed\nprimary,0,77\nprimary,1,999\n')
        dialog = PlayerCsvPreviewDialog(preview, self.panel)
        self.assertEqual(dialog.table.rowCount(), 2)
        dialog.reject()
        self.assertEqual(self.panel.document.to_body(), before)
        self.assertEqual(self.panel.undo_stack.depth, (0, 0))
        noop = PlayerCsvPreviewDialog(self.panel.preview_csv_text(self.panel.export_csv_text(True)), self.panel)
        self.assertFalse(noop.buttons.button(QDialogButtonBox.Apply).isEnabled())

    def test_nfl2k5tool_import_previews_and_undoes_as_one_action(self):
        before = self.panel.document.to_body()
        text = ("#Position,fname,lname,JerseyNumber,Speed,\n"
                "Team = IND    Players:1\n"
                "QB,F00,Last00,1,77,\n")
        preview = self.panel.preview_csv_text(text)
        self.assertEqual(preview.receipt['format'], rr.NFL2K5TOOL_CSV)
        self.assertEqual((preview.receipt['changed'], preview.receipt['fields']), (1, 1))
        dialog = PlayerCsvPreviewDialog(preview, self.panel)
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertIn('F00 Last00', dialog.table.item(0, 1).text())
        dialog.reject()
        self.assertEqual(self.panel.document.to_body(), before)
        receipt = self.panel.import_csv_text(text)
        self.assertEqual(receipt['changed'], 1)
        self.assertEqual(self.panel.undo_stack.depth, (1, 0))
        after = self.panel.document.to_body()
        self.assertNotEqual(after, before)
        self.panel.undo()
        self.assertEqual(self.panel.document.to_body(), before)
        self.panel.redo()
        self.assertEqual(self.panel.document.to_body(), after)

    def test_nfl2k5tool_preview_checkbox_opt_in_repreviews_appearance(self):
        document = self.panel.document
        player = document.players[0]
        row = rr._csv_row(document, player)
        text = tool_export_one(document, player,
                               Speed=str(int(row['speed']) + 1),
                               Photo=str(int(row['photo_id']) + 1),
                               PBP=str(int(row['pbp_id']) + 1))
        preview = self.panel.preview_csv_text(text)
        self.assertTrue(preview.receipt['rating_only'])
        self.assertTrue(preview.receipt['ignored_columns'])
        calls = []

        def repreview(include):
            calls.append(include)
            return self.panel.preview_csv_text(text, include_appearance=include)

        dialog = PlayerCsvPreviewDialog(preview, self.panel, repreview=repreview)
        try:
            self.assertIsNotNone(dialog.appearance_checkbox)
            self.assertFalse(dialog.appearance_checkbox.isChecked())
            self.assertIn(f'{len(preview.receipt["ignored_columns"])} non-rating columns were ignored',
                          dialog.summary.text())
            dialog.appearance_checkbox.setChecked(True)
            self.assertEqual(calls, [True])
            self.assertFalse(dialog.preview.receipt['rating_only'])
            self.assertEqual(dialog.preview.receipt['ignored_columns'], [])
            fields = {field['field'] for change in dialog.preview.receipt['changes']
                      for field in change['changes']}
            self.assertTrue({'speed', 'photo_id', 'pbp_id'} <= fields)
            dialog.appearance_checkbox.setChecked(False)
            self.assertEqual(calls, [True, False])
            self.assertTrue(dialog.preview.receipt['rating_only'])
            self.assertTrue(dialog.preview.receipt['ignored_columns'])
        finally:
            dialog.reject()

    def test_a_failed_repreview_puts_the_box_back_and_keeps_the_shown_preview(self):
        # b779 rv1 (R1 minor 3): box and preview must agree because Apply uses the preview.
        document = self.panel.document
        player = document.players[0]
        text = tool_export_one(document, player, Speed=str(int(rr._csv_row(document, player)['speed']) + 1))
        preview = self.panel.preview_csv_text(text)

        def repreview(include):
            raise rr.RosterRecordError('Pretend the second pass failed.')

        dialog = PlayerCsvPreviewDialog(preview, self.panel, repreview=repreview)
        try:
            with patch('mod_editor.gui.roster_editor_panel_qt.QMessageBox.warning') as warning:
                dialog.appearance_checkbox.setChecked(True)
            self.assertFalse(dialog.appearance_checkbox.isChecked())
            self.assertIs(dialog.preview, preview)
            self.assertTrue(dialog.preview.receipt['rating_only'])
            warning.assert_called_once()
            self.assertIn('Pretend the second pass failed.', warning.call_args[0][2])
        finally:
            dialog.reject()

    def test_the_repreview_runs_off_the_gui_thread_and_the_event_loop_keeps_turning(self):
        import threading
        import time
        from PyQt5.QtCore import QTimer
        from mod_editor.gui.roster_editor_panel_qt import run_in_background
        ticks, threads = [], []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)

        def slow():
            threads.append(threading.current_thread())
            time.sleep(0.4)
            return 'done'

        try:
            self.assertEqual(run_in_background(self.panel, 'Test', 'Working', slow), 'done')
        finally:
            timer.stop()
        self.assertIsNot(threads[0], threading.main_thread())
        self.assertGreater(len(ticks), 5)
        with self.assertRaisesRegex(ValueError, 'boom'):
            run_in_background(self.panel, 'Test', 'Working', lambda: (_ for _ in ()).throw(ValueError('boom')))

    def test_the_preview_lists_a_skipped_value_with_a_clear_note(self):
        document = self.panel.document
        player = document.players[0]
        speed = int(rr._csv_row(document, player)['speed'])
        text = tool_export_one(document, player, Speed=str((speed + 7) % 100), College='Nowhere State')
        preview = self.panel.preview_csv_text(text, include_appearance=True)
        dialog = PlayerCsvPreviewDialog(preview, self.panel, repreview=lambda include: preview)
        try:
            notes = [dialog.table.item(row, 5).text() for row in range(dialog.table.rowCount())]
            note = next(n for n in notes if n.startswith('Skipped'))
            self.assertIn('rest of the row imported', note)
            self.assertIn('Nowhere State', note)
            self.assertIn('1 appearance or bio values', dialog.summary.text())
            self.assertIn('speed', {dialog.table.item(row, 2).text() for row in range(dialog.table.rowCount())})
            self.assertTrue(dialog.apply_button.isEnabled())
        finally:
            dialog.reject()

    def test_nfl2k5tool_file_action_previews_and_applies(self):
        before = self.panel.document.to_body()
        text = ("#Position,fname,lname,JerseyNumber,Speed,\n"
                "Team = IND    Players:1\n"
                "QB,F00,Last00,1,78,\n")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'the1wam-ratings.csv'
            path.write_text(text, encoding='utf-8', newline='')
            with patch('mod_editor.gui.roster_editor_panel_qt.QFileDialog.getOpenFileName',
                       return_value=(str(path), '')), \
                 patch('mod_editor.gui.roster_editor_panel_qt.PlayerCsvPreviewDialog.exec_',
                       return_value=QDialog.Accepted):
                self.panel._import_csv()
        self.assertEqual(self.panel.undo_stack.depth, (1, 0))
        self.assertNotEqual(self.panel.document.to_body(), before)
        self.panel.undo()
        self.assertEqual(self.panel.document.to_body(), before)

    def test_real_save_layout_and_franchise_round_trip_never_write_source(self):
        for label, payload in [('roster', synthetic_save_v0(synthetic_body())),
                               ('franchise', synthetic_franchise(year_field=7, user_team=0))]:
            with self.subTest(kind=label), tempfile.TemporaryDirectory() as folder:
                source = write_container(Path(folder) / label, payload)
                self.assertTrue(self.panel.load_save(source))
                members = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
                before = self.panel.document.to_body()
                text = self.panel.export_csv_text(True)
                self.assertEqual(self.panel.import_csv_text(text)['fields'], 0)
                self.assertEqual(self.panel.undo_stack.depth, (0, 0))
                receipt = self.panel.import_csv_text(change_csv(text, contract_value='777'))
                self.assertEqual((receipt['changed'], receipt['fields']), (1, 1))
                after = self.panel.document.to_body()
                self.panel.undo()
                self.assertEqual(self.panel.document.to_body(), before)
                self.panel.redo()
                self.assertEqual(self.panel.document.to_body(), after)
                self.assertEqual({p: p.read_bytes() for p in members}, members)
                # The file export action refuses a path inside the loaded save.
                with patch('mod_editor.gui.roster_editor_panel_qt.QFileDialog.getSaveFileName',
                           return_value=(str(next(iter(members))), '')), \
                     patch('mod_editor.gui.roster_editor_panel_qt.QMessageBox.warning') as warn:
                    self.panel._export_csv(True)
                    warn.assert_called_once()
                self.assertEqual({p: p.read_bytes() for p in members}, members)


if __name__ == '__main__':
    unittest.main()
