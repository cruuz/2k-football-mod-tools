"""Sounds tab: catalog, search, fit preview, copy write + receipt, verify and the same-path refusal.

Everything runs on one synthetic XISO (``nfl2k5_xiso_fixture``) that carries the sound-bank
fixture of ``nfl2k5_soundbank_swap_test`` (three slots × three sub-banks, the middle sub-bank
across a pack seam) and two standalone AUDO records built by ``nfl2k5_audo_swap_test``; no
retail disc is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "tests", ROOT / "tools"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import nfl2k5_audo_swap as au  # noqa: E402
import nfl2k5_audo_swap_test as audo_fixture  # noqa: E402
import nfl2k5_soundbank_swap as sb  # noqa: E402
import nfl2k5_soundbank_swap_test as bank_fixture  # noqa: E402
from nfl2k5_xiso_fixture import SyntheticXiso  # noqa: E402

from mod_editor.gui import sounds_panel_qt as module  # noqa: E402
from mod_editor.gui.sounds_panel_qt import STANDALONE, SoundsError, SoundsPanel  # noqa: E402

BANK = bank_fixture.BANK_KEY          # "test": tip_01 (mono 8 kHz, 4/6/4 blocks), cheer-front_01, slot2
PACKAGE_OUTER = 3


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SoundsFixture:
    """One synthetic XISO holding the bank fixture and two standalone AUDO records."""

    def __init__(self, directory: Path) -> None:
        descriptor, external, self.bank_payloads = bank_fixture.build_bank()
        wrapper_a, self.payload_a = audo_fixture.make_audo("menu-back_01", 1, 16000, 3, tail=bytes(range(12)))
        wrapper_b, self.payload_b = audo_fixture.make_audo("chantdef1", 2, 22050, 4, system_size=160,
                                                           descriptor_offset=0x60)
        package = b"FONT" + bytes(0x7C) + wrapper_a + bytes(16) + wrapper_b + bytes(0x40)
        self.disc = SyntheticXiso(directory, [
            (bank_fixture.FILLER_ID, bytes(0x2800)),
            (0x33333333, descriptor),
            (sb.outer_name_id(bank_fixture.BANK_FILE), external),
            (0x8EE9EEED, package),
            (bank_fixture.TRAILER_ID, bytes(0x100)),
        ])
        self.banks = ((BANK, 1, bank_fixture.BANK_FILE),)
        rows = []
        placements = (
            (0, 0x80, wrapper_a, self.payload_a, 128, 12, 0x40, 1, 16000),
            (1, 0x80 + len(wrapper_a) + 16, wrapper_b, self.payload_b, 160, 0, 0x60, 2, 22050),
        )
        for chunk, offset, wrapper, payload, system, tail, desc_off, channels, rate in placements:
            virtual = self.disc.entry_offsets[PACKAGE_OUTER] + offset
            at = 0
            for pack_name, pack_size in zip(self.disc.pack_names, self.disc.pack_sizes):
                if at <= virtual < at + pack_size:
                    break
                at += pack_size
            pack_offset = virtual - at
            assert pack_offset + len(wrapper) <= pack_size, "record straddles a pack seam"
            name = wrapper[0x40:0x40 + 64].decode("utf-16le").split("\0")[0]
            rows.append({
                "key": f"outer_{PACKAGE_OUTER:04d}_chunk_{chunk:04d}",
                "name": name,
                "classification": "structurally-encodable-owner-runtime-unproved",
                "format": {"channels": channels, "sample_rate": rate,
                           "frame_count": len(payload) // (36 * channels) * 64,
                           "payload_allocation_bytes": len(payload), "system_bytes": system, "tail_bytes": tail,
                           "codec_word": "0x00000011"},
                "chunk": {"index": chunk, "offset_in_outer": offset, "stored_body_bytes": len(wrapper) - 0x20,
                          "wrapper_span_bytes": len(wrapper)},
                "descriptor": {"offset_in_body": desc_off},
                "hashes": {"resource_span_sha256": _sha(wrapper), "wrapper_header_sha256": _sha(wrapper[:0x20]),
                           "system_sha256": _sha(wrapper[0x20:0x20 + system]), "payload_sha256": _sha(payload),
                           "tail_sha256": _sha(wrapper[0x20 + system + len(payload):])},
                "absolute_span": {"pack": {"path": f"vc_53450030/{pack_name}", "start": pack_offset,
                                           "end": pack_offset + len(wrapper)}},
                "groups": {"physical_span_shared": False, "duplicate_name": None, "equal_decoded_content": None},
            })
        catalog = {"schema": au.CATALOG_SCHEMA,
                   "source": {"packs": [{"name": n, "size": s}
                                        for n, s in zip(self.disc.pack_names, self.disc.pack_sizes)]},
                   "records": rows}
        self.catalog_path = directory / "catalog.json"
        self.catalog_path.write_text(json.dumps(catalog), encoding="utf-8", newline="\n")
        self.records = au.load_catalog(self.catalog_path, expected_sha256=None)
        self.before = self.disc.path.read_bytes()

    def catalog(self) -> module.SoundCatalog:
        return module.read_catalog(self.disc.path, banks=self.banks, audo_records=self.records)

    def clip(self, name: str, frames: int, channels: int, rate: int) -> Path:
        path = self.disc.path.parent / name
        sb.write_wav(path, bank_fixture.tone_pcm(frames, channels, rate, 700), channels, rate)
        return path


class SoundsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fx = SoundsFixture(self.dir)
        self.panel = SoundsPanel()
        self.panel.bank_pins = self.fx.banks
        self.panel.audo_records = self.fx.records

    def tearDown(self) -> None:
        # drain the worker before the widget goes: a runnable signalling into a deleted panel crashes Qt on Windows
        self.panel.wait_idle(20_000)
        self.app.processEvents()
        self.panel.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    # ------------------------------------------------------------------ catalog
    def test_catalog_lists_bank_slots_and_standalone_cues(self) -> None:
        catalog = self.fx.catalog()
        self.assertEqual(catalog.containers(), [BANK, STANDALONE])
        rows = catalog.rows(BANK)
        self.assertEqual([row.name for row in rows], ["tip_01", "cheer-front_01", "slot2"])
        tip = rows[0]
        self.assertEqual((tip.variants, tip.channels, tip.sample_rates), (3, 1, (8000,)))
        self.assertEqual([a.frame_count for a in tip.allocations], [256, 384, 256])
        self.assertAlmostEqual(tip.seconds_min, 256 / 8000)
        self.assertAlmostEqual(tip.seconds_max, 384 / 8000)
        self.assertEqual(rows[1].channels, 2)
        self.assertEqual(catalog.bank_facts[BANK]["subbank_count"], 3)
        cues = catalog.standalone
        self.assertEqual([row.name for row in cues], ["menu-back_01", "chantdef1"])
        self.assertEqual(cues[0].key, "outer_0003_chunk_0000")
        self.assertIn("global.iff", cues[0].package)
        self.assertEqual((cues[1].channels, cues[1].sample_rates, cues[1].allocations[0].frame_count),
                         (2, (22050,), 256))
        self.assertEqual(catalog.standalone_error, "")
        self.assertEqual(catalog.total, 5)

        self.panel.apply_catalog(self.fx.disc.path, catalog)
        self.assertTrue(self.panel.source_loaded)
        self.assertEqual([self.panel.container_combo.itemText(i) for i in range(self.panel.container_combo.count())],
                         [BANK, "Standalone cues"])
        self.assertEqual([row.key for row in self.panel.visible_rows()], ["tip_01", "cheer-front_01", "slot2"])
        first = self.panel.sound_list.item(0).text()
        self.assertIn("3 sub-banks", first)
        self.assertIn("mono 8000 Hz", first)
        self.assertIn("0.032..0.048 s", first)
        self.assertIn("2 standalone cues", self.panel.status_label.text())

    def test_search_filters_each_container(self) -> None:
        self.panel.apply_catalog(self.fx.disc.path, self.fx.catalog())
        self.panel.search.setText("cheer")
        self.assertEqual([row.key for row in self.panel.visible_rows()], ["cheer-front_01"])
        self.panel.search.setText("SLOT2")
        self.assertEqual([row.key for row in self.panel.visible_rows()], ["slot2"])
        self.panel.search.setText("nothing here")
        self.assertEqual(self.panel.visible_rows(), [])
        self.panel.container_combo.setCurrentIndex(self.panel.container_combo.findData(STANDALONE))
        self.assertEqual(self.panel.visible_rows(), [])            # the query still applies
        self.panel.search.setText("chant")
        self.assertEqual([row.key for row in self.panel.visible_rows()], ["outer_0003_chunk_0001"])
        self.panel.search.setText("global.iff")                    # package text is searchable too
        self.assertEqual(len(self.panel.visible_rows()), 2)
        self.panel.search.clear()
        self.assertEqual(len(self.panel.visible_rows()), 2)
        self.assertTrue(self.panel.search.property("studioSearch"))
        self.assertEqual(self.panel.search.accessibleName(), "Search sounds")

    # ------------------------------------------------------------------ fit preview
    def test_fit_summary_reports_pad_and_trim_per_subbank(self) -> None:
        catalog = self.fx.catalog()
        tip = catalog.row(BANK, "tip_01")
        assert tip is not None
        # 320 frames into 256 / 384 / 256: trimmed in sub-banks 0 and 2, padded in sub-bank 1.
        preview = module.preview_fit(tip, 1, 8000, 5 * 64)
        self.assertEqual([(pad, trim) for _a, pad, trim in preview.rows], [(0, 64), (64, 0), (0, 64)])
        text = module.fit_summary(tip, preview)
        self.assertIn("Clip 0.040 s (mono, 8000 Hz)", text)
        self.assertIn("holds 0.032..0.048 s", text)
        self.assertIn("pad 0.008 s of silence in 1 of 3 sub-banks", text)
        self.assertIn("trim 0.008 s (10 ms fade-out) in 2 of 3 sub-banks", text)
        self.assertNotIn("Converted", text)
        # 100 frames: padded everywhere, by 156 or 284 frames.
        short = module.fit_summary(tip, module.preview_fit(tip, 1, 8000, 100))
        self.assertIn("pad 0.019..0.035 s of silence in 3 of 3 sub-banks", short)
        self.assertNotIn("trim", short)
        # Exact fit in one sub-bank, trimmed in the others.
        exact = module.fit_summary(tip, module.preview_fit(tip, 1, 8000, 384))
        self.assertIn("exact fit in 1 of 3 sub-banks", exact)
        self.assertIn("trim 0.016 s", exact)
        # Standalone stereo 22050 record fed a mono 16 kHz clip: resampled + remixed, then trimmed.
        chant = catalog.row(STANDALONE, "outer_0003_chunk_0001")
        assert chant is not None
        preview = module.preview_fit(chant, 1, 16000, 200)         # -> 276 frames at 22050 vs 256
        self.assertEqual([(pad, trim) for _a, pad, trim in preview.rows], [(0, 20)])
        text = module.fit_summary(chant, preview)
        self.assertIn("trim 0.001 s (10 ms fade-out).", text)
        self.assertNotIn("of 1 record", text)
        self.assertIn("Converted: resampled 16000 → 22050 Hz, mono → stereo.", text)
        with self.assertRaises(SoundsError):
            module.preview_fit(tip, 1, 8000, 0)

        # The panel shows the same line once a sound and a WAV are chosen.
        self.panel.apply_catalog(self.fx.disc.path, catalog)
        self.assertTrue(self.panel.select_sound(BANK, "tip_01"))
        self.panel.set_replacement(self.fx.clip("clip.wav", 5 * 64, 1, 8000))
        self.assertEqual(self.panel.fit_label.text(), module.fit_summary(tip, module.preview_fit(tip, 1, 8000, 320)))
        self.assertEqual(self.panel.scope_combo.count(), 4)        # all + three sub-banks
        self.assertEqual(self.panel.scope(), (None, False))
        self.panel.scope_combo.setCurrentIndex(2)
        self.assertEqual(self.panel.scope(), ([1], False))
        self.panel.set_replacement(str(self.dir / "missing.wav"))
        self.assertIn("Choose a sound and a WAV", self.panel.fit_label.text())

    # ------------------------------------------------------------------ gating
    def test_write_needs_source_sound_clip_and_a_different_target(self) -> None:
        panel = self.panel
        self.assertFalse(panel.write_button.isEnabled())
        self.assertFalse(panel.export_button.isEnabled())
        self.assertFalse(panel.verify_button.isEnabled())
        panel.apply_catalog(self.fx.disc.path, self.fx.catalog())
        self.assertFalse(panel.write_button.isEnabled())            # nothing picked yet
        self.assertTrue(panel.select_sound(BANK, "cheer-front_01"))
        self.assertTrue(panel.export_button.isEnabled())
        self.assertFalse(panel.write_button.isEnabled())            # no clip
        panel.set_replacement(self.fx.clip("clip.wav", 64, 1, 8000))
        self.assertFalse(panel.write_button.isEnabled())            # no target
        panel.target_field.setText(str(self.fx.disc.path))          # same as source
        self.assertFalse(panel.write_button.isEnabled())
        self.assertFalse(panel.verify_button.isEnabled())
        copy = self.dir / "copy.xiso.iso"
        panel.target_field.setText(str(copy))
        self.assertTrue(panel.write_button.isEnabled())
        self.assertFalse(panel.verify_button.isEnabled())           # copy does not exist yet
        copy.write_bytes(b"x")
        panel._refresh()
        self.assertTrue(panel.verify_button.isEnabled())
        panel.apply_failure(Path("/nowhere/other.bin"), "not an NFL 2K5 XISO")
        self.assertFalse(panel.write_button.isEnabled())
        self.assertIn("Not an NFL 2K5 disc image", panel.status_label.text())

    def test_load_source_runs_in_the_background_and_caches(self) -> None:
        panel = self.panel
        panel.load_source(self.fx.disc.path)
        self.assertTrue(panel._pool.waitForDone(20_000))
        self.app.processEvents()
        self.assertTrue(panel.source_loaded)
        self.assertEqual(len(panel.visible_rows()), 3)
        panel.search.setText("tip")
        panel._catalog = None
        panel.load_source(self.fx.disc.path)                       # cached: synchronous
        self.assertTrue(panel.source_loaded)
        self.assertEqual([row.key for row in panel.visible_rows()], ["tip_01"])
        junk = self.dir / "junk.iso"
        junk.write_bytes(bytes(0x30000))
        panel.load_source(junk)
        self.assertTrue(panel._pool.waitForDone(20_000))
        self.app.processEvents()
        self.assertFalse(panel.source_loaded)
        self.assertIn("Not an NFL 2K5 disc image", panel.status_label.text())

    # ------------------------------------------------------------------ export / write / verify
    def test_export_decodes_one_subbank_or_every_variant(self) -> None:
        out = self.dir / "export"
        rows = module.perform_export(self.fx.disc.path, BANK, "tip_01", out, subbanks=[1], banks=self.fx.banks)
        self.assertEqual([row["file"] for row in rows], ["test_tip_01_sb01.wav"])
        rows = module.perform_export(self.fx.disc.path, BANK, "tip_01", out, banks=self.fx.banks)
        self.assertEqual(len(rows), 3)
        rows = module.perform_export(self.fx.disc.path, STANDALONE, "outer_0003_chunk_0000", out,
                                     audo_records=self.fx.records)
        self.assertEqual([row["file"] for row in rows], ["outer_0003_chunk_0000_menu-back_01.wav"])
        self.assertTrue(rows[0]["retail_payload"])
        self.assertEqual(self.fx.disc.path.read_bytes(), self.fx.before)

    def test_write_produces_a_copy_and_receipt_and_leaves_the_source_alone(self) -> None:
        clip = self.fx.clip("clip.wav", 5 * 64, 1, 8000)
        target = self.dir / "copy.xiso.iso"
        receipt = module.perform_write(self.fx.disc.path, target, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                                       banks=self.fx.banks, audo_records=self.fx.records)
        self.assertTrue(target.is_file())
        receipt_path = Path(receipt["receipt_path"])
        self.assertEqual(receipt_path, self.dir / "copy.sounds-receipt.json")
        self.assertEqual(module.receipt_path_for(Path("/x/ESPN NFL 2K5 (sounds).xiso.iso")),
                         Path("/x/ESPN NFL 2K5 (sounds).sounds-receipt.json"))
        saved = json.loads(receipt_path.read_text())
        self.assertEqual(saved["schema"], "nfl2k5_soundbank_swap_receipt/v1")
        self.assertEqual((saved["source"], saved["target"], saved["container"], saved["selection"]),
                         (str(self.fx.disc.path), str(target), BANK, "tip_01"))
        self.assertEqual(saved["payload_count"], 3)
        self.assertTrue(all(row["retail_gate"] == "retail-packs" for row in saved["payloads"]))
        pads = {row["subbank"]: (row["padded_silence_frames"], row["trimmed_frames"]) for row in saved["payloads"]}
        self.assertEqual(pads, {0: (0, 64), 1: (64, 0), 2: (0, 64)})
        # Source untouched, copy changed only where the tool wrote.
        self.assertEqual(self.fx.disc.path.read_bytes(), self.fx.before)
        after = target.read_bytes()
        self.assertEqual(len(after), len(self.fx.before))
        self.assertNotEqual(after, self.fx.before)
        with sb.SoundBanks(target, banks=self.fx.banks) as disc:
            bank = disc.bank(BANK)
            self.assertNotEqual(disc.read_payload(bank.payload(0, 1)), self.fx.bank_payloads[(0, 1)])
            self.assertEqual(disc.read_payload(bank.payload(1, 1)), self.fx.bank_payloads[(1, 1)])
        # Verify against the copy passes; against the untouched source it does not.
        result = module.perform_verify(target, BANK, "tip_01", clip, banks=self.fx.banks)
        self.assertTrue(result["all_match"])
        self.assertEqual(result["payload_count"], 3)
        self.assertFalse(module.perform_verify(self.fx.disc.path, BANK, "tip_01", clip, banks=self.fx.banks)["all_match"])

        # One sub-bank only, then a standalone cue gated by the catalog hashes (no packs needed).
        single = self.dir / "single.xiso.iso"
        receipt = module.perform_write(self.fx.disc.path, single, BANK, "cheer-front_01", clip, None,
                                       subbanks=[2], banks=self.fx.banks, audo_records=self.fx.records)
        self.assertEqual(receipt["payload_count"], 1)
        self.assertEqual(receipt["payloads"][0]["subbank"], 2)
        self.assertEqual(receipt["payloads"][0]["retail_gate"], "forced")     # no packs: unverified
        chant = self.dir / "chant.xiso.iso"
        stereo = self.fx.clip("chant.wav", 2 * 64 + 10, 2, 22050)
        receipt = module.perform_write(self.fx.disc.path, chant, STANDALONE, "outer_0003_chunk_0001", stereo,
                                       self.fx.disc.retail_packs, banks=self.fx.banks, audo_records=self.fx.records)
        self.assertEqual(receipt["schema"], "nfl2k5_audo_swap_receipt/v1")
        self.assertEqual(receipt["records"], ["outer_0003_chunk_0001"])
        self.assertEqual(receipt["payloads"][0]["retail_gate"], "catalog-hashes+retail-packs")
        self.assertEqual(receipt["payloads"][0]["padded_silence_frames"], 118)
        self.assertTrue((self.dir / "chant.sounds-receipt.json").is_file())
        self.assertTrue(module.perform_verify(chant, STANDALONE, "outer_0003_chunk_0001", stereo,
                                              audo_records=self.fx.records)["all_match"])
        self.assertEqual(self.fx.disc.path.read_bytes(), self.fx.before)

    def test_write_refuses_a_non_retail_span_before_touching_anything(self) -> None:
        clip = self.fx.clip("clip.wav", 64, 1, 8000)
        first = self.dir / "first.xiso.iso"
        module.perform_write(self.fx.disc.path, first, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                             banks=self.fx.banks, audo_records=self.fx.records)
        # Writing the same slot again from the already-modified copy is refused by the retail gate.
        second = self.dir / "second.xiso.iso"
        with self.assertRaises(sb.SoundbankSwapError) as raised:
            module.perform_write(first, second, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                                 banks=self.fx.banks, audo_records=self.fx.records)
        self.assertIn("no longer carries the retail bytes", str(raised.exception))
        self.assertEqual(second.read_bytes(), first.read_bytes())    # the copy was made, nothing written into it
        # A different slot of that copy is still retail, so it can be layered on.
        receipt = module.perform_write(first, second, BANK, "slot2", clip, self.fx.disc.retail_packs,
                                       banks=self.fx.banks, audo_records=self.fx.records)
        self.assertEqual(receipt["payload_count"], 3)

    def test_refuses_to_write_the_source_itself(self) -> None:
        clip = self.fx.clip("clip.wav", 64, 1, 8000)
        source = self.fx.disc.path
        with self.assertRaises(SoundsError):
            module.perform_write(source, source, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                                 banks=self.fx.banks, audo_records=self.fx.records)
        alias = self.dir / "alias.iso"
        os.link(source, alias)                                          # same inode, different name
        with self.assertRaises(SoundsError):
            module.perform_write(source, alias, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                                 banks=self.fx.banks, audo_records=self.fx.records)
        relative = Path(os.path.relpath(source, Path.cwd()))
        with self.assertRaises(SoundsError):
            module.perform_write(source, relative, BANK, "tip_01", clip, self.fx.disc.retail_packs,
                                 banks=self.fx.banks, audo_records=self.fx.records)
        self.assertEqual(source.read_bytes(), self.fx.before)
        self.assertFalse((self.dir / "fixture.sounds-receipt.json").exists())

    def test_studio_offers_the_tab(self) -> None:
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        try:
            panels = window.findChildren(SoundsPanel)
            self.assertEqual(len(panels), 1)
            self.assertIs(panels[0], window._sounds_panel)
        finally:
            for panel in window.findChildren(SoundsPanel):
                panel.wait_idle(20_000)
            self.app.processEvents()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
