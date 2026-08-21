"""Retail-free number-texture pins and All Textures writer bridge."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Mapping

from .backend import ensure_tools_importable
from .models import (
    NUMBER_TEXTURE_KIND,
    ApfAsset,
    AssetActionBinding,
)


ensure_tools_importable()
import apf_inner  # type: ignore  # noqa: E402
import apf_number_texture_patch as number_patch  # type: ignore  # noqa: E402
import apf_outer  # type: ignore  # noqa: E402

NumberPatchError = number_patch.NumberPatchError


NUMBER_WIDTH = 512
NUMBER_HEIGHT = 512
AUTHORING_NOTE = (
    "512×512 RGBA PNG. Colour digits are DXT1; normals are two-channel DXN "
    "(R/G stored, B=0, A=255). All twenty digits in a package share one "
    "compressed budget — a set can overflow together even when one digit fits."
)
#: Measured on the retail disc (DIGIT_BUDGET_REPORT §2.1): the cheapest
#: non-blank replacement is one solid-colour glyph with no outline.  Digits
#: are NOT region-mask slots, so the jersey/shoulder flattening bands do not
#: apply; the only honest bands are "a solid glyph fits" and "nothing fits".
SOLID_DIGIT_COST_BYTES = 1_792
OUTLINED_DIGIT_COST_BYTES = 2_975
DIGIT_BUDGET_BOUNDARY = (
    "The digit writer is proved and byte-bounded. Retail uses ~99.9% of each "
    "package block, but the build encodes with the smaller of the preserving "
    "and greedy H7A encoders and regenerates mip tails, so a consistent digit "
    "set usually fits; lone off-style digits in tight packages can still "
    "overflow and the build names them."
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


@lru_cache(maxsize=32)
def _cached_package_budget(index_0a: str, entry_index: int) -> dict[str, int]:
    arc = apf_outer.parse_archive(Path(index_0a))
    try:
        entry = arc.entries[entry_index]
    except IndexError as exc:
        raise NumberPatchError(f"outer archive has no entry {entry_index}") from exc
    with apf_inner.ArchiveReader(arc) as reader:
        rec = apf_inner.parse_iff(reader, entry)
    return number_patch.number_package_budget(arc, entry, rec)


def package_budget(index_0a: Path, entry_index: int) -> dict[str, int]:
    """One number package's free compressed bytes, before any authoring.

    Header + block-table read only; the result is cached per (volume, entry)
    so browsing the twenty rows of one package costs one parse.
    """

    return _cached_package_budget(str(Path(index_0a)), int(entry_index))


def budget_band(free_bytes: int) -> str:
    """How much room the package has under the old preserving encoder.

    The build now re-encodes the shared block with the smaller of the
    preserving and greedy H7A encoders and regenerates the mip tail, so the
    band is context, not a verdict: self-similar sets routinely fit where a
    lone digit under the old encoder would not.
    """

    if free_bytes >= SOLID_DIGIT_COST_BYTES:
        return "loose"
    return "tight"


def budget_status_line(budget: Mapping[str, int]) -> str:
    """The up-front budget line shown under a digit row before authoring."""

    free = int(budget["free_bytes"])
    band = budget_band(free)
    verdict = (
        "Room for even the old preserving encoder's solid glyph."
        if band == "loose"
        else "Retail already uses ~99.9% of this block, but the build picks "
        "the smaller of two H7A encoders and regenerates the mip tail, so a "
        "consistent digit set usually fits anyway. The Build overflow check "
        "is the final word."
    )
    return (
        f"Free in this package: {free:,} bytes (tight under the old "
        f"preserving encoder; Band: {band}). {verdict}"
    )


def is_digit_overflow_target(target: str) -> bool:
    """True when an overflow target names jersey digits, not region masks.

    Overflow targets read ``number_1_color+number_7_color in package 862
    (uniform_number_04.iff)`` — every ``+``-joined name before " in package"
    must be a digit texture name.
    """

    label = str(target).split(" in package ", 1)[0]
    parts = label.split("+")
    return bool(parts) and all(
        number_patch.DIGIT_NAME_RE.fullmatch(part) for part in parts
    )


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
            DIGIT_BUDGET_BOUNDARY,
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
