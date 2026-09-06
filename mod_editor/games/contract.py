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
#: Shared **lane** bases live here.  ``_formats`` is a reader that knows a
#: container and nothing about a game; this is the layer above -- the lane
#: *shapes* two games on the same stack would otherwise write twice: how a
#: record edit becomes a plan, a build and an independent verdict; how a
#: texture member is exported and put back; how a string slot is rewritten in
#: place.  A base takes everything game-specific as data, including the game's
#: own disc-access module, so it is not a game either and discovery skips it
#: for the same reason.  A game composes a lane base exactly as it composes a
#: format package, and still never imports a sibling game.
SHARED_LANES_PACKAGE = "mod_editor.games._lanes"

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
#: The shapes an editor value may take.  A lane names the shape through
#: :class:`Field`; ``check_edit`` stays the authority on whether a value fits.
_FIELD_KINDS = (
    "text",
    "int",
    "float",
    "bool",
    "choice",
    "colour_argb",
    "png",
    "wav",
    "name_pick",
    "note",
)

#: The studio's pages, in the Xbox studio's order, as ``(page_id, title)``.
#: Every game's studio has all of them: a page whose lane does not exist yet is
#: present and says why, never hidden and never a dead button.
PAGE_ORDER: tuple[tuple[str, str], ...] = (
    ("uniforms", "Uniforms & Equipment"),
    ("rosters", "Names, Numbers & Faces"),
    ("identity", "Text & Team Identity"),
    ("field_art", "Field Art & Create-Team Art"),
    ("stadiums", "Stadiums"),
    ("presentation", "Presentation"),
    ("menus", "Menus & UI"),
    ("crib", "The Crib"),
    ("audio", "Audio"),
    ("gameplay", "Gameplay"),
    ("playbooks", "Playbooks & Plays"),
    ("textures", "All Textures"),
    ("saves", "Saves"),
    ("build", "Build & Share"),
)

#: Which page hosts a lane of a given capability-registry surface, by default.
#: A lane may name its own ``page`` instead; :func:`lane_page` reads both.  A
#: surface that two pages could claim is filed under the page that owns the
#: whole surface (``menus`` under *Menus & UI*, ``textures`` under *All
#: Textures*, ``logos_cards`` under *Text & Team Identity*); a lane that
#: belongs on the other page says so with ``page``.  The four surfaces the
#: shell plan's table does not name -- the two model surfaces, the cross-title
#: franchise restoration and the mode/state graph -- are filed on the nearest
#: page here rather than left without one.
SURFACE_PAGES: Mapping[str, str] = MappingProxyType({
    "audio": "audio",
    "catching_drops": "gameplay",
    "colors": "identity",
    "cpu_ai_draft": "gameplay",
    "crib_assets": "crib",
    "cross_title_model_conversion": "stadiums",
    "franchise_restoration_cross_title": "saves",
    "gameplay_tuning_sliders": "gameplay",
    "logos_cards": "identity",
    "menus": "menus",
    "mode_state_routing": "gameplay",
    "models_shap_scne": "stadiums",
    "players_rosters": "rosters",
    "portraits_faces": "rosters",
    "saves": "saves",
    "schedules_franchise": "saves",
    "scorebug_presentation": "presentation",
    "scripts_config": "playbooks",
    "stadiums_fields": "stadiums",
    "textures": "textures",
    "uniforms": "uniforms",
})

#: Where a lane goes when its surface is not in :data:`SURFACE_PAGES`: the
#: catch-all asset page, so a lane is always reachable somewhere.
_FALLBACK_PAGE = "textures"


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
class Field:
    """One editable value of a target, in the shape an editor should draw it.

    ``kind`` is one of ``text``, ``int``, ``float``, ``bool``, ``choice``,
    ``colour_argb``, ``png``, ``wav``, ``name_pick``, ``note``.  ``choices``
    lists the admissible values of a ``choice``; ``minimum`` and ``maximum``
    bound a number.  A field is the *shape* of a value, never the rule:
    ``Lane.check_edit`` stays the only authority on whether an edit fits, so a
    shell that draws a field it does not understand can still ask the lane.
    """

    key: str
    kind: str
    label: str
    help: str = ""
    choices: tuple[Any, ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    read_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ContractError("A field needs a non-empty key.")
        if self.kind not in _FIELD_KINDS:
            raise ContractError(
                f"Field {self.key}: kind {self.kind!r} is not one of "
                + ", ".join(_FIELD_KINDS) + "."
            )
        if not isinstance(self.label, str) or not self.label.strip():
            raise ContractError(f"Field {self.key}: label must be a non-empty string.")
        if not isinstance(self.choices, tuple):
            raise ContractError(f"Field {self.key}: choices must be a tuple.")
        for name in ("minimum", "maximum"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, (int, float)):
                raise ContractError(f"Field {self.key}: {name} must be a number or None.")
        if type(self.read_only) is not bool:
            raise ContractError(f"Field {self.key}: read_only must be a bool.")


@dataclass(frozen=True)
class Target:
    """One editable thing a lane's catalogue names.

    ``key`` is the selector the lane's recipe schema takes; ``budget`` is the
    fixed allocation in the user's words ("9 characters", "two 4-byte words");
    ``raw`` is the lane's own catalogue row, read-only.  ``fields`` is what an
    editor shows for the target -- the shape only; ``check_edit`` is the rule.
    """

    key: str
    label: str
    detail: str = ""
    budget: str = ""
    searchable: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)
    fields: tuple[Field, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ContractError("A target needs a non-empty key.")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ContractError(f"Target {self.key}: label must be a non-empty string.")
        if not isinstance(self.fields, tuple) or not all(isinstance(item, Field) for item in self.fields):
            raise ContractError(f"Target {self.key}: fields must be a tuple of Field.")
        keys = [item.key for item in self.fields]
        if len(keys) != len(set(keys)):
            raise ContractError(f"Target {self.key}: two fields claim one key.")
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
class Artifact:
    """One file a build produced, for lanes whose output is not an image.

    A texture pack, a pnach, an exported folder: these declare *files* the way a
    fixed-allocation lane declares byte ranges.  ``path`` is the file as
    written; ``sha256`` is what the verifier and the harness check it against.
    """

    path: str
    sha256: str
    kind: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise ContractError("An artifact needs a path.")
        if not isinstance(self.sha256, str) or _SHA256_RE.fullmatch(self.sha256) is None:
            raise ContractError(f"Artifact {self.path}: sha256 must be lowercase hex SHA-256.")


@dataclass(frozen=True)
class Receipt:
    """What a build did.  ``document`` is the lane tool's own receipt, verbatim.

    A fixed-allocation lane declares ``declared_ranges`` in the destination
    image; a lane that writes files declares ``artifacts``.  Every build
    declares one or the other, and the harness checks whichever it finds.
    """

    schema: str
    lane_id: str
    source: str
    destination: str
    declared_ranges: tuple[DeclaredRange, ...]
    document: Mapping[str, Any] = field(default_factory=dict)
    artifacts: tuple[Artifact, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.schema, str) or not self.schema.strip():
            raise ContractError("A receipt needs a schema id.")
        if not isinstance(self.artifacts, tuple) or not all(isinstance(item, Artifact) for item in self.artifacts):
            raise ContractError("Receipt artifacts must be a tuple of Artifact.")
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


@runtime_checkable
class ReadOnlyLane(Lane, Protocol):
    """A lane that only catalogues: ``plan``, ``build`` and ``verify`` refuse.

    An inventory is the shape: it names what is on the user's source, with
    sizes and digests, and writes nothing ever.  The shell renders its page as
    *inspect* -- a target table and no editor.

    ``read_only`` is the marker.  A protocol that added no member would match
    every lane at runtime (``isinstance`` asks only which members exist), so a
    read-only lane declares ``read_only = True`` and the shell reads the
    value, not merely the class.
    """

    read_only: bool


@dataclass(frozen=True)
class EncodedArt:
    """What an :class:`ArtLane` made of a user's PNG: the bytes and their size.

    ``png`` is the image as the lane would deliver it (a PCSX2 replacement
    pack carries PNGs), ``width`` and ``height`` the size it settled on, and
    ``note`` whatever the lane wants the user told -- "scaled 2x, PCSX2 scales
    it back", "palette reduced to 256 colours".  A PNG the lane cannot take is
    a :class:`Refusal` naming the size it wanted, never a silent resize.
    """

    png: bytes
    width: int
    height: int
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.png, (bytes, bytearray)) or not self.png:
            raise ContractError("Encoded art needs non-empty PNG bytes.")
        for name in ("width", "height"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ContractError(f"Encoded art needs a positive {name}.")
        object.__setattr__(self, "png", bytes(self.png))


@runtime_checkable
class ArtLane(Lane, Protocol):
    """A lane whose targets are texture art, previewable and replaceable.

    The shell's art pages get preview, Export PNG, Import PNG and *Write
    PCSX2 pack* from these three methods and nothing else.
    """

    def decode_png(self, source: Path, target: Target) -> bytes:
        """The target's art from the user's own source, as PNG bytes."""
        ...

    def encode(self, source: Path, target: Target, png: bytes) -> EncodedArt:
        """Take the user's PNG for ``target``, or :class:`Refusal` with the size it wanted."""
        ...

    def replacement_identity(self, target: Target) -> Optional[str]:
        """The PCSX2 replacement filename for the target, or None when the game does not run there."""
        ...


@runtime_checkable
class AudioLane(Lane, Protocol):
    """A lane whose targets are sounds: the page gets Play and Export WAV."""

    def decode_wav(self, source: Path, target: Target) -> bytes:
        """The target's sound from the user's own source, as WAV bytes."""
        ...


def lane_page(lane: Any) -> str:
    """Which studio page hosts ``lane``: its own ``page``, else its surface's.

    ``page`` is deliberately *not* a member of :class:`Lane`: making it one
    would refuse every lane written before the shell existed.  A lane that
    names one wins; otherwise :data:`SURFACE_PAGES` decides from the lane's
    capability-registry surface.
    """

    named = getattr(lane, "page", None)
    if isinstance(named, str) and named.strip():
        return named.strip()
    return SURFACE_PAGES.get(getattr(lane, "surface", ""), _FALLBACK_PAGE)


# --------------------------------------------------------------------------
# Executable patches: a lane kind for code changes, pnach-first.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class CodePatch:
    """One executable patch as the *host* tool defines it, before any translation.

    ``patch_id`` is the host's semantic id, ``parameters`` the values a user
    may set (names and the ranges the host states), ``host_site`` the host's
    own description of the code site it changes -- named targets, pinned
    executable digests, never raw retail bytes.  A PS2 module lists the host's
    patches so the chooser can say which are translated and which are not.
    """

    patch_id: str
    title: str
    surface: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    host_site: Mapping[str, Any] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.patch_id, str) or _LANE_ID_RE.fullmatch(self.patch_id) is None:
            raise ContractError(f"Code patch id {self.patch_id!r} is invalid.")
        for name in ("title", "surface"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ContractError(f"Code patch {self.patch_id}: {name} must be a non-empty string.")
        object.__setattr__(self, "parameters", _frozen(self.parameters))
        object.__setattr__(self, "host_site", _frozen(self.host_site))


@dataclass(frozen=True)
class MipsWord:
    """One 32-bit word at an EE virtual address: what it is, what it becomes."""

    address: int
    original: int
    replacement: int

    def __post_init__(self) -> None:
        for name in ("address", "original", "replacement"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ContractError(f"MipsWord {name} must be a 32-bit unsigned integer.")
        if self.address % 4:
            raise ContractError(f"MipsWord address 0x{self.address:08X} is not word-aligned.")
        if self.original == self.replacement:
            raise ContractError(f"MipsWord at 0x{self.address:08X} changes nothing.")


@dataclass(frozen=True)
class MipsPatch:
    """A host patch translated to the PS2 executable: words plus the ELF it is for.

    ``elf_identity`` names the executable the words were derived against --
    serial, boot file, its SHA-256 and the PCSX2 CRC -- so a pnach is never
    applied to, or verified against, a different build.
    """

    patch_id: str
    words: tuple[MipsWord, ...]
    elf_identity: Mapping[str, Any]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.words, tuple) or not self.words or not all(isinstance(w, MipsWord) for w in self.words):
            raise ContractError(f"MipsPatch {self.patch_id}: words must be a non-empty tuple of MipsWord.")
        addresses = [word.address for word in self.words]
        if len(addresses) != len(set(addresses)):
            raise ContractError(f"MipsPatch {self.patch_id}: an address is patched twice.")
        object.__setattr__(self, "elf_identity", _frozen(self.elf_identity))
        object.__setattr__(self, "parameters", _frozen(self.parameters))


@runtime_checkable
class CodePatchLane(Lane, Protocol):
    """A lane whose edits are executable patches, delivered emulator-side first.

    Everything :class:`Lane` requires still holds -- the catalogue lists the
    host's patches as targets, ``check_edit`` refuses parameters out of range
    or a patch with no translation, ``plan`` resolves words against the user's
    own ELF, ``build`` writes a ``.pnach`` (an artifact receipt), ``verify``
    re-reads the pnach and the ELF independently -- plus four methods that
    name the translation problem explicitly.  Writing the words into the ELF
    on a copy of the disc is a second, optional delivery through the
    fixed-allocation ISO writer; nothing here requires it.
    """

    def patches(self) -> tuple[CodePatch, ...]:
        """The host tool's patch catalogue, as it stores it; needs no source."""
        ...

    def translation(self, patch_id: str, parameters: Mapping[str, Any]) -> MipsPatch:
        """The MIPS words for one host patch, or ``Refusal`` when it is not mapped yet."""
        ...

    def emit_pnach(self, patches: Sequence[MipsPatch], crc: str) -> str:
        """The PCSX2 patch-file text delivering ``patches`` to the executable with ``crc``."""
        ...

    def verify_pnach(self, pnach_text: str, source: Path, expected: Sequence[MipsPatch]) -> Verdict:
        """Independent: every address inside the ELF, every original word as expected, nothing else declared."""
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

    ``console``, ``game`` and ``year`` are the three display fields the core
    composes :attr:`studio_label` from ("PS2", "NFL", "2K5" -> "PS2 NFL 2K5
    Studio").  ``title`` and ``platform`` stay: they are the long forms a
    detail pane and a receipt use.
    """

    schema: str
    game_id: str
    package: str
    title: str
    platform: str
    console: str
    game: str
    year: str
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
    #: ``{page_id: sentence}``: the game's own reason a studio page has no
    #: lane yet, shown under the core's default sentence.  Optional.
    page_notes: Mapping[str, str] = field(default_factory=dict)

    _REQUIRED = (
        "schema", "game_id", "package", "title", "platform", "console", "game", "year",
        "version", "contract",
        "registry_fragment", "allowlist_fragment", "pins",
        "product_modules", "tool_modules",
    )
    #: ``(key, maximum length, whitespace allowed)`` for the three label fields.
    _LABEL_FIELDS = (("console", 8, False), ("game", 24, True), ("year", 8, False))
    _OPTIONAL = ("allowlist_patterns", "page_notes")

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
        for name, limit, spaces_allowed in self._LABEL_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ContractError(
                    f"{self.root / MANIFEST_NAME}: {name} is {value!r}; it must be 1 to "
                    f"{limit} characters. The studio label is composed as "
                    "'<console> <game> <year> Studio'."
                )
            if not spaces_allowed and any(character.isspace() for character in value):
                raise ContractError(
                    f"{self.root / MANIFEST_NAME}: {name} is {value!r}; it must not contain "
                    "whitespace (the studio label separates the three fields with spaces)."
                )
            if value != value.strip():
                raise ContractError(
                    f"{self.root / MANIFEST_NAME}: {name} is {value!r}; it must not begin or "
                    "end with whitespace."
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
        pages = {page_id for page_id, _title in PAGE_ORDER}
        unknown = sorted(set(self.page_notes) - pages)
        if unknown:
            raise ContractError(
                f"{self.root / MANIFEST_NAME}: page_notes names {unknown}, which are not studio "
                "pages; the pages are " + ", ".join(sorted(pages)) + "."
            )
        for page_id, note in self.page_notes.items():
            if not isinstance(note, str) or not note.strip():
                raise ContractError(
                    f"{self.root / MANIFEST_NAME}: the page_notes entry for {page_id!r} must be "
                    "one non-empty sentence."
                )
        object.__setattr__(self, "page_notes", _frozen(self.page_notes))

    @property
    def studio_label(self) -> str:
        """``"<console> <game> <year> Studio"`` -- composed here, never hand-typed.

        One rule for every game, so a second title reads like the first:
        ``PS2 NFL 2K5 Studio``, ``PS2 Madden 09 Studio``, ``PS2 NCAA 06
        Studio``.  A module that spells the label out in its own files is
        refused by the conformance harness.
        """

        return f"{self.console} {self.game} {self.year} Studio"

    def page_note(self, page_id: str) -> str:
        """The game's own sentence about why a page is not available yet, if any."""

        note = self.page_notes.get(page_id, "")
        return note if isinstance(note, str) else ""

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
    label_fields = [name for name, _limit, _spaces in GameManifest._LABEL_FIELDS]
    absent = [key for key in label_fields if key not in document]
    if absent:
        raise ContractError(
            f"{path}: a game module must declare " + ", ".join(absent) + " in game.json; the "
            "studio label is composed as '<console> <game> <year> Studio' and is never "
            "hand-typed (e.g. \"console\": \"PS2\", \"game\": \"NFL\", \"year\": \"2K5\")."
        )
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
        elif key == "page_notes":
            if not isinstance(value, dict):
                raise ContractError(f"{path}: page_notes must be an object of page id to sentence.")
        elif not isinstance(value, str):
            raise ContractError(f"{path}: {key} must be a string.")
    return GameManifest(
        schema=document["schema"],
        game_id=document["game_id"],
        package=document["package"],
        title=document["title"],
        platform=document["platform"],
        console=document["console"],
        game=document["game"],
        year=document["year"],
        version=document["version"],
        contract=document["contract"],
        registry_fragment=document["registry_fragment"],
        allowlist_fragment=document["allowlist_fragment"],
        pins=document["pins"],
        product_modules=tuple(document["product_modules"]),
        tool_modules=tuple(document["tool_modules"]),
        root=root,
        allowlist_patterns=tuple(document.get("allowlist_patterns", [])),
        page_notes=dict(document.get("page_notes", {})),
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
    #: The window id of this module's studio -- the one the chooser opens and
    #: the one ``python -m mod_editor.games open <game>`` opens with no
    #: ``--window``.  It must name one of :attr:`windows`; every other window
    #: stays reachable by id.  ``"studio"`` by convention.
    studio_window: str

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
        if not isinstance(self.studio_window, str) or not self.studio_window.strip():
            raise ContractError(
                f"Game {self.identity.game_id}: studio_window must name the window that is this "
                "module's studio; its windows are " + (", ".join(window_ids) or "none") + "."
            )
        if self.studio_window not in window_ids:
            raise ContractError(
                f"Game {self.identity.game_id}: studio_window {self.studio_window!r} is not one "
                "of its windows (" + (", ".join(window_ids) or "none") + ")."
            )

    @property
    def game_id(self) -> str:
        return self.identity.game_id

    @property
    def version(self) -> str:
        """The module's own version, declared once in its manifest."""
        return self.manifest.version

    @property
    def studio(self) -> WindowSpec:
        """The module's studio window: what the chooser and ``open`` open."""

        return self.window(self.studio_window)

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
        elif isinstance(value, (str, int, tuple, MappingProxyType)):
            surface[name] = ("constant",)
    return surface


__all__ = [
    "ALLOWED_CORE_IMPORTS",
    "Artifact",
    "ArtLane",
    "AudioLane",
    "SHARED_FORMATS_PACKAGE",
    "SHARED_LANES_PACKAGE",
    "CONTRACT_MAJOR",
    "CONTRACT_MINOR",
    "CONTRACT_SCHEMA",
    "CONTRACT_VERSION",
    "Catalogue",
    "CodePatch",
    "CodePatchLane",
    "ContractError",
    "DeclaredRange",
    "Edit",
    "EncodedArt",
    "Field",
    "GAME_ATTRIBUTE",
    "GameIdentity",
    "GameManifest",
    "GameModule",
    "Lane",
    "MANIFEST_NAME",
    "MANIFEST_SCHEMA",
    "PAGE_ORDER",
    "MipsPatch",
    "MipsWord",
    "PINS_SCHEMA",
    "Plan",
    "REGISTRY_FRAGMENT_SCHEMA",
    "ReadOnlyLane",
    "Receipt",
    "Refusal",
    "SURFACE_PAGES",
    "SourceIdentifier",
    "SourceIdentity",
    "Target",
    "Verdict",
    "WindowSpec",
    "accepts_contract",
    "contract_surface",
    "lane_page",
    "load_manifest",
    "parse_contract",
    "require",
]
