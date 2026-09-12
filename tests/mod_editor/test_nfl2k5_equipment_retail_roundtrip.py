"""Beta 68: exported retail shoes retain their palette and every distance image."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_import_intent import with_import_mode, with_retail_source
from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ExtendedVisualIO
from nfl_outer import parse_archive, read_entry_bytes
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import decode_chunk, parse_chunks

INDEX = Path(os.environ.get("NFL2K5_RETAIL_INDEX",
    "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))


@unittest.skipUnless(INDEX.is_file(), "Private retail NFL 2K5 pack index is absent")
class RetailRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_id, cls.groups = writer.load_targets()
        cls.archive = parse_archive(INDEX)
        cls.package = read_entry_bytes(cls.archive, cls.archive.entries[3850])
        cls.chunk = next(c for c in parse_chunks(cls.package, allow_trailing=True) if c.index == 8)
        cls.span = cls.package[cls.chunk.offset:cls.chunk.end_offset]
        if hashlib.sha256(cls.span).hexdigest() != writer._chain_pins()[3850, 8]:
            raise unittest.SkipTest("Equipment round trip needs the pinned retail 28H0 shoe span")
        cls.decoded, _ = decode_chunk(cls.package, cls.chunk)
        cls.textures, _ = writer._validate_layout(cls.decoded, cls.chunk, cls.groups[3850, 8])

    def test_export_unchanged_same_and_other_slot_preserves_retail_bytes(self):
        with tempfile.TemporaryDirectory(prefix="equipment-retail-roundtrip-") as directory:
            root = Path(directory).resolve()
            cache = SimpleNamespace(originals=root / "originals", pack0=INDEX,
                                    source=SimpleNamespace(sha256="retail-roundtrip"))
            cache.originals.mkdir()
            io = Nfl2k5ExtendedVisualIO(cache)
            source = self.by_id["tset:3850:8:0:shoes01"]
            asset = SimpleNamespace(asset_id=source.asset_id, equipment_descriptor=source,
                                    texture=source.name, width=256, height=256, dimensions=(256, 256),
                                    kind="uniform_equipment_texture", label=source.name)
            exported = io.export_original(asset, root / "retail-shoe.png")
            payload = exported.read_bytes()
            rgba = decode_rgba_png(payload, (256, 256))[2]
            expected = writer.decode_equipment_levels(self.decoded, self.chunk, self.textures[0])
            self.assertEqual(rgba, expected[0], "Export must use the unfiltered base mip")
            hashes = {}
            for reference, portable in ((0, True), (4, True), (0, False), (4, False)):
                with self.subTest(reference=reference, portable=portable):
                    target = self.groups[3850, 8][reference]
                    path = root / "import.png"
                    art = payload if portable else with_retail_source(payload, None, rgba)
                    path.write_bytes(with_import_mode(art, target.asset_id, rgba, independent=True))
                    span, _, receipt, _, _ = writer.build_unified_uniform_equipment_imports(
                        INDEX, [(target.asset_id, path)], pack_hashes=hashes)
                    chunk = parse_chunks(span)[0]
                    decoded, _ = decode_chunk(span, chunk)
                    row = receipt["edits"][0]
                    texture = replace(self.textures[reference], pixel_offset=row["pixel_offset"],
                                      width=row["encoded_dimensions"][0], height=row["encoded_dimensions"][1],
                                      mip_levels=row["mip_levels"])
                    self.assertEqual(writer.decode_equipment_levels(decoded, chunk, texture), expected)
                    before_palette = self.chunk.system_bytes + source.palette_offset
                    after_palette = chunk.system_bytes + target.palette_offset
                    self.assertEqual(decoded[after_palette:after_palette + 1024],
                                     self.decoded[before_palette:before_palette + 1024])
                    self.assertEqual(chunk.video_bytes, self.chunk.video_bytes)
                    self.assertEqual(span[20:24], self.span[20:24])
                    if reference == 0:
                        self.assertEqual(span, self.span)
                    for sibling in self.groups[3850, 8]:
                        if sibling.reference_index != reference:
                            texture = self.textures[sibling.reference_index]
                            self.assertEqual(writer.decode_equipment_levels(decoded, chunk, texture),
                                             writer.decode_equipment_levels(self.decoded, self.chunk, texture))
            self.assertEqual(read_entry_bytes(self.archive, self.archive.entries[3850]), self.package)

    def test_designed_sock_full_size_all_mips_and_untouched_bump(self):
        sys.path.insert(0, str(ROOT / "tests/fixtures"))
        from prove_equipment_texture_chain import prove
        from nfl_txtr import parse_texture

        proof = prove(INDEX, texture_name="socks00", scale=1)
        self.assertTrue(proof["every_encoded_level_matches_direct_coverage_exactly"])
        self.assertTrue(proof["source_span_unchanged"])
        row = proof["complete_import_receipt"]["edits"][0]
        self.assertEqual(row["encoded_dimensions"], [64, 64])
        self.assertEqual(row["projection_quality"]["differing_pixel_count"], 0)
        self.assertEqual(proof["complete_import_receipt"]["target"]["chunk_index"], 4)
        bumps = []
        for chunk in parse_chunks(self.package, allow_trailing=True):
            if chunk.kind == "TXTR":
                decoded, _ = decode_chunk(self.package, chunk)
                if parse_texture(decoded, chunk).name == "bump_sock":
                    bumps.append(chunk)
        self.assertEqual(len(bumps), 1)
        self.assertNotEqual(bumps[0].index, 4)
        after = read_entry_bytes(self.archive, self.archive.entries[3850])
        bump = bumps[0]
        self.assertEqual(after[bump.offset:bump.end_offset], self.package[bump.offset:bump.end_offset])


if __name__ == "__main__":
    unittest.main()
