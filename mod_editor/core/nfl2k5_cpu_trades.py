"""CPU trades at every position for the standard 128 MiB franchise (beta 81, owner nfl2k5_cpu_trades).

Computer clubs trade a player for a draft pick when one has a hole at a position and another has a spare man there:
in the preseason and in season up to the NFL deadline week, never with a club a person manages, never a QB (the
quarterback room's stage 4b does those), K or P. tools/cpu_trades/trades.c holds every rule; the design is the trades-all
lane's DESIGN.md with the coordinator's rulings R1 to R7.

Two fixed pages at 0x152E000 (nfl2k5_xbe_space.CPU_TRADES_*) hold the native code, the CPUTRDv1 settings record, the
counters and the event ring. Two whole 5-byte calls enter them: 0x2BC96C, the native trade pass's call of its pending
scan, and 0x2BB296, the trade story writer's value line (every trade of ours posts its inbox story). The owner
authenticates both sites and the whole pages and refuses anything else, and it installs only where nothing else is
allocated in its range. Retail restores the sites and
fills the pages with 0xCC; the reservation stays, so Realistic then Retail is the source plus an empty reservation, byte
for byte. Nothing is added to any save: a record of this owner exists only inside the game's own trade call.

States: "retail" (the site holds its retail call; the pages are empty or not reserved), "applied" (the site enters the
pages and they are exactly the template linked for this address with a valid settings record), else "foreign".
"""
from __future__ import annotations

import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = space.CPU_TRADES_OWNER
REQUESTS = (space.CPU_TRADES_REQUEST,)
VA = space.CPU_TRADES_VA
SIZE = space.CPU_TRADES_SIZE
LEVELS = ("retail", "realistic")
# What the Studio installs for Realistic: the regular season (bit 1), the preseason (bit 2) and losing clubs' veteran
# sales in season (bit 4, RULINGS R3), at the calibrated chances per buyer and tick (millionths; the trades-all lane's
# calibration panels set them, stage 8 halved and weighted by week inside the page).
REALISTIC_STAGES = 1 | 2 | 4
P8_PPM = 250_000
P7_PPM = 400_000
SHADOW_DEFAULT = False
ERRORS = (ValueError, TypeError, IndexError, KeyError, OverflowError, struct.error)
LEFT_OUT = ("Computer clubs trading players at every position need the 2026 franchise season (its NFL week 9 trade "
            "deadline), the franchise economy, reserve save compatibility and modern injured reserve, so they were not "
            "added.")
STAGE_NAMES = ((1, "regular season to the deadline"), (2, "preseason"), (4, "losing clubs sell veterans"))


def stage_names(stages):
    return [name for bit, name in STAGE_NAMES if stages & bit]


class CpuTradesError(ValueError):
    """The requested option or the executable's installed state could not be verified."""


def _require(condition, message):
    if not condition:
        raise CpuTradesError(message)


def _code():
    from . import nfl2k5_cpu_trades_code as code
    return code


def allocation(payload):
    """The pages' allocator row, or None when this executable has no reservation for them."""
    if not space.is_scaleout(payload):
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    _require(len(rows) == 1 and tuple(rows[0][k] for k in ("owner", "kind", "size", "align")) == REQUESTS[0]
             and rows[0]["va"] == VA and rows[0]["owner_offset"] == 0, "Unknown CPU trades allocation")
    section = XbeImage(payload).section(VA, SIZE)
    _require(section.writable and section.executable, "The CPU trades pages need a writable executable pool")
    return rows[0]


def state(payload):
    """(status, settings) after authenticating both sites and the whole pages: ("retail", None) or ("applied",
    settings); raises CpuTradesError when foreign (a site half installed, foreign bytes, or code in the pages while the
    sites are retail)."""
    image = XbeImage(payload)
    row = allocation(payload)
    sites = _code().sites(VA)
    found = [image.read(at, len(original)) for at, original, _patched in sites]
    raw = image.read(VA, SIZE) if row is not None else None
    if all(now == original for now, (_at, original, _p) in zip(found, sites)):
        _require(raw is None or raw == b"\xcc" * SIZE, "The CPU trades pages hold code but their sites are retail")
        return "retail", None
    for now, (at, _original, patched) in zip(found, sites):
        _require(now == patched and raw is not None, f"Foreign or half-installed CPU trades bytes at {at:#x}")
    code = _code()
    record = raw[code.SETTINGS_OFFSET:code.SETTINGS_OFFSET + code.SETTINGS.size]
    settings = code.parse_settings(record)
    _require(raw == code.page_bytes(VA, record), "Foreign CPU trades pages")
    return "applied", settings


def read_settings(payload):
    try:
        status, settings = state(bytes(payload))
    except ERRORS as exc:
        return {"status": "foreign", "reason": str(exc)}
    if status == "retail":
        reserved = allocation(bytes(payload)) is not None
        return {"status": "retail", "mode": "retail", "reserved": reserved, "va": VA if reserved else None}
    return {"status": "applied", "mode": "realistic", **settings, "stage_names": stage_names(settings["stages"]),
            "va": VA, "reserved": True}


def status(payload):
    return read_settings(payload)["status"]


def requirements(payload):
    """Plain reasons this executable cannot take Realistic (empty when it can): the 128 MB standard edition, the 2026
    season's week 9 deadline, the franchise economy (cap and pick values), the practice squad (the executor's room test),
    modern IR and the ownership safeguards (the executor's ownership guard), as for the quarterback trades of stage 4b."""
    from . import nfl2k5_franchise_economy as economy, nfl2k5_franchise_ownership as ownership
    from . import nfl2k5_injured_reserve as ir, nfl2k5_k128 as memory, nfl2k5_practice_squad as squad
    from . import nfl2k5_trade_deadline as deadline
    missing = []
    try:
        standard = bool(memory.read_settings(payload).get("require_128"))
    except ERRORS:
        standard = False
    if not standard:
        missing.append("Computer trades need a 128 MB standard executable (the 128 MB start-up check).")
    for ok, what in ((deadline.status(payload) == "applied", "the NFL week 9 trade deadline"),
                     (economy.status(payload) == "applied", "the franchise economy"),
                     (squad.status(payload) == "applied", "the practice squad"),
                     (ir.status(payload) == "applied", "modern injured reserve"),
                     (ownership.status(payload, ir.store_va(payload) or 0) == "applied",
                      "the franchise ownership safeguards")):
        if not ok:
            missing.append(f"Computer trades need {what}.")
    return missing


def needs_met(payload):
    return not requirements(payload)


def _patch(payload, edits):
    """Write authenticated (address, before, after) edits, reseal the allocator and every changed section."""
    image = XbeImage(payload)
    data = bytearray(payload)
    changed = set()
    for address, before, after in edits:
        _require(len(before) == len(after) and image.read(address, len(before)) == before,
                 f"Foreign or mixed CPU trades bytes at {address:#x}")
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


def edits(record, *, restoring):
    """(address, before, after) for both sites and the whole pages with this settings record."""
    empty, full = b"\xcc" * SIZE, _code().page_bytes(VA, record)
    out = []
    for at, original, patched in _code().sites(VA):
        out.append((at, patched, original) if restoring else (at, original, patched))
    out.append((VA, full, empty) if restoring else (VA, empty, full))
    return out


def unowned_problem(payload):
    """N7: None when nothing but this owner is allocated in its fixed range; else a plain reason."""
    if not space.is_scaleout(payload):
        return None
    for r in space.layout(payload)["allocations"]:
        if r["owner"] != OWNER and r["va"] < VA + SIZE and r["va"] + r["size"] > VA:
            return (f"Another owner ({r['owner']}) is allocated at {r['va']:#x}, inside the computer trades pages "
                    f"{VA:#x}..{VA + SIZE - 1:#x}; refusing to install over it.")
    return None


def apply(payload, level="realistic"):
    """Install (Realistic: REALISTIC_STAGES at the calibrated chances) or restore (Retail) on an existing standard
    executable without moving any installed owner."""
    _require(level in LEVELS, "Choose Retail or Realistic for computer trades")
    if level == "retail":
        return _retail(bytes(payload))
    return _install(bytes(payload), REALISTIC_STAGES, shadow=SHADOW_DEFAULT, p8_ppm=P8_PPM, p7_ppm=P7_PPM,
                    receipt={"owner": OWNER, "mode": level, "va": hex(VA)})


def install(payload, stages, *, shadow=False, p8_ppm=P8_PPM, p7_ppm=P7_PPM, test_without_needs=False):
    """Calibration and test path only (season panels, owner tests): a named stage set, chances and shadow flag, with the
    same authentication, needs and readback as Realistic. The Studio writes only apply(). ``test_without_needs`` skips
    the dependency checks only (never the byte authentication)."""
    _require(type(test_without_needs) is bool, "test_without_needs must be True or False")
    receipt = {"owner": OWNER, "mode": "stages", "va": hex(VA)}
    if test_without_needs:
        receipt["test_without_needs"] = True
    return _install(bytes(payload), stages, shadow=shadow, p8_ppm=p8_ppm, p7_ppm=p7_ppm, receipt=receipt,
                    needs=not test_without_needs)


def _retail(source):
    XbeImage(source)
    try:
        current, settings = state(source)
    except ERRORS as exc:
        raise CpuTradesError(f"The CPU trades bytes are not recognized; refusing to change them ({exc})") from exc
    receipt = {"owner": OWNER, "mode": "retail", "va": hex(VA)}
    if current == "retail":
        return source, {**receipt, "status": "retail", "changed_bytes": 0, "file_growth": 0}
    record = _code().settings_record(settings["stages"], shadow=settings["shadow"], p8_ppm=settings["p8_ppm"],
                                     p7_ppm=settings["p7_ppm"])
    result = _patch(source, edits(record, restoring=True))
    _require(state(result)[0] == "retail", "The CPU trades failed Retail readback")
    return result, {**receipt, "status": "retail", "restored": settings,
                    "changed_bytes": space.count_differing_bytes(source, result), "file_growth": 0}


def _install(source, stages, *, shadow, p8_ppm, p7_ppm, receipt, needs=True):
    XbeImage(source)
    try:
        current, settings = state(source)
    except ERRORS as exc:
        raise CpuTradesError(f"The CPU trades bytes are not recognized; refusing to change them ({exc})") from exc
    record = _code().settings_record(stages, shadow=shadow, p8_ppm=p8_ppm, p7_ppm=p7_ppm)
    wanted = _code().parse_settings(record)
    if needs:
        missing = requirements(source)
        _require(not missing, " ".join(missing))
    if current == "applied" and settings == wanted:
        return source, {**receipt, "status": "already_applied", **wanted, "changed_bytes": 0, "file_growth": 0}
    working = source
    if current == "applied":
        working, _ = _retail(source)          # another stage set or calibration record: back to the empty reservation
    elif allocation(working) is None:
        problem = unowned_problem(working)
        _require(problem is None, problem or "")
        working, receipt["allocation"] = space.extend_scaleout(working, REQUESTS)
    empty = working
    result = _patch(working, edits(record, restoring=False))
    confirmed = state(result)
    _require(confirmed == ("applied", wanted), "The CPU trades failed Realistic readback")
    restored, _ = _retail(result)
    _require(restored == empty, "The CPU trades Retail restore does not reproduce the empty reservation")
    return result, {**receipt, "status": "applied", **wanted, "stage_names": stage_names(stages),
                    "sites": [hex(at) for at, _o, _p in _code().sites(VA)],
                    "changed_bytes": space.count_differing_bytes(source, result),
                    "file_growth": len(result) - len(source)}
