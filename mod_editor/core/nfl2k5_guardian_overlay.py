"""Per-player Guardian overlay. EXPERIMENTAL / UNWITNESSED, presets off.

Pair this executable with nfl2k5_guardian_resources on the same build copy.
Record +0x53 bit 5 is independent of A/C, stars, locks and abilities. Practice
is unsigned mode 0..3, without ever changing a player's saved selection.
All runtime scratch is on the stack; fresh native resource lookup replaces
the proposed bitmap/cache, avoiding index identity and stale-pointer state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_guardian_overlay_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_guardian_overlay"
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
RECORD_OFFSET, RECORD_BIT = 0x53, 0x20
CODE_SIZE = (len(assembly.CODE) + 15) & -16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
assert CODE_SIZE <= 2048
_UNSET = object()
HOOKS = {
    "bind": (0x8F02E, bytes.fromhex("8b55ec8bc2")),
    "shine": (0x8FB45, bytes.fromhex("0fb68b1f53b6003bc1")),
    "clone": (0xC16CD, bytes.fromhex("668b4d0466894f04")),
}
SYMBOLS = dict(retail_bind_tail=0x8F033, retail_shine_tail=0x8FB4E,
               retail_shine_next=0x8FBB1, retail_texture=0x449E0,
               retail_bind_texture=0x8E3F0, retail_clone_tail=0xC16D5)
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail has no separate Guardian cap. Patch: "
    "selected players wear a padded cover over either helmet. Caps for everyone "
    "in practice is optional. A missing cap texture keeps the normal helmet. "
    "Requires the matching models and global cap artwork."
)


class GuardianOverlayError(ValueError):
    """Unsupported, foreign, mixed or differently configured installation."""


def _require(condition, message):
    if not condition:
        raise GuardianOverlayError(message)


def _practice(value):
    _require(type(value) is bool, "guardian_everyone_practice must be a boolean")
    return value


def record_selected(record):
    _require(len(record) == 0x54, "Guardian cap needs one complete 0x54 player record")
    return bool(record[RECORD_OFFSET] & RECORD_BIT)


def set_record_selected(record, selected):
    record_selected(record)
    _require(type(selected) is bool, "Guardian cap selection must be a boolean")
    out = bytearray(record)
    out[RECORD_OFFSET] = (out[RECORD_OFFSET] & ~RECORD_BIT) | (RECORD_BIT if selected else 0)
    return bytes(out)


def apply_roster_body(body, selections):
    """Replace the cap selection using exact (pool, index) + record SHA-256 pins.

    Entries are {pool, index, record_sha256}. Empty clears all selections.
    Replays normalize only the owned bit when comparing record identities.
    No fuzzy name matching or fallback to another player's index is allowed.
    """
    from . import nfl2k5_player_tags as tags
    roster = tags.parse_body(body)
    players = {(p.pool, p.index): p for p in roster.players}
    wanted = set()
    for selection in selections:
        _require(isinstance(selection, dict) and set(selection) == {"pool", "index", "record_sha256"},
                 "Guardian selection needs pool, index and record_sha256")
        _require(type(selection["index"]) is int, "Guardian index must be an integer")
        key = (selection["pool"], selection["index"])
        _require(key in players and key not in wanted, "missing or duplicate Guardian player")
        p = players[key]
        record = set_record_selected(body[p.offset:p.offset+0x54], False)
        _require(hashlib.sha256(record).hexdigest() == selection["record_sha256"],
                 "Guardian roster provenance mismatch; refresh the selection")
        wanted.add(key)
    buf = bytearray(body)
    for key, p in players.items():
        buf[p.offset:p.offset+0x54] = set_record_selected(body[p.offset:p.offset+0x54], key in wanted)
    result = bytes(buf)
    return result, dict(selected=len(wanted), record_offset=hex(RECORD_OFFSET), bit=RECORD_BIT,
                        changed_bytes=sum(a != b for a, b in zip(body, result)),
                        before_sha256=hashlib.sha256(body).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


def code_for(code_va, guardian_everyone_practice=True):
    _practice(guardian_everyone_practice)
    blob = bytearray(assembly.CODE)
    symbols = {"code": code_va, **SYMBOLS}
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", blob, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    struct.pack_into("<I", blob, assembly.LABELS["config"], int(guardian_everyone_practice))
    blob.extend(b"\xcc" * (CODE_SIZE - len(blob)))
    return bytes(blob), {name: code_va + offset for name, offset in assembly.LABELS.items()}


def sites(labels):
    return [(name, va, before, b"\xe9" + struct.pack("<i", labels[name]-va-5)
             + b"\x90"*(len(before)-5)) for name, (va, before) in HOOKS.items()]


def allocation(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    _require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"])
             == ("code", CODE_SIZE, 16), "reserve Guardian overlay with the complete owner union")
    return rows[0]


def _inspect(payload):
    _require(isinstance(payload, (bytes, bytearray)) and len(payload) >= 4096, "truncated Guardian XBE")
    layout = space.layout(payload)
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for hook, before in HOOKS.values():
            if va <= hook and hook+len(before) <= va+size:
                blob[hook-va:hook-va+len(before)] = before
        _require(hashlib.sha256(blob).hexdigest() == digest, f"foreign Guardian dependency at {va:#x}")
    state, practice = "retail", True
    labels = {name: 0 for name in HOOKS}
    if any(a["owner"] == OWNER for a in layout["allocations"]):
        a = allocation(payload)
        content = image.read(a["va"], a["size"])
        if content != b"\xcc" * a["size"]:
            value = struct.unpack_from("<I", content, assembly.LABELS["config"])[0]
            _require(value in (0, 1), "foreign Guardian configuration")
            practice = bool(value)
            expected, labels = code_for(a["va"], practice)
            _require(content == expected, "foreign Guardian code or configuration")
            state = "applied"
    for name, va, before, after in sites(labels):
        _require(image.read(va, len(before)) == (after if state == "applied" else before),
                 "mixed/foreign Guardian hook: " + name)
    return state, practice


def status(payload):
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload):
    state = status(payload)
    return dict(status=state, guardian_everyone_practice=_inspect(payload)[1] if state != "foreign" else None,
                experimental=True, runtime_witnessed=False)


def reservations(payload):
    _require(status(payload) == "applied", "Guardian reservations require complete installation")
    return ([r for r in space.reservations(payload) if r["owner"] == OWNER]
            + [dict(owner=OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
                    basis="pinned live " + name + "; not a cave") for name, (va, before) in HOOKS.items()])


def apply(payload, *, guardian_everyone_practice=_UNSET):
    state, previous = _inspect(payload)
    wanted = previous if guardian_everyone_practice is _UNSET else _practice(guardian_everyone_practice)
    receipt = dict(owner=OWNER, guardian_everyone_practice=wanted, experimental=True,
                   runtime_witnessed=False, changed_bytes=0, edits=[])
    if state == "applied":
        _require(wanted == previous, "different Guardian settings; rebuild from a supported base")
        return bytes(payload), {**receipt, "status": "already_applied"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                     if space.status(payload) == "retail" else (payload, {}))
    a = allocation(allocated)
    content, labels = code_for(a["va"], wanted)
    installed, install_receipt = space.install_code(allocated, OWNER, content)
    image, buf, edits = XbeImage(installed), bytearray(installed), []
    for name, va, before, after in sites(labels):
        off = image.offset(va, len(before))
        buf[off:off+len(after)] = after
        edits.append(dict(label=name, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "Guardian installation postcondition failed")
    return result, {**receipt, "status": "applied", "edits": edits, "allocation": allocation_receipt,
                    "code_install": install_receipt, "requests": REQUESTS,
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result))+len(result)-len(payload)}


# Full retail dependencies, normalized only at the two owned hook sites.
GUARDS = (
    (0xc16b0, 1750, 'f7e3aa60c3daa88af0da1ded2c0278672f810e63e018db2a4793b32819593523'),
    (0x8efa0, 194, 'b4615263dcf020a9b1f335413f3da8593af33e2214193d7225f93afb054e567e'),
    (0x8fad0, 263, '84f7597e32b47cdc60663c2a461be107252059d6f38d18c8c948b1ebf90781b1'),
    (0x8e3f0, 56, '7a49b3a41f69c48ed28444a005aa33cb2f44eb1551b7613b8286836dbb8a7fb4'),
    (0x449e0, 104, '710fd5ba9fd2a147042dd4c5f133cc2a8d36dcdc10b47417d17ec65df9b46191'),
    (0x443d0, 770, '1caaf5b258e1849435c7ed69dbc970f9ce5f265415c4dadecee3bef94dc8d6b3'),
    (0x43e30, 384, '802fe8a7979f27dd15d3cdb5bd8f46954094104f134adb7f00567c14d09644e3'),
    (0x44da0, 32, 'fa8a4a51813f1b2fd43bf2503ba01e7930f857075ced8176d58f4908c1874639'),
    (0x34df0, 108, 'f84f040777759d3417fb8bee34ab8e046cf40255e18c467530417ae504aad29c'),
    (0x34c10, 267, '69266ee656258cc0c7c3f770b0a650452d18c4c84251088bb204fbecb3afa2fe'),
    (0x8f800, 300, '8ffa85e5ad6b1cec8d43c7ae9b4e6fe5faf9c1ed76ada99afb3973998849e5b6'),
    (0x8f930, 303, '7a1d3ec8b924ca607e72ce8d14cea98e5f4f24b0e00c57f8442c3c4eac4b7557'),
    (0x90740, 478, '732f9112b39a273f4f8e1e5e3534074aa623ea1472c3287caef251abb11ee1ae'),
    (0x4eee68, 32, '9d6883f42544a2218cd5eee45f18fab9d4baa052e423464f7da1e099181b7e88'),
    (0x4ef388, 32, 'c02a5395f5944011a5c90e9f7fbe67928babfa2cf75aa185fc8507ea7bbe29cf'),
    (0x8e9e0, 464, '00e461865528b7a5bfd66c61801334776d42562f26247a89c99d65002a79c77e'),
    (0x8e580, 49, '1e196cf2a1d8dbbc1635eafe652992ca0633903e0f1b4014dce2cd6cbc9673a9'),
    (0x43a20, 136, '9ffda5456aae6f8f11e07a430c8a5a7e20ecdfe7abddc621f432e3a319f2ce92'),
    (0x438d0, 277, '486d0d493690470a0a32892dde83c76603a006d922075fb95ddac840b078c52b'),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "check"))
    parser.add_argument("xbe", type=Path)
    args = parser.parse_args(argv)
    _require(args.xbe.stat().st_size <= 16*1024**2, "XBE exceeds 16 MiB")
    payload = args.xbe.read_bytes()
    info = read_settings(payload)
    if args.command == "check":
        rebuilt, receipt = apply(payload)
        _require(apply(rebuilt)[0] == rebuilt, "Guardian replay changed bytes")
        info["receipt"] = receipt
    print(json.dumps(info, indent=2))
    return 1 if info["status"] == "foreign" else 0


if __name__ == "__main__":
    raise SystemExit(main())
