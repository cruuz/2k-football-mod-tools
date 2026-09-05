#!/usr/bin/env python3
"""The PS2 NFL 2K5 uniform-art lane, proved on its own synthetic image.

No disc, no retail byte, no Pillow. The fixture is two textures -- one PSMT8
with a 256-colour CLUT, one PSMT4 with a 16-colour one -- laid out by the same
GS rules the decoder reads, so the decode can be checked against pixels this
file works out for itself rather than against the decoder's own answer.

Every expectation that could be met by importing the implementation is instead
restated here: the CSM1 CLUT position swizzle, the PS2 alpha scale, the 4-bit
unpacking order and the PCSX2 filename grammar. If the lane and this file ever
disagree, that disagreement is the finding.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_ps2_replacement_pack_verify as pack_verify  # noqa: E402
import nfl2k5_ps2_texture_map as texture_map  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402
from mod_editor.games.nfl2k5_ps2 import GAME  # noqa: E402
from mod_editor.games.nfl2k5_ps2 import uniform_art  # noqa: E402


# --------------------------------------------------------------------------
# Restated facts. Deliberately not imported.
# --------------------------------------------------------------------------

def csm1_position(entry: int) -> int:
    """Where index ``entry`` of an 8-bit CSM1 CLUT sits in the stored 1,024 bytes.

    The GS stores a 256-entry CLUT with entries 8..15 and 16..23 exchanged in
    every group of 32; ``docs/product/PS2_M1_PLAN.md`` §4 WP1 step 3 calls it
    the "CSM1 bits 3<->4 swap".
    """

    return (entry & ~0x18) | ((entry & 0x08) << 1) | ((entry & 0x10) >> 1)


def ps2_alpha(value: int) -> int:
    """PS2 alpha is 0..0x80 with 0x80 opaque; a PNG's is 0..0xFF."""

    return min(255, (value * 255) // 0x80)


def read_rgba_png(payload: bytes):
    """``(width, height, rgba)`` from an 8-bit RGBA, non-interlaced PNG.

    A whole PNG decoder is not needed: the lane writes filter type 0 on every
    row, and this asserts that rather than assuming it.
    """

    assert payload[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    offset = 8
    header = None
    data = b""
    while offset < len(payload):
        length, tag = struct.unpack_from(">I4s", payload, offset)
        body = payload[offset + 8:offset + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            data += body
        offset += 12 + length
    assert header is not None, "no IHDR"
    width, height, depth, colour, _c, _f, interlace = header
    assert (depth, colour, interlace) == (8, 6, 0), header
    raw = zlib.decompress(data)
    stride = width * 4
    rows = []
    for index in range(height):
        start = index * (stride + 1)
        assert raw[start] == 0, "the lane writes filter type 0 on every row"
        rows.append(raw[start + 1:start + 1 + stride])
    return width, height, b"".join(rows)


#: The PCSX2 replacement grammar, restated: two %llx fields that are NOT zero
#: padded, then the %08x property word, then .png.
PCSX2_NAME = re.compile(r"^[0-9a-f]{1,16}-[0-9a-f]{1,16}-[0-9a-f]{8}\.png$")


class UniformArtFixture(unittest.TestCase):
    """One synthetic image, built once, used by every case below."""

    @classmethod
    def setUpClass(cls) -> None:
        # .resolve() so a Windows short path (C:\Users\RUNNER~1\...) and the
        # long name it stands for cannot compare unequal.
        cls.room = Path(tempfile.mkdtemp(prefix="ps2-uniform-art-")).resolve()
        cls.lane = uniform_art.UniformArtLane()
        cls.source = cls.lane.synthetic_source(cls.room)
        cls.catalogue = cls.lane.build_catalogue(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.room, ignore_errors=True)

    def room_for(self, name: str) -> Path:
        room = self.room / name
        room.mkdir(parents=True, exist_ok=True)
        return room

    def target(self, pixel_format: str):
        for target in self.catalogue.targets:
            if dict(target.raw)["pixel_format"] == pixel_format:
                return target
        raise AssertionError(f"no {pixel_format} target in the fixture")


class CatalogueTests(UniformArtFixture):
    def test_the_fixture_carries_one_psmt8_and_one_psmt4_texture(self) -> None:
        formats = sorted(dict(t.raw)["pixel_format"] for t in self.catalogue.targets)
        self.assertEqual(formats, ["PSMT4", "PSMT8"])
        self.assertEqual(self.catalogue.schema, uniform_art.CATALOGUE_SCHEMA)

    def test_every_target_carries_the_facts_the_uniforms_page_shows(self) -> None:
        for target in self.catalogue.targets:
            row = dict(target.raw)
            for key in ("team", "kit", "side", "part", "width", "height",
                        "pixel_format", "mip_levels", "pcsx2_png", "selector"):
                self.assertIn(key, row, key)
            self.assertGreater(row["width"], 0)
            self.assertGreater(row["height"], 0)
            self.assertGreaterEqual(row["mip_levels"], 1)
            self.assertTrue(target.label.strip())
            self.assertIn(str(row["width"]), target.label)
            self.assertEqual([field.key for field in target.fields], ["png"])
            self.assertEqual([field.kind for field in target.fields], ["png"])
            self.assertFalse(target.fields[0].read_only)

    def test_the_summary_counts_what_could_not_be_joined(self) -> None:
        summary = self.catalogue.document["summary"]
        for key in ("textures", "teams", "packable_textures",
                    "textures_without_a_team_name",
                    "selectors_without_a_team_name",
                    "textures_without_an_identity"):
            self.assertIn(key, summary, key)
        self.assertEqual(summary["textures"], len(self.catalogue.targets))
        self.assertEqual(summary["packable_textures"], 2)
        self.assertEqual(summary["textures_without_an_identity"], 0)

    def test_the_catalogue_document_carries_no_payload(self) -> None:
        from mod_editor.games.conformance import contains_payload

        self.assertFalse(contains_payload(dict(self.catalogue.document)))

    def test_a_narrowed_walk_reads_only_the_packages_it_was_asked_for(self) -> None:
        narrowed = self.lane.build_catalogue(
            self.source, selectors=[uniform_art.SYNTHETIC_SELECTOR.lower()])
        self.assertEqual(narrowed.document["scope"]["selectors"],
                         [uniform_art.SYNTHETIC_SELECTOR])
        self.assertFalse(narrowed.document["scope"]["whole_disc"])
        self.assertEqual([t.key for t in narrowed.targets],
                         [t.key for t in self.catalogue.targets])
        self.assertTrue(self.catalogue.document["scope"]["whole_disc"])

    def test_a_package_this_disc_does_not_carry_is_refused_with_a_sentence(self) -> None:
        with self.assertRaises(Refusal) as caught:
            self.lane.build_catalogue(self.source, selectors=["77A9"])
        self.assertIn("77A9", str(caught.exception))
        self.assertIn("09H0", str(caught.exception))

    def test_a_team_resolves_to_the_packages_the_kit_table_gives_it(self) -> None:
        for name in ("DET", "Detroit Lions", "det"):
            selectors = self.lane.selectors_for_team(name)
            self.assertTrue(selectors, name)
            self.assertIn("09H0", selectors)
            self.assertTrue(all(row.startswith("09") for row in selectors), selectors)
        self.assertEqual(self.lane.selectors_for_team("Sheffield Steelers"), ())
        self.assertEqual(self.lane.selectors_for_team(""), ())

    def test_a_disc_with_no_uniform_package_is_refused_with_a_sentence(self) -> None:
        import nfl2k5_ps2_unif_color_target_catalog as colour_catalog

        empty = self.room_for("empty") / "not-a-uniform-disc.iso"
        empty.write_bytes(colour_catalog.build_synthetic_iso(
            entries=[("ZZZZ.BIN", b"RAWD" + bytes(12) + b"nothing here" * 8)]))
        with self.assertRaises(Refusal) as caught:
            self.lane.build_catalogue(empty)
        self.assertIn("uniform packages", str(caught.exception))


class DecodeTests(UniformArtFixture):
    def test_the_psmt8_decode_is_the_palette_image_this_test_works_out(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        width, height = row["width"], row["height"]
        indices = texture_map.pattern_bytes(width * height, 11)
        stored = texture_map.pattern_bytes(1024, 31)

        expected = bytearray()
        for index in indices:
            at = csm1_position(index) * 4
            red, green, blue, alpha = stored[at:at + 4]
            expected += bytes((red, green, blue, ps2_alpha(alpha)))

        got_width, got_height, rgba = read_rgba_png(
            self.lane.decode_png(self.source, target))
        self.assertEqual((got_width, got_height), (width, height))
        self.assertEqual(rgba, bytes(expected))

    def test_the_psmt4_decode_unpacks_low_nibble_first_against_a_raw_clut(self) -> None:
        target = self.target("PSMT4")
        row = dict(target.raw)
        width, height = row["width"], row["height"]
        packed = texture_map.pattern_bytes((width * height) // 2, 12)
        stored = texture_map.pattern_bytes(64, 32)

        indices = bytearray(width * height)
        for position, byte in enumerate(packed):
            indices[position * 2] = byte & 0x0F
            indices[position * 2 + 1] = byte >> 4

        expected = bytearray()
        for index in indices:
            red, green, blue, alpha = stored[index * 4:index * 4 + 4]
            expected += bytes((red, green, blue, ps2_alpha(alpha)))

        got_width, got_height, rgba = read_rgba_png(
            self.lane.decode_png(self.source, target))
        self.assertEqual((got_width, got_height), (width, height))
        self.assertEqual(rgba, bytes(expected))

    def test_decoding_never_writes_to_the_source(self) -> None:
        before = self.source.read_bytes()
        for target in self.catalogue.targets:
            self.lane.decode_png(self.source, target)
        self.assertEqual(self.source.read_bytes(), before)


class IdentityTests(UniformArtFixture):
    def test_the_replacement_name_is_two_unpadded_hex_fields_and_a_property_word(self) -> None:
        for target in self.catalogue.targets:
            name = self.lane.replacement_identity(target)
            self.assertIsNotNone(name)
            self.assertRegex(name, PCSX2_NAME)
            for field in name.split(".")[0].split("-")[:2]:
                self.assertFalse(field.startswith("0") and len(field) > 1,
                                 f"%llx is not zero padded: {name}")

    def test_the_property_word_sets_the_tcc_bit(self) -> None:
        """``bits = PSM | TW<<6 | TH<<10 | TCC<<14`` -- PS2_M1_PLAN §4 WP1 step 1."""

        for target in self.catalogue.targets:
            row = dict(target.raw)
            bits = int(row["pcsx2_png"].split(".")[0].split("-")[-1], 16)
            self.assertEqual(bits & 0x4000, 0x4000, row["pcsx2_png"])
            self.assertEqual(bits & 0x3F,
                             texture_map.PSMT8 if row["pixel_format"] == "PSMT8"
                             else texture_map.PSMT4)
            self.assertEqual(1 << ((bits >> 6) & 0xF), row["width"])
            self.assertEqual(1 << ((bits >> 10) & 0xF), row["height"])

    def test_a_texture_the_map_does_not_prove_is_catalogued_but_not_packable(self) -> None:
        blank = self.room_for("blank") / "blank-map.json"
        document = dict(uniform_art.synthetic_identity_map(self.source))
        document["entries"] = []
        with open(blank, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(document, indent=2, sort_keys=True) + "\n")

        lane = uniform_art.UniformArtLane(map_path=blank)
        catalogue = lane.build_catalogue(self.source)
        self.assertEqual(catalogue.document["summary"]["packable_textures"], 0)
        target = catalogue.targets[0]
        row = dict(target.raw)
        self.assertEqual(row["identity_source"], "rule")
        self.assertFalse(row["identity_confirmed"])
        # Still decodable: extraction is what an extract-only lane is for.
        self.assertTrue(lane.decode_png(self.source, target))
        png = uniform_art.write_rgba_png(
            bytes([1, 2, 3, 255]) * (row["width"] * row["height"]),
            row["width"], row["height"])
        problem = lane.check_edit(target, {"png": png})
        self.assertIsNotNone(problem)
        self.assertIn("shipped map does not prove", problem)
        with self.assertRaises(Refusal):
            lane.conformance_edits(catalogue)

    def test_a_sidecar_map_beside_the_image_wins_over_the_shipped_one(self) -> None:
        sidecar = Path(str(self.source) + uniform_art.MAP_SIDECAR_SUFFIX)
        self.assertTrue(sidecar.is_file())
        self.assertEqual(uniform_art.map_for_source(self.source), sidecar)
        other = self.room / "no-sidecar.iso"
        self.assertEqual(uniform_art.map_for_source(other), uniform_art.DEFAULT_MAP)


class EncodeTests(UniformArtFixture):
    def png(self, width: int, height: int, tint: int = 0x40) -> bytes:
        return uniform_art.write_rgba_png(
            bytes([tint, tint, tint, 255]) * (width * height), width, height)

    def test_a_replacement_at_the_texture_s_own_size_is_accepted(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        art = self.lane.encode(self.source, target, self.png(row["width"], row["height"]))
        self.assertIsInstance(art, uniform_art.EncodedArt)
        self.assertEqual((art.width, art.height), (row["width"], row["height"]))
        self.assertEqual(uniform_art.png_header(art.png)[:2], (row["width"], row["height"]))
        self.assertTrue(art.note)

    def test_a_replacement_at_twice_the_size_is_accepted_because_pcsx2_scales(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        art = self.lane.encode(self.source, target,
                               self.png(row["width"] * 2, row["height"] * 2))
        self.assertIsInstance(art, uniform_art.EncodedArt)
        self.assertEqual((art.width, art.height), (row["width"] * 2, row["height"] * 2))
        self.assertIn("2x", art.note)

    def test_a_three_to_two_stretch_is_refused_with_the_size_it_wanted(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        refusal = self.lane.encode(self.source, target,
                                   self.png(row["width"] * 3, row["height"] * 2))
        self.assertIsInstance(refusal, Refusal)
        self.assertIn(f"{row['width']}x{row['height']}", str(refusal))

    def test_a_size_that_is_not_a_whole_multiple_is_refused(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        refusal = self.lane.encode(self.source, target,
                                   self.png(row["width"] + 3, row["height"]))
        self.assertIsInstance(refusal, Refusal)
        self.assertIn(f"{row['width']}x{row['height']}", str(refusal))

    def test_something_that_is_not_a_png_is_refused_with_the_size_it_wanted(self) -> None:
        target = self.target("PSMT8")
        row = dict(target.raw)
        for payload in (b"", b"GIF89a not a png at all", "a string", 17):
            refusal = self.lane.encode(self.source, target, payload)
            self.assertIsInstance(refusal, Refusal, payload)
            self.assertIn(f"{row['width']}x{row['height']}", str(refusal))

    def test_check_edit_refuses_a_value_this_lane_does_not_edit(self) -> None:
        target = self.target("PSMT8")
        problem = self.lane.check_edit(target, {"colour": "#ff0000"})
        self.assertIsNotNone(problem)
        self.assertIn("colour", problem)


class PackTests(UniformArtFixture):
    def staged(self, name: str):
        room = self.room_for(name)
        edits = self.lane.conformance_edits(self.catalogue)
        recipe = self.lane.compose_recipe(edits)
        destination = room / "pack-receipt.json"
        receipt = self.lane.build(self.source, destination, recipe, self.catalogue)
        return recipe, destination, receipt

    def test_a_pack_is_written_and_the_independent_verifier_passes_it(self) -> None:
        _recipe, destination, receipt = self.staged("pack")
        pack_root = self.lane.pack_root_for(destination)
        self.assertTrue(pack_root.is_dir())
        names = sorted(p.name for p in pack_root.rglob("*.png"))
        self.assertTrue(names)
        for name in names:
            self.assertRegex(name, PCSX2_NAME)
        self.assertTrue((pack_root / "textures" / uniform_art.SERIAL
                         / "replacements").is_dir())
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)

        # The verifier reached PASS through the disc-native provenance, and the
        # receipt says so rather than the pack's origin being assumed.
        report = pack_verify.verify(pack_root,
                                    manifest=Path(str(self.source)
                                                  + uniform_art.MAP_SIDECAR_SUFFIX),
                                    edits=destination)
        self.assertEqual(report["result"], pack_verify.RESULT_PASS)
        self.assertEqual(report["origin"], pack_verify.ORIGIN_DISC_NATIVE_ART)

    def test_a_pack_without_its_edits_document_is_incomplete_not_a_pass(self) -> None:
        _recipe, destination, _receipt = self.staged("incomplete")
        pack_root = self.lane.pack_root_for(destination)
        report = pack_verify.verify(pack_root,
                                    manifest=Path(str(self.source)
                                                  + uniform_art.MAP_SIDECAR_SUFFIX))
        self.assertEqual(report["result"], pack_verify.RESULT_INCOMPLETE)
        self.assertIn("--edits", report["downgrade_reason"])

    def test_one_flipped_byte_in_the_pack_fails_verification(self) -> None:
        _recipe, destination, receipt = self.staged("flipped")
        pack_root = self.lane.pack_root_for(destination)
        victim = sorted(pack_root.rglob("*.png"))[0]
        blob = bytearray(victim.read_bytes())
        blob[-9] ^= 0xFF
        victim.write_bytes(bytes(blob))
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertFalse(verdict.passed, verdict.summary)

    def test_an_edits_document_that_is_not_the_receipted_one_fails(self) -> None:
        _recipe, destination, receipt = self.staged("swapped")
        with open(destination, "ab") as handle:
            handle.write(b"\n")
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertFalse(verdict.passed, verdict.summary)

    def test_an_existing_destination_is_refused_and_left_alone(self) -> None:
        recipe, destination, _receipt = self.staged("existing")
        before = destination.read_bytes()
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, destination, recipe, self.catalogue)
        self.assertIn("already exists", str(caught.exception))
        self.assertEqual(destination.read_bytes(), before)

    def test_the_source_image_is_refused_as_a_destination(self) -> None:
        recipe, _destination, _receipt = self.staged("as-source")
        before = self.source.read_bytes()
        with self.assertRaises(Refusal):
            self.lane.build(self.source, self.source, recipe, self.catalogue)
        self.assertEqual(self.source.read_bytes(), before)

    def test_a_recipe_naming_an_unknown_target_is_refused(self) -> None:
        recipe = dict(self.lane.compose_recipe(
            self.lane.conformance_edits(self.catalogue)))
        recipe["edits"] = [dict(recipe["edits"][0], target="no-such-target")]
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, recipe, self.catalogue)

    def test_the_build_writes_lf_only_text(self) -> None:
        _recipe, destination, receipt = self.staged("newlines")
        pack_root = self.lane.pack_root_for(destination)
        written = [destination] + [path for path in pack_root.rglob("*.json")]
        self.assertGreaterEqual(len(written), 3)
        for path in written:
            self.assertNotIn(b"\r\n", path.read_bytes(), path.name)
        self.assertEqual(receipt.document["edits_sha256"],
                         __import__("hashlib").sha256(
                             destination.read_bytes()).hexdigest())


class ShippedDataTests(unittest.TestCase):
    def test_the_kit_table_is_lf_only_names_and_nothing_else(self) -> None:
        payload = uniform_art.KITS_FILE.read_bytes()
        self.assertNotIn(b"\r\n", payload)
        document = json.loads(payload.decode("utf-8"))
        self.assertEqual(document["schema"], uniform_art.KITS_SCHEMA)
        self.assertEqual(document["counts"]["selectors"], len(document["selectors"]))
        self.assertGreaterEqual(document["counts"]["selectors"], 500)
        for selector, row in document["selectors"].items():
            self.assertRegex(selector, r"^[0-9A-Z]{2}[AH][0-9]{1,2}$")
            self.assertEqual(sorted(row), ["abbreviation", "kit", "side", "team"])
            self.assertIn(row["side"], ("home", "away"))

    def test_the_kit_table_is_still_the_committed_sidecar_s_own_answer(self) -> None:
        """It was extracted mechanically; prove it can be extracted again."""

        document = json.loads(uniform_art.KITS_FILE.read_text(encoding="utf-8"))
        sidecar = ROOT / document["source"]["file"]
        if not sidecar.is_file():  # the research sidecar is not in every checkout
            self.skipTest(f"{document['source']['file']} is not in this checkout")
        side = json.loads(sidecar.read_text(encoding="utf-8"))
        kits = side["demo_team"]["logical"]["kits"]
        teams = side["demo_team"]["physical"]["per_team"]
        rebuilt = {}
        for label, row in kits.items():
            selector = row.get("selector")
            if not isinstance(selector, str) or not selector:
                continue
            abbreviation, _, rest = label.partition("/")
            side_code, _, kit = rest.partition("/")
            rebuilt[selector.upper()] = {
                "abbreviation": abbreviation,
                "team": (teams.get(abbreviation) or {}).get("team") or "",
                "side": {"H": "home", "A": "away"}.get(side_code, side_code),
                "kit": kit,
            }
        self.assertEqual(document["selectors"], rebuilt)

    def test_part_names_come_from_the_texture_s_own_name(self) -> None:
        for name, part, variant in (
            ("jersey00", "torso", ""),
            ("jersey00_mud", "torso", "mud"),
            ("pants00", "pants", ""),
            ("sleeve00", "sleeve", ""),
            ("longsleeve01", "sleeve", ""),
            ("helmet00", "helmet", ""),
            ("helmet_numbers", "numbers", ""),
            ("jersey_numbers", "numbers", ""),
            ("names", "nameplate", ""),
            ("glove03", "equipment", ""),
            ("wibble", "other", ""),
        ):
            got_part, description, got_variant = uniform_art.part_of(name)
            self.assertEqual((got_part, got_variant), (part, variant), name)
            self.assertTrue(description)


class RegistrationTests(unittest.TestCase):
    def test_the_lane_is_on_the_module_and_matches_its_registry_row(self) -> None:
        lanes = {lane.lane_id: lane for lane in GAME.lanes}
        self.assertIn(uniform_art.LANE_ID, lanes)
        lane = lanes[uniform_art.LANE_ID]
        self.assertEqual(lane.capability_id, uniform_art.CAPABILITY_ID)
        self.assertEqual(lane.surface, "uniforms")
        self.assertEqual(lane.page, "uniforms")
        self.assertEqual(lane.classification, "extract-only")
        rows = {row["id"]: row for row
                in GAME.manifest.registry_document()["capabilities"]}
        row = rows[lane.capability_id]
        self.assertEqual(row["surface"], lane.surface)
        self.assertEqual(row["classification"], lane.classification)
        for validator in lane.validators:
            self.assertTrue((ROOT / validator).is_file(), validator)

    def test_the_three_art_lane_methods_carry_the_planned_names(self) -> None:
        """A1 adds ``ArtLane`` on another branch; these are the members it needs."""

        import inspect

        lane = uniform_art.UniformArtLane()
        for name, parameters in (
            ("decode_png", ["self", "source", "target"]),
            ("encode", ["self", "source", "target", "png"]),
            ("replacement_identity", ["self", "target"]),
        ):
            self.assertTrue(callable(getattr(lane, name)), name)
            signature = inspect.signature(getattr(type(lane), name))
            self.assertEqual(list(signature.parameters), parameters, name)


if __name__ == "__main__":
    unittest.main()
