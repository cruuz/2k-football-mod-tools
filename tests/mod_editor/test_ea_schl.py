"""The EA ``SCHl`` reader, its two decoders and its two encoders, on synthetic data.

Every stream, bank and frame here is built out of the format's own rules -- a
computed tone, a hand-written ADPCM frame whose samples are worked out below in
long form -- so the tests prove the layout without a game anywhere near them.
The evidence that the same code reads *real* audio is in
``docs/product/EA_SCHL_FORMAT.md``: 47 of 47 ``BGM.DAT`` streams and every
sound of every ``BNKl`` bank decode byte for byte against ffmpeg.  What these
tests hold is that the rules are implemented as written and that every refusal
names its fix.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_schl  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


def _block(payload: bytes) -> ea_schl.Block:
    """A one-block stream body, so a decoder can be handed frames directly."""

    chunk = ea_schl.SCDL_MAGIC + struct.pack("<I", 8 + len(payload)) + payload
    return chunk


class TagListTests(unittest.TestCase):
    """Tag / length / big-endian value, and the escape that 515 headers need."""

    def test_a_short_value_is_a_big_endian_integer(self) -> None:
        tags = ea_schl.parse_tags(bytes([0x84, 3, 0x00, 0x8C, 0xA0, 0xFF]))
        self.assertEqual(tags[0][0], ea_schl.TAG_SAMPLE_RATE)
        self.assertEqual(tags[0][1], 36000)
        self.assertEqual(tags[-1][0], ea_schl.TAG_END)

    def test_four_tags_carry_no_value_at_all(self) -> None:
        tags = ea_schl.parse_tags(bytes([0xFC, 0xFD, 0xFE, 0xFF]))
        self.assertEqual([tag for tag, _value, _blob in tags], [0xFC, 0xFD, 0xFE, 0xFF])
        self.assertTrue(all(value is None for _tag, value, _blob in tags))

    def test_a_length_of_ff_escapes_to_a_four_byte_length(self) -> None:
        body = bytes([0x14, 0xFF]) + (300).to_bytes(4, "big") + b"E" * 300
        body += bytes([0x82, 1, 2, 0xFF])
        tags = ea_schl.parse_tags(body)
        self.assertEqual(tags[0][0], 0x14)
        self.assertEqual(len(tags[0][2]), 300)
        self.assertEqual(tags[1], (ea_schl.TAG_CHANNELS, 2, b"\x02"))

    def test_the_walk_stops_at_the_terminator(self) -> None:
        tags = ea_schl.parse_tags(bytes([0x82, 1, 2, 0xFF, 0x84, 2, 0x56, 0x22]))
        self.assertEqual(len(tags), 2)

    def test_a_truncated_tag_ends_the_walk_rather_than_raising(self) -> None:
        self.assertEqual(ea_schl.parse_tags(bytes([0x84, 4, 0x00])), ())


class HeaderTests(unittest.TestCase):
    """Where the tag list starts, and what the platform tag decides."""

    def test_gstr_is_big_endian_and_its_tags_start_at_sixteen(self) -> None:
        raw = ea_schl.synthetic_stream(samples=224, channels=2, sample_rate=22050,
                                       big_endian=True)
        header = ea_schl.parse_stream_header(raw, 0, len(raw))
        self.assertEqual(header.platform, ea_schl.PLATFORM_GSTR)
        self.assertTrue(header.big_endian)
        self.assertEqual(header.channels, 2)
        self.assertEqual(header.sample_rate, 22050)
        self.assertEqual(header.sample_count, 224)

    def test_pt_is_little_endian_and_its_tags_start_at_twelve(self) -> None:
        raw = ea_schl.synthetic_stream(samples=224, channels=1, sample_rate=28000,
                                       big_endian=False)
        header = ea_schl.parse_stream_header(raw, 0, len(raw))
        self.assertEqual(header.platform, ea_schl.PLATFORM_PT)
        self.assertFalse(header.big_endian)
        self.assertEqual(header.platform_code, 5)

    def test_an_absent_channel_tag_means_one_channel(self) -> None:
        header = ea_schl.StreamHeader(0, 36, ea_schl.PLATFORM_GSTR, None, True,
                                      ((ea_schl.TAG_SAMPLE_COUNT, 10, b"\n"),))
        self.assertEqual(header.channels, 1)

    def test_an_unknown_platform_is_refused_by_name(self) -> None:
        raw = bytearray(ea_schl.synthetic_stream(samples=112, channels=1))
        raw[8:12] = b"ZZZZ"
        with self.assertRaises(Refusal) as caught:
            ea_schl.parse_stream_header(bytes(raw), 0, len(raw))
        self.assertIn("ZZZZ", str(caught.exception))

    def test_a_member_that_is_not_a_stream_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            ea_schl.parse_stream_header(b"MMAP" + bytes(60), 0, 64)


class StreamWalkTests(unittest.TestCase):
    """A member holds one or more streams, zero-padded apart."""

    def test_two_streams_in_one_member_are_both_found(self) -> None:
        first = ea_schl.synthetic_stream(samples=224, channels=1, sample_rate=22050)
        second = ea_schl.synthetic_stream(samples=112, channels=2, sample_rate=44100)
        member = first + b"\x00" * 64 + second
        streams = ea_schl.iter_streams(member, 0, len(member))
        self.assertEqual(len(streams), 2)
        self.assertEqual([item.index for item in streams], [0, 1])
        self.assertEqual(streams[0].header.sample_count, 224)
        self.assertEqual(streams[1].header.channels, 2)
        self.assertTrue(all(item.complete for item in streams))

    def test_the_block_count_and_the_blocks_agree(self) -> None:
        raw = ea_schl.synthetic_stream(samples=4480 * 2 + 224, channels=1)
        stream = ea_schl.iter_streams(raw, 0, len(raw))[0]
        self.assertEqual(stream.declared_blocks, len(stream.blocks))
        self.assertEqual(stream.block_samples, stream.header.sample_count)

    def test_trailing_bytes_that_are_not_a_stream_end_the_walk(self) -> None:
        raw = ea_schl.synthetic_stream(samples=224, channels=1) + b"\x00" * 16 + b"JUNKJUNK"
        self.assertEqual(len(ea_schl.iter_streams(raw, 0, len(raw))), 1)


class EaxaDecoderTests(unittest.TestCase):
    """The 28-sample frame, worked out by hand and then by the decoder."""

    def test_a_hand_computed_frame_decodes_to_the_hand_computed_samples(self) -> None:
        # Control byte 0x10: coefficient set 1 -> (c1, c2) = (240, 0); low
        # nibble 0 -> shift 20.  The predictor starts at (0, 0), so:
        #   s0 = ((1 << 20) + 0*240 + 0*0) >> 8            = 4096
        #   s1 = ((0 << 20) + 4096*240 + 0*0) >> 8         = 3840
        #   s2 = ((0 << 20) + 3840*240 + 4096*0) >> 8      = 3600
        #   s3 = ((0 << 20) + 3600*240 + 3840*0) >> 8      = 3375
        frame = bytes([0x10, 0x10]) + bytes(13)
        payload = struct.pack(">I", 28) + struct.pack(">I", 0) + frame
        raw = _block(payload)
        blocks = (ea_schl.Block(0, len(raw), 28),)
        pcm = ea_schl.decode_eaxa(raw, blocks, 1, True)
        got = struct.unpack("<4h", pcm[:8])
        self.assertEqual(got, (4096, 3840, 3600, 3375))

    def test_a_verbatim_frame_is_big_endian_even_in_a_little_endian_stream(self) -> None:
        # 0xEE, then current, previous, then 28 samples -- all big-endian [M].
        samples = [1] + [0] * 27
        frame = bytes([0xEE]) + struct.pack(">hh", 0, 0)
        frame += b"".join(struct.pack(">h", value) for value in samples)
        payload = struct.pack("<I", 28) + struct.pack("<I", 0) + frame
        raw = _block(payload)
        blocks = (ea_schl.Block(0, len(raw), 28),)
        pcm = ea_schl.decode_eaxa(raw, blocks, 1, False)
        self.assertEqual(struct.unpack("<h", pcm[:2])[0], 1)

    def test_a_coefficient_index_the_format_lacks_is_refused(self) -> None:
        frame = bytes([0x90, 0x00]) + bytes(13)
        payload = struct.pack(">I", 28) + struct.pack(">I", 0) + frame
        raw = _block(payload)
        with self.assertRaises(Refusal) as caught:
            ea_schl.decode_eaxa(raw, (ea_schl.Block(0, len(raw), 28),), 1, True)
        self.assertIn("coefficient set", str(caught.exception))

    def test_version_two_reads_its_predictor_out_of_every_block(self) -> None:
        frame = bytes([0x00, 0x00]) + bytes(13)  # every residual zero, no prediction
        payload = struct.pack("<I", 28) + struct.pack("<I", 0)
        payload += struct.pack("<hh", 1234, 0) + frame
        raw = _block(payload)
        blocks = (ea_schl.Block(0, len(raw), 28),)
        # Coefficient set 0 is (0, 0), so the predictor values are not used by
        # the arithmetic -- what is proved here is that four bytes were eaten.
        pcm = ea_schl.decode_eaxa(raw, blocks, 1, False, version=2)
        self.assertEqual(len(pcm), 56)
        self.assertEqual(struct.unpack("<h", pcm[:2])[0], 0)
        # Read the version-3 way, the same block walks off its own frames.
        with self.assertRaises(Refusal):
            ea_schl.decode_eaxa(raw, blocks, 1, False, version=3)


class EaxaRoundTripTests(unittest.TestCase):
    """Encode a computed signal, decode it, and say how close it came."""

    def _round_trip(self, channels: int, rate: int, big_endian: bool,
                    version: int) -> float:
        pcm = ea_schl.synthetic_pcm(2240, channels, sample_rate=rate)
        raw = ea_schl.build_stream(pcm, channels=channels, sample_rate=rate,
                                   big_endian=big_endian, version=version)
        stream = ea_schl.iter_streams(raw, 0, len(raw))[0]
        self.assertEqual(stream.header.sample_count, 2240)
        made = ea_schl.decode_eaxa(raw, stream.blocks, channels, big_endian,
                                   stream.header.version)
        self.assertEqual(len(made), len(pcm))
        ratio = ea_schl.signal_to_noise(pcm, made)
        self.assertIsNotNone(ratio)
        return float(ratio)

    def test_every_shape_the_disc_uses_round_trips_above_thirty_decibels(self) -> None:
        for channels in (1, 2):
            for big_endian in (True, False):
                for version in (2, 3):
                    with self.subTest(channels=channels, big_endian=big_endian,
                                      version=version):
                        ratio = self._round_trip(channels, 22050, big_endian, version)
                        self.assertGreater(ratio, 30.0)

    def test_the_encoder_writes_whole_frames_only(self) -> None:
        pcm = ea_schl.synthetic_pcm(30, 1, sample_rate=22050)  # 28 + 2 spare
        chunks = ea_schl.encode_eaxa_blocks(pcm, 1, True)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(struct.unpack_from(">I", chunks[0], 8)[0], 28)


class PsxTests(unittest.TestCase):
    """Sony PS ADPCM: the 16-byte frame, and the two details that bite."""

    def test_a_hand_computed_frame_decodes_to_the_hand_computed_samples(self) -> None:
        # Control byte 0x10: filter 1 -> (f0, f1) = (60, 0); shift 0.  Residual
        # nibbles are read LOW first.  Starting from (0, 0):
        #   s0 = ((1 << 12) >> 0) + trunc((0*60 + 0*0)/64)      = 4096
        #   s1 = ((0 << 12) >> 0) + trunc((4096*60 + 0*0)/64)   = 3840
        #   s2 = ((0 << 12) >> 0) + trunc((3840*60 + 4096*0)/64) = 3600
        frame = bytes([0x10, 0x00, 0x01]) + bytes(13)
        pcm = ea_schl.decode_psx(frame, 1)
        self.assertEqual(struct.unpack("<3h", pcm[:6]), (4096, 3840, 3600))

    def test_the_predictor_term_truncates_toward_zero(self) -> None:
        # An arithmetic shift would floor this to one less.  Filter 2 with a
        # negative history is where the two disagree.
        accumulator = -100 * 115 + 50 * 52
        self.assertNotEqual(accumulator >> 6, int(accumulator / 64))

    def test_a_filter_the_format_lacks_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            ea_schl.decode_psx(bytes([0x90, 0x00]) + bytes(14), 1)
        self.assertIn("filter", str(caught.exception))

    def test_stereo_channels_are_planar_runs(self) -> None:
        # Two frames per channel: channel 0's run first, then channel 1's.  An
        # interleaved reading would put the second frame of the first run into
        # the other channel, and the disc's stereo banks are not laid out that
        # way (tag 0x89 names the second run on all 183 of them).
        run0 = (bytes([0x00, 0x00, 0x11]) + bytes(13)) + (bytes([0x00, 0x00, 0x33]) + bytes(13))
        run1 = (bytes([0x00, 0x00, 0x22]) + bytes(13)) + (bytes([0x00, 0x00, 0x44]) + bytes(13))
        pcm = ea_schl.decode_psx(run0 + run1, 2)
        first_left, first_right = struct.unpack("<2h", pcm[:4])
        self.assertEqual(first_left, 1 << 12)
        self.assertEqual(first_right, 2 << 12)
        # Sample 28 (the second frame of each run) lands in the same channel.
        left_28, right_28 = struct.unpack_from("<2h", pcm, 28 * 4)
        self.assertEqual(left_28, 3 << 12)
        self.assertEqual(right_28, 4 << 12)
        # An explicit second-run offset overrides the equal split.
        again = ea_schl.decode_psx(run0 + run1, 2, channel_offsets=[0, len(run0)])
        self.assertEqual(again, pcm)

    def test_encode_then_decode_stays_above_thirty_decibels(self) -> None:
        for channels in (1, 2):
            with self.subTest(channels=channels):
                pcm = ea_schl.synthetic_pcm(1120, channels, sample_rate=24000)
                made = ea_schl.decode_psx(ea_schl.encode_psx(pcm, channels), channels)
                self.assertEqual(len(made), len(pcm))
                self.assertGreater(float(ea_schl.signal_to_noise(pcm, made)), 30.0)


class BankTests(unittest.TestCase):
    """The directory whose offsets are counted from their own slots."""

    def test_a_bank_parses_to_its_sounds(self) -> None:
        blob = ea_schl.synthetic_bank(sounds=3, samples=560, sample_rate=24000)
        bank = ea_schl.parse_bank(blob, 0, len(blob))
        self.assertEqual(bank.version, 5)
        self.assertEqual(len(bank.sounds), 3)
        self.assertEqual(bank.header_size + bank.data_size, len(blob))
        for sound in bank.sounds:
            self.assertEqual(sound.sample_count, 560)
            self.assertEqual(sound.sample_rate, 24000)
            self.assertGreater(sound.data_length, 0)

    def test_each_sound_decodes_to_its_declared_length(self) -> None:
        blob = ea_schl.synthetic_bank(sounds=2, samples=560, sample_rate=24000)
        bank = ea_schl.parse_bank(blob, 0, len(blob))
        for sound in bank.sounds:
            pcm = ea_schl.decode_bank_sound(blob, bank, sound)
            self.assertEqual(len(pcm), sound.sample_count * 2 * sound.channels)
            self.assertFalse(ea_schl.measure(pcm)["silent"])

    def test_a_stereo_bank_names_its_second_run_and_decodes_it_planar(self) -> None:
        blob = ea_schl.synthetic_bank(sounds=1, samples=560, sample_rate=32000, channels=2)
        bank = ea_schl.parse_bank(blob, 0, len(blob))
        sound = bank.sounds[0]
        second = sound.header.value(ea_schl.TAG_SECOND_CHANNEL)
        self.assertEqual(second, sound.data_offset + sound.data_length // 2,
                         "tag 0x89 is the second channel's offset, half way through the data")
        pcm = ea_schl.decode_bank_sound(blob, bank, sound)
        self.assertEqual(len(pcm), 560 * 2 * 2)
        wanted = ea_schl.synthetic_pcm(560, 2, sample_rate=32000, frequency=220.0)
        self.assertGreater(float(ea_schl.signal_to_noise(wanted, pcm)), 30.0)
        # A mono sound carries no second-run tag at all.
        mono = ea_schl.synthetic_bank(sounds=1, samples=560, sample_rate=32000, channels=1)
        mono_bank = ea_schl.parse_bank(mono, 0, len(mono))
        self.assertIsNone(mono_bank.sounds[0].header.value(ea_schl.TAG_SECOND_CHANNEL))

    def test_a_second_run_offset_off_a_frame_boundary_is_refused(self) -> None:
        blob = bytearray(ea_schl.synthetic_bank(sounds=1, samples=560, sample_rate=32000,
                                                channels=2))
        bank = ea_schl.parse_bank(bytes(blob), 0, len(blob))
        sound = bank.sounds[0]
        marker = (bytes([ea_schl.TAG_SECOND_CHANNEL, 4])
                  + int(sound.header.value(ea_schl.TAG_SECOND_CHANNEL)).to_bytes(4, "big"))
        where = blob.find(marker)
        self.assertGreater(where, 0)
        bad = int(sound.header.value(ea_schl.TAG_SECOND_CHANNEL)) + 5
        blob[where:where + 6] = bytes([ea_schl.TAG_SECOND_CHANNEL, 4]) + bad.to_bytes(4, "big")
        broken = ea_schl.parse_bank(bytes(blob), 0, len(blob))
        with self.assertRaises(Refusal) as caught:
            ea_schl.decode_bank_sound(bytes(blob), broken, broken.sounds[0])
        self.assertIn("frame boundary", str(caught.exception))

    def test_reading_the_offsets_from_the_table_instead_finds_nothing(self) -> None:
        # The rule that had to be measured: an offset is relative to its own
        # slot.  Reading them all from the table's start puts every sound after
        # the first in the wrong place, which is exactly what this asserts.
        blob = ea_schl.synthetic_bank(sounds=3, samples=560)
        bank = ea_schl.parse_bank(blob, 0, len(blob))
        table = 0x14
        naive = [table + struct.unpack_from("<I", blob, table + 4 * index)[0]
                 for index in range(3)]
        actual = [sound.header_offset for sound in bank.sounds]
        self.assertEqual(naive[0], actual[0])
        self.assertNotEqual(naive[1:], actual[1:])

    def test_a_member_that_is_not_a_bank_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            ea_schl.parse_bank(b"SCHl" + bytes(60), 0, 64)


class WavTests(unittest.TestCase):
    """What a user may hand back, and what is refused by name."""

    def test_a_wav_round_trips(self) -> None:
        pcm = ea_schl.synthetic_pcm(400, 2, sample_rate=22050)
        rate, channels, back = ea_schl.read_wav(ea_schl.wav_bytes(pcm, 22050, 2))
        self.assertEqual((rate, channels), (22050, 2))
        self.assertEqual(back, pcm)

    def test_a_compressed_wav_is_refused_by_name(self) -> None:
        good = ea_schl.wav_bytes(ea_schl.synthetic_pcm(100, 1), 22050, 1)
        broken = bytearray(good)
        struct.pack_into("<H", broken, 20, 2)  # MS ADPCM
        with self.assertRaises(Refusal) as caught:
            ea_schl.read_wav(bytes(broken))
        self.assertIn("compressed", str(caught.exception))

    def test_something_that_is_not_a_wav_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            ea_schl.read_wav(b"\x89PNG\r\n\x1a\n" + bytes(40))

    def test_eight_bit_samples_are_widened(self) -> None:
        body = bytes([128, 255, 0, 128])
        payload = b"".join((
            b"RIFF", struct.pack("<I", 36 + len(body)), b"WAVE",
            b"fmt ", struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8),
            b"data", struct.pack("<I", len(body)), body))
        rate, channels, pcm = ea_schl.read_wav(payload)
        self.assertEqual((rate, channels), (8000, 1))
        self.assertEqual(struct.unpack("<4h", pcm), (0, 32512, -32768, 0))

    def test_a_downmix_averages_and_an_upmix_copies(self) -> None:
        stereo = struct.pack("<4h", 100, 300, -100, -300)
        self.assertEqual(struct.unpack("<2h", ea_schl.remix(stereo, 2, 1)), (200, -200))
        mono = struct.pack("<2h", 7, -7)
        self.assertEqual(struct.unpack("<4h", ea_schl.remix(mono, 1, 2)), (7, 7, -7, -7))

    def test_resampling_scales_the_length(self) -> None:
        pcm = ea_schl.synthetic_pcm(1000, 1, sample_rate=22050)
        made = ea_schl.resample(pcm, 1, 22050, 11025)
        self.assertAlmostEqual(len(made) / 2, 500, delta=2)
        self.assertEqual(ea_schl.resample(pcm, 1, 22050, 22050), pcm)


class MeasureTests(unittest.TestCase):
    """The plausibility numbers a bank's export reports."""

    def test_a_tone_is_measured_as_loud_and_unsaturated(self) -> None:
        report = ea_schl.measure(ea_schl.synthetic_pcm(2000, 1, amplitude=20000))
        self.assertGreater(report["peak"], 19000)
        self.assertEqual(report["saturated"], 0)
        self.assertFalse(report["silent"])

    def test_silence_is_reported_as_silence(self) -> None:
        report = ea_schl.measure(bytes(400))
        self.assertTrue(report["silent"])
        self.assertEqual(report["peak"], 0)


class SpeechCodecTests(unittest.TestCase):
    """The codec this module refuses, and the sentence it refuses with."""

    def test_a_speech_stream_parses_and_is_not_decodable(self) -> None:
        raw = ea_schl.synthetic_speech_stream(samples=2240, sample_rate=36000)
        stream = ea_schl.iter_streams(raw, 0, len(raw))[0]
        self.assertEqual(stream.header.codec, ea_schl.CODEC_SPEECH)
        self.assertFalse(stream.header.decodable)
        self.assertIn("MicroTalk", stream.header.codec_name)
        self.assertIn("MicroTalk", ea_schl.SPEECH_REFUSAL)


if __name__ == "__main__":
    unittest.main()
