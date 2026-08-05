"""User-source-derived text and roster catalog for 2K5 Mod Studio.

The public application ships parsers and constraints, never decoded retail
strings.  This module builds its catalog from the private source cache created
from the user's own XISO.  Only the two already-understood fixed-allocation
ROST edit classes are writable:

* team city/nickname/abbreviation strings; and
* primary-player first/last names, plus the masked jersey-number and
  per-player face-shield fields for both player pools.

Everything else remains searchable/exportable when it has a strict decoder,
or appears as a read-only bank with a concise reason when it does not.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from .errors import ValidationError
from .nfl2k5_safe_text_banks import (
    SAFE_TEXT_PROVIDER_KIND,
    SafeTextAccess,
    SafeTextAsset,
    SafeTextBank,
    SafeTextCatalog,
)

if TYPE_CHECKING:
    from .nfl2k5_source_cache import SourceCache


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_roster  # noqa: E402
from nfl_outer import parse_archive, read_entry_range  # noqa: E402


TEXT_PROJECT_SCHEMA = "2k5_mod_studio_text_replacements/v1"
PACK0_SIZE = 193_710_080
ROSTER_TEAM_PROVIDER_KIND = "roster_team_text"
ROSTER_PLAYER_PROVIDER_KIND = "roster_player_text"
ROSTER_WRAPPER_SIZE = 0x20
PLAYER_STRIDE = 0x54
TEAM_STRIDE = 0x1F4
JERSEY_FIELD = 0x20
JERSEY_MASK = 0x3F8
JERSEY_SHIFT = 3
FACE_SHIELD_MASK = 0x18000
FACE_SHIELD_SHIFT = 15
FACE_SHIELD_CHOICES: tuple[tuple[int, str], ...] = (
    (0, "None"),
    (1, "Clear"),
    (2, "Dark"),
)
TEXT_BANK_KINDS = frozenset({"CRED", "NAME", "ROST", "SITU", "STRG", "TRIV"})
TEAM_TEXT_FIELDS: tuple[tuple[str, int], ...] = (
    ("nickname", 0x104),
    ("abbreviation", 0x108),
    ("asset_code", 0x10C),
    ("city", 0x138),
    ("city_abbreviation", 0x13C),
)
EDITABLE_TEAM_FIELDS = frozenset(
    {"nickname", "abbreviation", "city", "city_abbreviation"}
)
_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")


class TextAccess(str, Enum):
    """A product-facing text capability state."""

    EDITABLE = "editable"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class TextBank:
    bank_id: str
    kind: str
    label: str
    outer_index: int | None
    chunk_index: int | None
    decoded: bool
    access: str
    entry_count: int | None
    reason: str


@dataclass(frozen=True)
class TextAsset:
    asset_id: str
    bank_id: str
    label: str
    value: str
    encoding: str
    allocation_bytes: int
    character_limit: int
    used_utf16_code_units: int
    access: TextAccess
    reason: str
    outer_index: int
    chunk_index: int
    owner_kind: str
    owner_index: int
    field: str
    reference_count: int
    provider_kind: str | None = None
    provider_group_id: str | None = None

    @property
    def editable(self) -> bool:
        return self.access is TextAccess.EDITABLE


@dataclass(frozen=True)
class RosterNumberAsset:
    asset_id: str
    label: str
    value: int
    minimum: int
    maximum: int
    access: TextAccess
    reason: str
    outer_index: int
    player_index: int
    provider_group_id: str
    field: str = "jersey_number"
    choices: tuple[tuple[int, str], ...] = ()

    @property
    def editable(self) -> bool:
        return self.access is TextAccess.EDITABLE

    def display_value(self, value: int | None = None) -> str:
        selected = self.value if value is None else value
        return dict(self.choices).get(selected, str(selected))


@dataclass(frozen=True)
class RosterTeam:
    group_id: str
    outer_index: int
    resource_label: str
    historical: bool
    team_index: int
    display_name: str
    asset_code: str
    text_asset_ids: tuple[tuple[str, str], ...]
    editable: bool
    reason: str

    def asset_id_for(self, field: str) -> str:
        for name, asset_id in self.text_asset_ids:
            if name == field:
                return asset_id
        raise KeyError(field)


@dataclass(frozen=True)
class RosterPlayer:
    group_id: str
    outer_index: int
    resource_label: str
    historical: bool
    pool: str
    player_index: int
    display_name: str
    position_code: int
    face_id: int
    first_name_asset_id: str
    last_name_asset_id: str
    jersey_number_asset_id: str
    editable: bool
    reason: str
    face_shield_asset_id: str = ""


@dataclass(frozen=True)
class RosterResourceView:
    """Strictly parsed ROST resource plus its physical pack-0 ownership."""

    outer_index: int
    outer_id: str
    outer_size: int
    pack_offset: int
    body: bytes
    parsed: Mapping[str, Any]

    @property
    def body_size(self) -> int:
        return len(self.body)

    @property
    def resource_label(self) -> str:
        return str(self.parsed["label"])


def utf16le_code_units(value: str) -> int:
    try:
        return len(value.encode("utf-16le")) // 2
    except UnicodeEncodeError as exc:
        raise ValidationError("Text contains an invalid Unicode surrogate") from exc


def encode_fixed_utf16le(value: str, allocation_bytes: int, label: str) -> bytes:
    """Encode one NUL-terminated string into an existing fixed allocation.

    Shorter values are followed by the required UTF-16 NUL terminator and then
    zero-filled through the complete original span.  Pointers and allocation
    boundaries therefore remain unchanged.  The byte limit is authoritative;
    characters outside the BMP consume two UTF-16 code units.
    """

    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} cannot be empty")
    if "\0" in value:
        raise ValidationError(f"{label} cannot contain a NUL character")
    if allocation_bytes < 2 or allocation_bytes & 1:
        raise ValidationError(f"{label} has an invalid UTF-16 allocation")
    try:
        encoded = value.encode("utf-16le")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{label} contains invalid Unicode") from exc
    required = len(encoded) + 2
    limit = allocation_bytes // 2 - 1
    if required > allocation_bytes:
        used = len(encoded) // 2
        raise ValidationError(
            f"{label} uses {used} UTF-16 units; its existing allocation allows {limit}. "
            "Some emoji and uncommon symbols use two units."
        )
    payload = encoded + b"\0\0" + bytes(allocation_bytes - required)
    if len(payload) != allocation_bytes:
        raise ValidationError(f"{label} did not preserve its fixed allocation")
    return payload


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _inventory_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Could not read the private game index: {exc}") from exc
    if value.get("schema") != "nfl2k5_resource_chunk_inventory/v1":
        raise ValidationError("The private game index has an unsupported format")
    return value


def load_roster_resources(
    pack0: Path,
    inventory: Path,
    outer_indices: Iterable[int] | None = None,
) -> dict[int, RosterResourceView]:
    """Parse selected ROST resources from a user's private pack-0 cache."""

    try:
        archive = parse_archive(pack0)
        records = nfl_roster.parse_inventory(inventory)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Could not open the NFL 2K5 roster catalog: {exc}") from exc
    wanted = None if outer_indices is None else {int(value) for value in outer_indices}
    selected = [record for record in records
                if wanted is None or record.outer_index in wanted]
    if wanted is not None and {record.outer_index for record in selected} != wanted:
        missing = sorted(wanted - {record.outer_index for record in selected})
        raise ValidationError(f"ROST resources are missing from the index: {missing}")
    result: dict[int, RosterResourceView] = {}
    for record in selected:
        try:
            _raw, body = nfl_roster.load_body(archive, record)
            parsed = nfl_roster.parse_resource(archive, record)
            entry = archive.entries[record.outer_index]
        except (OSError, ValueError, KeyError, IndexError) as exc:
            raise ValidationError(
                f"Could not parse ROST outer {record.outer_index}: {exc}"
            ) from exc
        if len(entry.segments) != 1:
            raise ValidationError(
                f"ROST outer {record.outer_index} crosses archive packs and is read-only"
            )
        segment = entry.segments[0]
        if segment.pack_ordinal != 0 or segment.size != entry.size:
            raise ValidationError(
                f"ROST outer {record.outer_index} is not wholly owned by pack 0"
            )
        if hashlib.sha256(body).hexdigest() != parsed.get("body_sha256"):
            raise ValidationError(f"ROST outer {record.outer_index} changed while parsing")
        result[record.outer_index] = RosterResourceView(
            record.outer_index,
            record.outer_id,
            record.outer_size,
            segment.pack_offset,
            body,
            parsed,
        )
    return result


def roster_text_reference_counts(view: RosterResourceView) -> Counter[int]:
    """Count every decoded ROST UTF-16 pointer domain for alias safety."""

    parsed = view.parsed
    result: Counter[int] = Counter({0x20: 1})  # structural ``roster``/``historic`` label

    def add(value: object) -> None:
        if value is not None:
            result[int(value)] += 1

    for team in parsed["teams"]:
        for field, _pointer in TEAM_TEXT_FIELDS:
            add(team.get(f"{field}_offset"))
    for player in parsed["players"]:
        add(player.get("first_name_offset"))
        add(player.get("last_name_offset"))
    for stadium in parsed["stadiums"]:
        for field in ("name", "location", "asset_code", "display_name",
                      "secondary_label"):
            add(stadium.get(f"{field}_offset"))
    for coach in parsed["coaches"]:
        for field in ("first_name", "last_name", "description_1",
                      "description_2", "description_3"):
            add(coach.get(f"{field}_offset"))
    for college in parsed["colleges"]:
        add(college.get("name_offset"))
    for descriptor in parsed["historic_descriptors"]:
        add(descriptor.get("slug_offset"))

    # The canonical parser exports the two pointer records as raw bytes but
    # intentionally omits their redundant target offsets.  Resolve them with
    # the same proved field-local biased formula so aliases are still counted.
    for table_name in ("team_labels", "generated_names"):
        for item in parsed[table_name]:
            record = int(item["offset"])
            for relative in (0, 4):
                add(nfl_roster.relative_pointer(
                    view.body, record + relative,
                    f"outer {view.outer_index} {table_name} {item['index']}"
                ))
    return result


def _allocation(view: RosterResourceView, offset: int, value: str, label: str) -> int:
    encoded = value.encode("utf-16le") + b"\0\0"
    if view.body[offset:offset + len(encoded)] != encoded:
        raise ValidationError(f"{label} does not match its decoded UTF-16 allocation")
    return len(encoded)


def _asset_id(*parts: object) -> str:
    value = ".".join(str(part).replace(" ", "-") for part in parts)
    if not _ASSET_ID_RE.fullmatch(value):
        raise ValidationError(f"Internal text asset identifier is invalid: {value!r}")
    return value


def _text_asset(
    *,
    view: RosterResourceView,
    bank_id: str,
    owner_kind: str,
    owner_index: int,
    field: str,
    value: str,
    offset: int,
    references: Counter[int],
    editable: bool,
    reason: str,
    provider_kind: str | None = None,
    provider_group_id: str | None = None,
    label: str | None = None,
) -> TextAsset:
    allocation = _allocation(
        view, offset, value,
        f"outer {view.outer_index} {owner_kind} {owner_index} {field}",
    )
    return TextAsset(
        asset_id=_asset_id(
            "nfl2k5", "text", "rost", view.outer_index,
            owner_kind, owner_index, field,
        ),
        bank_id=bank_id,
        label=label or f"{owner_kind.replace('_', ' ').title()} {owner_index} · "
              f"{field.replace('_', ' ').title()}",
        value=value,
        encoding="utf-16le",
        allocation_bytes=allocation,
        character_limit=allocation // 2 - 1,
        used_utf16_code_units=utf16le_code_units(value),
        access=TextAccess.EDITABLE if editable else TextAccess.READ_ONLY,
        reason=reason,
        outer_index=view.outer_index,
        chunk_index=0,
        owner_kind=owner_kind,
        owner_index=owner_index,
        field=field,
        reference_count=references[offset],
        provider_kind=provider_kind if editable else None,
        provider_group_id=provider_group_id if editable else None,
    )


@dataclass(frozen=True)
class _ParsedStrg:
    outer_index: int
    outer_id: str
    chunk_index: int
    name: str
    pool: tuple[tuple[int, int, str, int], ...]
    record_count: int


def _relative_target(body: bytes, field: int, label: str) -> int:
    if field < 0 or field + 4 > len(body):
        raise ValidationError(f"{label} pointer field is out of bounds")
    value = struct.unpack_from("<i", body, field)[0]
    target = field + value - 1
    if not 0 <= target < len(body):
        raise ValidationError(f"{label} pointer resolves outside its STRG body")
    return target


def _utf16z(body: bytes, offset: int, label: str) -> tuple[str, int]:
    if offset & 1 or not 0 <= offset <= len(body) - 2:
        raise ValidationError(f"{label} has an invalid UTF-16 offset")
    cursor = offset
    while cursor + 2 <= len(body):
        if body[cursor:cursor + 2] == b"\0\0":
            try:
                return body[offset:cursor].decode("utf-16le"), cursor + 2
            except UnicodeDecodeError as exc:
                raise ValidationError(f"{label} is invalid UTF-16LE") from exc
        cursor += 2
    raise ValidationError(f"{label} is not NUL-terminated")


def _parse_strg_banks(pack0: Path, inventory: Mapping[str, Any]) -> list[_ParsedStrg]:
    try:
        archive = parse_archive(pack0)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Could not open STRG banks: {exc}") from exc
    result: list[_ParsedStrg] = []
    for row in inventory.get("chunks", []):
        if row.get("kind") != "STRG":
            continue
        outer_index = int(row["outer_index"])
        chunk_index = int(row["chunk_index"])
        stored_size = int(row["stored_size"])
        chunk_offset = int(row["chunk_offset"])
        entry = archive.entries[outer_index]
        raw = read_entry_range(
            archive, entry, chunk_offset, ROSTER_WRAPPER_SIZE + stored_size)
        header = struct.unpack_from("<4s7I", raw)
        expected = (
            b"STRG", stored_size, int(row["word_08"]), int(row["word_0c"]),
            int(str(row["word_10"]), 0), int(row["word_14"]), 0, 0,
        )
        if header != expected or expected[2:] != (0, 0, 0, 0, 0, 0):
            raise ValidationError(
                f"STRG outer {outer_index} chunk {chunk_index} uses an unsupported wrapper"
            )
        body = raw[ROSTER_WRAPPER_SIZE:]
        if len(body) < 0x34 or body[0x0C:0x10] != b"STRG":
            raise ValidationError(f"STRG outer {outer_index} has an invalid inner header")
        name_offset = _relative_target(body, 0x10, "STRG name")
        descriptor = _relative_target(body, 0x14, "STRG descriptor")
        name, name_end = _utf16z(body, name_offset, "STRG name")
        if name_end > descriptor:
            raise ValidationError("STRG name overlaps its descriptor")
        if descriptor + 4 > len(body):
            raise ValidationError("STRG descriptor is out of bounds")
        count = struct.unpack_from("<I", body, descriptor)[0]
        if count > 1_000_000:
            raise ValidationError("STRG record count is unreasonable")
        records = descriptor + 4
        pool_start = records + count * 12
        if pool_start > len(body):
            raise ValidationError("STRG record table exceeds its body")
        references: Counter[int] = Counter()
        strings: dict[int, tuple[str, int]] = {}
        for index in range(count):
            record = records + index * 12
            code_units = struct.unpack_from("<I", body, record + 8)[0]
            target = pool_start + code_units * 2
            if not pool_start <= target < len(body):
                raise ValidationError(f"STRG record {index} points outside its pool")
            text, end = _utf16z(body, target, f"STRG record {index}")
            prior = strings.setdefault(target, (text, end))
            if prior != (text, end):
                raise ValidationError(f"STRG record {index} has an inconsistent alias")
            references[target] += 1
        pool: list[tuple[int, int, str, int]] = []
        cursor = pool_start
        pool_end = max((end for _text, end in strings.values()), default=pool_start)
        while cursor < pool_end:
            text, end = _utf16z(body, cursor, "STRG pool entry")
            if cursor not in strings or strings[cursor] != (text, end):
                raise ValidationError("STRG pool contains an unreferenced or interior string")
            pool.append((cursor, end, text, references[cursor]))
            cursor = end
        if cursor != pool_end or set(strings) != {row[0] for row in pool}:
            raise ValidationError("STRG pool boundaries do not match its references")
        result.append(_ParsedStrg(
            outer_index,
            str(row["outer_id"]),
            chunk_index,
            name,
            tuple(pool),
            count,
        ))
    return result


class Nfl2k5TextCatalog:
    """Immutable original catalog plus product-facing search helpers."""

    def __init__(
        self,
        banks: Sequence[TextBank],
        assets: Sequence[TextAsset],
        teams: Sequence[RosterTeam],
        players: Sequence[RosterPlayer],
        number_assets: Sequence[RosterNumberAsset],
    ) -> None:
        self.banks = tuple(banks)
        self.assets = tuple(assets)
        self.teams = tuple(teams)
        self.players = tuple(players)
        self.number_assets = tuple(number_assets)
        self._banks = _unique_index(self.banks, "bank_id")
        self._assets = _unique_index(self.assets, "asset_id")
        self._teams = _unique_index(self.teams, "group_id")
        self._players = _unique_index(self.players, "group_id")
        self._numbers = _unique_index(self.number_assets, "asset_id")

    @property
    def editable_count(self) -> int:
        return sum(asset.editable for asset in self.assets)

    @property
    def read_only_count(self) -> int:
        return len(self.assets) - self.editable_count

    @classmethod
    def from_cache(cls, cache: SourceCache) -> "Nfl2k5TextCatalog":
        return cls.from_paths(cache.pack0, cache.inventory)

    @classmethod
    def from_paths(cls, pack0: Path, inventory: Path) -> "Nfl2k5TextCatalog":
        try:
            info = pack0.lstat()
        except FileNotFoundError as exc:
            raise ValidationError(f"Private pack 0 is missing: {pack0}") from exc
        if info.st_size != PACK0_SIZE:
            raise ValidationError("Private pack 0 has the wrong size")
        document = _inventory_document(inventory)
        views = load_roster_resources(pack0, inventory)
        strg = _parse_strg_banks(pack0, document)
        catalog = cls.from_parsed(document, views, strg)
        safe = SafeTextCatalog.from_paths(pack0, inventory)
        return _merge_safe_text_catalog(catalog, safe)

    @classmethod
    def from_parsed(
        cls,
        inventory: Mapping[str, Any],
        roster_views: Mapping[int, RosterResourceView],
        strg_banks: Sequence[_ParsedStrg] = (),
    ) -> "Nfl2k5TextCatalog":
        banks: list[TextBank] = []
        assets: list[TextAsset] = []
        teams: list[RosterTeam] = []
        players: list[RosterPlayer] = []
        numbers: list[RosterNumberAsset] = []

        roster_bank_ids: dict[int, str] = {}
        strg_by_key = {(item.outer_index, item.chunk_index): item for item in strg_banks}
        for row in inventory.get("chunks", []):
            kind = str(row.get("kind", ""))
            if kind not in TEXT_BANK_KINDS:
                continue
            outer = int(row["outer_index"])
            chunk = int(row["chunk_index"])
            bank_id = _asset_id("nfl2k5", "text-bank", kind.lower(), outer, chunk)
            if kind == "ROST" and outer in roster_views:
                view = roster_views[outer]
                roster_bank_ids[outer] = bank_id
                banks.append(TextBank(
                    bank_id, kind,
                    f"ROST {view.resource_label} · outer {outer}",
                    outer, chunk, True, "mixed", None,
                    "Primary names plus player numbers/face-shield types and bounded "
                    "team identity are editable; "
                    "other decoded ROST text is export-only.",
                ))
            elif kind == "STRG" and (outer, chunk) in strg_by_key:
                table = strg_by_key[(outer, chunk)]
                banks.append(TextBank(
                    bank_id, kind, f"STRG {table.name} · outer {outer}",
                    outer, chunk, True, TextAccess.READ_ONLY.value,
                    len(table.pool),
                    "Decoded and searchable, but pool aliases and archive writeback "
                    "ownership are not yet proved for a public writer.",
                ))
            else:
                banks.append(TextBank(
                    bank_id, kind, f"{kind} · outer {outer} chunk {chunk}",
                    outer, chunk, False, TextAccess.READ_ONLY.value, None,
                    _unresolved_bank_reason(kind),
                ))

        for outer in sorted(roster_views):
            view = roster_views[outer]
            bank_id = roster_bank_ids.get(outer)
            if bank_id is None:
                raise ValidationError(f"ROST outer {outer} has no indexed text bank")
            _append_roster_catalog(view, bank_id, assets, teams, players, numbers)

        for table in strg_banks:
            bank_id = _asset_id(
                "nfl2k5", "text-bank", "strg", table.outer_index, table.chunk_index
            )
            for pool_index, (start, end, value, references) in enumerate(table.pool):
                allocation = end - start
                assets.append(TextAsset(
                    asset_id=_asset_id(
                        "nfl2k5", "text", "strg", table.outer_index,
                        table.chunk_index, pool_index,
                    ),
                    bank_id=bank_id,
                    label=f"{table.name} · message {pool_index}",
                    value=value,
                    encoding="utf-16le",
                    allocation_bytes=allocation,
                    character_limit=allocation // 2 - 1,
                    used_utf16_code_units=utf16le_code_units(value),
                    access=TextAccess.READ_ONLY,
                    reason=(
                        "This STRG pool is decoded and byte-identically serializable, "
                        "but safe archive mutation and all shared-message consumers "
                        "have not been proved."
                    ),
                    outer_index=table.outer_index,
                    chunk_index=table.chunk_index,
                    owner_kind="strg_pool",
                    owner_index=pool_index,
                    field="text",
                    reference_count=references,
                ))
        return cls(banks, assets, teams, players, numbers)

    def get_bank(self, bank_id: str) -> TextBank:
        return self._banks[bank_id]

    def get_asset(self, asset_id: str) -> TextAsset:
        return self._assets[asset_id]

    def get_team(self, group_id: str) -> RosterTeam:
        return self._teams[group_id]

    def get_player(self, group_id: str) -> RosterPlayer:
        return self._players[group_id]

    def get_number_asset(self, asset_id: str) -> RosterNumberAsset:
        return self._numbers[asset_id]

    def search(
        self,
        query: str = "",
        *,
        editable: bool | None = None,
        bank_id: str | None = None,
    ) -> tuple[TextAsset, ...]:
        terms = query.casefold().split()
        result: list[TextAsset] = []
        for asset in self.assets:
            if editable is not None and asset.editable is not editable:
                continue
            if bank_id is not None and asset.bank_id != bank_id:
                continue
            haystack = f"{asset.label}\n{asset.value}\n{asset.asset_id}".casefold()
            if all(term in haystack for term in terms):
                result.append(asset)
        return tuple(result)

    def export_payload(self, asset_id: str) -> bytes:
        """Return a UTF-8 text export generated from the user's private cache."""

        return (self.get_asset(asset_id).value + "\n").encode("utf-8")

    def export_number_payload(self, asset_id: str) -> bytes:
        """Return one jersey number as a small, retail-free UTF-8 text export."""

        return (str(self.get_number_asset(asset_id).value) + "\n").encode("utf-8")


class Nfl2k5TextEdits:
    """Reversible, retail-free staged text and jersey replacements."""

    _MISSING = object()

    def __init__(self, catalog: Nfl2k5TextCatalog) -> None:
        self.catalog = catalog
        self._text: dict[str, str] = {}
        self._numbers: dict[str, int] = {}
        self._undo: list[tuple[str, str, object]] = []

    @property
    def modified_count(self) -> int:
        return len(self._text) + len(self._numbers)

    def value(self, asset_id: str) -> str:
        return self._text.get(asset_id, self.catalog.get_asset(asset_id).value)

    def number(self, asset_id: str) -> int:
        return self._numbers.get(
            asset_id, self.catalog.get_number_asset(asset_id).value
        )

    def set_text(self, asset_id: str, value: str) -> None:
        asset = self.catalog.get_asset(asset_id)
        if not asset.editable:
            raise ValidationError(asset.reason or "That text is read-only")
        encode_fixed_utf16le(value, asset.allocation_bytes, asset.label)
        previous = self._text.get(asset_id, self._MISSING)
        if value == asset.value:
            self._text.pop(asset_id, None)
        else:
            self._text[asset_id] = value
        if previous is self._MISSING and asset_id not in self._text:
            return
        if previous == self._text.get(asset_id, self._MISSING):
            return
        self._undo.append(("text", asset_id, previous))

    def set_number(self, asset_id: str, value: int) -> None:
        asset = self.catalog.get_number_asset(asset_id)
        if not asset.editable:
            raise ValidationError(asset.reason or "That number is read-only")
        if type(value) is not int or not asset.minimum <= value <= asset.maximum:
            raise ValidationError(
                f"{asset.label} must be {asset.minimum} through {asset.maximum}"
            )
        previous = self._numbers.get(asset_id, self._MISSING)
        if value == asset.value:
            self._numbers.pop(asset_id, None)
        else:
            self._numbers[asset_id] = value
        if previous is self._MISSING and asset_id not in self._numbers:
            return
        if previous == self._numbers.get(asset_id, self._MISSING):
            return
        self._undo.append(("number", asset_id, previous))

    def revert(self, asset_id: str) -> None:
        if asset_id in self._text:
            previous = self._text.pop(asset_id)
            self._undo.append(("text", asset_id, previous))
            return
        if asset_id in self._numbers:
            previous = self._numbers.pop(asset_id)
            self._undo.append(("number", asset_id, previous))

    def revert_all(self) -> None:
        for asset_id in tuple(self._text):
            self.revert(asset_id)
        for asset_id in tuple(self._numbers):
            self.revert(asset_id)

    def undo(self) -> bool:
        if not self._undo:
            return False
        kind, asset_id, previous = self._undo.pop()
        target = self._text if kind == "text" else self._numbers
        if previous is self._MISSING:
            target.pop(asset_id, None)
        else:
            target[asset_id] = previous  # type: ignore[assignment]
        return True

    def provider_edits(self) -> tuple[dict[str, Any], ...]:
        """Group only user changes into the unified provider's sparse schema."""

        grouped: dict[str, dict[str, Any]] = {}
        universal: list[dict[str, Any]] = []
        for asset_id, value in self._text.items():
            asset = self.catalog.get_asset(asset_id)
            assert asset.provider_group_id is not None and asset.provider_kind is not None
            if asset.provider_kind == SAFE_TEXT_PROVIDER_KIND:
                universal.append({
                    "kind": SAFE_TEXT_PROVIDER_KIND,
                    "selector": asset.provider_group_id,
                    "text": value,
                })
                continue
            record = grouped.setdefault(
                asset.provider_group_id,
                _provider_base(asset.provider_kind, asset.outer_index,
                               asset.owner_index, asset.owner_kind),
            )
            record["changes"][asset.field] = value
        for asset_id, value in self._numbers.items():
            asset = self.catalog.get_number_asset(asset_id)
            player = self.catalog.get_player(asset.provider_group_id)
            record = grouped.setdefault(
                asset.provider_group_id,
                _provider_base(
                    ROSTER_PLAYER_PROVIDER_KIND,
                    player.outer_index,
                    player.player_index,
                    player.pool,
                ),
            )
            record["changes"][asset.field] = value
        return (
            tuple(grouped[key] for key in sorted(grouped))
            + tuple(sorted(universal, key=lambda row: str(row["selector"])))
        )

    def replacement_document(self) -> dict[str, Any]:
        """Shareable document containing only user replacements and stable IDs."""

        edits: list[dict[str, Any]] = []
        edits.extend(
            {"asset_id": asset_id, "kind": "text", "value": value}
            for asset_id, value in sorted(self._text.items())
        )
        edits.extend(
            {"asset_id": asset_id, "kind": "number", "value": value}
            for asset_id, value in sorted(self._numbers.items())
        )
        return {"schema": TEXT_PROJECT_SCHEMA, "edits": edits}

    def canonical_replacement_bytes(self) -> bytes:
        return _canonical_json(self.replacement_document())

    def load_replacement_document(self, value: Mapping[str, Any]) -> None:
        if value.get("schema") != TEXT_PROJECT_SCHEMA or not isinstance(
            value.get("edits"), list
        ):
            raise ValidationError("Text replacement project has an unsupported format")
        staged_text: dict[str, str] = {}
        staged_numbers: dict[str, int] = {}
        for order, item in enumerate(value["edits"]):
            if not isinstance(item, dict) or set(item) != {"asset_id", "kind", "value"}:
                raise ValidationError(f"Text replacement {order} is malformed")
            asset_id = item["asset_id"]
            if type(asset_id) is not str:
                raise ValidationError(f"Text replacement {order} has no asset ID")
            if item["kind"] == "text" and type(item["value"]) is str:
                asset = self.catalog.get_asset(asset_id)
                if not asset.editable:
                    raise ValidationError(asset.reason)
                encode_fixed_utf16le(item["value"], asset.allocation_bytes, asset.label)
                if asset_id in staged_text or asset_id in staged_numbers:
                    raise ValidationError(f"Text project repeats {asset_id}")
                if item["value"] != asset.value:
                    staged_text[asset_id] = item["value"]
            elif item["kind"] == "number" and type(item["value"]) is int:
                asset = self.catalog.get_number_asset(asset_id)
                if not asset.editable or not asset.minimum <= item["value"] <= asset.maximum:
                    raise ValidationError(f"Invalid replacement for {asset.label}")
                if asset_id in staged_text or asset_id in staged_numbers:
                    raise ValidationError(f"Text project repeats {asset_id}")
                if item["value"] != asset.value:
                    staged_numbers[asset_id] = item["value"]
            else:
                raise ValidationError(f"Text replacement {order} has a wrong value type")
        self._text = staged_text
        self._numbers = staged_numbers
        self._undo.clear()


def _product_bank_from_safe(bank: SafeTextBank) -> TextBank:
    if bank.editable_count and bank.read_only_count:
        access = "mixed"
    elif bank.editable_count:
        access = TextAccess.EDITABLE.value
    else:
        access = TextAccess.READ_ONLY.value
    reason = bank.reason
    if bank.kind == "SITU":
        reason += (
            " Research boundary: team-selector reassignment, scenario-state "
            "values, and unlock-condition logic are inspect-only until a "
            "separate causal decode proves safe editing."
        )
    return TextBank(
        bank_id=bank.bank_id,
        kind=bank.kind,
        label=f"{bank.label} · outer {bank.outer_index}",
        outer_index=bank.outer_index,
        chunk_index=bank.chunk_index,
        decoded=bank.decoded,
        access=access,
        entry_count=bank.editable_count + bank.read_only_count,
        reason=reason,
    )


def _product_asset_from_safe(
    asset: SafeTextAsset, bank: SafeTextBank
) -> TextAsset:
    return TextAsset(
        asset_id=asset.asset_id,
        bank_id=asset.bank_id,
        label=asset.label,
        value=asset.value,
        encoding="utf-16le",
        allocation_bytes=asset.allocation_bytes,
        character_limit=asset.character_limit,
        used_utf16_code_units=asset.used_utf16_code_units,
        access=(
            TextAccess.EDITABLE
            if asset.access is SafeTextAccess.EDITABLE
            else TextAccess.READ_ONLY
        ),
        reason=asset.reason,
        outer_index=bank.outer_index,
        chunk_index=bank.chunk_index,
        owner_kind=f"{asset.bank_kind.lower()}_text",
        owner_index=asset.owner_index,
        field=asset.field_name,
        reference_count=asset.reference_count,
        provider_kind=asset.provider_kind if asset.editable else None,
        # This selector is private, source-derived provider metadata.  Public
        # project documents continue to serialize only asset_id/kind/value.
        provider_group_id=asset.selector if asset.editable else None,
    )


def _merge_safe_text_catalog(
    catalog: Nfl2k5TextCatalog, safe: SafeTextCatalog
) -> Nfl2k5TextCatalog:
    """Upgrade the product catalog without duplicating existing STRG rows."""

    safe_banks = {bank.bank_id: bank for bank in safe.banks}
    if len(safe_banks) != len(safe.banks):
        raise ValidationError("The safe text catalog repeats a bank ID")
    banks: list[TextBank] = []
    consumed_banks: set[str] = set()
    for bank in catalog.banks:
        proved = safe_banks.get(bank.bank_id)
        if proved is not None:
            if (
                bank.kind != proved.kind
                or bank.outer_index != proved.outer_index
                or bank.chunk_index != proved.chunk_index
            ):
                raise ValidationError(
                    f"Safe text bank ownership changed for {bank.bank_id}"
                )
            banks.append(_product_bank_from_safe(proved))
            consumed_banks.add(bank.bank_id)
        elif bank.kind == "NAME":
            banks.append(TextBank(
                bank.bank_id,
                bank.kind,
                f"NAME player-name glyph metrics · outer {bank.outer_index}",
                bank.outer_index,
                bank.chunk_index,
                False,
                TextAccess.READ_ONLY.value,
                None,
                _unresolved_bank_reason("NAME"),
            ))
        else:
            banks.append(bank)
    if consumed_banks != set(safe_banks):
        missing = sorted(set(safe_banks) - consumed_banks)
        raise ValidationError(f"Safe text banks are absent from the product index: {missing}")

    safe_assets = {asset.asset_id: asset for asset in safe.assets}
    if len(safe_assets) != len(safe.assets):
        raise ValidationError("The safe text catalog repeats an asset ID")
    product_assets = {asset.asset_id: asset for asset in catalog.assets}
    safe_bank_for = {bank.bank_id: bank for bank in safe.banks}
    merged: list[TextAsset] = []
    upgraded: set[str] = set()
    for existing in catalog.assets:
        proved = safe_assets.get(existing.asset_id)
        if proved is None:
            merged.append(existing)
            continue
        if (
            proved.bank_kind != "STRG"
            or existing.bank_id != proved.bank_id
            or existing.value != proved.value
            or existing.allocation_bytes != proved.allocation_bytes
            or existing.reference_count != proved.reference_count
        ):
            raise ValidationError(
                f"Existing STRG identity differs from safe writer: {existing.asset_id}"
            )
        merged.append(_product_asset_from_safe(
            proved, safe_bank_for[proved.bank_id]
        ))
        upgraded.add(existing.asset_id)

    expected_strg = {
        asset.asset_id for asset in safe.assets if asset.bank_kind == "STRG"
    }
    if upgraded != expected_strg:
        missing = sorted(expected_strg - upgraded)
        raise ValidationError(f"Existing STRG assets are missing: {missing[:5]}")
    for proved in safe.assets:
        if proved.bank_kind == "STRG":
            continue
        if proved.asset_id in product_assets:
            raise ValidationError(
                f"Safe text asset collides with the product index: {proved.asset_id}"
            )
        merged.append(_product_asset_from_safe(
            proved, safe_bank_for[proved.bank_id]
        ))

    result = Nfl2k5TextCatalog(
        banks, merged, catalog.teams, catalog.players, catalog.number_assets
    )
    expected_assets = len(catalog.assets) + len(safe.assets) - len(expected_strg)
    if len(result.assets) != expected_assets:
        raise ValidationError("Safe text merge changed the expected asset count")
    return result


def _unique_index(items: Sequence[Any], attribute: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        key = str(getattr(item, attribute))
        if key in result:
            raise ValidationError(f"Text catalog repeats {attribute} {key}")
        result[key] = item
    return result


def _provider_base(
    kind: str,
    outer_index: int,
    owner_index: int,
    player_pool: str | None = None,
) -> dict[str, Any]:
    if kind == ROSTER_TEAM_PROVIDER_KIND:
        key = "team_index"
    elif kind == ROSTER_PLAYER_PROVIDER_KIND:
        if player_pool == "secondary_players":
            return {
                "kind": kind,
                "resource_outer_index": outer_index,
                "player_pool": player_pool,
                "player_index": owner_index,
                "changes": {},
            }
        key = "primary_player_index"
    else:
        raise ValidationError(f"Unsupported text provider kind: {kind}")
    return {
        "kind": kind,
        "resource_outer_index": outer_index,
        key: owner_index,
        "changes": {},
    }


def _unresolved_bank_reason(kind: str) -> str:
    return {
        "CRED": "Credits data is indexed, but no allocation-safe NFL 2K5 text writer is proved.",
        "NAME": (
            "Player-name atlas glyph metrics are indexed here as resources, not "
            "user-facing strings; their structural measurements are read-only."
        ),
        "SITU": "Situation/scenario data is indexed; text ownership and scenario logic are not safely separated.",
        "TRIV": "Trivia data is indexed, but its string and lookup ownership are not decoded for writing.",
    }.get(kind, "This text-bearing bank is indexed but not safely decoded for editing.")


def _append_roster_catalog(
    view: RosterResourceView,
    bank_id: str,
    assets: list[TextAsset],
    teams: list[RosterTeam],
    players: list[RosterPlayer],
    numbers: list[RosterNumberAsset],
) -> None:
    parsed = view.parsed
    references = roster_text_reference_counts(view)
    historical = view.resource_label == "historic"

    label_value = str(view.resource_label)
    assets.append(_text_asset(
        view=view, bank_id=bank_id, owner_kind="resource", owner_index=0,
        field="label", value=label_value, offset=0x20, references=references,
        editable=False,
        reason="The ROST structural label selects the resource schema and is read-only.",
        label=f"ROST outer {view.outer_index} · Structural Label",
    ))

    for team in parsed["teams"]:
        team_index = int(team["index"])
        group = _asset_id("roster", view.outer_index, "team", team_index)
        field_ids: list[tuple[str, str]] = []
        group_editable = True
        group_reasons: list[str] = []
        for field, _pointer in TEAM_TEXT_FIELDS:
            value = str(team[field])
            offset = int(team[f"{field}_offset"])
            unique = references[offset] == 1
            editable = field in EDITABLE_TEAM_FIELDS and unique
            if field == "asset_code":
                reason = (
                    "Asset code owns uniforms/art and is deliberately outside the "
                    "allocation-only identity writer."
                )
            elif not unique:
                reason = "This string allocation is shared by multiple decoded pointers."
                group_editable = False
                group_reasons.append(reason)
            else:
                reason = "Fixed-allocation UTF-16 team identity string."
            asset = _text_asset(
                view=view, bank_id=bank_id, owner_kind="team",
                owner_index=team_index, field=field, value=value, offset=offset,
                references=references, editable=editable, reason=reason,
                provider_kind=ROSTER_TEAM_PROVIDER_KIND,
                provider_group_id=group,
                label=f"{team['city']} {team['nickname']} · {field.replace('_', ' ').title()}",
            )
            assets.append(asset)
            field_ids.append((field, asset.asset_id))
        teams.append(RosterTeam(
            group, view.outer_index, view.resource_label, historical,
            team_index, f"{team['city']} {team['nickname']}".strip(),
            str(team["asset_code"]), tuple(field_ids), group_editable,
            "; ".join(dict.fromkeys(group_reasons)) if group_reasons else
            "Four fixed-allocation identity strings are editable; art code stays fixed.",
        ))

    for player in parsed["players"]:
        pool = str(player["pool"])
        player_index = int(player["index"])
        group = _asset_id("roster", view.outer_index, pool, player_index)
        primary = pool == "primary_players"
        raw = bytes.fromhex(str(player["raw_hex"]))
        if len(raw) != PLAYER_STRIDE:
            raise ValidationError(
                f"ROST outer {view.outer_index} player {player_index} has wrong stride"
            )
        word = struct.unpack_from("<I", raw, JERSEY_FIELD)[0]
        jersey = (word >> JERSEY_SHIFT) & 0x7F
        face_shield = (word >> FACE_SHIELD_SHIFT) & 0x3
        face_id = struct.unpack_from("<H", raw, 0x06)[0]
        position_code = raw[0x35]
        name_assets: dict[str, str] = {}
        name_target_editable = False
        reasons: list[str] = []
        for field in ("first_name", "last_name"):
            value = str(player[field])
            offset = int(player[f"{field}_offset"])
            unique = references[offset] == 1
            editable = primary and unique
            name_target_editable = name_target_editable or editable
            if not primary:
                reason = (
                    "Secondary-player name allocations are zero-capacity and stay "
                    "read-only; this player's jersey number and face-shield type "
                    "are enabled by their own proved contracts."
                )
                reasons.append(reason)
            elif not unique:
                reason = "This name allocation is shared by multiple decoded pointers."
                reasons.append(reason)
            else:
                reason = "Fixed-allocation primary-player name string."
            asset = _text_asset(
                view=view, bank_id=bank_id, owner_kind=pool,
                owner_index=player_index, field=field, value=value, offset=offset,
                references=references, editable=editable, reason=reason,
                provider_kind=ROSTER_PLAYER_PROVIDER_KIND,
                provider_group_id=group,
                label=f"{player['first_name']} {player['last_name']} · "
                      f"{field.replace('_', ' ').title()}",
            )
            assets.append(asset)
            name_assets[field] = asset.asset_id
        # The generalized roster writer preserves the complete 32-bit word and
        # patches only its seven jersey-number bits for both player pools.
        # Secondary names remain unproved zero-capacity pointers, but their
        # fixed-stride number word is no less bounded than a primary record.
        number_editable = 0 <= jersey <= 99
        number_reason = (
            "Masked jersey-number bits; every other word bit is preserved."
            if number_editable else
            "The source jersey value is outside the supported 0 through 99 range."
        )
        number_id = _asset_id(
            "nfl2k5", "roster", view.outer_index, pool, player_index,
            "jersey-number",
        )
        numbers.append(RosterNumberAsset(
            number_id,
            f"{player['first_name']} {player['last_name']} · Jersey Number",
            jersey, 0, 99,
            TextAccess.EDITABLE if number_editable else TextAccess.READ_ONLY,
            number_reason, view.outer_index, player_index, group,
        ))
        face_shield_editable = face_shield in dict(FACE_SHIELD_CHOICES)
        face_shield_reason = (
            "Per-player face-shield type from +0x20 bits 15..16. This disc seed "
            "selects None, Clear, or Dark; it is not a HOME/AWAY visor tint, and "
            "a loaded roster or franchise save may override it."
            if face_shield_editable else
            "The source face-shield value is reserved value 3. It is shown but "
            "cannot be authored; only None, Clear, or Dark are supported."
        )
        face_shield_id = _asset_id(
            "nfl2k5", "roster", view.outer_index, pool, player_index,
            "face-shield",
        )
        numbers.append(RosterNumberAsset(
            face_shield_id,
            f"{player['first_name']} {player['last_name']} · Face Shield",
            face_shield, 0, 2,
            (TextAccess.EDITABLE if face_shield_editable
             else TextAccess.READ_ONLY),
            face_shield_reason, view.outer_index, player_index, group,
            field="face_shield", choices=FACE_SHIELD_CHOICES,
        ))
        # RC49 enables each field from its own proved contract instead of
        # locking the whole row, so a player row is writable when any bounded
        # target is writable.  This keeps the published writable-player count
        # truthful for the 68 secondary-pool players whose zero-capacity names
        # stay read-only while their masked jersey-number bits are editable.
        editable = (
            name_target_editable or number_editable or face_shield_editable
        )
        players.append(RosterPlayer(
            group, view.outer_index, view.resource_label, historical, pool,
            player_index, f"{player['first_name']} {player['last_name']}",
            position_code, face_id, name_assets["first_name"],
            name_assets["last_name"], number_id, editable,
            "; ".join(dict.fromkeys(reasons)) if reasons else
            "Names, jersey number, and face-shield type use bounded, "
            "pointer-preserving edits.",
            face_shield_id,
        ))

    read_only_groups: tuple[tuple[str, str, tuple[str, ...]], ...] = (
        ("stadium", "stadiums", ("name", "location", "asset_code",
                                   "display_name", "secondary_label")),
        ("coach", "coaches", ("first_name", "last_name", "description_1",
                                "description_2", "description_3")),
        ("college", "colleges", ("name",)),
        ("historic_descriptor", "historic_descriptors", ("slug",)),
    )
    for owner_kind, collection, fields in read_only_groups:
        for item in parsed[collection]:
            owner_index = int(item["index"])
            for field in fields:
                value = item.get(field)
                offset = item.get(f"{field}_offset")
                if value is None or offset is None:
                    continue
                assets.append(_text_asset(
                    view=view, bank_id=bank_id, owner_kind=owner_kind,
                    owner_index=owner_index, field=field, value=str(value),
                    offset=int(offset), references=references, editable=False,
                    reason=(
                        "Decoded and exportable, but this ROST field has no proved "
                        "public same-allocation writer."
                    ),
                ))

    for owner_kind, collection, fields in (
        ("team_label", "team_labels", ("nickname", "abbreviation")),
        ("generated_name", "generated_names", ("first_name", "last_name")),
    ):
        for item in parsed[collection]:
            owner_index = int(item["index"])
            record = int(item["offset"])
            for field_index, field in enumerate(fields):
                offset = nfl_roster.relative_pointer(
                    view.body, record + field_index * 4,
                    f"outer {view.outer_index} {owner_kind} {owner_index} {field}",
                )
                value = item.get(field)
                if value is None or offset is None:
                    continue
                assets.append(_text_asset(
                    view=view, bank_id=bank_id, owner_kind=owner_kind,
                    owner_index=owner_index, field=field, value=str(value),
                    offset=offset, references=references, editable=False,
                    reason=(
                        "Decoded and exportable, but generated/label pool ownership "
                        "is not admitted by the identity writer."
                    ),
                ))


__all__ = [
    "EDITABLE_TEAM_FIELDS",
    "Nfl2k5TextCatalog",
    "Nfl2k5TextEdits",
    "ROSTER_PLAYER_PROVIDER_KIND",
    "ROSTER_TEAM_PROVIDER_KIND",
    "RosterNumberAsset",
    "RosterPlayer",
    "RosterResourceView",
    "RosterTeam",
    "TEXT_PROJECT_SCHEMA",
    "TextAccess",
    "TextAsset",
    "TextBank",
    "encode_fixed_utf16le",
    "load_roster_resources",
    "roster_text_reference_counts",
    "utf16le_code_units",
]
