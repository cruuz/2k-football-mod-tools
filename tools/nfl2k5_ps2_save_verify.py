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
_PAGE = 528
_PAGE_DATA = 512
_ECC_CHUNK = 128
_ECC_SPARE_USED = 12
_ERASED_SPARE = b"\xff" * _ECC_SPARE_USED

# Page-ECC constants, restated here rather than imported: a verifier that
# borrowed the writer's ECC could only ever agree with it.
_ECC_BASIS = (0x07, 0x16, 0x25, 0x34, 0x43, 0x52, 0x61, 0x70)
_ECC_COLUMN_SEED = 0x77
_ECC_LINE_SEED = 0x7F
_ECC_LINE_MASK = 0x7F

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


def _memcard_directories(path: Path) -> list[str]:
    """Names of every save directory on a card, in on-card order."""
    raw = Path(path).read_bytes()

    def page(index: int) -> bytes:
        base = index * _PAGE
        return raw[base : base + _PAGE_DATA]

    superblock = page(0)
    if not superblock.startswith(b"Sony PS2 Memory Card Format"):
        raise VerifyError(f"{path}: missing memory-card superblock magic")
    pages_per_cluster = struct.unpack_from("<H", superblock, 0x2A)[0]
    alloc_offset, _end, rootdir = struct.unpack_from("<III", superblock, 0x34)
    indirect_list = struct.unpack_from("<32I", superblock, 0x50)

    def cluster(index: int) -> bytes:
        first = index * pages_per_cluster
        return b"".join(page(first + i) for i in range(pages_per_cluster))

    fat: list[int] = []
    for indirect in indirect_list:
        if indirect in (0, 0xFFFFFFFF):
            continue
        for (entry,) in struct.iter_unpack("<I", cluster(indirect)):
            if entry != 0xFFFFFFFF:
                fat.extend(v for (v,) in struct.iter_unpack("<I", cluster(entry)))

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
                name = entry[0x40:0x60].split(b"\x00")[0].decode("latin1")
                yield mode, length, name
                seen += 1

    root_count = next(records(rootdir, 1))[1]
    names: list[str] = []
    for mode, _length, name in records(rootdir, root_count):
        if name in (".", "..") or not mode & 0x8000 or not mode & _MODE_DIRECTORY:
            continue
        names.append(name)
    return names


def _chunk_ecc(chunk: bytes) -> bytes:
    """Independently compute the three ECC bytes for one 128-byte chunk."""
    column = _ECC_COLUMN_SEED
    line_a = line_b = _ECC_LINE_SEED
    for index, value in enumerate(chunk):
        mask = 0
        for bit in range(8):
            if value >> bit & 1:
                mask ^= _ECC_BASIS[bit]
        column ^= mask
        parity = value
        parity ^= parity >> 4
        parity ^= parity >> 2
        parity ^= parity >> 1
        if parity & 1:
            line_a ^= (~index) & _ECC_LINE_MASK
            line_b ^= index
    return bytes((column & 0xFF, line_a & _ECC_LINE_MASK, line_b & _ECC_LINE_MASK))


def audit_memcard_ecc(path: Path) -> dict:
    """Check every written page of a card image against recomputed ECC.

    Erased pages carry ``FF`` spare bytes rather than a computed value and are
    counted separately instead of being reported as damage.
    """
    raw = Path(path).read_bytes()
    if len(raw) % _PAGE:
        raise VerifyError(f"{path}: not a {_PAGE}-byte-page memory-card image")
    checked = erased = 0
    bad: list[int] = []
    for page in range(len(raw) // _PAGE):
        base = page * _PAGE
        data = raw[base : base + _PAGE_DATA]
        spare = raw[base + _PAGE_DATA : base + _PAGE][:_ECC_SPARE_USED]
        if spare == _ERASED_SPARE:
            erased += 1
            continue
        expected = b"".join(
            _chunk_ecc(data[start : start + _ECC_CHUNK])
            for start in range(0, _PAGE_DATA, _ECC_CHUNK)
        )
        checked += 1
        if expected != spare:
            bad.append(page)
    return {
        "pages_checked": checked,
        "pages_erased": erased,
        "pages_bad": len(bad),
        "first_bad_pages": bad[:8],
    }


def verify_memcard_write(
    original_card: Path, written_card: Path, directory: str,
    declared: list[dict] | None = None,
) -> dict:
    """Verify a save edited directly into a memory-card image.

    Beyond the usual save checks this proves the card itself is sound: every
    written page carries correct ECC, and every *other* save on the card is
    byte-identical, so an in-place write cannot quietly damage a neighbour.
    """
    report: dict[str, object] = {"schema": "nfl2k5_ps2_memcard_verify/v1"}

    ecc = audit_memcard_ecc(written_card)
    _require(
        ecc["pages_bad"] == 0,
        f"{ecc['pages_bad']} page(s) on the written card have wrong ECC "
        f"(first: {ecc['first_bad_pages']})",
    )
    report["ecc"] = ecc

    before_all = {save.directory: save for save in decode_memcard_all(original_card)}
    after_all = {save.directory: save for save in decode_memcard_all(written_card)}
    _require(
        set(before_all) == set(after_all),
        "the set of saves on the card changed: "
        f"{sorted(set(before_all) ^ set(after_all))}",
    )
    _require(directory in after_all, f"{written_card} has no save named {directory}")

    untouched = []
    for name in sorted(before_all):
        if name == directory:
            continue
        _require(
            before_all[name].files == after_all[name].files,
            f"save {name} changed, but only {directory} may be written",
        )
        untouched.append(name)
    report["other_saves_untouched"] = untouched

    report["save"] = verify(before_all[directory], after_all[directory], declared)
    report["result"] = "PASS"
    return report


def decode_memcard_all(path: Path) -> list[DecodedSave]:
    """Every 2K5 save on a card, decoded independently."""
    saves: list[DecodedSave] = []
    for name in _memcard_directories(path):
        saves.append(decode_memcard(path, name))
    return saves


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
    if not (report["result"] == "PASS"):
        raise VerifyError(report)
    # Differing bytes are bounded by the declared slot; they need not fill it
    # (UTF-16LE high bytes and shared letters often match the original).
    if not (0 < report["changed_bytes"] <= change["length"]):
        raise VerifyError(report)

    # The independent decoder must agree with the writer about the arena; if
    # it ever does not, that disagreement is the whole point of this module.
    tables = decode_roster_tables(original.payload)
    if not (tables["primary_players"][0] == 2):
        raise VerifyError(tables)

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

    # Page ECC, recomputed here rather than imported from the writer. These
    # vectors are non-degenerate on purpose: an all-zero or all-one chunk
    # cancels to the seed and would pass a broken implementation, while a
    # single set bit at index 0 versus index 1 pins the position-dependent
    # line parity.
    ecc_vectors = (
        (bytes(_ECC_CHUNK), "777f7f", "an empty chunk must return the seed"),
        (bytes([1]) + bytes(127), "70007f", "a set bit at index 0"),
        (bytes([0, 1]) + bytes(126), "70017e", "a set bit at index 1"),
        (bytes([0x80]) + bytes(127), "07007f", "a high bit at index 0"),
    )
    for chunk, expected, why in ecc_vectors:
        got = _chunk_ecc(chunk).hex()
        if got != expected:
            raise VerifyError(f"page ECC wrong for {why}: {got} != {expected}")

    print("NFL2K5_PS2_SAVE_VERIFY_SELFTEST_PASS decoder=independent ecc=independent "
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
