"""Formation art icon spacing (b777 tp1). PROVED OFFLINE (native draw path under Unicorn), UNWITNESSED in game.

Why icons overlap: the play-call diagrams draw each player's icon at his formation spot after the
diagram transform 0x180120, which on the formation select strip snaps every spot to a coarse grid
(|x| < 146 cm -> the middle column, 146..301 -> 106 cm, ...; depth 128..218 -> 201 cm, 218..480 -> 283 cm,
...). Players who stand close (a fullback and halfback a yard either side of the middle, a wing next
to the tight end, two backs stacked behind the QB) land on the same grid spot or less than one icon
apart, so one icon hides inside another.

This owner replaces the transform call at two diagram sites, the icon drawer (0x18108E in 0x181010)
and the slot route origin (0x1824EF in 0x182480), with owned code that, for an OFFENSE formation
diagram (record type < 4, no live player positions), reads all eleven slots through the game's own
getter 0x17FE60 and transform 0x180120, then spaces the icons: players are placed in order of
distance from the line; one on the line keeps his spot; any other whose icon (an ellipse 87 cm across,
193 cm deep, the strip's 40 px icon) overlaps one already placed first tries one sideways step that
clears it when the two really stand side by side (raw x 30 cm or more apart), kept only if it hits
nothing else, and otherwise moves straight away from the line until clear. x order is kept.
Only the drawn copy changes: the formation, the plays and the hold-L1 on-field art (live positions)
run the retail transform. Defense and special teams diagrams are unchanged.

Allocation: one late xbe_space code owner, the last one (nothing else moves). The build installs it
with the play art routes option (play_art_routes), after every other late owner.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Mapping

from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_formation_art_spacing"
SCHEMA = "2k5_mod_studio_formation_art_spacing/v1"
CODE_SIZE = 1024
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
EXPERIMENTAL = True
RUNTIME_WITNESSED = False
XFORM_VA = 0x180120
# (label, call site, retail bytes: call 0x180120)
HOOKS = (("formation icon drawer", 0x18108E, bytes.fromhex("e88df0ffff")),
         ("slot route origin", 0x1824EF, bytes.fromhex("e82cdcffff")))
# icon size in the strip's grid space (cm): 40 px at 0.46 px/cm across and 0.207 px/cm deep (720p frame)
ICON_ACROSS = 87.0
ICON_DEEP = 193.0
LINE_DEPTH = 60.0
SIDE_STEP_MIN = 30.0

# Position-independent (call/pop base; native calls through a pointer table). Assembled with GNU as from
# the algorithm in the module docstring.
CODE = bytes.fromhex(
    "85f67513a120fcbd008b4004c1e80883e03f83f80472066820011800c35589e553565781ecd001000083e4f089e60f1186400100000f118e"
    "500100000f1196600100000f119e700100000f11a6800100000f11ae900100000f11b6a00100000f11beb0010000e8000000005b31ff5689"
    "f8c1e00401f08b1510fcbd0083e201528b1520fcbd0089f931f6ff93810300005e89f8c1e0048b0c06898cbe0001000001f056ff750c5031"
    "f6ff93850300005e4783ff0b7cb831ff89f8c1e004f30f104406080f548345030000f30f1184beb0000000c6843ee0000000004783ff0b7c"
    "d7c786f00000000b000000b9fffffffff30f108b5503000031ff80bc3ee0000000007514f30f1084beb00000000f2fc17306f30f10c889f9"
    "4783ff0b7cdc83f9ff0f84e90100000f2f8b590300000f82c801000089cac1e204f30f10ab5d0300000f57c00f2f4416087608f30f10ab61"
    "030000f30f103416f30f107c160831ff80bc3ee000000000740e89f8c1e004e8ee01000085c0750b4783ff0b7ce2e979010000f30f10848e"
    "00010000f30f5c84be00010000f30f10c80f548b450300000f2f8b790300000f8298000000f30f10a35d0300000f57c90f2fc17308f30f10"
    "a36103000089f8c1e004f30f10440608f30f5cc70f548345030000f30f598371030000f30f59c0f30f10935d030000f30f5cd00f57c9f30f"
    "5fd1f30f51d2f30f599365030000f30f589375030000f30f59d4f30f581406f30f10f231ff80bc3ee000000000740e89f8c1e004e8310100"
    "0085c075104783ff0b7ce2f30f113416e9b7000000f30f103416c786f40000004000000031ffc786f80000000000000080bc3ee000000000"
    "747389f8c1e004f30f107c160850e8e700000085c058745df30f10c6f30f5c04060f548345030000f30f598369030000f30f59c0f30f1093"
    "5d030000f30f5cd00f57c9f30f5fd1f30f51d2f30f59936d030000f30f589375030000f30f59d5f30f58540608f30f11541608c786f80000"
    "00010000004783ff0b0f8c79ffffff83bef800000000740cff8ef40000000f8558ffffffc6840ee000000001ff8ef00000000f85dbfdffff"
    "8b4df4c1e1040f10040e8b45080f11000f1086400100000f108e500100000f1096600100000f109e700100000f10a6800100000f10ae9001"
    "00000f10b6a00100000f10beb00100008d65f45f5e5b5dc20800f30f10c6f30f5c0406f30f598369030000f30f59c0f30f10cff30f5c4c06"
    "08f30f598b71030000f30f59c9f30f58c131c00f2f837d0300007305b801000000c32e8db426000000008db600000000ffffff7fffffff7f"
    "ffffff7fffffff7fcaf24971000070420000803f000080bf0000ae4264523c3c000041434ac8a93b0000803f0000f04177be7f3f60fe1700"
    "20011800")
ABSMASK_OFFSET = 0x3b0   # 16-byte aligned constant (andps operand)


def code_bytes() -> bytes:
    if len(CODE) > CODE_SIZE:
        raise ValueError("formation art spacing code exceeds its allocation")
    return CODE.ljust(CODE_SIZE, b"\xcc")


# Retail code around the two call sites (sha256); every other owner leaves them retail. The getter
# 0x17FE60 and the transform 0x180120 are called through their entry points, so an owner hooking
# them (anniversary kickoff diagrams) composes.
GUARDS = (
    (0x181010, 0x7E, "c7fa05000639de74c39c2d1233370199b868f100c8f6571fdc2fa205c2cf2529", "icon drawer before the hook"),
    (0x181093, 0x14A, "8f61903ba428ac93a9d671c748b0c9c899a3621c1226d82d685c6738063fc225", "icon drawer after the hook"),
    (0x182480, 0x6F, "a0c188b9ef1b431870f8c47eafa9f4f9aab872bbca360a76c5d77c37b600cad4", "slot drawer before the hook"),
    (0x1824F4, 0x30, "9cf43396b056d555600036fdbe6ec1ff4074cc3046d70e78194b40940651ad71", "slot drawer after the hook"),
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _space():
    from . import nfl2k5_xbe_space as space
    return space


def hook_bytes(site: int, code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - (site + 5))


def sites(code_va: int):
    return tuple((label, site, retail, hook_bytes(site, code_va)) for label, site, retail in HOOKS)


def allocation(payload: bytes) -> dict | None:
    space = _space()
    if space.status(payload) != "applied":
        return None
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    if not rows:
        return None
    require(len(rows) == 1 and rows[0]["kind"] == "code" and rows[0]["size"] == CODE_SIZE,
            "foreign formation art spacing allocation")
    return rows[0]


def _state(payload: bytes):
    image = XbeImage(payload)
    for va, size, digest, label in GUARDS:
        require(hashlib.sha256(image.read(va, size)).hexdigest() == digest, f"foreign {label} at {va:#x}")
    space = _space()
    require(space.status(payload) != "foreign", "foreign executable geometry or digest")
    row = allocation(payload)
    hooks = [image.read(site, 5) for _label, site, _retail in HOOKS]
    retail = [r for _label, _site, r in HOOKS]
    if row is None:
        require(hooks == retail, "formation art hook without its allocation")
        return "retail", None
    code = image.read(row["va"], CODE_SIZE)
    if code == b"\xcc" * CODE_SIZE:
        require(hooks == retail, "formation art hook without its code")
        return "retail", row
    require(code == code_bytes(), "foreign formation art spacing code")
    require(row["va"] & 15 == 0, "formation art spacing code is not 16-byte aligned")
    require(hooks == [hook_bytes(site, row["va"]) for _label, site, _r in HOOKS],
            "formation art spacing code without its hooks")
    return "applied", row


def status(payload: bytes) -> str:
    try:
        return _state(payload)[0]
    except (ValueError, KeyError, TypeError, IndexError, struct.error):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Install the late owner and its two hooks. Idempotent; refuses foreign bytes."""
    from . import nfl2k5_rdata_sites as rdata
    space = _space()
    state, found = _state(payload)
    common = {"owner": OWNER, "experimental": EXPERIMENTAL, "runtime_witnessed": RUNTIME_WITNESSED,
              "owner_bytes": CODE_SIZE, "hooks": [hex(site) for _label, site, _r in HOOKS]}
    if state == "applied":
        return payload, {**common, "already_applied": True, "changed_bytes": 0, "code_va": hex(found["va"])}
    before = payload
    if found is None:
        if space.status(payload) == "retail":
            payload, _ = space.apply(payload, REQUESTS, scaleout=True)
        else:
            payload, _ = space.extend_scaleout(payload, REQUESTS)
        found = allocation(payload)
    require(found is not None, "reserve the formation art spacing allocation first")
    installed, code_receipt = space.install_code(payload, OWNER, code_bytes())
    result, site_receipt = rdata.apply(installed, sites(found["va"]), OWNER)
    require(status(result) == "applied", "formation art spacing postcondition failed")
    changed = sum(a != b for a, b in zip(before, result)) + abs(len(result) - len(before))
    return result, {**common, **site_receipt, "already_applied": False, "code_install": code_receipt,
                    "code_va": hex(found["va"]), "changed_bytes": changed,
                    "before_sha256": hashlib.sha256(before).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest()}


def reservations(payload: bytes) -> list[dict]:
    """The live spans this owner writes (for overlap checks)."""
    return [dict(owner=OWNER, start=hex(site), end=hex(site + 5), size=5,
                 basis=f"pinned live call 0x180120 in the {label}; not a cave") for label, site, _r in HOOKS]


__all__ = ["OWNER", "REQUESTS", "HOOKS", "CODE_SIZE", "ICON_ACROSS", "ICON_DEEP", "code_bytes", "sites",
           "allocation", "status", "apply", "reservations"]
