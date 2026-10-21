"""Play art routes at their real length (b776 pa2). PROVED OFFLINE (native draw lists), UNWITNESSED in game.

Why retail routes look short: before each assignment node is drawn, the play-art filter FUN_001812A0
rewrites a chain's LAST Route Segment (opcode 0x12, kinds 0-6: straight, 30/45/60 degree breaks,
lateral in/out, 45 degree outside) to exactly 304.8 cm (10 ft, 3.3 yd) whenever it is longer
(0x18162D-0x181686). Every go, drag, flat, out and post/corner break therefore ends in a short arrow,
while earlier segments are drawn at full length. The play-call panels (diagram camera FUN_00144360:
orthographic, +-1250 cm, centred 7 ft past the ball for every formation type that carries such
segments) show about 11.7 yd across either side and 14 yd downfield.

This owner replaces that one ``push 304.8`` (5 bytes at 0x181676) with a call into owned code that
draws the segment at its authored length, shortened only as far as needed to keep the line and
its arrowhead inside the panel: at most 9.5 yd either side of the ball and 12.2 yd downfield,
measured along the segment's own direction (the game's side test 0x17FF40 picks inside/outside
exactly as the draw handler 0x182110 does). A segment never gets shorter than retail, never
longer than authored, and keeps retail's 10 ft when its start is already outside the panel.
Only the node copy the art filter hands to the draw callback changes; the play data, the route
runner and every other node are untouched. The same filter serves the on-field (hold L1) art,
where the same bounds apply.

Allocation: one late xbe_space code owner (after every other owner, so no address moves).
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_play_art_routes"
SCHEMA = "2k5_mod_studio_play_art_routes/v1"
CODE_SIZE = 576
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK_VA = 0x181676
RETAIL_HOOK = bytes.fromhex("6866669843")  # push 304.8f, the retail final-segment cap
EXPERIMENTAL = True
RUNTIME_WITNESSED = False

# Panel bounds (cm, relative to the ball, offense direction positive), calibrated on the b775
# play-call frame: 0.192 px/cm across, 0.1149 px/cm deep at 1080p, panel edge +-1065 cm, top +1288 cm.
# The arrowhead extends 120 cm past a segment's end.
LATERAL_LIMIT = 868.68     # 9.5 yd: arrow tip <= 989 cm
DEPTH_LIMIT = 1112.52      # 12.17 yd: arrow tip <= 1233 cm
START_LATERAL = 1000.0     # a segment starting outside the panel keeps retail's 10 ft
START_DEPTH_MIN = -800.0
RETAIL_CAP = 304.8
FOOT = 30.48
SHADOW = 30.0              # the drop-shadow pass draws 30 cm down-left; it gets the same length

# Unit direction of each kind as (toward the middle, downfield), the geometry of 0x182110.
DIRECTIONS = ((0.0, 1.0), (0.5, 0.8660254), (0.70710677, 0.70710677), (0.8660254, 0.5),
              (1.0, 0.0), (-1.0, 0.0), (-0.70710677, 0.70710677))

# Position-independent: native calls go through EAX, data is addressed from the call/pop base, and
# the result replaces the return address so the hook acts as the 5-byte push it replaces.
#   push ecx/edx/esi; save xmm0-3; call/pop esi; result = 304.8
#   kind = node+4 & 15 (<= 6 else retail); dist = 0x2B6FA0(node, 2); right = 0x17FF40()
#   (lat_c, dep_c) = DIRECTIONS[kind], lat_c negated on the right; sign = byte [0xBDFBE0]
#   dep = sign*(pen.z - [0xBDFBF8]), lat = sign*(pen.x - [0xBDFBF0]), +30 each in the shadow pass ([0xBDFC18])
#   start outside [-1000,1000] x [-800, DEPTH_LIMIT] -> retail
#   t = min(dist, (+-LATERAL_LIMIT - lat)/lat_c, (DEPTH_LIMIT - dep)/dep_c); t = max(floor_ft(t), 304.8)
#   restore; xchg eax,[esp]; jmp eax
CODE = bytes.fromhex(
    "51525683ec500f1104240f114c24100f115424200f115c2430e8000000005ec744244066669843"
    "8b470483e00f83f8060f8762010000894424446a00ba0200000089f9b8a06f2b00ffd0d95c2448"
    "6a00b840ff1700ffd08b5424448d94d6a2010000f30f100af30f10520485c0740bf30f109eda01"
    "00000f57cb0fbe05e0fbbd00f30f2ad88b4d0cf30f104108f30f5c05f8fbbd00f30f59c3f30f11"
    "44244cf30f1001f30f5c05f0fbbd00f30f59c3833d18fcbd0000741cf30f5886de010000f30f10"
    "5c244cf30f589ede010000f30f115c244c0f2f86fe0100000f87b70000000f2f86020200000f82"
    "aa000000f30f105c244c0f2f9eea0100000f87970000000f2f9e060200000f828a0000000f57db"
    "0f2fcb7428720af30f109ee2010000eb08f30f109ee6010000f30f5cd8f30f5ed9f30f5d5c2448"
    "f30f115c24480f57db0f2fd3761ef30f109eea010000f30f5c5c244cf30f5edaf30f5d5c2448f3"
    "0f115c2448f30f105c2448f30f599eee010000f30f589ef2010000f30f2cc3f30f2ad8f30f599e"
    "f6010000f30f5f9efa010000f30f115c24400f1004240f104c24100f105424200f105c24308b44"
    "244083c4505e5a59870424ffe0")
DATA_OFFSET = 0x1C0        # base (the pop) is at +0x1E; the code addresses the table at base+0x1A2


def _f(*values):
    return struct.pack(f"<{len(values)}f", *values)


def code_bytes() -> bytes:
    table = b"".join(_f(*row) for row in DIRECTIONS)
    data = (table + struct.pack("<I", 0x80000000)
            + _f(SHADOW, LATERAL_LIMIT, -LATERAL_LIMIT, DEPTH_LIMIT, 1.0 / FOOT, 0.01, FOOT, RETAIL_CAP,
                 START_LATERAL, -START_LATERAL, START_DEPTH_MIN))
    out = CODE.ljust(DATA_OFFSET, b"\xcc") + data
    if len(out) > CODE_SIZE:
        raise ValueError("play art code exceeds its allocation")
    return out.ljust(CODE_SIZE, b"\xcc")


# Retail dependencies (sha256), unchanged by every other owner (data/nfl2k5_cave_reservations.json):
GUARDS = (
    (0x1812A0, 982, "db8b7f839029b734f82fcc8c21bb4a7d701bc0a3897b56eb82dd122642dabce6", "art filter before the hook"),
    (0x18167B, 709, "7ac23d3b05c956e19d044321d0e6d461056f6ce4e160ced5b50158dbea9470ad", "art filter after the hook"),
    (0x181940, 312, "90e97c5f411ad3de011038e81f24d819c11515ae212ab3344956a9780a3402c7", "chain drawer"),
    (0x182110, 872, "54b130152ae0908cb1661464938e4fe0d0021be536e0f15212184931536f8914", "route segment draw callback"),
    (0x17FF40, 148, "27100dac6f274bc0331305bfb176c06f683254c1f2d3e3481361920459f8cee4", "route side test"),
    (0x2B6FA0, 51, "e408132e4be33b6c8bfad3eb882a3233a33038ba41d366a2dc539968e339336a", "operand getter"),
    (0x2B6FE0, 63, "8ce5292597197ce9dc785cb8a21da513e48757f54d85ea822e9ce9be97e2d7e4", "operand setter"),
    (0x144360, 623, "71fded82f7757c5bc81768c8b30fbedb199fd4b3173e8b232d268d11bfddb1ef", "diagram camera window"),
    (0x164CB0, 288, "fe6f45a0ae1d50a5fc32e113251a62b05bb20e6a816445674ac6f4d1cafdbc13", "arrowhead"),
    (0x1A8CE0, 29, "7ad2df75b82f91b36bdee30de4f6736ab013db836e7be83deb705be0e791c524", "opcode entry lookup"),
    (0x509B70, 4, "eaef893b7b460835a9bc5c501e5b0927d3012188843ef065fa92ddc318f81e49", "304.8 constant"),
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _space():
    from . import nfl2k5_xbe_space as space
    return space


def hook_bytes(code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - (HOOK_VA + 5))


def sites(code_va: int):
    return (("play art final route segment", HOOK_VA, RETAIL_HOOK, hook_bytes(code_va)),)


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE,
            "foreign play art allocation")
    return rows[0]


def _state(payload: bytes):
    image = XbeImage(payload)
    for va, size, digest, label in GUARDS:
        require(hashlib.sha256(image.read(va, size)).hexdigest() == digest, f"foreign {label} at {va:#x}")
    space = _space()
    require(space.status(payload) != "foreign", "foreign executable geometry or digest")
    row = allocation(payload)
    hook = image.read(HOOK_VA, 5)
    if row is None:
        require(hook == RETAIL_HOOK, "play art hook without its allocation")
        return "retail", None
    code = image.read(row["va"], CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        require(hook == RETAIL_HOOK, "play art hook without its code")
        return "retail", row
    require(code == code_bytes(), "foreign play art code")
    require(hook == hook_bytes(row["va"]), "play art code without its hook")
    return "applied", row


def status(payload: bytes) -> str:
    try:
        return _state(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the late owner and its hook. Idempotent; refuses foreign bytes."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    state, found = _state(payload)
    common = {"owner": OWNER, "experimental": EXPERIMENTAL, "runtime_witnessed": RUNTIME_WITNESSED,
              "owner_bytes": CODE_SIZE, "hook_va": hex(HOOK_VA)}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "code_va": hex(found["va"])}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    require(found is not None, "reserve the play art allocation first")
    installed, code_receipt = space.install_code(payload, OWNER, code_bytes())
    result, site_receipt = rdata.apply(installed, sites(found["va"]), OWNER)
    require(status(result) == "applied", "play art postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(found["va"]), "changed_bytes": changed,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def reservations(payload: bytes) -> list[dict]:
    """The live span this owner writes (for overlap checks)."""
    return [dict(owner=OWNER, start=hex(HOOK_VA), end=hex(HOOK_VA + 5), size=5,
                 basis="pinned live push 304.8 in the play-art filter; not a cave")]


__all__ = ["OWNER", "REQUESTS", "HOOK_VA", "RETAIL_HOOK", "CODE_SIZE", "LATERAL_LIMIT", "DEPTH_LIMIT",
           "code_bytes", "sites", "allocation", "status", "apply", "reservations"]
