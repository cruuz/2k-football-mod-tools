"""Pin the all-slot retail crest channel audit that protects compatibility."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_retail_crest_blue_contract_is_persisted() -> None:
    report = json.loads(
        (ROOT / "docs/mod_editor/apf2k8_retail_crest_channel_audit.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["scope"]["catalog_slots"] == 118
    assert report["result"] == {
        "slots_with_nonzero_display_blue_logo_l0": 114,
        "slots_with_nonzero_display_blue_logo_l1": 19,
        "nonzero_display_blue_texels_logo_l0": 4_864_531,
        "nonzero_display_blue_texels_logo_l1": 243_204,
        "slots_with_zero_display_blue_in_both_layers": [9, 24, 65, 82],
        "unique_layer_blue_count_pairs": 115,
    }
    assert report["contract"]["retail_compatibility_migration_preserves_arbitrary_rgba"]
    assert report["contract"]["globally_zeroing_retail_blue_is_forbidden"]
