"""Beta 77 (job F4b): the letter grade on the player progression screen's overall row.

``mod_editor/core/nfl2k5_letter_grades_progress.py`` makes the "Previously" and "Currently" values of row 0 (the player's
overall) of the progression report (text callback ``0x365CE0``) print through F4's ``%R`` grade, and leaves the "+/- Change"
column and every attribute row as numbers. These tests pin the stub and the two sites, the allocation, the Studio path
(``letter_grades.apply`` installs both), the native repair on the F4-repaired v0.5 executable, that no consumer of the
number changed, and run the *real* row loop under Unicorn (the game's own ``swprintf`` with F4's ``%R``, the new stub and the
callback's own code) for every rating. Nothing is witnessed in game. The v0.5 tests skip without the shipped v0.5 disc
(``NFL2K5_V05_DISC``), the retail tests without the private USA executable.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "tests", REPO / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_letter_grades as lg  # noqa: E402
from mod_editor.core import nfl2k5_letter_grades_progress as progress  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
import test_nfl2k5_letter_grades as f4tests  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_CS = importlib.util.find_spec("capstone") is not None
noah_grade = f4tests.noah_grade


class StubTests(unittest.TestCase):
    def test_the_stub_is_fifteen_bytes_padded_to_sixteen_and_decodes(self) -> None:
        code = progress.code_for(0x1509DE4)
        self.assertEqual(len(code), 16)
        self.assertEqual(code[15:], b"\xcc")
        self.assertEqual(code[:5], bytes.fromhex("baf092eb00"))            # the retail literal, for every row but row 0
        self.assertEqual(code[5:9], bytes.fromhex("85f67505"))              # test esi, esi / jnz +5
        self.assertEqual(code[9:14], b"\xba" + struct.pack("<I", 0x1509DE4))
        self.assertEqual(code[14:15], b"\xc3")
        if HAVE_CS:
            import capstone
            text = [f"{i.mnemonic} {i.op_str}".strip() for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code[:15], 0)]
            self.assertEqual(text, ["mov edx, 0xeb92f0", "test esi, esi", "jne 0xe", "mov edx, 0x1509de4", "ret"])

    def test_two_sites_call_the_stub_and_the_change_print_is_not_one(self) -> None:
        rows = progress.sites(0x14EB1F0)
        self.assertEqual([(label, va) for label, va, _b, _a in rows],
                         [("progression_previously", 0x365E84), ("progression_currently", 0x365ED8)])
        for _label, va, before, after in rows:
            self.assertEqual(before, bytes.fromhex("baf092eb00"))
            self.assertEqual(after[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack("<i", after[1:])[0], 0x14EB1F0)
        # the third print of the same literal ("+/- Change", mov edx at 0x365F18) stays pinned retail inside the guard
        self.assertNotIn(0x365F18, [va for _l, va, _b, _a in rows])
        self.assertNotIn(0x365F19, [va for _l, va, _b, _a in rows])

    def test_the_request_is_one_sixteen_byte_late_owner_after_letter_grades(self) -> None:
        self.assertEqual(progress.REQUESTS, (("nfl2k5_letter_grades_progress", "code", 16, 16),))
        self.assertEqual(lg.REQUESTS, lg.F4_REQUESTS + progress.REQUESTS)
        self.assertEqual(space.LATE_OWNERS.index(progress.OWNER), space.LATE_OWNERS.index(lg.OWNER) + 1)


class AllocatorTests(unittest.TestCase):
    def test_the_complete_dormant_union_still_fits_and_nobody_moves(self) -> None:
        union = tuple(space.dormant_union())
        self.assertIn(progress.REQUESTS[0], union)
        without = tuple(r for r in union if r[0] != progress.OWNER)
        old = {(a["owner"], a["kind"]): a for a in space._scale_allocations(without)}
        new = {(a["owner"], a["kind"]): a for a in space._scale_allocations(union)}
        for key, row in old.items():
            self.assertEqual(new[key], row, f"{key} moved")
        self.assertEqual(sorted(k for k in new if k not in old), [(progress.OWNER, "code")])
        mine, f4 = new[(progress.OWNER, "code")], new[(lg.OWNER, "code")]
        self.assertEqual(mine["va"], f4["va"] + f4["size"])
        self.assertGreaterEqual(space.plan(union)["capacity"]["code"]["available_bytes"], 0)


@unittest.skipUnless(HAVE_UC, "unicorn required")
class RetailNativeTests(unittest.TestCase):
    """The Studio path on the pinned retail executable: letter_grades.apply installs F4 and the progression row."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = f4tests._retail()
        cls.both, cls.receipt = lg.apply(cls.retail)
        cls.f4_only, _ = lg.apply(cls.retail, progression=False)

    def test_studio_apply_installs_both_and_is_idempotent(self) -> None:
        self.assertEqual(lg.status(self.both), "applied")
        self.assertEqual(progress.status(self.both), "applied")
        self.assertEqual(lg.read_settings(self.both)["progression"], "applied")
        again, receipt = lg.apply(self.both)
        self.assertEqual(again, self.both)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(self.receipt["progression"]["owner_bytes"], 16)
        self.assertEqual(len(self.receipt["sites"]), 28)                    # F4's own receipt is unchanged

    def test_f4_alone_leaves_the_progression_sites_retail(self) -> None:
        self.assertEqual(lg.status(self.f4_only), "applied")
        self.assertEqual(progress.status(self.f4_only), "retail")
        self.assertEqual(lg.read_settings(self.f4_only)["progression"], "retail")
        self.assertIsNone(progress.allocation(self.f4_only))
        added, _ = progress.apply(self.f4_only)
        self.assertEqual(added, self.both)

    def test_the_progression_row_needs_f4_first(self) -> None:
        self.assertEqual(progress.status(self.retail), "retail")
        with self.assertRaises(ValueError):
            progress.apply(self.retail)

    def test_foreign_and_mixed_installations_are_refused(self) -> None:
        found = progress.allocation(self.both)
        for label, va, _before, _after in progress.sites(found["va"]):
            off = rdata.offset_of(self.both, va)
            for position in (0, 2):
                broken = bytearray(self.both)
                broken[off + position] ^= 0x01
                self.assertEqual(progress.status(bytes(broken)), "foreign", label)
                with self.assertRaises(ValueError):
                    progress.apply(bytes(broken))
        broken = bytearray(self.both)
        broken[found["raw"] + 3] ^= 0xFF
        self.assertEqual(progress.status(bytes(broken)), "foreign")
        # the third print of the shared literal and the literal itself are pinned as retail
        for va in (0x365F18, 0xEB92F0, 0x365B04):
            broken = bytearray(self.both)
            broken[rdata.offset_of(self.both, va)] ^= 0x01
            self.assertEqual(progress.status(bytes(broken)), "foreign", hex(va))
        # one site patched, the other retail: mixed
        mixed = bytearray(self.f4_only)
        mixed[rdata.offset_of(self.f4_only, 0x365E84)] = 0xE8
        self.assertEqual(progress.status(bytes(mixed)), "foreign")


def _rows(payload: bytes, start: int, prev, curr):
    """Run the progression callback's row loop (0x365E51 .. 0x365F69) from row ``start``: the text drawn per row."""

    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    texts: list[str] = []

    def value(mode, index):
        return {0: prev[index], 1: curr[index], 2: curr[index] - prev[index]}[mode]

    def getter():
        sp = m.reg("ESP")
        m.ret(value(m.get(sp + 4), m.get(sp + 8)), pop=0xC)

    m.leaf(0x365B20, getter, reason="the row value is supplied by the test: the proof is about the text, not the values")
    m.leaf(0x46A70, lambda: m.ret(0, pop=0xC), reason="vector constructor: no effect on the text")
    m.leaf(0x46B50, lambda: m.ret(0), reason="set colour: no effect on the text")

    def draw():
        texts.append(bytes(m.uc.mem_read(m.reg("EDX"), 64)).decode("utf-16le").split("\0")[0])
        m.ret(0)

    m.leaf(0xF1C70, draw, reason="text draw: capture the string it is asked to draw")
    esp = m.STACK + 0x400
    ebp = esp + 0xD0
    m.uc.mem_write(esp, bytes(0xE0))
    m.uc.mem_write(ebp, struct.pack("<II", 0, m.STOP))
    m.put(esp + 0x18, 0)                  # rows drawn so far (the loop ends at 6)
    m.put(esp + 0x20, 0x43B68000)
    for name, number in dict(ESP=esp, EBP=ebp, ESI=start, EDI=0x1234, EBX=0, ECX=0, EDX=0, EFLAGS=0x202).items():
        m.reg(name, number)
    m.uc.emu_start(0x365E51, 0x365F69, count=2000000)
    if m.reg("EIP") != 0x365F69:
        raise AssertionError(f"the loop stopped at {m.reg('EIP'):#x}")
    return [tuple(texts[i:i + 3]) for i in range(0, len(texts), 3)]


@unittest.skipUnless(HAVE_UC, "unicorn required")
class V05NativeTests(unittest.TestCase):
    """The native repair on the F4-repaired shipped v0.5 executable, and the real row loop."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.v05 = f4tests._v05_xbe()
        sys.path.insert(0, str(REPO / "tools" / "b77"))
        import f4_repair
        import f4b_repair
        cls.f4_repair, cls.repair = f4_repair, f4b_repair
        cls.f4, _ = f4_repair.repair_xbe(cls.v05)
        cls.patched, cls.receipt = f4b_repair.repair_xbe(cls.f4)

    def test_the_repair_is_scoped_deterministic_and_idempotent(self) -> None:
        self.assertEqual(hashlib.sha256(self.f4).hexdigest(), self.repair.F4_V05_SHA256)
        self.assertEqual(hashlib.sha256(self.patched).hexdigest(), self.repair.FIXED_V05_SHA256)
        self.assertEqual(self.receipt["status"], "applied")
        self.assertTrue(self.receipt["outside_scope_identical"])
        self.assertTrue(self.receipt["existing_allocations_unchanged"])
        self.assertEqual(self.receipt["changed_bytes"], 644)
        changed = [s["label"] for s in self.receipt["scopes"] if s["changed"]]
        self.assertEqual(len(changed), 8)
        self.assertIn("owned RX code (16 bytes)", changed)
        again, receipt = self.repair.repair_xbe(self.patched)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt["status"], "already_applied")
        self.assertEqual(receipt["changed_bytes"], 0)
        restored = bytearray(self.patched)
        for start, end, _label in self.repair.declared_scopes(self.f4, self.patched):
            restored[start:end] = self.f4[start:end]
        self.assertEqual(bytes(restored), self.f4)
        self.assertEqual(len(self.patched), len(self.f4))

    def test_the_studio_path_equals_the_two_repairs(self) -> None:
        studio, _ = lg.apply(self.v05)
        self.assertEqual(studio, self.patched)
        f4_alone, _ = lg.apply(self.v05, progression=False)               # F4 alone is exactly as F4 shipped it
        self.assertEqual(hashlib.sha256(f4_alone).hexdigest(), self.f4_repair.FIXED_V05_SHA256)

    def test_the_repair_refuses_unpatched_or_foreign_input(self) -> None:
        with self.assertRaises(ValueError):
            self.repair.repair_xbe(self.v05)                  # F4 is required
        with self.assertRaises(ValueError):
            self.repair.repair_xbe(self.f4[:-1])
        broken = bytearray(self.f4)
        broken[rdata.offset_of(self.f4, 0x365E84)] ^= 1
        with self.assertRaises(ValueError):
            self.repair.repair_xbe(bytes(broken))

    def test_every_existing_owner_keeps_its_bytes_and_address(self) -> None:
        old = space.layout(self.f4)["allocations"]
        new = space.layout(self.patched)["allocations"]
        for row in old:
            self.assertIn(row, new)
            if row["owner"] != space.DIRECTORY_OWNER:
                self.assertEqual(self.f4[row["raw"]:row["raw"] + row["size"]],
                                 self.patched[row["raw"]:row["raw"] + row["size"]], row["owner"])
        mine = [row for row in new if row["owner"] == progress.OWNER]
        self.assertEqual([(r["kind"], r["size"]) for r in mine], [("code", 16)])
        f4 = [row for row in new if row["owner"] == lg.OWNER and row["kind"] == "code"][0]
        self.assertEqual(mine[0]["va"], f4["va"] + f4["size"])

    def test_every_consumer_of_the_number_is_byte_identical(self) -> None:
        """Only the two 5-byte sites and the 16 owned bytes differ in the executable image; the row getter, the snapshot code,
        the overall computation and the rest of the progression callback are the F4 (and retail) bytes."""
        from tests.nfl2k5_supersim_draft_fixture import Machine
        before, after = Machine(self.f4, trace_writes=False), Machine(self.patched, trace_writes=False)
        ranges = ((0x365B00, 0x365C6B), (0x365C70, 0x365CD0), (0x365CE0, 0x365E84), (0x365E89, 0x365ED8),
                  (0x365EDD, 0x365F70), (0xE6660, 0xE6670), (0x246D90, 0x246DE0), (0xEB92F0, 0xEB92F6), (0x4E69B8, 0x4E69C0))
        for lo, hi in ranges:
            self.assertEqual(bytes(after.uc.mem_read(lo, hi - lo)), bytes(before.uc.mem_read(lo, hi - lo)), f"{lo:#x}..{hi:#x}")
        retail_sites = {va: bytes(before.uc.mem_read(va, 5)) for _l, va, _b, _a in progress.sites(0)}
        self.assertEqual(set(retail_sites.values()), {bytes.fromhex("baf092eb00")})

    # --- the real row loop -------------------------------------------------------------------------------
    def test_row_zero_prints_grades_for_previously_and_currently_and_nothing_else_changes(self) -> None:
        prev = [60 + i for i in range(30)]
        curr = [61 + i for i in range(30)]
        prev[0], curr[0] = 71, 96
        retail_rows = _rows(self.v05, 0, prev, curr)
        f4_rows = _rows(self.f4, 0, prev, curr)
        new_rows = _rows(self.patched, 0, prev, curr)
        self.assertEqual(retail_rows[0], ("71", "96", "25"))
        self.assertEqual(f4_rows, retail_rows)                       # F4 alone leaves this screen as numbers
        self.assertEqual(new_rows[0], ("C", "A+", "25"))              # grades, but the change stays a plain number
        self.assertEqual(new_rows[1:], retail_rows[1:])               # every attribute row is still numbers
        # a window that does not include row 0 is untouched
        self.assertEqual(_rows(self.patched, 3, prev, curr), _rows(self.v05, 3, prev, curr))

    def test_every_rating_gets_noahs_grade_on_row_zero_and_negative_change_stays_a_number(self) -> None:
        checked = 0
        for rating in list(range(0, 121)) + [-3]:
            prev = [0] * 30
            curr = [0] * 30
            prev[0] = rating
            curr[0] = 100 - rating
            row = _rows(self.patched, 0, prev, curr)[0]
            self.assertEqual(row[0], noah_grade(rating), rating)
            self.assertEqual(row[1], noah_grade(100 - rating), rating)
            self.assertEqual(row[2], str(100 - 2 * rating), rating)
            checked += 1
        self.assertEqual(checked, 122)

    def test_row_zero_follows_the_same_scale_as_the_f4_sites(self) -> None:
        # the same %R handler and band table: the progression row and the card-style site agree on every rating
        prev = [0] * 30
        curr = [0] * 30
        for rating in range(0, 121, 5):
            prev[0] = curr[0] = rating
            self.assertEqual(_rows(self.patched, 0, prev, curr)[0][:2], (lg.grade_for(rating),) * 2)


if __name__ == "__main__":
    unittest.main()
