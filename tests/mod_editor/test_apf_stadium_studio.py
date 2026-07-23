"""Retail-free tests for APF Stadium Studio inventory and private glTF cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mod_editor.apf_studio.asset_io import ApfAssetIO
from mod_editor.apf_studio.catalog import ApfCatalog
from mod_editor.apf_studio.models import (
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
)
from mod_editor.apf_studio.stadium import (
    ApfStadiumService,
    StadiumStudioError,
    stadium_package_assets,
    stadium_scenes,
)
from mod_editor.gui.stadium_viewer import GltfWireframeModel


def _asset(
    outer: int,
    inner: int,
    name: str,
    type_name: str,
    category: ApfCategory,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer}:inner:{inner}",
        outer_index=outer,
        inner_index=inner,
        name=name,
        type_name=type_name,
        asset_class="synthetic_fixture",
        category=category,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=1_024 + inner,
        outer_size=16_384,
        part_count=2,
    )


class ApfStadiumStudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="apf-stadium-studio-")
        self.root = Path(self.temporary.name)
        index = self.root / "0A"
        index.write_bytes(b"synthetic APF archive identity")
        self.source = ApfSource(
            selected_path=self.root,
            game_root=self.root,
            index_0a=index,
            source_sha256="1" * 64,
            source_size=index.stat().st_size,
            xex_sha256="2" * 64,
            display_name="Synthetic APF",
        )
        self.scene_asset = _asset(
            12, 3, "stadium", "SCNE", ApfCategory.STADIUMS
        )
        self.texture_asset = _asset(
            12, 1, "crowd_lower", "TXTR", ApfCategory.STADIUMS
        )
        self.same_package_other_category = _asset(
            12, 2, "opaque_helper", "SPCI", ApfCategory.ALL_ASSETS
        )
        self.assets = (
            self.texture_asset,
            self.same_package_other_category,
            self.scene_asset,
            _asset(13, 0, "stadium", "SCNE", ApfCategory.STADIUMS),
            _asset(14, 0, "stadium_alt", "SCNE", ApfCategory.STADIUMS),
            _asset(15, 0, "stadium", "TXTR", ApfCategory.STADIUMS),
        )
        self.catalog = ApfCatalog(
            source_sha256=self.source.source_sha256,
            outer_count=4,
            iff_count=4,
            non_iff_count=0,
            inner_count=len(self.assets),
            assets=self.assets,
            uniform_assets=(),
            capabilities=(),
            audio_selection_manifest=self.root / "audio-selection.json",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _decoded_scene(self, system: bytes) -> dict[str, object]:
        return {
            "root_name": "stadium",
            "system_sha256": hashlib.sha256(system).hexdigest(),
            "nodes": [
                {
                    "index": 7,
                    "name": "Synthetic stands",
                    "meshes": [
                        {
                            "primitive_type": 5,
                            "position": {"format": "float32x3"},
                            "_geometry": {
                                "positions": [
                                    [0.0, 0.0, 0.0],
                                    [2.0, 0.0, 0.0],
                                    [0.0, 1.0, 1.0],
                                    [2.0, 1.0, 1.0],
                                ],
                                "indices": [0, 1, 2, 3],
                            },
                        }
                    ],
                }
            ],
        }

    def test_lists_only_exact_stadium_scnes_and_all_same_outer_records(self) -> None:
        scenes = stadium_scenes(self.catalog)
        self.assertEqual(
            [(item.outer_index, item.inner_index) for item in scenes],
            [(12, 3), (13, 0)],
        )
        self.assertEqual(scenes[0].package_asset_count, 3)
        self.assertEqual(
            tuple(item.asset_id for item in stadium_scenes(self.catalog, "outer 13")),
            ("apf:outer:13:inner:0",),
        )
        package = stadium_package_assets(self.catalog, scenes[0])
        self.assertEqual(
            tuple(item.inner_index for item in package),
            (1, 2, 3),
        )
        self.assertIn(self.same_package_other_category, package)

    def test_prepares_validated_private_gltf_and_reuses_exact_cache(self) -> None:
        system = b"synthetic stadium SCNE system part"
        service = ApfStadiumService(
            self.source, self.catalog, self.root / "private-cache"
        )
        with (
            patch.object(service, "_read_scene_system", return_value=system) as read,
            patch(
                "mod_editor.apf_studio.stadium.apf_scene.parse_scene_system_part",
                return_value=self._decoded_scene(system),
            ) as parse,
        ):
            preview = service.prepare(self.scene_asset.asset_id)

        read.assert_called_once()
        parse.assert_called_once()
        self.assertEqual(preview.mesh_count, 1)
        self.assertEqual(preview.skipped_mesh_count, 0)
        self.assertEqual(preview.vertex_count, 4)
        self.assertEqual(preview.triangle_count, 2)
        self.assertEqual(
            tuple(item.asset_id for item in preview.package_assets),
            tuple(item.asset_id for item in stadium_package_assets(self.catalog, self.scene_asset.asset_id)),
        )
        manifest = json.loads(preview.manifest_path.read_text(encoding="utf-8"))
        self.assertFalse(manifest["claim_boundary"]["texture_ownership_resolved"])
        self.assertFalse(manifest["claim_boundary"]["stadium_texture_writer_available"])
        self.assertFalse(manifest["claim_boundary"]["geometry_import_available"])
        model = GltfWireframeModel.load(preview.gltf_path, preview.bin_path)
        identity = model.surface_identity(0, 0)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.apf_scene_node_indices, (7,))
        self.assertEqual(identity.apf_source_mesh_index, 0)

        with patch.object(
            service,
            "_read_scene_system",
            side_effect=AssertionError("a valid cache must avoid rereading retail data"),
        ):
            cached = service.prepare(self.scene_asset.asset_id)
        self.assertEqual(cached.gltf_path, preview.gltf_path)

    def test_cache_tamper_and_non_stadium_selection_fail_closed(self) -> None:
        system = b"synthetic stadium SCNE system part"
        service = ApfStadiumService(
            self.source, self.catalog, self.root / "private-cache"
        )
        with (
            patch.object(service, "_read_scene_system", return_value=system),
            patch(
                "mod_editor.apf_studio.stadium.apf_scene.parse_scene_system_part",
                return_value=self._decoded_scene(system),
            ),
        ):
            preview = service.prepare(self.scene_asset.asset_id)
        preview.gltf_path.write_text(
            preview.gltf_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(StadiumStudioError, "glTF changed"):
            service.prepare(self.scene_asset.asset_id)
        with self.assertRaisesRegex(StadiumStudioError, "exact stadium SCNE"):
            service.prepare(self.texture_asset.asset_id)

    def test_scene_bundle_contains_only_the_three_private_derivatives(self) -> None:
        system = b"synthetic stadium SCNE system part"
        asset_io = ApfAssetIO(
            self.source, self.catalog, self.root / "private-cache"
        )
        with (
            patch.object(asset_io.stadium, "_read_scene_system", return_value=system),
            patch(
                "mod_editor.apf_studio.stadium.apf_scene.parse_scene_system_part",
                return_value=self._decoded_scene(system),
            ),
        ):
            destination = asset_io.export_stadium_scene_bundle(
                self.scene_asset.asset_id, self.root / "stadium-scene.zip"
            )
        with zipfile.ZipFile(destination) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"scene.gltf", "scene.bin", "manifest.json"},
            )
            exported_manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(
            exported_manifest["scene"]["asset_id"], self.scene_asset.asset_id
        )


if __name__ == "__main__":
    unittest.main()
