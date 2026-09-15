"""Run the existing Music contracts through the pending shared-entry wiring.

T3 owns nfl2k5_music_*; audio_conform.py's two shared entry bodies are handed
back in WIRING.md. These scoped replacements exercise that exact delegation
without changing unrelated audio importers or leaving global patches installed.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import audio_conform as shared, nfl2k5_music_conform as music


class WiredSuite(unittest.TestSuite):
    def run(self, result, debug=False):
        with patch.object(shared, 'conform_song', music.conform_song), \
             patch.object(shared, 'conform_music', music.conform_music):
            return super().run(result, debug)


def load_tests(loader, tests, pattern):
    return WiredSuite(loader.loadTestsFromNames([
        'tests.mod_editor.test_music_conform',
        'tests.mod_editor.test_music_simple',
        'tests.mod_editor.test_music_service',
    ]))


if __name__ == '__main__':
    unittest.main()
