"""Lossless icon repair, exact input guards, relocation and replay."""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_menu_icon_orientation as icons
from mod_editor.core import nfl2k5_modern_fans as fans
from mod_editor.core import nfl2k5_historic_styles as hs
from tools.b77.ic1_repair import Overlay, compare_stream, main as repair_main


def slot(name, seed):
    tx, _ = fans._tools()
    system = bytearray(128)
    system[12:16] = b"TXTR"
    struct.pack_into("<II", system, 16, 0x18 - 0x0f, 0x40 - 0x13)
    text = name.encode("utf-16le") + b"\0\0"
    system[24:24 + len(text)] = text
    struct.pack_into("<5I", system, 0x44, 0, 4096,
                     (6 << 24) | (6 << 20) | (1 << 16) | (0x0b << 8) | (2 << 4), 0, 0)
    pixels = bytes((x * 3 + y * 11 + seed) % 256 for y in range(64) for x in range(64))
    palette = bytes(v for i in range(256) for v in (i, 255 - i, (i * 7) % 256, 255))
    return tx.HEADER.pack(b"TXTR", 5248, 128, 5120, 0, 0, 0, 0) + bytes(system) + tx.swizzle_2d(pixels, 64, 64, 1) + palette + bytes([seed]) * 96


class Archive:
    def __init__(self, target, donor, relocated=131072):
        names = sorted((icons.TARGET, icons.DONOR), key=hs.member_hash)
        record = bytearray(0x70)
        record[:4] = b"CACR"
        struct.pack_into("<I", record, 4, len(record) - 32)
        struct.pack_into("<4I", record, 0x60, 2, len(target), *(hs.member_hash(n) for n in names))
        self.data = bytearray(relocated + 2 * len(target))
        self.data[1024:1024 + len(record)] = record
        self.data[relocated:] = b"".join(target if n == icons.TARGET else donor for n in names)
        self.entries = [SimpleNamespace(name_id=hs.AGGREGATES[1]['record'], virtual_offset=1024, size=len(record)),
                        SimpleNamespace(name_id=hs.AGGREGATES[1]['cdf'], virtual_offset=relocated, size=2 * len(target))]

    def read(self, at, size):
        return bytes(self.data[at:at + size])

    def write(self, at, data):
        self.data[at:at + len(data)] = data
        return len(data)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.target, self.donor = slot(icons.TARGET, 3), slot(icons.DONOR, 19)

    def test_pixels_are_reflected_without_quantization_or_header_changes(self):
        result = icons.reflect_slot(self.target, self.donor)
        self.assertEqual(result[:160], self.target[:160])
        self.assertEqual(result[-96:], self.target[-96:])
        tx, _ = fans._tools()
        def rgba(s):
            c = tx.parse_chunks(s, allow_trailing=True)[0]
            d, _ = tx.decode_chunk(s, c)
            return tx.texture_to_rgba(d, c, tx.parse_texture(d, c))
        source, actual = rgba(self.donor), rgba(result)
        for y in range(64):
            for x in range(64):
                self.assertEqual(actual[(y * 64 + x) * 4:(y * 64 + x + 1) * 4],
                                 source[(y * 64 + 63 - x) * 4:(y * 64 + 64 - x) * 4])

    def test_bad_format_or_wrong_member_is_refused(self):
        for bad in (slot('mini_a09_0', 1), self.target[:164]):
            with self.assertRaises(ValueError):
                icons.reflect_slot(bad, self.donor)
        altered = bytearray(self.donor)
        altered[32 + 0x4c + 1] = 0x0c
        with self.assertRaises(ValueError):
            icons.reflect_slot(self.target, bytes(altered))

    def test_relocation_readback_scope_and_replay(self):
        after = icons.reflect_slot(self.target, self.donor)
        with patch.multiple(icons, BEFORE_SHA256=icons.sha(self.target),
                            DONOR_SHA256=icons.sha(self.donor), AFTER_SHA256=icons.sha(after)):
            for base in (131072, 262144):
                ar = Archive(self.target, self.donor, base)
                overlay = Overlay(ar)
                plan, row = icons.plan_archive(overlay)
                self.assertEqual(row['written'], 1)
                fans._write_all(overlay, plan)
                self.assertEqual(icons.plan_archive(overlay)[0], [])
                at = plan[0][0]
                self.assertEqual(overlay.read(0, at), ar.read(0, at))
                end = at + len(self.target)
                self.assertEqual(overlay.read(end, len(ar.data) - end), ar.read(end, len(ar.data) - end))

    def test_unknown_target_is_untouched_and_known_target_requires_pinned_donor(self):
        ar = Archive(self.target, self.donor)
        self.assertEqual(icons.plan_archive(ar)[1]['state'], 'not_applicable')
        with patch.object(icons, 'BEFORE_SHA256', icons.sha(self.target)):
            with self.assertRaisesRegex(ValueError, 'donor differs'):
                icons.plan_archive(ar)

    def test_studio_write_replays_and_partial_write_rolls_back(self):
        after = icons.reflect_slot(self.target, self.donor)
        with patch.multiple(icons, BEFORE_SHA256=icons.sha(self.target),
                            DONOR_SHA256=icons.sha(self.donor), AFTER_SHA256=icons.sha(after)):
            ar = Archive(self.target, self.donor)
            with patch('tools.nfl2k5_playbook_position_recode.OuterImage', return_value=ar):
                self.assertEqual(icons.apply_to_image('fixture')['written'], 1)
                self.assertEqual(icons.apply_to_image('fixture')['written'], 0)
            ar = Archive(self.target, self.donor)
            original = bytes(ar.data)
            real_write = ar.write
            calls = []
            def short_first(at, data):
                calls.append(at)
                return real_write(at, data[:100] if len(calls) == 1 else data)
            ar.write = short_first
            with patch('tools.nfl2k5_playbook_position_recode.OuterImage', return_value=ar):
                with self.assertRaisesRegex(ValueError, 'short Denver icon write'):
                    icons.apply_to_image('fixture')
            self.assertEqual(bytes(ar.data), original)

    def test_source_build_invokes_repair_after_imports_and_before_intro_relocation(self):
        source = (ROOT / 'mod_editor/core/mod_build.py').read_text()
        at = source.index('icon_receipt = icons.apply_to_image(target)')
        self.assertLess(source.index('fan_receipt = fans.apply_to_image(target,'), at)
        self.assertLess(at, source.index('cut = intro.finish_output(target, progress)'))

    def test_native_tool_rejects_unknown_input_and_outside_span_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base, output = root / 'base.bin', root / 'output.bin'
            base.write_bytes(bytes(range(64)))
            with self.assertRaisesRegex(ValueError, 'unknown input'):
                repair_main(['--input', str(base), '--receipts', str(root / 'receipts')])
            self.assertFalse((root / 'receipts').exists())
            ranges = [(10, bytes(range(10, 13)), b'xyz')]
            proof = compare_stream(base, ranges)
            self.assertEqual((proof['compared_bytes'], proof['changed_bytes'], proof['changed_outside_owned']), (64, 3, 0))
            valid = base.read_bytes()[:10] + b'xyz' + base.read_bytes()[13:]
            output.write_bytes(valid)
            self.assertEqual(compare_stream(base, ranges, output), proof)
            output.write_bytes(b'!' + valid[1:])
            with self.assertRaisesRegex(ValueError, 'differs from Studio output'):
                compare_stream(base, ranges, output)

    @unittest.skipUnless(os.environ.get('NFL2K5_IC1_BASE'), 'set NFL2K5_IC1_BASE for read-only base-disc proof')
    def test_real_base_matches_all_pins_and_replays(self):
        with fans._outer_image()(os.environ['NFL2K5_IC1_BASE']) as archive:
            overlay = Overlay(archive)
            plan, receipt = icons.plan_archive(overlay)
            self.assertEqual(receipt['written'], 1)
            self.assertEqual(receipt['changed_bytes'], 3531)
            fans._write_all(overlay, plan)
            self.assertEqual(icons.plan_archive(overlay)[0], [])


if __name__ == '__main__':
    unittest.main()
