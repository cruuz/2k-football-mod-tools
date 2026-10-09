"""Retail-free XEX transport, authored PPC decision, build and install tests."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from contextlib import ExitStack
from dataclasses import replace
import json
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
    struct.pack_into('<I', image, 0x3C, 0x80)
    struct.pack_into('<H', image, 0x86, 1)
    at = 0x98
    image[at:at + 8] = b'.XBMOVIE'
    struct.pack_into('<3I', image, at + 8, 12, 0x032D6600, 0x200)
    struct.pack_into('<I', image, at + 36, 0xC0000040)
    for site, block in ((p.HOOK, p.RETAIL_CAP), (p.QB_GATE, p.RETAIL_QB_GATE)):
        off = p.address(site, profile) - p.IMAGE_BASE
        image[off:off + len(block)] = block
    for site, word in p.PatchDocument(profile).original_words:
        struct.pack_into(">I", image, site - p.IMAGE_BASE, word)
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


def execute_feedback_leaf(document, state_word):
    """Retail-free, full-width ABI oracle for the emitted snapshot leaf."""
    rng = random.Random(76)
    regs = [rng.getrandbits(64) for _ in range(32)]
    fprs = [rng.random() for _ in range(32)]
    regs[10] = 0x200000
    fprs[28], fprs[18] = 0., 1.
    before, fbefore, cr = regs.copy(), fprs.copy(), 0x87654321
    initial_cr = cr
    pc = p.feedback_address(p.FEEDBACK_HOOK, document.profile)
    stop = pc + 4
    words = dict(document.words)
    for _ in range(12):
        if pc == stop:
            break
        w = words[pc]
        op = w >> 26
        nxt = pc + 4
        if op == 18:
            assert w & 3 == 0
            delta = w & 0x3FFFFFC
            nxt = pc + (delta - (1 << 26) if delta & (1 << 25) else delta)
        elif op == 32:
            assert w == 0x816A01A8 and regs[10] == 0x200000
            regs[11] = state_word
        elif op == 21:
            assert w == 0x556B577E
            regs[11] = (regs[11] >> 22) & 7
        elif op == 10:
            assert w == 0x2B0B0004
            nibble = 8 if regs[11] < 4 else 4 if regs[11] > 4 else 2
            cr = (cr & ~0xF0) | (nibble << 4)
        elif op == 16:
            assert w == 0x409A0008
            if not cr & 0x20:
                nxt = pc + 8
        elif op == 63:
            assert w in (0xFFC0E090, 0xFFC09090)
            fprs[30] = fprs[(w >> 11) & 31]
        else:
            raise AssertionError(f"Unexpected feedback instruction {w:08X}")
        pc = nxt
    assert pc == stop
    assert cr & ~0xF0 == initial_cr & ~0xF0
    assert all(regs[i] == before[i] for i in range(32) if i != 11)
    assert all(fprs[i] == fbefore[i] for i in range(32) if i != 30)
    return fprs[30]


def execute_move_leaf(document, check, record):
    """Independent full-width oracle for every move leaf and its ABI."""
    rng = random.Random(763)
    regs = [rng.getrandbits(64) for _ in range(32)]
    _, _, _, out, roster, player, _ = check
    regs[roster] = 0x200000
    if player is not None:
        regs[player] = 0x100000
    before, cr = regs.copy(), 0x87654321
    initial_cr = cr
    words = dict(document.words)
    pc = p.move_address(check, document.profile)
    stop = pc + 8
    for _ in range(30):
        if pc == stop:
            break
        w = words[pc]
        op, rs, ra = w >> 26, w >> 21 & 31, w >> 16 & 31
        nxt = pc + 4
        if op == 18:
            assert w & 3 == 0  # no LR/CTR changes
            delta = w & 0x3FFFFFC
            nxt = pc + (delta - (1 << 26) if delta & (1 << 25) else delta)
        elif op in (32, 34):
            addr = regs[ra] + (w & 65535)
            if addr == 0x100044:
                assert op == 32
                regs[rs] = 0x200000
            else:
                offset = addr - 0x200000
                assert 0 <= offset <= 44
                regs[rs] = int.from_bytes(record[offset:offset + (4 if op == 32 else 1)], "big")
        elif op == 21:
            assert w & 1 == 0  # CR0 preserved
            shift, mb, me = w >> 11 & 31, w >> 6 & 31, w >> 1 & 31
            value = regs[rs] & 0xFFFFFFFF
            rotated = ((value << shift) | (value >> ((32 - shift) % 32))) & 0xFFFFFFFF
            regs[ra] = rotated & sum(1 << (31 - bit) for bit in range(mb, me + 1))
        elif op == 10:
            assert w == 0x2B000000 | out << 16
            cr = (cr & ~0xF0) | ((2 if regs[out] == 0 else 4) << 4)
        elif op == 16:
            assert w >> 16 & 0x3FF == (4 << 5 | 26)
            if not cr & 0x20:
                nxt = pc + (w & 0xFFFC)
        elif op == 14:
            assert rs == out and ra == 0 and w & 65535 == 1
            regs[out] = 1
        else:
            raise AssertionError(f"Unexpected move instruction {w:08X}")
        pc = nxt
    assert pc == stop
    assert cr & ~0xF0 == initial_cr & ~0xF0
    assert all(regs[i] == before[i] for i in range(32) if i != out)
    return bool(regs[out])


class ChargeTests(unittest.TestCase):
    def test_move_leaf_ability_unions_all_bits_and_abi(self):
        specific_bits = (0, 3, 0, 3, 2, 1, 1, 2)
        for profile in p.PROFILES:
            doc = p.PatchDocument(profile)
            for check, specific in zip(p.MOVE_CHECKS, specific_bits):
                selected = {(36, specific), (44, 1), (44, 3 if check[-1] == "finesse" else 2)}
                for tier in (0, 2, 4, 6):
                    record = bytearray(0x150)
                    record[18] = tier
                    self.assertFalse(execute_move_leaf(doc, check, record))
                    for offset in range(23, 45):
                        for bit in range(8):
                            record[offset] = 1 << bit
                            self.assertEqual(execute_move_leaf(doc, check, record), (offset, bit) in selected,
                                             (profile.name, hex(check[0]), tier, offset, bit))
                            record[offset] = 0
                    for mask in range(16):
                        record[44] = mask
                        self.assertEqual(execute_move_leaf(doc, check, record),
                                         bool(mask & (0xA if check[-1] == "finesse" else 6)))

    def test_feedback_leaf_consumed_level_and_register_preservation(self):
        for profile in p.PROFILES:
            for state in range(8):
                for unrelated in (0, 0xFE3FFFFF, 0x12345678 & ~0x1C00000):
                    self.assertEqual(execute_feedback_leaf(p.PatchDocument(profile, revision=3),
                                                          unrelated | state << 22),
                                     1 if state == 4 else 0)

    def test_synthetic_xex_apply_revert_and_tamper_refusal(self):
        for profile in p.PROFILES:
            source = synthetic_xex(synthetic_image(profile))
            image, _ = decode_xex(source)
            doc = p.PatchDocument(profile, True)
            # Only the whole retail digest check is mocked. All site, bounds,
            # reservation, authored-byte and revert checks remain real.
            # A plain stub avoids Mock.call_args retaining every 54 MB tamper
            # image through the whole matrix.
            with patch.object(p, "check_image", new=lambda image: profile):
                self.assertEqual(p.apply_image(image, replace(doc, enabled=False)), image)
                changed = p.apply_image(image, doc)
                self.assertNotEqual(changed, image)
                self.assertEqual(p.revert_image(changed, doc), image)
                self.assertEqual(synthetic_xex(p.revert_image(changed, doc)), source)
                allowed = {a - p.IMAGE_BASE + byte for a, _ in doc.words for byte in range(4)}
                self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(image, changed)) if a != b))
                for address in (p.CAVE, p.CAVE_LIMIT - 1, p.address(p.HOOK + 8, profile),
                                p.address(p.QB_GATE + 12, profile),
                                *(a for a, _ in doc.original_words)):
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
            self.assertEqual(len(doc.words), 717)
            self.assertEqual(len(dict(doc.words)), len(doc.words))
            self.assertEqual(len(p.trampoline(profile)), 76)
            self.assertEqual(len(p.feedback_trampoline(profile)), 28)
            self.assertLessEqual(p.FEEDBACK_CAVE + len(p.feedback_trampoline(profile)), p.CAVE_LIMIT)
            self.assertFalse(set(dict(doc.words)) & set(dict(fourth.PatchDocument(profile).words)))
            other = situations.SituationPatch(profile, situations.encode_data({}))
            self.assertFalse(set(dict(doc.words)) & set(dict(other.words)))
            self.assertLess(p.CAVE_LIMIT, fetch.CAVE_START)
            for changed in (payload.replace(b'is_enabled = false', b'is_enabled = 1'),
                            payload.replace(b'0x84D0D100', b'0x84D0D104'),
                            payload + b'\n[[patch]]\nname="foreign"\n'):
                with self.assertRaises(p.ValidationError):
                    p.parse_payload(changed)

    def test_legacy_patch_remains_exactly_identifiable_for_upgrade_and_removal(self):
        for profile in p.PROFILES:
            for revision, enabled in ((r, e) for r in (1, 2, 3) for e in (False, True)):
                legacy = p.PatchDocument(profile, enabled, revision=revision)
                self.assertEqual(len(legacy.words), {1: 20, 2: 32, 3: 138}[revision])
                self.assertEqual(p.parse_payload(legacy.as_toml().encode()), legacy)
                self.assertEqual(p.canonical_payload(legacy.as_toml().encode()), (profile, enabled))
                self.assertNotEqual(legacy.as_toml(), p.PatchDocument(profile, enabled).as_toml())
                with self.assertRaises(p.ValidationError):
                    p.parse_payload(legacy.as_toml().encode().replace(b'0x84D0D100', b'0x84D0D104'))

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
            # A beta-75 install and cached launch copy must remain recognizable
            # so the new canonical patch can replace them without manual edits.
            installed = settings.patches_folder / p.FILENAME
            installed.parent.mkdir(parents=True, exist_ok=True)
            storage = root / "launch"
            (storage / "patches").mkdir(parents=True)
            for profile in p.PROFILES:
                for revision in (1, 2, 3):
                    legacy = p.PatchDocument(profile, True, revision).as_toml().encode()
                    output.write_bytes(legacy)
                    with self.assertRaisesRegex(ValueError, f"legacy revision {revision}"):
                        launcher.install_pass_fetch_patch(output, kind="charge_abilities", consent=True)
                    installed.write_bytes(legacy)
                    status = launcher.pass_fetch_status(kind="charge_abilities")["message"]
                    self.assertIn(f"revision {revision}", status)
                    self.assertIn("beta 75 feedback bug" if revision == 1 else
                                  "Finesse move qualification bug" if revision == 2 else
                                  "discharge lost during native charge cleanup", status)
                    (storage / "patches" / p.FILENAME).write_bytes(legacy)
                    p.write_patch(p.PatchDocument(profile, True), output)
                    launcher.install_pass_fetch_patch(output, kind="charge_abilities", consent=True)
                    launcher._sync_launch_patches(storage)
                    self.assertEqual((storage / "patches" / p.FILENAME).read_bytes(), output.read_bytes())
                    launcher.remove_pass_fetch_patch(kind="charge_abilities")
                    launcher._sync_launch_patches(storage)
                    self.assertFalse((storage / "patches" / p.FILENAME).exists())
                    installed.write_bytes(legacy)
                    launcher.remove_pass_fetch_patch(kind="charge_abilities")
                    self.assertFalse(installed.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
