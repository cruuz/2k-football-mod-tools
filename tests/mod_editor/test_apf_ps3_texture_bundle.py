"""Standalone synthetic importer tests and one read-only retail writer gate."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from mod_editor.apf_studio.ps3_texture_bundle import (
    Assignment, BundleError, DestinationSlot, build_plan, canonical_team,
    destination_slots, read_bundle, stage_plan, team_mapping,
    verify_plan,
)
from mod_editor.apf_studio.ps3_texture_codec import decode_dds, decode_gtf, TextureDecodeError

RETAIL = Path(os.environ.get("APF_RETAIL_0A", "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"))


def dds(color=(255, 0, 0, 255), size=(512, 512), compression=None):
    stream = io.BytesIO()
    Image.new("RGBA", size, color).save(stream, "DDS", **({"pixel_format": compression} if compression else {}))
    data = stream.getvalue()
    if compression and data[84:88] != compression.encode():
        # Pillow 10 silently ignores pixel_format when saving DDS. Retain its
        # synthetic container, then use a known constant BC block so these
        # tests actually exercise DXT rather than accidentally testing raw RGBA.
        header = bytearray(data[:128])
        c = ((color[0] >> 3) << 11) | ((color[1] >> 2) << 5) | (color[2] >> 3)
        block = struct.pack("<HHI", c, c, 0)
        if compression == "DXT5":
            block = bytes((color[3], color[3])) + b"\0" * 6 + block
        raw = block * (((size[0] + 3) // 4) * ((size[1] + 3) // 4))
        struct.pack_into("<I", header, 8, 0x81007)
        struct.pack_into("<I", header, 20, len(raw))
        struct.pack_into("<II4s5I", header, 76, 32, 4, compression.encode(), 0, 0, 0, 0, 0)
        data = bytes(header) + raw
    return data


def bundle_files(team="Cincinati Bengals", *, identical=False, manifest=True, kind="logo", hash_value="0x7ba6e2b0"):
    files = {}
    for layer in (0, 1):
        # APFe inner 0 can be l1; sorting numeric prefixes would swap the masks.
        inner = 1 - layer
        folder = f"NFL Logos/{team}/selected_subfile_753_{inner}_123"
        name = f"{inner:03d}_{kind}_l{layer}.dds"
        files[f"{folder}/{name}"] = dds((255, 0, 0, 255) if layer == 0 or identical else (0, 255, 0, 136),
                                      (512, 512) if kind == "logo" else (2048, 512))
        if manifest:
            row = {"entryIndex": 753, "entryHash": hash_value, "subfileName": f"{kind}_l{layer}", "byteLength": 699312, "type": "TXTR"}
            files[f"{folder}/manifest.json"] = json.dumps({"row": row, "files": [name]}).encode()
    return files


def write_folder(root, files):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def slot(kind="logo", hash_value=0x7BA6E2B0, outer=756, writable=True):
    return DestinationSlot(f"{kind}:{outer}", "Americans" if kind == "logo" else "Known endzone", kind, outer, hash_value,
                           (f"apf:outer:{outer}:inner:1", f"apf:outer:{outer}:inner:0"), (1, 0), 30 if kind == "logo" else None, writable)


class CodecTests(unittest.TestCase):
    def test_raw_dds_preserves_rgba(self):
        self.assertEqual(decode_dds(dds((17, 34, 51, 68), (8, 4))).getpixel((0, 0)), (17, 34, 51, 68))

    def test_dxt1_and_dxt5_from_pillow(self):
        for kind in ("DXT1", "DXT5"):
            with self.subTest(kind=kind):
                data = dds((255, 0, 0, 255), (8, 8), kind)
                self.assertEqual(data[84:88], kind.encode())
                image = decode_dds(data)
                self.assertEqual(image.size, (8, 8))
                self.assertEqual(image.getpixel((3, 3)), (255, 0, 0, 255))

    def test_apfe_argb4444_dds(self):
        data = bytearray(dds(size=(4, 4)))
        struct.pack_into("<I", data, 20, 8)
        struct.pack_into("<5I", data, 88, 16, 0xF00, 0xF0, 0xF, 0xF000)
        data[128:] = struct.pack("<H", 0x8123) * 16
        self.assertEqual(decode_dds(bytes(data)).getpixel((0, 0)), (17, 34, 51, 136))

    def test_gtf_declared_offset_not_fixed_128(self):
        for offset in (48, 128):
            raw = bytes.fromhex("ff112233") * 8
            header = bytearray(offset)
            struct.pack_into(">6I", header, 0, 0x01080000, offset + len(raw), 1, 0, offset, len(raw))
            struct.pack_into(">4BI3H2B2I", header, 24, 0xA5, 1, 2, 0, 0xAAE4, 4, 2, 1, 0, 0, 16, 0)
            self.assertEqual(decode_gtf(bytes(header) + raw).getpixel((3, 1)), (17, 34, 51, 255))

    def test_gtf_morton_rectangular_layout(self):
        # 4x2 raw words in Morton order: (0,0),(1,0),(0,1),(1,1), then x2/3.
        order = [0, 1, 4, 5, 2, 3, 6, 7]
        raw = b"".join(struct.pack(">H", 0xF000 | (value << 8)) for value in order)
        header = bytearray(48)
        struct.pack_into(">6I", header, 0, 0x01080000, 64, 1, 0, 48, 16)
        struct.pack_into(">4BI3H2B2I", header, 24, 0x83, 1, 2, 0, 0xAAE4, 4, 2, 1, 0, 0, 8, 0)
        image = decode_gtf(bytes(header) + raw)
        self.assertEqual([p[0] for p in image.getdata()], [i * 17 for i in range(8)])

    def test_truncation_and_oversize_are_rejected(self):
        with self.assertRaises(TextureDecodeError):
            decode_dds(dds()[:140])
        raw = bytearray(dds())
        struct.pack_into("<II", raw, 12, 65535, 65535)
        with self.assertRaises(TextureDecodeError):
            decode_dds(bytes(raw))
        with self.assertRaises(TextureDecodeError):
            decode_gtf(b"\0" * 128)

    def test_dx10_array_is_not_silently_imported_as_one_image(self):
        raw = bytearray(dds(size=(4, 4)))
        struct.pack_into("<I4s", raw, 80, 4, b"DX10")
        data = bytes(raw[:128]) + struct.pack("<5I", 28, 3, 0, 2, 0) + bytes(raw[128:])
        with self.assertRaisesRegex(TextureDecodeError, "arrays"):
            decode_dds(data)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def read(self, files=None):
        write_folder(self.root, bundle_files() if files is None else files)
        return read_bundle(self.root)

    def test_aliases_keep_historical_names(self):
        for alias, expected in (("Cincinati Bengals", "Cincinnati Bengals"), ("Detriot Lions", "Detroit Lions"),
                                ("Philadelia Eagles", "Philadelphia Eagles"), ("San Deigo Chargers", "San Diego Chargers"),
                                ("San Franciso 49ers", "San Francisco 49ers"), ("Phoenix Cardinals", "Phoenix Cardinals")):
            self.assertEqual(canonical_team(alias), expected)
        with self.assertRaises(BundleError):
            canonical_team("Stripe Update 1")

    def test_folder_layout_order_and_receipt(self):
        bundle = self.read()
        pair = bundle.pairs[0]
        self.assertEqual(pair.original_folder, "Cincinati Bengals")
        self.assertEqual(pair.team, "Cincinnati Bengals")
        self.assertEqual([l.layer for l in pair.layers], ["logo_l0", "logo_l1"])
        self.assertEqual(pair.layers[0].image.getpixel((0, 0)), (255, 0, 0, 255))
        receipt = json.loads(json.dumps(bundle.receipt()))
        layer = receipt["pairs"][0]["layers"][0]
        self.assertEqual(len(layer["decoded_pixels_sha256"]), 64)
        self.assertEqual(layer["source_manifest_row"]["entryIndex"], 753)

    def test_zip_matches_folder(self):
        bundle = self.read()
        target = self.root / "bundle.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in bundle_files().items():
                z.writestr(name, data)
        self.assertEqual(read_bundle(target).pairs[0].receipt(), bundle.pairs[0].receipt())

    def test_team_folder_as_input(self):
        self.read()
        self.assertEqual(read_bundle(self.root / "NFL Logos" / "Cincinati Bengals").teams, ("Cincinnati Bengals",))

    def test_identical_and_incomplete_pairs_rejected(self):
        for files in (bundle_files(identical=True), {k: v for k, v in bundle_files().items() if "_1_123" in k}):
            with self.subTest(files=list(files)):
                with tempfile.TemporaryDirectory() as temp:
                    write_folder(Path(temp), files)
                    with self.assertRaisesRegex(BundleError, "No valid"):
                        read_bundle(Path(temp))

    def test_rejected_pair_does_not_hide_valid_team(self):
        files = bundle_files(identical=True)
        files.update(bundle_files("Dallas Cowboys"))
        bundle = self.read(files)
        self.assertEqual(len(bundle.pairs), 1)
        self.assertEqual(len(bundle.rejected_pairs), 1)

    def test_two_alias_folders_cannot_silently_replace_one_pair(self):
        files = bundle_files("Detriot Lions")
        files.update(bundle_files("Detroit Lions"))
        with self.assertRaisesRegex(BundleError, "Aliased team folders"):
            self.read(files)

    def test_manifest_layer_mismatch_and_wrong_size(self):
        files = bundle_files()
        key = next(k for k in files if k.endswith("manifest.json"))
        document = json.loads(files[key]); document["row"]["subfileName"] = "logo_l1"
        files[key] = json.dumps(document).encode()
        with self.assertRaisesRegex(BundleError, "manifest"):
            self.read(files)

    def test_bad_dds_does_not_fall_back_to_gtf(self):
        files = bundle_files()
        key = next(k for k in files if k.endswith(".dds"))
        files[key] = b"bad DDS"
        files[key[:-4] + ".gtf"] = b"bad GTF"
        with self.assertRaisesRegex(BundleError, "DDS"):
            self.read(files)

    def test_gtf_fallback_only_when_dds_missing(self):
        files = bundle_files(manifest=False)
        output = {}
        for name in files:
            layer = 0 if "logo_l0" in name else 1
            raw = dds((255, 0, 0, 255) if layer == 0 else (0, 255, 0, 255), compression="DXT1")[128:]
            header = bytearray(48)
            struct.pack_into(">6I", header, 0, 0x01080000, 48 + len(raw), 1, 0, 48, len(raw))
            struct.pack_into(">4BI3H2B2I", header, 24, 0x86, 1, 2, 0, 0xAAE4, 512, 512, 1, 0, 0, 1024, 0)
            output[name[:-4] + ".gtf"] = bytes(header) + raw
        bundle = self.read(output)
        self.assertEqual(bundle.pairs[0].layers[0].image.getpixel((0, 0)), (255, 0, 0, 255))

    def test_wrong_layer_dimensions_refused(self):
        files = bundle_files()
        name = next(n for n in files if n.endswith(".dds"))
        files[name] = dds(size=(128, 128))
        with self.assertRaisesRegex(BundleError, "expected"):
            self.read(files)

    def test_reviewed_pixel_mutation_refused(self):
        plan = build_plan(self.read(), [slot()])
        plan.items[0].image.putpixel((0, 0), (17, 34, 51, 68))
        with self.assertRaisesRegex(BundleError, "changed after review"):
            verify_plan(plan)

    def test_decoded_memory_budget_applies_to_compressed_images(self):
        files = bundle_files()
        for name in list(files):
            if name.endswith(".dds"):
                files[name] = dds((255, 0, 0, 255) if "logo_l0" in name else (0, 255, 0, 255), compression="DXT1")
        with mock.patch("mod_editor.apf_studio.ps3_texture_bundle.MAX_BUNDLE_BYTES", 1536 * 1024):
            with self.assertRaisesRegex(BundleError, "decoded RGBA"):
                self.read(files)

    def test_traversal_and_case_collision_zip(self):
        for entries in (("../escape.dds",), ("A.dds", "a.dds")):
            target = self.root / "bad.zip"
            with zipfile.ZipFile(target, "w") as z:
                for name in entries:
                    z.writestr(name, b"bad")
            with self.assertRaises(BundleError):
                read_bundle(target)

    def test_hash_mapping_uses_semantic_names(self):
        plan = build_plan(self.read(), [slot()])
        self.assertEqual(plan.items[0].destination_asset_id, "apf:outer:756:inner:1")
        self.assertEqual(plan.items[0].layer, "logo_l0")
        self.assertEqual(plan.receipt["assignments"][0]["mapping_method"], "entry_hash_and_layer_name")

    def test_missing_hash_requires_chosen_destination(self):
        bundle = self.read(bundle_files(manifest=False))
        with self.assertRaisesRegex(BundleError, "Choose a destination"):
            build_plan(bundle, [slot()])
        plan = build_plan(bundle, [slot()], [Assignment(bundle.pairs[0].pair_id, slot().slot_id)])
        self.assertEqual(plan.items[0].receipt["mapping_method"], "chosen_destination_and_layer_name")

    def test_mapping_table_names_and_collisions(self):
        files = bundle_files(); files.update(bundle_files("Dallas Cowboys"))
        bundle = self.read(files)
        table = [{"team": p.team, "kind": "logo", "destination": "Americans"} for p in bundle.pairs]
        with self.assertRaisesRegex(BundleError, "repeats"):
            team_mapping(bundle, [slot()], table)
        assignments = team_mapping(bundle, [slot()], table[:1])
        self.assertEqual(len(build_plan(bundle, [slot()], assignments).items), 2)

    def test_unwritable_and_wrong_kind_refused(self):
        bundle = self.read()
        for target in (slot(writable=False), slot(kind="endzone")):
            with self.assertRaises(BundleError):
                build_plan(bundle, [target], [Assignment(bundle.pairs[0].pair_id, target.slot_id)])

    def test_duplicate_variants_need_choice(self):
        files = bundle_files()
        files.update({k.replace("/selected_", "/Alternate/selected_"): v for k, v in bundle_files().items()})
        bundle = self.read(files)
        with self.assertRaisesRegex(BundleError, "repeats"):
            build_plan(bundle, [slot()])
        with self.assertRaisesRegex(BundleError, "Ambiguous"):
            team_mapping(bundle, [slot()], [{"team": "Cincinnati Bengals", "kind": "logo", "destination": "Americans"}])

    def test_stage_failure_rolls_back_previous_operations(self):
        bundle = self.read(bundle_files(kind="endzone"))
        target = slot(kind="endzone")
        plan = build_plan(bundle, [target])
        session = mock.Mock(modifications=())
        session.replace_field_art.side_effect = [object(), ValueError("stage failure")]
        with mock.patch("mod_editor.apf_studio.ps3_texture_bundle.destination_slots", return_value=(target,)):
            with self.assertRaisesRegex(ValueError, "stage failure"):
                stage_plan(session, plan)
        session.undo.assert_called_once()


class RetailWriterTests(unittest.TestCase):
    def test_synthetic_bundle_stages_and_rebuilt_retail_resource_reparses(self):
        if not RETAIL.is_file() or not all((RETAIL.parent / n).is_file() for n in ("0B", "1A", "1B")):
            self.skipTest(f"Retail APF Xbox 360 0A/0B/1A/1B absent at {RETAIL.parent}")
        from mod_editor.apf_studio.models import ApfSource
        from mod_editor.apf_studio.session import ApfSession
        import apf_inner, apf_outer, apf_logo_patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_folder(root, bundle_files())
            bundle = read_bundle(root)
            slots = destination_slots(RETAIL)
            target = next(s for s in slots if s.slot_id == "logo:36")
            plan = build_plan(bundle, slots, [Assignment(bundle.pairs[0].pair_id, target.slot_id)])
            source = ApfSource(RETAIL.parent, RETAIL.parent, RETAIL, "a" * 64, RETAIL.stat().st_size, "b" * 64, "retail gate")
            session = ApfSession(source, mock.Mock(), cache_root=root / "cache")
            try:
                staged = stage_plan(session, plan)
                self.assertEqual(len(staged), 1)
                self.assertIn("detail_sha256", staged[0].metadata)
                stage_plan(session, plan)
                self.assertEqual(len(session.modifications), 1)
                result = apf_logo_patch.build_patch_rgba(RETAIL, plan.items[0].image.tobytes(), plan.items[1].image.tobytes(), entry_index=36)
                archive = apf_outer.parse_archive(RETAIL)
                entry = archive.entries[36]
                self.assertEqual(len(result.entry_bytes), entry.size)
                reader = apf_logo_patch.BytesReader(result.entry_bytes)
                record = apf_inner.parse_iff(reader, entry)
                blocks = {i: apf_inner.decode_block(reader, record, i, 32 * 1024 * 1024) for i in range(len(record.blocks))}
                for layer, inner in zip(plan.items, apf_logo_patch.resolve_layer_indices(record)):
                    file = record.files[inner]
                    dram, vram = file.parts
                    meta = apf_inner.parse_txtr_metadata(blocks[dram.block_index][dram.offset:dram.offset + dram.length])
                    rgba = apf_logo_patch.decode_4444_base(meta, blocks[vram.block_index][vram.offset:vram.offset + 0x80000])
                    self.assertEqual(rgba, layer.image.tobytes())
            finally:
                session.close()


if __name__ == "__main__":
    unittest.main()
