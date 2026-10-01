"""Presentation scene textures (beta 76 p2): the raw MRKS transport adapter and the fixed-span SCNE refit.

Synthetic scenes (tests/mod_editor/presentation_scene_fixture.py) cover the adapter's round trips and
refusals without game data; when the extracted retail packs are present, the six resources of the ESPN 2026
wipes and boards option are compiled from their real spans and every byte outside the targeted descriptors'
allocations is checked unchanged.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", Path(__file__).resolve().parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_presentation_scenes as scenes  # noqa: E402
from mod_editor.core import nfl2k5_stadium_texture_writer as stadium  # noqa: E402
import presentation_scene_fixture as fixture  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
import nfl_txtr as txtr  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def png(folder: Path, name: str, width: int, height: int, pixel) -> Path:
    path = folder / name
    path.write_bytes(txtr.encode_rgba_png(width, height, b"".join(bytes(pixel(x, y)) for y in range(height)
                                                                  for x in range(width))))
    return path


def outside_equal(before: bytes, after: bytes, ranges) -> bool:
    cursor = 0
    for start, end in sorted(ranges):
        if before[cursor:start] != after[cursor:start]:
            return False
        cursor = end
    return before[cursor:] == after[cursor:]


class SceneViewTests(unittest.TestCase):
    def test_the_view_repoints_only_the_mrks_header(self) -> None:
        decoded, _system = fixture.scene_decoded("MRKS", [(32, 32, 1, ["glow"])])
        view = scenes.scene_view(decoded, "MRKS")
        changed = [i for i, (a, b) in enumerate(zip(decoded, view)) if a != b]
        self.assertTrue(changed and all(12 <= i < 16 or 20 <= i < 24 for i in changed))
        self.assertEqual(view[12:16], b"SCNE")
        self.assertEqual(scenes.scene_view(view, "SCNE"), view)
        broken = bytearray(decoded)
        struct.pack_into("<i", broken, 20, 17)
        with self.assertRaisesRegex(scenes.PresentationSceneError, "wrapper descriptor drift"):
            scenes.scene_view(bytes(broken), "MRKS")
        with self.assertRaisesRegex(scenes.PresentationSceneError, "not a presentation scene"):
            scenes.scene_view(decoded, "TXTR")


class RawAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="presentation-scenes-")
        self.root = Path(self.temp.name)
        self.decoded, self.system = fixture.scene_decoded(
            "MRKS", [(32, 32, 1, ["pattern_flash"]), (16, 8, 2, ["white_streak", "yellow_streak"]),
                     (64, 32, 1, ["logo_glow"])])
        self.span = fixture.raw_span(self.decoded, self.system)
        self.resource = scenes.open_resource(self.span, outer_index=3114, chunk_index=1, chunk_offset=124160)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_raw_resource_parses(self) -> None:
        self.assertTrue(self.resource.raw)
        self.assertEqual((self.resource.kind, self.resource.consumed, self.resource.opaque_tail), ("MRKS", len(self.decoded), b""))
        rows = scenes.descriptor_summary(self.resource)
        self.assertEqual([(r["width"], r["height"], r["mip_levels"], r["contiguous"]) for r in rows],
                         [(32, 32, 1, True), (16, 8, 2, True), (64, 32, 1, True)])
        self.assertEqual(rows[1]["materials"], ["white_streak", "yellow_streak"])

    def test_one_descriptor_changes_and_nothing_else(self) -> None:
        art = png(self.root, "streak.png", 16, 8, lambda x, y: (200, 20 + 20 * y, 30, 255 if y % 3 else 120))
        new, receipt = scenes.compile_raw(self.resource, [(1, art)])
        self.assertEqual((len(new), new[:32]), (len(self.span), self.span[:32]))
        row = receipt["textures"][0]
        ranges = [(row["decoded_pixel_offset"], row["decoded_pixel_offset"] + row["index_bytes"]),
                  (row["decoded_palette_offset"], row["decoded_palette_offset"] + 1024)]
        self.assertTrue(outside_equal(self.decoded, new[32:], ranges))
        self.assertNotEqual(self.decoded, new[32:])
        self.assertEqual(new[32:32 + self.system], self.decoded[:self.system])
        again = scenes.open_resource(new, outer_index=3114, chunk_index=1, chunk_offset=124160)
        width, height, rgba = scenes.texture_rgba(again, 1)
        self.assertEqual(rgba, decode_rgba_png(art.read_bytes(), (16, 8))[2])
        self.assertEqual(scenes.descriptor_summary(again), scenes.descriptor_summary(self.resource))
        self.assertEqual((receipt["scratch_before"], receipt["scratch_after"], receipt["archive_growth"]), (0, 0, 0))
        self.assertEqual(len(row["mip_rgba_sha256"]), 2)
        self.assertTrue(row["base_rgba_exact"])
        self.assertIs(receipt["runtime_witnessed"], False)

    def test_every_descriptor_at_once(self) -> None:
        arts = [(0, png(self.root, "a.png", 32, 32, lambda x, y: (230, 230, 240, (x * 8) % 256))),
                (1, png(self.root, "b.png", 16, 8, lambda x, y: (150, 10, 20, 255))),
                (2, png(self.root, "c.png", 64, 32, lambda x, y: (190, 15 + x, 25, 255 if (x + y) % 5 else 0)))]
        new, receipt = scenes.compile_raw(self.resource, arts)
        ranges = [(t["decoded_pixel_offset"], t["decoded_pixel_offset"] + t["index_bytes"]) for t in receipt["textures"]]
        ranges += [(t["decoded_palette_offset"], t["decoded_palette_offset"] + 1024) for t in receipt["textures"]]
        self.assertTrue(outside_equal(self.decoded, new[32:], ranges))
        again = scenes.open_resource(new, outer_index=3114, chunk_index=1)
        for index, path in arts:
            width, height, rgba = scenes.texture_rgba(again, index)
            self.assertEqual(rgba, decode_rgba_png(path.read_bytes(), (width, height))[2], index)
        # compiling the same art again is deterministic
        self.assertEqual(scenes.compile_raw(self.resource, arts)[0], new)

    def test_refusals(self) -> None:
        good = png(self.root, "ok.png", 32, 32, lambda x, y: (1, 2, 3, 255))
        wrong = png(self.root, "wrong.png", 16, 16, lambda x, y: (1, 2, 3, 255))
        with self.assertRaisesRegex(scenes.PresentationSceneError, "repeats"):
            scenes.compile_raw(self.resource, [(0, good), (0, good)])
        with self.assertRaises(scenes.PresentationSceneError):
            scenes.compile_raw(self.resource, [(0, wrong)])
        with self.assertRaisesRegex(scenes.PresentationSceneError, "outside this scene's texture table"):
            scenes.compile_raw(self.resource, [(7, good)])
        with self.assertRaisesRegex(scenes.PresentationSceneError, "no presentation texture edits"):
            scenes.compile_raw(self.resource, [])
        gap, system = fixture.scene_decoded("MRKS", [(32, 32, 1, ["gap"])], palette_gap=512)
        refused = scenes.open_resource(fixture.raw_span(gap, system), outer_index=3114, chunk_index=2)
        with self.assertRaises(scenes.PresentationSceneError):
            scenes.compile_raw(refused, [(0, good)])
        compressed_decoded, compressed_system = fixture.scene_decoded("SCNE", [(32, 32, 1, ["sign"])])
        compressed = scenes.open_resource(fixture.compressed_span(compressed_decoded, compressed_system),
                                          outer_index=347, chunk_index=5)
        with self.assertRaisesRegex(scenes.PresentationSceneError, "compressed"):
            scenes.compile_raw(compressed, [(0, good)])
        with self.assertRaisesRegex(scenes.PresentationSceneError, "not an MRKS or SCNE"):
            scenes.open_resource(txtr.HEADER.pack(b"TXTR", 0, 0, 0, 0, 0, 0, 0), outer_index=1)
        truncated = self.span[:-4]
        with self.assertRaisesRegex(scenes.PresentationSceneError, "does not match its wrapper"):
            scenes.open_resource(truncated, outer_index=3114)
        scratched = bytearray(self.span)
        struct.pack_into("<I", scratched, 0x14, 16)
        with self.assertRaisesRegex(scenes.PresentationSceneError, "no scratch"):
            scenes.open_resource(bytes(scratched), outer_index=3114)


class CompressedRefitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="presentation-scenes-lz-")
        self.root = Path(self.temp.name)
        self.decoded, self.system = fixture.scene_decoded(
            "SCNE", [(64, 64, 3, ["sign02"]), (32, 32, 1, ["dot"]), (64, 64, 1, ["backboard"])], seed=11)
        self.tail = b"\x13" * 9
        self.span = fixture.compressed_span(self.decoded, self.system, tail=self.tail)
        self.resource = scenes.open_resource(self.span, outer_index=347, chunk_index=5)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_refit_keeps_wrapper_scratch_and_tail(self) -> None:
        art = png(self.root, "sign.png", 64, 64, lambda x, y: (32, 31, 32, 255) if (x // 8 + y // 8) % 2 else (190, 15, 25, 255))
        new, receipt = scenes.compile_compressed(self.resource, [(0, art)])
        self.assertEqual((len(new), new[:32], new[-len(self.tail):]), (len(self.span), self.span[:32], self.tail))
        self.assertEqual(receipt["encoded_bytes"] + receipt["zero_gap_bytes"], receipt["retail_consumed"])
        self.assertLessEqual(receipt["minimum_scratch"], receipt["scratch_after"])
        self.assertEqual(receipt["scratch_after"], struct.unpack_from("<I", self.span, 0x14)[0])
        again = scenes.open_resource(new, outer_index=347, chunk_index=5)
        row = receipt["textures"][0]
        ranges = [(row["decoded_pixel_offset"], row["decoded_pixel_offset"] + row["index_bytes"]),
                  (row["decoded_palette_offset"], row["decoded_palette_offset"] + 1024)]
        self.assertTrue(outside_equal(self.decoded, again.decoded, ranges))
        width, height, rgba = scenes.texture_rgba(again, 0)
        self.assertEqual(rgba, decode_rgba_png(art.read_bytes(), (64, 64))[2])
        self.assertEqual(len(row["mip_rgba_sha256"]), 3)
        self.assertEqual(scenes.descriptor_summary(again), scenes.descriptor_summary(self.resource))

    def test_the_stadium_compiler_writes_the_same_decoded_bytes(self) -> None:
        art = png(self.root, "tile.png", 32, 32, lambda x, y: (42, 50, 122, 255) if (x + y) % 2 == 0 else (0, 0, 0, 0))
        new, _receipt = scenes.compile_compressed(self.resource, [(1, art)])
        contract = scenes.texture_contract(self.resource, 1)
        resolved = stadium._ResolvedStadiumScene(contract, self.resource.record, self.resource.span,
                                                 self.resource.decoded, self.resource.opaque_tail,
                                                 self.resource.textures)
        compiled = stadium._compile_resolved_scene((resolved,), (art,))
        stadium_decoded, _ = txtr.decompress_vc_lz(compiled.fixed.encoded, len(self.decoded))
        self.assertEqual(stadium_decoded, scenes.open_resource(new, outer_index=347, chunk_index=5).decoded)

    def test_art_that_cannot_fit_is_refused_and_nothing_is_returned(self) -> None:
        rng = random.Random(5)
        noise = png(self.root, "noise.png", 64, 64, lambda x, y: (rng.randrange(256), rng.randrange(256),
                                                                 rng.randrange(256), 255))
        tight_decoded, tight_system = fixture.scene_decoded("SCNE", [(64, 64, 1, ["flat"])], seed=2)
        flat = bytearray(tight_decoded)
        flat[tight_system:tight_system + 4096] = bytes(4096)          # a flat retail texture packs very small
        tight = scenes.open_resource(fixture.compressed_span(bytes(flat), tight_system, margin=0),
                                     outer_index=347, chunk_index=5)
        with self.assertRaises(scenes.PresentationSceneError):
            scenes.compile_compressed(tight, [(0, noise)])

    def test_compile_resource_dispatches_on_the_resource_shape(self) -> None:
        art = png(self.root, "dot.png", 32, 32, lambda x, y: (40, 44, 58, 255))
        self.assertFalse(scenes.compile_resource(self.resource, [(1, art)])[1]["raw"])
        decoded, system = fixture.scene_decoded("MRKS", [(32, 32, 1, ["pattern_flash"])])
        raw = scenes.open_resource(fixture.raw_span(decoded, system), outer_index=3114, chunk_index=1)
        self.assertTrue(scenes.compile_resource(raw, [(0, art)])[1]["raw"])


@unittest.skipUnless((PACKS / "0").is_file() and (PACKS / "4").is_file(),
                     "extracted retail vc_53450030 packs absent; set NFL2K5_GAME_DIR")
class RetailResourceTests(unittest.TestCase):
    """The six pinned resources compiled from their real retail spans: only the targeted allocations change."""

    def test_only_the_targeted_descriptors_change(self) -> None:
        from mod_editor.core import nfl2k5_espn_wipes_boards as option
        import nfl2k5_playbook_position_recode as recode
        from mod_editor.core import nfl2k5_official_marks as official
        pins = option._pins()
        # mk: a resource that draws an official mark (the player card's NFL shield) compiles only from the local
        # official marks pack; without it that resource is left out and the others still run.
        pack = option.available()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(GAME)
        with recode.OuterImage(GAME) as archive:
            for resource in pins["resources"]:
                if not pack and any(texture["png"] in official.ASSETS or
                                   (option.ART_DIR / texture["png"]).relative_to(official.ROOT).as_posix() in official.CATALOG
                                   for texture in resource["textures"]):
                    continue
                with self.subTest(resource=resource["name"]):
                    entry = archive.entries[resource["outer_index"]]
                    self.assertEqual((entry.name_id, entry.size), (resource["outer_name_id"], resource["outer_size"]))
                    span = archive.read(entry.virtual_offset + resource["chunk_offset"], resource["span_size"])
                    self.assertEqual(sha(span), resource["retail_sha256"])
                    retail = option.open_span(span, resource)
                    new, receipt = option.compile_span(span, resource)
                    self.assertEqual(sha(new), resource["applied_sha256"])
                    self.assertEqual((len(new), new[:32]), (len(span), span[:32]))
                    after = scenes.open_resource(new, outer_index=resource["outer_index"],
                                                 chunk_index=resource["chunk_index"],
                                                 chunk_offset=resource["chunk_offset"])
                    ranges = []
                    for texture in receipt["textures"]:
                        ranges += [(texture["decoded_pixel_offset"], texture["decoded_pixel_offset"] + texture["index_bytes"]),
                                   (texture["decoded_palette_offset"], texture["decoded_palette_offset"] + 1024)]
                    self.assertTrue(outside_equal(retail.decoded, after.decoded, ranges))
                    self.assertEqual(after.decoded[:retail.system_bytes], retail.decoded[:retail.system_bytes])
                    self.assertEqual(scenes.descriptor_summary(after), scenes.descriptor_summary(retail))
                    if retail.raw:
                        self.assertTrue(outside_equal(span[32:], new[32:], ranges))
                    else:
                        self.assertEqual(new[-len(retail.opaque_tail):], retail.opaque_tail)
                        self.assertLessEqual(receipt["minimum_scratch"], receipt["scratch_after"])
                        self.assertEqual(receipt["scratch_after"], retail.scratch)
                    for texture in receipt["textures"]:
                        width, height, rgba = scenes.texture_rgba(after, texture["texture_index"])
                        if texture["base_rgba_exact"]:
                            art = option.art_path(next(t["png"] for t in resource["textures"]
                                                         if t["texture_index"] == texture["texture_index"])).read_bytes()
                            self.assertEqual(rgba, decode_rgba_png(art, (width, height))[2])


if __name__ == "__main__":
    unittest.main()
