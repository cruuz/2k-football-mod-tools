"""The bump-strength writer must stay pattern-driven, fail-closed, copy-only.

Fixtures are synthetic: a minimal XBE carrying the exact bump-strength switch
pattern, jump table, float/sock push handlers, and the scale-to-byte callee,
plus a valid 22-section table with a correct section digest.  No game file is
touched; a retail-XBE smoke test runs only when the extracted copy exists.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402

IMAGE_BASE = strength.IMAGE_BASE
CODE = 0x1000
CODE_SIZE = 0x800
TABLE_OFF = 0x200
CALLEE = CODE + 0x100
SWITCH = CODE + 0x200
JUMP_TABLE = CODE + 0x300
JERSEY_HANDLER = CODE + 0x400
PANTS_HANDLER = CODE + 0x410
SOCK_HANDLER = CODE + 0x420
RETAIL_XBE = Path("/tmp/opencode/espn26/default.xbe")


def _section_digest(payload: bytes, raw: int, raw_size: int) -> bytes:
    return hashlib.sha1(  # nosec B324 - XBE section scheme, not security
        struct.pack("<I", raw_size) + payload[raw : raw + raw_size]
    ).digest()


def _build_synthetic_xbe(jersey: float = 0.1, pants: float = 0.3) -> bytes:
    buf = bytearray(0x2000)
    buf[0:4] = strength.XBE_MAGIC
    struct.pack_into("<I", buf, 0x104, IMAGE_BASE)
    struct.pack_into("<II", buf, 0x11C, strength.SECTION_COUNT,
                     IMAGE_BASE + TABLE_OFF)
    for index in range(strength.SECTION_COUNT):
        header = TABLE_OFF + index * strength.SECTION_HEADER_SIZE
        fields = [0] * 9 + [b"\x00" * 20]
        if index == 0:
            fields[1] = IMAGE_BASE + CODE
            fields[3] = CODE
            fields[4] = CODE_SIZE
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, header, *fields)

    buf[CALLEE : CALLEE + len(strength.CALLEE_PROLOGUE)] = (
        strength.CALLEE_PROLOGUE
    )
    buf[SWITCH : SWITCH + len(strength.SWITCH_PATTERN)] = (
        strength.SWITCH_PATTERN
    )
    struct.pack_into("<I", buf, SWITCH + len(strength.SWITCH_PATTERN),
                     IMAGE_BASE + JUMP_TABLE)
    struct.pack_into(
        "<4I", buf, JUMP_TABLE,
        IMAGE_BASE + JERSEY_HANDLER,
        IMAGE_BASE + PANTS_HANDLER,
        IMAGE_BASE + JERSEY_HANDLER,
        IMAGE_BASE + SOCK_HANDLER,
    )
    for handler, value in ((JERSEY_HANDLER, jersey), (PANTS_HANDLER, pants)):
        buf[handler] = strength.FLOAT_PUSH
        struct.pack_into("<f", buf, handler + 1, value)
        buf[handler + 5] = 0xE8
        struct.pack_into("<i", buf, handler + 6, CALLEE - handler - 10)
    buf[SOCK_HANDLER] = 0x6A
    buf[SOCK_HANDLER + 1] = 0x00
    buf[SOCK_HANDLER + 2] = 0xE8
    struct.pack_into("<i", buf, SOCK_HANDLER + 3, CALLEE - SOCK_HANDLER - 7)

    digest = _section_digest(bytes(buf), CODE, CODE_SIZE)
    header0 = TABLE_OFF
    buf[header0 + 36 : header0 + 56] = digest
    return bytes(buf)


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source = self.work / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())

    def test_read_discovers_all_four_sites(self) -> None:
        result = strength.read_strengths(self.source)
        self.assertEqual(result["schema"], strength.READ_SCHEMA)
        self.assertEqual(
            {slot: round(value, 6)
             for slot, value in result["strengths"].items()},
            {"jersey": 0.1, "pants": 0.3, "sleeve": 0.1, "sock": 0.0},
        )
        by_slot = {site["slot"]: site for site in result["sites"]}
        self.assertEqual(by_slot["sleeve"]["shared_with"], "jersey")
        self.assertEqual(by_slot["sock"]["kind"], "push_imm8")
        self.assertFalse(result["sock_editable"])
        self.assertEqual(
            result["callee_offset"], f"0x{CALLEE:x}"
        )

    def test_write_patches_copy_recomputes_digest_and_reads_back(
        self,
    ) -> None:
        target = self.work / "patched.xbe"
        result = strength.write_strengths(
            self.source, target, jersey=0.25, pants=0.5
        )
        self.assertEqual(result["schema"], strength.WRITE_SCHEMA)
        reread = strength.read_strengths(target)
        strengths = {
            slot: round(value, 6)
            for slot, value in reread["strengths"].items()
        }
        self.assertEqual(strengths["jersey"], 0.25)
        self.assertEqual(strengths["sleeve"], 0.25)
        self.assertEqual(strengths["pants"], 0.5)
        self.assertEqual(strengths["sock"], 0.0)

        original = self.source.read_bytes()
        patched = target.read_bytes()
        self.assertEqual(len(original), len(patched))
        self.assertNotEqual(original, patched)
        changed = {
            offset
            for offset, (a, b) in enumerate(zip(original, patched))
            if a != b
        }
        self.assertTrue(changed <= {
            JERSEY_HANDLER + 1 + byte for byte in range(4)
        } | {PANTS_HANDLER + 1 + byte for byte in range(4)}
            | {TABLE_OFF + 36 + byte for byte in range(20)})

    def test_sock_edit_is_refused(self) -> None:
        with self.assertRaisesRegex(strength.BumpStrengthError, "read-only"):
            strength.write_strengths(self.source, self.work / "x.xbe",
                                     sock=0.5)

    def test_conflicting_shared_floats_are_refused(self) -> None:
        with self.assertRaisesRegex(strength.BumpStrengthError, "share one"):
            strength.write_strengths(self.source, self.work / "x.xbe",
                                     jersey=0.2, sleeve=0.7)

    def test_existing_target_is_refused(self) -> None:
        blocker = self.work / "blocker.xbe"
        blocker.write_bytes(b"\x00" * 16)
        with self.assertRaisesRegex(strength.BumpStrengthError,
                                    "already exists"):
            strength.write_strengths(self.source, blocker, pants=0.5)

    def test_overwrite_replaces_an_existing_target(self) -> None:
        target = self.work / "patched.xbe"
        target.write_bytes(b"\x00" * 16)
        result = strength.write_strengths(
            self.source, target, pants=0.5, overwrite=True
        )
        reread = strength.read_strengths(target)
        self.assertAlmostEqual(reread["strengths"]["pants"], 0.5, places=6)
        self.assertEqual(result["schema"], strength.WRITE_SCHEMA)

    def test_no_change_request_is_refused(self) -> None:
        with self.assertRaisesRegex(strength.BumpStrengthError,
                                    "no strength changes"):
            strength.write_strengths(self.source, self.work / "x.xbe")

    def test_identical_value_request_is_refused(self) -> None:
        with self.assertRaisesRegex(strength.BumpStrengthError,
                                    "already equals"):
            strength.write_strengths(self.source, self.work / "x.xbe",
                                     pants=0.30000001192092896)

    def test_stored_stale_digest_is_refused(self) -> None:
        drifted = bytearray(self.source.read_bytes())
        drifted[TABLE_OFF + 36] ^= 0xFF
        drifted_path = self.work / "drifted.xbe"
        drifted_path.write_bytes(bytes(drifted))
        with self.assertRaisesRegex(strength.BumpStrengthError,
                                    "already stale"):
            strength.write_strengths(drifted_path, self.work / "x.xbe",
                                     pants=0.5)

    def test_missing_switch_pattern_is_refused(self) -> None:
        gutted = bytearray(self.source.read_bytes())
        gutted[SWITCH : SWITCH + len(strength.SWITCH_PATTERN)] = bytes(
            len(strength.SWITCH_PATTERN)
        )
        gutted_path = self.work / "gutted.xbe"
        gutted_path.write_bytes(bytes(gutted))
        with self.assertRaisesRegex(strength.BumpStrengthError,
                                    "lacks the bump-strength switch"):
            strength.read_strengths(gutted_path)


@unittest.skipUnless(RETAIL_XBE.exists(), "retail extracted XBE not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_strengths_match_the_a10_census(self) -> None:
        result = strength.read_strengths(RETAIL_XBE)
        self.assertTrue(result["matches_retail_sha256"])
        strengths = result["strengths"]
        self.assertAlmostEqual(strengths["jersey"], 0.1, places=6)
        self.assertAlmostEqual(strengths["pants"], 0.3, places=6)
        self.assertAlmostEqual(strengths["sleeve"], 0.1, places=6)
        self.assertEqual(strengths["sock"], 0.0)


if __name__ == "__main__":
    unittest.main()
