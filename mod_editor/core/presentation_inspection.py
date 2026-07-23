"""Sanitized, hash-pinned APF scorebug/presentation inspection."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "reports/assets/scorebug_presentation_audit.json"
AUDIT_SIZE = 46_512
AUDIT_SHA256 = "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1"
AUDIT_SCHEMA = "vc_scorebug_presentation_audit/v1"
FONT_LAYOUT = ROOT / "reports/assets/apf_digital_font_layout.json"
FONT_LAYOUT_SIZE = 4_920
FONT_LAYOUT_SHA256 = "1d5e83d476dee76b4013c957cb450b316ab2251d0337907e269855ac8c800a02"
FONT_LAYOUT_SCHEMA = "apf_digital_font_layout/v1"
FONT_ROUNDTRIP = ROOT / "reports/assets/apf_digital_font_patch_roundtrip.json"
FONT_ROUNDTRIP_SIZE = 4_737
FONT_ROUNDTRIP_SHA256 = "c1ccb433832fe4c3465c2f9632e3a31887133cc5f8cf811cdff71ec9b36cd06e"
FONT_ROUNDTRIP_SCHEMA = "apf_digital_font_patch_roundtrip/v1"


def _read(path: Path, size: int, digest: str, schema: str, label: str) -> dict[str, Any]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} report is missing: {path}") from exc
    if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
        raise ValidationError(f"{label} report must be a non-symlink regular file")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            supplied.st_dev, supplied.st_ino, size
        ):
            raise ValidationError(f"{label} report identity or size changed")
        payload = bytearray()
        while len(payload) < size:
            block = os.read(descriptor, size - len(payload))
            if not block:
                raise ValidationError(f"{label} report ended early")
            payload.extend(block)
        if os.read(descriptor, 1):
            raise ValidationError(f"{label} report grew while reading")
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size) != (
            opened.st_dev, opened.st_ino, opened.st_size
        ):
            raise ValidationError(f"{label} report changed while reading")
    finally:
        os.close(descriptor)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValidationError(f"{label} report hash does not match the pinned audit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{label} report is invalid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValidationError(f"{label} report schema does not match")
    return value


def _provenance(path: Path, size: int, digest: str, schema: str) -> dict[str, Any]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "size": size,
        "sha256": digest,
        "schema": schema,
    }


def inspect_apf_scorebug_presentation(
    audit_path: Path = AUDIT,
    font_layout_path: Path = FONT_LAYOUT,
    font_roundtrip_path: Path = FONT_ROUNDTRIP,
) -> dict[str, Any]:
    """Return named APF scorebug owners and the exact safe writer boundary."""

    audit = _read(audit_path, AUDIT_SIZE, AUDIT_SHA256, AUDIT_SCHEMA, "Scorebug")
    layout = _read(
        font_layout_path,
        FONT_LAYOUT_SIZE,
        FONT_LAYOUT_SHA256,
        FONT_LAYOUT_SCHEMA,
        "Digital-font layout",
    )
    roundtrip = _read(
        font_roundtrip_path,
        FONT_ROUNDTRIP_SIZE,
        FONT_ROUNDTRIP_SHA256,
        FONT_ROUNDTRIP_SCHEMA,
        "Digital-font writer",
    )
    apf = audit["apf2k8"]
    components = [
        {
            "name": row["name"],
            "mesh_count": row["gltf"]["mesh_count"],
            "triangle_count": row["gltf"]["triangle_count"],
            "writer_available": False,
        }
        for row in apf["field_scorebug_package"]["resources"]
    ]
    descriptor = layout["target"]["descriptor"]
    conclusion = roundtrip["conclusion"]
    return {
        "schema": "mod_editor_apf_scorebug_presentation_inspection/v1",
        "game": "All-Pro Football 2K8",
        "platform": "Xbox 360",
        "source_reports": [
            _provenance(audit_path, AUDIT_SIZE, AUDIT_SHA256, AUDIT_SCHEMA),
            _provenance(
                font_layout_path,
                FONT_LAYOUT_SIZE,
                FONT_LAYOUT_SHA256,
                FONT_LAYOUT_SCHEMA,
            ),
            _provenance(
                font_roundtrip_path,
                FONT_ROUNDTRIP_SIZE,
                FONT_ROUNDTRIP_SHA256,
                FONT_ROUNDTRIP_SCHEMA,
            ),
        ],
        "access": "sanitized read-only evidence; no archive or executable opened",
        "field_scorebug": {
            "component_count": len(components),
            "components": components,
            "geometry_writer_available": False,
            "runtime_behavior_writer_available": False,
        },
        "season_gamecast_is_separate": True,
        "digital_font": {
            "name": "digital_font",
            "dimensions": [descriptor["width"], descriptor["height"]],
            "format": descriptor["format_name"],
            "stored_channel": "alpha only",
            "required_png_rgb": [255, 255, 255],
            "fixed_vram_size": descriptor["vc_base_data_length"],
            "exclusive_logical_owner": layout["ownership"][
                "target_vram_span_exclusive"
            ],
            "copy_only_writer_proved": conclusion[
                "copy_only_global_digital_font_cli_exposed"
            ],
            "all_unrelated_global_parts_preserved": conclusion[
                "all_750_unrelated_inner_parts_preserved"
            ],
            "global_ui_side_effect_warning_required": conclusion[
                "shared_global_ui_side_effect_warning_required"
            ],
            "production_encoder_ready": conclusion[
                "production_dxt5a_encoder_ready"
            ],
            "runtime_visibility_proved": conclusion[
                "xenia_runtime_visibility_proved"
            ],
        },
        "safe_writer_count": 1,
        "warning": (
            "Only the shared alpha-only digital_font has a proved copied-volume "
            "writer. The seven SCNE components, clocks, identity, visibility, "
            "timing, GameCast, replay/halftime, and audio remain separate and "
            "read-only."
        ),
    }


__all__ = ["inspect_apf_scorebug_presentation"]
