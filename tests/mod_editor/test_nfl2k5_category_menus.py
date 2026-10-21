"""Root-menu regression: removing a group's last formation must not leave NULL previews."""
import struct
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from tests.mod_editor.test_nfl2k5_playbook_inspector import _fixture
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_formation_play_writer as writer
from mod_editor.core import nfl2k5_playbook_lint as lint
from mod_editor.core.errors import ValidationError


def fixture():
    raw = bytearray(_fixture())
    h = ip.RESOURCE_HEADER_SIZE
    struct.pack_into('<I', raw, h + 0x34, 2)
    struct.pack_into('<I', raw, h + 0x3C, 3)
    for base, stride, indices in ((ip.FORMATION_BASE, ip.FORMATION_SIZE, (1,)),
                                  (ip.CATEGORY_BASE, ip.CATEGORY_SIZE, (1, 2))):
        record = bytes(raw[h+base:h+base+stride])
        ptr = struct.unpack_from('<i', record)[0]
        for index in indices:
            dst = h + base + index*stride
            raw[dst:dst+stride] = record
            struct.pack_into('<i', raw, dst, ptr-index*stride)
    aux = h+ip.FORMATION_AUX_BASE
    raw[aux+ip.FORMATION_AUX_SIZE:aux+2*ip.FORMATION_AUX_SIZE] = raw[aux:aux+ip.FORMATION_AUX_SIZE]
    struct.pack_into('<II', raw, aux+0x48, 0x80, 1)
    struct.pack_into('<II', raw, aux+ip.FORMATION_AUX_SIZE+0x48, 2, 4)
    for index, code in enumerate((13, 13, 14)):
        raw[h+ip.CATEGORY_BASE+index*ip.CATEGORY_SIZE+4] = code
    return bytes(raw)


class CategoryMenuTests(unittest.TestCase):
    def test_same_code_sibling_does_not_rescue_empty_category(self):
        raw = fixture()
        self.assertEqual([r['members'] for r in ip.category_menu_rows(raw)], [[0], [], [1]])
        self.assertEqual(len(ip.category_menu_problems(raw)), 1)
        with patch.object(lint, 'resource_views', return_value=[]), patch.object(lint, 'defense_findings', return_value=[]):
            result = lint.lint_resource(raw)
        self.assertEqual([(f.code, f.severity) for f in result.findings], [('CATEGORY_EMPTY', 'error')])

    def test_retirement_remaps_owner_mask_and_name_pointer_only(self):
        raw = fixture()
        fixed, receipt = writer.compact_unused_categories(raw)
        rows = ip.category_menu_rows(fixed)
        self.assertEqual([r['members'] for r in rows], [[0], [1]])
        self.assertEqual([r['code'] for r in rows], [13, 14])
        aux = 32+ip.FORMATION_AUX_BASE
        self.assertEqual(struct.unpack_from('<II', fixed, aux+0x48), (0x80, 1))
        self.assertEqual(struct.unpack_from('<II', fixed, aux+ip.FORMATION_AUX_SIZE+0x48), (1, 2))
        self.assertEqual(fixed[32+ip.CATEGORY_BASE+32:32+ip.CATEGORY_BASE+48], bytes(16))
        allowed = {i for a,b in receipt['scopes'] for i in range(a,b)}
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,fixed))))
        self.assertEqual(ip.parse_playbook_resource(raw).formations, ip.parse_playbook_resource(fixed).formations)
        self.assertEqual(ip.parse_playbook_resource(raw).plays, ip.parse_playbook_resource(fixed).plays)
        self.assertEqual(writer.compact_unused_categories(fixed)[0], fixed)

    def test_native_alias_fallback_is_kept(self):
        raw = bytearray(fixture())
        aux = 32+ip.FORMATION_AUX_BASE
        struct.pack_into('<II',raw,aux+0x48,2,4)
        raw[32+ip.CATEGORY_BASE+2*16+4] = 0x40|13
        self.assertEqual(ip.category_menu_rows(raw)[0]['members'], [0,1])
        fixed, receipt = writer.compact_unused_categories(bytes(raw))
        self.assertEqual([r['index'] for r in receipt['removed']], [1])
        self.assertEqual(ip.category_menu_rows(fixed)[0]['members'], [0,1])

    def test_owned_empty_category_is_not_silently_deleted(self):
        raw = bytearray(fixture())
        struct.pack_into('<I',raw,32+ip.FORMATION_AUX_BASE+0x48,1)
        with self.assertRaisesRegex(ValidationError,'owned category'):
            writer.compact_unused_categories(bytes(raw))

    def test_source_compile_clears_retired_trailing_name_for_next_pack(self):
        raw = bytearray(fixture())
        struct.pack_into('<II', raw, 32+ip.FORMATION_AUX_BASE+ip.FORMATION_AUX_SIZE+0x48, 1, 2)
        cursor = ip.STRING_BASE + 100
        live_end = None
        for index, name in enumerate(('First', 'Second', 'Unused tail')):
            value = name.encode('utf-16le') + b'\0\0'
            field = ip.CATEGORY_BASE + index*16
            struct.pack_into('<i', raw, 32+field, cursor-field+1)
            raw[32+cursor:32+cursor+len(value)] = value
            cursor += len(value)
            if index == 1:
                live_end = cursor
        struct.pack_into('<I', raw, 32+writer.POOL_COUNT_WORD, (cursor-ip.STRING_BASE)//2)
        fixed, receipt = writer.compact_unused_categories(bytes(raw), trim_name_tail=True)
        self.assertEqual(fixed[32+live_end:32+cursor], bytes(cursor-live_end))
        self.assertEqual(struct.unpack_from('<I', fixed, 32+writer.POOL_COUNT_WORD)[0],
                         (live_end-ip.STRING_BASE)//2)
        self.assertEqual([c.name for c in ip.parse_playbook_resource(fixed).categories], ['First', 'Second'])
        self.assertIn([32+live_end,32+cursor], receipt['scopes'])

    def test_out_of_range_owner_and_mask_refuse(self):
        for offset,value in ((0x48,3),(0x4c,8)):
            raw = bytearray(fixture())
            struct.pack_into('<I',raw,32+ip.FORMATION_AUX_BASE+offset,value)
            with self.assertRaisesRegex(ValidationError,'out-of-range'):
                writer.compact_unused_categories(bytes(raw))


if __name__ == '__main__':
    unittest.main()
