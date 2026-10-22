"""b778 fr1: no player record leaves the Studio without a college.

SOFTDRINK v0.6.1 shipped 50 main-roster players whose college word was null
(17 dated free agents with a blank source college, 33 refresh signings whose
source school is not in the 2004 table, such as "Illinois; Globe Institute").
Retail has none. The Franchise Player Contracts / Free Agents info panel reads
[[player+0]] with no null check (0x6E11D), so the game stopped on the first
such highlighted player (reproduced headless on the released disc: Giants,
Contracts, row 4, Jihad Ward; access violation at 0x6E11F).

These tests use synthetic records only, so they run on every platform.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import copy
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/mod_editor"), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_college_check as cc  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_roster_refresh as refresh  # noqa: E402
import test_nfl2k5_roster_records as fixture  # noqa: E402
import test_roster_refresh as refresh_fixture  # noqa: E402

PLAYER = rr.PLAYER_SIZE


def _null_college(body, indices):
    raw = bytearray(body)
    for index in indices:
        struct.pack_into("<I", raw, fixture.PLAYERS_OFF + index * PLAYER, 0)
    return bytes(raw)


class _Archive:
    """The two calls rr.apply makes on an outer image: entries[5], read and write."""

    def __init__(self, resource):
        self.data = bytearray(b"\0" * 0x800 + resource)
        entry = SimpleNamespace(index=rr.ROST_OUTER_INDEX, virtual_offset=0x800, size=len(resource))
        self.entries = [SimpleNamespace(index=i, virtual_offset=0, size=0) for i in range(rr.ROST_OUTER_INDEX)]
        self.entries.append(entry)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, offset, size):
        return bytes(self.data[offset:offset + size])

    def write(self, offset, data):
        self.data[offset:offset + len(data)] = data
        return len(data)


class CollegeNeverNullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body, cls.plan = refresh_fixture.sample()

    def test_resolver_exact_then_each_school_then_none(self):
        names = ["Clemson", "Illinois", "Utah", "None", ""]
        self.assertEqual(cc.resolve_index(names, "Utah"), 2)
        self.assertEqual(cc.resolve_index(names, " Utah "), 2)
        self.assertEqual(cc.resolve_index(names, "Illinois; Globe Institute"), 1)
        self.assertEqual(cc.resolve_index(names, "Grossmont; Utah"), 2)
        for missing in ("", None, "Valdosta State", "East Central; Western State", ";", 7):
            self.assertEqual(cc.resolve_index(names, missing), 3, missing)
        self.assertEqual(cc.resolve_index(["Clemson", "", "Duke"], "Nowhere"), 1)
        self.assertEqual(cc.resolve_index(["Clemson", "Duke"], "Nowhere"), 0)
        self.assertEqual(cc.resolve_index(["Clemson", "NONE"], ""), 1)
        with self.assertRaises(cc.CollegeCheckError):
            cc.resolve_index([], "Duke")

    def _new_player_plan(self, college):
        raw = bytearray(self.body)
        offset = fixture.PLAYERS_OFF + 2464 * PLAYER
        for field, target in ((0x10, 0x68000), (0x14, 0x68022)):
            raw[target:target + 34] = "****************".encode("utf-16le") + b"\0\0"
            struct.pack_into("<i", raw, offset + field, target - offset - field + 1)
        raw[offset + 8] = 1
        struct.pack_into("<I", raw, offset, 0)       # the vacancy itself carries no college
        plan = copy.deepcopy(self.plan)
        plan["identity_guards"] = [g for g in plan["identity_guards"] if g[0] != 2464]
        row = plan["players"][2464]
        row.update(first="New", last="Arrival", birth_date="2000-01-01", new=True, college=college)
        row["fields"] = {k: 50 for k in rr.RATING_BYTE_ORDER}
        row["fields"].update(position=3, jersey=18, height=72, weight=200, birth_year=2000, birth_month=1,
                             birth_day=1, years_pro=1, photo_id=7100, contract_length=1, contract_remaining=1,
                             contract_value=23, depth_rank=7, depth_side=7)
        plan["teams"][0]["active"].append(2464)
        return bytes(raw), plan

    def test_refresh_signing_always_points_at_a_college(self):
        colleges = list(fixture.COLLEGES)
        for source, expected in (("Marshall", "Marshall"), ("Nowhere Tech; Michigan", "Michigan"),
                                 ("Valdosta State", colleges[0]), ("", colleges[0])):
            with self.subTest(source=source):
                body, plan = self._new_player_plan(source)
                out, receipt = refresh.apply_body(body, plan)
                self.assertEqual(receipt["added"], 1)
                player = rr.RosterDocument(out, reference_year=2026).by_pool("primary")[2464]
                self.assertNotEqual(player.record.get("college_pointer"), 0)
                self.assertEqual(player.college, expected)
                self.assertEqual([f for f in cc.scan(out).findings], [])
                self.assertEqual(refresh.apply_body(out, plan)[0], out)

    def test_heal_changes_only_the_null_words_and_repeats_as_a_no_op(self):
        broken = _null_college(self.body, (3, 900, 2600))
        self.assertEqual(sorted(f.index for f in cc.scan(broken).findings), [3, 900, 2600])
        healed, receipt = cc.heal_null_references(broken, source="synthetic")
        self.assertEqual(receipt["changed"], 3)
        self.assertEqual(receipt["college"], fixture.COLLEGES[0])
        self.assertEqual(cc.scan(healed).findings, ())
        changed = [i for i in range(len(broken)) if broken[i] != healed[i]]
        words = {fixture.PLAYERS_OFF + i * PLAYER for i in (3, 900, 2600)}
        self.assertTrue(changed and all(any(w <= c < w + 4 for w in words) for c in changed))
        self.assertEqual(cc.heal_null_references(healed)[0], healed)
        self.assertEqual(cc.heal_null_references(self.body), (self.body, {
            "source": "", "changed": 0, "college": None, "players": [], "other_findings": 0}))
        rr.RosterDocument(healed)          # the strict codec still reads it

    def test_main_roster_writer_never_writes_a_null_college(self):
        broken = _null_college(self.body, (10, 2470))
        resource = b"ROST" + b"\0" * (rr.RESOURCE_HEADER_SIZE - 4) + broken
        self.assertEqual(rr.resource_status(resource), "edited")
        archive = _Archive(resource)
        with patch.object(rr, "_outer_image", return_value=lambda *a, **k: archive):
            result = rr.apply("image.iso", {"schema": rr.EDITS_SCHEMA, "edits": []}, refresh_follows=True)
        self.assertEqual(result["college_null_repair"]["changed"], 2)
        written = archive.read(0x800 + rr.RESOURCE_HEADER_SIZE, len(broken))
        self.assertEqual(cc.scan(written).findings, ())
        self.assertEqual(rr.RosterDocument(written).by_pool("primary")[2470].college, fixture.COLLEGES[0])
        with patch.object(rr, "_outer_image", return_value=lambda *a, **k: archive):
            again = rr.apply("image.iso", {"schema": rr.EDITS_SCHEMA, "edits": []}, refresh_follows=True)
        self.assertTrue(again.get("already_applied"))
        self.assertEqual(again["college_null_repair"]["changed"], 0)


if __name__ == "__main__":
    unittest.main()
