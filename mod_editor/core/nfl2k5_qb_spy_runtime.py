"""Dedicated zone QB spy, EXPERIMENTAL / UNWITNESSED, pinned USA Xbox XBE.

Reserve REQUESTS in the complete union before any grown owner installs bytes.
Both zone callbacks are intercepted. Authored intent comes only from a sealed
versioned RO table compiled from paired PLAY resources and authoring receipts;
the native command's state+0x420 bit 29 is an independent request.

Immutable budget: 1536 RX + 512 RO = 2048 bytes; state: 768 RW. Man/rush
initializers are tier 2, specified in ASTRA_QB_SPY_RUNTIME_REPORT.md. Runtime
application has no assembler, Capstone, Unicorn, GUI or private-data dependency.
"""
from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping

from . import nfl2k5_qb_spy_runtime_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_qb_spy"
CODE_SIZE, DATA_SIZE, TABLE_SIZE = 1536, 768, 512
MAX_RECORDS = (TABLE_SIZE - 16) // 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", TABLE_SIZE, 16))
INTENT_SCHEMA = "nfl2k5_spy_intent/v1"
TABLE_SCHEMA = "nfl2k5_qb_spy_lookup/v1"
HEADER = struct.Struct("<4sIII")
RECORD = struct.Struct("<IHBBII")
BOOK_BASES = (0xB75A40, 0xB88DD0)
HOOKS = {
    "snap": (0xB6FB3, bytes.fromhex("c705b802e6000e000000")),
    "zone_first": (0x1A5790, bytes.fromhex("558bec83e4f0")),
    "zone_later": (0x1A5090, bytes.fromhex("558bec83e4f0")),
    "reset_assignment": (0x1B8570, bytes.fromhex("33c03bd0894104")),
    "reset_command": (0x18AEFC, bytes.fromhex("0fbe412e8b5e0c")),
}
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: Spy widens a zone's sideways tracking "
    "and can still follow receivers. Patch: a zone spy follows the QB at four "
    "yards, then pursues a forward or wide escape. Handoffs and passes end QB "
    "priority. Works with the Spy command and paired authored Spy plays. "
    "Man and rush assignments need a future patch. All presets keep this off."
)
# Full dependency hashes below are generated from inspected retail instructions.
# Hook bytes are normalized before checking hashes, never arbitrary mutations.
GUARDS = (
    (0xb6f30, 276, "77dbaae73aa94a3e74d06eba56bd1b722e190e6638a049852b8d5bad9a74e72b"),
    (0x1cee1b, 5, "81a617c29a3c85f5d28dd9fc2b5ba77084a548445959dd3b439441c1da8d64e7"),
    (0x1ceb4f, 54, "8085af473c56a83234c5452ec36339dea31126b62ebbd16bc7a0e736a80e9106"),
    (0x1a5790, 1071, "d59741e3621681b9bdf54611853a43c2fc02bf32a849a502a1dac05fdecbb5aa"),
    (0x1a5090, 1790, "f376d44116246f3ea5d62e7f1cb550f49129ef9dd200be3fa173a5cee1cb8231"),
    (0x18ada0, 452, "0a401683a4237ce77256e903dff6ff962601b49101c0da26aa27baf58e391f03"),
    (0x1b8570, 38, "47bba5c5c62d8963f6b848ecfbf8511844f295587ba2218a0871f4fc142d62af"),
    (0x1ce600, 680, "176b5681bfd8600c24dbde74d0a40a25320a34bce26ce00c7088ca2bd3ce9b85"),
    (0x161e30, 497, "775282ba400cb00b05892157089d8c02855ea49eaf7d764bc4fe3e7cd6abfa3f"),
    (0xe2f10, 14, "f56f719476aee8c788e58f975bacf3771328bdd1ce63060bae7c99c67c844cb5"),
    (0x1a4170, 406, "10f9e12e191bac116a46afef1416edd352c2ff33296c4edc73ed6377024ab5e2"),
    (0x1adf90, 666, "21f204be985bc0cc384cc8a0e9b1ce10f32ae5535037a2b17110ebc82d161781"),
    (0x214b90, 24, "f4147fb1c90bcd40b8d37cd38abe7c1b2449c4ba219b0b31005fb6844e6ab412"),
    (0x19dc70, 72, "1cb65fa9ca08be4007077beeb218f3bd619898a5c8591f0b166081d11d3b3b5e"),
    (0x1ac7f0, 106, "c976211c9a0f58968abecdb0c9031c312a65e250ee4653b6fa2e9483c6f6239d"),
    (0x1ab6b0, 229, "a8699d2fd196251eb5742b4ff1cb5edaa8d967c9f6b7fd4fc3a7a1dedf536765"),
    (0x1ad9c0, 42, "959a0cc681439d31c7ea6b6353bc9a3a191b34799e75dc93e59a6bf922e11086"),
)


class QbSpyError(ValueError):
    """Unsupported image, mixed owner, stale pairing or invalid lookup."""


def _require(ok, message):
    if not ok:
        raise QbSpyError(message)


def _hash(data: bytes, value=0x811C9DC5):
    for octet in data:
        value = ((value ^ octet) * 0x01000193) & 0xFFFFFFFF
    return value


def _name_bytes(body, field):
    relative = struct.unpack_from("<i", body, field)[0]
    start = field + relative - 1
    _require(relative != 0 and 0x10840 <= start <= 0x13390 - 128 and start % 2 == 0,
             "Spy identity name is outside the bounded runtime string pool")
    for end in range(start, start + 128, 2):
        if body[end:end + 2] == b"\0\0":
            _require(end > start, "Spy identity requires nonempty names")
            return body[start:end]
    raise QbSpyError("Spy identity names must fit in 63 UTF-16 code units")


def compile_intent_table(compilations=()) -> tuple[bytes, dict]:
    """Compile (exact replacement PLAY bytes, compiler receipt) pairs.

    This consumes the existing formation/play writer's versioned play/slot
    records. It never infers intent from shallow-zone bytes. All rows are
    canonical, bounded and paired to replacement_sha256; no input is mutated.
    Build calls this before allocating, even when there are no authored spies.
    """
    from . import nfl2k5_playbook_inspector as inspector
    from . import nfl2k5_play_library as library
    rows, receipts, identities = [], [], {}
    for resource, receipt in compilations:
        _require(isinstance(resource, bytes) and isinstance(receipt, Mapping), "Expected PLAY bytes and compiler receipt")
        _require(hashlib.sha256(resource).hexdigest() == receipt.get("replacement_sha256"), "Stale Spy resource/receipt pairing")
        intent = receipt.get("spy_intent")
        _require(isinstance(intent, Mapping) and set(intent) == {"schema", "records"}
                 and intent["schema"] == INTENT_SCHEMA and isinstance(intent["records"], list),
                 "Expected versioned authoring Spy records")
        book = inspector.parse_playbook_resource(resource, asset_id=receipt.get("asset_id", "spy:book"))
        body = resource[32:]
        book_name = _name_bytes(body, 0x30)
        for record in intent["records"]:
            _require(isinstance(record, Mapping) and record.get("intent") == "spy", "Unknown Spy intent record")
            pi, slot = record.get("play_index"), record.get("slot")
            _require(type(pi) is int and 0 <= pi < len(book.plays) and type(slot) is int and 0 <= slot < 11,
                     "Spy play/slot outside compiled resource")
            _require(book.plays[pi].family_id == 1, "Spy intent requires a defensive play")
            play = 0x33FC + pi * 96
            play_name = _name_bytes(body, play)
            descriptor, nodes = library.play_chains(body, pi)[1][slot]
            chain = library.decoded_chains(body, pi)[slot]
            _require([op for op, _ in chain] == [0x1B, 0x0D]
                     and abs(chain[1][1][0]) < .001 and 3 * 91.44 - .001 <= chain[1][1][1] <= 5 * 91.44 + .001,
                     "Spy lookup requires the legal centered 3-5 yard shallow-zone fallback")
            script = struct.pack("<I", descriptor) + b"".join(nodes)
            _require(len(script) == 20, "Spy script must contain two encoded nodes")
            values = (_hash(book_name), pi, slot, 1, _hash(script), _hash(play_name))
            key = values[:3]
            full_identity = (book_name, play_name, script)
            _require(key not in identities, "Duplicate or colliding Spy book/play/slot identity")
            identities[key] = full_identity
            rows.append(RECORD.pack(*values))
            receipts.append(dict(asset_id=receipt.get("asset_id"), book=book.book_name, play_index=pi,
                                 slot=slot, resource_sha256=receipt["replacement_sha256"],
                                 record=rows[-1].hex()))
    _require(len(rows) <= MAX_RECORDS, f"Spy intent capacity is {MAX_RECORDS} records; rebuild with fewer authored spies")
    ordered = sorted(rows)
    table = HEADER.pack(b"QBS1", 1, len(rows), 0) + b"".join(ordered)
    table = table.ljust(TABLE_SIZE, b"\0")
    validate_intent_table(table)
    return table, dict(schema=TABLE_SCHEMA, records=sorted(receipts, key=lambda r: r["record"]),
                       count=len(rows), capacity=MAX_RECORDS, table_sha256=hashlib.sha256(table).hexdigest(),
                       experimental=True, runtime_witnessed=False)


def validate_intent_table(table):
    _require(isinstance(table, bytes) and len(table) == TABLE_SIZE, "Spy table must fill its exact RO allocation")
    magic, version, count, flags = HEADER.unpack_from(table)
    _require((magic, version, flags) == (b"QBS1", 1, 0) and count <= MAX_RECORDS, "Foreign Spy table header")
    rows = [table[16+i*16:32+i*16] for i in range(count)]
    _require(rows == sorted(rows) and len(set(rows)) == len(rows), "Spy table must be sorted and unique")
    keys = set()
    for row in rows:
        book, pi, slot, version, _script, _name = RECORD.unpack(row)
        key = (book, pi, slot)
        _require(pi < 270 and slot < 11 and version == 1 and key not in keys, "Foreign or duplicate Spy play/slot")
        keys.add(key)
    _require(not any(table[16 + count*16:]), "Foreign Spy table padding")
    return count


def code_for(code_va, data_va, table_va):
    symbols = dict(code=code_va, state_data=data_va, intent_table=table_va,
                   resume_first=0x1A5796, resume_later=0x1A5096,
                   resume_assignment=0x1B8577, resume_command=0x18AF03, resume_snap=0xB6FBD,
                   steer=0x1A4170, pursue=0x1ADF90, transition=0x214B90)
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "Spy runtime exceeded its immutable budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [(name, va, old, b"\xe9" + struct.pack("<i", code_va + assembly.LABELS[name] - va - 5)
             + b"\x90" * (len(old) - 5)) for name, (va, old) in HOOKS.items()]


def allocations(payload):
    result = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(result) == {"code", "data", "read_only"}, "Spy allocation missing; rebuild with complete request union")
    for _, kind, size, align in REQUESTS:
        _require((result[kind]["size"], result[kind]["align"]) == (size, align), "Foreign Spy allocation")
    return result


def _inspect(payload):
    _require(space.status(payload) != "foreign", "Foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    owned = any(a["owner"] == OWNER for a in space.layout(payload)["allocations"])
    installed, table, code_va = False, None, 0
    if owned:
        places = allocations(payload)
        code, data, ro = (places[k] for k in ("code", "data", "read_only"))
        code_va = code["va"]
        content = image.read(code_va, CODE_SIZE)
        table = image.read(ro["va"], TABLE_SIZE)
        _require(image.read(data["va"], DATA_SIZE) == bytes(DATA_SIZE), "Spy offline state must be zero")
        if content == b"\xcc" * CODE_SIZE:
            _require(table == bytes(TABLE_SIZE), "Mixed Spy table without runtime")
            table = None
        else:
            _require(content == code_for(code_va, data["va"], ro["va"]), "Foreign Spy runtime")
            validate_intent_table(table)
            installed = True
    for name, va, before, after in sites(code_va):
        _require(image.read(va, len(before)) == (after if installed else before), f"Mixed/foreign Spy {name}")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, address, before, _after in sites(code_va):
            if va <= address and address + len(before) <= va + size:
                content[address-va:address-va+len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"Foreign Spy dependency at {va:#x}")
    return "applied" if installed else "retail", table


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def reservations(payload):
    places = allocations(payload)
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(va), end=hex(va + len(old)), size=len(old),
             basis="pinned live " + name + "; not a cave")
        for name, va, old, _new in sites(places["code"]["va"])]


def apply(payload: bytes, *, intent_table: bytes | None = None) -> tuple[bytes, dict]:
    """Install atomically in memory; replay keeps omitted table, refuses changes."""
    state, previous = _inspect(payload)
    table = previous if intent_table is None and previous is not None else intent_table
    if table is None:
        table = compile_intent_table()[0]
    count = validate_intent_table(table)
    receipt = dict(experimental=True, runtime_witnessed=False, tier="zone-only", model_version=1,
                   authored_spies=count, table_sha256=hashlib.sha256(table).hexdigest(),
                   code_bytes=CODE_SIZE, instruction_bytes=assembly.LABELS['config'],
                   read_only_bytes=TABLE_SIZE, data_bytes=DATA_SIZE, changed_bytes=0)
    if state == "applied":
        _require(table == previous, "Different Spy intent; rebuild from the supported source")
        return payload, {**receipt, "status": "already_applied"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated)
    content = code_for(places["code"]["va"], places["data"]["va"], places["read_only"]["va"])
    installed, _ = space.install_code(allocated, OWNER, content)
    installed, _ = space.install_read_only(installed, OWNER, table)
    image = XbeImage(installed)
    result = bytearray(installed)
    edits = []
    for name, va, before, after in sites(places["code"]["va"]):
        off = image.offset(va, len(before))
        result[off:off + len(after)] = after
        edits.append(dict(label=name, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex()))
    for section in _sections(result):
        result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    result = bytes(result)
    _require(status(result) == "applied", "Spy postcondition failed")
    return result, {**receipt, "status": "applied", "allocation": allocation_receipt, "edits": edits,
                    "reservations": reservations(result),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload)}
