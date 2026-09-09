from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_coverage_tuning as c
from mod_editor.core.errors import ValidationError


def synthetic_master() -> bytes:
    """Authored PLAY grammar, two plays sharing one of two invented nodes."""
    inv = c.inventory
    b = bytearray(inv.APF_BODY_SIZE)
    b[12:16] = b"YALP"
    struct.pack_into("<II", b, 16, 32, 0)
    b[32:40] = "mpb\0".encode("utf-16be")
    struct.pack_into(">4I", b, 0x34, 1, 2, 1, 2)
    cursor, offsets = inv.APF_STRING_BASE, []
    for name in ("MASTER", "Synthetic shape", "Left example", "Right example", "Test defense"):
        offsets.append(cursor)
        v = (name + "\0").encode("utf-16be")
        b[cursor:cursor + len(v)] = v
        cursor += len(v)
    def ptr(field, target):
        struct.pack_into(">i", b, field, target - field + 1)
    ptr(0x30, offsets[0])
    ptr(inv.APF_CATEGORY_BASE, offsets[4])
    ptr(inv.APF_FORMATION_BASE, offsets[1])
    for i in range(2):
        off = inv.APF_PLAY_BASE + i * inv.APF_PLAY_SIZE
        ptr(off, offsets[2 + i])
        for slot in range(11):
            field = off + 12 + slot * 8
            struct.pack_into(">I", b, field, 1 << 28)
            ptr(field + 4, inv.APF_ROUTE_BASE + (i + slot) % 2 * 8)
    # Invented bits exercise preservation of opcode/header/mode/F/G.
    struct.pack_into(">II", b, inv.APF_ROUTE_BASE, 0x0D13579B, 0x835AED64)
    struct.pack_into(">II", b, inv.APF_ROUTE_BASE + 8, 0x0E2468AC, 0x10203040)
    return bytes(b)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.body = synthetic_master()
        _, zones = c._parsed(self.body)
        self.pin = patch.object(c, "MASKED_MASTER_SHA256", c._masked_hash(self.body, zones))
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def test_exact_bit_contract_shared_uses_and_idempotence(self):
        edits = [c.ZoneEdit(0, -80, 30, 15, 9)]
        output, receipt = c.apply_geometry(self.body, edits)
        off = c.inventory.APF_ROUTE_BASE
        self.assertEqual(struct.unpack_from(">I", output, off + 4)[0], 0x305EED9F)
        self.assertEqual(output[:off + 4], self.body[:off + 4])
        self.assertEqual(output[off + 8:], self.body[off + 8:])
        self.assertEqual(len(receipt["affected_nodes"][0]["uses"]), 11)
        self.assertEqual({v["play_index"] for v in receipt["affected_nodes"][0]["uses"]}, {0, 1})
        again, report = c.apply_geometry(output, edits)
        self.assertEqual(again, output)
        self.assertEqual(report["changed_byte_count"], 0)
        self.assertEqual(c.apply_geometry(self.body, [])[0], self.body)

    def test_pin_rejects_other_data_even_on_noop(self):
        altered = bytearray(self.body)
        altered[c.inventory.APF_FORMATION_BASE + 20] ^= 1
        with self.assertRaisesRegex(ValidationError, "retail pin"):
            c.apply_geometry(bytes(altered), [])

    def test_preserved_mode_bit_and_unrequested_geometry_fail_verification(self):
        edits = [c.ZoneEdit(0, drop_depth_feet=31)]
        output, _ = c.apply_geometry(self.body, edits)
        for delta in (5, 6):
            corrupt = bytearray(output)
            corrupt[c.inventory.APF_ROUTE_BASE + delta] ^= 1
            with self.assertRaises(ValidationError):
                c.verify_geometry(self.body, bytes(corrupt), edits)

    def test_boundaries_and_independent_partial_update(self):
        for x, y, a, b in ((-128, -64, 0, 0), (127, 191, 15, 15)):
            out, _ = c.apply_geometry(self.body, [c.ZoneEdit(0, x, y, a, b)])
            self.assertEqual(c.inspect_zones(out)[0]["drop_depth_feet"], y)
        out, _ = c.apply_geometry(self.body, [c.ZoneEdit(0, lateral_extent_yards=2)])
        v = c.inspect_zones(out)[0]
        self.assertEqual((v["landmark_x_feet"], v["drop_depth_feet"], v["depth_extent_yards"]), (3, 26, 6))

    def test_bad_requests(self):
        for edit in (c.ZoneEdit(0), c.ZoneEdit(True, drop_depth_feet=1), c.ZoneEdit(-1, drop_depth_feet=1),
                     c.ZoneEdit(1, drop_depth_feet=1), c.ZoneEdit(99, drop_depth_feet=1),
                     c.ZoneEdit(0, 128), c.ZoneEdit(0, drop_depth_feet=-65),
                     c.ZoneEdit(0, lateral_extent_yards=16), c.ZoneEdit(0, depth_extent_yards=1.5),
                     c.ZoneEdit(0, drop_depth_feet=True)):
            with self.subTest(edit=edit), self.assertRaises(ValidationError):
                c.apply_geometry(self.body, [edit])
        with self.assertRaises(ValidationError):
            c.apply_geometry(self.body, [c.ZoneEdit(0, 0), c.ZoneEdit(0, 1)])
        for value in ({}, {"node_index": 0, "carry_distance": 9}, {"node_index": "0", "drop_depth_feet": 1}):
            with self.assertRaises(ValidationError):
                c.edit_from_mapping(value)

    def test_parser_rejects_chain_overrun_before_pins(self):
        b = bytearray(self.body)
        struct.pack_into(">I", b, c.inventory.APF_PLAY_BASE + 12, 15 << 28)
        with self.assertRaisesRegex(ValidationError, "chain exceeds"):
            c.apply_geometry(bytes(b), [])
        with self.assertRaises(ValidationError):
            c.apply_geometry(self.body[:-1], [])

    def test_shareable_profile_roundtrip_and_reject_ambiguous_json(self):
        edits = (c.ZoneEdit(0, drop_depth_feet=31),)
        payload = c.encode_profile(edits)
        self.assertEqual(c.decode_profile(payload), edits)
        self.assertNotIn(b"retail", payload)
        for bad in (b"{}", b"\xff", b'{"schema":1,"schema":2,"edits":[]}', b"[0]",
                    b'{"schema":"apf2k8_coverage_geometry_profile/v1","edits":[[]]}',
                    b'{"node_index":' + b'9' * 5000 + b'}'):
            with self.assertRaises(ValidationError):
                c.decode_profile(bad)

    def test_composition_recomputes_shared_uses_and_preserves_zone_pool(self):
        from mod_editor.core.apf2k8_playbook_route_writer import RouteCloneRequest
        edits = [c.ZoneEdit(0, drop_depth_feet=31)]
        tuned, _ = c.apply_geometry(self.body, edits)
        final, report = c.compose_geometry(self.body, edits, routes=[RouteCloneRequest(0, 0, 1, 0)])
        self.assertEqual(final[c.inventory.APF_ROUTE_BASE:c.inventory.APF_STRING_BASE],
                         tuned[c.inventory.APF_ROUTE_BASE:c.inventory.APF_STRING_BASE])
        self.assertEqual(len(report["affected_nodes"][0]["uses"]), 10)
        self.assertTrue(report["composition"]["final_play_reparsed"])


class RetailGeometryTests(unittest.TestCase):
    def test_retail_full_pack_rebuild(self):
        index = Path("/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A")
        if not index.is_file() or not index.with_name("0B").is_file():
            self.skipTest("APF US retail 0A/0B archive absent; fixed-allocation coverage rebuild requires both")
        source = c.read_master_play_body(index)
        self.assertEqual(hashlib.sha256(source).hexdigest(), c.MASTER_SHA256)
        self.assertEqual(len(c.inspect_zones(source)), 368)
        out, receipt = c.apply_geometry(source, [c.ZoneEdit(2983, drop_depth_feet=27)])
        self.assertEqual(receipt["changed_body_offsets"], [120833])
        self.assertEqual(c.apply_geometry(out, [c.ZoneEdit(2983, drop_depth_feet=27)])[0], out)
        entry, report = c.compile_outer_entry(index, [c.ZoneEdit(2983, drop_depth_feet=27)])
        self.assertEqual(len(entry), 57344)
        self.assertEqual(report["replacement_sha256"], hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    unittest.main()
