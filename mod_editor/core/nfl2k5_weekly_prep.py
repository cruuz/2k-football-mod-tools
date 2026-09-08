"""Native weekly preparation, USA Xbox. EXPERIMENTAL / UNWITNESSED.

Fix the DB drill's CB-only filter, prepare participants before played/simulated
games, and retain plans through native cleanup. Bonuses remain temporary.
Options are immutable build settings. Plans/state/seeds use existing save fields.
Reserve the complete selected REQUESTS union before installing an owner.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from . import nfl2k5_weekly_prep_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_weekly_prep"
CODE_SIZE = 1536
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: DB drills omit safeties; CPU teams skip "
    "weekly prep. Patch: include safeties, optionally prepare CPU teams before "
    "games and reuse your plan across weeks and seasons. The game's Weekly "
    "Preparation setting must be On. Bonuses end after the game."
)
SYMBOLS = dict(native_human=0x13EC30, native_team=0xC4C50,
               native_team_index=0xC4CA0, native_apply=0x2AC4E0,
               native_clear=0x2AB840, native_sim_value=0xC5220,
               play_continue=0x134045, db_continue=0x2AB709)
HOOKS = (
    ("db_group", 0x2AB701, "33c983f804", 0xE9),
    ("team_gate", 0x2AC483, "e8a827e9ff", 0xE8),
    ("team_seed", 0x2AB9A2, "e8c932e9ff", 0xE8),
    ("team_seed", 0x2ABF12, "e8592de9ff", 0xE8),
    ("before_sim", 0xC7B47, "e8d4d6ffff", 0xE8),
    ("before_play", 0x134040, "a18401e600", 0xE9),
    ("remember_clear", 0x2483F7, "e844340600", 0xE8),
    ("remember_clear", 0x2AC53F, "e8fcf2ffff", 0xE8),
)
# Pin the complete native preparation kernel, all 173 drill rows, position
# masks and dispatch tables. Normalize only our exact recognized hook bytes.
GUARDS = (
    (0x134040, 32, "0c1a838772338da28454c0c51ea81c74c908e3adccb296cc1d33094ae3473211"),
    (0x2A82F0, 16994, "3637c144be7b869e9565efaea12051f6f06ddcd2db41d04d122495472cb13303"),
    (0x51D358, 5536, "2eb55f92c760aaadcbc5bd18e1fc2b29313131beca0cb234eb722725c2e54897"),
    (0x51E8F8, 68, "7bbdbfd983a68c72f055a035febfd3f139f6162d7ad76cb2d80a4829c41c59ce"),
    (0xACD728, 280, "09e1f563971b920f979f6856b370142d18d8341bd6f244bb8b62889a5c265584"),
    (0x2D11F0, 179, "3bcb169c69edeb0de668d8b6de8983797309253b8078d3fb02a05c1da283256a"),
    (0xC4CA0, 176, "bf8d23c3b7b39effc8cc7e4a8da4a9fccd64a7e7bddc40403b4618fb702ea60b"),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def code_for(code_va, *, cpu=True, remember=True):
    require(type(cpu) is bool and type(remember) is bool, "weekly prep options must be bools")
    symbols = dict(SYMBOLS, cpu_option=int(cpu), remember_option=int(remember))
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    require(len(result) <= CODE_SIZE, "weekly prep exceeds its RX budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def allocation(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"]) ==
            ("code", CODE_SIZE, 16), "reserve weekly prep with the complete owner union on a clean base")
    return rows[0]


def sites(code_va=0):
    return [(name, va, bytes.fromhex(pin), bytes([opcode]) +
             struct.pack("<i", code_va + assembly.LABELS[name] - va - 5))
            for name, va, pin, opcode in HOOKS]


def _recognize(payload):
    layout = space.layout(payload)  # geometry, ownership, directory and section seals
    image = XbeImage(payload)
    owned = allocation(payload) if any(a["owner"] == OWNER for a in layout["allocations"]) else None
    edits = sites(owned["va"] if owned else 0)
    states = set()
    settings = None
    for _, va, before, after in edits:
        actual = image.read(va, len(before))
        states.add("retail" if actual == before else "applied" if owned and actual == after else "foreign")
    if owned:
        body = image.read(owned["va"], CODE_SIZE)
        if body == b"\xcc" * CODE_SIZE:
            states.add("retail")
        else:
            for cpu, remember in itertools.product((False, True), repeat=2):
                if body == code_for(owned["va"], cpu=cpu, remember=remember):
                    settings = dict(cpu=cpu, remember=remember)
                    break
            states.add("applied" if settings is not None else "foreign")
    require(states in ({"retail"}, {"applied"}), "foreign/mixed weekly prep hooks or owned code")
    for va, size, digest in GUARDS:
        raw = bytearray(image.read(va, size))
        for _, at, before, _ in edits:
            if va <= at and at + len(before) <= va + size:
                raw[at-va:at-va+len(before)] = before
        require(hashlib.sha256(raw).hexdigest() == digest, f"foreign weekly prep prerequisite at {va:#x}")
    return next(iter(states)), settings


def status(payload):
    try:
        return _recognize(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def read_settings(payload):
    state = status(payload)
    return dict(status=state, **(_recognize(payload)[1] or {})) if state != "foreign" else dict(status=state)


def apply(payload, *, cpu=None, remember=None):
    """None replays installed settings, or enables the option on a clean base.

    A changed option requires a clean rebuild, so receipts cannot pretend that
    an immutable setting was changed in an already patched executable.
    """
    require(cpu is None or type(cpu) is bool, "cpu must be a bool or None")
    require(remember is None or type(remember) is bool, "remember must be a bool or None")
    state, installed = _recognize(payload)  # full preflight before allocation/mutation
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  body_bytes=len(assembly.CODE), rx_bytes=CODE_SIZE, rw_bytes=0,
                  ro_bytes=0, save_growth=0, native_plan_words_per_team=500)
    if state == "applied":
        require((cpu is None or cpu == installed["cpu"]) and
                (remember is None or remember == installed["remember"]),
                "different weekly prep settings; rebuild from a clean base")
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[], **installed)
    settings = dict(cpu=True if cpu is None else cpu, remember=True if remember is None else remember)
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, REQUESTS, scaleout=True)
    else:
        allocation(payload)
        allocated, receipt = payload, {}
    code_va = allocation(allocated)["va"]
    result, _ = space.install_code(allocated, OWNER, code_for(code_va, **settings))
    image = XbeImage(result)
    buffer = bytearray(result)
    edits = sites(code_va)
    for _, va, before, after in edits:
        at = image.offset(va, len(before))
        buffer[at:at+len(before)] = after
    for section in _sections(buffer):
        buffer[section.header_offset+36:section.header_offset+56] = section_digest(buffer, section)
    result = bytes(buffer)
    require(status(result) == "applied", "weekly prep postcondition failed")
    return result, dict(common, **settings, status="applied", allocation=receipt,
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
        file_growth=len(result)-len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
        after_sha256=hashlib.sha256(result).hexdigest(),
        edits=[dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
               for name, va, before, after in edits] + [dict(label="owned_code", va=hex(code_va), size=CODE_SIZE)],
        reservations=space.reservations(result))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "apply", "audit"):
        p = sub.add_parser(command)
        p.add_argument("source", type=Path)
        if command == "apply":
            p.add_argument("output", type=Path)
            p.add_argument("--cpu", choices=("on", "off"), default="on")
            p.add_argument("--remember", choices=("on", "off"), default="on")
    args = parser.parse_args(argv)
    require(args.source.stat().st_size <= 16 * 1024 * 1024, "choose default.xbe, at most 16 MiB")
    payload = args.source.read_bytes()
    if args.command == "apply":
        result, receipt = apply(payload, cpu=args.cpu == "on", remember=args.remember == "on")
        with args.output.open("xb") as stream:
            stream.write(result)
    elif args.command == "audit":
        from .nfl2k5_weekly_prep_save import audit_tables
        receipt = audit_tables(payload)
    else:
        receipt = dict(read_settings(payload), owner=OWNER, experimental=True, runtime_witnessed=False)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
