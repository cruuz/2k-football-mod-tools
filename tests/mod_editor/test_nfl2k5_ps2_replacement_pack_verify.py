"""A verifier that cannot fail is a rubber stamp, not a verifier.

Everything the exporter promises rests on this tool being able to say no. So
it is handed known-good output with exactly one thing wrong -- a flipped byte,
an extra file, a forged receipt row, a rewritten provenance block -- and
required to refuse every time. The control test in between proves the honest
pack still passes, so a verifier that simply always raised would fail too.

The exporter is used here only to *manufacture* fixtures, exactly as
``ps2_iso9660_verify``'s self-test uses the ISO writer. Every assertion runs
through the verifier's own independent decode, so the exporter is the subject
of these tests rather than a participant in them. The verifier module itself
must import nothing from the exporter, and
``IndependenceTests.test_the_verifier_does_not_import_the_exporter`` asserts
that directly -- a verifier sharing the writer's code could not see a bug in
it, because both sides would compute the same wrong answer and agree.

All fixtures are synthetic. No disc, no game data, no retail pixel.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_ROOT, _ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_ps2_replacement_pack_verify as verify  # noqa: E402
import nfl2k5_ps2_replacement_pack_audit as audit  # noqa: E402
from mod_editor.core import ps2_export_service as exporter  # noqa: E402


WIDE = "%08x" % (0x29 | (9 << 6) | (8 << 10) | (1 << 14))

ONE = "p8:5:one"
FANOUT = "tset:7:4:2:socks01"
UNEDITED = "p8:606:untouched"

NAME_ONE = "1111-2222-" + WIDE + ".png"
NAME_FAN_A = "3333-4444-" + WIDE + ".png"
NAME_FAN_B = "3333-4444-" + WIDE + "-mip1.png"
NAME_UNEDITED = "7777-8888-" + WIDE + ".png"

PROVENANCE = {
    "counts": {"entries": 4},
    "disc": {"serial": "SLUS-20919", "boot_sha256": "0" * 64},
    "emulator": {
        "name": "PenguinScreen2",
        "commit": "0123456789abcdef",
        "hash_convention": "classic-tcc-bit14",
    },
    "generated": "2026-01-01T00:00:00Z",
    "method": "hop1/v5",
}


def _json_bytes(document) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


class _PackTestCase(unittest.TestCase):
    """Every test gets a private temp dir holding one honest exported pack."""

    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix="ps2-verify-"))
        self.addCleanup(shutil.rmtree, self.work, True)

        document = dict(PROVENANCE)
        document["schema"] = verify.MAPPING_SCHEMA
        document["entries"] = [
            {"pcsx2_png": NAME_ONE, "xbox_asset_id": ONE},
            {"pcsx2_png": NAME_FAN_A, "xbox_asset_id": FANOUT},
            {"pcsx2_png": NAME_FAN_B, "xbox_asset_id": FANOUT},
            # Mapped but never edited: the target a leak would name.
            {"pcsx2_png": NAME_UNEDITED, "xbox_asset_id": UNEDITED},
        ]
        self.manifest = self.work / verify.MAPPING_MANIFEST
        self.manifest.write_bytes(_json_bytes(document))

        self.payload = verify.synthetic_png(512, 256)
        self.project_targets = [(ONE, self.payload), (FANOUT, self.payload)]
        self.project = self._archive(self.project_targets)
        self.pack = self.work / "pack"
        exporter.export_replacement_pack(
            exporter.project_from_targets(self.project_targets),
            self.pack,
            self.manifest,
        )

    def _archive(self, rows, name: str = "fixture.2k5mod") -> Path:
        path = self.work / name
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

    def replacement(self, name: str) -> Path:
        return self.pack.joinpath(*verify.REPLACEMENTS_PARTS, name)

    def receipt_document(self) -> dict:
        return json.loads(
            (self.pack / verify.RECEIPT_NAME).read_text(encoding="utf-8")
        )

    def rewrite_receipt(self, document) -> None:
        (self.pack / verify.RECEIPT_NAME).write_bytes(_json_bytes(document))


class HonestPackPassesTests(_PackTestCase):
    """The control. Without it, every refusal below proves nothing."""

    def test_the_honest_pack_passes(self) -> None:
        report = verify.verify(self.pack, self.manifest, self.project)
        self.assertEqual(report["result"], verify.RESULT_PASS)
        self.assertEqual(report["files_checked"], 3)
        self.assertEqual(report["edited_targets_checked"], 3)
        self.assertNotIn("downgraded", report)

    def test_the_manifest_may_come_from_inside_the_pack(self) -> None:
        """The exporter drops a copy beside the pack for the audit tool."""

        report = verify.verify(self.pack, None, self.project)
        self.assertEqual(report["result"], verify.RESULT_PASS)

    def test_every_check_is_recorded_as_run(self) -> None:
        report = verify.verify(self.pack, self.manifest, self.project)
        self.assertTrue(all(report["checks"].values()), report["checks"])

    def test_the_audit_tool_also_reports_the_pack_ready(self) -> None:
        """The second gate the validator script runs on the same folder."""

        report = audit.audit(self.pack)
        self.assertTrue(report["xbox_mapping_ready"], report["blocking_reasons"])


class MutatedContentTests(_PackTestCase):
    """Recorded digests must be of the bytes actually on disk."""

    def test_one_changed_output_byte_is_caught(self) -> None:
        victim = self.replacement(NAME_ONE)
        blob = bytearray(victim.read_bytes())
        blob[-8] ^= 0xFF
        victim.write_bytes(bytes(blob))
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn(NAME_ONE, str(caught.exception))

    def test_a_truncated_png_is_caught(self) -> None:
        victim = self.replacement(NAME_FAN_A)
        victim.write_bytes(victim.read_bytes()[:20])
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_a_file_that_is_not_a_png_at_all_is_caught(self) -> None:
        self.replacement(NAME_ONE).write_bytes(b"not a png" * 8)
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)


class ExtraAndMissingFileTests(_PackTestCase):
    """The folder and the receipt must describe each other exactly."""

    def test_an_extra_file_is_caught(self) -> None:
        stray = self.replacement("cccc-dddd-" + WIDE + ".png")
        stray.write_bytes(verify.synthetic_png(8, 8))
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("cccc-dddd", str(caught.exception))

    def test_an_extra_file_at_the_pack_root_is_caught(self) -> None:
        (self.pack / "readme.txt").write_bytes(b"hello")
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_a_missing_file_is_caught(self) -> None:
        self.replacement(NAME_FAN_B).unlink()
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn(NAME_FAN_B, str(caught.exception))

    def test_a_directory_outside_the_replacements_folder_is_caught(self) -> None:
        stray = self.pack / "textures" / verify.SERIAL / "dumps"
        stray.mkdir(parents=True)
        stray.joinpath(NAME_ONE).write_bytes(verify.synthetic_png(4, 4))
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("dumps", str(caught.exception))

    def test_a_symlink_inside_the_pack_is_caught(self) -> None:
        link = self.replacement("9999-aaaa-" + WIDE + ".png")
        try:
            link.symlink_to(self.replacement(NAME_ONE))
        except (OSError, NotImplementedError):  # pragma: no cover - Windows
            self.skipTest("this platform cannot create symlinks unprivileged")
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("links", str(caught.exception))


class ForgedReceiptTests(_PackTestCase):
    """The receipt is an input to be checked, never evidence."""

    def test_a_receipt_entry_for_an_unedited_target_is_caught(self) -> None:
        """The hard rule, asserted against a deliberate forgery.

        The file's bytes, name, digest and manifest row are all left correct;
        only the target it claims to come from is one the project never
        edited. That is exactly what a leak of retail pixels would look like,
        and it must be refused on the project evidence alone.
        """

        document = self.receipt_document()
        document["files"][0]["source_target"] = UNEDITED
        document["files"][0]["xbox_asset_id"] = UNEDITED
        # Keep the pack self-consistent so only the forgery can be the cause.
        document["files"][0]["pcsx2_png"] = NAME_UNEDITED
        document["files"][0]["path"] = (
            verify.REPLACEMENTS_POSIX + "/" + NAME_UNEDITED
        )
        self.replacement(NAME_ONE).rename(self.replacement(NAME_UNEDITED))
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        message = str(caught.exception)
        self.assertIn(UNEDITED, message)
        self.assertIn("does not mark edited", message)

    def test_a_filename_the_manifest_does_not_map_is_caught(self) -> None:
        document = self.receipt_document()
        document["files"][0]["xbox_asset_id"] = FANOUT
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("does not map", str(caught.exception))

    def test_an_asset_absent_from_the_manifest_is_caught(self) -> None:
        document = self.receipt_document()
        document["files"][0]["xbox_asset_id"] = "p8:999:invented"
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_an_uncanonical_filename_is_caught(self) -> None:
        document = self.receipt_document()
        self.replacement(NAME_ONE).rename(self.replacement("NotAHash.png"))
        document["files"][0]["pcsx2_png"] = "NotAHash.png"
        document["files"][0]["path"] = verify.REPLACEMENTS_POSIX + "/NotAHash.png"
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("canonical", str(caught.exception))

    def test_a_path_outside_the_replacements_folder_is_caught(self) -> None:
        document = self.receipt_document()
        document["files"][0]["path"] = "../escape/" + NAME_ONE
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_a_rewritten_provenance_block_is_caught(self) -> None:
        document = self.receipt_document()
        document["provenance"]["emulator"]["commit"] = "f" * 16
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("provenance", str(caught.exception))

    def test_a_missing_receipt_is_caught(self) -> None:
        (self.pack / verify.RECEIPT_NAME).unlink()
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_a_bundled_manifest_swapped_after_export_is_caught(self) -> None:
        """The pack ships its own map copy; it must be the one exported.

        Every other check would still pass: the files, names and digests are
        untouched, and the added row's provenance is unchanged. Only the
        digest the receipt recorded for the map itself catches this.
        """

        bundled = self.pack / verify.MAPPING_MANIFEST
        document = json.loads(bundled.read_text(encoding="utf-8"))
        document["entries"].append(
            {"pcsx2_png": "dead-beef-" + WIDE + ".png",
             "xbox_asset_id": "p8:1:smuggled"}
        )
        bundled.write_bytes(_json_bytes(document))
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("recorded a digest for", str(caught.exception))

    def test_the_exporter_bundles_the_manifest_verbatim(self) -> None:
        """The copy must hash to the digest the receipt records, byte for byte.

        Re-serializing the map on the way out would break that link and make
        the check above unenforceable.
        """

        bundled = (self.pack / verify.MAPPING_MANIFEST).read_bytes()
        self.assertEqual(bundled, self.manifest.read_bytes())
        recorded = self.receipt_document()["mapping_manifest"]["sha256"]
        self.assertEqual(hashlib.sha256(bundled).hexdigest(), recorded)


class DowngradedVerdictTests(_PackTestCase):
    """Without the project, the unedited-target check cannot run. Say so."""

    def test_dropping_the_project_downgrades_rather_than_passes(self) -> None:
        report = verify.verify(self.pack, self.manifest)
        self.assertEqual(report["result"], verify.RESULT_INCOMPLETE)
        self.assertNotEqual(report["result"], verify.RESULT_PASS)
        self.assertTrue(report["downgraded"])
        self.assertIn("--project", report["downgrade_reason"])
        self.assertFalse(report["checks"]["no_unedited_target"])

    def test_the_downgraded_run_still_performs_every_other_check(self) -> None:
        """A downgrade is not a bypass: the other four still have to pass."""

        self.replacement(NAME_ONE).write_bytes(verify.synthetic_png(8, 8))
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest)

    def test_a_leaking_pack_is_not_reported_as_passing_without_a_project(self) -> None:
        """The property that makes the downgrade honest rather than cosmetic."""

        document = self.receipt_document()
        document["files"][0]["source_target"] = UNEDITED
        document["files"][0]["xbox_asset_id"] = UNEDITED
        document["files"][0]["pcsx2_png"] = NAME_UNEDITED
        document["files"][0]["path"] = (
            verify.REPLACEMENTS_POSIX + "/" + NAME_UNEDITED
        )
        self.replacement(NAME_ONE).rename(self.replacement(NAME_UNEDITED))
        self.rewrite_receipt(document)
        report = verify.verify(self.pack, self.manifest)
        self.assertNotEqual(report["result"], verify.RESULT_PASS)


class EmulatorTargetTests(_PackTestCase):
    """A pack must say which emulator it is for, and say the right thing to it.

    The filenames are the same for all three, so nothing else in this file
    could catch a pack that tells a stock PCSX2 user to turn on Classic Texture
    Names -- a setting their build does not have -- or one that says nothing
    about the setting a PenguinScreen2 user does need.
    """

    def test_the_honest_pack_names_the_emulator_it_is_for(self) -> None:
        report = verify.verify(self.pack, self.manifest, self.project)
        self.assertEqual(report["emulator_target"],
                         verify.TARGET_PENGUINSCREEN2_CLASSIC)
        self.assertTrue(
            report["checks"]["instructions_match_the_emulator_target"])

    def test_every_target_the_exporter_offers_verifies(self) -> None:
        for target in exporter.EMULATOR_TARGETS:
            with self.subTest(target=target):
                pack = self.work / ("pack-" + target)
                exporter.export_replacement_pack(
                    exporter.project_from_targets(self.project_targets), pack,
                    self.manifest, emulator_target=target,
                )
                report = verify.verify(pack, self.manifest, self.project)
                self.assertEqual(report["result"], verify.RESULT_PASS)
                self.assertEqual(report["emulator_target"], target)

    def test_the_two_tools_agree_on_the_three_targets(self) -> None:
        """Restated in the verifier, never imported -- so they can disagree."""

        self.assertEqual(verify.EMULATOR_TARGETS, exporter.EMULATOR_TARGETS)
        for target in exporter.EMULATOR_TARGETS:
            self.assertEqual(
                set(verify.TARGET_REQUIRED_SETTINGS[target])
                - set(exporter.TARGET_SETTINGS[target]),
                set(),
                target,
            )

    def test_a_receipt_with_no_emulator_target_is_caught(self) -> None:
        document = self.receipt_document()
        del document["emulator_target"]
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("emulator_target", str(caught.exception))

    def test_a_receipt_naming_an_unknown_emulator_is_caught(self) -> None:
        document = self.receipt_document()
        document["emulator_target"] = "dolphin"
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError):
            verify.verify(self.pack, self.manifest, self.project)

    def test_a_receipt_with_no_instructions_is_caught(self) -> None:
        document = self.receipt_document()
        del document["instructions"]
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("instructions", str(caught.exception))

    def test_another_targets_instructions_are_caught(self) -> None:
        """PenguinScreen2's settings under a stock-PCSX2 label."""

        document = self.receipt_document()
        document["emulator_target"] = verify.TARGET_PCSX2_MODERN
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("ClassicTextureNames", str(caught.exception))

    def test_instructions_missing_the_setting_the_target_needs_are_caught(self) -> None:
        document = self.receipt_document()
        document["instructions"]["settings"] = ["ClassicTextureNames=true"]
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("LoadTextureReplacements=true", str(caught.exception))

    def test_instructions_that_explain_nothing_are_caught(self) -> None:
        """The steps must still carry the fact that makes them right."""

        document = self.receipt_document()
        document["instructions"]["lines"] = ["1. Copy the folder somewhere."]
        self.rewrite_receipt(document)
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(self.pack, self.manifest, self.project)
        self.assertIn("Classic Texture Names", str(caught.exception))

    def test_a_modern_pack_must_say_what_it_will_skip(self) -> None:
        pack = self.work / "modern"
        exporter.export_replacement_pack(
            exporter.project_from_targets(self.project_targets), pack,
            self.manifest, emulator_target=exporter.TARGET_PCSX2_MODERN,
        )
        path = pack / verify.RECEIPT_NAME
        document = json.loads(path.read_text(encoding="utf-8"))
        document["instructions"]["lines"] = [
            "1. Copy it.", "2. Turn on LoadTextureReplacements=true.",
        ]
        path.write_bytes(_json_bytes(document))
        with self.assertRaises(verify.PackVerifyError) as caught:
            verify.verify(pack, self.manifest, self.project)
        self.assertIn("1.7.4034", str(caught.exception))


class CliTests(_PackTestCase):
    """Exit non-zero on a violation; name the offending path."""

    def test_the_cli_returns_zero_on_an_honest_pack(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = verify.main([
                "--pack", str(self.pack), "--manifest", str(self.manifest),
                "--project", str(self.project),
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["result"], verify.RESULT_PASS)

    def test_the_cli_raises_on_a_violation(self) -> None:
        self.replacement(NAME_ONE).write_bytes(verify.synthetic_png(8, 8))
        with self.assertRaises(verify.PackVerifyError):
            verify.main([
                "--pack", str(self.pack), "--manifest", str(self.manifest),
                "--project", str(self.project),
            ])

    def test_the_cli_exits_nonzero_as_a_subprocess_on_a_violation(self) -> None:
        import subprocess

        self.replacement(NAME_ONE).write_bytes(verify.synthetic_png(8, 8))
        result = subprocess.run(
            [sys.executable,
             str(_ROOT / "tools" / "nfl2k5_ps2_replacement_pack_verify.py"),
             "--pack", str(self.pack), "--manifest", str(self.manifest),
             "--project", str(self.project)],
            capture_output=True, text=True, timeout=120,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(NAME_ONE, result.stderr)

    def test_the_cli_requires_a_pack(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            verify.main([])
        self.assertEqual(caught.exception.code, 2)

    def test_require_project_without_a_project_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            verify.main(["--pack", str(self.pack), "--require-project"])
        self.assertEqual(caught.exception.code, 2)

    def test_a_downgraded_run_says_so_on_stderr(self) -> None:
        stream = io.StringIO()
        real = sys.stderr
        sys.stderr = stream
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = verify.main(["--pack", str(self.pack), "--manifest",
                                    str(self.manifest)])
        finally:
            sys.stderr = real
        self.assertEqual(code, 0)
        self.assertIn("downgraded", stream.getvalue())


class SelfTestTests(unittest.TestCase):
    def test_the_selftest_passes(self) -> None:
        buffer = io.StringIO()
        real = sys.stdout
        sys.stdout = buffer
        try:
            code = verify.selftest()
        finally:
            sys.stdout = real
        self.assertEqual(code, 0)
        self.assertIn(
            "NFL2K5_PS2_REPLACEMENT_PACK_VERIFY_SELFTEST_PASS", buffer.getvalue()
        )


class IndependenceTests(unittest.TestCase):
    """The verifier re-derives; it does not borrow the writer's arithmetic."""

    def _source(self) -> str:
        return (
            _ROOT / "tools" / "nfl2k5_ps2_replacement_pack_verify.py"
        ).read_text(encoding="utf-8")

    def test_the_verifier_does_not_import_the_exporter(self) -> None:
        """The rule that makes this tool evidence rather than a second opinion.

        A verifier sharing the writer's code cannot see a bug in the writer:
        both sides would compute the same wrong name or digest and agree with
        each other.
        """

        tree = ast.parse(self._source())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotIn("ps2_export_service", module)
                self.assertFalse(module.startswith("mod_editor"), module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("ps2_export_service", alias.name)
                    self.assertFalse(alias.name.startswith("mod_editor"), alias.name)

    #: The one non-stdlib module the verifier may name, and only deferred: the
    #: audit tool its self-test gates on. Mirrors ``ps2_iso9660_verify``, whose
    #: self-test imports the ISO writer purely to manufacture fixtures.
    SIBLING = "nfl2k5_ps2_replacement_pack_audit"

    def _imports(self):
        """Every import in the file, as ``(module, at_module_scope)``."""

        tree = ast.parse(self._source())
        top = {id(node) for node in tree.body}
        found = []
        for node in ast.walk(tree):
            at_top = id(node) in top
            if isinstance(node, ast.ImportFrom):
                found.append(((node.module or "").split(".")[0], at_top))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    found.append((alias.name.split(".")[0], at_top))
        return found

    def test_module_scope_imports_only_the_standard_library(self) -> None:
        """It ships as a standalone tool, so importing it must need nothing else.

        This is the property ``test_shipped_tools_are_self_sufficient`` execs
        for real under ``python -I``; asserting it here names the offender.
        """

        allowed = {
            "argparse", "hashlib", "json", "os", "pathlib", "re", "stat",
            "struct", "sys", "zipfile", "zlib", "shutil", "tempfile",
            "__future__",
        }
        for module, at_top in self._imports():
            if at_top:
                self.assertIn(module, allowed, module)

    def test_the_only_sibling_import_is_the_audit_tool_and_it_is_deferred(self) -> None:
        """M1 requires the audit tool to agree, so the self-test gates on it.

        It stays inside ``selftest`` behind a ``sys.path`` guard: the installed
        Windows runtime is an embeddable CPython whose ``._pth`` does not add
        the script's own directory, so a module-scope sibling import would
        make the tool unimportable there.
        """

        stdlib = {
            "argparse", "hashlib", "json", "os", "pathlib", "re", "stat",
            "struct", "sys", "zipfile", "zlib", "shutil", "tempfile",
            "__future__",
        }
        outside = [module for module, _top in self._imports() if module not in stdlib]
        self.assertEqual(outside, [self.SIBLING])
        deferred = [
            module for module, at_top in self._imports()
            if module == self.SIBLING and not at_top
        ]
        self.assertEqual(deferred, [self.SIBLING])
        self.assertIn("sys.path.insert", self._source())

    def test_the_two_modules_agree_on_the_shared_contract(self) -> None:
        """Independent copies, kept equal by test rather than by import."""

        self.assertEqual(verify.MAPPING_SCHEMA, exporter.MAPPING_SCHEMA)
        self.assertEqual(verify.MAPPING_MANIFEST, exporter.MAPPING_MANIFEST)
        self.assertEqual(verify.RECEIPT_SCHEMA, exporter.RECEIPT_SCHEMA)
        self.assertEqual(verify.RECEIPT_NAME, exporter.RECEIPT_NAME)
        self.assertEqual(verify.SERIAL, exporter.SERIAL)
        self.assertEqual(verify.REPLACEMENTS_PARTS, exporter.REPLACEMENTS_DIR)
        self.assertEqual(verify.PROVENANCE_KEYS, exporter.PROVENANCE_KEYS)
        self.assertEqual(
            verify.PCSX2_HASH_NAME.pattern, exporter.PCSX2_HASH_NAME.pattern
        )


if __name__ == "__main__":
    unittest.main()
