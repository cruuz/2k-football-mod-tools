"""QB accuracy owner, b778 qa1, native: passes to backs at or behind the line, and screen backs drifting back.

The game's own lead solver 0x2DA8E0, route predictor 0x2266A0, accuracy, launch and flight run in Unicorn on supplied
plays (tests/nfl2k5_qb_accuracy_native.py). Compared: retail, the whole owner, and the owner with one b778 piece put
back to retail. Proves:
* a halfback or fullback target at or behind the line no longer gets retail's 1 yd downfield offset: the ball is aimed
  on his path; a wide receiver or tight end there, and any back past the line, is aimed exactly as without the piece;
* a moving screen back (route kind 9) drifting back toward the QB is aimed at his screen spot; a screen back running
  out, through or past his spot, or standing, is aimed exactly as retail (velocity lead / his spot);
* the caves preserve the registers the retail code continues with.
Skipped without the pinned retail XBE.
"""
from pathlib import Path
import math
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_qb_accuracy as accuracy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    unicorn = None

YD = 91.44
HB, FB, WR, TE = 10, 11, 9, 8
# back at (x, depth) yd moving (vx, vz) yd/s at the release; QB set 7 yd deep at x = 0
BEHIND = {"swing_r": (3., -4., 6.5, 1.), "swing_l": (-3., -4., -6.5, 1.), "flare": (2., -5., 5., -.5),
          "bubble_back": (6., -2., 4., -1.5), "swing_deep": (-2., -6., -6., .5)}
# backs whose target lands past the line (the solver aims them just upfield), and routes past the line
PAST = {"flat_r": (4., -1., 6.5, 2.), "at_line": (5., -.4, 6., .4), "flat_past": (5., 1.5, 6.5, 1.),
        "angle": (3., 2., -4.5, 4.5), "drag": (-3., 3., 7., .3), "leak_mid": (0., 2., 0., 6.), "wheel": (6., 4., 1., 7.)}


def restore(payload, site):
    _name, va, retail, _label = site
    offset = XbeImage(payload).offset(va, len(retail))
    return payload[:offset] + retail + payload[offset + len(retail):]


def throw(machine, geom, role, *, field_role=None):
    from nfl2k5_qb_accuracy_native import YD as yd
    rx, rz, rvx, rvz = geom
    machine.ratings(accuracy=.8)
    machine.route((rx * yd, rz * yd), (rvx * yd, rvz * yd), kind=1, role=role, direction=1, line=0.)
    machine.quarterback("set")
    machine.put(machine.P + 0x2C, role)
    machine.uc.mem_write(machine.P + 0x1035, bytes([role]))
    if field_role is not None:
        machine.field_role(field_role)
    machine.uc.mem_write(machine.P + 0x400, bytes([0x08 if (rvx or rvz) else 0]))
    machine.put(0xE5FC00, machine.BALL)
    machine.seed_complete_rng(7)
    result = machine.target(1.)
    t = result["time"]
    aim = (result["point"][0] / yd, result["point"][2] / yd)
    at = (rx + rvx * t, rz + rvz * t)
    speed = math.hypot(rvx, rvz)
    ux, uz = rvx / speed, rvz / speed
    dx, dz = aim[0] - at[0], aim[1] - at[1]
    return {"aim": aim, "time": t, "off_path": abs(-dx * uz + dz * ux), "miss": math.hypot(dx, dz)}


@unittest.skipIf(unicorn is None, "unicorn is required for the native probe")
class BackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_qb_accuracy_native import AccuracyMachine
        retail = retail_xbe()
        full = accuracy.apply(retail)[0]
        cls.retail = AccuracyMachine(retail)
        cls.full = AccuracyMachine(full)
        cls.no_back = AccuracyMachine(restore(full, accuracy.BACK))
        cls.no_screen = AccuracyMachine(restore(full, accuracy.SCREEN))

    def test_backs_behind_the_line_are_aimed_on_their_path(self):
        for name, geom in BEHIND.items():
            for role in (HB, FB):
                old = throw(self.no_back, geom, 1, field_role=role)
                new = throw(self.full, geom, 1, field_role=role)
                # exactly retail's yard toward the offense's goal (+z here) is gone, nothing else moves
                self.assertAlmostEqual(new["aim"][0], old["aim"][0], places=4)
                self.assertAlmostEqual(old["aim"][1] - new["aim"][1], 1., places=3)
                self.assertEqual(new["time"], old["time"])
                self.assertLess(new["off_path"], old["off_path"], (name, role, old, new))
                self.assertLess(new["miss"], old["miss"], (name, role))
                ret = throw(self.retail, geom, 1, field_role=role)
                self.assertLess(new["miss"], ret["miss"] + .05, (name, role, ret, new))

    def test_receivers_and_targets_past_the_line_are_unchanged(self):
        for name, geom in BEHIND.items():
            for role in (WR, TE, 0):
                self.assertEqual(throw(self.no_back, geom, 3, field_role=role), throw(self.full, geom, 3, field_role=role),
                                 (name, role))
        for name, geom in PAST.items():
            for role in (HB, FB, WR, TE):
                self.assertEqual(throw(self.no_back, geom, 1, field_role=role),
                                 throw(self.full, geom, 1, field_role=role), (name, role))

    def test_screen_back_drifting_back_is_aimed_at_his_spot(self):
        from nfl2k5_qb_accuracy_native import screen_target
        spot = (11., -1.5)
        drifting = ((11., -1.5), (-1., -2.5)), ((10.5, -1.2), (.5, -1.5)), ((9., -1.), (-2., -3.))
        for position, velocity in drifting:
            old = screen_target(self.retail, position, velocity, spot=spot, due=0.)
            new = screen_target(self.no_back, position, velocity, spot=spot, due=0.)
            self.assertAlmostEqual(new["aim"][0], spot[0], delta=.05, msg=(position, velocity))
            self.assertAlmostEqual(new["aim"][1], spot[1], delta=.05)
            self.assertGreater(math.hypot(old["aim"][0] - new["aim"][0], old["aim"][1] - new["aim"][1]), .5)
            hb = screen_target(self.full, position, velocity, spot=spot, due=0., field_role=HB)
            self.assertAlmostEqual(hb["aim"][0], spot[0], delta=.05)
            self.assertAlmostEqual(hb["aim"][1], spot[1], delta=.05)            # a halfback: exactly his spot
        others = (((4., -4.5), (7., 2.), (11., -1.5), 1.), ((11., -1.5), (7., .5), spot, 0.),
                  ((13., -1.3), (7., .5), spot, -.3), ((11., -1.5), (0., 0.), spot, 0.),
                  ((11., -1.5), (6., -.3), spot, 0.))                            # lateral with a slight drift: retail
        for position, velocity, s, due in others:
            self.assertEqual(screen_target(self.retail, position, velocity, spot=s, due=due),
                             screen_target(self.no_back, position, velocity, spot=s, due=due), (position, velocity))
        # without the drift piece the drifting back gets retail's lead again
        position, velocity = drifting[0]
        self.assertEqual(screen_target(self.retail, position, velocity, spot=spot, due=0.),
                         screen_target(self.no_screen, position, velocity, spot=spot, due=0.))

    def test_caves_preserve_registers(self):
        """At the cave's exits (0x22683D route path, 0x226A62 shortcut; 0x2DAE5C after the back offset) every register
        the retail code continues with, and the x87 stack depth, equal their values at the hooked instruction."""
        from nfl2k5_qb_accuracy_native import screen_target
        names = ("EAX", "ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI")
        log = []

        def hook(uc, address, _size, _user):
            log.append((address, tuple(uc.reg_read(getattr(x86, "UC_X86_REG_" + r)) for r in names),
                        (uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7))
        for va in (0x226837, 0x22683D, 0x226A62, 0x2DAE12, 0x2DAE5C):
            self.full.uc.hook_add(unicorn.UC_HOOK_CODE, hook, begin=va, end=va)
        pairs = 0
        for position, velocity in (((11., -1.5), (-1., -2.5)), ((11., -1.5), (7., .5)), ((11., -1.5), (0., 0.))):
            log.clear()
            screen_target(self.full, position, velocity, spot=(11., -1.5), due=0., field_role=HB)
            for (a, ra, ta), (b, rb, tb) in zip(log, log[1:]):
                if a == 0x226837 and b in (0x22683D, 0x226A62):
                    self.assertEqual((ra, ta), (rb, tb))
                    pairs += 1
        for geom in BEHIND.values():
            log.clear()
            throw(self.full, geom, 1, field_role=HB)
            for (a, ra, ta), (b, rb, tb) in zip(log, log[1:]):
                if a == 0x2DAE12 and b == 0x2DAE5C:
                    self.assertEqual((ra[1:], ta), (rb[1:], tb))           # EAX is reloaded by retail at 0x2DAE5C
                    pairs += 1
        self.assertGreaterEqual(pairs, 3 + len(BEHIND))

if __name__ == "__main__":
    unittest.main()
