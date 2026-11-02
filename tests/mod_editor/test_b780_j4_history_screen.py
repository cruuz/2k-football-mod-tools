"""Job b780 j4-history: the franchise History screen, box scores from the Schedule and the Player Card game log.

EXPERIMENTAL / UNWITNESSED in game. Static and model checks run everywhere. The native classes map the retail USA
``default.xbe`` with the owner installed and run the real code under Unicorn, with a synthetic league (32 clubs in the
league's club table 0xE5786C, the league grid and quarter scores), a seed document and a franchise footer body in the
j23-footer layout (``nfl2k5_franchise_extension``, envelope 1; ``j23_body`` below encodes it and is checked against
that module when the branch carrying it is present):

* the ESPN.com row table (twelve retail rows, TEAM HISTORY, the end marker) and the two descriptors the game reads;
* every page's text (captured from the game's own text calls), the page/club/award/filter cycling and the scroll;
* the box score of a played game (line score from the grid; team stats and player lines from the footer) and the CPU
  game message, and the Schedule hook (X on a played game pushes the box score; the legend entry follows the selection);
* the Player Card game log page and the card's four-page cycle through the champions owner (honors option);
* a damaged or foreign footer reads as empty, and no page reads past the footer (it ends at an unmapped page).

Boundaries: the menu manager, the pads and the Schedule's selection accessors are stand-ins; the in-game screens are
proven by the emulator stills in the job report, not here.
"""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_history_screen as hist  # noqa: E402
from mod_editor.core import nfl2k5_history_screen_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import HAVE_UC, LEAGUE_MODE, SCORES, SEASONS, Machine, _retail  # noqa: E402

from mod_editor.core import nfl2k5_champions_history as champions_history  # noqa: E402

# ---- the j23-footer body (nfl2k5_franchise_extension, envelope 1), as the History screen reads it ---------------------
J23_BLOCKS = {1: (0x0200, 18960), 2: (0x4C10, 528), 3: (0x4E20, 9520), 4: (0x7350, 16176), 5: (0xB280, 4624),
              6: (0xC490, 12304)}
J23_BODY_SIZE = 0x18000 - 16
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")


def adler(data: bytes, a: int = 1, b: int = 0) -> int:
    for byte in data:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


def j23_body(blocks: dict) -> bytes:
    """A sealed body: header, the 16-slot directory (blocks 1..6 present, version 1), the blocks at their offsets."""
    body = bytearray(J23_BODY_SIZE)
    body[0:8] = b"2K5XTND1"
    struct.pack_into("<HHIHHHH", body, 8, 1, 64, J23_BODY_SIZE, 0x40, 16, 16, 0)
    for block_id, (offset, size) in J23_BLOCKS.items():
        content = bytes(blocks.get(block_id, b"")).ljust(size, b"\0")[:size]
        body[offset:offset + size] = content
        struct.pack_into("<HBBIII", body, 0x40 + 16 * (block_id - 1), block_id, 1, 1, offset, size, adler(content))
    struct.pack_into("<I", body, 0x3C, adler(bytes(body[0:0x3C]) + bytes(body[0x40:0x140])))
    return bytes(body)


def person(first: str, last: str, pos="QB") -> bytes:
    """The 7-byte person (the champions packing; position code 0..31, 31 = coach)."""
    code = POSITIONS.index(pos) if isinstance(pos, str) else pos
    raw = bytearray(champions_history.pack_person((first + " " + last) if first else last, "QB"))
    for b in range(5):
        bit = 50 + b
        raw[bit >> 3] &= ~(1 << (bit & 7)) & 0xFF
        if code >> b & 1:
            raw[bit >> 3] |= 1 << (bit & 7)
    return bytes(raw)


LEAGUE_TEAMS, TEAM_COUNT_VA, FOCUS, HUMAN, GRID = 0xE5786C, 0xE576AC, 0xE3C0A0, 0xE5775C, 0xE57C40
CARD_PLAYER, ROSTER, YEAR_IMM = 0xC90248, 0xB72918, 0x3204AD
PADS = 0xB37A70
CLUBS = (("ARI", "Arizona", "Cardinals"), ("ATL", "Atlanta", "Falcons"), ("BAL", "Baltimore", "Ravens"),
         ("BUF", "Buffalo", "Bills"), ("CAR", "Carolina", "Panthers"), ("CHI", "Chicago", "Bears"),
         ("CIN", "Cincinnati", "Bengals"), ("CLE", "Cleveland", "Browns"), ("DAL", "Dallas", "Cowboys"),
         ("DEN", "Denver", "Broncos"), ("DET", "Detroit", "Lions"), ("GB", "Green Bay", "Packers"),
         ("HOU", "Houston", "Texans"), ("IND", "Indianapolis", "Colts"), ("JAX", "Jacksonville", "Jaguars"),
         ("KC", "Kansas City", "Chiefs"), ("LAR", "Los Angeles", "Rams"), ("LAC", "Los Angeles", "Chargers"),
         ("LV", "Las Vegas", "Raiders"), ("MIA", "Miami", "Dolphins"), ("MIN", "Minnesota", "Vikings"),
         ("NE", "New England", "Patriots"), ("NO", "New Orleans", "Saints"), ("NYG", "New York", "Giants"),
         ("NYJ", "New York", "Jets"), ("PHI", "Philadelphia", "Eagles"), ("PIT", "Pittsburgh", "Steelers"),
         ("SEA", "Seattle", "Seahawks"), ("SF", "San Francisco", "49ers"), ("TB", "Tampa Bay", "Buccaneers"),
         ("TEN", "Tennessee", "Titans"), ("WAS", "Washington", "Commanders"))
# the game's order is not the seed's: put the Giants first and the Rams (STL in a retail roster) second
GAME_ORDER = (23, 16) + tuple(i for i in range(32) if i not in (23, 16))


def seed_document():
    """A small seed in the j5-seed schema (nfl2k5_history_seed/v1). The names are test values, not data."""
    seasons = []
    for year, rows in ((2025, {"NYG": (4, 13, 0, 4, "missed", "Coach One"), "LA": (12, 5, 0, 1, "lost_divisional", "Coach Two")}),
                       (2024, {"NYG": (3, 14, 0, 4, "missed", "Coach One"), "LA": (10, 7, 0, 1, "lost_wild_card", "Coach Two")}),
                       (2023, {"NYG": (6, 11, 0, 3, "missed", "Coach One")}),
                       (2022, {"NYG": (9, 7, 1, 3, "lost_divisional", "Coach One")}),
                       (2011, {"NYG": (9, 7, 0, 1, "won_super_bowl", "Coach Three")})):
        seasons.append({"season": year, "teams": [{"club": k, "label": "STL" if k == "LA" and year < 2016 else k,
                                                   "w": w, "l": l, "t": t, "place": p, "playoffs": po, "coach": c}
                                                  for k, (w, l, t, p, po, c) in rows.items()]})
    awards = [{"season": 2025, "award": "mvp", "winners": [{"name": "Test Passer", "club": "LA", "position": "QB"}]},
              {"season": 2024, "award": "mvp", "winners": [{"name": "Other Passer", "club": "BUF", "position": "QB"}]},
              {"season": 2025, "award": "coy", "winners": [{"name": "Coach Four", "club": "NE", "position": None}]},
              {"season": 2025, "award": "dpoy", "winners": [{"name": "Edge Rusher", "club": "CLE", "position": "EDGE"}]}]
    records = [{"category": "pass_yds", "kind": "season", "value": 5477, "name": "Record Passer", "year": 2013,
                "club": "DEN", "position": "QB"},
               {"category": "rush_yds", "kind": "game", "value": 296, "name": "Record Runner", "year": 2007,
                "club": "MIN", "position": "RB"}]
    hof = [{"year": 2026, "name": "Member Two", "position": "QB", "club": "NO"},
           {"year": 2025, "name": "Member One", "position": "CB", "club": "PHI"},
           {"year": 2025, "name": "Member Three", "position": "LB", "club": "NYG"}]
    club_records = [{"club": "NYG", "category": "pass_yds", "kind": "season", "value": 4933, "name": "Giants Passer",
                     "year": 2011, "position": "QB"}]
    leaders = [{"club": "NYG", "category": "pass_yds", "rank": 1, "value": 57023, "name": "Giants Passer",
                "position": "QB"},
               {"club": "NYG", "category": "pass_yds", "rank": 2, "value": 33462, "name": "Older Passer",
                "position": "QB"}]
    return {"schema": "nfl2k5_history_seed/v1", "seasons": seasons, "awards": awards, "nfl_records": records,
            "hall_of_fame": hof, "club_records": club_records, "club_leaders": leaders}


class StaticTests(unittest.TestCase):
    """Run everywhere."""

    def test_template_fits_and_links_only_to_known_symbols(self):
        self.assertLessEqual(len(runtime.CODE), hist.CODE_SIZE)
        self.assertEqual(hist.REQUESTS, (("nfl2k5_history_screen", "code", 16384, 16),
                                         ("nfl2k5_history_screen", "data", 64, 16),
                                         ("nfl2k5_history_screen", "read_only", 0x9000, 16)))
        for offset, kind, symbol, _value in runtime.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertIn(symbol, ("code", "state", "ro", "xtnd_ptr"))
            self.assertLessEqual(offset + 4, len(runtime.CODE))
        for entry in ("hist_enter", "hist_input", "hist_draw", "box_enter", "box_input", "box_draw",
                      "hist_schedule_hook", "hist_schedule_x", "hist_card_flip", "hist_card_rows", "hist_card_bio"):
            self.assertIn(entry, runtime.LABELS)

    def test_code_relocates_with_its_pages(self):
        a = hist.code_for(0x1600000, 0x1700000, 0x1800000, 0x1900000)
        b = hist.code_for(0x1601000, 0x1700000, 0x1800000, 0x1900000)
        self.assertEqual(len(a), hist.CODE_SIZE)
        self.assertTrue(a.endswith(b"\xcc" * (hist.CODE_SIZE - len(runtime.CODE))))
        own = {off for off, kind, symbol, _v in runtime.RELOCATIONS if kind == 1 and symbol == "code"}
        differ = {i for i in range(len(a)) if a[i] != b[i]}
        self.assertTrue(differ)
        self.assertTrue(differ <= {off + k for off in own for k in range(4)})
        # without a footer owner every reference to its word is 0
        c = hist.code_for(0x1600000, 0x1700000, 0x1800000, 0)
        for off, kind, symbol, value in runtime.RELOCATIONS:
            if symbol == "xtnd_ptr":
                self.assertEqual(struct.unpack_from("<I", c, off)[0], value + struct.unpack_from("<i", runtime.CODE, off)[0] & 0xFFFFFFFF)

    def test_sites(self):
        rows = hist.sites(0x1600000, 0x1800000, 0x400)
        self.assertEqual([r[0] for r in rows], ["espn_rows", "schedule_input"])
        espn, schedule = rows
        self.assertEqual((espn[1], espn[2], espn[3]), (0x525674, struct.pack("<I", 0x5253C0), struct.pack("<I", 0x1800400)))
        self.assertEqual((schedule[1], schedule[2]), (0x24D2E5, bytes.fromhex("f7c320020000")))
        self.assertEqual(schedule[3][0], 0xE8)
        self.assertEqual(schedule[3][5], 0x90)
        self.assertEqual(0x24D2E5 + 5 + struct.unpack_from("<i", schedule[3], 1)[0],
                         hist.labels(0x1600000)["hist_schedule_hook"])

    def test_the_owner_is_late(self):
        self.assertIn("nfl2k5_history_screen", space.LATE_OWNERS)
        rows = space._scale_allocations(list(hist.REQUESTS))
        kinds = {r["kind"] for r in rows if r["owner"] == hist.OWNER}
        self.assertEqual(kinds, {"code", "data", "read_only"})

    def test_names_positions_and_clubs(self):
        self.assertEqual(hist.short_name("Patrick Mahomes"), "P. MAHOMES")
        self.assertEqual(hist.short_name("Odell Beckham Jr."), "O. BECKHAM JR.")
        self.assertEqual(hist.short_name("Brady"), "BRADY")
        self.assertEqual(hist.position_code("QB"), 0)
        self.assertEqual(hist.position_code("RB"), 7)
        self.assertEqual(hist.position_code("EDGE"), 16)
        self.assertEqual(hist.position_code(None), 0xFF)
        self.assertEqual(hist.club_key("STL"), "LA")
        self.assertEqual(hist.club_key("LAR"), "LA")
        self.assertEqual(hist.club_key("OAK"), "LV")
        self.assertEqual(hist.club_key("SD"), "LAC")
        self.assertEqual(hist.club_key("JAC"), "JAX")
        self.assertEqual(len(hist.CLUBS_2026), 32)

    def test_read_only_block_layout(self):
        rows12 = bytes(range(256)) * 2 + bytes(624 - 512)
        content = hist.build_ro(0x1800000, 0x1600000, rows12, seed_document())
        self.assertEqual(len(content), hist.RO_SIZE)
        self.assertEqual(content[:4], b"HSR1")
        at = hist.labels(0x1600000)
        # the ESPN.com rows: the twelve given, TEAM HISTORY (push), the end marker
        r = hist.ro_rows_offset(content)
        self.assertEqual(content[r:r + 624], rows12)
        kind, label, target = struct.unpack_from("<3I", content, r + 624)
        self.assertEqual(kind, 0)
        self.assertEqual(content[label - 0x1800000:label - 0x1800000 + 26].decode("utf-16le"), "Team History\0")
        self.assertEqual(struct.unpack_from("<I", content, r + 676)[0], 3)
        # the History descriptor: title, events, Team Standings' handler/layout/frame/flags
        d = hist.ro_history_descriptor(content)
        self.assertEqual(target, 0x1800000 + d)
        words = struct.unpack_from("<11I", content, d)
        self.assertEqual(words[2:], (0xF3DA0, 0, 0, 0, 0xEAA50C, 0, 0x02400044, 0x018D0052, 0x15))
        events, pairs = words[1] - 0x1800000, []
        while True:
            event, actions = struct.unpack_from("<II", content, events + 8 * len(pairs))
            if not event:
                break
            kind, fn = struct.unpack_from("<II", content, actions - 0x1800000)
            self.assertEqual(kind, 1)
            self.assertEqual(struct.unpack_from("<I", content, actions - 0x1800000 + 36)[0], 0)
            pairs.append((event, fn))
        self.assertEqual(pairs, [(9, 0x6C080), (1, at["hist_enter"]), (6, at["hist_input"]), (8, at["hist_draw"])])
        box = hist.ro_field(content, "box_descriptor")
        words = struct.unpack_from("<11I", content, box)
        self.assertEqual(content[words[0] - 0x1800000:words[0] - 0x1800000 + 20].decode("utf-16le"), "Box Score\0")
        legend = hist.ro_field(content, "box_legend")
        self.assertEqual(content[legend:legend + 28].decode("utf-16le"), "for Box Score\0")

    def test_seed_tables(self):
        content = hist.build_ro(0x1800000, 0x1600000, bytes(624), seed_document())
        clubs, seasons = hist.ro_field(content, "clubs"), hist.ro_field(content, "seasons")
        names = hist.ro_field(content, "names")

        def name(offset):
            end = content.index(b"\0", names + offset)
            return content[names + offset:end].decode()

        k = hist.CLUBS_2026.index("NYG")
        aliases = content[clubs + 16 * k:clubs + 16 * k + 12]
        first, count = struct.unpack_from("<HH", content, clubs + 16 * k + 12)
        self.assertEqual(aliases[:4], b"NYG\0")
        self.assertEqual(count, 5)
        years = [struct.unpack_from("<H", content, seasons + 10 * (first + i))[0] for i in range(count)]
        self.assertEqual(years, [2025, 2024, 2023, 2022, 2011])
        line = seasons + 10 * (first + 4)
        year, w, l, t, place_playoff, coach = struct.unpack_from("<HBBBBH", content, line)
        self.assertEqual((w, l, t, place_playoff & 15, place_playoff >> 4, name(coach)), (9, 7, 0, 1, 5, "C. THREE"))
        rams = hist.CLUBS_2026.index("LA")
        self.assertEqual(content[clubs + 16 * rams:clubs + 16 * rams + 12], b"LAR\0LA\0\0STL\0")
        self.assertEqual(hist.ro_field(content, "hof_count"), 3)
        self.assertEqual(hist.ro_field(content, "book_count"), 2)

    def test_a_seed_that_does_not_fit_leaves_out_club_leaders_then_club_records(self):
        doc = seed_document()
        doc["club_leaders"] = [{"club": "NYG", "category": "passing_yards", "rank": 1, "value": i,
                                "name": f"Leader Number{i:05d}", "position": "QB"} for i in range(2000)]
        content, dropped = hist.build_ro_fitting(0x1800000, 0x1600000, bytes(624), doc)
        self.assertEqual(dropped, ["club_leaders"])
        self.assertEqual(hist.ro_field(content, "leaders"), 0)
        self.assertEqual(hist.ro_field(content, "hof_count"), 3)
        with self.assertRaises(hist.HistoryScreenError):
            hist.build_ro(0x1800000, 0x1600000, bytes(624), doc)

    def test_footer_blocks_and_the_encoder(self):
        self.assertEqual(hist.FOOTER_MAGIC, b"2K5XTND1")
        self.assertEqual({k: v[1] for k, v in hist.FOOTER_BLOCKS.items()}, {k: v[1] for k, v in J23_BLOCKS.items()})
        body = j23_body({})
        self.assertEqual(len(body), J23_BODY_SIZE)
        try:
            from mod_editor.core import nfl2k5_franchise_extension as ext
        except ImportError:
            return                                     # the footer branch is not in this tree yet
        view = ext.read_body(body)
        self.assertTrue(view["header_ok"], view)
        self.assertEqual(sorted(view["blocks"]), [1, 2, 3, 4, 5, 6])
        for block in ext.BLOCKS:
            self.assertEqual((block.offset, block.size), J23_BLOCKS[block.id])
            self.assertEqual(hist.FOOTER_BLOCKS[block.id], (block.name, block.size))
        self.assertEqual(ext.pack_person("T", "BRADY", "QB"), person("T", "BRADY", "QB"))

    def test_runtime_header_names_the_footer_layout(self):
        source = (ROOT / "tools/nfl2k5_history_screen/runtime.c").read_text(encoding="utf-8")
        for fragment in ("#define X_SEASONS 1", "#define X_TOTALS 2", "#define X_RECORDS 3", "#define X_LEADERS 4",
                         "#define X_HALL 5", "#define X_BOX 6", "#define SEASON_RECORD 592u", "#define BOX_ENTRY 512u",
                         "#define LEAGUE_RECORDS_AT 9232u", "#define LEAGUE_LEADERS_AT 15376u"):
            self.assertIn(fragment, source)

    def test_seed_schema_shapes_of_j5(self):
        """j5-seed's document: awards under winners, records with holders and scope, members under hall_of_fame."""
        doc = {"seasons": [{"season": 2025, "teams": [{"club": "SEA", "w": 14, "l": 3, "t": 0, "place": 1,
                                                        "playoffs": "champion", "coach": "Mike Macdonald"}]}],
               "awards": {"kinds": [], "winners": [{"season": 2025, "award": "sb_mvp",
                                                    "winners": [{"name": "Kenneth Walker", "club": "SEA",
                                                                 "position": "HB"}]}]},
               "nfl_records": [{"category": "sacks_half", "scope": "season", "value": 22.5,
                                "holders": [{"name": "Michael Strahan", "season": 2001, "club": "NYG"},
                                            {"name": "T. J. Watt", "season": 2021, "club": "PIT"}]},
                               {"category": "points", "scope": "career", "value": 2673, "holders": [{"name": "X"}]}],
               "hall_of_fame": {"through_class": 2026, "members": [{"name": "Drew Brees", "class": 2026,
                                                                    "position": "QB", "club": "NO"}]}}
        seasons, awards, book, hof, _records, _leaders = hist._seed_tables(doc)
        self.assertEqual(seasons["SEA"][0]["playoff"], 5)
        self.assertEqual(awards["sbmvp"][0]["name"], "Kenneth Walker")
        self.assertEqual(len(book), 1)                   # points have no footer category
        self.assertEqual((book[0]["value"], book[0]["year"], book[0]["name"], book[0]["club"]),
                         (45, 2001, "Michael Strahan", "NYG"))
        self.assertEqual((hof[0]["year"], hof[0]["name"], hof[0]["pos"]), (2026, "Drew Brees", 0))

    def test_j5b_leaders_document(self):
        """j5b-leaders' document (nfl2k5_franchise_leaders/v1): career top three, the season and game record holders,
        values already in the footer's units (half sacks), clubs by today's code (LAR = the Rams); its lists replace the
        seed's own."""
        doc = {"schema": "nfl2k5_franchise_leaders/v1", "clubs": {
            "NYG": {"career": {"sacks_half": [{"rank": 1, "name": "Pass Rusher", "position": "DE", "value": 283}],
                               "passing_yards": [{"rank": r, "name": f"Passer {r}", "position": "QB", "value": 9000 - r}
                                                 for r in (1, 2, 3, 4)]},
                    "season": {"sacks_half": [{"rank": 1, "name": "Pass Rusher", "position": "DE", "season": 2001,
                                               "value": 45}]},
                    "game": {"rushing_yards": [{"rank": 1, "name": "Game Runner", "position": "HB", "season": 2006,
                                                "week": 17, "value": 234}]}},
            "LAR": {"career": {"receptions": [{"rank": 1, "name": "Rams Catcher", "position": "WR", "value": 942}]},
                    "season": {}, "game": {}}}}
        merged = hist.with_leaders(seed_document(), doc)
        _s, _a, _b, _h, records, leaders = hist._seed_tables(merged)
        sacks = hist.LEADER_CATEGORIES.index("sacks_half")
        self.assertIn(dict(category=sacks, rank=0, name="Pass Rusher", value=283, pos=16), leaders["NYG"])
        self.assertEqual([r["value"] for r in leaders["NYG"] if r["category"] == 0], [8999, 8998, 8997])
        self.assertEqual([(r["name"], r["value"], r["year"], r["kind"]) for r in records["NYG"]],
                         [("Pass Rusher", 45, 2001, 1), ("Game Runner", 234, 2006, 0)])
        self.assertEqual([r["name"] for r in leaders["LA"]], ["Rams Catcher"])
        self.assertIsNone(hist.with_leaders(None, None))
        self.assertEqual(hist.with_leaders(None, doc)["club_leaders"][0]["club"], "LAR")
        with self.assertRaises(hist.HistoryScreenError):
            hist.with_leaders(seed_document(), {"schema": "other", "clubs": {}})
        # the files: either one alone still gives a document; neither gives None
        with tempfile.TemporaryDirectory() as tmp:
            leaders_file, seed_file = Path(tmp) / "leaders.json", Path(tmp) / "seed.json"
            leaders_file.write_text(json.dumps(doc), encoding="utf-8")
            seed_file.write_text(json.dumps(seed_document()), encoding="utf-8")
            self.assertIsNone(hist.load_seed(Path(tmp) / "none.json", Path(tmp) / "none2.json"))
            self.assertEqual(len(hist.load_seed(Path(tmp) / "none.json", leaders_file)["club_leaders"]), 5)
            self.assertEqual(len(hist.load_seed(seed_file, Path(tmp) / "none2.json")["club_leaders"]), 2)
            both = hist.load_seed(seed_file, leaders_file)
            self.assertEqual(len(both["club_leaders"]), 5)
            self.assertEqual(len(both["seasons"]), 5)
            content, dropped = hist.build_ro_fitting(0x1800000, 0x1600000, bytes(624), both)
            self.assertEqual(dropped, [])

    def test_help_text_is_plain(self):
        for text in (hist.HELP_TEXT, hist.UI_LABEL):
            self.assertNotIn("—", text)
            self.assertNotIn("–", text)
        self.assertLessEqual(len(hist.UI_LABEL), 60)


@unittest.skipUnless(HAVE_UC, "unicorn is not installed")
class NativeTests(unittest.TestCase):
    """The installed runtime on the retail executable, under Unicorn."""

    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("the retail executable is not available")
        cls.retail = retail
        cls.payload, cls.receipt = hist.install(retail, seed=seed_document(), xtnd_ptr_va=0x3080000)
        cls.at = hist.labels(int(cls.receipt["code_va"], 16))
        cls.ro = int(cls.receipt["ro_va"], 16)
        cls.state = int(cls.receipt["data_va"], 16)
        cls.content = XbeImage(cls.payload).read(cls.ro, hist.RO_SIZE)

    # ---- machine ----------------------------------------------------------------------------------------------
    FOOTER = 0x3100000            # 128 KiB mapped, then an unmapped page: a read past the footer faults
    WORDS = 0x3080000             # the footer owner's body-pointer word (as code_for linked it)

    def machine(self, footer: bytes | None = None, seasons=0, at_end=False):
        m = Machine(self.payload)
        m.capture_text()
        m.rects = []

        def rect(mm):
            sp = mm.reg("ESP")
            mm.rects.append(tuple(mm.float_at(sp + 4 + 4 * i) for i in range(5)))
        m.hook(0x6BBE0, rect, 20)
        m.sounds = []
        m.hook(0x14D390, lambda mm: mm.sounds.append(1))
        m.uc.mem_map(self.WORDS, 0x1000)
        m.uc.mem_map(self.FOOTER, 0x20000)
        if footer is not None:
            body = self.FOOTER + (0x20000 - len(footer) if at_end else 0)
            m.uc.mem_write(body, footer[:0x20000])
            m.put(self.WORDS, body)
        # league: 32 clubs at the league table, names in the heap
        teams, names = m.HEAP + 0x4000, m.HEAP + 0x10000
        m.put(LEAGUE_MODE, 2)
        m.put(TEAM_COUNT_VA, 32)
        m.club_va = []
        for slot, k in enumerate(GAME_ORDER):
            abbr, city, nick = CLUBS[k]
            if abbr == "LAR":
                abbr = "STL"           # a retail-style label still finds the Rams' seed
            team = teams + 0x1F4 * slot
            m.uc.mem_write(team, bytes(0x1F4))
            for field, text in ((0x108, abbr), (0x138, city), (0x104, nick)):
                m.uc.mem_write(names, (text + "\0").encode("utf-16le"))
                m.put(team + field, names)
                names += 2 * len(text) + 2
            m.put(LEAGUE_TEAMS + 4 * slot, team)
            m.club_va.append(team)
        m.put(FOCUS, m.club_va[0])                      # the Giants
        for i in range(32):
            m.put(HUMAN + 4 * i, 1 if i == 0 else 0)
        m.put(SEASONS, seasons)
        m.put(ROSTER, m.ROOT)
        m.manager = m.HEAP + 0x70000
        m.uc.mem_write(m.manager, bytes(0x200))
        m.put(m.manager + 0x10C, m.HEAP + 0x72000)      # context; +0x590 = 0 (no pad filter)
        m.uc.mem_write(m.HEAP + 0x72000, bytes(0x1000))
        return m

    @staticmethod
    def call_keep(m, va, regs, budget=200000):
        """Machine.call without clobbering the callee-saved registers the site's caller passes (ebx, esi, edi)."""
        sp = m.SP - 4
        m.put(sp, m.STOP)
        m.reg("ESP", sp)
        for name, value in regs.items():
            m.reg(name, value)
        m.uc.emu_start(va, m.STOP, count=budget)
        assert m.reg("EIP") == m.STOP, hex(m.reg("EIP"))

    def draw(self, m, page=0, club=0, scroll=0, award=0, filt=0):
        m.call(self.at["hist_enter"], ecx=m.manager)
        for i, v in enumerate((page, club, scroll, award, filt)):
            m.put(self.state + 4 * i, v)
        m.text.clear()
        m.rects.clear()
        m.call(self.at["hist_draw"], ecx=m.manager)
        return [t[0] for t in m.text]

    def rows(self, m):
        """{row: [texts left to right]} from the captured positions (row bars start at y 88, 30 apart)."""
        out = {}
        for text, _font, _align, _colour, pos in m.text:
            if pos and 88 <= pos[1] < 388:
                out.setdefault(int((pos[1] - 88) // 30), []).append((pos[0], text))
        return {r: [t for _x, t in sorted(v)] for r, v in sorted(out.items())}

    # ---- the screen -------------------------------------------------------------------------------------------------
    def test_enter_starts_on_the_focus_club(self):
        m = self.machine()
        m.put(FOCUS, m.club_va[1])
        m.call(self.at["hist_enter"], ecx=m.manager)
        self.assertEqual([m.get(self.state + 4 * i) for i in range(5)], [0, 1, 0, 0, 0])

    def test_seasons_page_without_a_footer(self):
        m = self.machine()
        texts = self.draw(m, page=0, club=0)
        self.assertIn("NEW YORK GIANTS".upper(), [t.upper() for t in texts])
        rows = self.rows(m)
        self.assertEqual(rows[0], ["SINCE 2004: NO SEASONS PLAYED YET"])   # the retail executable's year base
        self.assertEqual(rows[1], ["YEAR", "W-L-T", "DIV", "PLAYOFFS", "HEAD COACH"])
        self.assertEqual(rows[2], ["2025", "4-13", "4TH", "C. ONE"])
        self.assertEqual(rows[5], ["2022", "9-7-1", "3RD", "LOST DIVISIONAL", "C. ONE"])
        self.assertEqual(rows[6], ["2011", "9-7", "1ST", "WON SUPER BOWL", "C. THREE"])
        self.assertEqual(len(m.rects), 10)
        self.assertEqual(m.rects[0][:2], (40.0, 88.0))
        self.assertEqual(m.rects[9][:2], (40.0, 358.0))
        self.assertIn("SEASONS", texts)
        self.assertIn("HALL OF FAME", texts)

    def test_rams_seed_found_by_a_retail_label(self):
        m = self.machine()
        self.draw(m, page=0, club=1)
        rows = self.rows(m)
        self.assertEqual(rows[2], ["2025", "12-5", "1ST", "LOST DIVISIONAL", "C. TWO"])

    def season_footer(self):
        """Two closed franchise seasons (2026, 2027) for the Giants (club 0), the totals, and 2027's awards."""
        seasons = bytearray(18960)
        records = []
        for year, w, l, place, playoff, coach in ((2026, 11, 6, 1, 2, ("C", "NEWMAN")), (2027, 13, 4, 1, 5, ("C", "NEWMAN"))):
            record = bytearray(592)
            struct.pack_into("<HBBBBBB", record, 0, year, 1, 17, 1, 3, 30, 20)
            line = struct.pack("<BBBBHH7sB", w, l, 0, playoff | 8 | (place - 1) << 5 | 0x80, 400, 300,
                               person(*coach, 31), 1)
            record[80:96] = line
            if year == 2027:
                record[16:23] = person("J", "SMITH", "HB")      # MVP
                record[23] = 3                                  # club index 2 + 1
            records.append(bytes(record))
        for i, record in enumerate(records):                    # ring slots 0, 1; head = 2
            seasons[16 + 592 * i:16 + 592 * (i + 1)] = record
        struct.pack_into("<BBHHB", seasons, 0, 2, 2, 2027, 2026, 32)
        totals = bytearray(528)
        struct.pack_into("<HH", totals, 0, 2026, 2)
        struct.pack_into("<HHHBBBBBBHH", totals, 16, 24, 10, 0, 2, 2, 1, 1, 2, 2, 4, 1)
        return {1: bytes(seasons), 2: bytes(totals)}

    def test_seasons_page_with_franchise_seasons(self):
        m = self.machine(j23_body(self.season_footer()), seasons=2)
        self.draw(m, page=0, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[0], ["SINCE 2026: 24-10   PLAYOFFS 2   DIVISION TITLES 2   SUPER BOWLS 1"])
        self.assertEqual(rows[2], ["2027", "13-4", "1ST", "WON SUPER BOWL", "C. NEWMAN"])
        self.assertEqual(rows[3], ["2026", "11-6", "1ST", "LOST DIVISIONAL", "C. NEWMAN"])
        self.assertEqual(rows[4], ["2025", "4-13", "4TH", "C. ONE"])
        # scrolled: 7 lines, 8 rows: the scroll clamps to 0
        self.draw(m, page=0, club=0, scroll=5)
        self.assertEqual(m.get(self.state + 8), 0)
        # another club has no line in those seasons: the year shows alone
        self.draw(m, page=0, club=2)
        self.assertEqual(self.rows(m)[2], ["2027"])

    def test_awards_page(self):
        m = self.machine()
        self.draw(m, page=4, award=0)
        rows = self.rows(m)
        self.assertEqual(rows[0], ["YEAR", "PLAYER", "POS", "CLUB"])
        self.assertEqual(rows[1], ["2025", "T. PASSER", "QB", "STL"])   # the Rams under the game's label
        self.assertEqual(rows[2], ["2024", "O. PASSER", "QB", "BUF"])
        texts = self.draw(m, page=4, award=6)
        self.assertIn("COACH OF THE YEAR", texts)
        self.assertEqual(self.rows(m)[1], ["2025", "C. FOUR", "NE"])
        self.draw(m, page=4, award=2)
        self.assertEqual(self.rows(m)[1], ["2025", "E. RUSHER", "DE", "CLE"])

    def test_awards_with_franchise_winners(self):
        m = self.machine(j23_body(self.season_footer()))
        self.draw(m, page=4, award=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["2027", "J. SMITH", "HB", "ARI"])
        self.assertEqual(rows[2], ["2026", "-"])                 # a season with no MVP kept
        self.assertEqual(rows[3], ["2025", "T. PASSER", "QB", "STL"])

    def test_hall_of_fame_page_and_filter(self):
        hall = bytearray(4624)
        inductees = ((person("A", "OLDER", "QB"), 5, 2026), (person("A", "NEWMAN", "WR"), 1, 2031))
        for i, (who, club_plus_one, year) in enumerate(inductees):
            hall[16 + 16 * i:23 + 16 * i] = who
            struct.pack_into("<BHHBBH", hall, 23 + 16 * i, club_plus_one, year, year - 5, 1, 12, 900)
        hall[0] = len(inductees)
        m = self.machine(j23_body({5: bytes(hall)}))
        self.draw(m, page=5, filt=0)
        rows = self.rows(m)
        self.assertEqual(rows[0], ["CLASS", "MEMBER", "POS", "CLUB"])
        self.assertEqual(rows[1], ["2031", "A. NEWMAN", "WR", "NYG"])
        # the footer's 2026 inductee belongs to a class the seed lists (its newest is 2026): listed once, by the seed
        self.assertEqual(rows[2], ["2026", "M. TWO", "QB", "NO"])
        self.assertEqual(rows[3], ["2025", "M. ONE", "CB", "PHI"])
        self.assertEqual(rows[4], ["2025", "M. THREE", "OLB", "NYG"])
        texts = self.draw(m, page=5, filt=1)             # the Giants only
        self.assertIn("NEW YORK GIANTS", [t.upper() for t in texts])
        rows = self.rows(m)
        self.assertEqual(rows[1], ["2031", "A. NEWMAN", "WR", "NYG"])
        self.assertEqual(rows[2], ["2025", "M. THREE", "OLB", "NYG"])
        self.assertNotIn(3, rows)

    def test_record_book_and_club_records(self):
        m = self.machine()
        texts = self.draw(m, page=3)
        self.assertIn("NATIONAL FOOTBALL LEAGUE", texts)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "SEASON", "5,477", "R. PASSER (DEN)", "2013"])
        self.assertEqual(rows[2], ["RUSH YARDS", "GAME", "296", "R. RUNNER (MIN)", "2007"])
        self.draw(m, page=1, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "SEASON", "4,933", "G. PASSER", "2011"])
        # a franchise league record that beats the real NFL record replaces it, marked NEW (records block, league part)
        records = bytearray(9520)
        e = 9232 + 12 * (0 * 2 + 1)                      # passing yards, season
        records[e:e + 7] = person("Z", "ARM", "QB")
        struct.pack_into("<BHBB", records, e + 7, 6, 5600, 2028 - 1900, 0)
        e = 16 + 12 * ((0 * 12 + 0) * 2 + 1)             # the Giants' club record, passing yards, season
        records[e:e + 7] = person("Z", "ARM", "QB")
        struct.pack_into("<BHBB", records, e + 7, 1, 5600, 2028 - 1900, 0)
        m = self.machine(j23_body({3: bytes(records)}))
        self.draw(m, page=3)
        self.assertEqual(self.rows(m)[1], ["PASS YARDS", "SEASON", "5,600", "Z. ARM (BUF)", "NEW 2028"])
        self.draw(m, page=1, club=0)
        self.assertEqual(self.rows(m)[1], ["PASS YARDS", "SEASON", "5,600", "Z. ARM", "NEW 2028"])

    def test_leaders_page(self):
        m = self.machine()
        self.draw(m, page=2, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "1.", "57,023", "G. PASSER"])
        self.assertEqual(rows[2], ["2.", "33,462", "O. PASSER"])
        self.draw(m, page=2, club=3)
        self.assertEqual(self.rows(m)[1], ["NO ALL-TIME LEADERS IN THIS BUILD YET"])
        # the footer's table (seeded at the franchise start, counted since) is the live one; NEW marks franchise entries
        leaders = bytearray(16176)
        for rank, (who, value, flags) in enumerate(((person("G", "PASSER", "QB"), 57400, 1 | 2 | 4),
                                                    (person("N", "ROOKIE", "QB"), 41000, 1 | 8))):
            e = 16 + 16 * ((0 * 10 + 0) * 3 + rank)
            leaders[e:e + 7] = who
            struct.pack_into("<BIHH", leaders, e + 7, flags, value, 0xFFFF, 0)
        m = self.machine(j23_body({4: bytes(leaders)}))
        self.draw(m, page=2, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "1.", "57,400", "G. PASSER"])
        self.assertEqual(rows[2], ["2.", "41,000", "N. ROOKIE", "NEW"])

    def test_leaders_merge_a_footer_that_was_never_seeded(self):
        """A footer table without real (seeded) entries keeps franchise-era players only: merged with the seed's by
        value, a player in both counted once (his larger total), equal values keep the seed's line first."""
        leaders = bytearray(16176)

        def put(category, rank, who, value, flags):
            e = 16 + 16 * ((0 * 10 + category) * 3 + rank)
            leaders[e:e + 7] = who
            struct.pack_into("<BIHH", leaders, e + 7, flags, value, 0xFFFF, 0)
        put(0, 0, person("N", "ROOKIE", "QB"), 41000, 1 | 8)
        put(0, 1, person("G", "PASSER", "QB"), 20000, 1 | 8)          # the seed's leader, counted since the start only
        put(1, 0, person("T", "THROWER", "QB"), 30, 1 | 8)            # a category the seed has no lines for
        m = self.machine(j23_body({4: bytes(leaders)}))
        self.draw(m, page=2, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "1.", "57,023", "G. PASSER"])
        self.assertEqual(rows[2], ["2.", "41,000", "N. ROOKIE", "NEW"])
        self.assertEqual(rows[3], ["3.", "33,462", "O. PASSER"])
        self.assertEqual(rows[4], ["PASS TD", "1.", "30", "T. THROWER", "NEW"])
        # the same player ahead of his seeded total in the footer: his footer line, once
        put(0, 1, person("G", "PASSER", "QB"), 60000, 1 | 8)
        m = self.machine(j23_body({4: bytes(leaders)}))
        self.draw(m, page=2, club=0)
        rows = self.rows(m)
        self.assertEqual(rows[1], ["PASS YARDS", "1.", "60,000", "G. PASSER", "NEW"])
        self.assertEqual(rows[2], ["2.", "41,000", "N. ROOKIE", "NEW"])
        self.assertEqual(rows[3], ["3.", "33,462", "O. PASSER"])
        # another club's table stays its own
        self.draw(m, page=2, club=3)
        self.assertEqual(self.rows(m)[1], ["NO ALL-TIME LEADERS IN THIS BUILD YET"])

    def test_real_leaders_spot_checks(self):
        """j5b-leaders' pinned data (data/nfl2k5_franchise_leaders_2026.json) when this tree carries it."""
        seed = hist.load_seed()
        if seed is None or not hist.LEADERS_PATH.is_file():
            self.skipTest("no franchise leaders data in this tree")
        payload, receipt = hist.install(self.retail, seed=seed, xtnd_ptr_va=self.WORDS)
        self.assertEqual(receipt["seed_parts_left_out"], [])
        saved = self.payload
        try:
            type(self).payload = payload
            m = self.machine()
            self.draw(m, page=2, club=0)                  # the Giants
            lines = list(self.rows(m).values())
            self.assertIn(["PASS YARDS", "1.", "57,023", "E. MANNING"], lines)
            self.draw(m, page=2, club=0, scroll=40)
            self.assertIn(["SACKS", "1.", "141.5", "M. STRAHAN"], list(self.rows(m).values()))
            self.draw(m, page=1, club=0)
            self.assertIn(["PASS YARDS", "SEASON", "4,933", "E. MANNING", "2011"], list(self.rows(m).values()))
        finally:
            type(self).payload = saved

    def press(self, m, pressed=0, repeat=0):
        m.put(PADS, 1)
        m.put(PADS + 8, pressed)
        m.put(PADS + 12, repeat)
        m.call(self.at["hist_input"], ecx=m.manager)
        m.put(PADS + 8, 0)
        m.put(PADS + 12, 0)

    def test_input_cycles_pages_clubs_awards_filters_and_scroll(self):
        m = self.machine()
        m.call(self.at["hist_enter"], ecx=m.manager)
        self.press(m, pressed=0x1000)                    # Black
        self.assertEqual(m.get(self.state), 1)
        self.press(m, pressed=0x2000)                    # White
        self.press(m, pressed=0x2000)
        self.assertEqual(m.get(self.state), 5)
        self.press(m, pressed=0x8000)                    # R on HALL OF FAME: the filter
        self.assertEqual(m.get(self.state + 16), 1)
        self.press(m, pressed=0x4000)
        self.press(m, pressed=0x4000)
        self.assertEqual(m.get(self.state + 16), 32)
        m.put(self.state, 0)
        self.press(m, pressed=0x4000)                    # L on SEASONS: the club, wrapping
        self.assertEqual(m.get(self.state + 4), 31)
        self.press(m, repeat=0x2000000)
        self.press(m, repeat=0x2000000)
        self.assertEqual(m.get(self.state + 8), 2)
        self.press(m, repeat=0x1000000)
        self.assertEqual(m.get(self.state + 8), 1)
        self.assertEqual(len(m.sounds), 10)
        m.put(self.state, 4)
        self.press(m, pressed=0x8000)
        self.assertEqual(m.get(self.state + 12), 1)

    # ---- box scores and the Schedule ---------------------------------------------------------------------------
    def game(self, m, row=2, slot=3, home=0, away=25, quarters=((7, 3, 7, 7, 0), (0, 10, 0, 7, 0))):
        m.uc.mem_write(GRID + 8 * (17 * row + slot), bytes((3, home, away, 9, 21, 26, 13, 0)))
        m.uc.mem_write(SCORES + 10 * (17 * row + slot), bytes(quarters[0] + quarters[1]))

    def box_footer(self, row=2, slot=3, home=0, away=25, year=2004, links=(40, 41)):
        """One kept game: the user club (home, the Giants) lines by player record index, the opponent's leader."""
        box = bytearray(12304)
        struct.pack_into("<HBB", box, 0, year, 1, 1)
        e = 16
        struct.pack_into("<BBBBBBBBB", box, e, row, slot, home, away, 24, 17, 0, 1 | 2, len(links))
        struct.pack_into("<16H", box, e + 16, 24, 21, 352, 250, 102, 31, 22, 25, 1, 1, 0, 2, 5, 45, 6, 13)
        struct.pack_into("<16H", box, e + 48, 17, 17, 298, 199, 99, 30, 18, 24, 2, 1, 1, 3, 7, 60, 4, 12)
        box[e + 80:e + 87] = person("J", "HURTS", "QB")
        box[e + 87] = 1
        struct.pack_into("<4h", box, e + 88, 18, 30, 199, 1)
        lines = ((links[0], 0, 1, (22, 31, 250, 2, 1, 12)), (links[1], 7, 2, (21, 102, 1, 3, 20, 0)))
        for i, (link, pos, kind, values) in enumerate(lines):
            struct.pack_into("<HBB6h", box, e + 144 + 16 * i, link, pos, kind, *values)
        return j23_body({6: bytes(box)})

    def roster_players(self, m, names=(("Daniel", "Jones"), ("Saquon", "Barkley")), links=(40, 41)):
        m.put(m.ROOT, 100)
        m.put(m.ROOT + 4, m.PLAYERS)
        at = m.HEAP + 0x30000
        out = []
        for (first, last), link in zip(names, links):
            player = m.PLAYERS + link * 0x54
            m.uc.mem_write(player, bytes(0x54))
            for field, text in ((0x10, first), (0x14, last)):
                m.uc.mem_write(at, (text + "\0").encode("utf-16le"))
                m.put(player + field, at)
                at += 2 * len(text) + 2
            out.append(player)
        return out

    def box(self, m, row=2, slot=3, scroll=0):
        m.put(self.state + 20, row)
        m.put(self.state + 24, slot)
        m.put(self.state + 28, scroll)
        m.text.clear()
        m.call(self.at["box_draw"], ecx=m.manager)
        return [t[0] for t in m.text]

    def test_box_score_line_score_for_any_game(self):
        m = self.machine()
        self.game(m)
        texts = self.box(m)
        self.assertIn("WEEK 3: Eagles 17, Giants 24", texts)
        rows = self.rows(m)
        self.assertEqual(rows[0], ["FINAL", "Q1", "Q2", "Q3", "Q4", "T"])
        self.assertEqual(rows[1], ["PHI", "0", "10", "0", "7", "17"])
        self.assertEqual(rows[2], ["NYG", "7", "3", "7", "7", "24"])
        self.assertEqual(rows[4], ["FULL STATS ARE KEPT FOR YOUR TEAM'S GAMES"])
        # an unplayed cell draws nothing
        m.uc.mem_write(GRID + 8 * (17 * 2 + 3), bytes((1,)))
        self.assertEqual(self.box(m), [])

    def test_box_score_with_kept_stats(self):
        m = self.machine(self.box_footer())
        self.roster_players(m)
        self.game(m)
        self.box(m)
        rows = self.rows(m)
        self.assertEqual(rows[3], ["TEAM STATS", "PHI", "NYG"])
        self.assertEqual(rows[4], ["FIRST DOWNS", "17", "21"])
        self.assertEqual(rows[8], ["COMP/ATT", "18/30", "22/31"])
        self.box(m, scroll=20)
        rows = self.rows(m)
        self.assertEqual(rows[6], ["THIRD DOWNS", "4/12", "6/13"])
        self.assertEqual(rows[7], ["NYG", "PASSING", "D. JONES", "22/31  250 YDS  2 TD  1 INT"])
        self.assertEqual(rows[8], ["NYG", "RUSHING", "S. BARKLEY", "21 CAR  102 YDS  1 TD  3 REC 20 YDS"])
        self.assertEqual(rows[9], ["PHI", "PASSING", "J. HURTS", "18/30  199 YDS  1 TD"])
        self.assertEqual(m.get(self.state + 28), 7)      # 7 rows of 14 lines: the scroll clamps to 7

    def test_box_score_ignores_a_box_of_another_game_or_season(self):
        m = self.machine(self.box_footer(year=2003))
        self.game(m)
        self.box(m)
        self.assertEqual(self.rows(m)[4], ["FULL STATS ARE KEPT FOR YOUR TEAM'S GAMES"])
        m = self.machine(self.box_footer(home=5))
        self.game(m)
        self.box(m)
        self.assertEqual(self.rows(m)[4], ["FULL STATS ARE KEPT FOR YOUR TEAM'S GAMES"])

    def test_schedule_x_pushes_the_box_score_on_a_played_game(self):
        m = self.machine()
        self.game(m)
        pushes, legends = [], []
        m.hook(0x6E390, lambda mm: pushes.append((mm.reg("ECX"), mm.reg("EDX"))))
        m.hook(0xF35A0, lambda mm: legends.append((mm.reg("EDX"), mm.get(mm.reg("ESP") + 4))), 4)
        m.hook(0x24B680, lambda mm: 2)
        m.hook(0x24B6C0, lambda mm: 3)
        m.put(PADS, 1)
        m.put(PADS + 8, 0)
        self.assertEqual(m.call(self.at["hist_schedule_x"], ecx=m.manager, edx=0), 0)
        legend = self.ro + hist.ro_field(self.content, "box_legend")
        self.assertEqual(legends[-1], (1, legend))   # the |M_HELP| (X) slot
        self.assertEqual(pushes, [])
        m.put(PADS + 8, 0x400)                           # X pressed
        self.assertEqual(m.call(self.at["hist_schedule_x"], ecx=m.manager, edx=0), 1)
        self.assertEqual(pushes, [(m.manager, self.ro + hist.ro_field(self.content, "box_descriptor"))])
        self.assertEqual((m.get(self.state + 20), m.get(self.state + 24)), (2, 3))
        self.assertEqual(m.get(PADS + 8) & 0x400, 0)     # the press is consumed
        # a bye (0xFFFF) or an unplayed game: no legend, no push
        m.hook(0x24B6C0, lambda mm: 0xFFFF)
        m.put(PADS + 8, 0x400)
        self.assertEqual(m.call(self.at["hist_schedule_x"], ecx=m.manager, edx=0), 0)
        self.assertEqual(legends[-1], (1, 0))
        self.assertEqual(len(pushes), 1)

    def test_schedule_hook_keeps_the_retail_back_test(self):
        m = self.machine()
        m.hook(0x24B680, lambda mm: 0xFFFF)
        m.hook(0x24B6C0, lambda mm: 0xFFFF)
        m.hook(0xF35A0, lambda mm: None, 4)
        m.put(PADS, 1)
        for buttons, zero in ((0x220, False), (0x20, False), (0x400, True), (0, True)):
            self.call_keep(m, self.at["hist_schedule_hook"], {"EBX": buttons, "EDI": m.manager, "ESI": 0})
            self.assertEqual(bool(m.reg("EFLAGS") & 0x40), zero, hex(buttons))
            self.assertEqual((m.reg("EBX"), m.reg("EDI"), m.reg("ESI")), (buttons, m.manager, 0))

    # ---- the game log -----------------------------------------------------------------------------------------
    def test_game_log_page(self):
        m = self.machine(self.box_footer())
        jones, barkley = self.roster_players(m)
        self.game(m)
        m.put(CARD_PLAYER, jones)
        card = m.HEAP + 0x31000                          # the honors owner's state: page, first row, screen, saved
        m.uc.mem_write(card, struct.pack("<4I", 2, 0x80000000, 0, 0))
        m.text.clear()
        m.call(self.at["hist_card_rows"], ecx=card)
        self.assertEqual([t[0] for t in m.text], ["WK 3 VS PHI W 24-17  22/31  250 YDS  2 TD  1 INT"])
        self.assertEqual(m.get(card + 4), 0x80000000)
        m.text.clear()
        self.assertEqual(m.call(self.at["hist_card_bio"]), 1)
        self.assertEqual([t[0] for t in m.text], ["GAME LOG: THIS SEASON", "YOUR TEAM'S GAMES ARE KEPT"])
        self.assertEqual(m.call(self.at["hist_card_bio"]), 0)       # only in a frame whose rows it drew
        m.put(CARD_PLAYER, barkley + 0x54)               # a player with no lines
        m.text.clear()
        m.call(self.at["hist_card_rows"], ecx=card)
        self.assertEqual([t[0] for t in m.text], ["NO GAMES KEPT FOR THIS PLAYER THIS SEASON"])

    # ---- damage ---------------------------------------------------------------------------------------------------
    def test_damaged_footers_read_as_empty(self):
        good = j23_body(self.season_footer())
        for damage in ("magic", "version", "slots", "id", "block version", "absent", "offset", "size", "pointer"):
            body = bytearray(good)
            if damage == "magic":
                body[0] = ord("X")
            elif damage == "version":
                struct.pack_into("<H", body, 8, 2)
            elif damage == "slots":
                struct.pack_into("<H", body, 0x12, 99)
            elif damage == "id":
                struct.pack_into("<H", body, 0x40, 9)
            elif damage == "block version":
                body[0x42] = 2
            elif damage == "absent":
                body[0x43] = 0
            elif damage == "offset":
                struct.pack_into("<I", body, 0x44, 0xFFFFFF00)
            elif damage == "size":
                struct.pack_into("<I", body, 0x48, 0x7FFFFFFF)
            m = self.machine(bytes(body), seasons=2)
            if damage == "pointer":
                m.put(self.WORDS, 0x3)
            self.draw(m, page=0, club=0)
            rows = self.rows(m)
            self.assertEqual(rows[2], ["2025", "4-13", "4TH", "C. ONE"], damage)

    def test_no_page_reads_past_the_footer(self):
        # a body with every block full of 0xFF (counts, offsets and lines at their limits) at the end of the mapped region:
        # every page, every club, the box score and the game log draw without touching the unmapped page after it
        blocks = {i: b"\xff" * size for i, (_offset, size) in J23_BLOCKS.items()}
        body = j23_body(blocks)
        self.assertEqual(len(body) % 4, 0)
        m = self.machine(body, seasons=2, at_end=True)
        self.roster_players(m)
        for page in range(6):
            for club in (0, 31):
                self.draw(m, page=page, club=club, scroll=99)
        self.game(m)
        for scroll in (0, 99):
            self.box(m, scroll=scroll)
        card = m.HEAP + 0x31000
        m.uc.mem_write(card, struct.pack("<4I", 2, 0x80000000, 0, 0))
        m.put(CARD_PLAYER, m.PLAYERS + 40 * 0x54)
        m.call(self.at["hist_card_rows"], ecx=card)

    def test_real_seed_spot_checks(self):
        """The pinned real-history seed (j5-seed's data/nfl2k5_history_2026.json) when this tree carries it."""
        seed = hist.load_seed()
        if seed is None:
            self.skipTest("no real-history seed in this tree")
        payload, _ = hist.install(self.retail, seed=seed, xtnd_ptr_va=self.WORDS)
        saved = self.payload
        try:
            type(self).payload = payload
            m = self.machine()
            self.draw(m, page=0, club=0, scroll=14)       # the Giants, 2011 at the top after 14 newer seasons
            rows = self.rows(m)
            self.assertEqual(rows[2], ["2011", "9-7", "1ST", "WON SUPER BOWL", "T. COUGHLIN"])
            self.assertEqual(rows[6], ["2007", "10-6", "2ND", "WON SUPER BOWL", "T. COUGHLIN"])
            self.draw(m, page=3)
            book = self.rows(m)
            self.assertIn(["PASS YARDS", "SEASON", "5,477", "P. MANNING (DEN)", "2013"], list(book.values()))
            self.draw(m, page=5)
            self.assertTrue(any(r[:2] == ["2026", "D. BREES"] for r in self.rows(m).values()))
        finally:
            type(self).payload = saved

    def test_card_cycle_through_the_champions_owner(self):
        """Honors (with champions) and this owner on one image: the card cycles card, honors, champions, game log."""
        from mod_editor.core import nfl2k5_champions as champions
        from mod_editor.core import nfl2k5_honors as honors
        both, _ = honors.apply(self.retail)
        both, receipt = hist.install(both, seed=seed_document(), xtnd_ptr_va=self.WORDS)
        self.assertEqual((honors.status(both), hist.status(both)), ("applied", "applied"))
        ch = champions.labels(champions.allocations(both)["code"]["va"])
        m = Machine(both)
        m.capture_text()
        m.uc.mem_map(self.WORDS, 0x1000)                 # the footer host's word: no body
        state = m.HEAP + 0x31000
        m.uc.mem_write(state, bytes(16))

        def flip(buttons):
            return m.call(ch["champions_flip"], ecx=buttons, edx=state)

        pages = []
        for _ in range(5):                               # Black: forward
            flip(0x1000)
            pages.append((m.get(state), m.get(state + 4)))
        self.assertEqual(pages, [(1, 0), (2, 0), (2, 0x80000000), (0, 0), (1, 0)])
        for _ in range(2):                               # White: back from honors to card, card to the game log
            flip(0x2000)
        self.assertEqual((m.get(state), m.get(state + 4)), (2, 0x80000000))
        self.assertEqual(flip(0x2000000), 1)             # Down scrolls the game log, its view kept
        self.assertEqual(m.get(state + 4), 0x80000001)
        m.text.clear()
        m.call(ch["champions_ratings"], ecx=state)       # the game log draws the table area
        self.assertEqual([t[0] for t in m.text], ["NO GAMES KEPT FOR THIS PLAYER THIS SEASON"])
        m.text.clear()
        m.call(ch["champions_bio"])
        self.assertEqual([t[0] for t in m.text], ["GAME LOG: THIS SEASON", "YOUR TEAM'S GAMES ARE KEPT"])
        flip(0x2000)                                     # back to the champions page: its own list and bio again
        self.assertEqual((m.get(state), m.get(state + 4)), (2, 0))
        m.text.clear()
        m.call(ch["champions_ratings"], ecx=state)
        m.call(ch["champions_bio"])
        self.assertIn("CHAMPIONS: NONE YET", [t[0] for t in m.text])
        # without this owner (the retail row pointer), the champions owner keeps its three pages
        m.put(0x525674, 0x5253C0)
        m.uc.mem_write(state, bytes(16))
        pages = []
        for _ in range(4):
            flip(0x1000)
            pages.append(m.get(state))
        self.assertEqual(pages, [1, 2, 0, 1])

if __name__ == "__main__":
    unittest.main()
