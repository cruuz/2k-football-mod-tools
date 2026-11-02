"""b780 b1-draft (row B1): draft classes from a real position mix on every build with the franchise draft fixes, and
at most one kicker or punter before display round 5 in a draft.

SharkMagick 11/01 (original 2004 rosters): "kickers getting drafted in R3 again", "6 by my count", "even punters are
getting drafted in r3", "only one qb". Unit tests on the owners' bytes, then the game's own class turnover and CPU
draft under Unicorn (the private retail executable, roster and the signed f0 franchise; skipped without them).
"""
from __future__ import annotations

import collections
import struct
import tempfile
import unittest
from pathlib import Path

from mod_editor.core import nfl2k5_draft_ai as ai
from mod_editor.core import nfl2k5_draft_class as draft_class
from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
MIX = dict(zip(POSITIONS, (21, 9, 9, 37, 44, 18, 14, 25, 9, 25, 18, 18, 30, 28, 44, 49, 52)))
# A 380-player class (the retail size, every class without the economy): prospect k = 380..1 takes slot
# (k - 1) x 151 mod 450, so slots 0..379 of that walk; the 70 unvisited slots fall in three bands.
MIX_380 = dict(zip(POSITIONS, (21, 9, 9, 37, 31, 12, 10, 25, 9, 25, 18, 12, 20, 20, 44, 43, 35)))
# The b778 dr2 pick head (beta-78 and beta-79, so every SOFTDRINK v0.7 / v0.8 build carries it).
PREVIOUS_HEAD = bytes.fromhex(
    "5356575581ecfc0000008be98bfa31c031c989048c4183f93b7cf78d84248800000050ff35a4c0e3008b15a8c0e3008bcde87afdffff8b"
    "351829b7008b1e8b760485db7e24f646081074188bce6a015ae83b8cf2ff0fb64635d80484d91c84ff44844483c6544b7fdce912000000"
    "ccccccccccccccccccccccccccccccccccccc78424f40000009a99993ebe010000008bcd8bd6e8275bdaff85c0752ca1a8c0e30083f804"
    "7c16ba2000000029f23b15a4c0e3007513b801000000eb05b8020000008984b4d40000004683fe027ec1e955620000cccccccccccccccc"
    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc0ad7233c8fc27539cccccc")


def _walk(size):
    """The class window's slot walk (runtime.c economy_class_position) for a class of `size` prospects."""
    counts, out = list(MIX.values()), collections.Counter()
    for k in range(size, 0, -1):
        slot, pos = (k - 1) * 151 % 450, 0
        while pos < 16 and slot >= counts[pos]:
            slot -= counts[pos]
            pos += 1
        out[POSITIONS[pos]] += 1
    return dict(out)


def _with_head(payload, head):
    image, out = XbeImage(payload), bytearray(payload)
    offset = image.offset(ai.PICK_FN_VA, ai.PICK_FN_SIZE)
    out[offset:offset + ai.PICK_FN_SIZE] = head
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


class ClassOwnerTests(unittest.TestCase):
    """The class half of economy revision 4, installed on its own."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.patched, cls.receipt = draft_class.apply(cls.retail)

    def test_installs_the_economy_class_sites_and_reads_as_no_economy(self):
        self.assertEqual(draft_class.status(self.retail), "retail")
        self.assertEqual(draft_class.status(self.patched), "applied")
        self.assertEqual(economy.status(self.patched), "retail")
        image = XbeImage(self.patched)
        revision_four = {s.va: s.patched for s in economy.sites()}
        self.assertEqual({s.va for s in draft_class.sites()}, set(economy.CLASS_SITES))
        self.assertEqual(economy.CLASS_SITES, {0x382200, 0x2BD3C0, 0x2BDCAE, 0x2BE91D})
        for site in draft_class.sites():
            self.assertEqual(image.read(site.va, len(site.patched)), revision_four[site.va])
        self.assertEqual([e["va"] for e in self.receipt["edits"]], ["0x2bd3c0", "0x2bdcae", "0x2be91d", "0x382200"])
        self.assertTrue(self.receipt["keeps_create_vacancies"])
        self.assertEqual(self.receipt["mix_per_450"], MIX)
        # only the four sites and the .text digest change
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b]
        self.assertEqual(len(changed), self.receipt["changed_bytes"])

    def test_the_economy_installs_over_it_unchanged(self):
        over, _ = economy.apply(self.patched)
        alone, _ = economy.apply(self.retail)
        self.assertEqual(over, alone)
        self.assertEqual((economy.status(over), draft_class.status(over)), ("applied", "applied"))
        self.assertEqual(draft_class.apply(alone)[1], {"already_applied": True, "changed_bytes": 0})

    def test_replay_is_a_no_op_and_foreign_bytes_refuse(self):
        self.assertEqual(draft_class.apply(self.patched), (self.patched, {"already_applied": True, "changed_bytes": 0}))
        image = XbeImage(self.patched)
        broken = bytearray(self.patched)
        broken[image.offset(0x382200 + 0xB0, 1)] ^= 0xFF          # one byte of the mix
        self.assertEqual(draft_class.status(bytes(broken)), "foreign")
        with self.assertRaises(draft_class.DraftClassError):
            draft_class.apply(bytes(broken))
        partial = bytearray(self.retail)                          # one call site alone is not the owner
        partial[image.offset(0x2BE91D, 6):image.offset(0x2BE91D, 6) + 6] = image.read(0x2BE91D, 6)
        self.assertEqual(draft_class.status(bytes(partial)), "foreign")

    def test_the_mix_and_a_retail_size_class(self):
        self.assertEqual(draft_class.mix(), MIX)
        self.assertEqual(sum(MIX.values()), 450)
        self.assertEqual(_walk(450), MIX)
        self.assertEqual(_walk(380), MIX_380)
        self.assertEqual(sum(MIX_380.values()), 380)

    def test_a_revision_three_image_with_the_class_sites_still_upgrades(self):
        # Someone rebuilds a beta-78 / v0.7 SOFTDRINK disc (economy revision 3) with the economy left off: the draft
        # fixes add the class sites. A later build with the economy on must still upgrade that image in place.
        from tests.mod_editor.test_b779_rc1_roster_capacity import _revision_three
        current = economy.apply(self.retail)[0]
        previous = _revision_three(current, self.retail)
        self.assertEqual(economy.status(previous), "legacy")
        with_class = draft_class.apply(previous)[0]
        self.assertEqual(economy.status(with_class), "legacy")
        upgraded, receipt = economy.apply(with_class)
        self.assertEqual(upgraded, current)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")


class DraftAiHeadTests(unittest.TestCase):
    """The early outlier is counted per draft; beta-78/79 heads upgrade in place."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.applied = ai.apply(cls.retail)[0]

    def test_the_class_sums_count_this_drafts_specialists_and_the_outlier_checks_it(self):
        head, tail = ai.pick_fn_bytes()
        self.assertEqual(len(head), ai.PICK_FN_SIZE)
        self.assertLessEqual(5 + len(tail), ai.BODY_SIZE)
        prefix = head[:ai.SPECIAL_HEAD_OFFSET]
        count_slot = struct.pack("<I", ai.SPECIALIST_COUNT_OFF)
        self.assertIn(bytes.fromhex("f6460820"), prefix)                         # test byte [esi+8],0x20
        self.assertIn(b"\xff\x84\x24" + count_slot, prefix)                       # inc dword [esp+0xe0]
        self.assertLess(ai.SPECIALIST_COUNT_OFF, 59 * 4)                           # inside the zeroed frame
        special = head[ai.SPECIAL_HEAD_OFFSET:ai.PICK_CONST_OFF]
        self.assertIn(b"\x83\xbc\x24" + count_slot + bytes((ai.EARLY_SPECIALIST_CAP,)) + b"\x73", special)
        self.assertEqual(ai.EARLY_SPECIALIST_CAP, 1)
        self.assertGreaterEqual(ai.SPECIAL_EDGE, 0.30)

    def test_a_beta79_head_reads_legacy_and_upgrades_in_place(self):
        import hashlib
        self.assertEqual(hashlib.sha256(PREVIOUS_HEAD).hexdigest(), ai.PREVIOUS_HEAD_SHA256)
        legacy = _with_head(self.applied, PREVIOUS_HEAD)
        self.assertEqual(ai.status(legacy), "legacy")
        upgraded, receipt = ai.apply(legacy)
        self.assertEqual(upgraded, self.applied)
        self.assertEqual(receipt["upgraded_from"], "legacy")
        image = XbeImage(legacy)
        head_offset = image.offset(ai.PICK_FN_VA, ai.PICK_FN_SIZE)
        changed = [i for i, (a, b) in enumerate(zip(legacy, upgraded)) if a != b]
        self.assertTrue(all(head_offset <= i < head_offset + ai.PICK_FN_SIZE or i < 0x1000 for i in changed))
        tampered = bytearray(PREVIOUS_HEAD)
        tampered[100] ^= 1
        self.assertEqual(ai.status(_with_head(self.applied, bytes(tampered))), "foreign")
        self.assertEqual(ai.status(_with_head(self.retail, PREVIOUS_HEAD)), "foreign")   # head alone is not the owner


class BuildPathTests(unittest.TestCase):
    """The executable writer installs the class owner whenever the draft fixes are on."""

    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()

    def _write(self, **options):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "default.xbe", Path(tmp) / "out.xbe"
            source.write_bytes(self.retail)
            result = tt.write_xbe_copy(source, target, catch_slider=False, **options)
            return result, target.read_bytes()

    def test_with_and_without_the_economy(self):
        result, payload = self._write(draft_ai=True)
        self.assertEqual((result["draft_ai"], result["draft_class"], result["franchise_economy"]),
                         ("applied", "applied", "retail"))
        self.assertEqual(draft_class.status(payload), "applied")
        result, payload = self._write(draft_ai=True, franchise_economy=True)
        self.assertEqual((result["draft_ai"], result["draft_class"], result["franchise_economy"]),
                         ("applied", "applied", "applied"))
        self.assertEqual(payload, economy.apply(self._write(draft_ai=True)[1])[0])
        result, _ = self._write(returner_fix=True)
        self.assertEqual((result["draft_ai"], result["draft_class"]), ("retail", "retail"))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeClassTurnoverTests(unittest.TestCase):
    """One native league year on the retail roster without the economy (b779 rc1's _turnover): the retirement
    pass 0x2BDB00, the Combine cleanup 0x2BDA90 and the class generator 0x2BE940(380)."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        cls.retail, cls.body = retail_bytes(), retail_roster()
        cls.fixed = draft_class.apply(ai.apply(cls.retail)[0])[0]

    def test_the_class_takes_the_mix_and_keeps_every_create_vacancy(self):
        from tests.mod_editor.test_b779_rc1_roster_capacity import _turnover
        before, after, positions, written, _ = _turnover(self.fixed, self.body)
        self.assertGreater(before, 100)
        self.assertEqual(after, before)              # Create Player, MyCareer and imports keep their records
        self.assertEqual(len(positions), 380)
        self.assertEqual(dict(collections.Counter(POSITIONS[p] for p in positions)), MIX_380)
        self.assertEqual(written, positions)          # the generator wrote each prospect at that position

    def test_negative_control_retail_copies_the_leavers_positions(self):
        from tests.mod_editor.test_b779_rc1_roster_capacity import _turnover
        before, after, positions, _, _ = _turnover(self.retail, self.body)
        self.assertEqual(len(positions), 380)
        self.assertNotEqual(dict(collections.Counter(POSITIONS[p] for p in positions)), MIX_380)
        self.assertLessEqual(after, before)


def _worst_case_draft(payload, seed=1, stars=5):
    """The signed franchise at the draft. No club has a K or P (they become QBs), and the first `stars` K and P
    prospects get every rating at 99 while the other K/P prospects get 15, so those sit far above their position's
    class mean. One full native 224-pick draft. Returns K/P counts per display round and the stars' edges."""
    from collections import Counter
    from tests.nfl2k5_supersim_draft_fixture import Machine, signed_save
    m = Machine(payload, trace_writes=False)
    m.load_franchise(signed_save())
    m.seed(seed)
    m.put(0xE576A4, 5)
    m.put(0xE60134, 1)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress text/render only")
    for t in range(32):
        team = m.team_base + 500 * t
        for i in range(m.uc.mem_read(team + 0x11C, 1)[0]):
            player = m.get(team + 4 * i)
            if m.uc.mem_read(player + 0x35, 1)[0] in (1, 2):
                m.uc.mem_write(player + 0x35, b"\x00")
    n, base, seen = m.get(m.root), m.get(m.root + 4), Counter()
    for i in range(n):
        player = base + 84 * i
        position = m.uc.mem_read(player + 0x35, 1)[0]
        if m.uc.mem_read(player + 8, 1)[0] & 0x10 and position in (1, 2):
            star = seen[position] < stars
            seen[position] += 1
            m.uc.mem_write(player + 0x36, bytes([99 if star else 15]) * (0x54 - 0x36))
    stub = Machine.STOP + 0x100   # call 0x246D80 (the class sums' own rating call); fstp dword [0x3000F00]; ret
    m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", 0x246D80 - (stub + 5)) + bytes.fromhex("d91d000f0003c3"))
    edges = {}
    for position in (1, 2):
        ratings = []
        for i in range(n):
            player = base + 84 * i
            if m.uc.mem_read(player + 8, 1)[0] & 0x10 and m.uc.mem_read(player + 0x35, 1)[0] == position:
                m.call(stub, ecx=player, edx=1, budget=200000)
                ratings.append(m.f32(0x3000F00))
        mean = sum(ratings) / len(ratings)
        edges[position] = sorted((r - mean for r in ratings), reverse=True)[:stars]
    m.call(0x325A30)
    rows = Counter()
    for _pick in range(224):
        round_number = m.get(0xE3C0A8)
        team = m.call(0x3254D0)
        count = m.uc.mem_read(team + 0x11C, 1)[0]
        m.call(0x325B90, ecx=0, budget=10000000)
        if m.uc.mem_read(team + 0x11C, 1)[0] > count:
            position = m.uc.mem_read(m.get(team + 4 * count) + 0x35, 1)[0]
            if position in (1, 2):
                rows[(round_number, position)] += 1
        m.call(0x325A50)
    return rows, edges, m.call(0x325D00)


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeSpecialistCapTests(unittest.TestCase):
    """The outlier gate's worst case: every club needs a K and a P and five of each are true outliers."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import signed_save
        signed_save()                                # skip early without the private franchise
        cls.applied = ai.apply(retail_bytes())[0]

    def test_one_specialist_before_round_five(self):
        rows, edges, done = _worst_case_draft(self.applied)
        self.assertEqual(done, 1)
        for position in (1, 2):
            self.assertTrue(all(edge > ai.SPECIAL_EDGE for edge in edges[position]), edges)
        early = sum(rows[(r, p)] for r in range(4) for p in (1, 2))
        self.assertEqual(early, ai.EARLY_SPECIALIST_CAP)
        for round_number in (4, 5, 6):
            self.assertLessEqual(rows[(round_number, 1)], 1)
            self.assertLessEqual(rows[(round_number, 2)], 1)

    def test_negative_control_the_beta79_head_lets_every_outlier_go_early(self):
        rows, _edges, done = _worst_case_draft(_with_head(self.applied, PREVIOUS_HEAD))
        self.assertEqual(done, 1)
        self.assertGreater(sum(rows[(r, p)] for r in range(4) for p in (1, 2)), ai.EARLY_SPECIALIST_CAP)


if __name__ == "__main__":
    unittest.main()
