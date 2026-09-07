"""Optional native Franchise Auto Save, USA Xbox. EXPERIMENTAL / UNWITNESSED.

The native serializer and signed transaction own every save byte. A successful
manual save/load chooses the slot; no default name or destination is invented.
Reserve the complete selected REQUESTS union before installing any owner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_franchise_autosave_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_franchise_autosave"
CODE_SIZE, DATA_SIZE, RO_SIZE = 1536, 128, 512
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: save Franchise manually. Patch: replace "
    "First Person Football in Franchise settings with Auto Save, Off or On. "
    "Save once to choose a slot. With Auto Save on, returning to Coach's Desk "
    "after a completed game saves to that slot using the game's save system."
)
ROW_VAS = (0x500B24, 0x52BB68)
DESK_VA, DESK_UPDATE_POINTER = 0x522190, 0x521DCC
SAVE_WORD_OFFSET = 0x64
FRANCHISE_MODE, FRANCHISE_TYPE = 2, 9
SYMBOLS = {
    "desk_native": 0x142DD0, "mark_played_native": 0xC4BC0,
    "mark_sim_native": 0x1C1C80, "copy_settings_native": 0xE2E10,
    "camera_size_native": 0xA5460, "league_native": 0xC4B80,
    "mode_nonzero": 0xC758B, "mode_zero": 0xC7576, "load_continue": 0x16E548,
    "dialog_native": 0x14E440, "notice_native": 0x14E520,
    "init_devices_native": 0x16BB20, "select_device_native": 0x16B740,
    "save_native": 0x16E3F0, "close_devices_native": 0x16A640,
    "allocate_native": 0x48700,
}
# Whole instructions, including the two original branch destinations.
HOOKS = (
    ("played", 0xC5DA9, "e912eeffff", 0xE9),
    ("simulated", 0xC7B61, "e81aa10f00", 0xE8),
    ("serialize", 0x16E4B6, "e85549f7ff", 0xE8),
    ("allocate", 0x16E4A9, "e852a2edff", 0xE8),
    ("load_settings", 0x16E7C5, "e8966cf3ff", 0xE8),
    ("load_slot", 0x16E81A, "e86163f5ff", 0xE8),
    ("load_begin", 0x16E540, "83ec14a1b8bdbd00", 0xE9),
    ("mode_change", 0xC7570, "8bc185c07515", 0xE9),
    ("overwrite_dialog", 0x16C03E, "e8fd23feff", 0xE8),
    ("success_dialog", 0x16C50D, "e82e1ffeff", 0xE8),
)
ROW_ORIGINALS = (
    (0xE7D5C4, 0x147EB0, 0x147E60, 0x147E80, 0x148960),
    (0xE9CB68, 0x2C6EC0, 0x2C6E80, 0x2C6EA0, 0x2C74D0),
)
# Generated once from the pinned retail executable, not on the user's input.
GUARDS = (
    (0x6e4e0, 336, "3e109f7f4227757237edf45f505e63087b702cdd94ae43d98272d9f04c796208"),
    (0x645d0, 76, "e87079308f01b5c107eea1da1d4eedd1383ee220ece52a4e16bb982f992fb5dd"),
    (0x507ec8, 44, "71af3a6aaefd42d6ed2660c84e53d410d1b4464fe0e34017902fa6a7269b11c7"),
    (0x508e20, 52, "bb333e7b42561a5b6b0f2869dd4df61328a2b645bd6ec2daf5248534a51f2b1c"),
    (0x504c30, 80, "f2ca73c6233f7b6cbb90120c5ce0039b43ef967d1f36ec02de259d004ff7e5d6"),
    (0x16b060, 101, "664119de59c8761ae38dc1f4b18b879acba54f2a0d9a7361171528bf3ec5d41d"),
    (0x16bd70, 272, "c7e12ac610f1308cc6a1eaab2dede36a5d43c4083dfa1329b099cf0bbdfbb1d6"),
    (0x16e984, 84, "ad5da342a9ac4e2666cbce51f63ebb5cf2fba70b5c45b778ac08eb978599fc8a"),
    (0x147ee0, 15, "a14b61c0152df43f5f2cc62a93e2811f6ba596dd44a73167039d993884504273"),
    (0x2c6ef0, 15, "2949095979bed076aba6c2255ce1673df45e13d15b5f2ca64447515706dabd52"),
    (0xc5d60, 79, "c5419e1a079da777588f9197e82673fbfc0fd81bb156cd871cdb77377a56eeba"),
    (0xc7b25, 65, "8d92f168176dfcb1c7df90e07063ad52fc83bf0cd291416521aef53331d1b81d"),
    (0xc7570, 45, "0f7322e60aaed22d188f82058a93dbfdbfe62bb2241165bb4710171a5ac64f73"),
    (0x16e3f0, 336, "fbafb374865bf17a8d3716f468de28eb31c3119bbccd4282e7a8454dd630fd79"),
    (0x16e540, 66, "3fae05e6ebeeeab6f3444b89051944a7cdadeeb3e25e42800f482a936fe747f3"),
    (0x16e7c5, 97, "6cd2212afb80b81fae0441d5598288988f33feac5d4c6c6e90f0bf7466b9a859"),
    (0x16be80, 1748, "712a01aeb624be5421184bc2eef0a10a9a0b2b393e66f3e89c9f4b0f4a7f6cf4"),
    (0x16bb20, 159, "572df8b294019f1dd6f2afa37b4795c053c4e527f759874bbfc98087bd05c68c"),
    (0x16b740, 156, "74655e9c4578c4b3cfdcb10c22d308bbe32b220c9cd7f7fa7ec998a9f76adf5e"),
    (0x16a640, 65, "a4abb5af36509f9889e934ee44649993c664f473af56d2d614efed39902250a0"),
    (0xe2e10, 16, "c59ecca590b4a7dfcbf880dfb50dc824169302ebf969ddd6a2cdeed8ce4a23bd"),
    (0xa5460, 6, "11443e93ea387ed107c62ae3147347e38323113552ce6e1ff1842ce12c7f0316"),
    (0x142dd0, 480, "c1d24be993f511c21ca440c302829a5229416b6ee7d3947c4a5f2725e7bb9fb3"),
    (0x1427a0, 113, "c62c12ab847d198256acc99f4fd19a5ee8930b353c6f72b5c89612f0c7c53075"),
    (0x521dc8, 72, "f4abdf3f0d32e7da044ccd54f0869b4c712e9470f4091056fe479a1023adffa2"),
    (0x500b24, 52, "9e7ff0531fda6217550ff709cf03ac524b8b83e87c07b0be740f8caa4e6cfe9e"),
    (0x52bb68, 52, "5bb96ff84ea5d93b7235478be5feb79f88b05bcb93f80e51d30c90a5b6f83a25"),
    (0x4ed994, 8, "9b2756c8bf5c8853bb5a5c059dca323c92f4d993eebfe7c72fc118953772580b"),
    (0x3b340, 357, "e9f37641128addd1c414f2d2406560305b58477ab882917d5f315c1becd68cb4"),
    (0x4d720, 416, "74976e8ab4a402917c22aec80c9fa36b7028546609e0a56507adee211fae23a5"),
    (0x4b2a0, 81, "b5d4bbcdfba146e16697d982421dfaaadc743fd0e4e24e2fd855cff34b0a0af4"),
    (0x4d520, 268, "1134911b43c8abf692b1890fcfe05136d6a506526eeb52d9e63a447d769f1162"),
    (0x4c880, 95, "1903039f9287fe5d892a217833205f3dbb72425d4b9b3a2628413c2447f41247"),
)


class FranchiseAutosaveError(ValueError):
    pass


def require(value, message):
    if not value:
        raise FranchiseAutosaveError(message)


def read_only_bytes():
    result = bytearray(RO_SIZE)
    for offset, text, limit in (
        (0, "Auto Save", 32),
        (128, "Auto Save needs a slot. Save Franchise manually once.", 128),
        (256, "Auto Save could not find this Franchise save. Save manually.", 128),
        (384, "Auto Save failed. Save Franchise manually.", 128),
    ):
        encoded = (text + "\0").encode("utf-16le")
        require(len(encoded) <= limit, "Auto Save text exceeds its fixed span")
        result[offset:offset+len(encoded)] = encoded
    return bytes(result)


def code_for(code_va, data_va, ro_va):
    symbols = {"code": code_va, "state": data_va, "strings": ro_va, **SYMBOLS}
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    require(len(result) <= CODE_SIZE, "Auto Save exceeds its RX budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def allocations(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require({(a["kind"], a["size"], a["align"]) for a in rows} ==
            {(kind, size, align) for _, kind, size, align in REQUESTS} and len(rows) == 3,
            "reserve Auto Save with the complete owner union on a clean base")
    return {a["kind"]: a for a in rows}


def sites(code_va=0, ro_va=0):
    result = []
    for name, va, pin, opcode in HOOKS:
        before = bytes.fromhex(pin)
        target = code_va + assembly.LABELS[name]
        after = bytes([opcode]) + struct.pack("<i", target-va-5) + b"\x90"*(len(before)-5)
        result.append((name, va, before, after))
    result.append(("desk_update", DESK_UPDATE_POINTER, struct.pack("<I", SYMBOLS["desk_native"]),
                   struct.pack("<I", code_va + assembly.LABELS["desk"])))
    for n, (row, originals) in enumerate(zip(ROW_VAS, ROW_ORIGINALS)):
        targets = (ro_va, *(code_va + assembly.LABELS[name]
                           for name in ("getter", "toggle", "toggle", "value_text")))
        for offset, before, after in zip((4, 20, 24, 28, 32), originals, targets):
            result.append((f"row_{n}_{offset}", row+offset, struct.pack("<I", before), struct.pack("<I", after)))
    return result


def _recognize(payload):
    layout = space.layout(payload)  # geometry, allocation directory and section seals
    image = XbeImage(payload)
    present = any(a["owner"] == OWNER for a in layout["allocations"])
    owned = allocations(payload) if present else None
    edits = sites(owned["code"]["va"], owned["read_only"]["va"]) if owned else sites()
    states = set()
    for name, va, before, after in edits:
        actual = image.read(va, len(before))
        states.add("retail" if actual == before else "applied" if owned and actual == after else "foreign")
    if owned:
        code = owned["code"]
        data = owned["data"]
        ro = owned["read_only"]
        require(image.read(data["va"], DATA_SIZE) == bytes(DATA_SIZE), "foreign initialized Auto Save RW state")
        body = image.read(code["va"], CODE_SIZE)
        text = image.read(ro["va"], RO_SIZE)
        states.add("retail" if body == b"\xcc"*CODE_SIZE else
                   "applied" if body == code_for(code["va"], data["va"], ro["va"]) else "foreign")
        states.add("retail" if text == bytes(RO_SIZE) else "applied" if text == read_only_bytes() else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed Auto Save hooks or owned spans")
    # Franchise Practice relocates this list to make room for its extra row.
    # Accept only its complete recognized installation and exact event list.
    from . import nfl2k5_franchise_practice as practice
    hooks = struct.unpack("<I", image.read(DESK_VA+4, 4))[0]
    if hooks == practice.COACH_DESK_HOOKS_VA:
        require(hashlib.sha256(image.read(hooks, 56)).hexdigest() ==
                "6d43ba61cdcf283e87a2761fd1fa0d9cec3c25c7cc83bb5886b124c142bf65cb",
                "foreign retail Coach's Desk event list")
    else:
        require(hooks == practice.CAVE_HOOKS_VA and practice.status(payload) == "applied"
                and image.read(hooks, practice.HOOKS_SIZE) == practice.cave_hooks(),
                "foreign relocated Coach's Desk event list")
    # Normalize only our exact recognized edits. Other owners never receive a
    # blanket exemption; these contexts deliberately exclude their live sites.
    for va, size, digest in GUARDS:
        raw = bytearray(image.read(va, size))
        if va == 0x6E4E0 and raw[:5] != bytes.fromhex("5155578bf9"):
            from . import nfl2k5_music_playlist as playlist
            require(playlist.status(payload) == "applied", "foreign playlist event dispatcher")
            raw[:5] = bytes.fromhex("5155578bf9")
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                raw[at-va:at-va+len(before)] = before
        require(hashlib.sha256(raw).hexdigest() == digest, f"foreign Auto Save prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    state = _recognize(payload)  # complete refusal BEFORE allocation or any edit
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  code_bytes=len(assembly.CODE), rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE,
                  ro_bytes=RO_SIZE, saved_word_offset=SAVE_WORD_OFFSET, save_growth=0,
                  native_save=hex(SYMBOLS["save_native"]), in_game_default="Off")
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        allocations(payload)
        allocated, allocation_receipt = payload, {}
    owned = allocations(allocated)
    code, data, ro = (owned[k]["va"] for k in ("code", "data", "read_only"))
    result, _ = space.install_code(allocated, OWNER, code_for(code, data, ro))
    result, _ = space.install_read_only(result, OWNER, read_only_bytes())
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = sites(code, ro)
    for _, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at+len(before)] = after
    for s in _sections(buffer):
        buffer[s.header_offset+36:s.header_offset+56] = section_digest(buffer, s)
    result = bytes(buffer)
    require(status(result) == "applied", "Auto Save postcondition failed")
    return result, dict(common, status="applied", allocation=allocation_receipt,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
        file_growth=len(result)-len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
        after_sha256=hashlib.sha256(result).hexdigest(),
        edits=[dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for name, va, before, after in edits] + [
            dict(label="owned_code", va=hex(code), size=CODE_SIZE),
            dict(label="owned_text", va=hex(ro), size=RO_SIZE)],
        reservations=space.reservations(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    require(args.source.stat().st_size <= 16*1024*1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "status":
        print(json.dumps(dict(status=status(payload), owner=OWNER, experimental=True, runtime_witnessed=False)))
    else:
        result, receipt = apply(payload)
        # Explicit output-copy CLI; refuse an existing file, including source.
        with args.output.open("xb") as stream:
            stream.write(result)
        print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
