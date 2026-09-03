"""Tests for the one-pool defensive positions (EDGE / DT / LB) executable patch."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_edge_rename as edge  # noqa: E402
from mod_editor.core import nfl2k5_modern_positions as modern  # noqa: E402
from mod_editor.core import nfl2k5_position_pools as pools  # noqa: E402
from nfl2k5_modern_positions_test import build_synthetic_xbe as build_modern_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
IMAGE_BASE = pools.IMAGE_BASE
FRANCHISE_SECTION = (15, 0x00521000, 0x1000)     # .rdata window for the roster target/maxima tables
RATINGS_SECTION = (16, 0x004F1000, 0x1000)       # .rdata window for the team-rating tables + the consistency list
FILTERS_SECTION = (17, 0x00539000, 0x50000)      # .rdata window for the position-filter record arrays
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None

RETAIL_ABBREV_PTRS = (0xE69BE8, 0xE69BF0, 0xE69BF4, 0xE69BF8, 0xE69C00, 0xE69C08, 0xE69C10, 0xE69C18, 0xE69C20,
                      0xE69C28, 0xE69C54, 0xE69C5C, 0xE69C38, 0xE69C3C, 0xE69C40, 0xE69C44, 0xE69C4C)
RETAIL_ABBREVS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
RETAIL_LIST_PAIRS = ((0, 0), (23, 23), (24, 24), (25, 25), (26, 27), (6, 7), (10, 10), (8, 9), (3, 3), (4, 5), (1, 1),
                     (2, 2), (11, 12), (13, 14), (17, 18), (15, 16), (19, 19), (20, 20), (21, 22))
RETAIL_PACKAGES = (0xC000A82A, 0xC000AC2E, 0xC0000000, 0xC000A426, 0xC00124A6, 0xC000A022, 0xC000C84A,
                   0xC0004442, 0xC000BC3E, 0xC000B032, 0xC000B436, 0xC000B83A, 0x4)


def _u16(text: str, slot: int) -> bytes:
    raw = text.encode("utf-16le") + b"\0\0"
    return raw + b"\0" * (slot - len(raw))


def _repin(buf: bytearray) -> None:
    table = struct.unpack_from("<I", buf, 0x120)[0] - IMAGE_BASE
    for section in strength._sections(bytes(buf)):
        if section.raw_size:
            header = table + section.index * strength.SECTION_HEADER_SIZE
            buf[header + 36: header + 56] = hashlib.sha1(  # nosec B324
                struct.pack("<I", section.raw_size) + buf[section.raw_offset: section.raw_offset + section.raw_size]).digest()


def build_synthetic_xbe() -> bytes:
    """The modern-positions fixture (EDGE + throw fixtures underneath) plus the bridge tables, the
    franchise target/maxima window, the strings and the three code sites, all seeded retail."""

    buf = bytearray(build_modern_synthetic_xbe())
    table = struct.unpack_from("<I", buf, 0x120)[0] - IMAGE_BASE
    for index, va, size in (FRANCHISE_SECTION, RATINGS_SECTION, FILTERS_SECTION):
        raw = (len(buf) + 0xFFF) & ~0xFFF
        buf.extend(b"\0" * (raw + size - len(buf)))
        fields = [0] * 9 + [b"\0" * 20]
        fields[1], fields[3], fields[4] = va, raw, size
        struct.pack_into(strength.SECTION_TABLE_FIELDS, buf, table + index * strength.SECTION_HEADER_SIZE, *fields)
    payload = bytes(buf)

    def off(target_va: int) -> int:
        return pools._offset(payload, target_va)

    struct.pack_into("<17I", buf, off(pools.ENUM_TO_KIND_VA), *pools.RETAIL_ENUM_TO_KIND)
    buf[off(pools.KIND_TO_ENUM_VA): off(pools.KIND_TO_ENUM_VA) + 19] = pools.RETAIL_KIND_TO_ENUM
    for kind, pair in enumerate(RETAIL_LIST_PAIRS):
        struct.pack_into("<II", buf, off(pools.KIND_LIST_PAIRS_VA + 8 * kind), *pair)
    struct.pack_into("<17I", buf, off(pools.ROSTER_TARGETS_VA), *pools.RETAIL_TARGETS)
    struct.pack_into("<17I", buf, off(pools.ROSTER_MAXIMA_VA), *pools.RETAIL_MAXIMA)
    struct.pack_into("<17I", buf, off(pools.ABBREV_TABLE_VA), *RETAIL_ABBREV_PTRS)
    struct.pack_into("<13I", buf, off(pools.PACKAGES_VA), *RETAIL_PACKAGES)
    for ptr, text in zip(RETAIL_ABBREV_PTRS, RETAIL_ABBREVS):
        raw16 = _u16(text, (len(text) * 2 + 2 + 3) & ~3)
        buf[off(ptr): off(ptr) + len(raw16)] = raw16
    buf[off(pools.STRING_LB_VA): off(pools.STRING_LB_VA) + 8] = _u16("LB", 8)
    for _label, string_va, slot, old, _new in pools.STRING_SITES:
        buf[off(string_va): off(string_va) + slot] = _u16(old, slot)
    buf[off(pools.PENALTY_JNE_VA): off(pools.PENALTY_JNE_VA) + 2] = pools.RETAIL_PENALTY_BYTES
    buf[off(pools.ROW_LOOKUP_SITE_VA): off(pools.ROW_LOOKUP_SITE_VA) + 13] = pools.RETAIL_ROW_LOOKUP_PROLOGUE
    buf[off(pools.CAVE_VA): off(pools.CAVE_VA) + 32] = pools.RETAIL_CAVE_HELPER
    # team-rating tables, the chain-rule index bytes, the sim's consistency list, the tab-init code
    for name, (va, count, retail_hex) in pools.RATING_TABLES.items():
        buf[off(va): off(va) + count * pools.RATING_ENTRY] = bytes.fromhex(retail_hex)
    buf[off(pools.CHAIN_INDEX_VA): off(pools.CHAIN_INDEX_VA) + 16] = pools.RETAIL_CHAIN_INDEX
    buf[off(pools.CONSISTENCY_DEF_VA): off(pools.CONSISTENCY_DEF_VA) + 88] = pools.RETAIL_CONSISTENCY_DEF
    buf[off(pools.TAB_INIT_VA): off(pools.TAB_INIT_VA) + len(pools.RETAIL_TAB_INIT)] = pools.RETAIL_TAB_INIT
    # position-filter records (string pointer at +0, roster enum at +0x18) and their strings
    for records, strings, enum, text in ((pools.FILTER_ILB_RECORDS, pools.FILTER_ILB_STRINGS, pools.ENUM_ILB, "Inside Linebackers"),
                                         (pools.FILTER_OLB_RECORDS, pools.FILTER_OLB_STRINGS, pools.ENUM_OLB, "Outside Linebackers")):
        for i, record in enumerate(records):
            string_va = strings[min(i, len(strings) - 1)]
            struct.pack_into("<I", buf, off(record), string_va)
            struct.pack_into("<I", buf, off(record) + pools.FILTER_ENUM_OFFSET, enum)
        for string_va in strings:
            buf[off(string_va): off(string_va) + pools.FILTER_STRING_SLOT] = _u16(text, pools.FILTER_STRING_SLOT)
    _repin(buf)
    return bytes(buf)


def _prepared() -> bytes:
    """Retail fixture with the EDGE rename and the Phase-1 labels applied (the required order)."""

    edged, _ = edge.apply(build_synthetic_xbe())
    labelled, _ = modern.apply(edged)
    return labelled


def _record_pools(payload: bytes, unit: int) -> list[tuple[int, int]]:
    return [(r["position"], r["chain"]) for r in (modern.read_record(payload, unit, s) for s in range(modern.SLOTS_PER_UNIT))]


class LayoutInvariantTests(unittest.TestCase):
    def test_cave_is_29_bytes_inside_the_dead_helper(self) -> None:
        cave = pools.cave_bytes()
        self.assertEqual(len(cave), pools.CAVE_SIZE)
        self.assertEqual(len(pools.RETAIL_CAVE_HELPER), 32)
        self.assertEqual(pools.RETAIL_CAVE_HELPER[21:], b"\x90" * 11)
        self.assertTrue(cave.startswith(pools.RETAIL_ROW_LOOKUP_PROLOGUE))
        # tail: jmp back to the instruction after the retail prologue
        rel = struct.unpack_from("<i", cave, len(cave) - 4)[0]
        self.assertEqual(pools.CAVE_VA + len(cave) + rel, pools.ROW_LOOKUP_RESUME_VA)
        self.assertEqual(pools.ROW_LOOKUP_SITE_VA + len(pools.RETAIL_ROW_LOOKUP_PROLOGUE), pools.ROW_LOOKUP_RESUME_VA)

    def test_hook_jumps_to_the_cave_and_pads_with_nops(self) -> None:
        hook = pools.row_lookup_hook_bytes()
        self.assertEqual(len(hook), 13)
        self.assertEqual(hook[0], 0xE9)
        rel = struct.unpack_from("<i", hook, 1)[0]
        self.assertEqual(pools.ROW_LOOKUP_SITE_VA + 5 + rel, pools.CAVE_VA)
        self.assertEqual(hook[5:], b"\x90" * 8)

    def test_package_word_reproduces_retail_and_new_swap(self) -> None:
        self.assertEqual(pools.package_word(0x0F, 0x2F), pools.RETAIL_PACKAGE_SWAP_OLB)
        self.assertEqual(pools.package_word(0x2E, 0x4E), pools.NEW_PACKAGE_SWAP_OLB)
        # LB1 / LB2 = ILB kind 14 with variants 1 and 2
        self.assertEqual(0x2E, pools.KIND_ILB | (1 << 5))
        self.assertEqual(0x4E, pools.KIND_ILB | (2 << 5))

    def test_targets_and_maxima_only_touch_the_four_front_enums(self) -> None:
        for retail, new in ((pools.RETAIL_TARGETS, pools.new_targets()), (pools.RETAIL_MAXIMA, pools.new_maxima())):
            for enum, (a, b) in enumerate(zip(retail, new)):
                if enum in (pools.ENUM_OLB, pools.ENUM_ILB, pools.ENUM_DT, pools.ENUM_DE):
                    continue
                self.assertEqual(a, b, pools.POSITIONS[enum])
        self.assertEqual(pools.new_targets()[pools.ENUM_OLB], 0)
        self.assertEqual(pools.new_maxima()[pools.ENUM_OLB], 0)

    def test_every_string_replacement_fits_its_slot(self) -> None:
        for label, _va, slot, old, new in pools.STRING_SITES:
            self.assertLessEqual(len(new.encode("utf-16le")) + 2, slot, label)
            self.assertLessEqual(len(old.encode("utf-16le")) + 2, slot, label)
            self.assertEqual(slot % 4, 0, label)

    def test_pool_records_match_the_phase_one_profile(self) -> None:
        for label, _unit, _slot, old, new in pools.POOL_RECORDS:
            self.assertEqual(modern.EXPECTED_POOLS[label], old, label)
            self.assertEqual(modern.ONE_POOL_POOLS[label], new, label)


class RatingAndRowCountLayoutTests(unittest.TestCase):
    """The 9/3-night additions: team-rating tables, chain rule, consistency list, tab-init rewrite, filters."""

    def test_rating_tables_only_move_the_olb_and_ilb_entries(self) -> None:
        for name, (va, count, retail_hex) in pools.RATING_TABLES.items():
            _va, before, after = pools.rating_table_edit(name)
            self.assertEqual(len(before), count * pools.RATING_ENTRY, name)
            self.assertEqual(_va, va)
            touched = 0
            for i in range(count):
                b, a = before[i * 20:(i + 1) * 20], after[i * 20:(i + 1) * 20]
                pos = struct.unpack_from("<b", b, 3)[0]
                if pos in (pools.ENUM_OLB, pools.ENUM_ILB):
                    self.assertEqual(a[3], pools.ENUM_ILB, (name, i))
                    self.assertEqual(a[2], pools.LB_STARTERS, (name, i))
                    self.assertEqual(a[:2] + a[4:], b[:2] + b[4:], (name, i))    # weight, getter, bench, lo, hi kept
                    touched += 1
                else:
                    self.assertEqual(a, b, (name, i))
            self.assertGreater(touched, 0, name)
        # the OLB weight of defense A / B is what the one-pool disc averaged as zero
        rows_a = pools.rating_table_rows(_prepared_with_ratings(), "defense_a")
        self.assertEqual(sum(r["weight"] for r in rows_a if r["position"] == "ILB"), 45)     # 25 (ex-OLB) + 20 (ILB)
        self.assertTrue(all(r["starters"] == 2 for r in rows_a if r["position"] == "ILB"))
        self.assertTrue(all(r["starters"] == 1 for r in rows_a if r["position"] != "ILB"))

    def test_chain_rule_makes_lb_and_dt_two_sided_only(self) -> None:
        new = pools.chain_index_bytes()
        self.assertEqual(len(new), 16)
        diff = [i for i in range(16) if new[i] != pools.RETAIL_CHAIN_INDEX[i]]
        self.assertEqual(diff, [pools.ENUM_ILB, pools.ENUM_DT])
        self.assertEqual(new[pools.ENUM_ILB], pools.CHAIN_TWO_SIDED)
        self.assertEqual(new[pools.ENUM_DT], pools.CHAIN_TWO_SIDED)
        self.assertEqual(pools.RETAIL_CHAIN_INDEX[pools.ENUM_ILB], 1)     # retail: single-sided unless team+0x150 != 0
        self.assertEqual(pools.RETAIL_CHAIN_INDEX[pools.ENUM_DT], 2)      # retail: single-sided when team+0x150 == 1

    def test_consistency_list_reads_lb_one_two_three(self) -> None:
        rows = list(struct.iter_unpack("<II", pools.NEW_CONSISTENCY_DEF))
        retail = list(struct.iter_unpack("<II", pools.RETAIL_CONSISTENCY_DEF))
        self.assertEqual(rows[:8], retail[:8])
        self.assertEqual(retail[8:], [(10, 0), (10, 1), (11, 1)])
        self.assertEqual(rows[8:], [(11, 0), (11, 1), (11, 2)])

    def test_tab_init_rewrite_fits_and_falls_into_the_retail_tail(self) -> None:
        code = pools.tab_init_bytes()
        size = pools.TAB_INIT_END_VA - pools.TAB_INIT_VA
        self.assertEqual(len(code), size)
        self.assertEqual(len(pools.RETAIL_TAB_INIT), size)
        live = code.rstrip(b"\xcc")
        self.assertEqual(live[-5], 0xE9)
        rel = struct.unpack_from("<i", live, len(live) - 4)[0]
        self.assertEqual(pools.TAB_INIT_VA + len(live) + rel, pools.TAB_INIT_END_VA)
        # both count calls target FUN_000c3cb0
        calls = [i for i in range(len(live) - 4) if live[i] == 0xE8 and pools.TAB_INIT_VA + i + 5 + struct.unpack_from("<i", live, i + 1)[0] == pools.FN_COUNT_AT_POSITION]
        self.assertEqual(len(calls), 2)
        self.assertTrue(live.startswith(pools.RETAIL_TAB_INIT[:13]))          # same unit * 11 + slot prologue

    def test_filter_sites_are_distinct_and_match_the_string_copies(self) -> None:
        self.assertEqual(len(pools.FILTER_ILB_RECORDS), 15)
        self.assertEqual(len(pools.FILTER_OLB_RECORDS), 14)
        self.assertEqual(len(set(pools.FILTER_ILB_RECORDS + pools.FILTER_OLB_RECORDS)), 29)
        self.assertEqual(len(set(pools.FILTER_ILB_STRINGS + pools.FILTER_OLB_STRINGS)), 25)
        self.assertLessEqual(len("Linebackers".encode("utf-16le")) + 2, pools.FILTER_STRING_SLOT)
        labels = [site.label for site in pools._sites(True, True)]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn("tab_init_rows", labels)
        self.assertNotIn("tab_init_rows", [site.label for site in pools._sites(True, False)])


def _prepared_with_ratings() -> bytes:
    patched, _ = pools.apply(_prepared())
    return patched


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retail = build_synthetic_xbe()
        self.prepared = _prepared()

    def test_requires_the_phase_one_labels(self) -> None:
        self.assertEqual(pools.status(self.retail), "retail")
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(self.retail)

    def test_status_and_apply_round_trip(self) -> None:
        self.assertEqual(pools.status(self.prepared), "retail")
        patched, receipt = pools.apply(self.prepared)
        self.assertEqual(pools.status(patched), "applied")
        self.assertEqual(pools.status(self.prepared), "retail")
        self.assertEqual(modern.status(patched), "applied")
        self.assertEqual(modern.status(patched, three_four_line=True), "applied")
        self.assertEqual(modern.pool_profile(patched), "one_pool")
        self.assertEqual(edge.status(patched), "applied")
        tables = receipt["tables"]
        self.assertEqual(tables["enum_to_kind"][pools.ENUM_OLB], pools.KIND_ILB)
        self.assertEqual(tables["kind_to_enum"][pools.KIND_OLB], pools.ENUM_ILB)
        self.assertEqual(tables["kind_list_pairs"][pools.KIND_OLB], pools.LB_LIST_PAIR)
        self.assertEqual(tables["roster_targets"]["OLB"], 0)
        self.assertEqual(tables["roster_targets"]["ILB"], 5)
        self.assertEqual(tables["roster_maxima"]["DE"], 6)
        self.assertEqual(tables["abbreviations"][pools.ENUM_OLB], "LB")
        self.assertEqual(tables["abbreviations"][pools.ENUM_ILB], "LB")
        self.assertEqual(tables["abbreviations"][pools.ENUM_DE], "EDGE")
        self.assertEqual(tables["package_swap_olb"], {"code": 0x2E, "alt": 0x4E})
        self.assertEqual(_record_pools(patched, modern.UNIT_43),
                         [(16, 0), (15, 0), (15, 1), (16, 1), (11, 3), (11, 0), (11, 1), (4, 1), (4, 0), (6, 0), (5, 0)])
        self.assertEqual(_record_pools(patched, modern.UNIT_34),
                         [(15, 1), (15, 0), (15, 3), (11, 1), (11, 0), (16, 1), (16, 0), (4, 1), (4, 0), (6, 0), (5, 0)])
        labels = [(r["abbreviation"], r["long_name"]) for r in (modern.read_record(patched, modern.UNIT_34, s) for s in range(7))]
        self.assertEqual(labels, [("DE", "LEFT DEFENSIVE END"), ("NT", "NOSE TACKLE"), ("DE", "RIGHT DEFENSIVE END"),
                                  ("WILL", "WEAKSIDE LINEBACKER"), ("MIKE", "MIDDLE LINEBACKER"),
                                  ("EDGE", "RIGHT EDGE RUSHER"), ("EDGE", "LEFT EDGE RUSHER")])

    def test_only_the_sites_and_digests_change(self) -> None:
        patched, receipt = pools.apply(self.prepared)
        allowed: set[int] = set()
        touched_sections: set[int] = set()
        sections = strength._sections(self.prepared)
        for site in pools._sites(True, True):
            off = pools._offset(self.prepared, site.va)
            allowed.update(range(off, off + site.size))
            touched_sections.add(strength._section_for_offset(sections, off).index)
        table = struct.unpack_from("<I", self.prepared, 0x120)[0] - IMAGE_BASE
        for index in touched_sections:
            header = table + index * strength.SECTION_HEADER_SIZE
            allowed.update(range(header + 36, header + 56))
        diff = {i for i, (a, b) in enumerate(zip(self.prepared, patched)) if a != b}
        self.assertTrue(diff <= allowed, sorted(diff - allowed)[:10])
        self.assertEqual(receipt["changed_bytes"], len(diff))
        self.assertEqual(set(receipt["sections_repinned"]), touched_sections)
        for section in strength._sections(patched):
            if section.raw_size:
                self.assertEqual(section.stored_digest, strength.section_digest(patched, section), section.index)

    def test_strings_shrink_in_place(self) -> None:
        patched, _ = pools.apply(self.prepared)
        for label, va, slot, _old, new in pools.STRING_SITES:
            off = pools._offset(patched, va)
            self.assertEqual(patched[off: off + slot], _u16(new, slot), label)
        self.assertNotIn("Inside Linebacker".encode("utf-16le"), patched)
        self.assertNotIn("Outside Linebacker".encode("utf-16le"), patched)

    def test_code_sites(self) -> None:
        patched, _ = pools.apply(self.prepared)
        off = pools._offset(patched, pools.PENALTY_JNE_VA)
        self.assertEqual(patched[off: off + 2], b"\x74\x59")
        off = pools._offset(patched, pools.ROW_LOOKUP_SITE_VA)
        self.assertEqual(patched[off: off + 13], pools.row_lookup_hook_bytes())
        off = pools._offset(patched, pools.CAVE_VA)
        self.assertEqual(patched[off: off + 29], pools.cave_bytes())
        self.assertEqual(patched[off + 29: off + 32], b"\x90" * 3)     # the helper's spare nops stay
        off = pools._offset(patched, pools.TAB_INIT_VA)
        self.assertEqual(patched[off: off + len(pools.RETAIL_TAB_INIT)], pools.tab_init_bytes())
        off = pools._offset(patched, pools.CHAIN_INDEX_VA)
        self.assertEqual(patched[off: off + 16], pools.chain_index_bytes())

    def test_rating_filters_and_consistency_sites(self) -> None:
        patched, receipt = pools.apply(self.prepared)
        for name, (va, count, _hex) in pools.RATING_TABLES.items():
            off = pools._offset(patched, va)
            self.assertEqual(patched[off: off + count * 20], pools.rating_table_edit(name)[2], name)
            self.assertFalse(any(r["position"] == "OLB" for r in receipt["rating_tables"][name]), name)
        off = pools._offset(patched, pools.CONSISTENCY_DEF_VA)
        self.assertEqual(patched[off: off + 88], pools.NEW_CONSISTENCY_DEF)
        for record in pools.FILTER_OLB_RECORDS:
            self.assertEqual(struct.unpack_from("<I", patched, pools._offset(patched, record) + 0x18)[0], pools.ENUM_ILB)
        for record in pools.FILTER_ILB_RECORDS:
            self.assertEqual(struct.unpack_from("<I", patched, pools._offset(patched, record) + 0x18)[0], pools.ENUM_ILB)
        for va in pools.FILTER_ILB_STRINGS + pools.FILTER_OLB_STRINGS:
            off = pools._offset(patched, va)
            self.assertEqual(patched[off: off + 40], _u16("Linebackers", 40))
        self.assertNotIn("Inside Linebackers".encode("utf-16le"), patched)
        self.assertNotIn("Outside Linebackers".encode("utf-16le"), patched)

    def test_optional_code_sites_can_be_left_out(self) -> None:
        patched, receipt = pools.apply(self.prepared, linebacker_penalty_fix=False, depth_chart_third_starter=False)
        self.assertEqual(pools.status(patched, linebacker_penalty_fix=False, depth_chart_third_starter=False), "applied")
        self.assertEqual(pools.status(patched), "foreign")           # the default profile expects the code sites
        self.assertIsNone(receipt["cave_va"])
        off = pools._offset(patched, pools.PENALTY_JNE_VA)
        self.assertEqual(patched[off: off + 2], pools.RETAIL_PENALTY_BYTES)
        off = pools._offset(patched, pools.CAVE_VA)
        self.assertEqual(patched[off: off + 32], pools.RETAIL_CAVE_HELPER)
        off = pools._offset(patched, pools.TAB_INIT_VA)
        self.assertEqual(patched[off: off + len(pools.RETAIL_TAB_INIT)], pools.RETAIL_TAB_INIT)   # no cave, no row shift
        # data sites still applied
        self.assertEqual(pools.read_tables(patched)["roster_targets"]["OLB"], 0)
        self.assertEqual(pools.rating_table_rows(patched, "defense_b")[3]["position"], "ILB")

    def test_apply_refuses_applied_and_foreign(self) -> None:
        patched, _ = pools.apply(self.prepared)
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(patched)
        foreign = bytearray(self.prepared)
        off = pools._offset(self.prepared, pools.ROSTER_TARGETS_VA) + 4 * pools.ENUM_DE
        struct.pack_into("<I", foreign, off, 9)
        self.assertEqual(pools.status(bytes(foreign)), "foreign")
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(bytes(foreign))
        moved = bytearray(self.prepared)
        off = pools._offset(self.prepared, modern.record_va(modern.UNIT_43, 5)) + modern.SLOT_TEXT_BYTES
        struct.pack_into("<I", moved, off, pools.ENUM_OLB)              # MIKE record pointed elsewhere: asserted field
        self.assertEqual(pools.status(bytes(moved)), "foreign")

    def test_three_four_line_labels_before_pools_are_accepted(self) -> None:
        labelled, _ = modern.apply(edge.apply(self.retail)[0], three_four_line=True)
        self.assertEqual(pools.status(labelled), "retail")
        patched, _ = pools.apply(labelled)
        self.assertEqual(pools.status(patched), "applied")
        self.assertEqual(edge.status(patched), "applied")

    def test_modern_status_reads_foreign_on_a_mixed_pool_profile(self) -> None:
        patched, _ = pools.apply(self.prepared)
        mixed = bytearray(patched)
        off = pools._offset(patched, modern.record_va(modern.UNIT_43, 4)) + modern.SLOT_TEXT_BYTES
        struct.pack_into("<II", mixed, off, pools.ENUM_OLB, 1)          # SAM back to retail, the rest one-pool
        self.assertEqual(modern.status(bytes(mixed)), "foreign")
        self.assertIsNone(modern.pool_profile(bytes(mixed)))


@unittest.skipUnless(RETAIL_XBE.is_file(), "retail default.xbe not present")
class RetailXbeSmokeTests(unittest.TestCase):
    def test_retail_reads_retail_and_applies_after_edge_and_labels(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        self.assertEqual(pools.status(payload), "retail")
        tables = pools.read_tables(payload)
        self.assertEqual(tables["enum_to_kind"], list(pools.RETAIL_ENUM_TO_KIND))
        self.assertEqual(bytes(tables["kind_to_enum"]), pools.RETAIL_KIND_TO_ENUM)
        self.assertEqual(tuple(tables["roster_targets"].values()), pools.RETAIL_TARGETS)
        self.assertEqual(tuple(tables["roster_maxima"].values()), pools.RETAIL_MAXIMA)
        self.assertEqual(tables["abbreviations"], list(RETAIL_ABBREVS))
        edged, _ = edge.apply(payload)
        labelled, _ = modern.apply(edged)
        self.assertEqual(pools.status(labelled), "retail")
        patched, receipt = pools.apply(labelled)
        self.assertEqual(pools.status(patched), "applied")
        self.assertEqual(modern.status(patched), "applied")
        self.assertEqual(edge.status(patched), "applied")
        self.assertEqual(receipt["sections_repinned"], [0, 12, 14])   # .text, .rdata, .string_
        for section in strength._sections(patched):
            self.assertEqual(section.stored_digest, strength.section_digest(patched, section), section.index)
        self.assertEqual(receipt["tables"]["abbreviations"], ["QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE",
                                                              "LB", "LB", "C", "G", "T", "DT", "EDGE"])


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN, "retail default.xbe and unicorn needed")
class EmulationTests(unittest.TestCase):
    """The rewritten tab init and the rating tables run on the real code with a synthetic team."""

    TEAM_VA = 0x02000000
    STACK_VA = 0x07000000
    SENT_VA = 0x07F00000
    SCRATCH = SENT_VA + 0x100
    PLAYER_STRIDE = 0x54

    @classmethod
    def setUpClass(cls) -> None:
        retail = RETAIL_XBE.read_bytes()
        cls.retail = retail
        cls.patched, _ = pools.apply(modern.apply(edge.apply(retail)[0])[0])

    def _boot(self, payload: bytes, players: list[tuple[int, int, int, dict[int, int]]]):
        """players: (position, rank, side, {attribute offset: value}); a 0x1F4 team at TEAM_VA."""
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0, 0x1000000)
        uc.mem_map(self.TEAM_VA, 0x10000)
        uc.mem_map(self.STACK_VA, 0x100000)
        uc.mem_map(self.SENT_VA, 0x10000)
        for section in strength._sections(payload):
            if section.raw_size:
                uc.mem_write(section.virtual_address, payload[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_write(self.SENT_VA, b"\xd9\x1d" + struct.pack("<I", self.SCRATCH) + b"\x90")   # fstp [scratch]; nop
        team = bytearray(0x1F4)
        base = self.TEAM_VA + 0x400
        for i, (pos, rank, side, attrs) in enumerate(players):
            rec = bytearray(self.PLAYER_STRIDE)
            rec[8] = 4
            struct.pack_into("<H", rec, 0x28, (rank << 10) | (side << 13))
            rec[0x35] = pos
            rec[0x50] = 100                                   # consistency: no injury scaling
            for off, value in attrs.items():
                rec[off] = value
            uc.mem_write(base + i * self.PLAYER_STRIDE, bytes(rec))
            struct.pack_into("<I", team, i * 4, base + i * self.PLAYER_STRIDE)
        team[0x11C] = len(players)
        uc.mem_write(self.TEAM_VA, bytes(team))
        return uc

    def _call(self, uc, entry: int, *, ecx: int = 0, edx: int = 0, stack: tuple[int, ...] = (), until: int | None = None) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        esp = self.STACK_VA + 0x80000
        uc.mem_write(esp, struct.pack("<%dI" % (1 + len(stack)), self.SENT_VA, *stack))
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.reg_write(UC_X86_REG_EDX, edx)
        uc.emu_start(entry, until if until is not None else self.SENT_VA + 6, count=5_000_000)
        return uc.reg_read(UC_X86_REG_EAX)

    def _rows(self, uc, unit: int, slot: int) -> int:
        uc.mem_write(pools.DC_UNIT_VA, struct.pack("<I", unit))
        uc.mem_write(pools.DC_SLOT_VA, struct.pack("<I", slot))
        uc.mem_write(pools.DC_TEAM_VA, struct.pack("<I", self.TEAM_VA))
        self._call(uc, 0x243D20, ecx=self.TEAM_VA + 0x8000, until=0x243E2C)       # stop at the tail's jmp
        return struct.unpack("<I", bytes(uc.mem_read(pools.DC_ROWS_VA, 4)))[0]

    def _row(self, uc, row: int, unit: int, slot: int) -> int:
        record = modern.read_record(self.patched, unit, slot)
        return self._call(uc, pools.ROW_LOOKUP_SITE_VA - 0x27, edx=self.TEAM_VA, stack=(row, record["position"], record["chain"]))

    @staticmethod
    def _lbs(n: int) -> list[tuple[int, int, int, dict[int, int]]]:
        return [(pools.ENUM_ILB, min(i, 7), min({0: 2, 1: 0, 2: 1}.get(i, i), 7), {}) for i in range(n)]

    def test_tab_init_lists_one_row_fewer_for_the_shifted_records(self) -> None:
        for n in (3, 6, 9):
            uc = self._boot(self.patched, self._lbs(n) + [(pools.ENUM_DT, 0, 2, {}), (8, 0, 0, {}), (7, 0, 0, {})])
            self.assertEqual(self._rows(uc, modern.UNIT_43, 5), n)          # MIKE (11, 0)
            self.assertEqual(self._rows(uc, modern.UNIT_43, 6), n)          # WILL (11, 1)
            self.assertEqual(self._rows(uc, modern.UNIT_43, 4), n - 1)      # SAM (11, 3): shifted by one
            self.assertEqual(self._rows(uc, modern.UNIT_34, 1), 1)          # NT (15, 0)
            self.assertEqual(self._rows(uc, modern.UNIT_34, 2), 0)          # third lineman (15, 3) with one DT
            self.assertEqual(self._rows(uc, 3, 0), 2)                        # KR: FB + HB + SS + FS + CB + WR
            # every SAM row resolves to a player and the retail rows are the same players as before
            sam = [self._row(uc, r, modern.UNIT_43, 4) for r in range(n - 1)]
            self.assertTrue(all(sam))
            self.assertEqual(self._row(uc, n - 1, modern.UNIT_43, 4), 0)    # the row the retail count would have asked for
            self.assertEqual(len(set(sam)), n - 1)
        retail = self._boot(self.retail, self._lbs(6))
        self.assertEqual(self._rows(retail, modern.UNIT_43, 5), 6)

    def test_defense_tables_no_longer_average_a_zero_for_the_retired_enum(self) -> None:
        def players():
            attrs = {off: 80 for off in range(0x36, 0x52)}
            out = self._lbs(5)
            out = [(p, r, s, dict(attrs)) for p, r, s, _ in out]
            for pos, n in ((pools.ENUM_DE, 4), (pools.ENUM_DT, 4), (4, 4), (5, 2), (6, 2)):
                for i in range(n):
                    out.append((pos, min(i, 7), {0: 2, 1: 0, 2: 1}.get(i, i), dict(attrs)))
            return out

        def defense(payload):
            uc = self._boot(payload, players())
            self._call(uc, 0xC4860, ecx=self.TEAM_VA)
            return struct.unpack("<f", bytes(uc.mem_read(self.SCRATCH, 4)))[0]

        # the same one-pool roster (no enum-10 player) rated by the retail tables and by the patched ones:
        # retail averages a zero for every OLB entry (55/225 of defense B, 25/185 of defense A)
        before, after = defense(self.retail), defense(self.patched)
        self.assertGreater(after - before, 0.15, (before, after))
        self.assertLess(after, 1.2)                     # FUN_000c4860 is not clamped; the bar code clamps


if __name__ == "__main__":
    unittest.main()
