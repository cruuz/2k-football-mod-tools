"""A lane whose targets are ``MMAP`` textures inside ``TERF`` container members.

Two Tiburon discs of the same generation put their art in the same place:
``MMAP`` textures inside ``TERF`` containers, read by
:mod:`mod_editor.games._formats.mmap_art`.  Madden NFL 09 has five such pages
(uniforms, stadiums, field art, presentation, faces) and NCAA Football 09 has
five more (uniforms and equipment, stadiums, field and create-team art,
presentation, faces).  **Ten rows, one lane**: what differs between them is
which containers to walk, which page the row lands on, and its own schema
strings -- all class attributes -- plus the game's own disc-access module.

Two classes, and the second is the first plus a writer:

* :class:`TerfArtLane` catalogues every texture on the user's own disc, decodes
  one to PNG on demand, checks a PNG the user offers back, derives the PCSX2
  replacement identity, and exports a chosen set as a folder of PNGs with a
  receipt an independent verifier re-derives.  ``extract-only``.
* :class:`TerfArtWriteLane` adds the disc write: re-encode the texture through
  ``mmap_art``, re-pack the member under a codec that fits the slot it owns,
  rewrite every preload-cache copy the edit disturbed, and hand the result to
  the repository's bounded ISO9660 writer.  ``offline-writer-proved``.

**The PCSX2 replacement identity is derived, and confirmed where a dump
exists.**  Naming a texture so PCSX2's replacement picks it up needs the GS
``TEX0`` and CLUT hashes the emulator computes at draw time.
:func:`derive_texture_names` computes both from the texture's own bytes through
:mod:`mod_editor.games._formats.pcsx2_texture_name`, and a game's own identity
document records which of those names a real texture dump has shown PCSX2
writing.  A lane sets :attr:`TerfArtLane.identity_document` to its game's;
:meth:`TerfArtLane.replacement_identity` answers with a confirmed name first
and a derived one otherwise.

**Nothing here has been booted.**  Every claim is offline: the user's own
image, a destination image, an independent verifier that re-reads it, and a
conformance harness that proves the whole path on a synthetic disc.

This was Madden 09's ``uniform_art.py`` until NCAA Football 09 needed the same
lane over a different set of containers.  Moving it here is what makes a fix to
the encoder a fix to ten rows rather than to five.

**Evidence tags.**  **[M]** measured; **[S]** sourced; **[A]** assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import zlib

from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    DeclaredRange,
    Edit,
    EncodedArt,
    Field,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
)

from mod_editor.games._formats import ea_terf
from mod_editor.games._formats import pcsx2_texture_name as texture_identity

from mod_editor.games._formats import mmap_art

from . import iso_tools, preload_coherence


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: The evidence document ``tools/madden09_ps2_texture_identities.py`` writes:
#: which texture on the disc PCSX2 saw, and under what filename.  Counts,
#: dimensions, filenames and member indexes; no pixel.
#: The schema a game's identity document declares, when it does not name its
#: own.  The pairing of a texture dump with a disc is the same measurement
#: whichever disc it was, but each game's shipped document already declares a
#: schema of its own, so :func:`load_identities` takes one rather than
#: assuming this.
IDENTITY_SCHEMA = "ps2_pcsx2_texture_identities/v1"

#: Which name :meth:`TerfArtLane.replacement_identity` hands back when a
#: texture was dumped under more than one convention.  ``classic`` first: it is
#: what PenguinScreen2 and the legacy replacement packs load, and stock PCSX2
#: ignores the TCC bit that distinguishes the two, so a classic name loads on
#: every build there has ever been.
IDENTITY_CONVENTIONS = ("classic", "modern")

_IDENTITY_CACHE: Dict[str, Any] = {}


def load_identities(path: Optional[Path] = None,
                    schema: str = IDENTITY_SCHEMA) -> Dict[str, Dict[str, List[str]]]:
    """``target key -> {convention: [filenames]}``, or nothing at all.

    An empty mapping is the honest answer for a user who has not dumped their
    own textures, and it is the state this lane shipped in: no name is
    invented, and the pack step keeps the refusal it always had.
    """

    if path is None:
        return {}
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path(__file__).resolve().parents[3] / resolved
    key = f"{resolved}|{schema}"
    cached = _IDENTITY_CACHE.get(key)
    if cached is not None:
        return cached
    out: Dict[str, Dict[str, List[str]]] = {}
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        document = {}
    if isinstance(document, Mapping) and document.get("schema") == schema:
        for target, entry in (document.get("identities") or {}).items():
            names = entry.get("names") if isinstance(entry, Mapping) else None
            if isinstance(names, Mapping) and names:
                out[str(target)] = {str(convention): list(values)
                                    for convention, values in names.items() if values}
    _IDENTITY_CACHE[key] = out
    return out

#: The art containers, and what the disc itself says about how they are
#: organised.  Only the first column is a fact about *this* module; the rest is
#: what the containers reveal, with an honest label on each.
#:
#: ``group`` is what a page can sort by today, and a container that names
#: nothing (``UNIFORMS.DAT`` on Madden 09, ``UNIFORM.DAT`` on NCAA 09) offers
#: -- every one of its 455 members carries 15 unnamed images -- so the member
#: index is the only structure it offers, and which team a member belongs to is
#: **not established here** [A].  ``PLYRFACE`` and ``COACFACE`` name their one
#: image ``FACE`` and ``TATTOOS`` names its own, so those groups are read from
#: the file [M].
#: What a sentence calls the identity tool when a game has not written one.
IDENTITY_TOOL_UNKNOWN = "this game's identity tool"

#: How many textures a catalogue offers as targets by default.  A page
#: whose containers hold more says so in its document either way.
MAX_TARGETS = 4000

#: Cataloguing a member costs one whole decode, and there is no way around it.
#:
#: Only the **surface** table sits at the front of an ``MMAP`` member.  The
#: image, palette and name tables sit at the *end*, after the pixels: in
#: ``UNIFORMS.DAT``'s first member the surface table is at byte 40 and the
#: palette table at byte 331,728 of 356,820 [M].  So a prefix read cannot
#: catalogue one, and an ``LZH1`` stream cannot be decoded from its tail.  What
#: this lane does instead is decode each member **once** -- checking the magic
#: on the result rather than asking for it separately, which was costing a
#: second decode of every member for a 32-byte answer.
#:
#: On the retail disc that is 1,780 members and a few minutes in pure Python.
#: The studio runs a catalogue in a child process with progress lines for
#: exactly this reason.
CATALOGUE_COST_NOTE = (
    "Cataloguing decodes every texture member once; the retail disc has 1,780 of them."
)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def write_rgba_png(pixels: bytes, width: int, height: int) -> bytes:
    """An 8-bit RGBA, non-interlaced PNG. No Pillow, so this runs everywhere."""

    require(len(pixels) == width * height * 4,
            f"an RGBA image of {width}x{height} needs {width * height * 4} bytes, "
            f"not {len(pixels)}")
    stride = width * 4
    raw = b"".join(b"\x00" + pixels[row * stride:(row + 1) * stride] for row in range(height))
    return (PNG_SIGNATURE
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw, 6))
            + _png_chunk(b"IEND", b""))


def read_rgba_png(payload: bytes) -> Tuple[int, int, bytes]:
    """``(width, height, RGBA bytes)`` from an 8-bit non-interlaced PNG.

    Refuses anything else by name -- a palette PNG, a 16-bit one, an interlaced
    one -- because a silent conversion is how a user ends up with art that is
    not what they drew.
    """

    require(payload[:8] == PNG_SIGNATURE and len(payload) >= 33 and payload[12:16] == b"IHDR",
            "that file is not a PNG; export a texture first and edit the file it wrote.")
    width, height, depth, colour, _compression, _filter, interlace = struct.unpack_from(
        ">IIBBBBB", payload, 16)
    require(depth == 8,
            f"that PNG is {depth} bits per channel and this lane reads 8; save it as an "
            f"8-bit PNG.")
    require(interlace == 0, "that PNG is interlaced; save it without interlacing.")
    require(colour in (2, 6),
            f"that PNG's colour type is {colour}; save it as RGB or RGBA, not indexed or "
            f"greyscale.")
    channels = 4 if colour == 6 else 3
    idat = bytearray()
    position = 8
    while position + 8 <= len(payload):
        length, = struct.unpack_from(">I", payload, position)
        tag = payload[position + 4:position + 8]
        body = payload[position + 8:position + 8 + length]
        if tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
        position += 12 + length
    require(bool(idat), "that PNG carries no image data; it is truncated or empty.")
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as exc:
        raise Refusal(f"that PNG's image data could not be read ({exc}); re-save it.") from exc
    stride = width * channels
    require(len(raw) == (stride + 1) * height,
            f"that PNG says it is {width}x{height} but its data unpacks to {len(raw)} bytes "
            f"instead of {(stride + 1) * height}; re-save it.")
    out = bytearray(width * height * 4)
    previous = bytearray(stride)
    for row in range(height):
        start = row * (stride + 1)
        filter_type = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                value = line[index]
            elif filter_type == 1:
                value = line[index] + left
            elif filter_type == 2:
                value = line[index] + up
            elif filter_type == 3:
                value = line[index] + ((left + up) >> 1)
            elif filter_type == 4:
                estimate = left + up - upper_left
                da, db, dc = (abs(estimate - left), abs(estimate - up),
                              abs(estimate - upper_left))
                nearest = left if (da <= db and da <= dc) else (up if db <= dc else upper_left)
                value = line[index] + nearest
            else:
                raise Refusal(
                    f"that PNG uses row filter {filter_type} on row {row}, which is not one of "
                    f"the five PNG defines; re-save it.")
            line[index] = value & 0xFF
        for column in range(width):
            source = column * channels
            destination = (row * width + column) * 4
            out[destination] = line[source]
            out[destination + 1] = line[source + 1]
            out[destination + 2] = line[source + 2]
            out[destination + 3] = line[source + 3] if channels == 4 else 255
        previous = line
    return int(width), int(height), bytes(out)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


#: Where a derived name sits in :meth:`TerfArtLane.replacement_identities`.
#: A dump-confirmed name keeps PCSX2's own convention word; a derived one is
#: prefixed so a caller can never mistake the two.
DERIVED_PREFIX = "derived:"


def derive_texture_names(payload: bytes, texture: mmap_art.MmapTexture,
                         image: mmap_art.Image) -> Tuple[Dict[str, List[str]], str]:
    """Every PCSX2 name this image would be looked up under, from its own bytes.

    Returns ``({convention: [names]}, "")`` or ``({}, why not)``.  The names
    are :mod:`pcsx2_texture_name`'s: the GS block hash of each mip chain the
    game can draw, and the CLUT hash of the image's **own first palette**.  A
    draw that borrows an alternate CLUT -- the team recolours a uniform sheet
    carries as palette-only entries -- has a different second half, and a CLUT
    the game builds at run time has none this can predict; the note says so.
    """

    levels: List[texture_identity.TextureLevel] = []
    for level in range(image.mip_count):
        surface = texture.surfaces[image.first_surface + level]
        try:
            indices = mmap_art.unpack_indices(mmap_art.surface_pixels(payload, surface),
                                              surface)
        except mmap_art.MmapError as exc:
            return {}, f"no name is derived: level {level} could not be read ({exc})"
        bits = 8 if surface.pixel_layout == mmap_art.PIXELS_INDEXED_8 else 4
        levels.append(texture_identity.TextureLevel(surface.width, surface.height, bits,
                                                    indices))
    if not levels or image.palette_count == 0:
        return {}, "no name is derived: this image has no pixels or no palette of its own"
    try:
        palette = mmap_art.read_palette(payload, texture.palettes[image.first_palette])
        derived = texture_identity.derive_names(levels, palette)
    except Refusal as exc:
        return {}, f"no name is derived: {exc}"
    return texture_identity.names_by_convention(derived), ""


def _key(container: str, member: int, image: int) -> str:
    return f"{container}:{member}:{image}"


def _file_name(container: str, member: int, image: int, width: int, height: int) -> str:
    stem = container.split(".")[0].lower()
    return f"{stem}-m{member:04d}-i{image:02d}-{width}x{height}.png"


class TerfArtLane:
    """Every ``MMAP`` texture on the disc: preview, export, and a checked import.

    **Container-parameterised.**  Which containers a lane walks, which page it
    lands on and which schemas it writes are class attributes, so a second art
    page is this class with a different :attr:`art_containers` rather than a
    second copy of the catalogue, the decoder and the PNG reader.  The uniform
    rows are the defaults; :mod:`.art_pages` sets the rest.
    """

    #: Every one of these is a game's to set.
    discs: Any = None
    lane_id = ""
    capability_id = ""
    surface = "uniforms"
    page = "uniforms"
    title = "Uniform, face and tattoo textures"
    classification = "extract-only"
    #: ``(container file name, group, what the file says about its structure)``
    #: -- the containers this lane catalogues and is willing to write.
    art_containers: Tuple[Tuple[str, str, str], ...] = ()
    #: Whether a preload cache's copy of a rewritten member may come back
    #: shorter.  Off here: a re-encoded texture is repacked to fit the slot it
    #: already owns, and Madden 09's five rows were proved under the strict
    #: rule, so a size change in a *carried* member stays a refusal until a
    #: lane has a reason to relax it.
    cached_member_may_shrink = False
    #: The game's ``docs/product/measured/<game>/pcsx2-texture-identities.json``,
    #: or ``None`` when no dump has been paired with that disc yet.
    identity_document: Optional[Path] = None
    #: The schema that document declares.  Each game's shipped document names
    #: its own, so a lane says which rather than the base assuming one.
    identity_schema: str = IDENTITY_SCHEMA
    #: What a sentence calls this game.  Every refusal and every receipt line
    #: that names a game reads it from here, so a base's wording is the lane's
    #: game and not the game the base was written for.
    game_title: str = "this game"
    #: The tool that pairs a PCSX2 texture dump with this disc, when one
    #: exists.  Empty when none has been written yet, and the identity note
    #: says so instead of naming a tool a user cannot run.
    identity_tool: str = ""
    #: How well the derivation reproduces the names a real dump wrote, as one
    #: clause the identity note reads out.  It is a **measurement of one
    #: disc**, and every game that has paired a dump should set its own from
    #: its ``pcsx2-texture-identity-derivation.json``: the base's default is
    #: Madden 09's, which is the number this sentence carried when it was a
    #: literal in the note and the only measurement there was.
    derivation_evidence: str = (
        "the rule reproduces the dumped hash of 2,994 of 3,024 dump-identified retail "
        "textures")
    #: How many textures the catalogue offers as targets.
    max_targets = MAX_TARGETS
    #: How many targets ONE container may take of that cap, or ``None`` for no
    #: per-container share.  Without it the first container listed can spend
    #: the whole budget and the last one is unreachable -- which is not a
    #: table being a table, it is a container a user cannot open.  Measured on
    #: NCAA Football 09: ``UNIFORM.DAT``'s 1,200 members carry about 15,600
    #: images between them, so a flat 4,000 hid all 396 of ``UIS_GEAR.DAT``'s
    #: -- the one container on that disc no preload cache names, and therefore
    #: the cheapest thing on it to rewrite [M].
    max_targets_per_container: Optional[int] = None
    catalog_schema = ""
    recipe_schema = ""
    write_schema = ""
    #: A lane sets its own; a base cannot know them.
    validators: Tuple[str, ...] = ()
    #: The lane publishes files rather than rewriting the source, so it
    #: declares artifacts instead of byte ranges.
    fixed_allocation = False

    #: What a catalogue says about the members it lists but cannot open.  Every
    #: art container on this disc carries members that are not textures, and
    #: they are **listed read-only** rather than hidden: a page that showed only
    #: the textures would leave a user thinking the rest of the file was empty.
    NOT_TEXTURE_NOTE = (
        "Members counted by format. Only MMAP members are textures this lane reads or writes. "
        "SMF and DMF members are EA geometry -- SMF static (fields, stadium shells), DMF "
        "animated (players, coaches, fans) -- and NO decoder for either is built here and no "
        "layout for either is documented anywhere in this repository, so they are listed and "
        "left alone. An empty member is a real zero-length slot the container declares, and an "
        "unclassified one is a member whose first 32 bytes match no format id this reader "
        "knows. None of the three is opened, previewed or written."
    )

    NO_IDENTITY = (
        "A PCSX2 replacement file is named from the GS TEX0 and CLUT hashes the emulator "
        "computes at draw time. This lane derives both from the texture's own bytes -- the "
        "GS block image of each mip chain and the image's own palette -- and marks a name "
        "confirmed where a texture dump of the game running has shown PCSX2 writing it. "
        "A texture "
        "whose size is not a power of two, or that the game draws with a CLUT it builds at "
        "run time, gets no derived name, and no pack built from any of these names has been "
        "loaded by an emulator yet."
    )

    #: What the page says for a texture with no derived name and no table at
    #: all -- the state a user without a dump is in for the few textures the
    #: derivation cannot name.
    NO_IDENTITY_TABLE = (
        "No PCSX2 texture dump has been paired with this disc and no name could be derived "
        "for this texture. Run the game once in PCSX2 with texture dumping on, then pair the "
        "dump with your image using this game's identity tool, and the names a dump confirms "
        "appear here."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = self.discs.open_disc(Path(source))
        present = {entry.name: entry for entry in self.discs.data_files(image)}
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"members": 0, "images": 0, "decodable": 0}
        skipped: Dict[str, str] = {}
        refusals: Dict[str, int] = {}
        census: Dict[str, Dict[str, int]] = {}

        for name, group, note in self.art_containers:
            entry = present.get(name)
            if entry is None:
                skipped[name] = "not on this image"
                continue
            if progress is not None:
                progress(f"{name}…")
            _report, container = self.discs.describe_container(image, entry, with_formats=False)
            if container is None:
                # The reader's own sentence when it has one: on the Deluxe disc
                # UNIFORMS.DAT is 137 MB, over the read limit, and "could not
                # be opened" would misreport a size as a format failure.
                skipped[name] = _report.note or "could not be opened as a TERF container"
                continue
            counted = census.setdefault(name, {})
            listed_here = 0
            for index in range(len(container)):
                # Classify from the member's first 32 bytes -- the codec stops
                # there -- and unpack only the textures.  ``FIELDART.DAT`` is
                # 642 SMF geometry members against 73 textures and
                # ``STADIUMS.DAT`` 651 against 434 [M]; decompressing all of
                # them to read a four-byte magic is most of a catalogue's cost
                # for an answer the head already gives.
                try:
                    kind = container.member_format(index) or "unclassified"
                except Exception:  # noqa: BLE001 - one bad member must not end the walk
                    kind = "undecodable"
                counted[kind] = counted.get(kind, 0) + 1
                if kind != "MMAP":
                    continue
                try:
                    payload = self.discs.member_uncached(container, index)
                except Exception:  # noqa: BLE001 - one bad member must not end the walk
                    continue
                if not payload.startswith(mmap_art.MMAP_MAGIC):
                    continue
                totals["members"] += 1
                if progress is not None and totals["members"] % 32 == 0:
                    progress(f"{name}: {totals['members']} texture member(s) read…")
                try:
                    texture = mmap_art.parse(payload)
                except mmap_art.MmapError as exc:
                    refusals[str(exc)[:120]] = refusals.get(str(exc)[:120], 0) + 1
                    continue
                for entry_image in texture.images:
                    totals["images"] += 1
                    reason = texture.undecodable_reason(entry_image)
                    if reason is not None:
                        refusals[reason] = refusals.get(reason, 0) + 1
                        continue
                    totals["decodable"] += 1
                    surface = texture.surfaces[entry_image.first_surface]
                    row = {
                        "container": name,
                        "group": group,
                        "member": index,
                        "image": entry_image.index,
                        "name": entry_image.name,
                        "width": surface.width,
                        "height": surface.height,
                        "layout": surface.layout_name,
                        "codec": surface.codec,
                        "mips": entry_image.mip_count,
                        "palettes": entry_image.palette_count,
                        "version": texture.version,
                        "file_name": _file_name(name, index, entry_image.index,
                                                surface.width, surface.height),
                    }
                    derived, derived_note = derive_texture_names(payload, texture, entry_image)
                    row["derived_names"] = derived
                    row["derived_note"] = derived_note
                    rows.append(row)
                    room = len(targets) < self.max_targets and (
                        self.max_targets_per_container is None
                        or listed_here < self.max_targets_per_container)
                    if room:
                        targets.append(self._target(row, note))
                        listed_here += 1
        document = {
            "schema": self.catalog_schema,
            "source": str(source),
            "containers": [
                {"name": name, "group": group, "structure": note}
                for name, group, note in self.art_containers
            ],
            "members_read": totals["members"],
            "images_seen": totals["images"],
            "images_decodable": totals["decodable"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "targets_cap": self.max_targets,
            "targets_cap_per_container": self.max_targets_per_container,
            "skipped": skipped,
            "not_decodable": refusals,
            "members_by_format": census,
            "members_not_texture": {
                container_name: {kind: count for kind, count in sorted(kinds.items())
                                 if kind != "MMAP"}
                for container_name, kinds in sorted(census.items())
                if any(kind != "MMAP" for kind in kinds)
            },
            "members_not_texture_note": self.NOT_TEXTURE_NOTE,
            "rows": rows,
            "note": "Dimensions, formats and counts only. A texture's pixels are decoded when "
                    "you ask to see or export one, and are never stored in this catalogue.",
        }
        return Catalogue(self.catalog_schema, self.lane_id, str(source), tuple(targets),
                         document)

    @staticmethod
    def _target(row: Mapping[str, Any], structure: str) -> Target:
        detail = [f"{row['width']}x{row['height']}", row["layout"]]
        if row["mips"] > 1:
            detail.append(f"{row['mips']} mip levels")
        if row["palettes"] > 1:
            detail.append(f"{row['palettes']} palettes")
        if row["name"]:
            detail.append(row["name"])
        return Target(
            key=_key(row["container"], row["member"], row["image"]),
            label=f"{row['group']} · member {row['member']} · image {row['image']}"
                  + (f" ({row['name']})" if row["name"] else ""),
            detail=" · ".join(detail),
            budget=f"Export writes {row['file_name']}. Nothing is written to your disc.",
            searchable=f"{row['container']} {row['group']} {row['member']} {row['name']}",
            raw=dict(row, structure=structure),
            fields=(
                Field("png", "png", "Replacement PNG",
                      "A PNG the same size as this texture, or an exact integer multiple of it. "
                      "It is checked against the texture's own palette and reported on; there is "
                      "nowhere to write it yet."),
                Field("group", "note", "Group", "Which container this texture came from.",
                      read_only=True),
                Field("dimensions", "note", "Size", "Width by height of the largest mip level.",
                      read_only=True),
                Field("layout", "note", "Pixel layout",
                      "How the disc stores this texture's pixels.", read_only=True),
                Field("structure", "note", "What the file says",
                      "How this container organises its textures, and what it does not say.",
                      read_only=True),
            ),
        )

    # -- the art protocol ----------------------------------------------

    @staticmethod
    def parse_key(key: str) -> Tuple[str, int, int]:
        """``container:member:image`` back into its three parts.

        A target key is enough to find a texture on the disc, which is what
        lets :meth:`verify` re-derive an export **without** the catalogue that
        produced it -- an independent check has to be independent, and on a
        retail disc rebuilding the catalogue to check eight files would cost
        minutes for nothing.
        """

        parts = str(key).split(":")
        if len(parts) != 3 or not parts[0]:
            raise Refusal(
                f"{key!r} does not name a texture: a key is "
                f"<container>:<member>:<image>, as the catalogue writes it.")
        try:
            return parts[0], int(parts[1]), int(parts[2])
        except ValueError as exc:
            raise Refusal(
                f"{key!r} does not name a texture: its member and image must be whole "
                f"numbers, as the catalogue writes them.") from exc

    def _texture_at(self, source: Path, container_name: str, member: int
                    ) -> Tuple[bytes, mmap_art.MmapTexture]:
        disc = self.discs.open_disc(Path(source))
        container = self.discs.load_container(disc, container_name)
        payload = container.member(member)
        return payload, mmap_art.parse(payload)

    def _texture(self, source: Path, target: Target
                 ) -> Tuple[bytes, mmap_art.MmapTexture, int]:
        container_name = str(target.raw.get("container") or "")
        member = target.raw.get("member")
        image_index = target.raw.get("image")
        if not container_name or not isinstance(member, int) or not isinstance(image_index, int):
            container_name, member, image_index = self.parse_key(target.key)
        payload, texture = self._texture_at(Path(source), container_name, member)
        return payload, texture, image_index

    def decode_png(self, source: Path, target: Target) -> bytes:
        """The target's largest mip level, from the user's own disc, as PNG."""

        payload, texture, image_index = self._texture(Path(source), target)
        width, height, rgba = mmap_art.decode_rgba(payload, image=image_index, texture=texture)
        return write_rgba_png(rgba, width, height)

    def decode_png_by_key(self, source: Path, key: str) -> bytes:
        """The same, addressed by key alone -- no catalogue needed."""

        container_name, member, image_index = self.parse_key(key)
        payload, texture = self._texture_at(Path(source), container_name, member)
        width, height, rgba = mmap_art.decode_rgba(payload, image=image_index, texture=texture)
        return write_rgba_png(rgba, width, height)

    def encode(self, source: Path, target: Target, png: bytes) -> EncodedArt:
        """Check a PNG against the texture it would replace, and say how it fits.

        The size rule is the shell's: the same size, or an exact integer
        multiple of it.  Anything else is refused **naming the size that was
        wanted**, never silently resized.

        A same-size PNG is then indexed against the texture's own palette and
        the result is reported: a Madden 09 texture rides its own CLUT, so a
        colour that palette does not carry cannot be introduced, and the note
        says how many pixels landed on an exact entry rather than leaving the
        user to discover it later.
        """

        payload, texture, image_index = self._texture(Path(source), target)
        entry = texture.image(image_index)
        surface = texture.surfaces[entry.first_surface]
        width, height, rgba = read_rgba_png(png)
        wanted = f"{surface.width}x{surface.height}"
        if (width, height) != (surface.width, surface.height):
            require(width % surface.width == 0 and height % surface.height == 0
                    and width // surface.width == height // surface.height
                    and width > surface.width,
                    f"that PNG is {width}x{height} and this texture is {wanted}; give a PNG of "
                    f"exactly that size, or an exact whole-number multiple of it.")
            scale = width // surface.width
            return EncodedArt(png=png, width=width, height=height,
                              note=f"{scale}x the texture's own {wanted}. Kept at that size; "
                                   f"nothing is written to your disc.")
        entries = mmap_art.read_palette(payload, texture.palettes[entry.first_palette])
        indices = mmap_art.encode_indexed(rgba, width, height, surface, entries)
        exact = self._exact_matches(rgba, entries)
        return EncodedArt(
            png=png, width=width, height=height,
            note=(f"{wanted}, indexed against this texture's own {len(entries)}-colour palette: "
                  f"{exact:,} of {width * height:,} pixels land on an exact entry, and "
                  f"{len(indices):,} index byte(s) would be written. There is nowhere to write "
                  f"them yet -- no {self.game_title} container has been rebuilt and booted."),
        )

    @staticmethod
    def _exact_matches(rgba: bytes, entries: Sequence[Tuple[int, int, int, int]]) -> int:
        palette = {(red, green, blue, mmap_art._scale_alpha(alpha))
                   for red, green, blue, alpha in entries}
        return sum(1 for position in range(0, len(rgba), 4)
                   if tuple(rgba[position:position + 4]) in palette)

    def replacement_identity(self, target: Target) -> Optional[str]:
        """The PCSX2 filename for this texture.

        A name a dump has **confirmed** wins, ``classic`` in preference to
        ``modern``: the two differ only in whether the ``bits`` word carries
        TCC in bit 14, and every PCSX2 build parses a classic name, so one
        answer is right for both.  Otherwise the name **derived** from the
        texture's own bytes -- the GS block hash of its full mip chain and the
        CLUT hash of its own palette, under the modern convention that every
        build looks up -- which on the retail disc reproduces the dumped hash of
        2,994 of the 3,024 dump-identified textures [M].  ``None`` only
        when neither exists: :meth:`identity_note` says why.
        """

        names = self.replacement_identities(target)
        for convention in IDENTITY_CONVENTIONS:
            if names.get(convention):
                return names[convention][0]
        for convention in IDENTITY_CONVENTIONS:
            derived = names.get(DERIVED_PREFIX + convention)
            if derived:
                return derived[0]
        for values in names.values():
            if values:
                return values[0]
        return None

    def replacement_identities(self, target: Target) -> Dict[str, List[str]]:
        """Every filename this texture answers to, by naming convention.

        ``classic`` and ``modern`` are names a dump has shown PCSX2 writing for
        this texture; ``derived:classic`` and ``derived:modern`` are the names
        derived from its own bytes -- one per mip chain the game can draw, and
        under classic both TCC values.  A pack writer wants all of them: the
        dumped names are proved, the derived ones cover the draws no frame
        captured.
        """

        out = {convention: list(values) for convention, values
               in load_identities(self.identity_document, self.identity_schema).get(str(target.key), {}).items()}
        derived = target.raw.get("derived_names") if isinstance(target.raw, Mapping) else None
        if isinstance(derived, Mapping):
            for convention, values in derived.items():
                if values:
                    out[DERIVED_PREFIX + str(convention)] = list(values)
        return out

    def identity_note(self, target: Target) -> str:
        """One or two sentences about where this texture's name comes from, or why it has none."""

        names = self.replacement_identities(target)
        confirmed = {convention: values for convention, values in names.items()
                     if not convention.startswith(DERIVED_PREFIX) and values}
        derived = {convention[len(DERIVED_PREFIX):]: values
                   for convention, values in names.items()
                   if convention.startswith(DERIVED_PREFIX) and values}
        parts: List[str] = []
        if confirmed:
            parts.append("Confirmed by a PCSX2 dump -- " + "; ".join(
                f"{convention}: {', '.join(values)}"
                for convention, values in sorted(confirmed.items())) + ".")
        if derived:
            total = sum(len(values) for values in derived.values())
            first = (derived.get("modern") or next(iter(derived.values())))[0]
            parts.append(
                f"Derived from this texture's own bytes: {first} is the modern name for its "
                f"full mip chain, and {total} name(s) in all cover every mip range the game "
                f"can draw and both TCC values ({self.derivation_evidence}; a draw with an "
                f"alternate CLUT has a different second half).")
        elif isinstance(target.raw, Mapping) and target.raw.get("derived_note"):
            parts.append(str(target.raw["derived_note"]) + ".")
        if not parts:
            if not load_identities(self.identity_document, self.identity_schema):
                return self.NO_IDENTITY_TABLE
            return (f"No PCSX2 dump has shown {target.key} being drawn and no name could be "
                    f"derived for it. Dump the frame that draws it and re-run "
                    f"{self.identity_tool or IDENTITY_TOOL_UNKNOWN}.")
        if not confirmed and derived:
            parts.append("No dump has shown this texture; the name is computed, not observed.")
        return " ".join(parts)

    # -- plan / build / verify -----------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"png"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not something this lane takes; give "
                    f"a PNG, or nothing at all to export this texture as it is.")
        path = values.get("png")
        if path in (None, ""):
            return None
        try:
            payload = Path(str(path)).read_bytes()
        except OSError as exc:
            return f"{target.key}: {path} could not be read ({exc}); choose a PNG file."
        try:
            width, height, _rgba = read_rgba_png(payload)
        except Refusal as exc:
            return f"{target.key}: {exc}"
        wanted_width = int(target.raw.get("width") or 0)
        wanted_height = int(target.raw.get("height") or 0)
        if (width, height) == (wanted_width, wanted_height):
            return None
        if (wanted_width and wanted_height and width % wanted_width == 0
                and height % wanted_height == 0
                and width // wanted_width == height // wanted_height and width > wanted_width):
            return None
        return (f"{target.key}: that PNG is {width}x{height} and this texture is "
                f"{wanted_width}x{wanted_height}; give a PNG of exactly that size, or an exact "
                f"whole-number multiple of it.")

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"texture": edit.target_key}
            path = edit.values.get("png")
            if path:
                row["png"] = str(path)
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "textures": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {self.recipe_schema}")
        rows = recipe.get("textures")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'textures' list; choose at least one texture "
                "to export")
        seen: set = set()
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("texture"), str)
                    and row["texture"],
                    f"texture {number} must name the texture it exports")
            require(set(row) <= {"texture", "png", "note"},
                    f"texture {number} carries unknown keys")
            require(row["texture"] not in seen,
                    f"{row['texture']} appears twice; one texture is exported once")
            seen.add(row["texture"])
            out.append(dict(row))
        return out

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        entries = self._entries(recipe)
        rows = []
        for entry in entries:
            target = catalogue.target(entry["texture"])  # the catalogue's own refusal
            problem = self.check_edit(target, {k: v for k, v in entry.items()
                                               if k in ("png",)})
            require(problem is None, str(problem))
            rows.append({
                "texture": entry["texture"],
                "file_name": target.raw.get("file_name"),
                "width": target.raw.get("width"),
                "height": target.raw.get("height"),
                "replacement_identity": self.replacement_identity(target),
                "replacement_identities": self.replacement_identities(target),
                "identity_note": self.identity_note(target),
            })
        return Plan(self.lane_id, tuple(entry["texture"] for entry in entries), (), {
            "schema": self.recipe_schema,
            "textures": rows,
            "identity_note": self.NO_IDENTITY,
        })

    @staticmethod
    def export_root_for(destination: Path) -> Path:
        """Where the PNGs go: a folder beside the destination the caller named.

        The destination itself is the **manifest** -- one JSON file naming
        every exported texture and its digest.  A build's destination is a file
        by contract (the harness digests it, and the studio chains one step's
        output into the next), so the pictures live in a folder next to it, the
        way the sibling PS2 module writes its replacement pack.
        """

        destination = Path(destination)
        return destination.with_name(destination.name + "-textures")

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        import os

        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build writes a NEW manifest and never "
                f"the disc.")
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite")
        export_root = self.export_root_for(destination)
        require(not os.path.lexists(export_root),
                f"the export folder {export_root} already exists; choose a destination whose "
                f"folder is free")
        planned = self.plan(source, recipe, catalogue)
        export_root.mkdir(parents=True)
        artifacts = []
        rows = []
        for row in planned.document["textures"]:
            target = catalogue.target(row["texture"])
            png = self.decode_png(source, target)
            path = export_root / str(row["file_name"])
            with open(path, "xb") as handle:  # exclusive: never overwrites
                handle.write(png)
            digest = _sha256(png)
            artifacts.append(Artifact(str(path), digest, "png"))
            rows.append({**row, "sha256": digest, "bytes": len(png)})
        readme = export_root / "HOW-TO.txt"
        readme.write_text(self._how_to(len(rows)), encoding="utf-8", newline="\n")
        artifacts.append(Artifact(str(readme), _sha256(readme.read_bytes()), "text"))
        document = {
            "schema": self.write_schema,
            "source": str(source),
            "destination": str(destination),
            "export_folder": export_root.as_posix(),
            "textures": rows,
            "identity_note": self.NO_IDENTITY,
            "note": "Exported PNGs. Your disc image was opened read-only and is unchanged.",
        }
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with open(destination, "xb") as handle:
            handle.write(payload)
        document["manifest_sha256"] = _sha256(payload)
        artifacts.insert(0, Artifact(str(destination), _sha256(payload), "export-manifest"))
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), (),
                       document, artifacts=tuple(artifacts))

    def _how_to(self, count: int) -> str:
        return (
            f"{self.game_title} — exported textures\n"
            "================================================\n"
            "\n"
            f"{count} PNG file(s), decoded from your own disc image. Your image was opened\n"
            "read-only and is unchanged.\n"
            "\n"
            "What you can do with these today: look at them, edit them, keep them.\n"
            "\n"
            "What you cannot do yet, and why:\n"
            "\n"
            "  * Put them back on the disc. Replacing a texture means rebuilding the\n"
            f"    container it lives in, and no rebuilt {self.game_title} container has ever been\n"
            "    booted in an emulator to prove the game still loads it. On top of that,\n"
            "    the compression EA used has no public encoder, so an edited texture\n"
            "    cannot be packed back to the size of the one it replaces.\n"
            "\n"
            "  * Load them in PCSX2 as a replacement pack. PCSX2 finds a replacement by a\n"
            "    name built from hashes it computes while the game draws. The studio now\n"
            "    derives those names from the disc (and a texture dump confirms them), but\n"
            "    no pack built from them has been loaded by an emulator yet, so the pack\n"
            "    step is not offered until one has.\n"
            "\n"
            "If you edit one and want to know whether it still fits, import it on the\n"
            "Uniforms page: the studio checks it against the texture's own palette and\n"
            "tells you how it landed.\n"
        )

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Re-derive every exported file from the user's disc, independently."""

        destination = Path(destination)
        if not destination.is_file():
            return Verdict(False, f"Verification failed: the manifest {destination} is missing.")
        export_root = Path(str(receipt.document.get("export_folder") or "")
                           or self.export_root_for(destination))
        if not export_root.is_dir():
            return Verdict(False,
                           f"Verification failed: the export folder {export_root} is missing.")
        declared = {Path(artifact.path): artifact for artifact in receipt.artifacts}
        on_disk = {path for path in export_root.rglob("*") if path.is_file()}
        on_disk.add(destination)
        extra = sorted(str(path) for path in on_disk - set(declared))
        missing = sorted(str(path) for path in set(declared) - on_disk)
        if extra or missing:
            return Verdict(False, "Verification failed: the export folder holds "
                           + (f"undeclared file(s) {extra}" if extra else "")
                           + (" and " if extra and missing else "")
                           + (f"no {missing}" if missing else "") + ".")
        for path, artifact in declared.items():
            if _sha256(path.read_bytes()) != artifact.sha256:
                return Verdict(False, f"Verification failed: {path.name} on disk is not the "
                                      f"file the receipt recorded.")
        rows = receipt.document.get("textures", [])
        if not rows:
            return Verdict(False, "Verification failed: the receipt declares no textures.")
        checked = 0
        for row in rows:
            # Addressed by key straight off the source, not through the
            # catalogue that produced the receipt: a check that trusts the
            # thing it is checking is not an independent one.
            try:
                expected = _sha256(self.decode_png_by_key(Path(source), str(row["texture"])))
            except Refusal as exc:
                return Verdict(False, f"Verification failed: {exc}")
            if expected != row.get("sha256"):
                return Verdict(False, f"Verification failed: {row['texture']} decodes from this "
                                      f"disc to a different image than the receipt recorded.")
            checked += 1
        return Verdict(True,
                       f"{checked} texture(s) re-decoded from the source and matched byte for "
                       f"byte; {len(declared)} declared file(s) present and nothing else.",
                       {"result": "PASS", "textures": checked, "files": len(declared)})

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.capability_id or 'terf'}-art-synthetic.iso"
        path.write_bytes(self.discs.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        return (Edit(catalogue.targets[0].key, {},
                     note="conformance: export this texture as it is"),)


# ==========================================================================
# The disc writer
# ==========================================================================



def _iso_writer():
    """``tools/ps2_iso9660_writer``, imported late.

    A game package may import Qt, the core and its tools only inside a
    function; ``containers`` has already put ``tools/`` on the path.
    """

    import ps2_iso9660_writer

    return ps2_iso9660_writer


def _iso_verifier():
    import ps2_iso9660_verify

    return ps2_iso9660_verify


class TerfArtWriteLane(TerfArtLane):
    """Edited PNGs, back into the ``MMAP`` members of a NEW disc image.

    The export lane above catalogues and decodes; this one is the other
    direction, and it is a separate row because it earns a different rung.  It
    shares the catalogue, the decoder and the PNG reader -- pointing two lanes
    at one decode is the whole reason the decoder is its own module -- and
    replaces the three steps that write.

    **What it does, in the order it does it.**

    1. Each edited PNG is indexed against the texture's own CLUT, keeping the
       index the file already used wherever a pixel is unchanged, and the
       member is laid out again by :func:`mmap_art.encode`.
    2. The member goes back into its ``TERF`` container through
       :func:`ea_terf.rewrite_member`.  :func:`ea_terf.plan_member_rewrite`
       chooses the codec first -- ``LZH1`` when it is smaller, stored when it
       is not -- and the receipt names which, because a member that no longer
       fits its aligned slot is the thing that decides whether the image can
       stay the length it was.
    3. The rebuilt container replaces the one on the disc through
       ``tools/ps2_iso9660_writer``, **inside its existing extent whenever it
       fits**.  Only when it does not is ``allow_growth`` used, and then the
       receipt says the image grew and by how many sectors.

    **What it does not claim.**  ``offline-writer-proved`` is the whole of it:
    every step is proved against the user's own bytes by a verifier that
    rebuilds the answer from the two images, and **no rebuilt container of
    either game has ever been booted**.  Nothing here says the game loads the
    result; the receipt says so too.
    """

    lane_id = ""
    capability_id = ""
    surface = "uniforms"
    page = "uniforms"
    title = "Write uniform, face and tattoo textures back to a new disc image"
    classification = "offline-writer-proved"
    recipe_schema = ""
    write_schema = ""
    validators: Tuple[str, ...] = ()
    #: The image keeps its length whenever the rebuilt container fits its
    #: extent, which is the ordinary case -- our ``LZH1`` streams come out at
    #: about EA's size.  It is not guaranteed, so the honest answer is False
    #: and the receipt carries the number.
    fixed_allocation = False

    NOT_BOOTED = (
        "No rebuilt container of this game has been booted. Every step here is proved against "
        "your own bytes offline -- the member decodes back to the pixels you gave it, the "
        "container follows the layout rules the retail discs follow, and every byte outside "
        "the declared ranges is unchanged -- but whether the game loads the result is not "
        "something this tool can find out."
    )

    # -- targets -------------------------------------------------------

    @staticmethod
    def _target(row: Mapping[str, Any], structure: str) -> Target:
        detail = [f"{row['width']}x{row['height']}", row["layout"]]
        if row["mips"] > 1:
            detail.append(f"{row['mips']} mip levels")
        if row["palettes"] > 1:
            detail.append(f"{row['palettes']} palettes")
        if row["name"]:
            detail.append(row["name"])
        return Target(
            key=_key(row["container"], row["member"], row["image"]),
            label=f"{row['group']} · member {row['member']} · image {row['image']}"
                  + (f" ({row['name']})" if row["name"] else ""),
            detail=" · ".join(detail),
            budget=(f"Writes this texture into a NEW copy of your image. The member is "
                    f"re-packed and the receipt names the codec it chose; your own image is "
                    f"opened read-only."),
            searchable=f"{row['container']} {row['group']} {row['member']} {row['name']}",
            raw=dict(row, structure=structure),
            fields=(
                Field("png", "png", "Replacement PNG",
                      f"A {row['width']}x{row['height']} 8-bit non-interlaced PNG. It is "
                      f"indexed against this texture's own palette -- a colour that palette "
                      f"does not carry cannot be introduced -- and the receipt says how many "
                      f"pixels landed exactly."),
                Field("group", "note", "Group", "Which container this texture came from.",
                      read_only=True),
                Field("dimensions", "note", "Size", "Width by height of the largest mip level.",
                      read_only=True),
                Field("layout", "note", "Pixel layout",
                      "How the disc stores this texture's pixels.", read_only=True),
                Field("structure", "note", "What the file says",
                      "How this container organises its textures, and what it does not say.",
                      read_only=True),
            ),
        )

    # -- recipe --------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        problem = super().check_edit(target, values)
        if problem is not None:
            return problem
        if not values.get("png"):
            return (f"{target.key}: this lane writes a texture, so it needs a PNG. Export the "
                    f"texture, edit it, and give the file back here.")
        width = int(target.raw.get("width") or 0)
        height = int(target.raw.get("height") or 0)
        try:
            got_width, got_height, _rgba = read_rgba_png(Path(str(values["png"])).read_bytes())
        except (OSError, Refusal) as exc:
            return f"{target.key}: {exc}"
        if (got_width, got_height) != (width, height):
            return (f"{target.key}: that PNG is {got_width}x{got_height} and this texture is "
                    f"{width}x{height}. A texture is written at its own size; a whole-number "
                    f"multiple can be exported and looked at but not written back.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            path = edit.values.get("png")
            require(bool(path),
                    f"{edit.target_key}: this lane writes a texture and no PNG was given.")
            row: Dict[str, Any] = {"texture": edit.target_key, "png": str(path)}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "textures": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {self.recipe_schema}")
        rows = recipe.get("textures")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'textures' list; choose at least one texture "
                "to write")
        seen: set = set()
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("texture"), str)
                    and row["texture"],
                    f"texture {number} must name the texture it writes")
            require(set(row) <= {"texture", "png", "note"},
                    f"texture {number} carries unknown keys")
            require(isinstance(row.get("png"), str) and row["png"],
                    f"{row.get('texture')}: this lane writes a texture and no PNG was given.")
            require(row["texture"] not in seen,
                    f"{row['texture']} appears twice; one texture is written once")
            seen.add(row["texture"])
            out.append(dict(row))
        return out

    # -- the composition both plan and build run -----------------------

    def _compose(self, source: Path, recipe: Mapping[str, Any],
                 catalogue: Optional[Catalogue]) -> Dict[str, Any]:
        """Rebuild every container an edit touches, and price the result.

        Done in full by ``plan`` as well as by ``build``: a dry run that does
        not encode cannot say whether the member still fits, and "it probably
        fits" is not a plan.
        """

        entries = self._entries(recipe)
        disc = self.discs.open_disc(Path(source))
        present = {entry.name: entry for entry in self.discs.data_files(disc)}
        by_member: Dict[Tuple[str, int], Dict[int, Dict[str, Any]]] = {}
        order: List[str] = []
        for entry in entries:
            if catalogue is not None:
                catalogue.target(entry["texture"])       # the catalogue's own refusal
            container_name, member, image_index = self.parse_key(entry["texture"])
            require(any(container_name == name
                        for name, _group, _note in self.art_containers),
                    f"{entry['texture']}: {container_name} is not one of the art containers "
                    f"this lane writes "
                    f"({', '.join(name for name, _g, _n in self.art_containers)}).")
            require(container_name in present,
                    f"{entry['texture']}: {container_name} is not on this image.")
            slot = by_member.setdefault((container_name, member), {})
            require(image_index not in slot,
                    f"{entry['texture']} appears twice; one texture is written once")
            slot[image_index] = entry
            if container_name not in order:
                order.append(container_name)

        rebuilt: Dict[str, bytes] = {}
        rows: List[Dict[str, Any]] = []
        member_notes: List[Dict[str, Any]] = []
        preload = self.discs.preload_copies(disc)
        caches: Dict[str, bytearray] = {}
        cache_notes: List[Dict[str, Any]] = []
        for container_name in order:
            data_file = present[container_name]
            writable = self.discs.open_for_rewrite(disc, data_file)
            blob = writable.data
            original = blob
            short_tail = writable.recorded_short
            container = writable.parsed
            for (name, member), images in sorted(by_member.items()):
                if name != container_name:
                    continue
                writable.require_member_inside(member)
                payload = container.member(member)
                require(payload.startswith(mmap_art.MMAP_MAGIC),
                        f"{name} member {member} is not an MMAP texture, so there is nothing "
                        f"to write into it.")
                texture = mmap_art.parse(payload)
                levels: Dict[Tuple[int, int], bytes] = {}
                for image_index, entry in sorted(images.items()):
                    image = texture.image(image_index)
                    reason = texture.undecodable_reason(image)
                    require(reason is None,
                            f"{entry['texture']} cannot be written: it is {reason}.")
                    surface = texture.surfaces[image.first_surface]
                    png = Path(entry["png"]).read_bytes()
                    width, height, rgba = read_rgba_png(png)
                    require((width, height) == (surface.width, surface.height),
                            f"{entry['texture']}: that PNG is {width}x{height} and this "
                            f"texture is {surface.width}x{surface.height}. A texture is "
                            f"written at its own size.")
                    levels[(image_index, 0)] = rgba
                    palette = mmap_art.read_palette(payload, texture.palettes[
                        image.first_palette])
                    _indices, exact = mmap_art.index_rgba(
                        rgba, width, height, palette,
                        original=mmap_art.unpack_indices(
                            mmap_art.surface_pixels(payload, surface), surface))
                    rows.append({
                        "texture": entry["texture"],
                        "container": name,
                        "member": member,
                        "image": image_index,
                        "width": width,
                        "height": height,
                        "png": entry["png"],
                        "png_sha256": _sha256(png),
                        "palette_entries": len(palette),
                        "exact_pixels": exact,
                        "total_pixels": width * height,
                        "max_channel_error": self._max_error(rgba, palette),
                        **({"note": entry["note"]} if entry.get("note") else {}),
                    })
                new_member = mmap_art.encode(payload, levels=levels, texture=texture)
                # A plain ``DATA`` container carries no ``COMP`` codec table, so a
                # member packed under LZH1 would be handed back to the game still
                # packed.  ``PLYRFACE``, ``TATTOOS`` and every ``UIS_*`` container
                # are that shape [M]; offering LZH1 there is a refusal waiting to
                # happen, so the codec list is narrowed to what the container can
                # record rather than chosen and then rejected.
                plan = ea_terf.plan_member_rewrite(
                    blob, member, new_member,
                    codecs=((ea_terf.CODEC_STORED,) if container.chunk("COMP") is None
                            else (ea_terf.CODEC_STORED, ea_terf.CODEC_LZH1)),
                    allow_short_tail=short_tail)
                blob = ea_terf.rewrite_member(blob, member, new_member, codec=plan.codec,
                                              allow_short_tail=short_tail)
                container = ea_terf.parse_terf(blob, allow_size_mismatch=True)
                member_notes.append({
                    "container": name, "member": member,
                    "images": sorted(images), **plan.as_dict()})
            violations = container.layout_violations(allow_short_tail=short_tail)
            if violations:
                raise Refusal(
                    f"the rebuilt {container_name} broke the container's own layout rules "
                    f"({violations[0]}); nothing was written.")
            rebuilt[container_name] = blob
            self._patch_preload(disc, present, preload, caches, cache_notes,
                                container_name, original, blob,
                                sorted(member for name, member in by_member if
                                       name == container_name))
            existing = int(data_file.recorded_length)
            rows_for = [row for row in rows if row["container"] == container_name]
            member_notes.append({
                "container": container_name, "member": None,
                "note": (f"{len(rows_for)} texture(s) rewritten; the container is "
                         f"{len(blob):,} bytes against the {existing:,} its directory record "
                         f"declares."),
                "container_bytes": len(blob),
                "recorded_bytes": existing,
                "grows_the_image": len(blob) > existing,
            })
        written = dict(rebuilt)
        written.update({name: bytes(blob) for name, blob in caches.items()})
        grows = [name for name, blob in written.items()
                 if len(blob) > int(present[name].recorded_length)]
        return {
            "containers": rebuilt,
            "caches": {name: bytes(blob) for name, blob in caches.items()},
            "cache_copies": cache_notes,
            "textures": rows,
            "members": member_notes,
            "grows": grows,
            "written": written,
            "paths": {name: present[name].path for name in written},
        }

    def _patch_preload(self, disc: Any, present: Mapping[str, Any],
                       preload: Mapping[str, Any], caches: Dict[str, bytearray],
                       notes: List[Dict[str, Any]], container_name: str,
                       before: bytes, after: bytes, touched: Sequence[int]) -> None:
        """Keep the preload caches' copies of this container in step with it.

        The rule itself is
        :func:`mod_editor.games._lanes.preload_coherence.patch_caches`, shared
        with every other lane on this stack that rewrites a container: a cache
        carries byte copies of container directories and of individual members
        and the game preloads from those, so a member rewrite is free only
        while the directory holds, and a member that is itself carried has to
        be rewritten in the cache or refused.
        """

        preload_coherence.patch_caches(
            self.discs, disc, present, preload, caches, notes, container_name,
            before, after, touched, allow_shorter=self.cached_member_may_shrink)

    @staticmethod
    def _max_error(rgba: bytes, entries: Sequence[Tuple[int, int, int, int]]) -> int:
        """The worst channel a pixel can move by, riding this CLUT.

        Reported rather than refused: an MMAP texture carries its own
        palette, so a colour it does not hold has to land on the nearest one it
        does, and a number is more use than a warning.
        """

        drawn = [(red, green, blue, mmap_art._scale_alpha(alpha))
                 for red, green, blue, alpha in entries]
        cache: Dict[Tuple[int, int, int, int], int] = {}
        worst = 0
        for position in range(0, len(rgba), 4):
            pixel = (rgba[position], rgba[position + 1], rgba[position + 2],
                     rgba[position + 3])
            found = cache.get(pixel)
            if found is None:
                best = min(drawn, key=lambda entry: sum(
                    (entry[channel] - pixel[channel]) ** 2 for channel in range(4)))
                found = cache[pixel] = max(abs(best[channel] - pixel[channel])
                                           for channel in range(4))
            if found > worst:
                worst = found
        return worst

    # -- plan / build / verify -----------------------------------------

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        composed = self._compose(Path(source), recipe, catalogue)
        writer = iso_tools.iso_writer()
        replacements = {composed["paths"][name]: blob
                        for name, blob in composed["written"].items()}
        report = writer.plan_report(Path(source), replacements,
                                    allow_growth=bool(composed["grows"]))
        ranges = tuple(DeclaredRange(item.start, item.length, item.reason)
                       for item in report["declared_ranges"])
        return Plan(self.lane_id, tuple(row["texture"] for row in composed["textures"]),
                    ranges, {
                        "schema": self.recipe_schema,
                        "textures": [{k: v for k, v in row.items() if k != "png_sha256"}
                                     for row in composed["textures"]],
                        "members": composed["members"],
                        "preload_copies": composed["cache_copies"],
                        "grows_the_image": bool(composed["grows"]),
                        "growth": report.get("growth"),
                        "declared_bytes": sum(item.length for item in ranges),
                        "identity_note": self.NO_IDENTITY,
                        "runtime_note": self.NOT_BOOTED,
                    })

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        import os

        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build always writes a NEW image.")
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite")
        composed = self._compose(source, recipe, catalogue)
        writer = iso_tools.iso_writer()
        replacements = {composed["paths"][name]: blob
                        for name, blob in composed["written"].items()}
        report = writer.replace_files(source, destination, replacements,
                                      allow_growth=bool(composed["grows"]))
        json_report = writer.report_to_json(report)
        ranges = tuple(DeclaredRange(item["start"], item["length"], item["reason"])
                       for item in json_report["declared_ranges"])
        document = {
            "schema": self.write_schema,
            "source": str(source),
            "destination": str(destination),
            "textures": composed["textures"],
            "members": composed["members"],
            "preload_copies": composed["cache_copies"],
            "containers": [
                {"name": name, "path": composed["paths"][name], "bytes": len(blob),
                 "sha256": _sha256(blob),
                 "kind": "preload-cache" if name in composed["caches"] else "container"}
                for name, blob in sorted(composed["written"].items())
            ],
            "grew_the_image": bool(json_report.get("growth")),
            "iso_report": json_report,
            "identity_note": self.NO_IDENTITY,
            "runtime_note": self.NOT_BOOTED,
        }
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination),
                       ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Rebuild the answer from the two images; import nothing that wrote them.

        Three separate things are checked and none of them trusts the build:
        the image-level edit through ``tools/ps2_iso9660_verify`` (its own
        ISO9660 decoder, not the reader's), the container-level edit by
        comparing every member of the two containers, and the texture itself by
        decoding it out of the destination and measuring it against the PNG the
        user handed in.
        """

        source, destination = Path(source), Path(destination)
        document = receipt.document
        try:
            report = document["iso_report"]
        except (TypeError, KeyError):
            return Verdict(False, "Verification failed: the receipt carries no write report.")
        try:
            outcome = iso_tools.iso_verifier().verify_replacement(source, destination, report)
        except Exception as exc:                            # noqa: BLE001
            return Verdict(False, f"Verification failed at the image level: {exc}")
        if outcome.get("result") != "PASS":
            return Verdict(False, f"Verification failed at the image level: {outcome}")

        edited: Dict[str, List[Mapping[str, Any]]] = {}
        for row in document.get("textures", ()):
            edited.setdefault(str(row["container"]), []).append(row)
        if not edited:
            return Verdict(False, "Verification failed: the receipt declares no textures.")

        before_disc = self.discs.open_disc(source)
        after_disc = self.discs.open_disc(destination)
        before_files = {entry.name: entry for entry in self.discs.data_files(before_disc)}
        after_files = {entry.name: entry for entry in self.discs.data_files(after_disc)}
        members_checked = 0
        textures_checked = 0
        copies_checked = 0
        for container_name, rows in sorted(edited.items()):
            if container_name not in after_files:
                return Verdict(False, f"Verification failed: {container_name} is not on the "
                                      f"destination image.")
            before = ea_terf.parse_terf(
                self.discs.read_file(before_disc, before_files[container_name]),
                allow_size_mismatch=True)
            after_blob = self.discs.read_file(after_disc, after_files[container_name])
            after = ea_terf.parse_terf(after_blob, allow_size_mismatch=True)
            violations = after.layout_violations()
            if violations:
                return Verdict(False, f"Verification failed: the rebuilt {container_name} "
                                      f"breaks the container's layout rules ({violations[0]}).")
            if after.member_count != before.member_count:
                return Verdict(False, f"Verification failed: {container_name} went from "
                                      f"{before.member_count} member(s) to "
                                      f"{after.member_count}.")
            touched = {int(row["member"]) for row in rows}
            for index in range(before.member_count):
                if index in touched:
                    continue
                if before.stored(index) != after.stored(index):
                    return Verdict(False, f"Verification failed: {container_name} member "
                                          f"{index} changed and no edit named it.")
                members_checked += 1
            for row in rows:
                # Every image of this member that the same receipt names is
                # exempt from the "nothing else changed" rule, as a set: five
                # edits to one member are five changes, not one change and
                # four intrusions.
                siblings = frozenset(int(other["image"]) for other in rows
                                     if int(other["member"]) == int(row["member"]))
                verdict = self._check_one_texture(before, after, row, named_images=siblings)
                if verdict is not None:
                    return verdict
                textures_checked += 1
            verdict, checked = self._check_preload(after_disc, after_files, after_blob,
                                                   container_name)
            if verdict is not None:
                return verdict
            copies_checked += checked
        return Verdict(
            True,
            f"{textures_checked} texture(s) decode from the NEW image as the PNG(s) you gave, "
            f"{members_checked} untouched member(s) are byte-identical, {copies_checked} "
            f"preload-cache copy/copies still equal what they copy, every container follows "
            f"its layout rules, and the image-level verifier re-derived every declared byte. "
            f"{self.NOT_BOOTED}",
            {"result": "PASS", "textures": textures_checked,
             "untouched_members": members_checked, "preload_copies": copies_checked,
             "image": outcome, "runtime_note": self.NOT_BOOTED},
        )

    def _check_preload(self, disc: Any, files: Mapping[str, Any], blob: bytes,
                       container_name: str) -> Tuple[Optional[Verdict], int]:
        """Every cached copy of this container still equals the container.

        Derived from the destination image alone -- the caches are re-parsed
        there and compared against the container as it now stands -- so a
        receipt that forgot a copy fails here rather than being believed.
        """

        sentence, checked = preload_coherence.check_caches(
            self.discs, disc, files, blob, container_name)
        if sentence is not None:
            return Verdict(False, f"Verification failed: {sentence}"), checked
        return None, checked

    @staticmethod
    def _check_one_texture(before: "ea_terf.TerfContainer", after: "ea_terf.TerfContainer",
                           row: Mapping[str, Any], *,
                           named_images: Optional[frozenset] = None) -> Optional[Verdict]:
        """One rewritten texture, measured against the PNG rather than the build.

        *named_images* is every image of this member the receipt names; each of
        them is allowed to differ from the source, and every other image of the
        member must be byte-for-byte the picture it was.  Without it only the
        row's own image is exempt, which is the single-edit case.
        """

        member = int(row["member"])
        image_index = int(row["image"])
        key = str(row["texture"])
        exempt = set(named_images or ()) | {image_index}
        try:
            png = Path(str(row["png"])).read_bytes()
        except OSError as exc:
            return Verdict(False, f"Verification failed: {key}'s PNG {row['png']} could not "
                                  f"be read back ({exc}).")
        if _sha256(png) != row.get("png_sha256"):
            return Verdict(False, f"Verification failed: {key}'s PNG is not the file the "
                                  f"receipt recorded.")
        wanted_width, wanted_height, wanted = read_rgba_png(png)
        payload = after.member(member)
        texture = mmap_art.parse(payload)
        width, height, drawn = mmap_art.decode_rgba(payload, image=image_index,
                                                    texture=texture)
        if (width, height) != (wanted_width, wanted_height):
            return Verdict(False, f"Verification failed: {key} is {width}x{height} on the new "
                                  f"image and the PNG is {wanted_width}x{wanted_height}.")
        entry = texture.image(image_index)
        clut = {(red, green, blue, mmap_art._scale_alpha(alpha)) for red, green, blue, alpha
                in mmap_art.read_palette(payload, texture.palettes[entry.first_palette])}
        exact = 0
        worst = 0
        for position in range(0, len(drawn), 4):
            pixel = (drawn[position], drawn[position + 1], drawn[position + 2],
                     drawn[position + 3])
            if pixel not in clut:
                return Verdict(False, f"Verification failed: {key} draws a colour at pixel "
                                      f"{position // 4} that is not in its own palette.")
            target = (wanted[position], wanted[position + 1], wanted[position + 2],
                      wanted[position + 3])
            if pixel == target:
                exact += 1
                continue
            worst = max(worst, max(abs(pixel[channel] - target[channel])
                                   for channel in range(4)))
        if exact != int(row.get("exact_pixels", -1)):
            return Verdict(False, f"Verification failed: {key} matches its PNG at {exact:,} "
                                  f"pixel(s) and the receipt claims "
                                  f"{row.get('exact_pixels')}.")
        if worst > int(row.get("max_channel_error", 0)):
            return Verdict(False, f"Verification failed: {key} moves a channel by {worst} and "
                                  f"the receipt claims at most "
                                  f"{row.get('max_channel_error')}.")
        # Every image in the same member that no edit named must be untouched.
        source_payload = before.member(member)
        source_texture = mmap_art.parse(source_payload)
        for other in source_texture.images:
            if other.index in exempt or source_texture.undecodable_reason(other):
                continue
            if (mmap_art.decode_rgba(source_payload, image=other.index,
                                     texture=source_texture)
                    != mmap_art.decode_rgba(payload, image=other.index, texture=texture)):
                return Verdict(False, f"Verification failed: image {other.index} of "
                                      f"{row['container']} member {member} changed and no edit "
                                      f"named it.")
        return None

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        """The synthetic disc, and beside it the PNG the conformance edit uses.

        A writer's conformance edit has to name a file, and ``synthetic_source``
        is the only hook the harness hands a working directory -- so the PNG is
        written here, from the synthetic disc's own first texture, flipped top
        to bottom.  Every pixel of a flip is a colour the texture's palette
        already holds, so the edit is exactly representable and the check that
        it landed is about the write rather than about quantisation.
        """

        work_dir = Path(work_dir)
        path = work_dir / f"{self.capability_id or 'terf'}-disc-art-synthetic.iso"
        path.write_bytes(self.discs.build_synthetic_disc())
        catalogue = self.build_catalogue(path)
        target = catalogue.targets[0]
        width, height, rgba = read_rgba_png(self.decode_png(path, target))
        stride = width * 4
        flipped = b"".join(rgba[row * stride:(row + 1) * stride]
                           for row in range(height - 1, -1, -1))
        self._conformance_png = work_dir / "conformance-edit.png"
        self._conformance_png.write_bytes(write_rgba_png(flipped, width, height))
        self._conformance_target = target.key
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple:
        png = getattr(self, "_conformance_png", None)
        require(png is not None and Path(png).is_file(),
                "conformance_edits needs the PNG synthetic_source writes; call "
                "synthetic_source first.")
        key = getattr(self, "_conformance_target", catalogue.targets[0].key)
        return (Edit(key, {"png": str(png)},
                     note="conformance: write this texture back, flipped"),)


__all__ = [
    "CATALOGUE_COST_NOTE",
    "IDENTITY_CONVENTIONS",
    "IDENTITY_SCHEMA",
    "MAX_TARGETS",
    "PNG_SIGNATURE",
    "TerfArtLane",
    "TerfArtWriteLane",
    "derive_texture_names",
    "load_identities",
    "read_rgba_png",
    "write_rgba_png",
]
