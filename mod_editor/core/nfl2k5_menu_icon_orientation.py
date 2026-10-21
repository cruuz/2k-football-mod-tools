"""Repair the known 2026 Denver schedule icon using its upright opposite view.

The shipped mini_a08_0 contains an inverted horse. This is not
a screen transform: the raw P8 picture itself is wrong. Reflect the existing
mini_h08_0 indices and copy its palette, keeping the destination's descriptor,
name, wrapper and padding. No artwork, retail bytes or quantization is involved.

Only exact known artwork is eligible. Retail and user-authored icons are left
alone. The same mini.cdf member serves every screen that requests this icon.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import nfl2k5_historic_styles as hs

TARGET = "mini_a08_0"
DONOR = "mini_h08_0"
BEFORE_SHA256 = "a939f90e1e3bfdc300ffe7650d9772823efbbda4e34031e84873e5ac1c2405b7"
DONOR_SHA256 = "253670b1dd97f1b0af7d7fd42982797e64857bc43f4a1f8741a154dfde4408a3"
AFTER_SHA256 = "b962df80a37124daf188b7890ae8505527ea08de5a0f9aa7654d0732c038f732"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reflect_slot(target: bytes, donor: bytes) -> bytes:
    """Lossless P8 reflection, preserving every destination non-image byte."""
    from tools import nfl_txtr as tx
    parsed = []
    for span, name in ((target, TARGET), (donor, DONOR)):
        chunk = tx.parse_chunks(span, allow_trailing=True)[0]
        decoded, _ = tx.decode_chunk(span, chunk)
        t = tx.parse_texture(decoded, chunk)
        hs.require(not chunk.compressed and t.name == name and t.format_code == 0x0B
                   and (t.width, t.height, t.mip_levels) == (64, 64, 1),
                   f"{name}: unexpected miniature layout")
        hs.require(t.pixel_offset + 4096 <= chunk.video_bytes
                   and t.palette_offset >= t.pixel_offset + 4096
                   and t.palette_offset + 1024 <= chunk.video_bytes,
                   f"{name}: invalid P8 image ranges")
        parsed.append((32 + chunk.system_bytes, t))
    (tb, tt), (db, dt) = parsed
    linear = tx.unswizzle_2d(donor[db + dt.pixel_offset:db + dt.pixel_offset + 4096], 64, 64, 1)
    reflected = b"".join(linear[y * 64:(y + 1) * 64][::-1] for y in range(64))
    result = bytearray(target)
    result[tb + tt.pixel_offset:tb + tt.pixel_offset + 4096] = tx.swizzle_2d(reflected, 64, 64, 1)
    result[tb + tt.palette_offset:tb + tt.palette_offset + 1024] = donor[db + dt.palette_offset:db + dt.palette_offset + 1024]
    hs.require(len(result) == len(target), "miniature slot length changed")
    return bytes(result)


def locate(archive, name: str) -> tuple[int, bytes]:
    """Resolve the member by CACR hash, including after aggregate relocation."""
    entries = {e.name_id: e for e in archive.entries}
    aggregate = hs.AGGREGATES[1]
    record, cdf = entries[aggregate["record"]], entries[aggregate["cdf"]]
    count, size, hashes = hs.parse_record(archive.read(record.virtual_offset, record.size))
    hs.require(count * size == cdf.size, "miniature aggregate size differs from CACR")
    offset = cdf.virtual_offset + hashes.index(hs.member_hash(name)) * size
    span = archive.read(offset, size)
    hs.require(hs.slot_name(span) == name, "miniature hash/name mismatch")
    return offset, span


def plan_archive(archive) -> tuple[list, dict]:
    try:
        at, before = locate(archive, TARGET)
    except (ValueError, KeyError, hs.HistoricStylesError):
        # Same contract as the Pittsburgh miniature step: an archive without the miniature aggregate or member is
        # not the known art (a synthetic or foreign image), so there is nothing to correct.
        return [], dict(state="not_applicable", written=0)
    digest = sha(before)
    if digest == AFTER_SHA256:
        return [], dict(state="applied", written=0)
    if digest != BEFORE_SHA256:
        return [], dict(state="not_applicable", written=0, target_sha256=digest)
    _, donor = locate(archive, DONOR)
    hs.require(sha(donor) == DONOR_SHA256, "Denver opposite-view donor differs from its pin")
    after = reflect_slot(before, donor)
    hs.require(sha(after) == AFTER_SHA256, "Denver correction differs from its pin")
    return [(at, before, after)], dict(state="applied", written=1, member=TARGET,
        donor=DONOR, virtual_offset=at, size=len(before), before_sha256=digest,
        after_sha256=sha(after), changed_bytes=sum(a != b for a, b in zip(before, after)))


def apply_to_image(image) -> dict:
    from tools.nfl2k5_playbook_position_recode import OuterImage
    try:
        archive_cm = OuterImage(Path(image), writable=True)
        archive = archive_cm.__enter__()
    except (ValueError, OSError):
        # Same contract as the Pittsburgh miniature step beside it: an image without the main pack folder is not
        # NFL 2K5 (a synthetic or foreign image) and has no miniature to correct. Nothing is written.
        return dict(state="other_image", written=0)
    try:
        plan, receipt = plan_archive(archive)
        attempted = []
        try:
            for at, before, after in plan:
                hs.require(archive.read(at, len(before)) == before, "Denver icon changed after preflight")
                attempted.append((at, before))
                hs.require(archive.write(at, after) == len(after), "short Denver icon write")
                hs.require(archive.read(at, len(after)) == after, "Denver icon read-back differs")
            replay, _ = plan_archive(archive)
            hs.require(not replay, "Denver correction did not survive read-back")
        except BaseException:
            for at, before in reversed(attempted):
                archive.write(at, before)
            raise
    finally:
        archive_cm.__exit__(None, None, None)
    return receipt
