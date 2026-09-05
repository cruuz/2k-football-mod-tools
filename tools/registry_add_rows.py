#!/usr/bin/env python3
"""Add capability-registry rows for a game and move every count pin with them, atomically.

Until the registry validator derives its game list and coverage from the game
modules' fragments (docs/product/MULTI_GAME_INTERFACES_PLAN.md, section 5),
a game PR still has to edit the upstream files that hard-code them.  This
tool is the one command that does so mechanically, so a PR never hunts for
the thirteen count-pin sites by hand:

    python3 tools/registry_add_rows.py --game nfl2k5_ps2 --row new_row.json [--row ...] \\
        [--widen SURFACE ...] [--module NAME ...] [--dry-run]

Every edit is computed first and asserted to match EXACTLY ONCE before any
file is written; a literal that is not where the tool expects it stops the
run with nothing changed.  Count literals are located by their CURRENT value,
so the tool works from whatever the registry says today.

What it edits, for rows of an existing game:

* ``mod_editor/capabilities/registry.v1.json`` -- the rows, kept canonical
  (sorted ids, sorted keys, two-space indent, trailing newline);
* the row-count pins: ``tools/validate_all_mod_editor_capabilities.py``
  (EXPECTED_CAPABILITIES / _COVERED_CAPABILITIES / _UNIQUE_VALIDATORS),
  ``packaging/check_2k5_mod_studio_runtime.py`` (the ``require`` and the
  closure marker), ``packaging/check_apf2k8_mod_studio_runtime.py``,
  ``tests/mod_editor/test_apf_studio_installer.py``,
  ``tests/mod_editor/test_phase1_packaging.py`` (two), ``APF2K8-README.md``,
  ``docs/mod_editor/APF2K8_STATUS.md``,
  ``docs/mod_editor/2k5_mod_studio_getting_started.md``, ``STATUS.md``;
* ``--widen SURFACE``: the game joins ``SURFACE_GAMES["<surface>"]`` (appended to the existing tuple, or ``_LEGACY_GAMES + (game,)``) in
  ``mod_editor/capabilities/validate_registry.py`` (the coverage rule is set
  equality, so a row on a newly covered surface and its widening land together);
* ``--module NAME``: a ``product_modules`` entry in the 2K5 runtime gate;
* ``--allowlist-fragment FILE``: the module's ``allowlist.fragment.txt`` lines appended to
  ``packaging/release-allowlist.txt`` (a duplicate is fatal);
* ``--rc OLD NEW --changelog-section FILE --status-heading TEXT``: the RC bump
  every registry commit carries (version, its asserted spellings, the
  changelog section, the STATUS heading);
* ``--repin PATH``: re-hash a dict-shaped runtime pin (the RC29 dict).

``--new-game ENTRY.json --display-name TEXT`` additionally registers a game
id that does not exist yet: the ``games[]`` entry, the ``GameId`` enum member
and display name, the ``_game_id`` map, the ``_validate_games`` set, the
sample registry, ``GAMES`` and the games-count pin in the validator, both
``registry.schema.json`` id enums and ``project.schema.json``; and it rewrites
the coverage table so the surfaces every established game covers are not
demanded of the newcomer (``_ESTABLISHED_GAMES``), adding one line per
surface the new game's rows actually cover.  The enum value is the registry id.
``KNOWN_FINGERPRINTS`` (``mod_editor/core/sources.py``) stays manual: its kinds
are game-specific.

Standard library only.  Run the registry validator and the affected test
files afterwards; the tool prints the commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Optional, Sequence


class ApplyError(ValueError):
    """An edit could not be located exactly once, or an input is unfit; nothing was written."""


REGISTRY = "mod_editor/capabilities/registry.v1.json"
VALIDATOR = "mod_editor/capabilities/validate_registry.py"
CAPABILITIES = "mod_editor/core/capabilities.py"
MODEL = "mod_editor/core/model.py"
REGISTRY_SCHEMA = "mod_editor/capabilities/registry.schema.json"
PROJECT_SCHEMA = "mod_editor/project.schema.json"
RUNTIME_GATE = "packaging/check_2k5_mod_studio_runtime.py"
ALLOWLIST = "packaging/release-allowlist.txt"
APF_RUNTIME_GATE = "packaging/check_apf2k8_mod_studio_runtime.py"
INSTALLER_TEST = "tests/mod_editor/test_apf_studio_installer.py"
PACKAGING_TEST = "tests/mod_editor/test_phase1_packaging.py"
VALIDATE_ALL = "tools/validate_all_mod_editor_capabilities.py"
APF_README = "APF2K8-README.md"
APF_STATUS = "docs/mod_editor/APF2K8_STATUS.md"
GETTING_STARTED = "docs/mod_editor/2k5_mod_studio_getting_started.md"
STATUS = "STATUS.md"
CHANGELOG = "docs/mod_editor/2k5_mod_studio_changelog.md"
PACKAGE_INIT = "mod_editor/__init__.py"
FREEZE_TEST = "tests/mod_editor/test_beta45_honesty_freeze.py"

_GAME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
_NUMBER_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}


class Plan:
    """Every pending edit, computed before anything is written."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.pending: dict[Path, bytes] = {}
        self.log: list[str] = []

    def read(self, relative: str) -> str:
        path = self.root / relative
        if path in self.pending:
            return self.pending[path].decode("utf-8")
        if not path.is_file():
            raise ApplyError(f"{relative} is missing under {self.root}")
        return path.read_bytes().decode("utf-8")

    def stage(self, relative: str, text: str) -> None:
        if "\r" in text:
            raise ApplyError(f"{relative}: a CR crept in; every staged file is LF")
        self.pending[self.root / relative] = text.encode("utf-8")

    def once(self, relative: str, text: str, old: str, new: str) -> str:
        count = text.count(old)
        if count != 1:
            raise ApplyError(f"{relative}: expected exactly 1 match, found {count}: {old[:90]!r}")
        return text.replace(old, new)

    def edit(self, relative: str, pairs: Sequence[tuple[str, str]]) -> None:
        text = self.read(relative)
        for old, new in pairs:
            text = self.once(relative, text, old, new)
        self.stage(relative, text)

    def write(self) -> list[Path]:
        written = []
        for path, payload in self.pending.items():
            path.write_bytes(payload)
            written.append(path)
        return written


def counts(rows: Sequence[dict]) -> tuple[int, int, int]:
    total = len(rows)
    covered = sum(1 for row in rows if row.get("classification") not in ("unknown", "unsafe/deferred"))
    validators = len({row.get("validation_command") for row in rows if row.get("validation_command")})
    return total, covered, validators


def canonical(document: Any) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def load_row(path: Path, game: str, existing_ids: set[str]) -> dict:
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ApplyError(f"{path}: cannot read row JSON: {exc}") from exc
    if not isinstance(row, dict):
        raise ApplyError(f"{path}: a row must be a JSON object")
    row.pop("_DRAFT_NOTE", None)
    blob = json.dumps(row)
    if "TODO" in blob or "<N_" in blob or "FILL IN" in blob or "PLACEHOLDER" in blob:
        raise ApplyError(f"{path}: unfilled placeholder in the row")
    if row.get("game") != game:
        raise ApplyError(f"{path}: row game is {row.get('game')!r}, expected {game!r}")
    if not isinstance(row.get("id"), str) or not row["id"]:
        raise ApplyError(f"{path}: row has no id")
    if row["id"] in existing_ids:
        raise ApplyError(f"{row['id']} is already in the registry")
    return row


def add_rows(plan: Plan, game: str, row_files: Sequence[Path], new_game: Optional[dict]) -> tuple[list[dict], tuple[int, int, int], tuple[int, int, int]]:
    registry = json.loads(plan.read(REGISTRY))
    rows = registry["capabilities"]
    before = counts(rows)
    ids = {row["id"] for row in rows}
    added = []
    for path in row_files:
        row = load_row(path, game, ids)
        rows.append(row)
        ids.add(row["id"])
        added.append(row)
        plan.log.append(f"[row] + {row['id']}  ({row['surface']}, {row['classification']})")
    rows.sort(key=lambda row: row["id"])
    if new_game is not None:
        if any(entry.get("id") == game for entry in registry["games"]):
            raise ApplyError(f"{game} already has a games[] entry; drop --new-game")
        registry["games"].append(new_game)
        registry["games"].sort(key=lambda entry: entry["id"])
        plan.log.append(f"[game] + {game}")
    after = counts(rows)
    plan.stage(REGISTRY, canonical(registry))
    return added, before, after


def move_count_pins(plan: Plan, before: tuple[int, int, int], after: tuple[int, int, int]) -> None:
    (rows, covered, validators), (n_rows, n_covered, n_validators) = before, after
    plan.edit(RUNTIME_GATE, [
        (f"require(len(registry.capabilities) == {rows},", f"require(len(registry.capabilities) == {n_rows},"),
        (f'"registry={rows} sections=12 nfl2k5_capabilities=32 "', f'"registry={n_rows} sections=12 nfl2k5_capabilities=32 "'),
    ])
    plan.edit(APF_RUNTIME_GATE, [(f"len(registry.capabilities) == {rows}", f"len(registry.capabilities) == {n_rows}")])
    plan.edit(INSTALLER_TEST, [(f'"len(registry.capabilities) == {rows}"', f'"len(registry.capabilities) == {n_rows}"')])
    plan.edit(PACKAGING_TEST, [
        (f'"registry has {rows} cross-title rows"', f'"registry has {n_rows} cross-title rows"'),
        (f'"registry={rows} sections=12 nfl2k5_capabilities=32"', f'"registry={n_rows} sections=12 nfl2k5_capabilities=32"'),
    ])
    plan.edit(VALIDATE_ALL, [
        (f"EXPECTED_CAPABILITIES = {rows}", f"EXPECTED_CAPABILITIES = {n_rows}"),
        (f"EXPECTED_COVERED_CAPABILITIES = {covered}", f"EXPECTED_COVERED_CAPABILITIES = {n_covered}"),
        (f"EXPECTED_UNIQUE_VALIDATORS = {validators}", f"EXPECTED_UNIQUE_VALIDATORS = {n_validators}"),
    ])
    plan.edit(APF_README, [(
        f"APF capabilities ({rows} across all three registered game/platform targets),",
        f"APF capabilities ({n_rows} across all three registered game/platform targets),",
    )])
    plan.edit(APF_STATUS, [(f"contains {rows} records globally and 37 APF", f"contains {n_rows} records globally and 37 APF")])
    plan.edit(GETTING_STARTED, [(
        f"The current registry has {rows} cross-title rows, including 32 Xbox NFL 2K5",
        f"The current registry has {n_rows} cross-title rows, including 32 Xbox NFL 2K5",
    )])
    plan.edit(STATUS, [(
        f"| Capability registry | {rows} rows total; 32 Xbox NFL 2K5 rows; ",
        f"| Capability registry | {n_rows} rows total; 32 Xbox NFL 2K5 rows; ",
    )])
    plan.log.append(
        f"[counts] rows {rows}->{n_rows}  covered {covered}->{n_covered}  validators {validators}->{n_validators}"
    )


_SURFACE_LINE = re.compile(r'^SURFACE_GAMES\["[a-z_]+"\] = .*$', re.M)


def widen(plan: Plan, surfaces: Sequence[str], game: str, new_game: bool) -> None:
    """Make the coverage rule expect ``game`` on ``surfaces``.

    For an established game a surface joins the GAMES-wide rule.  For a new
    game a surface that already has an explicit rule gets the newcomer appended
    to it, and a surface still on the legacy default gets its own line -- the
    GAMES-wide rules were just rewritten to ``_ESTABLISHED_GAMES`` so nothing
    demands the newcomer elsewhere.
    """

    if not surfaces:
        return
    text = plan.read(VALIDATOR)
    # One rule for a new game and for an existing one: the game joins the
    # surface's coverage tuple. Writing "= GAMES" would demand every other
    # newcomer too, which is exactly what broke once a second game existed.
    if True:
        additions = []
        for surface in surfaces:
            pattern = re.compile(r'^SURFACE_GAMES\["' + re.escape(surface) + r'"\] = (.+)$', re.M)
            found = pattern.findall(text)
            if len(found) > 1:
                raise ApplyError(f"{VALIDATOR}: {surface} is assigned more than once")
            if found:
                if game in _games_named(text, found[0]):
                    raise ApplyError(f"{VALIDATOR}: {surface} is already widened: it already names {game}")
                text = pattern.sub(lambda match: f'SURFACE_GAMES["{surface}"] = {match.group(1)} + ("{game}",)', text)
            else:
                additions.append(f'SURFACE_GAMES["{surface}"] = _LEGACY_GAMES + ("{game}",)\n')
        if additions:
            matches = list(_SURFACE_LINE.finditer(text))
            if not matches:
                raise ApplyError(f"{VALIDATOR}: no SURFACE_GAMES assignment to append after")
            last = matches[-1]
            comment = f"# {game} covers these surfaces (one row each):\n"
            text = text[:last.end() + 1] + comment + "".join(additions) + text[last.end() + 1:]
    plan.stage(VALIDATOR, text)
    plan.log.append(f"[widen] {', '.join(surfaces)}")


def add_modules(plan: Plan, modules: Sequence[str]) -> None:
    if not modules:
        return
    text = plan.read(RUNTIME_GATE)
    for name in modules:
        if f'"{name}",' in text:
            raise ApplyError(f"{RUNTIME_GATE}: product_modules already has {name}")
    lines = text.split("\n")
    try:
        start = lines.index("    product_modules = (")
    except ValueError as exc:
        raise ApplyError(f"{RUNTIME_GATE}: product_modules tuple not found") from exc
    end = next((index for index in range(start + 1, len(lines)) if lines[index] == "    )"), None)
    if end is None:
        raise ApplyError(f"{RUNTIME_GATE}: product_modules tuple has no closing line")
    lines[end:end] = [f'        "{name}",' for name in modules]
    plan.stage(RUNTIME_GATE, "\n".join(lines))
    plan.log.append(f"[modules] + {', '.join(modules)}")


def add_allowlist_lines(plan: Plan, fragment: Optional[Path], game: str) -> None:
    """Append a module's allowlist fragment to the release allowlist; a duplicate is fatal."""

    if fragment is None:
        return
    lines = [line.strip() for line in fragment.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.strip().startswith("#")]
    if not lines:
        raise ApplyError(f"{fragment}: no allowlist lines to append")
    text = plan.read(ALLOWLIST)
    existing = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    duplicates = [line for line in lines if line in existing]
    if duplicates:
        raise ApplyError(f"{ALLOWLIST}: already lists {duplicates}")
    if not text.endswith("\n"):
        text += "\n"
    text += f"# {game}: shipped by the game module (mod_editor/games/{game}/allowlist.fragment.txt).\n"
    text += "".join(f"{line}\n" for line in lines)
    plan.stage(ALLOWLIST, text)
    plan.log.append(f"[allowlist] + {len(lines)} lines")


def register_new_game(plan: Plan, game: str, display_name: str, enum_member: str, title: str) -> None:
    """The sites only a new game id touches; each located exactly once."""

    # GameId enum member and display name.
    model = plan.read(MODEL)
    members = re.findall(r'^    ([A-Z0-9_]+) = "([a-z0-9_]+)"$', model, re.M)
    if not members:
        raise ApplyError(f"{MODEL}: GameId members not found")
    last_member, last_value = members[-1]
    model = plan.once(MODEL, model, f'    {last_member} = "{last_value}"\n', f'    {last_member} = "{last_value}"\n    {enum_member} = "{game}"\n')
    display_lines = re.findall(r'^            GameId\.([A-Z0-9_]+): "([^"]+)",$', model, re.M)
    if not display_lines:
        raise ApplyError(f"{MODEL}: display-name table not found")
    tail_member, tail_text = display_lines[-1]
    model = plan.once(MODEL, model, f'            GameId.{tail_member}: "{tail_text}",\n',
                      f'            GameId.{tail_member}: "{tail_text}",\n            GameId.{enum_member}: "{display_name}",\n')
    plan.stage(MODEL, model)

    # Loader: sample registry, required set, id map.
    capabilities = plan.read(CAPABILITIES)
    sample = re.search(r'^        \{"id": "([a-z0-9_]+)", "title": "([^"]+)"\},\n    \],\n    "capabilities": \[', capabilities, re.M)
    if sample is None:
        raise ApplyError(f"{CAPABILITIES}: sample registry games not found")
    capabilities = plan.once(CAPABILITIES, capabilities, sample.group(0),
                             f'        {{"id": "{sample.group(1)}", "title": "{sample.group(2)}"}},\n'
                             f'        {{"id": "{game}", "title": "{title}"}},\n    ],\n    "capabilities": [')
    required = re.search(r'^        required = \{("[a-z0-9_]+"(?:, "[a-z0-9_]+")*)\}\n        if seen != required:', capabilities, re.M)
    if required is None:
        raise ApplyError(f"{CAPABILITIES}: _validate_games required set not found")
    capabilities = plan.once(CAPABILITIES, capabilities, required.group(0),
                             f'        required = {{{required.group(1)}, "{game}"}}\n        if seen != required:')
    mapping = re.search(r'^            "([a-z0-9_]+)": GameId\.([A-Z0-9_]+),\n        \}\n        try:\n            return mapping\[registry_id\]', capabilities, re.M)
    if mapping is None:
        raise ApplyError(f"{CAPABILITIES}: _game_id mapping not found")
    capabilities = plan.once(CAPABILITIES, capabilities, mapping.group(0),
                             f'            "{mapping.group(1)}": GameId.{mapping.group(2)},\n'
                             f'            "{game}": GameId.{enum_member},\n        }}\n        try:\n            return mapping[registry_id]')
    plan.stage(CAPABILITIES, capabilities)

    # Validator: GAMES, the games-count pin, and the established-games tuple for coverage.
    validator = plan.read(VALIDATOR)
    games_match = re.search(r'^GAMES = \(("[a-z0-9_]+"(?:, "[a-z0-9_]+")*,?)\)$', validator, re.M)
    if games_match is None:
        raise ApplyError(f"{VALIDATOR}: GAMES tuple not found")
    ids = re.findall(r'"([a-z0-9_]+)"', games_match.group(1))
    new_ids = sorted(ids + [game])
    validator = plan.once(VALIDATOR, validator, games_match.group(0), "GAMES = (" + ", ".join(f'"{item}"' for item in new_ids) + ")")
    if "_ESTABLISHED_GAMES = " not in validator:
        # The first newcomer freezes the games every GAMES-wide rule was written
        # for; later newcomers find the tuple in place and join surfaces one by one.
        validator = plan.once(VALIDATOR, validator, "\n_LEGACY_GAMES = ",
                              "\n# The games every GAMES-wide surface rule was written for; a newer game\n"
                              "# covers only the surfaces its own rows declare below.\n"
                              "_ESTABLISHED_GAMES = (" + ", ".join(f'"{item}"' for item in ids) + ")\n_LEGACY_GAMES = ")
        validator = validator.replace('] = GAMES\n', '] = _ESTABLISHED_GAMES\n')
    count_match = re.search(r'len\(games\) == (\d+), "games: expected exactly (\w+) entries"', validator)
    if count_match is None:
        raise ApplyError(f"{VALIDATOR}: games-count pin not found")
    new_count = int(count_match.group(1)) + 1
    validator = plan.once(VALIDATOR, validator, count_match.group(0),
                          f'len(games) == {new_count}, "games: expected exactly {_NUMBER_WORDS.get(new_count, str(new_count))} entries"')
    coverage_default = 'for game in SURFACE_GAMES.get(surface, GAMES)'
    if coverage_default in validator:
        validator = plan.once(VALIDATOR, validator, coverage_default, 'for game in SURFACE_GAMES.get(surface, _ESTABLISHED_GAMES)')
    plan.stage(VALIDATOR, validator)

    # Both schema id enums, and the project schema.
    schema = plan.read(REGISTRY_SCHEMA)
    enum_block = '"enum": [\n            ' + ",\n            ".join(f'"{item}"' for item in ids) + "\n          ]"
    if schema.count(enum_block) != 2:
        raise ApplyError(f"{REGISTRY_SCHEMA}: expected the game-id enum twice, found {schema.count(enum_block)}")
    schema = schema.replace(enum_block, '"enum": [\n            ' + ",\n            ".join(f'"{item}"' for item in new_ids) + "\n          ]")
    plan.stage(REGISTRY_SCHEMA, schema)
    project = json.loads(plan.read(PROJECT_SCHEMA))
    enum = project["properties"]["game"]["enum"]
    if game in enum:
        raise ApplyError(f"{PROJECT_SCHEMA}: {game} already present")
    enum.append(game)
    plan.stage(PROJECT_SCHEMA, json.dumps(project, indent=2) + "\n")
    plan.log.append(f"[new-game] {game}: GameId.{enum_member}, loader, validator ({len(new_ids)} games), schemas")


def bump_rc(plan: Plan, old: str, new: str, section_path: Path, status_heading: str) -> None:
    section = section_path.read_text(encoding="utf-8")
    if not section.startswith(f"## v1.0 RC{new} ") or not section.endswith("\n\n"):
        raise ApplyError("the changelog section must start with its '## v1.0 RC<new> ' header and end with a blank line")
    plan.edit(PACKAGE_INIT, [(f'__version__ = "1.0.0rc{old}"', f'__version__ = "1.0.0rc{new}"')])
    plan.edit(FREEZE_TEST, [(f'"1.0.0rc{old}"', f'"1.0.0rc{new}"')])
    plan.edit(PACKAGING_TEST, [
        (f"'__version__ = \"1.0.0rc{old}\"'", f"'__version__ = \"1.0.0rc{new}\"'"),
        (f'"# 2K5 Mod Studio v1.0 RC{old} — Getting Started"', f'"# 2K5 Mod Studio v1.0 RC{new} — Getting Started"'),
        (f'"# 2K5 Mod Studio — v1.0 RC{old} Release Status"', f'"# 2K5 Mod Studio — v1.0 RC{new} Release Status"'),
    ])
    plan.edit(GETTING_STARTED, [(f"# 2K5 Mod Studio v1.0 RC{old} — Getting Started", f"# 2K5 Mod Studio v1.0 RC{new} — Getting Started")])
    plan.edit(STATUS, [
        (f"# 2K5 Mod Studio — v1.0 RC{old} Release Status", f"# 2K5 Mod Studio — v1.0 RC{new} Release Status"),
        (f"Source/UI versions are **2K5 RC{old}** and **APF alpha.84**.", f"Source/UI versions are **2K5 RC{new}** and **APF alpha.84**."),
    ])
    changelog = plan.read(CHANGELOG)
    head = f"## v1.0 RC{old} "
    if changelog.count(head) != 1:
        raise ApplyError(f"{CHANGELOG}: expected one '{head}' heading")
    index = changelog.index(head)
    plan.stage(CHANGELOG, changelog[:index] + section + changelog[index:])
    status = plan.read(STATUS)
    match = re.search(r"^## Beta (\d+) \(unreleased\) — .*$", status, re.M)
    if match is None:
        raise ApplyError(f"{STATUS}: no '## Beta N (unreleased)' heading")
    beta = int(match.group(1)) + 1
    plan.stage(STATUS, status[:match.start()] + f"## Beta {beta} (unreleased) — {status_heading}\n\n" + status[match.start():])
    plan.log.append(f"[rc] RC{old} -> RC{new}; STATUS Beta {beta}")


def repin(plan: Plan, paths: Sequence[str]) -> None:
    if not paths:
        return
    text = plan.read(RUNTIME_GATE)
    for relative in paths:
        current = hashlib.sha256((plan.root / relative).read_bytes()).hexdigest()
        pattern = re.compile(r'("' + re.escape(relative) + r'"\s*:\s*\n?\s*")([0-9a-f]{64})(")')
        found = pattern.findall(text)
        if len(found) != 1:
            raise ApplyError(f"{relative}: expected one dict pin in {RUNTIME_GATE}, found {len(found)}")
        if found[0][1] != current:
            text = pattern.sub(lambda match: match.group(1) + current + match.group(3), text)
            plan.log.append(f"[repin] {relative}: {found[0][1][:12]} -> {current[:12]}")
    plan.stage(RUNTIME_GATE, text)


def _tuple_literal(text: str, name: str) -> tuple:
    """The string members of ``NAME = ("a", "b")`` in the validator's source."""
    match = re.search(r'^' + re.escape(name) + r' = \((.*?)\)$', text, re.M)
    return tuple(re.findall(r'"([a-z0-9_]+)"', match.group(1))) if match else ()


def _games_named(text: str, expression: str) -> set:
    """Every game a SURFACE_GAMES right-hand side names, resolving GAMES / _ESTABLISHED_GAMES / _LEGACY_GAMES."""
    named = set(re.findall(r'"([a-z0-9_]+)"', expression))
    for symbol in ("GAMES", "_ESTABLISHED_GAMES", "_LEGACY_GAMES"):
        if re.search(r'\b' + symbol + r'\b', expression):
            named.update(_tuple_literal(text, symbol))
    return named


def apply(
    root: Path,
    *,
    game: str,
    rows: Sequence[Path],
    widen_surfaces: Sequence[str] = (),
    modules: Sequence[str] = (),
    new_game: Optional[Path] = None,
    display_name: Optional[str] = None,
    enum_member: Optional[str] = None,
    rc: Optional[tuple[str, str]] = None,
    changelog_section: Optional[Path] = None,
    status_heading: Optional[str] = None,
    repin_paths: Sequence[str] = (),
    allowlist_fragment: Optional[Path] = None,
    dry_run: bool = False,
) -> Plan:
    if _GAME_ID_RE.fullmatch(game) is None:
        raise ApplyError(f"game id {game!r} is not a registry game id")
    if not rows and new_game is None and allowlist_fragment is None and not modules:
        raise ApplyError("nothing to do: give --row, --new-game, --module or --allowlist-fragment")
    plan = Plan(root.resolve())
    entry = None
    if new_game is not None:
        entry = json.loads(new_game.read_text(encoding="utf-8"))
        if not isinstance(entry, dict) or entry.get("id") != game:
            raise ApplyError(f"{new_game}: the games[] entry must carry id {game!r}")
        if set(entry) != {"id", "platform", "public_input", "retail_identity", "title"}:
            raise ApplyError(f"{new_game}: games[] entry keys must be id, platform, public_input, retail_identity, title")
        if not display_name:
            raise ApplyError("--new-game needs --display-name")
        enum_member = enum_member or game.upper()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", enum_member) is None:
            raise ApplyError(f"--enum-member {enum_member!r} must be an UPPER_CASE identifier")
    added, before, after = add_rows(plan, game, list(rows), entry) if (rows or entry is not None) else ([], None, None)
    if entry is not None:
        register_new_game(plan, game, display_name or "", enum_member or game.upper(), str(entry["title"]))
        covered = sorted({row["surface"] for row in added})
        missing = [surface for surface in covered if surface not in widen_surfaces]
        if missing:
            raise ApplyError(f"a new game's rows cover {missing}; pass --widen for each covered surface")
    if before is not None and after is not None and before != after:
        move_count_pins(plan, before, after)
    widen(plan, widen_surfaces, game, entry is not None)
    add_modules(plan, modules)
    add_allowlist_lines(plan, allowlist_fragment, game)
    if rc is not None:
        if changelog_section is None or status_heading is None:
            raise ApplyError("--rc needs --changelog-section and --status-heading")
        bump_rc(plan, rc[0], rc[1], changelog_section, status_heading)
    repin(plan, repin_paths)
    if not dry_run:
        plan.write()
    return plan


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--game", required=True, help="registry game id the rows belong to")
    parser.add_argument("--row", action="append", default=[], type=Path, help="a complete registry row as JSON")
    parser.add_argument("--widen", action="append", default=[], metavar="SURFACE")
    parser.add_argument("--module", action="append", default=[], metavar="NAME", help="product_modules entry for the runtime gate")
    parser.add_argument("--new-game", type=Path, metavar="ENTRY.json", help="register a new game id with this games[] entry")
    parser.add_argument("--display-name", help="GameId display name for --new-game")
    parser.add_argument("--enum-member", help="GameId member name for --new-game (default: the id upper-cased)")
    parser.add_argument("--rc", nargs=2, metavar=("OLD", "NEW"))
    parser.add_argument("--changelog-section", type=Path)
    parser.add_argument("--status-heading")
    parser.add_argument("--repin", action="append", default=[], metavar="PATH")
    parser.add_argument("--allowlist-fragment", type=Path, metavar="FILE",
                        help="append this module allowlist fragment to packaging/release-allowlist.txt")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        plan = apply(
            args.repo_root, game=args.game, rows=args.row, widen_surfaces=args.widen, modules=args.module,
            new_game=args.new_game, display_name=args.display_name, enum_member=args.enum_member,
            rc=tuple(args.rc) if args.rc else None, changelog_section=args.changelog_section,
            status_heading=args.status_heading, repin_paths=args.repin,
            allowlist_fragment=args.allowlist_fragment, dry_run=args.dry_run,
        )
    except ApplyError as exc:
        print(f"REGISTRY_ADD_ROWS_REFUSED: {exc}", file=sys.stderr)
        return 1
    for line in plan.log:
        print(line)
    files = sorted(path.relative_to(plan.root).as_posix() for path in plan.pending)
    print(f"[plan] {len(files)} files: " + ", ".join(files))
    if args.dry_run:
        print("[dry-run] nothing written")
        return 0
    print("[write] done")
    print("next: python3 mod_editor/capabilities/validate_registry.py --skip-file-checks")
    print("      python3 tools/validate_all_mod_editor_capabilities.py   (needs the evidence tree)")
    print("      PYTHONPATH=. python3 tests/mod_editor/test_phase1_packaging.py")
    if args.game and (args.row or args.new_game):
        print(f"      python -m mod_editor.games fragments {args.game} --write   (if the game is a module)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
