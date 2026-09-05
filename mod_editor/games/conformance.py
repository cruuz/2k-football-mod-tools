"""What CI proves about a game its maintainer has never seen.

The harness is generic: it knows the contract and nothing about any game.  For
each hosted game it checks the declarative half (manifest, registry fragment,
allowlist fragment, pins, validators), the plugin boundary (what the package
imports at module level), the behavioural half on the game's own **synthetic
source** -- identify, catalogue, plan, refuse, build, verify, tamper -- and
that every byte the build changed lies inside a range the build declared.

Nothing here needs a disc, a save or a catalogue the maintainer does not
have: a lane must ship a retail-free synthetic source and a known-good edit on
it, and that is what the harness drives.  The same checks run from
``tests/mod_editor/test_games_conformance.py`` in CI and from
``python -m mod_editor.games.conformance`` on a developer's machine.

Every check is named, every failure carries a sentence, and a failing check
never stops the others: a report lists them all.

Standard library only; importable without Qt.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Callable, Iterable, Optional, Sequence

from .contract import (
    ALLOWED_CORE_IMPORTS,
    PAGE_ORDER,
    SHARED_FORMATS_PACKAGE,
    SURFACE_PAGES,
    Catalogue,
    ContractError,
    Edit,
    GameManifest,
    GameModule,
    Lane,
    Plan,
    Receipt,
    Refusal,
    Verdict,
    lane_page,
)
from .registry_merge import validate_fragment

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Keys and shapes the release gate refuses in shipped metadata; a catalogue
#: built by a lane must not carry them either (mirrors
#: ``packaging/check_2k5_mod_studio_release.py``).
PAYLOAD_KEYS = frozenset({
    "base64", "data_uri", "payload", "payload_base64",
    "raw_bytes", "retail_bytes", "rgba_bytes",
})
_MAX_COMPARE_BYTES = 64 * 1024 * 1024
#: The QApplication the shell check made, if it had to make one.  Qt requires
#: exactly one and requires it to outlive every widget, so it is kept here for
#: the life of the process rather than made and dropped per game.
_APPLICATION: Any = None


@dataclass(frozen=True)
class Check:
    """One named check.  A skipped check passes and says so by name.

    Skipping is for a check that *cannot run here* -- the offscreen shell check
    without PyQt5 -- never for one that could run and was not.  It is printed
    as its own state so a green report never hides a check nobody ran.
    """

    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False

    def line(self) -> str:
        state = "SKIP" if self.skipped else ("PASS" if self.passed else "FAIL")
        return f"{state}  {self.name}" + (f" — {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class ConformanceReport:
    game_id: str
    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def lines(self) -> list[str]:
        return [check.line() for check in self.checks]

    @property
    def skipped(self) -> tuple[Check, ...]:
        return tuple(check for check in self.checks if check.skipped)

    @property
    def summary(self) -> str:
        skipped = len(self.skipped)
        return (
            f"{self.game_id}: {len(self.checks) - len(self.failures) - skipped} of "
            f"{len(self.checks)} conformance checks passed"
            + (f" ({skipped} skipped)" if skipped else "")
        )


class _Collector:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.checks: list[Check] = []

    def record(self, name: str, passed: bool, detail: str = "") -> bool:
        self.checks.append(Check(f"{self.prefix}.{name}", bool(passed), detail))
        return bool(passed)

    def skip(self, name: str, detail: str) -> None:
        """A check that cannot run here; it passes, and the line says SKIP."""

        self.checks.append(Check(f"{self.prefix}.{name}", True, detail, skipped=True))

    def attempt(self, name: str, action: Callable[[], Any], detail: str = "") -> tuple[bool, Any]:
        """Run ``action``; a raised exception is a failed check, not a crash."""

        try:
            value = action()
        except Exception as exc:  # any failure is reported, never propagated
            self.record(name, False, f"{exc.__class__.__name__}: {exc}")
            return False, None
        self.record(name, True, detail)
        return True, value

    def expect_refusal(self, name: str, action: Callable[[], Any]) -> bool:
        try:
            action()
        except Refusal as exc:
            return self.record(name, bool(str(exc).strip()), str(exc))
        except Exception as exc:
            return self.record(
                name, False,
                f"raised {exc.__class__.__name__} instead of Refusal: {exc}",
            )
        return self.record(name, False, "was not refused")


def contains_payload(value: Any) -> bool:
    """True when a document carries byte arrays or data URIs the gate would refuse."""

    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                if str(key).casefold() in PAYLOAD_KEYS and isinstance(item, (str, list)):
                    return True
                pending.append(item)
        elif isinstance(current, (list, tuple)):
            if len(current) > 256 and all(type(item) is int and 0 <= item <= 255 for item in current):
                return True
            pending.extend(current)
        elif isinstance(current, str):
            folded = current.casefold()
            if folded.startswith("data:") or folded.startswith("base64:"):
                return True
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _module_file(name: str, repo_root: Path) -> Optional[Path]:
    """Where a runtime-closure module name resolves in the repository, or None."""

    if name.startswith("mod_editor."):
        relative = Path(*name.split("."))
        for candidate in (relative.with_suffix(".py"), relative / "__init__.py"):
            if (repo_root / candidate).is_file():
                return repo_root / candidate
        return None
    candidate = repo_root / "tools" / f"{name}.py"
    return candidate if candidate.is_file() else None


# --------------------------------------------------------------------------
# Declarative half
# --------------------------------------------------------------------------

def check_manifest(manifest: GameManifest, repo_root: Path = REPO_ROOT) -> list[Check]:
    out = _Collector("manifest")

    def shown(path: Path) -> str:
        try:
            return str(path.relative_to(repo_root))
        except ValueError:  # a games root outside the repository (tests use one)
            return str(path)

    for label, path in (
        ("registry_fragment_exists", manifest.registry_fragment_path),
        ("allowlist_fragment_exists", manifest.allowlist_fragment_path),
        ("pins_exist", manifest.pins_path),
    ):
        out.record(label, path.is_file(), shown(path) if path.is_file() else f"missing: {path}")
    ok, fragment = out.attempt("registry_fragment_reads", manifest.registry_document)
    if ok:
        out.attempt("registry_fragment_valid", lambda: validate_fragment(fragment),
                    f"{len(fragment['capabilities'])} rows on {len(fragment['surfaces'])} surfaces")
        game = fragment["game"]
        expected_keys = {"id", "platform", "public_input", "retail_identity", "title"}
        out.record("registry_fragment_game_entry", set(game) == expected_keys,
                   f"keys: {sorted(game)}")
    ok, lines = out.attempt("allowlist_fragment_reads", manifest.allowlist_lines)
    if ok:
        missing = [line for line in lines if not (repo_root / line).is_file()]
        out.record("allowlist_files_exist", not missing,
                   f"{len(lines)} files" if not missing else f"missing: {missing}")
    out.record(
        "display_fields",
        all(str(getattr(manifest, name, "")).strip() for name in ("console", "game", "year")),
        f"console={manifest.console!r} game={manifest.game!r} year={manifest.year!r}",
    )
    pages = {page_id for page_id, _title in PAGE_ORDER}
    out.record("page_notes_name_pages", set(manifest.page_notes) <= pages,
               f"{len(manifest.page_notes)} page note(s)"
               if set(manifest.page_notes) <= pages
               else f"not pages: {sorted(set(manifest.page_notes) - pages)}")
    ok, pins = out.attempt("pins_read", manifest.pins_document)
    if ok:
        bad = [key for key, value in pins.items()
               if key not in ("schema", "game_id")
               and not isinstance(value, (int, str, list, dict))]
        out.record("pins_are_plain_values", not bad, f"{len(pins) - 2} pins" if not bad else f"bad: {bad}")
    unresolved = [name for name in manifest.product_modules + manifest.tool_modules
                  if _module_file(name, repo_root) is None]
    out.record("runtime_modules_resolve", not unresolved,
               f"{len(manifest.product_modules)} product + {len(manifest.tool_modules)} tool modules"
               if not unresolved else f"unresolved: {unresolved}")
    return out.checks


def _module_level_imports(tree: ast.Module) -> Iterable[tuple[int, str, int]]:
    """``(lineno, dotted name, level)`` for imports a module runs when imported."""

    pending: list[ast.stmt] = list(tree.body)
    while pending:
        node = pending.pop(0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, 0
        elif isinstance(node, ast.ImportFrom):
            yield node.lineno, node.module or "", node.level
        elif isinstance(node, (ast.If, ast.Try)):
            for attribute in ("body", "orelse", "finalbody"):
                pending.extend(getattr(node, attribute, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                pending.extend(handler.body)


def _import_allowed(name: str, level: int, package_name: str) -> bool:
    if level > 0:
        return True  # relative: the game's own package
    if name.startswith("PyQt5") or name == "PyQt5":
        return False  # Qt must stay lazy
    if not (name == "mod_editor" or name.startswith("mod_editor.")):
        return True  # stdlib, tools/, third party: not the core's business
    if name in ALLOWED_CORE_IMPORTS:
        return True
    if name == SHARED_FORMATS_PACKAGE or name.startswith(SHARED_FORMATS_PACKAGE + "."):
        return True
    if name == package_name or name.startswith(package_name + "."):
        return True
    return False


def check_boundary(package_dir: Path, package_name: str) -> list[Check]:
    """A game imports the core only through the contract and shared formats."""

    out = _Collector("boundary")
    offences: list[str] = []
    scanned = 0
    for path in sorted(Path(package_dir).rglob("*.py")):
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            offences.append(f"{path.name}: cannot parse: {exc}")
            continue
        for lineno, name, level in _module_level_imports(tree):
            if not _import_allowed(name, level, package_name):
                offences.append(f"{path.relative_to(package_dir)}:{lineno} imports {name}")
    out.record("module_level_imports_stay_inside_the_contract", not offences and scanned > 0,
               f"{scanned} files scanned" if not offences else "; ".join(offences))
    return out.checks


def check_module(game: GameModule, repo_root: Path = REPO_ROOT) -> list[Check]:
    out = _Collector("module")
    out.record("contract", True, game.contract)
    out.record("identity", True,
               f"{game.identity.title} · {game.identity.platform} · serials {list(game.identity.serials)}")
    out.record("has_a_lane_or_a_window", bool(game.lanes or game.windows),
               f"{len(game.lanes)} lanes, {len(game.windows)} windows")
    try:
        fragment = game.manifest.registry_document()
        rows = {row["id"]: row for row in fragment["capabilities"]}
    except ContractError as exc:
        out.record("registry_fragment_for_lanes", False, str(exc))
        rows = {}
    for lane in game.lanes:
        row = rows.get(lane.capability_id)
        if row is None:
            out.record(f"lane.{lane.lane_id}.registry_row", False,
                       f"no fragment row is called {lane.capability_id!r}")
            continue
        agree = (
            row.get("surface") == lane.surface
            and row.get("classification") == lane.classification
            and row.get("game") == game.game_id
        )
        out.record(f"lane.{lane.lane_id}.registry_row", agree,
                   f"{lane.capability_id}: surface {row.get('surface')}, {row.get('classification')}"
                   if agree else
                   f"row says surface={row.get('surface')!r} classification={row.get('classification')!r} "
                   f"game={row.get('game')!r}; lane says {lane.surface!r}/{lane.classification!r}")
        validation = str(row.get("validation_command") or "")
        named = [token for token in validation.split() if token.startswith("tools/")]
        out.record(f"lane.{lane.lane_id}.validator_declared",
                   bool(lane.validators) and all(token in lane.validators for token in named),
                   f"{list(lane.validators)}")
        missing = [path for path in lane.validators if not (repo_root / path).is_file()]
        out.record(f"lane.{lane.lane_id}.validators_exist", not missing,
                   "" if not missing else f"missing: {missing}")
    window_ids = [window.window_id for window in game.windows]
    out.record("studio_window", game.studio_window in window_ids,
               f"{game.studio_window} — {game.manifest.studio_label}"
               if game.studio_window in window_ids
               else f"studio_window {game.studio_window!r} is not one of {window_ids}")
    out.checks.extend(check_studio_label(game))
    for lane in game.lanes:
        page = lane_page(lane)
        named = isinstance(getattr(lane, "page", None), str) and bool(getattr(lane, "page").strip())
        known = named or lane.surface in SURFACE_PAGES
        out.record(f"lane.{lane.lane_id}.page", page in {p for p, _t in PAGE_ORDER} and known,
                   f"{page} ({'named by the lane' if named else 'from surface ' + lane.surface})"
                   if known else
                   f"surface {lane.surface!r} has no studio page and the lane names none; "
                   "set Lane.page to one of " + ", ".join(p for p, _t in PAGE_ORDER))
    for window in game.windows:
        out.record(f"window.{window.window_id}", callable(window.factory),
                   f"{window.menu_label} (--{window.flag})")
    return out.checks


#: Files of a module the composed studio label may not appear in.  The
#: registry and allowlist fragments are mirrors of canonical files whose prose
#: legitimately names the studio, so the rule is about what the module *writes*:
#: its code and its manifest.
LABEL_SCANNED_SUFFIXES = (".py", ".json")


def check_studio_label(game: GameModule) -> list[Check]:
    """The label is composed from the manifest and never typed out in the module.

    One rule composes every studio's name, so a module that spells its own
    name somewhere will drift the day the rule or the manifest changes -- and
    a second game copying it would inherit the drift.  The mirrors a module
    does not author (``registry.fragment.json``, ``allowlist.fragment.txt``,
    ``pins.json``) are exempt: their prose comes from the canonical registry.
    """

    out = _Collector("module")
    label = game.manifest.studio_label
    root = Path(game.manifest.root)
    exempt = {
        game.manifest.registry_fragment_path.name,
        game.manifest.allowlist_fragment_path.name,
        game.manifest.pins_path.name,
    }
    typed: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in LABEL_SCANNED_SUFFIXES or path.name in exempt:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if label in body:
            typed.append(path.relative_to(root).as_posix())
    out.record("studio_label_is_composed_not_typed", not typed,
               f"{label!r} composed from console/game/year" if not typed
               else f"{label!r} is typed out in " + ", ".join(typed)
                    + "; the core composes it from game.json's console, game and year")
    return out.checks


def check_shell(game: GameModule) -> list[Check]:
    """The core shell hosts this module: it opens, and it shows every page.

    Offscreen and read-only -- nothing is opened but the window.  Without
    PyQt5 the check cannot run and says so by name rather than passing quietly.
    """

    out = _Collector("shell")
    try:
        from PyQt5.QtWidgets import QApplication

        from .studio_qt import GameStudioDialog
    except ImportError as exc:
        out.skip("studio_opens", f"PyQt5 is not installed here ({exc}); the shell was not drawn")
        return out.checks
    import os

    global _APPLICATION
    if QApplication.instance() is None:
        # A conformance run must never need a display: without one Qt aborts
        # the process instead of raising, so offscreen is chosen before the
        # application exists (an explicit QT_QPA_PLATFORM still wins).
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _APPLICATION = QApplication([])
    dialog = None
    try:
        dialog = GameStudioDialog(game)
        out.record("studio_opens", dialog.windowTitle() == game.manifest.studio_label,
                   f"window title {dialog.windowTitle()!r}")
        expected = tuple(page_id for page_id, _title in PAGE_ORDER)
        missing = [page_id for page_id in expected if dialog.page_widget(page_id) is None]
        out.record("studio_shows_every_page",
                   dialog.page_ids() == expected and not missing,
                   f"{len(expected)} pages, in the studio's order" if not missing
                   else f"pages without a panel: {missing}")
        placed = {lane.lane_id for page_id in expected for lane in dialog.lanes_for_page(page_id)}
        out.record("studio_places_every_lane",
                   placed == {lane.lane_id for lane in game.lanes},
                   f"{len(placed)} of {len(game.lanes)} lanes on a page")
    except Exception as exc:  # a shell that cannot draw this module is a failure, not a crash
        out.record("studio_opens", False, f"{exc.__class__.__name__}: {exc}")
    finally:
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
    return out.checks


# --------------------------------------------------------------------------
# Behavioural half, on the lane's own synthetic source
# --------------------------------------------------------------------------

def _outside(ranges: Sequence[tuple[int, int]], offset: int) -> bool:
    return not any(start <= offset < start + length for start, length in ranges)


def _changed_offsets(source: Path, destination: Path) -> Optional[set[int]]:
    if source.stat().st_size != destination.stat().st_size:
        return None
    if source.stat().st_size > _MAX_COMPARE_BYTES:
        return None
    left = source.read_bytes()
    right = destination.read_bytes()
    return {index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]}


def check_lane_behaviour(game: GameModule, lane: Lane, work_dir: Path) -> list[Check]:
    out = _Collector(f"lane.{lane.lane_id}")
    room = Path(work_dir) / lane.lane_id.replace("/", "_")
    room.mkdir(parents=True, exist_ok=True)

    ok, source = out.attempt("synthetic_source", lambda: lane.synthetic_source(room))
    if not ok:
        return out.checks
    source = Path(source)
    if not out.record("synthetic_source_is_a_file", source.is_file(), str(source.name)):
        return out.checks
    source_before = _sha256(source)

    ok, identity = out.attempt("identify", lambda: game.identifier.identify(source))
    if ok:
        out.record("identify_serial", identity.serial_matches or not game.identity.serials,
                   identity.headline)
        out.record("identify_synthetic_is_not_retail", not identity.retail_executable,
                   "a synthetic source must never pass as retail")

    ok, catalogue = out.attempt("build_catalogue", lambda: lane.build_catalogue(source))
    if not ok:
        return out.checks
    out.record("catalogue_has_targets", bool(catalogue.targets),
               f"{len(catalogue.targets)} targets, schema {catalogue.schema}")
    out.record("catalogue_is_retail_free", not contains_payload(dict(catalogue.document)),
               "no payload keys, byte arrays or data URIs")

    ok, edits = out.attempt("conformance_edits", lambda: tuple(lane.conformance_edits(catalogue)))
    if not ok or not out.record("conformance_edits_nonempty", bool(edits), f"{len(edits)} edits"):
        return out.checks
    inline = []
    for edit in edits:
        try:
            target = catalogue.target(edit.target_key)
        except Refusal as exc:
            inline.append(str(exc))
            continue
        problem = lane.check_edit(target, edit.values)
        if problem:
            inline.append(problem)
    out.record("check_edit_accepts_conformance_edits", not inline, "; ".join(inline))

    ok, recipe = out.attempt("compose_recipe", lambda: lane.compose_recipe(edits))
    if not ok:
        return out.checks
    out.record("recipe_carries_schema", recipe.get("schema") == lane.recipe_schema,
               str(recipe.get("schema")))

    ok, plan = out.attempt("plan", lambda: lane.plan(source, recipe, catalogue))
    if ok:
        out.record("plan_is_a_plan", isinstance(plan, Plan),
                   f"{len(plan.target_keys)} targets, {plan.declared_bytes} declared bytes"
                   if isinstance(plan, Plan) else repr(plan))
        out.record("plan_names_the_edits",
                   isinstance(plan, Plan) and set(plan.target_keys) == {edit.target_key for edit in edits},
                   "")
        if lane.fixed_allocation and isinstance(plan, Plan):
            out.record("plan_declares_ranges", bool(plan.declared_ranges), "")
    out.record("plan_wrote_nothing", _sha256(source) == source_before, "source unchanged by planning")

    bogus = lane.compose_recipe((Edit("no-such-target-zz", edits[0].values),))
    out.expect_refusal("plan_refuses_unknown_target", lambda: lane.plan(source, bogus, catalogue))

    destination = room / "built.out"
    ok, receipt = out.attempt(
        "build", lambda: lane.build(source, destination, recipe, catalogue, work_dir=room)
    )
    if not ok:
        return out.checks
    out.record("build_is_a_receipt", isinstance(receipt, Receipt), receipt.schema if isinstance(receipt, Receipt) else "")
    out.record("build_created_destination", destination.is_file(), str(destination.name))
    out.record("build_left_source_unchanged", _sha256(source) == source_before, "source byte-identical")
    if lane.fixed_allocation:
        out.record("build_kept_size", destination.stat().st_size == source.stat().st_size,
                   f"{destination.stat().st_size:,} bytes")
    ranges = [(item.start, item.length) for item in receipt.declared_ranges]
    out.record("receipt_declares_ranges_or_artifacts", bool(ranges) or bool(receipt.artifacts),
               f"{len(ranges)} ranges, {len(receipt.artifacts)} artifacts")
    size = destination.stat().st_size
    if ranges:
        out.record("declared_ranges_inside_destination",
                   all(0 <= start and start + length <= size for start, length in ranges), "")
    if receipt.artifacts:
        stale = [item.path for item in receipt.artifacts
                 if not Path(item.path).is_file() or _sha256(Path(item.path)) != item.sha256]
        out.record("artifacts_match_their_digests", not stale, "" if not stale else f"stale: {stale}")
    changed = _changed_offsets(source, destination)
    if changed is not None:
        stray = sorted(offset for offset in changed if _outside(ranges, offset))
        out.record("every_changed_byte_is_declared", bool(changed) and not stray,
                   f"{len(changed)} bytes changed, all declared" if not stray
                   else f"{len(stray)} undeclared changed bytes, first at 0x{stray[0]:x}")
    destination_digest = _sha256(destination)

    ok, verdict = out.attempt("verify", lambda: lane.verify(source, destination, receipt))
    if ok:
        out.record("verify_passes", isinstance(verdict, Verdict) and verdict.passed,
                   verdict.summary if isinstance(verdict, Verdict) else repr(verdict))

    out.expect_refusal(
        "build_refuses_existing_destination",
        lambda: lane.build(source, destination, recipe, catalogue, work_dir=room),
    )
    out.record("refusal_left_destination_intact", _sha256(destination) == destination_digest, "")
    out.expect_refusal(
        "build_refuses_source_as_destination",
        lambda: lane.build(source, source, recipe, catalogue, work_dir=room),
    )
    out.record("refusal_left_source_intact", _sha256(source) == source_before, "")

    tampered = room / "tampered.out"
    shutil.copyfile(destination, tampered)
    offset = size - 1
    while offset >= 0 and not _outside(ranges, offset):
        offset -= 1
    if offset >= 0:
        with open(tampered, "r+b") as handle:
            handle.seek(offset)
            byte = handle.read(1)
            handle.seek(offset)
            handle.write(bytes([byte[0] ^ 0xFF]))
        try:
            tampered_verdict = lane.verify(source, tampered, receipt)
            failed = not tampered_verdict.passed
            detail = tampered_verdict.summary
        except Refusal as exc:
            failed, detail = True, str(exc)
        except Exception as exc:
            failed, detail = False, f"raised {exc.__class__.__name__}: {exc}"
        out.record("verify_fails_on_undeclared_change", failed,
                   f"byte 0x{offset:x} flipped: {detail}")
    return out.checks


def run(
    game: GameModule,
    work_dir: Path,
    repo_root: Path = REPO_ROOT,
    *,
    behavioural: bool = True,
) -> ConformanceReport:
    checks: list[Check] = []
    checks.extend(check_manifest(game.manifest, repo_root))
    checks.extend(check_boundary(game.manifest.root, game.package))
    checks.extend(check_module(game, repo_root))
    checks.extend(check_shell(game))
    if behavioural:
        for lane in game.lanes:
            checks.extend(check_lane_behaviour(game, lane, Path(work_dir)))
    return ConformanceReport(game.game_id, tuple(checks))


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    import tempfile

    from . import discover

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", help="one game id (default: every hosted game)")
    parser.add_argument("--work-dir", type=Path, help="where synthetic sources are built")
    parser.add_argument("--static-only", action="store_true", help="skip the behavioural half")
    parser.add_argument("--games-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    report = discover(args.games_root)
    failed = False
    for item in report.refused:
        print(f"REFUSED {item.directory}: {item.reason}")
        failed = True
    games = [game for game in report.games if args.game in (None, game.game_id)]
    if args.game and not games:
        print(f"no hosted game is called {args.game!r}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="game-conformance-") as fallback:
        work = args.work_dir or Path(fallback)
        for game in games:
            result = run(game, work, behavioural=not args.static_only)
            for line in result.lines():
                print(line)
            print(result.summary)
            failed = failed or not result.passed
    return 1 if failed else 0


__all__ = [
    "Check",
    "ConformanceReport",
    "LABEL_SCANNED_SUFFIXES",
    "PAYLOAD_KEYS",
    "REPO_ROOT",
    "check_boundary",
    "check_lane_behaviour",
    "check_manifest",
    "check_module",
    "check_shell",
    "check_studio_label",
    "contains_payload",
    "run",
]


if __name__ == "__main__":
    raise SystemExit(main())
