"""Say which disc image this is, before any step refuses it.

Every failure this exists for arrived as a number the user could not act on.
Build & Share -> Advanced died with

    ValueError: pack-0 schedule template is foreign: ROST stored size is not retail

and Apply refused with

    MISMATCH: 2802 run(s) hold bytes that are neither the expected base nor the
    patched bytes

Both sentences are true and neither one says the useful thing, which is *what
kind of image the user handed us*.  A dump of an Xbox disc is not one canonical
file, and four different things arrive under the same ``ESPN NFL 2K5 (USA).iso``
name:

* an extracted ``.xiso`` -- the game partition is the whole file;
* a raw / redump-style dump -- the video partition is still in front, so every
  file sits ``0x18300000`` (XGD1) or ``0x0FD90000`` (XGD2) bytes further in;
* a **repack** -- somebody unpacked the disc and rebuilt it, so the file *bytes*
  are retail but they live at other sectors;
* a **pre-modded** image -- someone else's roster or gameplay mod is already in
  ``vc_53450030/0`` or ``default.xbe``.

The first two are fine and every writer handles them, because every writer
resolves files through the XDVDFS directory.  The third builds fine and can
never take a byte-run ``.2k5patch``, because a patch addresses bytes by their
position in the game partition and a repack moved them.  The fourth cannot be
built from at all: the studio's writers start from retail bytes.

So identify the image first: find ``default.xbe`` and ``vc_53450030/0``
through the directory, hash them, compare their positions with the retail
layout, and hand the caller one sentence naming which of the five cases this
is.  Nothing here writes, and the identity is cheap enough to show in a panel
header before the user presses anything.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --------------------------------------------------------------------------
# Retail facts.  Offsets are relative to the game partition, so they hold for
# an .xiso (base 0) and for a raw dump (base 0x18300000) alike.

RETAIL_XISO_SIZE = 6_300_499_968
RETAIL_XBE_PATH = "default.xbe"
RETAIL_XBE_SIZE = 11_948_032
RETAIL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
RETAIL_PACK0_PATH = "vc_53450030/0"
RETAIL_PACK0_SIZE = 193_710_080
RETAIL_PACK0_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

# The ROST outer entry inside pack 0: the resource the 2026 schedule step reads.
# Hashing 594 KiB says "this pack still carries the retail roster template"
# without reading 193 MB, which is what makes this cheap enough for a header line.
ROST_OFFSET_IN_PACK0 = 0x392800
ROST_OUTER_SIZE = 0x90F80
RETAIL_ROST_SHA256 = "a5cf52fa5d1f2ecf911ef093a1afe6d3e4efbb2ce4d794b876c15a3ad537bacd"

# (path, partition-relative byte offset, size) for every file the retail disc
# holds, in disc order.  A repack keeps the names and sizes and changes the
# offsets; that is exactly what tells a repack from a dump.
# The dashboard updaters: present on a real disc, absent from plenty of legal images, and read
# by nothing the studio does. Their absence is worth mentioning and never worth a refusal.
OPTIONAL_FILES = frozenset({"update.xbe", "dashupdate.xbe"})

RETAIL_LAYOUT: tuple[tuple[str, int, int], ...] = (
    ("update.xbe", 0x11000, 2_326_528),
    ("default.xbe", 0x249000, 11_948_032),
    ("dashupdate.xbe", 0xDAE000, 58_421_248),
    ("vc_53450030/9", 0x4565800, 634_941_440),
    ("vc_53450030/5", 0x2A2EC800, 307_972_096),
    ("vc_53450030/3", 0x3C8A1000, 315_508_736),
    ("vc_53450030/1", 0x4F585800, 299_999_232),
    ("vc_53450030/0", 0x6139F800, 193_710_080),
    ("vc_53450030/2", 0x6CC5C000, 309_252_096),
    ("vc_53450030/4", 0x7F349000, 313_178_112),
    ("vc_53450030/7", 0x91DF4800, 319_197_184),
    ("vc_53450030/6", 0xA4E5D800, 458_231_808),
    ("vc_53450030/8", 0xC035E800, 929_370_112),
    ("vc_53450030/D", 0xF79AF800, 309_135_360),
    ("vc_53450030/B", 0x10A080000, 458_248_192),
    ("vc_53450030/A", 0x125585000, 310_294_528),
    ("vc_53450030/C", 0x137D70800, 315_131_904),
    ("vc_53450030/E", 0x14A9F9000, 301_813_760),
    ("vc_53450030/F", 0x15C9CE000, 451_733_504),
)

# The five answers.  These strings are the product: every refusal quotes one.
RETAIL_XISO = "retail dump (xiso)"
RETAIL_RAW = "retail dump (raw/redump with video partition)"
REPACK = ("repacked disc (retail files, different layout: rebuild your image with "
          "extract-xiso -r or use the original dump)")
MODIFIED = ("modified disc (pack 0 / default.xbe differ from retail: this image "
            "already carries a mod; start from a clean retail dump)")
UNKNOWN = "unknown image"

KIND_RETAIL_XISO = "retail-xiso"
KIND_RETAIL_RAW = "retail-raw"
KIND_REPACK = "repack"
KIND_MODIFIED = "modified"
KIND_UNKNOWN = "unknown"
KIND_NOT_A_DISC = "not-a-disc"

CHUNK = 1 << 24


class DiscIdentityError(ValueError):
    pass


def _xdvdfs_module():
    """The proven XDVDFS reader lives in tools/; import it lazily."""

    try:
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc
    except ImportError:
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc


@dataclass(frozen=True)
class DiscIdentity:
    """What this image is, in one sentence plus the evidence behind it."""

    kind: str
    headline: str
    detail: str
    partition_base: int | None = None
    image_size: int = 0
    layout: str = "unknown"          # "retail" | "relocated" | "unknown"
    files: Mapping[str, Any] = field(default_factory=dict)
    is_retail_image: bool = False    # an .xiso of retail size whose game files are retail
    checked_pack0_fully: bool = False

    @property
    def retail_files(self) -> bool:
        """The game files this looked at are byte-for-byte retail."""

        return self.kind in (KIND_RETAIL_XISO, KIND_RETAIL_RAW, KIND_REPACK)

    @property
    def can_build(self) -> bool:
        """Build & Share resolves every file through the directory, so a repack builds."""

        return self.retail_files

    @property
    def can_take_a_byte_run_patch(self) -> bool:
        """A ``.2k5patch`` addresses bytes by position, which a repack moved."""

        return self.kind in (KIND_RETAIL_XISO, KIND_RETAIL_RAW)

    def line(self) -> str:
        return f"{self.headline}. {self.detail}" if self.detail else self.headline

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "headline": self.headline,
            "detail": self.detail,
            "partition_base": self.partition_base,
            "image_size": self.image_size,
            "layout": self.layout,
            "files": dict(self.files),
            "is_retail_image": self.is_retail_image,
            "retail_files": self.retail_files,
            "can_build": self.can_build,
            "can_take_a_byte_run_patch": self.can_take_a_byte_run_patch,
        }

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.line()


def _sha256_range(xc, descriptor: int, offset: int, length: int) -> str:
    digest = hashlib.sha256()
    done = 0
    while done < length:
        want = min(CHUNK, length - done)
        digest.update(xc.read_exact(descriptor, offset + done, want))
        done += want
    return digest.hexdigest()


def _container(base: int | None) -> str:
    if base is None:
        return "an unreadable container"
    return "an xiso" if base == 0 else f"a raw dump (game partition at 0x{base:X})"


def identify_descriptor(descriptor: int, size: int, *, pack0: bytes | None = None,
                        deep: bool = False) -> DiscIdentity:
    """Identify the already-open image; never seeks past what it reports.

    ``pack0`` lets a caller that has already read ``vc_53450030/0`` hand the
    bytes in, so the schedule step's refusal costs nothing extra.  ``deep``
    hashes the whole 193 MB pack instead of its ROST resource.
    """

    xc = _xdvdfs_module()
    try:
        base = int(xc.locate_xdvdfs_base(descriptor, size))
    except Exception as exc:  # noqa: BLE001 -- any parse failure means "not a disc image"
        detail = str(exc).strip() or "No Xbox filesystem was found in this file."
        return DiscIdentity(kind=KIND_NOT_A_DISC, headline=UNKNOWN, detail=detail,
                            partition_base=None, image_size=size)

    try:
        entries, _directory = xc.parse_xdvdfs(descriptor, size, base)
    except Exception as exc:  # noqa: BLE001
        return DiscIdentity(kind=KIND_UNKNOWN, headline=UNKNOWN, image_size=size, partition_base=base,
                            detail=f"The game partition at 0x{base:X} has a directory this reader cannot walk: {exc}")

    found: dict[str, Any] = {}
    missing: list[str] = []
    wrong_size: list[str] = []
    relocated: list[str] = []
    # The dashboard updaters are the only files the studio never reads: images that drop or
    # shorten them are common and change nothing, so they are reported rather than refused.
    # Everything else -- default.xbe and every vc_53450030 pack -- has to be its retail self.
    essential = (RETAIL_XBE_PATH, RETAIL_PACK0_PATH)
    for path, retail_offset, retail_size in RETAIL_LAYOUT:
        entry = entries.get(path.casefold())
        if entry is None or (entry.attributes & 0x10):
            missing.append(path)
            continue
        relative = int(entry.byte_offset) - base
        record = {"offset": relative, "size": int(entry.size),
                  "retail_offset": retail_offset, "retail_size": retail_size,
                  "at_retail_offset": relative == retail_offset,
                  "retail_size_ok": int(entry.size) == retail_size}
        found[path] = record
        if not record["retail_size_ok"]:
            wrong_size.append(path)
        elif not record["at_retail_offset"]:
            relocated.append(path)

    if any(path not in found for path in essential):
        gone = ", ".join(path for path in essential if path not in found)
        return DiscIdentity(
            kind=KIND_UNKNOWN, headline=UNKNOWN, image_size=size, partition_base=base, files=found,
            detail=(f"This is {_container(base)} whose directory has no {gone}. "
                    "It is not ESPN NFL 2K5."))

    # --- content -----------------------------------------------------------
    xbe = found[RETAIL_XBE_PATH]
    if xbe["retail_size_ok"]:
        xbe["sha256"] = _sha256_range(xc, descriptor, base + xbe["offset"], xbe["size"])
        xbe["retail"] = xbe["sha256"] == RETAIL_XBE_SHA256
    else:
        xbe["retail"] = False

    pack = found[RETAIL_PACK0_PATH]
    checked_fully = False
    if not pack["retail_size_ok"]:
        pack["retail"] = False
    elif pack0 is not None and len(pack0) == RETAIL_PACK0_SIZE:
        pack["sha256"] = hashlib.sha256(pack0).hexdigest()
        pack["retail"] = pack["sha256"] == RETAIL_PACK0_SHA256
        pack["rost_sha256"] = hashlib.sha256(
            pack0[ROST_OFFSET_IN_PACK0: ROST_OFFSET_IN_PACK0 + ROST_OUTER_SIZE]).hexdigest()
        checked_fully = True
    elif deep:
        pack["sha256"] = _sha256_range(xc, descriptor, base + pack["offset"], pack["size"])
        pack["retail"] = pack["sha256"] == RETAIL_PACK0_SHA256
        checked_fully = True
    else:
        # the roster resource only: 594 KiB instead of 193 MB
        pack["rost_sha256"] = _sha256_range(
            xc, descriptor, base + pack["offset"] + ROST_OFFSET_IN_PACK0, ROST_OUTER_SIZE)
        pack["retail"] = pack["rost_sha256"] == RETAIL_ROST_SHA256

    is_retail_image = False
    if size == RETAIL_XISO_SIZE and base == 0 and xbe.get("retail") and pack.get("retail"):
        is_retail_image = True

    incomplete = sorted(set(missing) | set(wrong_size))
    needed = [path for path in incomplete if path not in OPTIONAL_FILES]
    layout = "unknown" if needed else ("relocated" if relocated else "retail")
    spare = [path for path in incomplete if path in OPTIONAL_FILES]
    aside = (f" ({', '.join(spare)} is missing or not its retail size; a full dump has it, and "
             "nothing the studio reads depends on it.)") if spare else ""

    # --- the answer --------------------------------------------------------
    if needed:
        broken = ", ".join(needed[:4])
        return DiscIdentity(
            kind=KIND_UNKNOWN, headline=UNKNOWN, image_size=size, partition_base=base,
            layout=layout, files=found, checked_pack0_fully=checked_fully,
            detail=(f"This is {_container(base)} holding ESPN NFL 2K5, but {broken} is missing or "
                    "not its retail size. Neither Build nor Apply can trust it; use a dump of your "
                    "own retail disc." + aside))

    if not xbe.get("retail") or not pack.get("retail"):
        which = []
        if not xbe.get("retail"):
            which.append("default.xbe")
        if not pack.get("retail"):
            which.append("vc_53450030/0" + ("" if checked_fully else " (its ROST roster resource)"))
        intact = [name for name, ok in (("default.xbe", xbe.get("retail")),
                                        ("vc_53450030/0", pack.get("retail"))) if ok]
        verb = "does" if len(which) == 1 else "do"
        detail = (f"Read as {_container(base)}. {' and '.join(which)} {verb} not match retail"
                  + (f", while {' and '.join(intact)} still {'does' if len(intact) == 1 else 'do'}"
                     if intact else "")
                  + ". Build starts from retail bytes, so it refuses this. Take a fresh dump of "
                    "your own disc and build again." + aside)
        return DiscIdentity(kind=KIND_MODIFIED, headline=MODIFIED, detail=detail, image_size=size,
                            partition_base=base, layout=layout, files=found,
                            checked_pack0_fully=checked_fully)

    if relocated:
        moved = len(relocated)
        detail = (f"Read as {_container(base)}. The game files are byte-for-byte retail, but {moved} of "
                  f"{len(RETAIL_LAYOUT)} sit at other sectors than a real dump (for example "
                  f"{relocated[0]} at 0x{found[relocated[0]]['offset']:X} instead of "
                  f"0x{found[relocated[0]]['retail_offset']:X}). Build & Share works (it finds every "
                  "file through the disc directory), but a .2k5patch addresses bytes by their "
                  "position and this image moved them, so Apply cannot use it. Build the mod "
                  "yourself on the Build tab instead of applying a patch file." + aside)
        return DiscIdentity(kind=KIND_REPACK, headline=REPACK, detail=detail, image_size=size,
                            partition_base=base, layout=layout, files=found,
                            checked_pack0_fully=checked_fully)

    if base == 0:
        detail = ("The game partition is the whole file, and every file sits where a retail disc "
                  "puts it. Build and Apply both work." + aside)
        return DiscIdentity(kind=KIND_RETAIL_XISO, headline=RETAIL_XISO, detail=detail, image_size=size,
                            partition_base=base, layout=layout, files=found,
                            is_retail_image=is_retail_image, checked_pack0_fully=checked_fully)
    detail = (f"The video partition is still in front, so the game partition starts at 0x{base:X}, "
              "and every file sits where a retail disc puts it. Build and Apply both work, and the "
              "file size differing from a patch author's base is expected." + aside)
    return DiscIdentity(kind=KIND_RETAIL_RAW, headline=RETAIL_RAW, detail=detail, image_size=size,
                        partition_base=base, layout=layout, files=found,
                        checked_pack0_fully=checked_fully)


def identify(image: Path | str, *, pack0: bytes | None = None, deep: bool = False) -> DiscIdentity:
    """Identify a disc image by path (read-only, never written)."""

    path = Path(image).expanduser()
    try:
        stat = os.lstat(path)
    except OSError as exc:
        raise DiscIdentityError(f"cannot read {path}: {exc}") from exc
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        return identify_descriptor(descriptor, stat.st_size, pack0=pack0, deep=deep)
    finally:
        os.close(descriptor)


def describe(image: Path | str, *, pack0: bytes | None = None, deep: bool = False) -> str:
    """One line naming the image, or one line saying why it could not be read."""

    try:
        return identify(image, pack0=pack0, deep=deep).line()
    except (DiscIdentityError, OSError) as exc:
        return f"{UNKNOWN} — {exc}"


def note_for(image: Path | str | None, *, pack0: bytes | None = None, deep: bool = False) -> str:
    """``This image is: <line>`` for appending to a refusal ("" when unavailable)."""

    if image is None:
        return ""
    try:
        identity = identify(image, pack0=pack0, deep=deep)
    except (DiscIdentityError, OSError):
        return ""
    return f"This image is: {identity.line()}"


__all__ = [
    "DiscIdentity",
    "DiscIdentityError",
    "MODIFIED",
    "REPACK",
    "RETAIL_LAYOUT",
    "RETAIL_PACK0_SHA256",
    "RETAIL_RAW",
    "RETAIL_ROST_SHA256",
    "RETAIL_XBE_SHA256",
    "RETAIL_XISO",
    "UNKNOWN",
    "describe",
    "identify",
    "identify_descriptor",
    "note_for",
]
