"""Scaffold a game module that passes the conformance suite on day one.

    python -m mod_editor.games new <game-id> --title "Madden NFL 08 (USA, PlayStation 2)" \
        --platform "PlayStation 2" [--serial SLUS-21638]

writes ``mod_editor/games/<game-id>/`` -- manifest, ``GAME``, one **example
lane** over a synthetic "slot file" format with a synthetic source and a
known-good edit, the registry/allowlist/pins fragments, the two validators --
and ``tests/mod_editor/test_<game-id>_module.py``.  Everything is under the
game's own directory; no upstream file is touched.

The example lane is a teaching template and a placeholder, not a capability.
Its registry row is complete so the row-insertion tool can read it, but it
must be deleted or replaced by a real lane before the game's first PR: the
canonical registry never carries a row for a format no game has.

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Optional, Sequence

from .contract import CONTRACT_SCHEMA, MANIFEST_SCHEMA, PINS_SCHEMA, REGISTRY_FRAGMENT_SCHEMA, ContractError
from .registry_merge import canonical_bytes

REPO_ROOT = Path(__file__).resolve().parents[2]
_GAME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
PLACEHOLDER_SHA256 = "0" * 64
DEFAULT_SERIAL = "EXAMPLE-0001"

INIT_TEMPLATE = '''"""__TITLE__ (__PLATFORM__) as a game module.

Scaffolded by ``python -m mod_editor.games new``.  Everything this game needs
lives under this directory; the core discovers it and never needs an edit.

Replace :class:`ExampleLane` with real lanes -- each wraps a catalogue tool, a
patcher and an independent verifier and ships a synthetic source the
conformance suite can prove it on (see docs/product/ADDING_A_GAME_MODULE.md).
Delete ``example_lane.py`` and its registry row before the first real PR.
"""

from __future__ import annotations

from pathlib import Path

from mod_editor.games.contract import CONTRACT_SCHEMA, GameIdentity, GameModule, load_manifest

from .example_lane import ExampleLane, SlotFileIdentifier

HERE = Path(__file__).resolve().parent
GAME_ID = "__GAME_ID__"

IDENTITY = GameIdentity(
    game_id=GAME_ID,
    title="__TITLE__",
    platform="__PLATFORM__",
    serials=__SERIAL_TUPLE__,
    # Fill in the retail digests the game recognises (hashes only, never payload).
    executable_sha256=(),
    content_sha256=(),
)

GAME = GameModule(
    contract=CONTRACT_SCHEMA,
    identity=IDENTITY,
    identifier=SlotFileIdentifier(IDENTITY),
    lanes=(ExampleLane(GAME_ID),),
    windows=(),
    manifest=load_manifest(HERE),
    package=__name__,
)

__all__ = ["GAME", "GAME_ID", "IDENTITY"]
'''

MAIN_TEMPLATE = '''"""``python -m mod_editor.games.__GAME_ID__``: this game alone, with no studio."""

from __future__ import annotations

import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Imported here, not at module level: a game package reaches the core only
    # through the contract at import time (the boundary check enforces it).
    from mod_editor.games.__main__ import main as games_main

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        return games_main(["open", "__GAME_ID__", *arguments])
    return games_main(["show", "__GAME_ID__"])


if __name__ == "__main__":
    raise SystemExit(main())
'''

EXAMPLE_LANE_TEMPLATE = '''"""The example lane: a fixed-allocation text writer over a synthetic slot file.

This is the shape every real lane has -- catalogue, inline check, recipe, plan,
build, independent verify, a synthetic source and a known-good edit -- shown
on a format that carries no game data: ``SLOT`` files hold a serial and a
fixed number of 32-character text slots.  A real lane wraps a catalogue tool,
a patcher and a verifier from ``tools/`` exactly the way this file wraps its
own helpers, and keeps the same disciplines: the source is opened read-only, a
destination must not exist, a write never grows or moves a slot, every changed
byte is declared, and the verifier re-derives the layout instead of trusting
the receipt.

Command line (what the validators run)::

    python -m mod_editor.games.__GAME_ID__.example_lane --selftest
    python -m mod_editor.games.__GAME_ID__.example_lane --source in.slot \\
        --destination out.slot --recipe recipe.json [--receipt receipt.json]

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Callable, Mapping, Optional, Sequence

from mod_editor.games.contract import (
    Catalogue,
    DeclaredRange,
    Edit,
    GameIdentity,
    Plan,
    Receipt,
    Refusal,
    SourceIdentity,
    Target,
    Verdict,
    require,
)

MAGIC = b"SLOT"
SLOT_SIZE = 32
SERIAL_SIZE = 16
HEADER = struct.Struct("<4sHH16s")  # magic, slot count, slot size, serial
SOURCE_KIND = "slot-file"
DEFAULT_SERIAL = "EXAMPLE-0001"


class SlotFileError(ValueError):
    """The slot file is not what its header says."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_header(data: bytes, label: str) -> tuple[int, int, str]:
    if len(data) < HEADER.size or data[:4] != MAGIC:
        raise SlotFileError(f"{label} is not a slot file (no SLOT header).")
    _magic, count, size, serial = HEADER.unpack_from(data, 0)
    if size != SLOT_SIZE:
        raise SlotFileError(f"{label} uses {size}-byte slots; this lane handles {SLOT_SIZE}-byte slots.")
    if len(data) != HEADER.size + count * size:
        raise SlotFileError(f"{label} declares {count} slots but its length does not agree.")
    return count, size, serial.rstrip(b"\\0").decode("ascii", "replace")


def build_slot_file(serial: str, texts: Sequence[str]) -> bytes:
    body = bytearray(HEADER.pack(MAGIC, len(texts), SLOT_SIZE, serial.encode("ascii")[:SERIAL_SIZE].ljust(SERIAL_SIZE, b"\\0")))
    for text in texts:
        body += text.encode("ascii").ljust(SLOT_SIZE, b"\\0")
    return bytes(body)


def slot_offset(index: int) -> int:
    return HEADER.size + index * SLOT_SIZE


class SlotFileIdentifier:
    """Say which slot file this is, against one game's identity."""

    accepted_suffixes = (".slot",)

    def __init__(self, identity: GameIdentity) -> None:
        self.identity = identity

    def identify(self, path: Path) -> SourceIdentity:
        path = Path(path)
        try:
            info = path.lstat()
        except OSError as exc:
            raise Refusal(f"{path} cannot be opened: {exc}. Choose a slot file.") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise Refusal(f"{path} is not a regular file; a source must be one.")
        try:
            count, _size, serial = read_header(path.read_bytes(), path.name)
        except (SlotFileError, OSError) as exc:
            raise Refusal(str(exc)) from exc
        matches = not self.identity.serials or serial in self.identity.serials
        return SourceIdentity(
            kind=SOURCE_KIND,
            path=str(path),
            size_bytes=int(info.st_size),
            serial=serial,
            executable_sha256=None,
            serial_matches=matches,
            retail_executable=False,
            headline=f"{path.name} — {serial}{'' if matches else ' (unexpected serial)'} · {count} slots · {info.st_size:,} bytes",
            details={"slots": count, "slot_size": SLOT_SIZE},
        )


class ExampleLane:
    """Rewrite one or more 32-character slots inside their own allocation."""

    lane_id = "example.slots"
    surface = "menus"
    title = "Example slot text (placeholder lane)"
    classification = "offline-writer-proved"
    fixed_allocation = True

    def __init__(self, game_id: str) -> None:
        self.game_id = game_id
        self.capability_id = f"{game_id}.menus.example_slots"
        self.recipe_schema = f"{game_id}_example_recipe/v1"
        self.write_schema = f"{game_id}_example_write/v1"
        self.validators = (
            f"mod_editor/games/{game_id}/validate_example.sh",
            f"mod_editor/games/{game_id}/validate_example.bat",
        )

    # -- catalogue -----------------------------------------------------

    def build_catalogue(self, source: Path, *, progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        data = Path(source).read_bytes()
        try:
            count, _size, serial = read_header(data, Path(source).name)
        except SlotFileError as exc:
            raise Refusal(str(exc)) from exc
        rows = []
        for index in range(count):
            offset = slot_offset(index)
            span = data[offset:offset + SLOT_SIZE]
            used = len(span.rstrip(b"\\0"))
            rows.append({"slot": index, "offset": offset, "length": SLOT_SIZE, "used": used,
                         "span_sha256": _sha256(span)})
        document = {"schema": f"{self.game_id}_example_catalog/v1", "serial": serial,
                    "slot_size": SLOT_SIZE, "targets": rows}
        targets = tuple(
            Target(key=f"slot:{row['slot']}", label=f"slot {row['slot']} ({row['used']} of {SLOT_SIZE} characters used)",
                   detail=f"offset 0x{row['offset']:x}", budget=f"{SLOT_SIZE} ASCII characters, never longer",
                   searchable=f"slot {row['slot']}", raw=row)
            for row in rows
        )
        return Catalogue(document["schema"], self.lane_id, str(source), targets, document)

    # -- editing -------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"text"})
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not a field this lane edits; give text."
        text = values.get("text")
        if not isinstance(text, str):
            return f"{target.key}: give the replacement text."
        if "\\0" in text or not text.isascii() or not text.isprintable():
            return f"{target.key}: use printable ASCII without NUL; the slot stores ASCII bytes."
        if len(text) > SLOT_SIZE:
            return f"{target.key}: that text is {len(text)} characters; the slot holds {SLOT_SIZE}. Shorten it to {SLOT_SIZE}."
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        return {"schema": self.recipe_schema,
                "edits": [{"slot": edit.target_key, "text": edit.values.get("text", "")} for edit in edits]}

    def _parse(self, recipe: Mapping[str, Any]) -> list[tuple[str, str]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, expected {self.recipe_schema}")
        edits = recipe.get("edits")
        require(isinstance(edits, list) and edits, "a recipe must carry a non-empty 'edits' list")
        parsed: list[tuple[str, str]] = []
        seen: set[str] = set()
        for number, raw in enumerate(edits):
            require(isinstance(raw, Mapping) and set(raw) == {"slot", "text"}, f"edit {number} must carry slot and text only")
            key, text = str(raw["slot"]), raw["text"]
            require(key not in seen, f"{key} appears twice; one slot may be written once")
            seen.add(key)
            problem = self.check_edit(Target(key, key), {"text": text})
            require(problem is None, problem or "")
            parsed.append((key, text))
        return parsed

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        parsed = self._parse(recipe)
        data = Path(source).read_bytes()
        try:
            count, _size, _serial = read_header(data, Path(source).name)
        except SlotFileError as exc:
            raise Refusal(str(exc)) from exc
        ranges: list[DeclaredRange] = []
        rows = []
        for key, text in parsed:
            target = catalogue.target(key)  # refuses an unknown slot with the catalogue's sentence
            index = int(target.raw["slot"])
            require(index < count, f"{key} is not one of the {count} slots in this file")
            offset = slot_offset(index)
            before = data[offset:offset + SLOT_SIZE]
            require(_sha256(before) == target.raw["span_sha256"],
                    f"{key}: the file changed since it was catalogued; rebuild the catalogue")
            after = text.encode("ascii").ljust(SLOT_SIZE, b"\\0")
            require(after != before, f"{key} already holds that text; refusing a write that changes nothing")
            ranges.append(DeclaredRange(offset, SLOT_SIZE, key))
            rows.append({"slot": key, "offset": offset, "length": SLOT_SIZE,
                         "before_sha256": _sha256(before), "after_sha256": _sha256(after)})
        return Plan(self.lane_id, tuple(key for key, _ in parsed), tuple(ranges), {"edits": rows})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any], catalogue: Catalogue,
              *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        require(destination.resolve() != source.resolve(), f"{destination} is the source; a build writes a NEW file.")
        require(not destination.exists(), f"destination {destination} already exists; refusing to overwrite")
        planned = self.plan(source, recipe, catalogue)
        data = bytearray(Path(source).read_bytes())
        for (key, text), item in zip(self._parse(recipe), planned.document["edits"]):
            data[item["offset"]:item["offset"] + SLOT_SIZE] = text.encode("ascii").ljust(SLOT_SIZE, b"\\0")
        try:
            with open(destination, "xb") as handle:  # exclusive: never overwrites
                handle.write(bytes(data))
        except FileExistsError as exc:
            raise Refusal(f"destination {destination} appeared meanwhile; refusing to overwrite") from exc
        document = {"schema": self.write_schema, "source": str(source), "destination": str(destination),
                    "edits": list(planned.document["edits"]),
                    "declared_ranges": [{"start": r.start, "length": r.length, "reason": r.reason} for r in planned.declared_ranges],
                    "source_sha256": _sha256(Path(source).read_bytes()), "destination_sha256": _sha256(bytes(data))}
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), planned.declared_ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        """Independent: re-read both files and compare, trusting nothing in the receipt."""

        left, right = Path(source).read_bytes(), Path(destination).read_bytes()
        try:
            read_header(left, "the source")
            read_header(right, "the destination")
        except SlotFileError as exc:
            return Verdict(False, f"Verification failed: {exc}")
        if len(left) != len(right):
            return Verdict(False, f"Verification failed: sizes differ ({len(left)} vs {len(right)}).")
        ranges = [(r.start, r.length) for r in receipt.declared_ranges]
        for offset, (a, b) in enumerate(zip(left, right)):
            if a != b and not any(s <= offset < s + n for s, n in ranges):
                return Verdict(False, f"Verification failed: byte 0x{offset:x} changed outside every declared range.")
        for item in receipt.document.get("edits", []):
            span = right[item["offset"]:item["offset"] + item["length"]]
            if _sha256(span) != item["after_sha256"]:
                return Verdict(False, f"Verification failed: {item['slot']} does not hold the bytes the receipt recorded.")
            if _sha256(left[item["offset"]:item["offset"] + item["length"]]) != item["before_sha256"]:
                return Verdict(False, f"Verification failed: the source does not hold the bytes the receipt recorded for {item['slot']}.")
        return Verdict(True, f"{len(ranges)} slot(s) verified; {len(left) - sum(n for _, n in ranges):,} unchanged bytes compared.",
                       {"result": "PASS"})

    # -- what CI proves it on ------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"{self.game_id}-example.slot"
        path.write_bytes(build_slot_file(_EXAMPLE_SERIAL, ("ALPHA", "BRAVO", "", "DELTA")))
        return path

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        return (Edit("slot:1", {"text": "CHARLIE"}, note="conformance"),)


_EXAMPLE_SERIAL = __SERIAL_LITERAL__


def selftest() -> int:
    import tempfile

    lane = ExampleLane("__GAME_ID__")
    with tempfile.TemporaryDirectory() as work:
        room = Path(work)
        source = lane.synthetic_source(room)
        catalogue = lane.build_catalogue(source)
        recipe = lane.compose_recipe(lane.conformance_edits(catalogue))
        receipt = lane.build(source, room / "out.slot", recipe, catalogue)
        verdict = lane.verify(source, room / "out.slot", receipt)
        if not verdict.passed:
            print(f"FAIL: {verdict.summary}", file=sys.stderr)
            return 1
        tampered = bytearray((room / "out.slot").read_bytes())
        tampered[-1] ^= 0xFF
        (room / "tampered.slot").write_bytes(bytes(tampered))
        if lane.verify(source, room / "tampered.slot", receipt).passed:
            print("FAIL: a tampered file verified", file=sys.stderr)
            return 1
    print("__GAME_ID_UPPER___EXAMPLE_SELFTEST_OK")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--recipe", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.source and args.destination and args.recipe):
        parser.error("--source, --destination and --recipe are required (or --selftest)")
    lane = ExampleLane("__GAME_ID__")
    try:
        catalogue = lane.build_catalogue(args.source)
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        receipt = lane.build(args.source, args.destination, recipe, catalogue)
        verdict = lane.verify(args.source, args.destination, receipt)
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.receipt:
        args.receipt.write_text(json.dumps(dict(receipt.document), indent=2, sort_keys=True) + "\\n",
                                encoding="utf-8", newline="\\n")
    print(verdict.summary)
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''

VALIDATE_SH_TEMPLATE = '''#!/usr/bin/env bash
# Deterministic validator for the __TITLE__ example lane (a placeholder).
#
# Runs the example lane's self-test: a synthetic slot file is catalogued, one
# slot is rewritten inside its own allocation into a new file, the independent
# verifier passes, and a byte changed outside the declared range fails it.
# No game data is required.  Replace this with your real lanes' validators.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/__GAME_ID__/example_lane.py
python3 -m mod_editor.games.__GAME_ID__.example_lane --selftest

echo "__GAME_ID_UPPER___EXAMPLE_VALIDATION_PASS"
'''

VALIDATE_BAT_TEMPLATE = '''@echo off
setlocal enableextensions
rem Windows validator for the __TITLE__ example lane (a placeholder).
rem Mirrors validate_example.sh: runs the example lane's self-test.
rem No game data is required.

rem Run from the repository root, three levels up from this script.
cd /d "%~dp0..\\..\\.."

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
    echo Python 3 was not found on PATH.
    exit /b 1
)

%PY_CMD% -m py_compile mod_editor\\games\\__GAME_ID__\\example_lane.py || exit /b 1
%PY_CMD% -m mod_editor.games.__GAME_ID__.example_lane --selftest || exit /b 1

echo __GAME_ID_UPPER___EXAMPLE_VALIDATION_PASS
exit /b 0
'''

TEST_TEMPLATE = '''"""Conformance for the __TITLE__ game module.  No game data.

The generic harness proves the module on its own synthetic sources; the
fragment check proves the committed mirrors agree with the canonical registry
and allowlist once the game's rows and files are in them.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import conformance, fragments  # noqa: E402

GAME_ID = "__GAME_ID__"


class __CLASS_NAME__ModuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work = Path(tempfile.mkdtemp(prefix=f"{GAME_ID}-conformance-"))
        self.addCleanup(shutil.rmtree, self.work, True)

    def test_the_module_conforms(self) -> None:
        game = games.load(GAME_ID)
        result = conformance.run(game, self.work)
        self.assertTrue(result.passed, "\\n".join(check.line() for check in result.failures))

    def test_fragments_match_the_canonical_files(self) -> None:
        self.assertEqual(fragments.check(GAME_ID), [])


if __name__ == "__main__":
    unittest.main()
'''

ALLOWLIST_HEADER = (
    "# Files {title} ships, one per line, repository-relative.\n"
    "# Regenerated by `python -m mod_editor.games fragments {game_id} --write` from\n"
    "# packaging/release-allowlist.txt using the manifest's allowlist_patterns.\n"
)

PACKAGE_FILES = (
    "__init__.py", "__main__.py", "allowlist.fragment.txt", "example_lane.py", "game.json",
    "pins.json", "registry.fragment.json", "validate_example.bat", "validate_example.sh",
)


def _render(template: str, **values: str) -> str:
    text = template
    for key, value in values.items():
        text = text.replace(f"__{key}__", value)
    return text


def example_row(game_id: str, title: str, platform: str) -> dict:
    """A complete registry row for the example lane, so the row tool can read it."""

    module = f"mod_editor/games/{game_id}/example_lane.py"
    return {
        "backend": {
            "command": f"python3 -m mod_editor.games.{game_id}.example_lane --source <in.slot> --destination <new.slot> --recipe <recipe.json> [--receipt <receipt.json>]",
            "module": module,
            "operation": "write",
        },
        "classification": "offline-writer-proved",
        "evidence": [f"tests/mod_editor/test_{game_id}_module.py"],
        "game": game_id,
        "gui": {
            "default_enabled": False,
            "expose": False,
            "mode": "edit",
            "reason": "PLACEHOLDER: the scaffold's example lane over a synthetic slot file. Delete or replace it before the first real row; it never enters the canonical registry.",
        },
        "id": f"{game_id}.menus.example_slots",
        "input_constraints": [
            f"Exact allocation, never longer: a slot holds 32 ASCII characters; longer text is refused before anything is written.",
            "The source is opened read-only; the destination must not exist; every refusal leaves no destination behind.",
        ],
        "portme": ["Replace with the game's real lanes; this row documents the shape only."],
        "public_distribution": {
            "game_data": "never-bundle-retail-data",
            "mod_payload": "user-authored-inputs-and-recipes",
            "rule": "Ship the lane, its validators and user-authored recipes; sources and outputs stay with the user.",
            "tooling": "source-and-schemas-only",
        },
        "runtime": {"evidence": [], "scope": "Synthetic only: a placeholder format no game uses.", "status": "not-tested"},
        "selectors": {
            "fields": [
                {"allowed": "slot:<index> from the catalogue", "name": "slot", "required": True},
                {"allowed": "up to 32 printable ASCII characters", "name": "text", "required": True},
            ],
            "notes": "One recipe entry rewrites one slot inside its own 32-byte allocation.",
        },
        "source_container": {
            "format": "Synthetic SLOT file: header plus fixed 32-byte text slots.",
            "hash_pins": [],
            "resource": "N text slots, each 32 bytes",
            "retail_file": f"None: a synthetic example for {title} ({platform}).",
        },
        "summary": f"PLACEHOLDER example lane for {title}: rewrite 32-character text slots of a synthetic slot file inside their allocation, with an independent verifier.",
        "surface": "menus",
        "title": f"{title} example slot text (placeholder)",
        "validation_command": f"bash mod_editor/games/{game_id}/validate_example.sh",
    }


def scaffold(game_id: str, title: str, platform: str, serial: Optional[str] = None,
             *, repo_root: Path = REPO_ROOT) -> list[Path]:
    """Write the module and its test; return the paths written.  Refuses to overwrite."""

    if _GAME_ID_RE.fullmatch(game_id) is None:
        raise ContractError(
            f"Game id {game_id!r} must be lowercase letters, digits and underscores, 3 to 64 "
            "characters, starting with a letter or digit (e.g. madden08_ps2)."
        )
    if not title.strip() or not platform.strip():
        raise ContractError("--title and --platform must be non-empty.")
    package = Path(repo_root) / "mod_editor" / "games" / game_id
    test_path = Path(repo_root) / "tests" / "mod_editor" / f"test_{game_id}_module.py"
    if package.exists():
        raise ContractError(f"{package} already exists; refusing to overwrite a game module.")
    if test_path.exists():
        raise ContractError(f"{test_path} already exists; refusing to overwrite.")
    serial_tuple = f'("{serial}",)' if serial else "()"
    serial_literal = json.dumps(serial or DEFAULT_SERIAL)
    upper = game_id.upper()
    class_name = "".join(part.capitalize() for part in game_id.split("_"))
    values = dict(GAME_ID=game_id, TITLE=title, PLATFORM=platform, SERIAL_TUPLE=serial_tuple,
                  SERIAL_LITERAL=serial_literal, GAME_ID_UPPER=upper, CLASS_NAME=class_name)

    package.mkdir(parents=True)
    written: list[Path] = []

    def put(name: str, payload: bytes, *, executable: bool = False) -> None:
        path = package / name
        path.write_bytes(payload)
        if executable:
            path.chmod(path.stat().st_mode | 0o111)
        written.append(path)

    put("__init__.py", _render(INIT_TEMPLATE, **values).encode("utf-8"))
    put("__main__.py", _render(MAIN_TEMPLATE, **values).encode("utf-8"))
    put("example_lane.py", _render(EXAMPLE_LANE_TEMPLATE, **values).encode("utf-8"))
    put("validate_example.sh", _render(VALIDATE_SH_TEMPLATE, **values).encode("utf-8"), executable=True)
    put("validate_example.bat", _render(VALIDATE_BAT_TEMPLATE, **values).replace("\n", "\r\n").encode("utf-8"))

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "game_id": game_id,
        "package": f"mod_editor.games.{game_id}",
        "title": title,
        "platform": platform,
        "version": "0.1.0",
        "contract": CONTRACT_SCHEMA,
        "registry_fragment": "registry.fragment.json",
        "allowlist_fragment": "allowlist.fragment.txt",
        "pins": "pins.json",
        "product_modules": [f"mod_editor.games.{game_id}", f"mod_editor.games.{game_id}.example_lane"],
        "tool_modules": [],
    }
    put("game.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))

    fragment = {
        "schema": REGISTRY_FRAGMENT_SCHEMA,
        "game": {
            "id": game_id,
            "platform": platform,
            "public_input": f"FILL IN: what the user supplies for {title} (their own legally obtained image or save); the tool never bundles game files.",
            "retail_identity": {"content_sha256": PLACEHOLDER_SHA256, "executable_sha256": PLACEHOLDER_SHA256},
            "title": title,
        },
        "surfaces": ["menus"],
        "capabilities": [example_row(game_id, title, platform)],
    }
    put("registry.fragment.json", canonical_bytes(fragment))

    lines = [f"mod_editor/games/{game_id}/{name}" for name in PACKAGE_FILES]
    put("allowlist.fragment.txt", (ALLOWLIST_HEADER.format(title=title, game_id=game_id) + "\n".join(lines) + "\n").encode("utf-8"))

    pins = {
        "schema": PINS_SCHEMA,
        "game_id": game_id,
        "capability_rows": 1,
        "surfaces": ["menus"],
        "hidden_disc_writers": 1,
        "save_writer_ids": [],
        "shipped_files": len(lines),
        "product_modules": 2,
        "windows": 0,
        "lanes_on_contract": 1,
        "retail_identity": {"content_sha256": PLACEHOLDER_SHA256, "executable_sha256": PLACEHOLDER_SHA256},
    }
    put("pins.json", (json.dumps(pins, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_bytes(_render(TEST_TEMPLATE, **values).encode("utf-8"))
    written.append(test_path)
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mod_editor.games new", description=__doc__.splitlines()[0])
    parser.add_argument("game")
    parser.add_argument("--title", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--serial", default=None)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        written = scaffold(args.game, args.title, args.platform, args.serial, repo_root=args.repo_root)
    except ContractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}")
    print(
        f"SCAFFOLDED game={args.game} files={len(written)}\n"
        f"next: python -m mod_editor.games conformance --game {args.game}\n"
        f"      PYTHONPATH=. python tests/mod_editor/test_{args.game}_module.py\n"
        f"      then replace example_lane.py with real lanes -- see docs/product/ADDING_A_GAME_MODULE.md"
    )
    return 0


__all__ = ["PACKAGE_FILES", "example_row", "scaffold"]


if __name__ == "__main__":
    raise SystemExit(main())
