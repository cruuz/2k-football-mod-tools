"""Bounded native proofs for the protection-calls owner (b780 p1-slide). No game boot.

The real retail code runs in Unicorn on the pinned USA default.xbe with the owner installed at its allocation:

* the per-tick slide call 0x23BC40 -> 0x23B5B0 -> the owner's snap_slide -> the real automatic read 0x23B6E0 (box
  count, facing 0x2FA5E0, depth 0x239B20) on a synthetic 4-3 with a walked-up safety on one side;
* the real pass set 0x23ABB0 for every blocker record (its target coordinator 0x2FAFF0 is replaced by a probe that
  records the set point it is handed: the slide is added before that call);
* the at-line case 0x18FE65 of 0x18FBE0 with the real 0xFEFA0 for the offense's three-audible menu.

Player skeletons, positions, the ball, the attacked-goal direction and the menu records are supplied inputs.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_protection_calls as pc
from mod_editor.core import nfl2k5_protection_calls_code as assembly
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

SLIDE, PLAY_LOG, OFFENSE_VA, DEFENSE_VA, CALLER_VA = 0xC16BAC, 0xE53804, 0xE60280, 0xE60284, 0xE60288
GAME_TICK = 0xB71D10
RECORDS, RECORD_COUNT, PANEL = 0xC168B0, 0xC16BB0, 0xBA3178
BALL_VA, CLOCK_VA, STATE_VA, KIND_VA, CARRIER_VA = 0xE602EC, 0xE6029C, 0xE602B8, 0xE602BC, 0xBE4F8C
SLIDE_STEP, SLIDE_MAX = 137.16, 274.32
OL_ROLE = 7                       # 0x509E08 flag 0x20: pass-set legs reach the target coordinator (0x23A710)
DL_ROLE, LB_ROLE, DB_ROLE = 15, 10, 4
TARGET_PROBE = 0x2FAFF0           # the probe replaces the coordinator's entry: records [edx] (the set point), fldz, ret 0x1C
PROBE_LOG = 0x3F00000


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


class World:
    OFF, DEF, T8, GOAL, BALL, CLOCK = 0x3030000, 0x3031000, 0x3034000, 0x3034100, 0x3035000, 0x3036000
    BRAIN_OFF, BRAIN_DEF, FLAGS = 0x3037000, 0x3038000, 0x3039000
    PLAYERS, STACK, STOP = 0x3000000, 0x3100000, 0x3120000

    def __init__(self, payload, *, attack=+1):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        pages = set()
        for s in image.sections:
            pages.update(range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096))
        pages.add(0x10000)
        ranges = []
        for va in sorted(pages):
            if ranges and ranges[-1][1] == va:
                ranges[-1][1] += 4096
            else:
                ranges.append([va, va + 4096])
        for a, b in ranges:
            self.uc.mem_map(a, b - a)
        self.uc.mem_write(0x10000, payload[:4096])
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, image.read(s.start, s.raw_size))
        self.uc.mem_map(self.PLAYERS, 0x40000)
        self.uc.mem_map(self.STACK, 0x20000)
        self.uc.mem_map(self.STOP, 0x1000)
        self.uc.mem_map(PROBE_LOG, 0x1000)
        self.uc.mem_write(self.STOP, b"\xf4")
        # the coordinator probe: append the 16-byte set point to the log, fldz, ret 0x1C
        probe = bytes.fromhex("5657a1") + struct.pack("<I", PROBE_LOG) + bytes.fromhex("c1e0048db8") \
            + struct.pack("<I", PROBE_LOG + 16) + bytes.fromhex("89d6b904000000f3a5ff05") + struct.pack("<I", PROBE_LOG) \
            + bytes.fromhex("5f5ed9eec21c00")
        self.uc.mem_write(TARGET_PROBE, probe)
        self.attack = attack
        self.u32(OFFENSE_VA, self.OFF); self.u32(DEFENSE_VA, self.DEF); self.u32(CALLER_VA, self.OFF)
        self.u32(self.OFF, self.DEF); self.u32(self.DEF, self.OFF)          # +0: the other team
        for team in (self.OFF, self.DEF):
            self.u32(team + 8, self.T8)
            self.u32(team + 0xC, self.BRAIN_OFF if team == self.OFF else self.BRAIN_DEF)
        self.u32(self.T8 + 0xC, self.GOAL)
        self.f32(self.GOAL + 4, 4572.0 * attack)        # the attacked goal z
        self.u32(self.BRAIN_OFF + 0xC, self.FLAGS)       # 0xFEDF0: [[[off]+0xC]+0xC]+4 & 0x1C0 != 0x180
        self.u32(self.FLAGS + 4, 0)
        self.u32(BALL_VA, self.BALL)
        for off, value in ((0x10, 0.0), (0x14, 0.0), (0x18, 0.0), (0x1C, 1.0)):
            self.f32(self.BALL + off, value)
        self.u32(CLOCK_VA, self.CLOCK); self.f32(self.CLOCK + 0x10, 0.0)
        self.u32(STATE_VA, 0xE); self.u32(KIND_VA, 5)
        self.u32(PLAY_LOG, 41)
        self.u32(GAME_TICK, 5000)
        self.next_player = self.PLAYERS
        self.offense, self.defense, self.blockers = [], [], []

    # memory helpers
    def u32(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def f32(self, va, value):
        self.uc.mem_write(va, struct.pack("<f", value))

    def rf32(self, va):
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    def ru32(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def player(self, team, role, x, z, vx=0.0, vz=0.0, cpu=True):
        """Object +0xC brain, +0x18 transform (+0x30 x, +0x38 z, +0x40 vx, +0x48 vz), +0x20 assignment block,
        +0x2D role, +0x34 next, +0x38 team, +0x48 active (0). Coordinates are local (offense frame); world = attack *."""
        p = self.next_player; self.next_player += 0x2000
        brain, xf, block = p + 0x100, p + 0x200, p + 0x400
        for off, value in ((0xC, brain), (0x18, xf), (0x20, block), (0x38, team), (0x48, 0), (0x34, 0), (0x10, p + 0x1800)):
            self.u32(p + off, value)
        self.uc.mem_write(p + 0x2D, bytes([role, 0]))
        self.u32(brain, 0xFFFFFFFF if cpu else 0)
        for off, value in ((0x30, self.attack * x), (0x34, 0.0), (0x38, self.attack * z), (0x3C, 1.0),
                           (0x40, self.attack * vx), (0x44, 0.0), (0x48, self.attack * vz), (0x4C, 0.0)):
            self.f32(xf + off, value)
        self.u32(block + 0x310, p + 0x1C00)             # where 0x23ABB0 stores the coordinator's picks
        roster = self.offense if team == self.OFF else self.defense
        if roster:
            self.u32(roster[-1] + 0x34, p)
        else:
            self.u32(team + 4, p)
        roster.append(p)
        return p

    def pass_leg(self, p, x_offset, z_offset):
        """The blocker's assignment cursor ([+0x20] + 0x41C): node 0 = Block Leg (opcode 0x11) with its decoded
        operands at +0x14: 0 leg type 1 (set to offset), 2 origin 0 (the ball), 4 angle selector 2, 5/6 offsets."""
        cursor = self.ru32(p + 0x20) + 0x41C
        nodes, head = p + 0x1000, p + 0x1100
        self.u32(cursor, head); self.u32(head + 4, nodes)
        self.uc.mem_write(nodes, bytes([0x11]) + bytes(7))
        self.uc.mem_write(cursor + 0x34, b"\x00")
        for idx, value in ((0, 1.0), (2, 0.0), (4, 2.0), (5, x_offset), (6, z_offset), (7, 0.0)):
            self.f32(cursor + 0x14 + idx * 4, value)
        self.blockers.append(p)

    def records(self):
        """The blocker records 0xC168B0 as 0x23ADA0 leaves them: player, world set point, leg type 1."""
        for i, p in enumerate(self.blockers):
            rec = RECORDS + 0x20 * i
            self.uc.mem_write(rec, bytes(0x20))
            self.u32(rec, p)
            cursor = self.ru32(p + 0x20) + 0x41C
            x, z = self.rf32(cursor + 0x14 + 5 * 4), self.rf32(cursor + 0x14 + 6 * 4)
            self.f32(rec + 0x14, self.attack * x + self.rf32(self.BALL + 0x10))
            self.f32(rec + 0x18, self.attack * z + self.rf32(self.BALL + 0x18))
            self.u32(rec + 0x1C, 1)
        self.uc.mem_write(RECORD_COUNT, struct.pack("<h", len(self.blockers)))

    def four_three(self, overload=-1):
        """Five linemen, a QB and a back; 4-3 front, two corners, a deep safety and a safety walked up on the
        `overload` side (local x sign), 5 yd off the ball."""
        for x in (-280.0, -140.0, 0.0, 140.0, 280.0):
            p = self.player(self.OFF, OL_ROLE, x, -30.0)
            self.pass_leg(p, x, -150.0)
        qb = self.player(self.OFF, 0, 0.0, -120.0)
        self.u32(CARRIER_VA, qb)
        self.u32(qb + 0x10, qb + 0x1800); self.u32(qb + 0x1800 + 4, qb + 0x1900)
        self.player(self.OFF, 7, 0.0, -600.0)
        for x in (-330.0, -110.0, 110.0, 330.0):
            self.player(self.DEF, DL_ROLE, x, 60.0)
        for x in (-380.0, 0.0, 380.0):
            self.player(self.DEF, LB_ROLE, x, 380.0)
        self.player(self.DEF, DB_ROLE, overload * 520.0, 300.0)        # the walked-up safety
        for x in (-1500.0, 1500.0):
            self.player(self.DEF, DB_ROLE, x, 600.0)
        self.player(self.DEF, DB_ROLE, 0.0, 1400.0)
        self.records()

    def run(self, start, regs=None, stack=(), stops=None, budget=400_000):
        esp = self.STACK + 0x10000
        words = [self.STOP] + list(stack)
        for i, w in enumerate(words):
            self.u32(esp + 4 * i, w)
        self.uc.reg_write(x86.UC_X86_REG_ESP, esp)
        self.uc.reg_write(x86.UC_X86_REG_EBP, esp + 0x400)
        for name, value in (regs or {}).items():
            self.uc.reg_write(getattr(x86, f"UC_X86_REG_{name.upper()}"), value & 0xFFFFFFFF)
        ends = [self.STOP] + list(stops or ())
        hit = []

        def hook(u, address, _size, _data):
            if address in ends:
                hit.append(address); u.emu_stop()
        h = self.uc.hook_add(uc.UC_HOOK_CODE, hook)
        try:
            self.uc.emu_start(start, self.STOP + 1, count=budget)
        finally:
            self.uc.hook_del(h)
        if not hit:
            raise AssertionError(f"run from {start:#x} did not reach an end point")
        return hit[0], self.uc.reg_read(x86.UC_X86_REG_ESP) - esp

    def slide_call(self, argument):
        """0x23BC40 as 0x23DBE0 calls it: push argument; call 0x23BC40 (the callee pops it)."""
        end, delta = self.run(0x23BC40, stack=(argument,))
        return self.rf32(SLIDE), delta

    def pass_sets(self):
        """0x23ABB0 for every record; the world set point x each one hands the coordinator."""
        self.u32(PROBE_LOG, 0)
        for i in range(len(self.blockers)):
            self.run(0x23ABB0, regs=dict(ecx=i))
        n = self.ru32(PROBE_LOG)
        return [round(self.rf32(PROBE_LOG + 16 + 16 * k), 2) for k in range(n)]

    def set_call(self, call, team=None, stamp=None, used=0, tick=None):
        state = self.state_va
        self.u32(state, self.OFF if team is None else team)
        self.u32(state + 4, self.ru32(PLAY_LOG) if stamp is None else stamp)
        self.uc.mem_write(state + 8, bytes([call, used, 0, 0]))
        self.u32(state + 12, self.ru32(GAME_TICK) - 120 if tick is None else tick)

    def state(self):
        raw = bytes(self.uc.mem_read(self.state_va, 16))
        team, stamp = struct.unpack_from("<II", raw)
        return dict(team=team, stamp=stamp, call=raw[8], used=raw[9], tick=struct.unpack_from("<I", raw, 12)[0])


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class SnapSlideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = pc.apply(cls.retail)
        rows = pc.allocations(cls.patched)
        cls.code_va, cls.state_va = rows["code"]["va"], rows["data"]["va"]

    def world(self, payload=None, attack=+1, overload=-1):
        w = World(payload or self.patched, attack=attack)
        w.state_va = self.state_va
        w.four_three(overload)
        return w

    def auto(self, attack, overload, argument=0):
        """The retail automatic slide for the same world, on the retail executable."""
        w = World(self.retail, attack=attack)
        w.state_va = self.state_va
        w.four_three(overload)
        value, delta = w.slide_call(argument)
        self.assertEqual(delta, 8)
        return value

    def test_retail_reads_the_overload_and_the_owner_keeps_it_without_a_call(self):
        for attack in (+1, -1):
            for overload in (-1, +1):
                with self.subTest(attack=attack, overload=overload):
                    retail = self.auto(attack, overload)
                    # one extra man on the overload side (five on that side, four on the other): 1.5 yd away from it,
                    # in world x (local overload side * attack direction)
                    self.assertAlmostEqual(retail, -overload * attack * SLIDE_STEP, places=2)
                    w = self.world(attack=attack, overload=overload)
                    value, delta = w.slide_call(0)
                    self.assertEqual(delta, 8)                       # ret 4 (return + argument), as retail
                    self.assertEqual(value, retail)
                    self.assertEqual(w.state()["call"], 0)

    def test_a_call_replaces_the_slide_toward_the_called_side_in_both_directions(self):
        for attack in (+1, -1):
            for call, side in ((pc.CALL_RIGHT, +1), (pc.CALL_LEFT, -1)):
                for argument in (0, 1):
                    with self.subTest(attack=attack, call=call, argument=argument):
                        w = self.world(attack=attack)
                        w.f32(w.CLOCK + 0x10, 1.5)             # past the 1-second re-seat window of the live call
                        w.set_call(call)
                        value, delta = w.slide_call(argument)
                        self.assertEqual(delta, 8)
                        # local +x is the offense's right; world = attack direction * local
                        self.assertAlmostEqual(value, side * attack * SLIDE_MAX, places=2)
                        self.assertAlmostEqual(value, pc.world_slide(call, 4572.0 * attack), places=2)
                        st = w.state()
                        self.assertEqual(st["call"], call)
                        self.assertEqual(st["used"], argument)

    def test_every_pass_set_point_moves_by_the_called_slide(self):
        for attack in (+1, -1):
            with self.subTest(attack=attack):
                w = self.world(attack=attack)
                auto, _ = w.slide_call(0)
                base = [round(w.rf32(RECORDS + 0x20 * i + 0x14), 2) for i in range(5)]
                self.assertEqual(w.pass_sets()[:5], [round(f32(b + auto), 2) for b in base])
                for call, side in ((pc.CALL_RIGHT, +1), (pc.CALL_LEFT, -1)):
                    w.set_call(call)
                    value, _ = w.slide_call(0)
                    got = w.pass_sets()[:5]
                    self.assertEqual(got, [round(f32(b + value), 2) for b in base])
                    # the whole line moves toward the called side of the offense (local x = attack * world x)
                    for g, b in zip(got, base):
                        self.assertAlmostEqual((g - b) * attack, side * SLIDE_MAX, places=1)

    def test_the_call_lasts_one_snap(self):
        w = self.world()
        auto = self.auto(+1, -1)
        w.f32(w.CLOCK + 0x10, 1.5)
        w.set_call(pc.CALL_LEFT)
        self.assertAlmostEqual(w.slide_call(0)[0], -SLIDE_MAX, places=2)       # set at the line (state 0xD)
        self.assertAlmostEqual(w.slide_call(1)[0], -SLIDE_MAX, places=2)       # live: marks the call used
        self.assertAlmostEqual(w.slide_call(1)[0], -SLIDE_MAX, places=2)       # every tick of that snap
        self.assertEqual(w.state()["used"], 1)
        self.assertEqual(w.slide_call(0)[0], auto)                              # the next play set: dropped
        self.assertEqual(w.state()["call"], 0)
        # a call from an earlier play (the play log moved), another team, or a game that was quit before its snap (the
        # game tick restarts at 0 in every game, so the new game's tick is behind the call's) is dropped at once
        for kw in (dict(stamp=40), dict(team=World.DEF), dict(tick=w.ru32(GAME_TICK) + 1)):
            w.set_call(pc.CALL_RIGHT, **kw)
            self.assertEqual(w.slide_call(1)[0], auto, kw)
            self.assertEqual(w.state()["call"], 0, kw)

    def test_owner_code_preserves_registers_and_flags(self):
        w = self.world()
        w.set_call(pc.CALL_RIGHT)
        regs = dict(eax=0x11111111, ebx=0x22222222, ecx=0x33333333, edx=0x44444444, esi=0x55555555, edi=0x66666666)
        # run the owner from its entry with the stack 0x23BC40 leaves (return, argument); the automatic read inside
        # changes nothing the caller reads, but the owner's own work must restore every GPR it touches
        w.uc.reg_write(x86.UC_X86_REG_EFLAGS, 0x202)
        end, delta = w.run(self.code_va + assembly.LABELS["snap_slide"], regs=regs, stack=(0,))
        self.assertEqual(delta, 8)
        for name in ("ebx", "esi", "edi"):       # callee-saved across 0x23B6E0 and the owner
            self.assertEqual(w.uc.reg_read(getattr(x86, f"UC_X86_REG_{name.upper()}")), regs[name], name)


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class LineButtonTests(unittest.TestCase):
    RESUME, DONE = 0x18FE6F, 0x18FF1C

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, _ = pc.apply(cls.retail)
        rows = pc.allocations(cls.patched)
        cls.code_va, cls.state_va = rows["code"]["va"], rows["data"]["va"]

    def world(self, payload=None):
        w = World(payload or self.patched)
        w.state_va = self.state_va
        return w

    def panel(self, w, record, open_, count):
        base = PANEL + 0x4C * record
        w.u32(base, 1 if open_ else 0)
        w.uc.mem_write(base + 4, bytes([0, 0, count]))

    def press(self, w, event, team):
        return w.run(0x18FE65, regs=dict(ecx=event, esi=team, ebx=0), stops=(self.RESUME, self.DONE))[0]

    def test_l_and_r_set_toggle_and_replace_the_call_without_touching_the_menu(self):
        w = self.world()
        self.panel(w, 0, True, 3)
        self.assertEqual(self.press(w, pc.EVENT_L, World.OFF), self.DONE)
        self.assertEqual(w.state(), dict(team=World.OFF, stamp=41, call=pc.CALL_LEFT, used=0, tick=5000))
        self.assertEqual(w.ru32(PANEL), 1)                                    # the menu stays open
        self.assertEqual(self.press(w, pc.EVENT_R, World.OFF), self.DONE)
        self.assertEqual(w.state()["call"], pc.CALL_RIGHT)
        self.assertEqual(self.press(w, pc.EVENT_R, World.OFF), self.DONE)      # the same button again
        self.assertEqual(w.state()["call"], pc.CALL_NONE)
        w.u32(PLAY_LOG, 42); w.u32(GAME_TICK, 6000)                           # a new play: a new call, not a toggle
        w.set_call(pc.CALL_LEFT, stamp=41)
        self.assertEqual(self.press(w, pc.EVENT_L, World.OFF), self.DONE)
        self.assertEqual(w.state(), dict(team=World.OFF, stamp=42, call=pc.CALL_LEFT, used=0, tick=6000))

    def test_other_presses_and_other_menus_run_the_retail_lookup(self):
        """X/A/B on the offense's menu return the real audible entry (team brain +0x74 + 12 * index); L/R on a
        five-play menu (No Huddle) and on the defense's menu go to 0xFEFA0 with index 3/4, as retail."""
        w = self.world()
        self.panel(w, 0, True, 3)
        for event, index in ((0x37, 0), (0x38, 1), (0x39, 2)):
            self.assertEqual(self.press(w, event, World.OFF), self.RESUME)
            self.assertEqual(w.uc.reg_read(x86.UC_X86_REG_EAX), World.BRAIN_OFF + 0x74 + 12 * index)
        self.assertEqual(w.state()["call"], 0)
        seen = []
        w.uc.mem_write(0xFEFA0, b"\xb8\x3c\x3c\x3c\x3c\xc3")                  # probe: mov eax, sentinel; ret
        def probe(u, _a, _s, _d):
            seen.append((u.reg_read(x86.UC_X86_REG_ECX), u.reg_read(x86.UC_X86_REG_EDX)))
        h = w.uc.hook_add(uc.UC_HOOK_CODE, probe, begin=0xFEFA0, end=0xFEFA0)
        self.panel(w, 0, True, 5)                                              # No Huddle: five plays
        self.assertEqual(self.press(w, pc.EVENT_L, World.OFF), self.RESUME)
        self.panel(w, 0, True, 3); self.panel(w, 1, True, 5)
        self.assertEqual(self.press(w, pc.EVENT_R, World.DEF), self.RESUME)    # the defense's menu
        self.panel(w, 0, False, 3)
        self.assertEqual(self.press(w, pc.EVENT_L, World.OFF), self.RESUME)    # menu not open
        w.uc.hook_del(h)
        self.assertEqual(seen, [(World.OFF, 3), (World.DEF, 4), (World.OFF, 3)])
        self.assertEqual(w.uc.reg_read(x86.UC_X86_REG_EAX), 0x3C3C3C3C)
        self.assertEqual(w.state()["call"], 0)

    def test_retail_l_and_r_find_no_play_on_the_three_audible_menu(self):
        w = self.world(self.retail)
        self.panel(w, 0, True, 3)
        for event in (pc.EVENT_L, pc.EVENT_R):
            self.assertEqual(self.press(w, event, World.OFF), self.RESUME)
            self.assertEqual(w.uc.reg_read(x86.UC_X86_REG_EAX), 0)     # retail then closes the menu (0xFEF30)


def _shipped_xbe():
    """NFL2K5_SHIPPED_XBE: an extracted default.xbe of a built disc (any SOFTDRINK build, with or without this owner)."""
    import os
    path = os.environ.get("NFL2K5_SHIPPED_XBE")
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("NFL2K5_SHIPPED_XBE (a built disc's default.xbe) is not set")
    return Path(path).read_bytes()


@unittest.skipUnless(uc is not None, "Unicorn is required for bounded instruction replay")
class ShippedExecutableTests(unittest.TestCase):
    """The same replays on a real built executable, where every other SOFTDRINK owner is installed around these sites
    (b780 p1-slide ran it on the released v0.8 default.xbe, sha256 5f987568...)."""

    @classmethod
    def setUpClass(cls):
        cls.before = _shipped_xbe()
        cls.patched = cls.before if pc.status(cls.before) == "applied" else pc.apply(cls.before)[0]
        cls.state_va = pc.allocations(cls.patched)["data"]["va"]

    def world(self, payload, attack=+1, overload=-1):
        w = World(payload, attack=attack)
        w.state_va = self.state_va
        w.four_three(overload)
        return w

    def test_automatic_read_unchanged_and_calls_on_the_built_executable(self):
        for attack in (+1, -1):
            for overload in (-1, +1):
                with self.subTest(attack=attack, overload=overload):
                    if pc.status(self.before) != "applied":
                        self.assertEqual(self.world(self.patched, attack, overload).slide_call(0)[0],
                                         self.world(self.before, attack, overload).slide_call(0)[0])
                    for call in (pc.CALL_LEFT, pc.CALL_RIGHT):
                        w = self.world(self.patched, attack, overload)
                        w.f32(w.CLOCK + 0x10, 1.5)
                        w.set_call(call)
                        for argument in (0, 1):
                            self.assertAlmostEqual(w.slide_call(argument)[0], pc.world_slide(call, 4572.0 * attack), places=2)
        w = self.world(self.patched)
        w.set_call(pc.CALL_RIGHT)
        value, _ = w.slide_call(0)
        base = [round(w.rf32(RECORDS + 0x20 * i + 0x14), 2) for i in range(5)]
        self.assertEqual(w.pass_sets()[:5], [round(f32(b + value), 2) for b in base])

    def test_buttons_on_the_built_executable(self):
        w = World(self.patched)
        w.state_va = self.state_va
        w.u32(PANEL, 1)
        w.uc.mem_write(PANEL + 4, bytes([0, 0, 3]))
        stops = (0x18FE6F, 0x18FF1C)
        self.assertEqual(w.run(0x18FE65, regs=dict(ecx=pc.EVENT_R, esi=World.OFF, ebx=0), stops=stops)[0], 0x18FF1C)
        self.assertEqual(w.state()["call"], pc.CALL_RIGHT)
        self.assertEqual(w.run(0x18FE65, regs=dict(ecx=0x38, esi=World.OFF, ebx=0), stops=stops)[0], 0x18FE6F)
        self.assertEqual(w.uc.reg_read(x86.UC_X86_REG_EAX), World.BRAIN_OFF + 0x74 + 12)


if __name__ == "__main__":
    unittest.main()
