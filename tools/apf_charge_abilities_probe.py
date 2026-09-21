"""Bounded charge-state execution using the existing guest-image/PPC helpers.

Owned bytes remain in memory or a temporary directory. The only callee
boundaries are charge rate (1 unit/sec) and three notification calls. Tier,
abilities, input gating, state transitions and the caller's CPU bypass run as
retail instructions. This is not a Xenia gameplay witness.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import subprocess
import tempfile

from mod_editor.core import apf2k8_charge_abilities as patch
from mod_editor.core.apf2k8_xex import decode_xex
from tools.apf_static_recomp_guest_image_bootstrap import (
    EXPECTED_XEX_SHA256, EXPECTED_DECODED_SHA256, parse_xex_execution_metadata,
)
from tools.apf_playcall_research_probe import Machine

PLAYER, STATE, INPUT, ROSTER, GAME_STATE = 0x300000, 0x310000, 0x320000, 0x330000, 0x340000
TEAM, AUTO = 0x360000, 0x370000


def load_owned_image(path):
    """Use bootstrap's native extractor when available, portable codec otherwise."""
    source = Path(path).read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_XEX_SHA256:
        raise ValueError("Owned XEX differs from the pinned BASE input")
    metadata = parse_xex_execution_metadata(source)
    root = Path(__file__).resolve().parents[1]
    vendor = root / "tools/vendor/XenonRecomp"
    archive = vendor / "build/XenonUtils/libXenonUtils.a"
    import shutil
    compiler = shutil.which("clang++-18")
    if compiler and archive.is_file():
        with tempfile.TemporaryDirectory(prefix="apf-charge-bootstrap-") as temporary:
            exe, image = Path(temporary) / "extract", Path(temporary) / "image.pe"
            command = [compiler, "-std=c++20", "-O2", str(root / "tools/xex_extract_pe.cpp"),
                       f"-I{vendor / 'XenonUtils'}", f"-I{vendor / 'thirdparty/TinySHA1'}",
                       f"-I{vendor / 'thirdparty/tiny-AES-c'}", str(archive), "-o", str(exe)]
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run([str(exe), str(path), str(image)], check=True, capture_output=True)
            data = image.read_bytes()
    else:
        data, _ = decode_xex(source)
    if hashlib.sha256(data).hexdigest() != EXPECTED_DECODED_SHA256:
        raise ValueError("Bootstrap decoded image hash differs")
    return data, metadata


def branch_target(image, pc):
    word = struct.unpack_from(">I", image, pc - patch.IMAGE_BASE)[0]
    assert word >> 26 == 18
    delta = word & 0x3FFFFFC
    return pc + (delta - 0x4000000 if delta & 0x2000000 else delta)


class ChargeMachine(Machine):
    def __init__(self, image, *, patched=False):
        super().__init__(image, b"")
        self.profile = patch.PROFILES[int(self.updated)]
        self.document = patch.PatchDocument(self.profile, patched)
        patch.verify_image(image, self.document)
        self.image = patch.apply_image(image, self.document)
        self.cpu.mem_write(patch.IMAGE_BASE, self.image)
        self.put(PLAYER + 0x14, STATE)
        self.put(PLAYER + 0x10, INPUT)
        self.put(PLAYER + 0x44, ROSTER)
        self.put(PLAYER + 0x40, TEAM)
        self.put(TEAM + 0x24, AUTO)
        self.put(STATE + 4, 0x350000)
        self.cpu.mem_write(0x350000, b"\x18")
        data_delta = 0x30 if self.updated else 0
        self.put(0x851A27EC + data_delta, GAME_STATE)
        self.put(0x84F3F8F8, 0)
        self.putf(0x84F0A16C, .5)
        # Read actual branch destinations; adjacent function families have
        # different TU deltas and must not inherit this routine's delta.
        self.rate = branch_target(image, self.site(0x848C5440))
        self.boundaries[self.rate] = lambda m: (m.setfpr(1, 1.), m.ret(0))
        for base in (0x848C5480, 0x848C5558, 0x848C4DE0):
            self.boundaries[branch_target(image, self.site(base))] = lambda m: m.ret(0)

    def site(self, base):
        return patch.address(base, self.profile)

    def configure_player(self, tier, abilities=(), *, qb=False, passing=True):
        record = bytearray(0x150)
        record[18] = tier
        for name, offset, bit in patch.CHARGED_ABILITIES:
            if name in abilities:
                record[offset] |= 1 << bit
        self.cpu.mem_write(ROSTER, bytes(record))
        self.cpu.mem_write(PLAYER + 0x34, bytes([0 if qb else 1]))
        self.put(INPUT + 0x18, 4 | (0 if passing else 8))
        self.put(STATE + 0x2C, 1)
        self.putf(STATE + 0xFC, 0)
        self.putf(STATE + 0x100, -1)
        self.put(STATE + 0x1A8, 0)
        self.put(STATE + 0x104, 0)
        return record

    def charge(self):
        trace, peak = [], 0
        for _ in range(7):
            before = self.steps
            self.call(self.site(patch.ROUTINE), PLAYER, bound=2_000)
            peak = max(peak, self.steps - before)
            trace.append({"charge": struct.unpack(">f", self.cpu.mem_read(STATE + 0xFC, 4))[0],
                          "state": (self.get(STATE + 0x1A8) >> 22) & 7})
        return {"maximum": trace[-1]["charge"], "frames": trace, "peak_instructions": peak}

    def caller(self, *, controller=0, selected_auto=False):
        self.put(INPUT, controller)
        self.put(AUTO + 0x1B4, 2 if selected_auto else 0)
        self.put(AUTO + 0x1368, PLAYER if selected_auto else 0)
        self.setreg(28, INPUT)
        self.setreg(30, PLAYER)
        delta = 0xE88 if self.updated else 0
        self.call(0x848D6C14 + delta, stop=0x848D6C38 + delta, bound=2_000)
        return self.site(patch.ROUTINE) in self.visited
