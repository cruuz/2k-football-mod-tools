"""Standalone r64 pointer-table, roster-policy and bounded native regressions."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_edge_rename as edge, nfl2k5_modern_positions as modern
from mod_editor.core import nfl2k5_probowl_order as probowl
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tools import nfl2k5_roster_reclassify as rr

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


def resource(entry, *, primary=(11, 16), secondary=(10,), owned=()):
    body = bytearray(0x100 + 0x54 * (len(primary) + len(secondary)))
    players = {0x100 + 0x54 * i: None for i in range(len(primary) + len(secondary))}
    for off, enum in zip(players, (*primary, *secondary)):
        body[off + 0x35] = enum
    return SimpleNamespace(entry=entry, body=bytes(body), players=players,
                           tables={"primary_players": {"offset": 0x100, "count": len(primary)}},
                           teams=[SimpleNamespace(roster=list(owned))])


class RosterPolicyTests(unittest.TestCase):
    def resources(self):
        return [resource(i) for i in (5, *range(113, 188))]

    def test_complete_zero_scan_excludes_only_unowned_templates(self):
        receipt = rr.olb_filter_evidence(self.resources())
        self.assertTrue(receipt["complete"])
        self.assertIs(receipt["roster_has_olb"], False)
        self.assertEqual(receipt["filter_rows"], "removed")
        self.assertEqual(sum(r["players"] for r in receipt["resources"]), 152)

    def test_unattached_primary_historic_and_owned_secondary_each_keep_row(self):
        for index, replacement in ((0, resource(5, primary=(11, 10))),
                                   (75, resource(187, primary=(10, 11))),
                                   (0, resource(5, owned=(0x100 + 2 * 0x54,)))):
            rows = self.resources()
            rows[index] = replacement
            receipt = rr.olb_filter_evidence(rows)
            self.assertTrue(receipt["complete"])
            self.assertIs(receipt["roster_has_olb"], True)
            self.assertEqual(receipt["olb_players"], 1)
            self.assertEqual(receipt["filter_rows"], "retained")

    def test_partial_empty_duplicate_and_invalid_scans_cannot_remove(self):
        for rows in ([], self.resources()[:-1], [resource(5)],
                     [resource(i, primary=()) for i in (5, *range(113, 188))]):
            result = rr.olb_filter_evidence(rows)
            self.assertFalse(result["complete"])
            self.assertIsNone(result["roster_has_olb"])
            self.assertEqual(result["filter_rows"], "retained")
        for rows in ([resource(5), resource(5)], [resource(5, primary=(255,))],
                     [resource(5, owned=(0xBAD,))]):
            with self.assertRaises(ValueError):
                rr.olb_filter_evidence(rows)


class RetailTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not XBE.is_file():
            raise unittest.SkipTest("pinned USA retail default.xbe extraction is absent")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("extracted XBE is not the pinned USA retail image")
        cls.base = modern.apply(edge.apply(cls.retail)[0])[0]
        cls.retained = pools.apply(cls.base)[0]
        cls.removed, cls.receipt = pools.apply(cls.retained, roster_has_olb=False)

    def test_all_sixteen_lists_shift_four_and_preserve_every_page_and_neighbor(self):
        self.assertEqual(len(pools.FILTER_TABLES), 16)
        self.assertEqual(len({t[2] for t in pools.FILTER_TABLES}), 15)
        before, after = XbeImage(self.retained), XbeImage(self.removed)
        for definition, site in zip(pools.FILTER_TABLES, pools.filter_list_sites()):
            name, va, olb, stride, pages = definition
            with self.subTest(screen=name):
                self.assertEqual(before.read(va, site.size), site.befores[0])
                self.assertEqual(after.read(va, site.size), site.after)
                words = struct.unpack("<" + "I" * (len(pages) + 1), site.after)
                self.assertEqual(words, tuple(p for p in pages if p != olb - 8) + (0, 0))
                self.assertEqual(after.read(va - 4, 4), before.read(va - 4, 4))
                self.assertEqual(after.read(va + site.size, 4), before.read(va + site.size, 4))
                self.assertEqual(struct.unpack("<I", before.read(olb + stride + 0x18, 4))[0], 11)
                for page in pages:
                    self.assertEqual(after.read(page, stride), before.read(page, stride))
                enums = [struct.unpack("<I", after.read(p + 0x20, 4))[0] for p in words[:-2]]
                self.assertNotIn(10, enums)
                self.assertEqual(enums.count(11), 1)
                self.assertEqual(enums.count(8), 1)

    def test_exact_receipt_only_data_and_one_digest_no_growth(self):
        self.assertEqual(len(self.removed), len(self.retained))
        self.assertEqual(len(self.receipt["edits"]), 16)
        allowed = set()
        for site, edit in zip(pools.filter_list_sites(), self.receipt["edits"]):
            off = pools._offset(self.retained, site.va)
            self.assertEqual(edit["before"], site.befores[0].hex())
            self.assertEqual(edit["after"], site.after.hex())
            self.assertEqual(int(edit["file_offset"], 0), off)
            self.assertEqual(edit["group"], "filter_lists")
            allowed.update(range(off, off + site.size))
        changed = {i for i, (a, b) in enumerate(zip(self.retained, self.removed)) if a != b}
        self.assertEqual(len(changed), self.receipt["changed_bytes"])
        self.assertEqual(len(self.receipt["sections_repinned"]), 1)
        for section in pools._sections(self.removed):
            if section.index in self.receipt["sections_repinned"]:
                allowed.update(range(section.header_offset + 36, section.header_offset + 56))
                self.assertEqual(self.removed[section.header_offset + 36:section.header_offset + 56],
                                 pools.section_digest(self.removed, section))
        self.assertFalse(changed - allowed)
        self.assertTrue(pools.retail_olb_identity(self.removed))

    def test_replay_legacy_upgrade_custom_restore_and_unknown_default(self):
        self.assertEqual(pools.filter_list_status(self.retained), "retail")
        for value in (None, False):
            replay, receipt = pools.apply(self.removed, roster_has_olb=value)
            self.assertEqual(replay, self.removed)
            self.assertEqual(receipt["changed_bytes"], 0)
            self.assertEqual(receipt["edits"], [])
            self.assertEqual(receipt["sections_repinned"], [])
        restored, receipt = pools.apply(self.removed, roster_has_olb=True)
        self.assertEqual(restored, self.retained)
        self.assertEqual(receipt["olb_filter_rows"], "retained")
        self.assertEqual(pools.apply(restored, roster_has_olb=True)[0], restored)
        self.assertEqual(pools.apply(self.base, roster_has_olb=False)[0], self.removed)
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(self.retail, roster_has_olb=False)
        with self.assertRaises(pools.PositionPoolsError):
            pools.apply(self.base, roster_has_olb="false")

    def test_half_edited_lists_and_changed_readers_refuse_before_mutation(self):
        for site in pools.filter_list_sites():
            with self.subTest(site=site.label):
                buf = bytearray(self.retained)
                off = pools._offset(buf, site.va)
                buf[off:off + site.size] = site.after
                original = bytes(buf)
                self.assertEqual(pools.status(original), "foreign")
                with self.assertRaises(pools.PositionPoolsError):
                    pools.apply(buf, roster_has_olb=False)
                self.assertEqual(bytes(buf), original)
                buf = bytearray(self.removed)
                buf[off + site.size - 1] = 1
                self.assertEqual(pools.status(buf), "foreign")
        for va, _size, _digest in pools.FILTER_READER_GUARDS:
            buf = bytearray(self.retained)
            buf[pools._offset(buf, va)] ^= 1
            original = bytes(buf)
            with self.assertRaises(pools.PositionPoolsError):
                pools.apply(buf, roster_has_olb=False)
            self.assertEqual(bytes(buf), original)

    def test_probowl_order_and_membership_compose_both_orders_and_restore(self):
        a = probowl.apply(self.removed)[0]
        b = pools.apply(probowl.apply(self.retained)[0], roster_has_olb=False)[0]
        self.assertEqual(a, b)
        self.assertEqual(probowl.status(a), "applied")
        self.assertEqual(pools.status(a), "applied")
        self.assertEqual(probowl.apply(a)[0], a)
        self.assertEqual(pools.apply(a, roster_has_olb=True)[0], probowl.apply(self.retained)[0])
        self.assertNotIn("OLB", probowl.apply(a)[1]["order"])

    def test_practice_screen_clone_is_identical_before_and_after_compaction(self):
        from tests.nfl2k5_practice_squad_screen_fixture import composed
        from mod_editor.core import nfl2k5_practice_squad_screen as screen
        first = screen.apply(composed(self.removed))[0]
        second = pools.apply(screen.apply(composed(self.retained))[0], roster_has_olb=False)[0]
        self.assertEqual(first, second)
        self.assertEqual(screen.status(first), "applied")


class NativeListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RetailTablesTests.setUpClass.__func__(cls)
        if importlib.util.find_spec("unicorn") is None:
            raise unittest.SkipTest("bounded native list-builder proof requires Unicorn")
        if not (XBE.parent / "vc_53450030" / "0").is_file():
            raise unittest.SkipTest("private extracted ROST archive is absent")
        with rr._open(XBE.parent, False) as archive:
            cls.resource = rr.load_resources(archive, historic=False)[0]
            body = bytearray(cls.resource.body)
            moves, _ = rr.plan_resource(cls.resource, rr.book_schemes(archive))
            rr.apply_moves(body, moves)
            cls.pooled_body = bytes(body)

    def scenario(self, custom):
        from tests.nfl2k5_olb_row_fixture import Machine
        m = Machine(self.retained if custom else self.removed, self.resource, self.pooled_body, custom=custom)
        for name, table, _olb, _stride, pages in pools.FILTER_TABLES:
            with self.subTest(screen=name, custom=custom):
                m.open(table)
                if name == "team_rosters":
                    # Select an actual team, then separately exercise FA below.
                    m.put(m.UI + 0x68, 0)
                    m.call(0x174140, eax=m.UI)
                count = m.call(0x170910, ecx=m.UI)
                self.assertEqual(count, len(pages) - int(not custom))
                results = []
                for i in range(count):
                    self.assertEqual(m.call(0x1706C0, ecx=m.UI), i)
                    result = m.result()
                    results.append(result)
                    enum = result["enum"]
                    if enum in (8, 10, 11):
                        self.assertEqual(len(result["players"]), (2 if name == "choose_players" else 1)
                                         if enum in (10, 11) and (enum == 11 or custom) else 0)
                        self.assertTrue(all(m.byte(p + 0x35) == enum for p in result["players"]))
                        if name == "team_rosters":
                            self.assertEqual(result["players"], [p for p in m.team_players if m.byte(p + 0x35) == enum])
                    m.call(0x174CB0, ecx=m.UI)
                self.assertEqual(m.word(m.UI + 0x5C), table)
                titles = [r["title"] for r in results]
                self.assertEqual(titles.count("Linebackers"), 1)
                self.assertIn("Fullbacks", titles)
                self.assertEqual(sum(t.lower() == "outside linebackers" for t in titles), int(custom))
                # Reverse wrap and indexed restore use the compact ordinal,
                # while callbacks continue to read the descriptor's enum.
                m.call(0x174CE0, ecx=m.UI)
                self.assertEqual(m.word(m.UI + 0x5C), table + 4 * (count - 1))
                for i in reversed(range(count)):
                    m.call(0x174D30, ecx=m.UI, edx=i)
                    self.assertEqual(m.result(), results[i])
                if name == "team_rosters":
                    for enum in ((10, 11) if custom else (11,)):
                        index = next(i for i, result in enumerate(results) if result["enum"] == enum)
                        m.put(m.UI + 0x68, 0xFFFFFFFF)
                        m.call(0x174D30, ecx=m.UI, edx=index)
                        self.assertEqual(m.result()["players"], [p for p in m.fa_players if m.byte(p + 0x35) == enum])
        for pc in (0x35F140, 0x2B8D90, 0x3213E0, 0x31AB20, 0x36F720, 0xC3CB0, 0xC3D30, 0x242520):
            self.assertGreater(m.native_calls[pc], 0, hex(pc))
        m.close()

    def test_native_pooled_every_selector_forward_reverse_index_empty_fullbacks(self):
        self.scenario(False)

    def test_native_custom_enum_ten_remains_selectable_on_every_selector(self):
        self.scenario(True)

    def test_native_constructors_and_cached_ordinal_bounds_in_both_profiles(self):
        from tests.nfl2k5_olb_row_fixture import Machine
        for custom, payload in ((False, self.removed), (True, self.retained)):
            m = Machine(payload, self.resource, self.pooled_body, custom=custom)
            for _name, table, _olb, _stride, pages in pools.FILTER_TABLES:
                m.call(0x1707F0, ecx=m.UI)
                m.call(0x1749D0, ecx=m.UI, edx=table - 0xF4, args=(m.MANAGER, 0, 0, 0, 0))
                self.assertEqual(m.word(m.UI + 0x5C), table)
                self.assertEqual(m.call(0x170910, ecx=m.UI), len(pages) - int(not custom))
            # The FA screen restores its cached ordinal only below the freshly
            # counted length. Exercise the original last ordinal and both ends.
            m.open(0x53E7E4)
            count = m.call(0x170910, ecx=m.UI)
            m.put(m.MANAGER + 0x10C, m.UI - 0x65C)
            for cached, expected in ((count, 0), (count - 1, count - 1), (0, 0)):
                m.put(0xCC1C28, cached)
                m.call(0x362E10, ecx=m.MANAGER)
                self.assertEqual(m.call(0x1706C0, ecx=m.UI), expected)
            m.close()

    def test_all_76_real_resources_scan_before_and_after_bounded_recoding(self):
        retail = rr.olb_filter_policy(XBE.parent)
        self.assertIs(retail["roster_has_olb"], True)
        with rr._open(XBE.parent, False) as archive:
            schemes = rr.book_schemes(archive)

            def converted():
                for index in (5, *range(113, 188)):
                    resource = rr.parse_resource(index, archive.entries[index].virtual_offset, archive.read_entry(index))
                    body = bytearray(resource.body)
                    rr.apply_moves(body, rr.plan_resource(resource, schemes)[0])
                    yield replace(resource, body=bytes(body))

            pooled = rr.olb_filter_evidence(converted())
        self.assertTrue(pooled["complete"])
        self.assertIs(pooled["roster_has_olb"], False)
        self.assertEqual(sum(r["players"] for r in pooled["resources"]), 6454)
        self.assertEqual(retail["olb_players"], 493)
        self.assertEqual(pooled["olb_players"], 0)


if __name__ == "__main__":
    unittest.main()
