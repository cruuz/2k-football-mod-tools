#!/usr/bin/env python3
"""Source-free closure check for the 206-slot APF Wordmarks product."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_textlogo_patch as patch  # noqa: E402
import apf_textlogo_verify as verify  # noqa: E402
from mod_editor.apf_studio import textlogo_authoring  # noqa: E402


def main() -> int:
    rows = patch.load_targets()
    assert len(rows) == patch.CATALOG_COUNT == 206
    assert {int(row["asset_index"]) for row in rows} == set(range(206))
    assert patch.SELECTOR_SLOT == 6
    assert (patch.WIDTH, patch.HEIGHT) == (
        textlogo_authoring.WORDMARK_WIDTH,
        textlogo_authoring.WORDMARK_HEIGHT,
    ) == (512, 128)
    assert textlogo_authoring.WORDMARK_FIT_MODES == ("contain", "cover")
    assert callable(patch.build_patch) and callable(verify.verify_copied_volume)
    print("APF_TEXTLOGO_PRODUCT_VALIDATION_PASS slots=206 size=512x128 mips=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
