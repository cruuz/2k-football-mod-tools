"""Grouped fixed-allocation writer for all 188 NFL 2K5 Crib scene surfaces.

The retail-free Crib catalog supplies exact SCNE/texture ownership for 36
resources and 188 fixed-allocation embedded P8 textures. Edits sharing a SCNE
are decoded, composed, and recompressed once so one replacement cannot
overwrite another. The general P8 allocation compiler is the same reviewed
implementation used by Stadium Studio.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .errors import ValidationError
from . import nfl2k5_stadium_texture_writer as stadium
from .nfl2k5_crib import CribStorage, load_nfl2k5_crib_catalog

try:
    from nfl_outer import FormatError, parse_archive, read_entry_range
    from nfl_scene_probe import ProbeError, decode_resource, parse_inventory
    from nfl_scne_inventory import ScneError, parse_scene
    from nfl_txtr import HEADER, TxtrError
except ImportError as exc:  # pragma: no cover - installation boundary
    raise RuntimeError("The NFL SCNE toolchain is unavailable") from exc


SCHEMA = "nfl2k5_crib_scene_p8_import/v3"
PACK_PATH = "vc_53450030/C"
PACK_NAME = "C"
PACK_SECTOR = 2_554_593
PACK_SIZE = 315_131_904
PACK_SHA256 = "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090"
OUTER_INDEX = 4248


class CribSceneTextureWriterError(ValidationError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CribSceneTextureWriterError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_targets() -> Mapping[str, tuple[str, int, int]]:
    assets = tuple(
        asset for asset in load_nfl2k5_crib_catalog().assets
        if asset.storage is CribStorage.SCENE_EMBEDDED
    )
    _require(
        len(assets) == 188
        and all(
            asset.editable
            and asset.format_name == "P8"
            and asset.texture_index is not None
            and asset.scene_name is not None
            for asset in assets
        ),
        "The fixed-allocation Crib scene texture catalog changed.",
    )
    result = {
        asset.selector: (asset.asset_id, asset.chunk_index, int(asset.texture_index))
        for asset in assets
    }
    _require(len(result) == len(assets), "Crib scene selectors are duplicated.")
    return MappingProxyType(result)


TARGETS = _load_targets()


def is_editable_selector(selector: str) -> bool:
    return selector in TARGETS


def asset_id_for(selector: str) -> str:
    try:
        return TARGETS[selector][0]
    except KeyError as exc:
        raise CribSceneTextureWriterError(
            "Choose one of the 188 fixed-allocation Crib scene surfaces."
        ) from exc


class _Resolver:
    def __init__(self, index_path: Path, inventory_path: Path) -> None:
        try:
            self.archive = parse_archive(index_path)
            _document, resources = parse_inventory(inventory_path)
        except (OSError, FormatError, ProbeError, ValueError) as exc:
            raise CribSceneTextureWriterError(
                f"Could not resolve the private Crib scene inventory ({exc})."
            ) from exc
        self.scne_resources = tuple(row for row in resources if row.kind == "SCNE")
        _require(len(self.scne_resources) == 4_616, "NFL 2K5 SCNE inventory changed")

    def resolve_many(
        self, selectors: Sequence[str]
    ) -> tuple[stadium._ResolvedStadiumScene, ...]:
        _require(bool(selectors), "Choose at least one Crib surface")
        targets = []
        for selector in selectors:
            try:
                targets.append((selector, *TARGETS[selector]))
            except KeyError as exc:
                raise CribSceneTextureWriterError(
                    "Choose one of the 188 fixed-allocation Crib scene surfaces."
                ) from exc
        chunks = {row[2] for row in targets}
        _require(len(chunks) == 1, "One Crib compiler call may contain only one SCNE")
        chunk_index = next(iter(chunks))
        indexed = [
            (scene_index, resource)
            for scene_index, resource in enumerate(self.scne_resources)
            if resource.outer_index == OUTER_INDEX
            and resource.chunk_index == chunk_index
        ]
        _require(len(indexed) == 1, "Crib SCNE selector no longer resolves uniquely")
        scene_index, resource = indexed[0]
        entry = self.archive.entries[OUTER_INDEX]
        span_size = HEADER.size + resource.stored_size
        try:
            span = read_entry_range(
                self.archive, entry, resource.chunk_offset, span_size
            )
            decoded, detail = decode_resource(span, resource)
            scene, _names, _mappings, _sample = parse_scene(
                scene_index, resource, decoded, {}
            )
        except (OSError, FormatError, ProbeError, ScneError, TxtrError) as exc:
            raise CribSceneTextureWriterError(
                f"The selected Crib SCNE failed source replay ({exc})."
            ) from exc
        expected_scene = targets[0][0].split(":", 2)[1]
        _require(scene.get("name") == expected_scene, "Crib scene name changed")
        texture_rows = tuple(scene.get("embedded_textures", ()))
        _require(bool(texture_rows), "Crib SCNE has no embedded texture table")

        absolute_archive = entry.virtual_offset + resource.chunk_offset
        pack = next(
            (row for row in self.archive.packs
             if row.virtual_start <= absolute_archive
             and absolute_archive + span_size <= row.virtual_end),
            None,
        )
        _require(pack is not None and pack.name.casefold() == PACK_NAME.casefold(),
                 "Crib SCNE no longer belongs wholly to archive pack C")
        assert pack is not None
        lz = detail.get("lz")
        _require(isinstance(lz, dict), "Crib SCNE is not losslessly compressed")
        consumed = lz.get("consumed_bytes")
        _require(type(consumed) is int and 0 < consumed <= resource.stored_size,
                 "Crib SCNE compressed stream length changed")
        opaque_tail = span[HEADER.size + consumed:]
        decoded_sha = _sha256(decoded)
        base = {
            "outer_index": OUTER_INDEX,
            "outer_id": resource.outer_id,
            "chunk_index": chunk_index,
            "scene_index": scene_index,
            "pack_name": PACK_NAME,
            "pack_sector": PACK_SECTOR,
            "pack_size": PACK_SIZE,
            "pack_sha256": PACK_SHA256,
            "pack_offset": absolute_archive - pack.virtual_start,
            "chunk_offset": resource.chunk_offset,
            "stored_size": resource.stored_size,
            "system_bytes": resource.word_08,
            "video_bytes": resource.word_0c,
            "decoded_sha256": decoded_sha,
            "source_span_sha256": _sha256(span),
            "retail_consumed": consumed,
            "retail_scratch": resource.word_14,
            "opaque_tail_size": len(opaque_tail),
            "opaque_tail_sha256": _sha256(opaque_tail),
        }
        result = []
        for selector, _asset_id, _chunk, texture_index in targets:
            try:
                contract = stadium._DynamicStadiumResolver._target_contract(
                    selector, texture_index, texture_rows, decoded, base
                )
            except stadium.StadiumTextureWriterError as exc:
                raise CribSceneTextureWriterError(str(exc)) from exc
            result.append(stadium._ResolvedStadiumScene(
                contract, resource, span, decoded, opaque_tail, texture_rows
            ))
        return tuple(result)


def build_unified_crib_scene_texture_imports(
    index_path: Path,
    inventory_path: Path,
    edits: Sequence[tuple[str, Path]],
) -> list[tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]]:
    _require(bool(edits), "Choose at least one Crib surface to build")
    selectors = [selector for selector, _path in edits]
    _require(len(selectors) == len(set(selectors)), "Crib surface target repeats")
    grouped: dict[int, list[tuple[str, Path]]] = {}
    for selector, png in edits:
        if selector not in TARGETS:
            raise CribSceneTextureWriterError(
                "Choose one of the 188 fixed-allocation Crib scene surfaces."
            )
        grouped.setdefault(TARGETS[selector][1], []).append((selector, png))
    resolver = _Resolver(index_path, inventory_path)
    results = []
    for chunk_index, rows in grouped.items():
        resolved = resolver.resolve_many([selector for selector, _png in rows])
        try:
            compiled = stadium._compile_resolved_scene(
                resolved, [png for _selector, png in rows]
            )
        except stadium.StadiumTextureWriterError as exc:
            raise CribSceneTextureWriterError(str(exc)) from exc
        first = resolved[0].contract
        selector = (
            rows[0][0] if len(rows) == 1
            else f"crib-scene-texture-bundle:c{chunk_index:04d}"
        )
        target = first.target_metadata()
        target.update({
            "selector": selector,
            "asset_ids": [TARGETS[item[0]][0] for item in rows],
            "texture_ids": [item[0] for item in rows],
            "texture_count": len(rows),
            "xiso_pack_path": PACK_PATH,
            "xiso_pack_sector": PACK_SECTOR,
            "xiso_pack_size": PACK_SIZE,
            "xiso_pack_sha256": PACK_SHA256,
            "pack_offset": first.pack_offset,
            "xiso_absolute_span_offset": PACK_SECTOR * 2048 + first.pack_offset,
            "span_sha256": first.source_span_sha256,
        })
        previews = [
            (
                f"crib-c{chunk_index:04d}-t{payload.contract.texture_index:03d}-preview.png",
                payload.quantized_preview_png,
            )
            for payload in compiled.textures
        ]
        report = {
            "schema": SCHEMA,
            "target": target,
            "input_pngs": [
                {
                    "target": payload.contract.texture_id,
                    "path": str(path),
                    "sha256": payload.replacement_png_sha256,
                    "rgba_sha256": payload.replacement_rgba_sha256,
                }
                for payload, (_selector, path) in zip(compiled.textures, rows)
            ],
            "replacement": {
                "span_size": len(compiled.fixed.span),
                "span_sha256": _sha256(compiled.fixed.span),
                "decoded_after_sha256": compiled.fixed.decoded_sha256,
                "decoded_changed_byte_count": compiled.decoded_changed_byte_count,
                "encoded_bytes": compiled.fixed.encoded_bytes,
                "zero_gap_bytes": compiled.fixed.zero_gap_bytes,
                "scratch_after": compiled.fixed.scratch_after,
            },
            "compiled_textures": [
                stadium._compiled_payload_metadata(payload)
                for payload in compiled.textures
            ],
            "claims": {
                "all_catalogued_crib_scene_p8_surfaces": True,
                "source_derived_descriptor_and_material_ownership": True,
                "fixed_p8_mip_and_palette_allocations_only": True,
                "same_scene_edits_composed_before_compression": True,
                "complete_mip_chains_regenerated": True,
                "geometry_materials_and_other_textures_preserved": True,
                "opaque_tail_preserved": True,
                "contains_retail_bytes": False,
            },
        }
        results.append((compiled.fixed.span, previews, report, selector, target))
    return results


__all__ = [
    "CribSceneTextureWriterError",
    "TARGETS",
    "asset_id_for",
    "build_unified_crib_scene_texture_imports",
    "is_editable_selector",
]
