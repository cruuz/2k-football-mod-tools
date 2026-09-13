"""Checked Models edits: sparse compiled bytes, source provenance and SCNE composition.

No glTF is consumed by the disc builder. Only changed bytes are archived; original
resources always come from the user's source. The quick path's exact packed bytes
are reconstructed, including its fixed wrapper and compression padding.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import re
from pathlib import Path
from urllib.parse import unquote

from . import nfl2k5_models as M
from .errors import ValidationError

KIND = "model_edit"
SCHEMA = "nfl2k5_model_project/v1"
MAX_BYTES = 64 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def changed_runs(before, after):
    require(len(before) == len(after), "Model resource size changed; check the model again.")
    rows, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            rows.append([start, base64.b64encode(after[start:i]).decode("ascii")])
            start = None
    if start is not None:
        rows.append([start, base64.b64encode(after[start:]).decode("ascii")])
    return rows


def apply_runs(before, rows):
    require(isinstance(rows, list), "Malformed compiled model change.")
    after, end = bytearray(before), 0
    for row in rows:
        require(isinstance(row, list) and len(row) == 2 and type(row[0]) is int
                and isinstance(row[1], str), "Malformed compiled model byte range.")
        try:
            data = base64.b64decode(row[1], validate=True)
        except ValueError as exc:
            raise ValidationError("Malformed compiled model bytes.") from exc
        offset = row[0]
        require(data and offset >= end and offset + len(data) <= len(before),
                "Compiled model byte range is outside its resource or overlaps another range.")
        require(all(a != b for a, b in zip(before[offset:offset+len(data)], data)),
                "Compiled model change includes unchanged source bytes.")
        after[offset:offset+len(data)] = data
        end = offset + len(data)
    return bytes(after)


def source_files(paths):
    """Pin glTF/GLB and external buffers, including the export identity manifest."""
    names = set()
    for supplied in paths:
        path = Path(supplied).expanduser().resolve()
        names.add(path)
        if path.suffix.lower() == ".gltf":
            try:
                require(path.stat().st_size <= MAX_BYTES, f"Model input is too large: {path}")
                doc = json.loads(path.read_bytes())
                require(isinstance(doc, dict) and isinstance(doc.get("buffers", []), list),
                        f"Invalid glTF document: {path}. Export it again from Blender.")
            except (OSError, ValueError) as exc:
                raise ValidationError(f"Cannot check glTF: {path}. Restore it or export it again from Blender.") from exc
            for buffer in doc.get("buffers", []):
                uri = buffer.get("uri", "")
                if uri and not uri.startswith("data:"):
                    names.add((path.parent / unquote(uri)).resolve())
        manifest = path.parent / "player-body-set.skeleton.json"
        if manifest.is_file():
            names.add(manifest)
    result = []
    for path in sorted(names):
        try:
            require(path.stat().st_size <= MAX_BYTES, f"Model input is too large: {path}")
            payload = path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"Cannot check model input: {path}. Restore it and check the model again.") from exc
        result.append({"path": str(path), "sha256": sha(payload), "size": len(payload)})
    return result


def recheck_files(record):
    """Refuse stale authoring inputs without discarding the compiled project edit."""
    problems = []
    for row in record["sources"]:
        path = Path(row["path"])
        try:
            matches = path.stat().st_size == row["size"] and sha(path.read_bytes()) == row["sha256"]
        except OSError:
            matches = False
        if not matches:
            problems.append(f"Re-check refused: {path} is missing or changed. Restore the checked file, "
                            "or check and add its replacement in Models. The saved compiled change can still build.")
    return problems


def _resource(source, key):
    outer, chunk = M.parse_model_key(key)
    if (outer, chunk) in source.resources:
        return source.resources[outer, chunk]
    # SKEL is a guard in a coordinated body set, not a catalogued SCNE.
    _, resources = source._probe.parse_inventory(source.inventory_path)
    resource = next((r for r in resources if (r.outer_index, r.chunk_index) == (outer, chunk)), None)
    require(resource is not None and key == "o3c116", f"Missing model resource {key}.")
    return resource


def checked_disc_summary(source, compiled):
    if isinstance(compiled, M.CompiledModelSet) and compiled.skeleton_plan is not None:
        count = compiled.changed_bytes
    else:
        members = compiled.members if isinstance(compiled, M.CompiledModelSet) else [compiled]
        count = sum(sum(a != b for a,b in zip(source.span(source.resource(m.key)),m.rebuilt_span)) for m in members)
    return re.sub(r"[\d,]+ bytes change on disc", f"{count:,} bytes change on disc", compiled.summary())


def make_record(source, compiled, files, options=None, pinned_sources=None):
    pins = source_files(files) if pinned_sources is None else copy.deepcopy(pinned_sources)
    skeleton = isinstance(compiled, M.CompiledModelSet) and compiled.skeleton_plan is not None
    members = compiled.skeleton_plan.members if skeleton else (
        compiled.members if isinstance(compiled, M.CompiledModelSet) else [compiled])
    rows = []
    for member in members:
        resource = _resource(source, member.key)
        before = source.span(resource)
        after = member.after if skeleton else member.rebuilt_span
        require(sha(before) == (sha(member.before) if skeleton else member.template_span_sha256),
                f"{member.key}: model source changed after checking.")
        decoded, _ = source._probe.decode_resource(before, resource)
        rebuilt, _ = source._probe.decode_resource(after, resource)
        require(before[:32] == after[:32], f"{member.key}: model wrapper changed.")
        rows.append({"key": member.key, "size": len(before), "before_sha256": sha(before),
                     "after_sha256": sha(after), "decoded_sha256": sha(rebuilt),
                     "changes": changed_runs(before, after),
                     "decoded_changes": changed_runs(decoded, rebuilt)})
    keys = {row["key"] for row in rows}
    # All single-LOD imports of a player belong to one replaceable project set.
    body = any(key in {"o3c113", "o3c114", "o3c115"} for key in keys)
    target = "player-body-o3" if body else "models-" + "-".join(sorted(keys))
    def check_metadata(value):
        if isinstance(value, dict):
            return {key: check_metadata(item) for key, item in value.items()
                    if key not in {"before_hex", "after_hex"}}
        if isinstance(value, list):
            return [check_metadata(item) for item in value]
        return value

    record = {"schema": SCHEMA, "target": target, "mode": "skeleton" if skeleton else "geometry",
              "summary": compiled.summary(), "sources": pins, "options": options or {},
              "check": check_metadata(compiled.report()), "members": rows,
              "changed_bytes": sum(sum(len(base64.b64decode(data)) for _, data in row["changes"]) for row in rows),
              "witnessed": False}
    record["summary"] = re.sub(r"[\d,]+ bytes change on disc", f"{record['changed_bytes']:,} bytes change on disc", record["summary"])
    require(record["changed_bytes"] > 0, "The checked model does not change any disc bytes.")
    problems = recheck_files(record)
    require(not problems, "\n".join(problems))
    validate_record(record)
    for row in record["members"]:
        restore_member(source, row, record)
    return record


def validate_record(record):
    require(isinstance(record, dict) and record.get("schema") == SCHEMA,
            "Unsupported compiled model project record; check and add the model again.")
    require(set(record) == {"schema", "target", "mode", "summary", "sources", "options", "check",
                            "members", "changed_bytes", "witnessed"}, "Malformed compiled model record fields.")
    require(record["mode"] in {"geometry", "skeleton"} and record["witnessed"] is False
            and isinstance(record["target"], str) and isinstance(record["summary"], str)
            and isinstance(record["check"], dict) and isinstance(record["options"], dict)
            and type(record["changed_bytes"]) is int and record["changed_bytes"] > 0,
            "Malformed model check result.")
    require(isinstance(record["sources"], list) and 1 <= len(record["sources"]) <= 64,
            "Missing checked model source paths and hashes.")
    for row in record["sources"]:
        require(isinstance(row, dict) and set(row) == {"path", "sha256", "size"}
                and isinstance(row["path"], str) and len(row["sha256"]) == 64
                and type(row["size"]) is int and 0 <= row["size"] <= MAX_BYTES,
                "Malformed checked model source path/hash.")
    require(isinstance(record["members"], list) and 1 <= len(record["members"]) <= 4,
            "Malformed compiled model set.")
    keys = []
    for row in record["members"]:
        require(isinstance(row, dict) and set(row) == {"key", "size", "before_sha256", "after_sha256",
                "decoded_sha256", "changes", "decoded_changes"}, "Malformed compiled model member.")
        M.parse_model_key(row["key"])
        require(type(row["size"]) is int and 32 <= row["size"] <= MAX_BYTES
                and all(isinstance(row[n], str) and len(row[n]) == 64 for n in
                        ("before_sha256", "after_sha256", "decoded_sha256")), "Malformed model member hashes/size.")
        keys.append(row["key"])
    require(len(set(keys)) == len(keys), "The project repeats a model resource.")
    if record["mode"] == "skeleton":
        require(set(keys) == {"o3c113", "o3c114", "o3c115", "o3c116"}
                and record["check"].get("preflight_passed") is True,
                "Coordinated skeleton project is missing its paired check or resource guards.")
    require(len(canonical(record)) <= MAX_BYTES, "Compiled model project exceeds 64 MiB.")
    return record


def _validate_model_lanes(source, resource, original, rebuilt, record):
    """Reparse compiled changes and restrict them to the Models writer's lanes."""
    key = M.model_key(resource.outer_index, resource.chunk_index)
    if resource.kind == "SKEL":
        require(key == "o3c116" and original == rebuilt, "The Models axial gate retains canonical SKEL directions.")
        return
    require(resource.kind == "SCNE" and len(original) == len(rebuilt), f"{key}: model resource layout changed.")
    _, _, scene = source.parse(key)
    allowed = bytearray(len(original))

    def allow(at, size):
        require(0 <= at <= at + size <= len(original), f"{key}: model lane exceeds its scene.")
        allowed[at:at+size] = b'\1' * size

    skeleton = record is not None and record["mode"] == "skeleton" and key in {"o3c113", "o3c114"}
    for shape in scene["shapes"]:
        if not int(shape["vertex_count"]):
            continue
        lanes = M._shape_lanes(scene, shape, original)
        if lanes.position_format not in {"NORMSHORT3", "FLOAT3"}:
            continue
        base = M._stream_base(scene, shape, lanes.position_stream)
        for i in range(lanes.vertex_count):
            allow(base + i*lanes.position_stride + lanes.position_offset,
                  6 if lanes.position_format == "NORMSHORT3" else 12)
        if lanes.position_format == "NORMSHORT3":
            allow(lanes.record_offset + 0x10, 4)
            allow(lanes.record_offset + 0x20, 12)
        allow(lanes.record_offset + M.UV_CONSTANT_OFFSET, 16)
        for lane in (lanes.normal, lanes.texcoord, lanes.colour):
            if lane is not None:
                base = M._stream_base(scene, shape, lane[0])
                for i in range(lanes.vertex_count):
                    allow(base + i*lane[2] + lane[1], 4)
        if skeleton:
            from . import nfl2k5_model_skeleton as S
            skin = M.decode_skin(original, shape, lanes, scene["submeshes"])
            changed = record["check"].get("changed_bones", [])
            require(isinstance(changed, list) and len(changed) <= 1, "A skeleton project supports one checked axial bone length.")
            bone, scale = None, 1.0
            if changed:
                bone = next((b for b in S.BONES if b.name == changed[0].get("bone") and b.kind != "upper_arm"), None)
                scale = changed[0].get("scale")
                require(bone is not None and type(scale) in (float,int) and math.isfinite(scale)
                        and .95 <= scale <= 1.05, "Skeleton project exceeds the checked axial bone gate.")
            targets = S.target_positions(skin.transforms, bone, scale) if bone else {t['name']:t['absolute'] for t in skin.transforms}
            bind = M._tools_module("nfl_scne_inventory").resolve_relative(
                original, lanes.record_offset + 0x64, len(original), "bind transforms")
            for i in range(lanes.transform_count):
                allow(bind + i*112 + 0x40, 12)
                allow(bind + i*112 + 0x50, 12)
            edited = M.decode_skin(rebuilt, shape, lanes, scene["submeshes"])
            for transform in edited.transforms:
                parent = transform['parent']
                expected = targets[transform['name']]
                parent_position = targets[edited.transforms[parent]['name']] if parent >= 0 else (0.,0.,0.)
                require(math.dist(transform['absolute'], expected) <= S.TOLERANCE_CM
                        and math.dist(transform['local'], tuple(a-b for a,b in zip(expected,parent_position))) <= S.TOLERANCE_CM,
                        f"{key}: compiled bind does not match the checked paired skeleton.")
        positions = M.read_positions(rebuilt, shape, M._shape_lanes(scene,shape,rebuilt))
        require(all(math.isfinite(v) for point in positions for v in point), f"{key}: compiled positions are not finite.")
    require(all(a == b or allowed[i] for i,(a,b) in enumerate(zip(original, rebuilt))),
            f"{key}: compiled model changes bytes outside the checked geometry/bind lanes.")


def restore_member(source, row, record=None):
    resource = _resource(source, row["key"])
    before = source.span(resource)
    require(len(before) == row["size"] and sha(before) == row["before_sha256"],
            f"{row['key']}: the project's checked model does not match this source disc.")
    after = apply_runs(before, row["changes"])
    require(before[:32] == after[:32] and sha(after) == row["after_sha256"],
            f"{row['key']}: stored compiled model bytes changed. Check and add the model again.")
    decoded, _ = source._probe.decode_resource(before, resource)
    rebuilt, _ = source._probe.decode_resource(after, resource)
    require(sha(rebuilt) == row["decoded_sha256"] and apply_runs(decoded, row["decoded_changes"]) == rebuilt,
            f"{row['key']}: compiled model reparse differs from the checked change.")
    _validate_model_lanes(source, resource, decoded, rebuilt, record)
    return resource, before, after


def merge_decoded(source, resource, before, model_after, other_after, label):
    original, _ = source._probe.decode_resource(before, resource)
    model, _ = source._probe.decode_resource(model_after, resource)
    other, _ = source._probe.decode_resource(other_after, resource)
    require(len(original) == len(model) == len(other),
            f"{label}: model and texture edits change the same resource layout; remove one edit.")
    combined = bytearray(other)
    for offset, (a, b, c) in enumerate(zip(original, model, other)):
        if b != a:
            require(c in (a, b), f"{label}: conflicting model and other edit at decoded byte {offset:#x}; "
                    "remove one edit or re-export a compatible model.")
            combined[offset] = b
    if bytes(combined) == model:
        return model_after
    if bytes(combined) == other:
        return other_after
    result, _ = M._tools_module("nfl_vc_lz_fill").rebuild_fixed_span_filled(before, bytes(combined), encoder="auto")
    checked, _ = source._probe.decode_resource(result, resource)
    require(result[:32] == before[:32] and checked == bytes(combined), f"{label}: composed model reparse failed.")
    return result


def prepare_project_models(backend, prepared, edits, project, pins, index, inventory,
                           temp_root, temp_files, source_fd):
    """Compose checked model resources after artwork, before binding/copying the disc."""
    if not edits:
        return
    source = M.ModelSource(index, inventory)
    packs = M._xdvdfs_pack_entries(source_fd, os.fstat(source_fd).st_size)
    pack_hashes = {}
    claimed = set()
    for edit in edits:
        pin = backend.resolve_asset(project, edit["recipe"], pins)
        record = validate_record(json.loads(pin.payload))
        require(record["target"] == edit["target"], "Model recipe target differs from its project row.")
        total = 0
        for row in record["members"]:
            key = row["key"]
            require(key not in claimed, f"Two project model edits claim {key}; remove one set.")
            claimed.add(key)
            resource, before, after = restore_member(source, row, record)
            total += sum(a != b for a, b in zip(before, after))
            segments = tuple(source.archive_segments(resource))
            consumed = 0
            for segment in segments:
                pack_name = str(segment.pack_name)
                pack = packs.get(pack_name)
                require(pack is not None, f"{key}: source disc is missing pack {pack_name}.")
                size, offset = int(segment.size), int(segment.pack_offset)
                original = before[consumed:consumed+size]
                replacement = after[consumed:consumed+size]
                absolute = int(pack.byte_offset) + offset
                current = M.platform_compat.pread(source_fd, size, absolute)
                require(current == original, f"{key}: source disc resource differs from the checked model.")
                if replacement == original:
                    consumed += size
                    continue
                overlaps = [p for p in prepared if p.pack_path.casefold() == f"vc_53450030/{pack_name}".casefold()
                            and p.pack_offset < offset + size and offset < p.pack_offset + p.replacement_size]
                reports, previews, inputs = [], [], {"recipe": pin.sha256}
                if overlaps:
                    require(len(segments) == 1 and len(overlaps) == 1
                            and overlaps[0].pack_offset == offset and overlaps[0].replacement_size == size,
                            f"{key}: another project writer overlaps part of this resource; remove the conflicting edit.")
                    previous = overlaps[0]
                    label = f"{key} and {previous.kind}:{previous.selector}"
                    replacement = merge_decoded(source, resource, before, after,
                                                previous.replacement_path.read_bytes(), label)
                    reports.append({"kind": previous.kind, "selector": previous.selector,
                                    "project_edit": previous.project_edit,
                                    "check": json.loads(previous.import_report_path.read_bytes())})
                    previews.extend(previous.preview_paths)
                    inputs.update({f"composed_{k}": v for k, v in previous.input_sha256.items()})
                    prepared.remove(previous)
                number = len(temp_files)
                replacement_path = temp_root.path / f"model_{number:05d}.bin"
                temp_files.append(backend.exclusive_payload(replacement_path, replacement, temp_root))
                report = {"schema": SCHEMA, "target": record["target"], "member": key,
                          "check": record["check"], "source_files": record["sources"],
                          "compiled_changed_bytes": record["changed_bytes"], "composed_edits": reports,
                          "writer": "Models fixed-span writer", "witnessed": False,
                          "reparsed": True}
                report_path = temp_root.path / f"model_{number:05d}_import.json"
                payload = canonical(report)
                temp_files.append(backend.exclusive_payload(report_path, payload, temp_root))
                if pack_name not in pack_hashes:
                    pack_hashes[pack_name] = backend.common.sha256_fd(source_fd, int(pack.byte_offset), int(pack.size))
                pack_path = f"vc_53450030/{pack_name}"
                target = {"model_key": key}
                prepared.append(backend.PreparedEdit(
                    len(prepared), KIND, f"{record['target']}:{key}:{consumed}", copy.deepcopy(edit), inputs, target,
                    pack_path, int(pack.byte_offset)//2048, int(pack.size), pack_hashes[pack_name], offset,
                    absolute, sha(original), replacement_path, size, sha(replacement), [], report_path,
                    sha(payload), previews))
                consumed += size
            require(consumed == len(before), f"{key}: model resource pack arithmetic changed.")
        require(total == record["changed_bytes"], "Model project's computed byte change differs from its check.")
    for number, edit in enumerate(prepared):
        edit.order = number


def plan_rows(session):
    return [{"target": r["target"], "summary": r["summary"], "mode": r["mode"],
             "changed_bytes": r["changed_bytes"], "resources": [m["key"] for m in r["members"]],
             "witnessed": False} for r in getattr(session, "model_records", ())]


def validate_build_plan(plan, session):
    """Early refusal for later fixed-retail writers; called by protected wiring."""
    keys = {key for row in plan_rows(session) for key in row["resources"]}
    if (getattr(plan, "guardian_cap", False) or getattr(plan, "guardian_overlay", False)) and keys & {"o3c113", "o3c115"}:
        raise ValidationError("Guardian cap/overlay and the project model both own " + ", ".join(sorted(keys & {"o3c113", "o3c115"}))
                              + ". Turn off Guardian cap/overlay or remove the model edit before building; "
                              "Both Guardian writers require their original low body and head resources.")
    if getattr(plan, "hires_pack", False) and keys:
        from . import nfl2k5_hires_pack as hires
        selected = hires._selection(hires.load_folder(plan.hires_folder, families=plan.hires_families))
        shared = keys & {f"o{a.outer}c{a.chunk}" for a in selected}
        require(not shared, "Hi-res artwork and project Models share " + ", ".join(sorted(shared))
                + ". Remove the overlapping hi-res selection or model edit; the hi-res writer requires retail resources.")
