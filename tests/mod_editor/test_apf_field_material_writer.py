"""Synthetic SCNE and H7A tests; no retail scene bytes are embedded."""
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf_field_material_writer as w
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_book_unlock import iff


def scene_fixture():
    scene = bytearray(0x2400)
    table = 0x100
    struct.pack_into('>I', scene, 0x30, 14)
    struct.pack_into('>i', scene, 0x38, table - 0x38 + 1)
    for i in range(14):
        record, payload = table + i * 0x28, 0x400 + i * 0x200
        struct.pack_into('>I', scene, record, w.MATERIAL_IDS[i] if i < 12 else i)
        struct.pack_into('>I', scene, record + 8, 0x868B853C if i == 1 else 0xAB01CC7A)
        struct.pack_into('>i', scene, record + 0x20, payload - record - 0x20 + 1)
        struct.pack_into('>4I', scene, payload, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0)
        struct.pack_into('>4f', scene, payload + (0x100 if i == 1 else 0x70), 1, 1, 1, 0.6)
    return bytes(scene)


class FieldMaterialTests(unittest.TestCase):
    def test_all_named_materials_roundtrip_and_idempotence(self):
        before = scene_fixture()
        values = {name: (i % 5) / 4 for i, name in enumerate(w.MATERIALS)}
        after, report = w.compile_scene(before, values)
        self.assertEqual(len(report['changes']), 11)
        self.assertTrue(report['reparsed'])
        self.assertEqual(w.compile_scene(after, values)[0], after)
        self.assertEqual(w.verify_scene(before, after, values), report)
        self.assertEqual(w.parse_scene(after)[1].alpha_offset - w.parse_scene(after)[1].payload_offset, 0x10C)

    def test_invalid_alpha_material_and_corrupt_layout_refused(self):
        before = scene_fixture()
        for value in (float('nan'), float('inf'), -0.1, 1.1, True, '0.5'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                w.compile_scene(before, {'ticks': value})
        with self.assertRaises(ValidationError): w.compile_scene(before, {'unknown': 0.5})
        for at, value in ((0x38, 0), (0x38, 0xFFFF0000), (0x30, 1000), (0x100, 0), (0x120, 1)):
            bad = bytearray(before); struct.pack_into('>I', bad, at, value)
            with self.subTest(offset=at), self.assertRaises(ValidationError): w.parse_scene(bytes(bad))

    def test_reparse_rejects_other_alpha_rgb_pointer_and_unowned_byte_changes(self):
        before = scene_fixture(); after, _ = w.compile_scene(before, {'ticks': 0.2})
        for at in (0x90, w.parse_scene(before)[0].alpha_offset, w.parse_scene(before)[2].alpha_offset - 4):
            bad = bytearray(after); bad[at] ^= 1
            with self.subTest(offset=at), self.assertRaises(ValidationError):
                w.verify_scene(before, bytes(bad), {'ticks': 0.2})

    def test_h7a_fixed_allocation_roundtrip_and_no_overlap(self):
        source = iff(scene_fixture(), 'field', 'SCNE')
        entry = w.apf_outer.Entry(53, w.ENTRY_NAME_IDS[53], 0, len(source)//2048, 0, len(source), '', ())
        after, report = w.compile_entry(entry, source, {k: 0.25 for k in w.OVERLAYS})
        self.assertEqual(len(source), len(after))
        self.assertEqual(report['transport']['overlapping_matches'], 0)
        self.assertTrue(report['transport']['reparsed'])
        # A second edit composes with the first in the same compressed entry.
        composed, _ = w.compile_entry(entry, after, {'ticks': 0.1})
        _, part, block = w._parse_entry(entry, composed)
        parsed = {m.name: m.alpha for m in w.parse_scene(block[part.offset:part.offset+part.length])}
        self.assertEqual(parsed['graphic_overlay_4'], 0.25)
        self.assertAlmostEqual(parsed['ticks'], 0.1)

    def test_nonzero_allocation_tail_refused(self):
        source = bytearray(iff(scene_fixture(), 'field', 'SCNE')); source[-1] = 7
        entry = w.apf_outer.Entry(53, 0, 0, len(source)//2048, 0, len(source), '', ())
        with self.assertRaisesRegex(ValidationError, 'tail'):
            w.compile_entry(entry, bytes(source), {'ticks': 0.2})


if __name__ == '__main__': unittest.main()
