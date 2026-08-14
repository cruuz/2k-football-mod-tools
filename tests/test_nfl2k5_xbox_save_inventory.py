from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl2k5_xbox_save_inventory as inventory  # noqa: E402


REPORT = ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json"
INVENTORY_TSV = ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_inventory.tsv"
SLIDER_TSV = ROOT / "reports/gameplay_tuning/nfl2k5_xbox_save_slider_snapshot.tsv"


class SaveInventoryUnitTests(unittest.TestCase):
    def test_decodes_bounded_container_metadata(self) -> None:
        self.assertEqual(
            inventory.decode_save_meta(
                b"\xff\xfe" + "Name=Fixture1\r\n".encode("utf-16le")
            ),
            "Fixture1",
        )
        self.assertEqual(inventory.decode_type("STG\0".encode("utf-16le")), "STG")
        with self.assertRaises(inventory.SaveInventoryError):
            inventory.decode_save_meta("Name=Fixture1\r\n".encode("utf-16le"))
        with self.assertRaises(inventory.SaveInventoryError):
            inventory.decode_type("TOOLONG\0".encode("utf-16le"))

    def test_extracts_synthetic_21_slot_join_without_retail_bytes(self) -> None:
        settings = bytearray(0x2E0)
        franchise = bytearray(720_044)
        for index, (label, offset, _group) in enumerate(inventory.SLIDER_LAYOUT):
            struct.pack_into("<f", settings, offset, 0.5)
            struct.pack_into("<f", franchise, offset, (index % 21) * 0.025)
        result = inventory.extract_slider_snapshot(bytes(settings), bytes(franchise))
        self.assertEqual(len(result["rows"]), 21)
        self.assertEqual(result["physical_storage_order"][:4], [
            "Injury", "Fumble", "Interception", "CPU Blocking"
        ])
        self.assertEqual(result["rows"][0]["offset"], "0x284")
        self.assertEqual(result["rows"][-1]["offset"], "0x2DC")
        # The last physical slot holds Human CATCHING, not Human Fatigue. The
        # save is a flat memcpy of the RAM struct, so a vector's slot order is
        # its globals' address order, and Catching's global (0x00E600F4) is the
        # highest in the human group even though the menu lists it fourth.
        # This assertion previously read `semantic_index == 8`, which is the
        # display index of Fatigue -- the test agreed with the mislabelling and
        # so could never catch it.
        self.assertEqual(result["rows"][-1]["label"], "Human Catching")
        self.assertEqual(result["rows"][-1]["semantic_index"],
                         inventory.LABELS.index("Human Catching"))

    def test_each_vector_is_stored_in_global_address_order(self) -> None:
        """Pin the ordering rule itself, derived, so it cannot regress.

        Twelve of the eighteen vector slots were once labelled as their
        neighbour because the layout enumerated LABELS in menu order. Deriving
        the expectation from EXPECTED_GLOBALS here means this test cannot repeat
        that mistake by hand-typing the same wrong order.
        """

        for group in ("cpu_vector", "human_vector"):
            with self.subTest(group=group):
                labels = [label for label, _offset, kind
                          in inventory.SLIDER_LAYOUT if kind == group]
                self.assertEqual(len(labels), 9)
                self.assertEqual(
                    labels,
                    sorted(labels, key=lambda l: inventory.EXPECTED_GLOBALS[l]),
                )
                self.assertEqual(labels[-1].split()[0] + " Catching", labels[-1])
        offsets = {label: offset for label, offset, _ in inventory.SLIDER_LAYOUT}
        self.assertEqual(offsets["Human Catching"], 0x2DC)
        self.assertEqual(offsets["CPU Catching"], 0x2B8)

    def test_rejects_non_grid_or_out_of_range_slider(self) -> None:
        payload = bytearray(0x2E0)
        struct.pack_into("<f", payload, 0x284, 0.513)
        with self.assertRaises(inventory.SaveInventoryError):
            inventory.normalized_slider(bytes(payload), 0x284, "Fixture")
        struct.pack_into("<f", payload, 0x284, 1.025)
        with self.assertRaises(inventory.SaveInventoryError):
            inventory.normalized_slider(bytes(payload), 0x284, "Fixture")

    def test_pinned_inputs_reject_symlink_hardlink_and_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            source.write_bytes(b"pinned-input")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            size = source.stat().st_size
            self.assertEqual(
                inventory.read_pinned_regular(source, size, digest, "fixture"),
                b"pinned-input",
            )

            link = root / "source-link.bin"
            link.symlink_to(source)
            with self.assertRaisesRegex(inventory.SaveInventoryError, "single-link"):
                inventory.read_pinned_regular(link, size, digest, "fixture")

            hardlink = root / "source-hardlink.bin"
            os.link(source, hardlink)
            with self.assertRaisesRegex(inventory.SaveInventoryError, "single-link"):
                inventory.read_pinned_regular(source, size, digest, "fixture")
            with self.assertRaisesRegex(inventory.SaveInventoryError, "single-link"):
                inventory.read_pinned_regular(hardlink, size, digest, "fixture")
            hardlink.unlink()

            tampered = root / "source-tampered.bin"
            tampered.write_bytes(b"pinned-inpuT")
            with self.assertRaisesRegex(inventory.SaveInventoryError, "SHA-256"):
                inventory.read_pinned_regular(tampered, size, digest, "fixture")

            raw = root / "raw.bin"
            raw.write_bytes(b"raw")
            raw_digest = hashlib.sha256(b"raw").hexdigest()
            raw_hardlink = root / "raw-hardlink.bin"
            os.link(raw, raw_hardlink)
            saved_image_size = inventory.IMAGE_SIZE
            inventory.IMAGE_SIZE = 3
            try:
                with self.assertRaisesRegex(inventory.SaveInventoryError, "single-link"):
                    inventory.open_image_read_only(raw, raw_digest)
                raw_hardlink.unlink()
                descriptor, _opened, observed = inventory.open_image_read_only(
                    raw, raw_digest
                )
                os.close(descriptor)
                self.assertEqual(observed, raw_digest)
                with self.assertRaisesRegex(inventory.SaveInventoryError, "SHA-256"):
                    inventory.open_image_read_only(raw, "0" * 64)
            finally:
                inventory.IMAGE_SIZE = saved_image_size

    def test_expected_image_hash_is_mandatory_and_canonical(self) -> None:
        digest = "a" * 64
        self.assertEqual(inventory.sha256_argument(digest), digest)
        for invalid in ("", "a" * 63, "A" * 64, "g" * 64):
            with self.subTest(invalid=invalid), self.assertRaises(
                inventory.argparse.ArgumentTypeError
            ):
                inventory.sha256_argument(invalid)

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/nfl2k5_xbox_save_inventory.py"),
                "--image",
                "/does/not/exist",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--expected-image-sha256", result.stderr)

    @staticmethod
    def _outputs(root: Path) -> tuple[tuple[Path, bytes, str], ...]:
        return (
            (root / "inventory.json", b"json\n", "JSON report"),
            (root / "inventory.tsv", b"inventory\n", "inventory TSV"),
            (root / "sliders.tsv", b"sliders\n", "slider TSV"),
        )

    def test_outputs_publish_exclusively_with_private_descriptor_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = self._outputs(root)
            inventory.write_outputs(outputs, set())
            for path, payload, _label in outputs:
                opened = path.stat()
                self.assertEqual(path.read_bytes(), payload)
                self.assertEqual(stat.S_IMODE(opened.st_mode), 0o600)
                self.assertEqual(opened.st_nlink, 1)

    def test_outputs_reject_existing_symlink_broken_link_and_parent_alias(self) -> None:
        for variant in ("existing", "symlink", "broken-symlink", "parent-symlink"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                outputs = list(self._outputs(root))
                protected_payload = None
                if variant == "existing":
                    outputs[1][0].write_bytes(b"user-data")
                    protected_payload = outputs[1][0]
                elif variant == "symlink":
                    target = root / "target"
                    target.write_bytes(b"target-data")
                    outputs[1][0].symlink_to(target)
                    protected_payload = target
                elif variant == "broken-symlink":
                    outputs[1][0].symlink_to(root / "missing-target")
                else:
                    real_parent = root / "real-parent"
                    real_parent.mkdir()
                    parent_alias = root / "parent-alias"
                    parent_alias.symlink_to(real_parent, target_is_directory=True)
                    outputs[0] = (
                        parent_alias / "inventory.json",
                        outputs[0][1],
                        outputs[0][2],
                    )

                with self.assertRaises(inventory.SaveInventoryError):
                    inventory.write_outputs(tuple(outputs), set())
                if protected_payload is not None:
                    expected = b"user-data" if variant == "existing" else b"target-data"
                    self.assertEqual(protected_payload.read_bytes(), expected)
                for path, _payload, _label in outputs:
                    if variant == "existing" and path == protected_payload:
                        continue
                    if variant in {"symlink", "broken-symlink"} and path.is_symlink():
                        continue
                    self.assertFalse(path.exists())

    def test_outputs_reject_duplicate_and_hardlink_input_alias_with_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            duplicate = root / "same.out"
            with self.assertRaisesRegex(inventory.SaveInventoryError, "distinct"):
                inventory.write_outputs(
                    (
                        (duplicate, b"one", "JSON report"),
                        (duplicate, b"two", "inventory TSV"),
                        (root / "third.out", b"three", "slider TSV"),
                    ),
                    set(),
                )
            self.assertFalse(duplicate.exists())

            protected = root / "raw.img"
            protected.write_bytes(b"protected")
            hardlink = root / "inventory.tsv"
            os.link(protected, hardlink)
            outputs = self._outputs(root)
            with self.assertRaisesRegex(inventory.SaveInventoryError, "absent"):
                inventory.write_outputs(outputs, {protected})
            self.assertEqual(protected.read_bytes(), b"protected")
            self.assertEqual(hardlink.read_bytes(), b"protected")
            self.assertFalse(outputs[0][0].exists())
            self.assertFalse(outputs[2][0].exists())

    def test_output_failure_cleanup_never_unlinks_foreign_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = self._outputs(root)
            moved_owned = root / "moved-owned-partial"
            original_writer = inventory._write_descriptor

            def replace_path_then_fail(descriptor: int, payload: bytes) -> None:
                original_writer(descriptor, payload)
                outputs[0][0].rename(moved_owned)
                outputs[0][0].write_bytes(b"foreign-replacement")
                raise inventory.SaveInventoryError("synthetic publication failure")

            with mock.patch.object(
                inventory, "_write_descriptor", side_effect=replace_path_then_fail
            ), self.assertRaisesRegex(
                inventory.SaveInventoryError, "synthetic publication failure"
            ):
                inventory.write_outputs(outputs, set())

            self.assertEqual(outputs[0][0].read_bytes(), b"foreign-replacement")
            self.assertEqual(moved_owned.read_bytes(), outputs[0][1])
            self.assertFalse(outputs[1][0].exists())
            self.assertFalse(outputs[2][0].exists())

    def test_qemu_descriptor_binding_executes_pinned_inode_and_detects_path_swap(self) -> None:
        validator = ROOT / "tools/validate_nfl2k5_xbox_save_inventory.sh"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pinned = root / "qemu-img"
            replacement = root / "replacement"
            shutil.copy2("/usr/bin/printf", pinned)
            shutil.copy2("/usr/bin/false", replacement)
            digest = hashlib.sha256(pinned.read_bytes()).hexdigest()
            script = r'''
source "$1"
QEMU_IMG="$2"
EXPECTED_QEMU_IMG_SIZE="$3"
EXPECTED_QEMU_IMG_SHA256="$4"
pin_qemu_img
mv "$QEMU_IMG" "$QEMU_IMG.original"
cp "$5" "$QEMU_IMG"
bound_output=$("$QEMU_IMG_EXEC" '%s' 'BOUND_INODE')
test "$bound_output" = BOUND_INODE
if verify_qemu_img_unchanged; then
  exit 91
fi
exec {QEMU_IMG_FD}<&-
'''
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    script,
                    "save-qemu-swap-test",
                    str(validator),
                    str(pinned),
                    str(pinned.stat().st_size),
                    digest,
                    str(replacement),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_qemu_descriptor_pin_rejects_symlink_hardlink_and_tamper(self) -> None:
        validator = ROOT / "tools/validate_nfl2k5_xbox_save_inventory.sh"
        helper = r'''
source "$1"
QEMU_IMG="$2"
EXPECTED_QEMU_IMG_SIZE="$3"
EXPECTED_QEMU_IMG_SHA256="$4"
pin_qemu_img
exec {QEMU_IMG_FD}<&-
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            shutil.copy2("/usr/bin/printf", original)
            size = original.stat().st_size
            digest = hashlib.sha256(original.read_bytes()).hexdigest()

            def run(path: Path, expected_hash: str = digest) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        "bash", "-c", helper, "save-qemu-pin-test",
                        str(validator), str(path), str(size), expected_hash,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )

            self.assertEqual(run(original).returncode, 0)
            symlink = root / "symlink"
            symlink.symlink_to(original)
            self.assertNotEqual(run(symlink).returncode, 0)
            hardlink = root / "hardlink"
            os.link(original, hardlink)
            self.assertNotEqual(run(original).returncode, 0)
            hardlink.unlink()
            self.assertNotEqual(run(original, "0" * 64).returncode, 0)


class SaveInventoryCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))

    def test_canonical_scope_and_counts(self) -> None:
        raw = REPORT.read_bytes()
        self.assertEqual(len(raw), 31_477)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "e49d30bc9adb87faf1a592a9d3a529169659be8f926be9db9028c90009477e3c",
        )
        self.assertEqual(raw, inventory.canonical_json(self.report))
        self.assertEqual(self.report["schema"], inventory.SCHEMA)
        self.assertEqual(
            self.report["inputs"]["raw_hdd"]["path"],
            "xemu-hdd-readonly.raw",
        )
        self.assertEqual(self.report["summary"]["save_container_count"], 8)
        self.assertEqual(self.report["summary"]["slider_field_count"], 21)
        self.assertEqual(self.report["summary"]["save_type_counts"], {
            "USR": 1, "STG": 1, "FXG": 1, "TMM": 5
        })
        self.assertTrue(self.report["scope"]["read_only"])
        self.assertFalse(self.report["scope"]["save_writer_exposed"])
        self.assertFalse(self.report["scope"]["signature_writer_exposed"])
        self.assertFalse(self.report["summary"]["safe_writer_proved"])

    def test_primary_save_hashes_and_prefix_join(self) -> None:
        rows = {row["display_name"]: row for row in self.report["containers"]}
        self.assertEqual(rows["Settings1"]["type"], "STG")
        self.assertEqual(rows["Settings1"]["files"]["SAVEGAME.DAT"]["file_size"], 736)
        self.assertEqual(rows["Franchise1"]["type"], "FXG")
        self.assertEqual(
            rows["Franchise1"]["files"]["SAVEGAME.DAT"]["file_size"], 720_044
        )
        snapshot = self.report["slider_snapshot"]
        self.assertEqual(snapshot["aligned_prefix_comparison"], {
            "differing_byte_count": 120,
            "equal_byte_count": 616,
            "equal_u32_slot_count": 137,
            "u32_slot_count": 184,
        })
        self.assertTrue(all(row["settings1"] == 0.5 for row in snapshot["rows"]))

    def test_signature_owner_is_bounded_and_not_a_writer(self) -> None:
        evidence = self.report["executable_evidence"]
        self.assertEqual(
            evidence["filename_dispatch"]["selector"],
            {"0": "EXTRA", "1": "TYPE", "other": "SAVEGAME.DAT"},
        )
        signature = evidence["signature_owner"]
        self.assertEqual(signature["begin"]["XCalculateSignatureBegin_mode"], 0)
        self.assertEqual(signature["stream_update_and_read_validation"]["reads_EXTRA_size"], 20)
        self.assertEqual(signature["write_close"]["writes_EXTRA_size"], 20)
        self.assertFalse(signature["current_EXTRA_cryptographically_recomputed"])

    def test_tsvs_have_only_metadata_and_decoded_values(self) -> None:
        inventory_rows = list(csv.DictReader(
            io.StringIO(INVENTORY_TSV.read_text(encoding="utf-8")), delimiter="\t"
        ))
        slider_rows = list(csv.DictReader(
            io.StringIO(SLIDER_TSV.read_text(encoding="utf-8")), delimiter="\t"
        ))
        self.assertEqual(len(inventory_rows), 8)
        self.assertEqual(len(slider_rows), 21)
        self.assertEqual(set(inventory_rows[0]), {
            "directory_id", "display_name", "type", "savegame_size",
            "savegame_sha256", "extra_size", "extra_sha256", "first_cluster"
        })
        self.assertEqual(slider_rows[0]["label"], "Injury")
        # Human CATCHING, not Fatigue: the vectors are stored in the globals'
        # address order, where Catching is last. The old menu-order layout put
        # Fatigue here and shifted 12 of the 18 vector labels by one.
        self.assertEqual(slider_rows[-1]["label"], "Human Catching")

    def test_analyzer_has_no_mutating_or_payload_export_option(self) -> None:
        source = (ROOT / "tools/nfl2k5_xbox_save_inventory.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "--apply", "--extract", "--write-save", "O_RDWR", "r+b"
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("os.O_RDONLY", source)
        self.assertIn("retail_or_save_bytes_emitted", source)

    def test_validator_rebuilds_private_raw_from_exact_pinned_qcow(self) -> None:
        source = (ROOT / "tools/validate_nfl2k5_xbox_save_inventory.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("NFL2K5_XBOX_RAW_HDD", source)
        self.assertIn(
            "EXPECTED_QCOW_SHA256="
            "ccd94e4f52b18ae7e171d95223e994a0028b13f22a2417d2bfb1175480e947b3",
            source,
        )
        self.assertIn(
            "EXPECTED_IMAGE_SHA256="
            "a495f735a6ca39ca7f476757d832fab5f535270cc675552c8c1ae9e32263fa13",
            source,
        )
        self.assertIn(
            "EXPECTED_QEMU_IMG_SHA256="
            "fd095f52d483230c957fe48eea7ac19ef0bc85feb5db347be6a5a4c811d854c1",
            source,
        )
        self.assertIn('convert -f qcow2 -O raw -S 4096', source)
        self.assertIn('"/proc/self/fd/$QCOW_FD" "$RAW_NAME"', source)
        self.assertIn('QEMU_IMG_EXEC="/proc/self/fd/$QEMU_IMG_FD"', source)
        self.assertNotIn('"$QEMU_IMG" info', source)
        self.assertNotIn('"$QEMU_IMG" convert', source)
        self.assertIn('chmod 0400 "$RAW_NAME"', source)
        self.assertIn('mktemp -d /tmp/nfl2k5-save-inventory.XXXXXX', source)
        self.assertIn("QCOW_WAS_EXPLICIT=1", source)
        self.assertIn("mode=committed-evidence-only", source)
        self.assertIn("mode=private-reproduction", source)
        self.assertIn("canonical_private_fixture=unavailable", source)
        self.assertIn("committed_evidence=true", source)
        self.assertLess(source.index("fixture_reason=''"), source.index("pin_qemu_img\n"))


if __name__ == "__main__":
    unittest.main()
