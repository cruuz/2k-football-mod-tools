#!/usr/bin/env python3
"""Pair a PCSX2 texture dump of MVP Baseball 2005 with the disc's own ``SHPS`` art.

PCSX2 looks for a replacement texture under a filename it builds while the game
draws -- ``<tex0 hash>-<clut hash>-<bits>.png``, two XXH3-64 hashes over the
GS's own texture and CLUT memory and a ``bits`` word packing
``PSM | TW<<6 | TH<<10 | TCC<<14``.  No disc byte carries that name, so
:mod:`mod_editor.games._formats.pcsx2_texture_name` *derives* it from the
texture's own bytes.  A derived name is a computation; a **confirmed** name is
a measurement, and this tool makes the measurement by pairing a dump with the
disc on **exact pixel equality**.

It is deliberately concrete rather than shared.  Madden 09 has its own tool
(``tools/madden09_ps2_texture_identities.py``) over ``TERF``/``MMAP``
containers; this one walks EA ``BIG`` archives and ``SHPS`` banks, and the two
formats have nothing in common below the pairing itself.  If a shared
``tools/ps2_texture_identities.py`` appears, the three readers here
(:func:`scan_dump`, :func:`pair`, :func:`derivation_check`) are the parts worth
lifting; the disc walk is not.

Three documents come out, all of them counts, names, dimensions and member
indexes -- **no pixel, no palette entry and no digest of either** goes into the
repository:

``pcsx2-texture-identities.json``
    every disc image a dumped texture confirms, with the filenames PCSX2 wrote.
``pcsx2-texture-identity-derivation.json``
    for every confirmed name, whether ``pcsx2_texture_name`` derives that same
    name from the disc bytes, and which GS mode explains it when it does not.
``shps-0x0e-dump-pairing.json``
    whether the dump answers the ``0x0E`` block codec, and by what test.  Two
    of those tests go through the palette and would miss a decoder that
    rebuilt the CLUT or interpolated in colour space; the last two do not --
    one correlates the two pictures at block resolution and the other asks
    whether the pixels lie between their block's endpoints.

Usage::

    mvp05_ps2_texture_identities.py --source DISC.iso --dump-dir DIR --out-dir DOCS
    mvp05_ps2_texture_identities.py --source DISC.iso --write-index CACHE.jsonl
    mvp05_ps2_texture_identities.py --selftest

**Evidence tags.**  **[M]** measured on the artefact named; **[S]** sourced;
**[A]** assumed.
"""

from __future__ import annotations

import argparse
import array
from dataclasses import dataclass, field
import hashlib
import math
import json
from pathlib import Path
import re
import sys
import time
import zlib
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_big, ea_shps, pcsx2_texture_name  # noqa: E402
from mod_editor.games.mvp05_ps2 import art_lane, containers                # noqa: E402

#: The schemas are the lane's, not this tool's: the lane reads the identity
#: table, so it owns where it lives and what it must say.
SCHEMA = art_lane.IDENTITY_SCHEMA
DEFAULT_OUT_DIR = art_lane.IDENTITY_DOCUMENT.parent
DERIVATION_SCHEMA = "mvp05_ps2_pcsx2_texture_identity_derivation/v1"
BLOCK_SCHEMA = "mvp05_ps2_shps_0x0e_dump_pairing/v1"
INDEX_SCHEMA = "mvp05_ps2_disc_texture_index/v1"

DERIVATION_DOCUMENT = "pcsx2-texture-identity-derivation.json"
BLOCK_DOCUMENT = "shps-0x0e-dump-pairing.json"

#: PCSX2's own filename grammar, including the palette-less form it writes for
#: a direct-colour texture.
_NAME = re.compile(
    r"^(?P<tex0>[0-9a-f]{1,16})(?:-(?P<clut>[0-9a-f]{1,16}))?"
    r"(?:-r(?P<rw>\d+)x(?P<rh>\d+))?"
    r"-(?P<bits>[0-9a-f]{8})(?:-mip(?P<mip>\d+))?\.png$"
)

#: How many other disc images an identity names before it records only how many
#: there were.  A flat texture lives in hundreds of banks on this disc and
#: listing every one of them on every one of them says nothing the count does not.
SHARED_SAMPLE = 8

#: The two naming conventions a dump directory can be written under, as the
#: sub-directory names PCSX2 and PenguinScreen2 use.
CONVENTIONS = (pcsx2_texture_name.CONVENTION_CLASSIC, pcsx2_texture_name.CONVENTION_MODERN)

#: The block codec's rate: 6 bytes per 4x4 block, so the payload of a
#: ``w x h`` image is ``w*h*3/8`` bytes and can carry no more than eight times
#: that many bits of decoded picture, whatever the codec turns out to be.
BLOCK_CODEC_BITS_PER_PIXEL = 3

#: How much contrast a thumbnail needs before a correlation between two of them
#: means anything.  A near-flat picture correlates with every other near-flat
#: picture, and on this dump the unfiltered ranking is entirely such pairs [M].
#: Standard deviation over the thumbnail's channel values, 0..255.
STRUCTURAL_CONTRAST_FLOOR = 20.0

#: How many correlated candidates each probe keeps.
STRUCTURAL_KEEP = 3


class IdentityError(ValueError):
    """The tool could not do what it was asked; the sentence says why."""


# --------------------------------------------------------------------------
# The two sides
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DumpTexture:
    """One dumped PNG: its name taken apart, its size and its pixel digests."""

    name: str
    convention: str
    width: int
    height: int
    tex0: int
    clut: Optional[int]
    bits: int
    region: Optional[Tuple[int, int]]
    mip: Optional[int]
    rgba_digest: str
    rgb_digest: str
    alpha_low: int
    alpha_high: int
    frames: Tuple[str, ...]
    #: Every distinct RGBA value the picture uses.  A decoded palette image
    #: draws only from its palette, whatever order the game uploaded it in, so
    #: this is what an order-independent palette join tests.
    colours: frozenset = frozenset()
    #: The smallest this picture's *index* image -- its colours relabelled by
    #: first appearance -- compresses to here.  It is an upper bound on the
    #: information the picture carries, and a codec cannot produce more
    #: information than its payload holds.
    index_zlib_bytes: int = 0
    #: The picture at 4x4-block resolution, mean RGB per block, zero-mean and
    #: unit-norm, or ``None`` when it is too flat for a correlation to mean
    #: anything.  This is what pairs a decoded ``0x0E`` texture with its source
    #: **without going through the palette** -- see :func:`structural_scores`.
    block_thumbnail: Optional[array.array] = None
    block_contrast: float = 0.0

    @property
    def psm(self) -> int:
        return self.bits & 0x3F

    @property
    def tcc(self) -> int:
        return (self.bits >> 14) & 1

    def as_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "convention": self.convention, "width": self.width,
                "height": self.height, "psm": self.psm, "tcc": self.tcc,
                "bits": "%08x" % self.bits, "region": list(self.region) if self.region else None,
                "mip": self.mip, "frames": list(self.frames)}

    def as_shape(self) -> Dict[str, Any]:
        """What the picture *is*, without saying what it looks like."""
        return {"name": self.name, "convention": self.convention, "width": self.width,
                "height": self.height, "psm": self.psm, "colours": len(self.colours),
                "index_zlib_bytes": self.index_zlib_bytes, "frames": list(self.frames)}


@dataclass(frozen=True)
class DiscTexture:
    """One mip level of one disc image, with the digests a dump is paired on."""

    archive: str
    path: str
    entry: int
    entry_name: str
    image: int
    tag: str
    level: int
    width: int
    height: int
    code: str
    rgba_digest: str
    rgb_digest: str
    names: Mapping[str, Sequence[str]]

    @property
    def key(self) -> str:
        return f"{self.archive}:{self.entry}:{self.image}"

    def as_dict(self) -> Dict[str, Any]:
        return {"archive": self.archive, "path": self.path, "entry": self.entry,
                "entry_name": self.entry_name, "image": self.image, "tag": self.tag,
                "level": self.level, "width": self.width, "height": self.height,
                "code": self.code, "rgba": self.rgba_digest, "rgb": self.rgb_digest,
                "names": {k: list(v) for k, v in self.names.items()}}

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> "DiscTexture":
        return cls(archive=row["archive"], path=row.get("path", ""), entry=int(row["entry"]),
                   entry_name=row.get("entry_name", ""), image=int(row["image"]),
                   tag=row.get("tag", ""), level=int(row["level"]), width=int(row["width"]),
                   height=int(row["height"]), code=row.get("code", ""),
                   rgba_digest=row["rgba"], rgb_digest=row["rgb"],
                   names=row.get("names") or {})


@dataclass(frozen=True)
class BlockImage:
    """One code-``0x0E`` image: what a pairing would need to know about it."""

    key: str
    archive: str
    width: int
    height: int
    payload_bytes: int
    palette_entries: int
    palette_distinct: int
    clut: Optional[int]

    def as_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "archive": self.archive, "width": self.width,
                "height": self.height, "payload_bytes": self.payload_bytes,
                "palette_entries": self.palette_entries,
                "palette_distinct": self.palette_distinct,
                "clut": ("%x" % self.clut) if self.clut is not None else None}


def _digests(rgba: bytes) -> Tuple[str, str]:
    """``(rgba, rgb)`` SHA-256 over the pixels, alpha kept and alpha dropped.

    The alpha-free digest is a *report*, never a match: TCC lets a draw ignore
    the CLUT's alpha, which is a real reason for two pictures of the same
    thing to differ in it.
    """

    rgb = bytearray(len(rgba) // 4 * 3)
    rgb[0::3] = rgba[0::4]
    rgb[1::3] = rgba[1::4]
    rgb[2::3] = rgba[2::4]
    return hashlib.sha256(rgba).hexdigest(), hashlib.sha256(bytes(rgb)).hexdigest()


def block_means(rgba: bytes, width: int, height: int) -> array.array:
    """Mean R, G, B of every 4x4 block, row-major: the picture at block resolution."""

    out = array.array("f", bytes(4 * 3 * (width // 4) * (height // 4)))
    position = 0
    for block_y in range(height // 4):
        for block_x in range(width // 4):
            red = green = blue = 0
            for y in range(4):
                start = ((block_y * 4 + y) * width + block_x * 4) * 4
                for x in range(4):
                    pixel = start + x * 4
                    red += rgba[pixel]
                    green += rgba[pixel + 1]
                    blue += rgba[pixel + 2]
            out[position] = red / 16.0
            out[position + 1] = green / 16.0
            out[position + 2] = blue / 16.0
            position += 3
    return out


def endpoint_thumbnail(payload: bytes, palette: Sequence[Sequence[int]],
                       width: int, height: int) -> Optional[array.array]:
    """The ``0x0E`` picture at block resolution, from its endpoint stream alone.

    The first ``w*h/8`` bytes are one 32-bit word per two horizontally adjacent
    blocks, ``[i1(x), i1(x+1), i0(x), i0(x+1)]``, block-raster order [M]; a
    block's value here is the midpoint of its two endpoint colours.  Rendering
    this for a portrait bank gives recognisable faces, which is what makes it a
    fingerprint the palette does not have to agree on.
    """

    blocks = (width // 4) * (height // 4)
    stream = payload[:width * height // 8]
    if len(stream) != 2 * blocks or blocks % 2 or len(palette) < 256:
        return None
    out = array.array("f", bytes(4 * 3 * blocks))
    for pair in range(blocks // 2):
        word = stream[pair * 4:pair * 4 + 4]
        for side in (0, 1):
            first = palette[word[2 + side]]
            second = palette[word[side]]
            position = (pair * 2 + side) * 3
            out[position] = (first[0] + second[0]) * 0.5
            out[position + 1] = (first[1] + second[1]) * 0.5
            out[position + 2] = (first[2] + second[2]) * 0.5
    return out


def normalise(values: array.array) -> Tuple[Optional[array.array], float]:
    """``(zero-mean unit-norm copy, standard deviation)``, or ``(None, sd)`` if too flat."""

    count = len(values)
    if count == 0:
        return None, 0.0
    mean = math.fsum(values) / count
    centred = array.array("f", (value - mean for value in values))
    total = math.fsum(value * value for value in centred)
    deviation = math.sqrt(total / count)
    if deviation < STRUCTURAL_CONTRAST_FLOOR or total <= 0.0:
        return None, deviation
    scale = 1.0 / math.sqrt(total)
    return array.array("f", (value * scale for value in centred)), deviation


def _index_image(rgba: bytes) -> Tuple[frozenset, bytes]:
    """``(every distinct RGBA value, the picture relabelled by first appearance)``.

    The relabelled image is what a decoder would have had to produce; how well
    it compresses bounds how much information it carries, and that bound is
    what a fixed-rate codec has to be able to pay for.
    """

    labels: Dict[bytes, int] = {}
    out = bytearray(len(rgba) // 4)
    for position in range(0, len(rgba), 4):
        colour = rgba[position:position + 4]
        label = labels.get(colour)
        if label is None:
            label = labels[colour] = len(labels)
        out[position // 4] = label & 0xFF
    return frozenset(labels), bytes(out)


def scan_dump(directory: Path) -> List[DumpTexture]:
    """Every PNG under *directory*, deduplicated by ``(convention, filename)``.

    The layout a capture writes is ``<stamp>/<convention>/<name>.png``; a flat
    directory of PNGs is read too, under the convention its ``bits`` word
    implies.  The same texture drawn in more than one frame is one entry that
    names every frame it appeared in, because that is what a coverage table
    wants to say.
    """

    directory = Path(directory)
    if not directory.is_dir():
        raise IdentityError(f"{directory} is not a directory; give the folder PCSX2 dumped into.")
    seen: Dict[Tuple[str, str], Dict[str, Any]] = {}
    files: List[Tuple[str, str, Path]] = []
    for stamp_dir in sorted(p for p in directory.iterdir() if p.is_dir()):
        for convention in CONVENTIONS:
            leg = stamp_dir / convention
            if leg.is_dir():
                files += [(stamp_dir.name, convention, p) for p in sorted(leg.glob("*.png"))]
    if not files:
        files = [("", pcsx2_texture_name.CONVENTION_MODERN, p)
                 for p in sorted(directory.rglob("*.png"))]
    for stamp, convention, path in files:
        match = _NAME.match(path.name)
        if match is None:
            continue
        key = (convention, path.name)
        row = seen.get(key)
        if row is not None:
            if stamp and stamp not in row["frames"]:
                row["frames"].append(stamp)
            continue
        width, height, rgba = art_lane.read_rgba_png(path.read_bytes())
        rgba_digest, rgb_digest = _digests(rgba)
        alphas = rgba[3::4]
        clut = match.group("clut")
        colours, indices = _index_image(rgba)
        thumbnail = contrast = None
        if width % 4 == 0 and height % 4 == 0 and width >= 4 and height >= 4:
            thumbnail, contrast = normalise(block_means(rgba, width, height))
        seen[key] = {
            "name": path.name, "convention": convention, "width": width, "height": height,
            "tex0": int(match.group("tex0"), 16),
            "clut": int(clut, 16) if clut is not None else None,
            "bits": int(match.group("bits"), 16),
            "region": ((int(match.group("rw")), int(match.group("rh")))
                       if match.group("rw") else None),
            "mip": int(match.group("mip")) if match.group("mip") else None,
            "rgba_digest": rgba_digest, "rgb_digest": rgb_digest,
            "alpha_low": min(alphas) if alphas else 0, "alpha_high": max(alphas) if alphas else 0,
            "frames": [stamp] if stamp else [],
            "colours": colours,
            "index_zlib_bytes": len(zlib.compress(indices, 9)),
            "block_thumbnail": thumbnail,
            "block_contrast": float(contrast or 0.0),
        }
    return [DumpTexture(**{**row, "frames": tuple(sorted(row["frames"]))})
            for row in seen.values()]


def _levels(bank: ea_shps.ShpsBank, image: ea_shps.ShpsImage) -> List[Tuple[int, int, bytes]]:
    """``(width, height, indices)`` per mip level of an 8-bit image, level 0 first.

    Sliced exactly the way :func:`art_lane._identities` slices them, so a name
    derived here and a name derived in the lane come from the same bytes.
    """

    pixels = image.pixels
    payload = bank.block_bytes(pixels)
    out: List[Tuple[int, int, bytes]] = []
    width, height = pixels.width, pixels.height
    cursor = 0
    while width >= 1 and height >= 1 and cursor + width * height <= len(payload):
        out.append((width, height, payload[cursor:cursor + width * height]))
        cursor += width * height
        if width == 1 and height == 1:
            break
        width, height = max(1, width // 2), max(1, height // 2)
        if len(out) > 1 and cursor >= len(payload):
            break
    if len(out) > 1 and cursor != len(payload):
        out = out[:1]
    return out


def _rgba_from_indices(indices: bytes, palette: Sequence[Tuple[int, int, int, int]]) -> bytes:
    tables = [bytes(bytearray(palette[value][channel] if value < len(palette) else 0
                              for value in range(256))) for channel in range(4)]
    out = bytearray(len(indices) * 4)
    for channel in range(4):
        out[channel::4] = indices.translate(tables[channel])
    return bytes(out)


def index_disc(source: Path, *, progress: Optional[Any] = None,
               dumps: Sequence[DumpTexture] = (),
               uploads: Optional[Mapping[str, Any]] = None,
               cluts: Optional[Mapping[str, Sequence[str]]] = None
               ) -> Tuple[List[DiscTexture], List[BlockImage], Dict[str, Any],
                          Dict[Tuple[str, str], List[str]],
                          Dict[Tuple[str, str], List[Dict[str, Any]]],
                          Dict[str, List[str]], Dict[str, Dict[str, List[str]]]]:
    """Walk every ``BIG`` archive on the disc and index every ``SHPS`` image.

    Two lists come back: the mip levels of every image that decodes, digested
    the way a dump carries them (**the CLUT's own 0..128 alpha**, not rescaled,
    which is what PCSX2 writes), and every code-``0x0E`` image with the facts a
    pairing needs -- its size, its payload length and its palette.

    When *dumps* is given, a third answer comes back with them: which dumped
    pictures draw every one of their colours from some ``0x0E`` image's
    palette.  That join is the one that survives a game re-ordering a CLUT
    before it uploads it, which this game demonstrably does, so it is the test
    that decides whether the dump can answer the block codec at all.
    """

    levels: List[DiscTexture] = []
    blocks: List[BlockImage] = []
    counts = {"archives": 0, "nested": 0, "banks": 0, "images": 0, "decodable": 0,
              "block_codec": 0, "unreadable": 0}
    wanted = [(dump, dump.colours, frozenset(colour[:3] for colour in dump.colours))
              for dump in dumps if dump.colours]
    palette_hits: Dict[Tuple[str, str], List[str]] = {}
    # The structural probes: one per distinct picture with enough contrast for a
    # correlation to mean anything, grouped by the block size they would pair at.
    probes: Dict[Tuple[int, int], List[DumpTexture]] = {}
    seen_pictures = set()
    for dump in dumps:
        if dump.block_thumbnail is None or dump.rgba_digest in seen_pictures:
            continue
        seen_pictures.add(dump.rgba_digest)
        probes.setdefault((dump.width, dump.height), []).append(dump)
    structural: Dict[Tuple[str, str], List[Tuple[float, str]]] = {}
    structural_seen = {"candidates": 0, "candidates_with_contrast": 0}
    upload_owners: Dict[str, List[str]] = {}
    clut_owners: Dict[str, Dict[str, List[str]]] = {}

    def walk(archive: ea_big.BigArchive, label: str, path: str) -> None:
        for row in archive.entries:
            if row.size == 0:
                continue
            try:
                fmt = archive.entry_format(row.index)
            except (ea_big.BigError, ValueError):
                counts["unreadable"] += 1
                continue
            if fmt == "BIGF":
                try:
                    nested = archive.nested(row.index)
                except (ea_big.BigError, ValueError):
                    counts["unreadable"] += 1
                    continue
                counts["nested"] += 1
                walk(nested, f"{label}!{row.name}", path)
                continue
            if fmt != "SHPS":
                continue
            try:
                bank = ea_shps.parse(archive.member(row.index), row.name)
            except (ea_big.BigError, ea_shps.ShpsError) as exc:
                counts["unreadable"] += 1
                continue
            counts["banks"] += 1
            for image in bank.images:
                counts["images"] += 1
                code = "0x%02x" % image.code
                if uploads or cluts:
                    _match_draw_dump(bank, image, f"{label}:{row.index}:{image.index}",
                                     uploads, cluts, upload_owners, clut_owners)
                if bank.undecodable_reason(image.index) is None:
                    counts["decodable"] += 1
                    names, _note = art_lane._identities(bank, image)
                    try:
                        if image.pixels.code == ea_shps.CODE_INDEXED8:
                            palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
                            steps = [(w, h, _rgba_from_indices(indices, palette))
                                     for w, h, indices in _levels(bank, image)]
                        else:
                            width, height, rgba = ea_shps.decode_rgba(bank, image.index,
                                                                      raw_alpha=True)
                            steps = [(width, height, rgba)]
                    except (ea_shps.ShpsError, IndexError, ValueError):
                        counts["unreadable"] += 1
                        continue
                    for level, (width, height, rgba) in enumerate(steps):
                        rgba_digest, rgb_digest = _digests(rgba)
                        levels.append(DiscTexture(
                            archive=label, path=path, entry=row.index, entry_name=row.name,
                            image=image.index, tag=image.tag, level=level, width=width,
                            height=height, code=code, rgba_digest=rgba_digest,
                            rgb_digest=rgb_digest, names=names))
                elif image.code == 0x0E:
                    counts["block_codec"] += 1
                    first = image.blocks[0]
                    clut: Optional[int] = None
                    entries = distinct = 0
                    first_bytes = b""
                    palette = ()
                    if image.palette is not None:
                        try:
                            first_bytes = bank.block_bytes(first)
                            palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
                            entries, distinct = len(palette), len(set(palette))
                            if len(palette) in (16, ea_shps.CSM1_ENTRIES):
                                clut = pcsx2_texture_name.clut_hash(palette)
                        except (ea_shps.ShpsError, ValueError):
                            pass
                    key = f"{label}:{row.index}:{image.index}"
                    blocks.append(BlockImage(
                        key=key, archive=label,
                        width=image.width, height=image.height,
                        payload_bytes=first.payload_bytes, palette_entries=entries,
                        palette_distinct=distinct, clut=clut))
                    if wanted and image.palette is not None and entries:
                        colours = {bytes(colour) for colour in palette}
                        for dump, dump_colours, _rgb in wanted:
                            if (dump.width, dump.height) != (image.width, image.height):
                                continue
                            if dump_colours <= colours:
                                hits = palette_hits.setdefault((dump.convention, dump.name), [])
                                if key not in hits:
                                    hits.append(key)
                    here = probes.get((image.width, image.height))
                    if here and image.palette is not None and entries >= 256:
                        structural_seen["candidates"] += 1
                        thumbnail = endpoint_thumbnail(first_bytes, palette,
                                                       image.width, image.height)
                        vector = normalise(thumbnail)[0] if thumbnail is not None else None
                        if vector is not None:
                            structural_seen["candidates_with_contrast"] += 1
                            for dump in here:
                                score = math.fsum(a * b for a, b in
                                                  zip(vector, dump.block_thumbnail))
                                best = structural.setdefault((dump.convention, dump.name), [])
                                if len(best) < STRUCTURAL_KEEP or score > best[-1][0]:
                                    best.append((score, key))
                                    best.sort(key=lambda row: -row[0])
                                    del best[STRUCTURAL_KEEP:]

    with containers.Disc(Path(source)) as disc:
        for entry in disc.big_files():
            label = entry.path.rsplit("/", 1)[-1]
            counts["archives"] += 1
            try:
                archive = disc.archive(entry)
            except containers.DiscError:
                counts["unreadable"] += 1
                continue
            if progress is not None:
                progress(f"{label}…")
            walk(archive, label, entry.path)
    counts.update(structural_seen)
    return levels, blocks, counts, palette_hits, {
        key: [{"ncc": round(score, 4), "key": name} for score, name in best]
        for key, best in structural.items()}, upload_owners, clut_owners


def _match_draw_dump(bank: ea_shps.ShpsBank, image: ea_shps.ShpsImage, key: str,
                     uploads: Optional[Mapping[str, Any]],
                     cluts: Optional[Mapping[str, Sequence[str]]],
                     upload_owners: Dict[str, List[str]],
                     clut_owners: Dict[str, Dict[str, List[str]]]) -> None:
    """Is this disc image the source of an upload, or the owner of a CLUT the game used?"""

    code = "0x%02x" % image.code
    if cluts and image.palette is not None and image.palette.width == ea_shps.CSM1_ENTRIES:
        try:
            palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
        except (ea_shps.ShpsError, ValueError):
            palette = ()
        if len(palette) == ea_shps.CSM1_ENTRIES:
            raw = bytearray()
            for entry in palette:
                raw += bytes((entry[0], entry[1], entry[2]))
            digest = hashlib.sha256(bytes(raw)).hexdigest()
            if digest in cluts:
                clut_owners.setdefault(digest, {}).setdefault(code, []).append(key)
    if uploads and image.pixels is not None and image.pixels.code == ea_shps.CODE_INDEXED8:
        try:
            payload = bank.block_bytes(image.pixels)
        except (ea_shps.ShpsError, ValueError):
            return
        level0 = payload[:image.width * image.height]
        if len(level0) != image.width * image.height:
            return
        digest = hashlib.sha256(level0).hexdigest()
        if digest in uploads:
            upload_owners.setdefault(digest, []).append(key)


def write_index(path: Path, source: Path, levels: Sequence[DiscTexture],
                blocks: Sequence[BlockImage], counts: Mapping[str, Any],
                palette_hits: Optional[Mapping[Tuple[str, str], Sequence[str]]] = None,
                structural: Optional[Mapping[Tuple[str, str], Sequence[Mapping[str, Any]]]] = None,
                upload_owners: Optional[Mapping[str, Sequence[str]]] = None,
                clut_owners: Optional[Mapping[str, Mapping[str, Sequence[str]]]] = None) -> None:
    """The disc index as JSONL, so a second run does not re-walk 4.3 GB."""

    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"schema": INDEX_SCHEMA, "source": Path(source).name,
                                 "counts": dict(counts)}, sort_keys=True) + "\n")
        for level in levels:
            handle.write(json.dumps({"kind": "level", **level.as_dict()}, sort_keys=True) + "\n")
        for block in blocks:
            handle.write(json.dumps({"kind": "block", **block.as_dict()}, sort_keys=True) + "\n")
        for (convention, name), keys in sorted((palette_hits or {}).items()):
            handle.write(json.dumps({"kind": "palette_hit", "convention": convention,
                                     "dump": name, "keys": list(keys)}, sort_keys=True) + "\n")
        for (convention, name), best in sorted((structural or {}).items()):
            handle.write(json.dumps({"kind": "structural", "convention": convention,
                                     "dump": name, "best": list(best)}, sort_keys=True) + "\n")
        for digest, keys in sorted((upload_owners or {}).items()):
            handle.write(json.dumps({"kind": "upload_owner", "digest": digest,
                                     "keys": list(keys)}, sort_keys=True) + "\n")
        for digest, owners in sorted((clut_owners or {}).items()):
            handle.write(json.dumps({"kind": "clut_owner", "digest": digest,
                                     "owners": {k: list(v) for k, v in owners.items()}},
                                    sort_keys=True) + "\n")


def read_index(path: Path) -> Tuple[List[DiscTexture], List[BlockImage], Dict[str, Any],
                                    Dict[Tuple[str, str], List[str]],
                                    Dict[Tuple[str, str], List[Dict[str, Any]]],
                                    Dict[str, List[str]], Dict[str, Dict[str, List[str]]]]:
    levels: List[DiscTexture] = []
    blocks: List[BlockImage] = []
    counts: Dict[str, Any] = {}
    palette_hits: Dict[Tuple[str, str], List[str]] = {}
    structural: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    upload_owners: Dict[str, List[str]] = {}
    clut_owners: Dict[str, Dict[str, List[str]]] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            kind = row.get("kind")
            if kind == "level":
                levels.append(DiscTexture.from_dict(row))
            elif kind == "block":
                blocks.append(BlockImage(
                    key=row["key"], archive=row["archive"], width=int(row["width"]),
                    height=int(row["height"]), payload_bytes=int(row["payload_bytes"]),
                    palette_entries=int(row["palette_entries"]),
                    palette_distinct=int(row["palette_distinct"]),
                    clut=int(row["clut"], 16) if row.get("clut") else None))
            elif kind == "palette_hit":
                palette_hits[(row["convention"], row["dump"])] = list(row.get("keys") or ())
            elif kind == "structural":
                structural[(row["convention"], row["dump"])] = list(row.get("best") or ())
            elif kind == "upload_owner":
                upload_owners[row["digest"]] = list(row.get("keys") or ())
            elif kind == "clut_owner":
                clut_owners[row["digest"]] = {k: list(v) for k, v in (row.get("owners") or {}).items()}
            elif row.get("schema") == INDEX_SCHEMA:
                counts = dict(row.get("counts") or {})
            else:
                raise IdentityError(f"{path} is not a disc index this tool wrote.")
    return levels, blocks, counts, palette_hits, structural, upload_owners, clut_owners


# --------------------------------------------------------------------------
# Pairing
# --------------------------------------------------------------------------


@dataclass
class MatchReport:
    """What pairing found, in the shape a document and a lane both want."""

    matched: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ambiguous: List[Dict[str, Any]] = field(default_factory=list)
    unmatched_dumps: List[Dict[str, Any]] = field(default_factory=list)
    rgb_only: List[Dict[str, Any]] = field(default_factory=list)
    by_frame: Dict[str, List[str]] = field(default_factory=dict)
    dumps_matched: int = 0
    dumps_seen: int = 0
    disc_seen: int = 0


def pair(dumps: Sequence[DumpTexture], disc: Sequence[DiscTexture]) -> MatchReport:
    """Pair on exact pixels, then report what only nearly matched.

    Exactness first and no tolerance at all: two textures that differ by one
    byte are two textures, and a matcher that shrugged at that would hand a
    lane the name of a different kit.  The tolerant leg is a *report*: a dump
    that agrees on RGB and not on alpha is listed as such, never matched.
    """

    report = MatchReport(dumps_seen=len(dumps), disc_seen=len(disc))
    by_rgba: Dict[Tuple[int, int, str], List[DiscTexture]] = {}
    by_rgb: Dict[Tuple[int, int, str], List[DiscTexture]] = {}
    for row in disc:
        by_rgba.setdefault((row.width, row.height, row.rgba_digest), []).append(row)
        by_rgb.setdefault((row.width, row.height, row.rgb_digest), []).append(row)

    for dump in dumps:
        found = by_rgba.get((dump.width, dump.height, dump.rgba_digest))
        if not found:
            loose = by_rgb.get((dump.width, dump.height, dump.rgb_digest))
            if loose:
                report.rgb_only.append({**dump.as_dict(),
                                        "candidates": sorted({row.key for row in loose})[:SHARED_SAMPLE]})
            else:
                report.unmatched_dumps.append(dump.as_dict())
            continue
        keys = sorted({row.key for row in found})
        report.dumps_matched += 1
        if len(keys) > 1:
            # One picture in several banks is ordinary on this disc and it does
            # not make the name wrong: PCSX2 hashes pixels, so one replacement
            # file covers every one of them.  The identity goes on all of them
            # and each says how many others it shares with.
            report.ambiguous.append({**dump.as_dict(), "candidates": keys[:12],
                                     "candidate_count": len(keys)})
        for row in {candidate.key: candidate for candidate in found}.values():
            levels = sorted({other.level for other in found if other.key == row.key})
            entry = report.matched.setdefault(row.key, {
                "archive": row.archive, "path": row.path, "entry": row.entry,
                "entry_name": row.entry_name, "image": row.image, "tag": row.tag,
                "width": row.width, "height": row.height, "code": row.code,
                "levels": levels, "names": {}, "frames": [],
            })
            if len(keys) > 1:
                shared = sorted(set(entry.get("shared_with", ())) | (set(keys) - {row.key}))
                entry["shared_count"] = len(shared)
                entry["shared_with"] = shared[:SHARED_SAMPLE]
            entry["names"].setdefault(dump.convention, [])
            if dump.name not in entry["names"][dump.convention]:
                entry["names"][dump.convention].append(dump.name)
            for frame in dump.frames:
                if frame not in entry["frames"]:
                    entry["frames"].append(frame)
                seen = report.by_frame.setdefault(frame, [])
                if row.key not in seen:
                    seen.append(row.key)
    for entry in report.matched.values():
        entry["frames"] = sorted(entry["frames"])
        for names in entry["names"].values():
            names.sort()
    return report


def derivation_check(report: MatchReport, disc: Sequence[DiscTexture]) -> Dict[str, Any]:
    """For every confirmed name, does the deriver produce that same name?

    A disagreement is a finding about the derivation, not about the dump: the
    emulator wrote the name it wrote.  Each one is bucketed by the GS pixel
    mode its ``bits`` word declares, because that is what the answer turned out
    to be.
    """

    names_by_key: Dict[str, Mapping[str, Sequence[str]]] = {}
    for row in disc:
        if row.names:
            names_by_key.setdefault(row.key, row.names)
    agree = disagree = underived = 0
    by_psm: Dict[str, Dict[str, int]] = {}
    examples: List[Dict[str, Any]] = []
    for key, entry in sorted(report.matched.items()):
        derived = names_by_key.get(key) or {}
        for convention, filenames in sorted(entry["names"].items()):
            for name in filenames:
                psm = str(pcsx2_texture_name.parse_name(name).psm)
                bucket = by_psm.setdefault(psm, {"agree": 0, "disagree": 0, "no name derived": 0})
                if not derived:
                    underived += 1
                    bucket["no name derived"] += 1
                elif name in (derived.get(convention) or ()):
                    agree += 1
                    bucket["agree"] += 1
                else:
                    disagree += 1
                    bucket["disagree"] += 1
                    if len(examples) < 12:
                        examples.append({"confirmed": name, "convention": convention, "key": key,
                                         "psm": int(psm),
                                         "derived": list(derived.get(convention) or ())[:4]})
    return {
        "confirmed_names_checked": agree + disagree + underived,
        "derived_name_is_the_confirmed_name": agree,
        "derived_but_a_different_name": disagree,
        "no_name_derived_for_the_disc_image": underived,
        "by_psm": {psm: by_psm[psm] for psm in sorted(by_psm, key=int)},
        "disagreements": examples,
    }


def tex0_only_check(source: Path, report: MatchReport,
                    disc: Sequence[DiscTexture]) -> Dict[str, Any]:
    """For confirmed names the deriver produces nothing for, is the TEX0 half still ours?

    This module names an 8-bit image only when it carries a 256-entry palette,
    because PCSX2 hashes a 256-entry CLUT and a shorter one is padded by
    something the disc does not record.  That rule leaves images named by the
    dump and not by the deriver, and the useful question about them is which
    *half* is missing: the CLUT half, which the game builds at run time, or the
    TEX0 half, which is only the texture's own texels.  A texture whose TEX0
    half is reproduced is one a future pack could still be built for if the
    run-time CLUT is ever measured.
    """

    named = {row.key for row in disc if row.names}
    wanted: Dict[str, List[str]] = {}
    for key, entry in report.matched.items():
        if key in named:
            continue
        for filenames in entry["names"].values():
            wanted.setdefault(key, [])
            for name in filenames:
                if name not in wanted[key]:
                    wanted[key].append(name)
    reproduced = missed = 0
    palettes: Dict[int, int] = {}
    by_psm: Dict[str, Dict[str, int]] = {}
    by_archive: Dict[str, List[Tuple[int, int, List[str]]]] = {}
    for key, filenames in wanted.items():
        archive, entry, image = art_lane.parse_key(key)
        by_archive.setdefault(archive, []).append((entry, image, filenames))
    with containers.Disc(Path(source)) as disc_file:
        for archive_name, items in sorted(by_archive.items()):
            try:
                archive = disc_file.archive(disc_file.find(archive_name.split("!")[0]))
                for part in archive_name.split("!")[1:]:
                    archive = archive.nested(next(row.index for row in archive.entries
                                                  if row.name == part))
            except (containers.DiscError, StopIteration, ea_big.BigError):
                continue
            banks: Dict[int, ea_shps.ShpsBank] = {}
            for entry, image_index, filenames in items:
                bank = banks.get(entry)
                if bank is None:
                    try:
                        bank = banks[entry] = ea_shps.parse(archive.member(entry),
                                                            archive.entry(entry).name)
                    except (ea_big.BigError, ea_shps.ShpsError):
                        continue
                image = bank.image(image_index)
                if image.pixels is None or image.pixels.code != ea_shps.CODE_INDEXED8:
                    continue
                if image.palette is not None:
                    palettes[image.palette.width] = palettes.get(image.palette.width, 0) + 1
                levels = _levels(bank, image)
                if not levels:
                    continue
                width, height, indices = levels[0]
                hashes = set()
                for psm in (None, pcsx2_texture_name.PSMT8H):
                    try:
                        stream, _path = pcsx2_texture_name.hashed_stream(indices, width, height, 8,
                                                                        psm=psm)
                    except Exception:
                        continue
                    hashes.add(pcsx2_texture_name.xxhash3_64.xxh3_64(stream))
                for name in filenames:
                    parsed = pcsx2_texture_name.parse_name(name)
                    bucket = by_psm.setdefault(str(parsed.psm), {"tex0 reproduced": 0,
                                                                 "tex0 not reproduced": 0})
                    if parsed.tex0 in hashes:
                        reproduced += 1
                        bucket["tex0 reproduced"] += 1
                    else:
                        missed += 1
                        bucket["tex0 not reproduced"] += 1
    return {
        "confirmed_images_the_deriver_names_nothing_for": len(wanted),
        "their_distinct_filenames": sum(len(v) for v in wanted.values()),
        "tex0_half_reproduced_from_the_disc": reproduced,
        "tex0_half_not_reproduced": missed,
        "by_psm": {psm: by_psm[psm] for psm in sorted(by_psm, key=int)},
        "palette_entries_histogram": {str(k): palettes[k] for k in sorted(palettes)},
        "reading": ("A name is <tex0>-<clut>-<bits>. Where the TEX0 half is reproduced and the "
                    "name still is not, the missing half is the CLUT: PCSX2 hashes a 256-entry "
                    "CLUT and this image carries a shorter palette that the game pads at upload "
                    "with something no disc byte records -- the same image is dumped under "
                    "several CLUT hashes across the capture, so it is recoloured at run time. "
                    "Those names can be confirmed by a dump and cannot be derived."),
    }


#: A per-draw GS dump names its files this way.  ``itex`` is a draw's input
#: texture, ``itpx`` its palette, ``transferNN`` an EE-to-GS upload with its
#: format and rectangle in the name.  A ``P_8`` upload's PNG carries the raw
#: uploaded byte in the red channel, so it *is* the index image [M].
_DRAW_UPLOAD = re.compile(r"^\d+_transfer\d+_EE_to_GS_[0-9a-f]+_\d+_P_8_0_0_(\d+)_(\d+)\.png$")
_DRAW_CLUT = re.compile(r"^\d+_f\d+_itpx_[0-9a-f]+_C_32\.png$")


@dataclass(frozen=True)
class DrawUpload:
    """One distinct 8-bit texture the game handed the GS, and what it looks like."""

    frame: str
    file: str
    width: int
    height: int
    digest: str
    blocks: int
    blocks_over_four: int
    most_distinct_in_a_block: int
    index_zlib_bytes: int

    @property
    def block_codec_budget(self) -> int:
        """Bytes a ``0x0E`` payload of this size would hold."""
        return self.width * self.height * 3 // 8

    def as_dict(self) -> Dict[str, Any]:
        return {"frame": self.frame, "file": self.file,
                "size": f"{self.width}x{self.height}", "blocks": self.blocks,
                "blocks_over_four_distinct": self.blocks_over_four,
                "most_distinct_in_a_block": self.most_distinct_in_a_block,
                "index_zlib_bytes": self.index_zlib_bytes,
                "block_codec_budget_bytes": self.block_codec_budget}


def scan_draw_dump(directories: Sequence[Path]) -> Tuple[List[DrawUpload], Dict[str, List[str]]]:
    """Every distinct 8-bit upload and every distinct CLUT a per-draw dump holds.

    A per-draw dump is what a *replacement* texture dump is not: it writes every
    texture a draw uses whatever its source, and every raw EE-to-GS transfer.
    That removes the filter the replacement dumper applies -- it only writes a
    texture sourced from a plain transfer -- which is the one thing that could
    have hidden a decoded ``0x0E`` texture from the earlier search.
    """

    uploads: Dict[str, DrawUpload] = {}
    cluts: Dict[str, List[str]] = {}
    # The same texture is uploaded in draw after draw and frame after frame, and
    # decoding a 512x512 PNG in Python is not free; identical uploads are
    # identical files, so the file's own digest skips the decode.
    seen_files: Dict[str, None] = {}
    for directory in directories:
        directory = Path(directory)
        if not directory.is_dir():
            raise IdentityError(f"{directory} is not a directory; give a per-draw dump folder.")
        frame = directory.name
        for path in sorted(directory.iterdir()):
            upload = _DRAW_UPLOAD.match(path.name)
            if upload is not None:
                payload = path.read_bytes()
                file_key = hashlib.sha256(payload).hexdigest()
                if file_key in seen_files:
                    continue
                seen_files[file_key] = None
                png_w, png_h, rgba = art_lane.read_rgba_png(payload)
                indices = bytes(rgba[0::4])
                key = hashlib.sha256(indices).hexdigest()
                if key in uploads:
                    continue
                worst = over = blocks = 0
                if png_w % 4 == 0 and png_h % 4 == 0 and png_w >= 4 and png_h >= 4:
                    for block_y in range(png_h // 4):
                        for block_x in range(png_w // 4):
                            seen = set()
                            for y in range(4):
                                start = (block_y * 4 + y) * png_w + block_x * 4
                                seen.update(indices[start:start + 4])
                            blocks += 1
                            worst = max(worst, len(seen))
                            if len(seen) > 4:
                                over += 1
                uploads[key] = DrawUpload(frame=frame, file=path.name, width=png_w, height=png_h,
                                          digest=key, blocks=blocks, blocks_over_four=over,
                                          most_distinct_in_a_block=worst,
                                          index_zlib_bytes=len(zlib.compress(indices, 9)))
                continue
            if _DRAW_CLUT.match(path.name):
                payload = path.read_bytes()
                file_key = hashlib.sha256(payload).hexdigest()
                if file_key in seen_files:
                    continue
                seen_files[file_key] = None
                png_w, png_h, rgba = art_lane.read_rgba_png(payload)
                if png_w * png_h != 256:
                    continue
                raw = bytearray()
                for position in range(0, len(rgba), 4):
                    raw += rgba[position:position + 3]
                cluts.setdefault(hashlib.sha256(bytes(raw)).hexdigest(), []).append(
                    f"{frame}/{path.name}")
    return list(uploads.values()), cluts


def draw_dump_report(uploads: Sequence[DrawUpload], clut_owners: Mapping[str, Dict[str, List[str]]],
                     upload_owners: Mapping[str, List[str]], cluts: Mapping[str, List[str]]
                     ) -> Dict[str, Any]:
    """What the per-draw dump says about where the game's 8-bit pixels come from."""

    plain = [u for u in uploads if upload_owners.get(u.digest)]
    other = [u for u in uploads if not upload_owners.get(u.digest)]
    blocky = [u for u in uploads if u.blocks and u.blocks_over_four == 0]
    by_code: Dict[str, int] = {}
    for digest in cluts:
        owners = clut_owners.get(digest) or {}
        label = "+".join(sorted(owners)) or "no disc image"
        by_code[label] = by_code.get(label, 0) + 1
    return {
        "method": ("A per-draw GS dump writes every texture a draw uses whatever its source and "
                   "every EE-to-GS upload, so the replacement dumper's filter -- it writes only "
                   "textures sourced from a plain transfer -- is gone. A P_8 upload's PNG carries "
                   "the uploaded byte in its red channel, which is the index image itself: no "
                   "palette is involved in reading it, so what follows is palette-free."),
        "frames": sorted({u.frame for u in uploads}),
        "distinct_8bit_uploads": len(uploads),
        "uploads_that_are_a_disc_0x02_image_byte_for_byte": len(plain),
        "uploads_with_no_disc_twin": len(other),
        "disc_0x02_images_identified": len({key for keys in upload_owners.values() for key in keys}),
        "distinct_cluts_uploaded": len(cluts),
        "cluts_by_the_pixel_code_of_the_disc_image_that_owns_them": dict(sorted(by_code.items())),
        "uploads_where_every_4x4_block_has_at_most_four_indices": len(blocky),
        "uploads_without_a_twin_that_could_be_a_block_decode": sum(
            1 for u in other if u.blocks and u.blocks_over_four == 0),
        "uploads_without_a_twin": [u.as_dict() for u in
                                   sorted(other, key=lambda u: -u.width * u.height)[:24]],
        "reading": ("Two endpoints and sixteen 2-bit selectors put at most four distinct indices "
                    "in a 4x4 block. An upload that exceeds that is not a decode of a 0x0E image "
                    "whatever its palette, and this test needs no palette at all."),
    }


#: The value sets a two-endpoint block codec could pick from, in colour space.
#: If the decoder lerps between ``pal[i0]`` and ``pal[i1]`` rather than working
#: in index space, every decoded pixel is one of these points on that segment.
LERP_SETS: Mapping[str, Tuple[float, ...]] = {
    "DXT weights {0, 1/3, 2/3, 1}": (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0),
    "linear {0, 1/2, 1}": (0.0, 0.5, 1.0),
    "endpoints only {0, 1}": (0.0, 1.0),
}


def structural_report(dumps: Sequence[DumpTexture],
                      scores: Mapping[Tuple[str, str], Sequence[Mapping[str, Any]]],
                      matched_names: Iterable[str], counts: Mapping[str, Any]) -> Dict[str, Any]:
    """Rank the picture-to-picture correlation, against a null that cannot be a pair.

    The null is the dumped pictures that already pair to a decoded ``0x02``
    image: those are *known* not to be ``0x0E``, so whatever they score is what
    an unrelated pair scores here.  A candidate that does not clear the null's
    maximum has said nothing.
    """

    paired = set(matched_names)
    by_name = {(row.convention, row.name): row for row in dumps}
    rows: List[Dict[str, Any]] = []
    for key, best in scores.items():
        dump = by_name.get(tuple(key))
        if dump is None or not best:
            continue
        rows.append({"dump": dump.name, "convention": dump.convention,
                     "size": f"{dump.width}x{dump.height}", "psm": dump.psm,
                     "contrast": round(dump.block_contrast, 1),
                     "already_paired_to_a_decoded_image": dump.name in paired,
                     "frames": list(dump.frames), "best": list(best)})
    rows.sort(key=lambda row: -row["best"][0]["ncc"])
    null = [row["best"][0]["ncc"] for row in rows if row["already_paired_to_a_decoded_image"]]
    live = [row["best"][0]["ncc"] for row in rows if not row["already_paired_to_a_decoded_image"]]
    ceiling = max(null) if null else None
    above = [row for row in rows if not row["already_paired_to_a_decoded_image"]
             and ceiling is not None and row["best"][0]["ncc"] > ceiling]
    return {
        "method": ("Normalised cross-correlation of two pictures at 4x4-block resolution: the "
                   "dumped texture's block means against the 0x0E image's endpoint thumbnail, "
                   "which is the midpoint of each block's two endpoint colours. It goes nowhere "
                   "near the palette, so it finds a pair whose CLUT the game rebuilt, and it "
                   "finds one whose decoder interpolated in colour space, both of which the "
                   "palette joins miss."),
        "contrast_floor": STRUCTURAL_CONTRAST_FLOOR,
        "contrast_note": ("Both sides are filtered on it. A near-flat thumbnail correlates with "
                          "every other near-flat thumbnail, and unfiltered the whole top of this "
                          "ranking is such pairs."),
        "probe_pictures": len(rows),
        "block_images_correlated": int(counts.get("candidates", 0)),
        "block_images_with_contrast": int(counts.get("candidates_with_contrast", 0)),
        "null_pictures": len(null),
        "null_ceiling": round(ceiling, 4) if ceiling is not None else None,
        "null_median": round(sorted(null)[len(null) // 2], 4) if null else None,
        "candidate_pictures": len(live),
        "candidate_best": round(max(live), 4) if live else None,
        "candidate_median": round(sorted(live)[len(live) // 2], 4) if live else None,
        "above_the_null_ceiling": len(above),
        "ranking": rows[:20],
    }


def lerp_residual(source: Path, dump_dir: Path, dump: DumpTexture, block_key: str
                  ) -> Dict[str, Any]:
    """How far a candidate's dumped pixels lie from the segment between its endpoints.

    The test that settles a correlation: under a two-endpoint codec every pixel
    of a block sits on the line from ``pal[i0]`` to ``pal[i1]``, so the residual
    is quantisation -- within 8 of 255 for a 16-bit target and less for a 32-bit
    one -- and adding the interior points to the value set has to reduce it. A
    residual that neither is small nor improves when the interior points are
    offered is a correlation that means nothing.
    """

    archive_name, entry, image_index = art_lane.parse_key(block_key)
    with containers.Disc(Path(source)) as disc:
        archive = disc.archive(disc.find(archive_name.split("!")[0]))
        for part in archive_name.split("!")[1:]:
            archive = archive.nested(next(row.index for row in archive.entries
                                          if row.name == part))
        bank = ea_shps.parse(archive.member(entry), archive.entry(entry).name)
        image = bank.image(image_index)
        palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
        payload = bank.block_bytes(image.blocks[0])
    width, height = image.width, image.height
    path = Path(dump_dir) / (dump.frames[0] if dump.frames else "") / dump.convention / dump.name
    if not path.exists():
        matches = list(Path(dump_dir).rglob(dump.name))
        if not matches:
            raise IdentityError(f"{dump.name} is not under {dump_dir} any more.")
        path = matches[0]
    dumped_w, dumped_h, rgba = art_lane.read_rgba_png(path.read_bytes())
    if (dumped_w, dumped_h) != (width, height):
        raise IdentityError(f"{dump.name} is {dumped_w}x{dumped_h} and {block_key} is "
                            f"{width}x{height}.")
    blocks = (width // 4) * (height // 4)
    stream = payload[:width * height // 8]
    out: Dict[str, Any] = {"dump": dump.name, "block_image": block_key,
                           "size": f"{width}x{height}", "sets": {}}
    for label, weights in LERP_SETS.items():
        total = 0.0
        within = samples = 0
        for pair in range(blocks // 2):
            word = stream[pair * 4:pair * 4 + 4]
            for side in (0, 1):
                index = pair * 2 + side
                block_x, block_y = index % (width // 4), index // (width // 4)
                first = palette[word[2 + side]]
                second = palette[word[side]]
                points = [tuple(first[channel] + (second[channel] - first[channel]) * weight
                                for channel in range(3)) for weight in weights]
                for y in range(4):
                    start = ((block_y * 4 + y) * width + block_x * 4) * 4
                    for x in range(4):
                        pixel = start + x * 4
                        best = min(math.dist(point, (rgba[pixel], rgba[pixel + 1],
                                                     rgba[pixel + 2])) for point in points)
                        total += best
                        samples += 1
                        if best <= 8.0:
                            within += 1
        out["sets"][label] = {"mean_residual": round(total / max(samples, 1), 2),
                              "pixels_within_quantisation_pct": round(100.0 * within / max(samples, 1), 1)}
    out["reading"] = ("A true pair puts nearly every pixel within quantisation and improves "
                      "markedly when the interior points are offered. One that does neither is "
                      "not a pair, whatever it correlated at.")
    return out


#: Block shapes a 6-byte-per-16-texel codec could be using.  Every one of them
#: is 16 texels, so every one of them would put at most four distinct values in
#: a block if the two spare bytes are endpoints and the four are 2-bit
#: selectors.  Measuring the true index image against all five settles the
#: geometry without enumerating bit orders.
CANDIDATE_BLOCK_SHAPES: Tuple[Tuple[int, int], ...] = ((4, 4), (8, 2), (2, 8), (16, 1), (1, 16))


def probe_candidate(source: Path, dump_dir: Path, dump: DumpTexture, block_key: str
                    ) -> Dict[str, Any]:
    """Invert the palette on a candidate dump and ask what its true indices look like.

    This is the answer key a codec needs, and building it is the first thing to
    do with a pairing rather than the last: every dumped pixel becomes the
    8-bit palette index the game would have had to produce, a colour that
    appears at more than one palette entry becomes a wildcard, and then the
    distinct-index count per block says whether *any* 16-texel block shape can
    be carrying two endpoints and sixteen 2-bit selectors.  If it cannot, the
    pairing is not a decode and no amount of bit-order search will make it one.
    """

    archive_name, entry, image_index = art_lane.parse_key(block_key)
    with containers.Disc(Path(source)) as disc:
        archive = disc.archive(disc.find(archive_name.split("!")[0]))
        for part in archive_name.split("!")[1:]:
            archive = archive.nested(next(row.index for row in archive.entries
                                          if row.name == part))
        bank = ea_shps.parse(archive.member(entry), archive.entry(entry).name)
        image = bank.image(image_index)
        palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
    where: Dict[bytes, List[int]] = {}
    for index, colour in enumerate(palette):
        where.setdefault(bytes(colour), []).append(index)
    path = Path(dump_dir) / (dump.frames[0] if dump.frames else "") / dump.convention / dump.name
    if not path.exists():
        matches = list(Path(dump_dir).rglob(dump.name))
        if not matches:
            raise IdentityError(f"{dump.name} is not under {dump_dir} any more.")
        path = matches[0]
    width, height, rgba = art_lane.read_rgba_png(path.read_bytes())
    truth: List[Optional[List[int]]] = []
    outside = wildcard = 0
    for position in range(0, len(rgba), 4):
        found = where.get(rgba[position:position + 4])
        if found is None:
            outside += 1
            truth.append(None)
        else:
            if len(found) > 1:
                wildcard += 1
            truth.append(found)
    shapes = []
    for block_w, block_h in CANDIDATE_BLOCK_SHAPES:
        if width % block_w or height % block_h:
            continue
        worst = 0
        over = total = 0
        for block_y in range(height // block_h):
            for block_x in range(width // block_w):
                values = set()
                for y in range(block_h):
                    row = (block_y * block_h + y) * width + block_x * block_w
                    for x in range(block_w):
                        candidate = truth[row + x]
                        if candidate is not None:
                            values.add(candidate[0])
                total += 1
                worst = max(worst, len(values))
                if len(values) > 4:
                    over += 1
        shapes.append({"block": f"{block_w}x{block_h}", "blocks": total,
                       "most_distinct_indices_in_a_block": worst,
                       "blocks_with_more_than_four": over})
    return {
        "dump": dump.name, "convention": dump.convention, "block_image": block_key,
        "size": f"{width}x{height}", "palette_entries": len(palette),
        "palette_distinct_colours": len(where),
        "dumped_pixels_outside_the_palette": outside,
        "dumped_pixels_whose_colour_is_at_more_than_one_index": wildcard,
        "distinct_true_indices": len({value[0] for value in truth if value is not None}),
        "block_shapes": shapes,
        "reading": ("Two 8-bit endpoints and sixteen 2-bit selectors put at most four distinct "
                    "indices in a block. A shape with blocks above four rules that reading out "
                    "for that shape; every shape ruled out rules the pairing out."),
    }


def block_codec_report(dumps: Sequence[DumpTexture], blocks: Sequence[BlockImage],
                       matched_keys: Iterable[str],
                       palette_hits: Optional[Mapping[Tuple[str, str], Sequence[str]]] = None
                       ) -> Dict[str, Any]:
    """Does the dump answer code ``0x0E``?  The three tests, and what each found.

    A decoded ``0x0E`` texture would be an 8-bit picture drawn from the palette
    that image carries, so two joins can find it:

    1. **the CLUT hash** PCSX2 writes into the filename, which finds a palette
       the game uploaded verbatim; and
    2. **the palette's colour set**, order-independent, which also finds one the
       game re-ordered first -- and this game does re-order some, so this is the
       test with the recall.

    Whatever a candidate passes, the payload still has to be able to hold the
    answer, which is the third test: a ``w x h`` image's payload is
    ``w*h*3/8`` bytes, so a decoder reading it can emit at most ``w*h*3``
    bits of picture, and a candidate whose own texel image does not compress
    into that many bits cannot be a decode of it whatever the codec turns out
    to be.
    """

    matched = set(matched_keys)
    by_clut: Dict[int, List[BlockImage]] = {}
    by_size: Dict[Tuple[int, int], List[BlockImage]] = {}
    for block in blocks:
        if block.clut is not None:
            by_clut.setdefault(block.clut, []).append(block)
        by_size.setdefault((block.width, block.height), []).append(block)
    sizes = sorted({(block.width, block.height) for block in blocks})
    by_key = {block.key: block for block in blocks}

    def capacity_row(dump: DumpTexture, candidates: Sequence[BlockImage]) -> Dict[str, Any]:
        same = [block for block in candidates
                if (block.width, block.height) == (dump.width, dump.height)]
        payload = same[0].payload_bytes if same else None
        return {
            "dump": dump.name, "convention": dump.convention,
            "size": f"{dump.width}x{dump.height}", "psm": dump.psm,
            "frames": list(dump.frames), "colours_used": len(dump.colours),
            "block_images": [block.key for block in candidates][:SHARED_SAMPLE],
            "payload_bytes": payload,
            "payload_capacity_bits": payload * 8 if payload is not None else None,
            "dumped_texels_compress_to_bits": dump.index_zlib_bytes * 8,
            "payload_can_hold_it": (payload is not None
                                    and dump.index_zlib_bytes <= payload),
        }

    clut_candidates = []
    dump_sizes_shared = 0
    for dump in dumps:
        if (dump.width, dump.height) in by_size:
            dump_sizes_shared += 1
        if dump.clut is None:
            continue
        found = by_clut.get(dump.clut) or []
        if found:
            clut_candidates.append(capacity_row(dump, found))
    subset_candidates = []
    by_name = {(row.convention, row.name): row for row in dumps}
    for key, keys in sorted((palette_hits or {}).items()):
        dump = by_name.get(tuple(key))
        if dump is None:
            continue
        subset_candidates.append(capacity_row(dump, [by_key[k] for k in keys if k in by_key]))
    return {
        "block_images": len(blocks),
        "block_images_with_a_256_entry_clut": sum(1 for b in blocks if b.clut is not None),
        "dump_files": len(dumps),
        "dump_textures": len({(row.tex0, row.clut, row.bits & ~0x4000, row.region, row.mip)
                              for row in dumps}),
        "dump_files_whose_size_a_block_image_also_has": dump_sizes_shared,
        "disc_images_paired_to_a_dumped_texture": len(matched),
        "block_image_sizes": ["%dx%d" % size for size in sizes][:24],
        "palette_hunt_ran": palette_hits is not None,
        "clut_hash_candidates": clut_candidates,
        "palette_subset_candidates": subset_candidates,
    }


# --------------------------------------------------------------------------
# The documents
# --------------------------------------------------------------------------


def _by_archive(report: MatchReport, disc: Sequence[DiscTexture],
                blocks: Sequence[BlockImage]) -> Dict[str, Dict[str, int]]:
    """The coverage table: per archive, images listed / named / confirmed."""

    rows: Dict[str, Dict[str, int]] = {}
    seen_images: Dict[str, set] = {}
    for level in disc:
        row = rows.setdefault(level.archive, {"listed": 0, "named": 0, "confirmed": 0,
                                              "block_codec": 0, "frames": 0})
        images = seen_images.setdefault(level.archive, set())
        if (level.entry, level.image) in images:
            continue
        images.add((level.entry, level.image))
        row["listed"] += 1
        if level.names:
            row["named"] += 1
    for block in blocks:
        row = rows.setdefault(block.archive, {"listed": 0, "named": 0, "confirmed": 0,
                                              "block_codec": 0, "frames": 0})
        row["listed"] += 1
        row["block_codec"] += 1
    frames: Dict[str, set] = {}
    for key, entry in report.matched.items():
        row = rows.setdefault(entry["archive"], {"listed": 0, "named": 0, "confirmed": 0,
                                                 "block_codec": 0, "frames": 0})
        row["confirmed"] += 1
        frames.setdefault(entry["archive"], set()).update(entry["frames"])
    for archive, stamps in frames.items():
        rows[archive]["frames"] = len(stamps)
    return {archive: rows[archive] for archive in sorted(rows)}


def build_document(source: Path, dump_dir: Path, dumps: Sequence[DumpTexture],
                   disc: Sequence[DiscTexture], blocks: Sequence[BlockImage],
                   report: MatchReport, *, note: str = "",
                   frame_labels: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """The evidence file: counts, dimensions, filenames, member indexes."""

    by_dimension: Dict[str, int] = {}
    for dump in report.unmatched_dumps:
        key = f"{dump['width']}x{dump['height']}"
        by_dimension[key] = by_dimension.get(key, 0) + 1
    images = {(row.archive, row.entry, row.image) for row in disc}
    coverage = _by_archive(report, disc, blocks)
    return {
        "schema": SCHEMA,
        "generated_by": "tools/mvp05_ps2_texture_identities.py",
        "method": "exact pixel equality, RGBA with the CLUT's own 0..128 alpha",
        "source": Path(source).name,
        "dump_directory": str(dump_dir),
        "conventions": sorted({dump.convention for dump in dumps}),
        "counts": {
            "dump_files": report.dumps_seen,
            "dump_textures": len({(row.tex0, row.clut, row.bits & ~0x4000, row.region, row.mip)
                                  for row in dumps}),
            "dump_files_matched": report.dumps_matched,
            "dump_files_rgb_only": len(report.rgb_only),
            "dump_files_ambiguous": len(report.ambiguous),
            "dump_files_unmatched": len(report.unmatched_dumps),
            "disc_images_indexed": len(images),
            "disc_levels_indexed": report.disc_seen,
            "disc_block_codec_images": len(blocks),
            "disc_images_confirmed": len(report.matched),
            "frames": len({frame for dump in dumps for frame in dump.frames}),
        },
        "coverage_by_archive": coverage,
        "unmatched_by_dimension": dict(sorted(by_dimension.items())),
        "note": note,
        "region_note": (
            "A name carrying -r<W>x<H> is a region: the game drew a sub-rectangle of a larger "
            "texture and the PNG is that rectangle, so it cannot equal a whole image on the disc "
            "unless the region is the whole of one. Those are counted, not treated as a failure."),
        "unmatched_note": (
            "An unmatched dump is not a failure of the pairing. The three frames drew a great "
            "deal this disc does not store as a finished picture -- nameplates and numbers the "
            "game composites at run time, font sheets, and pages of GS memory nothing had "
            "written yet -- and none of that has a disc image to equal."),
        "frames": {
            frame: {"label": (frame_labels or {}).get(frame, ""), "images": len(keys),
                    "by_archive": _count_archives(keys)}
            for frame, keys in sorted(report.by_frame.items())
        },
        "identities": {key: report.matched[key] for key in sorted(report.matched)},
        "ambiguous": report.ambiguous,
        "rgb_only": report.rgb_only,
        "unmatched": sorted(dump["name"] for dump in report.unmatched_dumps),
    }


def _count_archives(keys: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for key in keys:
        archive = key.rsplit(":", 2)[0]
        out[archive] = out.get(archive, 0) + 1
    return dict(sorted(out.items()))


def build_derivation_document(source: Path, check: Mapping[str, Any],
                              tex0_only: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return {
        "schema": DERIVATION_SCHEMA,
        "generated_by": "tools/mvp05_ps2_texture_identities.py",
        "source": Path(source).name,
        "question": ("For every dumped name that pairs on pixels, does "
                     "mod_editor/games/_formats/pcsx2_texture_name.py derive that same name from "
                     "the disc bytes?"),
        "method": ("The disc image's derived names are computed from its own pixel block and "
                   "palette and compared, string for string, with the filename PCSX2 wrote."),
        "tex0_only": dict(tex0_only or {}),
        "by_psm_note": (
            "The PSM 27 row is the finding. Those names are of textures the game uploaded as a "
            "high-byte surface, and until this run the deriver only ever produced the PSMT8 "
            "(PSM 19) reading, so every one of them was a disagreement: a different bits word "
            "AND a different TEX0 hash for the same pixels. The block reading reproduces none of "
            "them; the linear reading reproduces all of them, which is why "
            "pcsx2_texture_name.hashed_stream now takes the linear path for PSM 27 and "
            "derive_names offers both modes. A PSM with only 'no name derived' against it is a "
            "direct-colour or short-palette image, which this module names on purpose only when "
            "it is 8-bit with a 256-entry CLUT."),
        **dict(check),
    }


def block_codec_verdict(report: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """One sentence, and the tests behind it, from the block report alone."""

    clut = list(report.get("clut_hash_candidates") or ())
    subset = list(report.get("palette_subset_candidates") or ())
    # One dumped file can arrive on both lists and under both conventions; the
    # verdict counts pictures, not rows.
    joined = {(row["convention"], row["dump"]): row for row in clut + subset}
    payable = [row for row in joined.values() if row.get("payload_can_hold_it")]
    probes = list(report.get("ground_truth_probes") or ())
    structure = dict(report.get("structural_pairing") or {})
    per_draw = dict(report.get("per_draw_dump") or {})
    residuals = list(report.get("lerp_residuals") or ())
    convincing = [row for row in residuals
                  if max(entry["pixels_within_quantisation_pct"]
                         for entry in row["sets"].values()) >= 90.0]
    workable = [probe for probe in probes
                if any(shape["blocks_with_more_than_four"] == 0
                       for shape in probe.get("block_shapes") or ())]
    tests = [
        {"test": "the CLUT hash in the dumped filename equals a 0x0E image's palette",
         "candidates": len(clut),
         "finds": "a palette the game uploaded to the GS exactly as the disc stores it"},
        {"test": "every colour a dumped picture uses is in a 0x0E image's palette, in any order",
         "candidates": len(subset), "ran": bool(report.get("palette_hunt_ran")),
         "finds": "the same, and also a palette the game re-ordered before uploading it"},
        {"test": "the payload can hold the picture: w*h*3/8 bytes against what the dumped "
                 "texels compress to",
         "candidates": len(payable),
         "finds": "whether a candidate could be a decode of that payload at all"},
        {"test": "the true index image, palette inverted, has at most four distinct indices in "
                 "some 16-texel block shape",
         "candidates": len(workable), "probed": len(probes),
         "finds": "whether two endpoints and sixteen 2-bit selectors could describe it"},
        {"test": "no 8-bit texture the game hands the GS -- from a per-draw dump, which has no "
                 "source filter -- has more than four distinct indices in a 4x4 block",
         "candidates": int(per_draw.get("uploads_where_every_4x4_block_has_at_most_four_indices", 0)),
         "uploads": int(per_draw.get("distinct_8bit_uploads", 0)),
         "already_a_disc_0x02_image": int(
             per_draw.get("uploads_that_are_a_disc_0x02_image_byte_for_byte", 0)),
         "finds": "a decoded 0x0E texture wherever it reaches the GS, with no palette involved"},
        {"test": "the picture correlates with a 0x0E image's endpoint thumbnail, above what a "
                 "dumped texture already known not to be 0x0E scores",
         "candidates": int(structure.get("above_the_null_ceiling", 0)),
         "probes": int(structure.get("probe_pictures", 0)),
         "null_ceiling": structure.get("null_ceiling"),
         "finds": "a pair the palette joins miss -- a rebuilt CLUT, or a decoder that "
                  "interpolates in colour space and never uses the palette as a codebook"},
    ]
    survivors = int(structure.get("above_the_null_ceiling", 0))
    unfiltered = int(per_draw.get("uploads_without_a_twin_that_could_be_a_block_decode", 0))
    per_draw_line = ""
    if per_draw:
        per_draw_line = (
            "; and with the dumper's source filter removed, %d of the %d distinct 8-bit textures "
            "the game hands the GS are a disc 0x02 image byte for byte and %d of the rest could "
            "be a block decode" % (
                per_draw.get("uploads_that_are_a_disc_0x02_image_byte_for_byte", 0),
                per_draw.get("distinct_8bit_uploads", 0), unfiltered))
    if not clut and not subset and not survivors:
        return ("no dumped texture is a decoded 0x0E image: no dumped picture draws its colours "
                "from any 0x0E image's palette, and none correlates with a 0x0E image's own "
                "picture above what a texture known not to be one scores" + per_draw_line, tests)
    if not clut and not subset and survivors and not convincing:
        return ("no dumped texture is a decoded 0x0E image: no dumped picture draws its colours "
                "from any 0x0E image's palette, and the %d that clear the correlation null do "
                "not put their pixels on the segment between their block's endpoints"
                % survivors + per_draw_line, tests)
    if not clut and not subset:
        return ("no dumped texture is a decoded 0x0E image: no dumped picture draws its colours "
                "from any 0x0E image's palette", tests)
    if not payable and not workable and not convincing:
        return ("no dumped texture is a decoded 0x0E image: the %d candidate(s) a palette join "
                "finds carry more information than the 0x0E payload can hold and have far more "
                "than four distinct indices in every 16-texel block shape, and the %d that clear "
                "the picture-correlation null do not put their pixels on the segment between "
                "their block's endpoints" % (len(joined), survivors) + per_draw_line, tests)
    if not payable:
        return ("no dumped texture is a decoded 0x0E image: the %d candidate(s) a palette join "
                "finds carry more information than the 0x0E payload can hold, so no decoder "
                "could have produced them from it" % len(joined), tests)
    return ("%d dumped texture(s) could be a decoded 0x0E image: a palette join finds them, the "
            "payload is large enough to hold them and %d of them fit a 16-texel block shape"
            % (len(payable), len(workable)), tests)


def build_block_document(source: Path, dump_dir: Path, report: Mapping[str, Any],
                         verdict: str, tests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "schema": BLOCK_SCHEMA,
        "generated_by": "tools/mvp05_ps2_texture_identities.py",
        "source": Path(source).name,
        "dump_directory": str(dump_dir),
        "question": ("Does this texture dump carry the decoded pixels of any SHPS code-0x0E "
                     "image, which would be the answer key the codec needs?"),
        "verdict": verdict,
        "tests": list(tests),
        **dict(report),
    }


# --------------------------------------------------------------------------
# Self-test: synthetic bank, synthetic dump, no disc
# --------------------------------------------------------------------------


def selftest(tmp: Optional[Path] = None) -> int:
    """Prove the pairing on data this file builds, with no game bytes anywhere."""

    import tempfile

    holder = None
    if tmp is None:
        holder = tempfile.TemporaryDirectory()
        tmp = Path(holder.name)
    try:
        tmp = Path(tmp)
        # One synthetic bank, one 8-bit image, decoded the way the disc side does.
        tag, body = containers.synthetic_indexed_image(32, 16, seed=4, tag="synt")
        bank = ea_shps.parse(containers.synthetic_bank([(tag, body)]), "synthetic.ssh")
        image = bank.image(0)
        palette = ea_shps.read_palette(bank, image.palette, raw_alpha=True)
        names, note = art_lane._identities(bank, image)
        assert names, f"the synthetic image should be named, not {note!r}"
        levels = _levels(bank, image)
        rgba = _rgba_from_indices(levels[0][2], palette)
        rgba_digest, rgb_digest = _digests(rgba)
        disc = [DiscTexture(archive="SYNTH.BIG", path="/DATA/SYNTH.BIG", entry=0,
                            entry_name="synthetic.ssh", image=0, tag=tag, level=0,
                            width=32, height=16, code="0x02", rgba_digest=rgba_digest,
                            rgb_digest=rgb_digest, names=names)]

        # A dump directory holding exactly what PCSX2 would have written.
        frame = "20260101010101"
        wanted = names[pcsx2_texture_name.CONVENTION_MODERN][0]
        for convention in CONVENTIONS:
            leg = tmp / frame / convention
            leg.mkdir(parents=True, exist_ok=True)
            for name in names.get(convention, ()):
                (leg / name).write_bytes(ea_shps.encode_png(32, 16, rgba))
        # One PNG of something else, so the unmatched leg is exercised too.
        other = bytes(bytearray((value * 3) & 0xFF for value in range(8 * 8 * 4)))
        (tmp / frame / pcsx2_texture_name.CONVENTION_MODERN /
         "aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-00000cd3.png").write_bytes(
            ea_shps.encode_png(8, 8, other))

        dumps = scan_dump(tmp)
        assert len(dumps) >= 2, dumps
        report = pair(dumps, disc)
        assert list(report.matched) == ["SYNTH.BIG:0:0"], report.matched
        entry = report.matched["SYNTH.BIG:0:0"]
        assert wanted in entry["names"][pcsx2_texture_name.CONVENTION_MODERN], entry
        assert entry["frames"] == [frame], entry
        assert len(report.unmatched_dumps) == 1, report.unmatched_dumps

        check = derivation_check(report, disc)
        assert check["derived_but_a_different_name"] == 0, check
        assert check["derived_name_is_the_confirmed_name"] == check["confirmed_names_checked"], check

        # The same pixels drawn as a high-byte surface get a different name in
        # both halves, and the lane derives that one too -- which is the whole
        # reason the check above comes out clean on this disc's park textures.
        level = pcsx2_texture_name.TextureLevel(32, 16, 8, levels[0][2])
        low = pcsx2_texture_name.derive_names([level], palette)
        high = [item for item in pcsx2_texture_name.derive_names(
            [level], palette, extra_psms=(pcsx2_texture_name.PSMT8H,))
            if item.psm == pcsx2_texture_name.PSMT8H]
        assert high, "the high-byte mode should add names"
        assert {item.name for item in high}.isdisjoint({item.name for item in low})
        assert all(item.name in names[item.convention] for item in high), names
        confirmed_psms = {pcsx2_texture_name.parse_name(name).psm
                          for names_of in entry["names"].values() for name in names_of}
        assert confirmed_psms == {pcsx2_texture_name.PSMT8, pcsx2_texture_name.PSMT8H}, confirmed_psms

        # The block-codec leg: a 0x0E image whose palette no dump draws from.
        blocks = [BlockImage(key="SYNTH.BIG:1:0", archive="SYNTH.BIG", width=16, height=16,
                             payload_bytes=96, palette_entries=256, palette_distinct=250,
                             clut=0x1234)]
        # The structural leg, on pictures this file builds: one probe correlates
        # perfectly with itself and near zero with an unrelated picture.
        def checker(phase: int) -> bytes:
            out = bytearray()
            for y in range(16):
                for x in range(16):
                    value = 255 if ((x // 4) + (y // 4) + phase) % 2 else 0
                    out += bytes((value, value, value, 128))
            return bytes(out)

        first, contrast = normalise(block_means(checker(0), 16, 16))
        second, _ = normalise(block_means(checker(1), 16, 16))
        assert first is not None and second is not None, contrast
        # Opposite phases: a perfect anti-correlation, which is as far from a
        # pair as this measure goes.
        assert math.fsum(a * b for a, b in zip(first, second)) < -0.99
        assert abs(math.fsum(a * b for a, b in zip(first, first)) - 1.0) < 1e-5
        flat, flat_contrast = normalise(block_means(bytes(16 * 16 * 4), 16, 16))
        assert flat is None and flat_contrast == 0.0, flat_contrast
        synthetic_palette = [(index, 255 - index, (index * 3) & 0xFF, 128) for index in range(256)]
        thumb = endpoint_thumbnail(bytes(range(32)), synthetic_palette, 16, 4)
        assert thumb is not None and len(thumb) == 4 * 3, thumb

        block_report = block_codec_report(dumps, blocks, [], {})
        block_report["structural_pairing"] = structural_report(dumps, {}, [], {})
        block_report["lerp_residuals"] = []
        # The per-draw leg, on an upload this file writes: a checkerboard has
        # two indices in a block and passes; a ramp has sixteen and does not.
        holder_dir = tmp / "drawdump" / "20260101010101"
        holder_dir.mkdir(parents=True, exist_ok=True)
        flat = bytearray()
        ramp = bytearray()
        for y in range(16):
            for x in range(16):
                value = 255 if ((x // 4) + (y // 4)) % 2 else 0
                flat += bytes((value, value, value, 255))
                step = (y * 16 + x) & 0xFF
                ramp += bytes((step, step, step, 255))
        (holder_dir / "00001_transfer00_EE_to_GS_1000_1_P_8_0_0_16_16.png").write_bytes(
            ea_shps.encode_png(16, 16, bytes(flat)))
        (holder_dir / "00002_transfer00_EE_to_GS_2000_1_P_8_0_0_16_16.png").write_bytes(
            ea_shps.encode_png(16, 16, bytes(ramp)))
        found, found_cluts = scan_draw_dump([holder_dir])
        assert len(found) == 2 and found_cluts == {}, (found, found_cluts)
        checker = next(u for u in found if u.most_distinct_in_a_block == 1)
        steps = next(u for u in found if u.most_distinct_in_a_block == 16)
        assert checker.blocks_over_four == 0 and steps.blocks_over_four == steps.blocks
        assert steps.block_codec_budget == 16 * 16 * 3 // 8
        drawn = draw_dump_report(found, {}, {}, found_cluts)
        assert drawn["distinct_8bit_uploads"] == 2, drawn
        assert drawn["uploads_where_every_4x4_block_has_at_most_four_indices"] == 1, drawn
        assert drawn["uploads_with_no_disc_twin"] == 2, drawn
        block_report["per_draw_dump"] = drawn
        assert block_report["structural_pairing"]["probe_pictures"] == 0, block_report
        assert block_report["clut_hash_candidates"] == [], block_report
        assert block_report["palette_subset_candidates"] == [], block_report
        assert block_report["palette_hunt_ran"] is True, block_report
        verdict, tests = block_codec_verdict(block_report)
        assert "no" in verdict.lower(), verdict
        assert len(tests) == 6, tests
        json.dumps(build_block_document(Path("synthetic.iso"), tmp, block_report, verdict, tests))

        document = build_document(Path("synthetic.iso"), tmp, dumps, disc, blocks, report)
        assert document["schema"] == SCHEMA
        assert document["counts"]["disc_images_confirmed"] == 1, document["counts"]
        assert document["coverage_by_archive"]["SYNTH.BIG"]["confirmed"] == 1, document
        json.dumps(document)   # it has to be serialisable, every value of it
        print("mvp05_ps2_texture_identities selftest: OK")
        return 0
    finally:
        if holder is not None:
            holder.cleanup()


# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="the retail ISO, read only")
    parser.add_argument("--dump-dir", type=Path, help="the directory PCSX2 dumped into")
    parser.add_argument("--index", type=Path, help="read the disc index from here instead of walking")
    parser.add_argument("--write-index", type=Path, help="walk the disc and write the index here")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                        help="where the three measured documents go")
    parser.add_argument("--note", default="", help="one sentence about the capture")
    parser.add_argument("--frame-labels", type=Path,
                        help="JSON mapping a frame stamp to what that frame shows")
    parser.add_argument("--draw-dump", type=Path, nargs="*", default=(),
                        help="per-draw GS dump directories, one per frame; a replacement dump "
                             "writes only textures sourced from a plain transfer and these "
                             "write everything")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    def say(line: str) -> None:
        if not args.quiet:
            print(line, flush=True)

    started = time.time()
    dumps: List[DumpTexture] = []
    if args.dump_dir is not None:
        dumps = scan_dump(args.dump_dir)
        say(f"dump scanned: {len(dumps):,} texture(s)")
    palette_hits: Optional[Dict[Tuple[str, str], List[str]]] = None
    structural: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    draw_uploads: List[DrawUpload] = []
    draw_cluts: Dict[str, List[str]] = {}
    upload_owners: Dict[str, List[str]] = {}
    clut_owners: Dict[str, Dict[str, List[str]]] = {}
    if args.draw_dump:
        draw_uploads, draw_cluts = scan_draw_dump(args.draw_dump)
        say("per-draw dump: %d distinct 8-bit upload(s), %d distinct CLUT(s)"
            % (len(draw_uploads), len(draw_cluts)))
    if args.index and args.index.exists():
        (levels, blocks, counts, palette_hits, structural, upload_owners,
         clut_owners) = read_index(args.index)
        say(f"disc index read from {args.index}: {len(levels):,} level(s), {len(blocks):,} block "
            f"codec image(s)")
    else:
        if args.source is None:
            parser.error("give --source, or an --index a previous run wrote")
        (levels, blocks, counts, palette_hits, structural, upload_owners,
         clut_owners) = index_disc(
            args.source, progress=None if args.quiet else say, dumps=dumps,
            uploads={u.digest: u for u in draw_uploads} or None, cluts=draw_cluts or None)
        say(f"disc walked in {time.time() - started:.0f}s: {counts}")
        target = args.write_index or args.index
        if target is not None:
            write_index(target, args.source, levels, blocks, counts, palette_hits, structural,
                        upload_owners, clut_owners)
            say(f"disc index written to {target}")
    if args.dump_dir is None:
        if args.write_index:
            return 0
        parser.error("give --dump-dir, or only --write-index to build the index")

    report = pair(dumps, levels)
    say(f"paired: {report.dumps_matched:,} dumped file(s) equal {len(report.matched):,} disc "
        f"image(s) exactly")
    labels = {}
    if args.frame_labels and args.frame_labels.exists():
        labels = json.loads(args.frame_labels.read_text(encoding="utf-8"))
    document = build_document(args.source or Path(str(args.index)), args.dump_dir, dumps, levels,
                              blocks, report, note=args.note, frame_labels=labels)
    check = derivation_check(report, levels)
    say("derivation: %d of %d confirmed name(s) are derived from the disc bytes; %d differ"
        % (check["derived_name_is_the_confirmed_name"], check["confirmed_names_checked"],
           check["derived_but_a_different_name"]))
    tex0_only: Dict[str, Any] = {}
    if args.source is not None and check["no_name_derived_for_the_disc_image"]:
        tex0_only = tex0_only_check(args.source, report, levels)
        say("of the %d distinct confirmed filename(s) with no derived name, the TEX0 half is "
            "reproduced for %d"
            % (tex0_only["their_distinct_filenames"],
               tex0_only["tex0_half_reproduced_from_the_disc"]))
    block = block_codec_report(dumps, blocks, report.matched, palette_hits)
    probes: List[Dict[str, Any]] = []
    if args.source is not None:
        by_name = {(row.convention, row.name): row for row in dumps}
        seen_probe = set()
        for row in (block["clut_hash_candidates"] + block["palette_subset_candidates"]):
            dump = by_name.get((row["convention"], row["dump"]))
            for key in row["block_images"]:
                if dump is None or (row["dump"], key) in seen_probe:
                    continue
                seen_probe.add((row["dump"], key))
                try:
                    probes.append(probe_candidate(args.source, args.dump_dir, dump, key))
                except (IdentityError, containers.DiscError, ea_shps.ShpsError, OSError) as exc:
                    probes.append({"dump": row["dump"], "block_image": key, "error": str(exc)})
    block["ground_truth_probes"] = probes
    block["structural_pairing"] = structural_report(
        dumps, structural, {name for entry in report.matched.values()
                            for names in entry["names"].values() for name in names}, counts)
    residuals: List[Dict[str, Any]] = []
    if args.source is not None:
        ceiling = block["structural_pairing"]["null_ceiling"]
        for row in block["structural_pairing"]["ranking"]:
            if row["already_paired_to_a_decoded_image"]:
                continue
            if ceiling is not None and row["best"][0]["ncc"] <= ceiling:
                continue
            dump = next((d for d in dumps if d.name == row["dump"]
                         and d.convention == row["convention"]), None)
            if dump is None:
                continue
            try:
                residuals.append(lerp_residual(args.source, args.dump_dir, dump,
                                               row["best"][0]["key"]))
            except (IdentityError, containers.DiscError, ea_shps.ShpsError, OSError) as exc:
                residuals.append({"dump": row["dump"], "block_image": row["best"][0]["key"],
                                  "error": str(exc)})
    block["lerp_residuals"] = residuals
    if draw_uploads:
        block["per_draw_dump"] = draw_dump_report(draw_uploads, clut_owners, upload_owners,
                                                  draw_cluts)
        say("per-draw: %d of %d upload(s) are a disc 0x02 image; %d upload(s) could be a block "
            "decode" % (block["per_draw_dump"]["uploads_that_are_a_disc_0x02_image_byte_for_byte"],
                        block["per_draw_dump"]["distinct_8bit_uploads"],
                        block["per_draw_dump"]["uploads_where_every_4x4_block_has_at_most_four_indices"]))
    say("structure: %d probe picture(s), null ceiling %s, %d above it, %d residual probe(s)"
        % (block["structural_pairing"]["probe_pictures"],
           block["structural_pairing"]["null_ceiling"],
           block["structural_pairing"]["above_the_null_ceiling"], len(residuals)))
    verdict, tests = block_codec_verdict(block)
    say("block codec: " + verdict)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_name = args.source or Path(str(args.index))
    _write(out_dir / art_lane.IDENTITY_DOCUMENT.name, document)
    _write(out_dir / DERIVATION_DOCUMENT,
           build_derivation_document(source_name, check, tex0_only))
    _write(out_dir / BLOCK_DOCUMENT, build_block_document(source_name, args.dump_dir, block,
                                                          verdict, tests))
    say(f"written under {out_dir}")
    return 0


def _write(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
