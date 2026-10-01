"""The board kit (st3, job st5): the tier 2 renovations of the retail stadiums the teams still play in. The data files
(one reader for every venue), the boards' published sizes, the feed crop and the loop-gain colour, the renovated
scenes (sizes, budgets, pins, kept textures and materials, the old boards gone, the markers on the new boards), the
composition with the 2026 venue art, Modern colour and Modern surfaces, and the Build option's wiring."""
import json
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core import nfl2k5_board_kit as bk  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
FT = 0.3048
VENUES = bk.venues()
#: the published size of every path board, feet (width, height): a venue joins the kit with its row here
FACTS = {
    "s02": {"bk_board_n": (200, 36), "bk_board_s": (200, 36),      # M&T Bank Stadium, 2017: the end-zone boards
            "bk_board_ne": (33, 44), "bk_board_nw": (33, 44),      # and the corner notch suites' boards (2018-19)
            "bk_board_se": (33, 44), "bk_board_sw": (33, 44)},
    "s04": {"bk_board_n": (199, 56), "bk_board_s": (199, 56)},     # Bank of America Stadium, 2014
    "s06": {"bk_board_nw": (130, 36), "bk_board_s": (130, 36)},    # Paycor Stadium, 2015
    "s08": {"bk_board_s": (225, 72),                               # Empower Field at Mile High, 2023
            "bk_board_nw": (98, 30), "bk_board_ne": (98, 30)},     # its north corner displays (Daktronics, May 2023)
    "s09": {"bk_board_e": (152, 39.5), "bk_board_w": (152, 39.5),  # Ford Field, 2017: the end-zone boards
            "bk_board_en": (59, 13), "bk_board_es": (59, 13),      # and the four displays flanking them
            "bk_board_wn": (59, 13), "bk_board_ws": (59, 13)},
    "s13": {"bk_board_w": (150, 37)},                               # Arrowhead Stadium, 2019: the west board
    "s17": {"bk_board_n": (333, 38), "bk_board_s": (333, 38)},     # Caesars Superdome, 2016 (the team's figure)
    "s21": {"bk_board_n": (192, 27), "bk_board_s": (160, 27)},     # Lincoln Financial Field, 2014
    "s22": {"bk_board_nw": (72, 35)},                               # Acrisure Stadium, 2014: the northwest board
    "s26": {"bk_board_ne": (70.34, 39.9), "bk_board_nw": (70.34, 39.9)},  # Lumen Field, 2022: the north pair
    "s27": {"bk_board_n": (160, 60), "bk_board_s": (160, 60),      # Raymond James Stadium, 2016: the end boards
            "bk_board_nw": (43, 61), "bk_board_ne": (43, 61),    # and the four corner displays
            "bk_board_sw": (43, 61), "bk_board_se": (43, 61)},
    "s29": {"bk_board_n": (95.1, 27.3), "bk_board_s": (95.1, 27.3)},  # Northwest Stadium, 2023
    "s37": {"bk_board_n": (277, 52), "bk_board_s": (277, 52)},     # NRG Stadium, 2013
}
#: outline boards, feet: (height, [(height above the bottom, width at that height)])
OUTLINE_FACTS = {
    "s30": (40, [(0.0, 132), (20.0, 178), (40.0, 192)]),           # Huntington Bank Field, 2014
}


def _aspect(board):
    if "outline" in board:
        O = np.array(board["outline"], float)
        return float(np.ptp(O[:, 0]) / np.ptp(O[:, 1]))
    return float(board["width"]) / bk.board_height(board)


class Data(unittest.TestCase):
    def test_every_venue_reads_through_the_one_reader(self):
        self.assertTrue({"s08", "s17", "s30", "s37"} <= set(VENUES))
        self.assertEqual(bk.pinned_venues(), VENUES)
        for venue in VENUES:
            doc = bk.spec(venue)
            self.assertEqual((doc["schema"], doc["venue"]), (bk.SCHEMA, venue))
            names = [b["name"] for b in doc["boards"]]
            self.assertTrue(names and all(n.startswith("bk_board_") for n in names), venue)
            self.assertEqual(len(names), len(set(names)), venue)
            self.assertTrue(doc["sources"], venue)
            self.assertIsNone(doc.get("env"), venue)          # closed bowls: every camera is inside (accepted by main)
            self.assertTrue(set(doc["markers"].values()) <= set(names), venue)

    def test_the_reader_refuses_what_it_does_not_know(self):
        import tempfile
        from unittest import mock
        doc = json.loads((bk.DATA_DIR / "s08.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            for change in ({"env": {"style": "desert"}}, {"ribbon": []}, {"help": ""}):
                (Path(tmp) / "s08.json").write_text(json.dumps(dict(doc, **change)), encoding="utf-8")
                with mock.patch.object(bk, "DATA_DIR", Path(tmp)):
                    bk.spec.cache_clear()
                    with self.assertRaises(sb.ScneBuildError, msg=change):
                        bk.spec("s08")
        bk.spec.cache_clear()
        self.assertEqual(bk.spec("s08")["venue"], "s08")

    def test_the_help_names_every_venue(self):
        for venue in VENUES:
            doc = bk.spec(venue)
            self.assertIn(f"{doc['name']} ({doc['help']})", bk.HELP_TEXT)

    def test_the_boards_have_their_published_sizes(self):
        for venue in VENUES:
            boards = {b["name"]: b for b in bk.spec(venue)["boards"]}
            paths = {n for n, b in boards.items() if "outline" not in b}
            self.assertEqual(set(FACTS.get(venue, {})), paths, f"{venue}: every path board needs its published size")
            for name in paths:
                w, h = FACTS[venue][name]
                b = boards[name]
                self.assertAlmostEqual(float(b["width"]), w * FT, delta=0.01, msg=(venue, name))
                self.assertAlmostEqual(bk.board_height(b), h * FT, delta=0.01, msg=(venue, name))   # slant with lean
            outlines = [b for b in boards.values() if "outline" in b]
            self.assertEqual(bool(outlines), venue in OUTLINE_FACTS, venue)
            for board in outlines:
                height, widths = OUTLINE_FACTS[venue]
                O = np.array(board["outline"], float)
                self.assertAlmostEqual(float(np.ptp(O[:, 1])), height * FT, delta=0.01)
                self.assertAlmostEqual(float(np.ptp(O[:, 1])), float(board["y"][1]) - float(board["y"][0]), delta=0.01)
                for h, w in widths:
                    xs = []
                    for (s0, h0), (s1, h1) in zip(O, np.roll(O, -1, axis=0)):
                        if min(h0, h1) - 1e-6 <= h * FT <= max(h0, h1) + 1e-6:
                            xs += [s0, s1] if abs(h1 - h0) < 1e-9 else [s0 + (s1 - s0) * (h * FT - h0) / (h1 - h0)]
                    self.assertAlmostEqual(max(xs) - min(xs), w * FT, delta=0.02, msg=(board["name"], h))

    def test_the_feed_crop_keeps_each_board_aspect(self):
        for venue in VENUES:
            for board in bk.spec(venue)["boards"]:
                a = _aspect(board)
                u0, u1, v0, v1 = bk.feed_crop(a)
                self.assertTrue(0 <= u0 < u1 <= bk.FEED_U + 1e-9 and 0 <= v0 < v1 <= bk.FEED_V + 1e-9, board["name"])
                # in render-target pixels (1024 x 512): the window has the board's own aspect, never stretched
                self.assertAlmostEqual((u1 - u0) * 1024 / ((v1 - v0) * 512), a, places=6)
                self.assertTrue(abs(u1 - u0 - bk.FEED_U) < 1e-9 or abs(v1 - v0 - bk.FEED_V) < 1e-9)

    def test_the_loop_gain_rule(self):
        self.assertEqual(bk.FEED_VERTEX, 116)

    def test_path_boards_face_the_field_and_span_their_width(self):
        for venue in VENUES:
            for board in bk.spec(venue)["boards"]:
                if "outline" in board:
                    continue
                pts, nrm, ts = bk.board_geometry(board)
                self.assertAlmostEqual(float(ts[-1]), float(board["width"]), places=6)
                for p, n in zip(pts, nrm):
                    self.assertGreater(float(np.dot(n, -p)), 0, (venue, board["name"]))


class _Entry:
    def __init__(self, pin):
        self.virtual_offset, self.size, self.name_id, self.index = 0, pin["size"], pin["name_id"], pin["outer"]


class _Archive:
    """One bundle at the outer index its 2026 venue table pin names."""

    def __init__(self, pin, data):
        self.entries = [None] * pin["outer"] + [_Entry(pin)]
        self.data = bytes(data)

    def read(self, offset, size):
        return self.data[offset:offset + size]


def _scene(data):
    ml = bk._ml()
    c = ml.bundle_scenes(data)["stadium"]
    _rec, dec = ml._scene(data, c)
    return sb.parse(dec, c.system_bytes)


def _textures(sc):
    return [(bytes(t.record[0x0C:0x10]), t.pixels, t.palette) for t in sc.textures]


def _static(sc):
    for s in sc.shapes:
        if struct.unpack_from("<I", s.record, 0x84)[0] == 0x32 and s.stride(1) == 10:
            yield s


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Scenes(unittest.TestCase):
    """The dry-day bundle of each venue and one night snow bundle, renovated from retail."""

    @classmethod
    def setUpClass(cls):
        cls.retail, cls.out, cls.info = {}, {}, {}
        for venue in VENUES:
            data = bk.read_retail(EXTRACTED, venue)
            for name in (f"{venue}dd.iff",) + (("s30ns.iff",) if venue == "s30" else ()):
                cls.retail[name] = data[name]
                cls.out[name], cls.info[name] = bk.model_bundle(data[name], name)

    def test_the_bundles_keep_their_size_and_the_scenes_stay_under_retail(self):
        for name, out in self.out.items():
            info = self.info[name]
            self.assertEqual(len(out), len(self.retail[name]), name)
            a, b = info["stretch"]
            self.assertEqual(out[:a], self.retail[name][:a], name)
            self.assertEqual(out[b:], self.retail[name][b:], name)
            # under retail with room to spare (Cleveland's ribbons and fan area leave 3.9 KB at the tightest)
            self.assertLess(info["system"] + info["video"], info["retail_system"] + info["retail_video"] - 2048, name)

    def test_the_compiled_stretches_equal_their_pins(self):
        for name, out in self.out.items():
            pin = bk._pin(name)
            a, b = self.info[name]["stretch"]
            self.assertEqual((pin["offset"], pin["length"], pin["size"]), (a, b - a, len(out)), name)
            self.assertEqual(bk.sha(out[a:b]), pin["model_sha256"], name)
            self.assertEqual(bk.sha(self.retail[name][a:b]), pin["retail_sha256"], name)

    def test_every_texture_and_material_is_kept(self):
        """Every material, and every texture but the freed slots the ribbons' art repaints."""
        for name, out in self.out.items():
            before, after = _scene(self.retail[name]), _scene(out)
            self.assertEqual([m.name for m in after.materials], [m.name for m in before.materials], name)
            painted = set(self.info[name]["painted"])
            keep = [k for k in range(len(before.textures)) if k not in painted]
            self.assertEqual([_textures(after)[k] for k in keep], [_textures(before)[k] for k in keep], name)
            self.assertEqual(len(after.textures), len(before.textures), name)
            for k in painted:
                self.assertNotEqual(_textures(after)[k], _textures(before)[k], name)

    def test_the_feed_is_at_the_loop_gain_colour_and_cropped_to_the_board(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for name, out in self.out.items():
            sc = _scene(out)
            boards = {b["name"]: b for b in bk.spec(name[:3])["boards"]}
            seen = set()
            for s in _static(sc):
                if s.name not in boards:
                    continue
                seen.add(s.name)
                _P, C, UV = sm._vertices(s)
                u0, u1, v0, v1 = bk.feed_crop(_aspect(boards[s.name]))
                feed = [sub for sub in s.submeshes if sc.materials[sub.material].name == "jumbo_tron"]
                self.assertEqual(len(feed), 1, (name, s.name))
                ids = sorted({i for _m, ix in sb.decode_words(feed[0].words) for i in ix})
                self.assertTrue(all(tuple(C[i][:3]) == (116, 116, 116) for i in ids), (name, s.name))
                U = np.array([UV[i] for i in ids])
                self.assertAlmostEqual(float(U[:, 0].min()), u0, places=3)
                self.assertAlmostEqual(float(U[:, 0].max()), u1, places=3)
                self.assertAlmostEqual(float(U[:, 1].min()), v0, places=3)
                self.assertAlmostEqual(float(U[:, 1].max()), v1, places=3)
            self.assertEqual(seen, set(boards), name)

    def test_the_old_boards_are_gone(self):
        for name, out in self.out.items():
            doc = bk.spec(name[:3])
            sc = _scene(out)
            names = {s.name for s in sc.shapes}
            for rep in doc.get("replace", ()):
                self.assertNotIn(rep["shape"], names)
                if not rep["keep"]:                          # nothing kept: the shape is removed outright (KC's oval)
                    self.assertNotIn(f"bk_{rep['shape']}", names)
                    continue
                new = sc.shape(f"bk_{rep['shape']}")
                self.assertTrue({sc.materials[x.material].name for x in new.submeshes} <= set(rep["keep"]))
            for dr in doc.get("drop", ()):
                left = {sc.materials[x.material].name for x in sc.shape(dr["shape"]).submeshes}
                self.assertFalse(left & set(dr["materials"]), (name, dr["shape"]))
            made = {b["name"] for b in doc["boards"]} | {p["name"] for p in doc.get("panels", ())} | {"bk_ribbons"}
            for cut in doc.get("cut", ()):
                inside = 0
                for s in _static(sc):
                    if s.name in made:                       # the kit's own boards and panels stand where it cut
                        continue
                    P = np.array(sb.shape_positions(s)) / 100.0
                    for sub in s.submeshes:
                        if sc.materials[sub.material].name in cut["materials"]:
                            inside += sum(all(bk._in_box(P[i], cut["box"]) for i in tr) for tr in bk._triangles(sub.words))
                self.assertEqual(inside, 0, (name, cut["materials"]))

    def test_no_kit_surface_covers_surviving_venue_art(self):
        """The rule (main, 2026-09-28): the kit never covers 2026 venue art on a structure that still stands; a panel of
        a replaced board housing is cut, not covered."""
        for name, out in self.out.items():
            self.assertEqual(bk.covered_venue_art(_scene(self.retail[name]), _scene(out), name[:3]), [], name)

    def test_no_old_name_header_hides_behind_nrgs_boards(self):
        """The afternoon, rain and snow bundles draw the old 'Reliant Stadium' header with a material of their own; the
        kit cuts it with the old board housing (the stale-name audit, 2026-09-28)."""
        retail = bk.read_retail(EXTRACTED, "s37")["s37dr.iff"]
        sc = _scene(bk.model_bundle(retail, "s37dr.iff")[0])
        left = [s.name for s in _static(sc) for x in s.submeshes if "stadium_name" in sc.materials[x.material].name]
        self.assertEqual(left, [])

    def test_the_corner_displays_lean_like_the_retail_boards(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        out = self.out["s08dd.iff"]
        sc = _scene(out)
        for name in ("bk_board_nw", "bk_board_ne"):
            s = sc.shape(name)
            P, _C, _UV = sm._vertices(s)
            feed = next(x for x in s.submeshes if sc.materials[x.material].name == "jumbo_tron")
            ids = sorted({i for _m, ix in sb.decode_words(feed.words) for i in ix})
            Q = np.asarray(P)[ids]
            top, bot = Q[Q[:, 1] > Q[:, 1].mean()], Q[Q[:, 1] <= Q[:, 1].mean()]
            r_top = float(np.hypot(top[:, 0], top[:, 2]).mean())
            r_bot = float(np.hypot(bot[:, 0], bot[:, 2]).mean())
            self.assertGreater(r_bot - r_top, 1.5, name)              # the top stands toward the field, as retail's

    def test_the_markers_sit_on_the_new_boards(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        for name, out in self.out.items():
            sc = _scene(out)
            for marker, board in bk.spec(name[:3])["markers"].items():
                s = sc.shape(board)
                P, _C, _UV = sm._vertices(s)
                feed = next(x for x in s.submeshes if sc.materials[x.material].name == "jumbo_tron")
                ids = sorted({i for _m, ix in sb.decode_words(feed.words) for i in ix})
                centre = np.asarray(P)[ids].mean(axis=0) * 100.0            # the marker record is in centimetres
                at = struct.unpack_from("<3f", sc.marker(marker).record, 0x10)
                self.assertTrue(np.allclose(at, centre, atol=1.0), (name, marker, at, centre))


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class RibbonsAndPanels(unittest.TestCase):
    """Cleveland (pass 2): the six end-zone LED ribbons on the upper decks' front fascias in the old boards' freed lit
    slot, and the Dawg Pound's fan area behind the east board where the kit cut the upper rows."""

    NAME = "s30dd.iff"

    @classmethod
    def setUpClass(cls):
        cls.retail = bk.read_retail(EXTRACTED, "s30")[cls.NAME]
        cls.out, cls.info = bk.model_bundle(cls.retail, cls.NAME)
        cls.sc = _scene(cls.out)
        cls.doc = bk.spec("s30")

    def test_the_ribbons_follow_the_published_facts(self):
        self.assertEqual(len(self.doc["ribbons"]), 6)                 # three at each end zone (the eight sideline ones wait)
        for rib in self.doc["ribbons"]:
            self.assertAlmostEqual(rib["y"][1] - rib["y"][0], bk.RIBBON_HEIGHT, places=3)   # 2.5 ft
            P = np.array(rib["path"], float)
            length = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
            self.assertTrue(40 * FT <= length <= 372 * FT, (rib["name"], length))       # 40 to 372 ft
            self.assertIn(rib["material"], {e["material"] for e in self.doc["paint"]})

    def test_the_ribbons_draw_the_repainted_slot_and_clear_the_play_clocks(self):
        from mod_editor.core import nfl2k5_sofi_model as sm
        shape = self.sc.shape("bk_ribbons")
        P, _C, _UV = sm._vertices(shape)
        mats = {self.sc.materials[x.material].name for x in shape.submeshes}
        self.assertEqual(mats, {"LIGHT_jumbotronA1", "lambert42"})
        clock = self.sc.shape("group384")
        Pc, _c, _u = sm._vertices(clock)
        low = min(float(np.asarray(Pc)[i][1]) for x in clock.submeshes
                  if self.sc.materials[x.material].name.startswith("digit_playclock")
                  for _m, ix in sb.decode_words(x.words) for i in ix)
        self.assertLess(float(np.asarray(P)[:, 1].max()), low)

    def test_the_painted_slot_is_free_and_never_the_venue_arts(self):
        k = self.sc.materials[self.sc.material_index("LIGHT_jumbotronA1")].texture
        users = {m.name for m in self.sc.materials if m.texture == k}
        drawn = {self.sc.materials[x.material].name for s in self.sc.shapes if s.name != "bk_ribbons" for x in s.submeshes}
        self.assertFalse(users & drawn)
        self.assertFalse(users & bk._venue_art_materials("s30"))
        self.assertEqual(self.info["painted"], [k])

    def test_the_painted_slot_carries_the_art(self):
        from PIL import Image
        ml = bk._ml()
        c = ml.bundle_scenes(self.out)["stadium"]
        rec, dec = ml._scene(self.out, c)
        got = np.asarray(ml.retail_textures(dec, rec)["LIGHT_jumbotronA1"])[..., :3].astype(int)
        with Image.open(bk.ART_DIR / "s30_ribbons.png") as im:
            want = np.asarray(im.convert("RGB").resize(got.shape[1::-1])).astype(int)
        self.assertLess(float(np.abs(got - want).mean()), 6.0)

    def test_a_venue_art_slot_is_refused(self):
        from unittest import mock
        doc = dict(self.doc, paint=[{"material": "LIGHT_upperRiserSignA1", "art": "s30_ribbons.png"}])
        with mock.patch.object(bk, "spec", lambda venue: doc):
            with self.assertRaises(sb.ScneBuildError):
                bk.build_scene(self.retail, self.NAME)

    def test_the_dawg_pound_rows_behind_the_board_are_gone_and_the_fan_area_closes_them(self):
        inside = 0
        for s in _static(self.sc):
            if s.name.startswith("bk_"):
                continue
            P = np.array(sb.shape_positions(s)) / 100.0
            for sub in s.submeshes:
                if self.sc.materials[sub.material].name in ("deckA1", "crowd", "stairsA1_premipped"):
                    inside += sum(all(p[2] < -119.6 and abs(p[0]) < 49 and p[1] > 14 for p in P[list(tr)])
                                  for tr in bk._triangles(sub.words))
        self.assertEqual(inside, 0)
        fan = self.sc.shape("bk_fan_deck_e")
        self.assertEqual({self.sc.materials[x.material].name for x in fan.submeshes},
                         {"LIGHT_luxBoxB2", "lambert19", "concreteA1"})
        P = np.array(sb.shape_positions(fan)) / 100.0
        board = self.sc.shape("bk_board_e")
        B = np.array(sb.shape_positions(board)) / 100.0
        self.assertAlmostEqual(float(P[:, 1].max()), 39.95, places=2)     # the white beam's top, over the board's top
        self.assertLess(float(B[:, 1].max()), float(P[:, 1].max()))


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class Composition(unittest.TestCase):
    """The kit on a scene the 2026 venue art repainted (a flat palette on one texture stands in for its wall art): the
    repaint survives byte for byte, both options read their states, and Modern surfaces (after the kit) leaves the
    stadium alone."""

    NAME = "s08dd.iff"

    @classmethod
    def setUpClass(cls):
        ml = bk._ml()
        name = cls.NAME
        cls.pin = bk._venue_pins("s08")[name]
        cls.retail = bk.read_retail(EXTRACTED, "s08")[name]
        cls.out, _info = bk.model_bundle(cls.retail, name)
        # the stand-in repaint, refit in the stadium chunk's own span as the venue art does
        tx = ml._tools()[0]
        c = ml.bundle_scenes(cls.retail)["stadium"]
        sc = _scene(cls.retail)
        cls.texture = next(i for i, m in enumerate(sc.materials) if m.texture is not None and m.name != "jumbo_tron")
        k = sc.materials[cls.texture].texture
        sc.textures[k].palette = bytes([40, 90, 200, 255]) * 256
        decoded, system_bytes, video_bytes = sb.serialize(sc)
        span = bytes(cls.retail[c.offset:c.offset + 32 + c.stored_size])
        chunk, _ = sb.fixed_span_chunk("SCNE", decoded, system_bytes, video_bytes, span)
        if tx.HEADER.unpack_from(chunk, 0)[5] > tx.HEADER.unpack_from(span, 0)[5]:
            from mod_editor.core import nfl2k5_usbank_model as um
            chunk, _ = um.fit_keep_scratch(decoded, system_bytes, video_bytes, span)
        cls.painted = cls.retail[:c.offset] + chunk + cls.retail[c.offset + len(span):]
        cls.k = k
        cls.both, _info = bk.model_bundle(cls.painted, name)
        cls.receipt = {"bundles": {name: {"applied_sha256": bk.sha(cls.painted)}}}

    def test_the_repaint_survives_the_kit(self):
        painted, both = _scene(self.painted), _scene(self.both)
        self.assertEqual(both.textures[self.k].palette, bytes([40, 90, 200, 255]) * 256)
        self.assertEqual(_textures(both), _textures(painted))
        self.assertEqual(len(self.both), len(self.retail))

    def test_the_kit_reads_every_state(self):
        state = lambda data, receipt=None: bk.bundle_state(_Archive(self.pin, data), self.NAME, receipt)  # noqa: E731
        self.assertEqual(state(self.retail), "retail")
        self.assertEqual(state(self.out), "applied")
        self.assertEqual(state(self.painted), "foreign")
        self.assertEqual(state(self.painted, self.receipt), "venues")
        self.assertEqual(state(self.both), "applied")
        self.assertEqual(state(self.both, self.receipt), "applied")

    def test_the_venue_art_reads_the_kit(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        self.assertEqual(mv.bundle_state(_Archive(self.pin, self.retail), self.pin, None, None), "retail")
        self.assertEqual(mv.bundle_state(_Archive(self.pin, self.out), self.pin, None, None), "board_kit")
        receipt = {"bundles": {self.NAME: {"applied_sha256": bk.sha(self.both)}}}
        self.assertEqual(mv.bundle_state(_Archive(self.pin, self.both), self.pin, receipt, None), "venues")

    def test_the_venue_art_still_paints_the_kit_venues(self):
        from mod_editor.core import nfl2k5_modern_venues_2026 as mv
        art = dict(venues={p: None for p in VENUES}, league={"nfl_shield": {}}, skipped=[])
        self.assertTrue(set(VENUES) <= {p for p, _t in mv.venues_to_write(art)})

    def test_modern_surfaces_leaves_the_boards_alone(self):
        from mod_editor.core import nfl2k5_modern_surfaces as ms
        a, b = bk._pin(self.NAME)["offset"], bk._pin(self.NAME)["offset"] + bk._pin(self.NAME)["length"]
        after, _rec = ms.surface_bundle(self.out, self.NAME, indoor=False)
        self.assertEqual(after[a:b], self.out[a:b])
        self.assertEqual(bk.bundle_state(_Archive(self.pin, after), self.NAME), "applied")


class Build(unittest.TestCase):
    def test_off_in_every_preset_and_after_the_venue_art_before_surfaces(self):
        import inspect
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as bs
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values.get("modern_board_kit"), False, name)
        self.assertIs(mod_build.BuildPlan.__dataclass_fields__["modern_board_kit"].default, False)
        self.assertIn("modern_board_kit", mod_build.availability())
        self.assertIn("modern_board_kit", bs.FEATURE_KEYS)
        src = inspect.getsource(mod_build)
        steps = [src.index(f'{{"step": "{k}"') for k in ("modern_color_bundles", "modern_venues_2026", "modern_everbank",
                                                         "modern_board_kit", "modern_practice_field", "modern_surfaces")]
        self.assertEqual(steps, sorted(steps))

    def test_the_build_tab_has_the_checkbox(self):
        src = (ROOT / "mod_editor" / "gui" / "build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('"modern_board_kit": self.modern_board_kit_check', src)
        self.assertIn("board_kit.BUILD_CAPTION, board_kit.HELP_TEXT", src)

    def test_the_pins_are_canonical_and_cover_every_bundle(self):
        for venue in VENUES:
            path = bk.PINS_DIR / f"{venue}.json"
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text, json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
            doc = bk.model_pins(venue)
            self.assertEqual(sorted(p["name"] for p in doc["bundles"]), sorted(bk.variants(venue)))
            for p in doc["bundles"]:
                self.assertLess(p["system"] + p["video"], p["retail_system"] + p["retail_video"], p["name"])

    def test_the_registry_pins_each_venue(self):
        registry = json.loads((ROOT / "mod_editor" / "capabilities" / "registry.v1.json").read_text(encoding="utf-8"))
        row = next(c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_board_kit")
        want = []
        for venue in VENUES:
            pin = bk._pin(f"{venue}dd.iff")
            want += [pin["retail_sha256"], pin["model_sha256"]]
        self.assertEqual(row["source_container"]["hash_pins"], want)
        self.assertIs(row["gui"]["default_enabled"], False)
        self.assertEqual(row["validation_command"], "python3 -m tests.mod_editor.test_nfl2k5_board_kit")

    def test_the_release_allowlist_carries_the_kit(self):
        allow = set((ROOT / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split())
        want = ["mod_editor/core/nfl2k5_board_kit.py", "tests/mod_editor/test_nfl2k5_board_kit.py"]
        want += [f"data/nfl2k5_board_kit/{v}.json" for v in VENUES]
        want += [f"data/nfl2k5_board_kit/pins/{v}.json" for v in VENUES]
        art = sorted({e["art"] for v in VENUES for e in bk.spec(v).get("paint", ())})
        want += [f"data/nfl2k5_board_kit/art/{a}" for a in art]
        for rel in want:
            self.assertIn(rel, allow)
            self.assertTrue((ROOT / rel).is_file(), rel)
        shipped = {p.relative_to(ROOT).as_posix() for p in bk.DATA_DIR.rglob("*") if p.is_file()}
        self.assertEqual(shipped, set(want[2:]))

    def test_the_reviewed_release_catalog_carries_the_art(self):
        from PIL import Image
        catalog_path = ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))["files"]
        pngs = sorted(bk.ART_DIR.glob("*.png"))
        self.assertTrue(pngs)
        for png in pngs:
            rel = png.relative_to(ROOT).as_posix()
            row = catalog[rel]
            self.assertEqual((row["sha256"], row["size"]), (bk.sha(png.read_bytes()), png.stat().st_size), rel)
            with Image.open(png) as image:
                self.assertEqual((row["width"], row["height"]), image.size, rel)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{bk.sha(catalog_path.read_bytes())}"', checker)

    def test_the_art_tool_rebuilds_the_art(self):
        import nfl2k5_board_kit_art as art
        if not Path(art.FONT).is_file():
            self.skipTest(f'Art regeneration requires the original RobotoCondensed-Bold font: {art.FONT}')
        for name, make in art.IMAGES.items():
            from PIL import Image
            with Image.open(bk.ART_DIR / name) as have:
                self.assertEqual(have.convert("RGBA").tobytes(), make().tobytes(), name)


if __name__ == "__main__":
    unittest.main()
