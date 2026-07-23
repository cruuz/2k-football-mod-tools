#!/usr/bin/env python3
"""Build a side-by-side Blender authoring scene from the compatibility report.

Run ``--check`` with normal Python.  Scene creation must run inside Blender and
never emits a game archive or claims the imported collections are APF-ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA = "cross_title_model_compatibility/v1"
DEFAULT_REPORT = ROOT / "reports/assets/cross_title_model_compatibility.json"


class BlenderWorkflowError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BlenderWorkflowError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_report(path: Path) -> tuple[dict, list[tuple[dict, Path]]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "report must be a non-symlink regular file")
    payload = path.read_bytes()
    try:
        report = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise BlenderWorkflowError("compatibility report is invalid JSON") from exc
    canonical = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical and report.get("schema") == REPORT_SCHEMA,
            "compatibility report schema/canonical encoding differs")
    workflow = report.get("blender_workflow", {})
    require(workflow.get("status") == "safe authoring/reference workflow only",
            "report does not authorize the reference workflow")
    assets = report.get("assets", {})
    checked: list[tuple[dict, Path]] = []
    for item in workflow.get("items", []):
        role = item.get("role")
        require(type(role) is str and role in assets, "workflow role is not in report assets")
        text = item.get("gltf")
        require(type(text) is str, "workflow glTF path missing")
        candidate = ROOT / text
        resolved = candidate.resolve(strict=True)
        require(ROOT == resolved or ROOT in resolved.parents, "workflow path escapes repository")
        info = resolved.lstat()
        require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                f"workflow glTF is not a regular file: {text}")
        require(sha256_file(resolved) == assets[role]["gltf"]["sha256"],
                f"workflow glTF hash differs: {role}")
        scale = item.get("preview_scale")
        location = item.get("location")
        require(
            isinstance(scale, list) and len(scale) == 3
            and isinstance(location, list) and len(location) == 3
            and all(type(value) in (int, float) for value in scale + location),
            f"workflow transform invalid: {role}",
        )
        checked.append((item, resolved))
    require(len(checked) == 4, "expected four comparison assets")
    current = path.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino, current.st_size)
            == (supplied.st_dev, supplied.st_ino, supplied.st_size),
            "report changed while validating")
    return report, checked


def arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def blender_argv() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    return sys.argv[1:]


def create_scene(report: dict, checked: list[tuple[dict, Path]], output: Path) -> None:
    try:
        import bpy  # type: ignore
    except ImportError as exc:
        raise BlenderWorkflowError(
            "scene creation requires Blender: blender --background --python "
            "tools/blender_cross_title_model_compare.py -- --output NEW.blend"
        ) from exc
    requested = output.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    require(not os.path.lexists(requested), "output .blend already exists; overwrite refused")
    parent = requested.parent
    parent_info = parent.lstat()
    require(stat.S_ISDIR(parent_info.st_mode) and not stat.S_ISLNK(parent_info.st_mode),
            "output parent must be a non-symlink directory")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for item, gltf_path in checked:
        before = set(bpy.data.objects)
        result = bpy.ops.import_scene.gltf(filepath=os.fspath(gltf_path))
        require("FINISHED" in result, f"Blender glTF import failed: {item['role']}")
        imported = set(bpy.data.objects) - before
        require(bool(imported), f"Blender imported no objects: {item['role']}")
        anchor = bpy.data.objects.new(f"VC_COMPARE_{item['role']}", None)
        bpy.context.scene.collection.objects.link(anchor)
        roots = [obj for obj in imported if obj.parent not in imported]
        for obj in roots:
            obj.parent = anchor
        anchor.scale = tuple(float(value) for value in item["preview_scale"])
        anchor.location = tuple(float(value) for value in item["location"])
        anchor["vc_reference_only"] = True
        anchor["vc_not_apf_importable"] = True
        anchor["vc_source_sha256"] = report["assets"][item["role"]]["gltf"]["sha256"]
        anchor["vc_scale_claim"] = item["scale_claim"]
    bpy.context.scene["vc_cross_title_report_schema"] = REPORT_SCHEMA
    bpy.context.scene["vc_direct_copy_safe"] = False
    bpy.context.scene["vc_apf_writeback_available"] = False
    bpy.ops.wm.save_as_mainfile(filepath=os.fspath(requested), check_existing=False)


def main() -> int:
    args = arguments(blender_argv())
    report_path = args.report.expanduser().resolve(strict=True)
    report, checked = load_report(report_path)
    if args.check:
        print(
            "BLENDER_CROSS_TITLE_MODEL_COMPARE_CHECK_PASS "
            f"assets={len(checked)} direct_copy=false writeback=false"
        )
        return 0
    require(args.output is not None, "--output is required unless --check is used")
    create_scene(report, checked, args.output)
    print(
        "BLENDER_CROSS_TITLE_MODEL_COMPARE_PASS "
        f"assets={len(checked)} direct_copy=false writeback=false"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, BlenderWorkflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
