"""Portable synthetic frames plus both preserved, hash-pinned real v0 saves."""
from pathlib import Path
import hashlib
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_roster_records as records


def fixture(version=0, *, prefix=b'opaque-prefix' * 4, suffix=b'opaque-suffix' * 7):
    """Build a runtime arena directly, independent of the disc-only decoder."""
    # Word alignment matters for UTF-16 pointers, not the arbitrary prefix text.
    prefix += b'\0' * (-len(prefix) % 4)
    delta = 0x20 if version == 0 else 0x40
    base = len(prefix) + 0x20
    root = base + delta
    end = root + 0x2000
    data = bytearray(prefix + bytes(0x20 + delta + 0x2000) + suffix)
    wrapper = len(prefix)
    data[wrapper:wrapper + 4] = b'ROST'
    struct.pack_into('<II', data, wrapper + 4, end - base, 0x16E)
    data[base + 12:base + 16] = b'ROST'
    struct.pack_into('<Ii', data, base + 16, version, root - (base + 20) + 1)

    def rel(field, target):
        struct.pack_into('<i', data, field, target - field + 1)

    players, team, college, pool = root + 0x100, root + 0x300, root + 0x600, root + 0x800
    for field, count, target in ((0, 2, players), (0x18, 1, team), (0x20, 1, college)):
        struct.pack_into('<I', data, root + field, count)
        rel(root + field + 4, target)
    struct.pack_into('<I', data, root + 0x40, 2)
    rel(root + 0x44, pool)
    text_at = root + 0xA00

    def name(field, text):
        nonlocal text_at
        raw = text.encode('utf-16-le') + b'\0\0'
        rel(field, text_at)
        data[text_at:text_at + len(raw)] = raw
        text_at += len(raw)

    name(college, 'Test College')
    name(team + 0x104, 'Testers')
    name(team + 0x108, 'TST')
    name(team + 0x138, 'Test City')
    data[team + 0x11C] = 2
    for i in range(2):
        at = players + i * 0x54
        rel(at, college)
        name(at + 0x10, ('Ada', 'Grace')[i])
        name(at + 0x14, ('Tester', 'Coder')[i])
        data[at + 0x36] = 65 + i
        struct.pack_into('<I', data, at + 0x24, 3 << 8)
        rel(team + i * 4, at)
        rel(at + 0x2C, pool + i * 4)
        struct.pack_into('<I', data, pool + i * 4, 0x80000000 | (2 << 23) | 16)
    return bytes(data)


class SaveRostTests(unittest.TestCase):
    def test_both_framings_exact_roundtrip(self):
        for version in (0, 17):
            with self.subTest(version=version):
                payload = fixture(version)
                doc = codec.decode(payload)
                self.assertEqual(codec.encode(doc), payload)
                self.assertEqual(doc.layout.root - doc.layout.preamble, 0x20 if version == 0 else 0x40)
                self.assertEqual(doc.players[0].first, 'Ada')
                self.assertEqual(doc.teams[0].abbreviation, 'TST')
                self.assertEqual(doc.history_words['primary', 1], (0x81000010,))

    def test_edit_is_exactly_one_byte_and_does_not_touch_framing(self):
        payload = fixture()
        doc = codec.decode(payload)
        doc.edit_player('primary', 0, {'speed': 91})
        encoded = doc.to_bytes()
        changed = [i for i, (a, b) in enumerate(zip(payload, encoded)) if a != b]
        self.assertEqual(changed, [doc.players[0].offset + 0x36])
        self.assertEqual(codec.decode(encoded).players[0].record.values['speed'], 91)
        self.assertEqual(doc.to_bytes(), encoded)

    def test_atomic_field_validation(self):
        doc = codec.decode(fixture())
        with self.assertRaises(codec.SaveRostError):
            doc.edit_player('primary', 0, {'speed': 99, 'not_a_field': 1})
        self.assertEqual(doc.to_bytes(), doc.original)
        for fields in ({'speed': 256}, {'speed': True}, {'history_pointer': 0}):
            with self.assertRaises(codec.SaveRostError):
                doc.edit_player('primary', 0, fields)
        self.assertEqual(doc.to_bytes(), doc.original)

    def test_direct_pointer_mutation_refused(self):
        doc = codec.decode(fixture())
        doc.players[0].record.values['history_pointer'] = 0
        with self.assertRaisesRegex(codec.SaveRostError, 'pointer mutation'):
            doc.to_bytes()

    def test_corruption_matrix(self):
        original = fixture()
        doc = codec.decode(original)
        root, base = doc.layout.root, doc.layout.preamble
        player = doc.players[0].offset
        cases = ((base + 16, '<I', 18), (base + 20, '<i', 1),
                 (doc.layout.wrapper + 4, '<I', len(original) * 2),
                 (root, '<I', 8001), (root + 4, '<i', -root - 500),
                 (root + 4, '<i', len(original)), (root + 0x40, '<I', 50001),
                 (player + 0x10, '<i', len(original)), (player + 0x2C, '<i', 1),
                 (doc.teams[0].offset + 0x11C, '<B', 66))
        for offset, form, value in cases:
            with self.subTest(offset=offset, value=value):
                corrupt = bytearray(original)
                struct.pack_into(form, corrupt, offset, value)
                with self.assertRaises(codec.SaveRostError):
                    codec.decode(corrupt)

    def test_table_cannot_escape_into_suffix(self):
        payload = fixture(suffix=bytes(0x500))
        doc = codec.decode(payload)
        corrupt = bytearray(payload)
        field = doc.layout.root + 4
        struct.pack_into('<i', corrupt, field, doc.layout.end - field + 1)
        with self.assertRaises(codec.SaveRostError):
            codec.decode(corrupt)

    def test_unterminated_history_and_string_refused(self):
        for field in ('history', 'string'):
            corrupt = bytearray(fixture())
            doc = codec.decode(corrupt)
            if field == 'history':
                struct.pack_into('<II', corrupt, doc.pool, 16, 16)
            else:
                pointer = doc.players[0].offset + 0x10
                struct.pack_into('<i', corrupt, pointer, doc.layout.end - 2 - pointer + 1)
                corrupt[doc.layout.end - 2:doc.layout.end] = b'AA'
            with self.subTest(field=field), self.assertRaises(codec.SaveRostError):
                codec.decode(corrupt)

    def test_ambiguity_and_truncation_refused(self):
        one = fixture(prefix=b'', suffix=b'')
        with self.assertRaisesRegex(codec.SaveRostError, 'ambiguous'):
            codec.decode(one + one)
        for data in (b'', b'ROST', one[:-1]):
            with self.assertRaises(codec.SaveRostError):
                codec.decode(data)


HUB = Path(os.environ.get('NFL2K5_SAVE_FIXTURES', '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
PINS = {'f0': '56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8',
        'f1': '255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed'}


class RealSaveTests(unittest.TestCase):
    def test_two_real_signed_runtime_saves(self):
        for name, digest in PINS.items():
            path = HUB / name / 'UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
            if not path.is_file():
                self.skipTest(f'private version-0 fixture missing: {path}; set NFL2K5_SAVE_FIXTURES')
            with self.subTest(fixture=name):
                source = path.read_bytes()
                extra = path.with_name('EXTRA').read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(), digest)
                self.assertTrue(records.verify_extra(source, extra))
                document, container = codec.load_save(path)
                self.assertEqual(document.layout.root, 0x320)
                self.assertEqual(document.layout.end, 0x91320)
                self.assertEqual(len(document.players), 2547)
                self.assertEqual(len(document.teams), 52)
                self.assertEqual(document.to_bytes(), source)
                self.assertEqual(container.members[container.extra_name], extra)
                document.edit_player('primary', 0, {'speed': 88})
                output = document.to_bytes()
                self.assertEqual([i for i, (a, b) in enumerate(zip(source, output)) if a != b], [0xB2BE])
                self.assertEqual(codec.decode(output).players[0].record.values['speed'], 88)
                self.assertEqual(output[:0x320], source[:0x320])
                self.assertEqual(output[0x91320:], source[0x91320:])
                # Exercise the unchanged signing/container layer on a new,
                # disposable copy; never rewrite the preserved fixture.
                with tempfile.TemporaryDirectory(prefix='runtime-save-copy-') as temporary:
                    target = Path(temporary) / 'edited.zip'
                    container.write(target, output)
                    reloaded, signed = codec.load_save(target)
                    self.assertTrue(signed.verified)
                    self.assertEqual(reloaded.to_bytes(), output)
                    self.assertNotEqual(signed.members[signed.extra_name], extra)
                self.assertEqual(path.read_bytes(), source)
                self.assertEqual(path.with_name('EXTRA').read_bytes(), extra)


if __name__ == '__main__':
    unittest.main()
