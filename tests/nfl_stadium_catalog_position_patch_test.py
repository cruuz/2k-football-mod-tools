#!/usr/bin/env python3
"""Full copied-volume proof for catalog target stadium/upper_deck."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import struct
import sys
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_catalog_position_patch as writer  # noqa: E402
import nfl_stadium_catalog_position_verify as verifier  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
ZERO = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_nonretail_zero_recipe.v2.json"
SCHEMA = ROOT / "reports/specs/nfl2k5_catalog_static_position_recipe.v2.schema.json"
TARGET_ID = "nfl2k5/stadium/o3280/c5/s1"


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def write_recipe(path: Path, positions: list[list[float]]) -> str:
    value = {"catalog": {"schema": writer.CATALOG_SCHEMA, "sha256": writer.CATALOG_SHA256},
             "positions": positions, "schema": writer.RECIPE_SCHEMA, "target_id": TARGET_ID}
    payload = writer.canonical_json(value); path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def derive_noop(source: dict[str, object], contract: dict[str, int | str]) -> list[list[float]]:
    # Retail coordinates are read only into this temporary proof process and
    # never serialized into a repository artifact or the report.
    decoded = bytes(source["decoded"]); offset, end = int(contract["offset"]), int(contract["end"])
    return [list(xyz) for xyz in struct.iter_unpack("<3f", decoded[offset:end])]


def deterministic_growth() -> list[list[float]]:
    randomizer = random.Random(0); values: list[float] = []
    for _ in range(36):
        bits = randomizer.getrandbits(32) & 0x7F7FFFFF
        values.append(struct.unpack("<f", struct.pack("<I", bits or 1))[0])
    return [values[index:index + 3] for index in range(0, len(values), 3)]


def publication_refusals(root: Path) -> dict[str, bool]:
    pre = root / "prepublication"; pre.mkdir()
    staging = pre / ".staging"; staging.mkdir()
    (staging / "9").write_bytes(b"ours-pack")
    (staging / "manifest.json").write_bytes(b"ours-manifest")
    known = {name: writer._inode(staging / name) for name in ("9", "manifest.json")}
    (pre / "9").write_bytes(b"attacker")
    try:
        writer._publish_staged_no_replace(pre, writer._inode(pre), staging,
                                           writer._inode(staging), known)
    except writer.CatalogPositionPatchError:
        prepublication = (pre / "9").read_bytes() == b"attacker"
    else:
        prepublication = False
    assert prepublication

    partial = root / "partial-link"; partial.mkdir()
    stage = partial / ".staging"; stage.mkdir()
    (stage / "9").write_bytes(b"ours-pack")
    (stage / "manifest.json").write_bytes(b"ours-manifest")
    partial_inode, stage_inode = writer._inode(partial), writer._inode(stage)
    known = {name: writer._inode(stage / name) for name in ("9", "manifest.json")}
    real_link = writer.os.link; calls = 0

    def raced_link(source: Path, destination: Path, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            real_link(source, destination, **kwargs)
            (partial / "manifest.json").write_bytes(b"attacker")
            return
        real_link(source, destination, **kwargs)

    with mock.patch.object(writer.os, "link", side_effect=raced_link):
        try:
            writer._publish_staged_no_replace(partial, partial_inode, stage, stage_inode, known)
        except writer.CatalogPositionPatchError:
            pass
        else:
            raise AssertionError("second-link publication race accepted")
    writer._cleanup(partial, partial_inode, stage, stage_inode, known)
    partial_collision = ((partial / "manifest.json").read_bytes() == b"attacker"
                         and not (partial / "9").exists() and not stage.exists())
    assert partial_collision
    source = root / "race-source"; source.write_bytes(b"abcdefgh")
    staged_volume = root / "race-staged"; victim = root / "race-victim"
    victim.write_bytes(b"DO-NOT-CHANGE")

    class RacingReader:
        def __init__(self) -> None:
            self.stream = source.open("rb"); self.raced = False
        def __enter__(self) -> "RacingReader": return self
        def __exit__(self, *args: object) -> None: self.stream.close()
        def read(self, size: int = -1) -> bytes:
            if not self.raced:
                self.raced = True; staged_volume.unlink(); staged_volume.symlink_to(victim)
            return self.stream.read(size)

    class RacingSource:
        def open(self, mode: str) -> RacingReader:
            if mode != "rb": raise AssertionError(mode)
            return RacingReader()

    with mock.patch.object(writer, "PACK_SIZE", 8), \
            mock.patch.object(writer, "CHUNK_PACK_OFFSET", 2), \
            mock.patch.object(writer, "CHUNK_SPAN_SIZE", 2):
        try: writer._copy_and_patch_owned_volume(RacingSource(), staged_volume, b"XY")  # type: ignore[arg-type]
        except writer.CatalogPositionPatchError as exc:
            descriptor_race = ("pathname changed during copy/patch" in str(exc)
                               and victim.read_bytes() == b"DO-NOT-CHANGE")
        else: descriptor_race = False
    assert descriptor_race
    return {"prepublication_raced_name": prepublication,
            "partial_second_link_collision": partial_collision,
            "staged_volume_symlink_redirection": descriptor_race}


def run(report_path: Path) -> None:
    source_pack = INDEX.parent / "9"
    index_before, pack_before = file_sha(INDEX), file_sha(source_pack)
    assert index_before == writer.INDEX_SHA256 and pack_before == writer.PACK_SHA256
    catalog = writer.load_catalog(CATALOG); row = catalog["targets"][TARGET_ID]
    contract = writer._validate_target_row(row)
    source = writer._validate_source(INDEX, catalog, row)
    with tempfile.TemporaryDirectory(prefix=".nfl-catalog-position-proof-", dir=ROOT) as temporary:
        root = Path(temporary)
        publication = publication_refusals(root)
        noop_path = root / "noop.json"; noop_sha = write_recipe(noop_path, derive_noop(source, contract))
        growth_path = root / "growth.json"; growth_sha = write_recipe(growth_path, deterministic_growth())

        noop_dir = root / "noop"
        noop_manifest = writer.patch(INDEX, CATALOG, noop_path, noop_dir)
        noop = verifier.verify(INDEX, CATALOG, noop_path, noop_dir)
        assert noop_manifest["mode"] == noop["mode"] == "no_op"
        assert noop["output"]["volume_sha256"] == writer.PACK_SHA256
        assert noop["output"]["pack_changed_byte_count"] == 0
        assert noop["compression"]["consumed_bytes"] == 908864
        assert noop["compression"]["scratch_bytes"] == 16

        changed_dir = root / "changed"
        changed_manifest = writer.patch(INDEX, CATALOG, ZERO, changed_dir)
        changed = verifier.verify(INDEX, CATALOG, ZERO, changed_dir)
        assert changed_manifest["mode"] == changed["mode"] == "patched"
        assert changed["output"]["volume_sha256"] == "96c2d8dd4ed4f65df67157ad6a822878bcbd4eefc960135176cd8030c9f9b176"
        assert changed["decoded"]["output_sha256"] == "b2d70bb82f95cffc30a43b82b7263f9d211737fec8ed47b9fd8408c2babfb5f1"
        assert changed["decoded"]["decoded_changed_byte_count"] == 144
        assert changed["compression"] == {"consumed_bytes": 908799,
            "fixed_tail_sha256": writer.OPAQUE_TAIL_SHA256,
            "minimum_alias_scratch_bytes": 66, "padding_bytes": 81,
            "retail_cap": 908864, "retail_observed_scratch_max": 3120,
            "scratch_bytes": 96, "zero_gap_bytes": 65}

        try: writer.patch(INDEX, CATALOG, ZERO, changed_dir)
        except writer.CatalogPositionPatchError: existing_refused = True
        else: existing_refused = False
        assert existing_refused

        growth_dir = root / "growth"
        try: writer.patch(INDEX, CATALOG, growth_path, growth_dir)
        except writer.CatalogPositionPatchError as exc: overflow_refused = "908864-byte" in str(exc)
        else: overflow_refused = False
        assert overflow_refused and not growth_dir.exists()

        invalid = json.loads(ZERO.read_text()); invalid["target_id"] = "nfl2k5/stadium/o3280/c5/s999"
        invalid_path = root / "wrong-target.json"; invalid_path.write_bytes(writer.canonical_json(invalid))
        try: writer.load_recipe(invalid_path, catalog)
        except writer.CatalogPositionPatchError: wrong_target_refused = True
        else: wrong_target_refused = False
        assert wrong_target_refused
        invalid = json.loads(ZERO.read_text()); invalid["positions"].pop()
        invalid_path.write_bytes(writer.canonical_json(invalid))
        try: writer.load_recipe(invalid_path, catalog)
        except writer.CatalogPositionPatchError: wrong_count_refused = True
        else: wrong_count_refused = False
        assert wrong_count_refused
        invalid = json.loads(ZERO.read_text()); invalid["catalog"]["sha256"] = "0" * 64
        invalid_path.write_bytes(writer.canonical_json(invalid))
        try: verifier.load_recipe(invalid_path, verifier.load_catalog(CATALOG))
        except verifier.CatalogPositionVerifyError: wrong_hash_refused = True
        else: wrong_hash_refused = False
        assert wrong_hash_refused

        real = root / "real"; real.mkdir(); linked = root / "linked"; linked.symlink_to(real, target_is_directory=True)
        try: writer.patch(root / "missing", CATALOG, ZERO, linked / "out")
        except writer.CatalogPositionPatchError as exc: symlink_refused = "non-symlink" in str(exc)
        else: symlink_refused = False
        assert symlink_refused

        hardlink = root / "hardlink"; hardlink.mkdir(); os.link(source_pack, hardlink / "9")
        shutil.copyfile(noop_dir / "manifest.json", hardlink / "manifest.json")
        try: verifier.verify(INDEX, CATALOG, noop_path, hardlink)
        except verifier.CatalogPositionVerifyError as exc: hardlink_refused = "inode aliases" in str(exc)
        else: hardlink_refused = False
        assert hardlink_refused

        manifest_path = changed_dir / "manifest.json"; original_manifest = manifest_path.read_bytes()
        mutated = json.loads(original_manifest); mutated["source"]["extra"] = True
        manifest_path.write_bytes(verifier.canonical_json(mutated))
        try: verifier.verify(INDEX, CATALOG, ZERO, changed_dir)
        except verifier.CatalogPositionVerifyError as exc: manifest_refused = "manifest differs" in str(exc)
        else: manifest_refused = False
        manifest_path.write_bytes(original_manifest); assert manifest_refused
        assert verifier.verify(INDEX, CATALOG, ZERO, changed_dir)["mode"] == "patched"

    index_after, pack_after = file_sha(INDEX), file_sha(source_pack)
    assert index_after == index_before and pack_after == pack_before
    report = {"schema": "nfl2k5_catalog_static_position_patch_roundtrip/v2",
        "catalog": {"path": "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json",
            "size": writer.CATALOG_SIZE, "sha256": writer.CATALOG_SHA256,
            "authorized_target_count": 75},
        "source": {"index_sha256_before": index_before, "index_sha256_after": index_after,
            "volume_9_sha256_before": pack_before, "volume_9_sha256_after": pack_after,
            "retail_modified": False},
        "recipe_contract": {"schema": writer.RECIPE_SCHEMA, "json_schema_sha256": file_sha(SCHEMA),
            "nonretail_zero_recipe_sha256": file_sha(ZERO), "derived_noop_recipe_sha256": noop_sha,
            "derived_growth_recipe_sha256": growth_sha, "retail_positions_embedded": False,
            "report_embeds_replacement_positions": False},
        "target": {"target_id": TARGET_ID, "shape_name": "upper_deck", "vertex_count": 12,
            "position_span": [69920, 70064], "position_source_sha256":
                row["position"]["contiguous_decoded_span"]["sha256"],
            "mechanically_rigid_only": True, "runtime_ownership_proved": False},
        "no_op": noop, "controlled_nonretail_all_zero_edit": changed,
        "refusals": {"existing_output_directory": existing_refused,
            "consumed_stream_overflow": overflow_refused, "wrong_target_id": wrong_target_refused,
            "wrong_vertex_count": wrong_count_refused, "wrong_catalog_hash": wrong_hash_refused,
            "symlinked_output_parent": symlink_refused, "hardlink_source_alias": hardlink_refused,
            "mutated_manifest": manifest_refused, "overflow_output_artifact_created": False,
            **publication},
        "claims": {"catalog_backed_same_count_float3_dispatcher_implemented": True,
            "authorized_catalog_targets": 75, "upper_deck_full_copied_volume_roundtrip_proved": True,
            "changed_topology_or_count_proved": False, "runtime_visibility_proved": False,
            "semantic_rigidity_proved": False, "hardware_visibility_proved": False,
            "production_ready": False}}
    report_path.write_bytes(writer.canonical_json(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path); args = parser.parse_args()
    run(args.report)
    print(f"NFL_CATALOG_POSITION_ROUNDTRIP_PASS report={args.report}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
