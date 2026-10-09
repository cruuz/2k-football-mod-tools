"""The headless source command must enter the same authoring path as the GUI."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import modpack_sources
from mod_editor.core.nfl2k5_build_service import Nfl2k5BuildError
from tools import nfl2k5_modpack as cli


class SourceCommandTests(unittest.TestCase):
    def test_materialized_recipe_uses_gui_builder_and_records_its_result(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recipe = root / "editable recipe.json"
            project = root / "league project.json"
            recipe.write_text(json.dumps(dict(schema="softdrink_sources/v1",
                preset="softdrink_basic", overrides={}, project=str(project))))
            source, output, receipt = (root / name for name in
                                       ("retail.iso", "new.iso", "receipt.json"))
            expected = dict(target=str(output), outcome={"sha256": "test digest"})
            with mock.patch.object(modpack_sources, "build_project", return_value=expected) as build, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                result = cli.main(["build-sources", "--recipe", str(recipe), "--source", str(source),
                                   "--out", str(output), "--receipt", str(receipt), "--json"])
            self.assertEqual(result, 0)
            plan, passed_project, progress = build.call_args.args
            self.assertEqual((plan.source, plan.target, passed_project),
                             (str(source), str(output), str(project)))
            self.assertFalse(plan.overwrite)
            self.assertTrue(callable(progress))
            self.assertEqual(json.loads(receipt.read_text()), expected)
            self.assertEqual(json.loads(stdout.getvalue()), expected)

    def test_wrong_recipe_is_refused_without_starting_a_build(self):
        with tempfile.TemporaryDirectory() as folder:
            recipe = Path(folder) / "recipe.json"
            recipe.write_text('{"schema":"not a source recipe"}')
            with mock.patch.object(modpack_sources, "build_project") as build, \
                    contextlib.redirect_stderr(io.StringIO()):
                result = cli.main(["build-sources", "--recipe", str(recipe), "--source", "retail.iso",
                                   "--out", "new.iso"])
            self.assertEqual(result, 2)
            build.assert_not_called()

    def test_build_refusal_does_not_create_a_success_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            recipe, receipt = root / "recipe.json", root / "receipt.json"
            recipe.write_text(json.dumps(dict(schema="softdrink_sources/v1",
                preset="softdrink_basic", overrides={}, project="project.json")))
            with mock.patch.object(modpack_sources, "build_project", side_effect=Nfl2k5BuildError("source changed")), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                result = cli.main(["build-sources", "--recipe", str(recipe), "--source", "retail.iso",
                                   "--out", "new.iso", "--receipt", str(receipt)])
            self.assertEqual(result, 2)
            self.assertIn("source changed", stderr.getvalue())
            self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
