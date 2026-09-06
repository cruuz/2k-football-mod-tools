"""The ``SHPS`` art: catalogued everywhere, exported where it decodes, written back where it can be.

Every texture on this disc is an ``SHPS`` bank inside an EA ``BIG`` archive
(:mod:`mod_editor.games._formats.ea_shps`, :mod:`~mod_editor.games._formats.ea_big`).
Two codes decode -- 8-bit indexed (``0x02``) and direct 32-bit (``0x05``) --
and one, ``0x0E``, is the block codec whose per-pixel selectors are not decoded
(the note :data:`ea_shps.CODE_NOTES` carries says what was measured).

Two lane classes share one catalogue walker:

* :class:`ShpsArtLane` -- an ``ArtLane``: preview, Export PNG, Import PNG and
  Build.  An edited PNG is indexed against the image's **own** palette, the
  level-0 pixel bytes are replaced in place (same size), the bank is re-packed
  with RefPack when the disc packed it and put back inside its entry's slot,
  and the archive goes back inside its ISO9660 extent.  Direct-colour images
  export and are not written (no encoder for ``0x05`` is offered here).
* :class:`ShpsBankLane` -- a ``ReadOnlyLane`` for the archives that are
  entirely ``0x0E``: every bank and image listed with its dimensions and the
  measured refusal, nothing drawn and nothing written.

PCSX2 replacement identities come from two places.  They are **derived** for
8-bit images with a 256-entry palette and power-of-two sides through the shared
:mod:`~mod_editor.games._formats.pcsx2_texture_name` -- a computation over the
texture's own bytes -- and they are **confirmed** for the images a PCSX2
texture dump of this game has actually shown, by pairing that dump with the
disc on exact pixel equality (``tools/mvp05_ps2_texture_identities.py``, table
at :data:`IDENTITY_DOCUMENT`).  A confirmed name is what the emulator wrote; a
derived one is what it would write.  :meth:`ShpsArtLane.replacement_identity`
answers with the confirmed name where there is one and says which it is either
way.  **Evidence tags.**  **[M]** measured on the retail disc.
"""

from __future__ import annotations

import argparse
import binascii
import json
from pathlib import Path
import re
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import zlib

from mod_editor.games._formats import ea_big, ea_shps, pcsx2_texture_name
from mod_editor.games.contract import (
    Catalogue, Edit, EncodedArt, Field, Plan, Receipt, Refusal, Target, Verdict, require,
)

from . import containers, disc_write

MAX_TARGETS = 4000
#: ``MODELS.BIG``'s own cap.  The default 4,000 would reach 130 of its 1,407
#: banks, so a modder could not open nine kits in ten; the whole archive is
#: 30,535 images, and building every target from a walked catalogue costs 0.4 s
#: and no measurable memory [M], so the bound is set above the archive instead
#: of inside it.
MODELS_TARGETS = 32000
DERIVED_PREFIX = "derived:"
CONFIRMED_PREFIX = "confirmed:"

#: The tool that writes the identity table, and where it writes it.  The lane
#: owns both because the lane is what reads the table.
IDENTITY_TOOL = "tools/mvp05_ps2_texture_identities.py"
IDENTITY_SCHEMA = "mvp05_ps2_pcsx2_texture_identities/v1"
IDENTITY_DOCUMENT = Path("docs/product/measured/mvp05_ps2/pcsx2-texture-identities.json")

#: What the whole corpus is, said once.  Three frames is three frames: it names
#: the images those frames drew and nothing else, and every sentence below is
#: careful to say which of the two kinds of name it is offering.
DUMP_CORPUS = ("The one PCSX2 texture dump of this game here is three frames -- a Cardinals "
               "game at Fenway -- so a confirmed name exists only for what those frames drew; "
               "the table is docs/product/measured/mvp05_ps2/pcsx2-texture-identities.json.")
NOT_CONFIRMED = ("No frame of that dump drew this texture, so the name offered is derived from "
                 "the texture's own bytes and is not confirmed. " + DUMP_CORPUS)
NO_DUMP = NOT_CONFIRMED

#: The GS modes an 8-bit image on this disc is known to be drawn in.  The dump
#: shows both: 8-bit textures uploaded as ``PSMT8`` and, for eighteen of the
#: park textures it reached, as the high-byte ``PSMT8H`` -- a different ``bits``
#: word *and* a different TEX0 hash for the same pixels [M].  Nothing on the
#: disc says which a draw will use, so both names are offered.
EXTRA_PSMS: Tuple[int, ...] = (pcsx2_texture_name.PSMT8H,)

#: Cache: one parsed identity table per resolved path, read once per process.
_IDENTITY_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _identity_table(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """``<archive>:<entry>:<image> -> {"names": {...}, "frames": [...]}``, or nothing at all.

    An empty mapping is the honest answer when the table is absent, and it is
    the state this lane shipped in: no name is invented and every sentence
    falls back to the derived one.
    """

    if path is None:
        return {}
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path(__file__).resolve().parents[3] / resolved
    cached = _IDENTITY_CACHE.get(str(resolved))
    if cached is not None:
        return cached
    out: Dict[str, Dict[str, Any]] = {}
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        document = {}
    if isinstance(document, Mapping) and document.get("schema") == IDENTITY_SCHEMA:
        for key, entry in (document.get("identities") or {}).items():
            names = entry.get("names") if isinstance(entry, Mapping) else None
            if isinstance(names, Mapping) and names:
                out[str(key)] = {
                    "names": {str(convention): list(values)
                              for convention, values in names.items() if values},
                    "frames": list(entry.get("frames") or ()),
                    # What the image *is*, so a name cannot land on a different
                    # image that happens to sit at the same key.  A key is a
                    # position -- archive, entry, image -- and a position is not
                    # an identity: the synthetic disc the tests run on reuses
                    # the real archive names on purpose.
                    "shape": (int(entry.get("width") or 0), int(entry.get("height") or 0),
                              str(entry.get("code") or "")),
                }
    _IDENTITY_CACHE[str(resolved)] = out
    return out


def load_identities(path: Optional[Path] = IDENTITY_DOCUMENT
                    ) -> Dict[str, Dict[str, List[str]]]:
    """``<archive>:<entry>:<image> -> {convention: [filenames]}`` a dump confirmed."""

    return {key: entry["names"] for key, entry in _identity_table(path).items()}


def _coverage_sentence(totals: Mapping[str, Any]) -> str:
    """What this page's own numbers say about naming, said without rounding up."""

    images = int(totals.get("images", 0))
    named = int(totals.get("named", 0))
    confirmed = int(totals.get("confirmed", 0))
    return (f"{confirmed:,} of this page's {images:,} image(s) have a name a PCSX2 dump "
            f"confirmed and {named:,} have one derived from their own bytes; the rest have "
            f"neither. {DUMP_CORPUS}")


def _key(archive: str, entry: int, image: int) -> str:
    return f"{archive}:{entry}:{image}"


def parse_key(key: str) -> Tuple[str, int, int]:
    match = re.match(r"^(.+):(\d+):(\d+)$", str(key))
    if match is None:
        raise Refusal(f"{key!r} does not name a texture: a key is <archive>:<entry>:<image>, "
                      f"as the catalogue writes it.")
    return match.group(1), int(match.group(2)), int(match.group(3))


# -- PNG in, without Pillow --------------------------------------------------

def read_rgba_png(payload: bytes) -> Tuple[int, int, bytes]:
    """An 8-bit, non-interlaced PNG (grey, grey+alpha, RGB, RGBA or palette) as RGBA."""
    require(payload[:8] == b"\x89PNG\r\n\x1a\n", "that file is not a PNG.")
    position = 8
    width = height = 0
    colour = depth = interlace = 0
    idat = bytearray()
    palette: List[Tuple[int, int, int]] = []
    trns = b""
    while position + 8 <= len(payload):
        length, = struct.unpack_from(">I", payload, position)
        tag = payload[position + 4:position + 8]
        body = payload[position + 8:position + 8 + length]
        position += 12 + length
        if tag == b"IHDR":
            width, height, depth, colour, _c, _f, interlace = struct.unpack(">IIBBBBB", body[:13])
        elif tag == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body) - 2, 3)]
        elif tag == b"tRNS":
            trns = bytes(body)
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    require(width > 0 and height > 0, "that PNG declares no size.")
    require(depth == 8, f"that PNG is {depth}-bit; give an 8-bit PNG.")
    require(interlace == 0, "that PNG is interlaced; give a non-interlaced PNG.")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colour)
    require(channels is not None, f"that PNG uses colour type {colour}, which is not read here.")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    require(len(raw) == (stride + 1) * height, "that PNG's pixel data does not match its size.")
    rows: List[bytearray] = []
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filter_type = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = previous[x]
            c = previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                line[x] = (line[x] + a) & 0xFF
            elif filter_type == 2:
                line[x] = (line[x] + b) & 0xFF
            elif filter_type == 3:
                line[x] = (line[x] + ((a + b) >> 1)) & 0xFF
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 0xFF
            else:
                require(filter_type == 0, f"that PNG uses filter {filter_type}, which is not a PNG filter.")
        rows.append(line)
        previous = line
    out = bytearray()
    for line in rows:
        if colour == 6:
            out += line
        elif colour == 2:
            for x in range(width):
                out += line[x * 3:x * 3 + 3] + b"\xff"
        elif colour == 0:
            for x in range(width):
                out += bytes((line[x], line[x], line[x], 255))
        elif colour == 4:
            for x in range(width):
                out += bytes((line[x * 2], line[x * 2], line[x * 2], line[x * 2 + 1]))
        else:
            for x in range(width):
                index = line[x]
                require(index < len(palette), "that PNG indexes past its own palette.")
                alpha = trns[index] if index < len(trns) else 255
                out += bytes(palette[index]) + bytes((alpha,))
    return width, height, bytes(out)


# -- the catalogue walker -----------------------------------------------------

def _identities(bank: ea_shps.ShpsBank, image: ea_shps.ShpsImage) -> Tuple[Dict[str, List[str]], str]:
    pixels = image.pixels
    if pixels is None or pixels.code != ea_shps.CODE_INDEXED8 or image.palette is None:
        return {}, "no name is derived: only an 8-bit indexed image with its own palette is named"
    if image.palette.width != ea_shps.CSM1_ENTRIES:
        return {}, ("no name is derived: this image's palette has %d entries and PCSX2 hashes a "
                    "256-entry CLUT for an 8-bit texture" % image.palette.width)
    payload = bank.block_bytes(pixels)
    levels = []
    width, height = pixels.width, pixels.height
    cursor = 0
    while width >= 1 and height >= 1 and cursor + width * height <= len(payload):
        levels.append(pcsx2_texture_name.TextureLevel(width, height, 8,
                                                      payload[cursor:cursor + width * height]))
        cursor += width * height
        if width == 1 and height == 1:
            break
        width, height = max(1, width // 2), max(1, height // 2)
        if len(levels) > 1 and cursor >= len(payload):
            break
    if not levels:
        return {}, "no name is derived: the pixel block holds no whole level"
    if len(levels) > 1 and cursor != len(payload):
        levels = levels[:1]
    try:
        palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
        derived = pcsx2_texture_name.derive_names(levels, palette, extra_psms=EXTRA_PSMS)
    except Refusal as exc:
        return {}, f"no name is derived: {exc}"
    return pcsx2_texture_name.names_by_convention(derived), ""


# -- MODELS.BIG: which bank is what, and which part is writable ---------------

#: How a catalogue row spells the one pixel code this lane writes back.
INDEXED8 = "0x%02x" % ea_shps.CODE_INDEXED8

PARTS_SCHEMA = "mvp05_ps2_models_big_parts/v1"
PARTS_DOCUMENT = Path("docs/product/measured/mvp05_ps2/models-big-parts.json")
PARTS_COMMAND = ("python -m mod_editor.games.mvp05_ps2.art_lane --lane kits --source <iso> "
                 "--parts docs/product/measured/mvp05_ps2/models-big-parts.json")

#: ``MODELS.BIG``'s bank families, by the name each carries [M].  ``kit`` banks
#: hold the 32 parts a player wears, ``lettering`` banks the 26 letters and 10
#: digits of the name and number decals, ``head`` banks one face texture each.
#: The numbered families key on a three-digit number; the four named banks are
#: generic (two umpire kits, a create-a-team base kit, a shared font).
_KIT_BANK = re.compile(r"^u(\d{3})([a-z])\.ssh$", re.IGNORECASE)
_LETTERING_BANK = re.compile(r"^[fa](\d{3})([a-z])\.ssh$", re.IGNORECASE)
_HEAD_BANK = re.compile(r"^c(\d{3})\.ssh$", re.IGNORECASE)
_NAMED_BANKS = {"umpire.ssh": "kit", "umpirec.ssh": "kit", "uniform.ssh": "kit",
                "teamfont.ssh": "lettering"}

#: How a numbered bank names its club, measured and not assumed: ``team.dat``
#: column 6 ``team_artid`` runs 1..126 over the table's 126 rows and the ``u``
#: and ``f`` families each carry exactly the numbers 0..125, so
#: ``team_artid - 1`` is the bank number and the map is a bijection [M].  The
#: club's own name is a cell of that table and stays on the user's disc.
TEAM_ARTID_RULE = ("A numbered bank u<nnn><v>.ssh or f<nnn><v>.ssh belongs to the club whose "
                   "DATABASE.BIG!team.dat row carries team_artid == nnn + 1; the 126 artids and "
                   "the 126 bank numbers are a bijection, measured on the retail disc. <v> is the "
                   "uniform variant, a..p. The four named banks (umpire, umpirec, uniform, "
                   "teamfont) belong to no club.")


def bank_family(name: str) -> Tuple[str, Optional[int], Optional[str]]:
    """``(family, bank number, variant)`` for a ``MODELS.BIG`` member name.

    A name this does not recognise is ``("other", None, None)`` rather than a
    guess, so a bank the disc adds is listed and not mis-attributed.
    """

    lowered = name.lower()
    if lowered in _NAMED_BANKS:
        return _NAMED_BANKS[lowered], None, None
    for pattern, family in ((_KIT_BANK, "kit"), (_LETTERING_BANK, "lettering"),
                            (_HEAD_BANK, "head")):
        match = pattern.match(lowered)
        if match is not None:
            groups = match.groups()
            return family, int(groups[0]), (groups[1] if len(groups) > 1 else None)
    return "other", None, None


def parts_census(rows: Sequence[Mapping[str, Any]], *, source: str = "",
                 identities: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The per-part-tag table: how many of each tag are writable, and at what sizes.

    One row per four-character part tag, because that -- not the bank -- is what
    a modder is choosing between: ``llod`` is the whole kit at low detail and is
    8-bit, ``jers`` is the same kit at high detail and is code 0x0e.
    """

    families: Dict[str, Dict[str, Any]] = {}
    parts: Dict[str, Dict[str, Any]] = {}
    banks: Dict[Tuple[str, int], Dict[str, Any]] = {}
    totals = {"banks": 0, "images": 0, "writable": 0}
    codes: Dict[str, int] = {}
    for row in rows:
        name = str(row.get("entry_name", ""))
        family, number, variant = bank_family(name)
        code = str(row.get("code", ""))
        tag = str(row.get("tag", ""))
        writable = bool(row.get("decodable")) and code == INDEXED8
        key = (str(row.get("archive", "")), int(row.get("entry", -1)))
        bank = banks.setdefault(key, {"archive": key[0], "entry": key[1], "bank": name,
                                      "family": family, "number": number, "variant": variant,
                                      "images": 0, "writable": 0})
        bank["images"] += 1
        bank["writable"] += int(writable)
        group = families.setdefault(family, {"family": family, "banks": 0, "images": 0,
                                             "writable": 0, "codes": {}})
        group["images"] += 1
        group["writable"] += int(writable)
        group["codes"][code] = group["codes"].get(code, 0) + 1
        part = parts.setdefault(tag, {"tag": tag, "images": 0, "writable": 0, "codes": {},
                                      "families": [], "sizes": {}})
        part["images"] += 1
        part["writable"] += int(writable)
        part["codes"][code] = part["codes"].get(code, 0) + 1
        if family not in part["families"]:
            part["families"].append(family)
        size = "%dx%d" % (int(row.get("width", 0)), int(row.get("height", 0)))
        part["sizes"][size] = part["sizes"].get(size, 0) + 1
        if row.get("confirmed_names"):
            part["confirmed"] = part.get("confirmed", 0) + 1
            group["confirmed"] = group.get("confirmed", 0) + 1
        codes[code] = codes.get(code, 0) + 1
        totals["images"] += 1
        totals["writable"] += int(writable)
    for bank in banks.values():
        families[bank["family"]]["banks"] += 1
    totals["banks"] = len(banks)
    for part in parts.values():
        part["families"].sort()
    return {
        "schema": PARTS_SCHEMA, "source": source, "generated_by": PARTS_COMMAND,
        "totals": {**totals, "codes": codes, **(dict(identities) if identities else {})},
        "team_artid_rule": TEAM_ARTID_RULE, "confirmed_note": DUMP_CORPUS,
        "families": [families[name] for name in sorted(families)],
        "parts": sorted(parts.values(), key=lambda part: (-part["images"], part["tag"])),
        "banks": sorted(banks.values(), key=lambda bank: (bank["archive"], bank["entry"])),
        "runtime_note": disc_write.NOT_BOOTED,
    }


def slot_fit_census(source: Path, archives: Sequence[str], *,
                    progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """How many banks re-pack inside the slot their entry already owns, and by how much.

    This is the writer's real bound, and it is worth measuring rather than
    assuming: the archive is rewritten in place, so a bank that packs larger
    than its slot is refused naming the byte count.  The number here is for the
    banks *unedited*; an edit that compresses worse can still be refused, which
    is why the refusal exists and why this census is the floor, not a promise.
    """

    banks: List[Dict[str, Any]] = []
    with containers.Disc(Path(source)) as disc:
        for name, entry in containers.archives_named(disc, tuple(archives)):
            if progress is not None:
                progress(f"{name}…")
            archive = disc.archive(entry)
            for row in archive.entries:
                if row.size == 0 or archive.entry_format(row.index) != "SHPS":
                    continue
                payload = archive.member(row.index)
                packed = archive.is_compressed(row.index)
                stored = len(ea_big.refpack_compress(payload)) if packed else len(payload)
                slot = archive.slot_bytes(row.index)
                banks.append({"archive": name, "entry": row.index, "bank": row.name,
                              "family": bank_family(row.name)[0], "packed": packed,
                              "plain_bytes": len(payload), "stored_bytes": row.size,
                              "slot_bytes": slot, "repacked_bytes": stored,
                              "headroom": slot - stored})
    headroom = sorted(bank["headroom"] for bank in banks)
    families: Dict[str, Dict[str, int]] = {}
    for bank in banks:
        group = families.setdefault(bank["family"], {"banks": 0, "fit": 0})
        group["banks"] += 1
        group["fit"] += int(bank["headroom"] >= 0)
    return {
        "banks": len(banks), "fit": sum(1 for value in headroom if value >= 0),
        "headroom_min": headroom[0] if headroom else None,
        "headroom_median": headroom[len(headroom) // 2] if headroom else None,
        "headroom_max": headroom[-1] if headroom else None,
        "by_family": families,
        "over_the_slot": sorted(({"bank": bank["bank"], "entry": bank["entry"],
                                  "over_by": -bank["headroom"]}
                                 for bank in banks if bank["headroom"] < 0),
                                key=lambda row: (-row["over_by"], row["entry"])),
        "note": ("Measured with the banks unedited: our RefPack encoder against EA's stream, "
                 "into the slot the entry already owns. A bank over its slot is refused naming "
                 "the byte count, and an edit that compresses worse than the pixels it replaced "
                 "can push a bank that fits here over the line."),
    }


class _Walker:
    """Walks the banks of a set of archives; shared by both lane classes."""

    def __init__(self, archives: Sequence[str] = (), *, stadiums: bool = False,
                 loading_screens: bool = False, script_archives: Sequence[str] = ()) -> None:
        self.archives = tuple(archives)
        self.stadiums = stadiums
        self.loading_screens = loading_screens
        self.script_archives = tuple(script_archives)

    def entries(self, disc: containers.Disc) -> List[Tuple[str, Any]]:
        out = containers.archives_named(disc, self.archives)
        if self.stadiums:
            out += [(e.path.rsplit("/", 1)[-1], e) for e in disc.stadium_archives()]
        if self.loading_screens:
            out += [(e.path.rsplit("/", 1)[-1], e) for e in disc.loading_screens()]
        return out

    def walk(self, source: Path, progress: Optional[Callable[[str], None]], *,
             with_identities: bool,
             identities: Optional[Mapping[str, Mapping[str, Sequence[str]]]] = None
             ) -> Dict[str, Any]:
        confirmed_table = identities or {}
        rows: List[Dict[str, Any]] = []
        archives_out: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        reasons: Dict[str, int] = {}
        codes: Dict[str, int] = {}
        scripts: List[Dict[str, Any]] = []
        totals = {"banks": 0, "images": 0, "decodable": 0, "named": 0, "confirmed": 0}
        with containers.Disc(Path(source)) as disc:
            for name, entry in self.entries(disc):
                if progress is not None:
                    progress(f"{name}…")
                try:
                    archive = disc.archive(entry)
                except containers.DiscError as exc:
                    refusals.append({"where": name, "sentence": str(exc)})
                    continue
                summary = {"archive": name, "path": entry.path, "bytes": int(entry.length),
                           "entries": len(archive), "banks": 0, "images": 0, "decodable": 0,
                           "named": 0, "confirmed": 0, "packed": archive.compressed_count(),
                           "codes": {}}
                for row in archive.entries:
                    if row.size == 0 or archive.entry_format(row.index) != "SHPS":
                        continue
                    try:
                        bank = ea_shps.parse(archive.member(row.index), row.name)
                    except (ea_big.BigError, ea_shps.ShpsError) as exc:
                        refusals.append({"where": f"{name}!{row.name}", "sentence": str(exc)})
                        continue
                    summary["banks"] += 1
                    for image in bank.images:
                        reason = bank.undecodable_reason(image.index)
                        code = "0x%02x" % image.code
                        codes[code] = codes.get(code, 0) + 1
                        summary["codes"][code] = summary["codes"].get(code, 0) + 1
                        summary["images"] += 1
                        record: Dict[str, Any] = {
                            "archive": name, "path": entry.path, "entry": row.index,
                            "entry_name": row.name, "image": image.index, "tag": image.tag,
                            "width": image.width, "height": image.height, "code": code,
                            "decodable": reason is None,
                            "palette_entries": image.palette.width if image.palette else None,
                            "mip_bytes": image.mip_bytes, "packed": archive.is_compressed(row.index),
                            "slot_bytes": archive.slot_bytes(row.index), "stored_bytes": row.size,
                        }
                        confirmed = confirmed_table.get(_key(name, row.index, image.index))
                        if confirmed and confirmed.get("shape") not in (
                                None, (image.width, image.height, code)):
                            confirmed = None
                        if confirmed:
                            record["confirmed_names"] = {
                                str(convention): list(values)
                                for convention, values in (confirmed.get("names") or {}).items()}
                            record["frames"] = list(confirmed.get("frames") or ())
                            summary["confirmed"] += 1
                        if reason is None:
                            summary["decodable"] += 1
                            if with_identities:
                                names, note = _identities(bank, image)
                                record["derived_names"] = names
                                record["derived_note"] = note
                                if names:
                                    summary["named"] += 1
                        else:
                            short = re.sub(r"image \d+ \('[^']*'\) ", "", reason)
                            short = re.sub(r"declares \d+x\d+ in \d+ byte\(s\), which is [0-9.]+ byte\(s\) per pixel", "declares its size", short)
                            reasons[short] = reasons.get(short, 0) + 1
                            record["reason"] = reason
                        rows.append(record)
                for key in ("banks", "images", "decodable", "named", "confirmed"):
                    totals[key] += summary[key]
                archives_out.append(summary)
            for name, entry in containers.archives_named(disc, self.script_archives):
                try:
                    archive = disc.archive(entry)
                except containers.DiscError as exc:
                    refusals.append({"where": name, "sentence": str(exc)})
                    continue
                scripts.append({"archive": name, "path": entry.path, "entries": len(archive),
                                "formats": archive.format_histogram(),
                                "note": "layout scripts, plain text; the grammar is not decoded"})
        return {"rows": rows, "archives": archives_out, "refusals": refusals, "reasons": reasons,
                "codes": codes, "totals": totals, "scripts": scripts}


# -- the writer lane ----------------------------------------------------------

class ShpsArtLane:
    """Export any decodable ``SHPS`` image as PNG; write an edited 8-bit one back."""

    fixed_allocation = True

    def __init__(self, *, lane_id: str, capability_id: str, surface: str, page: str, title: str,
                 walker: _Walker, validators: Sequence[str],
                 classification: str = "offline-writer-proved", max_targets: int = MAX_TARGETS) -> None:
        self.lane_id = lane_id
        self.capability_id = capability_id
        self.surface = surface
        self.page = page
        self.title = title
        self.walker = walker
        self.validators = tuple(validators)
        self.classification = classification
        stem = lane_id.replace(".", "_")
        self.recipe_schema = f"mvp05_ps2_{stem}_recipe/v1"
        self.catalogue_schema = f"mvp05_ps2_{stem}_catalogue/v1"
        self.write_schema = f"mvp05_ps2_{stem}_write/v1"
        self.max_targets = max_targets

    # catalogue ---------------------------------------------------------------

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        walked = self.walker.walk(Path(source), progress, with_identities=True,
                                  identities=_identity_table(IDENTITY_DOCUMENT))
        targets = [self._target(row) for row in walked["rows"][:self.max_targets]]
        totals = walked["totals"]
        document = {
            "schema": self.catalogue_schema, "source": str(source),
            "archives": walked["archives"], "scripts": walked["scripts"],
            "codes": walked["codes"], "refused_by_reason": walked["reasons"],
            "refusals": walked["refusals"], **totals,
            "targets_listed": len(targets), "targets_cap": self.max_targets,
            "identity_note": _coverage_sentence(totals), "identity_tool": IDENTITY_TOOL,
            "identity_document": str(IDENTITY_DOCUMENT), "runtime_note": disc_write.NOT_BOOTED,
            "rows": [{k: v for k, v in row.items() if k != "derived_names"} for row in walked["rows"]],
        }
        return Catalogue(self.catalogue_schema, self.lane_id, str(source), tuple(targets), document)

    def _target(self, row: Mapping[str, Any]) -> Target:
        key = _key(row["archive"], row["entry"], row["image"])
        decodable = bool(row["decodable"])
        writable = decodable and row["code"] == "0x02"
        detail = [f"{row['width']}x{row['height']}", ea_shps.CODE_NAMES.get(int(row["code"], 16), row["code"]),
                  f"{row['palette_entries']}-entry palette" if row["palette_entries"] else "no palette",
                  "packed" if row["packed"] else "stored"]
        if not decodable:
            detail.append("refused: " + str(row.get("reason", ""))[:80])
        fields: Tuple[Field, ...]
        if writable:
            fields = (Field("png", "png", "Replacement PNG",
                            f"An 8-bit PNG of exactly {row['width']}x{row['height']}; it is indexed "
                            f"against this image's own palette and written back inside the bank."),)
        elif decodable:
            fields = (Field("writer", "note", "Why there is no import",
                            "This image is direct 32-bit colour; it exports, and no encoder for "
                            "code 0x05 is offered here.", read_only=True),)
        else:
            fields = (Field("writer", "note", "Why there is no preview",
                            str(row.get("reason", "")), read_only=True),)
        budget = ("The bank goes back inside the slot its entry owns; a bank that no longer fits "
                  "once re-packed is refused naming the byte count.") if writable else \
                 "Read-only: this image is listed and exported; nothing is written."
        return Target(key=key, label=f"{row['archive']}!{row['entry_name']} · {row['tag']}",
                      detail=" · ".join(detail), budget=budget,
                      searchable=f"{row['archive']} {row['entry_name']} {row['tag']} {row['width']}x{row['height']} {row['code']}",
                      raw=dict(row), fields=fields)

    # reading -----------------------------------------------------------------

    def _bank(self, disc: containers.Disc, archive_name: str, entry: int
              ) -> Tuple[Any, ea_big.BigArchive, ea_shps.ShpsBank]:
        iso_entry = disc.find(archive_name)
        archive = disc.archive(iso_entry)
        row = archive.entry(entry)
        return iso_entry, archive, ea_shps.parse(archive.member(entry), row.name)

    def decode_png(self, source: Path, target: Target) -> bytes:
        return self.decode_png_by_key(Path(source), target.key)

    def decode_png_by_key(self, source: Path, key: str) -> bytes:
        archive_name, entry, image = parse_key(key)
        with containers.Disc(Path(source)) as disc:
            _iso, _archive, bank = self._bank(disc, archive_name, entry)
            try:
                width, height, rgba = ea_shps.decode_rgba(bank, image)
            except ea_shps.ShpsError as exc:
                raise Refusal(str(exc)) from exc
            return ea_shps.encode_png(width, height, rgba)

    def encode(self, source: Path, target: Target, png: bytes) -> EncodedArt:
        archive_name, entry, image_index = parse_key(target.key)
        width, height, rgba = read_rgba_png(png)
        with containers.Disc(Path(source)) as disc:
            _iso, _archive, bank = self._bank(disc, archive_name, entry)
            image = bank.image(image_index)
            require(image.pixels is not None and image.pixels.code == ea_shps.CODE_INDEXED8
                    and image.palette is not None,
                    f"{target.key} is not an 8-bit indexed image, so nothing is written back to it.")
            wanted = f"{image.width}x{image.height}"
            require((width, height) == (image.width, image.height),
                    f"that PNG is {width}x{height} and this texture is {wanted}; give a PNG of "
                    f"exactly that size.")
            palette = ea_shps.read_palette(bank, image.palette)
            indices, exact = ea_shps.encode_indexed(rgba, width, height, palette)
        return EncodedArt(png=png, width=width, height=height,
                          note=(f"{wanted}, indexed against this image's own {len(palette)}-colour "
                                f"palette: {exact:,} of {width * height:,} pixels land on an exact "
                                f"entry and {len(indices):,} index byte(s) would be written. "
                                f"{disc_write.NOT_BOOTED}"))

    @staticmethod
    def _names(target: Target, field_name: str) -> Dict[str, List[str]]:
        names = target.raw.get(field_name) if isinstance(target.raw, Mapping) else None
        if not isinstance(names, Mapping):
            return {}
        return {str(convention): list(values) for convention, values in names.items() if values}

    @staticmethod
    def _first(names: Mapping[str, Sequence[str]]) -> Optional[str]:
        for convention in (pcsx2_texture_name.CONVENTION_MODERN,
                           pcsx2_texture_name.CONVENTION_CLASSIC):
            values = names.get(convention)
            if values:
                return values[0]
        for values in names.values():
            if values:
                return values[0]
        return None

    def replacement_identity(self, target: Target) -> Optional[str]:
        """The confirmed name where a dump has shown one, the derived name otherwise.

        A confirmed name wins because it is a measurement of what the emulator
        wrote and a derived one is a computation of what it would write; where
        the two agree it makes no difference, and where they disagree the
        measurement is the one a pack has to carry.
        """

        return (self._first(self._names(target, "confirmed_names"))
                or self._first(self._names(target, "derived_names")))

    def replacement_identities(self, target: Target) -> Dict[str, List[str]]:
        out = {CONFIRMED_PREFIX + convention: values
               for convention, values in self._names(target, "confirmed_names").items()}
        out.update({DERIVED_PREFIX + convention: values
                    for convention, values in self._names(target, "derived_names").items()})
        return out

    def identity_note(self, target: Target) -> str:
        confirmed = self._names(target, "confirmed_names")
        derived = self._names(target, "derived_names")
        if confirmed:
            first = self._first(confirmed)
            frames = ""
            raw_frames = target.raw.get("frames") if isinstance(target.raw, Mapping) else None
            if isinstance(raw_frames, Sequence) and not isinstance(raw_frames, str):
                frames = f" in {len(raw_frames)} frame(s) of the capture"
            if not derived:
                why = (target.raw.get("derived_note") if isinstance(target.raw, Mapping) else "") or ""
                tail = ("Nothing is derived for this image, so the dump is the only thing that "
                        "names it" + (f" ({why[len('no name is derived: '):]})" if why.startswith(
                            "no name is derived: ") else "") + ". ")
            elif (first in (derived.get(pcsx2_texture_name.CONVENTION_MODERN) or ())
                    or first in (derived.get(pcsx2_texture_name.CONVENTION_CLASSIC) or ())):
                tail = "The deriver produces that same name from the disc bytes. "
            else:
                tail = ("The deriver produces a different name from the disc bytes, so the "
                        "confirmed one is the one to use. ")
            return (f"Confirmed by a PCSX2 dump{frames}: {first} is the name the emulator wrote, "
                    f"{sum(len(v) for v in confirmed.values())} name(s) in all. "
                    + tail + DUMP_CORPUS)
        if derived:
            first = self._first(derived)
            return (f"Derived from this texture's own bytes: {first} is the modern name; "
                    f"{sum(len(v) for v in derived.values())} name(s) cover every mip range, both "
                    f"TCC values and both GS pixel modes. {NOT_CONFIRMED}")
        note = target.raw.get("derived_note") if isinstance(target.raw, Mapping) else None
        return f"{note or 'No name is derived for this image'}. {NOT_CONFIRMED}"

    # editing -----------------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"png"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; give a "
                    f"PNG, or nothing at all to export this texture as it is.")
        if not target.raw.get("decodable"):
            return f"{target.key}: {target.raw.get('reason', 'this image does not decode')}"
        path = values.get("png")
        if path in (None, ""):
            return None
        if target.raw.get("code") != "0x02":
            return (f"{target.key}: this image is direct 32-bit colour; it exports, and no "
                    f"encoder for code 0x05 is offered here.")
        try:
            payload = Path(str(path)).read_bytes()
        except OSError as exc:
            return f"{target.key}: {path} could not be read ({exc}); choose a PNG file."
        try:
            width, height, _rgba = read_rgba_png(payload)
        except Refusal as exc:
            return f"{target.key}: {exc}"
        if (width, height) != (target.raw.get("width"), target.raw.get("height")):
            return (f"{target.key}: that PNG is {width}x{height} and this texture is "
                    f"{target.raw.get('width')}x{target.raw.get('height')}; give a PNG of exactly "
                    f"that size.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"texture": edit.target_key, "png": str(edit.values.get("png", ""))}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "textures": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {self.recipe_schema}")
        rows = recipe.get("textures")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'textures' list; choose at least one texture")
        out = []
        seen = set()
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("texture"), str),
                    f"texture {number} must name the texture it replaces")
            require(set(row) <= {"texture", "png", "note"}, f"texture {number} carries unknown keys")
            require(isinstance(row.get("png"), str) and row["png"],
                    f"texture {number} ({row['texture']}) names no PNG; this lane writes a disc, so "
                    f"every texture in the recipe must name the file that replaces it")
            require(row["texture"] not in seen, f"{row['texture']} appears twice")
            seen.add(row["texture"])
            out.append({"texture": row["texture"], "png": row["png"], "note": row.get("note")})
        return out

    def _compose(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Dict[str, Any]:
        entries = self._entries(recipe)
        grouped: Dict[str, Dict[int, List[Tuple[int, Dict[str, Any]]]]] = {}
        for entry in entries:
            target = catalogue.target(entry["texture"])
            problem = self.check_edit(target, {"png": entry["png"]})
            require(problem is None, str(problem))
            archive_name, index, image = parse_key(entry["texture"])
            grouped.setdefault(archive_name, {}).setdefault(index, []).append((image, entry))
        written: Dict[str, bytes] = {}
        paths: Dict[str, str] = {}
        textures: List[Dict[str, Any]] = []
        rewrites: List[Dict[str, Any]] = []
        with containers.Disc(Path(source)) as disc:
            for archive_name, banks in grouped.items():
                iso_entry = disc.find(archive_name)
                archive = disc.archive(iso_entry)
                current: Optional[bytes] = None
                for index, items in banks.items():
                    row = archive.entry(index)
                    bank_bytes = archive.member(index)
                    for image_index, entry in items:
                        bank = ea_shps.parse(bank_bytes, row.name)
                        image = bank.image(image_index)
                        png = Path(entry["png"]).read_bytes()
                        width, height, rgba = read_rgba_png(png)
                        require(image.palette is not None and image.pixels is not None,
                                f"{entry['texture']} has no palette to index against.")
                        palette = ea_shps.read_palette(bank, image.palette)
                        indices, exact = ea_shps.encode_indexed(rgba, width, height, palette)
                        try:
                            bank_bytes = ea_shps.replace_pixels(bank, image_index, indices)
                        except ea_shps.ShpsError as exc:
                            raise Refusal(str(exc)) from exc
                        textures.append({"texture": entry["texture"], "archive": archive_name,
                                         "path": iso_entry.path, "entry": index, "entry_name": row.name,
                                         "image": image_index, "width": width, "height": height,
                                         "png": entry["png"], "png_sha256": disc_write.sha256(png),
                                         "indices_sha256": disc_write.sha256(indices),
                                         "exact_pixels": exact, "pixels": width * height})
                    try:
                        result = ea_big.rewrite_entry(archive, index, bank_bytes)
                    except ea_big.BigError as exc:
                        raise Refusal(str(exc)) from exc
                    rewrites.append({"archive": archive_name, "path": iso_entry.path, **result.as_dict()})
                    current = result.archive
                    archive = ea_big.parse_big(current, name=iso_entry.path)
                assert current is not None
                written[archive_name] = current
                paths[archive_name] = iso_entry.path
        return {"edits": entries, "textures": textures, "rewrites": rewrites, "written": written,
                "paths": paths}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        composed = self._compose(Path(source), recipe, catalogue)
        replacements = {composed["paths"][n]: b for n, b in composed["written"].items()}
        ranges = disc_write.plan_ranges(Path(source), replacements)
        return Plan(self.lane_id, tuple(e["texture"] for e in composed["edits"]), ranges,
                    {"schema": self.recipe_schema, "textures": composed["textures"],
                     "entries": composed["rewrites"],
                     "declared_bytes": sum(r.length for r in ranges),
                     "identity_note": DUMP_CORPUS, "runtime_note": disc_write.NOT_BOOTED})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        disc_write.check_destination(source, destination)
        composed = self._compose(source, recipe, catalogue)
        replacements = {composed["paths"][n]: b for n, b in composed["written"].items()}
        report, ranges = disc_write.replace_files(source, destination, replacements)
        document = {"schema": self.write_schema, "source": str(source), "destination": str(destination),
                    "edits": composed["edits"], "textures": composed["textures"],
                    "entries": composed["rewrites"],
                    "archives": [{"name": n, "path": composed["paths"][n], "bytes": len(b),
                                  "sha256": disc_write.sha256(b)}
                                 for n, b in sorted(composed["written"].items())],
                    "iso_report": report, "identity_note": DUMP_CORPUS,
                    "runtime_note": disc_write.NOT_BOOTED}
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        source, destination = Path(source), Path(destination)
        problem = disc_write.verify_image(source, destination, receipt.document.get("iso_report"))
        if problem:
            return Verdict(False, f"Verification failed {problem}")
        textures = receipt.document.get("textures") or []
        if not textures:
            return Verdict(False, "Verification failed: the receipt declares no textures.")
        wanted: Dict[str, Dict[int, Dict[int, Dict[str, Any]]]] = {}
        for row in textures:
            wanted.setdefault(row["archive"], {}).setdefault(int(row["entry"]), {})[int(row["image"])] = row
        checked_entries = checked_pixels = 0
        try:
            with containers.Disc(source) as before, containers.Disc(destination) as after:
                for archive_name, banks in wanted.items():
                    old = before.archive(before.find(archive_name))
                    new = after.archive(after.find(archive_name))
                    if len(old) != len(new) or old.length != new.length:
                        return Verdict(False, f"Verification failed: {archive_name} changed shape.")
                    for row in old.entries:
                        fresh = new.entry(row.index)
                        if row.name != fresh.name or row.offset != fresh.offset:
                            return Verdict(False, f"Verification failed: {archive_name} entry {row.index} moved.")
                        if row.index not in banks:
                            if row.size != fresh.size or old.stored(row.index) != new.stored(row.index):
                                return Verdict(False, f"Verification failed: {archive_name}!{row.name} "
                                                      f"was not part of the recipe and changed.")
                            checked_entries += 1
                            continue
                        if fresh.size > old.slot_bytes(row.index) or old.is_compressed(row.index) != new.is_compressed(row.index):
                            return Verdict(False, f"Verification failed: {archive_name}!{row.name} outgrew its slot or changed packing.")
                        old_bank = ea_shps.parse(old.member(row.index), row.name)
                        new_bank = ea_shps.parse(new.member(row.index), row.name)
                        if len(old_bank.data) != len(new_bank.data):
                            return Verdict(False, f"Verification failed: {archive_name}!{row.name} changed size.")
                        # Every byte outside the edited images' level-0 pixels is identical.
                        mask = bytearray(len(old_bank.data))
                        for image_index, row_doc in banks[row.index].items():
                            image = old_bank.image(image_index)
                            pixels = image.pixels
                            assert pixels is not None and image.palette is not None
                            start = pixels.offset + ea_shps.BLOCK_HEADER_SIZE
                            count = pixels.width * pixels.height
                            mask[start:start + count] = b"\x01" * count
                            png = Path(str(row_doc["png"])).read_bytes()
                            if disc_write.sha256(png) != row_doc.get("png_sha256"):
                                return Verdict(False, f"Verification failed: {row_doc['png']} is not the PNG the receipt recorded.")
                            width, height, rgba = read_rgba_png(png)
                            palette = ea_shps.read_palette(old_bank, image.palette)
                            expected, _exact = ea_shps.encode_indexed(rgba, width, height, palette)
                            got = new_bank.block_bytes(new_bank.image(image_index).pixels)[:count]
                            if got != expected:
                                return Verdict(False, f"Verification failed: {row_doc['texture']} does not "
                                                      f"decode to the PNG's pixels indexed against its palette.")
                            checked_pixels += count
                        for position in range(len(mask)):
                            if not mask[position] and old_bank.data[position] != new_bank.data[position]:
                                return Verdict(False, f"Verification failed: {archive_name}!{row.name} byte "
                                                      f"{position} changed outside the edited pixels.")
                        checked_entries += 1
        except (containers.DiscError, ea_big.BigError, ea_shps.ShpsError, Refusal, OSError) as exc:
            return Verdict(False, f"Verification failed: {exc}")
        return Verdict(True, f"{len(wanted)} archive(s) re-read from both images: {checked_entries} "
                             f"entr(ies) compared, {checked_pixels:,} pixel index(es) match the PNG, and "
                             f"the image-level ranges hold.",
                       {"result": "PASS", "entries": checked_entries, "pixels": checked_pixels})

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"mvp05-ps2-{self.lane_id.replace('.', '-')}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        self._work_dir = Path(work_dir)
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        work_dir = getattr(self, "_work_dir", None) or Path(catalogue.source).parent
        for target in catalogue.targets:
            if target.raw.get("decodable") and target.raw.get("code") == "0x02":
                png = self.decode_png_by_key(Path(catalogue.source), target.key)
                # Flip the image horizontally so the write is exact and visibly different.
                width, height, rgba = read_rgba_png(png)
                flipped = bytearray()
                for y in range(height):
                    line = rgba[y * width * 4:(y + 1) * width * 4]
                    for x in range(width - 1, -1, -1):
                        flipped += line[x * 4:x * 4 + 4]
                path = Path(work_dir) / f"conformance-{target.key.replace(':', '-').replace('!', '-')}.png"
                path.write_bytes(ea_shps.encode_png(width, height, bytes(flipped)))
                return (Edit(target.key, {"png": str(path)}, note="conformance: one texture, flipped"),)
        raise Refusal("this catalogue lists no 8-bit texture, so there is no edit to prove")


# -- the read-only lane -------------------------------------------------------

class ShpsBankLane:
    """Archives that are entirely code 0x0E: listed with the measurement, never drawn."""

    fixed_allocation = True
    read_only = True

    def __init__(self, *, lane_id: str, capability_id: str, surface: str, page: str, title: str,
                 walker: _Walker, validators: Sequence[str], refusal: str,
                 max_targets: int = MAX_TARGETS) -> None:
        self.lane_id = lane_id
        self.capability_id = capability_id
        self.surface = surface
        self.page = page
        self.title = title
        self.walker = walker
        self.validators = tuple(validators)
        self.classification = "read-only-mapped"
        self.REFUSAL = refusal
        stem = lane_id.replace(".", "_")
        self.recipe_schema = f"mvp05_ps2_{stem}_recipe/v1"
        self.catalogue_schema = f"mvp05_ps2_{stem}_catalogue/v1"
        self.max_targets = max_targets

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        walked = self.walker.walk(Path(source), progress, with_identities=False,
                                  identities=_identity_table(IDENTITY_DOCUMENT))
        targets = []
        for row in walked["rows"][:self.max_targets]:
            targets.append(Target(
                key=_key(row["archive"], row["entry"], row["image"]),
                label=f"{row['archive']}!{row['entry_name']} · {row['tag']}",
                detail=f"{row['width']}x{row['height']} · {ea_shps.CODE_NAMES.get(int(row['code'], 16), row['code'])} · "
                       f"{row['palette_entries'] or 0}-entry palette",
                budget="Read-only: this lane lists the image and writes nothing.",
                searchable=f"{row['archive']} {row['entry_name']} {row['tag']} {row['width']}x{row['height']}",
                raw=dict(row),
                fields=(Field("code", "note", "Pixel code", str(row["code"]), read_only=True),
                        Field("why", "note", "Why nothing is drawn", self.REFUSAL, read_only=True)),
            ))
        document = {"schema": self.catalogue_schema, "source": str(source),
                    "archives": walked["archives"], "codes": walked["codes"],
                    "refused_by_reason": walked["reasons"], "refusals": walked["refusals"],
                    **walked["totals"], "targets_listed": len(targets), "targets_cap": self.max_targets,
                    "why": self.REFUSAL, "identity_note": _coverage_sentence(walked["totals"]),
                    "identity_tool": IDENTITY_TOOL, "identity_document": str(IDENTITY_DOCUMENT),
                    "rows": [{k: v for k, v in row.items() if k != "derived_names"} for row in walked["rows"]]}
        return Catalogue(self.catalogue_schema, self.lane_id, str(source), tuple(targets), document)

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        return self.REFUSAL

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema, "edits": []}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        raise Refusal(self.REFUSAL)

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        raise Refusal(self.REFUSAL)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        raise Refusal(self.REFUSAL)

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"mvp05-ps2-{self.lane_id.replace('.', '-')}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        raise Refusal(self.REFUSAL)


# -- the rows -----------------------------------------------------------------

ART_VALIDATORS = ("tools/validate_mvp05_ps2_art.sh", "tools/validate_mvp05_ps2_art.bat")
BLOCK_CODEC_REFUSAL = (
    "Every image in these archives is SHPS code 0x0e: a 4x4-block codec at 6 bytes per block "
    "whose two 8-bit palette endpoints per block are decoded (the block-average render shows "
    "the picture) and whose per-pixel 2-bit selectors are not -- every reading tried leaves "
    "noise inside the blocks -- so nothing is drawn and nothing is written; "
    "docs/product/EA_SHPS_FORMAT.md section 5 carries every hypothesis and its measurement."
)

STADIUM_LANE = ShpsArtLane(
    lane_id="stadiums.park_textures", capability_id="mvp05ps2.stadiums.park_textures",
    surface="stadiums_fields", page="stadiums", title="Ballpark textures: the 87 park archives and the park menu art",
    walker=_Walker(containers.STADIUM_MENU_ARCHIVES, stadiums=True), validators=ART_VALIDATORS)

PRESENTATION_LANE = ShpsArtLane(
    lane_id="presentation.overlay_textures", capability_id="mvp05ps2.presentation.overlay_textures",
    surface="scorebug_presentation", page="presentation", title="In-game overlay textures",
    walker=_Walker(containers.PRESENTATION_ARCHIVES, script_archives=containers.PRESENTATION_SCRIPT_ARCHIVES),
    validators=ART_VALIDATORS)

MENU_LANE = ShpsArtLane(
    lane_id="menus.widget_textures", capability_id="mvp05ps2.menus.widget_textures",
    surface="menus", page="menus", title="Menu widgets, backgrounds, logos, awards and loading screens",
    walker=_Walker(containers.MENU_ARCHIVES, loading_screens=True), validators=ART_VALIDATORS)

KIT_LANE = ShpsArtLane(
    lane_id="uniforms.kit_textures", capability_id="mvp05ps2.uniforms.kit_textures",
    surface="uniforms", page="uniforms",
    title="Worn kit textures: MODELS.BIG's kit, lettering and head banks",
    walker=_Walker(containers.MODEL_ARCHIVES), validators=ART_VALIDATORS,
    max_targets=MODELS_TARGETS)

UNIFORM_LANE = ShpsBankLane(
    lane_id="uniforms.kit_banks", capability_id="mvp05ps2.uniforms.kit_banks",
    surface="uniforms", page="uniforms", title="Uniform preview swatches",
    walker=_Walker(containers.UNIFORM_ARCHIVES), validators=ART_VALIDATORS, refusal=BLOCK_CODEC_REFUSAL)

FACE_LANE = ShpsBankLane(
    lane_id="rosters.face_banks", capability_id="mvp05ps2.rosters.face_banks",
    surface="portraits_faces", page="rosters", title="Portraits and head textures",
    walker=_Walker(containers.FACE_ARCHIVES), validators=ART_VALIDATORS, refusal=BLOCK_CODEC_REFUSAL)

FIELD_ART_LANE = ShpsBankLane(
    lane_id="field_art.banks", capability_id="mvp05ps2.field_art.banks",
    surface="textures", page="field_art", title="Field art and the ballpark-builder art",
    walker=_Walker(containers.FIELD_ART_ARCHIVES), validators=ART_VALIDATORS, refusal=BLOCK_CODEC_REFUSAL)

LANES_BY_NAME = {"stadiums": STADIUM_LANE, "presentation": PRESENTATION_LANE, "menus": MENU_LANE,
                 "kits": KIT_LANE, "uniforms": UNIFORM_LANE, "faces": FACE_LANE,
                 "field_art": FIELD_ART_LANE}


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mod_editor.games.mvp05_ps2.art_lane",
                                     description="Catalogue the SHPS art of an MVP Baseball 2005 (PS2) disc.")
    parser.add_argument("--source")
    parser.add_argument("--lane", default="stadiums", choices=sorted(LANES_BY_NAME))
    parser.add_argument("--out")
    parser.add_argument("--parts", help="write the per-part-tag census of the lane's archives here")
    parser.add_argument("--slot-fit", action="store_true",
                        help="with --parts: also re-pack every bank and report slot headroom")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = LANES_BY_NAME[arguments.lane]
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                src = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(src)
                if getattr(lane, "read_only", False):
                    require(len(catalogue.targets) > 0, "the read-only lane listed nothing")
                    print(f"SELFTEST ok: {len(catalogue.targets)} image(s) listed, none drawn")
                    return 0
                recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
                dest = Path(room) / "out.iso"
                receipt = lane.build(src, dest, recipe, catalogue)
                verdict = lane.verify(src, dest, receipt)
                require(verdict.passed, verdict.summary)
                print(f"SELFTEST ok: {verdict.summary}")
                return 0
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.parts:
        census = parts_census(document["rows"], source=Path(str(arguments.source)).name,
                              identities={"derived_pcsx2_names": document["named"],
                                          "confirmed_pcsx2_names": document["confirmed"]})
        if arguments.slot_fit:
            census["slot_fit"] = slot_fit_census(
                Path(arguments.source), lane.walker.archives,
                progress=lambda line: print(line, file=sys.stderr))
        Path(arguments.parts).write_text(json.dumps(census, indent=1, sort_keys=True) + "\n",
                                         encoding="utf-8", newline="\n")
        print("PARTS banks=%d images=%d writable=%d tags=%d families=%s" % (
            census["totals"]["banks"], census["totals"]["images"], census["totals"]["writable"],
            len(census["parts"]),
            ",".join("%s=%d" % (f["family"], f["banks"]) for f in census["families"])))
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("ART archives=%d banks=%d images=%d decodable=%d named=%d codes=%s" % (
        len(document["archives"]), document["banks"], document["images"], document["decodable"],
        document["named"], document["codes"]))
    return 0


__all__ = ["ART_VALIDATORS", "BLOCK_CODEC_REFUSAL", "FACE_LANE", "FIELD_ART_LANE", "INDEXED8",
           "KIT_LANE", "LANES_BY_NAME", "PARTS_DOCUMENT", "PARTS_SCHEMA", "TEAM_ARTID_RULE",
           "PARTS_COMMAND", "bank_family", "parts_census", "slot_fit_census",
           "CONFIRMED_PREFIX", "DUMP_CORPUS", "IDENTITY_DOCUMENT", "IDENTITY_SCHEMA",
           "IDENTITY_TOOL", "load_identities", "NOT_CONFIRMED",
           "MAX_TARGETS", "MENU_LANE", "MODELS_TARGETS", "NO_DUMP", "PRESENTATION_LANE",
           "STADIUM_LANE",
           "ShpsArtLane", "ShpsBankLane", "UNIFORM_LANE", "parse_key", "read_rgba_png"]


if __name__ == "__main__":
    raise SystemExit(_main())
