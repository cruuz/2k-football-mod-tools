#!/usr/bin/env python3
"""Derive local-only NFL group36 geometry proof recipes from the retail source.

The checked tree intentionally contains no retail vertex coordinates.  This
helper derives the exact no-op positions only into a caller-selected temporary
path.  It can also derive the intentionally overflowing topology-only
permutation used to prove that fixed command footprint does not guarantee
VC-LZ fit.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import struct

import nfl_stadium_group36_geometry_patch as geometry
import nfl_stadium_group36_position_patch as position


def recipe(index: Path, mode: str) -> dict[str, object]:
    source = position._validate_source(index)
    decoded = bytes(source["decoded"])
    retail_positions = [
        list(struct.unpack_from("<3f", decoded, position.POSITION_OFFSET + vertex * 12))
        for vertex in range(4)
    ]
    return {
        "schema": geometry.RECIPE_SCHEMA,
        "operation": "replace_exact_same_footprint_positions_and_quad_indices",
        "profile_contract": geometry.PROFILE_CONTRACT,
        "target": geometry.TARGET,
        "encoding": {
            **position.ENCODING,
            "index_component_type": "uint16_le",
            "index_order": "native_quad_order",
        },
        "positions": retail_positions,
        "indices": [0, 1, 2, 3] if mode == "no-op" else [0, 2, 1, 3],
        "claim_flags": {
            "same_vertex_count": True,
            "same_index_count": True,
            "changed_count_or_relocation": False,
            "runtime_visibility_proved": False,
            "production_mesh_importer": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("no-op", "topology-only-permutation"))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"error: refusing to replace recipe path: {args.output}")
    args.output.write_bytes(geometry._canonical_json(recipe(args.index, args.mode)))
    geometry.load_recipe(args.output)
    print(f"NFL_GROUP36_GEOMETRY_PROOF_RECIPE_COMPLETE mode={args.mode} path={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, geometry.GeometryPatchError, position.PositionPatchError, struct.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
