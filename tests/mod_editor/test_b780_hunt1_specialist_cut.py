"""b780 hunt1: the stage-6 veteran cap cut never releases a club's last healthy kicker or punter (economy revision 6).

The retail cut (0x2BFAF0, every club from 0x247FF5) releases an overpaid veteran whatever his position. In the
SOFTDRINK 2K28 v0.9 RC franchise (seed 2602) it released Chicago's and Kansas City's only kickers after the draft and the
stage-6 fill replaced neither, so both clubs played the season with no kicker. Revision 6 sends the cut's own release
call (0x2BFBBD) through ``economy_vet_release``: the club's last healthy K or P stays, every other release goes on to the
native release with the cut's own return address.

Each case runs the game's own offseason advance 0x247D40 in stage 6 on the retail executable with the economy (the
b778 fa1 harness): club 0's specialist is made a 12-year veteran paid well over twice his modelled market value with
the club inside 6,000 of the cap, so the retail rule releases him. "Before" is the same image with the cut's native
release call put back (exactly the revision-5 path for that call).
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_star_retention as star_retention
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes, retail_roster

K, P, CUT_RETURN = 1, 2, 0x2BFBC2
NATIVE_RELEASE_CALL = bytes.fromhex("e83eddffff")      # call 0x2BD900 at 0x2BFBBD


def with_native_release(payload: bytes) -> bytes:
    """``payload`` with the cut's release call back to the native release (the revision-5 behaviour of that call)."""
    image = XbeImage(payload)
    out = bytearray(payload)
    at = image.offset(economy.VETERAN_CUT_RELEASE, 5)
    out[at:at + 5] = NATIVE_RELEASE_CALL
    return bytes(out)


def revision_five_money() -> bytes:
    """The money window as revisions 3 to 5 installed it: the fill gate with only the count test (rebuilt here from
    the same gate and the same targets; its digest is the owner's PREVIOUS_REVISION_5 entry)."""
    from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS, WINDOWS
    gate, room = SYMBOLS["economy_fill_gate"], SYMBOLS["economy_fill_room"]
    window = WINDOWS[economy.MONEY_WINDOW]
    stub = bytearray(bytes.fromhex("8b4c24048b54240c"))
    stub += b"\xe8" + struct.pack("<i", room - (gate + len(stub) + 5))
    stub += bytes.fromhex("85c0740f8944240c81ec14010000")
    stub += b"\xe9" + struct.pack("<i", 0x322BB6 - (gate + len(stub) + 5))
    stub += bytes.fromhex("31c0c210000f0b")
    return (window[:gate - economy.MONEY_WINDOW] + bytes(stub)).ljust(len(window), b"\xcc")


def with_revision_five_gate(payload: bytes) -> bytes:
    """``payload`` with the fill gate of revision 5 (a club of 54 or more signs nobody)."""
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    image = XbeImage(payload)
    out = bytearray(payload)
    at = image.offset(economy.MONEY_WINDOW, 198)
    out[at:at + 198] = revision_five_money()
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


class SiteTests(unittest.TestCase):
    def test_the_release_guard_is_revision_six_and_reads_back(self):
        self.assertIn(economy.REVISION, (6, 7))     # b780 econ3: revision 7 keeps the guard's call (its pick moved)
        site = next(s for s in economy.sites() if s.va == economy.VETERAN_CUT_RELEASE)
        self.assertEqual(site.patched[:1], b"\xe8")
        target = (economy.VETERAN_CUT_RELEASE + 5 + struct.unpack_from("<i", site.patched, 1)[0]) & 0xFFFFFFFF
        self.assertEqual(target, economy.SYMBOLS["economy_vet_release"])
        self.assertTrue(economy.ROSTER_M_WINDOW <= target < economy.ROSTER_M_WINDOW + 160)
        self.assertNotIn(economy.VETERAN_CUT_RELEASE, [s.va for s in economy.sites(5)])
        retail = retail_bytes()
        self.assertEqual(XbeImage(retail).read(economy.VETERAN_CUT_RELEASE, 5), NATIVE_RELEASE_CALL)
        applied, _ = economy.apply(retail)
        self.assertEqual(economy.status(applied), "applied")
        self.assertEqual(XbeImage(applied).read(economy.VETERAN_CUT_RELEASE, 5), site.patched)

    def test_a_revision_five_image_reads_legacy_and_upgrades_in_place(self):
        applied, _ = economy.apply(retail_bytes())
        # b780 econ3: revision 7's sites go back to their revision-6 bytes first (a revision-5 image has neither)
        six = applied
        if economy.REVISION >= 7:
            from tests.mod_editor.test_b780_econ3_roster_drift import revision_six
            six = revision_six(applied)
        image = XbeImage(six)
        before = bytearray(six)
        # revision 5: the native release call and roster_m without the guard (the guard's bytes back to int3)
        at = image.offset(economy.VETERAN_CUT_RELEASE, 5)
        before[at:at + 5] = NATIVE_RELEASE_CALL
        window = image.offset(economy.ROSTER_M_WINDOW, 160)
        guard = economy.SYMBOLS["economy_vet_release"] - economy.ROSTER_M_WINDOW
        before[window + guard:window + 160] = b"\xcc" * (160 - guard)
        money = image.offset(economy.MONEY_WINDOW, 198)
        before[money:money + 198] = revision_five_money()
        revision_five = bytes(before)
        # and (when a released executable is here) roster_a and roster_h without the in-season K/P cover, the bytes
        # every revision up to 5 installed there (without_cover recomputes the section digests either way)
        roster_a = released_roster_a()
        revision_five = without_cover(revision_five, roster_a if roster_a is not None
                                      else image.read(economy.ROSTER_A_WINDOW, 448))
        self.assertEqual(economy.status(revision_five), "legacy")
        upgraded, receipt = economy.apply(revision_five)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        self.assertEqual(upgraded, applied)

    def test_the_windows_without_the_cover_are_the_ones_the_owner_recognises(self):
        import hashlib
        roster_a = released_roster_a()
        if roster_a is None:
            self.skipTest("no released v0.8 / v0.9 RC executable in this scratch")
        old = XbeImage(without_cover(economy.apply(retail_bytes())[0], roster_a))
        for va in (economy.ROSTER_A_WINDOW, economy.ROSTER_H_WINDOW):
            with self.subTest(window=hex(va)):
                self.assertEqual(hashlib.sha256(old.read(va, len(economy.WINDOWS[va]))).hexdigest(),
                                 economy.PREVIOUS_REVISION_5[va])

    def test_the_revision_five_money_window_is_the_one_the_owner_recognises(self):
        import hashlib
        self.assertEqual(hashlib.sha256(revision_five_money()).hexdigest(),
                         economy.PREVIOUS_REVISION_5[economy.MONEY_WINDOW])

    def test_the_gate_skips_into_the_room_rule_after_its_count_test(self):
        # economy_fill_room + 9 is its body after "cmp byte [ecx+0x11C], 53; ja": the specialist path enters there
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS, WINDOWS
        room = SYMBOLS["economy_fill_room"]
        window = next(va for va in WINDOWS if va <= room < va + len(WINDOWS[va]))
        head = WINDOWS[window][room - window:room - window + 10]
        self.assertEqual(head[:7], bytes.fromhex("80b91c01000035"))
        self.assertEqual(head[7], 0x77)                        # ja (the refusal)
        self.assertEqual(head[9], 0x55)                        # push ebp: the body
        gate = SYMBOLS["economy_fill_gate"]
        code = WINDOWS[economy.MONEY_WINDOW][gate - economy.MONEY_WINDOW:]
        calls = [gate + i + 5 + struct.unpack_from("<i", code, i + 1)[0] for i in range(len(code) - 5) if code[i] == 0xE8]
        self.assertIn(room + 9, calls)
        self.assertIn(room, calls)

    def test_star_retention_still_recognises_the_cut(self):
        applied, _ = economy.apply(retail_bytes())
        self.assertEqual(star_retention.status(applied), "retail")
        both, _ = star_retention.apply(applied)
        self.assertEqual((star_retention.status(both), economy.status(both)), ("applied", "applied"))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeStageSixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.after, _ = economy.apply(retail_bytes())
        cls.before = with_native_release(cls.after)
        cls.body = retail_roster()

    def run_stage_six(self, payload, position, *, extra=None):
        """Stage 6 with club 0's only ``position`` player overpaid; ``extra`` = None, "healthy" or "injured" adds a
        second player at that position. Returns (the specialist, released players of the cut, club members)."""
        from tools.franchise_economy.probe import start
        from tests.franchise_economy_legacy import no_restructure_room
        m = start(self.body, payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        members = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        at_position = [p for p in members if m.uc.mem_read(p + 0x35, 1)[0] == position]
        self.assertEqual(len(at_position), 1, "the retail club 0 carries one player at the position")
        p = at_position[0]
        if extra:
            other = next(q for q in members if m.uc.mem_read(q + 0x35, 1)[0] == 3)     # a receiver made a second one
            m.uc.mem_write(other + 0x35, bytes([position]))
            word = m.get(other + 0x20) & 0x3FFFFF
            m.put(other + 0x20, word | (0x80000000 | (3 << 22) if extra == "injured" else 0))
        raw = bytearray(m.uc.mem_read(p, 84))
        raw[0x24] = (raw[0x24] & 0xF0) | 3            # 4-year deal, 3 left
        raw[0x25] = (raw[0x25] & 0xE0) | 12           # 12 years pro
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 4
        struct.pack_into("<H", raw, 10, 40000)        # far over twice any market value
        m.uc.mem_write(p, bytes(raw))
        m.put(0xE576B8, 1)
        market = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 3)) & 0xFFFF
        self.assertGreater(m.call(0xE6380, ecx=p), market * 21 // 10)
        no_restructure_room(m, team, {p})
        m.call(0xC3F00, ecx=team)
        # b780 econ3 (revision 7, Q45): the cut acts only while the club cannot fit two league-minimum signings
        m.put(0xE3C278, m.get(team + 0x124) + 100)    # short of that line (was: within 6000 of the cap)
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333)):
            self.assertEqual(m.reg(name), value)
        cut = [q for q, caller in released if caller == CUT_RETURN]
        after = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        return p, cut, after

    def test_before_the_guard_the_cut_released_the_only_kicker(self):
        # (whether the stage-6 fill then signs a kicker depends on the club's cap and squad room: here the release
        # itself makes room, in the v0.9 RC franchise it did not)
        p, cut, members = self.run_stage_six(self.before, K)
        self.assertIn(p, cut)

    def test_the_only_kicker_stays(self):
        p, cut, members = self.run_stage_six(self.after, K)
        self.assertNotIn(p, cut)
        self.assertIn(p, members)

    def test_the_only_punter_stays(self):
        p, cut, members = self.run_stage_six(self.after, P)
        self.assertNotIn(p, cut)
        self.assertIn(p, members)

    def test_a_kicker_with_a_healthy_second_kicker_is_still_cut(self):
        p, cut, members = self.run_stage_six(self.after, K, extra="healthy")
        self.assertIn(p, cut)

    def test_a_kicker_whose_only_other_kicker_is_hurt_stays(self):
        p, cut, members = self.run_stage_six(self.after, K, extra="injured")
        self.assertNotIn(p, cut)
        self.assertIn(p, members)



@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class CampSigningTests(unittest.TestCase):
    """The native CPU signing 0x322BB0 (through the economy's fill gate) for club 0 in camp (stage 6, the native
    65-man limit), grown to 58 with one-year free agents and with no kicker, with cap room."""

    @classmethod
    def setUpClass(cls):
        cls.after, _ = economy.apply(retail_bytes())
        cls.before = with_revision_five_gate(cls.after)
        cls.body = retail_roster()

    def sign(self, payload, position, *, remove_kicker=True, size=58):
        from tools.franchise_economy.probe import start
        m = start(self.body, payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team, lst = m.team_base, m.root + 0x38
        members = lambda: [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        if remove_kicker:
            for p in members():
                if m.uc.mem_read(p + 0x35, 1)[0] == K:
                    m.uc.mem_write(p + 0x35, bytes([3]))        # the club's kicker is listed as a receiver: no K
        m.put(0xE576A4, 5)
        free = [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]
        for p in free:
            if m.uc.mem_read(team + 0x11C, 1)[0] >= size:
                break
            raw = bytearray(m.uc.mem_read(p, 84))
            if raw[0x35] in (K, P) or raw[0x35] >= 17:
                continue
            m.call(0x2425C0, ecx=lst, edx=p)
            raw[0x27] = (raw[0x27] & 0xF0) | 1; raw[0x24] = (raw[0x24] & 0xF0) | 1
            struct.pack_into("<H", raw, 10, 30)
            m.uc.mem_write(p, bytes(raw))
            self.assertTrue(m.call(0xC3EE0, ecx=team, edx=p))
        self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], size)
        m.put(0xE576A4, 6)
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 40000)         # room for a kicker
        ok = m.call(0x322BB0, args=(team, position, 0xFFFF, m.ARENA + 0x1A0000), budget=200_000_000)
        at = [p for p in members() if m.uc.mem_read(p + 0x35, 1)[0] == position]
        return ok, at, m.uc.mem_read(team + 0x11C, 1)[0]

    def test_a_camp_of_58_with_no_kicker_signs_one(self):
        ok, kickers, count = self.sign(self.after, K)
        self.assertTrue(ok)
        self.assertEqual((len(kickers), count), (1, 59))

    def test_before_the_rule_the_same_camp_signed_nobody(self):
        ok, kickers, count = self.sign(self.before, K)
        self.assertFalse(ok)
        self.assertEqual((len(kickers), count), (0, 58))

    def test_any_other_position_keeps_the_count_test(self):
        ok, receivers, count = self.sign(self.after, 3, remove_kicker=False)
        self.assertFalse(ok)
        self.assertEqual(count, 58)



def without_cover(payload: bytes, roster_a: bytes) -> bytes:
    """``payload`` with roster_a (upkeep) and roster_h as revision 6 had them before the in-season K/P cover: the
    upkeep without its call, and the class top-up window's tail as int3 padding (``roster_a``: those 448 bytes from a
    released v0.8 or v0.9 RC executable, which carry them)."""
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    image, out = XbeImage(payload), bytearray(payload)
    head = economy.WINDOWS[economy.ROSTER_H_WINDOW]
    cover = economy.SYMBOLS["economy_cover"] - economy.ROSTER_H_WINDOW
    for va, code in ((economy.ROSTER_A_WINDOW, roster_a), (economy.ROSTER_H_WINDOW, head[:cover] + b"\xcc" * (len(head) - cover))):
        at = image.offset(va, len(code))
        out[at:at + len(code)] = code
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


def released_roster_a() -> bytes | None:
    import os
    for name in ("NFL2K5_V08_XBE", "NFL2K5_B780_RC_XBE"):
        path = Path(os.environ.get(name, "/nonexistent"))
        if path.is_file():
            return XbeImage(path.read_bytes()).read(economy.ROSTER_A_WINDOW, len(economy.WINDOWS[economy.ROSTER_A_WINDOW]))
    return None


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class InSeasonCoverTests(unittest.TestCase):
    """FIXWAVE #5: a played game can hurt a kicker or a punter (the collision injury chain 0x137520 / 0x137680 ->
    0x1373C0 -> 0x136B10 tests no position) and the native need counts injured players, so the CPU fill never asked for
    a replacement. Club 0, a computer club grown to 53 with one-year free agents, in the regular season (stage 8) with
    its only kicker hurt for three weeks and cap room; the free-agent pool holds healthy kickers. The weekly CPU pass
    (economy_week, the fills off) runs every computer club's upkeep, which now covers the hurt specialist."""

    @classmethod
    def setUpClass(cls):
        cls.after, _ = economy.apply(retail_bytes())
        cls.body = retail_roster()
        roster_a = released_roster_a()
        cls.before = without_cover(cls.after, roster_a) if roster_a is not None else None

    def season(self, payload, *, hurt=True, size=53, stage=8, direct=False):
        from tools.franchise_economy.probe import start
        m = start(self.body, payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team, lst = m.team_base, m.root + 0x38
        members = lambda: [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        for t in range(34):
            m.put(0xE5775C + 4 * t, 0)                        # every club the computer's
        m.put(0xE576A4, 5)
        free = [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]
        for p in free:
            if m.uc.mem_read(team + 0x11C, 1)[0] >= size:
                break
            raw = bytearray(m.uc.mem_read(p, 84))
            if raw[0x35] in (K, P) or raw[0x35] >= 17:
                continue
            m.call(0x2425C0, ecx=lst, edx=p)
            raw[0x27] = (raw[0x27] & 0xF0) | 1; raw[0x24] = (raw[0x24] & 0xF0) | 1
            struct.pack_into("<H", raw, 10, 30)
            m.uc.mem_write(p, bytes(raw))
            self.assertTrue(m.call(0xC3EE0, ecx=team, edx=p))
        while m.uc.mem_read(team + 0x11C, 1)[0] > size:          # a club that starts above it drops its last listed
            m.call(0x2BD900, ecx=team, edx=members()[-1], args=(1, 0))
        kickers = [p for p in members() if m.uc.mem_read(p + 0x35, 1)[0] == K]
        self.assertEqual(len(kickers), 1)
        if hurt:
            m.put(kickers[0] + 0x20, (m.get(kickers[0] + 0x20) & 0x003FFFFF) | 0x80000000 | (3 << 22))
        m.put(0xE576A4, stage)
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 40000)
        before = members()
        menu = m.ARENA + 0x1A0000
        if direct:
            m.call(economy.SYMBOLS["economy_cover"], ecx=team, edx=menu, budget=400_000_000)
        else:
            zero = struct.unpack("<I", struct.pack("<f", 0.0))[0]
            m.call(economy.SYMBOLS["economy_week"], ecx=menu, edx=0, args=(zero, zero), budget=2_000_000_000)
        after = members()
        healthy = [p for p in after if m.uc.mem_read(p + 0x35, 1)[0] == K and not m.uc.mem_read(p + 0x23, 1)[0] & 0x80]
        released = [p for p in before if p not in after]
        signed = [p for p in after if p not in before]
        positions = lambda ps: [m.uc.mem_read(p + 0x35, 1)[0] for p in ps]
        return dict(count=len(after), healthy=len(healthy), hurt_kept=kickers[0] in after,
                    released=positions(released), signed=positions(signed))

    def test_a_hurt_kicker_is_covered_and_the_club_stays_at_53(self):
        got = self.season(self.after)
        self.assertEqual((got["count"], got["healthy"], got["hurt_kept"]), (53, 1, True))
        self.assertEqual(got["signed"], [K])
        self.assertEqual(len(got["released"]), 1)
        self.assertNotIn(got["released"][0], (K, P))

    def test_the_cover_alone_makes_room_with_the_smart_cut(self):
        got = self.season(self.after, direct=True)
        self.assertEqual((got["count"], got["healthy"], got["hurt_kept"], got["signed"]), (53, 1, True, [K]))
        self.assertEqual(len(got["released"]), 1)

    def test_a_club_with_room_signs_without_a_cut(self):
        got = self.season(self.after, size=52, direct=True)
        self.assertEqual((got["count"], got["healthy"], got["released"], got["signed"]), (53, 1, [], [K]))

    def test_a_healthy_kicker_changes_nothing(self):
        got = self.season(self.after, hurt=False, direct=True)
        self.assertEqual((got["count"], got["released"], got["signed"]), (53, [], []))

    def test_camp_is_left_to_the_fill_gate(self):
        # stage 7: the upkeep does not run the cover (camp limits differ; revision 6's gate rule covers a club with no K)
        got = self.season(self.after, stage=7)
        self.assertEqual((got["healthy"], got["signed"].count(K)), (0, 0))

    def test_before_the_cover_the_club_kept_only_its_hurt_kicker(self):
        if self.before is None:
            self.skipTest("no released v0.8 / v0.9 RC executable in this scratch")
        got = self.season(self.before)
        self.assertEqual((got["count"], got["healthy"], got["signed"].count(K)), (53, 0, 0))


if __name__ == "__main__":
    unittest.main()
