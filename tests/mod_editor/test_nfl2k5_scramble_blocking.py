"""Receivers block for a scrambling QB (nfl2k5_scramble_blocking, b780 cv7): exact bytes, wiring, and native replays.

Public tests read the committed byte template only (no GNU as, no retail data). Private tests load the pinned USA
default.xbe (NFL2K5_RETAIL_EXTRACTION, as the kickoff tests do) and run the installed hook in Unicorn: the AI tick's
first instruction calls the owner, which calls the game's own block installer 0x23F450, selector 0x2FAFF0, refresh
0x23CD60 and drive-block tick 0x23CE70. Players, teams and the ball are synthetic fixtures (the kickoff machine's).
Set NFL2K5_V08_XBE to the released SOFTDRINK v0.8 default.xbe to also replay the scene on top of every v0.8 owner.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_scramble_blocking as sb  # noqa: E402
from mod_editor.core import nfl2k5_scramble_blocking_code as template  # noqa: E402

YD = 91.44
CODE_VA, STATE_VA = 0x0150D9E0, 0x014FD660


def u32(raw, at):
    return struct.unpack_from("<I", raw, at)[0]


class TemplateTests(unittest.TestCase):
    def test_sizes_requests_and_labels(self):
        self.assertEqual(len(template.CODE), template.LABELS["code_end"])
        self.assertLessEqual(len(template.CODE), sb.CODE_SIZE)
        self.assertEqual(sb.CODE_SIZE % 16, 0)
        self.assertEqual(sb.REQUESTS, (("nfl2k5_scramble_blocking", "code", 816, 16),
                                       ("nfl2k5_scramble_blocking", "data", 16, 16)))
        self.assertEqual(template.LABELS["tick"], 0)
        for name in ("refresh", "convert", "dedupe", "claimed", "nearest", "half_yard", "three_yards", "infinity"):
            self.assertIn(name, template.LABELS)
        self.assertEqual(struct.unpack_from("<f", template.CODE, template.LABELS["half_yard"])[0],
                         struct.unpack("<f", struct.pack("<f", sb.PAST_LINE_CM))[0])
        self.assertAlmostEqual(struct.unpack_from("<f", template.CODE, template.LABELS["three_yards"])[0], 274.32, 3)
        self.assertEqual(template.CODE[template.LABELS["infinity"]:template.LABELS["infinity"] + 4], b"\x00\x00\x80\x7f")

    def test_relocation_at_two_addresses(self):
        for code_va, state_va in ((CODE_VA, STATE_VA), (0x014DA000, 0x014F2000)):
            code = sb.code_for(code_va, state_va)
            self.assertEqual(len(code), sb.CODE_SIZE)
            self.assertEqual(code[len(template.CODE):], b"\xcc" * (sb.CODE_SIZE - len(template.CODE)))
            calls = {}
            for off, kind, symbol, value in template.RELOCATIONS:
                field = u32(code, off)
                if kind == 2:
                    calls.setdefault(symbol, set()).add((code_va + off + 4 + field) & 0xFFFFFFFF)
                elif symbol == "state":
                    self.assertEqual(field, state_va)
                else:
                    self.assertTrue(code_va <= field < code_va + len(template.CODE), hex(field))
            self.assertEqual(calls, {"installer": {0x23F450}, "native_refresh": {0x23CD60}, "engaged": {0x231EE0}})
            # the refresh pointer the converted tasks get is the owner's own refresh label
            at = code.index(bytes.fromhex("c780a0000000"))
            self.assertEqual(u32(code, at + 6), code_va + template.LABELS["refresh"])

    def test_gate_and_install_bytes(self):
        code = sb.code_for(CODE_VA, STATE_VA)
        for needle in ("833db802e6000e",          # play state 14
                       "833dc002e60002",          # ball state 2 (held)
                       "807d2c00",                # holder field role 0 (the retail slide test)
                       "83bbb001000000",          # no forward pass thrown (CTX+0x1B0)
                       "83e80883f803",            # field roles 8..11
                       "8338ff",                  # CPU-controlled ([[P+0xC]] == -1)
                       "83b89000000005",          # already blocking (task+0x90 == 5)
                       "81a020040000ffbffbff",    # AI+0x420 &= 0xFFFBBFFF, as 0x23A010 / 0x23B040
                       "83a08c010000f8",          # L+0x18C &= ~7
                       "680000807f526848e136436a006a016a006a0031d2"):   # (0, 0, 1, 0, 182.88, heading, +inf), EDX 0
            self.assertIn(bytes.fromhex(needle), code, needle)
        self.assertEqual(code[-1:], b"\xcc")

    def test_hook_site(self):
        rows = sb.sites(CODE_VA)
        self.assertEqual(len(rows), 1)
        name, va, before, after = rows[0]
        self.assertEqual((name, va, before), ("ai_tick", 0x214FC0, bytes.fromhex("a1b802e600")))
        self.assertEqual(after[0], 0xE8)
        self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], CODE_VA)
        # the displaced instruction runs at the end of tick, right before its RET
        code = sb.code_for(CODE_VA, STATE_VA)
        self.assertIn(bytes.fromhex("61a1b802e600c3"), code)

    def test_help_text_and_wiring(self):
        from mod_editor.core import mod_build, nfl2k5_build_settings as settings, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_throw_tuning as tt
        self.assertNotIn("—", sb.HELP_TEXT + sb.BUILD_CAPTION)
        self.assertNotIn("–", sb.HELP_TEXT + sb.BUILD_CAPTION)
        self.assertIn("Off in every preset", sb.HELP_TEXT)
        self.assertIn("(test)", sb.BUILD_CAPTION)
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).scramble_blocking, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["scramble_blocking"], False, name)
        self.assertIn("scramble_blocking", settings.FEATURE_KEYS)
        self.assertIn(("nfl2k5_scramble_blocking", "Receivers block for a scrambling QB"),
                      [(m, label) for m, label, _ in mod_build._LATE_OWNER_OPTIONS])
        self.assertEqual(space.LATE_OWNERS[-1], sb.OWNER)
        self.assertEqual(tt._selected_space_requests(scramble_blocking=True)[-2:], sb.REQUESTS)
        self.assertNotIn(sb.REQUESTS[0], tt._selected_space_requests())
        panel = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("scramble_blocking", _scramble_blocking.BUILD_CAPTION, _scramble_blocking.HELP_TEXT)', panel)

    def test_synthetic_input_is_foreign(self):
        self.assertEqual(sb.status(b"XBEH" + bytes(0x1000)), "foreign")
        with self.assertRaises(sb.ScrambleBlockingError):
            sb.apply(b"XBEH" + bytes(0x1000))


try:
    from tests.mod_editor.test_nfl2k5_dynamic_kickoff import RETAIL, PRIVATE_REASON, uni, x86, Cs
    from mod_editor.core import nfl2k5_dynamic_kickoff as dk
except Exception:  # pragma: no cover - the kickoff fixture needs its optional imports
    RETAIL, PRIVATE_REASON, uni, x86, Cs, dk = Path("/nonexistent"), "kickoff fixture unavailable", None, None, None, None
V08 = Path(os.environ.get("NFL2K5_V08_XBE", "/nonexistent/default.xbe"))
_PRIVATE = RETAIL.is_file() and uni is not None and Cs is not None

if _PRIVATE:
    from tests.mod_editor.test_nfl2k5_kickoff_v2 import NativeMachine
else:  # pragma: no cover
    NativeMachine = object


class ScrambleMachine(NativeMachine):
    """The kickoff machine as a scrimmage down: the "receiving" team is the offense, the "kicking" team the defense.

    The offense moves toward -direction * z (the machine's team direction floats). The quarterback (field role 0) is
    the RETURNER, the first receiver the BLOCKER, others are clones of him; defenders are the kickoff coverage list
    (KICKER first). Each receiver starts in a route task the way a play script leaves him (0x2C9AB0, then callback
    0x1AEF80, the scripted path mover)."""

    RECEIVERS = ((9, -15, 8), (9, 15, 10), (8, -4, 6), (10, 3, 2))           # (field role, x yd, yd past the line)
    DEFENDERS = ((18, -15, 10), (18, 15, 12), (14, -3, 8), (16, 0, 18), (15, 5, 4))

    def __init__(self, payload, *, direction=1, qb_past=1.0, receivers=None, defenders=None, los=0.0):
        super().__init__(payload, direction=direction, phase=4)
        self.sign = -direction
        self.code, self.state = sb._allocations(payload)
        self.offense, self.defense = self.RECEIVE_TEAM, self.KICK_TEAM
        self.put(dk.PLAY_STATE, 14); self.put(0xE602C0, 2)
        self.put(dk.POSSESSION, self.offense); self.put(0xE60284, self.defense); self.put(0xE60288, self.offense)
        self.f32(self.CTX + 0x18, los * YD); self.put(self.CTX + 0x1B0, 0)
        self.los = los
        self.qb = self.RETURNER
        self.uc.mem_write(self.qb + 0x2C, bytes([0, 0]))
        self.receivers = []
        for i, (role, x, d) in enumerate(receivers or self.RECEIVERS):
            who = self.BLOCKER if i == 0 else self.clone(self.BLOCKER, 0x2030000 + i * 0x1000, 1 + i)
            self.uc.mem_write(who + 0x2C, bytes([role, role]))
            self.uc.mem_write(who + 0x2E, bytes([1 + i]))
            self.place(who, x * YD, self.sign * (los + d) * YD)
            self.receivers.append(who)
        squad = [self.qb] + self.receivers
        for a, b in zip(squad, squad[1:] + [0]):
            self.put(a + 0x34, b)
        self.put(self.offense + 4, self.qb)
        rows = [(x * YD, self.sign * (los + d) * YD, 0, 0) for _r, x, d in (defenders or self.DEFENDERS)]
        self.defenders = self.coverage(rows)
        for (role, _x, _d), who in zip(defenders or self.DEFENDERS, self.defenders):
            self.uc.mem_write(who + 0x2C, bytes([role, role]))
        self.uc.mem_write(self.KICKER + 0x2C, bytes([17, 17]))
        self.place(self.KICKER, 0, self.sign * (los + 25) * YD)
        self.carry(qb_past)
        for who in self.receivers:
            self.route(who)

    def carry(self, past_yd, holder=None):
        holder = holder or self.qb
        z = self.sign * (self.los + past_yd) * YD
        self.place(holder, 0, z)
        self.position(0, z, holder=holder)

    def route(self, who):
        ai = self.get(who + 0x20)
        self.run(0x2C9AB0, ecx=ai, budget=50_000)
        self.put(self.get(ai + 0x310), 0x1AEF80)

    def task(self, who):
        return self.get(self.get(who + 0x20) + 0x310)

    def tick(self):
        self.run(0x214FC0, stop=0x214FC5, budget=4_000_000)
        assert self.uc.reg_read(x86.UC_X86_REG_EAX) == self.get(dk.PLAY_STATE)

    def refresh(self, who):
        self.run(self.code["va"] + sb.labels()["refresh"], ecx=who, budget=2_000_000)

    def mask(self):
        return self.get(self.state["va"])

    def snapshot(self):
        return [(self.get(self.task(p)), self.get(self.task(p) + 0x40), self.get(self.task(p) + 0x90))
                for p in self.receivers]


@unittest.skipUnless(_PRIVATE, PRIVATE_REASON + "; unicorn and capstone also required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.payload, cls.receipt = sb.apply(cls.retail)

    def machine(self, payload=None, **kw):
        return ScrambleMachine(payload or self.payload, **kw)

    def assert_converted(self, m, players=None):
        players = m.receivers if players is None else players
        refresh = m.code["va"] + sb.labels()["refresh"]
        targets = []
        for who in players:
            task = m.task(who)
            self.assertEqual(m.get(task), 0x23CE70, hex(who))          # the game's drive block
            self.assertEqual(m.get(task + 0x90), 5)                     # the game's block-task marker
            self.assertEqual(m.get(task + 0xA0), refresh)                # one blocker per man on every refresh
            self.assertEqual(m.readf(task + 0x60), float("inf"))         # no time limit, as 0x23A010
            self.assertIn(m.get(task + 0x40), m.defenders + [m.KICKER])
            self.assertEqual(m.get(m.get(who + 0x20) + 0x420) & 0x44000, 0)
            targets.append(m.get(task + 0x40))
        self.assertEqual(len(set(targets)), len(targets), "two receivers block the same man")
        return targets

    def test_apply_replay_and_refusal(self):
        self.assertEqual(sb.status(self.retail), "retail")
        self.assertEqual(sb.status(self.payload), "applied")
        again, receipt = sb.apply(self.payload)
        self.assertEqual((again, receipt["status"]), (self.payload, "already_applied"))
        self.assertEqual(self.receipt["edits"], [dict(label="ai_tick", va="0x214fc0", before="a1b802e600",
                                                      after=sb.sites(int(self.receipt["code_va"], 16))[0][3].hex())])
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        for va, size, _digest in sb.GUARDS[:2]:
            image = XbeImage(self.retail)
            off = image.offset(va + 0x10, 1)
            foreign = bytearray(self.retail); foreign[off] ^= 0xFF
            foreign = bytes(foreign)
            self.assertEqual(sb.status(foreign), "foreign")
            with self.assertRaises(sb.ScrambleBlockingError):
                sb.apply(foreign)
        off = XbeImage(self.payload).offset(0x214FC0 + 1, 1)
        mixed = bytearray(self.payload); mixed[off] ^= 1
        self.assertEqual(sb.status(bytes(mixed)), "foreign")

    def test_receivers_and_backs_convert_once_with_distinct_targets_both_directions(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                m = self.machine(direction=direction)
                m.tick()
                self.assert_converted(m)
                self.assertEqual(m.mask(), 0b11110)                      # formation slots 1..4
                before = m.snapshot()
                m.tick()
                self.assertEqual(m.snapshot(), before)                   # nothing changes on the next step
                for who in m.receivers:                                  # the game's drive tick asks for movement
                    m.run(0x23CE70, ecx=who, budget=3_000_000)
                    self.assertGreater(m.readf(m.get(who + 0xC) + 0x10), 0.0)
                    self.assertEqual(m.get(m.task(who)), 0x23CE70)

    def test_nothing_changes_outside_the_gate(self):
        cases = {
            "short of half a yard": lambda m: m.carry(0.45),
            "behind the line": lambda m: m.carry(-3.0),
            "forward pass in the air": lambda m: m.put(0xE602C0, 4),
            "backward pass in the air": lambda m: m.put(0xE602C0, 3),
            "a pass was thrown on the play": lambda m: m.put(m.CTX + 0x1B0, m.qb),
            "the holder is a receiver": lambda m: m.uc.mem_write(m.qb + 0x2C, b"\x09"),
            "a kickoff": lambda m: m.put(dk.PHASE, 2),
            "a safety kick": lambda m: m.put(dk.PHASE, 1),
            "the play is not live": lambda m: m.put(dk.PLAY_STATE, 13),
            "no holder": lambda m: m.put(m.BALL, 0),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                m = self.machine()
                change(m)
                before = m.snapshot()
                m.tick()
                self.assertEqual(m.snapshot(), before)
                self.assertEqual(m.mask(), 0)
        m = self.machine()
        m.put(dk.PHASE, 3)                                               # a try after a touchdown (2-point play)
        m.tick()
        self.assert_converted(m)

    def test_only_cpu_receivers_and_backs_who_are_free_convert(self):
        m = self.machine()
        wr1, wr2, te, hb = m.receivers
        m.uc.mem_write(wr2 + 0x2C, b"\x07")                              # a guard (offensive line) is never converted
        m.put(m.get(te + 0xC), 0)                                        # a human-controlled teammate
        m.put(m.task(hb) + 0x90, 5)                                      # already in a block task: left alone
        engaged = m.get(wr1 + 0x10)
        descriptor = m.get(engaged + 4)
        m.put(engaged + 4, 0x510460)                                     # engaged pair (0x231EE0 range)
        before = m.snapshot()
        m.tick()
        self.assertEqual(m.snapshot(), before)
        self.assertEqual(m.mask(), 0)
        m.put(engaged + 4, descriptor)                                   # the jam ends: he converts on the next step
        m.tick()
        self.assert_converted(m, [wr1])
        self.assertEqual(m.mask(), 1 << 1)
        self.assertEqual(m.snapshot()[1:], before[1:])

    def test_once_a_play_and_rearmed_by_the_next_play(self):
        m = self.machine()
        m.tick()
        self.assert_converted(m)
        wr1 = m.receivers[0]
        m.route(wr1)                                                     # the game ends his block (the runner passed)
        m.tick()
        self.assertEqual(m.get(m.task(wr1)), 0x1AEF80)                   # never re-armed on the same play
        m.put(dk.PLAY_STATE, 13); m.tick()                               # dead ball / the next lineup
        self.assertEqual(m.mask(), 0)
        m.put(dk.PLAY_STATE, 14); m.tick()                               # the next live play
        self.assert_converted(m, [wr1])

    def test_one_blocker_per_man_at_install_and_on_refresh(self):
        # Control: the game's own conversion alone (0x23A010's call, made directly, so the owner never runs) with the
        # field flipped sends the left receiver and the tight end to the same linebacker.
        m = self.machine(direction=-1)
        native = []
        for who in m.receivers:
            heading = 0x8000 if m.readf(m.get(m.get(m.get(who + 0x38) + 8) + 0xC) + 4) <= 0 else 0
            m.run(0x23F450, ecx=who, edx=0, args=(0, 0, 1, 0, 0x4336E148, heading, 0x7F800000), budget=3_000_000)
            native.append(m.get(m.task(who) + 0x40))
        self.assertLess(len(set(native)), len(native), "the fixture no longer shows the game's double team")
        # The owner on the same scene: distinct men.
        m = self.machine(direction=-1)
        m.tick()
        targets = self.assert_converted(m)
        # A refresh can never leave two of them on one man: force the second receiver onto the first one's man.
        first, second = m.receivers[0], m.receivers[1]
        m.put(m.task(second) + 0x40, targets[0])
        m.refresh(second)
        self.assert_converted(m)
        for who in m.receivers:                                          # and a full refresh round stays distinct
            m.refresh(who)
        self.assert_converted(m)
        self.assertIsNot(first, second)
        # one defender only: nobody else is free, so the game's choice stands (a shared man beats no block)
        m = self.machine(defenders=((14, 0, 6),), receivers=((9, -3, 7), (9, 3, 7)))
        m.tick()
        tasks = [m.task(p) for p in m.receivers]
        self.assertEqual({m.get(t) for t in tasks}, {0x23CE70})
        self.assertEqual({m.get(t + 0x40) for t in tasks} - {m.defenders[0], m.KICKER}, set())

    def test_fallback_skips_defenders_far_behind_the_ball(self):
        # Two receivers, one free man in front, one far behind the quarterback: the second receiver whose game
        # choice is taken gets the free man in front, never the one 6 yards behind the ball.
        m = self.machine(receivers=((9, -2, 6), (9, 2, 6)), defenders=((14, 0, 8), (12, 0, -5), (18, 12, 9)))
        m.tick()
        targets = self.assert_converted(m)
        self.assertNotIn(m.defenders[1], targets)

    @unittest.skipUnless(V08.is_file(), "set NFL2K5_V08_XBE to the released SOFTDRINK v0.8 default.xbe")
    def test_on_the_released_v08_executable(self):
        v08 = V08.read_bytes()
        self.assertEqual(hashlib.sha256(v08).hexdigest()[:8], "5f987568")
        payload, receipt = sb.apply(v08)
        self.assertEqual(receipt["file_growth"], 0)
        self.assertEqual(sb.status(payload), "applied")
        for direction in (1, -1):
            with self.subTest(direction=direction):
                m = ScrambleMachine(payload, direction=direction)
                r = ScrambleMachine(self.payload, direction=direction)
                m.tick(); r.tick()
                self.assert_converted(m)
                self.assertEqual([t[1] for t in m.snapshot()], [t[1] for t in r.snapshot()])


if __name__ == "__main__":
    unittest.main()
