#!/usr/bin/env python3
"""Build one bounded cement01 stadium-texture edit into a copied NFL 2K5 XISO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache  # noqa: E402
from mod_editor.core.nfl2k5_stadium_cache import (  # noqa: E402
    Nfl2k5StadiumCacheCoordinator,
)
from mod_editor.core.nfl2k5_stadium_studio import Nfl2k5StadiumStudio  # noqa: E402
from mod_editor.core.nfl2k5_stadium_texture_writer import (  # noqa: E402
    Nfl2k5StadiumTextureWriter,
    StadiumTextureWriterError,
    TARGET_SCENE_ID,
    TARGET_TEXTURE_ID,
)


def run(
    source_xiso: Path,
    replacement_png: Path,
    output_xiso: Path,
    manifest: Path,
) -> dict[str, object]:
    cache = Nfl2k5SourceCache().index(source_xiso)
    stadium_cache = Nfl2k5StadiumCacheCoordinator().load_existing(cache)
    if stadium_cache is None:
        raise StadiumTextureWriterError(
            "The private Stadium Studio cache is not ready. Open Stadium Studio "
            "once and let its asset preparation finish before using this writer."
        )
    studio = Nfl2k5StadiumStudio(
        stadium_cache.gltf_manifest,
        stadium_cache.texture_manifest,
        stadium_cache.texture_root,
    )
    texture = next(
        row for row in studio.scene_details(TARGET_SCENE_ID).textures
        if row.texture_id == TARGET_TEXTURE_ID
    )
    writer = Nfl2k5StadiumTextureWriter(cache, stadium_cache)
    compiled = writer.compile(texture, replacement_png)
    result = writer.build_xiso(compiled, output_xiso, manifest)
    return {
        "texture_id": TARGET_TEXTURE_ID,
        "replacement_png_sha256": compiled.replacement_png_sha256,
        "quantized_base_rgba_sha256": compiled.quantized_base_rgba_sha256,
        "mip_rgba_sha256": list(compiled.mip_rgba_sha256),
        "encoded_bytes": compiled.encoded_bytes,
        "scratch_after": compiled.scratch_after,
        "output_xiso": str(result.output_xiso),
        "manifest": str(result.manifest),
        "output_xiso_sha256": result.output_sha256,
        "changed_byte_count": result.changed_byte_count,
        "changed_run_count": result.changed_run_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--replacement-png", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(
            args.source_xiso,
            args.replacement_png,
            args.output_xiso,
            args.manifest,
        )
    except (OSError, ValidationError, KeyError, StopIteration) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
