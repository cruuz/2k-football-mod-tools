"""Bounded charge-state execution using the existing guest-image/PPC helpers.

Owned bytes remain in memory or a temporary directory. The only callee
boundaries are charge rate (1 unit/sec) and three notification calls. Tier,
abilities, input gating, state transitions and the caller's CPU bypass run as
retail instructions. This is not a Xenia gameplay witness.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import os
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
# Engaged blocker for the defensive line-move chain (all synthetic objects).
BLOCKER, BLOCKER_STATE, BLOCKER_ROSTER, BLOCKER_TEAM = 0x3A0000, 0x3A1000, 0x3A2000, 0x3A3000
BLOCKER_INPUT, POSITION, BLOCKER_POSITION = 0x3A4000, 0x3A5000, 0x3A6000
# Line-move request IDs read by the native chooser: (ID - 0x0A) >> 1 picks the
# move with a side, ID - 0x12 picks it without one; other IDs roll a random move.
LINE_MOVE_REQUESTS = {0: (0x0A, 0x0B, 0x12), 1: (0x0C, 0x0D, 0x13),
                      2: (0x0E, 0x0F, 0x14), 3: (0x10, 0x11, 0x15)}


def load_owned_image(path):
    """Use bootstrap's native extractor when available, portable codec otherwise."""
    source = Path(path).read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_XEX_SHA256:
        raise ValueError("Owned XEX differs from the pinned BASE input")
    metadata = parse_xex_execution_metadata(source)
    cached = os.environ.get("APF_RETAIL_DECODED_IMAGE")
    if cached:
        data = Path(cached).read_bytes()
        if hashlib.sha256(data).hexdigest() != EXPECTED_DECODED_SHA256:
            raise ValueError("Owned decoded image cache differs from the pinned BASE input")
        return data, metadata
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
    def __init__(self, image, *, patched=False, revision=patch.CURRENT_REVISION):
        super().__init__(image, b"")
        self.profile = patch.PROFILES[int(self.updated)]
        self.document = patch.PatchDocument(self.profile, patched, revision)
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
        self.put(STATE, 0)
        self.put(STATE + 4, 0x350000)
        self.put(0x350000, 0x18000000)
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

    def consume_move(self, move):
        """Execute consume, retail jump-table dispatch and the move gate.

        These four explicit move IDs avoid the direction-selection callee;
        both directions enter the real shared spin/juke gate. Stop before
        animation setup, with the actual consumed state still in memory.
        """
        moves = {"spin_left": 0x1D, "spin_right": 0x1E,
                 "juke_left": 0x21, "juke_right": 0x22}
        self.put(STATE, moves[move])
        for reg, value in ((30, PLAYER), (31, STATE), (28, 0), (29, 0)):
            self.setreg(reg, value)
        delta = 0xE88 if self.updated else 0
        self.call(0x848E7EF4 + delta, PLAYER, stop=0x848E7FB8 + delta, bound=2_000)
        return (self.get(STATE + 0x1A8) >> 22) & 7

    def line_site(self, base):
        return patch.line_move_address(base, self.profile)

    def _pair(self, high_site, low_site):
        """Decode a lis + signed-displacement address pair from the image."""
        high, low = self.get(high_site) & 0xFFFF, self.get(low_site) & 0xFFFF
        return ((high << 16) + (low - 0x10000 if low & 0x8000 else low)) & 0xFFFFFFFF

    def configure_blocker(self):
        """A CPU blocker engaged with PLAYER, with no ability and no charge."""
        for address, value in ((BLOCKER + 0x14, BLOCKER_STATE), (BLOCKER + 0x44, BLOCKER_ROSTER),
                               (BLOCKER + 0x40, BLOCKER_TEAM), (BLOCKER + 0x10, BLOCKER_INPUT),
                               (BLOCKER + 0x1C, BLOCKER_POSITION), (PLAYER + 0x1C, POSITION),
                               (BLOCKER_INPUT, 0xFFFFFFFF), (BLOCKER_TEAM + 0x38, 0), (TEAM + 0x38, 0)):
            self.put(address, value)
        self.cpu.mem_write(BLOCKER_STATE, bytes(0x400))
        self.cpu.mem_write(BLOCKER_ROSTER, bytes(0x150))
        self.put(BLOCKER_STATE + 4, 0x350000)
        self.putf(POSITION + 0x38, 1.)

    def consume_line_move(self):
        """Run the engaged pass-rush entry's own consume call (its real LR)."""
        site = self.line_site(0x848B3758)
        if branch_target(self.image, site) != self.site(0x848C4D70):
            raise AssertionError("Engaged pass-rush consume call site moved")
        self.call(site, PLAYER, stop=site + 4, bound=2_000)

    def choose_line_move(self, request, roll=0):
        """Execute the native line-move chooser (and any patched exit).

        Only the random primitives are boundaries; random moves take roll & 3.
        Returns (move index, rewritten request ID).
        """
        self.put(STATE, request)
        saved = dict(self.boundaries)
        self.random_boundaries(integer=roll, delta=0xFD0 if self.updated else 0)
        try:
            self.call(self.line_site(patch.LINE_MOVE_CHOOSER), BLOCKER, PLAYER, bound=5_000)
        finally:
            self.boundaries = saved
        return self.reg(3), self.get(STATE)

    def charge_difference(self):
        """Real 0x848C48C8: the mover's consumed level minus the blocker's."""
        self.call(self.site(0x848C48C8), PLAYER, BLOCKER, bound=500)
        return self.fpr(1)

    def line_move_outcome(self, index, *, slider=.5, roll=.9):
        """Real line-move handler prefix and its outcome gate 0x848B0000.

        The handler maps its move entry to the index, builds the real ability
        mask (0x848AD598) and calls the gate, which calls the real charge
        difference, slider leaf, flag leaf and random-range helper. Only the
        two random primitives are boundaries. The pass-rush slider entry and
        the game globals the gate reads are written explicitly. Returns the
        gate's outcome grade 0..4 (2 = decided later by the rating contest).
        """
        handler = self.line_site(0x848B0458)
        gate_call = self.line_site(0x848B0568)
        gate = branch_target(self.image, gate_call)
        entries = self._pair(self.line_site(0x848B0474), self.line_site(0x848B0484))
        game = self._pair(self.line_site(0x848B0058), self.line_site(0x848B0060))
        anchor = self._pair(self.line_site(0x848B0018), self.line_site(0x848B0028))
        options = self._pair(self.line_site(0x848B02F0), self.line_site(0x848B02F4))
        flag_leaf = branch_target(self.image, self.line_site(0x848B0054))
        flag = self._pair(flag_leaf, flag_leaf + 4) + (self.get(flag_leaf + 8) & 0xFFFF)
        slider_leaf = branch_target(self.image, self.line_site(0x848B0264))
        table = (self._pair(slider_leaf, slider_leaf + 8) + (self.get(slider_leaf + 0x10) & 0xFFFF))
        for address, value in ((game, 0), (game + 0x34, 0), (game + 0x3C, 0), (anchor, 0),
                               (options + 0x2C4, 0), (options + 0x1EC, 0), (options, 0), (flag, 0)):
            self.put(address, value)
        for side in (0, 1):
            self.putf(table + side * 0x28 + 4, slider)
        saved = dict(self.boundaries)
        self.random_boundaries(fraction=roll, integer=0, delta=0xFD0 if self.updated else 0)
        try:
            self.setfpr(1, 1.)
            self.call(handler, BLOCKER, PLAYER, 0, 0, entries + 0xC * index,
                      stop=gate_call + 4, bound=20_000)
        finally:
            self.boundaries = saved
        if gate not in self.visited:
            raise AssertionError("Line-move handler did not reach its outcome gate")
        return self.reg(3)

    def move_bonus(self, category):
        """Run the complete scalar bonus helper, including its stop query."""
        self.put(0x350000, category << 24)
        self.call(self.site(0x848C4B40), PLAYER, bound=300)
        return self.fpr(1)

    def feedback(self, tier, *, discharge=False, previous_packet=None, blend=1.):
        """Execute retail feedback decisions, stopping before any GPU work.

        Native packet packing and direct/interpolated scalar decoding are
        included. Actual pixels and render/update timing need a Xenia witness.
        Medal values use the retail packed tier / 2, never a patched value.
        """
        va = lambda a: patch.feedback_address(a, self.profile)
        if discharge:
            self.call(self.site(0x848C4D70), PLAYER, bound=2_000)
        self.setreg(10, STATE)
        self.setreg(29, PLAYER)  # native packet producer's current player
        self.setfpr(0, struct.unpack(">f", self.cpu.mem_read(STATE + 0x100, 4))[0])
        self.setfpr(28, 0.)
        self.setfpr(31, .5)
        self.setfpr(18, 1.)
        data_delta = 0x20 if self.updated else 0
        self.setfpr(19, struct.unpack('>f', self.cpu.mem_read(0x82000AC0, 4))[0])
        self.setfpr(21, struct.unpack('>f', self.cpu.mem_read(0x820C92F8 + data_delta, 4))[0])
        # Two VMX128 position transports cannot affect the scalar timer/charge
        # decisions. Skip those peripheral transports, then execute the native
        # expiry, active-ripple and held-charge branch selection itself.
        for site in (0x84AA6020, 0x84AA6030):
            self.boundaries[va(site)] = lambda m, target=va(site) + 4: m.cpu.reg_write(m.r.UC_PPC_REG_PC, target)
        try:
            self.call(va(0x84AA601C), stop=va(0x84AA6070), bound=2_000)
        finally:
            for site in (0x84AA6020, 0x84AA6030):
                del self.boundaries[va(site)]
        channel, timer = self.fpr(30), self.fpr(29)
        # Execute scalar packet writes and the medal bits. Vector/position
        # inputs are zero; they cannot affect the charge or timer bit fields.
        packet = 0x380000
        self.put(packet, 0)
        self.put(packet + 4, 0)
        self.setreg(29, PLAYER)
        self.setreg(31, packet)
        self.setfpr(26, 127.)
        self.call(va(0x84AA60E8), stop=va(0x84AA60EC), bound=10)
        self.setfpr(27, 511.)
        self.setreg(10, 0)
        self.setreg(9, self.reg(1) + 0x50)
        self.call(va(0x84AA6100), stop=va(0x84AA6194), bound=100)
        packet_word = self.get(packet)
        # Direct render caller: decode with its actual retail scaling factors.
        self.setreg(10, self.get(packet + 4))
        for reg, base in ((26, 0x820FE194), (27, 0x820FE18C), (29, 0x820FE190),
                          (30, 0x820FE174), (31, 0x820FE170)):
            data_address = base + (0x20 if self.updated else 0)
            self.setfpr(reg, struct.unpack(">f", self.cpu.mem_read(data_address, 4))[0])
        self.call(va(0x84AA6FCC), stop=va(0x84AA7044), bound=100)
        if previous_packet is not None:
            self.put(packet + 0x20, previous_packet)
            self.setreg(31, packet + 0x20)
            self.setreg(11, packet - 4)
            self.setfpr(28, blend)
            for reg, base in ((25, 0x820FE184), (24, 0x820FE188)):
                data_address = base + (0x20 if self.updated else 0)
                self.setfpr(reg, struct.unpack(">f", self.cpu.mem_read(data_address, 4))[0])
            self.call(va(0x84AA6F44), stop=va(0x84AA7044), bound=100)
        decoded_charge, decoded_timer = self.fpr(3), self.fpr(4)
        self.setreg(23, tier // 2)
        self.setfpr(31, decoded_charge)
        self.call(va(0x84AA66AC), stop=va(0x84AA66F4), bound=100)
        displayed = self.fpr(29)

        def choose(start, destinations):
            for destination in destinations:
                self.boundaries[va(destination)] = lambda m: m.ret(0)
            try:
                self.call(va(start), bound=100)
                return next(a for a in destinations if va(a) in self.visited)
            finally:
                for destination in destinations:
                    del self.boundaries[va(destination)]

        outer = choose(0x84AA6934, (0x84AA6944, 0x84AA69F4)) == 0x84AA6944
        second_discharge = choose(0x84AA673C, (0x84AA67A4, 0x84AA67B4)) == 0x84AA67A4
        return {"charge_channel": channel, "timer_channel": timer,
                "packet_word": packet_word, "decoded_charge": decoded_charge,
                "decoded_timer": decoded_timer,
                "displayed_charge": displayed * 2, "outer_ring": outer,
                "second_level_discharge": second_discharge,
                "medal": self.reg(23), "consumed_state": (self.get(STATE + 0x1A8) >> 22) & 7}
