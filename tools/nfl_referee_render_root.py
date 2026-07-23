#!/usr/bin/env python3
"""Pin NFL 2K5 gameplay-referee transform-to-render ownership.

This report closes the static edge from the actor transform pointer written by
the trajectory callback to the referee hierarchy, render-object matrix link,
skin-palette builder, and draw dispatcher.  It does not invent runtime values
or assign the selected penalty clip to one concrete actor in the seven-entry
pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable


SCHEMA = "nfl2k5_referee_render_root/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)

# These are raw-backed executable image spans.  The 0x001d2d90 span includes
# the six bytes between its two Ghidra body ranges; preserving that gap is
# intentional and makes the evidence independent of a mutable function body.
FUNCTION_RANGES = (
    ("render_object_dispatch", 0x00021860, 0x000218C3),
    ("render_matrix_pointer_setter", 0x00021900, 0x00021904),
    ("skin_palette_builder", 0x00022C00, 0x00022ECA),
    ("hierarchy_expander", 0x000233C0, 0x00023495),
    ("shape_draw_dispatch", 0x000243D0, 0x00024978),
    ("fixed_turn_y_matrix", 0x00037EB0, 0x00037F35),
    ("gameplay_draw_orchestrator", 0x00064E80, 0x00064F7C),
    ("referee_queue_registration", 0x00074DD0, 0x00074E19),
    ("referee_root_basis_scale", 0x00096350, 0x000963AB),
    ("referee_scene_loader", 0x00096600, 0x00096A15),
    ("referee_row_scale_accessor", 0x00096AD0, 0x00096AFB),
    ("referee_root_scale_dispatch", 0x00096B00, 0x00096B1E),
    ("referee_hierarchy_bridge", 0x00096B20, 0x00096B4E),
    ("referee_queue_store", 0x00096B50, 0x00096B83),
    ("referee_draw_queue", 0x00096B90, 0x00096CFC),
    ("alternate_draw_orchestrator", 0x00111E00, 0x00111FC0),
    ("gameplay_referee_pose_root_builder", 0x001D2D90, 0x001D2EA4),
    ("referee_pool_initializer", 0x00217EB0, 0x00217F1F),
    ("referee_actor_update", 0x00218010, 0x00218087),
    ("referee_pool_update", 0x002180D0, 0x00218144),
    ("alternate_referee_pose_root_builder", 0x0028EA10, 0x0028EB88),
    ("alternate_pose_dispatch", 0x0028ECF0, 0x0028ECFF),
    ("referee_trajectory_callback", 0x002CC570, 0x002CC622),
    ("quaternion_to_matrix_array", 0x003CA3D0, 0x003CA4D0),
)

REQUIRED_TRACE_LINES = (
    # Seven low/high render-object rows created by the referee scene loader.
    "0x00096960 PUSH 0xe65ccc",
    "0x0009698A MOV dword ptr [EBX + 0xb661c8],EAX",
    "0x0009699D PUSH 0xe65cbc",
    "0x000969AF MOV dword ptr [EBX + 0xb661c4],EAX",
    "0x000969BA CMP EAX,0x6",
    # Actor transform writes by the trajectory callback.
    "0x002CC57D MOV ESI,dword ptr [EDI + 0x18]",
    "0x002CC5CA MOV dword ptr [ESI + 0x34],ECX",
    "0x002CC5D1 MOV dword ptr [ESI + 0x38],ECX",
    "0x002CC5DC MOV dword ptr [ESI + 0x30],EDX",
    "0x002CC5FA MOV dword ptr [ESI + 0x50],ECX",
    # Main gameplay root construction from actor +0x18.
    "0x001D2E28 MOV ECX,dword ptr [ESI + 0x18]",
    "0x001D2E2B MOV EDX,dword ptr [ECX + 0x50]",
    "0x001D2E2E LEA ECX,[ESP + 0x20]",
    "0x001D2E32 CALL 0x00037eb0",
    "0x001D2E3A FLD float ptr [EAX + 0x38]",
    "0x001D2E44 FLD float ptr [EDX + 0x48]",
    "0x001D2E4B FMUL float ptr [ESI + 0x8]",
    "0x001D2E52 FLD float ptr [EAX + 0x30]",
    "0x001D2E09 MOV EDX,dword ptr [ESI + 0x4]",
    "0x001D2E0F MOV ECX,dword ptr [EAX + 0x34]",
    "0x001D2E18 CALL 0x003ca3d0",
    "0x001D2E23 CALL 0x00096b00",
    "0x001D2E7D MOV EAX,dword ptr [ESI + 0x4]",
    "0x001D2E80 MOV ECX,dword ptr [ESI + 0x2c]",
    "0x001D2E83 PUSH EAX",
    "0x001D2E84 CALL 0x00096b20",
    # Alternate root builder consumes all four transform placement fields.
    "0x0028EA3B MOV ESI,dword ptr [EDI + 0x18]",
    "0x0028EAE7 MOV EDX,dword ptr [ESI + 0x50]",
    "0x0028EAEA CALL 0x00037eb0",
    "0x0028EAEF FLD float ptr [ESI + 0x38]",
    "0x0028EAF6 FLD float ptr [ESI + 0x34]",
    "0x0028EB03 FLD float ptr [ESI + 0x30]",
    "0x0028EB37 CALL 0x001c2520",
    "0x0028EB42 CALL 0x00096b00",
    "0x0028EB4E LEA EDX,[ESP + 0x34]",
    "0x0028EB52 CALL 0x00096b20",
    # Hierarchy bridge: shape from low render object, in-place current array,
    # and caller-supplied external root remain distinct arguments.
    "0x00096B2F MOV ECX,dword ptr [ECX + 0xb661c4]",
    "0x00096B36 MOV ESI,dword ptr [EBP + 0x8]",
    "0x00096B39 PUSH EDX",
    "0x00096B3A PUSH ESI",
    "0x00096B3B CALL 0x00021930",
    "0x00096B40 MOV EDX,ESI",
    "0x00096B44 CALL 0x000233c0",
    "0x00023417 MOV EDX,dword ptr [EBP + 0xc]",
    # The same actor +0x04 array is registered for its +0x2c row.
    "0x00074E03 MOV EDX,dword ptr [ESI + 0x4]",
    "0x00074E06 MOV ECX,dword ptr [ESI + 0x2c]",
    "0x00074E0A CALL 0x00096b50",
    "0x00096B73 MOV dword ptr [EAX + 0xb661cc],ECX",
    "0x00096B79 MOV dword ptr [EAX + 0xb661d0],EDX",
    # Queue chooses low/high render object, attaches current matrices, draws.
    "0x00096BCA MOV EAX,dword ptr [ESI + -0x4]",
    "0x00096BCD ADD EAX,EBX",
    "0x00096BCF MOV EDI,dword ptr [EAX*0x4 + 0xb661c4]",
    "0x00096BD8 CALL 0x00021900",
    "0x00096CA6 CALL 0x00021860",
    "0x00021900 MOV dword ptr [ECX + 0x14],EDX",
    # Render object forwards the linked matrices through palette generation.
    "0x000218AA MOV EDX,dword ptr [ESI + 0x14]",
    "0x000218B3 MOV ECX,dword ptr [ESI + 0x8]",
    "0x000218B6 CALL 0x000243d0",
    "0x0002469F MOV EAX,dword ptr [ESP + 0x28]",
    "0x000246A3 MOV ECX,dword ptr [ESP + 0x1c]",
    "0x000246B1 CALL 0x00022c00",
    "0x00022C60 MOV EDX,dword ptr [EBP + 0xc]",
    # Both draw orchestrators enqueue before consuming the referee queue.
    "0x00064EFF CALL 0x0011a8f0",
    "0x00064F30 CALL 0x00096b90",
    "0x00111E54 CALL 0x0011a8f0",
    "0x00111E6D CALL 0x00096b90",
    "0x0011A8FA CALL 0x00074dd0",
)


class RenderRootError(ValueError):
    """Raised when pinned evidence no longer matches the recovered contract."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_pin(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256_file(path)}


def load_json(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise RenderRootError(f"{path}: expected schema {schema!r}")
    return value


def xbe_reader(xbe: bytes, header: dict[str, Any]) -> Callable[[int, int], bytes]:
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                result = xbe[offset:offset + size]
                if len(result) == size:
                    return result
        raise RenderRootError(
            f"XBE VA 0x{va:08x}+0x{size:x} is not completely raw-backed"
        )
    return read


def executable_evidence(xbe_path: Path, header_path: Path) -> dict[str, Any]:
    xbe = xbe_path.read_bytes()
    header = json.loads(header_path.read_text(encoding="utf-8"))
    md5 = hashlib.md5(xbe).hexdigest()
    digest = sha256(xbe)
    if md5 != EXPECTED_XBE_MD5 or digest != EXPECTED_XBE_SHA256:
        raise RenderRootError(f"unexpected NFL 2K5 XBE {md5}/{digest}")
    if header.get("md5") != md5 or header.get("sha256") != digest:
        raise RenderRootError("XBE header report does not pin the executable")
    read = xbe_reader(xbe, header)
    ranges = []
    for name, start, end in FUNCTION_RANGES:
        body = read(start, end - start)
        ranges.append({
            "name": name,
            "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}",
            "size": len(body),
            "sha256": sha256(body),
        })
    return {
        "path": str(xbe_path),
        "md5": md5,
        "sha256": digest,
        "header": source_pin(header_path),
        "function_image_spans": ranges,
    }


def validate_upstream(root: dict[str, Any], pose: dict[str, Any]) -> None:
    boundary = root.get("confidence_boundary", {})
    if "the final actor+0x18 to renderer external-root ownership edge" not in boundary.get(
        "unproved", []
    ):
        raise RenderRootError("root trajectory report no longer exposes the target gap")
    if boundary.get("gltf_root_translation_emitted") is not False:
        raise RenderRootError("root trajectory report unexpectedly emits translation")
    selected = root.get("selected_clip", {})
    if selected.get("name") != "ANM_REF_PENALTY_DELAY_OF_GAME_R":
        raise RenderRootError("root trajectory selected clip differs")
    if root.get("serialized_trajectory", {}).get("sha256") != (
        "829de7b7999ea1a47401d81b4ccc7bfa042d872614e0ee50c792babdded111fa"
    ):
        raise RenderRootError("root trajectory payload differs")

    renderer = pose.get("renderer_boundary", {})
    if renderer.get("render_dispatch") != "0x00021860 -> 0x000243d0 -> 0x00022c00":
        raise RenderRootError("pose report render dispatch differs")
    if renderer.get("current_space") != (
        "external-root-parent space selected by each 0x000233c0 caller; "
        "not universally model-space or universally world-space"
    ):
        raise RenderRootError("pose report current-space contract differs")
    multiplication = pose.get("multiplication_contract", {})
    if multiplication.get("hierarchy") != (
        "current[i] = local[i] * (current[parent] or external_root)"
    ):
        raise RenderRootError("pose report hierarchy equation differs")


def validate_ghidra(trace_path: Path, pseudo_path: Path) -> None:
    trace = trace_path.read_text(encoding="utf-8")
    pseudo = pseudo_path.read_text(encoding="utf-8")
    if trace.count("\nFUNCTION 0x") != 32:
        raise RenderRootError("focused trace function count differs")
    if pseudo.count("/* 0x") != 32:
        raise RenderRootError("focused pseudo-C function count differs")
    if "// PORTME: could not decompile function at" in pseudo:
        raise RenderRootError("a focused function did not decompile")
    for line in REQUIRED_TRACE_LINES:
        if line not in trace:
            raise RenderRootError(f"missing instruction evidence: {line}")


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    root = load_json(args.root_trajectory, "nfl2k5_referee_root_trajectory/v1")
    pose = load_json(args.pose_matrix, "nfl2k5_pose_matrix_apply/v2")
    validate_upstream(root, pose)
    validate_ghidra(args.trace, args.pseudo)

    return {
        "schema": SCHEMA,
        "result": {
            "actor_transform_to_renderer_external_root_edge_proved": True,
            "confidence": "instruction_exact_static_ownership",
            "closed_upstream_gap": (
                "the final actor+0x18 to renderer external-root ownership edge"
            ),
            "selected_clip_to_concrete_actor_instance_proved": False,
            "gameplay_equivalent_gltf_root_track_ready": False,
            "reason_root_track_remains_withheld": (
                "the render edge is closed, but the selected clip still lacks a "
                "concrete one-of-seven actor instance and captured live actor, "
                "controller, and transform-state values"
            ),
        },
        "object_fields": {
            "referee_actor": {
                "+0x04": "pointer to a 25-entry local/current 4x4 matrix array; quaternions are converted into it, then it is hierarchy-expanded in place",
                "+0x08": "actor scale used by trajectory and main render-root Y",
                "+0x14": "motion/controller pointer",
                "+0x18": "live actor-transform pointer",
                "+0x2c": "seven-row referee render selector",
                "+0x30": "next referee actor in gameplay pool",
            },
            "actor_transform": {
                "+0x30": "world/root X used by both hierarchy builders",
                "+0x34": "trajectory callback Y; consumed by alternate 0x0028ea10 builder, not main 0x001d2d90 builder",
                "+0x38": "world/root Z used by both hierarchy builders",
                "+0x3c": "homogeneous W set to 1.0 by 0x002cc570",
                "+0x50": "16-bit fixed-turn heading used to construct the external-root Y rotation",
                "+0x84": "live transform-state base consumed before callback placement writes",
            },
            "controller": {
                "+0x34": "pointer to 25 scalar-first pose quaternions consumed by 0x003ca3d0",
                "+0x48": "main 0x001d2d90 external-root Y before multiplication by actor scale",
                "+0x74": "installed motion root used by controller update",
            },
            "render_object": {
                "+0x08": "SCNE shape pointer",
                "+0x14": "current matrix-array pointer linked by 0x00021900 before draw",
                "+0x18": "shape-dispatch argument distinct from current matrices",
                "+0x1c": "shape-dispatch argument distinct from current matrices",
            },
        },
        "referee_render_rows": {
            "count": 7,
            "stride_bytes": 28,
            "low_render_object": {
                "name": "ref_low",
                "name_va": "0x00e65cbc",
                "row_field_va": "0x00b661c4 + row*0x1c",
                "loader_store_va": "0x000969af",
            },
            "high_render_object": {
                "name": "ref_high",
                "name_va": "0x00e65ccc",
                "row_field_va": "0x00b661c8 + row*0x1c",
                "loader_store_va": "0x0009698a",
            },
            "queued_variant_flag": "0x00b661cc + row*0x1c; 0 selects ref_low and 1 selects ref_high",
            "queued_current_matrices": "0x00b661d0 + row*0x1c",
            "hierarchy_shape_source": "ref_low render object +0x08; both shipped referee LODs have the same proved 25-transform order",
        },
        "external_root_builders": [
            {
                "function_va": "0x001d2d90",
                "role": "main gameplay referee pose/root preparation",
                "pool_head_va": "0x00e60274",
                "scratch_matrix": "aligned stack +0x20",
                "rotation": "row-vector +Y rotation from low16((actor+0x18)+0x50) via 0x00037eb0",
                "translation": {
                    "x": "(actor+0x18)+0x30",
                    "y": "(actor+0x14)+0x48 multiplied by actor+0x08",
                    "z": "(actor+0x18)+0x38",
                },
                "important_y_boundary": "(actor+0x18)+0x34 is not read by this builder",
                "local_pose_preparation": "0x003ca3d0 converts 25 quaternions from (actor+0x14)+0x34 into actor+0x04; 0x00096b00 applies the per-row referee scale to root basis only",
                "hierarchy_call": "ECX=actor+0x2c selector, EDX=&external_root, stack[0]=actor+0x04 matrices -> 0x00096b20",
                "instruction_vas": [
                    "0x001d2e28", "0x001d2e2b", "0x001d2e32",
                    "0x001d2e3a", "0x001d2e44", "0x001d2e4b",
                    "0x001d2e52", "0x001d2e7d", "0x001d2e80",
                    "0x001d2e83", "0x001d2e84",
                ],
            },
            {
                "function_va": "0x0028ea10",
                "role": "alternate per-update referee pose/root preparation dispatched by 0x0028ecf0",
                "pool_head_va": "0x00e60274",
                "scratch_matrix": "aligned stack +0x30",
                "rotation": "row-vector +Y rotation from low16((actor+0x18)+0x50) via 0x00037eb0",
                "translation": {
                    "x": "(actor+0x18)+0x30",
                    "y": "(actor+0x18)+0x34",
                    "z": "(actor+0x18)+0x38",
                },
                "local_pose_preparation": "0x001c2520/0x003ca3d0 converts 25 quaternions into actor+0x04; 0x00096b00 applies the per-row referee scale to root basis only",
                "hierarchy_call": "ECX=actor+0x2c selector, EDX=&external_root, stack[0]=actor+0x04 matrices -> 0x00096b20",
                "instruction_vas": [
                    "0x0028ea3b", "0x0028eae7", "0x0028eaea",
                    "0x0028eaef", "0x0028eaf6", "0x0028eb03",
                    "0x0028eb47", "0x0028eb4a", "0x0028eb4d",
                    "0x0028eb4e", "0x0028eb52",
                ],
            },
        ],
        "ownership_chain": [
            {
                "step": 1,
                "function_va": "0x002cc570",
                "contract": "trajectory callback obtains actor+0x18 and writes placement X/Y/Z/W/heading after live-state transformation",
                "instruction_vas": [
                    "0x002cc57d", "0x002cc582", "0x002cc5af",
                    "0x002cc5ca", "0x002cc5d1", "0x002cc5dc",
                    "0x002cc5e1", "0x002cc5fa",
                ],
            },
            {
                "step": 2,
                "function_va": "0x001d2d90/0x0028ea10",
                "contract": "read the same actor+0x18 pointer and construct a row-vector external-root matrix with heading and placement",
            },
            {
                "step": 3,
                "function_va": "0x00096b20",
                "contract": "select ref_low shape by actor+0x2c and call 0x000233c0 with actor+0x04 as both local source/current destination and the constructed matrix as external root",
                "hierarchy_equation": "current[i] = local[i] * (current[parent] or external_root)",
            },
            {
                "step": 4,
                "function_va": "0x00074dd0 -> 0x00096b50",
                "contract": "walk the same 0x00e60274 pool and queue actor+0x04 current matrices under actor+0x2c plus the low/high variant flag",
            },
            {
                "step": 5,
                "function_va": "0x00096b90",
                "contract": "select ref_low/ref_high render object, write queued actor+0x04 to render object+0x14 through 0x00021900, and call 0x00021860",
            },
            {
                "step": 6,
                "function_va": "0x00021860 -> 0x000243d0 -> 0x00022c00",
                "contract": "forward shape and render object+0x14 current matrices to skin-palette generation and the native draw path",
                "palette_equation": "skin = T(-serialized cumulative bind translation) * current",
            },
        ],
        "draw_order_proof": [
            {
                "function_va": "0x00064e80",
                "enqueue": "0x00064eff -> 0x0011a8f0 -> 0x00074dd0",
                "draw": "0x00064f30 -> 0x00096b90",
                "order": "enqueue precedes draw",
            },
            {
                "function_va": "0x00111e00",
                "enqueue": "0x00111e54 -> 0x0011a8f0 -> 0x00074dd0",
                "draw": "0x00111e6d -> 0x00096b90",
                "order": "enqueue precedes draw",
            },
        ],
        "remaining_boundaries": [
            "the selected penalty clip is not linked to one concrete record in the seven-entry referee pool",
            "initial/live actor scale, controller +0x48, actor-transform placement/state, and heading require a concrete runtime play capture",
            "the main and alternate builders intentionally differ on Y ownership; a port must preserve their call-context policy",
            "the low/high variant flag is runtime camera/visibility state even though both target render-object slots are statically proved",
        ],
        "portme": [
            "// PORTME: capture the concrete one-of-seven referee actor selected for ANM_REF_PENALTY_DELAY_OF_GAME_R before exporting a gameplay-equivalent root track.",
            "// PORTME: preserve the 0x001D2D90 controller-derived Y rule and the 0x0028EA10 actor-transform Y rule as distinct call-context policies.",
            "// PORTME: retain actor+0x04 local/current matrices, the stack external root, render-object+0x14, and the generated skin palette as separate storage/space concepts.",
            "// PORTME: reproduce low/high queue selection instead of rendering both LODs simultaneously in the gameplay path.",
        ],
        "worked": [
            "closed actor+0x18 to gameplay external-root ownership with two instruction-exact builders",
            "joined the external root to in-place 25-matrix hierarchy expansion",
            "joined the same actor+0x04 matrix array through queue registration and low/high render-object selection",
            "joined render-object+0x14 through shape draw dispatch to skin-palette generation",
            "proved enqueue-before-draw ordering in both recovered gameplay draw orchestrators",
        ],
        "executable": executable_evidence(args.xbe, args.xbe_header),
        "sources": {
            "generator": source_pin(Path(__file__)),
            "ghidra_script": source_pin(args.ghidra_script),
            "ghidra_trace": source_pin(args.trace),
            "ghidra_pseudo_c": source_pin(args.pseudo),
            "root_trajectory_report": source_pin(args.root_trajectory),
            "pose_matrix_report": source_pin(args.pose_matrix),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument(
        "--root-trajectory", type=Path,
        default=Path("reports/assets/nfl_referee_root_trajectory.json"),
    )
    parser.add_argument(
        "--pose-matrix", type=Path,
        default=Path("reports/assets/nfl_pose_matrix_apply.json"),
    )
    parser.add_argument(
        "--trace", type=Path,
        default=Path(
            "reports/assets/nfl_referee_render_root_ghidra/"
            "nfl_referee_render_root_trace.txt"
        ),
    )
    parser.add_argument(
        "--pseudo", type=Path,
        default=Path(
            "reports/assets/nfl_referee_render_root_ghidra/"
            "nfl_referee_render_root_focused_pseudo_c.c"
        ),
    )
    parser.add_argument(
        "--ghidra-script", type=Path,
        default=Path("tools/ghidra_scripts/NflRefereeRenderRootTrace.java"),
    )
    parser.add_argument(
        "--json", type=Path,
        default=Path("reports/assets/nfl_referee_render_root.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "NFL_REFEREE_RENDER_ROOT_REPORT_COMPLETE "
        f"functions={len(FUNCTION_RANGES)} chain={len(report['ownership_chain'])} "
        "edge_proved=1 root_track_ready=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
