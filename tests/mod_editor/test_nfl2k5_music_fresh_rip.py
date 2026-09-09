"""Beta-63 Music readiness on an opened-rip cache, with real synthetic scans."""
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_audio_origin_preparation import Nfl2k5AudioOriginPreparation
from mod_editor.core.nfl2k5_audio_source_containment import (
    Nfl2k5AudioSourceContainmentScanner,
    Nfl2k5AudioSourceContainmentStore,
)
from mod_editor.core.nfl2k5_audio_source_fingerprints import Nfl2k5AudioSourceFingerprintStore
from mod_editor.core.nfl2k5_source_cache import SOURCE_SHA256
from mod_editor.studio.facade import Nfl2k5StudioFacade
from tests.mod_editor.test_nfl2k5_audio_source_scan import SyntheticSourceFixture


class MusicFreshRipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = fixture = SyntheticSourceFixture(Path(temporary.name).resolve())
        # Exactly the field-report distinction: the stores retain the project's
        # identity while SourceCache uses the digest of the user's opened rip.
        fixture.pins = replace(fixture.pins, source_sha256=SOURCE_SHA256)
        fixture.store = Nfl2k5AudioSourceFingerprintStore(
            expected_source_sha256=SOURCE_SHA256,
            expected_standalone_count=1,
            expected_streaming_slot_count=2,
            expected_streaming_owner_count=2,
        )
        containment = Nfl2k5AudioSourceContainmentScanner(
            pins=fixture.pins,
            capacity_report=fixture.capacity_report,
            store=Nfl2k5AudioSourceContainmentStore(
                expected_source_sha256=SOURCE_SHA256,
                expected_cue_count=3,
                expected_owner_count=3,
            ),
            xdvdfs_parser=fixture.parser,
            decode_batch_bytes=144,
        )
        self.preparation = Nfl2k5AudioOriginPreparation(
            exact_scanner=fixture.scanner(), containment_scanner=containment,
        )
        self.facade = Nfl2k5StudioFacade(
            audio_origin_preparation=self.preparation, xemu_command=(),
        )
        self.facade._cache = fixture.cache
        # Readiness has not been short-circuited by an already loaded service.
        self.facade._audio_service = SimpleNamespace(audio_origin_ready=False)

    def test_empty_opened_rip_cache_prepares_both_inventories_and_reuses_them(self):
        fixture, preparation = self.fixture, self.preparation
        before = hashlib.sha256(fixture.source.read_bytes()).hexdigest()
        self.assertEqual(fixture.cache.root.name, before)
        self.assertEqual(fixture.cache.source.sha256, before)
        self.assertNotEqual(before, SOURCE_SHA256)
        self.assertFalse(self.facade.audio_editing_ready)
        events = []
        first = preparation.prepare(fixture.cache, lambda *event: events.append(event))
        self.assertFalse(first.exact_reused)
        self.assertFalse(first.containment_reused)
        self.assertTrue(self.facade.audio_editing_ready)
        for path in (first.exact_inventory, first.containment_inventory):
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent.parent, fixture.cache.root)
        # Run the scanners again to strictly parse and validate both published
        # documents, beyond the coordinator's inexpensive readiness probe.
        for scanner in (preparation.exact_scanner, preparation.containment_scanner):
            self.assertTrue(scanner.ensure(fixture.source, fixture.cache).reused_inventory)
        second = preparation.prepare(fixture.cache, lambda *_: None)
        self.assertTrue(second.exact_reused)
        self.assertTrue(second.containment_reused)
        self.assertEqual(events[-1], ("Audio editing safety data ready", 2, 2))
        self.assertEqual(hashlib.sha256(fixture.source.read_bytes()).hexdigest(), before)

    def test_foreign_folder_is_not_ready_and_explicit_preparation_still_refuses(self):
        foreign = self.fixture.cache.root.parent / ("d" * 64)
        foreign.mkdir(mode=0o700)
        cache = replace(self.fixture.cache, root=foreign)
        self.facade._cache = cache
        self.assertFalse(self.facade.audio_editing_ready)
        for scanner in (self.preparation.exact_scanner, self.preparation.containment_scanner):
            with self.subTest(store=type(scanner.store).__name__):
                with self.assertRaisesRegex(ValidationError, "does not belong"):
                    scanner.store.inventory_path(cache)
        with self.assertRaisesRegex(ValidationError, "does not belong"):
            self.preparation.prepare(cache, lambda *_: None)


if __name__ == "__main__":
    unittest.main()
