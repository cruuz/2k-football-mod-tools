from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.core.errors import ValidationError
from mod_editor.core.model import SourceRecord
from mod_editor.core.nfl2k5_audio_origin_preparation import (
    Nfl2k5AudioOriginPreparation,
)
from mod_editor.core.nfl2k5_source_cache import SourceCache


SOURCE_SHA256 = "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"


class _Store:
    def __init__(self, name: str) -> None:
        self.name = name

    def inventory_path(self, cache: SourceCache) -> Path:
        return cache.root / "derived" / self.name


class _Scanner:
    """Shaped like the real scanners: the exact scanner's result carries the published inventory object
    (``result.inventory.path``, like ``AudioSourceScanResult``) while the containment scanner's result carries
    ``inventory_path`` (like ``AudioSourceContainmentResult``). Beta 62 read ``inventory_path`` on both and raised
    AttributeError for every cache whose exact inventory was not already prepared."""

    def __init__(self, name: str, *, reused: bool = False, exact: bool = False) -> None:
        self.store = _Store(name)
        self.reused = reused
        self.exact = exact
        self.calls: list[tuple[Path, SourceCache, object]] = []

    def ensure(
        self,
        source: Path,
        cache: SourceCache,
        *,
        progress: object,
        cancelled: object,
    ) -> object:
        self.calls.append((source, cache, cancelled))
        progress(SimpleNamespace(stage="Scanning fixture", completed=2, total=4))
        derived = cache.root / "derived"
        derived.mkdir(mode=0o700, exist_ok=True)
        output = self.store.inventory_path(cache)
        output.write_bytes(b"private-digest-metadata\n")
        output.chmod(0o600)
        if self.exact:
            return SimpleNamespace(inventory=SimpleNamespace(path=output), reused_inventory=self.reused)
        return SimpleNamespace(
            inventory_path=output,
            reused_inventory=self.reused,
        )


class RealScanResultShapeTests(unittest.TestCase):
    def test_the_real_scan_results_carry_the_fields_the_preparation_reads(self) -> None:
        from dataclasses import fields
        from mod_editor.core.nfl2k5_audio_source_scan import AudioSourceScanResult
        from mod_editor.core.nfl2k5_audio_source_containment import AudioSourceContainmentResult
        from mod_editor.core.nfl2k5_audio_source_fingerprints import AudioSourceFingerprintInventory
        exact_fields = {f.name for f in fields(AudioSourceScanResult)}
        self.assertIn("inventory", exact_fields)
        self.assertNotIn("inventory_path", exact_fields)
        self.assertIn("path", {f.name for f in fields(AudioSourceFingerprintInventory)})
        self.assertIn("inventory_path", {f.name for f in fields(AudioSourceContainmentResult)})


class AudioOriginPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / SOURCE_SHA256
        self.root.mkdir(mode=0o700)
        self.source = Path(self.temporary.name) / "source.xiso.iso"
        record = SourceRecord(
            selected_path=str(self.source),
            inspected_path=str(self.source),
            kind="xiso",
            sha256=SOURCE_SHA256,
            size=6_300_499_968,
            recognized=True,
            fingerprint_id="nfl2k5-usa-retail-xiso",
            detected_game="nfl2k5",
        )
        self.cache = SourceCache(
            source=record,
            root=self.root,
            pack0=self.root / "pack0",
            inventory=self.root / "index.json",
            originals=self.root / "originals",
            resource_count=0,
            outer_entry_count=0,
            kind_counts={},
        )
        self.exact = _Scanner("exact.json", exact=True)
        self.containment = _Scanner("containment.json")
        self.coordinator = Nfl2k5AudioOriginPreparation(
            exact_scanner=self.exact,  # type: ignore[arg-type]
            containment_scanner=self.containment,  # type: ignore[arg-type]
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _publish(self, scanner: _Scanner, payload: bytes = b"metadata\n") -> Path:
        derived = self.root / "derived"
        derived.mkdir(mode=0o700, exist_ok=True)
        path = scanner.store.inventory_path(self.cache)
        path.write_bytes(payload)
        path.chmod(0o600)
        return path

    def test_prepare_builds_both_missing_artifacts_and_adapts_progress(self) -> None:
        events: list[tuple[str, int, int]] = []
        result = self.coordinator.prepare(self.cache, lambda *row: events.append(row))

        self.assertEqual(len(self.exact.calls), 1)
        self.assertEqual(len(self.containment.calls), 1)
        self.assertEqual(self.exact.calls[0][0], self.source.absolute())
        self.assertFalse(result.exact_reused)
        self.assertFalse(result.containment_reused)
        self.assertTrue(self.coordinator.is_ready(self.cache))
        self.assertIn(("[1/2] Scanning fixture", 2, 4), events)
        self.assertIn(("[2/2] Scanning fixture", 2, 4), events)
        self.assertEqual(events[-1], ("Audio editing safety data ready", 2, 2))

    def test_prepare_skips_an_existing_safe_artifact(self) -> None:
        exact_path = self._publish(self.exact)
        result = self.coordinator.prepare(self.cache, lambda *_row: None)

        self.assertEqual(result.exact_inventory, exact_path)
        self.assertTrue(result.exact_reused)
        self.assertEqual(self.exact.calls, [])
        self.assertEqual(len(self.containment.calls), 1)

    def test_ready_requires_owned_single_link_mode_0600_regular_files(self) -> None:
        exact = self._publish(self.exact)
        self._publish(self.containment)
        self.assertTrue(self.coordinator.is_ready(self.cache))

        # A mode the running platform can actually produce AND that differs from
        # the private mode it reports.  0o644 is that on POSIX; on Windows, where
        # chmod honours only the read-only attribute, 0o644 still reads back as
        # the private 0o666 and would prove nothing -- 0o444 (read-only) is the
        # state that platform can really express.
        wrong_mode = 0o444 if platform_compat.IS_WINDOWS else 0o644
        self.assertNotEqual(wrong_mode, platform_compat.private_file_mode())
        exact.chmod(wrong_mode)
        self.assertFalse(self.coordinator.is_ready(self.cache))
        exact.chmod(0o600)
        hardlink = exact.with_name("hardlink.json")
        os.link(exact, hardlink)
        self.assertFalse(self.coordinator.is_ready(self.cache))

    def test_a_refused_cache_reads_as_not_ready_instead_of_raising(self) -> None:
        """Beta 62.1 field report: Music tab -> audio_editing_ready -> is_ready ->
        store.inventory_path raised "source-cache directory is not the canonical
        cache key" for a fresh rip, and the app showed the unexpected-error
        dialog on every music change. The probe must answer False; prepare()
        is where a refusal gets reported."""

        from mod_editor.core.nfl2k5_audio_source_fingerprints import AudioSourceFingerprintError

        self._publish(self.exact)
        self._publish(self.containment)
        self.assertTrue(self.coordinator.is_ready(self.cache))

        class _RefusingStore:
            def inventory_path(self, cache: SourceCache) -> Path:
                raise AudioSourceFingerprintError(
                    "NFL 2K5 source-cache directory is not the canonical cache key"
                )

        self.exact.store = _RefusingStore()
        self.assertFalse(self.coordinator.is_ready(self.cache))

    def test_cancel_before_first_missing_scan_publishes_nothing(self) -> None:
        with self.assertRaisesRegex(ValidationError, "cancelled"):
            self.coordinator.prepare(
                self.cache,
                lambda *_row: None,
                cancelled=lambda: True,
            )
        self.assertEqual(self.exact.calls, [])
        self.assertEqual(self.containment.calls, [])
        self.assertFalse(self.coordinator.is_ready(self.cache))

    def test_invalid_arguments_are_actionable(self) -> None:
        with self.assertRaisesRegex(ValidationError, "currently loaded"):
            self.coordinator.prepare(object(), lambda *_row: None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValidationError, "progress"):
            self.coordinator.prepare(self.cache, None)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValidationError, "cancellation"):
            self.coordinator.prepare(
                self.cache,
                lambda *_row: None,
                cancelled=False,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
