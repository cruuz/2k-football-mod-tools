"""Retail-free number-texture pins and All Textures writer bridge."""

from __future__ import annotations

from pathlib import Path

from .backend import ensure_tools_importable
from .models import (
    NUMBER_TEXTURE_KIND,
    ApfAsset,
    AssetActionBinding,
)


ensure_tools_importable()
import apf_number_texture_patch as number_patch  # type: ignore  # noqa: E402

NumberPatchError = number_patch.NumberPatchError


NUMBER_WIDTH = 512
NUMBER_HEIGHT = 512
AUTHORING_NOTE = (
    "512×512 RGBA PNG. Colour digits are DXT1; normals are two-channel DXN "
    "(R/G stored, B=0, A=255). All twenty digits in a package share one "
    "compressed budget — a set can overflow together even when one digit fits."
)


def load_targets() -> tuple[dict[str, object], ...]:
    return number_patch.load_targets()


def lookup(
    outer_index: int,
    inner_index: int | None,
    name: str | None = None,
    type_name: str | None = None,
) -> dict[str, object] | None:
    if inner_index is None or (type_name is not None and type_name != "TXTR"):
        return None
    if name is not None and number_patch.DIGIT_NAME_RE.fullmatch(name) is None:
        return None
    return number_patch.lookup_target(outer_index, inner_index, name)


def writable_locations() -> dict[tuple[int, int], str]:
    return {
        (int(row["entry_index"]), int(row["file_index"])): str(row["name"])
        for row in load_targets()
    }


def action_binding(
    asset_id: str,
    outer_index: int,
    inner_index: int | None,
    name: str,
    type_name: str,
) -> AssetActionBinding | None:
    row = lookup(outer_index, inner_index, name, type_name)
    if row is None:
        return None
    expected_id = f"apf:outer:{int(row['entry_index'])}:inner:{int(row['file_index'])}"
    if asset_id != expected_id:
        return None
    return AssetActionBinding(
        capability_id="apf2k8.uniforms.number_digits",
        handler_id="asset.number_png_editor",
        asset_id=expected_id,
        outer_index=int(row["entry_index"]),
        inner_index=int(row["file_index"]),
        name=str(row["name"]),
        type_name="TXTR",
        edit_id=expected_id,
        preview_method="preview_asset",
        export_method="export_asset",
        replace_method="replace_number",
        authoring_note=AUTHORING_NOTE,
        notes=(
            AUTHORING_NOTE,
            "Digits are stageable individually. The copied-volume writer "
            "recompresses the shared package once and names the digit and "
            "package if the set overflows. Runtime visibility is not claimed.",
        ),
    )


def compile_package_patch(
    index_0a: Path,
    entry_index: int,
    replacements: dict[str, Path],
):
    result = number_patch.build_package_patch(index_0a, entry_index, replacements)
    source = result.manifest.get("source", {})
    if not isinstance(source, dict) or source.get("outer_entry_index") != entry_index:
        raise number_patch.NumberPatchError(
            "The number writer resolved a different retail package"
        )
    result.manifest["kind"] = NUMBER_TEXTURE_KIND
    return result
