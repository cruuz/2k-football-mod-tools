"""2026 kick meter (beta 76 km): art, geometry and pins, the sprite scorebug's HUD rule with the three kick spans, the
image plumbing (apply, states, exact revert) on an in-memory archive, the Build wiring, and, when the extracted retail
files are present, the real compile against the retail scenes and the retail animation sampler run offline.

No game data is involved in the always-on tests; the retail checks read the user's own extracted files and skip
without them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402
from mod_editor.core import nfl2k5_kick_meter_2026 as km  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACK0 = GAME / "vc_53450030" / "0"
HAVE_GAME = PACK0.is_file() and (GAME / "default.xbe").is_file()
try:
    import unicorn  # noqa: F401
    HAVE_UNICORN = True
except ImportError:
    HAVE_UNICORN = False
HUD_START, HUD_SIZE = 109895680, 2977184
U_B = 19 / 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ArtGeometryPins(unittest.TestCase):
    def test_available_and_pins_agree_with_the_shipped_art(self):
        self.assertTrue(km.available())
        pins = json.loads(km.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pins["art"], km.art_pins())
        self.assertEqual(sorted(pins["art"]), sorted(km.ART_FILES))
        self.assertEqual([(r["scene"], r["chunk_index"]) for r in pins["resources"]], list(km.RESOURCES))
        self.assertFalse(pins["runtime_witnessed"])
        # canonical form
        self.assertEqual(km.PINS_PATH.read_text(encoding="utf-8"), json.dumps(pins, indent=2, sort_keys=True) + "\n")

    def test_geometry_fills_every_slot_inside_its_retail_submesh(self):
        document = km.geometry()
        vertices, strips = document["kick_meter"]["vertices"], document["kick_meter"]["strips"]
        self.assertEqual(len(vertices), 575)
        covered = sorted(v for name, (_a, _c, first, count, _s) in km.METER_SUBMESHES.items() for v in range(first, first + count))
        self.assertEqual(covered, list(range(575)))
        for name, (_at, capacity, first, count, selector) in km.METER_SUBMESHES.items():
            with self.subTest(submesh=name):
                self.assertTrue(all(first <= i < first + count for i in strips[name]))
                self.assertLessEqual(5 + len(strips[name]) // 2, capacity)
                self.assertTrue(all(vertices[i][6] == selector for i in range(first, first + count)))

    def test_band_is_one_strip_whose_u_falls_along_the_path(self):
        vertices = km.geometry()["kick_meter"]["vertices"]
        self.assertEqual(km.geometry()["kick_meter"]["strips"]["a_meter"], list(range(80)))
        u = [vertices[k][3] for k in range(80)]
        self.assertEqual(u[0::2], u[1::2])                       # inner and outer edge share U
        self.assertTrue(all(a > b for a, b in zip(u[0::2], u[2::2])))  # U falls as the band runs round

    def test_every_strip_faces_front_like_the_retail_scene(self):
        # km lab 1 (PROVED IN GAME): the kick meter's textured materials cull back faces (material +0x60 bit 26; the
        # retail encoder 0x2FC80 turns CULL_FACE on), and three reversed strips (the centre disc, NO WIND and the MPH
        # tab) did not draw. Every triangle of every submesh must have the retail winding: positive area in model x, y.
        vertices = km.geometry()["kick_meter"]["vertices"]
        for name, indices in km.geometry()["kick_meter"]["strips"].items():
            signs = set()
            for i in range(len(indices) - 2):
                a, b, c = (vertices[indices[i + j]] for j in range(3))
                area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                if area:
                    signs.add((1 if area > 0 else -1) * (1 if i % 2 == 0 else -1))
            with self.subTest(submesh=name):
                self.assertEqual(signs, {1})

    def test_commands_encode_and_refuse_overflow(self):
        words = struct.unpack("<8I", km._commands([80, 81, 82, 83], 8))
        self.assertEqual(words, (0x417FC, 6, 0x40001800 | (2 << 18), 80 | 81 << 16, 82 | 83 << 16, 0x417FC, 0, 0))
        with self.assertRaises(km.KickMeterError):
            km._commands(list(range(8)), 8)

    def test_changes_outside_the_allowed_ranges_are_found(self):
        before = bytes(3840)
        after = bytearray(before)
        after[km.WIND_ATTRIBUTES] = 1
        self.assertEqual(km.changed_outside("windmeter", before, bytes(after)), [])
        after[0x10] = 1
        self.assertEqual(km.changed_outside("windmeter", before, bytes(after)), [0x10])

    def test_pins_refuse_malformed_documents(self):
        pins = json.loads(km.PINS_PATH.read_text(encoding="utf-8"))
        for mutate in (lambda d: d.update(schema="x"), lambda d: d["resources"].reverse(),
                       lambda d: d["resources"][0].update(applied_sha256=d["resources"][0]["retail_sha256"]),
                       lambda d: d["outer"].update(index=3)):
            bad = json.loads(json.dumps(pins))
            mutate(bad)
            with self.assertRaises(km.KickMeterError):
                km._check_pins(bad)


class SpriteHudRule(unittest.TestCase):
    """nfl2k5_scorebug_sprite accepts the HUD with the kick spans at retail or applied pins (shipped-pins rule)."""

    def setUp(self):
        import random
        rng = random.Random(76)
        self.hud = bytes(rng.getrandbits(8) for _ in range(64 * 1024))
        self.marks = [("m%d" % k, 1000 + k * 5000, 700) for k in range(4)]
        self.kick = [("KickArrow", 30000, 900), ("KickMeter", 32000, 4000), ("windmeter", 40000, 500)]
        self.applied = {name: bytes(rng.getrandbits(8) for _ in range(size)) for name, _at, size in self.marks + self.kick}
        rows = lambda spans: tuple((n, at, size, sha(self.hud[at:at + size]), sha(self.applied[n])) for n, at, size in spans)  # noqa: E731
        self.mark_rows, self.kick_rows = rows(self.marks), rows(self.kick)
        digest = hashlib.sha256(); cursor = 0
        for _n, at, size in sorted(self.marks + self.kick, key=lambda r: r[1]):
            digest.update(self.hud[cursor:at]); cursor = at + size
        digest.update(self.hud[cursor:])
        self.patches = [mock.patch.object(sprite, "espn_mark_spans", lambda pins=None: (len(self.hud), self.mark_rows)),
                        mock.patch.object(sprite, "kick_meter_spans", lambda pins=None: self.kick_rows),
                        mock.patch.object(sprite, "HUD_OUTSIDE_IN_PLACE", digest.hexdigest())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def splice(self, names):
        hud = bytearray(self.hud)
        for n, at, size in self.marks + self.kick:
            if n in names:
                hud[at:at + size] = self.applied[n]
        return bytes(hud)

    def test_kick_spans_retail_or_applied_are_supported(self):
        for chosen in ({"KickMeter"}, {"KickArrow", "KickMeter", "windmeter"}, {"m1", "KickMeter", "windmeter"}):
            with self.subTest(applied=sorted(chosen)):
                states = sprite._hud_in_place(self.splice(chosen))
                self.assertIsNotNone(states)
                self.assertEqual({n for n, s in states.items() if s == "applied"}, chosen)

    def test_anything_else_is_foreign(self):
        full = self.splice({"KickMeter"})
        for at in (0, 31999, 36000, len(full) - 1):
            bad = bytearray(full); bad[at] ^= 1
            self.assertIsNone(sprite._hud_in_place(bytes(bad)), hex(at))
        self.assertIsNone(sprite._hud_in_place(full + b"\0"))

    def test_explicit_pins_keep_the_marks_only_rule(self):
        # The kick rule applies only with the shipped defaults; an explicit marks rule still refuses kick changes.
        explicit = dict(pins={"marker": True}, outside="0" * 64, before="0" * 64)
        with mock.patch.object(sprite, "_hud_marks_only", return_value=None) as marks_only:
            self.assertIsNone(sprite.hud_espn_marks(self.splice({"KickMeter"}), **explicit))
            marks_only.assert_called_once()
        with mock.patch.object(sprite, "_hud_marks_only", return_value=None):
            self.assertIsNotNone(sprite.hud_espn_marks(self.splice({"KickMeter"})))


class FakeEntry:
    def __init__(self, name_id, size, virtual_offset):
        self.name_id, self.size, self.virtual_offset = name_id, size, virtual_offset


class FakeArchive:
    """An in-memory outer archive: entries by index, read and write by virtual offset."""
    store: dict[str, bytearray] = {}

    def __init__(self, path, *, writable=False):
        self.buf = FakeArchive.store[str(path)]
        self.entries = [FakeEntry(0, 0, 0)] * km.OUTER_INDEX + [FakeEntry(km.OUTER_NAME_ID, 8192, 4096)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, at, count):
        return bytes(self.buf[at:at + count])

    def write(self, at, data):
        self.buf[at:at + len(data)] = data
        return len(data)


class ImagePlumbing(unittest.TestCase):
    def setUp(self):
        import random
        rng = random.Random(1976)
        self.image = bytearray(rng.getrandbits(8) for _ in range(16384))
        rows, self.applied = [], {}
        for k, (scene, chunk) in enumerate(km.RESOURCES):
            offset, size = 256 + k * 1024, 600
            retail = bytes(self.image[4096 + offset:4096 + offset + size])
            applied = bytes(b ^ 0x5A for b in retail)
            self.applied[retail] = applied
            rows.append(dict(scene=scene, chunk_index=chunk, chunk_offset=offset, span_size=size, decoded_size=size,
                             retail_sha256=sha(retail), applied_sha256=sha(applied), retail_decoded_sha256="1" * 64,
                             applied_decoded_sha256="2" * 64))
        self.pins = dict(schema=km.PINS_SCHEMA, outer=dict(index=km.OUTER_INDEX, name_id=km.OUTER_NAME_ID, size=8192),
                         art={}, resources=rows, runtime_witnessed=False,
                         font=dict(name=km.FONT_NAME, chunk_size=6688, chunk_sha256="3" * 64))
        FakeArchive.store = {"target": bytearray(self.image), "retail": bytearray(self.image)}
        self.xbe = {"target": "retail"}
        self.font = {"target": False}

        def transaction(path, pins, *, font, xbe):
            self.font[str(path)] = font == "add"
            self.xbe[str(path)] = "applied" if xbe == "apply" else "retail"
            return dict(pack_transport=None, xbe_transport=None, image_growth=0)

        def font_state(read, size, pins):
            return "present" if self.font.get(self.current, False) else "absent"

        def xbe_of(source):
            self.current = str(source)
            return self.xbe.get(str(source), "retail")

        self.current = "target"
        self.patches = [mock.patch.object(km, "_outer_image", lambda: FakeArchive),
                        mock.patch.object(km, "compile_span", lambda span, row: (self.applied[span], {})),
                        mock.patch.object(km, "_transaction", transaction),
                        mock.patch.object(km, "_xbe_of", xbe_of),
                        mock.patch.object(km, "xbe_status", lambda payload: payload),
                        mock.patch.object(km, "font_state", font_state)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_apply_is_exact_idempotent_and_reverts(self):
        self.assertEqual(km.image_status("target", pins=self.pins), "retail")
        receipt = km.apply_to_image("target", pins=self.pins)
        self.assertEqual((receipt["state"], receipt["written"], receipt["gamedata_growth"], receipt["xbe"]["bytes"]),
                         ("applied", 3, 6688, 4))
        self.assertEqual(km.image_status("target", pins=self.pins), "applied")
        again = km.apply_to_image("target", pins=self.pins)
        self.assertEqual((again["written"], again["already_applied"], again["gamedata_growth"]), (0, 3, 0))
        outside = [i for i in range(len(self.image)) if FakeArchive.store["target"][i] != self.image[i]
                   and not any(4096 + r["chunk_offset"] <= i < 4096 + r["chunk_offset"] + r["span_size"] for r in self.pins["resources"])]
        self.assertEqual(outside, [])
        revert = km.revert_image("target", "retail", pins=self.pins)
        self.assertEqual((revert["state"], revert["restored"]), ("retail", 3))
        self.assertEqual(FakeArchive.store["target"], bytearray(self.image))
        self.assertEqual((self.font["target"], self.xbe["target"]), (False, "retail"))

    def test_a_half_installed_font_or_lookup_reads_mixed(self):
        self.xbe["target"] = "applied"
        self.assertEqual(km.image_status("target", pins=self.pins), "mixed")
        self.xbe["target"] = "retail"; self.font["target"] = True
        self.assertEqual(km.image_status("target", pins=self.pins), "mixed")
        self.xbe["target"] = "foreign"
        self.assertEqual(km.image_status("target", pins=self.pins), "foreign")

    def test_mixed_and_foreign(self):
        row = self.pins["resources"][1]
        at = 4096 + row["chunk_offset"]
        span = bytes(FakeArchive.store["target"][at:at + row["span_size"]])
        FakeArchive.store["target"][at:at + row["span_size"]] = self.applied[span]
        self.assertEqual(km.image_status("target", pins=self.pins), "mixed")
        FakeArchive.store["target"][at] ^= 0xFF
        self.assertEqual(km.image_status("target", pins=self.pins), "foreign")
        with self.assertRaises(km.KickMeterError):
            km.apply_to_image("target", pins=self.pins)


class DigitsFont(unittest.TestCase):
    """The wind digits FONT (part 2): the retail FONT contract, its pin and the executable's font lookup."""

    def test_the_font_meets_the_retail_font_contract_and_its_pin(self):
        from nfl_main_menu_font import parse_font
        from nfl_scene_probe import ResourceRecord
        chunk = km.compile_digits_font()
        kind, stored, system, video, magic = struct.unpack_from("<4s4I", chunk)
        self.assertEqual((kind, stored, magic, system % 128, len(chunk) % 16), (b"FONT", len(chunk) - 32, 0, 0, 0))
        decoded = chunk[32:]
        font = parse_font(0, km.FONT_NAME, ResourceRecord(346, "00b6926c", 0, 0, 0, "FONT", stored, system, video, 0, 0),
                          decoded, sha(decoded))
        self.assertEqual((font.minimum, font.maximum, font.width, font.height, len(font.glyphs)), (0x2D, 0x39, 64, 64, 13))
        self.assertEqual((font.space_advance, font.line_advance), (6, 24))
        digits = {chr(g.codepoint): g for g in font.glyphs}
        for ch in "0123456789":
            with self.subTest(digit=ch):
                g = digits[ch]
                self.assertEqual((g.top, g.bottom), (6.0, 23.0))          # the retail font3 line box
                self.assertGreaterEqual(g.advance, g.right - g.left + 1)
        pins = json.loads(km.PINS_PATH.read_text(encoding="utf-8"))["font"]
        self.assertEqual((pins["chunk_size"], pins["chunk_sha256"]), (len(chunk), sha(chunk)))
        self.assertEqual(sprite.kick_meter_font_tail(), (len(chunk), sha(chunk)))

    def test_the_sprite_sets_the_font_tail_aside(self):
        chunk = km.compile_digits_font()
        from mod_editor.core import nfl2k5_scorebug_resources as art
        hud = bytes(art.HUD_SIZE)
        appendix = b"A" * 160
        with mock.patch.object(sprite, "hud_espn_marks", lambda hud, **kw: {}), \
                mock.patch.object(sprite, "probe_sizes", lambda folder=None: (0, len(appendix), 0)), \
                mock.patch.object(sprite, "appendix", lambda *a, **kw: (appendix, {})):
            for body, want in ((hud, "retail"), (hud + chunk, "retail"), (hud + appendix, "applied"),
                               (hud + appendix + chunk, "applied"), (hud + appendix + chunk[:-1] + b"x", "foreign"),
                               (hud + chunk + appendix, "foreign")):
                read = lambda count, at, body=body: body[at:at + count]  # noqa: E731
                self.assertEqual(sprite.gamedata_status(read, len(body)), want)

    def test_the_manifest_generator_declares_the_lookup_edit(self):
        source = (ROOT / "mod_editor/core/nfl2k5_cave_manifest.py").read_text(encoding="utf-8")
        # ig 291447e01: the final composition calls kick_meter.apply_xbe (the function XbePatch.apply names), so the
        # manifest recorder, which wraps module-level apply/apply_xbe, observes the edit.
        for needle in ("kick_meter.apply_xbe(final)", "(kick_meter.XbePatch, {})", "kick_meter.OWNER",
                       "kick_meter.xbe_reservations(final)"):
            self.assertIn(needle, source)

    @unittest.skipUnless(HAVE_GAME, "needs the retail default.xbe")
    def test_the_lookup_repoint_is_guarded_and_exact(self):
        xbe = (GAME / "default.xbe").read_bytes()
        self.assertEqual(km.xbe_status(xbe), "retail")
        applied, receipt = km.apply_xbe(xbe)
        self.assertEqual((km.xbe_status(applied), receipt["status"], len(applied)), ("applied", "applied", len(xbe)))
        diff = [i for i in range(len(xbe)) if xbe[i] != applied[i]]
        self.assertEqual(len([i for i in diff if i > 0x1000]), 1)           # one operand byte in .text
        self.assertEqual(km.apply_xbe(applied)[1]["status"], "already_applied")
        self.assertEqual(km.restore_xbe(applied), xbe)
        self.assertEqual(km.xbe_reservations(applied)[0]["size"], 4)
        bad = bytearray(xbe)
        from mod_editor.core.nfl2k5_bump_strength import _sections
        at = km._xbe_image(xbe)(km.FONT_PUSH_VA + 5, 1)
        bad[at] ^= 0xFF
        self.assertEqual(km.xbe_status(bytes(bad)), "foreign")
        with self.assertRaises(km.KickMeterError):
            km.apply_xbe(bytes(bad))
        self.assertTrue(_sections(applied))


class BuildWiring(unittest.TestCase):
    def test_plan_default_presets_availability_and_settings(self):
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.kick_meter_2026, False)
        self.assertIn("kick_meter_2026", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values["kick_meter_2026"], False, name)
            self.assertIs(mod_build.apply_preset(plan, name).kick_meter_2026, False, name)
        self.assertTrue(mod_build.availability()["kick_meter_2026"])
        self.assertIn("kick_meter_2026", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"kick_meter_2026": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").kick_meter_2026, True)
        with self.assertRaisesRegex(ValueError, "kick_meter_2026 must be true or false"):
            build_settings.build_settings({"kick_meter_2026": "yes"})
        self.assertEqual((km.DEFAULT_ENABLED, km.CAVES, km.REQUESTS, km.RUNTIME_GLOBALS, km.LABEL),
                         (False, (), (), (), "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self):
        import tempfile
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="kick-meter-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "needs a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), kick_meter_2026=True))
            with self.assertRaisesRegex(ValueError, "Hi-res scorebug family cannot be combined"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), kick_meter_2026=True,
                                                    hires_pack=True, hires_families=("scorebug",)))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out3.xbe"), kick_meter_2026=1))
            self.assertEqual(mod_build.inspect(xbe)["kick_meter_2026"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_registry_row(self):
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text(encoding="utf-8"))
        row = [c for c in registry["capabilities"] if c["id"] == "nfl2k5.scorebug_presentation.kick_meter_2026"][0]
        self.assertEqual(row["backend"]["module"], "mod_editor/core/nfl2k5_kick_meter_2026.py")
        self.assertEqual(row["validation_command"], "python3 -m tests.mod_editor.test_nfl2k5_kick_meter_2026")
        self.assertFalse(row["gui"]["default_enabled"])
        pins = json.loads(km.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(row["source_container"]["hash_pins"], [r["retail_sha256"] for r in pins["resources"]])


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail files (NFL2K5_GAME_DIR)")
class RetailScenes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = json.loads(km.PINS_PATH.read_text(encoding="utf-8"))
        with PACK0.open("rb") as f:
            f.seek(HUD_START); cls.hud = f.read(HUD_SIZE)
        cls.spans = {r["scene"]: cls.hud[r["chunk_offset"]:r["chunk_offset"] + r["span_size"]] for r in cls.pins["resources"]}
        cls.compiled = {r["scene"]: km.compile_span(cls.spans[r["scene"]], r) for r in cls.pins["resources"]}

    def test_record_pins_reproduces_the_shipped_pins(self):
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(GAME)
        self.assertEqual(km.record_pins(GAME, None), self.pins)

    def test_compiled_spans_match_their_pins_and_keep_the_wrapper(self):
        for row in self.pins["resources"]:
            span, detail = self.compiled[row["scene"]]
            with self.subTest(scene=row["scene"]):
                self.assertEqual(sha(span), row["applied_sha256"])
                self.assertEqual(len(span), row["span_size"])
                self.assertEqual(span[:32], self.spans[row["scene"]][:32])
                self.assertTrue(detail["wrapper_identical"])
                self.assertLessEqual(detail["exact_minimum_scratch"], detail["scratch_bytes"])
                _c, before = km._decode(self.spans[row["scene"]])
                _c, after = km._decode(span)
                self.assertEqual(km.changed_outside(row["scene"], before, after), [])

    def test_textures_round_trip_to_the_shipped_art(self):
        import nfl_txtr as txtr
        import nfl_tset_png_import as palettes
        _c, after = km._decode(self.compiled["KickMeter"][0])
        for png, w, h, pixels, palette in km.METER_TEXTURES:
            _w, _h, rgba = palettes.decode_rgba_png((km.ART_DIR / png).read_bytes(), (w, h))
            base = km.METER_SYSTEM
            indices = txtr.unswizzle_2d(after[base + pixels:base + pixels + w * h], w, h, 1)
            table = after[base + palette:base + palette + 1024]
            worst = max(abs(table[4 * i + (2, 1, 0, 3)[ch]] - rgba[4 * p + ch]) for p, i in enumerate(indices) for ch in range(4))
            self.assertLessEqual(worst, 16, png)

    def test_sprite_accepts_the_real_hud_with_the_kick_meter(self):
        retail = sprite.hud_espn_marks(self.hud)
        self.assertEqual(set(retail.values()), {"retail"})
        hud = bytearray(self.hud)
        for row in self.pins["resources"]:
            hud[row["chunk_offset"]:row["chunk_offset"] + row["span_size"]] = self.compiled[row["scene"]][0]
        states = sprite.hud_espn_marks(bytes(hud))
        self.assertEqual({k: v for k, v in states.items() if k in ("KickArrow", "KickMeter", "windmeter")},
                         dict.fromkeys(("KickArrow", "KickMeter", "windmeter"), "applied"))
        hud[1000] ^= 1
        self.assertIsNone(sprite.hud_espn_marks(bytes(hud)))

    def test_the_sprite_accepts_its_appendix_followed_by_the_font(self):
        from mod_editor.core import nfl2k5_scorebug_resources as art
        with PACK0.open("rb") as stream:
            view = art.PackView.from_fd(stream.fileno(), 0, PACK0.stat().st_size)
            appendix, _receipt = sprite.appendix(view, None, True, "auto")
        hud = bytearray(self.hud)
        for row in self.pins["resources"]:
            hud[row["chunk_offset"]:row["chunk_offset"] + row["span_size"]] = self.compiled[row["scene"]][0]
        outer = bytes(hud) + appendix + km.compile_digits_font()
        read = lambda count, at: outer[at:at + count]  # noqa: E731
        self.assertEqual(sprite.gamedata_status(read, len(outer)), "applied")
        self.assertEqual(sprite.gamedata_status(read, len(outer) - 16), "foreign")

    @unittest.skipUnless(HAVE_UNICORN, "needs unicorn for the retail FONT loader")
    def test_the_retail_font_loader_takes_the_wind_digits_without_a_global_slot(self):
        import nfl2k5_scorebug_projection as projection
        from nfl_main_menu_font import parse_font
        from nfl_scene_probe import ResourceRecord
        chunk = km.compile_digits_font()
        _kind, stored, system, video = struct.unpack_from("<4s3I", chunk)
        font = parse_font(0, km.FONT_NAME, ResourceRecord(346, "00b6926c", 0, 0, 0, "FONT", stored, system, video, 0, 0),
                          chunk[32:], sha(chunk[32:]))
        m = projection.StaticMachine((GAME / "default.xbe").read_bytes()); m.record = False; m.fonts = {}
        receipt = m.load_private_font(chunk, font)
        self.assertFalse(receipt["global_slot_changed"])
        obj = int(receipt["object"], 16)
        self.assertEqual((m.get(obj) & 0xFFFF, m.get(obj) >> 16, m.get(obj + 4)), (0x2D, 0x39, 1))
        self.assertEqual(m.get(m.get(obj + 8) + 4), m.get(obj + 8) + 0x10)     # the relocated glyph records

    @unittest.skipUnless(HAVE_UNICORN, "needs unicorn for the retail animation sampler")
    def test_retail_sampler_behaves_the_same_and_the_fill_front_rides_the_marker(self):
        import nfl2k5_scorebug_projection as projection
        xbe = (GAME / "default.xbe").read_bytes()

        def machine(decoded):
            m = projection.StaticMachine(xbe); m.record = False
            body = m.alloc(len(decoded)); m.uc.mem_write(body, decoded)
            m.run(0x2F140, ecx=body + 256, limit=500000); m.run(0x43E30, (0,), ecx=body, edx=0, limit=500000)
            return m, body

        def sample(m, body, n, t):
            m.run(0x2F010, (struct.unpack("<I", struct.pack("<f", t))[0],), ecx=body + 256, limit=2000000)
            return bytes(m.uc.mem_read(body, n))

        _c, retail = km._decode(self.spans["KickMeter"])
        _c, applied = km._decode(self.compiled["KickMeter"][0])
        mr, br = machine(retail); ma, ba = machine(applied)
        scale = struct.unpack_from("<f", applied, 2384 + 0x10)[0]; offset = struct.unpack_from("<3f", applied, 2384 + 0x20)
        us, uo = struct.unpack_from("<2f", applied, 2384 + 0x30), struct.unpack_from("<2f", applied, 2384 + 0x38)
        ns = lambda q: q / 32767.0 if q >= 0 else q / 32768.0  # noqa: E731
        pos = [tuple(ns(q) * scale + o for q, o in zip(struct.unpack_from("<3h", applied, 0x2060 + 6 * k), offset)) for k in range(84)]
        u = [ns(struct.unpack_from("<h", applied, 0x2DE0 + 10 * k + 4)[0]) * us[0] + uo[0] for k in range(80)]
        marker = [sum(pos[80 + i][a] for i in range(4)) / 4 for a in range(2)]
        for t in (0.0, 0.5, 1.2, 1.73, 2.6, 3.2, 3.46, 4.0, 4.2, 5.0):
            with self.subTest(t=t):
                sr, sa = sample(mr, br, len(retail), t), sample(ma, ba, len(applied), t)
                # the animated targets: a_meter's U offset, the four bone matrices and the seven animated tints
                for at, size in ((0x2F8, 4), (0xDA0, 256)) + tuple((720 + 128 * k + 0x18, 4) for k in (5, 6, 8, 9, 10, 11, 12)):
                    self.assertEqual(sa[at:at + size], sr[at:at + size], hex(at))
                if t > 3.46:
                    continue
                uoff = struct.unpack_from("<f", sa, 0x2F8)[0]
                bone = struct.unpack_from("<16f", sa, 0xDA0 + 0x40)
                mx = marker[0] * bone[0] + marker[1] * bone[4] + bone[12]
                my = marker[0] * bone[1] + marker[1] * bone[5] + bone[13]
                # the fill front: where U + uoff crosses U_B along the band, between two vertex pairs
                front = None
                for k in range(0, 78, 2):
                    a, b = u[k] + uoff - U_B, u[k + 2] + uoff - U_B
                    if a >= 0 > b:
                        f = a / (a - b)
                        front = [((pos[k][i] + pos[k + 1][i]) / 2) * (1 - f) + ((pos[k + 2][i] + pos[k + 3][i]) / 2) * f for i in range(2)]
                        break
                self.assertIsNotNone(front)
                self.assertLess(math.hypot(front[0] - mx, front[1] - my), 1.5)


if __name__ == "__main__":
    unittest.main()
