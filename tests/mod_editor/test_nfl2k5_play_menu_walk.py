"""Formation play menus the play call can walk to the end (vb2, 2026-09-23).

Noah's recording: Practice, the Falcons on offense, page 2 of the play call (modern_gun_core's four gun
formations), a formation picked, then the game froze. The play-list screen's enter callback 0xACCE0 walks the
picked formation's plays with 0xE1320 / 0xE1360, and 0xE1360 returns the play in the link after the FIRST link
holding the current play, so a play listed twice in one formation makes the walk endless. The pack writer used to
append a second link for plays their formation already listed. These tests run the game's own walk (bounded) on
every retail book and on every pack compiled onto every team book it can target, check the writer's link rules,
and check the shared menu rule and the build gate that stops any writer from shipping such a book."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools")]

from mod_editor.core import nfl2k5_formation_play_writer as writer  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
XBE = EXTRACTION / "ESPN NFL 2K5 (USA)/default.xbe"
# pb phase 5: the native PLAY scoring gate compiles against the retail executable; the product callers pass it,
# these direct library calls get it from the stand-alone tools' variable (never overriding one already set).
os.environ.setdefault("NFL2K5_SCORING_XBE", str(XBE))
RETAIL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
ATL = 308


def _retail():
    """(retail default.xbe, {outer index: whole PLAY resource}) or SkipTest."""
    try:
        import unicorn  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("the native menu walk needs Unicorn")
    if not XBE.is_file() or hashlib.sha256(XBE.read_bytes()).hexdigest() != RETAIL_XBE_SHA256:
        raise unittest.SkipTest("the pinned USA retail default.xbe extraction is absent")
    from tests.mod_editor.test_nfl2k5_screen_timing import retail_books
    return XBE.read_bytes(), retail_books()


def _menu_worker_init(xbe):
    global _MENU_XBE
    _MENU_XBE = xbe


def _compile_menu_case(job):
    path, team, raw = job
    pack = packs.load_pack(path)
    book = insp.parse_playbook_resource(raw, asset_id=f"book:{team}")
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    try:
        if team != pack.book.team or packs.book_fingerprint(body) != pack.base.book_fingerprint:
            pack, _resolved = packs.retarget_pack(pack, team, book, body)
        compiled = packs.apply_pack_to_resource(raw, pack, asset_id=f"book:{team}", xbe=_MENU_XBE)
    except (packs.PlaybookPackError, ValidationError) as exc:
        return f"{path.name}:{team}", None, str(exc)
    return f"{path.name}:{team}", compiled.replacement, None


def _body(formation_links: dict[int, list[int]], play_count: int = 40, formations: int = 4) -> bytearray:
    """A bare PLAY body carrying only counts and menu words (names unreadable, which the rule tolerates)."""
    body = bytearray(insp.BODY_SIZE)
    struct.pack_into("<II", body, 0x34, formations, play_count)
    for index in range(formations):
        words = formation_links.get(index, [])
        packed = list(words) + [0x07FF] * (insp.FORMATION_PLAY_LINKS - len(words))
        struct.pack_into(f"<{insp.FORMATION_PLAY_LINKS}H", body,
                         insp.FORMATION_AUX_BASE + index * insp.FORMATION_AUX_SIZE, *packed)
    return body


def _link(play: int, group: int = 3) -> int:
    return 0x8000 | (group << 9) | play


class MenuRuleTests(unittest.TestCase):
    """menu_link_problems on hand-made bodies: no retail data needed."""

    def test_a_sound_menu_passes(self):
        body = _body({0: [_link(1, 0), _link(2, 1), _link(3, 2), _link(4), _link(5)], 1: [_link(1), _link(6)]})
        self.assertEqual(insp.menu_link_problems(bytes(body)), [])
        self.assertEqual(insp.menu_link_problems(b"PLAY" + bytes(0x1C) + bytes(body)), [])

    def test_a_play_listed_twice_is_the_hang(self):
        problems = insp.menu_link_problems(bytes(_body({2: [_link(7), _link(8), _link(9), _link(8)]})))
        self.assertEqual(len(problems), 1)
        self.assertIn("play 8 is listed twice (slots 1 and 3)", problems[0])
        self.assertIn("never end", problems[0])

    def test_groups_zero_to_two_hold_one_play_each(self):
        problems = insp.menu_link_problems(bytes(_body({0: [_link(1, 0), _link(2, 0), _link(3, 3)]})))
        self.assertEqual(len(problems), 1)
        self.assertIn("2 plays in selection group 0", problems[0])

    def test_gaps_and_out_of_range_plays(self):
        body = _body({0: [_link(1), _link(2)]}, play_count=10)
        struct.pack_into("<H", body, insp.FORMATION_AUX_BASE + 5 * 2, _link(3))   # after empty slots 2..4
        struct.pack_into("<H", body, insp.FORMATION_AUX_BASE + insp.FORMATION_AUX_SIZE, _link(12))
        problems = insp.menu_link_problems(bytes(body))
        self.assertTrue(any("follows an empty slot" in p for p in problems))
        self.assertTrue(any("past the book's 10 plays" in p for p in problems))

    def test_not_a_book(self):
        self.assertEqual(len(insp.menu_link_problems(b"PLAY")), 1)


class BuildGateTests(unittest.TestCase):
    """mod_build._check_playbook_menus refuses a built image with a menu the play call cannot walk."""

    def _gate(self, resources):
        from mod_editor.core import mod_build as build

        class Archive:
            def __init__(self, _path):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            @staticmethod
            def entries_with_head(head):
                return [SimpleNamespace(index=i) for i in sorted(resources)]

            @staticmethod
            def read_entry(index):
                return resources[index]

        fake_packs = SimpleNamespace(_outer_image=lambda: SimpleNamespace(OuterImage=Archive))
        modules = {"nfl2k5_playbook_inspector": insp, "nfl2k5_playbook_pack": fake_packs}
        with patch.object(build, "_core_module", side_effect=modules.get):
            return build._check_playbook_menus(Path("unused.iso"), lambda *a: None)

    def test_sound_books_pass_and_a_duplicate_link_refuses_the_build(self):
        good = b"PLAY" + bytes(0x1C) + bytes(_body({0: [_link(1), _link(2)]}))
        bad = b"PLAY" + bytes(0x1C) + bytes(_body({0: [_link(1), _link(2), _link(1)]}))
        self.assertEqual(self._gate({307: good, 308: good}), {"books": 2, "problems": 0})
        with self.assertRaisesRegex(RuntimeError, r"book 308: formation 0 .*play 1 is listed twice"):
            self._gate({307: good, 308: bad})


class NativeWalkTests(unittest.TestCase):
    """The game's own 0xE1320 / 0xE1360 / 0xACCE0 on retail and pack-compiled books."""

    @classmethod
    def setUpClass(cls):
        cls.xbe, cls.books = _retail()
        from tests.nfl2k5_play_menu_walk_native import MenuWalker
        cls.MenuWalker = MenuWalker

    def assert_every_menu_ends(self, resource, label):
        book = insp.parse_playbook_resource(resource, asset_id=label)
        machine = self.MenuWalker(self.xbe, resource)
        for formation in book.formations:
            if not formation.play_links:
                continue
            order, ended = machine.walk(formation.index)
            with self.subTest(book=label, formation=formation.name):
                self.assertTrue(ended, f"{label} {formation.name}: the play list never ends: {order[:20]}")
                self.assertEqual(order, [link.play_index for link in formation.play_links])
                returned, items = machine.page_builder(formation.index)
                self.assertTrue(returned, f"{label} {formation.name}: 0xACCE0 did not return")
                self.assertEqual(items, order[:3])

    def test_every_retail_menu_ends(self):
        for index, resource in sorted(self.books.items()):
            self.assertEqual(insp.menu_link_problems(resource), [], index)
            self.assert_every_menu_ends(resource, str(index))

    def test_the_old_duplicate_links_hang_the_game_walk(self):
        """The shape the old writer produced for modern_gun_core on ATL: the walk cycles and 0xACCE0 never
        returns. This is the hang in Noah's recording, reproduced with the game's code."""
        resource = bytearray(self.books[ATL])
        aux = insp.RESOURCE_HEADER_SIZE + insp.FORMATION_AUX_BASE + 15 * insp.FORMATION_AUX_SIZE
        words = list(struct.unpack_from("<36H", resource, aux))
        first_empty = next(i for i, word in enumerate(words) if word & 0x1FF == 0x1FF)
        for offset, play in enumerate((64, 131, 75)):          # the three links the old writer appended
            words[first_empty + offset] = _link(play)
        struct.pack_into("<36H", resource, aux, *words)
        self.assertTrue(any("listed twice" in p for p in insp.menu_link_problems(bytes(resource))))
        machine = self.MenuWalker(self.xbe, bytes(resource))
        order, ended = machine.walk(15, limit=40)
        self.assertFalse(ended)
        self.assertEqual(order[9:18], [64, 128, 177] * 3)
        returned, _items = machine.page_builder(15)
        self.assertFalse(returned)

    def test_every_pack_on_every_team_book_it_can_target(self):
        from concurrent.futures import ProcessPoolExecutor, as_completed
        entries = packs._outer_image().BOOK_ENTRIES
        compiled_any = 0
        jobs = []
        for path in sorted((REPO / "data/playbooks").glob("*.2k5book")):
            for team, index in sorted(entries.items()):
                if index not in self.books or not (len(team) <= 3 and team.isupper()):
                    continue            # the 32 team books plus GEN and WCO; Editor/PRACTICE/reference are not
                jobs.append((path, team, self.books[index]))
        # The compiler now executes the native scoring matrix. Keep the full
        # cross-team regression, distributing independent, read-only cases.
        with ProcessPoolExecutor(max_workers=min(8, os.cpu_count() or 1),
                                 initializer=_menu_worker_init, initargs=(self.xbe,)) as pool:
            for future in as_completed([pool.submit(_compile_menu_case, job) for job in jobs]):
                label, replacement, error = future.result()
                if error is not None:
                    self.assertNotIn("play menu", error, label)
                    continue
                compiled_any += 1
                self.assertEqual(insp.menu_link_problems(replacement), [], label)
                self.assert_every_menu_ends(replacement, label)
                if compiled_any % 100 == 0:
                    print(f"PROVED OFFLINE: {compiled_any} cross-team pack/menu cases passed", flush=True)
        self.assertGreaterEqual(compiled_any, 100)


class WriterLinkTests(unittest.TestCase):
    """The writer lists a play once per formation and keeps groups 0-2 single."""

    @classmethod
    def setUpClass(cls):
        _xbe, cls.books = _retail()
        cls.raw = cls.books[ATL]
        cls.book = insp.parse_playbook_resource(cls.raw, asset_id="book:ATL")

    def compile(self, links):
        # One formation clone keeps the compile from being a no-op; links then target existing formation 4.
        return writer.compile_formation_play_creations(
            self.raw, [{"asset_id": "t", "donor_formation_index": 0}], [], links)

    def test_a_play_already_listed_reuses_its_link(self):
        split_jokers = self.book.formations[4]
        existing = split_jokers.play_links[5]            # play 160, group 3
        compiled = self.compile([{"asset_id": "t", "formation_index": 4, "play_index": existing.play_index}])
        after = insp.parse_playbook_resource(compiled.replacement).formations[4].play_links
        self.assertEqual([(l.link_index, l.play_index, l.group) for l in after],
                         [(l.link_index, l.play_index, l.group) for l in split_jokers.play_links])
        self.assertEqual(compiled.report["reused_links"], 1)
        self.assertEqual(compiled.report["links"], [[4, existing.play_index, existing.group, existing.link_index]])

    def test_a_new_play_goes_into_group_three_and_an_audible_choice_moves_the_old_holder(self):
        split_jokers = self.book.formations[4]            # 136 is audible 1 (group 0), 55 audible 2 (group 1)
        listed = {l.play_index for l in split_jokers.play_links}
        new_play = next(p.index for p in self.book.plays if p.index not in listed and p.family_id == 0)
        compiled = self.compile([{"asset_id": "t", "formation_index": 4, "play_index": new_play}])
        after = insp.parse_playbook_resource(compiled.replacement).formations[4].play_links
        self.assertEqual((after[-1].play_index, after[-1].group), (new_play, 3))
        self.assertEqual(compiled.report["reused_links"], 0)
        # A new play chosen as audible 1 takes group 0; the old audible 1 stays listed in group 3.
        compiled = self.compile([{"asset_id": "t", "formation_index": 4, "play_index": new_play, "group": 0}])
        after = {l.play_index: l.group for l in insp.parse_playbook_resource(compiled.replacement).formations[4].play_links}
        self.assertEqual((after[new_play], after[136]), (0, 3))
        self.assertEqual(compiled.report["regrouped_links"], [[4, 0, 136, 0, 3]])
        # A listed play chosen as audible 2 keeps its one slot and takes group 1; the old holder (55) goes to 3.
        compiled = self.compile([{"asset_id": "t", "formation_index": 4, "play_index": 160, "group": 1}])
        after = insp.parse_playbook_resource(compiled.replacement).formations[4].play_links
        self.assertEqual([l.play_index for l in after], [l.play_index for l in split_jokers.play_links])
        self.assertEqual({l.play_index: l.group for l in after}[160], 1)
        self.assertEqual({l.play_index: l.group for l in after}[55], 3)
        self.assertEqual(insp.menu_link_problems(compiled.replacement), [])

    def test_modern_gun_core_on_atl_lists_every_play_once(self):
        pack = packs.load_pack(REPO / "data/playbooks/modern_gun_core.2k5book")
        compiled = packs.apply_pack_to_resource(self.raw, pack, asset_id="book:ATL")
        book = insp.parse_playbook_resource(compiled.replacement)
        self.assertEqual(insp.menu_link_problems(compiled.replacement), [])
        self.assertEqual(compiled.report["reused_links"], 11)
        for index, name in ((4, "Gun Trips Rt"), (15, "Gun Doubles"), (16, "Gun Bunch Rt"), (19, "Gun Empty")):
            formation = book.formations[index]
            self.assertEqual(formation.name, name)
            self.assertEqual([l.play_index for l in formation.play_links],
                             [l.play_index for l in self.book.formations[index].play_links])


if __name__ == "__main__":
    unittest.main()
