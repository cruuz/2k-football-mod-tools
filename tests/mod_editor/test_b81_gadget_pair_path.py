"""Beta 81 Q62 review F5: the gadget rule on a merged Playbook pair book (``lookup.c`` paired indices).

With "Separate offensive and defensive playbooks" on, the Playbook pair owner (``nfl2k5_playbook_pair``) builds a
private merged book (one club's offense + another book's defense) and publishes it in its contract
(``pair.contract_va()``: words [2] and [5] are the home and away merged roots). ``tools/gadget_play/lookup.c`` then
matches the table's paired play and formation indices instead of the book's own. These tests run that path with the
game's own play publication and snap-path lineup builder (the ``Native`` harness of ``test_b81_gadget_play``) on the
released v0.9 executable, before and after the gadget rule, same roster:
- a gadget play of the offense book, selected through the merged root, puts the GAD in the carrier slot exactly as
  the same play does unpaired, and the matched link is the table's paired (play, formation) with the table's slot;
- every other offensive link of the merged book keeps the game's lineup, and gives the same eleven as unpaired;
- with the contract unpublished, the same merged selection is refused (its indices are not the book's own).

How the pair owner is present. It cannot be installed on v0.9 through its own ``apply``: v0.9 reserves no Playbook
pair allocation (``contract_va`` is 0) and the owner is not a late owner, so ``extend_scaleout`` refuses to append it
(asserted below). Its runtime is linked exactly as the owner links it (``code_for``/``read_only_bytes`` for a chosen
code, RW and RO address), mapped beside the executable, and its hook sites and Options pointers (``pair.sites``) are
written into the emulated image. The gadget table is the one ``gadget.apply`` writes when ``pair.contract_va`` returns
that contract address. The merged root is published by the runtime's own ``pair_begin``, ``pair_queue``, load callback
(``home_loaded``/``away_loaded``) and ``pair_bind``; the game's heap and resource-queue natives are stubbed as in
``tests/nfl2k5_playbook_pair_fixture.py``, and the donor book is loaded by the game's own loader (0x161E30). The game's
side binder (0x8718D / 0x871BA, which the pair owner's cleanup relies on) copies the published root to the side.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_gadget_play as gadget  # noqa: E402
from mod_editor.core import nfl2k5_gadget_play_code as template  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pair as pair  # noqa: E402
from tests.mod_editor.test_b81_gadget_play import (  # noqa: E402
    BOOKS, CHOICE, DEPTH, SIDES, V09_DISC, V09_XBE_SHA256, Native, _have_unicorn, _require_disc, expectation)

# The pair owner's code, RW state and RO text, linked here (outside the executable and the harness's arena).
PAIR_CODE, PAIR_STATE, PAIR_RO, PAIR_HEAP = 0x2400000, 0x2402000, 0x2403000, 0x2410000
PAIR_SPAN = 0x30000
CONTRACT = PAIR_STATE + pair.CONTRACT_OFFSET
TEAMS = PAIR_STATE + 0x400            # stand-in team/book-entry records the pair menu reads (pair_begin only)
SIDE_BINDER = ((0x8718D, 0x87197), (0x871BA, 0x871C4))   # call 0x777D0/0x777F0; mov [0xE5FC40]/[0xE5FC80], eax
STUBS = ("heap_native", "allocate_native", "free_native", "queue_native", "unload_native", "notice_native")
SKIP_TYPES = (4, 5, 6, 7, 9, 11, 13)  # kicking and defensive formations: never offense on the snap path
# (side, offense book, defense book): two pairings whose merge fits the game's limits, one per contract word.
CASES = ((0, "CLE", "HOU"), (1, "NO", "ATL"))


class PairRuntime:
    """The Playbook pair owner's runtime inside one ``Native`` machine."""

    def __init__(self, native: Native):
        self.n, m = native, native.m
        m.uc.mem_map(PAIR_CODE, PAIR_SPAN)
        m.uc.mem_write(PAIR_CODE, pair.code_for(PAIR_CODE, PAIR_STATE, PAIR_RO))
        m.uc.mem_write(PAIR_RO, pair.read_only_bytes(PAIR_CODE, PAIR_RO))
        for name, va, before, after in pair.sites(PAIR_CODE, PAIR_RO):
            assert bytes(m.uc.mem_read(va, len(before))) == before, f"pair site {name} is not retail"
            m.uc.mem_write(va, after)
        self.events: list[tuple] = []

    def text(self, address):
        out = bytearray()
        while len(out) < 512:
            pair_ = bytes(self.n.m.uc.mem_read(address + len(out), 2))
            if pair_ == b"\0\0":
                return out.decode("utf-16le")
            out.extend(pair_)
        raise AssertionError("unbounded text")

    def call(self, label, *, ecx=0):
        m = self.n.m
        symbols = pair.SYMBOLS

        def stub(_uc, address, _size, _user):
            cx, dx, sp = m.reg("ECX"), m.reg("EDX"), m.reg("ESP")
            result, pop = 0, 0
            if address == symbols["heap_native"]:
                result = 0xB04E24
            elif address == symbols["allocate_native"]:
                self.events.append(("allocate", dx))
                result = PAIR_HEAP
            elif address == symbols["free_native"]:
                self.events.append(("free", cx))
            elif address == symbols["queue_native"]:
                self.events.append(("queue", self.text(cx), self.text(dx), m.get(sp + 16)))
                result, pop = 1, 16
            elif address == symbols["unload_native"]:
                self.events.append(("unload", self.text(cx)))
            elif address == symbols["notice_native"]:
                self.events.append(("notice", self.text(dx)))
            m.reg("EAX", result)
            m.reg("EIP", m.get(sp))
            m.reg("ESP", sp + 4 + pop)

        hooks = [m.uc.hook_add(m.u.UC_HOOK_CODE, stub, begin=symbols[k], end=symbols[k]) for k in STUBS]
        try:
            # pair_merge copies and de-duplicates byte by byte: about 10^9 instructions for two full books.
            return m.call(PAIR_CODE + pair.assembly.LABELS[label], ecx=ecx, budget=3_000_000_000)
        finally:
            for hook in hooks:
                m.uc.hook_del(hook)

    def word(self, index):
        return self.n.m.get(CONTRACT + 4 * index)

    def publish(self, side, offense, defense):
        """The pregame load with a defensive playbook chosen for ``side``: begin, queue, the donor's load callback,
        bind (merge + publish), then the game's side binder. Returns the merged root."""
        m, codes = self.n.m, [code for code, _ in pair.BOOKS]
        m.uc.mem_write(PAIR_STATE, bytes(pair.DATA_SIZE))     # the owner's zero-initialized RW child (a fresh game)
        saved = {va: m.get(va) for va in (0xE5FE68, 0xE5FE6C, 0xE5FE78, 0xE5FE7C)}
        for s, code in enumerate((offense, defense) if side == 0 else (defense, offense)):
            team, entry, text = TEAMS + 0x80 * s, TEAMS + 0x80 * s + 0x20, TEAMS + 0x80 * s + 0x40
            m.uc.mem_write(text, (code + "\0").encode("utf-16le"))
            m.put(entry + 4, text)
            m.put(team + 0x110, entry)
            m.put(0xE5FE68 + 4 * s, team)
            m.put(0xE5FE78 + 4 * s, entry)
        m.put(PAIR_STATE + 12 + 64 * side, codes.index(defense) + 1)     # the Options choice for this side
        m.put(PAIR_STATE + 16 + 64 * side, m.get(0xE5FE68 + 4 * side))
        self.events = []
        self.call("pair_begin")
        for va, value in saved.items():
            m.put(va, value)
        assert (m.get(PAIR_STATE), m.get(PAIR_STATE + 4)) == (1, 1), "pair_begin did not start the paired load"
        self.call("pair_queue")
        self.call(("home_loaded", "away_loaded")[side], ecx=BOOKS[1 - side])
        self.call("pair_bind")
        m.reg("ESP", m.STACK)
        m.uc.emu_start(*SIDE_BINDER[side], count=100)
        return m.get(0xE5FE80 + 4 * side)

    def cleanup(self):
        self.events = []
        self.call("pair_cleanup")


def merged_book(native: Native, root: int):
    from tests.nfl2k5_playbook_pair_fixture import serialize
    return ip.parse_playbook_resource(serialize(bytes(native.m.uc.mem_read(root, ip.BODY_SIZE)), root))


def menu(native: Native, root, formation, link_index):
    """The native formation menu on any live book root (Native.menu reads the side's static buffer)."""
    m = native.m
    f = m.call(0xE0660, ecx=root, edx=formation, budget=32)
    aux = m.call(0xE0830, ecx=root, edx=formation, budget=32)
    c = m.call(0xE05E0, ecx=root, edx=m.get(aux + 72) & 63, budget=32)
    p = m.call(0xE13F0, ecx=root, edx=link_index, args=(f,), budget=300)
    return c, f, p


def gad(native: Native, side, root):
    """The GAD row player as the runtime reads him (WR ordinal 7, the active book in ECX)."""
    m = native.m
    temp = 0x2192000 + 32
    list_id = m.call(0xE7530, eax=9, edx=7, esi=temp, budget=100)
    row = m.get(temp)
    if row >= m.call(0xE75A0, ecx=list_id, edx=DEPTH[side], budget=100):
        return 0
    return m.call(0xE7810, eax=list_id, ecx=root, args=(DEPTH[side], row), budget=15000)


def table_links(installed: bytes, name: str):
    """The installed table's links for one book: (play, paired play, formation, paired formation, slot)."""
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    table = XbeImage(installed).read(gadget.TABLE_VA, gadget.TABLE_SIZE)
    for b in range(len(gadget.BOOK_ASSETS)):
        raw, first, count = gadget.BOOK_RECORD.unpack_from(table, b * gadget.BOOK_RECORD.size)
        if raw.rstrip(b"\0").decode("ascii") == name:
            base = len(gadget.BOOK_ASSETS) * gadget.BOOK_RECORD.size + first * gadget.LINK.size
            return [gadget.LINK.unpack_from(table, base + i * gadget.LINK.size)[:5] for i in range(count)]
    raise AssertionError(f"book {name} is not in the table")


@contextmanager
def unpublished(runtime: PairRuntime, side):
    word = CONTRACT + 4 * (2 + 3 * side)
    old = runtime.n.m.get(word)
    runtime.n.m.put(word, 0)
    try:
        yield
    finally:
        runtime.n.m.put(word, old)


@unittest.skipUnless(_have_unicorn(), "Python unicorn")
class PairedGadgetPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_coach_staff as staff, nfl2k5_roster_records as roster
        source, books = _require_disc(V09_DISC, V09_XBE_SHA256)
        with roster._outer_image()(V09_DISC) as image:
            body = image.read_entry(5)[32:]
        cls.source = source
        with mock.patch.object(pair, "contract_va", return_value=CONTRACT):
            cls.installed, cls.receipt = gadget.apply(source, books)
            cls.settings = gadget.read_settings(cls.installed, books)
        cls.books, cls.gate = books, int(cls.receipt["native_gate"], 16)
        cls.assets = {}
        for asset in gadget.BOOK_ASSETS:
            cls.assets[ip.parse_playbook_resource(books[asset], asset_id=asset).book_name] = asset
        cls.clubs = {c.book: c.index for c in staff.clubs()}
        cls.before, cls.after = Native(source, body), Native(cls.installed, body)
        cls.runtimes = {id(n): PairRuntime(n) for n in (cls.before, cls.after)}

    def test_the_pair_owner_cannot_be_applied_to_v09_so_its_runtime_is_linked_beside_it(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual((pair.status(self.source), pair.contract_va(self.source)), ("retail", 0))
        with self.assertRaisesRegex(pair.PlaybookPairError, "complete owner union"):
            pair.apply(self.source)
        with self.assertRaisesRegex(ValueError, "only late owners"):
            space.extend_scaleout(self.source, pair.REQUESTS)
        # The gadget table carries that contract address. Read against this executable (contract 0) the same table is
        # stale: "pair" (its last word) and so also "books" (the table compiled for contract 0 differs in that word).
        self.assertEqual(self.settings["status"], "applied")
        word = gadget.TABLE_VA + self.settings["offsets"]["pair_info"]
        self.assertEqual(self.after.m.get(word), CONTRACT)
        self.assertEqual(gadget.read_settings(self.installed, self.books)["stale"], ["pair", "books"])

    def run_case(self, side, offense, defense):
        asset = self.assets[offense]
        raw = self.books[asset]
        book = ip.parse_playbook_resource(raw, asset_id=asset)
        body = raw[32:]
        from mod_editor.core import nfl2k5_play_library as lib
        types = [lib.formation_record(body, f.index).type_code for f in book.formations]
        kept_forms = [f.index for f in book.formations if not 4 <= types[f.index] <= 7]   # the merge's offense unit
        kept_plays = [p.index for p in book.plays if p.family_id != 1]
        table = {(form, play): (pform, pplay, slot) for play, pplay, form, pform, slot in table_links(self.installed, offense)}
        self.assertTrue(table, offense)
        sweep = [(f.index, link) for f in book.formations if types[f.index] not in SKIP_TYPES for link in f.play_links]
        lookup = gadget.CODE_VA + template.LABELS["select_slot"]
        runtimes = [self.runtimes[id(n)] for n in (self.before, self.after)]
        for n in (self.before, self.after):
            n.load(self.books[self.assets[defense]], 1 - side)    # the donor book, by the game's own loader
            n.load(raw, side)
            for s, book_root in enumerate(BOOKS):
                n.m.put(SIDES[s] + 0x20, book_root)               # the sides bound to their own books again
        unpaired, reasons = {}, {}
        for human in (False, True):
            for n in (self.before, self.after):
                n.club(self.clubs[offense], side, human)
            for form, link in sweep:
                for n in (self.before, self.after):
                    n.commit(side, *n.menu(side, book.formations[form], link), human=human)
                unpaired[human, form, link.link_index] = (self.before.line(side), self.after.line(side))

        roots = [r.publish(side, offense, defense) for r in runtimes]
        self.assertEqual(roots, [PAIR_HEAP, PAIR_HEAP])
        for r in runtimes:
            queued = [e for e in r.events if e[0] == "queue"]
            self.assertEqual([e[1:3] for e in queued], [(("PAIRDEFHOME", "PAIRDEFAWAY")[side], defense + "-pb.iff")])
            self.assertEqual(r.n.m.get(PAIR_STATE + 12 + 64 * side + 24), 0, "the merge refused")
            self.assertEqual([r.word(i) for i in range(2, 8)],
                             [PAIR_HEAP, BOOKS[0], BOOKS[1], 0, 0, 0] if side == 0 else
                             [0, 0, 0, PAIR_HEAP, BOOKS[1], BOOKS[0]])
            self.assertEqual((r.n.m.get(0xE5FE80 + 4 * side), r.n.m.get(SIDES[side] + 0x20)), (PAIR_HEAP, PAIR_HEAP))
        root = PAIR_HEAP
        merged = merged_book(self.after, root)
        donor = ip.parse_playbook_resource(self.books[self.assets[defense]])
        self.assertEqual(merged.book_name, offense)
        self.assertEqual(len(merged.plays), len(kept_plays) + sum(p.family_id == 1 for p in donor.plays))

        changed = 0
        for human in (False, True):
            for n in (self.before, self.after):
                n.club(self.clubs[offense], side, human)
            for form, link in sweep:
                mform = kept_forms.index(form)
                self.assertEqual(merged.formations[mform].name, book.formations[form].name)
                c, f, p = menu(self.after, root, mform, link.link_index)
                self.assertEqual((c, f, p), menu(self.before, root, mform, link.link_index))
                mplay = (p - root - ip.PLAY_BASE) // ip.PLAY_SIZE
                self.assertEqual(mplay, kept_plays.index(link.play_index))
                self.assertEqual(merged.plays[mplay].name, book.plays[link.play_index].name)
                for n in (self.before, self.after):
                    n.commit(side, c, f, p, human=human)
                key = (human, form, link.link_index)
                hit = table.get((form, link.play_index))
                if hit is None:
                    normal, got = self.before.line(side), self.after.line(side)
                    self.assertEqual(got, normal, (offense, key))
                    self.assertEqual((normal, got), unpaired[key], (offense, key))
                    continue
                pform, pplay, slot = hit
                self.assertEqual((pform, pplay), (mform, mplay), "the table's paired indices are the merge's")
                self.assertEqual(self.after.m.call(lookup, args=(root, CHOICE[side] + 4, c, f), budget=20000), slot)
                if (mform, mplay) != (form, link.play_index):
                    with unpublished(self.runtimes[id(self.after)], side):
                        self.assertEqual(self.after.m.call(lookup, args=(root, CHOICE[side] + 4, c, f), budget=20000),
                                         0xFFFFFFFF)
                normal, observations = self.before.line_with_picker(side, slot)
                want, reason = expectation(self.before, side, slot, normal, observations, self.gate,
                                           gad(self.before, side, root))
                got = self.after.line(side)
                self.assertEqual(got, want, (offense, key, reason))
                self.assertEqual((normal, got), unpaired[key], (offense, key, "paired differs from unpaired"))
                self.assertIn([j for j in range(11) if normal[j] != got[j]], ([], [slot]))
                reasons[reason] = reasons.get(reason, 0) + 1
                changed += reason == "changed"
        self.assertGreater(changed, 0, reasons)

        for r in runtimes:
            r.cleanup()
            self.assertEqual([r.word(i) for i in range(8)], [0] * 8)
            self.assertEqual((r.n.m.get(0xE5FE80 + 4 * side), r.n.m.get(SIDES[side] + 0x20)), (BOOKS[side],) * 2)
            self.assertIn(("free", PAIR_HEAP), r.events)
        return reasons, len(sweep)

    def test_home_cleveland_offense_with_the_houston_defense(self):
        """Contract word [2]. Cleveland's five gadget links; End Around 147 of formation 3 is merged play 87."""
        reasons, links = self.run_case(*CASES[0])
        self.assertGreater(links, 400)

    def test_away_new_orleans_offense_with_the_atlanta_defense(self):
        """Contract word [5]. New Orleans's three gadget links, one in formation 43 (merged formation 37)."""
        reasons, links = self.run_case(*CASES[1])
        self.assertGreater(links, 400)


if __name__ == "__main__":
    unittest.main()
