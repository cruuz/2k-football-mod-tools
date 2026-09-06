"""Fake game modules the contract tests share: one loadable, two refused.

Not a test module (no ``test_`` prefix), so CI's glob does not run it; it is
frozen with the contract tests because the negative controls depend on it.

``write_fake_root(directory)`` writes three packages under ``directory``:

* ``okgame`` -- loadable: contract v1, no lanes, three windows (one plain,
  one whose factory raises, one that needs the studio session), the first of
  them its ``studio_window``, complete fragments so the conformance harness
  passes with zero lanes;
* ``oldgame`` -- refused: its manifest declares ``vc_game_module/v9``;
* ``crashgame`` -- refused: its import raises ``ModuleNotFoundError``.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import textwrap

from mod_editor.games import contract, registry_merge

SHA = "0" * 64
REPO_ROOT = Path(__file__).resolve().parents[2]


def cli_command(*arguments: str) -> list[str]:
    """``python -m mod_editor.games <arguments>`` without relying on PYTHONPATH.

    The installed Windows runtime is an embeddable CPython whose ``._pth``
    ignores PYTHONPATH, so a subprocess test that depended on it passed
    everywhere except where users actually run the product.  Inserting the
    repository root from inside the child is what works on every runtime.
    """

    bootstrap = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from mod_editor.games.__main__ import main; "
        "sys.exit(main(sys.argv[2:]))"
    )
    return [sys.executable, "-c", bootstrap, str(REPO_ROOT), *arguments]

OK_GAME_SOURCE = textwrap.dedent(
    '''
    from __future__ import annotations
    from pathlib import Path
    from mod_editor.games.contract import (CONTRACT_SCHEMA, GameIdentity, GameModule,
                                           SourceIdentity, WindowSpec, load_manifest)

    HERE = Path(__file__).resolve().parent
    CALLS = []

    class Identifier:
        accepted_suffixes = (".bin",)
        def identify(self, path):
            path = Path(path)
            return SourceIdentity("fake", str(path), path.stat().st_size if path.exists() else 0,
                                  "FAKE-00001", None, True, False, f"{path.name} — fake source")

    def window(parent=None, **context):
        CALLS.append(dict(context))
        try:
            from PyQt5.QtWidgets import QDialog
        except ImportError:
            return {"opened": True}
        dialog = QDialog(parent)
        dialog.setWindowTitle("Fake window")
        return dialog

    def failing(parent=None, **context):
        raise RuntimeError("the window exploded")

    GAME = GameModule(
        contract=CONTRACT_SCHEMA,
        identity=GameIdentity("okgame", "OK Game", "Test Console", ("FAKE-00001",), (), ()),
        identifier=Identifier(),
        lanes=(),
        windows=(
            WindowSpec("main", "OK Game window…", "Opens the fake window.", "okgame", window),
            WindowSpec("broken", "Broken window…", "Always fails.", "okgame-broken", failing),
            WindowSpec("session", "Needs session…", "Needs the studio.", "okgame-session", window,
                       needs_studio_session=True),
        ),
        manifest=load_manifest(HERE),
        package=__name__,
        studio_window="main",
    )
    '''
)

INCOMPATIBLE_CONTRACT = "vc_game_module/v9"


def manifest(game_id: str, **overrides) -> dict:
    document = {
        "schema": contract.MANIFEST_SCHEMA,
        "game_id": game_id,
        "package": f"mod_editor.games.{game_id}",
        "title": f"{game_id} title",
        "platform": "Test Console",
        "console": "TC",
        "game": "Fake",
        "year": "1",
        "version": "2.3.4",
        "contract": contract.CONTRACT_SCHEMA,
        "registry_fragment": "registry.fragment.json",
        "allowlist_fragment": "allowlist.fragment.txt",
        "pins": "pins.json",
        "product_modules": [],
        "tool_modules": [],
    }
    document.update(overrides)
    return document


def write_fragments(directory: Path, game_id: str, title: str) -> None:
    fragment = {
        "schema": contract.REGISTRY_FRAGMENT_SCHEMA,
        "game": {
            "id": game_id, "platform": "Test Console",
            "public_input": "A fake console image nobody owns; tests only.",
            "retail_identity": {"content_sha256": SHA, "executable_sha256": SHA},
            "title": title,
        },
        "surfaces": ["saves"],
        "capabilities": [{
            "id": f"{game_id}.saves.fake", "game": game_id, "surface": "saves",
            "classification": "unknown", "backend": {"operation": "none", "module": None, "command": None},
            "validation_command": None,
        }],
    }
    (directory / "registry.fragment.json").write_bytes(registry_merge.canonical_bytes(fragment))
    (directory / "allowlist.fragment.txt").write_text(
        "mod_editor/games/contract.py\n", encoding="utf-8", newline="\n")
    (directory / "pins.json").write_text(
        json.dumps({"schema": contract.PINS_SCHEMA, "game_id": game_id, "capability_rows": 1}, indent=2) + "\n",
        encoding="utf-8", newline="\n")


def write_fake_game(root: Path, game_id: str, source: str, document: dict | None,
                    *, with_fragments: bool = False, title: str = "") -> Path:
    directory = root / game_id
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text(source, encoding="utf-8", newline="\n")
    if document is not None:
        (directory / contract.MANIFEST_NAME).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if with_fragments:
        write_fragments(directory, game_id, title or document.get("title", game_id) if document else game_id)
    return directory


def write_fake_root(root: Path) -> Path:
    """The three packages every negative control uses."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    # Distinct game words so the chooser's console/game/year ordering is
    # visible: TC Crash 1 Studio, TC OK 1 Studio, TC Old 1 Studio.
    write_fake_game(root, "okgame", OK_GAME_SOURCE, manifest("okgame", title="OK Game", game="OK"),
                    with_fragments=True, title="OK Game")
    write_fake_game(root, "oldgame", OK_GAME_SOURCE,
                    manifest("oldgame", title="Old Game", game="Old", contract=INCOMPATIBLE_CONTRACT))
    write_fake_game(root, "crashgame", "import a_dependency_nobody_has\n",
                    manifest("crashgame", title="Crash Game", game="Crash"))
    return root


#: The exact sentence the chooser shows for the incompatible module.
def incompatible_reason(root: Path) -> str:
    return (
        f"{Path(root) / 'oldgame' / contract.MANIFEST_NAME}: declares contract "
        f"'{INCOMPATIBLE_CONTRACT}'; this core hosts {contract.CONTRACT_SCHEMA}."
    )


__all__ = [
    "INCOMPATIBLE_CONTRACT",
    "REPO_ROOT",
    "cli_command",
    "OK_GAME_SOURCE",
    "SHA",
    "incompatible_reason",
    "manifest",
    "write_fake_game",
    "write_fake_root",
    "write_fragments",
]
