"""EXPERIMENTAL/UNWITNESSED initial deep-zone CB drop, USA retail.

Only the depth interpolator call in the zone initializer is replaced. Exact
position byte 18 and modes with (mode & 12) == 8 qualify. Receiver pickup,
later steering, movement banks and ball response keep their retail code.
Reserve the union of selected owners' REQUESTS before installing any owner.
No persistent data is allocated; the wrapper's scratch and x87 save are stack
local. The 78-byte body strengthens the memo's ABI with EFLAGS and x87
environment restoration, within its original 80-byte allocation budget.
"""
from __future__ import annotations

import hashlib
import math
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = "nfl2k5_zone_drop"
BODY_SIZE, CODE_SIZE = 78, 80
CAP_OFFSET = 50
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK_VA, CONTINUE_VA, CURVE_VA = 0x001A65D1, 0x001A65D6, 0x001B0AE0
RETAIL_HOOK = bytes.fromhex("e8 0a a5 00 00")
ZONE_RECORDS_VA = 0x00BE4B60
DEFAULT_CAP, MIN_CAP, MAX_CAP = 0.84, 0.50, 0.84
HELP_TEXT = (
    "Corners in deep zones backpedal instead of turning and running when they "
    "line up close to the line. Ball reaction and interceptions are not changed "
    "by this."
)
# Pin the surrounding algorithm, original leaf, both curves and its thresholds.
# In particular, the integer comparison in the wrapper requires the depth
# curve's finite, nonnegative results. Hashes avoid embedding retail routines.
RETAIL_GUARDS = (
    (0x001A652A, 167, "92d79a764ac84ee28a48119a5c9fc2d43e2bba11a86c431b9667f338d4f9de3b"),
    (CONTINUE_VA, 255, "9cf990d7256055059e84d42fbfeeb5f073d1aeb7488ceb4c382ba18d2288b9b3"),
    (CURVE_VA, 124, "85257e0d17fc30f87b44015e57a7951be3785ef634995aafaec65c9f5fc2bc7c"),
    (0x0050B2EC, 64, "d6849f9a94cc8189585a78ea45f1813c33c528112055ac3d49af491cffb9e3e1"),
    (0x00509B98, 4, "656d48b9a87ff9565ca1f17f38a1301691c3cb2ad32793ad3226cd3708296618"),
    (0x004F8DA0, 4, "d615db4ab0d2fbf3e307cfb9d57216c9ca3da28ed672b4f9281dec07f479d144"),
    (0x004E4180, 8, "0051cfd064ea4a91086438ce7f6b3d21ca62d76ee264a63f3692e57cda89cd6e"),
    (0x004E419C, 4, "e00e5eb9444182f352323374ef4e08ebcb784725fdd4fd612d7730540b3e0c8c"),
)


def _cap(value: float) -> float:
    space._require(type(value) in (int, float) and MIN_CAP <= value <= MAX_CAP
                   and math.isfinite(value),
                   "depth cap must be finite and within 0.50..0.84; retail promotes higher values to running")
    return struct.unpack("<f", struct.pack("<f", value))[0]


def code_for(code_va: int, cap: float = DEFAULT_CAP) -> bytes:
    """Position-specific stdcall wrapper; result is float32, as at continuation.

    EBX=P, ESI=A, ECX=curve, EDX=count, [ESP+4]=signed depth.
    Call the leaf once with a copied argument, then retain its GPR/EFLAGS and
    x87 environment (CW/SW/TOP/tags/IP/DP). Only ST(0)'s caller-visible float
    can change. FNSTENV masks exceptions during the temporary float store;
    FLDENV restores the leaf's environment and all deeper x87 values stay put.
    No SSE/MMX register or MXCSR instruction is added.
    """
    bits = struct.pack("<f", _cap(cap)).hex()
    a = _Asm(code_va)
    a.b("ff742404")                     # push [esp+4], leaf consumes copy
    a.call(CURVE_VA)
    a.b("9c 50 807b2c12")               # pushfd; push eax; exact byte CB
    a.j8("75", "done")
    a.b("8b86a4000000 c1e004")         # record index, 16-byte stride
    a.b("0fb680" + struct.pack("<I", ZONE_RECORDS_VA + 12).hex())
    a.b("240c 3c08")                   # ordinary deep, excludes modes 12..15
    a.j8("75", "done")
    a.b("83ec20 d9742404 d91c24")      # 4-byte float + 28-byte x87 environment
    a.label("cap")
    a.b("b8" + bits + " 390424")       # unsigned finite positive float compare
    a.j8("76", "reload")
    a.b("890424")
    a.label("reload")
    a.b("d90424 d9642404 8d642420")    # result, original environment, release scratch
    a.label("done")
    a.b("58 9d c20400")                # leaf's eax/flags, consume original argument
    body = a.assemble()
    space._require(len(body) == BODY_SIZE, "zone-drop body size drift")
    space._require(a.labels["cap"] + 1 == CAP_OFFSET, "zone-drop cap offset drift")
    return body + b"\xcc" * (CODE_SIZE - BODY_SIZE)


def site(payload: bytes) -> dict:
    owners = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    space._require(len(owners) == 1, "missing zone-drop allocation; reserve the full owner union on a clean base")
    a = owners[0]
    space._require((a["kind"], a["size"], a["align"]) == ("code", CODE_SIZE, 16),
                   "foreign zone-drop allocation kind/size/alignment")
    return a


def hook_bytes(code_va: int) -> bytes:
    return b"\xe8" + struct.pack("<i", code_va - CONTINUE_VA)


def _recognize(payload: bytes) -> tuple[str, float | None]:
    layout = space.layout(payload)  # validates geometry, owned pages and all section digests
    image = XbeImage(payload)
    for va, size, digest in RETAIL_GUARDS:
        space._require(hashlib.sha256(image.read(va, size)).hexdigest() == digest,
                       f"foreign zone-drop prerequisite at {va:#x}")
    hook = image.read(HOOK_VA, len(RETAIL_HOOK))
    if not any(a["owner"] == OWNER for a in layout["allocations"]):
        space._require(hook == RETAIL_HOOK, "foreign zone-drop hook without allocation")
        return "retail", None
    a = site(payload)
    content = image.read(a["va"], a["size"])
    if content == b"\xcc" * CODE_SIZE:
        space._require(hook == RETAIL_HOOK, "mixed zone-drop hook with empty allocation")
        return "retail", None
    # Immediate starts at byte 50; compare the entire regenerated body/padding,
    # not just this configurable field or an E8 opcode.
    cap = _cap(struct.unpack_from("<f", content, CAP_OFFSET)[0])
    space._require(content == code_for(a["va"], cap), "foreign zone-drop code or padding")
    space._require(hook == hook_bytes(a["va"]), "mixed/foreign zone-drop hook")
    return "applied", cap


def status(payload: bytes) -> str:
    try:
        return _recognize(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, **({"cap": _recognize(payload)[1]} if state == "applied" else {})}


def apply(payload: bytes, *, cap: float | None = None) -> tuple[bytes, dict]:
    """Apply or replay an exact installation. Changing settings needs a rebuild."""
    wanted = _cap(DEFAULT_CAP if cap is None else cap)
    try:
        state, installed_cap = _recognize(payload)  # every preflight before any mutation
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError, OverflowError) as exc:
        raise ValueError(f"foreign/mixed zone-drop input: {exc}") from exc
    common = {"experimental": True, "runtime_witnessed": False, "owner": OWNER,
              "persistent_data_bytes": 0, "body_bytes": BODY_SIZE, "owned_code_bytes": CODE_SIZE}
    if state == "applied":
        space._require(cap is None or wanted == installed_cap, "different zone-drop cap; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0,
                         "cap": installed_cap, "edits": [], **common}
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS)
    else:
        # The current allocator seals a complete sorted request set. Never move
        # another owner's installed code or claim an unallocated address.
        site(payload)
        allocated, allocation_receipt = payload, {}
    a = site(allocated)
    installed, _ = space.install_code(allocated, OWNER, code_for(a["va"], wanted))
    image = XbeImage(installed)
    off = image.offset(HOOK_VA, len(RETAIL_HOOK))
    buf = bytearray(installed)
    buf[off:off + len(RETAIL_HOOK)] = hook_bytes(a["va"])
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    space._require(status(result) == "applied", "zone-drop postcondition failed")
    return result, {"status": "applied", "cap": wanted, **common,
                    "changed_bytes": sum(x != y for x, y in zip(payload, result)) + len(result) - len(payload),
                    "file_growth": len(result) - len(payload), "allocation": allocation_receipt,
                    "before_sha256": hashlib.sha256(payload).hexdigest(),
                    "after_sha256": hashlib.sha256(result).hexdigest(),
                    "edits": [{"label": "initial_depth_call", "va": hex(HOOK_VA), "size": 5},
                              {"label": "zone_drop_wrapper", "va": hex(a["va"]), "size": CODE_SIZE}],
                    "reservations": space.reservations(result)}
