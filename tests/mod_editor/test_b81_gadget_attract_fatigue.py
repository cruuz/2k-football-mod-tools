"""Beta 81 Q62 review F3: what put the GAD on the field in six attract snaps (the retail fatigue substitution).

In Codex's attract game on the preview disc (ARZ home, ATL away; the candidate executable 7963a1db ran it), six snaps
had the club's SPECIAL GAD row player on the field at WR slot 9 although none is a gadget play: ATL 45/105 (Olamide
Zaccheaus picked, Zachariah Branch on the field) and ARZ 47/132, 47/151, 47/104, 23/100, 47/109 (Simi Fehoko picked,
Devin Duvernay on the field). Codex's same-page replays of the retail and candidate lineup builders agree with each
other, and the field differs from the builder's output only at slot 9, after the builder
(``nov19/runtime/speed/games/attract/base-personnel-exceptions.json``).

After the builder (0x18A641 returns to 0x18A646) the retail snap path checks every pick with the availability test
0x188440 (call 0x18A6EE), keeps an available, unique pick (0x18A70C) and refills an empty slot with the fallback
0x189360 (result stored at 0x18A799); the final eleven is at [esp+0x4C] at 0x18A7A7. The availability test reads:
- the player's status (roster record +0x24 bits 28-30) against the side's limit (0xE6019C home / 0xE601AC away);
- his stamina: roster record +0x30 is his in-game player object, object +4 his stamina record, and that record's
  float at +4 his current stamina (1.0 rested); object +0x10 is his on-field actor (0 on the bench);
- the thresholds: on the field [0xE60194]/20 (home; away 0xE601A4), on the bench min(1, [0xE60198]/20) (away
  0xE601A8). The boot defaults are 5 and 16, so a benched player needs 0.80 and a player on the field 0.25.

These tests show, with the game's own code under Unicorn on the preview disc's executable (f416b7e8) and the
qualified candidate (7963a1db), same roster and books:
- on the Saints game's frozen pages (Codex's cpu-02 capture), the availability test reads stamina exactly there and
  rejects a benched 0.698 receiver against 0.80 (the case Codex recorded at 0x18856E, where the fallback also brought
  in that club's GAD row player, Bryce Lance);
- for each of the six attract selections, with the live builder line placed at 0x18A646: rested players keep it; the
  slot-9 pick on the bench below 0.80 (or on the field below 0.25) is rejected and the fallback puts the club's GAD row
  player in slot 9, which is exactly the eleven the attract game showed; on both executables (the code after 0x18A646
  is retail in both, so this half cannot differ);
- the whole snap path with the harness's own builder output: the builder gives the same eleven on both executables,
  and its slot-9 pick, tired on the bench, is replaced by the GAD row player the same way;
- the candidate's classifier refuses all six on the preview disc's own books (the rule never acts on them).
The GAD row player is the fourth receiver in both of the club's WR chains (rank 3, side row 3), so he is the
fallback's first receiver who is not already on the field and is rested.

What stays a hypothesis: that Zaccheaus's and Fehoko's stamina was below the threshold at those snaps (or their
on-field binding, which picks the 0.80 or the 0.25 threshold). The attract records carry no stamina readings and no
page atlas. Fehoko lost slot 9 only right after snaps he had played (8 and 10 before 11, 17-18 before 19, 43 before
44, 45-51 before 52, 53-55 before 56), which fits fatigue, but he also played 28-31 without losing it; Zaccheaus had
just been on the opening kickoff's return unit (play 0) with Branch. A status above the side's word at 0x18846C
(record +0x24 bits 28-30 against 0xE6019C / 0xE601AC, 1 by default) would send the slot to the same fallback.

The harness's own builder fills the three WR ordinals from different depth rows than the live game did (ATL: London
at 9, not Zaccheaus; ARZ: Wilson at 9, not Fehoko; also another running back), so the live line is placed at 0x18A646
(the builder's output, the input to everything checked here) from the snap's on-field names with the slot-9 pick
restored. The harness's line is checked too.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_gadget_play as gadget  # noqa: E402
from mod_editor.core import nfl2k5_gadget_play_code as template  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from tests.mod_editor.test_b81_gadget_play import (  # noqa: E402
    BOOKS, CHOICE, PREVIEW_DISC, PREVIEW_XBE_SHA256, QUALIFIED_XBE, QUALIFIED_XBE_SHA256, SIDES, FIXTURES, Native,
    _have_unicorn, _require_disc)

RUNTIME = FIXTURES / "evidence/q62-gadget/nov19/runtime/speed"
SAINTS_CASE = RUNTIME / "games/cpu-02-saints-raiders/personnel-exceptions/q1-p4-away.json"
PAGE_STORE = RUNTIME / "personnel-pages"
FATIGUE_WORDS = (0xE60194, 0xE60198, 0xE6019C, 0xE601A4, 0xE601A8, 0xE601AC)   # home on-field, bench, status; away
AVAILABLE, KEEP, FALLBACK, FINAL = 0x18A6EE, 0x18A70C, 0x18A799, 0x18A7A7
REJECTED_ON_FIELD, REJECTED_ON_BENCH, REJECTED_STATUS = 0x188558, 0x18856D, 0x18846C
PLAYERS = 0x2500000                   # in-game player objects and stamina records, one 0x40 block per player
ATL = ("Michael Penix", "Jake Matthews", "Jawaan Taylor", "Ryan Neuzil", "Matthew Bergeron", "Chris Lindstrom",
       "Kyle Pitts", "Drake London", "Jahan Dotson", "Olamide Zaccheaus", "Bijan Robinson")
ARZ = ("Gardner Minshew", "Jayden Williams", "Elijah Wilkinson", "Hjalte Froholdt", "Isaac Seumalo", "Jon Gaines",
       "Trey McBride", "Reggie Virgil", "Michael Wilson", "Simi Fehoko", "Jeremiyah Love")
# (attract play, side, book asset, formation, play, category the CPU called, live builder line, GAD row player)
CASES = ((1, 1, 308, 45, 105, 4, ATL, "Zachariah Branch"),
         (11, 0, 307, 47, 132, 21, ARZ, "Devin Duvernay"),
         (19, 0, 307, 47, 151, 21, ARZ, "Devin Duvernay"),
         (44, 0, 307, 47, 104, 4, ARZ, "Devin Duvernay"),
         (52, 0, 307, 23, 100, 21, ARZ, "Devin Duvernay"),
         (56, 0, 307, 47, 109, 21, ARZ, "Devin Duvernay"))


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def just_below(value: float) -> float:
    return struct.unpack("<f", struct.pack("<I", struct.unpack("<I", struct.pack("<f", value))[0] - 1))[0]


def boot_fatigue_words(payload: bytes) -> tuple[int, ...]:
    """The fatigue option words after the game's own boot defaults (0x77D20 up to its roster part, 0x77D45)."""
    from tests.nfl2k5_supersim_draft_fixture import Machine
    m = Machine(payload, trace_writes=False)
    m.call(0x77D20, stop=0x77D45, budget=2_000_000)
    return tuple(m.get(a) for a in FATIGUE_WORDS)


class Fatigue:
    """In-game player objects for every player of the two clubs (the harness's roster records carry none)."""

    def __init__(self, native: Native, words, clubs):
        self.n, m = native, native.m
        m.uc.mem_map(PLAYERS, 0x10000)
        for address, value in zip(FATIGUE_WORDS, words):
            m.put(address, value)
        self.names, self.stamina, self.actor = {}, {}, {}
        k = 0
        for side, club in enumerate(clubs):
            team = m.team_base + club * 500
            for i in range(m.get(team + 0x11C) & 0xFF):
                player = m.get(team + 4 * i)
                obj = PLAYERS + 0x40 * k
                k += 1
                m.put(player + 0x30, obj)
                m.put(obj + 4, obj + 0x20)
                m.uc.mem_write(player + 0x34, bytes([side + 1]))   # 1 home, 2 away (as on the Saints game's pages)
                self.stamina[player], self.actor[player] = obj + 0x24, obj + 0x10
                self.set(player, 1.0, False)
                self.names.setdefault(club, {})[self.name(player)] = player

    def name(self, player):
        m, parts = self.n.m, []
        for field in (0x10, 0x14):
            at, raw = m.get(player + field), bytearray()
            while len(raw) < 96 and bytes(m.uc.mem_read(at + len(raw), 2)) != b"\0\0":
                raw += m.uc.mem_read(at + len(raw), 2)
            parts.append(raw.decode("utf-16le"))
        return " ".join(parts)

    def set(self, player, stamina, on_field):
        self.n.m.f32(self.stamina[player], stamina)
        self.n.m.put(self.actor[player], 0xB3F000 if on_field else 0)   # any actor address; only zero is tested

    def rest_all(self):
        for player in self.stamina:
            self.set(player, 1.0, False)


def snap(native: Native, side, line=None):
    """The snap path 0x9F3B7 -> builder -> availability, keep, fallback -> the final eleven at 0x18A7A7.
    ``line`` replaces the builder's output at 0x18A646. Returns (builder output, final eleven, events)."""
    m = native.m
    log = {"available": {}, "stamina": {}, "status": set(), "kept": {}, "fallback": {}}
    current, built = [None], []

    def visit(_uc, address, _size, _user):
        eax, edi, esi, sp = m.reg("EAX"), m.reg("EDI"), m.reg("ESI"), m.reg("ESP")
        if address == 0x18A646:
            if line is not None:
                m.uc.mem_write(sp + 0x74, struct.pack("<11I", *line))
            built.append(native.words(sp + 0x74, 11))
        elif address == AVAILABLE:
            current[0] = esi
        elif address == AVAILABLE + 5:
            log["available"][current[0]] = eax
            current[0] = None
        elif address == REJECTED_STATUS and current[0] is not None:
            log["status"].add(current[0])
        elif address in (REJECTED_ON_FIELD, REJECTED_ON_BENCH) and current[0] is not None:
            log["stamina"][current[0]] = (address == REJECTED_ON_FIELD, m.f32(sp + 8),
                                          m.f32(sp + (12 if address == REJECTED_ON_FIELD else 20)))
        elif address == KEEP:
            log["kept"][esi] = edi
        elif address == FALLBACK:
            log["fallback"][edi] = eax

    hooks = [m.uc.hook_add(m.u.UC_HOOK_CODE, visit, begin=a, end=a)
             for a in (0x18A646, AVAILABLE, AVAILABLE + 5, REJECTED_STATUS, REJECTED_ON_FIELD, REJECTED_ON_BENCH,
                       KEEP, FALLBACK)]
    try:
        m.put(0xE602B8, 12)
        m.put(0xE60280, SIDES[side])
        m.put(0xE60284, SIDES[1 - side])
        m.call(0x9F3B7, ecx=1, ebx=1, stop=FINAL, budget=3_000_000)
        return built[0], native.words(m.reg("ESP") + 0x4C, 11), log
    finally:
        for hook in hooks:
            m.uc.hook_del(hook)


class FrozenPages:
    def __init__(self, atlas, store: Path):
        self.pages = {}
        for address, digest in atlas.items():
            raw = zlib.decompress((store / (digest + ".z")).read_bytes())
            assert len(raw) == 4096 and hashlib.sha256(raw).hexdigest() == digest
            self.pages[int(address, 16)] = raw


@unittest.skipUnless(_have_unicorn(), "Python unicorn")
class SaintsPagesTests(unittest.TestCase):
    """The real game's memory: Codex's frozen pages of the Saints' snap (cpu-02, Q1 play 4, phase 12)."""

    def test_the_availability_test_reads_stamina_from_the_player_object(self):
        if not (SAINTS_CASE.is_file() and PAGE_STORE.is_dir()):
            self.skipTest("Codex's frozen Saints pages are absent")
        import unicorn
        from unicorn import x86_const as x
        case = json.loads(SAINTS_CASE.read_text())
        capture = case["samples"][1]
        self.assertEqual(capture["sample"]["source"]["formation_name"], "Gun Spread Y-Slot")
        pages = FrozenPages(capture["pages"], PAGE_STORE).pages
        vele = 0xB33064                                     # Devaughn Vele, the builder's slot-7 pick
        self.assertEqual(capture["sample"]["player_names"][hex(vele)], "Devaughn Vele")
        recorded = capture["sample"]["original_availability_slots"][7]
        self.assertEqual((recorded["native_rejection_pc"], recorded["availability_return"]), ("0x18856e", 0))
        # There too the fallback brought in the club's GAD row player (NO's WR rank 3 / side row 3).
        self.assertEqual(capture["sample"]["player_names"][hex(recorded["fallback_pick"])], "Bryce Lance")

        def word(address):
            page = address & ~4095
            return struct.unpack_from("<I", pages[page], address - page)[0]

        obj = word(vele + 0x30)
        record = word(obj + 4)
        self.assertEqual(word(obj + 0x10), 0)                # on the bench
        self.assertEqual(struct.unpack("<f", struct.pack("<I", word(record + 4)))[0], recorded["current_stamina"])
        self.assertEqual(tuple(word(a) for a in FATIGUE_WORDS), (5, 16, 1, 5, 16, 1))

        def available(stamina=None, actor=None):
            u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
            for page, raw in pages.items():
                u.mem_map(page, 4096)
                u.mem_write(page, raw)
            if stamina is not None:
                u.mem_write(record + 4, struct.pack("<f", stamina))
            if actor is not None:
                u.mem_write(obj + 0x10, struct.pack("<I", actor))
            stack, stop = 0x50000000, 0x50100000
            u.mem_map(stack - 0x10000, 0x20000)
            u.mem_map(stop, 4096)
            u.mem_write(stack, struct.pack("<II", stop, 1))
            for register, value in ((x.UC_X86_REG_ESP, stack), (x.UC_X86_REG_EDX, vele), (x.UC_X86_REG_EFLAGS, 2)):
                u.reg_write(register, value)
            u.emu_start(0x188440, stop, count=2000)
            return u.reg_read(x.UC_X86_REG_EAX)

        self.assertEqual(available(), 0)                                  # 0.698 on the bench: rejected
        self.assertEqual(available(stamina=f32(0.8)), 1)                  # exactly the bench threshold: kept
        self.assertEqual(available(stamina=just_below(0.8)), 0)
        self.assertEqual(available(actor=0xB3F000), 1)                    # on the field 0.698 >= 0.25: kept
        self.assertEqual(available(stamina=just_below(0.25), actor=0xB3F000), 0)


@unittest.skipUnless(_have_unicorn(), "Python unicorn")
class AttractFatigueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_coach_staff as staff, nfl2k5_roster_records as roster
        if not QUALIFIED_XBE.is_file():
            raise unittest.SkipTest("the qualified candidate executable is absent")
        source, books = _require_disc(PREVIEW_DISC, PREVIEW_XBE_SHA256)
        candidate = QUALIFIED_XBE.read_bytes()
        if hashlib.sha256(candidate).hexdigest() != QUALIFIED_XBE_SHA256:
            raise unittest.SkipTest("the qualified candidate is not the pinned executable")
        with roster._outer_image()(PREVIEW_DISC) as image:
            body = image.read_entry(5)[32:]
        cls.books, cls.words = books, boot_fatigue_words(source)
        clubs = {c.book: c.index for c in staff.clubs()}
        cls.clubs = (clubs["ARZ"], clubs["ATL"])                    # the attract game: ARZ home, ATL away
        cls.machines = {"original": Native(source, body), "candidate": Native(candidate, body)}
        cls.fatigue = {k: Fatigue(n, cls.words, cls.clubs) for k, n in cls.machines.items()}
        for n in cls.machines.values():
            for side, asset in ((0, "307"), (1, "308")):
                n.load(books[asset], side)
                n.club(cls.clubs[side], side, False)

    def setUp(self):
        for f in self.fatigue.values():
            f.rest_all()

    def test_boot_defaults_put_the_thresholds_at_080_on_the_bench_and_025_on_the_field(self):
        self.assertEqual(self.words, (5, 16, 1, 5, 16, 1))
        n, f = self.machines["original"], self.fatigue["original"]
        self.assertEqual(n.m.f32(0x4E6970), 20.0)
        player = f.names[self.clubs[1]]["Olamide Zaccheaus"]
        check = lambda: n.m.call(0x188440, edx=player, args=(1,), budget=2000)   # noqa: E731
        for stamina, on_field, expected in ((1.0, False, 1), (f32(0.8), False, 1), (just_below(0.8), False, 0),
                                            (0.7, True, 1), (f32(0.25), True, 1), (just_below(0.25), True, 0)):
            with self.subTest(stamina=stamina, on_field=on_field):
                f.set(player, stamina, on_field)
                self.assertEqual(check(), expected)
        f.set(player, 0.0, False)
        self.assertEqual(n.m.call(0x188440, edx=player, args=(0,), budget=2000), 1)   # the flag the snap path sets

    def select(self, case):
        _play, side, asset, form, play, category, _line, _gad = case
        book = ip.parse_playbook_resource(self.books[str(asset)], asset_id=str(asset))
        f = book.formations[form]
        link = next(i for i in f.play_links if i.play_index == play)
        chosen = []
        for n in self.machines.values():
            _c, fr, p = n.menu(side, f, link)
            c = n.m.call(0xE05E0, ecx=BOOKS[side], edx=category, budget=32)
            n.commit(side, c, fr, p)
            chosen.append((c, fr))
        return chosen[0]

    def test_the_six_attract_snaps_with_the_live_builder_line(self):
        lookup = gadget.CODE_VA + template.LABELS["select_slot"]
        for case in CASES:
            attract_play, side, _asset, _form, _play, _category, live, gad_name = case
            with self.subTest(play=attract_play):
                c, f = self.select(case)
                # The rule cannot act: the candidate's classifier refuses the selection with the preview's books.
                candidate = self.machines["candidate"]
                self.assertEqual(candidate.m.call(lookup, args=(BOOKS[side], CHOICE[side] + 4, c, f), budget=20000),
                                 0xFFFFFFFF)
                finals = {}
                for label, n in self.machines.items():
                    fatigue, names = self.fatigue[label], self.fatigue[label].names[self.clubs[side]]
                    line = tuple(names[name] for name in live)
                    pick, gad = line[9], names[gad_name]
                    self.assertEqual(n.gad(side), gad, "the GAD row (WR ordinal 7) is not the named player")
                    self.assertNotIn(gad, line)
                    # Rested: every pick is kept.
                    built, final, log = snap(n, side, line)
                    self.assertEqual((built, final, log["fallback"]), (line, line, {}))
                    # The slot-9 pick on the bench below 0.80: rejected, and the fallback brings in the GAD row player.
                    fatigue.set(pick, 0.7, False)
                    built, final, log = snap(n, side, line)
                    self.assertEqual(log["available"][9], 0)
                    self.assertEqual(log["stamina"], {9: (False, f32(0.7), f32(0.8))})
                    self.assertEqual(log["fallback"], {9: gad})
                    field = line[:9] + (gad,) + line[10:]
                    self.assertEqual(final, field)
                    finals[label] = final
                    # Exactly at the threshold he stays; on the field he stays down to 0.25.
                    fatigue.set(pick, f32(0.8), False)
                    self.assertEqual(snap(n, side, line)[1], line)
                    fatigue.set(pick, 0.7, True)
                    self.assertEqual(snap(n, side, line)[1], line)
                    fatigue.set(pick, 0.2, True)
                    final, log = snap(n, side, line)[1:]
                    self.assertEqual((final, log["stamina"][9][:1]), (field, (True,)))
                    fatigue.set(pick, 1.0, False)
                self.assertEqual(finals["original"], finals["candidate"])
                names = {v: k for k, v in self.fatigue["original"].names[self.clubs[side]].items()}
                self.assertEqual([names[p] for p in finals["original"]], [*live[:9], gad_name, live[10]])

    def test_the_harness_builder_line_through_the_whole_snap_path(self):
        """Without placing the live line: the builder runs on both executables (the rule must not act), and its own
        slot-9 pick, tired on the bench, is replaced by the GAD row player through the same fallback."""
        for case in CASES:
            attract_play, side, *_rest, gad_name = case
            with self.subTest(play=attract_play):
                self.select(case)
                results = {}
                for label, n in self.machines.items():
                    fatigue = self.fatigue[label]
                    gad = fatigue.names[self.clubs[side]][gad_name]
                    built, final, log = snap(n, side)
                    self.assertEqual((final, log["fallback"]), (built, {}))
                    self.assertNotIn(gad, built)
                    pick = built[9]
                    fatigue.set(pick, 0.7, False)
                    tired_built, tired_final, log = snap(n, side)
                    fatigue.set(pick, 1.0, False)
                    self.assertEqual(tired_built, built)
                    self.assertEqual(log["fallback"], {9: gad})
                    self.assertEqual(tired_final, built[:9] + (gad,) + built[10:])
                    results[label] = (built, tired_final)
                self.assertEqual(results["original"], results["candidate"])


if __name__ == "__main__":
    unittest.main()
