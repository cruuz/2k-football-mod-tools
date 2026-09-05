"""The pure-Python XXH3-64 that PCSX2 replacement filenames are made of.

Three independent levels of proof, strongest last:

1. **Vectors.** xxHash's own test buffer at thirteen lengths, one per branch of
   the dispatcher, recorded in the module.
2. **The C library.** When ``xxhash`` happens to be importable, every length
   from 0 to 299 plus a handful of long ones, at three seeds, must agree.
   Skipped -- not failed -- when the package is absent, because nothing this
   repository ships requires it.
3. **The disc oracle.** 120,779 textures off the retail ``SLUS-20919`` image
   produce 1.2 million hashes that pcsx2-VR's own ``xxhash.h`` already
   computed during the hop-1 research. Every one must reproduce. That run needs
   the retail image and the recorded results, so it is gated on
   ``NFL2K5_PS2_ISO`` and ``NFL2K5_HOP1_RESULTS`` and skips cleanly without
   them -- exactly like the ISO9660 conformance suite next door.

Nothing here is retail-derived: the vectors are synthetic and the oracle
compares hashes to hashes.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import xxh3  # noqa: E402

_NFL2K5_PS2_ISO = os.environ.get("NFL2K5_PS2_ISO")
_HOP1_RESULTS = os.environ.get("NFL2K5_HOP1_RESULTS")

# XXH3_kSecret is the one constant the whole algorithm hangs on; a single
# transposed byte would still hash, just not the way PCSX2 does.
_KSECRET_SHA256 = "2cf2f88bf9b71283059b6df53e5bcde20adbfd9e8d6ce2c1ab106262bb283bed"


class ConstantTests(unittest.TestCase):
    def test_the_default_secret_is_the_one_pcsx2_vendors(self) -> None:
        self.assertEqual(len(xxh3.KSECRET), 192)
        self.assertEqual(hashlib.sha256(xxh3.KSECRET).hexdigest(), _KSECRET_SHA256)

    def test_the_primes_are_the_published_ones(self) -> None:
        self.assertEqual(xxh3.PRIME64_1, 0x9E3779B185EBCA87)
        self.assertEqual(xxh3.PRIME64_2, 0xC2B2AE3D27D4EB4F)
        self.assertEqual(xxh3.PRIME_MX1, 0x165667919E3779F9)
        self.assertEqual(xxh3.PRIME_MX2, 0x9FB21C651E98DF25)


class VectorTests(unittest.TestCase):
    def test_every_recorded_vector_reproduces(self) -> None:
        for length, expected in xxh3._VECTORS:
            payload = xxh3._sanity_buffer(length)
            self.assertEqual(len(payload), length)
            self.assertEqual(
                xxh3.xxh3_64_python(payload), expected,
                "XXH3-64 of the %d-byte sanity buffer" % length)

    def test_the_vectors_cover_every_branch_of_the_dispatcher(self) -> None:
        lengths = sorted(length for length, _ in xxh3._VECTORS)
        buckets = set()
        for length in lengths:
            if length == 0:
                buckets.add("0")
            elif length <= 3:
                buckets.add("1-3")
            elif length <= 8:
                buckets.add("4-8")
            elif length <= 16:
                buckets.add("9-16")
            elif length <= 128:
                buckets.add("17-128")
            elif length <= 240:
                buckets.add("129-240")
            else:
                buckets.add("long")
        self.assertEqual(
            buckets,
            {"0", "1-3", "4-8", "9-16", "17-128", "129-240", "long"})

    def test_the_hex_form_is_unpadded_lower_case(self) -> None:
        # PCSX2 prints the hash with %llx, so a hash with leading zero nibbles
        # produces a *shorter* filename field. Zero-padding it would name a
        # file the emulator never looks for.
        self.assertEqual(xxh3.xxh3_64_hex(b""), "%x" % xxh3.xxh3_64(b""))
        self.assertNotIn("X", xxh3.xxh3_64_hex(b"abc").upper().replace("X", ""))
        self.assertEqual(xxh3.xxh3_64_hex(b"abc"), xxh3.xxh3_64_hex(b"abc").lower())


class DispatcherTests(unittest.TestCase):
    def test_hashing_is_stable_across_bytes_bytearray_and_memoryview(self) -> None:
        payload = xxh3._sanity_buffer(517)
        expected = xxh3.xxh3_64_python(payload)
        self.assertEqual(xxh3.xxh3_64_python(bytearray(payload)), expected)
        self.assertEqual(xxh3.xxh3_64_python(memoryview(payload)), expected)

    def test_a_non_bytes_argument_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            xxh3.xxh3_64_python("not bytes")

    def test_the_seed_changes_the_digest_in_every_length_class(self) -> None:
        for length in (0, 2, 6, 13, 64, 200, 900):
            payload = xxh3._sanity_buffer(length)
            self.assertNotEqual(xxh3.xxh3_64_python(payload, 0),
                                xxh3.xxh3_64_python(payload, 1),
                                "seed ignored at length %d" % length)

    def test_the_block_boundary_lengths_are_all_distinct(self) -> None:
        # 1024 bytes is exactly one accumulate block; the neighbours exercise
        # the partial-block and final-stripe paths that follow it.
        digests = {length: xxh3.xxh3_64_python(xxh3._sanity_buffer(length))
                   for length in (240, 241, 1023, 1024, 1025, 2047, 2048, 2049)}
        self.assertEqual(len(set(digests.values())), len(digests))


@unittest.skipUnless(xxh3.ACCELERATED, "the xxhash C extension is not installed")
class AcceleratorAgreementTests(unittest.TestCase):
    """When the optional accelerator is present it must be indistinguishable."""

    def test_every_length_to_300_agrees_at_three_seeds(self) -> None:
        rng = random.Random(20260904)
        native = xxh3._xxh3_64_native
        mismatches = []
        for length in list(range(0, 300)) + [512, 1023, 1024, 1025, 4096, 65536]:
            payload = bytes(rng.randrange(256) for _ in range(length))
            for seed in (0, 1, 0xDEADBEEFCAFEF00D):
                if xxh3.xxh3_64_python(payload, seed) != native(payload, seed):
                    mismatches.append((length, seed))
        self.assertEqual(mismatches, [])

    def test_the_public_entry_point_uses_the_accelerator(self) -> None:
        self.assertEqual(xxh3.accelerator_name(), "xxhash")
        payload = xxh3._sanity_buffer(4096)
        self.assertEqual(xxh3.xxh3_64(payload), xxh3.xxh3_64_python(payload))


class SelfTestTests(unittest.TestCase):
    def test_the_module_selftest_passes(self) -> None:
        import io

        buffer = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = buffer
        try:
            code = xxh3._selftest()
        finally:
            sys.stdout = real_stdout
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("vectors: %d/%d" % (len(xxh3._VECTORS), len(xxh3._VECTORS)),
                      buffer.getvalue())


@unittest.skipUnless(_NFL2K5_PS2_ISO and _HOP1_RESULTS,
                     "set NFL2K5_PS2_ISO and NFL2K5_HOP1_RESULTS to run the "
                     "1.2M-hash disc oracle")
class DiscOracleTests(unittest.TestCase):
    """Every hash pcsx2-VR's own xxhash.h produced from the disc must reproduce.

    This is the acceptance test the manifest rests on: if one texture in
    120,779 hashed differently, the manifest would name a file PCSX2 never
    looks for, and nothing downstream would notice.
    """

    def test_the_whole_disc_reproduces(self) -> None:
        os.environ["XXH3_PURE_PYTHON"] = "1"        # prove the shipped path
        import importlib

        importlib.reload(xxh3)
        try:
            self.assertFalse(xxh3.ACCELERATED)
            import nfl2k5_ps2_texture_map as mapper

            importlib.reload(mapper)
            report = mapper.oracle(_NFL2K5_PS2_ISO, _HOP1_RESULTS,
                                   jobs=0, limit=0, progress=None)
        finally:
            os.environ.pop("XXH3_PURE_PYTHON", None)
            importlib.reload(xxh3)
        self.assertEqual(report["records_missing"], 0)
        self.assertEqual(report["hashes_matched"], report["hashes_checked"],
                         report["mismatch_examples"])
        self.assertGreaterEqual(report["hashes_checked"], 1_201_117)
        self.assertEqual(report["records_reproduced"], 120_779)


if __name__ == "__main__":
    unittest.main()
