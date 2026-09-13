"""Model and artwork project loading shares one durable session transaction."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_model_project as model
from mod_editor.core.nfl2k5_model_project_session import ModelProjectSession
from tests.mod_editor import test_studio_session as fixtures


class ModelLoadTransactionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StudioSessionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        root = self.fixture.root
        donor = ModelProjectSession(self.fixture.cache, self.fixture.catalog,
                                    root=root / "sessions", session_id="donor")
        png = root / "authored.png"
        png.write_bytes(b"USER-A-CONTAINER")
        donor.replace(self.fixture.asset, png)
        gltf = root / "authored.gltf"
        gltf.write_bytes(b"{}")
        self.record = dict(schema=model.SCHEMA, target="player-body-o3", mode="geometry",
                           summary="Synthetic checked edit", sources=model.source_files([gltf]),
                           options={}, check={}, witnessed=False, changed_bytes=1,
                           members=[dict(key="o3c113", size=64, before_sha256="a" * 64,
                                         after_sha256="b" * 64, decoded_sha256="c" * 64,
                                         changes=[[32, "eA=="]], decoded_changes=[[32, "eA=="]])])
        donor.stage_model(self.record)
        self.project = donor.save_shareable_project(root / "complete.2k5mod")
        self.loaded = ModelProjectSession(self.fixture.cache, self.fixture.catalog,
                                         root=root / "sessions", session_id="loaded")
        # Model lane correctness has separate real-writer tests. Only its source
        # reader is stubbed here; ZIP validation and session publication are real.
        self.enterContext(patch("mod_editor.core.nfl2k5_model_project_session.M.ModelSource"))
        self.enterContext(patch.object(model, "restore_member"))

    def test_failed_model_manifest_leaves_no_loaded_artwork_or_models(self):
        before = (self.loaded.root / "session.json").read_bytes()
        write = self.loaded._write_manifest

        def fail_complete_manifest():
            if self.loaded._manifest_document().get("model_edits"):
                raise OSError("Synthetic disk full while saving model state")
            return write()

        with patch.object(self.loaded, "_write_manifest", side_effect=fail_complete_manifest):
            with self.assertRaisesRegex(Exception, "Synthetic disk full"):
                self.loaded.load_shareable_project(self.project)
        self.assertEqual(self.loaded.modified_count, 0)
        self.assertEqual(self.loaded.model_records, ())
        self.assertEqual(tuple(self.loaded.iter_edits()), ())
        self.assertEqual((self.loaded.root / "session.json").read_bytes(), before)
        self.assertEqual(list(self.loaded.replacements.iterdir()), [])

    def test_success_publishes_models_and_artwork_in_the_same_manifest(self):
        documents = []
        write = self.loaded._write_manifest

        def observe():
            documents.append(self.loaded._manifest_document())
            return write()

        with patch.object(self.loaded, "_write_manifest", side_effect=observe):
            self.assertEqual(self.loaded.load_shareable_project(self.project), 2)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["model_edits"], [self.record])
        self.assertEqual(json.loads((self.loaded.root / "session.json").read_bytes())["model_edits"], [self.record])


if __name__ == "__main__":
    unittest.main()
