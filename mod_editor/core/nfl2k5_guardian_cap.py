"""EXPERIMENTAL / UNWITNESSED guardian-cap visual trial, route B.

Every player wearing helmet C shows a guardian cap. Helmet C's normal look is
replaced while this is on. Only Detroit current away (09A0.IFF) receives the
neutral quilt repaint; other uniforms retain their existing helmet02 artwork.

This resource pass has no executable, roster-bit, practice-mode or per-player
selection patch. Geometry, animation clearance and matte rendering need Noah's
witness. The retail material's reflection/lighting behavior is retained.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Any, Mapping

from . import nfl2k5_models as models
from . import platform_compat

SCHEMA = "nfl2k5_guardian_cap/v1"
PROFILE = "c_padded_cover_v1"
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
UI_TEXT = ("Every player wearing helmet C shows a guardian cap. "
           "Helmet C's normal look is replaced while this is on.")
TEST_UNIFORM = "Detroit current away (09A0.IFF)"


class GuardianCapError(ValueError):
    """Unrecognized or mixed resource bytes; nothing may be written."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardianCapError(message)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Target:
    key: str
    pack: str
    pack_offset: int
    size: int
    retail_sha256: str
    applied_sha256: str
    shell_material: int = -1
    first_vertex: int = 0
    shell_vertices: int = 0
    shape_offset: int = 0


# These are pack-relative extents, NOT fixed XISO addresses. Whole-resource
# hashes include wrappers, unused compressed tail bytes and all sibling meshes.
TARGETS = (
    Target("o3c113", "0", 0x1A0850, 135840,
           "e3f71e2b930707d68eecfc9c1fa8025da6f1d1ec2087ec3d6ebaa3fa5fec604c",
           "54b80cb326a5983fc58617430307435478029ac6d501ba3c9f49889824f4f4db", 16, 4349, 112, 0x6740),
    Target("o3c115", "0", 0x1F3110, 270368,
           "4493cfafede437da6af7ddadfaa172bed3bd674a62801b73af3a99fc66315e43",
           "289659a0590b9b1af3f53e0cfa9f01a5842bbd35c52ef8a52e52dfcdef67eccc", 21, 11022, 435, 0x21A0),
    Target("o4002c12", "B", 0xF42D9B0, 36704,
           "c3ae19fb03e006dc50bd5ad6c2a995d333cefe1448fb8902df123c073cc5ac4e",
           "9a5479267fe8cbcac6176d62d817e67e949c79b82065d69a418fb80cdf0a843f"),
)
BY_KEY = {target.key: target for target in TARGETS}


def _target(payload: bytes, key: str | None) -> Target | None:
    if key is not None:
        return BY_KEY.get(key)
    return next((target for target in TARGETS if len(payload) == target.size), None)


def status(payload: bytes, *, key: str | None = None) -> str:
    """Whole stored resource (32-byte wrapper included): retail/applied/foreign."""
    target = _target(payload, key)
    if target is None or len(payload) != target.size:
        return "foreign"
    digest = _sha(payload)
    if digest == target.retail_sha256:
        return "retail"
    if digest == target.applied_sha256:
        return "applied"
    return "foreign"


def resources_status(resources: Mapping[str, bytes]) -> str:
    """Require all three owned resources in the same state. Partial installs refuse."""
    if set(resources) != set(BY_KEY):
        return "foreign"
    states = {status(payload, key=key) for key, payload in resources.items()}
    return states.pop() if len(states) == 1 else "foreign"


def _smooth(low: float, high: float, value: float) -> float:
    t = min(1.0, max(0.0, (value - low) / (high - low)))
    return t * t * (3.0 - 2.0 * t)


def sculpt_shell(positions: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
    """Shared dimensionless LOD profile; authored positions/offsets are centimetres.

    Position-only displacement keeps coincident seam vertices together. Crown
    and rear carry about 2 cm of padding, ears flare outward, the front opening
    tapers for the visor and the bottom lip never moves down onto the chinstrap.
    Broad shallow lobes suggest padded panels without adding topology. These
    are design clearances, not a collision/animation or visual proof.
    """
    _require(bool(positions) and all(len(p) == 3 and all(math.isfinite(v) for v in p) for p in positions),
             "Shell positions must be finite and nonempty")
    low = [min(p[a] for p in positions) for a in range(3)]
    high = [max(p[a] for p in positions) for a in range(3)]
    radius = [(high[a] - low[a]) / 2 for a in range(3)]
    _require(min(radius) > 0, "Shell bounds are degenerate")
    centre = [(high[a] + low[a]) / 2 for a in range(3)]
    out = []
    for point in positions:
        x, y, z = [(point[a] - centre[a]) / radius[a] for a in range(3)]
        crown = _smooth(0.15, 0.9, y)
        rear = 1 - _smooth(-0.75, 0.15, z)
        ear = _smooth(0.4, 0.9, abs(x)) * (1 - crown)
        front = _smooth(0.15, 0.8, z) * (1 - crown)
        rim = 1 - _smooth(-0.9, -0.25, y)
        quilt = (math.sin(x * math.pi * 2) ** 2
                 * math.sin((z + 1) * math.pi * 2) ** 2)
        thickness = (1.65 + 0.60 * crown + 0.45 * rear + 0.20 * ear
                     + 0.25 * quilt * (0.35 + 0.65 * crown))
        thickness *= (1 - 0.55 * front) * (1 - 0.60 * rim)
        direction = [x / radius[0], y / radius[1], z / radius[2]]
        length = math.sqrt(sum(v * v for v in direction))
        _require(length > 0, "Shell vertex lies at its centre")
        delta = [v / length * thickness for v in direction]
        # Roll the lower edge up; lift the brow away from the visor opening.
        delta[1] = max(0.0, delta[1]) if y < -0.25 else delta[1]
        delta[1] += 0.45 * front * _smooth(-0.4, 0.35, y)
        out.append(tuple(point[a] + delta[a] for a in range(3)))
    return out


def matte_cap_rgba() -> bytes:
    """Neutral gray quilt artwork with diffuse shading and no painted highlights.

    Integer-only periodic tiles are deterministic, logo-free, and do not depend
    on a private image asset. Opaque repaint also affects shared C accessories.
    Actual matte material behavior remains unproved.
    """
    out = bytearray()
    for y in range(256):
        for x in range(256):
            edge = min(x % 32, 31 - x % 32, y % 32, 31 - y % 32)
            value = 109 if edge == 0 else 117 if edge == 1 else 126 + min(edge - 2, 7)
            out.extend((value, value, value, 255))
    return bytes(out)


def _shell(source: models.ModelSpanSource, target: Target):
    resource, decoded, scene = source.parse(target.key)
    _require(len(scene["shapes"]) == 1, "Player shape table changed")
    shape = scene["shapes"][0]
    _require(shape["record_offset"] == target.shape_offset, "Player shape moved")
    material = next(m for m in scene["materials"] if m["index"] == target.shell_material)
    _require(material["name"] == "HI_HELMET_C", "Helmet C material identity changed")
    topology = models._tools_module("nfl_scne_gltf")
    shell_ids, other_ids = set(), set()
    for submesh in scene["submeshes"]:
        indices = {i for _, batch in topology.decode_batches(
            decoded, submesh["command_offset"], submesh["primary_command_word_count"]) for i in batch}
        (shell_ids if submesh["material_index"] == target.shell_material else other_ids).update(indices)
    _require(shell_ids == set(range(target.first_vertex, target.first_vertex + target.shell_vertices))
             and not shell_ids.intersection(other_ids), "C shell shares or changed vertex ownership")
    lanes = models._shape_lanes(scene, shape, decoded)
    positions = models.read_positions(decoded, shape, lanes)
    return resource, decoded, scene, shape, lanes, sorted(shell_ids), positions


def _compile_model(payload: bytes, target: Target, folder: Path) -> tuple[bytes, dict[str, Any]]:
    source = models.ModelSpanSource({target.key: payload})
    resource, before, _scene, shape, lanes, ids, positions = _shell(source, target)
    shell_before = [positions[i] for i in ids]
    shell_after = sculpt_shell(shell_before)
    exported = models.export_model(source, target.key, folder / (target.key + ".gltf"),
                                   include_textures=False, include_skins=True)
    document = json.loads(exported.gltf_path.read_text(encoding="utf-8"))
    gltf = models.GltfFile(exported.gltf_path)
    mesh = next(m for m in document["meshes"] if m["name"] == shape["name"])
    attributes = mesh["primitives"][0]["attributes"]
    source_ids = gltf.accessor(attributes[models.VERTEX_INDEX_ATTRIBUTE])
    accessor = document["accessors"][attributes["POSITION"]]
    view = document["bufferViews"][accessor["bufferView"]]
    _require(accessor["componentType"] == 5126 and accessor["type"] == "VEC3"
             and view["buffer"] == 0, "Exported position layout changed")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", 12)
    binary = bytearray(exported.bin_path.read_bytes())
    edits = dict(zip(ids, shell_after))
    for i, (source_id,) in enumerate(source_ids):
        if int(source_id) in edits:
            struct.pack_into("<3f", binary, start + i * stride, *edits[int(source_id)])
    exported.bin_path.write_bytes(binary)
    all_positions = [edits.get(i, point) for i, point in enumerate(positions)]
    accessor["min"] = [min(p[a] for p in all_positions) for a in range(3)]
    accessor["max"] = [max(p[a] for p in all_positions) for a in range(3)]
    exported.gltf_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    compiled = models.compile_import(source, target.key, exported.gltf_path,
                                    write_normals=False, write_uvs=False, write_colours=False,
                                    allow_rescale=False)
    after, decode_info = source._probe.decode_resource(compiled.rebuilt_span, resource)
    consumed = decode_info["lz"]["consumed_bytes"]
    txtr = models._tools_module("nfl_txtr")
    minimum_scratch = txtr.minimum_vc_lz_overlap_scratch(
        compiled.rebuilt_span[32:32 + consumed], resource.stored_size, len(after))
    _require(minimum_scratch <= resource.word_14, "Model exceeds the retail loader scratch allowance")
    base = models._stream_base({}, shape, lanes.position_stream)
    allowed = {base + i * lanes.position_stride + lanes.position_offset + b for i in ids for b in range(6)}
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    _require(len(after) == len(before) and changed and changed <= allowed,
             "Model differences escaped C-shell position lanes")
    _require(sum(s.positions_changed for s in compiled.shapes) == len(ids)
             and not any(s.rescaled for s in compiled.shapes), "Shell import changed coverage/range")
    decoded_positions = models.read_positions(after, shape, lanes)
    moves = [math.dist(positions[i], decoded_positions[i]) for i in ids]
    report = compiled.report()
    report.update({"profile": PROFILE, "shell_vertices": len(ids),
                   "compression": {"stored_bytes": resource.stored_size, "consumed_bytes": consumed,
                                   "padding_bytes": resource.stored_size - consumed,
                                   "retail_scratch_bytes": resource.word_14,
                                   "exact_minimum_scratch_bytes": minimum_scratch},
                   "shell_vertex_ids": ids, "decoded_changed_bytes": len(changed),
                   "decoded_diff_only_shell_positions": True, "range_constants_identical": True,
                   "move_cm": {"min": min(moves), "max": max(moves), "mean": sum(moves) / len(moves)},
                   "bounds_before": [[min(p[a] for p in shell_before), max(p[a] for p in shell_before)] for a in range(3)],
                   "bounds_after": [[min(decoded_positions[i][a] for i in ids), max(decoded_positions[i][a] for i in ids)] for a in range(3)]})
    return compiled.rebuilt_span, report


def _compile(payload: bytes, target: Target) -> tuple[bytes, dict[str, Any]]:
    if target.shell_material >= 0:
        with tempfile.TemporaryDirectory(prefix="nfl2k5-guardian-") as temporary:
            return _compile_model(payload, target, Path(temporary).resolve())
    from .nfl2k5_p8_texture_writer import compile_live_helmet_span
    return compile_live_helmet_span(payload, matte_cap_rgba())


def apply(payload: bytes, *, key: str | None = None) -> tuple[bytes, dict[str, Any]]:
    """Compile one retail resource, or return this exact installed profile unchanged."""
    payload = bytes(payload)
    state = status(payload, key=key)
    target = _target(payload, key)
    _require(state in {"retail", "applied"} and target is not None,
             "Guardian cap refuses foreign resource bytes")
    assert target is not None
    rebuilt, details = (payload, {}) if state == "applied" else _compile(payload, target)
    _require(len(rebuilt) == len(payload) and rebuilt[:32] == payload[:32]
             and status(rebuilt, key=target.key) == "applied",
             "Guardian-cap compiler output differs from its pinned profile")
    return rebuilt, {
        "schema": SCHEMA, "evidence": EVIDENCE, "profile": PROFILE, "ui_text": UI_TEXT,
        "test_uniform": TEST_UNIFORM, "target": asdict(target), "before": state, "after": "applied",
        "before_sha256": _sha(payload), "after_sha256": _sha(rebuilt),
        "changed_bytes": sum(a != b for a, b in zip(payload, rebuilt)),
        "wrapper_identical": True, "archive_growth": 0, "compiler": details,
    }


def apply_resources(resources: Mapping[str, bytes]) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Stage the complete trial; refuse mixed/foreign bytes before any compilation."""
    resources = {key: bytes(value) for key, value in resources.items()}
    state = resources_status(resources)
    _require(state in {"retail", "applied"}, "Guardian cap refuses missing, mixed or foreign resources")
    output, receipts = {}, []
    for target in TARGETS:
        output[target.key], receipt = apply(resources[target.key], key=target.key)
        receipts.append(receipt)
    return output, {"schema": SCHEMA, "evidence": EVIDENCE, "profile": PROFILE,
                    "ui_text": UI_TEXT, "test_uniform": TEST_UNIFORM, "before": state,
                    "after": resources_status(output), "archive_growth": 0,
                    "resource_bytes": sum(t.size for t in TARGETS), "resources": receipts}


def read_archive_resources(index: Path) -> dict[str, bytes]:
    """Read the three pinned pack extents from an extracted archive, without writes."""
    outer = models._tools_module("nfl_outer")
    archive = outer.parse_archive(Path(index))
    output = {}
    for target in TARGETS:
        outer_index, _ = models.parse_model_key(target.key)
        entry = archive.entries[outer_index]
        expected_id = 0x8EE9EEED if outer_index == 3 else 0x07E10847
        _require(entry.name_id == expected_id and len(entry.segments) == 1,
                 "Guardian-cap archive entry identity/layout changed")
        segment = entry.segments[0]
        relative = target.pack_offset - segment.pack_offset
        _require(str(segment.pack_name) == target.pack and 0 <= relative
                 and relative + target.size <= entry.size, "Guardian-cap archive extent changed")
        output[target.key] = outer.read_entry_range(archive, entry, relative, target.size)
    return output


def _image_locations(descriptor: int, size: int) -> dict[str, int]:
    packs = {name.casefold(): entry for name, entry in models._xdvdfs_pack_entries(descriptor, size).items()}
    locations = {}
    for target in TARGETS:
        pack = packs.get(target.pack.casefold())
        _require(pack is not None and target.pack_offset + target.size <= int(pack.size),
                 f"Guardian cap cannot locate pack {target.pack}")
        offset = int(pack.byte_offset) + target.pack_offset
        _require(0 <= offset and offset + target.size <= size, "Guardian-cap span is outside the image")
        locations[target.key] = offset
    spans = sorted((locations[t.key], locations[t.key] + t.size) for t in TARGETS)
    _require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "Guardian-cap image extents overlap")
    return locations


def _read_image(descriptor: int, locations: Mapping[str, int]) -> dict[str, bytes]:
    return {t.key: platform_compat.pread(descriptor, t.size, locations[t.key]) for t in TARGETS}


def image_status(path: Path) -> str:
    """Read actual XDVDFS pack placement; raw XBE input is foreign/unavailable."""
    try:
        with Path(path).open("rb") as stream:
            locations = _image_locations(stream.fileno(), os.fstat(stream.fileno()).st_size)
            return resources_status(_read_image(stream.fileno(), locations))
    except (OSError, ValueError, struct.error):
        return "foreign"


def apply_to_image(path: Path) -> dict[str, Any]:
    """Resource pass on the build's private COPY. Caller owns copying/publication.

    All three spans compile and revalidate before the first write. On I/O failure
    the caller must discard its incomplete build copy. Never pass the source disc.
    """
    descriptor = os.open(Path(path).resolve(strict=True), os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        size = os.fstat(descriptor).st_size
        locations = _image_locations(descriptor, size)
        original = _read_image(descriptor, locations)
        output, receipt = apply_resources(original)
        _require(os.fstat(descriptor).st_size == size
                 and _image_locations(descriptor, size) == locations
                 and _read_image(descriptor, locations) == original,
                 "Guardian-cap image changed during compilation")
        for target in TARGETS:
            if output[target.key] != original[target.key]:
                written = platform_compat.pwrite(descriptor, output[target.key], locations[target.key])
                _require(written == target.size, "Short guardian-cap write into build copy")
        os.fsync(descriptor)
        _require(os.fstat(descriptor).st_size == size and _read_image(descriptor, locations) == output,
                 "Guardian-cap image verification failed")
        receipt["image_spans"] = [{"key": t.key, "offset": locations[t.key], "size": t.size} for t in TARGETS]
        receipt["image_size_before"] = receipt["image_size_after"] = size
        return receipt
    finally:
        os.close(descriptor)


def main() -> None:
    """Emit reviewable resources and receipts; never modifies the supplied archive."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory for spans and receipt")
    args = parser.parse_args()
    resources, receipt = apply_resources(read_archive_resources(args.index))
    folder = args.output.expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=False)
    for key, span in resources.items():
        (folder / (key + ".span")).write_bytes(span)
    txtr = models._tools_module("nfl_txtr")
    (folder / "detroit-away-cap.png").write_bytes(txtr.encode_rgba_png(256, 256, matte_cap_rgba()))
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"{EVIDENCE}: wrote three fixed spans and receipt to {folder}")


if __name__ == "__main__":
    main()
