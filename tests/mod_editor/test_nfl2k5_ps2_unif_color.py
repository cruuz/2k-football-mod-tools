"""Conformance suite for the PS2 NFL 2K5 uniform-colour on-disc writer.

**No game data.** Every image asserted against here is built in a temp
directory: a real ISO9660 volume, a real ``/VC_20919`` two-pack archive, a real
outer index, and real ``Unif`` resource chunks whose colour pair is reached the
way the engine reaches it -- through the object's own descriptor pointer.  A CI
runner with an empty disk runs the whole file green, which is the only way
these checks stay runnable.

What is asserted hard, because these are the properties a colour poke can quietly
lose:

* the catalogue resolves the colour offset **through the descriptor pointer**
  and only then agrees with the Xbox writer's 0x50 constant -- an offset that
  was assumed rather than derived would not survive a layout change;
* one edit produces a new image of the *source's exact byte length*, with at
  most the declared eight bytes different anywhere in it;
* the untouched word of an edited pair survives, so "change the facemask" does
  not silently repaint the turtleneck;
* **every refusal leaves no destination behind** -- over-length, out of range,
  an unsafe (compressed) target, a catalogue that disagrees with the image, a
  no-op, and an existing output path;
* **the verifier can fail.**  A byte changed outside every declared span, a
  declared span rewritten behind the receipt's back, and a receipt that lies
  about the retail bytes each raise.  A verifier that cannot fail is a rubber
  stamp.
"""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl2k5_ps2_unif_color_patch as patcher  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as catalog_tool  # noqa: E402
import nfl2k5_ps2_unif_color_verify as verifier  # noqa: E402


def _recipe(*edits) -> dict:
    return {"schema": patcher.RECIPE_SCHEMA, "edits": list(edits)}


class _ColorTestCase(unittest.TestCase):
    """Base class: a private temp directory and one synthetic stock image."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2unif-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.source = self.work / "stock.iso"
        self.source.write_bytes(catalog_tool.build_synthetic_iso())
        self.catalog = catalog_tool.build_catalog(str(self.source))

    def edited(self, *edits, name: str = "edited.iso", pinned=None):
        destination = self.work / name
        receipt = patcher.apply(
            self.source, destination, patcher.parse_recipe(_recipe(*edits)),
            pinned_catalog=self.catalog if pinned is None else pinned)
        return destination, receipt

    def refused(self, *edits, name: str = "refused.iso", pinned=None):
        destination = self.work / name
        with self.assertRaises(patcher.ColorPatchError) as caught:
            patcher.apply(self.source, destination,
                          patcher.parse_recipe(_recipe(*edits)),
                          pinned_catalog=pinned)
        self.assertFalse(destination.exists(),
                         "a refusal must not leave a destination behind")
        return str(caught.exception)


class CatalogueTests(_ColorTestCase):
    def test_the_fixture_carries_the_retail_unif_shape(self) -> None:
        blob = self.source.read_bytes()
        chunk = catalog_tool.unif_chunk(0xFFA29895, 0xFF272320)
        self.assertEqual(chunk[:4], b"Unif")
        self.assertEqual(struct.unpack_from("<I", chunk, 4)[0],
                         catalog_tool.UNIF_OBJECT_SIZE)
        # The chunk header is 'Unif' followed by the little-endian stored size
        # 0x50, which is why the retail bytes read "UnifP" -- the Xbox writer's
        # own header probe looks for exactly that.
        self.assertTrue(chunk.startswith(b"UnifP"))
        self.assertIn(chunk, blob, "the fixture must carry a whole Unif chunk")

    def test_the_colour_offset_is_derived_not_assumed(self) -> None:
        target = catalog_tool.find_target(self.catalog, "18H0")
        self.assertEqual(target["colour_offset_in_chunk"],
                         catalog_tool.XBOX_COLOUR_OFFSET)
        self.assertTrue(target["matches_xbox_offsets"])
        # Move the descriptor pointer and the derived offset must move with it,
        # which is what proves it was read rather than hard-coded.
        moved = catalog_tool.unif_chunk(1, 2)
        body = bytearray(moved[catalog_tool.CHUNK_HEADER_SIZE:])
        field = catalog_tool.OBJECT_DESCRIPTOR_POINTER
        struct.pack_into("<i", body, field, 0x38 - field + 1)
        probe = moved[:catalog_tool.CHUNK_HEADER_SIZE] + bytes(body)
        described = catalog_tool.describe_target(probe)
        self.assertTrue(described["ok"])
        self.assertEqual(described["colour_offset_chunk"],
                         catalog_tool.CHUNK_HEADER_SIZE + 0x38)
        self.assertFalse(described["matches_xbox_offsets"])

    def test_a_compressed_body_never_reaches_the_catalogue(self) -> None:
        self.assertEqual(self.catalog["summary"]["compressed_targets"], 0)
        self.assertEqual(self.catalog["summary"]["rejected"], 1)
        self.assertIn("compressed", self.catalog["rejected"][0]["reason"])

    def test_the_catalogue_carries_no_retail_colour_words(self) -> None:
        text = json.dumps(self.catalog)
        self.assertNotIn("facemask_argb", text)
        self.assertNotIn("turtleneck_argb", text)
        for row in self.catalog["targets"]:
            self.assertNotIn("words", row)
            self.assertEqual(len(row["retail_span_sha256"]), 64)

    def test_selectors_share_the_xbox_namespace(self) -> None:
        self.assertEqual(
            catalog_tool.selector_index()[
                catalog_tool.uniform_name_id("18H0.IFF")], "18H0")
        self.assertEqual({row["selector"] for row in self.catalog["targets"]},
                         {"18H0", "18A0"})


class WriteTests(_ColorTestCase):
    def test_one_edit_keeps_the_image_length_and_changes_eight_bytes(self) -> None:
        destination, receipt = self.edited({"selector": "18H0",
                                            "facemask": "#00FF00"})
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        before, after = self.source.read_bytes(), destination.read_bytes()
        differing = [index for index, pair in enumerate(zip(before, after))
                     if pair[0] != pair[1]]
        self.assertTrue(differing)
        self.assertLessEqual(len(differing), 8)
        start = receipt["declared_ranges"][0]["start"]
        self.assertTrue(all(start <= index < start + 8 for index in differing))

    def test_the_untouched_word_of_the_pair_survives(self) -> None:
        destination, _receipt = self.edited({"selector": "18H0",
                                             "facemask": "#00FF00"})
        target = catalog_tool.find_target(self.catalog, "18H0")
        at = target["colour_offset_in_iso"]
        before = struct.unpack_from("<II", self.source.read_bytes(), at)
        after = struct.unpack_from("<II", destination.read_bytes(), at)
        self.assertEqual(after[0], 0xFF00FF00)
        self.assertEqual(after[1], before[1])

    def test_the_source_image_is_never_written(self) -> None:
        digest_before = self.source.read_bytes()
        self.edited({"selector": "18H0", "facemask": "#00FF00"})
        self.assertEqual(self.source.read_bytes(), digest_before)

    def test_a_dry_run_creates_nothing(self) -> None:
        plan = patcher.plan(self.source,
                            patcher.parse_recipe(_recipe(
                                {"selector": "18H0", "facemask": "#00FF00"})),
                            self.catalog)
        self.assertEqual(len(plan["edits"]), 1)
        self.assertEqual(list(self.work.glob("*.iso")), [self.source])


class RefusalTests(_ColorTestCase):
    def test_an_over_length_colour_literal_is_refused(self) -> None:
        with self.assertRaises(patcher.ColorPatchError) as caught:
            patcher.parse_recipe(_recipe({"selector": "18H0",
                                          "facemask": "FFAABBCCDD"}))
        self.assertIn("exactly 4 bytes", str(caught.exception))

    def test_an_out_of_range_selector_is_refused(self) -> None:
        message = self.refused({"selector": "99A9", "facemask": "#000000"})
        self.assertIn("out-of-range", message)

    def test_an_unsafe_compressed_target_is_refused(self) -> None:
        message = self.refused({"selector": "07H1", "facemask": "#000000"})
        self.assertIn("unsafe target", message)
        self.assertIn("recompressed back into the stored span", message)

    def test_a_catalogue_that_disagrees_with_the_image_is_refused(self) -> None:
        forged = json.loads(json.dumps(self.catalog))
        for row in forged["targets"]:
            row["probe_sha256"] = "0" * 64
        message = self.refused({"selector": "18H0", "facemask": "#123456"},
                               pinned=forged)
        self.assertIn("not the stock disc", message)

    def test_a_no_op_edit_is_refused(self) -> None:
        message = self.refused({"selector": "18H0", "facemask": "FFA29895"})
        self.assertIn("already uses those colours", message)

    def test_an_existing_destination_is_refused(self) -> None:
        destination, _receipt = self.edited({"selector": "18H0",
                                             "facemask": "#00FF00"})
        with self.assertRaises(patcher.ColorPatchError) as caught:
            patcher.apply(self.source, destination,
                          patcher.parse_recipe(_recipe(
                              {"selector": "18A0", "facemask": "#00FF00"})))
        self.assertIn("already exists", str(caught.exception))

    def test_a_recipe_may_not_name_an_unproved_field(self) -> None:
        with self.assertRaises(patcher.ColorPatchError) as caught:
            patcher.parse_recipe(_recipe({"selector": "18H0", "visor": "#000000"}))
        self.assertIn("unknown keys", str(caught.exception))

    def test_a_selector_may_be_written_once(self) -> None:
        with self.assertRaises(patcher.ColorPatchError) as caught:
            patcher.parse_recipe(_recipe({"selector": "18H0", "facemask": "#010101"},
                                         {"selector": "18h0", "turtleneck": "#020202"}))
        self.assertIn("appears twice", str(caught.exception))


class VerifierTests(_ColorTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.destination, self.receipt = self.edited(
            {"selector": "18H0", "facemask": "#00FF00"},
            {"selector": "18A0", "turtleneck": "FF010203"})

    def _poke(self, path: Path, offset: int, value: bytes) -> Path:
        candidate = self.work / ("mutated-%d.iso" % offset)
        candidate.write_bytes(path.read_bytes())
        with open(str(candidate), "r+b") as handle:
            handle.seek(offset)
            handle.write(value)
        return candidate

    def test_a_correct_write_verifies(self) -> None:
        report = verifier.verify(self.source, self.destination, self.receipt)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["edits_checked"], 2)
        self.assertGreater(report["unchanged_bytes_compared"], 0)

    def test_a_json_round_trip_of_the_receipt_verifies_identically(self) -> None:
        report = verifier.verify(self.source, self.destination,
                                 json.loads(json.dumps(self.receipt)))
        self.assertEqual(report["result"], "PASS")

    def test_a_byte_outside_every_declared_span_fails(self) -> None:
        target = catalog_tool.find_target(self.catalog, "18H0")
        candidate = self._poke(self.destination,
                               target["colour_offset_in_iso"] + 0x40, b"\xa5")
        with self.assertRaises(verifier.ColorVerifyError) as caught:
            verifier.verify(self.source, candidate, self.receipt)
        self.assertIn("outside every declared colour span", str(caught.exception))

    def test_a_declared_span_rewritten_behind_the_receipt_fails(self) -> None:
        target = catalog_tool.find_target(self.catalog, "18H0")
        candidate = self._poke(self.destination, target["colour_offset_in_iso"],
                               b"\x01\x02\x03\x04")
        with self.assertRaises(verifier.ColorVerifyError):
            verifier.verify(self.source, candidate, self.receipt)

    def test_a_broken_unif_object_fails(self) -> None:
        target = catalog_tool.find_target(self.catalog, "18H0")
        chunk = target["colour_offset_in_iso"] - catalog_tool.XBOX_COLOUR_OFFSET
        candidate = self._poke(
            self.destination, chunk + catalog_tool.XBOX_RECORD_TAG_OFFSET, b"XXXX")
        with self.assertRaises(verifier.ColorVerifyError):
            verifier.verify(self.source, candidate, self.receipt)

    def test_a_receipt_that_lies_about_the_retail_bytes_fails(self) -> None:
        forged = json.loads(json.dumps(self.receipt))
        forged["edits"][0]["before_sha256"] = "0" * 64
        with self.assertRaises(verifier.ColorVerifyError):
            verifier.verify(self.source, self.destination, forged)

    def test_dropping_the_declared_ranges_fails(self) -> None:
        forged = json.loads(json.dumps(self.receipt))
        forged["declared_ranges"] = []
        with self.assertRaises(verifier.ColorVerifyError):
            verifier.verify(self.source, self.destination, forged)

    def test_the_verifier_does_not_import_the_writer_or_its_parser(self) -> None:
        source = (_REPO_ROOT / "tools" / "nfl2k5_ps2_unif_color_verify.py").read_text(
            encoding="utf-8")
        head = source.split("def selftest", 1)[0]
        for forbidden in ("import nfl2k5_ps2_unif_color_patch",
                          "import nfl2k5_ps2_unif_color_target_catalog",
                          "import ps2_iso9660_writer",
                          "import ps2_iso9660 as"):
            self.assertNotIn(forbidden, head)


class SelfTestTests(unittest.TestCase):
    def test_every_module_self_test_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ps2unif-selftest-") as work:
            self.assertEqual(catalog_tool.selftest(work), 0)
            self.assertEqual(patcher.selftest(work), 0)
            self.assertEqual(verifier.selftest(work), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
