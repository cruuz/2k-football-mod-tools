"""Native proofs for the appended-resource replacement route (fonts, atlas).

Every native case runs the game's own reader, allocator, registry and boot
font-table loop on the grown pack-0 outers under Unicorn. OS I/O completion
is the fixture boundary. Nothing here is a played-game witness.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mod_editor.core import nfl2k5_scorebug_assets as A  # noqa: E402
from mod_editor.core import platform_compat as io  # noqa: E402

PACK = Path(os.environ.get("NFL2K5_RETAIL_INDEX", str(ROOT / "extracted" / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0")))
XBE = PACK.parents[1] / "default.xbe"
XISO = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
SCRATCH = Path(os.environ.get("NFL2K5_ASSETS_SCRATCH", "/media/noah/Storage/.b70-fable-assets"))
HAVE_UC = importlib.util.find_spec("unicorn") is not None
HAVE_PIL = importlib.util.find_spec("PIL") is not None
RETAIL = PACK.is_file() and XBE.is_file()


def _read(fd):
    return lambda count, offset: io.pread(fd, count, offset)


def _extent(read, parts, start, end):
    """Materialise one grown-pack extent from the composed views."""
    out, at = bytearray(), 0
    for source, off, ln in parts:
        if at + ln > start and at < end:
            lo, hi = max(start, at), min(end, at + ln)
            out += source[off + (lo - at):off + (hi - at)] if isinstance(source, bytes) else read(hi - lo, off + (lo - at))
        at += ln
    return bytes(out)


class NativeOuterLoad:
    """The runtime fixture's Collection, parameterised by outer extent."""
    def __init__(self, payload, blob, start, end, heap_bytes=10 * 1024 * 1024):
        import unicorn
        from test_nfl2k5_scorebug_runtime import Machine
        self.m = m = Machine(payload)
        m.uc.mem_map(m.HEAP + 0x400000, 12 * 1024 * 1024)
        self.blob, self.start, self.end = blob, start, end
        self.pending, self.textures, self.fonts, self.closed = [], [], [], False
        heap, pool = m.alloc(0x100), m.alloc(heap_bytes)
        m.record = False
        m.run(0x48640, (heap_bytes,), ecx=heap, edx=pool, limit=10000000)
        # This fixture checks native resources and I/O events directly. It does
        # not consume the full instruction/write history during collection I/O.
        m.put(0xb12034, heap)
        handlers = m.alloc(48)
        m.put(handlers, handlers + 16)
        m.put(handlers + 8, int.from_bytes(b"TXTR", "little"))
        m.put(handlers + 12, 0x44f10)
        m.put(handlers + 24, int.from_bytes(b"AUSB", "little"))
        m.put(handlers + 28, 0x45940)
        m.put(handlers + 16, handlers + 32)
        m.put(handlers + 40, int.from_bytes(b"FONT", "little"))
        m.put(handlers + 44, 0x44c10)
        m.put(0xb0957c, handlers)
        m.put(0xb09584, 1)
        m.put(0xb09598, start)
        m.put(0xb0959c, 0)
        m.put(0xb095a0, end)
        m.put(0xb095a4, 0)
        m.put(0xb095b8, 0)
        m.uc.mem_write(0x48ff0, bytes.fromhex("b801000000c21400"))
        m.uc.mem_write(0x48fc0, b"\xc3")
        m.uc.mem_write(0x43be0, bytes.fromhex("31c0c3"))

        def event(_uc, va, _size, _data):
            if va == 0x48ff0:
                sp = m.uc.reg_read(m.x.UC_X86_REG_ESP)
                lo, hi, size, callback, param = struct.unpack("<5I", m.uc.mem_read(sp + 4, 20))
                ctx, dst = m.uc.reg_read(m.x.UC_X86_REG_ECX), m.uc.reg_read(m.x.UC_X86_REG_EDX)
                if self.pending or hi or size > 8 * 1024 * 1024:
                    raise AssertionError("overlapping or unbounded native I/O")
                if not self.start <= lo < lo + size <= self.end:
                    raise AssertionError("native read outside the collection extent")
                self.pending.append((lo, size, callback, param, ctx, dst))
            elif va == 0x44da0:
                self.textures.append(m.uc.reg_read(m.x.UC_X86_REG_ECX))
            elif va == 0x44b60:
                self.fonts.append(m.uc.reg_read(m.x.UC_X86_REG_ECX))
            elif va == 0x48fc0:
                self.closed = True
        for address in (0x48ff0, 0x44da0, 0x44b60, 0x48fc0):
            m.uc.hook_add(unicorn.UC_HOOK_CODE, event, begin=address, end=address)

    def run(self):
        m = self.m
        m.run(0x43a20, ecx=m.context, limit=2000000)
        events = 0
        while self.pending:
            lo, size, callback, param, ctx, dst = self.pending.pop()
            data = self.blob[lo - self.start:lo - self.start + size]
            if len(data) != size:
                raise AssertionError("short fixture read")
            m.uc.mem_write(dst, bytes(data))
            for offset, value in ((0, lo + size), (4, 0), (0x18, size), (0x1c, dst), (0x20, 0)):
                m.put(ctx + offset, value)
            m.run(callback, (param,), edx=ctx, limit=3000000)
            events += 1
            if events > 3000:
                raise AssertionError("native callback event bound exceeded")
        if not self.closed or m.get(0xb09584) or m.get(0xb09598) != m.get(0xb095a0):
            raise AssertionError("native collection did not finish exactly at EOF")
        return dict(events=events, textures=len(self.textures), fonts=len(self.fonts))

    def utf16(self, at):
        out = bytearray()
        for i in range(128):
            unit = bytes(self.m.uc.mem_read(at + 2 * i, 2))
            if unit == b"\0\0":
                return out.decode("utf-16le")
            out += unit
        raise AssertionError("unterminated fixture string")

    def lookup(self, kind, name):
        m = self.m
        m.run(0x449e0, (m.string(name),), ecx=0, edx=int.from_bytes(kind.encode(), "little"), limit=500000)
        return m.uc.reg_read(m.x.UC_X86_REG_EAX)


@unittest.skipUnless(RETAIL and HAVE_PIL, "pinned retail pack 0 and Pillow required")
class ChunkBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fd = os.open(PACK, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        cls.read = staticmethod(_read(cls.fd))

    @classmethod
    def tearDownClass(cls):
        os.close(cls.fd)

    def test_slot9_font_chunk_layout_parses_with_the_repo_font_parser(self):
        from nfl_main_menu_font import parse_font
        from nfl_scene_probe import ResourceRecord
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        chunk, receipt = A.espn_font_chunk(A.retail_font_span(self.read, 7), A.FontSpec(A.SLOT9_NAME, cap=21))
        parsed_chunk, decoded, _ = r.decode(chunk)
        self.assertEqual(parsed_chunk.kind, "FONT")
        self.assertEqual(receipt["resident_bytes"], parsed_chunk.system_bytes + parsed_chunk.video_bytes)
        record = ResourceRecord(A.GLOBAL_OUTER, f"{A.GLOBAL_ID:08x}", A.GLOBAL_SIZE, 224, A.GLOBAL_SIZE, "FONT",
                                len(chunk) - 32, parsed_chunk.system_bytes, parsed_chunk.video_bytes, 0, 0)
        font = parse_font(9, A.SLOT9_NAME, record, decoded, A.digest(decoded))
        self.assertEqual((font.width, font.height), (256, 256))
        self.assertEqual(font.minimum, ord(" "))
        glyphs = {chr(g.codepoint): g for g in font.glyphs}
        for char in "0123456789&:":
            self.assertGreater(glyphs[char].advance, 0, char)
            self.assertGreater(glyphs[char].uv[2], glyphs[char].uv[0], char)
        self.assertEqual(glyphs["~"].advance > 0, True)
        self.assertLess(receipt["resident_bytes"], 80 * 1024)

    def test_atlas_chunk_is_a_256x512_p8_texture_named_score_buga(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        image = A.atlas_2026()
        chunk, receipt = A.texture_chunk("score_buga", image, A.retail_texture_span(self.read, "score_buga"))
        parsed, decoded, _ = r.decode(chunk)
        tex = r.tx.parse_texture(decoded, parsed)
        self.assertEqual((tex.width, tex.height, tex.name, tex.format_name), (256, 512, "score_buga", "P8"))
        self.assertEqual(receipt["resident_bytes"], 128 + 256 * 512 + 1024)
        for abbr in ("KC", "DEN", "WAS"):
            u0, v0, u1, v1 = A.logo_uv(abbr)
            self.assertTrue(0 <= u0 < u1 <= 1 and 0.5 <= v0 < v1 <= 1, abbr)

    def test_grown_pack_keeps_every_retail_byte_and_moves_only_later_sectors(self):
        import nfl_outer as outer
        chunk, _ = A.espn_font_chunk(A.retail_font_span(self.read, 7), A.FontSpec(A.SLOT9_NAME, cap=21))
        parts, growth = A.grow_pack(self.read, A.PACK_SIZE, {A.GLOBAL_OUTER: [chunk]})
        self.assertEqual(growth["size_after"], A.PACK_SIZE + growth["growth"])
        table = parts[0][0]
        count = struct.unpack_from("<I", table, 0)[0]
        retail = bytearray(self.read(outer.HEADER_SIZE + count * 12, 0))
        for index in range(count):
            ident, length, sector = struct.unpack_from("<3I", table, outer.HEADER_SIZE + index * 12)
            r_ident, r_length, r_sector = struct.unpack_from("<3I", retail, outer.HEADER_SIZE + index * 12)
            self.assertEqual(ident, r_ident)
            if index == A.GLOBAL_OUTER:
                self.assertEqual(length, r_length + len(chunk) + (-len(chunk)) % 16)
                self.assertEqual(sector, r_sector)
            elif index < A.GLOBAL_OUTER:
                self.assertEqual((length, sector), (r_length, r_sector))
            else:
                self.assertEqual(length, r_length)
                self.assertEqual(sector, r_sector + growth["growth"] // 2048)
        # the retail global.iff bytes are intact in front of the appended chunk
        blob = _extent(self.read, parts, A.GLOBAL_START, A.GLOBAL_START + A.GLOBAL_SIZE + 16)
        self.assertEqual(blob[:A.GLOBAL_SIZE], self.read(A.GLOBAL_SIZE, A.GLOBAL_START))
        self.assertEqual(blob[A.GLOBAL_SIZE:A.GLOBAL_SIZE + 16], chunk[:16])


@unittest.skipUnless(RETAIL and HAVE_UC and HAVE_PIL, "pinned retail files, Unicorn and Pillow required")
class NativeReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        cls.payload = runtime.apply(XBE.read_bytes())[0]  # the fixture Machine needs the owner's sites
        cls.fd = os.open(PACK, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        cls.read = staticmethod(_read(cls.fd))

    @classmethod
    def tearDownClass(cls):
        os.close(cls.fd)

    def _global(self, chunks):
        parts, growth = A.grow_pack(self.read, A.PACK_SIZE, {A.GLOBAL_OUTER: chunks})
        end = A.GLOBAL_START + growth["outers"][0]["size_after"]
        blob = _extent(self.read, parts, A.GLOBAL_START, end)
        return NativeOuterLoad(self.payload, blob, A.GLOBAL_START, end), growth

    def test_registry_returns_the_most_recent_resource_of_a_name(self):
        from test_nfl2k5_scorebug_runtime import Machine
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        m = Machine(self.payload)
        span = A.retail_font_span(self.read, 3)
        objects = []
        for _ in range(2):
            chunk, decoded, _ = r.decode(span)
            at = m.alloc(len(decoded))
            m.uc.mem_write(at, decoded)
            m.put(0xb12074, at + chunk.system_bytes)
            m.run(0x43e30, (0x44b80,), ecx=at, edx=0x44b60, limit=30000)
            objects.append(m.get(at + 20))
        m.run(0x449e0, (m.string("font4"),), ecx=0, edx=int.from_bytes(b"FONT", "little"), limit=200000)
        self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EAX), objects[1])

    def test_boot_loop_binds_slot9_to_the_appended_font(self):
        chunk, receipt = A.espn_font_chunk(A.retail_font_span(self.read, 7), A.FontSpec(A.SLOT9_NAME, cap=21))
        load, growth = self._global([chunk])
        result = load.run()
        self.assertEqual(result["fonts"], 10)
        m = load.m
        m.uc.mem_write(A.FONT_TABLE, bytes(40))
        m.run(0xEF570, limit=3000000)
        table = [m.get(A.FONT_TABLE + 4 * i) for i in range(10)]
        self.assertTrue(all(table), table)
        by_object = {m.get(base + 0x14): base for base in load.fonts}
        names = [load.utf16(by_object[entry] + 0x20) for entry in table]
        self.assertEqual(names, [f"font{i}" for i in range(1, 10)] + [A.SLOT9_NAME])
        self.assertEqual(by_object[table[9]], load.fonts[-1])
        self.assertLess(growth["growth"], 96 * 1024)

    def test_boot_loop_binds_slot3_to_an_appended_font4_replacement(self):
        chunk, _ = A.espn_font_chunk(A.retail_font_span(self.read, 3), A.FontSpec("font4", cap=11))
        load, _ = self._global([chunk])
        result = load.run()
        self.assertEqual(result["fonts"], 10)
        m = load.m
        m.uc.mem_write(A.FONT_TABLE, bytes(40))
        m.run(0xEF570, limit=3000000)
        table = [m.get(A.FONT_TABLE + 4 * i) for i in range(10)]
        by_object = {m.get(base + 0x14): base for base in load.fonts}
        self.assertEqual(by_object[table[3]], load.fonts[-1], "slot 3 must bind the appended font4, not the retail one")
        self.assertEqual(load.utf16(by_object[table[3]] + 0x20), "font4")
        self.assertEqual(table[9], 0)

    def test_hud_lookup_returns_the_appended_256x512_atlas(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as r
        image = A.atlas_2026()
        chunk, _ = A.texture_chunk("score_buga", image, A.retail_texture_span(self.read, "score_buga"))
        parts, growth = A.grow_pack(self.read, A.PACK_SIZE, {A.HUD_OUTER: [chunk]})
        end = A.HUD_START + growth["outers"][0]["size_after"]
        blob = _extent(self.read, parts, A.HUD_START, end)
        load = NativeOuterLoad(self.payload, blob, A.HUD_START, end)
        result = load.run()
        self.assertGreaterEqual(result["textures"], 45)
        found = load.lookup("TXTR", "score_buga")
        self.assertTrue(found)
        last = load.textures[-1]
        self.assertEqual(found, load.m.get(last + 0x14), "the appended atlas must win the name lookup")
        name = load.utf16(last + 0x20)
        self.assertEqual(name, "score_buga")
        descriptor = load.m.get(last + 0x14)
        fmt = load.m.get(descriptor + 12)
        self.assertEqual(((fmt >> 20) & 0xF, (fmt >> 24) & 0xF), (8, 9), "256 wide, 512 tall")


@unittest.skipUnless(RETAIL and HAVE_PIL and XISO.is_file(), "retail XISO required for the disc transaction")
class DiscTransactionTests(unittest.TestCase):
    def test_apply_in_place_grows_pack0_and_switches_the_node(self):
        if not SCRATCH.is_dir():
            self.skipTest("scratch directory for a disposable disc copy is absent")
        # Validate the disposable output location before touching an old probe.
        # Retail/native-loader checks above remain runnable on a read-only host.
        import errno
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(prefix="scorebug-access-", dir=SCRATCH):
                pass
        except OSError as exc:
            if exc.errno in (errno.EROFS, errno.EACCES, errno.EPERM):
                self.skipTest(f"disposable disc scratch is not writable: {SCRATCH}: {exc}")
            raise
        copy = SCRATCH / "test_assets_transaction.xiso.iso"
        if copy.exists():
            copy.unlink()
        shutil.copyfile(XISO, copy)
        try:
            self.assertEqual(A.image_status(copy), "retail")
            receipt = A.apply_in_place(copy, slot9=A.FontSpec(A.SLOT9_NAME, cap=21), atlas=A.atlas_2026())
            self.assertEqual(receipt["status"], "applied")
            self.assertEqual(A.image_status(copy), "applied")
            self.assertEqual(copy.stat().st_size, XISO.stat().st_size + receipt["image_growth"])
            from mod_editor.core import nfl2k5_scorebug_ingame as ingame
            with copy.open("rb") as stream:
                entries, _ = ingame.layout.xc.parse_xdvdfs(stream.fileno(), copy.stat().st_size)
                entry = entries["vc_53450030/0"]
                self.assertEqual(entry.size, receipt["pack_size"])
                self.assertEqual(entry.byte_offset, receipt["pack_offset"])
                read = _read(stream.fileno())
                head = read(16, entry.byte_offset + A.GLOBAL_START + A.GLOBAL_SIZE)
                self.assertEqual(head[:4], b"FONT")
        finally:
            if copy.exists():
                copy.unlink()


if __name__ == "__main__":
    unittest.main()
