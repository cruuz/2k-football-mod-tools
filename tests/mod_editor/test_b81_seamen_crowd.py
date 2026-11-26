"""b81-seamen: the classic Seamen's own crowd.

The owner (2026-11-25, playing the 11/20 private disc): "fans also wearing dolphins gear".

Root cause (PROVED OFFLINE by static reading of the USA executable): every crowd loader formats its file name from the
team's art code (+0x10C); the Seamen carry the Dolphins' "14", so the stands (14{h,a}{d,r}{n,s}.iff) and the cutaway
sets (cgfair14, cgfoul14, ns14, tg14) were the Dolphins'. No crowd set on the disc is neutral. nfl2k5_classic_crowd adds
fourteen "SM" files drawn from the user's own Dolphins files in the Seamen's colours with no mark (review S1: + the
cheerleaders ch and the tunnel's inflatable helmet ih; review M1: the 's' stand packages, loaded at ESPN Stadium, the
Seamen's home, carry the classic field's own end zones), and six helpers that load them for identity 230 at the six
sites. Unicorn runs the helpers; the files are composed from the retail disc. Not a played game.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]
from mod_editor.core import nfl2k5_classic_crowd as crowd  # noqa: E402
from mod_editor.core import nfl2k5_classic_teams as ct  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import XBE  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CV2 = importlib.util.find_spec("cv2") is not None
RETAIL = XBE.parent


def _sat(rgba):
    rgb = rgba[..., :3].astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    return np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)


def _warm(rgba):
    """Visible orange-red texels (hue 0..36 or 350..360, saturation >= 0.6, value >= 0.2)."""
    rgb = rgba[..., :3].astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    chroma = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.where((chroma > 1e-9) & (mx == r), (60 * (g - b) / np.maximum(chroma, 1e-9)) % 360, 180.0)
    sat = np.where(mx > 0, chroma / np.maximum(mx, 1e-9), 0)
    return int((((hue <= 36) | (hue >= 350)) & (sat >= 0.6) & (mx >= 0.2) & (rgba[..., 3] > 0)).sum())


def _hues(rgba):
    rgb = rgba[..., :3].astype(np.float64) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    chroma = mx - mn
    sat = np.where(mx > 0, chroma / np.maximum(mx, 1e-9), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.zeros_like(mx)
    nz = chroma > 1e-9
    hr = nz & (mx == r); hg = nz & (mx == g) & ~hr; hb = nz & ~hr & ~hg  # noqa: E702
    hue[hr] = (60 * ((g - b)[hr] / chroma[hr])) % 360
    hue[hg] = 60 * ((b - r)[hg] / chroma[hg]) + 120
    hue[hb] = 60 * ((r - g)[hb] / chroma[hb]) + 240
    visible = rgba[..., 3] > 0
    aqua = visible & (hue >= 182) & (hue <= 200) & (sat >= 0.5) & (mx >= 0.4)      # the Dolphins' aqua, not the teal
    orange = visible & (hue >= 12) & (hue <= 36) & (sat >= 0.72) & (mx >= 0.55)
    return int(aqua.sum()), int(orange.sum())


class DesignTests(unittest.TestCase):
    def test_the_redirect_names_the_seamen_and_their_files(self):
        self.assertEqual(crowd.IDENTITY, ct.own_name_identity())
        self.assertEqual(len(crowd.FILES), 14)
        self.assertEqual({src for _n, src in crowd.FILES},
                         {f"14{s}{w}{e}.iff" for s in "ha" for w in "dr" for e in "ns"}
                         | {"cgfair14.iff", "cgfoul14.iff", "ns14.iff", "tg14.iff", "ch14.iff", "ih14.iff"})
        self.assertEqual([n for n, _v, _r in crowd.SITES], ["cutaway_set", "cutaway_cg", "stands_away", "stands_home",
                                                             "helmet_home", "helmet_away"])
        self.assertTrue(all(n.replace("SM", "14") == src for n, src in crowd.FILES))
        code, labels = crowd.code_for(0x1600000)
        self.assertEqual(len(code), crowd.CODE_SIZE)
        self.assertEqual(code[:6], "SM".encode("utf-16le") + b"\0\0")
        self.assertLessEqual(len(code.rstrip(b"\xcc")), 256)
        for name, va, retail in crowd.SITES:
            hook = crowd.site_bytes(name, labels)
            self.assertEqual((len(hook), hook[0]), (len(retail), 0xE8))
            self.assertEqual(struct.unpack_from("<i", hook, 1)[0] + va + 5, labels[name])

    def test_the_owner_has_one_fixed_page_and_moves_no_other_owner(self):
        # 11/25: a code owner in the late order moved v3 addresses and a read-only owner after the classic block pushed
        # v3 sets into the pool (test_nfl2k5_allocator_pool); a fixed page (claimed in the coordinator's page register,
        # like the helmet sides and awards pages) is outside the shared unions and never advances the pool cursor.
        from unittest.mock import patch
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from tests import nfl2k5_allocator_stack as stack
        self.assertEqual(crowd.REQUESTS, (space.CLASSIC_CROWD_REQUEST,))
        self.assertEqual(space.CLASSIC_CROWD_REQUEST, (crowd.OWNER, "code", space.PAGE, space.PAGE))
        self.assertEqual(space.CLASSIC_CROWD_VA, 0x1532000)
        self.assertIn(crowd.OWNER, space.LATE_OWNERS)
        self.assertIn(crowd.OWNER, space.FIXED_PAGE_OWNERS)
        self.assertEqual(space.dormant_union()[-1], crowd.REQUESTS[0])
        self.assertNotIn(crowd.REQUESTS[0], stack.REQUESTS)
        self.assertNotIn(crowd.REQUESTS[0], tt._selected_space_requests(classic_teams=True))

        def rows(layout):
            return {(a["owner"], a["kind"], a["va"], a["raw"], a["size"]) for a in layout["allocations"]
                    if a["owner"] != space.DIRECTORY_OWNER}
        full = space.plan(stack.REQUESTS)
        with_crowd = space.plan(stack.REQUESTS + crowd.REQUESTS)
        self.assertLessEqual(rows(full), rows(with_crowd))                     # every owner keeps its row
        page = [a for a in with_crowd["allocations"] if a["owner"] == crowd.OWNER]
        self.assertEqual([(a["va"], a["raw"], a["size"]) for a in page],
                         [(0x1532000, space.POOL_RAW + 0x1532000 - space.POOL_VA, space.PAGE)])
        # a pool owner that would cover the page steps past it, with or without the crowd requested
        probe = ("nfl2k5_xs1_probe_code", "code", 0x30000, 16)
        with patch.object(space, "LATE_OWNERS", space.LATE_OWNERS + (probe[0],)):
            for extra in ((), crowd.REQUESTS):
                layout = space.plan(stack.REQUESTS + extra + (probe,))
                a = next(a for a in layout["allocations"] if a["owner"] == probe[0])
                self.assertFalse(a["va"] < 0x1533000 and a["va"] + a["size"] > 0x1532000, extra)

    def test_the_build_setting_and_the_memory_budget(self):
        # its own setting (on in the experimental preset with the classic teams), so the v0.9 pack plan the memory model
        # is anchored on does not carry it; with it on, the resident pool reaches the end of its fixed page
        from mod_editor.core import mod_build as mb_build
        from mod_editor.core import nfl2k5_build_settings as settings
        from mod_editor.core import nfl2k5_memory_budget as mb
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertIn("classic_crowd", settings.FEATURE_KEYS)
        self.assertIn("classic_crowd", mb_build.OPTIONAL_STEPS)
        for name, preset in mb_build.PRESETS.items():
            self.assertEqual(preset["classic_crowd"], name == "softdrink_experimental", name)
            self.assertLessEqual(preset["classic_crowd"], preset["classic_teams"], name)
        self.assertEqual(mb.LEGACY_REQUESTS["classic_crowd"], tuple(r[1:] for r in crowd.REQUESTS))
        self.assertEqual(mb.OWNER_BYTES["classic_crowd"], (crowd.CODE_SIZE, 0, 0, 0, 0))
        self.assertNotIn("classic_crowd", mb.owners(mb.rc_plan()))
        rc = mb.rc_plan()
        with_crowd = dict(rc, classic_crowd=True)
        self.assertIn("classic_crowd", mb.owners(with_crowd))
        base, more = mb.xbe_resident(rc, 128), mb.xbe_resident(with_crowd, 128)
        end = space.CLASSIC_CROWD_VA + space.CLASSIC_CROWD_SIZE - space.POOL_VA
        self.assertGreater(more, base)
        self.assertLessEqual(more - base, end)

    def test_recolour_moves_the_dolphins_colours_and_keeps_skin_lips_and_neutrals(self):
        swatch = np.array([[[0, 142, 151, 255], [244, 88, 31, 255], [255, 255, 255, 255], [200, 40, 50, 255],
                            [224, 172, 130, 255], [120, 70, 40, 255], [128, 128, 128, 255], [0, 46, 105, 255]]], np.uint8)
        out = crowd.recolour(swatch)[0]
        self.assertEqual(tuple(out[0, :3]), crowd.TEAL)                  # aqua at full light -> the teal
        self.assertLess(int(out[1, :3].max()), 50)                       # orange -> black
        for k in (2, 3, 4, 5, 6):                                        # white, red lips, skin, brown hair, grey
            self.assertEqual(tuple(out[k]), tuple(swatch[0, k]), k)
        self.assertLess(int(out[7, :3].max()), 60)                       # navy -> black
        self.assertTrue((out[:, 3] == swatch[0, :, 3]).all())

    @unittest.skipUnless(HAVE_CV2, "OpenCV draws the pictures")
    def test_the_pictures_are_what_the_authoring_tool_draws(self):
        spec = importlib.util.spec_from_file_location("ss2_crowd", ROOT / "tools/b77/ss2_crowd.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(tool.main(["--check"]), 0)

    def test_the_pictures_carry_no_dolphins_colour(self):
        from PIL import Image
        for name in crowd.PICTURES:
            with Image.open(crowd.ART_DIR / f"{name}.png") as image:
                aqua, orange = _hues(np.asarray(image.convert("RGBA")))
            self.assertEqual((aqua, orange), (0, 0), name)


@unittest.skipUnless(HAVE_UC, "Unicorn required")
class HelperTests(unittest.TestCase):
    """The four helpers run under Unicorn on a synthetic page: a team record, the two match contexts and the formats."""
    VA = 0x00800000
    TEAM = 0x00900000

    def machine(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        for base in (0x00800000, 0x00900000, 0x00B30000, 0x00A00000):
            uc.mem_map(base, 0x10000)
        code, labels = crowd.code_for(self.VA)
        uc.mem_write(self.VA, code)
        uc.mem_write(0x00A00000, b"\xf4")       # hlt: the return address
        return uc, labels

    def call(self, uc, va, **regs):
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX
        names = dict(eax=UC_X86_REG_EAX, ebx=UC_X86_REG_EBX, ecx=UC_X86_REG_ECX, edx=UC_X86_REG_EDX)
        for k, v in regs.items():
            uc.reg_write(names[k], v)
        sp = 0x00A0F000
        uc.mem_write(sp, struct.pack("<I", 0x00A00000))
        uc.reg_write(UC_X86_REG_ESP, sp)
        uc.emu_start(va, 0x00A00000, count=64)
        return {k: uc.reg_read(r) for k, r in names.items()}, uc.reg_read(UC_X86_REG_ESP)

    def test_cutaway_sets_move_only_ns_tg_ch_ih_and_cg_for_identity_230(self):
        uc, labels = self.machine()
        uc.mem_write(0x00908000, struct.pack("<I", self.TEAM))          # [ebx] = the team record
        uc.mem_write(self.TEAM + 0x10C, struct.pack("<I", 0x00920000))  # its art code text pointer
        for identity, moved in ((230, True), (14, False), (229, False), (231, False)):
            uc.mem_write(self.TEAM + 0x118, struct.pack("<H", identity))
            for fmt, want in ((crowd.FORMAT_NS, moved), (crowd.FORMAT_TG, moved), (crowd.FORMAT_CH, moved),
                              (crowd.FORMAT_IH, moved), (0x00E7AAAA, False), (crowd.FORMAT_CG, False),
                              (crowd.FORMAT_IH_TUNNEL, False)):
                out, sp = self.call(uc, labels["cutaway_set"], ebx=0x00908000, ecx=fmt)
                self.assertEqual(out["eax"], self.VA if want else 0x00920000, (identity, hex(fmt)))
                self.assertEqual((out["edx"], out["ecx"], out["ebx"], sp), (self.TEAM, fmt, 0x00908000, 0x00A0F004))
            for fmt, want in ((crowd.FORMAT_CG, moved), (crowd.FORMAT_NS, False)):
                out, sp = self.call(uc, labels["cutaway_cg"], ebx=0x00908000, ecx=fmt)
                self.assertEqual(out["edx"], self.VA if want else 0x00920000, (identity, hex(fmt)))
                self.assertEqual((out["eax"], out["ecx"], sp), (self.TEAM, fmt, 0x00A0F004))

    def test_the_tunnel_helmets_follow_each_match_context(self):
        # 0x1257DD (after call 0x61C50, the home context) loads EDX, 0x1257FF (after 0x61C60, away) loads ECX
        uc, labels = self.machine()
        ctx = 0x00908000
        uc.mem_write(ctx + 0x10C, struct.pack("<I", 0x00950000))
        for identity in (230, 14, 229, 0):
            uc.mem_write(ctx + 0x118, struct.pack("<H", identity))
            want = self.VA if identity == 230 else 0x00950000
            out, sp = self.call(uc, labels["helmet_home"], eax=ctx, ecx=0x1234, ebx=0x4321)
            self.assertEqual((out["edx"], out["eax"], out["ecx"], out["ebx"], sp), (want, ctx, 0x1234, 0x4321, 0x00A0F004))
            out, sp = self.call(uc, labels["helmet_away"], eax=ctx, edx=0x5678, ebx=0x4321)
            self.assertEqual((out["ecx"], out["eax"], out["edx"], out["ebx"], sp), (want, ctx, 0x5678, 0x4321, 0x00A0F004))

    def test_stands_follow_each_match_context(self):
        uc, labels = self.machine()
        uc.mem_write(crowd.AWAY_CODE, struct.pack("<I", 0x00930000))
        uc.mem_write(crowd.HOME_CODE, struct.pack("<I", 0x00940000))
        for home, away in ((230, 14), (14, 230), (230, 230), (0, 0)):
            uc.mem_write(crowd.HOME_ID, struct.pack("<H", home))
            uc.mem_write(crowd.AWAY_ID, struct.pack("<H", away))
            out, _ = self.call(uc, labels["stands_away"], ecx=0x1234, edx=0x5678)
            self.assertEqual((out["eax"], out["ecx"], out["edx"]), (self.VA if away == 230 else 0x00930000, 0x1234, 0x5678))
            out, _ = self.call(uc, labels["stands_home"], eax=0x1111, ecx=0x1234)
            self.assertEqual((out["edx"], out["eax"], out["ecx"]), (self.VA if home == 230 else 0x00940000, 0x1111, 0x1234))


@unittest.skipUnless(XBE.is_file() and (RETAIL / "vc_53450030/0").is_file(), "the private retail extraction is absent")
class RetailTests(unittest.TestCase):
    def test_the_sites_and_formats_are_retail(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(XBE.read_bytes())
        for _name, va, retail in crowd.SITES:
            self.assertEqual(image.read(va, len(retail)), retail, hex(va))
        self.assertTrue(crowd._formats_ok(image))
        self.assertEqual(crowd.xbe_status(XBE.read_bytes()), "retail")

    def test_install_changes_only_the_owner_the_sites_and_the_digests(self):
        from tests.nfl2k5_classic_teams_native import build
        from mod_editor.core import nfl2k5_xbe_space as space
        from unittest.mock import patch
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        payload = build(RETAIL)[0].payload
        self.assertEqual(crowd.xbe_status(payload), "retail")
        after, receipt = crowd.apply_xbe(payload)
        self.assertEqual(crowd.xbe_status(after), "applied")
        self.assertEqual(crowd.apply_xbe(after)[1]["status"], "already_applied")
        self.assertEqual(ct.xbe_status(after), "applied")
        self.assertEqual(space.status(after), "applied")
        self.assertEqual(len(receipt["edits"]), 6)
        before_rows = [a for a in space.layout(payload)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        after_rows = [a for a in space.layout(after)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        for row in before_rows:
            self.assertIn(row, after_rows)                                   # no installed owner moved
        self.assertEqual([a["va"] for a in after_rows if a not in before_rows], [space.CLASSIC_CROWD_VA])
        image = XbeImage(after)
        for name, va, retail in crowd.SITES:                                 # each site calls its helper in the page
            call = image.read(va, 5)
            self.assertEqual(call[0], 0xE8)
            target = va + 5 + struct.unpack("<i", call[1:])[0]
            self.assertTrue(space.CLASSIC_CROWD_VA <= target < space.CLASSIC_CROWD_VA + 256, name)
            self.assertEqual(target, crowd.code_for(space.CLASSIC_CROWD_VA)[1][name], name)
        # an owner appended after the crowd (as the rookie hair and offset toss steps append theirs) lands exactly where
        # it lands without the crowd page, and every other row is the same in both; the page itself stays put
        probe = ("nfl2k5_xs1_probe_code", "code", 9000, 16)
        with patch.object(space, "LATE_OWNERS", space.LATE_OWNERS + (probe[0],)):
            later, _ = space.extend_scaleout(after, (probe,))
            plain, _ = space.extend_scaleout(payload, (probe,))
        later_rows = [a for a in space.layout(later)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        plain_rows = [a for a in space.layout(plain)["allocations"] if a["owner"] != space.DIRECTORY_OWNER]
        self.assertEqual([a for a in later_rows if a["owner"] != crowd.OWNER], plain_rows)
        self.assertEqual([a["va"] for a in later_rows if a["owner"] == crowd.OWNER], [space.CLASSIC_CROWD_VA])
        self.assertEqual(crowd.xbe_status(later), "applied")

    def test_the_fourteen_files_are_the_dolphins_files_in_seamen_colours_with_no_mark(self):
        from nfl_txtr import decode_chunk, parse_chunks, parse_texture, texture_to_rgba
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
        with hs.Source(RETAIL) as src:
            files, receipts = crowd.compose_files(src.get)
            retail = {name: src.get(source) for name, source in crowd.FILES}

        def textures(data):
            out = {}
            for c in parse_chunks(data, allow_trailing=True):
                decoded, _ = decode_chunk(data, c)
                if c.kind == "TXTR":
                    t = parse_texture(decoded, c)
                    out[t.name] = np.frombuffer(texture_to_rgba(decoded, c, t), np.uint8).reshape(t.height, t.width, 4)
                elif c.kind == "TSET":
                    for t in fixes._tset_textures(decoded):
                        out[t["name"]] = fixes.read_palette(decoded, c, t)[fixes.read_planes(decoded, c, t)[0]]
            return out
        self.assertEqual([n for n, _ in files], [n for n, _ in crowd.FILES])
        for name, data in files:
            with self.subTest(file=name):
                self.assertEqual(len(data), len(retail[name]))                       # every span refit in place
                made, was = textures(data), textures(retail[name])
                self.assertEqual(set(made), set(was))
                touched = (set(crowd.PICTURES) | set(crowd.CLEAR) | set(crowd.PAINTED_HEADS) | set(crowd.DECALS)
                           | set(crowd.RECOLOURED) | set(crowd.PAINTED_OUT))
                for tex, rgba in made.items():
                    if tex.startswith("endzone_"):
                        # review M1: the 's' packages (ESPN Stadium, the Seamen's home) carry the classic field's own
                        # end zones: home endzone_south_*, away endzone_north_*; the 'n' packages carry none
                        self.assertEqual(name[-5], "s", (name, tex))
                        self.assertEqual(tex.split("_")[1], "south" if name.startswith("SMh") else "north", name)
                        want = crowd._end_zone(tex).astype(int)
                        self.assertLess(float(np.abs(rgba.astype(int) - want).mean()), 4.0, (name, tex))
                        self.assertFalse(np.array_equal(rgba, was[tex]), (name, tex))
                        continue
                    if tex in ("48", "49", "50", "51", "52", "53", "54", "55", "56", "57"):
                        continue
                    if not name.startswith(("SMh", "SMa")) and tex not in touched:
                        self.assertTrue(np.array_equal(rgba, was[tex]), (name, tex))       # untouched: retail
                        continue
                    aqua, orange = _hues(rgba)
                    self.assertLessEqual(orange, max(8, _hues(was[tex])[1] // 50), (name, tex))
                    if tex in crowd.CLEAR or tex in crowd.DECALS:
                        self.assertFalse(rgba[..., 3].any(), tex)
                    if tex in crowd.WARM:                           # review S1: no orange-red left on the uniforms
                        self.assertEqual(_warm(rgba), 0, (name, tex))
                        self.assertGreater(_warm(was[tex]), 1000, (name, tex))
                    if tex in crowd.PAINTED_OUT:                    # review S1: nothing saturated left in the marks
                        for box in crowd.PAINTED_OUT[tex]:
                            inside = crowd.mark_mask(was[tex], box)
                            self.assertGreater(int(inside.sum()), 100, box)
                            sat = _sat(rgba)
                            self.assertEqual(int((sat[inside] > 0.35).sum()), 0, box)
        # the faces keep their lips and skin: only the paint moved
        heads = textures(dict(files)["nsSM.iff"])["head01"].astype(int), textures(retail["nsSM.iff"])["head01"].astype(int)
        top = crowd.HEAD_FACE_TOP
        self.assertTrue(np.array_equal(heads[0][:top], heads[1][:top]))           # ear, teeth and lips: retail
        self.assertGreater(int((np.abs(heads[0][top:] - heads[1][top:]).sum(axis=2) > 0).sum()), 500)   # the paint moved
        self.assertEqual(receipts["nsSM.iff"]["source"], "ns14.iff")


if __name__ == "__main__":
    unittest.main()
