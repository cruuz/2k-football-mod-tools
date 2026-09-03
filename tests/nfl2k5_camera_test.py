"""Camera-descriptor and HUD-layout patches: pattern-driven, fail-closed, copy-only.

Synthetic fixture: a minimal XBE whose .text, .rdata and .data sections carry the retail bytes at
their retail virtual addresses (Standard and Far camera descriptors, the option default, the
kick-meter operand, the lineup gate, the float constants), with correct section digests.  A
retail-XBE smoke test runs only when the private copy exists.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_camera as camera  # noqa: E402
from mod_editor.core import nfl2k5_hud_layout as hud  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
TABLE_OFF = 0x200
HEADER_SIZE = 0xCC4
TEXT_VA, TEXT_RAW, TEXT_SIZE = 0x11000, 0x2000, 0x100000          # covers 0xBAB52, 0xE3C68 and 0xFFA80
RDATA_VA, RDATA_RAW, RDATA_SIZE = 0x4E3AE0, 0x102000, 0x30000     # covers the float constants and 0x4F03F8
DATA_VA, DATA_RAW, DATA_SIZE = 0xA69980, 0x132000, 0x20000        # covers 0xA87F10..0xA89800
RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")


def _digest(payload: bytes, raw: int, size: int) -> bytes:
    return hashlib.sha1(struct.pack("<I", size) + payload[raw: raw + size]).digest()  # nosec B324


def build_xbe() -> bytes:
    buf = bytearray(DATA_RAW + DATA_SIZE)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<I", buf, 0x108, HEADER_SIZE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT, IMAGE_BASE + TABLE_OFF)
    layout = {0: (TEXT_VA, TEXT_RAW, TEXT_SIZE), 1: (RDATA_VA, RDATA_RAW, RDATA_SIZE), 3: (DATA_VA, DATA_RAW, DATA_SIZE)}
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index in layout:
            fields[1], fields[3], fields[4] = layout[index]
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)
    # camera descriptors (.data): Standard row and Far row
    for state, va in camera.STANDARD_DESCRIPTORS.items():
        off = DATA_RAW + (va - DATA_VA)
        buf[off: off + camera.DESCRIPTOR_SIZE] = camera.RETAIL_DESCRIPTORS[state]
    for state, va in camera.FAR_DESCRIPTORS.items():
        off = DATA_RAW + (va - DATA_VA)
        buf[off: off + camera.DESCRIPTOR_SIZE] = camera.FAR_RETAIL_DESCRIPTORS[state]
    # preset/state table rows 0 and 1 (.rdata): only the entries the tests read
    for row, table in ((camera.STANDARD_ROW, camera.STANDARD_DESCRIPTORS), (camera.FAR_ROW, camera.FAR_DESCRIPTORS)):
        for state, va in table.items():
            off = RDATA_RAW + (camera.PRESET_TABLE_VA - RDATA_VA) + (row * camera.STATES_PER_ROW + state) * 8
            struct.pack_into("<II", buf, off, 0, va)
    # the fresh-profile option default (.text)
    site = TEXT_RAW + (camera.OPTION_DEFAULT_SITE_VA - TEXT_VA)
    buf[site: site + len(camera.RETAIL_OPTION_DEFAULT)] = camera.RETAIL_OPTION_DEFAULT
    # float constants (.rdata)
    for margin, va in hud.KICK_MARGIN_CONSTANTS.items():
        struct.pack_into("<f", buf, RDATA_RAW + (va - RDATA_VA), margin)
    # kick meter operand and lineup gate (.text)
    site = TEXT_RAW + (hud.KICK_MARGIN_SITE_VA - TEXT_VA)
    buf[site: site + 6] = hud.FSUB_M32 + struct.pack("<I", hud.KICK_RETAIL_OPERAND_VA)
    gate = TEXT_RAW + (hud.LINEUP_GATE_VA - TEXT_VA)
    buf[gate: gate + len(hud.LINEUP_RETAIL_HEAD)] = hud.LINEUP_RETAIL_HEAD
    for index, (_va, raw, size) in layout.items():
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        buf[header + 36: header + 56] = _digest(bytes(buf), raw, size)
    return bytes(buf)


class CameraPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_xbe()

    def test_retail_transcripts_decode_to_the_documented_values(self) -> None:
        for state, record in camera.RETAIL_DESCRIPTORS.items():
            decoded = camera.decode_descriptor(record)
            target, fov, offset = camera.RETAIL_VALUES[state]
            self.assertEqual(decoded["target"], target, state)
            self.assertEqual(decoded["fov"], fov, state)
            self.assertEqual(decoded["offset"], offset, state)
            self.assertEqual(decoded["type"], 2, state)
            self.assertEqual(decoded["lag_block"], 0x4F0380, state)
        self.assertEqual(camera.decode_descriptor(camera.RETAIL_DESCRIPTORS[16])["frame_callback"], 0xA4A50)
        for state, record in camera.FAR_RETAIL_DESCRIPTORS.items():
            decoded = camera.decode_descriptor(record)
            target, fov, offset = camera.FAR_RETAIL_VALUES[state]
            self.assertEqual((decoded["target"], decoded["fov"], decoded["offset"]), (target, fov, offset), state)
            self.assertEqual(decoded["type"], 2, state)
        self.assertEqual(camera.decode_descriptor(camera.FAR_RETAIL_DESCRIPTORS[16])["frame_callback"], 0xA4C30)

    def test_default_preset_is_the_far_look(self) -> None:
        self.assertEqual(camera.DEFAULT_PRESET, "far_look")
        self.assertEqual(camera.PRESETS["far_look"], camera.FAR_RETAIL_VALUES)
        # Far is Standard's geometry through a wider lens; only states 15 and 19 differ in position
        for state in (9, 13, 16, 17, 18):
            self.assertEqual(camera.FAR_RETAIL_VALUES[state][0], camera.RETAIL_VALUES[state][0], state)
            self.assertEqual(camera.FAR_RETAIL_VALUES[state][2], camera.RETAIL_VALUES[state][2], state)
            self.assertLess(camera.FAR_RETAIL_VALUES[state][1], camera.RETAIL_VALUES[state][1], state)

    def test_apply_rewrites_only_the_geometry_words(self) -> None:
        self.assertEqual(camera.status(self.payload), "retail")
        self.assertEqual(camera.detect_preset(self.payload), "retail")
        patched, receipt = camera.apply(self.payload)
        self.assertEqual(camera.status(patched), "applied")
        self.assertEqual(camera.detect_preset(patched), "far_look")
        self.assertEqual(receipt["preset"], "far_look")
        self.assertEqual(receipt["option_default"], "standard")
        self.assertEqual(len(receipt["edits"]), len(camera.STANDARD_DESCRIPTORS))
        self.assertEqual(receipt["sections_repinned"], [3])
        for state, va in camera.STANDARD_DESCRIPTORS.items():
            off = DATA_RAW + (va - DATA_VA)
            before = self.payload[off: off + camera.DESCRIPTOR_SIZE]
            after = patched[off: off + camera.DESCRIPTOR_SIZE]
            self.assertEqual(before[:camera.FIELD_TARGET], after[:camera.FIELD_TARGET])
            self.assertEqual(before[0x1C:camera.FIELD_FOV], after[0x1C:camera.FIELD_FOV])
            self.assertEqual(before[0x24:camera.FIELD_OFFSET], after[0x24:camera.FIELD_OFFSET])
            self.assertEqual(before[0x3C:], after[0x3C:])          # type, lag, callbacks stay Standard's own
            decoded = camera.decode_descriptor(after)
            target, fov, offset = camera.PRESETS[camera.DEFAULT_PRESET][state]
            self.assertEqual(decoded["target"], target)
            self.assertEqual(decoded["fov"], fov)
            self.assertEqual(decoded["offset"], offset)
        # the Far row is byte-identical before and after
        for va in camera.FAR_DESCRIPTORS.values():
            off = DATA_RAW + (va - DATA_VA)
            self.assertEqual(self.payload[off: off + camera.DESCRIPTOR_SIZE], patched[off: off + camera.DESCRIPTOR_SIZE])
        # and Standard now reads exactly like Far
        standard, far = camera.read_standard(patched), camera.read_far(patched)
        for state in camera.STANDARD_DESCRIPTORS:
            self.assertEqual((standard[state]["target"], standard[state]["fov"], standard[state]["offset"]),
                             (far[state]["target"], far[state]["fov"], far[state]["offset"]), state)
        header = TABLE_OFF + 3 * strength.SECTION_HEADER_SIZE
        self.assertEqual(patched[header + 36: header + 56], _digest(patched, DATA_RAW, DATA_SIZE))
        with self.assertRaises(camera.CameraPatchError):
            camera.apply(patched)
        self.assertEqual(camera.read_standard(patched)[16]["offset"], (0.0, 270.0, -750.0))
        self.assertEqual(camera.read_standard(patched)[16]["fov"], 28.0)
        # the option default (0 = Standard) is retail and left alone
        self.assertEqual(camera.option_default_status(patched), "standard")
        site = TEXT_RAW + (camera.OPTION_DEFAULT_SITE_VA - TEXT_VA)
        self.assertEqual(patched[site: site + len(camera.RETAIL_OPTION_DEFAULT)], camera.RETAIL_OPTION_DEFAULT)

    def test_broadcast_wide_stays_available_as_a_named_preset(self) -> None:
        for state, (target, fov, offset) in camera.PRESETS["broadcast_wide"].items():
            _rt, rfov, roff = camera.RETAIL_VALUES[state]
            self.assertLess(offset[2], roff[2], state)        # further behind the ball
            self.assertGreater(offset[1], roff[1], state)     # higher
            self.assertLessEqual(fov, rfov, state)            # lower word = wider lens
            self.assertGreaterEqual(-offset[2], 2000.0)
            self.assertLessEqual(-offset[2], 2500.0)
        patched, receipt = camera.apply(self.payload, preset="broadcast_wide")
        self.assertEqual(receipt["preset"], "broadcast_wide")
        self.assertEqual(camera.status(patched, "broadcast_wide"), "applied")
        self.assertEqual(camera.status(patched), "foreign")           # not the default preset
        self.assertEqual(camera.detect_preset(patched), "broadcast_wide")
        with self.assertRaises(camera.CameraPatchError):
            camera.apply(patched)                                     # one preset at a time, from retail only

    def test_foreign_bytes_are_refused(self) -> None:
        buf = bytearray(self.payload)
        off = DATA_RAW + (camera.STANDARD_DESCRIPTORS[16] - DATA_VA) + camera.FIELD_FOV
        buf[off] ^= 0x01
        self.assertEqual(camera.status(bytes(buf)), "foreign")
        self.assertIsNone(camera.detect_preset(bytes(buf)))
        with self.assertRaises(camera.CameraPatchError):
            camera.apply(bytes(buf))
        self.assertEqual(camera.status(b"\x00" * 0x400), "foreign")
        with self.assertRaises(camera.CameraPatchError):
            camera.apply(self.payload, preset="no_such_preset")

    def test_preset_table_reader(self) -> None:
        rows = camera.read_preset_table(self.payload)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0][16], (0, camera.STANDARD_DESCRIPTORS[16]))
        self.assertEqual(rows[1][16], (0, camera.FAR_DESCRIPTORS[16]))


class HudLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = build_xbe()

    def test_status_and_apply_both_sites(self) -> None:
        self.assertEqual(hud.status(self.payload), {"kick_meter_margin": "retail", "lineup_insert": "retail"})
        patched, receipt = hud.apply(self.payload, kick_margin=150.0, lineup_insert_off=True)
        self.assertEqual(hud.status(patched), {"kick_meter_margin": "150.0", "lineup_insert": "off"})
        # operand 0x4E6C48 -> 0x4E88E4 differs in 2 bytes, the gate head in 3, the .text digest in 20
        self.assertEqual(receipt["changed_bytes"], 2 + 3 + 20)
        site = TEXT_RAW + (hud.KICK_MARGIN_SITE_VA - TEXT_VA)
        self.assertEqual(patched[site: site + 6], bytes.fromhex("d825") + struct.pack("<I", 0x4E88E4))
        self.assertEqual(struct.unpack_from("<f", patched, RDATA_RAW + (0x4E88E4 - RDATA_VA))[0], 150.0)
        gate = TEXT_RAW + (hud.LINEUP_GATE_VA - TEXT_VA)
        self.assertEqual(patched[gate: gate + 3], bytes.fromhex("33c0c3"))
        self.assertEqual(patched[gate + 3: gate + 16], hud.LINEUP_RETAIL_HEAD[3:])
        header = TABLE_OFF + 0 * strength.SECTION_HEADER_SIZE
        self.assertEqual(patched[header + 36: header + 56], _digest(patched, TEXT_RAW, TEXT_SIZE))
        with self.assertRaises(hud.HudLayoutError):
            hud.apply(patched, kick_margin=150.0)
        with self.assertRaises(hud.HudLayoutError):
            hud.apply(patched, kick_margin=None, lineup_insert_off=True)

    def test_each_site_can_be_applied_alone(self) -> None:
        only_kick, _ = hud.apply(self.payload, kick_margin=120.0)
        self.assertEqual(hud.status(only_kick), {"kick_meter_margin": "120.0", "lineup_insert": "retail"})
        only_lineup, receipt = hud.apply(self.payload, kick_margin=None, lineup_insert_off=True)
        self.assertEqual(hud.status(only_lineup), {"kick_meter_margin": "retail", "lineup_insert": "off"})
        self.assertEqual([e["label"] for e in receipt["edits"]], ["lineup_insert_off"])

    def test_unsupported_margin_and_foreign_bytes_are_refused(self) -> None:
        with self.assertRaises(hud.HudLayoutError):
            hud.apply(self.payload, kick_margin=155.0)
        with self.assertRaises(hud.HudLayoutError):
            hud.apply(self.payload, kick_margin=None, lineup_insert_off=False)
        buf = bytearray(self.payload)
        struct.pack_into("<f", buf, RDATA_RAW + (0x4E88E4 - RDATA_VA), 151.0)   # the constant no longer holds 150
        with self.assertRaises(hud.HudLayoutError):
            hud.apply(bytes(buf), kick_margin=150.0)
        buf = bytearray(self.payload)
        buf[TEXT_RAW + (hud.LINEUP_GATE_VA - TEXT_VA)] = 0x90
        self.assertEqual(hud.lineup_status(bytes(buf)), "foreign")
        self.assertEqual(hud.status(b"\x00" * 0x400), {"kick_meter_margin": "foreign", "lineup_insert": "foreign"})


@unittest.skipUnless(RETAIL_XBE.exists(), "retail default.xbe not present")
class RetailSmokeTests(unittest.TestCase):
    def test_retail_executable_reads_as_retail_everywhere(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(camera.status(payload), "retail")
        self.assertEqual(camera.option_default_status(payload), "standard")
        self.assertEqual(hud.status(payload), {"kick_meter_margin": "retail", "lineup_insert": "retail"})
        table = camera.read_preset_table(payload)
        for state, va in camera.STANDARD_DESCRIPTORS.items():
            self.assertEqual(table[0][state][1], va, state)
        for state, va in camera.FAR_DESCRIPTORS.items():
            self.assertEqual(table[1][state][1], va, state)
        self.assertEqual(table[1][16][1], 0xA88D20)      # Far's live descriptor
        self.assertEqual(table[5][16][1], 0xA893B0)      # Custom's live descriptor
        # no other row references a Standard record (the patch cannot leak into another preset)
        standard_records = set(camera.STANDARD_DESCRIPTORS.values())
        for row in range(1, len(table)):
            for _flags, descriptor in table[row]:
                self.assertNotIn(descriptor, standard_records, row)
        standard = camera.read_standard(payload)
        for state, (target, fov, offset) in camera.RETAIL_VALUES.items():
            self.assertEqual(standard[state]["target"], target)
            self.assertEqual(standard[state]["fov"], fov)
            self.assertEqual(standard[state]["offset"], offset)
        far = camera.read_far(payload)
        for state, (target, fov, offset) in camera.FAR_RETAIL_VALUES.items():
            self.assertEqual((far[state]["target"], far[state]["fov"], far[state]["offset"]), (target, fov, offset), state)
        patched, _ = camera.apply(payload)
        patched, _ = hud.apply(patched, kick_margin=150.0, lineup_insert_off=True)
        self.assertEqual(camera.status(patched), "applied")
        self.assertEqual(hud.status(patched), {"kick_meter_margin": "150.0", "lineup_insert": "off"})


if __name__ == "__main__":
    unittest.main()
