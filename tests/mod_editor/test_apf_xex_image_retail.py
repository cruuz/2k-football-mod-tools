"""Optional local retail proof. Reads inputs; writes only authored patch TOML.

Set APF_RETAIL_XEX and APF_RETAIL_TU to user-owned files. Missing inputs cause
precise skips; executables, decoded images and update bytes are never fixtures.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_xex as x
from mod_editor.core import apf2k8_playcall_patch as p

XEX = Path(os.environ.get("APF_RETAIL_XEX", "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", "/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082"))
XEX_SHA = "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"


class RetailImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not XEX.is_file():
            raise unittest.SkipTest(f"Retail APF default.xex absent: {XEX}; set APF_RETAIL_XEX to your owned Xbox 360 executable")
        cls.xex = XEX.read_bytes()
        if hashlib.sha256(cls.xex).hexdigest() != XEX_SHA:
            raise AssertionError("APF_RETAIL_XEX exists but is not the pinned retail BASE executable")
        started = time.monotonic()
        cls.image, cls.receipt = x.decode_xex(cls.xex)
        cls.seconds = time.monotonic() - started

    def test_retail_base_sha_and_export(self):
        self.assertEqual(hashlib.sha256(self.image).hexdigest(), p.PROFILES[0].sha256)
        self.assertEqual(self.receipt["window_size"], 32768)
        self.assertEqual(self.receipt["lzx_bytes"], 37717546)
        self.assertEqual(len(self.image), p.IMAGE_SIZE)
        self.assertGreater(self.receipt["compressed_blocks_sha1_verified"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            source = {"input_paths": [str(XEX)], "derivation": self.receipt, "source_kind": "game_folder"}
            receipt = p.export_patch(p.compile_patch(self.image), Path(tmp) / "base.patch.toml", source)
            self.assertTrue(receipt["toml_reparsed"])
            self.assertEqual(receipt["module_hash"], "5447E5428AA2D52A")
            self.assertEqual(receipt["status"], "unwitnessed")
        self.assertEqual(hashlib.sha256(XEX.read_bytes()).hexdigest(), XEX_SHA)
        print(f"BASE: {self.receipt}; decode_seconds={self.seconds:.2f}", flush=True)

    def test_installed_title_update_sha_and_export(self):
        if not TU.is_file():
            self.skipTest(f"Retail APF TU 1.1 content absent: {TU}; set APF_RETAIL_TU to your installed content file")
        self.assertEqual(x.discover_title_update(XEX.parent, configured=TU), TU)
        payload = TU.read_bytes()
        image, proof = x.reconstruct_tu(self.image, self.xex, payload)
        self.assertEqual(hashlib.sha256(image).hexdigest(), p.PROFILES[1].sha256)
        self.assertEqual(proof["delta_records"], 3779)
        self.assertEqual(proof["delta_blocks_sha1_verified"], 12)
        self.assertEqual(proof["stfs_data_blocks_verified"], 191)
        with tempfile.TemporaryDirectory() as tmp:
            source = {"input_paths": [str(XEX), str(TU)], "derivation": proof, "source_kind": "game_folder"}
            receipt = p.export_patch(p.compile_patch(image), Path(tmp) / "tu.patch.toml", source)
            self.assertTrue(receipt["toml_reparsed"])
            self.assertEqual(receipt["module_hash"], "CEA825F7C2012F5A")
        self.assertEqual(TU.read_bytes(), payload)
        print(f"TU 1.1: {proof}", flush=True)


if __name__ == "__main__":
    unittest.main()
