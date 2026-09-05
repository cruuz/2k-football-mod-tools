"""Split a capability registry into per-game fragments and merge them back.

The canonical registry (``mod_editor/capabilities/registry.v1.json``) is one
document holding every game's ``games[]`` entry and every game's rows, and its
validator hard-codes which games exist and which surfaces each must cover.
That is why every new game edits the validator.  This module is the other
shape: the *core* registry carries the games the core team owns, each game
package carries a fragment with its own entry, its rows and the surfaces it
covers, and validation merges them.

The merge is deterministic and lossless.  :func:`split` followed by
:func:`merge` reproduces the canonical document byte for byte (canonical
sorted JSON), which is what the test suite proves for every game the core
ships today.  The coverage rule the validator enforces --
``(game, surface)`` equality -- survives per game: a fragment declares the
surfaces it covers and the merge refuses a fragment whose rows disagree with
its declaration, so a game can neither claim a surface it has no row for nor
carry a row on a surface it did not declare.  Legacy games are covered by the
validator's own tables until they, too, are expressed as fragments.

Standard library only.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .contract import REGISTRY_FRAGMENT_SCHEMA, ContractError


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The registry's own canonical encoding: sorted keys, two-space indent, LF."""

    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ContractError(message)


def coverage(document: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """``surface -> games`` actually covered by the document's rows.

    This is the derived form of the validator's hand-maintained
    ``SURFACE_GAMES`` table: what the rows say, rather than what a constant
    says the rows must say.
    """

    found: dict[str, set[str]] = {}
    for row in document.get("capabilities", []):
        found.setdefault(row["surface"], set()).add(row["game"])
    return {surface: tuple(sorted(games)) for surface, games in sorted(found.items())}


def fragment_for(document: Mapping[str, Any], game_id: str) -> dict[str, Any]:
    """The fragment a game package would carry for ``game_id``."""

    entries = [game for game in document.get("games", []) if game.get("id") == game_id]
    _require(len(entries) == 1, f"registry: expected exactly one games[] entry for {game_id!r}.")
    rows = [row for row in document.get("capabilities", []) if row.get("game") == game_id]
    _require(bool(rows), f"registry: {game_id!r} has no capability rows to split out.")
    return {
        "schema": REGISTRY_FRAGMENT_SCHEMA,
        "game": dict(entries[0]),
        "surfaces": sorted({row["surface"] for row in rows}),
        "capabilities": sorted((dict(row) for row in rows), key=lambda row: row["id"]),
    }


def split(document: Mapping[str, Any], game_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """``(core_without_game, fragment)`` -- the inverse of :func:`merge`."""

    fragment = fragment_for(document, game_id)
    core = dict(document)
    core["games"] = [game for game in document["games"] if game.get("id") != game_id]
    core["capabilities"] = [row for row in document["capabilities"] if row.get("game") != game_id]
    return core, fragment


def validate_fragment(fragment: Mapping[str, Any]) -> None:
    """Shape and self-consistency of one fragment; the merged whole is validated later."""

    _require(isinstance(fragment, Mapping), "registry fragment: expected an object.")
    _require(
        set(fragment) == {"schema", "game", "surfaces", "capabilities"},
        f"registry fragment: keys differ: {sorted(fragment)}",
    )
    _require(
        fragment["schema"] == REGISTRY_FRAGMENT_SCHEMA,
        f"registry fragment: schema is {fragment['schema']!r}, expected {REGISTRY_FRAGMENT_SCHEMA}.",
    )
    game = fragment["game"]
    _require(isinstance(game, Mapping) and isinstance(game.get("id"), str) and game["id"],
             "registry fragment: game must be an object with a string id.")
    rows = fragment["capabilities"]
    _require(isinstance(rows, list) and rows, "registry fragment: capabilities must be a non-empty list.")
    ids = [row.get("id") for row in rows]
    _require(all(isinstance(item, str) and item for item in ids), "registry fragment: every row needs a string id.")
    _require(ids == sorted(ids), f"registry fragment for {game['id']}: rows must be sorted by id.")
    _require(len(ids) == len(set(ids)), f"registry fragment for {game['id']}: duplicate row id.")
    foreign = [row["id"] for row in rows if row.get("game") != game["id"]]
    _require(not foreign, f"registry fragment for {game['id']}: rows {foreign} belong to another game.")
    declared = fragment["surfaces"]
    _require(isinstance(declared, list) and declared == sorted(declared) and len(declared) == len(set(declared)),
             f"registry fragment for {game['id']}: surfaces must be a sorted list without repeats.")
    actual = sorted({row["surface"] for row in rows})
    _require(
        declared == actual,
        f"registry fragment for {game['id']}: declares surfaces {declared} but its rows cover {actual}; "
        "a game covers exactly the surfaces it declares.",
    )


def merge(core: Mapping[str, Any], fragments: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The full registry: the core document plus every fragment, canonically ordered.

    Refuses a fragment whose game the core already carries, two fragments for
    one game, and a row id that appears twice anywhere.  ``games[]`` and
    ``capabilities[]`` come out sorted by id -- the order the validator calls
    canonical -- so the result is independent of discovery order.
    """

    merged = dict(core)
    games = [dict(game) for game in core.get("games", [])]
    rows = [dict(row) for row in core.get("capabilities", [])]
    known_games = {game.get("id") for game in games}
    known_rows = {row.get("id") for row in rows}
    for fragment in fragments:
        validate_fragment(fragment)
        game_id = fragment["game"]["id"]
        _require(game_id not in known_games,
                 f"registry merge: game {game_id!r} is declared by the core and by a fragment.")
        known_games.add(game_id)
        games.append(dict(fragment["game"]))
        for row in fragment["capabilities"]:
            _require(row["id"] not in known_rows,
                     f"registry merge: capability {row['id']!r} appears twice.")
            known_rows.add(row["id"])
            rows.append(dict(row))
    merged["games"] = sorted(games, key=lambda game: game["id"])
    merged["capabilities"] = sorted(rows, key=lambda row: row["id"])
    return merged


__all__ = [
    "canonical_bytes",
    "coverage",
    "fragment_for",
    "merge",
    "split",
    "validate_fragment",
]
