"""Pinned immutable allocations for the r62 gameplay levers.

No allocator policy lives here. Reserve the complete owner union on a clean
base before composing. Constants are immutable RX data, never runtime state.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage


def allocation(payload, owner, size):
    found = [a for a in space.layout(payload)["allocations"] if a["owner"] == owner]
    space._require(len(found) == 1 and (found[0]["kind"], found[0]["size"], found[0]["align"])
                   == ("code", size, 16), f"{owner}: reserve the complete owner union on a clean base")
    return found[0]


def recognize(payload, module):
    layout = space.layout(payload)  # also validates every digest and allocator seal
    image = XbeImage(payload)
    for va, size, digest in module.GUARDS:
        # Hash complete dependent routines, restoring only this owner's hook
        # operands for the comparison. Hook recognition below is independent.
        blob = bytearray(image.read(va, size))
        for _label, hook, before, _after in module.sites(0):
            if va <= hook and hook + len(before) <= va + size:
                blob[hook - va:hook - va + len(before)] = before
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"{module.OWNER}: foreign prerequisite at {va:#x}")
    present = any(a["owner"] == module.OWNER for a in layout["allocations"])
    a = allocation(payload, module.OWNER, module.CODE_SIZE) if present else None
    sites = module.sites(a["va"] if a else 0)
    original = all(image.read(va, len(before)) == before for _, va, before, _ in sites)
    if not a:
        space._require(original, f"{module.OWNER}: hook without allocation")
        return "retail"
    content = image.read(a["va"], a["size"])
    if content == b"\xcc" * a["size"]:
        space._require(original, f"{module.OWNER}: hook with empty allocation")
        return "retail"
    space._require(content == module.code_for(a["va"]), f"{module.OWNER}: foreign constants/code")
    space._require(all(image.read(va, len(after)) == after for _, va, _, after in sites),
                   f"{module.OWNER}: mixed/foreign hook")
    return "applied"


def status(payload, module):
    try:
        return recognize(payload, module)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError):
        return "foreign"


def apply(payload, module):
    state = status(payload, module)
    space._require(state != "foreign", f"{module.OWNER}: foreign/mixed bytes; refusing")
    common = {"owner": module.OWNER, "experimental": True, "runtime_witnessed": False,
              "runtime_state_bytes": 0, "mapping": module.mapping()}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "edits": []}
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, module.REQUESTS)
    else:
        allocation(payload, module.OWNER, module.CODE_SIZE)  # fail before mutation
        allocated, receipt = payload, {}
    a = allocation(allocated, module.OWNER, module.CODE_SIZE)
    code = module.code_for(a["va"])
    installed, _ = space.install_code(allocated, module.OWNER, code)
    result, patch = rdata.apply(installed, module.sites(a["va"]), module.OWNER)
    space._require(status(result, module) == "applied", "gameplay lever postcondition failed")
    edits = [{"label": label, "va": hex(va), "file_offset": hex(rdata.offset_of(result, va)),
              "before": before.hex(), "after": after.hex()}
             for label, va, before, after in module.sites(a["va"])]
    edits.append({"label": "immutable_allocation", "va": hex(a["va"]), "file_offset": hex(a["raw"]),
                  "before": (b"\xcc" * len(code)).hex(), "after": code.hex()})
    return result, {**common, "already_applied": False, "edits": edits,
                    "allocation": receipt, "reservations": space.reservations(result),
                    "sections_repinned": patch["sections_repinned"],
                    "changed_bytes": sum(x != y for x, y in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload),
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}
