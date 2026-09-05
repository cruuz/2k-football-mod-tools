"""The PS2 export service writes edited art only, and nothing else, ever.

Everything here is synthetic: hand-built PNGs, a hand-built manifest, a
hand-built project. No disc, no game data, no shipped manifest. That is
deliberate -- these tests must run in CI on a machine that has never seen the
game, and a test that needed retail bytes could not be committed.

The test that matters most is
``UneditedTargetsAreNeverWrittenTests.test_an_unedited_target_is_never_written``.
Emitting an unedited texture would be emitting retail pixels off the user's
disc under a PCSX2 filename, which is the one thing this lane must never do.
The rest of the suite exists to keep the surrounding machinery from growing a
path that could reach an unedited target sideways.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import ps2_export_service as svc  # noqa: E402
import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + tag
        + payload
        + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
    )


def png_bytes(width: int, height: int, value: int = 0x40) -> bytes:
    """A real, minimal, valid RGBA PNG built from scratch."""

    raw = b"".join(
        b"\x00" + bytes([value, value, value, 0xFF]) * width for _ in range(height)
    )
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def props(width_log2: int, height_log2: int, psm: int = 0x29) -> str:
    """The trailing ``%08x``: ``PSM | TW << 6 | TH << 10 | TCC << 14``."""

    return "%08x" % (psm | (width_log2 << 6) | (height_log2 << 10) | (1 << 14))


#: 512x256 and 256x256 property words, the two geometries this suite uses.
WIDE = props(9, 8)
SQUARE = props(8, 8)

ONE = "p8:5:one"
FANOUT = "tset:7:4:2:socks01"
SQUARE_ASSET = "p8:9:square"
UNMAPPED = "p8:404:nowhere"
UNEDITED = "p8:606:untouched"
LOGICAL = "nfl2k5.uniform.01h0.torso"

NAME_ONE = "1111-2222-" + WIDE + ".png"
NAME_FAN_A = "3333-4444-" + WIDE + ".png"
NAME_FAN_B = "3333-4444-" + WIDE + "-mip1.png"
NAME_SQUARE = "5555-6666-" + SQUARE + ".png"
NAME_UNEDITED = "7777-8888-" + WIDE + ".png"

PROVENANCE = {
    "counts": {"entries": 5},
    "disc": {
        "serial": "SLUS-20919",
        "boot_sha256": "0" * 64,
        "content_sha256": "1" * 64,
    },
    "emulator": {
        "name": "PenguinScreen2",
        "commit": "0123456789abcdef",
        "hash_convention": "classic-tcc-bit14",
    },
    "generated": "2026-01-01T00:00:00Z",
    "method": "hop1/v5",
}


def manifest_document() -> dict:
    """A 1:1 row, a 1:2 fan-out row, an aspect-mismatch row, an unedited row.

    ``UNMAPPED`` is deliberately absent: a target with no row at all is the
    third case the plan has to describe.
    """

    document = dict(PROVENANCE)
    document["schema"] = svc.MAPPING_SCHEMA
    document["entries"] = [
        {"pcsx2_png": NAME_ONE, "xbox_asset_id": ONE},
        {"pcsx2_png": NAME_FAN_A, "xbox_asset_id": FANOUT},
        {"pcsx2_png": NAME_FAN_B, "xbox_asset_id": FANOUT},
        {"pcsx2_png": NAME_SQUARE, "xbox_asset_id": SQUARE_ASSET},
        # Mapped, and never edited. If it ever appears in an export, the
        # service has reached past the project into the catalog.
        {"pcsx2_png": NAME_UNEDITED, "xbox_asset_id": UNEDITED},
    ]
    return document


class _ExportTestCase(unittest.TestCase):
    """Base class giving every test a private temp directory and a manifest."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2-export-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.manifest_path = self.work / svc.MAPPING_MANIFEST
        self.manifest_path.write_bytes(
            (json.dumps(manifest_document(), indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
        )
        self.wide = png_bytes(512, 256)
        self.square_source = png_bytes(512, 128)

    def project(self, extra=()):
        """Two edited targets that map, plus whatever a test adds.

        ``UNEDITED`` is never in here. That is the whole point: an
        ``ExportProject`` carries edited targets and nothing else, so there is
        no unedited target for an export to find.
        """

        rows = [(ONE, self.wide), (FANOUT, self.wide)]
        rows.extend(extra)
        return svc.project_from_targets(rows, source="fixture")

    def plan(self, extra=()):
        return svc.plan_export(self.project(extra), self.manifest_path)

    def export(self, extra=(), name: str = "pack"):
        return svc.run_export(self.plan(extra), self.work / name)

    def written_names(self, receipt):
        return sorted(row.pcsx2_png for row in receipt.files)


class UneditedTargetsAreNeverWrittenTests(_ExportTestCase):
    """The hard rule of the whole PS2 lane, asserted from three directions."""

    def test_an_unedited_target_is_never_written(self) -> None:
        """The control case for the rule.

        ``UNEDITED`` has a perfectly good manifest row -- the service knows the
        PCSX2 name it would take. The only reason it is not written is that the
        project does not list it, which is exactly the property being asserted.
        """

        receipt = self.export()
        self.assertNotIn(NAME_UNEDITED, self.written_names(receipt))
        for row in receipt.files:
            self.assertIn(row.source_target, {ONE, FANOUT})
            self.assertNotEqual(row.source_target, UNEDITED)

    def test_no_file_traces_to_a_target_outside_the_project(self) -> None:
        edited = self.project().edited_target_ids
        receipt = self.export()
        for row in receipt.files:
            self.assertIn(
                row.source_target,
                edited,
                "an exported file traced to a target the project does not list",
            )

    def test_the_written_folder_holds_only_receipt_named_files(self) -> None:
        """A file on disk that the receipt does not name would be unattributed."""

        receipt = self.export()
        named = {row.path for row in receipt.files}
        root = receipt.path
        found = set()
        for base, _dirs, names in os.walk(root):
            for name in names:
                relative = Path(base, name).relative_to(root).as_posix()
                if relative in (svc.RECEIPT_NAME, svc.MAPPING_MANIFEST):
                    continue
                found.add(relative)
        self.assertEqual(found, named)


class FanOutTests(_ExportTestCase):
    """One Xbox asset may own several PCSX2 identities; all of them are written."""

    def test_a_one_to_two_row_writes_two_files(self) -> None:
        receipt = self.export()
        fanned = [row for row in receipt.files if row.source_target == FANOUT]
        self.assertEqual(len(fanned), 2)
        self.assertEqual(
            sorted(row.pcsx2_png for row in fanned), sorted([NAME_FAN_A, NAME_FAN_B])
        )

    def test_the_receipt_lists_the_fan_out(self) -> None:
        receipt = self.export()
        entry = [row for row in self.plan().entries if row.target_id == FANOUT][0]
        self.assertEqual(entry.status, svc.STATUS_MAPPED)
        self.assertEqual(len(entry.pcsx2_pngs), 2)
        self.assertEqual(receipt.file_count, 3)

    def test_both_fan_out_files_carry_the_same_bytes(self) -> None:
        receipt = self.export()
        digests = {
            row.sha256 for row in receipt.files if row.source_target == FANOUT
        }
        self.assertEqual(len(digests), 1)


class UnmappedTargetTests(_ExportTestCase):
    """A target the manifest cannot name is skipped with a reason, never guessed."""

    def test_an_unmapped_target_is_skipped_with_a_reason(self) -> None:
        plan = self.plan([(UNMAPPED, self.wide)])
        entry = [row for row in plan.entries if row.target_id == UNMAPPED][0]
        self.assertEqual(entry.status, svc.STATUS_UNMAPPED)
        self.assertTrue(entry.reason)
        self.assertEqual(entry.pcsx2_pngs, ())

    def test_an_unmapped_target_writes_nothing(self) -> None:
        receipt = self.export([(UNMAPPED, self.wide)])
        self.assertNotIn(UNMAPPED, {row.source_target for row in receipt.files})
        self.assertIn(UNMAPPED, {row["target"] for row in receipt.skipped})

    def test_a_logical_uniform_id_is_skipped_and_says_why(self) -> None:
        """The one studio namespace that is not an Xbox asset id.

        ``nfl2k5.uniform.{selector}.{component}`` names a provider target that
        a writer composes into physical TSET/P8 packages at build time. It has
        no GS hash of its own, so it cannot be joined to a PCSX2 filename. The
        service must say that rather than invent a mapping.
        """

        plan = self.plan([(LOGICAL, self.wide)])
        entry = [row for row in plan.entries if row.target_id == LOGICAL][0]
        self.assertEqual(entry.status, svc.STATUS_UNMAPPED)
        self.assertIn("logical uniform provider target", entry.reason)

    def test_the_skipped_list_reaches_the_receipt(self) -> None:
        receipt = self.export([(UNMAPPED, self.wide), (LOGICAL, self.wide)])
        skipped = {row["target"]: row["reason"] for row in receipt.skipped}
        self.assertEqual(set(skipped), {UNMAPPED, LOGICAL})
        for reason in skipped.values():
            self.assertTrue(reason)


class AmbiguousTargetTests(_ExportTestCase):
    """A name more than one asset can claim is not uniquely attributable."""

    def test_a_contested_name_is_refused_rather_than_written(self) -> None:
        document = manifest_document()
        document["entries"].append(
            {"pcsx2_png": NAME_ONE, "xbox_asset_id": "p8:77:rival"}
        )
        contested = self.work / "contested.json"
        contested.write_bytes(
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        plan = svc.plan_export(self.project(), contested)
        entry = [row for row in plan.entries if row.target_id == ONE][0]
        self.assertEqual(entry.status, svc.STATUS_AMBIGUOUS)
        self.assertNotIn(NAME_ONE, {row.pcsx2_png for row in plan.files})


class GeometryTests(_ExportTestCase):
    """PCSX2 scales any size, so only the aspect has to be corrected."""

    def test_the_native_size_is_decoded_from_the_property_word(self) -> None:
        self.assertEqual(svc.native_size_from_name(NAME_ONE), (512, 256))
        self.assertEqual(svc.native_size_from_name(NAME_SQUARE), (256, 256))

    def test_a_matching_aspect_is_not_resampled(self) -> None:
        receipt = self.export()
        for row in receipt.files:
            self.assertIsNone(row.resampled_from)

    def test_a_differing_aspect_is_resampled_to_the_ps2_aspect(self) -> None:
        """512x128 art for a 256x256 native slot is 4:1 against 1:1."""

        if not svc.pillow_available():  # pragma: no cover - Pillow ships with the GUI
            self.skipTest("Pillow is not installed")
        receipt = self.export([(SQUARE_ASSET, self.square_source)])
        row = [item for item in receipt.files if item.source_target == SQUARE_ASSET][0]
        self.assertEqual(row.resampled_from, [512, 128])
        written = (receipt.path / row.path).read_bytes()
        self.assertEqual(svc.png_dimensions(written), (256, 256))

    def test_the_resample_is_recorded_in_the_receipt_document(self) -> None:
        if not svc.pillow_available():  # pragma: no cover
            self.skipTest("Pillow is not installed")
        receipt = self.export([(SQUARE_ASSET, self.square_source)])
        document = json.loads(
            (receipt.path / svc.RECEIPT_NAME).read_text(encoding="utf-8")
        )
        rows = {row["pcsx2_png"]: row for row in document["files"]}
        self.assertEqual(rows[NAME_SQUARE]["resampled_from"], [512, 128])
        self.assertIsNone(rows[NAME_ONE]["resampled_from"])
        self.assertEqual(document["counts"]["resampled"], 1)

    def test_a_resampled_fan_out_writes_byte_identical_files(self) -> None:
        """A mip chain resamples once and reuses the result for every level.

        If each level resized independently, a non-deterministic encoder could
        make the levels differ, and the pack would carry two "identical" files
        that are not.
        """

        if not svc.pillow_available():  # pragma: no cover
            self.skipTest("Pillow is not installed")
        document = manifest_document()
        chain = ["aaaa-bbbb-" + SQUARE + ".png"] + [
            "aaaa-bbbb-" + SQUARE + "-mip%d.png" % level for level in range(1, 7)
        ]
        document["entries"] = [
            {"pcsx2_png": name, "xbox_asset_id": SQUARE_ASSET} for name in chain
        ]
        path = self.work / "chain.json"
        path.write_bytes(
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        project = svc.project_from_targets([(SQUARE_ASSET, self.square_source)])
        receipt = svc.run_export(
            svc.plan_export(project, path), self.work / "chain-pack"
        )
        self.assertEqual(receipt.file_count, len(chain))
        digests = {row.sha256 for row in receipt.files}
        self.assertEqual(len(digests), 1)
        for row in receipt.files:
            self.assertEqual(row.resampled_from, [512, 128])

    def test_the_recorded_digest_is_of_the_resampled_bytes(self) -> None:
        """Not of the user's original, or the verifier would reject the file."""

        if not svc.pillow_available():  # pragma: no cover
            self.skipTest("Pillow is not installed")
        import hashlib

        receipt = self.export([(SQUARE_ASSET, self.square_source)])
        row = [item for item in receipt.files if item.source_target == SQUARE_ASSET][0]
        written = (receipt.path / row.path).read_bytes()
        self.assertEqual(hashlib.sha256(written).hexdigest(), row.sha256)
        self.assertNotEqual(row.sha256, hashlib.sha256(self.square_source).hexdigest())


class DestinationRefusalTests(_ExportTestCase):
    """An export publishes into a new name or it does not publish at all."""

    def test_an_existing_directory_is_refused(self) -> None:
        taken = self.work / "taken"
        taken.mkdir()
        with self.assertRaises(svc.Ps2ExportError):
            svc.run_export(self.plan(), taken)

    def test_an_existing_file_is_refused(self) -> None:
        taken = self.work / "taken-file"
        taken.write_bytes(b"occupied")
        with self.assertRaises(svc.Ps2ExportError):
            svc.run_export(self.plan(), taken)
        self.assertEqual(taken.read_bytes(), b"occupied")

    def test_a_symlink_destination_is_refused(self) -> None:
        """Even a link to nowhere: publishing *through* it is the hazard."""

        target = self.work / "elsewhere"
        target.mkdir()
        link = self.work / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            self.skipTest("this platform cannot create symlinks unprivileged")
        with self.assertRaises(svc.Ps2ExportError):
            svc.run_export(self.plan(), link)
        self.assertEqual(list(target.iterdir()), [])

    def test_a_dangling_symlink_destination_is_refused(self) -> None:
        link = self.work / "dangling"
        try:
            link.symlink_to(self.work / "does-not-exist")
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            self.skipTest("this platform cannot create symlinks unprivileged")
        with self.assertRaises(svc.Ps2ExportError):
            svc.run_export(self.plan(), link)

    def test_a_refused_export_leaves_no_staging_directory_behind(self) -> None:
        taken = self.work / "taken"
        taken.mkdir()
        before = sorted(path.name for path in self.work.iterdir())
        with self.assertRaises(svc.Ps2ExportError):
            svc.run_export(self.plan(), taken)
        self.assertEqual(sorted(path.name for path in self.work.iterdir()), before)


class ReceiptTests(_ExportTestCase):
    """The receipt is the pack's own account of itself, and must be exact."""

    def test_the_receipt_records_every_required_field(self) -> None:
        receipt = self.export()
        document = json.loads(
            (receipt.path / svc.RECEIPT_NAME).read_text(encoding="utf-8")
        )
        self.assertEqual(document["schema"], svc.RECEIPT_SCHEMA)
        for row in document["files"]:
            self.assertEqual(
                set(row),
                {"path", "pcsx2_png", "resampled_from", "sha256", "source_target",
                 "xbox_asset_id"},
            )

    def test_the_recorded_digests_are_the_bytes_on_disk(self) -> None:
        import hashlib

        receipt = self.export()
        for row in receipt.files:
            payload = (receipt.path / row.path).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), row.sha256)

    def test_the_provenance_block_is_copied_verbatim(self) -> None:
        receipt = self.export()
        document = json.loads(
            (receipt.path / svc.RECEIPT_NAME).read_text(encoding="utf-8")
        )
        expected = {key: PROVENANCE[key] for key in svc.PROVENANCE_KEYS}
        self.assertEqual(document["provenance"], expected)

    def test_files_land_under_the_pcsx2_serial_path(self) -> None:
        receipt = self.export()
        for row in receipt.files:
            self.assertTrue(row.path.startswith("textures/SLUS-20919/replacements/"))

    def test_the_pack_carries_the_manifest_for_the_audit_tool(self) -> None:
        """``xbox_mapping_ready`` is false without a manifest beside the pack."""

        receipt = self.export()
        report = audit.audit(receipt.path)
        self.assertTrue(report["xbox_mapping_ready"], report["blocking_reasons"])
        self.assertTrue(report["serial_directory_present"])
        self.assertEqual(
            report["summary"]["canonical_pcsx2_hash_png_count"], receipt.file_count
        )


class ProjectSourceTests(_ExportTestCase):
    """The project may arrive as a saved archive or as a live session."""

    def _archive(self, rows) -> Path:
        import hashlib

        path = self.work / "fixture.2k5mod"
        with zipfile.ZipFile(path, "w") as archive:
            edits = []
            for asset_id, payload in rows:
                member = "replacements/{key}.png".format(
                    key=hashlib.sha256(asset_id.encode("utf-8")).hexdigest()
                )
                archive.writestr(member, payload)
                edits.append({
                    "asset_id": asset_id,
                    "file": member,
                    "png_sha256": hashlib.sha256(payload).hexdigest(),
                    "rgba_sha256": "0" * 64,
                })
            archive.writestr("manifest.json", json.dumps({
                "schema": "2k5_mod_studio_project/v1",
                "game": "espn_nfl_2k5_xbox",
                "payload_policy": "user-replacements-only",
                "edits": edits,
            }, indent=2, sort_keys=True))
        return path

    def test_a_saved_project_archive_yields_its_edited_targets(self) -> None:
        path = self._archive([(ONE, self.wide), (FANOUT, self.wide)])
        project = svc.load_project(path)
        self.assertEqual(project.edited_target_ids, {ONE, FANOUT})

    def test_a_saved_project_exports_the_same_pack(self) -> None:
        path = self._archive([(ONE, self.wide), (FANOUT, self.wide)])
        receipt = svc.export_replacement_pack(
            path, self.work / "from-archive", self.manifest_path
        )
        self.assertEqual(receipt.file_count, 3)
        self.assertNotIn(NAME_UNEDITED, self.written_names(receipt))

    def test_a_tampered_archive_payload_is_refused(self) -> None:
        """The archive's own digest is checked, so a swapped member is caught."""

        import hashlib

        path = self.work / "tampered.2k5mod"
        with zipfile.ZipFile(path, "w") as archive:
            member = "replacements/{key}.png".format(
                key=hashlib.sha256(ONE.encode("utf-8")).hexdigest()
            )
            archive.writestr(member, self.wide)
            archive.writestr("manifest.json", json.dumps({
                "schema": "2k5_mod_studio_project/v1",
                "edits": [{
                    "asset_id": ONE, "file": member,
                    "png_sha256": "0" * 64, "rgba_sha256": "0" * 64,
                }],
            }))
        with self.assertRaises(svc.Ps2ExportError):
            svc.load_project(path)

    def test_a_live_session_adapter_reads_only_published_state(self) -> None:
        """The adapter must not reach into the session's private edit map."""

        class FakeSession:
            session_id = "fake"
            modified_asset_ids = frozenset({ONE, FANOUT, "nfl2k5.text.some.cue"})

            def __init__(self, payload):
                self._payload = payload

            def export_target_payload(self, asset_id):
                # Text and audio ids share modified_asset_ids and have no PNG.
                if asset_id.startswith("nfl2k5.text."):
                    return None
                return self._payload

        project = svc.load_project(FakeSession(self.wide))
        self.assertEqual(project.edited_target_ids, {ONE, FANOUT})


class ManifestContractTests(unittest.TestCase):
    """The service and the audit tool must agree on the shipped contract."""

    def test_the_schema_and_filename_match_the_audit_tool(self) -> None:
        self.assertEqual(svc.MAPPING_SCHEMA, audit.MAPPING_SCHEMA)
        self.assertEqual(svc.MAPPING_MANIFEST, audit.MAPPING_MANIFEST)
        self.assertEqual(svc.SERIAL, audit.SERIAL)

    def test_the_pcsx2_name_grammar_matches_the_audit_tool(self) -> None:
        """Two independent copies of the widened regex, kept equal by test."""

        for name in (
            "0abc-deadbeef-00006269.png",
            "1-2-00006269-mip3.png",
            "ffffffffffffffff-00006269.png",
            "abc-r64x64-00006269.png",
            "abc-def-r1f-00006269.PNG",
        ):
            self.assertIsNotNone(svc.PCSX2_HASH_NAME.fullmatch(name), name)
            self.assertIsNotNone(audit.PCSX2_HASH_NAME.fullmatch(name), name)
        for name in ("ABC-00006269.png", "notahash.png", "abc-0000626.png"):
            self.assertIsNone(svc.PCSX2_HASH_NAME.fullmatch(name), name)
            self.assertIsNone(audit.PCSX2_HASH_NAME.fullmatch(name), name)

    def test_a_manifest_with_the_wrong_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / svc.MAPPING_MANIFEST
            path.write_bytes(json.dumps({"schema": "wrong", "entries": []}).encode())
            with self.assertRaises(svc.Ps2ExportError):
                svc.load_manifest(path)

    def test_a_manifest_row_with_an_unknown_namespace_is_refused(self) -> None:
        document = manifest_document()
        document["entries"] = [{"pcsx2_png": NAME_ONE, "xbox_asset_id": "nope:1:x"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / svc.MAPPING_MANIFEST
            path.write_bytes(json.dumps(document).encode())
            with self.assertRaises(svc.Ps2ExportError):
                svc.load_manifest(path)


class ImportPurityTests(unittest.TestCase):
    """The service is Qt-free, and Pillow stays lazy."""

    def test_the_module_imports_no_qt(self) -> None:
        source = (
            _ROOT / "mod_editor" / "core" / "ps2_export_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("PyQt5", source)
        self.assertNotIn("QtWidgets", source)

    def test_pillow_is_imported_lazily(self) -> None:
        """Module scope must stay importable where Pillow is absent."""

        import ast

        source = (
            _ROOT / "mod_editor" / "core" / "ps2_export_service.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = getattr(node, "module", "") or ""
                self.assertNotIn("PIL", module)
                for name in names:
                    self.assertFalse(name.startswith("PIL"), name)


if __name__ == "__main__":
    unittest.main()
