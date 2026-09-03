"""Retail-free tests for tools/nfl2k5_commentary_swap.py.

A 160 KiB synthetic XISO is built in a temp dir: a real XDVDFS root, a
``vc_53450030`` folder with three packs, an outer-archive index, one AUSB
descriptor and one external bank whose middle stream crosses a pack seam.
That exercises the disc walk, the span mapping, the retail gate, the in-place
write, read-back verification and the receipt without any game data.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for candidate in (TOOLS, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_commentary_swap as cs  # noqa: E402
import xbox_ima_encoder as ima  # noqa: E402
from nfl_outer import ALIGNMENT, ENTRY_SIZE, HEADER_SIZE, PACK_SLOT_COUNT, Entry, Segment  # noqa: E402

SECTOR = 2048
BANK_NAME = "test"
BOUNDARIES = (0, 720, 2160, 2520)          # three mono streams: 20, 40, 10 blocks
BANK_ID = zlib.crc32(f"{BANK_NAME}.bin".upper().encode("utf-16le")) & 0xFFFFFFFF
DESCRIPTOR_CHUNK_OFFSET = 0x40


def _tone(frames: int, *, channels: int = 1, hz: float = 440.0, amplitude: float = 0.5,
          seed: int = 7) -> bytes:
    import random

    rng = random.Random(seed)
    samples = []
    for frame in range(frames):
        value = amplitude * math.sin(2 * math.pi * hz * frame / cs.SAMPLE_RATE)
        value += 0.02 * (rng.random() * 2 - 1)
        for _ in range(channels):
            samples.append(max(-32768, min(32767, int(value * 32767))))
    return struct.pack(f"<{len(samples)}h", *samples)


def _descriptor_body(count: int, channels: int, boundaries: tuple[int, ...]) -> bytes:
    body = bytearray(0x98 + (count + 1) * 4 + 8)
    body[0x0C:0x10] = b"AUSB"
    struct.pack_into("<i", body, 0x10, 0x11)                  # name at body+0x20
    name = BANK_NAME.encode("utf-16le") + b"\0\0"
    body[0x20:0x20 + len(name)] = name
    external = f"{BANK_NAME}.bin".encode("utf-16le") + b"\0\0"
    body[0x40:0x40 + len(external)] = external
    struct.pack_into("<5I", body, 0x80, count, 0, channels, cs.SAMPLE_RATE, cs.UNIT_WORD)
    struct.pack_into(f"<{count + 1}I", body, 0x98, *boundaries)
    return bytes(body)


def _dir_node(offset_table: list[tuple[int, int, int, str]]) -> bytes:
    """Serialize a flat XDVDFS directory (right-chained, 4-byte aligned nodes)."""

    nodes: list[bytes] = []
    cursor = 0
    positions = []
    for index, (sector, size, attributes, name) in enumerate(offset_table):
        raw = struct.pack("<HHIIBB", 0, 0, sector, size, attributes, len(name)) + name.encode("ascii")
        raw += b"\0" * (-len(raw) % 4)
        positions.append(cursor)
        nodes.append(raw)
        cursor += len(raw)
    out = bytearray(b"".join(nodes))
    for index in range(len(nodes) - 1):
        struct.pack_into("<H", out, positions[index] + 2, positions[index + 1] // 4)
    return bytes(out)


class SyntheticDisc:
    """Builds the fixture image and remembers where everything landed."""

    def __init__(self, directory: Path, *, bank_payload: bytes) -> None:
        self.path = directory / "fixture.xiso.iso"
        self.retail_packs = directory / "retail" / "vc_53450030"
        self.retail_packs.mkdir(parents=True)
        pack_sizes = (0x4000, 0x2000, 0x2000)
        assert len(bank_payload) == BOUNDARIES[-1]
        descriptor = _descriptor_body(len(BOUNDARIES) - 1, 1, BOUNDARIES)
        wrapper = struct.pack("<4sI6I", b"AUSB", len(descriptor), 0, 0, 0, 0, 0, 0)
        # Outer archive virtual layout (0x800-aligned entries tiling all packs).
        entry0_offset = 0x800
        entry0 = bytes(DESCRIPTOR_CHUNK_OFFSET) + wrapper + descriptor
        entry0 = entry0 + bytes(0x3000 - len(entry0))          # ends 0x3800
        entry1_offset = 0x3800                                  # bank crosses 0x4000 seam
        entry2_offset = 0x4800
        entry2 = bytes(0x8000 - entry2_offset)
        virtual = bytearray(sum(pack_sizes))
        header = struct.pack("<III", 3, 0, 3)
        header += struct.pack(f"<{PACK_SLOT_COUNT}I", *(
            [size // ALIGNMENT for size in pack_sizes] + [0] * (PACK_SLOT_COUNT - 3)))
        assert len(header) == HEADER_SIZE
        table = b"".join(struct.pack("<III", name_id, size, offset // ALIGNMENT) for name_id, size, offset in (
            (0x11111111, len(entry0), entry0_offset),
            (BANK_ID, len(bank_payload), entry1_offset),
            (0x22222222, len(entry2), entry2_offset),
        ))
        virtual[0:len(header)] = header
        virtual[len(header):len(header) + len(table)] = table
        virtual[entry0_offset:entry0_offset + len(entry0)] = entry0
        virtual[entry1_offset:entry1_offset + len(bank_payload)] = bank_payload
        packs = []
        cursor = 0
        for size in pack_sizes:
            packs.append(bytes(virtual[cursor:cursor + size]))
            cursor += size
        for name, payload in zip("012", packs):
            (self.retail_packs / name).write_bytes(payload)

        # XDVDFS: header sector 32, root sector 33, subdir sector 34, xbe sector 35, packs from 64.
        pack_sectors = (64, 72, 76)
        root = _dir_node([(35, 16, 0x80, "default.xbe"), (34, 0, 0x10, "vc_53450030")])
        subdir = _dir_node([(pack_sectors[index], pack_sizes[index], 0x80, name)
                            for index, name in enumerate("012")])
        root = _dir_node([(35, 16, 0x80, "default.xbe"), (34, len(subdir), 0x10, "vc_53450030")])
        image = bytearray(0x28000)
        head = bytearray(0x800)
        head[:20] = cs.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", head, 20, 33, len(root))
        head[-20:] = cs.xiso.XDVDFS_MAGIC
        image[0x10000:0x10800] = head
        image[33 * SECTOR:33 * SECTOR + len(root)] = root
        image[34 * SECTOR:34 * SECTOR + len(subdir)] = subdir
        image[35 * SECTOR:35 * SECTOR + 16] = b"XBEH" + bytes(12)
        for sector, payload in zip(pack_sectors, packs):
            image[sector * SECTOR:sector * SECTOR + len(payload)] = payload
        self.path.write_bytes(bytes(image))
        self.pack_sectors = pack_sectors
        self.entry1_offset = entry1_offset

    @property
    def descriptors(self) -> tuple[tuple[int, int, int, int, str], ...]:
        return ((0, 0, DESCRIPTOR_CHUNK_OFFSET, 0x98 + len(BOUNDARIES) * 4 + 8, BANK_NAME),)


def _open(disc: SyntheticDisc, **kwargs: object) -> cs.DiscBanks:
    return cs.DiscBanks(disc.path, descriptors=disc.descriptors, **kwargs)


class CodecRoundTripTests(unittest.TestCase):
    def test_encode_then_decode_is_close_and_exact_in_size(self) -> None:
        pcm = _tone(64 * 12)
        encoded = ima.encode_stream(pcm, 1)
        self.assertEqual(len(encoded), 12 * 36)
        decoded = cs.decode_payload(encoded, 1)
        self.assertEqual(len(decoded), len(pcm))
        self.assertGreater(cs.snr_db(pcm, decoded), 20.0)
        # The vectorised studio decoder and the scalar reference agree byte for byte.
        self.assertEqual(decoded, ima.decode_stream(encoded, 1))

    def test_stereo_round_trip(self) -> None:
        pcm = _tone(64 * 5, channels=2)
        encoded = ima.encode_stream(pcm, 2)
        self.assertEqual(len(encoded), 5 * 72)
        decoded = cs.decode_payload(encoded, 2)
        self.assertGreater(cs.snr_db(pcm, decoded), 20.0)

    def test_silence_blocks_decode_to_exact_zero(self) -> None:
        encoded = ima.encode_stream(bytes(64 * 3 * 2), 1)
        self.assertEqual(cs.decode_payload(encoded, 1), bytes(64 * 3 * 2))


class AllocationFittingTests(unittest.TestCase):
    def _stream(self, frames: int = 64 * 5, channels: int = 1) -> cs.Stream:
        size = frames // 64 * 36 * channels
        entry = Entry(1, BANK_ID, size, 0, 0, "", "", (Segment(0, "0", 0, size),))
        bank = cs.Bank(BANK_NAME, 0, 0, 0, "test.bin", 1, size, channels, cs.SAMPLE_RATE, 0,
                       (0, size), entry)
        return cs.Stream(bank, 0, 0, size, (cs.DiscSpan(0x1000, size, "0", 0),))

    def test_pads_short_clip_with_silence_to_the_exact_allocation(self) -> None:
        stream = self._stream()
        clip = _tone(64 * 3)
        encoded, source_frames = cs.encode_for_stream(clip, stream)
        self.assertEqual(len(encoded), stream.size)
        self.assertEqual(source_frames, 64 * 3)
        decoded = cs.decode_payload(encoded, 1)
        self.assertEqual(decoded[64 * 3 * 2:], bytes(64 * 2 * 2))
        self.assertGreater(cs.snr_db(clip, decoded[:len(clip)]), 20.0)

    def test_pads_a_clip_that_is_not_a_whole_block(self) -> None:
        stream = self._stream()
        clip = _tone(100)
        encoded, source_frames = cs.encode_for_stream(clip, stream)
        self.assertEqual(len(encoded), stream.size)
        self.assertEqual(source_frames, 100)

    def test_refuses_a_clip_longer_than_the_slot(self) -> None:
        stream = self._stream()
        with self.assertRaisesRegex(cs.CommentarySwapError, "trim it first"):
            cs.fit_pcm(_tone(64 * 5 + 1), 1, stream.frame_count)

    def test_refuses_empty_or_ragged_pcm(self) -> None:
        with self.assertRaises(cs.CommentarySwapError):
            cs.fit_pcm(b"", 1, 64)
        with self.assertRaises(cs.CommentarySwapError):
            cs.fit_pcm(b"\0", 1, 64)

    def test_stream_geometry(self) -> None:
        stream = self._stream(64 * 7, channels=2)
        self.assertEqual(stream.block_count, 7)
        self.assertEqual(stream.frame_count, 448)
        self.assertAlmostEqual(stream.duration, 448 / 22050)
        self.assertEqual(stream.stream_id, "test:0")


class WavHelpersTests(unittest.TestCase):
    def test_write_then_read(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.wav"
            pcm = _tone(300)
            cs.write_wav(path, pcm, 1)
            self.assertEqual(cs.read_wav(path), (1, cs.SAMPLE_RATE, pcm))

    def test_tolerates_list_chunk_before_data(self) -> None:
        pcm = _tone(64)
        fmt = struct.pack("<HHIIHH", 1, 1, cs.SAMPLE_RATE, cs.SAMPLE_RATE * 2, 2, 16)
        info = b"INFOISFT\x05\x00\x00\x00lavf\0\0"
        body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + b"LIST" + struct.pack("<I", len(info)) + info
        body += b"data" + struct.pack("<I", len(pcm)) + pcm
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "b.wav"
            path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
            self.assertEqual(cs.read_wav(path), (1, cs.SAMPLE_RATE, pcm))

    def test_rejects_non_pcm16(self) -> None:
        fmt = struct.pack("<HHIIHH", 3, 1, cs.SAMPLE_RATE, cs.SAMPLE_RATE * 4, 4, 32)
        body = b"WAVEfmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", 4) + bytes(4)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "c.wav"
            path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
            with self.assertRaisesRegex(cs.CommentarySwapError, "PCM16"):
                cs.read_wav(path)

    def test_parse_stream_id(self) -> None:
        self.assertEqual(cs.parse_stream_id("lines:1234"), ("lines", 1234))
        for bad in ("lines", "lines:", ":3", "lines:x"):
            with self.assertRaises(cs.CommentarySwapError):
                cs.parse_stream_id(bad)


class SyntheticDiscTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        folder = Path(self._tmp.name)
        self.retail_pcm = [_tone(64 * 20, hz=220, seed=1), _tone(64 * 40, hz=330, seed=2),
                           _tone(64 * 10, hz=550, seed=3)]
        self.retail_payload = b"".join(ima.encode_stream(pcm, 1) for pcm in self.retail_pcm)
        self.disc = SyntheticDisc(folder, bank_payload=self.retail_payload)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_walks_banks_and_maps_a_seam_crossing_stream(self) -> None:
        with _open(self.disc) as disc:
            self.assertEqual(sorted(disc.banks), [BANK_NAME])
            bank = disc.banks[BANK_NAME]
            self.assertEqual(bank.count, 3)
            self.assertEqual(bank.boundaries, BOUNDARIES)
            self.assertEqual(bank.external_outer_index, 1)
            first, middle, last = (disc.stream(BANK_NAME, index) for index in range(3))
            self.assertTrue(first.contiguous)
            self.assertEqual(first.spans[0].xiso_offset,
                             self.disc.pack_sectors[0] * SECTOR + self.disc.entry1_offset)
            self.assertEqual(len(middle.spans), 2)
            self.assertEqual([span.pack_name for span in middle.spans], ["0", "1"])
            self.assertEqual(middle.spans[0].length + middle.spans[1].length, 1440)
            self.assertEqual(middle.spans[1].xiso_offset, self.disc.pack_sectors[1] * SECTOR)
            self.assertEqual(last.spans[0].pack_name, "1")
            for stream, pcm in zip((first, middle, last), self.retail_pcm):
                self.assertEqual(disc.read_stream(stream), ima.encode_stream(pcm, 1))
            with self.assertRaises(cs.CommentarySwapError):
                disc.stream(BANK_NAME, 3)
            with self.assertRaises(cs.CommentarySwapError):
                disc.stream("nope", 0)

    def test_pinned_descriptor_mismatch_fails_closed(self) -> None:
        wrong = ((0, 0, DESCRIPTOR_CHUNK_OFFSET + 4, 0x98 + len(BOUNDARIES) * 4 + 8, BANK_NAME),)
        with self.assertRaisesRegex(cs.CommentarySwapError, "not the pinned AUSB descriptor"):
            cs.DiscBanks(self.disc.path, descriptors=wrong)

    def test_export_writes_wavs_and_manifest(self) -> None:
        out = Path(self._tmp.name) / "exports"
        with _open(self.disc) as disc:
            rows = cs.export_streams(disc, list(disc.iter_streams(BANK_NAME, 0, 3)), out)
        self.assertEqual([row["file"] for row in rows], ["test_00000.wav", "test_00001.wav", "test_00002.wav"])
        self.assertTrue((out / "manifest.json").is_file())
        channels, rate, pcm = cs.read_wav(out / "test_00001.wav")
        self.assertEqual((channels, rate, len(pcm)), (1, cs.SAMPLE_RATE, 64 * 40 * 2))
        self.assertGreater(cs.snr_db(self.retail_pcm[1], pcm), 20.0)

    def test_replace_gates_on_retail_bytes_then_writes_only_the_span(self) -> None:
        folder = Path(self._tmp.name)
        clip = _tone(64 * 25 + 17, hz=990, seed=9)          # shorter than the 40-block slot
        wav = folder / "clip.wav"
        cs.write_wav(wav, clip, 1)
        before_image = self.disc.path.read_bytes()
        receipt = cs.replace_stream(self.disc.path, f"{BANK_NAME}:1", wav,
                                    retail_packs=self.disc.retail_packs, descriptors=self.disc.descriptors)
        self.assertEqual(receipt["retail_gate"], "retail-packs")
        self.assertEqual(receipt["clip_frames"], 64 * 25 + 17)
        self.assertEqual(receipt["padded_silence_frames"], 64 * 40 - (64 * 25 + 17))
        self.assertFalse(receipt["descriptor_changed"])
        self.assertEqual(receipt["before_sha256"], hashlib.sha256(ima.encode_stream(self.retail_pcm[1], 1)).hexdigest())
        after_image = self.disc.path.read_bytes()
        self.assertEqual(len(after_image), len(before_image))
        with _open(self.disc) as disc:
            middle = disc.stream(BANK_NAME, 1)
            expected, _frames = cs.encode_for_stream(clip, middle)
            self.assertEqual(disc.read_stream(middle), expected)
            self.assertEqual(receipt["after_sha256"], hashlib.sha256(expected).hexdigest())
            # Neighbours untouched, the descriptor untouched, nothing else on the image changed.
            self.assertEqual(disc.read_stream(disc.stream(BANK_NAME, 0)), ima.encode_stream(self.retail_pcm[0], 1))
            self.assertEqual(disc.read_stream(disc.stream(BANK_NAME, 2)), ima.encode_stream(self.retail_pcm[2], 1))
            changed = [index for index, (a, b) in enumerate(zip(before_image, after_image)) if a != b]
            spans = middle.spans
            for index in changed:
                self.assertTrue(any(span.xiso_offset <= index < span.xiso_offset + span.length for span in spans))
        # verify sees the clip on the disc; a different clip does not match.
        result = cs.verify_stream(self.disc.path, f"{BANK_NAME}:1", wav, folder / "decoded.wav",
                                  descriptors=self.disc.descriptors)
        self.assertTrue(result["matches_encoded_clip"])
        self.assertGreater(result["decoded_snr_db_vs_clip"], 20.0)
        self.assertTrue((folder / "decoded.wav").is_file())
        other = folder / "other.wav"
        cs.write_wav(other, _tone(64 * 4, hz=120), 1)
        self.assertFalse(cs.verify_stream(self.disc.path, f"{BANK_NAME}:1", other,
                                          descriptors=self.disc.descriptors)["matches_encoded_clip"])
        # A second replace of the same stream now fails the retail gate unless forced.
        with self.assertRaisesRegex(cs.CommentarySwapError, "no longer carries the retail bytes"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:1", wav, retail_packs=self.disc.retail_packs,
                              descriptors=self.disc.descriptors)
        forced = cs.replace_stream(self.disc.path, f"{BANK_NAME}:1", other, retail_packs=self.disc.retail_packs,
                                   force=True, descriptors=self.disc.descriptors)
        self.assertEqual(forced["retail_gate"], "forced")

    def test_replace_refuses_wrong_shape_and_missing_gate(self) -> None:
        folder = Path(self._tmp.name)
        stereo = folder / "stereo.wav"
        cs.write_wav(stereo, _tone(64, channels=2), 2)
        with self.assertRaisesRegex(cs.CommentarySwapError, "channel"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:0", stereo, retail_packs=self.disc.retail_packs,
                              descriptors=self.disc.descriptors)
        wrong_rate = folder / "rate.wav"
        cs.write_wav(wrong_rate, _tone(64), 1, 16000)
        with self.assertRaisesRegex(cs.CommentarySwapError, "Hz"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:0", wrong_rate, retail_packs=self.disc.retail_packs,
                              descriptors=self.disc.descriptors)
        ok = folder / "ok.wav"
        cs.write_wav(ok, _tone(64), 1)
        with self.assertRaisesRegex(cs.CommentarySwapError, "verified before it is overwritten"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:0", ok, retail_packs=None,
                              descriptors=self.disc.descriptors)
        too_long = folder / "long.wav"
        cs.write_wav(too_long, _tone(64 * 21), 1)
        with self.assertRaisesRegex(cs.CommentarySwapError, "trim it first"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:0", too_long, retail_packs=self.disc.retail_packs,
                              descriptors=self.disc.descriptors)
        # None of the refusals touched the image.
        with _open(self.disc) as disc:
            self.assertEqual(disc.read_stream(disc.stream(BANK_NAME, 0)), ima.encode_stream(self.retail_pcm[0], 1))

    def test_guard_refuses_the_guarded_image_identity(self) -> None:
        folder = Path(self._tmp.name)
        ok = folder / "ok.wav"
        cs.write_wav(ok, _tone(64), 1)
        with self.assertRaisesRegex(cs.CommentarySwapError, "guarded retail image"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:0", ok, retail_packs=self.disc.retail_packs,
                              guards=[self.disc.path], descriptors=self.disc.descriptors)

    def test_expect_sha256_gate(self) -> None:
        folder = Path(self._tmp.name)
        ok = folder / "ok.wav"
        cs.write_wav(ok, _tone(64), 1)
        digest = hashlib.sha256(ima.encode_stream(self.retail_pcm[2], 1)).hexdigest()
        with self.assertRaisesRegex(cs.CommentarySwapError, "!= expected"):
            cs.replace_stream(self.disc.path, f"{BANK_NAME}:2", ok, retail_packs=None,
                              expect_sha256="0" * 64, descriptors=self.disc.descriptors)
        receipt = cs.replace_stream(self.disc.path, f"{BANK_NAME}:2", ok, retail_packs=None,
                                    expect_sha256=digest, descriptors=self.disc.descriptors)
        self.assertEqual(receipt["retail_gate"], "expect-sha256")

    def test_cli_list_and_json(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cs.main(["list", str(self.disc.path), "--bank", BANK_NAME, "--json",
                            "--descriptors-fixture", json.dumps(self.disc.descriptors)])
        self.assertEqual(code, 0)
        rows = json.loads(buffer.getvalue())
        self.assertEqual([row["stream"] for row in rows], ["test:0", "test:1", "test:2"])
        self.assertEqual(rows[1]["bytes"], 1440)
        self.assertEqual(len(rows[1]["xiso_spans"]), 2)


class ConformTests(unittest.TestCase):
    def test_conform_cuts_downmixes_and_normalises(self) -> None:
        import shutil

        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "stereo48k.wav"
            # 3 s of quiet stereo tone at 48 kHz, as a home recording would be.
            frames = 48_000 * 3
            samples = []
            for frame in range(frames):
                value = int(0.05 * 32767 * math.sin(2 * math.pi * 300 * frame / 48_000))
                samples += [value, value]
            cs.write_wav(source, struct.pack(f"<{len(samples)}h", *samples), 2, 48_000)
            out = root / "clip.wav"
            info = cs.conform_clip(source, out, channels=1, max_seconds=1.5, start=0.5,
                                   loudnorm_lufs=-16.0)
            channels, rate, pcm = cs.read_wav(out)
            self.assertEqual((channels, rate), (1, cs.SAMPLE_RATE))
            self.assertLessEqual(len(pcm) // 2, int(1.5 * cs.SAMPLE_RATE) + 64)
            self.assertEqual(info["channels"], 1)
            values = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            rms = math.sqrt(sum(v * v for v in values) / len(values)) / 32767
            self.assertGreater(20 * math.log10(rms), -24.0)   # lifted well above the -29 dBFS input
            self.assertLess(max(abs(v) for v in values), 32767)

    def test_target_rms_lands_on_the_retail_level_without_clipping(self) -> None:
        import shutil

        if shutil.which("ffmpeg") is None:
            self.skipTest("ffmpeg is not installed")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "quiet.wav"
            # A quiet, peaky voice-like signal: tone bursts with an 18 dB crest factor.
            frames = 48_000 * 2
            samples = []
            for frame in range(frames):
                envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * frame / 48_000)
                value = 0.08 * envelope * math.sin(2 * math.pi * 220 * frame / 48_000)
                samples.append(int(value * 32767))
            cs.write_wav(source, struct.pack(f"<{len(samples)}h", *samples), 1, 48_000)
            out = root / "clip.wav"
            info = cs.conform_clip(source, out, channels=1, max_seconds=2.0, target_rms_db=cs.RETAIL_SPEECH_RMS_DB)
            _c, _r, pcm = cs.read_wav(out)
            self.assertAlmostEqual(cs.pcm_rms_db(pcm), cs.RETAIL_SPEECH_RMS_DB, delta=0.6)
            self.assertEqual(info["output_rms_db"], round(cs.pcm_rms_db(pcm), 2))
            self.assertLess(info["input_rms_db"], -20.0)
            self.assertGreater(info["applied_gain_db"], 6.0)
            peak = max(abs(v) for v in struct.unpack(f"<{len(pcm) // 2}h", pcm))
            self.assertLessEqual(peak, int(0.97 * 32767))


if __name__ == "__main__":
    unittest.main()
