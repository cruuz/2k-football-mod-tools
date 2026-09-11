"""Native game-only offense/defense playbook pairing. EXPERIMENTAL / UNWITNESSED.

USA Xbox retail pins. Reserve the complete REQUESTS union before installation.
The patch adds Options rows; Same as offense is the default. No save is changed.
Publishes bounded source identities for authored read-option and QB-spy controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_playbook_pair_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_playbook_pair"
CODE_SIZE, DATA_SIZE, RO_SIZE = 8192, 512, 4096
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16),
            (OWNER, "read_only", RO_SIZE, 16))
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: one playbook supplies both units. "
    "Patch: choose a defensive playbook for either side in game Options. "
    "Pairs must fit the game's limits. Special teams use the offensive book. "
    "The choice lasts one game and is not saved to Franchise. "
    "Paired sides use ordinary CPU coaching without VIP learning or replay. "
    "Authored read-option and QB-spy controls retain their source identities."
)
BOOKS = (
    ("ARZ", "Cardinals"), ("ATL", "Falcons"), ("BAL", "Ravens"), ("BUF", "Bills"),
    ("CAR", "Panthers"), ("CHI", "Bears"), ("CIN", "Bengals"), ("CLE", "Browns"),
    ("DAL", "Cowboys"), ("DEN", "Broncos"), ("DET", "Lions"), ("GB", "Packers"),
    ("HOU", "Texans"), ("IND", "Colts"), ("JAX", "Jaguars"), ("KC", "Chiefs"),
    ("MIA", "Dolphins"), ("MIN", "Vikings"), ("NE", "Patriots"), ("NO", "Saints"),
    ("NYG", "Giants"), ("NYJ", "Jets"), ("OAK", "Raiders"), ("PHI", "Eagles"),
    ("PIT", "Steelers"), ("SD", "Chargers"), ("SEA", "Seahawks"), ("SF", "49ers"),
    ("STL", "Rams"), ("TB", "Buccaneers"), ("TEN", "Titans"), ("WAS", "Washington"),
    ("GEN", "Generic"), ("WCO", "West Coast"),
)
SYMBOLS = {
    "begin_continue": 0x62BE5, "queue_continue": 0x630CF,
    "bind_continue": 0x64719, "cleanup_continue": 0x61955,
    "home_team_native": 0x61C50, "mode_native": 0xE99C0,
    "vip_continue": 0xF71E6, "heap_native": 0x38FB0,
    "allocate_native": 0x48700, "free_native": 0x48870,
    "unload_native": 0x432F0, "queue_native": 0x43F50,
    "load_callback_native": 0x61580, "notice_native": 0x14E520,
}
HOOKS = (
    ("begin", 0x62BE0, "a18401e600", 0xE9),
    ("queue", 0x630C8, "833d80ffe50003", 0xE9),
    ("bind", 0x64710, "83ec0856e837d5ffff", 0xE9),
    ("cleanup", 0x61950, "b93816e600", 0xE9),
    ("load_mode", 0x166617, "e8a433f8ff", 0xE8),
    ("vip", 0xF71E0, "81f920fce500", 0xE9),
)
TABLES = (0x526A70, 0x526D88)
TABLE_POINTERS = (0x526C20, 0x526F38)
ROWS = (
    (7, 15315776, 0, 2889152, 2889136, 2889264, 2889168, 2889216, 2889280, 2889296, 0, 0, 0),
    (7, 15315792, 0, 489136, 489120, 489248, 489152, 489200, 489280, 489408, 0, 0, 0),
    (7, 15315820, 0, 488832, 488816, 488944, 488848, 488896, 488976, 489104, 0, 0, 0),
    (7, 15315848, 0, 2894640, 2894656, 2894624, 2894496, 2894560, 2895168, 2894672, 0, 0, 0),
    (7, 15315872, 0, 2894784, 2894800, 2894768, 2894688, 2894720, 2895184, 2894816, 0, 0, 0),
    (7, 15315904, 0, 2894960, 2894976, 2894944, 2894848, 2894896, 2895200, 2894992, 0, 0, 0),
    (7, 15315928, 0, 2895120, 2895136, 2895104, 2895008, 2895056, 2895216, 2895152, 0, 0, 0),
    (3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
)


# Exact retail prerequisites, normalized only at this owner's pinned sites.
GUARDS = (
    (0x77c6b, 10, "4257e3c419cd00452d0faa205f03202355ef298fc89aede90ada628eba763dbf"),
    (0xc73f2, 77, "08c52ec9c9dd74e1ab343a2e9db7b36dfa0e213d240cf360e55348c1b7808569"),
    (0x62be0, 21, "1921be843e72c6752efe2250f0730157aea5b544cfb36346e96193436d8d1133"),
    (0x63065, 106, "834cb362fe210e08c2a65d9365bb7d328fbd4a7b1bf7ce4a86676345f13d1f40"),
    (0x64710, 25, "866dc0a8f9c4c520679a46a03bcb1ca8a69fa6822cb03e7a1cf7f7243c510909"),
    (0x61950, 170, "d85a7efb8fb54926be24d716ef2bea7b50b5129525cef1c4300a5620544c8414"),
    (0x61580, 28, "cd861871d6a20e3debc505104655911bc508fd924e236af80e52b86b9d2ae9e9"),
    (0x628d0, 368, "b1c5fcbd35e743d9d172d5fd8072ed2bafde6548a22da99b8a7474743deb33d5"),
    (0x1665a0, 238, "9f786d333da5de97cbf9bf1bba0e2968a20a04788763a6def267e200e85a600d"),
    (0xe99c0, 47, "d03e3e959186d48a74dc0c6a48412c34a1b36374de5d5611bd25ff77fd7351da"),
    (0xe99f0, 7, "54358d295fdd3410cba6b548589c698502de32fb4c9afdcb3b7bb22389dedddb"),
    (0xf71e0, 19, "5c08a7153ba0c9a94ddeb94b8a76215462a00393acb1b490c146c15397ef10d5"),
    (0x43f50, 606, "9bf8b19d176dc9169c8d7b13af5887ce474ed202990d91f77b5601baccd21b71"),
    (0x48700, 39, "2afa1c64c28563d908a6f69d13fc1944f151aa7fc7c9baf50e4ded284cf88d01"),
    (0x48870, 185, "e010d1b355cbd4cf150dc9993b918c46f6805d4c410bc570207a695dc073fa3c"),
    (0x432f0, 938, "35d4d2319d791ef473698b18d482308c833ebed2b253105b99fbcd0605342b4a"),
    (0x14e520, 25, "3546625976e5bf1c782ad583cbc3f5bf3646469daace6d13f8907e2719a5c18f"),
    (0x87160, 299, "2df61ccab967a9116589fedc386197159d130b8d9af6c24a6801f878400c329c"),
    (0xe0660, 14, "f93887bb95940b4141260124fae08b8ab5aab596aa1519bf35e8da38e318e5b6"),
    (0xe0830, 24, "ecc45dc68c992388f558d102f2c134d17e910ca4d70b6289b56be49af9d254c6"),
    (0xe0850, 124, "f8de2c1334232931ead5b7a1f0c7897aca4546974c61a756d01912ec2d138f80"),
    (0xe1960, 105, "3b00061f7f8c1974394c10c72db8e740c301327479d7a33afb8dfe1877c5cfb0"),
    (0xf2f90, 98, "33d3960c737bdc2fd65813cf90b51ef0457c645832c91c22fb5c9454a9d53f87"),
)

class PlaybookPairError(ValueError):
    pass


def require(value, message):
    if not value:
        raise PlaybookPairError(message)


def read_only_bytes(code_va, ro_va):
    """One shared immutable row template; the native menu creates its own rows."""
    labels = ["Same as offense", *(name for _, name in BOOKS)]
    labels += [code + "-pb.iff" for code, _ in BOOKS]
    labels += ["PAIRDEFHOME", "PAIRDEFAWAY", "",  # index 71 becomes row pointer
               "Defensive playbooks last one game. This choice is not saved to Franchise. "
               "Paired sides do not use VIP learning or replay.",
               "Choose separate playbooks in Play Now or a Franchise game.",
               "Separate playbooks need stock books for both sides. Using the original books.",
               "HOME playbook pair could not be loaded or does not fit. Using the original HOME book.",
               "AWAY playbook pair could not be loaded or does not fit. Using the original AWAY book.",
               "HOME Defensive playbook", "AWAY Defensive playbook",
               "HOME Offensive playbook", "AWAY Offensive playbook"]
    require(len(labels) == 81, "Playbook pair RO directory changed")
    result = bytearray(len(labels)*4)
    addresses = []
    for index, label in enumerate(labels):
        address = ro_va + len(result)
        addresses.append(address)
        struct.pack_into("<I", result, index*4, address)
        result.extend((label + "\0").encode("utf-16le"))
    result.extend(bytes((-len(result)) % 4))
    struct.pack_into("<I", result, 71*4, ro_va+len(result))
    for index, original in enumerate(ROWS):
        row = list(original)
        if index in (1, 2):
            side = "away" if index == 1 else "home"
            row[1] = addresses[80 if index == 1 else 79]
            result.extend(struct.pack("<13I", *row))
            row[1] = addresses[78 if index == 1 else 77]
            for at, symbol in ((3, "maximum"), (4, "minimum"), (5, "get_"+side),
                               (6, "next_"+side), (7, "prev_"+side), (8, "text_"+side),
                               (9, "width"), (11, "visibility")):
                row[at] = code_va + assembly.LABELS[symbol]
        result.extend(struct.pack("<13I", *row))
    require(len(result) <= RO_SIZE, "Playbook pair exceeds its RO budget")
    return bytes(result).ljust(RO_SIZE, b"\0")


def sites(code_va=0, ro_va=0):
    edits = []
    for name, va, pin, opcode in HOOKS:
        before = bytes.fromhex(pin)
        target = code_va + assembly.LABELS[name]
        after = bytes([opcode])+struct.pack("<i", target-va-5)+b"\x90"*(len(before)-5)
        edits.append((name, va, before, after))
    table = struct.unpack_from("<I", read_only_bytes(code_va, ro_va), 71*4)[0]
    for index, (at, original) in enumerate(zip(TABLE_POINTERS, TABLES)):
        edits.append((f"options_{index}", at, struct.pack("<I", original), struct.pack("<I", table)))
    return edits


def _recognize(payload):
    layout = space.layout(payload)
    image = XbeImage(payload)
    present = any(a["owner"] == OWNER for a in layout["allocations"])
    owned = allocations(payload) if present else None
    edits = sites(owned["code"]["va"], owned["read_only"]["va"]) if owned else sites()
    states = set()
    for _, va, before, after in edits:
        actual = image.read(va, len(before))
        states.add("retail" if actual == before else "applied" if owned and actual == after else "foreign")
    if owned:
        c, d, r = (owned[k]["va"] for k in ("code", "data", "read_only"))
        require(image.read(d, DATA_SIZE) == bytes(DATA_SIZE), "foreign initialized playbook pair RW state")
        body, text = image.read(c, CODE_SIZE), image.read(r, RO_SIZE)
        states.add("retail" if body == b"\xcc"*CODE_SIZE else "applied" if body == code_for(c,d,r) else "foreign")
        states.add("retail" if text == bytes(RO_SIZE) else "applied" if text == read_only_bytes(c,r) else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed playbook pair hooks or owned spans")
    original_rows = b"".join(struct.pack("<13I", *r) for r in ROWS)
    for at in TABLES:
        require(image.read(at,len(original_rows)) == original_rows, "foreign native Options rows")
    for va, size, digest in GUARDS:
        raw = bytearray(image.read(va,size))
        for _, at, before, after in edits:
            if va <= at and at+len(before) <= va+size:
                require(bytes(raw[at-va:at-va+len(before)]) in (before,after), "foreign pair prerequisite")
                raw[at-va:at-va+len(before)] = before
        require(hashlib.sha256(raw).hexdigest() == digest, f"foreign playbook prerequisite at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def code_for(code_va, data_va, ro_va):
    symbols = {"code": code_va, "state": data_va, "ro": ro_va, **SYMBOLS}
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    require(len(result) <= CODE_SIZE, "Playbook pair exceeds its RX budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def allocations(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require({(a["kind"], a["size"], a["align"]) for a in rows} ==
            {(kind, size, align) for _, kind, size, align in REQUESTS} and len(rows) == 3,
            "reserve Playbook pair with the complete owner union on a clean base")
    return {a["kind"]: a for a in rows}


CONTRACT_OFFSET = 160
CONTRACT_SIZE = 32


def contract_va(payload):
    """Fixed absolute address for this sealed build, zero when pair is absent.

    Two callback words precede home/away (merged, offense, defense) roots.
    All words are zero on disc; complete merges publish, cleanup revokes.
    An allocated but disabled pair therefore follows the retail fallback.
    """
    rows = [a for a in space.layout(payload)['allocations'] if a['owner'] == OWNER]
    return allocations(payload)['data']['va'] + CONTRACT_OFFSET if rows else 0


def apply(payload):
    state = _recognize(payload)  # complete refusal BEFORE allocation or any edit
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  code_bytes=len(assembly.CODE), rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE,
                  ro_bytes=RO_SIZE, save_growth=0, franchise_persistence=False, in_game_default="Same as offense",
                  special_teams="offense source", vip_for_paired_side=False)
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
    result, _ = space.install_read_only(result, OWNER, read_only_bytes(code, ro))
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = sites(code, ro)
    for _, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at+len(before)] = after
    for s in _sections(buffer):
        buffer[s.header_offset+36:s.header_offset+56] = section_digest(buffer, s)
    result = bytes(buffer)
    require(status(result) == "applied", "Playbook pair postcondition failed")
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
