"""Modern goalposts (beta 77 v1): the scene compiler on synthetic data, the pins, the sprite scorebug's gamedata.iff
rule with the two goalpost spans, the image plumbing on an in-memory archive, the Build wiring, and, when the
extracted retail files are present, the real compile against the retail goalpost scenes and the executable sites.

No game data is involved in the always-on tests; the retail checks read the user's own extracted files and skip
without them (point NFL2K5_GAME_DIR at the folder holding default.xbe and vc_53450030/).
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
from mod_editor.core import nfl2k5_modern_goalposts as goal  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACK0 = GAME / "vc_53450030" / "0"
XBE = GAME / "default.xbe"
HAVE_GAME = PACK0.is_file() and XBE.is_file()
FOOT = 30.48


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_scene(scene: str) -> bytes:
    """A decoded buffer laid out like the retail scene: the retail position constant, two uprights of eight
    vertices each topped at 1,219.2 cm (plus caps), and everything else at or below the crossbar."""
    spec = goal.SCENES[scene]
    buf = bytearray(spec["size"])
    rec = spec["record"]
    scale, offset = 610.8191528320312, (0.0, 609.5999755859375, -102.41875457763672)
    struct.pack_into("<4f", buf, rec + 0x10, scale, scale, scale, 0.0)
    struct.pack_into("<4f", buf, rec + 0x20, *offset, 1.0)
    struct.pack_into("<H", buf, rec + 0x4C, spec["vertices"])
    points = []
    for k in range(spec["vertices"]):
        if k < spec["tops"]:
            side = -1 if k % 2 else 1
            points.append((side * (281.93 + (k % 4) * 3.4), 1219.2074, (k % 3) * 3.0 - 3.0))
        else:
            points.append(((k % 7) * 40.0 - 120.0, (k * 37) % 300 + 0.5, -(k % 5) * 40.0))
    for k, p in enumerate(points):
        q = tuple(goal._encode_normshort((p[a] - offset[a]) / scale) for a in range(3))
        struct.pack_into("<3h", buf, spec["positions"] + 6 * k, *q)
    # recognisable bytes elsewhere (colours, strips) that the compiler must leave alone
    for at in range(0, spec["positions"], 7):
        if not any(a <= at < b for a, b in goal.changed_ranges(scene)) and not rec + 0x4C <= at < rec + 0x4E:
            buf[at] = (at * 13) & 0xFF
    return bytes(buf)


class SceneCompiler(unittest.TestCase):
    def test_tops_rise_to_45_ft_and_nothing_else_moves(self):
        for scene in goal.SCENES:
            with self.subTest(scene=scene):
                before = synthetic_scene(scene)
                after = goal.compile_scene(scene, before)
                self.assertEqual(len(after), len(before))
                self.assertEqual(goal.changed_outside(scene, before, after), [])
                old, new = goal.positions(before, scene), goal.positions(after, scene)
                spec = goal.SCENES[scene]
                step = struct.unpack_from("<f", after, spec["record"] + 0x10)[0] / 32767
                for k, (a, b) in enumerate(zip(old, new)):
                    if abs(a[1] - goal.RETAIL_TOP) <= goal.TOP_TOLERANCE:
                        self.assertAlmostEqual(b[1], goal.MODERN_TOP, delta=step)
                        self.assertAlmostEqual(b[0], a[0], delta=step)
                        self.assertAlmostEqual(b[2], a[2], delta=step)
                    else:
                        self.assertLessEqual(math.dist(a, b), step)
                centre = struct.unpack_from("<3f", after, spec["record"])
                radius = struct.unpack_from("<f", after, spec["record"] + 0x48)[0]
                self.assertTrue(all(math.dist(centre, p) <= radius for p in new))
                self.assertEqual(struct.unpack_from("<4f", after, spec["record"] + 0x10)[1:],
                                 (struct.unpack_from("<f", after, spec["record"] + 0x10)[0],) * 2 + (0.0,))

    def test_growth_is_the_five_feet_of_the_2014_rule(self):
        self.assertAlmostEqual(goal.RETAIL_TOP - goal.CROSSBAR_TOP, 30 * FOOT, places=6)
        self.assertAlmostEqual(goal.MODERN_TOP - goal.CROSSBAR_TOP, 35 * FOOT, places=6)
        self.assertAlmostEqual(goal.GROWTH, 1.125)

    def test_refuses_an_unexpected_top_count_or_geometry_between_bar_and_tops(self):
        scene = "goalpost"
        spec = goal.SCENES[scene]
        bad = bytearray(synthetic_scene(scene))
        struct.pack_into("<3h", bad, spec["positions"], 0, 0, 0)        # one top vertex dropped to the middle
        with self.assertRaises(goal.ModernGoalpostsError):
            goal.compile_scene(scene, bytes(bad))
        with self.assertRaises(goal.ModernGoalpostsError):
            goal.compile_scene(scene, synthetic_scene(scene)[:-16])

    def test_changed_ranges_are_the_record_fields_and_the_position_stream(self):
        for scene, spec in goal.SCENES.items():
            rec = spec["record"]
            self.assertEqual(goal.changed_ranges(scene),
                             ((rec, rec + 0x10), (rec + 0x10, rec + 0x30), (rec + 0x48, rec + 0x4C),
                              (spec["positions"], spec["positions"] + 6 * spec["vertices"])))


class Pins(unittest.TestCase):
    def test_pins_load_and_are_canonical(self):
        self.assertTrue(goal.available())
        pins = json.loads(goal.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual([(r["scene"], r["chunk_index"]) for r in pins["resources"]], list(goal.RESOURCES))
        self.assertFalse(pins["runtime_witnessed"])
        self.assertEqual(goal.PINS_PATH.read_text(encoding="utf-8"), json.dumps(pins, indent=2, sort_keys=True) + "\n")
        for row in pins["resources"]:
            spec = goal.SCENES[row["scene"]]
            self.assertEqual((row["chunk_index"], row["decoded_size"]), (spec["chunk"], spec["size"]))
            self.assertLessEqual(row["fill"]["filled_bytes"], row["fill"]["stored_size"])
            self.assertTrue(row["fill"]["wrapper_identical"])

    def test_pins_refuse_malformed_documents(self):
        pins = json.loads(goal.PINS_PATH.read_text(encoding="utf-8"))
        for mutate in (lambda d: d.update(schema="x"), lambda d: d["resources"].reverse(),
                       lambda d: d["resources"][0].update(applied_sha256=d["resources"][0]["retail_sha256"]),
                       lambda d: d["outer"].update(index=3), lambda d: d["resources"][1].update(chunk_offset=545616)):
            bad = json.loads(json.dumps(pins))
            mutate(bad)
            with self.assertRaises(goal.ModernGoalpostsError):
                goal._check_pins(bad)

    def test_the_sprite_reads_the_same_spans(self):
        self.assertEqual(sprite.goalpost_spans(), goal.span_rows())


class SpriteHudRule(unittest.TestCase):
    """nfl2k5_scorebug_sprite accepts the HUD with the goalpost spans at retail or applied pins (shipped-pins rule)."""

    def setUp(self):
        import random
        rng = random.Random(77)
        self.hud = bytes(rng.getrandbits(8) for _ in range(64 * 1024))
        self.marks = [("m%d" % k, 1000 + k * 5000, 700) for k in range(4)]
        self.kick = [("KickArrow", 30000, 900), ("KickMeter", 32000, 4000), ("windmeter", 40000, 500)]
        self.goals = [("goalpost_shadow", 26000, 1968), ("goalpost", 45000, 2832)]
        spans = self.marks + self.kick + self.goals
        self.applied = {name: bytes(rng.getrandbits(8) for _ in range(size)) for name, _at, size in spans}
        rows = lambda group: tuple((n, at, size, sha(self.hud[at:at + size]), sha(self.applied[n])) for n, at, size in group)  # noqa: E731

        def outside(group):
            digest = hashlib.sha256(); cursor = 0
            for _n, at, size in sorted(group, key=lambda r: r[1]):
                digest.update(self.hud[cursor:at]); cursor = at + size
            digest.update(self.hud[cursor:])
            return digest.hexdigest()
        self.patches = [mock.patch.object(sprite, "espn_mark_spans", lambda pins=None: (len(self.hud), rows(self.marks))),
                        mock.patch.object(sprite, "kick_meter_spans", lambda pins=None: rows(self.kick)),
                        mock.patch.object(sprite, "goalpost_spans", lambda pins=None: rows(self.goals)),
                        mock.patch.object(sprite, "HUD_OUTSIDE_IN_PLACE", outside(self.marks + self.kick)),
                        mock.patch.object(sprite, "HUD_OUTSIDE_WITH_GOALPOSTS", outside(spans))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def splice(self, names):
        hud = bytearray(self.hud)
        for n, at, size in self.marks + self.kick + self.goals:
            if n in names:
                hud[at:at + size] = self.applied[n]
        return bytes(hud)

    def test_goalpost_spans_retail_or_applied_are_supported(self):
        for chosen in ({"goalpost"}, {"goalpost", "goalpost_shadow"}, {"goalpost", "KickMeter", "m2"}):
            with self.subTest(applied=sorted(chosen)):
                states = sprite._hud_in_place(self.splice(chosen))
                self.assertIsNotNone(states)
                self.assertEqual({n for n, s in states.items() if s == "applied"}, chosen)
                self.assertIsNotNone(sprite.hud_espn_marks(self.splice(chosen)))

    def test_the_earlier_rule_reads_as_before_while_the_goalposts_are_retail(self):
        states = sprite._hud_in_place(self.splice({"KickMeter"}))
        self.assertEqual(set(states), {"m0", "m1", "m2", "m3", "KickArrow", "KickMeter", "windmeter"})

    def test_anything_else_is_foreign(self):
        full = self.splice({"goalpost", "goalpost_shadow"})
        for at in (0, 26000 + 1967, 45000 + 5, 47900, len(full) - 1):
            bad = bytearray(full); bad[at] ^= 1
            self.assertIsNone(sprite._hud_in_place(bytes(bad)), hex(at))
        self.assertIsNone(sprite._hud_in_place(full + b"\0"))
        with mock.patch.object(sprite, "goalpost_spans", lambda pins=None: None):
            self.assertIsNone(sprite._hud_in_place(full))


class FakeEntry:
    def __init__(self, name_id, size, virtual_offset):
        self.name_id, self.size, self.virtual_offset = name_id, size, virtual_offset


class FakeArchive:
    """An in-memory outer archive: entries by index, read and write by virtual offset."""
    store: dict[str, bytearray] = {}

    def __init__(self, path, *, writable=False):
        self.buf = FakeArchive.store[str(path)]
        self.entries = [FakeEntry(0, 0, 0)] * goal.OUTER_INDEX + [FakeEntry(goal.OUTER_NAME_ID, 8192, 4096)]

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
        rng = random.Random(2014)
        self.image = bytearray(rng.getrandbits(8) for _ in range(16384))
        rows, self.applied = [], {}
        for k, (scene, chunk) in enumerate(goal.RESOURCES):
            offset, size = 256 + k * 1024, 600
            retail = bytes(self.image[4096 + offset:4096 + offset + size])
            applied = bytes(b ^ 0x5A for b in retail)
            self.applied[retail] = applied
            rows.append(dict(scene=scene, chunk_index=chunk, chunk_offset=offset, span_size=size, decoded_size=size,
                             retail_sha256=sha(retail), applied_sha256=sha(applied), retail_decoded_sha256="1" * 64,
                             applied_decoded_sha256="2" * 64))
        self.pins = dict(schema=goal.PINS_SCHEMA, outer=dict(index=goal.OUTER_INDEX, name_id=goal.OUTER_NAME_ID,
                                                             size=8192), resources=rows, runtime_witnessed=False)
        FakeArchive.store = {"target": bytearray(self.image), "retail": bytearray(self.image)}
        self.xbe = {"target": "retail", "retail": "retail"}

        def write_xbe(path, transform):
            self.xbe[str(path)] = transform(self.xbe[str(path)])
            return None

        def apply_xbe(state):
            goal.require(state in ("retail", "applied"), "foreign")
            return "applied", {}

        def restore_xbe(state):
            goal.require(state in ("retail", "applied"), "foreign")
            return "retail"
        locate = lambda outer, document: {r["scene"]: (r["chunk_offset"], r["span_size"]) for r in document["resources"]}  # noqa: E731
        self.patches = [mock.patch.object(goal, "_outer_image", lambda: FakeArchive),
                        mock.patch.object(goal, "locate_chunks", locate),
                        mock.patch.object(goal, "compile_span", lambda span, row: (self.applied[span], {})),
                        mock.patch.object(goal, "_write_xbe", write_xbe),
                        mock.patch.object(goal, "_xbe_of", lambda source: self.xbe[str(source)]),
                        mock.patch.object(goal, "xbe_status", lambda payload: payload),
                        mock.patch.object(goal, "apply_xbe", apply_xbe),
                        mock.patch.object(goal, "restore_xbe", restore_xbe)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_apply_is_exact_idempotent_and_reverts(self):
        self.assertEqual(goal.image_status("target", document=self.pins), "retail")
        receipt = goal.apply_to_image("target", document=self.pins)
        self.assertEqual((receipt["state"], receipt["written"], receipt["runtime_witnessed"]), ("applied", 2, False))
        self.assertEqual(goal.image_status("target", document=self.pins), "applied")
        again = goal.apply_to_image("target", document=self.pins)
        self.assertEqual((again["written"], again["already_applied"]), (0, 2))
        outside = [i for i in range(len(self.image)) if FakeArchive.store["target"][i] != self.image[i]
                   and not any(4096 + r["chunk_offset"] <= i < 4096 + r["chunk_offset"] + r["span_size"]
                               for r in self.pins["resources"])]
        self.assertEqual(outside, [])
        revert = goal.revert_image("target", "retail", document=self.pins)
        self.assertEqual((revert["state"], revert["restored"]), ("retail", 2))
        self.assertEqual(FakeArchive.store["target"], bytearray(self.image))
        self.assertEqual(self.xbe["target"], "retail")

    def test_half_installed_reads_mixed_and_foreign_refuses(self):
        self.xbe["target"] = "applied"
        self.assertEqual(goal.image_status("target", document=self.pins), "mixed")
        self.xbe["target"] = "retail"
        row = self.pins["resources"][1]
        at = 4096 + row["chunk_offset"]
        FakeArchive.store["target"][at] ^= 0xFF
        self.assertEqual(goal.image_status("target", document=self.pins), "foreign")
        with self.assertRaises(goal.ModernGoalpostsError):
            goal.apply_to_image("target", document=self.pins)
        self.xbe["target"] = "foreign"
        FakeArchive.store["target"][at] ^= 0xFF
        self.assertEqual(goal.image_status("target", document=self.pins), "foreign")


class BuildWiring(unittest.TestCase):
    def test_plan_default_presets_availability_and_settings(self):
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.modern_goalposts, False)
        self.assertIn("modern_goalposts", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            with self.subTest(preset=name):
                self.assertIs(values["modern_goalposts"], False)
                self.assertIs(mod_build.apply_preset(plan, name).modern_goalposts, False)
        self.assertTrue(mod_build.availability()["modern_goalposts"])
        self.assertIn("modern_goalposts", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"modern_goalposts": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").modern_goalposts, True)
        with self.assertRaisesRegex(ValueError, "modern_goalposts must be true or false"):
            build_settings.build_settings({"modern_goalposts": "yes"})
        self.assertEqual((goal.DEFAULT_ENABLED, goal.CAVES, goal.REQUESTS, goal.RUNTIME_GLOBALS, goal.LABEL),
                         (False, (), (), (), "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self):
        import tempfile
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="goalposts-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, "needs? a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), modern_goalposts=True))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), modern_goalposts=1))
            self.assertEqual(mod_build.inspect(xbe)["modern_goalposts"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_registry_row(self):
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text(encoding="utf-8"))
        row = [c for c in registry["capabilities"] if c["id"] == "nfl2k5.stadiums_fields.modern_goalposts"][0]
        self.assertEqual(row["backend"]["module"], "mod_editor/core/nfl2k5_modern_goalposts.py")
        self.assertEqual(row["validation_command"], "python3 -m tests.mod_editor.test_nfl2k5_modern_goalposts")
        self.assertFalse(row["gui"]["default_enabled"])
        pins = json.loads(goal.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(row["source_container"]["hash_pins"], [r["retail_sha256"] for r in pins["resources"]])

    def test_the_build_steps_and_panel_name_the_option(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        for needle in ('goalposts.apply_to_image(target, progress=progress)', '"step": "modern_goalposts"',
                       'goalposts.image_status(source)'):
            self.assertIn(needle, source)
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        for needle in ('"modern_goalposts": self.modern_goalposts_check', "modern_goalposts=self._modern_goalposts_changed()",
                       "def _modern_goalposts_changed(self)"):
            self.assertIn(needle, panel)

    def test_the_manifest_generator_declares_the_executable_edits(self):
        source = (ROOT / "mod_editor/core/nfl2k5_cave_manifest.py").read_text(encoding="utf-8")
        for needle in ("goalposts.apply_xbe(final)", "(goalposts.XbePatch, {})", "goalposts.OWNER",
                       "goalposts.xbe_reservations(final)"):
            self.assertIn(needle, source)

    def test_the_operands_are_four_bytes_after_retail_opcodes(self):
        self.assertEqual([(label, size) for label, _va, size in goal.operand_ranges()],
                         [("upright_line_left_top", 4), ("upright_line_right_top", 4), ("upright_collision_top", 4)])
        self.assertEqual(goal.PUSH_RETAIL.hex(), "6866669844")
        self.assertEqual(goal.PUSH_MODERN.hex(), "683373ab44")
        self.assertEqual(goal.FADD_RETAIL.hex(), "d80510a55000")
        self.assertEqual(goal.FADD_MODERN.hex(), "d8059c684f00")
        self.assertEqual(goal.xbe_status(b""), "foreign")


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail default.xbe and vc_53450030/0")
class RetailScenes(unittest.TestCase):
    """The real compile against the retail goalpost scenes (the user's own extracted files)."""

    @classmethod
    def setUpClass(cls):
        cls.pack0 = PACK0.read_bytes()
        at, size = goal.locate_outer(cls.pack0)
        cls.outer = cls.pack0[at:at + size]
        cls.where = goal.locate_chunks(cls.outer)

    def span(self, scene):
        off, size = self.where[scene]
        return self.outer[off:off + size]

    def test_compile_reproduces_the_applied_pins(self):
        rows = {r["scene"]: r for r in goal.pins()["resources"]}
        for scene in goal.SCENES:
            with self.subTest(scene=scene):
                after, detail = goal.compile_span(self.span(scene), rows[scene])
                self.assertEqual(sha(after), rows[scene]["applied_sha256"])
                self.assertEqual(len(after), rows[scene]["span_size"])
                self.assertTrue(detail["wrapper_identical"])

    def test_geometry_read_back_with_the_generic_model_reader(self):
        from mod_editor.core import nfl2k5_models as models
        rows = {r["scene"]: r for r in goal.pins()["resources"]}
        for scene, chunk in goal.RESOURCES:
            with self.subTest(scene=scene):
                key = f"o346c{chunk}"
                before_dec = goal.decode_span(self.span(scene))
                after = goal.compile_span(self.span(scene), rows[scene])[0]
                source = models.ModelSpanSource({key: after})
                _res, decoded, parsed = source.parse(key)
                shape = parsed["shapes"][0]
                lanes = models._shape_lanes(parsed, shape, decoded)
                points = models.read_positions(decoded, shape, lanes)
                tops = [p for p in points if p[1] > 1000]
                self.assertEqual(len(tops), goal.SCENES[scene]["tops"])
                self.assertTrue(all(abs(p[1] - goal.MODERN_TOP) < 0.03 for p in tops))
                self.assertAlmostEqual(min(abs(p[0]) for p in points if p[1] > 400), 281.93, delta=0.03)
                self.assertAlmostEqual(max(abs(p[0]) for p in points if p[1] > 400), 292.09, delta=0.03)
                self.assertLess(max(p[1] for p in points if p[1] < 1000), goal.CROSSBAR_TOP + 0.1)
                # colours, UVs and the strips are the retail bytes
                spec = goal.SCENES[scene]
                end_positions = spec["positions"] + 6 * spec["vertices"]
                self.assertEqual(decoded[end_positions:], before_dec[end_positions:])
                rec = spec["record"]
                self.assertEqual(decoded[rec + 0x30:rec + 0x48], before_dec[rec + 0x30:rec + 0x48])
                self.assertEqual(decoded[:rec], before_dec[:rec])

    def test_pack0_apply_touches_only_the_two_spans_and_is_idempotent(self):
        after, detail = goal.apply_pack0(self.pack0)
        changed = [i for i in range(len(self.pack0)) if after[i] != self.pack0[i]]
        spans = [(r["pack0_offset"], r["pack0_offset"] + r["span_size"]) for r in detail["resources"]]
        self.assertTrue(changed and all(any(a <= i < b for a, b in spans) for i in changed))
        self.assertEqual(goal.apply_pack0(after)[0], after)
        self.assertEqual(set(goal.pack0_states(after).values()), {"applied"})

    def test_the_sprite_rule_constant_is_the_retail_hud_with_nine_spans_cut(self):
        from mod_editor.core import nfl2k5_scorebug_resources as art
        hud = self.outer[:art.HUD_SIZE]
        rows = sorted(sprite.espn_mark_spans()[1] + sprite.kick_meter_spans() + sprite.goalpost_spans(),
                      key=lambda r: r[1])
        digest = hashlib.sha256(); cursor = 0
        for _n, at, size, _r, _a in rows:
            digest.update(hud[cursor:at]); cursor = at + size
        digest.update(hud[cursor:])
        self.assertEqual(digest.hexdigest(), sprite.HUD_OUTSIDE_WITH_GOALPOSTS)
        after = bytearray(hud)
        for scene, off, size, _r, applied in sprite.goalpost_spans():
            after[off:off + size] = goal.compile_span(hud[off:off + size],
                                                      {r["scene"]: r for r in goal.pins()["resources"]}[scene])[0]
        states = sprite.hud_espn_marks(bytes(after))
        self.assertEqual((states["goalpost"], states["goalpost_shadow"]), ("applied", "applied"))
        self.assertIsNone(sprite._hud_cut(bytes(after), sprite.espn_mark_spans()[1] + sprite.kick_meter_spans(),
                                          sprite.HUD_OUTSIDE_IN_PLACE))   # the earlier rule alone refuses it


@unittest.skipUnless(HAVE_GAME, "needs the extracted retail default.xbe")
class RetailExecutable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = XBE.read_bytes()

    def test_sites_are_retail_then_modern_then_retail_again(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        self.assertEqual(goal.xbe_status(self.xbe), "retail")
        after, receipt = goal.apply_xbe(self.xbe)
        self.assertEqual(goal.xbe_status(after), "applied")
        self.assertEqual(receipt["sections_resealed"], [0])
        self.assertTrue(all(section_digest(after, s) == s.stored_digest for s in _sections(after)))
        changed = [i for i in range(len(self.xbe)) if after[i] != self.xbe[i]]
        offset = goal._xbe_offsets(self.xbe)
        operands = [(offset(va, size), offset(va, size) + size) for _l, va, size in goal.operand_ranges()]
        text = _sections(self.xbe)[0]
        digest = (text.header_offset + 36, text.header_offset + 56)
        self.assertTrue(all(any(a <= i < b for a, b in operands + [digest]) for i in changed))
        self.assertEqual(goal.apply_xbe(after)[0], after)
        self.assertEqual(goal.restore_xbe(after), self.xbe)

    def test_the_constants_the_sites_rely_on(self):
        offset = goal._xbe_offsets(self.xbe)
        f32 = lambda va: struct.unpack_from("<f", self.xbe, offset(va, 4))[0]  # noqa: E731
        self.assertAlmostEqual(f32(goal.SHARED_TOP_VA), 1219.2, places=3)       # left untouched
        self.assertAlmostEqual(f32(goal.MODERN_LITERAL_VA), 1371.6, places=3)
        # The scoring rectangle at 0x510410: x within the inside edges, y from the crossbar to 30,480 cm.
        self.assertEqual(tuple(round(f32(0x510410 + 4 * k), 2) for k in range(4)), (-281.94, 304.8, 281.94, 30480.0))

    def test_the_shared_constant_keeps_its_other_readers_and_the_literal_is_never_written(self):
        text = self.xbe[0x1000:0x1000 + 0x40F114]
        refs = lambda va: [0x11000 + i for i in range(len(text) - 3)  # noqa: E731
                           if text[i:i + 4] == struct.pack("<I", va)]
        self.assertEqual(refs(goal.SHARED_TOP_VA), [0x19F0B7, 0x19F180, 0x1C6A2E, 0x216452])
        self.assertEqual(len(refs(goal.MODERN_LITERAL_VA)), 31)
        for ref in refs(goal.MODERN_LITERAL_VA):
            opcode, modrm = self.xbe[ref - 0x10000 - 2:ref - 0x10000]
            self.assertEqual(modrm & 0xC7, 0x05, hex(ref))              # [disp32]
            # D8 /r (fadd, fmul, fcom, fcomp, fsub, ...) only reads its operand; D9 /0 is fld (D9 /2, /3 would store)
            self.assertTrue(opcode == 0xD8 or (opcode == 0xD9 and modrm & 0x38 == 0), hex(ref))


if __name__ == "__main__":
    unittest.main()
