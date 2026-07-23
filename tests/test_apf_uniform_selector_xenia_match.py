#!/usr/bin/env python3
"""Focused tests for the APF selector runtime pose matcher."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_uniform_selector_xenia_match as matcher  # noqa: E402


class APFUniformSelectorXeniaMatchTests(unittest.TestCase):
    def _frame(
        self,
        path: Path,
        *,
        reference_color: tuple[int, int, int],
        evidence_color: tuple[int, int, int],
    ) -> None:
        image = Image.new("RGB", matcher.FRAME_SIZE, (8, 8, 8))
        draw = ImageDraw.Draw(image)
        for box in matcher.REFERENCE_BOXES:
            draw.rectangle(box, fill=reference_color)
        for box in matcher.EVIDENCE_BOXES:
            draw.rectangle(box, fill=evidence_color)
        image.save(path)

    def test_global_reference_minimum_is_selected_before_evidence_is_measured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            control_a = root / "control-000.png"
            control_b = root / "control-001.png"
            modified_a = root / "modified-000.png"
            modified_b = root / "modified-001.png"
            self._frame(control_a, reference_color=(20, 40, 60), evidence_color=(1, 2, 3))
            self._frame(control_b, reference_color=(80, 100, 120), evidence_color=(1, 2, 3))
            self._frame(modified_a, reference_color=(80, 100, 120), evidence_color=(230, 4, 5))
            self._frame(modified_b, reference_color=(22, 42, 62), evidence_color=(1, 2, 3))

            report, _control, _modified = matcher.match_frame_sets(
                [control_a, control_b], [modified_a, modified_b]
            )
            selected = report["selected"]
            self.assertEqual(Path(selected["control"]["path"]), control_b)
            self.assertEqual(Path(selected["modified"]["path"]), modified_a)
            self.assertEqual(
                selected["reference_metrics"]["mean_absolute_component_difference"], 0
            )
            self.assertGreater(
                selected["evidence_metrics"]["mean_absolute_component_difference"], 70
            )
            self.assertEqual(report["candidate_pair_count"], 4)
            search = report["localization_gate_search"]
            self.assertEqual(search["reference_eligible_pair_count"], 2)
            self.assertGreaterEqual(search["all_gate_pair_count"], 1)

    def test_dimension_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "small.png"
            Image.new("RGB", (64, 64), "black").save(path)
            with self.assertRaisesRegex(matcher.MatchError, "expected 1280x739"):
                matcher.match_frame_sets([path], [path])

    def test_metric_counts_rgb_components_and_pixels_independently(self) -> None:
        metrics = matcher.difference_metrics(
            bytes((0, 0, 0, 10, 20, 30)),
            bytes((0, 2, 0, 13, 25, 37)),
        )
        self.assertEqual(metrics["pixel_count"], 2)
        self.assertEqual(metrics["different_pixels"], 2)
        self.assertEqual(metrics["different_components"], 4)
        self.assertEqual(metrics["maximum_absolute_component_difference"], 7)
        self.assertAlmostEqual(
            metrics["mean_absolute_component_difference"], 17 / 6
        )

    def test_matcher_imports_no_selector_writer(self) -> None:
        tree = ast.parse(
            (ROOT / "tools/apf_uniform_selector_xenia_match.py").read_text(
                encoding="utf-8"
            )
        )
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertNotIn("apf_uniform_selector_patch", imported)
        self.assertNotIn("apf_uniform_selector_allocation", imported)


if __name__ == "__main__":
    unittest.main()
