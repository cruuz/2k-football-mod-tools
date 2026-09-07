"""Generic XBE recipe, exact receipts and refusal before output mutation."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_my_career_fixture import XBE


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe required")
class GenericBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE exceeds 16 MiB")
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE pin differs")

    def run_cli(self, *args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            result = mode.main([str(a) for a in args])
        return result, json.loads(out.getvalue())

    def test_full_union_generic_recipe_and_byte_identical_replay(self):
        with tempfile.TemporaryDirectory(prefix="mycareer-generic-") as folder:
            d = Path(folder).resolve()
            output, receipt_path = d / "default.xbe", d / "receipt.json"
            result, receipt = self.run_cli(
                "apply", XBE, output, "--receipt", receipt_path,
                "--requests", ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json")
            self.assertEqual(result, 0)
            patched = output.read_bytes()
            self.assertEqual(receipt, json.loads(receipt_path.read_text()))
            self.assertEqual(mode.status(patched), "applied")
            self.assertEqual(receipt["executable_seed_bytes"], 0)
            self.assertEqual(receipt["journal_files"], 0)
            self.assertEqual(receipt["input_sha256"], RETAIL_SHA256)
            self.assertEqual(receipt["output_sha256"], hashlib.sha256(patched).hexdigest())
            self.assertEqual(receipt["total_file_growth"], len(patched) - len(self.retail))
            self.assertEqual(receipt["total_changed_bytes"],
                             sum(a != b for a, b in zip(self.retail, patched)) + len(patched) - len(self.retail))
            self.assertEqual({a["owner"] for a in mode.space.layout(patched)["allocations"]},
                             {r[0] for r in json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())}
                             | {"nfl2k5_xbe_space_directory", "nfl2k5_boot_logo"})
            _, replay = self.run_cli("apply", output, d / "replay.xbe")
            self.assertEqual((d / "replay.xbe").read_bytes(), patched)
            self.assertEqual(replay["total_changed_bytes"], 0)
            self.assertTrue(replay["already_applied"])
            self.assertEqual(self.run_cli("status", output)[1]["status"], "applied")

    def test_foreign_hook_and_existing_destinations_are_not_written(self):
        with tempfile.TemporaryDirectory(prefix="mycareer-refusal-") as folder:
            d = Path(folder).resolve()
            bad = bytearray(self.retail)
            im = XbeImage(bad)
            off = im.offset(0x16E50D)
            bad[off] ^= 1
            source, output = d / "foreign.xbe", d / "output.xbe"
            source.write_bytes(bad)
            for args in (("apply", source, output), ("apply", XBE, XBE)):
                with self.assertRaises(SystemExit) as error:
                    self.run_cli(*args)
                self.assertEqual(error.exception.code, 2)
            self.assertFalse(output.exists())
            output.write_bytes(b"existing")
            with self.assertRaises(SystemExit):
                self.run_cli("apply", XBE, output)
            self.assertEqual(output.read_bytes(), b"existing")
            self.assertFalse(list(d.glob(".mycareer-*")))

    def test_generic_disc_recipe_relocates_only_xbe_and_keeps_neighbour(self):
        from tools.mycareer_mode import build_disc
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        import shutil
        if shutil.disk_usage(Path(tempfile.gettempdir()).anchor).free < build_disc.MIN_FREE + 100 * 1024**2:
            self.skipTest("100 GB root reserve plus bounded fixture space required")
        with tempfile.TemporaryDirectory(prefix="mycareer-disc-fixture-") as folder:
            d = Path(folder).resolve()
            source, target = d / "source.iso", d / "career.iso"
            body = image_with_xbe(self.retail)
            source.write_bytes(body)
            receipt = build_disc.build(source, target, mode.REQUESTS)
            self.assertEqual(receipt["source_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(source.read_bytes(), body)
            with target.open("rb") as stream:
                off, size = build_disc.disc.image_xbe_extent(stream.fileno(), target.stat().st_size)
                executable = build_disc.io.pread(stream.fileno(), size, off)
                self.assertEqual(mode.status(executable), "applied")
                self.assertEqual(build_disc.io.pread(stream.fileno(), 8, body.index(b"KEEPTHIS")), b"KEEPTHIS")
            self.assertFalse(list(d.glob("mycareer-disc-*")))
            self.assertEqual(receipt["setup_files"], 0)
            self.assertEqual(receipt["journal_files"], 0)
            self.assertFalse(receipt["runtime_witnessed"])
            with self.assertRaisesRegex(ValueError, "separate new"):
                build_disc.build(source, target, mode.REQUESTS)

    def test_disc_space_refusal_leaves_no_image_or_stage(self):
        from tools.mycareer_mode import build_disc
        from tests.mod_editor.test_nfl2k5_xbe_space import image_with_xbe
        import shutil
        with tempfile.TemporaryDirectory(prefix="mycareer-disc-space-") as folder:
            d = Path(folder).resolve()
            source = d / "source.iso"
            source.write_bytes(image_with_xbe(self.retail))
            low = shutil.disk_usage(d)._replace(free=build_disc.MIN_FREE - 1)
            with patch.object(build_disc.shutil, "disk_usage", return_value=low):
                with self.assertRaisesRegex(ValueError, "100 GB"):
                    build_disc.build(source, d / "output.iso", mode.REQUESTS)
            self.assertEqual([p.name for p in d.iterdir()], ["source.iso"])


class CapabilityTests(unittest.TestCase):
    def test_fragment_schema_and_its_file_command_closure(self):
        from mod_editor.capabilities.validate_registry import DEFAULT_REGISTRY, validate_data, _command_module
        fragment = json.loads((ROOT / "docs/mod_editor/nfl2k5_my_career_mode_capabilities.json").read_text())
        registry = json.loads(DEFAULT_REGISTRY.read_text())
        fragment_ids = {cap["id"] for cap in fragment}
        registry["capabilities"] = [cap for cap in registry["capabilities"]
                                    if cap["id"] not in fragment_ids] + fragment
        registry["capabilities"].sort(key=lambda item: item["id"])
        # The baseline registry has unrelated absent research paths. Validate
        # its complete schema, then every path/command introduced here.
        validate_data(registry, check_files=False)
        for cap in fragment:
            for path in [cap["backend"]["module"], *cap["evidence"], *cap["runtime"]["evidence"]]:
                self.assertTrue((ROOT / path).is_file(), path)
            self.assertEqual(_command_module(cap["backend"]["command"], "backend"), cap["backend"]["module"])
            self.assertIsNotNone(_command_module(cap["validation_command"], "validation"))
            self.assertFalse(cap["gui"]["expose"])
            self.assertFalse(cap["gui"]["default_enabled"])


if __name__ == "__main__":
    unittest.main()
