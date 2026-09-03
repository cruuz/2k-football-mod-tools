"""Retail-free tests for tools/nfl2k5_audo_swap.py.

A synthetic XISO (``nfl2k5_xiso_fixture``) carries two ``.iff``-style outer
entries with three AUDO records -- mono and stereo, +0x40 and +0x60 descriptor
pointers, tails of 12 and 0 bytes, one duplicated name across packages -- and a
synthetic catalog in the ``nfl2k5_audo_import_capacity/v1`` shape describing
them.  That exercises catalog validation, disc binding (pack extent and archive
table must agree), metadata identity gates, exact-allocation fitting, in-place
writes, receipts, ambiguity handling and verification without any game data.
"""

from __future__ import annotations

import hashlib
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

import nfl2k5_audo_swap as au  # noqa: E402
import nfl2k5_soundbank_swap as sb  # noqa: E402
import xbox_ima_encoder as ima  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402


def tone_pcm(frames: int, channels: int, rate: int, hz: float = 300.0) -> bytes:
    out: list[int] = []
    for frame in range(frames):
        value = 0.5 * math.sin(2 * math.pi * hz * frame / rate)
        for channel in range(channels):
            out.append(int(value * 32767 * (1 - 0.3 * channel)))
    return struct.pack(f"<{len(out)}h", *out)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_audo(name: str, channels: int, rate: int, blocks: int, *, system_size: int = 128,
              descriptor_offset: int = 0x40, tail: bytes = b"") -> tuple[bytes, bytes]:
    """(wrapper bytes, payload bytes) of one AUDO record exactly as the game stores it."""

    payload = ima.encode_stream(tone_pcm(blocks * 64, channels, rate, 250 + len(name) * 7), channels)
    system = bytearray(system_size)
    system[0x0C:0x10] = b"AUDO"
    struct.pack_into("<i", system, 0x10, 0x20 - 0x0F)
    struct.pack_into("<i", system, 0x14, descriptor_offset - 0x13)
    encoded = name.encode("utf-16le") + b"\0\0"
    system[0x20:0x20 + len(encoded)] = encoded
    struct.pack_into("<8I", system, descriptor_offset, channels, channels, 0x11,
                     0x35 if channels == 1 else 0x75, len(payload), 0, len(payload) // channels, rate)
    body = bytes(system) + payload + tail
    header = struct.pack("<4s7I", b"AUDO", len(body), system_size, len(payload), 0, 0, 0, 0)
    return header + body, payload


class Fixture:
    """Two packages: outer 0 holds records A (mono) and B (stereo); outer 1 holds A's twin."""

    def __init__(self, directory: Path) -> None:
        self.records: list[dict] = []
        wrapper_a, self.payload_a = make_audo("menu-back_01", 1, 16000, 3, tail=bytes(range(12)))
        wrapper_b, self.payload_b = make_audo("chantdef1", 2, 22050, 4, system_size=160,
                                              descriptor_offset=0x60)
        wrapper_c, self.payload_c = make_audo("menu-back_01", 1, 16000, 3, tail=b"\x01\x02\x03\x04")
        package0 = b"FONT" + bytes(0x7C) + wrapper_a + bytes(16) + wrapper_b + bytes(0x40)
        package1 = b"TXTR" + bytes(0x2C) + wrapper_c + bytes(0x20)
        self.disc = SyntheticXiso(directory, [
            (0x8EE9EEED, package0),
            (0x11111111, bytes(0x3000)),          # pushes package1 into pack 1
            (0x22222222, package1),
            (0x33333333, bytes(0x40)),
        ])
        placements = (
            (0, 0, 0x80, wrapper_a, self.payload_a, 128, 12, 0x40, 1, 16000),
            (0, 1, 0x80 + len(wrapper_a) + 16, wrapper_b, self.payload_b, 160, 0, 0x60, 2, 22050),
            (2, 0, 0x30, wrapper_c, self.payload_c, 128, 4, 0x40, 1, 16000),
        )
        pack_names = self.disc.pack_names
        pack_sizes = self.disc.pack_sizes
        for outer, chunk, offset, wrapper, payload, system, tail, desc_off, channels, rate in placements:
            virtual = self.disc.entry_offsets[outer] + offset
            at = 0
            for pack_name, pack_size in zip(pack_names, pack_sizes):
                if at <= virtual < at + pack_size:
                    break
                at += pack_size
            pack_offset = virtual - at
            assert pack_offset + len(wrapper) <= pack_size
            name = wrapper[0x20 + 0x20:0x20 + 0x20 + 64].decode("utf-16le").split("\0")[0]
            self.records.append({
                "key": f"outer_{outer:04d}_chunk_{chunk:04d}",
                "name": name,
                "classification": "structurally-encodable-owner-runtime-unproved",
                "format": {"channels": channels, "sample_rate": rate, "frame_count": len(payload) // (36 * channels) * 64,
                           "payload_allocation_bytes": len(payload), "system_bytes": system, "tail_bytes": tail,
                           "codec_word": "0x00000011"},
                "chunk": {"index": chunk, "offset_in_outer": offset, "stored_body_bytes": len(wrapper) - 0x20,
                          "wrapper_span_bytes": len(wrapper)},
                "descriptor": {"offset_in_body": desc_off},
                "hashes": {"resource_span_sha256": sha(wrapper), "wrapper_header_sha256": sha(wrapper[:0x20]),
                           "system_sha256": sha(wrapper[0x20:0x20 + system]), "payload_sha256": sha(payload),
                           "tail_sha256": sha(wrapper[0x20 + system + len(payload):])},
                "absolute_span": {"pack": {"path": f"vc_53450030/{pack_name}", "start": pack_offset,
                                           "end": pack_offset + len(wrapper)}},
                "groups": {"physical_span_shared": False,
                           "duplicate_name": {"group_id": "name:x", "member_count": 2} if name == "menu-back_01" else None,
                           "equal_decoded_content": None},
            })
        self.catalog = {
            "schema": au.CATALOG_SCHEMA,
            "source": {"packs": [{"name": n, "size": s} for n, s in zip(pack_names, pack_sizes)]},
            "records": self.records,
        }
        self.catalog_path = directory / "catalog.json"
        self.catalog_path.write_text(json.dumps(self.catalog))
        self.loaded = au.load_catalog(self.catalog_path, expected_sha256=None)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_loads_and_orders_records(self) -> None:
        records = self.fx.loaded
        self.assertEqual([r.key for r in records],
                         ["outer_0000_chunk_0000", "outer_0000_chunk_0001", "outer_0002_chunk_0000"])
        self.assertEqual(records[1].channels, 2)
        self.assertEqual(records[1].descriptor_offset, 0x60)
        self.assertEqual(records[1].frame_count, 256)
        self.assertEqual(records[0].duplicate_name_count, 2)
        self.assertEqual(records[0].duration, 192 / 16000)
        self.assertIn("global.iff", au.package_label(3))
        self.assertIn("away side", au.package_label(900))

    def test_rejects_inconsistent_catalog(self) -> None:
        broken = json.loads(json.dumps(self.fx.catalog))
        broken["records"][0]["format"]["payload_allocation_bytes"] += 1
        path = Path(self.tmp.name) / "broken.json"
        path.write_text(json.dumps(broken))
        with self.assertRaises(au.AudoSwapError):
            au.load_catalog(path, expected_sha256=None)
        with self.assertRaises(au.AudoSwapError):
            au.load_catalog(self.fx.catalog_path, expected_sha256="0" * 64)

    def test_selectors(self) -> None:
        records = self.fx.loaded
        self.assertEqual(len(au.select_records(records, names=["menu-*"])), 2)
        self.assertEqual([r.key for r in au.select_records(records, names=["menu-back_01"], outer=2)],
                         ["outer_0002_chunk_0000"])
        self.assertEqual([r.key for r in au.select_records(records, keys=["0:1", "outer_0002_chunk_0000"])],
                         ["outer_0000_chunk_0001", "outer_0002_chunk_0000"])
        self.assertEqual(len(au.select_records(records, all_records=True)), 3)
        with self.assertRaises(au.AudoSwapError):
            au.select_records(records, names=["nothing"])
        with self.assertRaises(au.AudoSwapError):
            au.select_records(records, keys=["9:9"])


class DiscTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fx = Fixture(self.dir)
        self.before = self.fx.disc.path.read_bytes()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _clip(self, name: str, frames: int, channels: int, rate: int) -> Path:
        path = self.dir / name
        sb.write_wav(path, tone_pcm(frames, channels, rate, 900), channels, rate)
        return path

    def test_binding_and_identity(self) -> None:
        with au.AudoDisc(self.fx.disc.path, records=self.fx.loaded) as disc:
            for record in self.fx.loaded:
                resolved = disc.resolve(record)
                facts = au.check_wrapper(disc.read_wrapper(resolved), record, require_retail_payload=True)
                self.assertTrue(facts["retail_payload"])
            b = disc.resolve(self.fx.loaded[2])
            self.assertEqual(b.payload_spans[0].pack_name, "1")
            self.assertEqual(disc.read_payload(b), self.fx.payload_c)
            # A catalog row whose pack span disagrees with the archive table is refused.
            wrong = self.fx.loaded[0].__class__(**{**self.fx.loaded[0].__dict__, "pack_offset": self.fx.loaded[0].pack_offset + 0x20})
            with self.assertRaises(au.AudoSwapError):
                disc.resolve(wrong)

    def test_export(self) -> None:
        out = self.dir / "export"
        with au.AudoDisc(self.fx.disc.path, records=self.fx.loaded) as disc:
            rows = au.export_records(disc, [self.fx.loaded[1]], out)
        channels, rate, pcm = sb.read_wav(out / rows[0]["file"])
        self.assertEqual((channels, rate), (2, 22050))
        self.assertEqual(pcm, ima.decode_stream(self.fx.payload_b, 2))
        self.assertTrue(rows[0]["retail_payload"])

    def test_replace_changes_only_the_payload(self) -> None:
        record = self.fx.loaded[1]                                     # stereo 22050, 4 blocks
        clip = self._clip("clip.wav", 2 * 64 + 10, 2, 22050)           # padded to 4 blocks
        receipt = au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded,
                                     retail_packs=self.fx.disc.retail_packs)
        row = receipt["payloads"][0]
        self.assertEqual(receipt["schema"], "nfl2k5_audo_swap_receipt/v1")
        self.assertEqual(row["retail_gate"], "catalog-hashes+retail-packs")
        self.assertEqual((row["clip_frames"], row["padded_silence_frames"], row["trimmed_frames"]), (138, 118, 0))
        self.assertTrue(row["metadata_preserved"])
        _c, _r, pcm = sb.read_wav(clip)
        expected = ima.encode_stream(sb.fit_pcm(pcm, 2, 256).pcm, 2)
        after = self.fx.disc.path.read_bytes()
        with au.AudoDisc(self.fx.disc.path, records=self.fx.loaded) as disc:
            resolved = disc.resolve(record)
            self.assertEqual(disc.read_payload(resolved), expected)
            wrapper = disc.read_wrapper(resolved)
            facts = au.check_wrapper(wrapper, record, require_retail_payload=False)
            self.assertFalse(facts["retail_payload"])
            start = resolved.payload_spans[0].xiso_offset
        end = start + record.payload_size
        self.assertEqual(after[:start], self.before[:start])
        self.assertEqual(after[end:], self.before[end:])
        self.assertNotEqual(after[start:end], self.before[start:end])
        result = au.verify_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded,
                                   decoded_dir=self.dir / "decoded")
        self.assertTrue(result["all_match"])
        self.assertTrue((self.dir / "decoded" / "outer_0000_chunk_0001_chantdef1.wav").is_file())
        # Second replacement is refused without --force, allowed with it.
        with self.assertRaises(au.AudoSwapError):
            au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded)
        receipt = au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded, force=True)
        self.assertEqual(receipt["payloads"][0]["retail_gate"], "forced")

    def test_trims_long_clip_and_refuses_when_asked(self) -> None:
        record = self.fx.loaded[0]                                     # mono 16000, 3 blocks
        clip = self._clip("long.wav", 10 * 64, 1, 16000)
        with self.assertRaises(sb.SoundbankSwapError):
            au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded, allow_trim=False)
        receipt = au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded)
        self.assertEqual(receipt["payloads"][0]["trimmed_frames"], 448)
        self.assertEqual(receipt["payloads"][0]["fade_out_frames"], 160)

    def test_tampered_metadata_is_refused_even_with_force(self) -> None:
        record = self.fx.loaded[0]
        clip = self._clip("clip.wav", 64, 1, 16000)
        with au.AudoDisc(self.fx.disc.path, writable=True, records=self.fx.loaded) as disc:
            resolved = disc.resolve(record)
            span = resolved.wrapper_spans[0]
            damaged = sb.DiscSpan(span.xiso_offset + 0x20 + 0x40, 4, span.pack_name, span.pack_offset + 0x60)
            disc.write_spans((damaged,), b"\x02\0\0\0")            # descriptor says stereo now
        with self.assertRaises(au.AudoSwapError) as raised:
            au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded, force=True)
        self.assertIn("descriptor", str(raised.exception))

    def test_guard_and_retail_folder_refusals(self) -> None:
        record = self.fx.loaded[0]
        clip = self._clip("clip.wav", 64, 1, 16000)
        with self.assertRaises(sb.SoundbankSwapError):
            au.replace_records(self.fx.disc.path, [record], clip, catalog=self.fx.loaded,
                               guards=[self.fx.disc.path])

    def test_cli_ambiguity_all_matches_and_receipt(self) -> None:
        clip = self._clip("clip.wav", 64, 1, 16000)
        base = [str(self.fx.disc.path), "--catalog", str(self.fx.catalog_path)]
        err = io.StringIO()
        with redirect_stdout(io.StringIO()):
            sys.stderr, saved = err, sys.stderr
            try:
                code = au.main(["replace", *base, "--name", "menu-back_01", "--wav", str(clip)])
            finally:
                sys.stderr = saved
        self.assertEqual(code, 2)
        self.assertIn("2 records match", err.getvalue())
        self.assertEqual(self.fx.disc.path.read_bytes(), self.before)
        receipt_path = self.dir / "receipt.json"
        with redirect_stdout(io.StringIO()):
            code = au.main(["replace", *base, "--name", "menu-back_01", "--all-matches", "--wav", str(clip),
                            "--receipt", str(receipt_path), "--quiet"])
        self.assertEqual(code, 0)
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["records"], ["outer_0000_chunk_0000", "outer_0002_chunk_0000"])
        with redirect_stdout(io.StringIO()):
            code = au.main(["verify", *base, "--name", "menu-back_01", "--wav", str(clip)])
        self.assertEqual(code, 0)
        out = io.StringIO()
        with redirect_stdout(out):
            code = au.main(["list", "--catalog", str(self.fx.catalog_path), "--name", "chant*", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())[0]["name"], "chantdef1")
        with redirect_stdout(io.StringIO()):
            code = au.main(["replace", *base, "--key", "0:1", "--wav", str(clip)])
        self.assertEqual(code, 0)                                     # single key, mono clip -> stereo slot


if __name__ == "__main__":
    unittest.main()
