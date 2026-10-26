"""Team-coloured long sleeves (job sl1; Noah 10/22: "Team colored sleeves would be sick").

What the game does (PROVED OFFLINE on the retail executable; the addresses are
pinned by ``tests/mod_editor/test_nfl2k5_team_sleeves.py``):

* A roster record's sleeve style is ``+0x1C`` bits 0-1: 0 None, 1 White, 2 Black,
  3 Team (``nfl2k5_roster_records.SLEEVES``). ``FUN_0008F620`` reads it, and the
  material binder ``FUN_0008EDB0`` maps styles 1/2/3 to player-texture cache rows
  35/36/37 through the table at ``0x004EF5C4`` (row 35 = ``longsleeve01``,
  36 = ``longsleeve02``, 37 = ``longsleeve03``; each entry is (row, 0x0B)).
* Rows 35 and 36 are *global* binding-table rows (context-first word 0) while row
  37 is context-first (word 1). ``FUN_0008E620`` fills the clean/mud x HOME/AWAY
  cache through ``FUN_0008E580``; a global row takes the newest loaded uniform
  package (the away team's package in a game) for both teams. That is why the
  Black style is black for every club, while the Team style is already the
  package's own colour.
* ``longsleeve01/02/03`` share one index/mip chain inside each uniform package's
  chunk-7 TSET and own separate 256-entry P8 palettes.

The change (data only; no native code, no cave):

* Flip the binding-table context-first word of row 36 from 0 to 1 in place in
  ``.rdata`` (``0x004EEC18 + 4``; the .rdata digest is recomputed). Row 36 then
  resolves from each side's HOME/AWAY package exactly like the Team row.
* In every uniform package, make row 36's palette the package's team colour:
  when the game's own Team palette (row 37) is not the default near-black, copy
  it byte for byte; when it is the default near-black on a coloured jersey, use
  that jersey's own primary colour; on a white jersey of a current club keep the
  club's Team colour (black for black-primary clubs), and on a white jersey of a
  retail historic club use the helmet's colour. The same derived colour also
  replaces a default-black Team palette, so both the Black and the Team styles
  are team-coloured for those historic kits. The mud twin follows the game's
  wet-93 rule. Row 35 (White) is untouched.
* Every package is input-checked against the pinned equipment catalog's layout
  (names, descriptors and the shared index/mip allocation); a package whose
  long-sleeve TSET no longer has that layout is left alone, and a package
  already carrying the change is a no-op.

Build option ``team_sleeves`` (on in every SOFTDRINK preset); needs a disc image.
The Hi-res jerseys family pins the whole 768-byte binding table, so the two
options refuse to build together.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import struct

import numpy as np

from . import nfl2k5_bump_texture_writer as bump
from . import nfl2k5_kit_fixes_2026 as kit_art
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_uniform_equipment_writer import EquipmentTarget, load_targets
from nfl_txtr import decode_chunk, parse_chunks
from nfl_vc_lz_fill import rebuild_fixed_span_filled

OWNER = "nfl2k5_team_sleeves"
BUILD_CAPTION = "Team-coloured long sleeves"
HELP_TEXT = (
    "The black undershirt sleeves take each uniform's own team colour: the colour the game already "
    "gives that kit's Team sleeve style, or the jersey/helmet colour where that Team colour is the "
    "default black. The Black sleeve style is rebound to each side's own uniform package. White "
    "sleeves stay white. Needs a disc image; the Hi-res jerseys family cannot be built with it."
)
SCHEMA = "nfl2k5_team_sleeves/v1"

BINDING_TABLE_VA = 0x004EEAF8
ROW_WHITE = 35
ROW_BLACK = 36
ROW_TEAM = 37
BLACK_NAME_VA = BINDING_TABLE_VA + ROW_BLACK * 8
BLACK_FLAG_VA = BLACK_NAME_VA + 4
TEAM_FLAG_VA = BINDING_TABLE_VA + ROW_TEAM * 8 + 4
WHITE_FLAG_VA = BINDING_TABLE_VA + ROW_WHITE * 8 + 4
# FUN_0008EDB0: sleeve style 1/2/3 -> (cache row, 0x0B), 8 bytes per style.
SLEEVE_STYLE_TABLE_VA = 0x004EF5BC
SLEEVE_STYLE_TABLE_SIZE = 32
RETAIL_BLACK_FLAG = 0
APPLIED_BLACK_FLAG = 1
WET_NUM, WET_DEN = 93, 100
CHUNK = 7
CURRENT_CODES = frozenset(range(32))


class TeamSleevesError(ValueError):
    """The executable or a uniform package is not the reviewed retail layout."""


def require(ok, message):
    if not ok:
        raise TeamSleevesError("Team-coloured sleeves: " + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------------- executable

def _binding_name(image: XbeImage, va: int) -> str:
    pointer = image.word(va)
    chars = []
    for index in range(64):
        pair = image.read(pointer + index * 2, 2)
        if pair == b"\0\0":
            break
        chars.append(pair)
    return b"".join(chars).decode("utf-16le")


def status(payload: bytes) -> str:
    """``retail`` (row 36 global), ``applied`` (row 36 context-first) or ``foreign``."""
    try:
        image = XbeImage(payload)
        if _binding_name(image, BLACK_NAME_VA) != "longsleeve02":
            return "foreign"
        if image.word(TEAM_FLAG_VA) != 1 or image.word(WHITE_FLAG_VA) != 0:
            return "foreign"
        flag = image.word(BLACK_FLAG_VA)
        return "retail" if flag == RETAIL_BLACK_FLAG else "applied" if flag == APPLIED_BLACK_FLAG else "foreign"
    except (ValueError, IndexError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Flip row 36's context-first word in place; the table's other rows must be retail."""
    state = status(payload)
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0, "edits": []}
    require(state == "retail", "the player texture binding table is neither retail nor this change")
    image = XbeImage(payload)
    offset = image.offset(BLACK_FLAG_VA, 4)
    result = bytearray(payload)
    struct.pack_into("<I", result, offset, APPLIED_BLACK_FLAG)
    for section in _sections(bytes(result)):
        header = section.header_offset + 36
        result[header:header + 20] = section_digest(bytes(result), section)
    patched = bytes(result)
    require(status(patched) == "applied", "post-apply verification failed")
    changed = sum(a != b for a, b in zip(payload, patched))
    return patched, {
        "already_applied": False,
        "flag_va": f"0x{BLACK_FLAG_VA:x}",
        "file_offset": f"0x{offset:x}",
        "row": ROW_BLACK,
        "name": "longsleeve02",
        "changed_bytes": changed,
        "native_code_bytes": 0,
        "cave_bytes": 0,
        "runtime_witnessed": False,
    }


def verify(payload: bytes) -> dict:
    state = status(payload)
    require(state == "applied", f"the team sleeve binding row is {state}, not applied")
    image = XbeImage(payload)
    return {
        "state": state,
        "row": ROW_BLACK,
        "name": _binding_name(image, BLACK_NAME_VA),
        "context_first": image.word(BLACK_FLAG_VA),
        "runtime_witnessed": False,
    }


def style_table(payload: bytes) -> tuple[int, int, int]:
    """Rows the game binds for sleeve styles 1 (White), 2 (Black), 3 (Team)."""
    image = XbeImage(payload)
    raw = image.read(SLEEVE_STYLE_TABLE_VA, SLEEVE_STYLE_TABLE_SIZE)
    return tuple(struct.unpack_from("<I", raw, 8 + style * 8)[0] for style in range(3))  # type: ignore[return-value]


# --------------------------------------------------------------------------------------------- colours

def _palette(decoded: bytes, chunk, texture) -> np.ndarray:
    return kit_art.read_palette(decoded, chunk, texture)


def _histogram(palette: np.ndarray, plane: np.ndarray) -> list[tuple[tuple[int, int, int], int]]:
    """Opaque colours grouped in 16-level RGB buckets, most common first.

    Each bucket reports the count-weighted mean of its exact colours, so a flat
    P8 ramp does not have to be a single index.
    """
    used, counts = np.unique(plane.reshape(-1), return_counts=True)
    buckets: dict[tuple[int, int, int], list[int]] = {}
    for index, count in zip(used.tolist(), counts.tolist()):
        r, g, b, a = (int(v) for v in palette[index])
        if a < 250:
            continue
        key = (r // 16, g // 16, b // 16)
        slot = buckets.setdefault(key, [0, 0, 0, 0])
        slot[0] += r * count
        slot[1] += g * count
        slot[2] += b * count
        slot[3] += count
    rows = [((slot[0] // slot[3], slot[1] // slot[3], slot[2] // slot[3]), slot[3])
            for slot in buckets.values() if slot[3]]
    rows.sort(key=lambda item: -item[1])
    return rows


def _is_white(colour) -> bool:
    return colour is not None and min(colour) >= 200


def _is_black(colour) -> bool:
    return colour is not None and max(colour) < 40


def _chroma(colour) -> float:
    if colour is None:
        return 0.0
    high = max(colour)
    return 0.0 if high == 0 else (high - min(colour)) / high


def _helmet_colour(rows: list[tuple[tuple[int, int, int], int]]):
    """The shell colour, or the first prominent chromatic mark on a white/silver shell."""
    if not rows:
        return None
    shell = rows[0][0]
    if not _is_white(shell) and not (_chroma(shell) < 0.12 and 40 <= max(shell) < 200):
        return shell
    for colour, count in rows:
        if count < 300:
            break
        if _is_white(colour) or (_chroma(colour) < 0.25 and max(colour) >= 40):
            continue
        return colour
    return None


def choose_target(
    team: tuple[int, int, int] | None,
    jersey: tuple[int, int, int] | None,
    helmet: list[tuple[tuple[int, int, int], int]] | None,
    code: int,
) -> tuple[tuple[int, int, int], str]:
    """The sleeve colour for one uniform package, and the rule that chose it.

    ``team`` is the game's own Team palette (row 37), ``jersey`` the jersey body's
    dominant colour and ``helmet`` the helmet histogram. The order is deliberate:
    a non-black Team colour is already the game's answer for that kit; only its
    default-black placeholder is replaced.
    """
    if team is not None and not _is_black(team):
        return team, "team-style"
    if jersey is not None and not _is_white(jersey):
        return jersey, "jersey"
    if code in CURRENT_CODES:
        return team or (0, 0, 0), "current-team"
    found = _helmet_colour(helmet or [])
    if found is not None and not _is_black(found):
        return found, "helmet"
    return team or (0, 0, 0), "default"


def _wet(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple((channel * WET_NUM + WET_DEN // 2) // WET_DEN for channel in colour)


def _flat_palette(palette: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    out = palette.copy()
    out[:, 0] = colour[0]
    out[:, 1] = colour[1]
    out[:, 2] = colour[2]
    return out


def _palette_bytes(palette: np.ndarray) -> bytes:
    return np.ascontiguousarray(palette[:, [2, 1, 0, 3]], np.uint8).tobytes()


def _write_palette(decoded: bytes, chunk, texture, palette: np.ndarray) -> bytes:
    out = bytearray(decoded)
    at = chunk.system_bytes + texture["palette"]
    out[at:at + 1024] = _palette_bytes(palette)
    return bytes(out)


# --------------------------------------------------------------------------------------------- packages

def _package_selectors(by_id: dict[str, EquipmentTarget]) -> dict[str, int]:
    return {
        target.set_selector: target.outer_index
        for target in by_id.values()
        if target.chunk_index == CHUNK and target.name.startswith("longsleeve")
    }


def _textures(decoded: bytes) -> dict[str, dict]:
    return {texture["name"]: texture for texture in kit_art._tset_textures(decoded)}


def _histogram_of(decoded: bytes, chunk, texture) -> list[tuple[tuple[int, int, int], int]]:
    return _histogram(_palette(decoded, chunk, texture), kit_art.read_planes(decoded, chunk, texture)[0])


def _jersey_colour(raw: bytes, chunks) -> tuple[int, int, int] | None:
    chunk = chunks.get(1)
    if chunk is None or chunk.kind != "TSET":
        return None
    decoded, _ = decode_chunk(raw, chunk)
    texture = next((item for item in kit_art._tset_textures(decoded) if item["name"] == "jersey00"), None)
    if texture is None:
        return None
    rows = _histogram_of(decoded, chunk, texture)
    return rows[0][0] if rows else None


def _helmet_histogram(raw: bytes, chunks) -> list[tuple[tuple[int, int, int], int]]:
    chunk = chunks.get(11)
    if chunk is None or chunk.kind != "TXTR":
        return []
    span = raw[chunk.offset:chunk.end_offset]
    try:
        inner, decoded, textures = kit_art.native_textures(span, "txtr")
    except ValueError:
        return []
    return _histogram_of(decoded, inner, textures[0])


def _validate_sleeve_layout(decoded: bytes, chunk, rows: tuple[EquipmentTarget, ...], *,
                            strict: bool = False) -> None:
    """The retail TSET structure for the six long-sleeve rows, without their palettes.

    Rows 35/36/37 own separate P8 palettes over one shared index/mip chain. The
    release build and the Studio's own equipment imports may recolor any of them
    (palette-only); only a changed index chain, descriptor or allocation means
    artwork this writer must not touch.
    """
    require(len(decoded) == chunk.system_bytes + chunk.video_bytes,
            "the long-sleeve TSET decoded size changed")
    version, count = struct.unpack_from("<II", decoded, 0)
    require(version == 0x0D and count == len(rows), "the long-sleeve TSET version/reference count changed")
    textures = _textures(decoded)
    expected = ("longsleeve01", "longsleeve01_mud", "longsleeve02", "longsleeve02_mud",
                "longsleeve03", "longsleeve03_mud")
    require(tuple(textures) == expected, "the long-sleeve texture names changed")
    for target in rows:
        texture = textures[target.name]
        require(texture["pixel"] == target.pixel_offset
                and texture["palette"] == target.palette_offset
                and (texture["width"], texture["height"]) == (target.width, target.height)
                and texture["mips"] == target.mip_levels
                and texture["format"] == 0x0B,
                f"{target.asset_id} is not the reviewed long-sleeve layout")
    layouts = {(texture["pixel"], texture["width"], texture["height"], texture["mips"])
               for texture in textures.values()}
    require(len(layouts) == 1, "the long-sleeve rows no longer share one index layout")
    pixel, width, height, mips = layouts.pop()
    chain = sum(max(1, width >> level) * max(1, height >> level) for level in range(mips))
    require(pixel == 0 and chain == min(texture["palette"] for texture in textures.values())
            and len({texture["palette"] for texture in textures.values()}) == len(textures),
            "the long-sleeve shared index/palette allocation changed")
    if strict:
        video = decoded[chunk.system_bytes:]
        require(sha(video[:width * height]) == rows[0].base_pixel_sha256,
                "the long-sleeve index image is not the retail one (user artwork)")


def _looks_applied(raw: bytes, chunks) -> bool:
    """True when the package's Black and Team sleeve palettes already match."""
    chunk = chunks.get(CHUNK)
    if chunk is None or chunk.kind != "TSET":
        return False
    try:
        decoded, _ = decode_chunk(raw, chunk)
        textures = _textures(decoded)
        black = textures["longsleeve02"]
        team = textures["longsleeve03"]
        black_mud = textures["longsleeve02_mud"]
        team_mud = textures["longsleeve03_mud"]
        return (_palette_bytes(_palette(decoded, chunk, black)) == _palette_bytes(_palette(decoded, chunk, team))
                and _palette_bytes(_palette(decoded, chunk, black_mud))
                == _palette_bytes(_palette(decoded, chunk, team_mud)))
    except (ValueError, KeyError, IndexError, struct.error):
        return False


def compile_package(raw: bytes, chunks, rows: tuple[EquipmentTarget, ...], *,
                    strict: bool = False) -> tuple[bytes, dict]:
    """One package: choose the colour, edit rows 36/37 and refit the fixed TSET span."""
    chunk = chunks[CHUNK]
    span = raw[chunk.offset:chunk.end_offset]
    if _looks_applied(raw, chunks):
        return span, {"state": "already", "rule": "already-applied", "target": None, "changed_bytes": 0}
    decoded, _ = decode_chunk(raw, chunk)
    try:
        _validate_sleeve_layout(decoded, chunk, rows, strict=strict)
    except ValueError as exc:
        if strict:
            raise
        return span, {"state": "skipped", "rule": "user-art", "target": None, "changed_bytes": 0,
                      "reason": str(exc)}
    textures = _textures(decoded)
    team = textures["longsleeve03"]
    team_rows = _histogram_of(decoded, chunk, team)
    team_colour = team_rows[0][0] if team_rows else None
    code = int(rows[0].set_selector[:2])
    jersey_colour = _jersey_colour(raw, chunks)
    helmet_rows = []
    if (_is_black(team_colour)
            and (jersey_colour is None or _is_white(jersey_colour))
            and code not in CURRENT_CODES):
        helmet_rows = _helmet_histogram(raw, chunks)
    target, rule = choose_target(team_colour, jersey_colour, helmet_rows, code)

    black = textures["longsleeve02"]
    black_mud = textures["longsleeve02_mud"]
    team_mud = textures["longsleeve03_mud"]
    black_palette = _palette(decoded, chunk, black)
    team_palette = _palette(decoded, chunk, team)
    black_mud_palette = _palette(decoded, chunk, black_mud)
    team_mud_palette = _palette(decoded, chunk, team_mud)

    if rule in ("team-style", "current-team", "default"):
        wanted_black = team_palette
        wanted_team = team_palette
        wanted_black_mud = team_mud_palette
        wanted_team_mud = team_mud_palette
    else:
        wanted_black = _flat_palette(black_palette, target)
        wanted_team = _flat_palette(team_palette, target)
        wanted_black_mud = _flat_palette(black_mud_palette, _wet(target))
        wanted_team_mud = _flat_palette(team_mud_palette, _wet(target))

    if (np.array_equal(black_palette, wanted_black)
            and np.array_equal(team_palette, wanted_team)
            and np.array_equal(black_mud_palette, wanted_black_mud)
            and np.array_equal(team_mud_palette, wanted_team_mud)):
        return span, {"state": "already", "rule": rule, "target": list(target), "changed_bytes": 0}

    edited = decoded
    edited = _write_palette(edited, chunk, black, wanted_black)
    edited = _write_palette(edited, chunk, team, wanted_team)
    edited = _write_palette(edited, chunk, black_mud, wanted_black_mud)
    edited = _write_palette(edited, chunk, team_mud, wanted_team_mud)
    decoded_changed = sum(a != b for a, b in zip(decoded, edited))
    rebuilt, fit = rebuild_fixed_span_filled(span, edited, encoder="auto")
    require(len(rebuilt) == len(span), "the refitted TSET changed length")
    check, _ = decode_chunk(rebuilt, parse_chunks(rebuilt)[0])
    require(check == edited, "the recoloured TSET round trip differs")
    return rebuilt, {
        "state": "applied",
        "rule": rule,
        "target": list(target),
        "team_colour": list(team_colour) if team_colour else None,
        "jersey_colour": list(jersey_colour) if jersey_colour else None,
        "changed_bytes": decoded_changed,
        "span_changed_bytes": sum(a != b for a, b in zip(span, rebuilt)),
        "fit": asdict(fit),
    }


def apply_to_image(path, *, strict: bool = False, catalog_path=None, keep=()) -> dict:
    """Studio uniform finish pass: only fixed long-sleeve TSET spans are written.

    ``keep``: package selectors another owner pins byte for byte (b778 bd3: the historic team styles' spare that
    reuses a retail slot, the Eagles' era 9, holds the retail style-0 art); they are left as they are and listed
    under ``kept``."""
    keep = frozenset(keep)
    from pathlib import Path

    try:
        with bump._Image.open(Path(path), writable=False) as source:
            bump._parsed_index(source)
    except (ValueError, OSError):
        if strict:
            raise
        return {"state": "other_image", "written_spans": 0, "written_bytes": 0,
                "changed_bytes": 0, "packages": [], "skipped": [], "kept": []}
    by_id, groups = load_targets() if catalog_path is None else load_targets(catalog_path)
    selectors = _package_selectors(by_id)
    with bump._Image.open(Path(path), writable=True) as image:
        index = bump._parsed_index(image)
        by_name: dict[str, list] = {}
        for entry in index.entries:
            by_name.setdefault(bump.logical_name_for(entry.name_id), []).append(entry)
        plans = []
        skipped = []
        kept = []
        for selector, outer in sorted(selectors.items(), key=lambda item: item[1]):
            if selector in keep:
                kept.append(selector)
                continue
            entries = by_name.get(selector + ".IFF", [])
            if len(entries) != 1:
                skipped.append({"selector": selector, "reason": "package absent or duplicated"})
                continue
            entry = entries[0]
            raw = image.read_segments(index.sub_extents(entry, 0, entry.size))
            chunks = {chunk.index: chunk for chunk in parse_chunks(raw, allow_trailing=True)
                      if chunk.kind in ("TSET", "TXTR")}
            if CHUNK not in chunks:
                skipped.append({"selector": selector, "reason": "chunk 7 absent"})
                continue
            rebuilt, receipt = compile_package(raw, chunks, groups[(outer, CHUNK)], strict=strict)
            if receipt["state"] == "skipped":
                skipped.append({"selector": selector, **receipt})
                continue
            plans.append((entry, raw, rebuilt, receipt, selector))
        written = written_bytes = 0
        packages = []
        for entry, raw, rebuilt, receipt, selector in plans:
            if receipt["state"] == "applied":
                chunk = next(chunk for chunk in parse_chunks(raw, allow_trailing=True)
                             if chunk.index == CHUNK and chunk.kind == "TSET")
                segments = index.sub_extents(entry, chunk.offset, len(rebuilt))
                image.write_segments(segments, rebuilt)
                require(image.read_segments(segments) == rebuilt, "written span read-back differs")
                written += 1
                written_bytes += len(rebuilt)
            packages.append({"selector": selector, **{k: v for k, v in receipt.items() if k != "fit"}})
        changed = sum(item.get("changed_bytes", 0) for item in packages)
        return {"state": "applied" if written else "already_applied",
                "written_spans": written, "written_bytes": written_bytes,
                "changed_bytes": changed, "packages": packages, "skipped": skipped, "kept": kept,
                "runtime_witnessed": False}
