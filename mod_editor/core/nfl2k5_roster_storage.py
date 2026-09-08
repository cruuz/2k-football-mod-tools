"""EXPERIMENTAL / UNWITNESSED roster storage primitives, USA retail.

This revision grows the Create a Team stadium ID list to all 82 existing
records. The immutable list occupies a named RX allocation (like the boot
bitmap); it is never executable code or mutable runtime state. Reserve the
union of every selected owner's REQUESTS before the first allocator pass.

Team stride, 65 player pointers, 12 reserves and the save arena remain retail
size. A larger practice squad is a separate, unimplemented save migration.
Codec helpers below have no executable, evidence-file or optional dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

OWNER = "nfl2k5_roster_storage"
RETAIL_LIST_VA = 0x531B70
RETAIL_IDS = bytes.fromhex(
    "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e25"
    "333435363738393a3b3c3d3e3f4041424344454647494a4b4c4d4e4f5051525354551f")
ADDED_IDS = bytes((32, 36, 39, 40, 41, 42, 43, 44, 45, 48, 95, 96, 97, 98, 99))
STADIUM_IDS = RETAIL_IDS + ADDED_IDS
REQUESTS = ((OWNER, "code", len(STADIUM_IDS), 16),)
STADIUM_SIZE = 0x80
TEAM_STADIUM = 0x114
UI_TEXT = (
    "Retail: Create a Team offers 67 stadiums. Patch: Offers all 82 existing "
    "stadiums. EXPERIMENTAL / UNWITNESSED. Added previews and game loading need "
    "testing. Team and reserve limits stay the same."
)

# Entire instructions, including opcodes. The optional relocation operand is
# the final four bytes; scalars retain their original width and signedness.
POINTER_SITES = (
    (0x3191C2, bytes.fromhex("8a90701b5300")),
    (0x3192C9, bytes.fromhex("3a90701b5300")),
    (0x319340, bytes.fromhex("0fb688701b5300")),
)
VALUE_SITES = (
    (0x31926D, bytes.fromhex("b943000000"), bytes.fromhex("b952000000")),
    (0x319289, bytes.fromhex("83c042"), bytes.fromhex("83c051")),
    (0x31928D, bytes.fromhex("b943000000"), bytes.fromhex("b952000000")),
    (0x3192D7, bytes.fromhex("83f843"), bytes.fromhex("83f852")),
    (0x31934C, bytes.fromhex("83f843"), bytes.fromhex("83f852")),
    (0x31A9CE, bytes.fromhex("c705f0f7c80042000000"), bytes.fromhex("c705f0f7c80051000000")),
    (0x31A9FD, bytes.fromhex("83f843"), bytes.fromhex("83f852")),
)
# Hash complete surrounding algorithms after normalizing only the ten owned
# instructions to retail. No copied game function body is distributed.
GUARDS = (
    (0x3191B0, 0x1C0, "078308e870565d61da1b5ba788f20687d2dc87697e4c3a31795573c810b65a26"),
    (0x31A9C0, 0x68, "22410b1db5c5724823c4f2331dcaf0f2722a4a676aeff0034dd18e492bbcfcc7"),
    (RETAIL_LIST_VA, 80, "f5d214c060d9194ac73693f5b759694b4eb6b01e9a88dfdf777391e6b7ad992e"),
)


class RosterStorageError(ValueError):
    """Foreign layout, reference, allocation or incomplete patch."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RosterStorageError(message)


@dataclass(frozen=True)
class Stadium:
    index: int
    offset: int
    asset_id: int


def read_stadiums(payload: bytes | bytearray, *, root: int, end: int) -> tuple[Stadium, ...]:
    """Read record identities inside the caller's declared ROST arena only.

    Stadium ID is the byte consumed at +7C, not a record ordinal or asset-code
    suffix. Preserve all other bytes, including the three bytes after the ID.
    """
    _require(0 <= root <= end - 0x70 and end <= len(payload), "invalid ROST arena bounds")
    count, relative = struct.unpack_from("<Ii", payload, root + 0x10)
    _require(count <= 1024, "implausible stadium count")
    if not count:
        return ()
    start = root + 0x14 + relative - 1
    _require(relative != 0 and root + 0x70 <= start
             and start + count * STADIUM_SIZE <= end, "stadium table outside ROST arena")
    return tuple(Stadium(i, start + i * STADIUM_SIZE,
                         payload[start + i * STADIUM_SIZE + 0x7C]) for i in range(count))


def team_stadium(payload: bytes | bytearray, team_offset: int,
                 stadiums: tuple[Stadium, ...]) -> Stadium | None:
    """Resolve the serialized +114 pointer; interior and unrelated pointers refuse."""
    field = team_offset + TEAM_STADIUM
    _require(0 <= team_offset and field + 4 <= len(payload), "truncated team stadium pointer")
    relative = struct.unpack_from("<i", payload, field)[0]
    if not relative:
        return None
    target = field + relative - 1
    found = next((stadium for stadium in stadiums if stadium.offset == target), None)
    _require(found is not None, "team stadium is not a stadium record")
    return found


def sites(list_va: int) -> tuple[tuple[int, bytes, bytes], ...]:
    return tuple((va, old, old[:-4] + struct.pack("<I", list_va))
                 for va, old in POINTER_SITES) + VALUE_SITES


def site(payload: bytes) -> dict:
    from . import nfl2k5_xbe_space as space
    matches = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    _require(len(matches) == 1, "missing stadium allocation; reserve the full owner union on a clean base")
    allocation = matches[0]
    _require((allocation["kind"], allocation["size"], allocation["align"]) ==
             ("code", len(STADIUM_IDS), 16), "foreign stadium allocation")
    return allocation


def _recognize(payload: bytes) -> str:
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    layout = space.layout(payload)  # Geometry, code seal and every section digest.
    image = XbeImage(payload)
    allocation = site(payload) if any(a["owner"] == OWNER for a in layout["allocations"]) else None
    edits = sites(allocation["va"] if allocation else RETAIL_LIST_VA)
    values = [image.read(va, len(old)) for va, old, _new in edits]
    retail = all(value == old for value, (_va, old, _new) in zip(values, edits))
    applied = allocation is not None and all(
        value == new for value, (_va, _old, new) in zip(values, edits))
    _require(retail or applied, "mixed/foreign stadium instructions")
    for va, size, digest in GUARDS:
        normalized = bytearray(image.read(va, size))
        for address, old, _new in edits:
            if va <= address < va + size:
                normalized[address - va:address - va + len(old)] = old
        _require(hashlib.sha256(normalized).hexdigest() == digest,
                 f"foreign stadium context at {va:#x}")
    if allocation:
        content = image.read(allocation["va"], allocation["size"])
        _require(content == (STADIUM_IDS if applied else b"\xcc" * len(STADIUM_IDS)),
                 "mixed/foreign stadium list")
    return "applied" if applied else "retail"


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Install once or replay exactly; refuse foreign/mixed state before mutation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    try:
        state = _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError) as exc:
        raise RosterStorageError(f"foreign/mixed stadium input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  selectable_stadiums=82, reserve_limit=12, team_slots=65,
                  save_layout_changed=False, persistent_data_bytes=0)
    if state == "applied":
        return payload, dict(status="already_applied", changed_bytes=0, file_growth=0, edits=[], **common)
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS)
    else:
        site(payload)
        allocated, allocation_receipt = payload, {}
    allocation = site(allocated)
    installed, _ = space.install_code(allocated, OWNER, STADIUM_IDS)
    image = XbeImage(installed)
    buf = bytearray(installed)
    edits = []
    for va, old, new in sites(allocation["va"]):
        off = image.offset(va, len(old))
        buf[off:off + len(old)] = new
        edits.append(dict(label="stadium_picker_operand", va=hex(va), size=len(old),
                          before=old.hex(), after=new.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "stadium patch postcondition failed")
    edits.append(dict(label="stadium_ids", va=hex(allocation["va"]), size=len(STADIUM_IDS)))
    return result, dict(status="applied", **common, allocation=allocation_receipt, edits=edits,
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                        file_growth=len(result) - len(payload),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest(),
                        reservations=space.reservations(result))
