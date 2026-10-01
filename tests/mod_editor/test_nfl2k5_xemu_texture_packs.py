"""Texture packs for the xemu 2K5 Edition: the x2 key, the canonical XXH3, the disc catalog, packs.

Synthetic data only: the XXH3 vectors come from xxHash 0.8.3's C library (the copy in the xemu 0.8.136 tree),
the disc is the shared synthetic XISO fixture, and every image is generated here.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mod_editor.core import nfl2k5_xemu_texture_packs as tp  # noqa: E402
from mod_editor.core.xxh3 import xxh3_64  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402
import nfl_txtr as txtr  # noqa: E402


def lcg_bytes(n: int, seed: int) -> bytes:
    """The fill of the C vector generator (xxh3ref.c): x = x * 1103515245 + 12345, byte = x >> 16."""
    x = (seed * 2654435761 + 12345) & 0xFFFFFFFF
    out = bytearray(n)
    for i in range(n):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        out[i] = (x >> 16) & 0xFF
    return bytes(out)


# XXH3_64bits (xxHash 0.8.3, seed 0) of lcg_bytes(n, n), from the C library.
C_VECTORS = {
    0: 0x2d06800538d394c2, 1: 0x76033e85f0acf92d, 2: 0x3d90c1c9ffc353ff,
}


class Xxh3Test(unittest.TestCase):
    def test_published_values(self) -> None:
        # the three values the Edition's self-test checks at start (x2tex.c hash_self_test)
        self.assertEqual(xxh3_64(b""), 0x2D06800538D394C2)
        self.assertEqual(xxh3_64(bytes(i & 0xFF for i in range(1024))), 0xA870F92984398D22)
        self.assertEqual(xxh3_64(bytes((i * 7) & 0xFF for i in range(100))), 0x6DBB812CF19D012E)

    def test_c_library_vectors(self) -> None:
        vectors = dict(C_VECTORS)
        vectors.update(EXTRA_VECTORS)
        for n, want in sorted(vectors.items()):
            with self.subTest(length=n):
                self.assertEqual(xxh3_64(lcg_bytes(n, n)), want)

    def test_pure_python_long_path(self) -> None:
        from mod_editor.core import xxh3 as module
        for n in (241, 1024, 1025, 4097, 16384):
            with self.subTest(length=n):
                data = lcg_bytes(n, n)
                self.assertEqual(module._long(data, n, use_numpy=False), EXTRA_VECTORS[n])
                self.assertEqual(module._long(data, n, use_numpy=True), EXTRA_VECTORS[n])

    def test_keys_without_numpy(self) -> None:
        import subprocess
        code = (
            "import sys; sys.modules['numpy'] = None; "
            f"sys.path[:0] = [{str(ROOT)!r}, {str(ROOT / 'tools')!r}]; "
            "from mod_editor.core import nfl2k5_xemu_texture_packs as tp; "
            "from mod_editor.core.xxh3 import xxh3_64; "
            "assert xxh3_64(bytes(i & 255 for i in range(1024))) == 0xA870F92984398D22; "
            "print(tp.texture_key(0x06, 16, 16, bytes(range(256)) * 4)); "
            "assert 'numpy' not in sys.modules or sys.modules['numpy'] is None")
        done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertRegex(done.stdout.strip(), r"^x2_16x16_[0-9a-f]{16}_06$")

    def test_every_code_path_is_covered(self) -> None:
        lengths = set(C_VECTORS) | set(EXTRA_VECTORS)
        for lo, hi in ((0, 0), (1, 3), (4, 8), (9, 16), (17, 128), (129, 240), (241, 1024), (1025, 1 << 21)):
            self.assertTrue(any(lo <= n <= hi for n in lengths), (lo, hi))


# More C-library vectors, one or two per code path and the block/stripe seams of the long path.
EXTRA_VECTORS: dict[int, int] = {
    3: 0xdc7dcb0044c640cb, 4: 0x3ba617ae11316f98, 5: 0xa0f9df38d04d8a0d,
    8: 0xd3f287f3174f4b93, 9: 0xae37d37d33f8391c, 15: 0x3432ececfe5710ec,
    16: 0x35fb51824319733d, 17: 0x3768dd857f4663ce, 31: 0x3179275b16f6171d,
    33: 0xf5db0c528b713304, 64: 0x64b03071ad6cd154, 65: 0x1bbf77f9c1ed7ba6,
    96: 0x658ffa74b3bdb0b6, 97: 0xe828a721f7d260e0, 127: 0x3d8237b7243dc1bf,
    128: 0x4972205dfcac7ed4, 129: 0xf2c53ae879b4191c, 200: 0xc7faa4c8ea817852,
    239: 0x08be915461af7ce7, 240: 0x92ed9723268d00ae, 241: 0xebc69fa7ffbd5fc5,
    255: 0xec8e80ff8d09bafa, 256: 0x4009755bb47995d8, 511: 0xb3fe8ba781b667bb,
    600: 0xbbf8ff8e4a0180f0, 1023: 0x3d7ecffeed117d65, 1024: 0x28ffd9d8cd51a54c,
    1025: 0x8260bd4ed9fd033a, 2047: 0xddebb741cad75dcd, 2048: 0x7a5413016fec94a2,
    4095: 0xe001c4f1e7d4f86d, 4096: 0xf01429daaa9bfa66, 4097: 0xd728756f9df267ad,
    16384: 0xde87c0ff962bf254, 65536: 0xc1b8b87df7a2807a, 65537: 0x1a8b4f9d1fd89b81,
    262144: 0x5e139e842e119bdf,
}


def _texture_chunk(kind: str, fmt: int, width: int, height: int, *, compressed: bool = False,
                   palette: bytes | None = None, flags: int = 0x80000000, extra_descriptor: bytes = b"",
                   seed: int = 7) -> tuple[bytes, bytes, bytes | None]:
    """A resource chunk whose system section holds one texture descriptor at 0x40 (and an optional second
    descriptor at 0x60), with level 0 at video offset 0 and the palette after it."""
    level0 = lcg_bytes(tp.level0_size(fmt, width, height), seed)
    video = bytearray(level0)
    palette_offset = 0
    if fmt == tp.P8:
        palette = palette if palette is not None else lcg_bytes(1024, seed + 1)
        palette_offset = len(video)
        video += palette
    video += bytes(-len(video) % 0x80)
    log_w, log_h = width.bit_length() - 1, height.bit_length() - 1
    word_format = 0x29 | (fmt << 8) | (1 << 16) | (log_w << 20) | (log_h << 24)
    system = bytearray(0x100)
    struct.pack_into("<8I", system, 0x40, 0, 0, palette_offset, word_format, 0, flags, 0, 0)
    if extra_descriptor:
        system[0x60:0x60 + len(extra_descriptor)] = extra_descriptor
    output = bytes(system) + bytes(video)
    if compressed:
        body, _info = txtr.compress_vc_lz(output)
        magic = txtr.COMPRESSED_SENTINEL
    else:
        body, magic = output, 0
    body += bytes(-len(body) % 4)
    header = struct.pack("<4s7I", kind.encode("ascii"), len(body), len(system), len(video), magic, 0, 0, 0)
    return header + body, level0, palette


class KeyTest(unittest.TestCase):
    def test_key_layout(self) -> None:
        level0 = bytes(range(256)) * 4
        palette = bytes(1024)
        key = tp.texture_key(tp.P8, 32, 32, level0, palette)
        parts = tp.parse_key(key)
        self.assertEqual((parts.width, parts.height, parts.fmt), (32, 32, 0x0B))
        self.assertEqual(parts.texels, f"{xxh3_64(level0):016x}")
        self.assertEqual(parts.palette, f"{xxh3_64(palette):016x}")
        self.assertEqual(tp.wild_key(key), f"x2_32x32_{parts.texels}_$_0b")
        dxt = tp.texture_key(0x0C, 8, 8, bytes(32))
        self.assertRegex(dxt, r"^x2_8x8_[0-9a-f]{16}_0c$")
        with self.assertRaises(tp.TexturePackError):
            tp.wild_key(dxt)

    def test_level0_sizes(self) -> None:
        self.assertEqual(tp.level0_size(0x0B, 256, 32), 8192)       # P8
        self.assertEqual(tp.level0_size(0x0C, 256, 256), 32768)     # DXT1: 8 bytes per 4x4 block
        self.assertEqual(tp.level0_size(0x0F, 6, 6), 64)            # DXT5 rounds up to whole blocks
        self.assertEqual(tp.level0_size(0x12, 640, 480), 640 * 480 * 4)  # linear A8R8G8B8, no pitch
        with self.assertRaises(tp.TexturePackError):
            tp.level0_size(0x7F, 1024, 32)  # VC's source-only P8 strip is not an NV2A format

    def test_bad_inputs_are_refused(self) -> None:
        with self.assertRaises(tp.TexturePackError):
            tp.texture_key(tp.P8, 16, 16, bytes(255), bytes(1024))
        with self.assertRaises(tp.TexturePackError):
            tp.texture_key(tp.P8, 16, 16, bytes(256), bytes(512))
        for bad in ("x1_16x16_0123456789abcdef_0b", "x2_16x16_0123456789ABCDEF_06", "x2_16_16_0123456789abcdef_06"):
            with self.assertRaises(tp.TexturePackError):
                tp.parse_key(bad)


class DescriptorTest(unittest.TestCase):
    def test_scanner_finds_descriptors_and_rejects_the_rest(self) -> None:
        cube = struct.pack("<8I", 0, 0, 0, 0x2D | (0x0B << 8) | (1 << 16) | (4 << 20) | (4 << 24), 0,
                           0x80000000, 0, 0)
        chunk, _level0, _palette = _texture_chunk("TEST", tp.P8, 16, 16, extra_descriptor=cube)
        chunks = txtr.parse_chunks(chunk)
        output, _ = txtr.decode_chunk(chunk, chunks[0])
        found = tp.scan_descriptors(output[:chunks[0].system_bytes], chunks[0].video_bytes)
        self.assertEqual([(d.offset, d.fmt, d.width, d.height) for d in found], [(0x40, 0x0B, 16, 16)])
        # without the flags bit the scanner does not trust a descriptor
        chunk, _l, _p = _texture_chunk("TEST", 0x06, 16, 16, flags=0)
        chunks = txtr.parse_chunks(chunk)
        output, _ = txtr.decode_chunk(chunk, chunks[0])
        self.assertEqual(tp.scan_descriptors(output[:chunks[0].system_bytes], chunks[0].video_bytes), [])

    def test_level0_past_the_video_section_is_rejected(self) -> None:
        system = bytearray(0x80)
        word_format = 0x29 | (0x06 << 8) | (1 << 16) | (6 << 20) | (6 << 24)  # 64x64 A8R8G8B8 = 16 KiB
        struct.pack_into("<8I", system, 0x20, 0, 0, 0, word_format, 0, 0x80000000, 0, 0)
        self.assertEqual(tp.scan_descriptors(bytes(system), 0x3000), [])
        self.assertEqual(len(tp.scan_descriptors(bytes(system), 0x4000)), 1)


class ChunkWalkTest(unittest.TestCase):
    def test_zero_slots_between_chunks_are_skipped(self) -> None:
        # the FaceTextures aggregate keeps a 32-byte zero slot after every face wrapper
        one, _, _ = _texture_chunk("TXTR", 0x0C, 8, 8, seed=1)
        two, _, _ = _texture_chunk("TXTR", 0x0C, 8, 8, seed=2)
        pad = bytes(-len(one) % 0x10 + 0x20)
        data = one + pad + two + bytes(0x20)
        chunks = list(tp.iter_chunks(data))
        self.assertEqual([(c.index, c.offset) for c in chunks], [(0, 0), (1, len(one) + len(pad))])
        # a gap that does not end on a 16-byte boundary at a bounded header ends the walk
        self.assertEqual(len(list(tp.iter_chunks(one + bytes(0x21) + two))), 1)


class CatalogTest(unittest.TestCase):
    def test_catalog_of_a_synthetic_disc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, level0_a, palette_a = _texture_chunk("TXTZ", tp.P8, 32, 32, seed=11)
            second, level0_b, _ = _texture_chunk("SCNZ", 0x06, 16, 16, compressed=True, seed=12)
            fixture = SyntheticXiso(Path(tmp), [(0x1111, first), (0x2222, second), (0x3333, b"\0" * 64)])
            with tp.DiscArchive(fixture.path) as archive:
                self.assertEqual(len(archive.entries), 3)
                self.assertEqual(archive.read_entry(archive.entries[0])[:len(first)], first)
            rows, errors = tp.catalog_disc(fixture.path, jobs=1)
            self.assertEqual(errors, [])  # the all-zero entry simply has no chunks
            keys = {(r.outer, r.kind): r.key for r in rows}
            self.assertEqual(keys[(0, "TXTZ")], tp.texture_key(tp.P8, 32, 32, level0_a, palette_a))
            self.assertEqual(keys[(1, "SCNZ")], tp.texture_key(0x06, 16, 16, level0_b))

            path = Path(tmp) / "c.tsv"
            tp.write_catalog(rows, path, source={"disc": "synthetic"})
            again = tp.read_catalog(path)
            self.assertEqual([r.key for r in again], [r.key for r in rows])

            # a "modded" disc: the second texture's texels change, the first stays
            second_mod, _, _ = _texture_chunk("SCNZ", 0x06, 16, 16, compressed=True, seed=99)
            fixture2 = SyntheticXiso(Path(tmp) / "mod", [(0x1111, first), (0x2222, second_mod),
                                                        (0x3333, b"\0" * 64)])
            modded, _ = tp.catalog_disc(fixture2.path, jobs=1)
            counts = tp.compare_with_retail(modded, rows)
            self.assertEqual(counts, {"same": 1, "changed": 1, "new": 0})
            self.assertEqual({r.kind: r.changed for r in modded}, {"TXTZ": "same", "SCNZ": "changed"})


def _catalog_rows() -> list[tp.CatalogRow]:
    p8 = tp.texture_key(tp.P8, 16, 16, lcg_bytes(256, 1), lcg_bytes(1024, 2))
    dxt = tp.texture_key(0x0C, 32, 32, lcg_bytes(512, 3))
    linear = tp.texture_key(0x12, 20, 10, lcg_bytes(800, 4))
    return [
        tp.CatalogRow(p8, tp.wild_key(p8), "TXTR", 10, 2, 0x40, tp.P8, 16, 16, 1, name="helm_test"),
        tp.CatalogRow(dxt, "", "TXTR", 11, 0, 0x40, 0x0C, 32, 32, 1, name="face_test"),
        tp.CatalogRow(linear, "", "SCNE", 12, 5, 0x80, 0x12, 20, 10, 1, name="board_test"),
    ]


class PackTest(unittest.TestCase):
    def test_build_validate_install(self) -> None:
        rows = _catalog_rows()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGBA", (64, 64), (200, 30, 30, 255)).save(tmp / "helmet_4x.png")
            Image.new("RGBA", (128, 128), (30, 30, 200, 255)).save(tmp / "face_4x.png")
            Image.new("RGBA", (80, 40), (30, 200, 30, 255)).save(tmp / "board_4x.png")
            manifest = {"name": "Test pack", "priority": 5, "entries": [
                {"image": "helmet_4x.png", "target": {"name": "helm_test"}, "group": "helmets"},
                {"image": "face_4x.png", "target": {"outer": 11, "chunk": 0}},
                {"image": "board_4x.png", "target": {"key": rows[2].key}},
                {"image": "helmet_4x.png", "target": {"name": "helm_test", "any_palette": True}},
            ]}
            (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            pack = tp.build_pack(tmp / "manifest.json", rows, tmp / "pack", disc_label="synthetic")
            self.assertEqual(len(pack["textures"]), 4)
            self.assertIn(rows[0].wild, pack["textures"])
            self.assertEqual(pack["textures"][rows[0].key]["scale"], 4.0)
            written = json.loads((tmp / "pack" / "pack.json").read_text(encoding="utf-8"))
            self.assertEqual((written["schema"], written["priority"], written["key"]), (tp.SCHEMA_PACK, 5, "x2"))
            self.assertTrue((tmp / "pack" / "textures" / "helmets" / f"{rows[0].key}.png").is_file())

            report = tp.validate_pack(tmp / "pack", rows)
            self.assertEqual((report["images"], report["errors"], report["not_on_disc"]), (4, [], []))

            root = tmp / "packs"
            target = tp.install_pack(tmp / "pack", root)
            self.assertTrue((target / "pack.json").is_file())
            self.assertTrue((root / "RELOAD").is_file())
            with self.assertRaises(tp.TexturePackError):
                tp.install_pack(tmp / "pack", root)

    def test_a_name_in_many_files_needs_a_file(self) -> None:
        a = tp.texture_key(tp.P8, 16, 16, lcg_bytes(256, 21), lcg_bytes(1024, 22))
        b = tp.texture_key(tp.P8, 16, 16, lcg_bytes(256, 23), lcg_bytes(1024, 24))
        rows = [tp.CatalogRow(a, tp.wild_key(a), "TXTR", 3762, 51, 0x30, tp.P8, 16, 16, 1, name="splayer",
                              file="18H0.IFF"),
                tp.CatalogRow(b, tp.wild_key(b), "TXTR", 3613, 51, 0x30, tp.P8, 16, 16, 1, name="splayer",
                              file="00H0.IFF")]
        with self.assertRaisesRegex(tp.TexturePackError, "2 archive entries"):
            tp._resolve_targets({"name": "splayer"}, rows)
        self.assertEqual([k for k, _ in tp._resolve_targets({"name": "splayer", "file": "18h0.iff"}, rows)], [a])
        self.assertEqual(len(tp._resolve_targets({"name": "splayer", "all": True}, rows)), 2)

    def test_linear_textures_need_one_scale(self) -> None:
        rows = _catalog_rows()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            Image.new("RGBA", (80, 20), (0, 0, 0, 255)).save(tmp / "bad.png")  # 4x wide, 2x tall
            (tmp / "m.json").write_text(json.dumps({"entries": [
                {"image": "bad.png", "target": {"name": "board_test"}}]}), encoding="utf-8")
            with self.assertRaisesRegex(tp.TexturePackError, "scale both axes"):
                tp.build_pack(tmp / "m.json", rows, tmp / "pack")
        notes = tp.check_image_for_key(rows[0].key, 64, 32)
        self.assertTrue(any("aspect ratio" in n for n in notes))

    def test_validate_flags_bad_names_and_other_discs(self) -> None:
        rows = _catalog_rows()
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "p"
            pack.mkdir()
            Image.new("RGBA", (64, 64)).save(pack / "x2_16x16_zz_0b.png")
            other = tp.texture_key(0x06, 8, 8, bytes(256))
            Image.new("RGBA", (32, 32)).save(pack / f"{other}.png")
            report = tp.validate_pack(pack, rows)
            self.assertEqual(len(report["errors"]), 1)
            self.assertEqual(report["not_on_disc"], [other])

    def test_name_a_dump(self) -> None:
        rows = _catalog_rows()
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp)
            other_palette = tp.parse_key(rows[0].key)
            variant = f"x2_16x16_{other_palette.texels}_{'0' * 16}_0b"
            lines = ["key\tsize\tfmt\tfmt_name\tlevels\tlayout\tvram_offset\tpalette_bytes\tfirst_seen_s\t"
                     "nth_at_offset\tpng_bytes\tsource",
                     f"{rows[1].key}\t32x32\t0x0c\tL_DXT1_A1R5G5B5\t1\tdxt\t0x00100000\t0\t1.0\t1\t10\tguest",
                     f"{variant}\t16x16\t0x0b\tSZ_I8_A8R8G8B8\t1\tswizzled\t0x00200000\t1024\t2.0\t1\t10\tguest",
                     f"{tp.texture_key(0x06, 4, 4, bytes(64))}\t4x4\t0x06\tSZ_A8R8G8B8\t1\tswizzled\t0x00300000"
                     "\t0\t3.0\t1\t10\tguest"]
            (dump / "index.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (dump / "rewrites.tsv").write_text("vram_offset\trewrites\tw\th\tfmt\n0x00300000\t500\t4\t4\tX\n",
                                               encoding="utf-8")
            named = tp.name_dump(dump, rows)
            self.assertEqual([(n.match, n.dynamic) for n in named],
                             [("exact", False), ("any-palette", False), ("none", True)])
            self.assertIn("face_test", named[0].names)
            self.assertIn("helm_test", named[1].names)

    def test_workspace(self) -> None:
        rows = _catalog_rows()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            guest = tmp / "guest.png"
            Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(guest)
            path = tp.make_workspace([(rows[0].key, "helm_test", guest), (rows[1].key, "face_test", None)],
                                     tmp / "ws", scale=4)
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(doc["entries"]), 2)
            with Image.open(tmp / "ws" / "helm_test" / "template_4x.png") as im:
                self.assertEqual(im.size, (64, 64))


if __name__ == "__main__":
    unittest.main()
