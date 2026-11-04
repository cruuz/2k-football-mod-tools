"""b780 hunt6: the weekly CPU auto-depth skips the all-star teams (depth locks revision 5).

The postseason schedule (0x2A8261..0x2A827E, retail) puts the AFC and NFC Pro Bowl teams in league slots 32 and 33 until
the next rollover removes them (0x247B51..0x247B6A). The weekly auto-depth 0x2BDCF0 walks TEAM_COUNT/TEAM_AT, so it sorted
both Pro Bowl teams after the 32 clubs, before every playoff game. Depth rank and side live in the player record (+0x28),
which a Pro Bowler shares with his club, so each one took his Pro Bowl row on his own club (hunt1's franchise run on the
v0.9 RC: 54 of 80 Pro Bowlers moved, 16 clubs lost a starter row, Buffalo had no QB1, LAC and PHI started their backups in
the Wild Card games, LAC's chart then had its third QB at QB1, and the locks kept it so for the whole postseason).
Revision 5 sends a kind-1 team (team +0x128 == 1) to the loop tail.

Three layers of proof:
  * bytes: the revision-5 sites, the 17-byte check, the in-place upgrade of revision-4 images (retail-built, and the
    released v0.8 executable when NFL2K5_V08_XBE is set; the v0.9 RC when NFL2K5_B780_RC_XBE is set);
  * the real weekly routine on synthetic teams (the depth-locks harness): a Pro Bowl team that shares a club's starter
    rewrites his club row on revision 4 and leaves it alone on revision 5; kind 0 and 2 teams are still sorted, a user
    club still gets the compactor pass;
  * the game's own franchise flow (NFL2K5_V08_XBE + NFL2K5_V08_ROST_BODY): a franchise started from the v0.8 roster, its
    regular season skipped, the native postseason schedule appends the Pro Bowl teams; the weekly pass with them in the
    league must equal the pass without them, player for player (revision 5), and differ on revision 4.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))
from mod_editor.core import nfl2k5_depth_locks as locks
from mod_editor.core import nfl2k5_returner_fix as returners
from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_CPU = importlib.util.find_spec("unicorn") is not None
HAVE_DISASM = importlib.util.find_spec("capstone") is not None


def _env(name):
    value = os.environ.get(name, "")
    return Path(value) if value else None


V08_XBE = _env("NFL2K5_V08_XBE")
V08_XBE_SHA256 = "5f987568bc88122f566e30cb5bb8a574acde4549b915b6f2514beab37ab3e9f3"
V08_ROST = _env("NFL2K5_V08_ROST_BODY")
RC_XBE = _env("NFL2K5_B780_RC_XBE")  # optional: the v0.9 RC default.xbe (sha256 1a476d94...)
RC_XBE_SHA256 = "1a476d94ee64acf5bb287736cc06fea8f8f8181f3ee98e2b9586006c5659c9da"


def _have(path):
    return path is not None and path.is_file()


def _revision_image(revision):
    """A complete install of an older revision on the retail executable (with the returner fix, as shipped)."""
    data = bytearray(locks.apply(returners.apply(XBE.read_bytes())[0])[0])
    image = XbeImage(bytes(data))
    for site in locks.sites("retail", revision):
        off = image.offset(site.va, len(site.before))
        data[off:off + len(site.after)] = site.after
    for s in strength._sections(bytes(data)):
        data[s.header_offset + 36:s.header_offset + 56] = strength.section_digest(bytes(data), s)
    return bytes(data)


def _ranges(a, b):
    out = []
    for i in (i for i in range(len(a)) if a[i] != b[i]):
        if out and i == out[-1][1]:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return [(lo, hi - lo) for lo, hi in out]


class BytesTests(unittest.TestCase):
    def test_revision5_sites(self):
        self.assertEqual(locks.REVISION, 5)
        self.assertEqual(locks.SWAP_VA + len(locks.V4_PATCHED_SWAP), locks.ALL_STAR_SKIP_VA)
        self.assertEqual(locks.PATCHED_SWAP[:len(locks.V4_PATCHED_SWAP)], locks.V4_PATCHED_SWAP)
        self.assertLessEqual(len(locks.PATCHED_SWAP), len(locks.RETAIL_SWAP))
        site = {s.label: s for s in locks.sites("retail")}["weekly_all_star_skip"]
        self.assertEqual((site.va, site.before, site.after), (0x2BDD1B, bytes.fromhex("e8100fe8ff"),
                                                              bytes.fromhex("e8de4ff8ff")))
        old = {s.label: s for s in locks.sites("retail", 4)}
        self.assertEqual(old["weekly_all_star_skip"].after, old["weekly_all_star_skip"].before)
        self.assertEqual(old["screen_swap"].after[len(locks.V4_PATCHED_SWAP):],
                         b"\x90" * (len(locks.RETAIL_SWAP) - len(locks.V4_PATCHED_SWAP)))

    @unittest.skipUnless(HAVE_DISASM, "capstone required")
    def test_the_check_reads_the_team_kind_and_exits_through_the_loop_tail(self):
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        rows = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(locks.ALL_STAR_SKIP, locks.ALL_STAR_SKIP_VA)]
        self.assertEqual(rows, [(0x242CFE, "cmp", "dword ptr [ecx + 0x128], 1"), (0x242D05, "jne", "0x242d0a"),
                                (0x242D07, "pop", "eax"), (0x242D08, "jmp", "0x242cf9"),
                                (0x242D0A, "jmp", "0x13ec30")])
        call = next(md.disasm(locks.PATCHED_ALL_STAR, locks.ALL_STAR_VA))
        self.assertEqual((call.mnemonic, call.op_str), ("call", "0x242cfe"))
        # 0x242CF9 is revision 2's ``jmp 0x2BDFD4`` (the loop tail: next team)
        at = 0x242CF9 - locks.SWAP_VA
        tail = next(md.disasm(locks.PATCHED_SWAP[at:at + 5], 0x242CF9))
        self.assertEqual((tail.mnemonic, tail.op_str), ("jmp", "0x2bdfd4"))


@unittest.skipUnless(XBE.is_file(), "retail extraction required")
class UpgradeTests(unittest.TestCase):
    def _upgrade(self, data, layout_check=None):
        state = locks.read_any(data)
        self.assertEqual((state["status"], state["revision"]), ("legacy", 4))
        patched, receipt = locks.apply(data)
        self.assertEqual(locks.read_any(patched)["status"], "applied")
        self.assertEqual((receipt["revision"], receipt["upgraded_from"]), (5, 4))
        self.assertEqual(sorted(e["label"] for e in receipt["edits"]), ["screen_swap", "weekly_all_star_skip"])
        image = XbeImage(patched)
        text = strength._section_for_offset(strength._sections(patched), image.offset(locks.ALL_STAR_VA, 5))
        ranges = _ranges(data, patched)
        owned = {image.offset(locks.ALL_STAR_SKIP_VA, 17): 17, image.offset(locks.ALL_STAR_VA + 1, 3): 3}
        digest = range(text.header_offset + 36, text.header_offset + 56)
        # exactly the 17-byte check, the call's three changed displacement bytes and the .text section digest (b780
        # st1: a digest byte that happens to stay equal splits the digest's run, so the digest is checked as a field)
        self.assertEqual({lo: n for lo, n in ranges if lo not in digest}, owned)
        self.assertTrue(all(lo + n <= digest.stop for lo, n in ranges if lo in digest))
        self.assertNotEqual(patched[digest.start:digest.stop], data[digest.start:digest.stop])
        self.assertEqual(image.read(locks.ALL_STAR_SKIP_VA, 17), locks.ALL_STAR_SKIP)
        self.assertEqual(image.read(locks.ALL_STAR_VA, 5), locks.PATCHED_ALL_STAR)
        self.assertEqual(locks.apply(patched)[0], patched)
        return patched

    def test_revision4_install_upgrades_in_place(self):
        self._upgrade(_revision_image(4))

    def test_older_revisions_still_upgrade(self):
        for revision in (1, 2, 3):
            with self.subTest(revision=revision):
                data = _revision_image(revision)
                self.assertEqual((locks.read_any(data)["status"], locks.read_any(data)["revision"]), ("legacy", revision))
                patched = locks.apply(data)[0]
                self.assertEqual(locks.read_any(patched)["status"], "applied")
                self.assertEqual(XbeImage(patched).read(locks.ALL_STAR_VA, 5), locks.PATCHED_ALL_STAR)

    def test_retail_apply_includes_revision5(self):
        patched = locks.apply(returners.apply(XBE.read_bytes())[0])[0]
        self.assertEqual(locks.read_any(patched)["status"], "applied")
        image = XbeImage(patched)
        self.assertEqual(image.read(locks.ALL_STAR_SKIP_VA, 17), locks.ALL_STAR_SKIP)
        # b780 st1: the returner fix (applied first in every build) owns the loop head's call and sends it to the
        # same skip in its own site; depth locks leaves it. Without the returner fix, revision 5 points it at its own.
        self.assertEqual(image.read(locks.ALL_STAR_VA, 5), returners.all_star_call_bytes())
        alone = XbeImage(locks.apply(XBE.read_bytes())[0])
        self.assertEqual(alone.read(locks.ALL_STAR_VA, 5), locks.PATCHED_ALL_STAR)

    def test_a_foreign_call_target_refuses(self):
        data = bytearray(locks.apply(returners.apply(XBE.read_bytes())[0])[0])
        off = XbeImage(bytes(data)).offset(locks.ALL_STAR_VA, 5)
        data[off + 1] ^= 0x10
        self.assertEqual(locks.status(bytes(data)), "foreign")

    @unittest.skipUnless(_have(V08_XBE), "NFL2K5_V08_XBE (the released v0.8 default.xbe) required")
    def test_released_v08_upgrades_in_place(self):
        raw = V08_XBE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != V08_XBE_SHA256:
            self.skipTest("the v0.8 XBE pin differs")
        self._upgrade(raw)

    @unittest.skipUnless(_have(RC_XBE), "NFL2K5_B780_RC_XBE (the v0.9 RC default.xbe) not set")
    def test_v09_rc_upgrades_in_place(self):
        raw = RC_XBE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != RC_XBE_SHA256:
            self.skipTest("the RC XBE pin differs")
        self._upgrade(raw)


@unittest.skipUnless(XBE.is_file() and HAVE_CPU, "retail extraction and Unicorn required")
class WeeklyPassTests(unittest.TestCase):
    """The real 0x2BDCF0 (TEAM_COUNT/TEAM_AT/user test stubbed by the depth-locks harness) on synthetic teams."""

    @classmethod
    def setUpClass(cls):
        from test_nfl2k5_depth_locks import CPU, record, fields, TEAM, PLAYERS
        cls.CPU, cls.TEAM, cls.PLAYERS = CPU, TEAM, PLAYERS
        cls.record, cls.fields = staticmethod(record), staticmethod(fields)
        cls.current = locks.apply(returners.apply(XBE.read_bytes())[0])[0]
        cls.revision4 = _revision_image(4)

    def _league(self, data, kind=1):
        """Club (kind 0): QB A starter (.80, rank 0 side 1, locked) and QB B backup (.60, rank 1 side 0, locked).
        Second team (``kind``): QB X (.95, another club's starter, rank 0 side 2, locked) and QB A, a Pro Bowler shape."""
        r, T, P = self.record, self.TEAM, self.PLAYERS
        cpu = self.CPU(data)
        players = [r(position=0, rank=0, side=1, bits=3, score=.80), r(position=0, rank=1, side=0, bits=3, score=.60),
                   r(position=0, rank=0, side=2, bits=3, score=.95)]
        cpu.seed(players, order=[0, 1])
        second = bytearray(500)
        for i, index in enumerate((2, 0)):
            struct.pack_into("<I", second, 4 * i, P + 84 * index)
        second[0x11C] = 2
        second[0x194:0x19A] = b"\xff" * 6
        struct.pack_into("<I", second, 0x128, kind)
        cpu.uc.mem_write(T + 500, bytes(second))
        cpu.teams = [T, T + 500]
        return cpu

    def test_pro_bowl_team_rewrote_the_club_starter_on_revision4(self):
        cpu = self._league(self.revision4)
        cpu.run(0x2BDCF0)
        a, b = self.fields(cpu.player(0)), self.fields(cpu.player(1))
        # the second team's sort seats A behind X: the club keeps two QBs at rank 1 and none at rank 0
        self.assertEqual((a[0], b[0]), (1, 1))

    def test_revision5_skips_the_all_star_team(self):
        cpu = self._league(self.current)
        before_team = bytes(cpu.uc.mem_read(self.TEAM + 500, 500))
        before_x = cpu.player(2)
        cpu.run(0x2BDCF0)
        self.assertEqual([self.fields(cpu.player(i))[:2] for i in range(2)], [(0, 1), (1, 0)])
        self.assertEqual(bytes(cpu.uc.mem_read(self.TEAM + 500, 500)), before_team)  # not touched at all
        self.assertEqual(cpu.player(2), before_x)
        # and the result equals the club alone in the league
        alone = self._league(self.current)
        alone.teams = [self.TEAM]
        alone.run(0x2BDCF0)
        self.assertEqual([cpu.player(i) for i in range(3)], [alone.player(i) for i in range(3)])
        self.assertEqual(cpu.team(), alone.team())

    def test_clubs_and_created_teams_are_still_sorted(self):
        for kind in (0, 2):
            with self.subTest(kind=kind):
                cpu = self._league(self.current, kind=kind)
                cpu.run(0x2BDCF0)
                # a sorted second team writes A's shared row (as retail does for any team in the league)
                self.assertEqual(self.fields(cpu.player(0))[0], 1)

    def test_a_user_club_still_gets_the_compactor_pass(self):
        r = self.record
        cpu = self.CPU(self.current)
        cpu.seed([r(rank=0, bits=1, score=.1), r(rank=1, score=.9)])
        cpu.human = True
        cpu.run(0x2BDCF0)
        self.assertEqual([self.fields(cpu.player(i)) for i in range(2)], [(0, 0, 1), (1, 1, 0)])
        self.assertTrue(cpu.compactor_calls)


# ------------------------------------------------------------------------------------- the game's own postseason
POS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")


def postseason_pass(payload, body, seed=2601, ql=15):
    """A franchise from ``body`` on ``payload`` through the game's own flow (hunt1's screener recipe: 0x13EE10 start,
    the regular season skipped, 0x2480B0 into the postseason), then the weekly auto-depth 0x2BDCF0 twice from the same
    memory: with the league as the game left it (the Pro Bowl teams appended) and with TEAM_COUNT held at the 32 clubs.
    Returns a dict: league count, the Pro Bowl team indices, every player's +0x28/+0x52 after each pass, memberships."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    hsize = struct.unpack_from("<I", payload, 0x108)[0]
    m.uc.mem_write(0x10000, payload[:hsize])
    arena_body = Machine.ARENA + 0x300
    m.uc.mem_write(arena_body, body)
    m.put(0xB72804, arena_body)
    m.put(0xB72808, len(body) - 0x40 if len(body) - 0x40 in (0xB0000, 0xCA000) else 0x91000)
    m.put(0xB7280C, len(body) - 0x40)
    m.fixup_roster(Machine.ARENA + 0x340)
    m.seed(seed)
    for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, ql), (0xE60010, ql)):
        m.put(address, value)
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")

    def decision(*_):
        raise AssertionError("unhandled decision dialog")
    m.uc.hook_add(m.u.UC_HOOK_CODE, decision, begin=0x14E440, end=0x14E440)
    m.uc.ctl_flush_tb()
    m.call(0x13EE10, budget=2_000_000_000)
    menu = m.ARENA + 0x1A0000

    def state():
        return tuple(m.get(a) for a in (0xE576A4, 0xE576B4, 0xE576B0))      # stage, week, end week
    for _ in range(8):
        stage, week, end = state()
        if stage == 9:
            break
        if stage == 8 and week < end:
            m.put(0xE576B4, end)                                            # skip the regular season
            continue
        m.call(0x247D40 if stage in (7, 8) and week < end else 0x2480B0, ecx=menu, budget=20_000_000_000)
    if state()[0] != 9:
        raise AssertionError(f"did not reach the postseason: {state()}")
    root = m.root
    pcount, ptable = m.get(root), m.get(root + 4)
    tcount, tbase = m.get(root + 0x18), m.get(root + 0x1C)
    league = m.get(0xE576AC)
    slots = [m.get(0xE5786C + 4 * i) for i in range(league)]
    kinds = {i: m.get(slots[i] + 0x128) for i in range(league)}
    member = {}
    for t in range(min(tcount, 64)):
        raw = bytes(m.uc.mem_read(tbase + 500 * t, 500))
        for i in range(raw[0x11C]):
            member.setdefault(struct.unpack_from("<I", raw, 4 * i)[0], []).append(t)
    writable = [(s.start, s.size) for s in XbeImage(payload).sections if s.writable and s.size]
    regions = [(Machine.ARENA, 0x200000), (0x3000000, 0x10000)] + writable
    saved = [(a, bytes(m.uc.mem_read(a, n))) for a, n in regions]

    def players():
        return [bytes(m.uc.mem_read(ptable + 0x54 * i, 0x54)) for i in range(pcount)]
    m.call(0x2BDCF0, budget=2_000_000_000)
    with_pro_bowl = players()
    for a, raw in saved:
        m.uc.mem_write(a, raw)
    m.put(0xE576AC, 32)
    m.call(0x2BDCF0, budget=2_000_000_000)
    clubs_only = players()
    for a, raw in saved:
        m.uc.mem_write(a, raw)
    return dict(league=league, kinds=kinds, slot_teams=[(slots[i] - tbase) // 500 for i in range(league)],
                with_pro_bowl=with_pro_bowl, clubs_only=clubs_only,
                members=[member.get(ptable + 0x54 * i, []) for i in range(pcount)])


def rank0_holes(rows, members):
    """Club cells (club index, position) with players but none at depth rank 0."""
    cells = {}
    for raw, teams in zip(rows, members):
        for t in teams:
            if t < 32:
                cells.setdefault((t, POS[raw[0x35]] if raw[0x35] < 17 else raw[0x35]), []).append(
                    struct.unpack_from("<H", raw, 0x28)[0] >> 10 & 7)
    return sorted(k for k, v in cells.items() if 0 not in v)


@unittest.skipUnless(_have(V08_XBE) and _have(V08_ROST) and HAVE_CPU,
                     "NFL2K5_V08_XBE + NFL2K5_V08_ROST_BODY (released v0.8) and Unicorn required")
class FranchisePostseasonTests(unittest.TestCase):
    """The game's own postseason on the released v0.8 executable (revision 4) and the same image upgraded to 5."""

    @classmethod
    def setUpClass(cls):
        raw = V08_XBE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != V08_XBE_SHA256:
            raise unittest.SkipTest("the v0.8 XBE pin differs")
        body = V08_ROST.read_bytes()
        cls.v08 = postseason_pass(raw, body)
        cls.fixed = postseason_pass(locks.apply(raw)[0], body)

    def test_the_postseason_puts_both_pro_bowl_teams_in_the_league(self):
        for result in (self.v08, self.fixed):
            self.assertEqual(result["league"], 34)
            self.assertEqual([result["kinds"][i] for i in (32, 33)], [1, 1])
            self.assertTrue(all(result["kinds"][i] != 1 for i in range(32)))

    def test_revision4_moved_pro_bowlers_on_their_clubs(self):
        moved = [i for i, (a, b) in enumerate(zip(self.v08["with_pro_bowl"], self.v08["clubs_only"])) if a != b]
        self.assertTrue(moved)
        pro_bowl = set(self.v08["slot_teams"][32:])
        # every player the extra teams moved is on a Pro Bowl team, and the move is in his depth word (+0x28)
        self.assertTrue(all(set(self.v08["members"][i]) & pro_bowl for i in moved))
        for i in moved:
            a, b = self.v08["with_pro_bowl"][i], self.v08["clubs_only"][i]
            self.assertEqual(a[:0x28] + a[0x2A:0x52] + a[0x53:], b[:0x28] + b[0x2A:0x52] + b[0x53:])

    def test_revision5_pass_equals_the_clubs_only_pass(self):
        self.assertEqual(self.fixed["with_pro_bowl"], self.fixed["clubs_only"])

    def test_no_club_loses_a_starter_row_to_the_pro_bowl(self):
        holes = rank0_holes(self.fixed["with_pro_bowl"], self.fixed["members"])
        self.assertEqual(holes, rank0_holes(self.fixed["clubs_only"], self.fixed["members"]))


if __name__ == "__main__":
    unittest.main()
