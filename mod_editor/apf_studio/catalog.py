"""Live, retail-free APF archive and product catalog.

Every record is derived from the user's selected four-volume archive.  The
cache contains names, indices, sizes, and classifications only; it never stores
decoded or compressed game payloads.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterable

from mod_editor.core.capabilities import CapabilityRegistryLoader, Classification
from mod_editor.core.model import GameId

from .backend import PRODUCT_ROOT, ensure_tools_importable
from .models import (
    ApfProductAction,
    ApfAsset,
    ApfCategory,
    ApfSource,
    ApfStatus,
    CapabilityCard,
    ExternalAudioBankIdentity,
    UNIFORM_FAMILY_CAPABILITY_IDS,
    UniformAsset,
    asset_action_binding,
    capability_action_binding,
)
from .inspectors import InspectorError, discover_external_audio_banks


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402
import apf_uniform_inventory  # type: ignore  # noqa: E402
import apf_textlogo_patch  # type: ignore  # noqa: E402

from .uniform_targets import load_targets


Progress = Callable[[str, int, int], None]
CATALOG_SCHEMA = "apf2k8_mod_studio_live_catalog/v1"


class CatalogError(ValueError):
    """Raised when the live archive cannot satisfy the proved grammar."""


def _noop(_stage: str, _completed: int, _total: int) -> None:
    return None


def _category_for(name: str, type_name: str) -> ApfCategory:
    value = f"{name} {type_name}".casefold()
    if type_name in {"AUDO", "AUSB", "XMA1_BANK"} or any(
        token in value for token in ("audio", "sound", "music", "comment")
    ):
        return ApfCategory.AUDIO
    if "crowd" in value:
        return ApfCategory.STADIUMS
    if type_name in {"PLAY", "DRCT"} or "playbook" in value:
        return ApfCategory.PLAYBOOKS
    if type_name == "ROST" or any(token in value for token in ("player", "roster", "portrait", "head")):
        return ApfCategory.ROSTERS
    if "uniform" in value or any(
        token in value
        for token in ("jersey", "pants", "helmet", "shoulder", "sock", "shoe", "glove", "numberfont", "namefont")
    ):
        return ApfCategory.UNIFORMS
    if any(token in value for token in ("logo", "teamcard", "team_card")):
        return ApfCategory.LOGOS
    if any(token in value for token in ("scorebug", "scoreboard", "gamecast", "digital_font", "halftime", "replay")):
        return ApfCategory.SCOREBUG
    if any(token in value for token in ("field", "turf", "endzone", "midfield", "grass", "divot")):
        return ApfCategory.FIELD_ART
    if any(token in value for token in ("stadium", "stad_")):
        return ApfCategory.STADIUMS
    if type_name in {"LAYT", "STRG", "TXT loc system", "FONT", "KERN"} or any(
        token in value for token in ("frontend", "menu", "layout", "localization", "quicknav")
    ):
        return ApfCategory.MENUS
    if any(token in value for token in ("season", "franchise", "schedule", "coachdesk")):
        return ApfCategory.FRANCHISE
    return ApfCategory.ALL_ASSETS


def _status_for(
    outer_index: int, inner_index: int | None, type_name: str, name: str
) -> ApfStatus:
    asset_id = (
        f"apf:outer:{outer_index}"
        if inner_index is None
        else f"apf:outer:{outer_index}:inner:{inner_index}"
    )
    action = asset_action_binding(
        asset_id, outer_index, inner_index, name, type_name
    )
    capability = (
        capability_action_binding(action.capability_id) if action else None
    )
    if capability is not None and capability.has_complete_editor:
        return ApfStatus.EDITABLE
    if type_name in {"TXTR", "SCNE", "AUDO", "AUSB", "CurveAnim", "SingleMoCap"}:
        return ApfStatus.EXPORT_ONLY
    if type_name in {
        "ROST",
        "PLAY",
        "DRCT",
        "LAYT",
        "STRG",
        "TXT loc system",
        "SPCI",
        "FSMR",
    }:
        return ApfStatus.PREVIEW
    return ApfStatus.EXPORT_ONLY


def _notes_for(
    outer_index: int,
    inner_index: int | None,
    type_name: str,
    name: str,
    status: ApfStatus,
) -> tuple[str, ...]:
    asset_id = (
        f"apf:outer:{outer_index}"
        if inner_index is None
        else f"apf:outer:{outer_index}:inner:{inner_index}"
    )
    action = asset_action_binding(
        asset_id, outer_index, inner_index, name, type_name
    )
    if action is not None:
        return action.notes
    if status is ApfStatus.PREVIEW:
        return ("This structure is mapped for browsing; replacement is not yet safe.",)
    if status is ApfStatus.EXPORT_ONLY:
        if type_name == "XMA1_BANK":
            return (
                "Exact physical XMA1 packet bank named by its source-owned AUSB descriptor.",
                "This is a multi-cue raw container: export is available, but Play, Replace, and shortlist actions belong only to its addressed substream rows.",
            )
        if type_name == "TXTR":
            return (
                "PNG export is attempted for decoded formats; an exact raw-parts ZIP is always available.",
                "No validated replacement writer owns this target yet.",
            )
        return (
            "Only an exact raw export is available here; no decoded authoring format or validated writer owns this target yet.",
        )
    return ()


def _external_audio_catalog_identities(
    source: ApfSource,
    iff_entries: Iterable[dict[str, object]],
) -> tuple[ExternalAudioBankIdentity, ...]:
    try:
        return discover_external_audio_banks(source.index_0a, iff_entries)
    except InspectorError as exc:
        raise CatalogError(f"Could not route external APF audio banks: {exc}") from exc


def _apply_external_audio_catalog_policy(
    assets: Iterable[ApfAsset],
    identities: Iterable[ExternalAudioBankIdentity],
) -> tuple[ApfAsset, ...]:
    """Name and route the 19 raw outer banks without bundling a manifest."""

    owned = {identity.outer_table_index: identity for identity in identities}
    if len(owned) != 19:
        raise CatalogError(
            f"Expected 19 external audio banks, found {len(owned)}"
        )
    result: list[ApfAsset] = []
    matched: set[int] = set()
    for asset in assets:
        identity = owned.get(asset.outer_index) if asset.inner_index is None else None
        if identity is None:
            result.append(asset)
            continue
        if (
            asset.asset_id != identity.raw_asset_id
            or asset.decoded_size != identity.encoded_size
            or asset.outer_size != identity.encoded_size
            or asset.type_name not in {"NON_IFF", "XMA1_BANK"}
        ):
            raise CatalogError(
                f"External audio bank {identity.external_filename} no longer owns "
                f"the exact raw outer record {identity.outer_table_index}"
            )
        stored_name_id = str(asset.metadata.get("name_id", "")).casefold()
        if stored_name_id and stored_name_id != f"0x{identity.name_id:08x}":
            raise CatalogError(
                f"External audio bank {identity.external_filename} changed name identity"
            )
        owner_rows = tuple(
            {
                "descriptor_outer_index": owner.descriptor_outer_index,
                "descriptor_inner_index": owner.descriptor_inner_index,
                "bank_name": owner.bank_name,
                "substream_count": owner.substream_count,
                "sample_rate": owner.sample_rate,
                "derived_channel_count": owner.channel_count,
                "audio_source_id": owner.audio_source_id,
            }
            for owner in identity.owners
        )
        matched.add(asset.outer_index)
        result.append(
            replace(
                asset,
                name=identity.external_filename,
                type_name="XMA1_BANK",
                asset_class="external_xma1_packet_bank",
                category=ApfCategory.AUDIO,
                status=ApfStatus.EXPORT_ONLY,
                notes=_notes_for(
                    identity.outer_table_index,
                    None,
                    "XMA1_BANK",
                    identity.external_filename,
                    ApfStatus.EXPORT_ONLY,
                ),
                metadata={
                    **dict(asset.metadata),
                    "name_id": f"0x{identity.name_id:08x}",
                    "external_filename": identity.external_filename,
                    "descriptor_owner_count": len(identity.owners),
                    "descriptor_owners": owner_rows,
                    "addressable_substream_rows": sum(
                        owner.substream_count for owner in identity.owners
                    ),
                },
            )
        )
    if matched != set(owned):
        missing = ", ".join(str(value) for value in sorted(set(owned) - matched))
        raise CatalogError(f"External audio bank outer records are missing: {missing}")
    return tuple(result)


@dataclass(frozen=True)
class ApfCatalog:
    source_sha256: str
    outer_count: int
    iff_count: int
    non_iff_count: int
    inner_count: int
    assets: tuple[ApfAsset, ...]
    uniform_assets: tuple[UniformAsset, ...]
    capabilities: tuple[CapabilityCard, ...]
    audio_selection_manifest: Path

    def get(self, asset_id: str) -> ApfAsset:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        raise CatalogError(f"Unknown APF asset: {asset_id}")

    def uniform(self, asset_id: str) -> UniformAsset:
        for asset in self.uniform_assets:
            if asset.asset_id == asset_id:
                return asset
        raise CatalogError(f"Unknown APF uniform asset: {asset_id}")

    def browse(
        self,
        *,
        search: str = "",
        category: ApfCategory | None = None,
        status: ApfStatus | None = None,
        type_name: str | None = None,
        offset: int = 0,
        limit: int = 250,
    ) -> tuple[ApfAsset, ...]:
        needle = search.strip().casefold()
        result: list[ApfAsset] = []
        for asset in self.assets:
            if category is not None and category is not ApfCategory.ALL_ASSETS and asset.category is not category:
                continue
            if status is not None and asset.status is not status:
                continue
            if type_name and asset.type_name != type_name:
                continue
            if needle and needle not in (
                f"{asset.name} {asset.type_name} {asset.asset_class} "
                f"{asset.outer_index} {asset.inner_index}"
            ).casefold():
                continue
            result.append(asset)
        return tuple(result[max(0, offset) : max(0, offset) + max(1, limit)])

    @property
    def type_names(self) -> tuple[str, ...]:
        return tuple(sorted({item.type_name for item in self.assets}))


class CatalogBuilder:
    def __init__(self, cache_root: Path | None = None):
        self.cache_root = cache_root or Path.home() / ".cache" / "apf2k8-mod-studio"

    def build(
        self,
        source: ApfSource,
        progress: Progress = _noop,
        *,
        force: bool = False,
    ) -> ApfCatalog:
        cache = self.cache_root / "catalogs" / source.source_sha256
        document_path = cache / "catalog.json"
        selection_path = cache / "inner-selection.json"
        if not force and document_path.is_file() and selection_path.is_file():
            try:
                return self._load_cached(document_path, selection_path, source)
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        cache.mkdir(parents=True, exist_ok=True)
        archive = apf_outer.parse_archive(source.index_0a)
        assets: list[ApfAsset] = []
        iff_entries: list[dict[str, object]] = []
        iff_count = 0
        non_iff_count = 0
        with apf_inner.ArchiveReader(archive) as reader:
            for ordinal, entry in enumerate(archive.entries, start=1):
                if ordinal == 1 or ordinal % 25 == 0 or ordinal == len(archive.entries):
                    progress("Indexing every APF game asset", ordinal, len(archive.entries))
                if entry.head_hex != f"{apf_inner.IFF_MAGIC:08x}":
                    non_iff_count += 1
                    name = f"outer_{entry.table_index:04d}"
                    assets.append(
                        ApfAsset(
                            asset_id=f"apf:outer:{entry.table_index}",
                            outer_index=entry.table_index,
                            inner_index=None,
                            name=name,
                            type_name="NON_IFF",
                            asset_class="opaque_outer_resource",
                            category=ApfCategory.ALL_ASSETS,
                            status=ApfStatus.EXPORT_ONLY,
                            decoded_size=entry.size,
                            outer_size=entry.size,
                            part_count=len(entry.segments),
                            notes=("Unknown outer record; raw export is available.",),
                            metadata={"name_id": f"0x{entry.name_id:08x}"},
                        )
                    )
                    continue
                try:
                    record = apf_inner.parse_iff(reader, entry)
                except apf_inner.FormatError as exc:
                    raise CatalogError(
                        f"Outer entry {entry.table_index} no longer matches the APF IFF grammar: {exc}"
                    ) from exc
                iff_count += 1
                manifest_files: list[dict[str, object]] = []
                for item in record.files:
                    name = item.name or f"file_{item.index:04d}"
                    type_name = item.type_name or f"0x{item.type_hash:08x}"
                    status = _status_for(entry.table_index, item.index, type_name, name)
                    asset_class = apf_inner.ASSET_CLASSES.get(type_name, "unknown")
                    parts = tuple(item.parts)
                    assets.append(
                        ApfAsset(
                            asset_id=f"apf:outer:{entry.table_index}:inner:{item.index}",
                            outer_index=entry.table_index,
                            inner_index=item.index,
                            name=name,
                            type_name=type_name,
                            asset_class=asset_class,
                            category=_category_for(name, type_name),
                            status=status,
                            decoded_size=sum(part.length for part in parts),
                            outer_size=entry.size,
                            part_count=len(parts),
                            notes=_notes_for(
                                entry.table_index,
                                item.index,
                                type_name,
                                name,
                                status,
                            ),
                            metadata={
                                "file_id": f"0x{item.file_id:08x}",
                                "type_hash": f"0x{item.type_hash:08x}",
                                "block_indices": sorted({part.block_index for part in parts}),
                            },
                        )
                    )
                    manifest_files.append(
                        {"index": item.index, "name": name, "type_name": type_name}
                    )
                iff_entries.append(
                    {"table_index": entry.table_index, "files": manifest_files}
                )
        if len(archive.entries) != 1543 or iff_count != 1473 or non_iff_count != 70:
            raise CatalogError(
                "The APF archive inventory changed unexpectedly "
                f"(outer={len(archive.entries)}, IFF={iff_count}, non-IFF={non_iff_count})."
            )
        if sum(1 for item in assets if item.inner_index is not None) != 10_394:
            raise CatalogError("The APF inner asset count changed unexpectedly")
        external_audio = _external_audio_catalog_identities(source, iff_entries)
        assets = list(_apply_external_audio_catalog_policy(assets, external_audio))
        selection_payload = {
            "schema": "apf2k8_mod_studio_private_selection/v1",
            "source_sha256": source.source_sha256,
            "iff_entries": iff_entries,
        }
        self._write_json_atomic(selection_path, selection_payload)
        uniforms = build_uniform_assets(source.index_0a)
        capabilities = build_capability_cards()
        document = {
            "schema": CATALOG_SCHEMA,
            "source_sha256": source.source_sha256,
            "outer_count": len(archive.entries),
            "iff_count": iff_count,
            "non_iff_count": non_iff_count,
            "inner_count": 10_394,
            "assets": [
                {
                    **asdict(asset),
                    "category": asset.category.value,
                    "status": asset.status.value,
                }
                for asset in assets
            ],
        }
        self._write_json_atomic(document_path, document)
        return ApfCatalog(
            source_sha256=source.source_sha256,
            outer_count=len(archive.entries),
            iff_count=iff_count,
            non_iff_count=non_iff_count,
            inner_count=10_394,
            assets=tuple(assets),
            uniform_assets=uniforms,
            capabilities=capabilities,
            audio_selection_manifest=selection_path,
        )

    def _load_cached(
        self, path: Path, selection: Path, source: ApfSource
    ) -> ApfCatalog:
        document = json.loads(path.read_text(encoding="utf-8"))
        selection_document = json.loads(selection.read_text(encoding="utf-8"))
        if (
            document.get("schema") != CATALOG_SCHEMA
            or document.get("source_sha256") != source.source_sha256
            or document.get("outer_count") != 1543
            or document.get("iff_count") != 1473
            or document.get("non_iff_count") != 70
            or document.get("inner_count") != 10_394
        ):
            raise CatalogError("Cached APF inventory is stale")
        iff_entries = selection_document.get("iff_entries")
        if (
            selection_document.get("schema")
            != "apf2k8_mod_studio_private_selection/v1"
            or selection_document.get("source_sha256") != source.source_sha256
            or not isinstance(iff_entries, list)
            or len(iff_entries) != 1473
            or any(
                not isinstance(row, dict) or not isinstance(row.get("files"), list)
                for row in iff_entries
            )
            or sum(
                len(row["files"])
                for row in iff_entries
                if isinstance(row, dict) and isinstance(row.get("files"), list)
            )
            != 10_394
        ):
            raise CatalogError("Cached APF inner selection is stale")
        loaded_assets: list[ApfAsset] = []
        for row in document["assets"]:
            outer_index = int(row["outer_index"])
            inner_index = (
                None if row["inner_index"] is None else int(row["inner_index"])
            )
            type_name = str(row["type_name"])
            name = str(row["name"])
            # Status and product-facing notes are policy, not retail-derived
            # cache data. Recompute them so an older private catalog unlocks a
            # newly wired bounded writer without requiring a destructive cache
            # migration.
            status = _status_for(outer_index, inner_index, type_name, name)
            loaded_assets.append(
                ApfAsset(
                    asset_id=row["asset_id"],
                    outer_index=outer_index,
                    inner_index=inner_index,
                    name=name,
                    type_name=type_name,
                    asset_class=row["asset_class"],
                    # Category routing is also product policy. Recompute it so
                    # existing private catalogs immediately stop presenting
                    # crowd TXTR/SCNE resources as sounds.
                    category=_category_for(name, type_name),
                    status=status,
                    decoded_size=int(row["decoded_size"]),
                    outer_size=int(row["outer_size"]),
                    part_count=int(row["part_count"]),
                    notes=_notes_for(
                        outer_index, inner_index, type_name, name, status
                    ),
                    metadata=dict(row.get("metadata", {})),
                )
            )
        assets = tuple(loaded_assets)
        if len(assets) != 10_464:
            raise CatalogError("Cached APF asset coverage is incomplete")
        external_audio = _external_audio_catalog_identities(source, iff_entries)
        assets = _apply_external_audio_catalog_policy(assets, external_audio)
        return ApfCatalog(
            source_sha256=source.source_sha256,
            outer_count=1543,
            iff_count=1473,
            non_iff_count=70,
            inner_count=10_394,
            assets=assets,
            uniform_assets=build_uniform_assets(source.index_0a),
            capabilities=build_capability_cards(),
            audio_selection_manifest=selection,
        )

    @staticmethod
    def _write_json_atomic(path: Path, document: object) -> None:
        data = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            temporary.unlink(missing_ok=True)
            raise


def build_uniform_assets(index_0a: Path) -> tuple[UniformAsset, ...]:
    """Return the uniform-material assets plus all rectangular wordmarks."""

    _source, team_rows = apf_uniform_inventory._load_team_selectors(index_0a)  # type: ignore[attr-defined]
    team_uses: dict[tuple[str, int], set[str]] = {}
    for team in team_rows:
        name = str(team["display_name"] or f"Team {team['team_index']}")
        for bank in team["banks"]:
            for selector in bank["selectors"]:
                for family in selector["families"]:
                    if family == "shoulder_normal":
                        continue
                    team_uses.setdefault(
                        (str(family), int(selector["asset_index_byte_0"])), set()
                    ).add(name)
    targets = load_targets()
    definitions = (
        (
            "jersey",
            targets["jersey"],
            1024,
            1024,
            "1024x1024 RGBA PNG. Treat channels as material-mask inputs; visible colors are shader-driven, not literal paint.",
            (
                "Asset 6 is runtime-proved and corroborated in Xenia's Home/Away editor.",
                "Alpha and RGB are not ordinary final-color layers.",
            ),
        ),
        (
            "pants",
            targets["pants"],
            512,
            512,
            "512x512 opaque RGBA PNG. Alpha must be 255 everywhere.",
            (
                "Runtime-proved in the Americans Away Uniform Type PANTS leg preview with an unmistakable checker witness.",
                "Broader channel/material behavior remains under study.",
            ),
        ),
        (
            "helmet",
            targets["helmet"],
            256,
            1024,
            "256x1024 RGBA PNG. R and G are the two stored DXN channels; B must be 0 and A must be 255.",
            (
                "This is the helmet's centre stripe, not the shell. R and G are "
                "region masks the game fills with team colours -- R renders "
                "light, G renders dark -- the same scheme the team crest uses.",
                "Only a narrow front-to-crown band of this map reaches the "
                "helmet. A full-coverage probe showed the rest is off-model "
                "padding, so art painted outside the lit column renders nowhere.",
                "APF helmets have no shell texture at all: the package holds "
                "only this stripe and a normal map, both DXN (two channels, so "
                "no RGB is possible). Shell colour comes from the team palette.",
            ),
        ),
        (
            "shoulder",
            targets["shoulder"],
            1024,
            1024,
            "1024x1024 RGBA PNG. This changes shoulder_color only and preserves the paired normal package.",
            ("Material-mask behavior may differ from a normal color texture.",),
        ),
        (
            "textlogo",
            apf_textlogo_patch.load_targets(),
            512,
            128,
            "512x128 opaque RGBA PNG. The Logos → Wordmarks importer can contain or cover-fit ordinary art and flattens transparency onto black.",
            (
                "Selector slot 6: rectangular team/menu wordmark, not the square helmet crest.",
                "All six tiled BC1 mip levels are regenerated inside the selected fixed package allocation.",
            ),
        ),
    )
    result: list[UniformAsset] = []
    for family, rows, width, height, contract, notes in definitions:
        expected_count = 206 if family == "textlogo" else 24
        if len(rows) != expected_count:
            raise CatalogError(
                f"{family} catalog no longer contains {expected_count} assets"
            )
        capability_id = UNIFORM_FAMILY_CAPABILITY_IDS[family]
        action = capability_action_binding(capability_id)
        product_status = (
            ApfStatus.EDITABLE
            if action is not None and action.has_complete_editor
            else ApfStatus.COMING_SOON
        )
        for row in rows:
            asset_index = int(row["asset_index"])
            inner = row["inner_file"]
            result.append(
                UniformAsset(
                    family=family,
                    asset_index=asset_index,
                    asset_id=f"apf:uniform:{family}:{asset_index:02d}",
                    title=f"{family.title()} {asset_index:02d}",
                    width=width,
                    height=height,
                    png_contract=contract,
                    status=product_status,
                    outer_index=int(row["outer_table_index"]),
                    inner_index=int(inner["index"]),
                    affected_teams=tuple(sorted(team_uses.get((family, asset_index), ()))),
                    notes=notes,
                )
            )
    return tuple(result)


def _capability_category(surface: str, capability_id: str) -> ApfCategory:
    if capability_id == "apf2k8.models.scne_gltf":
        return ApfCategory.UNIFORMS
    if capability_id == "apf2k8.colors.uniform_selector_appearance_custom_team":
        return ApfCategory.UNIFORMS
    if capability_id.startswith("apf2k8.colors.uniform_selector"):
        return ApfCategory.TEAM_IDENTITY
    if surface == "uniforms":
        return ApfCategory.UNIFORMS
    if surface == "logos_cards":
        return ApfCategory.LOGOS
    if surface in {"players_rosters", "portraits_faces"}:
        return ApfCategory.ROSTERS
    if surface == "scorebug_presentation":
        return ApfCategory.SCOREBUG
    if surface in {"stadiums_fields", "models_shap_scne", "cross_title_model_conversion"}:
        return ApfCategory.STADIUMS
    if surface in {"menus", "mode_state_routing"}:
        return ApfCategory.MENUS
    if surface == "audio":
        return ApfCategory.AUDIO
    if surface == "scripts_config":
        return ApfCategory.PLAYBOOKS
    if surface in {"schedules_franchise", "franchise_restoration_cross_title", "saves"}:
        return ApfCategory.FRANCHISE
    if surface in {"catching_drops", "cpu_ai_draft", "gameplay_tuning_sliders"}:
        return ApfCategory.GAMEPLAY
    return ApfCategory.ALL_ASSETS


def build_capability_cards() -> tuple[CapabilityCard, ...]:
    registry = CapabilityRegistryLoader().load(
        allow_sample_fallback=False, check_files=False
    )
    cards: list[CapabilityCard] = []
    capabilities = registry.for_game(GameId.APF2K8)
    for capability in capabilities:
        gui = capability.raw.get("gui", {})
        action = capability_action_binding(capability.capability_id)
        status = ApfStatus.COMING_SOON
        exposed = gui.get("expose") is True
        if not exposed:
            status = (
                ApfStatus.EVIDENCE
                if capability.classification
                in {
                    Classification.RUNTIME_PROVED,
                    Classification.OFFLINE_WRITER_PROVED,
                }
                else ApfStatus.RESEARCH
            )
        elif action is not None:
            mode = gui.get("mode")
            if (
                mode == "edit"
                and (
                    action.has_complete_editor
                    or action.has_verified_one_shot_writer
                )
                and capability.classification
                in {
                    Classification.RUNTIME_PROVED,
                    Classification.OFFLINE_WRITER_PROVED,
                }
                and capability.raw.get("backend", {}).get("operation")
                == "write"
            ):
                status = ApfStatus.EDITABLE
            elif mode == "export" and ApfProductAction.EXPORT in action.actions:
                status = ApfStatus.EXPORT_ONLY
            elif mode == "view" and ApfProductAction.PREVIEW in action.actions:
                status = ApfStatus.PREVIEW
        findings: list[str] = []
        if action is None and gui.get("expose") is True:
            findings.append(
                "No dedicated Mod Studio semantic handler is wired yet; universal rows retain only their separately labeled raw export."
            )
        elif action is not None and action.product_note:
            findings.append(action.product_note)
        reason = gui.get("reason")
        if isinstance(reason, str) and reason.strip():
            findings.append(reason.strip())
        runtime = capability.raw.get("runtime", {}).get("scope")
        if isinstance(runtime, str) and runtime.strip():
            findings.append(runtime.strip())
        for item in capability.raw.get("portme", ())[:2]:
            if isinstance(item, str):
                findings.append(f"Boundary: {item}")
        cards.append(
            CapabilityCard(
                capability_id=capability.capability_id,
                title=capability.title,
                summary=capability.summary,
                category=_capability_category(
                    capability.surface, capability.capability_id
                ),
                status=status,
                findings=tuple(findings),
            )
        )
    if len(cards) != len(capabilities):
        raise CatalogError("APF capability cards no longer match the registry")
    return tuple(cards)
