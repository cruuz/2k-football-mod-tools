#!/usr/bin/env python3
"""Reproduce one shipped NFL 2K5 player celebration ownership witness.

The report joins one exact SMCD archive body to the executable celebration
selector, acquire/controller path, player channel map, gameplay frame path,
player low/high hierarchy builders, portable post-process implementations,
and the canonical low-detail player skin.  It intentionally withholds an
animated glTF while concrete runtime external-root and high-skin ownership
remain unproved.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


TARGET_NAME = "ANM_CELEBRATE_USER_34"
TARGET_OUTER_INDEX = 3092
TARGET_OUTER_ID = 0xDADDB151
TARGET_CHUNK_INDEX = 163
TARGET_CHUNK_OFFSET = 0x003F5A80
TARGET_SELECTOR_INDEX = 2
SELECTOR_BASE = 0x0050CFC8
SELECTOR_COUNT = 37
SELECTOR_STRIDE = 12
SELECTOR_END = SELECTOR_BASE + SELECTOR_COUNT * SELECTOR_STRIDE
NAMESPACE_VA = 0x00E8470C
TARGET_NAME_VA = 0x00E8480C
CHANNEL_MAP_VA = 0x0051CD70
WRAPPER = struct.Struct("<4s7I")
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"


# These are exact function bodies where the saved Ghidra boundary is known,
# and explicitly named bounded evidence regions otherwise.
EXPECTED_XBE_RANGES = [
    ("smcd_prefetch", 0x001685B0, 0x001685D5,
     "474e2db5aa9abe9d469d53a089d67282513506c82902215f87fed2e19bfce2a9"),
    ("smcd_acquire", 0x001685E0, 0x00168653,
     "836524bbafd3ace2fe7075aa92f8e663c77650c0fe06c3350313020949a7b2cb"),
    ("celebration_selector", 0x001B6B50, 0x001B6C45,
     "7a8a6aee666fc177ee58353f56fb8040cd3f2bb9ad4ea6a810f5925eb45d64de"),
    ("celebration_acquire_poll", 0x001B6C70, 0x001B6C91,
     "b25257d3f6f63895b4069ffab6f86fb487994f3cba13cd347ede7f537e45fa68"),
    ("celebration_acquire_and_play", 0x001B7460, 0x001B791A,
     "147ea782d60b00d3d0f5dfaac90f338400ebf1668a7e8d6769f8d729f0db63d9"),
    ("celebration_player_pool_slice", 0x001B7B31, 0x001B7B4F,
     "78c0c07dd20be356496c3416059277ff1f7e3e242025191f12f0cb4f7564292f"),
    ("state_0x002ddb10_missing_boundary", 0x002DDB10, 0x002DDCB9,
     "5b47e65e5041f49bc4876ff76324223ce08748d95952ed1f9c69677dd72dcc60"),
    ("celebration_state_dispatch", 0x002DE9C0, 0x002DE9FE,
     "24c4fc66406e14292bfe4dcb859a6d072156a559f1966f5a5a518c59ed9ac3a1"),
    ("player_controller_initializer", 0x00217E10, 0x00217EAA,
     "af2e563d0ada69f608f78bc44b329b8327705f8ca76d7de08748b78046c9b460"),
    ("actor_controller_update", 0x00218010, 0x00218087,
     "8474b3a8d45f82c71bc18297c8845cdc55182129dfda610f0a9f43d3265b456b"),
    ("motion_pool_update", 0x002180D0, 0x00218144,
     "0ba19f84eb2e492880c43ae6957818a8d095b520390e3e56fa5aab1c433f7bde"),
    ("trajectory_callback", 0x002CC570, 0x002CC622,
     "5fa00a474133d7fb286cfe373d104c30d2b641cbbad2a4aed740041ab834c344"),
    ("controller_install_motion", 0x002D6B70, 0x002D6CC1,
     "eeee29fe5eeec0c81254fd2e6d9271e33d484e3c5046e26d334a65ba691cb5d0"),
    ("controller_update_dispatch", 0x0031BEB0, 0x0031C0C2,
     "b2d22a7d51a0de73e6d7dd7e749db9fb6beb7e1ed86e5ded9ac30c0ddb93b5f3"),
    ("controller_transition", 0x0031C180, 0x0031C473,
     "f9183d791868eff01a42b152a729865f296d262195e1b4150bb8ccb25dbf0ef3"),
    ("gameplay_frame", 0x0011A7C0, 0x0011A8E7,
     "6dbbc1be36593c0d3d1b225c6064a816ab51f22d3dda98fb4c2c3c0ba194427d"),
    ("player_pose_and_hierarchy", 0x0028E360, 0x0028EA08,
     "ccdce899eb7a148a690540065d00ac016c19b14e806bdd915c5bedcc82a247b0"),
    ("late_neck_head_postprocess", 0x001DFAA0, 0x001DFB4D,
     "5a0c9cc97ab2d53e9f1b5feaf4d6c58770498fd3101fd44daa8ef3773463b62e"),
    ("player_lo_body_loader_slice", 0x000905F0, 0x00090680,
     "a5769f7de396c2b65d8901c7cc378483b0a941dbede7aac7218f1707c4bc8384"),
    ("player_hi_body_loader_slice", 0x00090FD0, 0x00091040,
     "0761ad5a3f4b3af4c1970ed820a23585625b4e28b82ac007a47f95166c39c69d"),
    ("external_root_matrix_slice", 0x00037EB0, 0x00037F40,
     "bab7e17166cf9b31541feaf3512db059f78fa581ac5dd8d96fc2b01434b886df"),
    ("player_twist_dispatch", 0x00091890, 0x000918AA,
     "b4e5af75639cfb7ee5e2717e77d0617a9e355aa471b56473c0c93c7d2b9e9b81"),
    ("player_root_basis_scale", 0x000918D0, 0x000918FC,
     "ec5140682b6ffe1d75f2043418e70d6a5a3907aa3f95ff7aa2260743fd3c7331"),
    ("player_local_postprocess", 0x00092140, 0x000937F6,
     "27d5220ca131c3f41d5c40e8a715fa6386d7d5fb50c1618ff0abf3ac7dffcacb"),
    ("player_hierarchy_wrapper", 0x00093800, 0x00093849,
     "cf008441aa4b2bfb1308df4c4ef6df410bbd2dc3d4fcc954b6ec95ea813ef4fd"),
    ("player_current_postprocess", 0x00093850, 0x00093B39,
     "e8328476d6c3282ed48f9729f790068334a846c41e7dfd6d1043e5d7087d8d5f"),
    ("secondary_player_shape_lookup", 0x0002EB70, 0x0002EB7E,
     "f34c13f52bc007a2c1e6647e9afab8fec664216d606b6b0b07af38aa11db36fe"),
    ("hierarchy_expander", 0x000233C0, 0x00023495,
     "d6db4ec7b581ed531f708d4ac2b9236b151b823aaf9e6828f58f0e4e584dbeda"),
    ("skin_palette_builder", 0x00022C00, 0x00022ECA,
     "55e7b14873c75c21ffaa53456246b515bf6795c6ac20e2b5414a5d668330f053"),
    ("render_object_dispatch", 0x00021860, 0x000218C3,
     "4b51b577a3dedc1b8aebb5d89bc1983c054d913728acefd5514edf291c9c2566"),
    ("render_shape", 0x000243D0, 0x00024978,
     "8ee29a692f1a36ecbca9d17828f71d8e78e6001271b2a805bb6c15387fba59fd"),
    ("quaternion_array_to_matrix", 0x003CA3D0, 0x003CA4D2,
     "e732a761202f934b5583ad3845a6d8793e7895d654e1567ff4d03352f7a73142"),
    ("selector_table", SELECTOR_BASE, SELECTOR_END,
     "111d8b26c0ad4c4cb5276a837017333c0a660d903ff5fc3f68fb4cb1d79b774d"),
    ("player_channel_map", CHANNEL_MAP_VA, CHANNEL_MAP_VA + 50,
     "9d1b0670498bde0a18ee06d0270c1a3e54793638f3671b050b4168636240a0d3"),
]


class OwnershipError(ValueError):
    """Raised when a shipped input differs from this ownership contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": file_sha256(path)}


def load_json(path: Path, schema: str) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != schema:
        raise OwnershipError(f"{path}: expected schema {schema!r}")
    return document


class XbeView:
    def __init__(self, path: Path, header_path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        actual = hashlib.md5(self.data).hexdigest()
        if actual != EXPECTED_XBE_MD5:
            raise OwnershipError(f"unexpected XBE MD5 {actual}")

    def file_offset(self, va: int, size: int = 1) -> int:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                return int(section["raw_address"]) + va - start
        raise OwnershipError(f"VA 0x{va:08x}+0x{size:x} is not file-backed")

    def at(self, va: int, size: int) -> bytes:
        offset = self.file_offset(va, size)
        result = self.data[offset:offset + size]
        if len(result) != size:
            raise OwnershipError(f"short XBE read at 0x{va:08x}")
        return result

    def utf16z(self, va: int) -> str:
        offset = self.file_offset(va, 2)
        units = bytearray()
        for _ in range(512):
            unit = self.data[offset:offset + 2]
            if len(unit) != 2:
                break
            offset += 2
            if unit == b"\0\0":
                return units.decode("utf-16le")
            units.extend(unit)
        raise OwnershipError(f"unterminated UTF-16 string at 0x{va:08x}")


def parse_sampler_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))


def single_resource(resources_by_name: dict[str, list[dict[str, object]]],
                    name: str) -> dict[str, object]:
    matches = resources_by_name.get(name, [])
    if len(matches) != 1:
        raise OwnershipError(f"{name!r}: expected one SMCD, found {len(matches)}")
    return matches[0]


def parse_body(body: bytes) -> dict[str, object]:
    if len(body) != 9456 or body[:12] != bytes(12) or body[12:16] != b"SMCD":
        raise OwnershipError("target SMCD strict prefix/length differs")
    name_stored, root_stored = struct.unpack_from("<II", body, 0x10)
    name_offset = 0x10 + name_stored - 1
    root_offset = 0x14 + root_stored - 1
    cursor = name_offset
    units = bytearray()
    while cursor + 2 <= len(body):
        unit = body[cursor:cursor + 2]
        cursor += 2
        if unit == b"\0\0":
            break
        units.extend(unit)
    else:
        raise OwnershipError("unterminated target SMCD name")
    name = units.decode("utf-16le")
    words = struct.unpack_from("<13I", body, root_offset)
    pointer_fields = (root_offset + 36, root_offset + 40, root_offset + 44)
    pointer_targets = tuple(field + words[9 + i] - 1 for i, field in enumerate(pointer_fields))
    if pointer_targets != (888, 144, 128):
        raise OwnershipError(f"target root pointers differ: {pointer_targets}")
    word00, word04, runtime_mask, word0c = words[:4]
    flags = word04 & 0xFF
    packed = word00 & 0xFF
    frames = word00 >> 16
    rate = word0c & 0xFF
    quaternion_bytes = packed * frames * 4
    quaternion_region = body[888:]
    trajectory_region = body[144:888]
    event_region = body[128:144]
    if len(quaternion_region) < quaternion_bytes:
        raise OwnershipError("target quaternion region is truncated")
    if event_region[-4:] != b"\xff\xff\xff\xff":
        raise OwnershipError("target event sentinel differs")
    vector = struct.unpack_from("<3f", body, root_offset + 24)
    return {
        "name": name,
        "name_offset": name_offset,
        "root_offset": root_offset,
        "root_header_words": [f"0x{word:08x}" for word in words],
        "packed_quaternion_dwords_per_frame": packed,
        "opaque_header_byte_01": (word00 >> 8) & 0xFF,
        "frame_count": frames,
        "flags": flags,
        "opaque_word04_bits_08_31": f"0x{word04 >> 8:06x}",
        "runtime_mask_word08": f"0x{runtime_mask:08x}",
        "sample_rate_hz": rate,
        "duration_raw": f"0x{words[5]:08x}",
        "duration_seconds": struct.unpack_from("<f", body, root_offset + 20)[0],
        "opaque_vector_raw": [f"0x{word:08x}" for word in words[6:9]],
        "opaque_vector": list(vector),
        "pointer_targets": list(pointer_targets),
        "event_offset": 128,
        "event_bytes": len(event_region),
        "event_count": 3,
        "event_sha256": sha256(event_region),
        "trajectory_offset": 144,
        "trajectory_stride": 8,
        "trajectory_bytes": len(trajectory_region),
        "trajectory_sha256": sha256(trajectory_region),
        "quaternion_offset": 888,
        "quaternion_bytes": quaternion_bytes,
        "quaternion_region_bytes": len(quaternion_region),
        "quaternion_region_sha256": sha256(quaternion_region),
        "quaternion_slack_bytes": len(quaternion_region) - quaternion_bytes,
        "quaternion_slack_sha256": sha256(quaternion_region[quaternion_bytes:]),
        "looping": bool(flags & 1),
        "mirrored": bool(flags & 4),
        "trajectory_is_eight_byte": not bool(flags & 8),
    }


def selector_rows(xbe: XbeView,
                  resources_by_name: dict[str, list[dict[str, object]]]
                  ) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(SELECTOR_COUNT):
        row_va = SELECTOR_BASE + index * SELECTOR_STRIDE
        left, right, opaque = struct.unpack("<III", xbe.at(row_va, 12))
        row: dict[str, object] = {
            "selector_index": index,
            "row_va": f"0x{row_va:08x}",
            "row_file_offset": xbe.file_offset(row_va, 12),
            "left_pointer_field_va": f"0x{row_va:08x}",
            "right_pointer_field_va": f"0x{row_va + 4:08x}",
            "opaque_u32": f"0x{opaque:08x}",
            "opaque_s32": struct.unpack("<i", struct.pack("<I", opaque))[0],
        }
        for side, pointer in (("left", left), ("right", right)):
            row[f"{side}_name_string_va"] = "" if not pointer else f"0x{pointer:08x}"
            row[f"{side}_name"] = ""
            row[f"{side}_match_count"] = 0
            row[f"{side}_outer_index"] = ""
            row[f"{side}_chunk_index"] = ""
            row[f"{side}_chunk_offset"] = ""
            row[f"{side}_decoded_sha256"] = ""
            if not pointer:
                continue
            name = xbe.utf16z(pointer)
            resource = single_resource(resources_by_name, name)
            row[f"{side}_name"] = name
            row[f"{side}_match_count"] = 1
            row[f"{side}_outer_index"] = int(resource["outer_index"])
            row[f"{side}_chunk_index"] = int(resource["chunk_index"])
            row[f"{side}_chunk_offset"] = int(resource["chunk_offset"])
            row[f"{side}_decoded_sha256"] = str(resource["decoded_sha256"])
        rows.append(row)
    return rows


def build_path_rows() -> list[dict[str, object]]:
    return [
        {"step": 1, "source": "outer3092/chunk163", "target": "0x00e8480c",
         "instruction_va": "0x0050cfe4", "evidence": "selector row 2 right pointer equals the unique archived SMCD name VA",
         "meaning": "when selector result is 2, the null left slot forces this exact shipped clip", "confidence": "exact_static_conditional_on_index_2"},
        {"step": 2, "source": "0x002de9c0", "target": "0x001b6b50",
         "instruction_va": "0x002de9d1/0x002de9df/0x002de9e8", "evidence": "dispatch accepts state callback 0x002de170 or 0x002ddb10 and calls celebration selection",
         "meaning": "the selector belongs to the gameplay actor-state path", "confidence": "instruction_exact"},
        {"step": 3, "source": "0x001b6b50", "target": "0x0050cfc8 row[index]",
         "instruction_va": "0x001b6bd7..0x001b6be3", "evidence": "result is multiplied by 12 and indexed into the 37-row table",
         "meaning": "dynamic selector result chooses one table row", "confidence": "instruction_exact_index_2_producer_unproved"},
        {"step": 4, "source": "row 2", "target": "CELEBRATE/ANM_CELEBRATE_USER_34",
         "instruction_va": "0x001b6bea..0x001b6c31", "evidence": "left is null, +4 name is stored at 0x00be50c4, namespace literal is loaded, and SMCD prefetch is called",
         "meaning": "row 2 has no side ambiguity and is prefetched as CELEBRATE SMCD", "confidence": "instruction_exact_conditional_on_index_2"},
        {"step": 5, "source": "0x002ddb10 raw state", "target": "0x001b6c70",
         "instruction_va": "0x002ddb3f", "evidence": "missing-boundary handler polls deferred acquire readiness",
         "meaning": "gameplay state waits for selected CELEBRATE resource", "confidence": "instruction_exact_boundary_missing"},
        {"step": 6, "source": "0x001b6c70", "target": "0x001685e0",
         "instruction_va": "0x001b6c70..0x001b6c7f", "evidence": "loads selected global as EDX and literal CELEBRATE as ECX before acquire",
         "meaning": "the selected name is acquired under the exact namespace", "confidence": "instruction_exact"},
        {"step": 7, "source": "0x002ddb10 raw state", "target": "0x001b7460",
         "instruction_va": "0x002ddb7f..0x002ddb8a", "evidence": "passes actor, state+0xa0 mode, state+0xa4, and zero",
         "meaning": "mode 1 enters selected-name acquire/play branch", "confidence": "instruction_exact_mode_value_for_concrete_event_unproved"},
        {"step": 8, "source": "0x001b7460", "target": "0x002d6b70",
         "instruction_va": "0x001b74db/0x001b7511/0x001b751c/0x001b78cb..0x001b78de", "evidence": "mode 1 acquires selected name then passes returned root with [1,0,1,1,speed,0,0]",
         "meaning": "selected root reaches gameplay controller setup", "confidence": "instruction_exact_conditional_on_mode_1"},
        {"step": 9, "source": "0x002d6b70", "target": "0x0031c180/controller+0x74",
         "instruction_va": "0x002d6c13", "evidence": "controller install calls transition with acquired root",
         "meaning": "root becomes enabled controller motion", "confidence": "instruction_exact"},
        {"step": 10, "source": "0x00e60268 player pool", "target": "0x0051cd70/0x00091890",
         "instruction_va": "0x00217e12/0x00217e69/0x00217e77", "evidence": "initializer traverses player pool and installs 23-channel map plus wrist completion callback",
         "meaning": "clip width binds to player lo_body 25-logical-channel family", "confidence": "instruction_exact_family"},
        {"step": 11, "source": "0x0011a7c0 frame", "target": "0x002180d0 -> 0x0028e360 -> 0x001dfaa0",
         "instruction_va": "0x0011a89d/0x0011a8a2/0x0011a8b6", "evidence": "ordered calls update controller/trajectory, build pose/hierarchy, then finish neck/head",
         "meaning": "one exact gameplay frame owns the complete player pose pipeline", "confidence": "instruction_exact"},
        {"step": 12, "source": "controller+0x34 sampled poses", "target": "actor+0x04 low matrices",
         "instruction_va": "0x0028e91a..0x0028e971", "evidence": "25 quaternion slots are converted through 0x003ca3d0 thunk",
         "meaning": "sampled player local pose enters matrix storage", "confidence": "instruction_exact"},
        {"step": 13, "source": "actor+0x18 live transform", "target": "external root matrix",
         "instruction_va": "0x0028e4c2/0x0028e908..0x0028e92c", "evidence": "heading builds root rotation and +0x30/+0x34/+0x38 add live translation",
         "meaning": "raw clip trajectory is integrated into live state, not flattened as a clip-local root", "confidence": "instruction_exact_runtime_initial_state_unproved"},
        {"step": 14, "source": "low local matrices + external root", "target": "low/high current hierarchies",
         "instruction_va": "0x0028e98c -> 0x00093800", "evidence": "0x00092140 builds 62 high locals and 0x000233c0 expands high and low against the same external root",
         "meaning": "now-portable high local graph and hierarchy are in the gameplay path", "confidence": "instruction_exact_and_value_validated"},
        {"step": 15, "source": "player current matrices", "target": "all 25 logical channels",
         "instruction_va": "0x0028e99d/0x001dfadf", "evidence": "masks 0x01ffe7ff and 0x00001800 are complementary",
         "meaning": "now-portable 0x00093850 covers body then neck/head in frame order", "confidence": "instruction_exact_and_value_validated"},
        {"step": 16, "source": "low/high current matrices", "target": "T(-bind) * current palettes",
         "instruction_va": "0x00021860 -> 0x000243d0 -> 0x00022c00", "evidence": "render path consumes expanded current matrices and bind translations",
         "meaning": "canonical mapped lo_body skin is a render-compatible player witness", "confidence": "instruction_exact_low_skin_exact_high_skin_unproved"},
    ]


def find_one(items: Iterable[dict[str, object]], **wanted: object) -> dict[str, object]:
    matches = [item for item in items if all(item.get(k) == v for k, v in wanted.items())]
    if len(matches) != 1:
        raise OwnershipError(f"expected one record matching {wanted}, found {len(matches)}")
    return matches[0]


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    motion = load_json(args.motion_inventory, "nfl2k5_motion_inventory/v1")
    sampler_report = load_json(args.sampler_report, "nfl2k5_motion_sampler_inventory/v1")
    pose = load_json(args.pose_report, "nfl2k5_pose_matrix_apply/v2")
    pools = load_json(args.pool_report, "nfl2k5_motion_object_pools/v1")
    bone = load_json(args.bone_report, "nfl2k5_bone_binding/v1")
    player_pose = load_json(args.player_pose_report, "nfl2k5_player_pose_native/v1")
    native_92140 = load_json(args.player_92140_report, "nfl2k5_player_92140_native/v1")
    post = load_json(args.player_postprocess_report, "nfl2k5_player_postprocess/v1")
    root = load_json(args.root_report, "nfl2k5_referee_root_trajectory/v1")
    scne = load_json(args.scne_report, "nfl2k5_scne_inventory/v1")
    raw_skin = load_json(args.raw_skin_report, "nfl2k5_raw_skin_gltf_manifest/v2")
    meter_skin = load_json(args.meter_skin_report, "nfl2k5_meter_skin_gltf_manifest/v1")
    del sampler_report

    smcd = [item for item in motion["resources"] if item["kind"] == "SMCD"]
    by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in smcd:
        by_name[str(item["name"])].append(item)
    target = single_resource(by_name, TARGET_NAME)
    identity = (int(target["outer_index"]), int(str(target["outer_id"]), 16),
                int(target["chunk_index"]), int(target["chunk_offset"]))
    if identity != (TARGET_OUTER_INDEX, TARGET_OUTER_ID, TARGET_CHUNK_INDEX,
                    TARGET_CHUNK_OFFSET):
        raise OwnershipError(f"target identity differs: {identity}")

    archive = nfl_outer.parse_archive(args.index)
    entry = archive.entries[TARGET_OUTER_INDEX]
    if entry.name_id != TARGET_OUTER_ID or entry.size != 4228352:
        raise OwnershipError("outer 3092 ID/size differs")
    wrapper_bytes = nfl_outer.read_entry_range(archive, entry, TARGET_CHUNK_OFFSET,
                                                WRAPPER.size)
    wrapper = WRAPPER.unpack(wrapper_bytes)
    if not (wrapper[0] == b"SMCD" and wrapper[1] == wrapper[2] == 9456
            and all(word == 0 for word in wrapper[3:])):
        raise OwnershipError(f"target wrapper differs: {wrapper}")
    body = nfl_outer.read_entry_range(archive, entry,
                                      TARGET_CHUNK_OFFSET + WRAPPER.size, 9456)
    if sha256(body) != "a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52":
        raise OwnershipError("target body hash differs")
    if sha256(body) != target["decoded_sha256"]:
        raise OwnershipError("target body differs from canonical inventory")
    zero_before = int(target["zero_padding_before"])
    padding = nfl_outer.read_entry_range(archive, entry,
                                         TARGET_CHUNK_OFFSET - zero_before, zero_before)
    if any(padding):
        raise OwnershipError("target zero_padding_before contains nonzero bytes")
    parsed = parse_body(body)
    if parsed["name"] != TARGET_NAME:
        raise OwnershipError("target body name differs")

    sampler_matches = [row for row in parse_sampler_rows(args.sampler_tsv)
                       if row["name"] == TARGET_NAME
                       and int(row["outer_index"]) == TARGET_OUTER_INDEX
                       and int(row["chunk_index"]) == TARGET_CHUNK_INDEX]
    if len(sampler_matches) != 1:
        raise OwnershipError(f"expected one sampler row, found {len(sampler_matches)}")
    sampler = sampler_matches[0]
    sampler_contract = {
        "duration_coordinate": float(sampler["duration_coordinate"]),
        "last_sample_coordinate": int(sampler["last_sample_coordinate"]),
        "duration_gap": float(sampler["duration_gap"]),
        "events_after_clip_duration": int(sampler["events_after_clip_duration"]),
    }
    checks = {
        "packed_quaternion_dwords_per_frame": int(sampler["packed_quaternion_dwords_per_frame"]),
        "frame_count": int(sampler["frame_count"]),
        "flags": int(sampler["flags"], 16),
        "sample_rate_hz": int(sampler["sample_rate"]),
        "quaternion_bytes": int(sampler["quaternion_bytes"]),
        "quaternion_region_bytes": int(sampler["quaternion_region_length"]),
        "quaternion_slack_bytes": int(sampler["quaternion_slack_length"]),
        "trajectory_stride": int(sampler["trajectory_stride"]),
        "trajectory_bytes": int(sampler["trajectory_bytes"]),
        "event_count": int(sampler["event_count"]),
    }
    for key, expected in checks.items():
        if parsed[key] != expected:
            raise OwnershipError(f"sampler/body field {key} differs")
    if sampler["quaternion_slack_sha256"] != parsed["quaternion_slack_sha256"]:
        raise OwnershipError("quaternion slack hash differs")

    xbe = XbeView(args.xbe, args.xbe_header)
    ranges: list[dict[str, object]] = []
    for name, start, end, expected in EXPECTED_XBE_RANGES:
        actual = sha256(xbe.at(start, end - start))
        if actual != expected:
            raise OwnershipError(f"XBE range {name} differs: {actual}")
        ranges.append({"name": name, "start": f"0x{start:08x}",
                       "end_exclusive": f"0x{end:08x}", "size": end - start,
                       "sha256": actual})

    selectors = selector_rows(xbe, by_name)
    selected = selectors[TARGET_SELECTOR_INDEX]
    if not (selected["left_name"] == ""
            and selected["right_name"] == TARGET_NAME
            and selected["right_name_string_va"] == "0x00e8480c"
            and selected["opaque_s32"] == 21
            and selected["right_outer_index"] == TARGET_OUTER_INDEX
            and selected["right_chunk_index"] == TARGET_CHUNK_INDEX):
        raise OwnershipError("selector row 2 differs")
    names = [str(row[f"{side}_name"]) for row in selectors
             for side in ("left", "right") if row[f"{side}_name"]]
    if len(names) != 70 or len(set(names)) != 70:
        raise OwnershipError("selector corpus cardinality differs")
    if any(int(row[f"{side}_outer_index"]) != TARGET_OUTER_INDEX
           for row in selectors for side in ("left", "right")
           if row[f"{side}_name"]):
        raise OwnershipError("selector corpus escapes outer 3092")
    if xbe.utf16z(NAMESPACE_VA) != "CELEBRATE" or xbe.utf16z(TARGET_NAME_VA) != TARGET_NAME:
        raise OwnershipError("CELEBRATE/target executable strings differ")
    if xbe.utf16z(0x00E63E60) != "lo_body" or xbe.utf16z(0x00E63E70) != "hi_body":
        raise OwnershipError("player scene strings differ")

    map_contract = pose["installed_channel_maps"]["0x0051cd70"]
    if map_contract["enabled_channel_count"] != 23 or map_contract["disabled_logical_channels"] != [16, 21]:
        raise OwnershipError("player channel-map contract differs")
    player_pool = find_one(pools["motion_mapped_pools"], head_global_va="0x00e60268")
    if player_pool["maximum_count"] != 22 or player_pool["channel_map_va"] != "0x0051cd70":
        raise OwnershipError("player pool contract differs")
    player_family = find_one(bone["skeleton_families"], name="player_lo_body")
    if len(player_family["bindings"]) != 25:
        raise OwnershipError("player bone-binding count differs")
    if player_pose["validation"]["maximum_lane_error"] != 0.0:
        raise OwnershipError("portable player pose validator is not exact")
    validation_92140 = native_92140["validation"]
    if validation_92140["calls_observed_per_case"] != 127 or validation_92140["bit_identity_claimed"] is not False:
        raise OwnershipError("0x00092140 native validation contract differs")
    if post["counts"]["low_transforms"] != 25 or post["counts"]["high_transforms"] != 62:
        raise OwnershipError("player postprocess transform counts differ")
    callers = post["function_0x00093850"]["direct_callers"]
    if find_one(callers, callsite="0x0028e99d")["mask"] != "0x01ffe7ff":
        raise OwnershipError("main current-postprocess mask differs")
    if find_one(callers, callsite="0x001dfadf")["mask"] != "0x00001800":
        raise OwnershipError("neck/head current-postprocess mask differs")
    if not any(step["function_va"] == "0x002cc570" for step in root["gameplay_instruction_chain"]):
        raise OwnershipError("trajectory report lacks live actor transform callback")

    lo_scene = find_one(scne["scenes"], name="lo_body")
    hi_scene = find_one(scne["scenes"], name="hi_body")
    if (lo_scene["decoded_sha256"] != "2a89df4b2e83dee4c7937194e5cd885c4b3662720bf976d8440ab5c3fb423e56"
            or hi_scene["decoded_sha256"] != "43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b"):
        raise OwnershipError("player SCNE identities differ")
    raw_output = next((item for item in raw_skin["outputs"]
                       if item["output_gltf"] == "0003_0113_lo_body_raw_skin.gltf"), None)
    meter_output = next((item for item in meter_skin["outputs"]
                         if item["output_gltf"] == "0003_0113_lo_body_meter_skin.gltf"), None)
    if raw_output is None or meter_output is None:
        raise OwnershipError("canonical low player skin records are missing")
    gltf_path = args.meter_skin_dir / str(meter_output["output_gltf"])
    bin_path = args.meter_skin_dir / str(meter_output["output_bin"])
    if file_sha256(gltf_path) != meter_output["output_gltf_sha256"]:
        raise OwnershipError("canonical low player glTF hash differs")
    if file_sha256(bin_path) != meter_output["output_bin_sha256"]:
        raise OwnershipError("canonical low player BIN hash differs")

    path_rows = build_path_rows()
    report = {
        "schema": "nfl2k5_player_clip_ownership/v1",
        "source_index": str(args.index),
        "executable": {"path": str(args.xbe), "md5": EXPECTED_XBE_MD5,
                       "sha256": file_sha256(args.xbe), "ranges": ranges},
        "selected_clip": {
            "name": TARGET_NAME, "outer_index": TARGET_OUTER_INDEX,
            "outer_id": f"0x{TARGET_OUTER_ID:08x}", "outer_size": entry.size,
            "chunk_index": TARGET_CHUNK_INDEX, "chunk_offset": TARGET_CHUNK_OFFSET,
            "wrapper_size": WRAPPER.size, "stored_size": len(body),
            "decoded_size": len(body), "decoded_sha256": sha256(body),
            "zero_padding_before": zero_before,
            **parsed, **sampler_contract,
            "selector_index": TARGET_SELECTOR_INDEX,
            "selector_row_va": "0x0050cfe0",
            "selector_left_pointer_is_null": True,
            "selector_right_pointer_field_va": "0x0050cfe4",
            "selector_right_name_string_va": "0x00e8480c",
            "selector_opaque_s32": 21,
            "exact_inventory_match_count": 1,
        },
        "selector_table": {
            "base_va": f"0x{SELECTOR_BASE:08x}", "end_exclusive_va": f"0x{SELECTOR_END:08x}",
            "row_count": SELECTOR_COUNT, "row_stride": SELECTOR_STRIDE,
            "left_pointer_offset": 0, "right_pointer_offset": 4, "opaque_word_offset": 8,
            "nonempty_name_count": len(names), "unique_name_count": len(set(names)),
            "reused_name_count": sum(count > 1 for count in Counter(names).values()),
            "all_nonempty_names_have_one_exact_smcd_match": True,
            "all_nonempty_names_resolve_to_outer_3092": True,
            "selected_row_side_is_forced_right_because_left_is_null": True,
            "dynamic_index_2_producer_proved": False,
        },
        "runtime_ownership": {
            "namespace_name": "CELEBRATE", "namespace_string_va": "0x00e8470c",
            "smcd_fourcc_immediate": "0x44434d53",
            "selector_function_va": "0x001b6b50", "selected_name_global_va": "0x00be50c4",
            "selected_opaque_global_va": "0x00be50cc", "prefetch_va": "0x001685b0",
            "acquire_poll_va": "0x001b6c70", "acquire_va": "0x001685e0",
            "acquire_and_play_va": "0x001b7460", "controller_install_va": "0x002d6b70",
            "controller_transition_va": "0x0031c180", "active_motion_slot": "controller+0x74",
            "player_pool_head_va": "0x00e60268", "player_pool_max_count": 22,
            "player_controller_initializer_va": "0x00217e10", "channel_map_va": "0x0051cd70",
            "enabled_packed_channels": 23, "logical_channels": 25,
            "disabled_callback_completed_channels": [16, 21], "completion_callback_va": "0x00091890",
            "selector_index_2_path_is_conditional": True,
            "concrete_state_plus_a0_equals_one_proved": False,
        },
        "frame_and_external_root": {
            "frame_function_va": "0x0011a7c0",
            "ordered_calls": ["0x002180d0", "0x0028ecf0 -> 0x0028e360", "0x001dfaa0"],
            "controller_pose_source": "controller+0x34", "low_matrix_array": "actor+0x04",
            "player_context": "actor+0x3c", "live_external_transform": "actor+0x18",
            "trajectory_callback_va": "0x002cc570",
            "external_root_builder_va": "0x00037eb0",
            "external_root_heading": "(actor+0x18)+0x50",
            "external_root_translation": ["(actor+0x18)+0x30", "(actor+0x18)+0x34", "(actor+0x18)+0x38"],
            "root_policy": "integrate serialized trajectory into live actor+0x18, then build one external root used by both low and high hierarchies",
            "raw_clip_root_may_be_flattened_directly": False,
            "concrete_initial_actor_transform_proved": False,
        },
        "render_target_join": {
            "conditional_on_selector_index_2_and_playback_mode_1": True,
            "lo_body_LO_res_reached": True,
            "lo_body_evidence": "0x0028e360 converts 25 controller slots into actor+0x04, then 0x00093800 expands the low array with the external root",
            "hi_body_HI_res_matrix_path_reached": True,
            "hi_body_evidence": "0x00093800 always calls 0x00092140, selects the high shape through 0x0002eb70, and expands high locals at low+0x640",
            "hi_body_exact_skin_attachment_reached": False,
            "local_postprocess_0x00092140_runs": True,
            "hierarchy_wrapper_0x00093800_runs": True,
            "current_postprocess_0x00093850_runs": True,
            "current_postprocess_calls": [
                {"callsite": "0x0028e99d", "context_source": "ECX = *(actor+0x3c)",
                 "mask_source": "EDX immediate 0x01ffe7ff", "matrix_source": "stack = actor+0x04",
                 "covered_channels": "all except neck/head (logical 11/12)"},
                {"callsite": "0x001dfadf", "context_source": "ECX = *(actor+0x3c)",
                 "mask_source": "EDX immediate 0x00001800", "matrix_source": "stack = actor+0x04",
                 "covered_channels": "neck/head (logical 11/12)"},
            ],
            "current_postprocess_live_inputs": {
                "profile": "(*(actor+0x3c)+0x18 >> 3) & 3",
                "scalar": "clamp(float(u8(*(actor+0x3c)+0x2a) + 150), 150, 450)",
                "final_head_gate": "global u32 0x00e601f0 != 0 and mask bit 12",
                "skel_object_pointer": "global 0x00b65b78",
                "high_to_low_schedule": "u8[62] at 0x004ef898",
                "concrete_profile_and_scalar_values_proved": False,
            },
        },
        "portable_player_pipeline": {
            "pose_sampler_validation": player_pose["validation"],
            "local_postprocess_va": "0x00092140", "low_matrix_count": 25,
            "high_matrix_count": 62, "ordered_helper_calls": 127,
            "local_postprocess_validation": validation_92140,
            "hierarchy_wrapper_va": "0x00093800", "hierarchy_expander_va": "0x000233c0",
            "current_postprocess_va": "0x00093850",
            "main_mask": "0x01ffe7ff", "late_neck_head_mask": "0x00001800",
            "masks_cover_all_25_channels_without_overlap": True,
            "current_postprocess_validation": {"cases": 116, "mask_cases": 29,
                                                "maximum_abs_difference": 3.81469727e-06,
                                                "validator": "tools/nfl_player_current_postprocess_native_validate.py"},
            "bit_identity_claimed": False,
        },
        "mapped_player_assets": {
            "lo_body": {
                "resource": [3, 113], "outer_id": lo_scene["outer_id"],
                "decoded_sha256": lo_scene["decoded_sha256"], "shape_name": "LO_res",
                "transform_count": 25, "vertex_count": raw_output["skins"][0]["vertex_count"],
                "primitive_count": raw_output["skins"][0]["primitive_count"],
                "influence_arity_counts": raw_output["skins"][0]["influence_arity_counts"],
                "canonical_gltf": str(gltf_path), "canonical_gltf_sha256": file_sha256(gltf_path),
                "canonical_bin": str(bin_path), "canonical_bin_sha256": file_sha256(bin_path),
                "skin_attachment_proved": True,
            },
            "hi_body": {
                "resource": [3, 114], "outer_id": hi_scene["outer_id"],
                "decoded_sha256": hi_scene["decoded_sha256"], "shape_name": "HI_res",
                "transform_count": 62, "primitive_count": hi_scene["submesh_count"],
                "static_gltf": "assets/intermediate/nfl2k5/models/0003_0114_hi_body.gltf",
                "skin_attachment_proved": False,
            },
        },
        "export_decision": {
            "animated_gltf_emitted": False, "status": "withheld_until_every_ownership_edge_is_exact",
            "reason": "the selected clip and low skin are exact, but concrete selector production, playback mode, live actor initial transform/context, and HI_res skin attachment are not all exact",
            "required_before_emit": [
                "prove the dynamic producer that yields selector result 2",
                "prove state+0xa0 equals selected-name mode 1 for the concrete celebration event",
                "recover concrete actor+0x18 initial transform/scale and actor+0x3c profile fields",
                "attach the 62-transform HI_res mesh to its exact shipped skin/palette records",
            ],
        },
        "ownership_claims": [
            {"claim": "row 2 necessarily selects the unique target SMCD when index 2 is produced", "confidence": "exact_conditional", "limitation": "index-2 producer unproved"},
            {"claim": "selected name is prefetched/acquired as CELEBRATE and reaches controller install in mode 1", "confidence": "instruction_exact_conditional", "limitation": "concrete state+0xa0 value unproved"},
            {"claim": "0x0051cd70/0x00091890 and pool 0x00e60268 are the player lo_body family", "confidence": "instruction_exact_family"},
            {"claim": "gameplay uses live actor+0x18 as external root for both low/high hierarchies", "confidence": "instruction_exact"},
            {"claim": "portable 0x00092140 and 0x00093850 cover the exact shipped gameplay call sites", "confidence": "instruction_exact_value_validated_not_bit_identical"},
            {"claim": "canonical 0003/0113 meter skin is the mapped low player render witness", "confidence": "exact_low_skin"},
        ],
        "ghidra": {
            "script": "tools/ghidra_scripts/NflPlayerClipOwnershipTrace.java",
            "trace": "reports/assets/nfl_player_clip_ownership_ghidra/nfl_player_clip_ownership_trace.txt",
            "pseudo_c": "reports/assets/nfl_player_clip_ownership_ghidra/nfl_player_clip_ownership_focused_pseudo_c.c",
            "missing_function_boundaries": ["0x002ddb10", "0x002de170"],
        },
        "source_pins": {
            "motion_inventory": source_pin(args.motion_inventory), "sampler_report": source_pin(args.sampler_report),
            "sampler_tsv": source_pin(args.sampler_tsv), "pose_report": source_pin(args.pose_report),
            "pool_report": source_pin(args.pool_report), "bone_report": source_pin(args.bone_report),
            "player_pose_report": source_pin(args.player_pose_report),
            "player_92140_report": source_pin(args.player_92140_report),
            "player_postprocess_report": source_pin(args.player_postprocess_report),
            "root_report": source_pin(args.root_report), "scne_report": source_pin(args.scne_report),
            "raw_skin_report": source_pin(args.raw_skin_report), "meter_skin_report": source_pin(args.meter_skin_report),
            "xbe_header": source_pin(args.xbe_header),
            "player_pose_header": source_pin(Path("include/recovered/nfl2k5/player_pose.h")),
            "player_pose_source": source_pin(Path("src/recovered/nfl2k5/player_pose.c")),
            "player_local_postprocess_header": source_pin(Path("include/recovered/nfl2k5/player_local_postprocess.h")),
            "player_local_postprocess_source": source_pin(Path("src/recovered/nfl2k5/player_local_postprocess.c")),
            "player_current_postprocess_header": source_pin(Path("include/recovered/nfl2k5/player_current_postprocess.h")),
            "player_current_postprocess_source": source_pin(Path("src/recovered/nfl2k5/player_current_postprocess.c")),
            "player_current_postprocess_validator": source_pin(Path("tools/nfl_player_current_postprocess_native_validate.py")),
        },
        "worked": [
            "reopened and hashed exact outer 3092 chunk 163 wrapper/body and every bounded motion region",
            "decoded all 37 selector rows and joined all 70 unique non-null names to one SMCD in outer 3092",
            "proved row 2 has no side ambiguity and preserved conditional selector/acquire/controller instructions",
            "joined player pool, 23-to-25 channel map, controller update, trajectory, hierarchy, postprocess, and render paths",
            "joined the exact low player SCNE to its canonical 25-joint meter skin",
        ],
        "failed": [
            "the upstream dynamic producer of selector result 2 remains unresolved",
            "a concrete event's state+0xa0 selected-name mode and initial actor+0x18/context values remain unresolved",
            "the shipped 62-transform HI_res skin attachment remains unresolved",
            "Xbox rsqrt/x87 bit identity remains intentionally unclaimed",
        ],
        "portme": [
            "// PORTME(0x001B6B50): recover the dynamic producer that returns selector index 2 for ANM_CELEBRATE_USER_34.",
            "// PORTME(0x002DDB7F): prove state+0xA0 equals 1 for a concrete playback of selector row 2.",
            "// PORTME(0x002CC570/0x0028E4C2): capture or reconstruct the concrete actor+0x18 initial live transform and actor scale/context.",
            "// PORTME(0x00090570/0x00093800): recover exact HI_res skin/palette ownership before emitting a combined low/high animated glTF.",
            "// PORTME(0x002DDB10): create a saved Ghidra function boundary; exact bytes are retained in the trace.",
            "// PORTME(0x002DE170): create a saved Ghidra function boundary; exact bytes are retained in the trace.",
            "// PORTME(0x0008D630/0x00093850): reproduce Xbox rsqrt/x87 behavior only if bit identity is required.",
        ],
    }
    return report, selectors, path_rows


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--motion-inventory", type=Path, required=True)
    parser.add_argument("--sampler-report", type=Path, required=True)
    parser.add_argument("--sampler-tsv", type=Path, required=True)
    parser.add_argument("--pose-report", type=Path, required=True)
    parser.add_argument("--pool-report", type=Path, required=True)
    parser.add_argument("--bone-report", type=Path, required=True)
    parser.add_argument("--player-pose-report", type=Path, required=True)
    parser.add_argument("--player-92140-report", type=Path, required=True)
    parser.add_argument("--player-postprocess-report", type=Path, required=True)
    parser.add_argument("--root-report", type=Path, required=True)
    parser.add_argument("--scne-report", type=Path, required=True)
    parser.add_argument("--raw-skin-report", type=Path, required=True)
    parser.add_argument("--meter-skin-report", type=Path, required=True)
    parser.add_argument("--meter-skin-dir", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--selectors-tsv", type=Path, required=True)
    parser.add_argument("--path-tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        report, selectors, path_rows = build_report(args)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_tsv(args.selectors_tsv, selectors, [
            "selector_index", "row_va", "row_file_offset", "left_pointer_field_va",
            "left_name_string_va", "left_name", "left_match_count", "left_outer_index",
            "left_chunk_index", "left_chunk_offset", "left_decoded_sha256",
            "right_pointer_field_va", "right_name_string_va", "right_name",
            "right_match_count", "right_outer_index", "right_chunk_index",
            "right_chunk_offset", "right_decoded_sha256", "opaque_u32", "opaque_s32",
        ])
        write_tsv(args.path_tsv, path_rows,
                  ["step", "source", "target", "instruction_va", "evidence", "meaning", "confidence"])
    except (OwnershipError, nfl_outer.FormatError, OSError, UnicodeError, ValueError,
            KeyError, StopIteration) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"NFL_PLAYER_CLIP_OWNERSHIP_COMPLETE clip={TARGET_NAME} selector=2:right rows={SELECTOR_COUNT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
