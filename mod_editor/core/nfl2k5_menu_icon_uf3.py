"""uf3 (b773): the 2026 Pittsburgh road miniature helmet with its Steelmark the right way up.

The schedule and calendar screens draw ``mini_a22_0`` (64x64, P8, one level) from the ``mini`` aggregate. Its
Steelmark is turned half a turn: the blue hypocycloid sits at the top left, the red one on the left, the gold one at
the bottom right and the lettering at the upper right, where the club mark has gold at the top, red on the right,
blue at the bottom and the lettering on the left (the 128/256 ``helm_a22_0`` cards show it right). Only the inside of
the white disc turns: every texel within ``RADIUS`` of the disc centre takes the index of the texel opposite it, so
the disc rim, the shell and the facemask stay, no colour is requantised and nothing is mirrored (the lettering keeps
its handedness). The palette and every non-image byte of the slot stay the same.

Only the exact known art is changed (``BEFORE_SHA256``); retail or user art is left alone.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import nfl2k5_historic_styles as hs

TARGET = "mini_a22_0"
BEFORE_SHA256 = "eeb465c42d3285b670e28d9eaf8998d0ebac17bc6b101e4ff23f45acd41a3d38"
AFTER_SHA256 = "f5d7d63bdbcb6fd51e8cf13a34095ae917e55a0c6abf4c55e96e40ceb9985356"
CENTRE = (18.5, 19.5)          # the white disc spans columns 9-28 and rows 10-29 of the 64x64 icon
RADIUS = 8.6                   # inside the disc's dark rim (radius about 9.5)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rotate_disc(span: bytes) -> bytes:
    """Turn the inside of the Steelmark disc half a turn, losslessly (P8 indices only)."""
    from tools import nfl_txtr as tx
    chunk = tx.parse_chunks(span, allow_trailing=True)[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    t = tx.parse_texture(decoded, chunk)
    hs.require(not chunk.compressed and t.name == TARGET and t.format_code == 0x0B
               and (t.width, t.height, t.mip_levels) == (64, 64, 1), f"{TARGET}: unexpected miniature layout")
    base = 32 + chunk.system_bytes + t.pixel_offset
    linear = bytearray(tx.unswizzle_2d(span[base:base + 4096], 64, 64, 1))
    old = bytes(linear)
    cx, cy = CENTRE
    for y in range(64):
        for x in range(64):
            if (x - cx) ** 2 + (y - cy) ** 2 <= RADIUS ** 2:
                sx, sy = int(round(2 * cx - x)), int(round(2 * cy - y))
                linear[y * 64 + x] = old[sy * 64 + sx]
    out = bytearray(span)
    out[base:base + 4096] = tx.swizzle_2d(bytes(linear), 64, 64, 1)
    hs.require(len(out) == len(span), "miniature slot length changed")
    return bytes(out)


def locate(archive, name: str):
    entries = {e.name_id: e for e in archive.entries}
    aggregate = hs.AGGREGATES[1]
    record, cdf = entries[aggregate["record"]], entries[aggregate["cdf"]]
    count, size, hashes = hs.parse_record(archive.read(record.virtual_offset, record.size))
    hs.require(count * size == cdf.size, "miniature aggregate size differs from CACR")
    offset = cdf.virtual_offset + hashes.index(hs.member_hash(name)) * size
    span = archive.read(offset, size)
    hs.require(hs.slot_name(span) == name, "miniature hash/name mismatch")
    return offset, span


def plan_archive(archive):
    try:
        at, before = locate(archive, TARGET)
    except (ValueError, KeyError, hs.HistoricStylesError):
        return [], dict(state="not_applicable", written=0)
    digest = sha(before)
    after_pin = AFTER_SHA256
    if digest == after_pin:
        return [], dict(state="applied", written=0)
    if digest != BEFORE_SHA256:
        return [], dict(state="not_applicable", written=0, target_sha256=digest)
    after = rotate_disc(before)
    hs.require(sha(after) == after_pin, "Pittsburgh miniature differs from its pin")
    return [(at, before, after)], dict(state="applied", written=1, member=TARGET, virtual_offset=at,
                                       size=len(before), before_sha256=digest, after_sha256=sha(after),
                                       changed_bytes=sum(a != b for a, b in zip(before, after)))


def apply_to_image(image, *, strict=False) -> dict:
    from tools.nfl2k5_playbook_position_recode import OuterImage
    try:
        archive_cm = OuterImage(Path(image), writable=True)
        archive = archive_cm.__enter__()
    except (ValueError, OSError):
        if strict:
            raise
        return dict(state="other_image", written=0)
    try:
        plan, receipt = plan_archive(archive)
        hs.require(not strict or receipt["state"] == "applied", "the Pittsburgh miniature is not the known art")
        attempted = []
        try:
            for at, before, after in plan:
                hs.require(archive.read(at, len(before)) == before, "Pittsburgh icon changed after preflight")
                attempted.append((at, before))
                hs.require(archive.write(at, after) == len(after), "short Pittsburgh icon write")
                hs.require(archive.read(at, len(after)) == after, "Pittsburgh icon read-back differs")
            replay, _ = plan_archive(archive)
            hs.require(not replay, "Pittsburgh correction did not survive read-back")
        except BaseException:
            for at, before in reversed(attempted):
                archive.write(at, before)
            raise
    finally:
        archive_cm.__exit__(None, None, None)
    return receipt
