"""Blender (4.0) headless: render the NFL 2K5 hi_head helmet with a helmet texture at a mini-helmet camera (job u3).
Usage: blender -b -P tools/nfl2k5_mini_helmet_blender.py -- JOB.json   (tools/nfl2k5_team_logos_2026.py minis writes JOB)
JOB: {gltf, size, items: [{texture00, facemask_rgb, shell: "A"|"B"|"C", facemask: "FACEMASK07", ambient, sun,
      sun_rot | sun_cam, roughness, specular, views: [{yaw, pitch, roll, dist, fov, target:[x,y,z], shift_x, out}]}]}
A single-item job may put the item's keys at the top level (the older format). The model is imported once and each
item swaps the texture, the facemask colour, the visible parts and the lighting, so one process renders many teams.
"""
import bpy, json, math, sys
from mathutils import Vector, Euler, Matrix

args = sys.argv[sys.argv.index("--") + 1:]
job = json.load(open(args[0]))
items = job.get("items") or [job]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=job["gltf"])
obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")

parts = {}   # material name -> (base name, mix node, bsdf node, texture node or None)
for slot in obj.material_slots:
    m = slot.material
    if m is None or m.name in parts:
        continue
    name = m.name.split(".")[0]
    m.use_nodes = True
    m.blend_method = "CLIP"
    nodes, links = m.node_tree.nodes, m.node_tree.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    tr = nodes.new("ShaderNodeBsdfTransparent")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(tr.outputs[0], mix.inputs[1])
    links.new(bsdf.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs[0])
    tex = None
    if name.startswith("FACEMASK"):
        bsdf.inputs["Metallic"].default_value = 0.3
    else:
        tex = nodes.new("ShaderNodeTexImage")
        tex.interpolation = "Linear"
        links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    parts[m.name] = (name, mix, bsdf, tex)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = True
scene.render.resolution_x = scene.render.resolution_y = job.get("size", items[0].get("size", 256))
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); scene.world = world
world.use_nodes = True
background = world.node_tree.nodes["Background"]
_wn, _wl = world.node_tree.nodes, world.node_tree.links
_coord = _wn.new("ShaderNodeTexCoord")
_sep = _wn.new("ShaderNodeSeparateXYZ")
_map = _wn.new("ShaderNodeMapRange")
ramp = _wn.new("ShaderNodeMix")
ramp.data_type = "RGBA"
_wl.new(_coord.outputs["Generated"], _sep.inputs[0])
_wl.new(_sep.outputs["Z"], _map.inputs["Value"])
_map.inputs["From Min"].default_value = -1.0
_map.inputs["From Max"].default_value = 1.0
_wl.new(_map.outputs["Result"], ramp.inputs[0])
_wl.new(ramp.outputs[2], background.inputs[0])
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
images = {}

for item in items:
    shell = item.get("shell", "A")
    keep = {f"HI_HELMET_{shell}", "LOGO_helmet", "LOGO_nfl", item.get("facemask", "FACEMASK07")}
    if item.get("accessories", True):
        keep.add(f"HELMET_{shell}_accessories")
    if shell == "C":
        keep |= {"LOGO_helmet_C"}
    path = item["texture00"]
    if path not in images:
        images[path] = bpy.data.images.load(path)
    for name, mix, bsdf, tex in parts.values():
        mix.inputs[0].default_value = 1.0 if name in keep else 0.0
        bsdf.inputs["Roughness"].default_value = item.get("roughness", 0.25)
        bsdf.inputs["Specular IOR Level"].default_value = item.get("specular", 0.6)
        bsdf.inputs["Coat Weight"].default_value = item.get("coat", 0.0) if tex is not None else 0.0
        bsdf.inputs["Coat Roughness"].default_value = item.get("coat_roughness", 0.03)
        if tex is not None:
            tex.image = images[path]
        else:
            r, g, b = item["facemask_rgb"]
            bsdf.inputs["Base Color"].default_value = (r / 255, g / 255, b / 255, 1)
    background.inputs[1].default_value = item.get("ambient", 0.6)
    # optional sky gradient: world light bright from above, dark from below ([bottom, top] strengths)
    lo, hi = item.get("ambient_gradient", [1.0, 1.0])
    bottom = item.get("world_bottom", [lo, lo, lo])
    top = item.get("world_top", [hi, hi, hi])
    ramp.inputs[6].default_value = (*bottom, 1)
    ramp.inputs[7].default_value = (*top, 1)
    _map.inputs["From Min"].default_value, _map.inputs["From Max"].default_value = item.get("horizon", [-1.0, 1.0])
    sun.data.energy = item.get("sun", 3.0)
    sun.rotation_euler = Euler([math.radians(v) for v in item.get("sun_rot", [40, 0, -30])])
    for view in item["views"]:
        t = Vector(view["target"])
        yaw, pitch, dist = math.radians(view["yaw"]), math.radians(view["pitch"]), view["dist"]
        # glTF Y-up imported into Blender Z-up: the helmet faces -Y (front) after import
        pos = t + Vector((dist * math.cos(pitch) * math.sin(yaw), -dist * math.cos(pitch) * math.cos(yaw), dist * math.sin(pitch)))
        cam.location = pos
        rot = (t - pos).to_track_quat("-Z", "Y").to_matrix().to_4x4()
        rot = rot @ Matrix.Rotation(math.radians(view.get("roll", 0)), 4, "Z")
        cam.rotation_euler = rot.to_euler()
        if "sun_cam" in item:
            # key light fixed to the camera: [tilt about the camera X, turn about the camera Y] in degrees; 0,0 = from
            # the camera itself (a sun shines down its local -Z)
            rx, ry = item["sun_cam"]
            sun.rotation_euler = (rot @ Matrix.Rotation(math.radians(rx), 4, "X") @ Matrix.Rotation(math.radians(ry), 4, "Y")).to_euler()
        cam.data.angle = math.radians(view.get("fov", 30))
        cam.data.shift_x = view.get("shift_x", 0.0)
        cam.data.shift_y = view.get("shift_y", 0.0)
        scene.render.filepath = view["out"]
        bpy.ops.render.render(write_still=True)
