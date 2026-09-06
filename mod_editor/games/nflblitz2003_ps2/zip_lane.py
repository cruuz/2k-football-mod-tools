"""The one way this module writes: whole members, same length, three CRC sites, one new image.

Every writer lane here ends the same way and every verifier starts the same way,
so both live here once:

**Build.**  A lane hands :func:`build_replacements` the members it changed, each
already the length it had.  This module asks
:func:`~mod_editor.games._formats.blitz_zip.plan_member_replacement` for the byte
ranges -- the member's own span, its local file header's CRC-32, the central
directory's CRC-32, and the ``.ZIH`` index's CRC-32 where the disc keeps one --
applies them to copies of the two files, and hands those two whole files to the
shared ISO9660 writer.  Neither file changes length, so neither extent moves and
the image's own length is the source's.

**Verify, importing none of the patcher.**  :func:`verify_replacements` re-opens
both images with its own reader, re-derives the ZIP and the index from the
destination's bytes, and requires:

1. the two images are the same length;
2. every member the receipt did not name is byte-identical;
3. every member the receipt did name carries exactly the bytes the receipt's
   digest says, at its original offset and length;
4. the destination's index and archive still agree -- names, sizes, offsets and,
   where the disc keeps a CRC column, every CRC-32 -- and every named member's
   CRC-32 recomputes to what all three sites now carry;
5. `tools/ps2_iso9660_verify.py` re-derives the image-level claim with its own
   ISO9660 decoder.

Standard library only.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
import zlib

from mod_editor.games._formats import blitz_zip
from mod_editor.games.contract import DeclaredRange, Refusal, require

from . import containers

#: The sentence every writer here carries, because it is true of every one.
NOT_BOOTED = ("No NFL Blitz image rebuilt by this module has been booted in an emulator or on "
              "hardware; the game's acceptance of a rewritten member is not claimed anywhere.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _writer() -> Any:
    import ps2_iso9660_writer

    return ps2_iso9660_writer


def _verifier() -> Any:
    import ps2_iso9660_verify

    return ps2_iso9660_verify


def check_destination(source: Path, destination: Path) -> None:
    require(Path(destination).resolve() != Path(source).resolve(),
            f"{destination} is the source image; a build always writes a NEW image.")
    require(not os.path.lexists(destination),
            f"destination {destination} already exists; refusing to overwrite it.")


def _rewritten_pair(disc: containers.Disc, members: Mapping[str, bytes]
                    ) -> Tuple[bytes, bytes, List[Dict[str, Any]]]:
    """The two files as they will be written, and one row per member changed."""

    archive = disc.archive()
    index = disc.index()
    archive_blob = bytearray(disc.archive_bytes())
    index_blob = bytearray(disc.index_bytes())
    rows: List[Dict[str, Any]] = []
    for name in sorted(members):
        payload = members[name]
        plan = blitz_zip.plan_member_replacement(archive, index, name, payload)
        blitz_zip.apply_member_replacement(archive_blob, index_blob, plan)
        member = archive.member(name)
        rows.append({
            "member": name,
            "bytes": plan.size,
            "data_offset": member.data_offset,
            "crc32": "%08x" % plan.crc32,
            "previous_crc32": "%08x" % plan.previous_crc32,
            "sha256": sha256(payload),
            "archive_ranges": len(plan.zip_ranges),
            "index_ranges": len(plan.index_ranges),
        })
    return bytes(archive_blob), bytes(index_blob), rows


def plan_ranges(disc: containers.Disc, members: Mapping[str, bytes]
                ) -> Tuple[Tuple[DeclaredRange, ...], List[Dict[str, Any]]]:
    """What a build would declare, decided without writing anything."""

    archive_blob, index_blob, rows = _rewritten_pair(disc, members)
    replacements = {disc.archive_path: archive_blob}
    if any(row["index_ranges"] for row in rows):
        replacements[disc.index_path] = index_blob
    report = _writer().plan_report(disc.path, dict(replacements))
    ranges = tuple(DeclaredRange(item.start, item.length, item.reason)
                   for item in report["declared_ranges"])
    return ranges, rows


def build_replacements(disc: containers.Disc, destination: Path, members: Mapping[str, bytes]
                       ) -> Tuple[Dict[str, Any], Tuple[DeclaredRange, ...], List[Dict[str, Any]]]:
    """Write the new image; return the writer's JSON report, its ranges and the rows."""

    archive_blob, index_blob, rows = _rewritten_pair(disc, members)
    replacements: Dict[str, bytes] = {disc.archive_path: archive_blob}
    if any(row["index_ranges"] for row in rows):
        replacements[disc.index_path] = index_blob
    tool = _writer()
    report = tool.replace_files(disc.path, Path(destination), dict(replacements))
    json_report = tool.report_to_json(report)
    ranges = tuple(DeclaredRange(item["start"], item["length"], item["reason"])
                   for item in json_report["declared_ranges"])
    return json_report, ranges, rows


def _member_digest(disc: containers.Disc, member: Any, chunk: int = 1 << 22) -> str:
    """SHA-256 of one member's stored bytes, read in chunks so any size is comparable."""

    where = disc.pair()
    digest = hashlib.sha256()
    start, left = where.archive_offset + member.data_offset, member.size
    while left > 0:
        block = disc.read(start, min(chunk, left))
        if not block:
            break
        digest.update(block)
        start += len(block)
        left -= len(block)
    return digest.hexdigest()


def verify_replacements(source: Path, destination: Path, document: Mapping[str, Any]) -> Dict[str, Any]:
    """The independent verdict.  Imports none of the code that wrote the image."""

    rows = list(document.get("members") or ())
    changed = {str(row["member"]): row for row in rows}
    failures: List[str] = []
    checked = identical = 0

    source_size = Path(source).stat().st_size
    destination_size = Path(destination).stat().st_size
    if source_size != destination_size:
        failures.append(f"the destination is {destination_size} bytes and the source is "
                        f"{source_size}; a fixed-allocation build never changes the length")

    with containers.Disc(Path(source)) as before, containers.Disc(Path(destination)) as after:
        old_archive, new_archive = before.archive(), after.archive()
        old_index, new_index = before.index(), after.index()
        old_names = [member.name for member in old_archive.members]
        new_names = [member.name for member in new_archive.members]
        if old_names != new_names:
            failures.append("the destination's member list is not the source's")
        cross = blitz_zip.cross_check(new_index, new_archive)
        for key in ("names_match_as_sets",):
            if not cross[key]:
                failures.append(f"in the destination, the index and the archive disagree: {key}")
        for key, wanted in (("sizes_agree", len(new_archive.members)),
                            ("data_offsets_agree", len(new_archive.members))):
            if cross[key] != wanted:
                failures.append(f"in the destination, {cross[key]} of {wanted} members "
                                f"{key.replace('_', ' ')}")
        if new_index.has_crc_column and cross["crc_column_agrees"] != len(new_archive.members):
            failures.append(f"in the destination, {cross['crc_column_agrees']} of "
                            f"{len(new_archive.members)} index CRC-32 values match the archive's")

        for member in new_archive.members:
            old = old_archive.by_name().get(member.name)
            if old is None:
                continue
            if member.data_offset != old.data_offset or member.size != old.size:
                failures.append(f"{member.name} moved or changed length")
                continue
            checked += 1
            row = changed.get(member.name)
            if row is None:
                # Every member the receipt did not name must be byte-identical, including the
                # 137 MB sound bank: it is compared by streaming digest rather than skipped,
                # because a member too large to hold in memory is exactly where an undeclared
                # change would hide.
                if _member_digest(after, member) == _member_digest(before, member):
                    identical += 1
                else:
                    failures.append(f"{member.name} was not named by the receipt and its bytes "
                                    f"changed")
                continue
            payload = after.archive().member_bytes(member.name)
            if sha256(payload) != row["sha256"]:
                failures.append(f"{member.name} does not carry the bytes the receipt names")
            recomputed = zlib.crc32(payload) & 0xFFFFFFFF
            if "%08x" % recomputed != row["crc32"]:
                failures.append(f"{member.name}'s bytes do not recompute to the CRC-32 the "
                                f"receipt names")
            if member.crc32 != recomputed:
                failures.append(f"{member.name}'s central-directory CRC-32 is not its bytes'")
            entry = new_index.by_name().get(member.name)
            if entry is not None and entry.crc32 is not None and entry.crc32 != recomputed:
                failures.append(f"{member.name}'s index CRC-32 is not its bytes'")

    image_report = document.get("iso_report")
    if not image_report:
        failures.append("the receipt carries no write report")
    else:
        tool = _verifier()
        try:
            tool.verify_replacement(Path(source), Path(destination), dict(image_report))
        except tool.IsoVerifyError as exc:
            failures.append(f"at the image level: {exc}")

    return {
        "passed": not failures,
        "members_checked": checked,
        "members_byte_identical": identical,
        "members_replaced": len(changed),
        "failures": failures,
        "not_booted": NOT_BOOTED,
    }


def refuse_read_only(sentence: str) -> None:
    raise Refusal(sentence)


__all__ = ["NOT_BOOTED", "build_replacements", "check_destination", "plan_ranges",
           "refuse_read_only", "sha256", "verify_replacements"]
