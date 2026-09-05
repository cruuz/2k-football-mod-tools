"""What the game studio shell does when nobody is looking: lanes, plans, builds.

Core-owned, game-blind and Qt-free.  :class:`GameStudioService` is to
:class:`~mod_editor.games.studio_qt.GameStudioDialog` what
``ps2_disc_studio_service`` is to the hand-written PS2 window -- the same
service, generalised from one game's six lanes to *any* module's contract
lanes.  Everything the window would otherwise decide lives here, so the whole
of it is provable without a display:

* opening a source read-only and saying what it is (the module's own
  :class:`~mod_editor.games.contract.SourceIdentifier`);
* building a lane's catalogue, cached on this machine and keyed by the
  source's size and name, so a second visit to a page is instant;
* staging edits, asking the lane whether each one fits, composing the lane's
  own recipe and previewing it;
* the dry run, the free-space check, and the chained build: one step per lane,
  each writing a new file from the previous step's output and verified before
  the previous intermediate is deleted;
* one receipt naming every step, every verdict and every digest.

**Every step that touches a lane runs in a child process** through
``python -m mod_editor.games lane`` (:mod:`mod_editor.games.lane_cli`).  A lane
that raises takes the child down and not the window, a build that runs for
tens of minutes is cancellable by killing it, and the exact command the studio
ran is a command the user can run themselves.  That is the same bargain the
PS2 studio's worker made; this one speaks the contract instead of one game.

Three refusals are the service's own and not a lane's, because they are true
before any lane is asked: the destination must not already exist, it must not
be the source, and its volume must have room for the new file plus one
intermediate plus the staging reserve.  Everything else is the lane's own
sentence, surfaced verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from mod_editor.core import platform_compat

from . import DiscoveryReport
from .contract import (
    Catalogue,
    ContractError,
    Edit,
    GameModule,
    Plan,
    SourceIdentity,
    Target,
    Verdict,
)
from .lane_cli import catalogue_from_json, receipt_from_json

ROOT = Path(__file__).resolve().parents[2]

RECEIPT_SCHEMA = "vc_game_studio_receipt/v1"
RECEIPT_SUFFIX = ".game-studio-receipt.v1.json"
CATALOGUE_SUFFIX = ".catalogue.v1.json"

#: Room a build wants beyond the new file and one intermediate: a lane stages
#: a rewritten pack while it works.  The PS2 studio settled on this figure by
#: measurement and it is the one number the shell keeps from it.
STAGING_RESERVE = int(1.25 * (1 << 30))
GIB = float(1 << 30)

#: The default scope every lane has.  A lane that offers more says so with a
#: ``scopes()`` method returning objects with ``id``/``label``/``note``; the
#: contract does not require one, so the shell asks and falls back to this.
DEFAULT_SCOPE = "default"


class StudioError(ContractError):
    """Something the studio itself refuses, in one sentence."""


class Cancelled(StudioError):
    """The user cancelled; nothing the operation created was kept."""


class CancelToken:
    """Set by Cancel, read by the loop that is waiting on a child process."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self, what: str = "The operation") -> None:
        if self._cancelled:
            raise Cancelled(f"{what} was cancelled; nothing it created was kept.")


Progress = Optional[Callable[[str], None]]


# --------------------------------------------------------------------------
# Small value types the window draws
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Scope:
    """How much of a lane one catalogue covers."""

    id: str
    label: str
    note: str = ""


DEFAULT_SCOPES = (Scope(DEFAULT_SCOPE, "The whole lane", ""),)


def lane_scopes(lane: Any) -> Tuple[Scope, ...]:
    """A lane's catalogue scopes, or the single default.

    ``scopes`` is deliberately not a member of the :class:`Lane` protocol: it
    would refuse every lane written before the shell existed.  A lane that has
    more than one offers them; the shell shows a picker only then.
    """

    raw = getattr(lane, "scopes", None)
    items: Iterable[Any] = ()
    if callable(raw):
        try:
            items = raw() or ()
        except Exception:  # a lane that cannot describe its scopes has one
            return DEFAULT_SCOPES
    elif raw:
        items = raw
    out = []
    for item in items:
        identifier = str(getattr(item, "id", getattr(item, "scope_id", "")) or "").strip()
        if not identifier:
            continue
        out.append(Scope(identifier,
                         str(getattr(item, "label", identifier)),
                         str(getattr(item, "note", ""))))
    return tuple(out) or DEFAULT_SCOPES


@dataclass(frozen=True)
class CatalogueState:
    """Whether a lane's catalogue exists for the open source, and what it says."""

    lane_id: str
    scope: str
    built: bool
    targets: int = 0
    summary: str = ""
    seconds: Optional[float] = None

    @property
    def headline(self) -> str:
        if not self.built:
            return "catalogue not built for this source yet"
        took = f" (built in {self.seconds:.0f} s)" if self.seconds else ""
        return f"{self.targets:,} target{'' if self.targets == 1 else 's'}{took}"


@dataclass(frozen=True)
class BuildEstimate:
    """Free space, said before a build starts rather than half way through."""

    source_bytes: int
    steps: int
    needed_bytes: int
    available_bytes: int
    volume: str

    @property
    def fits(self) -> bool:
        return self.available_bytes >= self.needed_bytes

    @property
    def sentence(self) -> str:
        text = (
            f"Needs about {_gib(self.needed_bytes)} free on {self.volume}: a "
            f"{_gib(self.source_bytes)} new file, room for one {_gib(self.source_bytes)} "
            f"intermediate while it is verified, and {_gib(STAGING_RESERVE)} for the "
            f"staged work; {_gib(self.available_bytes)} is free."
        )
        if not self.fits:
            text += " Free some space or choose a destination on another drive."
        return text


@dataclass(frozen=True)
class StepResult:
    """One build step, as the receipt records it."""

    lane_id: str
    index: int
    title: str
    input_name: str
    output_name: str
    declared_ranges: int
    declared_bytes: int
    artifacts: Tuple[str, ...]
    verdict_passed: bool
    verdict_summary: str
    seconds: float
    output_size: int
    output_sha256: str
    receipt_document: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildReceipt:
    """What a whole queue did: the new file, every step, every verdict."""

    destination: Path
    receipt_path: Path
    steps: Tuple[StepResult, ...]
    seconds: float
    source_sha256: str
    destination_sha256: str
    exports: Tuple[Path, ...] = ()
    document: Mapping[str, Any] = field(default_factory=dict)

    @property
    def all_verified(self) -> bool:
        return all(step.verdict_passed for step in self.steps)

    @property
    def message(self) -> str:
        lanes = ", ".join(step.title for step in self.steps)
        verdict = ("every verifier passed" if self.all_verified
                   else "a verifier did NOT pass; do not use what was written")
        count = len(self.steps)
        return (f"Wrote {self.destination.name} ({lanes}; {count} step{'' if count == 1 else 's'}, "
                f"{self.seconds / 60:.1f} min) — {verdict}. Your source was not changed.")


@dataclass(frozen=True)
class StudioActionState:
    """Headless control gating, shared by the window and its tests."""

    can_open: bool
    can_build_catalogue: bool
    can_edit: bool
    can_check: bool
    can_build: bool
    can_cancel: bool
    can_open_folder: bool


def studio_action_state(
    *, source_open: bool, busy: bool, catalogue_built: bool, staged_count: int,
    plans_ready: bool, built: bool,
) -> StudioActionState:
    """Compute gating without consulting a widget.

    Build waits for a clean dry run on every staged lane: the plan is where a
    patcher's refusals surface, so a build is never offered before it has been
    done for the recipe as it now stands.
    """

    live = source_open and not busy
    return StudioActionState(
        can_open=not busy,
        can_build_catalogue=live,
        can_edit=bool(live and catalogue_built),
        can_check=bool(live and staged_count > 0),
        can_build=bool(live and staged_count > 0 and plans_ready),
        can_cancel=busy,
        can_open_folder=bool(built and not busy),
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _gib(value: int) -> str:
    return f"{value / GIB:.2f} GiB"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_bytes(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def default_cache_root() -> Path:
    """Where catalogues are kept between sessions, per user and never in the repo."""

    return platform_compat.user_private_root() / "2k5-mod-studio" / "game-studio"


def open_filter(module: GameModule) -> str:
    """The file dialog's filter, composed from the module's accepted suffixes."""

    suffixes = tuple(getattr(module.identifier, "accepted_suffixes", ()) or ())
    if not suffixes:
        return "All files (*)"
    patterns = " ".join(f"*{suffix}" for suffix in suffixes)
    return f"{module.manifest.title} sources ({patterns});;All files (*)"


def suggested_destination(source_name: str) -> str:
    """A default name for the destination: never the source's own name."""

    path = Path(str(source_name).strip())
    stem = path.stem or "modded"
    return f"{stem}-modded{path.suffix or '.out'}"


def is_read_only(lane: Any) -> bool:
    """Whether a lane only catalogues -- the contract's ``read_only`` marker."""

    return bool(getattr(lane, "read_only", False))


def writes_files(lane: Any) -> bool:
    """Whether a lane's build produces files rather than a same-size copy.

    A fixed-allocation lane rewrites its source into a new file of the same
    length and the shell chains those; an export lane publishes a folder and
    cannot be chained into the next step's input, so the build page runs it on
    its own from the original source.
    """

    return not bool(getattr(lane, "fixed_allocation", True))


# --------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------

class GameStudioService:
    """Open one module's source read-only and drive its contract lanes over it."""

    def __init__(
        self,
        module: GameModule,
        *,
        cache_root: Optional[Path] = None,
        python: Optional[str] = None,
        poll_seconds: float = 0.2,
        games_root: Optional[Path] = None,
    ) -> None:
        self.module = module
        self._cache_root = Path(cache_root).resolve() if cache_root is not None else default_cache_root()
        self._python = python or sys.executable
        self._poll = max(0.02, float(poll_seconds))
        self._games_root = Path(games_root).resolve() if games_root else None
        self._source: Optional[Path] = None
        self._identity: Optional[SourceIdentity] = None
        self._catalogues: Dict[Tuple[str, str], Catalogue] = {}
        self._states: Dict[Tuple[str, str], CatalogueState] = {}

    # -- identity ------------------------------------------------------

    @property
    def open_filter(self) -> str:
        return open_filter(self.module)

    @property
    def is_open(self) -> bool:
        return self._source is not None

    @property
    def source_path(self) -> Optional[Path]:
        return self._source

    def identity(self) -> SourceIdentity:
        if self._identity is None:
            raise StudioError("No source is open yet; choose one with Open…")
        return self._identity

    def _require_open(self) -> Tuple[Path, SourceIdentity]:
        if self._source is None or self._identity is None:
            raise StudioError("No source is open yet; choose one with Open…")
        return self._source, self._identity

    def open(self, path: Path, progress: Progress = None) -> SourceIdentity:
        """Identify the user's own file, read-only.  Every failure is one sentence."""

        candidate = Path(path).expanduser()
        if not candidate.is_file():
            raise StudioError(f"{candidate} is not a file this studio can open.")
        say = progress or (lambda _line: None)
        say(f"Reading {candidate.name}…")
        try:
            identity = self.module.identifier.identify(candidate)
        except ContractError:
            raise
        except (OSError, ValueError) as exc:
            raise StudioError(
                f"{candidate.name} could not be identified: {exc}. Nothing was changed."
            ) from exc
        self._source = candidate
        self._identity = identity
        self._catalogues.clear()
        self._states.clear()
        self._load_cached_states()
        return identity

    def close(self) -> None:
        self._source = None
        self._identity = None
        self._catalogues.clear()
        self._states.clear()

    # -- catalogues ----------------------------------------------------

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    def cache_dir(self) -> Path:
        """One directory per (game, source): name and size are enough to key it.

        Digesting a 4 GiB image to name its cache would cost a minute before
        anything is shown; the size and the name change together in practice,
        and a stale catalogue is caught by the lane's own pinning at plan time.
        """

        source, identity = self._require_open()
        key = f"{self.module.game_id}|{source.name}|{identity.size_bytes}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        directory = self._cache_root / self.module.game_id / digest
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def catalogue_path(self, lane_id: str, scope: str = DEFAULT_SCOPE) -> Path:
        safe = f"{lane_id}.{scope}".replace("/", "_").replace(os.sep, "_")
        return self.cache_dir() / (safe + CATALOGUE_SUFFIX)

    def _load_cached_states(self) -> None:
        if self._source is None:
            return
        for lane in self.module.lanes:
            for scope in lane_scopes(lane):
                path = self.catalogue_path(lane.lane_id, scope.id)
                if path.is_file():
                    try:
                        catalogue = catalogue_from_json(json.loads(path.read_text(encoding="utf-8")))
                    except (OSError, ValueError, ContractError):
                        continue
                    self._catalogues[(lane.lane_id, scope.id)] = catalogue
                    self._states[(lane.lane_id, scope.id)] = CatalogueState(
                        lane.lane_id, scope.id, True, len(catalogue.targets),
                        f"{len(catalogue.targets):,} targets from a cached catalogue",
                    )

    def catalogue_state(self, lane_id: str, scope: str = DEFAULT_SCOPE) -> CatalogueState:
        return self._states.get((lane_id, scope), CatalogueState(lane_id, scope, False))

    def catalogue(self, lane_id: str, scope: str = DEFAULT_SCOPE) -> Catalogue:
        try:
            return self._catalogues[(lane_id, scope)]
        except KeyError:
            raise StudioError(
                f"The {self.module.lane(lane_id).title} catalogue has not been built for this "
                "source yet; choose Build catalogue."
            ) from None

    def build_catalogue(
        self, lane_id: str, scope: str = DEFAULT_SCOPE,
        progress: Progress = None, cancel: Optional[CancelToken] = None,
    ) -> CatalogueState:
        """Run the lane's catalogue step in a child process and cache what it wrote."""

        source, _identity = self._require_open()
        lane = self.module.lane(lane_id)
        out = self.catalogue_path(lane_id, scope)
        temporary = out.with_name(out.name + ".part")
        temporary.unlink(missing_ok=True)
        started = time.monotonic()
        self._run_lane(
            lane_id, "catalogue",
            ["--source", str(source), "--out", str(temporary)],
            scope=scope, progress=progress, cancel=cancel,
            describe=f"Building the {lane.title} catalogue",
        )
        try:
            document = json.loads(temporary.read_text(encoding="utf-8"))
            catalogue = catalogue_from_json(document)
        except (OSError, ValueError, ContractError) as exc:
            temporary.unlink(missing_ok=True)
            raise StudioError(
                f"The {lane.title} catalogue could not be read back: {exc}. Nothing was changed."
            ) from exc
        os.replace(temporary, out)
        seconds = time.monotonic() - started
        self._catalogues[(lane_id, scope)] = catalogue
        state = CatalogueState(
            lane_id, scope, True, len(catalogue.targets),
            f"{len(catalogue.targets):,} target{'' if len(catalogue.targets) == 1 else 's'} "
            f"read from {Path(source).name}",
            seconds,
        )
        self._states[(lane_id, scope)] = state
        return state

    def forget_catalogue(self, lane_id: str, scope: str = DEFAULT_SCOPE) -> None:
        self._catalogues.pop((lane_id, scope), None)
        self._states.pop((lane_id, scope), None)
        if self._source is not None:
            self.catalogue_path(lane_id, scope).unlink(missing_ok=True)

    def targets(self, lane_id: str, scope: str = DEFAULT_SCOPE) -> Tuple[Target, ...]:
        return self.catalogue(lane_id, scope).targets

    def target(self, lane_id: str, key: str, scope: str = DEFAULT_SCOPE) -> Target:
        return self.catalogue(lane_id, scope).target(key)

    # -- editing -------------------------------------------------------

    def check_edit(self, lane_id: str, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """The lane's inline refusal for one proposed edit, verbatim, or None."""

        lane = self.module.lane(lane_id)
        if is_read_only(lane):
            return f"{lane.title} only catalogues what is on your source; it never edits it."
        try:
            return lane.check_edit(target, dict(values))
        except ContractError as exc:
            return str(exc)
        except Exception as exc:  # a lane that raised past its own refusals
            return f"{lane.title} could not check that edit: {exc}"

    def stage(self, lane_id: str, target: Target, values: Mapping[str, Any], note: str = "") -> Edit:
        """Turn a checked editor state into a staged :class:`Edit`, or refuse."""

        problem = self.check_edit(lane_id, target, values)
        if problem:
            raise StudioError(problem)
        return Edit(target.key, dict(values), note)

    def compose(self, lane_id: str, edits: Sequence[Edit]) -> Mapping[str, Any]:
        lane = self.module.lane(lane_id)
        try:
            return lane.compose_recipe(tuple(edits))
        except ContractError:
            raise
        except Exception as exc:
            raise StudioError(f"The {lane.title} recipe could not be composed: {exc}") from exc

    @staticmethod
    def recipe_preview(recipe: Mapping[str, Any]) -> str:
        """The exact document the lane's own patcher will be handed."""

        try:
            return json.dumps(dict(recipe), indent=2, sort_keys=True)
        except (TypeError, ValueError) as exc:  # pragma: no cover - a lane's own values
            return f"The recipe cannot be shown as JSON yet: {exc}"

    def plan_lane(
        self, lane_id: str, edits: Sequence[Edit], scope: str = DEFAULT_SCOPE,
        progress: Progress = None, cancel: Optional[CancelToken] = None,
    ) -> Plan:
        """One lane's dry run against the open source, in a child process."""

        source, _identity = self._require_open()
        lane = self.module.lane(lane_id)
        recipe = self.compose(lane_id, edits)
        with self._scratch("plan") as room:
            recipe_path = room / "recipe.json"
            recipe_path.write_text(json.dumps(dict(recipe), indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8", newline="\n")
            out = room / "plan.json"
            self._run_lane(
                lane_id, "plan",
                ["--source", str(source), "--recipe", str(recipe_path),
                 "--catalogue", str(self.catalogue_path(lane_id, scope)), "--out", str(out)],
                scope=scope, progress=progress, cancel=cancel,
                describe=f"Checking the {lane.title} recipe",
            )
            document = json.loads(out.read_text(encoding="utf-8"))
        return Plan(
            lane_id=str(document.get("lane_id", lane_id)),
            target_keys=tuple(str(key) for key in document.get("target_keys", ())),
            declared_ranges=(),
            document=dict(document.get("document", {}) or {}),
        )

    # -- the build -----------------------------------------------------

    def check_destination(self, destination: Path) -> Path:
        """The three refusals that need no lane: exists, is the source, has no folder."""

        source, _identity = self._require_open()
        requested = Path(destination).expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        requested = Path(os.path.abspath(os.fspath(requested)))
        # The source is checked first: it exists, so the general "already
        # there" sentence would be true and unhelpful.  Naming what the file
        # actually is says what to do.
        if requested.resolve(strict=False) == source.resolve():
            raise StudioError(
                "The destination must not be the source you opened; a build writes a NEW file "
                "and never the one you chose."
            )
        if os.path.lexists(requested):
            raise StudioError(
                f"A file already exists there: {requested}. Choose a name that does not exist "
                "yet; what you opened is never overwritten."
            )
        parent = requested.parent
        if not parent.is_dir() or parent.is_symlink():
            raise StudioError(f"The destination's folder is missing or is a link: {parent}")
        receipt = parent / (requested.name + RECEIPT_SUFFIX)
        if os.path.lexists(receipt):
            raise StudioError(f"A receipt already exists there: {receipt}. Choose another name.")
        return requested

    def estimate(self, steps: int, destination: Path) -> BuildEstimate:
        """Free space on the destination's volume, against the file plus one intermediate."""

        _source, identity = self._require_open()
        parent = Path(destination).expanduser().parent
        if not parent.is_absolute():
            parent = Path.cwd() / parent
        probe = parent
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        try:
            available = platform_compat.available_bytes(probe)
        except OSError:
            available = 0
        needed = identity.size_bytes * 2 + STAGING_RESERVE
        return BuildEstimate(identity.size_bytes, max(1, steps), needed, int(available),
                             str(probe.anchor or probe))

    def build(
        self,
        staged: Mapping[str, Sequence[Edit]],
        destination: Path,
        progress: Progress = None,
        cancel: Optional[CancelToken] = None,
        scopes: Optional[Mapping[str, str]] = None,
    ) -> BuildReceipt:
        """Run every staged lane as one step, chained, into a NEW file.

        Fixed-allocation lanes chain: step *n* reads step *n-1*'s output and is
        verified before that intermediate is deleted, so a failure anywhere
        leaves nothing half-written.  A lane that publishes files instead --
        an export -- cannot be an input to the next step, so it is run once
        from the original source into its own folder beside the destination.
        """

        source, identity = self._require_open()
        scopes = dict(scopes or {})
        chain = [(lane_id, tuple(edits)) for lane_id, edits in self._ordered(staged)
                 if not writes_files(self.module.lane(lane_id))]
        exports = [(lane_id, tuple(edits)) for lane_id, edits in self._ordered(staged)
                   if writes_files(self.module.lane(lane_id))]
        if not chain and not exports:
            raise StudioError("Stage and check at least one edit before building.")
        requested = self.check_destination(destination)
        if chain:
            estimate = self.estimate(len(chain), requested)
            if not estimate.fits:
                raise StudioError(estimate.sentence)

        started = time.monotonic()
        results: List[StepResult] = []
        intermediates: List[Path] = []
        created: List[Path] = []
        export_paths: List[Path] = []
        current_input = source
        source_sha256 = ""
        try:
            for index, (lane_id, edits) in enumerate(chain):
                lane = self.module.lane(lane_id)
                last = index == len(chain) - 1
                output = requested if last else requested.parent / f".{requested.name}.step{index + 1}"
                if os.path.lexists(output):
                    raise StudioError(
                        f"A file already exists where an intermediate would go: {output}"
                    )
                if cancel is not None:
                    cancel.raise_if_cancelled("The build")
                if index == 0:
                    source_sha256 = _sha256_file(source)
                result = self._build_step(
                    lane_id, edits, current_input, output,
                    scopes.get(lane_id, DEFAULT_SCOPE),
                    index + 1, len(chain), progress, cancel,
                )
                created.append(output)
                results.append(result)
                if not result.verdict_passed:
                    raise StudioError(
                        f"The {lane.title} verifier did not pass on step {index + 1}: "
                        f"{result.verdict_summary}. The part-written file has been removed."
                    )
                if current_input in intermediates:
                    current_input.unlink(missing_ok=True)
                    intermediates.remove(current_input)
                if not last:
                    intermediates.append(output)
                current_input = output
            for lane_id, edits in exports:
                if cancel is not None:
                    cancel.raise_if_cancelled("The build")
                folder = requested.parent / f"{requested.name}-{lane_id.replace('.', '-')}"
                if os.path.lexists(folder):
                    raise StudioError(
                        f"A folder already exists where the export would go: {folder}. "
                        "Choose another destination name."
                    )
                result = self._build_step(
                    lane_id, edits, source, folder, scopes.get(lane_id, DEFAULT_SCOPE),
                    len(results) + 1, len(chain) + len(exports), progress, cancel,
                )
                created.append(folder)
                export_paths.append(folder)
                results.append(result)
        except BaseException:
            for path in dict.fromkeys(intermediates + created):
                if path != source and os.path.lexists(path):
                    if Path(path).is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        Path(path).unlink(missing_ok=True)
            raise

        seconds = time.monotonic() - started
        final = results[-1] if results else None
        document = {
            "schema": RECEIPT_SCHEMA,
            "generated": _now(),
            "game": self.module.game_id,
            "studio": self.module.manifest.studio_label,
            "module_version": self.module.version,
            "source": {"name": Path(source).name, "size": identity.size_bytes,
                       "sha256": source_sha256, "serial": identity.serial,
                       "headline": identity.headline},
            "destination": {"path": str(requested),
                            "size": final.output_size if final else 0,
                            "sha256": final.output_sha256 if final else ""},
            "steps": [{
                "step": item.index, "lane": item.lane_id, "title": item.title,
                "input": item.input_name, "output": item.output_name,
                "declared_ranges": item.declared_ranges,
                "declared_bytes": item.declared_bytes,
                "artifacts": list(item.artifacts),
                "verdict": {"passed": item.verdict_passed, "summary": item.verdict_summary},
                "seconds": round(item.seconds, 2),
                "output_sha256": item.output_sha256,
                "receipt": dict(item.receipt_document),
            } for item in results],
            "exports": [str(path) for path in export_paths],
            "seconds_total": round(seconds, 1),
            "claims": {
                "source_opened_read_only": True,
                "destination_created_exclusively": True,
                "every_step_independently_verified": all(item.verdict_passed for item in results),
                "runtime_visibility_proved": False,
                "runtime_audibility_proved": False,
            },
        }
        receipt_path = requested.parent / (requested.name + RECEIPT_SUFFIX)
        with open(receipt_path, "xb") as stream:
            stream.write(_json_bytes(document))
        return BuildReceipt(
            requested, receipt_path, tuple(results), seconds, source_sha256,
            final.output_sha256 if final else "", tuple(export_paths), document,
        )

    def _ordered(self, staged: Mapping[str, Sequence[Edit]]) -> List[Tuple[str, Sequence[Edit]]]:
        """Staged lanes in the module's own lane order: one fixed queue, never a race."""

        order = {lane.lane_id: index for index, lane in enumerate(self.module.lanes)}
        rows = [(lane_id, edits) for lane_id, edits in staged.items() if edits]
        rows.sort(key=lambda item: order.get(item[0], len(order)))
        return rows

    def _build_step(
        self, lane_id: str, edits: Sequence[Edit], source: Path, output: Path,
        scope: str, index: int, steps: int, progress: Progress, cancel: Optional[CancelToken],
    ) -> StepResult:
        """Write one step and verify it, both in their own child processes."""

        lane = self.module.lane(lane_id)
        recipe = self.compose(lane_id, edits)
        prefix = f"Step {index} of {steps} · {lane.title}: "
        started = time.monotonic()
        with self._scratch(f"step{index}", near=output.parent) as room:
            recipe_path = room / "recipe.json"
            recipe_path.write_text(json.dumps(dict(recipe), indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8", newline="\n")
            receipt_path = room / "receipt.json"
            self._run_lane(
                lane_id, "build",
                ["--source", str(source), "--destination", str(output),
                 "--recipe", str(recipe_path),
                 "--catalogue", str(self.catalogue_path(lane_id, scope)),
                 "--work-dir", str(room), "--receipt", str(receipt_path)],
                scope=scope, progress=progress, cancel=cancel,
                describe=f"{prefix}writing",
                on_failure=lambda: _remove(output),
            )
            try:
                receipt = receipt_from_json(json.loads(receipt_path.read_text(encoding="utf-8")))
            except (OSError, ValueError, ContractError) as exc:
                _remove(output)
                raise StudioError(
                    f"{lane.title} wrote a receipt this studio cannot read: {exc}. "
                    "What it created has been removed."
                ) from exc
            verdict_path = room / "verdict.json"
            try:
                self._run_lane(
                    lane_id, "verify",
                    ["--source", str(source), "--destination", str(output),
                     "--receipt", str(receipt_path), "--out", str(verdict_path)],
                    scope=scope, progress=progress, cancel=cancel,
                    describe=f"{prefix}verifying", allow_failure=True,
                )
            except Cancelled:
                _remove(output)
                raise
            verdict = _verdict_from(verdict_path, lane.title)
        size, digest = _size_and_digest(output)
        return StepResult(
            lane_id=lane_id, index=index, title=lane.title,
            input_name=Path(source).name, output_name=Path(output).name,
            declared_ranges=len(receipt.declared_ranges),
            declared_bytes=sum(item.length for item in receipt.declared_ranges),
            artifacts=tuple(item.path for item in receipt.artifacts),
            verdict_passed=verdict.passed, verdict_summary=verdict.summary,
            seconds=time.monotonic() - started, output_size=size, output_sha256=digest,
            receipt_document=dict(receipt.document),
        )

    # -- child processes -----------------------------------------------

    class _Scratch:
        def __init__(self, prefix: str, near: Optional[Path]) -> None:
            self._prefix = prefix
            self._near = near
            self._path: Optional[Path] = None

        def __enter__(self) -> Path:
            self._path = Path(tempfile.mkdtemp(
                prefix=f"game-studio-{self._prefix}-",
                dir=str(self._near) if self._near is not None else None,
            )).resolve()
            return self._path

        def __exit__(self, *_exc: object) -> None:
            if self._path is not None:
                shutil.rmtree(self._path, ignore_errors=True)

    def _scratch(self, prefix: str, near: Optional[Path] = None) -> "GameStudioService._Scratch":
        return self._Scratch(prefix, near)

    def lane_command(self, lane_id: str, step: str, arguments: Sequence[str]) -> List[str]:
        """The exact command the studio runs, so a user can run it themselves."""

        command = [self._python, "-m", "mod_editor.games"]
        if self._games_root is not None:
            command += ["--games-root", str(self._games_root)]
        return command + ["lane", self.module.game_id, lane_id, step, *arguments]

    def _run_lane(
        self, lane_id: str, step: str, arguments: Sequence[str], *, scope: str,
        progress: Progress, cancel: Optional[CancelToken], describe: str,
        allow_failure: bool = False, on_failure: Optional[Callable[[], None]] = None,
    ) -> str:
        """Run one lane step as a child; relay its lines; keep its own sentence."""

        lane = self.module.lane(lane_id)
        command = self.lane_command(lane_id, step, arguments)
        returncode, tail = self._run_child(command, progress=progress, cancel=cancel,
                                           describe=describe)
        if returncode != 0 and not allow_failure:
            if on_failure is not None:
                on_failure()
            message = tail.strip() or f"the {step} step exited with code {returncode}"
            message = message[len("error: "):] if message.startswith("error: ") else message
            raise StudioError(f"{lane.title}: {message}")
        return tail

    def _run_child(
        self, command: Sequence[str], *, progress: Progress,
        cancel: Optional[CancelToken], describe: str,
    ) -> Tuple[int, str]:
        """Run one child process, relaying its output as progress; kill it on cancel."""

        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT), str(ROOT / "tools")]
            + ([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else [])
        )
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUNBUFFERED"] = "1"
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                list(command), cwd=str(ROOT), env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", creationflags=creation,
            )
        except OSError as exc:
            raise StudioError(f"Could not start {Path(command[0]).name}: {exc}") from exc
        lines: "queue.Queue[Tuple[str, str]]" = queue.Queue()

        def pump(stream: Any, channel: str) -> None:
            try:
                for line in iter(stream.readline, ""):
                    lines.put((channel, line.rstrip("\r\n")))
            finally:
                stream.close()

        readers = [threading.Thread(target=pump, args=(process.stdout, "out"), daemon=True),
                   threading.Thread(target=pump, args=(process.stderr, "err"), daemon=True)]
        for reader in readers:
            reader.start()
        started = time.monotonic()
        last_out = ""
        recent_err: List[str] = []
        last_report = 0.0

        def drain() -> None:
            nonlocal last_out
            while True:
                try:
                    channel, line = lines.get_nowait()
                except queue.Empty:
                    return
                if not line.strip():
                    continue
                if channel == "out":
                    last_out = line.strip()
                else:
                    recent_err.append(line.strip())
                    del recent_err[:-6]

        try:
            while process.poll() is None:
                drain()
                if cancel is not None and cancel.cancelled:
                    process.kill()
                    process.wait()
                    raise Cancelled("The operation was cancelled; nothing it created was kept.")
                now = time.monotonic()
                if progress is not None and now - last_report >= 0.5:
                    last_report = now
                    elapsed = int(now - started)
                    progress(f"{describe} · {elapsed // 60}:{elapsed % 60:02d} · {last_out}")
                time.sleep(self._poll)
        finally:
            for reader in readers:
                reader.join(timeout=2.0)
        drain()
        tail = " ".join(recent_err[-3:]) if recent_err else last_out
        return int(process.returncode or 0), tail


def _remove(path: Path) -> None:
    if os.path.lexists(path):
        if Path(path).is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            Path(path).unlink(missing_ok=True)


def _size_and_digest(path: Path) -> Tuple[int, str]:
    """A file's size and digest; a folder's total size and no digest."""

    target = Path(path)
    if target.is_dir():
        total = sum(item.stat().st_size for item in target.rglob("*") if item.is_file())
        return total, ""
    if not target.is_file():
        return 0, ""
    return target.stat().st_size, _sha256_file(target)


def _verdict_from(path: Path, lane_title: str) -> Verdict:
    """The verifier's own verdict, or a failing one saying it did not run."""

    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Verdict(False, f"The {lane_title} verifier did not write a verdict; do not use "
                              "what was written.")
    summary = str(document.get("summary") or "").strip()
    return Verdict(bool(document.get("passed")),
                   summary or f"The {lane_title} verifier gave no summary.",
                   dict(document.get("document", {}) or {}))


def service_for(report: DiscoveryReport, game_id: str, **kwargs: Any) -> GameStudioService:
    """A service over one discovered module; a refused module raises a Refusal."""

    return GameStudioService(report.game(game_id), **kwargs)


__all__ = [
    "BuildEstimate",
    "BuildReceipt",
    "CATALOGUE_SUFFIX",
    "CancelToken",
    "Cancelled",
    "CatalogueState",
    "DEFAULT_SCOPE",
    "DEFAULT_SCOPES",
    "GameStudioService",
    "RECEIPT_SCHEMA",
    "RECEIPT_SUFFIX",
    "STAGING_RESERVE",
    "Scope",
    "StepResult",
    "StudioActionState",
    "StudioError",
    "default_cache_root",
    "is_read_only",
    "lane_scopes",
    "open_filter",
    "service_for",
    "studio_action_state",
    "suggested_destination",
    "writes_files",
]
