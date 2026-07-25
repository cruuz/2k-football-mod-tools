"""One-click preparation of private NFL 2K5 audio-origin safety data.

The exact and containment inventories are intentionally derived from the
user's own recognized XISO and kept below that source's private cache.  They
are never project or release payloads.  This coordinator gives the desktop
product one bounded, progress-reporting operation for creating the reviewed
inventories when an authored audio replacement is attempted for the first
time.

Strict parsing and source authentication remain owned by the two reviewed
scanners/stores.  ``is_ready`` is deliberately only a cheap filesystem
preflight; callers must still load both inventories through the strict stores
before accepting a replacement.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import time
from typing import Callable

from . import platform_compat
from .errors import ValidationError
from .nfl2k5_audio_source_containment import (
    MAX_PRIVATE_DOCUMENT_BYTES,
    Nfl2k5AudioSourceContainmentScanner,
)
from .nfl2k5_audio_source_fingerprints import MAX_INVENTORY_BYTES
from .nfl2k5_audio_source_scan import Nfl2k5AudioSourceScanner
from .nfl2k5_source_cache import SourceCache


ProgressSink = Callable[[str, int, int], None]
CancellationCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class AudioOriginPreparationResult:
    """Paths and reuse state for one complete private preparation."""

    exact_inventory: Path
    containment_inventory: Path
    exact_reused: bool
    containment_reused: bool
    elapsed_seconds: float


class Nfl2k5AudioOriginPreparation:
    """Create missing source-bound audio inventories without touching the XISO."""

    def __init__(
        self,
        *,
        exact_scanner: Nfl2k5AudioSourceScanner | None = None,
        containment_scanner: Nfl2k5AudioSourceContainmentScanner | None = None,
    ) -> None:
        self.exact_scanner = exact_scanner or Nfl2k5AudioSourceScanner()
        self.containment_scanner = (
            containment_scanner or Nfl2k5AudioSourceContainmentScanner()
        )

    def is_ready(self, cache: SourceCache) -> bool:
        """Cheaply report whether both canonical private artifacts are present.

        This does not parse the large documents.  The audio service performs
        the authoritative source/shape/canonical-byte validation immediately
        after preparation and before any user WAV is admitted.
        """

        exact = self.exact_scanner.store.inventory_path(cache)
        containment = self.containment_scanner.store.inventory_path(cache)
        return self._private_file_ready(exact, MAX_INVENTORY_BYTES) and \
            self._private_file_ready(containment, MAX_PRIVATE_DOCUMENT_BYTES)

    def prepare(
        self,
        cache: SourceCache,
        progress: ProgressSink,
        cancelled: CancellationCheck | None = None,
    ) -> AudioOriginPreparationResult:
        """Build only missing inventories, then return their canonical paths."""

        if not isinstance(cache, SourceCache):
            raise ValidationError(
                "Audio preparation needs the currently loaded NFL 2K5 game."
            )
        if not callable(progress):
            raise ValidationError("Audio preparation progress is unavailable.")
        if cancelled is not None and not callable(cancelled):
            raise ValidationError("Audio preparation cancellation is invalid.")

        started = time.monotonic()
        source = Path(os.path.abspath(os.fspath(cache.source.selected_path)))
        exact_path = self.exact_scanner.store.inventory_path(cache)
        containment_path = self.containment_scanner.store.inventory_path(cache)
        exact_ready = self._private_file_ready(exact_path, MAX_INVENTORY_BYTES)
        containment_ready = self._private_file_ready(
            containment_path, MAX_PRIVATE_DOCUMENT_BYTES
        )

        progress("Preparing audio safety data", 0, 2)
        exact_reused = exact_ready
        if exact_ready:
            progress("Exact audio safety data already prepared", 1, 2)
        else:
            self._check_cancelled(cancelled)
            result = self.exact_scanner.ensure(
                source,
                cache,
                progress=self._phase_progress(progress, 1, "Exact audio scan"),
                cancelled=cancelled,
            )
            if result.inventory_path != exact_path:
                raise ValidationError(
                    "Exact audio preparation published outside its private cache."
                )
            exact_reused = bool(result.reused_inventory)
            if not self._private_file_ready(exact_path, MAX_INVENTORY_BYTES):
                raise ValidationError(
                    "Exact audio safety data was not published safely."
                )
            progress("Exact audio safety data ready", 1, 2)

        containment_reused = containment_ready
        if containment_ready:
            progress("Containment safety data already prepared", 2, 2)
        else:
            self._check_cancelled(cancelled)
            result = self.containment_scanner.ensure(
                source,
                cache,
                progress=self._phase_progress(
                    progress, 2, "Audio containment scan"
                ),
                cancelled=cancelled,
            )
            if result.inventory_path != containment_path:
                raise ValidationError(
                    "Audio containment preparation published outside its private cache."
                )
            containment_reused = bool(result.reused_inventory)
            if not self._private_file_ready(
                containment_path, MAX_PRIVATE_DOCUMENT_BYTES
            ):
                raise ValidationError(
                    "Audio containment safety data was not published safely."
                )
            progress("Containment safety data ready", 2, 2)

        if not self.is_ready(cache):
            raise ValidationError(
                "Audio safety preparation did not produce both private inventories."
            )
        progress("Audio editing safety data ready", 2, 2)
        return AudioOriginPreparationResult(
            exact_inventory=exact_path,
            containment_inventory=containment_path,
            exact_reused=exact_reused,
            containment_reused=containment_reused,
            elapsed_seconds=time.monotonic() - started,
        )

    @staticmethod
    def _private_file_ready(path: Path, maximum: int) -> bool:
        try:
            info = path.lstat()
        except (FileNotFoundError, OSError):
            return False
        return bool(
            stat.S_ISREG(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and platform_compat.is_owned_by_current_user(info, path=path)
            and info.st_nlink == 1
            # Byte-for-byte the 0o600 equality check on POSIX; on Windows the
            # same private file reads back as 0o666, the only value that
            # platform can produce, and its confidentiality comes from the cache
            # root's ACL (see platform_compat.private_file_mode).
            and stat.S_IMODE(info.st_mode) == platform_compat.private_file_mode()
            and 0 < info.st_size <= maximum
        )

    @staticmethod
    def _check_cancelled(cancelled: CancellationCheck | None) -> None:
        if cancelled is not None and cancelled():
            raise ValidationError(
                "Audio preparation was cancelled; no partial inventory was accepted."
            )

    @staticmethod
    def _phase_progress(
        progress: ProgressSink, phase: int, label: str
    ) -> Callable[[object], None]:
        def emit(event: object) -> None:
            stage = str(getattr(event, "stage", label))
            completed = getattr(event, "completed", 0)
            total = getattr(event, "total", 1)
            completed_value = completed if type(completed) is int else 0
            total_value = total if type(total) is int and total > 0 else 1
            progress(f"[{phase}/2] {stage}", completed_value, total_value)

        return emit
