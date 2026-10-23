"""b778 ai4: CPU clock management (Noah's 10/21 stream, c2-37, c3-16, c3-23).

Bounded native replays (Unicorn) of the real USA instructions with supplied game state; no game boot here (the
emulator witness is in the job report). What they prove:

* end of the first half: the native CPU timeout decision 1885F0 (which sets the selection flag 0x80000 that the
  dead-ball step 1885D0 turns into a timeout) now fires for an offense with seconds left near midfield, where retail
  stopped calling timeouts at 15 seconds unless already in field goal range (Modern 2's 207202 operand edit);
* automatic coach profiles: the coach AI kernel no longer answers fourth downs or the clock windows from its playback
  pools (which never consult the native kneel, Hail Mary or urgency logic); it hands those snaps to the native CPU
  caller, and Modern 2 then decides fourth downs for an automatic profile (team +0x38 clear) instead of delegating
  to the retail chart as it still does for a user VIP.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coach_ai as ai
from mod_editor.core import nfl2k5_coach_ai_code as kernel
from mod_editor.core import nfl2k5_cpu_money_downs as money
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    from tests.nfl2k5_cpu_money_downs_native import Machine, uc, x86
except ImportError:      # pragma: no cover
    uc = None

TIMEOUT_FLAGGED = 0x188722       # 1885F0: the selection |= 0x80000 tail (the CPU will call a timeout)
STUB = 0x3200100


def _est(m, team, state):
    """Native 20A4D0: the time a team needs (stored by 20AC70 in BF1240 / BF1480 before each call)."""
    m.configure(**state)
    m.run(0x20A4D0, args=(team,), count=20000)
    m.uc.mem_write(STUB, b"\xd9\x1d" + struct.pack("<I", 0x3100800) + b"\xc3")
    m.run(STUB, count=10)
    return m.readf(0x3100800)


def cpu_timeout(m, *, seconds, own_yard, score_margin, quarter=2, down=2, distance=2):
    """Run the real 1885F0 for the CPU offense (home team) with the clock running. True = timeout flagged."""
    state = dict(down=down, quarter=quarter, seconds=seconds, score_margin=score_margin, own_yard=own_yard,
                 distance=distance, home=True, quarter_seconds=300)
    offense, defense = _est(m, m.HOME, state), _est(m, m.DEF, state)
    m.configure(**state)
    m.f32(0xBF1240, offense)
    m.f32(0xBF1480, defense)
    m.f32(0xE602AC, 40)                       # native play-clock reset
    m.u32(0xE602FC, 0x20)                     # two-minute warning already given
    m.u32(m.OFFMETA + 0x14, 1)                # timeout permitted at this dead ball
    m.u32(m.HOME + 0xC, m.HOME + 0x100)
    m.u32(m.HOME + 0x100 + 0x24, 0)
    return m.run(0x1885F0, ecx=m.HOME, stop_at=TIMEOUT_FLAGGED, count=200000) == TIMEOUT_FLAGGED


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class EndOfHalfTimeouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_xbe()
        cls.retail = Machine(retail)
        cls.patched = Machine(money.apply(retail, level="modern2")[0])
        for m in (cls.retail, cls.patched):
            m.supply_fg_range(50)

    def test_stream_case_colts_with_eight_seconds_at_midfield(self):
        # c3-16: Colts (CPU) ball near midfield, :08 left in the half, timeouts in hand, clock running.
        for seconds in (14, 8, 3):
            self.assertFalse(cpu_timeout(self.retail, seconds=seconds, own_yard=50, score_margin=6), seconds)
            self.assertTrue(cpu_timeout(self.patched, seconds=seconds, own_yard=50, score_margin=6), seconds)

    def test_unchanged_where_retail_already_acts_or_should_not(self):
        cases = (dict(seconds=40, own_yard=50, score_margin=6),     # above 15 s: both call it
                 dict(seconds=8, own_yard=70, score_margin=6),      # field goal range: both call it
                 dict(seconds=8, own_yard=20, score_margin=6),      # own 20: no estimate, both let it run
                 dict(seconds=8, own_yard=35, score_margin=0),      # 65 yards out, tied: both let it run
                 dict(seconds=100, own_yard=50, score_margin=6, quarter=4),
                 dict(seconds=100, own_yard=50, score_margin=-6, quarter=4))
        for case in cases:
            self.assertEqual(cpu_timeout(self.retail, **case), cpu_timeout(self.patched, **case), case)


class CoachKernelTemplates(unittest.TestCase):
    def test_v061_kernel_is_kept_exactly_and_differs_only_by_the_deferral(self):
        self.assertEqual(len(kernel.CODE_V061), 4448)
        self.assertLessEqual(len(kernel.CODE), ai.CODE_SIZE)
        names = {r[2] for r in kernel.RELOCATIONS} - {r[2] for r in kernel.RELOCATIONS_V061}
        self.assertEqual(names, {"late_native", "half_time_native"})
        self.assertEqual((ai.SYMBOLS["late_native"], ai.SYMBOLS["half_time_native"]), (0x205FE0, 0x205F80))


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class AutomaticCoachDeferral(unittest.TestCase):
    """The real coach_choose kernel (fastcall team, out) with an automatic profile bound to the home team."""

    @classmethod
    def setUpClass(cls):
        retail = cls.retail = retail_xbe()
        base = money.apply(retail, level="modern2")[0]
        cls.payloads = {}
        current, _ = ai.apply(base)
        cls.payloads["b778"] = current
        # The beta-77.1 kernel in the same allocation (what v0.6.1 players have).
        owned = ai.allocations(current)
        c, d = owned["code"]["va"], owned["data"]["va"]
        old = bytearray(current)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(current)
        off = image.offset(c, ai.CODE_SIZE)
        old[off:off + ai.CODE_SIZE] = ai.code_for(c, d, 0, "v061")
        for _, va, _, after in ai.sites(c, "v061"):
            o = image.offset(va, len(after))
            old[o:o + len(after)] = after
        space._seal_scaleout(old, space._read_scale_directory(current))
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for section in _sections(old):
            old[section.header_offset + 36:section.header_offset + 56] = section_digest(old, section)
        cls.payloads["v061"] = bytes(old)
        assert ai.installed_variant(cls.payloads["v061"]) == "v061"
        assert ai.upgrade(cls.payloads["v061"])[0] == current      # the native repair reproduces a fresh install
        cls.code, cls.data = c, d

    def choose(self, variant, *, down, quarter, seconds):
        m = Machine(self.payloads[variant])
        m.supply_fg_range(50)
        m.configure(down=down, quarter=quarter, seconds=seconds, score_margin=3, own_yard=45, distance=3,
                    home=True, quarter_seconds=300)
        team, context, book = m.HOME, m.SOURCE + 0x1E000, m.SOURCE + 0x1C000
        m.u32(0xE5FF80, 6)                       # franchise
        m.u32(0xE601FC, 0)
        m.u32(team + 0x30, 0)
        m.u32(team + 0x38, 0)                    # automatic profile: presentation cleared the flag
        m.u32(team + 0x20, book)
        m.u32(0xBA04B0, context)
        m.u32(context + 0x38, 2)                 # playback
        state = self.data
        m.u32(state + 0, context)                # context[home]
        m.u32(state + 8, book)                   # book[home]
        m.u32(state + 48, 1)                     # active[home]
        m.u32(state + 60, 0)                     # not selecting
        out = m.SOURCE + 0x1F800
        labels = kernel.LABELS if variant == "b778" else kernel.LABELS_V061
        at = m.run(self.code + labels["coach_choose"], ecx=team, edx=out, stop_at=0x17F1D0, count=200000)
        drew = at == 0x17F1D0
        return drew, (None if drew else m.uc.reg_read(x86.UC_X86_REG_EAX)), m.get(team + 0x38)

    def test_fourth_down_and_clock_windows_go_to_the_native_caller(self):
        for down, quarter, seconds in ((4, 1, 600), (4, 3, 500), (2, 2, 110), (1, 2, 30), (3, 4, 290), (1, 4, 43)):
            drew, result, flag = self.choose("b778", down=down, quarter=quarter, seconds=seconds)
            self.assertFalse(drew, (down, quarter, seconds))
            self.assertEqual((result, flag), (0, 0))
            # beta-77.1 kernel: every one of these snaps came from the playback pools
            self.assertTrue(self.choose("v061", down=down, quarter=quarter, seconds=seconds)[0], (down, quarter, seconds))

    def test_ordinary_snaps_keep_the_coach_profile(self):
        for down, quarter, seconds in ((1, 1, 600), (3, 2, 400), (2, 3, 100), (2, 4, 600)):
            for variant in ("b778", "v061"):
                self.assertTrue(self.choose(variant, down=down, quarter=quarter, seconds=seconds)[0],
                                (variant, down, quarter, seconds))

    def test_live_game_direction_magnitude_reaches_the_modern2_table(self):
        """The live game keeps the end-line z (+/-5486.4 cm, 60 yards) in the direction slot that native 209CA0
        reads only for its sign (seen in the emulator at the policy exit, EAX 0x45AB7333). The beta-77.1 template
        accepted only +/-1.0, so every real fourth down fell back to the retail chart."""
        state = dict(down=4, quarter=1, seconds=280, score_margin=0, own_yard=48, distance=2, quarter_seconds=300)
        self.assertEqual(money.decision(level="modern2", **state), "go")
        allocated, _ = space.apply(self.retail, money.REQUESTS, scaleout=True)
        templates = {"b778": money.apply(self.retail, level="modern2")[0],
                     "v061": money.lever.apply(allocated, money._adapter("modern2", variant="v061"))[0]}
        for variant, expected in (("b778", 1), ("v061", 0)):
            m = Machine(templates[variant])
            m.supply_fg_range(50)
            for direction in (-1, 1):
                m.configure(**state, direction=direction)
                m.f32(m.DIR + 4, 5486.4 * direction)
                self.assertEqual(m.run_policy(), expected, (variant, direction))
                m.configure(**state, direction=direction)          # the unit fixture value still works
                self.assertEqual(m.run_policy(), 1, (variant, direction))

    def test_automatic_profile_fourth_down_uses_modern2_user_vip_keeps_retail(self):
        m = Machine(self.payloads["b778"])
        m.supply_fg_range(50)
        context = m.SOURCE + 0x1E000
        m.u32(0xBA04B0, context)
        m.u32(context + 0x38, 2)
        m.u32(context + 0x10, 1)
        state = dict(down=4, quarter=1, seconds=600, score_margin=0, own_yard=50, distance=2, home=True)
        self.assertEqual(money.decision(level="modern2", own_yard=50, distance=2, quarter=1, seconds=600), "go")
        m.configure(**state)
        m.u32(m.HOME + 0x38, 0)
        self.assertEqual(m.run_policy(), 1)      # automatic profile: Modern 2 goes for it on 4th and 2 at midfield
        m.configure(**state)
        m.u32(m.HOME + 0x38, 1)
        self.assertEqual(m.run_policy(), 0)      # user VIP: delegated to the native chart and VIP roll
        # The brief's case: trailing by 7, 1:22 left, 4th and 5 at the opponent 35 -> go, for an automatic profile.
        late = dict(down=4, quarter=4, seconds=82, score_margin=-7, own_yard=65, distance=5, home=True,
                    quarter_seconds=300)
        self.assertEqual(money.decision(level="modern2", **{k: v for k, v in late.items() if k != "home"}), "go")
        m.configure(**late)
        m.u32(m.HOME + 0x38, 0)
        self.assertEqual(m.run_policy(), 1)


if __name__ == "__main__":
    unittest.main()
