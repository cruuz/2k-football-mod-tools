"""Counter semantics, hostile inputs, pool transactions and retail round-trips."""
from dataclasses import replace
import datetime as dt
from decimal import Decimal
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from mod_editor.core import nfl2k5_career_stats as cs
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_team_history as th
from tests.mod_editor.test_nfl2k5_team_history import synthetic_body, entry, games
from tools import nfl2k5_career_stats as cli


SOURCE_HASH = hashlib.sha256(b'explicit synthetic test source').hexdigest()


def make_body(*, stream=None, no_history=False, duplicate_player=False, birth=True, pad=0):
    words = games([1, 2, 3], extra=(entry(3, 8, 3000), entry(2, 117, 54321, deleted=True, folded=True)))
    if stream is not None:
        words = stream
    players = [{'first': 'Test', 'last': 'Player', 'birth': dt.date(1976, 3, 24) if birth else None,
                'position': 0, 'count': 4, 'stream': None if no_history else words}]
    if duplicate_player:
        players.append(dict(players[0]))
    body = bytearray(synthetic_body(players, pool_used_pad=pad))
    # The older history-only fixture does not need this pointer; our general
    # framing decoder does. This is the actual v17 field-local root pointer.
    struct.pack_into('<i', body, 0x14, 0x2D)
    return bytes(body)


def row(stat='passing_yards', value='3500', **kwargs):
    result = cs.Row('Test', 'Player', dt.date(1976, 3, 24), 2003, stat, None if value is None else Decimal(value),
                    'synthetic:test', SOURCE_HASH, player_index=0)
    return replace(result, **kwargs)


def values(body, field, *, phase='regular', index=0):
    doc = cs.decode_body(body)
    return [raw & 65535 for raw in doc.history_words['primary', index]
            if cs.Word(raw).field == field and cs.Word(raw).slot == 3
            and cs.Word(raw).phase == phase and not raw & 0x50000000]


class CareerStatsTests(unittest.TestCase):
    def test_lossless_word_flags_and_body_roundtrip(self):
        for raw in (0, 0xFFFFFFFF, 0xFEDCBA98, entry(31, 117, 0xFEDC, end=True, folded=True, deleted=True, post=True)):
            self.assertEqual(cs.encode_word(cs.decode_word(raw)), raw)
        body = make_body()
        self.assertEqual(cs.encode_body(cs.decode_body(body)), body)
        out, receipt = cs.apply_body(body, [])
        self.assertEqual(out, body)
        self.assertEqual(receipt['used_after'], receipt['used_before'])

    def test_replace_preserves_opaque_words_and_is_idempotent(self):
        body = make_body()
        out, receipt = cs.apply_body(body, [row()])
        self.assertEqual(values(out, 8), [3500])
        self.assertEqual(receipt['replaced'], 1)
        self.assertEqual(receipt['added'], 0)
        before = cs.decode_body(body).history_words['primary', 0]
        after = cs.decode_body(out).history_words['primary', 0]
        self.assertEqual(before[-1], after[-1])
        self.assertEqual([w & 0xFFFF0000 for w in before], [w & 0xFFFF0000 for w in after])
        again, receipt = cs.apply_body(out, [row()])
        self.assertEqual(again, out)
        self.assertEqual(receipt['unchanged'], 1)

    def test_half_sacks_and_signed_yards(self):
        out, receipt = cs.apply_body(make_body(), [row('defensive_sacks', '7.5'), row('rushing_yards', '-3')])
        self.assertEqual(values(out, 19), [15])
        self.assertEqual(values(out, 2), [65533])
        exported = cs.read_csv(cs.export_csv(out))
        self.assertIn(Decimal('7.5'), [r.value for r in exported if r.stat == 'defensive_sacks'])
        self.assertIn(Decimal('-3'), [r.value for r in exported if r.stat == 'rushing_yards'])
        self.assertEqual(receipt['added'], 2)

    def test_every_supported_field_decodes_to_its_source_number(self):
        rows = [row(field.name, '-3' if field.signed else '3.5' if field.units == 2 else '14')
                for field in cs.FIELDS]
        output, receipt = cs.apply_body(make_body(), rows)
        exported = {r.stat: r.value for r in cs.read_csv(cs.export_csv(output)) if r.season == 2003}
        self.assertEqual(len(receipt['rows']), len(cs.FIELDS))
        for source in rows:
            with self.subTest(stat=source.stat):
                self.assertEqual(exported[source.stat], source.value)
        self.assertEqual(cs.apply_body(output, rows)[0], output)

    def test_fractional_nonfinite_and_overflow_values_refused(self):
        for stat, value in (('defensive_sacks', '7.25'), ('passing_attempts', '3.5'),
                            ('passing_yards', 'NaN'), ('passing_yards', 'Infinity'),
                            ('passing_yards', '1e999999999'), ('passing_yards', '-32769'),
                            ('passing_attempts', '1e-999999999'),
                            ('passing_attempts', '3.00000000000000000000000000001'),
                            ('defensive_sacks', '3.50000000000000000000000000001'),
                            ('passing_touchdowns', '-1'), ('passing_yards', '32768')):
            with self.subTest(stat=stat, value=value), self.assertRaises(cs.CareerStatsError):
                cs.apply_body(make_body(), [row(stat, value)])

    def test_missing_is_not_zero(self):
        body = make_body()
        missing, receipt = cs.apply_body(body, [row(value=None)])
        self.assertEqual(missing, body)
        self.assertEqual(receipt['source_missing'], 1)
        zero, _ = cs.apply_body(body, [row(value=Decimal(0))])
        self.assertEqual(values(zero, 8), [0])

    def test_phase_separation_and_missing_games(self):
        body = make_body()
        with self.assertRaisesRegex(cs.CareerStatsError, 'games entry'):
            cs.apply_body(body, [row('defensive_sacks', '1.5', phase='postseason')])
        out, _ = cs.apply_body(body, [row('defensive_sacks', '1.5', phase='postseason'),
                                     row('games', '2', phase='postseason')])
        self.assertEqual(values(out, 19, phase='postseason'), [3])
        self.assertEqual(values(out, 0, phase='regular'), [16])

    def test_no_history_can_gain_a_proved_season(self):
        body = make_body(no_history=True)
        with self.assertRaises(cs.CareerStatsError):
            cs.apply_body(body, [row()])
        out, receipt = cs.apply_body(body, [row(), row('games', '16')])
        self.assertEqual(values(out, 8), [3500])
        self.assertEqual(receipt['added'], 2)
        self.assertEqual(cs.apply_body(out, [row(), row('games', '16')])[0], out)

    def test_reserved_and_full_pool_refusal(self):
        body = make_body()
        doc = cs.decode_body(body)
        reserve = doc.pool_capacity - doc.pool_used
        self.assertEqual(cs.apply_body(body, [row()], reserved_tail_words=reserve)[1]['free_after'], 0)
        with self.assertRaisesRegex(cs.CareerStatsError, 'usable capacity'):
            cs.apply_body(body, [row('defensive_sacks', '1')], reserved_tail_words=reserve)
        full = make_body(pad=50000 - doc.pool_used)
        with self.assertRaisesRegex(cs.CareerStatsError, 'usable capacity'):
            cs.apply_body(full, [row('defensive_sacks', '1')])

    def test_nonzero_slack_refused_and_input_immutable(self):
        body = bytearray(make_body())
        doc = cs.decode_body(body)
        body[doc.pool + doc.pool_used * 4] = 0x7F
        original = bytes(body)
        with self.assertRaisesRegex(cs.CareerStatsError, 'nonzero'):
            cs.apply_body(body, [row('defensive_sacks', '1')])
        self.assertEqual(bytes(body), original)

    def test_identities_are_not_name_only(self):
        body = make_body()
        for bad in (row(player_index=9), row(first_name='Someone'), row(birth_date=dt.date(1975, 3, 24)),
                    row(player_index=None, birth_date=None), row(record_sha256='0' * 64)):
            with self.subTest(bad=bad), self.assertRaises(cs.CareerStatsError):
                cs.apply_body(body, [bad])
        with self.assertRaisesRegex(cs.CareerStatsError, 'ambiguous'):
            cs.apply_body(make_body(duplicate_player=True), [row(player_index=None)])
        no_birth = make_body(birth=False)
        player = cs.decode_body(no_birth).players[0]
        out, _ = cs.apply_body(no_birth, [row(birth_date=None, record_sha256=cs.record_digest(player))])
        self.assertEqual(values(out, 8), [3500])

    def test_duplicates_need_occurrence_and_pin(self):
        body = make_body(stream=games([1, 2, 3], extra=(entry(3, 8, 100), entry(3, 8, 200))))
        with self.assertRaisesRegex(cs.CareerStatsError, 'duplicate live'):
            cs.apply_body(body, [row()])
        exported = cs.read_csv(cs.export_csv(body))
        self.assertEqual(cs.apply_body(body, exported)[0], body)
        changed = [replace(r, value=Decimal('999')) if r.stat == 'passing_yards' and r.occurrence == 1 else r
                   for r in exported]
        out, _ = cs.apply_body(body, changed)
        self.assertEqual(values(out, 8), [100, 999])
        self.assertEqual(cs.apply_body(out, changed)[0], out)
        with self.assertRaisesRegex(cs.CareerStatsError, 'pin changed'):
            cs.apply_body(out, exported)
        with self.assertRaisesRegex(cs.CareerStatsError, 'duplicate source'):
            cs.apply_body(make_body(), [row(), row()])

    def test_derived_totals_and_unproved_fields_refused(self):
        for stat in ('field_goals_made', 'field_goal_percentage', 'invented_counter'):
            with self.assertRaises(cs.CareerStatsError):
                cs.apply_body(make_body(), [row(stat)])
        out, _ = cs.apply_body(make_body(), [row('field_goals_made_1_29', '3'),
                                            row('field_goals_made_30_39', '4'),
                                            row('field_goals_made_40_49', '5'),
                                            row('field_goals_made_50_plus', '2')])
        self.assertEqual(sum(values(out, field)[0] for field in (61, 63, 65, 67)), 14)

    def test_epoch_and_unrepresentable_seasons(self):
        for year in (1899, 1980, 2004, 2005):
            with self.subTest(year=year), self.assertRaises(cs.CareerStatsError):
                cs.apply_body(make_body(), [row(season=year)])
        out, _ = cs.apply_body(make_body(), [row(season=2004)], base_year=2005)
        self.assertEqual(values(out, 8), [3500])

    def test_csv_validation(self):
        text = cs.export_csv(make_body())
        rows = cs.read_csv(text)
        self.assertEqual(cs.apply_body(make_body(), rows)[0], make_body())
        for corrupt in (text.replace('first_name', 'typo', 1), text.replace('season', 'stat', 1),
                        text + 'too,few,cells\n', text.replace('1976-03-24', 'not-a-date')):
            with self.assertRaises(cs.CareerStatsError):
                cs.read_csv(corrupt)

    def test_cli_export_import_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='career-cli-') as directory:
            # The CLI refuses a symlinked output parent; macOS temp dirs sit under
            # /var -> /private/var, so hand it the real path.
            root = Path(directory).resolve()
            source, csv_path, output, receipt = (root / n for n in ('body.bin', 'stats.csv', 'result.bin', 'receipt.json'))
            body = make_body()
            source.write_bytes(body)
            self.assertEqual(cli.main(['export', str(source), '--output', str(csv_path)]), 0)
            self.assertEqual(cli.main(['import', str(source), str(csv_path), '--output', str(output), '--receipt', str(receipt)]), 0)
            self.assertEqual(output.read_bytes(), body)
            self.assertEqual(source.read_bytes(), body)
            self.assertEqual(cli.main(['import', str(source), str(csv_path), '--output', str(source)]), 1)
            absent = root / 'not-created.bin'
            self.assertEqual(cli.main(['import', str(source), str(csv_path), '--output', str(absent), '--receipt', str(receipt)]), 1)
            self.assertFalse(absent.exists())


RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')


@unittest.skipUnless((RETAIL / 'vc_53450030/0').is_file(), 'private retail NFL 2K5 extraction is absent')
class RetailCareerTests(unittest.TestCase):
    def test_full_retail_codec_csv_and_history_pass(self):
        with rr._outer_image()(RETAIL) as archive:
            item = rr._entry(archive)
            body = archive.read(item.virtual_offset, item.size)[32:]
        self.assertEqual(hashlib.sha256(body).hexdigest(), rr.RETAIL_BODY_SHA256)
        self.assertEqual(cs.encode_body(cs.decode_body(body)), body)
        csv_rows = cs.read_csv(cs.export_csv(body))
        self.assertEqual(cs.apply_body(body, csv_rows)[0], body)
        rows, _ = th.load_rows('retail')
        after_history, _ = th.apply_body(body, rows)
        self.assertEqual(cs.apply_body(after_history, [])[0], after_history)
        before = cs.decode_body(after_history)
        # One explicit test correction on an existing named counter; never a
        # claim that the synthetic number is the player's historical statistic.
        candidate = next(r for r in cs.read_csv(cs.export_csv(after_history))
                         if r.stat == 'passing_yards' and r.value < 32000)
        modified = replace(candidate, value=candidate.value + 1, source='synthetic:regression')
        output, receipt = cs.apply_body(after_history, [modified])
        after = cs.decode_body(output)
        self.assertEqual(receipt['replaced'], 1)
        self.assertEqual(receipt['used_after'], 42612)
        for player in before.players:
            self.assertEqual([w for w in before.history_words[player.key] if cs.Word(w).field == 87],
                             [w for w in after.history_words[player.key] if cs.Word(w).field == 87])

    def test_field_map_against_pinned_xbe(self):
        from tools.xbe_info import Xbe
        image = Xbe(RETAIL / 'default.xbe')
        self.assertEqual(hashlib.sha256(image.data).hexdigest(),
                         '73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9')
        for field in cs.FIELDS:
            address = 0xA8A51C + 28 * field.selector
            actual = struct.unpack_from('<i', image.data, image.va_to_offset(address, 4))[0]
            self.assertEqual(actual, field.id, field.name)
        self.assertEqual(struct.unpack_from('<II', image.data, image.va_to_offset(0xA8B918, 8)), (6, 47))
        self.assertEqual(struct.unpack_from('<f', image.data, image.va_to_offset(0x4E4184, 4))[0], 0.5)


if __name__ == '__main__':
    unittest.main()
