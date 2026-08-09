"""Retail-free product tests for The Crib catalog and bounded writers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.model import SourceRecord
from mod_editor.core.nfl2k5_crib import (
    COMPACT_CATALOG_PATH,
    ORIGINAL_SCHEMA,
    CribAssetStatus,
    CribCatalogError,
    CribCatalogExpectations,
    CribReportPaths,
    CribStorage,
    Nfl2k5CribCatalog,
    Nfl2k5CribIO,
    load_nfl2k5_crib_catalog,
)
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256, SourceCache

from nfl_txtr import HEADER, encode_rgba_png, parse_chunks, decode_chunk


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def photo_template() -> tuple[bytes, bytes, bytes]:
    system = bytearray(128)
    system[0x0C:0x10] = b"TXTR"
    name = "00_photo_00".encode("utf-16le") + b"\0\0"
    system[32:32 + len(name)] = name
    struct.pack_into("<I", system, 0x10, 32 - 0x0F)
    struct.pack_into("<I", system, 0x14, 56 - 0x13)
    struct.pack_into(
        "<5I", system, 60, 0, 21_824, 0x07750B29, 0, 0x80000000
    )
    indices = bytes(21_824)
    palette = bytearray(1_024)
    palette[:4] = bytes((0, 0, 255, 255))
    video = indices + bytes(palette)
    body = bytes(system) + video
    span = HEADER.pack(b"TXTR", len(body), 128, 22_848, 0, 0, 0, 0) + body
    rgba = bytes((255, 0, 0, 255)) * (128 * 128)
    return span, bytes(system), rgba


def texture_row(
    name: str,
    chunk_index: int,
    *,
    outer_index: int = 4274,
    outer_head: str = "TXTR",
    decoded_sha256: str,
    rgba_sha256: str,
) -> dict[str, object]:
    return {
        "outer_index": outer_index,
        "outer_id": "0xd8b625da" if outer_index == 4274 else "0xc61a9833",
        "outer_head": outer_head,
        "outer_size": 5_575_680 if outer_index == 4274 else 5_131_344,
        "chunk_index": chunk_index,
        "chunk_offset": chunk_index * 23_040,
        "stored_size": 22_976,
        "system_bytes": 128,
        "video_bytes": 22_848,
        "compressed": False,
        "name": name,
        "descriptor_offset": 56,
        "pixel_offset": 0,
        "palette_offset": 21_824,
        "packed_format": "0x07750b29",
        "packed_size": "0x00000000",
        "format_name": "P8",
        "mip_levels": 5,
        "width": 128,
        "height": 128,
        "decoded_sha256": decoded_sha256,
        "rgba_sha256": rgba_sha256,
    }


class SyntheticCribFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.span, self.system, self.rgba = photo_template()
        self.paths = CribReportPaths(
            texture_inventory=root / "textures.json",
            photo_ownership=root / "photos.json",
            embedded_textures=root / "embedded.tsv",
            scenes=root / "scenes.tsv",
        )
        photo = texture_row(
            "00_photo_00", 0,
            decoded_sha256=sha(self.span[HEADER.size:]),
            rgba_sha256=sha(self.rgba),
        )
        item = texture_row(
            "00_helmet", 1,
            decoded_sha256="1" * 64,
            rgba_sha256="2" * 64,
        )
        external = texture_row(
            "bobblehead_00", 9,
            outer_index=4248,
            outer_head="CRIB",
            decoded_sha256="3" * 64,
            rgba_sha256="4" * 64,
        )
        self.paths.texture_inventory.write_text(json.dumps({
            "schema": "nfl2k5_all_txtr_inventory/v1",
            "textures": [photo, item, external],
        }), encoding="utf-8")
        self.paths.photo_ownership.write_text(json.dumps({
            "schema": "nfl2k5_player_portrait_compatibility/v1",
            "crib_action_photo_contract": {"resource_count": 1},
            "crib_action_photo_resources": [{
                "selector": "crib_team_photo:00_photo_00",
                "name": "00_photo_00",
                "asset_code": "00",
                "variant": 0,
                "span_sha256": sha(self.span),
                "xiso_absolute_span_offset": 123_456,
                "post_span_zero_padding": 32,
            }],
        }), encoding="utf-8")
        self.paths.scenes.write_text(
            "scene_index\touter_index\touter_id\tchunk_index\tchunk_offset\t"
            "stored_size\tsystem_bytes\tvideo_bytes\tname\tdecoded_sha256\n"
            "1\t4248\t0xc61a9833\t2\t1000\t2000\t512\t4096\troom\t"
            + "5" * 64 + "\n",
            encoding="utf-8",
        )
        self.paths.embedded_textures.write_text(
            "scene_index\touter_index\tchunk_index\tscene_name\tindex\t"
            "descriptor_offset\tunknown0\tpixel_offset\tpalette_offset\t"
            "packed_format\tpacked_size\tdescriptor_flags\textra_word_18\t"
            "extra_word_1c\tdimensions\tformat_code\tformat_name\tmip_levels\t"
            "width\theight\tdepth\tconversion_status\trgba_sha256\t"
            "mapped_material_count\tmapped_material_names\tconversion_error\n"
            "1\t4248\t2\troom\t0\t100\t0x0\t0\t5440\t107219753\t0\t"
            "2147483648\t0\t0\t2\t11\tP8\t4\t64\t64\t1\t"
            "base_level_supported\t" + "6" * 64 + "\t1\tbar_monitor\t\n",
            encoding="utf-8",
        )
        self.expectations = CribCatalogExpectations(
            team_item_count=2,
            photo_count=1,
            external_texture_count=1,
            embedded_texture_count=1,
            embedded_scene_count=1,
        )

    def catalog(self) -> Nfl2k5CribCatalog:
        return Nfl2k5CribCatalog.from_reports(
            self.paths, expectations=self.expectations
        )


class Nfl2k5CribProductionCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_crib_catalog()

    def test_all_known_physical_crib_textures_are_visible_once(self) -> None:
        self.assertEqual(len(self.catalog.assets), 498)
        self.assertEqual(len(self.catalog.photos), 128)
        self.assertEqual(len(self.catalog.objects), 370)
        self.assertEqual(len({asset.asset_id for asset in self.catalog.assets}), 498)
        self.assertEqual(len({asset.selector for asset in self.catalog.assets}), 498)
        storage_counts = {
            storage: sum(asset.storage is storage for asset in self.catalog.assets)
            for storage in CribStorage
        }
        self.assertEqual(storage_counts, {
            CribStorage.TEAM_ITEM_AGGREGATE: 242,
            CribStorage.EXTERNAL_TEXTURE: 68,
            CribStorage.SCENE_EMBEDDED: 188,
        })
        self.assertEqual(
            len({asset.scene_name for asset in self.catalog.assets if asset.scene_name}),
            36,
        )

    def test_all_498_crib_textures_are_editable(self) -> None:
        bar_monitor = self.catalog.by_selector("crib_scene_texture:room:22")
        self.assertIn("bar_monitor", bar_monitor.material_names)
        self.assertEqual(bar_monitor.status, CribAssetStatus.EDITABLE)
        self.assertEqual(bar_monitor.asset_id, "nfl2k5.crib.scene.c0002.t022")
        self.assertEqual(bar_monitor.provider_edit("user-screen.png"), {
            "kind": "crib_scene_texture",
            "png": "user-screen.png",
            "selector": "crib_scene_texture:room:22",
        })
        self.assertIn("recompresses", bar_monitor.authoring_note)
        self.assertEqual(sum(asset.editable for asset in self.catalog.assets), 498)
        self.assertEqual(sum(not asset.editable for asset in self.catalog.assets), 0)
        trivia = self.catalog.search("trivia machine")
        self.assertTrue(trivia)
        self.assertTrue(all(asset.editable for asset in trivia[:3]))
        self.assertTrue(all(asset.editable for asset in trivia))
        ownership = json.loads(Path(
            "reports/experiments/nfl2k5_crib_electronics_ownership.json"
        ).read_text(encoding="utf-8"))
        electronics = [
            self.catalog.by_selector(row["selector"])
            for row in ownership["textures"]
        ]
        self.assertEqual(len(electronics), 25)
        self.assertTrue(all(asset.editable for asset in electronics))
        self.assertEqual(sum(not asset.editable for asset in electronics), 0)

        item = self.catalog.by_selector("crib_item_texture:00_helmet")
        self.assertEqual(item.provider_edit("mine.png")["kind"],
                         "crib_standalone_texture")
        external = self.catalog.by_selector("crib_external_texture:7:logo")
        self.assertEqual(external.provider_edit("mine.png")["kind"],
                         "crib_standalone_texture")

    def test_compact_release_catalog_exactly_matches_audited_reports(self) -> None:
        compact = Nfl2k5CribCatalog.from_compact_catalog(COMPACT_CATALOG_PATH)
        audited = Nfl2k5CribCatalog.from_reports()
        self.assertEqual(compact.assets, audited.assets)
        payload = COMPACT_CATALOG_PATH.read_bytes()
        self.assertLess(len(payload), 2 * 1024 * 1024)
        self.assertNotIn(b"replacement_span", payload)
        self.assertNotIn(b"preview_png", payload)

    def test_bar_monitor_wrong_dimensions_are_explained_before_build(self) -> None:
        asset = self.catalog.by_selector("crib_scene_texture:room:22")
        with tempfile.TemporaryDirectory() as temporary:
            supplied = Path(temporary) / "wrong-screen.png"
            supplied.write_bytes(
                encode_rgba_png(64, 64, bytes((8, 16, 32, 255)) * (64 * 64))
            )
            with self.assertRaisesRegex(ValidationError, "128×128"):
                Nfl2k5CribIO.validate_replacement(asset, supplied)


class Nfl2k5CribSyntheticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = SyntheticCribFixture(self.root)
        self.catalog = self.fixture.catalog()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def cache(
        self,
        *,
        source_sha256: str = "a" * 64,
        source_size: int = 6_300_958_720,
    ) -> SourceCache:
        originals = self.root / "originals"
        originals.mkdir(exist_ok=True)
        dummy = self.root / "dummy"
        dummy.touch(exist_ok=True)
        source = SourceRecord(
            selected_path=str(dummy),
            inspected_path=str(dummy),
            kind="xiso",
            sha256=source_sha256,
            size=source_size,
            recognized=True,
            fingerprint_id="synthetic",
            detected_game="nfl2k5",
        )
        return SourceCache(
            source=source,
            root=self.root,
            pack0=dummy,
            inventory=dummy,
            originals=originals,
            resource_count=0,
            outer_entry_count=0,
            kind_counts={},
        )

    def test_shareable_photo_edit_has_no_retail_bytes_or_offsets(self) -> None:
        photo = self.catalog.by_selector("crib_team_photo:00_photo_00")
        self.assertTrue(photo.editable)
        edit = photo.provider_edit("replacements/my-wall-photo.png")
        self.assertEqual(edit, {
            "kind": "crib_team_photo",
            "png": "replacements/my-wall-photo.png",
            "selector": "crib_team_photo:00_photo_00",
        })
        lowered = json.dumps(edit).lower()
        for forbidden in ("offset", "span", "sha256", "retail"):
            self.assertNotIn(forbidden, lowered)
        item = self.catalog.by_selector("crib_item_texture:00_helmet")
        self.assertEqual(item.provider_edit("replacement.png"), {
            "kind": "crib_standalone_texture",
            "png": "replacement.png",
            "selector": "crib_item_texture:00_helmet",
        })

    def test_photo_export_and_five_mip_replacement_are_round_trip_safe(self) -> None:
        photo = self.catalog.by_selector("crib_team_photo:00_photo_00")
        io = Nfl2k5CribIO(
            self.cache(), self.catalog,
            span_reader=lambda asset: self.fixture.span,
        )
        original = io.ensure_original(photo)
        self.assertTrue(original.is_file())
        self.assertEqual(original, io.ensure_original(photo))
        metadata = json.loads(original.with_suffix(".json").read_text())
        self.assertEqual(metadata["schema"], ORIGINAL_SCHEMA)
        self.assertEqual(metadata["source_sha256"], SOURCE_SHA256)

        # A raw-disc layout has a different whole-container digest and size but
        # resolves to the same pinned private source cache. Its valid original
        # must be reused without decoding the retail span again.
        raw_layout = Nfl2k5CribIO(
            self.cache(source_sha256="b" * 64, source_size=7_825_162_240),
            self.catalog,
            span_reader=lambda _asset: (_ for _ in ()).throw(
                AssertionError("canonical Crib original was re-decoded")
            ),
        )
        self.assertEqual(raw_layout.ensure_original(photo), original)

        pixels = bytearray()
        colors = (
            (0, 255, 255, 255),
            (255, 0, 255, 255),
            (255, 255, 0, 255),
            (0, 0, 0, 255),
        )
        for y in range(128):
            for x in range(128):
                pixels.extend(colors[(x >= 64) + 2 * (y >= 64)])
        replacement = self.root / "replacement.png"
        replacement.write_bytes(encode_rgba_png(128, 128, bytes(pixels)))
        patch = io.compile_photo(photo, replacement)
        self.assertEqual(patch.absolute_xiso_offset, 123_456)
        self.assertEqual(len(patch.replacement_span), len(self.fixture.span))
        self.assertGreater(patch.changed_byte_count, 0)
        self.assertEqual(
            patch.replacement_span[:HEADER.size + 128],
            self.fixture.span[:HEADER.size + 128],
        )
        chunks = parse_chunks(patch.replacement_span)
        decoded, info = decode_chunk(patch.replacement_span, chunks[0])
        self.assertIsNone(info)
        self.assertEqual(len(decoded), 128 + 22_848)
        self.assertEqual(
            patch.shareable_edit(replacement),
            photo.provider_edit(replacement),
        )

    def test_crib_original_migrates_only_an_intact_legacy_source_binding(self) -> None:
        photo = self.catalog.by_selector("crib_team_photo:00_photo_00")
        io = Nfl2k5CribIO(
            self.cache(), self.catalog, span_reader=lambda _asset: self.fixture.span
        )
        original = io.ensure_original(photo)
        metadata = original.with_suffix(".json")
        legacy = json.loads(metadata.read_text())
        legacy["source_sha256"] = "c" * 64
        metadata.write_text(json.dumps(legacy), encoding="utf-8")
        calls = 0

        def read_span(_asset):
            nonlocal calls
            calls += 1
            return self.fixture.span

        migrated = Nfl2k5CribIO(
            self.cache(source_sha256="b" * 64, source_size=7_825_162_240),
            self.catalog,
            span_reader=read_span,
        ).ensure_original(photo)

        self.assertEqual(migrated, original)
        self.assertEqual(calls, 1)
        self.assertEqual(
            json.loads(metadata.read_text())["source_sha256"], SOURCE_SHA256
        )

    def test_crib_original_still_refuses_tampered_incomplete_and_linked_pairs(self) -> None:
        photo = self.catalog.by_selector("crib_team_photo:00_photo_00")

        for defect in ("tampered", "incomplete", "linked"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cache = self.cache()
                cache = SourceCache(
                    source=cache.source,
                    root=cache.root,
                    pack0=cache.pack0,
                    inventory=cache.inventory,
                    originals=root,
                    resource_count=cache.resource_count,
                    outer_entry_count=cache.outer_entry_count,
                    kind_counts=cache.kind_counts,
                )
                io = Nfl2k5CribIO(
                    cache, self.catalog, span_reader=lambda _asset: self.fixture.span
                )
                original = io.ensure_original(photo)
                metadata = original.with_suffix(".json")
                if defect == "tampered":
                    original.write_bytes(b"changed outside the app")
                elif defect == "incomplete":
                    metadata.unlink()
                else:
                    target = root / "outside.png"
                    target.write_bytes(original.read_bytes())
                    original.unlink()
                    original.symlink_to(target)

                with self.assertRaisesRegex(ValidationError, "changed outside Mod Studio"):
                    io.ensure_original(photo)

    def test_wrong_dimensions_and_unknown_selectors_are_human_readable(self) -> None:
        photo = self.catalog.by_selector("crib_team_photo:00_photo_00")
        wrong = self.root / "wrong.png"
        wrong.write_bytes(encode_rgba_png(64, 64, bytes((1, 2, 3, 255)) * 4096))
        io = Nfl2k5CribIO(
            self.cache(), self.catalog,
            span_reader=lambda asset: self.fixture.span,
        )
        with self.assertRaisesRegex(ValidationError, "128x128"):
            io.compile_photo(photo, wrong)
        with self.assertRaisesRegex(CribCatalogError, "Unknown Crib selector"):
            self.catalog.by_selector("crib_team_photo:missing")


if __name__ == "__main__":
    unittest.main()
