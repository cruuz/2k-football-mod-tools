"""Headless, read-only APF 2K8 specialized inspectors.

The product must derive these views from the user's selected game.  This
module therefore calls the existing evidence-backed parsers against
``ApfSource.index_0a`` and never reads the packaged research reports or
manifests.  Returned rows contain identities and decoded metadata only; there
is deliberately no replacement or archive-writing API here.
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, replace
from io import StringIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterable, Mapping

from .backend import ensure_tools_importable
from .models import (
    ApfSource,
    ExternalAudioBankIdentity,
    ExternalAudioBankOwner,
)
from .player_ratings import (
    PlayerRatingsError,
    load_player_rating_schema,
)
from .player_positions import load_player_position_schema
from .player_rating_sheet import (
    PLAYER_RATING_SHEET_FIELDS,
    PLAYER_RATING_SHEET_SCHEMA,
    RATING_COLUMNS,
    safe_text_cell,
)


ensure_tools_importable()
import apf_audio  # type: ignore  # noqa: E402
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_roster  # type: ignore  # noqa: E402
import apf_roster_identity_patch  # type: ignore  # noqa: E402
import apf_txt_loc  # type: ignore  # noqa: E402
import apf_uniform_inventory  # type: ignore  # noqa: E402
import director_inventory  # type: ignore  # noqa: E402
import playbook_inventory  # type: ignore  # noqa: E402


MAX_DECOMPRESSED = 256 * 1024 * 1024

EXPECTED_ROSTER_COUNTS = {
    "players": 2_254,
    "teams": 40,
    "stadiums": 31,
    "memberships": 1_344,
}
EXPECTED_LOCALIZATION_COUNTS = {
    "tables": 2,
    "records": 1_572,
    "distinct_texts": 1_279,
}
EXPECTED_PLAYBOOK_COUNTS = {
    "books": 1,
    "formations": 163,
    "plays": 586,
    "categories": 28,
    "route_nodes": 4_948,
    "slot_references": 6_446,
}
EXPECTED_DIRECTOR_COUNTS = {
    "resources": 5,
    "fixed_records": 137,
    "instructions": 1_623,
    "primary_strings": 120,
}
EXPECTED_SELECTOR_COUNTS = {
    "teams": 40,
    "banks": 80,
    "selectors": 1_120,
}
EXPECTED_AUDIO_COUNTS = {
    "audo": 2_261,
    "ausb_banks": 20,
    "ausb_substreams": 45_514,
    "external_bins": 19,
}
PLAYER_RATING_SCHEMA = load_player_rating_schema()
PLAYER_POSITION_SCHEMA = load_player_position_schema()

# These broad labels are intentionally less specific than cue names.  AUSB
# roles come from exact, source-owned bank names; AUDO roles are conservative
# name heuristics and carry that limitation on every row.
AUDIO_ROLE_LABELS: Mapping[str, str] = {
    "soundtrack_music": "Soundtrack & Music",
    "commentary_speech": "Commentary & Speech",
    "stadium_pa_chants": "Stadium PA & Chants",
    "presentation": "Presentation",
    "diagnostic_ambient": "Diagnostic & Ambient",
    "ui_menu_sfx": "UI & Menu SFX",
    "crowd_stadium": "Crowd & Stadium",
    "on_field_player": "On-field & Player",
    "general_sfx": "General / Unknown SFX",
}

AUSB_BANK_ROLE_IDS: Mapping[str, str] = {
    "cwdloop": "diagnostic_ambient",
    "cwdsurr": "diagnostic_ambient",
    "halftimeaudio": "presentation",
    "overlayaudio": "presentation",
    "animationaudio": "presentation",
    "wrapupm": "soundtrack_music",
    "jukeboxmusic": "soundtrack_music",
    "jukebox22": "soundtrack_music",
    "femusic": "soundtrack_music",
    "loadm": "soundtrack_music",
    "drafta": "presentation",
    "players": "commentary_speech",
    "lines": "commentary_speech",
    "teams": "commentary_speech",
    "pageneric": "stadium_pa_chants",
    "pascore": "stadium_pa_chants",
    "pachant": "stadium_pa_chants",
    "coacha": "stadium_pa_chants",
    "pasfx": "stadium_pa_chants",
}

_AUDO_CROWD_TOKENS = (
    "crowd",
    "clap",
    "cheer",
    "boo",
    "aww",
    "chant",
    "precheer",
    "whistle",
)
_AUDO_FIELD_TOKENS = (
    "grunt",
    "tackle",
    "block",
    "catch",
    "snap",
    "huddle",
    "bodyfall",
    "body_fall",
    "pad_hit",
    "impact",
    "footstep",
    "grab",
)

# Static roster/config ownership is proved for this exact retail revision.
# Runtime selector consumption and saved-team overrides remain unproved.
SELECTOR_BANKS: Mapping[int, Mapping[str, object]] = {
    0: {
        "label": "HOME",
        "config_start": 0,
        "config_end": 13,
        "mode": 1,
    },
    1: {
        "label": "AWAY",
        "config_start": 14,
        "config_end": 27,
        "mode": 0,
    },
}


class InspectorError(ValueError):
    """A selected source no longer satisfies a proved read-only contract."""


@dataclass(frozen=True)
class ExportIdentity:
    """Exact coordinates consumed by the existing read-only audio exporters."""

    kind: str
    outer_table_index: int
    inner_file_index: int
    substream_index: int | None
    suggested_basename: str
    supported_extensions: tuple[str, ...] = (".xma", ".wav")

    @property
    def exporter(self) -> str:
        if self.kind == "audo":
            return "apf_audio.export_selected"
        if self.kind == "ausb_substream":
            return "apf_ausb_audio.export_substream"
        raise InspectorError(f"Unknown audio export identity kind: {self.kind}")

    @property
    def coordinates(self) -> tuple[int, int, int | None]:
        return (
            self.outer_table_index,
            self.inner_file_index,
            self.substream_index,
        )


@dataclass(frozen=True)
class InspectorRow:
    row_id: str
    kind: str
    title: str
    subtitle: str
    fields: Mapping[str, object]
    export_identity: ExportIdentity | None = None
    external_bank_identity: ExternalAudioBankIdentity | None = None
    _search_text: str = ""

    def matches(self, search: str) -> bool:
        needle = search.strip().casefold()
        return not needle or needle in self._search_text


@dataclass(frozen=True)
class Page:
    items: tuple[InspectorRow, ...]
    total: int
    offset: int
    limit: int
    search: str
    kinds: tuple[str, ...]
    roles: tuple[str, ...]
    sources: tuple[str, ...]

    @property
    def next_offset(self) -> int | None:
        value = self.offset + len(self.items)
        return value if value < self.total else None

    @property
    def previous_offset(self) -> int | None:
        if self.offset <= 0:
            return None
        return max(0, self.offset - self.limit)


@dataclass(frozen=True)
class PagedModel:
    """Small UI-independent paging/search model, including the 45k bank rows."""

    rows: tuple[InspectorRow, ...]
    findings: tuple[str, ...] = ()

    def filtered_rows(
        self,
        *,
        search: str = "",
        kinds: str | Iterable[str] | None = None,
        roles: str | Iterable[str] | None = None,
        sources: str | Iterable[str] | None = None,
    ) -> tuple[InspectorRow, ...]:
        if kinds is None:
            selected_kinds: tuple[str, ...] = ()
        elif isinstance(kinds, str):
            selected_kinds = (kinds,)
        else:
            selected_kinds = tuple(dict.fromkeys(str(value) for value in kinds))
        if roles is None:
            selected_roles: tuple[str, ...] = ()
        elif isinstance(roles, str):
            selected_roles = (roles,)
        else:
            selected_roles = tuple(dict.fromkeys(str(value) for value in roles))
        if sources is None:
            selected_sources: tuple[str, ...] = ()
        elif isinstance(sources, str):
            selected_sources = (sources,)
        else:
            selected_sources = tuple(
                dict.fromkeys(str(value) for value in sources)
            )
        allowed = set(selected_kinds)
        allowed_roles = set(selected_roles)
        allowed_sources = set(selected_sources)

        def owns_any(
            row: InspectorRow,
            allowed_values: set[str],
            primary_field: str,
            linked_field: str,
        ) -> bool:
            if not allowed_values:
                return True
            primary = str(row.fields.get(primary_field, ""))
            linked_value = row.fields.get(linked_field, ())
            if isinstance(linked_value, str):
                linked = (linked_value,)
            elif isinstance(linked_value, Iterable):
                linked = tuple(str(value) for value in linked_value)
            else:
                linked = ()
            return primary in allowed_values or bool(
                allowed_values.intersection(linked)
            )

        return tuple(
            row
            for row in self.rows
            if (not allowed or row.kind in allowed)
            and owns_any(row, allowed_roles, "role_id", "linked_role_ids")
            and owns_any(
                row,
                allowed_sources,
                "audio_source_id",
                "linked_audio_source_ids",
            )
            and row.matches(search)
        )

    def page(
        self,
        *,
        search: str = "",
        kinds: str | Iterable[str] | None = None,
        roles: str | Iterable[str] | None = None,
        sources: str | Iterable[str] | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> Page:
        if offset < 0:
            raise InspectorError("Page offset cannot be negative")
        if not 1 <= limit <= 1_000:
            raise InspectorError("Page size must be between 1 and 1000")
        if kinds is None:
            selected_kinds: tuple[str, ...] = ()
        elif isinstance(kinds, str):
            selected_kinds = (kinds,)
        else:
            selected_kinds = tuple(dict.fromkeys(str(value) for value in kinds))
        if roles is None:
            selected_roles: tuple[str, ...] = ()
        elif isinstance(roles, str):
            selected_roles = (roles,)
        else:
            selected_roles = tuple(dict.fromkeys(str(value) for value in roles))
        if sources is None:
            selected_sources: tuple[str, ...] = ()
        elif isinstance(sources, str):
            selected_sources = (sources,)
        else:
            selected_sources = tuple(
                dict.fromkeys(str(value) for value in sources)
            )
        matches = self.filtered_rows(
            search=search,
            kinds=selected_kinds,
            roles=selected_roles,
            sources=selected_sources,
        )
        return Page(
            items=tuple(matches[offset : offset + limit]),
            total=len(matches),
            offset=offset,
            limit=limit,
            search=search,
            kinds=selected_kinds,
            roles=selected_roles,
            sources=selected_sources,
        )

    def get(self, row_id: str) -> InspectorRow:
        for row in self.rows:
            if row.row_id == row_id:
                return row
        raise InspectorError(f"Unknown inspector row: {row_id}")

    @property
    def kind_counts(self) -> Mapping[str, int]:
        return dict(sorted(Counter(row.kind for row in self.rows).items()))

    @property
    def role_counts(self) -> Mapping[str, int]:
        return dict(
            sorted(
                Counter(
                    str(row.fields["role_id"])
                    for row in self.rows
                    if row.fields.get("role_id")
                ).items()
            )
        )

    @property
    def audio_sources(self) -> tuple[tuple[str, str, int], ...]:
        """Return stable source IDs, labels, and playable-row counts in UI order."""

        counts = Counter(
            str(row.fields["audio_source_id"])
            for row in self.rows
            if row.export_identity is not None
            and row.fields.get("audio_source_id")
        )
        seen: set[str] = set()
        sources: list[tuple[str, str, int]] = []
        for row in self.rows:
            source_id = str(row.fields.get("audio_source_id") or "")
            if not source_id or source_id in seen:
                continue
            seen.add(source_id)
            label = str(row.fields.get("audio_source_label") or source_id)
            sources.append((source_id, label, counts[source_id]))
        return tuple(sources)


def _semantic_row_document(row: InspectorRow) -> dict[str, object]:
    document: dict[str, object] = {
        "row_id": row.row_id,
        "kind": row.kind,
        "title": row.title,
        "subtitle": row.subtitle,
        "fields": dict(row.fields),
    }
    if row.export_identity is not None:
        document["export_identity"] = {
            "exporter": row.export_identity.exporter,
            "coordinates": row.export_identity.coordinates,
            "suggested_basename": row.export_identity.suggested_basename,
            "supported_extensions": row.export_identity.supported_extensions,
        }
    if row.external_bank_identity is not None:
        identity = row.external_bank_identity
        document["external_bank_identity"] = {
            "external_filename": identity.external_filename,
            "outer_table_index": identity.outer_table_index,
            "name_id": f"0x{identity.name_id:08x}",
            "encoded_size": identity.encoded_size,
            "raw_asset_id": identity.raw_asset_id,
            "descriptor_coordinates": [
                owner.coordinates for owner in identity.owners
            ],
        }
    return document


def export_semantic_rows(
    model: PagedModel,
    destination: Path,
    *,
    search: str = "",
    kinds: str | Iterable[str] | None = None,
    roles: str | Iterable[str] | None = None,
    sources: str | Iterable[str] | None = None,
) -> Path:
    """Export the current decoded inspector selection as useful JSON or CSV.

    The data is derived locally from the user's game. It is never bundled into
    the application or a shareable mod project, and publication never replaces
    an existing destination.
    """

    destination = destination.expanduser()
    suffix = destination.suffix.casefold()
    if suffix not in {".json", ".csv"}:
        raise InspectorError("Decoded inspector exports must end in .json or .csv")
    if kinds is None:
        selected_kinds: tuple[str, ...] = ()
    elif isinstance(kinds, str):
        selected_kinds = (kinds,)
    else:
        selected_kinds = tuple(dict.fromkeys(str(value) for value in kinds))
    if roles is None:
        selected_roles: tuple[str, ...] = ()
    elif isinstance(roles, str):
        selected_roles = (roles,)
    else:
        selected_roles = tuple(dict.fromkeys(str(value) for value in roles))
    if sources is None:
        selected_sources: tuple[str, ...] = ()
    elif isinstance(sources, str):
        selected_sources = (sources,)
    else:
        selected_sources = tuple(dict.fromkeys(str(value) for value in sources))
    rows = model.filtered_rows(
        search=search,
        kinds=selected_kinds,
        roles=selected_roles,
        sources=selected_sources,
    )
    if suffix == ".json":
        payload = (
            json.dumps(
                {
                    "schema": "apf2k8_mod_studio_semantic_export/v1",
                    "record_count": len(rows),
                    "filter": {
                        "search": search,
                        "kinds": selected_kinds,
                        "roles": selected_roles,
                        "sources": selected_sources,
                    },
                    "findings": model.findings,
                    "records": [_semantic_row_document(row) for row in rows],
                    "distribution_note": (
                        "Local retail-derived metadata from the user's own game; "
                        "not part of Mod Studio or a shareable project."
                    ),
                },
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            + "\n"
        ).encode("utf-8")
    else:
        stream = StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "row_id",
                "kind",
                "title",
                "subtitle",
                "fields_json",
                "export_identity_json",
                "filter_search",
                "filter_kinds_json",
                "filter_roles_json",
                "filter_sources_json",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            document = _semantic_row_document(row)
            writer.writerow(
                {
                    "row_id": row.row_id,
                    "kind": row.kind,
                    "title": row.title,
                    "subtitle": row.subtitle,
                    "fields_json": json.dumps(
                        document["fields"],
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    "export_identity_json": json.dumps(
                        document.get("export_identity"),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    if "export_identity" in document
                    else "",
                    "filter_search": search,
                    "filter_kinds_json": json.dumps(selected_kinds),
                    "filter_roles_json": json.dumps(selected_roles),
                    "filter_sources_json": json.dumps(selected_sources),
                }
            )
        payload = stream.getvalue().encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".exporting",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.link(temporary, destination)
        temporary.unlink()
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return destination


def export_player_rating_sheet(
    model: PagedModel,
    destination: Path,
    *,
    source_sha256: str,
    value_resolver: Callable[[int, str], int] | None = None,
) -> Path:
    """Export one private, spreadsheet-friendly row per on-disc player.

    This is deliberately an inspection/export route, not a writer. The CSV is
    derived from the user's own game and never enters a shareable project or
    the retail-free application package. Publication is atomic and refuses an
    existing destination.
    """

    destination = destination.expanduser()
    if destination.suffix.casefold() != ".csv":
        raise InspectorError("The complete APF player ratings sheet must end in .csv")
    players = tuple(row for row in model.rows if row.kind == "player")
    expected_count = EXPECTED_ROSTER_COUNTS["players"]
    if len(players) != expected_count:
        raise InspectorError(
            f"APF ratings sheet found {len(players):,} players; expected "
            f"exactly {expected_count:,}"
        )
    indexes = tuple(row.fields.get("player_index") for row in players)
    if indexes != tuple(range(expected_count)):
        raise InspectorError(
            "APF ratings sheet requires every unique player index in exact 0..2253 order"
        )

    if not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise InspectorError("The loaded APF game fingerprint is invalid")
    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=PLAYER_RATING_SHEET_FIELDS, lineterminator="\n"
    )
    writer.writeheader()
    for expected_index, row in enumerate(players):
        raw_ratings = row.fields.get("base_ratings")
        if not isinstance(raw_ratings, (tuple, list)) or len(raw_ratings) != 28:
            raise InspectorError(
                f"APF player {expected_index} does not expose all 28 base ratings"
            )
        rating_values: dict[str, int] = {}
        observed_ids: list[str] = []
        for rating_index, raw_rating in enumerate(raw_ratings):
            if not isinstance(raw_rating, Mapping):
                raise InspectorError(
                    f"APF player {expected_index} rating {rating_index} is malformed"
                )
            field_id = raw_rating.get("id")
            value = raw_rating.get("value")
            if not isinstance(field_id, str) or isinstance(value, bool) or not isinstance(value, int):
                raise InspectorError(
                    f"APF player {expected_index} rating {rating_index} has invalid ID/value"
                )
            observed_ids.append(field_id)
            rating_values[field_id] = value
        expected_ids = [field.field_id for field in PLAYER_RATING_SCHEMA.fields]
        if observed_ids != expected_ids or len(rating_values) != 28:
            raise InspectorError(
                f"APF player {expected_index} rating order or identity changed"
            )
        try:
            canonical_rows = PLAYER_RATING_SCHEMA.field_rows(rating_values)
        except PlayerRatingsError as exc:
            raise InspectorError(
                f"APF player {expected_index} base ratings are invalid: {exc}"
            ) from exc
        team_names = row.fields.get("team_names", ())
        if not isinstance(team_names, (tuple, list)) or not all(
            isinstance(value, str) for value in team_names
        ):
            raise InspectorError(
                f"APF player {expected_index} team membership labels are malformed"
            )
        output: dict[str, object] = {
            "schema": PLAYER_RATING_SHEET_SCHEMA,
            "source_sha256": source_sha256,
            "player_index": expected_index,
            "first_name": safe_text_cell(row.fields.get("first_name", "")),
            "last_name": safe_text_cell(row.fields.get("last_name", "")),
            "display_name": safe_text_cell(row.title),
            "position_code": row.fields.get("position_code", ""),
            "position_abbreviation": safe_text_cell(
                row.fields.get("position_abbreviation", "")
            ),
            "position_name": safe_text_cell(row.fields.get("position_name", "")),
            "team_names": safe_text_cell(" | ".join(team_names)),
            "native_rating_minimum": PLAYER_RATING_SCHEMA.native_minimum,
            "native_rating_maximum": PLAYER_RATING_SCHEMA.native_maximum,
            "stock_observed_minimum": PLAYER_RATING_SCHEMA.stock_observed_minimum,
            "stock_observed_maximum": PLAYER_RATING_SCHEMA.stock_observed_maximum,
        }
        for rating in canonical_rows:
            field_id = str(rating["id"])
            value = int(rating["value"])
            if value_resolver is not None:
                value = value_resolver(expected_index, field_id)
            if not 0 <= value <= 100:
                raise InspectorError(
                    f"APF player {expected_index} {field_id} is outside native 0..100"
                )
            output[f"rating.{field_id}"] = value
        if tuple(key for key in output if key.startswith("rating.")) != RATING_COLUMNS:
            raise InspectorError("APF player-rating export column order changed")
        writer.writerow(output)

    payload = stream.getvalue().encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".exporting",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(payload)
            output.flush()
            os.fchmod(output.fileno(), 0o600)
            os.fsync(output.fileno())
        os.link(temporary, destination)
        temporary.unlink()
    except FileExistsError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise InspectorError(
            "The ratings sheet destination already exists; choose a new filename"
        ) from exc
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
        raise
    return destination


@dataclass(frozen=True)
class RosterSnapshot:
    summary: Mapping[str, int]
    model: PagedModel


@dataclass(frozen=True)
class LocalizationSnapshot:
    summary: Mapping[str, int]
    records: PagedModel
    pool: PagedModel


@dataclass(frozen=True)
class PlaybookDirectorSnapshot:
    playbook_summary: Mapping[str, int]
    director_summary: Mapping[str, int]
    playbooks: PagedModel
    directors: PagedModel


@dataclass(frozen=True)
class UniformSelectorSnapshot:
    summary: Mapping[str, int]
    model: PagedModel


@dataclass(frozen=True)
class AudioSnapshot:
    summary: Mapping[str, int]
    audo: PagedModel
    ausb_banks: PagedModel
    ausb_substreams: PagedModel
    external_banks: PagedModel


@dataclass(frozen=True)
class InspectorBundle:
    roster: RosterSnapshot
    localization: LocalizationSnapshot
    playbooks_directors: PlaybookDirectorSnapshot
    uniform_selectors: UniformSelectorSnapshot
    audio: AudioSnapshot


def _json_search(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _row(
    row_id: str,
    kind: str,
    title: str,
    subtitle: str,
    fields: Mapping[str, object],
    *,
    export_identity: ExportIdentity | None = None,
    external_bank_identity: ExternalAudioBankIdentity | None = None,
) -> InspectorRow:
    search_text = " ".join(
        (row_id, kind, title, subtitle, _json_search(fields))
    ).casefold()
    return InspectorRow(
        row_id=row_id,
        kind=kind,
        title=title,
        subtitle=subtitle,
        fields=dict(fields),
        export_identity=export_identity,
        external_bank_identity=external_bank_identity,
        _search_text=search_text,
    )


def _require_counts(
    label: str,
    actual: Mapping[str, int],
    expected: Mapping[str, int],
) -> None:
    changed = {
        key: (actual.get(key), value)
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if changed:
        detail = ", ".join(
            f"{key}={found} (expected {wanted})"
            for key, (found, wanted) in changed.items()
        )
        raise InspectorError(f"{label} inventory changed: {detail}")


def _full_name(player: Mapping[str, object]) -> str:
    value = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
    return value or f"Unnamed player {int(player['player_index']):04d}"


def inspect_roster(source: ApfSource) -> RosterSnapshot:
    """Decode the live ROST resource into searchable, bounded product rows."""

    try:
        data, source_document = apf_roster.load_roster(source.index_0a)
        report = apf_roster.build_report(data, source_document)
    except (apf_roster.RosterError, apf_inner.FormatError, OSError) as exc:
        raise InspectorError(f"Could not inspect the APF roster: {exc}") from exc

    players = list(report["players"])
    teams = list(report["teams"])
    stadiums = list(report["stadiums"])
    memberships = list(report["team_roster_memberships"])
    summary = {
        "players": len(players),
        "teams": len(teams),
        "stadiums": len(stadiums),
        "memberships": len(memberships),
    }
    _require_counts("APF roster", summary, EXPECTED_ROSTER_COUNTS)

    try:
        identity_allocations = apf_roster_identity_patch.inventory_from_decoded(
            data
        )
    except apf_roster_identity_patch.RosterIdentityError as exc:
        raise InspectorError(f"Could not map APF roster-name edits: {exc}") from exc
    identity_by_owner = {
        owner.owner_id: allocation
        for allocation in identity_allocations
        for owner in allocation.known_owners
    }

    def identity_field(
        entity_kind: str, entity_index: int, field: str
    ) -> Mapping[str, object]:
        owner_id = f"{entity_kind}:{entity_index}:{field}"
        try:
            allocation = identity_by_owner[owner_id]
        except KeyError as exc:
            raise InspectorError(
                f"Mapped roster identity owner is missing: {owner_id}"
            ) from exc
        edit_scope = apf_roster_identity_patch.roster_identity_edit_scope(
            allocation
        )
        return {
            "asset_id": allocation.asset_id,
            "maximum_characters": allocation.maximum_utf16_units,
            "editable": allocation.editable,
            # Product authoring remains narrower than the decoded identity map.
            # The centralized scope admits only pure team display-name or pure
            # player first/last aliases with positive capacity.
            "runtime_editable": edit_scope is not None,
            "runtime_edit_scope": edit_scope,
            "known_alias_count": allocation.known_owner_count,
            # Local inspection metadata only.  These semantic coordinates make
            # shared edits understandable without exposing retail names or
            # persisting any owner list in a shareable project.
            "known_alias_owners": tuple(
                {
                    "entity_kind": owner.entity_kind,
                    "entity_index": owner.entity_index,
                    "field": owner.field,
                    "label": (
                        f"{owner.entity_kind.title()} {owner.entity_index} · "
                        f"{owner.field.replace('_', ' ')}"
                    ),
                }
                for owner in allocation.known_owners
            ),
            "note": allocation.note,
        }

    rows: list[InspectorRow] = []
    for player in players:
        index = int(player["player_index"])
        values = player.get("base_ratings")
        if not isinstance(values, dict):
            raise InspectorError(
                f"APF roster player {index} is missing its exact base-rating mapping"
            )
        try:
            base_ratings = PLAYER_RATING_SCHEMA.field_rows(values)
        except PlayerRatingsError as exc:
            raise InspectorError(
                f"APF roster player {index} base ratings are invalid: {exc}"
            ) from exc
        team_names = tuple(
            str(item["team_name"]) for item in player.get("team_memberships", ())
        )
        rows.append(
            _row(
                f"apf:roster:player:{index}",
                "player",
                _full_name(player),
                f"#{index:04d} · {player['position_abbreviation']}",
                {
                    "player_index": index,
                    "first_name": player["first_name"],
                    "last_name": player["last_name"],
                    "identity_editor": {
                        "first_name": identity_field(
                            "player", index, "first_name"
                        ),
                        "last_name": identity_field(
                            "player", index, "last_name"
                        ),
                    },
                    "jersey_number_edit_status": dict(
                        apf_roster_identity_patch.JERSEY_NUMBER_FINDING
                    ),
                    "position_code": player["position_code"],
                    "position_abbreviation": player["position_abbreviation"],
                    "position_name": player["position_name"],
                    "position_editor": {
                        "asset_id": f"apf:player-position:{index}",
                        "editable": True,
                        "backend_editable": True,
                        "gui_status": "semantic_dropdown_enabled",
                        "semantic_relative_offset": (
                            PLAYER_POSITION_SCHEMA.semantic_relative_offset
                        ),
                        "mirror_relative_offset": (
                            PLAYER_POSITION_SCHEMA.mirror_relative_offset
                        ),
                        "source_mirror_required": True,
                        "runtime_status": PLAYER_POSITION_SCHEMA.runtime_status,
                        "runtime_reason": PLAYER_POSITION_SCHEMA.runtime_reason,
                        "choices": tuple(
                            {
                                "code": position.code,
                                "abbreviation": position.abbreviation,
                                "name": position.name,
                            }
                            for position in PLAYER_POSITION_SCHEMA.positions
                        ),
                    },
                    "base_ratings": base_ratings,
                    "base_rating_scale": {
                        "native_minimum": PLAYER_RATING_SCHEMA.native_minimum,
                        "native_maximum": PLAYER_RATING_SCHEMA.native_maximum,
                        "stock_observed_minimum": PLAYER_RATING_SCHEMA.stock_observed_minimum,
                        "stock_observed_maximum": PLAYER_RATING_SCHEMA.stock_observed_maximum,
                        "display_policy": PLAYER_RATING_SCHEMA.display_policy,
                        "runtime_status": PLAYER_RATING_SCHEMA.runtime_status,
                    },
                    "team_names": team_names,
                    "team_memberships": tuple(player.get("team_memberships", ())),
                    "biography_and_accolade_strings": dict(player.get("strings", {})),
                    "hall_of_fame_year": player[
                        "hall_of_fame_induction_year_at_0x112"
                    ],
                    "championship_count": player["championship_count_at_0x114"],
                    "championship_game_appearances": player[
                        "championship_game_appearance_count_at_0x115"
                    ],
                    "all_pro_game_count": player["all_pro_game_count_at_0x116"],
                },
            )
        )
    for team in teams:
        index = int(team["team_index"])
        title = str(team["display_name"] or f"Team {index}")
        rows.append(
            _row(
                f"apf:roster:team:{index}",
                "team",
                title,
                f"{team['abbreviation']} · {team['derived_slot_kind']}",
                {
                    "team_index": index,
                    "display_name": team["display_name"],
                    "abbreviation": team["abbreviation"],
                    "secondary_abbreviation": team["secondary_abbreviation"],
                    "identity_editor": {
                        "display_name": identity_field(
                            "team", index, "display_name"
                        ),
                        "abbreviation": identity_field(
                            "team", index, "abbreviation"
                        ),
                        "secondary_abbreviation": identity_field(
                            "team", index, "secondary_abbreviation"
                        ),
                    },
                    "numeric_string_code": team["numeric_string_code"],
                    "slot_kind": team["derived_slot_kind"],
                    "roster_count": team["roster_count"],
                    "stadium_index": team["stadium_index"],
                    "stadium_name": team["stadium_name"],
                },
            )
        )
    for stadium in stadiums:
        index = int(stadium["stadium_index"])
        rows.append(
            _row(
                f"apf:roster:stadium:{index}",
                "stadium",
                str(stadium["display_name"]),
                f"Capacity {int(stadium['capacity']):,}",
                {
                    "stadium_index": index,
                    "display_name": stadium["display_name"],
                    "asset_key": stadium["asset_key"],
                    "capacity": stadium["capacity"],
                    "description": stadium["description"],
                },
            )
        )
    for membership in memberships:
        team_index = int(membership["team_index"])
        player_index = int(membership["player_index"])
        team = teams[team_index]
        player = players[player_index]
        slot = int(membership["roster_slot"])
        rows.append(
            _row(
                f"apf:roster:membership:{team_index}:{slot}",
                "membership",
                _full_name(player),
                f"{team['display_name']} · roster slot {slot}",
                {
                    "team_index": team_index,
                    "team_name": team["display_name"],
                    "roster_slot": slot,
                    "player_index": player_index,
                    "player_name": _full_name(player),
                    "position": player["position_abbreviation"],
                },
            )
        )
    return RosterSnapshot(
        summary=summary,
        model=PagedModel(
            tuple(rows),
            (
                "Editable: every player exposes 27 executable-named base ratings plus neutral Unknown Rating 24 as exact 0–99 values; an existing native source 100 stays visible and can be preserved or reverted without authoring a new 100.",
                "Editable now: all 40 existing team display-name allocations and every pure player first/last-name allocation use exact UTF-16BE limits and the runtime-proved token-preserving ROST transport.",
                "Shared player-name aliases remain editable and disclose how many first/last fields change together; mixed-owner, zero-capacity, unknown, and both team-abbreviation scopes remain runtime-locked.",
                "Still unmapped: star tier, effective runtime modifiers, appearance, equipment, abilities, and behavior remain separate research lanes.",
                "Jersey numbers remain read-only because no consumer-backed packed field has been identified.",
            ),
        ),
    )


def inspect_localization(
    source: ApfSource,
    *,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> LocalizationSnapshot:
    """Parse both live English localization tables and their complete pools."""

    try:
        tables = apf_txt_loc.parse_archive(source.index_0a, max_decompressed)
    except (apf_txt_loc.TextError, apf_inner.FormatError, OSError) as exc:
        raise InspectorError(f"Could not inspect APF localization: {exc}") from exc
    all_records = [record for table in tables for record in table["records"]]
    all_pool = [item for table in tables for item in table["pool"]]
    summary = {
        "tables": len(tables),
        "records": len(all_records),
        # The proved report defines this over pool strings, including fallback.
        "distinct_texts": len({str(item["text"]) for item in all_pool}),
        "pool_entries": len(all_pool),
        "control_records": sum(bool(item["is_control_record"]) for item in all_records),
    }
    _require_counts("APF localization", summary, EXPECTED_LOCALIZATION_COUNTS)
    if not all(bool(table.get("byte_identical_rebuild")) for table in tables):
        raise InspectorError("APF localization no longer rebuilds byte-identically")

    record_rows = tuple(
        _row(
            f"apf:text:{record['outer_index']}:{record['inner_index']}:{record['record_index']}",
            "localization_record",
            str(record["text"] if record["text"] is not None else "<control record>"),
            f"{record['table_name']} · {record['text_id']}",
            {
                "outer_index": record["outer_index"],
                "inner_index": record["inner_index"],
                "table_name": record["table_name"],
                "record_index": record["record_index"],
                "text_id": record["text_id"],
                "is_control_record": record["is_control_record"],
                "pool_index": record["pool_index"],
                "text": record["text"],
            },
        )
        for record in all_records
    )
    pool_rows = tuple(
        _row(
            f"apf:text-pool:{table['outer_index']}:{table['inner_index']}:{item['pool_index']}",
            "localization_pool_string",
            str(item["text"]),
            f"{table['inner_name']} · pool {item['pool_index']}",
            {
                "outer_index": table["outer_index"],
                "inner_index": table["inner_index"],
                "table_name": table["inner_name"],
                "pool_index": item["pool_index"],
                "offset": item["offset"],
                "text": item["text"],
                "referenced": int(item["pool_index"])
                not in set(int(value) for value in table["unreferenced_pool_indices"]),
            },
        )
        for table in tables
        for item in table["pool"]
    )
    findings = (
        "Both English tables are structurally decoded and serialize byte-identically.",
        "Read-only: safe in-archive replacement/allocation transport is not exposed by this inspector.",
    )
    return LocalizationSnapshot(
        summary=summary,
        records=PagedModel(record_rows, findings),
        pool=PagedModel(pool_rows, findings),
    )


def inspect_playbooks_directors(
    source: ApfSource,
    *,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> PlaybookDirectorSnapshot:
    """Build structural PLAY and DRCT viewers from the selected live archive."""

    try:
        books = playbook_inventory.parse_apf(source.index_0a, max_decompressed)
        directors = director_inventory.parse_apf(source.index_0a, max_decompressed)
    except (
        playbook_inventory.PlaybookError,
        director_inventory.DirectorError,
        apf_inner.FormatError,
        OSError,
    ) as exc:
        raise InspectorError(f"Could not inspect APF play data: {exc}") from exc

    play_summary = {
        "books": len(books),
        "formations": sum(len(book["formations"]) for book in books),
        "plays": sum(len(book["plays"]) for book in books),
        "categories": sum(len(book["categories"]) for book in books),
        "route_nodes": sum(int(book["root_counts"]["route_node_count"]) for book in books),
        "slot_references": sum(
            len(play["slots"]) for book in books for play in book["plays"]
        ),
    }
    director_summary = {
        "resources": len(directors),
        "fixed_records": sum(
            len(item["graph"]["fixed_records"]) for item in directors
        ),
        "instructions": sum(
            len(item["graph"]["instructions"]) for item in directors
        ),
        "primary_strings": sum(
            len(item["graph"]["strings"]) for item in directors
        ),
    }
    _require_counts("APF playbook", play_summary, EXPECTED_PLAYBOOK_COUNTS)
    _require_counts("APF director", director_summary, EXPECTED_DIRECTOR_COUNTS)

    play_rows: list[InspectorRow] = []
    for book in books:
        outer = int(book["outer_index"])
        play_rows.append(
            _row(
                f"apf:playbook:{outer}:{book['inner_index']}",
                "playbook",
                str(book["book_name"]),
                f"Outer {outer} · {book['inner_name']}",
                {
                    "outer_index": outer,
                    "inner_index": book["inner_index"],
                    "book_name": book["book_name"],
                    **dict(book["root_counts"]),
                },
            )
        )
        for kind, key in (
            ("category", "categories"),
            ("formation", "formations"),
            ("play", "plays"),
        ):
            for item in book[key]:
                fields: dict[str, object] = {
                    "outer_index": outer,
                    "book_name": book["book_name"],
                    "index": item["index"],
                    "name": item["name"],
                    "offset": item["offset"],
                    "size": item["size"],
                }
                if kind == "play":
                    fields.update(
                        {
                            "flags_or_id_04": item.get("flags_or_id_04"),
                            "unknown_word_08": item.get("unknown_word_08"),
                            "slot_route_node_indices": tuple(
                                int(slot["route_node_index"])
                                for slot in item["slots"]
                            ),
                        }
                    )
                play_rows.append(
                    _row(
                        f"apf:playbook:{outer}:{kind}:{item['index']}",
                        kind,
                        str(item["name"]),
                        f"{book['book_name']} · {kind} {item['index']}",
                        fields,
                    )
                )
        route_blob = bytes.fromhex(str(book["route_node_blob_hex"]))
        route_count = int(book["root_counts"]["route_node_count"])
        if len(route_blob) != route_count * playbook_inventory.ROUTE_NODE_SIZE:
            raise InspectorError("APF route-node blob length changed")
        for index in range(route_count):
            raw = route_blob[
                index * playbook_inventory.ROUTE_NODE_SIZE :
                (index + 1) * playbook_inventory.ROUTE_NODE_SIZE
            ]
            play_rows.append(
                _row(
                    f"apf:playbook:{outer}:route-node:{index}",
                    "route_node",
                    f"Route node {index}",
                    "Opaque 8-byte node",
                    {"index": index, "raw_hex": raw.hex()},
                )
            )

    director_rows: list[InspectorRow] = []
    for resource in directors:
        outer = int(resource["outer_index"])
        role = str(resource["role"])
        graph = resource["graph"]
        director_rows.append(
            _row(
                f"apf:director:{outer}",
                "director_resource",
                role.title(),
                str(resource["outer_name"]),
                {
                    "outer_index": outer,
                    "inner_index": resource["inner_index"],
                    "role": role,
                    "fixed_record_count": graph["nonnull_fixed_record_count"],
                    "instruction_count": graph["instruction_count"],
                    "primary_string_count": graph["string_count"],
                },
            )
        )
        for item in graph["fixed_records"]:
            director_rows.append(
                _row(
                    f"apf:director:{outer}:fixed:{item['slot_index']}",
                    "director_fixed_record",
                    f"{role.title()} fixed slot {item['slot_index']}",
                    f"{item['child_count']} child references",
                    {
                        "role": role,
                        "slot_index": item["slot_index"],
                        "ordinal": item["ordinal"],
                        "offset": item["offset"],
                        "package_size": item["package_size"],
                        "child_count": item["child_count"],
                        "unknown_u16_04": item["unknown_u16_04"],
                        "unknown_u16_06": item["unknown_u16_06"],
                    },
                )
            )
        for item in graph["instructions"]:
            director_rows.append(
                _row(
                    f"apf:director:{outer}:instruction:{item['index']}",
                    "director_instruction",
                    f"{role.title()} instruction {item['index']}",
                    f"{item['size']} opaque bytes",
                    {
                        "role": role,
                        "index": item["index"],
                        "offset": item["offset"],
                        "size": item["size"],
                        "first_byte": item["first_byte"],
                        "head_hex": item["head_hex"],
                    },
                )
            )
        for item in graph["strings"]:
            director_rows.append(
                _row(
                    f"apf:director:{outer}:string:{item['index']}",
                    "director_string",
                    str(item["text"]),
                    f"{role.title()} · string {item['index']}",
                    {
                        "role": role,
                        "index": item["index"],
                        "offset": item["offset"],
                        "size": item["size"],
                        "text": item["text"],
                    },
                )
            )
    return PlaybookDirectorSnapshot(
        playbook_summary=play_summary,
        director_summary=director_summary,
        playbooks=PagedModel(
            tuple(play_rows),
            (
                "Read-only: formations, plays, categories, slot references, and every route-node identity are browsable.",
                "Route-node coordinate/action semantics are not decoded well enough for play authoring.",
            ),
        ),
        directors=PagedModel(
            tuple(director_rows),
            (
                "Read-only: DRCT graph partitions are proved, but instruction opcodes and mutation integrity are unknown.",
            ),
        ),
    )


def inspect_uniform_selectors(source: ApfSource) -> UniformSelectorSnapshot:
    """Expose every live team/bank/slot with the current proved orientation."""

    try:
        _source_document, teams = apf_uniform_inventory._load_team_selectors(  # type: ignore[attr-defined]
            source.index_0a
        )
    except (
        apf_uniform_inventory.UniformError,
        apf_roster.RosterError,
        apf_inner.FormatError,
        OSError,
    ) as exc:
        raise InspectorError(f"Could not inspect APF uniform selectors: {exc}") from exc
    bank_count = sum(len(team["banks"]) for team in teams)
    selector_count = sum(
        len(bank["selectors"]) for team in teams for bank in team["banks"]
    )
    summary = {
        "teams": len(teams),
        "banks": bank_count,
        "selectors": selector_count,
    }
    _require_counts("APF uniform selector", summary, EXPECTED_SELECTOR_COUNTS)

    rows: list[InspectorRow] = []
    for team in teams:
        team_index = int(team["team_index"])
        team_name = str(team["display_name"] or f"Team {team_index}")
        rows.append(
            _row(
                f"apf:selector:team:{team_index}",
                "selector_team",
                team_name,
                f"{team['abbreviation']} · {team['slot_kind']}",
                {
                    "team_index": team_index,
                    "display_name": team_name,
                    "abbreviation": team["abbreviation"],
                    "slot_kind": team["slot_kind"],
                    "config_record_index": team["config_record_index"],
                },
            )
        )
        seen_banks: set[int] = set()
        for bank in team["banks"]:
            bank_index = int(bank["bank"])
            if bank_index not in SELECTOR_BANKS or bank_index in seen_banks:
                raise InspectorError(
                    f"Team {team_index} has an unexpected selector bank {bank_index}"
                )
            seen_banks.add(bank_index)
            ownership = SELECTOR_BANKS[bank_index]
            label = str(ownership["label"])
            rows.append(
                _row(
                    f"apf:selector:team:{team_index}:bank:{bank_index}",
                    "selector_bank",
                    f"{team_name} {label}",
                    f"Bank {bank_index} · mode {ownership['mode']}",
                    {
                        "team_index": team_index,
                        "team_name": team_name,
                        "bank_index": bank_index,
                        "proved_label": label,
                        "config_index_start": ownership["config_start"],
                        "config_index_end": ownership["config_end"],
                        "selector_mode": ownership["mode"],
                    },
                )
            )
            for selector in bank["selectors"]:
                slot = int(selector["slot"])
                config_index = int(ownership["config_start"]) + slot
                families = tuple(str(value) for value in selector["families"])
                family_label = ", ".join(families) if families else "unknown family"
                rows.append(
                    _row(
                        f"apf:selector:team:{team_index}:bank:{bank_index}:slot:{slot}",
                        "selector",
                        f"{team_name} {label} · slot {slot}",
                        f"{family_label} → asset {selector['asset_index_byte_0']}",
                        {
                            "team_index": team_index,
                            "team_name": team_name,
                            "bank_index": bank_index,
                            "proved_label": label,
                            "selector_mode": ownership["mode"],
                            "bank_config_index": config_index,
                            "slot": slot,
                            "families": families,
                            "asset_index_byte_0": selector["asset_index_byte_0"],
                            "selector_record_index": selector["selector_record_index"],
                            "raw_record_hex": selector["raw_record_hex"],
                            "opaque_bytes_1_7_hex": selector[
                                "opaque_bytes_1_7_hex"
                            ],
                            "semantic_status": selector["semantic_status"],
                        },
                    )
                )
        if seen_banks != set(SELECTOR_BANKS):
            raise InspectorError(f"Team {team_index} does not expose both selector banks")
    return UniformSelectorSnapshot(
        summary=summary,
        model=PagedModel(
            tuple(rows),
            (
                "Static ownership proof: bank 0/configs 0–13/mode 1 is HOME; bank 1/configs 14–27/mode 0 is AWAY.",
                "Runtime bank consumption and saved-team overrides are not yet proved.",
                "Only selector byte 0 is a proved asset index; bytes 1–7 remain opaque. This inspector never writes them.",
            ),
        ),
    )


_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_stem(value: str, fallback: str) -> str:
    cleaned = _SAFE_STEM.sub("-", value.strip()).strip("-._")
    return (cleaned or fallback)[:96]


def _normalized_audio_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def classify_audo_role(name: str) -> tuple[str, str]:
    """Return a deliberately broad role and its evidence boundary."""

    lowered = name.casefold()
    normalized = _normalized_audio_name(name)
    if "menu" in lowered:
        role_id = "ui_menu_sfx"
    elif any(token in lowered for token in _AUDO_CROWD_TOKENS):
        role_id = "crowd_stadium"
    elif any(token in lowered for token in _AUDO_FIELD_TOKENS):
        role_id = "on_field_player"
    elif "music" in lowered or "song" in lowered or normalized.startswith("jukebox"):
        role_id = "soundtrack_music"
    else:
        role_id = "general_sfx"
    return role_id, "Name heuristic only; exact cue routing is not proved."


def classify_ausb_role(name: str) -> tuple[str, str]:
    normalized = _normalized_audio_name(name)
    role_id = AUSB_BANK_ROLE_IDS.get(normalized, "general_sfx")
    if normalized in AUSB_BANK_ROLE_IDS:
        basis = "Exact source-owned AUSB bank name; individual cue meaning remains unproved."
    else:
        basis = "Unrecognized source-owned bank name; left in the conservative fallback role."
    return role_id, basis


def _jukebox_presentation(
    name: str, substream_index: int
) -> tuple[str, Mapping[str, object]]:
    normalized = _normalized_audio_name(name)
    if normalized == "jukeboxmusic":
        return (
            f"Soundtrack Track {substream_index + 1:02d} · Full stereo",
            {
                "logical_track_number": substream_index + 1,
                "paired_bank_name": "jukebox22",
                "paired_encoding_role": "48 kHz stereo",
                "track_title_status": "Unknown; artist and title are not guessed.",
            },
        )
    if normalized == "jukebox22":
        return (
            f"Soundtrack Track {substream_index + 1:02d} · Mono companion",
            {
                "logical_track_number": substream_index + 1,
                "paired_bank_name": "jukeboxmusic",
                "paired_encoding_role": "22.05 kHz mono companion",
                "track_title_status": "Unknown; artist and title are not guessed.",
            },
        )
    return f"{name} · {substream_index:05d}", {}


@dataclass
class _ExternalBankBuilder:
    external_filename: str
    outer_table_index: int
    name_id: int
    encoded_size: int
    owners: list[ExternalAudioBankOwner]


def _record_external_bank_owner(
    builders: dict[int, _ExternalBankBuilder],
    *,
    external: object,
    parsed: Mapping[str, object],
    owner: ExternalAudioBankOwner,
) -> None:
    filename = str(parsed["external_filename"])
    if (
        not filename
        or Path(filename).name != filename
        or not filename.casefold().endswith(".bin")
    ):
        raise InspectorError("AUSB external-bank filename is not a safe .bin name")
    outer_index = int(getattr(external, "table_index"))
    name_id = int(getattr(external, "name_id"))
    encoded_size = int(getattr(external, "size"))
    if str(getattr(external, "head_hex", "")) == f"{apf_inner.IFF_MAGIC:08x}":
        raise InspectorError(f"External audio bank {filename} unexpectedly became IFF")
    if encoded_size <= 0:
        raise InspectorError(f"External audio bank {filename} is empty")
    current = builders.get(outer_index)
    if current is None:
        current = _ExternalBankBuilder(
            external_filename=filename,
            outer_table_index=outer_index,
            name_id=name_id,
            encoded_size=encoded_size,
            owners=[],
        )
        builders[outer_index] = current
    elif (
        current.external_filename != filename
        or current.name_id != name_id
        or current.encoded_size != encoded_size
    ):
        raise InspectorError(
            f"External audio bank outer {outer_index} has conflicting ownership metadata"
        )
    if any(existing.coordinates == owner.coordinates for existing in current.owners):
        raise InspectorError(
            f"AUSB descriptor {owner.coordinates} owns an external bank twice"
        )
    current.owners.append(owner)


def _freeze_external_audio_banks(
    builders: Mapping[int, _ExternalBankBuilder],
    *,
    require_pinned_counts: bool = True,
) -> tuple[ExternalAudioBankIdentity, ...]:
    result = tuple(
        ExternalAudioBankIdentity(
            external_filename=value.external_filename,
            outer_table_index=value.outer_table_index,
            name_id=value.name_id,
            encoded_size=value.encoded_size,
            owners=tuple(sorted(value.owners, key=lambda owner: owner.coordinates)),
        )
        for _index, value in sorted(builders.items())
    )
    owner_count = sum(len(identity.owners) for identity in result)
    if require_pinned_counts and (len(result) != 19 or owner_count != 20):
        raise InspectorError(
            "APF external audio ownership changed unexpectedly "
            f"(banks={len(result)}, descriptors={owner_count})"
        )
    return result


def discover_external_audio_banks(
    index_0a: Path,
    iff_entries: Iterable[Mapping[str, object]],
    *,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> tuple[ExternalAudioBankIdentity, ...]:
    """Resolve the 20 AUSB descriptors to 19 physical source-owned banks.

    ``iff_entries`` is the private metadata-only catalog selection.  It lets a
    cached catalog decode only the few outer records that declare AUSB files,
    while every filename, CRC owner, size, and descriptor coordinate is still
    recovered from the user's selected game rather than a bundled manifest.
    """

    targets: dict[int, set[int]] = {}
    for entry in iff_entries:
        outer_index = int(entry["table_index"])
        files = entry.get("files")
        if not isinstance(files, list):
            raise InspectorError("APF catalog selection has an invalid file list")
        for item in files:
            if not isinstance(item, Mapping):
                raise InspectorError("APF catalog selection has an invalid file row")
            if str(item.get("type_name")) == apf_audio.AUSB_TYPE:
                targets.setdefault(outer_index, set()).add(int(item["index"]))
    if sum(len(values) for values in targets.values()) != 20:
        raise InspectorError("APF catalog selection no longer names 20 AUSB descriptors")

    try:
        archive = apf_outer.parse_archive(index_0a)
        entries_by_table = {
            int(entry.table_index): entry for entry in archive.entries
        }
        external_by_id: dict[int, list[object]] = {}
        for entry in archive.entries:
            external_by_id.setdefault(int(entry.name_id), []).append(entry)
        builders: dict[int, _ExternalBankBuilder] = {}
        with apf_inner.ArchiveReader(archive) as reader:
            for outer_index, inner_indices in sorted(targets.items()):
                entry = entries_by_table.get(outer_index)
                if entry is None or entry.head_hex != f"{apf_inner.IFF_MAGIC:08x}":
                    raise InspectorError(
                        f"AUSB owner outer {outer_index} is no longer an IFF record"
                    )
                record = apf_inner.parse_iff(reader, entry)
                files_by_index = {int(item.index): item for item in record.files}
                cache: dict[int, bytes] = {}
                for inner_index in sorted(inner_indices):
                    item = files_by_index.get(inner_index)
                    if item is None or item.type_name != apf_audio.AUSB_TYPE:
                        raise InspectorError(
                            f"AUSB owner {outer_index}:{inner_index} changed type"
                        )
                    if len(item.parts) != 1:
                        raise InspectorError(
                            f"AUSB {outer_index}:{inner_index} no longer has one descriptor part"
                        )
                    descriptor = apf_audio._read_part(  # type: ignore[attr-defined]
                        reader,
                        record,
                        item.parts[0],
                        cache,
                        max_decompressed,
                    )
                    parsed = apf_audio.parse_ausb(descriptor)
                    external_id = int(
                        str(parsed["external_filename_crc32_upper_ascii"]), 16
                    )
                    matches = external_by_id.get(external_id, [])
                    if len(matches) != 1:
                        raise InspectorError(
                            f"AUSB {outer_index}:{inner_index} resolves to "
                            f"{len(matches)} external banks"
                        )
                    owner = ExternalAudioBankOwner(
                        descriptor_outer_index=outer_index,
                        descriptor_inner_index=inner_index,
                        bank_name=str(item.name or f"file_{inner_index:04d}"),
                        substream_count=int(parsed["entry_count"]),
                        sample_rate=int(parsed["sample_rate"]),
                        channel_count=int(parsed["derived_channel_count"]),
                    )
                    _record_external_bank_owner(
                        builders,
                        external=matches[0],
                        parsed=parsed,
                        owner=owner,
                    )
        return _freeze_external_audio_banks(builders)
    except InspectorError:
        raise
    except (
        apf_audio.AudioError,
        apf_outer.FormatError,
        apf_inner.FormatError,
        OSError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
    ) as exc:
        raise InspectorError(f"Could not resolve APF external audio banks: {exc}") from exc


def inspect_audio(
    source: ApfSource,
    *,
    max_decompressed: int = MAX_DECOMPRESSED,
) -> AudioSnapshot:
    """Inventory every live AUDO identity and every AUSB bank substream.

    AUDO payloads are intentionally not decoded during catalog construction.
    Their exact outer/inner coordinates are enough for ``apf_audio`` to export
    on demand.  AUSB descriptors are decoded because their boundary tables are
    required to address all 45,514 individual substreams.
    """

    try:
        archive = apf_outer.parse_archive(source.index_0a)
        external_by_id: dict[int, list[object]] = {}
        for entry in archive.entries:
            external_by_id.setdefault(int(entry.name_id), []).append(entry)
        audo_rows: list[InspectorRow] = []
        bank_rows: list[InspectorRow] = []
        substream_rows: list[InspectorRow] = []
        external_indices: set[int] = set()
        external_builders: dict[int, _ExternalBankBuilder] = {}
        jukebox_banks: dict[str, tuple[int, tuple[float, ...]]] = {}
        with apf_inner.ArchiveReader(archive) as reader:
            for entry in archive.entries:
                if entry.head_hex != f"{apf_inner.IFF_MAGIC:08x}":
                    continue
                record = apf_inner.parse_iff(reader, entry)
                cache: dict[int, bytes] = {}
                for item in record.files:
                    name = str(item.name or f"file_{item.index:04d}")
                    if item.type_name == apf_audio.AUDO_TYPE:
                        metadata_part, payload_part = apf_audio._identify_parts(  # type: ignore[attr-defined]
                            record, item
                        )
                        metadata_bytes = apf_audio._read_part(  # type: ignore[attr-defined]
                            reader,
                            record,
                            metadata_part,
                            cache,
                            max_decompressed,
                        )
                        metadata = apf_audio.parse_metadata(metadata_bytes)
                        encoded_size = int(metadata["encoded_size"])
                        sample_rate = int(metadata["sample_rate"])
                        declared_samples = int(metadata["declared_sample_count"])
                        channels = metadata["derived_channel_count"]
                        if encoded_size != int(payload_part.length):
                            raise InspectorError(
                                f"AUDO {entry.table_index}:{item.index} encoded size changed"
                            )
                        if encoded_size <= 0 or encoded_size % apf_audio.XMA_PACKET_SIZE:
                            raise InspectorError(
                                f"AUDO {entry.table_index}:{item.index} is not packet aligned"
                            )
                        if sample_rate <= 0 or declared_samples <= 0 or channels is None:
                            raise InspectorError(
                                f"AUDO {entry.table_index}:{item.index} has unsupported audio metadata"
                            )
                        role_id, role_basis = classify_audo_role(name)
                        identity = ExportIdentity(
                            kind="audo",
                            outer_table_index=int(entry.table_index),
                            inner_file_index=int(item.index),
                            substream_index=None,
                            suggested_basename=_safe_stem(
                                name,
                                f"audo-{entry.table_index}-{item.index}",
                            ),
                        )
                        audo_rows.append(
                            _row(
                                f"apf:audio:audo:{entry.table_index}:{item.index}",
                                "audo",
                                name,
                                f"AUDO · outer {entry.table_index} / inner {item.index}",
                                {
                                    "outer_table_index": entry.table_index,
                                    "inner_file_index": item.index,
                                    "name": name,
                                    "audio_source_id": "audo:standalone",
                                    "audio_source_label": "Standalone AUDO",
                                    "part_count": len(item.parts),
                                    "role_id": role_id,
                                    "role_label": AUDIO_ROLE_LABELS[role_id],
                                    "role_basis": role_basis,
                                    "audio_format": "XMA1",
                                    "sample_rate": sample_rate,
                                    "derived_channel_count": int(channels),
                                    "declared_sample_count": declared_samples,
                                    "encoded_size": encoded_size,
                                    "packet_count": encoded_size
                                    // apf_audio.XMA_PACKET_SIZE,
                                    "duration_seconds": declared_samples / sample_rate,
                                    "export_status": (
                                        "Original XMA1; WAV only after full decoder verification"
                                    ),
                                },
                                export_identity=identity,
                            )
                        )
                        continue
                    if item.type_name != apf_audio.AUSB_TYPE:
                        continue
                    if len(item.parts) != 1:
                        raise InspectorError(
                            f"AUSB {entry.table_index}:{item.index} no longer has one descriptor part"
                        )
                    descriptor = apf_audio._read_part(  # type: ignore[attr-defined]
                        reader,
                        record,
                        item.parts[0],
                        cache,
                        max_decompressed,
                    )
                    parsed = apf_audio.parse_ausb(descriptor)
                    normalized_bank_name = _normalized_audio_name(name)
                    role_id, role_basis = classify_ausb_role(name)
                    audio_source_id = f"ausb:{entry.table_index}:{item.index}"
                    audio_source_label = (
                        f"{name} · O{entry.table_index}/I{item.index}"
                    )
                    external_id = int(
                        str(parsed["external_filename_crc32_upper_ascii"]), 16
                    )
                    external_matches = external_by_id.get(external_id, [])
                    if len(external_matches) != 1:
                        raise InspectorError(
                            f"AUSB {entry.table_index}:{item.index} resolves to "
                            f"{len(external_matches)} external banks"
                        )
                    external = external_matches[0]
                    external_indices.add(int(external.table_index))
                    boundaries = list(parsed["entries"])
                    terminal = parsed["terminal_boundary"]
                    if int(parsed["entry_count"]) != len(boundaries):
                        raise InspectorError("AUSB declared substream count changed")
                    _record_external_bank_owner(
                        external_builders,
                        external=external,
                        parsed=parsed,
                        owner=ExternalAudioBankOwner(
                            descriptor_outer_index=int(entry.table_index),
                            descriptor_inner_index=int(item.index),
                            bank_name=name,
                            substream_count=len(boundaries),
                            sample_rate=int(parsed["sample_rate"]),
                            channel_count=int(parsed["derived_channel_count"]),
                        ),
                    )
                    bank_rows.append(
                        _row(
                            f"apf:audio:ausb:{entry.table_index}:{item.index}",
                            "ausb_bank",
                            name,
                            f"{len(boundaries):,} substreams · {parsed['external_filename']}",
                            {
                                "outer_table_index": entry.table_index,
                                "inner_file_index": item.index,
                                "name": name,
                                "audio_source_id": audio_source_id,
                                "audio_source_label": audio_source_label,
                                "role_id": role_id,
                                "role_label": AUDIO_ROLE_LABELS[role_id],
                                "role_basis": role_basis,
                                "external_filename": parsed["external_filename"],
                                "external_outer_table_index": external.table_index,
                                "substream_count": len(boundaries),
                                "sample_rate": parsed["sample_rate"],
                                "channel_layout_code": parsed[
                                    "channel_layout_code"
                                ],
                                "derived_channel_count": parsed[
                                    "derived_channel_count"
                                ],
                                "audio_format": "AUSB index → external XMA1 bank",
                                "bulk_export_status": (
                                    "Available as a transactional ZIP"
                                    if 0 < len(boundaries) <= 256
                                    else "Too large for one-click bank export; browse and export substreams individually"
                                ),
                            },
                        )
                    )
                    previous_start = -1
                    duration_vector: list[float] = []
                    for substream_index, boundary in enumerate(boundaries):
                        next_boundary = (
                            boundaries[substream_index + 1]
                            if substream_index + 1 < len(boundaries)
                            else terminal
                        )
                        start = int(boundary["packet_offset"])
                        end = int(next_boundary["packet_offset"])
                        if (
                            start <= previous_start
                            or not 0 <= start < end <= int(external.size)
                            or start % apf_audio.XMA_PACKET_SIZE
                            or end % apf_audio.XMA_PACKET_SIZE
                        ):
                            raise InspectorError(
                                f"AUSB {entry.table_index}:{item.index} substream "
                                f"{substream_index} has invalid packet boundaries"
                            )
                        previous_start = start
                        duration = float(next_boundary["value_float"])
                        duration_vector.append(duration)
                        stem = _safe_stem(
                            f"{name}-{substream_index:05d}",
                            f"ausb-{entry.table_index}-{item.index}-{substream_index}",
                        )
                        identity = ExportIdentity(
                            kind="ausb_substream",
                            outer_table_index=int(entry.table_index),
                            inner_file_index=int(item.index),
                            substream_index=substream_index,
                            suggested_basename=stem,
                        )
                        display_title, paired_fields = _jukebox_presentation(
                            name, substream_index
                        )
                        substream_rows.append(
                            _row(
                                f"apf:audio:ausb:{entry.table_index}:{item.index}:{substream_index}",
                                "ausb_substream",
                                display_title,
                                f"{(end - start) // apf_audio.XMA_PACKET_SIZE:,} XMA packets",
                                {
                                    "outer_table_index": entry.table_index,
                                    "inner_file_index": item.index,
                                    "substream_index": substream_index,
                                    "bank_name": name,
                                    "audio_source_id": audio_source_id,
                                    "audio_source_label": audio_source_label,
                                    "role_id": role_id,
                                    "role_label": AUDIO_ROLE_LABELS[role_id],
                                    "role_basis": role_basis,
                                    "audio_format": "XMA1",
                                    "external_filename": parsed[
                                        "external_filename"
                                    ],
                                    "external_outer_table_index": external.table_index,
                                    "range_offset": start,
                                    "range_length": end - start,
                                    "packet_count": (end - start)
                                    // apf_audio.XMA_PACKET_SIZE,
                                    "sample_rate": parsed["sample_rate"],
                                    "derived_channel_count": parsed[
                                        "derived_channel_count"
                                    ],
                                    "declared_sample_count": round(
                                        duration * int(parsed["sample_rate"])
                                    ),
                                    "duration_seconds_candidate": duration,
                                    "export_status": (
                                        "Original XMA1; strict exact-slot replacement available"
                                    ),
                                    **paired_fields,
                                },
                                export_identity=identity,
                            )
                        )
                    if normalized_bank_name in {"jukeboxmusic", "jukebox22"}:
                        if normalized_bank_name in jukebox_banks:
                            raise InspectorError(
                                f"Duplicate soundtrack bank {normalized_bank_name}"
                            )
                        jukebox_banks[normalized_bank_name] = (
                            len(boundaries),
                            tuple(duration_vector),
                        )
    except InspectorError:
        raise
    except (
        apf_audio.AudioError,
        apf_outer.FormatError,
        apf_inner.FormatError,
        OSError,
        IndexError,
        UnicodeError,
    ) as exc:
        raise InspectorError(f"Could not inspect APF audio: {exc}") from exc

    summary = {
        "audo": len(audo_rows),
        "ausb_banks": len(bank_rows),
        "ausb_substreams": len(substream_rows),
        "external_bins": len(external_indices),
    }
    _require_counts("APF audio", summary, EXPECTED_AUDIO_COUNTS)
    external_identities = _freeze_external_audio_banks(external_builders)
    external_rows: list[InspectorRow] = []
    for identity in external_identities:
        owner_documents: list[dict[str, object]] = []
        role_ids: list[str] = []
        role_labels: list[str] = []
        for owner in identity.owners:
            role_id, role_basis = classify_ausb_role(owner.bank_name)
            if role_id not in role_ids:
                role_ids.append(role_id)
                role_labels.append(AUDIO_ROLE_LABELS[role_id])
            owner_documents.append(
                {
                    "descriptor_outer_index": owner.descriptor_outer_index,
                    "descriptor_inner_index": owner.descriptor_inner_index,
                    "bank_name": owner.bank_name,
                    "audio_source_id": owner.audio_source_id,
                    "substream_count": owner.substream_count,
                    "sample_rate": owner.sample_rate,
                    "derived_channel_count": owner.channel_count,
                    "role_id": role_id,
                    "role_label": AUDIO_ROLE_LABELS[role_id],
                    "role_basis": role_basis,
                }
            )
        external_rows.append(
            _row(
                f"apf:audio:external:{identity.outer_table_index}",
                "external_bank",
                identity.external_filename,
                (
                    f"{identity.encoded_size:,} raw XMA1 bytes · "
                    f"{len(identity.owners)} AUSB descriptor owner"
                    f"{'s' if len(identity.owners) != 1 else ''}"
                ),
                {
                    "outer_table_index": identity.outer_table_index,
                    "external_filename": identity.external_filename,
                    "name_id": f"0x{identity.name_id:08x}",
                    "encoded_size": identity.encoded_size,
                    "raw_asset_id": identity.raw_asset_id,
                    "descriptor_owner_count": len(identity.owners),
                    "addressable_substream_rows": sum(
                        owner.substream_count for owner in identity.owners
                    ),
                    "linked_audio_source_ids": identity.linked_audio_source_ids,
                    "linked_role_ids": tuple(role_ids),
                    "linked_role_labels": tuple(role_labels),
                    "descriptor_owners": owner_documents,
                    "audio_format": "Raw external XMA1 packet bank",
                    "export_status": (
                        "Exact original .bin export; not one playable cue. "
                        "Use its AUSB substream rows for Play or sound export."
                    ),
                },
                external_bank_identity=identity,
            )
        )
    if jukebox_banks:
        if set(jukebox_banks) != {"jukeboxmusic", "jukebox22"}:
            raise InspectorError("Only one of APF's paired jukebox banks is present")
        full_count, full_durations = jukebox_banks["jukeboxmusic"]
        companion_count, companion_durations = jukebox_banks["jukebox22"]
        if full_count != 15 or companion_count != 15:
            raise InspectorError("APF's paired jukebox bank count changed from 15 tracks")
        if any(
            abs(left - right) > 0.001
            for left, right in zip(full_durations, companion_durations, strict=True)
        ):
            raise InspectorError("APF's jukebox duration pairing no longer matches")
    # AUSB descriptors can occasionally name the exact same physical range.
    # Surface that relationship without exposing source pack offsets or bytes;
    # editing either semantic row necessarily changes every listed owner.
    owners_by_physical_range: dict[tuple[int, int, int], list[str]] = {}
    for row in substream_rows:
        key = (
            int(row.fields["external_outer_table_index"]),
            int(row.fields["range_offset"]),
            int(row.fields["range_length"]),
        )
        owners_by_physical_range.setdefault(key, []).append(row.row_id)
    disclosed_rows: list[InspectorRow] = []
    for row in substream_rows:
        key = (
            int(row.fields["external_outer_table_index"]),
            int(row.fields["range_offset"]),
            int(row.fields["range_length"]),
        )
        owner_ids = tuple(sorted(owners_by_physical_range[key]))
        fields = dict(row.fields)
        fields["shared_effect"] = len(owner_ids) > 1
        fields["shared_owner_asset_ids"] = owner_ids
        if len(owner_ids) > 1:
            fields["replacement_effect"] = (
                "Shared physical sound: replacing this row also changes "
                + ", ".join(owner_ids)
            )
        disclosed_rows.append(replace(row, fields=fields))
    substream_rows = disclosed_rows

    findings = (
        "All 2,261 AUDO identities and all 45,514 AUSB substream identities come from the selected game, not a bundled manifest.",
        "All 19 physical external XMA1 packet banks are named from their 20 source-owned AUSB descriptors; raw bank export does not make a multi-cue container playable or writable.",
        "The 15 jukeboxmusic rows and 15 jukebox22 rows are paired by source index and matching duration as Track 01–15; artist/title names are deliberately not guessed.",
        "Every individual AUDO and AUSB row has a bounded exact-slot editor for pre-encoded XMA1; WAV/FLAC encoding still needs a usable XMA1 encoder and AUSB runtime consumption is not yet proved.",
        "One cwdloop physical range has two disclosed semantic owners; replacing either row changes both owners and divergent edits are rejected.",
        "A small number of AUDO payloads may fail WAV decoding; their exact XMA export identity remains browsable.",
    )
    return AudioSnapshot(
        summary=summary,
        audo=PagedModel(tuple(audo_rows), findings),
        ausb_banks=PagedModel(tuple(bank_rows), findings),
        ausb_substreams=PagedModel(tuple(substream_rows), findings),
        external_banks=PagedModel(tuple(external_rows), findings),
    )


class ApfInspectorService:
    """Lazy per-source facade suitable for a desktop or headless frontend."""

    def __init__(
        self,
        source: ApfSource,
        *,
        max_decompressed: int = MAX_DECOMPRESSED,
    ):
        self.source = source
        self.max_decompressed = max_decompressed
        self._roster: RosterSnapshot | None = None
        self._localization: LocalizationSnapshot | None = None
        self._playbooks: PlaybookDirectorSnapshot | None = None
        self._selectors: UniformSelectorSnapshot | None = None
        self._audio: AudioSnapshot | None = None

    def roster(self) -> RosterSnapshot:
        if self._roster is None:
            self._roster = inspect_roster(self.source)
        return self._roster

    def localization(self) -> LocalizationSnapshot:
        if self._localization is None:
            self._localization = inspect_localization(
                self.source, max_decompressed=self.max_decompressed
            )
        return self._localization

    def playbooks_directors(self) -> PlaybookDirectorSnapshot:
        if self._playbooks is None:
            self._playbooks = inspect_playbooks_directors(
                self.source, max_decompressed=self.max_decompressed
            )
        return self._playbooks

    def uniform_selectors(self) -> UniformSelectorSnapshot:
        if self._selectors is None:
            self._selectors = inspect_uniform_selectors(self.source)
        return self._selectors

    def audio(self) -> AudioSnapshot:
        if self._audio is None:
            self._audio = inspect_audio(
                self.source, max_decompressed=self.max_decompressed
            )
        return self._audio

    def load_all(self) -> InspectorBundle:
        return InspectorBundle(
            roster=self.roster(),
            localization=self.localization(),
            playbooks_directors=self.playbooks_directors(),
            uniform_selectors=self.uniform_selectors(),
            audio=self.audio(),
        )


__all__ = [
    "AUDIO_ROLE_LABELS",
    "AUSB_BANK_ROLE_IDS",
    "ApfInspectorService",
    "AudioSnapshot",
    "ExportIdentity",
    "InspectorBundle",
    "InspectorError",
    "InspectorRow",
    "LocalizationSnapshot",
    "Page",
    "PagedModel",
    "PlaybookDirectorSnapshot",
    "RosterSnapshot",
    "SELECTOR_BANKS",
    "UniformSelectorSnapshot",
    "classify_audo_role",
    "classify_ausb_role",
    "discover_external_audio_banks",
    "inspect_audio",
    "inspect_localization",
    "inspect_playbooks_directors",
    "inspect_roster",
    "inspect_uniform_selectors",
    "export_semantic_rows",
]
