"""Strict owned-space transactions shared by beta-69 rule writers.

No allocation policy lives here. Reserve the complete selected REQUESTS union
on a clean base. Runtime data is RW, options/text RO, instructions RX.

b780 modes2: a module may name earlier releases of its code with ``previous(places)`` -> [(code, sites)], each the
exact body and hook sites a shipped revision installed in the same allocation. Such an install reads "previous"
(status) and apply() upgrades it in place: the owned code, then every hook whose bytes differ (a site the earlier
revision did not hook goes from retail to this revision's bytes). The options, the data and the allocation stay.
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


def _revisions(module, places):
    """[(revision, code, sites)]: this revision first, then the module's earlier releases (newest first)."""
    rows = [("current", module.code_for(places), module.sites(places))]
    if places and hasattr(module, "previous"):
        rows += [("previous", code, sites) for code, sites in module.previous(places)]
    return rows


def inspect(payload, module):
    return _inspect(payload, module)[0]


def installed_revision(payload, module):
    """'current', 'previous' (an earlier release the module names) or None (not installed)."""
    return _inspect(payload, module)[1]


def _inspect(payload, module):
    from . import nfl2k5_era_rules as era
    payload = era.underlying_view(payload)
    space._require(isinstance(payload, bytes) and len(payload) <= space.SCALE_FILE_SIZE,
                   "Expected bounded default.xbe bytes")
    layout = space.layout(payload)
    image = XbeImage(payload)
    places = (allocations(payload, module) if any(a["owner"] == module.OWNER for a in layout["allocations"])
              else None)
    settings = None
    revision = None
    sites = module.sites(places)
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
            match = [(rev, sites_of) for rev, body, sites_of in _revisions(module, places) if body == code]
            space._require(bool(match), "Foreign rules code, relocation or padding")
            revision, sites = match[0]
    if revision == "previous":
        # an earlier release did not hook every site of this revision: those stay retail in its image
        current = {va for _n, va, _b, _a in module.sites(places)}
        listed = {va for _n, va, _b, _a in sites}
        sites = list(sites) + [row for row in module.sites(places) if row[1] in current - listed]
        old = {va: after for _n, va, _b, after in sites if va in listed}
        sites = [(n, va, before, old.get(va, before)) for n, va, before, _a in sites]
    for name, va, before, after in sites:
        space._require(image.read(va, len(before)) == (after if settings is not None else before),
                       f"Mixed/foreign {module.OWNER} {name} hook")
    sites = module.sites(places) if revision == "previous" else sites
    # b776-ai2: a module may name verified neighbor hooks inside its guarded spans (the neighbor
    # verifies its own complete bytes); they are restored to retail for the hash like its own sites.
    neighbors = list(module.neighbor_sites(payload)) if hasattr(module, "neighbor_sites") else []
    for va, size, digest in module.GUARDS:
        blob = bytearray(image.read(va, size))
        for _, hook, before, _ in list(sites) + neighbors:
            if va <= hook and hook + len(before) <= va + size:
                blob[hook-va:hook-va+len(before)] = before
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"Foreign {module.OWNER} prerequisite at {va:#x}")
    if hasattr(module, "validate_neighbors"):
        module.validate_neighbors(payload, image)
    return settings, revision


def status(payload, module):
    """'retail', 'applied', 'previous' (an earlier release the module names; apply() upgrades it) or 'foreign'."""
    try:
        settings, revision = _inspect(payload, module)
        return "retail" if settings is None else "previous" if revision == "previous" else "applied"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError, zlib.error):
        return "foreign"


def verify(payload, module, expected=None):
    settings = inspect(payload, module)
    if expected is not None:
        space._require(settings == expected, "Rules options differ from requested build")
    return dict(status="applied" if settings is not None else "retail", settings=settings,
                experimental=True, runtime_witnessed=False, option_source="build_time")


def _upgrade(payload, module, places):
    """An earlier release -> this revision in place: the owned code (same allocation), then the hooks that differ."""
    image = XbeImage(payload)
    old_code = image.read(places["code"]["va"], places["code"]["size"])
    _rev, _body, old_sites = next(row for row in _revisions(module, places) if row[0] == "previous"
                                  and row[1] == old_code)
    result, _ = space.install_code(payload, module.OWNER, module.code_for(places), previous=old_code)
    old = {va: after for _n, va, _b, after in old_sites}
    moved = [(name, va, old.get(va, before), after) for name, va, before, after in module.sites(places)
             if old.get(va, before) != after]
    if moved:
        result, _ = rdata.apply(result, moved, module.OWNER)
    space._require(installed_revision(result, module) == "current", f"{module.OWNER} upgrade read-back failed")
    return result, [dict(label=name, va=hex(va), before=before.hex(), after=after.hex())
                    for name, va, before, after in moved]


def apply(payload, module, settings=None):
    previous, revision = _inspect(payload, module)
    selected = settings if settings is not None else (previous if previous is not None else module.DEFAULTS)
    encoded = module.encode_options(**selected)
    if previous is not None:
        space._require(previous == selected, "Different rules options; rebuild from a clean base")
        if revision == "previous":
            result, edits = _upgrade(payload, module, allocations(payload, module))
            return result, dict(**verify(result, module, selected), owner=module.OWNER, upgraded=True,
                                changed_bytes=sum(a != b for a, b in zip(payload, result)), edits=edits)
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
