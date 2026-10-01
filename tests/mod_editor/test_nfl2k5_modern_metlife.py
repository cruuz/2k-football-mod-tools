"""Modern MetLife (experimental): rules, art, weather transfer, fixed-span refit, venue name and pins."""
from __future__ import annotations

import json
import os
import struct
import sys
import unittest
from official_marks_fixture import requires_real_pack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_modern_metlife as mm  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"


class RuleAndArtTests(unittest.TestCase):
    @requires_real_pack("modern_metlife")
    def test_every_rule_names_exact_size_art_and_the_pins_cover_it(self):
        rules = mm.rules()
        pins = json.loads(mm.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pins["schema"], mm.PINS_SCHEMA)
        self.assertEqual(pins["art"], mm.art_pins())
        self.assertEqual(pins["rules_sha256"], mm.sha(mm.RULES_PATH.read_bytes()))
        named = {item["art"] for kind in ("patches", "overlays") for item in rules[kind]}
        self.assertEqual(named, set(pins["art"]))
        from PIL import Image
        for rel in named:
            with Image.open(mm.official.resolve_path(mm.DATA_DIR / rel)) as image:
                width, height = image.size
            self.assertTrue(width & (width - 1) == 0 and height & (height - 1) == 0, rel)
            self.assertEqual(mm.art_rgba(rel, width, height).shape, (height, width, 4))
        for item in rules["palette_rules"]:
            self.assertIn(item["rule"], rules["palette_kinds"])
        # geometry: in the stadium only whole-shape collapses (every vertex to the retail sphere centre), no sphere
        # writes; in the field only b76-u5b's quad resize (the Giants' midfield helmet at its painted size)
        self.assertTrue(rules["geometry"])
        for item in rules["geometry"]:
            if item.get("scene", "stadium") == "field":
                self.assertEqual((item["mode"], item["material"]), ("quad", "center_logo"), item)
                self.assertIn(item["venues"], (["s18"], ["s19"]))
                self.assertEqual(item["retail_half_extent_m"], [4.233, 4.576])
                self.assertTrue(all(n >= r for n, r in zip(item["half_extent_m"], item["retail_half_extent_m"])))
            else:
                self.assertEqual(item["mode"], "collapse", item)
        self.assertEqual(sorted(item["marker"] for item in rules["markers"]),
                         sorted([f"marker_lightShape{k}" for k in range(1, 15)]
                                + ["marker_flare1Shape", "marker_flare2Shape", "marker_flareShape3", "marker_flareShape4"]))
        for item in rules["markers"]:
            self.assertTrue(isinstance(item["retail_sha256"], list) and item["retail_sha256"], item)
            self.assertEqual(len(item["position_m"]), 3)
            self.assertGreater(item["position_m"][1], 58.3)  # above the rim top

    def test_variants_and_name_ids(self):
        self.assertEqual(len(mm.VARIANTS), 18)
        self.assertEqual(mm.variant_parts("s19nr.iff"), ("s19", "n", "r"))
        self.assertEqual(mm.dry_name("s18as.iff"), "s18ad.iff")
        self.assertEqual(mm.name_id("s13nd.iff"), 0x03808CDC)  # the same engine hash Arrowhead pins


class TransferTests(unittest.TestCase):
    def test_affine_weather_transfer_maps_authored_art(self):
        import numpy as np
        rng = np.random.default_rng(3)
        dry = rng.integers(0, 256, (16, 16, 4), dtype=np.uint8)
        dry[..., 3] = 255
        wet = dry.copy()
        wet[..., :3] = np.clip(dry[..., :3].astype(int) * 0.9 + 5, 0, 255).astype(np.uint8)
        art = np.full((16, 16, 4), 200, dtype=np.uint8)
        out, fits = mm.weather_transfer(dry, wet, art)
        self.assertTrue(all(abs(g - 0.9) < 0.02 and abs(b - 5) < 2.5 for g, b in fits))
        self.assertTrue(abs(int(out[0, 0, 0]) - 185) <= 1)
        self.assertEqual(int(out[0, 0, 3]), 200)
        same, none = mm.weather_transfer(dry, dry, art)
        self.assertIsNone(none)
        self.assertTrue((same == art).all())

    def test_palette_rule_keeps_alpha_and_greys_the_seats(self):
        import numpy as np
        pal = np.zeros((256, 4), dtype=np.uint8)
        pal[0] = (95, 45, 40, 255)   # red-brown seat
        pal[1] = (150, 150, 150, 7)  # neutral aisle, odd alpha
        out = mm.palette_rule(pal, mm.rules()["palette_kinds"]["seat_charcoal"])
        r, g, b, a = (int(v) for v in out[0])
        self.assertLess(max(r, g, b) - min(r, g, b), 12)
        self.assertEqual(int(out[1, 3]), 7)

    def test_composite_over_keeps_base_where_overlay_is_clear(self):
        import numpy as np
        base = np.full((4, 4, 4), 100, dtype=np.uint8)
        over = np.zeros((4, 4, 4), dtype=np.uint8)
        over[0, 0] = (255, 0, 0, 255)
        out = mm.composite_over(base, over)
        self.assertEqual(tuple(int(v) for v in out[0, 0, :3]), (255, 0, 0))
        self.assertEqual(tuple(int(v) for v in out[1, 1, :3]), (100, 100, 100))


class BundleStateTests(unittest.TestCase):
    def test_states_from_site_hashes(self):
        class Entry:
            name_id, size, virtual_offset = 1, 8, 0

        class Archive:
            entries = [Entry()]

            def __init__(self, blob):
                self.blob = blob

            def read(self, at, size):
                return self.blob[at:at + size]

        pin = dict(name="x", outer=0, name_id=1, size=8,
                   sites=[dict(offset=0, size=4, retail=mm.sha(b"aaaa"), applied=mm.sha(b"bbbb")),
                          dict(offset=4, size=4, retail=mm.sha(b"cccc"), applied=mm.sha(b"dddd"))])
        self.assertEqual(mm._bundle_state(Archive(b"aaaacccc"), pin), "retail")
        self.assertEqual(mm._bundle_state(Archive(b"bbbbdddd"), pin), "applied")
        self.assertEqual(mm._bundle_state(Archive(b"aaaadddd"), pin), "mixed")
        self.assertEqual(mm._bundle_state(Archive(b"aaaazzzz"), pin), "foreign")


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RetailTests(unittest.TestCase):
    def _read(self, names):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with mm._outer_image()(PACKS) as archive:
            entries = mm.metlife_entries(archive)
            return {n: archive.read(entries[n].virtual_offset, entries[n].size) for n in names}

    @requires_real_pack("modern_metlife")
    def test_jets_rain_bundle_refit_matches_the_pins_and_keeps_every_wrapper(self):
        pins = {b["name"]: b for b in json.loads(mm.PINS_PATH.read_text(encoding="utf-8"))["bundles"]}
        data = self._read(["s19nr.iff", "s19nd.iff"])
        pin = pins["s19nr.iff"]
        self.assertEqual(mm.sha(data["s19nr.iff"]), pin["retail_sha256"])
        after, edits = mm.modern_bundle(data["s19nr.iff"], "s19nr.iff", data["s19nd.iff"])
        self.assertEqual(mm.sha(after), pin["applied_sha256"])
        self.assertEqual(len(after), len(data["s19nr.iff"]))
        for edit, site in zip(edits, pin["sites"]):
            self.assertEqual((edit["offset"], edit["size"], edit["before_sha256"], edit["after_sha256"]),
                             (site["offset"], site["size"], site["retail"], site["applied"]))
            # the whole 32-byte wrapper, loader scratch word included, is retail
            self.assertEqual(after[edit["offset"]:edit["offset"] + 32], data["s19nr.iff"][edit["offset"]:edit["offset"] + 32])
            self.assertLessEqual(edit["alias_scratch"], edit["scratch_bytes"])
        spans = [(e["offset"], e["offset"] + e["size"]) for e in edits]
        for at in range(0, len(after), 4096):
            if not any(a <= at < b for a, b in spans):
                self.assertEqual(after[at:at + 64], data["s19nr.iff"][at:at + 64], hex(at))

    @requires_real_pack("modern_metlife")
    def test_pins_cover_every_bundle_and_the_packs_read_as_retail(self):
        pins = json.loads(mm.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual([b["name"] for b in pins["bundles"]], list(mm.VARIANTS))
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with mm._outer_image()(PACKS) as archive:
            self.assertEqual(set(mm.metlife_entries(archive)), set(mm.VARIANTS))
            for pin in pins["bundles"]:
                self.assertEqual(mm._bundle_state(archive, pin), "retail", pin["name"])
        self.assertEqual(mm.image_status(PACKS), "retail")

    @requires_real_pack("modern_metlife")
    def test_giants_midfield_quad_moves_only_its_four_corners(self):
        """b76-u5b: the s18 field's center_logo quad grows to the painted helmet's size (16.8 x 14.8 yd), the s19
        one to the Jets' oval (15.2 x 9.26 yd); the four
        corner positions are the only system bytes that change outside the textures, and every corner keeps its
        signs (the UVs stay) and stays inside the D_graphic_overlays sphere."""
        import struct
        data = self._read(["s18dd.iff"])["s18dd.iff"]
        rec, decoded = mm._scene(data, mm.bundle_scenes(data)["field"])
        edited, receipt = mm.paint_scene(decoded, rec, "s18", "d", dry=None)
        self.assertEqual([(g["shape"], g["material"]) for g in receipt["geometry"]], [("D_graphic_overlays", "center_logo")])
        corners = receipt["geometry"][0]["corners_m"]
        self.assertEqual(sorted((round(abs(x), 3), round(abs(z), 3)) for x, y, z in corners), [(7.59, 7.681)] * 4)
        textures = set()
        for row in mm.texture_rows(rec).values():
            system = int(rec["system_bytes"])
            textures |= set(range(system + int(row["pixel_offset"]), system + int(row["palette_offset"]) + 1024))
        changed = [i for i in range(len(decoded)) if decoded[i] != edited[i] and i not in textures]
        self.assertLessEqual(len(changed), 4 * 12)
        data19 = self._read(["s19dd.iff"])["s19dd.iff"]
        rec19, dec19 = mm._scene(data19, mm.bundle_scenes(data19)["field"])
        _e19, receipt19 = mm.paint_scene(dec19, rec19, "s19", "d", dry=None)
        corners19 = receipt19["geometry"][0]["corners_m"]
        self.assertEqual(sorted((round(abs(x), 3), round(abs(z), 3)) for x, y, z in corners19), [(4.234, 6.949)] * 4)

    @requires_real_pack("modern_metlife")
    def test_stadium_system_bytes_change_only_in_collapsed_lanes_and_moved_markers(self):
        import struct
        from mod_editor.core import nfl2k5_models as models
        data = self._read(["s18dd.iff"])["s18dd.iff"]
        rec, decoded = mm._scene(data, mm.bundle_scenes(data)["stadium"])
        edited, receipt = mm.paint_scene(decoded, rec, "s18", "d", dry=None)
        shapes = {s["name"]: s for s in rec["shapes"]}
        markers = {m["name"]: m for m in rec["markers"]}
        self.assertEqual({g["shape"] for g in receipt["geometry"]},
                         {g["shape"] for g in mm.rules()["geometry"] if g.get("scene", "stadium") == "stadium"})
        allowed = set()
        for g in receipt["geometry"]:
            shape = shapes[g["shape"]]
            lanes, positions = mm._shape_positions(rec, shape, edited)
            centre = struct.unpack_from("<3f", edited, int(shape["record_offset"]))
            self.assertEqual({tuple(p) for p in positions}, {centre}, g["shape"])
            # the sphere (centre, w, radius) the culling reads is retail
            at = int(shape["record_offset"])
            self.assertEqual(edited[at:at + 16], decoded[at:at + 16])
            self.assertEqual(edited[at + 0x48:at + 0x4C], decoded[at + 0x48:at + 0x4C])
            base = models._stream_base({}, shape, lanes.position_stream)
            for k in range(len(positions)):
                start = base + k * lanes.position_stride + lanes.position_offset
                allowed |= set(range(start, start + 12))
        for m in receipt["markers"]:
            start = int(markers[m["marker"]]["record_offset"]) + mm.MARKER_POSITION
            self.assertEqual(struct.unpack_from("<3f", edited, start),
                             tuple(struct.unpack("<f", struct.pack("<f", v * 100.0))[0] for v in m["position_m"]))
            allowed |= set(range(start, start + 12))
        self.assertEqual(len(receipt["markers"]), 18)
        system = int(rec["system_bytes"])
        changed = {i for i in range(system) if decoded[i] != edited[i]}
        self.assertTrue(changed and changed <= allowed)
        collapsed = {g["shape"] for g in receipt["geometry"]}
        for shape in rec["shapes"]:
            if shape["name"] in collapsed:
                continue
            try:
                _l, before = mm._shape_positions(rec, shape, decoded)
            except mm.ModernMetLifeError:
                continue
            _l, after = mm._shape_positions(rec, shape, edited)
            self.assertEqual([tuple(p) for p in before], [tuple(p) for p in after], shape["name"])

    def test_venue_rename_changes_only_two_string_blocks_and_ten_pointers(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        with mm._outer_image()(PACKS) as archive:
            entry = archive.entries[mm.ROST_OUTER_INDEX]
            rost = archive.read(entry.virtual_offset, entry.size)
        self.assertEqual(mm.rost_status(rost), "retail")
        after, receipt = mm.rost_rename(rost)
        pins = json.loads(mm.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(mm.sha(after), pins["rost"]["applied_sha256"])
        self.assertEqual(mm.rost_status(after), "applied")
        self.assertEqual(len(after), len(rost))
        from mod_editor.core import nfl2k5_roster_records as rr
        header = rr.RESOURCE_HEADER_SIZE
        allowed = set()
        for record in receipt["records"]:
            start, end = record["block"]
            allowed |= set(range(header + start, header + end))
            allowed |= {header + record["record_offset"] + f + k for f, _n in mm.ROST_STRING_FIELDS for k in range(4)}
        changed = {i for i, (a, b) in enumerate(zip(rost, after)) if a != b}
        self.assertTrue(changed <= allowed)
        again, second = mm.rost_rename(after)
        self.assertEqual(again, after)
        self.assertEqual({r["state"] for r in second["records"]}, {"already_applied"})
        # every other stadium keeps its name, and the asset codes (the engine's file-name keys) stay
        body = after[header:]
        codes = {fields["asset_code"][1]: fields for _o, fields in mm._stadium_records(body)}
        self.assertEqual(codes["s18"]["asset_code"][1], "s18")
        self.assertEqual(codes["s19"]["asset_code"][1], "s19")
        self.assertEqual(codes["s13"]["name"][1], "Arrowhead Stadium")

@unittest.skipUnless(PACKS.is_dir(), "retail extraction not available")
class RostCompositionTests(unittest.TestCase):
    """b76-u5b: the league roster edits turned player 515's +0x20 bit-field word into a value that reads as a
    self-relative pointer into "Giants Stadium", and the rename refused the whole build. A player's data word is not
    a pointer; a real string pointer into the block still refuses; the MetLife rename and the 2026 venues' rename
    compose in either order."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_roster_records as rr
        cls.rr = rr
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(GAME)
        with mm._outer_image()(str(GAME)) as archive:
            entry = archive.entries[mm.ROST_OUTER_INDEX]
            cls.retail = archive.read(entry.virtual_offset, entry.size)
        body = cls.retail[rr.RESOURCE_HEADER_SIZE:]
        fields = {f["asset_code"][1]: f for _o, f in mm._stadium_records(body)}
        cls.block = mm._string_block(fields["s18"])
        cls.player = min(p.offset for p in rr.RosterDocument(body, base=0).players if p.pool == "primary")

    def _with_word(self, field, target):
        header = self.rr.RESOURCE_HEADER_SIZE
        data = bytearray(self.retail)
        at = header + self.player + field
        struct.pack_into("<i", data, at, target - (self.player + field) + 1)
        return bytes(data), at

    def test_a_player_data_word_that_reads_as_a_pointer_does_not_block_the_rename(self):
        data, at = self._with_word(0x20, self.block[0] + 24)
        after, receipt = mm.rost_rename(data)
        self.assertEqual(mm.rost_status(after), "applied")
        self.assertEqual(after[at:at + 4], data[at:at + 4])
        self.assertEqual([r["state"] for r in receipt["records"]], ["applied", "applied"])

    def test_a_real_string_pointer_into_the_block_still_refuses(self):
        data, _at = self._with_word(0x14, self.block[0])          # the player's last-name pointer
        with self.assertRaisesRegex(mm.ModernMetLifeError, "other pointers reach the stadium strings"):
            mm.rost_rename(data)

    def test_the_two_renames_compose_in_either_order(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        data, _at = self._with_word(0x20, self.block[0] + 24)
        a = mm.rost_rename(mv.rost_rename(data)[0])[0]
        b = mv.rost_rename(mm.rost_rename(data)[0])[0]
        self.assertEqual(a, b)
        self.assertEqual((mm.rost_status(a), mv.rost_state(a)), ("applied", "applied"))

    def _with_history_pointer(self):
        from mod_editor.core import nfl2k5_team_history as history
        data = bytearray(self.retail)
        header = self.rr.RESOURCE_HEADER_SIZE
        roster = history.parse_body(data[header:])
        # Replace a non-terminal stat, preserving the stream's termination/shape.
        field = next(p.stream for p in roster.players if len(p.entries) > 1)
        struct.pack_into("<i", data, header + field, self.block[0] - field + 1)
        history.parse_body(data[header:])
        return data, roster, field

    def test_history_stat_that_reads_as_pointer_is_ignored_and_preserved(self):
        data, roster, field = self._with_history_pointer()
        self.assertIn(field, mm._history_data_words(data[self.rr.RESOURCE_HEADER_SIZE:]))
        after, _ = mm.rost_rename(data)
        self.assertEqual(mm.rost_status(after), "applied")
        start = self.rr.RESOURCE_HEADER_SIZE + roster.pool
        end = start + roster.used * 4
        self.assertEqual(after[start:end], data[start:end])

    def test_real_pointer_outside_history_still_refuses_with_history_stat_present(self):
        data, _roster, _field = self._with_history_pointer()
        field = self.player + 0x14  # a real last-name pointer, never a data exemption
        struct.pack_into("<i", data, self.rr.RESOURCE_HEADER_SIZE + field,
                         self.block[0] - field + 1)
        with self.assertRaisesRegex(mm.ModernMetLifeError, "other pointers reach the stadium strings"):
            mm.rost_rename(data)

    def test_unused_history_capacity_is_not_exempt(self):
        data, roster, _field = self._with_history_pointer()
        field = roster.pool + roster.used * 4
        struct.pack_into("<i", data, self.rr.RESOURCE_HEADER_SIZE + field,
                         self.block[0] - field + 1)
        self.assertNotIn(field, mm._history_data_words(data[self.rr.RESOURCE_HEADER_SIZE:]))
        with self.assertRaisesRegex(mm.ModernMetLifeError, "other pointers reach the stadium strings"):
            mm.rost_rename(data)

    def test_malformed_history_keeps_the_pointer_scan(self):
        from mod_editor.core import nfl2k5_team_history as history
        data, roster, field = self._with_history_pointer()
        header = self.rr.RESOURCE_HEADER_SIZE
        struct.pack_into("<I", data, header + history.OBJ_OFF + 0x40, roster.used + 1)
        self.assertEqual(mm._history_data_words(data[header:]), frozenset())
        self.assertIn(field, mm._pointers_into(data[header:], *self.block, set()))
        with self.assertRaisesRegex(mm.ModernMetLifeError, "other pointers reach the stadium strings"):
            mm.rost_rename(data)

    def test_unparseable_body_keeps_the_pointer_scan(self):
        data = bytearray(64)
        struct.pack_into("<i", data, 4, 40 - 4 + 1)
        self.assertEqual(mm._pointers_into(data, 40, 44, set()), [4])


if __name__ == "__main__":
    unittest.main()
