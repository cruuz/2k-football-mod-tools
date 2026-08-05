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

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_stadium_studio import (  # noqa: E402
    GLTF_UNIT_SCALE,
    Nfl2k5StadiumStudio,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


if __name__ == "__main__":
    unittest.main()
