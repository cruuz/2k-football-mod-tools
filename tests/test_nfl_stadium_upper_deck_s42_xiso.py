from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_upper_deck_s42_xiso_patch as writer  # noqa: E402
import nfl_stadium_upper_deck_s42_xiso_verify as verifier  # noqa: E402


RUNTIME = ROOT / "reports/assets/nfl2k5_group36_s42_xemu_runtime_positive.v2.json"
MANIFEST = ROOT / "build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/s42-workflow.json"


class UpperDeckS42XisoTests(unittest.TestCase):
    def test_both_paths_accept_exact_runtime_authority(self) -> None:
        writer_path, writer_value = writer.load_runtime_authority(RUNTIME)
        verifier_path, verifier_value = verifier.load_runtime_authority(RUNTIME)
        self.assertEqual(writer_path, verifier_path)
        self.assertEqual(writer_value, verifier_value)
        self.assertEqual(writer_value["schema"], writer.RUNTIME_SCHEMA)
        self.assertTrue(writer_value["claims"]["target_outer_loaded_proved"])
        self.assertEqual(
            writer_value["runs"]["control"]["artifacts"]["xiso"]["sha256"],
            writer.SOURCE_XISO_SHA256,
        )

    def test_runtime_authority_hash_and_semantics_fail_closed(self) -> None:
        value = json.loads(RUNTIME.read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = root / "changed.json"
            changed.write_bytes(writer.canonical_json(value))
            with mock.patch.object(writer, "RUNTIME_SHA256", "0" * 64):
                with self.assertRaisesRegex(writer.UpperDeckS42XisoError, "size or SHA"):
                    writer.load_runtime_authority(changed)
            with mock.patch.object(verifier, "RUNTIME_SHA256", "0" * 64):
                with self.assertRaisesRegex(verifier.UpperDeckS42XisoVerifyError,
                                            "size or SHA"):
                    verifier.load_runtime_authority(changed)

            value["claims"]["target_outer_loaded_proved"] = False
            payload = writer.canonical_json(value)
            changed.write_bytes(payload)
            digest = __import__("hashlib").sha256(payload).hexdigest()
            with (
                mock.patch.object(writer, "RUNTIME_SIZE", len(payload)),
                mock.patch.object(writer, "RUNTIME_SHA256", digest),
            ):
                with self.assertRaisesRegex(writer.UpperDeckS42XisoError,
                                            "does not pin"):
                    writer.load_runtime_authority(changed)

    def test_transport_ledgers_are_independent_and_equal(self) -> None:
        before = bytes(range(32))
        after = bytearray(before)
        after[0] = 99
        after[9] = 98
        after[10] = 97
        with (
            mock.patch.object(writer, "SPAN_SIZE", 32),
            mock.patch.object(verifier, "SPAN_SIZE", 32),
        ):
            self.assertEqual(writer._ledger(before, bytes(after)),
                             verifier.ledger(before, bytes(after)))

    def test_checked_manifest_preserves_diagnostic_and_false_new_runtime_claims(self) -> None:
        raw = MANIFEST.read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, verifier.canonical_json(value))
        self.assertEqual(value["schema"], verifier.MANIFEST_SCHEMA)
        self.assertTrue(value["claims"]["diagnostic_only"])
        self.assertTrue(value["claims"]["s42_routing_and_xbe_preserved"])
        self.assertTrue(value["claims"]["source_s42_target_outer_loaded_proved"])
        self.assertFalse(value["claims"]["xemu_boot_proved"])
        self.assertFalse(value["claims"]["xemu_changed_count_visibility_proved"])
        self.assertFalse(value["claims"]["retail_signed_executable_chain_preserved"])

    def test_independent_verifier_does_not_import_s42_writer(self) -> None:
        source = (ROOT / "tools/nfl_stadium_upper_deck_s42_xiso_verify.py").read_text()
        self.assertNotIn("import nfl_stadium_upper_deck_s42_xiso_patch", source)
        self.assertNotIn("from nfl_stadium_upper_deck_s42_xiso_patch", source)


if __name__ == "__main__":
    unittest.main()
