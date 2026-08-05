#!/usr/bin/env python3
"""Blender-background renderer for ``apf_helmet_static_visual_proof.py``."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Quaternion, Vector


UV_LAYER_NAME = "Exact APF crest UV"
CARRIER_VISUAL_NORMAL_BIAS_M = 0.0005


def fail(message: str) -> None:
    raise RuntimeError(f"APF exact helmet proof: {message}")


def arguments() -> Path:
    if "--" not in sys.argv:
        fail("missing proof receipt after --")
    values = sys.argv[sys.argv.index("--") + 1 :]
    if len(values) != 1:
        fail("expected exactly one proof receipt")
    path = Path(values[0]).resolve()
    if not path.is_file():
        fail(f"receipt is unavailable: {path}")
    return path


def preflight_outputs(root: Path) -> None:
    """A retry is safe only before Blender has published any visual result."""

    outputs = [
        *(root / f"helmet-v18-{name}.png"
          for name in ("side-right", "side-left", "crown", "rear")),
        *(root / f"helmet-v18-{name}.png"
          for name in ("debug-carrier-material", "debug-carrier-uv",
                       "debug-carrier-material-roll90", "debug-camera-axes")),
        root / "helmet-v18-proof.blend",
        root / "helmet-v18-blender-stage.json",
        root / "helmet-v18-contact-sheet.png",
        root / "helmet-v18-debug-contact-sheet.png",
    ]
    found = [path.name for path in outputs if path.exists() or path.is_symlink()]
    if found:
        fail("refusing a partial/complete render retry; outputs already exist: " + ", ".join(found))


def write_error_log(receipt_path: Path | None, message: str) -> None:
    if receipt_path is None or not receipt_path.parent.is_dir():
        return
    path = receipt_path.parent / "helmet-v18-blender-error.log"
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, message.encode("utf-8", errors="replace"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def srgb_to_linear(value: float) -> float:
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    """An exposure/specular-independent unlit solid material."""

    result = bpy.data.materials.new(name)
    result.diffuse_color = color
    result.use_nodes = True
    nodes = result.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (
        srgb_to_linear(color[0]), srgb_to_linear(color[1]),
        srgb_to_linear(color[2]), color[3],
    )
    emission.inputs["Strength"].default_value = 1.0
    result.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return result


def crest_material(
    path: Path,
    shell_color: tuple[float, float, float, float],
) -> bpy.types.Material:
    """Opaque crest material with inactive pixels simulated as exact shell RGB.

    The decoded review PNG uses alpha zero for the flat black/unpainted region.
    Mixing that alpha against the staged shell color before one opaque emission
    avoids all transparent draw ordering while preserving the recovered rule.
    """

    result = bpy.data.materials.new("Exact v18 crest region material")
    result.diffuse_color = (*shell_color[:3], 1.0)
    result.use_nodes = True
    nodes = result.node_tree.nodes
    nodes.clear()
    links = result.node_tree.links
    output = nodes.new("ShaderNodeOutputMaterial")
    image = nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(str(path), check_existing=False)
    image.image.colorspace_settings.name = "sRGB"
    image.interpolation = "Closest"
    image.extension = "CLIP"
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.uv_map = UV_LAYER_NAME
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs[1].default_value = (
        srgb_to_linear(shell_color[0]), srgb_to_linear(shell_color[1]),
        srgb_to_linear(shell_color[2]), 1.0,
    )
    links.new(uv_map.outputs["UV"], image.inputs["Vector"])
    links.new(image.outputs["Alpha"], mix.inputs[0])
    links.new(image.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    if hasattr(result, "blend_method"):  # Blender 4.0/4.1 compatibility.
        result.blend_method = "OPAQUE"
    return result


def split_carrier_sides(group: dict) -> dict[str, dict]:
    """Split draw 2 into its exact two signed-x topology islands."""

    positions = group["positions_cm"]
    assigned: dict[str, list[list[int]]] = {"left": [], "right": []}
    for triangle in group["triangles"]:
        x_values = [positions[index][0] for index in triangle]
        has_negative = any(value < 0.0 for value in x_values)
        has_positive = any(value > 0.0 for value in x_values)
        if has_negative and has_positive:
            fail("crest carrier triangle crosses the x=0 side boundary")
        if not has_negative and not has_positive:
            fail("crest carrier triangle has no signed x coordinate")
        assigned["right" if has_positive else "left"].append(triangle)

    output: dict[str, dict] = {}
    all_indices: set[int] = set()
    for label, sign in (("left", -1), ("right", 1)):
        triangles = assigned[label]
        indices = sorted({index for triangle in triangles for index in triangle})
        if len(indices) != 163 or len(triangles) != 268:
            fail(f"crest carrier {label} is not exactly 163 vertices/268 triangles")
        if sum(positions[index][0] == 0.0 for index in indices) != 3:
            fail(f"crest carrier {label} does not own exactly three x=0 seam vertices")
        if not all(positions[index][0] * sign >= 0.0 for index in indices):
            fail(f"crest carrier {label} contains the opposite x sign")
        if all_indices.intersection(indices):
            fail("crest carrier side islands share a source vertex")
        all_indices.update(indices)
        remap = {source: target for target, source in enumerate(indices)}
        output[label] = {
            "positions_cm": [positions[index] for index in indices],
            "normals": [group["normals"][index] for index in indices],
            "uv_blender": [group["uv_blender"][index] for index in indices],
            "triangles": [[remap[index] for index in triangle] for triangle in triangles],
        }
    if all_indices != set(range(len(positions))):
        fail("crest carrier split does not cover every source vertex")
    return output


def mesh_object(
    name: str,
    group: dict,
    assigned: bpy.types.Material,
    *,
    uv: bool = False,
    normal_bias_m: float = 0.0,
) -> bpy.types.Object:
    if normal_bias_m:
        if len(group.get("normals", ())) != len(group["positions_cm"]):
            fail(f"{name} cannot apply its visual normal bias")
        vertices = [
            [
                position[axis] * 0.01 + normal[axis] * normal_bias_m
                for axis in range(3)
            ]
            for position, normal in zip(group["positions_cm"], group["normals"])
        ]
    else:
        vertices = [[component * 0.01 for component in row] for row in group["positions_cm"]]
    faces = group["triangles"]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(assigned)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if uv:
        values = group["uv_blender"]
        layer = mesh.uv_layers.new(name=UV_LAYER_NAME)
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                vertex_index = mesh.loops[loop_index].vertex_index
                layer.data[loop_index].uv = values[vertex_index]
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def look_at(camera: bpy.types.Object, target: tuple[float, float, float], roll: float = 0.0) -> None:
    direction = Vector(target) - camera.location
    rotation = direction.to_track_quat("-Z", "Y")
    if roll:
        rotation = Quaternion(direction.normalized(), roll) @ rotation
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = rotation


def camera_basis(camera: bpy.types.Object) -> dict[str, list[float]]:
    rotation = camera.rotation_quaternion
    return {
        "screen_right_world": list(rotation @ Vector((1.0, 0.0, 0.0))),
        "screen_up_world": list(rotation @ Vector((0.0, 1.0, 0.0))),
        "forward_world": list(rotation @ Vector((0.0, 0.0, -1.0))),
    }


def axis_marker(
    name: str,
    target: tuple[float, float, float],
    axis: int,
    assigned: bpy.types.Material,
) -> bpy.types.Object:
    location = list(target)
    location[axis] += 0.09
    scale = [0.003, 0.003, 0.003]
    scale[axis] = 0.09
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    result = bpy.context.object
    result.name = name
    result.data.materials.append(assigned)
    result.hide_render = True
    return result


def render_receipt(receipt_path: Path, expected_schema: str, expected_claim: str) -> None:
    root = receipt_path.parent
    preflight_outputs(root)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != expected_schema:
        fail("receipt schema differs")
    if receipt.get("claim") != expected_claim:
        fail("receipt claim differs")
    geometry_path = root / receipt["geometry"]["file"]
    if sha256(geometry_path) != receipt["geometry"]["sha256"]:
        fail("geometry hash differs from receipt")
    crest_info = receipt["crest"]["review_material"]
    crest_path = root / crest_info["file"]
    if sha256(crest_path) != crest_info["png_sha256"]:
        fail("crest material hash differs from receipt")
    diagnostic_info = receipt["crest"]["uv_diagnostic"]
    diagnostic_path = root / diagnostic_info["file"]
    if sha256(diagnostic_path) != diagnostic_info["png_sha256"]:
        fail("UV diagnostic hash differs from receipt")
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials,
                       bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)

    shell_argb = int(receipt["appearance"]["shell_argb"], 16)
    shell_color = (
        ((shell_argb >> 16) & 0xFF) / 255.0,
        ((shell_argb >> 8) & 0xFF) / 255.0,
        (shell_argb & 0xFF) / 255.0,
        1.0,
    )
    shell = material("Staged Eagles midnight-green shell", shell_color)
    crest = crest_material(crest_path, shell_color)
    diagnostic = crest_material(diagnostic_path, shell_color)
    axis_red = material("Diagnostic world X", (1.0, 0.0, 0.0, 1.0))
    axis_green = material("Diagnostic world Y", (0.0, 1.0, 0.0, 1.0))
    axis_blue = material("Diagnostic world Z", (0.0, 0.3, 1.0, 1.0))

    groups = geometry["groups"]
    # Only the source-declared exterior shell (material 1) and crest carrier
    # (material 2) participate. The other ten material routes, visor, and cage
    # are unresolved context and previously obscured the proof with invented
    # dark/silver assignments.
    shell_object = None
    shell_object = mesh_object("helmet_hi_draw_01", groups["helmet_hi_draw_01"], shell)
    component_contract = receipt["geometry"]["coordinate_proof"]["carrier_components"]
    if component_contract.get("contract") != (
        "signed_x_topology_islands_with_distinct_zero_seams_v2"
    ):
        fail("receipt carrier component contract differs")
    if component_contract.get("component_count") != 2:
        fail("receipt carrier component count differs")
    for label in ("left", "right"):
        row = component_contract.get("sides", {}).get(label, {})
        if (row.get("vertex_count") != 163 or row.get("triangle_count") != 268
                or row.get("x_zero_seam_vertex_count") != 3):
            fail(f"receipt carrier {label} component counts differ")
    carrier_groups = split_carrier_sides(groups["helmet_hi_draw_02"])
    carrier_objects = {
        label: mesh_object(
            f"helmet_hi_draw_02_{label}", carrier_groups[label], crest, uv=True,
            normal_bias_m=CARRIER_VISUAL_NORMAL_BIAS_M,
        )
        for label in ("left", "right")
    }
    if shell_object is None or len(carrier_objects) != 2:
        fail("shell/carrier proof objects were not created")

    world = bpy.data.worlds.new("Neutral proof world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.006, 0.008, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.03
    bpy.context.scene.world = world

    camera_data = bpy.data.cameras.new("Proof camera")
    camera_data.lens = 55.0
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new("Proof camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:  # Blender 4.0/4.1 name; EEVEE_NEXT arrived later.
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 768
    scene.render.resolution_y = 768
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    target = (0.0, 0.045, 0.015)
    axes = (
        axis_marker("World X axis", target, 0, axis_red),
        axis_marker("World Y axis", target, 1, axis_green),
        axis_marker("World Z axis", target, 2, axis_blue),
    )
    views = {
        "side-right": ((0.72, 0.055, 0.018), math.radians(90.0)),
        "side-left": ((-0.72, 0.055, 0.018), math.radians(-90.0)),
        "crown": ((0.0, 0.75, 0.015), 0.0),
        "rear": ((0.0, 0.06, -0.75), 0.0),
    }
    camera_bases = {}
    for name, (location, roll) in views.items():
        camera.location = location
        look_at(camera, target, roll)
        camera_bases[name] = camera_basis(camera)
        scene.render.filepath = str(root / f"helmet-v18-{name}.png")
        bpy.ops.render.render(write_still=True)

    # Bounded diagnostics use the same camera, geometry, and recovered UV layer.
    # They change visibility/material only and never touch the game or main views.
    camera.location = views["side-right"][0]
    look_at(camera, target, views["side-right"][1])
    shell_object.hide_render = True
    carrier_objects["left"].hide_render = True
    scene.render.filepath = str(root / "helmet-v18-debug-carrier-material.png")
    bpy.ops.render.render(write_still=True)
    carrier_objects["right"].data.materials[0] = diagnostic
    scene.render.filepath = str(root / "helmet-v18-debug-carrier-uv.png")
    bpy.ops.render.render(write_still=True)
    carrier_objects["right"].data.materials[0] = crest
    # -90 degrees relative to the measured side-right +90-degree proof roll.
    look_at(camera, target, 0.0)
    scene.render.filepath = str(root / "helmet-v18-debug-carrier-material-roll90.png")
    bpy.ops.render.render(write_still=True)
    carrier_objects["right"].hide_render = True
    for axis in axes:
        axis.hide_render = False
    look_at(camera, target, 0.0)
    scene.render.filepath = str(root / "helmet-v18-debug-camera-axes.png")
    bpy.ops.render.render(write_still=True)
    for axis in axes:
        axis.hide_render = True
    carrier_objects["right"].hide_render = False
    carrier_objects["left"].hide_render = False
    shell_object.hide_render = False

    blend = root / "helmet-v18-proof.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    completion = {
        "schema": "apf2k8_exact_helmet_blender_stage/v2",
        "source_claim": receipt["claim"],
        "blender_version": bpy.app.version_string,
        "shading_contract": "unlit_emission_exact_palette_no_lights_v1",
        "physical_light_count": len(bpy.data.lights),
        "visible_source_draws": [1, 2],
        "uv_binding": f"explicit:{UV_LAYER_NAME}",
        "texture_extension": "CLIP",
        "carrier_material_background_contract": (
            "inactive_black_mask_pixels_simulated_as_exact_shell_rgb_opaque_v1"
        ),
        "carrier_visual_normal_bias": {
            "meters": CARRIER_VISUAL_NORMAL_BIAS_M,
            "purpose": "render-only coplanar shell depth separation",
            "game_geometry_changed": False,
        },
        "carrier_component_contract": {
            "split": "signed_x_topology_islands_with_distinct_zero_seams_v2",
            "component_count": 2,
            "left": {
                "vertex_count": 163, "triangle_count": 268,
                "x_zero_seam_vertex_count": 3,
            },
            "right": {
                "vertex_count": 163, "triangle_count": 268,
                "x_zero_seam_vertex_count": 3,
            },
            "main_visibility": ["left", "right"],
            "side_diagnostic_visibility": ["right"],
        },
        "camera_contract": "lens55mm_side0.72m_crown_rear0.75m_v1",
        "camera_axis_contract": (
            "right_roll_plus_pi_over_2_left_minus_pi_over_2_"
            "crown_rear_zero_v2"
        ),
        "camera_bases": camera_bases,
        "blend_scene": {"file": blend.name, "sha256": sha256(blend)},
        "views": {
            name: {
                "file": f"helmet-v18-{name}.png",
                "sha256": sha256(root / f"helmet-v18-{name}.png"),
            }
            for name in views
        },
        "debug_views": {
            name: {
                "file": f"helmet-v18-{name}.png",
                "sha256": sha256(root / f"helmet-v18-{name}.png"),
            }
            for name in ("debug-carrier-material", "debug-carrier-uv",
                         "debug-carrier-material-roll90", "debug-camera-axes")
        },
    }
    (root / "helmet-v18-blender-stage.json").write_text(
        json.dumps(completion, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("APF_EXACT_HELMET_BLENDER_RENDER_PASS views=4")


def main() -> None:
    render_receipt(
        arguments(),
        "apf2k8_exact_helmet_static_visual_proof/v2",
        "exact_v18_editor_build_static_asset_space_visualization",
    )


if __name__ == "__main__":
    _receipt: Path | None = None
    try:
        _receipt = arguments()
        main()
    except BaseException:
        write_error_log(_receipt, traceback.format_exc())
        raise
