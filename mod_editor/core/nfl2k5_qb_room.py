"""Reversible quarterback room owner for the standard 128 MiB franchise (beta 81 pieces 3 and 4, owner nfl2k5_qb_room).

Three fixed pages at 0x1529000 (nfl2k5_xbe_space.QB_ROOM_*) hold the native code, the QBROOMv1 settings record, the
counters and the event ring; whole 5-byte calls of the weekly advance enter them (nfl2k5_qb_room_code.HOOKS). The
installer authenticates every hook site and the whole page against the exact bytes it expects and refuses anything
else. Retail restores the sites and fills the pages with 0xCC; the reservation stays, so Realistic then Retail is the
source plus an empty reservation, byte for byte. The byte interface is .b77-scratch/b81/qb34/INTERFACE.md.
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.QB_ROOM_OWNER
REQUESTS = (space.QB_ROOM_REQUEST,)
VA = space.QB_ROOM_VA
SIZE = space.QB_ROOM_SIZE
LEVELS = ("retail", "realistic")
# Stage 0 handover: the hooks run and every pass only counts (and logs) in shadow. The stage bits move here, one
# stage at a time, after each stage's tests and panel (BUILD_ORDERS order 3). Shadow is on only while no stage is.
REALISTIC_STAGES = 0
SHADOW_DEFAULT = REALISTIC_STAGES == 0
ERRORS = (ValueError, TypeError, IndexError, KeyError, OverflowError, struct.error)


class QbRoomError(ValueError):
    """The requested option or the executable's installed state could not be verified."""


def _require(condition, message):
    if not condition:
        raise QbRoomError(message)


def _code():
    from . import nfl2k5_qb_room_code as code
    return code


def _allocation(payload):
    """The page's allocator row, or None when this executable has no reservation for it."""
    if not space.is_scaleout(payload):
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ("owner", "kind", "size", "align")) == REQUESTS[0]
             and rows[0]["va"] == VA and rows[0]["owner_offset"] == 0, "Unknown quarterback room allocation")
    section = XbeImage(payload).section(VA, SIZE)
    _require(section.writable and section.executable, "The quarterback room needs a writable executable pool")
    return rows[0]


def _ir_store_va(payload, stages):
    """The link word at +0x2020: the modern IR owner's store, which the signing pass (stage 4a) reads; 0 otherwise.
    0 with stage 4a means E2 never fires (the page counts sign_ir_unlinked)."""
    if not stages & _code().STAGE_SIGN:
        return 0
    from . import nfl2k5_injured_reserve as ir
    return ir.store_va(payload) or 0


def _sites_state(image, va, stages):
    """'retail' when every hook site holds its retail call, 'applied' when exactly the stage set's sites hold the
    calls into the page at ``va`` and the rest hold retail calls; anything else is foreign."""
    code = _code()
    wanted = {at: patched for _label, at, _original, patched in code.sites(va, stages)} if va else {}
    states = set()
    for at, original, _label, _need in code.HOOKS:
        found = image.read(at, len(original))
        if found == original and at not in wanted:
            states.add("retail")
        elif at in wanted and found == wanted[at]:
            states.add("applied")
        else:
            raise QbRoomError(f"Foreign or mixed quarterback room bytes at {at:#x}")
    return states


def _state(payload):
    """(status, settings, allocation) after authenticating every site and the whole page; raises when foreign."""
    code = _code()
    image = XbeImage(payload)
    allocation = _allocation(payload)
    if allocation is None:
        _sites_state(image, 0, 0)
        return "retail", None, None
    page = image.read(VA, SIZE)
    if page == b"\xcc" * SIZE:
        _sites_state(image, 0, 0)
        return "retail", None, allocation
    record = page[code.SETTINGS_OFFSET:code.SETTINGS_OFFSET + code.SETTINGS.size]
    settings = code.parse_settings(record)
    link = struct.unpack_from("<I", page, code.LINK_IR_STORE)[0]
    _require(link == _ir_store_va(payload, settings["stages"]), "Foreign quarterback room link words")
    _require(page == code.page_bytes(VA, record, ir_store_va=link), "Foreign quarterback room page")
    states = _sites_state(image, VA, settings["stages"])
    _require(states == {"applied"} or (states == {"applied", "retail"}), "Foreign or mixed quarterback room sites")
    return "applied", settings, allocation


def read_settings(payload):
    try:
        status, settings, allocation = _state(bytes(payload))
    except ERRORS as exc:
        return {"status": "foreign", "reason": str(exc)}
    if status == "retail":
        return {"status": "retail", "mode": "retail", "reserved": allocation is not None,
                "va": VA if allocation else None}
    return {"status": "applied", "mode": "realistic", "stages": settings["stages"], "shadow": settings["shadow"],
            "h0_ppm": settings["h0_ppm"], "d2_scale_milli": settings["d2_scale_milli"], "va": VA, "reserved": True}


def status(payload):
    return read_settings(payload)["status"]


def requirements(payload, stages=None):
    """Plain reasons this executable cannot take Realistic (empty when it can): 128 MiB standard, depth locks and
    lineup roles applied; for the signing stage (4a) also the economy, the practice squad, modern IR and the ownership
    page. A stage whose needs are missing is an error, never a silent skip."""
    from . import nfl2k5_depth_locks as locks, nfl2k5_k128 as memory, nfl2k5_lineup_roles as lineup
    code = _code()
    stages = REALISTIC_STAGES if stages is None else stages
    _require(not stages & code.STAGE_TRADE, "The quarterback room trade stage is not available in this build")
    _require(not stages & code.STAGE_E2 or stages & code.STAGE_SIGN, "The quarterback room E2 stage needs stage 4a")
    missing = []
    try:
        standard = bool(memory.read_settings(payload).get("require_128"))
    except ERRORS:
        standard = False
    if not standard:
        missing.append("The quarterback room rules need a 128 MB standard executable (the 128 MB start-up check).")
    if locks.status(payload) != "applied":
        missing.append("The quarterback room rules need depth chart locks.")
    if lineup.status(payload) != "applied":
        missing.append("The quarterback room rules need the situational lineup roles.")
    if stages & code.STAGE_SIGN:
        from . import nfl2k5_franchise_economy as economy, nfl2k5_franchise_ownership as ownership
        from . import nfl2k5_injured_reserve as ir, nfl2k5_practice_squad as squad
        if economy.status(payload) != "applied":
            missing.append("Emergency quarterback signings need the franchise economy.")
        if squad.status(payload) != "applied":
            missing.append("Emergency quarterback signings need the practice squad.")
        if ir.status(payload) != "applied":
            missing.append("Emergency quarterback signings need modern injured reserve.")
        if ownership.status(payload, ir.store_va(payload) or 0) != "applied":
            missing.append("Emergency quarterback signings need the franchise ownership safeguards.")
    return missing


def _patch(payload, edits):
    """Write authenticated (address, before, after) edits, reseal the allocator and every changed section."""
    image = XbeImage(payload)
    data = bytearray(payload)
    changed = set()
    for address, before, after in edits:
        _require(len(before) == len(after) and image.read(address, len(before)) == before,
                 f"Foreign or mixed quarterback room bytes at {address:#x}")
        at = image.offset(address, len(before))
        data[at:at + len(after)] = after
        changed.add(image.section(address).start)
    space._seal_scaleout(data, space._read_scale_directory(payload))
    for section in _sections(data):
        if section.virtual_address in changed:
            at = section.header_offset + 36
            data[at:at + 20] = section_digest(data, section)
    space._validate(data)
    return bytes(data)


def _edits(va, stages, page, *, restoring):
    """Every byte the owner writes: the sites the stage set needs and the whole page."""
    code = _code()
    empty = b"\xcc" * SIZE
    out = [(at, patched, original) if restoring else (at, original, patched)
           for _label, at, original, patched in code.sites(va, stages)]
    out.append((va, page, empty) if restoring else (va, empty, page))
    return out


def apply(payload, level="realistic"):
    """Install or restore on an existing standard executable without moving any installed owner."""
    _require(level in LEVELS, "Choose Retail or Realistic for the quarterback room rules")
    source = bytes(payload)
    XbeImage(source)
    try:
        current, settings, allocation = _state(source)
    except ERRORS as exc:
        raise QbRoomError(f"The quarterback room bytes are not recognized; refusing to change them ({exc})") from exc
    code = _code()
    receipt = {"owner": OWNER, "mode": level, "va": hex(VA)}
    if level == "retail":
        if current == "retail":
            return source, {**receipt, "status": "retail", "changed_bytes": 0, "file_growth": 0}
        page = code.page_bytes(VA, code.settings_record(settings["stages"], shadow=settings["shadow"],
                                                        h0_ppm=settings["h0_ppm"],
                                                        d2_scale_milli=settings["d2_scale_milli"]),
                               ir_store_va=_ir_store_va(source, settings["stages"]))
        result = _patch(source, _edits(VA, settings["stages"], page, restoring=True))
        _require(_state(result)[0] == "retail", "The quarterback room failed Retail readback")
        return result, {**receipt, "status": "retail", "restored_stages": settings["stages"],
                        "changed_bytes": space.count_differing_bytes(source, result), "file_growth": 0}
    missing = requirements(source)
    _require(not missing, " ".join(missing))
    record = code.settings_record(REALISTIC_STAGES, shadow=SHADOW_DEFAULT)
    wanted = code.parse_settings(record)
    if current == "applied" and settings == wanted:
        return source, {**receipt, "status": "already_applied", "stages": REALISTIC_STAGES,
                        "shadow": SHADOW_DEFAULT, "changed_bytes": 0, "file_growth": 0}
    working = source
    if current == "applied":
        # Another stage set or calibration record: back to the empty reservation first, then install.
        working, _ = apply(source, "retail")
    elif allocation is None:
        working, receipt["allocation"] = space.extend_scaleout(source, REQUESTS)
    empty = working
    page = code.page_bytes(VA, record, ir_store_va=_ir_store_va(working, REALISTIC_STAGES))
    result = _patch(working, _edits(VA, REALISTIC_STAGES, page, restoring=False))
    confirmed = _state(result)
    _require(confirmed[0] == "applied" and confirmed[1] == wanted, "The quarterback room failed Realistic readback")
    restored, _ = apply(result, "retail")
    _require(restored == empty, "The quarterback room Retail restore does not reproduce the empty reservation")
    return result, {**receipt, "status": "applied", "stages": REALISTIC_STAGES, "shadow": SHADOW_DEFAULT,
                    "sites": [hex(at) for _label, at, _o, _p in code.sites(VA, REALISTIC_STAGES)],
                    "changed_bytes": space.count_differing_bytes(source, result),
                    "file_growth": len(result) - len(source)}
