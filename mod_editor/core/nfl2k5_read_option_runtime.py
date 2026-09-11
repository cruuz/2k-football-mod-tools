"""Cancelable native read mesh. EXPERIMENTAL / UNWITNESSED, all presets off.

V5 uses the team's loaded book and exact paired fingerprints, starts native
GIVE/TAKE on snap reception, and samples pull controls until native transfer.
The human diagnostic retains the v4 CPU-give policy within the same reservation.
Old executable variants require a clean rebuild; no in-place upgrades.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_read_option_runtime_code as assembly
from . import nfl2k5_xbe_space as space
from . import nfl2k5_playbook_pair as pair
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_read_option_runtime"
CODE_SIZE, DATA_SIZE, TABLE_SIZE, RO_SIZE = 2048, 256, 64, 88
MESH_SECONDS, CRASH_SAMPLES = 1.0, 3
# Nominal samples at 60 Hz, including the initial sample; expiry uses time.
MESH_FRAMES = 61
AUTO_EDGE = 255
# Retain the RO layout: close pitch radius, legacy HUD fields, prediction
# time and read radius. Diagnostic marker replaces one unused HUD field.
PROMPT = struct.pack("<6f", 91.44, 96, 0, 1, .2, 228.6)
DIAGNOSTIC_PROMPT = PROMPT[:4] + b"RDV5" + PROMPT[8:]
# Offsets within the owner's named RW allocation, NOT fixed Xbox addresses.
DIAGNOSTIC_FIELDS = dict(actor=0, descriptor=4, roster=8, lookup_row=12,
    sample_clock=16, samples=20, controller=24, decision=28, back=32,
    receiver=36, edge=40, deadline=44, snap_seen=48, play_index=52,
    native_play_index=56, book=60, keep_armed=64, confidence=68,
    crash=72, started=76, lane=80, depth=84, raw_held=88, raw_pressed=92)
DECISIONS = {0: "keep", 1: "give", 2: "pass", 3: "pitch", 4: "stop", 0xFFFFFFFF: "pend"}

REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
TABLE_SCHEMA = "nfl2k5_read_option_lookup/v1"
HEADER = struct.Struct("<4sIII")
RECORD = struct.Struct("<5I4B")
MAX_RECORDS = (TABLE_SIZE - HEADER.size) // RECORD.size
HOOKS = {
    "tick": (0x1AF009, bytes.fromhex("d944241cd81d0ca55000")),
    "schedule": (0x21516A, bytes.fromhex("8b44243033f6")),
    "hud": (0x646A1, bytes.fromhex("e80a5a0900")),
    "pass_init": (0x19C849, bytes.fromhex("c70660bb1900")),
    "snap": (0xB6FBD, bytes.fromhex("8935c802e600")),
    "reset": (0x1AD9C3, bytes.fromhex("b95a000000")),
    "exchange": (0x313520, bytes.fromhex("558bec83e4f0")),
}
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: original option controls. Patch: "
    "paired reads begin a native handoff after the snap. Do nothing to give. "
    "Before the ball leaves the QB, press Black to pull and pitch, or release "
    "A after snapping and press A again to pull and keep. On an RPO, press X "
    "or the named receiver button to pull and pass. These are Xbox button "
    "names; use your controller mapping. The stick waits until the decision. "
    "The CPU reads the unblocked edge. Noah witnessed the v4 snap hook and "
    "READ line, but these new controls and the animated exchange are unwitnessed. "
    "All presets are off."
)
DIAGNOSTIC_HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: original option controls. Patch: "
    "human read diagnostic. READ shows the resolved resource play number, "
    "then snap, pend, give, keep, pitch or pass. Photograph the line and the "
    "ball exchange separately. A miss shows the actual loaded-table index, "
    "not an assumed editor-buffer offset. Human controls are the same as v5. "
    "CPU reads give in this diagnostic variant."
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
    from .nfl2k5_play_intents import table_compiler_pairs, final_table_receipt, certify_read_identities
    _require(type(use_authored_edge) is bool, "Expected an authored EDGE policy Boolean")
    pairs, final_hashes = table_compiler_pairs(compilations)
    table, receipt = compile_read_option_intent_table(pairs)
    certify_read_identities(pairs, receipt)
    final_table_receipt(receipt, final_hashes)
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
    keys, fingerprints = set(), set()
    for row in rows:
        book, offset, qb, back, name, back_slot, read_slot, receiver, flags = RECORD.unpack(row)
        key = (book, offset)
        fingerprint = (book, qb, back, name, back_slot)
        _require(0 <= offset - 0x3404 < 270*96 and (offset - 0x3404) % 96 == 0
                 and back_slot in (9, 10) and (read_slot < 11 or read_slot == AUTO_EDGE) and receiver in (0, 7, 8)
                 and flags == 0 and key not in keys and fingerprint not in fingerprints,
                 "Foreign read option identity or fields")
        keys.add(key)
        fingerprints.add(fingerprint)
    _require(not any(table[16+count*24:]), "Foreign read option table padding")
    return count


def code_for(code_va, table_va, data_va, *, diagnostic=False, paired_contract=0):
    symbols = dict(code=code_va, intent_table=table_va, original_tail=0x1AF013,
                   paired_contract=paired_contract,
                   result_tail=0x1AF210, lookup_actor=0x1894F0,
                   held_command=0x120960, receiver_ready=0x19B800,
                   state_data=data_va, hud_native=0xFA0B0, draw_icon=0xF97F0,
                   hud_tail=0x646A6, pass_tail=0x19C84F, snap_tail=0xB6FC3,
                   reset_tail=0x1AD9C8, schedule_tail=0x215170, schedule_mesh=0x215367,
                   draw_text=0x47420, exchange_tail=0x313526,
                   animation_change=0x1cd550, set_node=0x1b8790,
                   decode_node=0x1b84e0, transition=0x214b90,
                   give_init=0x300b00, pass_native=0x19c740,
                   carry_init=0x2e36f0)
    symbols['schedule_human'] = 0x215275
    result = bytearray(assembly.DIAGNOSTIC_CODE if diagnostic else assembly.CODE)
    for offset, kind, symbol, value in (assembly.DIAGNOSTIC_RELOCATIONS if diagnostic else assembly.RELOCATIONS):
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "Read option exceeds the fixed owner budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def sites(code_va, *, diagnostic=False):
    labels = assembly.DIAGNOSTIC_LABELS if diagnostic else assembly.LABELS
    return [(name, va, old, b"\xe9" + struct.pack("<i", code_va + labels[name] - va - 5)
             + b"\x90" * (len(old) - 5)) for name, (va, old) in HOOKS.items()]


def allocations(payload):
    result = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(result) == {"code", "data", "read_only"}, "Read option allocation missing; rebuild with complete request union")
    for _, kind, size, align in REQUESTS:
        _require((result[kind]["size"], result[kind]["align"]) == (size, align), "Old/foreign Read option allocation; rebuild from base with revised requests")
    return result


def _inspect_owner(payload, image):
    """Check owned bytes without dependencies; caller validates the allocator.

    Screen hooks uses this first phase to validate our exact detours without
    recursively entering status while checking the shared pass initializer.
    """
    owned = any(a["owner"] == OWNER for a in space.layout(payload)["allocations"])
    installed, table, code_va, diagnostic = False, None, 0, False
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
            diagnostic = content == code_for(code_va, ro["va"], places["data"]["va"], diagnostic=True,
                                             paired_contract=pair.contract_va(payload))
            _require(diagnostic or content == code_for(code_va, ro["va"], places["data"]["va"],
                                                     paired_contract=pair.contract_va(payload)),
                     "Foreign Read option runtime")
            validate_intent_table(table)
            _require(prompt == (DIAGNOSTIC_PROMPT if diagnostic else PROMPT), "Foreign Read option prompt")
            installed = True
    checked_sites = sites(code_va, diagnostic=diagnostic)
    for name, va, before, after in checked_sites:
        _require(image.read(va, len(before)) == (after if installed else before), f"Mixed/foreign Read option {name}")
    return installed, table, checked_sites


def _check_dependencies(image, checked_sites):
    """Normalize only hook spans already checked against their complete owner."""
    checked_sites = list(checked_sites)
    from . import nfl2k5_abilities_runtime as abilities
    va, before = abilities.HOOKS['initialize']
    if image.read(va, len(before)) != before:
        # Cancellation uses the same native animation entry. Validate the
        # complete sealed abilities owner before normalizing its prologue.
        _require(abilities.status(image.data) == 'applied', 'Foreign abilities animation neighbor')
        checked_sites.append(('abilities_initialize', va, before, None))
    from . import nfl2k5_defensive_try as defensive_try
    va, before_hex, _kind = defensive_try.HOOKS['cpu_return']
    before = bytes.fromhex(before_hex)
    if image.read(va, len(before)) != before:
        _require(defensive_try.status(image.data) == 'applied', 'Foreign defensive try carry neighbor')
        checked_sites.append(('defensive_try_cpu_return', va, before, None))
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, address, before, _after in checked_sites:
            if va <= address and address + len(before) <= va + size:
                content[address-va:address-va+len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest, f"Foreign Read option dependency at {va:#x}")


def _inspect(payload):
    _require(space.status(payload) != "foreign", "Foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    installed, table, checked_sites = _inspect_owner(payload, image)
    from . import nfl2k5_screen_hooks as screen
    va, before = screen.HOOKS["qb"]
    if image.read(va, len(before)) != before:
        # Disjoint timer store at 0x19c7e9, before our callback store at
        # 0x19c849. Validate both owners before normalizing either detour.
        neighbor_installed, neighbor_sites = screen._inspect_owner(payload, image)
        _require(neighbor_installed, "Foreign screen hooks pass initializer neighbor")
        checked_sites += neighbor_sites
        screen._check_dependencies(image, checked_sites)
    _check_dependencies(image, checked_sites)
    if installed and _diagnostic_installed(payload):
        for va, size, digest in DIAGNOSTIC_GUARDS:
            _require(hashlib.sha256(image.read(va, size)).hexdigest() == digest,
                     f"Foreign Read option diagnostic dependency at {va:#x}")
    return "applied" if installed else "retail", table


def _diagnostic_installed(payload):
    places = allocations(payload)
    return XbeImage(payload).read(places['read_only']['va']+TABLE_SIZE, len(PROMPT)) == DIAGNOSTIC_PROMPT


def decode_diagnostic_state(data):
    """Decode exactly one owner's memory dump, never an XBE or guessed address.

    This is observation, not validation of live pointers or proof that text
    appeared on a display. The caller finds the RW allocation in the receipt.
    """
    _require(isinstance(data, bytes) and len(data) == DATA_SIZE,
             "Expected the owner's exact 256-byte RW memory dump")
    values = {name: struct.unpack_from('<I', data, offset)[0]
              for name, offset in DIAGNOSTIC_FIELDS.items() if name != 'text'}
    import math
    for name in ('sample_clock', 'deadline', 'lane', 'depth'):
        value = struct.unpack_from('<f', data, DIAGNOSTIC_FIELDS[name])[0]
        values[name + '_bits'] = hex(values[name])
        values[name] = value if math.isfinite(value) else str(value)
    values['phase'] = ('off' if not values['snap_seen'] else
        'miss' if not values['lookup_row'] else 'snap' if not values['started'] else
        DECISIONS.get(values['decision'], 'unknown'))
    number = values['native_play_index'] if values['phase'] == 'miss' else values['play_index']
    label = '???' if number == 0xFFFFFFFF else str(number)
    values['text'] = ('' if values['phase'] == 'off' else 'READ miss '+label
                      if values['phase'] == 'miss' else 'READ '+label+' '+values['phase'])
    values['runtime_witnessed'] = False
    return values


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
        diagnostic = _diagnostic_installed(payload)
        return dict(model_version=5, diagnostic=diagnostic,
                    authored_reads=validate_intent_table(table),
                    table_sha256=hashlib.sha256(table).hexdigest(), mesh_seconds=MESH_SECONDS,
                    mesh_frames=MESH_FRAMES, crash_samples=CRASH_SAMPLES,
                    edge_policy="diagnostic CPU gives" if diagnostic else "snap assignments, live unblocked replacement",
                    prompt="native READ resource-identity line" if diagnostic else "none",
                    identity="actual loaded book and paired book/name/participant fingerprints",
                    human_control="no input gives; new A keeps; Black pitches; X or receiver passes",
                    experimental=True, runtime_witnessed=False)
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return None


def reservations(payload):
    places = allocations(payload)
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(va), end=hex(va + len(old)), size=len(old),
             basis="pinned live " + name + "; not a cave")
        for name, va, old, _new in sites(places["code"]["va"])]


def apply(payload: bytes, *, intent_table: bytes | None = None,
          diagnostic: bool | None = None) -> tuple[bytes, dict]:
    """Install atomically in memory; replay keeps omitted table, refuses changes."""
    state, previous = _inspect(payload)
    _require(diagnostic is None or type(diagnostic) is bool, "Expected a diagnostic Boolean")
    previous_diagnostic = _diagnostic_installed(payload) if state == 'applied' else False
    diagnostic = previous_diagnostic if diagnostic is None else diagnostic
    if diagnostic:
        image = XbeImage(payload)
        for va, size, digest in DIAGNOSTIC_GUARDS:
            _require(hashlib.sha256(image.read(va, size)).hexdigest() == digest,
                     f"Foreign Read option diagnostic dependency at {va:#x}")
    table = previous if intent_table is None and previous is not None else intent_table
    if table is None:
        table = compile_intent_table()[0]
    count = validate_intent_table(table)
    labels = assembly.DIAGNOSTIC_LABELS if diagnostic else assembly.LABELS
    receipt = dict(experimental=True, runtime_witnessed=False, tier="mesh", model_version=5,
                   diagnostic=diagnostic,
                   mesh_seconds=MESH_SECONDS,
                   authored_reads=count, table_sha256=hashlib.sha256(table).hexdigest(),
                   code_bytes=CODE_SIZE, instruction_bytes=labels['config'],
                   read_only_bytes=RO_SIZE, data_bytes=DATA_SIZE, changed_bytes=0, edits=[])
    if state == "applied":
        _require(diagnostic == previous_diagnostic, "Different Read option diagnostic; rebuild from the supported source")
        _require(table == previous, "Different Read option intent; rebuild from the supported source")
        return payload, {**receipt, "status": "already_applied"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated)
    content = code_for(places["code"]["va"], places["read_only"]["va"], places["data"]["va"],
                       diagnostic=diagnostic, paired_contract=pair.contract_va(allocated))
    installed, code_receipt = space.install_code(allocated, OWNER, content)
    installed, table_receipt = space.install_read_only(installed, OWNER, table +
                                                     (DIAGNOSTIC_PROMPT if diagnostic else PROMPT))
    image = XbeImage(installed)
    result = bytearray(installed)
    edits = []
    for name, va, before, after in sites(places["code"]["va"], diagnostic=diagnostic):
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


# Pinned dependency slices and controller tables. Only validated owner hooks
# (including the screen timer store in the shared initializer) are normalized.
GUARDS = (
    (0x215145, 62, "c02a6c72d6bac4ea370d814d4f5ac18f4254bd822276d6f9c221e3c1c69aeb33"),
    (0xfa0b0, 434, "8dcb54df98e3b4259017ef519b03cf976752a92aed610ecf530b13596193dced"),
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

# V5 native animation cancellation, task dispatch, decoded pitch and exchange.
GUARDS += (
    (0x39380, 89, "8e5d5a3bee554b57b2c4b4ea47fa8fad6f643245cfb379dc670f0dda9fe32c2a"),
    (0x393e0, 1491, "33071743027c99bcb73e6b67ec4b59d5109437d053123095ee9223c60d82e8df"),
    (0x1b84e0, 142, "0c2df9ec89384a307f207975ea43e6f9bdfa1d88e31eab028e99bb2cf9a5d4f4"),
    # QB Spy owns the three rush/man stores between these slices. The
    # paired back uses only native release/take entries, never those stores.
    (0x1b85a0, 184, "bfa665c54b321f123228f24b5d935765ae653036261970ae67a0aac6b6805ebf"),
    (0x1b8676, 274, "031e0d21c35b9c62373977713bdb3198e66a255d3ee9314a862ac2c762d586a5"),
    (0x1b8790, 74, "a4dd08a60a27e7151f71d9b4e41c2c9e8b146f70e653f533163691ad9bb4ad84"),
    (0x1b8c40, 96, "03d6410993f38054e7855f6e3e820da9f3766808bb04df4f00c9f6cc99709378"),
    (0x1b8ca0, 58, "c4a42a1bcc6b0f25a43a7ad493606154f27bec62ef9b0d63743b234642730de6"),
    (0x1cd550, 59, "fa171719f06965537ecd42af3764d5a6c174115c2f4ae100e646c77d23307997"),
    (0x2146c0, 98, "9cd9a1096382a52e29fa471eec65cad3e811747b4d13f1b2884e3a472112c6c4"),
    (0x214b90, 24, "f4147fb1c90bcd40b8d37cd38abe7c1b2449c4ba219b0b31005fb6844e6ab412"),
    (0x215275, 74, "0409dcc40f84192cb33a537b9f78ed6e2d48e43cb6de4a2e8c8d0b348f5f63c7"),
    (0x2e36f0, 261, "da791f861c7d8bcc101f8d54074933616990248724be0494e558f2ed08ad73ef"),
    (0x2ff450, 74, "434114b32e0a929331cf052badb55129c18956684c8e5cdc03694f8a65322a99"),
    (0x2ff7c0, 723, "b70c7f93f05f6c1591b1bb8e94b0a305b06e495d70b1f5659d98ccddf61506b7"),
    (0x300810, 78, "ed71fc6b821b98c2503cc7fdbe98eb53a768d28ffb1da7a0b91e395ed1e8c653"),
    (0x300860, 672, "6c906522249fbad6c530fd51ba7f327c96fe12a39b813c329ae2420578fb3ca9"),
    (0x300b00, 1342, "ed787d8fde8dcebceeb794a32c6e41dc2c6fd8261628fac9c422452da53e3f7f"),
    (0x3133a0, 26, "67f537e2f5b43dc9458a8c4648b06b75878e1b4fc6285ec9e45a795dfa1a821e"),
    (0x313520, 507, "ade6a901dcf24aa58172c49e3569f1d2a3a8ca00068ae3ba37316284b6cb2f17"),
    (0x50f4ec, 24, "d3667d699ed6d70d23a0e9172b9477eafaf922527e0f57acfb29d7d7c284dbc9"),
    (0x531a08, 24, "a7a851afac0bd24902d547c36cdc4e151eaa3026c148d11e4317039d1e3ff83c"),
)

# Only the diagnostic calls
# this native text renderer. Its passicons FONT initializer is already pinned
# by GUARDS at 0xF9F40; font/position storage is cloned to the stack at runtime.
# Pin the actual 2D glyph helpers, line walker/table and string wrapper. The
# intervening unused 3D font path is owned by widescreen and team-column.
DIAGNOSTIC_GUARDS = (
    (0x460f0, 0x480, '6124464d2b575fe4ae175db48d92cf5f7e96303b729773ec043ddfd5dd54d21a'),
    (0x46df0, 0xf0, '990b60a03a3c7aa9675c5d62fb73a65138124f728d99b36d8b87a047da46d15f'),
    (0x47420, 0x65, '9139e722cbec6eb58e5e61fb29acb28121c4840149ed5d52b4a314633c27cb71'),
)


def main(argv=None):
    """Development CLI; bounded XBE/table reads, exclusive output, no disc IO."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    parser.add_argument('operation', choices=('status', 'apply', 'state'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--table', type=Path, help='exact 64-byte compiled intent table')
    parser.add_argument('--diagnostic', action='store_const', const=True, default=None,
                        help=DIAGNOSTIC_HELP_TEXT)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'state':
            with args.source.open('rb') as stream:
                data = stream.read(DATA_SIZE+1)
            print(json.dumps(decode_diagnostic_state(data), sort_keys=True, allow_nan=False))
            return 0
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
        result, receipt = apply(payload, intent_table=table, diagnostic=args.diagnostic)
        with args.output.open('xb') as stream:
            stream.write(result)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
