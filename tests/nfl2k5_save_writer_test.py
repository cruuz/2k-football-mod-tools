"""The save/slider/franchise writer trio must stay fail-closed and copy-only.

Fixtures are synthetic: a minimal XBE carrying a certificate key (for the A4
title-static HMAC), a 736-byte settings save and a 720,044-byte franchise save
with known slider/year fields, and a small FATX volume built in memory.  No
game file or real HDD image is touched; retail-XBE signing is smoke-tested only
when the extracted copy exists.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_save_writer as saver  # noqa: E402

RETAIL_XBE = Path("/tmp/opencode/espn26/default.xbe")

SYNTH_CERT_KEY = bytes(range(16))
PARTITION_OFFSET = 0x80000  # partition X
BYTES_PER_CLUSTER = 0x1000
VOLUME_LENGTH = 0x100000


def _build_synth_xbe() -> bytes:
    buf = bytearray(0x800)
    buf[0:4] = saver.XBE_MAGIC
    base = 0x10000
    cert = base + 0x300
    struct.pack_into("<I", buf, 260, base)
    struct.pack_into("<I", buf, 280, cert)
    location = cert - base
    buf[location + 192 : location + 208] = SYNTH_CERT_KEY
    return bytes(buf)


def _settings_save(catching: float = 0.75) -> bytes:
    buf = bytearray(saver.SETTINGS_SAVE_SIZE)
    # Human Catching editable slot is the 9th of the Human block.
    offset = saver.EDITABLE_HUMAN_BASE + 4 * 8
    struct.pack_into("<f", buf, offset, catching)
    mirror = saver.MIRROR_HUMAN_BASE + 4 * 8
    struct.pack_into("<f", buf, mirror, 0.5)
    struct.pack_into("<f", buf, saver.SPECIAL_SLIDERS["Injury"], 1.0)
    return bytes(buf)


def _franchise_save(year_field: int = 7) -> bytes:
    buf = bytearray(saver.FRANCHISE_SAVE_SIZE)
    buf[0 : saver.SETTINGS_BLOCK_SIZE] = _settings_save()
    buf[saver.FRANCHISE_STATE_OFFSET : saver.FRANCHISE_STATE_OFFSET + 4] = (
        b"\x02\x01\x02\x20"
    )
    struct.pack_into("<H", buf, saver.FRANCHISE_SEASON_ORDINAL_OFFSET, 1)
    struct.pack_into("<H", buf, saver.FRANCHISE_YEAR_OFFSET, year_field)
    return bytes(buf)


def _dirent(name: str, attributes: int, first_cluster: int,
            file_size: int) -> bytes:
    return struct.pack(
        "<BB42sLLLLL", len(name), attributes, name.encode("ascii"),
        first_cluster, file_size, 0, 0, 0,
    )


def _build_fatx_image(savegame: bytes, extra: bytes) -> bytes:
    """One FATX volume at partition X holding <Title>/SAVEGAME.DAT + EXTRA."""

    total = PARTITION_OFFSET + VOLUME_LENGTH
    buf = bytearray(total)
    sectors_per_cluster = BYTES_PER_CLUSTER // saver.FATX_SECTOR_SIZE
    max_clusters = VOLUME_LENGTH // BYTES_PER_CLUSTER + 1
    struct.pack_into(
        "<LLLL", buf, PARTITION_OFFSET,
        saver.FATX_SIGNATURE, 0x12345678, sectors_per_cluster, 1,
    )
    fat_size = max_clusters * 2
    fat_size = (fat_size + saver.FATX_PAGE_SIZE - 1) & ~(
        saver.FATX_PAGE_SIZE - 1
    )
    fat_offset = PARTITION_OFFSET + saver.FATX_PAGE_SIZE
    file_area = PARTITION_OFFSET + saver.FATX_PAGE_SIZE + fat_size
    # FAT: clusters 1..4 are terminal chains.
    for cluster in (1, 2, 3, 4):
        struct.pack_into("<H", buf, fat_offset + cluster * 2, 0xFFFF)

    def cluster_base(cluster: int) -> int:
        return file_area + BYTES_PER_CLUSTER * (cluster - 1)

    # Root dir: one subdir "53450030" -> cluster 2.
    root = bytearray(BYTES_PER_CLUSTER)
    entry = _dirent("53450030", saver.FILE_ATTRIBUTE_DIRECTORY, 2, 0)
    root[0 : len(entry)] = entry
    root[len(entry)] = 0x00  # terminator
    buf[cluster_base(1) : cluster_base(1) + BYTES_PER_CLUSTER] = root
    # Container dir: SAVEGAME.DAT -> cluster 3, EXTRA -> cluster 4.
    container = bytearray(BYTES_PER_CLUSTER)
    a = _dirent(saver.SAVEGAME_NAME, 0, 3, len(savegame))
    b = _dirent(saver.EXTRA_NAME, 0, 4, len(extra))
    container[0 : len(a)] = a
    container[len(a) : len(a) + len(b)] = b
    container[len(a) + len(b)] = 0x00
    buf[cluster_base(2) : cluster_base(2) + BYTES_PER_CLUSTER] = container
    buf[cluster_base(3) : cluster_base(3) + len(savegame)] = savegame
    buf[cluster_base(4) : cluster_base(4) + len(extra)] = extra
    return bytes(buf)


class SliderAndYearTests(unittest.TestCase):
    def test_slider_offsets_cover_21_labels(self) -> None:
        self.assertEqual(len(saver.SLIDER_LABELS), 21)
        self.assertEqual(
            saver.slider_offsets("Injury"), {"editable": 0x284}
        )
        human = saver.slider_offsets("Human Catching")
        self.assertEqual(human["editable"], 0x174)
        self.assertEqual(human["mirror"], 0x2DC)

    def test_consistent_edit_touches_editable_and_mirror(self) -> None:
        payload = bytearray(_settings_save())
        changes = saver.apply_slider_edits(
            payload, {"Human Catching": 0.9}, mode="consistent"
        )
        self.assertEqual(len(changes), 2)
        regions = {change["region"] for change in changes}
        self.assertEqual(regions, {"editable", "mirror"})
        self.assertAlmostEqual(
            struct.unpack_from("<f", payload, 0x174)[0], 0.9, places=6
        )
        self.assertAlmostEqual(
            struct.unpack_from("<f", payload, 0x2DC)[0], 0.9, places=6
        )

    def test_out_of_range_slider_is_refused(self) -> None:
        payload = bytearray(_settings_save())
        with self.assertRaisesRegex(saver.SaveWriterError, "slider range"):
            saver.apply_slider_edits(payload, {"Injury": 1.5},
                                     mode="editable")

    def test_unknown_slider_is_refused(self) -> None:
        payload = bytearray(_settings_save())
        with self.assertRaisesRegex(saver.SaveWriterError, "unknown slider"):
            saver.apply_slider_edits(payload, {"Human Telekinesis": 0.5},
                                     mode="editable")

    def test_franchise_year_edit_and_readback(self) -> None:
        payload = bytearray(_franchise_save(year_field=7))
        change = saver.apply_franchise_year(payload, 2012)
        self.assertEqual(change["old_year_field"], 7)
        self.assertEqual(change["new_year_field"], 8)
        fields = saver.read_franchise_fields(bytes(payload))
        self.assertEqual(fields["display_year"], 2012)
        self.assertEqual(fields["season_ordinal"], 1)

    def test_same_year_is_refused(self) -> None:
        payload = bytearray(_franchise_save(year_field=7))
        with self.assertRaisesRegex(saver.SaveWriterError, "already equals"):
            saver.apply_franchise_year(payload, 2011)


class SigningAndLooseFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.xbe = self.work / "default.xbe"
        self.xbe.write_bytes(_build_synth_xbe())
        self.sig_key = saver.derive_sig_key(self.xbe.read_bytes())
        self.assertEqual(self.sig_key, hmac.new(
            saver.MASTER_XBOX_KEY, SYNTH_CERT_KEY, hashlib.sha1
        ).digest()[:16])

    def test_read_save_reports_kind_and_sliders(self) -> None:
        save = self.work / "SAVEGAME.DAT"
        save.write_bytes(_settings_save())
        result = saver.read_save(save)
        self.assertEqual(result["kind"], "settings")
        self.assertEqual(result["schema"], saver.READ_SCHEMA)
        self.assertAlmostEqual(
            result["sliders"]["Human Catching"]["editable"], 0.75, places=6
        )

    def test_edit_save_file_writes_dat_and_signed_extra(self) -> None:
        save = self.work / "SAVEGAME.DAT"
        original = _settings_save()
        save.write_bytes(original)
        target = self.work / "mut.DAT"
        extra = self.work / "EXTRA"
        result = saver.edit_save_file(
            save, target, extra, xbe_path=self.xbe,
            sliders={"Human Catching": 0.9}, slider_mode="consistent",
        )
        self.assertEqual(result["schema"], saver.EDIT_SCHEMA)
        mutated = target.read_bytes()
        self.assertEqual(len(mutated), len(original))
        self.assertTrue(saver.verify_extra(
            self.sig_key, mutated, extra.read_bytes()
        ))
        self.assertNotEqual(mutated, original)
        self.assertEqual(
            struct.unpack_from("<f", mutated, 0x174)[0],
            struct.unpack_from("<f", mutated, 0x2DC)[0],
        )

    def test_franchise_year_via_edit_save_file(self) -> None:
        save = self.work / "Franchise1.DAT"
        save.write_bytes(_franchise_save(year_field=7))
        target = self.work / "mut.DAT"
        extra = self.work / "EXTRA"
        result = saver.edit_save_file(
            save, target, extra, xbe_path=self.xbe, franchise_year=2012,
        )
        self.assertIsNotNone(result["franchise_year_change"])
        fields = saver.read_franchise_fields(target.read_bytes())
        self.assertEqual(fields["display_year"], 2012)

    def test_existing_target_is_refused(self) -> None:
        save = self.work / "SAVEGAME.DAT"
        save.write_bytes(_settings_save())
        blocker = self.work / "blocker.DAT"
        blocker.write_bytes(b"\x00")
        with self.assertRaisesRegex(saver.SaveWriterError, "already exists"):
            saver.edit_save_file(save, blocker, self.work / "EXTRA",
                                 xbe_path=self.xbe,
                                 sliders={"Injury": 0.5})

    def test_overwrite_replaces_existing_outputs(self) -> None:
        save = self.work / "SAVEGAME.DAT"
        save.write_bytes(_settings_save())
        target = self.work / "mut.DAT"
        extra = self.work / "EXTRA"
        target.write_bytes(b"\x00" * 8)
        extra.write_bytes(b"\x00" * 8)
        saver.edit_save_file(
            save, target, extra, xbe_path=self.xbe,
            sliders={"Injury": 0.5}, overwrite=True,
        )
        self.assertEqual(len(target.read_bytes()), saver.SETTINGS_SAVE_SIZE)
        self.assertEqual(len(extra.read_bytes()), 20)

    def test_no_edits_is_refused(self) -> None:
        save = self.work / "SAVEGAME.DAT"
        save.write_bytes(_settings_save())
        with self.assertRaisesRegex(saver.SaveWriterError,
                                    "no edits were requested"):
            saver.edit_save_file(save, self.work / "m.DAT",
                                 self.work / "EXTRA", xbe_path=self.xbe)


class FatXWriteBackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.xbe = self.work / "default.xbe"
        self.xbe.write_bytes(_build_synth_xbe())
        self.sig_key = saver.derive_sig_key(self.xbe.read_bytes())
        self.savegame = _settings_save()
        self.extra = saver.sign_save(self.sig_key, self.savegame)
        image = _build_fatx_image(self.savegame, self.extra)
        self.source = self.work / "src.raw"
        self.source.write_bytes(image)
        self.target = self.work / "dst.raw"
        self.target.write_bytes(image)

    def test_writeback_edits_save_and_resigns_extra(self) -> None:
        result = saver.write_back_to_hdd(
            self.source, self.target,
            container=("53450030",),
            xbe_path=self.xbe,
            sliders={"Human Catching": 0.9},
            slider_mode="consistent",
            partition="X",
        )
        self.assertEqual(result["schema"], saver.WRITEBACK_SCHEMA)
        self.assertTrue(result["post_write_readback_matches"])
        self.assertNotEqual(
            result["save_sha256_before"], result["save_sha256_after"]
        )
        self.assertNotEqual(
            self.source.read_bytes(), self.target.read_bytes()
        )

    def test_stale_extra_is_refused(self) -> None:
        image = bytearray(_build_fatx_image(self.savegame, b"\x00" * 20))
        stale = self.work / "stale.raw"
        stale.write_bytes(bytes(image))
        clean = self.work / "clean.raw"
        clean.write_bytes(_build_fatx_image(self.savegame, self.extra))
        with self.assertRaisesRegex(saver.SaveWriterError,
                                    "cannot honestly re-sign"):
            saver.write_back_to_hdd(
                stale, clean, container=("53450030",), xbe_path=self.xbe,
                sliders={"Injury": 0.5}, partition="X",
            )

    def test_same_file_is_refused(self) -> None:
        with self.assertRaisesRegex(saver.SaveWriterError, "same"):
            saver.write_back_to_hdd(
                self.source, self.source, container=("53450030",),
                xbe_path=self.xbe, sliders={"Injury": 0.5}, partition="X",
            )

    def test_missing_container_is_refused(self) -> None:
        with self.assertRaisesRegex(saver.SaveWriterError,
                                    "no SAVEGAME.DAT"):
            saver.write_back_to_hdd(
                self.source, self.target, container=("DEADBEEF",),
                xbe_path=self.xbe, sliders={"Injury": 0.5}, partition="X",
            )


@unittest.skipUnless(RETAIL_XBE.exists(), "retail extracted XBE not present")
class RetailSigningSmokeTests(unittest.TestCase):
    def test_retail_key_derives_20_byte_signatures(self) -> None:
        payload = RETAIL_XBE.read_bytes()
        key = saver.derive_sig_key(payload)
        self.assertEqual(len(key), 16)
        mac = saver.sign_save(key, b"retail smoke")
        self.assertEqual(len(mac), 20)


if __name__ == "__main__":
    unittest.main()
