"""b777 ar1: the football is the retail ball again (era ball off), the midfield logo is centred, the banner numbers match
the roster."""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
import numpy as np
from mod_editor.core import nfl2k5_era_ball as ball
from mod_editor.core import nfl2k5_midfield_centre as centre
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core import nfl2k5_scne_builder as builder
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
import ar1_banner_numbers as banners

DISC = os.environ.get("AR1_DISC")          # the b776 test disc, read only
RETAIL = os.environ.get("AR1_RETAIL")      # the retail game, read only
FIXES = os.environ.get("AR1_FIXES")        # the v0.6.1 fixes disc (the ball Noah liked), read only


class Ball(unittest.TestCase):
    def test_the_era_ball_ships_off(self):
        doc = json.loads((ROOT / "data/nfl2k5_era_ball/manifest.json").read_text())
        self.assertIs(doc["enabled"], False)
        self.assertFalse(ball.enabled())

    def test_forced_overrides_and_nests(self):
        with ball.forced(True):
            self.assertTrue(ball.enabled())
            with ball.forced(False):
                self.assertFalse(ball.enabled())
            self.assertTrue(ball.enabled())
        self.assertFalse(ball.enabled())

    def test_default_owner_has_no_selector_and_no_hook(self):
        body, edits = venues.code_for(0x500000)
        self.assertNotIn(ball.HOOK[1], [site for site, _, _ in edits])
        self.assertEqual(body[venues.TABLE - ball.SELECTOR_SIZE:venues.TABLE], b"\xcc" * ball.SELECTOR_SIZE)
        with ball.forced(True):
            on_body, on_edits = venues.code_for(0x500000)
        self.assertIn(ball.HOOK[1], [site for site, _, _ in on_edits])
        self.assertNotEqual(body, on_body)

    def test_build_skips_the_step_and_gates_the_scene(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text()
        self.assertIn("if era_ball.enabled():", source)
        self.assertIn("the era ball is off but the ball scene is not the user", source)

    @unittest.skipUnless(DISC and FIXES, "set AR1_DISC (b776) and AR1_FIXES (v0.6.1 fixes)")
    def test_b776_owner_becomes_the_fixes_disc_owner_and_the_hook_is_retail(self):
        from mod_editor.core import nfl2k5_espn25_rosters as rosters
        b776, fixes = rosters.read_xbe(Path(DISC)), rosters.read_xbe(Path(FIXES))
        self.assertEqual(venues.status(b776), "previous")
        # b777-sm2 (merged after ar1): the owner also tests the Situation flag, so the v0.6.1 fixes owner (ball off,
        # no Situation test) is an earlier body too. Both discs upgrade to the same b777 owner: the fixes disc's
        # ball-off layout plus the Situation test.
        self.assertEqual(venues.status(fixes), "previous")
        result, receipt = venues.apply(b776)
        self.assertEqual((venues.status(result), receipt["status"]), ("applied", "applied"))
        self.assertEqual(XbeImage(result).read(ball.HOOK[1], 5), ball.HOOK[2])

        def owner(payload):
            span = venues.allocation(payload)["spans"]
            image = XbeImage(payload)
            return b"".join(image.read(r["va"], r["size"]) for r in span)
        fixed = venues.apply(fixes)[0]
        self.assertEqual(owner(result), owner(fixed))
        spans = venues.allocation(fixes)["spans"]
        self.assertEqual(owner(fixes), venues.code_for(spans[0]["va"], spans, ball=False, situation=False)[0])
        self.assertEqual(owner(fixed), venues.code_for(spans[0]["va"], spans, ball=False, situation=True)[0])
        self.assertEqual(venues.apply(result)[1]["status"], "already_applied")


def fake_field(offset=(0.0, 0.0), uv_swap=True):
    """A decoded scene with one overlay shape: a private center_logo quad at ``offset`` (cm, x then z), 847 x 915 cm,
    UVs laid out like the retail field (u falls along z, v rises along x), plus four unrelated vertices."""
    hx, hz = 423.265, 457.5
    quad = [(-hx, -hz), (hx, -hz), (-hx, hz), (hx, hz)]
    uvs = [(32702, -32702), (32702, 32702), (-32702, -32702), (-32702, 32702)]
    stream0 = b"".join(struct.pack("<3f", x + offset[0], 0.0, z + offset[1]) for x, z in quad)
    stream0 += b"".join(struct.pack("<3f", x, 0.0, z) for x, z in ((900, 1000), (950, 1000), (900, 1100), (950, 1100)))
    stream1 = b"".join(struct.pack("<4Bhhh", 255, 255, 255, 255, u, v, 0) for u, v in uvs + uvs)
    words_logo = builder.encode_words(builder.TRIANGLE_STRIP, [0, 1, 2, 3])
    words_other = builder.encode_words(builder.TRIANGLE_STRIP, [4, 5, 6, 7])
    decoded = bytearray(64)
    s0, s1 = len(decoded), len(decoded) + len(stream0)
    decoded += stream0 + stream1
    c0 = len(decoded)
    decoded += words_logo
    c1 = len(decoded)
    decoded += words_other
    rec = dict(shapes=[dict(name=centre.SHAPE, index=0, vertex_streams=[
        dict(stream_index=0, stride=12, offset=s0), dict(stream_index=1, stride=10, offset=s1)])],
        submeshes=[dict(shape_index=0, material_name=centre.MATERIAL, command_offset=c0,
                        primary_command_word_count=len(words_logo) // 4),
                   dict(shape_index=0, material_name="numbers", command_offset=c1,
                        primary_command_word_count=len(words_other) // 4)])
    return rec, bytes(decoded), s0


def logo(ink_box=(24, 24, 232, 232), size=256):
    rgba = np.zeros((size, size, 4), np.uint8)
    x0, y0, x1, y1 = ink_box
    rgba[y0:y1, x0:x1] = (255, 255, 255, 255)
    return rgba


class Midfield(unittest.TestCase):
    def test_a_centred_logo_keeps_every_byte(self):
        rec, decoded, _ = fake_field()
        out = bytearray(decoded)
        ranges, receipt = centre.recentre(out, rec, decoded, logo())
        self.assertEqual((ranges, receipt["state"], bytes(out)), ([], "centred", decoded))

    def test_the_titans_quad_is_moved_exactly_and_only_its_eight_floats(self):
        rec, decoded, s0 = fake_field(offset=(0.0, 155.0))
        before = centre.measure(rec, decoded, logo())
        self.assertAlmostEqual(before["ink_offset_cm"][1], 155.0, places=3)
        self.assertGreater(before["offset_texels"][1], 40)
        out = bytearray(decoded)
        ranges, receipt = centre.recentre(out, rec, decoded, logo())
        self.assertEqual(receipt["state"], "moved")
        self.assertEqual(len(ranges), 8)
        changed = [i for i, (a, b) in enumerate(zip(decoded, out)) if a != b]
        allowed = {i for at, n in ranges for i in range(at, at + n)}
        self.assertTrue(set(changed) <= allowed)
        after = centre.measure(rec, bytes(out), logo())
        self.assertLess(abs(after["ink_offset_cm"][0]), 0.01)
        self.assertLess(abs(after["ink_offset_cm"][1]), 0.01)
        # the unrelated vertices and the UVs are untouched
        self.assertEqual(bytes(out)[s0 + 48:], decoded[s0 + 48:])

    def test_an_asymmetric_ink_box_is_centred_by_its_ink(self):
        rec, decoded, _ = fake_field()
        art = logo(ink_box=(40, 24, 232, 232))     # ink 16 px right of centre horizontally in the texture
        out = bytearray(decoded)
        _ranges, receipt = centre.recentre(out, rec, decoded, art)
        self.assertEqual(receipt["state"], "moved")
        self.assertLess(abs(centre.measure(rec, bytes(out), art)["ink_offset_cm"][0]), 0.01)

    def test_within_a_texel_is_left_alone(self):
        rec, decoded, _ = fake_field(offset=(0.0, 3.0))   # 3 cm is under one texel (3.6 cm)
        out = bytearray(decoded)
        self.assertEqual(centre.recentre(out, rec, decoded, logo())[0], [])
        self.assertEqual(bytes(out), decoded)

    def test_no_texture_or_no_quad_is_not_an_error(self):
        rec, decoded, _ = fake_field(offset=(0.0, 155.0))
        self.assertEqual(centre.recentre(bytearray(decoded), rec, decoded, None)[1]["state"], "no midfield logo")
        blank = np.zeros((256, 256, 4), np.uint8)
        self.assertEqual(centre.recentre(bytearray(decoded), rec, decoded, blank)[0], [])
        rec2 = dict(rec, submeshes=[s for s in rec["submeshes"] if s["material_name"] != centre.MATERIAL])
        self.assertIsNone(centre.quad(rec2, decoded))

    def test_a_quad_sharing_vertices_is_left_alone(self):
        rec, decoded, _ = fake_field(offset=(0.0, 155.0))
        shared = builder.encode_words(builder.TRIANGLE_STRIP, [0, 1, 6, 7])
        out = decoded + shared
        rec["submeshes"][1] = dict(rec["submeshes"][1], command_offset=len(decoded),
                                   primary_command_word_count=len(shared) // 4)
        self.assertIsNone(centre.quad(rec, out))

    def test_every_field_writer_runs_the_centring(self):
        core = ROOT / "mod_editor/core"
        self.assertIn("midfield_centre.recentre(edited, rec, bytes(edited), texture)",
                      (core / "nfl2k5_modern_venues_2026.py").read_text())      # 30 home fields and the special slots
        self.assertIn("midfield_centre.recentre(", (core / "nfl2k5_modern_metlife.py").read_text())   # Modern MetLife
        fields = (core / "nfl2k5_espn25_fields.py").read_text()                 # Anniversary aliases
        self.assertEqual(fields.count("centred,centre_receipt=_centre_midfield(out,rec,rows,materials)"), 2)  # painted rows and rows 24/25 (retail paint)

    @unittest.skipUnless(DISC, "set AR1_DISC to the b776 test disc")
    def test_the_real_titans_field_is_155_cm_off_and_centres_exactly(self):
        import ar1_midfield_audit as audit
        for name, rec, decoded in audit.field_scenes(DISC, ["dd"]):
            if name != "s28dd.iff":
                continue
            texture = audit.logo_texture(rec, decoded)
            before = centre.measure(rec, decoded, texture)
            self.assertAlmostEqual(before["ink_offset_cm"][0], 0.0, delta=0.2)
            self.assertAlmostEqual(before["ink_offset_cm"][1], 155.0, delta=0.2)
            out = bytearray(decoded)
            ranges, receipt = centre.recentre(out, rec, decoded, texture)
            self.assertEqual((receipt["state"], len(ranges)), ("moved", 8))
            after = centre.measure(rec, bytes(out), texture)
            self.assertLess(max(abs(v) for v in after["ink_offset_cm"]), 0.01)
            self.assertEqual(sum(a != b for a, b in zip(decoded, out)) <= 8 * 4, True)
            return
        self.fail("s28dd has no field with a midfield logo")


class BannerNumbers(unittest.TestCase):
    ROSTER = [("Carnell Tate", 14), ("Cam Ward", 1), ("Jeffery Simmons", 98), ("Will Anderson", 51), ("Josh Hines-Allen", 41),
              ("Brian Thomas", 7), ("Tate Ratledge", 69), ("De'Von Achane", 28)]

    def test_the_specs_hold_the_roster_numbers_for_the_two_fixed_cloths(self):
        ten = json.loads((ROOT / "data/nfl2k5_teams_2026/TEN.json").read_text())
        hou = json.loads((ROOT / "data/nfl2k5_teams_2026/HOU.json").read_text())
        ten_text = [t for _, _, t in banners.banner_texts(ten)]
        hou_text = [t for _, _, t in banners.banner_texts(hou)]
        self.assertIn("#14 CARNELL\nTATE", ten_text)
        self.assertNotIn("#6 CARNELL\nTATE", ten_text)
        self.assertIn("#51 WILL\nANDERSON", hou_text)
        self.assertNotIn("#31 WILL\nANDERSON", hou_text)

    def test_wrong_numbers_are_flagged_and_right_ones_pass(self):
        self.assertEqual(banners.check_text("#14 CARNELL\nTATE", self.ROSTER), [])
        self.assertEqual(banners.check_text("#1\nCAM WARD", self.ROSTER), [])
        self.assertEqual(banners.check_text("#98 BIG JEFF\nSIMMONS", self.ROSTER), [])
        self.assertEqual(banners.check_text("#41\nHINES-ALLEN", self.ROSTER), [])
        self.assertEqual(banners.check_text("#7 BTJ\nON THE PROWL", self.ROSTER), [])
        wrong = banners.check_text("#6 CARNELL\nTATE", self.ROSTER)
        self.assertEqual([n for n, _ in wrong], [6])
        self.assertIn(("Carnell Tate", 14), wrong[0][1])
        self.assertEqual([n for n, _ in banners.check_text("#31 WILL\nANDERSON", self.ROSTER)], [31])

    def test_two_numbers_on_one_cloth_are_checked_separately(self):
        text = "#14 CARNELL\n#6 TATE RATLEDGE"
        self.assertEqual([n for n, _ in banners.check_text(text, self.ROSTER)], [6])

    def test_every_numbered_cloth_in_every_spec_is_parsed(self):
        count = 0
        for path in sorted((ROOT / "data/nfl2k5_teams_2026").glob("*.json")):
            spec = json.loads(path.read_text())
            for _material, _slot, text in banners.banner_texts(spec):
                self.assertTrue(re.search(r"#\s*\d+", text))
                count += 1
        self.assertGreaterEqual(count, 100)

    @unittest.skipUnless(DISC, "set AR1_DISC to the b776 test disc")
    def test_every_banner_number_matches_the_disc_roster(self):
        self.assertEqual(banners.check(DISC), [])


if __name__ == "__main__":
    unittest.main()
