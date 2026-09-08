"""Standalone bounded synthetic tests. No disc/evidence/network dependencies."""
from __future__ import annotations

from dataclasses import replace
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/"tests")]
from PIL import Image
from nfl2k5_xiso_fixture import SyntheticXiso
from mod_editor.core import nfl2k5_hires_pack as pack
from mod_editor.core import nfl2k5_hires_texture as texture
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import texture_master
from tools import nfl_txtr as txtr


def fixtures():
    assets, resources = [], {}
    for i, original in enumerate(texture.PILOT_ASSETS):
        a = replace(original, outer=i, chunk=1, name_id=100+i, native=16, levels=1 if i == 0 else 3)
        system = bytearray(128)
        system[12:16] = b"TXTR"
        struct.pack_into("<II", system, 16, 17, a.descriptor-19)
        name = a.name.encode("utf-16le")
        system[32:32+len(name)] = name
        chain_size = sum(w*h for w, h in a.dimensions(1))
        struct.pack_into("<6I", system, a.descriptor, 0, 0, chain_size, a.format_word(1), 0, 0x80000000)
        a = replace(a, system_sha256=texture.sha(system))
        decoded = bytes(system) + bytes(chain_size) + bytes((0,0,0,255))*256
        compressed, _ = txtr.compress_vc_lz(decoded, stream_tag=a.stream_tag, offset_bits=a.offset_bits)
        stored = (len(compressed)+15)&~15
        scratch = (max(stored-len(compressed), txtr.minimum_vc_lz_overlap_scratch(compressed, stored, len(decoded)))+15)&~15
        raw = txtr.HEADER.pack(b"TXTR", stored, 128, chain_size+1024, txtr.COMPRESSED_SENTINEL, scratch, 0, 0)
        raw += compressed + bytes(stored-len(compressed))
        a = replace(a, retail_sha256=texture.sha(raw))
        assets.append(a)
        resources[a.key] = raw
    return tuple(assets), resources


def artwork(path, size=32):
    pixels = bytes(c for y in range(size) for x in range(size)
                   for c in ((x%4)*80, (y%4)*80, ((x+y)%4)*80, 0 if x%4 == 0 else 255))
    Image.frombytes("RGBA", (size,size), pixels).save(path)


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root/"Hi-res"
        self.folder.mkdir()
        self.assets, self.resources = fixtures()
        # Synthetic XISO has a 16-byte dummy XBE; real consumer pins are tested
        # separately against optional retail evidence, never weakened in code.
        consumer = patch.object(pack, "_consumer_check", return_value={"synthetic": True})
        consumer.start()
        self.addCleanup(consumer.stop)
        for module, name, value in ((texture,"ASSETS",self.assets), (pack,"ASSETS",self.assets),
                                    (texture,"BY_KEY",{a.key:a for a in self.assets})):
            p = patch.object(module, name, value)
            p.start()
            self.addCleanup(p.stop)
        for a in self.assets:
            artwork(self.folder/(a.key+".png"))
        opaque = b"TEST"+struct.pack("<I",16)+bytes(24)+b"opaque-neighbour"
        entries = []
        for a in self.assets:
            raw = self.resources[a.key]
            _, system = texture.inspect_span(raw,a)
            rgba = texture.png_rgba((self.folder/(a.key+".png")).read_bytes(),a)
            native = texture.compile_texture(system,rgba,a,1)[0]
            body = opaque+bytes(16)+raw+opaque+bytes(16)
            # The authored native outer ends exactly at a sector boundary;
            # the larger chain must cross it. Fixture stays below 200 KiB.
            body += bytes(2048-len(body)-(len(native)-len(raw)))
            entries.append((a.name_id,body))
        entries.append((999, b"unselected last outer"))
        fixture = SyntheticXiso(self.root, entries, pack_sizes=(2048,)*16,
                                pack_sectors=tuple(64+i for i in range(16)))
        self.source, self.output = fixture.path, self.root/"built.iso"

    def test_pure_replay_native_downscale_and_reupgrade(self):
        self.assertEqual(pack.status(self.resources,self.folder), "retail")
        enlarged, receipt = pack.apply(self.resources,self.folder)
        self.assertEqual(pack.status(enlarged,self.folder), "applied")
        again, replay = pack.apply(enlarged,self.folder)
        self.assertEqual(enlarged,again)
        self.assertTrue(replay["already_applied"])
        native, _ = pack.apply(enlarged,self.folder,scale=1)
        self.assertEqual(pack.status(native,self.folder,scale=1), "applied")
        self.assertEqual(pack.apply(native,self.folder)[0],enlarged)
        self.assertFalse(receipt["runtime_witnessed"])
        self.assertFalse(receipt["memory"]["target_128_available"])
        for row in receipt["assets"]:
            self.assertEqual(row["after"]["mips"][0]["width"],32)
            self.assertEqual(len(row["after"]["mips"]),texture.BY_KEY[row["key"]].levels)
            self.assertEqual(row["compiler"]["quality"]["maximum_channel_error"],0)

    def test_whole_set_mixed_and_foreign_refusal(self):
        enlarged,_ = pack.apply(self.resources,self.folder)
        for mask in range(1,7):
            mixed = {a.key:(enlarged if mask & (1<<i) else self.resources)[a.key] for i,a in enumerate(self.assets)}
            with self.subTest(mask=mask), self.assertRaisesRegex(ValueError,"Mixed"):
                pack.apply(mixed,self.folder)
        wrong = dict(enlarged)
        wrong["helmet"] = wrong["helmet"][:-1]+b"\x19"
        with self.assertRaisesRegex(ValueError,"foreign artwork"):
            pack.apply(wrong,self.folder)
        Image.new("RGBA",(32,32),(1,2,3,255)).save(self.folder/"helmet.png")
        with self.assertRaisesRegex(ValueError,"foreign artwork"):
            pack.apply(enlarged,self.folder)

    def test_all_headers_preflight_before_first_encode(self):
        for offset, value in ((4,0xFFFFFFFF),(8,0xFFFFFFFF),(12,0xFFFFFFFF),(20,0),(24,1)):
            bad = bytearray(self.resources["helmet"])
            struct.pack_into("<I",bad,offset,value)
            resources = dict(self.resources,helmet=bytes(bad))
            with self.subTest(offset=offset), patch.object(texture,"compile_texture") as encode:
                self.assertEqual(pack.status(resources,self.folder),"foreign")
                encode.assert_not_called()

    def test_scale_target_and_png_guards(self):
        for kwargs in ({"scale":4},{"scale":True},{"target":"xemu-128"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                pack.apply(self.resources,self.folder,**kwargs)
        artwork(self.folder/"scorebug.png",16)
        with self.assertRaisesRegex(ValueError,"exact 32x32"):
            pack.apply(self.resources,self.folder)
        (self.folder/"scorebug.png").write_bytes(b"broken png")
        with self.assertRaises(OSError):
            pack.load_folder(self.folder)

    def test_subset_selection_and_empty_folder(self):
        (self.folder/"field_logo.png").unlink()
        (self.folder/"helmet.png").unlink()
        only = {"scorebug":self.resources["scorebug"]}
        self.assertEqual(set(pack.apply(only,self.folder)[0]),{"scorebug"})
        (self.folder/"scorebug.png").unlink()
        with self.assertRaisesRegex(ValueError,"Select one"):
            pack.load_folder(self.folder)

    def test_master_2x_and_4x_import_and_identity_refusal(self):
        for scale in (2,4):
            with self.subTest(scale=scale):
                path = self.folder/"scorebug.2ktexmaster"
                if path.exists(): path.unlink()
                source = self.folder/"scorebug.png"
                artwork(source)
                texture_master.save_texture_master_bundle(destination=path, source_image=source,
                    asset_id="test-scorebug", editor_target="nfl2k5_xbox", native_width=16, native_height=16,
                    high_resolution_scale=scale)
                with self.assertRaisesRegex(ValueError,"either PNG or master"):
                    pack.load_folder(self.folder)
                source.unlink()
                loaded = pack.load_folder(self.folder)
                self.assertEqual(len(loaded["scorebug"][0]),32*32*4)
                self.assertEqual(loaded["scorebug"][1]["preview_scale"],scale)

    def test_real_archive_writer_growth_shrink_identity_and_mips(self):
        source_hash = archive.file_hash(self.source)
        receipt = pack.build_image(self.source,self.output,self.folder)
        self.assertEqual(receipt["verification"]["unchanged_outers"],1)
        self.assertEqual(receipt["verification"]["unchanged_named_files"],1)
        self.assertGreater(receipt["logical_growth"],0)
        self.assertGreater(receipt["physical_growth"],0)
        self.assertEqual(archive.file_hash(self.source),source_hash)
        self.assertEqual(pack.inspect_image(self.output,self.folder)["status"],"applied")
        self.assertEqual(pack.inspect_image(self.output)["status"],"authored-unverified")
        again = self.root/"again.iso"
        replay = pack.build_image(self.output,again,self.folder)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(archive.file_hash(again),archive.file_hash(self.output))
        native = self.root/"native.iso"
        restored = pack.build_image(self.output,native,self.folder,scale=1)
        self.assertLess(restored["logical_growth"],0)
        self.assertEqual(native.stat().st_size,self.output.stat().st_size)
        self.assertEqual(pack.inspect_image(native,self.folder,scale=1)["status"],"applied")

    def test_master_bounds_precede_general_loader(self):
        (self.folder/"scorebug.png").unlink()
        path = self.folder/"scorebug.2ktexmaster"
        for native, source, message in ((15,32,"native canvas"), (16,5000,"16 megapixels")):
            with zipfile.ZipFile(path,"w") as zipped:
                zipped.writestr("manifest.json",json.dumps(dict(native=dict(width=native,height=native),
                    source=dict(width=source,height=source))))
                for name in ("source.png","native.png","high_resolution.png"):
                    zipped.writestr(name,b"not decoded")
            with self.subTest(message=message), patch.object(texture_master,"load_texture_master_bundle") as loader:
                with self.assertRaisesRegex(ValueError,message): pack.load_folder(self.folder)
                loader.assert_not_called()

    def test_source_mutation_and_disk_budget_refuse_publication(self):
        self.output.write_bytes(b"keep")
        with patch.object(archive.shutil,"disk_usage",return_value=type("Disk",(),{"free":0})()):
            with self.assertRaisesRegex(ValueError,"scratch space"):
                pack.build_image(self.source,self.output,self.folder,overwrite=True)
        def mutate(stage,*_):
            if stage == "copy":
                # Unused disc padding is outside named files and archive hashes;
                # the full source digest/identity must still catch this race.
                with self.source.open("r+b") as stream:
                    stream.seek(100); stream.write(b"changed")
        with self.assertRaisesRegex(ValueError,"source changed during build"):
            pack.build_image(self.source,self.output,self.folder,overwrite=True,progress=mutate)
        self.assertEqual(self.output.read_bytes(),b"keep")
        self.assertFalse(list(self.root.glob(".archive-*")))

    def test_failed_write_verification_and_publish_preserve_destination(self):
        before = self.source.read_bytes()
        self.output.write_bytes(b"keep previous build")
        cases = ((pack.transport,"_write_archive"),(pack,"_verify"),(archive.os,"replace"))
        for obj,name in cases:
            with self.subTest(failure=name), patch.object(obj,name,side_effect=OSError("injected")):
                with self.assertRaisesRegex(OSError,"injected"):
                    pack.build_image(self.source,self.output,self.folder,overwrite=True)
            self.assertEqual(self.output.read_bytes(),b"keep previous build")
            self.assertEqual(self.source.read_bytes(),before)
            self.assertFalse(list(self.root.glob(".archive-*")))

    def test_partial_writes_and_cancel_roll_back(self):
        real = archive.io.pwrite
        with patch.object(archive.io,"pwrite",side_effect=lambda fd,b,at: real(fd,b[:7],at)):
            pack.build_image(self.source,self.output,self.folder)
        output_hash = archive.file_hash(self.output)
        def cancel(stage,*_):
            if stage == "archive": raise RuntimeError("cancelled")
        with self.assertRaisesRegex(RuntimeError,"cancelled"):
            pack.build_image(self.source,self.output,self.folder,overwrite=True,progress=cancel)
        self.assertEqual(archive.file_hash(self.output),output_hash)

    def test_hash_readback_catches_unselected_outer_corruption(self):
        real = pack.transport._write_archive
        def corrupt(fd,disc,geometry,*args):
            real(fd,disc,geometry,*args)
            archive.write_virtual(fd,geometry["packs"],geometry["entries"][-1]["offset"],b"!")
        with patch.object(pack.transport,"_write_archive",side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,"Outer 3 hash"):
                pack.build_image(self.source,self.output,self.folder)
        self.assertFalse(self.output.exists())

    def test_source_destination_input_races_and_aliases(self):
        for output in (self.source,self.folder/"scorebug.png"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError,"separate copy|aliases"):
                pack.build_image(self.source,output,self.folder,overwrite=True)
        def destination_race(stage,*_):
            if stage == "copy": self.output.write_bytes(b"concurrent")
        with self.assertRaisesRegex(ValueError,"destination changed"):
            pack.build_image(self.source,self.output,self.folder,progress=destination_race)
        self.assertEqual(self.output.read_bytes(),b"concurrent")
        def input_race(stage,*_):
            if stage == "archive": (self.folder/"scorebug.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"authored input changed"):
            pack.build_image(self.source,self.output,self.folder,overwrite=True,progress=input_race)
        self.assertEqual(self.output.read_bytes(),b"concurrent")

    def test_windows_io_fallback_and_closed_handles_at_replace(self):
        from test_modpack import windows_file_locks
        with windows_file_locks(), patch.object(os,"pread",None,create=True), patch.object(os,"pwrite",None,create=True):
            pack.build_image(self.source,self.output,self.folder)

    def test_failed_constructor_closes_descriptor(self):
        self.source.write_bytes(b"invalid")
        opened = []
        real = os.open
        def track(*args,**kwargs):
            fd = real(*args,**kwargs); opened.append(fd); return fd
        with patch.object(archive.os,"open",side_effect=track):
            try:
                archive.Disc(self.source,descriptors=())
            except ValueError as exc:
                held_traceback = exc.__traceback__
            else:
                self.fail("malformed disc accepted")
        self.assertTrue(held_traceback)
        for fd in opened:
            with self.assertRaises(OSError): os.fstat(fd)


if __name__ == "__main__":
    unittest.main()
