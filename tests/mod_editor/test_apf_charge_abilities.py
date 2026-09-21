"""Retail-free XEX transport, authored PPC decision, build and install tests."""
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import apf2k8_charge_abilities as p
from mod_editor.core.apf2k8_xex import decode_xex
from mod_editor.apf_studio.build import ApfBuildOptions, ApfBuildService
from mod_editor.apf_studio.launcher import XeniaLauncher, XeniaSettings


def synthetic_image(profile):
    image = bytearray(p.IMAGE_SIZE)
    image[:2] = b"MZ"
    for site, block in ((p.HOOK, p.RETAIL_CAP), (p.QB_GATE, p.RETAIL_QB_GATE)):
        off = p.address(site, profile) - p.IMAGE_BASE
        image[off:off + len(block)] = block
    return bytes(image)


def synthetic_xex(image):
    header = bytearray(0x400)
    struct.pack_into(">6I", header, 0, 0x58455832, 1, len(header), 0, 0x80, 1)
    struct.pack_into(">II", header, 24, 0x3FF, 0x300)
    struct.pack_into(">I", header, 0x84, len(image))
    struct.pack_into(">IHH", header, 0x300, 8, 0, 0)
    return bytes(header) + image


def execute_leaf(document, record):
    """Independent 64-bit instruction oracle; refuses any unreviewed opcode."""
    rng = random.Random(75)
    regs = [rng.getrandbits(64) for _ in range(32)]
    regs[29] = 0x100000
    before, cr = regs.copy(), 0x87654321
    memory = {0x100044: 0x200000}
    memory.update({0x200000 + i: int.from_bytes(record[i:i + 4], "big") for i in (36, 40, 44)})
    words = dict(document.words)
    pc = p.address(p.HOOK, document.profile)
    initial_cr = cr
    for _ in range(25):
        if pc == p.address(p.RESUME, document.profile):
            break
        w = words[pc]
        op, rt, ra = w >> 26, w >> 21 & 31, w >> 16 & 31
        nxt = pc + 4
        if op == 18:
            assert w & 3 == 0
            delta = w & 0x3FFFFFC
            nxt = pc + (delta - (1 << 26) if delta & (1 << 25) else delta)
        elif op == 32:
            assert rt == 11
            regs[rt] = memory[(regs[ra] + (w & 65535)) & 0xFFFFFFFF]
        elif op == 21:
            assert (w >> 11 & 31) == 0 and w & 1 == 0
            mb, me = w >> 6 & 31, w >> 1 & 31
            mask = sum(1 << (31 - bit) for bit in range(mb, me + 1))
            regs[ra] = regs[rt] & mask
        elif op == 10:
            assert w == 0x2B0B0000
            cr = (cr & ~0xF0) | ((2 if regs[11] == 0 else 4) << 4)
        elif op == 16:
            assert w >> 16 & 0x3FF == (4 << 5 | 26)  # bne cr6
            if not (cr & 0x20):
                nxt = pc + (w & 0xFFFC)
        elif op == 14:
            assert rt == 27 and ra == 0 and w & 65535 in (0, 1)
            regs[27] = w & 65535
        else:
            raise AssertionError(f"Unexpected leaf instruction {w:08X}")
        pc = nxt
    assert pc == p.address(p.RESUME, document.profile)
    assert cr & ~0xF0 == initial_cr & ~0xF0
    assert all(regs[i] == before[i] for i in range(32) if i not in (11, 27))
    return 1 + regs[27]


class ChargeTests(unittest.TestCase):
    def test_synthetic_xex_apply_revert_and_tamper_refusal(self):
        for profile in p.PROFILES:
            source = synthetic_xex(synthetic_image(profile))
            image, _ = decode_xex(source)
            doc = p.PatchDocument(profile, True)
            # Only the whole retail digest check is mocked. All site, bounds,
            # reservation, authored-byte and revert checks remain real.
            with patch.object(p, "check_image", return_value=profile):
                self.assertEqual(p.apply_image(image, replace(doc, enabled=False)), image)
                changed = p.apply_image(image, doc)
                self.assertNotEqual(changed, image)
                self.assertEqual(p.revert_image(changed, doc), image)
                self.assertEqual(synthetic_xex(p.revert_image(changed, doc)), source)
                allowed = {a - p.IMAGE_BASE + byte for a, _ in doc.words for byte in range(4)}
                self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(image, changed)) if a != b))
                for address in (p.CAVE, p.CAVE_LIMIT - 1, p.address(p.HOOK + 8, profile), p.address(p.QB_GATE + 12, profile)):
                    broken = bytearray(image)
                    broken[address - p.IMAGE_BASE] ^= 1
                    with self.assertRaises(p.ValidationError):
                        p.apply_image(broken, doc)
                broken = bytearray(changed)
                broken[p.CAVE - p.IMAGE_BASE] ^= 1
                with self.assertRaises(p.ValidationError):
                    p.revert_image(broken, doc)
            with self.assertRaises(p.ValidationError):
                p.apply_image(image, doc)  # Synthetic digest is never accepted in production.

    def test_emitted_decision_table_all_bits_and_abi(self):
        from mod_editor.apf_studio.save_roster_players import _ABILITY_COORDINATES
        self.assertTrue(set(p.CHARGED_ABILITIES) <= set(_ABILITY_COORDINATES))
        chosen = {(offset, bit) for _, offset, bit in p.CHARGED_ABILITIES}
        for profile in p.PROFILES:
            doc = p.PatchDocument(profile)
            self.assertFalse(doc.enabled)
            for tier in (0, 2, 4, 6):
                record = bytearray(0x150)
                record[18] = tier
                self.assertEqual(execute_leaf(doc, record), 1)
                for offset in range(23, 45):
                    for bit in range(8):
                        record[offset] = 1 << bit
                        expected = 2 if (offset, bit) in chosen else 1
                        self.assertEqual(execute_leaf(doc, record), expected)
                        self.assertEqual(p.maximum_charge(record), expected)
                        record[offset] = 0

    def test_canonical_payload_and_patch_composition(self):
        from mod_editor.core import apf2k8_fourth_down as fourth, apf2k8_situation_mask as situations
        from mod_editor.core import apf2k8_playcall_patch as fetch
        for profile in p.PROFILES:
            doc = p.PatchDocument(profile)
            payload = doc.as_toml().encode()
            self.assertEqual(p.parse_payload(payload), doc)
            self.assertEqual(len(doc.words), 20)
            self.assertEqual(len(p.trampoline(profile)), 76)
            self.assertFalse(set(dict(doc.words)) & set(dict(fourth.PatchDocument(profile).words)))
            other = situations.SituationPatch(profile, situations.encode_data({}))
            self.assertFalse(set(dict(doc.words)) & set(dict(other.words)))
            self.assertLess(p.CAVE_LIMIT, fetch.CAVE_START)
            for changed in (payload.replace(b'is_enabled = false', b'is_enabled = 1'),
                            payload.replace(b'0x84D0D100', b'0x84D0D104'),
                            payload + b'\n[[patch]]\nname="foreign"\n'):
                with self.assertRaises(p.ValidationError):
                    p.parse_payload(changed)

    def test_build_plan_emits_receipts_only_when_enabled(self):
        from tests.mod_editor import test_apf_build_raw_span_overlays as fixture
        self.assertFalse(ApfBuildOptions().charge_abilities)
        with self.assertRaises(ValueError):
            ApfBuildOptions(charge_abilities=1)
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            game = root / "source"
            game.mkdir()
            source = fixture._source(game)
            tree = fixture._complete_tree(game)
            stack.enter_context(patch("mod_editor.apf_studio.build.EXPECTED_TREE", tree))
            stack.enter_context(patch("mod_editor.apf_studio.build.EXPECTED_0A_SHA256", source.source_sha256))
            stack.enter_context(patch("mod_editor.apf_studio.build.apf_outer.parse_archive", side_effect=fixture._archive))
            stack.enter_context(patch("mod_editor.apf_studio.build.disc_book_identity_report", return_value={"synthetic": True}))
            for enabled in (False, True):
                output = root / str(enabled)
                receipt = ApfBuildService(source).build((), output, options=ApfBuildOptions(enabled))
                report = json.loads(receipt.manifest.read_text())
                self.assertEqual(report["build_options"]["charge_abilities"], enabled)
                self.assertEqual("charge_abilities" in report, enabled)
                self.assertEqual((output / "default.xex").read_bytes(), (game / "default.xex").read_bytes())
                files = list(output.glob("*charge-abilities-*.patch.toml"))
                self.assertEqual(len(files), 2 if enabled else 0)
                for path in files:
                    self.assertTrue(p.parse_payload(path.read_bytes()).enabled)
                    self.assertTrue(path.with_suffix(path.suffix + ".receipt.json").exists())

    def test_install_sync_and_exact_removal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "xenia_edge"
            exe.write_bytes(b"authored")
            exe.chmod(0o755)
            settings = XeniaSettings(root / "settings.json")
            settings.configure(exe)
            launcher = XeniaLauncher(settings, root / "data")
            output = root / p.FILENAME
            p.write_patch(p.PatchDocument(p.PROFILES[0]), output)
            with self.assertRaisesRegex(ValueError, "disabled"):
                launcher.install_pass_fetch_patch(output, kind="charge_abilities", consent=True)
            p.write_patch(p.PatchDocument(p.PROFILES[0], True), output)
            launcher.install_pass_fetch_patch(output, kind="charge_abilities", consent=True)
            storage = root / "launch"
            launcher._sync_launch_patches(storage)
            self.assertEqual((storage / "patches" / p.FILENAME).read_bytes(), output.read_bytes())
            launcher.remove_pass_fetch_patch(kind="charge_abilities")
            launcher._sync_launch_patches(storage)
            self.assertFalse((storage / "patches" / p.FILENAME).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
