from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_qcow2_historical_chain_verify as verify


def qcow2_payload(backing: str, size: int = 3 * 65_536) -> bytes:
    payload = bytearray(size)
    encoded = backing.encode("utf-8")
    backing_offset = 512 if encoded else 0
    struct.pack_into(
        ">IIQIIQIIQQIIQ",
        payload,
        0,
        verify.QCOW_MAGIC,
        3,
        backing_offset,
        len(encoded),
        16,
        verify.QCOW_VIRTUAL_SIZE,
        0,
        1,
        65_536,
        131_072,
        1,
        0,
        0,
    )
    struct.pack_into(">QQQII", payload, 72, 0, 0, 0, 4, 112)
    payload[backing_offset:backing_offset + len(encoded)] = encoded
    return bytes(payload)


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


class HistoricalQcowChainTest(unittest.TestCase):
    def fixture(self, directory: Path, *, child_backing: str | None = None):
        base = directory / "missing-base.qcow2"
        child = directory / "child.qcow2"
        backing = str(base) if child_backing is None else child_backing
        child_payload = qcow2_payload(backing)
        child.write_bytes(child_payload)
        base_payload = qcow2_payload("")
        value = {
            "boundary": verify.EXPECTED_BOUNDARY,
            "nodes": [
                {
                    "backing": None,
                    "captured_path": str(base),
                    "id": "base",
                    "retained": False,
                    "sha256": hashlib.sha256(base_payload).hexdigest(),
                    "size": len(base_payload),
                },
                {
                    "backing": "base",
                    "captured_path": str(child),
                    "id": "child",
                    "retained": True,
                    "sha256": hashlib.sha256(child_payload).hexdigest(),
                    "size": len(child_payload),
                },
            ],
            "schema": verify.SCHEMA,
        }
        spec = directory / "chain.json"
        spec_payload = canonical(value)
        spec.write_bytes(spec_payload)
        return base, child, spec, value, hashlib.sha256(spec_payload).hexdigest()

    def test_exact_child_and_absent_base_are_historical_not_replayable(self):
        with tempfile.TemporaryDirectory() as raw:
            base, _child, spec, _value, spec_sha = self.fixture(Path(raw))
            self.assertFalse(base.exists())
            result = verify.verify_chain(
                root=ROOT, spec_path=spec, spec_sha256=spec_sha, leaf="child"
            )
        self.assertEqual(result["base_status"], "missing")
        self.assertFalse(result["chain_complete"])
        self.assertFalse(result["guest_content_replayable"])
        self.assertFalse(result["historical_runtime_reexecuted"])
        self.assertEqual([row["id"] for row in result["layers"]], ["child", "base"])

    def test_child_byte_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            _base, child, spec, _value, spec_sha = self.fixture(Path(raw))
            payload = bytearray(child.read_bytes())
            payload[-1] ^= 1
            child.write_bytes(payload)
            with self.assertRaisesRegex(verify.ChainError, "SHA-256 differs"):
                verify.verify_chain(
                    root=ROOT, spec_path=spec, spec_sha256=spec_sha, leaf="child"
                )

    def test_backing_path_tamper_is_rejected_even_when_rehashed(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            base, child, spec, value, _spec_sha = self.fixture(
                directory, child_backing=str(directory / "other-base.qcow2")
            )
            self.assertFalse(base.exists())
            value["nodes"][1]["sha256"] = hashlib.sha256(child.read_bytes()).hexdigest()
            spec_payload = canonical(value)
            spec.write_bytes(spec_payload)
            with self.assertRaisesRegex(verify.ChainError, "backing pathname differs"):
                verify.verify_chain(
                    root=ROOT,
                    spec_path=spec,
                    spec_sha256=hashlib.sha256(spec_payload).hexdigest(),
                    leaf="child",
                )

    def test_wrong_file_at_missing_base_path_is_not_accepted_as_substitute(self):
        with tempfile.TemporaryDirectory() as raw:
            base, _child, spec, _value, spec_sha = self.fixture(Path(raw))
            base.write_bytes(bytes(3 * 65_536))
            with self.assertRaisesRegex(verify.ChainError, "SHA-256 differs"):
                verify.verify_chain(
                    root=ROOT, spec_path=spec, spec_sha256=spec_sha, leaf="child"
                )

    def test_hardlinked_child_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            _base, child, spec, _value, spec_sha = self.fixture(directory)
            (directory / "second-name.qcow2").hardlink_to(child)
            with self.assertRaisesRegex(verify.ChainError, "hard-linked"):
                verify.verify_chain(
                    root=ROOT, spec_path=spec, spec_sha256=spec_sha, leaf="child"
                )

    def test_symlinked_parent_of_child_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            real = directory / "real"
            real.mkdir()
            alias = directory / "alias"
            alias.symlink_to(real, target_is_directory=True)
            _base, child, spec, value, _spec_sha = self.fixture(real)
            value["nodes"][1]["captured_path"] = str(alias / child.name)
            spec_payload = canonical(value)
            spec.write_bytes(spec_payload)
            with self.assertRaisesRegex(verify.ChainError, "component is a symlink"):
                verify.verify_chain(
                    root=ROOT,
                    spec_path=spec,
                    spec_sha256=hashlib.sha256(spec_payload).hexdigest(),
                    leaf="child",
                )

    def test_nonfinite_json_constant_is_rejected(self):
        with self.assertRaisesRegex(verify.ChainError, "non-finite JSON constant"):
            verify.canonical_json(b'{"value":NaN}\n', "synthetic spec")


if __name__ == "__main__":
    unittest.main()
