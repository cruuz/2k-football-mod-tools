"""Getting a 2K5 stadium out of the editor and into Blender.

The Stadiums page could render a stadium but offered no way to save it, so a
modder could look at a model and still not open it -- reported directly: "for
the stadium mods it's APF 2k8 only right? ... 2k5 doesn't have an export for a
gltf file".

The export has to solve the *second* half of that report too. The same modder
had already hit APF models arriving about a hundred times too large in Blender,
and 2K5 has exactly the same problem and never had the fix: measured on real
samples, ``3161_0006_stadium.gltf`` spans 23,122 x 7,615 x 29,044 authored
units. glTF's unit is the metre, so an untouched copy declares a 23 km stadium
and disappears past Blender's default 1 km view distance. Shipping the export
without the unit fix would ship the bug he already reported.

The fix is a single scaled root node, not rewritten vertices. That distinction
is what these tests hold hardest: the buffer must come out byte-identical to
what the game shipped, because the geometry still has to mean what the game says
it means. Only the file's declared units change.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.errors import (  # noqa: E402
    ActionNotImplementedError,
    ValidationError,
)
from mod_editor.core.nfl2k5_stadium_studio import (  # noqa: E402
    GLTF_UNIT_SCALE,
    Nfl2k5StadiumStudio,
)
from nfl_scne_embedded_texture_png import parse_png_rgba  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def one_pixel_png(rgba: bytes) -> bytes:
    """The same deterministic IHDR/IDAT/IEND container the cache worker emits."""

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


class RecordingTextureDelegate:
    """Test double for the bounded P8 writer's replace route."""

    def __init__(self) -> None:
        self.supplied: dict[str, bytes] = {}
        self.reverted: list[str] = []

    def supports(self, texture: object) -> bool:
        return getattr(texture, "texture_index", None) == 0

    def current_png(self, texture: object) -> Path:
        raise AssertionError("export embedding must use the manifest PNG here")

    def replace(self, texture: object, supplied_png: Path) -> str:
        texture_id = getattr(texture, "texture_id")
        self.supplied[texture_id] = supplied_png.read_bytes()
        return "replaced"

    def revert(self, texture: object) -> str:
        texture_id = getattr(texture, "texture_id")
        self.supplied.pop(texture_id, None)
        self.reverted.append(texture_id)
        return "reverted"


class StadiumGltfExportTests(unittest.TestCase):
    """A synthetic scene; no retail geometry is needed to test the contract."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.models = self.root / "models"
        self.models.mkdir()
        self.textures = self.root / "textures"
        self.textures.mkdir()
        self.out = self.root / "out"
        self.out.mkdir()

        # Three positions so the buffer has real content to compare against.
        self.binary = struct.pack("<9f", *[float(n) for n in range(9)])
        (self.models / "0042_0003_stadium.bin").write_bytes(self.binary)

        document = {
            "asset": {"version": "2.0"},
            "buffers": [
                {"byteLength": len(self.binary), "uri": "0042_0003_stadium.bin"}
            ],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(self.binary)}
            ],
            "accessors": [{
                "bufferView": 0, "componentType": 5126, "count": 3,
                "type": "VEC3", "min": [0.0, 1.0, 2.0], "max": [6.0, 7.0, 8.0],
            }],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "mode": 4}]}],
            "nodes": [
                {"name": "upper_deck", "mesh": 0},
                {"name": "lower_bowl", "mesh": 0},
            ],
            "scenes": [{"nodes": [0, 1]}],
            "scene": 0,
        }
        self.gltf_payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        (self.models / "0042_0003_stadium.gltf").write_bytes(self.gltf_payload)

        manifest = {
            "schema": "nfl2k5_static_gltf_manifest/v2",
            "exports": [{
                "outer_index": 42,
                "chunk_index": 3,
                "scene_index": 0,
                "scene_name": "stadium",
                "status": "exported",
                "gltf": "0042_0003_stadium.gltf",
                "bin": "0042_0003_stadium.bin",
                "gltf_sha256": hashlib.sha256(self.gltf_payload).hexdigest(),
                "bin_sha256": hashlib.sha256(self.binary).hexdigest(),
                "mesh_count": 1,
                "primitive_count": 1,
                "vertex_count": 3,
            }],
        }
        self.manifest = self.models / "manifest.json"
        self.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        # No textures are needed to test a geometry export, but the studio still
        # authenticates the manifest's schema before it will open.
        texture_manifest = {
            "schema": "nfl2k5_scne_embedded_texture_png/v1",
            "materials": [],
            "occurrences": [],
            "textures": [],
        }
        self.texture_manifest = self.root / "textures.json"
        self.texture_manifest.write_text(
            json.dumps(texture_manifest, indent=2) + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _studio(self) -> Nfl2k5StadiumStudio:
        return Nfl2k5StadiumStudio(
            self.manifest, self.texture_manifest, self.textures
        )

    def _scene_id(self, studio: Nfl2k5StadiumStudio) -> str:
        return studio.list_scenes()[0].scene_id

    def test_it_writes_the_model_and_its_buffer_together(self) -> None:
        studio = self._studio()
        gltf, binary = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        self.assertTrue(gltf.is_file())
        self.assertTrue(binary.is_file())
        # The glTF names its buffer by filename, so the pair must keep that name.
        self.assertEqual(binary.name, "0042_0003_stadium.bin")
        self.assertEqual(binary.parent, gltf.parent)

    def test_the_buffer_is_byte_identical(self) -> None:
        """No vertex is re-encoded; the geometry still means what the game says."""

        studio = self._studio()
        _, binary = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        self.assertEqual(binary.read_bytes(), self.binary)

    def test_one_scaled_root_adopts_every_former_root(self) -> None:
        studio = self._studio()
        gltf, _ = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        document = json.loads(gltf.read_text(encoding="utf-8"))

        roots = document["scenes"][document["scene"]]["nodes"]
        self.assertEqual(len(roots), 1)
        root = document["nodes"][roots[0]]
        self.assertEqual(
            root["scale"], [GLTF_UNIT_SCALE, GLTF_UNIT_SCALE, GLTF_UNIT_SCALE]
        )
        self.assertEqual(sorted(root["children"]), [0, 1])

    def test_the_declared_extent_lands_in_metres(self) -> None:
        """The whole point: the model must open at a usable size."""

        studio = self._studio()
        gltf, _ = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        document = json.loads(gltf.read_text(encoding="utf-8"))
        accessor = document["accessors"][0]
        authored = max(
            hi - lo for hi, lo in zip(accessor["max"], accessor["min"])
        )
        self.assertAlmostEqual(authored * GLTF_UNIT_SCALE, authored / 100.0)

    def test_the_unit_change_is_recorded_in_the_file(self) -> None:
        """Someone opening this later should be able to see what was done."""

        studio = self._studio()
        gltf, _ = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        contract = json.loads(gltf.read_text(encoding="utf-8"))["extras"][
            "nfl2k5_unit_contract"
        ]
        self.assertEqual(contract["authored_unit"], "centimetre")
        self.assertEqual(contract["gltf_unit"], "metre")
        self.assertEqual(contract["applied_as"], "root node scale")
        self.assertIs(contract["buffer_rewritten"], False)

    def test_a_glTF_without_a_declared_scene_still_exports(self) -> None:
        """``scenes`` is optional in glTF 2.0 and the corpus is not uniform."""

        document = json.loads(
            (self.models / "0042_0003_stadium.gltf").read_text(encoding="utf-8")
        )
        del document["scenes"]
        del document["scene"]
        payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        (self.models / "0042_0003_stadium.gltf").write_bytes(payload)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["exports"][0]["gltf_sha256"] = hashlib.sha256(payload).hexdigest()
        self.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        studio = self._studio()
        gltf, _ = studio.export_scene_gltf(
            self._scene_id(studio), self.out / "stadium.gltf"
        )
        written = json.loads(gltf.read_text(encoding="utf-8"))
        roots = written["scenes"][written["scene"]]["nodes"]
        self.assertEqual(len(roots), 1)
        self.assertEqual(sorted(written["nodes"][roots[0]]["children"]), [0, 1])

    def test_it_refuses_to_overwrite_anything(self) -> None:
        studio = self._studio()
        existing = self.out / "stadium.gltf"
        existing.write_text("do not clobber me", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "already exists"):
            studio.export_scene_gltf(self._scene_id(studio), existing)
        self.assertEqual(existing.read_text(encoding="utf-8"), "do not clobber me")

    def test_it_refuses_when_the_buffer_name_would_collide(self) -> None:
        studio = self._studio()
        with self.assertRaisesRegex(ValidationError, "cannot share one filename"):
            studio.export_scene_gltf(
                self._scene_id(studio), self.out / "0042_0003_stadium.bin"
            )

    def test_a_tampered_source_is_refused_before_anything_is_written(self) -> None:
        """The manifest hash is the gate; a changed model must not export."""

        (self.models / "0042_0003_stadium.bin").write_bytes(b"tampered")
        studio = self._studio()
        with self.assertRaisesRegex(ValidationError, "no longer matches its manifest"):
            studio.export_scene_gltf(
                self._scene_id(studio), self.out / "stadium.gltf"
            )
        self.assertEqual(list(self.out.iterdir()), [])

    def test_nothing_is_left_behind_when_the_buffer_cannot_be_written(self) -> None:
        """Both files land or neither does."""

        studio = self._studio()
        blocker = self.out / "0042_0003_stadium.bin"
        blocker.write_text("occupied", encoding="utf-8")
        with self.assertRaises(ValidationError):
            studio.export_scene_gltf(
                self._scene_id(studio), self.out / "stadium.gltf"
            )
        self.assertFalse((self.out / "stadium.gltf").exists())
        self.assertEqual(blocker.read_text(encoding="utf-8"), "occupied")

    def test_the_source_model_is_never_modified(self) -> None:
        before_gltf = _sha256(self.models / "0042_0003_stadium.gltf")
        before_bin = _sha256(self.models / "0042_0003_stadium.bin")
        studio = self._studio()
        studio.export_scene_gltf(self._scene_id(studio), self.out / "stadium.gltf")
        self.assertEqual(_sha256(self.models / "0042_0003_stadium.gltf"), before_gltf)
        self.assertEqual(_sha256(self.models / "0042_0003_stadium.bin"), before_bin)

    def test_exporting_twice_to_the_same_name_is_refused(self) -> None:
        studio = self._studio()
        studio.export_scene_gltf(self._scene_id(studio), self.out / "stadium.gltf")
        with self.assertRaisesRegex(ValidationError, "already exists"):
            studio.export_scene_gltf(
                self._scene_id(studio), self.out / "stadium.gltf"
            )


class StadiumGltfTextureEmbeddingTests(unittest.TestCase):
    """F2: the exported glTF carries the game's decoded surface textures.

    The fixture mirrors the private Stadium cache corpus: one scene, one mesh,
    two primitives (one textured material, one untextured), and a texture
    manifest whose PNG was produced by the proved P8 decode.
    """

    SCENE_ID = "nfl2k5.stadium.o0042.c0003.scene0077"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.models = self.root / "models"
        self.models.mkdir()
        self.textures = self.root / "textures"
        self.textures.mkdir()
        self.out = self.root / "out"
        self.out.mkdir()

        self.binary = struct.pack("<9f", *[float(n) for n in range(9)])
        (self.models / "0042_0003_stadium.bin").write_bytes(self.binary)

        document = {
            "asset": {"version": "2.0"},
            "buffers": [
                {"byteLength": len(self.binary), "uri": "0042_0003_stadium.bin"}
            ],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(self.binary)}
            ],
            "accessors": [{
                "bufferView": 0, "componentType": 5126, "count": 3,
                "type": "VEC3", "min": [0.0, 1.0, 2.0], "max": [6.0, 7.0, 8.0],
            }],
            "meshes": [{
                "name": "paintable_wall",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "mode": 4,
                        "extras": {
                            "source_material_index": 0,
                            "source_submesh_index": 0,
                        },
                    },
                    {
                        "attributes": {"POSITION": 0},
                        "mode": 4,
                        "extras": {
                            "source_material_index": 1,
                            "source_submesh_index": 1,
                        },
                    },
                ],
            }],
            "nodes": [
                {
                    "name": "paintable_wall",
                    "mesh": 0,
                    "extras": {"source_shape_index": 7},
                }
            ],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        }
        self.gltf_payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        (self.models / "0042_0003_stadium.gltf").write_bytes(self.gltf_payload)

        manifest = {
            "schema": "nfl2k5_static_gltf_manifest/v2",
            "exports": [{
                "outer_index": 42,
                "chunk_index": 3,
                "scene_index": 77,
                "scene_name": "stadium",
                "status": "exported",
                "gltf": "0042_0003_stadium.gltf",
                "bin": "0042_0003_stadium.bin",
                "gltf_sha256": digest(self.gltf_payload),
                "bin_sha256": digest(self.binary),
                "mesh_count": 1,
                "primitive_count": 2,
                "vertex_count": 3,
            }],
        }
        self.manifest = self.models / "manifest.json"
        self.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        self.rgba = bytes((200, 60, 30, 255))
        self.rgba_hash = digest(self.rgba)
        self.png_payload = one_pixel_png(self.rgba)
        png_rel = Path("by_rgba_sha256") / self.rgba_hash[:2] / f"{self.rgba_hash}.png"
        png_path = self.textures / png_rel
        png_path.parent.mkdir(parents=True)
        png_path.write_bytes(self.png_payload)

        common = {
            "outer_index": 42,
            "chunk_index": 3,
            "scene_index": 77,
            "scene_name": "stadium",
        }
        texture_manifest = {
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
                    "material_name": "bare_concrete",
                    "mapping_status": "null_texture_pointer",
                    "texture_index": None,
                },
            ],
            "occurrences": [{
                **common,
                "texture_index": 0,
                "width": 1,
                "height": 1,
                "format_name": "P8",
                "rgba_sha256": self.rgba_hash,
                "png_sha256": digest(self.png_payload),
                "png_path": png_rel.as_posix(),
                "mapped_material_names": "wall_art",
                "mapped_material_count": 1,
            }],
            "pngs": [],
        }
        self.texture_manifest = self.root / "textures.json"
        self.texture_manifest.write_text(
            json.dumps(texture_manifest, indent=2) + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _studio(self, delegate: object | None = None) -> Nfl2k5StadiumStudio:
        return Nfl2k5StadiumStudio(
            self.manifest, self.texture_manifest, self.textures,
            edit_delegate=delegate,
        )

    def _export(self, studio: Nfl2k5StadiumStudio) -> tuple[Path, Path]:
        return studio.export_scene_gltf(
            self.SCENE_ID, self.out / "stadium.gltf"
        )

    def test_textured_materials_carry_the_game_image(self) -> None:
        gltf, _ = self._export(self._studio())
        document = json.loads(gltf.read_text(encoding="utf-8"))

        self.assertEqual(len(document["images"]), 1)
        image = document["images"][0]
        self.assertEqual(image["mimeType"], "image/png")
        self.assertEqual(image["name"], "wall_art")
        self.assertEqual(len(document["textures"]), 1)
        texture = document["textures"][0]
        self.assertEqual(texture["source"], 0)
        self.assertEqual(texture["sampler"], 0)
        self.assertTrue(document["samplers"])

        materials = document["materials"]
        self.assertEqual([row["name"] for row in materials],
                         ["wall_art", "bare_concrete"])
        textured = materials[0]["pbrMetallicRoughness"]
        self.assertEqual(textured["baseColorTexture"]["index"], 0)
        self.assertNotIn("baseColorTexture", materials[1]["pbrMetallicRoughness"])

    def test_primitives_bind_their_source_materials(self) -> None:
        gltf, _ = self._export(self._studio())
        document = json.loads(gltf.read_text(encoding="utf-8"))
        primitives = document["meshes"][0]["primitives"]
        self.assertEqual(primitives[0]["material"], 0)
        self.assertEqual(primitives[1]["material"], 1)

    def test_image_bytes_round_trip_the_decoded_png(self) -> None:
        """The embedded image is the proved decode, read back byte for byte."""

        gltf, binary = self._export(self._studio())
        document = json.loads(gltf.read_text(encoding="utf-8"))
        payload = binary.read_bytes()

        # Geometry bytes stay byte-identical; images are appended after them.
        self.assertEqual(payload[:len(self.binary)], self.binary)
        self.assertEqual(document["buffers"][0]["byteLength"], len(payload))

        view = document["bufferViews"][document["images"][0]["bufferView"]]
        embedded = payload[view["byteOffset"]:view["byteOffset"] + view["byteLength"]]
        self.assertEqual(embedded, self.png_payload)
        # And the bytes still decode to the exact game RGBA.
        roundtrip_png = self.out / "roundtrip.png"
        roundtrip_png.write_bytes(embedded)
        width, height, rgba = parse_png_rgba(roundtrip_png)
        self.assertEqual((width, height), (1, 1))
        self.assertEqual(rgba, self.rgba)

    def test_the_texture_contract_is_recorded(self) -> None:
        gltf, _ = self._export(self._studio())
        extras = json.loads(gltf.read_text(encoding="utf-8"))["extras"]
        contract = extras["nfl2k5_texture_contract"]
        self.assertEqual(contract["embedded_image_count"], 1)
        self.assertEqual(contract["material_count"], 2)
        self.assertEqual(contract["textured_material_count"], 1)
        self.assertIs(contract["geometry_bytes_preserved"], True)
        self.assertEqual(contract["image_bytes_appended"], len(self.png_payload))
        self.assertEqual(contract["mapping"][0]["texture_id"],
                         f"{self.SCENE_ID}.texture0000")
        self.assertIs(extras["nfl2k5_unit_contract"]["buffer_rewritten"], False)

    def test_a_scene_without_texture_rows_stays_byte_identical(self) -> None:
        data = json.loads(self.texture_manifest.read_text(encoding="utf-8"))
        for row in (*data["materials"], *data["occurrences"]):
            row["scene_index"] = 999
        self.texture_manifest.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        gltf, binary = self._export(self._studio())
        document = json.loads(gltf.read_text(encoding="utf-8"))
        self.assertEqual(binary.read_bytes(), self.binary)
        for section in ("materials", "images", "textures", "samplers"):
            self.assertNotIn(section, document)

    def test_refuses_a_gltf_that_already_declares_materials(self) -> None:
        document = json.loads(
            (self.models / "0042_0003_stadium.gltf").read_text(encoding="utf-8")
        )
        document["materials"] = [{"name": "existing"}]
        payload = (json.dumps(document, indent=2) + "\n").encode("utf-8")
        (self.models / "0042_0003_stadium.gltf").write_bytes(payload)
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["exports"][0]["gltf_sha256"] = digest(payload)
        self.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(ValidationError, "already declares materials"):
            self._export(self._studio())


class StadiumGltfTextureWriteBackTests(StadiumGltfTextureEmbeddingTests):
    """F3: Blender-edited glTF images map back onto the P8 writer route."""

    def _edited_pair(
        self, new_png: bytes, *, strip_extras: bool = False, data_uri: bool = False
    ) -> Path:
        """Simulate a Blender re-export with one replaced image."""

        gltf, binary = self._export(self._studio())
        document = json.loads(gltf.read_text(encoding="utf-8"))
        payload = binary.read_bytes()
        view = document["bufferViews"][document["images"][0]["bufferView"]]
        geometry = payload[:view["byteOffset"]]

        edited_dir = self.root / "blender"
        edited_dir.mkdir(exist_ok=True)
        edited_gltf = edited_dir / "stadium_edited.gltf"
        if data_uri:
            document["images"][0].pop("bufferView", None)
            document["images"][0]["uri"] = (
                "data:image/png;base64," + base64.b64encode(new_png).decode("ascii")
            )
            document["buffers"][0]["byteLength"] = len(geometry)
            (edited_dir / binary.name).write_bytes(geometry)
        else:
            view_index = document["images"][0]["bufferView"]
            document["bufferViews"][view_index] = {
                "buffer": 0,
                "byteOffset": len(geometry),
                "byteLength": len(new_png),
            }
            document["buffers"][0]["byteLength"] = len(geometry) + len(new_png)
            (edited_dir / binary.name).write_bytes(geometry + new_png)
        if strip_extras:
            for section in ("materials", "textures", "images"):
                for row in document.get(section, []):
                    row.pop("extras", None)
        edited_gltf.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return edited_gltf

    def test_edited_image_writes_back_through_the_p8_route(self) -> None:
        replacement = one_pixel_png(bytes((1, 2, 3, 255)))
        edited = self._edited_pair(replacement)
        delegate = RecordingTextureDelegate()
        results = self._studio(delegate).replace_textures_from_gltf(
            self.SCENE_ID, edited
        )
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.texture_id, f"{self.SCENE_ID}.texture0000")
        self.assertEqual(result.write_result, "replaced")
        self.assertEqual(result.supplied_png_sha256, digest(replacement))
        self.assertEqual(delegate.supplied[result.texture_id], replacement)

    def test_material_names_still_map_when_extras_are_stripped(self) -> None:
        replacement = one_pixel_png(bytes((9, 9, 9, 255)))
        edited = self._edited_pair(replacement, strip_extras=True)
        delegate = RecordingTextureDelegate()
        results = self._studio(delegate).replace_textures_from_gltf(
            self.SCENE_ID, edited
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(
            delegate.supplied[f"{self.SCENE_ID}.texture0000"], replacement
        )

    def test_data_uri_images_are_accepted(self) -> None:
        replacement = one_pixel_png(bytes((7, 8, 9, 255)))
        edited = self._edited_pair(replacement, data_uri=True)
        delegate = RecordingTextureDelegate()
        results = self._studio(delegate).replace_textures_from_gltf(
            self.SCENE_ID, edited
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(
            delegate.supplied[f"{self.SCENE_ID}.texture0000"], replacement
        )

    def test_unmapped_gltf_is_refused(self) -> None:
        replacement = one_pixel_png(bytes((5, 5, 5, 255)))
        edited = self._edited_pair(replacement)
        document = json.loads(edited.read_text(encoding="utf-8"))
        for row in document["materials"]:
            row["name"] = "not_a_stadium_material"
            row.pop("extras", None)
        for section in ("textures", "images"):
            for row in document[section]:
                row.pop("extras", None)
        edited.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "no editable stadium texture"):
            self._studio(RecordingTextureDelegate()).replace_textures_from_gltf(
                self.SCENE_ID, edited
            )

    def test_without_a_writer_the_write_back_is_honest(self) -> None:
        replacement = one_pixel_png(bytes((4, 4, 4, 255)))
        edited = self._edited_pair(replacement)
        with self.assertRaises(ActionNotImplementedError):
            self._studio().replace_textures_from_gltf(self.SCENE_ID, edited)

    def test_conflicting_images_for_one_texture_are_refused(self) -> None:
        replacement = one_pixel_png(bytes((2, 2, 2, 255)))
        edited = self._edited_pair(replacement)
        document = json.loads(edited.read_text(encoding="utf-8"))
        texture_id = f"{self.SCENE_ID}.texture0000"
        other = one_pixel_png(bytes((3, 3, 3, 255)))
        # A second material bound to a second image carrying other bytes but
        # claiming the same stadium texture slot.
        document["bufferViews"].append({
            "buffer": 0,
            "byteOffset": document["buffers"][0]["byteLength"],
            "byteLength": len(other),
        })
        document["images"].append({
            "name": "wall_art_copy",
            "bufferView": len(document["bufferViews"]) - 1,
            "mimeType": "image/png",
            "extras": {"nfl2k5_texture_id": texture_id},
        })
        document["textures"].append({
            "name": "wall_art_copy",
            "sampler": 0,
            "source": len(document["images"]) - 1,
        })
        document["materials"].append({
            "name": "wall_art_copy",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": len(document["textures"]) - 1}
            },
            "extras": {"nfl2k5_texture_id": texture_id},
        })
        document["buffers"][0]["byteLength"] += len(other)
        binary_path = edited.parent / document["buffers"][0]["uri"]
        binary_path.write_bytes(binary_path.read_bytes() + other)
        edited.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "disagrees with itself"):
            self._studio(RecordingTextureDelegate()).replace_textures_from_gltf(
                self.SCENE_ID, edited
            )


if __name__ == "__main__":
    unittest.main()
