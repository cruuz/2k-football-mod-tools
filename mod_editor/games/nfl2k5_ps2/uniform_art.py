"""ESPN NFL 2K5 (PS2) uniform art: the disc's own textures in, a PCSX2 pack out.

What this lane is
-----------------

The M1 exporter (``mod_editor/core/ps2_export_service.py``) writes a PCSX2
replacement pack from an *Xbox* project: the user edits on the Xbox disc and
the shipped map names the PS2 texture their edit replaces.  This lane is the
other way in.  It opens the user's own PlayStation 2 image read-only, walks the
634 uniform packages, decodes each indexed texture to a PNG, and lets an edit be
made against the art that is actually on that disc.  The pack it writes is the
same folder, under the same names, checked by the same independent verifier.

Nothing is written back to the disc: PCSX2 overlays the pack at draw time.  The
registry classifies this row ``extract-only`` for exactly that reason.

How a texture is decoded
------------------------

Every step is ``tools/nfl2k5_ps2_texture_map.py``'s, run backwards.  That tool
already decodes far enough to *hash* a texture -- TEX0 fields, the PSMT8/PSMT4
block swizzle, the linear / VRAM / one-shot-PSMCT32 (``c32``) layouts, and the
CLUT permutations -- and it is what produced the shipped map.  Reusing it, and
adding only the inverse permutations beside the forward ones, means a decode and
an identity can never disagree about what the bytes are.  See
``docs/product/PS2_M1_PLAN.md`` §4 WP1 for the algorithm and
``docs/product/PS2_UNIFORM_ART.md`` for what this lane claims and refuses.

Which layout a texture uses is not written on the disc, so the hasher tries all
of them.  This lane resolves it two ways, in this order:

1. **The shipped map.**  When one of a texture's candidate ``(level-0, CLUT)``
   routes produces a filename the map carries, that route is the route PCSX2's
   own hash agreed with, and the map's ``xbox_asset_id`` is the id a pack may be
   attributed to.  841 of the disc's 38,674 uniform textures resolve this way.
2. **The documented rule**, for the rest: mip chains take the ``c32`` route and
   single-level textures the linear one, with the CLUT taken in the preference
   order below.  Measured against the 841 the map proves, the rule picks the
   same route for 839 -- so it is good enough to *preview* a texture, and not
   good enough to name a file a pack claims.  A target the map does not prove
   is catalogued, decoded and exported as a PNG, and refused for packing.

The lane's own map may be overridden per source: a disc image accompanied by
``<image>.map.json`` uses that file instead of the shipped one.  That is how the
synthetic fixture supplies identities for textures that exist nowhere else.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
import zlib

from mod_editor.games.contract import (
    Artifact,
    Catalogue,
    Edit,
    Plan,
    Receipt,
    Refusal,
    Target,
    Verdict,
    require,
    EncodedArt,
    Field,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402
import nfl2k5_ps2_replacement_pack_verify as pack_verify  # noqa: E402
import nfl2k5_ps2_texture_map as texture_map  # noqa: E402
import nfl2k5_ps2_unif_color_target_catalog as colour_catalog  # noqa: E402

LANE_ID = "uniforms.art"
CAPABILITY_ID = "nfl2k5ps2.uniforms.replacement_pack_export"
SURFACE = "uniforms"
PAGE = "uniforms"
CLASSIFICATION = "extract-only"
SERIAL = inventory_lib.SERIAL

CATALOGUE_SCHEMA = "nfl2k5_ps2_uniform_art_catalogue/v1"
RECIPE_SCHEMA = "nfl2k5_ps2_uniform_art_recipe/v1"
PACK_SCHEMA = "nfl2k5_ps2_uniform_art_pack/v1"
EDITS_SCHEMA = "nfl2k5_ps2_uniform_art_edits/v1"
KITS_SCHEMA = "nfl2k5_ps2_uniform_kits/v1"

#: Where the shipped PS2 -> Xbox identity map lives, and the per-source override.
DEFAULT_MAP = ROOT / "mod_editor" / "data" / "nfl2k5-xbox-map.v1.json"
MAP_SIDECAR_SUFFIX = ".map.json"
MAP_SCHEMA = "nfl2k5_ps2_to_xbox_texture_map/v1"
#: Selector -> team / side / kit, beside this file so a kit has a name without
#: the research sidecar it was extracted from.
KITS_FILE = HERE / "uniform_kits.v1.json"

MAX_PNG_BYTES = 64 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: PS2 CLUT alpha runs 0..0x80 with 0x80 fully opaque, so a decoded PNG scales
#: it into 0..255 rather than leaving every texture half transparent.
PS2_ALPHA_OPAQUE = 0x80


# --------------------------------------------------------------------------
# Contract types this lane needs before the contract has them.
#
# RC86 work package A1 adds ``ArtLane``, ``EncodedArt`` and ``Field`` to
# mod_editor/games/contract.py on another branch.  These two dataclasses move
# --------------------------------------------------------------------------


def _target_with_fields(fields: Tuple[Field, ...], **kwargs: Any) -> Target:
    """A :class:`Target` carrying ``fields``, before and after A1 lands.

    ``Target`` is a frozen dataclass; once the contract declares ``fields`` this
    is the plain constructor call.  Until then the attribute is set the way a
    frozen dataclass sets its own -- so the shell reads ``target.fields`` today
    and nothing changes when the field becomes real.
    """

    try:
        return Target(fields=fields, **kwargs)  # type: ignore[call-arg]
    except TypeError:
        target = Target(**kwargs)
        object.__setattr__(target, "fields", fields)
        return target


PNG_FIELD = Field(
    key="png",
    kind="png",
    label="Texture",
    help=("The replacement image, as a PNG. Give the texture's own size, or an "
          "exact whole-number multiple of it: PCSX2 scales a replacement but "
          "cannot change its shape."),
)


# --------------------------------------------------------------------------
# Small helpers: digests, PNG in and out, all standard library.
# --------------------------------------------------------------------------

def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def write_rgba_png(pixels: bytes, width: int, height: int) -> bytes:
    """An 8-bit RGBA, non-interlaced PNG.  No Pillow: this runs everywhere."""

    require(len(pixels) == width * height * 4,
            f"an RGBA image of {width}x{height} needs {width * height * 4} bytes, not {len(pixels)}")
    stride = width * 4
    raw = b"".join(b"\x00" + pixels[row * stride:(row + 1) * stride] for row in range(height))
    return (PNG_SIGNATURE
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw, 6))
            + _png_chunk(b"IEND", b""))


def png_header(payload: bytes) -> Optional[Tuple[int, int, int, int, int]]:
    """``(width, height, bit_depth, colour_type, interlace)``, or None if not a PNG."""

    if (len(payload) < 33 or payload[:8] != PNG_SIGNATURE
            or payload[12:16] != b"IHDR"):
        return None
    width, height, depth, colour, _compress, _filter, interlace = struct.unpack_from(
        ">IIBBBBB", payload, 16)
    if not (0 < width <= 16_384 and 0 < height <= 16_384):
        return None
    return int(width), int(height), int(depth), int(colour), int(interlace)


# --------------------------------------------------------------------------
# Which route decodes a texture, when the map does not say.
# --------------------------------------------------------------------------

#: Level-0 layouts in the order the M1 plan measured them: a mip chain is a
#: one-shot PSMCT32 upload far more often than not, a single level never is.
_LEVEL_ORDER_MIPPED = ("c32", "c32w", "lin", "vram")
_LEVEL_ORDER_FLAT = ("lin", "vram", "c32", "c32w")

#: CLUT sources x permutations, most-observed first.  ``analyse`` emits every
#: one that is in range; this picks between them when the map is silent.
_CLUT_ORDER = (
    "c32cbp/vramread", "c32wcbp/vramread", "c32cbp/raw", "c32wcbp/raw",
    "ovr/swap34", "cbp/swap34", "afterlin/swap34", "afterl0/swap34", "tail/swap34",
    "ovr/raw", "cbp/raw", "afterlin/raw", "afterl0/raw", "tail/raw",
    "ovr/vramread", "cbp/vramread", "afterlin/vramread", "afterl0/vramread",
    "tail/vramread",
)

_CLUT_PERMUTATIONS = {
    "swap34": (texture_map.SWAP34, "swap34"),
    "vramread": (texture_map.VRAMREAD, "vramread"),
    "vramread4": (texture_map.VRAMREAD4, "vramread4"),
}


def rule_routes(record: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """``(level0_route, clut_route)`` the documented rule picks for one texture."""

    order = _LEVEL_ORDER_MIPPED if int(record["mips"]) > 1 else _LEVEL_ORDER_FLAT
    level = next((name for name in order if name in record["l0"]), None)
    clut = next((name for name in _CLUT_ORDER if name in record["clut"]), None)
    return level, clut


def candidate_names(record: Mapping[str, Any]) -> Dict[str, Tuple[str, str]]:
    """``{pcsx2 filename: (level0 route, clut route)}`` for one texture."""

    fields = texture_map.tex0_fields(int(record["tex0"], 16))
    bits = texture_map.texture_bits(fields["PSM"], fields["TW"], fields["TH"], fields["TCC"])
    out: Dict[str, Tuple[str, str]] = {}
    for level_route, level_hash in record["l0"].items():
        for clut_route, clut_hash in record["clut"].items():
            name = texture_map.replacement_name(level_hash, clut_hash, bits)
            out.setdefault(name, (level_route, clut_route))
    return out


# --------------------------------------------------------------------------
# Decoding one texture to RGBA.
# --------------------------------------------------------------------------

def _palette(video: bytes, region: bytes, descriptor: bytes, fields: Mapping[str, int],
             image_offset: int, level0_bytes: int, linear_total: int,
             palette_bytes: int, clut_route: str) -> bytes:
    """The CLUT in palette-index order, for one of ``analyse``'s clut routes."""

    source, _, permutation = clut_route.partition("/")
    clut_override = struct.unpack_from("<I", descriptor, 0x28)[0]
    if source in ("c32cbp", "c32wcbp"):
        width32 = 64 if source == "c32cbp" else max(64, fields["TBW"] * 32)
        raw = texture_map.c32_clut_bytes(region, fields["CBP"] * 256, palette_bytes, width32)
    else:
        start = {
            "ovr": clut_override,
            "cbp": image_offset + fields["CBP"] * 256,
            "afterlin": image_offset + linear_total,
            "afterl0": image_offset + level0_bytes,
            "tail": len(video) - palette_bytes,
        }.get(source)
        if start is None:
            raise Refusal(f"{clut_route!r} is not a CLUT route this decoder knows.")
        if start < 0 or start + palette_bytes > len(video):
            raise Refusal(f"the {source} CLUT of this texture is not inside its own payload.")
        raw = video[start:start + palette_bytes]
    if permutation == "raw":
        return raw
    order, name = _CLUT_PERMUTATIONS[permutation]
    return texture_map.permute_clut(raw, order, name)


def decode_level0_rgba(payload: Mapping[str, Any], level_route: str,
                       clut_route: str) -> Tuple[bytes, int, int]:
    """``(rgba, width, height)`` for level 0 of one TXTR, from the disc's bytes."""

    descriptor = payload["descriptor"]
    video = payload["video"]
    fields = texture_map.tex0_fields(struct.unpack_from("<Q", descriptor, 0)[0])
    psm = fields["PSM"]
    if psm not in (texture_map.PSMT8, texture_map.PSMT4):
        raise Refusal(f"PSM 0x{psm:02x} is not an indexed format this lane decodes.")
    width, height = struct.unpack_from("<HH", descriptor, 0x2C)
    image_offset = struct.unpack_from("<I", descriptor, 0x18)[0]
    bits_per_pixel = 8 if psm == texture_map.PSMT8 else 4
    palette_bytes = 1024 if psm == texture_map.PSMT8 else 64
    pow2 = (1 << fields["TW"], 1 << fields["TH"])
    _levels, linear_total = texture_map.level_count_and_linear_size(
        width, height, bits_per_pixel, descriptor)
    level0_bytes = (width * height * bits_per_pixel) // 8

    end = payload.get("region_end")
    end = end if end and end > image_offset else len(video)
    region = video[image_offset:end]
    region = region[: (len(region) // 256) * 256]

    if level_route == "lin":
        raw = video[image_offset:image_offset + level0_bytes]
        if len(raw) < level0_bytes:
            raise Refusal("this texture's level 0 runs past the end of its payload.")
        indices = raw if psm == texture_map.PSMT8 else texture_map.unpack4(raw, width, height)
        if (width, height) != pow2:
            if width < pow2[0] or height < pow2[1]:
                raise Refusal("this texture is smaller than the size its TEX0 declares.")
            indices = b"".join(indices[row * width:row * width + pow2[0]]
                               for row in range(pow2[1]))
            width, height = pow2
    elif level_route == "vram":
        blocks = texture_map.vram_level_bytes(
            video, image_offset, width, height, fields["TBW"], psm)
        indices = texture_map.level_indices(psm, blocks, width, height)
    elif level_route in ("c32", "c32w"):
        width32 = 64 if level_route == "c32" else max(64, fields["TBW"] * 32)
        blocks = texture_map.c32_level_bytes(
            region, width, height, fields["TBW"], psm, width32)
        indices = texture_map.level_indices(psm, blocks, width, height)
    else:
        raise Refusal(f"{level_route!r} is not a level-0 route this decoder knows.")

    palette = _palette(video, region, descriptor, fields, image_offset, level0_bytes,
                       linear_total, palette_bytes, clut_route)
    lookup = bytearray(len(palette))
    for entry in range(len(palette) // 4):
        red, green, blue, alpha = palette[entry * 4:entry * 4 + 4]
        lookup[entry * 4:entry * 4 + 4] = bytes(
            (red, green, blue, min(255, (alpha * 255) // PS2_ALPHA_OPAQUE)))
    rgba = bytearray(width * height * 4)
    for position, index in enumerate(indices[:width * height]):
        rgba[position * 4:position * 4 + 4] = lookup[index * 4:index * 4 + 4]
    return bytes(rgba), width, height


# --------------------------------------------------------------------------
# What a texture is, in a user's words.
# --------------------------------------------------------------------------

_PART_BY_PREFIX = (
    ("jersey_numbers", "numbers", "jersey numbers"),
    ("helmet_numbers", "numbers", "helmet numbers"),
    ("arm_numbers", "numbers", "arm numbers"),
    ("jersey", "torso", "jersey"),
    ("pants", "pants", "pants"),
    ("sleeve", "sleeve", "sleeve"),
    ("longsleeve", "sleeve", "long sleeve"),
    ("socks", "socks", "socks"),
    ("helmet", "helmet", "helmet"),
    ("names", "nameplate", "nameplate strip"),
    ("logo", "logo", "team logo"),
    ("chiclet", "presentation", "chiclet"),
    ("flipchip", "presentation", "coin-toss chip"),
    ("splayer", "presentation", "player card"),
    ("glove", "equipment", "gloves"),
    ("shoes", "equipment", "shoes"),
    ("elbowpad", "equipment", "elbow pad"),
    ("wristband", "equipment", "wristband"),
)


def part_of(name: str) -> Tuple[str, str, str]:
    """``(part, description, variant)`` for one TXTR name (``jersey00_mud``)."""

    lowered = (name or "").strip().lower()
    variant = "mud" if lowered.endswith("_mud") else ""
    stem = lowered[:-4] if variant else lowered
    for prefix, part, description in _PART_BY_PREFIX:
        if stem.startswith(prefix):
            return part, description, variant
    return "other", stem or "unnamed texture", variant


_SIDE_NAMES = {"H": "home", "A": "away"}


def describe_selector(selector: str) -> str:
    """``uniform package 18 · home · variant 0`` -- the module's own vocabulary."""

    if len(selector) >= 4 and selector[:2].isalnum() and selector[2] in _SIDE_NAMES:
        return (f"uniform package {selector[:2]} · {_SIDE_NAMES[selector[2]]} · "
                f"variant {selector[3:]}")
    return f"uniform record {selector}"


def load_kits(path: Path = KITS_FILE) -> Dict[str, Dict[str, str]]:
    """``{selector: {abbreviation, team, side, kit}}``; empty when unavailable."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if document.get("schema") != KITS_SCHEMA:
        return {}
    rows = document.get("selectors")
    if not isinstance(rows, dict):
        return {}
    return {str(key).upper(): dict(value) for key, value in rows.items()
            if isinstance(value, dict)}


# --------------------------------------------------------------------------
# The identity map.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class IdentityMap:
    """The shipped PS2 -> Xbox map, indexed by filename, plus its provenance."""

    path: Path
    sha256: str
    by_name: Mapping[str, str]
    provenance: Mapping[str, Any]

    @property
    def entries(self) -> int:
        return len(self.by_name)


def map_for_source(source: Path, override: Optional[Path] = None) -> Path:
    """Which identity map names ``source``'s textures.

    A disc image may be accompanied by ``<image>.map.json``; when one is there
    it wins.  That is how a synthetic fixture -- whose textures exist on no
    retail disc -- supplies its own identities without a special case in the
    catalogue.
    """

    if override is not None:
        return Path(override)
    sidecar = Path(str(source) + MAP_SIDECAR_SUFFIX)
    return sidecar if sidecar.is_file() else DEFAULT_MAP


def load_identity_map(path: Path) -> IdentityMap:
    path = Path(path)
    try:
        payload = path.read_bytes()
        document = json.loads(payload.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refusal(
            f"the texture identity map {path} cannot be read: {exc}. "
            f"Reinstall the map at {DEFAULT_MAP.name} or pass one with --map."
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != MAP_SCHEMA:
        raise Refusal(f"{path} is not a {MAP_SCHEMA} document.")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise Refusal(f"{path} carries no entry list.")
    by_name: Dict[str, str] = {}
    for row in entries:
        if isinstance(row, dict) and isinstance(row.get("pcsx2_png"), str):
            by_name.setdefault(row["pcsx2_png"], str(row.get("xbox_asset_id", "")))
    provenance = {key: document[key] for key in ("disc", "emulator", "method",
                                                 "generated", "counts")
                  if key in document}
    return IdentityMap(path, _sha256_bytes(payload), by_name, provenance)


# --------------------------------------------------------------------------
# Walking the disc's uniform packages.
# --------------------------------------------------------------------------

def uniform_entries(iso_path: Path) -> Tuple[list, list, dict, List[Tuple[int, str]]]:
    """``(packs, entries, identity, [(outer index, selector)])`` for one image."""

    try:
        packs, entries, identity = texture_map.disc_jobs(str(iso_path), hash_image=False)
    except (AssertionError, ValueError, OSError, struct.error) as exc:
        raise Refusal(
            f"{iso_path} is not a readable {SERIAL} resource layout: {exc}"
        ) from exc
    selectors = colour_catalog.selector_index()
    uniform = [(index, selectors[row[0]])
               for index, row in enumerate(entries) if row[0] in selectors]
    if not uniform:
        raise Refusal(
            f"{iso_path} carries no uniform packages; this lane needs an "
            f"ESPN NFL 2K5 ({SERIAL}) disc image."
        )
    return packs, entries, identity, uniform


def _row_key(selector: str, record: Mapping[str, Any]) -> str:
    return f"{selector}:{record['chunk']}:{record['idx']}:{record['name'] or 'unnamed'}"


class _EntryReader:
    """One open archive, so decoding several textures walks an entry once."""

    def __init__(self, iso_path: Path) -> None:
        self.iso_path = Path(iso_path)
        packs, entries, _identity, uniform = uniform_entries(self.iso_path)
        texture_map.initialise(str(self.iso_path), packs, entries)
        self.uniform = uniform
        self._cache_index: Optional[int] = None
        self._cache_rows: List[dict] = []

    def rows(self, entry_index: int) -> List[dict]:
        if self._cache_index != entry_index:
            self._cache_rows = texture_map.process_entry(entry_index, keep_payload=True)
            self._cache_index = entry_index
        return self._cache_rows

    def find(self, entry_index: int, chunk: int, child: int, name: str) -> dict:
        for record in self.rows(entry_index):
            if (record["chunk"] == chunk and record["idx"] == child
                    and (record["name"] or "") == name):
                return record
        raise Refusal(
            f"the texture {name!r} is no longer at package entry {entry_index}, "
            f"chunk {chunk}, child {child} on this image; re-run the catalogue."
        )


# --------------------------------------------------------------------------
# The lane.
# --------------------------------------------------------------------------

class UniformArtLane:
    """Uniform textures read off the PS2 disc, edited, and packed for PCSX2."""

    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = SURFACE
    page = PAGE
    title = "Uniform art from the disc's own textures"
    classification = CLASSIFICATION
    recipe_schema = RECIPE_SCHEMA
    validators = (
        "tools/validate_nfl2k5_ps2_replacement_pack.sh",
        "tools/validate_nfl2k5_ps2_replacement_pack.bat",
        "tools/validate_nfl2k5_ps2_uniform_art.sh",
        "tools/validate_nfl2k5_ps2_uniform_art.bat",
    )
    fixed_allocation = False
    budget = ("one PNG per texture, at the texture's own size or a whole-number "
              "multiple of it")

    def __init__(self, map_path: Optional[Path] = None,
                 kits_path: Path = KITS_FILE) -> None:
        self._map_override = Path(map_path) if map_path else None
        self._kits_path = Path(kits_path)

    # -- catalogue -----------------------------------------------------

    def selectors_for_team(self, team: str) -> Tuple[str, ...]:
        """Every uniform package one team owns, by abbreviation or full name."""

        wanted = (team or "").strip().casefold()
        if not wanted:
            return ()
        kits = load_kits(self._kits_path)
        return tuple(sorted(
            selector for selector, row in kits.items()
            if wanted in (str(row.get("abbreviation", "")).casefold(),
                          str(row.get("team", "")).casefold())))

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None,
        jobs: int = 0, selectors: Sequence[str] = (),
    ) -> Catalogue:
        """Every uniform texture on ``source``, or only the named packages'.

        ``selectors`` narrows the *walk*, not the result: one team's kit is 61
        textures out of 38,674, and reading the whole disc to show them is a
        minute a user does not have to spend.
        """

        source = Path(source)
        identity_map = load_identity_map(map_for_source(source, self._map_override))
        kits = load_kits(self._kits_path)
        packs, entries, disc_identity, uniform = uniform_entries(source)
        if selectors:
            wanted = {str(value).strip().upper() for value in selectors if str(value).strip()}
            narrowed = [row for row in uniform if row[1].upper() in wanted]
            if not narrowed:
                raise Refusal(
                    f"{', '.join(sorted(wanted))} names no uniform package on this "
                    f"disc; a package is two characters, H or A, and a variant "
                    f"number, e.g. 09H0."
                )
            uniform = narrowed

        rows: List[dict] = []
        started = time.time()
        for done, (entry_index, records) in enumerate(
                self._walk(source, packs, entries, uniform, jobs), 1):
            for record in records:
                rows.append(self._row(record, entry_index, identity_map, kits))
            if progress and (done % 25 == 0 or done == len(uniform)):
                progress(f"{done}/{len(uniform)} uniform packages · "
                         f"{len(rows)} textures · {time.time() - started:0.0f}s")

        targets = tuple(self._target(row) for row in rows)
        document = {
            "schema": CATALOGUE_SCHEMA,
            "lane": LANE_ID,
            "serial": SERIAL,
            "source": str(source),
            "disc": {
                "serial": disc_identity.get("serial"),
                "serial_matches": disc_identity.get("serial_matches"),
                "boot_sha256": disc_identity.get("boot_sha256"),
                "retail_boot_elf": disc_identity.get("retail_boot_elf"),
            },
            "identity_map": {
                "file": identity_map.path.as_posix(),
                "sha256": identity_map.sha256,
                "entries": identity_map.entries,
                "provenance": dict(identity_map.provenance),
            },
            "kits": {
                "file": self._kits_path.as_posix() if kits else "",
                "selectors": len(kits),
            },
            "scope": {"selectors": sorted(row[1] for row in uniform),
                       "whole_disc": not selectors},
            "summary": self._summary(rows, uniform, kits),
            "targets": rows,
        }
        return Catalogue(schema=CATALOGUE_SCHEMA, lane_id=LANE_ID, source=str(source),
                         targets=targets, document=document)

    @staticmethod
    def _walk(source: Path, packs, entries, uniform, jobs: int):
        """Yield ``(outer index, [records])`` per uniform package, pooled when it pays."""

        order = [index for index, _selector in uniform]
        workers = jobs if jobs > 0 else min(8, (os.cpu_count() or 1))
        if workers <= 1 or len(order) < 8 or not hasattr(os, "fork"):
            texture_map.initialise(str(source), packs, entries)
            for index in order:
                yield index, texture_map.process_entry(index)
            return
        import multiprocessing

        context = multiprocessing.get_context("fork")
        with context.Pool(workers, initializer=texture_map.initialise,
                          initargs=(str(source), packs, entries)) as pool:
            for index, batch in zip(order, pool.imap(texture_map.process_entry,
                                                     order, chunksize=4)):
                yield index, batch

    def _row(self, record: Mapping[str, Any], entry_index: int,
             identity_map: IdentityMap, kits: Mapping[str, Mapping[str, str]]) -> dict:
        selectors = colour_catalog.selector_index()
        selector = selectors.get(int(record["id"], 16), "")
        names = candidate_names(record)
        mapped_name = ""
        mapped_asset = ""
        for name, _routes in names.items():
            asset = identity_map.by_name.get(name)
            if asset:
                mapped_name, mapped_asset = name, asset
                break
        if mapped_name:
            level_route, clut_route = names[mapped_name]
            identity_source = "map"
            pcsx2_png = mapped_name
        else:
            level_route, clut_route = rule_routes(record)
            identity_source = "rule" if level_route and clut_route else "none"
            pcsx2_png = ""
            if level_route and clut_route:
                for name, routes in names.items():
                    if routes == (level_route, clut_route):
                        pcsx2_png = name
                        break
        kit = dict(kits.get(selector.upper(), {}))
        part, description, variant = part_of(record["name"])
        return {
            "key": _row_key(selector, record),
            "selector": selector,
            "entry": entry_index,
            "chunk": int(record["chunk"]),
            "child": int(record["idx"]),
            "source_kind": record["src"],
            "name": record["name"] or "",
            "team": kit.get("team", ""),
            "team_abbreviation": kit.get("abbreviation", ""),
            "kit": kit.get("kit", ""),
            "side": kit.get("side", ""),
            "part": part,
            "part_description": description,
            "variant": variant,
            "width": int(record["w"]),
            "height": int(record["h"]),
            "pixel_format": record["psm"],
            "mip_levels": int(record["mips"]),
            "level0_route": level_route or "",
            "clut_route": clut_route or "",
            "identity_source": identity_source,
            "identity_confirmed": identity_source == "map",
            "pcsx2_png": pcsx2_png,
            "xbox_asset_id": mapped_asset,
            "candidate_identities": len(names),
        }

    def _target(self, row: Mapping[str, Any]) -> Target:
        team = row["team"] or (f"package {row['selector'][:2]}" if row["selector"] else "unknown package")
        kit = " · ".join(part for part in (row["side"], row["kit"]) if part) or describe_selector(row["selector"])
        variant = f" ({row['variant']})" if row["variant"] else ""
        label = (f"{team} · {kit} · {row['part_description']}{variant} — "
                 f"{row['width']}x{row['height']} {row['pixel_format']}")
        if row["identity_confirmed"]:
            detail = (f"{row['name']} · replacement {row['pcsx2_png']} · "
                      f"{row['mip_levels']} mip level(s) · identity from the shipped map")
        elif row["pcsx2_png"]:
            detail = (f"{row['name']} · replacement {row['pcsx2_png']} · "
                      f"{row['mip_levels']} mip level(s) · identity computed by rule, "
                      f"not proved by the shipped map: exportable as a PNG, not packable")
        else:
            detail = (f"{row['name']} · no replacement identity could be computed · "
                      f"{row['mip_levels']} mip level(s)")
        searchable = " ".join(str(value) for value in (
            row["key"], row["selector"], row["team"], row["team_abbreviation"],
            row["kit"], row["side"], row["name"], row["part"], row["part_description"],
            row["pcsx2_png"],
        ) if value)
        return _target_with_fields(
            (PNG_FIELD,),
            key=row["key"],
            label=label,
            detail=detail,
            budget=self.budget,
            searchable=searchable,
            raw=dict(row),
        )

    @staticmethod
    def _summary(rows: Sequence[Mapping[str, Any]], uniform: Sequence[Tuple[int, str]],
                 kits: Mapping[str, Mapping[str, str]]) -> dict:
        named = [row for row in rows if row["team"]]
        packable = [row for row in rows if row["identity_confirmed"]]
        no_identity = [row for row in rows if not row["pcsx2_png"]]
        teams = sorted({row["team"] for row in named})
        unnamed_selectors = sorted({row["selector"] for row in rows if not row["team"]})
        return {
            "uniform_packages": len(uniform),
            "textures": len(rows),
            "teams": len(teams),
            "team_names": teams,
            "selectors": len({row["selector"] for row in rows}),
            "packable_textures": len(packable),
            "packable_selectors": len({row["selector"] for row in packable}),
            "textures_without_a_team_name": len(rows) - len(named),
            "selectors_without_a_team_name": len(unnamed_selectors),
            "selectors_without_a_team_name_list": unnamed_selectors,
            "textures_without_an_identity": len(no_identity),
            "kit_table_selectors": len(kits),
            "note": (
                "A texture is packable only when one of its candidate identities "
                "is in the shipped map: that is the identity PCSX2's own hash "
                "agreed with. The rest are catalogued and can be exported as "
                "PNGs, but a pack must not claim a filename nothing proved. "
                "A texture with no team name belongs to a uniform package the "
                "shipped kit table does not name; its package code is still "
                "exact."
            ),
        }

    # -- the ArtLane three ---------------------------------------------

    def decode_png(self, source: Path, target: Target) -> bytes:
        """Level 0 of one uniform texture as an 8-bit RGBA PNG."""

        row = dict(target.raw)
        reader = _EntryReader(Path(source))
        record = reader.find(int(row["entry"]), int(row["chunk"]), int(row["child"]),
                             str(row["name"]))
        level_route = row.get("level0_route") or ""
        clut_route = row.get("clut_route") or ""
        if not level_route or not clut_route:
            raise Refusal(
                f"{target.key}: this texture's palette or pixel layout could not "
                f"be resolved from the disc, so it cannot be decoded."
            )
        rgba, width, height = decode_level0_rgba(record["payload"], level_route, clut_route)
        return write_rgba_png(rgba, width, height)

    def encode(self, source: Path, target: Target, png: bytes):
        """Accept a replacement PNG, or return the :class:`Refusal` that says why."""

        row = dict(target.raw)
        want = (int(row["width"]), int(row["height"]))
        wanted = (f"{want[0]}x{want[1]} (or a whole-number multiple of it, "
                  f"{want[0] * 2}x{want[1] * 2}, {want[0] * 3}x{want[1] * 3}, …)")
        if not isinstance(png, (bytes, bytearray)):
            return Refusal(f"{target.key}: a replacement must be PNG bytes; this is "
                           f"{type(png).__name__}. Give a PNG of {wanted}.")
        png = bytes(png)
        if len(png) > MAX_PNG_BYTES:
            return Refusal(f"{target.key}: that replacement is larger than the "
                           f"{MAX_PNG_BYTES // (1024 * 1024)} MB bound a PNG of "
                           f"{wanted} could need.")
        header = png_header(png)
        if header is None:
            return Refusal(f"{target.key}: that file is not a PNG with a valid IHDR. "
                           f"Give a PNG of {wanted}.")
        width, height, depth, colour, interlace = header
        if width % want[0] or height % want[1]:
            return Refusal(f"{target.key}: that PNG is {width}x{height}; this texture "
                           f"is {want[0]}x{want[1]}, so give a PNG of {wanted}.")
        scale = width // want[0]
        if scale != height // want[1] or scale < 1:
            return Refusal(f"{target.key}: that PNG is {width}x{height}, which is "
                           f"{width // want[0]}x wide and {height // want[1]}x tall; "
                           f"PCSX2 scales a replacement but cannot change its shape, "
                           f"so give a PNG of {wanted}.")
        note = (f"{width}x{height}, the texture's own size"
                if scale == 1 else
                f"{width}x{height}, {scale}x the texture's {want[0]}x{want[1]}; PCSX2 scales it down")
        if depth == 8 and colour == 6 and interlace == 0:
            return EncodedArt(png=png, width=width, height=height, note=note)
        converted = _to_rgba_png(png, target.key, wanted)
        if isinstance(converted, Refusal):
            return converted
        return EncodedArt(png=converted, width=width, height=height,
                          note=note + "; converted to 8-bit RGBA")

    def replacement_identity(self, target: Target) -> Optional[str]:
        """The filename PCSX2 loads for this texture, computed from the user's disc."""

        name = dict(target.raw).get("pcsx2_png") or ""
        return name or None

    # -- editing -------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"png", "png_path", "png_base64", "note"})
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not a value this lane "
                    f"edits; a uniform texture has exactly one, the PNG.")
        try:
            png = _png_from_values(target.key, values)
        except Refusal as exc:
            return str(exc)
        result = self.encode(Path(""), target, png)
        if isinstance(result, Refusal):
            return str(result)
        row = dict(target.raw)
        if not row.get("identity_confirmed"):
            return (f"{target.key}: the shipped map does not prove this texture's "
                    f"PCSX2 filename, so a pack cannot claim it. Export it as a PNG "
                    f"instead, or choose a texture the catalogue marks packable.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"target": edit.target_key}
            values = dict(edit.values)
            if isinstance(values.get("png_path"), str):
                row["png_path"] = values["png_path"]
            else:
                png = _png_from_values(edit.target_key, values)
                row["png_base64"] = base64.b64encode(png).decode("ascii")
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": RECIPE_SCHEMA, "emulator_target": "penguinscreen2_classic",
                "edits": rows}

    # -- plan / build / verify -----------------------------------------

    def _resolve(self, recipe: Mapping[str, Any], catalogue: Catalogue
                 ) -> List[Tuple[Target, EncodedArt]]:
        if recipe.get("schema") != RECIPE_SCHEMA:
            raise Refusal(f"a uniform-art recipe carries schema {RECIPE_SCHEMA}, "
                          f"not {recipe.get('schema')!r}.")
        rows = recipe.get("edits")
        if not isinstance(rows, list) or not rows:
            raise Refusal("this recipe stages no edits; choose a texture and give it a PNG.")
        resolved: List[Tuple[Target, EncodedArt]] = []
        seen = set()
        for number, row in enumerate(rows, 1):
            if not isinstance(row, dict) or not isinstance(row.get("target"), str):
                raise Refusal(f"recipe edit {number} names no target.")
            key = row["target"]
            if key in seen:
                raise Refusal(f"{key} is staged twice; one texture takes one PNG.")
            seen.add(key)
            target = catalogue.target(key)
            png = _png_from_values(key, row)
            result = self.encode(Path(catalogue.source), target, png)
            if isinstance(result, Refusal):
                raise result
            if not dict(target.raw).get("identity_confirmed"):
                raise Refusal(
                    f"{key}: the shipped map does not prove this texture's PCSX2 "
                    f"filename, so a pack cannot claim it. Export it as a PNG "
                    f"instead, or choose a texture the catalogue marks packable."
                )
            resolved.append((target, result))
        return resolved

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        resolved = self._resolve(recipe, catalogue)
        identity_map = load_identity_map(map_for_source(Path(source), self._map_override))
        files: List[dict] = []
        for target, art in resolved:
            row = dict(target.raw)
            names = sorted(name for name, asset in identity_map.by_name.items()
                           if asset == row["xbox_asset_id"])
            if not names:
                raise Refusal(
                    f"{target.key}: the identity map no longer names "
                    f"{row['xbox_asset_id']}; re-run the catalogue against this map."
                )
            files.append({
                "target": target.key,
                "xbox_asset_id": row["xbox_asset_id"],
                "pcsx2_png": names,
                "png_sha256": _sha256_bytes(art.png),
                "size": [art.width, art.height],
                "note": art.note,
            })
        return Plan(
            lane_id=LANE_ID,
            target_keys=tuple(target.key for target, _art in resolved),
            declared_ranges=(),
            document={
                "serial": SERIAL,
                "identity_map": {"file": identity_map.path.as_posix(),
                                 "sha256": identity_map.sha256},
                "emulator_target": str(recipe.get("emulator_target")
                                       or "penguinscreen2_classic"),
                "files": files,
                "file_count": sum(len(row["pcsx2_png"]) for row in files),
            },
        )

    @staticmethod
    def pack_root_for(destination: Path) -> Path:
        """The folder a contract build writes beside its receipt.

        The contract's harness treats a build's ``destination`` as a file it can
        hash, and a replacement pack is a folder; so ``destination`` is the
        receipt-and-edits document and the pack sits next to it under
        ``<destination>.pack/``.  A caller that wants the folder named directly
        -- the CLI does -- calls :meth:`export_pack`.
        """

        destination = Path(destination)
        return destination.parent / (destination.name + ".pack")

    def export_pack(self, source: Path, pack_root: Path, recipe: Mapping[str, Any],
                    catalogue: Catalogue) -> Tuple[dict, dict]:
        """Write the replacement pack folder.  Returns ``(pack receipt, edits)``."""

        from mod_editor.core import ps2_export_service as export  # lazy: core stays off the boundary

        resolved = self._resolve(recipe, catalogue)
        identity_map = map_for_source(Path(source), self._map_override)
        emulator_target = str(recipe.get("emulator_target") or export.DEFAULT_EMULATOR_TARGET)
        edits = []
        targets = []
        for target, art in resolved:
            row = dict(target.raw)
            targets.append(export.ExportTarget(row["xbox_asset_id"], art.png, target.key))
            edits.append({
                "target": target.key,
                "xbox_asset_id": row["xbox_asset_id"],
                "selector": row["selector"],
                "texture": row["name"],
                "png_sha256": _sha256_bytes(art.png),
                "size": [art.width, art.height],
            })
        try:
            project = export.project_from_targets(targets, source=str(source))
            plan = export.plan_export(project, identity_map)
            receipt = export.run_export(plan, Path(pack_root),
                                        emulator_target=emulator_target,
                                        origin=export.ORIGIN_DISC_NATIVE_ART)
        except export.Ps2ExportError as exc:
            raise Refusal(str(exc).strip() or exc.__class__.__name__) from exc
        document = {
            "schema": EDITS_SCHEMA,
            "serial": SERIAL,
            "origin": export.ORIGIN_DISC_NATIVE_ART,
            "source": str(source),
            "pack": Path(pack_root).as_posix(),
            "identity_map": {"file": Path(identity_map).as_posix(),
                             "sha256": load_identity_map(identity_map).sha256},
            "emulator_target": emulator_target,
            "edits": edits,
        }
        return dict(receipt.document), document

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt:
        source = Path(source)
        destination = Path(destination)
        require(destination.resolve() != source.resolve(),
                f"{destination} is the source image; a build writes a NEW pack and "
                f"never the disc.")
        require(not os.path.lexists(destination),
                f"destination {destination} already exists; refusing to overwrite it")
        pack_root = self.pack_root_for(destination)
        require(not os.path.lexists(pack_root),
                f"the pack folder {pack_root} already exists; choose a destination "
                f"whose pack folder is free")

        pack_receipt, edits = self.export_pack(source, pack_root, recipe, catalogue)
        payload = (json.dumps(edits, indent=2, sort_keys=True) + "\n").encode("utf-8")
        with open(destination, "xb") as handle:
            handle.write(payload)
        digest = _sha256_bytes(payload)

        artifacts = [Artifact(str(destination), digest, "uniform-art-edits")]
        for path in sorted(p for p in pack_root.rglob("*") if p.is_file()):
            artifacts.append(Artifact(str(path), _sha256_file(path),
                                      "replacement-png" if path.suffix.lower() == ".png"
                                      else "pack-metadata"))
        document = {
            "schema": PACK_SCHEMA,
            "lane": LANE_ID,
            "source": str(source),
            "destination": str(destination),
            "pack": pack_root.as_posix(),
            "edits_sha256": digest,
            "edits_document": edits,
            "pack_receipt": pack_receipt,
            "counts": {"targets": len(edits["edits"]),
                       "files": len(pack_receipt.get("files", []))},
        }
        return Receipt(schema=PACK_SCHEMA, lane_id=LANE_ID, source=str(source),
                       destination=str(destination), declared_ranges=(),
                       document=document, artifacts=tuple(artifacts))

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        destination = Path(destination)
        document = dict(receipt.document)
        try:
            actual = _sha256_file(destination)
        except OSError as exc:
            return Verdict(False, f"Verification failed: {destination} cannot be read: {exc}")
        expected = str(document.get("edits_sha256") or "")
        if actual != expected:
            return Verdict(
                False,
                "Verification failed: the edits document on disk is not the one the "
                "receipt recorded, so the pack cannot be attributed to it.",
                {"expected_sha256": expected, "actual_sha256": actual},
            )
        pack_root = Path(str(document.get("pack") or ""))
        if not pack_root.is_dir():
            return Verdict(False, f"Verification failed: the pack folder {pack_root} is missing.")
        identity_map = (document.get("edits_document") or {}).get("identity_map") or {}
        manifest = identity_map.get("file") or str(
            map_for_source(Path(source), self._map_override))
        try:
            report = pack_verify.verify(pack_root, manifest=Path(manifest),
                                        edits=destination)
        except pack_verify.PackVerifyError as exc:
            return Verdict(False, f"Verification failed: {exc}", {"error": str(exc)})
        except (OSError, ValueError) as exc:
            return Verdict(False, f"Verification could not run: {exc}", {"error": str(exc)})
        passed = report.get("result") == pack_verify.RESULT_PASS
        return Verdict(
            passed,
            f"{report['files_checked']} replacement file(s) verified against the "
            f"receipt and the identity map; {report['edited_targets_checked']} "
            f"edited target(s) checked; result {report['result']}.",
            report,
        )

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        """A tiny PS2 image with two synthetic uniform textures, and its own map.

        No retail byte is involved: the pixels are a pseudo-random pattern and
        the palette is another, laid out by the same GS rules the decoder reads.
        The sidecar map beside it names the two textures, so the whole route --
        catalogue, decode, edit, pack, verify -- runs on CI without a disc.
        """

        work_dir = Path(work_dir)
        path = work_dir / "nfl2k5-ps2-uniform-art-synthetic.iso"
        path.write_bytes(build_synthetic_iso())
        sidecar = Path(str(path) + MAP_SIDECAR_SUFFIX)
        with open(sidecar, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(synthetic_identity_map(path), indent=2,
                                    sort_keys=True) + "\n")
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            row = dict(target.raw)
            if not row.get("identity_confirmed"):
                continue
            png = write_rgba_png(
                bytes([0x20, 0x80, 0xC0, 0xFF]) * (row["width"] * row["height"]),
                row["width"], row["height"])
            return (Edit(target.key, {"png": png},
                         note="conformance: a flat RGBA fill at the texture's own size"),)
        raise Refusal("this catalogue has no texture whose identity the map proves.")


# --------------------------------------------------------------------------
# PNG values in a recipe or an edit.
# --------------------------------------------------------------------------

def _png_from_values(key: str, values: Mapping[str, Any]) -> bytes:
    """The PNG bytes of one edit: inline, base64 or a path."""

    png = values.get("png")
    if isinstance(png, (bytes, bytearray)):
        return bytes(png)
    encoded = values.get("png_base64")
    if isinstance(encoded, str):
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise Refusal(f"{key}: png_base64 is not valid base64: {exc}") from exc
    path = values.get("png_path") or (png if isinstance(png, str) else None)
    if isinstance(path, str) and path:
        candidate = Path(path)
        try:
            info = candidate.lstat()
        except OSError as exc:
            raise Refusal(f"{key}: {candidate} cannot be read: {exc}") from exc
        if not info.st_size or info.st_size > MAX_PNG_BYTES:
            raise Refusal(f"{key}: {candidate} is empty or larger than the safe bound.")
        return candidate.read_bytes()
    raise Refusal(f"{key}: give the replacement as png (bytes), png_base64 or png_path.")


def _to_rgba_png(png: bytes, key: str, wanted: str):
    """Re-encode a PNG as 8-bit RGBA.  Pillow only, and only when needed."""

    try:
        from PIL import Image
    except ImportError:
        return Refusal(
            f"{key}: that PNG is not 8-bit RGBA and Pillow is not installed to "
            f"convert it. Save it as an 8-bit RGBA PNG of {wanted}, or install Pillow."
        )
    import io

    try:
        with Image.open(io.BytesIO(png)) as image:
            converted = image.convert("RGBA")
            buffer = io.BytesIO()
            converted.save(buffer, format="PNG")
    except (OSError, ValueError) as exc:
        return Refusal(f"{key}: that PNG could not be read: {exc}. Give a PNG of {wanted}.")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# The synthetic fixture: a PS2 image with two uniform textures, no retail bytes.
# --------------------------------------------------------------------------

SYNTHETIC_SELECTOR = "00H0"
SYNTHETIC_ASSET_IDS = {
    "jersey00": "nfl2k5.uniform.00h0.torso",
    "sleeve00": "nfl2k5.uniform.00h0.sleeve",
}
_SYNTHETIC_TEXTURES = (
    # (name, PSM, width, height) -- one 256-colour PSMT8 and one 16-colour PSMT4.
    ("jersey00", texture_map.PSMT8, 64, 32),
    ("sleeve00", texture_map.PSMT4, 64, 32),
)


def _pointer(field: int, target: int) -> bytes:
    return struct.pack("<i", target - field + 1)


def _synthetic_tset() -> bytes:
    """One ``TSET`` chunk holding the two synthetic TXTR children."""

    count = len(_SYNTHETIC_TEXTURES)
    reference_base = inventory_lib.TSET_REF_BASE
    stride = inventory_lib.TSET_REF_STRIDE
    names_at = reference_base + count * stride
    system = bytearray(names_at)
    struct.pack_into("<II", system, 0, 1, count)

    encoded_names = []
    for name, _psm, _width, _height in _SYNTHETIC_TEXTURES:
        encoded_names.append((len(system), name))
        system += name.encode("utf-16le") + b"\x00\x00"
    while len(system) % 4:
        system += b"\x00"

    video = bytearray()
    descriptors = []
    for index, (_name, psm, width, height) in enumerate(_SYNTHETIC_TEXTURES):
        bits_per_pixel = 8 if psm == texture_map.PSMT8 else 4
        palette_bytes = 1024 if psm == texture_map.PSMT8 else 64
        level0 = (width * height * bits_per_pixel) // 8
        image_offset = len(video)
        pixels = texture_map.pattern_bytes(level0, 11 + index)
        video += pixels
        video += texture_map.pattern_bytes(palette_bytes, 31 + index)
        while len(video) % 256:
            video += b"\x00"
        tex0 = texture_map.make_tex0(
            psm, width.bit_length() - 1, height.bit_length() - 1,
            max(1, width // (64 if psm == texture_map.PSMT8 else 128)),
            level0 // 256)
        descriptors.append((len(system), texture_map.descriptor_bytes(
            tex0, image_offset, width, height)))
        system += descriptors[-1][1]

    for index in range(count):
        record = reference_base + index * stride
        system[record:record + 4] = b"TXTR"
        system[record + 4:record + 8] = _pointer(record + 4, encoded_names[index][0])
        system[record + 8:record + 12] = _pointer(record + 8, descriptors[index][0])

    header = bytearray(inventory_lib.CHUNK_HEADER_SIZE)
    header[0:4] = b"TSET"
    struct.pack_into("<4I", header, 4, len(system) + len(video), len(system),
                     len(video), 0)
    return bytes(header) + bytes(system) + bytes(video)


def build_synthetic_iso() -> bytes:
    """A ``/VC_20919`` archive whose first entry is a uniform package."""

    return colour_catalog.build_synthetic_iso(entries=[
        (f"{SYNTHETIC_SELECTOR}.IFF", _synthetic_tset()),
        ("ZZZZ.BIN", b"RAWD" + bytes(12) + b"not a chunk stream" * 4),
    ])


def synthetic_identity_map(iso_path: Path) -> dict:
    """The sidecar map for :func:`build_synthetic_iso`, computed from its own bytes."""

    packs, entries, _identity, uniform = uniform_entries(Path(iso_path))
    texture_map.initialise(str(iso_path), packs, entries)
    rows = []
    for entry_index, _selector in uniform:
        for record in texture_map.process_entry(entry_index):
            asset = SYNTHETIC_ASSET_IDS.get(record["name"] or "")
            if not asset:
                continue
            level_route, clut_route = rule_routes(record)
            for name, routes in candidate_names(record).items():
                if routes == (level_route, clut_route):
                    rows.append({"pcsx2_png": name, "xbox_asset_id": asset})
                    break
    return {
        "schema": MAP_SCHEMA,
        "disc": {"serial": SERIAL, "boot_sha256": "0" * 64, "content_sha256": "0" * 64},
        "emulator": {"name": "PenguinScreen2", "commit": "synthetic",
                     "hash_convention": "classic-tcc-bit14",
                     "requires_setting": "ClassicTextureNames=true"},
        "method": "synthetic-fixture",
        "generated": "1970-01-01T00:00:00Z",
        "counts": {"entries": len(rows)},
        "entries": rows,
    }


__all__ = [
    "CAPABILITY_ID",
    "CATALOGUE_SCHEMA",
    "CLASSIFICATION",
    "DEFAULT_MAP",
    "EDITS_SCHEMA",
    "EncodedArt",
    "Field",
    "IdentityMap",
    "KITS_FILE",
    "LANE_ID",
    "MAP_SIDECAR_SUFFIX",
    "PACK_SCHEMA",
    "PNG_FIELD",
    "RECIPE_SCHEMA",
    "SURFACE",
    "UniformArtLane",
    "build_synthetic_iso",
    "candidate_names",
    "decode_level0_rgba",
    "describe_selector",
    "load_identity_map",
    "load_kits",
    "map_for_source",
    "part_of",
    "png_header",
    "rule_routes",
    "synthetic_identity_map",
    "uniform_entries",
    "write_rgba_png",
]
