"""Validated retail-free APF stadium material findings for product surfaces.

The source tree contains much richer private research evidence.  This loader
accepts only the small, sanitized product projection: aggregate counts, proof
booleans, an author-facing boundary, and one bounded next experiment.  It
deliberately exposes no retail payload, archive coordinates, or executable
addresses.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


STADIUM_MATERIAL_FINDINGS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "apf2k8_stadium_material_findings.v1.json"
)
STADIUM_MATERIAL_FINDINGS_SCHEMA = (
    "apf2k8_mod_studio_stadium_material_findings/v1"
)

_RAW_ADDRESS = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)
_FORBIDDEN_PROVENANCE = (
    "sha256",
    "source_report",
    "source_reports",
    "retail_file",
    "outer_index",
    "inner_index",
    "system_offset",
    "extracted/",
)
_EXACT_EXPERIMENT: Mapping[str, object] = MappingProxyType(
    {
        "scene_name": "stadium",
        "scene_mesh_nodes": 116,
        "draw_records": 328,
        "serialized_material_records": 113,
        "shader_family_records": 13,
        "minimum_material_slot": 0,
        "maximum_material_slot": 112,
        "out_of_range_material_slots": 0,
        "known_named_texture_identities_checked": 737,
        "named_texture_identity_matches_in_scene_system_part": 0,
        "same_package_named_texture_candidates": 3,
        "same_package_identity_matches_in_scene_system_part": 0,
    }
)
_EXACT_PROOF: Mapping[str, bool] = MappingProxyType(
    {
        "draw_to_serialized_material_slot": True,
        "material_slot_to_serialized_material_record": True,
        "serialized_material_to_shader_family": True,
        "mesh_to_named_texture_identity": False,
        "texture_writer_safe_to_expose": False,
    }
)
_EXACT_RUNTIME_CAPTURE: Mapping[str, object] = MappingProxyType(
    {
        "route": "Wine-hosted Xenia instruction breakpoint",
        "outcome": "host_breakpoint_intercepted",
        "game_frame_rendered": False,
        "guest_registers_captured": False,
        "configuration_restored": True,
    }
)
_BOUNDARY_KEYS = frozenset(
    {
        "material_payload_status",
        "texture_reference_status",
        "package_candidate_status",
        "gpu_part_status",
        "product_behavior",
    }
)
_EXACT_MISSING_RUNTIME_FIELDS = (
    "the loaded stadium instance material-array base",
    "the selected pixel-shader eight-entry texture mapping",
    "the live texture object in each selected material texture record",
    "the guest allocation or resource identity behind each live texture object",
)


class StadiumMaterialFindingsError(ValueError):
    """The packaged stadium material projection is missing or malformed."""


@dataclass(frozen=True, slots=True)
class StadiumMaterialFindings:
    outcome: str
    experiment: Mapping[str, object]
    proof: Mapping[str, bool]
    runtime_capture: Mapping[str, object]
    boundary: Mapping[str, str]
    missing_runtime_fields: tuple[str, ...]
    author_summary: str
    best_next_experiment: str


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise StadiumMaterialFindingsError(
            f"APF stadium material findings are missing {label}"
        )
    return value


def _validate_payload_is_retail_free(payload: str) -> None:
    if _RAW_ADDRESS.search(payload):
        raise StadiumMaterialFindingsError(
            "APF stadium material findings contain a raw address"
        )
    lowered = payload.casefold()
    for forbidden in _FORBIDDEN_PROVENANCE:
        if forbidden in lowered:
            raise StadiumMaterialFindingsError(
                "APF stadium material findings contain retail or research provenance"
            )


def _author_summary(experiment: Mapping[str, object]) -> str:
    return (
        f"{experiment['scene_mesh_nodes']} scene meshes and "
        f"{experiment['draw_records']} draws map cleanly through "
        f"{experiment['serialized_material_records']} material records and "
        f"{experiment['shader_family_records']} shader families. Texture "
        f"ownership remains unresolved: none of the "
        f"{experiment['known_named_texture_identities_checked']} known named "
        "texture identities appears in the scene system part, so texture "
        "Replace/Revert stays disabled. A bounded Wine-hosted Xenia instruction "
        "breakpoint was intercepted by the host before a game frame or guest "
        "register capture, so that route is complete but did not test ownership."
    )


def load_stadium_material_findings(
    path: Path = STADIUM_MATERIAL_FINDINGS,
) -> StadiumMaterialFindings:
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StadiumMaterialFindingsError(
            f"Could not load the retail-free APF stadium material findings: {exc}"
        ) from exc

    _validate_payload_is_retail_free(payload)
    if (
        not isinstance(document, dict)
        or document.get("schema") != STADIUM_MATERIAL_FINDINGS_SCHEMA
    ):
        raise StadiumMaterialFindingsError(
            "APF stadium material findings use an unsupported schema"
        )
    if document.get("outcome") != "texture_owner_unresolved":
        raise StadiumMaterialFindingsError(
            "APF stadium material findings have an unsupported outcome"
        )

    experiment = dict(_mapping(document.get("experiment"), "experiment"))
    if experiment != dict(_EXACT_EXPERIMENT):
        raise StadiumMaterialFindingsError(
            "APF stadium material experiment counts or identities changed"
        )
    proof = dict(_mapping(document.get("proved"), "proof boundary"))
    # Equality is intentional: a newly true writer or ownership claim must be
    # reviewed as a capability upgrade, not silently accepted by old UI code.
    if proof != dict(_EXACT_PROOF):
        raise StadiumMaterialFindingsError(
            "APF stadium material proof booleans changed"
        )
    runtime_capture = dict(
        _mapping(document.get("runtime_capture"), "runtime capture result")
    )
    if runtime_capture != dict(_EXACT_RUNTIME_CAPTURE):
        raise StadiumMaterialFindingsError(
            "APF stadium material runtime capture result changed"
        )

    raw_boundary = dict(_mapping(document.get("boundary"), "product boundary"))
    if set(raw_boundary) != _BOUNDARY_KEYS or not all(
        isinstance(value, str) and value.strip()
        for value in raw_boundary.values()
    ):
        raise StadiumMaterialFindingsError(
            "APF stadium material product boundary is incomplete"
        )
    boundary = {key: str(value) for key, value in raw_boundary.items()}

    missing = document.get("missing_runtime_fields")
    if not isinstance(missing, list) or tuple(missing) != _EXACT_MISSING_RUNTIME_FIELDS:
        raise StadiumMaterialFindingsError(
            "APF stadium material runtime boundary changed"
        )
    best_next = document.get("best_next_experiment")
    if not isinstance(best_next, str) or not best_next.strip():
        raise StadiumMaterialFindingsError(
            "APF stadium material findings are missing the next experiment"
        )
    for required in (
        "material-array base",
        "pixel-shader mapping",
        "texture-object pointer",
        "guest allocation",
    ):
        if required not in best_next:
            raise StadiumMaterialFindingsError(
                "APF stadium material next experiment is incomplete"
            )

    return StadiumMaterialFindings(
        outcome="texture_owner_unresolved",
        experiment=MappingProxyType(experiment),
        proof=MappingProxyType(proof),
        runtime_capture=MappingProxyType(runtime_capture),
        boundary=MappingProxyType(boundary),
        missing_runtime_fields=_EXACT_MISSING_RUNTIME_FIELDS,
        author_summary=_author_summary(experiment),
        best_next_experiment=best_next.strip(),
    )


__all__ = [
    "STADIUM_MATERIAL_FINDINGS",
    "STADIUM_MATERIAL_FINDINGS_SCHEMA",
    "StadiumMaterialFindings",
    "StadiumMaterialFindingsError",
    "load_stadium_material_findings",
]
