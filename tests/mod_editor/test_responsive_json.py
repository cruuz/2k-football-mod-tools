from pathlib import Path
import json
import io
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core.responsive_json import dump, load


class ResponsiveJsonTests(unittest.TestCase):
    def test_write_preserves_existing_metadata_bytes(self):
        value = {"schema": 1, "rows": [[i, "帽子", None, False, .125] for i in range(3000)]}
        stream = io.StringIO()
        dump(value, stream)
        self.assertEqual(stream.getvalue(), json.dumps(value, ensure_ascii=True, separators=(",", ":")))

    def test_metadata_shapes_unicode_and_buffer_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metadata.json"
            for value in ({"chunks": [{"id": i, "words": "é帽子", "data": [False, None, 1.2e-10]}
                                       for i in range(4000)]},
                          {"rows": [[[i, "test"] for i in range(10000)], [[1, 2, 3]]]},
                          {}, [], 1, "hello", True):
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                self.assertEqual(load(path), value)
            for padding in range(65525, 65540):
                path.write_text(' ' * padding + '[1.234e+29, true, "héllo"]', encoding="utf-8")
                self.assertEqual(load(path), [1.234e29, True, "héllo"])

    def test_invalid_or_truncated_json_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for raw in ('', '{', '[', '{"rows":[1,]}', '[1', 'null false', '{"a": 1}garbage',
                        '{3: 4}', '"unterminated', '[1e]', '\u00a0null', '[1,\v2]'):
                path.write_text(raw, encoding="utf-8")
                with self.subTest(raw=raw), self.assertRaises(json.JSONDecodeError):
                    load(path)


if __name__ == "__main__":
    unittest.main()
