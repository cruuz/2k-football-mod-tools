"""Standalone evidence audit, owner composition and foreign-state refusals."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_catch_slider as catch
from mod_editor.core import nfl2k5_coverage_slider as coverage
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_zone_drop as drop
from mod_editor.core import nfl2k5_zone_facing as facing
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256, ReservationManifest, DEFAULT_MANIFEST
from tests.mod_editor.test_nfl2k5_zone_drop import XBE, repin


class PublicTests(unittest.TestCase):
    def test_bad_inputs_refuse_without_an_affirmative_report(self):
        for payload in (None, b"", b"XBEH", bytes(4096), bytearray(4096)):
            with self.subTest(payload_type=type(payload)), self.assertRaises(ValueError):
                facing.assess(payload)

    def test_file_read_is_bounded_and_closes_even_on_failure(self):
        class Reader(io.BytesIO):
            requested = []

            def read(self, size=-1):
                self.requested.append(size)
                return super().read(size)

        stream = Reader(b"XBEH")
        with patch.object(Path, "open", return_value=stream):
            self.assertEqual(facing.read_xbe(Path("synthetic.xbe")), b"XBEH")
        self.assertEqual(stream.requested, [space.SCALE_FILE_SIZE + 1])
        self.assertTrue(stream.closed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "oversized.xbe"
            with path.open("wb") as output:
                output.truncate(space.SCALE_FILE_SIZE + 1)
            with self.assertRaisesRegex(ValueError, "exceeds"):
                facing.read_xbe(path)
            path.unlink()  # no reader survives refusal, including on Windows

    def test_cli_refuses_and_never_offers_a_patch_operation(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(facing.main(["--xbe", "/missing/deep-zone-default.xbe"]), 2)
        self.assertIn("evidence refused", stderr.getvalue())
        self.assertFalse(hasattr(facing, "apply"))
        self.assertFalse(hasattr(facing, "REQUESTS"))


@unittest.skipUnless(XBE.is_file(), f"pinned USA default.xbe absent: {XBE}")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = facing.read_xbe(XBE)
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise AssertionError("Retail evidence hash differs from pinned USA executable")
        cls.base = space.apply(cls.retail, drop.REQUESTS + spy.REQUESTS + coverage.REQUESTS, scaleout=True)[0]
        cls.composed = coverage.apply(spy.apply(drop.apply(cls.base)[0])[0])[0]

    def test_scope_report_on_retail_and_composed_images(self):
        for payload in (self.retail, self.base, self.composed):
            digest = hashlib.sha256(payload).hexdigest()
            result = facing.assess(payload)
            self.assertEqual(result["input_sha256"], digest)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), digest)
            self.assertFalse(result["patch_available"])
            self.assertFalse(result["runtime_witnessed"])
            self.assertEqual([r["implementation"] for r in result["tiers"]], ["shipped", "deferred", "deferred", "deferred"])
            self.assertEqual(result["changed_bytes"], 0)
            self.assertEqual(result["requests"], [])
            self.assertEqual(result["reaction"]["angle_knots"][0]["angle_units"], 0)
            self.assertAlmostEqual(result["reaction"]["angle_knots"][0]["contribution"], .3)
            self.assertEqual(result["reaction"]["angle_knots"][-1]["angle_units"], 32768)
            self.assertEqual(facing.assess(payload), result)

    def test_spy_and_drop_compose_in_both_orders_including_custom_cap(self):
        for cap in (.6, .84):
            left = spy.apply(drop.apply(self.base, cap=cap)[0])[0]
            right = drop.apply(spy.apply(self.base)[0], cap=cap)[0]
            self.assertEqual(left, right)
            report = facing.assess(left)
            self.assertEqual(report["states"]["initial_drop"], "applied")
            self.assertEqual(report["states"]["qb_spy"], "applied")
            image = XbeImage(left)
            code_va = spy.allocations(left)["code"]["va"]
            for _name, va, old, new in spy.sites(code_va):
                self.assertEqual(image.read(va, len(old)), new)
            self.assertTrue(all(row["owner"] == spy.OWNER for row in report["callbacks"]))
            self.assertEqual(drop.apply(left)[0], left)
            self.assertEqual(spy.apply(left)[0], left)

    def test_reaction_owners_are_recognized_independently(self):
        for source in (self.retail, self.composed):
            patched = catch.apply(source)[0]
            before, after = facing.assess(source), facing.assess(patched)
            self.assertEqual(before["reaction"], after["reaction"])
            self.assertEqual(after["states"]["catch"], "applied")
            self.assertEqual(before["callbacks"], after["callbacks"])
            before_image, after_image = XbeImage(source), XbeImage(patched)
            self.assertEqual(before_image.read(0x1F4250, 265), after_image.read(0x1F4250, 265))

    def test_foreign_facing_and_mixed_callback_dependencies_refuse(self):
        image = XbeImage(self.composed)
        targets = [(va, size) for va, size, _ in facing.GUARDS]
        targets += [(facing.CONVERSION_VA, len(facing.CONVERSION_BYTES)), (0x1A5790, 6), (0x1A5090, 6),
                    (0x1F4250, 265), (0x50B330, 40), (drop.HOOK_VA, 5)]
        for va, size in targets:
            for index in (0, size - 1):
                bad = bytearray(self.composed)
                bad[image.offset(va) + index] ^= 1
                bad = repin(bad)  # valid section digests must not bless foreign instructions
                with self.subTest(va=hex(va), index=index), self.assertRaises(ValueError):
                    facing.assess(bad)
        # Recognizing a jump opcode alone would accept this mixed installation.
        for name in ("zone_first", "zone_later"):
            va, old = spy.HOOKS[name]
            bad = bytearray(self.composed)
            offset = image.offset(va)
            bad[offset:offset + len(old)] = old
            with self.assertRaisesRegex(ValueError, "qb_spy"):
                facing.assess(repin(bad))

    def test_owned_code_corruption_refuses_even_if_resealed(self):
        sites = spy.allocations(self.base)
        code = bytearray(spy.code_for(sites["code"]["va"], sites["data"]["va"], sites["read_only"]["va"]))
        code[0] ^= 1
        bad = space.install_code(self.base, spy.OWNER, bytes(code))[0]
        bad = space.install_read_only(bad, spy.OWNER, spy.compile_intent_table()[0])[0]
        image, buf = XbeImage(bad), bytearray(bad)
        for _name, va, old, new in spy.sites(sites["code"]["va"]):
            offset = image.offset(va)
            buf[offset:offset + len(old)] = new
        bad = repin(buf)
        self.assertEqual(space.status(bad), "applied")
        with self.assertRaisesRegex(ValueError, "qb_spy"):
            facing.assess(bad)

    def test_existing_manifest_assigns_callbacks_to_spy_and_drop_call_to_drop(self):
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, XbeImage(self.retail))
        for name in ("zone_first", "zone_later"):
            va, old = spy.HOOKS[name]
            overlaps = manifest.overlaps(va, va + len(old))
            self.assertTrue(overlaps, hex(va))
            self.assertEqual(manifest.overlaps(va, va + len(old), exclude_owner=spy.OWNER), [])
        overlaps = manifest.overlaps(drop.HOOK_VA, drop.CONTINUE_VA)
        self.assertTrue(overlaps)
        self.assertEqual(manifest.overlaps(drop.HOOK_VA, drop.CONTINUE_VA, exclude_owner=drop.OWNER), [])

    def test_cli_emits_read_only_evidence_json(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(facing.main(["--xbe", str(XBE)]), 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["schema"], facing.SCHEMA)
        self.assertFalse(report["patch_available"])
        self.assertEqual(report["input_sha256"], RETAIL_SHA256)


if __name__ == "__main__":
    unittest.main()
