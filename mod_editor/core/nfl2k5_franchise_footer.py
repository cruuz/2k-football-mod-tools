"""Franchise extension footer host (b780 J2, job j23-footer). EXPERIMENTAL.

One late allocator owner that writes and reads the ``2K5XTND1`` franchise footer (format and Studio codec:
``nfl2k5_franchise_extension``) through the game's own save transaction, and owns the one save-list admission check
for every franchise footer. It hosts the Player Progress footer (``nfl2k5_player_progress_screen`` installed in its
*hosted* variant: that owner keeps its screen and capture hooks; this owner saves and loads its 34,320 bytes, always as
the last bytes of the file, exactly where a v0.8 game reads them).

What the game does today (retail USA ``default.xbe``, static reading)
---------------------------------------------------------------------
* ``FUN_0016AA10`` adds the franchise save's parts (settings, roster, season, front office ``0x2D0780``); the save
  ``FUN_0016E3F0`` asks it twice (0x16E439 and the free-space check 0x16AB50), takes a main-heap buffer of that size
  (0x16E4A9), fills it (front office at 0x16E50D) and signs and writes it (0x16C2F0).
* The load ``FUN_0016E540`` admits the slot (``FUN_0016AB70``; a franchise slot must be exactly ``FUN_0016AA10``'s
  size), reads the file into a main-heap buffer of the file's size and runs the deserializers; the front office ends
  at 0x16E815.
* A new franchise is ``FUN_0013EE10`` (the Franchise menu 0x148CD1 and the MyCareer runtime both call it).

What this owner changes (five sites, each chained to the bytes it displaced)
---------------------------------------------------------------------------
* 0x16AA26 size: the displaced size (front office, + MyCareer's 128 when that owner adds it) + the Player Progress
  footer (when hosted) + the body (when this boot has one; it is allocated here the first time).
* 0x16E50D save: the displaced writer first (front office, MyCareer block), then the sealed body and the Player
  Progress footer at the end of the buffer.
* 0x16E815 load: the displaced reader first (MyCareer decodes there), then the footers from the file: a valid Player
  Progress footer goes to that owner (else it starts a fresh baseline, its own old-save rule); a body is checked block
  by block (a bad block is rebuilt from its seed, a bad header gives a fresh body); no body gives a fresh one.
* 0x16ABB5 admission: one check for every footer: retail saves, this build's native size and (on a larger arena)
  beta-78's, each with or without the MyCareer block and with any of the four footer combinations
  (``nfl2k5_franchise_extension.admitted_sizes``). It replaces MyCareer's own admission.
* 0x13EF21 new franchise: the body is made fresh (a new franchise never inherits the last one's history).

Memory
------
On a build with the 128 MB roster heap (``nfl2k5_k128`` with ``roster_heap``) the body is allocated once per boot from
the extra memory above 64 MB, so it costs the 64 MB heap the game plays in nothing; at 64 MB there is no extra region
and the history pauses (no body; saves are written without one; a loaded body is dropped and that is recorded in the
owner state). Without the roster heap the body lives in this owner's own writable memory (98,352 bytes with the state).

Allocation: code 4,096 B (the generated blob, the CONFIG table at ``xt_config``), data 64 B (K128 builds) or 98,352 B.
Late owner, after ``nfl2k5_player_progress_screen`` (it reads that owner's allocation) and after the MyCareer owner.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from . import nfl2k5_franchise_extension as ext
from . import nfl2k5_franchise_footer_code as runtime
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_franchise_footer"
EVIDENCE = "EXPERIMENTAL"
BUILD_CAPTION = "Franchise: team history, records and box scores (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL. Your franchise remembers what happened: every season's standings, playoff results and awards, "
    "club and league records, all-time leaders, Hall of Fame classes and the box scores of your team's games this "
    "season. It is kept in the franchise save itself (about 98 KB more per save; old saves load and start an empty "
    "history). With the 128 MB memory option it uses the extra memory; at 64 MB that build pauses the history. "
    "Saves made with it also load on builds without it (the history is then left out of the next save).")
CODE_SIZE = 4096
STATE_SIZE = 64
DATA_SIZE_EXTRA = STATE_SIZE
DATA_SIZE_STATIC = STATE_SIZE + ext.BODY_SIZE          # 98,352
CONFIG_AT = runtime.LABELS["xt_config"]
CONFIG_MAGIC, CONFIG_VERSION = 0x43485458, 1           # "XTHC"
STAMP = int.from_bytes(hashlib.sha256(runtime.CODE).digest()[:4], "little")
FLAG_MAIN_HEAP = 1
CONFIG_FIELDS = ("magic", "version", "state", "static_body", "pp_footer", "pp_baseline", "chain_size", "chain_save",
                 "chain_load", "seeds", "flags", "stamp", "chain_franchise")
STATE_FIELDS = {"magic": 0, "body": 4, "flags": 8, "source": 12, "loads": 16, "saves": 20, "load_result": 24,
                "last_admitted_size": 28}

# (label, VA, retail bytes, entry label, opcode, length)
SITE_TABLE = (
    ("total_size", 0x0016AA26, bytes.fromhex("e8555d1600"), "xt_size_hook", 0xE8, 5),
    ("save", 0x0016E50D, bytes.fromhex("e87e221600"), "xt_save_hook", 0xE8, 5),
    ("load", 0x0016E815, bytes.fromhex("e8661f1600"), "xt_load_hook", 0xE8, 5),
    ("admission", 0x0016ABB5, bytes.fromhex("e856feffffeb13"), "xt_admission", 0xE9, 7),
    ("new_franchise", 0x0013EF21, bytes.fromhex("e84afeffff"), "xt_franchise_hook", 0xE8, 5),
)
RETAIL_TARGETS = {"total_size": 0x002D0780, "save": 0x002D0790, "load": 0x002D0780, "new_franchise": 0x0013ED70}
CHAIN_FIELD = {"total_size": "chain_size", "save": "chain_save", "load": "chain_load",
               "new_franchise": "chain_franchise"}

# Retail context around each site (the site itself masked to its retail bytes), the allocator the body uses.
GUARDS = (
    ("total size", 0x0016AA10, 0x1F, "9593845e7f1ed72c863875db7487e4b2125d722cff22b27214c59da46ff7601c"),
    ("save front office", 0x0016E4FA, 0x1D, "9a05077e740a79120ab1451937c66bfb89f7697dfb2f8c9ab3f30acd1bf77ecc"),
    ("load front office", 0x0016E804, 0x16, "a44d273b2272cc92124bac027f8926c652a596012a56228a0d5e78c95d0e2684"),
    ("save-list admission", 0x0016AB70, 0x5F, "5f7c613df6c0ad6d2f0a0531dd937250406da24a0197573e38781e3b5ef8af77"),
    ("new franchise tail", 0x0013EF21, 0x0F, "379396e4bdd00ed08a541f566b4832749e86831afa53163cefb00be14527719b"),
    ("heap allocate", 0x00048700, 0x27, "2afa1c64c28563d908a6f69d13fc1944f151aa7fc7c9baf50e4ded284cf88d01"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, AttributeError)


class FranchiseFooterError(ValueError):
    """Unsupported executable, foreign or mixed installation, or no room for the owner."""


def _require(condition, message):
    if not condition:
        raise FranchiseFooterError(message)


def requests(*, static_body: bool) -> tuple:
    data = DATA_SIZE_STATIC if static_body else DATA_SIZE_EXTRA
    return ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", data, 16))


REQUESTS = requests(static_body=False)


def _rel32(source_end: int, target: int) -> bytes:
    return struct.pack("<i", target - source_end)


def _call_target(raw: bytes, va: int) -> int | None:
    return va + 5 + struct.unpack_from("<i", raw, 1)[0] if raw[:1] == b"\xe8" else None


def labels(code_va: int) -> dict[str, int]:
    return {name: code_va + offset for name, offset in runtime.LABELS.items()}


def code_for(code_va: int, config: Mapping[str, int], admission: bytes) -> bytes:
    """The owned RX content: the template with its relocations applied and the CONFIG table filled."""

    _require(len(admission) == 7, "the displaced admission bytes are seven")
    result = bytearray(runtime.CODE)
    for offset, kind, symbol, value in runtime.RELOCATIONS:
        _require(symbol == "code", "unexpected footer host relocation")
        target = code_va + value + struct.unpack_from("<i", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    values = dict(config)
    values.setdefault("magic", CONFIG_MAGIC)
    values.setdefault("version", CONFIG_VERSION)
    values.setdefault("stamp", STAMP)
    for index, name in enumerate(CONFIG_FIELDS):
        struct.pack_into("<I", result, CONFIG_AT + 4 * index, int(values.get(name, 0)) & 0xFFFFFFFF)
    result[CONFIG_AT + 52:CONFIG_AT + 60] = bytes(admission) + b"\0"
    _require(len(result) <= CODE_SIZE, "the footer host exceeds its fixed budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def read_config(blob: bytes) -> tuple[dict[str, int], bytes] | None:
    if len(blob) < CONFIG_AT + 64:
        return None
    values = {name: struct.unpack_from("<I", blob, CONFIG_AT + 4 * index)[0] for index, name in enumerate(CONFIG_FIELDS)}
    if values["magic"] != CONFIG_MAGIC or values["version"] != CONFIG_VERSION:
        return None
    return values, bytes(blob[CONFIG_AT + 52:CONFIG_AT + 59])


def sites(code_va: int) -> list[tuple[str, int, bytes, bytes]]:
    """Every executable edit as (label, VA, retail bytes, patched bytes)."""

    at = labels(code_va)
    return [(label, va, before, bytes([opcode]) + _rel32(va + 5, at[entry]) + b"\x90" * (length - 5))
            for label, va, before, entry, opcode, length in SITE_TABLE]


def allocations(payload: bytes) -> dict[str, dict]:
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER] if space.status(payload) == "applied" else []
    if not rows:
        return {}
    code = [r for r in rows if r["kind"] == "code"]
    data = [r for r in rows if r["kind"] == "data"]
    _require(len(code) == 1 and len(data) == 1 and len(rows) == 2 and (code[0]["size"], code[0]["align"]) == (CODE_SIZE, 16)
             and data[0]["size"] in (DATA_SIZE_EXTRA, DATA_SIZE_STATIC) and data[0]["align"] == 16,
             "foreign franchise footer allocation")
    return {"code": code[0], "data": data[0]}


def _guard_digest(image: XbeImage, va: int, size: int) -> str:
    content = bytearray(image.read(va, size))
    for _label, address, before, *_rest in SITE_TABLE:
        if va <= address and address + len(before) <= va + size:
            content[address - va:address - va + len(before)] = before
    return hashlib.sha256(content).hexdigest()


def guard_digests(payload: bytes) -> dict[str, str]:
    image = XbeImage(payload)
    return {name: _guard_digest(image, va, size) for name, va, size, _d in GUARDS}


def _check_guards(image: XbeImage) -> None:
    for name, va, size, digest in GUARDS:
        _require(_guard_digest(image, va, size) == digest, f"foreign franchise footer dependency: {name} ({va:#x})")


# ------------------------------------------------------------------------------------------- companions on the chain
def _my_career_handlers(payload: bytes) -> dict[str, int] | None:
    """The generic MyCareer owner's inline handlers ({site label: VA}) when its exact install is present."""

    from . import nfl2k5_my_career_mode as career
    try:
        found = [a for a in space.layout(payload)["allocations"] if a["owner"] == career.OWNER]
        if not found:
            return None
        code, data = career.legacy.allocations(payload)
        named = career.code_for(code["va"], data["va"])[1]
        return {"total_size": named["inline_size"], "save": named["inline_save"], "load": named["inline_load_end"],
                "admission": named["inline_admission"]}
    except _ERRORS:
        return None


def _pp_hosted(payload: bytes) -> tuple[int, int] | None:
    """(RAM footer VA, capture_baseline VA) of the Player Progress owner's exact hosted install, else None."""

    from . import nfl2k5_player_progress_screen as progress
    return progress.hosted_addresses(payload)


def _expected_chain(payload: bytes, label: str, target: int) -> bool:
    if target == RETAIL_TARGETS.get(label):
        return True
    handlers = _my_career_handlers(payload)
    return bool(handlers) and handlers.get(label) == target


def _expected_admission(payload: bytes, raw: bytes) -> bool:
    if raw == SITE_TABLE[3][2]:
        return True
    handlers = _my_career_handlers(payload)
    return bool(handlers) and raw == b"\xe9" + _rel32(0x16ABB5 + 5, handlers["admission"]) + b"\x90\x90"


# ------------------------------------------------------------------------------------------- recognize / apply
def _recognize(payload: bytes):
    _require(space.status(payload) != "foreign", "foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    found = allocations(payload)
    if not found:
        for label, va, before, *_rest in SITE_TABLE:
            raw = image.read(va, len(before))
            # another owner may hold a footer site (MyCareer, Player Progress); never this owner without allocation
            _require(raw[:1] in (b"\xe8", b"\xe9"), f"franchise footer site {label} is not a call or jump")
        _check_guards(image)
        return "retail", None, None
    code_va, data_va = found["code"]["va"], found["data"]["va"]
    blob = image.read(code_va, CODE_SIZE)
    if blob == b"\xcc" * CODE_SIZE:
        _check_guards(image)
        return "retail", found, None
    parsed = read_config(blob)
    _require(parsed is not None, "foreign franchise footer code (no CONFIG)")
    config, admission = parsed
    static = found["data"]["size"] == DATA_SIZE_STATIC
    _require(config["state"] == data_va and config["static_body"] == (data_va + STATE_SIZE if static else 0),
             "the footer host's memory does not match its allocation")
    _require(blob == code_for(code_va, config, admission), "foreign franchise footer code")
    _require(image.read(data_va, found["data"]["size"]) == bytes(found["data"]["size"]),
             "foreign initial franchise footer memory")
    for label, va, before, after in sites(code_va):
        _require(image.read(va, len(after)) == after, f"franchise footer site {label} is not this owner's")
    for label in ("total_size", "save", "load", "new_franchise"):
        target = config[CHAIN_FIELD[label]]
        if label == "new_franchise":
            _require(target == RETAIL_TARGETS[label], "the new-franchise site chains a foreign target")
        else:
            _require(_expected_chain(payload, label, target), f"the {label} site chains a foreign target")
    _require(_expected_admission(payload, admission), "the admission site displaced foreign bytes")
    hosted = _pp_hosted(payload)
    if config["pp_footer"] or config["pp_baseline"]:
        _require(hosted is not None and (config["pp_footer"], config["pp_baseline"]) == hosted,
                 "the hosted Player Progress addresses do not match that owner")
    else:
        _require(hosted is None, "a hosted Player Progress owner is installed but this host does not save it")
    _check_guards(image)
    return "applied", found, config


def owned_state(payload: bytes):
    """("retail" | "applied", allocations, config); anything else raises."""

    return _recognize(payload)


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except _ERRORS:
        return "foreign"


def underlying_view(payload: bytes) -> bytes:
    """The payload with this owner's five sites restored to the bytes they displaced (MyCareer's or retail), for the
    owners whose guards hash those routines (MyCareer, Auto Save). Unchanged unless this owner is exactly installed."""

    try:
        state, found, config = _recognize(payload)
    except _ERRORS:
        return payload
    if state != "applied":
        return payload
    parsed = read_config(XbeImage(payload).read(found["code"]["va"], CODE_SIZE))
    _admission = parsed[1]
    image = XbeImage(payload)
    view = bytearray(payload)
    for label, va, before, *_rest in SITE_TABLE:
        if label == "admission":
            original = _admission
        else:
            original = b"\xe8" + _rel32(va + 5, config[CHAIN_FIELD[label]])
        off = image.offset(va, len(original))
        view[off:off + len(original)] = original
    for section in _sections(view):
        view[section.header_offset + 36:section.header_offset + 56] = section_digest(view, section)
    return bytes(view)


def installed_sites(payload: bytes) -> list[tuple[str, int, bytes, bytes]]:
    """(label, VA, displaced bytes, installed bytes) of an exact install; empty otherwise."""

    try:
        state, found, config = _recognize(payload)
    except _ERRORS:
        return []
    if state != "applied":
        return []
    admission = read_config(XbeImage(payload).read(found["code"]["va"], CODE_SIZE))[1]
    rows = []
    for label, va, before, after in sites(found["code"]["va"]):
        original = admission if label == "admission" else b"\xe8" + _rel32(va + 5, config[CHAIN_FIELD[label]])
        rows.append((label, va, original, after))
    return rows


def body_pointer_va(payload: bytes) -> int | None:
    """The RAM cell (u32) holding the body pointer (0 until the first franchise use), for other native owners."""

    found = allocations(payload)
    return found["data"]["va"] + STATE_FIELDS["body"] if found else None


def body_function_va(payload: bytes) -> int | None:
    """``xt_body`` (fastcall, ecx = 1 to allocate on first use): the body pointer or 0, for other native owners."""

    found = allocations(payload)
    return found["code"]["va"] + runtime.LABELS["xt_body"] if found else None


def reservations(payload: bytes) -> list[dict]:
    rows = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    found = allocations(payload)
    edits = sites(found["code"]["va"] if found else 0x14DA000)
    return rows + [dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                        basis="pinned live " + label + "; not a cave") for label, va, before, _after in edits]


def apply(payload: bytes, *, static_body: bool = False, main_heap_ok: bool = False,
          seeds_va: int = 0) -> tuple[bytes, Mapping[str, object]]:
    """Install the host over whatever holds the footer sites now (retail, MyCareer). Needs the scale-out pool.

    ``static_body``: keep the body in this owner's writable memory (builds without the 128 MB roster heap).
    ``main_heap_ok``: without an extra region, take the body from the main heap (off by default: see the module text).
    The Player Progress owner, when present, must already be installed in its hosted variant."""

    _require(type(static_body) is bool and type(main_heap_ok) is bool, "static_body and main_heap_ok are booleans")
    state, found, _config = _recognize(payload)
    common = {"owner": OWNER, "experimental": True, "code_bytes": len(runtime.CODE), "owner_bytes": CODE_SIZE,
              "body_bytes": ext.BODY_SIZE, "static_body": static_body}
    if state == "applied":
        return payload, {**common, "status": "already_applied", "changed_bytes": 0}
    from . import nfl2k5_player_progress_screen as progress
    _require(progress.variant(payload) != "full", "Player Progress is installed with its own footer; build it hosted")
    image = XbeImage(payload)
    chains, admission = {}, b""
    for label, va, before, *_rest in SITE_TABLE:
        raw = image.read(va, len(before))
        if label == "admission":
            _require(_expected_admission(payload, raw), "the admission site holds foreign bytes")
            admission = raw
            continue
        target = _call_target(raw, va)
        _require(target is not None, f"the {label} site is not a call")
        if label == "new_franchise":
            _require(target == RETAIL_TARGETS[label], "the new-franchise site is already hooked by another owner")
        else:
            _require(_expected_chain(payload, label, target), f"the {label} site calls a foreign target")
        chains[CHAIN_FIELD[label]] = target
    _check_guards(image)
    before = payload
    wanted = requests(static_body=static_body)
    if not found:
        if space.status(payload) == "retail":
            payload, allocation_receipt = space.apply(payload, wanted, scaleout=True)
        else:
            _require(space.is_scaleout(payload), "the franchise footer needs the scale-out allocator")
            payload, allocation_receipt = space.extend_scaleout(payload, wanted)
        found = allocations(payload)
    else:
        allocation_receipt = {}
    _require((found["data"]["size"] == DATA_SIZE_STATIC) == static_body, "the allocated memory variant differs")
    code_va, data_va = found["code"]["va"], found["data"]["va"]
    hosted = _pp_hosted(payload)
    config = {**chains, "state": data_va, "static_body": data_va + STATE_SIZE if static_body else 0,
              "pp_footer": hosted[0] if hosted else 0, "pp_baseline": hosted[1] if hosted else 0,
              "seeds": seeds_va, "flags": FLAG_MAIN_HEAP if main_heap_ok else 0}
    payload, code_receipt = space.install_code(payload, OWNER, code_for(code_va, config, admission))
    buf = bytearray(payload)
    image = XbeImage(payload)
    for label, va, _before, after in sites(code_va):
        off = image.offset(va, len(after))
        buf[off:off + len(after)] = after
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "franchise footer postcondition failed")
    return result, {**common, "status": "applied", "code_va": hex(code_va), "data_va": hex(data_va),
                    "hosts_player_progress": bool(hosted), "main_heap_ok": main_heap_ok,
                    "chains": {k: hex(v) for k, v in chains.items()}, "admission_displaced": admission.hex(),
                    "allocation": allocation_receipt, "code_install": code_receipt,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": space.count_differing_bytes(before, result),
                    "file_growth": len(result) - len(before),
                    "sites": [{"label": label, "va": hex(va), "size": len(b)} for label, va, b, _a in sites(code_va)]}


__all__ = ["OWNER", "REQUESTS", "CODE_SIZE", "DATA_SIZE_EXTRA", "DATA_SIZE_STATIC", "FranchiseFooterError", "apply",
           "allocations", "body_function_va", "body_pointer_va", "code_for", "guard_digests", "installed_sites",
           "labels", "owned_state", "read_config", "requests", "reservations", "sites", "status", "underlying_view"]
