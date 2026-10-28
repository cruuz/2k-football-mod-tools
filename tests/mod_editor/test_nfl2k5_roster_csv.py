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
        before = self.doc.to_body()
        text = tool_export(self.doc)
        self.assertNotIn('Team = DraftClass', text)
        receipt = rr.import_csv(self.doc, text)
        self.assertEqual(receipt['format'], rr.NFL2K5TOOL_CSV)
        self.assertFalse(receipt['refused'])
        self.assertEqual((receipt['rows'], receipt['changed'], receipt['fields']), (7, 0, 0))
        self.assertEqual(self.doc.to_body(), before)

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
        receipt = rr.import_csv(self.doc, text)
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
                receipt = rr.import_csv(self.doc, text)
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
