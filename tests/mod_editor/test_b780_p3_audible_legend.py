"""b780 p3-legend: the at-line audible panel's button legend and its lift clear of the bottom score bar.

Unit tests need nothing. The native tests run the INSTALLED owner from its two hooked call sites under Unicorn on the
pinned USA retail executable (env NFL2K5_RETAIL_EXTRACTION, the same input as test_nfl2k5_play_menu_walk), with the nine
retail FONT resources and one PLAY book read from that extraction (tests/nfl2k5_user_play_menu_native): every string the
game's own text code draws is recorded with its position, so the rows, their gating and the header are checked exactly.
The shipped-disc test (env NFL2K5_V08_IMAGE, a SOFTDRINK 2K28 v0.8 image) installs the owner on the released executable
and checks that no other owner moves or changes state. Nothing here is an in-game result: the emulator gate is separate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mod_editor.core import nfl2k5_audible_legend as al  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
V08_IMAGE = Path(os.environ.get("NFL2K5_V08_IMAGE", str(ROOT / "missing-v08-image.iso")))


def _retail_inputs():
    """(retail default.xbe, PLAY resource, font entry 3) or SkipTest."""
    if not HAVE_UC:
        raise unittest.SkipTest("the native legend replay needs Unicorn")
    from tests.mod_editor.test_nfl2k5_play_menu_walk import XBE, RETAIL_XBE_SHA256
    if not XBE.is_file() or hashlib.sha256(XBE.read_bytes()).hexdigest() != RETAIL_XBE_SHA256:
        raise unittest.SkipTest("the pinned USA retail default.xbe extraction is absent")
    from nfl2k5_playbook_position_recode import OuterImage
    with OuterImage(XBE.parent) as archive:
        return XBE.read_bytes(), archive.read_entry(308), archive.read_entry(3)


class Design(unittest.TestCase):
    def test_owner_request_and_late_order(self):
        self.assertEqual(al.REQUESTS, ((al.OWNER, "code", 1280, 16),))
        # b780-int: several wave owners append after the b779 tail; each must come after every owner v0.8 carries
        self.assertEqual(space.LATE_OWNERS.count(al.OWNER), 1)
        self.assertGreater(space.LATE_OWNERS.index(al.OWNER), space.LATE_OWNERS.index("nfl2k5_sim_realism_state"))

    def test_sites_are_the_two_retail_calls(self):
        self.assertEqual(al.LIFT_SITE, ("audible_panel_lift", 0x648C5, bytes.fromhex("e866a80900")))
        self.assertEqual(al.LEGEND_SITE, ("audible_panel_legend", 0xFF60B, bytes.fromhex("e86026ffff")))
        # the retail bytes are calls to the panel setup and to the text draw
        self.assertEqual(0x648C5 + 5 + struct.unpack("<i", al.LIFT_SITE[2][1:])[0], al.PANEL_INIT)
        self.assertEqual(0xFF60B + 5 + struct.unpack("<i", al.LEGEND_SITE[2][1:])[0], al.TEXT_DRAW)

    def test_every_choice_fits_and_relocates(self):
        for lift, legend, slide in al.VARIANTS:
            with self.subTest(lift=lift, legend=legend, slide=slide):
                a, la = al.code_for(0x14DA000, lift=lift, legend=legend, slide=slide)
                b, lb = al.code_for(0x150D9E0, lift=lift, legend=legend, slide=slide)
                self.assertEqual((len(a), len(b)), (al.CODE_SIZE, al.CODE_SIZE))
                self.assertNotEqual(a, b)
                rows = al.sites(la, lift=lift, legend=legend)
                self.assertEqual([r[0] for r in rows],
                                 [n for want, n in ((lift, "audible_panel_lift"), (legend, "audible_panel_legend")) if want])
                for name, va, before, after in rows:
                    self.assertEqual(len(before), len(after))
                    self.assertEqual(after[0], 0xE8)
        with self.assertRaises(al.AudibleLegendError):
            al.code_for(0x14DA000, lift=False, legend=False)
        with self.assertRaises(al.AudibleLegendError):
            al.code_for(0x14DA000, lift=True, legend=False, slide=True)

    def test_lift_writes_only_the_settled_root(self):
        code, labels = al.code_for(0x14DA000, lift=True, legend=False)
        body = code[:labels["lift_root"] - 0x14DA000 + 0x15]
        self.assertIn(bytes.fromhex("817854") + struct.pack("<f", 240.0), body)            # cmp [root+0x54], 240.0
        self.assertIn(bytes.fromhex("c74054") + struct.pack("<f", 240.0 - al.LIFT), body)  # mov [root+0x54], 186.0
        for root in al.PANE_ROOTS:
            self.assertIn(b"\xa1" + struct.pack("<I", root), body)
        self.assertEqual(code[51:], b"\xcc" * (al.CODE_SIZE - 51))

    def test_lift_clears_the_2026_bar(self):
        """Measured retail panel bottom (HUD y 435.1, b780 r3 R3C1 still) minus LIFT stays above the bar's top tab."""
        layout = json.loads((ROOT / "data/nfl2k5_scorebug_sprite/layout.json").read_text(encoding="utf-8"))
        x0, y0, x1, y1 = layout["reference_boxes"]["bar"]
        bar_top = y0 * 448 / 1080                                   # sprite source px -> HUD y (16-line inset removed)
        self.assertAlmostEqual(bar_top, 390.76, places=2)
        self.assertGreaterEqual(bar_top - (435.1 - al.LIFT), 9.0)    # at least 9 units of clear space
        self.assertEqual(al.LIFT, 54.0)                              # the play-call screen's lift above the same bar

    def test_legend_rows_and_wording(self):
        rows = al.tables(slide=True)
        self.assertEqual([r[2] for r in rows["offense"]],
                         ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|R2| FLIP PLAY", "|R3| FLIP ROUTES", "|L2| LAST PLAY",
                          "|L1||R1| SLIDE"])
        self.assertEqual([r[2] for r in rows["defense"]], ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|R2| FLIP",
                                                           "|L2| LAST PLAY"])
        self.assertEqual([r[2] for r in rows["reduced"]], ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|L2| LAST PLAY"])
        self.assertEqual([r[2] for r in rows["basic"]], ["|DPAD| BROWSE", "|TRIANGLE| BACK"])
        self.assertNotIn(al.SLIDE, [r[2] for r in al.tables(slide=False)["offense"]])
        for table in rows.values():
            cells = [(r[0], r[1]) for r in table]
            self.assertEqual(len(cells), len(set(cells)), "two items in one cell")
        self.assertNotIn("\u2014", al.HELP_TEXT + al.BUILD_CAPTION)       # no em dash in user text

    def test_slide_call_indicator_needs_the_slide_row(self):
        lit = al.tables(slide=True, indicator=True)["offense"][-1]
        self.assertEqual(lit, (3, 1, al.SLIDE, al.COND_SLIDE))
        self.assertEqual(al.tables(slide=True)["offense"][-1][3], al.COND_ALWAYS)
        content, labels = al.code_for(0x14DA000, lift=True, legend=True, slide=True, slide_state=0x14F2000)
        self.assertEqual(len(content), al.CODE_SIZE)
        self.assertIn(struct.pack("<I", 0x14F2008), content)              # reads the call byte at state+8
        self.assertIn(struct.pack("<I", al.PLAY_LOG), content)
        self.assertIn("|L1| SLIDE LEFT\0".encode("utf-16le"), content)
        with self.assertRaises(al.AudibleLegendError):
            al.code_for(0x14DA000, slide=False, slide_state=0x14F2000)


@unittest.skipUnless(HAVE_UC, "unicorn required")
class Native(unittest.TestCase):
    TEAM_OFF = 0x2400400

    @classmethod
    def setUpClass(cls):
        cls.retail, cls.book, cls.fonts = _retail_inputs()
        cls.patched, cls.receipt = al.apply(cls.retail, lift=True, legend=True, slide=False)
        cls.patched_slide, _ = al.apply(cls.retail, lift=True, legend=True, slide=True)
        cls.legend_only, _ = al.apply(cls.retail, lift=False, legend=True, slide=False)
        cls.lift_only, _ = al.apply(cls.retail, lift=True, legend=False)

    # ---- recognition -----------------------------------------------------------------------------------------------
    def test_statuses_and_settings(self):
        self.assertEqual(al.status(self.retail), "retail")
        self.assertTrue(al.guards_valid(self.retail))
        self.assertEqual(al.read_settings(self.patched), {"status": "applied", "audible_panel_lift": True,
                                                          "audible_legend": True, "audible_legend_slide": False,
                                                          "slide_call_shown": False})
        self.assertEqual(al.read_settings(self.patched_slide)["audible_legend_slide"], True)
        self.assertEqual(al.read_settings(self.legend_only)["audible_panel_lift"], False)
        self.assertEqual(al.read_settings(self.lift_only)["audible_legend"], False)
        self.assertEqual(al.status(self.lift_only), "applied")

    def test_static_slide_row_stays_recognized_when_the_call_state_appears_later(self):
        """A slide row built without the slide-call owner's state is still a whole install if that owner is placed
        later by hand; one built with the state reads lit. Both keep their recognized choice."""
        from unittest import mock
        self.assertFalse(al.read_settings(self.patched_slide)["slide_call_shown"])
        with mock.patch.object(al, "slide_state_va", return_value=0x14F2000):
            settings = al.read_settings(self.patched_slide)
            self.assertEqual((settings["status"], settings["audible_legend_slide"], settings["slide_call_shown"]),
                             ("applied", True, False))
            again, receipt = al.apply(self.patched_slide, lift=True, legend=True, slide=True)
            self.assertEqual(again, self.patched_slide)
            self.assertTrue(receipt["already_applied"])
            lit, _ = al.apply(self.retail, lift=True, legend=True, slide=True)
            self.assertEqual(al.read_settings(lit)["slide_call_shown"], True)

    def test_replay_is_idempotent_and_other_choices_refused(self):
        again, receipt = al.apply(self.patched, lift=True, legend=True, slide=False)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        with self.assertRaises(al.AudibleLegendError):
            al.apply(self.patched, lift=True, legend=True, slide=True)
        with self.assertRaises(al.AudibleLegendError):
            al.apply(self.lift_only, lift=True, legend=True)

    def test_mixed_and_foreign_installs_are_foreign(self):
        owned = al.allocation(self.patched)
        code_off = al.rdata.offset_of(self.patched, owned["va"])
        for va in (al.LIFT_SITE[1], al.LEGEND_SITE[1]):
            broken = bytearray(self.patched)
            off = al.rdata.offset_of(self.patched, va)
            broken[off:off + 5] = al.LIFT_SITE[2] if va == al.LIFT_SITE[1] else al.LEGEND_SITE[2]
            self.assertEqual(al.status(bytes(broken)), "foreign", hex(va))       # code without its site
        broken = bytearray(self.patched)
        broken[code_off + 40] ^= 0xFF
        self.assertEqual(al.status(bytes(broken)), "foreign")                    # changed owner code
        broken = bytearray(self.retail)
        off = al.rdata.offset_of(self.retail, 0xFF5F0)                          # inside the pinned panel draw
        broken[off] ^= 0x01
        self.assertEqual(al.status(bytes(broken)), "foreign")
        with self.assertRaises(al.AudibleLegendError):
            al.apply(bytes(broken))

    def test_button_tags_exist_in_the_retail_icon_table(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.retail)
        names = set()
        for i in range(0x828 // 0x24):
            ptr = struct.unpack("<I", image.read(0xA91100 + 0x24 * i, 4))[0]
            raw = image.read(ptr, 64)
            names.add(raw.decode("utf-16le", "ignore").split("\0")[0])
        import re
        for table in al.tables(slide=True).values():
            for _row, _col, text, _cond in table:
                for tag in re.findall(r"\|([A-Z0-9_]+)\|", text):
                    self.assertIn(tag, names, text)

    # ---- the lift, run from its hooked call ----------------------------------------------------------------------
    def _machine(self, payload):
        from tests.nfl2k5_user_play_menu_native import UserPlayMenuMachine

        class M(UserPlayMenuMachine):
            def __init__(self, xbe, book, fonts):
                super().__init__(xbe, book, fonts)
                self.draws = None
                self.uc.hook_add(self.u.UC_HOOK_CODE, self._text, begin=al.TEXT_DRAW, end=al.TEXT_DRAW)

            def _text(self, uc, address, size, data):
                if self.draws is None:
                    return
                ecx, edx = self.reg("ECX"), self.reg("EDX")
                text = bytes(self.uc.mem_read(edx, 96)).decode("utf-16le", "replace").split("\0")[0]
                obj = bytes(self.uc.mem_read(ecx, 0x80))
                self.draws.append(dict(text=text, x=struct.unpack_from("<f", obj, 0x10)[0],
                                       y=struct.unpack_from("<f", obj, 0x14)[0], font=struct.unpack_from("<I", obj, 0)[0],
                                       lineh=struct.unpack_from("<f", obj, 0x24)[0], align=struct.unpack_from("<I", obj, 0x64)[0],
                                       colour=struct.unpack_from("<I", obj, 0x20)[0], verts=[]))

            def _leaf(self, uc, address, size, data):
                if self.draws and address == 0x2CA70:
                    self.draws[-1]["verts"].append(struct.unpack("<4f", self.uc.mem_read(self.reg("ECX"), 16)))
                super()._leaf(uc, address, size, data)

        return M(payload, self.book, self.fonts)

    def test_lift_moves_only_settled_roots(self):
        m = self._machine(self.patched)
        roots = (0x2600800, 0x2600900)
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda uc, a, s, d: m._return(0x1234ABCD), begin=al.PANEL_INIT,
                      end=al.PANEL_INIT)       # the native setup, stubbed; its return value passes through
        for case, ys, expect in (("both settled", (240.0, 240.0), (186.0, 186.0)),
                                 ("one foreign", (240.0, 100.0), (186.0, 100.0))):
            with self.subTest(case=case):
                for root, y in zip(roots, ys):
                    m.uc.mem_write(root, bytes(0x60))
                    m.uc.mem_write(root + 0x54, struct.pack("<f", y))
                m.put(0xBA318C, roots[0]); m.put(0xBA31D8, roots[1])
                self._run(m, al.LIFT_SITE[1])
                got = tuple(struct.unpack("<f", m.uc.mem_read(r + 0x54, 4))[0] for r in roots)
                self.assertEqual(got, expect)
        m.put(0xBA318C, 0); m.put(0xBA31D8, 0)
        self._run(m, al.LIFT_SITE[1])                              # no panes yet: nothing written, no fault

    def _run(self, m, site, regs=None):
        sp = 0x3008000 - 0x400
        start = dict(ESP=sp, EAX=0x11111111, ECX=0x44444444, EDX=0x55555555, EBX=0x22222222, EBP=0x33333333,
                     ESI=0x66666666, EDI=0x77777777, EFLAGS=0x202)
        start.update(regs or {})
        for k, v in start.items():
            m.uc.reg_write(getattr(m.r, "UC_X86_REG_" + k), v)
        m.uc.emu_start(site, site + 5, count=5_000_000)
        self.assertEqual(m.reg("EIP"), site + 5)
        for k in ("ESP", "EBX", "EBP", "ESI", "EDI"):
            self.assertEqual(m.reg(k), start[k], k)
        if site == al.LIFT_SITE[1]:
            self.assertEqual(m.reg("EAX"), 0x1234ABCD)              # 0xFF130's own return value, as retail
        self.assertEqual(m.reg("FPTAG"), 0xFFFF, "x87 stack left dirty")

    # ---- the legend, run from its hooked call --------------------------------------------------------------------
    def _legend(self, payload, *, record=0, controller=0, param=0, mode=4, offense=True, formation_type=0,
                play_side=0, play_flags=0, other_flags=None, header=(120.5, 247.5), code=None, setup=None):
        m = self._machine(payload)
        if code is not None:                       # a different build of this owner, written over its allocation
            m.uc.mem_write(al.allocation(payload)["va"], code)
        if setup is not None:
            setup(m)
        team, other, ctx, formation, play, otherplay = (0x2400400, 0x2400500, 0x2400600, 0x2400700, 0x2400780,
                                                        0x24007C0)
        m.uc.mem_write(team, bytes(0x100)); m.uc.mem_write(ctx, bytes(0x100))
        m.put(team + 0xC, ctx); m.put(ctx + 8, formation); m.put(formation + 4, (formation_type & 0x3F) << 8)
        m.put(ctx + 0xC, play); m.put(play + 4, ((play_side & 7) << 6) | play_flags)
        m.put(ctx + 0x10, 0 if other_flags is None else otherplay)
        if other_flags is not None:
            m.put(otherplay + 4, other_flags)
        m.put(0xE60280, team if offense else other); m.put(0xE60284, other if offense else team)
        m.put(al.GAME_MODE, mode)
        rec = al.PANEL_RECORDS + 0x4C * record
        m.uc.mem_write(rec, bytes(0x4C)); m.put(rec, 1)
        m.uc.mem_write(rec + 4, bytes([controller, 0, 3 if param == 0 else 5])); m.put(rec + 8, param)
        # 0xFF360's text object for the header: init, centred, shadow, header grey, font slot 6, position
        text, string = 0x2401800, 0x2401A00
        m.call(0x46920, ecx=text); m.call(0x46A00, ecx=text, edx=3); m.call(0x46B60, ecx=text, edx=1)
        m.call(0x46B50, ecx=text, edx=0xFFC0C0C0)
        m.call(0x469B0, ecx=text, edx=struct.unpack("<I", m.uc.mem_read(0xA90ECC + 24, 4))[0])
        m.call(0x46A70, ecx=text, args=[struct.unpack("<I", struct.pack("<f", v))[0] for v in (*header, 20.0)])
        m.uc.mem_write(string, "audible\0".encode("utf-16le"))
        m.draws = []
        self._run(m, al.LEGEND_SITE[1], dict(ECX=text, EDX=string, ESI=0x4C * record, EDI=team))
        draws, m.draws = m.draws, None
        return draws

    def test_header_is_drawn_first_and_unchanged(self):
        draws = self._legend(self.patched)
        head = draws[0]
        self.assertEqual((head["text"], head["x"], head["y"], head["align"], head["colour"]),
                         ("audible", 120.5, 247.5, 3, 0xFFC0C0C0))
        # the same quads as the retail executable's own call
        retail = self._legend(self.retail)
        self.assertEqual(len(retail), 1)
        self.assertEqual(retail[0]["verts"], head["verts"])

    def _texts(self, draws):
        return [d["text"] for d in draws[1:]]

    def test_offense_rows_follow_the_native_gates(self):
        cases = {
            "offense": (dict(), ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|R2| FLIP PLAY", "|R3| FLIP ROUTES",
                                 "|L2| LAST PLAY"]),
            "route flip off (current play)": (dict(play_flags=0x1000), ["|DPAD| BROWSE", "|TRIANGLE| BACK",
                                                                       "|R2| FLIP PLAY", "|L2| LAST PLAY"]),
            "route flip off (context +0x10)": (dict(other_flags=0x1000), ["|DPAD| BROWSE", "|TRIANGLE| BACK",
                                                                         "|R2| FLIP PLAY", "|L2| LAST PLAY"]),
            "no huddle": (dict(param=1), ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|L2| LAST PLAY"]),
            "kicking formation": (dict(formation_type=10), ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|L2| LAST PLAY"]),
            "special play": (dict(play_side=6), ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|L2| LAST PLAY"]),
            "basic training": (dict(mode=3), ["|DPAD| BROWSE", "|TRIANGLE| BACK"]),
            "opened by the CPU": (dict(controller=0xFF), []),
            "defense": (dict(record=1, offense=False, play_side=1), ["|DPAD| BROWSE", "|TRIANGLE| BACK", "|R2| FLIP",
                                                                     "|L2| LAST PLAY"]),
        }
        for name, (kw, want) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self._texts(self._legend(self.patched, **kw)), want)
        self.assertEqual(self._texts(self._legend(self.patched_slide))[-1], "|L1||R1| SLIDE")
        self.assertEqual(self._texts(self._legend(self.patched_slide, record=1, offense=False, play_side=1))[-1],
                         "|L2| LAST PLAY")                               # slide is an offense row only

    def test_active_slide_call_lights_its_item(self):
        """With the slide-call owner's state, the slide item names the active call in yellow, else the static row."""
        va = al.allocation(self.patched_slide)["va"]
        state = 0x2400900
        code, labels = al.code_for(va, lift=True, legend=True, slide=True, slide_state=state)
        self.assertEqual(al.sites(labels, lift=True, legend=True),
                         al.sites(al.code_for(va, lift=True, legend=True, slide=True)[1], lift=True, legend=True))
        team = 0x2400400

        def call(value, team_word=team, log=7, now=7):
            def setup(m):
                m.uc.mem_write(state, struct.pack("<II", team_word, log) + bytes([value]) + bytes(7))
                m.put(al.PLAY_LOG, now)
            return setup

        cases = (("left", call(1), "|L1| SLIDE LEFT", al.HIGHLIGHT),
                 ("right", call(2), "|R1| SLIDE RIGHT", al.HIGHLIGHT),
                 ("no call", call(0), "|L1||R1| SLIDE", al.COLOUR),
                 ("an older play", call(1, now=8), "|L1||R1| SLIDE", al.COLOUR),
                 ("the other offense", call(2, team_word=0x2400500), "|L1||R1| SLIDE", al.COLOUR))
        for name, setup, text, colour in cases:
            with self.subTest(case=name):
                draws = self._legend(self.patched_slide, code=code, setup=setup)
                last = draws[-1]
                self.assertEqual((last["text"], last["colour"]), (text, colour))
                self.assertTrue(all(d["colour"] == al.COLOUR for d in draws[1:-1]))  # every other row stays grey
                self.assertLess(max(v[1] for v in last["verts"]), 247.5)

    def test_rows_sit_above_the_panel_inside_the_screen_without_overlap(self):
        for side, header in (("left", (120.5, 247.5 - al.LIFT)), ("right", (519.5, 247.5 - al.LIFT)),
                             ("screen edge", (24.5, 247.5))):
            with self.subTest(side=side):
                draws = self._legend(self.patched_slide, header=header)[1:]
                self.assertEqual(len(draws), 6)
                boxes = []
                for d in draws:
                    self.assertEqual((d["align"], d["lineh"], d["colour"]), (1, al.LINE_HEIGHT, al.COLOUR))
                    xs = [v[0] for v in d["verts"]]; ys = [v[1] for v in d["verts"]]
                    self.assertTrue(xs and ys, d["text"])
                    box = (min(xs), min(ys), max(xs), max(ys))
                    self.assertGreaterEqual(box[0], 0.0); self.assertLessEqual(box[2], 640.0)
                    self.assertGreater(box[1], 0.0)
                    self.assertLess(box[3], header[1], d["text"])        # every row ends above the header line
                    boxes.append((d["text"], box))
                for i, (ta, a) in enumerate(boxes):
                    for tb, b in boxes[i + 1:]:
                        apart = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] + 2.5 or b[3] <= a[1] + 2.5
                        self.assertTrue(apart, f"{ta} overlaps {tb}")
                # the block's left edge is the panel's left edge for the offense's panel (header x 120.5); any other
                # header position is clamped so the whole block stays on screen (left column x >= 8, rows <= 632)
                left = min(b[0] for _t, b in boxes)
                anchor = min(max(header[0], al.ANCHOR_X_MIN), al.ANCHOR_X_MAX)
                self.assertAlmostEqual(left, anchor - 110.0, delta=1.0)
                self.assertGreaterEqual(left, 8.0 - 1.0)
                self.assertLessEqual(max(b[2] for _t, b in boxes), 632.0 + 1.0)


@unittest.skipUnless(V08_IMAGE.is_file(), "a SOFTDRINK 2K28 v0.8 image (env NFL2K5_V08_IMAGE) is required")
class ShippedDisc(unittest.TestCase):
    def test_install_on_the_released_executable_moves_nothing(self):
        from mod_editor.core.nfl2k5_espn25_rosters import read_xbe
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime, nfl2k5_widescreen as wide
        v08 = read_xbe(str(V08_IMAGE))
        self.assertEqual(al.status(v08), "retail")
        patched, receipt = al.apply(v08, lift=True, legend=True, slide=False)
        self.assertEqual(len(patched), len(v08))                         # the pool already has room: no growth
        before = {(r["owner"], r["kind"]): (r["va"], r["size"]) for r in space.layout(v08)["allocations"]}
        after = {(r["owner"], r["kind"]): (r["va"], r["size"]) for r in space.layout(patched)["allocations"]}
        self.assertEqual({k: v for k, v in after.items() if k[0] != al.OWNER}, before)
        self.assertEqual([k for k in after if k not in before], [(al.OWNER, "code")])
        for module in (runtime, wide):
            self.assertEqual(module.status(patched), module.status(v08), module.__name__)
        self.assertEqual(al.read_settings(patched)["status"], "applied")
        # only the owner's code, its two call sites, the allocator directory and section digests changed
        self.assertLess(receipt["changed_bytes"], 4096)


if __name__ == "__main__":
    unittest.main()
