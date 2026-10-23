"""The cornerback tackle tail: code shape, the NFL draw, the merge hook and coexistence with b778-pg1."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_sim_cb_tackles as cb  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
V061 = Path("/home/noah/2k-worktrees/.b77-scratch/b778/rh1/xbe/v061.xbe")
PG1 = Path(__file__).resolve().parent.parent / "fixtures" / "b778_pg1_weekly_progression.py"
HAVE_UC = importlib.util.find_spec("unicorn") is not None


def retail():
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


class CodeTests(unittest.TestCase):
    def test_code_fits_tables_are_16_bit_and_the_tail_replays_the_merge_head(self):
        code = cb.code_for(0x14E0000)
        self.assertEqual(len(code), cb.CODE_SIZE)
        body = code[:cb.TABLE_OFF].rstrip(b"\xcc")
        self.assertLessEqual(len(body), cb.TABLE_OFF)
        # the last instructions are the two displaced merge instructions and the return
        self.assertEqual(body[-7:], bytes.fromhex("618b45308b18c3"))
        self.assertEqual(code[cb.TABLE_OFF:cb.TABLE_OFF + len(cb.TABLES)], cb.TABLES)
        self.assertEqual(len(cb.TABLES), len(cb.LCB_CDF) + len(cb.RCB_CDF) + len(cb.NICKEL_CDF) + len(cb.DIME_CDF))
        for table in (cb.LCB_CDF, cb.RCB_CDF, cb.NICKEL_CDF, cb.DIME_CDF):
            self.assertEqual(table[-1], 128)
            self.assertEqual(list(table), sorted(table))
            self.assertEqual(len(set(table)), len(table))

    def test_site_is_the_merge_body_and_clear_of_the_pg1_call(self):
        name, va, before, after = cb.sites(0x14E0000)[0]
        self.assertEqual(name, "merge_body")
        self.assertEqual((va, before), (cb.SITE, cb.SITE_BEFORE))
        self.assertEqual(cb.SITE, 0x001334C3)
        self.assertEqual(cb.SITE + len(before), cb.RESUME)
        self.assertGreaterEqual(cb.SITE, 0x001334B0 + 0x10, "inside b778-pg1's guarded merge head")
        self.assertNotEqual(cb.SITE, 0x00134E05)
        self.assertEqual(after[:1], b"\xe8")
        self.assertEqual((va + 5 + struct.unpack_from("<i", after, 1)[0]) & 0xFFFFFFFF, 0x14E0000)

    def test_retail_is_recognised_without_writing(self):
        data = retail()
        if data is None:
            self.skipTest("pinned USA retail XBE is not available")
        self.assertEqual(cb.status(data), "retail")
        self.assertEqual(XbeImage(data).read(cb.SITE, len(cb.SITE_BEFORE)), cb.SITE_BEFORE)
        self.assertEqual(XbeImage(data).read(0x134E05, 5), cb.RETAIL_PG1_CALL)

    @unittest.skipUnless(V061.is_file(), "the released v0.6.1 extraction is not in this scratch")
    def test_released_v061_merge_context_is_supported(self):
        self.assertEqual(cb.status(V061.read_bytes()), "retail")

    def test_apply_is_idempotent_and_leaves_the_pg1_call_retail(self):
        data = retail()
        if data is None:
            self.skipTest("pinned USA retail XBE is not available")
        out, receipt = cb.apply(data)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(cb.status(out), "applied")
        self.assertEqual(XbeImage(out).read(0x134E05, 5), cb.RETAIL_PG1_CALL)
        again, second = cb.apply(out)
        self.assertEqual(again, out)
        self.assertEqual(second["status"], "already_applied")


def _fixture_asm_class():
    """b778-pg1's two-pass assembler (the fixture source imports it from its branch's progression module)."""
    class _Asm:
        def __init__(self, base):
            self.base, self.items, self.labels = base, [], {}

        def __call__(self, hexs):
            self.items.append(bytes.fromhex(hexs))

        def raw(self, data):
            self.items.append(bytes(data))

        def label(self, name):
            self.items.append(("label", name))

        def j8(self, opcode, label):
            self.items.append(("j8", bytes.fromhex(opcode), label))

        def j32(self, opcode, label):
            self.items.append(("j32", bytes.fromhex(opcode), label))

        def call(self, target):
            self.items.append(("call", target))

        def abs32(self, label, addend=0):
            self.items.append(("abs", label, addend))

        @staticmethod
        def _size(item):
            if isinstance(item, bytes):
                return len(item)
            if item[0] == "j32":
                return len(item[1]) + 4
            return {"label": 0, "j8": 2, "call": 5, "abs": 4}[item[0]]

        def assemble(self):
            pos = 0
            for item in self.items:
                if isinstance(item, tuple) and item[0] == "label":
                    if item[1] in self.labels:
                        raise ValueError(f"duplicate label {item[1]}")
                    self.labels[item[1]] = self.base + pos
                pos += self._size(item)
            out = bytearray()
            for item in self.items:
                here = self.base + len(out)
                if isinstance(item, bytes):
                    out += item
                elif item[0] == "j8":
                    rel = self.labels[item[2]] - (here + 2)
                    if not -128 <= rel <= 127:
                        raise ValueError(f"rel8 out of range to {item[2]}")
                    out += item[1] + struct.pack("<b", rel)
                elif item[0] == "j32":
                    out += item[1] + struct.pack("<i", self.labels[item[2]] - (here + len(item[1]) + 4))
                elif item[0] == "call":
                    target = self.labels[item[1]] if isinstance(item[1], str) else item[1]
                    out += b"\xe8" + struct.pack("<i", target - (here + 5))
                elif item[0] == "abs":
                    out += struct.pack("<I", (self.labels[item[1]] + item[2]) & 0xFFFFFFFF)
            return bytes(out)
    return _Asm


def load_pg1():
    """The real pg1 module when the merged tree has it, else its frozen source fixture (commit 688503675)."""
    try:
        from mod_editor.core import nfl2k5_weekly_progression as real
        return real
    except Exception:
        pass
    if not PG1.is_file():
        return None
    import mod_editor.core.nfl2k5_progression as progression
    if not hasattr(progression, "_Asm"):
        progression._Asm = _fixture_asm_class()
    if not hasattr(progression, "CLASSES"):
        progression.CLASSES = ("QB", "KP", "WR", "CB", "S", "RB", "FB", "TE", "LB", "OL", "DL")
        progression.CLASS_OF = {"QB": "QB", "K": "KP", "P": "KP", "WR": "WR", "CB": "CB", "FS": "S", "SS": "S",
                                "RB": "RB", "FB": "FB", "TE": "TE", "OLB": "LB", "ILB": "LB", "C": "OL", "G": "OL",
                                "T": "OL", "DT": "DL", "DE": "DL"}
    module = types.ModuleType("mod_editor.core._b778_pg1_fixture")
    module.__package__ = "mod_editor.core"
    exec(compile(PG1.read_text(encoding="utf-8"), str(PG1), "exec"), module.__dict__)
    return module


class DrawMachine:
    """A retail image, the owner's tail mapped in RAM, the game RNG seeded, and a synthetic CB."""

    WEEK = 8
    CODE = 0x14E0000

    def __init__(self):
        from tests.mod_editor.test_nfl2k5_honors import Machine, word
        data = retail()
        if data is None:
            raise unittest.SkipTest("pinned USA retail XBE is not available")
        self.m = Machine(data)
        self.m.uc.mem_write(self.m.ROOT, bytes(0x200))
        self.player = self.m.roster([(4, [word(0, 4, self.WEEK - 1)])])[0]
        self.m.put8(self.player + 0x35, 4)
        self.live = 0xB30C4C
        self.m.uc.mem_write(self.live, bytes(self.m.uc.mem_read(self.player, 0x54)))
        self.record = self.m.HEAP + 0x70000
        self.context = self.m.HEAP + 0x71000
        self.m.put(self.live + 0x30, self.record)
        self.m.put(self.record, self.context)
        self.m.uc.mem_write(self.context, bytes(0x200))
        self.m.uc.mem_write(0xE576B4, bytes([self.WEEK]))
        self.m.uc.mem_map(self.CODE, 0x1000)
        self.m.uc.mem_write(self.CODE, cb.code_for(self.CODE))
        self.seed_rng()

    def seed_rng(self, seed=0x12345678):
        state = 0xB12680
        self.m.put(state, 54)
        self.m.put(state + 4, 0)

        def splitmix(x):
            x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
            z = x
            z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
            z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
            return z ^ (z >> 31)

        for k in range(55):
            seed = splitmix(seed)
            self.m.uc.mem_write(state + 8 + 8 * k, struct.pack("<Q", seed))

    def role(self, rank, side=2):
        self.m.put(self.player + 0x28, (rank & 7) << 10 | (side & 7) << 13)
        self.m.put8(self.player + 0x35, 4)

    def position(self, position):
        self.m.put8(self.player + 0x35, position)

    def games(self, games):
        self.m.call(0x14F430, ecx=self.player, edx=0, stack=(games,))

    def run(self):
        sp = self.m.SP - 4
        self.m.put(sp, self.m.STOP)
        self.m.reg("ESP", sp)
        self.m.reg("EAX", self.player)
        self.m.reg("EBP", self.live)
        self.m.reg("EDI", self.player)
        for name in ("EBX", "ECX", "EDX", "ESI"):
            self.m.reg(name, 0)
        self.m.uc.emu_start(self.CODE, self.m.STOP, count=200_000)
        if self.m.reg("EIP") != self.m.STOP:
            raise AssertionError(f"tail did not return: {self.m.reg('EIP'):#x}")

    def draw(self):
        self.m.put(self.record + 4, 0)
        self.m.call(0x14F430, ecx=self.player, edx=18, stack=(0,))
        self.run()
        return self.history(18)

    def history(self, field):
        return self.m.call(0x14EE40, ecx=self.player, edx=field, stack=(), budget=100_000)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class DrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = DrawMachine()

    def test_starter_line_is_drawn_not_a_flat_step(self):
        self.d.role(0)
        lines = [self.d.draw() for _ in range(300)]
        self.assertGreaterEqual(len(set(lines)), 5, lines)
        self.assertNotEqual(set(lines), {2})
        self.assertTrue(1.7 <= sum(lines) / len(lines) <= 2.3, sum(lines) / len(lines))
        self.assertTrue(0.07 <= lines.count(0) / len(lines) <= 0.15, lines.count(0))
        self.assertLessEqual(max(lines), 8)
        self.assertEqual(self.d.history(18), lines[-1])

    def test_role_distributions_follow_the_four_bonus_tables(self):
        expected = {(0, 2): (2.00, 0.109), (1, 0): (2.87, 0.078), (2, 2): (2.26, 0.109), (3, 2): (1.11, 0.344)}
        histograms = {}
        for (rank, side), (mean, p0) in expected.items():
            with self.subTest(rank=rank, side=side):
                self.d.role(rank, side)
                lines = [self.d.draw() for _ in range(800)]
                histograms[(rank, side)] = [lines.count(k) for k in range(11)]
                self.assertAlmostEqual(sum(lines) / len(lines), mean, delta=0.22)
                self.assertAlmostEqual(lines.count(0) / len(lines), p0, delta=0.045)
                self.assertEqual(self.d.history(18), lines[-1])
        self.assertNotEqual(histograms[(0, 2)], histograms[(3, 2)])

    def test_non_starters_other_positions_and_missing_records_are_unchanged(self):
        self.d.role(0)
        self.d.games(6)
        self.assertEqual(self.d.draw(), 0)
        self.d.position(11)
        self.assertEqual(self.d.draw(), 0)
        self.d.position(4)
        self.d.games(self.d.WEEK)
        self.assertGreaterEqual(self.d.draw(), 0)
        self.d.games(self.d.WEEK - 1)
        history = self.d.m.get(self.d.player + 0x2C)
        self.d.m.put(self.d.player + 0x2C, 0)
        self.assertEqual(self.d.draw(), 0)
        self.d.m.put(self.d.player + 0x2C, history)

    def test_tail_replays_the_displaced_instructions(self):
        self.d.role(0)
        self.d.m.put(self.d.record + 4, 0)
        self.d.run()
        self.assertEqual(self.d.m.reg("EAX"), self.d.record)
        self.assertEqual(self.d.m.reg("EBX"), self.d.context)
        self.assertEqual(self.d.m.get(self.d.m.SP - 4), self.d.m.STOP)
        self.assertEqual(self.d.m.reg("ESP"), self.d.m.SP)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class ChainTests(unittest.TestCase):
    """b778-pg1 also wraps 0x134e05; the cb1 hook is inside the merge instead, so both owners coexist."""

    @classmethod
    def setUpClass(cls):
        cls.pg1 = load_pg1()
        if cls.pg1 is None:
            raise unittest.SkipTest("b778-pg1's module or fixture is not available")
        cls.retail = retail()
        if cls.retail is None:
            raise unittest.SkipTest("pinned USA retail XBE is not available")
        cls.saved = space.LATE_OWNERS
        space.LATE_OWNERS = (tuple(x for x in space.LATE_OWNERS if x not in (cb.OWNER, cls.pg1.OWNER))
                             + (cls.pg1.OWNER, cb.OWNER))
        cls.union, _ = space.apply(cls.retail, cls.pg1.REQUESTS + cb.REQUESTS, scaleout=True)

    @classmethod
    def tearDownClass(cls):
        space.LATE_OWNERS = cls.saved

    def install(self, order):
        payload = self.union
        for name in order:
            payload, receipt = (cb.apply(payload) if name == "cb" else self.pg1.apply(payload))
            self.assertEqual(receipt["status"], "applied", (name, receipt))
        return payload

    def run_merge(self, payload):
        from tests.mod_editor.test_nfl2k5_honors import Machine, word
        allocation = {row["owner"]: row["va"] for row in space.layout(payload)["allocations"]}
        cb_va, pg_va = allocation[cb.OWNER], allocation[self.pg1.OWNER]
        m = Machine(payload)
        m.uc.mem_write(m.ROOT, bytes(0x200))
        player = m.roster([(4, [word(0, 4, 7)])])[0]
        m.put8(player + 0x35, 4)
        m.put(player + 0x28, (0 << 10) | (2 << 13))
        m.put8(player + 0x23, m.uc.mem_read(player + 0x23, 1)[0] | 0x80)   # injured: pg1 reads and merges, then leaves
        live = 0xB30C4C
        m.uc.mem_write(live, bytes(m.uc.mem_read(player, 0x54)))
        record, context = m.HEAP + 0x70000, m.HEAP + 0x71000
        m.put(live + 0x30, record)
        m.put(record, context)
        m.uc.mem_write(context, bytes(0x200))
        m.put(record + 4, 0)
        for va, value in ((0xE576A0, 2), (0xE576A4, 8)):
            m.uc.mem_write(va, struct.pack("<I", value))
        m.uc.mem_write(0xE576B4, bytes([8]))
        # seed the retail RNG state (zero BSS in the harness)
        state = 0xB12680
        m.put(state, 54)
        m.put(state + 4, 0)
        def splitmix(x):
            x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
            z = x
            z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
            z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
            return z ^ (z >> 31)
        seed = 0x5EED5EED
        for k in range(55):
            seed = splitmix(seed)
            m.uc.mem_write(state + 8 + 8 * k, struct.pack("<Q", seed))
        m.call(0xCA7B0, stack=(0, 0))
        events, reads, pending = [], [], []

        def on_code(uc, address, _size, _data):
            events.append(address)

        def read_entry(uc, _address, _size, _data):
            pending.append(m.reg("EDX") if pg_va <= m.get(m.reg("ESP")) < pg_va + self.pg1.CODE_SIZE else None)

        def read_value(uc, _address, _size, _data):
            field = pending.pop()
            if field is not None:
                reads.append((field, m.reg("EAX")))

        def read_zero(uc, _address, _size, _data):
            field = pending.pop()
            if field is not None:
                reads.append((field, 0))

        def leave(uc, _address, _size, _data):
            m.reg("EIP", m.STOP)

        import unicorn as u
        for va in (pg_va, cb_va, cb.RESUME):
            m.uc.hook_add(u.UC_HOOK_CODE, on_code, begin=va, end=va)
        m.uc.hook_add(u.UC_HOOK_CODE, read_entry, begin=0x14EE40, end=0x14EE40)
        m.uc.hook_add(u.UC_HOOK_CODE, read_value, begin=0x14EE5B, end=0x14EE5B)
        m.uc.hook_add(u.UC_HOOK_CODE, read_zero, begin=0x14EE5C, end=0x14EE5C)
        m.uc.hook_add(u.UC_HOOK_CODE, leave, begin=0x134E0A, end=0x134E0A)
        # run the loop call exactly as FUN_00134dd0 does: push club, push copy, call 0x134e05
        sp = m.SP
        m.put(sp, m.STOP)
        sp -= 4
        m.put(sp, 0)
        sp -= 4
        m.put(sp, live)
        m.reg("ESP", sp)
        m.reg("EAX", player)
        for name in ("EBX", "ECX", "EDX", "ESI", "EDI", "EBP"):
            m.reg(name, 0x0BADF00D)
        m.uc.emu_start(0x134E05, m.STOP, count=60_000_000)
        if m.reg("EIP") != m.STOP:
            raise AssertionError(f"merge did not return: {m.reg('EIP'):#x}")
        final = m.call(0x14EE40, ecx=player, edx=18, stack=(), budget=100_000)
        layout = {row["owner"]: (row["va"], row["size"]) for row in space.layout(payload)["allocations"]
                  if row["owner"] in (cb.OWNER, self.pg1.OWNER)}
        return dict(events=[{pg_va: "pg1", cb_va: "cb", cb.RESUME: "merge"}[a] for a in events],
                    reads=reads, taken=m.uc.mem_read(record + 4, 1)[0], final=final, layout=layout)

    def test_both_installation_orders_run_each_owner_once(self):
        first = self.run_merge(self.install(("cb", "pg1")))
        second = self.run_merge(self.install(("pg1", "cb")))
        for result in (first, second):
            self.assertEqual(result["events"], ["pg1", "cb", "merge"])
            self.assertEqual(result["layout"], first["layout"])
            self.assertGreater(result["final"], 0)
            # pg1's pre-merge read sees the retail line, its post-merge read the credited line
            self.assertEqual(result["reads"], [(18, 0), (20, 0), (0, 7), (18, result["final"]), (20, 0), (0, 7)])
        self.assertEqual(first["final"], second["final"])

    def test_cb1_alone_leaves_the_pg1_call_retail(self):
        payload, receipt = cb.apply(self.retail)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(XbeImage(payload).read(0x134E05, 5), cb.RETAIL_PG1_CALL)
        # pg1 still reads the whole image as retail: its call site and guarded merge head are untouched
        self.assertEqual(self.pg1.status(payload), "retail")
        # and on the pre-allocated union both installations succeed in either order (the allocator is
        # append-only in LATE_OWNERS order, so the test allocates both owners before installing)
        patched = self.install(("cb", "pg1"))
        self.assertEqual(cb.status(patched), "applied")
        self.assertEqual(self.pg1.status(patched), "applied")


if __name__ == "__main__":
    unittest.main()
