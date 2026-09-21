"""Beta 74: modern colour's field-scene refits are cached on disk by content.

Every rebuild with Colour & lighting refit the same 390 distinct spans on a
process pool (two and a half minutes here, much longer on a laptop). The
result of a refit depends only on the span bytes, the settings and the
transform's sources, so it is kept under the private cache root and replayed
when the digests match. Synthetic spans through a stubbed worker; the real
transform is covered by test_nfl2k5_modern_color.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from mod_editor.core import nfl2k5_modern_color as colour
from mod_editor.core import nfl2k5_source_cache as source_cache


def fake_worker(args):
    kind, outer, span_hex, settings = args
    span = bytes.fromhex(span_hex)
    after = bytes((b + 1) & 255 for b in span)
    return (colour.settings_id(settings), kind, colour.sha(span)), after.hex(), dict(refit=True, outer=outer)


class RefitCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="b74-refit-cache-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spans = {("field", "a"): ("field", 3, bytes(range(64))),
                      ("normal", "b"): ("normal", 5, bytes(range(32)) * 2),
                      ("divots", "c"): ("divots", 7, b"\x10" * 48)}
        self.messages = []
        for patch in (mock.patch.object(source_cache, "default_cache_root", return_value=self.root),
                      mock.patch.object(colour, "_worker", side_effect=fake_worker),
                      mock.patch.dict(os.environ, {"NFL2K5_DISABLE_MODERN_COLOR_CACHE": "0"})):
            patch.start()
            self.addCleanup(patch.stop)
        self.worker = colour._worker

    def refit(self, settings=None):
        return colour._refit_fields(self.spans, progress=lambda m, d, t: self.messages.append(m),
                                    workers=1, settings=settings)

    def test_second_build_replays_from_the_cache(self):
        first = self.refit()
        self.assertEqual(self.worker.call_count, 3)
        self.assertEqual(colour._refit_fields.last_hits, 0)
        entries = sorted((self.root / "modern-colour-refits").glob("*.json"))
        self.assertEqual(len(entries), 3)
        second = self.refit()
        self.assertEqual(self.worker.call_count, 3, "nothing was refit again")
        self.assertEqual(colour._refit_fields.last_hits, 3)
        self.assertEqual(first, second)
        self.assertTrue(any("(3 cached)" in m for m in self.messages))

    def test_other_settings_miss_and_cache_separately(self):
        self.refit()
        settings = colour.default_settings()
        settings["values"]["turf.value_lift"] = 3.1
        self.refit(settings)
        self.assertEqual(self.worker.call_count, 6)
        self.assertEqual(len(list((self.root / "modern-colour-refits").glob("*.json"))), 6)

    def test_a_corrupted_entry_is_recomputed(self):
        first = self.refit()
        entry = next((self.root / "modern-colour-refits").glob("*.json"))
        envelope = json.loads(entry.read_bytes())
        payload = json.loads(envelope["payload"])
        payload["after"] = {"$bytes": "AAAA"}  # wrong bytes, envelope digest kept stale
        envelope["payload"] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        entry.write_text(json.dumps(envelope))
        self.assertEqual(self.refit(), first)
        self.assertEqual(self.worker.call_count, 4, "one entry was refit again")

    def test_an_entry_with_the_wrong_length_is_ignored(self):
        first = self.refit()
        # Forge an entry whose payload verifies but whose bytes are the wrong size.
        from mod_editor.core.nfl2k5_compile_cache import CompileCache
        cache = CompileCache(self.root / "modern-colour-refits")
        kind, outer, span = self.spans[("field", "a")]
        key = colour.sha(json.dumps([colour._refit_transform_key(), colour.settings_id(None), kind,
                                     colour.sha(span)], sort_keys=True).encode("utf-8"))
        cache.put(key, dict(span_sha256=colour.sha(span), after=b"\x00" * 3,
                            after_sha256=colour.sha(b"\x00" * 3), receipt={}))
        self.assertEqual(self.refit(), first)
        self.assertEqual(self.worker.call_count, 4)

    def test_transform_sources_are_part_of_the_key(self):
        self.refit()
        with mock.patch.object(colour, "_refit_transform_key", return_value=(("x", "changed"),)):
            self.refit()
        self.assertEqual(self.worker.call_count, 6)

    def test_environment_switch_disables_the_cache(self):
        with mock.patch.dict(os.environ, {"NFL2K5_DISABLE_MODERN_COLOR_CACHE": "1"}):
            self.refit()
            self.refit()
        self.assertEqual(self.worker.call_count, 6)
        self.assertFalse((self.root / "modern-colour-refits").exists())

    def test_longest_spans_go_first(self):
        order = []

        def recording(args):
            order.append(len(args[2]))
            return fake_worker(args)

        with mock.patch.dict(os.environ, {"NFL2K5_DISABLE_MODERN_COLOR_CACHE": "1"}), \
                mock.patch.object(colour, "_worker", side_effect=recording):
            self.refit()
        self.assertEqual(order, sorted(order, reverse=True))


if __name__ == "__main__":
    unittest.main()
