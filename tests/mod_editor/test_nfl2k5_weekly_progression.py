"""b778 pg1: franchise in-season weekly progression (nfl2k5_weekly_progression).

The installed cave runs in Unicorn on the patched retail executable with the per-player merge 0x1334B0 and the
current-season stat reader 0x14EE40 mocked (the merge adds one game's line); every player record must come out
exactly as the documented rule says. Also: exact hook bytes, foreign refusal, the plain path in other modes,
callee-saved registers and stack, presets and late-owner order. The pinned USA retail default.xbe is read from
NFL2K5_RETAIL_EXTRACTION (skipped when absent).
"""
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_progression as prog
from mod_editor.core import nfl2k5_weekly_progression as wp
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit

try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:  # pragma: no cover
    uc = x86 = None

WORLD, STACK, SENTINEL = 0x03000000, 0x03800000, 0x03F00000
SAVED = ("EBX", "EBP", "ESI", "EDI")


def model(rec, ptr, week, line, played, *, league=2, stage=8):
    """The documented rule, in Python: returns the record after this game's weekly step."""
    out = bytearray(rec)
    pos = rec[0x35]
    if league != wp.LEAGUE_FRANCHISE or stage != wp.STAGE_REGULAR or pos > 16:
        return bytes(out)
    cls = prog.CLASS_OF[prog.POSITIONS[pos]]
    fields, kind, good, poor, young_max, old_from, keys = wp.RULES[cls]
    if kind == wp.KIND_NONE or rec[0x23] & 0x80:
        return bytes(out)
    d = [line.get(f, 0) for f in fields] + [0] * (4 - len(fields))
    verdict = 0
    if played <= 0:
        verdict = -1
    elif kind == wp.KIND_PLAYED:
        verdict = 1
    else:
        if kind == wp.KIND_QB:
            if d[0] < wp.QB_MIN_ATTEMPTS:
                value = None
            else:
                value = int((d[1] + 20 * d[2] - 45 * d[3]) * 10 / d[0])
        else:
            value = d[0] + d[1]
        if value is not None:
            verdict = 1 if value >= good else -1 if value <= poor else 0
    years = (struct.unpack_from("<I", rec, 0x24)[0] >> 8) & 31
    h = ((ptr >> 2) + week) & 0xFFFFFFFF
    if verdict == 1 and years <= young_max and not h & wp.GOOD_MASK:
        for k in keys:
            if out[k] < 100:
                out[k] += 1
    elif verdict == -1 and years >= old_from and not h & wp.OLD_MASK:
        if out[wp.SPEED]:
            out[wp.SPEED] -= 1
        if pos != 0:
            other = wp.STAMINA if h & 4 else wp.AGILITY
            if out[other]:
                out[other] -= 1
    return bytes(out)


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, cls.receipt = wp.apply(cls.retail)

    def test_states_hook_and_replay(self):
        self.assertEqual(wp.status(self.retail), "retail")
        self.assertEqual(wp.status(self.applied), "applied")
        self.assertEqual(wp.apply(self.applied)[0], self.applied)
        code_va = int(self.receipt["code_va"], 16)
        image = XbeImage(self.applied)
        self.assertEqual(image.read(0x134E05, 5), b"\xe8" + struct.pack("<i", code_va - 0x134E0A))
        self.assertEqual(image.read(code_va, wp.CODE_SIZE), wp.code_for(code_va))
        self.assertEqual(self.receipt["file_growth"] % 0x1000, 0)
        self.assertEqual(len(wp.code_for(code_va).rstrip(b"\xcc")) <= wp.CODE_SIZE, True)

    def test_foreign_prerequisite_is_refused(self):
        bad = repin_edit(self.retail, 0x14EE45, b"\x90")
        self.assertEqual(wp.status(bad), "foreign")
        with self.assertRaises(wp.WeeklyProgressionError):
            wp.apply(bad)

    def test_presets_options_and_late_owner_order(self):
        # b778-int2: xs1's on-demand module loader is the last late owner; weekly progression sits before it.
        self.assertEqual(space.LATE_OWNERS[-3:], (wp.OWNER, "nfl2k5_player_progress_screen", "nfl2k5_module_loader"))
        self.assertIs(mod_build.BuildPlan(Path("source.iso"), Path("target.iso")).weekly_progression, False)
        for name, preset in mod_build.PRESETS.items():
            self.assertIs(preset["weekly_progression"], False, name)    # off until the second scale-out lands
        self.assertIn("weekly_progression", settings.FEATURE_KEYS)
        self.assertIn((wp.OWNER, "Weekly player progression"),
                      [(owner, label) for owner, label, _ in mod_build._LATE_OWNER_OPTIONS])
        text = (ROOT / "mod_editor/core/nfl2k5_weekly_progression.py").read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("—", text)


@unittest.skipIf(uc is None, "unicorn is not installed")
class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.applied, receipt = wp.apply(cls.retail)
        cls.code_va = int(receipt["code_va"], 16)
        cls.profiles = prog._profiles(cls.retail)

    def emu(self):
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(self.applied)
        pages = sorted({va for s in image.sections for va in range(s.start & -4096, (s.start + s.size + 4095) & -4096, 4096)})
        start = prev = None
        for va in pages + [None]:
            if va is not None and prev is not None and va == prev + 4096:
                prev = va
                continue
            if start is not None:
                m.mem_map(start, prev + 4096 - start)
            start = prev = va
        for s in image.sections:
            if s.raw_size:
                m.mem_write(s.start, image.read(s.start, s.raw_size))
        for base, size in ((WORLD, 0x100000), (STACK, 0x100000), (SENTINEL, 0x1000)):
            m.mem_map(base, size)
        m.mem_write(SENTINEL, b"\xf4")
        self.now, self.line, self.merges = {}, {}, []

        def merge(mu, _a, _s, _d):           # 0x1334B0: add this game's line to the season totals; ret 8
            esp = mu.reg_read(x86.UC_X86_REG_ESP)
            ret, copy, club = struct.unpack("<III", mu.mem_read(esp, 12))
            player = mu.reg_read(x86.UC_X86_REG_EAX)
            self.merges.append((player, copy, club))
            for field, value in self.line.get(player, {}).items():
                self.now[(player, field)] = self.now.get((player, field), 0) + value
            mu.reg_write(x86.UC_X86_REG_ESP, esp + 12)
            mu.reg_write(x86.UC_X86_REG_EIP, ret)

        def stat(mu, _a, _s, _d):            # 0x14EE40(ecx = player, edx = field) -> this season's total
            esp = mu.reg_read(x86.UC_X86_REG_ESP)
            ret = struct.unpack("<I", mu.mem_read(esp, 4))[0]
            key = (mu.reg_read(x86.UC_X86_REG_ECX), mu.reg_read(x86.UC_X86_REG_EDX))
            mu.reg_write(x86.UC_X86_REG_EAX, self.now.get(key, 0) & 0xFFFFFFFF)
            mu.reg_write(x86.UC_X86_REG_ESP, esp + 4)
            mu.reg_write(x86.UC_X86_REG_EIP, ret)
            mu.reg_write(x86.UC_X86_REG_EDX, 0xDEAD)
        m.hook_add(uc.UC_HOOK_CODE, merge, begin=wp.FN_MERGE, end=wp.FN_MERGE)
        m.hook_add(uc.UC_HOOK_CODE, stat, begin=wp.FN_STAT_NOW, end=wp.FN_STAT_NOW)
        return m

    def run_merge(self, m, player, copy=0x11112222, club=0x33334444):
        esp = STACK + 0xFFF00 - 8
        m.mem_write(esp, struct.pack("<II", copy, club))         # the merge loop pushed esi (club) and ebx (copy)
        m.reg_write(x86.UC_X86_REG_ESP, esp)
        for i, name in enumerate(SAVED):
            m.reg_write(getattr(x86, f"UC_X86_REG_{name}"), 0x5A5A0000 + i)
        m.reg_write(x86.UC_X86_REG_EAX, player)
        m.emu_start(0x00134E05, 0x00134E0A, count=200000)    # the hooked call, back to the loop's next instruction
        self.assertEqual(m.reg_read(x86.UC_X86_REG_ESP), esp + 8)           # ret 8, as the retail merge
        self.assertEqual([m.reg_read(getattr(x86, f"UC_X86_REG_{n}")) for n in SAVED], [0x5A5A0000 + i for i in range(4)])

    def test_every_rule_against_the_model(self):
        rng = random.Random(9)
        lines = {"QB": lambda: {0: 1, 6: rng.choice((0, 10, 15, 30, 40)), 8: rng.randrange(0, 450), 9: rng.randrange(0, 5),
                                10: rng.randrange(0, 4)},
                 "default": lambda: {0: 1, 2: rng.randrange(0, 160), 13: rng.randrange(0, 140), 18: rng.randrange(0, 14),
                                     19: rng.randrange(0, 6), 20: rng.randrange(0, 2)}}
        checked = changed = 0
        for trial in range(1200):
            m = self.emu()
            league = rng.choice((2, 2, 2, 1, 0))
            stage = rng.choice((8, 8, 8, 7, 9))
            week = rng.randrange(0, 18)
            m.mem_write(0x00E576A0, struct.pack("<I", league))
            m.mem_write(0x00E576A4, struct.pack("<I", stage))
            m.mem_write(0x00E576B4, struct.pack("<I", week))
            from tests.mod_editor.test_nfl2k5_progression_careers import synthetic_player
            pos = rng.randrange(17)
            rec = bytearray(synthetic_player(rng, pos, self.profiles))
            if rng.random() < 0.1:
                rec[0x23] |= 0x80                                  # injured
            for off in (0x36, 0x37, 0x39, 0x42, 0x44):
                if rng.random() < 0.05:
                    rec[off] = rng.choice((0, 100))
            ptr = WORLD + 0x1000 + 0x54 * rng.randrange(0, 2000)
            m.mem_write(ptr, bytes(rec))
            line = (lines["QB"] if pos == 0 else lines["default"])()
            if rng.random() < 0.25:
                line[0] = 0                                        # dressed, did not play
            base = {f: rng.randrange(0, 900) for f in (0, 2, 6, 8, 9, 10, 13, 18, 19, 20)}
            self.now = {(ptr, f): v for f, v in base.items()}
            self.line = {ptr: line}
            self.run_merge(m, ptr)
            got = bytes(m.mem_read(ptr, 0x54))
            want = model(bytes(rec), ptr, week, line, line.get(0, 0), league=league, stage=stage)
            self.assertEqual(got, want, f"trial {trial} pos {pos} league {league} stage {stage} week {week} line {line}")
            self.assertEqual(len(self.merges), 1)                   # the retail merge runs exactly once, same args
            self.assertEqual(self.merges[0], (ptr, 0x11112222, 0x33334444))
            checked += 1
            changed += got != bytes(rec)
        self.assertGreater(changed, 15)


if __name__ == "__main__":
    unittest.main()
