#!/usr/bin/env python3
"""Build the PS2-to-Xbox texture map for ESPN NFL 2K5 (SLUS-20919).

What this produces
------------------
``mod_editor/data/nfl2k5-xbox-map.v1.json`` -- the shipped manifest that lets
2K5 Mod Studio name a PCSX2 texture replacement for an asset the user edited on
the Xbox disc, plus an unresolved sidecar recording, with a reason, everything
that did not make it.

Why it can be computed at all
-----------------------------
PCSX2 names a replacement after the texture's identity, not after any file on
the disc: ``<TEX0Hash>-<CLUTHash>-<bits>.png`` where both hashes are XXH3-64
(``GSTextureCache.cpp``'s ``HashCacheKey::Create`` / ``HashTextureLevel``) and
``bits = PSM | TW<<6 | TH<<10 | TCC<<14`` (``GSTextureReplacements.cpp:35-40``).
Every input is on the disc, so the whole map is an offline computation over the
retail image -- no emulator, no dumping, no capture.

Retail-free
-----------
Pixels are read, hashed and dropped.  Nothing this tool writes contains image
or palette data: the outputs are hashes, resource names, Xbox asset ids and
counts, which is the same class of thing the capability registry already ships.

What a row is keyed by
----------------------
The Xbox side of a row is an asset id in the Studio's own spelling, because
``ps2_export_service.plan_export`` looks the manifest up by the exact string an
edit carries.  Three of the four namespaces are physical texture ids --
``p8:{entry}:{name}``, ``tset:{entry}:{chunk}:{child}:{name}``,
``nfl2k5.crib.scene.…`` -- and the fourth is the *logical* uniform target,
``nfl2k5.uniform.{selector}.{component}`` (634 selectors x 39 components, per
``mod_editor/core/nfl2k5_uniform_catalog.py``).  A uniform edit carries the
logical id and nothing else, so without those rows every uniform export would
plan as unmapped.

**One Xbox asset per filename.**  The export service refuses to write a file
that two assets both claim -- it cannot attribute the result -- so publishing a
texture under both its physical id and a logical one makes *both* unusable
rather than offering two ways in.  :func:`resolve_claims` therefore picks a
single owner per name and sends every loser to the sidecar with a reason.  Its
tie-break, and the honest consequence, are documented on the function.

Layouts
-------
Three verified on-disc arrangements, all of which occur:

* ``lin``  -- linear rows, swizzled into GS 16x16 (PSMT8) / 32x16 (PSMT4)
  blocks with ``columnTable8`` / ``columnTable4``.
* ``vram`` -- the region already *is* the GS VRAM image; read the blocks out
  with ``blockTable8`` / ``blockTable4`` and TBW.
* ``c32``  -- the region is a linear PSMCT32 image (one 8 KB page wide, or
  ``TBW*32`` wide) whose GS-swizzled VRAM image is the PSMT8/PSMT4 texture,
  its mips and its CLUT, uploaded in one shot.

Mipped textures are **not** always ``c32``: 482 identities in the reference
pack are proved only by the linear path.  Both are tried, always.

Usage
-----
    nfl2k5_ps2_texture_map.py --selftest
    nfl2k5_ps2_texture_map.py --iso DISC.iso --xbox-inventory inventory_xbox.tsv.gz \\
        --pack-hashes pack_hashes.json \\
        --uniform-reports reports/assets \\
        --uniform-selectors reports/assets/uniform_texture_sharing.v2.json \\
        --manifest mod_editor/data/nfl2k5-xbox-map.v1.json \\
        --sidecar reports/gameplay_tuning/nfl2k5-xbox-map.unresolved.v1.json
    nfl2k5_ps2_texture_map.py --iso DISC.iso --hashes-out hashes.jsonl.gz
    nfl2k5_ps2_texture_map.py --hashes-in hashes.jsonl.gz ...   # redo the join
    nfl2k5_ps2_texture_map.py --iso DISC.iso --oracle hop1_v5_results.jsonl.gz
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import io
import json
import multiprocessing
import os
from operator import itemgetter
from pathlib import Path
import re
import struct
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# A shipped tool may be launched by an embeddable interpreter that does not put
# the script's directory on sys.path; put it back before importing siblings.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import nfl2k5_ps2_disc_inventory as inv  # noqa: E402
import ps2_iso9660 as iso  # noqa: E402
from xxh3 import xxh3_64  # noqa: E402

# Past this many candidate Xbox ids a name is fanned out beyond any hope of
# shipping, so the exact set stops being worth its memory.
ID_CAP = 16

SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"
SIDECAR_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map_unresolved/v1"
SERIAL = inv.SERIAL
METHOD = "hop1/v5"

# The emulator this map is named for.  Verified read-only on the rig: the
# replacement loader always inserts the canonical (bit-14-stripped) key and
# additionally inserts the verbatim bit-14 alias when ClassicTextureNames is
# on (GSTextureReplacements.cpp:449-456).  With it off a bit-14 name aliases
# onto the TCC=0 variant's key, so the setting is load-bearing and travels with
# the manifest.  SLUS-20919 is not in s_classic_default_serials.
EMULATOR = {
    "branch": "pcsx2-vr-classic-dump",
    "checkout": "rig:~/penguinscreen2-dev",
    "commit": "8226182aabe19640c6e676331678612f257356dd",
    "commit_status": "rig-verified",
    "hash_convention": "classic-tcc-bit14",
    "name": "PenguinScreen2",
    "requires_setting": "ClassicTextureNames=true",
}

PSMT8 = 0x13
PSMT4 = 0x14

TXTR_DESCRIPTOR_SIZE = inv.TXTR_DESCRIPTOR_SIZE      # 0x38


class TextureMapError(ValueError):
    """A refusal with a sentence attached."""


# ---------------------------------------------------------------------------
# GS tables, verbatim from pcsx2/GS/GSTables.cpp
# ---------------------------------------------------------------------------

COLUMN_TABLE8 = (
    (0, 4, 16, 20, 32, 36, 48, 52, 2, 6, 18, 22, 34, 38, 50, 54),
    (8, 12, 24, 28, 40, 44, 56, 60, 10, 14, 26, 30, 42, 46, 58, 62),
    (33, 37, 49, 53, 1, 5, 17, 21, 35, 39, 51, 55, 3, 7, 19, 23),
    (41, 45, 57, 61, 9, 13, 25, 29, 43, 47, 59, 63, 11, 15, 27, 31),
    (96, 100, 112, 116, 64, 68, 80, 84, 98, 102, 114, 118, 66, 70, 82, 86),
    (104, 108, 120, 124, 72, 76, 88, 92, 106, 110, 122, 126, 74, 78, 90, 94),
    (65, 69, 81, 85, 97, 101, 113, 117, 67, 71, 83, 87, 99, 103, 115, 119),
    (73, 77, 89, 93, 105, 109, 121, 125, 75, 79, 91, 95, 107, 111, 123, 127),
    (128, 132, 144, 148, 160, 164, 176, 180, 130, 134, 146, 150, 162, 166, 178, 182),
    (136, 140, 152, 156, 168, 172, 184, 188, 138, 142, 154, 158, 170, 174, 186, 190),
    (161, 165, 177, 181, 129, 133, 145, 149, 163, 167, 179, 183, 131, 135, 147, 151),
    (169, 173, 185, 189, 137, 141, 153, 157, 171, 175, 187, 191, 139, 143, 155, 159),
    (224, 228, 240, 244, 192, 196, 208, 212, 226, 230, 242, 246, 194, 198, 210, 214),
    (232, 236, 248, 252, 200, 204, 216, 220, 234, 238, 250, 254, 202, 206, 218, 222),
    (193, 197, 209, 213, 225, 229, 241, 245, 195, 199, 211, 215, 227, 231, 243, 247),
    (201, 205, 217, 221, 233, 237, 249, 253, 203, 207, 219, 223, 235, 239, 251, 255),
)

COLUMN_TABLE4 = (
    (0, 8, 32, 40, 64, 72, 96, 104, 2, 10, 34, 42, 66, 74, 98, 106,
     4, 12, 36, 44, 68, 76, 100, 108, 6, 14, 38, 46, 70, 78, 102, 110),
    (16, 24, 48, 56, 80, 88, 112, 120, 18, 26, 50, 58, 82, 90, 114, 122,
     20, 28, 52, 60, 84, 92, 116, 124, 22, 30, 54, 62, 86, 94, 118, 126),
    (65, 73, 97, 105, 1, 9, 33, 41, 67, 75, 99, 107, 3, 11, 35, 43,
     69, 77, 101, 109, 5, 13, 37, 45, 71, 79, 103, 111, 7, 15, 39, 47),
    (81, 89, 113, 121, 17, 25, 49, 57, 83, 91, 115, 123, 19, 27, 51, 59,
     85, 93, 117, 125, 21, 29, 53, 61, 87, 95, 119, 127, 23, 31, 55, 63),
    (192, 200, 224, 232, 128, 136, 160, 168, 194, 202, 226, 234, 130, 138, 162, 170,
     196, 204, 228, 236, 132, 140, 164, 172, 198, 206, 230, 238, 134, 142, 166, 174),
    (208, 216, 240, 248, 144, 152, 176, 184, 210, 218, 242, 250, 146, 154, 178, 186,
     212, 220, 244, 252, 148, 156, 180, 188, 214, 222, 246, 254, 150, 158, 182, 190),
    (129, 137, 161, 169, 193, 201, 225, 233, 131, 139, 163, 171, 195, 203, 227, 235,
     133, 141, 165, 173, 197, 205, 229, 237, 135, 143, 167, 175, 199, 207, 231, 239),
    (145, 153, 177, 185, 209, 217, 241, 249, 147, 155, 179, 187, 211, 219, 243, 251,
     149, 157, 181, 189, 213, 221, 245, 253, 151, 159, 183, 191, 215, 223, 247, 255),
    (256, 264, 288, 296, 320, 328, 352, 360, 258, 266, 290, 298, 322, 330, 354, 362,
     260, 268, 292, 300, 324, 332, 356, 364, 262, 270, 294, 302, 326, 334, 358, 366),
    (272, 280, 304, 312, 336, 344, 368, 376, 274, 282, 306, 314, 338, 346, 370, 378,
     276, 284, 308, 316, 340, 348, 372, 380, 278, 286, 310, 318, 342, 350, 374, 382),
    (321, 329, 353, 361, 257, 265, 289, 297, 323, 331, 355, 363, 259, 267, 291, 299,
     325, 333, 357, 365, 261, 269, 293, 301, 327, 335, 359, 367, 263, 271, 295, 303),
    (337, 345, 369, 377, 273, 281, 305, 313, 339, 347, 371, 379, 275, 283, 307, 315,
     341, 349, 373, 381, 277, 285, 309, 317, 343, 351, 375, 383, 279, 287, 311, 319),
    (448, 456, 480, 488, 384, 392, 416, 424, 450, 458, 482, 490, 386, 394, 418, 426,
     452, 460, 484, 492, 388, 396, 420, 428, 454, 462, 486, 494, 390, 398, 422, 430),
    (464, 472, 496, 504, 400, 408, 432, 440, 466, 474, 498, 506, 402, 410, 434, 442,
     468, 476, 500, 508, 404, 412, 436, 444, 470, 478, 502, 510, 406, 414, 438, 446),
    (385, 393, 417, 425, 449, 457, 481, 489, 387, 395, 419, 427, 451, 459, 483, 491,
     389, 397, 421, 429, 453, 461, 485, 493, 391, 399, 423, 431, 455, 463, 487, 495),
    (401, 409, 433, 441, 465, 473, 497, 505, 403, 411, 435, 443, 467, 475, 499, 507,
     405, 413, 437, 445, 469, 477, 501, 509, 407, 415, 439, 447, 471, 479, 503, 511),
)

COLUMN_TABLE32 = (
    (0, 1, 4, 5, 8, 9, 12, 13),
    (2, 3, 6, 7, 10, 11, 14, 15),
    (16, 17, 20, 21, 24, 25, 28, 29),
    (18, 19, 22, 23, 26, 27, 30, 31),
    (32, 33, 36, 37, 40, 41, 44, 45),
    (34, 35, 38, 39, 42, 43, 46, 47),
    (48, 49, 52, 53, 56, 57, 60, 61),
    (50, 51, 54, 55, 58, 59, 62, 63),
)

BLOCK_TABLE8 = (
    (0, 1, 4, 5, 16, 17, 20, 21),
    (2, 3, 6, 7, 18, 19, 22, 23),
    (8, 9, 12, 13, 24, 25, 28, 29),
    (10, 11, 14, 15, 26, 27, 30, 31),
)

BLOCK_TABLE4 = (
    (0, 2, 8, 10), (1, 3, 9, 11), (4, 6, 12, 14), (5, 7, 13, 15),
    (16, 18, 24, 26), (17, 19, 25, 27), (20, 22, 28, 30), (21, 23, 29, 31),
)

BLOCK_TABLE32 = (
    (0, 1, 4, 5, 16, 17, 20, 21),
    (2, 3, 6, 7, 18, 19, 22, 23),
    (8, 9, 12, 13, 24, 25, 28, 29),
    (10, 11, 14, 15, 26, 27, 30, 31),
)

# columnTable32 read backwards: VRAM u32 index -> (y & 7, x & 7).
_INV_COLUMN32: List[Tuple[int, int]] = [(0, 0)] * 64
for _y in range(8):
    for _x in range(8):
        _INV_COLUMN32[COLUMN_TABLE32[_y][_x]] = (_y, _x)

# blockTable32 read backwards: block-in-page -> ((y >> 3) & 3, (x >> 3) & 7).
_INV_BLOCK32: List[Tuple[int, int]] = [(0, 0)] * 32
for _y in range(4):
    for _x in range(8):
        _INV_BLOCK32[BLOCK_TABLE32[_y][_x]] = (_y, _x)

_LOW_NIBBLE = bytes(value & 0x0F for value in range(256))
_HIGH_NIBBLE = bytes(value >> 4 for value in range(256))
_SHIFT_NIBBLE = bytes((value << 4) & 0xFF for value in range(256))


# ---------------------------------------------------------------------------
# Permutation gathers.  Everything below moves bytes with one cached
# ``itemgetter`` per shape, which is a C-level loop; a Python for-loop over
# 6.4 GB of texels is not a thing that finishes.
# ---------------------------------------------------------------------------

_GATHERS: Dict[tuple, object] = {}


def _gather(key: tuple, build) -> object:
    getter = _GATHERS.get(key)
    if getter is None:
        indices = build()
        if not indices:
            raise TextureMapError("empty permutation")
        getter = itemgetter(*indices) if len(indices) > 1 else None
        if getter is None:
            single = indices[0]
            getter = lambda data, _i=single: (data[_i],)   # noqa: E731
        _GATHERS[key] = getter
    return getter


def _apply(getter, data: bytes) -> bytes:
    return bytes(getter(data))


def _swizzle8_perm(width: int, height: int) -> List[int]:
    """Row-major 16x16 blocks, ``columnTable8`` inside -- what BlockPtr sees."""
    blocks_x, blocks_y = width // 16, height // 16
    out = [0] * (width * height)
    for by in range(blocks_y):
        for bx in range(blocks_x):
            base = (by * blocks_x + bx) * 256
            for y in range(16):
                row = (by * 16 + y) * width + bx * 16
                column = COLUMN_TABLE8[y]
                for x in range(16):
                    out[base + column[x]] = row + x
    return out


def _swizzle4_perms(width: int, height: int) -> Tuple[List[int], List[int]]:
    """32x16 blocks per ``columnTable4``; even nibble address = low nibble."""
    blocks_x, blocks_y = width // 32, height // 16
    nibbles = [0] * (width * height)
    for by in range(blocks_y):
        for bx in range(blocks_x):
            base = (by * blocks_x + bx) * 512
            for y in range(16):
                row = (by * 16 + y) * width + bx * 32
                column = COLUMN_TABLE4[y]
                for x in range(32):
                    nibbles[base + column[x]] = row + x
    return nibbles[0::2], nibbles[1::2]


def swizzle8_blocks(image: bytes, width: int, height: int) -> bytes:
    getter = _gather(("s8", width, height), lambda: _swizzle8_perm(width, height))
    return _apply(getter, image)


def swizzle4_blocks(indices: bytes, width: int, height: int) -> bytes:
    low_getter = _gather(("s4lo", width, height),
                         lambda: _swizzle4_perms(width, height)[0])
    high_getter = _gather(("s4hi", width, height),
                          lambda: _swizzle4_perms(width, height)[1])
    low = _apply(low_getter, indices)
    high = _apply(high_getter, indices).translate(_SHIFT_NIBBLE)
    return bytes(map(int.__or__, low, high))


def unpack4(data: bytes, width: int, height: int) -> bytes:
    """4-bit indices to one byte each, low nibble first (WritePixel4 order)."""
    packed = data[: (width * height) // 2]
    out = bytearray(width * height)
    out[0::2] = packed.translate(_LOW_NIBBLE)
    out[1::2] = packed.translate(_HIGH_NIBBLE)
    return bytes(out)


def level_bytes(psm: int, image: bytes, width: int, height: int) -> bytes:
    """The bytes PCSX2 hashes for one level.

    The block path applies whenever the level covers a whole GS block in both
    directions (``fmsk == 0xFFFFFFFF`` for PSMT8/PSMT4); anything smaller is
    hashed as the expanded index rows that ``rtxP`` produced.
    """
    if psm == PSMT8:
        if width >= 16 and height >= 16:
            return swizzle8_blocks(image, width, height)
        return image
    if psm == PSMT4:
        if width >= 32 and height >= 16:
            return swizzle4_blocks(image, width, height)
        return image
    raise TextureMapError("unsupported PSM 0x%02x" % psm)


# ---------------------------------------------------------------------------
# The same permutations, run backwards.  Hashing only ever needs the forward
# direction; a *decoder* needs the inverse, because what it holds is the GS
# block image and what it wants is the linear index rows.  They live here, one
# function under the other, so the two directions cannot drift apart -- an
# inverse derived from a copy of the tables would be a second implementation of
# the same maths, and the pair would agree only until one of them was fixed.
# ---------------------------------------------------------------------------

def _invert(order: Sequence[int]) -> List[int]:
    """``inverse[order[i]] == i``.  ``order`` must be a permutation."""
    inverse = [0] * len(order)
    for position, source in enumerate(order):
        inverse[source] = position
    return inverse


def unswizzle8_blocks(blocks: bytes, width: int, height: int) -> bytes:
    """Inverse of :func:`swizzle8_blocks`: GS 16x16 blocks back to linear rows."""
    getter = _gather(("u8", width, height),
                     lambda: _invert(_swizzle8_perm(width, height)))
    return _apply(getter, blocks)


def unswizzle4_blocks(packed: bytes, width: int, height: int) -> bytes:
    """Inverse of :func:`swizzle4_blocks`: one index byte per texel, linear.

    The forward direction packs two texels per byte, so the inverse gathers
    from the low-nibble and high-nibble halves laid end to end.
    """
    count = width * height

    def build() -> List[int]:
        low, high = _swizzle4_perms(width, height)
        order = [0] * count
        for position, source in enumerate(low):
            order[source] = position
        for position, source in enumerate(high):
            order[source] = position + len(low)
        return order

    getter = _gather(("u4", width, height), build)
    half = packed[: count // 2]
    return _apply(getter, half.translate(_LOW_NIBBLE) + half.translate(_HIGH_NIBBLE))


def level_indices(psm: int, blocks: bytes, width: int, height: int) -> bytes:
    """Inverse of :func:`level_bytes`: one palette index per texel, row-major.

    The small-level path of :func:`level_bytes` is the identity, so this one is
    too: below a whole GS block in either direction the bytes already are the
    expanded index rows.
    """
    if psm == PSMT8:
        if width >= 16 and height >= 16:
            return unswizzle8_blocks(blocks, width, height)
        return blocks[: width * height]
    if psm == PSMT4:
        if width >= 32 and height >= 16:
            return unswizzle4_blocks(blocks, width, height)
        return blocks[: width * height]
    raise TextureMapError("unsupported PSM 0x%02x" % psm)


def vram_block_offsets(width: int, height: int, tbw: int, psm: int) -> List[int]:
    """Byte offset of every block relative to the image's TBP, row-major."""
    pages_wide = max(1, (tbw * 64) // 128)
    out = []
    if psm == PSMT8:
        blocks_x, blocks_y = width // 16, height // 16
        for by in range(blocks_y):
            for bx in range(blocks_x):
                page = (by >> 2) * pages_wide + (bx >> 3)
                out.append((page * 32 + BLOCK_TABLE8[by & 3][bx & 7]) * 256)
    else:
        blocks_x, blocks_y = width // 32, height // 16
        for by in range(blocks_y):
            for bx in range(blocks_x):
                page = (by >> 3) * pages_wide + (bx >> 2)
                out.append((page * 32 + BLOCK_TABLE4[by & 7][bx & 3]) * 256)
    return out


def vram_level_bytes(vram: bytes, offset: int, width: int, height: int,
                     tbw: int, psm: int) -> bytes:
    """The hash input when the disc region already holds the GS VRAM image."""
    block_width = 16 if psm == PSMT8 else 32
    if width < block_width or height < 16:
        raise TextureMapError("vram-small")
    offsets = vram_block_offsets(width, height, tbw, psm)
    if offset + max(offsets) + 256 > len(vram):
        raise TextureMapError("vram out of range")
    return b"".join(vram[offset + start:offset + start + 256] for start in offsets)


def c32_source_words(vram_word_index: int, width32: int, pages_wide: int) -> int:
    """Invert the one-shot PSMCT32 upload: VRAM u32 slot -> linear u32 slot."""
    page, within = divmod(vram_word_index, 2048)
    block, column = divmod(within, 64)
    y_hi, x_hi = _INV_BLOCK32[block]
    y_lo, x_lo = _INV_COLUMN32[column]
    page_y, page_x = divmod(page, pages_wide)
    y = (page_y << 5) | (y_hi << 3) | y_lo
    x = (page_x << 6) | (x_hi << 3) | x_lo
    return y * width32 + x


def _c32_check(region_words: int, width32: int) -> int:
    """Refuse a region that is not a whole number of 32-row PSMCT32 pages.

    The reference implementation scattered into an uninitialised array, so a
    partial page either ran off the end (an error) or would have hashed
    uninitialised memory (not reproducible).  Both are refusals here.
    """
    if width32 <= 0 or region_words % width32:
        raise TextureMapError("c32 region not a whole number of rows")
    pages_wide = width32 // 64
    if pages_wide < 1:
        raise TextureMapError("c32 width narrower than a page")
    if region_words % (32 * width32):
        raise TextureMapError("c32 region not a whole number of pages")
    return pages_wide


def c32_level_bytes(region: bytes, width: int, height: int, tbw: int, psm: int,
                    width32: int) -> bytes:
    """L0 hash input for the c32 layout, gathered straight from the region."""
    words = len(region) // 4
    pages_wide = _c32_check(words, width32)
    block_width = 16 if psm == PSMT8 else 32
    if width < block_width or height < 16:
        raise TextureMapError("vram-small")
    offsets = vram_block_offsets(width, height, tbw, psm)
    if max(offsets) + 256 > len(region):
        raise TextureMapError("vram out of range")

    def build() -> List[int]:
        indices: List[int] = []
        for start in offsets:
            first_word = start // 4
            for slot in range(64):
                source = c32_source_words(first_word + slot, width32, pages_wide)
                base = source * 4
                indices.extend((base, base + 1, base + 2, base + 3))
        return indices

    getter = _gather(("c32", width, height, tbw, psm, width32, pages_wide), build)
    return _apply(getter, region)


def c32_clut_bytes(region: bytes, byte_offset: int, palette_bytes: int,
                   width32: int) -> bytes:
    """The CLUT as it sits in the rebuilt VRAM image, without rebuilding it."""
    words = len(region) // 4
    pages_wide = _c32_check(words, width32)
    if byte_offset < 0 or byte_offset % 4 or byte_offset + palette_bytes > len(region):
        raise TextureMapError("c32 clut out of range")

    def build() -> List[int]:
        indices: List[int] = []
        for slot in range(palette_bytes // 4):
            source = c32_source_words(byte_offset // 4 + slot, width32, pages_wide)
            base = source * 4
            indices.extend((base, base + 1, base + 2, base + 3))
        return indices

    getter = _gather(("c32clut", byte_offset, palette_bytes, width32, pages_wide),
                     build)
    return _apply(getter, region)


# ---------------------------------------------------------------------------
# CLUT permutations
# ---------------------------------------------------------------------------

def _swap34_perm() -> List[int]:
    """CSM1 8-bit CLUT position swizzle: entries 8..15 <-> 16..23 in every 32."""
    return [(i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1) for i in range(256)]


def _vramread_perm() -> List[int]:
    """A 1024-byte CSM1 CLUT stored as the 16x16 PSMCT32 VRAM image."""
    out = []
    for entry in _swap34_perm():
        x, y = entry & 15, entry >> 4
        block = (x >> 3) + 2 * (y >> 3)
        out.append(block * 64 + COLUMN_TABLE32[y & 7][x & 7])
    return out


def _vramread4_perm() -> List[int]:
    return [COLUMN_TABLE32[i >> 3][i & 7] for i in range(16)]


SWAP34 = _swap34_perm()
VRAMREAD = _vramread_perm()
VRAMREAD4 = _vramread4_perm()


def _entry_perm_getter(name: str, order: Sequence[int]):
    def build() -> List[int]:
        indices: List[int] = []
        for entry in order:
            base = entry * 4
            indices.extend((base, base + 1, base + 2, base + 3))
        return indices
    return _gather(("clut", name), build)


def permute_clut(palette: bytes, order: Sequence[int], name: str) -> bytes:
    return _apply(_entry_perm_getter(name, order), palette)


# ---------------------------------------------------------------------------
# TEX0
# ---------------------------------------------------------------------------

def tex0_fields(tex0: int) -> dict:
    return {
        "TBP0": tex0 & 0x3FFF, "TBW": (tex0 >> 14) & 0x3F,
        "PSM": (tex0 >> 20) & 0x3F, "TW": (tex0 >> 26) & 0xF,
        "TH": (tex0 >> 30) & 0xF, "TCC": (tex0 >> 34) & 1,
        "TFX": (tex0 >> 35) & 3, "CBP": (tex0 >> 37) & 0x3FFF,
        "CPSM": (tex0 >> 51) & 0xF, "CSM": (tex0 >> 55) & 1,
        "CSA": (tex0 >> 56) & 0x1F, "CLD": (tex0 >> 61) & 7,
    }


def texture_bits(psm: int, tw: int, th: int, tcc: int) -> int:
    """``GSTextureReplacements.cpp``'s packed property word."""
    return psm | (tw << 6) | (th << 10) | (tcc << 14)


def replacement_name(tex0_hash: int, clut_hash: Optional[int], bits: int) -> str:
    """``%llx-%llx-%08x.png`` -- the 64-bit fields are unpadded, ``bits`` is not."""
    if clut_hash is None:
        return "%x-%08x.png" % (tex0_hash, bits)
    return "%x-%x-%08x.png" % (tex0_hash, clut_hash, bits)


def parse_replacement_name(name: str) -> Tuple[Optional[int], Optional[int]]:
    """``(bits, clut_hash)`` from a canonical PCSX2 filename, or ``(None, None)``."""
    parts = name.rsplit(".", 1)[0].split("-")
    if len(parts) < 2:
        return None, None
    field = parts[-2] if parts[-1].startswith("mip") else parts[-1]
    try:
        bits = int(field, 16)
        clut = int(parts[1], 16) if len(parts) >= 3 else None
    except ValueError:
        return None, None
    return bits, clut


def level_count_and_linear_size(width: int, height: int, bits_per_pixel: int,
                               descriptor: bytes) -> Tuple[int, int]:
    """Levels in use, and the linear byte size of the whole chain."""
    low1, high1, low2, high2 = struct.unpack_from("<4I", descriptor, 8)
    register1 = low1 | (high1 << 32)
    register2 = low2 | (high2 << 32)
    pointers = [(register1 >> 0) & 0x3FFF, (register1 >> 20) & 0x3FFF,
                (register1 >> 40) & 0x3FFF, (register2 >> 0) & 0x3FFF,
                (register2 >> 20) & 0x3FFF, (register2 >> 40) & 0x3FFF]
    levels = 1
    for pointer in pointers:
        if pointer == 0:
            break
        levels += 1
    total = sum((max(1, width >> i) * max(1, height >> i) * bits_per_pixel) // 8
                for i in range(levels))
    return levels, total


# ---------------------------------------------------------------------------
# One texture
# ---------------------------------------------------------------------------

def analyse(descriptor: bytes, video: bytes, is_chunk: bool,
            region_end: Optional[int] = None) -> Optional[dict]:
    """Every candidate identity for one TXTR descriptor, or None if not indexed.

    Returns hashes and geometry.  No pixel or palette byte is retained.
    """
    if len(descriptor) < TXTR_DESCRIPTOR_SIZE:
        return None
    tex0 = struct.unpack_from("<Q", descriptor, 0)[0]
    fields = tex0_fields(tex0)
    psm = fields["PSM"]
    if psm not in (PSMT8, PSMT4):
        return None
    width, height = struct.unpack_from("<HH", descriptor, 0x2C)
    image_offset = struct.unpack_from("<I", descriptor, 0x18)[0]
    clut_override = struct.unpack_from("<I", descriptor, 0x28)[0]
    bits_per_pixel = 8 if psm == PSMT8 else 4
    palette_bytes = 1024 if psm == PSMT8 else 64
    tex0_width, tex0_height = 1 << fields["TW"], 1 << fields["TH"]
    levels, linear_total = level_count_and_linear_size(
        width, height, bits_per_pixel, descriptor)

    record = {
        "w": width, "h": height, "tw": tex0_width, "th": tex0_height,
        "psm": "PSMT8" if psm == PSMT8 else "PSMT4",
        "mips": levels, "img_off": image_offset, "clut_ovr": clut_override,
        "cbp_off": fields["CBP"] * 256, "tbw": fields["TBW"],
        "tex0": "0x%016x" % tex0, "l0": {}, "clut": {}, "notes": [],
    }
    level0_bytes = (width * height * bits_per_pixel) // 8

    # ---- linear ----
    if image_offset + level0_bytes <= len(video):
        raw = video[image_offset:image_offset + level0_bytes]
        try:
            image = raw if psm == PSMT8 else unpack4(raw, width, height)
            level_w, level_h = width, height
            if (width, height) != (tex0_width, tex0_height):
                if width >= tex0_width and height >= tex0_height:
                    image = b"".join(
                        image[row * width:row * width + tex0_width]
                        for row in range(tex0_height))
                    level_w, level_h = tex0_width, tex0_height
                    record["notes"].append("cropped-to-pow2")
                else:
                    raise TextureMapError("smaller than pow2")
            record["l0"]["lin"] = xxh3_64(level_bytes(psm, image, level_w, level_h))
        except (TextureMapError, ValueError) as exc:
            record["notes"].append("lin:%s" % exc)
    else:
        record["notes"].append("l0 out of range")

    # ---- the region already is VRAM ----
    try:
        if (width, height) == (tex0_width, tex0_height):
            record["l0"]["vram"] = xxh3_64(vram_level_bytes(
                video, image_offset, width, height, fields["TBW"], psm))
    except (TextureMapError, ValueError) as exc:
        record["notes"].append("vram:%s" % exc)

    # ---- CLUT candidates: offsets x permutations ----
    offsets = {}
    if clut_override:
        offsets["ovr"] = clut_override
    offsets["cbp"] = image_offset + fields["CBP"] * 256
    offsets["afterlin"] = image_offset + linear_total
    offsets["afterl0"] = image_offset + level0_bytes
    if is_chunk:
        offsets["tail"] = len(video) - palette_bytes
    for label, start in offsets.items():
        if start < 0 or start + palette_bytes > len(video):
            continue
        palette = video[start:start + palette_bytes]
        if psm == PSMT8:
            record["clut"][label + "/swap34"] = xxh3_64(
                permute_clut(palette, SWAP34, "swap34"))
            record["clut"][label + "/vramread"] = xxh3_64(
                permute_clut(palette, VRAMREAD, "vramread"))
        else:
            record["clut"][label + "/raw"] = xxh3_64(palette)
            record["clut"][label + "/vramread"] = xxh3_64(
                permute_clut(palette, VRAMREAD4, "vramread4"))

    # ---- one-shot PSMCT32 upload ----
    if (width, height) != (tex0_width, tex0_height):
        return record
    end = region_end if region_end and region_end > image_offset else len(video)
    region = video[image_offset:end]
    region = region[: (len(region) // 256) * 256]
    for label, width32 in (("c32", 64), ("c32w", max(64, fields["TBW"] * 32))):
        if label == "c32w" and width32 == 64:
            continue
        try:
            record["l0"][label] = xxh3_64(c32_level_bytes(
                region, width, height, fields["TBW"], psm, width32))
            clut_at = fields["CBP"] * 256
            if clut_at + palette_bytes <= len(region):
                palette = c32_clut_bytes(region, clut_at, palette_bytes, width32)
                order = VRAMREAD if psm == PSMT8 else VRAMREAD4
                name = "vramread" if psm == PSMT8 else "vramread4"
                record["clut"][label + "cbp/vramread"] = xxh3_64(
                    permute_clut(palette, order, name))
                record["clut"][label + "cbp/raw"] = xxh3_64(palette)
        except (TextureMapError, ValueError) as exc:
            record["notes"].append("%s:%s" % (label, exc))
    return record


# ---------------------------------------------------------------------------
# Disc walk.  The chunk loop mirrors nfl2k5_ps2_disc_inventory.process_entry so
# the two enumerate the same objects; this one decodes the whole payload
# because the pixels live past the metadata cap.
# ---------------------------------------------------------------------------

_state: dict = {}


def initialise(iso_path: str, packs, entries) -> None:
    _state["archive"] = inv.VirtualPacks(iso_path, packs)
    _state["entries"] = list(entries)


def _full_payload(archive, virtual_offset: int, stored: int, compressed: bool,
                  system_bytes: int, video_bytes: int) -> Tuple[bytes, bytes]:
    body = archive.read(virtual_offset, stored)
    if compressed:
        declared = struct.unpack_from("<I", body, 0)[0]
        data = inv.decompress_prefix(body, declared)
    else:
        data = body
    if len(data) < system_bytes + video_bytes:
        raise TextureMapError("short payload %d < %d+%d"
                              % (len(data), system_bytes, video_bytes))
    return data[:system_bytes], data[system_bytes:system_bytes + video_bytes]


def _tset_descriptors(system: bytes) -> List[Tuple[int, Optional[str], bytes]]:
    _version, count = struct.unpack_from("<II", system, 0)
    out = []
    for index in range(count):
        record = inv.TSET_REF_BASE + index * inv.TSET_REF_STRIDE
        if system[record:record + 4] != b"TXTR":
            continue
        pointer = struct.unpack_from("<i", system, record + 8)[0]
        descriptor = record + 8 + pointer - 1
        name_pointer = struct.unpack_from("<i", system, record + 4)[0]
        name = (inv.utf16z(system, record + 4 + name_pointer - 1, len(system))
                if name_pointer else None)
        out.append((index, name, system[descriptor:descriptor + TXTR_DESCRIPTOR_SIZE]))
    return out


def _scene_descriptors(system: bytes) -> List[Tuple[int, bytes]]:
    descriptor = struct.unpack_from("<i", system, 0x14)[0] + 0x14 - 1
    count = struct.unpack_from("<I", system, descriptor + 0x14)[0]
    table = struct.unpack_from("<i", system, descriptor + 0x18)[0] + descriptor + 0x18 - 1
    return [(index, system[table + index * TXTR_DESCRIPTOR_SIZE:
                           table + (index + 1) * TXTR_DESCRIPTOR_SIZE])
            for index in range(count)
            if table + (index + 1) * TXTR_DESCRIPTOR_SIZE <= len(system)]


def _next_offset(candidates: Sequence[int], after: int) -> Optional[int]:
    return next((value for value in candidates if value > after), None)


def process_entry(index: int, keep_payload: bool = False) -> List[dict]:
    """Every indexed texture in one outer-table entry.

    ``keep_payload`` attaches the bytes :func:`analyse` read -- the descriptor,
    the video block and the region end -- under a ``payload`` key, so a caller
    that wants *pixels* rather than hashes can decode the very same input this
    hashed.  It is off by default and never set on the pooled build: the map is
    a retail-free document, and a record carrying a video block would be
    neither small enough to pickle across a worker nor safe to serialise.
    """
    archive = _state["archive"]
    name_id, entry_size, offset_blocks = _state["entries"][index]
    virtual_base = offset_blocks * inv.ALIGNMENT
    out: List[dict] = []

    offset = 0
    chunk_index = 0
    while entry_size - offset >= inv.CHUNK_HEADER_SIZE:
        header = archive.read(virtual_base + offset, inv.CHUNK_HEADER_SIZE)
        fourcc = header[:4]
        stored, system_bytes, video_bytes, magic = struct.unpack_from("<4I", header, 4)
        bounded = (inv.printable_fourcc(fourcc) and stored
                   and offset + inv.CHUNK_HEADER_SIZE + stored <= entry_size)
        if not bounded:
            successor = inv.find_after_zero_padding(
                archive, virtual_base, entry_size, offset)
            if successor is None:
                break
            offset = successor
            continue

        compressed = magic == inv.COMPRESSED_SENTINEL
        kind = fourcc.decode("ascii")
        base = {"src": "", "entry": index, "id": "0x%08x" % name_id,
                "chunk": chunk_index}
        # The metadata cap the inventory walks under, so both agree on which
        # objects exist; the payload below is read in full regardless.
        capped = min(system_bytes if system_bytes else inv.NO_SYSTEM_PREFIX,
                     inv.METADATA_CAP)
        if not compressed:
            capped = min(capped, stored)

        try:
            system, video = _full_payload(
                archive, virtual_base + offset + inv.CHUNK_HEADER_SIZE, stored,
                compressed, system_bytes, video_bytes)
        except (inv.InventoryError, TextureMapError, struct.error):
            offset += inv.CHUNK_HEADER_SIZE + stored
            chunk_index += 1
            continue

        head = system[:capped]
        inner = ""
        object_name = None
        if len(head) >= 0x18 and inv.printable_fourcc(head[0x0C:0x10]):
            inner = head[0x0C:0x10].decode("ascii")
            object_name = inv.pointer_name(head, 0x10, len(head))

        try:
            if inner == "TXTR":
                descriptor = inv.relative_pointer(head, 0x14, len(head))
                if descriptor is not None:
                    desc = system[descriptor:descriptor + TXTR_DESCRIPTOR_SIZE]
                    record = analyse(desc, video, True)
                    if record:
                        record.update(base, src="chunk", idx=0, name=object_name or "",
                                      name_key=inv.name_key(object_name))
                        if keep_payload:
                            record["payload"] = {"descriptor": desc, "video": video,
                                                 "is_chunk": True, "region_end": None}
                        out.append(record)
            elif kind == "TSET":
                descriptors = _tset_descriptors(system)
                boundaries = sorted(
                    {struct.unpack_from("<I", desc, 0x28)[0]
                     for _i, _n, desc in descriptors if len(desc) >= TXTR_DESCRIPTOR_SIZE}
                    | {struct.unpack_from("<I", desc, 0x18)[0]
                       for _i, _n, desc in descriptors if len(desc) >= TXTR_DESCRIPTOR_SIZE})
                for child, name, desc in descriptors:
                    if len(desc) < TXTR_DESCRIPTOR_SIZE:
                        continue
                    start = struct.unpack_from("<I", desc, 0x18)[0]
                    region_end = _next_offset(boundaries, start)
                    record = analyse(desc, video, False, region_end)
                    if record:
                        record.update(base, src="tset", idx=child, name=name or "",
                                      name_key=inv.name_key(name))
                        if keep_payload:
                            record["payload"] = {"descriptor": desc, "video": video,
                                                 "is_chunk": False, "region_end": region_end}
                        out.append(record)
            if inner == "SCNE" and video_bytes > 0:
                descriptors = _scene_descriptors(system)
                boundaries = sorted({struct.unpack_from("<I", desc, 0x18)[0]
                                     for _i, desc in descriptors})
                scene_key = inv.name_key(object_name)
                for child, desc in descriptors:
                    start = struct.unpack_from("<I", desc, 0x18)[0]
                    region_end = _next_offset(boundaries, start)
                    record = analyse(desc, video, False, region_end)
                    if record:
                        record.update(
                            base, src="scne", idx=child,
                            name="%s/embedded_%04d" % (object_name or "", child),
                            name_key="%s/EMBEDDED_%04d" % (scene_key, child),
                            scene=scene_key)
                        if keep_payload:
                            record["payload"] = {"descriptor": desc, "video": video,
                                                 "is_chunk": False, "region_end": region_end}
                        out.append(record)
        except (struct.error, ValueError, IndexError):
            pass

        offset += inv.CHUNK_HEADER_SIZE + stored
        chunk_index += 1
    return out


# ---------------------------------------------------------------------------
# Xbox side
# ---------------------------------------------------------------------------

def _open_text(path: str):
    if str(path).endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")


def parse_extra(text: str) -> dict:
    return dict(pair.split("=", 1) for pair in text.split(";") if "=" in pair)


class XboxSide:
    """The Xbox disc's named resources, keyed the three ways the map joins."""

    def __init__(self) -> None:
        self.objects: Dict[str, List[Tuple[int, str]]] = {}
        self.tset_children: Dict[Tuple[int, int], List[Tuple[int, str]]] = {}
        self.tset_key: Dict[Tuple[str, int], List[Tuple[int, int]]] = {}
        self.scenes: Dict[str, List[Tuple[int, int]]] = {}
        self.children_by_entry: Dict[int, List[Tuple[int, int, str]]] = {}
        self.containers: Dict[Tuple[int, int], Tuple[str, str, str]] = {}
        self.rows = 0

    def asset_ids_in(self, entry: int) -> List[str]:
        """Every ``tset:`` asset id the Xbox disc carries in one outer entry."""
        return ["tset:%d:%d:%d:%s" % (entry, chunk, child, name)
                for chunk, child, name in self.children_by_entry.get(entry, ())]

    def physical_ids_in(self, entry: int, chunk: int) -> List[str]:
        """The asset ids one Xbox chunk carries, in the map's own namespaces.

        A uniform component names a chunk, not a texture, so this is where a
        logical target becomes something the map can key on.
        """
        children = self.tset_children.get((entry, chunk))
        if children:
            return ["tset:%d:%d:%d:%s" % (entry, chunk, child, name)
                    for child, name in sorted(children)]
        container = self.containers.get((entry, chunk))
        if container and container[0]:
            return ["p8:%d:%s" % (entry, container[0])]
        return []

    @classmethod
    def load(cls, path: str) -> "XboxSide":
        side = cls()
        containers = side.containers
        scene_chunks = set()
        with _open_text(path) as stream:
            header = stream.readline().rstrip("\n").split("\t")
            for line in stream:
                columns = line.rstrip("\n").split("\t")
                row = dict(zip(header, columns))
                extra = parse_extra(row.get("extra", ""))
                role = extra.get("role", "")
                side.rows += 1
                if role == "object":
                    entry = int(row["entry_index"])
                    chunk = int(extra.get("chunk", 0))
                    containers[(entry, chunk)] = (
                        row["name"], row["fourcc"], extra.get("id", ""))
                    side.objects.setdefault(row["name_key"], []).append(
                        (entry, row["name"]))
                elif role == "tset_child":
                    entry = int(row["entry_index"])
                    chunk = int(extra.get("chunk", 0))
                    child = int(extra.get("child", 0))
                    side.tset_children.setdefault((entry, chunk), []).append(
                        (child, row["name"]))
                    side.children_by_entry.setdefault(entry, []).append(
                        (chunk, child, row["name"]))
                elif role == "scne_texture":
                    scene_chunks.add((int(row["entry_index"]),
                                      int(extra.get("chunk", 0))))
        for (entry, chunk), (name, fourcc, identifier) in containers.items():
            if fourcc == "SCNE" and (entry, chunk) in scene_chunks:
                side.scenes.setdefault(inv.name_key(name), []).append((entry, chunk))
            if fourcc == "TSET" and identifier:
                side.tset_key.setdefault((identifier, chunk), []).append((entry, chunk))
        return side


def xbox_ids(side: XboxSide, record: dict) -> Tuple[List[str], str]:
    """The Xbox asset ids this PS2 texture resolves to, and the namespace.

    Uniqueness is the shipping rule.  ``p8:`` and scene rows must be unique by
    name; ``tset:`` children join at the *set* level on the shared ``(id,
    chunk)`` key -- the containers are unnamed on both discs -- and then pick
    the child by name, falling back to index.
    """
    source = record["src"]
    if source == "scne":
        matches = side.scenes.get(record.get("scene", ""), [])
        return ([("nfl2k5.crib.scene.c%04d.t%03d" % (chunk, record["idx"]))
                 if entry == 4248 else
                 ("nfl2k5.scene.o%04d.c%04d.t%03d" % (entry, chunk, record["idx"]))
                 for entry, chunk in matches], "scene")
    if source == "tset":
        sets = side.tset_key.get((record["id"], record["chunk"]), [])
        ids = []
        for entry, chunk in sets:
            children = side.tset_children.get((entry, chunk), [])
            chosen = [(child, name) for child, name in children
                      if inv.name_key(name) == record["name_key"]
                      and record["name_key"]]
            if not chosen:
                chosen = [(child, name) for child, name in children
                          if child == record["idx"]]
            for child, name in chosen:
                ids.append("tset:%d:%d:%d:%s" % (entry, chunk, child, name))
        return ids, "tset"
    matches = side.objects.get(record["name_key"], [])
    return (["p8:%d:%s" % (entry, name) for entry, name in matches], "p8")


# ---------------------------------------------------------------------------
# Pack corpus (the identity oracle)
# ---------------------------------------------------------------------------

class PackCorpus:
    """The canonical replacement identities a real pack proves."""

    def __init__(self, by_tex0: Dict[int, List[str]]) -> None:
        self.by_tex0 = by_tex0
        self.names = {name for names in by_tex0.values() for name in names}

    @classmethod
    def load(cls, path: str) -> "PackCorpus":
        with open(path, "r", encoding="utf-8") as stream:
            document = json.load(stream)
        by_tex0 = {int(key): sorted(set(value))
                   for key, value in document["byname"].items()}
        return cls(by_tex0)


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------

def _namespace_of(row: dict) -> str:
    """One namespace, or ``mixed`` when a name is proved across several."""
    namespaces = {value for value in row.get("namespaces", ()) if value}
    if len(namespaces) == 1:
        return next(iter(namespaces))
    return "mixed" if namespaces else "unknown"


def _hash_hex(mapping: Dict[str, int]) -> Dict[str, str]:
    return {key: "%x" % value for key, value in mapping.items()}


def disc_jobs(iso_path: str, hash_image: bool = True):
    """``(packs, entries, identity)`` for the retail image."""
    image = iso.open_image(iso_path)
    packs = inv.discover_packs(image)
    archive = inv.VirtualPacks(iso_path, packs)
    try:
        _outer, entries = inv.read_outer_table(archive)
    finally:
        archive.close()
    identity = inv.image_identity(image, hash_image)
    return packs, entries, identity


def stream_textures(iso_path: str, jobs: int = 0, limit: int = 0,
                    progress=None, hash_image: bool = True) -> Iterable[dict]:
    packs, entries, identity = disc_jobs(iso_path, hash_image)
    order = list(range(len(entries)))
    if limit:
        order = order[:limit]
    yield {"__identity__": identity, "__entries__": len(entries)}
    workers = jobs or (os.cpu_count() or 4)
    if workers <= 1:
        initialise(iso_path, packs, entries)
        for done, index in enumerate(order, 1):
            for record in process_entry(index):
                yield record
            if progress and done % 200 == 0:
                progress(done, len(order))
        return
    context = multiprocessing.get_context("fork" if hasattr(os, "fork") else "spawn")
    with context.Pool(workers, initializer=initialise,
                      initargs=(iso_path, packs, entries)) as pool:
        for done, batch in enumerate(
                pool.imap_unordered(process_entry, order, chunksize=8), 1):
            for record in batch:
                yield record
            if progress and done % 200 == 0:
                progress(done, len(order))


def replay_hashes(path: str) -> Iterable[dict]:
    """Re-read a ``--hashes-out`` cache, so the join can be redone off-disc.

    The cache is hashes, names and offsets -- the same retail-free content the
    manifest is -- and re-running the join from it takes seconds instead of
    re-reading 4.6 GB.
    """
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if "__identity__" in record:
                yield record
                continue
            record["l0"] = {key: int(value, 16)
                            for key, value in record["l0"].items()}
            record["clut"] = {key: int(value, 16)
                              for key, value in record["clut"].items()}
            yield record


def build(iso_path: Optional[str], xbox_inventory: Optional[str],
          pack_hashes: Optional[str],
          jobs: int = 0, limit: int = 0, hashes_out: Optional[str] = None,
          progress=None, uniform_selectors: Optional[str] = None,
          uniform_reports: Optional[str] = None,
          hashes_in: Optional[str] = None) -> dict:
    """One pass over the disc; returns everything the outputs are made of."""
    corpus = PackCorpus.load(pack_hashes) if pack_hashes else None
    side = XboxSide.load(xbox_inventory) if xbox_inventory else XboxSide()
    selectors = load_uniform_selectors(uniform_selectors) if uniform_selectors else {}
    logical_targets = (load_logical_uniform_targets(uniform_reports)
                       if uniform_reports else {})

    identity = {}
    entry_count = 0
    scanned = 0
    stream = None
    if hashes_out:
        # newline="\n" on both arms: text mode would otherwise let the C
        # runtime decide, and a cache written on Windows would not compare
        # equal to one written anywhere else.
        stream = (gzip.open(hashes_out, "wt", encoding="utf-8", newline="\n")
                  if hashes_out.endswith(".gz")
                  else open(hashes_out, "w", encoding="utf-8", newline="\n"))

    proved: Dict[str, dict] = {}          # png -> {"ids": set, "namespaces", ...}
    tex0_only: Dict[str, int] = {}
    no_xbox: Dict[str, int] = {}
    per_texture_hits = 0
    bits_checked = 0
    bits_mismatched = 0
    name_divergence: Dict[str, str] = {}
    scanned_header = [False]
    # The shared (outer id, chunk) key, PS2 side: it is what lets a *logical*
    # Xbox uniform target find the PS2 texture that carries the same piece.
    ps2_by_id_chunk: Dict[Tuple[str, int], List[tuple]] = {}

    source = (replay_hashes(hashes_in) if hashes_in
              else stream_textures(iso_path, jobs, limit, progress))
    try:
        for record in source:
            if "__identity__" in record:
                identity = record["__identity__"]
                entry_count = record["__entries__"]
                continue
            scanned += 1
            if stream is not None:
                if not scanned_header[0]:
                    stream.write(json.dumps(
                        {"__identity__": identity, "__entries__": entry_count},
                        separators=(",", ":"), sort_keys=True) + "\n")
                    scanned_header[0] = True
                stream.write(json.dumps(
                    dict(record, l0=_hash_hex(record["l0"]),
                         clut=_hash_hex(record["clut"])),
                    separators=(",", ":"), sort_keys=True) + "\n")
            if corpus is None:
                continue
            fields = tex0_fields(int(record["tex0"], 16))
            psm = fields["PSM"]
            accepted = {
                texture_bits(psm, fields["TW"], fields["TH"], fields["TCC"]),
                texture_bits(psm, fields["TW"], fields["TH"], 0),
            }
            clut_values = set(record["clut"].values())
            ids: Optional[List[str]] = None
            namespace = ""
            proved_here: List[str] = []
            for layout, tex0_hash in record["l0"].items():
                for name in corpus.by_tex0.get(tex0_hash, ()):
                    bits, clut = parse_replacement_name(name)
                    if bits is None:
                        continue
                    bits_checked += 1
                    if bits not in accepted:
                        bits_mismatched += 1
                        continue
                    per_texture_hits += 1
                    if clut is not None and clut not in clut_values:
                        tex0_only[name] = tex0_only.get(name, 0) + 1
                        continue
                    canonical = replacement_name(
                        tex0_hash, clut,
                        texture_bits(psm, fields["TW"], fields["TH"], 1))
                    if canonical != name:
                        name_divergence[name] = canonical
                    if ids is None:
                        ids, namespace = xbox_ids(side, record)
                    # The manifest publishes the *computed* name, always with
                    # the classic TCC bit set, not the pack's spelling: four
                    # pack names were dumped on a build that strips bit 14, and
                    # a manifest that mixed both conventions would be a trap.
                    # The pack spelling stays the bookkeeping key so the corpus
                    # arithmetic (proved / tex0-only / unexplained) stays exact.
                    row = proved.setdefault(
                        name, {"ids": set(), "capped": False,
                               "namespaces": set(), "layouts": set(),
                               "sources": 0, "canonical": canonical})
                    row["namespaces"].add(namespace)
                    row["layouts"].add(layout)
                    row["sources"] += 1
                    # A fanned-out name can carry thousands of candidate ids and
                    # there are millions of pairs in total; the shipping rule
                    # only asks whether there is exactly one, so stop counting
                    # past the cap rather than holding the whole cross product.
                    if not row["capped"]:
                        row["ids"].update(ids)
                        if len(row["ids"]) > ID_CAP:
                            row["capped"] = True
                            row["ids"] = set(sorted(row["ids"])[:ID_CAP])
                    if not ids:
                        no_xbox[name] = no_xbox.get(name, 0) + 1
                    proved_here.append(name)
            if proved_here:
                key = (record.get("id") or "", record["chunk"])
                slot = ps2_by_id_chunk.setdefault(key, [])
                if len(slot) < 128:
                    slot.append((record["idx"], record["name_key"],
                                 tuple(sorted(set(proved_here)))))
    finally:
        if stream is not None:
            stream.close()

    # A name proved by any texture is not a tex0-only name, and a name that
    # resolved anywhere is not an orphan, whatever some other texture saw.
    for name in proved:
        tex0_only.pop(name, None)
        if proved[name]["ids"]:
            no_xbox.pop(name, None)

    return {
        "identity": identity,
        "entry_count": entry_count,
        "textures_scanned": scanned,
        "proved": proved,
        "tex0_only": tex0_only,
        "no_xbox": no_xbox,
        "bits_checked": bits_checked,
        "bits_mismatched": bits_mismatched,
        "name_divergence": name_divergence,
        "corpus": corpus,
        "xbox_rows": side.rows,
        "side": side,
        "selectors": selectors,
        "logical_targets": logical_targets,
        "ps2_by_id_chunk": ps2_by_id_chunk,
    }


# ---------------------------------------------------------------------------
# Uniform coverage -- the demo-team question
# ---------------------------------------------------------------------------
#
# "Is this team's kit mappable?" is a question about the *Xbox* side, because
# the Xbox target is what a user edits in the Studio.  NFL 2K5 stores one
# uniform per outer archive entry -- a "selector" -- and
# reports/assets/uniform_texture_sharing.v2.json names all 634 of them with
# their team, side and era.  So: enumerate the tset children in each selector
# entry, and ask which of those asset ids the manifest can name.

def load_uniform_selectors(path: str) -> Dict[int, dict]:
    """``outer_index -> {abbreviation, team, side, style, selector}``."""
    with open(path, "r", encoding="utf-8") as stream:
        document = json.load(stream)
    rows = document.get("nfl2k5", {}).get("selectors", [])
    out: Dict[int, dict] = {}
    for row in rows:
        index = row.get("outer_index")
        if isinstance(index, int):
            out[index] = {
                "abbreviation": row.get("abbreviation", ""),
                "team": row.get("team", ""),
                "side": row.get("side", ""),
                "style": row.get("style", ""),
                "selector": row.get("selector", ""),
            }
    return out


# ---------------------------------------------------------------------------
# Logical uniform targets
# ---------------------------------------------------------------------------
#
# What a user edits in the Studio is not a texture, it is a uniform component:
# `nfl2k5.uniform.{selector}.{component}`, 634 sets x 39 components.  The Xbox
# writer composes those into physical packages at build time, so a logical id
# has no GS hash of its own and would otherwise be unmappable -- every uniform
# export would plan as `unmapped`.
#
# Each of the four component families has a hash-pinned compatibility report
# that already says which archive chunk carries the component, so the logical
# id resolves to `(outer_index, chunk_index)` and from there to whatever asset
# ids the Xbox inventory shows in that chunk.  No new format work; the reports
# are the same ones the Xbox writers resolve their targets against.

UNIFORM_REPORTS = {
    "jersey": "nfl2k5_jersey_tset_compatibility.json",
    "pants": "nfl2k5_pants_tset_compatibility.json",
    "sleeve": "nfl2k5_sleeve_tset_compatibility.json",
    "helmet": "nfl2k5_live_helmet_txtr_compatibility.json",
    "numbers": "nfl2k5_live_numbers_nameplate_compatibility.json",
    "cards": "nfl2k5_team_select_card_inventory.json",
}
UNIFORM_SET_COUNT = 634
UNIFORM_COMPONENTS_PER_SET = 39
# Components whose Xbox and PS2 forms are not the same texture at all. The Xbox
# disc stores ten separate digit textures per family per kit and a 1024x32
# nameplate strip; the PS2 disc packs each digit family into one atlas
# (JERSEY_NUMBERS and friends) and carries no indexed texture at the nameplate
# chunk. There is no GS hash that names an individual Xbox digit, so these are
# reported unmappable rather than pointed at an atlas an exporter cannot write
# from a single digit PNG. Resolving them needs atlas composition, which is a
# WP4-and-later question, not a hashing one.
STRUCTURAL_COMPONENTS = frozenset(
    ["nameplate"]
    + ["digit.%s.%d" % (family, digit)
       for family in ("jersey", "helmet", "arm") for digit in range(10)])
MAPPABLE_COMPONENTS_PER_SET = UNIFORM_COMPONENTS_PER_SET - len(STRUCTURAL_COMPONENTS)
_DIGIT_COMPONENTS = {"jersey_digit": "digit.jersey", "helmet_digit": "digit.helmet",
                     "arm_digit": "digit.arm"}


_SELECTOR_SHAPE = re.compile(r"^[0-9A-Z]{2}[AH][0-9]{1,2}$")


def _selector_of(row: dict) -> str:
    """``00A0`` for one report row, however that report happens to say it.

    The four families disagree: the TSET and live-art reports carry a
    ``selector`` object, while the team-select inventory's ``selector`` is a
    *different* string (``unif:00:away:0:256``) and only its
    ``uniform_package`` names the set.  Package name first, therefore, then the
    object, and a bare string only when it is actually shaped like a selector.
    """
    for key in ("uniform_package", "logical_name"):
        value = row.get(key)
        if isinstance(value, str) and value:
            candidate = value.split(".")[0].strip().upper()
            if _SELECTOR_SHAPE.match(candidate):
                return candidate
    selector = row.get("selector")
    if isinstance(selector, dict):
        for key in ("logical_name",):
            value = selector.get(key)
            if isinstance(value, str) and value:
                candidate = value.split(".")[0].strip().upper()
                if _SELECTOR_SHAPE.match(candidate):
                    return candidate
        code = selector.get("asset_code")
        side = selector.get("side") or selector.get("side_code")
        variant = selector.get("variant")
        if code is not None and side is not None and variant is not None:
            return "%s%s%d" % (code, side, int(variant))
        return ""
    if isinstance(selector, str):
        candidate = selector.split(".")[0].strip().upper()
        return candidate if _SELECTOR_SHAPE.match(candidate) else ""
    return ""


def _logical_id(selector: str, component: str) -> str:
    return "nfl2k5.uniform.%s.%s" % (selector.lower(), component)


def load_logical_uniform_targets(reports_dir: str) -> Dict[str, List[Tuple[int, int]]]:
    """``logical asset id -> [(outer_index, chunk_index), ...]``."""
    folder = Path(reports_dir)

    def read(key: str) -> Optional[dict]:
        path = folder / UNIFORM_REPORTS[key]
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    targets: Dict[str, List[Tuple[int, int]]] = {}

    def add(selector: str, component: str, row: dict) -> None:
        if not selector:
            return
        try:
            location = (int(row["outer_index"]), int(row["chunk_index"]))
        except (KeyError, TypeError, ValueError):
            return
        slot = targets.setdefault(_logical_id(selector, component), [])
        if location not in slot:
            slot.append(location)

    for key, component in (("jersey", "torso"), ("pants", "pants"),
                           ("sleeve", "sleeve")):
        document = read(key)
        for row in (document or {}).get("packages", []):
            add(_selector_of(row), component, row)

    document = read("helmet")
    for row in (document or {}).get("resources", []):
        family = row.get("family")
        if family in ("helmet00", "helmet02"):
            add(_selector_of(row), "helmet.%s" % family, row)

    document = read("numbers")
    for row in (document or {}).get("resources", []):
        family = row.get("family")
        if family == "nameplate_atlas":
            add(_selector_of(row), "nameplate", row)
        elif family in _DIGIT_COMPONENTS and row.get("digit") is not None:
            add(_selector_of(row),
                "%s.%d" % (_DIGIT_COMPONENTS[family], int(row["digit"])), row)

    document = read("cards")
    for row in (document or {}).get("targets", []):
        family = row.get("family")
        try:
            width = int(row.get("width", 0))
        except (TypeError, ValueError):
            continue
        if family == "unif" and width == 256:
            add(_selector_of(row), "team-select.unif.256", row)
        elif family == "helm" and width in (128, 256):
            add(_selector_of(row), "team-select.helm.%d" % width, row)
    return targets


def _xbox_pieces(side: XboxSide, entry: int, chunk: int) -> List[Tuple[int, str]]:
    """``[(child index, name)]`` for a chunk, TSET children or the object itself."""
    children = side.tset_children.get((entry, chunk))
    if children:
        return sorted(children)
    container = side.containers.get((entry, chunk))
    if container and container[0]:
        return [(0, container[0])]
    return []


def logical_uniform_rows(side: XboxSide,
                         targets: Dict[str, List[Tuple[int, int]]],
                         by_asset: Dict[str, List[str]],
                         ps2_by_id_chunk: Optional[Dict[Tuple[str, int], List[tuple]]] = None
                         ) -> Tuple[List[dict], Dict[str, dict]]:
    """``(candidate entries, detail)`` for every logical uniform target.

    These are *candidates*: a name here still has to survive
    :func:`resolve_claims`, because a texture two kits share cannot be
    attributed to either of them.  Coverage is counted afterwards, by
    :func:`logical_coverage`, on the rows that actually ship.

    Two routes, both name-confirmed:

    1. the physical asset ids in the component's chunk, where those already
       resolved uniquely;
    2. the shared ``(outer id, chunk)`` key straight into the PS2 side, which
       is how the `p8:`-shaped pieces get mapped at all -- a PS2 texture called
       ``HELMET00`` matches all 634 Xbox ``helmet00`` objects by name, so the
       name join alone fans out to nothing shippable, while the id+chunk key
       names exactly one uniform package.

    Route 2 still requires the names to agree, which is what keeps the jersey
    digits out: Xbox stores ten 64x64 digits per kit, PS2 stores one
    ``JERSEY_NUMBERS`` atlas, so no piece matches and the component is reported
    unmapped rather than silently mapped to an atlas an exporter cannot write.
    """
    ps2_by_id_chunk = ps2_by_id_chunk or {}
    entries: List[dict] = []
    detail: Dict[str, dict] = {}
    for logical, locations in sorted(targets.items()):
        names: List[str] = []
        physical = 0
        for entry, chunk in locations:
            for identifier in side.physical_ids_in(entry, chunk):
                physical += 1
                for name in by_asset.get(identifier, ()):
                    if name not in names:
                        names.append(name)
            container = side.containers.get((entry, chunk))
            if not container or not container[2]:
                continue
            wanted = {inv.name_key(name): index
                      for index, name in _xbox_pieces(side, entry, chunk)}
            for _index, name_key, pngs in ps2_by_id_chunk.get(
                    (container[2], chunk), ()):
                if name_key and name_key in wanted:
                    for name in pngs:
                        if name not in names:
                            names.append(name)
        detail[logical] = {"names": names, "physical": physical}
        for name in names:
            entries.append({"pcsx2_png": name, "xbox_asset_id": logical})
    return entries, detail


def logical_coverage(detail: Dict[str, dict],
                     shipped: Dict[str, Sequence[str]]
                     ) -> Tuple[dict, Dict[str, dict]]:
    """``(coverage, per_selector)`` counted on the rows that actually ship.

    Deliberately measured *after* :func:`resolve_claims` rather than before it.
    A component whose only candidate PNG is shared with another kit does not
    ship, and calling it mapped would hand WP7 a demo kit whose export plans
    as ambiguous.
    """
    by_component: Dict[str, dict] = {}
    per_selector: Dict[str, dict] = {}
    covered = 0
    rows = 0
    for logical, row in sorted(detail.items()):
        component = logical.split(".", 3)[3] if logical.count(".") >= 3 else ""
        selector = logical.split(".")[2] if logical.count(".") >= 2 else ""
        names = shipped.get(logical) or ()
        component_row = by_component.setdefault(
            component, {"targets": 0, "mapped": 0})
        component_row["targets"] += 1
        selector_row = per_selector.setdefault(
            selector.upper(), {"targets": 0, "mapped": 0, "structural": 0})
        if component in STRUCTURAL_COMPONENTS:
            selector_row["structural"] += 1
        else:
            selector_row["targets"] += 1
        if names:
            covered += 1
            rows += len(names)
            component_row["mapped"] += 1
            selector_row["mapped"] += 1
        elif row["names"]:
            # Candidates existed but lost the sole-claimant tie-break.
            component_row["contested"] = component_row.get("contested", 0) + 1
        elif row["physical"]:
            # The chunk is there; nothing in it is the same texture. This is
            # the digit-atlas case: ten Xbox digits against one PS2 atlas.
            component_row["no_matching_texture"] = (
                component_row.get("no_matching_texture", 0) + 1)
        else:
            component_row["no_physical_chunk"] = (
                component_row.get("no_physical_chunk", 0) + 1)
    mappable_targets = sum(value["targets"] for key, value in by_component.items()
                           if key not in STRUCTURAL_COMPONENTS)
    coverage = {
        "logical_targets": len(detail),
        "logical_targets_expected": UNIFORM_SET_COUNT * UNIFORM_COMPONENTS_PER_SET,
        "logical_targets_mapped": covered,
        "structurally_unmappable_components": sorted(STRUCTURAL_COMPONENTS),
        "structurally_unmappable_reason":
            "the Xbox disc stores each jersey/helmet/arm digit as its own "
            "texture and the nameplate as a 1024x32 strip; the PS2 disc packs "
            "each digit family into one atlas and has no indexed texture at "
            "the nameplate chunk, so no GS hash names these targets",
        "mappable_logical_targets": mappable_targets,
        "mappable_logical_targets_mapped": covered,
        "rows": rows,
        "by_component": {key: value for key, value in sorted(by_component.items())},
        "unmapped_components": sorted(
            key for key, value in by_component.items()
            if value["mapped"] < value["targets"]
            and key not in STRUCTURAL_COMPONENTS),
    }
    return coverage, per_selector


def uniform_coverage(side: XboxSide, selectors: Dict[int, dict],
                     shipped: set) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """``(per_team, per_selector)`` mapped/unmapped counts over uniform pieces."""
    per_team: Dict[str, dict] = {}
    per_selector: Dict[str, dict] = {}
    for entry, meta in sorted(selectors.items()):
        ids = side.asset_ids_in(entry)
        if not ids:
            continue
        mapped = [identifier for identifier in ids if identifier in shipped]
        label = "%s/%s/%s" % (meta["abbreviation"] or "?", meta["side"] or "?",
                              meta["style"] or "(unnamed)")
        per_selector[label] = {
            "outer_index": entry,
            "pieces": len(ids),
            "mapped": len(mapped),
            "fully_mappable": len(mapped) == len(ids),
        }
        team = meta["abbreviation"] or "?"
        row = per_team.setdefault(team, {
            "team": meta["team"], "selectors": 0, "selectors_fully_mappable": 0,
            "pieces": 0, "mapped": 0, "unmapped_selectors": []})
        row["selectors"] += 1
        row["pieces"] += len(ids)
        row["mapped"] += len(mapped)
        if len(mapped) == len(ids):
            row["selectors_fully_mappable"] += 1
        elif len(row["unmapped_selectors"]) < 12:
            row["unmapped_selectors"].append(
                {"selector": label, "pieces": len(ids), "mapped": len(mapped)})
    for row in per_team.values():
        row["fully_mappable"] = (row["pieces"] > 0
                                 and row["mapped"] == row["pieces"])
    return per_team, per_selector


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

LOGICAL_PREFIX = "nfl2k5.uniform."

#: Why a candidate row was dropped by :func:`resolve_claims`.
DROP_SUPERSEDED = "superseded_by_logical_uniform_id"
DROP_SHARED = "texture_shared_by_several_uniform_targets"
DROP_CONTESTED = "several_physical_assets_claim_one_texture"


def resolve_claims(candidates: List[dict]) -> Tuple[List[dict], List[dict]]:
    """One Xbox asset per PCSX2 filename, plus a record of everything dropped.

    The export service refuses to write a file that more than one Xbox asset
    claims, because it cannot attribute the result
    (``ps2_export_service.plan_export``: "the manifest lets more than one Xbox
    asset claim ...").  So publishing a texture under *both* its physical id
    and a logical uniform id does not give a user two ways in -- it makes both
    unusable.  The rule, per filename:

    * exactly one logical claimant wins outright.  A physical id naming the
      same texture is the same pixels reached another way, and the logical id
      is the one a Studio uniform edit actually carries;
    * no logical claimant: the single physical id ships;
    * several logical claimants: those kits genuinely share one PS2 texture --
      editing one would repaint the others -- so no logical id may claim it.
      The physical id ships if there is exactly one, because a texture id is
      still an unambiguous name for the thing itself.

    Everything dropped comes back with a reason and lands in the sidecar; the
    plan's rule is that unresolved identities are evidence, never data.
    """
    by_name: Dict[str, List[str]] = {}
    for row in candidates:
        owners = by_name.setdefault(row["pcsx2_png"], [])
        if row["xbox_asset_id"] not in owners:
            owners.append(row["xbox_asset_id"])
    kept: List[dict] = []
    dropped: List[dict] = []
    for name, owners in by_name.items():
        logical = sorted(item for item in owners
                         if item.startswith(LOGICAL_PREFIX))
        physical = sorted(item for item in owners
                          if not item.startswith(LOGICAL_PREFIX))
        if len(logical) == 1:
            winner, reason = logical[0], DROP_SUPERSEDED
        elif not logical:
            winner = physical[0] if len(physical) == 1 else None
            reason = DROP_CONTESTED
        elif len(physical) == 1:
            winner, reason = physical[0], DROP_SHARED
        else:
            winner, reason = None, DROP_SHARED
        if winner is not None:
            kept.append({"pcsx2_png": name, "xbox_asset_id": winner})
        for owner in owners:
            if owner != winner:
                dropped.append({"pcsx2_png": name, "xbox_asset_id": owner,
                                "reason": reason})
    kept.sort(key=lambda item: (item["pcsx2_png"], item["xbox_asset_id"]))
    dropped.sort(key=lambda item: (item["pcsx2_png"], item["xbox_asset_id"]))
    return kept, dropped


def manifest_document(result: dict, generated: str) -> Tuple[dict, dict]:
    """``(manifest, counts)`` -- only both-hash-proved, uniquely joined rows."""
    entries = []
    fanout: Dict[str, Dict[str, int]] = {}
    for name, row in sorted(result["proved"].items()):
        ids = sorted(row["ids"])
        if len(ids) == 1 and not row.get("capped"):
            entries.append({"pcsx2_png": row.get("canonical") or name,
                            "xbox_asset_id": ids[0]})
        elif ids:
            namespace = _namespace_of(row)
            bucket = fanout.setdefault(
                namespace, {"pngs": 0, "candidate_ids_at_least": 0})
            bucket["pngs"] += 1
            bucket["candidate_ids_at_least"] += len(ids)
    uniquely_joined = len(entries)
    # A uniform edit carries a *logical* target id, not a texture id, so the
    # same proved rows are offered a second time under the logical ids the
    # Studio's uniform catalog uses.  Offered, not published: resolve_claims
    # then decides which single asset owns each filename.
    by_asset: Dict[str, List[str]] = {}
    for entry in entries:
        by_asset.setdefault(entry["xbox_asset_id"], []).append(entry["pcsx2_png"])
    logical_entries, logical_detail = logical_uniform_rows(
        result.get("side") or XboxSide(), result.get("logical_targets") or {},
        by_asset, result.get("ps2_by_id_chunk"))
    entries, dropped = resolve_claims(entries + logical_entries)
    shipped_names: Dict[str, List[str]] = {}
    for entry in entries:
        shipped_names.setdefault(entry["xbox_asset_id"], []).append(
            entry["pcsx2_png"])
    coverage, logical_by_selector = logical_coverage(logical_detail,
                                                     shipped_names)
    logical_shipped = sum(1 for entry in entries
                          if entry["xbox_asset_id"].startswith(LOGICAL_PREFIX))
    drop_reasons: Dict[str, int] = {}
    for row in dropped:
        drop_reasons[row["reason"]] = drop_reasons.get(row["reason"], 0) + 1
    identity = result["identity"]
    counts = {
        "entries": len(entries),
        "physical_entries": len(entries) - logical_shipped,
        "logical_uniform_entries": logical_shipped,
        "logical_uniform_coverage": coverage,
        "distinct_xbox_asset_ids": len({entry["xbox_asset_id"]
                                        for entry in entries}),
        "png_unique_xbox_id": uniquely_joined,
        "candidate_rows_dropped": len(dropped),
        "candidate_rows_dropped_by_reason": {
            key: drop_reasons[key] for key in sorted(drop_reasons)},
        "fanout_by_namespace": fanout,
        "png_full_identity": len(result["proved"]),
        "png_no_xbox_id": len(result["no_xbox"]),
        "png_tex0_only": len(result["tex0_only"]),
        "textures_scanned": result["textures_scanned"],
    }
    result["logical_by_selector"] = logical_by_selector
    result["claim_drops"] = dropped
    document = {
        "schema": SCHEMA,
        "disc": {
            "serial": SERIAL,
            "boot_sha256": identity.get("boot_sha256", ""),
            "content_sha256": identity.get("image_sha256", ""),
        },
        "emulator": dict(EMULATOR),
        "method": METHOD,
        "generated": generated,
        "counts": counts,
        "entries": entries,
    }
    return document, counts


# Teams whose kit is on screen in a GS dump that already exists on the rig, so
# WP7 can witness the render by dump replay instead of playing a game:
# DET (in blue) @ DAL, DEN @ SF, NE @ SF, KC @ SD, and SEA. Listed in that
# order, which is also the preference order when several kits qualify.
DUMP_TEAMS = ("DET", "DAL", "DEN", "SF", "NE", "KC", "SD", "SEA")


def _demo_rank(label: str) -> tuple:
    """Prefer the kit a dump most plainly shows: current era, away side."""
    team, _, rest = label.partition("/")
    side, _, style = rest.partition("/")
    return (
        DUMP_TEAMS.index(team) if team in DUMP_TEAMS else len(DUMP_TEAMS),
        0 if "current" in style.casefold() else 1,
        0 if side == "A" else 1,
        label,
    )


def _logical_demo(result: dict, per_selector: Dict[str, dict]) -> dict:
    """The demo question asked of the ids a real edit actually carries.

    A user's edit is a logical uniform target, so "fully mappable" has to mean
    every one of that kit's 39 components has at least one proved row -- not
    that its physical textures happen to resolve.
    """
    by_selector = result.get("logical_by_selector") or {}
    meta = {row["selector"].upper(): row
            for row in (result.get("selectors") or {}).values()
            if row.get("selector")}
    kits: Dict[str, dict] = {}
    teams: Dict[str, dict] = {}
    for selector, row in sorted(by_selector.items()):
        info = meta.get(selector, {})
        team = info.get("abbreviation") or "?"
        label = "%s/%s/%s" % (team, info.get("side") or "?",
                              info.get("style") or "(unnamed)")
        kits[label] = {
            "selector": selector,
            "components": row["targets"],
            "mapped": row["mapped"],
            "fully_mappable": row["targets"] > 0 and row["mapped"] == row["targets"],
        }
        bucket = teams.setdefault(team, {"kits": 0, "kits_fully_mappable": 0,
                                         "components": 0, "mapped": 0})
        bucket["kits"] += 1
        bucket["components"] += row["targets"]
        bucket["mapped"] += row["mapped"]
        if kits[label]["fully_mappable"]:
            bucket["kits_fully_mappable"] += 1
    ranked = sorted(
        (label for label, row in kits.items()
         if row["fully_mappable"] and label.split("/", 1)[0] in DUMP_TEAMS),
        key=_demo_rank)
    best = max(kits.items(), key=lambda item: (item[1]["mapped"], item[0]),
               default=("", {}))
    fully_mappable_teams = sorted(
        team for team, row in teams.items()
        if row["kits"] and row["kits_fully_mappable"] == row["kits"])
    return {
        "kits": kits,
        "per_team": {key: value for key, value in sorted(teams.items())},
        "fully_mappable_teams": fully_mappable_teams,
        "witnessable_teams": [team for team in DUMP_TEAMS
                              if team in fully_mappable_teams],
        "fully_mappable_kits_in_a_dump": ranked,
        "chosen_kit": ranked[0] if ranked else "",
        "best_covered_kit": {"kit": best[0], **best[1]} if best[0] else {},
    }


#: Said when no kit has a shipped row for every one of its eight mappable
#: components, which is the state the sole-claimant rule leaves the disc in.
NO_FULLY_MAPPABLE_KIT = (
    "no kit has a shipped row for all eight of its mappable components. The "
    "PS2 disc shares torso, sleeve, pants and helmet art across a team's era "
    "variants -- three Bills away kits carry one sleeve texture -- so those "
    "textures belong to no single logical target and the export service would "
    "refuse to attribute a file written under one. WP7 should witness the "
    "components that did map on the kit named in logical.best_covered_kit, "
    "and treat a fully-mappable kit as work for a later slice that resolves "
    "shared art rather than as a blocker here."
)

#: Prose for each :func:`resolve_claims` outcome, for the sidecar.
DROP_REASON_TEXT = {
    DROP_SUPERSEDED:
        "the texture is also named by a logical uniform target, and the "
        "logical id is the one a Studio uniform edit carries; publishing both "
        "would make the export service call the file unattributable and skip "
        "it under either name",
    DROP_SHARED:
        "several uniform kits share this one PS2 texture, so no single logical "
        "target owns it; editing one kit would repaint the others",
    DROP_CONTESTED:
        "more than one physical Xbox asset resolves to this filename",
}


def sidecar_document(result: dict, generated: str, counts: dict,
                     shipped: Optional[set] = None) -> dict:
    reasons: Dict[str, dict] = {}
    fanout_rows: Dict[str, List[dict]] = {}
    for name, row in sorted(result["proved"].items()):
        ids = sorted(row["ids"])
        if len(ids) <= 1 and not row.get("capped"):
            continue
        namespace = _namespace_of(row)
        bucket = reasons.setdefault(
            "fanout:" + namespace,
            {"pngs": 0, "candidate_ids_at_least": 0,
             "reason": "the identity is proved but the name resolves to more "
                       "than one Xbox asset in the %s namespace" % namespace})
        bucket["pngs"] += 1
        bucket["candidate_ids_at_least"] += len(ids)
        if len(fanout_rows.setdefault(namespace, [])) < 20:
            fanout_rows[namespace].append(
                {"pcsx2_png": name,
                 "candidate_ids": ("%d+" % len(ids) if row.get("capped")
                                   else len(ids)),
                 "examples": ids[:4]})
    drops = result.get("claim_drops") or []
    drop_rows: Dict[str, List[dict]] = {}
    drop_names: Dict[str, set] = {}
    for row in drops:
        bucket = reasons.setdefault(
            "claim:" + row["reason"],
            {"pngs": 0, "rows": 0,
             "reason": DROP_REASON_TEXT.get(row["reason"], "")})
        bucket["rows"] += 1
        # ``rows`` counts dropped (name, asset) claims; ``pngs`` counts the
        # distinct filenames they touch, which is the unit every other reason
        # in this block is measured in.
        drop_names.setdefault(row["reason"], set()).add(row["pcsx2_png"])
        examples = drop_rows.setdefault(row["reason"], [])
        if len(examples) < 20:
            examples.append({"pcsx2_png": row["pcsx2_png"],
                             "xbox_asset_id": row["xbox_asset_id"]})
    for reason, names in drop_names.items():
        reasons["claim:" + reason]["pngs"] = len(names)
    reasons["tex0_only"] = {
        "pngs": len(result["tex0_only"]),
        "reason": "the level-0 pixel hash reproduces but no CLUT candidate "
                  "matches the palette hash in the filename; the identity is "
                  "unproved and never ships",
    }
    reasons["no_xbox_id"] = {
        "pngs": len(result["no_xbox"]),
        "reason": "both hashes reproduce but the PS2 resource name has no "
                  "counterpart on the Xbox disc",
    }
    corpus = result["corpus"]
    unexplained = sorted(corpus.names - set(result["proved"])
                         - set(result["tex0_only"])) if corpus else []
    divergence = result.get("name_divergence") or {}
    if divergence:
        reasons["tcc_bit_divergence"] = {
            "pngs": len(divergence),
            "reason": "the reference pack spells these identities without the "
                      "classic TCC bit (bit 14 of the property word); the "
                      "manifest publishes the computed name, which always has "
                      "it set, because a pack that mixed both conventions "
                      "would load the wrong art under ClassicTextureNames=true",
        }
    reasons["unexplained"] = {
        "pngs": len(unexplained),
        "reason": "a canonical identity in the reference pack that no disc "
                  "texture reproduces under any layout; open, unbudgeted",
    }
    teams, per_selector = uniform_coverage(
        result.get("side") or XboxSide(), result.get("selectors") or {},
        shipped or set())
    mappable = sorted(team for team, row in teams.items()
                      if row.get("fully_mappable"))
    witnessable = [team for team in mappable if team in DUMP_TEAMS]
    # A whole team's era catalogue is a high bar; the demo needs one kit, so
    # also report the best single selector among the teams a dump can witness.
    dump_selectors = {
        label: row for label, row in per_selector.items()
        if label.split("/", 1)[0] in DUMP_TEAMS and row["fully_mappable"]}
    dump_ranked = sorted(dump_selectors, key=_demo_rank)
    logical = _logical_demo(result, per_selector)
    return {
        "schema": SIDECAR_SCHEMA,
        "disc": {"serial": SERIAL,
                 "boot_sha256": result["identity"].get("boot_sha256", ""),
                 "content_sha256": result["identity"].get("image_sha256", "")},
        "emulator": dict(EMULATOR),
        "method": METHOD,
        "generated": generated,
        "counts": counts,
        "reasons": reasons,
        "fanout_examples": fanout_rows,
        "claim_examples": {key: drop_rows[key] for key in sorted(drop_rows)},
        "unexplained_sample": unexplained[:50],
        "tcc_bit_divergence": {key: divergence[key]
                               for key in sorted(divergence)},
        "demo_team": {
            "criteria": [
                "every mappable component of the kit has a shipped manifest "
                "row under the logical id a Studio edit actually carries",
                "the kit is on screen in a GS dump that already exists on the "
                "rig, so the render can be witnessed by dump replay",
            ],
            "method": "the 634 Xbox uniform selectors and their 39 components "
                      "come from the hash-pinned compatibility reports; a "
                      "component is mapped when the manifest names at least "
                      "one PCSX2 replacement for its logical id. Thirty-one of "
                      "the 39 (the ten digits of each family, plus the "
                      "nameplate) have no PS2 counterpart texture at all and "
                      "are excluded from 'fully mappable' -- see "
                      "counts.logical_uniform_coverage",
            "dump_teams": list(DUMP_TEAMS),
            "chosen": (logical["chosen_kit"].split("/", 1)[0]
                       if logical["chosen_kit"] else ""),
            "chosen_kit": logical["chosen_kit"],
            "chosen_reason": ("" if logical["chosen_kit"] else
                              NO_FULLY_MAPPABLE_KIT),
            "fully_mappable_teams": logical["fully_mappable_teams"],
            "fully_mappable_and_witnessable": logical["witnessable_teams"],
            "logical": logical,
            "physical": {
                "note": "the texture-level view: which of a selector's tset "
                        "children resolve to a unique manifest row. Kept as "
                        "supporting evidence; the logical view above is what "
                        "an export actually needs",
                "fully_mappable_teams": mappable,
                "fully_mappable_and_witnessable": witnessable,
                "chosen_selector": dump_ranked[0] if dump_ranked else "",
                "witnessable_selectors_fully_mappable": sorted(dump_selectors),
                "per_team": teams,
                "per_selector": per_selector,
            },
        },
    }


def write_json(path: str, document: dict) -> None:
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    # Not Path.write_text(newline=...): that keyword is 3.10+ and this tool
    # targets 3.9.
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------

def oracle(iso_path: str, results_path: str, jobs: int = 0, limit: int = 0,
           progress=None) -> dict:
    """Recompute every hash a reference run recorded and compare, one by one."""
    expected: Dict[tuple, dict] = {}
    opener = gzip.open if results_path.endswith(".gz") else open
    with opener(results_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("status") not in (None, "ok"):
                continue
            expected[(row["src"], row["entry"], row["chunk"], row["idx"])] = row

    checked = 0
    matched = 0
    missing_records = 0
    extra_records = 0
    mismatches: List[str] = []
    seen = set()
    for record in stream_textures(iso_path, jobs, limit, progress,
                                  hash_image=False):
        if "__identity__" in record:
            continue
        key = (record["src"], record["entry"], record["chunk"], record["idx"])
        reference = expected.get(key)
        if reference is None:
            extra_records += 1
            continue
        seen.add(key)
        for group in ("l0", "clut"):
            for label, value in reference[group].items():
                checked += 1
                got = record[group].get(label)
                if got is not None and "%x" % got == value:
                    matched += 1
                elif len(mismatches) < 20:
                    mismatches.append("%s %s/%s want=%s got=%s"
                                      % (key, group, label, value,
                                         "%x" % got if got is not None else "<absent>"))
    missing_records = len(expected) - len(seen) if not limit else 0
    return {
        "reference_records": len(expected),
        "records_reproduced": len(seen),
        "records_missing": missing_records,
        "records_extra": extra_records,
        "hashes_checked": checked,
        "hashes_matched": matched,
        "mismatch_examples": mismatches,
    }


# ---------------------------------------------------------------------------
# Self-test: a synthetic PS2 image, no disc
# ---------------------------------------------------------------------------

def _pattern(size: int, salt: int) -> bytes:
    out = bytearray(size)
    value = (salt * 2654435761 + 1) & 0xFFFFFFFF
    for i in range(size):
        out[i] = value >> 24 & 0xFF
        value = (value * 1103515245 + 12345) & 0xFFFFFFFF
    return bytes(out)


def _make_tex0(psm: int, tw: int, th: int, tbw: int, cbp: int, tcc: int = 1) -> int:
    return (tbw << 14) | (psm << 20) | (tw << 26) | (th << 30) | (tcc << 34) | (cbp << 37)


def _descriptor(tex0: int, image_offset: int, width: int, height: int,
                mip_tbps: Sequence[int] = (), clut_override: int = 0) -> bytes:
    out = bytearray(TXTR_DESCRIPTOR_SIZE)
    struct.pack_into("<Q", out, 0, tex0)
    register1 = 0
    register2 = 0
    for index, tbp in enumerate(mip_tbps[:3]):
        register1 |= (tbp & 0x3FFF) << (20 * index)
    for index, tbp in enumerate(mip_tbps[3:6]):
        register2 |= (tbp & 0x3FFF) << (20 * index)
    struct.pack_into("<4I", out, 8, register1 & 0xFFFFFFFF, register1 >> 32,
                     register2 & 0xFFFFFFFF, register2 >> 32)
    struct.pack_into("<I", out, 0x18, image_offset)
    struct.pack_into("<I", out, 0x28, clut_override)
    struct.pack_into("<HH", out, 0x2C, width, height)
    return bytes(out)


# Public names for the three fixture builders above.  A game module's own
# synthetic source lays its bytes out with these rather than copying the TEX0
# and descriptor packing, so a fixture and this parser cannot drift apart.
pattern_bytes = _pattern
make_tex0 = _make_tex0
descriptor_bytes = _descriptor


def _c32_upload(vram: bytes, width32: int) -> bytes:
    """Forward direction of the c32 layout: VRAM image -> the linear region."""
    words = len(vram) // 4
    pages_wide = _c32_check(words, width32)
    out = bytearray(len(vram))
    for slot in range(words):
        source = c32_source_words(slot, width32, pages_wide)
        out[source * 4:source * 4 + 4] = vram[slot * 4:slot * 4 + 4]
    return bytes(out)


def selftest() -> int:
    """Round-trip hash -> name on a synthetic image; no disc, no pixels kept."""
    failures = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        if not condition:
            failures += 1
            print("FAIL %s %s" % (label, detail))

    # -- 1. linear PSMT8, one level -----------------------------------------
    width, height = 64, 32
    image = _pattern(width * height, 1)
    palette = _pattern(1024, 2)
    video = image + palette
    tex0 = _make_tex0(PSMT8, 6, 5, width // 64, len(image) // 256)
    record = analyse(_descriptor(tex0, 0, width, height), video, True)
    check("psmt8-linear-present", record is not None and "lin" in record["l0"])
    expected = xxh3_64(swizzle8_blocks(image, width, height))
    check("psmt8-linear-hash", record["l0"]["lin"] == expected,
          "%x != %x" % (record["l0"]["lin"], expected))
    clut = xxh3_64(permute_clut(palette, SWAP34, "swap34"))
    check("psmt8-linear-clut", record["clut"].get("cbp/swap34") == clut)
    bits = texture_bits(PSMT8, 6, 5, 1)
    name = replacement_name(record["l0"]["lin"], clut, bits)
    parsed_bits, parsed_clut = parse_replacement_name(name)
    check("psmt8-name-roundtrip", parsed_bits == bits and parsed_clut == clut, name)
    check("psmt8-bit14", bits & 0x4000 == 0x4000, "%08x" % bits)

    # -- 2. c32-mipped PSMT8 ------------------------------------------------
    width, height = 64, 32
    level0 = _pattern(width * height, 3)
    vram = bytearray(8192)                       # one PSMCT32 page
    tbw = max(1, width // 64)
    for index, start in enumerate(vram_block_offsets(width, height, tbw, PSMT8)):
        vram[start:start + 256] = swizzle8_blocks(
            level0, width, height)[index * 256:(index + 1) * 256]
    palette = _pattern(1024, 4)
    clut_at = 4096
    stored = permute_clut(palette, VRAMREAD, "vramread")
    vram[clut_at:clut_at + 1024] = stored
    region = _c32_upload(bytes(vram), 64)
    tex0 = _make_tex0(PSMT8, 6, 5, tbw, clut_at // 256)
    record = analyse(_descriptor(tex0, 0, width, height, mip_tbps=(1, 2, 3)),
                     region, False)
    check("c32-present", record is not None and "c32" in record["l0"])
    check("c32-mips", record["mips"] == 4, str(record["mips"]))
    expected = xxh3_64(swizzle8_blocks(level0, width, height))
    check("c32-hash", record["l0"]["c32"] == expected,
          "%x != %x" % (record["l0"].get("c32", 0), expected))
    check("c32-clut", record["clut"].get("c32cbp/raw") == xxh3_64(stored))
    name = replacement_name(record["l0"]["c32"], record["clut"]["c32cbp/raw"],
                            texture_bits(PSMT8, 6, 5, 1))
    check("c32-name", parse_replacement_name(name)[0] == texture_bits(PSMT8, 6, 5, 1))

    # -- 3. linear PSMT4 ----------------------------------------------------
    width, height = 64, 32
    indices = bytes(value & 0x0F for value in _pattern(width * height, 5))
    packed = bytes(map(int.__or__, indices[0::2],
                       indices[1::2].translate(_SHIFT_NIBBLE)))
    palette = _pattern(64, 6)
    video = packed + palette
    tex0 = _make_tex0(PSMT4, 6, 5, max(1, width // 128), len(packed) // 256)
    record = analyse(_descriptor(tex0, 0, width, height), video, True)
    check("psmt4-present", record is not None and "lin" in record["l0"])
    check("psmt4-unpack", unpack4(packed, width, height) == indices)
    expected = xxh3_64(swizzle4_blocks(indices, width, height))
    check("psmt4-hash", record["l0"]["lin"] == expected,
          "%x != %x" % (record["l0"]["lin"], expected))
    check("psmt4-clut", record["clut"].get("cbp/raw") == xxh3_64(palette))
    name = replacement_name(record["l0"]["lin"], record["clut"]["cbp/raw"],
                            texture_bits(PSMT4, 6, 5, 1))
    check("psmt4-name", name.endswith("-%08x.png" % texture_bits(PSMT4, 6, 5, 1)))

    # -- 4. the tables are permutations ------------------------------------
    check("columnTable8", sorted(v for row in COLUMN_TABLE8 for v in row)
          == list(range(256)))
    check("columnTable4", sorted(v for row in COLUMN_TABLE4 for v in row)
          == list(range(512)))
    check("swap34-perm", sorted(SWAP34) == list(range(256)))
    check("vramread-perm", sorted(VRAMREAD) == list(range(256)))

    # -- 5. the c32 inverse really inverts ----------------------------------
    round_trip = all(
        c32_source_words(slot, 64, 1) < 2048 for slot in range(2048))
    check("c32-inverse-range", round_trip)
    check("c32-inverse-bijection",
          sorted(c32_source_words(slot, 64, 1) for slot in range(2048))
          == list(range(2048)))

    # -- 6. the block permutations really invert -----------------------------
    # A decoder reads the hash input backwards to get pixels, so the inverse is
    # load-bearing in exactly the way the forward direction is.
    width, height = 64, 32
    image8 = _pattern(width * height, 7)
    check("unswizzle8", unswizzle8_blocks(
        swizzle8_blocks(image8, width, height), width, height) == image8)
    indices4 = bytes(value & 0x0F for value in _pattern(width * height, 8))
    check("unswizzle4", unswizzle4_blocks(
        swizzle4_blocks(indices4, width, height), width, height) == indices4)
    check("level_indices8", level_indices(
        PSMT8, level_bytes(PSMT8, image8, width, height), width, height) == image8)
    check("level_indices4", level_indices(
        PSMT4, level_bytes(PSMT4, indices4, width, height), width, height) == indices4)
    small = _pattern(8 * 8, 9)
    check("level_indices-small-is-identity",
          level_indices(PSMT8, level_bytes(PSMT8, small, 8, 8), 8, 8) == small)

    if failures:
        print("NFL2K5_PS2_TEXTURE_MAP_SELFTEST_FAIL %d" % failures)
        return 1
    print("NFL2K5_PS2_TEXTURE_MAP_SELFTEST_PASS")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _progress(done: int, total: int) -> None:
    sys.stderr.write("\r  entries %d/%d" % (done, total))
    sys.stderr.flush()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--iso")
    parser.add_argument("--xbox-inventory")
    parser.add_argument("--pack-hashes")
    parser.add_argument("--uniform-reports",
                        help="directory holding the hash-pinned uniform "
                             "compatibility reports (reports/assets); they say "
                             "which chunk each logical uniform component lives "
                             "in, so logical targets can be mapped too")
    parser.add_argument("--uniform-selectors",
                        help="reports/assets/uniform_texture_sharing.v2.json; "
                             "names the 634 Xbox uniform selectors so the "
                             "sidecar can answer the demo-team question")
    parser.add_argument("--manifest")
    parser.add_argument("--sidecar")
    parser.add_argument("--hashes-out")
    parser.add_argument("--hashes-in",
                        help="replay a --hashes-out cache instead of reading "
                             "the disc; the join and the outputs are rebuilt "
                             "from it in seconds")
    parser.add_argument("--oracle")
    parser.add_argument("--summary")
    parser.add_argument("--jobs", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.iso and not args.hashes_in:
        parser.error("--iso is required unless --selftest or --hashes-in")
    progress = None if args.quiet else _progress

    if args.oracle:
        report = oracle(args.iso, args.oracle, args.jobs, args.limit, progress)
        if not args.quiet:
            sys.stderr.write("\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if (report["hashes_checked"] == report["hashes_matched"]
                     and report["records_missing"] == 0) else 1

    result = build(args.iso, args.xbox_inventory, args.pack_hashes, args.jobs,
                   args.limit, args.hashes_out, progress,
                   args.uniform_selectors, args.uniform_reports,
                   args.hashes_in)
    if not args.quiet:
        sys.stderr.write("\n")
    generated = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    document, counts = manifest_document(result, generated)
    shipped = {row["xbox_asset_id"] for row in document["entries"]}
    if args.manifest:
        write_json(args.manifest, document)
    if args.sidecar and result["corpus"] is not None:
        write_json(args.sidecar,
                   sidecar_document(result, generated, counts, shipped))
    summary = {
        "textures_scanned": result["textures_scanned"],
        "xbox_rows": result["xbox_rows"],
        "manifest_entries": counts["entries"],
        "png_full_identity": counts["png_full_identity"],
        "png_tex0_only": counts["png_tex0_only"],
        "png_no_xbox_id": counts["png_no_xbox_id"],
        "bits_checked": result["bits_checked"],
        "bits_mismatched": result["bits_mismatched"],
        "name_divergences": len(result["name_divergence"]),
        "fanout_by_namespace": counts["fanout_by_namespace"],
        "physical_entries": counts["physical_entries"],
        "logical_uniform_entries": counts["logical_uniform_entries"],
        "png_unique_xbox_id": counts["png_unique_xbox_id"],
        "distinct_xbox_asset_ids": counts["distinct_xbox_asset_ids"],
        "candidate_rows_dropped": counts["candidate_rows_dropped"],
        "candidate_rows_dropped_by_reason":
            counts["candidate_rows_dropped_by_reason"],
        "logical_uniform_coverage": counts["logical_uniform_coverage"],
    }
    if args.summary:
        write_json(args.summary, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
