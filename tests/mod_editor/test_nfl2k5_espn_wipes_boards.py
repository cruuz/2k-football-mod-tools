"""ESPN 2026 wipes and boards (beta 76 p2): art and pins, the synthetic-image round trip (apply, states, exact
revert), the Build wiring, and the real pins against the retail resources when the extracted packs are present.

The synthetic image is a real XDVDFS disc with one archive pack whose outers 3, 18, 347 and 3114 carry synthetic
scenes shaped like the six pinned resources (same chunk or slot, same descriptor sizes and mip counts: raw MRKS
wipes in wipe.cdf slots 1, 3 and 4, VC-LZ SCNEs elsewhere). No game data is involved; the shipped art is
compiled into it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _extra in (ROOT, ROOT / "tools", ROOT / "tests", Path(__file__).resolve().parent):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import numpy as np  # noqa: E402

from official_marks_fixture import install_for_class
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402
from mod_editor.core import nfl2k5_espn_wipes_boards as wipes  # noqa: E402
from mod_editor.core import nfl2k5_presentation_scenes as scenes  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, align_up  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
import presentation_scene_fixture as fixture  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"
# resource: (kind, [(width, height, mips, materials)]) with the retail descriptor sizes
SHAPES = {
    "replay_wipe": ("MRKS", [(32, 32, 1, ["pattern_flash"]), (8, 8, 1, ["a_white_streak01", "b_yellow_streak01"]),
                             (128, 64, 1, ["logo_glow_a", "logo_glow_b"]), (256, 128, 1, ["crescent01", "top_rays"])]),
    "fullscreen_WipeElectricity": ("MRKS", [(64, 64, 1, ["background1"]), (128, 128, 1, ["lightning2", "lightning1"])]),
    "fullscreen_WipeRedFlashy": ("MRKS", [(256, 256, 1, ["logo1"])]),
    "scoreboard": ("SCNE", [(128, 128, 1, ["sign02"]), (64, 64, 1, ["dot"]), (128, 128, 1, ["sign01"]),
                            (64, 64, 1, ["backboard01"])]),
    "helmetbumper": ("SCNE", [(256, 256, 6, ["monitor"]), (256, 128, 5, ["monitorcolors"])]),
    "playercard": ("SCNE", [(64, 64, 1, ["zframe_trim"]), (64, 64, 1, ["znfl_shield"]), (64, 64, 1, ["zplayers_logo"])]),
}
OUTERS = (3, 18, 347, 3114)
TAIL_ID = 0x2000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_outers() -> dict[int, bytes]:
    """Outer bodies 3, 18, 347 and 3114 with the six synthetic resources at their pinned chunks and slots."""

    spans = {}
    for seed, (name, outer, chunk, _edits) in enumerate(wipes.RESOURCES):
        kind, textures = SHAPES[name]
        decoded, system = fixture.scene_decoded(kind, textures, name=name, seed=seed + 1)
        spans[name] = (fixture.raw_span(decoded, system) if kind == "MRKS"
                       else fixture.compressed_span(decoded, system, margin=512))
    wipe = bytearray(6 * wipes.WIPE_SLOT)
    for name, slot in (("replay_wipe", 1), ("fullscreen_WipeElectricity", 3), ("fullscreen_WipeRedFlashy", 4)):
        span = spans[name]
        assert len(span) <= wipes.WIPE_SLOT
        wipe[slot * wipes.WIPE_SLOT:slot * wipes.WIPE_SLOT + len(span)] = span
    for slot in (0, 2, 5):
        filler = fixture.filler_chunk(slot)
        wipe[slot * wipes.WIPE_SLOT:slot * wipes.WIPE_SLOT + len(filler)] = filler
    return {3: fixture.outer_with({57: spans["playercard"]}, 60)[0], 18: fixture.outer_with({11: spans["helmetbumper"]}, 13)[0],
            347: fixture.outer_with({5: spans["scoreboard"]}, 7)[0], 3114: bytes(wipe)}


def disc(folder: Path, outers: dict[int, bytes]) -> SyntheticXiso:
    entries = [(0x1000 + i, outers[i] if i in outers else bytes((i % 251,)) * 16) for i in range(3115)]
    entries.append((TAIL_ID, b"tail" * 4))
    need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
    return SyntheticXiso(folder, entries, pack_sizes=(align_up(need) + ALIGNMENT,), pack_sectors=(64,))


def spans_of(image: bytes, fixture_disc: SyntheticXiso, pins: dict) -> list[tuple[int, int]]:
    out = []
    for resource in pins["resources"]:
        at = fixture_disc.virtual_to_image(fixture_disc.entry_offsets[resource["outer_index"]] + resource["chunk_offset"])
        out.append((at, at + resource["span_size"]))
    return out


def outside(image: bytes, spans: list[tuple[int, int]]) -> bytes:
    """Every byte of ``image`` outside the given spans, in order."""

    parts, cursor = [], 0
    for start, end in sorted(spans):
        parts.append(image[cursor:start])
        cursor = end
    parts.append(image[cursor:])
    return b"".join(parts)


class ArtAndPinsTests(unittest.TestCase):
    @unittest.skipUnless(wipes.available(), "official marks pack absent")
    def test_art_sizes_pins_and_refusals(self) -> None:
        pins = json.loads(wipes.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pins["schema"], wipes.PINS_SCHEMA)
        self.assertEqual(pins["art"], wipes.art_pins())
        self.assertEqual(sorted(pins["art"]), sorted(png for _n, _o, _c, edits in wipes.RESOURCES for _i, png in edits))
        self.assertEqual(len(pins["art"]), 14)
        self.assertEqual(pins["refused"], sorted(wipes.REFUSED))
        self.assertIs(pins["runtime_witnessed"], False)
        self.assertEqual([(r["name"], r["outer_index"], r["chunk_index"]) for r in pins["resources"]],
                         [(n, o, c) for n, o, c, _e in wipes.RESOURCES])
        for resource in pins["resources"]:
            self.assertNotEqual(resource["retail_sha256"], resource["applied_sha256"])
            self.assertEqual(resource["raw"], resource["outer_index"] == 3114)
            for texture in resource["textures"]:
                with self.subTest(png=texture["png"]):
                    width, height, _rgba = decode_rgba_png(wipes.art_path(texture["png"]).read_bytes(),
                                                           (texture["width"], texture["height"]))
                    self.assertEqual((width, height), (texture["width"], texture["height"]))
                    self.assertEqual(texture["png_sha256"], pins["art"][texture["png"]])
                    self.assertLessEqual(texture["palette_entries"], 256)
            if not resource["raw"]:
                fill = resource["fill"]
                self.assertLessEqual(fill["minimum_scratch"], resource["scratch"])
                self.assertEqual(fill["encoded_bytes"] + fill["zero_gap_bytes"], fill["retail_consumed"])
        self.assertTrue(wipes.available())
        self.assertIs(wipes._pins(), wipes._pins())
        self.assertIn("bermanintro", wipes.refused_targets())
        self.assertIn("propsgamecoin", wipes.refused_targets())

    def test_the_pinned_offsets_are_the_research_catalog_offsets(self) -> None:
        # r2 section 2 and the scene table: wipe.cdf slots in pack 4, the scenes in pack 0
        expected = {"replay_wipe": ("4", 0x1DE3D00), "fullscreen_WipeElectricity": ("4", 0x1E20700),
                    "fullscreen_WipeRedFlashy": ("4", 0x1E3EC00), "scoreboard": ("0", 0x6BABEB0),
                    "helmetbumper": ("0", 0xAAB030), "playercard": ("0", 0x118D30)}
        for resource in wipes._pins()["resources"]:
            self.assertEqual((resource["pack_name"], resource["pack_offset"]), expected[resource["name"]])

    def test_the_reviewed_release_catalog_carries_the_art(self) -> None:
        catalog = json.loads((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_text(encoding="utf-8"))
        self.assertNotIn("data/nfl2k5_espn_wipes_boards/playercard_znfl_shield.png", catalog["files"])
        for png in sorted(wipes.ART_DIR.glob("*.png")):
            row = catalog["files"][f"data/nfl2k5_espn_wipes_boards/{png.name}"]
            self.assertEqual((row["sha256"], row["size"]), (sha(png.read_bytes()), png.stat().st_size), png.name)
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        catalog_sha = sha((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_bytes())
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{catalog_sha}"', checker)


class SyntheticImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="espn-wipes-")
        cls.root = Path(cls.temp.name)
        install_for_class(cls, cls.root / "neutral-marks")
        cls.outers = synthetic_outers()
        cls.disc = disc(cls.root / "fixture", cls.outers)
        cls.pins = wipes.record_pins(cls.disc.path, None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def copy(self, name: str) -> Path:
        target = self.root / name
        shutil.copyfile(self.disc.path, target)
        return target

    def test_pins_from_the_synthetic_source(self) -> None:
        self.assertEqual(wipes.image_status(self.disc.path, pins=self.pins), "retail")
        self.assertEqual(wipes.image_status(self.disc.retail_packs, pins=self.pins), "retail")
        for resource in self.pins["resources"]:
            self.assertEqual(resource["outer_name_id"], 0x1000 + resource["outer_index"])
            self.assertNotEqual(resource["applied_sha256"], resource["retail_sha256"])

    def test_apply_writes_only_the_six_spans_and_reads_back(self) -> None:
        target = self.copy("apply.iso")
        before = target.read_bytes()
        receipt = wipes.apply_to_image(target, pins=self.pins)
        after = target.read_bytes()
        self.assertEqual((receipt["state"], receipt["written"], receipt["already_applied"]), ("applied", 6, 0))
        self.assertEqual(len(after), len(before))
        spans = spans_of(before, self.disc, self.pins)
        changed = np.nonzero(np.frombuffer(before, np.uint8) != np.frombuffer(after, np.uint8))[0]
        self.assertTrue(len(changed))
        self.assertTrue(all(any(a <= int(i) < b for a, b in spans) for i in changed))
        for (a, b), resource in zip(spans, self.pins["resources"]):
            self.assertEqual(after[a:a + 32], before[a:a + 32], resource["name"])      # wrapper and scratch word
            self.assertEqual(sha(after[a:b]), resource["applied_sha256"])
            parsed = scenes.open_resource(after[a:b], outer_index=resource["outer_index"],
                                          chunk_index=resource["chunk_index"])
            for texture in resource["textures"]:
                if texture["base_rgba_exact"]:
                    width, height, rgba = scenes.texture_rgba(parsed, texture["texture_index"])
                    art = wipes.art_path(texture["png"]).read_bytes()
                    self.assertEqual(rgba, decode_rgba_png(art, (width, height))[2], texture["png"])
        self.assertEqual(receipt["refused"], wipes.REFUSED)
        self.assertEqual((receipt["archive_growth"], receipt["rw_pool_growth"], receipt["runtime_witnessed"]), (0, 0, False))
        for row in receipt["resources"]:
            self.assertEqual(row["state_before"], "retail")
            self.assertTrue(row["written"] and row["wrapper_identical"])
            self.assertEqual(row["scratch_before"], row["scratch_after"])
            if not row["raw"]:
                self.assertLessEqual(row["minimum_scratch"], row["scratch_after"])
        again = wipes.apply_to_image(target, pins=self.pins)
        self.assertEqual((again["written"], again["already_applied"], again["changed_bytes"]), (0, 6, 0))
        self.assertEqual(target.read_bytes(), after)

    def test_mixed_and_foreign_states(self) -> None:
        target = self.copy("states.iso")
        wipes.apply_to_image(target, pins=self.pins)
        resource = self.pins["resources"][3]                  # the scoreboard
        at = self.disc.virtual_to_image(self.disc.entry_offsets[347] + resource["chunk_offset"])
        with target.open("r+b") as stream:
            stream.seek(at)
            stream.write(self.disc.image[at:at + resource["span_size"]])
        self.assertEqual(wipes.image_status(target, pins=self.pins), "mixed")
        self.assertEqual(wipes.resource_states(target, pins=self.pins)["scoreboard"], "retail")
        self.assertEqual(wipes.apply_to_image(target, pins=self.pins)["written"], 1)
        self.assertEqual(wipes.image_status(target, pins=self.pins), "applied")
        with target.open("r+b") as stream:
            stream.seek(at + 200)
            byte = stream.read(1)
            stream.seek(at + 200)
            stream.write(bytes((byte[0] ^ 0xFF,)))
        corrupted = target.read_bytes()
        self.assertEqual(wipes.image_status(target, pins=self.pins), "foreign")
        with self.assertRaisesRegex(wipes.EspnWipesBoardsError, "neither retail nor"):
            wipes.apply_to_image(target, pins=self.pins)
        self.assertEqual(target.read_bytes(), corrupted)

    def test_exact_revert_from_a_retail_source(self) -> None:
        target = self.copy("revert.iso")
        wipes.apply_to_image(target, pins=self.pins)
        receipt = wipes.revert_image(target, self.disc.path, pins=self.pins)
        self.assertEqual((receipt["state"], receipt["restored"]), ("retail", 6))
        self.assertEqual(target.read_bytes(), self.disc.path.read_bytes())
        applied = self.copy("not-retail.iso")
        wipes.apply_to_image(applied, pins=self.pins)
        with self.assertRaisesRegex(wipes.EspnWipesBoardsError, "retail source is not retail"):
            wipes.revert_image(target, applied, pins=self.pins)

    def test_outers_grown_after_the_spans_take_the_option_and_revert_exactly(self) -> None:
        # A Build option may append chunks to an outer and keep every earlier chunk in place (the Guardian overlay
        # appends its 88,544-byte helmet texture to GLOBAL.IFF, outer 3): the spans keep their offsets.
        grown = dict(self.outers)
        grown[3] = grown[3] + bytes(88544)
        grown[347] = grown[347] + bytes(2048)
        other = disc(self.root / "grown", grown)
        self.assertEqual(wipes.image_status(other.path, pins=self.pins), "retail")
        before = other.path.read_bytes()
        receipt = wipes.apply_to_image(other.path, pins=self.pins)
        self.assertEqual((receipt["state"], receipt["written"]), ("applied", 6))
        sizes = {row["resource"]: (row["outer_size"], row["outer_size_retail"]) for row in receipt["resources"]}
        self.assertEqual(sizes["playercard"], (len(grown[3]), len(self.outers[3])))
        self.assertEqual(sizes["scoreboard"], (len(grown[347]), len(self.outers[347])))
        after = other.path.read_bytes()
        spans = spans_of(before, other, self.pins)
        self.assertEqual(outside(after, spans), outside(before, spans))
        restored = wipes.revert_image(other.path, self.disc.path, pins=self.pins)
        self.assertEqual((restored["state"], restored["restored"]), ("retail", 6))
        self.assertEqual(other.path.read_bytes(), before)

    def test_a_moved_or_cut_span_reads_as_foreign_and_nothing_is_written(self) -> None:
        moved = dict(self.outers)
        moved[347] = bytes(16) + moved[347]                      # a chunk inserted before the scoreboard
        other = disc(self.root / "moved", moved)
        self.assertEqual(wipes.resource_states(other.path, pins=self.pins)["scoreboard"], "foreign")
        self.assertEqual(wipes.image_status(other.path, pins=self.pins), "foreign")
        before = other.path.read_bytes()
        with self.assertRaisesRegex(wipes.EspnWipesBoardsError, "neither retail nor"):
            wipes.apply_to_image(other.path, pins=self.pins)
        self.assertEqual(other.path.read_bytes(), before)
        scoreboard = next(r for r in self.pins["resources"] if r["name"] == "scoreboard")
        cut = dict(self.outers)
        cut[347] = cut[347][:scoreboard["chunk_offset"] + scoreboard["span_size"] - 1]
        short = disc(self.root / "cut", cut)
        self.assertEqual(wipes.resource_states(short.path, pins=self.pins)["scoreboard"], "foreign")
        before = short.path.read_bytes()
        with self.assertRaisesRegex(wipes.EspnWipesBoardsError, "not the pinned USA resource"):
            wipes.apply_to_image(short.path, pins=self.pins)
        self.assertEqual(short.path.read_bytes(), before)

    def test_the_real_pins_refuse_a_foreign_image(self) -> None:
        self.assertEqual(wipes.image_status(self.disc.path), "foreign")
        with self.assertRaisesRegex(wipes.EspnWipesBoardsError, "not the pinned USA resource|art differs from the pinned art"):
            wipes.apply_to_image(self.copy("foreign.iso"))


class BuildWiringTests(unittest.TestCase):
    def setUp(self):
        # This source has no PLAY archive; this test owns presentation wiring only.
        patcher = mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_plan_default_presets_availability_and_settings(self) -> None:
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.espn_wipes_boards_2026, False)
        self.assertIn("espn_wipes_boards_2026", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values["espn_wipes_boards_2026"], False, name)
            self.assertIs(mod_build.apply_preset(plan, name).espn_wipes_boards_2026, False, name)
        self.assertEqual(mod_build.availability()["espn_wipes_boards_2026"], wipes.available())
        self.assertIn("espn_wipes_boards_2026", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"espn_wipes_boards_2026": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").espn_wipes_boards_2026, True)
        with self.assertRaisesRegex(ValueError, "espn_wipes_boards_2026 must be true or false"):
            build_settings.build_settings({"espn_wipes_boards_2026": "yes"})
        self.assertEqual((wipes.DEFAULT_ENABLED, wipes.BUILD_CAPTION, wipes.LABEL),
                         (False, "ESPN 2026 wipes and boards", "EXPERIMENTAL / UNWITNESSED"))
        self.assertNotIn(chr(0x2014), wipes.HELP_TEXT + wipes.BUILD_CAPTION + "".join(wipes.REFUSED.values()))

    def test_refusals_before_any_copy(self) -> None:
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="espn-wipes-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, r"need a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), espn_wipes_boards_2026=True))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), espn_wipes_boards_2026=1))
            self.assertEqual(mod_build.inspect(xbe)["espn_wipes_boards_2026"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_build_step_lands_in_the_receipt(self) -> None:
        from test_mod_build_performance import synthetic_disc
        calls = []

        def apply_to_image(target, *, progress=None, pins=None, marks_pack=None):
            self.assertEqual(marks_pack, "chosen-pack")
            calls.append(Path(target))
            return {"state": "applied", "label": wipes.LABEL, "resources": [], "written": 6, "refused": wipes.REFUSED}

        stand_in = types.SimpleNamespace(image_status=lambda source: "retail", available=lambda *_: True, validate_art=lambda root: self.assertEqual(root, "chosen-pack"),
                                         apply_to_image=apply_to_image)
        real = mod_build._core_module
        with tempfile.TemporaryDirectory(prefix="espn-wipes-build-") as raw:
            root = Path(raw)
            source = root / "retail.iso"
            synthetic_disc(source)
            original = source.read_bytes()
            with mock.patch.object(mod_build, "_core_module",
                                   side_effect=lambda name: stand_in if name == "nfl2k5_espn_wipes_boards" else real(name)):
                receipt = mod_build.build(mod_build.BuildPlan(str(source), str(root / "out.iso"),
                                                              espn_wipes_boards_2026=True, official_marks_pack="chosen-pack"))
            self.assertEqual(len(calls), 1)
            step = [s for s in receipt["steps"] if s["step"] == "espn_wipes_boards_2026"]
            self.assertEqual(len(step), 1)
            self.assertEqual(step[0]["refused"], wipes.REFUSED)
            self.assertEqual(receipt["result"]["espn_wipes_boards_2026"], "applied")
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue((root / "out.iso").is_file())


@unittest.skipUnless(wipes.available() and (PACKS / "0").is_file() and (PACKS / "4").is_file(),
                     "extracted retail vc_53450030 packs absent; set NFL2K5_GAME_DIR")
class RetailPinsTests(unittest.TestCase):
    """The shipped pins against the real resources: apply and revert on a synthetic disc carrying the four
    real outers, with every byte outside the six spans hashed unchanged."""

    def test_packs_read_as_retail_and_the_option_applies_and_reverts_exactly(self) -> None:
        import nfl2k5_playbook_position_recode as recode
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(GAME)
        self.assertEqual(wipes.image_status(GAME), "retail")
        with recode.OuterImage(GAME) as archive:
            outers = {index: archive.read(archive.entries[index].virtual_offset, archive.entries[index].size)
                      for index in OUTERS}
            names = {index: archive.entries[index].name_id for index in OUTERS}
        pins = wipes._pins()
        with tempfile.TemporaryDirectory(prefix="espn-wipes-retail-") as raw:
            root = Path(raw)
            entries = [(names[i] if i in outers else 0x1000 + i, outers[i] if i in outers else bytes((i % 251,)) * 16)
                       for i in range(3115)]
            entries.append((TAIL_ID, b"tail" * 4))
            need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
            fixture_disc = SyntheticXiso(root / "disc", entries, pack_sizes=(align_up(need) + ALIGNMENT,),
                                         pack_sectors=(64,))
            target = root / "target.iso"
            shutil.copyfile(fixture_disc.path, target)
            before = target.read_bytes()
            self.assertEqual(wipes.image_status(target), "retail")
            receipt = wipes.apply_to_image(target)
            self.assertEqual((receipt["state"], receipt["written"]), ("applied", 6))
            after = target.read_bytes()
            spans = spans_of(before, fixture_disc, pins)
            self.assertEqual(sha(outside(after, spans)), sha(outside(before, spans)))
            self.assertNotEqual(after, before)
            self.assertEqual(wipes.image_status(target), "applied")
            self.assertEqual(wipes.revert_image(target, fixture_disc.path)["state"], "retail")
            self.assertEqual(target.read_bytes(), fixture_disc.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
