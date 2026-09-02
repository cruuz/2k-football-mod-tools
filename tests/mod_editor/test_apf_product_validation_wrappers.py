"""Hostile-input tests for the no-argument APF product validators."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import validate_apf_field_art_product as field_gate  # noqa: E402
import validate_apf_logocache_product as cache_gate  # noqa: E402


class NoArgumentProductValidationTests(unittest.TestCase):
    def test_fast_gates_validate_the_pinned_fixtures(self) -> None:
        self.assertEqual(field_gate.validate_fast()["schema"], "apf_field_art_verify/v1")
        self.assertEqual(
            cache_gate.validate_fast()["schema"],
            "apf_logocache_roundtrip_validation/v1",
        )

    def test_forged_evidence_is_refused_before_semantic_use(self) -> None:
        for gate in (field_gate, cache_gate):
            with self.subTest(gate=gate.__name__), tempfile.TemporaryDirectory() as temporary:
                forged = Path(temporary) / "forged.json"
                forged.write_bytes(gate.EVIDENCE.read_bytes() + b"\n")
                with self.assertRaisesRegex(gate.ProductValidationError, "hash differs"):
                    gate.validate_fast(forged)

    def test_duplicate_json_keys_fail_closed_even_with_a_matching_outer_pin(self) -> None:
        for gate in (field_gate, cache_gate):
            with self.subTest(gate=gate.__name__), tempfile.TemporaryDirectory() as temporary:
                forged = Path(temporary) / "duplicate.json"
                payload = b'{"schema":"first","schema":"second"}\n'
                forged.write_bytes(payload)
                with mock.patch.object(
                    gate, "EVIDENCE_SHA256", hashlib.sha256(payload).hexdigest()
                ):
                    with self.assertRaisesRegex(
                        gate.ProductValidationError, "duplicate key"
                    ):
                        gate._load_evidence(forged)

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks unavailable")
    def test_symlinked_evidence_is_refused(self) -> None:
        for gate in (field_gate, cache_gate):
            with self.subTest(gate=gate.__name__), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / "target.json"
                target.write_bytes(gate.EVIDENCE.read_bytes())
                link = root / "link.json"
                link.symlink_to(target)
                with self.assertRaisesRegex(
                    gate.ProductValidationError, "not a regular file"
                ):
                    gate.validate_fast(link)

    def test_deep_inputs_are_never_accepted_implicitly(self) -> None:
        self.assertEqual(field_gate.main(["--source-volume", "/missing"]), 1)
        self.assertEqual(cache_gate.main(["--source", "/missing"]), 1)
        self.assertEqual(field_gate.main(["--full-volume"]), 1)
        self.assertEqual(cache_gate.main(["--full-volume"]), 1)


if __name__ == "__main__":
    unittest.main()
