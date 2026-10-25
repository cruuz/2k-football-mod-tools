"""Franchise draft clock (nfl2k5_draft_clock): exact bytes, replay, refusal, presets, late-owner placement, and the
real draft code run frame by frame in Unicorn on a mid-draft franchise save. No game boot.

The pinned USA retail default.xbe is read from NFL2K5_RETAIL_EXTRACTION (skipped when absent). The frame tests also
need a franchise SAVEGAME.DAT saved on the draft screen (stage 5), named by NFL2K5_DRAFT_SAVE (skipped when absent;
the b778 dr1 evidence is a 720,044-byte save at round 1, pick 17, a user club on the clock with 146 s left). Only the
draft screen's display, sound and dialog services are substituted; the pick, next-pick, end-of-draft, PDA and clock
code is the game's own.
"""
import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_draft_clock as dc
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn  # noqa: F401
except ImportError:  # pragma: no cover
    unicorn = None

Y, X = 0x0800, 0x0400
MENU_OFFSET = 0x1A0000


class StaticTests(unittest.TestCase):
    def test_cave_shape_and_hook(self):
        code = dc.code_for(0x14EC5D0)
        self.assertEqual(len(code), dc.CODE_SIZE)
        body = code.rstrip(b"\xcc")
        self.assertLessEqual(len(body), dc.CODE_SIZE)
        self.assertEqual(code, dc.code_for(0x14EC5D0))                      # deterministic
        self.assertNotEqual(code, dc.code_for(0x14DA000))                   # position dependent (rel32 calls)
        self.assertEqual(dc.sites(0x14EC5D0), [("draft_step", 0x326DBC, bytes.fromhex("e8bffbffff"),
                                                b"\xe8" + struct.pack("<i", 0x14EC5D0 - 0x326DBC - 5)),
                                               ("draft_draw", 0x537D34, struct.pack("<I", 0x326250),
                                                struct.pack("<I", dc.draw_entry(0x14EC5D0)))])
        self.assertTrue(0x14EC5D0 < dc.draw_entry(0x14EC5D0) < 0x14EC5D0 + dc.CODE_SIZE)
        for va in (0x14EC5D0, 0x14EC5D1, 0x14DA000):                         # the help lines stay UTF-16 aligned
            raw = dc.code_for(va) if va % 16 == 0 else dc._build(va)[0]
            text = (dc.CPU_TEXT + "\0").encode("utf-16-le")
            self.assertEqual((va + raw.index(text)) % 2, 0)
        self.assertEqual(struct.pack("<f", dc.CPU_SECONDS), struct.pack("<f", 60.0))
        self.assertEqual(dc.REQUESTS, ((dc.OWNER, "code", dc.CODE_SIZE, 16),))   # code only: no state bytes

    def test_presets_options_and_late_owner_order(self):
        self.assertEqual(space.LATE_OWNERS[-9:], (dc.OWNER, "nfl2k5_weekly_progression", "nfl2k5_player_progress_screen", "nfl2k5_contract_college_guard", "nfl2k5_sim_cb_tackles", "nfl2k5_clock_led", "nfl2k5_cpu_third_down", "nfl2k5_return_coverage", "nfl2k5_module_loader"))  # b778-int2: the module loader stays last
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).franchise_draft_clock, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["franchise_draft_clock"], name in ("softdrink_advanced", "softdrink_experimental"), name)
        self.assertIn("franchise_draft_clock", settings.FEATURE_KEYS)
        self.assertIn((dc.OWNER, "Franchise draft clock"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_draft_clock.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", dc.HELP_TEXT + dc.BUILD_CAPTION + text)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.final, cls.receipt = dc.apply(cls.retail)

    def test_site_code_and_receipt(self):
        self.assertEqual(dc.status(self.retail), "retail")
        self.assertEqual(dc.status(self.final), "applied")
        self.assertEqual(space.status(self.final), "applied")
        image = XbeImage(self.final)
        code = dc.allocation(self.final)["va"]
        self.assertEqual(image.read(code, dc.CODE_SIZE), dc.code_for(code))
        raw = image.read(0x326DBC, 5)
        self.assertEqual(raw[0], 0xE8)
        self.assertEqual(0x326DBC + 5 + struct.unpack_from("<i", raw, 1)[0], code)
        self.assertEqual(self.receipt["state_bytes"], 0)

    def test_only_the_hook_changes_in_retail_sections(self):
        a, b = XbeImage(self.retail), XbeImage(self.final)
        changed = []
        for s in a.sections:
            if s.raw_size:
                x, y = a.read(s.start, s.raw_size), b.read(s.start, s.raw_size)
                changed += [s.start + i for i in range(len(x)) if x[i] != y[i]]
        self.assertEqual(changed, list(range(0x326DBD, 0x326DC1)) + [0x537D34, 0x537D35, 0x537D36, 0x537D37])
        self.assertEqual(struct.unpack("<I", b.read(0x537D34, 4))[0], dc.draw_entry(dc.allocation(self.final)["va"]))

    def test_replay_and_foreign_refusal_before_mutation(self):
        again, receipt = dc.apply(self.final)
        self.assertEqual(again, self.final)
        self.assertEqual(receipt["status"], "already_applied")
        code = dc.allocation(self.final)["va"]
        for label, (va, content) in {"hook": (0x326DBC, b"\xe8\x00\x00\x00\x00"),
                                     "code": (code + 3, b"\x90"),
                                     "draft step": (0x326996, b"\x90"),
                                     "retail clock": (0x3264A2, b"\x90"),
                                     "clock reset": (0x325A26, b"\x90"),
                                     "pad state": (0x70A1C, b"\x90"),
                                     "draw slot": (0x537D34, b"\x00"),
                                     "draw record": (0x537D28, b"\x04"),
                                     "retail draw": (0x326260, b"\x90")}.items():
            bad = repin_edit(self.final, va, content)
            self.assertEqual(dc.status(bad), "foreign", label)
            with self.assertRaises(ValueError):
                dc.apply(bad)
        retail_bad = repin_edit(self.retail, 0x326DBC, b"\x90")
        self.assertEqual(dc.status(retail_bad), "foreign")
        with self.assertRaises(ValueError):
            dc.apply(retail_bad)


def draft_save():
    path = os.environ.get("NFL2K5_DRAFT_SAVE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_DRAFT_SAVE (a franchise save on the draft screen) is not set")
    body = Path(path).read_bytes()
    if len(body) != 720044:
        raise unittest.SkipTest("NFL2K5_DRAFT_SAVE is not a 720,044-byte franchise SAVEGAME.DAT")
    return body


class Draft:
    """The franchise draft of a loaded save, stepped one screen frame at a time through ``entry`` (the cave, or the
    retail draft step 0x326980 for the base)."""

    def __init__(self, payload, save, entry=None):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = self.m = Machine(payload, trace_writes=False)
        # The released executable keeps small code caves in its header page (e.g. a jump at 0x324414 to 0x10B40);
        # the fixture maps 0x10000 but writes only the sections, so write the header bytes as the loader does.
        m.uc.mem_write(0x10000, payload[:struct.unpack_from("<I", payload, 0x108)[0]])
        m.load_franchise(save)
        m.seed(7)
        self.menu = m.ARENA + MENU_OFFSET
        self.entry = entry or dc.allocation(payload)["va"]
        self.events, self.picks = [], []

        def leaf(va, name, pop=0, value=0):
            m.leaf(va, lambda: (self.events.append(name), m.ret(value, pop=pop)), reason=name)

        def dialog():
            text = bytes(m.uc.mem_read(m.reg("EDX"), 120)).decode("utf-16le", "replace").split("\0")[0]
            self.events.append("dialog: " + text)
            m.ret(2, pop=24)
        m.leaf(0x14E440, dialog, reason="modal dialog: answered Yes / OK")
        leaf(0x177990, "notice", pop=4)       # "Round N: <team> chose <player>" on-screen notice
        leaf(0x14D3C0, "notice mode")
        leaf(0x174C70, "widget")              # board widget refresh
        leaf(0x14E520, "info")
        leaf(0x35F140, "pda")                 # PDA widgets after the six recommendations are chosen
        leaf(0x326530, "end of draft")        # the stage advance and menu pop at the end of the draft

        def logged():  # the draft transaction record (0x2BFDF0, ecx = 4): round, pick, order byte, player record
            r, p = m.get(0xE3C0A8), m.get(0xE3C0A4)
            self.picks.append((r, p, bytes(m.uc.mem_read(0xE3C0B4 + 32 * r + p, 1))[0], m.reg("EDX")))
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: logged(), begin=0x2BFDF0, end=0x2BFDF0)

    @property
    def made(self):
        """Picks made (a CPU pick writes two draft records: the pick and the rookie signing)."""
        return len({p[:2] for p in self.picks})

    def club(self):
        return (self.m.call(0x3254D0) - self.m.team_base) // 500

    def human(self):
        return bool(self.m.call(0xC4D50, ecx=self.m.call(0x3254D0)))

    @property
    def clock(self):
        return self.m.f32(0xE3C0AC)

    @property
    def at(self):
        return self.m.get(0xE3C0A8), self.m.get(0xE3C0A4)

    def frame(self, dt=1 / 60, press=0):
        m = self.m
        m.f32(self.menu + 0x104, dt)
        m.put(0xB37A70, 1)
        m.put(0xB37A78, press)
        m.call(self.entry, ecx=self.menu, budget=2_000_000_000)
        return m.get(0xB37A78)


@unittest.skipIf(unicorn is None, "unicorn is not installed")
class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.save = draft_save()
        cls.retail = retail_xbe()
        cls.final, _ = dc.apply(cls.retail)

    def draft(self, payload=None, entry=None):
        return Draft(payload or self.final, self.save, entry)

    def to_cpu(self, d):
        """Simulate the user's pick (Y) so a CPU club is on the clock."""
        self.assertTrue(d.human())
        d.frame(press=Y)
        self.assertFalse(d.human())

    def test_retail_base_makes_every_cpu_pick_in_one_frame(self):
        d = self.draft(self.retail, 0x326980)
        d.m.f32(0xE3C0AC, 0.01)                         # the user's clock runs out on this frame
        d.frame()
        self.assertIn("dialog: A Player Has Been Drafted For You", d.events)
        self.assertGreater(d.made, 2)             # his pick and then every CPU pick at once
        self.assertTrue(d.human())

    def test_simulate_my_pick_then_each_cpu_club_has_sixty_seconds(self):
        d = self.draft()
        start = d.at
        left = d.frame(press=Y)
        self.assertEqual(left & Y, 0)                   # consumed
        self.assertEqual(d.made, 1)
        self.assertIn("dialog: A Player Has Been Drafted For You", d.events)
        self.assertEqual(d.at, (start[0], start[1] + 1))
        self.assertFalse(d.human())
        self.assertEqual(d.clock, 60.0)
        for second in range(59):
            d.frame(dt=1.0)
            self.assertEqual(d.made, 1, second)
            self.assertAlmostEqual(d.clock, 59.0 - second, places=3)
        d.frame(dt=1.0)                                 # 0.0 is not below zero (as retail)
        self.assertEqual(d.made, 1)
        d.frame(dt=1 / 60)
        self.assertEqual(d.made, 2)
        self.assertEqual(d.events.count("notice"), 2)
        self.assertEqual(d.at, (start[0], start[1] + 2))

    def test_advance_to_next_pick(self):
        d = self.draft()
        self.to_cpu(d)
        n = d.made
        d.frame(dt=5.0)
        self.assertEqual(d.made, n)
        left = d.frame(press=Y)
        self.assertEqual(left & Y, 0)
        self.assertEqual(d.made, n + 1)
        if not d.human():
            self.assertEqual(d.clock, 60.0)             # the next CPU club starts its 60 s at once

    def test_advance_to_next_user_pick_is_the_retail_fast_draft(self):
        d = self.draft()
        self.to_cpu(d)
        n = d.made
        d.frame(press=X)
        self.assertTrue(d.human() or d.at[0] >= 7)
        self.assertGreater(d.made, n + 1)
        self.assertIn("pda", d.events)                  # retail refresh of the PDA's recommendations

    def test_buttons_do_nothing_out_of_turn(self):
        d = self.draft()
        n = d.made
        left = d.frame(press=X)                         # user on the clock: X does nothing (and is consumed)
        self.assertEqual(left & X, 0)
        self.assertEqual(d.made, n)
        self.assertTrue(d.human())
        left = d.frame(press=0x1000 | 0x2000 | 0x100)   # Black / White / A are the screen's own: left alone
        self.assertEqual(left, 0x1000 | 0x2000 | 0x100)
        self.assertEqual(d.made, n)

    def test_simulate_ignored_in_the_first_moment_of_the_users_clock(self):
        d = self.draft()
        d.m.f32(0xE3C0AC, 210.5 - 0.5)                  # his clock started half a second ago
        d.frame(press=Y)
        self.assertEqual(d.made, 0)
        self.assertTrue(d.human())
        d.m.f32(0xE3C0AC, 208.0)
        d.frame(press=Y)
        self.assertEqual(d.made, 1)

    def test_help_line_follows_the_clock(self):
        d = self.draft()
        m, lines = d.m, []
        m.leaf(0x326250, lambda: (lines.append("retail draw"), m.ret()), reason="the screen's 3D/board draw")

        def text():
            sp = m.reg("ESP")
            words = [m.get(sp + 4 * i) for i in range(1, 9)]
            raw = bytes(m.uc.mem_read(m.reg("ECX"), 160))
            lines.append((raw.decode("utf-16-le").split("\0")[0], m.reg("EDX"),
                          struct.unpack("<4f", struct.pack("<4I", *words[:4])), words[4:7], hex(words[7])))
            m.ret(pop=0x20)
        m.leaf(0x6BC30, text, reason="text renderer")
        draw = dc.draw_entry(dc.allocation(self.final)["va"])
        m.call(draw, budget=10_000_000)
        self.assertEqual(lines[0], "retail draw")
        self.assertEqual(lines[1], ("Y  Simulate My Pick", 0, (320.0, 456.0, 20.0, 240.0), [0, 0, m.get(0xA90ECC)],
                                    "0xffffffff"))
        self.to_cpu(d)
        lines.clear()
        m.call(draw, budget=10_000_000)
        self.assertEqual(lines[1][0], "Y  Advance to Next Pick      X  Advance to Next User Pick")
        m.put(0xC94480, 1)                              # CPU Complete Draft: only the retail draw
        lines.clear()
        m.call(draw, budget=10_000_000)
        self.assertEqual(lines, ["retail draw"])
        m.put(0xC94480, 0)
        m.put(0xE3C0A8, 7)                              # draft over: only the retail draw
        lines.clear()
        m.call(draw, budget=10_000_000)
        self.assertEqual(lines, ["retail draw"])

    def test_loaded_cpu_clock_is_held_to_sixty(self):
        d = self.draft()
        self.to_cpu(d)
        d.m.f32(0xE3C0AC, 146.25)                       # e.g. a save made while a CPU club was on the clock
        d.frame(dt=0.25)
        self.assertAlmostEqual(d.clock, 59.75, places=4)

    def test_first_pick_round_boundary_and_final_pick(self):
        # Reposition the real loaded draft cursor to each boundary. The existing undrafted pool and order are
        # retained; this checks the screen's control flow, not a regenerated rookie class from an earlier date.
        for at, after in (((0, 0), (0, 1)), ((0, 31), (1, 0)), ((6, 31), (7, 0))):
            for press in (0, Y, X):
                with self.subTest(at=at, press=press):
                    d = self.draft()
                    d.m.put(dc.ROUND, at[0])
                    d.m.put(0xE3C0A4, at[1])
                    d.m.f32(dc.CLOCK, dc.RETAIL_CLOCK)
                    self.assertFalse(d.human())
                    d.frame(dt=1.0, press=press)
                    if press == X:
                        self.assertTrue(d.at[0] >= 7 or d.human())
                    elif press == Y:
                        self.assertEqual(d.at, after)
                        self.assertEqual(d.made, 1)
                        if after[0] < 7:
                            self.assertEqual(d.clock, dc.CPU_SECONDS)
                        else:
                            d.frame()
                            self.assertIn("end of draft", d.events)
                    else:
                        self.assertEqual(d.at, at)
                        self.assertEqual(d.made, 0)
                        self.assertEqual(d.clock, 59.0)

    def test_next_user_with_no_user_picks_left_finishes_the_draft(self):
        d = self.draft()
        d.m.put(dc.ROUND, 6)
        d.m.put(0xE3C0A4, 17)  # last round, immediately after this save's final user pick
        self.assertFalse(d.human())
        d.frame(press=X)
        self.assertEqual(d.at, (7, 0))
        self.assertIn("end of draft", d.events)

    def test_next_user_refreshes_the_same_native_phone_recommendations(self):
        recommendations = []
        for payload, entry, press in ((self.retail, 0x326980, 0), (self.final, None, X)):
            d = self.draft(payload, entry)
            d.m.put(0xE3C0A4, 17)  # a CPU pick immediately after the saved user's pick
            d.m.f32(dc.CLOCK, dc.RETAIL_CLOCK)
            d.frame(press=press)
            self.assertTrue(d.human())
            self.assertIn("pda", d.events)
            self.assertEqual(d.m.get(0xC95C20), 6)  # native backing list for the phone recommendations
            players = struct.unpack("<6I", d.m.uc.mem_read(0xC95C08, 24))
            self.assertEqual(len(set(players)), 6)
            self.assertNotIn(0, players)
            recommendations.append(players)
        self.assertEqual(*recommendations)

    def test_exhausted_draft_ends_with_either_shortcut(self):
        for press in (0, Y, X):
            with self.subTest(press=press):
                d = self.draft()
                d.m.leaf(dc.PLAYERS_LEFT, lambda: d.m.ret(0), reason="exhausted undrafted pool")
                d.frame(press=press)
                self.assertEqual(d.made, 0)
                self.assertIn("end of draft", d.events)

    def test_native_saved_cursor_and_clock_resume_without_private_state(self):
        for cpu in (False, True):
            with self.subTest(cpu=cpu):
                d = self.draft()
                if cpu:
                    self.to_cpu(d)
                d.frame(dt=10.0)
                at, seconds = d.at, d.clock
                m = d.m
                front = m.ARENA + 0x996FC
                # Execute the native serializer's draft-field prefix, then its full native loader. The rest of
                # the serializer needs the game's save-pointer relocation table, outside this screen fixture.
                m.call(0x2D0790, ecx=front, stop=0x2D07D1)
                self.assertEqual(m.f32(front + 0x700), seconds)
                self.assertEqual(bytes(m.uc.mem_read(front + 0x704, 2)), bytes((at[1], at[0])))
                m.put(dc.ROUND, 0)
                m.put(0xE3C0A4, 0)
                m.f32(dc.CLOCK, dc.RETAIL_CLOCK)
                m.call(0x2D0CE0, ecx=front, budget=3_000_000)
                self.assertEqual(d.at, at)
                self.assertEqual(d.clock, seconds)
                self.assertEqual(d.human(), not cpu)
                d.frame(dt=0.25)
                self.assertAlmostEqual(d.clock, seconds - 0.25, places=4)

    def test_step_preserves_callee_saved_registers_and_stack(self):
        d = self.draft()
        for press in (0, Y, 0, Y, X):
            d.frame(press=press)
            for register, value in (("ESI", 0x22222222), ("EDI", 0x33333333), ("EBX", 0x11111111),
                                    ("EBP", 0x44444444), ("ESP", d.m.STACK + 4)):
                self.assertEqual(d.m.reg(register), value, (press, register))

    def test_cpu_complete_draft_stays_retail(self):
        d = self.draft()
        d.m.put(0xC94480, 1)
        d.frame()
        self.assertIn("end of draft", d.events)
        self.assertEqual(d.at[0], 7)

    def test_whole_draft_same_picks_as_retail(self):
        """Every pick of the rest of the draft, in order, is the same player for the same club as the retail fast
        draft (which the CPU Complete Draft option runs), and the draft ends once."""
        r = self.draft(self.retail, 0x326980)
        r.m.put(0xC94480, 1)
        r.frame()
        d = self.draft()
        d.m.put(0xC94480, 0)
        frames = 0
        while "end of draft" not in d.events and frames < 5000:
            d.frame(press=Y)
            if d.human():
                d.m.f32(0xE3C0AC, 100.0)                # past the 1.5 s guard, as a player would be
            frames += 1
        self.assertEqual(d.events.count("end of draft"), 1)
        self.assertEqual(r.events.count("end of draft"), 1)
        self.assertEqual(d.picks, r.picks)  # round, pick, club AND player, including the signing records



RELEASED_SHA256 = "9465382bfd617b6d1aeadc5653fefef256678c12a65a5f828705495291e40610"  # v0.6.1 default.xbe


@unittest.skipIf(unicorn is None, "unicorn is not installed")
class ReleasedFrameTests(FrameTests):
    """The same frames on the released SOFTDRINK 2K28 v0.6.1 executable (its practice-squad roster limit inside the
    draft step's user branch, MyCareer's club-control hook, the reworked CPU pick logic), named by
    NFL2K5_RELEASED_XBE (skipped when absent). The retail base for the comparison is that same executable."""

    @classmethod
    def setUpClass(cls):
        cls.save = draft_save()
        path = os.environ.get("NFL2K5_RELEASED_XBE")
        if not path or not Path(path).is_file():
            raise unittest.SkipTest("NFL2K5_RELEASED_XBE (the v0.6.1 default.xbe) is not set")
        payload = Path(path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != RELEASED_SHA256:
            raise unittest.SkipTest("NFL2K5_RELEASED_XBE is not the v0.6.1 executable")
        cls.retail = payload
        cls.final, _ = dc.apply(payload)


if __name__ == "__main__":
    unittest.main()
