"""Manifest recorder proof without writing a disc or regenerating protected JSON."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_music_playlist import XBE
from mod_editor.core import nfl2k5_music_playlist as playlist
from mod_editor.core import nfl2k5_cave_manifest as manifest


@unittest.skipUnless(XBE.is_file(), 'USA retail XBE absent; manifest observation requires pinned executable')
class ManifestTests(unittest.TestCase):
    def test_real_writer_records_all_hooks_and_three_complete_children(self):
        source = XBE.read_bytes()
        recorder = manifest.Recorder(source)
        result, _ = recorder.wrapper(playlist, 'apply')(source)
        spans = recorder.finish(result)
        for name, (va, before) in playlist.HOOKS.items():
            self.assertTrue(any(s['owner'] == playlist.OWNER and int(s['start'], 0) <= va
                                and int(s['end'], 0) >= va + len(before) for s in spans), name)
        for allocation in playlist.sites(result):
            self.assertTrue(any(s['owner'] == playlist.OWNER and int(s['start'], 0) == allocation['va']
                                and s['size'] == allocation['size'] for s in spans), allocation)
        self.assertEqual(recorder.steps[-1]['owner'], playlist.OWNER)
        # Repeat observation leaves the complete final ownership coverage valid.
        repeated, _ = recorder.wrapper(playlist, 'apply')(result)
        self.assertEqual(repeated, result)
        self.assertEqual(recorder.finish(repeated), spans)

    def test_complete_union_and_builder_include_playlist(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        self.assertTrue(all(r in REQUESTS for r in playlist.REQUESTS))
        # Inspect actual builder syntax without launching its multi-GB disc writer.
        import ast
        source = Path(manifest.__file__).read_text()
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_manifest')
        calls = [n for n in ast.walk(function) if isinstance(n, ast.Call)]
        self.assertTrue(any(isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                            and n.func.value.id == 'playlist' and n.func.attr == 'apply' for n in calls))
        self.assertTrue(any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                            and n.value.id == 'playlist' and n.attr == 'REQUESTS' for n in ast.walk(function)))


if __name__ == '__main__':
    unittest.main()
