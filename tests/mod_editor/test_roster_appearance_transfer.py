"""Real XISO transport proof with entirely synthetic named native resources."""
from __future__ import annotations

import copy
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_appearance_transfer as appearance
from tests.nfl2k5_xiso_fixture import SyntheticXiso
from test_nfl2k5_roster_records import synthetic_body, synthetic_resource
from test_roster_save_to_disc import signed


def texture(name, marker):
    body = bytearray(136)
    body[12:16] = b"TXTR"
    struct.pack_into("<II", body, 16, 17, 25)
    raw = name.encode("utf-16-le") + b"\0\0"
    body[32:32 + len(raw)] = raw
    struct.pack_into("<5I", body, 48, 0, 0, 0x02210C29, 0, 0x80000000)
    body[128:] = bytes([marker]) * 8
    return struct.pack("<4s7I", b"TXTR", len(body), 128, 8, 0, 0, 0, 0) + body


def shape(face):
    body = bytearray(64)
    body[12:16] = b"SHAP"
    body[32:42] = ("s" + face).encode("utf-16-le")
    return struct.pack("<4s7I", b"SHAP", 64, 64, 0, 0, 0, 0, 0) + body


def fixture(directory, marker):
    doc = rr.load_body(synthetic_body())
    for p in doc.players:
        p.record.set("photo_id", 1501)
    entries = [(100 + i, b"") for i in range(appearance.FACE_SHAPES_OUTER + 2)]
    for i in range(5):
        entries[i] = (100 + i, b"neighbor" * 8)
    entries[5] = (105, synthetic_resource(doc.to_body()))
    catalog = {}
    for number, family in enumerate(("f", "h", "n", "s", "portrait"), 6):
        selector = f"1501:{family}" if family != "portrait" else "portrait:1501"
        name = family + "1501" if family != "portrait" else "1501"
        raw = shape("1501") if family == "s" else texture(name, marker)
        entries[number] = (100 + number, raw)
        catalog[selector] = {"kind": "SHAP" if family == "s" else "TXTR", "face_id": "1501",
                             "resource_name": name, "outer_index": number, "outer_id": hex(100 + number),
                             "outer_size": len(raw), "chunk_offset": 0, "span_size": len(raw),
                             "system_bytes": 128, "video_bytes": 8, "packed_format": "0x02210C29"}
    table = bytearray(624 * 512)
    for i, face in enumerate([f"{i:04d}" for i in range(623)] + ["1501"]):
        raw = shape(face)
        table[i * 512:i * 512 + len(raw)] = raw
    entries[appearance.FACE_SHAPES_OUTER] = (0x52057D0A, bytes(table))
    catalog["1501:s_global"] = dict(catalog["1501:s"], outer_index=appearance.FACE_SHAPES_OUTER)
    return SyntheticXiso(directory, entries, pack_sizes=(0x200000,), pack_sectors=(64,)), catalog


class AppearanceTransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.source, self.catalog = fixture(root / "source", 0xA5)
        self.target, _ = fixture(root / "target", 0x3C)
        self.patch = patch.object(appearance, "_catalog", return_value=self.catalog)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temporary.cleanup()

    def exported(self):
        source = rr.load_image(self.source.path)
        player = source.players[0]
        source.set_name(player, "first", "Lamar")
        source.set_name(player, "last", "Jackson")
        for key, value in {"skin_low": 0, "skin_high": 2, "face": 5, "body": 2, "dreads": 1}.items():
            player.record.set(key, value)
        return appearance.complete_document(self.source.path, source)

    def test_transfer_preserves_lamar_record_and_selected_art_then_is_idempotent(self):
        edits = self.exported()
        source_before = self.source.path.read_bytes()
        target_before = self.target.path.read_bytes()
        receipt = rr.apply(self.target.path, edits, scheme="retail")
        loaded = rr.load_image(self.target.path)
        p = loaded.players[0]
        self.assertEqual((p.first, p.last, p.record.skin, p.record.get("face"),
                          p.record.get("body"), p.record.get("dreads")), ("Lamar", "Jackson", 4, 5, 2, 1))
        self.assertEqual(self.source.path.read_bytes(), source_before)
        self.assertEqual(len(receipt["appearance_resources"]), 4)
        spans = [(self.target.virtual_to_image(self.target.entry_offsets[5]),
                  self.target.virtual_to_image(self.target.entry_offsets[5]) + rr.RESOURCE_SIZE)]
        for row in receipt["appearance_resources"]:
            start = self.target.virtual_to_image(row["virtual_offset"])
            spans.append((start, start + row["size"]))
        after = self.target.path.read_bytes()
        self.assertTrue(all(any(a <= i < b for a, b in spans) for i, (x, y) in
                            enumerate(zip(target_before, after)) if x != y))
        with rr._outer_image()(self.target.path) as archive:
            self.assertEqual(appearance.prepare_writes(archive, edits["appearance_assets"], loaded.to_body()), [])
        self.assertTrue(rr.apply(self.target.path, edits)["already_applied"])
        self.assertEqual(self.target.path.read_bytes(), after)

    def test_corrupt_missing_duplicate_or_unknown_resource_refuses_before_any_write(self):
        edits = self.exported()
        bad_bundles = []
        corrupt = copy.deepcopy(edits["appearance_assets"])
        corrupt["resources"][0]["sha256"] = "0" * 64
        bad_bundles.append(corrupt)
        partial = copy.deepcopy(edits["appearance_assets"])
        partial["resources"].pop(0)
        bad_bundles.append(partial)
        duplicate = copy.deepcopy(edits["appearance_assets"])
        duplicate["resources"].append(duplicate["resources"][0])
        bad_bundles.append(duplicate)
        unknown = copy.deepcopy(edits["appearance_assets"])
        unknown["resources"][0]["selector"] = "arbitrary:offset"
        bad_bundles.append(unknown)
        missing_portrait = copy.deepcopy(edits["appearance_assets"])
        missing_portrait["resources"] = [r for r in missing_portrait["resources"] if r["selector"] != "portrait:1501"]
        bad_bundles.append(missing_portrait)
        before = self.target.path.read_bytes()
        for bundle in bad_bundles:
            with self.subTest(resources=len(bundle["resources"])):
                edits["appearance_assets"] = bundle
                with self.assertRaises(rr.RosterRecordError):
                    rr.apply(self.target.path, edits)
                self.assertEqual(self.target.path.read_bytes(), before)

    def test_changed_destination_shape_identity_refuses_before_roster_write(self):
        edits = self.exported()
        with rr._outer_image()(self.target.path, writable=True) as archive:
            entry = archive.entries[appearance.FACE_SHAPES_OUTER]
            archive.write(entry.virtual_offset, b"FAIL")
        before = self.target.path.read_bytes()
        with self.assertRaisesRegex(rr.RosterRecordError, "FaceShapes slot"):
            rr.apply(self.target.path, edits)
        self.assertEqual(self.target.path.read_bytes(), before)

    def test_export_is_deterministic_and_legacy_scalar_only_documents_still_work(self):
        self.assertEqual(self.exported(), self.exported())
        doc = rr.load_image(self.target.path)
        doc.players[0].record.set("speed", 91)
        rr.apply(self.target.path, rr.edits_document(doc))
        self.assertEqual(rr.load_image(self.target.path).players[0].record.get("speed"), 91)

    def test_native_fallback_uses_low_three_skin_and_face_bits(self):
        doc = rr.load_body(synthetic_body())
        for player in doc.players:
            player.record.set("photo_id", 22000)
            player.record.skin = 16
            player.record.set("face", 5)
        catalog = {f"9006:{family}": {} for family in ("f", "h", "n", "s", "s_global")}
        with patch.object(appearance, "_catalog", return_value=catalog):
            self.assertEqual(appearance._selected(doc), set(catalog))

    def test_signed_save_export_can_attach_art_from_its_source_disc(self):
        from mod_editor.core import nfl2k5_roster_save_to_disc as importer
        source = signed(rr.load_image(self.source.path).to_body())
        target = rr.load_image(self.target.path)
        result = importer.compare(target, source, replace_roster=True, appearance_source=self.source.path)
        self.assertTrue(result.receipt["appearance_source_supplied"])
        self.assertIn("Faces and portraits are included", result.summary)
        self.assertEqual(len(result.edits["appearance_assets"]["resources"]), 6)
        rr.apply(self.target.path, result.edits)
        with self.assertRaisesRegex(importer.SaveToDiscError, "complete roster replacement"):
            importer.compare(target, source, appearance_source=self.source.path)


if __name__ == "__main__":
    unittest.main()
