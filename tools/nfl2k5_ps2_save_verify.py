#!/usr/bin/env python3
"""Independently verify an edited ESPN NFL 2K5 (PS2) save.

This is the deterministic check that stands behind the save writer: it reads
the original and edited saves and re-derives, from the bytes alone, that

  1. no file was added, removed or renamed, and every sidecar other than
     ``EXTRA`` is byte-identical;
  2. the payload changed *only* inside the byte ranges the writer declared;
  3. ``EXTRA`` equals the CRC-32 of the edited payload (and the original's
     ``EXTRA`` matched its own payload, so the baseline was sound);
  4. the ROST arena still parses and every table count *and offset* is
     unchanged, i.e. the edit stayed inside its fixed allocation instead of
     moving the arena.

**The verification re-derives the container itself.**  A verifier that reuses
the writer's parser cannot see a bug in that parser: both sides would read the
same wrong offset and agree with each other.  So everything this module checks
is decoded by the independent reader below -- its own ``.psu`` walk, its own
ROST location, its own table geometry, and its own CRC -- and the constants it
uses are written out here rather than imported.  If the two implementations
ever disagree about where something lives, verification fails instead of
rubber-stamping the writer.

It also never trusts the writer's report: the declared ranges are an input to
be checked, not evidence.  Exit status is nonzero if any check fails.

Usage::

    nfl2k5_ps2_save_verify.py --original <before.psu> --edited <after.psu> \\
        --changes <write-report.json>
    nfl2k5_ps2_save_verify.py --selftest
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import struct
import sys
import zlib


# --------------------------------------------------------------------------
# Independent reader.  Deliberately duplicated from the writer's knowledge of
# the format so the two can disagree; see the module docstring.
# --------------------------------------------------------------------------

_PSU_ENTRY = 512
_PSU_PAD = 1024
_MODE_DIRECTORY = 0x20
_ROST_MAGIC = b"ROST"
_WRAPPER_SIZE = 0x20
_FRANCHISE_PREFIX = 0x2E0

# (name, count_offset, pointer_offset, stride) for the ten ROST tables.
_TABLE_GEOMETRY = (
    ("primary_players", 0x00, 0x04, 0x54),
    ("secondary_players", 0x08, 0x0C, 0x54),
    ("stadiums", 0x10, 0x14, 0x80),
    ("teams", 0x18, 0x1C, 0x1F4),
    ("colleges", 0x20, 0x24, 0x08),
    ("coaches", 0x30, 0x34, 0xA8),
    ("player_pointer_vector", 0x38, 0x3C, 0x04),
    ("team_labels", 0x48, 0x4C, 0x08),
    ("generated_names", 0x50, 0x54, 0x08),
    ("historic_descriptors", 0x58, 0x5C, 0x10),
)


@dataclass
class DecodedSave:
    """A save as this module decoded it, without the writer's help."""

    directory: str
    files: dict[str, bytes] = field(default_factory=dict)

    @property
    def payload(self) -> bytes:
        return self.files[self.directory]

    @property
    def stored_crc(self) -> int | None:
        raw = self.files.get("EXTRA")
        if not raw or len(raw) < 4:
            return None
        return struct.unpack_from("<I", raw, 0)[0]

    def computed_crc(self) -> int:
        return zlib.crc32(self.payload) & 0xFFFFFFFF


def _relative_pointer(body: bytes, offset: int) -> int | None:
    """Resolve the engine's ``field_offset + int32le(field) - 1`` rule."""
    if offset + 4 > len(body):
        return None
    raw = struct.unpack_from("<I", body, offset)[0]
    if raw == 0:
        return None
    return offset + raw - 1


def decode_psu(path: Path) -> DecodedSave:
    """Walk a .psu without using the writer's reader."""
    data = Path(path).read_bytes()
    if len(data) < _PSU_ENTRY:
        raise VerifyError(f"{path}: too short to be a .psu")
    mode, count = struct.unpack_from("<II", data, 0)
    if not mode & _MODE_DIRECTORY:
        raise VerifyError(f"{path}: first .psu record is not a directory")
    directory = data[0x40:0x60].split(b"\x00")[0].decode("latin1")
    decoded = DecodedSave(directory=directory)
    offset = _PSU_ENTRY
    for _ in range(count):
        if offset + _PSU_ENTRY > len(data):
            break
        record = data[offset : offset + _PSU_ENTRY]
        entry_mode, length = struct.unpack_from("<II", record, 0)
        name = record[0x40:0x60].split(b"\x00")[0].decode("latin1")
        offset += _PSU_ENTRY
        if entry_mode & _MODE_DIRECTORY:
            continue
        decoded.files[name] = data[offset : offset + length]
        offset += (length + _PSU_PAD - 1) // _PSU_PAD * _PSU_PAD
    if decoded.directory not in decoded.files:
        raise VerifyError(f"{path}: no payload named {decoded.directory!r}")
    return decoded


def decode_directory(path: Path) -> DecodedSave:
    """Read an extracted save folder without using the writer's reader."""
    path = Path(path)
    decoded = DecodedSave(directory=path.name)
    for child in sorted(path.iterdir()):
        if child.is_file():
            decoded.files[child.name] = child.read_bytes()
    if decoded.directory not in decoded.files:
        raise VerifyError(f"{path}: no payload named {decoded.directory!r}")
    return decoded


def decode_memcard(path: Path, directory: str | None = None) -> DecodedSave:
    """Read a save out of a .ps2 card image without the writer's reader.

    Independently walks the superblock, the indirect FAT and the directory
    chains, so a card-sourced baseline is decoded on this module's own terms
    like every other input.
    """
    raw = Path(path).read_bytes()
    page_size = 528
    if len(raw) % page_size:
        raise VerifyError(f"{path}: not a 528-byte-page memory-card image")

    def page(index: int) -> bytes:
        base = index * page_size
        return raw[base : base + 512]

    superblock = page(0)
    if not superblock.startswith(b"Sony PS2 Memory Card Format"):
        raise VerifyError(f"{path}: missing memory-card superblock magic")
    pages_per_cluster = struct.unpack_from("<H", superblock, 0x2A)[0]
    alloc_offset, _alloc_end, rootdir = struct.unpack_from("<III", superblock, 0x34)
    indirect = struct.unpack_from("<32I", superblock, 0x50)

    def cluster(index: int) -> bytes:
        first = index * pages_per_cluster
        return b"".join(page(first + i) for i in range(pages_per_cluster))

    fat: list[int] = []
    for entry in indirect:
        if entry in (0, 0xFFFFFFFF):
            continue
        for (slot,) in struct.iter_unpack("<I", cluster(entry)):
            if slot != 0xFFFFFFFF:
                fat.extend(v for (v,) in struct.iter_unpack("<I", cluster(slot)))

    def chain(start: int):
        current, guard = start, 0
        while True:
            yield current
            if current >= len(fat):
                return
            nxt = fat[current]
            if nxt == 0xFFFFFFFF or (nxt & 0x7FFFFFFF) == 0x7FFFFFFF:
                return
            current = nxt & 0x7FFFFFFF
            guard += 1
            if guard > len(fat):
                raise VerifyError(f"{path}: FAT chain does not terminate")

    def records(start: int, count: int):
        seen = 0
        for index in chain(start):
            data = cluster(alloc_offset + index)
            for base in range(0, len(data), _PSU_ENTRY):
                if seen >= count:
                    return
                entry = data[base : base + _PSU_ENTRY]
                mode, length = struct.unpack_from("<II", entry, 0)
                first = struct.unpack_from("<I", entry, 0x10)[0]
                name = entry[0x40:0x60].split(b"\x00")[0].decode("latin1")
                yield mode, length, first, name
                seen += 1

    def read_file(start: int, length: int) -> bytes:
        out = bytearray()
        for index in chain(start):
            out += cluster(alloc_offset + index)
            if len(out) >= length:
                break
        return bytes(out[:length])

    root_count = next(records(rootdir, 1))[1]
    found: list[DecodedSave] = []
    for mode, length, first, name in records(rootdir, root_count):
        if name in (".", "..") or not mode & 0x8000 or not mode & _MODE_DIRECTORY:
            continue
        if directory and name != directory:
            continue
        decoded = DecodedSave(directory=name)
        for entry_mode, entry_len, entry_first, entry_name in records(first, length):
            if entry_name in (".", "..") or entry_mode & _MODE_DIRECTORY:
                continue
            if not entry_mode & 0x8000:
                continue
            decoded.files[entry_name] = read_file(entry_first, entry_len)
        if decoded.directory in decoded.files:
            found.append(decoded)
    if not found:
        raise VerifyError(f"{path}: no matching save on this memory card")
    if len(found) > 1:
        names = ", ".join(save.directory for save in found)
        raise VerifyError(f"{path}: pick one with --directory ({names})")
    return found[0]


def decode_save(path: Path, directory: str | None = None) -> DecodedSave:
    path = Path(path)
    if path.is_dir():
        return decode_directory(path)
    if path.suffix.lower() == ".ps2":
        return decode_memcard(path, directory)
    return decode_psu(path)


def decode_roster_tables(payload: bytes) -> dict[str, tuple[int, int]]:
    """Locate the ROST arena and return {table: (count, offset)}.

    Independently re-derived: this finds the container, follows the root
    pointer and walks the table geometry using the constants above.
    """
    base = None
    for candidate in (0, _FRANCHISE_PREFIX):
        if payload[candidate : candidate + 4] == _ROST_MAGIC:
            base = candidate
            break
    if base is None:
        raise VerifyError("no ROST container found in the payload")
    stored = struct.unpack_from("<I", payload, base + 4)[0]
    if base + _WRAPPER_SIZE + stored > len(payload):
        raise VerifyError("the ROST container overruns the payload")
    body = payload[base + _WRAPPER_SIZE :]
    if body[0x0C:0x10] != _ROST_MAGIC:
        raise VerifyError("the ROST object header is malformed")
    root = _relative_pointer(body, 0x14)
    if root is None:
        raise VerifyError("the ROST root pointer is null")
    tables: dict[str, tuple[int, int]] = {}
    for name, count_offset, pointer_offset, stride in _TABLE_GEOMETRY:
        count = struct.unpack_from("<I", body, root + count_offset)[0]
        pointer = _relative_pointer(body, root + pointer_offset)
        if pointer is None:
            if count:
                raise VerifyError(f"table {name} has {count} rows but a null pointer")
            pointer = -1
        elif pointer + count * stride > len(body):
            raise VerifyError(f"table {name} overruns the arena")
        tables[name] = (count, pointer)
    return tables


class VerifyError(AssertionError):
    """A verification contract was violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def changed_ranges(before: bytes, after: bytes) -> list[tuple[int, int]]:
    """Coalesce differing byte positions into (offset, length) spans."""
    _require(len(before) == len(after),
             f"payload size changed: {len(before)} -> {len(after)}")
    spans: list[tuple[int, int]] = []
    start = None
    for index, (lhs, rhs) in enumerate(zip(before, after)):
        if lhs != rhs:
            if start is None:
                start = index
        elif start is not None:
            spans.append((start, index - start))
            start = None
    if start is not None:
        spans.append((start, len(before) - start))
    return spans


def verify(original: DecodedSave, edited: DecodedSave,
           declared: list[dict] | None = None) -> dict:
    report: dict[str, object] = {"schema": "nfl2k5_ps2_save_verify/v1"}

    _require(original.directory == edited.directory,
             f"save directory changed: {original.directory} -> {edited.directory}")
    _require(set(original.files) == set(edited.files),
             "the set of save files changed: "
             f"{sorted(set(original.files) ^ set(edited.files))}")

    payload_name = original.directory
    for name in sorted(original.files):
        if name in (payload_name, "EXTRA"):
            continue
        _require(original.files[name] == edited.files[name],
                 f"sidecar {name} changed but only the payload and EXTRA may")

    _require(original.stored_crc == original.computed_crc(),
             "the ORIGINAL save's EXTRA does not match its payload; "
             "the baseline is not a sound reference")
    _require(edited.stored_crc == edited.computed_crc(),
             "the edited save's EXTRA does not match its payload CRC-32")

    spans = changed_ranges(original.payload, edited.payload)
    report["changed_spans"] = [{"offset": off, "length": length} for off, length in spans]
    report["changed_bytes"] = sum(length for _off, length in spans)

    if declared is not None:
        allowed = [(int(item["offset"]), int(item["length"])) for item in declared]
        for off, length in spans:
            covered = any(
                off >= a_off and off + length <= a_off + a_len
                for a_off, a_len in allowed
            )
            _require(covered,
                     f"payload changed at 0x{off:x}+{length}, which no declared "
                     "edit covers")
        report["declared_ranges"] = [
            {"offset": off, "length": length} for off, length in allowed
        ]

    before_tables = decode_roster_tables(original.payload)
    after_tables = decode_roster_tables(edited.payload)
    _require(set(before_tables) == set(after_tables), "ROST table set changed")
    for name in before_tables:
        before_count, before_offset = before_tables[name]
        after_count, after_offset = after_tables[name]
        _require(before_count == after_count,
                 f"ROST table {name} count changed "
                 f"{before_count} -> {after_count}")
        _require(before_offset == after_offset,
                 f"ROST table {name} moved; the arena must not be relocated")
    report["tables_checked"] = len(before_tables)
    report["payload_bytes"] = len(edited.payload)
    report["crc32"] = zlib.crc32(edited.payload) & 0xFFFFFFFF
    report["result"] = "PASS"
    return report


def selftest() -> int:
    """Prove the checks accept a correct edit and reject three bad ones.

    The writer is used only to *manufacture* fixtures here; every assertion
    below still runs through this module's own decoder, so the writer is the
    subject of the test rather than a participant in it.
    """
    import tempfile

    TOOLS = Path(__file__).resolve().parent
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import nfl2k5_ps2_save as writer  # fixture generator only

    def written(save) -> DecodedSave:
        """Round-trip a fixture to disk and decode it independently."""
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / "fixture.psu"
            writer.write_psu(save, path)
            return decode_psu(path)

    original = written(writer._synthetic_save())

    edited_save = writer._synthetic_save()
    change = writer.set_player_name(edited_save, 0, "first", "Delta")
    edited_save.reseal()
    report = verify(original, written(edited_save), [change])
    assert report["result"] == "PASS", report
    # Differing bytes are bounded by the declared slot; they need not fill it
    # (UTF-16LE high bytes and shared letters often match the original).
    assert 0 < report["changed_bytes"] <= change["length"], report

    # The independent decoder must agree with the writer about the arena; if
    # it ever does not, that disagreement is the whole point of this module.
    tables = decode_roster_tables(original.payload)
    assert tables["primary_players"][0] == 2, tables

    # A save whose EXTRA was not resealed must be rejected.
    forged = writer._synthetic_save()
    writer.set_player_name(forged, 0, "first", "Delta")  # no reseal
    try:
        verify(original, written(forged), [change])
    except VerifyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("stale EXTRA must fail verification")

    # An edit outside the declared range must be rejected.
    sneaky = writer._synthetic_save()
    first = writer.set_player_name(sneaky, 0, "first", "Delta")
    writer.set_player_name(sneaky, 1, "first", "Echo")
    sneaky.reseal()
    try:
        verify(original, written(sneaky), [first])
    except VerifyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("undeclared edit must fail verification")

    # A sidecar change must be rejected even when the payload is untouched.
    tampered = writer._synthetic_save()
    tampered.files["TYPE"] = b"X\x00X\x00X\x00\x00\x00"
    try:
        verify(original, written(tampered), [])
    except VerifyError:
        pass
    else:  # pragma: no cover
        raise AssertionError("a changed sidecar must fail verification")

    print("NFL2K5_PS2_SAVE_VERIFY_SELFTEST_PASS decoder=independent "
          "accepts=sealed-declared rejects=stale-crc,undeclared-edit,sidecar")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--original", type=Path, help="save before the edit")
    parser.add_argument("--edited", type=Path, help="save after the edit")
    parser.add_argument("--changes", type=Path,
                        help="writer report JSON whose declared ranges must bound the diff")
    parser.add_argument("--directory", help="save directory when reading a card image")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.original or not args.edited:
        parser.error("--original and --edited are required unless --selftest is given")

    declared = None
    if args.changes:
        payload = json.loads(args.changes.read_text(encoding="utf-8"))
        declared = payload.get("changes", payload)

    report = verify(
        decode_save(args.original, args.directory),
        decode_save(args.edited, args.directory),
        declared,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
