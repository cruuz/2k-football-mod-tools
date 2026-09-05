"""Discovery of game modules: the one seam the core needs to host N games.

A game is a package under ``mod_editor/games/<game>/`` that carries a
``game.json`` manifest and exposes a ``GAME`` object built from
:mod:`mod_editor.games.contract`.  Nothing here names a game.  The core asks
this module three questions and never imports a game by name:

* :func:`manifests` -- the declarative half of every game, read without
  importing any code.  This is what gates use: registry validation merges
  each manifest's registry fragment, release staging appends each allowlist
  fragment, the runtime closure imports each manifest's module lists.
* :func:`discover` -- the behavioural half: import each package, take its
  ``GAME``, check the contract.  A package that fails is *reported*, not
  skipped silently, and never prevents the others from loading.
* :func:`load` -- one game by id, for a window or a command line.

Discovery is deliberately filesystem-based rather than entry-point based: the
products ship as a copied tree (``stage_release.py``), not as an installed
distribution, so there is no metadata to consult.  A directory is the unit of
ownership -- a game team owns everything under its directory and nothing
outside it.

Standard library only; importing this module imports no game and no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Optional

from .contract import (
    CONTRACT_SCHEMA,
    GAME_ATTRIBUTE,
    MANIFEST_NAME,
    ContractError,
    GameManifest,
    GameModule,
    Refusal,
    WindowSpec,
    load_manifest,
)

GAMES_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RefusedGame:
    """A package under the games root that could not be hosted, and why.

    ``title``, ``platform``, ``version`` and ``contract`` are read leniently
    from the package's ``game.json`` so a chooser can still show *which* game
    was refused; each falls back to ``"?"`` when the manifest cannot say.
    """

    directory: str
    reason: str
    title: str = "?"
    platform: str = "?"
    version: str = "?"
    contract: str = "?"

    @property
    def game_id(self) -> str:
        return self.directory


def _lenient_fields(directory: Path) -> dict[str, str]:
    """Display fields from a possibly-invalid manifest; never raises."""

    fields = {"title": "?", "platform": "?", "version": "?", "contract": "?"}
    try:
        document = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fields
    if isinstance(document, dict):
        for key in fields:
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                fields[key] = value.strip()
    return fields


@dataclass(frozen=True)
class DiscoveryReport:
    """Every hosted game plus every refusal, so nothing fails silently."""

    games: tuple[GameModule, ...]
    refused: tuple[RefusedGame, ...]

    def game(self, game_id: str) -> GameModule:
        for candidate in self.games:
            if candidate.game_id == game_id:
                return candidate
        known = ", ".join(sorted(item.game_id for item in self.games)) or "none"
        raise Refusal(f"No hosted game is called {game_id!r}; hosted games: {known}.")

    @property
    def game_ids(self) -> tuple[str, ...]:
        return tuple(sorted(item.game_id for item in self.games))


def _candidate_directories(root: Path) -> Iterator[Path]:
    """Subdirectories that look like game packages, in sorted order."""

    if not root.is_dir():
        return
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if not (entry / "__init__.py").is_file():
            continue
        yield entry


def manifests(root: Optional[Path] = None) -> tuple[GameManifest, ...]:
    """Every game manifest under ``root``, validated, without importing code.

    A package directory without a ``game.json`` is not a game and is ignored;
    a ``game.json`` that fails validation raises, because a gate reading it
    must not proceed on a half-read declaration.
    """

    found: list[GameManifest] = []
    seen: dict[str, str] = {}
    for directory in _candidate_directories(Path(root) if root else GAMES_ROOT):
        if not (directory / MANIFEST_NAME).is_file():
            continue
        manifest = load_manifest(directory)
        if manifest.game_id in seen:
            raise ContractError(
                f"Game id {manifest.game_id!r} is declared by both "
                f"{seen[manifest.game_id]} and {directory.name}."
            )
        seen[manifest.game_id] = directory.name
        found.append(manifest)
    return tuple(found)


def _import_package(directory: Path, root: Path) -> Any:
    if root == GAMES_ROOT:
        return importlib.import_module(f"{__name__}.{directory.name}")
    # A foreign root (tests use one): load the package from its path without
    # touching the real ``mod_editor.games`` namespace.
    name = f"_mod_editor_games_probe.{directory.name}"
    spec = importlib.util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    if spec is None or spec.loader is None:
        raise ContractError(f"{directory}: cannot build an import spec.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def discover(root: Optional[Path] = None) -> DiscoveryReport:
    """Import every game package under ``root`` and validate its ``GAME``.

    Fail closed per game: a package whose manifest, import or ``GAME`` object
    is unacceptable becomes a :class:`RefusedGame` with the sentence that
    explains it, and the remaining games still load.  A directory with no
    ``game.json`` is not a game and is not reported.
    """

    base = Path(root) if root else GAMES_ROOT
    games: list[GameModule] = []
    refused: list[RefusedGame] = []
    seen_ids: dict[str, str] = {}
    for directory in _candidate_directories(base):
        if not (directory / MANIFEST_NAME).is_file():
            continue
        try:
            manifest = load_manifest(directory)
            module = _import_package(directory, base)
            game = getattr(module, GAME_ATTRIBUTE, None)
            if game is None:
                raise ContractError(
                    f"{manifest.package} exposes no module-level {GAME_ATTRIBUTE}."
                )
            if not isinstance(game, GameModule):
                raise ContractError(
                    f"{manifest.package}.{GAME_ATTRIBUTE} is not a GameModule from "
                    f"{CONTRACT_SCHEMA}."
                )
            if game.manifest.root != manifest.root:
                raise ContractError(
                    f"{manifest.package}: GAME.manifest was loaded from "
                    f"{game.manifest.root}, not from its own package directory."
                )
            if game.game_id in seen_ids:
                raise ContractError(
                    f"Game id {game.game_id!r} is claimed by both "
                    f"{seen_ids[game.game_id]} and {directory.name}."
                )
        except ContractError as exc:
            refused.append(RefusedGame(directory.name, str(exc), **_lenient_fields(directory)))
            continue
        except Exception as exc:  # an import error inside the game package
            refused.append(
                RefusedGame(
                    directory.name,
                    f"{exc.__class__.__name__}: {exc}",
                    **_lenient_fields(directory),
                )
            )
            continue
        seen_ids[game.game_id] = directory.name
        games.append(game)
    return DiscoveryReport(tuple(games), tuple(refused))


def load(game_id: str, root: Optional[Path] = None) -> GameModule:
    """One hosted game by id; a refused game is reported with its reason."""

    report = discover(root)
    for game in report.games:
        if game.game_id == game_id:
            return game
    for item in report.refused:
        if item.directory == game_id:
            raise Refusal(f"Game {game_id!r} could not be hosted: {item.reason}")
    return report.game(game_id)


def registry_fragments(root: Optional[Path] = None) -> tuple[dict[str, Any], ...]:
    """Every game's registry fragment, for the validator's merge step."""

    return tuple(manifest.registry_document() for manifest in manifests(root))


def allowlist_lines(root: Optional[Path] = None) -> tuple[str, ...]:
    """Every game's shipped files, for release staging and the release gate."""

    lines: list[str] = []
    owners: dict[str, str] = {}
    for manifest in manifests(root):
        for line in manifest.allowlist_lines():
            if line in owners:
                raise ContractError(
                    f"{line} is shipped by both {owners[line]} and {manifest.game_id}."
                )
            owners[line] = manifest.game_id
            lines.append(line)
    return tuple(lines)


def runtime_modules(root: Optional[Path] = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(product_modules, tool_modules)`` every game adds to the runtime closure."""

    product: list[str] = []
    tools: list[str] = []
    for manifest in manifests(root):
        product.extend(manifest.product_modules)
        tools.extend(manifest.tool_modules)
    return tuple(product), tuple(tools)


def window_specs(root: Optional[Path] = None) -> tuple[tuple[GameModule, WindowSpec], ...]:
    """Every hosted game's windows, in discovery order, for a File menu."""

    return tuple(
        (game, window)
        for game in discover(root).games
        for window in game.windows
    )


__all__ = [
    "DiscoveryReport",
    "GAMES_ROOT",
    "RefusedGame",
    "allowlist_lines",
    "discover",
    "load",
    "manifests",
    "registry_fragments",
    "runtime_modules",
    "window_specs",
]
