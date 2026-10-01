"""Historic teams in Quick Game, USA Xbox. EXPERIMENTAL / UNWITNESSED.

Retail 2K5 ships 75 historic teams (the '85 Bears, the '72 Dolphins and so on) as one-team roster
files named by the roster's historic list (count at root+0x58, 16-byte entries at root+0x5C). The
retail game reaches them only through Create a Team's "Load Historic Team" (2D17B0), which imports
the file into one of the two spare team slots (USER1, USER2).

With this option, Quick Game Team Select (Team Select flow 1 at 0xACF614) keeps stepping past the
last resident team into that list, in both directions, and wraps back to the first NFL team after
the last entry. Stepping onto entry k imports it into the side's spare slot (home USER1, away USER2)
with the loader core 2D17B0 uses: the file name "h-%s-%d-%s-%d.iff", queue 43F50 in the "historic"
context, wait 432D0, lookup 449E0, clear C2300 first (the slot's players go back to the spare pool),
import C1030 (the practice squad's ps_import on its builds), category 4, the label of the NFL team
with the same asset code, pop 432F0. It skips 2D17B0's slot choice and 2D13B0 (the Create a Team
refresh). The list length is the roster's own count.

A slot is used only when it is empty (category 2 with no players) or holds a historic team
(category 4), and never while the other side shows it. A user-created team (category 2 with
players; the game's own Create a Team check 319370 calls only identity 90 and 91 "user created
teams") is never touched: that side just skips the historic list. The resident list skips both
spare slots while they hold historic teams, so neither side offers the team in the other side's
slot, and the Random Team spin stays on the resident list. Leaving the list returns the slot to an
empty created-team slot, as the ESPN 25th Anniversary exit event 20C3C0 does.

Hooks: the six calls of the four retail step functions from the Team Select next and previous
handlers (2C2240, 2C2310) and the Random Team spin (2C1AC0, 2C1B10). Practice and First Person
Football use the same local list. Every other flow calls the retail step functions unchanged, and the
team iterator itself (778C0, 77950) is not modified, so Franchise and season lists are retail. A network
session (128C70 nonzero: Xbox Live or system link) keeps the retail steps too.
Loading happens in the menu and finishes before the step returns; the two slots and the 155-record
spare pool exist in retail, so a game carries no extra memory. Runtime state: 16 zero-initialised
bytes (per side: the slot, the entry shown there plus one, its identity number).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_historic_teams_quick_game_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_historic_teams_quick_game"
# 1,280 bytes (the code is 1,231) keeps the scale-out union's page-aligned owners where they were.
CODE_SIZE = 1280
DATA_SIZE = 16
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
UI_LABEL = "Historic teams in Quick Game"
BUILD_CAPTION = "historic teams in Quick Game Team Select"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the game's 75 historic teams (the '85 Bears, the '72 Dolphins "
    "and the rest) can be played only after loading one into a Create a Team slot. Patch: Quick Game "
    "Team Select keeps going past the last team into the historic teams and back to the 49ers after "
    "the last one, both ways; the picked team loads into that side's spare slot (home USER1, away "
    "USER2). A slot that holds your own created team is never touched; that side just skips the "
    "historic teams. Practice and First Person Football also offer the historic list. "
    "Other flows, Franchise and season lists are unchanged.")

QUICK_GAME_FLOW = 1
LOCAL_FLOWS = (1, 3, 7)
FLOW_VA = 0xACF614
SELECTION_VAS = (0xACF63C, 0xACF640)
SYMBOLS = dict(
    retail_home_next=0x2C18D0, retail_home_prev=0x2C18F0,
    retail_away_next=0x2C1910, retail_away_prev=0x2C1930,
    team_mask=0x2C0D60, iter_next=0x778C0, iter_prev=0x77950, network_session=0x128C70,
    set_home=0x2C1780, set_away=0x2C17C0,
    text_format=0x4A400, loader_heap=0x38FB0, loader_queue=0x43F50, loader_wait=0x432D0,
    loader_lookup=0x449E0, loader_pop=0x432F0,
    team_release=0xC2300, team_import=0xC1030, text_equal=0x30C40)
# The six replaced calls: (label, call site, retail bytes, entry point).
HOOKS = (
    ("home_next", 0x2C22D0, "e8fbf5ffff", "home_next"),
    ("away_next", 0x2C2280, "e88bf6ffff", "away_next"),
    ("home_prev", 0x2C2392, "e859f5ffff", "home_prev"),
    ("away_prev", 0x2C2349, "e8e2f5ffff", "away_prev"),
    ("home_random", 0x2C1B02, "e8c9fdffff", "home_random"),
    ("away_random", 0x2C1B52, "e8b9fdffff", "away_random"),
)
# Retail code and text the runtime relies on, pinned; only our own call sites are normalised.
GUARDS = (
    (0x2C0D60, 0x44, "f4e1f2b9189f3a8198039646ea6929fcdd04127bf449935183c161cf1487890c", "mask by flow and its jump table"),
    (0x2C1780, 0x5D, "8facdc417939aae0a34e9c5e0bccd6ca0bef35b799ac06a2cc3d024cc126a3c3", "home and away setters"),
    (0x2C18D0, 0x79, "740aa22f9597bd96472c04c2ef183c4f9664974c5d8e85254286332ec9d6e49f", "the four retail step functions"),
    (0x2C1AC0, 0x9F, "f811bbf1b556ce74dff816461905c9f5ecc7ba22e1c659b32d111cbed78d6833", "the Random Team spin steps"),
    (0x2C2240, 0x18D, "04aeb901a56132627104a490162e0f0e33e2ae35f505b2b4a61641873a3d3056",
     "the Team Select next and previous handlers"),
    (0x77090, 0xB8, "c0e7ec298fbcd39c6f070f30813efd9923961a550c50a111b7635a732cf9b4d4", "team index helpers"),
    (0x778C0, 0x117, "cce877214b0cbfa9fbd553a64c2e541c498c3dacd6c306d2ffc2c6c47b4e8306", "the team iterator"),
    (0xE2E50, 0xB4, "cd6cbfa9a49b72e7615b379309fc94c52e82e567181cf3163b0ae7473080ca46", "the team filter and its jump table"),
    (0x2D17B0, 0x19D, "c72530b9b42e5e53d7b9fd02e004d6e5e7a719daa6d9b5ef16874bd8be27b8d3",
     "Load Historic Team, the loader this mirrors"),
    (0x4A3E0, 0x25, "11210b47962dfa23193223585e5639b62cd63844b7747181397bb66a335dc25a", "the text formatter"),
    (0x38FB0, 0x06, "cc3ad517ec546fdbfa574fe66093f15a5f30ce9dfa7457e426a684a84a063e98", "the loader heap"),
    (0x432D0, 0x1F, "005ba2f686bdcb6bdf502d4a459f0e918445b13299110652071dddb3e66e77d1", "the loader wait"),
    (0x30C40, 0x25, "dd3d52cc45c43dc86d8db7220d777346237b324dd9a00dce35c9de3362bbfdee", "text equality"),
    (0x128C70, 0x0E, "6447141db5ba54815ef9a241b3cb3602fc5a823982a82afe12d2814c94d8dbf5", "the network session test"),
    (0xE9F970, 0x54, "61b33cd8c7598451dcce1e32e5c938a002a7907d74f2fbbde62554d2779cebec",
     "the historic name, file and context texts"),
)


class HistoricQuickGameError(ValueError):
    """Foreign prerequisites or an allocation outside the complete owner union."""


def require(condition, message):
    if not condition:
        raise HistoricQuickGameError(message)


def code_for(code_va, data_va, *, seasons=False):
    symbols = dict(SYMBOLS, state=data_va)
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    if seasons:
        operand=b'\xba'+struct.pack('<I',0xE9F984)
        require(result.count(operand)==1, 'historic filename operand changed')
        at=result.index(operand)+1
        struct.pack_into('<I',result,at,code_va+len(result))
        result.extend('HTS-h-%s-%d-%s-%d.iff\0'.encode('utf-16le'))
    require(len(result) <= CODE_SIZE, "historic teams in Quick Game exceeds its RX budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def allocations(payload):
    rows = {(a["owner"], a["kind"]): a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    code, data = rows.get((OWNER, "code")), rows.get((OWNER, "data"))
    require(code is not None and data is not None and code["size"] == CODE_SIZE and data["size"] == DATA_SIZE
            and len(rows) == 2, "reserve historic teams in Quick Game with the complete owner union on a clean base")
    return code, data


def sites(code_va=0):
    return [(label, va, bytes.fromhex(pin),
             b"\xe8" + struct.pack("<i", code_va + assembly.LABELS[entry] - va - 5))
            for label, va, pin, entry in HOOKS]


def _guard_digest(image, va, size, edits):
    raw = bytearray(image.read(va, size))
    for _, at, before, _ in edits:
        if va <= at and at + len(before) <= va + size:
            raw[at - va:at - va + len(before)] = before
    return hashlib.sha256(bytes(raw)).hexdigest()


def _recognize(payload):
    layout = space.layout(payload)  # geometry, ownership, directory and section seals
    image = XbeImage(payload)
    owned = allocations(payload) if any(a["owner"] == OWNER for a in layout["allocations"]) else None
    edits = sites(owned[0]["va"] if owned else 0)
    states = set()
    for _, va, before, after in edits:
        actual = image.read(va, len(before))
        states.add("retail" if actual == before else "applied" if owned and actual == after else "foreign")
    if owned:
        code, data = owned
        body = image.read(code["va"], CODE_SIZE)
        states.add("retail" if body == b"\xcc" * CODE_SIZE else
                   "applied" if body in (code_for(code["va"], data["va"]),
                                          code_for(code["va"], data["va"], seasons=True)) else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed historic Quick Game hooks or owned code")
    for va, size, digest, what in GUARDS:
        require(_guard_digest(image, va, size, edits) == digest, f"foreign {what} at {va:#x}")
    return next(iter(states))


def status(payload):
    try:
        return _recognize(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def season_routing_status(payload):
    if status(payload) != 'applied':
        return False
    code,data=allocations(payload)
    return XbeImage(payload).read(code['va'],CODE_SIZE)==code_for(code['va'],data['va'],seasons=True)


def enable_season_routing(payload):
    require(status(payload)=='applied','historic roster bank requires local historic selection')
    code,data=allocations(payload)
    # This owner alone admits this exact, verified configuration transition.
    # The generic allocator continues refusing arbitrary filled-code replacement.
    buffer=bytearray(payload)
    buffer[code['raw']:code['raw']+CODE_SIZE]=code_for(code['va'],data['va'],seasons=True)
    _,_,requests=space._validate(payload)
    if space.is_scaleout(payload):
        space._seal_scaleout(buffer,requests)
    else:
        buffer[space.DIRECTORY:space._directory_end(requests)]=space._directory(requests,space._code_bytes(buffer,requests))
        for section in _sections(buffer):
            buffer[section.header_offset+36:section.header_offset+56]=section_digest(buffer,section)
    result=bytes(buffer)
    require(season_routing_status(result),'season filename route readback failed')
    return result


def apply(payload):
    """Install on a clean base, or replay an installed copy unchanged."""
    state = _recognize(payload)  # full preflight before allocation/mutation
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, label=UI_LABEL,
                  body_bytes=len(assembly.CODE), rx_bytes=CODE_SIZE, rw_bytes=DATA_SIZE, ro_bytes=0,
                  save_growth=0, quick_game_flow=QUICK_GAME_FLOW)
    if state == "applied":
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    if space.status(payload) == "retail":
        # Alone, the two-page layout; with any scale-out owner the Build pass reserves the whole union first.
        allocated, receipt = space.apply(payload, REQUESTS)
    else:
        allocations(payload)
        allocated, receipt = payload, {}
    code, data = allocations(allocated)
    result, _ = space.install_code(allocated, OWNER, code_for(code["va"], data["va"]))
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = sites(code["va"])
    for _, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at + len(before)] = after
    for section in _sections(buffer):
        buffer[section.header_offset + 36:section.header_offset + 56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(status(result) == "applied", "historic teams in Quick Game postcondition failed")
    return result, dict(common, status="applied", allocation=receipt,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
        file_growth=len(result) - len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
        after_sha256=hashlib.sha256(result).hexdigest(),
        edits=[dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for name, va, before, after in edits]
              + [dict(label="owned_code", va=hex(code["va"]), size=CODE_SIZE),
                 dict(label="owned_state", va=hex(data["va"]), size=DATA_SIZE)],
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
    require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
    else:
        receipt = dict(status=status(payload), owner=OWNER, experimental=True, runtime_witnessed=False)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
