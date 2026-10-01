"""GAMEDATA presentation inventory (beta 76): pinned counts, the grade gate and the typed build.

The 44 standalone TXTR chunks of gamedata.iff join the 11,395-target All Textures inventory only through
the explicit ``extended_standalone_inventory()`` view, and only the four A/B graded ESPN marks are offered
for a write. Retail-dependent cases skip when the inputs are absent: set NFL2K5_RETAIL_XISO to a retail
USA XISO and NFL2K5_GAME_DIR to an extracted game folder holding ``vc_53450030``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_presentation_standalone as ps  # noqa: E402

RETAIL_XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
INDEX = GAME / "vc_53450030" / "0"
from mod_editor.core.nfl2k5_espn_marks import art_path
PINS = ROOT / "data" / "nfl2k5_espn_marks_pins.json"
MARKS = ("nfl_chiclet", "shield_espn", "espnLogo1", "z_ESPN_bug")
REFUSED_C = ("telecircle1", "telecircle2", "passicons", "replayicons", "endQTR_textures", "score_buga")
# The research report's ten named targets: chunk, pack 0 offset, exact span.
NAMED = {"telecircle1": (19, 0x6901890, 2240), "telecircle2": (20, 0x6902150, 1856),
         "passicons": (21, 0x6902890, 4976), "replayicons": (22, 0x6903C00, 3856),
         "nfl_chiclet": (24, 0x6904E60, 4368), "shield_espn": (26, 0x6906050, 5952),
         "espnLogo1": (33, 0x690C740, 6240), "endQTR_textures": (51, 0x693C560, 2704),
         "score_buga": (53, 0x693D450, 2432), "z_ESPN_bug": (57, 0x693E250, 4064)}


class PinnedInventoryTests(unittest.TestCase):
    def test_counts_formats_grades_and_named_spans_are_pinned(self) -> None:
        document = ps.load_standalone()
        self.assertEqual(ps.digest(ps.STANDALONE_PATH.read_bytes()), ps.STANDALONE_SHA256)
        self.assertEqual(document["summary"], dict(
            target_count=44, editable_target_count=42, offered_target_count=4,
            format_counts={"DXT1": 2, "P8": 42}, grade_counts={"A": 3, "B": 1, "C": 6}))
        rows = ps.rows_by_texture(document)
        self.assertEqual(len({row["asset_id"] for row in document["targets"]}), 44)
        self.assertEqual(sorted(t for t, r in rows.items() if r["format_name"] == "DXT1"), ["espn1", "nflShield1"])
        self.assertEqual({t: r["authored_grade"] for t, r in rows.items() if r["authored_grade"]},
                         {**ps.AUTHORED_GRADES, **{name: "C" for name in REFUSED_C}})
        self.assertEqual(ps.AUTHORED_GRADES, {"nfl_chiclet": "A", "shield_espn": "A", "espnLogo1": "A", "z_ESPN_bug": "B"})
        for name, (chunk, offset, span) in NAMED.items():
            with self.subTest(name=name):
                row = rows[name]
                self.assertEqual((row["chunk_index"], row["pack_offset"], row["span_size"]), (chunk, offset, span))
                self.assertEqual((row["outer_index"], row["outer_id"], row["pack_name"]), (346, "0x00b6926c", "0"))
        self.assertEqual(document["packs"]["0"], {
            "path": "vc_53450030/0", "retail_sector": 796479, "size": 193710080,
            "sha256": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"})

    def test_content_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="presentation-drift-") as tmp:
            changed = Path(tmp) / ps.STANDALONE_PATH.name
            changed.write_bytes(ps.STANDALONE_PATH.read_bytes() + b" ")
            with self.assertRaisesRegex(ps.PresentationMarkError, "content drift"):
                ps.load_standalone(changed)

    def test_grade_gate_offers_only_the_four_graded_marks(self) -> None:
        self.assertEqual(ps.offered_marks(), MARKS)
        records = ps.extension_records()
        self.assertEqual(len(records), 44)
        self.assertEqual(sum(r["format_supported"] for r in records.values()), 42)
        self.assertEqual({r["texture"] for r in records.values() if r["replacement_supported"]}, set(MARKS))
        missing_png, missing_index = Path("absent-mark.png"), Path("absent-index") / "0"
        for name in REFUSED_C:
            with self.subTest(name=name):
                self.assertEqual(records[ps.asset_id(name)]["refusal_reason"], ps.REFUSED[name])
                self.assertTrue(ps.REFUSED[name].startswith("C: "))
                with self.assertRaisesRegex(ps.PresentationMarkError, f"{name} is refused: C: "):
                    ps.require_offered(name)
                # refused before any input is opened: neither path exists
                with self.assertRaisesRegex(ps.PresentationMarkError, "refused: C: "):
                    ps.build_unified_presentation_mark_imports(missing_index, ps.asset_id(name), missing_png)
        for name in ("espn1", "nflShield1"):
            with self.subTest(name=name), self.assertRaisesRegex(ps.PresentationMarkError, "DXT1"):
                ps.build_unified_presentation_mark_imports(missing_index, ps.asset_id(name), missing_png)
        with self.assertRaisesRegex(ps.PresentationMarkError, "no graded broadcast-still art"):
            ps.build_unified_presentation_mark_imports(missing_index, "p8:346:flare000", missing_png)
        with self.assertRaisesRegex(ps.PresentationMarkError, "not a GAMEDATA presentation target"):
            ps.build_unified_presentation_mark_imports(missing_index, "p8:346:not_a_texture", missing_png)

    def test_extension_records_carry_the_all_textures_proof_shape(self) -> None:
        from mod_editor.core.nfl2k5_p8_texture_writer import P8PhysicalSpan, P8Target, target_record
        piece = P8PhysicalSpan("0", "vc_53450030/0", 1, "0" * 64, 1, 0, 0, 1, "0" * 64)
        shipped_keys = set(target_record(P8Target(
            "p8:1:x", "x", "g", "x", 1, 0, "0", "vc_53450030/0", 1, "0" * 64, 1, 0, 1, "0" * 64,
            1, 1, 1, "P8", 1, True, "", (piece,))))
        for record in ps.extension_records().values():
            self.assertLessEqual(shipped_keys, set(record))
        record = ps.extension_records()["p8:346:shield_espn"]
        self.assertEqual(record["xiso_absolute_span_offset"], 796479 * 2048 + 0x6906050)
        self.assertEqual((record["physical_span_count"], record["replacement_offset"], record["selector"]),
                         (1, 0, "p8:346:shield_espn"))
        self.assertEqual((record["authored_grade"], record["refusal_reason"]), ("A", ""))

    def test_the_prefix_keeps_other_lanes_off_the_inventory_file(self) -> None:
        with mock.patch.object(ps, "load_standalone", side_effect=AssertionError("read the inventory")):
            self.assertFalse(ps.is_presentation_asset("p8:3136:pad_north"))
            self.assertFalse(ps.is_presentation_asset(None))
        self.assertTrue(ps.is_presentation_asset("p8:346:shield_espn"))
        self.assertFalse(ps.is_presentation_asset("p8:346:not_a_texture"))

    def test_extended_view_counts_when_the_private_inventory_is_present(self) -> None:
        from mod_editor.core.nfl2k5_p8_texture_writer import DEFAULT_REPORT, load_inventory
        if not DEFAULT_REPORT.is_file():
            self.skipTest("the private 11,395-target All Textures inventory is absent")
        shipped = load_inventory()
        view = ps.extended_standalone_inventory()
        self.assertEqual((len(shipped), len(view)), (11395, 11439))
        self.assertEqual(sum(bool(r.get("format_supported", True)) for r in view.values()), 11437)
        self.assertEqual(sum(bool(r.get("replacement_supported", True)) for r in view.values()), 11399)
        self.assertEqual(set(view) - set(shipped), {row["asset_id"] for row in ps.load_standalone()["targets"]})


class UnifiedProviderDispatchTests(unittest.TestCase):
    """The typed build sends p8:346 marks to this adapter and every other p8 id to All Textures."""

    def test_build_one_import_routes_by_asset_id(self) -> None:
        import nfl2k5_visual_mod_project as unified
        with tempfile.TemporaryDirectory(prefix="presentation-unified-") as raw:
            root = Path(raw)
            png = root / "mark.png"
            png.write_bytes(b"user-authored png input")
            project_path = root / "project.json"
            project_path.write_bytes(unified.canonical_json({
                "edits": [
                    {"kind": unified.P8_TEXTURE_KIND, "asset_id": "p8:346:shield_espn", "png": str(png)},
                    {"kind": unified.P8_TEXTURE_KIND, "asset_id": "p8:3136:pad_north", "png": str(png)},
                ],
                "purpose": "GAMEDATA presentation mark unified-provider contract test.",
                "schema": unified.SCHEMA,
            }))
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            work = root / "work"
            work.mkdir()
            owned_root = unified.ownership.track_existing(work, True)
            files: list = []
            mark = (b"mark span", [], {"target": {}}, "p8:346:shield_espn", {"selector": "p8:346:shield_espn"})
            other = (b"other span", [], {"target": {}}, "p8:3136:pad_north", {"selector": "p8:3136:pad_north"})
            try:
                with mock.patch.object(unified.presentation_adapter, "build_unified_presentation_mark_imports",
                                       return_value=[mark]) as marks, \
                        mock.patch.object(unified.p8_texture_adapter, "build_unified_p8_texture_import",
                                          return_value=other) as p8:
                    first = unified.build_one_import(0, project.value["edits"][0], project, pins, {},
                                                     root / "0", root / "inventory.json", owned_root, files, -1)
                    second = unified.build_one_import(1, project.value["edits"][1], project, pins, {},
                                                      root / "0", root / "inventory.json", owned_root, files, -1)
                self.assertEqual((first, second), (mark, other))
                self.assertEqual(marks.call_args.args[1], "p8:346:shield_espn")
                self.assertEqual(p8.call_args.args[1], "p8:3136:pad_north")
                self.assertEqual(Path(marks.call_args.args[2]).read_bytes(), png.read_bytes())
            finally:
                unified.ownership.cleanup_owned(files, [owned_root])

    def test_the_composed_prepare_path_dispatches_too(self) -> None:
        source = (ROOT / "tools" / "nfl2k5_visual_mod_project.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("presentation_adapter.is_presentation_asset(edit[\"asset_id\"])"), 2)
        self.assertEqual(source.count("presentation_adapter.build_unified_presentation_mark_imports("), 2)
        self.assertIn("presentation_adapter.PresentationMarkError", source)


def _official_marks_ready() -> bool:
    """mk: the real marks live only in the local official marks pack; these checks compare against its pinned bytes."""
    from mod_editor.core import nfl2k5_espn_marks
    return nfl2k5_espn_marks.available()


@unittest.skipUnless(INDEX.is_file(), "extracted retail vc_53450030 packs absent; set NFL2K5_GAME_DIR")
@unittest.skipUnless(_official_marks_ready(), "official marks pack absent; set NFL2K5_MARKS_PACK")
class RetailTypedBuildTests(unittest.TestCase):
    """The four real complete-resource writes, from the extracted retail index, against the shipped pins."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pins = {m["texture"]: m for m in json.loads(PINS.read_text(encoding="utf-8"))["marks"]}
        cls.built = {}
        for texture in MARKS:
            cls.built[texture] = ps.build_unified_presentation_mark_imports(
                INDEX, ps.asset_id(texture), art_path(f"{texture}.png"))

    def test_each_mark_matches_its_applied_pin_and_keeps_its_wrapper(self) -> None:
        for texture in MARKS:
            with self.subTest(texture=texture):
                (span, previews, record, selector, proof), = self.built[texture]
                pin = self.pins[texture]
                self.assertEqual(ps.digest(span), pin["applied_sha256"])
                self.assertEqual((len(span), selector, previews), (pin["span_size"], ps.asset_id(texture), []))
                self.assertEqual(proof["span_sha256"], pin["retail_sha256"])
                self.assertEqual(record["fill"], pin["fill"])
                self.assertTrue(record["authored_rgba_identical"] and record["wrapper_identical"])
                self.assertLessEqual(record["fill"]["exact_minimum_scratch"], record["fill"]["scratch_bytes"])
                self.assertEqual((record["archive_growth"], record["gamedata_growth"], record["runtime_witnessed"]),
                                 (0, 0, False))

    def test_unchanged_art_reproduces_the_research_receipt_numbers(self) -> None:
        expected = {"espnLogo1": (5068, 6194, 14, 16, 12), "z_ESPN_bug": (1206, 4021, 11, 80, 0),
                    "shield_espn": (1736, 5906, 14, 112, 4), "nfl_chiclet": (2792, 4332, 4, 144, 4)}
        for texture, numbers in expected.items():
            fill = self.built[texture][0][2]["fill"]
            self.assertEqual((fill["compressed_bytes"], fill["filled_bytes"], fill["padding_bytes"],
                              fill["scratch_bytes"], fill["exact_minimum_scratch"]), numbers, texture)

    def test_composed_gamedata_changes_only_the_four_chunks(self) -> None:
        from nfl_outer import parse_archive, read_entry_bytes
        from nfl_tset_png_import import decode_rgba_png
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(INDEX.parents[1])
        archive = parse_archive(INDEX)
        original = read_entry_bytes(archive, archive.entries[346])
        composed = bytearray(original)
        for texture in MARKS:
            pin = self.pins[texture]
            span = self.built[texture][0][0]
            composed[pin["chunk_offset"]:pin["chunk_offset"] + len(span)] = span
        composed = bytes(composed)
        self.assertEqual((len(original), len(composed)), (2977184, 2977184))
        chunks = parse_chunks(composed, allow_trailing=True)
        self.assertEqual(len(chunks), 139)
        changed = [c.index for c in chunks if composed[c.offset:c.end_offset] != original[c.offset:c.end_offset]]
        self.assertEqual(changed, [24, 26, 33, 57])
        for texture in MARKS:
            chunk = chunks[self.pins[texture]["chunk_index"]]
            decoded, _ = decode_chunk(composed, chunk)
            rgba = texture_to_rgba(decoded, chunk, parse_texture(decoded, chunk))
            png = (art_path(f"{texture}.png")).read_bytes()
            self.assertEqual(rgba, decode_rgba_png(png, (self.pins[texture]["width"], self.pins[texture]["height"]))[2])
            self.assertEqual(ps.digest(rgba), self.pins[texture]["rgba_sha256"])
            self.assertEqual(composed[chunk.offset:chunk.offset + 32], original[chunk.offset:chunk.offset + 32])


@unittest.skipUnless(RETAIL_XISO.is_file(), "retail NFL 2K5 XISO absent; set NFL2K5_RETAIL_XISO")
class RetailDerivationTests(unittest.TestCase):
    def test_the_pinned_inventory_rederives_byte_for_byte_from_the_disc(self) -> None:
        with ps.DiscArchive(RETAIL_XISO) as disc:
            document = ps.derive_standalone(disc)
        self.assertEqual(ps.canonical(document), ps.STANDALONE_PATH.read_bytes())
        self.assertEqual(document["archive_directory_sha256"],
                         "1b4c2af593e2b61d42b5afc3ad9c67433eee2af4fc16920f8a1538640c956b10")


if __name__ == "__main__":
    unittest.main()
