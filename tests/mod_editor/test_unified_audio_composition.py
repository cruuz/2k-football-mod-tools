"""Retail-free tests for composing the fixed menu-back cue with visual edits."""

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import wave


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_visual_mod_project as unified  # noqa: E402


class UnifiedAudioCompositionTests(unittest.TestCase):
    @staticmethod
    def _authorized(pin: unified.InputPin, **_kwargs: object) -> object:
        return SimpleNamespace(
            wav_bytes=pin.payload,
            wav_sha256=pin.sha256,
            pcm_sha256=hashlib.sha256(pin.payload[44:]).hexdigest(),
        )

    def _wav(self, path: Path, frames: int = 5_696) -> None:
        samples = tuple(
            int(12_000 * math.sin(index * 2 * math.pi / 91))
            for index in range(frames)
        )
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16_000)
            output.writeframes(struct.pack(f"<{frames}h", *samples))

    def _project(self, path: Path, wav: Path) -> None:
        document = {
            "edits": [{"kind": "menu_back_audio", "wav": str(wav)}],
            "purpose": "Synthetic user-authored audio composition test.",
            "schema": unified.SCHEMA,
        }
        path.write_bytes(unified.canonical_json(document))

    def test_strict_wav_is_a_normal_unified_input_and_fixed_span(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-audio-test-") as temporary:
            root = Path(temporary)
            wav = root / "mine.wav"
            project_path = root / "project.json"
            self._wav(wav)
            self._project(project_path, wav)

            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            with patch.object(
                unified, "authorize_audio_input", side_effect=self._authorized
            ):
                replacement, previews, report, selector, target = (
                    unified.build_menu_back_audio_import(
                        project.value["edits"][0], project, pins, object()
                    )
                )
            self.assertEqual(len(replacement), 3_204)
            self.assertEqual(previews, [])
            self.assertEqual(selector, "menu-back_01")
            self.assertEqual(target["xiso_absolute_span_offset"], 1_632_809_776)
            self.assertEqual(report["input_wav"]["frame_count"], 5_696)
            validated = unified.validate_only(project_path)
            self.assertEqual(validated["kind_counts"], {"menu_back_audio": 1})
            self.assertEqual(validated["unique_png_count"], 1)

    def test_wrong_frame_count_and_duplicate_fixed_target_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unified-audio-test-") as temporary:
            root = Path(temporary)
            wav = root / "short.wav"
            self._wav(wav, frames=5_695)
            project_path = root / "project.json"
            self._project(project_path, wav)
            project = unified.read_project(project_path)
            pins = unified.pin_project_inputs(project)
            with patch.object(
                unified, "authorize_audio_input", side_effect=self._authorized
            ), self.assertRaisesRegex(unified.ProjectError, "5696 frames"):
                unified.build_menu_back_audio_import(
                    project.value["edits"][0], project, pins, object()
                )

            duplicate = {
                "edits": [
                    {"kind": "menu_back_audio", "wav": str(wav)},
                    {"kind": "menu_back_audio", "wav": str(wav)},
                ],
                "purpose": "Duplicate must fail.",
                "schema": unified.SCHEMA,
            }
            project_path.write_bytes(unified.canonical_json(duplicate))
            with self.assertRaisesRegex(unified.ProjectError, "repeats"):
                unified.read_project(project_path)

    def test_large_out_of_order_span_set_uses_sorted_adjacent_validation(self) -> None:
        count = 25_000
        disjoint = tuple(
            (index * 4, index * 4 + 2, f"synthetic:{index}")
            for index in reversed(range(count))
        )
        unified.require_non_overlapping_ranges(disjoint)
        unified.require_non_overlapping_ranges(((0, 8, "first"), (8, 16, "second")))
        with self.assertRaisesRegex(
            unified.ProjectError, "target spans overlap at second"
        ):
            unified.require_non_overlapping_ranges(
                ((16, 32, "second"), (0, 24, "first"))
            )


if __name__ == "__main__":
    unittest.main()
