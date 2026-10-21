"""CPU quarterback reads, USA retail. EXPERIMENTAL / UNWITNESSED.

Two independent options for the CPU passing AI (0x19BB60), both off by default:

* ``zone_windows`` ("CPU QB respects zone defenders"): one data table. The openness model
  0x199F40 subtracts curve 0x50C51C(ball time - defender arrival time), but a defender who
  reaches the catch point first can only remove 0.20 while a receiver with no man defender gets
  +0.45, so a zone defender standing in the window still scores 1.25, above every pass
  threshold (at most 1.20). The y values for a defender who arrives within 0.1 s of the ball or
  earlier become -0.50 (with the ball) and -0.80 (0.5 s early). Defenders 0.1 s or more late
  keep the retail values, so receivers with separation score exactly as in retail. The curve
  has exactly one reader (0x19A5DE).
* ``recheck`` ("CPU QB re-checks his read before throwing"): three hooks and an owned cave
  (see tools/nfl2k5_cpu_qb_reads.S). The native grid refreshes only the current read, yet the
  picker ranks every row with the score it had when it was last read. The cave stamps each
  grid point when it is scored, hides scores older than 1.5 x the QB's native read dwell
  (clamped 0.6..1.5 s) from the picker, keeps his read on the receiver he committed to, and
  drops that target (at most twice per play) when every point of it has been re-scored since
  the commit and none clears the pass threshold minus 0.05. Pocket pressure above 0.7, the
  native panic flag or a non-CPU passer keep the retail path.

Human passing, ball flight and the defense are not changed. Settings are build-time only; a
different selection needs a rebuild from a clean base.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_cpu_qb_reads"
CODE_SIZE, DATA_SIZE = 1280, 192
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
BUILD_CAPTION_ZONE = "CPU QB respects zone defenders (experimental)"
BUILD_CAPTION_RECHECK = "CPU QB re-checks his read before throwing (experimental)"
HELP_ZONE = ("EXPERIMENTAL / UNWITNESSED. Off in every preset. The CPU quarterback stops treating a receiver as "
             "open when a zone or man defender will reach the catch point with the ball or before it. Receivers "
             "with a step of separation (the defender 0.1 s or more late) keep their retail rating. Expect more "
             "check-downs, more holds and some extra sacks or scrambles against good coverage. Human play is "
             "unchanged.")
HELP_RECHECK = ("EXPERIMENTAL / UNWITNESSED. Off in every preset. The CPU quarterback only throws to receivers he "
                "looked at recently, keeps looking at the receiver he picked, and pulls the throw (at most twice a "
                "play) when that window has closed by the time he is ready to release. Under heavy pocket pressure "
                "he plays exactly as retail. Human play is unchanged.")

ZONE_CURVE_VA = 0x0050C51C
ZONE_X = (-0.5, -0.2, -0.1, 0.0, 0.5)
RETAIL_ZONE_Y = (0.05, 0.0, -0.05, -0.10, -0.20)
ZONE_Y = (0.05, 0.0, -0.05, -0.50, -0.80)


def _curve(xs, ys):
    return struct.pack("<I", len(xs)) + b"".join(struct.pack("<ff", x, y) for x, y in zip(xs, ys))


RETAIL_ZONE_CURVE = _curve(ZONE_X, RETAIL_ZONE_Y)
ZONE_CURVE = _curve(ZONE_X, ZONE_Y)
ZONE_SITE = ("covered_window_curve", ZONE_CURVE_VA, RETAIL_ZONE_CURVE, ZONE_CURVE)

# name, VA, retail bytes, opcode, assembly label. The pick and stamp hooks are native calls;
# hold is the native jne at 0x19BC72 (taken when committed and the release timer is <= 0.5 s).
HOOKS = (
    ("stamp", 0x0019B7D3, bytes.fromhex("e808f0ffff"), b"\xe8", "stamp"),
    ("pick", 0x0019BD8C, bytes.fromhex("e84fc8ffff"), b"\xe8", "pick"),
    ("hold", 0x0019BC72, bytes.fromhex("0f85a1020000"), b"\x0f\x85", "hold"),
)
SYMBOLS = dict(point_score=0x0019A7E0, picker=0x001985E0, rating=0x0017B010, lerp=0x001B0AE0,
               pick_path=0x0019BC78, release_path=0x0019BF19)
CPU_SCRAMBLES_HOOK = (0x0019C36C, bytes.fromhex("d80d6c694e00"))
# Everything read or entered, retail and b775-identical except the QB tick, whose verified
# cpu_scrambles hook and these hooks are normalized before hashing. 0x17B010 is a native
# call target that other owners wrap; it is entered only through its native ABI.
GUARDS = (
    (0x0019BB60, 2510, "fdc6a3131d3475c3583cbbc91857d24c02599ef3b29772f8b3e9dedd15cb7aef"),
    (0x0019B1F0, 1543, "63289048003aa5a627754b4f5a370411b86eb588821af21178d79445dd9597bc"),
    (0x00199100, 185, "607067b3fa227818ffc1b4499a806a48743377994ba9c44a430fa81e850dc928"),
    (0x00199F40, 2208, "1516a2172e86082261cb20e16facf979bc73e5739ea97e5f0f6e0a7c85ff9596"),
    (0x0019A7E0, 195, "c090d31a5529236597a83349d2b3955114af7099891e69a45eadc6aa66f07989"),
    # The picker, except the five bytes at 0x1987B5 that cpu_money_downs owns.
    (0x001985E0, 469, "7d5a3b519b1282f028bfe3286c5874ef74297e0ff13aeb0c281c7f3b4cb4854e"),
    (0x001987BB, 158, "50b879e224cd97bed381f45096b843923013dccb280a03caac640aa8c3b81c33"),
    (0x0050C394, 36, "5c6f816cb66fbed6cdeda03a3b1f01ddd8c4cbe3a12e9672b7f9c5601ee95cae"),
    (0x0050C548, 44, "159d3ae9567181ff1607e8406ac9f40c9163a7fe7755dcf9061d9c481f435d33"),
    (0x004EFE08, 4, "2f0d6f3d65a7e28c4223e4389106e46f1e9010a2bd724d35f9794cb8a86d7c68"),
    (0x004E6D5C, 4, "fb360f7241a770dc32cade9a1d1273c92b13bd4959b1c130931312b7fe95e63f"),
    (0x004E4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),
    (0x001B0AE0, 124, "85257e0d17fc30f87b44015e57a7951be3785ef634995aafaec65c9f5fc2bc7c"),
)
_ERRORS = (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError)


class CpuQbReadsError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise CpuQbReadsError(message)


def allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) == 2 and {(r["kind"], r["size"], r["align"]) for r in rows} ==
            {(k, n, a) for _, k, n, a in REQUESTS}, "Missing or foreign CPU QB reads allocation")
    return {r["kind"]: r for r in rows}


def code_for(code_va, data_va):
    from . import nfl2k5_cpu_qb_reads_code as assembly
    symbols = dict(SYMBOLS, code=code_va, state=data_va)
    out = bytearray(assembly.CODE)
    for off, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", out, off)[0]
        if kind == 2:
            target -= code_va + off
        struct.pack_into("<I", out, off, target & 0xFFFFFFFF)
    require(len(out) <= CODE_SIZE, "CPU QB reads code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def hook_sites(code_va=0):
    from . import nfl2k5_cpu_qb_reads_code as assembly
    result = []
    for name, va, before, opcode, label in HOOKS:
        after = opcode + struct.pack("<i", code_va + assembly.LABELS[label] - va - len(opcode) - 4)
        result.append((name, va, before, after.ljust(len(before), b"\x90")))
    return result


def _owned(payload):
    """(zone_windows, recheck, recheck_sites) from this owner's own bytes, without neighbors."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    curve = image.read(ZONE_CURVE_VA, len(RETAIL_ZONE_CURVE))
    require(curve in (RETAIL_ZONE_CURVE, ZONE_CURVE), "Foreign covered-window curve at 0x50C51C")
    zone = curve == ZONE_CURVE
    present = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    owned = allocations(payload) if present else None
    edits = hook_sites(owned["code"]["va"] if owned else 0)
    states = set()
    for _name, va, before, after in edits:
        raw = image.read(va, len(before))
        states.add("retail" if raw == before else "applied" if owned and raw == after else "foreign")
    if owned:
        c, d = owned["code"]["va"], owned["data"]["va"]
        require(image.read(d, DATA_SIZE) == bytes(DATA_SIZE), "Foreign initialized CPU QB reads state")
        raw = image.read(c, CODE_SIZE)
        states.add("retail" if raw == b"\xcc" * CODE_SIZE else "applied" if raw == code_for(c, d) else "foreign")
    require(states in ({"retail"}, {"applied"}), "Foreign or mixed CPU QB reads hooks/code")
    recheck = states == {"applied"}
    return zone, recheck, (edits if recheck else [])


def normalized_sites(payload):
    """For neighbor recognizers: this owner's verified hook sites, or [] when they are retail."""
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    if all(image.read(va, len(before)) == before for _, va, before, _, _ in HOOKS):
        return []
    _zone, recheck, edits = _owned(payload)
    require(recheck, "Foreign CPU QB reads neighbor")
    return edits


def _recognize(payload):
    from . import nfl2k5_cpu_scrambles as scrambles
    from .nfl2k5_cave_oracle import XbeImage
    zone, recheck, edits = _owned(payload)
    image = XbeImage(payload)
    neighbors = []
    va, before = CPU_SCRAMBLES_HOOK
    if image.read(va, len(before)) != before:
        require(scrambles.status(payload) == "applied", "Foreign CPU scramble neighbor in the QB tick")
        neighbors.append(("cpu_scrambles_threshold", va, before, None))
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _, at, before, _ in edits + neighbors:
            if va <= at and at + len(before) <= va + size:
                content[at - va:at - va + len(before)] = before
        require(hashlib.sha256(content).hexdigest() == digest, f"Foreign CPU QB reads prerequisite at {va:#x}")
    return zone, recheck


def read_settings(payload):
    try:
        zone, recheck = _recognize(payload)
    except _ERRORS:
        return {"status": "foreign"}
    return {"status": "applied" if zone or recheck else "retail", "zone_windows": zone, "recheck": recheck}


def status(payload):
    return read_settings(payload)["status"]


def component_status(payload, key):
    """'retail' | 'applied' | 'foreign' for one option ('zone_windows' or 'recheck')."""
    settings = read_settings(payload)
    if settings["status"] == "foreign":
        return "foreign"
    return "applied" if settings[key] else "retail"


def apply(payload, *, zone_windows=False, recheck=False):
    """Install the selected options, or replay an identical installation."""
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    require(type(zone_windows) is bool and type(recheck) is bool, "CPU QB reads options must be Off or On")
    require(zone_windows or recheck, "Select at least one CPU QB reads option")
    try:
        installed = _recognize(payload)
    except _ERRORS as exc:
        raise CpuQbReadsError(f"foreign/mixed CPU QB reads input: {exc}") from exc
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False,
                  zone_windows=zone_windows, recheck=recheck)
    if installed == (zone_windows, recheck):
        return payload, dict(common, status="already_applied", changed_bytes=0, edits=[])
    require(installed == (False, False), "Different CPU QB reads options are installed; rebuild from a clean base")
    before = payload
    allocation_receipt = {}
    edits = []
    if recheck:
        if not any(r["owner"] == OWNER for r in space.layout(payload)["allocations"]):
            if space.status(payload) == "retail":
                payload, allocation_receipt = space.apply(payload, REQUESTS, scaleout=True)
            else:
                require(space.is_scaleout(payload), "CPU QB reads needs the scale-out allocator")
                payload, allocation_receipt = space.extend_scaleout(payload, REQUESTS)
        owned = allocations(payload)
        c, d = owned["code"]["va"], owned["data"]["va"]
        payload, _ = space.install_code(payload, OWNER, code_for(c, d))
        edits += hook_sites(c)
    if zone_windows:
        edits.append(ZONE_SITE)
    image = XbeImage(payload)
    buf = bytearray(payload)
    for _, va, old, new in edits:
        off = image.offset(va, len(old))
        require(bytes(buf[off:off + len(old)]) == old, f"CPU QB reads site {va:#x} is not retail")
        buf[off:off + len(old)] = new
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(_recognize(result) == (zone_windows, recheck), "CPU QB reads postcondition failed")
    if recheck:
        require(space.status(result) == "applied", "CPU QB reads allocator postcondition failed")
    receipt = dict(common, status="applied",
                   before_sha256=hashlib.sha256(before).hexdigest(), after_sha256=hashlib.sha256(result).hexdigest(),
                   changed_bytes=space.count_differing_bytes(before, result), file_growth=len(result) - len(before),
                   allocation=allocation_receipt,
                   edits=[dict(label=name, va=hex(va), before=old.hex(), after=new.hex()) for name, va, old, new in edits])
    if recheck:
        receipt["reservations"] = [r for r in space.reservations(result) if r["owner"] == OWNER]
    return result, receipt


__all__ = ["OWNER", "REQUESTS", "HOOKS", "GUARDS", "ZONE_SITE", "ZONE_Y", "RETAIL_ZONE_Y", "apply", "status",
           "read_settings", "component_status", "normalized_sites", "allocations", "code_for", "hook_sites"]
