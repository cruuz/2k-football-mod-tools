"""Synthetic ``MMAP`` textures, built from the format's own rules.

No game data may enter this repository, so every art lane's conformance run
works off a member built here.  Each piece is **computed, never sampled**: a
CLUT whose three channels use different strides, so a decode that swaps or
shifts palette entries produces obviously wrong colours instead of a subtle
shift, and an index ramp, so a wrong stride shows as a visible diagonal.  A
fixture whose failure mode is invisible proves nothing.

``MMAP`` is a table-of-tables -- an image table, a surface table (one row per
mip level), a palette table and a name table, each addressed by an offset in
the 40-byte header -- and :func:`synthetic_mmap` builds all of it, through
:mod:`mod_editor.games._formats.mmap_art`'s own constants rather than a
transcription of them.

This was Madden 09's, in its own ``containers`` module, until NCAA Football 09
needed the identical fixture: same ``MMAP`` format, same decoder, different
disc.  It is here so the two games prove their art lanes on the same bytes.
"""

from __future__ import annotations

import struct
from typing import List, Tuple

from mod_editor.games._formats import mmap_art


def synthetic_palette(entries: int = 256) -> List[Tuple[int, int, int, int]]:
    """A CLUT of *entries* colours, computed rather than sampled.

    Every channel is a different stride so a decode that swaps or shifts
    palette entries produces obviously wrong colours instead of a subtle
    shift.  Alpha is PS2's 0..128 scale.
    """

    return [((index * 5) & 0xFF, (index * 9) & 0xFF, (index * 17) & 0xFF,
             0x80 if index % 4 else 0x40)
            for index in range(entries)]


def synthetic_indices(width: int, height: int, *, seed: int = 0, bits: int = 8) -> bytes:
    """Index bytes for a *width* x *height* surface: a deterministic ramp.

    A wrong stride turns this into a visible diagonal, which is the point:
    a fixture whose failure mode is invisible proves nothing.
    """

    modulus = 256 if bits == 8 else 16
    values = [(seed + x * 7 + y * 13) % modulus
              for y in range(height) for x in range(width)]
    if bits == 8:
        return bytes(values)
    packed = bytearray(len(values) // 2)
    for position in range(0, len(values) - 1, 2):
        packed[position // 2] = values[position] | (values[position + 1] << 4)
    return bytes(packed)


def synthetic_mmap(width: int, height: int, *, version: int = 2, seed: int = 0,
                   bits: int = 8, mips: int = 1, palette_only_extra: bool = False,
                   retail_layout: bool = False, images: int = 1) -> bytes:
    """An ``MMAP`` member built from the format's own rules, not from a disc.

    ``MMAP`` is a table-of-tables -- an image table, a surface table (one row
    per mip level), a palette table and a name table, each addressed by an
    offset in the 40-byte header -- and this builds all of it.  See
    :mod:`.mmap_art` for the layout and the evidence behind it.

    *mips* adds halved levels after the base one, and *palette_only_extra*
    appends a further image entry the real containers carry: a row with no
    surfaces whose job is to hold an alternate CLUT for the first image.  Both
    exist so a lane's handling of them is exercised without a game.  *images*
    puts that many **drawable** images in the member, each with its own mip
    chain and its own palette -- the shape of a uniform member, which carries
    about fifteen -- so a writer that edits two images of one member can be
    proved on a fixture that has two.

    The default puts all four tables at the front, which is a **legal member
    the disc does not contain**: only the surface table's position is fixed,
    so a fixture in this shape proves the reader follows the header's offsets
    instead of assuming the disc's arrangement.  *retail_layout* runs the
    result through :func:`mmap_art.encode` with nothing replaced, which lays
    the same member out the way every measured member is laid out -- tables
    behind the pixels, 16-byte aligned -- and is what a writer's fixture wants.
    """

    import struct

    header_size = mmap_art.HEADER_SIZE
    drawable = max(1, images)
    #: Per drawable image: its levels as (width, height, pixels).  Each image
    #: seeds its texels differently so two images of one member are two
    #: pictures, not one twice.
    chains = []
    for number in range(drawable):
        levels = []
        level_width, level_height = width, height
        for level in range(max(1, mips)):
            levels.append((level_width, level_height,
                           synthetic_indices(level_width, level_height,
                                             seed=seed + level + 17 * number, bits=bits)))
            level_width = max(1, level_width // 2)
            level_height = max(1, level_height // 2)
        chains.append(levels)
    levels_total = sum(len(chain) for chain in chains)

    # A 256-entry CLUT is stored in the GS's CSM1 interleave, and undoing it is
    # an involution -- so storing the de-interleaved form makes the decoder
    # hand back exactly the palette this function names.
    wanted = synthetic_palette(256 if bits == 8 else 16)
    stored = mmap_art.deinterleave_csm1(wanted) if len(wanted) == 256 else list(wanted)
    clut = b"".join(bytes(entry) for entry in stored)

    image_count = drawable + (1 if palette_only_extra else 0)
    palette_count = drawable + (1 if palette_only_extra else 0)
    surface_offset = header_size
    image_offset = surface_offset + mmap_art.SURFACE_STRIDE * levels_total
    palette_offset = image_offset + mmap_art.IMAGE_STRIDE * image_count
    name_offset = palette_offset + mmap_art.PALETTE_STRIDE * palette_count
    data_offset = name_offset + mmap_art.NAME_STRIDE * image_count

    surfaces = bytearray()
    cursor = data_offset
    layout = (mmap_art.PIXELS_INDEXED_8 if bits == 8 else mmap_art.PIXELS_INDEXED_4)
    for chain in chains:
        for level_w, level_h, pixels in chain:
            surfaces += struct.pack("<HHIII", level_w, level_h, layout, len(pixels), cursor)
            cursor += len(pixels)
    palettes = bytearray()
    palette_cursor = cursor
    for _ in range(palette_count):
        palettes += struct.pack("<HHII", 0, mmap_art.PALETTE_RGBA8888,
                                len(clut), palette_cursor)
        palette_cursor += len(clut)

    images_table = bytearray()
    first_surface = 0
    for number, chain in enumerate(chains):
        images_table += struct.pack("<HHII", 1, len(chain), first_surface, number)
        first_surface += len(chain)
    if palette_only_extra:
        images_table += struct.pack("<HHII", 1, 0, 0, drawable)
    name_list = [b"SYNTH" + (str(number).encode("ascii") if number else b"")
                 for number in range(drawable)]
    if palette_only_extra:
        name_list.append(b"SYNTHALT")
    names = b"".join(name.ljust(mmap_art.NAME_STRIDE, b"\x00") for name in name_list)

    payload = bytearray()
    payload += mmap_art.MMAP_MAGIC
    payload += struct.pack("<I", version)
    payload += bytes((0x00, 0x01, 0x02, 0x03))
    payload += struct.pack("<HH", image_count, levels_total)
    payload += struct.pack("<IIIIII", palette_count, image_offset, surface_offset,
                           palette_offset, name_offset, 0)
    assert len(payload) == header_size, len(payload)
    payload += surfaces
    payload += images_table
    payload += palettes
    payload += names
    for chain in chains:
        for _level_w, _level_h, pixels in chain:
            payload += pixels
    payload += clut * palette_count
    if retail_layout:
        return mmap_art.encode(bytes(payload))
    return bytes(payload)


__all__ = ["synthetic_indices", "synthetic_mmap", "synthetic_palette"]
