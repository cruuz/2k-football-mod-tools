"""Metadata-backed mesh read. EXPERIMENTAL / UNWITNESSED, all presets off.

Version 2 grows the existing owner to 2,048 RX, 256 RW and 88 RO bytes.
Rebuild from the supported base with the complete revised request union;
v1 allocations are deliberately refused, never upgraded in place. The v1
64-byte PLAY lookup remains compatible. Private state is reset at each snap
and native new-play reset, and scoped to actor/roster/assignment identity.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_read_option_runtime_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_read_option_runtime"
CODE_SIZE, DATA_SIZE, TABLE_SIZE, RO_SIZE = 2048, 256, 64, 88
MESH_FRAMES, CRASH_SAMPLES = 21, 3
AUTO_EDGE = 255
PROMPT = struct.pack("<6f", 360, 96, 0, 1, .2, 228.6)
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
TABLE_SCHEMA = "nfl2k5_read_option_lookup/v1"
HEADER = struct.Struct("<4sIII")
RECORD = struct.Struct("<5I4B")
MAX_RECORDS = (TABLE_SIZE - HEADER.size) // RECORD.size
HOOKS = {
    "tick": (0x1AF191, bytes.fromhex("d94760d81d80414e00")),
    "hud": (0x646A1, bytes.fromhex("e80a5a0900")),
    "pass_init": (0x19C849, bytes.fromhex("c70660bb1900")),
    "snap": (0xB6FBD, bytes.fromhex("8935c802e600")),
    "reset": (0x1AD9C3, bytes.fromhex("b95a000000")),
}
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: option plays use the original pitch "
    "and position rules. Patch: paired authored reads use release to give and "
    "hold the snap button to keep at the mesh. CPU QBs read the selected edge. "
    "A brief snap-button cue marks the read window. CPU reads use a live "
    "unblocked edge and sustained movement. A receiver press during the RPO "
    "mesh reaches the native pass request. All presets are off."
)


class ReadOptionError(ValueError):
    """Unsupported XBE, mixed owner or stale authored read identity."""


def _require(ok, message):
    if not ok:
        raise ReadOptionError(message)


def compile_intent_table(compilations=(), *, use_authored_edge=True):
    """Keep paired PLAY validation; optionally leave EDGE selection to the snap.

    False means there is no authored runtime defender. The required data-tier
    opponent fixture still validates the legal native condition encoding.
    """
    from .nfl2k5_play_library import compile_read_option_intent_table
    _require(type(use_authored_edge) is bool, "Expected an authored EDGE policy Boolean")
    table, receipt = compile_read_option_intent_table(compilations)
    if use_authored_edge:
        return table, receipt
    rows = []
    for record in receipt["records"]:
        row = bytearray.fromhex(record["record"])
        row[21] = AUTO_EDGE
        record.update(authored_read_slot=None, record=bytes(row).hex(), edge_selection="live snap assignments")
        rows.append(bytes(row))
    table = (table[:HEADER.size] + b"".join(sorted(rows))).ljust(TABLE_SIZE, b"\0")
    receipt.update(records=sorted(receipt["records"], key=lambda record: record["record"]),
                   table_sha256=hashlib.sha256(table).hexdigest())
    validate_intent_table(table)
    return table, receipt


def validate_intent_table(table):
    _require(isinstance(table, bytes) and len(table) == TABLE_SIZE,
             "Read option table must fill its exact read-only allocation")
    magic, version, count, flags = HEADER.unpack_from(table)
    _require((magic, version, flags) == (b"RDO1", 1, 0) and count <= MAX_RECORDS,
             "Foreign read option table header")
    rows = [table[16+i*24:40+i*24] for i in range(count)]
    _require(rows == sorted(rows) and len(set(rows)) == len(rows), "Unsorted or duplicate read option rows")
    keys = set()
    for row in rows:
        book, offset, qb, back, name, back_slot, read_slot, receiver, flags = RECORD.unpack(row)
        key = (book, offset)
        _require(0 <= offset - 0x3404 < 270*96 and (offset - 0x3404) % 96 == 0
                 and back_slot in (9, 10) and (read_slot < 11 or read_slot == AUTO_EDGE) and receiver in (0, 7, 8)
                 and flags == 0 and key not in keys, "Foreign read option identity or fields")
        keys.add(key)
    _require(not any(table[16+count*24:]), "Foreign read option table padding")
    return count


def code_for(code_va, table_va, data_va):
    symbols = dict(code=code_va, intent_table=table_va, original_tail=0x1AF19A,
                   result_tail=0x1AF210, lookup_actor=0x1894F0,
                   held_command=0x120960, receiver_ready=0x19B800,
                   state_data=data_va, hud_native=0xFA0B0, draw_icon=0xF97F0,
                   hud_tail=0x646A6, pass_tail=0x19C84F, snap_tail=0xB6FC3,
                   reset_tail=0x1AD9C8)
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "Read option exceeds the fixed owner budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [(name, va, old, b"\xe9" + struct.pack("<i", code_va + assembly.LABELS[name] - va - 5)
             + b"\x90" * (len(old) - 5)) for name, (va, old) in HOOKS.items()]


def allocations(payload):
    result = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(result) == {"code", "data", "read_only"}, "Read option allocation missing; rebuild with complete request union")
    for _, kind, size, align in REQUESTS:
        _require((result[kind]["size"], result[kind]["align"]) == (size, align), "Old/foreign Read option allocation; rebuild from base with revised requests")
    return result


def _inspect(payload):
    _require(space.status(payload) != "foreign", "Foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    owned = any(a["owner"] == OWNER for a in space.layout(payload)["allocations"])
    installed, table, code_va = False, None, 0
    if owned:
        places = allocations(payload)
        code, ro = (places[k] for k in ("code", "read_only"))
        code_va = code["va"]
        content = image.read(code_va, CODE_SIZE)
        table = image.read(ro["va"], TABLE_SIZE)
        _require(image.read(places["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE),
                 "Foreign Read option initial writable state")
        prompt = image.read(ro["va"] + TABLE_SIZE, len(PROMPT))
        if content == b"\xcc" * CODE_SIZE:
            _require(table == bytes(TABLE_SIZE) and prompt == bytes(len(PROMPT)), "Mixed Read option table without runtime")
            table = None
        else:
            _require(content == code_for(code_va, ro["va"], places["data"]["va"]), "Foreign Read option runtime")
            validate_intent_table(table)
            _require(prompt == PROMPT, "Foreign Read option prompt")
            installed = True
    for name, va, before, after in sites(code_va):
        _require(image.read(va, len(before)) == (after if installed else before), f"Mixed/foreign Read option {name}")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, address, before, _after in sites(code_va):
            if va <= address and address + len(before) <= va + size:
                content[address-va:address-va+len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"Foreign Read option dependency at {va:#x}")
    return "applied" if installed else "retail", table


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload):
    """Installed settings for inspection/status dictionaries, never a guess."""
    try:
        state, table = _inspect(payload)
        if state != 'applied':
            return None
        return dict(model_version=2, authored_reads=validate_intent_table(table),
                    table_sha256=hashlib.sha256(table).hexdigest(), mesh_frames=MESH_FRAMES, crash_samples=CRASH_SAMPLES,
                    edge_policy="snap assignments, live unblocked replacement",
                    prompt="native snap-button icon during human mesh",
                    human_control='hold snap to keep; release to give',
                    experimental=True, runtime_witnessed=False)
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return None


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
    receipt = dict(experimental=True, runtime_witnessed=False, tier="mesh", model_version=2,
                   authored_reads=count, table_sha256=hashlib.sha256(table).hexdigest(),
                   code_bytes=CODE_SIZE, instruction_bytes=assembly.LABELS['config'],
                   read_only_bytes=RO_SIZE, data_bytes=DATA_SIZE, changed_bytes=0, edits=[])
    if state == "applied":
        _require(table == previous, "Different Read option intent; rebuild from the supported source")
        return payload, {**receipt, "status": "already_applied"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated)
    content = code_for(places["code"]["va"], places["read_only"]["va"], places["data"]["va"])
    installed, code_receipt = space.install_code(allocated, OWNER, content)
    installed, table_receipt = space.install_read_only(installed, OWNER, table + PROMPT)
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
    _require(status(result) == "applied", "Read option postcondition failed")
    return result, {**receipt, "status": "applied", "allocation": allocation_receipt, "edits": edits,
                    "code_install": code_receipt, "table_install": table_receipt,
                    "reservations": reservations(result),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload)}


# Pinned dependency slices and controller tables, normalized only at our hook.
GUARDS = (
    (0x64670, 63, "8982b6527e0545f7fddf26e6ecb1aa2d39411bf3c520b4bfb925a46509080de5"),
    (0xf97f0, 345, "c89e3adfe3227a7c7d450a322434a30f147b4bb0057993d51fcfca97ec1541d0"),
    (0xf9f40, 338, "0b33d7255b461fcbfbc9895a0550af05e0dab708905d51b5c4c324178c9df5ac"),
    (0x4f68c0, 56, "28c5d41e856e75fa9e47b37d22e81051fca12739c1b5630d5008ad092f16f34f"),
    (0x19c740, 275, "661ab0647ceb5ff1e2243adccfc36dba60829f8d04caede6d74c2db0f86dab72"),
    (0x19bae0, 128, "5850cdeb4b6d6e3cd8274289163077cb7a5369b7dad434de1fa5849b18bbbd3b"),
    (0x1907d0, 27, "829ae1184284f56d36efe622c5ffc9d64ce8f91b40d5651ae09002b61e22e945"),
    (0xb6fbd, 6, "f6e77bdc1d859dd89679fa7ed6f636f66f01ea7f568617d86ae7099e09c65675"),
    (0x1ad9c0, 30, "eb8e528af8cc929aad10945d94b16079a94dd8fecad340cbc03a57115c2e7bb7"),
    (0x1af870, 689, "9732aeed45f78229952192e53c954f2459446cda65cfe58091a4b61753cbca0d"),
    (0x1aef80, 837, "abb3db24b4955ff8416ef62d65d06c746dedeb9465d4e470840d84a9c37450fe"),
    (0x1894f0, 86, "db73838ef658a792ff82f9c99bd4d5d2061f873d765322425d81293ab430b0dd"),
    (0x120960, 77, "7a454c043a4b5cfd8b4c9c4064966acffc1bac1c611ab322b5745c7fc1c5b28a"),
    (0x77230, 10, "f48cb6071a431b85a98320d0f25cd12bc268e2ac3dbeee6a9ea259622f931e38"),
    (0x4faac0, 108, "978a5172109ec5ac36db9ac4452aa409f2b99abefb6a54b4f77f8a99815b1eea"),
    (0x19b800, 79, "4e8de03e04b2794a38df1cc2f6d98deaec75462949976470f04af014379f5113"),
    (0x231ee0, 49, "64e7240b64b1ecd2cd54836c132698ca7b4d0e14deae9bfc07f77259f1a0df35"),
    (0x2b2a10, 48, "4cd7d3beca50e1e2ac5ddd6d54dba4a1e48aae015cf32f30345ff1dc0d7ff107"),
    (0x2b2db0, 48, "21e9d2ce45bad98723f588e1f5b7bf114ec63556a8daacbc6d8338330d7d3801"),
    (0x1b8a20, 179, "b0f8ec19748f768effb99d3d60e74c789a0267dc62fc1e6f03100bfd687e8bea"),
    (0x1ac7b0, 30, "c871d3c36c895993d54df874a2c253e4a2a734b9a71eec42c664e953530307a0"),
    (0x1ad2c2, 50, "bab4b870fa702e37599abe5b04735ae33a25d57beaf234c4c745c08db7ac3fc2"),
    (0xa9a004, 108, "cb90b844ecc7754d681451aa9b726d06eb0b4a4c2338bf32eb664aca68b4370a"),
    (0xa9a070, 108, "0bbbaf4719078fb9c9db2c457f09cb3b205eaa47bfe7ad84f7614a1bd7e21cef"),
    (0xa9a148, 108, "b2b4c5d8773572d43119bf1e1005498db521aac0838bceb91bcef5f91613f73d"),
    (0xa9a220, 108, "8554ad5808a1f0bf1e7fbb79d3723faaa62f67f59814dc48212dc70c70d0d277"),
    (0xa9a2f8, 108, "ba33700c6b378357a60d1e1a7ce609fea19b0b87991cab88b17fc5c38f03665e"),
    (0xa9a8e0, 108, "cb90b844ecc7754d681451aa9b726d06eb0b4a4c2338bf32eb664aca68b4370a"),
    (0xa9a94c, 108, "0bbbaf4719078fb9c9db2c457f09cb3b205eaa47bfe7ad84f7614a1bd7e21cef"),
    (0xa9aa24, 108, "b2b4c5d8773572d43119bf1e1005498db521aac0838bceb91bcef5f91613f73d"),
    (0xa9aafc, 108, "8554ad5808a1f0bf1e7fbb79d3723faaa62f67f59814dc48212dc70c70d0d277"),
    (0xa9abd4, 108, "191a644ef47c4430dd1d095441d5986d2e62ebd43adde396306250bdc2d9a2d3"),
    (0xa9b1bc, 108, "cb90b844ecc7754d681451aa9b726d06eb0b4a4c2338bf32eb664aca68b4370a"),
    (0xa9b228, 108, "0bbbaf4719078fb9c9db2c457f09cb3b205eaa47bfe7ad84f7614a1bd7e21cef"),
    (0xa9b300, 108, "b2b4c5d8773572d43119bf1e1005498db521aac0838bceb91bcef5f91613f73d"),
    (0xa9b3d8, 108, "7cf5d92da644b3d7a71e9f7a32aea5b7d4a9c70e7d3663d527e562ac2e0921f6"),
    (0xa9b4b0, 108, "688da526368a7181635c7fb0b4f97119514675040bd84ee63df9849a1e9c9ce0"),
)


def main(argv=None):
    """Development CLI; bounded XBE/table reads, exclusive output, no disc IO."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    parser.add_argument('operation', choices=('status', 'apply'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--table', type=Path, help='exact 64-byte compiled intent table')
    args = parser.parse_args(argv)
    try:
        with args.source.open('rb') as stream:
            payload = stream.read(12_300_289)
        _require(len(payload) <= 12_300_288, 'Expected a supported XBE, not a disc or archive pack')
        if args.operation == 'status':
            print(json.dumps(dict(status=status(payload), settings=read_settings(payload)), sort_keys=True))
            return 0 if status(payload) != 'foreign' else 2
        _require(args.output is not None, 'Apply requires a new --output XBE path')
        table = None
        if args.table:
            with args.table.open('rb') as stream:
                table = stream.read(TABLE_SIZE+1)
            validate_intent_table(table)
        result, receipt = apply(payload, intent_table=table)
        with args.output.open('xb') as stream:
            stream.write(result)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
