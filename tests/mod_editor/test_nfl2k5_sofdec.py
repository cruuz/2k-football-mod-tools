"""CRI Sofdec streams: the retail rules, the muxer, the ffmpeg encoder round trip, the native header stage."""
from pathlib import Path
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_sofdec as sofdec  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC  # noqa: E402
from tests.nfl2k5_sofdec_fixture import (synthetic_adx, synthetic_movie, synthetic_video,  # noqa: E402
                                         sequence_header)

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
PACKS = XBE.parent / "vc_53450030" / "0"
# SHA-256 of the first 8,192 bytes (four header sectors) of each retail boot movie; hashes only.
BOOT_HEADER_SHA256 = {
    "espn_videogames.mov": "2f24a067bc591fa1768a975547b3aff1fe01f4e15fb673ccec35d0069dd5184d",
    "vc.mov": "ed99f29f2dc08e60946c6eeeb9bbbd3c258e06a65dd60cd9ab092e6f4e6d2ec7",
    "espn_game_sound.mov": "6c11baf712fd69e7e401f5496b4e2f7e11501e1ec4568343b8b561711f84d583",
    "intro.mov": "26224f42895e59d1a83aa1bebda7967dd05ee92e4c2e3c023bf648168e007ce5",
}
# Pack clocks every retail ADX stream shares at these indices (all 29 agree index by index).
RETAIL_SCR = {0: 0, 1: 14, 2: 28, 3: 41, 286: 3947, 287: 3961, 292: 4030, 24530: 338505, 26157: 360958,
              49571: 684063, 72985: 1007168, 96399: 1330273, 119813: 1653378, 131522: 1814958}


class FieldTests(unittest.TestCase):
    def test_timestamp_encoding_round_trips_with_marker_bits(self):
        for prefix in (1, 2, 3):
            for value in (0, 1, 3006, 5822880, 2 ** 32 + 5, 2 ** 33 - 1):
                raw = sofdec.timestamp_bytes(prefix, value)
                self.assertEqual(sofdec.timestamp(raw), value)
                self.assertEqual(raw[0] >> 4, prefix)
                self.assertTrue(raw[0] & 1 and raw[2] & 1 and raw[4] & 1)
        with self.assertRaises(ValueError):
            sofdec.timestamp_bytes(2, 2 ** 33)
        self.assertEqual(sofdec.rate_bytes(sofdec.MUX_RATE), bytes.fromhex("882705"))
        self.assertEqual(sofdec.MUX_RATE, 267138)

    def test_pack_clock_line_matches_the_retail_samples(self):
        for index, value in RETAIL_SCR.items():
            self.assertEqual(sofdec.scr(index), value, index)
        # the plain record-rate formula is what the retail streams do NOT use (fails from pack 287)
        plain = lambda i: (2 * i * 2048 * 90000 + 13356861) // (2 * 13356861)  # noqa: E731
        self.assertEqual(plain(286), RETAIL_SCR[286])
        self.assertNotEqual(plain(287), RETAIL_SCR[287])

    def test_picture_clock_is_the_gop_time_code(self):
        self.assertEqual(sofdec.picture_time(0, 0), 0)
        self.assertEqual(sofdec.picture_time(0, 1), 3006)
        self.assertEqual(sofdec.picture_time(0, 42), 126252)
        self.assertEqual(sofdec.picture_time(1, 13), 129168)   # a new second resets the 3006 steps
        self.assertEqual(sofdec.picture_time(3, 29), 357445)   # rounding of 90,090.09 per second
        # two retail ties on the rounded stamps went opposite ways; the exact clock explains both
        self.assertGreater(5822880 * sofdec.CLOCK_DENOMINATOR, sofdec.picture_clock(64, 19))
        self.assertLess(18174240 * sofdec.CLOCK_DENOMINATOR, sofdec.picture_clock(201, 22))
        self.assertEqual(sofdec.picture_time(64, 19), 5822880)
        self.assertEqual(sofdec.picture_time(201, 22), 18174240)

    def test_record_and_critags_layout(self):
        rec = sofdec.record(name="intro.mov", date="202609220000", frames=420, width=640, height=480,
                            video_ms=14014, audio_ms=14000, video_name="INTRO   .SFV", video_date="202609220000",
                            audio_name="INTRO   .SFA", audio_date="202609220000")
        self.assertEqual(len(rec), sofdec.RECORD_SIZE)
        f = sofdec.record_fields(rec)
        self.assertEqual((f["name"], f["frames"], f["width"], f["height"], f["rate"], f["channels"],
                          f["sample_rate"], f["video_id"], f["audio_id"], f["audio_type"]),
                         ("intro   .mov", 420, 640, 480, 13356861, 2, 48000, 0xE0, 0xC0, 0))
        self.assertEqual(rec[0x0E:0x1A], b"SofdecStream")
        self.assertEqual(rec[0x1AE + 0x18], 0xE0)                  # what 0x3CB750 tests
        self.assertEqual(rec[0x1AE + 0x1C:0x1AE + 0x1F], bytes.fromhex("2801e0"))
        tags = sofdec.critags(420, 640, 480)
        self.assertEqual(len(tags), 576)
        self.assertTrue(tags.startswith(b"CRITAGS\x000000230\x00") and tags.endswith(b"CRITAGE\x000000000\x00"))
        self.assertIn(b"419\x00", tags)
        self.assertEqual(tags.count(b"420\x00"), 3)
        self.assertEqual(sofdec._name83("intro.mov"), b"intro   .mov")
        self.assertEqual(sofdec._eighty_three("intro.SFV"), "INTRO   .SFV")
        self.assertEqual(sofdec._eighty_three("nfl2k5_intro.SFV"), "NFL2K5~1.SFV")

    def test_adx_is_reheaded_to_the_retail_v4_header(self):
        raw = synthetic_adx(4000)
        parsed = sofdec.adx(raw)
        self.assertEqual((parsed.version, parsed.samples, parsed.channels, len(parsed.header)), (3, 4000, 2, 36))
        out = sofdec.retail_adx(raw)
        again = sofdec.adx(out)
        self.assertEqual((again.version, len(again.header), again.blocks), (4, 288, parsed.blocks))
        self.assertEqual(out[:4], bytes.fromhex("8000011c"))
        self.assertEqual(out[0x18:0x20], bytes(8))                 # zero history = ffmpeg's encoder state
        self.assertTrue(out.endswith(sofdec.ADX_END))
        self.assertEqual(sofdec.retail_adx(out), out)              # already retail: kept verbatim
        for bad in (raw[:-18] + bytes(18), raw.replace(b"(c)CRI", b"(c)XXX"), raw[:0x13] + b"\x08" + raw[0x14:]):
            with self.assertRaises(ValueError):
                sofdec.adx(bad)
        with self.assertRaises(ValueError):
            sofdec.retail_adx(synthetic_adx(4000, channels=1))
        with self.assertRaises(ValueError):
            sofdec.retail_adx(synthetic_adx(4000, rate=44100))


class MuxTests(unittest.TestCase):
    def test_synthetic_movie_obeys_every_retail_rule(self):
        movie, es = synthetic_movie(4, slice_bytes=(9000, 4000, 1500))
        self.assertEqual(len(movie) % 2048, 0)
        self.assertEqual(sofdec.problems(movie), [])
        reads, width, height = sofdec.header_stage(movie)
        self.assertEqual((tuple(reads), width, height), (sofdec.HEADER_STAGE_READS, 640, 480))
        stream = sofdec.parse(movie)
        self.assertEqual(stream.video_es, es)
        self.assertEqual(stream.audio_es, sofdec.retail_adx(synthetic_adx(round(58 * 1001 / 30000 * 48000))))
        self.assertTrue(any(p.pts is None for p in stream.packets if p.stream_id == sofdec.VIDEO))
        self.assertTrue(stream.end_sector)
        self.assertEqual([u[0] for u in stream.layout[0]], [sofdec.SYSTEM, sofdec.PADDING])
        self.assertEqual([u[0] for u in stream.layout[2]], [sofdec.PRIVATE_2])
        self.assertEqual(stream.layout[4], ((sofdec.AUDIO, 2023), (sofdec.PADDING, 1)))
        self.assertEqual(stream.layout[5][0][0], sofdec.VIDEO)
        self.assertEqual([c for c, _ in stream.packs], [sofdec.scr(i) for i in range(len(stream.packs))])
        audio = [p for p in stream.packets if p.stream_id == sofdec.AUDIO]
        self.assertEqual([p.pts for p in audio], [n * 3360 for n in range(len(audio))])
        video = [p for p in stream.packets if p.stream_id == sofdec.VIDEO]
        self.assertTrue(all(p.length == 2030 for p in video[:-1]))
        forms = {(p.pts is not None, p.dts is not None, p.header[:len(p.header) - 5 * ((p.pts is not None) +
                  (p.dts is not None))]) for p in video}
        self.assertEqual(forms, {(False, False, b"\xff" * 9 + b"\x60\x2e\x0f"), (True, False, b"\xff" * 5 + b"\x60\x2e"),
                                 (True, True, b"\x60\x2e")})
        v = sofdec.video(es)
        self.assertEqual(v.gops[0][1], 1)
        self.assertEqual([g[3] for g in v.gops], [0, 13, 28, 43])
        self.assertEqual(sofdec.remux(movie), movie)

    def test_conform_video_gives_ffmpeg_output_the_retail_sequence_form(self):
        ffmpeg_like = synthetic_video(3, repeat_headers=True, end_code=False, vbv_delay=4321,
                                      header=sequence_header(aspect=1, bit_rate=6000000 // 400, vbv=104))
        conformed, receipt = sofdec.conform_video(ffmpeg_like)
        v = sofdec.video(conformed)
        self.assertEqual(len(v.sequences), 1)
        seq = v.sequences[0][1]
        self.assertEqual((seq.aspect, seq.bit_rate, seq.vbv, seq.frame_rate), (12, 0x3FFFF, 112, 4))
        self.assertTrue(all(p.vbv_delay == 0xFFFF for p in v.pictures))
        self.assertEqual(v.end_codes, [len(conformed) - 4])
        self.assertEqual(receipt["sequence_headers_removed"], 2)
        def slices(es):
            codes = list(sofdec.start_codes(es)) + [(len(es), None)]
            return [es[at:after] for (at, code), (after, _) in zip(codes, codes[1:]) if code and code <= 0xAF]
        self.assertEqual(slices(conformed), slices(ffmpeg_like))
        self.assertEqual(sofdec.conform_video(conformed)[0], conformed)
        self.assertEqual(sofdec.problems(sofdec.mux(conformed, synthetic_adx(60000))), [])

    def test_last_video_pack_that_cannot_hold_padding_is_filled_by_start_code_stuffing(self):
        base = synthetic_video(2)
        body = base[:-4]
        # grow the last slice until the stream length leaves 3 bytes in its last pack
        grow = (sofdec.VIDEO_PAYLOAD - 3 - (len(base) % sofdec.VIDEO_PAYLOAD)) % sofdec.VIDEO_PAYLOAD
        es = body + b"\x55" * grow + b"\0\0\1\xb7"
        self.assertEqual(sofdec.VIDEO_PAYLOAD - len(es) % sofdec.VIDEO_PAYLOAD, 3)
        with self.assertRaises(ValueError):
            sofdec.mux(es, synthetic_adx(40000))
        conformed, receipt = sofdec.conform_video(es)
        self.assertEqual(receipt["end_code_stuffing"], 3)
        self.assertEqual(len(conformed) % sofdec.VIDEO_PAYLOAD, 0)
        movie = sofdec.mux(conformed, synthetic_adx(40000))
        self.assertEqual(sofdec.problems(movie), [])

    def test_mux_refuses_what_the_retail_streams_never_carry(self):
        adx = synthetic_adx(40000)
        cases = {
            "size": synthetic_video(2, width=720, height=480),
            "rate": synthetic_video(2, header=sequence_header(rate=5)),
            "headers": synthetic_video(2, repeat_headers=True),
            "end": synthetic_video(2, end_code=False),
            "drop": synthetic_video(2, drop=True),
            "open": synthetic_video(2, first_closed=False),
        }
        for label, es in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                sofdec.mux(es, adx)
        with self.assertRaises(ValueError):
            sofdec.mux(synthetic_video(2), synthetic_adx(40000, channels=1))

    def test_problems_names_each_departure(self):
        movie, _ = synthetic_movie(3)
        self.assertEqual(sofdec.problems(movie), [])
        tampered = bytearray(movie)
        tampered[7 * 2048 + 8] ^= 2                              # one pack clock
        self.assertTrue(any("pack 7" in p for p in sofdec.problems(bytes(tampered))))
        swapped = bytearray(movie)
        a, v = 4, 5                                                # first audio pack <-> first video pack
        swapped[a * 2048:(a + 1) * 2048], swapped[v * 2048:(v + 1) * 2048] = movie[v * 2048:(v + 1) * 2048], movie[a * 2048:(a + 1) * 2048]
        self.assertTrue(any(p.startswith(("layout", "pack")) for p in sofdec.problems(bytes(swapped))))
        wrong_count = bytearray(movie)
        struct.pack_into("<I", wrong_count, 2 * 2048 + 18 + 0xAE, 999)
        self.assertTrue(any("frame count" in p for p in sofdec.problems(bytes(wrong_count))))
        self.assertTrue(sofdec.problems(movie[:-2048])[0].startswith(("layout", "no program end")))
        self.assertTrue(sofdec.problems(movie[:5000])[0].startswith("structure"))
        self.assertTrue(sofdec.problems(b"\0" * 20480)[0].startswith("structure"))
        no_record = bytearray(movie)
        no_record[2 * 2048 + 32:2 * 2048 + 44] = b"NotSofdecStr"
        self.assertTrue(sofdec.problems(bytes(no_record)))
        crib, _ = synthetic_movie(2, width=256, height=144)
        self.assertTrue(any("256x144" in p for p in sofdec.problems(crib)))
        self.assertEqual(sofdec.problems(crib, size=(256, 144)), [])
        big, _ = synthetic_movie(2, slice_bytes=(140000, 400, 150))
        self.assertTrue(any("largest picture" in p for p in sofdec.problems(big)))

    def test_header_stage_emulation_scans_like_the_traced_code(self):
        movie, _ = synthetic_movie(2)
        self.assertEqual(sofdec.header_stage(movie)[0], list(sofdec.HEADER_STAGE_READS))
        with self.assertRaisesRegex(ValueError, "no SofdecStream"):
            sofdec.header_stage(movie[:2 * 2048] + bytes(2048) + movie[3 * 2048:])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe are absent")
class EncoderTests(unittest.TestCase):
    """tools/nfl2k5_intro_encode.py on synthetic clips: retail rules, decode round trip, track choice."""

    @classmethod
    def setUpClass(cls):
        from tools import nfl2k5_intro_encode as encoder
        cls.encoder = encoder
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.clip = cls.root / "clip.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60:duration=3",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(cls.clip)], check=True)
        # three audio tracks: silence, 440 Hz, 1320 Hz (like a recording with several tracks)
        cls.tracks = cls.root / "tracks.mkv"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2",
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-f", "lavfi",
                        "-i", "sine=frequency=440:sample_rate=48000:duration=2", "-f", "lavfi",
                        "-i", "sine=frequency=1320:sample_rate=48000:duration=2", "-map", "0:v", "-map", "1:a",
                        "-map", "2:a", "-map", "3:a", "-t", "2", "-c:v", "libx264", "-c:a", "aac", str(cls.tracks)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def encode(self, clip, name, **options):
        output = self.root / name
        receipt = self.encoder.encode(clip, output, progress=lambda *_: None, **options)
        return output, receipt

    def test_two_second_clip_round_trip(self):
        output, receipt = self.encode(self.clip, "intro.mov", start=0.5, end=2.5,
                                      native=HAVE_UC and XBE.is_file())
        movie = output.read_bytes()
        self.assertEqual(sofdec.problems(movie), [])
        facts = receipt["movie"]
        self.assertEqual((facts["pictures"], facts["width"], facts["height"], facts["audio_samples"]),
                         (60, 640, 480, 96000))
        trip = receipt["decode_round_trip"]
        self.assertTrue(trip["video_frames_identical"] and trip["audio_pcm_identical"])
        self.assertEqual((trip["video_frames"], trip["audio_samples"]), (60, 96000))
        self.assertLessEqual(facts["largest_picture"], sofdec.RETAIL_MAX_PICTURE)
        self.assertEqual(receipt["retail_rules"], "pass")
        self.assertEqual(receipt["runtime_witnessed"], False)
        self.assertIn(receipt["native_header_stage"]["status"], ("accepted", "skipped"))
        if HAVE_UC and XBE.is_file():
            self.assertEqual(receipt["native_header_stage"]["status"], "accepted")
        v = sofdec.video(sofdec.parse(movie).video_es)
        self.assertEqual([g[1] for g in v.gops][:2], [1, 0])        # closed first GOP, open after: retail shape
        self.assertEqual(receipt["loudness"]["target_lufs"], -14.1)
        json.dumps(receipt)

    def test_fits_and_silence(self):
        for fit in ("anamorphic", "crop"):
            output, receipt = self.encode(self.clip, f"{fit}.mov", start=0, end=1, fit=fit, native=False)
            self.assertEqual(sofdec.problems(output.read_bytes()), [])
        output, receipt = self.encode(self.clip, "silent.mov", start=0, end=1, audio_track=None, native=False)
        self.assertEqual(receipt["loudness"], {"applied": "silence"})
        self.assertEqual(sofdec.problems(output.read_bytes()), [])
        mute = self.root / "mute.mp4"                                  # a clip with no audio at all
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(self.clip), "-an", "-c:v", "copy", str(mute)], check=True)
        output, receipt = self.encode(mute, "auto.mov", start=0, end=1, native=False)
        self.assertEqual((receipt["settings"]["audio_track"], receipt["loudness"]), (None, {"applied": "silence"}))
        output, receipt = self.encode(self.clip, "first.mov", start=0, end=1, native=False)
        self.assertEqual(receipt["settings"]["audio_track"], 0)

    def test_audio_track_picks_that_track(self):
        def crossings(path):
            pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1",
                                  "-f", "s16le", "-"], capture_output=True, check=True).stdout
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            loud = max(abs(s) for s in samples)
            return loud, sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0)) / (len(samples) / 48000)
        results = {}
        for track in (0, 1, 2):
            output, receipt = self.encode(self.tracks, f"track{track}.mov", start=0.2, end=1.8, audio_track=track,
                                          loudness=None, native=False)
            self.assertEqual(sofdec.problems(output.read_bytes()), [])
            results[track] = crossings(output)
        self.assertLess(results[0][0], 64)                           # the silent track
        self.assertAlmostEqual(results[1][1] / 2, 440, delta=25)       # zero crossings: 2 per cycle
        self.assertAlmostEqual(results[2][1] / 2, 1320, delta=40)
        with self.assertRaisesRegex(ValueError, "audio track 3 does not exist"):
            self.encode(self.tracks, "track3.mov", audio_track=3, native=False)

    def test_bad_ranges_refuse(self):
        for start, end in ((2.0, 1.0), (0.0, 99.0), (-1.0, 1.0)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.encode(self.clip, "bad.mov", start=start, end=end, native=False)
        self.assertEqual(self.encoder.seconds("1:02.5"), 62.5)
        self.assertEqual(self.encoder.seconds("0:00:14"), 14.0)
        with self.assertRaises(ValueError):
            self.encoder.seconds("14s")


@unittest.skipUnless(PACKS.is_file(), "the retail extraction is absent")
class RetailTests(unittest.TestCase):
    """Every rule above is re-proved on the retail streams themselves."""

    @classmethod
    def setUpClass(cls):
        from tools.nfl_outer import parse_archive, read_entry_range
        from tools.nfl2k5_movie_inventory import NAMES
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(PACKS.parents[1])
        cls.archive, cls.read, cls.names = parse_archive(PACKS), staticmethod(read_entry_range), NAMES

    def stream(self, name):
        index = 4293 + self.names.index(name)
        entry = self.archive.entries[index]
        self.assertEqual(entry.name_id, zlib.crc32(name.upper().encode("utf-16le")))
        return self.read(self.archive, entry, 0, entry.size)

    def test_boot_movie_header_pins(self):
        from mod_editor.core import nfl2k5_intro_videos as boot
        for index, name, size, digest in boot.MOVIES:
            data = self.stream(name)
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (size, digest))
            self.assertEqual(hashlib.sha256(data[:8192]).hexdigest(), BOOT_HEADER_SHA256[name])

    def test_every_retail_adx_stream_remuxes_byte_for_byte(self):
        streams = 0
        for name in self.names:
            data = self.stream(name)
            fields = sofdec.record_fields(sofdec.parse(data).record)
            with self.subTest(name):
                if name == "espn_game_sound.mov":                      # the one AIX stream: not our format
                    self.assertEqual(fields["audio_type"], 4)
                    with self.assertRaises(ValueError):
                        sofdec.remux(data)
                    continue
                self.assertEqual(sofdec.remux(data), data)
                self.assertEqual(sofdec.problems(data, size=(fields["width"], fields["height"])), [])
                self.assertEqual(sofdec.header_stage(data)[0], list(sofdec.HEADER_STAGE_READS))
                streams += 1
        self.assertEqual(streams, 29)

    def test_retail_intro_measures(self):
        facts = sofdec.summary(self.stream("intro.mov"))
        self.assertEqual((facts["pictures"], facts["gops"], facts["audio_samples"], facts["largest_picture"]),
                         (1937, 152, 3102303, 108542))


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn or the pinned USA retail default.xbe is absent")
class NativeTests(unittest.TestCase):
    """The game's own header-stage code (0x178150 -> 0x3CB940 / 0x3CB8B0 / 0x3CB750) on muxed movies."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE differs from the USA evidence pin")

    def run_movie(self, movie):
        from tests.nfl2k5_movie_native import MovieMachine
        m = MovieMachine(self.retail)
        m.uc.mem_write(m.SAVE, "intro\0".encode("utf-16le"))
        m.files["intro.mov"] = lambda at, n: movie[at:at + n] if at + n <= len(movie) else b""
        returned = m.call(0x178150, ecx=m.SAVE, args=(0,), budget=100000)
        return returned, m.reads, m.allocations_seen

    def test_muxed_movie_gets_the_retail_intro_reads_and_allocation(self):
        movie, _ = synthetic_movie(3)
        returned, reads, allocations = self.run_movie(movie)
        self.assertEqual(returned, 0)                                   # allocation is failed on purpose
        self.assertEqual(reads, list(sofdec.HEADER_STAGE_READS))
        self.assertEqual(reads, sofdec.header_stage(movie)[0])
        self.assertEqual(allocations, [sofdec.BOOT_ALLOCATION])
        crib, _ = synthetic_movie(2, width=256, height=144)
        self.assertEqual(self.run_movie(crib)[2], [3138000])             # the size drives the request
        broken = (movie[:2 * 2048 + 32] + b"NotSofdecStr" + movie[2 * 2048 + 44:])[:4 * 2048]
        self.assertEqual(self.run_movie(broken)[2], [])                   # header failure: no allocation


if __name__ == "__main__":
    unittest.main()
