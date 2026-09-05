"""The game-module contract: what a game must provide for the studios to host it.

This module is the whole public surface a *game package* may depend on.  A game
package lives under ``mod_editor/games/<game>/`` and is discovered, never
imported by name, by the core (:mod:`mod_editor.games`).  The core team owns
this file, the discovery code beside it, and the conformance harness that runs
against every discovered game in CI.  A game team owns everything under its own
package: identity, container readers and writers, catalogue tools, lanes,
independent verifiers, validators, windows, registry rows, allowlist lines and
count pins.

Three rules, restated here because everything below follows from them:

* **Passive.**  Nothing in this module reaches into a game, and a game reaches
  into the core only through this module (and the two stable helpers it names
  in :data:`ALLOWED_CORE_IMPORTS`).  Adding, changing or removing a game never
  edits an upstream file.
* **Fail closed.**  A game that declares another contract version, an
  identity that is not well-formed, or a lane that does not answer the
  protocol is *refused with a sentence*, never half-loaded.
* **Retail-free and fixed-allocation.**  A lane reads the user's own source
  read-only, writes a NEW destination that must not already exist, never moves
  or grows what it edits, declares every byte range it changes, and ships an
  independent verifier that can fail.  Catalogues carry names, offsets,
  lengths and digests -- never payload.

Versioning
----------

:data:`CONTRACT_SCHEMA` is ``vc_game_module/<major>.<minor>``-shaped in
spirit and spelled ``vc_game_module/v1`` today.  A game declares the contract
it was written against in ``GameModule.contract``; :func:`accepts_contract`
admits the same major version and any minor the core has reached.  Adding an
optional field or method bumps the minor; renaming or removing anything bumps
the major and is a deliberate, documented event.  The frozen-surface test in
``tests/mod_editor/test_games_contract.py`` pins every public name and field
here so an accidental edit fails CI before it reaches a game team.

Python 3.11+, standard library only, importable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from mod_editor.core.errors import ValidationError


#: The number the change procedure bumps (``major.minor``).  Everything else
#: about the version is derived from it: ``CONTRACT_SCHEMA`` is what a game
#: declares, ``CONTRACT_MAJOR``/``CONTRACT_MINOR`` what :func:`accepts_contract`
#: compares.  See ``mod_editor/games/CONTRACT_CHANGELOG.md`` for the procedure.
CONTRACT_VERSION = "1.0"
CONTRACT_MAJOR, CONTRACT_MINOR = (int(part) for part in CONTRACT_VERSION.split("."))
CONTRACT_SCHEMA = f"vc_game_module/v{CONTRACT_MAJOR}" + (
    "" if CONTRACT_MINOR == 0 else f".{CONTRACT_MINOR}"
)
MANIFEST_SCHEMA = "vc_game_module_manifest/v1"
REGISTRY_FRAGMENT_SCHEMA = "vc_mod_capability_registry_fragment/v1"
PINS_SCHEMA = "vc_game_module_pins/v1"

#: The name every game package must expose at module level.
GAME_ATTRIBUTE = "GAME"
#: The declarative manifest every game package must carry beside its code.
MANIFEST_NAME = "game.json"

#: The only ``mod_editor`` imports a game package may make at module level.
#: Everything else -- Qt dialogs, studio facades, another game -- must be
#: imported lazily inside a function, so a game stays importable without a
#: display and never binds itself to a core module the core team may move.
ALLOWED_CORE_IMPORTS = (
    "mod_editor.games.contract",
    "mod_editor.core.errors",
    "mod_editor.core.platform_compat",
)
#: Shared container and format packages live here and are the sanctioned way
#: for two games to reuse a stack: a game *composes* ``_formats`` packages, it
#: never imports a sibling game.  The leading underscore keeps discovery from
#: mistaking a format package for a game.  Ownership follows the format, not
#: the game: ``ps2_disc`` (ISO9660 + boot identity), ``vc_ps2`` (the Visual
#: Concepts outer-pack stack the NFL 2K5 PS2 lanes read, which an ESPN NBA 2K5
#: module would measure against before reusing), ``ea_tdb``, ``ps2_memcard``.
SHARED_FORMATS_PACKAGE = "mod_editor.games._formats"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GAME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")
_LANE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,127}$")
_CONTRACT_RE = re.compile(r"^vc_game_module/v(\d+)(?:\.(\d+))?$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
_CLASSIFICATIONS = (
    "extract-only",
    "offline-writer-proved",
    "read-only-mapped",
    "runtime-proved",
    "unknown",
    "unsafe/deferred",
)


class ContractError(ValidationError):
    """A game package does not meet the contract; the message says how."""


class Refusal(ContractError):
    """A lane declined to act.  One sentence, naming the condition and the fix.

    Every refusal a lane raises must be this type so a window, a worker or the
    conformance harness has exactly one thing to catch.  The wording is the
    lane tool's own sentence, surfaced verbatim: a refusal is never re-worded
    on its way up.
    """


def require(condition: object, message: str) -> None:
    """Raise :class:`Refusal` with ``message`` unless ``condition`` holds."""

    if not condition:
        raise Refusal(message)


def _frozen(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


def parse_contract(version: str) -> tuple[int, int]:
    """``"vc_game_module/v1"`` -> ``(1, 0)``; ``"vc_game_module/v1.2"`` -> ``(1, 2)``."""

    match = _CONTRACT_RE.match(version) if isinstance(version, str) else None
    if match is None:
        raise ContractError(
            f"Unrecognised game-module contract {version!r}; expected "
            f"{CONTRACT_SCHEMA} (or a minor revision of it)."
        )
    return int(match.group(1)), int(match.group(2) or 0)


def accepts_contract(version: str) -> bool:
    """True when this core can host a game written against ``version``."""

    try:
        major, minor = parse_contract(version)
    except ContractError:
        return False
    return major == CONTRACT_MAJOR and minor <= CONTRACT_MINOR


# --------------------------------------------------------------------------
# Identity: who the game is, and what the user handed us.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GameIdentity:
    """The retail identity of one game on one platform.

    ``game_id`` is the registry id (``nfl2k5_ps2``, ``madden08_ps2``).
    ``serials`` are the disc serials the game ships under (``SLUS-20919``);
    an Xbox title without a serial passes an empty tuple.  The digests are the
    pins a source is checked against: every executable and whole-image digest
    the game recognises as retail.  Nothing here is a payload.
    """

    game_id: str
    title: str
    platform: str
    serials: tuple[str, ...] = ()
    executable_sha256: tuple[str, ...] = ()
    content_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.game_id, str) or _GAME_ID_RE.fullmatch(self.game_id) is None:
            raise ContractError(
                f"Game id {self.game_id!r} must be lowercase letters, digits and "
                "underscores, 3 to 64 characters, and start with a letter or digit."
            )
        for name in ("title", "platform"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"Game {self.game_id}: {name} must be a non-empty string.")
        for name in ("serials", "executable_sha256", "content_sha256"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise ContractError(f"Game {self.game_id}: {name} must be a tuple.")
            if len(value) != len(set(value)):
                raise ContractError(f"Game {self.game_id}: {name} repeats a value.")
        for serial in self.serials:
            if not isinstance(serial, str) or not serial.strip():
                raise ContractError(f"Game {self.game_id}: serials must be non-empty strings.")
        for digest in self.executable_sha256 + self.content_sha256:
            if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
                raise ContractError(
                    f"Game {self.game_id}: {digest!r} is not a lowercase hex SHA-256."
                )


@dataclass(frozen=True)
class SourceIdentity:
    """What one user-supplied source is, as a lane's identifier read it.

    ``kind`` names the container (``ps2-iso``, ``ps2-psu``, ``xiso``, ...).
    ``serial_matches`` and ``retail_executable`` are the two facts a window
    shows before any row; ``headline`` is the one line it shows them in.
    ``details`` is whatever else the identifier learned (read-only mapping).
    """

    kind: str
    path: str
    size_bytes: int
    serial: Optional[str]
    executable_sha256: Optional[str]
    serial_matches: bool
    retail_executable: bool
    headline: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ContractError("A source identity needs a non-empty kind.")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ContractError("A source identity's size must be a non-negative int.")
        if self.executable_sha256 is not None and (
            not isinstance(self.executable_sha256, str)
            or _SHA256_RE.fullmatch(self.executable_sha256) is None
        ):
            raise ContractError("A source identity's executable digest must be hex SHA-256 or None.")
        if not isinstance(self.headline, str) or not self.headline.strip():
            raise ContractError("A source identity needs a headline.")
        object.__setattr__(self, "details", _frozen(self.details))


@runtime_checkable
class SourceIdentifier(Protocol):
    """Read a user's source read-only and say what it is.  Never writes."""

    #: Suffixes a file chooser should offer, lowercase with the dot.
    accepted_suffixes: tuple[str, ...]

    def identify(self, path: Path) -> SourceIdentity: ...


# --------------------------------------------------------------------------
# Catalogue, edits, plan, receipt, verdict: the lane vocabulary.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    """One editable thing a lane's catalogue names.

    ``key`` is the selector the lane's recipe schema takes; ``budget`` is the
    fixed allocation in the user's words ("9 characters", "two 4-byte words");
    ``raw`` is the lane's own catalogue row, read-only.
    """

    key: str
    label: str
    detail: str = ""
    budget: str = ""
    searchable: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ContractError("A target needs a non-empty key.")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ContractError(f"Target {self.key}: label must be a non-empty string.")
        object.__setattr__(self, "raw", _frozen(self.raw))


@dataclass(frozen=True)
class Catalogue:
    """A lane's targets, built from the user's own source and retail-free.

    ``document`` is the lane tool's own catalogue, verbatim, so a plan can pin
    against exactly what the tool wrote.  It carries digests and offsets and
    never payload; the conformance harness checks that claim.
    """

    schema: str
    lane_id: str
    source: str
    targets: tuple[Target, ...]
    document: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.schema, str) or not self.schema.strip():
            raise ContractError("A catalogue needs a schema id.")
        keys = [target.key for target in self.targets]
        if len(keys) != len(set(keys)):
            raise ContractError(f"Catalogue {self.lane_id}: target keys repeat.")
        object.__setattr__(self, "document", _frozen(self.document))

    def target(self, key: str) -> Target:
        for candidate in self.targets:
            if candidate.key == key:
                return candidate
        raise Refusal(
            f"{key!r} is not a target this catalogue names; choose one of the "
            f"{len(self.targets)} catalogued targets."
        )


@dataclass(frozen=True)
class Edit:
    """One staged change: a target key and the lane-specific values."""

    target_key: str
    values: Mapping[str, Any]
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.target_key, str) or not self.target_key.strip():
            raise ContractError("An edit needs a target key.")
        object.__setattr__(self, "values", _frozen(self.values))


@dataclass(frozen=True)
class DeclaredRange:
    """One byte range a build declares it will change, in the destination."""

    start: int
    length: int
    reason: str = ""

    def __post_init__(self) -> None:
        if type(self.start) is not int or self.start < 0:
            raise ContractError("A declared range needs a non-negative start.")
        if type(self.length) is not int or self.length <= 0:
            raise ContractError("A declared range needs a positive length.")

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class Plan:
    """What a build would change, decided without writing anything."""

    lane_id: str
    target_keys: tuple[str, ...]
    declared_ranges: tuple[DeclaredRange, ...]
    document: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "document", _frozen(self.document))

    @property
    def declared_bytes(self) -> int:
        return sum(item.length for item in self.declared_ranges)


@dataclass(frozen=True)
class Receipt:
    """What a build did.  ``document`` is the lane tool's own receipt, verbatim."""

    schema: str
    lane_id: str
    source: str
    destination: str
    declared_ranges: tuple[DeclaredRange, ...]
    document: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.schema, str) or not self.schema.strip():
            raise ContractError("A receipt needs a schema id.")
        object.__setattr__(self, "document", _frozen(self.document))


@dataclass(frozen=True)
class Verdict:
    """An independent verifier's answer.  ``passed`` is the only bit that matters."""

    passed: bool
    summary: str
    document: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.passed) is not bool:
            raise ContractError("A verdict's passed flag must be a bool.")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ContractError("A verdict needs a summary sentence.")
        object.__setattr__(self, "document", _frozen(self.document))


@runtime_checkable
class Lane(Protocol):
    """One editable surface of one game: exactly one capability-registry row.

    A lane wraps a catalogue tool, a patcher and an independent verifier -- the
    trio every shipped PS2 writer already has -- and adds the two things CI
    needs to prove it without game data: a synthetic source and a known-good
    edit on that source.  Every method that touches the user's source opens it
    read-only; every write goes to a destination that must not already exist.
    """

    lane_id: str
    capability_id: str
    surface: str
    title: str
    classification: str
    recipe_schema: str
    #: Repository-relative validators (``tools/validate_<lane>.sh`` / ``.bat``).
    validators: tuple[str, ...]
    #: True when the destination must keep the source's exact byte length.
    fixed_allocation: bool

    def build_catalogue(
        self, source: Path, *, progress: Optional[Callable[[str], None]] = None
    ) -> Catalogue: ...

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        """An inline refusal sentence for a proposed edit, or None when it fits."""
        ...

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        """The exact document the lane's own patcher accepts."""
        ...

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        """Dry run: resolve every edit against the live source; raise :class:`Refusal`."""
        ...

    def build(
        self,
        source: Path,
        destination: Path,
        recipe: Mapping[str, Any],
        catalogue: Catalogue,
        *,
        work_dir: Optional[Path] = None,
    ) -> Receipt: ...

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict: ...

    def synthetic_source(self, work_dir: Path) -> Path:
        """Write a retail-free source this lane can be proved on; return its path."""
        ...

    def conformance_edits(self, catalogue: Catalogue) -> tuple[Edit, ...]:
        """At least one edit the synthetic source accepts, for the harness."""
        ...


# --------------------------------------------------------------------------
# Windows: how a game reaches the File menu and the command line.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class WindowSpec:
    """A separate window a game offers, in the shape the PS2 windows set.

    ``factory(parent=None, **context)`` builds and returns the dialog; it must
    import Qt lazily.  ``flag`` is the command-line spelling that opens the
    window alone (``ps2-disc`` for ``--ps2-disc``).  A window that needs the
    Xbox studio's live session says so with ``needs_studio_session`` and is
    passed it as ``context["facade"]``; every other window opens with no
    studio state at all, which is what lets a user who owns only this game's
    release use it.
    """

    window_id: str
    menu_label: str
    tooltip: str
    flag: str
    factory: Callable[..., Any]
    needs_studio_session: bool = False

    def __post_init__(self) -> None:
        for name in ("window_id", "menu_label", "tooltip", "flag"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"A window spec needs a non-empty {name}.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.flag):
            raise ContractError(
                f"Window {self.window_id}: flag {self.flag!r} must be lowercase "
                "letters, digits and hyphens (it is spelled --<flag>)."
            )
        if not callable(self.factory):
            raise ContractError(f"Window {self.window_id}: factory must be callable.")


# --------------------------------------------------------------------------
# Manifest: the declarative half, readable by gates without importing code.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GameManifest:
    """``game.json`` beside a game package: what the gates need, no code.

    The gates -- registry validation, release staging, the runtime closure --
    read this file and the fragments it names.  They never import the game.
    Paths are relative to the package directory and may not escape it.
    """

    schema: str
    game_id: str
    package: str
    title: str
    platform: str
    version: str
    contract: str
    registry_fragment: str
    allowlist_fragment: str
    pins: str
    product_modules: tuple[str, ...]
    tool_modules: tuple[str, ...]
    root: Path
    #: Case-insensitive glob patterns selecting this game's lines in the
    #: release allowlist, for ``python -m mod_editor.games fragments``.
    #: Optional in ``game.json``; defaults to the package's own directory.
    allowlist_patterns: tuple[str, ...] = ()

    _REQUIRED = (
        "schema", "game_id", "package", "title", "platform", "version", "contract",
        "registry_fragment", "allowlist_fragment", "pins",
        "product_modules", "tool_modules",
    )
    _OPTIONAL = ("allowlist_patterns",)

    def __post_init__(self) -> None:
        if self.schema != MANIFEST_SCHEMA:
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: schema is {self.schema!r}, expected {MANIFEST_SCHEMA}."
            )
        if _GAME_ID_RE.fullmatch(self.game_id or "") is None:
            raise ContractError(f"{self.root / MANIFEST_NAME}: game_id {self.game_id!r} is invalid.")
        if not accepts_contract(self.contract):
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: declares contract {self.contract!r}; this core "
                f"hosts {CONTRACT_SCHEMA}."
            )
        if _VERSION_RE.fullmatch(self.version or "") is None:
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: version {self.version!r} must look like 1.2.3 "
                "(an optional -suffix is allowed)."
            )
        expected_package = f"mod_editor.games.{self.root.name}"
        if self.package != expected_package:
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: package is {self.package!r} but the "
                f"directory implies {expected_package!r}."
            )
        for name in ("registry_fragment", "allowlist_fragment", "pins"):
            self._fragment_path(getattr(self, name), name)
        for name in ("product_modules", "tool_modules", "allowlist_patterns"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(isinstance(v, str) and v for v in value):
                raise ContractError(f"{self.root / MANIFEST_NAME}: {name} must be a list of strings.")
        if not self.allowlist_patterns:
            object.__setattr__(self, "allowlist_patterns", (f"mod_editor/games/{self.root.name}/*",))

    def _fragment_path(self, relative: str, name: str) -> Path:
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: {name} must be a relative path inside the package."
            )
        return self.root / relative

    @property
    def registry_fragment_path(self) -> Path:
        return self._fragment_path(self.registry_fragment, "registry_fragment")

    @property
    def allowlist_fragment_path(self) -> Path:
        return self._fragment_path(self.allowlist_fragment, "allowlist_fragment")

    @property
    def pins_path(self) -> Path:
        return self._fragment_path(self.pins, "pins")

    def registry_document(self) -> dict[str, Any]:
        document = _read_json(self.registry_fragment_path)
        if document.get("schema") != REGISTRY_FRAGMENT_SCHEMA:
            raise ContractError(
                f"{self.registry_fragment_path}: schema is {document.get('schema')!r}, "
                f"expected {REGISTRY_FRAGMENT_SCHEMA}."
            )
        game = document.get("game")
        if not isinstance(game, dict) or game.get("id") != self.game_id:
            raise ContractError(
                f"{self.registry_fragment_path}: the fragment's game entry must carry id {self.game_id!r}."
            )
        return document

    def allowlist_lines(self) -> tuple[str, ...]:
        path = self.allowlist_fragment_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContractError(f"{path}: cannot read allowlist fragment: {exc}") from exc
        lines: list[str] = []
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "\\" in line or line.startswith("/") or ".." in line.split("/"):
                raise ContractError(f"{path}:{number}: not a canonical repository-relative path: {line}")
            if line in lines:
                raise ContractError(f"{path}:{number}: duplicated entry: {line}")
            lines.append(line)
        if not lines:
            raise ContractError(f"{path}: an allowlist fragment must name at least one file.")
        return tuple(lines)

    def pins_document(self) -> dict[str, Any]:
        document = _read_json(self.pins_path)
        if document.get("schema") != PINS_SCHEMA:
            raise ContractError(
                f"{self.pins_path}: schema is {document.get('schema')!r}, expected {PINS_SCHEMA}."
            )
        if document.get("game_id") != self.game_id:
            raise ContractError(f"{self.pins_path}: pins must carry game_id {self.game_id!r}.")
        return document


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"{path}: cannot read JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractError(f"{path}: expected a JSON object.")
    return document


def load_manifest(package_dir: Path) -> GameManifest:
    """Read ``<package_dir>/game.json`` into a validated :class:`GameManifest`."""

    root = Path(package_dir)
    path = root / MANIFEST_NAME
    document = _read_json(path)
    missing = [key for key in GameManifest._REQUIRED if key not in document]
    extra = sorted(set(document) - set(GameManifest._REQUIRED) - set(GameManifest._OPTIONAL))
    if missing or extra:
        raise ContractError(f"{path}: manifest keys differ: missing={missing} extra={extra}")
    for key in GameManifest._REQUIRED + GameManifest._OPTIONAL:
        if key not in document:
            continue
        value = document[key]
        if key in ("product_modules", "tool_modules", "allowlist_patterns"):
            if not isinstance(value, list):
                raise ContractError(f"{path}: {key} must be a list.")
        elif not isinstance(value, str):
            raise ContractError(f"{path}: {key} must be a string.")
    return GameManifest(
        schema=document["schema"],
        game_id=document["game_id"],
        package=document["package"],
        title=document["title"],
        platform=document["platform"],
        version=document["version"],
        contract=document["contract"],
        registry_fragment=document["registry_fragment"],
        allowlist_fragment=document["allowlist_fragment"],
        pins=document["pins"],
        product_modules=tuple(document["product_modules"]),
        tool_modules=tuple(document["tool_modules"]),
        root=root,
        allowlist_patterns=tuple(document.get("allowlist_patterns", [])),
    )


# --------------------------------------------------------------------------
# The module object: everything a game provides, in one value.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class GameModule:
    """What ``mod_editor/games/<game>/__init__.py`` exposes as ``GAME``."""

    contract: str
    identity: GameIdentity
    identifier: SourceIdentifier
    lanes: tuple[Lane, ...]
    windows: tuple[WindowSpec, ...]
    manifest: GameManifest
    package: str

    def __post_init__(self) -> None:
        if not accepts_contract(self.contract):
            raise ContractError(
                f"Game {self.identity.game_id} declares contract {self.contract!r}; "
                f"this core hosts {CONTRACT_SCHEMA}."
            )
        if self.manifest.game_id != self.identity.game_id:
            raise ContractError(
                f"Game {self.identity.game_id}: its manifest says {self.manifest.game_id!r}."
            )
        # The directory is the unit of ownership, so the package is checked by
        # its last component: a package loaded from another root (a test's
        # temporary games directory) carries a different prefix and is still
        # the same game.
        if self.package.rsplit(".", 1)[-1] != self.manifest.package.rsplit(".", 1)[-1]:
            raise ContractError(
                f"Game {self.identity.game_id}: package {self.package!r} is not the "
                f"manifest's {self.manifest.package!r}."
            )
        if not isinstance(self.identifier, SourceIdentifier):
            raise ContractError(f"Game {self.identity.game_id}: identifier does not implement SourceIdentifier.")
        if not isinstance(self.lanes, tuple):
            raise ContractError(f"Game {self.identity.game_id}: lanes must be a tuple.")
        lane_ids: list[str] = []
        capability_ids: list[str] = []
        for lane in self.lanes:
            if not isinstance(lane, Lane):
                raise ContractError(
                    f"Game {self.identity.game_id}: {lane!r} does not implement the Lane protocol."
                )
            if _LANE_ID_RE.fullmatch(lane.lane_id) is None:
                raise ContractError(f"Game {self.identity.game_id}: lane id {lane.lane_id!r} is invalid.")
            if lane.classification not in _CLASSIFICATIONS:
                raise ContractError(
                    f"Lane {lane.lane_id}: classification {lane.classification!r} is not a registry classification."
                )
            if not isinstance(lane.validators, tuple):
                raise ContractError(f"Lane {lane.lane_id}: validators must be a tuple of paths.")
            if type(lane.fixed_allocation) is not bool:
                raise ContractError(f"Lane {lane.lane_id}: fixed_allocation must be a bool.")
            lane_ids.append(lane.lane_id)
            capability_ids.append(lane.capability_id)
        if len(lane_ids) != len(set(lane_ids)):
            raise ContractError(f"Game {self.identity.game_id}: lane ids repeat.")
        if len(capability_ids) != len(set(capability_ids)):
            raise ContractError(f"Game {self.identity.game_id}: two lanes claim one capability row.")
        if not isinstance(self.windows, tuple):
            raise ContractError(f"Game {self.identity.game_id}: windows must be a tuple.")
        window_ids = [window.window_id for window in self.windows]
        flags = [window.flag for window in self.windows]
        if len(window_ids) != len(set(window_ids)) or len(flags) != len(set(flags)):
            raise ContractError(f"Game {self.identity.game_id}: window ids or flags repeat.")

    @property
    def game_id(self) -> str:
        return self.identity.game_id

    @property
    def version(self) -> str:
        """The module's own version, declared once in its manifest."""
        return self.manifest.version

    def lane(self, lane_id: str) -> Lane:
        for candidate in self.lanes:
            if candidate.lane_id == lane_id:
                return candidate
        raise Refusal(
            f"{self.game_id} has no lane {lane_id!r}; its lanes are "
            + ", ".join(item.lane_id for item in self.lanes) + "."
        )

    def window(self, window_id: str) -> WindowSpec:
        for candidate in self.windows:
            if candidate.window_id == window_id or candidate.flag == window_id:
                return candidate
        raise Refusal(
            f"{self.game_id} has no window {window_id!r}; its windows are "
            + ", ".join(item.window_id for item in self.windows) + "."
        )


def contract_surface() -> dict[str, tuple[str, ...]]:
    """The public names and dataclass fields of this module, for the frozen-API pin."""

    surface: dict[str, tuple[str, ...]] = {}
    for name in sorted(__all__):
        value = globals()[name]
        if isinstance(value, type) and hasattr(value, "__dataclass_fields__"):
            surface[name] = tuple(item.name for item in fields(value))
        elif isinstance(value, type) and issubclass(value, Exception):
            surface[name] = ("exception",)
        elif isinstance(value, type) and getattr(value, "_is_protocol", False):
            # Annotations are the protocol's attributes; the class body's
            # callables are its methods.  Computed here rather than through
            # ``__protocol_attrs__`` so the pin reads the same on 3.11 and 3.12.
            members = set(getattr(value, "__annotations__", {}))
            members.update(
                attribute
                for attribute, member in vars(value).items()
                if callable(member) and not attribute.startswith("_")
            )
            surface[name] = tuple(sorted(members))
        elif callable(value) and getattr(value, "__module__", None) == __name__:
            surface[name] = ("function",)
        elif isinstance(value, (str, int, tuple)):
            surface[name] = ("constant",)
    return surface


__all__ = [
    "ALLOWED_CORE_IMPORTS",
    "SHARED_FORMATS_PACKAGE",
    "CONTRACT_MAJOR",
    "CONTRACT_MINOR",
    "CONTRACT_SCHEMA",
    "CONTRACT_VERSION",
    "Catalogue",
    "ContractError",
    "DeclaredRange",
    "Edit",
    "GAME_ATTRIBUTE",
    "GameIdentity",
    "GameManifest",
    "GameModule",
    "Lane",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA",
    "PINS_SCHEMA",
    "Plan",
    "REGISTRY_FRAGMENT_SCHEMA",
    "Receipt",
    "Refusal",
    "SourceIdentifier",
    "SourceIdentity",
    "Target",
    "Verdict",
    "WindowSpec",
    "accepts_contract",
    "contract_surface",
    "load_manifest",
    "parse_contract",
    "require",
]
