"""Resolve and compose one per-uniform ``Unif`` colour-record edit.

Word 0 jointly tints the facemask and faceshield. Word 1 tints
``HI_turtleneck``. There is no independently proved visor word. Most
importantly, these words are not global: every physical uniform package owns
its own record. The old editor happened to patch Detroit's current HOME and
AWAY records and incorrectly presented those two offsets as a universal pair.

The public project stores only a logical uniform selector and user-authored
colours. During a build this module resolves that selector through the pinned
NFL archive index, verifies the selected package header and the complete retail
pack fingerprint, then emits exactly one eight-byte replacement. Raw offsets
and retail bytes never enter the shareable project.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import struct
import sys
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _ROOT / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import nfl_uniform_color_xiso_direct_patch as writer  # noqa: E402
import nfl_outer  # noqa: E402
import nfl_uniform_inventory  # noqa: E402


UNIF_COLOR_KIND = "unif_color"
UNIFORM_SELECTOR_RE = re.compile(r"^[0-9]{2}[HA](?:[0-9]|[1-9][0-9])$", re.ASCII)
RECORD_TAG_OFFSET = 0x2C
COLOUR_OFFSET = 0x50
RECORD_PROBE_BYTES = 0x70

# Complete source-pack provenance for all 634 uniform packages. Retail sectors
# are report-only: alternate legal dump layouts may place the same exact pack
# at another sector, so the build records the actual XDVDFS location it found.
PACK_PROVENANCE = {
    "9": (634_941_440,
          "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a", 35_531),
    "A": (310_294_528,
          "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b", 2_403_082),
    "B": (458_248_192,
          "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614", 2_179_328),
    "C": (315_131_904,
          "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090", 2_554_593),
}


class UnifColorWriterError(ValueError):
    """Raised when a colour, target, or replacement fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UnifColorWriterError(message)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=8)
def _file_digest_for_identity(
    path: str, device: int, inode: int, size: int, modified_ns: int,
) -> str:
    """Hash one immutable private pack once per observed file identity."""
    result = hashlib.sha256()
    source = Path(path)
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            result.update(block)
    after = source.stat()
    _require(
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        == (device, inode, size, modified_ns),
        f"uniform source pack {source.name} changed while it was verified",
    )
    return result.hexdigest()


def _file_digest(path: Path) -> str:
    info = path.stat()
    return _file_digest_for_identity(
        str(path.resolve(strict=True)), info.st_dev, info.st_ino,
        info.st_size, info.st_mtime_ns,
    )


@lru_cache(maxsize=4)
def _archive_for_identity(
    path: str, device: int, inode: int, size: int, modified_ns: int,
) -> Any:
    """Parse the 5,527-entry index once, while still keying file identity."""
    source = Path(path)
    archive = nfl_outer.parse_archive(source)
    after = source.stat()
    _require(
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        == (device, inode, size, modified_ns),
        "uniform archive index changed while it was parsed",
    )
    return archive


def _archive(index_path: Path) -> Any:
    resolved = Path(index_path).resolve(strict=True)
    info = resolved.stat()
    return _archive_for_identity(
        str(resolved), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    )


def parse_color(text: str) -> int:
    """Accept ``AARRGGBB`` or ``#RRGGBB`` and return a 32-bit ARGB integer."""
    value = str(text).strip().lstrip("#")
    _require(len(value) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in value),
             f"{text!r} is not a colour; use AARRGGBB or #RRGGBB")
    if len(value) == 6:
        value = "FF" + value
    return int(value, 16)


@dataclass(frozen=True)
class UniformColorRecord:
    selector: str
    logical_name: str
    outer_index: int
    outer_name_id: int
    pack_name: str
    pack_path: Path
    pack_offset: int
    facemask_argb: str
    turtleneck_argb: str

    @property
    def pair(self) -> tuple[str, str]:
        return self.facemask_argb, self.turtleneck_argb


def resolve_uniform_color_record(
    index_path: Path,
    selector: str,
    *,
    verify_pack_hash: bool = False,
) -> UniformColorRecord:
    """Resolve one logical set to its exact private-cache colour record."""

    normalized = str(selector).strip().upper()
    _require(UNIFORM_SELECTOR_RE.fullmatch(normalized) is not None,
             "uniform colour selector must look like 18H0 or 18A10")
    logical_name = f"{normalized}.IFF"
    try:
        archive = _archive(Path(index_path))
    except (OSError, nfl_outer.FormatError) as exc:
        raise UnifColorWriterError(f"uniform archive index is invalid: {exc}") from exc
    name_id = nfl_uniform_inventory.uniform_name_id(logical_name)
    matches = tuple(entry for entry in archive.entries if entry.name_id == name_id)
    _require(len(matches) == 1,
             f"uniform set {normalized} does not resolve to one archive package")
    entry = matches[0]
    _require(bool(entry.segments), f"uniform set {normalized} has no pack extent")
    first = entry.segments[0]
    _require(first.size >= RECORD_PROBE_BYTES,
             f"uniform set {normalized} header crosses an unsupported pack boundary")
    provenance = PACK_PROVENANCE.get(first.pack_name)
    _require(provenance is not None,
             f"uniform set {normalized} resolved outside the reviewed uniform packs")
    expected_size, expected_sha256, _retail_sector = provenance
    pack_path = archive.index_path.parent / first.pack_name
    try:
        actual_size = pack_path.stat().st_size
        with pack_path.open("rb") as stream:
            stream.seek(first.pack_offset)
            probe = stream.read(RECORD_PROBE_BYTES)
    except OSError as exc:
        raise UnifColorWriterError(
            f"uniform source pack {first.pack_name} cannot be read"
        ) from exc
    _require(actual_size == expected_size,
             f"uniform source pack {first.pack_name} size changed")
    if verify_pack_hash:
        _require(_file_digest(pack_path) == expected_sha256,
                 f"uniform source pack {first.pack_name} fingerprint changed")
    _require(len(probe) == RECORD_PROBE_BYTES
             and probe.startswith(b"UnifP")
             and probe[RECORD_TAG_OFFSET:RECORD_TAG_OFFSET + 4] == b"Unif"
             and probe[0x40:0x50] == "uniform\0".encode("utf-16le"),
             f"uniform set {normalized} record header changed")
    facemask, turtleneck = struct.unpack_from("<II", probe, COLOUR_OFFSET)
    return UniformColorRecord(
        selector=normalized,
        logical_name=logical_name,
        outer_index=entry.table_index,
        outer_name_id=entry.name_id,
        pack_name=first.pack_name,
        pack_path=pack_path,
        pack_offset=first.pack_offset + COLOUR_OFFSET,
        facemask_argb=f"{facemask:08X}",
        turtleneck_argb=f"{turtleneck:08X}",
    )


def build_unif_color_imports(
    edit: dict[str, Any],
    *,
    index_path: Path,
    source_fd: int,
    entries: dict[str, Any],
    pack_hashes: dict[str, str],
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]]:
    """Return the single proved span owned by ``edit['selector']``."""

    record = resolve_uniform_color_record(index_path, str(edit["selector"]))
    facemask = parse_color(edit["facemask"])
    turtleneck = parse_color(edit.get("turtleneck") or edit["facemask"])
    replacement = writer.pack_colors(facemask, turtleneck)
    _require(len(replacement) == 8, "colour pair must be eight bytes")
    pack_path = f"vc_53450030/{record.pack_name}"
    xiso_pack = entries.get(pack_path.casefold())
    _require(xiso_pack is not None, f"source XISO is missing {pack_path}")
    expected_size, expected_sha256, retail_sector = PACK_PROVENANCE[record.pack_name]
    _require(xiso_pack.size == expected_size
             and record.pack_offset + 8 <= xiso_pack.size,
             f"source XISO {pack_path} extent changed")
    if pack_path not in pack_hashes:
        pack_hashes[pack_path] = writer.sha256_fd(
            source_fd, xiso_pack.byte_offset, xiso_pack.size
        )
    pack_sha256 = pack_hashes[pack_path]
    _require(pack_sha256 == expected_sha256,
             f"source XISO {pack_path} fingerprint changed")
    source_probe = writer.read_exact(
        source_fd,
        xiso_pack.byte_offset + record.pack_offset - COLOUR_OFFSET,
        RECORD_PROBE_BYTES,
    )
    with record.pack_path.open("rb") as stream:
        stream.seek(record.pack_offset - COLOUR_OFFSET)
        cached_probe = stream.read(RECORD_PROBE_BYTES)
    _require(source_probe == cached_probe,
             f"uniform set {record.selector} source/cache provenance disagrees")
    retail = source_probe[COLOUR_OFFSET:COLOUR_OFFSET + 8]
    _require(replacement != retail,
             f"{record.selector} already uses the chosen colours")
    absolute = xiso_pack.byte_offset + record.pack_offset
    target = {
        "pack_offset": record.pack_offset,
        "selector": f"unif_color:{record.selector}",
        "span_sha256": _digest(retail),
        "span_size": 8,
        "xiso_absolute_span_offset": absolute,
        "xiso_pack_path": pack_path,
        "xiso_pack_sector": xiso_pack.sector,
        "xiso_pack_sha256": pack_sha256,
        "xiso_pack_size": xiso_pack.size,
    }
    report = {
        "schema": "nfl2k5_unif_color_import/v2",
        "uniform_selector": record.selector,
        "outer_index": record.outer_index,
        "outer_name_id": f"0x{record.outer_name_id:08x}",
        "facemask_faceshield_argb": f"{facemask:08X}",
        "turtleneck_argb": f"{turtleneck:08X}",
        "replacement_sha256": _digest(replacement),
        "retail_sha256": _digest(retail),
        "retail_sector_reference": retail_sector,
        "note": "Word 0 jointly tints the facemask/faceshield; word 1 is "
                "HI_turtleneck. No separate visor field is proved. This edit "
                "changes only the selected physical uniform record.",
        "target": dict(target),
    }
    return [(replacement, [], report, str(target["selector"]), target)]


__all__ = [
    "COLOUR_OFFSET",
    "PACK_PROVENANCE",
    "RECORD_TAG_OFFSET",
    "UNIF_COLOR_KIND",
    "UNIFORM_SELECTOR_RE",
    "UniformColorRecord",
    "UnifColorWriterError",
    "build_unif_color_imports",
    "parse_color",
    "resolve_uniform_color_record",
]
