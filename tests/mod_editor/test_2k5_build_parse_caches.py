"""A multi-edit build pays each image-constant parse exactly once.

The 2K5 build backend prepares every edit against the same canonical inputs:
the extracted ``vc_53450030`` index volume, the ~55 MB chunk inventory, the
hash-pinned compatibility reports, and the logical-name table.  Before this
work each edit re-read and re-parsed all of them (and the helmet/face/digit/
field-art/portrait importers additionally re-hashed the whole 193 MB index
volume per edit), so N edits cost N full parses.  Every one of those
structures is now memoized behind a file-identity key (path, device, inode,
size, mtime): the first edit parses, the rest reuse, and any rewrite of the
input moves the identity and re-parses.  These tests prove the reuse and the
invalidation with call counters -- never wall clocks.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl_jersey_tset_targets as jersey_targets  # noqa: E402
import nfl_outer  # noqa: E402
import nfl_pants_tset_targets as pants_targets  # noqa: E402
import nfl_sleeve_tset_targets as sleeve_targets  # noqa: E402
import nfl_uniform_inventory  # noqa: E402


def _write_archive(directory: Path) -> Path:
    """One synthetic vc_53450030-style archive: index '0' plus pack '1'."""

    payload = bytes(range(256)) * 16  # two full 0x800 blocks
    header = struct.pack("<III", 1, 0, 2)
    slots = [0] * nfl_outer.PACK_SLOT_COUNT
    slots[0] = 1
    slots[1] = len(payload) // 0x800
    entry = struct.pack("<III", 0x0ABCDEF0, len(payload), 1)
    index = header + struct.pack(f"<{nfl_outer.PACK_SLOT_COUNT}I", *slots) + entry
    index += bytes(0x800 - len(index))
    (directory / "0").write_bytes(index)
    (directory / "1").write_bytes(payload)
    return directory / "0"


class _CallCounter:
    """Counts calls while delegating to the wrapped callable."""

    def __init__(self, original):
        self.calls = 0
        self._original = original

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._original(*args, **kwargs)


class ParseArchiveCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.archive_dir = self.work / "vc_53450030"
        self.archive_dir.mkdir()
        self.index_path = _write_archive(self.archive_dir)
        nfl_outer.clear_parse_cache()
        self.addCleanup(nfl_outer.clear_parse_cache)

    def test_many_reads_parse_the_archive_once(self) -> None:
        counter = _CallCounter(nfl_outer._parse_archive_uncached)
        original = nfl_outer._parse_archive_uncached
        nfl_outer._parse_archive_uncached = counter
        self.addCleanup(setattr, nfl_outer, "_parse_archive_uncached", original)
        first = nfl_outer.parse_archive(self.index_path)
        second = nfl_outer.parse_archive(self.index_path)
        third = nfl_outer.parse_archive(self.index_path)
        self.assertEqual(counter.calls, 1)
        self.assertIs(first, second)
        self.assertIs(second, third)
        self.assertEqual(len(first.entries), 1)

    def test_touching_the_index_invalidates_the_cache(self) -> None:
        nfl_outer.parse_archive(self.index_path)
        future = self.index_path.stat().st_mtime_ns + 10_000_000_000
        os.utime(self.index_path, ns=(future, future))
        counter = _CallCounter(nfl_outer._parse_archive_uncached)
        original = nfl_outer._parse_archive_uncached
        nfl_outer._parse_archive_uncached = counter
        self.addCleanup(setattr, nfl_outer, "_parse_archive_uncached", original)
        nfl_outer.parse_archive(self.index_path)
        self.assertEqual(counter.calls, 1)

    def test_clearing_the_cache_forces_a_reparse(self) -> None:
        first = nfl_outer.parse_archive(self.index_path)
        nfl_outer.clear_parse_cache()
        second = nfl_outer.parse_archive(self.index_path)
        self.assertIsNot(first, second)
        self.assertEqual(first.entries, second.entries)


class LogicalNameCacheTests(unittest.TestCase):
    def test_the_candidate_table_is_built_once_and_shared(self) -> None:
        first = nfl_uniform_inventory.logical_name_candidates()
        second = nfl_uniform_inventory.logical_name_candidates()
        self.assertIs(first, second)
        self.assertEqual(len(first), 20_000)


class InventoryCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.inventory_path = self.work / "inventory.json"
        self.document = {
            "schema": nfl_uniform_inventory.INVENTORY_SCHEMA,
            "chunks": [
                {"outer_index": 5, "chunk_index": 2, "kind": "TSET"},
                {"outer_index": 7, "chunk_index": 0, "kind": "TXTR"},
                {"outer_index": 7, "chunk_index": 0, "kind": "TXTR"},
                {"outer_index": 9, "chunk_index": 1, "kind": "NAME"},
            ],
        }
        self.inventory_path.write_bytes(
            (json.dumps(self.document) + "\n").encode("utf-8")
        )
        nfl_uniform_inventory.clear_inventory_cache()
        self.addCleanup(nfl_uniform_inventory.clear_inventory_cache)

    def test_repeated_loads_parse_the_document_once(self) -> None:
        counter = Counter()
        real_loads = nfl_uniform_inventory.json.loads

        def counting_loads(payload, *args, **kwargs):
            counter["loads"] += 1
            return real_loads(payload, *args, **kwargs)

        nfl_uniform_inventory.json.loads = counting_loads
        self.addCleanup(
            setattr, nfl_uniform_inventory.json, "loads", real_loads
        )
        first = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        second = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        self.assertEqual(counter["loads"], 1)
        self.assertIs(first, second)

    def test_row_lookup_matches_the_historical_linear_scan(self) -> None:
        cached_value = nfl_uniform_inventory.load_inventory_document(
            self.inventory_path
        )
        plain_value = json.loads(self.inventory_path.read_bytes())
        for outer, chunk in ((5, 2), (7, 0), (9, 1), (4, 0)):
            expected = [
                row for row in plain_value["chunks"]
                if int(row["outer_index"]) == outer
                and int(row["chunk_index"]) == chunk
            ]
            self.assertEqual(
                nfl_uniform_inventory.inventory_chunk_rows(
                    cached_value, outer, chunk
                ),
                expected,
            )
            self.assertEqual(
                nfl_uniform_inventory.inventory_chunk_rows(
                    plain_value, outer, chunk
                ),
                expected,
            )
        self.assertEqual(
            len(nfl_uniform_inventory.inventory_chunk_rows(cached_value, 7, 0)), 2
        )

    def test_rewriting_the_inventory_invalidates_the_cache(self) -> None:
        first = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        rewritten = dict(self.document)
        rewritten["chunks"] = self.document["chunks"] + [
            {"outer_index": 11, "chunk_index": 3, "kind": "TSET"}
        ]
        self.inventory_path.write_bytes(
            (json.dumps(rewritten) + "\n").encode("utf-8")
        )
        second = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        self.assertIsNot(first, second)
        self.assertEqual(
            len(nfl_uniform_inventory.inventory_chunk_rows(second, 11, 3)), 1
        )

    def test_clearing_the_cache_forces_a_reload(self) -> None:
        first = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        nfl_uniform_inventory.clear_inventory_cache()
        second = nfl_uniform_inventory.load_inventory_document(self.inventory_path)
        self.assertIsNot(first, second)
        self.assertEqual(first, second)

    def test_eviction_drops_the_row_index_side_table(self) -> None:
        paths = []
        for index in range(nfl_uniform_inventory._INVENTORY_CACHE_LIMIT + 1):
            path = self.work / f"inventory_{index}.json"
            path.write_bytes(
                json.dumps(
                    {
                        "schema": nfl_uniform_inventory.INVENTORY_SCHEMA,
                        "chunks": [
                            {"outer_index": index, "chunk_index": 0,
                             "kind": "TSET"}
                        ],
                    }
                ).encode("utf-8")
            )
            paths.append(path)
        values = [
            nfl_uniform_inventory.load_inventory_document(path) for path in paths
        ]
        self.assertEqual(
            len(nfl_uniform_inventory._INVENTORY_CACHE),
            nfl_uniform_inventory._INVENTORY_CACHE_LIMIT,
        )
        # The evicted first document falls back to the linear scan and still
        # answers correctly.
        self.assertEqual(
            nfl_uniform_inventory.inventory_chunk_rows(values[0], 0, 0),
            [{"outer_index": 0, "chunk_index": 0, "kind": "TSET"}],
        )

    def test_a_malformed_document_keeps_the_legacy_scan_exceptions(self) -> None:
        absent = self.work / "absent_chunks.json"
        absent.write_bytes(json.dumps({"schema": "whatever"}).encode("utf-8"))
        value = nfl_uniform_inventory.load_inventory_document(absent)
        with self.assertRaises(KeyError):
            nfl_uniform_inventory.inventory_chunk_rows(value, 1, 0)
        not_a_list = self.work / "chunks_not_a_list.json"
        not_a_list.write_bytes(
            json.dumps({"schema": "whatever", "chunks": 3}).encode("utf-8")
        )
        value = nfl_uniform_inventory.load_inventory_document(not_a_list)
        with self.assertRaises(TypeError):
            nfl_uniform_inventory.inventory_chunk_rows(value, 1, 0)
        bad_row = self.work / "bad_row.json"
        bad_row.write_bytes(
            json.dumps(
                {"schema": "whatever",
                 "chunks": [{"outer_index": None, "chunk_index": 0}]}
            ).encode("utf-8")
        )
        value = nfl_uniform_inventory.load_inventory_document(bad_row)
        with self.assertRaises(TypeError):
            nfl_uniform_inventory.inventory_chunk_rows(value, 1, 0)


class CompatibilityReportCacheTests(unittest.TestCase):
    """Jersey/sleeve/pants targets memoize their validated report.

    Each module pins a different summary/layout conjunction, so the cache is
    exercised on a private copy of the real hash-pinned report: validation
    stays exactly as strict as production, and the copy can be touched and
    rewritten freely.  Where the report is absent (a fresh checkout carries
    none of the gitignored ``reports/assets``), the behavior is untestable
    and the test says so instead of pretending.
    """

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)

    def _check_module(self, module) -> None:
        source = Path(module.DEFAULT_REPORT)
        if not source.is_file():
            raise unittest.SkipTest(f"{source} is not on this machine")
        report_path = self.work / source.name
        report_path.write_bytes(source.read_bytes())
        module.clear_report_cache()
        self.addCleanup(module.clear_report_cache)

        entry_first = module.load_report(report_path)
        entry_second = module.load_report(report_path)
        self.assertIs(entry_first, entry_second)
        self.assertEqual(
            hashlib.sha256(entry_first[2]).hexdigest(), module.REPORT_SHA256
        )

        future = report_path.stat().st_mtime_ns + 10_000_000_000
        os.utime(report_path, ns=(future, future))
        entry_third = module.load_report(report_path)
        self.assertIsNot(entry_second, entry_third)
        self.assertEqual(entry_third[2], entry_first[2])

        module.clear_report_cache()
        entry_fourth = module.load_report(report_path)
        self.assertIsNot(entry_third, entry_fourth)
        self.assertEqual(entry_fourth[1], entry_first[1])

    def test_jersey_report_is_parsed_once_per_identity(self) -> None:
        self._check_module(jersey_targets)

    def test_sleeve_report_is_parsed_once_per_identity(self) -> None:
        self._check_module(sleeve_targets)

    def test_pants_report_is_parsed_once_per_identity(self) -> None:
        self._check_module(pants_targets)


class FileDigestCacheTests(unittest.TestCase):
    """The 193 MB pinned-index hash is memoized per file identity."""

    INDEX_MODULES = []

    @classmethod
    def setUpClass(cls) -> None:
        import nfl_create_team_field_art_png_import as field_import
        import nfl_live_face_texture_png_import as face_import
        import nfl_live_helmet_txtr_png_import as helmet_import
        import nfl_live_numbers_nameplate_png_import as live_art_import
        import nfl_player_portrait_png_import as portrait_import

        cls.INDEX_MODULES = [
            helmet_import, live_art_import, face_import, field_import,
            portrait_import,
        ]

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)

    def test_every_importer_hashes_a_file_once_per_identity(self) -> None:
        for module in self.INDEX_MODULES:
            with self.subTest(module=module.__name__):
                path = self.work / f"{module.__name__}.bin"
                path.write_bytes(bytes(range(256)) * 64)
                module.clear_file_digest_cache()
                self.addCleanup(module.clear_file_digest_cache)
                counter = _CallCounter(module._file_digest_uncached)
                original = module._file_digest_uncached
                module._file_digest_uncached = counter
                try:
                    expected = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(module.file_digest(path), expected)
                    self.assertEqual(module.file_digest(path), expected)
                    self.assertEqual(counter.calls, 1)
                    future = path.stat().st_mtime_ns + 10_000_000_000
                    os.utime(path, ns=(future, future))
                    self.assertEqual(module.file_digest(path), expected)
                    self.assertEqual(counter.calls, 2)
                    module.clear_file_digest_cache()
                    self.assertEqual(module.file_digest(path), expected)
                    self.assertEqual(counter.calls, 3)
                finally:
                    module._file_digest_uncached = original


if __name__ == "__main__":
    unittest.main()
