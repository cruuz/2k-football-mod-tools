"""The PS2 exact-slot AUDO audio lane, end to end on a synthetic disc.

A real ``SLUS-20919`` image is 4.3 GB of someone else's game, so everything here
is generated: a ``/VC_20919`` pack holding AUDO chunks shaped exactly like the
disc's own, inside a structurally valid ISO9660 volume, patched with a tone this
file computes.  No game data is read and none is needed.

What the tests are actually for, in order of how much they would hurt if they
regressed:

* **A replacement must not move anything.**  The whole reason this lane can ride
  a fixed-allocation ISO writer is that ``video_bytes`` never changes, so the
  chunk after it keeps its offset and the ISO9660 tree keeps every extent.
  ``test_patch_changes_only_the_payload`` compares the two images byte by byte
  and asserts the difference set is exactly the slot.
* **The container's own description of the sound must survive.**  If the 0x20
  wrapper or the 8-word descriptor were rewritten, the file would still look
  fine and the game would read a wrong length.  Asserted directly.
* **Refusals must happen before the output exists.**  A half-written 4.3 GB
  image that looks plausible is worse than an error, so the refusal tests check
  the destination was never created.
* **The verifier must actually fail.**  A verifier that only ever passes proves
  nothing, so two mutations -- one inside the slot, one outside it -- are
  required to fail, with the reason named.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS = _REPO_ROOT / "tools"
for _entry in (str(_REPO_ROOT), str(_TOOLS)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import nfl2k5_ps2_audo_patch as patcher  # noqa: E402
import nfl2k5_ps2_audo_target_catalog as catalogue  # noqa: E402
import nfl2k5_ps2_audo_verify as verifier  # noqa: E402
import spu_adpcm  # noqa: E402

MONO_BLOCKS = 40
STEREO_BLOCKS = 60          # 30 per channel
MONO_RATE = 11025
STEREO_RATE = 22050


def _tone(frames: int, rate: int, hz: float, amplitude: int) -> list:
    import math
    return [int(round(amplitude * math.sin(2.0 * math.pi * hz * n / rate)))
            for n in range(frames)]


def _wav(planes, rate: int) -> bytes:
    channels = len(planes)
    frames = len(planes[0])
    interleaved = []
    for index in range(frames):
        for plane in planes:
            interleaved.append(plane[index])
    pcm = struct.pack("<%dh" % len(interleaved), *interleaved)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * channels * 2, channels * 2, 16)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WAVE" + body


def _synthetic_image() -> bytes:
    """Two entries: a mono slot and a duplicate-named pair, plus a stereo slot."""
    mono = spu_adpcm.encode([0] * (spu_adpcm.BLOCK_FRAMES * MONO_BLOCKS))
    stereo = (spu_adpcm.encode([0] * (spu_adpcm.BLOCK_FRAMES * (STEREO_BLOCKS // 2)))
              + spu_adpcm.encode([0] * (spu_adpcm.BLOCK_FRAMES * (STEREO_BLOCKS // 2))))
    return catalogue.build_disc([
        catalogue.build_audo_chunk("test_beep", 1, MONO_RATE, mono)
        + catalogue.build_audo_chunk("test_shared", 1, MONO_RATE, mono),
        catalogue.build_audo_chunk("test_shared", 1, MONO_RATE, mono)
        + catalogue.build_audo_chunk("test_pair", 2, STEREO_RATE, stereo),
    ])


class _Fixture(unittest.TestCase):
    """A generated disc, its catalogue and a well-formed replacement WAV."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "source.iso"
        self.source.write_bytes(_synthetic_image())
        self.catalog = catalogue.build(self.source)
        self.beep = catalogue.find_slot(self.catalog, "test_beep")
        self.pair = catalogue.find_slot(self.catalog, "test_pair")
        self.wav = self.root / "tone.wav"
        self.wav.write_bytes(
            _wav([_tone(spu_adpcm.BLOCK_FRAMES * 25, MONO_RATE, 440.0, 9000)], MONO_RATE))
        self.output = self.root / "out.iso"
        self.addCleanup(self._tmp.cleanup)

    def _patch(self, requests=None, output=None):
        requests = requests or [("test_beep", self.wav)]
        output = output or self.output
        prepared = patcher.plan(self.source, requests, self.catalog)
        return prepared, patcher.apply(prepared, self.source, output)


class CatalogueTests(_Fixture):
    def test_slots_are_found_with_their_descriptor_fields(self) -> None:
        slots = self.catalog["slots"]
        self.assertEqual(len(slots), 4)
        self.assertEqual([s["name"] for s in slots],
                         ["test_beep", "test_shared", "test_shared", "test_pair"])
        self.assertEqual(self.beep["channels"], 1)
        self.assertEqual(self.beep["sample_rate"], MONO_RATE)
        self.assertEqual(self.beep["video_bytes"], MONO_BLOCKS * spu_adpcm.BLOCK_BYTES)
        self.assertEqual(self.beep["max_frames"], MONO_BLOCKS * spu_adpcm.BLOCK_FRAMES)
        self.assertEqual(self.pair["channels"], 2)
        self.assertEqual(self.pair["per_channel_bytes"] * 2, self.pair["video_bytes"])

    def test_duplicate_names_are_marked_and_refused_as_selectors(self) -> None:
        shared = [s for s in self.catalog["slots"] if s["name"] == "test_shared"]
        self.assertEqual(len(shared), 2)
        self.assertTrue(all(not s["unique_name"] for s in shared))
        self.assertTrue(self.beep["unique_name"])
        with self.assertRaises(catalogue.CatalogError):
            catalogue.find_slot(self.catalog, "test_shared")
        # ...but the slot id always resolves.
        self.assertEqual(
            catalogue.find_slot(self.catalog, shared[1]["slot_id"])["slot_id"],
            shared[1]["slot_id"])


class PatchTests(_Fixture):
    def test_patch_changes_only_the_payload(self) -> None:
        prepared, receipt = self._patch()
        item = prepared["items"][0]
        before = self.source.read_bytes()
        after = self.output.read_bytes()
        self.assertEqual(len(before), len(after))
        differing = {i for i in range(len(before)) if before[i] != after[i]}
        low = item["iso_offset"]
        high = low + item["video_bytes"]
        self.assertTrue(differing, "the patch changed nothing at all")
        self.assertTrue(differing <= set(range(low, high)),
                        "bytes changed outside the slot payload")
        self.assertEqual(receipt["replacements"][0]["slot_id"], self.beep["slot_id"])

    def test_container_metadata_is_never_rewritten(self) -> None:
        prepared, _receipt = self._patch()
        item = prepared["items"][0]
        prefix = self.beep["system_bytes"] + 0x20
        start = item["iso_offset"] - prefix
        self.assertEqual(self.source.read_bytes()[start:start + prefix],
                         self.output.read_bytes()[start:start + prefix])

    def test_short_audio_is_padded_to_the_exact_slot(self) -> None:
        prepared, _receipt = self._patch()
        item = prepared["items"][0]
        self.assertEqual(len(item["_payload"]), self.beep["video_bytes"])
        self.assertEqual(item["blocks_written"], 25)
        self.assertEqual(item["pad_blocks"], MONO_BLOCKS - 25)
        report = spu_adpcm.validate_payload(item["_payload"])
        self.assertEqual(report["terminators"][0], 24)
        self.assertEqual(report["terminators"][-1], MONO_BLOCKS - 1)
        tail, _p1, _p2 = spu_adpcm.decode(item["_payload"][25 * spu_adpcm.BLOCK_BYTES:])
        self.assertEqual(set(tail), {0}, "the filler is not silent")

    def test_stereo_is_two_contiguous_halves(self) -> None:
        stereo_wav = self.root / "pair.wav"
        stereo_wav.write_bytes(_wav(
            [_tone(spu_adpcm.BLOCK_FRAMES * 20, STEREO_RATE, 300.0, 8000),
             _tone(spu_adpcm.BLOCK_FRAMES * 20, STEREO_RATE, 700.0, 8000)], STEREO_RATE))
        prepared, _receipt = self._patch([("test_pair", stereo_wav)])
        payload = prepared["items"][0]["_payload"]
        half = self.pair["per_channel_bytes"]
        self.assertEqual(len(payload), half * 2)
        for channel in (payload[:half], payload[half:]):
            report = spu_adpcm.validate_payload(channel)
            self.assertEqual(report["terminators"][0], 19)
            self.assertEqual(report["terminators"][-1], half // spu_adpcm.BLOCK_BYTES - 1)

    def test_a_rate_mismatch_is_resampled(self) -> None:
        other = self.root / "other-rate.wav"
        other.write_bytes(_wav([_tone(400, STEREO_RATE, 440.0, 9000)], STEREO_RATE))
        prepared = patcher.plan(self.source, [("test_beep", other)], self.catalog)
        item = prepared["items"][0]
        self.assertEqual(item["resampled_from"], STEREO_RATE)
        self.assertAlmostEqual(item["frames_written"], 200, delta=1)


class RefusalTests(_Fixture):
    def _assert_refused(self, requests, fragment: str) -> None:
        destination = self.root / "refused.iso"
        with self.assertRaises((patcher.PatchError, catalogue.CatalogError,
                                spu_adpcm.SpuAdpcmError)) as caught:
            prepared = patcher.plan(self.source, requests, self.catalog)
            patcher.apply(prepared, self.source, destination)
        self.assertIn(fragment, str(caught.exception))
        self.assertFalse(destination.exists(),
                         "a refusal left an output image behind")

    def test_over_length_audio_is_refused(self) -> None:
        long_wav = self.root / "long.wav"
        long_wav.write_bytes(
            _wav([_tone(self.beep["max_frames"] + 1, MONO_RATE, 440.0, 9000)], MONO_RATE))
        self._assert_refused([("test_beep", long_wav)], "never grows a slot")

    def test_a_channel_mismatch_is_refused(self) -> None:
        stereo_wav = self.root / "stereo.wav"
        stereo_wav.write_bytes(
            _wav([_tone(280, MONO_RATE, 440.0, 9000)] * 2, MONO_RATE))
        self._assert_refused([("test_beep", stereo_wav)], "supply mono audio")

    def test_a_malformed_wav_is_refused(self) -> None:
        bad = self.root / "bad.wav"
        bad.write_bytes(b"RIFF" + struct.pack("<I", 4) + b"WAVE")
        self._assert_refused([("test_beep", bad)], "too short")

    def test_a_wav_with_metadata_chunks_is_refused(self) -> None:
        raw = _wav([_tone(280, MONO_RATE, 440.0, 9000)], MONO_RATE)
        extra = b"LIST" + struct.pack("<I", 4) + b"INFO"
        tagged = (b"RIFF" + struct.pack("<I", len(raw) - 8 + len(extra))
                  + raw[8:] + extra)
        path = self.root / "tagged.wav"
        path.write_bytes(tagged)
        self._assert_refused([("test_beep", path)], "Remove metadata chunks")

    def test_eight_bit_pcm_is_refused(self) -> None:
        raw = bytearray(_wav([_tone(280, MONO_RATE, 440.0, 9000)], MONO_RATE))
        struct.pack_into("<H", raw, 34, 8)
        path = self.root / "eight.wav"
        path.write_bytes(bytes(raw))
        self._assert_refused([("test_beep", path)], "this writer takes 16-bit PCM")

    def test_a_duplicate_name_cannot_select_a_slot(self) -> None:
        self._assert_refused([("test_shared", self.wav)], "names 2 slots")

    def test_the_same_slot_twice_is_refused(self) -> None:
        self._assert_refused(
            [("test_beep", self.wav), (self.beep["slot_id"], self.wav)],
            "appears twice")


class VerifierTests(_Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.prepared, self.receipt = self._patch()
        self.item = self.receipt["replacements"][0]

    def test_a_clean_patch_verifies(self) -> None:
        result = verifier.verify(self.source, self.output, self.receipt)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["changed_outside_declared_spans"], 0)
        self.assertEqual(result["declared_slots"], 1)
        self.assertTrue(result["tree_identical"])
        self.assertEqual(result["slots"][0]["payload_bytes"], self.item["video_bytes"])

    def _mutate(self, offset: int, name: str) -> Path:
        data = bytearray(self.output.read_bytes())
        data[offset] ^= 0xFF
        path = self.root / name
        path.write_bytes(bytes(data))
        return path

    def test_a_byte_changed_outside_the_slot_fails(self) -> None:
        beyond = self.item["iso_offset"] + self.item["video_bytes"] + 16
        tampered = self._mutate(beyond, "outside.iso")
        with self.assertRaises(verifier.VerifyError) as caught:
            verifier.verify(self.source, tampered, self.receipt)
        self.assertIn("outside every declared slot", str(caught.exception))

    def test_a_byte_changed_inside_the_slot_fails(self) -> None:
        tampered = self._mutate(self.item["iso_offset"] + 7, "inside.iso")
        with self.assertRaises(verifier.VerifyError) as caught:
            verifier.verify(self.source, tampered, self.receipt)
        self.assertIn("not the one the receipt records", str(caught.exception))

    def test_a_rewritten_descriptor_fails(self) -> None:
        prefix_at = self.item["iso_offset"] - self.beep["system_bytes"] - 0x20
        tampered = self._mutate(prefix_at + 0x0C, "descriptor.iso")
        with self.assertRaises(verifier.VerifyError) as caught:
            verifier.verify(self.source, tampered, self.receipt)
        self.assertIn("outside every declared slot", str(caught.exception))

    def test_the_verifier_does_not_import_the_writer(self) -> None:
        source = (_TOOLS / "nfl2k5_ps2_audo_verify.py").read_text(encoding="utf-8")
        for forbidden in ("import nfl2k5_ps2_audo_patch", "import ps2_iso9660"):
            self.assertNotIn(forbidden, source,
                             "the verifier must re-derive, not reuse the writer's parser")


class ValidatorTests(unittest.TestCase):
    def test_every_selftest_passes(self) -> None:
        for tool in ("spu_adpcm.py", "nfl2k5_ps2_audo_target_catalog.py",
                     "nfl2k5_ps2_audo_patch.py", "nfl2k5_ps2_audo_verify.py"):
            with self.subTest(tool=tool):
                done = subprocess.run(
                    [sys.executable, str(_TOOLS / tool), "--selftest"],
                    capture_output=True, text=True, check=False)
                self.assertEqual(done.returncode, 0,
                                 f"{tool} --selftest failed:\n{done.stdout}\n{done.stderr}")
                self.assertIn("PASS", done.stdout)

    def test_the_committed_catalogue_is_well_formed(self) -> None:
        path = (_REPO_ROOT / "reports" / "gameplay_tuning"
                / "nfl2k5_ps2_audo_catalog.v1.json")
        if not path.is_file():
            self.skipTest("the disc catalogue has not been generated here")
        raw = path.read_bytes()
        self.assertNotIn(b"\r", raw, "the catalogue must be LF-only")
        catalog = json.loads(raw.decode("utf-8"))
        self.assertEqual(catalog["schema"], catalogue.SCHEMA)
        totals = catalog["totals"]
        self.assertEqual(totals["slots"], catalogue.EXPECTED_SLOT_COUNT)
        self.assertEqual(totals["unique_names"], catalogue.EXPECTED_UNIQUE_NAME_COUNT)
        self.assertEqual(totals["slots"], len(catalog["slots"]))
        self.assertEqual(totals["mono"] + totals["stereo"], totals["slots"])
        for slot in catalog["slots"]:
            self.assertEqual(slot["per_channel_bytes"] * slot["channels"],
                             slot["video_bytes"])
            self.assertEqual(slot["video_bytes"] % spu_adpcm.BLOCK_BYTES, 0)
            self.assertEqual(slot["max_frames"],
                             spu_adpcm.max_frames_for_bytes(slot["per_channel_bytes"]))
        # Retail-free: no payload or decoded digests may appear anywhere.
        for banned in ("payload_sha256", "decoded_sha256", "pcm_sha256"):
            self.assertNotIn(banned, raw.decode("utf-8"),
                             "the catalogue must not fingerprint retail audio")


if __name__ == "__main__":
    unittest.main()
