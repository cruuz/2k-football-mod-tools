"""Synthetic archive contracts for clean-clone hydration; no network used."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging"))
SPEC = importlib.util.spec_from_file_location("hydrate_release_inputs", ROOT / "packaging/hydrate_release_inputs.py")
hydrator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hydrator)


class HydrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hydrate-test-")
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.root = self.folder / "repo"
        (self.root / "packaging").mkdir(parents=True)
        (self.root / hydrator.ALLOWLISTS[0]).write_text("# same parser as staging\nkeep.txt\nreports/assets/catalog.json\n")
        (self.root / hydrator.ALLOWLISTS[1]).write_text("keep.txt\ntools/vendor/helper\n")
        (self.root / "keep.txt").write_bytes(b"local edit")
        self.output = io.StringIO()
        self.addCleanup(patch.stopall)
        patch.object(hydrator, "ROOT", self.root).start()
        patch.object(hydrator.urllib.request, "urlopen", side_effect=AssertionError("network forbidden")).start()
        patch("sys.stdout", self.output).start()

    def archive(self, name="inputs.tar.gz", extra=(), omit=()):
        archive = self.folder / name
        rows = [("portable/keep.txt", b"upstream", tarfile.REGTYPE),
                ("portable/reports/assets/catalog.json", b"catalog", tarfile.REGTYPE),
                ("portable/tools/vendor/helper", b"helper", tarfile.REGTYPE),
                ("portable/unlisted/", b"", tarfile.DIRTYPE),
                ("portable/unlisted/secret", b"never copy", tarfile.REGTYPE)]
        with tarfile.open(archive, "w:gz") as bundle:
            for member_name, payload, kind in [*rows, *extra]:
                if member_name in omit:
                    continue
                member = tarfile.TarInfo(member_name)
                member.type = kind
                member.size = len(payload) if kind == tarfile.REGTYPE else 0
                member.mode = 0o777 if member_name.endswith("helper") else 0o666
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    member.linkname = "portable/keep.txt"
                bundle.addfile(member, io.BytesIO(payload) if kind == tarfile.REGTYPE else None)
        self.sidecar(archive)
        return archive

    def sidecar(self, archive):
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_name(archive.name + ".sha256").write_text(f"{checksum}  {archive.name}\n")

    def test_restores_only_missing_declared_files_and_is_idempotent(self):
        archive = self.archive()
        self.assertEqual(hydrator.hydrate(self.root, [archive]), 2)
        self.assertEqual((self.root / "keep.txt").read_bytes(), b"local edit")
        self.assertEqual((self.root / "reports/assets/catalog.json").read_bytes(), b"catalog")
        self.assertFalse((self.root / "unlisted").exists())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE((self.root / "tools/vendor/helper").stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE((self.root / "reports/assets/catalog.json").stat().st_mode), 0o644)
        self.assertEqual(hydrator.hydrate(self.root, [archive]), 0)
        self.assertIn("restored reports/assets/catalog.json", self.output.getvalue())
        self.assertTrue(self.output.getvalue().endswith("restored 0 files; 0 declared inputs absent\n"))

    def test_repeatable_offline_archives_never_read_tag_or_network(self):
        first = self.archive("one.tar.gz", omit=("portable/tools/vendor/helper",))
        second = self.archive("two.tar.gz", omit=("portable/reports/assets/catalog.json",))
        self.assertEqual(hydrator.main(["--archive", str(first), "--archive", str(second)]), 0)

    def test_verifies_all_checksums_before_any_copy(self):
        first = self.archive("first.tar.gz")
        second = self.archive("second.tar.gz")
        second.write_bytes(second.read_bytes() + b"tampered")
        with self.assertRaisesRegex(hydrator.HydrationError, "hash mismatch"):
            hydrator.hydrate(self.root, [first, second])
        self.assertFalse((self.root / "reports").exists())

    def test_validates_all_archives_before_any_copy(self):
        first = self.archive("first.tar.gz")
        second = self.archive("second.tar.gz", extra=(("portable/link", b"", tarfile.SYMTYPE),))
        with self.assertRaisesRegex(hydrator.HydrationError, "non-regular"):
            hydrator.hydrate(self.root, [first, second])
        self.assertFalse((self.root / "reports").exists())

    def test_failed_copy_removes_partial_file_for_retry(self):
        archive = self.archive()
        def interrupted(source, target, **kwargs):
            target.write(b"partial")
            raise OSError("disk failure")
        with patch.object(hydrator.shutil, "copyfileobj", side_effect=interrupted):
            with self.assertRaisesRegex(OSError, "disk failure"):
                hydrator.hydrate(self.root, [archive])
        self.assertFalse((self.root / "reports/assets/catalog.json").exists())
        self.assertEqual(hydrator.hydrate(self.root, [archive]), 2)

    def test_file_appearing_during_copy_is_never_overwritten(self):
        archive = self.archive()
        original = tarfile.TarFile.extractfile
        def concurrent_file(bundle, member):
            target = self.root / "reports/assets/catalog.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"concurrent edit")
            return original(bundle, member)
        with patch.object(tarfile.TarFile, "extractfile", concurrent_file):
            with self.assertRaises(FileExistsError):
                hydrator.hydrate(self.root, [archive])
        self.assertEqual((self.root / "reports/assets/catalog.json").read_bytes(), b"concurrent edit")

    def test_missing_sidecar_refuses(self):
        archive = self.archive()
        archive.with_name(archive.name + ".sha256").unlink()
        with self.assertRaises(FileNotFoundError):
            hydrator.hydrate(self.root, [archive])

    def test_malformed_or_wrong_filename_sidecar_refuses(self):
        archive = self.archive()
        sidecar = archive.with_name(archive.name + ".sha256")
        for content in ("bad", "0" * 64, "0" * 64 + "  other.tar.gz\n", "x" * 4097):
            with self.subTest(content=content[:70]):
                sidecar.write_text(content)
                with self.assertRaisesRegex(hydrator.HydrationError, "sidecar"):
                    hydrator.hydrate(self.root, [archive])

    def test_incomplete_inputs_return_nonzero_and_name_missing_path(self):
        archive = self.archive(omit=("portable/tools/vendor/helper",))
        with patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(hydrator.main(["--archive", str(archive)]), 1)
        self.assertIn("tools/vendor/helper", error.getvalue())
        self.assertFalse((self.root / "reports").exists())

    def test_unsafe_members_refuse_even_when_not_allowlisted(self):
        for name in ("/absolute/file", "portable/../outside", "portable/./file",
                     "portable//file", "portable/C:/file", "portable/back\\slash",
                     "portable/.git/config", "file", "portable/file/"):
            with self.subTest(name=name):
                archive = self.archive(extra=((name, b"bad", tarfile.REGTYPE),))
                with self.assertRaisesRegex(hydrator.HydrationError, "unsafe archive member"):
                    hydrator.hydrate(self.root, [archive])
                self.assertFalse((self.root / "reports").exists())

    def test_nonregular_members_refuse_even_when_not_allowlisted(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE):
            with self.subTest(kind=kind):
                archive = self.archive(extra=(("portable/unlisted/link", b"", kind),))
                with self.assertRaisesRegex(hydrator.HydrationError, "non-regular archive member"):
                    hydrator.hydrate(self.root, [archive])
                self.assertFalse((self.root / "reports").exists())

    def test_ambiguous_members_refuse(self):
        for name in ("portable/keep.txt", "other/keep.txt"):
            with self.subTest(name=name):
                archive = self.archive(extra=((name, b"ambiguous", tarfile.REGTYPE),))
                with self.assertRaisesRegex(hydrator.HydrationError, "ambiguous archive member"):
                    hydrator.hydrate(self.root, [archive])

    def test_existing_directory_is_not_a_restored_file(self):
        (self.root / "reports/assets/catalog.json").mkdir(parents=True)
        with self.assertRaisesRegex(hydrator.StageError, "not a regular file"):
            hydrator.hydrate(self.root, [self.archive()])

    @unittest.skipIf(os.name == "nt", "symlink creation needs Windows privileges")
    def test_destination_symlinks_and_dangling_symlinks_refuse(self):
        outside = self.folder / "outside"
        outside.mkdir()
        for path, target in ((self.root / "reports", outside),
                             (self.root / "reports", outside / "absent"),
                             (self.root / "keep.txt", outside / "absent")):
            with self.subTest(path=path, target=target):
                if path.exists():
                    path.unlink()
                path.symlink_to(target)
                try:
                    with self.assertRaises((hydrator.StageError, hydrator.HydrationError)):
                        hydrator.hydrate(self.root, [self.archive()])
                    self.assertEqual(list(outside.iterdir()), [])
                finally:
                    path.unlink()

    def test_allowlist_parser_is_shared_and_rejects_duplicates(self):
        import stage_release
        self.assertIs(hydrator._manifest_entries, stage_release._manifest_entries)
        (self.root / hydrator.ALLOWLISTS[0]).write_text("keep.txt\nkeep.txt\n")
        with self.assertRaisesRegex(hydrator.StageError, "duplicated"):
            hydrator.hydrate(self.root, [self.archive()])

    def test_unsafe_declared_paths_refuse(self):
        for relative in ("../outside", "C:/outside", ".git/config", "reports/file:stream"):
            with self.subTest(relative=relative):
                (self.root / hydrator.ALLOWLISTS[0]).write_text(relative + "\n")
                with self.assertRaises((hydrator.StageError, hydrator.HydrationError)):
                    hydrator.hydrate(self.root, [self.archive()])

    def test_default_tag_uses_checkout_without_importing_application(self):
        source = self.root / "mod_editor/core/update_check.py"
        source.parent.mkdir(parents=True)
        source.write_text('raise RuntimeError("must not import")\nBUILD_RELEASE_TAG = "beta-76.1"\n')
        with patch.object(hydrator, "download_release", return_value=[self.archive()]) as download:
            self.assertEqual(hydrator.main([]), 0)
        self.assertEqual(download.call_args.args[:2], (hydrator.DEFAULT_REPO, "beta-76.1"))

    def test_explicit_repo_and_tag(self):
        with patch.object(hydrator, "download_release", return_value=[self.archive()]) as download:
            self.assertEqual(hydrator.main(["--repo", "community/fork", "--tag", "beta-77"]), 0)
        self.assertEqual(download.call_args.args[:2], ("community/fork", "beta-77"))

    def test_download_selects_only_two_portables_and_sidecars_without_token(self):
        names = ["2K5-Mod-Studio-v1.0-RC105.tar.gz", "apf2k8-mod-studio-0.1.0-alpha.101.tar.gz"]
        assets = [{"name": name, "browser_download_url": "https://untrusted.invalid/"}
                  for name in [*names, *(name + ".sha256" for name in names), "unrelated.zip"]]
        document = json.dumps({"tag_name": "beta-76", "assets": assets}).encode()
        responses = [io.BytesIO(document), *(io.BytesIO(b"download") for _ in range(4))]
        with patch.object(hydrator.urllib.request, "urlopen", side_effect=responses) as request:
            paths = hydrator.download_release("community/fork", "beta-76", self.folder)
        self.assertEqual([p.name for p in paths], names)
        self.assertEqual(request.call_count, 5)
        for call in request.call_args_list:
            self.assertNotIn("Authorization", call.args[0].headers)
            self.assertIn("/community/fork/", call.args[0].full_url)

    def test_missing_or_ambiguous_remote_assets_refuse_before_download(self):
        first, second = "2K5-Mod-Studio-v1.tar.gz", "apf2k8-mod-studio-1.tar.gz"
        for names in ((first, second), (first, first, second, first + ".sha256", second + ".sha256")):
            document = json.dumps({"tag_name": "beta-76", "assets": [{"name": n} for n in names]}).encode()
            with patch.object(hydrator, "_request", return_value=io.BytesIO(document)) as request:
                with self.assertRaises(hydrator.HydrationError):
                    hydrator.download_release("community/fork", "beta-76", self.folder)
                self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
