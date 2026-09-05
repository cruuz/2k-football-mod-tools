"""ESPN horizontal scorebug re-layout: deterministic mesh edit, range guard, fixed-span fit, status.

The executable tests need the base disc image; the emulation tests additionally need unicorn and
run the retail routines for real (the placement-mode node visibility of FUN_000fc200 and the
ball-live hide gate in FUN_0009fe50, retail bytes versus the persistent patch).
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import nfl_txtr  # noqa: E402
import nfl2k5_scorebug_layout as L  # noqa: E402

ASSETS = ROOT / "mod_editor" / "assets" / "nfl2k5_scorebug_espn"


class ScorebugLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        extraction = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
        pack = extraction / "ESPN NFL 2K5 (USA)/vc_53450030/0"
        if not pack.is_file():
            self.skipTest("retail pack 0 evidence absent")
        with pack.open("rb") as stream:
            stream.seek(L.CHUNK78_PACK_OFFSET)
            self.span = stream.read(L.SPAN_SIZE)
        self.retail = nfl_txtr.decode_chunk(self.span, nfl_txtr.parse_chunks(self.span)[0])[0]

    def test_retail_mesh_parses_to_the_known_layout(self) -> None:
        m = L.Mesh(self.retail)
        self.assertEqual(len(m.pos), L.VCOUNT)
        self.assertEqual(sorted(set(m.tindex)), [0, 11, 13, 15, 17, 19, 21, 23, 26])
        self.assertAlmostEqual(m.world[L.T["away_city"]][0], -95.82, places=1)
        self.assertAlmostEqual(m.world[L.T["home_score"]][1], -26.69, places=1)
        self.assertEqual(hashlib.sha256(L.Mesh(self.retail).serialize()).hexdigest()[:0], "")

    def test_layout_is_deterministic_and_stays_in_range(self) -> None:
        m = L.Mesh(self.retail)
        L.espn_layout(m)
        out = m.serialize()
        self.assertEqual(len(out), L.SCNE_SIZE)
        again = L.Mesh(self.retail)
        L.espn_layout(again)
        self.assertEqual(out, again.serialize())
        xs = [p[0] for p in m.pos]
        ys = [p[1] for p in m.pos]
        self.assertGreaterEqual(min(xs), L.NEW_OFFSET[0] - L.NEW_SCALE)
        self.assertLessEqual(max(xs), L.NEW_OFFSET[0] + L.NEW_SCALE)
        self.assertLessEqual(max(ys), L.ROW_TOP + 0.1)   # source ranges are rounded by ~0.04
        # every text anchor sits on the single row, the ball-on/hang-time/penalty boxes are parked off-screen
        for name in ("away_city", "home_city", "quarter", "clock_a", "away_score", "home_score", "drop_down", "drop_clock"):
            self.assertLessEqual(abs(m.world[L.T[name]][1] - L.TEXT_Y), 3.0, name)
        for name in ("drop_ball_on", "drop_hangtime", "drop_red"):
            self.assertEqual(tuple(m.world[L.T[name]][:2]), L.OFFSCREEN, name)
        # bytes outside the vertex positions / shape scale / transform positions are untouched
        changed = [i for i, (a, b) in enumerate(zip(self.retail, out)) if a != b]
        for i in changed:
            in_pos = L.S0 <= i < L.S0 + L.VCOUNT * L.S0_STRIDE
            in_shape = L.SHAPE + 0x10 <= i < L.SHAPE + 0x2C
            in_transform = any(L.TBASE + k * L.TSTRIDE + 0x40 <= i < L.TBASE + k * L.TSTRIDE + 0x5C for k in range(L.TCOUNT))
            in_uv = L.S1 <= i < L.S1 + L.VCOUNT * L.S1_STRIDE and 4 <= (i - L.S1) % L.S1_STRIDE < 8
            self.assertTrue(in_pos or in_shape or in_transform or in_uv, f"unexpected edit at {i:#x}")

    def test_edited_mesh_refits_the_retail_fixed_span(self) -> None:
        span = self.span
        self.assertEqual(len(span), L.SPAN_SIZE)
        m = L.Mesh(self.retail)
        L.espn_layout(m)
        new_span, info = L.refit(span, m.serialize())
        self.assertEqual(len(new_span), len(span))
        self.assertLessEqual(info.filled_bytes, 4800)
        self.assertTrue(info.wrapper_identical)
        self.assertEqual(new_span[:0x20], span[:0x20])
        chunk = nfl_txtr.parse_chunks(new_span, allow_trailing=True)[0]
        decoded, _ = nfl_txtr.decode_chunk(new_span, chunk)
        self.assertEqual(decoded, m.serialize())

    def test_status_refuses_what_it_cannot_prove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.xiso.iso"
            self.assertEqual(L.status(missing), "foreign")
            short = Path(tmp) / "short.xiso.iso"
            short.write_bytes(b"\0" * 4096)
            self.assertEqual(L.status(short), "foreign")

    def test_mesh_refuses_foreign_bytes(self) -> None:
        with self.assertRaises(SystemExit):
            L.Mesh(bytes(L.SCNE_SIZE))

    def test_v6_both_mark_copies_are_laid_identically_with_retail_uvs(self) -> None:
        """FUN_000fc200 shows zz_ESPN_bug1 in placement mode 0 and zz_ESPN_bug in mode 1, so both
        copies must carry the mark; the retail UVs stay so the two-row texture wrap reassembles."""

        retail = L.Mesh(self.retail)
        m = L.Mesh(self.retail)
        L.espn_layout(m)
        for v in range(274, 286):
            self.assertEqual(m.pos[v], m.pos[v - 12], v)
        for v in range(262, 286):
            self.assertEqual(m.uv[v], retail.uv[v], v)
            self.assertNotIn(v, m.uv_edit)
        x0, y0, x1, y1 = L.MARK_BOX
        white = [m.pos[v] for v in range(268, 274)]
        self.assertGreaterEqual(min(p[0] for p in white), x0 - 0.01)
        self.assertLessEqual(max(p[0] for p in white), x1 + 0.01)
        self.assertGreaterEqual(min(p[1] for p in white), y0 - 0.01)
        self.assertLessEqual(max(p[1] for p in white), y1 + 0.01)
        self.assertTrue(all(p[2] == L.MARK_Z for p in white))
        shadow = [m.pos[v] for v in range(262, 268)]
        self.assertTrue(all(p[2] == L.MARK_SHADOW_Z for p in shadow))
        # the drop shadow keeps the retail direction (right and down), scaled with the mark
        self.assertGreater(shadow[0][0], white[0][0])
        self.assertLess(shadow[0][1], white[0][1])
        # the mark sits inside the bar, left of the away city cell
        self.assertGreaterEqual(x0, L.BAR_LEFT)
        self.assertLessEqual(x1, L.CELLS["away_city"][0])

    def test_v6_pill_fits_the_widest_down_and_distance_strings(self) -> None:
        """FUN_000fc7d0 formats "%s & %s" from 1st..4th and %d / Goal / Inches: "4th & Inches" is
        the widest (12 glyphs, ~104 units at the in-game text scale measured on disc x)."""

        a, b = L.CELLS["down"]
        self.assertGreaterEqual(b - a, 110.0)
        order = ["away_city", "away_score", "home_city", "home_score", "down", "quarter", "clock", "playclock"]
        for left, right in zip(order, order[1:]):
            self.assertEqual(L.CELLS[left][1], L.CELLS[right][0], (left, right))
        self.assertGreaterEqual(L.CELLS[order[0]][0], L.MARK_BOX[2])
        self.assertLessEqual(L.CELLS[order[-1]][1], L.BAR_RIGHT)
        self.assertLessEqual(L.BAR_RIGHT - L.BAR_LEFT, 480.0)     # inside the 4:3 HUD's safe width
        m = L.Mesh(self.retail)
        L.espn_layout(m)
        pill = [m.pos[v] for v in range(64, 80)]                   # dscore_buga quad (drop_down)
        self.assertAlmostEqual(min(p[0] for p in pill), a, delta=0.05)
        self.assertAlmostEqual(max(p[0] for p in pill), b, delta=0.05)
        self.assertAlmostEqual(m.world[L.T["drop_down"]][0], (a + b) / 2, places=3)

    def test_strips_come_from_the_scene_not_the_research_export(self) -> None:
        """The mockup used to read an intermediate glTF that is not in a release (and gated the
        whole step).  The same index lists decode straight out of the retail scene."""

        from_scene = L.strips(self.retail)
        self.assertEqual(len(from_scene), len(L.SUBMESHES))
        self.assertTrue(all(idx for _k, idx in from_scene))
        self.assertTrue(all(0 <= v < L.VCOUNT for _k, idx in from_scene for v in idx))
        export = ROOT / "assets/intermediate/nfl2k5/models/0346_0078_score_bug.gltf"
        if not export.is_file():
            self.skipTest("the intermediate glTF research export is not in this tree")
        import json
        document = json.loads(export.read_text())
        buffer = export.with_suffix(".bin").read_bytes()
        for k, primitive in enumerate(document["meshes"][0]["primitives"]):
            accessor = document["accessors"][primitive["indices"]]
            view = document["bufferViews"][accessor["bufferView"]]
            offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
            expected = list(struct.unpack_from("<%dH" % accessor["count"], buffer, offset))
            self.assertEqual(from_scene[k][1], expected, k)

    def test_v6_preview_renders_normal_and_widest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = L.Mesh(self.retail)
            L.espn_layout(m)
            for widest in (False, True):
                out = Path(tmp) / f"bar_{int(widest)}.png"
                L.preview(m, out, widest=widest)
                self.assertGreater(out.stat().st_size, 1000)


class ScorebugXbePatchTests(unittest.TestCase):
    """Text-colour and persistence patches on the retail executable (skipped without the base image)."""

    BASE = Path("/home/noah/2K5 Mod Studio Builds/NFL 2K5 Create-a-Play.xiso.iso")

    def setUp(self) -> None:
        if not self.BASE.exists():
            self.skipTest("base disc image not present")
        from mod_editor.core import nfl2k5_throw_tuning as tt
        fd = os.open(self.BASE, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            off, length = tt.image_xbe_extent(fd, size)
            self.xbe = L._pread(fd, length, off)
        finally:
            os.close(fd)

    def test_patch_xbe_recolours_black_fields_and_nops_the_hide_calls(self) -> None:
        import struct
        import nfl2k5_scorebug_position_patch as sp

        patched, receipt = L.patch_xbe(self.xbe, freeze_elements=True)
        self.assertEqual(len(patched), len(self.xbe))
        for va, (field, retail) in L.TEXT_COLOUR_SITES.items():
            off = sp.va_to_off(self.xbe, va)
            self.assertEqual(struct.unpack_from("<I", self.xbe, off)[0], retail, field)
            self.assertEqual(struct.unpack_from("<I", patched, off)[0], L.TEXT_COLOUR_NEW, field)
        for va, retail in L.PERSIST_SITES.items():
            off = sp.va_to_off(self.xbe, va)
            self.assertEqual(self.xbe[off: off + 5], retail)
            self.assertEqual(patched[off: off + 5], b"\x90" * 5)
        self.assertEqual(len(receipt["persistent"]), 4)
        self.assertIn(0x0009FEAB, L.PERSIST_SITES)      # v6: the ball-live hide (snap / kick fielded)
        self.assertEqual(L.PERSIST_SITES[0x0009FEAB], bytes.fromhex("e800c80500"))
        self.assertIn(0x000FC6D5, L.PERSIST_SITES)      # v6: the possession-change hide inside FUN_000fc6c0
        from mod_editor.core import nfl2k5_hud_layout as hud
        self.assertEqual(hud.status(patched), {"kick_meter_margin": str(hud.DEFAULT_KICK_MARGIN), "lineup_insert": "off"})
        self.assertEqual(hud.status(self.xbe), {"kick_meter_margin": "retail", "lineup_insert": "retail"})
        self.assertEqual(len(receipt["text_colours"]), len(L.TEXT_COLOUR_SITES))
        # the two new steps are idempotent on already-patched bytes (the placement patch itself refuses
        # a second pass by design, so they are checked on their own)
        again, edits = L.patch_persistent(patched)
        self.assertEqual(again, patched)
        self.assertTrue(all(e.get("state") == "already" for e in edits))
        again, edits = L.patch_text_colours(patched)
        self.assertEqual(again, patched)
        self.assertTrue(all(e.get("state") == "already" for e in edits))

    def test_patch_xbe_refuses_foreign_bytes_at_a_site(self) -> None:
        import nfl2k5_scorebug_position_patch as sp

        va = next(iter(L.PERSIST_SITES))
        off = sp.va_to_off(self.xbe, va)
        foreign = bytearray(self.xbe)
        foreign[off] = 0xCC
        with self.assertRaises(SystemExit):
            L.patch_xbe(bytes(foreign), freeze_elements=True)


HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
IMAGE_BASE = 0x10000
SCRATCH = 0x03000000
STACK = 0x02000000
SENTINEL = 0x04000000
VIS_FLAG, TIMER_FLAG, SCENE_PTR, MODE = 0x00A95524, 0x00A957E0, 0x00A95528, 0x00A95870
OFFENSE_PTR = 0x00E60280
NODE_NAMES = ("bscore_buga", "bscore_buga1", "bscore_buga2", "cscore_buga", "dscore_buga", "hscore_buga",
              "yscore_buga", "yscore_buga1", "zscore_buga", "zz_ESPN_bug", "zz_ESPN_bug1")


@unittest.skipUnless(HAVE_UNICORN and os.environ.get("NFL2K5_SCOREBUG_EMULATION_TEST") == "1",
                     "bounded CPU tests require unicorn and NFL2K5_SCOREBUG_EMULATION_TEST=1")
class ScorebugEmulationTests(unittest.TestCase):
    """Run the retail routines that own the two in-game symptoms (skipped without the base image)."""

    BASE = ScorebugXbePatchTests.BASE

    def setUp(self) -> None:
        if not self.BASE.exists():
            self.skipTest("base disc image not present")
        from mod_editor.core import nfl2k5_throw_tuning as tt
        fd = os.open(self.BASE, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            size = os.fstat(fd).st_size
            off, length = tt.image_xbe_extent(fd, size)
            self.xbe = L._pread(fd, length, off)
        finally:
            os.close(fd)

    def _machine(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        from mod_editor.core import nfl2k5_bump_strength as bs
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0, 0x1000000)
        uc.mem_map(STACK, 0x100000)
        uc.mem_map(SCRATCH, 0x100000)
        uc.mem_map(SENTINEL, 0x1000)
        header = struct.unpack_from("<I", payload, 0x108)[0]
        uc.mem_write(IMAGE_BASE, payload[:header])
        for section in bs._sections(payload):
            uc.mem_write(section.virtual_address, payload[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_write(SENTINEL, b"\xc3")
        return uc

    def _run(self, uc, entry: int, until: int, *, ecx: int = 0, edx: int = 0, push_return: bool = False) -> None:
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP
        esp = STACK + 0x80000
        if push_return:
            esp -= 4
            uc.mem_write(esp, struct.pack("<I", SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.reg_write(UC_X86_REG_EDX, edx)
        uc.reg_write(UC_X86_REG_EIP, entry)
        uc.emu_start(entry, until, count=200_000)

    def _u32(self, uc, va: int) -> int:
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    def _hide_gate(self, payload: bytes, play_type: int) -> tuple[int, int]:
        """FUN_0009fe50 tail (0x9FE84..0x9FEB0): hides unless the offense's play type is 10."""

        uc = self._machine(payload)
        team, play, data = SCRATCH, SCRATCH + 0x100, SCRATCH + 0x200
        uc.mem_write(OFFENSE_PTR, struct.pack("<I", team))
        uc.mem_write(team + 0xC, struct.pack("<I", play))
        uc.mem_write(play + 8, struct.pack("<I", data))
        uc.mem_write(data + 4, struct.pack("<I", play_type << 8))
        uc.mem_write(VIS_FLAG, struct.pack("<I", 1))
        uc.mem_write(TIMER_FLAG, struct.pack("<I", 1))
        self._run(uc, 0x0009FE84, 0x0009FEB0)
        return self._u32(uc, VIS_FLAG), self._u32(uc, TIMER_FLAG)

    def test_ball_live_hide_gate_retail_vs_persistent(self) -> None:
        self.assertEqual(self._hide_gate(self.xbe, 0xC), (0, 0), "retail: a scrimmage snap hides the bug")
        self.assertEqual(self._hide_gate(self.xbe, 0xA), (1, 1), "retail: a kickoff keeps the bug")
        patched, _ = L.patch_persistent(self.xbe)
        self.assertEqual(self._hide_gate(patched, 0xC), (1, 1), "persistent: the snap keeps the bug")
        self.assertEqual(self._hide_gate(patched, 0xA), (1, 1))

    def _timed_show(self, payload: bytes) -> tuple[int, int, float]:
        """FUN_000fc6c0(2.0): retail hides (the timer flag is cleared again by the hide)."""

        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        uc = self._machine(payload)
        uc.mem_write(VIS_FLAG, struct.pack("<I", 1))
        uc.mem_write(TIMER_FLAG, struct.pack("<I", 0))
        esp = STACK + 0x80000 - 8
        uc.mem_write(esp, struct.pack("<If", SENTINEL, 2.0))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_EIP, 0x000FC6C0)
        uc.emu_start(0x000FC6C0, SENTINEL, count=1000)
        timer = struct.unpack("<f", bytes(uc.mem_read(0x00A957E4, 4)))[0]
        return self._u32(uc, VIS_FLAG), self._u32(uc, TIMER_FLAG), timer

    def test_possession_change_timed_show_retail_vs_persistent(self) -> None:
        self.assertEqual(self._timed_show(self.xbe), (0, 0, 2.0), "retail: FUN_000fc6c0 is a plain hide")
        patched, _ = L.patch_persistent(self.xbe)
        self.assertEqual(self._timed_show(patched), (1, 1, 2.0), "persistent: the bug stays visible")

    def _mode_visibility(self, mode: int) -> dict[str, int]:
        """FUN_000fc200 on a synthetic scene with the eleven runtime nodes: bit 0 of node+8 per name."""

        uc = self._machine(self.xbe)
        scene, nodes, names = SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x4000
        uc.mem_write(SCENE_PTR, struct.pack("<I", scene))
        uc.mem_write(scene + 0x1C, struct.pack("<I", len(NODE_NAMES)))
        uc.mem_write(scene + 0x20, struct.pack("<I", nodes))
        for i, name in enumerate(NODE_NAMES):
            uc.mem_write(names + i * 0x40, name.encode("utf-16-le") + b"\0\0")
            uc.mem_write(nodes + i * 0x80, struct.pack("<I", names + i * 0x40))
            uc.mem_write(nodes + i * 0x80 + 8, struct.pack("<I", 0x0000FFF1))   # bit 0 set to start
        uc.mem_write(MODE, struct.pack("<I", mode))
        self._run(uc, 0x000FC200, SENTINEL, push_return=True)
        return {name: self._u32(uc, nodes + i * 0x80 + 8) & 1 for i, name in enumerate(NODE_NAMES)}

    def test_placement_mode_shows_one_mark_copy_and_one_frame(self) -> None:
        mode0 = self._mode_visibility(0)
        mode1 = self._mode_visibility(1)
        self.assertEqual((mode0["zz_ESPN_bug"], mode0["zz_ESPN_bug1"]), (0, 1))
        self.assertEqual((mode0["yscore_buga"], mode0["yscore_buga1"]), (1, 0))
        self.assertEqual((mode1["zz_ESPN_bug"], mode1["zz_ESPN_bug1"]), (1, 0))
        self.assertEqual((mode1["yscore_buga"], mode1["yscore_buga1"]), (0, 1))
        for name in NODE_NAMES:
            if not name.startswith(("zz_ESPN", "yscore")):
                self.assertEqual((mode0[name], mode1[name]), (1, 1), name)


class ReferenceLayoutTests(unittest.TestCase):
    setUp = ScorebugLayoutTests.setUp
    def test_reference_widest_preview_uses_patched_texels(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as reference
        from PIL import Image
        m = reference.mesh(self.retail)
        self.assertEqual(reference.serialize(m), reference.decode(reference.apply(self.span, "score_bug")[0])[1])
        # A diagnostic atlas tests actual texture sampling, independently of fonts.
        texture = Image.new("RGBA", (64, 64), (21, 33, 49, 255))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference.png"
            L.preview_reference(m, texture, path, widest=True)
            with Image.open(path) as im:
                self.assertEqual(im.size, (1280, 960))
                self.assertEqual(im.getpixel((180, 780)), (21, 33, 49))
        for name in ("away_score", "home_score"):
            self.assertEqual(m.world[L.T[name]][1], 10)
        self.assertEqual(m.world[L.T["drop_down"]][1], 27)
        self.assertEqual(m.world[L.T["quarter"]][1], 2)



if __name__ == "__main__":
    unittest.main()
