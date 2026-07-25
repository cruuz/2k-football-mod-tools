#!/usr/bin/env python3
"""Read, edit and write ESPN NFL 2K5 (PS2, SLUS-20919) memory-card saves.

A PS2 save is a memory-card *directory* named ``BASLUS-20919<suffix>`` holding
the payload plus its metadata sidecars::

    BASLUS-209192K5Roster/
        BASLUS-209192K5Roster   the payload (same name as the directory)
        icon.sys                dashboard title/icon metadata
        VIEW.ICO                3D icon the PS2 dashboard renders
        TYPE                    UTF-16LE save-kind code (ROS/PBK/FXG/USR/...)
        EXTRA                   u32 little-endian CRC-32 of the payload

``EXTRA`` is the whole integrity story on PS2 -- a plain reflected CRC-32 that
anyone can recompute (the Xbox release instead carries a 20-byte
platform-keyed signature, which is why Xbox save editing stays walled).  That
is what makes an offline PS2 save writer safe to ship: edit the payload,
recompute one checksum, and the save loads.

Roster payloads are a Visual Concepts ``ROST`` container -- a 0x20-byte
resource wrapper over a fixed-size arena whose ten tables are reached by the
engine's usual ``target = field_offset + int32le(field) - 1`` pointer rule.
It is the same object the disc ships, so ``tools/nfl_roster.py`` parses it
unchanged; only the preamble is leaner (version 0, root 0x20 against the
disc's 17/0x40).

Edits here are **fixed-allocation**: a replacement string must fit the bytes
the original occupies, so the arena's size, pointers and table layout never
move.  That keeps the writer bounded and lets an independent verifier prove
only the intended bytes changed (see ``nfl2k5_ps2_save_verify.py``).

Interchange format is ``.psu`` (EMS/SharkPort), which mymc, PS2 Save Builder
and PCSX2 all import, and which real hardware accepts through the usual
USB/Action-Replay routes.  Saves can also be read straight out of a ``.ps2``
memory-card image.

Usage::

    nfl2k5_ps2_save.py --inspect  <save.psu | save-dir | card.ps2>
    nfl2k5_ps2_save.py --input <save.psu> --set-player-name 42="Smith" \\
                       --output <edited.psu>
    nfl2k5_ps2_save.py --selftest
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import zlib
from dataclasses import dataclass, field

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_roster  # noqa: E402  (repo-local parser for the ROST arena)


SERIAL = "SLUS-20919"
SAVE_PREFIX = f"BA{SERIAL}"
PAYLOAD_SIDECARS = ("icon.sys", "VIEW.ICO", "COPY.ICO", "DELETE.ICO", "TYPE", "EXTRA")

# Save-kind codes, as recovered from the game executable's 14-entry registry.
TYPE_CODES = {
    "NNN": "(none)",
    "STG": "Settings",
    "OST": "Online Settings",
    "USR": "VIP File",
    "REP": "Replay",
    "ROS": "Roster",
    "PBK": "Playbook",
    "EXG": "Exhibition",
    "TMG": "Tournament",
    "FXG": "Franchise",
    "TMM": "Team",
    "PAM": "Stadium Music",
    "OUS": "OL VIP File",
    "ORS": "Online Roster",
}

ROST_MAGIC = b"ROST"
WRAPPER = struct.Struct("<4s7I")
WRAPPER_SIZE = 0x20

# Franchise saves embed a full ROST container after a settings prefix.
FRANCHISE_ROSTER_OFFSET = 0x2E0

MEMCARD_PAGE = 528          # 512 data bytes + 16 spare (ECC)
MEMCARD_PAGE_DATA = 512
PSU_ENTRY = 512
PSU_PAD = 1024
PSU_MODE_DIR = 0x8427
PSU_MODE_FILE = 0x8417


class SaveError(ValueError):
    """Raised when a save fails bounded parsing or a fail-closed edit rule."""


# --------------------------------------------------------------------------
# Save container: an ordered set of named files plus the directory name.
# --------------------------------------------------------------------------

@dataclass
class Ps2Save:
    """One PS2 memory-card save directory, held in memory."""

    directory: str
    files: dict[str, bytes] = field(default_factory=dict)
    # Raw 512-byte .psu directory entries, preserved so a rewrite keeps the
    # original timestamps/attributes byte-for-byte.
    _entries: dict[str, bytes] = field(default_factory=dict, repr=False)
    _dir_entry: bytes | None = field(default=None, repr=False)

    @property
    def payload_name(self) -> str:
        """The payload file shares its name with the save directory."""
        return self.directory

    @property
    def payload(self) -> bytes:
        try:
            return self.files[self.payload_name]
        except KeyError:
            raise SaveError(f"save {self.directory} has no payload file") from None

    @property
    def type_code(self) -> str | None:
        raw = self.files.get("TYPE")
        if not raw:
            return None
        return raw.decode("utf-16le", "replace").split("\x00")[0] or None

    @property
    def stored_crc(self) -> int | None:
        raw = self.files.get("EXTRA")
        if not raw or len(raw) < 4:
            return None
        return struct.unpack_from("<I", raw, 0)[0]

    def computed_crc(self) -> int:
        return zlib.crc32(self.payload) & 0xFFFFFFFF

    def crc_is_valid(self) -> bool:
        return self.stored_crc == self.computed_crc()

    def reseal(self) -> None:
        """Rewrite EXTRA so the save's integrity field matches its payload."""
        self.files["EXTRA"] = struct.pack("<I", self.computed_crc())


# --------------------------------------------------------------------------
# Readers: .psu archive, extracted directory, .ps2 memory-card image
# --------------------------------------------------------------------------

def read_psu(path: Path) -> Ps2Save:
    data = path.read_bytes()
    if len(data) < PSU_ENTRY:
        raise SaveError(f"{path}: too small to be a .psu")
    mode, count = struct.unpack_from("<II", data, 0)
    if not mode & 0x20:
        raise SaveError(f"{path}: first .psu entry is not a directory")
    directory = data[0x40:0x60].split(b"\x00")[0].decode("latin1")
    save = Ps2Save(directory=directory, _dir_entry=data[:PSU_ENTRY])
    off = PSU_ENTRY
    for _ in range(count):
        if off + PSU_ENTRY > len(data):
            break
        entry = data[off : off + PSU_ENTRY]
        emode, length = struct.unpack_from("<II", entry, 0)
        name = entry[0x40:0x60].split(b"\x00")[0].decode("latin1")
        off += PSU_ENTRY
        if emode & 0x20:  # "." / ".."
            continue
        save.files[name] = data[off : off + length]
        save._entries[name] = entry
        off += (length + PSU_PAD - 1) // PSU_PAD * PSU_PAD
    if not save.files:
        raise SaveError(f"{path}: no files found in .psu")
    return save


def read_directory(path: Path) -> Ps2Save:
    save = Ps2Save(directory=path.name)
    for child in sorted(path.iterdir()):
        if child.is_file():
            save.files[child.name] = child.read_bytes()
    if not save.files:
        raise SaveError(f"{path}: directory holds no save files")
    return save


def read_memcard(path: Path, directory: str | None = None) -> list[Ps2Save]:
    """Extract 2K5 saves from a PS2 memory-card image (read-only)."""
    raw = path.read_bytes()
    if len(raw) % MEMCARD_PAGE:
        raise SaveError(f"{path}: not a 528-byte-page memory-card image")

    def page(index: int) -> bytes:
        base = index * MEMCARD_PAGE
        return raw[base : base + MEMCARD_PAGE_DATA]

    superblock = page(0)
    if not superblock.startswith(b"Sony PS2 Memory Card Format"):
        raise SaveError(f"{path}: missing memory-card superblock magic")
    pages_per_cluster = struct.unpack_from("<H", superblock, 0x2A)[0]
    alloc_offset, _alloc_end, rootdir = struct.unpack_from("<III", superblock, 0x34)
    ifc_list = struct.unpack_from("<32I", superblock, 0x50)

    def cluster(index: int) -> bytes:
        first = index * pages_per_cluster
        return b"".join(page(first + i) for i in range(pages_per_cluster))

    fat: list[int] = []
    for indirect in ifc_list:
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
                raise SaveError(f"{path}: FAT chain does not terminate")

    def read_chain(start: int, length: int) -> bytes:
        out = bytearray()
        for index in chain(start):
            out += cluster(alloc_offset + index)
            if len(out) >= length:
                break
        return bytes(out[:length])

    def entries(start: int, count: int):
        seen = 0
        for index in chain(start):
            data = cluster(alloc_offset + index)
            for base in range(0, len(data), PSU_ENTRY):
                if seen >= count:
                    return
                record = data[base : base + PSU_ENTRY]
                mode, length = struct.unpack_from("<II", record, 0)
                first = struct.unpack_from("<I", record, 0x10)[0]
                name = record[0x40:0x60].split(b"\x00")[0].decode("latin1")
                yield mode, length, first, name
                seen += 1

    root_count = next(entries(rootdir, 1))[1]
    saves: list[Ps2Save] = []
    for mode, length, first, name in entries(rootdir, root_count):
        if name in (".", "..") or not mode & 0x8000 or not mode & 0x20:
            continue
        if not name.startswith(SAVE_PREFIX):
            continue
        if directory and name != directory:
            continue
        save = Ps2Save(directory=name)
        for fmode, flen, ffirst, fname in entries(first, length):
            if fname in (".", "..") or fmode & 0x20 or not fmode & 0x8000:
                continue
            save.files[fname] = read_chain(ffirst, flen)
        if save.files:
            saves.append(save)
    return saves


def load_save(path: Path, directory: str | None = None) -> Ps2Save:
    """Load one save from a .psu, an extracted directory, or a card image."""
    if path.is_dir():
        return read_directory(path)
    if path.suffix.lower() == ".ps2":
        found = read_memcard(path, directory)
        if not found:
            raise SaveError(f"{path}: no {SERIAL} saves on this memory card")
        if len(found) > 1 and not directory:
            names = ", ".join(save.directory for save in found)
            raise SaveError(f"{path}: pick one with --directory ({names})")
        return found[0]
    return read_psu(path)


# --------------------------------------------------------------------------
# Writer: emit a .psu the console and every mainstream tool accept
# --------------------------------------------------------------------------

def _psu_entry(name: str, length: int, mode: int, template: bytes | None) -> bytes:
    """Build a 512-byte .psu entry, preserving a template's timestamps."""
    entry = bytearray(template if template else bytes(PSU_ENTRY))
    if not template:
        struct.pack_into("<I", entry, 0x20, 0)  # attributes
    struct.pack_into("<I", entry, 0x00, mode)
    struct.pack_into("<I", entry, 0x04, length)
    entry[0x40:0x60] = name.encode("latin1")[:32].ljust(32, b"\x00")
    return bytes(entry)


def write_psu(save: Ps2Save, path: Path) -> None:
    """Serialize a save as .psu (dir entry, '.', '..', then padded files)."""
    names = [name for name in save.files if name == save.payload_name]
    names += [name for name in save.files if name != save.payload_name]

    out = bytearray()
    out += _psu_entry(save.directory, len(names) + 2, PSU_MODE_DIR, save._dir_entry)
    out += _psu_entry(".", 0, PSU_MODE_DIR, None)
    out += _psu_entry("..", 0, PSU_MODE_DIR, None)
    for name in names:
        payload = save.files[name]
        out += _psu_entry(name, len(payload), PSU_MODE_FILE, save._entries.get(name))
        out += payload
        pad = (-len(payload)) % PSU_PAD
        out += bytes(pad)
    path.write_bytes(bytes(out))


# --------------------------------------------------------------------------
# ROST arena: locate it, parse it, and apply fixed-allocation edits
# --------------------------------------------------------------------------

def roster_region(save: Ps2Save) -> tuple[int, int]:
    """Return (offset, length) of the ROST container inside the payload.

    Roster saves are a bare ROST container.  Franchise saves place one after a
    settings prefix, which is why the same code serves both.
    """
    payload = save.payload
    for base in (0, FRANCHISE_ROSTER_OFFSET):
        if len(payload) >= base + WRAPPER_SIZE and payload[base : base + 4] == ROST_MAGIC:
            stored = struct.unpack_from("<I", payload, base + 4)[0]
            total = WRAPPER_SIZE + stored
            if base + total <= len(payload):
                return base, total
    raise SaveError(f"{save.directory}: no ROST container in payload")


def parse_roster(save: Ps2Save) -> dict[str, object]:
    """Parse the save's ROST arena with the repo's shared roster parser."""
    base, _length = roster_region(save)
    body = save.payload[base + WRAPPER_SIZE :]
    if body[0x0C:0x10] != ROST_MAGIC:
        raise SaveError(f"{save.directory}: ROST object header is malformed")
    root = nfl_roster.relative_pointer(body, 0x14, f"{save.directory} root")
    if root is None:
        raise SaveError(f"{save.directory}: ROST root pointer is null")
    return {
        "arena_offset": base,
        "version": struct.unpack_from("<I", body, 0x10)[0],
        "root": root,
        "tables": nfl_roster.parse_tables(body, root, 0),
    }


def player_name_slots(save: Ps2Save) -> list[dict[str, object]]:
    """Locate every primary player's first/last name string, with capacity.

    Capacity is the exact byte span the stored UTF-16LE string occupies
    including its terminator; a replacement may not exceed it.
    """
    base, _length = roster_region(save)
    body_offset = base + WRAPPER_SIZE
    body = save.payload[body_offset:]
    parsed = parse_roster(save)
    table = parsed["tables"]["primary_players"]  # type: ignore[index]
    start = int(table["offset"])  # type: ignore[index]
    stride = int(table["stride"])  # type: ignore[index]
    count = int(table["count"])  # type: ignore[index]

    slots: list[dict[str, object]] = []
    for index in range(count):
        record = start + index * stride
        for label, field_offset in (("first", 0x10), ("last", 0x14)):
            pointer = nfl_roster.relative_pointer(
                body, record + field_offset, f"player {index} {label}"
            )
            if pointer is None:
                continue
            end = pointer
            while end + 2 <= len(body) and body[end : end + 2] != b"\x00\x00":
                end += 2
            slots.append({
                "player": index,
                "field": label,
                "file_offset": body_offset + pointer,
                "capacity_bytes": end - pointer + 2,
                "value": body[pointer:end].decode("utf-16le", "replace"),
            })
    return slots


def set_player_name(save: Ps2Save, player: int, field_name: str, value: str) -> dict:
    """Overwrite one player-name string in place; refuse anything that grows.

    Returns the byte range touched so a verifier can be handed an exact
    expectation rather than trusting the writer's own report.
    """
    if field_name not in ("first", "last"):
        raise SaveError(f"name field must be 'first' or 'last', not {field_name!r}")
    matches = [
        slot for slot in player_name_slots(save)
        if slot["player"] == player and slot["field"] == field_name
    ]
    if not matches:
        raise SaveError(f"player {player} has no {field_name}-name slot")
    slot = matches[0]
    encoded = value.encode("utf-16le") + b"\x00\x00"
    capacity = int(slot["capacity_bytes"])  # type: ignore[arg-type]
    if len(encoded) > capacity:
        raise SaveError(
            f"player {player} {field_name} name needs {len(encoded)} bytes but the "
            f"slot holds {capacity}; fixed-allocation edits may not grow the arena"
        )
    offset = int(slot["file_offset"])  # type: ignore[arg-type]
    payload = bytearray(save.payload)
    payload[offset : offset + capacity] = encoded.ljust(capacity, b"\x00")
    save.files[save.payload_name] = bytes(payload)
    return {
        "player": player,
        "field": field_name,
        "offset": offset,
        "length": capacity,
        "previous": slot["value"],
        "value": value,
    }


def inspect(save: Ps2Save) -> dict[str, object]:
    report: dict[str, object] = {
        "schema": "nfl2k5_ps2_save/v1",
        "serial": SERIAL,
        "directory": save.directory,
        "files": {name: len(data) for name, data in sorted(save.files.items())},
        "type_code": save.type_code,
        "type_name": TYPE_CODES.get(save.type_code or "", "unknown"),
        "payload_bytes": len(save.payload),
        "stored_crc32": save.stored_crc,
        "computed_crc32": save.computed_crc(),
        "crc_valid": save.crc_is_valid(),
    }
    try:
        parsed = parse_roster(save)
    except SaveError:
        return report
    report["roster"] = {
        "arena_offset": parsed["arena_offset"],
        "version": parsed["version"],
        "root": parsed["root"],
        "tables": {
            name: int(table["count"])  # type: ignore[index]
            for name, table in parsed["tables"].items()  # type: ignore[union-attr]
        },
    }
    return report


# --------------------------------------------------------------------------
# Self-test: exercises seal/round-trip/fail-closed rules without game data
# --------------------------------------------------------------------------

def _synthetic_save() -> Ps2Save:
    """Build a minimal but structurally real ROST save."""
    names = ["Alpha", "Bravo"]
    body = bytearray(0x400)
    body[0x0C:0x10] = ROST_MAGIC
    struct.pack_into("<I", body, 0x10, 0)          # version
    struct.pack_into("<I", body, 0x14, 0x20 - 0x14 + 1)  # root -> 0x20
    root = 0x20

    table_start, stride = 0x100, 0x54
    spec = {s.name: s for s in nfl_roster.TABLE_SPECS}["primary_players"]
    struct.pack_into("<I", body, root + spec.count_offset, len(names))
    struct.pack_into(
        "<I", body, root + spec.pointer_offset,
        table_start - (root + spec.pointer_offset) + 1,
    )
    cursor = table_start + stride * len(names)
    for index, name in enumerate(names):
        record = table_start + index * stride
        encoded = name.encode("utf-16le") + b"\x00\x00"
        body[cursor : cursor + len(encoded)] = encoded
        struct.pack_into("<I", body, record + 0x10, cursor - (record + 0x10) + 1)
        struct.pack_into("<I", body, record + 0x14, 0)  # no last name
        cursor += len(encoded)

    payload = WRAPPER.pack(ROST_MAGIC, len(body), 2, 0, 0, 0, 0, 0) + bytes(body)
    save = Ps2Save(directory=f"{SAVE_PREFIX}2K5Roster")
    save.files[save.payload_name] = payload
    save.files["TYPE"] = "ROS".encode("utf-16le") + b"\x00\x00"
    save.files["icon.sys"] = bytes(964)
    save.reseal()
    return save


def selftest(tmp: Path | None = None) -> int:
    import tempfile

    save = _synthetic_save()
    assert save.crc_is_valid(), "freshly sealed save must verify"
    assert save.type_code == "ROS", save.type_code

    slots = player_name_slots(save)
    assert [slot["value"] for slot in slots] == ["Alpha", "Bravo"], slots

    # Fixed-allocation rule: same length is fine, longer is refused.
    change = set_player_name(save, 0, "first", "Delta")
    assert change["previous"] == "Alpha"
    assert not save.crc_is_valid(), "payload changed, so the old CRC must fail"
    save.reseal()
    assert save.crc_is_valid(), "reseal must restore integrity"
    assert [slot["value"] for slot in player_name_slots(save)] == ["Delta", "Bravo"]

    try:
        set_player_name(save, 1, "first", "WayTooLongForTheSlot")
    except SaveError:
        pass
    else:  # pragma: no cover - guarded by the assertion below
        raise AssertionError("oversized name must be refused")

    # .psu round-trip must preserve every file byte-for-byte.
    with tempfile.TemporaryDirectory(dir=tmp) as work:
        out = Path(work) / "roundtrip.psu"
        write_psu(save, out)
        again = read_psu(out)
        assert again.directory == save.directory
        assert again.files == save.files, "psu round-trip changed file bytes"
        assert again.crc_is_valid()

    print("NFL2K5_PS2_SAVE_SELFTEST_PASS "
          f"players=2 psu_roundtrip=ok crc32=0x{save.computed_crc():08x}")
    return 0


# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, help=".psu, extracted save dir, or .ps2 card")
    parser.add_argument("--directory", help="save directory to pick from a card image")
    parser.add_argument("--inspect", action="store_true", help="print a JSON report")
    parser.add_argument("--list-players", action="store_true",
                        help="list primary player name slots and their capacity")
    parser.add_argument("--set-player-name", action="append", default=[],
                        metavar="INDEX:FIELD=VALUE",
                        help="fixed-allocation name edit, e.g. 42:last=Smith")
    parser.add_argument("--output", type=Path, help="write the edited save as .psu")
    parser.add_argument("--selftest", action="store_true",
                        help="verify the writer against synthetic data; no game data needed")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.input:
        parser.error("--input is required unless --selftest is given")

    save = load_save(args.input, args.directory)

    if args.inspect:
        print(json.dumps(inspect(save), indent=2))
    if args.list_players:
        for slot in player_name_slots(save):
            print(f"{slot['player']:>5} {slot['field']:<5} "
                  f"cap={slot['capacity_bytes']:<4} {slot['value']!r}")

    changes = []
    for directive in args.set_player_name:
        try:
            locator, value = directive.split("=", 1)
            index_text, field_name = locator.split(":", 1)
            index = int(index_text)
        except ValueError:
            parser.error(f"malformed --set-player-name {directive!r}; use INDEX:FIELD=VALUE")
        changes.append(set_player_name(save, index, field_name, value))

    if changes:
        save.reseal()
        if not args.output:
            parser.error("--output is required when applying edits")
        write_psu(save, args.output)
        print(json.dumps({
            "schema": "nfl2k5_ps2_save_write/v1",
            "output": str(args.output),
            "directory": save.directory,
            "changes": changes,
            "crc32": save.computed_crc(),
        }, indent=2))
    elif args.output:
        write_psu(save, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
