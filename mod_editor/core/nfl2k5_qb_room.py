"""Reversible quarterback room owner for the standard 128 MiB franchise (beta 81 pieces 3 and 4, owner nfl2k5_qb_room).

Three fixed pages at 0x1529000 (nfl2k5_xbe_space.QB_ROOM_*) hold the native code, the QBROOMv1 settings record, the
counters and the event ring; whole 5-byte calls of the weekly advance enter them (nfl2k5_qb_room_code.HOOKS). The
installer authenticates every hook site and the whole page against the exact bytes it expects and refuses anything
else. Retail restores the sites and fills the pages with 0xCC; the reservation stays, so Realistic then Retail is the
source plus an empty reservation, byte for byte. A page an earlier revision's Studio wrote (the frozen templates
nfl2k5_qb_room_code_b81_*) reads "previous": Realistic upgrades it in place to the current template and Retail
restores it. The byte interface is .b77-scratch/b81/qb34/INTERFACE.md.

Stage bit 16 (4b trades, DESIGN_CHANGES C20) brings a second owner with it: nfl2k5_qb_trades, one fixed page at 0x152C000
and the site 0x247E1E. This owner installs and restores it together with the room (never one without the other: the
room's state authenticates it, Retail restores the trades site and page first, then the room). The Studio's Realistic set
includes bit 16 wherever 4b's five needs are installed (the trades review's F1, coordinator 11/21: the deadline owner,
the economy, the practice squad, modern IR and the ownership page; studio_stages(..., trades=True)), so Realistic is 383
there and 367 elsewhere, with one plain note (TRADES_LEFT_OUT) instead of a refused build. A current room page whose
trades page is an earlier revision's (nfl2k5_qb_trades.previous_revisions: the 383 page of ff6ae30b2, whose cap test
charged the buyer the base salary before the trade) reads "previous" too: Realistic upgrades the trades page in place
(same address; the room page and its sites are written back byte for byte) and Retail restores both.
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
# Piece 3's stage bits for the Studio move here one stage at a time, after each stage's tests and panel (BUILD_ORDERS
# order 3). The floor handover shipped the floor alone (FLOOR_STUDIO_STAGES below, from the injury level). D1 + D2
# handover (lead, after the designer's addendum 2): D1 (veteran or rookie at the opening) and D2 (the kid's turn, by
# record). D3 (bit 256, benched for poor play) and D4 (bit 4) stay off until their own handovers.
REALISTIC_STAGES = 1 | 2 | 4 | 8 | 32 | 256  # D1 | D2 | D4 | E1 (4a) | E2 | D3 (E1/E2 hand-over; 1 | 2 | 4 | 256 at D3/D4,
#   1 | 2 at the floor hand-over)
SHADOW_DEFAULT = False
ERRORS = (ValueError, TypeError, IndexError, KeyError, OverflowError, struct.error)
# The floor (DESIGN addendum F1 to F8): stage bit 64, Realistic only, installed from the injury level (C7 below) and
# never on a cut list. Its site is the signing call at 0x248010 (installed for bit 8 or 64). It signs only through the
# gated native signing routine and never over the cap (floor review F1(b), route A at 644c5e30b): the over-cap rung,
# its ungated entry into 0x322BB6 and stage bit 128 are retired, so the owner no longer authenticates that routine.
# It still calls the economy's restructure and smart cut, which are authenticated (floor_economy_problem).
STAGE_FLOOR = 64
STAGE_OVER_CAP = 128  # retired (floor review F1(b)): new installs refuse it; only earlier revisions' pages carry it
SIGN_SITE = 0x248010  # the weekly advance's stage-6 signing call the floor and stage 4a replace
SMART_CUT = 0x2BF9A0  # the native cut-down the floor's release rung calls; the economy points it at economy_smart_cut
# Coordinator's product rule (2026-11-20): quarterback injuries above zero are never installed without the floor. The
# Studio's stage set is therefore a function of the plan: these bits whenever injuries are above zero (Realistic, or
# Custom above 0 percent), plus piece 3's bits from REALISTIC_STAGES where rule C1a allows them.
FLOOR_STUDIO_STAGES = STAGE_FLOOR  # 64 only since the floor review (F1(b)); earlier Studios wrote 64 | 128
PIECE3_BITS = 1 | 2 | 4 | 256  # STAGE_D1 | STAGE_D2 | STAGE_D4 | STAGE_D3
# E1 (8) and E2 (32): they need the floor's needs (economy, practice squad, modern IR, ownership) and were judged with
# piece 3 on (P5 at 335/367, C21), so the Studio installs them only where both the floor and piece 3 are installed.
E_BITS = 8 | 32  # STAGE_SIGN | STAGE_E2
# 4b trades (bit 16; C20, C22): the Studio adds it where E1/E2 are installed and 4b's own needs are installed
# (trade_needs_met); otherwise it is left out with one plain note, never a refused build (the trades review's F1).
STUDIO_TRADE_BITS = 16
TRADES_LEFT_OUT = ("Computer clubs trading for a quarterback need the 2026 franchise season (its NFL week 9 trade deadline), "
                   "the franchise economy, reserve save compatibility and modern injured reserve, so trades were not "
                   "added.")
STAGE_NAMES = ((1, "D1 veteran or rookie"), (2, "D2 the kid's turn"), (256, "D3 benched for poor play"),
               (4, "D4 returning starter"),
               (8, "E1 emergency backup signing"), (16, "trades (4b)"), (32, "E2 better quarterback while the starter is out"),
               (STAGE_FLOOR, "floor"), (STAGE_OVER_CAP, "over-cap signing (retired)"))


def stage_names(stages):
    """The installed stage set by name, for receipts and reviewers."""
    return [name for bit, name in STAGE_NAMES if stages & bit]


def studio_stages(injuries_above_zero, piece3, trades=False):
    """The stage set the Studio installs: the floor whenever injuries are above zero, piece 3 where C1a allows it, E1/E2
    where both are installed, and 4b trades (bit 16) where those are and 4b's own needs are installed too
    (``trades``: trade_needs_met)."""
    return ((FLOOR_STUDIO_STAGES if injuries_above_zero else 0) | ((REALISTIC_STAGES & PIECE3_BITS) if piece3 else 0)
            | ((REALISTIC_STAGES & E_BITS) if injuries_above_zero and piece3 else 0)
            | (STUDIO_TRADE_BITS if injuries_above_zero and piece3 and trades else 0))


def trade_needs_met(payload):
    """4b's five needs are installed on this executable (requirements(payload, 16) is empty)."""
    return not requirements(payload, STUDIO_TRADE_BITS)


def realistic_stages(payload=None):
    """apply(payload, "realistic") with no stage set: what the Studio installs for Realistic injuries with piece 3:
    383 on an executable that carries 4b's needs, else 367 (and 367 when no executable is named)."""
    return studio_stages(True, True, payload is not None and trade_needs_met(payload))


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


STAGE_TRADE = 16


def _trades():
    from . import nfl2k5_qb_trades as trades
    return trades


def _trades_link(payload):
    """The trades page's link word: the modern IR owner's store (E2's lost starter), 0 without one."""
    from . import nfl2k5_injured_reserve as ir
    return ir.store_va(payload) or 0


def _trades_check(payload, stages):
    """With bit 16 the trades page must be the current template or an earlier revision's ("previous"), linked to this
    executable's IR store; without it, retail. Returns the trades page's revision (name, frozen template) when it is
    an earlier one, else None."""
    status, link, _shadow = _trades().state(payload)
    if stages & STAGE_TRADE:
        _require(status in ("applied", "previous") and link == _trades_link(payload),
                 "The quarterback trades page is not as installed")
        return _trades().revision(payload) if status == "previous" else None
    _require(status == "retail", "Quarterback trades bytes without the room's trade stage")
    return None


def _ir_store_va(payload, stages):
    """The link word at +0x2020: the modern IR owner's store, which only E2 (stage bit 32) reads; 0 otherwise.
    0 with E2 means E2 never fires (the page counts sign_ir_unlinked)."""
    if not stages & _code().STAGE_E2:
        return 0
    from . import nfl2k5_injured_reserve as ir
    return ir.store_va(payload) or 0


def _site_stages(stages):
    """The stage set the hook table is asked for: the 0x248010 call serves both stage 4a and the floor."""
    return stages | _code().STAGE_SIGN if stages & STAGE_FLOOR else stages


def _sites(va, stages, code=None):
    return (code or _code()).sites(va, _site_stages(stages))


def _previous_revisions():
    """(name, frozen page template, the stage sets that revision's Studio wrote) for each earlier template whose pages a
    disc may hold ([validator]'s finding at c8683ea7e): the floor + D1 + D2 hand-over's (c7067bacabf4, pinned at
    b2672e398, the P5 and P6-5ff candidates' page; C21 replaced its E1/E2 smart cut; its Studio wrote 67, 64 where piece
    3's needs were missing, 3 for Custom 0, and the D3/D4 hand-over's Studio at 9c7f38657 wrote the same page at 327
    and 263 for Custom 0: the E1/E2 review's F1), the floor review's (420fbe089764, pinned at 66d8a7e1b; 67, 64, 3), the
    D1 + D2 handover's (65259084fc89, pinned at 692062151; 195, 192, 3), the floor handover's (752571283e98, pinned at
    c16934bee and f34553b06; 192) and the reviewed stage 0 + 3a page's (b1372b645e46 at 78d3633d3; 1)."""
    from . import nfl2k5_qb_room_code_b81_3a as stage_3a, nfl2k5_qb_room_code_b81_d1d2 as d1d2
    from . import nfl2k5_qb_room_code_b81_floor as floor, nfl2k5_qb_room_code_b81_floor_review as floor_review
    from . import nfl2k5_qb_room_code_b81_handover as handover
    return (("b81 floor + D1 + D2 hand-over", handover, (67, 64, 3, 327, 263)),
            ("b81 floor review", floor_review, (67, 64, 3)),
            ("b81 D1 + D2 handover", d1d2, (195, 192, 3)), ("b81 floor handover", floor, (192,)),
            ("b81 stage 3a", stage_3a, (1,)))


def sign_calls():
    """Every call at 0x248010 that is this owner's own: the current page's sign_entry and each earlier revision's where
    its Studio wrote one. nfl2k5_star_retention accepts exactly these in the caller window it authenticates."""
    calls = {patched for _label, at, _o, patched in _sites(VA, _code().STAGE_SIGN) if at == SIGN_SITE}
    for _name, module, stage_sets in _previous_revisions():
        for stages in stage_sets:
            calls |= {patched for _label, at, _o, patched in _sites(VA, stages, module) if at == SIGN_SITE}
    return calls


def floor_economy_problem(payload):
    """None when the economy routines the floor calls are the economy's own (F3 steps 6 and 7): economy_restructure at
    0x3B9F60 and the native cut-down 0x2BF9A0 sending its call to economy_smart_cut; else a plain reason."""
    from .nfl2k5_franchise_economy_code import SYMBOLS, WINDOWS
    image = XbeImage(payload)
    restructure, smart = SYMBOLS["economy_restructure"], SYMBOLS["economy_smart_cut"]
    if image.read(restructure, len(WINDOWS[restructure])) != WINDOWS[restructure]:
        return "The quarterback floor found unrecognized code in the economy's restructure (0x3B9F60)."
    cut = b"\xe9" + struct.pack("<i", smart - (SMART_CUT + 5))
    if image.read(SMART_CUT, len(cut)) != cut or image.read(smart, len(WINDOWS[smart])) != WINDOWS[smart]:
        return "The quarterback floor found unrecognized code in the economy's smart cut (0x2BF9A0)."
    return None


def _floor_problems(payload, stages):
    if not stages & STAGE_FLOOR:
        return []
    problem = floor_economy_problem(payload)
    return [problem] if problem else []


def _sites_state(image, va, stages, code=None):
    """'retail' when every hook site holds its retail call, 'applied' when exactly the stage set's sites hold the
    calls into the page at ``va`` (written by ``code``, the current template by default) and the rest hold retail
    calls; anything else is foreign."""
    code = code or _code()
    wanted = {at: patched for _label, at, _original, patched in _sites(va, stages, code)} if va else {}
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
    """(status, settings, allocation, revision) after authenticating every site and the whole page; raises when
    foreign. "previous" means the page and its sites, or (with bit 16) the trades page, are exactly what an earlier
    revision's Studio wrote; revision is then (name, the room's template, the trades page's frozen template or None),
    else None."""
    image = XbeImage(payload)
    allocation = _allocation(payload)
    if allocation is None:
        _sites_state(image, 0, 0)
        _trades_check(payload, 0)
        return "retail", None, None, None
    page = image.read(VA, SIZE)
    if page == b"\xcc" * SIZE:
        _sites_state(image, 0, 0)
        _trades_check(payload, 0)
        return "retail", None, allocation, None
    try:
        settings = _page_settings(payload, image, page, _code())
        trades = _trades_check(payload, settings["stages"])
        if trades is not None:
            # The current room page with an earlier revision's trades page (N6: the 383 page of ff6ae30b2).
            return "previous", settings, allocation, (trades[0], _code(), trades[1])
        return "applied", settings, allocation, None
    except ERRORS as exc:
        current_error = exc
    for name, module, stage_sets in _previous_revisions():
        try:
            settings = _page_settings(payload, image, page, module)
        except ERRORS:
            continue
        written = module.parse_settings(module.settings_record(settings["stages"]))  # that Studio's own record
        if settings["stages"] in stage_sets and settings == written:
            _trades_check(payload, 0)
            return "previous", settings, allocation, (name, module, None)
    raise current_error


def _page_settings(payload, image, page, code):
    """The settings of a page written with template ``code``, after authenticating the whole page and its sites."""
    record = page[code.SETTINGS_OFFSET:code.SETTINGS_OFFSET + code.SETTINGS.size]
    settings = code.parse_settings(record)
    link = struct.unpack_from("<I", page, code.LINK_IR_STORE)[0]
    _require(link == _ir_store_va(payload, settings["stages"]), "Foreign quarterback room link words")
    _require(not _floor_problems(payload, settings["stages"]),
             "The quarterback floor's native signing routine or economy routines are not recognized")
    _require(page == code.page_bytes(VA, record, ir_store_va=link), "Foreign quarterback room page")
    states = _sites_state(image, VA, settings["stages"], code)
    _require(states == {"applied"} or (states == {"applied", "retail"}), "Foreign or mixed quarterback room sites")
    current = _code()
    if code is not current:
        # An earlier revision never wrote the sites the current template added (0x248687, the stage advance's end, since
        # the floor review's step 2): on its page they must still hold their retail calls.
        known = {at for at, *_rest in code.HOOKS}
        for at, original, _label, _need in current.HOOKS:
            if at not in known:
                _require(image.read(at, len(original)) == original, f"Foreign or mixed quarterback room bytes at {at:#x}")
    return settings


def read_settings(payload):
    try:
        status, settings, allocation, revision = _state(bytes(payload))
    except ERRORS as exc:
        return {"status": "foreign", "reason": str(exc)}
    if status == "retail":
        return {"status": "retail", "mode": "retail", "reserved": allocation is not None,
                "va": VA if allocation else None}
    out = {"status": status, "mode": "realistic", "stages": settings["stages"],
           "stage_names": stage_names(settings["stages"]), "shadow": settings["shadow"],
           "h0_ppm": settings["h0_ppm"], "d2_scale_milli": settings["d2_scale_milli"], "va": VA, "reserved": True,
           "trades": "applied" if settings["stages"] & STAGE_TRADE else "retail"}
    if settings["stages"] & STAGE_TRADE:
        out["trades_shadow"] = _trades().state(bytes(payload))[2]
    if revision is not None:
        # An earlier revision's page; Realistic upgrades it in place, Retail restores it. Its stage names are read
        # with the current meaning of the bits, which matches for the sets those Studios wrote (192 and 1).
        out["revision"] = revision[0]
        if revision[2] is not None:
            out["trades"] = "previous"                  # the room page is current; the trades page is the earlier one
    return out


def status(payload):
    return read_settings(payload)["status"]


def _check_stage_set(stages):
    code = _code()
    _require(not stages & code.STAGE_E2 or stages & code.STAGE_SIGN, "The quarterback room E2 stage needs stage 4a")
    _require(not stages & STAGE_OVER_CAP,
             "Signing over the cap is retired: the quarterback floor never goes over the cap")


def requirements(payload, stages=None):
    """Plain reasons this executable cannot take Realistic (empty when it can): 128 MiB standard, depth locks and
    lineup roles applied; for the signing stage (4a) and the floor (64) also the economy, the practice squad, modern IR
    and the ownership page, and for the floor the economy's own restructure and smart cut. A stage whose needs are
    missing is an error, never a silent skip."""
    from . import nfl2k5_depth_locks as locks, nfl2k5_k128 as memory, nfl2k5_lineup_roles as lineup
    code = _code()
    stages = realistic_stages() if stages is None else stages
    _check_stage_set(stages)
    missing = []
    try:
        standard = bool(memory.read_settings(payload).get("require_128"))
    except ERRORS:
        standard = False
    if not standard:
        missing.append("The quarterback room rules need a 128 MB standard executable (the 128 MB start-up check).")
    if stages & PIECE3_BITS and locks.status(payload) != "applied":
        missing.append("The quarterback room rules need depth chart locks.")
    if stages & PIECE3_BITS and lineup.status(payload) != "applied":
        missing.append("The quarterback room rules need the situational lineup roles.")
    missing += _floor_problems(payload, stages)
    if stages & (code.STAGE_SIGN | STAGE_FLOOR):
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
    if stages & STAGE_TRADE:
        # 4b (C20): the native trade pass it wraps must be the deadline owner's, the executor must run the ownership
        # guard and the practice-squad room test, the price is the economy's, and the lost-starter test reads modern IR.
        from . import nfl2k5_franchise_economy as economy, nfl2k5_franchise_ownership as ownership
        from . import nfl2k5_injured_reserve as ir, nfl2k5_practice_squad as squad, nfl2k5_trade_deadline as deadline
        for ok, what in ((deadline.status(payload) == "applied", "the NFL week 9 trade deadline"),
                         (economy.status(payload) == "applied", "the franchise economy"),
                         (squad.status(payload) == "applied", "the practice squad"),
                         (ir.status(payload) == "applied", "modern injured reserve"),
                         (ownership.status(payload, ir.store_va(payload) or 0) == "applied",
                          "the franchise ownership safeguards")):
            if not ok:
                missing.append(f"Quarterback trades need {what}.")
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


def _edits(va, stages, page, *, restoring, code=None, trades_link=0, trades_shadow=False, trades_code=None):
    """Every byte the owner writes: the sites the stage set needs and the whole page (template ``code``); with bit 16
    the trades site and page first (C20: restored before the room), written with ``trades_code`` (the current trades
    template by default; an earlier revision's to restore its page)."""
    empty = b"\xcc" * SIZE
    out = (_trades().edits(trades_link, restoring=restoring, shadow=trades_shadow, code=trades_code)
           if stages & STAGE_TRADE else [])
    out += [(at, patched, original) if restoring else (at, original, patched)
            for _label, at, original, patched in _sites(va, stages, code)]
    out.append((va, page, empty) if restoring else (va, empty, page))
    return out


def apply(payload, level="realistic", *, stages=None):
    """Install or restore on an existing standard executable without moving any installed owner. ``stages`` is the
    Studio's set for Realistic (studio_stages); None means realistic_stages()."""
    _require(level in LEVELS, "Choose Retail or Realistic for the quarterback room rules")
    source = bytes(payload)
    XbeImage(source)
    try:
        current, settings, allocation, revision = _state(source)
    except ERRORS as exc:
        raise QbRoomError(f"The quarterback room bytes are not recognized; refusing to change them ({exc})") from exc
    receipt = {"owner": OWNER, "mode": level, "va": hex(VA)}
    if level == "retail":
        if current == "retail":
            return source, {**receipt, "status": "retail", "changed_bytes": 0, "file_growth": 0}
        code = revision[1] if revision is not None else _code()
        page = code.page_bytes(VA, code.settings_record(settings["stages"], shadow=settings["shadow"],
                                                        h0_ppm=settings["h0_ppm"],
                                                        d2_scale_milli=settings["d2_scale_milli"]),
                               ir_store_va=_ir_store_va(source, settings["stages"]))
        trades_shadow = bool(_trades().state(source)[2]) if settings["stages"] & STAGE_TRADE else False
        result = _patch(source, _edits(VA, settings["stages"], page, restoring=True, code=code,
                                       trades_link=_trades_link(source), trades_shadow=trades_shadow,
                                       trades_code=revision[2] if revision is not None else None))
        _require(_state(result)[0] == "retail", "The quarterback room failed Retail readback")
        return result, {**receipt, "status": "retail", "restored_stages": settings["stages"],
                        **({"restored_revision": revision[0]} if revision is not None else {}),
                        "changed_bytes": space.count_differing_bytes(source, result), "file_growth": 0}
    stages = realistic_stages(source) if stages is None else stages
    _require(type(stages) is int and stages > 0, "Realistic needs at least one quarterback room stage")
    return _install(source, current, settings, allocation, receipt, stages, SHADOW_DEFAULT, revision)


def install_stages(payload, stages, *, shadow=False, test_without_needs=False, trades_shadow=False):
    """Calibration and test path only (season panels, owner tests): install a named stage set with the same
    authentication, needs and readback as Realistic. Nothing in the Studio calls it; the Studio writes only
    studio_stages() sets through apply() (a test pins both). ``test_without_needs`` skips only the dependency checks (the
    128 MB standard, locks, roles, economy, practice squad, modern IR, ownership), never the byte authentication of
    the routines the floor enters: it exists to replay recorded seasons on executables made before those owners.
    ``trades_shadow`` (bit 16 only) puts 4b alone in shadow through the trades page's flag word, while the room's other
    stages act: the 4b shadow panel."""
    source = bytes(payload)
    XbeImage(source)
    try:
        current, settings, allocation, revision = _state(source)
    except ERRORS as exc:
        raise QbRoomError(f"The quarterback room bytes are not recognized; refusing to change them ({exc})") from exc
    _require(type(test_without_needs) is bool, "test_without_needs must be True or False")
    _require(type(trades_shadow) is bool and (not trades_shadow or stages & STAGE_TRADE),
             "The trades shadow flag needs stage bit 16")
    receipt = {"owner": OWNER, "mode": "stages", "va": hex(VA)}
    if test_without_needs:
        receipt["test_without_needs"] = True
    return _install(source, current, settings, allocation, receipt, stages, shadow, revision,
                    needs=not test_without_needs, trades_shadow=trades_shadow)


def _install(source, current, settings, allocation, receipt, stages, shadow, revision=None, *, needs=True,
             trades_shadow=False):
    code = _code()
    if needs:
        missing = requirements(source, stages)
    else:
        _check_stage_set(stages)
        missing = _floor_problems(source, stages)
    _require(not missing, " ".join(missing))
    record = code.settings_record(stages, shadow=shadow)
    wanted = code.parse_settings(record)
    if current == "applied" and settings == wanted and (
            not stages & STAGE_TRADE or _trades().state(source)[2] == trades_shadow):
        return source, {**receipt, "status": "already_applied", "stages": stages,
                        "shadow": shadow, "changed_bytes": 0, "file_growth": 0}
    working = source
    if current in ("applied", "previous"):
        # Another stage set, calibration record or earlier revision's page: back to the empty reservation first (same
        # page address, every other row untouched), then install.
        working, _ = apply(source, "retail")
        if revision is not None:
            receipt["upgraded_from"] = revision[0]
    elif allocation is None:
        working, receipt["allocation"] = space.extend_scaleout(source, REQUESTS)
    if stages & STAGE_TRADE and _trades().allocation(working) is None:
        working, receipt["trades_allocation"] = space.extend_scaleout(working, _trades().REQUESTS)
    empty = working
    page = code.page_bytes(VA, record, ir_store_va=_ir_store_va(working, stages))
    result = _patch(working, _edits(VA, stages, page, restoring=False, trades_link=_trades_link(working),
                                    trades_shadow=trades_shadow))
    confirmed = _state(result)
    _require(confirmed[0] == "applied" and confirmed[1] == wanted, "The quarterback room failed Realistic readback")
    restored, _ = apply(result, "retail")
    _require(restored == empty, "The quarterback room Retail restore does not reproduce the empty reservation")
    return result, {**receipt, "status": "applied", "stages": stages, "stage_names": stage_names(stages), "shadow": shadow,
                    **({"trades_shadow": trades_shadow} if stages & STAGE_TRADE else {}),
                    "sites": [hex(at) for _label, at, _o, _p in _sites(VA, stages)]
                    + ([hex(_trades().edits(0, restoring=False)[0][0])] if stages & STAGE_TRADE else []),
                    "changed_bytes": space.count_differing_bytes(source, result),
                    "file_growth": len(result) - len(source)}
