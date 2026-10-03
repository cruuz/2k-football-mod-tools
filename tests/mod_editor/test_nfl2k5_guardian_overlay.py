"""Standalone integrity, record ownership, composition and manifest proofs."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_guardian_overlay as g
from mod_editor.core import nfl2k5_player_tags as tags
from mod_editor.core import nfl2k5_roster_records as records
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_depth_locks as locks
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))/"ESPN NFL 2K5 (USA)"
XBE = EXTRACTION/"default.xbe"


def repin(buf):
    for s in _sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = section_digest(buf, s)
    return bytes(buf)


def roster():
    body = bytearray(tags.BODY_SIZE)
    body[12:16] = b"ROST"
    struct.pack_into("<I", body, 16, 17)
    for pool, count, start in (("primary", 2, 0x100), ("secondary", 1, 0x200)):
        size_at, ptr_at = tags.POOL_FIELDS[pool]
        struct.pack_into("<I", body, size_at, count)
        struct.pack_into("<i", body, ptr_at, start-ptr_at+1)
        for i in range(count):
            at = start+0x54*i
            body[at+0x52:at+0x54] = b"\xff\xde"
    return bytes(body)


class ContractTests(unittest.TestCase):
    def test_bit_is_disjoint_and_all_adjacent_bits_roundtrip(self):
        self.assertEqual(g.RECORD_BIT << 8 & (abilities.ABILITY_MASK | locks.LOCK_MASK | 0x100), 0)
        for byte in range(256):
            record = bytes(0x52)+bytes((0xff,byte))
            for selected in (True,False):
                after = g.set_record_selected(record, selected)
                self.assertEqual(after[:0x53], record[:0x53])
                self.assertEqual(after[0x53] & ~g.RECORD_BIT, byte & ~g.RECORD_BIT)
                self.assertEqual(g.record_selected(after), selected)
                self.assertEqual(g.set_record_selected(after, selected), after)
        with self.assertRaises(ValueError): g.set_record_selected(b"", True)
        with self.assertRaises(ValueError): g.set_record_selected(bytes(84), 1)

    def test_pinned_selection_and_star_writer_compose_both_orders(self):
        body = roster()
        selection = dict(pool="primary", index=1, record_sha256=hashlib.sha256(body[0x154:0x1a8]).hexdigest())
        selected, receipt = g.apply_roster_body(body, [selection])
        self.assertEqual(receipt["selected"], 1)
        self.assertTrue(selected[0x154+0x53] & g.RECORD_BIT)
        self.assertEqual(g.apply_roster_body(selected, [selection])[0], selected)
        tagged = tags.apply_body(selected, [0])[0]
        self.assertEqual([tagged[p.offset+0x53] & ~1 for p in tags.parse_body(tagged).players],
                         [selected[p.offset+0x53] & ~1 for p in tags.parse_body(selected).players])
        # A pinned player whose neighboring attributes changed must be refreshed.
        with self.assertRaisesRegex(ValueError, "provenance"):
            g.apply_roster_body(tags.apply_body(body,[1])[0], [selection])
        tag_first = tags.apply_body(body, [0])[0]
        pin = {**selection, "record_sha256":hashlib.sha256(tag_first[0x154:0x1a8]).hexdigest()}
        self.assertEqual(g.apply_roster_body(tag_first, [pin])[0], tagged)
        self.assertFalse(any(g.record_selected(g.apply_roster_body(selected, [])[0][p.offset:p.offset+84])
                             for p in tags.parse_body(body).players))
        for bad in ([selection, selection], [{**selection,"index":99}], [{**selection,"record_sha256":"0"*64}]):
            with self.assertRaises(ValueError): g.apply_roster_body(body, bad)

    def test_budget_and_fail_closed_public_contract(self):
        self.assertLessEqual(g.CODE_SIZE, 2048)
        self.assertEqual(g.REQUESTS, ((g.OWNER,"code",g.CODE_SIZE,16),))
        rows=json.loads((ROOT/"tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(r) for r in rows if r[0]==g.OWNER], list(g.REQUESTS))
        self.assertEqual([r for r in g.space.dormant_union() if r[0]==g.OWNER], list(g.REQUESTS))
        g.space.plan(rows)
        for blob in (b"", b"XBEH"+bytes(5000)):
            self.assertEqual(g.status(blob), "foreign")
            with self.assertRaises(ValueError): g.apply(blob)
        with self.assertRaises(ValueError): g.code_for(0x14da000, 1)


@unittest.skipUnless(XBE.is_file(), "retail USA XBE evidence absent")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=XBE.read_bytes()
        cls.patched,cls.receipt=g.apply(cls.retail)

    def test_default_explicit_off_and_replay(self):
        self.assertEqual(g.status(self.retail),"retail")
        self.assertEqual(g.status(self.patched),"applied")
        self.assertEqual(g.apply(self.patched)[0],self.patched)
        off,_=g.apply(self.retail,guardian_everyone_practice=False)
        self.assertFalse(g.read_settings(off)["guardian_everyone_practice"])
        self.assertEqual(g.apply(off)[0],off)
        with self.assertRaises(ValueError):g.apply(off,guardian_everyone_practice=True)
        for s in _sections(self.patched):self.assertEqual(s.stored_digest,section_digest(self.patched,s))

    def test_repinned_foreign_code_dependencies_and_mixed_hooks_refuse(self):
        image=XbeImage(self.patched);a=g.allocation(self.patched)
        for va in [a["va"],a["va"]+g.assembly.LABELS["config"],a["va"]+a["size"]-1]+[va for va,_ in g.HOOKS.values()]+[va for va,_,_ in g.GUARDS]:
            bad=bytearray(self.patched);bad[image.offset(va)]^=1;before=repin(bad)
            self.assertEqual(g.status(before),"foreign",hex(va))
            with self.assertRaises(ValueError):g.apply(before)
        for name,(va,raw) in g.HOOKS.items():
            bad=bytearray(self.patched);at=image.offset(va,len(raw));bad[at:at+len(raw)]=raw
            with self.assertRaises(ValueError):g.apply(repin(bad))

    def test_recorded_complete_hooks_and_allocation(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder=Recorder(self.retail)
        recorder.observe(g,"apply",self.retail,self.patched,self.receipt)
        rows=recorder.finish(self.patched)
        for va,before in g.HOOKS.values():
            self.assertTrue(any(r["owner"]==g.OWNER and int(r["start"],0)==va and r["size"]==len(before) for r in rows))
        a=g.allocation(self.patched)
        self.assertTrue(any(r["owner"]==g.OWNER and int(r["start"],0)==a["va"] and r["size"]==a["size"] for r in rows))

    def test_retail_star_tail_does_not_import_anniversary_dependencies(self):
        import builtins
        original_import = builtins.__import__

        def without_moments(name, globals=None, locals=None, fromlist=(), level=0):
            if "nfl2k5_espn25_more_moments" in name or "nfl2k5_espn25_more_moments" in (fromlist or ()):
                raise AssertionError("retail star tail must not load Anniversary dependencies")
            return original_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=without_moments):
            self.assertEqual(g.status(self.retail), "retail")
            self.assertEqual(g.status(self.patched), "applied")
            self.assertEqual(g.apply(self.patched)[0], self.patched)

    def test_anniversary_star_copy_and_guardian_compose_both_orders_and_replay(self):
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        allocated, _ = g.space.apply(self.retail, g.REQUESTS + moments.REQUESTS, scaleout=True)
        for variant, owner in (("shipped", moments), ("manifest_probe", moments.Probe)):
            with self.subTest(variant=variant):
                guardian_first, _ = g.apply(allocated)
                guardian_first, _ = owner.apply(guardian_first)
                moments_first, _ = owner.apply(allocated)
                moments_first, _ = g.apply(moments_first)
                self.assertEqual(guardian_first, moments_first)
                self.assertEqual(g.status(guardian_first), "applied")
                self.assertEqual(owner.status(guardian_first), "applied")
                self.assertEqual(g.apply(guardian_first)[0], guardian_first)
                self.assertEqual(owner.apply(guardian_first)[0], guardian_first)

    def test_anniversary_guard_normalization_rejects_foreign_hooks_code_and_neighbors(self):
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        allocated, _ = g.space.apply(self.retail, g.REQUESTS + moments.REQUESTS, scaleout=True)
        for variant, owner in (("shipped", moments), ("manifest_probe", moments.Probe)):
            both, _ = g.apply(allocated)
            both, _ = owner.apply(both)
            image = XbeImage(both)
            code, _ = moments.allocations(both)
            requests = g.space._read_scale_directory(both)
            for label, va in (
                ("star jump target", moments.STAR_VA + 1),
                ("owned star code", code["va"] + moments.STAR_OFFSET),
                ("other owned code", code["va"]),
                ("owned team table", code["va"] + moments.TABLE_OFFSET),
                ("before star hook", moments.STAR_VA - 1),
                ("after star hook", moments.STAR_VA + len(bytes.fromhex(moments.STAR_RETAIL))),
            ):
                with self.subTest(variant=variant, label=label):
                    bad = bytearray(both)
                    bad[image.offset(va)] ^= 1
                    if code["va"] <= va < code["va"] + code["size"]:
                        # Deliberately reseal the malformed fixture: rejection must
                        # inspect companion code, not just its previous checksum.
                        g.space._seal_scaleout(bad, requests)
                    bad = repin(bad)
                    self.assertEqual(g.status(bad), "foreign")
                    with self.assertRaises(ValueError):
                        g.apply(bad)

    def test_anniversary_star_hook_and_owned_code_versions_must_match(self):
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        allocated, _ = g.space.apply(self.retail, g.REQUESTS + moments.REQUESTS, scaleout=True)
        for variant, owner in (("shipped", moments), ("manifest_probe", moments.Probe)):
            current, _ = g.apply(allocated)
            current, _ = owner.apply(current)
            image = XbeImage(current)
            code, _ = moments.allocations(current)
            requests = g.space._read_scale_directory(current)
            star_size = moments.TABLE_OFFSET - moments.STAR_OFFSET
            star_at = image.offset(code["va"] + moments.STAR_OFFSET, star_size)
            hook_retail = bytes.fromhex(moments.STAR_RETAIL)
            hook_at = image.offset(moments.STAR_VA, len(hook_retail))
            for current_body in (False, True):
                for current_hook in (False, True):
                    with self.subTest(variant=variant, current_body=current_body, current_hook=current_hook):
                        candidate = bytearray(current)
                        if not current_body:
                            candidate[star_at:star_at + star_size] = b"\xcc" * star_size
                        if not current_hook:
                            candidate[hook_at:hook_at + len(hook_retail)] = hook_retail
                        g.space._seal_scaleout(candidate, requests)
                        candidate = repin(candidate)
                        if current_body == current_hook:
                            self.assertEqual(owner.status(candidate), "applied")
                            self.assertEqual(owner.apply(candidate)[0], candidate)
                            self.assertEqual(g.status(candidate), "applied")
                            self.assertEqual(g.apply(candidate)[0], candidate)
                        else:
                            self.assertEqual(owner.status(candidate), "foreign")
                            with self.assertRaises(ValueError):
                                owner.apply(candidate)
                            if current_hook:
                                self.assertEqual(g.status(candidate), "foreign")
                                with self.assertRaises(ValueError):
                                    g.apply(candidate)


if __name__ == "__main__": unittest.main()
