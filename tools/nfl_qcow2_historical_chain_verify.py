#!/usr/bin/env python3
"""Verify retained QCOW2 evidence without pretending a missing base exists.

The historical NFL 2K5 xemu captures share one deleted base image.  A recursive
``qemu-img check`` can no longer open those chains, but the exact child layers
remain useful historical evidence.  This verifier pins every retained layer in
one selected branch, checks its QCOW2-v3 header and captured backing pathname,
and fails if anything has been substituted at the missing base pathname.

It deliberately does not read guest sectors, reconstruct the base, launch an
emulator, or claim that the historical chain is currently replayable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any


SCHEMA = "nfl2k5_historical_xemu_hdd_chain/v1"
EXPECTED_BOUNDARY = {
    "guest_content_replayable": False,
    "historical_runtime_reexecuted": False,
    "missing_base_reconstructed": False,
    "substitution_allowed": False,
}
NODE_KEYS = {"backing", "captured_path", "id", "retained", "sha256", "size"}
ID_RE = re.compile(r"^[a-z0-9_]+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_SPEC_BYTES = 256 * 1024
HASH_CHUNK = 8 * 1024 * 1024
QCOW_MAGIC = 0x514649FB
QCOW_VIRTUAL_SIZE = 8_589_934_592
QCOW_CLUSTER_BITS = 16


class ChainError(ValueError):
    """A provenance, byte-identity, or QCOW2-header invariant failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ChainError(message)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ChainError(f"non-finite JSON constant: {value}")


def canonical_json(payload: bytes, label: str) -> dict[str, Any]:
    require(0 < len(payload) <= MAX_SPEC_BYTES, f"{label} size is out of range")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ChainError(f"invalid JSON in {label}: {exc}") from exc
    require(isinstance(value, dict), f"{label} root is not an object")
    expected = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    require(payload == expected, f"{label} is not canonical sorted JSON")
    return value


def _require_no_symlink_components(path: Path, *, missing_tail_ok: bool = False) \
        -> None:
    """Reject symlinks in the leaf and every parent without resolving them."""
    require(".." not in path.parts, f"pinned path contains '..': {path}")
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, component in enumerate(parts):
        current /= component
        try:
            info = current.lstat()
        except FileNotFoundError:
            require(missing_tail_ok,
                    f"pinned path component is unavailable: {current}")
            return
        require(not stat.S_ISLNK(info.st_mode),
                f"pinned path component is a symlink: {current}")


def _open_pinned(path: Path, expected_size: int, expected_sha256: str) \
        -> tuple[int, dict[str, int | str]]:
    _require_no_symlink_components(path)
    try:
        before = path.lstat()
    except OSError as exc:
        raise ChainError(f"pinned file is unavailable: {path}: {exc}") from exc
    require(stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"pinned path is not a non-symlink regular file: {path}")
    require(before.st_nlink == 1, f"pinned file is hard-linked: {path}")
    require(before.st_size == expected_size, f"pinned file size differs: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (
            before.st_dev, before.st_ino, before.st_size,
            before.st_mtime_ns, before.st_nlink,
        )
        require(
            (opened.st_dev, opened.st_ino, opened.st_size,
             opened.st_mtime_ns, opened.st_nlink) == identity,
            f"pinned path changed while opening: {path}",
        )
        digest = hashlib.sha256()
        position = 0
        while position < expected_size:
            payload = os.pread(
                descriptor, min(HASH_CHUNK, expected_size - position), position
            )
            require(bool(payload), f"short pinned read: {path}")
            digest.update(payload)
            position += len(payload)
        require(digest.hexdigest() == expected_sha256,
                f"pinned file SHA-256 differs: {path}")
        after = os.fstat(descriptor)
        current = path.lstat()
        require(
            (after.st_dev, after.st_ino, after.st_size,
             after.st_mtime_ns, after.st_nlink) == identity and
            (current.st_dev, current.st_ino, current.st_size,
             current.st_mtime_ns, current.st_nlink) == identity,
            f"pinned file changed while hashing: {path}",
        )
        return descriptor, {
            "device": int(opened.st_dev),
            "inode": int(opened.st_ino),
            "sha256": expected_sha256,
            "size": expected_size,
        }
    except Exception:
        os.close(descriptor)
        raise


def _read_exact(descriptor: int, offset: int, size: int, label: str) -> bytes:
    result = bytearray()
    while len(result) < size:
        payload = os.pread(descriptor, size - len(result), offset + len(result))
        require(bool(payload), f"short {label} read at 0x{offset + len(result):x}")
        result.extend(payload)
    return bytes(result)


def parse_qcow2_header(descriptor: int, file_size: int) -> dict[str, Any]:
    fixed = _read_exact(descriptor, 0, 112, "QCOW2 header")
    (
        magic, version, backing_offset, backing_size, cluster_bits, virtual_size,
        crypt_method, l1_size, l1_offset, refcount_offset,
        refcount_clusters, snapshots, snapshots_offset,
    ) = struct.unpack_from(">IIQIIQIIQQIIQ", fixed, 0)
    incompatible, compatible, _autoclear, refcount_order, header_length = \
        struct.unpack_from(">QQQII", fixed, 72)
    require(magic == QCOW_MAGIC, "QCOW2 magic differs")
    require(version == 3, "QCOW2 version is not 3")
    require(cluster_bits == QCOW_CLUSTER_BITS, "QCOW2 cluster size differs")
    require(virtual_size == QCOW_VIRTUAL_SIZE, "QCOW2 virtual size differs")
    require(crypt_method == 0, "QCOW2 encryption unexpectedly enabled")
    require(l1_size > 0, "QCOW2 L1 table is empty")
    require(refcount_clusters > 0, "QCOW2 refcount table is empty")
    require(snapshots == 0 and snapshots_offset == 0,
            "QCOW2 internal snapshots unexpectedly present")
    require(incompatible & 0x3 == 0, "QCOW2 dirty/corrupt feature bit is set")
    require(compatible & 0x1 == 0, "QCOW2 lazy refcounts unexpectedly enabled")
    require(refcount_order == 4, "QCOW2 refcount width differs")
    require(104 <= header_length <= 112, "QCOW2 header length differs")
    cluster_size = 1 << cluster_bits
    for label, offset in (("L1", l1_offset), ("refcount", refcount_offset)):
        require(offset > 0 and offset % cluster_size == 0 and offset < file_size,
                f"QCOW2 {label} table offset is invalid")
    require(0 <= backing_size <= 4096, "QCOW2 backing pathname size is invalid")
    if backing_size == 0:
        require(backing_offset == 0, "QCOW2 empty backing pathname has an offset")
        backing_path = ""
    else:
        require(header_length <= backing_offset and
                backing_offset + backing_size <= cluster_size and
                backing_offset + backing_size <= file_size,
                "QCOW2 backing pathname extent is invalid")
        backing_payload = _read_exact(
            descriptor, backing_offset, backing_size, "QCOW2 backing pathname"
        )
        try:
            backing_path = backing_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ChainError("QCOW2 backing pathname is not UTF-8") from exc
        require(backing_path and "\x00" not in backing_path,
                "QCOW2 backing pathname is empty or contains NUL")
    return {
        "backing_path": backing_path,
        "cluster_size": cluster_size,
        "dirty": False,
        "format": "qcow2",
        "snapshot_count": 0,
        "virtual_size": virtual_size,
    }


def _resolved(root: Path, captured_path: str) -> Path:
    value = Path(captured_path)
    return value if value.is_absolute() else root / value


def load_spec(spec_path: Path, expected_sha256: str) \
        -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    require(SHA_RE.fullmatch(expected_sha256) is not None,
            "expected spec SHA-256 is invalid")
    supplied = spec_path.lstat()
    require(0 < supplied.st_size <= MAX_SPEC_BYTES, "spec size is out of range")
    descriptor, _pin = _open_pinned(
        spec_path, supplied.st_size, expected_sha256
    )
    try:
        payload = _read_exact(descriptor, 0, supplied.st_size, "spec")
    finally:
        os.close(descriptor)
    value = canonical_json(payload, str(spec_path))
    require(set(value) == {"boundary", "nodes", "schema"},
            "chain spec key set differs")
    require(value["schema"] == SCHEMA, "chain spec schema differs")
    require(value["boundary"] == EXPECTED_BOUNDARY, "chain boundary differs")
    require(isinstance(value["nodes"], list) and value["nodes"],
            "chain spec has no nodes")
    nodes: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    for index, raw in enumerate(value["nodes"]):
        require(isinstance(raw, dict) and set(raw) == NODE_KEYS,
                f"node {index} key set differs")
        node_id = raw["id"]
        require(isinstance(node_id, str) and ID_RE.fullmatch(node_id) is not None,
                f"node {index} id is invalid")
        require(node_id not in nodes, f"duplicate node id: {node_id}")
        path = raw["captured_path"]
        require(isinstance(path, str) and path and "\x00" not in path,
                f"node {node_id} path is invalid")
        require(path not in paths, f"duplicate captured path: {path}")
        paths.add(path)
        require(type(raw["size"]) is int and raw["size"] > 0,
                f"node {node_id} size is invalid")
        require(isinstance(raw["sha256"], str) and
                SHA_RE.fullmatch(raw["sha256"]) is not None,
                f"node {node_id} SHA-256 is invalid")
        require(type(raw["retained"]) is bool,
                f"node {node_id} retained flag is invalid")
        require(raw["backing"] is None or
                (isinstance(raw["backing"], str) and
                 ID_RE.fullmatch(raw["backing"]) is not None),
                f"node {node_id} backing id is invalid")
        nodes[node_id] = raw
    roots = [node for node in nodes.values() if node["backing"] is None]
    require(len(roots) == 1 and roots[0]["retained"] is False,
            "chain must have one explicitly unretained root")
    for node in nodes.values():
        if node["backing"] is not None:
            require(node["backing"] in nodes,
                    f"node {node['id']} backing id is absent")
            require(node["retained"] is True,
                    f"non-root node {node['id']} is not retained")
    return value, nodes


def verify_chain(*, root: Path, spec_path: Path, spec_sha256: str,
                 leaf: str) -> dict[str, Any]:
    _spec, nodes = load_spec(spec_path, spec_sha256)
    require(leaf in nodes, f"unknown leaf: {leaf}")
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    current = nodes[leaf]
    while True:
        node_id = current["id"]
        require(node_id not in visited, "cycle in selected backing chain")
        visited.add(node_id)
        path = _resolved(root, current["captured_path"])
        if current["retained"]:
            descriptor, pin = _open_pinned(
                path, current["size"], current["sha256"]
            )
            try:
                header = parse_qcow2_header(descriptor, current["size"])
            finally:
                os.close(descriptor)
            backing_id = current["backing"]
            require(backing_id is not None, "retained layer unexpectedly has no backing")
            expected_backing = nodes[backing_id]["captured_path"]
            require(header["backing_path"] == expected_backing,
                    f"captured backing pathname differs for {node_id}")
            chain.append({
                "backing": backing_id,
                "header": header,
                "id": node_id,
                "path": current["captured_path"],
                "pin": pin,
                "retained": True,
            })
            current = nodes[backing_id]
            continue

        require(current["backing"] is None, "unretained node is not the root")
        _require_no_symlink_components(path, missing_tail_ok=True)
        if os.path.lexists(path):
            descriptor, pin = _open_pinned(
                path, current["size"], current["sha256"]
            )
            try:
                header = parse_qcow2_header(descriptor, current["size"])
            finally:
                os.close(descriptor)
            require(header["backing_path"] == "",
                    "restored historical base unexpectedly has a backing")
            base_status = "retained_exact"
            base_pin: dict[str, Any] | None = pin
        else:
            base_status = "missing"
            base_pin = None
        chain.append({
            "backing": None,
            "id": node_id,
            "path": current["captured_path"],
            "pin": base_pin,
            "retained": base_status == "retained_exact",
            "sha256": current["sha256"],
            "size": current["size"],
            "status": base_status,
        })
        break

    complete = chain[-1]["status"] == "retained_exact"
    return {
        "base_status": chain[-1]["status"],
        "chain_complete": complete,
        "guest_content_replayable": False,
        "historical_runtime_reexecuted": False,
        "leaf": leaf,
        "layers": chain,
        "missing_base_reconstructed": False,
        "schema": "nfl2k5_historical_xemu_hdd_chain_verify/v1",
        "substitution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--leaf", required=True)
    args = parser.parse_args()
    try:
        result = verify_chain(
            root=args.root,
            spec_path=args.spec,
            spec_sha256=args.spec_sha256,
            leaf=args.leaf,
        )
    except (OSError, ChainError, json.JSONDecodeError) as exc:
        print(f"NFL_QCOW2_HISTORICAL_CHAIN_REFUSED reason={exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
