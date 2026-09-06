"""The PS2 disc inventory: the self-test, its pins, its codec and its evidence.

Everything here runs without a disc. The one exception is gated on
``NFL2K5_PS2_ISO`` and skips cleanly when the variable is unset, exactly like
the ISO9660 conformance suite next door.
"""

from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import random
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _candidate in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import nfl2k5_ps2_disc_inventory as inv  # noqa: E402

_REGISTRY = _REPO_ROOT / "mod_editor" / "capabilities" / "registry.v1.json"
_EVIDENCE_JSON = _REPO_ROOT / "reports" / "gameplay_tuning" / "nfl2k5_ps2_disc_inventory.v1.json"
_EVIDENCE_JOIN = _REPO_ROOT / "reports" / "gameplay_tuning" / "nfl2k5_ps2_xbox_name_join.v1.csv"
_NFL2K5_PS2_ISO = (
    Path(os.environ["NFL2K5_PS2_ISO"]) if os.environ.get("NFL2K5_PS2_ISO") else None
)

# What the retail disc inventories to, and how it joins the Xbox disc by name.
# These are the numbers the PS2 plan is built on; the committed evidence must
# keep reproducing them or the plan's premise has moved.
_RETAIL_OUTER_ENTRIES = 4322
_RETAIL_ROWS = 550_746
_RETAIL_PS2_NAME_KEYS = 25_846
_RETAIL_XBOX_NAME_KEYS = 24_285
_RETAIL_SHARED_NAME_KEYS = 24_187


class SelfTestTests(unittest.TestCase):
    def test_the_selftest_passes(self) -> None:
        buffer = io.StringIO()
        real_stdout = sys.stdout
        sys.stdout = buffer
        try:
            code = inv.selftest()
        finally:
            sys.stdout = real_stdout
        self.assertEqual(code, 0)
        self.assertIn("NFL2K5_PS2_DISC_INVENTORY_SELFTEST_PASS", buffer.getvalue())


class PinTests(unittest.TestCase):
    """A shipped tool may import only its siblings, so it carries copies of the
    registry's identity pins. Copies drift; this keeps them equal."""

    def setUp(self) -> None:
        registry = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        (game,) = [entry for entry in registry["games"] if entry["id"] == "nfl2k5_ps2"]
        self.identity = game["retail_identity"]

    def test_the_boot_elf_pin_is_the_registry_pin(self) -> None:
        self.assertEqual(inv.RETAIL_BOOT_ELF_SHA256, self.identity["executable_sha256"])

    def test_the_image_pin_is_the_registry_pin(self) -> None:
        self.assertEqual(inv.RETAIL_IMAGE_SHA256, self.identity["content_sha256"])

    def test_the_serial_is_the_audit_serial(self) -> None:
        import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402

        self.assertEqual(inv.SERIAL, audit.SERIAL)
        self.assertEqual(inv.SERIAL, "SLUS-20919")

    def test_the_pins_agree_with_the_product_fingerprints(self) -> None:
        try:
            from mod_editor.core.model import GameId
            from mod_editor.core.sources import KNOWN_FINGERPRINTS
        except ImportError as exc:  # pragma: no cover - product package absent
            self.skipTest(f"product package not importable here: {exc}")
        by_kind = {fp.kind: fp.sha256 for fp in KNOWN_FINGERPRINTS if fp.game == GameId.NFL2K5_PS2}
        self.assertEqual(by_kind["ps2-iso"], inv.RETAIL_IMAGE_SHA256)
        self.assertEqual(by_kind["ps2-elf"], inv.RETAIL_BOOT_ELF_SHA256)


class LzPrefixCodecTests(unittest.TestCase):
    """The decoder stops the instant the metadata prefix exists; that prefix
    must be byte-identical to a full decode's, or names and descriptors read
    from LZ-compressed chunks would be wrong."""

    def _sample(self, seed: int) -> bytes:
        rng = random.Random(seed)
        pieces = []
        for _ in range(60):
            if rng.random() < 0.5 and pieces:
                pieces.append(rng.choice(pieces))
            else:
                pieces.append(bytes(rng.randrange(256) for _ in range(rng.randrange(1, 24))))
        return b"".join(pieces)

    def test_prefix_decode_equals_the_prefix_of_a_full_decode(self) -> None:
        for seed in range(6):
            data = self._sample(seed)
            stream = inv.compress(data)
            full = inv.decompress_prefix(stream, len(data))
            self.assertEqual(full, data, f"seed {seed}: round-trip")
            for want in (1, 7, 64, len(data) // 2, len(data) - 1):
                with self.subTest(seed=seed, want=want):
                    self.assertEqual(inv.decompress_prefix(stream, want), data[:want])

    def test_a_want_past_the_end_clamps_to_the_declared_size(self) -> None:
        data = b"clamp" * 50
        self.assertEqual(inv.decompress_prefix(inv.compress(data), 10_000), data)

    def test_the_decoder_refuses_a_bad_offset_width(self) -> None:
        stream = bytearray(inv.compress(b"x" * 40))
        stream[8] = 0
        with self.assertRaises(inv.InventoryError):
            inv.decompress_prefix(bytes(stream), 40)

    def test_the_decoder_refuses_a_truncated_stream(self) -> None:
        stream = inv.compress(bytes(range(200)))
        with self.assertRaises(inv.InventoryError):
            inv.decompress_prefix(stream[:20], 200)


class NameJoinTests(unittest.TestCase):
    def test_the_key_rule_is_strip_then_upper(self) -> None:
        self.assertEqual(inv.name_key("  legalpage "), "LEGALPAGE")
        self.assertEqual(inv.name_key(None), "")
        self.assertEqual(inv.name_key(""), "")

    def test_rows_without_a_name_never_join(self) -> None:
        side = inv.NameSide()
        side.add("", "TXTR", "PSMT8", 8, 8)
        self.assertEqual(side.keys, {})

    def test_presence_and_counts(self) -> None:
        ps2 = inv.NameSide()
        xbox = inv.NameSide()
        ps2.add("HELMET", "TXTR", "PSMT8", 256, 256)
        ps2.add("HELMET", "TXTR", "PSMT4", 64, 64)
        ps2.add("PS2_ONLY", "SCNE", "", "", "")
        xbox.add("HELMET", "TXTR", "P8", 256, 256)
        xbox.add("XBOX_ONLY", "TXTR", "DXT1", 32, 32)
        rows, summary = inv.name_join(ps2, xbox)
        self.assertEqual(
            summary,
            {
                "join_key": summary["join_key"],
                "ps2_name_keys": 2, "xbox_name_keys": 2, "shared": 1,
                "ps2_only": 1, "xbox_only": 1, "xbox_keys_matched_percent": 50.0,
            },
        )
        by_key = {row[0]: tuple(row) for row in rows}
        self.assertEqual(by_key["HELMET"][1], "both")
        self.assertEqual(by_key["HELMET"][2:6], ("2", "TXTR:2", "PSMT4:1|PSMT8:1", "256x256|64x64"))
        self.assertEqual(by_key["HELMET"][6:10], ("1", "TXTR:1", "P8:1", "256x256"))
        self.assertEqual(by_key["PS2_ONLY"][1], "ps2_only")
        self.assertEqual(by_key["PS2_ONLY"][6:10], ("", "", "", ""))
        self.assertEqual(by_key["XBOX_ONLY"][6:10], ("1", "TXTR:1", "DXT1:1", "32x32"))
        self.assertEqual([row[0] for row in rows], sorted(row[0] for row in rows))

    def test_an_inventory_file_loads_by_header_name(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as work:
            path = os.path.join(work, "xbox.csv")
            with open(path, "w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["name", "fourcc", "format", "width", "height"])
                writer.writerow(["helmet", "TXTR", "P8", "256", "256"])
                writer.writerow(["", "TXTR", "P8", "8", "8"])
            side, provenance = inv.load_name_side(path)
            self.assertEqual(set(side.keys), {"HELMET"})
            self.assertEqual(provenance["rows"], 2)
            self.assertEqual(provenance["name"], "xbox.csv")
            self.assertEqual(len(provenance["sha256"]), 64)


class CommittedEvidenceTests(unittest.TestCase):
    """The evidence the registry row cites, checked against the plan's numbers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(_EVIDENCE_JSON.read_text(encoding="utf-8"))

    def test_the_report_is_this_tool_over_the_retail_disc(self) -> None:
        self.assertEqual(self.report["schema"], inv.SCHEMA)
        identity = self.report["image"]["identity"]
        self.assertEqual(identity["serial"], inv.SERIAL)
        self.assertTrue(identity["retail_boot_elf"])
        self.assertTrue(identity["retail_image"])
        self.assertEqual(identity["boot_sha256"], inv.RETAIL_BOOT_ELF_SHA256)
        self.assertEqual(identity["image_sha256"], inv.RETAIL_IMAGE_SHA256)
        self.assertEqual(self.report["error_count"], 0)

    def test_the_report_carries_no_local_paths(self) -> None:
        name = self.report["image"]["name"]
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        self.assertNotIn("/", self.report["name_join"]["xbox_inventory"]["name"])

    def test_the_counts_are_the_plans_counts(self) -> None:
        self.assertEqual(self.report["outer"]["entry_count"], _RETAIL_OUTER_ENTRIES)
        self.assertEqual(self.report["outer"]["entries_scanned"], _RETAIL_OUTER_ENTRIES)
        self.assertEqual(self.report["resources"]["row_count"], _RETAIL_ROWS)
        self.assertEqual(self.report["resources"]["distinct_name_keys"], _RETAIL_PS2_NAME_KEYS)
        join = self.report["name_join"]
        self.assertEqual(join["ps2_name_keys"], _RETAIL_PS2_NAME_KEYS)
        self.assertEqual(join["xbox_name_keys"], _RETAIL_XBOX_NAME_KEYS)
        self.assertEqual(join["shared"], _RETAIL_SHARED_NAME_KEYS)
        self.assertEqual(join["xbox_keys_matched_percent"], 99.6)

    def test_the_join_csv_matches_the_report(self) -> None:
        with _EVIDENCE_JOIN.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream)
            header = next(reader)
            rows = list(reader)
        self.assertEqual(header, inv.JOIN_COLUMNS)
        join = self.report["name_join"]
        self.assertEqual(len(rows), join["rows_written"])
        self.assertEqual(len(rows), join["ps2_name_keys"] + join["xbox_only"])
        presence = {row[1] for row in rows}
        self.assertEqual(presence, {"both", "ps2_only", "xbox_only"})
        self.assertEqual(sum(1 for row in rows if row[1] == "both"), join["shared"])
        self.assertEqual([row[0] for row in rows], sorted(row[0] for row in rows))

    def test_the_evidence_is_retail_free_by_suffix_and_size(self) -> None:
        self.assertEqual(_EVIDENCE_JSON.suffix, ".json")
        self.assertEqual(_EVIDENCE_JOIN.suffix, ".csv")
        self.assertLess(_EVIDENCE_JOIN.stat().st_size, 8 * 1024 * 1024)
        self.assertLess(_EVIDENCE_JSON.stat().st_size, 8 * 1024 * 1024)


class CliRefusalTests(unittest.TestCase):
    def test_an_existing_output_is_never_overwritten(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as work:
            existing = os.path.join(work, "report.json")
            Path(existing).write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                inv.main(["--iso", os.path.join(work, "missing.iso"), "--json", existing])
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(Path(existing).read_text(encoding="utf-8"), "{}")

    def test_a_join_needs_an_xbox_side(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            inv.main(["--iso", "x.iso", "--join-csv", "join.csv"])
        self.assertEqual(caught.exception.code, 2)


@unittest.skipUnless(
    _NFL2K5_PS2_ISO is not None and _NFL2K5_PS2_ISO.is_file(),
    "set NFL2K5_PS2_ISO to a legally dumped SLUS-20919 image to run the disc-gated test",
)
class RetailDiscSmokeTests(unittest.TestCase):
    def test_the_first_entries_inventory_as_recorded(self) -> None:
        import tempfile

        stat = _NFL2K5_PS2_ISO.stat()
        with tempfile.TemporaryDirectory() as work:
            csv_path = os.path.join(work, "inventory.csv")
            report, _side = inv.inventory(str(_NFL2K5_PS2_ISO), csv_path=csv_path,
                                          jobs=1, limit=2)
            with open(csv_path, "r", encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(report["image"]["identity"]["serial"], "SLUS-20919")
        self.assertTrue(report["image"]["identity"]["retail_boot_elf"])
        self.assertEqual(report["outer"]["entry_count"], _RETAIL_OUTER_ENTRIES)
        self.assertEqual(rows[0]["name"], "legalpage")
        self.assertEqual((rows[0]["format"], rows[0]["width"], rows[0]["height"]),
                         ("PSMT8", "512", "512"))
        self.assertEqual(_NFL2K5_PS2_ISO.stat().st_mtime_ns, stat.st_mtime_ns,
                         "the disc image was written to")


if __name__ == "__main__":
    unittest.main()
