"""Synthetic trace windows test missing-state and provenance boundaries."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from tools.scorebug_sprite import live, xemu_model


def method(offset, value, name='KNOWN[0]', sub=0):
    return f'nv2a_pgraph_method {sub}: 0x97 -> 0x{offset:04x} {name} 0x{value:x}'


class LiveTests(unittest.TestCase):
    def test_partial_window_and_missing_indices_are_not_empty_draw_proof(self):
        result = live.parse([method(0x17fc, 0), method(0x1b00, 128),
                             method(0x17fc, 6), method(0x17fc, 0)], first_line=40)
        self.assertEqual(result['counts']['orphan_ends'], 1)
        draw = result['draws'][0]
        self.assertEqual((draw['begin_line'], draw['end_line']), (42, 43))
        self.assertEqual(draw['state_writes']['0x1b00'], 41)
        self.assertNotIn('0x030c', draw['state'])
        self.assertEqual(draw['geometry_events'], [])
        self.assertFalse(draw['vertex_program_complete'])

    def test_upload_ports_use_component_not_event_count_and_advance_on_w(self):
        result = live.parse([method(0x1ea4, 6), method(0xb88, 12),
                             method(0xb8c, 13), method(0xb80, 14),
                             method(0x17fc, 6)])
        self.assertEqual(result['draws'][0]['vertex_constants'], {'26':12,'27':13,'28':14})
        self.assertIsNone(result['draws'][0]['end_line'])

    def test_program_residency_and_rewrites_are_indexed(self):
        lines = [method(0x1e9c, 8), method(0x1ea0, 8)]
        lines += [method(0xb00+i*4, v) for i,v in enumerate((2,4,6,1))]
        lines += [method(0x17fc, 6), method(0x17fc, 0),
                  method(0x1e9c, 8), method(0xb00, 7), method(0x17fc, 6)]
        a,b = live.parse(lines)['draws']
        self.assertEqual(a['vertex_program'], [2,4,6,1])
        self.assertEqual(b['vertex_program'], [7,4,6,1])
        self.assertTrue(b['vertex_program_complete'])

    def test_windows_do_not_share_missing_upload_pointers(self):
        live.parse([method(0x1ea4, 0), method(0xb80, 9)])
        result = live.parse([method(0xb80, 4), method(0x17fc, 6)])
        self.assertEqual(result['draws'][0]['vertex_constants'], {})
        self.assertEqual(result['counts']['uploads_without_load_pointer'], 1)

    def test_unhandled_and_unknown_names_do_not_become_state(self):
        result = live.parse([method(0x380, 8, '?[0]'),
            'nv2a_pgraph_method_unhandled 0: 0x97 -> 0x0380 0x8', method(0x17fc, 6)])
        self.assertNotIn('0x0380', result['draws'][0]['state'])
        with self.assertRaisesRegex(ValueError, 'line 1'):
            live.parse(['broken method'])

    def test_geometry_and_mutations_inside_draw_are_retained(self):
        lines = [method(0x17fc, 6), method(0x1800, 0x20001),
                 method(0x1810, 0x03000005), method(0x304, 1), method(0x17fc, 0)]
        draw = live.parse(lines)['draws'][0]
        self.assertEqual([v['value'] for v in draw['geometry_events']], [0x20001,0x03000005])
        self.assertEqual(draw['changes_inside'][0]['method'], '0x0304')
        self.assertNotIn('0x0304', draw['state'])

    def test_subchannels_and_abbreviated_indices_stay_distinct(self):
        lines = [method(0x1b00, 1), method(0x1b00, 2, sub=1), method(0x17fc, 6),
            'nv2a_pgraph_method_abbrev 0: 0x97 -> 0x1800 NV097_ARRAY_ELEMENT16 * 7',
            method(0x17fc, 0), method(0x17fc, 6, sub=1)]
        a,b = live.parse(lines)['draws']
        self.assertEqual([a['state']['0x1b00'], b['state']['0x1b00']], [1,2])
        self.assertTrue(a['geometry_events'][0]['indices_unknown'])

    def test_ram_and_raw_texture_refuse_truncation(self):
        self.assertEqual(live.read_ram(b'abcd', 1, 2), b'bc')
        for offset,size in ((-1,1),(0,-1),(3,2)):
            with self.assertRaises(ValueError):live.read_ram(b'abcd',offset,size)
        with self.assertRaises(ValueError):xemu_model.p8_texture(bytes(3),bytes(1024),2,2)
        with self.assertRaises(ValueError):xemu_model.p8_texture(bytes(4),bytes(1023),2,2)

    def test_rectangular_morton_decode_from_exact_bytes(self):
        palette = bytes(v for i in range(256) for v in (i,2,3,255))
        image = xemu_model.p8_texture(bytes(range(8)),palette,4,2)
        self.assertEqual([image.getpixel((x,0)) for x in range(4)],
                         [(3,2,v,255) for v in (0,1,4,5)])
        self.assertEqual([image.getpixel((x,1))[2] for x in range(4)], [2,3,6,7])


if __name__ == '__main__':unittest.main()
