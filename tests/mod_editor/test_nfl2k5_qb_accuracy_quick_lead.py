"""QB accuracy owner, b777 qb4 quick-throw placement, native: the game's own lead solver 0x2DA8E0 (and accuracy,
launch, flight) on supplied quick and longer routes.

The retail solver moves the target 1.5 yd (137.16 cm) sideways off a moving receiver's path, toward the QB side,
whenever he runs within 45 degrees of the throw line: quick outs, flats and bubbles arrive underneath him. The owner
scales that offset by the target's depth past the line (none to 8 yd and behind the line, retail from 10 yd).
Compared here: the owner with the placement tail put back to retail ("qb3") against the full owner ("qb4").
Proves: quick outs, flats and bubbles land on the receiver's path; slants, hitches and drags (never offset) and
every intermediate and deep route are byte-for-byte unchanged; the 8-10 yd band fades; registers and the x87 stack
match retail at 0x2DADBB. Skipped without the pinned retail XBE.
"""
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_qb_accuracy as accuracy
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe

try:
    import unicorn
except ImportError:  # pragma: no cover
    unicorn = None

QB = (0., -400. / 91.44)          # the fixture's QB spot (yd) when the route is laid out
QUICK_OFFSET = {"qout2": (7., 2., 7.0, -0.5), "qout5": (8., 5., 7.0, -0.5), "qout7": (10., 7., 7.0, -0.5),
                "qout5_left": (-8., 5., -7.0, -0.5), "flat1": (2., 1., 7., 1.), "flat3": (4., 2., 7., 0.5),
                "bubble": (9., -1., 2.5, 2.5)}
QUICK_NO_OFFSET = {"slant3": (-10., 2., 5.5, 5.5), "slant5": (-10., 4., 5.5, 5.5), "slant8": (9., 7., -5.5, 5.5),
                   "hitch5": (15., 5., 0., 0.), "drag3": (-4., 3., 7.5, 0.)}
LONGER = {"out10": (10., 10., 7.0, -0.5), "out12_wide": (14., 11., 7.0, -0.3), "out14": (12., 14., 7.0, -0.5),
          "dig12": (-8., 12., 7.5, 0.), "curl10": (8., 10., 0., -1.), "seam20": (-6., 20., 0., 9.),
          "go30": (14., 30., 0., 9.5), "post25": (-10., 25., 4., 8.), "fade18": (16., 14., 1., 8.5),
          "wheel20": (12., 16., 1.5, 8.5), "corner18": (8., 14., 5., 6.)}
STATES = (("set", 7), ("roll_human", 7), ("roll_human", 23), ("roll_cpu", 7), ("roll_cpu", 23))


def off_path(row, geom):
    """Sideways distance (yd) of the aim from the receiver's path at arrival; positive = toward the QB side."""
    _x, _z, vx, vz = geom
    speed = math.hypot(vx, vz)
    ux, uz = vx / speed, vz / speed
    wx, wz = row["receiver"]
    px, pz = -uz, ux
    if (QB[0] - wx) * px + (QB[1] - wz) * pz < 0:
        px, pz = -px, -pz
    return (row["aim"][0] - wx) * px + (row["aim"][1] - wz) * pz


@unittest.skipIf(unicorn is None, "unicorn is required for the native probe")
class QuickLeadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_qb_accuracy_native import AccuracyMachine, ROUTES
        from test_nfl2k5_qb_accuracy_unicorn import without_quick_lead
        ROUTES.update(QUICK_OFFSET, **QUICK_NO_OFFSET, **LONGER, qout9=(10., 9., 7.0, -0.5))
        applied = accuracy.apply(retail_xbe())[0]
        cls.qb3 = AccuracyMachine(without_quick_lead(applied))
        cls.qb4 = AccuracyMachine(applied)
        cls.exits = {}
        for name, machine in (("qb3", cls.qb3), ("qb4", cls.qb4)):
            machine.uc.hook_add(unicorn.UC_HOOK_CODE, cls._exit(name), begin=0x2DADBB, end=0x2DADBB)
        cls.rows = {}
        for route in list(QUICK_OFFSET) + list(QUICK_NO_OFFSET) + list(LONGER) + ["qout9"]:
            for state, seed in STATES:
                cls.exits.clear()
                pair = tuple(m.throw(route, state=state, accuracy=.85, seed=seed) for m in (cls.qb3, cls.qb4))
                cls.rows[(route, state, seed)] = pair + (dict(cls.exits),)

    @classmethod
    def _exit(cls, name):
        from unicorn import x86_const as x86

        def hook(uc, _address, _size, _user):
            regs = {r: uc.reg_read(getattr(x86, "UC_X86_REG_" + r)) for r in ("ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI")}
            cls.exits[name] = dict(regs=regs, top=(uc.reg_read(x86.UC_X86_REG_FPSW) >> 11) & 7,
                                   tag=uc.reg_read(x86.UC_X86_REG_FPTAG))
        return hook

    def test_quick_outs_flats_and_bubbles_land_on_the_receivers_path(self):
        for route, geom in QUICK_OFFSET.items():
            for state, seed in STATES:
                old, new, _ = self.rows[(route, state, seed)]
                before, after = off_path(old, geom), off_path(new, geom)
                if state == "set":
                    self.assertAlmostEqual(before, 1.5, delta=0.02, msg=route)        # retail: 1.5 yd underneath
                    self.assertLess(abs(after), 0.02, route)                          # now on his path
                    self.assertLess(new["miss_yd"], 0.7, route)
                self.assertLess(abs(after), abs(before) - 0.9, (route, state, seed))
                self.assertEqual(old["flight_s"] > 0, new["flight_s"] > 0)

    def test_routes_without_the_offset_and_all_longer_routes_are_unchanged(self):
        for route in list(QUICK_NO_OFFSET) + list(LONGER):
            for state, seed in STATES:
                old, new, _ = self.rows[(route, state, seed)]
                self.assertEqual(old["raw"], new["raw"], (route, state, seed))
                self.assertEqual(old["launch"], new["launch"], (route, state, seed))
                self.assertEqual(old["aim"], new["aim"], (route, state, seed))

    def test_eight_to_ten_yard_band_fades(self):
        old, new, _ = self.rows[("qout9", "set", 7)]
        geom = (10., 9., 7.0, -0.5)
        self.assertAlmostEqual(off_path(old, geom), 1.5, delta=0.02)
        self.assertTrue(0.3 < off_path(new, geom) < 1.2, off_path(new, geom))

    def test_screen_targets_keep_qb3s_lead(self):
        from nfl2k5_qb_accuracy_native import screen_target
        for position, velocity in (((4., -4.5), (7., 2.)), ((6., -3.), (6., 2.)), ((9., -2.), (4., 1.)),
                                   ((8., -2.6), (7., 0.)), ((2.5, -5.3), (0., 0.))):
            self.assertEqual(screen_target(self.qb3, position, velocity), screen_target(self.qb4, position, velocity))

    def test_registers_and_x87_match_at_the_resume(self):
        checked = 0
        for key, (_old, _new, exits) in self.rows.items():
            if set(exits) != {"qb3", "qb4"}:
                continue
            a, b = exits["qb3"], exits["qb4"]
            self.assertEqual(a["top"], b["top"], key)
            self.assertEqual(a["tag"], b["tag"], key)
            for name in ("ECX", "EDX", "EBX", "ESP", "EBP", "ESI", "EDI"):
                self.assertEqual(a["regs"][name], b["regs"][name], (key, name))
            checked += 1
        self.assertGreater(checked, 40)


if __name__ == "__main__":
    unittest.main()
