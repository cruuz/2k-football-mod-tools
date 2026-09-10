"""College repair owns only player +0x00; all fixtures are generated, retail is read-only."""
from pathlib import Path
import hashlib
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_practice_squad as ps
from tests.mod_editor.test_nfl2k5_roster_records import (
    synthetic_body, synthetic_resource, synthetic_save_v0, RETAIL_EXTRACTION,
)
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise


def rel(data, field, target):
    struct.pack_into('<i', data, field, 0 if target is None else target - field + 1)


def corrupt(payload, kind, player=0):
    data = bytearray(payload)
    doc = codec.decode(data)
    field = doc.players[player].offset
    table = doc.tables['colleges']
    targets = {'null': None, 'outside': doc.layout.end + 16,
               'before': -4, 'misaligned': table.offset + 1,
               'past_table': table.offset + table.count * 8,
               'string': doc.rel(table.offset), 'interior_string': doc.rel(table.offset) + 2}
    rel(data, field, targets[kind])
    return bytes(data), field


class ExistingBoundaryTests(unittest.TestCase):
    def test_631_accepts_null_and_off_table_but_refuses_outside_arena(self):
        for payload in (synthetic_body(), synthetic_save_v0(synthetic_body()), synthetic_franchise()):
            for kind in ('null', 'outside', 'before', 'misaligned', 'past_table', 'string', 'interior_string'):
                bad, field = corrupt(payload, kind)
                with self.subTest(version=codec.decode(payload).layout.version, kind=kind):
                    # Legacy document loads and displays all these as blank, preserving the word.
                    doc = rr.RosterDocument(bad, base=rr.find_block_base(bad))
                    self.assertEqual(doc.players[0].college, '')
                    self.assertEqual(doc.to_body(), bad)
                    if kind in ('outside', 'before'):
                        with self.assertRaisesRegex(codec.SaveRostError,
                                'primary player 0.*college pointer: range outside ROST arena data'):
                            codec.decode(bad)
                        with self.assertRaises(codec.SaveRostError):
                            ps.validate_save(bad)
                    else:
                        self.assertEqual(codec.decode(bad).to_bytes(), bad)
                        ps.validate_save(bad)

    def test_table_corruption_refusals_are_distinct_from_missing_player_colleges(self):
        for kind, message in (('suffix', 'UTF-16 pointer: range outside ROST arena data'),
                              ('unaligned', 'unaligned UTF-16 string'),
                              ('unterminated', 'unterminated UTF-16 string'),
                              ('invalid_utf16', 'invalid UTF-16 string'),
                              ('count_high', 'colleges: implausible count 4001'),
                              ('null_table', 'colleges: null table with nonzero count'),
                              ('table_outside', 'colleges: range outside ROST arena data')):
            data = bytearray(synthetic_franchise())
            doc = codec.decode(data)
            table = doc.tables['colleges'].offset
            if kind == 'suffix':
                rel(data, table, doc.layout.end + 16)
            elif kind == 'unaligned':
                rel(data, table, doc.rel(table) + 1)
            elif kind == 'unterminated':
                rel(data, table, doc.layout.end - 2)
                data[doc.layout.end - 2:doc.layout.end] = b'AA'
            elif kind == 'invalid_utf16':
                rel(data, table, doc.layout.end - 4)
                data[doc.layout.end - 4:doc.layout.end] = b'\0\xd8\0\0'
            elif kind == 'count_high':
                struct.pack_into('<I', data, doc.layout.root + 0x20, 4001)
            else:
                rel(data, doc.layout.root + 0x24, None if kind == 'null_table' else len(data) + 100)
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(codec.SaveRostError, message):
                    codec.decode(data)
                if kind == 'table_outside':
                    with self.assertRaises(struct.error):
                        rr.RosterDocument(data, base=doc.layout.preamble)
                else:
                    rr.RosterDocument(data, base=doc.layout.preamble)  # legacy document is more permissive

    def test_disc_edits_replay_preserves_existing_bad_pointer_and_refuses_raw_pointer_import(self):
        bad, field = corrupt(synthetic_body(), 'outside')
        doc = rr.RosterDocument(bad)
        doc.players[0].record.set('speed', 77)
        edits = rr.edits_document(doc)
        edits['edits'][0]['fields']['college_pointer'] = 1
        after, receipt = rr.apply_body(bad, edits)
        self.assertEqual(after[field:field + 4], bad[field:field + 4])
        self.assertTrue(any('pointer and cannot travel' in line for line in receipt['log']))
        self.assertEqual(rr.RosterDocument(after).players[0].record.values['speed'], 77)

    def test_low_level_record_mutation_can_create_a_bad_pointer_but_typed_codec_refuses(self):
        doc = rr.RosterDocument(synthetic_body())
        doc.players[0].record.set('college_pointer', 0x7FFFFFFF)
        with self.assertRaisesRegex(codec.SaveRostError, 'college pointer'):
            codec.decode(doc.to_body())
        typed = codec.decode(synthetic_body())
        with self.assertRaisesRegex(codec.SaveRostError, 'pointer edits require a typed relocation writer'):
            typed.edit_player('primary', 0, {'college_pointer': 0x7FFFFFFF})


class RepairTests(unittest.TestCase):
    def setUp(self):
        from mod_editor.core import nfl2k5_college_check
        self.check = nfl2k5_college_check

    def test_repairs_every_shape_without_other_writes_and_is_idempotent(self):
        payloads = (synthetic_body(), synthetic_resource(), synthetic_save_v0(synthetic_body()),
                    synthetic_franchise())
        for payload in payloads:
            for kind in ('null', 'outside', 'before', 'misaligned', 'past_table', 'string', 'interior_string'):
                with self.subTest(size=len(payload), kind=kind):
                    bad, field = corrupt(payload, kind)
                    original = bytearray(bad)
                    scan = self.check.scan(original, source='fixture')
                    self.assertEqual(len(scan.findings), 1)
                    row = scan.findings[0]
                    self.assertEqual((row.source, row.pool, row.index, row.offset, row.player),
                                     ('fixture', 'primary', 0, field, 'Peyton Manning'))
                    self.assertEqual(row.raw, struct.unpack_from('<I', bad, field)[0])
                    self.assertTrue(row.game_display)
                    fixed, receipt = self.check.repair(original, source='fixture',
                                                      expected_sha256=scan.sha256)
                    self.assertEqual(original, bad)
                    self.assertEqual(len(fixed), len(bad))
                    self.assertEqual(fixed[:field] + fixed[field + 4:], bad[:field] + bad[field + 4:])
                    self.assertEqual(fixed, payload)
                    self.assertEqual(receipt['changed'], 1)
                    self.assertEqual(receipt['repairs'][0]['player'], 'Peyton Manning')
                    self.assertFalse(receipt['saved'])
                    self.assertEqual(self.check.scan(fixed).findings, ())
                    again, second = self.check.repair(fixed)
                    self.assertEqual(again, fixed)
                    self.assertEqual(second['changed'], 0)
                    ps.validate_save(fixed)

    def test_none_then_blank_then_first_and_explicit_choice(self):
        for name in ('None', '', 'Custom'):
            data = bytearray(synthetic_body())
            doc = codec.decode(data)
            table = doc.tables['colleges'].offset
            target = doc.rel(table + 8)
            encoded = name.encode('utf-16-le') + b'\0\0'
            data[target:target + len(encoded)] = encoded
            bad, field = corrupt(bytes(data), 'outside')
            fixed, receipt = self.check.repair(bad)
            self.assertEqual(receipt['college_index'], 1 if name != 'Custom' else 0)
            fixed, receipt = self.check.repair(bad, college_index=3)
            self.assertEqual(codec.decode(fixed).rel(field), table + 24)
            for index in (-1, 5, True, 1.0):
                with self.assertRaises(self.check.CollegeCheckError):
                    self.check.repair(bad, college_index=index)

    def test_multiple_pools_and_shared_bad_reference(self):
        data = bytearray(synthetic_body())
        doc = codec.decode(data)
        secondary = doc.tables['primary'].offset + 8 * rr.PLAYER_SIZE
        struct.pack_into('<I', data, doc.layout.root + 8, 1)
        # Zero-initialized secondary record: a null college and null names are permitted.
        for player in doc.players[:2]:
            rel(data, player.offset, doc.layout.end + 16)
        scan = self.check.scan(data)
        self.assertEqual([(r.pool, r.index) for r in scan.findings],
                         [('primary', 0), ('primary', 1), ('secondary', 0)])
        fixed, receipt = self.check.repair(data)
        allowed = {r.offset + i for r in scan.findings for i in range(4)}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(data, fixed)) if a != b))
        self.assertEqual(receipt['changed'], 3)
        self.assertIsNotNone(codec.decode(fixed).rel(secondary))

    def test_bad_table_strings_reported_and_never_guessed(self):
        for kind in ('outside', 'unaligned', 'unterminated', 'invalid_utf16'):
            data = bytearray(synthetic_body())
            doc = codec.decode(data)
            table = doc.tables['colleges'].offset
            if kind == 'outside':
                rel(data, table, doc.layout.end + 2)
            elif kind == 'unaligned':
                rel(data, table, doc.rel(table) + 1)
            else:
                rel(data, table, doc.layout.end - 2 if kind == 'unterminated' else doc.layout.end - 4)
                data[doc.layout.end - 2:doc.layout.end] = b'AA' if kind == 'unterminated' else b'\0\0'
                if kind == 'invalid_utf16':
                    data[doc.layout.end - 4:doc.layout.end - 2] = b'\0\xd8'
            with self.subTest(kind=kind):
                scan = self.check.scan(data)
                self.assertEqual(len(scan.table_issues), 1)
                self.assertEqual(len(scan.findings), 3)  # three players use college zero
                with self.assertRaisesRegex(self.check.CollegeCheckError, 'college table'):
                    self.check.repair(data)
                with self.assertRaises(codec.SaveRostError):
                    codec.decode(data)

    def test_structural_boundaries_ambiguity_and_index_abi_refused(self):
        original = synthetic_body()
        doc = codec.decode(original)
        for field, value in ((doc.layout.root, 8001), (doc.layout.root + 0x20, 4001),
                             (doc.layout.root + 0x20, 0), (0x14, 1)):
            data = bytearray(original)
            struct.pack_into('<I', data, field, value)
            with self.subTest(field=field), self.assertRaises(self.check.CollegeCheckError):
                self.check.scan(data)
        data = bytearray(original)
        rel(data, doc.layout.root + 0x24, doc.players[0].offset)
        with self.assertRaisesRegex(self.check.CollegeCheckError, 'overlapping'):
            self.check.scan(data)
        # Both frames are within the first 64 KiB (small codec fixture).
        from tests.mod_editor.test_nfl2k5_save_rost import fixture
        framed = fixture(prefix=b'', suffix=b'')
        for bad in (b'', original[:-1], framed + framed, bytes(33 * 1024 * 1024)):
            with self.assertRaises(self.check.CollegeCheckError):
                self.check.scan(bad)

    def test_stale_scan_and_unrelated_corruption_refuse_atomically(self):
        bad, field = corrupt(synthetic_body(), 'outside')
        with self.assertRaisesRegex(self.check.CollegeCheckError, 'stale'):
            self.check.repair(bad, expected_sha256=hashlib.sha256(synthetic_body()).hexdigest())
        data = bytearray(bad)
        struct.pack_into('<I', data, field + 0x2C, 1)  # unrelated history corruption
        before = bytes(data)
        self.assertEqual(len(self.check.scan(data).findings), 1)
        with self.assertRaisesRegex(self.check.CollegeCheckError, 'history stream'):
            self.check.repair(data)
        self.assertEqual(data, before)

    def test_grown_schema_reserves_and_suffix_are_preserved(self):
        from mod_editor.core import nfl2k5_roster_arena as arena
        for payload in (synthetic_body(), synthetic_franchise()):
            old = codec.decode(payload).layout
            new_end = old.root + arena.ARENA_SIZE
            data = bytearray(payload[:old.end] + bytes(new_end - old.end) + payload[old.end:])
            struct.pack_into('<I', data, old.preamble + 16, 18 if old.version == 17 else 1)
            if old.wrapper is not None:
                struct.pack_into('<I', data, old.wrapper + 4, new_end - old.preamble)
            arena.write_block(data, old.root, arena.Overflow())
            original = bytes(data)
            codec.decode(original)
            field = codec.decode(original).players[0].offset
            # The reserved tail is in the file, but must never be a college target.
            rel(data, field, old.root + arena.BLOCK_OFFSET)
            self.assertEqual(self.check.scan(data).findings[0].reason, 'outside_arena')
            with self.assertRaises(codec.SaveRostError):
                rr.RosterDocument(data, base=old.preamble)
            fixed, receipt = self.check.repair(data)
            self.assertEqual(fixed, original)
            self.assertEqual(fixed[new_end:], payload[old.end:])

    def test_null_name_blank_and_nonordinal_metadata_are_preserved(self):
        data = bytearray(synthetic_body())
        doc = codec.decode(data)
        field = doc.tables['colleges'].offset + 8
        rel(data, field, None)
        struct.pack_into('<I', data, field + 4, 0xFFFFFFFF)
        self.assertEqual(self.check.scan(data).findings, ())
        self.assertEqual(self.check.scan(data).colleges[1].stored_id, 0xFFFFFFFF)
        bad, player = corrupt(bytes(data), 'outside')
        fixed, receipt = self.check.repair(bad)
        self.assertEqual(receipt['college_index'], 1)
        self.assertEqual(codec.decode(fixed).rel(player), field)
        self.assertEqual(rr.RosterDocument(fixed).players[0].college, '')

    def test_integer_written_in_pointer_abi_is_not_guessed_as_a_college_index(self):
        for raw in (1, 6, 4001, 0xFFFFFFFF):
            data = bytearray(synthetic_body())
            field = codec.decode(data).players[0].offset
            struct.pack_into('<I', data, field, raw)
            scan = self.check.scan(data)
            self.assertEqual(scan.findings[0].raw, raw)
            self.assertIsNone(scan.findings[0].college_index)
            fixed, receipt = self.check.repair(data)
            self.assertEqual(fixed, synthetic_body())

    def test_inline_mycareer_college_identity_cannot_be_invalidated(self):
        from mod_editor.core import nfl2k5_my_career_save as career
        payload = synthetic_franchise()
        doc = codec.decode(payload)
        player = doc.players[0].offset
        block = bytearray(career.SIZE)
        block[:8] = career.MAGIC
        struct.pack_into('<HH', block, 8, 1, career.SIZE)
        block[16] = 1
        block[36:40] = bytes((3, 0, 0, payload[player + 0x35]))
        for field, stored in ((0, 44), (16, 48), (20, 52)):
            struct.pack_into('<I', block, stored, doc.rel(player + field) - doc.layout.root)
        block[56:60] = payload[player + 4:player + 8]
        struct.pack_into('<I', block, 60, career.word(payload, player + 0x18) & career.BIRTH_MASK)
        block[74] = 255
        original, _ = career.append(payload, career.seal(block))
        bad, _ = corrupt(original, 'outside')
        with self.assertRaisesRegex(self.check.CollegeCheckError, 'MyPlayer name or college reference changed'):
            self.check.repair(bad, college_index=1)
        fixed, _ = self.check.repair(bad, college_index=0)
        self.assertEqual(fixed, original)
        career.read(fixed)

    def test_signed_copy_keeps_metadata_and_source(self):
        bad, field = corrupt(synthetic_franchise(), 'outside')
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'source'
            source.mkdir()
            for name, payload in {'SAVEGAME.DAT': bad, 'EXTRA': rr.sign_save(bad),
                                  'SaveMeta.xbx': b'metadata', 'TYPE': b'FXG'}.items():
                (source / name).write_bytes(payload)
            container = rr.SaveContainer.load(source)
            doc = container.document()
            with self.assertRaises(codec.SaveRostError):
                rr.save_document(doc, Path(td) / 'blocked')
            fixed, receipt = self.check.repair(container.savegame, source=str(source))
            ps.validate_save(fixed)
            container.write(Path(td) / 'copy', fixed)
            reopened = rr.SaveContainer.load(Path(td) / 'copy')
            self.assertEqual(reopened.savegame, fixed)
            self.assertEqual(reopened.members['SaveMeta.xbx'], b'metadata')
            self.assertEqual(rr.SaveContainer.load(source).savegame, bad)


class RetailTests(unittest.TestCase):
    def test_preserved_franchise_fixtures_scan_and_in_memory_fault_repair(self):
        from tests.mod_editor.test_nfl2k5_franchise_save import F0, F1, FRANCHISE1
        from mod_editor.core import nfl2k5_college_check as check
        present = [p for p in (F0, F1, FRANCHISE1) if p.is_file()]
        if not present:
            self.skipTest(f'private NFL 2K5 franchise fixtures absent under {F0.parents[5]}')
        for path in present:
            container = rr.SaveContainer.load(path)
            original = container.savegame
            self.assertEqual(check.scan(original).findings, ())
            for kind in ('null', 'outside', 'misaligned', 'interior_string'):
                with self.subTest(path=str(path), kind=kind):
                    bad, field = corrupt(original, kind)
                    if kind == 'outside':
                        with self.assertRaises(codec.SaveRostError):
                            ps.validate_save(bad)
                    fixed, receipt = check.repair(bad, source=str(path))
                    ps.validate_save(fixed)
                    self.assertEqual(fixed[:field] + fixed[field + 4:], bad[:field] + bad[field + 4:])
            self.assertEqual(path.read_bytes(), original)

    def test_retail_scan_has_zero_findings(self):
        if not (RETAIL_EXTRACTION / 'vc_53450030' / '0').is_file():
            self.skipTest(f'private NFL 2K5 retail pack absent: {RETAIL_EXTRACTION / "vc_53450030/0"}')
        from mod_editor.core import nfl2k5_college_check as check
        doc = rr.load_image(RETAIL_EXTRACTION)
        self.assertEqual(hashlib.sha256(doc.original).hexdigest(), rr.RETAIL_BODY_SHA256)
        scan = check.scan(doc.original, source=str(RETAIL_EXTRACTION))
        self.assertEqual(scan.player_count, 2547)
        self.assertEqual(scan.findings, ())
        self.assertEqual(scan.table_issues, ())
        self.assertEqual(check.repair(doc.original)[0], doc.original)
        bad, field = corrupt(doc.original, 'outside')
        fixed, receipt = check.repair(bad)
        self.assertEqual(receipt['college_index'], 187)
        self.assertEqual(rr.RosterDocument(fixed).players[0].college, 'None')
        self.assertEqual(fixed[:field] + fixed[field + 4:], bad[:field] + bad[field + 4:])


if __name__ == '__main__':
    unittest.main()
