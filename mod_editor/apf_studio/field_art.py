"""Fail-closed, retail-free semantic inventory for APF field-art rows.

The universal APF catalog already exposes every archive record.  This module
adds a product-facing interpretation for the 258 rows currently routed to
``Field Art`` without reading or retaining any game payload.  Its strongest
ownership statement is archive-package co-location: sharing an outer package
does *not* prove a team selector, stadium selector, rendered field material, or
runtime consumer.

All counts and relationships below are deliberate review gates.  If a future
catalog changes, the inventory fails closed instead of silently mislabeling a
new resource.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, TYPE_CHECKING

from .models import ApfAsset, ApfCategory, ApfStatus

if TYPE_CHECKING:
    from .catalog import ApfCatalog


FIELD_ART_RECORD_COUNT = 258
FIELD_ART_PACKAGE_COUNT = 125


class FieldArtInventoryError(ValueError):
    """The live APF field-art catalog no longer matches the reviewed model."""


class FieldArtKind(str, Enum):
    """The seven bounded semantic families in the current Field Art catalog."""

    ENDZONE_TEXTURE = "endzone_texture"
    FIELD_SCENE = "field_scene"
    FIELD_RADIANCE = "field_radiance"
    DIVOT_WEATHER_TEXTURE = "divot_weather_texture"
    PRACTICE_FIELD_OVERLAY = "practice_field_overlay"
    PRACTICE_SCENE = "practice_scene"
    PENALTY_ANIMATION = "penalty_animation"

    @property
    def title(self) -> str:
        return {
            self.ENDZONE_TEXTURE: "Endzone textures",
            self.FIELD_SCENE: "Field scenes",
            self.FIELD_RADIANCE: "Field radiance textures",
            self.DIVOT_WEATHER_TEXTURE: "Divot & weather textures",
            self.PRACTICE_FIELD_OVERLAY: "Practice & field overlays",
            self.PRACTICE_SCENE: "Practice-related scenes",
            self.PENALTY_ANIMATION: "Penalty animation curves",
        }[self]


@dataclass(frozen=True, slots=True)
class FieldArtRecord:
    """One sanitized semantic view of a live :class:`ApfAsset`.

    Archive indices are catalog identities, not byte offsets.  No payload,
    checksum, block coordinate, or decoded pixel data is copied here.
    """

    asset_id: str
    package_id: str
    outer_index: int
    inner_index: int
    name: str
    type_name: str
    asset_class: str
    kind: FieldArtKind
    status: ApfStatus
    export_label: str
    author_note: str
    #: The team that owns this endzone package, where someone has identified
    #: it from the artwork.  ``None`` means unidentified, never "shared".
    team_label: str | None = None

    @property
    def display_name(self) -> str:
        """What to show on the row: the team when known, else the package."""

        if self.team_label:
            return f"{self.name} — {self.team_label}"
        return self.name


@dataclass(frozen=True, slots=True)
class FieldArtSemanticGroup:
    """A complete name/type family with stable author-facing guidance."""

    kind: FieldArtKind
    title: str
    records: tuple[FieldArtRecord, ...]
    package_ids: tuple[str, ...]
    author_note: str


@dataclass(frozen=True, slots=True)
class FieldArtPackageGroup:
    """Records that are physically co-located in one archive package."""

    package_id: str
    outer_index: int
    records: tuple[FieldArtRecord, ...]
    kinds: tuple[FieldArtKind, ...]
    ownership_note: str


@dataclass(frozen=True, slots=True)
class FieldArtInventory:
    """Immutable semantic inventory ready for a dedicated product surface."""

    records: tuple[FieldArtRecord, ...]
    semantic_groups: tuple[FieldArtSemanticGroup, ...]
    package_groups: tuple[FieldArtPackageGroup, ...]
    summary: Mapping[str, int]
    findings: tuple[str, ...]

    def get(self, asset_id: str) -> FieldArtRecord:
        for record in self.records:
            if record.asset_id == asset_id:
                return record
        raise FieldArtInventoryError(f"Unknown APF field-art asset: {asset_id}")

    def semantic_group(self, kind: FieldArtKind) -> FieldArtSemanticGroup:
        for group in self.semantic_groups:
            if group.kind is kind:
                return group
        raise FieldArtInventoryError(f"Unknown APF field-art group: {kind.value}")

    def package_group(self, package_id: str) -> FieldArtPackageGroup:
        for group in self.package_groups:
            if group.package_id == package_id:
                return group
        raise FieldArtInventoryError(
            f"Unknown APF field-art package: {package_id}"
        )


ENDZONE_LABELS_SCHEMA = "apf2k8_endzone_labels/v1"
ENDZONE_LABELS = (
    Path(__file__).resolve().parents[1] / "data" / "apf2k8_endzone_labels.v1.json"
)
#: What every endzone package is, and is not.  Decoding any of them gives pure
#: red / green / blue region selectors over black with uniformly opaque alpha,
#: exactly like ``jersey_color`` and ``shoulder_color``; the colours a player
#: sees are shader-driven.  Someone who exports one expecting to repaint "the
#: endzone art" gets a three-colour mask instead, so the panel says so first.
ENDZONE_MASK_CONTRACT = (
    "Endzone layers are region masks, not artwork: pure red / green / blue "
    "region selectors over black, 2048×512 DXT1, with alpha uniformly opaque. "
    "The colours in game are shader-driven. Author them like the uniform "
    "masks — flat colours, hard edges, no anti-aliasing — because an "
    "intermediate value is an invalid region ID, not a blend."
)
#: Why the discovery path is visual rather than a search box.
ENDZONE_IDENTITY_NOTE = (
    "Endzone packages carry no team identity, and the nicknames are not on the "
    "disc: a team name appears zero times in 0A, 0B, 1A, 1B and default.xex in "
    "ASCII, UTF-16BE and UTF-16LE — it lives only in Roster.ROS. Text search "
    "therefore cannot find a team's endzone, by construction. Export the "
    "contact sheet and identify the package by its artwork; identifications "
    "confirmed so far are shown on the rows."
)


@lru_cache(maxsize=1)
def endzone_team_labels() -> Mapping[int, str]:
    """Which team owns each endzone package, for the packages anyone has named.

    Missing is missing: a package nobody has identified stays an index rather
    than being guessed from its neighbours.
    """

    try:
        document = json.loads(ENDZONE_LABELS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FieldArtInventoryError(
            f"The APF endzone label table could not be read: {exc}"
        ) from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != ENDZONE_LABELS_SCHEMA
        or not isinstance(document.get("labels"), list)
    ):
        raise FieldArtInventoryError("The APF endzone label table has an unknown format")
    labels: dict[int, str] = {}
    for row in document["labels"]:
        if (
            not isinstance(row, dict)
            or type(row.get("outer_index")) is not int
            or not isinstance(row.get("team"), str)
            or not row["team"].strip()
        ):
            raise FieldArtInventoryError("An APF endzone label row is malformed")
        outer = int(row["outer_index"])
        if outer in labels:
            raise FieldArtInventoryError(
                f"The APF endzone label table names package {outer} twice"
            )
        labels[outer] = str(row["team"]).strip()
    return MappingProxyType(labels)


@dataclass(frozen=True, slots=True)
class _NameContract:
    kind: FieldArtKind
    type_name: str
    asset_class: str
    count: int


_NAME_CONTRACTS: Mapping[str, _NameContract] = MappingProxyType(
    {
        "endzone_l0": _NameContract(
            FieldArtKind.ENDZONE_TEXTURE, "TXTR", "texture", 118
        ),
        "endzone_l1": _NameContract(
            FieldArtKind.ENDZONE_TEXTURE, "TXTR", "texture", 117
        ),
        "field": _NameContract(
            FieldArtKind.FIELD_SCENE, "SCNE", "scene_model_package", 4
        ),
        "field_radiance": _NameContract(
            FieldArtKind.FIELD_RADIANCE, "TXTR", "texture", 4
        ),
        "divots": _NameContract(
            FieldArtKind.DIVOT_WEATHER_TEXTURE, "TXTR", "texture", 3
        ),
        "divot_GrassRain": _NameContract(
            FieldArtKind.DIVOT_WEATHER_TEXTURE, "TXTR", "texture", 1
        ),
        "divot_GrassSnow": _NameContract(
            FieldArtKind.DIVOT_WEATHER_TEXTURE, "TXTR", "texture", 1
        ),
        "divot_GrassDry": _NameContract(
            FieldArtKind.DIVOT_WEATHER_TEXTURE, "TXTR", "texture", 1
        ),
        "pc_field_goal": _NameContract(
            FieldArtKind.PRACTICE_FIELD_OVERLAY, "TXTR", "texture", 1
        ),
        "Field_Pass_text": _NameContract(
            FieldArtKind.PRACTICE_FIELD_OVERLAY, "TXTR", "texture", 1
        ),
        "Stride_number_field": _NameContract(
            FieldArtKind.PRACTICE_FIELD_OVERLAY, "TXTR", "texture", 1
        ),
        "divotb1": _NameContract(
            FieldArtKind.PRACTICE_SCENE, "SCNE", "scene_model_package", 1
        ),
        "field_pass01": _NameContract(
            FieldArtKind.PRACTICE_SCENE, "SCNE", "scene_model_package", 1
        ),
        "divota1": _NameContract(
            FieldArtKind.PRACTICE_SCENE, "SCNE", "scene_model_package", 1
        ),
        "tc2_footballField": _NameContract(
            FieldArtKind.PRACTICE_SCENE, "SCNE", "scene_model_package", 1
        ),
        "there_is_a_penalty_onthe_field": _NameContract(
            FieldArtKind.PENALTY_ANIMATION,
            "CurveAnim",
            "animation_curve",
            1,
        ),
        "penalty_onthe_field": _NameContract(
            FieldArtKind.PENALTY_ANIMATION,
            "CurveAnim",
            "animation_curve",
            1,
        ),
    }
)

_GROUP_COUNTS: Mapping[FieldArtKind, int] = MappingProxyType(
    {
        FieldArtKind.ENDZONE_TEXTURE: 235,
        FieldArtKind.FIELD_SCENE: 4,
        FieldArtKind.FIELD_RADIANCE: 4,
        FieldArtKind.DIVOT_WEATHER_TEXTURE: 6,
        FieldArtKind.PRACTICE_FIELD_OVERLAY: 3,
        FieldArtKind.PRACTICE_SCENE: 4,
        FieldArtKind.PENALTY_ANIMATION: 2,
    }
)

_AUTHOR_NOTES: Mapping[FieldArtKind, str] = MappingProxyType(
    {
        FieldArtKind.ENDZONE_TEXTURE: (
            "The catalog contains 117 package-local l0/l1 pairs and one "
            "l0-only record. Keep the named companions together when "
            "exporting; the l0/l1 runtime meaning and selector ownership are "
            "not yet proved."
        ),
        FieldArtKind.FIELD_SCENE: (
            "Four SCNE resources are named field. They are safe to browse and "
            "export, but the name and package relationship do not identify a "
            "specific team, stadium, or rendered field instance."
        ),
        FieldArtKind.FIELD_RADIANCE: (
            "Each field SCNE package also contains one field_radiance TXTR. "
            "That co-location does not prove which mesh, shader, or material "
            "uses the texture."
        ),
        FieldArtKind.DIVOT_WEATHER_TEXTURE: (
            "This family contains three package-local divots textures and the "
            "three named GrassRain, GrassSnow, and GrassDry textures. Their "
            "names are inventory evidence, not a proved runtime assignment."
        ),
        FieldArtKind.PRACTICE_FIELD_OVERLAY: (
            "The three texture names suggest field-goal, passing, and stride "
            "overlays. They share one archive package; consumption and screen "
            "placement remain unproved."
        ),
        FieldArtKind.PRACTICE_SCENE: (
            "Four SCNE rows have divot, field-pass, or football-field names. "
            "They are grouped for discovery only and are not claimed as a "
            "specific practice mode, stadium, or runtime scene owner."
        ),
        FieldArtKind.PENALTY_ANIMATION: (
            "These two CurveAnim rows enter Field Art only because their names "
            "contain 'field'. They are animation resources, not field textures, "
            "and remain visible here so universal catalog coverage is honest."
        ),
    }
)

_PACKAGE_OWNERSHIP_NOTE = (
    "Archive-package co-location only. This does not establish team, stadium, "
    "field-material, shader, selector, or runtime ownership."
)


def _validate_exact_rows(assets: tuple[ApfAsset, ...]) -> None:
    if len(assets) != FIELD_ART_RECORD_COUNT:
        raise FieldArtInventoryError(
            "Expected exactly 258 APF Field Art rows, "
            f"found {len(assets)}"
        )
    if len({asset.asset_id for asset in assets}) != len(assets):
        raise FieldArtInventoryError("APF Field Art contains duplicate asset IDs")
    coordinates = {(asset.outer_index, asset.inner_index) for asset in assets}
    if len(coordinates) != len(assets):
        raise FieldArtInventoryError(
            "APF Field Art contains duplicate archive identities"
        )
    if any(asset.inner_index is None for asset in assets):
        raise FieldArtInventoryError(
            "APF Field Art unexpectedly contains an outer-only record"
        )
    if any(asset.status is not ApfStatus.EXPORT_ONLY for asset in assets):
        raise FieldArtInventoryError(
            "APF Field Art status changed; review the semantic action boundary"
        )

    actual_names = {asset.name for asset in assets}
    if actual_names != set(_NAME_CONTRACTS):
        raise FieldArtInventoryError(
            "APF Field Art names changed; refusing to guess a semantic group"
        )
    for name, contract in _NAME_CONTRACTS.items():
        matching = tuple(asset for asset in assets if asset.name == name)
        if len(matching) != contract.count:
            raise FieldArtInventoryError(
                f"APF Field Art name {name!r} expected {contract.count} rows, "
                f"found {len(matching)}"
            )
        if any(
            asset.type_name != contract.type_name
            or asset.asset_class != contract.asset_class
            for asset in matching
        ):
            raise FieldArtInventoryError(
                f"APF Field Art name {name!r} changed type or class"
            )


def _validate_package_relationships(assets: tuple[ApfAsset, ...]) -> None:
    by_name = {
        name: tuple(asset for asset in assets if asset.name == name)
        for name in _NAME_CONTRACTS
    }

    endzone_l0 = {asset.outer_index: asset for asset in by_name["endzone_l0"]}
    endzone_l1 = {asset.outer_index: asset for asset in by_name["endzone_l1"]}
    if (
        len(endzone_l0) != 118
        or len(endzone_l1) != 117
        or not set(endzone_l1) < set(endzone_l0)
        or len(set(endzone_l0) - set(endzone_l1)) != 1
        or any(asset.inner_index != 0 for asset in endzone_l0.values())
        or any(asset.inner_index != 1 for asset in endzone_l1.values())
    ):
        raise FieldArtInventoryError(
            "APF endzone package pairing changed from 117 l0/l1 pairs plus one l0-only package"
        )

    field_outers = {asset.outer_index for asset in by_name["field"]}
    radiance_outers = {
        asset.outer_index for asset in by_name["field_radiance"]
    }
    divots_outers = {asset.outer_index for asset in by_name["divots"]}
    if (
        len(field_outers) != 4
        or radiance_outers != field_outers
        or len(divots_outers) != 3
        or not divots_outers < field_outers
    ):
        raise FieldArtInventoryError(
            "APF field/field_radiance/divots package relationships changed"
        )

    shared_names = (
        "divot_GrassRain",
        "divot_GrassSnow",
        "divot_GrassDry",
        "pc_field_goal",
        "Field_Pass_text",
        "Stride_number_field",
        "divotb1",
        "field_pass01",
        "divota1",
    )
    shared_outers = {
        asset.outer_index for name in shared_names for asset in by_name[name]
    }
    if len(shared_outers) != 1:
        raise FieldArtInventoryError(
            "APF weather, overlay, and companion-scene package grouping changed"
        )
    tc2_outer = by_name["tc2_footballField"][0].outer_index
    if tc2_outer in shared_outers:
        raise FieldArtInventoryError(
            "APF tc2_footballField unexpectedly moved into the shared overlay package"
        )

    penalty_outers = {
        asset.outer_index
        for name in (
            "there_is_a_penalty_onthe_field",
            "penalty_onthe_field",
        )
        for asset in by_name[name]
    }
    if len(penalty_outers) != 1:
        raise FieldArtInventoryError(
            "APF penalty CurveAnim package grouping changed"
        )

    if len({asset.outer_index for asset in assets}) != FIELD_ART_PACKAGE_COUNT:
        raise FieldArtInventoryError(
            "Expected Field Art rows in exactly 125 archive packages"
        )


def build_field_art_inventory(catalog: ApfCatalog) -> FieldArtInventory:
    """Build the reviewed semantic inventory from one live APF catalog.

    The function consumes metadata already present in :class:`ApfCatalog` and
    never opens the selected game files.  Unknown names, changed counts, new
    statuses, or changed package relationships are rejected for human review.
    """

    assets = tuple(
        sorted(
            (
                asset
                for asset in catalog.assets
                if asset.category is ApfCategory.FIELD_ART
            ),
            key=lambda asset: (
                asset.outer_index,
                -1 if asset.inner_index is None else asset.inner_index,
                asset.asset_id,
            ),
        )
    )
    _validate_exact_rows(assets)
    _validate_package_relationships(assets)

    team_labels = endzone_team_labels()
    records: list[FieldArtRecord] = []
    for asset in assets:
        contract = _NAME_CONTRACTS[asset.name]
        assert asset.inner_index is not None
        records.append(
            FieldArtRecord(
                asset_id=asset.asset_id,
                package_id=f"apf:outer:{asset.outer_index}",
                outer_index=asset.outer_index,
                inner_index=asset.inner_index,
                name=asset.name,
                type_name=asset.type_name,
                asset_class=asset.asset_class,
                kind=contract.kind,
                status=asset.status,
                export_label=asset.export_label,
                author_note=_AUTHOR_NOTES[contract.kind],
                team_label=(
                    team_labels.get(asset.outer_index)
                    if contract.kind is FieldArtKind.ENDZONE_TEXTURE
                    else None
                ),
            )
        )
    frozen_records = tuple(records)

    semantic_groups: list[FieldArtSemanticGroup] = []
    for kind in FieldArtKind:
        members = tuple(record for record in frozen_records if record.kind is kind)
        if len(members) != _GROUP_COUNTS[kind]:
            raise FieldArtInventoryError(
                f"APF {kind.title} group expected {_GROUP_COUNTS[kind]} rows, "
                f"found {len(members)}"
            )
        semantic_groups.append(
            FieldArtSemanticGroup(
                kind=kind,
                title=kind.title,
                records=members,
                package_ids=tuple(sorted({record.package_id for record in members})),
                author_note=_AUTHOR_NOTES[kind],
            )
        )

    package_groups: list[FieldArtPackageGroup] = []
    for outer_index in sorted({record.outer_index for record in frozen_records}):
        members = tuple(
            record for record in frozen_records if record.outer_index == outer_index
        )
        package_groups.append(
            FieldArtPackageGroup(
                package_id=f"apf:outer:{outer_index}",
                outer_index=outer_index,
                records=members,
                kinds=tuple(
                    kind for kind in FieldArtKind if any(row.kind is kind for row in members)
                ),
                ownership_note=_PACKAGE_OWNERSHIP_NOTE,
            )
        )

    type_counts = {
        "txtr_records": sum(record.type_name == "TXTR" for record in frozen_records),
        "scne_records": sum(record.type_name == "SCNE" for record in frozen_records),
        "curve_anim_records": sum(
            record.type_name == "CurveAnim" for record in frozen_records
        ),
    }
    if type_counts != {
        "txtr_records": 248,
        "scne_records": 8,
        "curve_anim_records": 2,
    }:
        raise FieldArtInventoryError("APF Field Art type totals changed")

    return FieldArtInventory(
        records=frozen_records,
        semantic_groups=tuple(semantic_groups),
        package_groups=tuple(package_groups),
        summary=MappingProxyType(
            {
                "semantic_records": len(frozen_records),
                "semantic_groups": len(semantic_groups),
                "archive_packages": len(package_groups),
                **type_counts,
                "editable_records": 0,
            }
        ),
        findings=(
            "All 258 existing Field Art catalog rows are represented exactly once in seven semantic groups.",
            "The 235 endzone textures occupy 118 archive packages: 117 named l0/l1 pairs and one l0-only package.",
            "Every endzone package is one team's own artwork. Package 6 is not "
            "a shared layer — it is structurally identical to the other 117 and "
            "is simply the pair whose writer was proved first, so editing it "
            "repaints that one team's endzone.",
            ENDZONE_MASK_CONTRACT,
            ENDZONE_IDENTITY_NOTE,
            f"{len(team_labels)} of the 118 endzone packages have been "
            "identified by their artwork so far; the rest show their package "
            "index rather than a guess.",
            _PACKAGE_OWNERSHIP_NOTE,
            "Every record remains browse/export-only until a bounded writer and runtime consumer are proved.",
        ),
    )


#: One contact sheet holds this many packages, which keeps each sheet under a
#: size an image viewer opens comfortably while staying big enough to read a
#: mascot at a glance.
CONTACT_SHEET_ROWS = 12
CONTACT_SHEET_COLUMNS = 2
CONTACT_TILE_WIDTH = 512
CONTACT_TILE_HEIGHT = 128
CONTACT_LABEL_HEIGHT = 18


def export_endzone_contact_sheets(
    index_0a: "Path",
    destination: "Path",
    progress=None,
    outer_indices: "tuple[int, ...] | None" = None,
) -> tuple["Path", ...]:
    """Render every endzone package into labelled sheets for identification.

    This is the supported answer to "which package is my team's endzone".
    A name search cannot work -- the nicknames are not on the disc -- so the
    only route is to look at the artwork, and doing that by hand meant writing
    a decode script and eyeballing 118 PNGs.  One action now produces the same
    thing: each tile carries its package index and, where someone has already
    identified it, the team.

    ``outer_indices`` lets a caller that already has the inventory name the 118
    endzone packages instead of parsing all 1,543 archive entries to rediscover
    them, which is most of the wall-clock cost.  Omitting it scans, so the
    function still works standalone.

    The user's volume is opened read-only and nothing is written back to it.
    """

    from PIL import Image, ImageDraw

    from .backend import ensure_tools_importable

    ensure_tools_importable()
    import apf_inner  # type: ignore
    import apf_outer  # type: ignore

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    labels = endzone_team_labels()
    archive = apf_outer.parse_archive(Path(index_0a))
    tiles: list[tuple[int, object]] = []
    with apf_inner.ArchiveReader(archive) as reader:
        if outer_indices:
            wanted = {int(value) for value in outer_indices}
            candidates = [
                entry for entry in archive.entries if entry.table_index in wanted
            ]
        else:
            candidates = list(archive.entries)
        for position, entry in enumerate(candidates):
            if progress is not None:
                progress("Reading endzone packages", position, len(candidates))
            try:
                record = apf_inner.parse_iff(reader, entry, strict_footer=False)
            except Exception:
                continue
            base_file = next(
                (
                    item
                    for item in getattr(record, "files", ())
                    if getattr(item, "name", "") == "endzone_l0"
                ),
                None,
            )
            if base_file is None:
                continue
            parts = list(base_file.parts)
            header_part, base_part = parts[0], parts[-1]
            header = apf_inner.decode_block(
                reader, record, header_part.block_index, 64 << 20
            )[header_part.offset : header_part.offset + header_part.length]
            metadata = apf_inner.parse_txtr_metadata(header)
            payload = apf_inner.decode_block(
                reader, record, base_part.block_index, 64 << 20
            )[base_part.offset : base_part.offset + base_part.length]
            width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, payload)
            image = (
                Image.frombytes("RGBA", (width, height), rgba)
                .convert("RGB")
                .resize((CONTACT_TILE_WIDTH, CONTACT_TILE_HEIGHT), Image.LANCZOS)
            )
            tiles.append((entry.table_index, image))
    if not tiles:
        raise FieldArtInventoryError(
            "No endzone packages were found in the selected volume"
        )

    per_sheet = CONTACT_SHEET_ROWS * CONTACT_SHEET_COLUMNS
    written: list[Path] = []
    tile_pitch = CONTACT_TILE_HEIGHT + CONTACT_LABEL_HEIGHT + 6
    sheet_count = (len(tiles) + per_sheet - 1) // per_sheet
    for sheet_index in range(sheet_count):
        group = tiles[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
        rows = (len(group) + CONTACT_SHEET_COLUMNS - 1) // CONTACT_SHEET_COLUMNS
        sheet = Image.new(
            "RGB",
            (
                CONTACT_SHEET_COLUMNS * (CONTACT_TILE_WIDTH + 8) + 8,
                rows * tile_pitch + 8,
            ),
            (18, 18, 22),
        )
        draw = ImageDraw.Draw(sheet)
        for position, (outer_index, image) in enumerate(group):
            x = 8 + (position % CONTACT_SHEET_COLUMNS) * (CONTACT_TILE_WIDTH + 8)
            y = 8 + (position // CONTACT_SHEET_COLUMNS) * tile_pitch
            team = labels.get(outer_index)
            draw.text(
                (x, y),
                f"package {outer_index}" + (f"  —  {team}" if team else ""),
                fill=(236, 236, 240) if team else (168, 168, 176),
            )
            sheet.paste(image, (x, y + CONTACT_LABEL_HEIGHT))
        path = destination / f"apf-endzone-contact-sheet-{sheet_index + 1:02d}.png"
        sheet.save(path)
        written.append(path)
        if progress is not None:
            progress("Writing contact sheets", sheet_index + 1, sheet_count)
    return tuple(written)


__all__ = [
    "CONTACT_SHEET_COLUMNS",
    "CONTACT_SHEET_ROWS",
    "ENDZONE_IDENTITY_NOTE",
    "ENDZONE_LABELS",
    "ENDZONE_LABELS_SCHEMA",
    "ENDZONE_MASK_CONTRACT",
    "FIELD_ART_PACKAGE_COUNT",
    "FIELD_ART_RECORD_COUNT",
    "FieldArtInventory",
    "FieldArtInventoryError",
    "FieldArtKind",
    "FieldArtPackageGroup",
    "FieldArtRecord",
    "FieldArtSemanticGroup",
    "build_field_art_inventory",
    "endzone_team_labels",
    "export_endzone_contact_sheets",
]
