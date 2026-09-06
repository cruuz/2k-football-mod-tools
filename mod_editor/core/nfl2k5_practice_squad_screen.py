"""Coach's Desk Practice Squad destination. EXPERIMENTAL / UNWITNESSED.

Clones the Team Rosters sheet with Active/Reserves pages and a single move
plus Cancel. Uses the shipped native transactions, including salary and slot
repair. No poaching, protection, new save fields, or global roster callbacks.
Reserve REQUESTS with the entire selected allocator union before applying.
Tables are immutable RX content within the 4096-byte budget; state is RW.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_practice_squad_screen_code as assembly
from . import nfl2k5_franchise_practice as fp
from . import nfl2k5_practice_squad as ps
from . import nfl2k5_practice_reserves as pr
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_practice_squad_screen"
CODE_SIZE = 4096
DATA_SIZE = 256
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: Coach's Desk has no reserve list or move actions. "
    "Patch: Practice Squad replaces The Crib on Coach's Desk with Active and Reserves "
    "pages, Demote and Promote. Keep up to 53 active players. Larger reserves "
    "require the separate roster growth patch and a migrated save. "
    "Trophy Room remains on the main menu. CPU poaching and protection are off."
)
TEMPLATES = {"descriptor": (0x555098, 48), "frame": (0x555070, 40),
             "sheet": (0x554C70, 320), "active_page": (0x554B58, 280),
             "reserve_page": (0x554B58, 280)}
# SHA-256 pins for every cloned source and dependent native ABI. Generated
# from the pinned USA retail XBE, never inferred from an arbitrary input.
GUARDS = (
    (0x524fa0, 48, "90f26a988f65ad451b3bde35543b0d8d0b0fb1094be63affa824ebeb3be9fb3d"),
    (0x24d440, 29, "0f697fa74abaa4e1d38046f2439f77d41f1138ff99ae5e9b18fa09c8f88dd3fc"),
    (0x515528, 52, "df49dfaca4c581d0a6a0c89f13fa44ea094ab9bced847db52e2b1bcbc445ca89"),
    (0x555098, 48, "e989d4069bd58732ab3e2bd7c0d66af382006f6568638ec44220a5a14dcfd178"),
    (0x555070, 40, "85bb00909245b27782f6b853ab09f1b57ef8d4e10b8bced6df0207caacd85fed"),
    (0x554c70, 320, "ce0f52a0bbed8918faaf8cf5dfb1f99ddac7f7b7849412ed4ab44d1861db214e"),
    (0x554b58, 280, "d157a52a3db3f3c9ef754165ae358b84706d40fe4f6013aa34fbde3b3da024b3"),
    (0x521ff0, 416, "39dc09ba2529425dd26ddde35ae725a69fa8ed3f5cca043d6f9cefc776dff42e"),
    (0xf40f0, 408, "957c5abfe279d16e6072c288cc54174beffd1903cbc64df0964722a91b4175a6"),
    (0x6e4e0, 330, "99caf0191ed992d21b0f97a695a27cc63d1740ef4ec6483af48a10a211e9242d"),
    (0x14e440, 47, "d60ded014278ec6b17d843deb5ba7a6a208e2b8a364a63ca9bffefd74e6cfcbd"),
    (0x174c70, 61, "ecbd475f904a85d4d72eeb8cc62d9229becbba6c8b0a22cd27d7793577b4f600"),
    (0x1707c0, 36, "d1fbfb20a21f0af6c2d0287d9bd2305ae3e419753b1f732421552fc0d00f34a1"),
    (0x172680, 300, "d0acf62180e6e1f5961b58e699f00d058c9ff7c77007f6080939b965f12b90f2"),
    (0x172930, 164, "b8d991896aabb70143b396ac73aa586f311fabd3c1fcd36eb665f3821878cebf"),
    (0x27ccd0, 3, "58367ffa2a0179375018fa0f5c26da24391e42ebe0ed8fdda35a21fc7bdc396f"),
    (0x542518, 176, "19ba3de086f338eb1677dbb8ffa8fdb2e9e1efd2b450c7e3157e3843bdfb3548"),
    (0x5408e8, 176, "2b818337299a0fc36e4240f7a408659e044f5977ef88b24ad73fcd35a7a5450c"),
)


class PracticeSquadScreenError(ValueError):
    """Mixed, foreign, unreserved or missing prerequisite screen bytes."""


def _require(ok, message):
    if not ok:
        raise PracticeSquadScreenError(message)


def allocations(payload):
    found = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(found) == {"code", "data"}, "reserve the complete Practice Squad screen request union first")
    for _, kind, size, align in REQUESTS:
        _require((found[kind]["size"], found[kind]["align"]) == (size, align), "foreign screen allocation")
    return found["code"], found["data"]


def code_for(payload, code_va, data_va):
    """Deterministic relocated code and immutable clones, using pinned sources."""
    image = XbeImage(payload)
    out = bytearray(assembly.CODE)
    labels = {key: code_va + offset for key, offset in assembly.LABELS.items()}

    def append(name, content):
        out.extend(b"\xcc" * (-len(out) % 4))
        labels[name] = code_va + len(out)
        out.extend(content)

    for name, (va, size) in TEMPLATES.items():
        append(name, image.read(va, size))
    # 12 actions + terminator + one zero padding record. The fixed 728-byte
    # allowance comes from the brief's additive menu estimate; replacing the
    # Crib consumes only 13 records. Never introduce a fake thirteenth action.
    menu = image.read(fp.NEW_ROW_VA, 13 * fp.ROW_SIZE)
    rows = [menu[i:i + fp.ROW_SIZE] for i in range(0, len(menu), fp.ROW_SIZE)]
    rows = rows[:5] + [rows[8]] + rows[5:8] + rows[9:]
    append("menu", b"".join(rows) + bytes(fp.ROW_SIZE))
    append("hooks", bytes(28))
    for name in ("enter_record", "leave_record", "back_record"):
        append(name, bytes(40))
    for name, value in (("screen_text", "Practice Squad"), ("active_text", "Active"),
                        ("reserve_text", "Reserves"), ("promote_text", "Promote"),
                        ("demote_text", "Demote"), ("cancel_text", "Cancel"),
                        ("invalid_text", "Select your franchise team first."),
                        ("refused_text", "Move refused. Check team ownership and your active and reserve limits.")):
        append(name, value.encode("utf-16le") + b"\0\0")
    append("promote_menu", bytes(24))
    append("demote_menu", bytes(24))
    labels["active_binding"] = labels["sheet"] + 0xF4
    labels["reserve_binding"] = labels["sheet"] + 0xF8

    def put(name, offset, *values):
        struct.pack_into("<" + "I" * len(values), out, labels[name] - code_va + offset, *values)

    put("descriptor", 0, labels["screen_text"], labels["hooks"])
    put("descriptor", 0x14, labels["frame"])
    put("frame", 0, labels["sheet"])
    put("sheet", 0x30, labels["selector"])
    put("sheet", 0x48, labels["title"])
    put("sheet", 0x60, labels["one"])
    put("sheet", 0x78, labels["selector"])
    put("sheet", 0x90, labels["selector"])
    put("sheet", 0xC4, labels["activate"])
    put("sheet", 0xF4, labels["active_page"], labels["reserve_page"], *([0] * 17))
    for name, tab in (("active_page", "active"), ("reserve_page", "reserve")):
        put(name, 8, labels[tab + "_text"])
        put(name, 0x30, labels[tab + "_count"])
        put(name, 0x48, labels[tab + "_get"])
        put(name, 0x94, 0)
    put("menu", 5 * fp.ROW_SIZE + 4, labels["screen_text"])
    put("menu", 5 * fp.ROW_SIZE + 0x28, labels["row"], 0)
    put("hooks", 0, 1, labels["enter_record"], 5, labels["leave_record"],
        10, labels["back_record"], 0)
    put("enter_record", 0, 1, labels["enter"])
    put("leave_record", 0, 1, labels["leave"])
    put("back_record", 0, 7)  # native dispatcher pops this screen
    for tab in ("promote", "demote"):
        put(tab + "_menu", 0, labels[tab + "_text"], 1, labels["cancel_text"], 0, 0, 0)
    symbols = {**labels, "code": code_va, "state_data": data_va, "fade": fp.FADE_VA,
               "dialog": 0x14E440, "rebuild": 0x174C70, "clamp": 0x1707C0,
               "ps_reserve_count": ps.SYMBOLS["reserve_count"],
               "ps_promote": ps.SYMBOLS["ps_promote"], "ps_demote": ps.SYMBOLS["ps_demote"]}
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        addend = struct.unpack_from("<I", out, offset)[0]
        target = symbols[symbol] + value + addend
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", out, offset, target & 0xFFFFFFFF)
    _require(len(out) <= CODE_SIZE, "Practice Squad screen exceeds its 4096-byte budget")
    labels["content_end"] = code_va + len(out)
    return bytes(out).ljust(CODE_SIZE, b"\xcc"), labels


def _owned_state(payload):
    """Validate this owner's content without recursing through prerequisites."""
    layout = space.layout(payload)  # section digests and allocator seals
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        content = image.read(va, size)
        if va == 0x6E4E0 and content[:5] != bytes.fromhex("5155578bf9"):
            # Playlist tier 4b adapts the shared event-dispatch prologue. Accept
            # only its complete sealed installation, then pin every remaining
            # native instruction. Never normalize an arbitrary jump or cave.
            # Playlist in turn validates MyCareer's separate PUSH detour at
            # 0x6E390; MyCareer touches none of our guards or cloned templates.
            from . import nfl2k5_music_playlist as playlist
            _require(playlist.status(payload) == "applied", "foreign music screen-dispatch hook")
            content = playlist.HOOKS["screen_event"][1] + content[5:]
        _require(hashlib.sha256(content).hexdigest() == digest,
                 f"foreign Practice Squad screen prerequisite at {va:#x}")
    # Pin the already-composed Schedule/Practice records and other franchise
    # sites, excluding only the row pointer whose ownership we explicitly take.
    original_pointer = struct.pack("<I", fp.COACH_DESK_ROWS_VA)
    prior_pointer = struct.pack("<I", fp.NEW_ROW_VA)
    pointer = image.read(fp.COACH_DESK_ROWS_PTR_VA, 4)
    found = any(a["owner"] == OWNER for a in layout["allocations"])
    if not found:
        _require(pointer in (original_pointer, prior_pointer), "screen pointer without allocation")
        return "retail", None, None
    code, data = allocations(payload)
    _require(image.read(data["va"], data["size"]) == bytes(DATA_SIZE), "foreign on-disc screen state")
    blob = image.read(code["va"], CODE_SIZE)
    if blob == b"\xcc" * CODE_SIZE:
        _require(pointer in (original_pointer, prior_pointer), "screen hook with empty allocation")
        return "retail", code, data
    expected, labels = code_for(payload, code["va"], data["va"])
    _require(blob == expected and pointer == struct.pack("<I", labels["menu"]),
             "mixed/foreign Practice Squad screen code, tables or pointer")
    return "applied", code, data


def owns_franchise_pointer(payload):
    """Narrow delegation contract used by Franchise Practice status/replay."""
    try:
        return _owned_state(payload)[0] == "applied"
    except (ValueError, KeyError, TypeError, IndexError, struct.error, OverflowError):
        return False


def status(payload):
    try:
        state = _owned_state(payload)[0]
        if state == "applied":
            _require(ps.status(payload) == pr.status(payload) == fp.status(payload) == "applied",
                     "screen prerequisites are missing")
        return state
    except (ValueError, KeyError, TypeError, IndexError, struct.error, OverflowError):
        return "foreign"


def apply(payload):
    state = status(payload)
    _require(state != "foreign", "foreign/mixed Practice Squad screen; refusing")
    _require(ps.status(payload) == pr.status(payload) == fp.status(payload) == "applied",
             "apply practice squads, Franchise Practice and practice reserves first")
    common = {"owner": OWNER, "experimental": True, "runtime_witnessed": False,
              "code_capacity": CODE_SIZE, "runtime_state_bytes": DATA_SIZE,
              "poaching": False, "protection": False, "save_growth": 0,
              "active_limit": 53, "reserve_limit": 12, "total_limit": 65}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "edits": []}
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        allocations(payload)  # sealed request set must include us before any writes
        allocated, allocation_receipt = payload, {}
    code, data = allocations(allocated)
    blob, labels = code_for(allocated, code["va"], data["va"])
    result, code_receipt = space.install_code(allocated, OWNER, blob)
    before = struct.pack("<I", fp.NEW_ROW_VA)
    after = struct.pack("<I", labels["menu"])
    result, receipt = rdata.apply(result, [("practice_squad_menu", fp.COACH_DESK_ROWS_PTR_VA,
                                           before, after)], OWNER)
    _require(status(result) == "applied", "Practice Squad screen postcondition failed")
    return result, {**common, **receipt, "already_applied": False,
                    "allocation": allocation_receipt, "code_install": code_receipt,
                    "code_bytes": len(assembly.CODE),
                    "immutable_bytes": labels["content_end"] - code["va"] - len(assembly.CODE),
                    "labels": {k: hex(v) for k, v in labels.items()},
                    "reservations": space.reservations(result),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}
