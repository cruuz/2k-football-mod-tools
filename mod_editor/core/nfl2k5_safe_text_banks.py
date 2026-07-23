"""Bounded fixed-allocation writers for proved NFL 2K5 text banks.

This module deliberately covers only text whose complete source binding is
known.  It derives every decoded string and every preimage from the user's
private source cache; no retail strings are embedded here or placed in a
shareable project.

The proved domains are:

* STRG pool allocations.  A pool allocation can be referenced by more than
  one lookup record, so one edit intentionally affects every listed alias.
* The four display-text pointers in each of the 25 SITU moment records.  The
  two adjacent team-resource selectors and the remaining scenario state are
  intentionally excluded.
* CRED's two pointer fields per credit event and TRIV's category, subject,
  question, and four answer pointers.  Numeric credit behavior and trivia
  answer-key fields are left untouched.

All replacements stay inside the original UTF-16LE allocation, retain its
terminator, and zero-fill unused bytes.  The archive directory, resource
wrapper, pointer fields, counts, IDs, and allocation boundaries do not move.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Iterable, Mapping, Sequence

if __package__:
    from .errors import ValidationError
else:
    # The unified copied-XISO backend loads this reviewed module by exact path
    # inside its pinned execution bundle.  Keep that narrow adapter route free
    # of product-package side effects while retaining the same fail-closed
    # ValueError contract consumed by the backend CLI.
    class ValidationError(ValueError):
        pass


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from nfl_outer import Archive, Entry, parse_archive, read_entry_range  # noqa: E402
from nfl_scene_probe import (  # noqa: E402
    ResourceRecord,
    decode_resource,
    parse_inventory,
)
from string_table_inventory import (  # noqa: E402
    ParsedTable,
    parse_nfl_body,
    rebuild_table,
)


SAFE_TEXT_PROVIDER_KIND = "universal_fixed_text"
SAFE_TEXT_PROJECT_KIND = "text"
SAFE_TEXT_AUDIT_SCHEMA = "2k5_mod_studio_safe_text_audit/v1"
WRAPPER_SIZE = 0x20
SITU_RECORD_COUNT = 25
SITU_RECORD_SIZE = 0x6C
SITU_DESCRIPTOR_OFFSET = 0x40
SITU_RECORD_TABLE_OFFSET = 0x44
SITU_POOL_OFFSET = 0xAD0
SITU_DISPLAY_FIELDS: tuple[tuple[str, int], ...] = (
    ("title", 0x00),
    ("historical_description", 0x04),
    ("challenge_objective", 0x08),
    ("date", 0x0C),
)
SITU_SELECTOR_FIELDS: tuple[tuple[str, int], ...] = (
    ("away_team_asset_code", 0x14),
    ("home_team_asset_code", 0x18),
)
TRIV_TEXT_FIELDS: tuple[tuple[str, int], ...] = (
    ("category", 0x04),
    ("subject", 0x08),
    ("question", 0x0C),
    ("answer_a", 0x10),
    ("answer_b", 0x14),
    ("answer_c", 0x18),
    ("answer_d", 0x1C),
)
TEXT_BANK_KINDS = frozenset({"CRED", "NAME", "ROST", "SITU", "STRG", "TRIV"})


class SafeTextAccess(str, Enum):
    EDITABLE = "editable"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class _PrivateLocator:
    """Private source-cache binding; never serialize into a project."""

    outer_index: int
    chunk_index: int
    body_offset: int
    allocation_bytes: int
    pack_name: str
    pack_offset: int
    preimage_sha256: str


@dataclass(frozen=True)
class SafeTextAsset:
    """One decoded, searchable text allocation from the user's own dump."""

    asset_id: str
    selector: str
    bank_id: str
    bank_kind: str
    label: str
    value: str
    allocation_bytes: int
    character_limit: int
    used_utf16_code_units: int
    access: SafeTextAccess
    reason: str
    reference_count: int
    owner_index: int
    field_name: str
    provider_kind: str | None
    _locator: _PrivateLocator = field(repr=False, compare=False)

    @property
    def editable(self) -> bool:
        return self.access is SafeTextAccess.EDITABLE

    def validate_replacement(self, value: str) -> bytes:
        if not self.editable:
            raise ValidationError(self.reason or "That text is read-only")
        return encode_fixed_utf16le(value, self.allocation_bytes, self.label)

    def public_project_record(self, value: str) -> dict[str, object]:
        """Return the complete retail-free shareable edit representation."""

        self.validate_replacement(value)
        return {
            "asset_id": self.asset_id,
            "kind": SAFE_TEXT_PROJECT_KIND,
            "value": value,
        }

    def provider_edit(self, value: str) -> dict[str, object]:
        """Return the logical internal edit; physical offsets stay private."""

        self.validate_replacement(value)
        return {
            "kind": SAFE_TEXT_PROVIDER_KIND,
            "selector": self.selector,
            "text": value,
        }


@dataclass(frozen=True)
class SafeTextBank:
    bank_id: str
    kind: str
    outer_index: int
    chunk_index: int
    label: str
    decoded: bool
    editable_count: int
    read_only_count: int
    reason: str


@dataclass(frozen=True)
class SafeTextReplacement:
    """A re-resolved private patch span for a copied source archive."""

    asset_id: str
    selector: str
    pack_name: str
    pack_offset: int
    replacement: bytes = field(repr=False)
    preimage_sha256: str
    replacement_sha256: str

    @property
    def size(self) -> int:
        return len(self.replacement)


class SafeTextCatalog:
    """Strict STRG/SITU catalog and fixed-span replacement resolver."""

    def __init__(
        self,
        pack0: Path,
        inventory: Path,
        archive: Archive,
        banks: Sequence[SafeTextBank],
        assets: Sequence[SafeTextAsset],
        inventory_kind_counts: Mapping[str, int],
    ) -> None:
        self.pack0 = pack0
        self.inventory = inventory
        self.archive = archive
        self.banks = tuple(banks)
        self.assets = tuple(assets)
        self.inventory_kind_counts = {
            str(key): int(value) for key, value in inventory_kind_counts.items()
        }
        self._assets_by_id = _unique_assets(self.assets, "asset_id")
        self._assets_by_selector = _unique_assets(self.assets, "selector")

    @classmethod
    def from_paths(cls, pack0: Path, inventory: Path) -> "SafeTextCatalog":
        pack0 = pack0.expanduser().resolve(strict=True)
        inventory = inventory.expanduser().resolve(strict=True)
        try:
            document, records = parse_inventory(inventory)
            archive = parse_archive(pack0)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not open the private text index: {exc}") from exc

        declared = {
            str(key): int(value)
            for key, value in dict(
                document.get("summary", {}).get("resource_kind_counts", {})
            ).items()
        }
        actual = Counter(record.kind for record in records)
        for kind in TEXT_BANK_KINDS:
            if actual[kind] != declared.get(kind, 0):
                raise ValidationError(
                    f"Private text index count changed for {kind}: "
                    f"{actual[kind]} found, {declared.get(kind, 0)} declared"
                )

        selected = [
            record for record in records
            if record.kind in {"CRED", "SITU", "STRG", "TRIV"}
        ]
        expected = Counter({"CRED": 1, "SITU": 1, "STRG": 2, "TRIV": 1})
        if Counter(record.kind for record in selected) != expected:
            raise ValidationError("The supported fixed-text bank set is incomplete")

        banks: list[SafeTextBank] = []
        assets: list[SafeTextAsset] = []
        for record in sorted(selected, key=lambda item: (item.outer_index, item.chunk_index)):
            body = _load_uncompressed_body(archive, record)
            if record.kind == "STRG":
                bank, additions = _parse_strg_bank(archive, record, body)
            elif record.kind == "SITU":
                bank, additions = _parse_situ_bank(archive, record, body)
            elif record.kind == "CRED":
                bank, additions = _parse_cred_bank(archive, record, body)
            else:
                bank, additions = _parse_triv_bank(archive, record, body)
            banks.append(bank)
            assets.extend(additions)
        return cls(pack0, inventory, archive, banks, assets, declared)

    def get_asset(self, asset_id: str) -> SafeTextAsset:
        try:
            return self._assets_by_id[asset_id]
        except KeyError as exc:
            raise ValidationError(f"Unknown text asset: {asset_id}") from exc

    def get_selector(self, selector: str) -> SafeTextAsset:
        try:
            return self._assets_by_selector[selector]
        except KeyError as exc:
            raise ValidationError(f"Unknown text selector: {selector}") from exc

    def resolve_edit(self, selector: str, value: str) -> SafeTextReplacement:
        """Re-resolve and validate one edit against the private source cache."""

        asset = self.get_selector(selector)
        replacement = asset.validate_replacement(value)
        locator = asset._locator
        pack = self.pack0.parent / locator.pack_name
        current = _read_regular_span(pack, locator.pack_offset, locator.allocation_bytes)
        current_sha256 = hashlib.sha256(current).hexdigest()
        if current_sha256 != locator.preimage_sha256:
            raise ValidationError(
                f"Private source allocation changed for {asset.label}; reload the XISO"
            )
        return SafeTextReplacement(
            asset_id=asset.asset_id,
            selector=asset.selector,
            pack_name=locator.pack_name,
            pack_offset=locator.pack_offset,
            replacement=replacement,
            preimage_sha256=current_sha256,
            replacement_sha256=hashlib.sha256(replacement).hexdigest(),
        )

    def resolve_edits(
        self, edits: Iterable[Mapping[str, object]]
    ) -> tuple[SafeTextReplacement, ...]:
        """Resolve logical provider edits and reject duplicates/overlaps."""

        result: list[SafeTextReplacement] = []
        selectors: set[str] = set()
        for edit in edits:
            if edit.get("kind") != SAFE_TEXT_PROVIDER_KIND:
                raise ValidationError("Universal text edit has the wrong provider kind")
            selector = edit.get("selector")
            value = edit.get("text")
            if not isinstance(selector, str) or not isinstance(value, str):
                raise ValidationError("Universal text edit needs a selector and text")
            if selector in selectors:
                raise ValidationError(f"Duplicate universal text edit: {selector}")
            selectors.add(selector)
            result.append(self.resolve_edit(selector, value))

        ordered = sorted(result, key=lambda item: (item.pack_name, item.pack_offset))
        for left, right in zip(ordered, ordered[1:]):
            if left.pack_name == right.pack_name and \
                    left.pack_offset + left.size > right.pack_offset:
                raise ValidationError("Universal text replacement spans overlap")
        return tuple(ordered)

    def search(
        self,
        query: str = "",
        *,
        editable: bool | None = None,
        bank_kind: str | None = None,
    ) -> tuple[SafeTextAsset, ...]:
        terms = query.casefold().split()
        result: list[SafeTextAsset] = []
        for asset in self.assets:
            if editable is not None and asset.editable is not editable:
                continue
            if bank_kind is not None and asset.bank_kind != bank_kind:
                continue
            haystack = f"{asset.label}\n{asset.value}\n{asset.asset_id}".casefold()
            if all(term in haystack for term in terms):
                result.append(asset)
        return tuple(result)

    def audit_document(self) -> dict[str, object]:
        """Return counts/proof state only; decoded retail text is excluded."""

        by_kind = Counter(asset.bank_kind for asset in self.assets)
        editable = Counter(
            asset.bank_kind for asset in self.assets if asset.editable
        )
        read_only = Counter(
            asset.bank_kind for asset in self.assets if not asset.editable
        )
        return {
            "schema": SAFE_TEXT_AUDIT_SCHEMA,
            "inventory": {
                "bank_count": sum(
                    self.inventory_kind_counts.get(kind, 0) for kind in TEXT_BANK_KINDS
                ),
                "bank_kind_counts": {
                    kind: self.inventory_kind_counts.get(kind, 0)
                    for kind in sorted(TEXT_BANK_KINDS)
                },
            },
            "proved_fixed_allocation_banks": {
                "bank_count": len(self.banks),
                "asset_count": len(self.assets),
                "asset_counts": dict(sorted(by_kind.items())),
                "editable_count": sum(editable.values()),
                "editable_counts": dict(sorted(editable.items())),
                "read_only_count": sum(read_only.values()),
                "read_only_counts": dict(sorted(read_only.items())),
            },
            "constraints": {
                "encoding": "UTF-16LE",
                "fixed_allocation_only": True,
                "pointers_unchanged": True,
                "resource_sizes_unchanged": True,
                "strg_aliases_edit_together": True,
                "situ_display_fields_only": list(name for name, _ in SITU_DISPLAY_FIELDS),
                "situ_team_selectors_editable": False,
                "situ_scenario_logic_editable": False,
                "cred_nonempty_pool_editable": True,
                "cred_event_types_editable": False,
                "triv_display_fields_editable": list(
                    name for name, _ in TRIV_TEXT_FIELDS
                ),
                "triv_correct_answer_index_editable": False,
                "public_projects_include_original_text": False,
                "public_projects_include_raw_offsets": False,
            },
            "unresolved_bank_policy": {
                "NAME": "read_only_undecoded",
                "ROST": "handled_by_existing_bounded_roster_writer",
            },
        }


def encode_fixed_utf16le(value: str, allocation_bytes: int, label: str) -> bytes:
    """Encode one nonempty NUL-terminated value without moving its allocation."""

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
            f"{label} uses {used} UTF-16 units; this allocation allows {limit}. "
            "Some emoji and uncommon symbols use two units."
        )
    return encoded + b"\0\0" + bytes(allocation_bytes - required)


def _load_uncompressed_body(archive: Archive, record: ResourceRecord) -> bytes:
    if record.word_10 != 0:
        raise ValidationError(
            f"{record.kind} outer {record.outer_index} is compressed and remains read-only"
        )
    try:
        entry = archive.entries[record.outer_index]
        if entry.name_id != int(record.outer_id, 0) or entry.size != record.outer_size:
            raise ValidationError("Private archive directory and inventory disagree")
        span = read_entry_range(
            archive, entry, record.chunk_offset, WRAPPER_SIZE + record.stored_size
        )
        body, _detail = decode_resource(span, record)
    except (OSError, ValueError, IndexError) as exc:
        raise ValidationError(
            f"Could not decode {record.kind} outer {record.outer_index}: {exc}"
        ) from exc
    if len(body) != record.stored_size:
        raise ValidationError(
            f"{record.kind} outer {record.outer_index} changed size while decoding"
        )
    return body


@dataclass(frozen=True)
class _PointerPoolEntry:
    index: int
    start: int
    end: int
    value: str
    reference_count: int


@dataclass(frozen=True)
class _ParsedPointerPool:
    name: str
    descriptor_offset: int
    record_table_offset: int
    pool_offset: int
    entries: tuple[_PointerPoolEntry, ...]
    record_pool_indices: Mapping[tuple[int, str], int]


def _parse_pointer_pool(
    body: bytes,
    record: ResourceRecord,
    *,
    descriptor_offset: int,
    record_count: int,
    record_size: int,
    pointer_fields: Sequence[tuple[str, int]],
    numeric_fields: Sequence[int],
) -> _ParsedPointerPool:
    """Parse and byte-identically rebuild a fixed-record UTF-16 pointer pool."""

    marker = record.kind.encode("ascii")
    if body[0x0C:0x10] != marker or body[:0x0C] != bytes(0x0C):
        raise ValidationError(f"{record.kind} inner header differs from proof")
    name_offset = _relative_target(body, 0x10, f"{record.kind} name")
    descriptor = _relative_target(body, 0x14, f"{record.kind} descriptor")
    name, name_end = _utf16z(body, name_offset, f"{record.kind} name")
    if descriptor != descriptor_offset or name_end > descriptor:
        raise ValidationError(f"{record.kind} descriptor layout differs from proof")
    expected_prefix = bytearray(descriptor)
    expected_prefix[0x0C:0x10] = marker
    struct.pack_into("<i", expected_prefix, 0x10, name_offset - 0x10 + 1)
    struct.pack_into("<i", expected_prefix, 0x14, descriptor - 0x14 + 1)
    encoded_name = name.encode("utf-16le") + b"\0\0"
    expected_prefix[name_offset:name_offset + len(encoded_name)] = encoded_name
    if body[:descriptor] != expected_prefix:
        raise ValidationError(f"{record.kind} inner-header reserved bytes changed")
    count = struct.unpack_from("<I", body, descriptor)[0]
    if count != record_count:
        raise ValidationError(
            f"{record.kind} record count is {count}; expected {record_count}"
        )
    table = descriptor + 4
    pool = table + count * record_size
    if pool > len(body):
        raise ValidationError(f"{record.kind} record table exceeds its body")

    references: Counter[int] = Counter()
    decoded: dict[int, tuple[str, int]] = {}
    targets: dict[tuple[int, str], int] = {}
    for record_index in range(count):
        base = table + record_index * record_size
        for field_name, relative in pointer_fields:
            pointer_field = base + relative
            target = _relative_target(
                body,
                pointer_field,
                f"{record.kind} record {record_index} {field_name}",
            )
            if target < pool:
                raise ValidationError(f"{record.kind} pointer precedes its string pool")
            value, end = _utf16z(
                body, target, f"{record.kind} record {record_index} {field_name}"
            )
            prior = decoded.setdefault(target, (value, end))
            if prior != (value, end):
                raise ValidationError(f"{record.kind} alias decoding is inconsistent")
            references[target] += 1
            targets[(record_index, field_name)] = target

    pool_end = max((end for _value, end in decoded.values()), default=pool)
    cursor = pool
    entries: list[_PointerPoolEntry] = []
    while cursor < pool_end:
        value, end = _utf16z(body, cursor, f"{record.kind} pool entry")
        if decoded.get(cursor) != (value, end):
            raise ValidationError(
                f"{record.kind} pool has an unreferenced or interior allocation"
            )
        entries.append(_PointerPoolEntry(
            len(entries), cursor, end, value, references[cursor]
        ))
        cursor = end
    if set(decoded) != {item.start for item in entries}:
        raise ValidationError(f"{record.kind} pool/reference boundaries disagree")
    if len(body) - cursor != 10 or body[cursor:] != bytes(10):
        raise ValidationError(f"{record.kind} pool trailer differs from proof")

    # Reconstruct every declared field.  Only the bounded zero trailer is
    # retained; byte equality independently checks pointer encoding and pool
    # ownership rather than trusting a mutation of the source buffer.
    rebuilt = bytearray(len(body))
    rebuilt[:descriptor] = expected_prefix
    struct.pack_into("<I", rebuilt, descriptor, count)
    by_start = {item.start: item for item in entries}
    record_pool_indices: dict[tuple[int, str], int] = {}
    for record_index in range(count):
        base = table + record_index * record_size
        for relative in numeric_fields:
            rebuilt[base + relative:base + relative + 4] = \
                body[base + relative:base + relative + 4]
        for field_name, relative in pointer_fields:
            pointer_field = base + relative
            target = targets[(record_index, field_name)]
            struct.pack_into("<i", rebuilt, pointer_field, target - pointer_field + 1)
            record_pool_indices[(record_index, field_name)] = by_start[target].index
    for item in entries:
        encoded = item.value.encode("utf-16le") + b"\0\0"
        rebuilt[item.start:item.end] = encoded
    if bytes(rebuilt) != body:
        raise ValidationError(f"{record.kind} did not rebuild byte-identically")
    return _ParsedPointerPool(
        name=name,
        descriptor_offset=descriptor,
        record_table_offset=table,
        pool_offset=pool,
        entries=tuple(entries),
        record_pool_indices=record_pool_indices,
    )


def _parse_cred_bank(
    archive: Archive, record: ResourceRecord, body: bytes
) -> tuple[SafeTextBank, list[SafeTextAsset]]:
    if record.word_08 != 0 or record.word_0c != 0 or len(body) != 29_856:
        raise ValidationError("CRED wrapper/body layout differs from proof")
    parsed = _parse_pointer_pool(
        body,
        record,
        descriptor_offset=0x30,
        record_count=619,
        record_size=0x0C,
        pointer_fields=(("primary_text", 0x04), ("secondary_text", 0x08)),
        numeric_fields=(0x00,),
    )
    bank_id = f"nfl2k5.text-bank.cred.{record.outer_index}.{record.chunk_index}"
    assets: list[SafeTextAsset] = []
    for item in parsed.entries:
        allocation = item.end - item.start
        editable = allocation > 2
        assets.append(SafeTextAsset(
            asset_id=f"nfl2k5.text.cred.{record.outer_index}.{record.chunk_index}.{item.index}",
            selector=f"cred:{record.outer_index}:{record.chunk_index}:string:{item.index}",
            bank_id=bank_id,
            bank_kind="CRED",
            label=f"Credits string {item.index}",
            value=item.value,
            allocation_bytes=allocation,
            character_limit=allocation // 2 - 1,
            used_utf16_code_units=len(item.value.encode("utf-16le")) // 2,
            access=(SafeTextAccess.EDITABLE if editable else SafeTextAccess.READ_ONLY),
            reason=(
                "This fixed credits allocation is writable. Every event that "
                f"shares it updates together ({item.reference_count} references)."
                if editable else
                "This credits allocation contains only its terminator; no text fits."
            ),
            reference_count=item.reference_count,
            owner_index=item.index,
            field_name="text",
            provider_kind=SAFE_TEXT_PROVIDER_KIND if editable else None,
            _locator=_locator_for_body_span(
                archive, record, body, item.start, allocation
            ),
        ))
    return SafeTextBank(
        bank_id=bank_id,
        kind="CRED",
        outer_index=record.outer_index,
        chunk_index=record.chunk_index,
        label="Credits",
        decoded=True,
        editable_count=sum(asset.editable for asset in assets),
        read_only_count=sum(not asset.editable for asset in assets),
        reason=(
            "Both credit-event text pointers and their complete UTF-16 pool are "
            "decoded. Empty zero-capacity allocations remain read-only."
        ),
    ), assets


def _parse_triv_bank(
    archive: Archive, record: ResourceRecord, body: bytes
) -> tuple[SafeTextBank, list[SafeTextAsset]]:
    if record.word_08 != 691 or record.word_0c != 0 or len(body) != 242_848:
        raise ValidationError("TRIV wrapper/body layout differs from proof")
    parsed = _parse_pointer_pool(
        body,
        record,
        descriptor_offset=0x44,
        record_count=691,
        record_size=0x24,
        pointer_fields=TRIV_TEXT_FIELDS,
        numeric_fields=(0x00, 0x20),
    )
    # Every trivia string is uniquely owned.  Preserve the record/field identity
    # in logical selectors so projects stay stable without physical offsets.
    entries = {item.index: item for item in parsed.entries}
    bank_id = f"nfl2k5.text-bank.triv.{record.outer_index}.{record.chunk_index}"
    assets: list[SafeTextAsset] = []
    for question_index in range(691):
        for field_name, _relative in TRIV_TEXT_FIELDS:
            pool_index = parsed.record_pool_indices[(question_index, field_name)]
            item = entries[pool_index]
            if item.reference_count != 1:
                raise ValidationError("TRIV unexpectedly aliases a display string")
            allocation = item.end - item.start
            assets.append(SafeTextAsset(
                asset_id=f"nfl2k5.text.triv.question.{question_index}.{field_name}",
                selector=f"triv:question:{question_index}:{field_name}",
                bank_id=bank_id,
                bank_kind="TRIV",
                label=(
                    f"Trivia Question {question_index + 1} · "
                    f"{field_name.replace('_', ' ').title()}"
                ),
                value=item.value,
                allocation_bytes=allocation,
                character_limit=allocation // 2 - 1,
                used_utf16_code_units=len(item.value.encode("utf-16le")) // 2,
                access=SafeTextAccess.EDITABLE,
                reason=(
                    "This category/question/answer display string has a unique "
                    "fixed allocation. The numeric correct-answer key is unchanged."
                ),
                reference_count=1,
                owner_index=question_index,
                field_name=field_name,
                provider_kind=SAFE_TEXT_PROVIDER_KIND,
                _locator=_locator_for_body_span(
                    archive, record, body, item.start, allocation
                ),
            ))
    return SafeTextBank(
        bank_id=bank_id,
        kind="TRIV",
        outer_index=record.outer_index,
        chunk_index=record.chunk_index,
        label="Trivia questions",
        decoded=True,
        editable_count=len(assets),
        read_only_count=0,
        reason=(
            "Category, subject, question, and four answers are fixed-span editable. "
            "Correct-answer indices and unlock/progress state are unchanged."
        ),
    ), assets


def _parse_strg_bank(
    archive: Archive, record: ResourceRecord, body: bytes
) -> tuple[SafeTextBank, list[SafeTextAsset]]:
    try:
        table = parse_nfl_body(body, record)
        if rebuild_table(table) != body:
            raise ValidationError("STRG did not rebuild byte-identically")
    except (ValueError, IndexError, struct.error) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(
            f"Could not prove STRG outer {record.outer_index}: {exc}"
        ) from exc

    aliases = Counter(row.pool_index for row in table.records)
    bank_id = f"nfl2k5.text-bank.strg.{record.outer_index}.{record.chunk_index}"
    assets: list[SafeTextAsset] = []
    for item in table.pool:
        allocation = item.end_offset - item.offset
        editable = allocation > 2
        reason = (
            "Fixed allocation is safe. Editing this message updates all lookup "
            f"records that share it ({aliases[item.index]} reference"
            f"{'s' if aliases[item.index] != 1 else ''})."
            if editable else
            "This allocation contains only its terminator, so no nonempty text fits."
        )
        selector = (
            f"strg:{record.outer_index}:{record.chunk_index}:message:{item.index}"
        )
        locator = _locator_for_body_span(
            archive, record, body, item.offset, allocation
        )
        assets.append(SafeTextAsset(
            asset_id=(
                f"nfl2k5.text.strg.{record.outer_index}."
                f"{record.chunk_index}.{item.index}"
            ),
            selector=selector,
            bank_id=bank_id,
            bank_kind="STRG",
            label=f"String message {item.index}",
            value=item.text,
            allocation_bytes=allocation,
            character_limit=allocation // 2 - 1,
            used_utf16_code_units=len(item.text.encode("utf-16le")) // 2,
            access=(SafeTextAccess.EDITABLE if editable else SafeTextAccess.READ_ONLY),
            reason=reason,
            reference_count=aliases[item.index],
            owner_index=item.index,
            field_name="text",
            provider_kind=SAFE_TEXT_PROVIDER_KIND if editable else None,
            _locator=locator,
        ))
    editable_count = sum(asset.editable for asset in assets)
    return SafeTextBank(
        bank_id=bank_id,
        kind="STRG",
        outer_index=record.outer_index,
        chunk_index=record.chunk_index,
        label=f"String table · outer {record.outer_index}",
        decoded=True,
        editable_count=editable_count,
        read_only_count=len(assets) - editable_count,
        reason=(
            "Pool allocations are fixed-span editable. Shared allocations carry "
            "their alias count; zero-capacity allocations remain read-only."
        ),
    ), assets


def _parse_situ_bank(
    archive: Archive, record: ResourceRecord, body: bytes
) -> tuple[SafeTextBank, list[SafeTextAsset]]:
    if len(body) != record.stored_size or len(body) != 0x71B0:
        raise ValidationError("SITU body size differs from the proved layout")
    if body[0x0C:0x10] != b"SITU":
        raise ValidationError("SITU inner marker is missing")
    name = _relative_target(body, 0x10, "SITU name")
    descriptor = _relative_target(body, 0x14, "SITU descriptor")
    _name_value, name_end = _utf16z(body, name, "SITU name")
    if descriptor != SITU_DESCRIPTOR_OFFSET or name_end > descriptor:
        raise ValidationError("SITU header/descriptor layout differs from proof")
    count = struct.unpack_from("<I", body, descriptor)[0]
    if count != SITU_RECORD_COUNT or record.word_08 != count:
        raise ValidationError("SITU moment count differs from the proved 25 records")
    if SITU_RECORD_TABLE_OFFSET + count * SITU_RECORD_SIZE != SITU_POOL_OFFSET:
        raise ValidationError("Internal SITU record-table bounds are inconsistent")

    pointers: list[tuple[int, int, str, int]] = []
    # Parse all six pointer fields.  Only the first four are display text.
    for moment in range(count):
        base = SITU_RECORD_TABLE_OFFSET + moment * SITU_RECORD_SIZE
        for field_name, relative in (*SITU_DISPLAY_FIELDS, *SITU_SELECTOR_FIELDS):
            pointer_field = base + relative
            target = _relative_target(
                body, pointer_field, f"SITU moment {moment + 1} {field_name}"
            )
            if target < SITU_POOL_OFFSET:
                raise ValidationError("A SITU text pointer precedes the string pool")
            value, end = _utf16z(
                body, target, f"SITU moment {moment + 1} {field_name}"
            )
            pointers.append((target, end, value, pointer_field))

    if len({start for start, _end, _value, _field in pointers}) != len(pointers):
        raise ValidationError("SITU unexpectedly aliases two text allocations")
    cursor = SITU_POOL_OFFSET
    for start, end, _value, _field in sorted(pointers):
        if start != cursor:
            raise ValidationError("SITU string pool is not a contiguous owned sequence")
        cursor = end
    if body[cursor:] != bytes(len(body) - cursor):
        raise ValidationError("SITU string-pool trailer contains unknown data")

    by_field = {pointer_field: (start, end, value)
                for start, end, value, pointer_field in pointers}
    bank_id = f"nfl2k5.text-bank.situ.{record.outer_index}.{record.chunk_index}"
    assets: list[SafeTextAsset] = []
    for moment in range(count):
        base = SITU_RECORD_TABLE_OFFSET + moment * SITU_RECORD_SIZE
        for field_name, relative in (*SITU_DISPLAY_FIELDS, *SITU_SELECTOR_FIELDS):
            start, end, value = by_field[base + relative]
            allocation = end - start
            selector = f"situ:moment:{moment}:{field_name}"
            editable = field_name in {name for name, _ in SITU_DISPLAY_FIELDS}
            assets.append(SafeTextAsset(
                asset_id=f"nfl2k5.text.situ.moment.{moment}.{field_name}",
                selector=selector,
                bank_id=bank_id,
                bank_kind="SITU",
                label=(
                    f"25th Anniversary Moment {moment + 1} · "
                    f"{field_name.replace('_', ' ').title()}"
                ),
                value=value,
                allocation_bytes=allocation,
                character_limit=allocation // 2 - 1,
                used_utf16_code_units=len(value.encode("utf-16le")) // 2,
                access=(
                    SafeTextAccess.EDITABLE if editable else SafeTextAccess.READ_ONLY
                ),
                reason=(
                    "This display string has a unique fixed allocation and a "
                    "proved on-screen consumer. Scenario state is unchanged."
                    if editable else
                    "This string is a team-resource selector consumed by scenario "
                    "logic, not display copy. Its lookup constraints are not proved."
                ),
                reference_count=1,
                owner_index=moment,
                field_name=field_name,
                provider_kind=SAFE_TEXT_PROVIDER_KIND if editable else None,
                _locator=_locator_for_body_span(
                    archive, record, body, start, allocation
                ),
            ))
    return SafeTextBank(
        bank_id=bank_id,
        kind="SITU",
        outer_index=record.outer_index,
        chunk_index=record.chunk_index,
        label="ESPN 25th Anniversary moments",
        decoded=True,
        editable_count=sum(asset.editable for asset in assets),
        read_only_count=sum(not asset.editable for asset in assets),
        reason=(
            "Title, historical description, objective, and date are fixed-span "
            "editable. Team selectors and scenario-state fields remain read-only."
        ),
    ), assets


def _relative_target(body: bytes, field_offset: int, label: str) -> int:
    if field_offset < 0 or field_offset + 4 > len(body):
        raise ValidationError(f"{label} pointer field is out of bounds")
    stored = struct.unpack_from("<i", body, field_offset)[0]
    target = field_offset + stored - 1
    if not 0 <= target < len(body):
        raise ValidationError(f"{label} pointer resolves outside its resource")
    return target


def _utf16z(body: bytes, offset: int, label: str) -> tuple[str, int]:
    if offset < 0 or offset + 2 > len(body) or offset & 1:
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


def _locator_for_body_span(
    archive: Archive,
    record: ResourceRecord,
    body: bytes,
    body_offset: int,
    allocation_bytes: int,
) -> _PrivateLocator:
    if body_offset < 0 or allocation_bytes <= 0 or \
            body_offset + allocation_bytes > len(body):
        raise ValidationError("Text allocation exceeds its decoded resource")
    entry = archive.entries[record.outer_index]
    entry_relative = record.chunk_offset + WRAPPER_SIZE + body_offset
    pack_name, pack_offset = _physical_span(
        entry, entry_relative, allocation_bytes
    )
    preimage = body[body_offset:body_offset + allocation_bytes]
    return _PrivateLocator(
        outer_index=record.outer_index,
        chunk_index=record.chunk_index,
        body_offset=body_offset,
        allocation_bytes=allocation_bytes,
        pack_name=pack_name,
        pack_offset=pack_offset,
        preimage_sha256=hashlib.sha256(preimage).hexdigest(),
    )


def _physical_span(entry: Entry, relative_offset: int, size: int) -> tuple[str, int]:
    if relative_offset < 0 or size <= 0 or relative_offset + size > entry.size:
        raise ValidationError("Text span exceeds its outer archive entry")
    cursor = 0
    for segment in entry.segments:
        segment_end = cursor + segment.size
        if cursor <= relative_offset and relative_offset + size <= segment_end:
            return (
                segment.pack_name,
                segment.pack_offset + relative_offset - cursor,
            )
        cursor = segment_end
    raise ValidationError("Text allocation crosses archive packs and remains read-only")


def _read_regular_span(path: Path, offset: int, size: int) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise ValidationError(f"Private archive pack is not a regular file: {path}")
        with path.open("rb") as stream:
            stream.seek(offset)
            result = stream.read(size)
    except OSError as exc:
        raise ValidationError(f"Could not read private archive pack: {exc}") from exc
    if len(result) != size:
        raise ValidationError("Private archive pack ended inside a text allocation")
    return result


def _unique_assets(
    assets: Sequence[SafeTextAsset], attribute: str
) -> dict[str, SafeTextAsset]:
    result: dict[str, SafeTextAsset] = {}
    for asset in assets:
        key = str(getattr(asset, attribute))
        if key in result:
            raise ValidationError(f"Duplicate safe text {attribute}: {key}")
        result[key] = asset
    return result


__all__ = [
    "SAFE_TEXT_AUDIT_SCHEMA",
    "SAFE_TEXT_PROJECT_KIND",
    "SAFE_TEXT_PROVIDER_KIND",
    "SafeTextAccess",
    "SafeTextAsset",
    "SafeTextBank",
    "SafeTextCatalog",
    "SafeTextReplacement",
    "encode_fixed_utf16le",
]
