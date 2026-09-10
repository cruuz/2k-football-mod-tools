"""Synthetic authoring/ownership tests and explicitly gated retail proofs."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dataclasses import replace
import json
import os
import struct
import zlib
import unittest
from unittest.mock import patch

from mod_editor.core import apf2k8_play_codec as c
from mod_editor.core import nfl2k5_play_codec as nfl
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_play_designer import (
    compile_design, decode_plan, empty_plan, encode_plan, normalize_plan, sha, verify_design,
)
from mod_editor.core.apf2k8_play_design_build import (
    build_design, compile_cpu_calls, pack_resource, read_resource,
    parse_resource, apf_inner, apf_outer, apf_texture_patch,
)
from mod_editor.core.apf2k8_play_concepts import concept_plan
from mod_editor.core.errors import ValidationError

INDEX = Path(os.environ.get("APF_RETAIL_INDEX", "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"))


def synthetic() -> bytes:
    data = bytearray(c.BODY_SIZE)
    data[12:16] = b"YALP"
    struct.pack_into("<I", data, 16, 32)
    data[32:40] = "mpb\0".encode("utf-16be")
    struct.pack_into(">4I", data, 52, 2, 4, 2, 8)
    cursor = c.STRING_BASE
    for field, name in ([(48, "MASTER"), (c.CATEGORY_BASE, "Offense"), (c.CATEGORY_BASE + 16, "Defense"),
                        (c.FORMATION_BASE, "Test formation"), (c.FORMATION_BASE + c.FORMATION_SIZE, "Test defense")]
    + [(c.PLAY_BASE + i * c.PLAY_SIZE, f"Synthetic play {i}") for i in range(4)]):
        encoded = (name + "\0").encode("utf-16be")
        struct.pack_into(">i", data, field, c.relative_token(field, cursor))
        data[cursor:cursor + len(encoded)] = encoded
        cursor += len(encoded)
    for fi in range(2):
        at = c.FORMATION_BASE + fi * c.FORMATION_SIZE
        data[at + 5] = fi * 4
        data[at + 12:at + 17] = bytes(range(6, 11))
        data[at + 17:at + 28] = bytes(range(11))
        for s in range(11):
            struct.pack_into(">H3h3h", data, at + 30 + s * 14, s << 4 | 3, s * 90, s * 100, s * 110, -s * 30, -s * 40, -s * 50)
    nodes = [
        c.Node(1, 0, (1, 3, 0, 0.0, 0.0, 0.0)),
        c.Node(18, 64, (0, 0, 6 * 30.48, 15)), c.Node(18, 32, (4, 0, 12 * 30.48, 15)),
        c.Node(1, 0, (1, 3, 0, 0.0, 0.0, 0.0)),
        c.Node(18, 64, (0, 0, 9 * 30.48, 15)), c.Node(18, 32, (6, 0, 15 * 30.48, 15)),
        c.Node(27, 0, (0, 0, 0.0, 0.0, 17, 0)), c.Node(13, 96, (0.0, 9 * 30.48, 0, 0, 0, 0, 0)),
    ]
    data[c.NODE_BASE:c.NODE_BASE + len(nodes) * 8] = b"".join(n.to_bytes() for n in nodes)
    for pi in range(4):
        at = c.PLAY_BASE + pi * c.PLAY_SIZE
        struct.pack_into(">II", data, at + 4, 0 if pi < 2 else 1 << 28, 6 if pi < 2 else 0x1000)
        for slot in range(11):
            start = 3 if (pi, slot) == (0, 0) else 0 if pi < 2 else 6
            count = 3 if pi < 2 else 2
            struct.pack_into(">Ii", data, at + 12 + slot * 8, count << 28 | 0x0110BC00,
                             c.relative_token(at + 16 + slot * 8, c.NODE_BASE + start * 8))
    return bytes(data)


def play_request(mode="edit", target=0, donor=0, name=None, nodes=None, copies=None):
    return {"mode": mode, "target": target, "donor": donor, "name": name, "nodes": nodes or [], "copies": copies or []}


def synthetic_cpu() -> bytes:
    data = bytearray(splb.RESOURCE_SIZE)
    data[12:16] = b"BLPS"
    name = "O-TwoBack\0".encode("utf-16be")
    data[48:48 + len(name)] = name
    for ri in range(176):
        at = splb.RECORD_BASE + ri * 176
        for slot in range(84):
            struct.pack_into(">H", data, at + slot * 2, splb.FILLER)
    struct.pack_into(">H", data, splb.RECORD_BASE, splb.SplbEntry(2, 1, 0).encode())
    struct.pack_into(">II", data, splb.RECORD_BASE + 168, 0, 1)
    struct.pack_into(">I", data, splb.BOOK_CATEGORY_MASK_OFFSET, 1)
    return bytes(data)


def synthetic_resource(body: bytes):
    compressed = apf_texture_patch.compress_h7a(body, 11)
    stored = struct.pack(">5I", apf_inner.H7A_MAGIC, len(body), 20 + len(compressed), 7, 11) + compressed
    header = bytearray(84)
    struct.pack_into(">8I", header, 0, apf_inner.IFF_MAGIC, 84, 84 + len(stored), 0, 1, 13, 1, 37)
    struct.pack_into(">8I", header, 32, 0, 0, 32, len(body), 7, 84, len(stored), 0)
    struct.pack_into(">5I", header, 64, 5, zlib.crc32(b"mpb"), zlib.crc32(b"PLAY"), 1, 0)
    name, kind = "mpb\0".encode("utf-16le"), "PLAY\0".encode("utf-16le")
    payload = struct.pack("<5I", 1, 5, 5, 9, 5 + len(name)) + name + kind
    raw = bytes(header) + stored + struct.pack(">I", apf_inner.NAME_FOOTER_MAGIC) + struct.pack("<I", len(payload)) + payload
    allocation = (len(raw) + 4095) // 2048 * 2048
    raw += bytes(allocation - len(raw))
    entry = apf_outer.Entry(180, 0, 0, allocation // 2048, 0, allocation, "", ())
    return parse_resource(entry, raw)


class CodecTests(unittest.TestCase):
    def test_whole_synthetic_body_is_structurally_rebuilt(self):
        source = synthetic()
        self.assertEqual(c.Book.from_bytes(source).to_bytes(), source)

    def test_native_align_is_not_the_nfl_layout(self):
        for mode in range(4):
            for left in range(18):
                values = (mode, 1, left, 0, 17 - left, 12, 0)
                node = c.Node(28, 96, values)
                self.assertEqual(c.Node.from_bytes(node.to_bytes()), node)
                self.assertEqual(c.decode_align(c.encode_align(values), True), (mode, 0, 17 if left == 0 else left - 1, 1, 17 if left == 17 else 16 - left, 12, 0))

    def test_reserved_operand_and_header_bits_survive_field_edit(self):
        raw = struct.pack(">BBHI", 18, 0xE0, 0x9876, 0x50112345)
        node = c.Node.from_bytes(raw)
        out = node.with_field("distance_ft", 30).to_bytes()
        self.assertEqual(out[:4], raw[:4])
        self.assertEqual(out[5:], raw[5:])

    def test_invalid_fields_refuse_without_wraparound(self):
        node = c.Node(18, 32, (0, 0, 0.0, 15))
        for key, value in [("distance_ft", 192), ("distance_ft", True), ("distance_ft", -65), ("segment_type", 15), ("drop", 5)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                node.with_field(key, value)

    def test_descriptor_count_is_used_instead_of_next_pointer(self):
        source = bytearray(synthetic())
        struct.pack_into(">I", source, c.PLAY_BASE + 12, 15 << 28)
        with self.assertRaisesRegex(ValidationError, "node pool"):
            c.Book.from_bytes(bytes(source))


class DesignerTests(unittest.TestCase):
    def setUp(self):
        self.source = synthetic()
        self.plan = empty_plan(self.source)

    def test_unique_node_edit_keeps_index_pool_and_other_assignments(self):
        self.plan["plays"] = [play_request(nodes=[[0, 1, "distance_ft", 30]])]
        result = compile_design(self.source, self.plan)
        before, after = c.Book.from_bytes(self.source), c.Book.from_bytes(result.replacement)
        self.assertEqual(len(after.nodes), len(before.nodes))
        self.assertEqual(after.chain(0, 0)[1].operands[2], 30 * 30.48)
        self.assertEqual(after.opaque_relation, before.opaque_relation)
        for pi in range(4):
            for slot in range(11):
                if (pi, slot) != (0, 0):
                    self.assertEqual(after.chain(pi, slot), before.chain(pi, slot))

    def test_shared_node_edit_detaches_only_target(self):
        self.plan["plays"] = [play_request(nodes=[[1, 1, "distance_ft", 30]])]
        result = compile_design(self.source, self.plan)
        before, after = c.Book.from_bytes(self.source), c.Book.from_bytes(result.replacement)
        self.assertEqual(len(after.nodes), len(before.nodes) + 3)
        self.assertEqual(after.chain(1, 1), before.chain(1, 1))
        self.assertNotEqual(after.chain(0, 1), before.chain(0, 1))

    def test_append_and_rename_relocate_all_name_pointers(self):
        self.plan["plays"] = [play_request("append", 4, 1, "New Ω play")]
        result = compile_design(self.source, self.plan)
        after = c.Book.from_bytes(result.replacement)
        self.assertEqual(after.play_name(4), "New Ω play")
        self.assertEqual(after.chain(4, 6), c.Book.from_bytes(self.source).chain(1, 6))
        self.assertEqual(len(after.plays), 5)

    def test_explicit_replacement_keeps_other_names_and_opaque_relation(self):
        self.plan["plays"] = [play_request("replace", 0, 1, "Replaced slot, much longer")]
        after = c.Book.from_bytes(compile_design(self.source, self.plan).replacement)
        self.assertEqual(len(after.plays), 4)
        self.assertEqual(after.play_name(1), "Synthetic play 1")
        self.assertEqual(after.chain(0, 0), after.chain(1, 0))
        self.assertEqual(after.opaque_relation, c.Book.from_bytes(self.source).opaque_relation)

    def test_append_formation_coordinates_all_variants(self):
        self.plan["formations"] = [{"mode": "append", "target": 2, "donor": 0, "name": "New formation", "positions": [[0, v, 10, -410] for v in range(3)]}]
        after = c.Book.from_bytes(compile_design(self.source, self.plan).replacement)
        self.assertEqual(after.formations[2].slots[0].y, (-410,) * 3)
        self.assertEqual(after.formations[2].slot_order, tuple(range(11)))
        self.assertEqual(after.formations[0].slots[0].y, (0,) * 3)

    def test_assignment_swap_delegates_to_route_writer(self):
        self.plan["plays"] = [play_request(copies=[[0, 1]]), play_request(target=1, donor=1, copies=[[0, 0]])]
        result = compile_design(self.source, self.plan)
        after, before = c.Book.from_bytes(result.replacement), c.Book.from_bytes(self.source)
        self.assertEqual(after.chain(0, 0), before.chain(1, 0))
        self.assertEqual(after.chain(1, 0), before.chain(0, 0))

    def test_replacement_preserves_side_and_personnel_for_existing_calls(self):
        self.plan["plays"] = [play_request("replace", 0, 2, "Wrong side")]
        with self.assertRaisesRegex(ValidationError, "type/side"):
            compile_design(self.source, self.plan)
        self.plan["plays"] = []
        self.plan["formations"] = [{"mode": "replace", "target": 0, "donor": 1, "name": "Wrong personnel", "positions": []}]
        with self.assertRaisesRegex(ValidationError, "personnel category"):
            compile_design(self.source, self.plan)

    def test_orphaning_copy_still_requires_relay(self):
        self.plan["plays"] = [play_request(copies=[[0, 1]])]
        with self.assertRaisesRegex(ValidationError, "Swap"):
            compile_design(self.source, self.plan)

    def test_defensive_clone_and_zone_landmark_edit(self):
        self.plan["plays"] = [play_request("append", 4, 2, "New zone", [[4, 1, "y_ft", 21]])]
        after = c.Book.from_bytes(compile_design(self.source, self.plan).replacement)
        self.assertEqual(after.plays[4].type_nibble, 1)
        self.assertEqual(after.chain(4, 4)[1].operands[1], 21 * 30.48)
        self.assertEqual(after.chain(2, 4)[1].operands[1], 9 * 30.48)

    def test_idempotent_apply_and_changed_source_rejected(self):
        self.plan["plays"] = [play_request(nodes=[[0, 1, "distance_ft", 30]])]
        first = compile_design(self.source, self.plan)
        second = compile_design(self.source, self.plan, current=first.replacement)
        self.assertEqual(first.replacement, second.replacement)
        self.assertTrue(second.report["already_applied"])
        with self.assertRaisesRegex(ValidationError, "SHA-256"):
            compile_design(first.replacement, self.plan)
        with self.assertRaisesRegex(ValidationError, "Current MASTER"):
            compile_design(self.source, self.plan, current=bytes(len(self.source)))

    def test_verifier_detects_other_play_tamper(self):
        self.plan["plays"] = [play_request(nodes=[[0, 1, "distance_ft", 30]])]
        result = bytearray(compile_design(self.source, self.plan).replacement)
        result[c.PLAY_BASE + c.PLAY_SIZE + 4] ^= 1
        with self.assertRaises(ValidationError):
            verify_design(self.source, bytes(result), self.plan)

    def test_bad_indices_names_duplicates_and_side(self):
        cases = [play_request("append", 5, 0, "Skipped"), play_request("append", 4, 0, "\0"),
                 play_request(nodes=[[0, 1, "distance_ft", 500]]), play_request(copies=[[0, 2]])]
        for request in cases:
            self.plan["plays"] = [request]
            with self.subTest(request=request), self.assertRaises(ValidationError):
                compile_design(self.source, self.plan)

    def test_payload_is_logical_strict_and_roundtrips(self):
        self.plan["plays"] = [play_request("append", 4, 0, "Made here")]
        self.assertEqual(decode_plan(encode_plan(self.plan)), self.plan)
        with self.assertRaises(ValidationError):
            decode_plan(b'{"schema":"a","schema":"b"}')
        with self.assertRaises(ValidationError):
            normalize_plan({**self.plan, "retail_hex": "00"})

    def test_pool_exhaustion_fails_closed(self):
        self.plan["plays"] = [play_request(nodes=[[1, 1, "distance_ft", 30]])]
        with patch.object(c, "NODE_CAPACITY", 8), self.assertRaisesRegex(ValidationError, "node pool"):
            compile_design(self.source, self.plan)

    def test_plan_encoding_cannot_create_an_unloadable_oversized_payload(self):
        self.plan["plays"] = [play_request(nodes=[[0, 1, "x" * (256 * 1024), 0]])]
        with self.assertRaisesRegex(ValidationError, "too large"):
            encode_plan(self.plan)

    def test_new_cpu_play_uses_reparsed_master_count_and_keeps_tags(self):
        self.plan["plays"] = [play_request("append", 4, 0, "CPU candidate")]
        after = compile_design(self.source, self.plan).replacement
        call = {"outer": 259, "record": 0, "play": 4, "formation": 0, "donor_record": None}
        body, _ = compile_cpu_calls(synthetic_cpu(), 259, self.source, after, [call])
        record = splb.parse_book(body, 259).records[0]
        self.assertEqual([e.play_index for e in record.entries], [0, 4])
        self.assertEqual([e.y for e in record.entries], [1, 0])
        again, _ = compile_cpu_calls(body, 259, self.source, after, [call])
        self.assertEqual(again, body)

    def test_new_cpu_formation_needs_explicit_empty_row_and_same_category(self):
        self.plan["formations"] = [{"mode": "append", "target": 2, "donor": 0, "name": "Callable", "positions": []}]
        after = compile_design(self.source, self.plan).replacement
        call = {"outer": 259, "record": 1, "play": 0, "formation": 2, "donor_record": 0}
        body, _ = compile_cpu_calls(synthetic_cpu(), 259, self.source, after, [call])
        self.assertEqual(splb.parse_book(body, 259).records[1].formation_index, 2)
        repeated, receipt = compile_cpu_calls(synthetic_cpu(), 259, self.source, after, [call], current=body)
        self.assertEqual(repeated, body)
        self.assertTrue(receipt["already_applied"])
        call["record"] = 0
        with self.assertRaisesRegex(ValidationError, "populated CPU row"):
            compile_cpu_calls(synthetic_cpu(), 259, self.source, after, [call])

    def test_cloned_cpu_formation_clears_donor_secondary_personnel(self):
        self.plan["formations"] = [{"mode": "append", "target": 2, "donor": 0, "name": "Callable", "positions": []}]
        after = compile_design(self.source, self.plan).replacement
        source = bytearray(synthetic_cpu())
        at = splb.RECORD_BASE + splb.TRAILER_OFFSET + 4
        struct.pack_into(">I", source, at, 1 | (1 << 8))
        source = bytes(source)
        call = {"outer": 259, "record": 1, "play": 0, "formation": 2, "donor_record": 0}
        body, receipt = compile_cpu_calls(source, 259, self.source, after, [call])
        rows = splb.parse_book(body, 259).records
        self.assertEqual(int.from_bytes(rows[0].trailer[4:], "big"), 257)
        self.assertEqual(int.from_bytes(rows[1].trailer[4:], "big"), 1)
        self.assertEqual(receipt["personnel"][0]["word_b_after"], 1)

    def test_synthetic_transport_for_both_master_and_cpu_resource_sizes(self):
        self.plan["plays"] = [play_request("append", 4, 0, "Transport", [[1, 1, "distance_ft", 45]])]
        after = compile_design(self.source, self.plan).replacement
        for before, changed in ((self.source, after), (synthetic_cpu(), synthetic_cpu())):
            resource = synthetic_resource(before)
            with patch("apf_texture_patch._optimal_binary", return_value=None):
                entry, receipt = pack_resource(resource, changed)
            self.assertEqual(parse_resource(resource.entry, entry).body, changed)
            self.assertEqual(receipt["overlapping_matches"], 0)
            self.assertTrue(receipt["h7a_round_trip_exact"])
            self.assertEqual(len(entry), resource.entry.size)


@unittest.skipUnless(INDEX.is_file(), f"Retail APF 0A absent: {INDEX}; set APF_RETAIL_INDEX to extracted read-only retail")
class RetailProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource = read_resource(INDEX, 180)
        cls.book = c.Book.from_bytes(cls.resource.body)

    def test_all_records_nodes_and_38_native_alignment_nodes(self):
        self.assertEqual((len(self.book.plays), len(self.book.formations), len(self.book.nodes)), (586, 163, 4948))
        self.assertEqual(self.book.to_bytes(), self.resource.body)
        lost = []
        for i, node in enumerate(self.book.nodes):
            raw = node.to_bytes()
            converted = raw[:4] + raw[4:][::-1]
            if nfl.Node.from_bytes(converted).to_bytes() != converted:
                lost.append(node.op)
            self.assertFalse(node.opaque_bits)
        self.assertEqual(lost, [28] * 38)
        for pi in range(586):
            for slot in range(11):
                self.assertTrue(self.book.chain(pi, slot)[-1].flags & c.NODE_TERMINAL)

    def test_complete_six_play_and_formation_build(self):
        plan = concept_plan(self.resource.body)
        defense = splb.read_book(INDEX, 618)
        drow = next(r for r in defense.records if r.entries)
        donor = next(e.play_index for e in drow.entries if any(n.op == 13 for s in range(11) for n in self.book.chain(e.play_index, s)))
        slot, ni = next((s, i) for s in range(11) for i, n in enumerate(self.book.chain(donor, s)) if n.op == 13)
        depth = round(self.book.chain(donor, slot)[ni].operands[1] / 30.48) + 3
        plan["plays"].append(play_request("append", 591, donor, "Astra Defense", [[slot, ni, "y_ft", depth]]))
        plan["cpu_calls"].append({"outer": 618, "record": drow.record_index, "play": 591, "formation": drow.formation_index, "donor_record": None})
        plan["formations"].append({"mode": "append", "target": 163, "donor": 0, "name": "Astra I Pro", "positions": [[6, v, -600, 0] for v in range(3)]})
        offense = splb.read_book(INDEX, 259)
        empty = next(r.record_index for r in offense.records if not r.entries)
        plan["cpu_calls"].append({"outer": 259, "record": empty, "play": 586, "formation": 163, "donor_record": 0})
        built = build_design(INDEX, plan)
        self.assertEqual(set(built.entries), {180, 259, 618})
        for receipt in built.report["resources"]:
            self.assertTrue(receipt["h7a_round_trip_exact"])
            self.assertEqual(receipt["overlapping_matches"], 0)
            self.assertGreaterEqual(receipt["free_bytes"], 0)
        self.assertEqual(built.report["design"]["counts_after"][:2], [164, 592])
        self.assertEqual(sha(read_resource(INDEX, 180).body), c.MASTER_SHA256)
        with patch("apf_texture_patch._optimal_binary", return_value=None):
            portable = build_design(INDEX, plan)
        self.assertEqual(set(portable.entries), {180, 259, 618})
        self.assertTrue(all(r["free_bytes"] >= 0 for r in portable.report["resources"]))
        print("SIX_PLAY_FORMATION_PORTABLE", json.dumps(portable.report["resources"], sort_keys=True))
        print("SIX_PLAY_FORMATION_BUILD", json.dumps(built.report, sort_keys=True))

    def test_13_spare_formation_records_fit(self):
        plan = empty_plan(self.resource.body)
        plan["formations"] = [{"mode": "append", "target": 163 + i, "donor": 0, "name": f"Astra Formation {i + 1}", "positions": []} for i in range(13)]
        result = compile_design(self.resource.body, plan)
        self.assertEqual(len(c.Book.from_bytes(result.replacement).formations), 176)
        _, receipt = pack_resource(self.resource, result.replacement)
        self.assertGreaterEqual(receipt["free_bytes"], 0)

    def test_fixed_budget_and_compression_fallback(self):
        _, receipt = pack_resource(self.resource, self.resource.body)
        if receipt["strategy"] == "optimal":
            self.assertEqual(receipt["free_bytes"], 2522)
        with patch("apf_texture_patch._optimal_binary", return_value=None):
            _, portable = pack_resource(self.resource, self.resource.body)
        self.assertGreaterEqual(portable["free_bytes"], 0)
        small = replace(self.resource, entry=replace(self.resource.entry, size=200))
        with self.assertRaisesRegex(ValidationError, "allocation bytes"):
            pack_resource(small, self.resource.body)


if __name__ == "__main__":
    unittest.main()
