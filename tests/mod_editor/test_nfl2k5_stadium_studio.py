from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from mod_editor.core.errors import ActionNotImplementedError, ValidationError
from mod_editor.core.nfl2k5_stadium_studio import (
    EDITABLE,
    Nfl2k5StadiumStudio,
    PREVIEW_EXPORT_ONLY,
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def one_pixel_png(rgba: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + rgba, 9))
        + chunk(b"IEND", b"")
    )


class FakeTextureDelegate:
    def __init__(self) -> None:
        self.current: dict[str, Path] = {}
        self.reverted: list[str] = []

    def supports(self, texture: object) -> bool:
        return getattr(texture, "texture_index") == 0

    def current_png(self, texture: object) -> Path:
        return self.current.get(getattr(texture, "texture_id"), getattr(texture, "png_path"))

    def replace(self, texture: object, supplied_png: Path) -> str:
        self.current[getattr(texture, "texture_id")] = supplied_png
        return "replaced"

    def revert(self, texture: object) -> str:
        texture_id = getattr(texture, "texture_id")
        self.current.pop(texture_id, None)
        self.reverted.append(texture_id)
        return "reverted"


class StadiumStudioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # Resolve the temp root so paths the studio canonicalises compare equal to
        # ours under a symlinked (macOS /private/var) or short-name (Windows) temp
        # location.
        self.root = Path(self.temporary.name).resolve()
        self.models = self.root / "models"
        self.textures = self.root / "scne_textures"
        self.models.mkdir()
        self.textures.mkdir()
        self.scene_index = 77
        self.outer_index = 42
        self.chunk_index = 3
        self.gltf_manifest = self.models / "manifest.json"
        self.texture_manifest = self.root / "texture-manifest.json"
        self.geometry_catalog = self.root / "geometry-catalog.json"
        self.png_payload = one_pixel_png(bytes((10, 20, 30, 255)))
        self.rgba_hash = digest(bytes((10, 20, 30, 255)))
        png_rel = Path("by_rgba_sha256") / self.rgba_hash[:2] / f"{self.rgba_hash}.png"
        self.png_path = self.textures / png_rel
        self.png_path.parent.mkdir(parents=True)
        self.png_path.write_bytes(self.png_payload)
        self._write_scene()
        self._write_texture_manifest(png_rel)
        self._write_geometry_catalog()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_scene(self) -> None:
        binary = b"nonretail synthetic stadium geometry"
        gltf = {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(binary), "uri": "0042_0003_stadium.bin"}],
            "nodes": [
                {
                    "name": "paintable_wall",
                    "mesh": 0,
                    "extras": {"source_shape_index": 7},
                }
            ],
            "meshes": [
                {
                    "name": "paintable_wall",
                    "primitives": [
                        {
                            "extras": {
                                "source_material_index": 0,
                                "source_material_name": "wall_art",
                                "source_submesh_index": 0,
                            }
                        },
                        {
                            "extras": {
                                "source_material_index": 1,
                                "source_material_name": "untextured",
                                "source_submesh_index": 1,
                            }
                        },
                    ],
                }
            ],
        }
        gltf_payload = (json.dumps(gltf, indent=2) + "\n").encode("utf-8")
        (self.models / "0042_0003_stadium.gltf").write_bytes(gltf_payload)
        (self.models / "0042_0003_stadium.bin").write_bytes(binary)
        manifest = {
            "schema": "nfl2k5_static_gltf_manifest/v2",
            "exports": [
                {
                    "outer_index": self.outer_index,
                    "chunk_index": self.chunk_index,
                    "scene_index": self.scene_index,
                    "scene_name": "stadium",
                    "status": "exported",
                    "gltf": "0042_0003_stadium.gltf",
                    "bin": "0042_0003_stadium.bin",
                    "gltf_sha256": digest(gltf_payload),
                    "bin_sha256": digest(binary),
                    "mesh_count": 1,
                    "primitive_count": 2,
                    "vertex_count": 4,
                },
                {
                    "outer_index": 99,
                    "chunk_index": 0,
                    "scene_index": 90,
                    "scene_name": "not_a_stadium",
                    "status": "withheld",
                },
            ],
        }
        self.gltf_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def _write_texture_manifest(self, png_rel: Path) -> None:
        prefix = Path("assets/intermediate/nfl2k5/scne_textures") / png_rel
        common = {
            "outer_index": self.outer_index,
            "chunk_index": self.chunk_index,
            "scene_index": self.scene_index,
            "scene_name": "stadium",
        }
        document = {
            "schema": "nfl2k5_scne_embedded_texture_png/v1",
            "materials": [
                {
                    **common,
                    "material_index": 0,
                    "material_name": "wall_art",
                    "mapping_status": "mapped_embedded_texture",
                    "texture_index": 0,
                },
                {
                    **common,
                    "material_index": 1,
                    "material_name": "untextured",
                    "mapping_status": "null_texture_pointer",
                    "texture_index": None,
                },
                {
                    "outer_index": 500,
                    "chunk_index": 0,
                    "scene_index": 999,
                    "scene_name": "menu",
                    "material_index": 0,
                },
            ],
            "occurrences": [
                {
                    **common,
                    "texture_index": 0,
                    "width": 1,
                    "height": 1,
                    "format_name": "P8",
                    "rgba_sha256": self.rgba_hash,
                    "png_sha256": digest(self.png_payload),
                    "png_path": prefix.as_posix(),
                    "mapped_material_names": "wall_art",
                    "mapped_material_count": 1,
                }
            ],
            "pngs": [],
        }
        self.texture_manifest.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    def _write_geometry_catalog(self) -> None:
        source = {
            "outer_index": self.outer_index,
            "chunk_index": self.chunk_index,
            "scene_index": self.scene_index,
        }
        document = {
            "schema": "nfl2k5_stadium_static_target_catalog/v1",
            "targets": [
                {
                    "target_id": "nfl2k5/stadium/o0042/c3/s7",
                    "source_identity": source,
                    "shape": {"index": 7, "name": "paintable_wall", "vertex_count": 4},
                    "eligibility": {"runtime_visibility_proved": False},
                }
            ],
            "implemented_reference": {
                "target_id": "nfl2k5/stadium/o0042/c3/s8",
                "shape_index": 8,
                "shape_name": "reference_quad",
            },
            "resource_contract": {
                "outer_entry": {"index": self.outer_index},
                "resource": {"chunk_index": self.chunk_index},
            },
        }
        self.geometry_catalog.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    def _open(self, delegate: object | None = None) -> Nfl2k5StadiumStudio:
        return Nfl2k5StadiumStudio(
            self.gltf_manifest,
            self.texture_manifest,
            self.textures,
            geometry_catalog=self.geometry_catalog,
            edit_delegate=delegate,
        )

    def test_enumerates_scene_nodes_materials_textures_and_geometry_bounds(self) -> None:
        studio = self._open()
        self.assertEqual(studio.scene_count, 1)
        scene = studio.list_scenes(search="42")[0]
        self.assertEqual(scene.mesh_count, 1)
        self.assertEqual(len(scene.geometry_targets), 2)
        self.assertEqual(
            [target.writer_route for target in scene.geometry_targets],
            ["catalog-same-count-position-v2", "group36-same-footprint-v1"],
        )
        details = studio.scene_details(scene)
        self.assertEqual(len(details.nodes), 1)
        self.assertEqual(len(details.materials), 2)
        self.assertEqual(len(details.textures), 1)
        self.assertEqual(details.textures[0].access_status, PREVIEW_EXPORT_ONLY)
        self.assertEqual(details.materials[0].owners[0].node_name, "paintable_wall")
        self.assertEqual(
            studio.texture_for_surface(scene.scene_id, 0, 0), details.textures[0]
        )
        self.assertIsNone(studio.texture_for_surface(scene.scene_id, 0, 1))
        with self.assertRaisesRegex(ValidationError, "not present"):
            studio.texture_for_surface(scene.scene_id, 2, 0)

    def test_preview_export_only_is_honest_and_export_is_exact(self) -> None:
        studio = self._open()
        texture = studio.scene_details(studio.list_scenes()[0]).textures[0]
        self.assertEqual(studio.preview_texture(texture.texture_id), self.png_path)
        output = self.root / "exported.png"
        studio.export_texture(texture.texture_id, output)
        self.assertEqual(output.read_bytes(), self.png_payload)
        with self.assertRaises(ActionNotImplementedError):
            studio.replace_texture(texture.texture_id, self.png_path)
        with self.assertRaises(ActionNotImplementedError):
            studio.revert_texture(texture.texture_id)

    def test_exact_delegate_unlocks_only_the_texture_it_supports(self) -> None:
        delegate = FakeTextureDelegate()
        studio = self._open(delegate)
        texture = studio.scene_details(studio.list_scenes()[0]).textures[0]
        self.assertEqual(texture.access_status, EDITABLE)
        replacement = self.root / "replacement.png"
        replacement.write_bytes(one_pixel_png(bytes((200, 100, 50, 255))))
        self.assertEqual(
            studio.replace_texture(texture.texture_id, replacement), "replaced"
        )
        self.assertEqual(studio.preview_texture(texture.texture_id), replacement)
        self.assertEqual(studio.revert_texture(texture.texture_id), "reverted")
        self.assertEqual(studio.preview_texture(texture.texture_id), self.png_path)

    def test_runtime_manifest_contains_metadata_and_findings_not_asset_bytes(self) -> None:
        document = self._open().runtime_manifest()
        self.assertEqual(document["scene_count"], 1)
        encoded = json.dumps(document)
        self.assertIn("Preview/Export-only", encoded)
        self.assertIn("shader stage", encoded)
        self.assertNotIn(self.png_payload.hex(), encoded)

    def test_rejects_gltf_hash_drift_and_noncanonical_png_path(self) -> None:
        studio = self._open()
        gltf = self.models / "0042_0003_stadium.gltf"
        gltf.write_text(gltf.read_text(encoding="utf-8") + " ", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "no longer matches"):
            studio.scene_details(studio.list_scenes()[0])

        self._write_scene()
        data = json.loads(self.texture_manifest.read_text(encoding="utf-8"))
        data["occurrences"][0]["png_path"] = "somewhere/wrong.png"
        self.texture_manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        broken = self._open()
        with self.assertRaisesRegex(ValidationError, "noncanonical"):
            broken.scene_details(broken.list_scenes()[0])

    def test_rejects_symlinked_manifest_and_asset_escape(self) -> None:
        linked = self.root / "linked-manifest.json"
        linked.symlink_to(self.gltf_manifest)
        with self.assertRaisesRegex(ValidationError, "regular file"):
            Nfl2k5StadiumStudio(linked, self.texture_manifest, self.textures)

        document = json.loads(self.gltf_manifest.read_text(encoding="utf-8"))
        document["exports"][0]["gltf"] = "../outside.gltf"
        self.gltf_manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "unsafe path"):
            self._open()


if __name__ == "__main__":
    unittest.main()
