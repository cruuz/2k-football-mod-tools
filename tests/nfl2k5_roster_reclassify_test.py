"""Tests for the one-pool ROST reclassification (rules, ranking, apply on a synthetic XISO)."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "tools", ROOT, ROOT / "tests"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_playbook_position_recode as pr  # noqa: E402
import nfl2k5_roster_reclassify as rr  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

RETAIL_PACKS = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030")
QB, WR, CB, OLB, ILB, DT, DE = 0, 3, 4, 10, 11, 15, 16
POS = rr.POSITIONS


def word(rank: int, side: int, low: int = 0x155) -> int:
    return low | (rank << 10) | (side << 13)


# ---------------------------------------------------------------------------------------------
# synthetic ROST resource
# ---------------------------------------------------------------------------------------------

class RostBuilder:
    """Builds a main-roster ROST body: root at 0x40, label pairs, team records (0x1F4) and primary
    player records (0x54) with real biased relative pointers, then a UTF-16 string pool."""

    def __init__(self) -> None:
        self.labels: list[tuple[str, str]] = []
        self.teams: list[dict] = []
        self.players: list[dict] = []

    def label(self, nickname: str, abbreviation: str) -> int:
        self.labels.append((nickname, abbreviation))
        return len(self.labels) - 1

    def player(self, first: str, last: str, position: int, rank: int = 0, side: int = 0) -> int:
        self.players.append({"first": first, "last": last, "position": position, "word": word(rank, side)})
        return len(self.players) - 1

    def team(self, city: str, nickname: str, abbreviation: str, kind: int, label: int | None, roster: list[int],
             scheme_word: int = 0) -> int:
        self.teams.append({"city": city, "nickname": nickname, "abbreviation": abbreviation, "kind": kind,
                           "label": label, "roster": roster, "scheme_word": scheme_word})
        return len(self.teams) - 1

    def build(self) -> bytes:
        root = 0x40
        labels_off = root + rr.nr.NFL_ROOT_SIZE
        teams_off = labels_off + 8 * len(self.labels)
        players_off = teams_off + rr.nr.NFL_TEAM_STRIDE * len(self.teams)
        strings_off = players_off + rr.nr.NFL_PLAYER_STRIDE * len(self.players)
        body = bytearray(strings_off)
        pool: list[bytes] = []
        cursor = strings_off

        def put(text: str) -> int:
            nonlocal cursor
            raw = text.encode("utf-16le") + b"\0\0"
            raw += b"\0" * (-len(raw) % 4)
            pool.append(raw)
            at = cursor
            cursor += len(raw)
            return at

        def rel(field: int, target: int) -> None:
            struct.pack_into("<i", body, field, target - field + 1)

        body[0x0C:0x10] = b"ROST"
        struct.pack_into("<I", body, 0x10, 17)
        rel(0x14, root)
        body[0x20:0x20 + 14] = "roster".encode("utf-16le") + b"\0\0"
        # root: counts + pointers (empty tables keep a non-null pointer to the root end)
        for count_off, ptr_off, count, target in (
            (0x00, 0x04, len(self.players), players_off), (0x08, 0x0C, 0, labels_off), (0x10, 0x14, 0, labels_off),
            (0x18, 0x1C, len(self.teams), teams_off), (0x20, 0x24, 0, labels_off), (0x30, 0x34, 0, labels_off),
            (0x38, 0x3C, 0, labels_off), (0x48, 0x4C, len(self.labels), labels_off), (0x50, 0x54, 0, labels_off),
            (0x58, 0x5C, 0, labels_off),
        ):
            struct.pack_into("<I", body, root + count_off, count)
            rel(root + ptr_off, target)
        for i, (nickname, abbreviation) in enumerate(self.labels):
            rel(labels_off + 8 * i, put(nickname))
            rel(labels_off + 8 * i + 4, put(abbreviation))
        for i, p in enumerate(self.players):
            off = players_off + i * rr.nr.NFL_PLAYER_STRIDE
            rel(off + 0x10, put(p["first"]))
            rel(off + 0x14, put(p["last"]))
            struct.pack_into("<H", body, off + 0x28, p["word"])
            body[off + 0x35] = p["position"]
        for i, t in enumerate(self.teams):
            off = teams_off + i * rr.nr.NFL_TEAM_STRIDE
            for slot, player_index in enumerate(t["roster"]):
                rel(off + slot * 4, players_off + player_index * rr.nr.NFL_PLAYER_STRIDE)
            body[off + 0x11C] = len(t["roster"])
            rel(off + 0x104, put(t["nickname"]))
            rel(off + 0x108, put(t["abbreviation"]))
            rel(off + 0x138, put(t["city"]))
            if t["label"] is not None:
                rel(off + 0x110, labels_off + 8 * t["label"])
            struct.pack_into("<I", body, off + 0x128, t["kind"])
            struct.pack_into("<I", body, off + rr.TEAM_SCHEME_WORD, t["scheme_word"])
        body += b"".join(pool)
        body += b"\0" * (-len(body) % 0x10)
        header = struct.pack("<4s7I", b"ROST", len(body), len(body), 0, 0, 0, 0, 0)
        return header + bytes(body)


def build_roster() -> tuple[bytes, dict[str, int]]:
    """Two NFL teams (a 4-3 ARZ and a 3-4 BAL), a Pro Bowl squad sharing a player, one free agent."""

    b = RostBuilder()
    arz_label, bal_label, gen_label = b.label("Cardinals", "ARZ"), b.label("Ravens", "BAL"), b.label("General", "GEN")
    ids = {}
    # ARZ (4-3): DEs Berry (rank 0) / Pace (side 0) / Johnson; DTs Bryant / Davis; ILB McKinnon (r0) / Darling;
    # OLBs Thompson (r0), Dansby (s0), Woods (r1), Hayes (r3)
    ids["berry"] = b.player("Bert", "Berry", DE, 0, 2)
    ids["johnson"] = b.player("Dennis", "Johnson", DE, 1, 3)
    ids["pace"] = b.player("Calvin", "Pace", DE, 3, 0)
    ids["bryant"] = b.player("Wendell", "Bryant", DT, 0, 3)
    ids["davis"] = b.player("Russell", "Davis", DT, 3, 0)
    ids["mckinnon"] = b.player("Ronald", "McKinnon", ILB, 0, 1)
    ids["darling"] = b.player("James", "Darling", ILB, 1, 0)
    ids["thompson"] = b.player("Raynoch", "Thompson", OLB, 0, 3)
    ids["woods"] = b.player("LeVar", "Woods", OLB, 1, 4)
    ids["dansby"] = b.player("Karlos", "Dansby", OLB, 2, 0)
    ids["hayes"] = b.player("Gerald", "Hayes", OLB, 3, 1)
    ids["mccown"] = b.player("Josh", "McCown", QB, 0, 0)
    arz = [ids[k] for k in ("mccown", "berry", "johnson", "pace", "bryant", "davis", "mckinnon", "darling", "thompson",
                            "woods", "dansby", "hayes")]
    # BAL (3-4): DEs Weaver (r0) / Douglas (s0) / Green; DTs Gregg (r0) / Kemoeatu (s0) / Franklin;
    # ILB Hartwell (r0) / Lewis (s0) / Slaughter; OLB Suggs (r0) / Boulware (s0) / Thomas / Brown
    ids["weaver"] = b.player("Anthony", "Weaver", DE, 0, 2)
    ids["green"] = b.player("Roderick", "Green", DE, 1, 3)
    ids["douglas"] = b.player("Marques", "Douglas", DE, 2, 0)
    ids["gregg"] = b.player("Kelly", "Gregg", DT, 0, 1)
    ids["franklin"] = b.player("Aubrayo", "Franklin", DT, 1, 2)
    ids["kemoeatu"] = b.player("Ma'ake", "Kemoeatu", DT, 2, 0)
    ids["hartwell"] = b.player("Edgerton", "Hartwell", ILB, 0, 1)
    ids["slaughter"] = b.player("T.J.", "Slaughter", ILB, 1, 2)
    ids["lewis"] = b.player("Ray", "Lewis", ILB, 2, 0)
    ids["suggs"] = b.player("Terrell", "Suggs", OLB, 0, 2)
    ids["thomas"] = b.player("Adalius", "Thomas", OLB, 1, 3)
    ids["boulware"] = b.player("Peter", "Boulware", OLB, 2, 0)
    ids["brown"] = b.player("Cornell", "Brown", OLB, 3, 1)
    bal = [ids[k] for k in ("weaver", "green", "douglas", "gregg", "franklin", "kemoeatu", "hartwell", "slaughter",
                            "lewis", "suggs", "thomas", "boulware", "brown")]
    ids["fa_olb"] = b.player("Free", "Agent", OLB, 5, 5)
    ids["fa_de"] = b.player("Free", "End", DE, 5, 5)
    b.team("Arizona", "Cardinals", "ARZ", 0, arz_label, arz)
    b.team("Baltimore", "Ravens", "BAL", 0, bal_label, bal, scheme_word=1)
    b.team("AFC", "AFC", "AFC", 1, gen_label, [ids["suggs"], ids["berry"], ids["lewis"]])     # shares NFL players
    return b.build(), ids


def build_fixture(directory: Path, rost: bytes) -> SyntheticXiso:
    entries: list[tuple[int, bytes]] = []
    for index in range(rr.MAIN_ROST_ENTRY):
        entries.append((0x1000 + index, bytes([index + 1]) * 0x10))
    entries.append((0x2005, rost))
    entries.append((0x3000, b"tail"))
    return SyntheticXiso(directory, entries, pack_sizes=(0x20000, 0x2000, 0x2000), pack_sectors=(64, 128, 132))


SCHEMES = {"ARZ": "4-3", "BAL": "3-4", "GEN": "dual"}


def _main(path: Path) -> rr.Resource:
    with pr.OuterImage(path) as archive:
        return rr.load_resources(archive, historic=False)[0]


def _pool(resource: rr.Resource, team_index: int, enum: int) -> list[tuple[str, int, int]]:
    team = resource.teams[team_index]
    rows = [(p.name, p.rank, p.side) for p in (resource.players[o] for o in team.roster) if p.position == enum]
    return sorted(rows, key=lambda r: r[1])


class RuleTests(unittest.TestCase):
    def test_side_formula_matches_the_auto_depth_chart(self) -> None:
        self.assertEqual([rr.side_for_rank(r) for r in range(8)], [2, 0, 1, 3, 4, 5, 6, 7])

    def test_pool_plans(self) -> None:
        self.assertEqual(rr.pool_plan("4-3")[ILB], ([ILB, OLB], [(0, "rank"), (1, "rank"), (1, "side")]))
        self.assertEqual(rr.pool_plan("3-4")[DT], ([DT, DE], [(0, "rank"), (1, "rank"), (1, "side")]))
        self.assertEqual(rr.pool_plan("3-4")[DE], ([OLB], [(0, "rank"), (0, "side")]))
        self.assertNotIn(OLB, rr.pool_plan("4-3"))
        self.assertNotIn(OLB, rr.pool_plan("3-4"))

    def test_team_scheme_defaults_and_overrides(self) -> None:
        team = rr.Team(0, 0, "Dallas Cowboys", "DAL", 0, "DAL", [], 7)      # unknown scheme word: the book decides
        self.assertEqual(rr.team_scheme(team, {"DAL": "dual"}), "4-3")
        self.assertEqual(rr.team_scheme(team, {"DAL": "dual"}, three_four=("DAL",)), "3-4")
        self.assertEqual(rr.team_scheme(team, {"DAL": "3-4"}), "3-4")
        self.assertEqual(rr.team_scheme(team, {"DAL": "3-4"}, four_three=("DAL",)), "4-3")
        historic = rr.Team(0, 0, "St. Louis Cardinals '75", "STL75", 4, None, [])
        self.assertEqual(rr.team_scheme(historic, {}), "4-3")

    def test_team_scheme_word_decides_before_the_book(self) -> None:
        # +0x150: 0 = 4-3, 1 = 3-4, 2 = dual (played as 4-3); the book only decides for other values
        self.assertEqual(rr.team_scheme(rr.Team(0, 0, "Ravens", "BAL", 0, "BAL", [], 1), {"BAL": "4-3"}), "3-4")
        self.assertEqual(rr.team_scheme(rr.Team(0, 0, "Cowboys", "DAL", 0, "DAL", [], 2), {"DAL": "3-4"}), "4-3")
        self.assertEqual(rr.team_scheme(rr.Team(0, 0, "Giants", "NYG", 0, "NYG", [], 0), {"NYG": "3-4"}), "4-3")
        self.assertEqual(rr.team_scheme(rr.Team(0, 0, "Odd", "ODD", 0, "BAL", [], 7), {"BAL": "3-4"}), "3-4")
        self.assertEqual(rr.team_scheme(rr.Team(0, 0, "Ravens", "BAL", 0, "BAL", [], 1), {}, four_three=("BAL",)), "4-3")


class SyntheticImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.rost, self.ids = build_roster()
        self.fixture = build_fixture(Path(self.tmp.name), self.rost)
        self.retail_digest = rr.record_digest([_main(self.fixture.path)])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parse_reads_teams_players_and_labels(self) -> None:
        main = _main(self.fixture.path)
        self.assertEqual(main.label, "roster")
        self.assertEqual([t.abbreviation for t in main.teams], ["ARZ", "BAL", "AFC"])
        self.assertEqual([t.label_abbreviation for t in main.teams], ["ARZ", "BAL", "GEN"])
        self.assertEqual(len(main.players), len(self.ids))
        suggs = next(p for p in main.players.values() if p.name == "Terrell Suggs")
        self.assertEqual((suggs.position, suggs.rank, suggs.side, suggs.teams), (OLB, 0, 2, [1, 2]))

    def test_inspect_plans_the_documented_moves(self) -> None:
        reports = rr.inspect(self.fixture.path, schemes=SCHEMES)
        by_team = {r["abbreviation"]: r for r in reports}
        self.assertEqual(by_team["ARZ"]["scheme"], "4-3")
        self.assertEqual(by_team["ARZ"]["moves"], {"OLB->LB": 4})
        self.assertEqual(by_team["ARZ"]["pools"]["LB"][:3],
                         ["Ronald McKinnon", "Raynoch Thompson (was OLB)", "Karlos Dansby (was OLB)"])
        self.assertEqual(by_team["ARZ"]["pools"]["EDGE"], ["Bert Berry", "Calvin Pace", "Dennis Johnson"])
        self.assertEqual(by_team["BAL"]["scheme"], "3-4")
        self.assertEqual(by_team["BAL"]["moves"], {"OLB->EDGE": 4, "DE->DT": 3})
        self.assertEqual(by_team["BAL"]["pools"]["DT"][:3],
                         ["Kelly Gregg", "Anthony Weaver (was DE)", "Marques Douglas (was DE)"])
        self.assertEqual(by_team["BAL"]["pools"]["EDGE"][:2], ["Terrell Suggs (was OLB)", "Peter Boulware (was OLB)"])
        self.assertEqual(by_team["BAL"]["pools"]["LB"], ["Edgerton Hartwell", "Ray Lewis", "T.J. Slaughter"])
        # the shared players were claimed by their NFL teams: nothing left for the Pro Bowl squad to move
        self.assertEqual(by_team["AFC"]["moves"], {})
        self.assertEqual(by_team["AFC"]["reranked"], 0)
        # --three-four flips a team to the 3-4 rule
        flipped = {r["abbreviation"]: r for r in rr.inspect(self.fixture.path, schemes=SCHEMES, three_four=("ARZ",))}
        self.assertEqual(flipped["ARZ"]["moves"], {"OLB->EDGE": 4, "DE->DT": 3})

    def test_apply_writes_positions_and_ranks_then_reads_applied(self) -> None:
        before = self.fixture.path.read_bytes()
        receipt = rr.apply(self.fixture.path, schemes=SCHEMES, historic=False, expected_digest=self.retail_digest)
        self.assertEqual(receipt["before_sha256"], self.retail_digest)
        self.assertEqual(receipt["totals"], {"OLB->LB": 5, "OLB->EDGE": 4, "DE->DT": 3})
        after = self.fixture.path.read_bytes()
        main = _main(self.fixture.path)
        # ARZ: LB order MIKE, WILL, SAM, then backups by retail rank; EDGE/DT canonical
        self.assertEqual(_pool(main, 0, ILB), [("Ronald McKinnon", 0, 2), ("Raynoch Thompson", 1, 0), ("Karlos Dansby", 2, 1),
                                               ("James Darling", 3, 3), ("LeVar Woods", 4, 4), ("Gerald Hayes", 5, 5)])
        self.assertEqual(_pool(main, 0, DE), [("Bert Berry", 0, 2), ("Calvin Pace", 1, 0), ("Dennis Johnson", 2, 1)])
        self.assertEqual(_pool(main, 0, DT), [("Wendell Bryant", 0, 2), ("Russell Davis", 1, 0)])
        self.assertEqual(_pool(main, 0, OLB), [])
        # BAL: nose, LDE, RDE then backups; EDGE = the outside backers; LB = the inside backers
        self.assertEqual(_pool(main, 1, DT), [("Kelly Gregg", 0, 2), ("Anthony Weaver", 1, 0), ("Marques Douglas", 2, 1),
                                              ("Aubrayo Franklin", 3, 3), ("Roderick Green", 4, 4), ("Ma'ake Kemoeatu", 5, 5)])
        self.assertEqual(_pool(main, 1, DE), [("Terrell Suggs", 0, 2), ("Peter Boulware", 1, 0), ("Adalius Thomas", 2, 1),
                                              ("Cornell Brown", 3, 3)])
        self.assertEqual(_pool(main, 1, ILB), [("Edgerton Hartwell", 0, 2), ("Ray Lewis", 1, 0), ("T.J. Slaughter", 2, 1)])
        # free agents: only the OLB byte moves, his rank bits stay
        fa = next(p for p in main.players.values() if p.name == "Free Agent")
        self.assertEqual((fa.position, fa.rank, fa.side), (ILB, 5, 5))
        fa_de = next(p for p in main.players.values() if p.name == "Free End")
        self.assertEqual((fa_de.position, fa_de.rank, fa_de.side), (DE, 5, 5))
        # the QB and the low bits of every order word are untouched
        qb = next(p for p in main.players.values() if p.name == "Josh McCown")
        self.assertEqual((qb.position, qb.word), (QB, word(0, 0)))
        self.assertTrue(all(p.word & 0x3FF == 0x155 for p in main.players.values()))
        # only position bytes and order words changed
        diff = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        with pr.OuterImage(self.fixture.path) as archive:
            base = archive.image_offset(main.virtual_offset + rr.RESOURCE_HEADER_SIZE)
        allowed: set[int] = set()
        for p in main.players.values():
            allowed.update(range(base + p.offset + 0x28, base + p.offset + 0x2A))
            allowed.add(base + p.offset + 0x35)
        self.assertTrue(diff <= allowed, sorted(diff - allowed)[:8])
        self.assertEqual(len(before), len(after))
        self.assertEqual(rr.status(self.fixture.path, historic=False)["status"], "applied-custom")

    def test_apply_refuses_non_retail_and_repeat(self) -> None:
        with self.assertRaises(rr.ReclassifyError):
            rr.apply(self.fixture.path, schemes=SCHEMES, historic=False, expected_digest="0" * 64)
        rr.apply(self.fixture.path, schemes=SCHEMES, historic=False, expected_digest=self.retail_digest)
        with self.assertRaises(rr.ReclassifyError):
            rr.apply(self.fixture.path, schemes=SCHEMES, historic=False, expected_digest=self.retail_digest)

    def test_record_digest_ignores_name_strings(self) -> None:
        # the EDGE rename rewrites name strings after the record tables: the record digest must not move
        edited = bytearray(self.rost)
        at = edited.find("Berry".encode("utf-16le"))
        self.assertGreater(at, 0)
        edited[at: at + 10] = "Edgey".encode("utf-16le")
        other = build_fixture(Path(self.tmp.name) / "renamed", bytes(edited))
        self.assertEqual(rr.record_digest([_main(other.path)]), self.retail_digest)


@unittest.skipUnless(RETAIL_PACKS.is_dir(), "retail packs not present")
class RetailPackSmokeTests(unittest.TestCase):
    def test_retail_packs_read_retail_and_the_plan_is_the_documented_one(self) -> None:
        st = rr.status(RETAIL_PACKS)
        self.assertEqual(st["status"], "retail")
        self.assertEqual(st["resources"], 76)
        with pr.OuterImage(RETAIL_PACKS) as archive:
            schemes = rr.book_schemes(archive)
            main = rr.load_resources(archive, historic=False)[0]
        self.assertEqual({k for k, v in schemes.items() if v == "3-4"}, set(rr.PURE_THREE_FOUR_BOOKS))
        self.assertEqual({k for k, v in schemes.items() if v == "dual"}, set(rr.DUAL_BOOKS))
        moves, team_schemes = rr.plan_resource(main, schemes)
        nfl = [t for t in main.teams if t.kind == rr.TEAM_KIND_NFL]
        self.assertEqual(len(nfl), 32)
        self.assertEqual({t.abbreviation for t in nfl if team_schemes[t.index] == "3-4"}, {"BAL", "HOU", "NE", "PIT", "SD"})
        bal = next(t for t in nfl if t.abbreviation == "BAL")
        report = rr.team_report(main, bal, "3-4", moves)
        self.assertEqual(report["moves"], {"OLB->EDGE": 4, "DE->DT": 4})
        self.assertEqual(report["pools"]["DT"][:3], ["Kelly Gregg", "Anthony Weaver (was DE)", "Marques Douglas (was DE)"])
        self.assertEqual(report["pools"]["EDGE"][:2], ["Terrell Suggs (was OLB)", "Peter Boulware (was OLB)"])
        self.assertFalse(any(m.new_position == OLB for m in moves))


if __name__ == "__main__":
    unittest.main()
