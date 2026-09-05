"""Qt-free service behind the PS2 Disc Studio window.

The window never talks to a lane tool directly.  This module is the seam: it
opens the user's own ``SLUS-20919`` ISO read-only and identity-checks it the
way the disc inventory does, builds or loads each lane's target catalogue from
that disc through the lane's own catalogue tool, keeps the catalogues in a
private sidecar keyed by the disc, composes and plans recipes through the six
:mod:`ps2_disc_studio_lanes` adapters, and runs the build queue that writes a
NEW image -- never the source -- and verifies every step with the lane's
independent verifier.

Two boundaries are deliberate.

*The source is never written.*  Every patcher opens it read-only and creates
its destination ``O_EXCL``; this service refuses a destination that exists, a
destination that is the source, and a volume without room for the image plus
one intermediate, before the first byte.  A cancelled or failed step removes
the part-written image it created and nothing else.

*Long work runs in child processes.*  A catalogue build runs the lane's own
tool (``python tools/<catalogue tool>.py --iso … --output …``); a build step
runs :mod:`ps2_disc_studio_worker` (plan, write, verify).  The tools have no
progress or cancel hook and one step holds ~1 GiB of staged pack; a child
gives every lane the same honest progress (elapsed time plus the tool's own
last line), a real Cancel (terminate), and memory that is freed when the step
ends.  The audio verifier already spawns ``ps2_iso9660_verify`` this way.

Threading: :meth:`open`, :meth:`build_catalogue`, :meth:`plan_lane` and
:meth:`build` are slow and are meant to run off the Qt thread with a
:class:`CancelToken`; the fast readers (:meth:`targets`, :meth:`check_edit`,
the disc-display helpers) are meant for the thread that owns the view.  The
dialog serialises them: it never queries while an operation is running.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import platform_compat
from .ps2_disc_studio_lanes import (
    DEFAULT_SCOPE,
    LANE_ORDER,
    Lane,
    LaneRefusal,
    PlanResult,
    Ps2DiscStudioError,
    RecipeContext,
    RecipeStep,
    SERIAL,
    StagedEdit,
    Target,
    lane as lane_by_id,
    lanes_in_order,
)

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl2k5_ps2_disc_inventory as inventory_lib  # noqa: E402
import ps2_iso9660 as iso_lib  # noqa: E402

RECEIPT_SCHEMA = "nfl2k5_ps2_disc_studio_receipt/v1"
RECEIPT_SUFFIX = ".ps2-disc-studio-receipt.v1.json"
WORKER_MODULE = "mod_editor.core.ps2_disc_studio_worker"

#: Room a build step needs beyond the images themselves: the staged 1 GiB pack
#: plus the recipe and report files.
STAGING_RESERVE = int(1.25 * (1 << 30))
GIB = float(1 << 30)

Progress = Optional[Callable[[str], None]]


class Cancelled(Ps2DiscStudioError):
    """The user cancelled; whatever was being created has been removed."""


class CancelToken:
    """A plain event the dialog sets and the service's loops poll."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self, what: str = "The operation") -> None:
        if self._event.is_set():
            raise Cancelled(f"{what} was cancelled.")


def default_cache_root() -> Path:
    """Where the disc-keyed catalogues live: the studio's private per-user root."""
    return platform_compat.user_private_root() / "2k5-mod-studio" / "ps2-disc-studio"


def _gib(value: int) -> str:
    return f"{value / GIB:.2f} GiB"


def _json_bytes(document: object) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# What the window shows
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DiscIdentity:
    """What the header shows about the open image before any catalogue."""

    name: str
    path: str
    size_bytes: int
    serial: Optional[str]
    serial_matches: bool
    boot_file: Optional[str]
    boot_sha256: Optional[str]
    retail_boot_elf: bool
    volume_id: str
    pack_count: int
    entry_count: int
    key: str

    @property
    def headline(self) -> str:
        if self.serial is None:
            serial = "no SYSTEM.CNF boot serial"
        elif self.serial_matches:
            serial = self.serial
        else:
            serial = f"{self.serial} (expected {SERIAL})"
        boot = "retail boot ELF" if self.retail_boot_elf else "boot ELF differs from retail"
        return f"{self.name} — {serial} · {boot} · {self.size_bytes:,} bytes"

    @property
    def supported(self) -> bool:
        return self.serial_matches


@dataclass(frozen=True)
class CatalogueState:
    """Whether a lane's catalogue exists for the open disc, and what it holds."""

    lane_id: str
    scope: str
    path: Optional[Path]
    built: bool
    summary: str
    seconds: Optional[float]

    @property
    def headline(self) -> str:
        if not self.built:
            return "Catalogue not built yet for this disc."
        took = f" · built in {self.seconds:.0f} s" if self.seconds else ""
        return f"{self.summary}{took}"


@dataclass(frozen=True)
class PlanOutcome:
    """One lane's staged edits, composed and dry-run against the open disc."""

    lane_id: str
    steps: Tuple[RecipeStep, ...]
    plans: Tuple[PlanResult, ...]

    @property
    def edits(self) -> int:
        return sum(step.edits for step in self.steps)

    @property
    def summary(self) -> str:
        return " | ".join(plan.summary for plan in self.plans) or "nothing staged"


@dataclass(frozen=True)
class BuildEstimate:
    """Free space and time, said before a build starts."""

    image_bytes: int
    steps: int
    needed_bytes: int
    available_bytes: int
    volume: str
    minutes_hint: str

    @property
    def fits(self) -> bool:
        return self.available_bytes >= self.needed_bytes

    @property
    def sentence(self) -> str:
        text = (
            f"Needs about {_gib(self.needed_bytes)} free on {self.volume}: a {_gib(self.image_bytes)} "
            f"new image, room for one {_gib(self.image_bytes)} intermediate while it is verified, and "
            f"{_gib(STAGING_RESERVE)} for the staged pack; {_gib(self.available_bytes)} is free."
        )
        if not self.fits:
            text += " Free some space or choose a destination on another drive."
        return text


@dataclass(frozen=True)
class StepResult:
    """One build step as the receipt records it."""

    lane_id: str
    index: int
    note: str
    input_name: str
    output_name: str
    plan_summary: str
    receipt: dict
    verdict_passed: bool
    verdict_summary: str
    verdict_report: dict
    seconds: Dict[str, float]
    output_size: int
    output_sha256: str
    input_sha256: Optional[str]
    recipe: dict


@dataclass(frozen=True)
class BuildReceipt:
    """Outcome of a whole queue: the new image, every step, every verdict."""

    destination: Path
    receipt_path: Path
    steps: Tuple[StepResult, ...]
    seconds: float
    source_sha256: str
    destination_sha256: str
    document: Dict[str, Any] = field(default_factory=dict)

    @property
    def all_verified(self) -> bool:
        return all(step.verdict_passed for step in self.steps)

    @property
    def message(self) -> str:
        lanes = ", ".join(lane_by_id(step.lane_id).title for step in self.steps)
        verdict = "every verifier passed" if self.all_verified else "a verifier did NOT pass; do not use the image"
        return (f"Wrote {self.destination.name} ({lanes}; {len(self.steps)} step{'' if len(self.steps) == 1 else 's'}, "
                f"{self.seconds / 60:.1f} min) — {verdict}. Your original disc image was not changed.")


# --------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------

class Ps2DiscStudioService:
    """Open one PS2 disc image read-only and drive the six lanes over it."""

    OPEN_FILTER = "PS2 disc images (*.iso *.bin *.img);;All files (*)"
    WAV_FILTER = "WAV audio (*.wav);;All files (*)"
    SAVE_FILTER = "PS2 disc image (*.iso)"

    def __init__(self, *, cache_root: Optional[Path] = None, python: Optional[str] = None,
                 poll_seconds: float = 0.2) -> None:
        self._cache_root = Path(cache_root) if cache_root is not None else default_cache_root()
        self._python = python or sys.executable
        self._poll = max(0.02, float(poll_seconds))
        self._source: Optional[Path] = None
        self._identity: Optional[DiscIdentity] = None
        self._catalogues: Dict[Tuple[str, str], dict] = {}
        self._targets: Dict[Tuple[str, str], List[Target]] = {}

    # -- state ---------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._identity is not None

    @property
    def source_path(self) -> Optional[Path]:
        return self._source

    @property
    def python(self) -> str:
        return self._python

    def identity(self) -> DiscIdentity:
        if self._identity is None:
            raise Ps2DiscStudioError("No disc image is open.")
        return self._identity

    def _require_open(self) -> Tuple[Path, DiscIdentity]:
        if self._source is None or self._identity is None:
            raise Ps2DiscStudioError("No disc image is open.")
        return self._source, self._identity

    @staticmethod
    def lanes() -> Tuple[Lane, ...]:
        return lanes_in_order()

    @staticmethod
    def lane(lane_id: str) -> Lane:
        return lane_by_id(lane_id)

    # -- opening -------------------------------------------------------

    def open(self, path: Path, progress: Progress = None) -> DiscIdentity:
        """Identity-check ``path`` read-only.  Fast (the boot ELF is hashed, nothing else)."""
        path = Path(path)
        if not path.is_file():
            raise Ps2DiscStudioError(f"{path} is not a file.")
        self.close()
        if progress is not None:
            progress("Reading the disc identity and pack table…")
        try:
            image = iso_lib.open_image(str(path))
            who = inventory_lib.image_identity(image, False)
            packs = inventory_lib.discover_packs(image)
            archive = inventory_lib.VirtualPacks(str(path), packs)
            try:
                outer, entries = inventory_lib.read_outer_table(archive)
                table = archive.read(0, inventory_lib.OUTER_HEADER_SIZE
                                     + len(entries) * inventory_lib.OUTER_ENTRY_SIZE)
            finally:
                archive.close()
        except (inventory_lib.InventoryError, iso_lib.Iso9660Error, OSError, ValueError) as exc:
            raise Ps2DiscStudioError(str(exc).strip() or exc.__class__.__name__) from exc
        size = path.stat().st_size
        key_material = "|".join([
            str(who.get("serial")), str(who.get("boot_sha256")), str(size), str(image.volume_id),
            hashlib.sha256(table).hexdigest(),
        ])
        self._source = path
        self._identity = DiscIdentity(
            name=path.name, path=str(path), size_bytes=size,
            serial=who.get("serial"), serial_matches=bool(who.get("serial_matches")),
            boot_file=who.get("boot_file"), boot_sha256=who.get("boot_sha256"),
            retail_boot_elf=bool(who.get("retail_boot_elf")), volume_id=str(image.volume_id),
            pack_count=len(packs), entry_count=int(outer["entry_count"]),
            key=hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:32],
        )
        self._catalogues.clear()
        self._targets.clear()
        return self._identity

    def close(self) -> None:
        self._source = None
        self._identity = None
        self._catalogues.clear()
        self._targets.clear()

    # -- the sidecar ---------------------------------------------------

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    def cache_dir(self) -> Path:
        _source, identity = self._require_open()
        directory = self._cache_root / identity.key
        if not directory.is_dir():
            platform_compat.create_private_directory(self._cache_root, parents=True, exist_ok=True)
            platform_compat.create_private_directory(directory, parents=True, exist_ok=True)
            (directory / "disc.json").write_bytes(_json_bytes({
                "schema": "nfl2k5_ps2_disc_studio_disc/v1",
                "name": identity.name, "size_bytes": identity.size_bytes, "serial": identity.serial,
                "boot_sha256": identity.boot_sha256, "volume_id": identity.volume_id,
                "pack_count": identity.pack_count, "entry_count": identity.entry_count,
                "key": identity.key, "note": "catalogues built from this disc, by the lane tools; "
                                             "no decoded text, colour words or payload",
            }))
        return directory

    def catalogue_path(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> Path:
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        name = lane_id if scope == DEFAULT_SCOPE.id else f"{lane_id}-{scope}"
        return self.cache_dir() / f"{name}.json"

    @staticmethod
    def _scope_of(lane: Lane, scope: Optional[str]) -> str:
        scopes = lane.scopes()
        if not scope:
            return scopes[0].id
        if scope not in {item.id for item in scopes}:
            raise Ps2DiscStudioError(f"{scope!r} is not a catalogue scope of the {lane.title} lane.")
        return scope

    def catalogue_state(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> CatalogueState:
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        path = self.catalogue_path(lane_id, scope)
        if not path.is_file():
            return CatalogueState(lane_id, scope, None, False, "", None)
        try:
            summary = lane.catalogue_summary(self.catalogue(lane_id, scope))
        except Ps2DiscStudioError as exc:
            return CatalogueState(lane_id, scope, path, False, str(exc), None)
        return CatalogueState(lane_id, scope, path, True, summary, self.last_timing(f"catalogue:{lane_id}:{scope}"))

    def catalogue(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> dict:
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        cached = self._catalogues.get((lane_id, scope))
        if cached is None:
            path = self.catalogue_path(lane_id, scope)
            if not path.is_file():
                raise Ps2DiscStudioError(f"The {lane.title} catalogue has not been built for this disc yet.")
            cached = lane.load_catalogue(path)
            self._catalogues[(lane_id, scope)] = cached
        return cached

    def catalogue_sha256(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> str:
        return _sha256_file(self.catalogue_path(lane_id, scope))

    def build_catalogue(self, lane_id: str, scope: str = DEFAULT_SCOPE.id, progress: Progress = None,
                        cancel: Optional[CancelToken] = None) -> CatalogueState:
        """Run the lane's catalogue tool over the open disc into the sidecar.  Slow; cancellable."""
        source, _identity = self._require_open()
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        final = self.catalogue_path(lane_id, scope)
        directory = final.parent
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{final.stem}-", suffix=".building.json",
                                                      dir=str(directory))
        os.close(descriptor)
        temporary = Path(temporary_name)
        command = lane.catalogue_command(self._python, source, temporary, scope)
        started = time.monotonic()
        try:
            returncode, tail = self._run_child(
                command, cwd=ROOT, progress=progress, cancel=cancel,
                describe=lambda elapsed, last: (
                    f"Building the {lane.title} catalogue from your disc… {elapsed}"
                    + (f" · {last}" if last else "")),
            )
            if returncode != 0:
                raise Ps2DiscStudioError(
                    f"The {lane.title} catalogue tool did not finish (exit {returncode}): "
                    + (tail or "no output"))
            document = lane.load_catalogue(temporary)
            if progress is not None:
                progress(f"Checking the {lane.title} catalogue…")
            os.replace(temporary, final)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        seconds = time.monotonic() - started
        self._record_timing(f"catalogue:{lane_id}:{scope}", seconds)
        self._catalogues[(lane_id, scope)] = document
        self._targets.pop((lane_id, scope), None)
        return CatalogueState(lane_id, scope, final, True, lane.catalogue_summary(document), seconds)

    def forget_catalogue(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> None:
        path = self.catalogue_path(lane_id, scope)
        path.unlink(missing_ok=True)
        self._catalogues.pop((lane_id, scope), None)
        self._targets.pop((lane_id, scope), None)

    # -- timings -------------------------------------------------------

    def _timings_path(self) -> Path:
        return self.cache_dir() / "timings.json"

    def timings(self) -> Dict[str, float]:
        try:
            document = json.loads(self._timings_path().read_bytes().decode("utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(k): float(v) for k, v in document.items() if isinstance(v, (int, float))} \
            if isinstance(document, dict) else {}

    def last_timing(self, key: str) -> Optional[float]:
        if not self.is_open:
            return None
        return self.timings().get(key)

    def _record_timing(self, key: str, seconds: float) -> None:
        document = self.timings()
        document[key] = round(float(seconds), 2)
        self._timings_path().write_bytes(_json_bytes(document))

    # -- targets and editing --------------------------------------------

    def targets(self, lane_id: str, scope: str = DEFAULT_SCOPE.id) -> List[Target]:
        scope = self._scope_of(self.lane(lane_id), scope)
        rows = self._targets.get((lane_id, scope))
        if rows is None:
            rows = self.lane(lane_id).targets(self.catalogue(lane_id, scope))
            self._targets[(lane_id, scope)] = rows
        return rows

    def target(self, lane_id: str, key: str, scope: str = DEFAULT_SCOPE.id) -> Target:
        for row in self.targets(lane_id, scope):
            if row.key == key:
                return row
        raise Ps2DiscStudioError(f"{key} is not in this disc's {self.lane(lane_id).title} catalogue.")

    def check_edit(self, lane_id: str, target: Target, values: dict,
                   staged: Sequence[StagedEdit] = ()) -> Optional[str]:
        """The inline refusal for an edit, or ``None`` when it may be staged."""
        try:
            return self.lane(lane_id).check_edit(target, values, staged)
        except Ps2DiscStudioError as exc:
            return str(exc)

    def stage(self, lane_id: str, target: Target, values: dict,
              staged: Sequence[StagedEdit] = ()) -> StagedEdit:
        refusal = self.check_edit(lane_id, target, values, staged)
        if refusal:
            raise Ps2DiscStudioError(refusal)
        lane = self.lane(lane_id)
        return StagedEdit(lane_id, target.key, dict(values), lane.edit_summary(target, values))

    def compose(self, lane_id: str, edits: Sequence[StagedEdit],
                scope: str = DEFAULT_SCOPE.id) -> List[RecipeStep]:
        source, _identity = self._require_open()
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        own = [edit for edit in edits if edit.lane_id == lane_id]
        if not own:
            return []
        catalogue_path = self.catalogue_path(lane_id, scope)
        context = RecipeContext(source=source, catalogue_path=catalogue_path,
                                catalogue_sha256=_sha256_file(catalogue_path) if lane_id == "stadium" else "")
        return lane.compose_recipes(self.catalogue(lane_id, scope), own, context)

    @staticmethod
    def recipe_preview(steps: Sequence[RecipeStep]) -> str:
        """The exact JSON the patcher will be handed, for the tab's preview box."""
        if not steps:
            return ""
        if len(steps) == 1:
            return json.dumps(steps[0].recipe, indent=2, sort_keys=True)
        return "\n\n".join(f"// step {index + 1}: {step.note}\n" + json.dumps(step.recipe, indent=2, sort_keys=True)
                           for index, step in enumerate(steps))

    def plan_lane(self, lane_id: str, edits: Sequence[StagedEdit], scope: str = DEFAULT_SCOPE.id,
                  progress: Progress = None, cancel: Optional[CancelToken] = None) -> PlanOutcome:
        """Compose and dry-run one lane against the open disc.  Nothing is written."""
        source, identity = self._require_open()
        lane = self.lane(lane_id)
        scope = self._scope_of(lane, scope)
        if not identity.supported:
            raise Ps2DiscStudioError(
                f"{identity.name} boots {identity.serial or 'no serial'}, not {SERIAL}; the six writers were "
                "proved on that disc only, so nothing is planned for this one.")
        steps = self.compose(lane_id, edits, scope)
        if not steps:
            raise Ps2DiscStudioError(f"Nothing is staged for the {lane.title} lane.")
        plans: List[PlanResult] = []
        catalogue_path = self.catalogue_path(lane_id, scope)
        for index, step in enumerate(steps):
            if cancel is not None:
                cancel.raise_if_cancelled("Planning")
            if progress is not None:
                progress(f"Checking the {lane.title} recipe against your disc"
                         + (f" (step {index + 1} of {len(steps)})" if len(steps) > 1 else "") + "…")
            work_dir = Path(tempfile.mkdtemp(prefix="ps2-disc-studio-plan-"))
            try:
                plans.append(lane.plan(source, step.recipe, catalogue_path, work_dir))
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)
        return PlanOutcome(lane_id, tuple(steps), tuple(plans))

    # -- the build -----------------------------------------------------

    def check_destination(self, destination: Path) -> Path:
        """The refusals that need no build: exists, is the source, or has no folder."""
        source, _identity = self._require_open()
        requested = Path(destination).expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        requested = Path(os.path.abspath(os.fspath(requested)))
        if os.path.lexists(requested):
            raise Ps2DiscStudioError(
                f"A file already exists there: {requested}. Choose a name that does not exist yet; "
                "an existing image is never overwritten.")
        if requested.resolve(strict=False) == source.resolve():
            raise Ps2DiscStudioError("The destination must not be the source image.")
        parent = requested.parent
        if not parent.is_dir() or parent.is_symlink():
            raise Ps2DiscStudioError(f"The destination's folder is missing or is a link: {parent}")
        receipt = parent / (requested.name + RECEIPT_SUFFIX)
        if os.path.lexists(receipt):
            raise Ps2DiscStudioError(f"A receipt already exists there: {receipt}. Choose another name.")
        return requested

    def estimate(self, steps: int, destination: Path) -> BuildEstimate:
        """Free space on the destination's volume against the image plus one intermediate."""
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
        hints = []
        for lane in self.lanes():
            seconds = self.last_timing(f"build:{lane.id}")
            if seconds:
                hints.append(f"{lane.title} {seconds / 60:.1f} min")
        if hints:
            minutes = "Last build steps on this machine: " + ", ".join(hints) + "."
        else:
            minutes = ("Each step copies the whole image and rewrites a 1 GiB pack, then two verifiers re-read "
                       "both images: expect several minutes per step, and tens of minutes for a stadium step.")
        return BuildEstimate(identity.size_bytes, max(1, steps), needed, int(available),
                             str(probe.anchor or probe), minutes)

    @staticmethod
    def ordered(plans: Sequence[PlanOutcome]) -> List[Tuple[PlanOutcome, RecipeStep, PlanResult]]:
        order = {lane_id: index for index, lane_id in enumerate(LANE_ORDER)}
        rows: List[Tuple[PlanOutcome, RecipeStep, PlanResult]] = []
        for outcome in sorted(plans, key=lambda item: order.get(item.lane_id, 99)):
            for step, plan in zip(outcome.steps, outcome.plans):
                rows.append((outcome, step, plan))
        return rows

    def build(self, plans: Sequence[PlanOutcome], destination: Path, progress: Progress = None,
              cancel: Optional[CancelToken] = None,
              scopes: Optional[Dict[str, str]] = None) -> BuildReceipt:
        """Run every planned step as a chained queue into a NEW image.  Slow; cancellable."""
        source, identity = self._require_open()
        rows = self.ordered(plans)
        if not rows:
            raise Ps2DiscStudioError("Stage and check at least one edit before building.")
        if not identity.supported:
            raise Ps2DiscStudioError(
                f"{identity.name} boots {identity.serial or 'no serial'}, not {SERIAL}; the six writers were "
                "proved on that disc only, so nothing is built from this one.")
        requested = self.check_destination(destination)
        estimate = self.estimate(len(rows), requested)
        if not estimate.fits:
            raise Ps2DiscStudioError(estimate.sentence)
        scopes = dict(scopes or {})

        started = time.monotonic()
        results: List[StepResult] = []
        intermediates: List[Path] = []
        created: List[Path] = []
        current_input = source
        source_sha256 = ""
        try:
            for index, (outcome, step, plan) in enumerate(rows):
                lane = self.lane(step.lane_id)
                last = index == len(rows) - 1
                output = requested if last else requested.parent / f".{requested.name}.step{index + 1}.iso"
                if os.path.lexists(output):
                    raise Ps2DiscStudioError(f"A file already exists where an intermediate image would go: {output}")
                if cancel is not None:
                    cancel.raise_if_cancelled("The build")
                work_dir = Path(tempfile.mkdtemp(prefix=f".{requested.name}.work-", dir=str(requested.parent)))
                job = {
                    "schema": "nfl2k5_ps2_disc_studio_job/v1",
                    "lane": step.lane_id,
                    "source": str(current_input),
                    "destination": str(output),
                    "recipe": step.recipe,
                    "catalogue_path": str(self.catalogue_path(step.lane_id, scopes.get(step.lane_id, DEFAULT_SCOPE.id))),
                    "work_dir": str(work_dir),
                    "result_path": str(work_dir / "result.json"),
                    "hash_input": index == 0,
                    "step": index + 1,
                    "steps": len(rows),
                }
                step_started = time.monotonic()
                try:
                    result = self._run_step(job, lane, progress, cancel)
                finally:
                    shutil.rmtree(work_dir, ignore_errors=True)
                created.append(output)
                self._record_timing(f"build:{step.lane_id}", time.monotonic() - step_started)
                if index == 0:
                    source_sha256 = str(result.get("input_sha256") or "")
                verdict = result.get("verdict") or {}
                results.append(StepResult(
                    lane_id=step.lane_id, index=index + 1, note=step.note,
                    input_name=Path(job["source"]).name, output_name=output.name,
                    plan_summary=str(result.get("plan_summary", plan.summary)),
                    receipt=dict(result.get("receipt") or {}),
                    verdict_passed=bool(verdict.get("passed")), verdict_summary=str(verdict.get("summary", "")),
                    verdict_report=dict(verdict.get("report") or {}),
                    seconds={k: float(v) for k, v in (result.get("seconds") or {}).items()},
                    output_size=int(result.get("output_size") or 0),
                    output_sha256=str(result.get("output_sha256") or ""),
                    input_sha256=result.get("input_sha256"),
                    recipe=lane.recipe_for_receipt(step.recipe),
                ))
                if not verdict.get("passed"):
                    raise Ps2DiscStudioError(
                        f"The {lane.title} verifier did not pass on step {index + 1}: {verdict.get('summary', '')}. "
                        "The part-written image has been removed.")
                # The previous intermediate was this step's verification baseline;
                # only now can it go.
                if current_input in intermediates:
                    current_input.unlink(missing_ok=True)
                    intermediates.remove(current_input)
                if not last:
                    intermediates.append(output)
                current_input = output
        except BaseException:
            # Everything this queue created goes: the intermediates still on
            # disk, an output whose verifier did not pass, and the destination
            # if the last step had already created it.  The source is never
            # in this list.
            for path in dict.fromkeys(intermediates + created):
                if path != source and os.path.lexists(path):
                    Path(path).unlink(missing_ok=True)
            raise

        seconds = time.monotonic() - started
        document = {
            "schema": RECEIPT_SCHEMA,
            "generated": _now(),
            "serial": SERIAL,
            "source": {"name": identity.name, "size": identity.size_bytes, "sha256": source_sha256,
                       "serial": identity.serial, "boot_sha256": identity.boot_sha256,
                       "retail_boot_elf": identity.retail_boot_elf, "modified": False},
            "destination": {"path": str(requested), "size": results[-1].output_size,
                            "sha256": results[-1].output_sha256, "same_size_as_source":
                            results[-1].output_size == identity.size_bytes},
            "steps": [{
                "step": item.index, "lane": item.lane_id, "note": item.note,
                "input": item.input_name, "output": item.output_name,
                "recipe": item.recipe, "plan": item.plan_summary, "receipt": item.receipt,
                "verdict": {"passed": item.verdict_passed, "summary": item.verdict_summary,
                            "report": item.verdict_report},
                "seconds": item.seconds, "output_sha256": item.output_sha256,
            } for item in results],
            "seconds_total": round(seconds, 1),
            "claims": {"source_opened_read_only": True, "destination_created_exclusively": True,
                       "every_step_independently_verified": all(item.verdict_passed for item in results),
                       "runtime_visibility_proved": False, "runtime_audibility_proved": False},
        }
        receipt_path = requested.parent / (requested.name + RECEIPT_SUFFIX)
        with open(receipt_path, "xb") as stream:
            stream.write(_json_bytes(document))
        return BuildReceipt(requested, receipt_path, tuple(results), seconds, source_sha256,
                            results[-1].output_sha256, document)

    def _run_step(self, job: dict, lane: Lane, progress: Progress, cancel: Optional[CancelToken]) -> dict:
        work_dir = Path(job["work_dir"])
        job_path = work_dir / "job.json"
        job_path.write_bytes(_json_bytes(job))
        output = Path(job["destination"])
        existed = os.path.lexists(output)
        prefix = f"Step {job['step']} of {job['steps']} · {lane.title}: "
        stage_text = {"text": "starting"}

        def on_line(line: str) -> None:
            try:
                event = json.loads(line)
            except ValueError:
                return
            if isinstance(event, dict) and event.get("event") == "stage":
                stage_text["text"] = str(event.get("text", ""))

        command = [self._python, "-m", WORKER_MODULE, str(job_path)]
        try:
            returncode, tail = self._run_child(
                command, cwd=ROOT, progress=progress, cancel=cancel, on_line=on_line,
                describe=lambda elapsed, _last: f"{prefix}{stage_text['text']} · {elapsed}",
            )
        except Cancelled:
            if not existed and os.path.lexists(output):
                output.unlink(missing_ok=True)
            raise
        result_path = Path(job["result_path"])
        result: dict = {}
        if result_path.is_file():
            try:
                result = json.loads(result_path.read_bytes().decode("utf-8"))
            except ValueError:
                result = {}
        if returncode != 0 or not result.get("ok"):
            if not existed and os.path.lexists(output):
                output.unlink(missing_ok=True)
            message = str(result.get("error") or tail or f"the worker exited with code {returncode}")
            stage = str(result.get("stage") or "")
            raise LaneRefusal(lane.id, f"{lane.title}: {message}", stage)
        return result

    # -- child processes -----------------------------------------------

    def _run_child(self, command: Sequence[str], *, cwd: Path, progress: Progress,
                   cancel: Optional[CancelToken], describe: Callable[[str, str], str],
                   on_line: Optional[Callable[[str], None]] = None) -> Tuple[int, str]:
        """Run one child, relaying its output as progress; kill it on cancel."""
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(ROOT), str(TOOLS)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = subprocess.Popen(
                list(command), cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                errors="replace", creationflags=creation,
            )
        except OSError as exc:
            raise Ps2DiscStudioError(f"Could not start {Path(command[0]).name}: {exc}") from exc
        lines: "queue.Queue[Tuple[str, str]]" = queue.Queue()

        def pump(stream, channel: str) -> None:
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
                if channel == "out":
                    if on_line is not None:
                        on_line(line)
                    if line.strip() and not line.lstrip().startswith("{"):
                        last_out = line.strip()
                else:
                    if line.strip():
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
                    progress(describe(f"{elapsed // 60}:{elapsed % 60:02d}", last_out))
                time.sleep(self._poll)
        finally:
            for reader in readers:
                reader.join(timeout=2.0)
        drain()
        tail = " ".join(recent_err[-3:]) if recent_err else last_out
        return int(process.returncode or 0), tail


__all__ = [
    "BuildEstimate", "BuildReceipt", "CancelToken", "Cancelled", "CatalogueState", "DiscIdentity",
    "PlanOutcome", "Ps2DiscStudioService", "RECEIPT_SCHEMA", "RECEIPT_SUFFIX", "STAGING_RESERVE",
    "StepResult", "WORKER_MODULE", "default_cache_root",
]
