"""NFL 2K5 Stadium textures for Blender. EXPERIMENTAL / UNWITNESSED.

Run this file in Blender's Text Editor, then use File > Import / Export.
The core functions accept an injected bpy module and import without Blender.
No game files or SCNE writers run inside Blender. Export a texture-only glTF
and import it with Stadiums > Import textures in Mod Studio.
"""
from __future__ import annotations

from array import array
import base64
import json
import os
from pathlib import Path
import re
import struct
import tempfile

ID_KEY = "nfl2k5_texture_id"
SIZE_KEY = "nfl2k5_texture_size"
ID_RE = re.compile(r"nfl2k5\.stadium\.o[0-9]{4,}\.c[0-9]{4,}\.scene[0-9]{4,}\.texture[0-9]{4,}\Z")
MAX_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 4 * 1024 * 1024
_CLASSES = []


class StadiumBlenderError(ValueError):
    pass


def _bpy(module=None):
    if module is None:
        import bpy
        return bpy
    return module


def _key(item):
    return item.as_pointer() if hasattr(item, "as_pointer") else id(item)


def _identity(value):
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise StadiumBlenderError("A material has lost its Stadium texture ID. Import the original export again.")
    return value


def _base_image(material):
    """Require the actual Base Color connection, not a guessed image node."""
    tree = getattr(material, "node_tree", None)
    shaders = [] if tree is None else [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]
    if len(shaders) != 1:
        raise StadiumBlenderError(f"{material.name}: keep one Principled shader for texture export.")
    socket = shaders[0].inputs.get("Base Color")
    links = [] if socket is None else list(socket.links)
    if len(links) != 1 or links[0].from_node.type != "TEX_IMAGE":
        raise StadiumBlenderError(f"{material.name}: connect the edited image directly to Base Color.")
    image = links[0].from_node.image
    if image is None or getattr(image, "source", "FILE") not in ("FILE", "GENERATED"):
        raise StadiumBlenderError(f"{material.name}: choose one still image.")
    return image


def bind_materials(materials, document):
    """Keep canonical IDs and dimensions on both material and image datablocks."""
    expected = {}
    for row in document.get("images", []):
        extra = row.get("extras", {})
        identity = extra.get(ID_KEY)
        if identity is None:
            continue
        _identity(identity)
        size = (extra.get("width"), extra.get("height"))
        if any(type(n) is not int or n <= 0 for n in size) or size[0] * size[1] > MAX_PIXELS:
            raise StadiumBlenderError("The source export has invalid texture dimensions.")
        if identity in expected and expected[identity] != size:
            raise StadiumBlenderError("The source export has conflicting texture sizes.")
        expected[identity] = size
    if not expected:
        raise StadiumBlenderError("Choose an original Stadiums export with texture IDs.")
    bindings = []
    seen = set()
    # Preflight before assigning custom properties, including image sharing.
    image_owners = {}
    for material in materials:
        identity = material.get(ID_KEY)
        if identity is None:
            continue
        if identity not in expected:
            raise StadiumBlenderError("An imported material has a foreign Stadium texture ID.")
        image = _base_image(material)
        if tuple(image.size) != expected[identity]:
            raise StadiumBlenderError(f"{material.name}: keep its original image dimensions.")
        owner = image_owners.setdefault(_key(image), identity)
        if owner != identity:
            raise StadiumBlenderError("Two game textures share one Blender image. Make separate image copies.")
        bindings.append((material, image, identity, expected[identity]))
        seen.add(identity)
    if seen != set(expected):
        raise StadiumBlenderError("Blender did not retain every texture material. Reimport the original Stadiums export.")
    for material, image, identity, size in bindings:
        material[SIZE_KEY] = list(size)
        image[ID_KEY] = identity
        image[SIZE_KEY] = list(size)
    return len(seen)


def import_stadium(path, bpy_module=None):
    bpy = _bpy(bpy_module)
    source = Path(path).expanduser().resolve(strict=True)
    with source.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise StadiumBlenderError("The source glTF exceeds 64 MiB.")
    document = json.loads(raw)
    if not document.get("extras", {}).get("nfl2k5_texcoord_contract"):
        raise StadiumBlenderError("Export this stadium again with Mod Studio's textured UV export.")
    before = {_key(item) for item in bpy.data.materials}
    result = bpy.ops.import_scene.gltf(filepath=str(source), import_pack_images=True)
    if "FINISHED" not in result:
        raise StadiumBlenderError("Blender did not finish importing the stadium.")
    materials = [item for item in bpy.data.materials if _key(item) not in before]
    return bind_materials(materials, document)


def _save_image(image, path, bpy):
    """Copy live painted pixels explicitly; Image.copy alone loses dirty pixels.

    Image.save uses the image's own colour space, without the scene's view
    transform. save_render would bake that view transform and is not used.
    Blender owns pixel row orientation and PNG encoding in this path.
    """
    width, height = map(int, image.size)
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise StadiumBlenderError("A Stadium texture is too large or has no pixels.")
    values = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(values)
    copy = bpy.data.images.new("NFL2K5 export temporary", width=width, height=height,
                               alpha=True, float_buffer=bool(image.is_float))
    try:
        copy.colorspace_settings.name = image.colorspace_settings.name
        copy.alpha_mode = image.alpha_mode
        copy.pixels.foreach_set(values)
        copy.update()
        copy.file_format = "PNG"
        copy.filepath_raw = str(path)
        copy.save()
    finally:
        bpy.data.images.remove(copy)
    with path.open("rb") as stream:
        payload = stream.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise StadiumBlenderError("A saved Stadium texture exceeds 64 MiB.")
    return payload


def texture_document(rows):
    """Create a portable texture-only glTF; the Mod Studio reader validates it."""
    images, textures, materials = [], [], []
    scene_ids, claimed, total = set(), {}, 0
    for identity, width, height, payload in rows:
        _identity(identity)
        scene_ids.add(identity.rsplit(".texture", 1)[0])
        if len(scene_ids) != 1:
            raise StadiumBlenderError("Export materials from one Stadium scene at a time.")
        if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) < 33:
            raise StadiumBlenderError("Blender did not save a PNG.")
        if struct.unpack_from(">II", payload, 16) != (width, height):
            raise StadiumBlenderError("A saved image changed dimensions.")
        if identity in claimed:
            if claimed[identity] != payload:
                raise StadiumBlenderError("Linked materials disagree about one game texture.")
            continue
        claimed[identity] = payload
        total += len(payload)
        if total > MAX_BYTES * 3 // 4 - 1024 * 1024:
            raise StadiumBlenderError("The texture bundle exceeds its 64 MiB limit.")
        index = len(images)
        extra = {ID_KEY: identity, "width": width, "height": height}
        images.append({"name": identity, "mimeType": "image/png", "extras": extra,
                       "uri": "data:image/png;base64," + base64.b64encode(payload).decode("ascii")})
        textures.append({"source": index, "extras": {ID_KEY: identity}})
        materials.append({"name": identity, "extras": {ID_KEY: identity},
                          "pbrMetallicRoughness": {"baseColorTexture": {"index": index}}})
    if not images:
        raise StadiumBlenderError("Select materials imported by the Stadium helper.")
    return {"asset": {"version": "2.0", "generator": "NFL2K5 Stadium Blender helper v1"},
            "images": images, "textures": textures, "materials": materials,
            "extras": {"nfl2k5_scene_id": next(iter(scene_ids)),
                       "nfl2k5_texture_only": True, "status": "EXPERIMENTAL / UNWITNESSED"}}


def export_textures(path, materials, bpy_module=None):
    bpy = _bpy(bpy_module)
    destination = Path(path).expanduser().absolute()
    if destination.suffix.lower() != ".gltf":
        raise StadiumBlenderError("Choose a .gltf filename for the texture bundle.")
    if os.path.lexists(destination):
        raise StadiumBlenderError("Choose a new filename; an export already exists there.")
    bindings, image_owners = [], {}
    for material in materials:
        identity = material.get(ID_KEY)
        if identity is None:
            continue
        _identity(identity)
        image = _base_image(material)
        image_identity = image.get(ID_KEY)
        if image_identity is not None and image_identity != identity:
            raise StadiumBlenderError("The material and image have different Stadium texture IDs.")
        owner = image_owners.setdefault(_key(image), identity)
        if owner != identity:
            raise StadiumBlenderError("Two game textures share one Blender image. Make separate image copies.")
        expected = material.get(SIZE_KEY)
        if expected is None or tuple(image.size) != tuple(expected):
            raise StadiumBlenderError(f"{material.name}: keep the original image dimensions.")
        bindings.append((identity, image, tuple(expected)))
    if len({row[0].rsplit(".texture", 1)[0] for row in bindings}) > 1:
        raise StadiumBlenderError("Select objects from one Stadium scene at a time.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nfl2k5-blender-", dir=destination.parent) as temporary:
        root = Path(temporary).resolve()
        rows, saved = [], {}
        for identity, image, size in bindings:
            key = _key(image)
            if key not in saved:
                saved[key] = _save_image(image, root / f"{len(saved)}.png", bpy)
            rows.append((identity, *size, saved[key]))
        document = texture_document(rows)
        payload = (json.dumps(document, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > MAX_BYTES:
            raise StadiumBlenderError("The texture bundle exceeds 64 MiB.")
        staged = root / "textures.gltf"
        with staged.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive publication; handles are closed before the link/cleanup.
        os.link(staged, destination)
    return len(document["images"])


def register(bpy_module=None):
    """Register File menu operators only when actually running in Blender."""
    bpy = _bpy(bpy_module)
    if _CLASSES:
        return

    class ImportStadium(bpy.types.Operator):
        bl_idname = "import_scene.nfl2k5_stadium"
        bl_label = "NFL 2K5 Stadium (.gltf, experimental)"
        def execute(self, context):
            try:
                count = import_stadium(self.filepath, bpy)
                self.report({"INFO"}, f"Imported {count} Stadium textures. Game play is unwitnessed.")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        def invoke(self, context, event):
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

    class ExportTextures(bpy.types.Operator):
        bl_idname = "export_scene.nfl2k5_stadium_textures"
        bl_label = "NFL 2K5 Stadium textures (.gltf, experimental)"
        def execute(self, context):
            try:
                materials = {slot.material.name: slot.material
                             for obj in context.selected_objects for slot in obj.material_slots
                             if slot.material is not None}
                count = export_textures(self.filepath, materials.values(), bpy)
                self.report({"INFO"}, f"Exported {count} textures. Import this file in Mod Studio Stadiums.")
                return {"FINISHED"}
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        def invoke(self, context, event):
            self.filepath = "stadium-textures.gltf"
            context.window_manager.fileselect_add(self)
            return {"RUNNING_MODAL"}

    # Evaluated properties, even with postponed Python annotations enabled.
    for cls in (ImportStadium, ExportTextures):
        cls.__annotations__ = {"filepath": bpy.props.StringProperty(subtype="FILE_PATH")}
        bpy.utils.register_class(cls)
        _CLASSES.append(cls)
    bpy.types.TOPBAR_MT_file_import.append(_import_menu)
    bpy.types.TOPBAR_MT_file_export.append(_export_menu)


def _import_menu(self, context):
    self.layout.operator("import_scene.nfl2k5_stadium")


def _export_menu(self, context):
    self.layout.operator("export_scene.nfl2k5_stadium_textures")


def unregister(bpy_module=None):
    bpy = _bpy(bpy_module)
    if not _CLASSES:
        return
    bpy.types.TOPBAR_MT_file_import.remove(_import_menu)
    bpy.types.TOPBAR_MT_file_export.remove(_export_menu)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _CLASSES.clear()


if __name__ == "__main__":
    register()
