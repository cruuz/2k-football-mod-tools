"""Uniform audit renderer, derived from the k2 Blender (4.0) card renderer, on the Studio's own hi_body / hi_head exports.

Usage: blender -b -P tools/b765/u1_blender.py -- JOB.json

Run this authoring-only helper with Blender's embedded Python. Blender supplies
bpy and mathutils; this file is not shipped with Studio and these modules are
not Studio pip dependencies.

JOB = {
  "head": gltf, "body": gltf | null, "head_offset": [x, y, z] (applied when both are loaded),
  "items": [ {
     "tex": {material base name or prefix*: png},        # swapped per item, the model is loaded once
     "facemask_rgb": [r, g, b], "facemask": "FACEMASK07", "shell": "A",
     "skin": [r, g, b], "shoe": [r, g, b], "turtleneck": [r, g, b],
     "hide": [material names or prefix*],                 # hidden for every view of this item
     "light": {...},                                      # lighting preset keys (see LIGHT_DEFAULT)
     "views": [ {"yaw", "pitch", "roll", "dist", "fov", "target": [x, y, z], "shift_x", "shift_y",
                 "size": [w, h], "out": png, "parts": "head" | "body" | "all", "hide": [...],
                 "light": {...}, "samples": n} ],
     "fit": {...}   # optional: Nelder-Mead over camera parameters against a target mask (see fit())
  } ]
}
Camera: looks at target from yaw/pitch at dist (yaw 0 = from the front, the model faces -Y; yaw 90 = from the
model's left side, so the front points to the image's left), then roll about the view axis, lens shift in frame units.
Materials: textured parts use Principled BSDF (helmet parts glossy with a clear coat), alpha CLIP.
"""
import bpy, json, math, sys, os
import numpy as np
from mathutils import Vector, Euler, Matrix

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
bpy.ops.wm.read_factory_settings(use_empty=True)

objs = []
for key in ("body", "head"):
    if not job.get(key):
        continue
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=job[key])
    new = [o for o in bpy.context.scene.objects if o not in before]
    for o in new:
        if o.type == "MESH" and o.name.startswith("Icosphere"):
            o.hide_render = True
        if key == "head" and job.get("body") and o.parent is None:
            o.location = Vector(job.get("head_offset", [0.0, 0.0455, 0.339])) + o.location
    objs += [(key, o) for o in new if o.type == "MESH" and not o.name.startswith("Icosphere")]

# shell C with hm's modern details (edbff6021): the named submeshes come from hm's product-scene dump (game units),
# replacing the glTF's retail ones (their materials are renamed ORIG_*, which set_item never shows)
rep = job.get("replace_parts")
if rep:
    D = json.load(open(rep["json"]))
    names = list(rep["names"])
    for key, o in objs:
        for slot in o.material_slots:
            m = slot.material
            if m is not None and m.name.split(".")[0] in names:
                m.name = "ORIG_" + m.name
    sc = float(rep.get("scale", 0.01)); off = rep.get("offset", [0.0, 0.0455, 0.339])
    for nm in names:
        d = D[nm]
        me = bpy.data.meshes.new(nm)
        verts = [(p[0] * sc + off[0], -p[2] * sc + off[1], p[1] * sc + off[2]) for p in d["pos"]]
        me.from_pydata(verts, [], [tuple(t) for t in d["tris"] if len(set(t)) == 3])
        me.update()
        if d.get("uv"):
            uvl = me.uv_layers.new(name="uv")
            for poly in me.polygons:
                for li in poly.loop_indices:
                    u, v = d["uv"][me.loops[li].vertex_index]
                    uvl.data[li].uv = (u, 1.0 - v)
        for poly in me.polygons:
            poly.use_smooth = True
        if d.get("nrm"):
            nv = [(n[0], -n[2], n[1]) for n in d["nrm"]]
            if hasattr(me, "use_auto_smooth"):
                me.use_auto_smooth = True
            me.normals_split_custom_set_from_vertices(nv)
        me.materials.append(bpy.data.materials.new(nm))
        ob = bpy.data.objects.new(nm, me)
        bpy.context.scene.collection.objects.link(ob)
        objs.append(("head", ob))
        print("REPLACED", nm, len(d["pos"]), "verts", flush=True)


def pose_arms(deg):
    """u7's arm pose: rotate each humerus down about the world Y axis through its head (T-pose to arms down)."""
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE" and any(b.name.endswith("lhumerus") for b in o.data.bones)]
    for arm in arms:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="POSE")
        for side, sign in (("l", 1.0), ("r", -1.0)):
            pb = next(b for b in arm.pose.bones if b.name.endswith(f"{side}humerus"))
            M = arm.matrix_world @ pb.matrix
            head = M.translation.copy()
            R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(sign * deg), 4, "Y") @ Matrix.Translation(-head)
            pb.matrix = arm.matrix_world.inverted() @ R @ M
            bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode="OBJECT")


if job.get("arms_down"):
    pose_arms(job["arms_down"])

# body-type morphs (shape keys of the Studio export: jersey_shoulderpad_big, jersey_gut_big, pants_thighpad_thick, ...)
for key, o in objs:
    sk = o.data.shape_keys
    if sk is None:
        continue
    for kb in sk.key_blocks:
        if kb.name in job.get("morphs", {}):
            kb.value = float(job["morphs"][kb.name])
            print("MORPH", o.name, kb.name, kb.value)

images = {}


def img(p):
    if p not in images:
        images[p] = bpy.data.images.load(p)
        images[p].alpha_mode = "STRAIGHT"
    return images[p]


def lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def match(name, pats):
    return any(name == p or (p.endswith("*") and name.startswith(p[:-1])) for p in pats)


# one material rig per material: transparent/principled mix, optional image, optional UV mapping
parts = {}
for key, obj in objs:
    for slot in obj.material_slots:
        m = slot.material
        if m is None or m.name in parts:
            continue
        name = m.name.split(".")[0]
        m.use_nodes = True
        # Helmet decals share the head object; alpha blending can sort them
        # behind its opaque shell in EEVEE. Clip them without changing the
        # blended body numerals and nameplates.
        m.blend_method = ("CLIP" if name.startswith("NUMBER_helmet") else
                          "BLEND" if name.startswith("NUMBER") or name.startswith("PLAYERNAME") else "CLIP")
        m.shadow_method = "CLIP"
        m.show_transparent_back = False
        nodes, links = m.node_tree.nodes, m.node_tree.links
        for n in list(nodes):
            nodes.remove(n)
        out = nodes.new("ShaderNodeOutputMaterial")
        mix = nodes.new("ShaderNodeMixShader")
        tr = nodes.new("ShaderNodeBsdfTransparent")
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        emit = nodes.new("ShaderNodeEmission")
        mixe = nodes.new("ShaderNodeMixShader")     # 0 = shaded, 1 = emission (flat texture colour, or white masks)
        white = nodes.new("ShaderNodeMix"); white.data_type = "RGBA"   # factor 1 = white
        white.inputs[7].default_value = (1, 1, 1, 1)
        links.new(white.outputs[2], emit.inputs["Color"])
        links.new(bsdf.outputs[0], mixe.inputs[1]); links.new(emit.outputs[0], mixe.inputs[2])
        links.new(tr.outputs[0], mix.inputs[1]); links.new(mixe.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], out.inputs[0])
        tex = nodes.new("ShaderNodeTexImage")
        tex.interpolation = "Linear"
        geo = nodes.new("ShaderNodeNewGeometry")
        dark = nodes.new("ShaderNodeMix"); dark.data_type = "RGBA"; dark.blend_type = "MULTIPLY"
        dark.inputs[7].default_value = (0.35, 0.35, 0.35, 1)
        links.new(geo.outputs["Backfacing"], dark.inputs[0])
        mp = None
        if name.startswith("NUMBER"):
            uvn = nodes.new("ShaderNodeUVMap"); mp = nodes.new("ShaderNodeMapping")
            links.new(uvn.outputs["UV"], mp.inputs["Vector"]); links.new(mp.outputs["Vector"], tex.inputs["Vector"])
            tex.extension = "CLIP"
        parts[m.name] = {"name": name, "key": key, "mix": mix, "mixe": mixe, "bsdf": bsdf, "tex": tex, "links": links,
                         "map": mp, "mat": m, "white": white, "dark": dark}

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
wn, wl = world.node_tree.nodes, world.node_tree.links
background = wn["Background"]
coord = wn.new("ShaderNodeTexCoord"); sep = wn.new("ShaderNodeSeparateXYZ"); mapr = wn.new("ShaderNodeMapRange")
ramp = wn.new("ShaderNodeMix"); ramp.data_type = "RGBA"
wl.new(coord.outputs["Generated"], sep.inputs[0]); wl.new(sep.outputs["Z"], mapr.inputs["Value"])
wl.new(mapr.outputs["Result"], ramp.inputs[0]); wl.new(ramp.outputs[2], background.inputs[0])
sun = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN")); scene.collection.objects.link(sun)
rim = bpy.data.objects.new("rim", bpy.data.lights.new("rim", "SUN")); scene.collection.objects.link(rim)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam

LIGHT_DEFAULT = {"ambient": 1.0, "world_bottom": [0.05, 0.05, 0.05], "world_top": [1.0, 1.0, 1.0], "horizon": [-1.0, 1.0],
                 "sun": 2.0, "sun_cam": [20, -25], "rim": 0.0, "rim_cam": [30, 150],
                 "helmet_roughness": 0.3, "helmet_specular": 0.5, "helmet_coat": 1.0, "helmet_coat_roughness": 0.03,
                 "cloth_roughness": 0.55, "cloth_specular": 0.25, "facemask_metallic": 0.3}


def set_item(item):
    tex = item.get("tex", {})
    hide = item.get("hide", [])
    shell = item.get("shell", "A")
    fm_part = item.get("facemask", "FACEMASK07")
    colours = {"SKIN": item.get("skin", [140, 100, 70]), "SHOE": item.get("shoe", [235, 235, 235]),
               "FACEMASK": item.get("facemask_rgb", [128, 128, 128]), "HI_turtleneck": item.get("turtleneck", [230, 230, 230])}
    for p in parts.values():
        name, bsdf, t = p["name"], p["bsdf"], p["tex"]
        src = tex.get(name)
        if src is None:
            for k, v in tex.items():
                if k.endswith("*") and name.startswith(k[:-1]):
                    src = v; break
        # detach the image unless this part is textured
        for l in list(p["links"]):
            if l.from_node == t:
                p["links"].remove(l)
        visible = True
        p["helmet"] = name.startswith("HI_HELMET") or name.startswith("LOGO") or name.startswith("HELMET")
        if match(name, hide):
            visible = False
        elif src:
            t.image = img(src)
            if name.startswith("UNIF_jersey") or name.startswith("UNIF_sleeve") or name.startswith("NECKROLL"):
                p["links"].new(t.outputs["Color"], p["dark"].inputs[6])
                p["links"].new(p["dark"].outputs[2], bsdf.inputs["Base Color"])
            else:
                p["links"].new(t.outputs["Color"], bsdf.inputs["Base Color"])
            p["links"].new(t.outputs["Color"], p["white"].inputs[6])
            p["links"].new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            if p["map"] is not None:
                sc = None
                for k, v in item.get("uv_scale", {}).items():
                    if name == k or (k.endswith("*") and name.startswith(k[:-1])):
                        sc = v
                sc = sc or [1, 1]
                du = float(item.get("uv_offset", {}).get(name, 0.0))    # the game's material U offset (+0x28)
                p["map"].inputs["Scale"].default_value = (sc[0], sc[1], 1.0)
                p["map"].inputs["Location"].default_value = (du, 1.0 - sc[1], 0.0)
        elif name.startswith("FACEMASK"):
            visible = name == fm_part
            bsdf.inputs["Base Color"].default_value = (*[lin(c) for c in colours["FACEMASK"]], 1)
            bsdf.inputs["Alpha"].default_value = 1.0
        elif name.startswith("SKIN") and not name.startswith("SKIN_L_hand_") and not name.startswith("SKIN_R_hand_"):
            bsdf.inputs["Base Color"].default_value = (*[lin(c) for c in colours["SKIN"]], 1)
            bsdf.inputs["Alpha"].default_value = 1.0
        elif name in ("SHOE_L", "SHOE_R"):
            bsdf.inputs["Base Color"].default_value = (*[lin(c) for c in colours["SHOE"]], 1)
            bsdf.inputs["Alpha"].default_value = 1.0
        elif name == "HI_turtleneck":
            bsdf.inputs["Base Color"].default_value = (*[lin(c) for c in colours["HI_turtleneck"]], 1)
            bsdf.inputs["Alpha"].default_value = 1.0
        else:
            visible = False
        if not src:
            p["white"].inputs[6].default_value = tuple(bsdf.inputs["Base Color"].default_value)
        if name.startswith("HI_HELMET_") and name not in ("HI_HELMET_flag", f"HI_HELMET_{shell}"):
            visible = False
        if name.startswith("HELMET_") and name != f"HELMET_{shell}_accessories":
            visible = False
        if name == "LOGO_helmet_C" and shell != "C":
            visible = False
        if name == "LOGO_helmet" and shell == "C":
            visible = False
        p["visible"] = visible


def set_light(light, rot):
    L = dict(LIGHT_DEFAULT); L.update(light or {})
    background.inputs[1].default_value = L["ambient"]
    ramp.inputs[6].default_value = (*L["world_bottom"], 1)
    ramp.inputs[7].default_value = (*L["world_top"], 1)
    mapr.inputs["From Min"].default_value, mapr.inputs["From Max"].default_value = L["horizon"]
    sun.data.energy = L["sun"]
    rx, ry = L["sun_cam"]
    sun.rotation_euler = (rot @ Matrix.Rotation(math.radians(rx), 4, "X") @ Matrix.Rotation(math.radians(ry), 4, "Y")).to_euler()
    rim.data.energy = L["rim"]
    rx, ry = L["rim_cam"]
    rim.rotation_euler = (rot @ Matrix.Rotation(math.radians(rx), 4, "X") @ Matrix.Rotation(math.radians(ry), 4, "Y")).to_euler()
    for p in parts.values():
        b = p["bsdf"]
        if p.get("helmet"):
            b.inputs["Roughness"].default_value = L["helmet_roughness"]
            b.inputs["Specular IOR Level"].default_value = L["helmet_specular"]
            b.inputs["Coat Weight"].default_value = L["helmet_coat"]
            b.inputs["Coat Roughness"].default_value = L["helmet_coat_roughness"]
        elif p["name"].startswith("FACEMASK"):
            b.inputs["Metallic"].default_value = L["facemask_metallic"]
            b.inputs["Roughness"].default_value = 0.35
        else:
            b.inputs["Roughness"].default_value = L["cloth_roughness"]
            b.inputs["Specular IOR Level"].default_value = L["cloth_specular"]
            b.inputs["Coat Weight"].default_value = 0.0


def place_camera(view):
    t = Vector(view["target"])
    yaw, pitch, dist = math.radians(view["yaw"]), math.radians(view["pitch"]), view["dist"]
    pos = t + Vector((dist * math.cos(pitch) * math.sin(yaw), -dist * math.cos(pitch) * math.cos(yaw), dist * math.sin(pitch)))
    cam.location = pos
    rot = (t - pos).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    rot = rot @ Matrix.Rotation(math.radians(view.get("roll", 0.0)), 4, "Z")
    cam.rotation_euler = rot.to_euler()
    cam.data.angle = math.radians(view.get("fov", 20))
    cam.data.shift_x = view.get("shift_x", 0.0)
    cam.data.shift_y = view.get("shift_y", 0.0)
    return rot


def render(item, view, out, mask=False, flat=False):
    parts_mode = view.get("parts", "all")
    for key, o in objs:
        o.hide_render = (parts_mode == "head" and key == "body") or (parts_mode == "body" and key == "head")
    vh = view.get("hide", [])
    for p in parts.values():
        vis = p["visible"] and not match(p["name"], vh)
        p["mix"].inputs[0].default_value = 1.0 if vis else 0.0
        p["mixe"].inputs[0].default_value = 1.0 if (mask or flat) else 0.0
        p["white"].inputs[0].default_value = 1.0 if mask else 0.0
    rot = place_camera(view)
    set_light(dict(item.get("light", {}), **view.get("light", {})), rot)
    w, h = view.get("size", job.get("size", [256, 256]))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.eevee.taa_render_samples = view.get("samples", 1 if mask else (4 if flat else 32))
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)


def read_rgba(path):
    im = bpy.data.images.load(path)
    im.colorspace_settings.name = "Non-Color"   # raw sRGB bytes / 255, like PIL
    w, h = im.size
    px = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(px)
    bpy.data.images.remove(im)
    return px.reshape(h, w, 4)[::-1]


def read_alpha(path):
    return read_rgba(path)[..., 3]


def ncc(a, b, m):
    if m.sum() < 50:
        return 0.0
    out = []
    for c in range(3):
        x = a[..., c][m]; y = b[..., c][m]
        x = x - x.mean(); y = y - y.mean()
        d = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
        out.append(float((x * y).sum()) / d if d > 1e-9 else 0.0)
    return sum(out) / 3.0


def morph(a, k, op):
    if k <= 1:
        return a
    pad = k // 2
    p = np.pad(a, pad, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(p, (k, k))
    return win.min(axis=(2, 3)) if op == "min" else win.max(axis=(2, 3))


def opening(a, k):
    return morph(morph(a, k, "min"), k, "max")


def fit(item, spec):
    """Nelder-Mead over the named camera parameters; loss = 1 - IoU of the opened masks inside the region rows."""
    from PIL import Image  # noqa: F401  (Blender's python has no PIL; target masks come as .npy)
    target = np.load(spec["target_npy"]).astype(np.float32)          # H x W x 4 (RGBA 0..1) or H x W alpha
    trgb = target[..., :3] if target.ndim == 3 else None
    talpha = target[..., 3] if target.ndim == 3 else target
    region = np.load(spec["region_npy"]).astype(bool) if spec.get("region_npy") else np.ones(talpha.shape, bool)
    k = spec.get("open", 5)
    wc = spec.get("colour_weight", 0.0) if trgb is not None else 0.0
    tgt = opening(talpha > 0.5, k) & region
    tcore = morph(talpha > 0.5, 5, "min") & region
    base = dict(spec["view"])
    names = spec["params"]
    x0 = np.array([base[n] for n in names], np.float64)
    steps = np.array([spec["steps"][n] for n in names], np.float64)
    tmp = spec["tmp"]
    cache = {}

    def loss(x):
        key = tuple(np.round(x, 5))
        if key in cache:
            return cache[key]
        v = dict(base); v.update({n: float(val) for n, val in zip(names, x)})
        render(item, v, tmp, mask=wc == 0.0, flat=wc > 0.0)
        rgba = read_rgba(tmp)
        raw = rgba[..., 3] > 0.5
        a = opening(raw, k) & region
        inter = float((a & tgt).sum()); union = float((a | tgt).sum())
        val = 1.0 - inter / max(union, 1.0)
        if wc > 0.0:
            m = morph(raw, 5, "min") & tcore
            val += wc * (1.0 - ncc(rgba[..., :3], trgb, m))
        cache[key] = val
        return val

    n = len(x0)
    simplex = [x0] + [x0 + np.eye(n)[i] * steps[i] for i in range(n)]
    vals = [loss(s) for s in simplex]
    for it in range(spec.get("iters", 150)):
        order = np.argsort(vals); simplex = [simplex[i] for i in order]; vals = [vals[i] for i in order]
        if it % 10 == 0:
            print("FIT", it, round(vals[0], 5), [round(v, 4) for v in simplex[0]], flush=True)
        c = np.mean(simplex[:-1], axis=0)
        xr = c + (c - simplex[-1]); fr = loss(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - simplex[-1]); fe = loss(xe)
            simplex[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            simplex[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (simplex[-1] - c); fc = loss(xc)
            if fc < vals[-1]:
                simplex[-1], vals[-1] = xc, fc
            else:
                simplex = [simplex[0]] + [simplex[0] + 0.5 * (s - simplex[0]) for s in simplex[1:]]
                vals = [vals[0]] + [loss(s) for s in simplex[1:]]
        if max(vals) - min(vals) < spec.get("tol", 1e-4) and it > 20:
            break
    i = int(np.argmin(vals))
    best = dict(base); best.update({nm: float(v) for nm, v in zip(names, simplex[i])})
    json.dump({"loss": float(vals[i]), "iou": 1.0 - float(vals[i]), "view": best, "evals": len(cache)},
              open(spec["result"], "w"), indent=1)
    print("FIT_DONE", round(1 - vals[i], 4), best, flush=True)


if job.get("print_bounds"):
    for key, o in objs:
        for slot in o.material_slots:
            pass
        bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
        print("BOUNDS", key, o.name, [round(min(v[i] for v in bb), 4) for i in range(3)], [round(max(v[i] for v in bb), 4) for i in range(3)])
    if job.get("part_bounds"):
        dg = bpy.context.evaluated_depsgraph_get()
        for key, o in objs:
            me = o.evaluated_get(dg).to_mesh()
            mats = [s.material.name.split(".")[0] if s.material else "" for s in o.material_slots]
            acc = {}
            for poly in me.polygons:
                nm = mats[poly.material_index]
                if nm not in job["part_bounds"]:
                    continue
                for vi in poly.vertices:
                    co = o.matrix_world @ me.vertices[vi].co
                    lo, hi = acc.setdefault(nm, [[9e9] * 3, [-9e9] * 3])
                    for i in range(3):
                        lo[i] = min(lo[i], co[i]); hi[i] = max(hi[i], co[i])
            for nm, (lo, hi) in acc.items():
                print("PART", nm, [round(v, 4) for v in lo], [round(v, 4) for v in hi])
            o.evaluated_get(dg).to_mesh_clear()

for item in job.get("items", []):
    set_item(item)
    if item.get("fit"):
        fit(item, item["fit"])
    for view in item.get("views", []):
        render(item, view, view["out"], mask=view.get("mask", False))
        print("Saved", view["out"], flush=True)
