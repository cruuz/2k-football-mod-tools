"""The disc's ``MMAP`` textures, decoded to PNG. Export is the whole value today.

Madden 09's uniforms, player and coach faces, tattoos and field art are
``MMAP`` textures inside ``TERF`` containers.  `mmap_art` reads the pixels;
this file is the lane: it catalogues every texture on the user's own disc,
decodes one to PNG on demand, checks a PNG the user offers back, and exports a
chosen set as a folder of PNGs with a receipt an independent verifier
re-derives.

**Extract-only, and that is the honest classification.**  Nothing here writes
to a disc image. Two separate things stand in the way and both are named on
the page rather than worked around:

* **There is no PCSX2 replacement identity.**  Naming a texture so PCSX2's
  texture replacement picks it up needs the GS ``TEX0`` and CLUT hashes the
  emulator computes at draw time, and those come from a **GS dump of Madden 09
  running**.  No such dump exists.  :meth:`UniformArtLane.replacement_identity`
  therefore returns ``None`` and the *Write PCSX2 pack* step refuses with that
  sentence, rather than inventing a filename that would silently never match.
* **Writing back into the container is not proved.**  A replaced member would
  have to be stored uncompressed (no ``LZH1`` encoder exists publicly) and no
  rebuilt Madden 09 container has ever been booted.

What *is* proved is the decode. See :mod:`.mmap_art` for the layout and the
evidence: 10,545 of 10,546 images across eight containers of the retail disc
decode cleanly, and the results are recognisable jersey sheets and human
faces rather than plausible-looking noise.

Run it without a window::

    python3 -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso
    python3 -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso \\
        --export OUT_DIR --limit 24

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

from . import containers, mmap_art

CAPABILITY_ID = "madden09ps2.uniforms.mmap_export"
LANE_ID = "uniforms.mmap_export"
CATALOG_SCHEMA = "madden09_ps2_uniform_art_catalog/v1"
RECIPE_SCHEMA = "madden09_ps2_uniform_art_recipe/v1"
WRITE_SCHEMA = "madden09_ps2_uniform_art_export/v1"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: The art containers, and what the disc itself says about how they are
#: organised.  Only the first column is a fact about *this* module; the rest is
#: what the containers reveal, with an honest label on each.
#:
#: ``group`` is what a page can sort by today.  ``UNIFORMS.DAT`` names nothing
#: -- every one of its 455 members carries 15 unnamed images -- so the member
#: index is the only structure it offers, and which team a member belongs to is
#: **not established here** [A].  ``PLYRFACE`` and ``COACFACE`` name their one
#: image ``FACE`` and ``TATTOOS`` names its own, so those groups are read from
#: the file [M].
ART_CONTAINERS: Tuple[Tuple[str, str, str], ...] = (
    (containers.UNIFORM_CONTAINER, "Uniforms",
     "455 members, each carrying about fifteen unnamed images: jersey, trouser and "
     "kit sheets. The file names none of them, so the member index is the only "
     "structure it offers and which team a member belongs to is not established here."),
    (containers.PLAYER_FACE_CONTAINER, "Player faces",
     "532 members, one image each, named FACE by the file. The member index is a "
     "player face id; which player it belongs to is not established here."),
    (containers.COACH_FACE_CONTAINER, "Coach faces",
     "711 members, one image each. Same shape as the player faces."),
    (containers.TATTOO_CONTAINER, "Tattoos",
     "82 members, one image each, named by the file."),
)

#: How many textures the catalogue lists.  The retail disc offers more than ten
#: thousand; a table is a table.
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


def _key(container: str, member: int, image: int) -> str:
    return f"{container}:{member}:{image}"


def _file_name(container: str, member: int, image: int, width: int, height: int) -> str:
    stem = container.split(".")[0].lower()
    return f"{stem}-m{member:04d}-i{image:02d}-{width}x{height}.png"


class UniformArtLane:
    """Every ``MMAP`` texture on the disc: preview, export, and a checked import."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "uniforms"
    page = "uniforms"
    title = "Uniform, face and tattoo textures"
    classification = "extract-only"
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_madden09_ps2_uniform_art.sh",
        "tools/validate_madden09_ps2_uniform_art.bat",
    )
    #: The lane publishes files rather than rewriting the source, so it
    #: declares artifacts instead of byte ranges.
    fixed_allocation = False

    NO_IDENTITY = (
        "This lane cannot name a PCSX2 replacement file for a Madden 09 texture yet: the name "
        "PCSX2 looks for is built from the GS TEX0 and CLUT hashes it computes while the game "
        "draws, and getting those needs a GS dump of Madden 09 running, which nobody has "
        "captured. Export the PNG instead; a pack cannot be written until that dump exists."
    )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue:
        image = containers.open_disc(Path(source))
        present = {entry.name: entry for entry in containers.data_files(image)}
        rows: List[Dict[str, Any]] = []
        targets: List[Target] = []
        totals = {"members": 0, "images": 0, "decodable": 0}
        skipped: Dict[str, str] = {}
        refusals: Dict[str, int] = {}

        for name, group, note in ART_CONTAINERS:
            entry = present.get(name)
            if entry is None:
                skipped[name] = "not on this image"
                continue
            if progress is not None:
                progress(f"{name}…")
            _report, container = containers.describe_container(image, entry, with_formats=False)
            if container is None:
                skipped[name] = "could not be opened as a TERF container"
                continue
            for index in range(len(container)):
                try:
                    payload = containers.member_uncached(container, index)
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
                    rows.append(row)
                    if len(targets) < MAX_TARGETS:
                        targets.append(self._target(row, note))
        document = {
            "schema": CATALOG_SCHEMA,
            "source": str(source),
            "containers": [
                {"name": name, "group": group, "structure": note}
                for name, group, note in ART_CONTAINERS
            ],
            "members_read": totals["members"],
            "images_seen": totals["images"],
            "images_decodable": totals["decodable"],
            "rows_listed": len(rows),
            "targets_listed": len(targets),
            "targets_cap": MAX_TARGETS,
            "skipped": skipped,
            "not_decodable": refusals,
            "rows": rows,
            "note": "Dimensions, formats and counts only. A texture's pixels are decoded when "
                    "you ask to see or export one, and are never stored in this catalogue.",
        }
        return Catalogue(CATALOG_SCHEMA, self.lane_id, str(source), tuple(targets), document)

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
        disc = containers.open_disc(Path(source))
        container = containers.load_container(disc, container_name)
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
                  f"them yet -- no Madden 09 container has been rebuilt and booted."),
        )

    @staticmethod
    def _exact_matches(rgba: bytes, entries: Sequence[Tuple[int, int, int, int]]) -> int:
        palette = {(red, green, blue, mmap_art._scale_alpha(alpha))
                   for red, green, blue, alpha in entries}
        return sum(1 for position in range(0, len(rgba), 4)
                   if tuple(rgba[position:position + 4]) in palette)

    def replacement_identity(self, target: Target) -> Optional[str]:
        """``None``: PCSX2 identities need a GS dump of this game, and none exists."""

        return None

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
        return {"schema": RECIPE_SCHEMA, "textures": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == RECIPE_SCHEMA,
                f"recipe schema is "
                f"{recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {RECIPE_SCHEMA}")
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
            })
        return Plan(self.lane_id, tuple(entry["texture"] for entry in entries), (), {
            "schema": RECIPE_SCHEMA,
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
            "schema": WRITE_SCHEMA,
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
        return Receipt(WRITE_SCHEMA, self.lane_id, str(source), str(destination), (),
                       document, artifacts=tuple(artifacts))

    def _how_to(self, count: int) -> str:
        return (
            "Madden NFL 09 (PlayStation 2) — exported textures\n"
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
            "    container it lives in, and no rebuilt Madden 09 container has ever been\n"
            "    booted in an emulator to prove the game still loads it. On top of that,\n"
            "    the compression EA used has no public encoder, so an edited texture\n"
            "    cannot be packed back to the size of the one it replaces.\n"
            "\n"
            "  * Load them in PCSX2 as a replacement pack. PCSX2 finds a replacement by a\n"
            "    name built from hashes it computes while the game draws, and nobody has\n"
            "    captured a GS dump of Madden 09 to read those hashes from. Until someone\n"
            "    does, any name this tool wrote would simply never match.\n"
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
        path = Path(work_dir) / "madden09-ps2-art-synthetic.iso"
        path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        return (Edit(catalogue.targets[0].key, {},
                     note="conformance: export this texture as it is"),)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m mod_editor.games.madden09_ps2.uniform_art --source DISC.iso``."""

    parser = argparse.ArgumentParser(
        prog="mod_editor.games.madden09_ps2.uniform_art",
        description="Catalogue and export a Madden NFL 09 (PS2) disc's MMAP textures.",
    )
    parser.add_argument("--source", required=True, help="the user's own SLUS-21770 disc image")
    parser.add_argument("--out", help="write the catalogue document to this JSON file")
    parser.add_argument("--export", metavar="MANIFEST.json",
                        help="write this NEW manifest and the PNGs in a folder beside it")
    parser.add_argument("--limit", type=int, default=12,
                        help="how many textures --export writes (default 12)")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = UniformArtLane()
    try:
        catalogue = lane.build_catalogue(
            Path(arguments.source), progress=lambda line: print(line, file=sys.stderr))
        if arguments.export:
            edits = tuple(Edit(target.key, {}) for target in
                          catalogue.targets[:max(1, arguments.limit)])
            recipe = lane.compose_recipe(edits)
            manifest = Path(arguments.export)
            receipt = lane.build(Path(arguments.source), manifest, recipe, catalogue)
            verdict = lane.verify(Path(arguments.source), manifest, receipt)
            print(f"EXPORT files={len(receipt.artifacts)} "
                  f"verify={'PASS' if verdict.passed else 'FAIL'} — {verdict.summary}")
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    print("UNIFORM_ART members=%d images=%d decodable=%d listed=%d not_decodable=%d"
          % (document["members_read"], document["images_seen"], document["images_decodable"],
             document["targets_listed"], sum(document["not_decodable"].values())))
    return 0


__all__ = ["ART_CONTAINERS", "CAPABILITY_ID", "CATALOGUE_COST_NOTE", "CATALOG_SCHEMA",
           "LANE_ID", "MAX_TARGETS",
           "PNG_SIGNATURE", "RECIPE_SCHEMA", "UniformArtLane", "WRITE_SCHEMA",
           "read_rgba_png", "write_rgba_png"]


if __name__ == "__main__":
    raise SystemExit(_main())
