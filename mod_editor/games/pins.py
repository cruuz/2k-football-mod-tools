"""Pins of the frozen contract files, and the one procedure that moves them.

The contract is a promise to game teams, so the files that *are* the contract
are pinned by SHA-256 in ``CONTRACT_PINS.json`` and checked by
``tests/mod_editor/test_games_contract_frozen.py``.  The set covers the
contract itself, discovery, the registry merge, the conformance harness, the
chooser, this module, and the contract tests -- including the frozen test, so
loosening the test is itself a pinned edit.

Pins are **loud, not preventive**: a determined edit can move them.  What the
rule buys is that moving them is an *event* with a procedure, never an
accident inside feature work:

1. bump ``CONTRACT_VERSION`` in ``contract.py`` (minor for an additive change,
   major for a rename or removal);
2. add a ``## <version> (unreleased)`` entry to ``CONTRACT_CHANGELOG.md``
   saying what changed and why a game written against the old version still
   loads (or does not);
3. ``python -m mod_editor.games pins --write`` -- the only path that rewrites
   the pins; it refuses when the version has not moved past a released entry;
4. run the conformance suite;
5. commit that alone, never together with feature work;
6. when the version ships, ``python -m mod_editor.games pins --release``
   drops the ``(unreleased)`` marker and rewrites the pins one last time.

While an entry is marked ``(unreleased)`` the version is under development and
its pins may be rewritten; once released, they are fixed until the next entry.
The changelog entry records the digest of the pins written for it, so a pins
file rewritten without a new entry no longer matches its version's entry.

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Optional

from .contract import CONTRACT_VERSION, ContractError

REPO_ROOT = Path(__file__).resolve().parents[2]
PINS_NAME = "CONTRACT_PINS.json"
CHANGELOG_NAME = "CONTRACT_CHANGELOG.md"
PINS_SCHEMA = "vc_game_module_contract_pins/v1"

#: Repository-relative paths whose bytes are the contract.  Adding a file here
#: is itself a pinned edit (this module is in the set).
FROZEN_FILES: tuple[str, ...] = (
    "mod_editor/games/__init__.py",
    "mod_editor/games/contract.py",
    "mod_editor/games/registry_merge.py",
    "mod_editor/games/conformance.py",
    "mod_editor/games/chooser.py",
    "mod_editor/games/chooser_qt.py",
    # The shell a module is drawn on: a game depends on the shape of its page,
    # so it moves through the version procedure like the rest.  Its service
    # (studio_service.py) and the lane verb stay out while the build page grows.
    "mod_editor/games/studio_qt.py",
    "mod_editor/games/pins.py",
    "tests/mod_editor/games_fakes.py",
    "tests/mod_editor/test_games_contract.py",
    "tests/mod_editor/test_games_contract_frozen.py",
    "tests/mod_editor/test_games_conformance.py",
    "tests/mod_editor/test_games_chooser.py",
)

_HEADING = re.compile(r"^## (?P<version>\d+\.\d+)(?P<unreleased> \(unreleased\))?\s*$")
_PINS_LINE = re.compile(r"^pins: (?P<digest>[0-9a-f]{64})\s*$")

PROCEDURE = (
    "The frozen contract files may only move through the version procedure: "
    "bump CONTRACT_VERSION in mod_editor/games/contract.py, add a "
    "'## <version> (unreleased)' entry to mod_editor/games/CONTRACT_CHANGELOG.md, "
    "run 'python -m mod_editor.games pins --write', run the conformance suite, "
    "and commit that alone. See docs/product/GAME_MODULE_CONTRACT.md."
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version_tuple(version: str) -> tuple[int, int]:
    major, minor = version.split(".")
    return int(major), int(minor)


def pins_path(root: Path = REPO_ROOT) -> Path:
    return Path(root) / "mod_editor" / "games" / PINS_NAME


def changelog_path(root: Path = REPO_ROOT) -> Path:
    return Path(root) / "mod_editor" / "games" / CHANGELOG_NAME


def compute(root: Path = REPO_ROOT, version: str = CONTRACT_VERSION) -> dict:
    """The pins document for the frozen files as they are on disk now."""

    files: dict[str, str] = {}
    for relative in FROZEN_FILES:
        path = Path(root) / relative
        if not path.is_file():
            raise ContractError(f"frozen file is missing: {relative}")
        files[relative] = _sha256(path)
    return {"schema": PINS_SCHEMA, "contract_version": version, "files": files}


def digest(document: dict) -> str:
    """The digest a changelog entry records for its pins."""

    body = {"contract_version": document["contract_version"], "files": document["files"]}
    return hashlib.sha256(
        (json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def canonical_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read(root: Path = REPO_ROOT) -> Optional[dict]:
    path = pins_path(root)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ContractError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("schema") != PINS_SCHEMA:
        raise ContractError(f"{path}: schema is not {PINS_SCHEMA}")
    if not isinstance(document.get("files"), dict) or not isinstance(document.get("contract_version"), str):
        raise ContractError(f"{path}: expected contract_version and files")
    return document


class ChangelogEntry:
    def __init__(self, version: str, unreleased: bool, line: int) -> None:
        self.version = version
        self.unreleased = unreleased
        self.line = line
        self.pins_digest: Optional[str] = None
        self.pins_line: Optional[int] = None


def changelog_entries(root: Path = REPO_ROOT) -> list[ChangelogEntry]:
    """Entries in file order (the first is the latest)."""

    path = changelog_path(root)
    if not path.is_file():
        return []
    entries: list[ChangelogEntry] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
        heading = _HEADING.match(raw)
        if heading:
            entries.append(ChangelogEntry(heading.group("version"), bool(heading.group("unreleased")), number))
            continue
        pins_line = _PINS_LINE.match(raw)
        if pins_line and entries and entries[-1].pins_digest is None:
            entries[-1].pins_digest = pins_line.group("digest")
            entries[-1].pins_line = number
    return entries


def entry_for(version: str, root: Path = REPO_ROOT) -> Optional[ChangelogEntry]:
    for entry in changelog_entries(root):
        if entry.version == version:
            return entry
    return None


def check(root: Path = REPO_ROOT, version: str = CONTRACT_VERSION) -> list[str]:
    """Every way the pins, the files and the changelog can disagree; empty when consistent."""

    problems: list[str] = []
    recorded = None
    try:
        recorded = read(root)
    except ContractError as exc:
        problems.append(str(exc))
    if recorded is None:
        if not problems:
            problems.append(f"{PINS_NAME} is missing; run 'python -m mod_editor.games pins --write'.")
        return problems
    if recorded["contract_version"] != version:
        problems.append(
            f"{PINS_NAME} was written for contract {recorded['contract_version']} but "
            f"contract.py says {version}; regenerate the pins through the procedure."
        )
    try:
        current = compute(root, version)
    except ContractError as exc:
        return problems + [str(exc)]
    missing = sorted(set(FROZEN_FILES) - set(recorded["files"]))
    extra = sorted(set(recorded["files"]) - set(FROZEN_FILES))
    if missing:
        problems.append(f"{PINS_NAME} does not pin: {missing}")
    if extra:
        problems.append(f"{PINS_NAME} pins files that are not frozen: {extra}")
    for relative, expected in sorted(recorded["files"].items()):
        actual = current["files"].get(relative)
        if actual is not None and actual != expected:
            problems.append(f"{relative} changed (pinned {expected[:12]}…, now {actual[:12]}…)")
    entries = changelog_entries(root)
    entry = entry_for(version, root)
    if entry is None:
        problems.append(f"{CHANGELOG_NAME} has no entry for contract {version}.")
    else:
        if entries and entries[0].version != version:
            problems.append(
                f"{CHANGELOG_NAME}: the latest entry is {entries[0].version}, not the current {version}."
            )
        expected_digest = digest(recorded)
        if entry.pins_digest is None:
            problems.append(f"{CHANGELOG_NAME}: the {version} entry records no 'pins:' digest.")
        elif entry.pins_digest != expected_digest:
            problems.append(
                f"{CHANGELOG_NAME}: the {version} entry records pins {entry.pins_digest[:12]}… but "
                f"{PINS_NAME} digests to {expected_digest[:12]}…; the pins moved without a new entry."
            )
    if problems:
        problems.append(PROCEDURE)
    return problems


def _write_digest_line(root: Path, entry: ChangelogEntry, new_digest: str) -> None:
    path = changelog_path(root)
    lines = path.read_text(encoding="utf-8").splitlines()
    line = f"pins: {new_digest}"
    if entry.pins_line is not None:
        lines[entry.pins_line] = line
    else:
        # Directly under the heading, then a blank line before the prose.
        lines.insert(entry.line + 1, line)
        if entry.line + 2 >= len(lines) or lines[entry.line + 2].strip():
            lines.insert(entry.line + 2, "")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write(root: Path = REPO_ROOT, version: str = CONTRACT_VERSION, *, release: bool = False) -> Path:
    """Rewrite the pins for ``version`` -- only when the procedure allows it."""

    entry = entry_for(version, root)
    if entry is None:
        raise ContractError(
            f"{CHANGELOG_NAME} has no '## {version}' entry; add one (marked '(unreleased)') "
            f"before writing pins. {PROCEDURE}"
        )
    recorded = read(root)
    if recorded is not None and _version_tuple(recorded["contract_version"]) > _version_tuple(version):
        raise ContractError(
            f"{PINS_NAME} was written for {recorded['contract_version']}, newer than {version}; "
            "the contract version never goes backwards."
        )
    entries = changelog_entries(root)
    if entries[0].version != version:
        raise ContractError(
            f"{CHANGELOG_NAME}: the latest entry is {entries[0].version}; the current contract "
            f"{version} must be the latest entry."
        )
    if release and not entry.unreleased:
        raise ContractError(f"Contract {version} is already released.")
    if (
        recorded is not None
        and _version_tuple(recorded["contract_version"]) == _version_tuple(version)
        and not entry.unreleased
    ):
        raise ContractError(
            f"Contract {version} is released; its pins are fixed. Bump CONTRACT_VERSION and add a "
            f"new '(unreleased)' entry instead. {PROCEDURE}"
        )
    if release:
        path = changelog_path(root)
        lines = path.read_text(encoding="utf-8").splitlines()
        lines[entry.line] = f"## {version}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        entry = entry_for(version, root)
        assert entry is not None
    document = compute(root, version)
    pins_path(root).write_bytes(canonical_bytes(document))
    _write_digest_line(root, entry, digest(document))
    return pins_path(root)


__all__ = [
    "CHANGELOG_NAME",
    "FROZEN_FILES",
    "PINS_NAME",
    "PINS_SCHEMA",
    "PROCEDURE",
    "ChangelogEntry",
    "changelog_entries",
    "changelog_path",
    "check",
    "compute",
    "digest",
    "entry_for",
    "pins_path",
    "read",
    "write",
]
