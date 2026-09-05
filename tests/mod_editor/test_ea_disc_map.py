"""The read-only disc mapper: schema reader, container mapping and rendering on synthetic bytes."""

from __future__ import annotations

from pathlib import Path
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import ea_disc_map as mapper  # noqa: E402


class TdbSchemaTests(unittest.TestCase):
    def test_tables_fields_and_preamble(self) -> None:
        db = mapper._synthetic_tdb([("TEAM", [("TGID", 3, 8), ("TDNA", 0, 32)], 3)])
        schema = mapper.tdb_schema(db)
        self.assertEqual([t["name"] for t in schema["tables"]], ["TEAM"])
        self.assertEqual(schema["tables"][0]["fields"][0], {"name": "TGID", "type": "uint", "bit_offset": 0, "bits": 8})
        self.assertEqual(mapper.tdb_schema(b"\x02\x00\x00\x00" + db)["preamble"], 4)
        self.assertEqual(mapper.schema_signature(schema), mapper.schema_signature(mapper.tdb_schema(db)))

    def test_not_a_database_is_a_sentence(self) -> None:
        with self.assertRaises(mapper.MapError):
            mapper.tdb_schema(b"TERF" + bytes(64))

    def test_big_endian_is_reported_not_parsed(self) -> None:
        head = bytearray(24); head[:2] = b"DB"; struct.pack_into(">I", head, 0x10, 3)
        self.assertEqual(mapper.tdb_schema(bytes(head))["endian"], "big")


class SelftestTests(unittest.TestCase):
    def test_the_selftest_passes_as_a_subprocess(self) -> None:
        completed = subprocess.run([sys.executable, str(ROOT / "tools" / "ea_disc_map.py"), "--selftest"],
                                   capture_output=True, text=True, timeout=300, cwd=str(ROOT))
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("EA_DISC_MAP_SELFTEST_PASS", completed.stdout)

    def test_magic_kinds(self) -> None:
        self.assertEqual(mapper.magic_kind(b"TERF@\x00\x00\x00"), "TERF")
        self.assertEqual(mapper.magic_kind(b"DB\x00\x08" + bytes(12)), "TDB")
        self.assertTrue(mapper.magic_kind(b"\x00\x01\x02\x03").startswith("other:"))


if __name__ == "__main__":
    unittest.main()
