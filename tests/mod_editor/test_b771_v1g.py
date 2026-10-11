"""Team Needs native counts and the two shipped Unc Bowl uniform repairs."""
from __future__ import annotations
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77"), str(ROOT / "tools/b765")]
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_unc_bowl_uniforms as uniforms
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from nfl_txtr import parse_chunks, decode_chunk, parse_texture, minimum_vc_lz_overlap_scratch
import a5k_acceptance as acceptance
import v1g_repair as repair

PRIVATE = Path(os.environ.get("B771_V1G_SCRATCH", "/home/noah/2k-worktrees/.b77-scratch/b771-v1g"))


def fixture_scene():
    span = bytearray(21024)
    span[:32] = struct.pack("<4s7I", b"MRKS", 20992, 20992, 0, 0, 0, 0, 0)
    span[32 + 0x4FE2:32 + 0x4FF8] = "team_needs\0".encode("utf-16le")
    for at, identity in ((0x430, 0xAC689FAF), (0x940, 0x6FCA5DA8), (0x9D0, 0x44E70E6B)):
        struct.pack_into("<I", span, at + 32, identity)
    for at, old, _new, _label in pools.team_needs_scene_edits():
        span[32 + at:32 + at + len(old)] = old
    return bytes(span)


class OverviewTests(unittest.TestCase):
    def test_labels_hidden_pair_and_gap_closed_in_same_allocation(self):
        raw = fixture_scene()
        fixed, receipt = pools.apply_team_needs_scene(raw)
        self.assertEqual(len(fixed), len(raw))
        self.assertEqual(receipt["visible_pools"], 16)
        body = fixed[32:]
        self.assertEqual(body[0x171E:0x1732].decode("utf-16le"), "EDGE:\0LB:\0")
        self.assertEqual(struct.unpack_from("<I", body, 0xC14)[0], 0)
        for at in (0x950, 0x964, 0x978):
            self.assertEqual(struct.unpack_from("<f", body, at)[0], 0)
        for count, label in ((0xA24, 0xC64), (0xAB4, 0xCF4)):
            self.assertEqual(body[count:count + 4], body[label:label + 4])
        allowed = {32 + at + i for at, old, _new, _label in pools.team_needs_scene_edits() for i in range(len(old))}
        self.assertFalse({i for i, (a, b) in enumerate(zip(raw, fixed)) if a != b} - allowed)
        self.assertEqual(pools.apply_team_needs_scene(fixed)[0], fixed)

    def test_partial_foreign_and_binding_drift_refuse(self):
        raw = fixture_scene()
        for at in (0x434, 0x9D0, 0x171E, 0x950):
            bad = bytearray(raw)
            bad[32 + at] ^= 1
            with self.assertRaises(ValueError):
                pools.apply_team_needs_scene(bytes(bad))
        bad = bytearray(raw)
        at, _old, new, _label = pools.team_needs_scene_edits()[0]
        bad[32 + at:32 + at + len(new)] = new
        with self.assertRaises(ValueError):
            pools.apply_team_needs_scene(bytes(bad))

    def test_both_build_hooks_run_after_their_final_owners(self):
        source = (ROOT / "mod_editor/core/mod_build.py").read_text()
        self.assertGreater(source.index("overview_receipt = pools_final.apply_team_needs_image"),
                           source.index("scan = roster_scan.olb_filter_policy(target)"))
        self.assertGreater(source.index("uniforms_receipt = uniforms.apply_to_image"),
                           source.index("espn_receipt = espn.apply_to_image(target, loaded_espn25_plan)"))


@unittest.skipUnless((PRIVATE / "export/resources/06H5.IFF").exists(), "private v0.6 uniform inputs absent")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {name: (PRIVATE / "export/resources" / name).read_bytes() for name in uniforms.OWNED}
        cls.donor = (PRIVATE / "export/resources/22H0.IFF").read_bytes()
        cls.fixed = {"06H5.IFF": uniforms.finish_cincinnati(cls.raw["06H5.IFF"]),
                     "22A4.IFF": uniforms.finish_pittsburgh(cls.raw["22A4.IFF"], cls.donor)}

    def test_owned_hashes_replay_and_unowned_changes_compose(self):
        for name, raw in self.raw.items():
            spec = uniforms.validate_owned(name, raw)
            fixed = self.fixed[name]
            uniforms.validate_owned(name, fixed)
            allowed = {i for p in spec["spans"] for i in range(p["offset"], p["offset"] + p["length"])}
            self.assertFalse({i for i, (a, b) in enumerate(zip(raw, fixed)) if a != b} - allowed)
            replay = uniforms.finish_cincinnati(fixed) if name == "06H5.IFF" else uniforms.finish_pittsburgh(fixed, self.donor)
            self.assertEqual(replay, fixed)
            modified = bytearray(raw)
            modified[0x70] ^= 1  # an unrelated uniform header byte
            uniforms.validate_owned(name, bytes(modified))
            modified[spec["spans"][0]["offset"]] ^= 1
            with self.assertRaises(ValueError):
                uniforms.validate_owned(name, bytes(modified))
            with self.assertRaises(ValueError):
                uniforms.validate_owned("22H4.IFF", raw)

    def test_pittsburgh_all_ten_jersey_digits_match_donor_at_every_mip(self):
        fixed, old = self.fixed["22A4.IFF"], self.raw["22A4.IFF"]
        fc, oc, dc = parse_chunks(fixed), parse_chunks(old), parse_chunks(self.donor)
        for i in range(53):
            if 13 <= i < 23:
                acceptance.compare_texture_chunks(self.donor, dc[i], fixed, fc[i])
            elif oc[i].kind in ("TXTR", "TSET"):
                self.assertEqual(decode_chunk(old, oc[i])[0], decode_chunk(fixed, fc[i])[0])

    def test_cincinnati_palette_descriptors_other_textures_and_wet_pairs_preserved(self):
        old, fixed = self.raw["06H5.IFF"], self.fixed["06H5.IFF"]
        for oc, fc in zip(parse_chunks(old), parse_chunks(fixed)):
            if oc.kind not in ("TXTR", "TSET"):
                continue
            before, after = decode_chunk(old, oc)[0], decode_chunk(fixed, fc)[0]
            self.assertEqual((oc.system_bytes, oc.video_bytes), (fc.system_bytes, fc.video_bytes))
            self.assertEqual(before[:oc.system_bytes], after[:fc.system_bytes])
            if oc.index not in (2, *range(23, 33), 51):
                self.assertEqual(before, after)
            if oc.index in (2, 51):
                self.assertEqual(before[-2048:] if oc.index == 2 else before[-1024:],
                                 after[-2048:] if oc.index == 2 else after[-1024:])
        # Independent decoder checks width and black coverage, not polygon instructions.
        import numpy as np
        for label, raw in (("before", old), ("after", fixed)):
            c = parse_chunks(raw)[2]
            d = decode_chunk(raw, c)[0]
            t = acceptance.kits.audit.tset_texture(d, 0)
            pixels = np.frombuffer(acceptance.mip_pixels(d, c, t)[0], dtype=np.uint8).reshape(256, 512, 4)
            count = int((pixels[:, 111:174, :3].max(axis=2) < 50).sum())
            setattr(self, label + "_black", count)
        self.assertGreater(self.after_black, self.before_black * 2)
        for i in range(23, 33):
            c = parse_chunks(fixed)[i]
            d = decode_chunk(fixed, c)[0]
            t = parse_texture(d, c)
            self.assertEqual(t.name, "hn" + str(48 + i - 23))
            self.assertEqual((t.width, t.height, t.mip_levels), (32, 32, 3))
            pixels = acceptance.mip_pixels(d, c, t)[0]
            visible = [pixels[n:n + 3] for n in range(0, len(pixels), 4) if pixels[n + 3] > 128]
            self.assertTrue(visible)
            self.assertEqual(set(visible), {b"\0\0\0"})

    def test_every_native_wrapper_has_enough_in_place_decompression_scratch(self):
        for raw in self.fixed.values():
            for c in parse_chunks(raw):
                if c.kind not in ("TXTR", "TSET"):
                    continue
                d, info = decode_chunk(raw, c)
                stream = raw[c.offset + 32:c.offset + 32 + info.consumed_bytes]
                minimum = minimum_vc_lz_overlap_scratch(stream, c.stored_size, len(d))
                self.assertGreaterEqual(c.overlap_scratch_bytes, minimum)
                self.assertGreaterEqual(c.overlap_scratch_bytes, c.stored_size - len(stream))

    def test_actual_moment_selection_and_foreign_team_and_slot_refusal(self):
        raw = (PRIVATE / "situ.before.iff").read_bytes()
        self.assertTrue(uniforms.unc_bowl_uses_slots(raw))
        for field in (0x1C, 0x14, 0x58, 0x5C):
            bad = bytearray(raw)
            bad[32 + 0x44 + 50 * 0x6C + field] ^= 1
            self.assertFalse(uniforms.unc_bowl_uses_slots(bytes(bad)))

    def test_real_team_and_pending_counts_for_every_enum(self):
        import unicorn as u
        from unicorn import x86_const as r
        raw = (PRIVATE / "default.before.xbe").read_bytes()
        repair.xbe_check(raw)
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        uc.mem_map(0x10000, 0x1500000 - 0x10000)
        for section in XbeImage(raw).sections:
            if section.raw_size and section.start + section.raw_size <= 0x1500000:
                uc.mem_write(section.start, raw[section.raw:section.raw + section.raw_size])
        uc.mem_map(0x2000000, 0x10000)
        uc.mem_map(0x3000000, 0x10000)
        put = lambda at, value: uc.mem_write(at, struct.pack("<I", value))
        word = lambda at: struct.unpack("<I", uc.mem_read(at, 4))[0]
        team, stack, stop, player = 0x2000000, 0x3008000, 0x300F000, 0x2002000
        expected = {i: 0 if i == 10 else i % 3 + 1 for i in range(17)}
        pointers = []
        for enum, count in expected.items():
            for _ in range(count):
                pointers.append(player)
                uc.mem_write(player + 0x35, bytes([enum]))
                player += 0x54
        for i, ptr in enumerate(pointers):
            put(team + 4 * i, ptr)
        uc.mem_write(team + 0x11C, bytes([len(pointers)]))
        put(0xC8F7EC, team)
        put(0xC8F654, 2)
        for i, enum in enumerate((16, 11)):
            put(0xC8F658 + 4 * i, player)
            uc.mem_write(player + 0x35, bytes([enum]))
            expected[enum] += 1
            player += 0x54
        captured = []

        def hook(_uc, pc, _size, _data):
            if pc == 0x4A400:
                sp = uc.reg_read(r.UC_X86_REG_ESP)
                params = word(sp + 4)
                captured.append((word(params), word(params + 4)))
                # Only the text material formatter is supplied. Native team,
                # pending selection, max/target readers and arithmetic run.
                uc.reg_write(r.UC_X86_REG_EIP, word(sp))
                uc.reg_write(r.UC_X86_REG_ESP, sp + 8)

        uc.hook_add(u.UC_HOOK_CODE, hook)
        xbe = XbeImage(raw)
        maximum = struct.unpack("<17I", xbe.read(pools.ROSTER_MAXIMA_VA, 68))
        target = struct.unpack("<17I", xbe.read(pools.ROSTER_TARGETS_VA, 68))
        for enum in range(17):
            uc.mem_write(stack, struct.pack("<4I", stop, 0x2001000, 0, 0))
            uc.reg_write(r.UC_X86_REG_ESP, stack)
            uc.reg_write(r.UC_X86_REG_EDX, enum)
            uc.emu_start(0x319C20, stop, count=20000)
            self.assertEqual(captured[-1], (expected[enum], (maximum[enum] + target[enum]) // 2))
            self.assertEqual(uc.reg_read(r.UC_X86_REG_ESP), stack + 16)
        self.assertEqual(captured[10], (0, 0))
        self.assertEqual(captured[11][1], 6)
        self.assertEqual(captured[16][1], 5)


if __name__ == "__main__":
    unittest.main()
