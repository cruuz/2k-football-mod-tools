"""Exported stadium glTF must arrive in metres without rewriting the buffer.

A modder reported "I'm not sure if the gltf is loading correctly on blender" with
a screenshot of a mesh swallowing the whole viewport. APF authors geometry in
centimetres and glTF's unit is the metre, so an unscaled export lands a hundred
times too large -- a stadium reaches ~17,759 units across, well past Blender's
default 1000 m clip distance.

The conversion is a root node, deliberately, not a rewritten buffer:

* ``scene.bin`` is byte-identical game data and the static topology conformance
  spec depends on it staying that way.
* The position writer's recipe declares ``coordinate_space`` as a const,
  ``serialized_scne_object_space``. Pre-scaling the buffer would put the export
  and the writer in different spaces.

That choice has a cost worth pinning: anything read back out of a viewer is in
metres while a recipe must be in raw object space, so ``asset.extras`` records
the exact factor rather than leaving it to be guessed. These tests check the
wrapper is complete (nothing escapes it), that the buffer really is untouched,
and that the declaration matches what the wrapper actually does -- metadata
asserting a conversion that was not applied would be worse than none.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import apf_scene  # noqa: E402

_INDEX = _REPO_ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
#: The stadium scene the position writer targets.
_OUTER, _INNER = 14, 8


def _export():
    import apf_inner
    import apf_outer

    archive = apf_outer.parse_archive(_INDEX)
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, archive.entries[_OUTER])
        inner = record.files[_INNER]
        part = inner.parts[0]
        blob = apf_inner.decode_block(reader, record, part.block_index, 1 << 30)
        data = blob[part.offset:part.offset + part.length]
        scene = apf_scene.parse_scene_system_part(
            data, outer_index=_OUTER, inner_index=_INNER, capture_geometry=True)
    directory = tempfile.mkdtemp()
    gltf = Path(directory) / "scene.gltf"
    binary = Path(directory) / "scene.bin"
    apf_scene.write_gltf_collection(gltf, binary, scene, _OUTER, _INNER)
    return json.loads(gltf.read_text(encoding="utf-8")), binary.read_bytes()


class UnitContractTests(unittest.TestCase):
    """These need no game data."""

    def test_the_scale_is_centimetres_to_metres(self) -> None:
        self.assertEqual(apf_scene.UNIT_SCALE, 0.01)

    def test_the_declaration_matches_the_node_it_describes(self) -> None:
        contract = apf_scene._unit_contract()
        root = apf_scene._unit_root("demo", [0])
        self.assertEqual(contract["linear_scale"], apf_scene.UNIT_SCALE)
        self.assertEqual(root["scale"], [apf_scene.UNIT_SCALE] * 3)
        self.assertEqual(contract["source_linear_unit"], "centimeter")
        self.assertEqual(contract["target_linear_unit"], "meter")

    def test_the_declaration_says_the_buffer_is_untouched(self) -> None:
        contract = apf_scene._unit_contract()
        self.assertIn("unmodified", str(contract["applied_as"]))
        self.assertEqual(contract["buffer_space"], "serialized_scne_object_space")

    def test_the_recipe_trap_is_spelled_out(self) -> None:
        """A silent 100x error in someone's stadium edit is the risk here."""

        note = str(apf_scene._unit_contract()["recipe_note"])
        self.assertIn("serialized_scne_object_space", note)
        self.assertIn("linear_scale", note)

    def test_the_root_adds_no_transform_of_its_own(self) -> None:
        root = apf_scene._unit_root("demo", [0, 1, 2])
        self.assertEqual(root["children"], [0, 1, 2])
        self.assertNotIn("translation", root)
        self.assertNotIn("rotation", root)
        self.assertNotIn("matrix", root)


@unittest.skipUnless(_INDEX.is_file(), "extracted APF 0A not present")
class ExportedStadiumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document, cls.binary = _export()

    def test_the_scene_has_exactly_one_root_and_it_scales(self) -> None:
        roots = self.document["scenes"][0]["nodes"]
        self.assertEqual(len(roots), 1)
        root = self.document["nodes"][roots[0]]
        self.assertEqual(root["scale"], [0.01, 0.01, 0.01])

    def test_every_mesh_node_is_under_the_root(self) -> None:
        """A node left outside would silently stay 100x too large."""

        nodes = self.document["nodes"]
        root_index = self.document["scenes"][0]["nodes"][0]
        children = sorted(nodes[root_index]["children"])
        self.assertEqual(children, [i for i in range(len(nodes)) if i != root_index])
        for index in children:
            self.assertIn("mesh", nodes[index])

    def test_the_buffer_is_still_raw_centimetres(self) -> None:
        """The whole point of a wrapper: game bytes go out unmodified."""

        accessor = self.document["accessors"][0]
        self.assertEqual(accessor["type"], "VEC3")
        # A stadium is on the order of 10,000+ units across in centimetres. If
        # anything pre-scaled the buffer these would be ~100x smaller.
        self.assertGreater(max(abs(v) for v in accessor["max"]), 1_000)

    def test_the_document_declares_the_conversion(self) -> None:
        contract = self.document["asset"]["extras"]["coordinate_contract"]
        self.assertEqual(contract["linear_scale"], 0.01)
        self.assertEqual(contract["buffer_space"], "serialized_scne_object_space")

    def test_mesh_nodes_still_state_their_coordinates_are_raw(self) -> None:
        nodes = self.document["nodes"]
        root_index = self.document["scenes"][0]["nodes"][0]
        sample = nodes[0 if root_index != 0 else 1]
        self.assertTrue(sample["extras"]["raw_coordinates"])
        self.assertTrue(sample["extras"]["source_raw_coordinates"])

    def test_scaled_extent_is_a_plausible_stadium_in_metres(self) -> None:
        """The reported symptom, checked as a number rather than a screenshot."""

        accessor = self.document["accessors"][0]
        widest = max(
            accessor["max"][i] - accessor["min"][i] for i in range(3)
        ) * apf_scene.UNIT_SCALE
        # A stadium is tens to a few hundred metres, not tens of thousands.
        self.assertGreater(widest, 20.0)
        self.assertLess(widest, 1_000.0)


if __name__ == "__main__":
    unittest.main()
