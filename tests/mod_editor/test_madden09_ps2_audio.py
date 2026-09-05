"""The Madden 09 (PS2) audio lanes, on a synthetic disc built by the lane itself.

The image these tests run against is ``audio_lane.build_synthetic_audio_disc``:
an ``SLUS-21770``-shaped ISO carrying computed ``SCHl`` streams, computed
``BNKl`` banks, a stream that declares the speech codec so the refusal has
something real to refuse, and a ``QL01`` preload cache carrying byte copies of
one container's header block and one of its members -- the shape the retail
disc's ``GAME.QKL`` and ``FE.QKL`` have.  Not one byte of game audio is
involved.

The evidence that the same lanes read a *real* disc is in
``docs/product/MADDEN09_PS2_AUDIO.md``.  What these tests hold is that the
catalogue is retail-free, that the writer keeps the image's length and the
caches in step, that the verifier fails when it should, and that every refusal
names its fix.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games._formats import ea_schl  # noqa: E402
from mod_editor.games.contract import Edit, Refusal  # noqa: E402
from mod_editor.games.madden09_ps2 import audio_lane  # noqa: E402


class _Room(unittest.TestCase):
    """A temporary folder and one synthetic image, shared by the cases below."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.room = Path(tempfile.mkdtemp(prefix="m09-audio-tests-"))
        cls.source = audio_lane.AudioStreamsLane().synthetic_source(cls.room)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.room, ignore_errors=True)

    def tone(self, name: str, samples: int, channels: int, rate: int) -> Path:
        path = self.room / name
        path.write_bytes(ea_schl.wav_bytes(
            ea_schl.synthetic_pcm(samples, channels, sample_rate=rate), rate, channels))
        return path


class StreamCatalogueTests(_Room):
    """What the catalogue says, and what it must never carry."""

    def setUp(self) -> None:
        self.lane = audio_lane.AudioStreamsLane()
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_every_synthetic_stream_is_listed(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["schema"], audio_lane.STREAM_CATALOG_SCHEMA)
        self.assertEqual(document["streams_seen"], 5)
        self.assertEqual(document["streams_decodable"], 4)
        self.assertEqual(document["streams_speech_codec"], 1)
        self.assertEqual(len(self.catalogue.targets), 5)

    def test_a_member_holding_two_streams_yields_two_targets(self) -> None:
        keys = [target.key for target in self.catalogue.targets]
        self.assertIn("BGM.DAT:2:0", keys)
        self.assertIn("BGM.DAT:2:1", keys)

    def test_the_catalogue_carries_no_audio(self) -> None:
        from mod_editor.games.conformance import contains_payload

        document = dict(self.catalogue.document)
        self.assertFalse(contains_payload(document))
        # Every leaf is a number, a flag or a sentence, and no sentence is long
        # enough to be hiding samples in it.
        def walk(value: object) -> None:
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)
            elif isinstance(value, str):
                self.assertLess(len(value), 2000)
            else:
                self.assertIsInstance(value, (int, float, bool, type(None)))

        walk(document)
        json.dumps(document)

    def test_the_catalogue_reports_how_long_it_took(self) -> None:
        self.assertGreaterEqual(self.catalogue.document["catalogue_seconds"], 0.0)

    def test_a_speech_target_is_listed_and_says_it_is_not_decoded(self) -> None:
        target = self.catalogue.target("SOUNDDAT.DAT:2:0")
        self.assertFalse(target.raw["decodable"])
        self.assertIn("MicroTalk", target.detail)
        self.assertTrue(all(field.read_only for field in target.fields))

    def test_a_decodable_target_offers_a_wav_field(self) -> None:
        target = self.catalogue.target("BGM.DAT:0:0")
        kinds = {field.key: field.kind for field in target.fields}
        self.assertEqual(kinds["wav"], "wav")


class StreamDecodeTests(_Room):
    """Play and Export WAV, and the sound that refuses both."""

    def setUp(self) -> None:
        self.lane = audio_lane.AudioStreamsLane()
        self.catalogue = self.lane.build_catalogue(self.source)

    def test_a_stream_decodes_to_a_wav_of_its_declared_length(self) -> None:
        target = self.catalogue.target("BGM.DAT:0:0")
        payload = self.lane.decode_wav(self.source, target)
        rate, channels, pcm = ea_schl.read_wav(payload)
        self.assertEqual((rate, channels), (22050, 2))
        self.assertEqual(len(pcm) // (2 * channels), target.raw["samples"])

    def test_a_version_two_stream_decodes(self) -> None:
        target = self.catalogue.target("BGM.DAT:1:0")
        rate, channels, pcm = ea_schl.read_wav(
            self.lane.decode_wav(self.source, target))
        self.assertEqual((rate, channels), (28000, 1))
        self.assertEqual(len(pcm) // 2, target.raw["samples"])

    def test_a_speech_stream_refuses_with_the_codec_name(self) -> None:
        target = self.catalogue.target("SOUNDDAT.DAT:2:0")
        with self.assertRaises(Refusal) as caught:
            self.lane.decode_wav(self.source, target)
        self.assertIn("MicroTalk", str(caught.exception))

    def test_a_key_that_names_nothing_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.decode_wav_by_key(self.source, "BGM.DAT:99:0")
        with self.assertRaises(Refusal):
            self.lane.decode_wav_by_key(self.source, "not-a-key")


class StreamCheckEditTests(_Room):
    """The rule, which is the only authority on whether a WAV fits."""

    def setUp(self) -> None:
        self.lane = audio_lane.AudioStreamsLane()
        self.catalogue = self.lane.build_catalogue(self.source)
        self.target = self.catalogue.target("BGM.DAT:0:0")

    def test_no_values_at_all_is_accepted_on_a_decodable_sound(self) -> None:
        self.assertIsNone(self.lane.check_edit(self.target, {}))

    def test_an_unknown_key_is_refused_by_name(self) -> None:
        problem = self.lane.check_edit(self.target, {"png": "x.png"})
        self.assertIn("png", str(problem))

    def test_a_missing_file_is_refused(self) -> None:
        problem = self.lane.check_edit(self.target, {"wav": str(self.room / "nope.wav")})
        self.assertIn("could not be read", str(problem))

    def test_a_wav_that_fits_is_accepted(self) -> None:
        path = self.tone("fits.wav", 2240, 2, 22050)
        self.assertIsNone(self.lane.check_edit(self.target, {"wav": str(path)}))

    def test_a_wav_that_is_too_long_is_refused_with_the_length_it_must_fit(self) -> None:
        path = self.tone("long.wav", 60000, 2, 22050)
        problem = self.lane.check_edit(self.target, {"wav": str(path)})
        self.assertIn(f"{self.target.raw['bytes']:,}", str(problem))
        self.assertIn("Trim it", str(problem))

    def test_a_wav_at_another_rate_is_measured_after_resampling(self) -> None:
        # 2,240 samples at 44,100 Hz becomes 1,120 at this sound's 22,050 Hz,
        # which fits; the check has to resample before it decides.
        path = self.tone("other-rate.wav", 2240, 1, 44100)
        self.assertIsNone(self.lane.check_edit(self.target, {"wav": str(path)}))

    def test_a_speech_sound_refuses_every_edit(self) -> None:
        speech = self.catalogue.target("SOUNDDAT.DAT:2:0")
        self.assertIn("MicroTalk", str(self.lane.check_edit(speech, {})))
        path = self.tone("any.wav", 280, 1, 36000)
        self.assertIn("cannot be replaced",
                      str(self.lane.check_edit(speech, {"wav": str(path)})))


class StreamWriteTests(_Room):
    """Build a new image, and prove the three things a bounded write owes."""

    def setUp(self) -> None:
        self.lane = audio_lane.AudioStreamsLane()
        self.catalogue = self.lane.build_catalogue(self.source)
        self.work = Path(tempfile.mkdtemp(prefix="m09-audio-build-", dir=self.room))
        self.wav = self.tone(f"{self.work.name}.wav", 2240, 2, 22050)
        self.recipe = self.lane.compose_recipe(
            (Edit("BGM.DAT:0:0", {"wav": str(self.wav)}),))

    def test_the_plan_declares_the_container_and_the_cache(self) -> None:
        plan = self.lane.plan(self.source, self.recipe, self.catalogue)
        reasons = " ".join(item.reason for item in plan.declared_ranges)
        self.assertIn("BGM.DAT", reasons)
        self.assertIn("GAME.QKL", reasons)
        self.assertEqual(len(plan.document["preload_copies"]), 1)

    def test_the_plan_writes_nothing(self) -> None:
        before = self.source.read_bytes()
        self.lane.plan(self.source, self.recipe, self.catalogue)
        self.assertEqual(self.source.read_bytes(), before)

    def test_an_unknown_target_is_refused_by_the_plan(self) -> None:
        bogus = self.lane.compose_recipe((Edit("BGM.DAT:9:9", {"wav": str(self.wav)}),))
        with self.assertRaises(Refusal):
            self.lane.plan(self.source, bogus, self.catalogue)

    def test_the_build_keeps_the_length_and_the_verifier_passes(self) -> None:
        destination = self.work / "built.iso"
        receipt = self.lane.build(self.source, destination, self.recipe,
                                  self.catalogue, work_dir=self.work)
        self.assertEqual(destination.stat().st_size, self.source.stat().st_size)
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertGreaterEqual(verdict.document["preload_copies_checked"], 2)
        self.assertGreater(verdict.document["sounds"][0]["snr_db"],
                           audio_lane.SNR_THRESHOLD_DB)

    def test_every_changed_byte_is_inside_a_declared_range(self) -> None:
        destination = self.work / "declared.iso"
        receipt = self.lane.build(self.source, destination, self.recipe,
                                  self.catalogue, work_dir=self.work)
        left = self.source.read_bytes()
        right = destination.read_bytes()
        spans = [(item.start, item.start + item.length)
                 for item in receipt.declared_ranges]
        stray = [index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]
                 and not any(start <= index < end for start, end in spans)]
        self.assertEqual(stray, [])

    def test_the_replaced_sound_reads_back_as_the_wav_that_was_written(self) -> None:
        destination = self.work / "readback.iso"
        self.lane.build(self.source, destination, self.recipe, self.catalogue,
                        work_dir=self.work)
        _rate, _channels, made = ea_schl.read_wav(
            self.lane.decode_wav_by_key(destination, "BGM.DAT:0:0"))
        _rate, _channels, wanted = ea_schl.read_wav(self.wav.read_bytes())
        length = min(len(made), len(wanted))
        self.assertGreater(float(ea_schl.signal_to_noise(wanted[:length], made[:length])),
                           audio_lane.SNR_THRESHOLD_DB)

    def test_the_preload_cache_copy_is_rewritten_with_the_member(self) -> None:
        destination = self.work / "cache.iso"
        self.lane.build(self.source, destination, self.recipe, self.catalogue,
                        work_dir=self.work)
        with audio_lane._DiscAudio(destination) as disc:
            cache = disc.caches()[0]
            member = {index: (start, size)
                      for index, start, size in disc.members("BGM.DAT")}[0]
            copies = [copy for copy in cache.copies
                      if copy.kind == audio_lane.QKL_KIND_MEMBER]
            self.assertEqual(len(copies), 1)
            want = bytes(disc.view[member[0]:member[0] + member[1]])
            got = bytes(disc.view[copies[0].offset:copies[0].offset + member[1]])
            self.assertEqual(got, want)

    def test_a_stale_cache_copy_fails_verification(self) -> None:
        destination = self.work / "stale.iso"
        receipt = self.lane.build(self.source, destination, self.recipe,
                                  self.catalogue, work_dir=self.work)
        with audio_lane._DiscAudio(destination) as disc:
            offset = [copy for copy in disc.caches()[0].copies
                      if copy.kind == audio_lane.QKL_KIND_MEMBER][0].offset
        with open(destination, "r+b") as handle:
            handle.seek(offset + 64)
            byte = handle.read(1)
            handle.seek(offset + 64)
            handle.write(bytes([byte[0] ^ 0xFF]))
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("stale copy", verdict.summary)

    def test_a_change_outside_the_declared_ranges_fails_verification(self) -> None:
        destination = self.work / "tampered.iso"
        receipt = self.lane.build(self.source, destination, self.recipe,
                                  self.catalogue, work_dir=self.work)
        spans = [(item.start, item.start + item.length)
                 for item in receipt.declared_ranges]
        offset = destination.stat().st_size - 1
        while any(start <= offset < end for start, end in spans):
            offset -= 1
        with open(destination, "r+b") as handle:
            handle.seek(offset)
            byte = handle.read(1)
            handle.seek(offset)
            handle.write(bytes([byte[0] ^ 0xFF]))
        verdict = self.lane.verify(self.source, destination, receipt)
        self.assertFalse(verdict.passed)
        self.assertIn("outside every declared range", verdict.summary)

    def test_the_build_refuses_a_destination_that_exists(self) -> None:
        destination = self.work / "twice.iso"
        self.lane.build(self.source, destination, self.recipe, self.catalogue,
                        work_dir=self.work)
        with self.assertRaises(Refusal):
            self.lane.build(self.source, destination, self.recipe, self.catalogue,
                            work_dir=self.work)

    def test_the_build_refuses_to_write_over_the_source(self) -> None:
        with self.assertRaises(Refusal):
            self.lane.build(self.source, self.source, self.recipe, self.catalogue,
                            work_dir=self.work)

    def test_a_recipe_with_no_wav_is_refused_by_the_build(self) -> None:
        recipe = self.lane.compose_recipe((Edit("BGM.DAT:0:0", {}),))
        with self.assertRaises(Refusal) as caught:
            self.lane.build(self.source, self.work / "nowav.iso", recipe,
                            self.catalogue, work_dir=self.work)
        self.assertIn("must name the WAV", str(caught.exception))

    def test_the_conformance_edit_is_one_the_rule_accepts(self) -> None:
        edits = self.lane.conformance_edits(self.catalogue)
        self.assertTrue(edits)
        for edit in edits:
            target = self.catalogue.target(edit.target_key)
            self.assertIsNone(self.lane.check_edit(target, edit.values))


class BankLaneTests(_Room):
    """The extract-only lane, and the reason it stays that way."""

    def setUp(self) -> None:
        self.lane = audio_lane.AudioBanksLane()
        self.catalogue = self.lane.build_catalogue(self.source)
        self.work = Path(tempfile.mkdtemp(prefix="m09-banks-", dir=self.room))

    def test_every_bank_sound_is_listed(self) -> None:
        document = self.catalogue.document
        self.assertEqual(document["banks_read"], 2)
        self.assertEqual(document["sounds_seen"], 3)
        self.assertEqual(document["sounds_playable"], 3)

    def test_a_bank_sound_decodes_to_its_declared_length(self) -> None:
        target = self.catalogue.targets[0]
        rate, channels, pcm = ea_schl.read_wav(self.lane.decode_wav(self.source, target))
        self.assertEqual(rate, target.raw["sample_rate"])
        self.assertEqual(len(pcm) // (2 * channels), target.raw["samples"])

    def test_the_lane_takes_no_values_and_says_why(self) -> None:
        target = self.catalogue.targets[0]
        problem = self.lane.check_edit(target, {"wav": "anything.wav"})
        self.assertIn("loop points", str(problem))
        self.assertIsNone(self.lane.check_edit(target, {}))

    def test_the_export_verifies_against_the_source(self) -> None:
        manifest = self.work / "export.json"
        edits = self.lane.conformance_edits(self.catalogue)
        receipt = self.lane.build(self.source, manifest,
                                  self.lane.compose_recipe(edits), self.catalogue,
                                  work_dir=self.work)
        verdict = self.lane.verify(self.source, manifest, receipt)
        self.assertTrue(verdict.passed, verdict.summary)
        self.assertTrue(manifest.is_file())

    def test_an_extra_file_in_the_export_folder_fails_verification(self) -> None:
        manifest = self.work / "extra.json"
        edits = self.lane.conformance_edits(self.catalogue)
        receipt = self.lane.build(self.source, manifest,
                                  self.lane.compose_recipe(edits), self.catalogue,
                                  work_dir=self.work)
        (self.lane.export_root_for(manifest) / "stray.wav").write_bytes(b"stray")
        self.assertFalse(self.lane.verify(self.source, manifest, receipt).passed)

    def test_the_export_leaves_the_source_alone(self) -> None:
        before = self.source.read_bytes()
        manifest = self.work / "untouched.json"
        self.lane.build(self.source, manifest,
                        self.lane.compose_recipe(self.lane.conformance_edits(
                            self.catalogue)), self.catalogue, work_dir=self.work)
        self.assertEqual(self.source.read_bytes(), before)


class QklTests(_Room):
    """The preload cache reader, on the synthetic cache the disc carries."""

    def test_preload_copies_answers_in_the_shape_the_integrator_swaps(self) -> None:
        # One function, taking the opened image, returning per container the
        # directory copies and the member copies as (cache, offset).  The lane
        # goes through this and nothing else, so the shared reader the art
        # branch landed can replace it in one line.
        from mod_editor.games.madden09_ps2 import containers

        copies = audio_lane.preload_copies(containers.open_disc(self.source))
        self.assertEqual(sorted(copies), ["BGM.DAT"])
        row = copies["BGM.DAT"]
        self.assertEqual(len(row["directory"]), 1)
        self.assertEqual(sorted(row["members"]), [0])
        for cache, offset in row["directory"] + row["members"][0]:
            self.assertTrue(cache.endswith("GAME.QKL"))
            self.assertIsInstance(offset, int)
        self.assertIs(audio_lane._preload_copies, audio_lane.preload_copies)

    def test_an_image_with_no_cache_answers_empty(self) -> None:
        from mod_editor.games.madden09_ps2 import containers

        plain = self.room / "no-cache.iso"
        if not plain.exists():
            # The synthetic disc carries both caches by default since the art
            # writer landed; this test wants an image with neither.
            plain.write_bytes(containers.build_synthetic_disc(preload_caches=False))
        self.assertEqual(audio_lane.preload_copies(containers.open_disc(plain)), {})

    def test_the_cache_names_its_files_and_its_copies(self) -> None:
        with audio_lane._DiscAudio(self.source) as disc:
            caches = disc.caches()
            self.assertEqual(len(caches), 1)
            cache = caches[0]
            self.assertIn("bgm.dat", cache.files)
            self.assertEqual(len(cache.headers_of("BGM.DAT")), 1)
            self.assertEqual(sorted(cache.members_of("BGM.DAT")), [0])

    def test_a_header_copy_matches_the_container_it_copies(self) -> None:
        with audio_lane._DiscAudio(self.source) as disc:
            cache = disc.caches()[0]
            base, _length = disc.span("BGM.DAT")
            block = disc.header_block_bytes("BGM.DAT")
            want = bytes(disc.view[base:base + block])
            copy = cache.headers_of("BGM.DAT")[0]
            self.assertEqual(bytes(disc.view[copy.offset:copy.offset + block]), want)

    def test_a_cache_that_is_not_a_cache_is_refused(self) -> None:
        with self.assertRaises(Refusal):
            audio_lane.parse_qkl(b"NOPE" + bytes(60), 0, 64, "/DATA/X.QKL")


class KeyTests(unittest.TestCase):
    """Every refusal names the shape it wanted."""

    def test_a_well_formed_key_parses(self) -> None:
        self.assertEqual(audio_lane.parse_key("BGM.DAT:12:3", "sound"),
                         ("BGM.DAT", 12, 3))

    def test_a_key_with_the_wrong_shape_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            audio_lane.parse_key("BGM.DAT:12", "sound")
        self.assertIn("<container>:<member>:<index>", str(caught.exception))

    def test_a_key_whose_numbers_are_not_numbers_is_refused(self) -> None:
        with self.assertRaises(Refusal) as caught:
            audio_lane.parse_key("BGM.DAT:a:b", "sound")
        self.assertIn("whole numbers", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
