"""Inline format, native transport, cold allocator relocation and refusals."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_save as save
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career as legacy
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, draft_save
from tests.nfl2k5_my_career_mode_fixture import Machine


def block_for(payload, index=0, token=1):
    doc = codec.decode(payload)
    player = doc.by_key["primary", index]
    p = player.offset
    b = bytearray(save.SIZE)
    b[:8] = save.MAGIC
    struct.pack_into("<HH", b, 8, 1, save.SIZE)
    b[16:32] = token.to_bytes(16, "little")
    struct.pack_into("<I", b, 32, index)
    b[36:40] = bytes((3, 0, 0, payload[p + 0x35]))
    struct.pack_into("<I", b, 40, 0)
    for field, stored in ((0, 44), (16, 48), (20, 52)):
        struct.pack_into("<I", b, stored, doc.rel(p + field) - doc.layout.root)
    b[56:60] = payload[p + 4:p + 8]
    struct.pack_into("<I", b, 60, save.word(payload, p + 0x18) & save.BIRTH_MASK)
    b[74] = 255
    return save.seal(b)


class FormatTests(unittest.TestCase):
    def test_append_preserves_every_native_byte_and_has_no_runtime_pointer(self):
        source = draft_save()
        block = block_for(source)
        out, receipt = save.append(source, block)
        self.assertEqual(out[:-128], source)
        self.assertEqual(len(out), 720172)
        self.assertEqual(save.read(out), block)
        self.assertEqual(receipt["changed_bytes"], 128)
        self.assertEqual(save.append(out, block)[1]["changed_bytes"], 0)
        runtime = save.to_runtime(block)
        self.assertEqual(save.from_runtime(runtime), block)
        self.assertEqual(runtime[60:64], bytes(4))

    def test_corrupt_unknown_noncanonical_and_mismatched_identity_refuse(self):
        source = draft_save()
        block = block_for(source)
        for at in (0, 8, 12, 16, 32, 37, 38, 39, 44, 64, 72, 73, 75, 80, 82, 84, 127):
            bad = bytearray(block)
            bad[at] ^= 255
            with self.subTest(at=at), self.assertRaises(save.CareerSaveError):
                save.read(source + bytes(bad))
        for at, value in ((32, 4000), (56, save.word(block, 56) ^ 1), (60, save.word(block, 60) ^ 0x1000)):
            bad = bytearray(block)
            struct.pack_into("<I", bad, at, value)
            with self.subTest(identity=at), self.assertRaises(save.CareerSaveError):
                save.read(source + save.seal(bad))
        for n in (0, 720043, 720045, 720171, 720173):
            with self.subTest(size=n), self.assertRaises(save.CareerSaveError):
                save.read((source + block + b"\0")[:n])


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA retail XBE and Unicorn are required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE pin differs")
        cls.payload, cls.receipt = mode.apply(cls.retail)
        union = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        allocated = mode.space.apply(cls.retail, union, scaleout=True)[0]
        cls.second = mode.apply(allocated)[0]

    def test_compact_native_validation_matches_host_and_pointer_free_codec(self):
        block = block_for(draft_save())
        with Machine(self.payload) as m:
            m.uc.mem_write(m.SAVE, block)
            self.assertEqual(m.call("inline_valid", ecx=m.SAVE, edx=0x91000), 1)
            m.uc.mem_write(m.state, save.to_runtime(block))
            m.call("inline_encode", ecx=m.OUT)
            self.assertEqual(m.uc.mem_read(m.OUT, 128), block)
            for at in (0, 8, 12, 32, 37, 38, 39, 44, 64, 72, 73, 74, 75, 80, 82, 84, 127):
                bad = bytearray(block)
                bad[at] ^= 255
                bad = save.seal(bad)
                m.uc.mem_write(m.SAVE, bad)
                try:
                    save.validate(bad, arena_size=0x91000)
                    expected = 1
                except save.CareerSaveError:
                    expected = 0
                self.assertEqual(m.call("inline_valid", ecx=m.SAVE, edx=0x91000), expected, at)

    def test_native_all_serializers_and_cold_reload_on_two_builds(self):
        source = draft_save()
        careers = [source + block_for(source, i, i + 1) for i in (0, 1)]
        self.assertNotEqual(legacy.allocations(self.payload), legacy.allocations(self.second))
        for payload in (self.payload, self.second):
            with Machine(payload) as m:
                for career in careers:
                    m.native_load(career)
                    self.assertEqual(m.get(m.state + 2580), 2)
                    self.assertEqual(m.get(m.state + 28), save.word(career[-128:], 32))
                    self.assertEqual(m.get(m.state + 2576), 0)
                    self.assertEqual(m.uc.mem_read(m.SAVE, len(career)), career)
                    output = m.native_save()
                    self.assertIsNotNone(output)
                    self.assertEqual(len(output), len(career))
                    self.assertEqual(save.read(output)[16:32], career[-112:-96])
                    # A completely new CPU instance and different code/RW layout.
                    other = self.second if payload == self.payload else self.payload
                    with Machine(other) as cold:
                        cold.native_load(output)
                        self.assertEqual(cold.get(cold.state + 28), m.get(m.state + 28))
                        self.assertEqual(cold.uc.mem_read(cold.state + 40, 16), m.uc.mem_read(m.state + 40, 16))
                        self.assertEqual(cold.call("primary"), cold.get(cold.root + 4) + 84 * m.get(m.state + 28))

    def test_native_signing_includes_footer_and_extra_write_errors(self):
        from mod_editor.core import nfl2k5_save_writer as writer
        source = draft_save()
        with Machine(self.payload) as m:
            m.native_load(source + block_for(source))
            output = m.native_save()
            extra = m.native_signature(output)
            key = writer.derive_sig_key(XBE.read_bytes())
            self.assertTrue(writer.verify_extra(key, output, extra))
            self.assertFalse(writer.verify_extra(key, output[:-128], extra))
            damaged = output[:-1] + bytes((output[-1] ^ 1,))
            self.assertFalse(writer.verify_extra(key, damaged, extra))
            self.assertIsNone(m.native_signature(output, fail_write=True))

    def test_failed_foreign_and_short_load_cannot_retain_previous_identity(self):
        source = draft_save()
        career = source + block_for(source)
        with Machine(self.payload) as m:
            for bad, read_ok in ((career, False), (source, True), (career[:-1], True),
                                 (career[:-1] + b"\xff", True)):
                m.native_load(career)
                m.native_load(bad, read_ok=read_ok)
                self.assertEqual(m.get(m.state), 0)
                self.assertEqual(m.get(m.state + 2564), 0)
                self.assertEqual(m.get(m.state + 2568), 0)

    def test_ordinary_franchise_remains_native_sized_and_cancel_writes_nothing(self):
        with Machine(self.payload) as m:
            m.native_load(draft_save(), requested=False)
            self.assertEqual(m.get(m.state), 0)
            self.assertEqual(len(m.native_save()), 720044)
            self.assertIsNone(m.native_save(accepted=False))
            self.assertIsNone(m.native_save(allocated=False))

    def test_replay_receipt_and_foreign_hooks_refuse_before_mutation(self):
        self.assertEqual(mode.status(self.payload), "applied")
        self.assertEqual(mode.apply(self.payload)[0], self.payload)
        self.assertEqual(mode.apply(self.payload)[1]["changed_bytes"], 0)
        self.assertEqual(self.receipt["executable_seed_bytes"], 0)
        self.assertEqual(self.receipt["journal_files"], 0)
        image = XbeImage(self.payload)
        for name, va, before, after in mode.sites(*[a["va"] for a in legacy.allocations(self.payload)]):
            bad = bytearray(self.payload)
            at = mode.rdata.offset_of(self.payload, va)
            bad[at:at + len(before)] = before
            frozen = bytes(bad)
            with self.subTest(name=name), self.assertRaises(ValueError):
                mode.apply(frozen)
            self.assertEqual(bytes(bad), frozen)


if __name__ == "__main__":
    unittest.main()
