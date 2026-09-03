"""Retail-free tests for tools/nfl2k5_soundbank_swap.py.

A synthetic XISO (see ``nfl2k5_xiso_fixture``) carries one BANK descriptor and
one external bank of three sub-banks whose middle sub-bank crosses a pack seam.
Slot allocations differ per sub-bank exactly as they do on the retail disc, so
the tests exercise directory parsing, CRC naming, per-sub-bank fitting (pad and
trim), rate/channel conversion, the retail gate, in-place writes, read-back and
receipts without any game data.
"""

from __future__ import annotations

import io
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for candidate in (TOOLS, ROOT, ROOT / "tests"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_soundbank_swap as sb  # noqa: E402
import xbox_ima_encoder as ima  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

BANK_KEY = "test"
BANK_FILE = "test.bnk"
UNNAMED_ID = 0x12345678
# (name or None, channels, rate, blocks per sub-bank)
SLOT_PLAN = (
    ("tip_01", 1, 8000, (4, 6, 4)),
    ("cheer-front_01", 2, 16000, (6, 10, 8)),
    (None, 1, 11025, (2, 2, 2)),
)
SUBBANK_COUNT = 3
FILLER_ID = 0x11111111
TRAILER_ID = 0x22222222


def tone_pcm(frames: int, channels: int, rate: int, hz: float = 300.0, seed: int = 1) -> bytes:
    out: list[int] = []
    for frame in range(frames):
        value = 0.5 * math.sin(2 * math.pi * hz * frame / rate) + 0.05 * math.sin(2.1 * seed * frame)
        for channel in range(channels):
            out.append(max(-32768, min(32767, int(value * 32767 * (1 - 0.2 * channel)))))
    return struct.pack(f"<{len(out)}h", *out)


def build_bank(plan=SLOT_PLAN, subbanks: int = SUBBANK_COUNT, *, break_rule: str | None = None):
    """Return (descriptor entry bytes, external bank bytes, payloads {(slot, sub): bytes})."""

    ids = [sb.sample_name_id(name) if name else UNNAMED_ID for name, *_ in plan]
    payloads: dict[tuple[int, int], bytes] = {}
    for slot, (_name, channels, rate, blocks) in enumerate(plan):
        for sub in range(subbanks):
            frames = blocks[sub] * sb.BLOCK_FRAMES
            payloads[(slot, sub)] = ima.encode_stream(tone_pcm(frames, channels, rate, 200 + 90 * slot, sub + 1),
                                                      channels)
    desc_sizes = [0x80 if channels == 2 else 0x40 for _n, channels, _r, _b in plan]
    desc_offsets = [sum(desc_sizes[:index]) for index in range(len(plan))]
    abnk_size = 8 + 8 * len(plan) + sum(desc_sizes)
    wbnk_sizes = [sum(len(payloads[(slot, sub)]) for slot in range(len(plan))) for sub in range(subbanks)]
    capacity = max(wbnk_sizes)
    stride = sb.WRAPPER_SIZE + abnk_size + sb.WRAPPER_SIZE + capacity + 0x20
    stride += -stride % 64

    external = bytearray()
    for sub in range(subbanks):
        body = bytearray(abnk_size)
        struct.pack_into("<II", body, 0, len(plan), 0)
        data = bytearray()
        for slot, (_name, channels, rate, _blocks) in enumerate(plan):
            slot_ids = list(ids)
            if break_rule == "ids-differ" and sub == 1 and slot == 0:
                slot_ids[0] ^= 1
            struct.pack_into("<II", body, 8 + 8 * slot, slot_ids[slot], desc_offsets[slot])
            payload = payloads[(slot, sub)]
            data_off = len(data)
            size = len(payload)
            if break_rule == "overlap" and slot == 1:
                data_off -= 36
            if break_rule == "not-blocks" and slot == 0:
                size -= 1
            at = 8 + 8 * len(plan) + desc_offsets[slot]
            struct.pack_into("<8I", body, at, channels, channels, sb.CODEC_WORD, data_off, size, 0,
                             size // channels, rate)
            if channels == 2:
                body[at + 0x74:at + 0x80] = "PADDING*PADD".encode("utf-16le")[:12]
            data += payload
        if break_rule == "escapes" and sub == 2:
            data = data[:-36]
        chunk = struct.pack("<4sI6I", b"ABNK", abnk_size, 0, 0, 0, 0, 0, 0) + bytes(body)
        chunk += struct.pack("<4sI6I", b"WBNK", len(data), 0, 0, 0, 0, 0, 0) + bytes(data)
        chunk += b"ENDB"
        chunk += bytes(stride - len(chunk))
        external += chunk

    body = bytearray(0x50 + 4 * subbanks)
    body[:len(BANK_FILE) * 2] = BANK_FILE.encode("utf-16le")
    struct.pack_into("<4I", body, 0x40, subbanks, stride, abnk_size, capacity)
    for sub in range(subbanks):
        struct.pack_into("<I", body, 0x50 + 4 * sub, sb.subbank_file_id(sub))
    descriptor = struct.pack("<4sI6I", b"BANK", len(body), 0, 0, 0, 0, 0, 0) + bytes(body)
    return descriptor, bytes(external), payloads


class Fixture:
    def __init__(self, directory: Path, **bank_kwargs) -> None:
        descriptor, external, self.payloads = build_bank(**bank_kwargs)
        self.disc = SyntheticXiso(directory, [
            (FILLER_ID, bytes(0x2800)),
            (0x33333333, descriptor),
            (sb.outer_name_id(BANK_FILE), external),
            (TRAILER_ID, bytes(0x100)),
        ])
        self.banks = ((BANK_KEY, 1, BANK_FILE),)
        self.external_offset = self.disc.entry_offsets[2]

    def open(self, **kwargs) -> sb.SoundBanks:
        return sb.SoundBanks(self.disc.path, banks=self.banks, **kwargs)


class NamingTests(unittest.TestCase):
    def test_known_names_hash_to_the_documented_ids(self) -> None:
        table = sb.build_name_table()
        self.assertEqual(table[sb.sample_name_id("hit-pads_03")], "hit-pads_03")
        self.assertEqual(sb.subbank_file_id(0), 0xE85AC347)         # CRC32(UTF-16LE "000.iff")
        self.assertEqual(sb.outer_name_id("sfx_game.bnk"), sb.outer_name_id("SFX_GAME.BNK"))

    def test_fit_pads_and_trims(self) -> None:
        pcm = tone_pcm(200, 1, 8000)
        fit = sb.fit_pcm(pcm, 1, 256, sample_rate=8000)
        self.assertEqual((fit.source_frames, fit.padded_frames, fit.trimmed_frames), (200, 56, 0))
        self.assertEqual(fit.pcm[400:], bytes(112))
        fit = sb.fit_pcm(pcm, 1, 128, sample_rate=8000, fade_ms=10)
        self.assertEqual((fit.source_frames, fit.padded_frames, fit.trimmed_frames, fit.fade_frames),
                         (200, 0, 72, 80))
        self.assertEqual(len(fit.pcm), 256)
        self.assertEqual(struct.unpack_from("<h", fit.pcm, 254)[0], 0)      # faded to silence
        with self.assertRaises(sb.SoundbankSwapError):
            sb.fit_pcm(pcm, 1, 128, allow_trim=False)

    def test_resample_and_remix_shapes(self) -> None:
        pcm = tone_pcm(800, 1, 8000)
        up = sb.resample_pcm(pcm, 1, 8000, 16000)
        self.assertEqual(len(up), 1600 * 2)
        down = sb.resample_pcm(pcm, 1, 8000, 4000)
        self.assertEqual(len(down), 400 * 2)
        self.assertEqual(sb.remix_channels(pcm, 1, 2)[:8], pcm[:2] * 2 + pcm[2:4] * 2)
        stereo = sb.remix_channels(pcm, 1, 2)
        self.assertEqual(sb.remix_channels(stereo, 2, 1), pcm)

    def test_synth_kinds(self) -> None:
        tone = sb.synth_pcm("tone", 8000, 2, 0.5, hz=440)
        self.assertEqual(len(tone), 4000 * 4)
        beep = sb.synth_pcm("beep2", 11025, 1, 0.3)
        self.assertEqual(len(beep), round(11025 * 0.3) * 2)
        with self.assertRaises(sb.SoundbankSwapError):
            sb.synth_pcm("noise", 8000, 1, 1)


class ParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bank_geometry_and_names(self) -> None:
        with self.fx.open() as disc:
            bank = disc.bank(BANK_KEY)
            self.assertEqual(bank.subbank_count, SUBBANK_COUNT)
            self.assertEqual([slot.name for slot in bank.slots], ["tip_01", "cheer-front_01", "slot2"])
            self.assertEqual([slot.named for slot in bank.slots], [True, True, False])
            self.assertEqual(bank.slots[1].channels, 2)
            self.assertEqual(bank.slots[1].sample_rates, (16000,))
            self.assertEqual((bank.slots[0].min_bytes, bank.slots[0].max_bytes), (4 * 36, 6 * 36))
            self.assertEqual([layout.trailer_magic for layout in bank.subbanks], ["ENDB"] * 3)
            straddling = [p for p in bank.payloads.values() if len(p.spans) == 2]
            self.assertEqual(len(straddling), 1, "exactly one payload must straddle the pack seam")
            seam = straddling[0]
            self.assertEqual(seam.subbank, 1)
            self.assertEqual({span.pack_name for span in seam.spans}, {"0", "1"})
            self.assertEqual(disc.read_payload(seam), self.fx.payloads[(seam.slot, 1)])
            tip = bank.payload(0, 1)
            self.assertEqual(tip.frame_count, 6 * 64)
            self.assertAlmostEqual(tip.duration, 384 / 8000)
            self.assertEqual(disc.read_payload(tip), self.fx.payloads[(0, 1)])
            self.assertEqual(disc.bank("TEST").key, BANK_KEY)

    def test_selection(self) -> None:
        with self.fx.open() as disc:
            bank = disc.bank(BANK_KEY)
            self.assertEqual([s.index for s in bank.select_slots(["cheer-*", "slot2"])], [1, 2])
            self.assertEqual([s.index for s in bank.select_slots(["TIP_01"])], [0])
            self.assertEqual(len(disc.payloads_for(BANK_KEY, ["tip_01"])), 3)
            self.assertEqual([p.subbank for p in disc.payloads_for(BANK_KEY, ["tip_01"], [2, 0])], [0, 2])
            with self.assertRaises(sb.SoundbankSwapError):
                bank.select_slots(["nothing"])
            with self.assertRaises(sb.SoundbankSwapError):
                disc.payloads_for(BANK_KEY, ["tip_01"], [7])

    def test_export_writes_decoded_wavs(self) -> None:
        out = Path(self.tmp.name) / "export"
        with self.fx.open() as disc:
            rows = sb.export_samples(disc, disc.payloads_for(BANK_KEY, ["cheer-front_01"], [1]), out)
        self.assertEqual(len(rows), 1)
        channels, rate, pcm = sb.read_wav(out / rows[0]["file"])
        self.assertEqual((channels, rate), (2, 16000))
        self.assertEqual(pcm, ima.decode_stream(self.fx.payloads[(1, 1)], 2))
        self.assertTrue((out / "manifest.json").is_file())

    def test_slot_table_counts_distinct_recordings(self) -> None:
        with self.fx.open() as disc:
            rows = sb.slot_table(disc, disc.bank(BANK_KEY))
        self.assertEqual([row["distinct_payloads"] for row in rows], [3, 3, 3])
        self.assertEqual(rows[0]["bytes_min"], 144)

    def test_malformed_banks_fail_closed(self) -> None:
        for rule in ("ids-differ", "overlap", "not-blocks", "escapes"):
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(sb.SoundbankSwapError, msg=rule):
                    Fixture(Path(directory), break_rule=rule).open()

    def test_pinned_bank_mismatch_fails_closed(self) -> None:
        with self.assertRaises(sb.SoundbankSwapError):
            sb.SoundBanks(self.fx.disc.path, banks=((BANK_KEY, 1, "other.bnk"),))
        with self.assertRaises(sb.SoundbankSwapError):
            sb.SoundBanks(self.fx.disc.path, banks=((BANK_KEY, 0, BANK_FILE),))


class ReplaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fx = Fixture(self.dir)
        self.before = self.fx.disc.path.read_bytes()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _clip(self, name: str, frames: int, channels: int, rate: int) -> Path:
        path = self.dir / name
        sb.write_wav(path, tone_pcm(frames, channels, rate, 700), channels, rate)
        return path

    def _changed_ranges(self) -> list[tuple[int, int]]:
        after = self.fx.disc.path.read_bytes()
        self.assertEqual(len(after), len(self.before))
        runs: list[tuple[int, int]] = []
        for index, (a, b) in enumerate(zip(self.before, after)):
            if a != b:
                if runs and runs[-1][1] == index:
                    runs[-1] = (runs[-1][0], index + 1)
                else:
                    runs.append((index, index + 1))
        return runs

    def test_replace_all_subbanks_pads_and_trims_per_allocation(self) -> None:
        clip = self._clip("clip.wav", 5 * 64, 1, 8000)           # 5 blocks: sub-banks hold 4 / 6 / 4
        receipt = sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip,
                                     retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks)
        self.assertEqual(receipt["payload_count"], 3)
        rows = {row["subbank"]: row for row in receipt["payloads"]}
        self.assertEqual((rows[0]["trimmed_frames"], rows[0]["padded_silence_frames"]), (64, 0))
        self.assertEqual((rows[1]["trimmed_frames"], rows[1]["padded_silence_frames"]), (0, 64))
        self.assertTrue(all(row["retail_gate"] == "retail-packs" and row["changed"] for row in rows.values()))
        self.assertFalse(receipt["descriptors_changed"])
        _c, _r, pcm = sb.read_wav(clip)
        with self.fx.open() as disc:
            bank = disc.bank(BANK_KEY)
            for sub in range(3):
                payload = bank.payload(0, sub)
                fit = sb.fit_pcm(pcm, 1, payload.frame_count, sample_rate=8000)
                self.assertEqual(disc.read_payload(payload), ima.encode_stream(fit.pcm, 1))
                self.assertEqual(sb.sha256_bytes(disc.read_payload(payload)), rows[sub]["after_sha256"])
            # Nothing else moved: directories, descriptors, the other slots.
            self.assertEqual(disc.read_payload(bank.payload(1, 1)), self.fx.payloads[(1, 1)])
            spans = [span for sub in range(3) for span in bank.payload(0, sub).spans]
        expected = sorted((span.xiso_offset, span.xiso_offset + span.length) for span in spans)
        merged: list[tuple[int, int]] = []
        for start, end in expected:
            if merged and merged[-1][1] == start:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        changed = self._changed_ranges()
        self.assertTrue(all(any(s >= a and e <= b for a, b in merged) for s, e in changed),
                        f"bytes changed outside the payload spans: {changed} vs {merged}")
        self.assertEqual(len(changed) >= 3, True)
        # verify agrees
        result = sb.verify_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, banks=self.fx.banks,
                                   decoded_dir=self.dir / "decoded")
        self.assertTrue(result["all_match"])
        self.assertTrue((self.dir / "decoded" / "test_tip_01_sb01.wav").is_file())

    def test_replace_single_subbank_and_conversion(self) -> None:
        clip = self._clip("mono8k.wav", 3 * 64, 1, 8000)         # mono 8 kHz into stereo 16 kHz slot
        receipt = sb.replace_samples(self.fx.disc.path, BANK_KEY, ["cheer-front_01"], clip, subbanks=[1],
                                     retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks)
        self.assertEqual(receipt["payload_count"], 1)
        row = receipt["payloads"][0]
        self.assertTrue(row["resampled"] and row["remixed"])
        self.assertEqual(row["clip_frames"], 384)                 # 192 frames resampled x2
        with self.fx.open() as disc:
            bank = disc.bank(BANK_KEY)
            self.assertNotEqual(disc.read_payload(bank.payload(1, 1)), self.fx.payloads[(1, 1)])
            self.assertEqual(disc.read_payload(bank.payload(1, 0)), self.fx.payloads[(1, 0)])
            self.assertEqual(disc.read_payload(bank.payload(1, 2)), self.fx.payloads[(1, 2)])
        with self.assertRaises(sb.SoundbankSwapError):
            sb.replace_samples(self.fx.disc.path, BANK_KEY, ["cheer-front_01"], clip, subbanks=[2],
                               retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks, strict=True)

    def test_retail_gate_refuses_then_force_overwrites(self) -> None:
        clip = self._clip("clip.wav", 64, 1, 8000)
        sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, subbanks=[0],
                           retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks)
        with self.assertRaises(sb.SoundbankSwapError) as raised:
            sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, subbanks=[0],
                               retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks)
        self.assertIn("no longer carries the retail bytes", str(raised.exception))
        receipt = sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, subbanks=[0],
                                     retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks, force=True)
        self.assertEqual(receipt["payloads"][0]["retail_gate"], "forced")
        with self.assertRaises(sb.SoundbankSwapError):
            sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, retail_packs=None,
                               banks=self.fx.banks)
        with self.assertRaises(sb.SoundbankSwapError):
            sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip, retail_packs=None,
                               banks=self.fx.banks, guards=[self.fx.disc.path], force=True)

    def test_gate_fails_before_anything_is_written(self) -> None:
        clip = self._clip("clip.wav", 64, 1, 8000)
        # Damage the retail copy of sub-bank 2 only: the whole replace must refuse, sub-banks 0/1 untouched.
        pack = self.fx.disc.retail_packs / "1"
        data = bytearray(pack.read_bytes())
        with self.fx.open() as disc:
            span = disc.bank(BANK_KEY).payload(0, 2).spans[0]
        data[span.pack_offset] ^= 0xFF
        pack.write_bytes(bytes(data))
        with self.assertRaises(sb.SoundbankSwapError):
            sb.replace_samples(self.fx.disc.path, BANK_KEY, ["tip_01"], clip,
                               retail_packs=self.fx.disc.retail_packs, banks=self.fx.banks)
        self.assertEqual(self.fx.disc.path.read_bytes(), self.before)

    def test_cli_round_trip(self) -> None:
        clip = self._clip("clip.wav", 64, 1, 8000)
        fixture = json.dumps([list(item) for item in self.fx.banks])
        out = io.StringIO()
        with redirect_stdout(out):
            code = sb.main(["list", str(self.fx.disc.path), "--bank", BANK_KEY, "--json",
                            "--banks-fixture", fixture])
        self.assertEqual(code, 0)
        listing = json.loads(out.getvalue())
        self.assertEqual([row["name"] for row in listing["slots"]], ["tip_01", "cheer-front_01", "slot2"])
        receipt_path = self.dir / "receipt.json"
        with redirect_stdout(io.StringIO()):
            code = sb.main(["replace", str(self.fx.disc.path), "--bank", BANK_KEY, "--sample", "slot2",
                            "--wav", str(clip), "--retail-packs", str(self.fx.disc.retail_packs),
                            "--receipt", str(receipt_path), "--quiet", "--banks-fixture", fixture])
        self.assertEqual(code, 0)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["schema"], "nfl2k5_soundbank_swap_receipt/v1")
        self.assertEqual(receipt["samples"], ["slot2"])
        self.assertEqual(len(receipt["payloads"]), 3)
        self.assertTrue(all(row["resampled"] for row in receipt["payloads"]))   # 8 kHz clip -> 11025 slot
        with redirect_stdout(io.StringIO()):
            code = sb.main(["verify", str(self.fx.disc.path), "--bank", BANK_KEY, "--sample", "slot2",
                            "--wav", str(clip), "--banks-fixture", fixture])
        self.assertEqual(code, 0)
        with redirect_stdout(io.StringIO()):
            code = sb.main(["verify", str(self.fx.disc.path), "--bank", BANK_KEY, "--sample", "tip_01",
                            "--wav", str(clip), "--banks-fixture", fixture])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
