"""Public-safe adapter for the read-only APF jersey-family exporter.

The editor exposes only the retail ``0A`` path, the proved asset index, and a
new output directory.  Archive entries, offsets, allocations, codecs, and mip
layout values remain owned by the hash-pinned exporter catalog and cannot be
supplied through this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Any

from .errors import ModEditorError, OutputRefusedError, ValidationError


APF_JERSEY_EXPORT_CAPABILITY_ID = "apf2k8.uniforms.jersey_00_23"


class ApfJerseyExportError(ModEditorError):
    """The fixed read-only jersey export could not be completed."""


@dataclass(frozen=True)
class ApfJerseyExportResult:
    """Small editor-facing result; retail-derived pixels remain on disk only."""

    output_dir: Path
    provenance: Path
    asset_index: int
    file_count: int


def _new_output_directory(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if os.path.lexists(requested):
        raise OutputRefusedError(
            f"APF jersey export directory already exists: {requested}"
        )
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise OutputRefusedError(
            f"APF jersey export parent does not exist: {requested.parent}"
        ) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise OutputRefusedError(
            "APF jersey export parent must be a non-symlink directory"
        )
    return requested.resolve(strict=False)


def _backend_export(source_0a: Path, asset_index: int, output_dir: Path) -> Any:
    # Keep the large archive/texture stack lazy so registry checks and ordinary
    # editor startup do not load an exporter that the user did not request.
    from tools import apf_jersey_family_export

    return apf_jersey_family_export.export_jersey(
        source_0a, asset_index, output_dir
    )


def export_apf_jersey(
    source_0a: Path, asset_index: int, output_dir: Path
) -> ApfJerseyExportResult:
    """Run the fixed read-only export contract and return its provenance path."""

    if type(asset_index) is not int or not 0 <= asset_index <= 23:
        raise ValidationError("APF jersey export asset index must be an integer in 0..23")
    destination = _new_output_directory(output_dir)
    try:
        result = _backend_export(Path(source_0a), asset_index, destination)
    except ModEditorError:
        raise
    except Exception as exc:
        raise ApfJerseyExportError(f"APF jersey export failed: {exc}") from exc
    return ApfJerseyExportResult(
        output_dir=Path(result.output_dir),
        provenance=Path(result.provenance),
        asset_index=int(result.asset_index),
        file_count=int(result.file_count),
    )
