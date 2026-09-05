"""Community playbook packs (``.2k5book``): a shareable, retail-free book recipe.

A pack is the studio's own ``formation_creates`` / ``play_creates`` /
``formation_links`` rows written out as JSON.  Those rows are what ``.2k5mod``
already stores and what :mod:`nfl2k5_formation_play_writer` already consumes, so
a pack carries **zero retail bytes**: every entry is a donor/replace *index*, a
name the author typed, eleven coordinates the author dragged, and node chains
built from the game's own opcode grammar.  Nothing of the user's disc travels
with the file.

Why a recipe and not a book blob.  A raw 78,768-byte PLAY resource is 90 %
somebody else's game data (the project's own rule, see
``nfl2k5_playbook_inspector`` and ``modpack``), and a playbook-only
``.2k5patch`` is opaque byte runs that cannot be reviewed or merged.  A recipe
is reviewable in a pull request, mergeable, portable between discs, and can be
retargeted from the team it was authored on to any other team.

Capacity is the binding constraint, not expressiveness: eight of the 32 retail
team books are already at the 270-play cap and the mean book has 5.6 spare play
slots, so a pack **replaces, never appends** if it wants to fit everywhere.  The
budget stage reports net growth for exactly that reason.

The offline check runs in a fixed order, and steps 1-6 need **no game data at
all** -- only the JSON and the codec:

1. ``schema``       - the document is a v1 pack and every field has the right type
2. ``budget``       - 50 formations / 270 plays / 3,500 nodes / 36 links per
                      formation / 40-character names / 15-node chains
3. ``validator``    - the ported retail play validator on every play, with the
                      descriptors :func:`nfl2k5_play_codec.build_descriptor`
                      computes (only possible when all eleven slots are authored)
4. ``class_flags``  - ``play_flags & 0x1FF`` equals the donor's, and the QB
                      chain's shape agrees with the header's class nibble (a
                      pass under a run header is *played* as a run: the receiver
                      icons vanish at the snap and the QB cannot throw)
5. ``legality``     - NFL alignment rules on every authored formation
6. ``donor``        - the donor came from :func:`nfl2k5_play_library.reference_play_for`
                      (same QB shape, same class, not a special), never "the
                      book's first play"
7. ``compile``      - a dry compile through the real writer; needs a book body,
                      so it only runs when one is supplied

Native conditions support alternate paths and fixed-opponent position/velocity
experiments. Their encoding can be checked offline; option gameplay and a
dependable modern read remain EXPERIMENTAL / UNWITNESSED.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace as _dc_replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import ValidationError
from . import nfl2k5_play_codec as codec
from . import nfl2k5_play_library as lib
from .nfl2k5_playbook_inspector import (
    BODY_SIZE,
    CATEGORY_CAPACITY,
    FORMATION_CAPACITY,
    FORMATION_PLAY_LINKS,
    NODE_BASE,
    NODE_SIZE,
    PLAY_CAPACITY,
    RESOURCE_HEADER_SIZE,
    STRING_BASE,
    Nfl2k5Playbook,
    parse_playbook_resource,
)

SCHEMA = "nfl2k5_playbook_pack/v1"
DEFENSE_SCHEMA = "nfl2k5_playbook_pack/v2"
OPTION_SCHEMA = "nfl2k5_playbook_pack/v3"
PACK_EXTENSION = ".2k5book"
MAX_PACK_BYTES = 8 << 20             # a recipe is text; 8 MiB is far past any real book
MAX_CUSTOM_NAME_CHARS = 40
MAX_CHAIN_NODES = 15
SLOT_COUNT = 11
NODE_CAPACITY = (STRING_BASE - NODE_BASE) // NODE_SIZE      # 3,500
RESOURCE_SIZE = RESOURCE_HEADER_SIZE + BODY_SIZE

#: The 32 team books (the other five -- Editor, GEN, PRACTICE, reference, WCO -- are
#: utility books a community pack has no business rewriting).
TEAM_BOOKS: tuple[str, ...] = (
    "ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI",
    "PIT", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS",
)
ALL_TEAMS = "ALL"
DEFENSE_BOOKS = TEAM_BOOKS + ("GEN", "reference", "WCO", "Editor", "PRACTICE")

BUDGET_LIMITS: Mapping[str, int] = {
    "formations": FORMATION_CAPACITY,
    "plays": PLAY_CAPACITY,
    "nodes": NODE_CAPACITY,
    "links_per_formation": FORMATION_PLAY_LINKS,
    "nodes_per_chain": MAX_CHAIN_NODES,
    "name_chars": MAX_CUSTOM_NAME_CHARS,
}

#: QB chain shape -> the class the header must carry (``nfl2k5_play_library``).
SIGNATURE_CLASS: Mapping[str, str] = {
    "pass": "pass", "pa_pass": "pass", "run": "run", "draw": "run", "qb_run": "run",
}
PLAY_TYPES = ("pass", "pa_pass", "run", "sneak", "keeper", "reverse", "defense")

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class PlaybookPackError(ValidationError):
    """A ``.2k5book`` is malformed or fails a check."""


# ---------------------------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PackDonor:
    """Which stock entry the author cloned, and the few header facts the offline
    check needs.  Indices are retail-book offsets (stable across discs); the name
    is what lets a retarget re-resolve them in another team's book."""

    index: int
    name: str = ""
    flags: int | None = None            # plays only: the donor's header word
    signature: str | None = None        # plays only: qb_signature of the donor's QB chain

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"index": self.index, "name": self.name}
        if self.flags is not None:
            out["flags"] = self.flags
        if self.signature is not None:
            out["signature"] = self.signature
        return out

    @classmethod
    def from_json(cls, value: object, label: str) -> "PackDonor":
        if not isinstance(value, Mapping):
            raise PlaybookPackError(f"{label}: donor must be an object.")
        extra = set(value) - {"index", "name", "flags", "signature"}
        if extra:
            raise PlaybookPackError(f"{label}: donor has unsupported fields {sorted(extra)}.")
        return cls(
            _index(value.get("index"), f"{label} donor index"),
            _text(value.get("name", ""), f"{label} donor name", allow_empty=True),
            _optional_index(value.get("flags"), f"{label} donor flags", maximum=0xFFFFFFFF),
            _optional_text(value.get("signature"), f"{label} donor signature"),
        )


@dataclass(frozen=True)
class PackFormation:
    """One :class:`nfl2k5_formation_play_writer.FormationCreateRequest` minus the
    per-disc ``asset_id``, plus the names a retarget resolves by."""

    id: str
    custom_name: str
    slot_positions: tuple[tuple[int, int], ...]
    position_codes: tuple[int, ...]                     # who lines up in each of the eleven slots
    donor: PackDonor
    replace_index: int | None = None
    replace_name: str = ""
    category_index: int | None = None
    category_positions: tuple[int, ...] | None = None   # set when no stock group fields the mix

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "custom_name": self.custom_name,
            "donor": self.donor.to_json(),
            "replace_index": self.replace_index,
            "replace_name": self.replace_name,
            "slot_positions": [list(pair) for pair in self.slot_positions],
            "position_codes": list(self.position_codes),
        }
        if self.category_index is not None:
            out["category_index"] = self.category_index
        if self.category_positions is not None:
            out["category_positions"] = list(self.category_positions)
        return out

    @classmethod
    def from_json(cls, value: object, ordinal: int) -> "PackFormation":
        label = f"formation {ordinal}"
        if not isinstance(value, Mapping):
            raise PlaybookPackError(f"{label} must be an object.")
        fields = {"id", "custom_name", "donor", "replace_index", "replace_name",
                  "slot_positions", "position_codes", "category_index", "category_positions"}
        extra = set(value) - fields
        if extra:
            raise PlaybookPackError(f"{label} has unsupported fields {sorted(extra)}.")
        pack_id = _identifier(value.get("id"), label)
        return cls(
            pack_id,
            _name(value.get("custom_name"), f"{label} ({pack_id})"),
            _slot_positions(value.get("slot_positions"), f"{label} ({pack_id})"),
            _position_codes(value.get("position_codes"), f"{label} ({pack_id}) position codes"),
            PackDonor.from_json(value.get("donor"), f"{label} ({pack_id})"),
            _optional_index(value.get("replace_index"), f"{label} replace index",
                            maximum=FORMATION_CAPACITY - 1),
            _text(value.get("replace_name", ""), f"{label} replace name", allow_empty=True),
            _optional_index(value.get("category_index"), f"{label} personnel group",
                            maximum=CATEGORY_CAPACITY - 1),
            _optional_position_codes(value.get("category_positions"), f"{label} personnel codes"),
        )

    def request_mapping(self, asset_id: str) -> dict[str, Any]:
        row: dict[str, Any] = {
            "asset_id": asset_id,
            "donor_formation_index": self.donor.index,
            "custom_name": self.custom_name,
            "slot_positions": [list(pair) for pair in self.slot_positions],
        }
        if self.category_index is not None:
            row["category_index"] = self.category_index
        if self.replace_index is not None:
            row["replace_index"] = self.replace_index
        if self.category_positions is not None:
            row["category_positions"] = list(self.category_positions)
        return row


@dataclass(frozen=True)
class PackPlay:
    """One :class:`nfl2k5_formation_play_writer.PlayCreateRequest` plus its menu
    link (a :class:`FormationLinkRequest`) and the names a retarget resolves by."""

    id: str
    custom_name: str
    play_type: str
    assignments: tuple[tuple[codec.AuthoredNode, ...] | None, ...]
    donor: PackDonor
    play_flags: int | None = None
    replace_index: int | None = None
    replace_name: str = ""
    concept: str = ""                     # the wizard concept / run scheme the author picked
    link_formation: str | int | None = None   # a pack formation id, or an existing formation index
    link_group: int | None = None         # 0-3: the three audible slots every populated formation uses

    defense_formation: str = ""
    front_index: int | None = None
    component: str = ""
    spy_slots: tuple[int, ...] = ()
    preset_recipe: bool = False
    option_intent: dict | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "custom_name": self.custom_name,
            "play_type": self.play_type,
            "concept": self.concept,
            "donor": self.donor.to_json(),
            "play_flags": self.play_flags,
            "replace_index": self.replace_index,
            "replace_name": self.replace_name,
            "link_formation": self.link_formation,
            "link_group": self.link_group,
            "assignments": [
                None if chain is None else codec.chain_json(chain)
                for chain in self.assignments
            ],
        }
        if self.option_intent is not None:
            out["option_intent"] = self.option_intent
        if self.play_type == "defense":
            out.update(defense_formation=self.defense_formation, front_index=self.front_index,
                       component=self.component, preset_recipe=self.preset_recipe,
                       spy_intent={"schema": lib.SPY_INTENT_SCHEMA, "slots": list(self.spy_slots)})
        return out

    @classmethod
    def from_json(cls, value: object, ordinal: int) -> "PackPlay":
        label = f"play {ordinal}"
        if not isinstance(value, Mapping):
            raise PlaybookPackError(f"{label} must be an object.")
        fields = {"id", "custom_name", "play_type", "concept", "donor", "play_flags",
                  "replace_index", "replace_name", "link_formation", "link_group", "assignments",
                  "defense_formation", "front_index", "component", "spy_intent", "preset_recipe", "option_intent"}
        extra = set(value) - fields
        if extra:
            raise PlaybookPackError(f"{label} has unsupported fields {sorted(extra)}.")
        pack_id = _identifier(value.get("id"), label)
        play_type = _text(value.get("play_type"), f"{label} ({pack_id}) play type")
        if play_type not in PLAY_TYPES:
            raise PlaybookPackError(
                f"{label} ({pack_id}): play type {play_type!r} is not one of {', '.join(PLAY_TYPES)}."
            )
        link = value.get("link_formation")
        if link is not None and not isinstance(link, str) and (
            isinstance(link, bool) or not isinstance(link, int)
        ):
            raise PlaybookPackError(f"{label} ({pack_id}): link_formation must be a formation id or an index.")
        return cls(
            pack_id,
            _name(value.get("custom_name"), f"{label} ({pack_id})"),
            play_type,
            _assignments(value.get("assignments"), f"{label} ({pack_id})"),
            PackDonor.from_json(value.get("donor"), f"{label} ({pack_id})"),
            _optional_index(value.get("play_flags"), f"{label} play flags", maximum=0xFFFFFFFF),
            _optional_index(value.get("replace_index"), f"{label} replace index",
                            maximum=PLAY_CAPACITY - 1),
            _text(value.get("replace_name", ""), f"{label} replace name", allow_empty=True),
            _text(value.get("concept", ""), f"{label} concept", allow_empty=True),
            link,
            _optional_index(value.get("link_group"), f"{label} audible group", maximum=3),
            _text(value.get("defense_formation", ""), "defense formation", allow_empty=True),
            _optional_index(value.get("front_index"), "defense front", maximum=PLAY_CAPACITY - 1),
            _text(value.get("component", ""), "defense component", allow_empty=True),
            _spy_slots(value.get("spy_intent")),
            _boolean(value.get("preset_recipe", False), "preset_recipe"),
            _option_intent(value.get("option_intent")),
        )

    @property
    def authored_slots(self) -> tuple[int, ...]:
        return tuple(s for s, chain in enumerate(self.assignments) if chain is not None)

    @property
    def node_count(self) -> int:
        return sum(len(chain) for chain in self.assignments if chain is not None)

    def request_mapping(self, asset_id: str) -> dict[str, Any]:
        row: dict[str, Any] = {
            "asset_id": asset_id,
            "donor_play_index": self.donor.index,
            "custom_name": self.custom_name,
            "assignments": [
                None if chain is None else codec.chain_json(chain)
                for chain in self.assignments
            ],
        }
        if self.replace_index is not None:
            row["replace_index"] = self.replace_index
        if self.play_flags is not None:
            row["play_flags"] = self.play_flags
        if self.option_intent is not None:
            row["option_intent"] = self.option_intent
        if self.spy_slots:
            row["spy_intent"] = {"schema": lib.SPY_INTENT_SCHEMA, "slots": list(self.spy_slots)}
        return row


@dataclass(frozen=True)
class PackBook:
    team: str
    name: str
    author: str
    version: str
    license: str
    targets: tuple[str, ...] = ()        # empty = just ``team``; ("ALL",) = the 32 team books
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        out = {"team": self.team, "name": self.name, "author": self.author,
               "version": self.version, "license": self.license}
        if self.targets:
            out["targets"] = list(self.targets)
        if self.notes:
            out["notes"] = self.notes
        return out

    @classmethod
    def from_json(cls, value: object) -> "PackBook":
        if not isinstance(value, Mapping):
            raise PlaybookPackError("“book” must be an object with team / name / author / version / license.")
        extra = set(value) - {"team", "name", "author", "version", "license", "targets", "notes"}
        if extra:
            raise PlaybookPackError(f"“book” has unsupported fields {sorted(extra)}.")
        team = _text(value.get("team"), "book team")
        targets = value.get("targets", ())
        if isinstance(targets, str):
            targets = (targets,)
        if not isinstance(targets, (list, tuple)):
            raise PlaybookPackError("“book.targets” must be a list of team names.")
        targets = tuple(_text(t, "book target") for t in targets)
        for name in targets:
            if name != ALL_TEAMS and name not in DEFENSE_BOOKS:
                raise PlaybookPackError(f"“{name}” is not a supported retail book (or “{ALL_TEAMS}”).")
        return cls(
            team,
            _text(value.get("name"), "book name"),
            _text(value.get("author"), "book author"),
            _text(value.get("version"), "book version"),
            _text(value.get("license"), "book license"),
            targets,
            _text(value.get("notes", ""), "book notes", allow_empty=True, max_chars=2000),
        )

    def resolved_targets(self) -> tuple[str, ...]:
        if not self.targets:
            return (self.team,)
        if ALL_TEAMS in self.targets:
            return TEAM_BOOKS
        return self.targets


@dataclass(frozen=True)
class PackBase:
    """What the author started from.  ``book_fingerprint`` is the SHA-256 of the
    retail 0x13390 body, so a mismatch means another patch already touched that
    book and the importer reports rather than guesses.  It is a digest, not data."""

    book_fingerprint: str
    donor_formation_count: int
    donor_play_count: int
    donor_node_count: int
    xiso_sha256: str = ""

    def to_json(self) -> dict[str, Any]:
        out = {
            "book_fingerprint": self.book_fingerprint,
            "donor_formation_count": self.donor_formation_count,
            "donor_play_count": self.donor_play_count,
            "donor_node_count": self.donor_node_count,
        }
        if self.xiso_sha256:
            out["xiso_sha256"] = self.xiso_sha256
        return out

    @classmethod
    def from_json(cls, value: object) -> "PackBase":
        if not isinstance(value, Mapping):
            raise PlaybookPackError("“base” must be an object with the book fingerprint and donor counts.")
        extra = set(value) - {"book_fingerprint", "donor_formation_count", "donor_play_count",
                              "donor_node_count", "xiso_sha256"}
        if extra:
            raise PlaybookPackError(f"“base” has unsupported fields {sorted(extra)}.")
        digest = _text(value.get("book_fingerprint"), "base book fingerprint")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PlaybookPackError("“base.book_fingerprint” must be a 64-character SHA-256 digest.")
        xiso = _text(value.get("xiso_sha256", ""), "base xiso digest", allow_empty=True)
        if xiso and not re.fullmatch(r"[0-9a-f]{64}", xiso):
            raise PlaybookPackError("“base.xiso_sha256” must be a 64-character SHA-256 digest.")
        return cls(
            digest,
            _index(value.get("donor_formation_count"), "base donor formation count",
                   maximum=FORMATION_CAPACITY),
            _index(value.get("donor_play_count"), "base donor play count", maximum=PLAY_CAPACITY),
            _index(value.get("donor_node_count"), "base donor node count", maximum=NODE_CAPACITY),
            xiso,
        )


@dataclass(frozen=True)
class PlaybookPack:
    book: PackBook
    base: PackBase
    formations: tuple[PackFormation, ...]
    plays: tuple[PackPlay, ...]
    schema: str = SCHEMA

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "book": self.book.to_json(),
            "base": self.base.to_json(),
            "budget": dict(BUDGET_LIMITS),
            "formations": [f.to_json() for f in self.formations],
            "plays": [p.to_json() for p in self.plays],
        }

    def dumps(self) -> str:
        """Pretty JSON with the numeric leaves kept on one line.

        A pack is meant to be read in a pull request: ``indent=1`` alone puts every
        coordinate and every operand on its own line and turns fifteen entries into
        thousands of lines of noise, so short all-numeric arrays stay inline."""

        return _pretty_json(self.to_json()) + "\n"

    @property
    def formations_by_id(self) -> dict[str, PackFormation]:
        return {f.id: f for f in self.formations}


# ---------------------------------------------------------------------------------------------
# Field parsing (schema stage 1 lives here: every constructor validates its own types)
# ---------------------------------------------------------------------------------------------

_INLINE_WIDTH = 110


def _pretty_json(value: object, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, Mapping):
        if not value:
            return "{}"
        rows = [f"{pad} {json.dumps(str(k))}: {_pretty_json(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(rows) + f"\n{pad}}}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        compact = json.dumps(list(value), separators=(", ", ": "), ensure_ascii=False)
        if len(compact) + indent <= _INLINE_WIDTH and not any(
            isinstance(item, Mapping) for item in value
        ):
            return compact
        rows = [f"{pad} {_pretty_json(item, indent + 1)}" for item in value]
        return "[\n" + ",\n".join(rows) + f"\n{pad}]"
    return json.dumps(value, ensure_ascii=False)


def _number(value: object) -> float | int:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value  # type: ignore[return-value]


def _text(value: object, label: str, *, allow_empty: bool = False, max_chars: int = 200) -> str:
    if not isinstance(value, str):
        raise PlaybookPackError(f"{label} must be text.")
    text = value.strip()
    if not text and not allow_empty:
        raise PlaybookPackError(f"{label} must not be empty.")
    if len(text) > max_chars:
        raise PlaybookPackError(f"{label} is longer than {max_chars} characters.")
    return text


def _optional_text(value: object, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _identifier(value: object, label: str) -> str:
    text = _text(value, f"{label} id")
    if not _ID_RE.match(text):
        raise PlaybookPackError(
            f"{label}: id {text!r} must be lower-case letters, digits, '-', '_' or '.' (max 64)."
        )
    return text


def _name(value: object, label: str) -> str:
    text = _text(value, f"{label} name")
    if len(text) > MAX_CUSTOM_NAME_CHARS:
        raise PlaybookPackError(
            f"{label}: “{text}” is {len(text)} characters; the PLAY name pool allows {MAX_CUSTOM_NAME_CHARS}."
        )
    if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in text):
        raise PlaybookPackError(f"{label}: “{text}” may use printable ASCII only.")
    return text


def _index(value: object, label: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlaybookPackError(f"{label} must be a whole number of 0 or more.")
    if maximum is not None and value > maximum:
        raise PlaybookPackError(f"{label} must be {maximum} or less.")
    return value


def _optional_index(value: object, label: str, *, maximum: int | None = None) -> int | None:
    return None if value is None else _index(value, label, maximum=maximum)


def _slot_positions(value: object, label: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, (list, tuple)) or len(value) != SLOT_COUNT:
        raise PlaybookPackError(f"{label}: slot_positions needs exactly eleven (x, depth) pairs in centimetres.")
    out: list[tuple[int, int]] = []
    for pair in value:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise PlaybookPackError(f"{label}: each slot position must be an (x_cm, depth_cm) pair.")
        x, z = pair
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (x, z)):
            raise PlaybookPackError(f"{label}: slot positions must be numbers (centimetres).")
        xi, zi = int(round(x)), int(round(z))
        if not -3000 <= xi <= 3000 or not -3000 <= zi <= 3000:
            raise PlaybookPackError(f"{label}: a slot position is outside the field (±30 m).")
        out.append((xi, zi))
    return tuple(out)


def _position_codes(value: object, label: str) -> tuple[int, ...]:
    codes = _optional_position_codes(value, label)
    if codes is None:
        raise PlaybookPackError(f"{label} must list eleven position codes.")
    return codes


def _optional_position_codes(value: object, label: str) -> tuple[int, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != SLOT_COUNT:
        raise PlaybookPackError(f"{label} must list exactly eleven position codes.")
    out: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 255:
            raise PlaybookPackError(f"{label}: each position code must be a byte.")
        if (item & 0x1F) not in codec.POSITION_KINDS:
            raise PlaybookPackError(f"{label}: code 0x{item:02x} names no known position.")
        out.append(item)
    return tuple(out)


def _assignments(value: object, label: str) -> tuple[tuple[codec.AuthoredNode, ...] | None, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != SLOT_COUNT:
        raise PlaybookPackError(
            f"{label}: assignments needs exactly eleven entries (null keeps the donor's chain)."
        )
    chains: list[tuple[tuple[int, tuple[float, ...]], ...] | None] = []
    for slot, chain in enumerate(value):
        if chain is None:
            chains.append(None)
            continue
        if not isinstance(chain, (list, tuple)) or not 1 <= len(chain) <= MAX_CHAIN_NODES:
            raise PlaybookPackError(
                f"{label}: slot {slot} needs 1 through {MAX_CHAIN_NODES} nodes (the descriptor's count is four bits)."
            )
        try:
            codec.encode_chain(chain)
        except (ValueError, TypeError, IndexError) as exc:
            raise PlaybookPackError(f"{label}: slot {slot}: {exc}") from exc
        nodes = [(n[0], tuple(float(v) for v in n[1]), *n[2:]) for n in chain]
        chains.append(tuple(nodes))
    return tuple(chains)


# ---------------------------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------------------------

def book_fingerprint(resource_or_body: bytes) -> str:
    """SHA-256 of the retail 0x13390 PLAY *body* (the 0x20 wrapper is not hashed)."""

    if len(resource_or_body) == RESOURCE_SIZE:
        body = resource_or_body[RESOURCE_HEADER_SIZE:]
    elif len(resource_or_body) == BODY_SIZE:
        body = resource_or_body
    else:
        raise PlaybookPackError(
            f"A PLAY book is {BODY_SIZE} bytes of body (or {RESOURCE_SIZE} with its wrapper); "
            f"this is {len(resource_or_body)}."
        )
    return hashlib.sha256(body).hexdigest()


def pack_from_json(document: object) -> PlaybookPack:
    if not isinstance(document, Mapping):
        raise PlaybookPackError("A playbook pack must be a JSON object.")
    extra = set(document) - {"schema", "book", "base", "budget", "formations", "plays"}
    if extra:
        raise PlaybookPackError(f"The pack has unsupported top-level fields {sorted(extra)}.")
    schema = document.get("schema")
    if schema not in (SCHEMA, DEFENSE_SCHEMA, OPTION_SCHEMA):
        raise PlaybookPackError(
            f"This file declares schema {schema!r}; this studio reads {SCHEMA!r}."
        )
    budget = document.get("budget")
    if budget is not None:
        if not isinstance(budget, Mapping):
            raise PlaybookPackError("“budget” must be an object.")
        for key, limit in budget.items():
            expected = BUDGET_LIMITS.get(str(key))
            if expected is None:
                raise PlaybookPackError(f"“budget.{key}” is not a limit this format defines.")
            if limit != expected:
                raise PlaybookPackError(
                    f"“budget.{key}” says {limit}; the engine's limit is {expected}. "
                    "The budget block is informational and must match."
                )
    formations_raw = document.get("formations", [])
    plays_raw = document.get("plays", [])
    if not isinstance(formations_raw, list) or not isinstance(plays_raw, list):
        raise PlaybookPackError("“formations” and “plays” must be lists.")
    formations = tuple(PackFormation.from_json(v, i) for i, v in enumerate(formations_raw, 1))
    plays = tuple(PackPlay.from_json(v, i) for i, v in enumerate(plays_raw, 1))
    if not formations and not plays:
        raise PlaybookPackError("A playbook pack must contain at least one formation or play.")
    seen: set[str] = set()
    for entry in (*formations, *plays):
        if entry.id in seen:
            raise PlaybookPackError(f"Two entries share the id “{entry.id}”.")
        seen.add(entry.id)
    known = {f.id for f in formations}
    for play in plays:
        if isinstance(play.link_formation, str) and play.link_formation not in known:
            raise PlaybookPackError(
                f"play “{play.id}” lists itself in formation “{play.link_formation}”, which this pack does not define."
            )
    if schema != OPTION_SCHEMA and any(p.play_type == "defense" for p in plays) != (schema == DEFENSE_SCHEMA):
        raise PlaybookPackError("Defense needs schema v2; offense-only packs use schema v1")
    if schema != OPTION_SCHEMA and any(p.option_intent or any(c and any(len(n) == 3 for n in c) for c in p.assignments) for p in plays):
        raise PlaybookPackError("Explicit branch flags and option intent require schema v3")
    if any(p.option_intent for p in plays) and (formations or any(p.replace_index is None for p in plays)):
        raise PlaybookPackError("Option packs keep native formations and replace existing plays only")
    for p in plays:
        if p.play_type == "defense" and (not p.defense_formation or p.component not in ("front", "coverage", "full")):
            raise PlaybookPackError("Defense needs a formation and a front / coverage / full component")
    pack_book = PackBook.from_json(document.get("book"))
    if schema == SCHEMA and any(t != ALL_TEAMS and t not in TEAM_BOOKS for t in pack_book.targets):
        raise PlaybookPackError("Utility book targets require defense schema v2")
    return PlaybookPack(
        pack_book,
        PackBase.from_json(document.get("base")),
        formations,
        plays,
        schema,
    )


def loads_pack(text: str) -> PlaybookPack:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlaybookPackError(f"That file is not valid JSON: {exc}") from exc
    return pack_from_json(document)


def load_pack(path: Path | str) -> PlaybookPack:
    path = Path(path).expanduser()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PlaybookPackError(f"Could not open {path}: {exc}") from exc
    if size > MAX_PACK_BYTES:
        raise PlaybookPackError(f"{path.name} is {size:,} bytes; a playbook pack is a small JSON recipe.")
    return loads_pack(path.read_text(encoding="utf-8"))


def save_pack(pack: PlaybookPack, path: Path | str) -> Path:
    path = Path(path).expanduser()
    if path.suffix.casefold() != PACK_EXTENSION:
        path = path.with_suffix(PACK_EXTENSION)
    path.write_text(pack.dumps(), encoding="utf-8", newline="\n")
    return path


# ---------------------------------------------------------------------------------------------
# The offline check
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckStage:
    name: str
    title: str
    ok: bool
    skipped: bool = False
    errors: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "ok": self.ok, "skipped": self.skipped,
                "errors": list(self.errors), "notes": list(self.notes)}


@dataclass(frozen=True)
class PackCheck:
    stages: tuple[CheckStage, ...]
    totals: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(stage.ok for stage in self.stages)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(e for stage in self.stages for e in stage.errors)

    def to_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "totals": dict(self.totals),
                "stages": [stage.to_json() for stage in self.stages]}

    def text(self) -> str:
        lines = []
        for stage in self.stages:
            mark = "skip" if stage.skipped else ("PASS" if stage.ok else "FAIL")
            lines.append(f"[{mark}] {stage.title}")
            for note in stage.notes:
                lines.append(f"        {note}")
            for err in stage.errors:
                lines.append(f"    !!  {err}")
        lines.append("")
        lines.append("PACK CHECK: GREEN" if self.ok else "PACK CHECK: FAILED")
        return "\n".join(lines)


CHECK_ORDER = (
    ("schema", "1. Schema and types"),
    ("budget", "2. Budget (50 formations / 270 plays / 3,500 nodes / 36 links / 15-node chains)"),
    ("validator", "3. The ported retail play validator on every play"),
    ("class_flags", "4. Class-flag sanity (donor family kept, QB shape matches the class nibble)"),
    ("legality", "5. Formation legality (NFL alignment rules)"),
    ("donor", "6. Donor-header rule (a stock play of the same shape, never “the book's first play”)"),
    ("compile", "7. Dry compile through the real writer"),
)


def _descriptor_assignments(play: PackPlay, flags: int) -> tuple[list[tuple[int, list[bytes]]], str | None]:
    """Encode a fully authored play into the (descriptor, raw nodes) pairs the
    validator consumes.  The descriptor high byte (bits 24-31) is the donor's on a
    real book and is not read by the validator, so it is zero here."""

    assignments: list[tuple[int, list[bytes]]] = []
    for slot in range(SLOT_COUNT):
        chain = play.assignments[slot]
        if chain is None:
            return [], f"slot {slot} keeps the donor's chain, so the validator needs the book body"
        try:
            nodes = codec.encode_chain(chain)
        except ValueError as exc:
            return [], f"slot {slot}: {exc}"
        assignments.append((0, [node.to_bytes() for node in nodes]))
    for slot in range(SLOT_COUNT):
        try:
            desc = codec.build_descriptor(flags, assignments, slot, 0)
        except ValueError as exc:
            return [], f"slot {slot}: {exc}"
        assignments[slot] = (desc, assignments[slot][1])
    return assignments, None


def budget_totals(pack: PlaybookPack, book: Nfl2k5Playbook | None = None) -> dict[str, Any]:
    """Counts the pack leaves behind, from ``base`` (offline) or the target book."""

    formations = len(book.formations) if book is not None else pack.base.donor_formation_count
    plays = len(book.plays) if book is not None else pack.base.donor_play_count
    nodes = book.node_count if book is not None else pack.base.donor_node_count
    added_f = sum(1 for f in pack.formations if f.replace_index is None)
    added_p = sum(1 for p in pack.plays if p.replace_index is None)
    added_nodes = sum(p.node_count for p in pack.plays)
    return {
        "formations": formations + added_f, "formations_before": formations,
        "plays": plays + added_p, "plays_before": plays,
        "nodes": nodes + added_nodes, "nodes_before": nodes,
        "cloned_nodes": added_nodes, "node_pool_bytes": added_nodes * NODE_SIZE,
        "name_pool_bytes": sum((len(e.custom_name) + 1) * 2 for e in (*pack.formations, *pack.plays)),
        "formation_capacity": FORMATION_CAPACITY,
        "play_capacity": PLAY_CAPACITY,
        "node_capacity": NODE_CAPACITY,
        "net_formation_growth": added_f,
        "net_play_growth": added_p,
        "replaced_formations": sum(1 for f in pack.formations if f.replace_index is not None),
        "replaced_plays": sum(1 for p in pack.plays if p.replace_index is not None),
    }


def check_pack(
    pack: PlaybookPack,
    book: Nfl2k5Playbook | None = None,
    body: bytes | None = None,
    *,
    resource: bytes | None = None,
    asset_id: str = "pack-check",
) -> PackCheck:
    """Run the seven checks in order.  Steps 1-6 need no game data; step 7 runs
    only when ``resource`` (a full 0x20 + 0x13390 PLAY resource) is supplied."""

    if resource is not None and book is None:
        book = parse_playbook_resource(resource, asset_id=asset_id)
    if resource is not None and body is None:
        body = resource[RESOURCE_HEADER_SIZE:]

    if resource is None and body is not None and any(p.play_type == "defense" or p.option_intent for p in pack.plays):
        import struct
        resource = struct.pack("<4s7I", b"PLAY", BODY_SIZE, BODY_SIZE, 0, 0, 0, 0, 0) + body
    stages: list[CheckStage] = []
    totals = budget_totals(pack, book)

    # 1. schema -----------------------------------------------------------------
    notes = [f"{pack.book.name} v{pack.book.version} by {pack.book.author} "
             f"({pack.book.license}); authored on {pack.book.team}",
             f"{len(pack.formations)} formation(s), {len(pack.plays)} play(s)"]
    schema_errors: list[str] = []
    if book is not None and body is not None:
        digest = book_fingerprint(body)
        if digest != pack.base.book_fingerprint:
            if any(p.option_intent for p in pack.plays):
                schema_errors.append("Option source fingerprint changed; regenerate and review the intended test fixture")
            notes.append(
                "the supplied book is not the one this pack was authored on "
                f"(fingerprint {digest[:12]}… vs {pack.base.book_fingerprint[:12]}…) — "
                "indices are re-resolved by name on retarget"
            )
        else:
            notes.append("the supplied book matches base.book_fingerprint exactly")
    stages.append(CheckStage("schema", CHECK_ORDER[0][1], not schema_errors,
                             errors=tuple(schema_errors), notes=tuple(notes)))

    # 2. budget -----------------------------------------------------------------
    errors: list[str] = []
    notes = [
        f"plays {totals['plays']}/{PLAY_CAPACITY}, "
        f"formations {totals['formations']}/{FORMATION_CAPACITY}, "
        f"nodes {totals['nodes']}/{NODE_CAPACITY}",
        f"replaces {totals['replaced_formations']} formation(s) and {totals['replaced_plays']} play(s); "
        f"net growth {totals['net_formation_growth']} formation(s), {totals['net_play_growth']} play(s)",
    ]
    if totals["formations"] > FORMATION_CAPACITY:
        errors.append(f"{totals['formations']} formations exceeds the {FORMATION_CAPACITY} the engine holds")
    if totals["plays"] > PLAY_CAPACITY:
        errors.append(f"{totals['plays']} plays exceeds the {PLAY_CAPACITY} the engine holds")
    if body is not None:
        import struct
        used_names = struct.unpack_from('<I', body, 0x1083C)[0] * 2
        totals['name_pool_free_bytes'] = BODY_SIZE - STRING_BASE - used_names
        if totals['name_pool_bytes'] > totals['name_pool_free_bytes']:
            errors.append("The custom names exceed the remaining name pool bytes")
    if totals["nodes"] > NODE_CAPACITY:
        errors.append(f"{totals['nodes']} nodes exceeds the {NODE_CAPACITY} the node pool holds")
    if totals["net_play_growth"] or totals["net_formation_growth"]:
        notes.append(
            "this pack grows the book — eight retail books are already at the 270-play cap, "
            "so it will not fit every team"
        )
    seen_f: set[int] = set()
    for f in pack.formations:
        if f.replace_index is not None:
            if f.replace_index in seen_f:
                errors.append(f"two formations replace stock formation {f.replace_index}")
            seen_f.add(f.replace_index)
    seen_p: set[int] = set()
    for p in pack.plays:
        if p.replace_index is not None:
            if p.replace_index in seen_p:
                errors.append(f"two plays replace stock play {p.replace_index}")
            seen_p.add(p.replace_index)
        for slot, chain in enumerate(p.assignments):
            if chain is not None and len(chain) > MAX_CHAIN_NODES:
                errors.append(f"play “{p.id}” slot {slot} has {len(chain)} nodes (max {MAX_CHAIN_NODES})")
    links_per_formation: dict[object, int] = {}
    for p in pack.plays:
        if p.link_formation is not None:
            target_index = _link_target_index(pack, p.link_formation, book)
            if book is not None and target_index is not None and target_index < len(book.formations) and any(
                    l.play_index == p.replace_index for l in book.formations[target_index].play_links):
                continue
            if isinstance(p.link_formation, str):
                formation = pack.formations_by_id.get(p.link_formation)
                if formation is not None and book is not None and formation.replace_index is None and any(
                        l.play_index == p.replace_index for l in book.formations[formation.donor.index].play_links):
                    continue
            links_per_formation[p.link_formation] = links_per_formation.get(p.link_formation, 0) + 1
    for target, count in links_per_formation.items():
        used = 0
        if book is not None:
            index = _link_target_index(pack, target, book)
            if index is not None and 0 <= index < len(book.formations):
                used = len(book.formations[index].play_links)
        if used + count > FORMATION_PLAY_LINKS:
            errors.append(
                f"formation “{target}” would list {used + count} plays; the menu table holds {FORMATION_PLAY_LINKS}"
            )
    stages.append(CheckStage("budget", CHECK_ORDER[1][1], not errors,
                             errors=tuple(errors), notes=tuple(notes)))

    # 3. the ported retail validator --------------------------------------------
    errors, notes, skipped = [], [], False
    checked = 0
    for p in pack.plays:
        flags = p.play_flags if p.play_flags is not None else p.donor.flags
        if flags is None:
            errors.append(f"play “{p.id}” carries no play_flags and its donor's header is unrecorded")
            continue
        assignments, why = _descriptor_assignments(p, flags)
        if why is not None:
            if body is None:
                notes.append(f"play “{p.id}”: {why}")
                skipped = True
                continue
            assignments, why = _book_assignments(p, flags, body)
            if why is not None:
                errors.append(f"play “{p.id}”: {why}")
                continue
        try:
            codec.validate_sync(assignments)
            lib.validate_option_intent(p.option_intent, assignments, book, body)
            reason = codec.validate_play(flags, assignments)
        except ValueError as exc:
            reason = str(exc)
        if reason:
            errors.append(f"the game would reject “{p.custom_name}” ({p.id}): {reason}")
        else:
            checked += 1
    notes.insert(0, f"{checked} of {len(pack.plays)} play(s) ran the full validator")
    stages.append(CheckStage("validator", CHECK_ORDER[2][1], not errors, skipped and not checked,
                             errors=tuple(errors), notes=tuple(notes)))

    # 4. class-flag sanity -------------------------------------------------------
    errors, notes = [], []
    for p in pack.plays:
        flags = p.play_flags if p.play_flags is not None else p.donor.flags
        if flags is None:
            continue
        if p.donor.flags is not None and (flags & lib.PLAY_FLAGS_KEEP_MASK) != (
            p.donor.flags & lib.PLAY_FLAGS_KEEP_MASK
        ):
            errors.append(
                f"play “{p.id}”: header bits 0-8 are 0x{flags & 0x1FF:03x} but the donor's are "
                f"0x{p.donor.flags & 0x1FF:03x}; the validator checks the type code and family"
            )
        family = (flags >> 6) & 7
        if family != 0:
            notes.append(f"play “{p.id}” is family {family} (not offence); the QB rule does not apply")
            continue
        qb_chain = p.assignments[0]
        if p.option_intent and p.option_intent['preset'] == lib.OPTION_PRESETS[2]:
            if lib.play_class_label(flags) != 'pass':
                errors.append(f"play {p.id}: experimental RPO needs a pass-capable header")
            notes.append(f"play {p.id}: mixed give/pass classification is UNWITNESSED")
            continue
        if qb_chain is None:
            notes.append(f"play “{p.id}” keeps the donor's QB chain")
            continue
        signature = lib.qb_signature(qb_chain)
        wanted = SIGNATURE_CLASS.get(signature)
        if wanted is None:
            errors.append(
                f"play “{p.id}”: the slot-0 chain is not a QB shape the corpus knows "
                f"(qb_signature = {signature})"
            )
            continue
        actual = lib.play_class_label(flags)
        if actual != wanted:
            errors.append(
                f"play “{p.id}”: the QB chain is a {signature} but the header's class nibble says "
                f"{actual} (0x{flags & lib.PLAY_CLASS_MASK:04x}) — a pass under a run header is "
                "played as a run: the receiver icons vanish at the snap and the QB cannot throw"
            )
    stages.append(CheckStage("class_flags", CHECK_ORDER[3][1], not errors,
                             errors=tuple(errors), notes=tuple(notes)))

    # 5. formation legality ------------------------------------------------------
    errors, notes = [], []
    for f in pack.formations:
        slots = [
            codec.FormationSlot(0, codec.NO_MIRROR, 1, [x, x, x], [z, z, z])
            for x, z in f.slot_positions
        ]
        issues = codec.formation_legality(slots, f.position_codes, offense=not all(12 <= c & 31 <= 18 for c in f.position_codes))
        for issue in issues:
            errors.append(f"formation “{f.custom_name}” ({f.id}): {issue}")
        shotgun = f.slot_positions[0][1] <= codec.SHOTGUN_DEPTH_THRESHOLD_CM
        notes.append(
            f"“{f.custom_name}”: {'shotgun' if shotgun else 'under centre'}, "
            f"{lib.back_count(f.position_codes)} back(s), "
            + " ".join(codec.position_label(c) for c in f.position_codes[6:])
        )
        if f.category_positions is not None and f.category_index is None:
            errors.append(
                f"formation “{f.id}” writes personnel codes but names no personnel group to write them into"
            )
        if f.category_positions is not None and tuple(f.category_positions) != tuple(f.position_codes):
            errors.append(
                f"formation “{f.id}”: category_positions and position_codes disagree about who lines up"
            )
    stages.append(CheckStage("legality", CHECK_ORDER[4][1], not errors,
                             errors=tuple(errors), notes=tuple(notes)))

    # 6. donor-header rule -------------------------------------------------------
    errors, notes = [], []
    for p in pack.plays:
        flags = p.play_flags if p.play_flags is not None else p.donor.flags
        if p.play_type == "defense":
            try:
                validate_defense_pack_play(p, book, body)
            except (ValueError, ValidationError) as exc:
                errors.append(f"play {p.id}: {exc}")
            continue
        if flags is None or ((flags >> 6) & 7) != 0:
            continue
        if p.donor.flags is None or p.donor.signature is None:
            errors.append(
                f"play “{p.id}”: the donor's header and QB shape are unrecorded, so the "
                "donor-header rule cannot be checked offline"
            )
            continue
        if p.donor.flags & lib.PLAY_FLAG_SPECIAL:
            errors.append(
                f"play “{p.id}”: donor {p.donor.index} (“{p.donor.name}”) is a special "
                "(Take Knee / Spike / Hail Mary); reference_play_for never picks one"
            )
        qb_chain = p.assignments[0]
        if qb_chain is None:
            continue
        authored = SIGNATURE_CLASS.get(lib.qb_signature(qb_chain))
        donor_class = SIGNATURE_CLASS.get(p.donor.signature)
        if donor_class is None:
            errors.append(
                f"play “{p.id}”: donor {p.donor.index} (“{p.donor.name}”) has QB shape "
                f"{p.donor.signature!r}, which is not a shape reference_play_for returns"
            )
        elif authored is not None and donor_class != authored:
            errors.append(
                f"play “{p.id}”: the play is a {authored} but its donor “{p.donor.name}” is a "
                f"{donor_class} — take the donor from reference_play_for, not the book's first play"
            )
        if book is not None and body is not None and (
            book_fingerprint(body) == pack.base.book_fingerprint
        ):
            if not 0 <= p.donor.index < len(book.plays):
                errors.append(f"play “{p.id}”: donor {p.donor.index} is outside this book")
                continue
            actual_flags, chains = lib.play_chains(body, p.donor.index)
            if actual_flags != p.donor.flags:
                errors.append(
                    f"play “{p.id}”: donor {p.donor.index} carries header 0x{actual_flags:08x} in this "
                    f"book, not the recorded 0x{p.donor.flags:08x}"
                )
            actual_signature = lib.qb_signature(chains[0][1])
            if actual_signature != p.donor.signature:
                errors.append(
                    f"play “{p.id}”: donor {p.donor.index} is a {actual_signature} in this book, "
                    f"not the recorded {p.donor.signature}"
                )
    for f in pack.formations:
        if book is not None and not 0 <= f.donor.index < len(book.formations):
            errors.append(f"formation “{f.id}”: donor {f.donor.index} is outside this book")
    if not errors:
        notes.append("every donor is a stock play of the same shape and class")
    stages.append(CheckStage("donor", CHECK_ORDER[5][1], not errors,
                             errors=tuple(errors), notes=tuple(notes)))

    # 7. dry compile -------------------------------------------------------------
    if resource is None:
        stages.append(CheckStage("compile", CHECK_ORDER[6][1], True, True,
                                 notes=("no book body supplied — run the check again with --book "
                                        "or --image to compile it for real",)))
    else:
        errors, notes = [], []
        try:
            compiled = apply_pack_to_resource(resource, pack, asset_id=asset_id)
        except Exception as exc:  # noqa: BLE001 - every failure is reported, never raised
            errors.append(str(exc))
        else:
            report = compiled.report
            notes.append(
                f"compiled and reparsed: {report['new_formation_count']} formations, "
                f"{report['new_play_count']} plays, {report['new_node_count']} nodes, "
                f"{compiled.changed_byte_count:,} bytes changed"
            )
            totals = {**totals, "compiled_formations": report["new_formation_count"],
                      "compiled_plays": report["new_play_count"],
                      "compiled_nodes": report["new_node_count"]}
        stages.append(CheckStage("compile", CHECK_ORDER[6][1], not errors,
                                 errors=tuple(errors), notes=tuple(notes)))

    return PackCheck(tuple(stages), totals)


def _book_assignments(play: PackPlay, flags: int, body: bytes) -> tuple[list[tuple[int, list[bytes]]], str | None]:
    """Validator input for a play that keeps some donor chains: the donor's chains
    from the book, with the authored slots replaced."""

    if not 0 <= play.donor.index < PLAY_CAPACITY:
        return [], f"donor {play.donor.index} is outside the book"
    try:
        _donor_flags, donor_chains = lib.play_chains(body, play.donor.index)
    except Exception as exc:  # noqa: BLE001
        return [], f"could not read donor {play.donor.index}: {exc}"
    assignments: list[tuple[int, list[bytes]]] = [
        (desc, list(nodes)) for desc, nodes in donor_chains
    ]
    for slot, chain in enumerate(play.assignments):
        if chain is None:
            continue
        try:
            nodes = codec.encode_chain(chain, donor_chains[slot][1])
        except ValueError as exc:
            return [], f"slot {slot}: {exc}"
        assignments[slot] = (assignments[slot][0], [n.to_bytes() for n in nodes])
    for slot, chain in enumerate(play.assignments):
        if chain is None:
            continue
        try:
            desc = codec.build_descriptor(flags, assignments, slot, donor_chains[slot][0] >> 24)
        except ValueError as exc:
            return [], f"slot {slot}: {exc}"
        assignments[slot] = (desc, assignments[slot][1])
    return assignments, None


def _link_target_index(pack: PlaybookPack, target: object, book: Nfl2k5Playbook | None) -> int | None:
    if isinstance(target, int) and not isinstance(target, bool):
        return target
    formation = pack.formations_by_id.get(str(target))
    if formation is None:
        return None
    if formation.replace_index is not None:
        return formation.replace_index
    if book is None:
        return None
    appended = [f for f in pack.formations if f.replace_index is None]
    return len(book.formations) + appended.index(formation)


# ---------------------------------------------------------------------------------------------
# Writer requests / dry compile
# ---------------------------------------------------------------------------------------------

def pack_requests(
    pack: PlaybookPack, asset_id: str, book: Nfl2k5Playbook | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The three request-row lists ``compile_formation_play_creations`` consumes.

    Appended formations/plays land in pack order, which is the order the writer
    assigns new indices in, so a play's ``link_formation`` resolves exactly."""

    formation_rows = [f.request_mapping(asset_id) for f in pack.formations]
    play_rows = [p.request_mapping(asset_id) for p in pack.plays]
    link_rows: list[dict[str, Any]] = []
    appended_plays = [p for p in pack.plays if p.replace_index is None]
    base_plays = len(book.plays) if book is not None else pack.base.donor_play_count
    for play in pack.plays:
        if play.link_formation is None:
            continue
        formation_index = _link_target_index(pack, play.link_formation, book)
        if formation_index is None:
            raise PlaybookPackError(
                f"play “{play.id}” lists itself in formation “{play.link_formation}”, which cannot be resolved."
            )
        play_index = (
            play.replace_index if play.replace_index is not None
            else base_plays + appended_plays.index(play)
        )
        if play.option_intent and book is not None:
            links = [l for l in book.formations[formation_index].play_links if l.play_index == play_index]
            if not links:
                raise PlaybookPackError("Option replacement must already belong to its native formation menu")
            if play.link_group is not None and any(l.group != play.link_group for l in links):
                raise PlaybookPackError("Option presets preserve existing audible groups")
            continue
        row: dict[str, Any] = {
            "asset_id": asset_id, "formation_index": formation_index, "play_index": play_index,
        }
        if play.link_group is not None:
            row["group"] = play.link_group
        link_rows.append(row)
    return formation_rows, play_rows, link_rows


def apply_pack_to_resource(resource: bytes, pack: PlaybookPack, *, asset_id: str = "pack-apply"):
    """Compile one pack against one raw PLAY resource (wrapper + body)."""

    from .nfl2k5_formation_play_writer import compile_formation_play_creations

    if len(resource) != RESOURCE_SIZE:
        raise PlaybookPackError(
            f"A PLAY resource is {RESOURCE_SIZE} bytes (0x20 wrapper + 0x13390 body); this is {len(resource)}."
        )
    book = parse_playbook_resource(resource, asset_id=asset_id)
    body = resource[RESOURCE_HEADER_SIZE:]
    if any(p.play_type == "defense" for p in pack.plays):
        if book_fingerprint(body) != pack.base.book_fingerprint:
            raise PlaybookPackError("Defense source fingerprint changed; retarget and review before compiling")
        for p in pack.plays:
            if p.play_type == "defense":
                validate_defense_pack_play(p, book, body)
    if any(p.option_intent for p in pack.plays):
        if book_fingerprint(body) != pack.base.book_fingerprint:
            raise PlaybookPackError("Option source fingerprint changed; regenerate against the intended test fixture")
        if pack.formations or any(p.replace_index is None for p in pack.plays):
            raise PlaybookPackError("Option packs keep native formations and replace existing plays only")
    formation_rows, play_rows, link_rows = pack_requests(pack, asset_id, book)
    return compile_formation_play_creations(resource, formation_rows, play_rows, link_rows)


# ---------------------------------------------------------------------------------------------
# Retargeting (indices re-resolved BY NAME)
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolution:
    entry_id: str
    kind: str                 # "formation" | "play"
    field: str                # "replace" | "donor"
    index: int | None
    name: str
    how: str                  # "name" | "index" | "ranked" | "reference" | "unresolved"
    detail: str = ""


#: Operands that name another assignment slot, and when they mean it.  A retarget can
#: permute the eleven slots (a stock personnel group in the target book may order its
#: skill players differently), so the chains move with the players *and* every slot
#: reference inside them is renumbered -- otherwise the tight end runs the split end's
#: route and a handoff points at nobody.
SLOT_OPERANDS: Mapping[int, tuple[int, Callable[[Sequence[float]], bool] | None]] = {
    0x0E: (5, lambda vals: bool(vals[4] or vals[6] or vals[7])),                 # friendly exchange partner ONLY
    0x02: (0, None),                                          # Snap To
    0x13: (0, None),                                          # Handoff To
    0x14: (0, None),                                          # Fake Handoff To
    0x15: (5, lambda vals: int(vals[0]) == 2),                # Move: follow slot (mode 2)
    0x18: (5, lambda vals: int(vals[0]) == 2),
    0x1A: (3, lambda vals: int(vals[5]) == 0),     # Conditional: the slot it reads
}


def permute_assignments(
    assignments: Sequence[Any], order: Sequence[int]
) -> tuple[Any, ...]:
    """Re-slot eleven chains for a new slot order (``new[s] = old[order[s]]``).

    Every operand that names a slot is renumbered through the inverse map, so a
    handoff still points at the back who takes it."""

    if len(order) != SLOT_COUNT or sorted(order) != list(range(SLOT_COUNT)):
        raise PlaybookPackError("a slot order needs eleven entries")
    inverse = [0] * SLOT_COUNT
    for new_slot, old_slot in enumerate(order):
        inverse[old_slot] = new_slot
    out: list[Any] = []
    for new_slot in range(SLOT_COUNT):
        chain = assignments[order[new_slot]]
        if chain is None:
            out.append(None)
            continue
        nodes = []
        for node in chain:
            op, vals = node[:2]
            fresh = list(vals)
            rule = SLOT_OPERANDS.get(op)
            if rule is not None:
                index, applies = rule
                if index < len(fresh) and (applies is None or applies(fresh)):
                    value = int(fresh[index])
                    if 0 <= value < SLOT_COUNT:
                        fresh[index] = float(inverse[value])
            nodes.append((op, tuple(fresh), *node[2:]))
        out.append(tuple(nodes))
    return tuple(out)


def _match_by_name(candidates: Sequence[tuple[int, str]], names: Sequence[str], wanted: str) -> int | None:
    """The first ranked candidate whose book name equals ``wanted`` (case-folded)."""

    if not wanted:
        return None
    target = wanted.casefold()
    for index, _why in candidates:
        if 0 <= index < len(names) and names[index].casefold() == target:
            return index
    return None


def retarget_pack(
    pack: PlaybookPack, team: str, book: Nfl2k5Playbook, body: bytes
) -> tuple[PlaybookPack, tuple[Resolution, ...]]:
    """Point every entry at ``book``'s own indices.

    Replace targets are re-resolved **by name** through
    ``suggest_formations_to_replace`` / ``suggest_plays_to_replace``; the stored
    index is only kept when the book's entry at that index carries the same name.
    Failing both, the highest-ranked unused suggestion is taken and the resolution
    is reported as ``ranked`` so the plan table can show it.

    Play donors are re-derived with ``reference_play_for`` on the target book (a
    donor supplies the header family the validator checks, so it cannot be a bare
    index), and the header flags are re-stamped from it."""

    if any(p.option_intent for p in pack.plays):
        return retarget_option_pack(pack, team, book, body)
    if any(p.play_type == "defense" for p in pack.plays):
        return retarget_defense_pack(pack, team, book, body)
    formation_names = [f.name for f in book.formations]
    play_names = [p.name for p in book.plays]
    resolutions: list[Resolution] = []
    used_f: set[int] = set()
    used_p: set[int] = set()

    new_formations: list[PackFormation] = []
    slot_orders: dict[str, list[int]] = {}
    claimed: dict[int, Sequence[int]] = {}
    for f in pack.formations:
        plan = lib.resolve_personnel(book, body, list(f.position_codes), claimed)
        claimed[plan.category_index] = plan.codes
        ranked = [(i, why) for i, why in lib.suggest_formations_to_replace(book, body, plan.category_index)]
        replace_index, how, detail = _resolve_target(
            f.replace_index, f.replace_name, ranked, formation_names, used_f
        )
        if replace_index is not None:
            used_f.add(replace_index)
        donor_index = lib.donor_for_personnel(book, body, plan)
        if f.donor.name:
            by_name = next((i for i, n in enumerate(formation_names)
                            if n.casefold() == f.donor.name.casefold()), None)
            if by_name is not None:
                donor_index = by_name
        resolutions.append(Resolution(f.id, "formation", "replace", replace_index,
                                      formation_names[replace_index] if replace_index is not None else "",
                                      how, detail))
        resolutions.append(Resolution(f.id, "formation", "donor", donor_index,
                                      formation_names[donor_index], "name" if f.donor.name else "personnel"))
        slot_orders[f.id] = list(plan.slot_order)
        new_formations.append(_dc_replace(
            f,
            replace_index=replace_index,
            replace_name=formation_names[replace_index] if replace_index is not None else "",
            donor=PackDonor(donor_index, formation_names[donor_index]),
            category_index=plan.category_index,
            category_positions=(tuple(plan.category_positions)
                                if plan.category_positions is not None else None),
            position_codes=tuple(plan.codes),
            slot_positions=tuple(f.slot_positions[plan.slot_order[s]] for s in range(SLOT_COUNT)),
        ))

    by_id = {f.id: nf for f, nf in zip(pack.formations, new_formations)}
    new_plays: list[PackPlay] = []
    for p in pack.plays:
        donor_index, flags = lib.reference_play_for(book, body, p.play_type, p.concept or None)
        _dflags, dchains = lib.play_chains(body, donor_index)
        signature = lib.qb_signature(dchains[0][1])
        link_formation = p.link_formation
        menu_source = None
        if isinstance(link_formation, str) and link_formation in by_id:
            target = by_id[link_formation]
            menu_source = target.replace_index if target.replace_index is not None else target.donor.index
        elif isinstance(link_formation, int) and 0 <= link_formation < len(book.formations):
            menu_source = link_formation
        ranked = (
            [(i, why) for i, why in lib.suggest_plays_to_replace(book, menu_source)]
            if menu_source is not None else []
        )
        if not ranked:
            ranked = [(i, "stock play") for i in lib.offense_plays(book)]
        replace_index, how, detail = _resolve_target(
            p.replace_index, p.replace_name, ranked, play_names, used_p
        )
        if replace_index is not None:
            used_p.add(replace_index)
        resolutions.append(Resolution(p.id, "play", "replace", replace_index,
                                      play_names[replace_index] if replace_index is not None else "",
                                      how, detail))
        resolutions.append(Resolution(p.id, "play", "donor", donor_index, play_names[donor_index],
                                      "reference", f"reference_play_for({p.play_type})"))
        order = slot_orders.get(str(p.link_formation)) if isinstance(p.link_formation, str) else None
        assignments = p.assignments
        if order is not None and order != list(range(SLOT_COUNT)):
            # the target book's personnel group lines the skill players up in another
            # order, so the chains follow their players and their slot references with them
            assignments = permute_assignments(p.assignments, order)
            resolutions.append(Resolution(
                p.id, "play", "slots", None, "", "permuted",
                f"the assignments follow “{p.link_formation}”'s new slot order {order[6:]}",
            ))
        new_plays.append(_dc_replace(
            p,
            assignments=assignments,
            replace_index=replace_index,
            replace_name=play_names[replace_index] if replace_index is not None else "",
            donor=PackDonor(donor_index, play_names[donor_index], flags, signature),
            play_flags=flags,
        ))

    retargeted = PlaybookPack(
        _dc_replace(pack.book, team=team, targets=()),
        PackBase(book_fingerprint(body), len(book.formations), len(book.plays), book.node_count,
                 pack.base.xiso_sha256),
        tuple(new_formations),
        tuple(new_plays),
        pack.schema,
    )
    return retargeted, tuple(resolutions)


def _resolve_target(
    stored_index: int | None,
    stored_name: str,
    ranked: Sequence[tuple[int, str]],
    names: Sequence[str],
    used: set[int],
) -> tuple[int | None, str, str]:
    if stored_index is None:
        return None, "append", "added as new (grows the book)"
    by_name = _match_by_name(ranked, names, stored_name)
    if by_name is None and stored_name:
        by_name = next((i for i, n in enumerate(names)
                        if n.casefold() == stored_name.casefold() and i not in used), None)
    if by_name is not None and by_name not in used:
        return by_name, "name", f"“{names[by_name]}” by name"
    if (0 <= stored_index < len(names) and stored_index not in used
            and stored_name and names[stored_index].casefold() == stored_name.casefold()):
        return stored_index, "index", f"index {stored_index} still carries “{stored_name}”"
    for index, why in ranked:
        if index not in used and 0 <= index < len(names):
            return index, "ranked", (
                f"this book has no “{stored_name}”; replacing “{names[index]}” instead ({why})"
                if stored_name else f"replacing “{names[index]}” ({why})"
            )
    return None, "unresolved", f"nothing left to replace for “{stored_name}”"


# ---------------------------------------------------------------------------------------------
# Export from a project's staged rows
# ---------------------------------------------------------------------------------------------

#: QB-chain shape -> (play_type, scheme) for an exported row.  ``reference_play_for``
#: only distinguishes a draw by its scheme, so a draw carries it explicitly.
_SIGNATURE_PLAY_TYPE: Mapping[str, tuple[str, str]] = {
    "pass": ("pass", ""), "pa_pass": ("pa_pass", ""), "run": ("run", ""),
    "draw": ("run", "Draw"), "qb_run": ("keeper", ""),
}


def pack_from_staged_rows(
    *,
    team: str,
    book: Nfl2k5Playbook,
    body: bytes,
    formation_rows: Iterable[Mapping[str, object]] = (),
    play_rows: Iterable[Mapping[str, object]] = (),
    link_rows: Iterable[Mapping[str, object]] = (),
    name: str = "",
    author: str = "",
    version: str = "1.0.0",
    license: str = "CC0-1.0",
    notes: str = "",
    xiso_sha256: str = "",
) -> PlaybookPack:
    """Turn one book's staged ``formation_creates`` / ``play_creates`` /
    ``formation_links`` rows (the ``provider_edit`` mappings ``.2k5mod`` stores)
    into a shareable pack."""

    from .nfl2k5_formation_play_writer import (
        formation_request_from_mapping, link_request_from_mapping, play_request_from_mapping,
    )

    # Appended entries take their Build index from the project archive's own row order
    # (asset, kind, canonical JSON), so the export has to walk the rows in that order or a
    # link would name the wrong new play.
    def _build_order(row: Mapping[str, object]) -> tuple[str, str, str]:
        return (str(row.get("asset_id", "")), str(row.get("kind", "")),
                json.dumps(dict(row), sort_keys=True, default=list))

    formations: list[PackFormation] = []
    used_ids: set[str] = set()
    formation_ids_by_index: dict[int, str] = {}
    appended_formation_ids: list[str] = []
    for row in sorted(formation_rows, key=_build_order):
        request = formation_request_from_mapping(dict(row))
        custom = request.custom_name or book.formations[request.donor_formation_index].name
        pack_id = _unique_id(custom, used_ids)
        if request.slot_positions is None:
            raise PlaybookPackError(
                f"“{custom}” is a plain clone with no geometry; a pack carries designed formations only."
            )
        category_index = request.category_index
        if category_index is None:
            category_index = lib.formation_category(body, request.donor_formation_index)
        codes = (list(request.category_positions) if request.category_positions is not None
                 else lib.category_positions(body, category_index))
        formations.append(PackFormation(
            pack_id,
            _name(custom, f"formation “{custom}”"),
            tuple((int(x), int(z)) for x, z in request.slot_positions),
            tuple(codes),
            PackDonor(request.donor_formation_index,
                      book.formations[request.donor_formation_index].name),
            request.replace_index,
            book.formations[request.replace_index].name if request.replace_index is not None else "",
            request.category_index,
            tuple(request.category_positions) if request.category_positions is not None else None,
        ))
        if request.replace_index is not None:
            formation_ids_by_index[request.replace_index] = pack_id
        else:
            appended_formation_ids.append(pack_id)

    for offset, pack_id in enumerate(appended_formation_ids):
        formation_ids_by_index[len(book.formations) + offset] = pack_id

    staged_links: dict[int, tuple[int, int | None]] = {}
    for row in link_rows:
        request = link_request_from_mapping(dict(row))
        staged_links[request.play_index] = (request.formation_index, request.group)

    plays: list[PackPlay] = []
    appended = 0
    for row in sorted(play_rows, key=_build_order):
        request = play_request_from_mapping(dict(row))
        custom = request.custom_name or book.plays[request.donor_play_index].name
        pack_id = _unique_id(custom, used_ids)
        donor_flags, donor_chains = lib.play_chains(body, request.donor_play_index)
        signature = lib.qb_signature(donor_chains[0][1])
        assignments = request.assignments or (None,) * SLOT_COUNT
        qb_chain = assignments[0]
        play_type, scheme = _SIGNATURE_PLAY_TYPE.get(
            lib.qb_signature(qb_chain) if qb_chain is not None else signature, ("pass", "")
        )
        if request.option_intent:
            scheme = request.option_intent['preset']
            play_type = 'pass' if scheme == lib.OPTION_PRESETS[2] else 'run'
        play_index = (request.replace_index if request.replace_index is not None
                      else len(book.plays) + appended)
        if request.replace_index is None:
            appended += 1
        link_formation: str | int | None = None
        link_group: int | None = None
        if play_index in staged_links:
            formation_index, link_group = staged_links[play_index]
            link_formation = formation_ids_by_index.get(formation_index, formation_index)
        if request.option_intent:
            # These replacements already inhabit their native menus. Keeping
            # this empty also avoids staging duplicate links through the facade.
            link_formation = link_group = None
        defense = (donor_flags >> 6) & 7 == 1
        defense_fi = next((f.index for f in book.formations if any(l.play_index == request.donor_play_index for l in f.play_links)), None)
        if isinstance(link_formation, int):
            defense_fi = link_formation
        if isinstance(link_formation, str):
            defense_fi = next(f.donor.index for f in formations if f.id == link_formation)
        if defense:
            play_type = "defense"
            signature = lib.defense_signature(body, request.donor_play_index)
        plays.append(PackPlay(
            pack_id,
            _name(custom, f"play “{custom}”"),
            play_type,
            tuple(
                None if chain is None else tuple((n[0], tuple(float(v) for v in n[1]), *n[2:]) for n in chain)
                for chain in assignments
            ),
            PackDonor(request.donor_play_index, book.plays[request.donor_play_index].name,
                      donor_flags, signature),
            request.play_flags if request.play_flags is not None else donor_flags,
            request.replace_index,
            book.plays[request.replace_index].name if request.replace_index is not None else "",
            scheme,
            link_formation,
            link_group,
            book.formations[defense_fi].name if defense and defense_fi is not None else "",
            lib.defense_donors(book, body, defense_fi)[0] if defense and defense_fi is not None else None,
            lib.defense_component([chain if chain is not None else lib.decoded_chains(body, request.donor_play_index)[s]
                                   for s, chain in enumerate(assignments)]) if defense else "",
            request.spy_slots,
            option_intent=request.option_intent,
        ))

    return PlaybookPack(
        PackBook(team, name or f"{team} playbook pack", author or "unknown", version, license,
                 (), notes),
        PackBase(book_fingerprint(body), len(book.formations), len(book.plays), book.node_count,
                 xiso_sha256),
        tuple(formations),
        tuple(plays),
        OPTION_SCHEMA if any(p.option_intent or any(c and any(len(n) == 3 for n in c) for c in p.assignments) for p in plays) else DEFENSE_SCHEMA if any(p.play_type == "defense" for p in plays) else SCHEMA,
    )


def _unique_id(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:56] or "entry"
    if not base[0].isalnum():
        base = f"e{base}"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate


# ---------------------------------------------------------------------------------------------
# Install plan (the UI's table + budget bar; pure data so it tests headless)
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanRow:
    entry_id: str
    kind: str                # "Formation" | "Play"
    name: str
    replaces: str
    status: str              # "ok" | "conflict" | "over budget" | "retargeted"
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {"id": self.entry_id, "kind": self.kind, "name": self.name,
                "replaces": self.replaces, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class InstallPlan:
    team: str
    rows: tuple[PlanRow, ...]
    totals: Mapping[str, Any]
    blocked: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.blocked and all(row.status in ("ok", "retargeted") for row in self.rows)

    def budget_line(self) -> str:
        t = self.totals
        return (f"plays {t['plays']}/{t['play_capacity']}, "
                f"formations {t['formations']}/{t['formation_capacity']}, "
                f"nodes {t['nodes']}/{t['node_capacity']}")


def install_plan(
    pack: PlaybookPack,
    book: Nfl2k5Playbook,
    body: bytes,
    *,
    team: str | None = None,
    staged_formation_targets: Iterable[int] = (),
    staged_play_targets: Iterable[int] = (),
    resolutions: Sequence[Resolution] = (),
) -> InstallPlan:
    """One row per entry: what it replaces and whether it is OK, in conflict with a
    staged edit, or over budget."""

    taken_f = set(staged_formation_targets)
    taken_p = set(staged_play_targets)
    totals = budget_totals(pack, book)
    by_entry = {(r.entry_id, r.field): r for r in resolutions}
    rows: list[PlanRow] = []
    over_f = totals["formations"] > FORMATION_CAPACITY
    over_p = totals["plays"] > PLAY_CAPACITY
    over_n = totals["nodes"] > NODE_CAPACITY

    for f in pack.formations:
        res = by_entry.get((f.id, "replace"))
        if f.replace_index is None:
            replaces, status, detail = "add as new", ("over budget" if over_f else "ok"), (
                f"{totals['formations']} formations after this (cap {FORMATION_CAPACITY})"
            )
        elif f.replace_index in taken_f:
            replaces = _entry_name(book.formations, f.replace_index)
            status, detail = "conflict", (
                f"formation {f.replace_index} (“{replaces}”) is already replaced by a staged edit"
            )
        else:
            replaces = _entry_name(book.formations, f.replace_index)
            status = "retargeted" if res is not None and res.how == "ranked" else "ok"
            detail = res.detail if res is not None else f"replaces formation {f.replace_index}"
            if over_f:
                status = "over budget"
        rows.append(PlanRow(f.id, "Formation", f.custom_name, replaces, status, detail))

    for p in pack.plays:
        res = by_entry.get((p.id, "replace"))
        if p.replace_index is None:
            replaces, status, detail = "add as new", ("over budget" if over_p else "ok"), (
                f"{totals['plays']} plays after this (cap {PLAY_CAPACITY})"
            )
        elif p.replace_index in taken_p:
            replaces = _entry_name(book.plays, p.replace_index)
            status, detail = "conflict", (
                f"play {p.replace_index} (“{replaces}”) is already replaced by a staged edit"
            )
        else:
            replaces = _entry_name(book.plays, p.replace_index)
            status = "retargeted" if res is not None and res.how == "ranked" else "ok"
            detail = res.detail if res is not None else f"replaces play {p.replace_index}"
            if over_p:
                status = "over budget"
        if over_n and status == "ok":
            status, detail = "over budget", (
                f"{totals['nodes']} nodes after this (pool holds {NODE_CAPACITY})"
            )
        rows.append(PlanRow(p.id, "Play", p.custom_name, replaces, status, detail))

    blocked: list[str] = []
    unresolved = [r for r in resolutions if r.how == "unresolved"]
    for r in unresolved:
        blocked.append(f"{r.kind} “{r.entry_id}”: {r.detail}")
    return InstallPlan(team or pack.book.team, tuple(rows), totals, tuple(blocked))


def _entry_name(entries: Sequence[Any], index: int) -> str:
    return entries[index].name if 0 <= index < len(entries) else f"#{index}"


@dataclass(frozen=True)
class PackPreview:
    """Everything the install dialog shows for one target team: the pack as it
    will actually be applied (retargeted when the team is not the authored one),
    the plan table, the budget totals and the full offline check."""

    team: str
    pack: PlaybookPack
    plan: InstallPlan
    check: PackCheck
    resolutions: tuple[Resolution, ...] = ()
    retargeted: bool = False

    @property
    def ok(self) -> bool:
        return self.plan.ok and self.check.ok


def preview_pack(
    pack: PlaybookPack,
    team: str,
    book: Nfl2k5Playbook,
    body: bytes,
    *,
    resource: bytes | None = None,
    staged_formation_targets: Iterable[int] = (),
    staged_play_targets: Iterable[int] = (),
) -> PackPreview:
    """Retarget when needed, then build the plan table and run the check."""

    resolutions: tuple[Resolution, ...] = ()
    use = pack
    retargeted = False
    if team != pack.book.team or book_fingerprint(body) != pack.base.book_fingerprint:
        use, resolutions = retarget_pack(pack, team, book, body)
        retargeted = True
    check = check_pack(use, book, body, resource=resource, asset_id=f"book:{team}")
    plan = install_plan(
        use, book, body, team=team,
        staged_formation_targets=staged_formation_targets,
        staged_play_targets=staged_play_targets,
        resolutions=resolutions,
    )
    return PackPreview(team, use, plan, check, resolutions, retargeted)


# ---------------------------------------------------------------------------------------------
# Disc images (the Build step)
# ---------------------------------------------------------------------------------------------

def _outer_image():
    import importlib
    import sys

    tools = Path(__file__).resolve().parents[2] / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module("nfl2k5_playbook_position_recode")


def apply_packs_to_archive(
    archive: Any,
    packs: Sequence[tuple[str, PlaybookPack]],
    progress: Callable[[str], None] | None = None,
    book_entries: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Install loaded packs into an open, writable ``vc_53450030`` archive.

    ``archive`` needs the three members the outer reader already provides:
    ``entries``, ``read_entry(index)`` and ``write(virtual_offset, payload)``.
    Every write is read back before the next one."""

    say = progress or (lambda _m: None)
    if book_entries is None:
        book_entries = _outer_image().BOOK_ENTRIES
    applied: list[dict[str, Any]] = []
    pending: dict[int, bytes] = {}
    originals: dict[int, bytes] = {}
    for source, pack in packs:
        targets = pack.book.resolved_targets()
        entry_report: list[dict[str, Any]] = []
        for team in targets:
            index = book_entries.get(team)
            if index is None or index >= len(archive.entries):
                raise PlaybookPackError(f"This image has no playbook for “{team}”.")
            entry = archive.entries[index]
            if entry.size != RESOURCE_SIZE:
                raise PlaybookPackError(
                    f"{team}: outer entry {index} is 0x{entry.size:x} bytes, not a playbook"
                )
            say(f"Installing “{pack.book.name}” into {team}")
            if index not in originals:
                originals[index] = archive.read_entry(index)
            before = pending.get(index, originals[index])
            book = parse_playbook_resource(before, asset_id=f"book:{team}")
            body = before[RESOURCE_HEADER_SIZE:]
            use = pack
            resolved: tuple[Resolution, ...] = ()
            if team != pack.book.team or book_fingerprint(body) != pack.base.book_fingerprint:
                use, resolved = retarget_pack(pack, team, book, body)
            compiled = apply_pack_to_resource(before, use, asset_id=f"book:{team}")
            if compiled.replacement[:RESOURCE_HEADER_SIZE] != before[:RESOURCE_HEADER_SIZE]:
                raise PlaybookPackError(f"{team}: the PLAY resource wrapper changed")
            pending[index] = compiled.replacement
            entry_report.append({
                "team": team, "outer_index": index,
                "retargeted": bool(resolved),
                "retargeted_entries": sum(1 for r in resolved if r.how == "ranked"),
                "formations": compiled.report["new_formation_count"],
                "plays": compiled.report["new_play_count"],
                "nodes": compiled.report["new_node_count"],
                "changed_bytes": compiled.changed_byte_count,
            })
        applied.append({
            "pack": source,
            "name": pack.book.name,
            "author": pack.book.author,
            "version": pack.book.version,
            "license": pack.book.license,
            "authored_on": pack.book.team,
            "book_fingerprint": pack.base.book_fingerprint,
            "formations": len(pack.formations),
            "plays": len(pack.plays),
            "books": entry_report,
        })
    # Every target and cumulative pool budget is proved before the first write.
    # Keep this preflight separate from the writer so a later/smaller book cannot
    # leave the earlier books partially installed.
    for index, expected in originals.items():
        if archive.read_entry(index) != expected:
            raise PlaybookPackError(f"Book {index} changed during pack preflight")
    for index, payload in pending.items():
        if archive.write(archive.entries[index].virtual_offset, payload) != len(payload):
            raise PlaybookPackError(f"Book {index}: short write of the playbook")
        if archive.read_entry(index) != payload:
            raise PlaybookPackError(f"Book {index}: read-back of the playbook differs")
    return {"status": "applied", "packs": applied}


def apply_packs_to_image(
    path: Path | str,
    packs: Sequence[Path | str],
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Apply every ``.2k5book`` to the team books of the disc image at ``path`` (a COPY).

    Each pack names the team it was authored on; ``book.targets`` may name others
    or ``"ALL"``.  Every target other than the authored team is retargeted first,
    so replace indices are resolved by name inside that team's own book."""

    recode = _outer_image()
    loaded = [(Path(p).name, load_pack(p)) for p in packs]
    with recode.OuterImage(path, writable=True) as archive:
        return apply_packs_to_archive(archive, loaded, progress, recode.BOOK_ENTRIES)


__all__ = [
    "ALL_TEAMS", "BUDGET_LIMITS", "CHECK_ORDER", "CheckStage", "InstallPlan", "NODE_CAPACITY",
    "PACK_EXTENSION", "PLAY_TYPES", "PackBase", "PackBook", "PackCheck", "PackDonor",
    "PackFormation", "PackPlay", "PackPreview", "PlanRow", "PlaybookPack", "PlaybookPackError",
    "Resolution",
    "SCHEMA", "TEAM_BOOKS", "apply_pack_to_resource", "apply_packs_to_archive",
    "apply_packs_to_image", "book_fingerprint",
    "budget_totals", "check_pack", "install_plan", "load_pack", "loads_pack", "pack_from_json",
    "pack_from_staged_rows", "pack_requests", "permute_assignments", "preview_pack",
    "retarget_pack", "save_pack",
]


def _spy_slots(value: object) -> tuple[int, ...]:
    from .nfl2k5_formation_play_writer import spy_slots_from
    return spy_slots_from(value)


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise PlaybookPackError(f"{label} must be a Boolean")
    return value


def validate_defense_pack_play(play: PackPlay, book: Nfl2k5Playbook | None, body: bytes | None) -> None:
    flags = play.play_flags if play.play_flags is not None else play.donor.flags
    if flags is None or (flags >> 6) & 7 != 1:
        raise PlaybookPackError("Defense must retain a defensive header")
    if play.donor.flags != flags or not (play.donor.signature or '').startswith('defense/v1:'):
        raise PlaybookPackError("Defense needs its exact donor header and versioned shape signature")
    if play.component not in ('front', 'coverage', 'full') or not play.defense_formation:
        raise PlaybookPackError("Defense needs a formation and component kind")
    for chain in play.assignments:
        if chain is not None:
            codec.validate_defense_operands(chain)
    if all(c is not None for c in play.assignments) and lib.defense_component(play.assignments) != play.component:
        raise PlaybookPackError("Defense component disagrees with the active assignments")
    if play.preset_recipe and (play.concept not in lib.MODERN_DEFENSE_PRESETS or play.spy_slots):
        raise PlaybookPackError("Built-in defense recipes must name a core preset without custom spy intent")
    if book is None or body is None:
        return
    if not 0 <= play.donor.index < len(book.plays):
        raise PlaybookPackError("Defense donor is outside this book")
    if lib.defense_signature(body, play.donor.index) != play.donor.signature:
        raise PlaybookPackError("Defense donor signature changed")
    fi = next((f.index for f in book.formations if f.name == play.defense_formation), None)
    if fi is None:
        raise PlaybookPackError("Defense formation is missing")
    lib.defense_personnel(book, body, fi)
    if play.front_index is None or not 0 <= play.front_index < len(book.plays):
        raise PlaybookPackError("Defense must identify its preview front")
    front = lib.decoded_chains(body, play.front_index)
    if lib.defense_component(front) != 'front':
        raise PlaybookPackError("Defense preview front is not a front component")
    if not any(l.play_index == play.front_index for l in book.formations[fi].play_links):
        raise PlaybookPackError("Defense preview front is absent from the formation menu")
    if play.preset_recipe:
        expected = lib.make_defense_design(book, body, fi, play.concept)
        if _freeze_chains(expected.chains) != play.assignments:
            raise PlaybookPackError("Preset assignments changed; export as a custom defense before retargeting")


def _freeze_chains(chains: Sequence) -> tuple:
    return tuple(None if c is None else tuple((int(op), tuple(float(v) for v in vals)) for op, vals in c)
                 for c in chains)


def modern_defense_pack(book: Nfl2k5Playbook, body: bytes, team: str | None = None) -> PlaybookPack:
    """Build the SOFTDRINK recipe from this book's native defense donors.

    Core books replace ten coverage records, preserving all category rows,
    formation geometry, package permutations, membership masks and menu words.
    Editor/PRACTICE append ten calls to their 4-3 menu, preserving drill records.
    """
    team = team or book.book_name
    if team not in DEFENSE_BOOKS:
        raise PlaybookPackError("Modern defense supports the 37 retail books only")
    fi = next((f.index for f in book.formations if f.name == 'Nickel'), None)
    if fi is None:
        fi = next((f.index for f in book.formations if f.name == '4-3'), None)
    if fi is None:
        raise PlaybookPackError("This book has no supported Nickel or 4-3 donor")
    info = lib.defense_personnel(book, body, fi)
    ftype = lib.formation_record(body, fi).type_code
    candidates = [p.index for p in book.plays_for_formation(fi)
                  if p.family_id == 1 and (p.flags_or_id & 63) == ftype
                  and lib.defense_component(lib.decoded_chains(body, p.index)) == 'coverage']
    candidates = list(dict.fromkeys(candidates))
    append = team in ('Editor', 'PRACTICE')
    if not append and len(candidates) < len(lib.MODERN_DEFENSE_PRESETS):
        raise PlaybookPackError("This book has fewer than ten compatible coverage replacement slots")
    plays = []
    used = set()
    names = ('SD Zero Man', 'SD One High Man', 'SD Two Man', 'SD Two Hard', 'SD Two Soft',
             'SD Three Deep', 'SD Four Deep Spot', 'SD Six Split Field', 'SD Fire Replace Three', 'SD Replace Three')
    if any(p.name in names for p in book.plays):
        raise PlaybookPackError("This book already contains part or all of modern defense; use the unmodified source")
    for ordinal, (preset, name) in enumerate(zip(lib.MODERN_DEFENSE_PRESETS, names)):
        design = lib.make_defense_design(book, body, fi, preset)
        target = None
        if not append:
            target = next((p for p in candidates if p == design.donor_play_index and p not in used),
                          next(p for p in candidates if p not in used))
            used.add(target)
        donor = book.plays[design.donor_play_index]
        plays.append(PackPlay(
            f'sd-defense-{ordinal:02d}', name, 'defense', _freeze_chains(design.chains),
            PackDonor(donor.index, donor.name, donor.flags_or_id, lib.defense_signature(body, donor.index)),
            donor.flags_or_id, target, book.plays[target].name if target is not None else '', preset,
            fi if append else None, 3 if append else None,
            book.formations[fi].name, design.front_index, lib.defense_component(design.chains), (), True,
        ))
    pack = PlaybookPack(
        PackBook(team, 'SOFTDRINK modern defense', 'SOFTDRINK', '1.0.0', 'CC0-1.0', (),
                 f'{lib.DEFENSE_EVIDENCE}. Spot coverages and replacement pressures from native retail donors. '
                 f'{book.formations[fi].name}: personnel row {info["category_index"]}, CPU code {info["category_code"]}. '
                 'Category rows and formation membership stay unchanged. No match-quarters or Palms claim. '
                 + lib.SPY_NOTICE),
        PackBase(book_fingerprint(body), len(book.formations), len(book.plays), book.node_count),
        (), tuple(plays), DEFENSE_SCHEMA,
    )
    totals = budget_totals(pack, book)
    if totals['nodes'] > NODE_CAPACITY or totals['plays'] > PLAY_CAPACITY:
        raise PlaybookPackError("Modern defense exceeds this book's remaining capacity")
    return pack


def retarget_defense_pack(pack: PlaybookPack, team: str, book: Nfl2k5Playbook, body: bytes):
    if all(p.play_type == 'defense' and p.preset_recipe for p in pack.plays) and not pack.formations:
        if len(pack.plays) != 10 or {p.concept for p in pack.plays} != set(lib.MODERN_DEFENSE_PRESETS):
            raise PlaybookPackError("A built-in defense pack must contain all ten core presets")
        fresh = modern_defense_pack(book, body, team)
        return fresh, tuple(Resolution(p.id, 'play', 'donor', p.donor.index, p.donor.name,
                                       'defense', 'Target native front, personnel and partial coverage') for p in fresh.plays)
    # Custom scripts contain slot-specific exchange/receiver semantics. Exact
    # reload is safe; automatic cross-book guesses are not an authoring contract.
    if team == pack.book.team and book_fingerprint(body) == pack.base.book_fingerprint:
        return pack, ()
    raise PlaybookPackError("Custom defense source changed. Re-author against the target's native formation; automatic slot guesses are refused")


def _option_intent(value):
    try:
        return lib.option_intent_from(value)
    except ValueError as exc:
        raise PlaybookPackError(str(exc)) from exc


def option_pack(book: Nfl2k5Playbook, body: bytes, team: str = 'MIN') -> PlaybookPack:
    """Eight calls in a native I menu; only changed chains use pool space.

    Four native strong options share the same grammar, one is weak. Their
    source names identify retail donors awaiting play tests, not copied resources.
    """
    dfi = next((f.index for f in book.formations if f.name == '4-3'), None)
    if dfi is None:
        raise PlaybookPackError('SOFTDRINK option needs the native 4-3 test formation')
    templates = [(f'SD {t}{i} Speed EXPERIMENTAL', lib.OPTION_PRESETS[0], (t, i) == ('NO', 66), 10)
                 for t, i in lib.STOCK_SPEED_OPTIONS]
    templates += [('SD Speed Weak EXPERIMENTAL', lib.OPTION_PRESETS[0], True, 9),
                  ('SD Zone Read EXPERIMENTAL', lib.OPTION_PRESETS[1], False, 10),
                  ('SD RPO EXPERIMENTAL', lib.OPTION_PRESETS[2], False, 10)]
    # Gun packs can replace I Jokers. Select another unchanged I alignment,
    # excluding calls now shared with a gun menu so its scripts survive.
    gun_calls = {l.play_index for f in book.formations
                 if lib.formation_record(body, f.index).qb_alignment == 2 for l in f.play_links}
    candidates = sorted((f for f in book.formations if 'I ' in f.name),
                        key=lambda f: (f.name != 'I Jokers', f.index))
    fi = None
    for f in candidates:
        try:
            lib.make_option_design(book, body, f.index)
        except ValueError:
            continue
        targets = list(dict.fromkeys(l.play_index for l in f.play_links
                   if l.play_index not in gun_calls and book.plays[l.play_index].family_id == 0
                   and not any(n[0] == 26 for n in lib.play_chains(body, l.play_index)[1][0][1])))
        if len(targets) >= len(templates):
            fi = f.index
            break
    if fi is None:
        raise PlaybookPackError('SOFTDRINK option needs a native under-center I formation with eight replacement calls outside gun menus')
    plays = []
    for ordinal, ((name, preset, weak, back), target) in enumerate(zip(templates, targets)):
        d = lib.make_option_design(book, body, fi, preset, weak=weak, back_slot=back,
                                   opponent_formation_index=dfi, read_slot=2 if preset == lib.OPTION_PRESETS[1] else 6,
                                   receiver_slot=7)
        donor_flags, donor_chains = lib.play_chains(body, d.donor_play_index)
        chains = tuple(None if [n.to_bytes() for n in codec.encode_chain(c)] == donor_chains[s][1]
                       else tuple((n[0], tuple(n[1]), *n[2:]) for n in c)
                       for s, c in enumerate(d.chains))
        plays.append(PackPlay(f'option-{ordinal + 1}', name,
            'pass' if preset == lib.OPTION_PRESETS[2] else 'run', chains,
            PackDonor(d.donor_play_index, book.plays[d.donor_play_index].name, donor_flags,
                      lib.qb_signature(donor_chains[0][1])), d.play_flags, target, book.plays[target].name,
            preset, option_intent=d.intent))
    return PlaybookPack(PackBook(team, 'SOFTDRINK option', 'SOFTDRINK', '1.0.0', 'CC0-1.0', (),
        lib.OPTION_NOTICE + ' Five native speed-option recipes plus speed, zone-read and RPO presets. '
        f'Replaces eight {book.formations[fi].name} calls, never appends. The 4-3 fixture is an authoring check only; '
        'use matching defensive personnel in play tests. False/missing target does not guarantee a safe give.'),
        PackBase(book_fingerprint(body), len(book.formations), len(book.plays), book.node_count),
        (), tuple(plays), OPTION_SCHEMA)


def retarget_option_pack(pack: PlaybookPack, team: str, book: Nfl2k5Playbook, body: bytes):
    """Never discard authored edits or guess a different opponent namespace.

    The seed targets MIN only. For a different or previously edited book, call
    option_pack on that book, then review its replacements and test fixture.
    """
    if team == pack.book.team and book_fingerprint(body) == pack.base.book_fingerprint:
        return pack, ()
    raise PlaybookPackError('Option source or team changed. Regenerate the pack against that book and review its native formation, replacements and opponent test fixture')
