"""The minimum-cost H7A encoder must stay linear-ish on repetitive data.

The first version of ``tools/apf_h7a_optimal.c`` walked its hash chain starting
from ``head[hash]``, the newest position with that key anywhere in the file. The
backward dynamic-programming pass runs from the end down, so for most positions
that chain begins *above* the current one, and the loop skipped those with a
bare ``continue``. Skipped links never reached the ``MAX_CANDIDATES`` counter, so
the cap did not bound the walk at all.

That only shows up on the data the encoder exists for. Texture blocks are highly
repetitive -- one 3-byte key such as three zero bytes covers a large share of all
positions -- so the chain for that key is enormous and the walk becomes
quadratic. The 1.44 MB ``endzone_l0`` block ran for over six minutes without
finishing and, because ``compress_h7a_best`` allowed a 900-second subprocess, it
silently turned the test suite into something that appeared to hang.

The fix records, for each position, the newest earlier position sharing its key,
so every visited link is a legal candidate and the cap applies. This pins the
consequence rather than the implementation: a pathological input has to encode
quickly and still round-trip. A return of the quadratic walk fails on time.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import time
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import apf_field_art_patch as fa  # noqa: E402
import apf_inner  # noqa: E402


SHIFT = 9

#: Worst case for the old walk: a single 3-byte key at every position, so the
#: chain is as long as the input.  Small enough that even a slow-but-linear
#: encoder finishes instantly, and large enough that a quadratic one cannot.
PATHOLOGICAL = bytes(256 * 1024)

#: Long runs broken by rare noise, which is what flat field-art colour looks
#: like after Xenos tiling.
def _mostly_flat(size: int = 256 * 1024) -> bytes:
    body = bytearray(size)
    for index in range(0, size, 4096):
        body[index] = 0xA5
        body[index + 1] = 0x5A
    return bytes(body)


class OptimalEncoderIsBoundedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.binary = fa._optimal_binary()
        if cls.binary is None:
            raise unittest.SkipTest(
                "reviewed Linux x86-64 optimal-encoder helper is unavailable"
            )

    def _encode(self, payload: bytes) -> tuple[bytes, float]:
        started = time.monotonic()
        finished = subprocess.run(
            [str(self.binary), str(SHIFT)],
            input=payload,
            capture_output=True,
            timeout=120,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(finished.returncode, 0, finished.stderr[:400])
        return finished.stdout, elapsed

    def test_an_all_one_key_block_encodes_quickly_and_round_trips(self) -> None:
        encoded, elapsed = self._encode(PATHOLOGICAL)
        self.assertEqual(
            apf_inner.decompress_h7a(encoded, len(PATHOLOGICAL), SHIFT), PATHOLOGICAL
        )
        # The old walk did not finish this in six minutes.  Twenty seconds leaves
        # generous headroom on slow hardware while still failing a quadratic walk
        # by orders of magnitude.
        self.assertLess(
            elapsed, 20.0,
            f"encoding {len(PATHOLOGICAL):,} bytes of one repeated key took "
            f"{elapsed:.1f}s; the candidate walk is unbounded again",
        )

    def test_mostly_flat_texture_data_encodes_quickly_and_round_trips(self) -> None:
        payload = _mostly_flat()
        encoded, elapsed = self._encode(payload)
        self.assertEqual(
            apf_inner.decompress_h7a(encoded, len(payload), SHIFT), payload
        )
        self.assertLess(elapsed, 20.0, f"took {elapsed:.1f}s")

    def test_the_result_never_loses_to_greedy(self) -> None:
        """``compress_h7a_best`` promises the smaller of the two parses."""

        payload = _mostly_flat(64 * 1024)
        greedy = fa.compress_h7a(payload, SHIFT)
        best = fa.compress_h7a_best(payload, SHIFT)
        self.assertLessEqual(len(best), len(greedy))
        self.assertEqual(
            apf_inner.decompress_h7a(best, len(payload), SHIFT), payload
        )

    def test_no_match_is_emitted_with_length_over_distance(self) -> None:
        """The no-overlap rule the speckle bug proved still has to hold.

        A decoded reference whose length exceeds its distance reads bytes this
        stream has not written yet.  APF's decoder tolerates it; the GPU output
        did not, which is what the crest speckle was.
        """

        payload = _mostly_flat(64 * 1024)
        encoded, _ = self._encode(payload)
        at = 0
        while at < len(encoded):
            descriptor = encoded[at]
            at += 1
            for bit in range(8):
                if at >= len(encoded):
                    break
                if descriptor & (1 << bit):
                    word = int.from_bytes(encoded[at:at + 2], "big")
                    at += 2
                    distance = word & ((1 << SHIFT) - 1)
                    length = (word >> SHIFT) + 3
                    self.assertLessEqual(
                        length, distance,
                        f"overlapping match: length {length} > distance {distance}",
                    )
                else:
                    at += 1


if __name__ == "__main__":
    unittest.main()
