"""b775-ek1: game-accurate Anniversary uniforms as NEW kit slots (Noah 10/17).

Static tests check the data, the stage order and the shared-status hook (historic spares never pick an ek1 index). The disc tests read the release-candidate test disc
(read only): every new index is free there, the composition equals the pins, the moment sides switch, modern Team
Select labels are untouched, and the stage's applied state (an in-memory overlay of its edits) reads back as
'applied' and refuses to install twice.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_moment_kits as mk  # noqa: E402

DISC = Path(os.environ.get("B775_EK1_DISC",
                           "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"))
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Data(unittest.TestCase):
    def test_document_validates_and_every_selection_is_wired(self):
        doc = mk.document()
        self.assertEqual(len(doc["kits"]), 10)
        self.assertEqual(len(doc["selections"]), 15)
        by_id = {k["id"]: k for k in doc["kits"]}
        for kit in doc["kits"]:
            users = [(s["row"], s["side"]) for s in doc["selections"] if s.get("kit") == kit["id"]]
            self.assertEqual(sorted(users), sorted(tuple(m) for m in kit["moments"]), kit["id"])
        for s in doc["selections"]:
            if "kit" in s:
                self.assertEqual(s["style"], by_id[s["kit"]]["style"])
            self.assertNotEqual(s["before"], s["style"])

    def test_the_giants_super_bowl_road_kit_is_noahs_look(self):
        k1 = next(k for k in mk.document()["kits"] if k["id"] == "K1")
        a = mk._expand(k1["sides"]["A"]["chunks"])
        # red numerals with no outline, red name and sleeve stripes from the 2026 road set; grey pants (chunk 2),
        # helmet (11, 12) and helmet numbers from the Reebok-era road kit
        self.assertTrue(all(a[i] == "18A0" for i in [1, 3, 4, *range(13, 23), *range(33, 45)]))
        self.assertNotIn(2, a)
        self.assertNotIn(11, a)
        self.assertEqual(k1["sides"]["A"]["base"], "18A8")
        self.assertEqual(sorted(map(tuple, k1["moments"])), [(27, "away"), (29, "away")])

    def test_cards_rename_existing_members(self):
        k1 = next(k for k in mk.document()["kits"] if k["id"] == "K1")
        cards = mk.card_sources(k1)
        self.assertEqual(cards["unif_a18_9"], ("logos", "unif_a18_0"))
        self.assertEqual(cards["helm_a18_9"], ("logos", "helm_a18_8"))
        self.assertEqual(cards["unif_h18_9"], ("logos", "unif_h18_8"))
        self.assertEqual(cards["18_flipchip_00_h9"], ("flipchip", "18_flipchip_00_h8"))
        self.assertEqual(len(cards), 9)
        k3 = next(k for k in mk.document()["kits"] if k["id"] == "K3")
        swapped = mk.card_sources(k3)
        self.assertEqual(swapped["unif_h29_10"], ("logos", "unif_a29_2"))   # white at home
        self.assertEqual(swapped["unif_a29_10"], ("logos", "unif_h29_2"))   # burgundy on the road

    def test_palette_map_keeps_shading_and_white_blends_exactly(self):
        import numpy as np
        pal = np.zeros((256, 4), np.int64)
        pal[:, 3] = 255
        pal[:7, :3] = [(0, 46, 102), (0, 31, 82), (255, 61, 0), (253, 227, 223), (255, 255, 255), (0, 0, 0), (240, 57, 0)]
        out = mk.map_entries(pal, [{"from": "#002E66", "to": "#FB4F14"}, {"from": "#FF3D00", "to": "#002E66"}], 12)
        self.assertEqual(out[:7, :3].tolist(), [[251, 79, 20], [203, 64, 16], [0, 46, 102], [222, 227, 234],
                                                [255, 255, 255], [0, 0, 0], [0, 43, 96]])
        self.assertTrue((out[7:] == pal[7:]).all())

    def test_expand_ranges(self):
        self.assertEqual(mk._expand({"13-15": "X", "2": "Y"}), {13: "X", 14: "X", 15: "X", 2: "Y"})
        with self.assertRaises(ValueError):
            mk._expand({"1-3": "X", "2": "Y"})

    def test_pins_follow_the_data(self):
        pins = mk.pins()
        names = {mk.package_name(k["code"], l, k["style"]) for k in mk.document()["kits"] for l in "HA"}
        self.assertEqual(set(pins["packages"]), names)
        self.assertEqual(set(pins["donors"]), set(mk.donors()))


class Wiring(unittest.TestCase):
    def test_runs_after_every_uniform_writer_and_before_the_roster_steps(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = source.index("kits_receipt = moment_kits.apply_to_image(target)")
        for earlier in ("styles_receipt = styles.apply_to_image(target, retail)",
                        "era_receipt = era_kits.apply_to_image(target",
                        "uniforms_receipt = uniforms.apply_to_image(target)",
                        "overlap_receipt = kit_fixes.apply_overlaps(target)",
                        "hem_receipt = pants_hem.apply_to_image(target)"):
            self.assertGreater(at, source.index(earlier), earlier)
        self.assertLess(at, source.index("_apply_roster_refresh(plan, target, receipt, progress)\n    _apply_draft"))
        self.assertIn('if _core_module("nfl2k5_moment_kits").image_status(target) != "applied":', source)

    def test_historic_spares_never_take_an_ek1_index(self):
        # Browns and Chiefs have no spare: their first free index used to be the ek1 index
        styles = {"30": 5, "13": 6, "18": 8}
        taken = {}
        for code, index in mk.reserved_styles():
            if code in styles and index >= styles[code]:
                taken.setdefault(code, set()).add(index)
        self.assertEqual(hs.spare_style("30", styles, taken), 6)
        self.assertEqual(hs.spare_style("13", styles, taken), 7)
        self.assertEqual(hs.spare_style("18", styles, taken), 8)

    def test_added_pairs_are_only_the_new_kit_labels(self):
        added = mk.added_pairs()
        self.assertEqual(added["h-29-1982-redskins-2.iff"], {10: (1979, 1983)})
        self.assertNotIn("h-11-1970-colts-5.iff", added)            # reuse of an existing style: nothing added


@unittest.skipUnless(DISC.is_file(), "release-candidate test disc absent")
class Disc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = mk.document()
        cls.src = hs.Source(DISC)
        cls.inputs = mk.read_inputs(cls.src, cls.doc)

    @classmethod
    def tearDownClass(cls):
        cls.src.__exit__(None, None, None)

    def test_the_copy_is_retail_for_this_stage_and_every_index_is_free(self):
        self.assertEqual(mk.state_of(self.doc, self.inputs, self.src), "retail")
        hashes = {a["name"]: set(hs.parse_record(self.src.get(identity=a["record"]))[2]) for a in hs.AGGREGATES}
        for kit in self.doc["kits"]:
            for letter in "HA":
                self.assertFalse(self.src.has(mk.package_name(kit["code"], letter, kit["style"])))
            for new, (aggregate, old) in mk.card_sources(kit).items():
                self.assertNotIn(hs.member_hash(new), hashes[aggregate], new)
                self.assertIn(hs.member_hash(old), hashes[aggregate], old)

    def test_modern_team_select_never_offers_a_new_index(self):
        for kit in self.doc["kits"]:
            self.assertEqual(mk.main_label(self.inputs["main"], kit["code"], kit["style"]), (0, 0), kit["id"])

    def test_composition_equals_the_pins_and_fits_existing_allocations(self):
        pins = mk.pins()
        for selector, data in self.inputs["packages"].items():
            self.assertEqual(sha(data), pins["donors"][selector], selector)
        packages, members, files, situ = mk.expected(self.doc, self.inputs)
        self.assertEqual({n: sha(d) for n, d in packages.items()}, pins["packages"])
        self.assertEqual({a: {n: sha(s) for n, s in m.items()} for a, m in members.items()}, pins["members"])
        self.assertEqual(sha(situ), pins["situ"]["after_sha256"])
        for name, data in files.items():
            self.assertEqual(sha(data), pins["team_files"][name]["after_sha256"], name)

    def test_whole_kit_copies_and_swaps_are_byte_copies(self):
        packages = mk.compose(self.doc, self.inputs["packages"])
        p = self.inputs["packages"]
        self.assertEqual(packages["29h10.iff"], p["29A2"])
        self.assertEqual(packages["29a10.iff"], p["29H2"])
        self.assertEqual(packages["20a6.iff"], p["20H1"])
        self.assertEqual(packages["08a8.iff"], p["08H1"])
        self.assertEqual(packages["18h9.iff"], p["18H8"])

    def test_giants_road_numerals_have_no_outline(self):
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        raw = mk.compose(self.doc, self.inputs["packages"])["18a9.iff"]
        chunks = parse_chunks(raw)
        for index in range(13, 23):
            decoded, _ = decode_chunk(raw, chunks[index])
            t = parse_texture(decoded, chunks[index])
            rgba = texture_to_rgba(decoded, chunks[index], t)
            colours = {tuple(rgba[i:i + 3]) for i in range(0, len(rgba), 4) if rgba[i + 3] > 200}
            self.assertTrue(colours, index)
            # every opaque texel is red (no blue outline): red dominant, blue low
            self.assertTrue(all(r > 120 and b < 110 and r > 2 * g for r, g, b in colours), index)

    def test_broncos_2012_home_is_orange_with_navy_panels(self):
        from nfl_txtr import decode_chunk, parse_chunks
        from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
        raw = mk.compose(self.doc, self.inputs["packages"])["08h9.iff"]
        span = raw[parse_chunks(raw)[1].offset:parse_chunks(raw)[1].end_offset]
        chunk, decoded, textures = fixes.native_textures(span, "tset")
        palette = fixes.read_palette(decoded, chunk, textures[0])
        plane = fixes.read_planes(decoded, chunk, textures[0])[0]
        rgb = palette[plane][..., :3].reshape(-1, 3)
        orange = ((rgb[:, 0] > 200) & (rgb[:, 2] < 60)).sum()
        navy = ((rgb[:, 0] < 30) & (rgb[:, 2] > 80)).sum()
        self.assertGreater(orange, 2 * navy)                 # orange body
        self.assertGreater(navy, rgb.shape[0] // 20)         # navy side panels and collar

    def test_selections_and_labels(self):
        _packages, _members, files, situ = mk.expected(self.doc, self.inputs)
        sides = {(row + 1, side): kit for row, side, _s, _y, kit, _f in hs.situ_sides(situ)}
        before = {(row + 1, side): kit for row, side, _s, _y, kit, _f in hs.situ_sides(self.inputs["situ"])}
        for s in self.doc["selections"]:
            self.assertEqual(before[(s["row"], s["side"])], s["before"])
            self.assertEqual(sides[(s["row"], s["side"])], s["style"])
        changed = {k for k in sides if sides[k] != before[k]}
        self.assertEqual(changed, {(s["row"], s["side"]) for s in self.doc["selections"]})
        for s in self.doc["selections"]:
            _code, _t, pairs = mk._team_file_pairs(files[s["file"]])
            self.assertNotEqual(pairs[s["style"] - 1], (0, 0), s)
        # only year pairs and the default style byte change in a team file
        defaults = {c["file"]: c["style"] for c in self.doc["classic_defaults"]}
        for name, data in files.items():
            old = self.inputs["files"][name]
            diff = [i for i in range(len(old)) if old[i] != data[i]]
            _code, t, _pairs = mk._team_file_pairs(old)
            self.assertTrue(all(t + hs.TABLE <= i < t + hs.TABLE + 56 or i == t + hs.STYLE for i in diff), name)
            if name in defaults:
                self.assertEqual(old[t + hs.STYLE], next(c["before"] for c in self.doc["classic_defaults"]
                                                         if c["file"] == name))
                self.assertEqual(data[t + hs.STYLE], defaults[name])
                self.assertNotEqual(defaults[name], 0)        # never style 0: historic_styles owns those files

    def test_classic_defaults_follow_the_moment_kit(self):
        situ = mk.expected(self.doc, self.inputs)[3]
        sides = {(row + 1, side): kit for row, side, _s, _y, kit, _f in hs.situ_sides(situ)}
        for c in self.doc["classic_defaults"]:
            if c["file"] == "h-07-1977-cowboys-3.iff":
                continue                                       # two moments; the white-home 1979 set is chosen
            rows = [part.split() for part in c["why"].split("row(s) ")[1].split(", ")]
            self.assertTrue(all(sides[(int(r), sd)] == c["style"] for r, sd in rows), c)

    def test_applied_overlay_reads_back_applied_and_refuses_a_second_install(self):
        packages, members, files, situ = mk.expected(self.doc, self.inputs)
        overlay = Overlay(self.src)
        for a in hs.AGGREGATES:
            record, cdf = self.inputs["members"][a["name"]]
            record, cdf = hs.grow_aggregate(record, cdf, members[a["name"]])
            overlay.put(identity=a["record"], data=record)
            overlay.put(identity=a["cdf"], data=cdf)
        for name, data in {**files, **packages}.items():
            overlay.put(name=name, data=data)
        overlay.put(identity=hs.SITU_OUTER_ID, data=situ)
        applied = mk.read_inputs(overlay, self.doc)
        self.assertEqual(mk.state_of(self.doc, applied, overlay), "applied")
        with self.assertRaises(ValueError):
            mk.compile_edits(overlay, self.doc, applied)
        # one changed byte in a new kit is foreign
        bad = bytearray(packages["30h5.iff"])
        bad[-1] ^= 1
        overlay.put(name="30h5.iff", data=bytes(bad))
        self.assertEqual(mk.state_of(self.doc, mk.read_inputs(overlay, self.doc), overlay), "foreign")

    @unittest.skipUnless(RETAIL.is_file(), "retail disc absent")
    def test_historic_spares_still_read_applied(self):
        self.assertEqual(hs.image_status(DISC, RETAIL), "applied")


class Overlay:
    """Name/identity reads from a disc with in-memory replacements (the stage's edits, without writing)."""

    def __init__(self, source):
        self.source, self.data = source, {}

    def put(self, *, name=None, identity=None, data):
        self.data[hs.name_id(name) if identity is None else identity] = data

    def _key(self, name, identity):
        return hs.name_id(name) if identity is None else identity

    def has(self, name):
        return self._key(name, None) in self.data or self.source.has(name)

    def get(self, name=None, *, identity=None):
        key = self._key(name, identity)
        return self.data[key] if key in self.data else self.source.get(name, identity=identity)

    def outer(self, name=None, *, identity=None):
        return self._key(name, identity)


if __name__ == "__main__":
    unittest.main()
