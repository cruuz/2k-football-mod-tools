"""Retail-free boundaries for PCSX2-to-Xbox replacement-pack mapping."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402
from nfl_txtr import write_png  # noqa: E402


class Ps2ReplacementPackAuditTests(unittest.TestCase):
    def test_friendly_pngs_are_inventoried_but_not_fabricated_into_xbox_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PCSX2" / "textures" / audit.SERIAL / "replacements"
            source.mkdir(parents=True)
            payload = bytes((1, 2, 3, 255)) * (8 * 8)
            write_png(source / "Friendly Player.png", 8, 8, payload)
            report = audit.audit(root)
        self.assertFalse(report["xbox_mapping_ready"])
        self.assertEqual(report["summary"]["png_count"], 1)
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"], 0)
        self.assertIn("no canonical PCSX2", " ".join(report["blocking_reasons"]))
        self.assertIn("no source-owned", " ".join(report["blocking_reasons"]))

    def test_exact_duplicate_payloads_are_grouped_without_deleting_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = bytes((4, 5, 6, 255)) * (4 * 4)
            for name in ("one.png", "two.png"):
                write_png(root / name, 4, 4, payload)
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in root.iterdir()}
            report = audit.audit(root)
            after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in root.iterdir()}
        self.assertEqual(before, after)
        self.assertEqual(report["summary"]["unique_png_payload_count"], 1)
        self.assertEqual(len(report["duplicate_payload_groups"]), 1)
        self.assertEqual(len(report["duplicate_payload_groups"][0]["paths"]), 2)

    def test_canonical_hash_and_explicit_manifest_can_cross_the_identity_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "0123456789abcdef-fedcba9876543210-00006653.png"
            write_png(png, 4, 4, bytes((9, 8, 7, 255)) * (4 * 4))
            (root / audit.MAPPING_MANIFEST).write_text(json.dumps({
                "schema": audit.MAPPING_SCHEMA,
                "entries": [{
                    "pcsx2_png": png.name,
                    "xbox_asset_id": "nfl2k5.live-face.0001.f",
                }],
            }), encoding="utf-8")
            report = audit.audit(root)
        self.assertTrue(report["xbox_mapping_ready"])
        self.assertEqual(report["blocking_reasons"], [])
        self.assertEqual(report["summary"]["mapping_entry_count"], 1)

    def test_links_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.png"
            write_png(target, 4, 4, bytes(4 * 4 * 4))
            (root / "linked.png").symlink_to(target)
            with self.assertRaisesRegex(audit.PackAuditError, "must not contain links"):
                audit.audit(root)


@unittest.skipUnless(
    Path("/home/noah/Downloads/NFL2K27").is_dir(),
    "local NFL2K27 report source is absent",
)
class LocalPackWitnessTests(unittest.TestCase):
    def test_the_supplied_tree_is_an_incomplete_duplicate_only_skeleton(self) -> None:
        report = audit.audit(Path("/home/noah/Downloads/NFL2K27"))
        self.assertEqual(report["summary"]["file_count"], 12)
        self.assertEqual(report["summary"]["png_count"], 12)
        self.assertEqual(report["summary"]["unique_png_payload_count"], 4)
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"], 0)
        self.assertFalse(report["mapping_manifest"]["present"])
        self.assertFalse(report["xbox_mapping_ready"])


class Pcsx2ReplacementNameContractTests(unittest.TestCase):
    """The six shapes GSTextureReplacements.cpp actually emits.

    The 64-bit fields print with ``%llx``, which is not zero padded, so a
    hash whose leading nibble is zero is shorter than 16 digits.  Names below
    are taken from the shape census of a real 23,010-PNG pack, where the old
    fixed-width pattern rejected 27.36% of the files and this one rejects
    17.20% -- 2,337 recovered, no good name lost.
    """

    ACCEPTED = (
        # CLUT, both fields full width (the only shape formerly accepted).
        "805dd1bde4b7915d-9cfb7ef8d324634d-00005e53.png",
        # CLUT with an unpadded 15-digit first field.
        "9db432481565c6d-3e3835476e6adc19-00005dd3.png",
        # CLUT with an unpadded 15-digit second field.
        "e9adc4f5801adca6-145270a0b5c8371-00005dd3.png",
        # Plain, no CLUT.
        "805dd1bde4b7915d-00005e53.png",
        # Region (new form) and region + CLUT.
        "805dd1bde4b7915d-r128x64-00005e53.png",
        "805dd1bde4b7915d-9cfb7ef8d324634d-r128x64-00005e53.png",
        # Region (old form) and old region + CLUT.
        "805dd1bde4b7915d-r9cfb7ef8d324634d-00005e53.png",
        "805dd1bde4b7915d-9cfb7ef8d324634d-r145270a0b5c8371-00005e53.png",
        # Any of the above may carry a mip suffix.
        "805dd1bde4b7915d-9cfb7ef8d324634d-00005e53-mip0.png",
        "805dd1bde4b7915d-r128x64-00005e53-mip3.png",
    )

    REFUSED = (
        "Panthers.png",                     # author-named working file
        "old.png",
        "Camo Beige.png",
        "Bengal Stripes.png",
        # A canonical name buried behind a friendly prefix is still not one.
        "Bengals White Tiger - 3f0acbdc6c7ea27f-494961a55ab55cd9-00005e13.png",
        "805dd1bde4b7915d-9cfb7ef8d324634d-00005e53.png.png",   # double suffix
        "805dd1bde4b7915d-9cfb7ef8d324634d-00005e5.png",        # props not 8
        "805dd1bde4b7915d-9cfb7ef8d324634dd-00005e53.png",      # 17-digit hash
        "805dd1bde4b7915d-9CFB7EF8D324634D-00005e53.png",       # upper case
    )

    def test_every_emitted_shape_is_recognized(self) -> None:
        for name in self.ACCEPTED:
            with self.subTest(name=name):
                self.assertRegex(name, audit.PCSX2_HASH_NAME)

    def test_non_canonical_names_stay_refused(self) -> None:
        for name in self.REFUSED:
            with self.subTest(name=name):
                self.assertIsNone(audit.PCSX2_HASH_NAME.match(name))

    def test_the_audit_itself_counts_every_shape_as_canonical(self) -> None:
        """The constant is only useful if ``audit()`` agrees with it."""
        # Names that differ from an accepted one only by case cannot both
        # exist on a case-insensitive filesystem; the pattern-level test
        # above already covers that shape.
        folded = {name.casefold() for name in self.ACCEPTED}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, name in enumerate(self.ACCEPTED):
                write_png(root / name, 2, 2, bytes((index, 7, 9, 255)) * 4)
            for index, name in enumerate(self.REFUSED):
                if name.casefold() not in folded:
                    write_png(root / name, 2, 2, bytes((index, 3, 1, 255)) * 4)
            report = audit.audit(root)
        self.assertEqual(
            report["summary"]["canonical_pcsx2_hash_png_count"], len(self.ACCEPTED)
        )
        canonical = {row["path"] for row in report["pngs"] if row["pcsx2_hash_filename"]}
        self.assertEqual(canonical, set(self.ACCEPTED))


class EmptyMarkerFileTests(unittest.TestCase):
    """1,067 zero-byte ``.txt`` files in the real pack are content, not rot.

    Their filenames carry the donor-slot provenance, so an audit that dies on
    the first empty file cannot read the pack at all.
    """

    MARKERS = (
        "NFL 2k5 Original Player  Colts- Edgerrin James.txt",
        "NFL 2k5 Original Player  Packers- Na'il Diggs.txt",
        "UNK_1180_Bryan Cox.txt",
    )

    def test_zero_byte_markers_are_inventoried_instead_of_aborting_the_walk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            slot = root / "Real Players" / "Giants" / "OLB_Brian Burns"
            slot.mkdir(parents=True)
            for name in self.MARKERS:
                (slot / name).write_bytes(b"")
            write_png(root / "0123456789abcdef-fedcba9876543210-00006653.png",
                      4, 4, bytes((2, 4, 6, 255)) * (4 * 4))
            report = audit.audit(root)
        self.assertEqual(report["summary"]["empty_marker_count"], len(self.MARKERS))
        self.assertEqual(report["summary"]["file_count"], len(self.MARKERS) + 1)
        self.assertEqual(report["summary"]["png_count"], 1)
        self.assertEqual(report["suffix_counts"][".txt"], len(self.MARKERS))
        recorded = {Path(row).name for row in report["empty_markers"]}
        self.assertEqual(recorded, set(self.MARKERS))

    def test_an_empty_png_is_a_marker_and_never_reaches_the_header_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "0000000000000000-0000000000000000-00000000.png").write_bytes(b"")
            report = audit.audit(root)
        self.assertEqual(report["summary"]["empty_marker_count"], 1)
        self.assertEqual(report["summary"]["png_count"], 0)
        self.assertEqual(report["pngs"], [])

    def test_a_truncated_png_is_still_fatal(self) -> None:
        """Empty is a marker; malformed-but-present is still a broken pack."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "torn.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 4)
            with self.assertRaisesRegex(audit.PackAuditError, "PNG header is malformed"):
                audit.audit(root)

    def test_an_oversized_file_is_still_refused(self) -> None:
        original = audit.MAX_FILE_BYTES
        audit.MAX_FILE_BYTES = 8
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "fat.bin").write_bytes(b"far too many bytes")
                with self.assertRaisesRegex(audit.PackAuditError, "outside the safe bound"):
                    audit.audit(root)
        finally:
            audit.MAX_FILE_BYTES = original


class SymlinkPolicyTests(unittest.TestCase):
    """The root may be a link; nothing inside the tree may be.

    PenguinScreen2 installs its replacement directory as a symlink to the
    PCSX2 pack, so refusing a symlinked root refuses the normal install. A
    link found mid-walk is a different promise -- it can leave the tree the
    caller consented to -- and stays fatal.
    """

    def test_a_symlinked_root_is_resolved_and_both_paths_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            pack = base / "pcsx2-pack"
            pack.mkdir()
            write_png(pack / "0123456789abcdef-fedcba9876543210-00006653.png",
                      4, 4, bytes((5, 5, 5, 255)) * (4 * 4))
            link = base / "penguinscreen2-replacements"
            link.symlink_to(pack, target_is_directory=True)
            report = audit.audit(link)
        self.assertTrue(report["root"]["given_is_symlink"])
        self.assertTrue(report["root"]["resolved_differs"])
        self.assertEqual(Path(report["root"]["given"]).name, "penguinscreen2-replacements")
        self.assertEqual(Path(report["root"]["resolved"]).name, "pcsx2-pack")
        self.assertEqual(report["root_name"], "pcsx2-pack")
        self.assertEqual(report["summary"]["png_count"], 1)
        self.assertEqual(report["summary"]["canonical_pcsx2_hash_png_count"], 1)

    def test_a_plain_root_reports_itself_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            write_png(root / "plain.png", 2, 2, bytes(2 * 2 * 4))
            report = audit.audit(root)
        self.assertFalse(report["root"]["given_is_symlink"])
        self.assertFalse(report["root"]["resolved_differs"])
        self.assertEqual(report["root"]["given"], report["root"]["resolved"])

    def test_a_symlinked_directory_inside_the_tree_is_still_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            elsewhere = root / "elsewhere"
            elsewhere.mkdir()
            write_png(elsewhere / "hidden.png", 2, 2, bytes(2 * 2 * 4))
            inside = root / "pack"
            inside.mkdir()
            (inside / "shortcut").symlink_to(elsewhere, target_is_directory=True)
            with self.assertRaisesRegex(audit.PackAuditError, "must not contain links"):
                audit.audit(inside)

    def test_a_missing_root_fails_with_an_actionable_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            absent = Path(directory) / "not-here"
            with self.assertRaisesRegex(audit.PackAuditError, "cannot resolve"):
                audit.audit(absent)

    def test_a_file_supplied_as_the_root_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lone = Path(directory) / "lone.png"
            write_png(lone, 2, 2, bytes(2 * 2 * 4))
            with self.assertRaisesRegex(audit.PackAuditError, "must be a directory"):
                audit.audit(lone)


class JsonByteOrderMarkTests(unittest.TestCase):
    """PowerShell's ``ConvertTo-Json`` writes a BOM; ``json.loads`` chokes.

    The real pack's ``.mods/mods.json`` opens with ``EF BB BF``, which a
    plain ``utf-8`` read hands to the parser as U+FEFF.
    """

    MODS_DOCUMENT = {
        "categories": [
            {"id": "broadcast", "name": "Broadcast Packages",
             "exclusive": True, "options": []},
            {"id": "buttons", "name": "Controller", "exclusive": True,
             "options": [{"id": "dualsense_5_white", "name": "Dualsense 5 White"}]},
            {"id": "cyberfaces", "name": "Cyberfaces (2027)",
             "exclusive": False, "type": "cyberfaces", "options": []},
        ]
    }

    def _pack_with_mods(self, root: Path, text: str, encoding: str) -> None:
        write_png(root / "0123456789abcdef-fedcba9876543210-00006653.png",
                  4, 4, bytes((1, 1, 1, 255)) * (4 * 4))
        mods = root / ".mods"
        mods.mkdir()
        (mods / "mods.json").write_text(text, encoding=encoding)

    def test_a_bom_prefixed_mods_manifest_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._pack_with_mods(root, json.dumps(self.MODS_DOCUMENT), "utf-8-sig")
            raw = (root / ".mods" / "mods.json").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            report = audit.audit(root)
        self.assertTrue(report["mods_manifest"]["present"])
        self.assertTrue(report["mods_manifest"]["byte_order_mark"])
        self.assertEqual(report["mods_manifest"]["category_count"], 3)
        self.assertEqual(report["mods_manifest"]["option_count"], 1)

    def test_a_plain_mods_manifest_still_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._pack_with_mods(root, json.dumps(self.MODS_DOCUMENT), "utf-8")
            report = audit.audit(root)
        self.assertTrue(report["mods_manifest"]["present"])
        self.assertFalse(report["mods_manifest"]["byte_order_mark"])
        self.assertEqual(report["mods_manifest"]["category_count"], 3)

    def test_an_absent_mods_manifest_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_png(root / "plain.png", 2, 2, bytes(2 * 2 * 4))
            report = audit.audit(root)
        self.assertFalse(report["mods_manifest"]["present"])
        self.assertEqual(report["mods_manifest"]["category_count"], 0)

    def test_a_bom_prefixed_mapping_manifest_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "0123456789abcdef-fedcba9876543210-00006653.png"
            write_png(png, 4, 4, bytes((9, 8, 7, 255)) * (4 * 4))
            (root / audit.MAPPING_MANIFEST).write_text(json.dumps({
                "schema": audit.MAPPING_SCHEMA,
                "entries": [{
                    "pcsx2_png": png.name,
                    "xbox_asset_id": "nfl2k5.live-face.0001.f",
                }],
            }), encoding="utf-8-sig")
            report = audit.audit(root)
        self.assertTrue(report["xbox_mapping_ready"])
        self.assertEqual(report["summary"]["mapping_entry_count"], 1)

    def test_malformed_json_is_still_refused(self) -> None:
        """A BOM is an encoding fix, not a parsing amnesty."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._pack_with_mods(root, "\ufeff{not json at all", "utf-8")
            with self.assertRaisesRegex(audit.PackAuditError, "cannot read"):
                audit.audit(root)

    def test_the_emitted_report_is_bom_free(self) -> None:
        """We tolerate a BOM on the way in; we never write one out."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._pack_with_mods(root, json.dumps(self.MODS_DOCUMENT), "utf-8-sig")
            # main() finishes the audit before it writes, so the report can
            # land inside the tree it just described.
            out = root / "report.json"
            argv = sys.argv
            sys.argv = ["nfl2k5_ps2_replacement_pack_audit", str(root), "--json", str(out)]
            try:
                self.assertEqual(audit.main(), 0)
            finally:
                sys.argv = argv
            raw = out.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(json.loads(raw.decode("utf-8"))["mods_manifest"]["present"])


if __name__ == "__main__":
    unittest.main()
