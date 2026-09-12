"""Beta 66.1: writers the unified visual tool loads by file path must not rely on bare relative imports.

Coach Edwards and maumau78 (2026-09-11): every build that touched a shoe or equipment texture failed with
"ImportError: attempted relative import with no known parent package". tools/nfl2k5_visual_mod_project.py
loads the reviewed writer files with importlib.util.spec_from_file_location under private names, so a
lazy ``from .x import y`` inside one of them raises at build time on every platform. Synthetic data only.
"""
import ast
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

TOOL = ROOT / "tools/nfl2k5_visual_mod_project.py"


def path_loaded_writers():
    """Every ``ROOT / "mod_editor/..."`` file the tool loads through spec_from_file_location."""
    source = TOOL.read_text(encoding="utf-8")
    found = []
    for match in re.finditer(r'path = ROOT / "(mod_editor/[^"]+\.py)"\n\s+spec = importlib\.util\.spec_from_file_location', source):
        found.append(match.group(1))
    return found


def unguarded_relative_imports(path: Path):
    """Relative imports that are not wrapped in a try/except ImportError fallback."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded = set()
    for node in ast.walk(tree):
        # try: from .x import y / except ImportError: absolute fallback
        if isinstance(node, ast.Try) and any(
            isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
            or isinstance(handler.type, ast.Tuple) and any(isinstance(e, ast.Name) and e.id == "ImportError" for e in handler.type.elts)
            for handler in node.handlers
        ):
            for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if isinstance(inner, ast.ImportFrom):
                    guarded.add(id(inner))
        # if __package__: from .x import y / else: package-free definition
        if isinstance(node, ast.If) and any(isinstance(n, ast.Name) and n.id == "__package__" for n in ast.walk(node.test)):
            for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
                if isinstance(inner, ast.ImportFrom):
                    guarded.add(id(inner))
    return [f"{path.name}:{node.lineno} from {'.' * node.level}{node.module or ''} import ..."
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level and id(node) not in guarded]


class PathLoadedWriterTests(unittest.TestCase):
    def test_tool_loads_seven_writers_by_path(self):
        writers = path_loaded_writers()
        self.assertGreaterEqual(len(writers), 7, writers)
        self.assertIn("mod_editor/core/nfl2k5_uniform_equipment_writer.py", writers)

    def test_no_path_loaded_writer_has_an_unguarded_relative_import(self):
        problems = []
        for rel in path_loaded_writers():
            problems += unguarded_relative_imports(ROOT / rel)
        self.assertEqual(problems, [], "these break every build under the unified tool: " + ", ".join(problems))

    def test_equipment_palette_runs_through_the_path_loaded_adapter(self):
        import nfl2k5_visual_mod_project as tool
        adapter = tool.uniform_equipment_adapter
        self.assertEqual(adapter.__package__, "", "the adapter is loaded without a package on purpose")
        # A two-colour 4x4 base level with its index bytes: the beta-66 palette projection must run here.
        rgba = bytes()
        indices = bytearray()
        for i in range(16):
            colour = (200, 30, 30, 255) if i % 2 else (20, 20, 220, 255)
            rgba += bytes(colour); indices.append(1 if i % 2 else 0)
        palette, used = adapter._project_palette([bytes(indices)], [SimpleNamespace(rgba=rgba)], 16)
        self.assertEqual(len(palette), 1024)
        self.assertEqual(used, 2)


if __name__ == "__main__":
    unittest.main()
