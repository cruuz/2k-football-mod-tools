"""ESPN presentation marks (2026) (beta 76): art and pins, the shield_espn wrap, the synthetic-image round
trip (apply, states, exact revert), the Build wiring, and the real pins when retail packs are present.

The synthetic image is a real XDVDFS disc with one archive pack whose outer 346 is a small gamedata.iff
carrying four compressed P8 TXTRs with the retail names, sizes, stored bodies, scratch words and stream
parameters at chunks 24, 26, 33 and 57. No game data is involved; the shipped art is compiled into it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
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
from mod_editor.core import nfl2k5_espn_marks as marks  # noqa: E402
from mod_editor.core import nfl2k5_presentation_standalone as presentation  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, align_up  # noqa: E402
from nfl_tset_png_import import decode_rgba_png  # noqa: E402
import nfl_txtr as txtr  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"
# texture: (chunk, width, height, stored body, scratch word, stream tag, offset bits, packed format) as retail
SHAPES = {
    "nfl_chiclet": (24, 64, 64, 4336, 144, 130, 12, 0x06610B29),
    "shield_espn": (26, 128, 64, 5920, 112, 99, 11, 0x06710B29),
    "espnLogo1": (33, 256, 256, 6208, 16, 1, 10, 0x08810B29),
    "z_ESPN_bug": (57, 64, 64, 4032, 80, 55, 10, 0x06610B29),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def synthetic_txtr(name: str) -> bytes:
    """One compressed P8 TXTR span shaped like the retail mark (synthetic stripes, not game data)."""

    _chunk, width, height, stored, scratch, tag, bits, packed = SHAPES[name]
    system = bytearray(128)
    system[0x0C:0x10] = b"TXTR"
    struct.pack_into("<II", system, 0x10, 0x20 - 0x0F, 0x40 - 0x13)
    encoded = name.encode("utf-16le") + b"\0\0"
    system[0x20:0x20 + len(encoded)] = encoded
    struct.pack_into("<6I", system, 0x40, 0, 0, width * height, packed, 0, 0x80000000)
    indices = bytes(((x // 8) + (y // 8)) % 4 for y in range(height) for x in range(width))
    palette = b"".join(bytes((40 * i % 256, 90, 160, 255)) for i in range(256))
    decoded = bytes(system) + indices + palette
    stream, _info = txtr.compress_vc_lz(decoded, stream_tag=tag, offset_bits=bits, verify_roundtrip=True)
    assert len(stream) <= stored
    header = txtr.HEADER.pack(b"TXTR", stored, 128, width * height + 1024, txtr.COMPRESSED_SENTINEL, scratch, 0, 0)
    return header + stream + bytes(stored - len(stream))


def filler(index: int) -> bytes:
    return txtr.HEADER.pack(b"Unif", 32, 0, 0, 0, 0, 0, 0) + bytes((index % 251,)) * 32


def synthetic_gamedata() -> tuple[bytes, dict[str, int]]:
    by_chunk = {shape[0]: name for name, shape in SHAPES.items()}
    out, offsets = bytearray(), {}
    for index in range(59):
        if index in by_chunk:
            offsets[by_chunk[index]] = len(out)
            out += synthetic_txtr(by_chunk[index])
        else:
            out += filler(index)
    return bytes(out), offsets


class SyntheticDisc:
    """A synthetic XISO whose outer 346 is gamedata.iff, plus the matching inventory rows."""

    def __init__(self, folder: Path):
        gamedata, offsets = synthetic_gamedata()
        entries = [(0x1000 + i, bytes((i % 251,)) * 16) for i in range(346)]
        entries += [(presentation.OUTER_NAME_ID, gamedata), (0x2000, b"tail" * 4)]
        need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
        pack = (need + ALIGNMENT - 1) // ALIGNMENT * ALIGNMENT + ALIGNMENT
        self.xiso = SyntheticXiso(folder, entries, pack_sizes=(pack,), pack_sectors=(64,))
        self.path = self.xiso.path
        self.gamedata = gamedata
        entry_offset = self.xiso.entry_offsets[346]
        self.rows = {}
        for name, (chunk, width, height, stored, _s, _t, _b, _p) in SHAPES.items():
            span = gamedata[offsets[name]:offsets[name] + 32 + stored]
            self.rows[name] = dict(
                texture=name, outer_index=346, outer_id=f"0x{presentation.OUTER_NAME_ID:08x}",
                outer_size=len(gamedata), chunk_index=chunk, chunk_offset=offsets[name], span_size=len(span),
                span_sha256=sha(span), pack_name="0", pack_offset=entry_offset + offsets[name], width=width,
                height=height, mip_levels=1, authored_grade=presentation.AUTHORED_GRADES[name])

    def span_at(self, image: bytes, name: str) -> bytes:
        row = self.rows[name]
        at = self.xiso.virtual_to_image(self.xiso.entry_offsets[346] + row["chunk_offset"])
        return image[at:at + row["span_size"]]


class ArtAndPinsTests(unittest.TestCase):
    @unittest.skipUnless(marks.available(), "official marks pack absent")
    def test_art_sizes_pins_and_grades(self) -> None:
        pins = json.loads(marks.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(pins["schema"], marks.PINS_SCHEMA)
        self.assertEqual(pins["art"], marks.art_pins())
        self.assertEqual(sorted(pins["art"]), sorted(f"{name}.png" for name in marks.MARKS))
        self.assertEqual([m["texture"] for m in pins["marks"]], list(marks.MARKS))
        self.assertEqual({m["texture"]: m["grade"] for m in pins["marks"]}, presentation.AUTHORED_GRADES)
        self.assertEqual(pins["refused"], sorted(presentation.REFUSED))
        self.assertIs(pins["runtime_witnessed"], False)
        for mark in pins["marks"]:
            with self.subTest(mark=mark["texture"]):
                width, height, _rgba = decode_rgba_png(marks.art_path(mark["png"]).read_bytes(),
                                                       (mark["width"], mark["height"]))
                self.assertEqual((width, height), (mark["width"], mark["height"]))
                fill = mark["fill"]
                self.assertTrue(fill["wrapper_identical"])
                self.assertLessEqual(fill["exact_minimum_scratch"], fill["scratch_bytes"])
                self.assertEqual(fill["filled_bytes"] + fill["padding_bytes"], fill["stored_size"])
                self.assertEqual(fill["stored_size"] + 32, mark["span_size"])
        self.assertTrue(marks.available())
        self.assertIs(marks._pins(), marks._pins())

    def test_pins_agree_with_the_pinned_gamedata_inventory(self) -> None:
        rows = presentation.rows_by_texture()
        for mark in marks._pins()["marks"]:
            row = rows[mark["texture"]]
            self.assertEqual((mark["chunk_index"], mark["chunk_offset"], mark["span_size"], mark["retail_sha256"]),
                             (row["chunk_index"], row["chunk_offset"], row["span_size"], row["span_sha256"]))

    def test_the_reviewed_release_catalog_carries_the_art(self) -> None:
        catalog = json.loads((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_text(encoding="utf-8"))
        for name in marks.MARKS:
            relative = f"data/nfl2k5_espn_marks/{name}.png"
            self.assertNotIn(relative, catalog["files"])
            self.assertFalse((ROOT / relative).exists())
        checker = (ROOT / "packaging" / "check_2k5_mod_studio_release.py").read_text(encoding="utf-8")
        catalog_sha = sha((ROOT / "packaging" / "nfl2k5_scorebug_template_pngs.json").read_bytes())
        self.assertIn(f'SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 = "{catalog_sha}"', checker)


class ShieldEspnWrapTests(unittest.TestCase):
    """Every shield_espn consumer draws the texture through these two triangles; the art must read whole."""

    @staticmethod
    def reassemble(alpha: np.ndarray, scale: float = 8.0):
        th, tw = alpha.shape
        xs = [p[0] for t in marks.SHIELD_ESPN_WRAP for p in t["pos"]]
        ys = [p[1] for t in marks.SHIELD_ESPN_WRAP for p in t["pos"]]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        w, h = int((x1 - x0) * scale), int((y1 - y0) * scale)
        gy, gx = np.mgrid[0:h, 0:w]
        px, py = x0 + (gx + 0.5) / scale, y1 - (gy + 0.5) / scale
        shown = np.zeros((h, w))
        for tri in marks.SHIELD_ESPN_WRAP:
            (ax, ay), (bx, by), (cx, cy) = tri["pos"]
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            l0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
            l1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
            l2 = 1 - l0 - l1
            inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            u = sum(l * (uv[0] + 1) / 2 * tw for l, uv in zip((l0, l1, l2), tri["uv"]))
            v = sum(l * (uv[1] + 1) / 2 * th for l, uv in zip((l0, l1, l2), tri["uv"]))
            ui = np.clip(np.floor(u).astype(int), 0, tw - 1)
            vi = np.clip(np.floor(v).astype(int), 0, th - 1)
            shown[inside] = alpha[vi[inside], ui[inside]]
        return shown, px, py

    @staticmethod
    def seam_break(alpha: np.ndarray) -> float:
        """Mean alpha jump across the seam x = -70.419: both triangles sampled (bilinear) on the seam line itself.

        The left triangle reaches the seam at texture column ~124.8 and the right one at ~1.8, on different
        rows; a texture laid out in the wrap shows the same display point from both sides.
        """

        th, tw = alpha.shape

        def texel(tri, x, y):
            A = np.array([[p[0], p[1], 1.0] for p in tri["pos"]])
            B = np.array([[(u + 1) / 2 * tw, (v + 1) / 2 * th] for u, v in tri["uv"]])
            M = np.linalg.solve(A, B)
            return x * M[0, 0] + y * M[1, 0] + M[2, 0] - 0.5, x * M[0, 1] + y * M[1, 1] + M[2, 1] - 0.5

        def bilinear(u, v):
            x0 = np.clip(np.floor(u).astype(int), 0, tw - 1)
            y0 = np.clip(np.floor(v).astype(int), 0, th - 1)
            x1, y1 = np.clip(x0 + 1, 0, tw - 1), np.clip(y0 + 1, 0, th - 1)
            fx, fy = np.clip(u - x0, 0, 1), np.clip(v - y0, 0, 1)
            return (alpha[y0, x0] * (1 - fx) * (1 - fy) + alpha[y0, x1] * fx * (1 - fy)
                    + alpha[y1, x0] * (1 - fx) * fy + alpha[y1, x1] * fx * fy)

        ys = np.linspace(20.9, 43.9, 400)   # where both triangles meet the seam
        xs = np.full_like(ys, -70.419)
        left = bilinear(*texel(marks.SHIELD_ESPN_WRAP[0], xs, ys))
        right = bilinear(*texel(marks.SHIELD_ESPN_WRAP[1], xs, ys))
        assert left.mean() > 0.1, "the mark must cross the seam for this check to mean anything"
        return float(np.abs(left - right).mean())

    @unittest.skipUnless(marks.available(), "official marks pack absent")
    def test_the_shipped_art_reads_whole_through_the_retail_triangles(self) -> None:
        _w, _h, rgba = decode_rgba_png(marks.art_path("shield_espn.png").read_bytes(), (128, 64))
        alpha = np.frombuffer(rgba, np.uint8).reshape(64, 128, 4)[..., 3].astype(np.float64) / 255.0
        shown, px, py = self.reassemble(alpha)
        opaque = shown > 0.5
        xs, ys = px[opaque], py[opaque]
        # the mark sits inside the retail logo's display ellipse, centred on the seam
        self.assertTrue((((xs + 70.62) / 37.92) ** 2 + ((ys - 32.33) / 11.99) ** 2 <= 1.0).all())
        self.assertAlmostEqual(float((xs.min() + xs.max()) / 2), -70.62, delta=1.5)
        self.assertGreater(float(xs.max() - xs.min()), 50.0)
        self.assertLess(self.seam_break(alpha), 0.05)
        # a picture laid straight across the texture (shifted off its wrap) tears at the seam
        self.assertGreater(self.seam_break(np.roll(alpha, 24, axis=1)), 0.15)
        # 2026 red, one colour for every texel
        colours = {tuple(p) for p in np.frombuffer(rgba, np.uint8).reshape(-1, 4)[:, :3]}
        self.assertEqual(colours, {(191, 13, 19)})


class SyntheticImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="espn-marks-")
        cls.root = Path(cls.temp.name)
        install_for_class(cls, cls.root / "neutral-marks")
        cls.disc = SyntheticDisc(cls.root / "fixture")
        cls.pins = marks.record_pins(cls.disc.path, None, rows=cls.disc.rows)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def copy(self, name: str) -> Path:
        target = self.root / name
        shutil.copyfile(self.disc.path, target)
        return target

    def test_pins_from_the_synthetic_source(self) -> None:
        self.assertEqual(marks.image_status(self.disc.path, pins=self.pins), "retail")
        self.assertEqual(marks.image_status(self.disc.xiso.retail_packs, pins=self.pins), "retail")
        for mark in self.pins["marks"]:
            self.assertNotEqual(mark["applied_sha256"], mark["retail_sha256"])
            self.assertEqual(mark["png"], f"{mark['texture']}.png")

    def test_apply_writes_only_the_four_spans_and_reads_back(self) -> None:
        target = self.copy("apply.iso")
        before = target.read_bytes()
        receipt = marks.apply_to_image(target, pins=self.pins)
        after = target.read_bytes()
        self.assertEqual((receipt["state"], receipt["written"], receipt["already_applied"]), ("applied", 4, 0))
        self.assertEqual(len(after), len(before))
        spans = []
        for name in marks.MARKS:
            row = self.disc.rows[name]
            at = self.disc.xiso.virtual_to_image(self.disc.xiso.entry_offsets[346] + row["chunk_offset"])
            spans.append((at, at + row["span_size"]))
            new = after[at:at + row["span_size"]]
            self.assertEqual(new[:32], before[at:at + 32], name)          # wrapper and scratch word kept
            chunk = dataclasses.replace(txtr.parse_chunks(new, allow_trailing=True)[0], offset=0)
            decoded, _ = txtr.decode_chunk(new, chunk)
            rgba = txtr.texture_to_rgba(decoded, chunk, txtr.parse_texture(decoded, chunk))
            png = marks.art_path(f"{name}.png").read_bytes()
            self.assertEqual(rgba, decode_rgba_png(png, (row["width"], row["height"]))[2], name)
        changed = np.nonzero(np.frombuffer(before, np.uint8) != np.frombuffer(after, np.uint8))[0]
        self.assertTrue(all(any(a <= int(i) < b for a, b in spans) for i in changed))
        self.assertEqual(receipt["refused"], presentation.REFUSED)
        self.assertEqual((receipt["archive_growth"], receipt["gamedata_growth"], receipt["runtime_witnessed"]),
                         (0, 0, False))
        for row in receipt["marks"]:
            self.assertEqual(row["state_before"], "retail")
            self.assertTrue(row["written"] and row["wrapper_identical"])
            self.assertLessEqual(row["exact_minimum_scratch"], row["scratch_bytes"])
            self.assertEqual(row["filled_bytes"] + row["padding_bytes"], row["stored_size"])
        again = marks.apply_to_image(target, pins=self.pins)
        self.assertEqual((again["written"], again["already_applied"], again["changed_bytes"]), (0, 4, 0))
        self.assertEqual(target.read_bytes(), after)

    def test_mixed_and_foreign_states(self) -> None:
        target = self.copy("states.iso")
        marks.apply_to_image(target, pins=self.pins)
        row = self.disc.rows["espnLogo1"]
        at = self.disc.xiso.virtual_to_image(self.disc.xiso.entry_offsets[346] + row["chunk_offset"])
        with target.open("r+b") as stream:
            stream.seek(at)
            stream.write(self.disc.span_at(self.disc.xiso.image, "espnLogo1"))
        self.assertEqual(marks.image_status(target, pins=self.pins), "mixed")
        self.assertEqual(marks.mark_states(target, pins=self.pins)["espnLogo1"], "retail")
        self.assertEqual(marks.apply_to_image(target, pins=self.pins)["written"], 1)
        self.assertEqual(marks.image_status(target, pins=self.pins), "applied")
        with target.open("r+b") as stream:
            stream.seek(at + 100)
            byte = stream.read(1)
            stream.seek(at + 100)
            stream.write(bytes((byte[0] ^ 0xFF,)))
        corrupted = target.read_bytes()
        self.assertEqual(marks.image_status(target, pins=self.pins), "foreign")
        with self.assertRaisesRegex(marks.EspnMarksError, "neither retail nor"):
            marks.apply_to_image(target, pins=self.pins)
        self.assertEqual(target.read_bytes(), corrupted)
        other = dict(self.pins, outer=dict(self.pins["outer"], name_id=0x12345678))
        self.assertEqual(marks.image_status(self.disc.path, pins=other), "foreign")

    def test_exact_revert_from_a_retail_source(self) -> None:
        target = self.copy("revert.iso")
        marks.apply_to_image(target, pins=self.pins)
        receipt = marks.revert_image(target, self.disc.path, pins=self.pins)
        self.assertEqual((receipt["state"], receipt["restored"]), ("retail", 4))
        self.assertEqual(target.read_bytes(), self.disc.path.read_bytes())
        applied = self.copy("not-retail.iso")
        marks.apply_to_image(applied, pins=self.pins)
        with self.assertRaisesRegex(marks.EspnMarksError, "retail source is not retail"):
            marks.revert_image(target, applied, pins=self.pins)

    def test_a_grown_gamedata_reads_as_foreign(self) -> None:
        # growth that is not the sprite scorebug's own appended collection (b76 c1 accepts only that one; see
        # test_nfl2k5_espn_marks_sprite.py) leaves an outer that is not the pinned resource
        entries = [(0x1000 + i, bytes((i % 251,)) * 16) for i in range(346)]
        entries += [(presentation.OUTER_NAME_ID, self.disc.gamedata + bytes(4096)), (0x2000, b"tail" * 4)]
        need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
        grown = SyntheticXiso(self.root / "grown", entries, pack_sizes=(align_up(need) + ALIGNMENT,), pack_sectors=(64,))
        self.assertEqual(marks.image_status(grown.path, pins=self.pins), "foreign")
        with self.assertRaisesRegex(marks.EspnMarksError, "not the pinned USA resource"):
            marks.apply_to_image(grown.path, pins=self.pins)

    def test_the_real_pins_refuse_a_foreign_image(self) -> None:
        # the synthetic gamedata.iff has the retail name id but not the retail size or bytes
        self.assertEqual(marks.image_status(self.disc.path), "foreign")
        with self.assertRaisesRegex(marks.EspnMarksError, "not the pinned USA resource|art differs from the pinned art"):
            marks.apply_to_image(self.copy("foreign.iso"))


class BuildWiringTests(unittest.TestCase):
    def setUp(self):
        # This source has no PLAY archive; this test owns presentation wiring only.
        patcher = mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_plan_default_presets_availability_and_settings(self) -> None:
        plan = mod_build.BuildPlan("s", "t")
        self.assertIs(plan.espn_marks_2026, False)
        self.assertIn("espn_marks_2026", plan.to_recipe())
        for name, values in mod_build.PRESETS.items():
            self.assertIs(values["espn_marks_2026"], False, name)
            self.assertIs(mod_build.apply_preset(plan, name).espn_marks_2026, False, name)
        self.assertEqual(mod_build.availability()["espn_marks_2026"], marks.available())
        self.assertIn("espn_marks_2026", build_settings.FEATURE_KEYS)
        saved = build_settings.build_settings({"espn_marks_2026": True})
        self.assertIs(build_settings.to_plan(saved, "s", "t").espn_marks_2026, True)
        with self.assertRaisesRegex(ValueError, "espn_marks_2026 must be true or false"):
            build_settings.build_settings({"espn_marks_2026": "yes"})
        self.assertEqual((marks.DEFAULT_ENABLED, marks.BUILD_CAPTION, marks.LABEL),
                         (False, "ESPN presentation marks (2026)", "EXPERIMENTAL / UNWITNESSED"))

    def test_refusals_before_any_copy(self) -> None:
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="espn-marks-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaisesRegex(ValueError, r"need a disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), espn_marks_2026=True))
            with self.assertRaisesRegex(ValueError, "Hi-res scorebug family cannot be combined: both rewrite shield_espn"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), espn_marks_2026=True,
                                                    hires_pack=True, hires_families=("scorebug",)))
            with self.assertRaisesRegex(ValueError, "must be Off or On"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out3.xbe"), espn_marks_2026=1))
            # b76 c1: the sprite scorebug composes; a bare executable is refused for the disc image instead
            with self.assertRaisesRegex(ValueError, "disc image"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out4.xbe"), espn_marks_2026=True,
                                                    scorebug_runtime=True))
            self.assertEqual(mod_build.inspect(xbe)["espn_marks_2026"], "needs_image")
            self.assertFalse((root / "out.xbe").exists())

    def test_the_build_step_lands_in_the_receipt(self) -> None:
        from test_mod_build_performance import synthetic_disc
        calls = []

        def apply_to_image(target, *, progress=None, pins=None, sprite_folder=None, marks_pack=None):
            self.assertEqual(marks_pack, "chosen-pack")
            calls.append(Path(target))
            self.assertIsNone(sprite_folder)                     # no sprite scorebug in this build
            return {"state": "applied", "label": marks.LABEL, "marks": [], "written": 4, "refused": presentation.REFUSED}

        stand_in = types.SimpleNamespace(image_status=lambda source, sprite_folder=None: "retail",
                                         available=lambda *_: True, validate_art=lambda root: self.assertEqual(root, "chosen-pack"), apply_to_image=apply_to_image)
        real = mod_build._core_module
        with tempfile.TemporaryDirectory(prefix="espn-marks-build-") as raw:
            root = Path(raw)
            source = root / "retail.iso"
            synthetic_disc(source)
            original = source.read_bytes()
            with mock.patch.object(mod_build, "_core_module",
                                   side_effect=lambda name: stand_in if name == "nfl2k5_espn_marks" else real(name)):
                receipt = mod_build.build(mod_build.BuildPlan(str(source), str(root / "out.iso"), espn_marks_2026=True, official_marks_pack="chosen-pack"))
            self.assertEqual(len(calls), 1)
            step = [s for s in receipt["steps"] if s["step"] == "espn_marks_2026"]
            self.assertEqual(len(step), 1)
            self.assertEqual(step[0]["refused"], presentation.REFUSED)
            self.assertEqual(receipt["result"]["espn_marks_2026"], "applied")
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue((root / "out.iso").is_file())


@unittest.skipUnless(marks.available() and (PACKS / "0").is_file(), "extracted retail vc_53450030 packs absent; set NFL2K5_GAME_DIR")
class RetailPinsTests(unittest.TestCase):
    """The shipped pins against the real gamedata.iff, apply and revert on a synthetic disc that carries it."""

    def test_packs_read_as_retail_and_the_marks_apply_and_revert_exactly(self) -> None:
        from nfl_outer import parse_archive, read_entry_bytes
        self.assertEqual(marks.image_status(GAME), "retail")
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS)
        archive = parse_archive(PACKS / "0")
        gamedata = read_entry_bytes(archive, archive.entries[346])
        pins = marks._pins()
        self.assertEqual(len(gamedata), pins["outer"]["size"])
        with tempfile.TemporaryDirectory(prefix="espn-marks-retail-") as raw:
            root = Path(raw)
            entries = [(0x1000 + i, bytes((i % 251,)) * 16) for i in range(346)]
            entries += [(presentation.OUTER_NAME_ID, gamedata), (0x2000, b"tail" * 4)]
            need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
            fixture = SyntheticXiso(root / "disc", entries, pack_sizes=(align_up(need) + ALIGNMENT,),
                                    pack_sectors=(64,))
            target = root / "target.iso"
            shutil.copyfile(fixture.path, target)
            self.assertEqual(marks.image_status(target), "retail")
            receipt = marks.apply_to_image(target)
            self.assertEqual((receipt["state"], receipt["written"]), ("applied", 4))
            self.assertEqual([row["texture"] for row in receipt["marks"]], list(marks.MARKS))
            self.assertEqual(marks.image_status(target), "applied")
            self.assertEqual(marks.revert_image(target, fixture.path)["state"], "retail")
            self.assertEqual(target.read_bytes(), fixture.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
