#!/usr/bin/env python3
"""Negative and determinism tests for the capability registry contract."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import validate_registry as registry


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = registry.load_and_validate(registry.DEFAULT_REGISTRY)

    def assert_rejected(self, mutate) -> None:
        candidate = copy.deepcopy(self.data)
        mutate(candidate)
        with self.assertRaises(registry.RegistryError):
            registry.validate_data(candidate, check_files=False)

    def test_canonical_roundtrip(self) -> None:
        canonical = json.dumps(self.data, indent=2, sort_keys=True) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "registry.json"
            path.write_text(canonical, encoding="utf-8")
            registry.load_and_validate(path, check_files=False)

    def test_duplicate_id_rejected(self) -> None:
        self.assert_rejected(lambda data: data["capabilities"].__setitem__(1, copy.deepcopy(data["capabilities"][0])))

    def test_missing_surface_rejected(self) -> None:
        def mutate(data):
            data["capabilities"] = [
                item for item in data["capabilities"]
                if not (item["game"] == "nfl2k5_xbox" and item["surface"] == "saves")
            ]
        self.assert_rejected(mutate)

    def test_runtime_claim_without_visible_status_rejected(self) -> None:
        def mutate(data):
            item = next(value for value in data["capabilities"] if value["classification"] == "runtime-proved")
            item["runtime"]["status"] = "not-tested"
        self.assert_rejected(mutate)

    def test_unsafe_gui_exposure_rejected(self) -> None:
        def mutate(data):
            item = next(value for value in data["capabilities"] if value["classification"] == "unsafe/deferred")
            item["gui"]["expose"] = True
        self.assert_rejected(mutate)

    def test_unknown_classification_rejected(self) -> None:
        self.assert_rejected(lambda data: data["capabilities"][0].__setitem__("classification", "maybe"))

    def test_missing_backend_file_rejected(self) -> None:
        candidate = copy.deepcopy(self.data)
        item = next(value for value in candidate["capabilities"] if value["backend"]["module"] is not None)
        item["backend"]["module"] = "tools/definitely_missing.py"
        item["backend"]["command"] = "python3 tools/definitely_missing.py"
        with self.assertRaises(registry.RegistryError):
            registry.validate_data(candidate, check_files=True)


if __name__ == "__main__":
    unittest.main()
