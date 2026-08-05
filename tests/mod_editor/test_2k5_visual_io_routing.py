"""Every kind the extended visual IO can decode must be routed to it.

Reported symptom: the All Textures panel showed "Preview unavailable -- Export
is not implemented for asset kind 'p8_texture'" for every end-zone package, and
the same message killed the build at the bottom of the window.

The decoder was not missing. ``Nfl2k5ExtendedVisualIO._decode_original`` had a
``p8_texture`` branch the whole time. What was missing was one entry in
``Nfl2k5ProductVisualIO._extended_kinds``, the set the router consults, so those
assets were handed to the uniform IO -- which legitimately cannot decode them
and says so.

A router keyed off a hand-maintained list will drift from the decoder it routes
to, so this derives the expectation from the decoder itself rather than
restating the list.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MODULE = (
    _REPO_ROOT / "mod_editor" / "core" / "nfl2k5_extended_visual_io.py"
)


def _kinds_the_decoder_handles() -> set[str]:
    """Read the kinds compared in ``_decode_original`` straight from the source."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    for klass in ast.walk(tree):
        if not (isinstance(klass, ast.ClassDef)
                and klass.name == "Nfl2k5ExtendedVisualIO"):
            continue
        for node in ast.walk(klass):
            if isinstance(node, ast.FunctionDef) and node.name == "_decode_original":
                kinds: set[str] = set()
                for compare in ast.walk(node):
                    if not isinstance(compare, ast.Compare):
                        continue
                    left = compare.left
                    if not (isinstance(left, ast.Attribute) and left.attr == "kind"):
                        continue
                    for operand in compare.comparators:
                        if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                            kinds.add(operand.value)
                return kinds
    raise AssertionError("Nfl2k5ExtendedVisualIO._decode_original not found")


class RoutingTests(unittest.TestCase):
    def test_the_router_covers_every_kind_the_decoder_handles(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ProductVisualIO

        handled = _kinds_the_decoder_handles()
        routed = set(Nfl2k5ProductVisualIO._extended_kinds)
        missing = sorted(handled - routed)
        self.assertEqual(
            missing, [],
            "these kinds decode fine but are routed to the uniform IO, which "
            f"will report 'Export is not implemented': {missing}",
        )

    def test_p8_texture_specifically_is_routed(self) -> None:
        """The one that shipped broken; worth naming so it cannot slip again."""
        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ProductVisualIO

        self.assertIn("p8_texture", Nfl2k5ProductVisualIO._extended_kinds)
        self.assertIn("p8_texture", _kinds_the_decoder_handles())

    def test_the_router_claims_nothing_the_decoder_cannot_do(self) -> None:
        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ProductVisualIO

        handled = _kinds_the_decoder_handles()
        extra = sorted(set(Nfl2k5ProductVisualIO._extended_kinds) - handled)
        self.assertEqual(
            extra, [],
            f"routed to the extended IO but it has no branch for them: {extra}",
        )

    def test_all_textures_export_calls_the_extended_exporter(self) -> None:
        """Exercise the public route, not just the membership constant."""

        from mod_editor.core.nfl2k5_extended_visual_io import Nfl2k5ProductVisualIO

        calls: list[tuple[str, str, bool]] = []

        class Owner:
            def __init__(self, name: str) -> None:
                self.name = name

            def export_original(self, asset, destination, *, replace=False):
                calls.append((self.name, asset.kind, replace))
                return destination

        router = Nfl2k5ProductVisualIO.__new__(Nfl2k5ProductVisualIO)
        router.uniforms = Owner("uniform")
        router.extended = Owner("extended")
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export.png"
            result = router.export_original(
                SimpleNamespace(kind="p8_texture"), destination, replace=True
            )
        self.assertEqual(result, destination)
        self.assertEqual(calls, [("extended", "p8_texture", True)])


if __name__ == "__main__":
    unittest.main()
