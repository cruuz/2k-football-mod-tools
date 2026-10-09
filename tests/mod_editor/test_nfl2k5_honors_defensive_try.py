"""Job F5b (beta 77): the honors owner's history-fold edit and defensive_try's history-engine pin do not interact.

Background: ``nfl2k5_defensive_try`` pins the history engine (VA 0x14E7E0, 3,216 bytes) because it writes field 59
through the engine's writer. ``nfl2k5_honors`` (job F5) replaces one 7-byte instruction in that span (0x14F168, the
fold's rule-table load) so the ten honor fields 96..105 always fold by sum. Every reader of the rule table and every
caller of the fold lies inside the same span (checked below), so the edit cannot move to a site outside the pin.
defensive_try therefore restores the retail bytes of that one site before it hashes its context, and only while the
honors owner validates as exactly applied. This file proves the two edits are independent:

* bytes: the two owners change disjoint file bytes (the shared section digests aside) and apply in either order to
  byte-identical images; the honors site is the only edit inside any defensive_try pin; no defensive_try edit touches a
  honors dependency span;
* tolerance is exact: any other change to the site, a missing honors installation or a flipped byte elsewhere in the
  span still reads foreign;
* behaviour (Unicorn, the game's own code): the hook returns the retail table value for all 118 non-honor fields of the
  7-bit field space and preserves every register and the stack; the real fold gives byte-identical streams with and
  without the honors edit for every non-honor field (field 59 included) and sums honor fields whatever the live text
  scratch holds; the real writer and postgame merge of defensive_try give identical results with and without it.

Nothing here is an in-game result. The native classes skip without the pinned USA XBE or Unicorn.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_defensive_try as dt  # noqa: E402
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import CLASS, HAVE_UC, Machine, _retail, word  # noqa: E402

RULE_TABLE, FOLD_SITE = 0xAA26C0, 0x14F168
SPAN = (0x14E7E0, 3216)                    # defensive_try's history-engine pin
HONOR_FIELDS = range(96, 106)
V4 = os.environ.get("B77_V4_XBE", "")      # optional: the integrator's stacked default.xbe


def first(field: int) -> int:     # the value written for a field in season slot 1
    return field % 7 + 1


def second(field: int) -> int:    # ... and in season slot 2
    return field % 5 + 2


def changed_offsets(before: bytes, after: bytes) -> set[int]:
    return {i for i, (a, b) in enumerate(zip(before, after)) if a != b}


def derived_offsets(payload: bytes) -> set[int]:
    """Bytes every install recomputes: the section digests and the allocator directory's code digest (two copies)."""
    digests = {o for s in _sections(payload) for o in range(s.header_offset + 36, s.header_offset + 56)}
    return digests | set(range(space.DIRECTORY, space.LIB_COPY)) | set(range(space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE))


@unittest.skipUnless(_retail() is not None, "pinned USA XBE required")
class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.base, _ = space.apply(cls.retail, space.dormant_union(), scaleout=True)   # every owner's pages, nothing installed
        cls.dt_first = honors.apply(dt.apply(cls.base)[0])[0]
        cls.honors_first = dt.apply(honors.apply(cls.base)[0])[0]

    def test_both_owners_read_applied_in_either_order_and_the_images_are_identical(self):
        for image in (self.dt_first, self.honors_first):
            self.assertEqual(dt.status(image), "applied")
            self.assertEqual(honors.status(image), "applied")
            self.assertEqual(space.status(image), "applied")
        self.assertEqual(self.dt_first, self.honors_first)

    def test_the_two_owners_change_disjoint_bytes(self):
        dt_only, honors_only = dt.apply(self.base)[0], honors.apply(self.base)[0]
        a, b = changed_offsets(self.base, dt_only), changed_offsets(self.base, honors_only)
        shared = a & b
        self.assertTrue(shared <= derived_offsets(self.base), sorted(hex(o) for o in shared - derived_offsets(self.base)))
        self.assertTrue(shared)                       # ... and they do share exactly those derived bytes
        self.assertEqual(changed_offsets(self.base, self.dt_first), a | b)

    def test_the_fold_site_is_the_only_honors_edit_inside_a_defensive_try_pin(self):
        honors_sites = honors.sites(honors.allocations(self.dt_first)["code"]["va"])
        inside = [(label, hex(va)) for label, va, before, _after in honors_sites for start, size, _d in dt.CONTEXT_PINS
                  if start <= va < start + size or va < start < va + len(before)]
        self.assertEqual(inside, [("history_fold", hex(FOLD_SITE))])
        self.assertTrue(SPAN[0] <= FOLD_SITE and FOLD_SITE + 7 <= SPAN[0] + SPAN[1])

    def test_no_defensive_try_edit_touches_a_honors_dependency_span(self):
        edits = [(va, len(bytes.fromhex(before))) for va, before, _a in {**dt.BRANCHES, **dt.HOOKS}.values()]
        touched = [(name, hex(va)) for name, va, size, _digest in honors.GUARDS for e, n in edits if e < va + size and va < e + n]
        self.assertEqual(touched, [])

    def test_only_the_exact_honors_edit_is_tolerated(self):
        image = self.dt_first
        site = FOLD_SITE - 0x10000
        self.assertEqual(image[site], 0xE8)
        # another call target: honors reads foreign (mixed sites) and so does defensive_try
        moved = bytearray(image)
        moved[site + 1] ^= 1
        self.assertEqual(honors.status(bytes(moved)), "foreign")
        self.assertEqual(dt.status(bytes(moved)), "foreign")
        # the honors edit bytes with no honors code behind them
        code = honors.allocations(image)["code"]
        emptied = bytearray(image)
        emptied[code["raw"]:code["raw"] + code["size"]] = b"\xcc" * code["size"]
        self.assertEqual(honors.status(bytes(emptied)), "foreign")
        self.assertEqual(dt.status(bytes(emptied)), "foreign")
        # a different change inside the same pinned span, with honors installed
        for va in (0x14E7E0, 0x14F167, 0x14F16F, 0x14F456, 0x14F46F):
            bad = bytearray(image)
            bad[va - 0x10000] ^= 1
            self.assertEqual(dt.status(bytes(bad)), "foreign", hex(va))
        # honors alone and defensive_try alone are unaffected
        self.assertEqual(dt.status(self.base), "retail")
        self.assertEqual(honors.status(self.base), "retail")

    def test_every_rule_table_reader_and_fold_caller_lies_inside_the_pinned_span(self):
        """Why no site outside the pin can carry the edit (static scan of the retail executable)."""
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.retail)
        text = next(s for s in image.sections if s.name == ".text")
        data = image.read(text.start, text.size)
        lo, hi = SPAN[0], SPAN[0] + SPAN[1]
        readers = [text.start + i for i in range(len(data) - 3) if struct.unpack_from("<I", data, i)[0] == RULE_TABLE]
        self.assertEqual([hex(r) for r in readers], ["0x14ee7a", "0x14f16b", "0x14f456"])
        self.assertTrue(all(lo <= r < hi for r in readers))
        callers = [text.start + i for i in range(len(data) - 4) if data[i] == 0xE8
                   and text.start + i + 5 + struct.unpack_from("<i", data, i + 1)[0] == 0x14EFE0]
        self.assertEqual([hex(c) for c in callers], ["0x14f282", "0x14f29d"])
        self.assertTrue(all(lo <= c < hi for c in callers))

    @unittest.skipUnless(V4 and Path(V4).is_file(), "set B77_V4_XBE to the integrator's stacked default.xbe")
    def test_the_stacked_executable(self):
        v4 = Path(V4).read_bytes()
        self.assertEqual((dt.status(v4), honors.status(v4)), ("applied", "retail"))
        both, _ = honors.apply(v4)
        self.assertEqual((dt.status(both), honors.status(both)), ("applied", "applied"))


@unittest.skipUnless(_retail() is not None and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        base, _ = space.apply(retail, dt.REQUESTS + honors.REQUESTS, scaleout=True)
        cls.dt_only = dt.apply(base)[0]
        cls.both = honors.apply(cls.dt_only)[0]
        cls.at = honors.labels(honors.allocations(cls.both)["code"]["va"])

    # --- the hook itself ----------------------------------------------------------------------------------------
    def run_hook(self, payload, entry, field, table):
        m = Machine(payload)
        for i, value in enumerate(table):
            m.put(RULE_TABLE + 4 * i, value)
        sp = m.SP
        m.put(sp - 4, m.STOP)
        m.reg("ESP", sp - 4)
        canary = {"EBX": 0x11111111, "ECX": 0x22222222, "EDX": 0x33333333, "ESI": field, "EDI": 0x55555555, "EBP": 0x66666666}
        for name, value in canary.items():
            m.reg(name, value)
        m.reg("EAX", 0x77777777)
        m.uc.emu_start(entry, m.STOP, count=100)
        out = {name: m.reg(name) for name in canary}
        out["EAX"], out["ESP"] = m.reg("EAX"), m.reg("ESP")
        return out, sp

    def test_the_hook_returns_the_retail_value_for_every_non_honor_field(self):
        table = [(0x9E3779B1 * (i + 1)) & 0xFFFFFFFF for i in range(128)]   # arbitrary live contents for fields 87..127
        retail_load = bytes.fromhex("8b04b5c026aa00c3")                      # the displaced instruction, then ret
        for field in range(128):
            got, sp = self.run_hook(self.both, self.at["honors_fold_rule"], field, table)
            if field in HONOR_FIELDS:
                self.assertEqual(got["EAX"], 1, field)
            else:
                self.assertEqual(got["EAX"], table[field], field)             # what "mov eax, [esi*4 + 0xaa26c0]" loads
            self.assertEqual({k: v for k, v in got.items() if k not in ("EAX", "ESP")},
                             {"EBX": 0x11111111, "ECX": 0x22222222, "EDX": 0x33333333, "ESI": field,
                              "EDI": 0x55555555, "EBP": 0x66666666}, field)
            self.assertEqual(got["ESP"], sp, field)                           # the call/ret pair is balanced
        # and the displaced instruction really is that load, run on the retail image for the same inputs
        m = Machine(self.dt_only)
        m.uc.mem_write(m.STACK, retail_load)
        for field in (0, 59, 86, 87, 95, 106, 127):
            m.put(RULE_TABLE + 4 * field, 0xABCD0000 + field)
            m.reg("ESI", field)
            m.reg("EAX", 0)
            m.uc.emu_start(m.STACK, m.STACK + 7, count=1)
            self.assertEqual(m.reg("EAX"), 0xABCD0000 + field)

    # --- the real fold --------------------------------------------------------------------------------------------
    @staticmethod
    def population():
        """Two seasons of words for every field of the 7-bit space, plus a young season that must stay unfolded."""
        words = []
        for field in range(128):
            words += [word(field, 1, first(field)), word(field, 2, second(field))]
        words += [word(59, 3, 5, post=True), word(0, 4, 16)]
        return words

    def fold(self, payload, scratch=0):
        m = Machine(payload)
        for i in range(10):                                          # the live UI text object that fields 96..105 alias
            m.put(RULE_TABLE + 4 * (96 + i), scratch)
        m.record(0x177990, "progress", pop=4)
        rec = m.roster([(5, self.population())])[0]
        m.put(CLASS, 0)
        m.call(0x14EFE0, stack=(4,))
        return {((w >> 16) & 0x7F, (w >> 23) & 31, bool(w & 0x20000000)): (w & 0xFFFF, bool(w & 0x40000000))
                for w in m.stream(rec) if not w & 0x10000000}

    def test_the_fold_is_identical_for_every_non_honor_field_with_and_without_the_edit(self):
        without, with_edit = self.fold(self.dt_only), self.fold(self.both)
        other = {k for k in without if not 96 <= k[0] <= 105}
        self.assertGreater(len(other), 118)
        self.assertEqual({k: without[k] for k in other}, {k: with_edit[k] for k in other})
        self.assertEqual(with_edit[(59, 2, False)], (first(59) + second(59), True))   # defensive_try's field: native sum rule
        self.assertEqual(with_edit[(59, 3, True)], (5, False))          # its postseason word is not folded
        self.assertEqual(with_edit[(0, 4, False)], (16, False))
        self.assertEqual(with_edit[(30, 2, False)], (max(first(30), second(30)), True))   # a max-rule field keeps max
        self.assertEqual(with_edit[(87, 2, False)], (first(87) + second(87), True))       # TEAM column: pointer, sum

    def test_honor_fields_always_sum_whatever_the_text_scratch_holds(self):
        for scratch in (0, 0x43F00000, 1, 0xFFFFFFFF):
            folded = self.fold(self.both, scratch)
            for field in HONOR_FIELDS:
                self.assertEqual(folded[(field, 2, False)], (first(field) + second(field), True), (field, scratch))
        retail = self.fold(self.dt_only, 0)
        self.assertEqual(retail[(96, 2, False)], (max(first(96), second(96)), True))         # retail reads zero here: max
        self.assertNotEqual(retail[(96, 2, False)], self.fold(self.both, 0)[(96, 2, False)])

    # --- defensive_try's own routines, with and without the honors edit ------------------------------------------
    def sequence(self, payload):
        from tests.mod_editor.test_nfl2k5_defensive_try_stats import StatsMachine
        out = []
        for history_class in (0, 1):
            m = StatsMachine(payload)
            saved = m.saved(1)
            out += [m.write_history(saved, 59, 2, 4, history_class), m.write_history(saved, 59, 3, 2, history_class),
                    m.write_history(saved, 59, 3, 9, 1 - history_class), m.write_history(saved, 87, 2, 7, history_class)]
            m.history(0, 1)
            m.set(0xBD7F98, history_class)
            out.append([m.value(m.live(1), bank) for bank in (0, 8, 9, 10, 11, 12, 13)])
            m.merge(1, history_class=history_class)
            out.append(m.count(1))
            m.set(0xBD7F98, history_class)
            out.append([m.value(saved, bank) for bank in (9, 10, 11, 12)])
            m.merge(1, history_class=history_class)
            m.set(0xBD7F98, 1 - history_class)
            out.append(m.value(saved, 11))
            out.append(bytes(m.u.mem_read(m.POOL, 0x200)))
        return out

    def test_defensive_try_writer_and_postgame_merge_are_identical_with_and_without_the_edit(self):
        without, with_edit = self.sequence(self.dt_only), self.sequence(self.both)
        self.assertEqual(without, with_edit)
        self.assertEqual(with_edit[4], [1, 6, 7, 2, 3, 4, 0])           # the retail-proven readings of that sequence
        self.assertEqual(with_edit[5], 0x8001)


if __name__ == "__main__":
    unittest.main()
