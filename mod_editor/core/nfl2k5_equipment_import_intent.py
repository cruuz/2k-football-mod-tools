"""Explicit equipment import intent carried with the authored PNG.

The private ancillary PNG chunk survives the existing replacement-only project,
snapshot and Undo transport without a second, unsynchronised settings ledger.
Its uppercase final letter makes it unsafe to copy after an image editor changes
pixels. The target and decoded pixel digest also reject stale/copied intent.
Ordinary PNGs continue to mean palette-only import.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib

from .errors import ValidationError


PALETTE_ONLY = "palette-only"
OWN_TEXTURE = "independent-mip-chain"
INTENT_CHUNK = b"npTC"
RETAIL_SOURCE_CHUNK = b"npRS"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCHEMA = "nfl2k5_equipment_import_intent/v1"
CHOICE_CAPTION = "Give this sock, glove or shoe its own texture"
CHOICE_HELP = (
    "Import a new design for this selected sock, glove or shoe. Other variants keep "
    "their artwork, including the separate dirty version. Smaller copies are "
    "made for distance. The original image size often cannot fit. Choose a "
    "smaller game image below, or use fewer colours and simpler shapes. "
    "Smaller images lose fine detail. Uses more game memory. Experimental / unwitnessed: check close up "
    "and at distance in a game."
)
PALETTE_HELP = (
    "Change this variant's colours using the game's shared image. "
    "This cannot add a new design or shape."
)


def _chunks(payload: bytes):
    if not payload.startswith(PNG_SIGNATURE):
        raise ValidationError("Equipment artwork must be a PNG.")
    cursor = len(PNG_SIGNATURE)
    while cursor + 12 <= len(payload):
        size, kind = struct.unpack_from(">I4s", payload, cursor)
        end = cursor + 12 + size
        if end > len(payload):
            raise ValidationError("Equipment PNG chunk is truncated.")
        data = payload[cursor + 8:end - 4]
        if zlib.crc32(kind + data) & 0xFFFFFFFF != struct.unpack_from(">I", payload, end - 4)[0]:
            raise ValidationError("Equipment PNG chunk checksum changed.")
        yield kind, data, cursor, end
        cursor = end
        if kind == b"IEND":
            if data or cursor != len(payload):
                raise ValidationError("Equipment PNG has an invalid ending.")
            return
    raise ValidationError("Equipment PNG has no ending.")


def supports_own_texture(asset_id: str) -> bool:
    import re

    return re.fullmatch(
        r"tset:\d+:(?:4:[01]:socks00(?:_mud)?|6:\d+:glove\d{2}|[89]:\d+:shoes\d{2}(?:_mud)?)",
        asset_id, re.ASCII,
    ) is not None


def import_settings(payload: bytes, asset_id: str, rgba: bytes) -> tuple[str, int]:
    records = [data for kind, data, _start, _end in _chunks(payload)
               if kind == INTENT_CHUNK]
    if not records:
        return PALETTE_ONLY, 1
    if len(records) != 1 or len(records[0]) > 1024:
        raise ValidationError("Equipment PNG repeats or exceeds its import choice.")
    try:
        record = json.loads(records[0])
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Equipment PNG import choice is invalid.") from exc
    scale = record.get("scale") if isinstance(record, dict) else None
    if type(scale) is not int or scale not in (1, 2, 4) or record != {
        "schema": SCHEMA, "asset_id": asset_id, "mode": OWN_TEXTURE,
        "rgba_sha256": hashlib.sha256(rgba).hexdigest(), "scale": scale,
    } or not supports_own_texture(asset_id):
        raise ValidationError(
            "Equipment PNG import choice no longer matches this artwork or variant. "
            "Import the edited image again and choose its texture option."
        )
    return OWN_TEXTURE, scale


def import_mode(payload: bytes, asset_id: str, rgba: bytes) -> str:
    return import_settings(payload, asset_id, rgba)[0]


def with_import_mode(payload: bytes, asset_id: str, rgba: bytes, *, independent: bool,
                     scale: int = 1) -> bytes:
    """Set an explicit UI choice on an already strictly decoded PNG snapshot."""
    if type(independent) is not bool:
        raise ValidationError("Choose whether this equipment uses its own texture.")
    if independent and not supports_own_texture(asset_id):
        raise ValidationError("Only the reviewed socks, gloves and shoes can own a texture.")
    if type(scale) is not int or scale not in (1, 2, 4):
        raise ValidationError("Equipment image size must be original, half or quarter width and height.")
    result = bytearray(PNG_SIGNATURE)
    for kind, _data, start, end in _chunks(payload):
        if kind == INTENT_CHUNK:
            continue
        if kind == b"IEND" and independent:
            data = json.dumps({
                "schema": SCHEMA, "asset_id": asset_id, "mode": OWN_TEXTURE,
                "rgba_sha256": hashlib.sha256(rgba).hexdigest(), "scale": scale,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")
            result.extend(struct.pack(">I4s", len(data), INTENT_CHUNK) + data
                          + struct.pack(">I", zlib.crc32(INTENT_CHUNK + data) & 0xFFFFFFFF))
        result.extend(payload[start:end])
    return bytes(result)


def retail_source(payload: bytes, rgba: bytes) -> str | None:
    """Portable origin hint, never authority for pixels or executable writes.

    Editors may discard this unsafe-to-copy chunk. Stale hints are ignored;
    the writer independently reopens the catalog-pinned retail source and
    compares its base pixels before preserving its original distance images.
    """
    records = [data for kind, data, *_ in _chunks(payload) if kind == RETAIL_SOURCE_CHUNK]
    if len(records) != 1 or len(records[0]) > 1024:
        return None
    try:
        record = json.loads(records[0])
    except (ValueError, UnicodeDecodeError):
        return None
    if (not isinstance(record, dict) or set(record) != {"asset_id", "rgba_sha256"}
            or not isinstance(record["asset_id"], str)
            or record["rgba_sha256"] != hashlib.sha256(rgba).hexdigest()):
        return None
    return record["asset_id"]


def with_retail_source(payload: bytes, asset_id: str | None, rgba: bytes) -> bytes:
    """Attach only a source selector and pixel digest, never retail mip bytes."""
    result = bytearray(PNG_SIGNATURE)
    for kind, _data, start, end in _chunks(payload):
        if kind == RETAIL_SOURCE_CHUNK:
            continue
        if kind == b"IEND" and asset_id is not None:
            data = json.dumps({"asset_id": asset_id, "rgba_sha256": hashlib.sha256(rgba).hexdigest()},
                              sort_keys=True, separators=(",", ":")).encode("utf-8")
            result.extend(struct.pack(">I4s", len(data), RETAIL_SOURCE_CHUNK) + data
                          + struct.pack(">I", zlib.crc32(RETAIL_SOURCE_CHUNK + data) & 0xFFFFFFFF))
        result.extend(payload[start:end])
    return bytes(result)


def same_visual_import(asset, left: bytes, left_rgba: bytes,
                       right: bytes, right_rgba: bytes) -> bool:
    """Pixel equality plus explicit intent, only for equipment replacements."""
    if left_rgba != right_rgba:
        return False
    if getattr(asset, "kind", None) != "uniform_equipment_texture":
        return True
    settings = import_settings(left, asset.asset_id, left_rgba)
    if settings != import_settings(right, asset.asset_id, right_rgba):
        return False
    # Only own-texture imports can preserve a donor's private distance images.
    # An export hint must not turn an identical palette-only import into an edit
    # or prevent the ordinary restore-to-original path.
    return settings[0] == PALETTE_ONLY or retail_source(left, left_rgba) == retail_source(right, right_rgba)
