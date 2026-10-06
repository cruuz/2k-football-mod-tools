#!/usr/bin/env python3
"""Strict u1 helmet/facemask handoff: export native IDs; edit lanes in fixed spans.

This tool never approximates topology or matches vertices by distance. Coordinates
in glTF are metres, native coordinates are centimetres. Keep Blender's glTF
Attributes export enabled: _NFL_VERTEX_INDEX is mandatory on reimport.
"""
from __future__ import annotations

import argparse
import base64
import copy
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_models as models  # noqa: E402
from mod_editor.core import nfl2k5_modern_helmets as mh  # noqa: E402

SCHEMA = "b765/u1-geometry/v1"
DEFAULT_NAMES = {
    mh.HI: [f"FACEMASK{i:02d}" for i in range(12, 27)] + ["HI_HELMET_C", "LOGO_helmet_C"],
    mh.LO: ["HI_HELMET_C", "LO_FACEMASK_C"],
}
ALLOWED_NAMES = {
    key: names + [f"NUMBER_helmet_C_{side}" for side in ("L", "R", "M")]
    for key, names in DEFAULT_NAMES.items()
}


class Refusal(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Refusal(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def output_path(path):
    """Refuse links before resolution, including output directory components."""
    path = Path(path)
    absolute = path.absolute()
    require(not any(p.is_symlink() for p in (absolute, *absolute.parents)),
            f"Output has a symlink component: {path}")
    return path


def path_alias(a, b):
    a, b = Path(a), Path(b)
    return a.resolve() == b.resolve() or (a.exists() and b.exists() and a.samefile(b))


def guard_write_paths(inputs, outputs):
    """Validate every output before any write, including receipts and pin files."""
    outputs = [output_path(p) for p in outputs]
    for i, output in enumerate(outputs):
        require(not any(path_alias(output, source) for source in inputs),
                f"Output aliases an input file: {output}")
        require(not any(path_alias(output, other) for other in outputs[:i]),
                f"Output files alias each other: {output}")
        require(not output.exists() or (output.is_file() and output.stat().st_nlink == 1),
                f"Output is not an unlinked regular file: {output}")


def gltf_input_paths(path):
    document = models.GltfFile(Path(path)).document
    return [Path(path)] + [Path(path).parent / unquote(str(b["uri"]))
                          for b in document.get("buffers", [])
                          if b.get("uri") is not None and not str(b["uri"]).startswith("data:")]


def write_new(path, data):
    """Write a checked copied output atomically; never truncate a linked inode."""
    path = output_path(path)
    require(not path.exists() or (path.is_file() and path.stat().st_nlink == 1),
            f"Output is not an unlinked regular file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".u1-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        require(Path(temporary).read_bytes() == data, f"Staged output readback failed: {path}")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    require(path.read_bytes() == data, f"Output readback failed: {path}")


def write_json(path, document):
    write_new(path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode())


def triangles(mode, indices):
    result = []
    if mode == 6:
        result = [(a, b, c) if i % 2 == 0 else (b, a, c)
                  for i, (a, b, c) in enumerate(zip(indices, indices[1:], indices[2:]))]
    elif mode == 5:
        result = [tuple(indices[i:i + 3]) for i in range(0, len(indices) - 2, 3)]
    elif mode == 7:
        result = [(indices[0], indices[i], indices[i + 1]) for i in range(1, len(indices) - 1)]
    else:
        raise Refusal(f"Unsupported native topology {mode}")
    return [t for t in result if len(set(t)) == 3]


def face_counter(faces):
    """Triangle order/cyclic rotation can change, vertex IDs and winding cannot."""
    return Counter(min(tuple(t), (t[1], t[2], t[0]), (t[2], t[0], t[1])) for t in faces)


def parse_span(key, span, names=None):
    require(key in mh.KEYS, "Only the two common player helmet resources are allowed")
    _resource, decoded, scene = models.ModelSpanSource({key: bytes(span)}).parse(key)
    require(len(scene["shapes"]) == 1, "Expected one common player shape")
    shape = scene["shapes"][0]
    lanes = models._shape_lanes(scene, shape, decoded)
    require(lanes.position_format == "NORMSHORT3", "Expected the pinned short position layout")
    positions = models.read_positions(decoded, shape, lanes)
    require(lanes.normal is not None and lanes.texcoord is not None, "Normal/UV lanes are missing")
    normals = [models.decode_normpacked3(w) for w in models.read_lane_u32(decoded, shape, lanes.normal, lanes.vertex_count)]
    uv = [models.uv_to_gltf(u, v, lanes.uv_scale, lanes.uv_offset)
          for u, v in models.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)]
    materials = {m["index"]: m["name"] for m in scene["materials"]}
    wanted = set(DEFAULT_NAMES[key] if names is None else names)
    # This is a bounded handoff, never a route to stadium or unrelated player art.
    require(wanted <= set(ALLOWED_NAMES[key]), "Submesh outside the helmet/facemask handoff scope")
    meshes = []
    gltf = models._tools_module("nfl_scne_gltf")
    for sub in scene["submeshes"]:
        name = materials[sub["material_index"]]
        if name not in wanted:
            continue
        batches = gltf.decode_batches(decoded, sub["command_offset"], sub["primary_command_word_count"])
        ids = sorted({i for _mode, ix in batches for i in ix})
        faces = [t for mode, ix in batches for t in triangles(mode, ix)]
        require(ids and faces, f"{name}: empty mesh")
        meshes.append({"name": name, "ids": ids, "faces": [list(t) for t in faces],
                       "command_offset": sub["command_offset"], "command_words": sub["primary_command_word_count"],
                       "positions": [positions[i] for i in ids], "normals": [normals[i] for i in ids],
                       "uvs": [uv[i] for i in ids]})
    require({m["name"] for m in meshes} == wanted, "Requested native submesh is missing")
    return decoded, lanes, meshes


def manifest_for(key, span, names, outer_offset=None):
    decoded, lanes, meshes = parse_span(key, span, names)
    return {"schema": SCHEMA, "key": key, "span_sha256": sha(span), "span_size": len(span),
            "wrapper_sha256": sha(span[:32]), "decoded_sha256": sha(decoded), "decoded_size": len(decoded),
            "outer_offset": outer_offset, "units": "glTF metres; native centimetres", "lanes": asdict(lanes),
            "meshes": [{k: m[k] for k in ("name", "ids", "faces", "command_offset", "command_words")} for m in meshes]}


def export(key, span, folder, names=None, outer_offset=None):
    names = DEFAULT_NAMES[key] if names is None else names
    decoded, lanes, meshes = parse_span(key, span, names)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    binary = bytearray()
    doc = {"asset": {"version": "2.0", "generator": "b765-u1 strict native geometry handoff"},
           "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "bufferViews": [], "accessors": [],
           "buffers": [], "extras": {"key": key, "native_span_sha256": sha(span), "vertex_id": models.VERTEX_INDEX_ATTRIBUTE}}

    def accessor(values, fmt, kind, target):
        binary.extend(bytes((-len(binary)) % 4))
        at = len(binary)
        for row in values:
            binary.extend(struct.pack("<" + fmt, *row))
        view = len(doc["bufferViews"])
        doc["bufferViews"].append({"buffer": 0, "byteOffset": at, "byteLength": len(binary) - at, "target": target})
        index = len(doc["accessors"])
        doc["accessors"].append({"bufferView": view, "componentType": 5125 if fmt == "I" else 5126,
                                 "count": len(values), "type": kind})
        return index

    render_dump = {}
    for mesh in meshes:
        ids = mesh["ids"]
        local = {v: i for i, v in enumerate(ids)}
        attrs = {"POSITION": accessor([tuple(v * 0.01 for v in p) for p in mesh["positions"]], "3f", "VEC3", 34962),
                 "NORMAL": accessor(mesh["normals"], "3f", "VEC3", 34962),
                 "TEXCOORD_0": accessor(mesh["uvs"], "2f", "VEC2", 34962),
                 models.VERTEX_INDEX_ATTRIBUTE: accessor([(v,) for v in ids], "I", "SCALAR", 34962)}
        doc["accessors"][attrs["POSITION"]].update(
            min=[min(p[a] for p in mesh["positions"])*0.01 for a in range(3)],
            max=[max(p[a] for p in mesh["positions"])*0.01 for a in range(3)])
        indices = accessor([(local[v],) for t in mesh["faces"] for v in t], "I", "SCALAR", 34963)
        n = len(doc["meshes"])
        doc["meshes"].append({"name": mesh["name"], "primitives": [{"attributes": attrs, "indices": indices, "mode": 4}]})
        doc["nodes"].append({"mesh": n, "name": mesh["name"]})
        doc["scenes"][0]["nodes"].append(n)
        # OBJ is also provided for editors which preserve native vertex order.
        obj = ["# Native centimetres, +Y up, +Z forward. Keep vertex and face order.", f"o {mesh['name']}"]
        for vid, p in zip(ids, mesh["positions"]):
            obj += [f"# _NFL_VERTEX_INDEX {vid}", "v " + " ".join(f"{v:.10g}" for v in p)]
        obj += ["vt " + " ".join(f"{v:.10g}" for v in uv) for uv in mesh["uvs"]]
        obj += ["vn " + " ".join(f"{v:.10g}" for v in nr) for nr in mesh["normals"]]
        obj += ["f " + " ".join(f"{local[v] + 1}/{local[v] + 1}/{local[v] + 1}" for v in t) for t in mesh["faces"]]
        write_new(folder / f"{mesh['name']}.obj", ("\n".join(obj) + "\n").encode())
        render_dump[mesh["name"]] = {"pos": mesh["positions"], "nrm": mesh["normals"], "uv": mesh["uvs"],
                                     "tris": [[local[v] for v in t] for t in mesh["faces"]]}
    doc["buffers"] = [{"uri": "geometry.bin", "byteLength": len(binary)}]
    write_new(folder / "geometry.bin", bytes(binary))
    write_json(folder / "geometry.gltf", doc)
    manifest = manifest_for(key, span, names, outer_offset)
    write_json(folder / "manifest.json", manifest)
    write_json(folder / "render.json", render_dump)
    return manifest


def read_edits(path, expected):
    gltf = models.GltfFile(Path(path))
    doc = gltf.document
    nodes = doc.get("nodes", [])
    require(len(nodes) == len(expected), "Adding/removing nodes or meshes is refused")
    require(all("mesh" in n and not any(k in n for k in ("children", "skin", "matrix", "translation", "rotation", "scale"))
                for n in nodes), "Apply transforms to the mesh before export; hierarchy/skin/transforms are refused")
    require(sorted(n["mesh"] for n in nodes) == list(range(len(expected))), "Meshes must be referenced exactly once")
    require(len(doc.get("meshes", [])) == len(expected), "Adding/removing meshes is refused")
    wanted = {m["name"]: m for m in expected}
    result = {}
    for mesh in doc["meshes"]:
        name = mesh.get("name")
        require(name in wanted and name not in result, "Native mesh names must be unique and preserved")
        by_id, faces = {}, []
        for primitive in mesh.get("primitives", []):
            require(primitive.get("mode", 4) == 4 and "indices" in primitive, "Only indexed native triangle topology is allowed")
            a = primitive.get("attributes", {})
            require(all(k in a for k in ("POSITION", "NORMAL", "TEXCOORD_0", models.VERTEX_INDEX_ATTRIBUTE)),
                    "Missing native vertex ID, position, normal or UV attribute; enable glTF Attributes")
            arrays = {k: gltf.accessor(a[k]) for k in ("POSITION", "NORMAL", "TEXCOORD_0", models.VERTEX_INDEX_ATTRIBUTE)}
            count = len(arrays["POSITION"])
            require(all(len(v) == count for v in arrays.values()), "Vertex attribute counts differ")
            ids = []
            for i in range(count):
                raw_id = arrays[models.VERTEX_INDEX_ATTRIBUTE][i][0]
                require(math.isfinite(raw_id) and raw_id == int(raw_id), "Native vertex IDs must be exact integers")
                vid = int(raw_id)
                values = {"position": tuple(v * 100 for v in arrays["POSITION"][i]),
                          "normal": arrays["NORMAL"][i], "uv": arrays["TEXCOORD_0"][i]}
                require(all(math.isfinite(v) for row in values.values() for v in row), "Nonfinite vertex lane")
                require(vid not in by_id or all(max(abs(a-b) for a,b in zip(by_id[vid][k], values[k])) < 1e-6 for k in values),
                        f"{name}: conflicting edits for split copies of native vertex {vid}")
                by_id[vid] = values
                ids.append(vid)
            ix = [int(v[0]) for v in gltf.accessor(primitive["indices"])]
            require(len(ix) % 3 == 0 and all(0 <= i < count for i in ix), "Triangle index is out of range")
            faces += [tuple(ids[i] for i in ix[j:j + 3]) for j in range(0, len(ix), 3)]
        require(sorted(by_id) == wanted[name]["ids"], f"{name}: native vertex IDs/topology changed")
        require(face_counter(faces) == face_counter(wanted[name]["faces"]), f"{name}: native faces/topology/winding changed")
        result[name] = by_id
    require(set(result) == set(wanted), "Native mesh set changed")
    return result


def scope_receipt(before, after, ranges):
    require(len(before) == len(after), "Stored span size changed")
    mask = bytearray(len(before))
    for start, length in ranges:
        require(0 <= start <= start + length <= len(before), "Scope range outside stored input")
        mask[start:start + length] = bytes([1]) * length
    require(all(a == b or mask[i] for i, (a, b) in enumerate(zip(before, after))), "Byte changed outside declared scope")
    outside_before = bytes(v for i, v in enumerate(before) if not mask[i])
    outside_after = bytes(v for i, v in enumerate(after) if not mask[i])
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(before),
            "changed_bytes": sum(a != b for a, b in zip(before, after)), "ranges": ranges,
            "outside_scope_before_sha256": sha(outside_before), "outside_scope_after_sha256": sha(outside_after),
            "outside_scope_identical": outside_before == outside_after}


def compile_import(span, manifest, edited, selected_lanes=("position",)):
    require(manifest.get("schema") == SCHEMA, "Unexpected handoff manifest schema")
    require(sha(span) == manifest["span_sha256"], "Unexpected input span hash; export the exact intended source first")
    names = [m["name"] for m in manifest["meshes"]]
    expected = manifest_for(manifest["key"], span, names, manifest.get("outer_offset"))
    require(json.dumps(manifest, sort_keys=True) == json.dumps(expected, sort_keys=True),
            "Manifest does not describe the exact input")
    require(set(selected_lanes) <= {"position", "normal", "uv"} and selected_lanes, "Unknown/empty editable lane selection")
    decoded, lanes, meshes = parse_span(manifest["key"], span, names)
    edits = read_edits(edited, manifest["meshes"])
    output, ranges, seen = bytearray(decoded), [], {}
    streams = dict(enumerate(lanes.stream_offsets))
    for mesh in meshes:
        for vid in mesh["ids"]:
            values = edits[mesh["name"]][vid]
            for lane in selected_lanes:
                value = values[lane]
                require((vid, lane) not in seen or all(abs(a-b) < 1e-6 for a,b in zip(value,seen[(vid,lane)])),
                        f"Shared native vertex {vid} has conflicting {lane} edits")
                seen[(vid,lane)] = value
                if lane == "position":
                    normalized = [(value[i] - lanes.offset[i]) / lanes.scale for i in range(3)]
                    require(all(-1 <= v <= 1 for v in normalized), "Position exceeds the fixed native quantization range")
                    data = struct.pack("<3h", *(models.encode_normshort(v) for v in normalized))
                    at = streams[lanes.position_stream] + vid * lanes.position_stride + lanes.position_offset
                elif lane == "normal":
                    require(all(-1 <= v <= 1 for v in value) and sum(v*v for v in value) > 1e-12,
                            "Normal exceeds the native packed range or has zero length")
                    data = struct.pack("<I", models.encode_normpacked3(*value))
                    at = streams[lanes.normal[0]] + vid * lanes.normal[2] + lanes.normal[1]
                else:
                    require(all(models.uv_in_range(value[i], lanes.uv_scale[i], lanes.uv_offset[i]) for i in range(2)),
                            "UV exceeds fixed native range; scale-field changes are refused")
                    data = struct.pack("<2h", *models.uv_from_gltf(*value, lanes.uv_scale, lanes.uv_offset))
                    at = streams[lanes.texcoord[0]] + vid * lanes.texcoord[2] + lanes.texcoord[1]
                output[at:at + len(data)] = data
                ranges.append((at, len(data)))
    decoded_receipt = scope_receipt(decoded, bytes(output), ranges)
    if output == decoded:
        rebuilt = bytes(span)
        compression = {"state": "byte-identical-noop"}
    else:
        fill = models._tools_module("nfl_vc_lz_fill")
        rebuilt, info = fill.rebuild_fixed_span_filled(span, bytes(output), encoder="auto")
        require(info.wrapper_identical and len(rebuilt) == len(span), "Native fixed span/wrapper changed")
        compression = asdict(info)
    require(mh.decode_span_bytes(rebuilt, span) == bytes(output), "Native compression readback differs")
    # Topology is still read from the untouched push streams, not reconstructed.
    _, _, back_meshes = parse_span(manifest["key"], rebuilt, names)
    require([m["faces"] for m in meshes] == [m["faces"] for m in back_meshes], "Native readback topology differs")
    receipt = {"schema": SCHEMA, "key": manifest["key"], "lanes": list(selected_lanes),
               "decoded_scope": decoded_receipt, "stored_scope": scope_receipt(span, rebuilt, [(32, len(span)-32)]),
               "topology_identical": True, "shape_scale_and_uv_constants_identical": True,
               "native_decode_readback_identical": True, "compression": compression}
    return rebuilt, receipt


def apply_outer(before, span, manifest):
    """Compose with other outer-3 work: hash gate only the exact geometry span."""
    at = manifest.get("outer_offset")
    require(type(at) is int, "Manifest has no exact outer-3 offset")
    length = manifest["span_size"]
    require(len(span) == length and 0 <= at <= at+length <= len(before), "Native span size/offset differs")
    old = before[at:at+length]
    require(sha(old) == manifest["span_sha256"] or old == span, "Unexpected geometry span hash in outer 3")
    after = before[:at] + span + before[at+length:]
    return after, scope_receipt(before, after, [(at, length)])


def update_mask_document(document, before_span, after_span, retail_span):
    """Make the existing Studio data writer reproduce mask/detail lane edits.

    A shell or LO plate edit needs a separate writer extension: refuse it here,
    rather than produce a document which silently drops the edited mesh.
    """
    before = mh.decode_span_bytes(before_span, before_span)
    after = mh.decode_span_bytes(after_span, after_span)
    retail = mh.decode_span_bytes(retail_span, retail_span)
    require(mh.author(mh.HI, retail, document)[0] == before, "Baseline geometry document does not reproduce the before scene")
    layout = mh.parse_layout(mh.HI, before)
    result = copy.deepcopy(document)
    entry = result["resources"][mh.HI]
    size = mh.record_size(layout)
    vertex = mh.RUNS[mh.HI][0][0]
    for i in range(12,27):
        part = entry["parts"][f"FACEMASK{i:02d}"]
        records = base64.b64decode(part["records"])
        require(len(records) % size == 0, "Malformed baseline vertex records")
        count = len(records)//size
        require(mh.read_records(layout,before,vertex,count) == records, "Baseline native mask records differ")
        updated = mh.read_records(layout,after,vertex,count)
        if updated != records:
            part["records"] = base64.b64encode(updated).decode("ascii")
        vertex += count
    detail = entry.get("shell_detail")
    if detail:
        records = base64.b64decode(detail["records"])
        require(len(records) % size == 0, "Malformed baseline detail records")
        count = len(records)//size
        require(mh.read_records(layout,before,vertex,count) == records, "Baseline native detail records differ")
        updated = mh.read_records(layout,after,vertex,count)
        if updated != records:
            detail["records"] = base64.b64encode(updated).decode("ascii")
    reproduced = mh.author(mh.HI,retail,result)[0]
    require(reproduced == after, "Edit extends beyond existing mask/detail writer scope; shell/LOD/decal-base edits require a writer extension")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("--span", type=Path, required=True)
    ex.add_argument("--key", choices=mh.KEYS, required=True)
    ex.add_argument("--out", type=Path, required=True)
    ex.add_argument("--meshes", help="Comma-separated names; default all handoff meshes")
    ex.add_argument("--outer-offset", type=lambda s:int(s,0))
    im = sub.add_parser("import")
    im.add_argument("--span", type=Path, required=True)
    im.add_argument("--manifest", type=Path, required=True)
    im.add_argument("--edited", type=Path, required=True)
    im.add_argument("--output", type=Path, required=True)
    im.add_argument("--receipt", type=Path, required=True)
    im.add_argument("--lanes", default="position", help="Explicit position,normal,uv selection (default position)")
    ap = sub.add_parser("apply-outer")
    ap.add_argument("--outer", type=Path, required=True)
    ap.add_argument("--span", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    source = sub.add_parser("update-mask-document", help="Stage build data for mask/detail edits, refusing unsupported shell or LOD changes")
    source.add_argument("--document", type=Path, required=True)
    source.add_argument("--before-span", type=Path, required=True)
    source.add_argument("--after-span", type=Path, required=True)
    source.add_argument("--retail-span", type=Path, required=True)
    source.add_argument("--retail-outer", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    source.add_argument("--pins", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            names = args.meshes.split(",") if args.meshes else DEFAULT_NAMES[args.key]
            require(set(names) <= set(ALLOWED_NAMES[args.key]), "Submesh outside the helmet/facemask handoff scope")
            guard_write_paths([args.span], [args.out / name for name in
                              ["geometry.bin", "geometry.gltf", "manifest.json", "render.json"] +
                              [name + ".obj" for name in names]])
            receipt = export(args.key, args.span.read_bytes(), args.out,
                             names, args.outer_offset)
        elif args.command == "import":
            guard_write_paths([args.span, args.manifest, args.edited], [args.output, args.receipt])
            guard_write_paths([args.span, args.manifest] + gltf_input_paths(args.edited), [args.output, args.receipt])
            manifest = json.loads(args.manifest.read_text())
            output, receipt = compile_import(args.span.read_bytes(), manifest, args.edited, args.lanes.split(","))
            write_new(args.output, output)
            write_json(args.receipt, receipt)
        elif args.command == "apply-outer":
            guard_write_paths([args.outer, args.span, args.manifest], [args.output, args.receipt])
            output, receipt = apply_outer(args.outer.read_bytes(), args.span.read_bytes(), json.loads(args.manifest.read_text()))
            write_new(args.output, output)
            write_json(args.receipt, receipt)
        else:
            guard_write_paths([args.document, args.before_span, args.after_span, args.retail_span, args.retail_outer],
                              [args.output, args.pins])
            document = update_mask_document(json.loads(args.document.read_text()),args.before_span.read_bytes(),
                                            args.after_span.read_bytes(),args.retail_span.read_bytes())
            pins = mh.record_pins(args.retail_outer.read_bytes(),document)
            serialized = (json.dumps(document,indent=2,sort_keys=True)+"\n").encode()
            pins["geometry_sha256"] = sha(serialized)
            write_new(args.output,serialized)
            write_json(args.pins,pins)
            receipt = {"key": mh.HI, "geometry_sha256": sha(serialized), "build_reproduces_native_decoded_scene": True}
        print(json.dumps({"command": args.command, "status": "OK", "key": receipt.get("key"),
                          "before_sha256": receipt.get("before_sha256", receipt.get("span_sha256"))}, sort_keys=True))
        return 0
    except (ValueError, KeyError, IndexError, OSError, struct.error) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
