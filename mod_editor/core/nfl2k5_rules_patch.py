"""Strict owned-space transactions shared by beta-69 rule writers.

No allocation policy lives here. Reserve the complete selected REQUESTS union
on a clean base. Runtime data is RW, options/text RO, instructions RX.
"""
from __future__ import annotations

import hashlib
import struct
import zlib

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage


def allocations(payload, module):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == module.OWNER]
    result = {a["kind"]: a for a in rows}
    space._require(len(rows) == len(module.REQUESTS), "Reserve the complete rules owner union on a clean base")
    for _, kind, size, align in module.REQUESTS:
        space._require(kind in result and (result[kind]["size"], result[kind]["align"]) == (size, align),
                       "Foreign rules allocation geometry")
    return result


def inspect(payload, module):
    space._require(isinstance(payload, bytes) and len(payload) <= space.SCALE_FILE_SIZE,
                   "Expected bounded default.xbe bytes")
    layout = space.layout(payload)
    image = XbeImage(payload)
    places = (allocations(payload, module) if any(a["owner"] == module.OWNER for a in layout["allocations"])
              else None)
    settings = None
    if places:
        for kind, row in places.items():
            if kind == "data":
                space._require(image.read(row["va"], row["size"]) == bytes(row["size"]),
                               "Offline rules runtime state must be zero")
        code = image.read(places["code"]["va"], places["code"]["size"])
        options = image.read(places["read_only"]["va"], places["read_only"]["size"])
        if code == b"\xcc" * places["code"]["size"]:
            space._require(options == bytes(len(options)), "Mixed rules options/code")
        else:
            settings = module.decode_options(options)
            space._require(code == module.code_for(places), "Foreign rules code, relocation or padding")
    sites = module.sites(places)
    for name, va, before, after in sites:
        space._require(image.read(va, len(before)) == (after if settings is not None else before),
                       f"Mixed/foreign {module.OWNER} {name} hook")
    for va, size, digest in module.GUARDS:
        blob = bytearray(image.read(va, size))
        for _, hook, before, _ in sites:
            if va <= hook and hook + len(before) <= va + size:
                blob[hook-va:hook-va+len(before)] = before
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"Foreign {module.OWNER} prerequisite at {va:#x}")
    if hasattr(module, "validate_neighbors"):
        module.validate_neighbors(payload, image)
    return settings


def status(payload, module):
    try:
        return "applied" if inspect(payload, module) is not None else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, zlib.error):
        return "foreign"


def verify(payload, module, expected=None):
    settings = inspect(payload, module)
    if expected is not None:
        space._require(settings == expected, "Rules options differ from requested build")
    return dict(status="applied" if settings is not None else "retail", settings=settings,
                experimental=True, runtime_witnessed=False, option_source="build_time")


def apply(payload, module, settings=None):
    previous = inspect(payload, module)
    selected = settings if settings is not None else (previous if previous is not None else module.DEFAULTS)
    encoded = module.encode_options(**selected)
    if previous is not None:
        space._require(previous == selected, "Different rules options; rebuild from a clean base")
        return payload, dict(**verify(payload, module, selected), owner=module.OWNER,
                             changed_bytes=0, edits=[])
    allocated, allocation_receipt = (space.apply(payload, module.REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated, module)
    installed, _ = space.install_code(allocated, module.OWNER, module.code_for(places))
    installed, _ = space.install_read_only(installed, module.OWNER, encoded)
    sites = module.sites(places)
    result, patch = rdata.apply(installed, sites, module.OWNER)
    return result, dict(**verify(result, module, selected), owner=module.OWNER,
        allocation=allocation_receipt, sections_repinned=patch["sections_repinned"],
        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
        file_growth=len(result)-len(payload),
        before_sha256=hashlib.sha256(payload).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
        edits=[dict(label=name, va=hex(va), before=before.hex(), after=after.hex())
               for name, va, before, after in sites],
        reservations=[r for r in space.reservations(result) if r["owner"] == module.OWNER] +
                     [dict(owner=module.OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
                           basis="pinned live rule hook; not a cave") for _, va, before, _ in sites])


def relocate(assembly, places, symbols):
    code_va = places["code"]["va"]
    symbols = {**symbols, "code": code_va}
    content = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", content, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", content, offset, target & 0xFFFFFFFF)
    size = places["code"]["size"]
    space._require(len(content) <= size, "Rules code exceeds its reservation")
    return bytes(content).ljust(size, b"\xcc")


def hook_sites(hooks, assembly, places):
    va = places["code"]["va"] if places else 0
    return [(name, address, before, opcode + struct.pack("<i", va + assembly.LABELS[name] - address - 5)
             + b"\x90" * (len(before)-5)) for name, address, before, opcode in hooks]
