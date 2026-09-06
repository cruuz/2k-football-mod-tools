"""The one way this module writes: a NEW image, through the shared ISO9660 writer.

Every writer lane here ends the same way -- a set of whole files, each no
longer than the extent it already owns, handed to ``tools/ps2_iso9660_writer``
-- and every verifier starts the same way, with ``tools/ps2_iso9660_verify``
re-deriving the image-level claim with its own decoder.  Both tools are
imported inside functions, as a game package must.

Standard library only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from mod_editor.games.contract import DeclaredRange, require

from . import containers  # noqa: F401  (puts tools/ on the path)

#: The sentence every writer here carries, because it is true of every one.
NOT_BOOTED = ("No MVP Baseball 2005 image rebuilt by this module has been booted in an "
              "emulator or on hardware; the game's acceptance of a rewritten archive is "
              "not claimed anywhere.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def writer() -> Any:
    import ps2_iso9660_writer

    return ps2_iso9660_writer


def verifier() -> Any:
    import ps2_iso9660_verify

    return ps2_iso9660_verify


def check_destination(source: Path, destination: Path) -> None:
    require(Path(destination).resolve() != Path(source).resolve(),
            f"{destination} is the source image; a build always writes a NEW image.")
    require(not os.path.lexists(destination),
            f"destination {destination} already exists; refusing to overwrite")


def plan_ranges(source: Path, replacements: Mapping[str, bytes]) -> Tuple[DeclaredRange, ...]:
    report = writer().plan_report(Path(source), dict(replacements))
    return tuple(DeclaredRange(item.start, item.length, item.reason)
                 for item in report["declared_ranges"])


def replace_files(source: Path, destination: Path, replacements: Mapping[str, bytes]
                  ) -> Tuple[Dict[str, Any], Tuple[DeclaredRange, ...]]:
    """Write the new image; return the JSON-safe writer report and its ranges."""
    tool = writer()
    report = tool.replace_files(Path(source), Path(destination), dict(replacements))
    json_report = tool.report_to_json(report)
    ranges = tuple(DeclaredRange(item["start"], item["length"], item["reason"])
                   for item in json_report["declared_ranges"])
    return json_report, ranges


def verify_image(source: Path, destination: Path, iso_report: Optional[Mapping[str, Any]]
                 ) -> Optional[str]:
    """The image-level check, independent of the writer.  ``None`` when it holds."""
    if not iso_report:
        return "the receipt carries no write report"
    tool = verifier()
    try:
        outcome = tool.verify_replacement(Path(source), Path(destination), dict(iso_report))
    except tool.IsoVerifyError as exc:
        return f"at the image level: {exc}"
    if not isinstance(outcome, dict):
        return f"at the image level: {outcome}"
    return None


__all__ = ["NOT_BOOTED", "check_destination", "plan_ranges", "replace_files", "sha256",
           "verifier", "verify_image", "writer"]
