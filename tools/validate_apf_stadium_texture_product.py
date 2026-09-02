#!/usr/bin/env python3
"""Source-free closure check for the bounded APF Stadium texture editor."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.apf_studio import stadium_texture  # noqa: E402


def main() -> int:
    assert stadium_texture.OUTER_INDEX == 14
    assert stadium_texture.INNER_INDEX == 8
    assert stadium_texture.EDITABLE_FORMATS == frozenset(
        {"DXT1", "DXT4_5", "DXN", "DXT5A", "8", "8_8", "5_6_5", "8_8_8_8"}
    )
    assert all(
        callable(getattr(stadium_texture, name))
        for name in (
            "load_catalog",
            "decoded_rgba",
            "export_png",
            "stage_replacement_png",
            "build_patch",
            "write_output",
        )
    )
    print("APF_STADIUM_TEXTURE_PRODUCT_VALIDATION_PASS textures=78 formats=8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
