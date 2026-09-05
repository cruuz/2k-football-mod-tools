"""Retail-free contract tests for the unified scorebug adapter."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import zlib

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core.nfl2k5_scorebug_unified_adapter import (
    SCOREBUG_ADAPTER_SCHEMA,
    SCOREBUG_IMPORT_SCHEMA,
    SCOREBUG_REPORT,
    SCOREBUG_REPORT_SHA256,
    SCOREBUG_TARGET_DIMENSIONS,
    SCOREBUG_TARGETS,
    ScorebugUnifiedAdapterError,
    build_scorebug_texture_import,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _synthetic_png(width: int, height: int) -> bytes:
    """Create an RGBA PNG from generated pixels, never from game artwork."""

    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            len(payload).to_bytes(4, "big")
            + body
            + (zlib.crc32(body) & 0xFFFFFFFF).to_bytes(4, "big")
        )

    header = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes((8, 6, 0, 0, 0))
    )
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(((x * 17) & 0xFF, (y * 29) & 0xFF, 0xA5, 0xFF))
    return signature + chunk(b"IHDR", header) + chunk(
        b"IDAT", zlib.compress(bytes(rows), 9)
    ) + chunk(b"IEND", b"")


def _synthetic_import_result(target_name: str) -> tuple[bytes, bytes, dict]:
    width, height = SCOREBUG_TARGET_DIMENSIONS[target_name]
    replacement = bytes((index * 37 + 11) & 0xFF for index in range(96))
    preview = _synthetic_png(width, height)
    retail = bytes(96)
    target = {
        "name": target_name,
        "width": width,
        "height": height,
        "pack_path": "synthetic/pack0",
        "pack_size": 4096,
        "pack_sha256": _sha256(b"synthetic pack metadata"),
        "pack_offset": 128,
        "xiso_pack_sector": 3,
        "xiso_pack_byte_offset": 3 * 2048,
        "xiso_absolute_span_offset": 3 * 2048 + 128,
        "span_size": len(replacement),
        "span_sha256": _sha256(retail),
    }
    report = {
        "schema": SCOREBUG_IMPORT_SCHEMA,
        "target": target,
        "input_png": {
            "width": width,
            "height": height,
            "sha256": _sha256(preview),
        },
        "rebuild": {
            "span_size": len(replacement),
            "span_sha256": _sha256(replacement),
            "changed_byte_count": len(replacement),
            "changed_runs": [[0, len(replacement) - 1]],
        },
        "preview": {
            "file_name": "preview.png",
            "sha256": _sha256(preview),
            "width": width,
            "height": height,
        },
        "claims": {
            "fixed_span_only": True,
            "originals_modified": False,
            "xiso_created": False,
        },
    }
    return replacement, preview, report


class ScorebugUnifiedAdapterTests(unittest.TestCase):
    def test_all_targets_emit_the_exact_unified_five_value_contract(self) -> None:
        for target_name in SCOREBUG_TARGETS:
            with self.subTest(target=target_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                png = root / f"{target_name}.png"
                png.write_bytes(_synthetic_png(*SCOREBUG_TARGET_DIMENSIONS[target_name]))
                expected = _synthetic_import_result(target_name)
                raw_report_snapshot = copy.deepcopy(expected[2])
                calls: list[tuple[Path, Path, str, Path]] = []

                def importer(index: Path, audit: Path, target: str, source: Path):
                    calls.append((index, audit, target, source))
                    return expected

                result = build_scorebug_texture_import(
                    root / "private-pack0",
                    root / "retail-free-audit.json",
                    {"kind": "scorebug_texture", "target": target_name, "png": png},
                    importer=importer,
                )
                replacement, previews, report, selector, target = result
                self.assertEqual(
                    calls,
                    [(root / "private-pack0", root / "retail-free-audit.json",
                      target_name, png)],
                )
                self.assertEqual(replacement, expected[0])
                self.assertEqual(previews, [("preview.png", expected[1])])
                self.assertEqual(selector, target_name)
                self.assertEqual(target["selector"], target_name)
                self.assertEqual(target["xiso_pack_path"], "synthetic/pack0")
                self.assertEqual(target["xiso_pack_size"], 4096)
                self.assertEqual(
                    target["xiso_pack_sha256"], target["pack_sha256"]
                )
                self.assertEqual(report["target"], target)
                self.assertEqual(
                    report["unified_adapter"]["schema"], SCOREBUG_ADAPTER_SCHEMA
                )
                self.assertFalse(
                    report["unified_adapter"]["retail_bytes_embedded"]
                )
                self.assertEqual(expected[2], raw_report_snapshot)

    def test_edit_is_strictly_logical_and_offset_free(self) -> None:
        valid = {
            "kind": "scorebug_texture",
            "target": "score_buga",
            "png": "generated.png",
        }
        invalid = (
            {**valid, "kind": "team_select"},
            {**valid, "target": "arbitrary_texture"},
            {**valid, "png": ""},
            {**valid, "pack_offset": 1234},
        )
        for edit in invalid:
            with self.subTest(edit=edit), self.assertRaises(
                ScorebugUnifiedAdapterError
            ):
                build_scorebug_texture_import(
                    Path("index"), Path("audit"), edit,
                    importer=lambda *_args: _synthetic_import_result("score_buga"),
                )

    def test_importer_target_pack_aliases_and_arithmetic_fail_closed(self) -> None:
        edit = {
            "kind": "scorebug_texture",
            "target": "score_buga",
            "png": "generated.png",
        }
        for field, value in (
            ("name", "shield_espn"),
            ("pack_sha256", "not-a-hash"),
            ("xiso_absolute_span_offset", 7),
            ("span_size", 95),
        ):
            replacement, preview, report = _synthetic_import_result("score_buga")
            report["target"][field] = value
            with self.subTest(field=field), self.assertRaises(
                ScorebugUnifiedAdapterError
            ):
                build_scorebug_texture_import(
                    Path("index"), Path("audit"), edit,
                    importer=lambda *_args, value=(replacement, preview, report): value,
                )

    def test_replacement_preview_and_changed_run_proofs_fail_closed(self) -> None:
        edit = {
            "kind": "scorebug_texture",
            "target": "score_buga",
            "png": "generated.png",
        }
        mutations = (
            lambda report: report["rebuild"].update({"span_sha256": "0" * 64}),
            lambda report: report["rebuild"].update({"changed_runs": [[0, 8], [8, 9]]}),
            lambda report: report["preview"].update({"sha256": "0" * 64}),
            lambda report: report["claims"].update({"fixed_span_only": False}),
        )
        for mutate in mutations:
            replacement, preview, report = _synthetic_import_result("score_buga")
            mutate(report)
            with self.subTest(mutation=mutate), self.assertRaises(
                ScorebugUnifiedAdapterError
            ):
                build_scorebug_texture_import(
                    Path("index"), Path("audit"), edit,
                    importer=lambda *_args, value=(replacement, preview, report): value,
                )

    def test_public_report_dependency_is_metadata_and_matches_typed_importer(self) -> None:
        self.assertEqual(SCOREBUG_REPORT.name, "scorebug_presentation_audit.json")
        self.assertEqual(len(SCOREBUG_REPORT_SHA256), 64)
        self.assertEqual(SCOREBUG_TARGETS, ("score_buga", "shield_espn", "digital_font"))


if __name__ == "__main__":
    unittest.main()
