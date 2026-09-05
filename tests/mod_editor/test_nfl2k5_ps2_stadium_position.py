"""Bounded PS2 stadium geometry editing: the writer, the catalogue, the verifier.

Every fixture here is synthetic.  A tiny SLUS-20919-shaped ISO9660 volume
carries one ``/VC_20919/0.`` pack, which carries one VC-LZ compressed SCNE
resource, which carries one shape with two DMA/VIF geometry batches.  No game
data is needed and none is produced.

The interesting tests are the negative ones.  A writer that only ever succeeds
proves nothing, so this asserts that the verifier rejects a byte changed
outside the declared position lanes, that the writer refuses a changed vertex
count, and that when the recompressed stream cannot fit the chunk's fixed
stored body the writer refuses *and leaves no output image behind*.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _REPO_ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl2k5_ps2_stadium_position_patch as patcher  # noqa: E402
import nfl2k5_ps2_stadium_position_verify as verifier  # noqa: E402
import nfl2k5_ps2_stadium_target_catalog as catalog_tool  # noqa: E402


def _write(path: Path, payload: bytes) -> Path:
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


class _Disc:
    """A synthetic source ISO plus its catalogue, in a scratch directory."""

    def __init__(self, root: Path, **kwargs) -> None:
        self.root = root
        self.source = _write(root / "source.iso",
                             patcher.build_synthetic_disc(**kwargs))
        self.document = catalog_tool.catalog(str(self.source), [(0, None)],
                                             False, None, True)
        self.catalog = _write(root / "catalog.json",
                              catalog_tool.canonical_json(self.document))
        self.catalog_sha = patcher.load_catalog(str(self.catalog))["sha256"]
        self.targets = self.document["targets"]

    def recipe(self, name: str, edits) -> Path:
        path = self.root / name
        patcher.write_recipe(str(path), self.catalog_sha, edits)
        return path

    def moved(self, target, delta: float = 1.0):
        count = target["position"]["vertex_count"]
        return [(11.0 + index * delta, 21.0, 29.0 - index * delta)
                for index in range(count)]


class Ps2StadiumPositionTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="ps2-stadium-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    # -- the catalogue -----------------------------------------------------

    def test_catalog_selftest_passes(self) -> None:
        self.assertEqual(0, catalog_tool.selftest())

    def test_verifier_selftest_passes(self) -> None:
        self.assertEqual(0, verifier.selftest())

    def test_catalog_finds_both_batches_of_the_synthetic_scene(self) -> None:
        disc = _Disc(self.root)
        summary = disc.document["summary"]
        self.assertEqual(1, summary["scenes"])
        self.assertEqual(1, summary["shapes"])
        self.assertEqual(2, summary["batches"])
        self.assertEqual(2, summary["target_count"])
        self.assertEqual([4, 6],
                         [t["position"]["vertex_count"] for t in disc.targets])
        common = disc.document["target_common"]
        self.assertEqual("vif_unpack_v4_32", common["position_encoding"])
        self.assertEqual(16, common["element_stride"])
        self.assertEqual(12, common["lane_size"])
        self.assertTrue(common["w_component_preserved"])
        self.assertFalse(common["eligibility"]["runtime_visibility_proved"])
        for target in disc.targets:
            self.assertTrue(target["eligible"])
            self.assertLessEqual(target["max_distance_over_radius"], 1.0001)
            self.assertEqual(0, target["scene_index"])

    def test_catalog_emits_no_coordinates(self) -> None:
        disc = _Disc(self.root)
        text = disc.catalog.read_text(encoding="utf-8")
        self.assertNotIn("positions", text)
        self.assertFalse(disc.document["data_policy"]
                         ["contains_retail_geometry_or_pixel_bytes"])
        self.assertFalse(disc.document["data_policy"]["contains_position_values"])

    # -- the happy path ----------------------------------------------------

    def test_patch_then_verify_round_trip(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        recipe = disc.recipe("recipe.json",
                             [(target["target_id"], disc.moved(target))])
        output = self.root / "patched.iso"
        report = patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                               str(output), str(self.root / "patch-report.json"))

        self.assertEqual("patched", report["compression"]["mode"])
        self.assertTrue(report["compression"]["wrapper_identical"])
        self.assertEqual(os.stat(disc.source).st_size, os.stat(output).st_size)
        self.assertEqual(target["position"]["vertex_count"] * 12,
                         report["edits"][0]["written_bytes"])
        self.assertTrue(report["decoded_diff"]
                        ["every_changed_byte_inside_a_declared_lane"])
        self.assertFalse(report["claims"]["runtime_visibility_proved"])

        result = verifier.verify(str(disc.source), str(output),
                                 str(disc.catalog), str(recipe))
        self.assertEqual("pass", result["verdict"])
        self.assertEqual("patched", result["mode"])
        self.assertTrue(result["chunk"]["wrapper_identical"])
        self.assertTrue(result["decoded"]["w_component_preserved"])
        self.assertTrue(result["decoded"]["matches_recipe_exactly"])
        self.assertTrue(result["topology"]["vertex_counts_unchanged"])
        self.assertGreater(result["image"]["changed_bytes"], 0)

    def test_two_lanes_in_one_recipe(self) -> None:
        disc = _Disc(self.root)
        recipe = disc.recipe(
            "both.json",
            [(target["target_id"], disc.moved(target, 0.5))
             for target in disc.targets])
        output = self.root / "both.iso"
        report = patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                               str(output))
        self.assertEqual(2, len(report["edits"]))
        result = verifier.verify(str(disc.source), str(output),
                                 str(disc.catalog), str(recipe))
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(10, sum(lane["vertex_count"] for lane in result["lanes"]))

    def test_a_chunk_that_straddles_two_pack_files(self) -> None:
        """The retail layout addresses the packs as one flat byte range.

        A resource may therefore begin in one pack file and end in the next,
        which means the writer has to build two replacement files for one
        edit and the verifier has to read the span across the seam. The
        fixture puts the pack boundary inside the chunk on purpose.
        """
        disc = _Disc(self.root, split_packs=True, scratch=4096, slack_bytes=256)
        layout = verifier.read_iso_packs(str(disc.source))
        self.assertEqual(2, len(layout["packs"]))
        target = disc.targets[0]
        recipe = disc.recipe("straddle.json",
                             [(target["target_id"], disc.moved(target))])
        output = self.root / "straddle.iso"
        report = patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                               str(output))
        self.assertEqual(["/VC_20919/0.", "/VC_20919/1."],
                         [pack["iso_path"] for pack in report["packs"]])
        self.assertEqual(report["scene"]["span_size"],
                         sum(pack["bytes_spliced"] for pack in report["packs"]))

        result = verifier.verify(str(disc.source), str(output),
                                 str(disc.catalog), str(recipe))
        self.assertEqual("pass", result["verdict"])
        self.assertEqual(2, len(result["chunk"]["physical_windows"]))
        self.assertEqual(["0", "1"],
                         [w["pack"] for w in result["chunk"]["physical_windows"]])

    def test_a_no_op_recipe_reproduces_the_source_image_byte_for_byte(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        # Read the source coordinates back out of the synthetic scene so the
        # recipe asks for exactly what is already there.
        payload = target["position"]["payload"]
        decoded = _decode_scene(disc.source)
        current = [struct.unpack_from("<3f", decoded,
                                      payload["offset"] + index * 16)
                   for index in range(target["position"]["vertex_count"])]
        recipe = disc.recipe("noop.json", [(target["target_id"], current)])
        output = self.root / "noop.iso"
        report = patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                               str(output))
        self.assertEqual("no_op", report["compression"]["mode"])
        self.assertEqual(disc.source.read_bytes(), output.read_bytes())
        result = verifier.verify(str(disc.source), str(output),
                                 str(disc.catalog), str(recipe))
        self.assertEqual("no_op", result["mode"])
        self.assertEqual(0, result["image"]["changed_bytes"])

    # -- the verifier must catch what the writer must not do ---------------

    def test_verifier_fails_when_a_byte_outside_the_lanes_is_mutated(self) -> None:
        """An honest edit plus one extra decoded byte must be rejected.

        This does not go through the writer -- the writer refuses this before
        it compresses anything. It builds the image the writer would have to
        be broken to produce: the recipe's coordinates in the declared lanes,
        and one byte changed outside them, recompressed into the same fixed
        span with the same wrapper. Nothing about the container is wrong; only
        the containment claim is, and that is what the verifier must catch.
        """
        disc = _Disc(self.root)
        target = disc.targets[0]
        recipe = disc.recipe("recipe.json",
                             [(target["target_id"], disc.moved(target))])
        honest = self.root / "patched.iso"
        patcher.patch(str(disc.source), str(disc.catalog), str(recipe), str(honest))
        self.assertEqual("pass",
                         verifier.verify(str(disc.source), str(honest),
                                         str(disc.catalog), str(recipe))["verdict"])

        payload = target["position"]["payload"]
        # The fourth component of vertex 0: inside the payload, outside every
        # declared 12-byte lane, and the writer promises to carry it over.
        for extra in (payload["offset"] + 12, payload["offset"] - 4):
            tampered = _forge_image(disc, recipe, self.root / ("forged%d.iso" % extra),
                                    extra)
            with self.assertRaises(verifier.VerifyError):
                verifier.verify(str(disc.source), str(tampered),
                                str(disc.catalog), str(recipe))

    def test_verifier_fails_when_a_byte_outside_the_chunk_span_is_mutated(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        recipe = disc.recipe("recipe.json",
                             [(target["target_id"], disc.moved(target))])
        output = self.root / "patched.iso"
        patcher.patch(str(disc.source), str(disc.catalog), str(recipe), str(output))

        tampered = self.root / "outside.iso"
        shutil.copyfile(output, tampered)
        layout = verifier.read_iso_packs(str(tampered))
        # The last byte of the pack extent is far past the chunk's fixed span.
        offset = layout["packs"][0]["byte_offset"] + layout["packs"][0]["length"] - 1
        with open(tampered, "r+b") as handle:
            handle.seek(offset)
            original = handle.read(1)
            handle.seek(offset)
            handle.write(bytes([original[0] ^ 0xFF]))
        with self.assertRaisesRegex(verifier.VerifyError, "outside the declared"):
            verifier.verify(str(disc.source), str(tampered), str(disc.catalog),
                            str(recipe))

    def test_verifier_fails_when_the_wrapper_scratch_word_moves(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        recipe = disc.recipe("recipe.json",
                             [(target["target_id"], disc.moved(target))])
        output = self.root / "patched.iso"
        patcher.patch(str(disc.source), str(disc.catalog), str(recipe), str(output))

        tampered = self.root / "scratch.iso"
        shutil.copyfile(output, tampered)
        identity = disc.document["scenes"][target["scene_index"]]["identity"]
        with open(tampered, "rb") as handle:
            layout = verifier.read_iso_packs(str(tampered))
            table = verifier.read_outer_table(handle, layout["packs"])
        base = table[identity["entry_index"]][2] * verifier.ALIGNMENT
        wrapper = layout["packs"][0]["byte_offset"] + base + identity["chunk_offset"]
        with open(tampered, "r+b") as handle:
            handle.seek(wrapper + 0x14)
            handle.write(struct.pack("<I", 0xB0))
        with self.assertRaisesRegex(verifier.VerifyError, "wrapper changed"):
            verifier.verify(str(disc.source), str(tampered), str(disc.catalog),
                            str(recipe))

    # -- the writer must refuse --------------------------------------------

    def test_patcher_refuses_a_changed_vertex_count(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        short = disc.moved(target)[:-1]
        recipe = disc.recipe("short.json", [(target["target_id"], short)])
        output = self.root / "never.iso"
        with self.assertRaisesRegex(patcher.PatchError, "exactly .* vertices"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertFalse(output.exists())

        longer = disc.moved(target) + [(1.0, 2.0, 3.0)]
        recipe = disc.recipe("long.json", [(target["target_id"], longer)])
        with self.assertRaisesRegex(patcher.PatchError, "exactly .* vertices"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertFalse(output.exists())

    def test_patcher_refuses_a_coordinate_that_is_not_exactly_binary32(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        positions = disc.moved(target)
        positions[0] = (0.1, 21.0, 29.0)          # not representable in binary32
        recipe = disc.recipe("inexact.json", [(target["target_id"], positions)])
        output = self.root / "never.iso"
        with self.assertRaisesRegex(patcher.PatchError, "binary32"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertFalse(output.exists())

    def test_patcher_refuses_a_target_the_catalog_does_not_authorise(self) -> None:
        disc = _Disc(self.root)
        recipe = disc.recipe(
            "unknown.json",
            [("nfl2k5ps2/stadium/e0/c0/s0/b9/l0", [(1.0, 2.0, 3.0)])])
        output = self.root / "never.iso"
        with self.assertRaisesRegex(patcher.PatchError, "not authorised"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertFalse(output.exists())

    def test_patcher_refuses_a_recipe_pinned_to_another_catalog(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        path = self.root / "wrongpin.json"
        patcher.write_recipe(str(path), "0" * 64,
                             [(target["target_id"], disc.moved(target))])
        output = self.root / "never.iso"
        with self.assertRaisesRegex(patcher.PatchError, "different catalog"):
            patcher.patch(str(disc.source), str(disc.catalog), str(path),
                          str(output))
        self.assertFalse(output.exists())

    def test_patcher_refuses_when_recompression_does_not_fit(self) -> None:
        """The stored body has no spare bytes and the edit destroys the match.

        The fixture's positions are all identical, so the payload packs into
        one long run.  Making every vertex distinct forces the stream to grow
        past a stored body that had nothing spare, and the writer must refuse
        before the destination image exists.
        """
        disc = _Disc(self.root, vertex_counts=(64,), slack_bytes=0, scratch=16,
                     uniform_positions=True)
        target = disc.targets[0]
        positions = [(1000.0 + index * 3.0, 2000.0 - index * 7.0,
                      3000.0 + index * 11.0)
                     for index in range(target["position"]["vertex_count"])]
        recipe = disc.recipe("overflow.json", [(target["target_id"], positions)])
        output = self.root / "overflow.iso"
        with self.assertRaisesRegex(patcher.PatchError, "fixed .*stored body"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertFalse(output.exists())

    def test_patcher_refuses_to_overwrite_an_existing_output(self) -> None:
        disc = _Disc(self.root)
        target = disc.targets[0]
        recipe = disc.recipe("recipe.json",
                             [(target["target_id"], disc.moved(target))])
        output = _write(self.root / "taken.iso", b"already here")
        with self.assertRaisesRegex(patcher.PatchError, "existing output"):
            patcher.patch(str(disc.source), str(disc.catalog), str(recipe),
                          str(output))
        self.assertEqual(b"already here", output.read_bytes())

    def test_patcher_refuses_edits_spanning_two_scenes(self) -> None:
        disc = _Disc(self.root)
        forged = json.loads(disc.catalog.read_text(encoding="utf-8"))
        second_scene = json.loads(json.dumps(forged["scenes"][0]))
        second_scene["scene_index"] = 1
        second_scene["identity"] = dict(second_scene["identity"], entry_index=1)
        forged["scenes"].append(second_scene)
        second = json.loads(json.dumps(forged["targets"][1]))
        second["target_id"] = "nfl2k5ps2/stadium/e1/c0/s0/b0/l0"
        second["scene_index"] = 1
        forged["targets"].append(second)
        forged_path = _write(self.root / "forged.json",
                             catalog_tool.canonical_json(forged))
        sha = patcher.load_catalog(str(forged_path))["sha256"]
        path = self.root / "twoscenes.json"
        patcher.write_recipe(
            str(path), sha,
            [(disc.targets[0]["target_id"], disc.moved(disc.targets[0])),
             (second["target_id"], disc.moved(second))])
        output = self.root / "never.iso"
        with self.assertRaisesRegex(patcher.PatchError, "different SCNE chunk"):
            patcher.patch(str(disc.source), str(forged_path), str(path),
                          str(output))
        self.assertFalse(output.exists())

    # -- the walkers agree -------------------------------------------------

    def test_writer_and_verifier_walkers_agree_on_the_synthetic_scene(self) -> None:
        disc = _Disc(self.root)
        decoded = _decode_scene(disc.source)
        system_bytes = disc.document["scenes"][0]["identity"]["system_bytes"]
        system = decoded[:system_bytes]
        for target in disc.targets:
            address = verifier._parse_target_id(target["target_id"])
            lanes = verifier.scene_lanes(system, address["s"], address["b"])
            found = lanes[address["l"]]["lane"]
            self.assertEqual(target["position"]["vertex_count"], found["num"])
            self.assertEqual(target["position"]["payload"]["offset"],
                             found["data_offset"])
            self.assertEqual(target["position"]["payload"]["size"],
                             found["data_bytes"])


# ---------------------------------------------------------------------------
# helpers that read the synthetic disc without going through the writer
# ---------------------------------------------------------------------------

def _decode_scene(iso_path: Path) -> bytes:
    layout = verifier.read_iso_packs(str(iso_path))
    with open(iso_path, "rb") as handle:
        table = verifier.read_outer_table(handle, layout["packs"])
        base = table[0][2] * verifier.ALIGNMENT
        header = verifier._virtual_read(handle, layout["packs"], base,
                                        verifier.CHUNK_HEADER)
        stored, system_bytes, video_bytes = struct.unpack_from("<3I", header, 4)
        body = verifier._virtual_read(handle, layout["packs"],
                                      base + verifier.CHUNK_HEADER, stored)
    decoded, _consumed = verifier.decompress(body, system_bytes + video_bytes)
    return decoded


def _chunk_image_offset(iso_path: Path, identity: dict) -> int:
    """The absolute byte offset of a chunk's fixed span inside the image."""
    layout = verifier.read_iso_packs(str(iso_path))
    with open(iso_path, "rb") as handle:
        table = verifier.read_outer_table(handle, layout["packs"])
    base = table[identity["entry_index"]][2] * verifier.ALIGNMENT
    return (layout["packs"][0]["byte_offset"] + base + identity["chunk_offset"])


def _forge_image(disc: "_Disc", recipe: Path, destination: Path,
                 extra_decoded_offset: int) -> Path:
    """Build the image a broken writer would produce, bypassing the writer.

    The recipe's coordinates go into the declared lanes and one further
    decoded byte is flipped, then the whole scene is recompressed into the
    same fixed span with the same wrapper and spliced into a copy of the
    source. The container stays perfectly well formed.
    """
    import nfl_vc_lz_fill as vclz
    import nfl_txtr as txtr

    loaded = patcher.load_catalog(str(disc.catalog))
    parsed = patcher.load_recipe(str(recipe), loaded)
    decoded = bytearray(_decode_scene(disc.source))
    for edit in parsed["edits"]:
        start = edit["row"]["position"]["payload"]["offset"]
        for vertex, triple in enumerate(edit["positions"]):
            struct.pack_into("<3f", decoded, start + vertex * 16, *triple)
    decoded[extra_decoded_offset] ^= 0xFF

    identity = parsed["identity"]
    offset = _chunk_image_offset(disc.source, identity)
    with open(disc.source, "rb") as handle:
        handle.seek(offset)
        header = handle.read(verifier.CHUNK_HEADER)
        stored = struct.unpack_from("<I", header, 4)[0]
        handle.seek(offset)
        span = handle.read(verifier.CHUNK_HEADER + stored)
    rebuilt, _info = vclz.rebuild_fixed_span_filled(span, bytes(decoded),
                                                    encoder="auto")
    assert len(rebuilt) == len(span)
    assert rebuilt[:verifier.CHUNK_HEADER] == span[:verifier.CHUNK_HEADER]
    shutil.copyfile(disc.source, destination)
    with open(destination, "r+b") as handle:
        handle.seek(offset)
        handle.write(rebuilt)
    return destination


if __name__ == "__main__":
    unittest.main()
