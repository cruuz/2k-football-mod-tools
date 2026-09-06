"""How this module writes: whole members, same length, every CRC site, one new image.

The behaviour is :mod:`mod_editor.games._lanes.blitz_zip_lanes` -- the build
half (``plan_ranges``, ``build_replacements``) and the verify half
(``verify_replacements``), shared with the other Blitz disc because the two
pairs are the same pair.  This file binds the verifier to *this* game's disc
module, so a caller in this package keeps the call it always had.

The three-place rule and its two-place collapse live in the format package and
are decided by the index's own record shape, never by which disc this is:
``docs/product/MIDWAY_ZIP_FORMAT.md`` §6 is the measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from mod_editor.games._lanes.blitz_zip_lanes import (
    NOT_BOOTED,
    build_replacements,
    check_destination,
    plan_ranges,
    refuse_read_only,
    sha256,
)

from . import containers


def verify_replacements(source: Path, destination: Path,
                        document: Mapping[str, Any]) -> Dict[str, Any]:
    """The independent verdict, over this game's own disc reader."""

    from mod_editor.games._lanes import blitz_zip_lanes

    return blitz_zip_lanes.verify_replacements(containers, Path(source), Path(destination),
                                               document)


__all__ = ["NOT_BOOTED", "build_replacements", "check_destination", "plan_ranges",
           "refuse_read_only", "sha256", "verify_replacements"]
