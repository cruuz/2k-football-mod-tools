"""2026 team identity (schema v3). Synthetic resources everywhere; the retail classes need the private extraction.

Only synthetic images are written. The retail classes read the user's own extracted disc and default.xbe and run
the game's own key code under Unicorn.
"""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tests", ROOT / "tools"):
    sys.path.insert(0, str(p))
from mod_editor.core import nfl2k5_team_names_2026 as names
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_ages as ages
from mod_editor.core.nfl2k5_text_catalog import Nfl2k5TextCatalog, load_roster_resources
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body, RETAIL_EXTRACTION
from nfl2k5_xiso_fixture import SyntheticXiso

NFL_COM_2026 = {  # https://www.nfl.com/teams/ (2026-09-23)
    7: "Arizona Cardinals", 8: "Los Angeles Chargers", 22: "Las Vegas Raiders", 23: "Los Angeles Rams",
    25: "Washington Commanders"}


def synthetic_resource():
    """A synthetic main ROST carrying the retail team-name runs and pointers the manifest pins."""
    data = names.manifest()
    body = bytearray(synthetic_body())
    body[:64] = bytes.fromhex(data["body_prefix_hex"])
    for pin in data["structure_pins"]:
        value = bytes.fromhex(pin["hex"])
        body[pin["offset"]:pin["offset"] + len(value)] = value
    targets = {}
    for block in data["blocks"]:
        body[block["start"]:block["start"] + block["size"]] = names._layout_bytes(block["retail"], block["size"])
        targets.update(names._targets(block, "retail"))
    for name, field in data["pointers"].items():
        struct.pack_into("<i", body, field, targets[name] - field + 1)
    return bytes.fromhex(data["resource_header_hex"]) + bytes(body)


class PlanTests(unittest.TestCase):
    def test_names_and_uniform_choice_refuse_together_both_rewrite_the_jersey_rule(self):
        from mod_editor.core import mod_build
        plan = mod_build.BuildPlan("in.iso", "out.iso")
        plan.team_names_2026 = True
        self.assertEqual(mod_build.validate_plan(plan), [])
        for mode in ("rule", "choice"):
            plan.uniform_choice = mode
            problems = mod_build.validate_plan(plan)
            self.assertEqual(len(problems), 1)
            self.assertIn("Uniform choice", problems[0])
        plan.team_names_2026 = False
        self.assertEqual(mod_build.validate_plan(plan), [])


class ManifestTests(unittest.TestCase):
    def test_full_2026_names_for_the_five_changed_teams_and_retail_elsewhere(self):
        data = names.manifest()
        self.assertEqual([t["index"] for t in data["teams"]], list(range(32)))
        changed = {t["index"]: t for t in data["teams"] if t["retail"] != t["written"]}
        self.assertEqual(sorted(changed), [7, 8, 22, 23, 25])
        for index, full in NFL_COM_2026.items():
            w = changed[index]["written"]
            self.assertEqual(f"{w['city']} {w['nickname']}", full)
            self.assertEqual(changed[index]["full_name"], full)
        codes = {7: "ARI", 8: "LAC", 22: "LV", 23: "LAR", 25: "WAS"}
        self.assertEqual({i: t["written"]["abbreviation"] for i, t in changed.items()}, codes)
        self.assertEqual({i: t["written"]["city_abbreviation"] for i, t in changed.items()}, codes)
        self.assertEqual(changed[25]["written"]["label_nickname"], "Commanders")
        for t in data["teams"]:
            self.assertEqual(t["written"]["asset_code"], t["retail"]["asset_code"])
            self.assertEqual(t["written"]["label_abbreviation"], t["retail"]["label_abbreviation"])
            self.assertNotIn(".", t["written"]["city"])     # no cramped short forms

    def test_runs_fit_share_only_equal_codes_and_never_move_an_engine_key_out_of_its_team(self):
        data = names.manifest()
        shared = {}
        for block in data["blocks"]:
            for item in block["written"]:
                self.assertLessEqual(item["offset"] + 2 * (len(item["text"]) + 1), block["size"])
                if len(item["fields"]) > 1:
                    shared.setdefault(block["id"], []).append(sorted(item["fields"]))
        self.assertEqual(shared, {
            "team.8": [["team.8.abbreviation", "team.8.city_abbreviation"]],
            "team.23": [["team.23.abbreviation", "team.23.city_abbreviation"]],
            "team.25": [["team.25.nickname", "team_label.25.nickname"],
                        ["team.25.abbreviation", "team.25.city_abbreviation"]]})
        freed = next(b for b in data["blocks"] if b["id"] == "team_label.25.nickname")
        self.assertEqual(freed["written"], [])
        names.check_engine_keys(data)
        for bad_edit in ("asset", "label", "text"):
            bad = json.loads(json.dumps(data))
            if bad_edit == "asset":
                bad["teams"][8]["written"]["asset_code"] = "99"
            elif bad_edit == "label":
                bad["teams"][23]["written"]["label_abbreviation"] = "LAR"
            else:
                block = next(b for b in bad["blocks"] if b["id"] == "team.8")
                item = next(i for i in block["written"] if "team.8.asset_code" in i["fields"])
                item["text"] = "99"
            with self.assertRaisesRegex(names.TeamNamesError, "engine key"):
                names.check_engine_keys(bad)

    def test_xbe_sites_are_the_key_paths_the_dallas_rule_and_the_35_colour_rows(self):
        sites = {label: (va, before, after) for label, va, before, after in names.xbe_sites()}
        keys = sorted(label for label in sites if not label.startswith("menu_colours."))
        self.assertEqual(keys, ["dallas_road_uniform_match", "dallas_road_uniform_preview", "espn25_alias_helper",
                                "espn25_nickname_compare", "schedule_codes", "schedule_key", "thanksgiving_key",
                                "user_playbook_team"])
        colour_codes = sorted(label.split(".")[1] for label in sites if label.startswith("menu_colours."))
        teams = sorted(t["retail"]["asset_code"] for t in names.manifest()["teams"])
        self.assertEqual(colour_codes, sorted(teams + ["31", "34", "35"]))   # the 32 teams, NFL, AFC, NFC
        rows = {row["code"]: row for row in names.colours()["rows"]}
        self.assertEqual((rows["23"]["written"]["primary"], rows["23"]["written"]["secondary"]), ("FF003594", "FFFFD100"))
        self.assertEqual((rows["24"]["written"]["primary"], rows["29"]["written"]["primary"]), ("FF0080C6", "FF5A1414"))
        for code, row in rows.items():
            va, before, after = sites[f"menu_colours.{code}"]
            self.assertEqual(va, names.COLOUR_TABLE + row["entry"] * names.COLOUR_STRIDE + 4)
            self.assertEqual(len(before), 24)
        for _va, before, after in sites.values():
            self.assertEqual(len(before), len(after))
            self.assertNotEqual(before, after)
        _va, retail, keyed = sites["schedule_codes"]
        self.assertEqual([retail[i:i + 8].decode("utf-16le").rstrip("\0") for i in range(0, 256, 8)],
                         list(names.CODE_TABLE_ORDER))
        codes = [keyed[i:i + 8].decode("utf-16le").rstrip("\0") for i in range(0, 256, 8)]
        by_abbr = {t["retail"]["abbreviation"]: t["retail"]["asset_code"] for t in names.manifest()["teams"]}
        self.assertEqual(codes, [by_abbr[c] for c in names.CODE_TABLE_ORDER])
        helper = sites["espn25_alias_helper"][2]
        self.assertEqual(helper[0x28:0x28 + 40].decode("utf-16le").split("\0")[:2], ["Commanders", "Redskins"])
        self.assertEqual(sites["espn25_nickname_compare"][2], names._call(names.ESPN25_COMPARE, names.ALIAS_HELPER))


class NamesTests(unittest.TestCase):
    def setUp(self):
        self.before = synthetic_resource()

    def test_exact_runs_idempotence_and_zero_growth(self):
        data = names.manifest()
        after, receipt = names.apply(self.before)
        self.assertEqual(names.status(self.before), "retail")
        self.assertEqual(names.status(after), "applied")
        self.assertEqual(receipt["changed_runs"], 6)
        self.assertEqual(receipt["pointers_moved"], 16)
        self.assertEqual(receipt["growth_bytes"], 0)
        allowed = {32 + i for b in data["blocks"] for i in range(b["start"], b["start"] + b["size"])}
        allowed |= {32 + f + k for f in data["pointers"].values() for k in range(4)}
        self.assertEqual(len(after), len(self.before))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(self.before, after)) if a != b))
        again, repeated = names.apply(after)
        self.assertEqual(again, after)
        self.assertTrue(repeated["already_applied"])
        self.assertEqual(repeated["changed_runs"], 0)

    def test_each_partial_write_and_foreign_byte_refuses(self):
        data = names.manifest()
        after, _ = names.apply(self.before)
        for block in data["blocks"]:
            start, size = 32 + block["start"], block["size"]
            for src, dst in ((self.before, after), (after, self.before)):
                mixed = bytearray(src)
                mixed[start:start + size] = dst[start:start + size]
                self.assertEqual(names.status(bytes(mixed)), "foreign", block["id"])
                with self.assertRaises(names.TeamNamesError):
                    names.apply(bytes(mixed))
        for name, field in data["pointers"].items():
            for src, dst in ((self.before, after), (after, self.before)):
                mixed = bytearray(src)
                mixed[32 + field:36 + field] = dst[32 + field:36 + field]
                if bytes(mixed) != src:
                    self.assertEqual(names.status(bytes(mixed)), "foreign", name)
        for off in (0, 32 + 0x10, 32 + 0x58):
            foreign = bytearray(self.before)
            foreign[off] ^= 0x01
            with self.assertRaises(names.TeamNamesError):
                names.apply(bytes(foreign))
        self.assertEqual(names.status(self.before[:-1]), "foreign")

    def test_a_foreign_reference_into_a_run_refuses(self):
        data = names.manifest()
        block = next(b for b in data["blocks"] if b["id"] == "team.23")
        for target in (block["start"], block["start"] + 2):
            body = bytearray(self.before)
            struct.pack_into("<i", body, 32 + 0xAFA8 + 0x10, target - (0xAFA8 + 0x10) + 1)   # a player name
            self.assertEqual(names.status(bytes(body)), "foreign")

    def test_catalog_uses_the_written_names_and_rejects_manual_conflicts(self):
        assets = [SimpleNamespace(asset_id=f"nfl2k5.text.rost.5.{c['domain']}.{c['team_index']}.{c['field']}",
                                  value=c["retail"], label=c["field"]) for c in names.cells()]
        catalog = SimpleNamespace(assets=assets)
        self.assertEqual(names.catalog_overrides(catalog), {})
        values = names.catalog_overrides(catalog, enabled=True)
        self.assertEqual(values["nfl2k5.text.rost.5.team.25.nickname"], "Commanders")
        self.assertEqual(values["nfl2k5.text.rost.5.team_label.25.nickname"], "Commanders")
        self.assertEqual(values["nfl2k5.text.rost.5.team.8.abbreviation"], "LAC")
        self.assertEqual(values["nfl2k5.text.rost.5.team.8.city"], "Los Angeles")
        self.assertEqual(values["nfl2k5.text.rost.5.team.22.city"], "Las Vegas")
        self.assertEqual(values["nfl2k5.text.rost.5.team_label.23.abbreviation"], "STL")   # the playbook file key
        assets[0].value = "CUSTOM"
        with self.assertRaisesRegex(names.TeamNamesError, "manual edit"):
            names.catalog_overrides(catalog, enabled=True)

    def test_real_archive_adapter_relocated_pack_copy_noop_refusal_and_closed_handles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            fixture = SyntheticXiso(root, [(100 + i, b"DUMY" + bytes(256)) for i in range(5)] +
                                    [(5, self.before), (200, b"TAIL" + bytes(256))],
                                    pack_sizes=(0xA0000,), pack_sectors=(96,))
            original = fixture.path.read_bytes()  # capped < 1 MB synthetic image only
            self.assertEqual(names.image_status(fixture.path), "retail")
            with rr._outer_image()(fixture.path) as archive:
                entry = archive.entries[5]
                offset = archive.packs[0].image_offset + entry.virtual_offset
            receipt = names.apply_to_image(fixture.path)
            expected = bytearray(original)
            expected[offset:offset + len(self.before)] = names.apply(self.before)[0]
            self.assertEqual(fixture.path.read_bytes(), expected)
            self.assertEqual(receipt["status"], "applied")
            with patch.object(rr._outer_image(), "write", side_effect=AssertionError("idempotent write")):
                self.assertTrue(names.apply_to_image(fixture.path)["already_applied"])
            fixture.path.write_bytes(original)
            with patch.object(rr._outer_image(), "write", return_value=1):
                with self.assertRaisesRegex(names.TeamNamesError, "short"):
                    names.apply_to_image(fixture.path)
            os.replace(fixture.path, root / "closed.iso")


class RetailNamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RETAIL_EXTRACTION / "vc_53450030/0").is_file():
            raise unittest.SkipTest("private retail extraction is absent")
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(RETAIL_EXTRACTION)
        with rr._outer_image()(RETAIL_EXTRACTION) as archive:
            cls.entry = archive.entries[5]
            cls.before = archive.read(cls.entry.virtual_offset, cls.entry.size)
            cls.name_ids = {e.name_id for e in archive.entries}

    def test_retail_names_and_both_orders_with_ages_and_roster_edits(self):
        named, _ = names.apply(self.before)
        actual = names.read_team_identities(named)
        self.assertEqual({i: actual[i]["display"] for i in NFL_COM_2026}, NFL_COM_2026)
        codes = ["ARI", "LAC", "LV", "LAR", "WAS"]
        self.assertEqual([actual[i]["abbreviation"] for i in (7, 8, 22, 23, 25)], codes)
        self.assertEqual([actual[i]["city_abbreviation"] for i in (7, 8, 22, 23, 25)], codes)
        self.assertEqual(names.read_team_identities(self.before, enabled=True), actual)
        retail = names.read_team_identities(self.before)
        self.assertEqual([r for i, r in enumerate(actual) if i not in NFL_COM_2026],
                         [r for i, r in enumerate(retail) if i not in NFL_COM_2026])

        def change(resource):
            doc = rr.RosterDocument(resource[32:])
            doc.players[0].record.set("scramble", 97)
            ages.apply(doc, ages.preview(doc, 2004, 2026))
            return resource[:32] + doc.to_body()
        self.assertEqual(names.apply(change(self.before))[0], change(named))

    def test_manifest_matches_the_retail_runs_and_every_label_code_names_a_playbook_file(self):
        self.assertEqual(names.status(self.before), "retail")
        named, _ = names.apply(self.before)
        body = named[32:]
        count = struct.unpack_from("<I", body, 0x88)[0]
        table = names._relative(body, 0x8C)
        codes = [rr.read_utf16z(body, names._relative(body, table + 8 * i + 4))[0] for i in range(count)]
        self.assertEqual(len(codes), 36)
        stock = [c for c in codes if c not in ("UA", "UB")]   # user books are handled by name
        missing = [c for c in stock if zlib.crc32(f"{c}-pb.iff".upper().encode("utf-16le")) not in self.name_ids]
        self.assertEqual(missing, [])

    def test_existing_team_identity_catalog_points_at_same_fields(self):
        header = struct.unpack_from("<4s7I", self.before)
        row = dict(kind="ROST", outer_index=5, outer_id=hex(self.entry.name_id), outer_size=self.entry.size,
                   chunk_index=0, chunk_offset=0, stored_size=header[1], word_08=header[2], word_0c=header[3],
                   word_10=header[4], word_14=header[5])
        inventory = {"schema": "nfl2k5_resource_chunk_inventory/v1", "chunks": [row]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "inventory.json"
            path.write_text(json.dumps(inventory))
            views = load_roster_resources(RETAIL_EXTRACTION / "vc_53450030/0", path, [5])
        catalog = Nfl2k5TextCatalog.from_parsed(inventory, views)
        overrides = names.catalog_overrides(catalog, enabled=True)
        written = {t["index"]: t["written"] for t in names.manifest()["teams"]}
        for team in catalog.teams[:32]:
            fields = dict(team.text_asset_ids)
            for name in ("city", "nickname", "abbreviation", "city_abbreviation"):
                asset = next(a for a in catalog.assets if a.asset_id == fields[name])
                self.assertEqual(overrides.get(asset.asset_id, asset.value), written[team.team_index][name])

    def test_composes_with_history_prospect_names_and_position_pools_in_both_orders(self):
        from mod_editor.core import nfl2k5_team_history as history, nfl2k5_prospect_names as prospects
        import nfl2k5_roster_reclassify as reclassify
        history_rows = history.read_csv(history.SHIPPED_CSV.read_text())
        prospect_rows = prospects.read_csv(prospects.SHIPPED_CSV.read_text())

        def other_passes(resource):
            parsed = reclassify.parse_resource(5, 0, resource)
            moves, _schemes = reclassify.plan_resource(parsed, {})
            body = bytearray(parsed.body)
            reclassify.apply_moves(body, moves)
            body, _ = history.apply_body(bytes(body), history_rows)
            body, _ = prospects.apply_body(body, prospect_rows)
            return resource[:32] + body
        self.assertEqual(names.apply(other_passes(self.before))[0], other_passes(names.apply(self.before)[0]))


# --------------------------------------------------------------------------- the game's own key code under Unicorn
ARENA, STACK, SCRATCH, SENTINEL = 0x20000000, 0x30000000, 0x31000000, 0x32000000


def _sections(xbe):
    base, = struct.unpack_from("<I", xbe, 0x104)
    count, headers = struct.unpack_from("<II", xbe, 0x11C)
    for i in range(count):
        flags, va, vsize, raw, rawsize = struct.unpack_from("<5I", xbe, headers - base + i * 56)
        yield flags, va, vsize, raw, rawsize


class _Game:
    """default.xbe mapped at its VAs and a main ROST arena at ARENA with the pointers these paths read made absolute."""

    def __init__(self, xbe, body):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_32)
        top = max(va + max(vs, rs) for _f, va, vs, _r, rs in _sections(xbe))
        uc.mem_map(0x10000, (top - 0x10000 + 0xFFF) & ~0xFFF)
        uc.mem_write(0x10000, xbe[:0x1000])
        for _flags, va, _vsize, raw, rawsize in _sections(xbe):
            uc.mem_write(va, xbe[raw:raw + rawsize])
        mem = bytearray(body)

        def absolute(field):
            value = struct.unpack_from("<i", body, field)[0]
            struct.pack_into("<I", mem, field, ARENA + field + value - 1 if value else 0)
        tables = {}
        for pair in range(0, 0x60, 8):
            value = struct.unpack_from("<i", body, 0x44 + pair)[0]
            tables[pair] = (struct.unpack_from("<I", body, 0x40 + pair)[0], 0x44 + pair + value - 1 if value else None)
            absolute(0x44 + pair)
        teams, self.teams_at = tables[0x18]
        for i in range(teams):
            for field in (0x104, 0x108, 0x10C, 0x110, 0x138, 0x13C):
                absolute(self.teams_at + i * 0x1F4 + field)
        labels, labels_at = tables[0x48]
        for i in range(labels):
            absolute(labels_at + i * 8)
            absolute(labels_at + i * 8 + 4)
        uc.mem_map(ARENA, (len(body) + 0xFFF) & ~0xFFF)
        uc.mem_write(ARENA, bytes(mem))
        uc.mem_write(names.ROSTER_ROOT, struct.pack("<I", ARENA + 0x40))
        for base in (STACK, SCRATCH, SENTINEL):
            uc.mem_map(base, 0x100000)
        self.scratch = SCRATCH

    def wide(self, text):
        at, raw = self.scratch, (text + "\0").encode("utf-16le")
        self.uc.mem_write(at, raw)
        self.scratch += (len(raw) + 15) & ~15
        return at

    def run(self, start, stop, **registers):
        from unicorn import x86_const as r
        sp = STACK + 0xF0000
        self.uc.mem_write(sp, struct.pack("<II", SENTINEL, 0xDEAD0000))
        self.uc.reg_write(r.UC_X86_REG_ESP, sp)
        for name, value in registers.items():
            self.uc.reg_write(getattr(r, f"UC_X86_REG_{name.upper()}"), value)
        self.uc.emu_start(start, stop, count=5_000_000)

    def team(self, pointer):
        return None if pointer == 0 else (pointer - ARENA - self.teams_at) // 0x1F4

    def keys(self):
        from unicorn import x86_const as r
        self.run(0x2BEAA0, SENTINEL)
        schedule = [struct.unpack("<i", self.uc.mem_read(0xC8C768 + 4 * k, 4))[0] for k in range(32)]
        thanksgiving = []
        for code in (0xE9A4D4, 0xE9A494):     # the table's DAL and DET entries (0x2BF47C, 0x2BF486)
            self.run(0x2BEA70, SENTINEL, ebx=code)
            thanksgiving.append(self.team(self.uc.reg_read(r.UC_X86_REG_EAX)))
        espn25 = {}
        for selector in ("redskins", "oilers", "rams", "chargers", "raiders", "cardinals", "giants"):
            self.run(0x20C4E0, SENTINEL, ecx=self.wide(selector))
            espn25[selector] = self.team(self.uc.reg_read(r.UC_X86_REG_EAX))
        playbook = {}
        for code in ("STL", "SD", "OAK", "ARZ", "WAS", "SF"):
            self.uc.mem_write(0xB75A40 + 0x30, struct.pack("<I", self.wide(code)))
            sp = STACK + 0xE0000
            self.uc.mem_write(sp, struct.pack("<I", 0xDEAD0000))   # the pushed ebx that 0xE9B0C pops
            self.uc.reg_write(r.UC_X86_REG_ESP, sp)
            self.uc.reg_write(r.UC_X86_REG_EDI, 0)
            self.uc.emu_start(0xE9AB0, 0xE9B1A, count=5_000_000)
            playbook[code] = self.team(self.uc.reg_read(r.UC_X86_REG_ESI))
        return dict(schedule=schedule, thanksgiving=thanksgiving, espn25=espn25, playbook=playbook)


def _short_forms(resource):
    """The 2026-09-23 t1 roster (display cells only), as MyNFL saves made with it carry it."""
    body = bytearray(resource[32:])
    teams = names._relative(body, 0x5C)

    def put(field, text):
        target = names._relative(body, field)
        old = rr.read_utf16z(body, target)[0]
        raw = (text + "\0").encode("utf-16le")
        assert len(raw) <= 2 * (len(old) + 1)
        body[target:target + 2 * (len(old) + 1)] = raw.ljust(2 * (len(old) + 1), b"\0")
    for index, city, code in ((7, None, "ARI"), (8, "L.A.", "LA"), (22, "L Vegas", "LV"), (23, "L.A.", "LAR")):
        t = teams + index * 0x1F4
        if city:
            put(t + 0x138, city)
        put(t + 0x13C, code)
    put(names._relative(body, teams + 25 * 0x1F4 + 0x110), "Cmdrs")   # the label record's nickname pointer
    return resource[:32] + bytes(body)


class RetailKeyPathTests(unittest.TestCase):
    """PROVED OFFLINE: the retail XBE's own schedule, Thanksgiving, ESPN25 and saved-playbook code."""

    @classmethod
    def setUpClass(cls):
        xbe_path = RETAIL_EXTRACTION / "default.xbe"
        if not ((RETAIL_EXTRACTION / "vc_53450030/0").is_file() and xbe_path.is_file()):
            raise unittest.SkipTest("private retail extraction is absent")
        cls.xbe = xbe_path.read_bytes()
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(RETAIL_EXTRACTION)
        with rr._outer_image()(RETAIL_EXTRACTION) as archive:
            entry = archive.entries[5]
            cls.rost = archive.read(entry.virtual_offset, entry.size)
        cls.named, _ = names.apply(cls.rost)
        cls.keyed, cls.receipt = names.apply_xbe(cls.xbe)
        cls.baseline = _Game(cls.xbe, cls.rost[32:]).keys()

    def test_retail_baseline(self):
        base = self.baseline
        self.assertEqual(sorted(base["schedule"]), list(range(32)))
        self.assertEqual(base["thanksgiving"], [11, 18])
        self.assertEqual(base["espn25"], dict(redskins=25, oilers=30, rams=23, chargers=8, raiders=22,
                                              cardinals=7, giants=15))
        self.assertEqual(base["playbook"], dict(STL=23, SD=8, OAK=22, ARZ=7, WAS=25, SF=0))

    def test_patched_keys_equal_retail_on_2026_retail_and_old_save_rosters(self):
        for label, body in (("2026", self.named[32:]), ("retail", self.rost[32:]),
                            ("t1 short forms", _short_forms(self.rost)[32:])):
            with self.subTest(roster=label):
                self.assertEqual(_Game(self.keyed, body).keys(), self.baseline)

    def test_without_the_key_paths_the_2026_names_break_the_engine(self):
        broken = _Game(self.xbe, self.named[32:]).keys()
        lost = sorted(self.baseline["schedule"][k] for k, v in enumerate(broken["schedule"]) if v == -1)
        self.assertEqual(lost, [7, 8, 22, 23])                # ARZ, SD, OAK and STL slots return -1
        self.assertIsNone(broken["espn25"]["redskins"])       # the moment intro would read NULL+0x10C
        self.assertEqual([broken["playbook"][c] for c in ("STL", "SD", "OAK", "ARZ")], [0, 0, 0, 0])

    def _dallas_swaps(self, xbe, body):
        """{(away, home): swap} from the match block (0x6160F) and the Team Select preview block (0x31F830)."""
        from unicorn import x86_const as r
        game = _Game(xbe, body)
        teams = {}
        for i in range(32):
            team = ARENA + game.teams_at + i * 0x1F4
            fields = {}
            for name, off in (("abbr", 0x108), ("code", 0x10C)):
                fields[name] = struct.unpack("<I", game.uc.mem_read(team + off, 4))[0]
            abbr = bytes(game.uc.mem_read(fields["abbr"], 8)).decode("utf-16le").split("\0")[0]
            teams[abbr] = (team, fields)
        match, preview = {}, {}
        for away, (a_team, a) in teams.items():
            for home, (h_team, h) in teams.items():
                if away == home:
                    continue
                game.uc.mem_write(0xB30B60, struct.pack("<II", a["abbr"], a["code"]))
                game.uc.mem_write(0xB3096C, struct.pack("<II", h["abbr"], h["code"]))
                game.uc.reg_write(r.UC_X86_REG_ESP, STACK + 0xF0000)
                game.uc.emu_start(names.MATCH_RULE, names.MATCH_RULE_END, count=10_000)
                match[away, home] = game.uc.reg_read(r.UC_X86_REG_ESI) != 0
                for reg, value in ((r.UC_X86_REG_ECX, a_team), (r.UC_X86_REG_EBP, h_team),
                                   (r.UC_X86_REG_ESI, 0xEA2CDC), (r.UC_X86_REG_EDI, 0xEA2CE0)):
                    game.uc.reg_write(reg, value)
                game.uc.emu_start(names.PREVIEW_RULE, names.PREVIEW_DONE, count=10_000)
                sides = (game.uc.reg_read(r.UC_X86_REG_EDI), game.uc.reg_read(r.UC_X86_REG_ESI))
                self.assertIn(sides, ((0xEA2CE0, 0xEA2CDC), (0xEA2CDC, 0xEA2CE0)))
                preview[away, home] = sides == (0xEA2CDC, 0xEA2CE0)
        return match, preview

    def test_dallas_road_uniforms_follow_the_2026_rule_in_match_and_preview(self):
        retail_match, retail_preview = self._dallas_swaps(self.xbe, self.rost[32:])
        self.assertEqual(retail_match, retail_preview)
        self.assertEqual(sorted(k for k, v in retail_match.items() if v and k[0] == "DAL"), [("DAL", "TEN"), ("DAL", "WAS")])
        self.assertTrue(all(retail_match[a, "DAL"] for a in {k[0] for k in retail_match} if a != "DAL"))
        self.assertEqual(sum(retail_match.values()), 31 + 2)
        for label, body in (("2026", self.named[32:]), ("retail", self.rost[32:])):
            with self.subTest(roster=label):
                match, preview = self._dallas_swaps(self.keyed, body)
                self.assertEqual(match, preview)
                road = "LAR" if label == "2026" else "STL"
                self.assertEqual(sorted(k for k, v in match.items() if v and k[0] == "DAL"),
                                 sorted([("DAL", "HOU"), ("DAL", "IND"), ("DAL", road)]))
                self.assertTrue(all(match[a, "DAL"] for a in {k[0] for k in match} if a != "DAL"))
                self.assertEqual(sum(match.values()), 31 + 3)

    def test_menu_colour_getters_return_the_2026_rows(self):
        from unicorn import x86_const as r
        rows = names.colours()["rows"]
        for xbe, state in ((self.xbe, "retail"), (self.keyed, "written")):
            game = _Game(xbe, self.named[32:])
            teams_by_code = {}
            for i in range(52):
                team = ARENA + game.teams_at + i * 0x1F4
                code_ptr = struct.unpack("<I", game.uc.mem_read(team + 0x10C, 4))[0]
                code = bytes(game.uc.mem_read(code_ptr, 4)).decode("utf-16le")
                teams_by_code.setdefault(code, team)
            for row in rows:
                with self.subTest(state=state, code=row["code"]):
                    values = row[state]
                    team = teams_by_code[row["code"]]
                    got = {}
                    for name, va in (("primary", 0x68D70), ("secondary", 0x68DC0), ("accent", 0x68E10),
                                     ("background", 0x68E60), ("darker", 0x68EB0), ("menu", 0x6B5B0)):
                        game.run(va, SENTINEL, ecx=team)
                        got[name] = game.uc.reg_read(r.UC_X86_REG_EAX)
                    for name in ("primary", "secondary", "accent", "background"):
                        self.assertEqual(f"{got[name]:08X}", values[name])
                    self.assertEqual(f"{got['darker']:08X}", values["secondary" if values["flag12"] else "primary"])
                    # the menu background: the game's own scaler 0x69FA0 on the chosen slot and scale
                    chosen = int(values["secondary" if values["flag10"] else "primary"], 16)
                    sp = STACK + 0xF0000
                    game.uc.mem_write(sp, struct.pack("<If", SENTINEL, values["scale"]))
                    game.uc.reg_write(r.UC_X86_REG_ESP, sp)
                    game.uc.reg_write(r.UC_X86_REG_ECX, chosen)
                    game.uc.emu_start(0x69FA0, SENTINEL, count=100_000)
                    self.assertEqual(got["menu"], game.uc.reg_read(r.UC_X86_REG_EAX))

    def test_xbe_install_touches_only_the_sites_and_section_digests_and_replays(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(names.xbe_status(self.xbe), "retail")
        self.assertEqual(names.xbe_status(self.keyed), "applied")
        image = XbeImage(self.xbe)
        allowed = set()
        for _label, va, before, _after in names.xbe_sites():
            at = image.offset(va, len(before))
            allowed |= set(range(at, at + len(before)))
        base = struct.unpack_from("<I", self.xbe, 0x104)[0]
        count, headers = struct.unpack_from("<II", self.xbe, 0x11C)
        for i in range(count):
            allowed |= set(range(headers - base + i * 56 + 36, headers - base + i * 56 + 56))
        changed = [i for i, (a, b) in enumerate(zip(self.xbe, self.keyed)) if a != b]
        self.assertTrue(changed and set(changed) <= allowed)
        again, receipt = names.apply_xbe(self.keyed)
        self.assertEqual(again, self.keyed)
        self.assertEqual(receipt["status"], "already_applied")
        mixed = bytearray(self.keyed)
        at = image.offset(names.ESPN25_COMPARE, 5)
        mixed[at:at + 5] = self.xbe[at:at + 5]
        self.assertEqual(names.xbe_status(bytes(mixed)), "foreign")
        with self.assertRaises(names.TeamNamesError):
            names.apply_xbe(bytes(mixed))

    def test_the_scorebug_guard_accepts_the_2026_rows_and_both_install_in_either_order(self):
        # The scorebug's guard on the retail team colour table (scorebar v3 reads it) recognizes the pinned 2026 rows
        # whole, so the scorebug runtime composes with the names option in either order; a partial row stays foreign.
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebug, nfl2k5_scorebug_runtime as runtime
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual((scorebug.xbe_status(self.keyed), runtime.status(self.keyed)), ("retail", "retail"))
        installed, _ = runtime.apply(space.apply(self.keyed, runtime.REQUESTS)[0])
        self.assertEqual((runtime.status(installed), scorebug.xbe_status(installed),
                          names.xbe_status(installed, colours=True)), ("applied", "applied", "applied"))
        first, _ = runtime.apply(space.apply(self.xbe, runtime.REQUESTS)[0])
        both, _ = names.apply_xbe(first)
        self.assertEqual((runtime.status(both), names.xbe_status(both, colours=True)), ("applied", "applied"))
        label, va, before, after = next(site for site in names.xbe_sites()
                                        if site[0].startswith("menu_colours.") and site[2][4:8] != site[3][4:8])
        partial = bytearray(self.keyed)
        at = XbeImage(self.keyed).offset(va, len(before))
        partial[at + 4:at + 8] = before[4:8]       # one row with its retail primary back: not a recognized row
        self.assertEqual(scorebug.xbe_status(bytes(partial)), "foreign", label)

    def test_without_colour_rows_the_scorebug_still_reads_retail_and_forms_never_mix(self):
        # The key paths and the Dallas rule alone (apply_xbe(colours=False)) also compose with the scorebug.
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebug, nfl2k5_scorebug_runtime as runtime
        plain, receipt = names.apply_xbe(self.xbe, colours=False)
        self.assertFalse(receipt["menu_colours"])
        self.assertEqual(names.xbe_status(plain), "applied")
        self.assertEqual(names.xbe_status(plain, colours=False), "applied")
        self.assertEqual(names.xbe_status(plain, colours=True), "foreign")
        self.assertFalse(names.xbe_colours_written(plain))
        self.assertTrue(names.xbe_colours_written(self.keyed))
        self.assertEqual(names.xbe_status(self.keyed, colours=False), "foreign")
        self.assertEqual((scorebug.xbe_status(plain), runtime.status(plain)), ("retail", "retail"))
        bases = [row["basis"] for row in names.xbe_reservations(plain)]
        self.assertFalse(any("menu_colours" in basis for basis in bases))
        self.assertEqual(len(names.xbe_reservations(self.keyed)), len(names.xbe_sites()))
        self.assertEqual(names.apply_xbe(plain, colours=False)[1]["status"], "already_applied")
        with self.assertRaises(names.TeamNamesError):
            names.apply_xbe(plain, colours=True)
        self.assertEqual(_Game(plain, self.named[32:]).keys(), self.baseline)

    def test_the_overwritten_routine_is_dead_in_retail(self):
        # 0xC03F0 (find a team by abbreviation): no call, no jump and no pointer anywhere in the executable.
        import numpy as np
        target = names.ALIAS_HELPER
        self.assertEqual(self.xbe.find(struct.pack("<I", target)), -1)
        for flags, va, _vsize, raw, rawsize in _sections(self.xbe):
            if not flags & 4:
                continue
            data = np.frombuffer(self.xbe[raw:raw + rawsize], dtype=np.uint8)
            at = np.nonzero((data[:-4] == 0xE8) | (data[:-4] == 0xE9))[0]
            disp = (data[at + 1].astype(np.int64) | data[at + 2].astype(np.int64) << 8 |
                    data[at + 3].astype(np.int64) << 16 | data[at + 4].astype(np.int64) << 24)
            disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
            self.assertFalse(np.any(va + at + 5 + disp == target), f"relative branch to 0xC03F0 in {va:#x}")


if __name__ == "__main__":
    unittest.main()
