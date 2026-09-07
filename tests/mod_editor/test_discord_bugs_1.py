"""PROVED editor regressions from B3/B9/B11/B14/B16/B22/B12/B10.

Small synthetic fixtures; no network, emulator, or full image/pack allocation.
The community's exact inputs and in-game outcomes remain HYPOTHESIS.
"""
from pathlib import Path
import hashlib
import os
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mod_editor.core import self_update as updates
from mod_editor.core import nfl2k5_source_cache as cachemod
from mod_editor.core import nfl2k5_build_settings as settings
from mod_editor.core import nfl2k5_roster_records as roster
from mod_editor.core.errors import ValidationError
from mod_editor.studio import facade
from mod_editor.studio import project_archive as projects
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
import nfl_tset_png_import as png


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

def png16(samples, transparent):
    channels = len(samples[0])
    return (png.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", len(samples), 1, 16, 0 if channels == 1 else 2, 0, 0, 0))
            + chunk(b"tRNS", struct.pack(">" + "H" * channels, *transparent))
            + chunk(b"IDAT", zlib.compress(b"\0" + b"".join(struct.pack(">" + "H" * channels, *p) for p in samples)))
            + chunk(b"IEND", b""))


class DiscordCoreTests(unittest.TestCase):
    def test_B7_PROVED_retail_catch_patch_replay_is_byte_identical(self):
        from mod_editor.core import nfl2k5_catch_slider as catch
        from mod_editor.core import nfl2k5_throw_tuning as tt
        path = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
        if not path.is_file():
            self.skipTest("Private retail default.xbe is unavailable for the bounded patch replay")
        with path.open("rb") as stream:
            payload = stream.read(16 * 1024 * 1024 + 1)
        self.assertLessEqual(len(payload), 16 * 1024 * 1024)
        once, _ = tt._apply_all(payload, None, True)
        twice, receipt = tt._apply_all(once, None, True)
        self.assertEqual(twice, once)
        self.assertEqual(catch.status(twice), "applied")
        self.assertTrue(receipt["catch_slider_patch"]["already_applied"])

    def test_B3_PROVED_worker_compares_release_identity_and_missing_sidecar_hides_update_now(self):
        from mod_editor.gui import update_ui
        from mod_editor.core import update_check
        observed = []
        worker = update_ui._CheckTask("v1.0-RC86")
        worker.signals.done.connect(observed.append)
        with patch.object(update_check, "_read", return_value=[{"tag_name": "beta-62"}]):
            worker.run()
        self.assertFalse(observed[0].available)
        self.assertEqual(observed[0].current_tag, "beta-62")
        install = updates.InstallKind("tarball", Path("."), ())
        with self.assertRaisesRegex(updates.SelfUpdateError, "sha256"):
            updates.plan_update({"tag_name": "beta-62", "assets": [{"name": "2K5-Mod-Studio-v1.0-RC86.tar.gz",
                "browser_download_url": "https://example.invalid/file", "size": 4}]}, install)

    def test_B3_PROVED_missing_sidecar_is_refused_before_download(self):
        asset = updates.ReleaseAsset("a.tar.gz", "https://example.invalid/a", 4)
        plan = updates.UpdatePlan("2k5", "beta-62", updates.InstallKind("tarball", Path("."), ()), asset, None)
        with tempfile.TemporaryDirectory() as tmp, patch.object(updates, "download") as download:
            with self.assertRaisesRegex(updates.SelfUpdateError, "sha256"):
                updates.fetch_update(plan, Path(tmp))
            download.assert_not_called()

    def test_B22_PROVED_gameplay_settings_survive_project_archive(self):
        state = dict(catch_slider=True, dynamic_kickoff=True, momentum=50, screen_timing="D", abilities=True, abilities_off_week=5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "gameplay.2k5mod"
            projects.save_project_archive(catalog=None, asset_io=None, edits=(), destination=path, build_settings=state)
            loaded = projects.load_project_archive(source=path, catalog=None, asset_io=None, private_root=path.parent)
            try:
                self.assertEqual(loaded.build_settings, state)
            finally:
                loaded.cleanup()

    def test_B22_PROVED_invalid_choices_refuse_without_mutating_input(self):
        from copy import deepcopy
        from mod_editor.core.mod_build import BuildPlan, CommentarySwap
        plan = BuildPlan("source", "target", overwrite=True, catch_slider=True,
                         playbook_packs=("own.2k5book",), commentary=[CommentarySwap("line", "own.wav")])
        state = settings.from_plan(plan)
        restored = settings.to_plan(state, "new source", "new target")
        self.assertFalse(restored.overwrite)
        self.assertEqual(restored.commentary, plan.commentary)
        self.assertNotIn("source", state)
        before = deepcopy(state)
        settings.build_settings(state)
        self.assertEqual(state, before)
        for invalid in (dict(catch_slider="yes"), dict(momentum=True), dict(abilities_off_week=99),
                        dict(screen_timing="E"), dict(max_deep_yards=float("inf")), dict(source="other.iso")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                settings.build_settings(invalid)

    def test_B11_PROVED_other_disc_cannot_reuse_retail_cache_without_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "modded.iso"
            path.write_bytes(b"different archive")
            source = SimpleNamespace(recognized=True, fingerprint_id="nfl2k5-usa-retail-xiso", kind="xiso", sha256="a" * 64, size=path.stat().st_size)
            cache = cachemod.Nfl2k5SourceCache(Path(tmp))
            cache.inspector = SimpleNamespace(inspect=lambda *args: source)
            # A cache hit must still read/validate this image. This is deliberately
            # not a valid XDVDFS file, so no real packs can be extracted or copied.
            with patch.object(cache, "_ensure_private_cache_root"), patch.object(cache, "_load_existing", return_value=SimpleNamespace(root=Path(tmp))):
                with self.assertRaises((ValidationError, ValueError, OSError)):
                    cache.index(path)

    def test_B11_PROVED_disc_digest_namespaces_cached_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.iso"
            path.write_bytes(b"bounded fixture")
            cache = cachemod.Nfl2k5SourceCache(Path(tmp))
            source = SimpleNamespace(recognized=True, fingerprint_id="nfl2k5-usa-retail-xiso", kind="xiso", sha256="b" * 64, size=path.stat().st_size)
            cache.inspector = SimpleNamespace(inspect=lambda *args: source)
            with patch.object(cache, "_ensure_private_cache_root"), patch.object(cache, "_verify_cached_source"), \
                 patch.object(cache, "_load_existing", return_value=object()) as load:
                cache.index(path)
            self.assertEqual(load.call_args.args[0], Path(tmp) / source.sha256)

    def test_B11_PROVED_same_packs_in_different_layout_pass_changed_late_pack_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / cachemod.PACK_FOLDER
            reference.mkdir(parents=True)
            disc = root / "alternate.iso"
            payload = bytearray(b"padding!" * 7)
            entries = {}
            for i, name in enumerate("0123456789ABCDEF"):
                block = bytes([i]) * 31
                entries[f"vc_53450030/{name}"] = SimpleNamespace(byte_offset=len(payload), size=len(block), attributes=0)
                payload.extend(block)
                (reference / name).write_bytes(block)
            disc.write_bytes(payload)
            with patch.object(cachemod.xiso, "parse_xdvdfs", return_value=(entries, None)):
                cachemod.Nfl2k5SourceCache._verify_cached_source(disc, SimpleNamespace(root=root), None)
                payload[entries["vc_53450030/B"].byte_offset] ^= 1
                disc.write_bytes(payload)
                with self.assertRaisesRegex(ValidationError, "pack B.*differs"):
                    cachemod.Nfl2k5SourceCache._verify_cached_source(disc, SimpleNamespace(root=root), None)
            # Refusal closed every reader, including on Windows.
            disc.unlink()


    def test_B14_PROVED_short_first_name_can_be_replaced_through_pool(self):
        doc = roster.RosterDocument(synthetic_body())
        player = doc.players[0]
        doc.set_name(player, "first", "Tom")
        doc.set_name(player, "first", "Michael")
        rebuilt = roster.RosterDocument(doc.to_body())
        self.assertEqual(rebuilt.players[0].first, "Michael")
        self.assertEqual(len(doc.original), len(doc.to_body()))

    def test_B14_PROVED_full_pool_explains_capacity_and_keeps_roster_unchanged(self):
        doc = roster.RosterDocument(synthetic_body())
        doc.set_name(doc.players[0], "first", "Tom")
        before = doc.to_body()
        with self.assertRaisesRegex(roster.RosterPoolFull, "needs 24 bytes.*largest free block"):
            doc.set_name(doc.players[0], "first", "Christopher")
        self.assertEqual(doc.to_body(), before)

    def test_B12_PROVED_portrait_id_survives_roster_recipe_and_name_change(self):
        body = synthetic_body()
        doc = roster.RosterDocument(body)
        player = doc.players[0]
        player.record.set("photo_id", 1234)
        doc.set_name(player, "first", "Drake")
        doc.set_name(player, "last", "Maye")
        rebuilt, _ = roster.apply_body(body, roster.edits_document(doc))
        result = roster.RosterDocument(rebuilt).players[0]
        self.assertEqual((result.first, result.last, result.record.values["photo_id"]), ("Drake", "Maye", 1234))

    def test_B12_PROVED_explicit_photo_selector_wins_over_old_owner_name(self):
        from mod_editor.core.nfl2k5_player_assets import build_player_assets
        asset = SimpleNamespace(kind="player_portrait", asset_id="nfl2k5.portrait.1234", portrait_id="1234", label="Portrait 1234 - Tom Brady")
        row = build_player_assets([dict(name="Drake Maye", face_id="1234", photo_id=1234)], [asset])[0]
        self.assertEqual([(a.asset_id, a.link) for a in row.portrait_assets], [(asset.asset_id, "photo_id")])
        absent = build_player_assets([dict(name="Tom Brady", face_id="1234", photo_id=4567)], [asset])[0]
        self.assertFalse(absent.portrait_assets)
        self.assertIn("absent", " ".join(absent.notes))

    def test_B12_PROVED_confirmation_distinguishes_present_missing_and_unavailable(self):
        import json
        doc = roster.RosterDocument(synthetic_body())
        player = doc.players[0]
        player.record.set("photo_id", 1234)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "portraits.json"
            self.assertIn("unavailable", roster.portrait_confirmation(doc, player, path))
            path.write_text(json.dumps({"targets": [{"name": "1234"}]}))
            message = roster.portrait_confirmation(doc, player, path)
            self.assertIn("Portrait 1234", message)
            self.assertIn("same disc build", message)
            player.record.set("photo_id", 4567)
            self.assertIn("no cataloged portrait", roster.portrait_confirmation(doc, player, path))

    def test_B16_PROVED_windows_PE_validation_checks_file_kind_and_OS_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xemu.exe"
            data = bytearray(512)
            data[:2] = b"MZ"
            struct.pack_into("<I", data, 60, 64)
            data[64:68] = b"PE\0\0"
            struct.pack_into("<HH", data, 68, 0x8664, 1)
            struct.pack_into("<HHH", data, 84, 240, 2, 0x20b)
            path.write_bytes(data)
            facade._validate_xemu_executable(path, windows=True, machine="AMD64")
            with self.assertRaisesRegex(ValidationError, "64-bit Windows"):
                facade._validate_xemu_executable(path, windows=True, machine="x86")
            with patch.dict(os.environ, {"PROCESSOR_ARCHITEW6432": "AMD64"}):
                facade._validate_xemu_executable(path, windows=True)
            for bad in (b"PK archive", b"\x7fELF", b"MZ truncated"):
                path.write_bytes(bad)
                with self.assertRaises(ValidationError):
                    facade._validate_xemu_executable(path, windows=True, machine="AMD64")
            with self.assertRaisesRegex(ValidationError, "Shortcuts"):
                facade._validate_xemu_executable(path.with_suffix(".lnk"), windows=True)


    def test_B16_PROVED_winerror_193_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "built.iso"
            iso.write_bytes(b"small fixture")
            error = OSError("not a valid Win32 application")
            error.winerror = 193
            studio = facade.Nfl2k5StudioFacade(uniform_catalog=object(), visual_catalog=object(), xemu_command=("xemu",), process_launcher=Mock(side_effect=error))
            studio.register_external_build(iso)
            with self.assertRaisesRegex(ValidationError, "xemu.exe.*64-bit|64-bit.*xemu.exe"):
                studio.launch_xemu(lambda *args: None)

    def test_B10_PROVED_16_bit_transparency_compares_full_samples(self):
        for first, second in (((0x1234,), (0x12ff,)), ((0x1234, 0x5678, 0x9abc), (0x12ff, 0x5678, 0x9abc))):
            with self.subTest(channels=len(first)):
                _, _, rgba = png.decode_rgba_png(png16([first, second], first), (2, 1))
                self.assertEqual(rgba[3::4], b"\0\xff")

    def test_B10_PROVED_actual_Adam7_RGB_with_profile_and_DDS_refusal(self):
        from mod_editor.core.nfl2k5_asset_io import Nfl2k5AssetIO
        width, height = 9, 5
        expected = bytes(v for y in range(height) for x in range(width) for v in (x, y, 42, 255))
        raw = bytearray()
        for x0, y0, dx, dy in png._ADAM7:
            for y in range(y0, height, dy):
                xs = list(range(x0, width, dx))
                if xs:
                    raw.append(0)
                    for x in xs:
                        raw.extend((x, y, 42))
        payload = (png.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 1))
                   + chunk(b"iCCP", b"profile\0\0" + zlib.compress(b"bounded synthetic profile metadata"))
                   + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        self.assertEqual(png.decode_rgba_png(payload, (width, height))[2], expected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pants.dds"
            path.write_bytes(b"DDS " + bytes(124))
            with self.assertRaisesRegex(ValidationError, "9x5 PNG.*DDS import is not supported"):
                Nfl2k5AssetIO.validate_replacement(SimpleNamespace(label="Pants", width=9, height=5), path)


if __name__ == "__main__":
    unittest.main()
