"""Compose a facemask/turtleneck colour change into the unified build.

The two ``Unif`` colour words are the one edit modders keep asking for and the
one that has never been reachable from the app. Word 0 is the
facemask/faceshield tint and word 1 is ``HI_turtleneck``, both established by
executable trace; the writer that owns them could only ever paint magenta,
which made it a proof rather than a feature.

One colour choice touches **two** packs -- ``vc_53450030/A`` and ``/B`` carry
the same eight-byte pair -- so this returns two composed imports from a single
edit, the same shape ``team_identity`` already uses.

Identity is per-extent: each target names its pack, and the build locates that
pack in the user's own image, derives the absolute offset from where it landed,
and verifies the pack hash and the retail span before writing. Nothing depends
on the container's size or hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl_uniform_color_xiso_direct_patch as writer  # noqa: E402


UNIF_COLOR_KIND = "unif_color"
# Retail sectors, recorded for the build proof only. A pressed disc or a repack
# puts the same pack somewhere else, so the build locates it by path and
# re-derives every offset; nothing is compared against these.
RETAIL_PACK_SECTORS = {"vc_53450030/A": 2_403_082, "vc_53450030/B": 2_179_328}


class UnifColorWriterError(ValueError):
    """Raised when a colour, target, or replacement fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UnifColorWriterError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_color(text: str) -> int:
    """Accept ``AARRGGBB`` or ``#RRGGBB`` and return a 32-bit ARGB integer."""
    value = str(text).strip().lstrip("#")
    _require(len(value) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in value),
             f"{text!r} is not a colour; use AARRGGBB or #RRGGBB")
    if len(value) == 6:
        value = "FF" + value
    return int(value, 16)


def targets() -> tuple[Any, ...]:
    """The two retail spans this edit replaces, straight from the writer."""
    return writer.TARGETS


def build_unif_color_imports(
    edit: dict[str, Any]
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]]:
    """Return one composed import per pack for a single colour choice."""
    facemask = parse_color(edit["facemask"])
    turtleneck = parse_color(edit.get("turtleneck") or edit["facemask"])
    replacement = writer.pack_colors(facemask, turtleneck)
    _require(len(replacement) == 8, "colour pair must be eight bytes")

    built: list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]] = []
    for target in targets():
        _require(len(target.expected_bytes) == 8,
                 f"{target.path} retail colour span is not eight bytes")
        _require(replacement != target.expected_bytes,
                 "the chosen colours are already the retail colours")
        pack_path = target.path
        sector = RETAIL_PACK_SECTORS.get(pack_path)
        _require(sector is not None, f"{pack_path} is not a known colour pack")
        record = {
            "pack_offset": target.pack_offset,
            "selector": f"unif_color:{pack_path.rsplit('/', 1)[-1]}",
            "span_sha256": _digest(target.expected_bytes),
            "span_size": 8,
            # Recorded for the proof; the build re-derives the real position.
            "xiso_absolute_span_offset": target.expected_absolute_patch_offset,
            "xiso_pack_path": pack_path,
            "xiso_pack_sector": sector,
            "xiso_pack_sha256": target.expected_sha256,
            "xiso_pack_size": target.expected_size,
        }
        report = {
            "schema": "nfl2k5_unif_color_import/v1",
            "facemask_argb": f"{facemask:08X}",
            "turtleneck_argb": f"{turtleneck:08X}",
            "pack_path": pack_path,
            "replacement_sha256": _digest(replacement),
            "retail_sha256": _digest(target.expected_bytes),
            "note": "Word 0 is the facemask/faceshield tint; word 1 is "
                    "HI_turtleneck, read only when a player's two-bit selector "
                    "is 3. Ownership is proved by executable trace, not by a "
                    "controlled runtime capture.",
            "target": dict(record),
        }
        built.append((replacement, [], report, str(record["selector"]), record))
    return built


__all__ = [
    "RETAIL_PACK_SECTORS",
    "UNIF_COLOR_KIND",
    "UnifColorWriterError",
    "build_unif_color_imports",
    "parse_color",
    "targets",
]
