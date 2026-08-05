"""Retail-free boundaries for PCSX2-to-Xbox replacement-pack mapping."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402
from nfl_txtr import write_png  # noqa: E402


class Ps2ReplacementPackAuditTests(unittest.TestCase):
    def test_friendly_pngs_are_inventoried_but_not_fabricated_into_xbox_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PCSX2" / "textures" / audit.SERIAL / "replacements"
            source.mkdir(parents=True)
            payload = bytes((1, 2, 3, 255)) * (8 * 8)
            write_png(source / "Friendly Player.png", 8, 8, payload)
            report = audit.audit(root)
        self.assertFalse(report["xbox_mapping_ready"])
        self.assertEqual(report["summary"]["png_count"], 1)
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"], 0)
        self.assertIn("no canonical PCSX2", " ".join(report["blocking_reasons"]))
        self.assertIn("no source-owned", " ".join(report["blocking_reasons"]))

    def test_exact_duplicate_payloads_are_grouped_without_deleting_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = bytes((4, 5, 6, 255)) * (4 * 4)
            for name in ("one.png", "two.png"):
                write_png(root / name, 4, 4, payload)
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in root.iterdir()}
            report = audit.audit(root)
            after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(report["summary"]["unique_png_payload_count"], 1)
        self.assertEqual(len(report["duplicate_payload_groups"]), 1)
        self.assertEqual(len(report["duplicate_payload_groups"][0]["paths"]), 2)

    def test_canonical_hash_and_explicit_manifest_can_cross_the_identity_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "0123456789abcdef-fedcba9876543210-00006653.png"
            write_png(png, 4, 4, bytes((9, 8, 7, 255)) * (4 * 4))
            (root / audit.MAPPING_MANIFEST).write_text(json.dumps({
                "schema": audit.MAPPING_SCHEMA,
                "entries": [{
                    "pcsx2_png": png.name,
                    "xbox_asset_id": "nfl2k5.live-face.0001.f",
                }],
            }), encoding="utf-8")
            report = audit.audit(root)
        self.assertTrue(report["xbox_mapping_ready"])
        self.assertEqual(report["blocking_reasons"], [])
        self.assertEqual(report["summary"]["mapping_entry_count"], 1)

    def test_links_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.png"
            write_png(target, 4, 4, bytes(4 * 4 * 4))
            (root / "linked.png").symlink_to(target)
            with self.assertRaisesRegex(audit.PackAuditError, "must not contain links"):
                audit.audit(root)


@unittest.skipUnless(
    Path("/home/noah/Downloads/NFL2K27").is_dir(),
    "local NFL2K27 report source is absent",
)
class LocalPackWitnessTests(unittest.TestCase):
    def test_the_supplied_tree_is_an_incomplete_duplicate_only_skeleton(self) -> None:
        report = audit.audit(Path("/home/noah/Downloads/NFL2K27"))
        self.assertEqual(report["summary"]["file_count"], 12)
        self.assertEqual(report["summary"]["png_count"], 12)
        self.assertEqual(report["summary"]["unique_png_payload_count"], 4)
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"], 0)
        self.assertFalse(report["mapping_manifest"]["present"])
        self.assertFalse(report["xbox_mapping_ready"])


if __name__ == "__main__":
    unittest.main()
