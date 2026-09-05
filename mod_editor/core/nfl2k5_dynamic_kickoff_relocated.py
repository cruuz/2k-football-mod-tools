"""EXPERIMENTAL/UNWITNESSED dynamic kickoff in owned grown RX/RW pages.

Use after every existing patch, including dynamic_kickoff. The old cave is
retained byte-identically (or left retail); all eleven hooks enter the new
page. The same assembler generates both implementations. No retail function
bytes are distributed and no opcode search-and-replace relocation is used.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_dynamic_kickoff as kickoff
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest

OWNER = "nfl2k5_dynamic_kickoff_relocated"
REQUESTS = ((OWNER, "code", kickoff.CAVE_SIZE, 16), (OWNER, "data", 10, 4))


def _sites(payload):
    allocations = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(allocations) == {"code", "data"}, "missing kickoff allocation")
    for kind, size, align in (("code", kickoff.CAVE_SIZE, 16), ("data", 10, 4)):
        a = allocations[kind]
        space._require((a["size"], a["align"]) == (size, align), "foreign kickoff allocation size/alignment")
    return allocations["code"], allocations["data"]


def code_for(settings, code_va, data_va):
    return kickoff._code(settings, cave_va=code_va, storage_ranges=((data_va, 7), (data_va + 7, 3)))


def _installed(payload):
    code, data = _sites(payload)
    _, labels = code_for(kickoff._settings(), code["va"], data["va"])
    vals = {key: payload[code["raw"] + labels["config_" + key] - code["va"] + 6]
            for key in ("aim_prob", "tb_prob", "tb_yard", "target_min", "target_max")}
    settings = kickoff._settings(vals["tb_yard"], vals["aim_prob"],
                                 (vals["target_min"], vals["target_max"]), vals["tb_prob"])
    expected, labels = code_for(settings, code["va"], data["va"])
    space._require(payload[code["raw"]:code["raw"] + code["size"]] == expected, "foreign relocated code")
    for name, (va, original) in kickoff.HOOKS.items():
        off = kickoff._offset(payload, va, len(original))
        space._require(payload[off:off + len(original)] == kickoff._hook_bytes(name, labels), "mixed kickoff hooks")
    old = kickoff._offset(payload, kickoff.CAVE_VA, kickoff.CAVE_SIZE)
    old_bytes = payload[old:old + kickoff.CAVE_SIZE]
    space._require(hashlib.sha256(old_bytes).hexdigest() == kickoff.RETAIL_CAVE_SHA256
                   or old_bytes == kickoff._code(settings)[0], "foreign retired kickoff cave")
    return settings


def status(payload: bytes) -> str:
    try:
        space_state = space.status(payload)
        if space_state == "foreign":
            return "foreign"
        if space_state == "applied":
            owners = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
            if owners:
                code, _ = _sites(payload)
                if payload[code["raw"]:code["raw"] + code["size"]] != b"\xcc" * code["size"]:
                    _installed(payload)
                    return "applied"
        # Use the legacy-only recognizer to avoid a status delegation cycle.
        return "retail" if kickoff._legacy_status(payload) in ("retail", "applied") else "foreign"
    except (ValueError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload):
    state = status(payload)
    return {"status": state, **(_installed(payload) if state == "applied" else {})}


def apply(payload: bytes, **kwargs) -> tuple[bytes, dict]:
    state = status(payload)
    space._require(state != "foreign", "foreign/mixed kickoff relocation; rebuild from supported base")
    if state == "applied":
        settings = _installed(payload)
        space._require(not kwargs or kickoff._settings(**kwargs) == settings, "different kickoff settings; rebuild from base")
        return payload, {"status": "already_applied", "changed_bytes": 0, **settings}
    legacy = kickoff._legacy_status(payload)
    settings = kickoff._decode_legacy_settings(payload) if legacy == "applied" else kickoff._settings(**kwargs)
    space._require(not kwargs or settings == kickoff._settings(**kwargs), "different legacy kickoff settings")
    if space.status(payload) == "retail":
        allocated, allocation_receipt = space.apply(payload, REQUESTS)
    else:
        allocated, allocation_receipt = payload, {}
    code, data = _sites(allocated)
    content, labels = code_for(settings, code["va"], data["va"])
    installed, _ = space.install_code(allocated, OWNER, content)
    buf = bytearray(installed)
    edits = [{"label": "relocated_cave", "va": hex(code["va"]), "size": code["size"]}]
    for name, (va, original) in kickoff.HOOKS.items():
        off = kickoff._offset(installed, va, len(original))
        buf[off:off + len(original)] = kickoff._hook_bytes(name, labels)
        edits.append({"label": name, "va": hex(va), "size": len(original)})
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    result = bytes(buf)
    space._require(status(result) == "applied", "kickoff relocation postcondition failed")
    return result, {"status": "applied", "experimental": True, "runtime_witnessed": False,
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                    "allocation": allocation_receipt, "edits": edits, "reservations": space.reservations(result),
                    "code_va": hex(code["va"]), "data_va": hex(data["va"]), **settings}
