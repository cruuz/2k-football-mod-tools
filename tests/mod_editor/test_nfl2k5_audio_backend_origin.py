"""Retail-free backend tests for final 2K5 audio origin and AUSB composition."""

from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_ausb_fixed_slots import StreamingSlotCatalog
from tests.mod_editor.test_nfl2k5_ausb_build_adapter import (
    _origin_inventories,
    _slot,
    _wav,
)


TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_visual_mod_project as unified  # noqa: E402


def _context(slot) -> unified.AudioOriginContext:
    exact, containment = _origin_inventories()
    lookup = {slot.canonical_id: slot}
    lookup.update({owner.asset_id: slot for owner in slot.owners})
    return unified.AudioOriginContext(
        exact,
        containment,
        StreamingSlotCatalog((slot,), MappingProxyType(lookup)),
    )


def _write_project(path: Path, edits: list[dict[str, object]]) -> unified.ProjectFile:
    document = {
        "edits": edits,
        "purpose": "Synthetic private-origin backend test.",
        "schema": unified.SCHEMA,
    }
    path.write_bytes(unified.canonical_json(document))
    return unified.read_project(path)


class AudioBackendOriginTests(unittest.TestCase):
    def test_ausb_schema_pins_once_and_aliases_deduplicate_or_reject(self) -> None:
        slot = _slot(channels=2, seam=True, shared=True)
        context = _context(slot)
        with tempfile.TemporaryDirectory(prefix="ausb-backend-alias-") as temporary:
            root = Path(temporary)
            first_wav = root / "first.wav"
            second_wav = root / "second.wav"
            first_wav.write_bytes(_wav(channels=2))
            second_wav.write_bytes(first_wav.read_bytes())
            project = _write_project(root / "project.json", [
                {
                    "asset_id": slot.owners[0].asset_id,
                    "kind": unified.AUSB_AUDIO_KIND,
                    "wav": str(first_wav),
                },
                {
                    "asset_id": slot.owners[1].asset_id,
                    "kind": unified.AUSB_AUDIO_KIND,
                    "wav": str(second_wav),
                },
            ])
            pins = unified.pin_project_inputs(project)
            self.assertEqual(len(pins), 2)
            resolved, deduplicated = unified.resolve_ausb_project_edits(
                project, pins, context
            )
            # Project accounting stays logical even though both aliases resolve
            # to one physical streaming slot.
            self.assertEqual(len(project.value["edits"]), 2)
            self.assertEqual(set(resolved), {0})
            self.assertEqual(deduplicated, {1})

            changed = bytearray(second_wav.read_bytes())
            changed[-2] ^= 1
            second_wav.write_bytes(changed)
            divergent = unified.read_project(project.path)
            divergent_pins = unified.pin_project_inputs(divergent)
            with self.assertRaisesRegex(
                unified.ProjectError, "different WAVs"
            ):
                unified.resolve_ausb_project_edits(
                    divergent, divergent_pins, context
                )

    def test_authorized_input_and_two_span_compiler_use_exact_pin_bytes(self) -> None:
        slot = _slot(channels=2, seam=True, shared=True)
        context = _context(slot)
        with tempfile.TemporaryDirectory(prefix="ausb-backend-compile-") as temporary:
            root = Path(temporary)
            wav = root / "replacement.wav"
            wav.write_bytes(_wav(channels=2))
            project = _write_project(root / "project.json", [{
                "asset_id": slot.owners[0].asset_id,
                "kind": unified.AUSB_AUDIO_KIND,
                "wav": str(wav),
            }])
            pins = unified.pin_project_inputs(project)
            pin = unified.resolve_asset(project, str(wav), pins)
            authorized = unified.authorize_audio_input(
                pin,
                channels=slot.channels,
                sample_rate=slot.sample_rate,
                frame_count=slot.frame_count,
                context=context,
            )
            self.assertIs(authorized.wav_bytes, pin.payload)

            source = root / "synthetic-source.bin"
            source.write_bytes(
                bytes((index * 17 + 3) & 0xFF for index in range(2_560))
            )
            entries = {
                "vc_53450030/0": unified.common.XdvdfsEntry(
                    "vc_53450030/0", 0, 512, 0
                ),
                "vc_53450030/1": unified.common.XdvdfsEntry(
                    "vc_53450030/1", 1, 512, 0
                ),
            }
            descriptor = os.open(source, os.O_RDONLY)
            try:
                built = unified.build_ausb_audio_imports(
                    project.value["edits"][0],
                    project,
                    pins,
                    slot,
                    context,
                    entries,
                    descriptor,
                    {},
                )
            finally:
                os.close(descriptor)
            # One logical edit expands to two physical spans at a pack seam.
            self.assertEqual(len(project.value["edits"]), 1)
            self.assertEqual(len(built), 2)
            self.assertEqual(
                [(row[4]["xiso_pack_path"], len(row[0])) for row in built],
                [("vc_53450030/0", 50), ("vc_53450030/1", 94)],
            )
            self.assertEqual({row[4]["span_count"] for row in built}, {2})
            self.assertTrue(all(
                row[2]["claims"]["source_containment_gate_passed"]
                for row in built
            ))
            serialized = unified.canonical_json([row[2] for row in built])
            self.assertNotIn(context.exact_inventory.source_sha256.encode(), serialized)
            self.assertNotIn(str(context.exact_inventory.path).encode(), serialized)

    def test_private_load_uses_canonical_paths_and_both_strict_store_apis(self) -> None:
        with tempfile.TemporaryDirectory(prefix="audio-backend-load-") as temporary:
            root = Path(temporary) / unified.AUDIO_SOURCE_SHA256
            root.mkdir()
            pack0 = root / unified.SOURCE_CACHE_PACK_FOLDER / "0"
            inventory = root / unified.SOURCE_CACHE_INVENTORY_RELATIVE
            exact_path = root / unified.EXACT_PRIVATE_RELATIVE_PATH
            containment_path = root / unified.CONTAINMENT_PRIVATE_RELATIVE_PATH
            index_pin = SimpleNamespace(path=pack0)
            inventory_pin = SimpleNamespace(path=inventory)
            slot_catalog = StreamingSlotCatalog((), MappingProxyType({}))
            catalog = SimpleNamespace(assets=(), streaming_ranges=())
            exact = SimpleNamespace(source_sha256=unified.AUDIO_SOURCE_SHA256)
            containment = SimpleNamespace(
                source_binding_sha256=unified.AUDIO_SOURCE_SHA256
            )
            exact_store = MagicMock()
            exact_store.inventory_path.return_value = exact_path
            exact_store.load_existing.return_value = exact
            containment_store = MagicMock()
            containment_store.inventory_path.return_value = containment_path
            containment_store.load_existing.return_value = containment
            with patch.object(
                unified, "Nfl2k5AudioCatalog", return_value=catalog
            ), patch.object(
                unified, "parse_archive", return_value=object()
            ), patch.object(
                unified, "build_streaming_slot_catalog", return_value=slot_catalog
            ), patch.object(
                unified, "Nfl2k5AudioSourceFingerprintStore",
                return_value=exact_store,
            ), patch.object(
                unified, "Nfl2k5AudioSourceContainmentStore",
                return_value=containment_store,
            ), patch.object(
                unified.Nfl2k5AudioSourceContainmentScanner,
                "_policy",
                return_value=object(),
            ):
                context = unified.load_audio_origin_context(
                    index_pin,
                    inventory_pin,
                    root / "capacity.json",
                    root,
                    exact_path,
                    containment_path,
                )
            self.assertIs(context.exact_inventory, exact)
            self.assertIs(context.containment_inventory, containment)
            exact_store.load_existing.assert_called_once()
            containment_store.load_existing.assert_called_once()

    def test_audio_private_paths_are_required_but_not_project_fields(self) -> None:
        with self.assertRaisesRegex(unified.ProjectError, "Audio edits need"):
            unified.load_audio_origin_context(
                SimpleNamespace(path=Path("/not-used")),
                SimpleNamespace(path=Path("/not-used")),
                Path("/not-used"),
                None,
                None,
                None,
            )
        slot = _slot(channels=1, seam=False, shared=False)
        document = {
            "asset_id": slot.owners[0].asset_id,
            "kind": unified.AUSB_AUDIO_KIND,
            "wav": "user.wav",
        }
        self.assertEqual(
            unified.validate_edit_shape(document, 0), document
        )
        self.assertNotIn("inventory", json.dumps(document))
        self.assertNotIn("cache", json.dumps(document))

    def test_cli_reports_private_gate_errors_without_a_traceback(self) -> None:
        stderr = io.StringIO()
        argv = [
            "nfl2k5_visual_mod_project.py",
            "build",
            "--project", "/synthetic/project.json",
            "--source-xiso", "/synthetic/source.iso",
            "--output-xiso", "/synthetic/output.iso",
            "--manifest", "/synthetic/manifest.json",
            "--artifact-dir", "/synthetic/artifacts",
        ]
        with patch.object(sys, "argv", argv), patch.object(
            unified,
            "build",
            side_effect=ValidationError("private audio inventory was rejected"),
        ), redirect_stderr(stderr):
            self.assertEqual(unified.main(), 1)
        self.assertEqual(
            stderr.getvalue(),
            "error: private audio inventory was rejected\n",
        )


if __name__ == "__main__":
    unittest.main()
