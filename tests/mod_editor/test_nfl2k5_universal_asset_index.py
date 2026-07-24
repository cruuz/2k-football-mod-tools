from __future__ import annotations

from dataclasses import replace
import gc
import json
from pathlib import Path
import struct
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_universal_asset_index import (
    Nfl2k5UniversalAssetIndex,
)


HEADER_SIZE = 0x0C + 36 * 4


class UniversalAssetIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pack0 = self.root / "0"
        self.inventory = self.root / "inventory.json"
        self.database = self.root / "universal.sqlite3"
        self.payloads = (
            ("TEST", b"fixture!", (7, 8, 9, 10)),
            ("DATA", b"safe", (11, 12, 13, 14)),
        )
        self._write_archive_and_inventory()

    def tearDown(self) -> None:
        # The index opens the SQLite database through short-lived read-only
        # connections; sqlite3.Connection participates in reference cycles, so a
        # connection's file handle is released by cyclic GC rather than the
        # instant its ``with`` block exits.  POSIX happily deletes a file that
        # still has an open handle, but Windows refuses (WinError 32), which
        # wedged this TemporaryDirectory cleanup on the Windows runner.  Forcing
        # a collection first closes any lingering handle deterministically on
        # every platform; on POSIX it is a harmless no-op for behaviour.
        gc.collect()
        self.temporary.cleanup()

    def _write_archive_and_inventory(self) -> None:
        pack = bytearray(4096)
        struct.pack_into("<III", pack, 0, 1, 0, 1)
        struct.pack_into("<36I", pack, 12, 2, *([0] * 35))
        struct.pack_into("<III", pack, HEADER_SIZE, 0x12345678, 2048, 1)
        rows = []
        offset = 0
        for chunk_index, (kind, body, words) in enumerate(self.payloads):
            base = 2048 + offset
            pack[base:base + 4] = kind.encode("ascii")
            struct.pack_into("<IIIII", pack, base + 4, len(body), *words)
            pack[base + 0x18:base + 0x20] = b"\0" * 8
            pack[base + 0x20:base + 0x20 + len(body)] = body
            end = offset + 0x20 + len(body)
            rows.append(
                {
                    "outer_index": 0,
                    "outer_id": "0x12345678",
                    "outer_head": "TEST",
                    "outer_size": 2048,
                    "chunk_index": chunk_index,
                    "chunk_offset": offset,
                    "zero_padding_before": 0,
                    "kind": kind,
                    "stored_size": len(body),
                    "end_offset": end,
                    "word_08": words[0],
                    "word_0c": words[1],
                    "word_10": f"0x{words[2]:08x}",
                    "word_14": words[3],
                }
            )
            offset = end
        self.pack0.write_bytes(pack)
        self.inventory.write_text(
            json.dumps(
                {
                    "schema": "nfl2k5_resource_chunk_inventory/v1",
                    "summary": {"resource_chunk_count": len(rows)},
                    "txtr_not_first": [],
                    "trailing_regions": [],
                    "chunks": rows,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    def _open(self) -> Nfl2k5UniversalAssetIndex:
        return Nfl2k5UniversalAssetIndex(
            self.inventory,
            self.pack0,
            self.database,
            expected_count=2,
        )

    def test_indexes_every_chunk_and_pages_without_retaining_payloads(self) -> None:
        index = self._open()
        self.assertEqual(index.asset_count, 2)
        self.assertEqual(index.kinds(), (("DATA", 1), ("TEST", 1)))
        first = index.query(limit=1)
        second = index.query(offset=1, limit=1)
        self.assertEqual([row.kind for row in first + second], ["TEST", "DATA"])
        self.assertEqual(index.query(kind="DATA")[0].stored_size, 4)
        self.assertEqual(index.query(search="12345678")[0].outer_index, 0)
        self.assertEqual(tuple(index.iter_all(page_size=1)), first + second)
        self.assertTrue(self.database.is_file())

    def test_exports_exact_wrapper_and_body_without_overwrite(self) -> None:
        index = self._open()
        asset = index.query(kind="DATA")[0]
        output = self.root / asset.suggested_filename
        self.assertEqual(index.export_raw(asset, output), output.resolve())
        expected = self.pack0.read_bytes()[
            2048 + asset.chunk_offset:2048 + asset.end_offset
        ]
        self.assertEqual(output.read_bytes(), expected)
        with self.assertRaisesRegex(ValidationError, "already exists"):
            index.export_raw(asset.asset_id, output)

    def test_rejects_forged_record_and_archive_header_drift(self) -> None:
        index = self._open()
        asset = index.query(limit=1)[0]
        with self.assertRaisesRegex(ValidationError, "does not match"):
            index.export_raw(replace(asset, stored_size=asset.stored_size + 1), self.root / "x")
        payload = bytearray(self.pack0.read_bytes())
        payload[2048] = ord("X")
        self.pack0.write_bytes(payload)
        with self.assertRaisesRegex(ValidationError, "header no longer matches"):
            index.export_raw(asset, self.root / "changed.bin")

    def test_rejects_invalid_inventory_extent_and_bad_page_requests(self) -> None:
        document = json.loads(self.inventory.read_text(encoding="utf-8"))
        document["chunks"][0]["end_offset"] += 1
        self.inventory.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "inconsistent resource extent"):
            self._open()

        self._write_archive_and_inventory()
        index = self._open()
        with self.assertRaises(ValidationError):
            index.query(offset=-1)
        with self.assertRaises(ValidationError):
            index.query(limit=0)
        with self.assertRaises(ValidationError):
            index.query(kind="TOO-LONG")

    def test_rejects_symlinked_inventory_and_sidecar(self) -> None:
        linked = self.root / "linked.json"
        linked.symlink_to(self.inventory)
        with self.assertRaisesRegex(ValidationError, "regular file"):
            Nfl2k5UniversalAssetIndex(linked, self.pack0, self.database)

        self.database.symlink_to(self.root / "somewhere")
        with self.assertRaisesRegex(ValidationError, "symbolic link"):
            self._open()


if __name__ == "__main__":
    unittest.main()
