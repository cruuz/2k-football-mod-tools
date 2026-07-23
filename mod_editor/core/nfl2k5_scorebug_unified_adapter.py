"""Translate one logical NFL 2K5 scorebug edit for the unified XISO writer.

The scorebug PNG codec and fixed-span writer already live in
``tools/nfl_scorebug_png_import.py``.  That importer predates the unified
visual project and names its pack proof fields slightly differently.  This
module is the deliberately small bridge between the two contracts; it does
not contain texture data, offsets, or a second codec implementation.

Callers remain responsible for pinning/copying the user PNG before invoking
this adapter.  The returned tuple is accepted directly by the unified
backend's ``build_one_import`` path::

    replacement, previews, report, selector, target

``target`` includes the ``xiso_pack_*`` aliases consumed by
``target_proof`` while retaining every field emitted by the typed importer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import hashlib
import os
from pathlib import Path
import re
import sys
from types import MappingProxyType
from typing import Any, TypeAlias


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_scorebug_png_import as scorebug_import  # noqa: E402


SCOREBUG_TEXTURE_KIND = "scorebug_texture"
SCOREBUG_IMPORT_SCHEMA = "nfl2k5_scorebug_png_import/v1"
SCOREBUG_ADAPTER_SCHEMA = "2k5_mod_studio_scorebug_unified_adapter/v1"
SCOREBUG_TARGET_DIMENSIONS = MappingProxyType({
    "score_buga": (64, 64),
    "shield_espn": (128, 64),
    "digital_font": (128, 128),
})
SCOREBUG_TARGETS = tuple(SCOREBUG_TARGET_DIMENSIONS)
SCOREBUG_REPORT = ROOT / scorebug_import.DEFAULT_AUDIT
SCOREBUG_REPORT_SHA256 = scorebug_import.AUDIT_SHA256

_EDIT_FIELDS = frozenset({"kind", "target", "png"})
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)

ScorebugImporter: TypeAlias = Callable[
    [Path, Path, str, Path],
    tuple[bytes, bytes, dict[str, Any]],
]
UnifiedImport: TypeAlias = tuple[
    bytes,
    list[tuple[str, bytes]],
    dict[str, Any],
    str,
    dict[str, Any],
]


class ScorebugUnifiedAdapterError(ValueError):
    """The logical edit or typed-importer result violates the bridge contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScorebugUnifiedAdapterError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    _require(
        type(value) is int and value >= minimum,
        f"scorebug importer returned an invalid {label}",
    )
    return int(value)


def _hash(value: object, label: str) -> str:
    _require(
        type(value) is str and _SHA256.fullmatch(value) is not None,
        f"scorebug importer returned an invalid {label}",
    )
    return str(value)


def _logical_edit(edit: Mapping[str, object]) -> tuple[str, Path]:
    _require(isinstance(edit, Mapping), "scorebug edit must be an object")
    _require(
        set(edit) == _EDIT_FIELDS,
        "scorebug edit must contain only kind, target, and png",
    )
    _require(
        edit.get("kind") == SCOREBUG_TEXTURE_KIND,
        "scorebug edit kind must be scorebug_texture",
    )
    target = edit.get("target")
    _require(
        type(target) is str and target in SCOREBUG_TARGET_DIMENSIONS,
        "scorebug target must be score_buga, shield_espn, or digital_font",
    )
    png_value = edit.get("png")
    _require(
        isinstance(png_value, (str, os.PathLike)) and not isinstance(png_value, bytes),
        "scorebug png must be a pathname",
    )
    png_text = os.fspath(png_value)
    _require(
        isinstance(png_text, str) and bool(png_text) and "\0" not in png_text,
        "scorebug png pathname cannot be empty or contain NUL",
    )
    return str(target), Path(png_text)


def _changed_run_count(rebuild: Mapping[str, object], span_size: int) -> int:
    runs = rebuild.get("changed_runs")
    _require(
        isinstance(runs, list) and bool(runs),
        "scorebug importer returned no changed-byte runs",
    )
    count = 0
    previous_end = -1
    for item in runs:
        _require(
            isinstance(item, list) and len(item) == 2,
            "scorebug importer returned a malformed changed-byte run",
        )
        first = _integer(item[0], "changed-byte run start")
        last = _integer(item[1], "changed-byte run end")
        _require(
            previous_end < first <= last < span_size,
            "scorebug importer returned overlapping or out-of-range changed-byte runs",
        )
        previous_end = last
        count += last - first + 1
    return count


def _unified_target(
    target_name: str,
    replacement: bytes,
    raw_target: Mapping[str, object],
) -> dict[str, Any]:
    _require(
        raw_target.get("name") == target_name,
        "scorebug importer selected a different target than requested",
    )
    width, height = SCOREBUG_TARGET_DIMENSIONS[target_name]
    _require(
        _integer(raw_target.get("width"), "target width", minimum=1) == width
        and _integer(raw_target.get("height"), "target height", minimum=1) == height,
        "scorebug importer target dimensions changed",
    )
    pack_path = raw_target.get("pack_path")
    _require(
        type(pack_path) is str and bool(pack_path),
        "scorebug importer returned an invalid pack path",
    )
    pack_sector = _integer(raw_target.get("xiso_pack_sector"), "pack sector")
    pack_byte_offset = _integer(
        raw_target.get("xiso_pack_byte_offset"), "pack byte offset"
    )
    pack_size = _integer(raw_target.get("pack_size"), "pack size", minimum=1)
    pack_sha256 = _hash(raw_target.get("pack_sha256"), "pack SHA-256")
    pack_offset = _integer(raw_target.get("pack_offset"), "span pack offset")
    absolute = _integer(
        raw_target.get("xiso_absolute_span_offset"), "absolute span offset"
    )
    span_size = _integer(raw_target.get("span_size"), "span size", minimum=1)
    span_sha256 = _hash(raw_target.get("span_sha256"), "retail span SHA-256")
    _require(
        pack_byte_offset == pack_sector * 2048
        and absolute == pack_byte_offset + pack_offset
        and pack_offset + span_size <= pack_size,
        "scorebug importer target pack arithmetic changed",
    )
    _require(
        span_size == len(replacement),
        "scorebug replacement changed its fixed span size",
    )
    target = copy.deepcopy(dict(raw_target))
    target.update({
        "selector": target_name,
        "xiso_pack_path": str(pack_path),
        "xiso_pack_sector": pack_sector,
        "xiso_pack_size": pack_size,
        "xiso_pack_sha256": pack_sha256,
        "pack_offset": pack_offset,
        "xiso_absolute_span_offset": absolute,
        "span_sha256": span_sha256,
    })
    return target


def build_scorebug_texture_import(
    index_path: Path,
    audit_path: Path,
    edit: Mapping[str, object],
    *,
    importer: ScorebugImporter | None = None,
) -> UnifiedImport:
    """Run the typed importer and return the unified backend's five values.

    ``edit`` is intentionally logical and offset-free.  In normal product use
    its ``png`` value should be the unified backend's private, pinned input
    copy, not an unpinned user pathname.
    """

    target_name, png_path = _logical_edit(edit)
    implementation = scorebug_import.build_import if importer is None else importer
    replacement, preview, raw_report = implementation(
        Path(index_path), Path(audit_path), target_name, png_path
    )
    _require(
        type(replacement) is bytes and bool(replacement),
        "scorebug importer returned an invalid replacement span",
    )
    _require(
        type(preview) is bytes and bool(preview),
        "scorebug importer returned an invalid preview PNG",
    )
    _require(
        isinstance(raw_report, dict)
        and raw_report.get("schema") == SCOREBUG_IMPORT_SCHEMA,
        "scorebug importer returned an unsupported report",
    )
    raw_target = raw_report.get("target")
    _require(
        isinstance(raw_target, Mapping),
        "scorebug importer report has no target proof",
    )
    target = _unified_target(target_name, replacement, raw_target)

    rebuild = raw_report.get("rebuild")
    _require(
        isinstance(rebuild, Mapping),
        "scorebug importer report has no rebuild proof",
    )
    _require(
        _integer(rebuild.get("span_size"), "rebuilt span size", minimum=1)
        == len(replacement)
        and _hash(rebuild.get("span_sha256"), "replacement span SHA-256")
        == _sha256(replacement),
        "scorebug importer replacement proof does not match its bytes",
    )
    changed_count = _changed_run_count(rebuild, len(replacement))
    _require(
        _integer(rebuild.get("changed_byte_count"), "changed-byte count", minimum=1)
        == changed_count,
        "scorebug importer changed-byte count does not match its runs",
    )

    preview_report = raw_report.get("preview")
    width, height = SCOREBUG_TARGET_DIMENSIONS[target_name]
    _require(
        isinstance(preview_report, Mapping)
        and preview_report.get("file_name") == "preview.png"
        and _hash(preview_report.get("sha256"), "preview SHA-256")
        == _sha256(preview)
        and _integer(preview_report.get("width"), "preview width", minimum=1)
        == width
        and _integer(preview_report.get("height"), "preview height", minimum=1)
        == height,
        "scorebug importer preview proof does not match its bytes or target",
    )
    claims = raw_report.get("claims")
    _require(
        isinstance(claims, Mapping)
        and claims.get("fixed_span_only") is True
        and claims.get("originals_modified") is False
        and claims.get("xiso_created") is False,
        "scorebug importer safety claims changed",
    )

    report = copy.deepcopy(raw_report)
    report["target"] = copy.deepcopy(target)
    report["unified_adapter"] = {
        "schema": SCOREBUG_ADAPTER_SCHEMA,
        "selector": target_name,
        "target_proof_aliases_added": [
            "selector",
            "xiso_pack_path",
            "xiso_pack_size",
            "xiso_pack_sha256",
        ],
        "typed_importer_reused": True,
        "retail_bytes_embedded": False,
    }
    return replacement, [("preview.png", preview)], report, target_name, target


__all__ = [
    "SCOREBUG_ADAPTER_SCHEMA",
    "SCOREBUG_IMPORT_SCHEMA",
    "SCOREBUG_REPORT",
    "SCOREBUG_REPORT_SHA256",
    "SCOREBUG_TARGET_DIMENSIONS",
    "SCOREBUG_TARGETS",
    "SCOREBUG_TEXTURE_KIND",
    "ScorebugImporter",
    "ScorebugUnifiedAdapterError",
    "UnifiedImport",
    "build_scorebug_texture_import",
]
