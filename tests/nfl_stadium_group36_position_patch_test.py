#!/usr/bin/env python3
"""Full copied-volume round-trip and refusal proof for group36 positions."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_group36_position_patch as writer  # noqa: E402
import nfl_stadium_group36_position_verify as verifier  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
ZERO_RECIPE = ROOT / "reports/asset_samples/nfl_scne/stadium_group36_zero_recipe.json"
SCHEMA_PATH = ROOT / "reports/specs/nfl2k5_static_position_recipe.schema.json"

RETAIL_POSITIONS = [
    [6554.81298828125, 1848.93798828125, 6977.7041015625],
    [6554.81298828125, 1982.4000244140625, 6977.7021484375],
    [6369.21923828125, 1901.9410400390625, 6906.51806640625],
    [6369.21484375, 1848.93798828125, 6906.51611328125],
]

# Deterministic seed-0 binary32 values from the independent growth audit.
GROWTH_POSITIONS = [
    [6888.43701171875, 5159.087890625, -1588.568359375],
    [-4821.6650390625, 225.4944305419922, -1901.3172607421875],
    [5675.9716796875, -3933.745361328125, -468.0609130859375],
    [1667.6407470703125, 8162.2578125, 93.73711395263672],
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def recipe(path: Path, positions: list[list[float]]) -> str:
    value = {
        "schema": writer.RECIPE_SCHEMA,
        "target": writer.TARGET,
        "encoding": writer.ENCODING,
        "positions": positions,
    }
    payload = writer.canonical_json(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def publication_refusal_probes(root: Path) -> dict[str, bool]:
    # Symlinked parent is rejected before source access.
    real_parent = root / "publication-real"
    real_parent.mkdir()
    linked_parent = root / "publication-link"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    try:
        writer.patch(root / "missing-index", ZERO_RECIPE, linked_parent / "output")
    except writer.PositionPatchError as exc:
        symlink_parent = "non-symlink directory" in str(exc)
    else:
        symlink_parent = False
    assert symlink_parent

    # A name appearing after directory reservation but before publication is
    # never replaced.
    pre = root / "prepublication"
    pre.mkdir()
    pre_inode = writer._inode(pre)
    pre_stage = pre / ".staging"
    pre_stage.mkdir()
    (pre_stage / "9").write_bytes(b"ours-pack")
    (pre_stage / "manifest.json").write_bytes(b"ours-manifest")
    pre_known = {
        "9": writer._inode(pre_stage / "9"),
        "manifest.json": writer._inode(pre_stage / "manifest.json"),
    }
    (pre / "9").write_bytes(b"attacker")
    try:
        writer._publish_staged_no_replace(
            pre, pre_inode, pre_stage, writer._inode(pre_stage), pre_known
        )
    except writer.PositionPatchError:
        prepublication = (pre / "9").read_bytes() == b"attacker"
    else:
        prepublication = False
    assert prepublication

    # The first link succeeds, then a raced manifest makes the second link
    # fail. Owned links/staged files are cleaned, the attacker inode remains.
    partial = root / "partial-link"
    partial.mkdir()
    partial_inode = writer._inode(partial)
    partial_stage = partial / ".staging"
    partial_stage.mkdir()
    (partial_stage / "9").write_bytes(b"ours-pack")
    (partial_stage / "manifest.json").write_bytes(b"ours-manifest")
    partial_stage_inode = writer._inode(partial_stage)
    partial_known = {
        "9": writer._inode(partial_stage / "9"),
        "manifest.json": writer._inode(partial_stage / "manifest.json"),
    }
    real_link = writer.os.link
    link_calls = 0

    def second_link_race(source: Path, destination: Path, **kwargs: object) -> None:
        nonlocal link_calls
        link_calls += 1
        if link_calls == 1:
            real_link(source, destination, **kwargs)
            (partial / "manifest.json").write_bytes(b"attacker")
            return
        real_link(source, destination, **kwargs)

    with mock.patch.object(writer.os, "link", side_effect=second_link_race):
        try:
            writer._publish_staged_no_replace(
                partial, partial_inode, partial_stage, partial_stage_inode,
                partial_known,
            )
        except writer.PositionPatchError:
            pass
        else:
            raise AssertionError("partial second-link collision was accepted")
    writer._safe_cleanup_owned_reservation(
        partial, partial_inode, partial_stage, partial_stage_inode, partial_known
    )
    partial_collision = (
        (partial / "manifest.json").read_bytes() == b"attacker"
        and not (partial / "9").exists() and not partial_stage.exists()
    )
    assert partial_collision

    # Replace a staged path after linking but before owned cleanup. The writer
    # refuses and its cleanup preserves the replacement inode.
    replaced = root / "staged-replacement"
    replaced.mkdir()
    replaced_inode = writer._inode(replaced)
    replaced_stage = replaced / ".staging"
    replaced_stage.mkdir()
    replaced_stage_inode = writer._inode(replaced_stage)
    replaced_pack = replaced_stage / "9"
    replaced_manifest = replaced_stage / "manifest.json"
    replaced_pack.write_bytes(b"ours-pack")
    replaced_manifest.write_bytes(b"ours-manifest")
    replaced_known = {
        "9": writer._inode(replaced_pack),
        "manifest.json": writer._inode(replaced_manifest),
    }
    real_inode_check = writer._is_regular_inode
    staged_checks = 0

    def staged_replacement(path: Path, expected: tuple[int, int]) -> bool:
        nonlocal staged_checks
        if path == replaced_pack:
            staged_checks += 1
            if staged_checks == 2:
                replaced_pack.unlink()
                replaced_pack.write_bytes(b"attacker")
        return real_inode_check(path, expected)

    with mock.patch.object(
        writer, "_is_regular_inode", side_effect=staged_replacement
    ):
        try:
            writer._publish_staged_no_replace(
                replaced, replaced_inode, replaced_stage,
                replaced_stage_inode, replaced_known,
            )
        except writer.PositionPatchError:
            pass
        else:
            raise AssertionError("staged replacement was accepted")
    writer._safe_cleanup_owned_reservation(
        replaced, replaced_inode, replaced_stage, replaced_stage_inode,
        replaced_known,
    )
    staged_replace = (
        replaced_pack.read_bytes() == b"attacker"
        and not (replaced / "9").exists()
        and not replaced_manifest.exists() and replaced_stage.exists()
    )
    assert staged_replace
    return {
        "symlinked_output_parent": symlink_parent,
        "prepublication_raced_name": prepublication,
        "partial_second_link_collision": partial_collision,
        "staged_replacement_before_unlink": staged_replace,
    }


def run(report_path: Path) -> None:
    source_pack = INDEX.parent / "9"
    source_index_before = sha256_file(INDEX)
    source_pack_before = sha256_file(source_pack)
    assert source_index_before == writer.INDEX_SHA256
    assert source_pack_before == writer.PACK_SHA256
    schema_sha = sha256_file(SCHEMA_PATH)
    zero_sha = sha256_file(ZERO_RECIPE)
    assert zero_sha == "ad6b4fd7e658512c54770c66731adeea81e8b08b7731c981a0757b713a356781"

    with tempfile.TemporaryDirectory(
        prefix=".nfl-group36-position-test-", dir=ROOT
    ) as temporary:
        root = Path(temporary)
        noop_recipe = root / "noop-recipe.json"
        noop_sha = recipe(noop_recipe, RETAIL_POSITIONS)
        growth_recipe = root / "growth-recipe.json"
        growth_sha = recipe(growth_recipe, GROWTH_POSITIONS)
        publication_refusals = publication_refusal_probes(root)

        noop_dir = root / "noop"
        noop_manifest = writer.patch(INDEX, noop_recipe, noop_dir)
        noop_verify = verifier.verify(INDEX, noop_recipe, noop_dir)
        assert noop_manifest["mode"] == noop_verify["mode"] == "no_op"
        assert noop_verify["output"]["volume_sha256"] == writer.PACK_SHA256
        assert noop_verify["output"]["pack_changed_byte_count"] == 0
        assert noop_verify["compression"] == {
            "consumed_bytes": 908864,
            "retail_cap": 908864,
            "zero_gap_bytes": 0,
            "padding_bytes": 16,
            "minimum_alias_scratch_bytes": 0,
            "scratch_bytes": 16,
            "fixed_tail_sha256": writer.OPAQUE_TAIL_SHA256,
        }

        changed_dir = root / "changed"
        changed_manifest = writer.patch(INDEX, ZERO_RECIPE, changed_dir)
        changed_verify = verifier.verify(INDEX, ZERO_RECIPE, changed_dir)
        assert changed_manifest["mode"] == changed_verify["mode"] == "patched"
        assert changed_verify["output"]["volume_sha256"] == \
            "c48117938862fa03b5b3d871db87cb7d3c32a9653be497d46dc188ba51993fca"
        assert changed_verify["decoded"]["output_sha256"] == \
            "6c0ccfe11acf732efc7324b71b6665189adedfef71e69496a0e5c91f14d1432e"
        assert changed_verify["decoded"]["outside_position_bit_exact"] is True
        assert changed_verify["compression"] == {
            "consumed_bytes": 908825,
            "retail_cap": 908864,
            "zero_gap_bytes": 39,
            "padding_bytes": 55,
            "minimum_alias_scratch_bytes": 39,
            "scratch_bytes": 64,
            "fixed_tail_sha256": writer.OPAQUE_TAIL_SHA256,
        }
        assert changed_verify["rigid_static"] == {
            "one_zero_root": True,
            "selectors": [0, 0, 0, 0],
            "material": "cement01",
            "native_quads_indices": [0, 1, 2, 3],
        }

        # Existing artifacts and the retail source directory are refused before
        # source decoding or copying.
        try:
            writer.patch(INDEX, ZERO_RECIPE, changed_dir)
        except writer.PositionPatchError:
            existing_refused = True
        else:
            existing_refused = False
        assert existing_refused
        try:
            writer.patch(INDEX, ZERO_RECIPE, INDEX.parent)
        except writer.PositionPatchError:
            source_directory_refused = True
        else:
            source_directory_refused = False
        assert source_directory_refused

        growth_dir = root / "growth"
        try:
            writer.patch(INDEX, growth_recipe, growth_dir)
        except writer.PositionPatchError as exc:
            growth_refused = "908864-byte consumed-stream cap" in str(exc)
        else:
            growth_refused = False
        assert growth_refused and not growth_dir.exists()

        # A hardlink can have a different pathname but is still the retail
        # inode. The independent verifier must reject it explicitly.
        hardlink_dir = root / "hardlink-alias"
        hardlink_dir.mkdir()
        os.link(source_pack, hardlink_dir / "9")
        shutil.copyfile(noop_dir / "manifest.json", hardlink_dir / "manifest.json")
        try:
            verifier.verify(INDEX, noop_recipe, hardlink_dir)
        except verifier.VerifyError as exc:
            hardlink_refused = "inode aliases" in str(exc)
        else:
            hardlink_refused = False
        assert hardlink_refused

        # Exact recursive manifest key sets are part of the independent gate.
        manifest_path = changed_dir / "manifest.json"
        manifest_payload = manifest_path.read_bytes()
        mutated = json.loads(manifest_payload)
        mutated["source"]["resource"]["extra"] = True
        manifest_path.write_bytes(verifier.canonical_json(mutated))
        try:
            verifier.verify(INDEX, ZERO_RECIPE, changed_dir)
        except verifier.VerifyError as exc:
            manifest_extra_refused = "key set differs" in str(exc)
        else:
            manifest_extra_refused = False
        finally:
            manifest_path.write_bytes(manifest_payload)
        assert manifest_extra_refused
        # Restored manifest remains valid.
        assert verifier.verify(INDEX, ZERO_RECIPE, changed_dir)["mode"] == "patched"

    source_index_after = sha256_file(INDEX)
    source_pack_after = sha256_file(source_pack)
    assert source_index_after == source_index_before
    assert source_pack_after == source_pack_before
    report = {
        "schema": "nfl2k5_static_position_patch_roundtrip/v1",
        "source": {
            "index_sha256_before": source_index_before,
            "index_sha256_after": source_index_after,
            "volume_9_sha256_before": source_pack_before,
            "volume_9_sha256_after": source_pack_after,
            "retail_modified": False,
        },
        "recipe_contract": {
            "schema": writer.RECIPE_SCHEMA,
            "json_schema_sha256": schema_sha,
            "zero_recipe_sha256": zero_sha,
            "noop_recipe_sha256": noop_sha,
            "growth_recipe_sha256": growth_sha,
            "only_positions_authored": True,
            "replacement_positions_embedded_in_report": False,
        },
        "target": {
            **writer.TARGET,
            "encoding": writer.ENCODING,
            "rigid_static_proof": {
                "morph_count": 0, "transform_count": 1,
                "root_parent": -1, "root_absolute_xyz": [0, 0, 0],
                "selectors": [0, 0, 0, 0], "material": "cement01",
                "native_primitive": "QUADS", "indices": [0, 1, 2, 3],
            },
        },
        "no_op": noop_verify,
        "controlled_all_zero_edit": changed_verify,
        "refusals": {
            "existing_output_directory": existing_refused,
            "retail_source_directory_as_output": source_directory_refused,
            "tail_consuming_growth_recipe": growth_refused,
            "growth_output_artifact_created": False,
            "hardlink_source_alias": hardlink_refused,
            "recursive_manifest_extra_key": manifest_extra_refused,
            **publication_refusals,
        },
        "safety": {
            "fixed_outer_entry_extent": True,
            "fixed_chunk_stored_size": True,
            "fixed_final_opaque_tail": True,
            "zero_filled_new_gap": True,
            "scratch_capped_at_0x40": True,
            "decoded_change_limited_to_48_position_bytes": True,
            "pack_outside_chunk_bit_exact": True,
            "independent_verifier_imports_writer": False,
            "exclusive_output_files": ["9", "manifest.json"],
            "output_directory_atomically_reserved": True,
            "link_if_absent_publication_never_replaces": True,
            "cleanup_unlinks_owned_regular_inodes_only": True,
            "attacker_raced_inodes_preserved": True,
        },
        "claims": {
            "same_count_group36_float3_write_back_proved": True,
            "arbitrary_static_mesh_write_back_proved": False,
            "changed_topology_write_back_proved": False,
            "runtime_visibility_proved": False,
            "production_ready": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(writer.canonical_json(report))
    print(
        "NFL_GROUP36_POSITION_PATCH_TEST_PASS "
        "noop_pack_exact=true changed_pack=true growth_refused=true "
        "hardlink_refused=true manifest_extra_refused=true runtime=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    run(args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
