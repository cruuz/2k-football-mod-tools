#!/usr/bin/env python3
"""PROVED OFFLINE: execute the retail lob-speed reader, never a game session.

Reads the supplied retail XBE and optional disc without writing either. All
patched executables exist only in memory. Writes a small JSON evidence file.
Requires Unicorn; modeled hang/apex are equal-height ballistic estimates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core.nfl2k5_bump_strength import _sections


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def encoded_lookup(table, yards):
    """Independent interpolation of the actual float32 cm knots and input."""
    f32 = lambda value: struct.unpack("<f", struct.pack("<f", value))[0]
    pairs = tuple((f32(d * tt.YD_CM), f32(s * tt.YD_CM)) for d, s in table)
    distance = f32(yards * tt.YD_CM)
    if distance <= pairs[0][0]:
        value = pairs[0][1]
    elif distance >= pairs[-1][0]:
        value = pairs[-1][1]
    else:
        for (x0, y0), (x1, y1) in zip(pairs, pairs[1:]):
            if distance <= x1:
                value = (y1 - y0) * (distance - x0) / (x1 - x0) + y0
                break
    return struct.pack("<f", value).hex()


class NativeReader:
    """Real FUN_002d8970 and FUN_001b0ae0, with no hooks replacing code/results."""
    def __init__(self, payload):
        import unicorn as u
        from unicorn import x86_const as x
        self.x, self.u = x, u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.u.mem_map(0x10000, 0x1600000)
        self.u.mem_write(0x10000, payload[:0x1000])
        for section in _sections(payload):
            self.u.mem_write(section.virtual_address,
                             payload[section.raw_offset:section.raw_offset + section.raw_size])
        self.u.mem_map(0x2000000, 0x10000)
        # Return trampoline only stores the actual x87 return value as float32.
        self.u.mem_write(0x2000000, b"\xd9\x1d" + struct.pack("<I", 0x2000100))
        self.u.reg_write(x.UC_X86_REG_FPCW, 0x37f)
        self.reads = set()
        self.instructions = set()
        self.u.hook_add(u.UC_HOOK_MEM_READ, self._read)
        self.u.hook_add(u.UC_HOOK_CODE, self._code)

    def _read(self, _machine, _access, address, size, _value, _user):
        if tt.ARC_TABLE_VA <= address < tt.ARC_TABLE_END_VA or 0x50BC8C <= address < 0x50BCE4:
            self.reads.add((address, size))

    def _code(self, _machine, address, _size, _user):
        self.instructions.add(address)

    def speed(self, yards):
        # stdcall(distance_cm, blend_factor_1, blend_factor_2), with zero lob blend.
        self.u.mem_write(0x2008000, struct.pack("<Ifff", 0x2000000, yards * tt.YD_CM, 0.0, 1.0))
        self.u.reg_write(self.x.UC_X86_REG_ESP, 0x2008000)
        self.u.emu_start(0x2D8970, 0x2000006, count=1000)
        assert self.u.reg_read(self.x.UC_X86_REG_EIP) == 0x2000006, "reader failed to return"
        assert self.u.reg_read(self.x.UC_X86_REG_ESP) == 0x2008010, "reader stack mismatch"
        raw = bytes(self.u.mem_read(0x2000100, 4))
        return struct.unpack("<f", raw)[0] / tt.YD_CM, raw.hex()


def prove(retail_path, disc_path=None):
    retail = retail_path.read_bytes()
    assert sha(retail) == tt.RETAIL_XBE_SHA256, "retail XBE hash mismatch"
    new, receipt = tt.apply_arc_table(retail)
    assert tt.revert_arc_table(new, receipt) == retail
    old = bytearray(new)
    off = tt.ARC_TABLE_VA - tt.IMAGE_BASE
    old[off:off + tt.ARC_TABLE_CURVE.size] = tt.ARC_TABLE_CURVE.encode(tt.HIGH_ARC_20260903_LOBSPEED)
    old = bytes(old)
    upgraded, upgrade_receipt = tt.apply_arc_table(old)
    assert upgraded == new
    assert tt.revert_arc_table(upgraded, upgrade_receipt) == old
    basic, _ = tt.plan_patch(retail, {"lobspeed": tt.REALISTIC_LOBSPEED})
    variants = {"retail": (retail, tt.CURVES["lobspeed"].retail),
                "basic_realistic": (basic, tt.REALISTIC_LOBSPEED),
                "old_20260903": (old, tt.HIGH_ARC_20260903_LOBSPEED),
                "new_20261002": (new, tt.ARC_BY_DISTANCE_LOBSPEED)}
    disc_evidence = None
    if disc_path:
        with disc_path.open("rb") as source:
            size = os.fstat(source.fileno()).st_size
            offset, length = tt.image_xbe_extent(source.fileno(), size)
            source.seek(offset)
            disc_xbe = source.read(length)
        arc = tt.read_arc_table(disc_xbe)
        assert arc["state"] == "legacy_high_arc", arc
        assert arc["points"] == tt.HIGH_ARC_20260903_LOBSPEED
        disc_evidence = {"path": str(disc_path), "disc_bytes": size, "xbe_offset": offset,
                         "xbe_bytes": length, "xbe_sha256": sha(disc_xbe), "arc_table": arc,
                         "settings": tt.infer_settings(tt.read_curves(disc_xbe), arc["state"]).__dict__}
        variants["reported_disc"] = (disc_xbe, tt.HIGH_ARC_20260903_LOBSPEED)
        upgraded_disc, disc_receipt = tt.apply_arc_table(disc_xbe)
        assert tt.revert_arc_table(upgraded_disc, disc_receipt) == disc_xbe
        changed = [i for i, (a, b) in enumerate(zip(disc_xbe, upgraded_disc)) if a != b]
        assert all(off <= i < off + tt.ARC_TABLE_CURVE.size for i in changed), "disc upgrade moved other bytes"
        disc_evidence["in_memory_upgrade"] = {"receipt": disc_receipt, "only_header_table_changed": True,
                                              "exact_revert": True}
        variants["reported_disc_upgraded_in_memory"] = (upgraded_disc, tt.ARC_BY_DISTANCE_LOBSPEED)
    output = {"claim": "PROVED OFFLINE", "retail_path": str(retail_path),
              "retail_sha256": sha(retail), "disc": disc_evidence,
              "method": "Unicorn x86-32 runs FUN_002d8970 and both real FUN_001b0ae0 calls; zero lob blend; x87 return stored as float32",
              "physics": "DESIGN: hang=distance/speed; equal-height apex=980.664/91.44*hang^2/8; no in-game witness",
              "code_sha256": {}, "profiles": {}, "apply_receipt": receipt,
              "upgrade_receipt": upgrade_receipt, "exact_reverts": True}
    for va, length in ((0x2D8970, 0x4b), (0x1B0AE0, 0x7c)):
        offset, _ = tt._text_offset(retail, va)
        output["code_sha256"][hex(va)] = {"bytes": length, "sha256": sha(retail[offset:offset + length])}
    short_bits = {}
    distances = sorted(set([i / 4 for i in range(0, 161)] + list(range(41, 81))))
    for name, (payload, table) in variants.items():
        machine = NativeReader(payload)
        rows = []
        bits = {}
        max_error = 0
        for distance in distances:
            speed, raw = machine.speed(distance)
            expected = tt.interpolate(table, distance)
            error = abs(speed - expected)
            assert raw == encoded_lookup(table, distance), (name, distance, raw, encoded_lookup(table, distance))
            assert math.isclose(speed, expected, rel_tol=1e-6, abs_tol=2e-5), (name, distance, speed, expected)
            max_error = max(max_error, error)
            if distance <= 40:
                bits[distance] = raw
            if distance in range(5, 81, 5):
                hang = distance / speed
                rows.append({"yards": distance, "speed_yd_s": speed, "table_speed_yd_s": expected,
                             "native_return_cm_s_float32_hex": raw, "hang_s": hang,
                             "apex_yd": tt.GRAVITY_YD_S2 * hang ** 2 / 8})
        if name == "retail":
            short_bits = bits
        elif name != "basic_realistic":
            assert bits == short_bits, (name, "short game differs from retail")
        assert {0x2D8982, 0x2D8997, 0x1B0AE0, 0x2D89B8} <= machine.instructions
        if name not in ("retail", "basic_realistic"):
            assert (tt.ARC_TABLE_VA, 4) in machine.reads
        output["profiles"][name] = {"xbe_sha256": sha(payload), "points": table,
                                    "cases": len(distances), "max_speed_error_yd_s": max_error,
                                    "all_returns_equal_float32_encoded_table": True,
                                    "short_return_bits_equal_retail": bits == short_bits,
                                    "table_reads": [[hex(a), n] for a, n in sorted(machine.reads)],
                                    "rows": rows}
        del machine
    profile = tt.ARC_BY_DISTANCE_LOBSPEED
    assert all(y0*x1 >= y1*x0 for (x0, y0), (x1, y1) in zip(profile[4:], profile[5:]))
    assert max(tt.GRAVITY_YD_S2 * (d/s)**2 / 8 for d, s in profile) < 20
    output["continuous_deep_hang_monotonic_40_80"] = True
    output["continuous_apex_bound_0_80_yd"] = 20
    output["retail_exception"] = "Retail hang drops from 1.0 s at 6 yd to 0.833333 s at 10 yd; preserved exactly."
    assert retail_path.read_bytes() == retail, "source changed"
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retail-xbe", required=True, type=Path)
    parser.add_argument("--disc", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prove(args.retail_xbe, args.disc)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"claim": result["claim"], "profiles": list(result["profiles"]),
                      "cases_per_profile": result["profiles"]["retail"]["cases"],
                      "disc_profile": result["disc"]["arc_table"]["label"] if result["disc"] else None,
                      "exact_reverts": result["exact_reverts"]}))


if __name__ == "__main__":
    main()
