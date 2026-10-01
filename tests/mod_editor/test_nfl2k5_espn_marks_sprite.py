"""ESPN presentation marks (2026) with the sprite scorebug (beta 76, job c1).

The rule: the sprite scorebug accepts gamedata.iff when every byte outside the four mark spans is retail and each
span holds its retail or applied pin; the marks accept a gamedata.iff grown only by the sprite's own appended
resources, which the sprite checks itself. Covered here: the rule on synthetic bytes, both build orders on a
synthetic disc, the inspector after a second pack-0 owner (u1 F4), the Build wiring, the composition on the retail
pack 0, and (opt in) the whole-disc matrix on the retail ISO with the Guardian overlay as the second pack-0 owner.

Synthetic cases carry no game data. Retail cases skip when their inputs are absent: NFL2K5_GAME_DIR names an extracted
game folder holding vc_53450030 (pack level, seconds); NFL2K5_C1_COMPOSITION=1 with NFL2K5_RETAIL_XISO (the retail
USA XISO) and NFL2K5_C1_SCRATCH (a folder with about 12 GB free: one disc copy at a time) runs the whole-disc matrix
(about 25 minutes).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
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

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_espn_marks as marks  # noqa: E402
from mod_editor.core import nfl2k5_presentation_standalone as presentation  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_ingame as scene  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_resources as art  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from nfl2k5_xiso_fixture import SECTOR, SyntheticXiso, dir_node  # noqa: E402
from nfl_outer import ALIGNMENT, HEADER_SIZE, align_up  # noqa: E402
from official_marks_fixture import install_for_class
from test_nfl2k5_espn_marks import SyntheticDisc  # noqa: E402

GAME = Path(os.environ.get("NFL2K5_GAME_DIR", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)")))
PACKS = GAME / "vc_53450030"
XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", str(ROOT / "ESPN NFL 2K5 (USA).xiso.iso")))
HEAVY = os.environ.get("NFL2K5_C1_COMPOSITION") == "1"
SCRATCH = Path(os.environ.get("NFL2K5_C1_SCRATCH", str(ROOT / ".scratch" / "c1-composition")))
TAIL = bytes((7 * i + 3) % 251 for i in range(4096))   # a synthetic appended "sprite" collection


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def outside_digest(hud: bytes, pins: dict) -> str:
    """SHA-256 of ``hud`` with the pinned mark spans cut out, in offset order (the rule's outside pin)."""

    digest, cursor = hashlib.sha256(), 0
    for mark in sorted(pins["marks"], key=lambda m: m["chunk_offset"]):
        digest.update(hud[cursor:mark["chunk_offset"]])
        cursor = mark["chunk_offset"] + mark["span_size"]
    digest.update(hud[cursor:])
    return digest.hexdigest()


def synthetic_hud(size: int = 0x10000):
    """A random HUD with four spans, their retail and applied bytes, and pins in the shipped shape."""

    rng = random.Random(76)
    hud = bytearray(rng.getrandbits(8) for _ in range(size))
    spans = ((0x1000, 0x200), (0x2400, 0x310), (0x8000, 0x180), (0xC000, 0x400))
    applied, rows = {}, []
    for texture, (at, n) in zip(marks.MARKS, spans):
        applied[texture] = bytes(rng.getrandbits(8) for _ in range(n))
        rows.append(dict(texture=texture, chunk_offset=at, span_size=n, retail_sha256=sha(bytes(hud[at:at + n])),
                         applied_sha256=sha(applied[texture])))
    pins = dict(schema=marks.PINS_SCHEMA, outer=dict(index=346, name_id=presentation.OUTER_NAME_ID, size=size),
                marks=rows)
    return bytes(hud), applied, pins


def with_marks(hud: bytes, pins: dict, applied: dict, textures) -> bytes:
    out = bytearray(hud)
    for mark in pins["marks"]:
        if mark["texture"] in textures:
            out[mark["chunk_offset"]:mark["chunk_offset"] + mark["span_size"]] = applied[mark["texture"]]
    return bytes(out)


def build_disc(folder: Path, gamedata: bytes) -> SyntheticXiso:
    """p1's synthetic archive shape (outer 346 is gamedata.iff) around any gamedata bytes."""

    entries = [(0x1000 + i, bytes((i % 251,)) * 16) for i in range(346)]
    entries += [(presentation.OUTER_NAME_ID, gamedata), (0x2000, b"tail" * 4)]
    need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
    return SyntheticXiso(folder, entries, pack_sizes=(align_up(need) + ALIGNMENT,), pack_sectors=(64,))


def outer_bytes(image: Path) -> bytes:
    with marks._outer_image()(image) as archive:
        entry = archive.entries[346]
        return archive.read(entry.virtual_offset, entry.size)


def changed_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Maximal [start, end) runs where two equal-length byte strings differ."""

    assert len(a) == len(b)
    out, start = [], None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y and start is None:
            start = i
        elif x == y and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(a)))
    return out


class HudRuleTests(unittest.TestCase):
    """nfl2k5_scorebug_sprite.hud_espn_marks on synthetic bytes, and the shipped pins it reads."""

    def setUp(self) -> None:
        self.hud, self.applied, self.pins = synthetic_hud()
        self.kw = dict(pins=self.pins, outside=outside_digest(self.hud, self.pins), before=sha(self.hud))

    def test_every_subset_of_applied_marks_is_the_supported_base(self) -> None:
        self.assertEqual(sprite.hud_espn_marks(self.hud, **self.kw), dict.fromkeys(marks.MARKS, "retail"))
        for mask in range(16):
            chosen = {t for i, t in enumerate(marks.MARKS) if mask >> i & 1}
            with self.subTest(applied=sorted(chosen)):
                states = sprite.hud_espn_marks(with_marks(self.hud, self.pins, self.applied, chosen), **self.kw)
                self.assertEqual(states, {t: "applied" if t in chosen else "retail" for t in marks.MARKS})

    def test_anything_else_is_foreign(self) -> None:
        full = with_marks(self.hud, self.pins, self.applied, marks.MARKS)
        for at in (0, 0x1000 - 1, 0x1200, 0x2400 + 0x310, 0xBFFF, len(full) - 1):     # outside every span
            bad = bytearray(full)
            bad[at] ^= 0x01
            self.assertIsNone(sprite.hud_espn_marks(bytes(bad), **self.kw), hex(at))
        for mark in self.pins["marks"]:                                               # a span at neither pin
            bad = bytearray(full)
            bad[mark["chunk_offset"] + 5] ^= 0x80
            self.assertIsNone(sprite.hud_espn_marks(bytes(bad), **self.kw), mark["texture"])
        self.assertIsNone(sprite.hud_espn_marks(full + b"\0", **self.kw))
        self.assertIsNone(sprite.hud_espn_marks(full[:-1], **self.kw))

    def test_without_valid_pins_only_the_byte_exact_retail_hud(self) -> None:
        full = with_marks(self.hud, self.pins, self.applied, marks.MARKS)
        broken = [dict(self.pins, schema="other"), dict(self.pins, marks=self.pins["marks"][:3]),
                  dict(self.pins, outer=dict(self.pins["outer"], name_id=1)),
                  dict(self.pins, marks=[dict(self.pins["marks"][0], chunk_offset=0x2400)] + self.pins["marks"][1:]),
                  dict(self.pins, marks=[dict(self.pins["marks"][0], applied_sha256="0" * 63)] + self.pins["marks"][1:]),
                  dict(self.pins, marks=[dict(self.pins["marks"][0], applied_sha256=self.pins["marks"][0]["retail_sha256"])]
                       + self.pins["marks"][1:])]
        for index, pins in enumerate(broken):
            with self.subTest(case=index):
                self.assertIsNone(sprite.espn_mark_spans(pins))
                kw = dict(self.kw, pins=pins)
                self.assertEqual(sprite.hud_espn_marks(self.hud, **kw), {})
                self.assertIsNone(sprite.hud_espn_marks(full, **kw))

    def test_the_shipped_pins_are_the_four_marks_inside_the_retail_hud(self) -> None:
        size, rows = sprite.espn_mark_spans()
        self.assertEqual(size, art.HUD_SIZE)
        document = json.loads(marks.PINS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(sprite.ESPN_MARKS_PINS, marks.PINS_PATH)
        self.assertEqual([r[0] for r in rows], list(marks.MARKS))                      # chunk order is offset order
        self.assertEqual(rows, tuple((m["texture"], m["chunk_offset"], m["span_size"], m["retail_sha256"],
                                      m["applied_sha256"]) for m in document["marks"]))
        inventory = presentation.rows_by_texture()
        for texture, at, n, retail, _applied in rows:
            self.assertEqual((at, n, retail), (inventory[texture]["chunk_offset"], inventory[texture]["span_size"],
                                               inventory[texture]["span_sha256"]))
            self.assertEqual(inventory[texture]["pack_offset"], art.HUD_START + at)    # inside the sprite's HUD
        # the sprite's own retail sources (score_bug, score_buga) never overlap a mark
        spans = [(art.HUD_START + at, art.HUD_START + at + n) for _t, at, n, _r, _a in rows]
        for name in ("score_bug", "score_buga"):
            record = art.RESOURCES[name]
            self.assertFalse(any(a < record["pack_offset"] + record["span_size"] and record["pack_offset"] < b
                                 for a, b in spans), name)


class SyntheticCompositionTests(unittest.TestCase):
    """Both build orders on p1's synthetic disc, with a stand-in for the sprite's own tail recognizer.

    The stand-in applies the real rule (hud_espn_marks) with the synthetic pins, then recognizes TAIL as the only
    appended collection; the real recognizer runs on the retail pack below.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory(prefix="espn-marks-sprite-")
        cls.root = Path(cls.temp.name)
        cls.disc = SyntheticDisc(cls.root / "fixture")
        install_for_class(cls, cls.root / "neutral-marks")
        cls.pins = marks.record_pins(cls.disc.path, None, rows=cls.disc.rows)
        cls.gamedata = cls.disc.gamedata
        cls.rule = dict(pins=cls.pins, outside=outside_digest(cls.gamedata, cls.pins), before=sha(cls.gamedata))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def setUp(self) -> None:
        self.folders = []
        size = len(self.gamedata)

        def gamedata_status(read, outer_size, folder=None, widescreen=None, watermark=None):
            self.folders.append(folder)
            if sprite.hud_espn_marks(read(size, 0), **self.rule) is None:
                return "foreign"
            if outer_size == size:
                return "retail"
            return "applied" if outer_size == size + len(TAIL) and read(len(TAIL), size) == TAIL else "foreign"

        patcher = mock.patch.object(sprite, "gamedata_status", side_effect=gamedata_status)
        self.status = patcher.start()
        self.addCleanup(patcher.stop)

    def disc_with(self, name: str, gamedata: bytes) -> Path:
        return build_disc(self.root / name, gamedata).path

    def copy(self, source: Path, name: str) -> Path:
        target = self.root / name
        shutil.copyfile(source, target)
        return target

    def test_sprite_then_marks(self) -> None:
        s = self.disc_with("s", self.gamedata + TAIL)
        self.assertEqual(marks.image_status(s, pins=self.pins), "retail")
        sm = self.copy(s, "sm.iso")
        receipt = marks.apply_to_image(sm, pins=self.pins, sprite_folder="layout-x")
        self.assertEqual((receipt["state"], receipt["written"], receipt["gamedata_appended"]),
                         ("applied", 4, "sprite scorebug"))
        self.assertIn("layout-x", self.folders)
        before, after = s.read_bytes(), sm.read_bytes()
        outer = outer_bytes(sm)
        self.assertEqual(outer[len(self.gamedata):], TAIL)                              # the sprite's tail is kept
        self.assertEqual(self.status(lambda n, at: outer[at:at + n], len(outer)), "applied")
        self.assertEqual(sprite.hud_espn_marks(outer[:len(self.gamedata)], **self.rule),
                         dict.fromkeys(marks.MARKS, "applied"))
        # only the four spans changed
        with marks._outer_image()(sm) as archive:
            base = archive.image_offset(archive.entries[346].virtual_offset)
        spans = [(base + m["chunk_offset"], base + m["chunk_offset"] + m["span_size"]) for m in self.pins["marks"]]
        self.assertTrue(all(any(a <= lo and hi <= b for a, b in spans) for lo, hi in changed_ranges(before, after)))
        # exact revert of the marks leaves the sprite-only image
        reverted = marks.revert_image(sm, self.disc.path, pins=self.pins)
        self.assertEqual((reverted["state"], reverted["restored"], reverted["gamedata_appended"]),
                         ("retail", 4, "sprite scorebug"))
        self.assertEqual(sm.read_bytes(), before)

    def test_marks_then_sprite_equals_sprite_then_marks(self) -> None:
        m = self.copy(self.disc.path, "m.iso")
        self.assertEqual(marks.apply_to_image(m, pins=self.pins)["gamedata_appended"], "none")
        ms = self.disc_with("ms", outer_bytes(m) + TAIL)                               # the sprite appends last
        self.assertEqual(marks.image_status(ms, pins=self.pins), "applied")
        sm = self.copy(self.disc_with("s2", self.gamedata + TAIL), "sm2.iso")
        marks.apply_to_image(sm, pins=self.pins)
        self.assertEqual(ms.read_bytes(), sm.read_bytes())
        # reverting the marks of either order gives the sprite-only image; of the marks alone, retail
        s = self.disc_with("s3", self.gamedata + TAIL)
        marks.revert_image(ms, self.disc.path, pins=self.pins)
        self.assertEqual(ms.read_bytes(), s.read_bytes())
        marks.revert_image(m, self.disc.path, pins=self.pins)
        self.assertEqual(m.read_bytes(), self.disc.path.read_bytes())

    def test_mixed_marks_with_the_sprite(self) -> None:
        m = self.copy(self.disc.path, "mixed-m.iso")
        marks.apply_to_image(m, pins=self.pins)
        applied = outer_bytes(m)
        mark = self.pins["marks"][1]
        at, n = mark["chunk_offset"], mark["span_size"]
        mixed = applied[:at] + self.gamedata[at:at + n] + applied[at + n:]
        disc = self.disc_with("mixed", mixed + TAIL)
        self.assertEqual(marks.image_status(disc, pins=self.pins), "mixed")
        self.assertEqual(marks.mark_states(disc, pins=self.pins)[mark["texture"]], "retail")
        self.assertEqual(marks.apply_to_image(disc, pins=self.pins)["written"], 1)
        self.assertEqual(marks.image_status(disc, pins=self.pins), "applied")

    def test_other_growth_and_foreign_bytes_still_read_foreign(self) -> None:
        other_tail = bytes(len(TAIL))
        cases = {
            "another tail": self.gamedata + other_tail,
            "a longer tail": self.gamedata + TAIL + bytes(16),
            "a changed byte outside the marks": self.gamedata[:40] + bytes((self.gamedata[40] ^ 1,))
                                               + self.gamedata[41:] + TAIL,
        }
        for name, gamedata in cases.items():
            with self.subTest(case=name):
                disc = self.disc_with(name.replace(" ", "-"), gamedata)
                before = disc.read_bytes()
                self.assertEqual(marks.image_status(disc, pins=self.pins), "foreign")
                with self.assertRaisesRegex(marks.EspnMarksError, "not the pinned USA resource"):
                    marks.apply_to_image(disc, pins=self.pins)
                self.assertEqual(disc.read_bytes(), before)
        # a retail source for the revert must be the retail size, never a sprite disc
        sm = self.copy(self.disc_with("s4", self.gamedata + TAIL), "sm4.iso")
        marks.apply_to_image(sm, pins=self.pins)
        with self.assertRaisesRegex(marks.EspnMarksError, "retail source's gamedata.iff is not the pinned"):
            marks.revert_image(sm, self.disc_with("s5", self.gamedata + TAIL), pins=self.pins)


def sixteen_pack_disc(folder: Path, outer3: bytes, gamedata: bytes, *, xbe_size: int) -> Path:
    """A synthetic XISO with the retail archive's shape where it matters to the inspector: packs 0..F, outer 3,
    outer 346 (gamedata.iff) and a default.xbe of a supported size. No game data."""

    entries = [(0x1000 + i, bytes((i % 251,)) * 16) for i in range(348)]
    entries[3] = (0x8EE9EEED, outer3)
    entries[346] = (presentation.OUTER_NAME_ID, gamedata)
    need = align_up(HEADER_SIZE + 12 * len(entries)) + sum(align_up(len(p)) for _n, p in entries)
    sizes = (align_up(need),) + (ALIGNMENT,) * 15
    sectors, at = [], 64
    for size in sizes:
        sectors.append(at)
        at += size // SECTOR + 1
    fixture = SyntheticXiso(folder, entries, pack_sizes=sizes, pack_sectors=tuple(sectors))
    image = bytearray(fixture.path.read_bytes())
    image += bytes(-len(image) % SECTOR)
    xbe_sector = len(image) // SECTOR
    # the fixture's root names a 16-byte default.xbe; point it at a supported-size extent after the packs
    subdir = dir_node([(sectors[i], sizes[i], 0x80, name) for i, name in enumerate(fixture.pack_names)])
    old_root = dir_node([(35, 16, 0x80, "default.xbe"), (34, len(subdir), 0x10, "vc_53450030")])
    new_root = dir_node([(xbe_sector, xbe_size, 0x80, "default.xbe"), (34, len(subdir), 0x10, "vc_53450030")])
    assert image[33 * SECTOR:33 * SECTOR + len(old_root)] == old_root and len(new_root) == len(old_root)
    image[33 * SECTOR:33 * SECTOR + len(new_root)] = new_root
    image += bytes(xbe_size)
    fixture.path.write_bytes(bytes(image))
    return fixture.path


class InspectorAfterSecondPackOwnerTests(unittest.TestCase):
    """u1 F4: runtime_image_status finds the sprite's outer 346 through the archive when pack 0 grew after it."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="sprite-inspector-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.gamedata = bytes(range(256)) * 64 + b"SPRITE-TAIL" * 50
        self.seen = []

        def gamedata_status(read, size, folder=None, widescreen=None, watermark=None):
            self.seen.append((read(size, 0), folder))
            return "applied" if read(size, 0) == self.gamedata else "foreign"

        for patcher in (mock.patch.object(sprite, "gamedata_status", side_effect=gamedata_status),
                        mock.patch("mod_editor.core.nfl2k5_scorebug_runtime.status", return_value="applied")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def disc(self, name: str, outer3: bytes, gamedata: bytes | None = None) -> Path:
        from mod_editor.core import nfl2k5_xbe_space as space
        return sixteen_pack_disc(self.root / name, outer3, self.gamedata if gamedata is None else gamedata,
                                 xbe_size=space.special.RETAIL_FILE_SIZE)

    def test_a_second_owner_growing_pack_0_keeps_the_sprite_applied(self) -> None:
        before = self.disc("before", b"helmets" * 100)
        after = self.disc("after", b"helmets" * 100 + bytes(88544))                   # the Guardian overlay's growth
        layout = str(sprite.DEFAULT_FOLDER)                                            # forwarded as given
        for path in (before, after):
            with self.subTest(disc=path.parent.name):
                self.assertEqual(scene.runtime_image_status(path, scorebug_folder=layout), "applied")
        with marks._outer_image()(before) as one, marks._outer_image()(after) as two:
            self.assertNotEqual(one.entries[346].virtual_offset, two.entries[346].virtual_offset)
        self.assertEqual(self.seen, [(self.gamedata, layout)] * 2)

    def test_the_outer_must_still_be_the_sprites(self) -> None:
        self.assertEqual(scene.runtime_image_status(self.disc("tampered", b"x" * 64, self.gamedata[:-1] + b"?")),
                         "foreign")
        with mock.patch("mod_editor.core.nfl2k5_scorebug_runtime.status", return_value="retail"):
            self.assertEqual(scene.runtime_image_status(self.disc("retail-xbe", b"x" * 64)), "foreign")
        self.assertEqual(len(self.seen), 1)                                             # no fallback without the XBE


class BuildWiringTests(unittest.TestCase):
    def setUp(self):
        # This source has no PLAY archive; this test owns presentation wiring only.
        patcher = mock.patch.object(mod_build, "_check_playbook_scoring", return_value={"synthetic": True})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_sprite_refusal_is_gone_and_the_hires_family_refusal_names_its_reason(self) -> None:
        from nfl2k5_throw_tuning_test import _build_synthetic_xbe
        with tempfile.TemporaryDirectory(prefix="espn-marks-sprite-plan-") as raw:
            root = Path(raw)
            xbe = root / "default.xbe"
            xbe.write_bytes(_build_synthetic_xbe())
            with self.assertRaises(ValueError) as caught:
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out.xbe"), espn_marks_2026=True,
                                                    scorebug_runtime=True))
            self.assertNotRegex(str(caught.exception), "sprite scorebug")
            self.assertRegex(str(caught.exception), "disc image")
            with self.assertRaisesRegex(ValueError, "Hi-res scorebug family cannot be combined: both rewrite "
                                                    "shield_espn, and the Hi-res scorebug re-lays GAMEDATA"):
                mod_build.build(mod_build.BuildPlan(str(xbe), str(root / "out2.xbe"), espn_marks_2026=True,
                                                    hires_pack=True, hires_families=("scorebug",)))
            self.assertFalse(any(root.glob("out*")))
        self.assertIn("Works with the sprite scorebug", marks.HELP_TEXT)

    def test_the_build_installs_the_sprite_then_the_marks_with_its_layout_folder(self) -> None:
        from test_mod_build_performance import synthetic_disc
        calls = []

        def apply_to_image(target, *, progress=None, pins=None, sprite_folder=None, marks_pack=None):
            calls.append(("marks", sprite_folder))
            return {"state": "applied", "label": marks.LABEL, "marks": [], "written": 4,
                    "gamedata_appended": "sprite scorebug", "refused": presentation.REFUSED}

        def image_status(source, *, pins=None, sprite_folder=None):
            calls.append(("status", sprite_folder))
            return "retail"

        def runtime_apply_in_place(target, **kwargs):
            calls.append(("sprite", kwargs["scorebug_folder"]))
            return {"status": "applied"}

        marks_stand_in = types.SimpleNamespace(image_status=image_status, available=lambda *_: True, validate_art=lambda *_: None,
                                               apply_to_image=apply_to_image)
        scene_stand_in = types.SimpleNamespace(runtime_apply_in_place=runtime_apply_in_place,
                                               runtime_image_status=lambda *a, **k: "applied")
        real = mod_build._core_module
        layout = str(sprite.DEFAULT_FOLDER)
        with tempfile.TemporaryDirectory(prefix="espn-marks-sprite-build-") as raw:
            root = Path(raw)
            source = root / "retail.iso"
            synthetic_disc(source)
            original = source.read_bytes()
            stand_ins = {"nfl2k5_espn_marks": marks_stand_in, "nfl2k5_scorebug_ingame": scene_stand_in}
            with mock.patch.object(mod_build, "_core_module", side_effect=lambda name: stand_ins.get(name) or real(name)):
                receipt = mod_build.build(mod_build.BuildPlan(str(source), str(root / "out.iso"), espn_marks_2026=True,
                                                              scorebug_runtime=True, scorebug=True,
                                                              scorebug_folder=layout))
            # preflight, the sprite, the composed-disc inspection (it reads with the shipped layout), the marks
            self.assertEqual(calls, [("status", layout), ("sprite", layout), ("status", None), ("marks", layout)])
            steps = [s["step"] for s in receipt["steps"]]
            self.assertLess(steps.index("scorebug_runtime"), steps.index("espn_marks_2026"))
            self.assertEqual(receipt["result"]["espn_marks_2026"], "applied")
            self.assertEqual(source.read_bytes(), original)


def _pack_with(pack, spans: dict[int, bytes]):
    """A pack view with ``spans`` ({pack offset: bytes}) laid over it."""

    parts, cursor = [], 0
    for at in sorted(spans):
        parts += [(pack, cursor, at - cursor), (spans[at], 0, len(spans[at]))]
        cursor = at + len(spans[at])
    parts.append((pack, cursor, len(pack) - cursor))
    return art.join_views(parts)


@unittest.skipUnless(marks.available() and (PACKS / "0").is_file(), "extracted retail vc_53450030 packs absent; set NFL2K5_GAME_DIR")
class RetailPackCompositionTests(unittest.TestCase):
    """The real rule, the real sprite compiler and the real marks compiler on the retail pack 0, in both orders."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.stream = (PACKS / "0").open("rb")
        cls.retail = art.PackView.from_fd(cls.stream.fileno(), 0, (PACKS / "0").stat().st_size)
        cls.pins = marks._pins()
        cls.applied = {}
        for mark in cls.pins["marks"]:
            at = art.HUD_START + mark["chunk_offset"]
            cls.applied[at] = marks.compile_mark_span(cls.retail[at:at + mark["span_size"]], mark)[0]
        cls.marked = _pack_with(cls.retail, cls.applied)
        cls.sprite_only, cls.sprite_receipt = art.compile_runtime_collection(cls.retail, probe="sprite")
        cls.marks_then_sprite, cls.ms_receipt = art.compile_runtime_collection(cls.marked, probe="sprite")
        cls.sprite_then_marks = _pack_with(cls.sprite_only, cls.applied)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.stream.close()

    @staticmethod
    def hud(pack) -> bytes:
        return pack[art.HUD_START:art.HUD_START + art.HUD_SIZE]

    def outer_status(self, pack, folder=None) -> str:
        """The outer-level check, reading outer 346 of a pack-0 view (its size from the pack's index)."""

        entry = HEADER_SIZE + art.HUD_OUTER_INDEX * 12
        size = struct.unpack("<I", pack[entry + 4:entry + 8])[0]
        return sprite.gamedata_status(lambda n, at: pack[art.HUD_START + at:art.HUD_START + at + n], size, folder)

    def test_the_outside_pin_is_the_retail_hud(self) -> None:
        hud = self.hud(self.retail)
        self.assertEqual(sha(hud), art.RUNTIME_PINS["hud_before"])
        self.assertEqual(outside_digest(hud, self.pins), sprite.HUD_OUTSIDE_ESPN_MARKS)
        self.assertEqual({sha(span) for span in self.applied.values()},
                         {m["applied_sha256"] for m in self.pins["marks"]})

    def test_states_in_both_orders(self) -> None:
        self.assertEqual(sprite.pack_status(self.retail), "retail")
        self.assertEqual(sprite.pack_status(self.marked), "retail")
        for name, pack in (("sprite only", self.sprite_only), ("marks then sprite", self.marks_then_sprite),
                           ("sprite then marks", self.sprite_then_marks)):
            with self.subTest(order=name):
                self.assertEqual(sprite.pack_status(pack), "applied")
                self.assertEqual(art.runtime_pack_status(pack, probe="sprite"), "applied")
                self.assertEqual(self.outer_status(pack), "applied")
                self.assertIs(art.compile_runtime_collection(pack, probe="sprite")[0], pack)   # already applied
        self.assertEqual(self.outer_status(self.retail), "retail")
        self.assertEqual(self.outer_status(self.marked), "retail")
        self.assertEqual(self.sprite_receipt["hud_espn_marks"], dict.fromkeys(marks.MARKS, "retail"))
        self.assertEqual(self.ms_receipt["hud_espn_marks"], dict.fromkeys(marks.MARKS, "applied"))
        self.assertEqual(sprite.hud_espn_marks(self.hud(self.marked)), dict.fromkeys(marks.MARKS, "applied"))

    def test_both_orders_give_the_same_pack_and_each_option_adds_only_its_own_bytes(self) -> None:
        self.assertEqual(art.pack_digest(self.marks_then_sprite), art.pack_digest(self.sprite_then_marks))
        end = art.HUD_START + art.HUD_SIZE
        growth = len(self.sprite_only) - len(self.retail)
        self.assertEqual(growth, sprite.probe_sizes()[2])
        # the sprite's collection does not depend on the marks
        self.assertEqual(self.sprite_only[end:end + growth], self.marks_then_sprite[end:end + growth])
        # exact inverse of the sprite at the pack level: normalize its index and drop its appended sectors; what is
        # left is the pack it was installed on, byte for byte (the marks-only pack, or retail)
        block = 8 * 1024 * 1024
        for with_sprite, without in ((self.sprite_then_marks, self.marked), (self.sprite_only, self.retail)):
            count = struct.unpack("<I", with_sprite[:4])[0]
            table = bytearray(with_sprite[:HEADER_SIZE + 12 * count])
            struct.pack_into("<I", table, 12, scene.PACK_SIZE // 2048)
            struct.pack_into("<I", table, HEADER_SIZE + art.HUD_OUTER_INDEX * 12 + 4, art.HUD_SIZE)
            for i in range(art.HUD_OUTER_INDEX + 1, count):
                at = HEADER_SIZE + i * 12 + 8
                struct.pack_into("<I", table, at, struct.unpack_from("<I", table, at)[0] - growth // 2048)
            self.assertEqual(bytes(table), without[:len(table)])
            # up to the end of gamedata.iff nothing moved; after its aligned end everything moved by the growth
            for start, stop, shift in ((len(table), end, 0), (align_up(end), len(without), growth)):
                for at in range(start, stop, block):
                    n = min(block, stop - at)
                    self.assertEqual(with_sprite[at + shift:at + shift + n], without[at:at + n], (start, at))
        # the marks add only their four spans to the sprite pack
        for at, span in self.applied.items():
            self.assertEqual(self.sprite_then_marks[at:at + len(span)], span)

    def test_foreign_bytes_still_refuse(self) -> None:
        def flip(pack, at):
            return _pack_with(pack, {at: bytes((pack[at:at + 1][0] ^ 1,))})

        first = self.pins["marks"][0]
        outside = art.HUD_START + first["chunk_offset"] - 1
        inside = art.HUD_START + first["chunk_offset"] + 40
        tail = art.HUD_START + art.HUD_SIZE + 17
        for name, at in (("outside the marks", outside), ("inside a mark", inside), ("the sprite's tail", tail)):
            with self.subTest(byte=name):
                bad = flip(self.sprite_then_marks, at)
                self.assertEqual(sprite.pack_status(bad), "foreign")
                self.assertEqual(self.outer_status(bad), "foreign")
        for at in (outside, inside):
            with self.assertRaisesRegex(ValueError, "Foreign or mixed"):
                art.compile_runtime_collection(flip(self.marked, at), probe="sprite")

    def test_the_outer_check_follows_the_layout_folder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sprite-layout-") as raw:
            folder = Path(raw) / "layout"
            shutil.copytree(sprite.DEFAULT_FOLDER, folder)
            spec = json.loads((folder / "layout.json").read_text(encoding="utf-8"))
            spec["fields"][0]["colour"] = "#FDFDFE" if spec["fields"][0]["colour"] != "#FDFDFE" else "#FDFDFD"
            (folder / "layout.json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8", newline="\n")
            custom, _ = art.compile_runtime_collection(self.marked, probe="sprite", sprite_folder=str(folder))
            self.assertEqual(self.outer_status(custom, str(folder)), "applied")
            self.assertEqual(self.outer_status(custom), "foreign")
            self.assertEqual(self.outer_status(self.marks_then_sprite, str(folder)), "foreign")


def _digest(image: Path, replace: dict[int, bytes] | None = None, block: int = 64 * 1024 * 1024) -> str:
    """SHA-256 of an image, with byte ranges ({image offset: bytes}) substituted while hashing (nothing is written).

    One image at a time: every comparison in the whole-disc matrix is a recorded digest, and "only these spans
    differ" is proved by substituting the other state's bytes at exactly those spans."""

    rows = sorted((replace or {}).items())
    digest = hashlib.sha256()
    with image.open("rb") as stream:
        at = 0
        while True:
            data = stream.read(block)
            if not data:
                break
            patched = None
            for offset, value in rows:
                lo, hi = max(offset, at), min(offset + len(value), at + len(data))
                if lo < hi:
                    patched = bytearray(data) if patched is None else patched
                    patched[lo - at:hi - at] = value[lo - offset:hi - offset]
            digest.update(data if patched is None else patched)
            at += len(data)
    return digest.hexdigest()


def _read(image: Path, spans) -> list[bytes]:
    with image.open("rb") as stream:
        out = []
        for lo, hi in spans:
            stream.seek(lo)
            out.append(stream.read(hi - lo))
        return out


def _mark_spans(image: Path) -> list[tuple[int, int]]:
    """Absolute image ranges of the four marks in the live gamedata.iff of ``image``."""

    with marks._outer_image()(image) as archive:
        entry = archive.entries[346]
        return [(archive.image_offset(entry.virtual_offset + m["chunk_offset"]),
                 archive.image_offset(entry.virtual_offset + m["chunk_offset"]) + m["span_size"])
                for m in marks._pins()["marks"]]


def _files(image: Path) -> dict[str, str]:
    """SHA-256 of every file in the image's XDVDFS directory (the disc as the console reads it)."""

    import nfl_uniform_color_xiso_direct_patch as xc
    out = {}
    with image.open("rb") as stream:
        entries, _ = xc.parse_xdvdfs(stream.fileno(), os.fstat(stream.fileno()).st_size)
        for name, entry in sorted(entries.items()):
            if entry.attributes & 0x10:
                continue
            digest = hashlib.sha256()
            stream.seek(entry.byte_offset)
            for at in range(0, entry.size, 64 * 1024 * 1024):
                digest.update(stream.read(min(64 * 1024 * 1024, entry.size - at)))
            out[name] = digest.hexdigest()
    return out


def _revert_sprite(target: Path, retail: Path) -> None:
    """The exact inverse of the sprite scorebug's disc transaction, for proof only.

    The product has no sprite revert (turning it off means rebuilding from the retail disc). The transaction appends
    the grown pack 0 and the grown executable after the image and switches their two directory nodes; nothing else
    inside the original extent changes. The inverse therefore writes the live pack 0 back to the retail pack 0 extent
    with the sprite's collection dropped and its index normalized (the check pack_status already performs), takes the
    two nodes, the executable and the 608-byte alignment fill after gamedata.iff from the retail source, and cuts the
    image to the retail length. Whatever else the live pack 0 carries (the ESPN marks) survives.
    """

    import nfl_uniform_color_xiso_direct_patch as xc
    from mod_editor.core import nfl2k5_depth_chart_storage as storage
    block = 8 * 1024 * 1024
    with retail.open("rb") as source, target.open("r+b") as stream:
        def reader(handle):
            def read(count, offset):
                handle.seek(offset)
                return handle.read(count)
            return read

        size = os.fstat(source.fileno()).st_size
        before, _ = xc.parse_xdvdfs(source.fileno(), size)
        after, _ = xc.parse_xdvdfs(stream.fileno(), os.fstat(stream.fileno()).st_size)
        old, new = before["vc_53450030/0"], after["vc_53450030/0"]
        growth = new.size - old.size
        assert growth == sprite.probe_sizes()[2] and new.byte_offset >= size, "not a sprite transaction"
        live = art.PackView(new.size, lambda count, at: reader(stream)(count, new.byte_offset + at))
        count = struct.unpack("<I", live[:4])[0]
        table = bytearray(live[:HEADER_SIZE + 12 * count])
        struct.pack_into("<I", table, 12, old.size // 2048)
        struct.pack_into("<I", table, HEADER_SIZE + art.HUD_OUTER_INDEX * 12 + 4, art.HUD_SIZE)
        for i in range(art.HUD_OUTER_INDEX + 1, count):
            at = HEADER_SIZE + i * 12 + 8
            struct.pack_into("<I", table, at, struct.unpack_from("<I", table, at)[0] - growth // 2048)
        end = art.HUD_START + art.HUD_SIZE
        pieces = [(bytes(table), None, 0), (None, len(table), end - len(table)),
                  (reader(source)(align_up(end) - end, old.byte_offset + end), None, 0),
                  (None, align_up(end) + growth, old.size - align_up(end))]
        cursor = old.byte_offset
        for data, at, n in pieces:
            chunks = [data] if data is not None else (live[at + i:at + i + min(block, n - i)] for i in range(0, n, block))
            for chunk in chunks:
                stream.seek(cursor)
                stream.write(chunk)
                cursor += len(chunk)
        assert cursor == old.byte_offset + old.size
        for path in ("vc_53450030/0", "default.xbe"):
            node, _sector, _length = storage.image_file_node(reader(source), before[path].base_offset, size, path)
            stream.seek(node)
            stream.write(reader(source)(8, node))
        xbe = before["default.xbe"]
        stream.seek(xbe.byte_offset)
        stream.write(reader(source)(xbe.size, xbe.byte_offset))
        stream.truncate(size)


@unittest.skipUnless(HEAVY and XISO.is_file() and (PACKS / "0").is_file(),
                     "set NFL2K5_C1_COMPOSITION=1, NFL2K5_RETAIL_XISO and NFL2K5_C1_SCRATCH for the whole-disc matrix")
class RetailDiscMatrixTests(unittest.TestCase):
    """Real ISO copies, one at a time: each copy walks through its states in place, every state is recorded as a
    SHA-256 (with spans substituted while hashing where the claim is "only these spans differ"), and the copy is
    deleted before the next is made. Covered: sprite (S), marks (M), both orders (SM, MS), exact reverts of each
    option alone and of both, and the Build with the sprite, the Guardian overlay and the marks. The marks revert is
    the product's (from the retail source); the sprite revert is _revert_sprite, a proof."""

    def test_whole_disc_matrix(self) -> None:
        import time
        from mod_editor.core import nfl2k5_guardian_resources as guardian
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.assertGreater(shutil.disk_usage(SCRATCH).free, 12 * 1024 ** 3, "the matrix needs about 12 GB free")
        work = Path(tempfile.mkdtemp(prefix="c1-matrix-", dir=SCRATCH))
        self.addCleanup(shutil.rmtree, work, True)
        started = time.monotonic()
        rec: dict = {}

        def fresh(name: str) -> Path:
            self.assertEqual(list(work.glob("*.iso")), [], "one image at a time")
            target = work / name
            shutil.copyfile(XISO, target)
            return target

        def states(image: Path) -> tuple[str, str]:
            return scene.runtime_image_status(image), marks.image_status(image)

        rec["retail"] = dict(size=XISO.stat().st_size, sha256=_digest(XISO))
        dead = _mark_spans(XISO)                     # the four spans where retail keeps pack 0
        retail_spans = _read(XISO, dead)

        # Disc A: sprite (S), then the marks (SM); revert the marks (exactly S), then the sprite (exactly retail)
        a = fresh("a.iso")
        receipt = scene.runtime_apply_in_place(a)
        self.assertEqual(receipt["resources"]["hud_espn_marks"], dict.fromkeys(marks.MARKS, "retail"))
        self.assertEqual(states(a), ("applied", "retail"))
        live = _mark_spans(a)                        # the same spans in the appended pack 0
        rec["S"] = dict(size=a.stat().st_size, growth=receipt["image_growth"], sha256=_digest(a), files=_files(a),
                        outer_346_sha256=sha(outer_bytes(a)))
        s_outer = outer_bytes(a)
        receipt = marks.apply_to_image(a)
        self.assertEqual((receipt["state"], receipt["written"], receipt["gamedata_appended"]),
                         ("applied", 4, "sprite scorebug"))
        self.assertEqual(states(a), ("applied", "applied"))
        applied_spans = _read(a, live)
        rec["SM"] = dict(sha256=_digest(a), files=_files(a))
        # SM is S everywhere outside the four live spans
        self.assertEqual(_digest(a, dict(zip((lo for lo, _ in live), retail_spans))), rec["S"]["sha256"])
        self.assertEqual(marks.revert_image(a, XISO)["gamedata_appended"], "sprite scorebug")
        self.assertEqual(states(a), ("applied", "retail"))
        self.assertEqual(_digest(a), rec["S"]["sha256"])                      # marks alone: exactly S
        _revert_sprite(a, XISO)
        self.assertEqual((a.stat().st_size, _digest(a)), (rec["retail"]["size"], rec["retail"]["sha256"]))
        a.unlink()

        # Disc B: marks (M), then the sprite (MS); revert the sprite (exactly M), then the marks (exactly retail)
        b = fresh("b.iso")
        self.assertEqual(marks.apply_to_image(b)["gamedata_appended"], "none")
        self.assertEqual(states(b), ("retail", "applied"))
        self.assertEqual(_read(b, dead), applied_spans)                       # the same 2026 bytes either way
        rec["M"] = dict(sha256=_digest(b))
        self.assertEqual(_digest(b, dict(zip((lo for lo, _ in dead), retail_spans))), rec["retail"]["sha256"])
        receipt = scene.runtime_apply_in_place(b)
        self.assertEqual(receipt["resources"]["hud_espn_marks"], dict.fromkeys(marks.MARKS, "applied"))
        self.assertEqual(states(b), ("applied", "applied"))
        self.assertEqual(_mark_spans(b), live)
        rec["MS"] = dict(sha256=_digest(b), files=_files(b))
        self.assertEqual(rec["MS"]["files"], rec["SM"]["files"])               # the same disc to the console
        # MS is SM everywhere outside the dead pre-sprite copy of the four spans
        self.assertEqual(_digest(b, dict(zip((lo for lo, _ in dead), retail_spans))), rec["SM"]["sha256"])
        _revert_sprite(b, XISO)
        self.assertEqual(_digest(b), rec["M"]["sha256"])                      # sprite alone: exactly M
        marks.revert_image(b, XISO)
        self.assertEqual(_digest(b), rec["retail"]["sha256"])                 # marks alone on M: exactly retail
        b.unlink()

        # Disc C: SM again; revert the sprite first (exactly M), then the marks (exactly retail)
        c = fresh("c.iso")
        scene.runtime_apply_in_place(c)
        marks.apply_to_image(c)
        self.assertEqual(_digest(c), rec["SM"]["sha256"])                     # deterministic
        _revert_sprite(c, XISO)
        self.assertEqual(_digest(c), rec["M"]["sha256"])
        self.assertEqual(states(c), ("retail", "applied"))
        marks.revert_image(c, XISO)
        self.assertEqual(_digest(c), rec["retail"]["sha256"])
        c.unlink()

        # Disc D: MS again; revert the marks first (S on every file; the dead copy keeps the 2026 spans), then the
        # sprite (exactly retail)
        d = fresh("d.iso")
        marks.apply_to_image(d)
        scene.runtime_apply_in_place(d)
        self.assertEqual(_digest(d), rec["MS"]["sha256"])                     # deterministic
        marks.revert_image(d, XISO)
        self.assertEqual(states(d), ("applied", "retail"))
        self.assertEqual(_files(d), rec["S"]["files"])
        self.assertEqual(_digest(d, dict(zip((lo for lo, _ in dead), retail_spans))), rec["S"]["sha256"])
        _revert_sprite(d, XISO)
        self.assertEqual(_digest(d), rec["retail"]["sha256"])
        d.unlink()
        rec["reverts_exact"] = ["SM-marks=S", "SM-marks-sprite=retail (S-sprite=retail)", "MS-sprite=M",
                                "M-marks=retail", "SM-sprite=M", "SM-sprite-marks=retail",
                                "MS-marks=S on every file (dead copy keeps the 2026 spans)", "MS-marks-sprite=retail"]
        rec["matrix_seconds"] = round(time.monotonic() - started)

        # The Build: the sprite, then the Guardian overlay (a second pack-0 owner), then the marks
        self.assertEqual(list(work.glob("*.iso")), [], "one image at a time")
        target = work / "g.iso"
        receipt = mod_build.build(mod_build.BuildPlan(str(XISO), str(target), scorebug_runtime=True,
                                                      guardian_overlay=True, espn_marks_2026=True))
        steps = [row["step"] for row in receipt["steps"]]
        self.assertLess(steps.index("scorebug_runtime"), steps.index("guardian_overlay"))
        self.assertLess(steps.index("guardian_overlay"), steps.index("espn_marks_2026"))
        mark_step = receipt["steps"][steps.index("espn_marks_2026")]
        self.assertEqual((mark_step["state"], mark_step["gamedata_appended"]), ("applied", "sprite scorebug"))
        sprite_step = receipt["steps"][steps.index("scorebug_runtime")]
        self.assertEqual(sprite_step["resources"]["hud_espn_marks"], dict.fromkeys(marks.MARKS, "retail"))
        self.assertEqual(receipt["result"]["scorebug_runtime_resources"], "applied")   # F4, after the Guardian
        self.assertEqual(states(target), ("applied", "applied"))
        self.assertEqual(guardian.image_status(target), "applied")
        with target.open("rb") as stream:
            import nfl_uniform_color_xiso_direct_patch as xc
            entries, _ = xc.parse_xdvdfs(stream.fileno(), os.fstat(stream.fileno()).st_size)
            pack = art.PackView.from_fd(stream.fileno(), entries["vc_53450030/0"].byte_offset,
                                        entries["vc_53450030/0"].size)
            self.assertEqual(art.runtime_pack_status(pack, probe="sprite"), "foreign")   # the pack-0 view alone
        outer = outer_bytes(target)
        self.assertEqual(sprite.hud_espn_marks(outer[:art.HUD_SIZE]), dict.fromkeys(marks.MARKS, "applied"))
        self.assertEqual(outer[art.HUD_SIZE:], s_outer[art.HUD_SIZE:])                  # the same sprite collection
        rec["G"] = dict(size=target.stat().st_size, sha256=_digest(target), steps=steps,
                        outer_346=len(outer), outer_346_sha256=sha(outer))
        # the marks revert on the three-way disc leaves the sprite and the Guardian overlay applied
        self.assertEqual(marks.revert_image(target, XISO)["gamedata_appended"], "sprite scorebug")
        self.assertEqual(states(target), ("applied", "retail"))
        self.assertEqual(guardian.image_status(target), "applied")
        self.assertEqual(outer_bytes(target), s_outer)
        target.unlink()
        rec["total_seconds"] = round(time.monotonic() - started)
        for row in rec.values():
            if isinstance(row, dict):
                row.pop("files", None)
        print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    unittest.main()
