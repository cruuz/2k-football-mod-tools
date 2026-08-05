"""Public contract for one APF team crest and its shared helmet carrier."""

from __future__ import annotations

import math
from typing import Mapping


HELMET_CREST_DESIGN_EDIT_ID = "apf:logos:helmet_crest_design"
HELMET_CREST_DESIGN_KIND = "helmet_crest_design"

RETAIL_CREST_PROFILE = "retail_box"
FULL_SHELL_CREST_PROFILE = "front_crown_to_rear_v1"
HELMET_CREST_PROFILES = frozenset(
    {RETAIL_CREST_PROFILE, FULL_SHELL_CREST_PROFILE}
)

RETAIL_COVERAGE_SCOPE = "selected_team_retail_side_decal"
GLOBAL_COVERAGE_SCOPE = "global_helmet_model"

GLOBAL_HELMET_WARNING = (
    "This changes the shared helmet model for every team. The selected crest art "
    "remains team-specific, but every helmet crest uses the larger shell area. "
    "It creates no Xenia patch and does not edit default.xex."
)


class HelmetCrestDesignError(ValueError):
    """The shareable crest-design identity or fixed profile is invalid."""


def profile_scope(profile: str) -> str:
    if profile == RETAIL_CREST_PROFILE:
        return RETAIL_COVERAGE_SCOPE
    if profile == FULL_SHELL_CREST_PROFILE:
        return GLOBAL_COVERAGE_SCOPE
    raise HelmetCrestDesignError("Unknown helmet crest coverage profile")


def metadata(
    *,
    profile: str,
    crest_asset_index: int,
    crest_outer_entry_index: int,
    fit_visible_mask: bool,
    source_horizontal_coverage: float,
    output_horizontal_coverage: float,
) -> dict[str, object]:
    """Return canonical target metadata for a 512x512 RGBA crest payload."""

    value: dict[str, object] = {
        "width": 512,
        "height": 512,
        "storage_format": "xenos_4_4_4_4",
        "profile": profile,
        "coverage_scope": profile_scope(profile),
        "crest_asset_index": crest_asset_index,
        "crest_outer_entry_index": crest_outer_entry_index,
        "fit_visible_mask": fit_visible_mask,
        "source_horizontal_coverage": source_horizontal_coverage,
        "output_horizontal_coverage": output_horizontal_coverage,
        "mirrored_sides": True,
        "creates_xenia_patch": False,
        "edits_default_xex": False,
    }
    return validate_metadata(
        HELMET_CREST_DESIGN_EDIT_ID,
        HELMET_CREST_DESIGN_KIND,
        value,
    )


def validate_metadata(
    asset_id: str,
    kind: str,
    supplied: Mapping[str, object],
) -> dict[str, object]:
    """Validate the complete, slider-free project metadata contract."""

    value = dict(supplied)
    required = {
        "width",
        "height",
        "storage_format",
        "profile",
        "coverage_scope",
        "crest_asset_index",
        "crest_outer_entry_index",
        "fit_visible_mask",
        "source_horizontal_coverage",
        "output_horizontal_coverage",
        "mirrored_sides",
        "creates_xenia_patch",
        "edits_default_xex",
    }
    profile = value.get("profile")
    source_coverage = value.get("source_horizontal_coverage")
    output_coverage = value.get("output_horizontal_coverage")
    asset_index = value.get("crest_asset_index")
    outer_index = value.get("crest_outer_entry_index")
    fit = value.get("fit_visible_mask")
    if (
        asset_id != HELMET_CREST_DESIGN_EDIT_ID
        or kind != HELMET_CREST_DESIGN_KIND
        or set(value) != required
        or value.get("width") != 512
        or value.get("height") != 512
        or value.get("storage_format") != "xenos_4_4_4_4"
        or not isinstance(profile, str)
        or profile not in HELMET_CREST_PROFILES
        or value.get("coverage_scope") != profile_scope(profile)
        or type(asset_index) is not int
        or not 0 <= int(asset_index) < 118
        or type(outer_index) is not int
        or not 0 <= int(outer_index) < 1543
        or type(fit) is not bool
        or not isinstance(source_coverage, (int, float))
        or isinstance(source_coverage, bool)
        or not math.isfinite(float(source_coverage))
        or not 0.0 < float(source_coverage) <= 1.0
        or not isinstance(output_coverage, (int, float))
        or isinstance(output_coverage, bool)
        or not math.isfinite(float(output_coverage))
        or not 0.0 < float(output_coverage) <= 1.0
        or value.get("mirrored_sides") is not True
        or value.get("creates_xenia_patch") is not False
        or value.get("edits_default_xex") is not False
    ):
        raise HelmetCrestDesignError(
            "Helmet crest design project metadata changed"
        )
    if profile == RETAIL_CREST_PROFILE and fit:
        raise HelmetCrestDesignError(
            "Visible-mask fitting is available only for the full-shell profile"
        )
    if fit and float(output_coverage) != 1.0:
        raise HelmetCrestDesignError(
            "A fitted full-shell crest must occupy the complete horizontal range"
        )
    if not fit and float(output_coverage) != float(source_coverage):
        raise HelmetCrestDesignError(
            "An unfitted helmet crest cannot claim different mask coverage"
        )
    return value


__all__ = [
    "FULL_SHELL_CREST_PROFILE",
    "GLOBAL_COVERAGE_SCOPE",
    "GLOBAL_HELMET_WARNING",
    "HELMET_CREST_DESIGN_EDIT_ID",
    "HELMET_CREST_DESIGN_KIND",
    "HELMET_CREST_PROFILES",
    "HelmetCrestDesignError",
    "RETAIL_CREST_PROFILE",
    "metadata",
    "profile_scope",
    "validate_metadata",
]
