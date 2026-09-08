"""Standalone bounded roster/data/image tests. Retail evidence is optional."""
from collections import Counter
import copy
import csv
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT, ROOT / "tools", ROOT / "tests"):
    sys.path.insert(0, str(directory))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_roster_records as rr
import nfl2k5_espn25_rosters_from_nflverse as gen
from nfl2k5_xiso_fixture import SyntheticXiso

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(gen.DEFAULT_RETAIL)))
if not (RETAIL / "default.xbe").is_file() and (RETAIL / "ESPN NFL 2K5 (USA)").is_dir():
    RETAIL = RETAIL / "ESPN NFL 2K5 (USA)"


def sheet(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, e.CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def synthetic():
    """One small historic-shaped roster, no retail data or external fixture."""
    body = bytearray(12000)
    body[12:16] = b"ROST"
    struct.pack_into("<I", body, 16, 17)
    def ptr(at, target):
        struct.pack_into("<i", body, at, target - at + 1)
    ptr(20, 64)
    struct.pack_into("<I", body, 64, 53)
    ptr(68, 768)
    ptr(76, 768 + 53 * 84)
    struct.pack_into("<I", body, 88, 1)
    ptr(92, 256)
    cursor = 5300
    def string(text):
        nonlocal cursor
        at = cursor
        raw = text.encode("utf-16le") + b"\0\0"
        body[at:at + len(raw)] = raw
        cursor += len(raw)
        return at
    for off, value in ((rr.TEAM_NICKNAME, "Historic"), (rr.TEAM_ABBREVIATION, "TEST"), (rr.TEAM_CITY, "Test")):
        ptr(256 + off, string(value))
    body[256 + rr.TEAM_PLAYER_COUNT] = 53
    for i in range(53):
        at = 768 + i * 84
        ptr(256 + i * 4, at)
        ptr(at + 16, string("FirstHolder"))
        ptr(at + 20, string("LastHolder"))
        record = rr.PlayerRecord.decode(bytes(body[at:at + 84]))
        record.set("position", i % 17)
        record.set("jersey", (i + 8) % 100)
        for j, field in enumerate(rr.RATING_BYTE_ORDER):
            record.set(field, (i + j * 11) % 256)
        body[at:at + 84] = record.encode()
    raw = b"ROST" + struct.pack("<7I", len(body), len(body), 0, 0, 0, 0, 0) + body
    document = rr.RosterDocument(raw[32:])
    rows = [{"pool": "primary", "index": str(i), "first": "Name" + str(i), "last": "Player" + str(i),
             "position": p.record.position_name, "jersey": str(i + 1),
             "college": "Example College" if i == 0 else "", **{k: str(v) for k, v in p.record.ratings().items()}}
            for i, p in enumerate(document.players)]
    return bytes(raw), rows


class DatasetTests(unittest.TestCase):
    def test_complete_dataset_inventory_and_all_moment_bindings(self):
        manifest, sheets = e.dataset()
        inventory = json.loads((ROOT / "docs/mod_editor/nfl2k5_espn25_inventory.json").read_text())
        with (ROOT / "docs/mod_editor/nfl2k5_espn25_inventory.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual((len(manifest["resources"]), len(manifest["moments"]), len(rows)), (35, 25, 3975))
        self.assertEqual(len(inventory["files"]), 75)
        self.assertEqual(Counter(r["outer"] for r in rows), {str(i): 53 for i in range(113, 188)})
        self.assertTrue({r["classification"] for r in rows} <= {"placeholder", "real_name_in_supplied_data", "unresolved_name"})
        self.assertEqual(Counter(r["classification"] for r in rows),
                         sum((Counter(f["classification"]) for f in inventory["files"]), Counter()))
        self.assertEqual(set(sheets), {side["outer"] for m in manifest["moments"] for side in m["sides"].values()})
        self.assertEqual(set(e.CSV_COLUMNS) - set(rr.CSV_COLUMNS), set())
        self.assertEqual(manifest["source"]["licence"], "CC-BY-4.0")
        self.assertEqual(len(manifest["source"]["files"]), 45)
        self.assertFalse(e.DEFAULT_ENABLED)
        self.assertEqual(e.REQUESTS, ())
        self.assertTrue(all(not m["exact_game_lineup_established"] for m in manifest["moments"]))
        for target in manifest["resources"]:
            self.assertEqual(Counter(r["position"] for r in sheets[target["outer"]]), target["position_mix"])
            self.assertEqual(target["fillers"], sum(p["source_season"] != target["selected_season"] for p in target["players"]))
            for position in rr.POSITIONS:
                group = [p for row, p in zip(sheets[target["outer"]], target["players"]) if row["position"] == position]
                regulars = [p["retail_depth_rank"] for p in group if not p["adjacent_season_filler"]]
                fillers = [p["retail_depth_rank"] for p in group if p["adjacent_season_filler"]]
                if regulars and fillers:
                    self.assertLessEqual(max(regulars), min(fillers))
            if target["editorial_qb_preference"]:
                qb = next(p for row, p in zip(sheets[target["outer"]], target["players"])
                          if row["position"] == "QB" and p["retail_depth_rank"] == 0)
                self.assertEqual(qb["source_full_name"], target["editorial_qb_preference"])
                self.assertEqual(qb["source_season"], target["selected_season"])

    def test_every_name_number_and_college_has_exact_supplied_source_provenance(self):
        missing = [f"roster_{year}.csv" for year in range(1960, 2005)
                   if not (gen.DEFAULT_INPUT / f"roster_{year}.csv").is_file()]
        if missing:
            self.skipTest("user-supplied nflverse evidence absent: " + ", ".join(missing))
        source = gen.Source(gen.DEFAULT_INPUT)
        by_line = {(r["source_file"], r["source_line"]): r for r in source.rows}
        manifest, sheets = e.dataset()
        self.assertEqual(source.files, manifest["source"]["files"])
        for target in manifest["resources"]:
            seen = set()
            for p, row in zip(target["players"], sheets[target["outer"]]):
                r = by_line[p["source_file"], p["source_line"]]
                self.assertEqual(gen.display_parts(r), (row["first"], row["last"]))
                self.assertEqual(r["identity"], p["source_identity"])
                self.assertNotIn(r["identity"], seen)
                seen.add(r["identity"])
                self.assertEqual(r["franchise"], gen.SELECTORS[target["selector"]])
                self.assertEqual(r["season"], p["source_season"])
                fit, _ = gen.position_fit(r, row["position"])
                self.assertLess(fit, gen.INF)
                if row["college"]:
                    self.assertEqual(row["college"], r["college"])
                    self.assertEqual(manifest["colleges"].count(row["college"]), 1)
                basis = p["jersey_source"]
                if basis["basis"] != "retail_slot_unknown_historical_number":
                    donor = by_line[basis["file"], basis["line"]]
                    self.assertEqual((donor["identity"], donor["franchise"]), (r["identity"], r["franchise"]))
                    self.assertEqual(gen.number(donor["jersey_number"]), int(row["jersey"]))

    def test_short_lists_do_not_silently_become_claimed_53_player_season_rosters(self):
        manifest, _ = e.dataset()
        self.assertGreater(sum(t["fillers"] for t in manifest["resources"]), 0)
        self.assertGreater(sum(t["unknown_numbers"] for t in manifest["resources"]), 0)
        for target in manifest["resources"]:
            if target["season_source_players"] < 53:
                self.assertGreaterEqual(target["fillers"], 53 - target["season_source_players"])
        # These are shared-resource choices, not new historical claims.
        bills = next(t for t in manifest["resources"] if t["filename"] == "h-03-1990-bills-2.iff")
        self.assertEqual((bills["selected_season"], bills["chosen_moment"], bills["losing_moments"]), (1990, 14, [17, 19]))
        self.assertEqual(manifest["moments"][23]["season"], 2002)
        self.assertEqual(manifest["moments"][24]["season"], 2003)

    def test_dataset_revalidates_manifest_csv_corruption_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "data"
            shutil.copytree(e.DATA_DIR, folder)
            with patch.object(e, "DATA_DIR", folder):
                manifest, _ = e.dataset()
                path = folder / manifest["resources"][0]["csv"]
                raw = path.read_bytes()
                path.write_bytes(raw.replace(b"primary", b"foreign", 1))
                with self.assertRaisesRegex(e.Espn25RostersError, "digest mismatch"):
                    e.dataset()
                path.write_bytes(raw)
                e.dataset()
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    e.dataset()
                (folder / "manifest.json").write_text("{}")
                with self.assertRaisesRegex(e.Espn25RostersError, "manifest differs"):
                    e.dataset()
        e.dataset()

    def test_csv_rejects_duplicates_missing_rows_invalid_cells_and_extra_columns(self):
        rows = copy.deepcopy(next(iter(e.dataset()[1].values())))
        for mutate in (lambda r: r.pop(), lambda r: r.append(r[0]),
                       lambda r: r[1].update(first=r[0]["first"], last=r[0]["last"]),
                       lambda r: r[0].update(index="1"), lambda r: r[0].update(jersey="100"),
                       lambda r: r[0].update(jersey="1.0"), lambda r: r[0].update(position="LS"),
                       lambda r: r[0].update(first="X" * 16), lambda r: r[0].update(speed="256")):
            bad = copy.deepcopy(rows)
            mutate(bad)
            with self.assertRaises(ValueError):
                e.parse_csv(sheet(bad))
        with self.assertRaises(e.Espn25RostersError):
            e.parse_csv(sheet(rows).replace("pool,index", "pool,pool,index", 1))

    def test_assignment_reserves_scarce_roles_and_season_choice_ties(self):
        # A greedy first choice would strand the second slot.
        self.assertEqual(gen.assignment([[1, 2, 20], [1, gen.INF, gen.INF]]), [1, 0])
        with self.assertRaises(e.Espn25RostersError):
            gen.assignment([[gen.INF, gen.INF], [gen.INF, gen.INF]])
        a = dict(moment=5, season=1987, game_date="1987-09-20")
        b = dict(moment=13, season=1988, game_date="1989-01-22")
        self.assertEqual(gen.choose_season({"year": 1988}, [a, b]), b)
        self.assertEqual(gen.choose_season({"year": 1989}, [a, b]), b)
        self.assertEqual(gen.franchise("BAL", 1970), "IND")
        self.assertEqual(gen.franchise("STL", 1987), "ARZ")
        self.assertEqual(gen.franchise("LA", 1980), "STL")

    def test_capability_handoff_schema_and_new_file_references(self):
        from mod_editor.capabilities import validate_registry as registry
        cap = json.loads((ROOT / "docs/mod_editor/nfl2k5_espn25_rosters_capability.json").read_text())
        candidate = json.loads(registry.DEFAULT_REGISTRY.read_text())
        candidate["capabilities"] = sorted([c for c in candidate["capabilities"] if c["id"] != cap["id"]] + [cap], key=lambda c: c["id"])
        registry.validate_data(candidate, check_files=False)
        for path in cap["evidence"] + cap["runtime"]["evidence"] + [cap["backend"]["module"]]:
            registry._local_path(path, cap["id"])
        for command in (cap["backend"]["command"], cap["validation_command"]):
            registry._local_path(registry._command_module(command, cap["id"]), cap["id"])
        self.assertEqual(cap["runtime"]["status"], "not-tested")
        self.assertLessEqual(len(e.CAPTION), 60)
        for text in ("Retail", "Patch", "EXPERIMENTAL / UNWITNESSED"):
            self.assertIn(text, e.HELP_TEXT)


class SyntheticWriterTests(unittest.TestCase):
    def test_name_pool_reclamation_wrapper_ratings_appearance_and_college_index(self):
        raw, rows = synthetic()
        self.assertEqual(rr.RosterDocument(raw[32:]).to_body(), raw[32:])
        after = e.compile_resource(raw, rows, ["Other College", "Example College"])
        before_doc, doc = rr.RosterDocument(raw[32:]), rr.RosterDocument(after[32:])
        self.assertEqual((len(after), after[:32]), (len(raw), raw[:32]))
        self.assertEqual(doc.players[0].record.values["college_pointer"], 1)
        self.assertEqual([(p.first, p.last, p.record.values["jersey"]) for p in doc.players],
                         [(r["first"], r["last"], int(r["jersey"])) for r in rows])
        for a, b in zip(before_doc.players, doc.players):
            self.assertEqual(a.record.ratings(), b.record.ratings())
            self.assertEqual(a.record.skin, b.record.skin)
        self.assertEqual(doc.teams[0].slots, before_doc.teams[0].slots)

    def test_compressed_wrapper_wrong_size_and_overfull_name_pool_refuse(self):
        raw, rows = synthetic()
        for off, value in ((16, 0xFFFFFFFF), (4, len(raw))):
            bad = bytearray(raw)
            struct.pack_into("<I", bad, off, value)
            with self.assertRaises(e.Espn25RostersError):
                e.compile_resource(bytes(bad), rows, ["Example College"])
        bad = copy.deepcopy(rows)
        for i, row in enumerate(bad):
            row.update(first=("F" * 13 + f"{i:02d}"), last=("L" * 13 + f"{i:02d}"))
        snapshot = bytes(raw)
        with self.assertRaises(e.Espn25RostersError):
            e.compile_resource(raw, bad, ["Example College"])
        self.assertEqual(raw, snapshot)

    def test_csv_cannot_change_position_ratings_or_guess_college(self):
        raw, rows = synthetic()
        for field, value in (("position", "G"), ("speed", "99"), ("college", "Almost College")):
            bad = copy.deepcopy(rows)
            bad[0][field] = value
            with self.assertRaises(e.Espn25RostersError):
                e.compile_resource(raw, bad, ["Example College"])

    def test_full_transaction_refuses_partial_and_foreign_before_compilation(self):
        raw, rows = synthetic()
        applied = e.compile_resource(raw, rows, ["Example College"])
        targets = [{"outer": i, "filename": f"synthetic-{i}.iff", "size": len(raw),
                    "retail_sha256": e.sha(raw), "applied_sha256": e.sha(applied)} for i in range(35)]
        data = {"resources": targets, "colleges": ["Example College"]}, {i: rows for i in range(35)}
        resources = {i: raw for i in range(35)}
        with patch.object(e, "dataset", return_value=data):
            after, receipt = e.apply(resources)
            self.assertEqual(e.status(after), "applied")
            replay, again = e.apply(after)
            self.assertEqual(replay, after)
            self.assertEqual(again["changed_bytes"], 0)
            self.assertTrue(all(not t["changes"] for t in again["resources"]))
            for i in range(35):
                for bad in ({**resources, i: applied}, {**after, i: raw}, {**resources, i: raw[:-1]},
                            {**resources, i: b"X" + raw[1:]},
                            {k: v for k, v in resources.items() if k != i}):
                    with patch.object(e, "compile_resource", side_effect=AssertionError("must not compile")):
                        self.assertEqual(e.status(bad), "foreign")
                        with self.assertRaises(e.Espn25RostersError):
                            e.apply(bad)
            self.assertFalse(receipt["xbe_changed"])


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RETAIL / "vc_53450030/0").is_file():
            raise unittest.SkipTest("user-owned retail extraction absent: " + str(RETAIL))
        cls.manifest, cls.sheets = e.dataset()
        cls.resources = e.read_resources(RETAIL)
        if e.status(cls.resources) != "retail":
            raise unittest.SkipTest("private retail evidence is not the pinned USA resource set")
        cls.output, cls.receipt = e.apply(cls.resources)
        with rr._outer_image()(RETAIL) as archive:
            cls.context = {i: archive.read_entry(i) for i in (5, 22)}
            cls.descriptors = e.describe_context(cls.context[5], cls.context[22], archive.entries)["descriptors"]
            cls.all_rosters = {d["outer"]: archive.read_entry(d["outer"]) for d in cls.descriptors}

    def test_all_75_codec_roundtrips_and_all_35_csv_imports(self):
        for index, raw in self.all_rosters.items():
            with self.subTest(outer=index):
                doc = rr.RosterDocument(raw[32:])
                self.assertEqual(doc.to_body(), raw[32:])
                self.assertEqual(len(doc.players), 53)
                self.assertTrue(all(rr.encode_record(rr.decode_record(raw[32 + p.offset:32 + p.offset + 84])) ==
                                    raw[32 + p.offset:32 + p.offset + 84] for p in doc.players))
        for t in self.manifest["resources"]:
            raw, after = self.resources[t["outer"]], self.output[t["outer"]]
            self.assertEqual(after, e.compile_resource(raw, self.sheets[t["outer"]], self.manifest["colleges"]))
            self.assertEqual(raw[:32], after[:32])
            before_doc, doc = rr.RosterDocument(raw[32:]), rr.RosterDocument(after[32:])
            for a, b, row in zip(before_doc.players, doc.players, self.sheets[t["outer"]]):
                self.assertEqual((b.first, b.last, b.record.values["jersey"]), (row["first"], row["last"], int(row["jersey"])))
                self.assertEqual(a.record.ratings(), b.record.ratings())

    def test_receipts_reconstruct_every_changed_byte_and_replay_is_identity(self):
        for item in self.receipt["resources"]:
            index = item["outer"]
            forward, reverse = bytearray(self.resources[index]), bytearray(self.output[index])
            for change in item["changes"]:
                off, old, new = change["offset"], bytes.fromhex(change["before"]), bytes.fromhex(change["after"])
                self.assertEqual(forward[off:off + len(old)], old)
                self.assertEqual(reverse[off:off + len(new)], new)
                forward[off:off + len(new)], reverse[off:off + len(old)] = new, old
            self.assertEqual(forward, self.output[index])
            self.assertEqual(reverse, self.resources[index])
        after, again = e.apply(self.output)
        self.assertEqual(after, self.output)
        self.assertEqual(again["changed_bytes"], 0)

    def fixture(self, folder, *, split=False):
        by_outer = {d["outer"]: d for d in self.descriptors}
        entries = []
        for i in range(189):
            raw = self.context.get(i, self.all_rosters.get(i, bytes(32)))
            identity = by_outer[i]["id"] if i in by_outer else i
            entries.append((identity, raw))
        fixture = SyntheticXiso(folder, entries, pack_sizes=(2 * 1024 * 1024,), pack_sectors=(80,))
        if split:
            seam = fixture.entry_offsets[min(self.resources)] + 2048
            fixture = SyntheticXiso(folder, entries, pack_sizes=(seam, 2 * 1024 * 1024 - seam),
                                    pack_sectors=(80, 80 + seam // 2048 + 16))
        return fixture

    def test_moved_pack_image_writer_only_changes_the_35_owned_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory).resolve())
            before = fixture.path.read_bytes()  # synthetic image <3 MiB, never a disc
            receipt = e.apply_to_image(fixture.path)
            after = fixture.path.read_bytes()
            self.assertEqual(e.image_status(fixture.path), "applied")
            allowed = set()
            for item in receipt["image_spans"]:
                for span in item["segments"]:
                    allowed.update(range(span["image_offset"], span["image_offset"] + span["size"]))
            self.assertEqual(len(before), len(after))
            self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(before, after)) if a != b))
            self.assertEqual(before[35 * 2048:35 * 2048 + 16], after[35 * 2048:35 * 2048 + 16])
            again = e.apply_to_image(fixture.path)
            self.assertEqual(again["changed_bytes"], 0)
            self.assertEqual(fixture.path.read_bytes(), after)
            # All wrappers, main ROST, SITU and other 40 resources are preserved
            # by whole-image comparison above. Explicitly verify 40 unused spans.
            with rr._outer_image()(fixture.path) as archive:
                for i in set(self.all_rosters) - set(self.output):
                    self.assertEqual(archive.read_entry(i), self.all_rosters[i])
            published = fixture.path.with_name("closed-handles.iso")
            os.replace(fixture.path, published)
            self.assertTrue(published.is_file())

    def test_mixed_image_and_changed_context_refuse_without_one_write(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory).resolve())
            index = next(iter(self.resources))
            with rr._outer_image()(fixture.path, writable=True) as archive:
                archive.write(archive.entries[index].virtual_offset, self.output[index])
            before = fixture.path.read_bytes()
            with self.assertRaises(e.Espn25RostersError):
                e.apply_to_image(fixture.path)
            self.assertEqual(fixture.path.read_bytes(), before)
            with rr._outer_image()(fixture.path, writable=True) as archive:
                archive.write(archive.entries[index].virtual_offset, self.resources[index])
                body = bytearray(self.context[22])
                struct.pack_into("<I", body, 32 + e.RECORDS + 28, 1900)
                archive.write(archive.entries[22].virtual_offset, bytes(body))
            before = fixture.path.read_bytes()
            with self.assertRaises(e.Espn25RostersError):
                e.apply_to_image(fixture.path)
            self.assertEqual(fixture.path.read_bytes(), before)

    def test_copy_publication_failure_cleans_stage_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            fixture = self.fixture(folder)
            before = fixture.path.read_bytes()
            target = folder / "new.iso"
            free = SimpleNamespace(free=200 * 1024**3)
            with patch.object(e.shutil, "disk_usage", return_value=free), patch.object(e, "apply_to_image", side_effect=OSError("simulated write failure")):
                with self.assertRaises(OSError):
                    e.build_image(fixture.path, target)
            self.assertFalse(target.exists())
            self.assertEqual(fixture.path.read_bytes(), before)
            self.assertFalse(list(folder.glob("espn25-rosters-*")))
            with patch.object(e.shutil, "disk_usage", return_value=free):
                receipt = e.build_image(fixture.path, target)
            self.assertEqual(e.image_status(target), "applied")
            self.assertEqual(fixture.path.read_bytes(), before)
            self.assertFalse(receipt["xbe_changed"])
            with self.assertRaises(e.Espn25RostersError):
                e.build_image(fixture.path, target)

    def test_late_compile_failure_leaves_private_image_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory).resolve())
            before = fixture.path.read_bytes()
            compile_original, calls = e.compile_resource, []
            def fail_late(*args):
                calls.append(1)
                if len(calls) == 35:
                    raise e.Espn25RostersError("last resource cannot fit")
                return compile_original(*args)
            with patch.object(e, "compile_resource", side_effect=fail_late):
                with self.assertRaisesRegex(e.Espn25RostersError, "last resource"):
                    e.apply_to_image(fixture.path)
            self.assertEqual(len(calls), 35)
            self.assertEqual(fixture.path.read_bytes(), before)

    def test_split_resource_windows_io_fallback_and_closed_handles(self):
        from tests.mod_editor.test_modpack import windows_file_locks
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.fixture(Path(directory).resolve(), split=True)
            before = fixture.path.read_bytes()
            with windows_file_locks() as open_paths, patch.object(os, "pread", None, create=True), \
                    patch.object(os, "pwrite", None, create=True):
                receipt = e.apply_to_image(fixture.path)
                self.assertEqual(open_paths(), [])
                self.assertTrue(any(len(s["segments"]) == 2 for s in receipt["image_spans"]))
                self.assertEqual(e.image_status(fixture.path), "applied")
                self.assertEqual(e.apply_to_image(fixture.path)["changed_bytes"], 0)
                self.assertEqual(open_paths(), [])
                after = fixture.path.read_bytes()
                reconstructed = bytearray(before)
                with rr._outer_image()(fixture.path) as archive:
                    for outer, raw in self.output.items():
                        cursor = 0
                        for pack, offset, length in archive._segments(archive.entries[outer].virtual_offset, len(raw)):
                            start = pack.image_offset + offset
                            reconstructed[start:start + length] = raw[cursor:cursor + length]
                            cursor += length
                self.assertEqual(after, reconstructed)
                os.replace(fixture.path, fixture.path.with_name("closed.iso"))
                self.assertEqual(open_paths(), [])

    def test_current_team_names_and_current_player_edits_compose_in_both_orders(self):
        from mod_editor.core import nfl2k5_team_names_2026 as names
        changed_main, _ = names.apply(self.context[5])
        doc = rr.RosterDocument(changed_main[32:])
        player = doc.players[0]
        player.record.set("speed", (player.record.values["speed"] + 1) % 100)
        changed_main = changed_main[:32] + doc.to_body()
        for historic_first in (False, True):
            with self.subTest(historic_first=historic_first), tempfile.TemporaryDirectory() as directory:
                fixture = self.fixture(Path(directory).resolve())
                if historic_first:
                    e.apply_to_image(fixture.path)
                with rr._outer_image()(fixture.path, writable=True) as archive:
                    archive.write(archive.entries[5].virtual_offset, changed_main)
                self.assertEqual(e.image_status(fixture.path), "applied" if historic_first else "retail")
                e.apply_to_image(fixture.path)
                with rr._outer_image()(fixture.path) as archive:
                    self.assertEqual(archive.read_entry(5), changed_main)
                    self.assertEqual({i: archive.read_entry(i) for i in self.output}, self.output)

    def test_receipt_and_copy_publication_failures_leave_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            fixture = self.fixture(folder)
            before = fixture.path.read_bytes()
            target, receipt_path = folder / "new.iso", folder / "receipt.json"
            free = SimpleNamespace(free=200 * 1024**3)
            with patch.object(e.shutil, "disk_usage", return_value=free):
                with patch.object(e.shutil, "copyfileobj", side_effect=AssertionError("must not copy")):
                    with self.assertRaises(FileNotFoundError):
                        e.build_image(fixture.path, target, receipt_path=folder / "missing" / "receipt.json")
                    with self.assertRaises(e.Espn25RostersError):
                        e.build_image(fixture.path, target, receipt_path=fixture.path)
                with patch.object(e.json, "dump", side_effect=OSError("receipt write failed")):
                    with self.assertRaisesRegex(OSError, "receipt write failed"):
                        e.build_image(fixture.path, target, receipt_path=receipt_path)
                real_replace = os.replace
                def fail_image(source, destination):
                    if Path(destination) == target:
                        raise OSError("image publication failed")
                    return real_replace(source, destination)
                with patch.object(e.os, "replace", side_effect=fail_image):
                    with self.assertRaisesRegex(OSError, "image publication failed"):
                        e.build_image(fixture.path, target, receipt_path=receipt_path)
                self.assertFalse(target.exists())
                self.assertFalse(receipt_path.exists())
                self.assertEqual(fixture.path.read_bytes(), before)
                self.assertFalse(list(folder.glob("espn25-*")))
                receipt = e.build_image(fixture.path, target, receipt_path=receipt_path)
            self.assertEqual(json.loads(receipt_path.read_text()), receipt)
            self.assertEqual(e.image_status(target), "applied")
            self.assertEqual(fixture.path.read_bytes(), before)

    def test_disk_floor_and_foreign_source_refuse_before_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory).resolve()
            fixture = self.fixture(folder)
            target = folder / "new.iso"
            with patch.object(e.shutil, "copyfileobj", side_effect=AssertionError("must not copy")):
                with patch.object(e.shutil, "disk_usage", return_value=SimpleNamespace(free=100 * 1024**3)):
                    with self.assertRaisesRegex(e.Espn25RostersError, "100 GiB"):
                        e.build_image(fixture.path, target)
                with rr._outer_image()(fixture.path, writable=True) as archive:
                    outer = min(self.output)
                    archive.write(archive.entries[outer].virtual_offset, self.output[outer])
                with self.assertRaisesRegex(e.Espn25RostersError, "mixed or foreign"):
                    e.build_image(fixture.path, target)
            self.assertFalse(target.exists())
            self.assertFalse(list(folder.glob("espn25-*")))


if __name__ == "__main__":
    unittest.main()
