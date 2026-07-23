"""Retail-free product views of APF gameplay and presentation findings.

The development tree owns richer, hash-pinned research reports.  Release
packages deliberately exclude the entire ``reports`` tree, so the APF desktop
product consumes only this small sanitized projection.  It contains names,
counts, proof booleans, and author-facing warnings: never retail payloads,
executable addresses, profile values, or writer coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

from .inspectors import InspectorRow, PagedModel, _row


PRODUCT_FINDINGS = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "apf2k8_product_findings.v1.json"
)
PRODUCT_FINDINGS_SCHEMA = "apf2k8_mod_studio_product_findings/v1"
_RAW_ADDRESS = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)


class ProductFindingsError(ValueError):
    """Raised when the packaged product projection is missing or malformed."""


@dataclass(frozen=True)
class ProductInspectorSnapshot:
    summary: Mapping[str, int]
    model: PagedModel


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProductFindingsError(f"APF product findings are missing {label}")
    return value


def _rows(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ProductFindingsError(f"APF product findings are missing {label} rows")
    return tuple(value)


def load_product_findings(path: Path = PRODUCT_FINDINGS) -> Mapping[str, object]:
    try:
        payload = path.read_text(encoding="utf-8")
        document = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductFindingsError(
            f"Could not load the retail-free APF product findings: {exc}"
        ) from exc
    if not isinstance(document, dict) or document.get("schema") != PRODUCT_FINDINGS_SCHEMA:
        raise ProductFindingsError("APF product findings use an unsupported schema")
    if _RAW_ADDRESS.search(payload):
        raise ProductFindingsError("APF product findings contain a raw address")
    _mapping(document.get("gameplay"), "gameplay")
    _mapping(document.get("presentation"), "presentation")
    return document


def gameplay_snapshot(
    document: Mapping[str, object] | None = None,
) -> ProductInspectorSnapshot:
    root = document or load_product_findings()
    gameplay = _mapping(root.get("gameplay"), "gameplay")
    stock_range = _mapping(gameplay.get("stock_ui_range"), "stock slider range")
    platform_proof = dict(
        _mapping(gameplay.get("platform_proof"), "gameplay platform proof")
    )
    slider_names = _rows(gameplay.get("sliders"), "gameplay slider")
    if len(slider_names) != 21 or not all(
        isinstance(value, str) and value for value in slider_names
    ):
        raise ProductFindingsError("APF gameplay findings must name exactly 21 sliders")
    if platform_proof.get("exact_serialized_value_count") != 21:
        raise ProductFindingsError("APF slider serialization count changed")

    minimum = float(stock_range.get("minimum", -1))
    maximum = float(stock_range.get("maximum", -1))
    step = float(stock_range.get("step", -1))
    if (minimum, maximum, step) != (0.0, 1.0, 0.025):
        raise ProductFindingsError("APF stock slider range changed")

    slider_rows: list[InspectorRow] = []
    for index, name_value in enumerate(slider_names):
        name = str(name_value)
        fields: dict[str, object] = {
            "index": index,
            "name": name,
            "stock_minimum": minimum,
            "stock_maximum": maximum,
            "stock_step": step,
            "current_profile_value_available": bool(
                gameplay.get("current_values_available")
            ),
            "save_or_profile_writer_available": bool(
                gameplay.get("save_or_profile_writer_available")
            ),
            "executable_writer_available": bool(
                gameplay.get("executable_writer_available")
            ),
            "out_of_range_runtime_safety_proved": bool(
                gameplay.get("out_of_range_runtime_safety_proved")
            ),
            "exact_serialized_value_count": int(
                platform_proof["exact_serialized_value_count"]
            ),
            "exact_serialized_byte_count": int(
                platform_proof["exact_serialized_byte_count"]
            ),
            "offline_and_online_controls_share_callbacks_and_state": bool(
                platform_proof[
                    "offline_and_online_controls_share_callbacks_and_state"
                ]
            ),
        }
        if name in {"Human Catching", "CPU Catching"}:
            fields.update(
                {
                    "catching_runtime_copy_mapped": bool(
                        platform_proof["catching_runtime_copy_mapped"]
                    ),
                    "final_catch_or_drop_consumer_proved": bool(
                        platform_proof["final_catch_or_drop_consumer_proved"]
                    ),
                }
            )
        slider_rows.append(
            _row(
                f"apf:gameplay:slider:{index:02d}",
                "gameplay_slider",
                name,
                f"Stock order {index:02d} · 0.0–1.0 in 0.025 steps · read-only",
                fields,
            )
        )

    draft = _mapping(gameplay.get("draft_lineage"), "draft lineage")
    proof_status = dict(_mapping(draft.get("proof_status"), "draft proof status"))
    weight_values = _rows(draft.get("position_weights"), "draft position weight")
    if len(weight_values) != 17 or proof_status.get("table_copy_count") != 2:
        raise ProductFindingsError("APF draft-lineage findings changed")
    draft_rows: list[InspectorRow] = []
    seen_positions: set[str] = set()
    for item in weight_values:
        weight = _mapping(item, "draft position weight")
        position = str(weight.get("position", ""))
        if not position or position in seen_positions:
            raise ProductFindingsError("APF draft positions are empty or duplicated")
        seen_positions.add(position)
        position_code = int(weight.get("position_code", -1))
        value = float(weight.get("weight", -1))
        draft_rows.append(
            _row(
                f"apf:gameplay:draft-lineage:{position.casefold()}",
                "draft_lineage_weight",
                position,
                f"Retained stock weight {value:g} · not a live APF AI control",
                {
                    "position_code": position_code,
                    "position": position,
                    "retained_weight": value,
                    "proof_status": proof_status,
                    "safe_writer_available": bool(
                        draft.get("safe_writer_available")
                    ),
                    "runtime_patch_performed": bool(
                        draft.get("runtime_patch_performed")
                    ),
                },
            )
        )

    findings = (
        str(gameplay.get("warning", "APF gameplay settings are read-only.")),
        str(draft.get("warning", "APF draft lineage is read-only.")),
        "Human/CPU Catching controls are named, but the final catch/drop consumer and polarity are not proved; no catch-strength preset is enabled.",
        "The 2,254 player records expose exact 0–99 editing for all 28 independent base ratings in Rosters & Players; this Gameplay view does not duplicate them or confuse player attributes with global sliders.",
    )
    return ProductInspectorSnapshot(
        summary={
            "sliders": len(slider_rows),
            "draft_lineage_weights": len(draft_rows),
            "editable_controls": 0,
        },
        model=PagedModel(tuple(slider_rows + draft_rows), findings),
    )


def presentation_snapshot(
    document: Mapping[str, object] | None = None,
) -> ProductInspectorSnapshot:
    root = document or load_product_findings()
    presentation = _mapping(root.get("presentation"), "presentation")
    field = _mapping(presentation.get("field_scorebug"), "field scorebug")
    component_values = _rows(field.get("components"), "scorebug component")
    if len(component_values) != 7:
        raise ProductFindingsError("APF field scorebug must contain seven components")

    rows: list[InspectorRow] = []
    seen_names: set[str] = set()
    for item in component_values:
        component = _mapping(item, "scorebug component")
        name = str(component.get("name", ""))
        if not name or name in seen_names:
            raise ProductFindingsError("APF scorebug component names are empty or duplicated")
        seen_names.add(name)
        mesh_count = int(component.get("mesh_count", -1))
        triangle_count = int(component.get("triangle_count", -1))
        rows.append(
            _row(
                f"apf:presentation:component:{name}",
                "scorebug_scene_component",
                name,
                f"{mesh_count} meshes · {triangle_count} triangles · geometry read-only",
                {
                    "name": name,
                    "mesh_count": mesh_count,
                    "triangle_count": triangle_count,
                    "geometry_writer_available": bool(
                        component.get("writer_available")
                    ),
                    "runtime_behavior_writer_available": bool(
                        field.get("runtime_behavior_writer_available")
                    ),
                },
            )
        )

    font = _mapping(presentation.get("digital_font"), "digital font")
    dimensions = _rows(font.get("dimensions"), "digital-font dimension")
    required_rgb = _rows(font.get("required_png_rgb"), "digital-font RGB")
    if tuple(dimensions) != (128, 128) or tuple(required_rgb) != (255, 255, 255):
        raise ProductFindingsError("APF digital_font authoring contract changed")
    font_fields = dict(font)
    rows.append(
        _row(
            "apf:presentation:digital_font",
            "digital_font_writer_boundary",
            "digital_font",
            "128×128 DXT5A · alpha-only mask · bounded PNG writer",
            font_fields,
        )
    )

    findings = (
        str(
            presentation.get(
                "warning", "APF presentation geometry and behavior are read-only."
            )
        ),
        "Season GameCast is a separate presentation system; it is not the seven-part field scorebug.",
        "digital_font is shared globally, so edits may affect UI outside the field scorebug; runtime visibility is not proved.",
    )
    return ProductInspectorSnapshot(
        summary={
            "scorebug_scene_components": len(component_values),
            "bounded_texture_writers": int(
                presentation.get("safe_writer_count", 0)
            ),
            "semantic_rows": len(rows),
        },
        model=PagedModel(tuple(rows), findings),
    )


__all__ = [
    "PRODUCT_FINDINGS",
    "PRODUCT_FINDINGS_SCHEMA",
    "ProductFindingsError",
    "ProductInspectorSnapshot",
    "gameplay_snapshot",
    "load_product_findings",
    "presentation_snapshot",
]
