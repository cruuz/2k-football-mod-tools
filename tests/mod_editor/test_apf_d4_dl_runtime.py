"""Retail-free branch guards plus optional owned BASE/TU native d4 witnesses."""
import json
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import apf2k8_charge_abilities as charge
from mod_editor.core import apf2k8_fourth_down as fourth
from mod_editor.core import apf2k8_situation_mask as situation
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.apf2k8_playcall_patch import check_image
from mod_editor.core.errors import ValidationError
from tools.apf_d4_dl_runtime_probe import (
    branch_target, native_runtime_proof, shell_metadata,
)


class BranchTests(unittest.TestCase):
    def test_relative_forward_backward_and_absolute(self):
        cases = ((0x48000011, 0x82000010), (0x4BFFFFF1, 0x81FFFFF0),
                 (0x48001003, 0x1000), (0x4BFFF003, 0xFFFFF000))
        for word, expected in cases:
            with self.subTest(word=word):
                self.assertEqual(branch_target(struct.pack(">I", word), 0x82000000), expected)

    def test_reject_non_branch(self):
        with self.assertRaises(ValueError):
            branch_target(struct.pack(">I", 0x60000000), 0x82000000)

    def test_foreign_metadata_input_rejected(self):
        with self.assertRaises(ValidationError):
            shell_metadata(bytes(256))


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(str(exc))
        names = ("APF_D4_BASE_PE", "APF_D4_TU_PE", "APF_RETAIL_INDEX")
        paths = [Path(os.environ[name]) if os.environ.get(name) else None for name in names]
        if not all(path and path.is_file() for path in paths):
            raise unittest.SkipTest("Set APF_D4_BASE_PE, APF_D4_TU_PE and APF_RETAIL_INDEX to owned pinned inputs")
        cls.images = [path.read_bytes() for path in paths[:2]]
        cls.master = read_master_play_body(paths[2])

    def test_native_shell_names_and_role_tables_both_profiles(self):
        expected = [[None, "Base Shell", "Safety Weak", "Safety Strong", "Cover 1 Shell", "Cover 1 Shell"],
                    [None, "Cover 2 Shell", "Cover 3 Weak Shell", "Cover 3 Strong Shell", "Cover 1 Shell", "Cover 1 Shell"]]
        for image in self.images:
            metadata = shell_metadata(image)
            self.assertEqual(metadata["messages_by_call_flag_bank"], expected)
            self.assertEqual(metadata["alignment_variant_role_order"], ["CB", "FS", "SS"])
            self.assertEqual(metadata["alignment_variants_by_call_flag_bank"][0][2], [1, 1, 1])
            self.assertEqual(metadata["alignment_variants_by_call_flag_bank"][1][2], [1, 2, 2])

    def test_actual_initializer_shell_and_d3_patch_noninterference(self):
        receipts = []
        for image in self.images:
            stock = native_runtime_proof(image, self.master)
            profile = check_image(image)
            charge_patch = charge.PatchDocument(profile, True)
            charge.verify_image(image, charge_patch)
            masks = {"O-ManBlock": [[14] for _ in range(12)]}
            rows = {"O-ManBlock": [{"6": 10} for _ in range(12)]}
            weights = {"O-ManBlock": [{"14": 0.25, "15": 4.0} for _ in range(13)]}
            mask_patch = situation.compile_patch(image, masks, rows, weights)
            fourth_patch = fourth.PatchDocument(profile, fourth.Thresholds(
                short_yards=3, own_half_limit=75, fallback_threshold=1), enabled=True)
            fourth.verify_image(image, fourth_patch)
            patches = (*charge_patch.words, *mask_patch.words, *fourth_patch.words)
            patched = native_runtime_proof(image, self.master, patches)
            for field in ("initializer_cases", "shell_role_cases", "base_front_defense_start_displacements"):
                self.assertEqual(stock[field], patched[field], field)
            self.assertEqual(stock["initializer_slot_checks"], 132)
            self.assertEqual(stock["cpu_lane_checks"], 144)
            self.assertEqual(stock["shell_role_checks"], 84)
            self.assertEqual(stock["base_front_defense_start_displacements"], [[0.0, 0.0]] * 4)
            self.assertNotEqual(stock["executed_image_sha256"], patched["executed_image_sha256"])
            for case in stock["shell_role_cases"]:
                if case["role"] in ("DE", "DT", "ILB", "OLB"):
                    self.assertEqual(case["runtime_flags_after"], case["runtime_flags_before"])
                    self.assertFalse(case["refresh_requested"])
                    self.assertEqual(len(case["writes"]), 1)  # D+C4 only
            for case in stock["initializer_cases"]:
                if case["second_play"] in (278, 283):
                    self.assertEqual([row["selected_play"] for row in case["slots"][:4]], [277] * 4)
                    expected = [1, 0, 3, 2] if int(case["call_flags"], 16) & 4 else [0, 1, 2, 3]
                    self.assertEqual([row["selected_slot"] for row in case["slots"][:4]], expected)
            receipts.extend([stock, patched])
        if os.environ.get("APF_D4_DL_RECEIPT"):
            target = Path(os.environ["APF_D4_DL_RECEIPT"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"runs": receipts}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
