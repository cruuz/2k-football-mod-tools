#!/usr/bin/env python3
"""Background-only Blender stage for the shell-candidate visual proof."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
import traceback

import bpy
from mathutils import Quaternion, Vector


SCHEMA = "apf2k8_helmet_shell_candidate_visual_proof/v1"
EXPECTED_SCNE_SHA256 = "ef04ef4418e4df555d9418db2f6083c7852802428aae0a15dbf81518bff3b5ef"
UV_LAYER = "Shell candidate crest UV"
VIEW_NAMES = ("side-right", "side-left", "front-crown", "rear", "top")
LOW_VIEW_NAME = "lod-low-side-right"


def fail(message: str) -> None:
    raise RuntimeError(f"APF shell candidate Blender proof: {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_argument() -> Path:
    if "--" not in sys.argv:
        fail("missing receipt argument")
    values = sys.argv[sys.argv.index("--") + 1 :]
    if len(values) != 1:
        fail("expected one receipt argument")
    path = Path(values[0]).resolve()
    if not path.is_file():
        fail("receipt is unavailable")
    return path


def srgb_to_linear(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def emission_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    # Node socket colors are scene-linear, while PNG texture samples marked
    # sRGB are decoded to scene-linear by Blender. Convert solid shell colors
    # too, otherwise identical RGB bytes render as a visible carrier halo.
    linear_color = tuple(srgb_to_linear(channel) for channel in color[:3]) + (color[3],)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = linear_color
    emission.inputs["Strength"].default_value = 1.0
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def image_material(path: Path) -> bpy.types.Material:
    material = bpy.data.materials.new("Exact Eagles candidate material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    image = nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(str(path), check_existing=False)
    image.image.colorspace_settings.name = "sRGB"
    image.interpolation = "Linear"
    image.extension = "EXTEND"
    uv_map = nodes.new("ShaderNodeUVMap")
    uv_map.uv_map = UV_LAYER
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Strength"].default_value = 1.0
    material.node_tree.links.new(uv_map.outputs["UV"], image.inputs["Vector"])
    material.node_tree.links.new(image.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def mesh_object(name: str, group: dict, material: bpy.types.Material, *, uv: bool) -> bpy.types.Object:
    vertices = [[component * 0.01 for component in row] for row in group["positions_cm"]]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], group["triangles"])
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    if uv:
        layer = mesh.uv_layers.new(name=UV_LAYER)
        for polygon in mesh.polygons:
            for loop_index in polygon.loop_indices:
                vertex = mesh.loops[loop_index].vertex_index
                layer.data[loop_index].uv = group["uv_blender"][vertex]
    mesh.update(calc_edges=True)
    result = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(result)
    return result


def split_carrier(
    group: dict, *, expected_vertices: int, expected_faces: int,
) -> dict[str, dict]:
    positions = group["positions_cm"]
    assigned = {"left": [], "right": []}
    for triangle in group["triangles"]:
        signs = {0 if positions[index][0] == 0 else (1 if positions[index][0] > 0 else -1) for index in triangle}
        if -1 in signs and 1 in signs:
            fail("carrier triangle crosses sides")
        assigned["right" if 1 in signs else "left"].append(triangle)
    output = {}
    for label in ("left", "right"):
        faces = assigned[label]
        used = sorted({index for face in faces for index in face})
        if len(used) != expected_vertices or len(faces) != expected_faces:
            fail(f"{label} carrier counts differ")
        remap = {source: target for target, source in enumerate(used)}
        output[label] = {
            "positions_cm": [positions[index] for index in used],
            "uv_blender": [group["uv_blender"][index] for index in used],
            "triangles": [[remap[index] for index in face] for face in faces],
        }
    return output


def look_at(camera: bpy.types.Object, target: tuple[float, float, float], roll: float = 0.0) -> None:
    direction = Vector(target) - camera.location
    rotation = direction.to_track_quat("-Z", "Y")
    if roll:
        rotation = Quaternion(direction.normalized(), roll) @ rotation
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = rotation


def render() -> None:
    receipt_path = receipt_argument()
    root = receipt_path.parent
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != SCHEMA:
        fail("receipt schema differs")
    if receipt.get("source", {}).get("candidate_scne_sha256") != EXPECTED_SCNE_SHA256:
        fail("candidate hash differs")
    geometry_path = root / receipt["geometry"]["file"]
    material_path = root / receipt["crest"]["material"]["file"]
    if sha256(geometry_path) != receipt["geometry"]["sha256"]:
        fail("geometry hash differs")
    if sha256(material_path) != receipt["crest"]["material"]["sha256"]:
        fail("material hash differs")
    for name in VIEW_NAMES:
        if (root / f"helmet-shell-candidate-{name}.png").exists():
            fail("refusing to overwrite a rendered view")

    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    shell_material = emission_material("Midnight green shell", (0.0, 76 / 255, 84 / 255, 1.0))
    crest_material = image_material(material_path)
    high = geometry["lods"]["helmet_hi"]
    low = geometry["lods"]["helmet_lo"]
    high_shell = mesh_object("helmet_hi_shell", high["shell"], shell_material, uv=False)
    high_carrier_groups = split_carrier(
        high["carrier"], expected_vertices=161, expected_faces=258
    )
    high_carriers = {
        label: mesh_object(f"helmet_hi_carrier_{label}", group, crest_material, uv=True)
        for label, group in high_carrier_groups.items()
    }
    low_shell = mesh_object("helmet_lo_shell", low["shell"], shell_material, uv=False)
    low_carrier_groups = split_carrier(
        low["carrier"], expected_vertices=56, expected_faces=78
    )
    low_carriers = {
        label: mesh_object(f"helmet_lo_carrier_{label}", group, crest_material, uv=True)
        for label, group in low_carrier_groups.items()
    }
    low_shell.hide_render = True
    for carrier in low_carriers.values():
        carrier.hide_render = True

    world = bpy.data.worlds.new("Proof world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.003, 0.005, 0.008, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.02
    bpy.context.scene.world = world
    camera_data = bpy.data.cameras.new("Proof camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 0.30
    camera = bpy.data.objects.new("Proof camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene = bpy.context.scene
    scene.camera = camera
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.filter_size = 1.5
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    if hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 128

    target = (0.0, 0.065, 0.01)
    views = {
        "side-right": ((0.46, 0.065, 0.01), math.pi / 2, (True, False)),
        "side-left": ((-0.46, 0.065, 0.01), -math.pi / 2, (False, True)),
        "front-crown": ((0.0, 0.24, 0.42), 0.0, (True, True)),
        "rear": ((0.0, 0.065, -0.46), 0.0, (True, True)),
        "top": ((0.0, 0.49, 0.01), 0.0, (True, True)),
    }
    camera_rows = {}
    for name, (location, roll, visible) in views.items():
        high_carriers["right"].hide_render = not visible[0]
        high_carriers["left"].hide_render = not visible[1]
        camera.location = location
        look_at(camera, target, roll)
        scene.render.filepath = str(root / f"helmet-shell-candidate-{name}.png")
        bpy.ops.render.render(write_still=True)
        camera_rows[name] = {"location": list(location), "roll_radians": roll}
    high_shell.hide_render = True
    for carrier in high_carriers.values():
        carrier.hide_render = True
    low_shell.hide_render = False
    low_carriers["right"].hide_render = False
    low_carriers["left"].hide_render = True
    location, roll, _visible = views["side-right"]
    camera.location = location
    look_at(camera, target, roll)
    scene.render.filepath = str(
        root / f"helmet-shell-candidate-{LOW_VIEW_NAME}.png"
    )
    bpy.ops.render.render(write_still=True)
    camera_rows[LOW_VIEW_NAME] = {"location": list(location), "roll_radians": roll}
    high_shell.hide_render = False
    for carrier in high_carriers.values():
        carrier.hide_render = False
    low_shell.hide_render = True
    for carrier in low_carriers.values():
        carrier.hide_render = True
    blend_path = root / "helmet-shell-candidate.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    stage = {
        "schema": "apf2k8_helmet_shell_candidate_blender_stage/v1",
        "source_scne_sha256": EXPECTED_SCNE_SHA256,
        "blender_version": bpy.app.version_string,
        "background_render": bpy.app.background,
        "carrier_visual_normal_bias_m": 0.0,
        "texture_interpolation": "Linear",
        "texture_extension": "EXTEND",
        "antialiasing": "EEVEE temporal antialiasing plus Gaussian 1.5px filter",
        "camera": camera_rows,
        "blend": {"file": blend_path.name, "sha256": sha256(blend_path)},
        "views": {
            name: {
                "file": f"helmet-shell-candidate-{name}.png",
                "sha256": sha256(root / f"helmet-shell-candidate-{name}.png"),
            }
            for name in (*VIEW_NAMES, LOW_VIEW_NAME)
        },
    }
    (root / "helmet-shell-candidate-blender-stage.json").write_text(
        json.dumps(stage, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("APF_HELMET_SHELL_CANDIDATE_RENDER_PASS views=6")


if __name__ == "__main__":
    try:
        render()
    except BaseException:
        receipt = receipt_argument()
        (receipt.parent / "helmet-shell-candidate-blender-error.log").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
        raise
