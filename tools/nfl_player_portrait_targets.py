#!/usr/bin/env python3
"""Fail-closed target selection for NFL 2K5 numeric roster portraits."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any


SCHEMA = "nfl2k5_player_portrait_compatibility/v1"
DEFAULT_REPORT = Path("reports/assets/nfl2k5_player_portrait_compatibility.json")
REPORT_SHA256 = "c0f792df4aa03a9a0c4e670c7b214da53a97f19526c84fd52765137120713481"
REPORT_SIZE = 9_446_076


class TargetError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


@dataclass(frozen=True)
class PortraitTarget:
    selector: str
    portrait_id: int
    name: str
    outer_index: int
    outer_id: int
    outer_size: int
    chunk_index: int
    chunk_offset: int
    slot_size: int
    span_size: int
    stored_size: int
    system_bytes: int
    video_bytes: int
    name_offset: int
    descriptor_offset: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    span_sha256: str
    decoded_sha256: str
    rgba_sha256: str
    post_span_padding_bytes: int
    post_span_padding_sha256: str
    span_segments: tuple[dict[str, Any], ...]

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "PortraitTarget":
        return cls(
            selector=str(record["selector"]), portrait_id=int(record["portrait_id"]),
            name=str(record["name"]), outer_index=int(record["outer_index"]),
            outer_id=int(record["outer_id"], 0), outer_size=int(record["outer_size"]),
            chunk_index=int(record["chunk_index"]),
            chunk_offset=int(record["chunk_offset"]),
            slot_size=int(record["slot_size"]), span_size=int(record["span_size"]),
            stored_size=int(record["stored_size"]),
            system_bytes=int(record["system_bytes"]),
            video_bytes=int(record["video_bytes"]),
            name_offset=int(record["name_offset"]),
            descriptor_offset=int(record["descriptor_offset"]),
            pixel_offset=int(record["pixel_offset"]),
            palette_offset=int(record["palette_offset"]),
            packed_format=int(record["packed_format"], 0),
            span_sha256=str(record["span_sha256"]),
            decoded_sha256=str(record["decoded_sha256"]),
            rgba_sha256=str(record["rgba_sha256"]),
            post_span_padding_bytes=int(record["post_span_padding_bytes"]),
            post_span_padding_sha256=str(record["post_span_padding_sha256"]),
            span_segments=tuple(record["span_segments"]),
        )


def load_report(path: Path = DEFAULT_REPORT) -> tuple[Path, bytes, dict[str, Any]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "portrait compatibility report must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino, opened.st_size) ==
                (supplied.st_dev, supplied.st_ino, REPORT_SIZE),
                "portrait compatibility report pathname/size changed")
        pieces: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(16 * 1024 * 1024, remaining))
            require(bool(block), "short portrait compatibility report read")
            pieces.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), "portrait compatibility report grew")
        payload = b"".join(pieces)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "portrait compatibility report changed while reading")
    finally:
        os.close(descriptor)
    require(hashlib.sha256(payload).hexdigest() == REPORT_SHA256,
            "portrait compatibility report SHA-256 mismatch")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TargetError("portrait compatibility report is invalid JSON") from exc
    require(value.get("schema") == SCHEMA and
            value.get("summary", {}).get("numeric_portrait_count") == 4303 and
            len(value.get("targets", [])) == 4303,
            "portrait compatibility report schema/count changed")
    return resolved, payload, value


def normalize(portrait_id: str | int) -> str:
    if type(portrait_id) is int:
        require(0 <= portrait_id <= 9999, "portrait ID integer is outside 0000..9999")
        name = f"{portrait_id:04d}"
    else:
        require(type(portrait_id) is str and len(portrait_id) == 4 and
                portrait_id.isascii() and portrait_id.isdecimal(),
                "portrait ID must be exactly four ASCII decimal digits")
        name = portrait_id
    return f"portrait:{name}"


def select_target(portrait_id: str | int,
                  report_path: Path = DEFAULT_REPORT) \
        -> tuple[Path, bytes, PortraitTarget]:
    selector = normalize(portrait_id)
    resolved, payload, value = load_report(report_path)
    matches = [record for record in value["targets"] if record["selector"] == selector]
    require(len(matches) == 1, f"portrait selector {selector!r} is absent or ambiguous")
    target = PortraitTarget.from_record(matches[0])
    require(target.selector == selector and target.name == selector.split(":", 1)[1] and
            target.portrait_id == int(target.name) and target.outer_index == 3105 and
            target.outer_id == 0x35CB8D72 and target.outer_size == 87_207_168 and
            target.slot_size == 17_664 and target.span_size == 17_568 and
            target.stored_size == 17_536 and target.system_bytes == 128 and
            target.video_bytes == 17_408 and target.name_offset == 32 and
            target.descriptor_offset == 44 and target.pixel_offset == 0 and
            target.palette_offset == 16_384 and target.packed_format == 0x07710B29 and
            target.post_span_padding_bytes == 96 and
            sum(int(item["size"]) for item in target.span_segments) == target.span_size and
            [int(item["span_relative_offset"]) for item in target.span_segments] ==
            ([0] if len(target.span_segments) == 1 else [0, 8448]),
            "selected portrait fixed-layout contract changed")
    return resolved, payload, target
