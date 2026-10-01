"""Modern helmets and facemasks (beta 76 job hm): the Revolution helmet with the modern Riddell details, and 15
current Riddell facemasks.

EXPERIMENTAL / UNWITNESSED until the lab and Noah's own games.

The game has two selectable helmets and 27 facemasks, all in the common player group (outer 3), shared by every
team (PROVED OFFLINE, ``HM_HELMETS_2026-09-24.md``):

* roster ``+0x0C`` bits 6-7 pick the shell: 0 Standard -> ``HI_HELMET_A`` (team art ``helmet00``), 1 Revolution ->
  ``HI_HELMET_C`` (``helmet02``). ``HI_HELMET_B`` is in the mesh but no route selects it; the Guardian overlay
  sculpts it into a cap, so this module never touches shell B;
* roster ``+0x20`` bits 10-14 pick ``FACEMASK00``..``FACEMASK26`` (one mesh each in ``hi_head``, drawn untextured in
  the kit's facemask colour word) and the 64x64 P8 texture ``maskNN`` (outer 3, chunks 131-157) that the distant
  model draws on ``LO_FACEMASK`` / ``LO_FACEMASK_C``;
* close up the helmet comes from ``hi_head`` (``o3c115``), at distance from ``lo_body`` (``o3c113``).

The shipped mode (``revolution``) keeps the Revolution shell's geometry and texture coordinates, so every team's
helmet art maps exactly as painted, and adds the modern Riddell surface details close up: the flex panel's U-shaped
cut, the temple, crown, rear and side vents, the jaw-flap seam and the rear shelf, as thin parts just above the
shell. They sample a texel that is near black in every team's helmet art and are drawn by the helmet decal submesh
``LOGO_helmet_C`` (the same texture, without the shell's reflection weight), whose commands move into the facemask
run's spare words; their vertices follow the masks there. Facemasks 12-26 become 15 current Riddell masks; the
Standard helmet and masks 0-11 stay retail for the historic teams and the 25 moments, whose few other players are
moved onto them. The distant model is unchanged.

Every shape keeps its vertex count, streams, skin palette and morph records; the owned submeshes' vertex lanes and
push words are rewritten inside the runs of consecutive owned submeshes, the submesh records' command pointers and
word counts follow, and each resource is refitted into its retail stored span with the wrapper unchanged. Decoded
sizes do not change, so the game allocates exactly what it did (zero memory delta). The authored geometry is data
(``data/nfl2k5_modern_helmets/geometry.json``), generated offline by ``tools/nfl2k5_modern_helmets_generate.py``,
so a build copies integers and every platform writes the same bytes. The ``speedflex`` mode (the pass-3 Riddell
SpeedFlex shell in slot C) is research only: its data (``geometry_speedflex.json``) is not part of a release.

Composition: the Guardian overlay changes only shell B's position lanes; this module changes only its own runs. The
two therefore commute on the decoded scene, and the refit is a function of the decoded bytes, so either order gives
the same spans (``classify`` recognises all four states; ``guardian_lanes`` is the overlay's direct B-lane edit).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import nfl2k5_models as models

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "nfl2k5_modern_helmets"
GEOMETRY_PATH = DATA_DIR / "geometry.json"
PINS_PATH = DATA_DIR / "pins.json"
#: The modes: "revolution" (shipped: the retail Revolution shell with the modern details, the 15 modern masks seated
#: on it) and "speedflex" (research: the pass-3 SpeedFlex shell in slot C). Both keep the Standard helmet and masks
#: 0-11 for the classic scenarios.
MODES = ("revolution", "speedflex")
MODE_LABELS = (("Revolution shell with modern details", "revolution"), ("SpeedFlex shell (research, not shipped)", "speedflex"))
MODE_HELP = ("revolution (the shipped mode): the game's own Revolution shell, geometry and texture coordinates unchanged, "
             "with modern surface details and the modern facemasks. speedflex: the pass-3 Riddell SpeedFlex shell, kept "
             "for research; its data is not part of a release.")


def mode_paths(mode: str = "revolution") -> tuple[Path, Path]:
    """(geometry, pins) for a mode: the shipped mode owns geometry.json / pins.json."""
    require(mode in MODES, f"unknown Modern helmets mode {mode!r}")
    suffix = "" if mode == "revolution" else f"_{mode}"
    return DATA_DIR / f"geometry{suffix}.json", DATA_DIR / f"pins{suffix}.json"
SCHEMA = "nfl2k5_modern_helmets/v1"
GEOMETRY_SCHEMA = "nfl2k5_modern_helmets/geometry/v1"
LABEL = "Modern helmets and facemasks"
BUILD_CAPTION = "Modern helmets and facemasks"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: the 2004 Standard and Revolution helmets and 27 facemasks. Patch: the "
    "Revolution helmet keeps its shape and every team's art, and gains the modern Riddell details close up (the "
    "flex panel's U-shaped cut, vents, the jaw seam and the rear shelf); facemasks 12-26 become 15 current Riddell "
    "masks. The Standard helmet and masks 0-11 stay retail for the historic teams and the 25 moments, whose few "
    "other players are moved onto them. The Guardian overlay works with it. Pair it with the league roster's "
    "equipment fields to put the 2026 players in them.")
EVIDENCE = "EXPERIMENTAL / UNWITNESSED"
OUTER = 3
OUTER_ID = 0x8EE9EEED
HI, LO = "o3c115", "o3c113"
KEYS = (HI, LO)
MASK_CHUNKS = tuple(range(131, 158))            # mask00..mask26 (0x8E620 formats "mask%02u")
PUSH_BEGIN_END, PUSH_ARRAY16, PUSH_ARRAY32, PUSH_DRAW_ARRAYS = 0x17FC, 0x1800, 0x1808, 0x1810
TRIANGLE_STRIP = 6
SUBMESH_STRIDE = 0x80
SPHERE_OFFSET, RADIUS_OFFSET = 0x00, 0x48

#: Retail and Guardian-overlay spans (whole stored resource, 32-byte wrapper included).
RETAIL_SPAN_SHA256 = {
    LO: "e3f71e2b930707d68eecfc9c1fa8025da6f1d1ec2087ec3d6ebaa3fa5fec604c",
    HI: "4493cfafede437da6af7ddadfaa172bed3bd674a62801b73af3a99fc66315e43",
}
GUARDIAN_SPAN_SHA256 = {
    LO: "863be42715d650f326c9d001082aa01c4d3b0b0a78b90d04cea8ad43ef057e58",
    HI: "22e198aed7a04be16275d8946adee6ef36ae560020f24e003639313f919d8a8a",
}
#: Shell B (the Guardian overlay's cap): its vertex run and whose position lanes the overlay rewrites.
GUARDIAN_SHELL = {LO: (4229, 120), HI: (10620, 402)}
#: HELMET_C_accessories (the retail chin strap, pads and snaps drawn with helmet C): first vertex, count. Only the
#: speedflex mode writes them, and only their position lanes (parts that would show through the SpeedFlex are pulled
#: inside it); the records' other lanes, the command words and the face morph records stay retail.
ACCESSORIES = {LO: (4024, 97), HI: (9881, 348)}
#: The submesh that may draw the Revolution shell's modern surface details after its own retail triangles, per scene:
#: the helmet C decals (the team's helmet texture, without the shell's reflection weight).
DETAIL_SUBMESH = {HI: "LOGO_helmet_C"}

#: The submeshes this module owns, per resource, in retail submesh order. Everything else stays retail: the
#: Standard shell A and facemasks 0-11 are the classic set that historic teams and the 25 moments keep; the flag,
#: NFL shield, numbers, accessories and mouthpieces are shared with shell A.
OWNED = {
    HI: tuple([f"FACEMASK{i:02d}" for i in range(12, 27)] + ["HI_HELMET_C", "HI_faceshield_C", "LOGO_helmet_C"]),
    LO: ("HI_HELMET_C", "HI_faceshield_C", "LO_FACEMASK_C"),
}
MODERN_MASKS = tuple(range(12, 27))
CLASSIC_MASKS = tuple(range(0, 12))

#: The owned runs of the retail scenes (PROVED OFFLINE by ``parse_layout(..., strict=True)`` on the retail bytes):
#: (first vertex, vertex count, decoded push-word offset, push words, owned submeshes in order). Push buffers are
#: contiguous in submesh order, so a run's words can be re-partitioned among its own submeshes only.
RUNS = {
    HI: ((4470, 4740, 0x1EFE4, 5152, tuple(f"FACEMASK{i:02d}" for i in range(12, 27))),
         (11022, 435, 0x25A7C, 496, ("HI_HELMET_C",)),
         (11477, 20, 0x262A8, 22, ("HI_faceshield_C",)),
         (11509, 12, 0x26348, 18, ("LOGO_helmet_C",))),
    LO: ((4349, 112, 0x10EA0, 139, ("HI_HELMET_C",)),
         (4469, 8, 0x110F4, 10, ("HI_faceshield_C",)),
         (4514, 19, 0x111E8, 23, ("LO_FACEMASK_C",))),
}


class ModernHelmetsError(ValueError):
    """A refusal with a user-facing message; nothing is written."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise ModernHelmetsError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


# ------------------------------------------------------------------------------------------------ scene layout

@dataclass
class Submesh:
    index: int
    name: str
    record: int                 # decoded offset of the 0x80-byte submesh record
    command: int                # decoded offset of its push words
    words: int                  # primary push word count
    vertices: tuple[int, int]   # first, last vertex referenced (inclusive)


@dataclass
class Run:
    """Consecutive owned submeshes: one vertex range and one push-word range, re-partitioned freely."""
    submeshes: list[Submesh]
    first_vertex: int
    vertex_count: int
    command: int
    words: int


@dataclass
class Layout:
    key: str
    shape_record: int
    vertex_count: int
    streams: dict[int, tuple[int, int]]        # stream index -> (decoded offset, stride)
    lanes: models.ShapeLanes
    submeshes: list[Submesh]
    runs: list[Run] = field(default_factory=list)

    def by_name(self) -> dict[str, Submesh]:
        return {s.name: s for s in self.submeshes}


def _relative(decoded: bytes, at: int) -> int | None:
    value = struct.unpack_from("<i", decoded, at)[0]
    return None if value == 0 else at - 1 + value


def parse_layout(key: str, decoded: bytes, *, strict: bool = False) -> Layout:
    """The player shape's streams, submeshes and owned runs. ``strict`` derives the runs from retail bytes (and
    proves ``RUNS``); otherwise the pinned runs are used and every owned submesh must lie inside its run."""
    inventory = models._tools_module("nfl_scne_inventory")
    probe = models._tools_module("nfl_scene_probe")
    outer, chunk = models.parse_model_key(key)
    record = probe.ResourceRecord(outer, "resource-bytes", 0, chunk, 0, "SCNE", 0, len(decoded), 0, 0xFEEDBEEF, 0,
                                  source="resource-bytes")
    parsed, _names, _maps, _sample = inventory.parse_scene(outer * 100_000 + chunk, record, bytes(decoded), {})
    require(len(parsed["shapes"]) == 1, f"{key}: the player scene should hold one shape")
    shape = parsed["shapes"][0]
    lanes = models._shape_lanes(parsed, shape, bytes(decoded))
    models.read_positions(bytes(decoded), shape, lanes)          # fills scale / offset
    streams = {int(s["stream_index"]): (int(s["offset"]), int(s["stride"])) for s in shape["vertex_streams"]}
    materials = {m["index"]: m["name"] for m in parsed["materials"]}
    gltf = models._tools_module("nfl_scne_gltf")
    subs = []
    for s in parsed["submeshes"]:
        batches = gltf.decode_batches(bytes(decoded), int(s["command_offset"]), int(s["primary_command_word_count"]))
        used = [i for _m, b in batches for i in b]
        subs.append(Submesh(int(s["submesh_index"]), materials[s["material_index"]], int(s["record_offset"]),
                            int(s["command_offset"]), int(s["primary_command_word_count"]),
                            (min(used), max(used)) if used else (-1, -1)))
    layout = Layout(key, int(shape["record_offset"]), int(shape["vertex_count"]), streams, lanes, subs)
    owned = set(OWNED[key])
    names = [s.name for s in subs]
    require(owned <= set(names), f"{key}: owned submeshes are missing: {sorted(owned - set(names))}")
    by_name = layout.by_name()
    if strict:
        # retail shape: push buffers contiguous in submesh order, owned vertex ranges consecutive within a run
        order = sorted(subs, key=lambda s: s.command)
        require([s.index for s in order] == [s.index for s in subs], f"{key}: push buffers are not in submesh order")
        for a, b in zip(order, order[1:]):
            require(a.command + 4 * a.words == b.command, f"{key}: push buffers are not contiguous")
        current: list[Submesh] = []
        for s in subs + [None]:                                     # type: ignore[list-item]
            if s is not None and s.name in owned:
                current.append(s)
                continue
            if current:
                first = min(x.vertices[0] for x in current)
                last = max(x.vertices[1] for x in current)
                require(all(a.vertices[1] + 1 == b.vertices[0] for a, b in zip(current, current[1:])),
                        f"{key}: owned vertex ranges are not consecutive")
                layout.runs.append(Run(list(current), first, last - first + 1, current[0].command,
                                       sum(x.words for x in current)))
                current = []
        return layout
    runs = [Run([by_name[m] for m in members], first, count, command, words)
            for first, count, command, words, members in RUNS[key]]
    for run in runs:
        for sub in run.submeshes:
            if sub.name == DETAIL_SUBMESH.get(key):
                # the submesh that draws the shell details: its push words may follow the masks in the facemask
                # run, and its vertices are its own run's plus the details' in the facemask run
                require(any(r.command <= sub.command and sub.command + 4 * sub.words <= r.command + 4 * r.words
                            for r in runs), f"{key} {sub.name}: push words outside the owned runs")
                continue
            require(run.command <= sub.command and sub.command + 4 * sub.words <= run.command + 4 * run.words,
                    f"{key} {sub.name}: push words outside their run")
            require(sub.vertices[0] >= run.first_vertex and sub.vertices[1] < run.first_vertex + run.vertex_count,
                    f"{key} {sub.name}: vertices outside their run")
        layout.runs.append(run)
    for sub in subs:                                               # everything else sits where retail has it
        if sub.name not in owned:
            require(not any(r.command <= sub.command < r.command + 4 * r.words for r in layout.runs),
                    f"{key} {sub.name}: a retail submesh inside an owned run")
    return layout


# ------------------------------------------------------------------------------------------------ push words

def _group_words(indices: Sequence[int]) -> list[int]:
    """ARRAY_ELEMENT16 pairs (headers of up to 2047 pairs) and an odd tail as ARRAY_ELEMENT32."""
    out: list[int] = []
    pairs = [indices[k] | (indices[k + 1] << 16) for k in range(0, len(indices) - 1, 2)]
    for start in range(0, len(pairs), 2047):
        chunk = pairs[start:start + 2047]
        out.extend([0x40000000 | (len(chunk) << 18) | PUSH_ARRAY16] + chunk)
    if len(indices) % 2:
        out.extend([(1 << 18) | PUSH_ARRAY32, indices[-1]])
    return out


def encode_strip(indices: Sequence[int]) -> list[int]:
    """BEGIN(strip), the indices, END, in the fewest push words: ascending runs of consecutive indices as
    DRAW_ARRAYS (two words per run of up to 256, as the retail scenes do), everything else as ARRAY_ELEMENT16
    pairs with an odd leftover as ARRAY_ELEMENT32. A linear dynamic programme picks the split (a group of L plain
    indices costs L // 2 + 1 words, plus 2 when L is odd; a group of 0 costs nothing, of 1 costs 2).
    ``nfl_scne_gltf.decode_batches`` reads the words back to exactly ``indices``."""
    require(len(indices) >= 3, "a strip needs three indices")
    require(all(0 <= i < 0xFFFF for i in indices), "strip index out of range")
    require(len(indices) <= 4094, "a strip longer than 4,094 indices needs a second ARRAY_ELEMENT16 header")
    n = len(indices)
    seq_end = [0] * n
    for k in range(n - 1, -1, -1):
        seq_end[k] = seq_end[k + 1] if k + 1 < n and indices[k + 1] == indices[k] + 1 else k + 1
    inf = 1 << 60
    best = [inf] * (n + 1)          # best[m]: fewest words for indices[:m] when m ends a DRAW_ARRAYS (or m == 0)
    came: list[tuple[int, int] | None] = [None] * (n + 1)
    best[0] = 0
    # running minima of 2*best[i] - i over i <= k - 2, split by the parity of i
    run_min = [inf, inf]
    run_arg = [-1, -1]
    tail = None
    for k in range(n + 1):
        if k >= 2 and best[k - 2] < inf:
            i = k - 2
            value = 2 * best[i] - i
            if value < run_min[i % 2]:
                run_min[i % 2], run_arg[i % 2] = value, i
        options = []
        if best[k] < inf:
            options.append((2 * best[k], k))                                  # empty group
        if k >= 1 and best[k - 1] < inf:
            options.append((2 * (best[k - 1] + 2), k - 1))                     # one index (ARRAY_ELEMENT32)
        if run_min[k % 2] < inf:                                               # even group of 2 or more
            options.append((run_min[k % 2] + k + 2, run_arg[k % 2]))
        if run_min[1 - k % 2] < inf:                                           # odd group of 3 or more
            options.append((run_min[1 - k % 2] + k + 5, run_arg[1 - k % 2]))
        cost2, group_from = min(options)
        group_best = cost2 // 2
        if k == n:
            tail = (group_best, group_from)
            break
        for m in range(k + 1, min(seq_end[k], k + 256) + 1):
            if group_best + 2 < best[m]:
                best[m], came[m] = group_best + 2, (group_from, k)
    assert tail is not None
    pieces: list[tuple[str, int, int]] = [("group", tail[1], n)]
    start = tail[1]
    while start > 0:
        group_from, k = came[start]            # type: ignore[misc]
        pieces += [("draw", k, start), ("group", group_from, k)]
        start = group_from
    out = [(1 << 18) | PUSH_BEGIN_END, TRIANGLE_STRIP]
    for kind, a, b in reversed(pieces):
        if kind == "group":
            out.extend(_group_words(indices[a:b]))
        else:
            out.extend([(1 << 18) | PUSH_DRAW_ARRAYS, indices[a] | ((b - a - 1) << 24)])
    out += [(1 << 18) | PUSH_BEGIN_END, 0]
    require(len(out) == tail[0] + 4, "push word packing mismatch")
    return out


# ------------------------------------------------------------------------------------------------ geometry data

@dataclass
class Part:
    """One authored submesh: stream records (hi: 16 bytes per vertex; lo: 24) and one strip of local indices."""
    name: str
    records: bytes              # per vertex: stream 0 (10 B), stream 1 (6 B)[, stream 2 (8 B)]
    strip: list[int]
    slot_selector: int          # SHORT1 selector written into stream 1 (3 x palette slot)


def _b64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def load_geometry(path: Path | None = None, mode: str = "revolution") -> dict[str, Any]:
    path = mode_paths(mode)[0] if path is None else Path(path)
    require(path.is_file(), f"the modern helmet geometry is missing: {path}")
    stat = path.stat()
    return _load_json(str(path), stat.st_size, stat.st_mtime_ns, GEOMETRY_SCHEMA)


@__import__("functools").lru_cache(maxsize=4)
def _load_json(path: str, size: int, mtime_ns: int, schema: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    require(document.get("schema") == schema, f"{Path(path).name} has another schema")
    return document


def parts_for(document: Mapping[str, Any], key: str) -> dict[str, Part]:
    entry = document["resources"][key]
    out = {}
    for name, item in entry["parts"].items():
        strip = list(struct.unpack(f"<{len(_b64(item['strip'])) // 2}H", _b64(item["strip"])))
        out[name] = Part(name, _b64(item["records"]), strip, int(item.get("selector", -1)))
    return out


def record_size(layout: Layout) -> int:
    return sum(stride for _offset, stride in layout.streams.values())


def read_records(layout: Layout, decoded: bytes, first: int, count: int) -> bytes:
    """Interleaved stream records (stream order) of vertices first..first+count-1."""
    out = bytearray()
    for v in range(first, first + count):
        for s in sorted(layout.streams):
            base, stride = layout.streams[s]
            out += decoded[base + v * stride: base + (v + 1) * stride]
    return bytes(out)


def write_records(layout: Layout, output: bytearray, first: int, records: bytes) -> None:
    size = record_size(layout)
    require(len(records) % size == 0, f"{layout.key}: vertex records are not whole")
    for k in range(len(records) // size):
        at = k * size
        for s in sorted(layout.streams):
            base, stride = layout.streams[s]
            output[base + (first + k) * stride: base + (first + k + 1) * stride] = records[at:at + stride]
            at += stride


# ------------------------------------------------------------------------------------------------ authoring

def author(key: str, decoded: bytes, document: Mapping[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """Write the authored parts into their runs. Only owned bytes change (``owned_mask``)."""
    layout = parse_layout(key, decoded)
    entry = document["resources"][key]
    expect = entry["shape"]
    lanes = layout.lanes
    require(layout.vertex_count == expect["vertex_count"], f"{key}: the shape's vertex count changed")
    require(abs(lanes.scale - expect["scale"]) == 0 and list(lanes.offset) == expect["offset"]
            and [*lanes.uv_scale, *lanes.uv_offset] == expect["uv"], f"{key}: the shape's range constants changed")
    parts = parts_for(document, key)
    size = record_size(layout)
    output = bytearray(decoded)
    receipt = {"key": key, "runs": []}
    for run in layout.runs:
        present = [sub.name in parts for sub in run.submeshes]
        if not any(present):
            continue                                  # this mode leaves the run retail
        require(all(present), f"{key}: the document covers only part of the run at vertex {run.first_vertex}")
        vertex, command = run.first_vertex, run.command
        words_used = verts_used = 0
        for sub in run.submeshes:
            part = parts[sub.name]
            count = len(part.records) // size
            require(count >= 1, f"{key} {sub.name}: no vertices")
            require(max(part.strip) < count, f"{key} {sub.name}: strip index beyond its vertices")
            require(verts_used + count <= run.vertex_count, f"{key}: run at vertex {run.first_vertex} overflows its "
                    f"{run.vertex_count} vertices")
            write_records(layout, output, vertex, part.records)
            words = encode_strip([vertex + i for i in part.strip])
            require(words_used + len(words) <= run.words, f"{key}: run at 0x{run.command:x} overflows its "
                    f"{run.words} push words")
            struct.pack_into(f"<{len(words)}I", output, command, *words)
            struct.pack_into("<i", output, sub.record + 0x78, command - (sub.record + 0x78) + 1)
            struct.pack_into("<HH", output, sub.record + 0x7C, len(words), 0)
            vertex += count
            command += 4 * len(words)
            verts_used += count
            words_used += len(words)
        detail = entry.get("shell_detail")
        if detail and any(sub.name == detail["host"] for sub in run.submeshes):
            require(detail["submesh"] == DETAIL_SUBMESH.get(key), f"{key}: shell details may only be drawn by "
                    f"{DETAIL_SUBMESH.get(key)}")
            # modern surface details on the retail shell: their vertices follow the masks in this run, and the
            # drawing submesh's command buffer (its own retail triangles, then the details) follows the masks' commands
            records = base64.b64decode(detail["records"])
            count = len(records) // size
            require(verts_used + count <= run.vertex_count, f"{key}: the shell details overflow the run's vertices")
            write_records(layout, output, vertex, records)
            retail_strip = list(struct.unpack(f"<{len(base64.b64decode(detail['retail_strip'])) // 2}H",
                                              base64.b64decode(detail["retail_strip"])))
            local = list(struct.unpack(f"<{len(base64.b64decode(detail['strip'])) // 2}H", base64.b64decode(detail["strip"])))
            joined = list(retail_strip)
            if local:
                joined += [joined[-1], vertex + local[0]]
                if len(joined) % 2:
                    joined.append(vertex + local[0])
                joined += [vertex + i for i in local]
            words = encode_strip(joined)
            require(words_used + len(words) <= run.words, f"{key}: the shell details overflow the run's push words")
            struct.pack_into(f"<{len(words)}I", output, command, *words)
            target = layout.by_name()[detail["submesh"]]
            struct.pack_into("<i", output, target.record + 0x78, command - (target.record + 0x78) + 1)
            struct.pack_into("<HH", output, target.record + 0x7C, len(words), 0)
            vertex += count
            command += 4 * len(words)
            verts_used += count
            words_used += len(words)
            receipt["shell_detail"] = {"vertices": count, "words": len(words), "submesh": detail["submesh"]}
        # spare vertices repeat the run's last record (never drawn; compress to nothing); spare words are zero
        last = read_records(layout, bytes(output), vertex - 1, 1)
        spare = run.vertex_count - verts_used
        if spare:
            write_records(layout, output, vertex, last * spare)
        output[command:run.command + 4 * run.words] = bytes(run.command + 4 * run.words - command)
        receipt["runs"].append({"first_vertex": run.first_vertex, "vertex_budget": run.vertex_count,
                                "vertices": verts_used, "word_budget": run.words, "words": words_used,
                                "submeshes": [s.name for s in run.submeshes]})
    moved = entry.get("accessory_positions")
    if moved:
        first, count = ACCESSORIES[key]
        data = base64.b64decode(moved)
        require(len(data) == 6 * count, f"{key}: accessory positions for {count} vertices expected")
        base = layout.streams[lanes.position_stream][0]
        for i in range(count):
            at = base + (first + i) * lanes.position_stride + lanes.position_offset
            output[at:at + 6] = data[6 * i:6 * i + 6]
        receipt["accessories"] = count
    sphere = entry.get("sphere")
    if sphere:
        struct.pack_into("<4f", output, layout.shape_record + SPHERE_OFFSET, sphere[0], sphere[1], sphere[2], 1.0)
        struct.pack_into("<f", output, layout.shape_record + RADIUS_OFFSET, sphere[3])
    return bytes(output), receipt


def owned_mask(key: str, decoded: bytes) -> bytearray:
    """1 for every decoded byte this module may change (its runs, the owned submesh records' push fields, the
    shape's culling sphere), 0 elsewhere. The layout is read from retail-shaped fields only."""
    layout = parse_layout(key, decoded)
    mask = bytearray(len(decoded))
    for run in layout.runs:
        for s in sorted(layout.streams):
            base, stride = layout.streams[s]
            mask[base + run.first_vertex * stride: base + (run.first_vertex + run.vertex_count) * stride] = \
                b"\x01" * (run.vertex_count * stride)
        mask[run.command:run.command + 4 * run.words] = b"\x01" * (4 * run.words)
        for sub in run.submeshes:
            mask[sub.record + 0x78:sub.record + 0x80] = b"\x01" * 8
    mask[layout.shape_record + SPHERE_OFFSET:layout.shape_record + SPHERE_OFFSET + 16] = b"\x01" * 16
    mask[layout.shape_record + RADIUS_OFFSET:layout.shape_record + RADIUS_OFFSET + 4] = b"\x01" * 4
    first, count = ACCESSORIES[key]
    lanes = layout.lanes
    base = layout.streams[lanes.position_stream][0]
    for v in range(first, first + count):
        at = base + v * lanes.position_stride + lanes.position_offset
        mask[at:at + 6] = b"\x01" * 6
    return mask


def guardian_mask(key: str, decoded: bytes) -> bytearray:
    """1 for the Guardian overlay's bytes: shell B's position lanes (6 bytes per vertex)."""
    layout = parse_layout(key, decoded)
    first, count = GUARDIAN_SHELL[key]
    lanes = layout.lanes
    base = layout.streams[lanes.position_stream][0]
    mask = bytearray(len(decoded))
    for v in range(first, first + count):
        at = base + v * lanes.position_stride + lanes.position_offset
        mask[at:at + 6] = b"\x01" * 6
    return mask


def guardian_lanes(key: str, decoded: bytes) -> bytes:
    """The Guardian overlay's edit as a direct lane write: shell B sculpted (``nfl2k5_guardian_cap.sculpt_shell``)
    and quantised exactly as the Models importer does it (PROVED OFFLINE byte-identical to the pinned overlay)."""
    from . import nfl2k5_guardian_cap as cap
    layout = parse_layout(key, decoded)
    first, count = GUARDIAN_SHELL[key]
    lanes = layout.lanes
    shape_positions = _positions(layout, decoded)
    ids = list(range(first, first + count))
    after = cap.sculpt_shell([shape_positions[i] for i in ids])
    out = bytearray(decoded)
    base = layout.streams[lanes.position_stream][0]
    f32 = lambda value: struct.unpack("<f", struct.pack("<f", value))[0]   # noqa: E731 (the glTF round trip)
    for i, point in zip(ids, after):
        q = tuple(models.encode_normshort(max(-1.0, min(1.0, (f32(point[a]) - lanes.offset[a]) / lanes.scale)))
                  for a in range(3))
        struct.pack_into("<3h", out, base + i * lanes.position_stride + lanes.position_offset, *q)
    return bytes(out)


def _positions(layout: Layout, decoded: bytes) -> list[tuple[float, float, float]]:
    lanes = layout.lanes
    base = layout.streams[lanes.position_stream][0]
    out = []
    for v in range(layout.vertex_count):
        q = struct.unpack_from("<3h", decoded, base + v * lanes.position_stride + lanes.position_offset)
        out.append(tuple(models.normshort(q[a]) * lanes.scale + lanes.offset[a] for a in range(3)))
    return out


def _select(decoded: bytes, mask: bytes, value: int) -> bytes:
    return bytes(b for b, m in zip(decoded, mask) if m == value)


# ------------------------------------------------------------------------------------------------ digests / states

def region_digests(key: str, decoded: bytes) -> dict[str, str]:
    """sha256 of the owned bytes, of shell B's position lanes (the Guardian overlay's) and of everything else."""
    owned = owned_mask(key, decoded)
    guard = guardian_mask(key, decoded)
    require(not any(a and b for a, b in zip(owned, guard)), f"{key}: owned bytes overlap the Guardian lanes")
    other = bytes(1 if (a or b) else 0 for a, b in zip(owned, guard))
    return {"owned": sha(_select(decoded, owned, 1)), "guardian": sha(_select(decoded, guard, 1)),
            "other": sha(_select(decoded, other, 0))}


def classify(key: str, decoded: bytes, pins: Mapping[str, Any]) -> tuple[str, str]:
    """(helmets state, Guardian state): ('retail' | 'applied' | 'foreign', 'retail' | 'guardian' | 'foreign')."""
    pin = pins["scenes"][key]
    try:
        d = region_digests(key, decoded)
    except (ModernHelmetsError, ValueError, KeyError, IndexError, struct.error):
        return "foreign", "foreign"
    if d["other"] != pin["other"]:
        return "foreign", "foreign"
    if pin["owned_retail"] == pin["owned_applied"]:
        helmets = "unchanged" if d["owned"] == pin["owned_retail"] else "foreign"
    else:
        helmets = {pin["owned_retail"]: "retail", pin["owned_applied"]: "applied"}.get(d["owned"], "foreign")
    guardian = {pin["guardian_retail"]: "retail", pin["guardian_applied"]: "guardian"}.get(d["guardian"], "foreign")
    return helmets, guardian


def decode_span(key: str, span: bytes) -> bytes:
    source = models.ModelSpanSource({key: bytes(span)})
    return source.decode_span(bytes(span), source.resource(key))


def refit(template_span: bytes, decoded: bytes) -> bytes:
    """The fixed-span refit every writer of these two resources uses (wrapper, scratch word included, unchanged).
    Deterministic in the decoded bytes, so two writers applied in either order produce the same span."""
    fill = models._tools_module("nfl_vc_lz_fill")
    rebuilt, info = fill.rebuild_fixed_span_filled(bytes(template_span), bytes(decoded), encoder="auto")
    require(info.wrapper_identical and len(rebuilt) == len(template_span), "refit changed the wrapper or size")
    require(decode_span_bytes(rebuilt, template_span) == bytes(decoded), "refit failed its decode check")
    return rebuilt


def decode_span_bytes(span: bytes, template_span: bytes) -> bytes:
    tx = models._tools_module("nfl_txtr")
    chunk = tx.parse_chunks(bytes(span), allow_trailing=True)[0]
    out, _info = tx.decode_chunk(bytes(span), chunk)
    return out


def compile_scene(key: str, span: bytes, document: Mapping[str, Any], pins: Mapping[str, Any]) -> tuple[bytes, dict]:
    """The helmets edit of one player scene span, whatever the Guardian overlay's state."""
    decoded = decode_span_bytes(span, span)
    helmets, guardian = classify(key, decoded, pins)
    require(helmets != "foreign" and guardian != "foreign",
            f"{key}: the player scene is not retail, Modern helmets or the Guardian overlay; rebuild from a "
            f"supported USA source")
    if helmets == "applied":
        return bytes(span), {"key": key, "state": "already_applied", "guardian": guardian}
    if helmets == "unchanged":
        return bytes(span), {"key": key, "state": "unchanged", "guardian": guardian}
    authored, receipt = author(key, decoded, document)
    require(classify(key, authored, pins) == ("applied", guardian), f"{key}: the authored scene differs from its pin")
    rebuilt = refit(span, authored)
    expected = pins["scenes"][key]["span_applied" if guardian == "retail" else "span_composed"]
    require(sha(rebuilt) == expected, f"{key}: the refitted span differs from its pin")
    return rebuilt, {"key": key, "state": "applied", "guardian": guardian, "runs": receipt["runs"],
                     "after_sha256": sha(rebuilt)}


def apply_guardian_lanes(key: str, span: bytes, pins: Mapping[str, Any]) -> bytes:
    """The Guardian overlay's shell-B edit on a Modern-helmets span (the other order of the composition)."""
    decoded = decode_span_bytes(span, span)
    helmets, guardian = classify(key, decoded, pins)
    require(helmets in ("applied", "unchanged") and guardian in ("retail", "guardian"), f"{key}: not a Modern helmets scene")
    if guardian == "guardian":
        return bytes(span)
    composed = guardian_lanes(key, decoded)
    require(classify(key, composed, pins) == ("applied", "guardian"), f"{key}: the Guardian lanes differ from the pin")
    rebuilt = refit(span, composed)
    require(sha(rebuilt) == pins["scenes"][key]["span_composed"], f"{key}: the composed span differs from its pin")
    return rebuilt


# ------------------------------------------------------------------------------------------------ mask textures

def mask_alpha(document: Mapping[str, Any], slot: int) -> bytes:
    alpha = _b64(document["mask_alpha"][str(slot)])
    require(len(alpha) == 64 * 64, f"mask{slot:02d}: the alpha map is not 64 x 64")
    return alpha


def compile_mask_texture(alpha: bytes, template_span: bytes) -> bytes:
    """A 64 x 64 P8 facemask texture (retail layout: one level, palette at 4096, white with an alpha ramp like the
    retail masks), refitted into the retail stored span with the wrapper unchanged."""
    tx = models._tools_module("nfl_txtr")
    kind, stored, system, video, magic, scratch, r0, r1 = struct.unpack_from("<4s7I", template_span)
    require(kind == b"TXTR" and system == 128 and video == 5120 and stored == len(template_span) - 32,
            "the facemask texture allocation changed")
    chunk = tx.Chunk(0, 0, "TXTR", stored, system, video, magic, scratch, r0, r1)
    decoded, _info = tx.decode_chunk(bytes(template_span), chunk)
    texture = tx.parse_texture(decoded, chunk)
    require(texture.format_name == "P8" and (texture.width, texture.height, texture.mip_levels) == (64, 64, 1)
            and texture.pixel_offset == 0 and texture.palette_offset == 4096, "the facemask texture layout changed")
    levels = sorted(set(alpha))
    require(len(levels) <= 256, "too many alpha levels")
    index_of = {a: i for i, a in enumerate(levels)}
    palette = bytearray(1024)
    for i, a in enumerate(levels):
        palette[i * 4:i * 4 + 4] = bytes((0xFF, 0xFD, 0xFF, a))          # B G R A, the retail masks' white
    new = decoded[:system] + tx.swizzle_2d(bytes(index_of[a] for a in alpha), 64, 64, 1) + bytes(palette)
    require(len(new) == len(decoded), "the facemask texture size changed")
    return refit(template_span, new)


# ------------------------------------------------------------------------------------------------ outer 3

def load_pins(path: Path | None = None, mode: str = "revolution") -> dict[str, Any]:
    path = mode_paths(mode)[1] if path is None else Path(path)
    require(path.is_file(), f"the modern helmet pins are missing: {path}")
    stat = path.stat()
    return _load_json(str(path), stat.st_size, stat.st_mtime_ns, SCHEMA)


def _chunks(payload: bytes) -> list:
    tx = models._tools_module("nfl_txtr")
    return tx.parse_chunks(bytes(payload), allow_trailing=True)


def _chunk_span(payload: bytes, chunk) -> bytes:
    return bytes(payload[chunk.offset:chunk.offset + 32 + chunk.stored_size])


def collection_status(payload: bytes, pins: Mapping[str, Any] | None = None) -> str:
    """retail / applied / foreign for the helmets part of outer 3 (any Guardian overlay state is accepted)."""
    pins = load_pins() if pins is None else pins
    try:
        chunks = _chunks(payload)
        states = set()
        for key in KEYS:
            _outer, index = models.parse_model_key(key)
            state = classify(key, decode_span_bytes(_chunk_span(payload, chunks[index]), b""), pins)[0]
            if state != "unchanged":
                states.add(state)
        for slot in MODERN_MASKS:
            digest = sha(_chunk_span(payload, chunks[MASK_CHUNKS[slot]]))
            states.add({pins["masks"][str(slot)]["retail"]: "retail",
                        pins["masks"][str(slot)]["applied"]: "applied"}.get(digest, "foreign"))
    except (ModernHelmetsError, ValueError, IndexError, KeyError, struct.error):
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def compile_collection(payload: bytes, document: Mapping[str, Any] | None = None,
                       pins: Mapping[str, Any] | None = None) -> tuple[bytes, dict[str, Any]]:
    """Outer 3 with the helmets written (same size; spans replaced in place)."""
    document = load_geometry() if document is None else document
    pins = load_pins() if pins is None else pins
    out = bytearray(payload)
    chunks = _chunks(payload)
    receipt: dict[str, Any] = {"scenes": [], "masks": []}
    for key in KEYS:
        _outer, index = models.parse_model_key(key)
        chunk = chunks[index]
        span = _chunk_span(payload, chunk)
        new, rec = compile_scene(key, span, document, pins)
        out[chunk.offset:chunk.offset + len(new)] = new
        receipt["scenes"].append(rec)
    for slot in MODERN_MASKS:
        chunk = chunks[MASK_CHUNKS[slot]]
        span = _chunk_span(payload, chunk)
        pin = pins["masks"][str(slot)]
        if sha(span) == pin["applied"]:
            continue
        require(sha(span) == pin["retail"], f"mask{slot:02d}: the texture is not retail")
        new = compile_mask_texture(mask_alpha(document, slot), span)
        require(sha(new) == pin["applied"], f"mask{slot:02d}: the texture differs from its pin")
        out[chunk.offset:chunk.offset + len(new)] = new
        receipt["masks"].append(slot)
    require(len(out) == len(payload), "outer 3 changed size")
    require(collection_status(bytes(out), pins) == "applied", "the helmets read-back failed")
    return bytes(out), receipt


MASK_CHUNKS = {slot: 131 + slot for slot in range(27)}


# ------------------------------------------------------------------------------------------------ historic teams

HISTORIC_OUTERS = tuple(range(113, 188))
RECORD_SIZE = 0x54


def _historic_players(payload: bytes):
    from . import nfl2k5_roster_records as rr
    require(len(payload) > 32 and payload[:4] == b"ROST", "not a historic roster resource")
    return rr.RosterDocument(bytes(payload[32:])).players


def _get_field(payload: bytes, record: int, name: str) -> int:
    from . import nfl2k5_roster_records as rr
    spec = rr.FIELD_BY_NAME[name]
    raw = int.from_bytes(payload[record + spec.offset:record + spec.offset + spec.size], "little")
    return (raw >> spec.shift) & ((1 << spec.width) - 1)


def _set_field(payload: bytearray, record: int, name: str, value: int) -> None:
    from . import nfl2k5_roster_records as rr
    spec = rr.FIELD_BY_NAME[name]
    at = record + spec.offset
    raw = int.from_bytes(payload[at:at + spec.size], "little")
    mask = ((1 << spec.width) - 1) << spec.shift
    raw = (raw & ~mask) | ((value << spec.shift) & mask)
    payload[at:at + spec.size] = raw.to_bytes(spec.size, "little")


def historic_edits(document: Mapping[str, Any] | None = None) -> dict[int, list]:
    """{outer: [[player index, field, retail value, classic value], ...]} (the Standard shell and masks 0-11)."""
    document = load_geometry() if document is None else document
    return {int(k): v for k, v in document["historic_edits"].items()}


def _record_offsets(payload: bytes) -> dict[int, int]:
    return {p.index: 32 + p.offset for p in _historic_players(payload)}


def historic_state(payload: bytes, outer: int, edits: Mapping[int, list] | None = None) -> str:
    """retail / applied / foreign, field level: only the listed equipment fields are read, so other writers of the
    same file (the historic rosters, One-pool positions, the EDGE rename) never make it foreign."""
    edits = historic_edits() if edits is None else edits
    rows = edits.get(outer, [])
    if not rows:
        return "retail"
    try:
        offsets = _record_offsets(payload)
        states = set()
        for index, name, retail_value, classic_value in rows:
            value = _get_field(payload, offsets[index], name)
            states.add("retail" if value == retail_value else "applied" if value == classic_value else "foreign")
    except (ModernHelmetsError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    return states.pop() if len(states) == 1 else "foreign"


def compile_historic(payload: bytes, outer: int, edits: Mapping[int, list] | None = None) -> bytes:
    edits = historic_edits() if edits is None else edits
    state = historic_state(payload, outer, edits)
    require(state in ("retail", "applied"), f"historic outer {outer}: the equipment fields are foreign")
    if state == "applied":
        return bytes(payload)
    out = bytearray(payload)
    offsets = _record_offsets(payload)
    for index, name, _retail_value, classic_value in edits[outer]:
        _set_field(out, offsets[index], name, classic_value)
    require(historic_state(bytes(out), outer, edits) == "applied", f"historic outer {outer}: read-back failed")
    return bytes(out)


def without_equipment_edits(payload: bytes, outer: int, edits: Mapping[int, list] | None = None) -> bytes:
    """The payload with this module's historic equipment edits put back to retail (for a whole-file pin such as
    the historic rosters' own). Anything else is returned as is."""
    try:
        edits = historic_edits() if edits is None else edits
    except ModernHelmetsError:
        return payload
    rows = edits.get(outer, [])
    if not rows or historic_state(payload, outer, edits) != "applied":
        return payload
    out = bytearray(payload)
    offsets = _record_offsets(payload)
    for index, name, retail_value, _classic_value in rows:
        _set_field(out, offsets[index], name, retail_value)
    return bytes(out)


# ------------------------------------------------------------------------------------------------ pins

def record_pins(outer3_retail: bytes, document: Mapping[str, Any] | None = None, mode: str = "revolution") -> dict[str, Any]:
    """Pins from a retail outer 3: every scene state (retail, helmets, Guardian, both orders composed) and the
    modern mask textures. Raises if the two orders of the composition disagree."""
    document = load_geometry(mode=mode) if document is None else document
    geometry = mode_paths(mode)[0]
    chunks = _chunks(outer3_retail)
    pins: dict[str, Any] = {"schema": SCHEMA, "mode": mode,
                            "geometry_sha256": sha(geometry.read_bytes()) if geometry.is_file() else None,
                            "scenes": {}, "masks": {}}
    for key in KEYS:
        _outer, index = models.parse_model_key(key)
        span = _chunk_span(outer3_retail, chunks[index])
        require(sha(span) == RETAIL_SPAN_SHA256[key], f"{key}: the source is not the retail scene")
        retail = decode_span_bytes(span, span)
        authored, _receipt = author(key, retail, document)
        guarded = guardian_lanes(key, retail)
        both_a = guardian_lanes(key, authored)
        both_b, _r2 = author(key, guarded, document)
        require(both_a == both_b, f"{key}: the helmets and the Guardian lanes do not commute")
        d_r, d_a, d_g = region_digests(key, retail), region_digests(key, authored), region_digests(key, guarded)
        require(d_r["other"] == d_a["other"] == d_g["other"], f"{key}: an edit escaped its region")
        unchanged = authored == retail                 # a scene this mode leaves retail keeps the retail span
        span_applied = span if unchanged else refit(span, authored)
        span_guardian = refit(span, guarded)
        require(sha(span_guardian) == GUARDIAN_SPAN_SHA256[key], f"{key}: the Guardian overlay's span differs from its pin")
        span_composed = span_guardian if unchanged else refit(span, both_a)
        pins["scenes"][key] = {"other": d_r["other"], "owned_retail": d_r["owned"], "owned_applied": d_a["owned"],
                               "guardian_retail": d_r["guardian"], "guardian_applied": d_g["guardian"],
                               "span_retail": sha(span), "span_applied": sha(span_applied),
                               "span_guardian": sha(span_guardian), "span_composed": sha(span_composed),
                               "stored": len(span) - 32}
    for slot in MODERN_MASKS:
        span = _chunk_span(outer3_retail, chunks[MASK_CHUNKS[slot]])
        new = compile_mask_texture(mask_alpha(document, slot), span)
        pins["masks"][str(slot)] = {"retail": sha(span), "applied": sha(new), "stored": len(span) - 32}
    return pins


# ------------------------------------------------------------------------------------------------ disc image

def _outer_image():
    import sys as _sys
    tools = ROOT / "tools"
    if str(tools) not in _sys.path:
        _sys.path.insert(0, str(tools))
    import nfl2k5_playbook_position_recode as recode
    return recode.OuterImage


def _read_entry(archive, index: int) -> bytes:
    entry = archive.entries[index]
    return archive.read(entry.virtual_offset, entry.size)


def image_status(path: Path | str, mode: str = "revolution") -> str:
    """retail / applied / foreign for one mode: the player scenes, the modern mask textures and the historic
    equipment fields (an image with the other mode reads foreign)."""
    try:
        pins = load_pins(mode=mode)
        edits = historic_edits(load_geometry(mode=mode))
        with _outer_image()(str(path)) as archive:
            state = collection_status(_read_entry(archive, OUTER), pins)
            historic = {historic_state(_read_entry(archive, outer), outer, edits) for outer in edits}
    except (ModernHelmetsError, OSError, ValueError, KeyError, IndexError, struct.error):
        return "foreign"
    states = {state} | historic
    return states.pop() if len(states) == 1 else "foreign"


def image_mode(path: Path | str) -> str | None:
    """The mode an image already carries, or None (retail or foreign)."""
    for mode in MODES:
        if image_status(path, mode) == "applied":
            return mode
    return None


def apply_to_image(path: Path | str, *, mode: str = "revolution",
                   progress: Callable[[str, int, int], None] | None = None) -> dict[str, Any]:
    """Build step: write the helmets (outer 3 spans in place) and the historic equipment fields into the
    disposable output image. Same-size writes; the Guardian overlay may be on the image already, or come later."""
    say = progress or (lambda message, done, total: None)
    document, pins = load_geometry(mode=mode), load_pins(mode=mode)
    edits = historic_edits(document)
    receipt: dict[str, Any] = {"label": LABEL, "mode": mode, "evidence": EVIDENCE, "runtime_witnessed": False,
                               "historic": []}
    with _outer_image()(str(path), writable=True) as archive:
        entry = archive.entries[OUTER]
        before = archive.read(entry.virtual_offset, entry.size)
        require(collection_status(before, pins) in ("retail", "applied"),
                "Modern helmets: the common player group is not retail, helmets or the Guardian overlay")
        say("Modern helmets: player scenes and facemask textures", 0, 2)
        after, receipt["collection"] = compile_collection(before, document, pins)
        for chunk in _chunks(before):
            a, b = _chunk_span(before, chunk), _chunk_span(after, chunk)
            if a != b:
                archive.write(entry.virtual_offset + chunk.offset, b)
        require(archive.read(entry.virtual_offset, entry.size) == after, "Modern helmets: write-back differs")
        say("Modern helmets: classic equipment on the historic teams", 1, 2)
        for outer, rows in sorted(edits.items()):
            e = archive.entries[outer]
            raw = archive.read(e.virtual_offset, e.size)
            new = compile_historic(raw, outer, edits)
            if new != raw:
                spans = [(k, new[k]) for k in range(len(raw)) if raw[k] != new[k]]
                archive.write(e.virtual_offset, new)
                require(archive.read(e.virtual_offset, e.size) == new, f"historic outer {outer}: write-back differs")
                receipt["historic"].append({"outer": outer, "records": len({r[0] for r in rows}),
                                            "changed_bytes": len(spans)})
    say("Modern helmets: done", 2, 2)
    receipt["status"] = image_status(path, mode)
    require(receipt["status"] == "applied", "Modern helmets: the image read-back is not applied")
    return receipt


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="python3 -m mod_editor.core.nfl2k5_modern_helmets", description=LABEL)
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("status", help="retail / applied / foreign for a disc image or loose packs (last line)")
    st.add_argument("source")
    st.add_argument("--mode", choices=MODES, default=None, help="default: whichever mode the image carries")
    ap = sub.add_parser("apply-lab", help="lab only: write the helmets into a disposable disc image copy")
    ap.add_argument("disc")
    ap.add_argument("--mode", choices=MODES, default="revolution")
    rp = sub.add_parser("record-pins", help="record the pins from a retail disc image or loose packs")
    rp.add_argument("source")
    rp.add_argument("--mode", choices=MODES, default="revolution")
    rp.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    if args.command == "status":
        if args.mode is None:
            found = image_mode(args.source)
            print(f"mode: {found or 'none'}")
            print("applied" if found else image_status(args.source))
        else:
            print(image_status(args.source, args.mode))
        return 0
    if args.command == "apply-lab":
        receipt = apply_to_image(args.disc, mode=args.mode, progress=lambda m, d, t: print(f"  {m}", flush=True))
        print(json.dumps({k: v for k, v in receipt.items() if k != "collection"}, indent=1))
        return 0
    out = Path(args.out) if args.out else mode_paths(args.mode)[1]
    with _outer_image()(args.source) as archive:
        pins = record_pins(_read_entry(archive, OUTER), mode=args.mode)
    out.write_text(json.dumps(pins, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print("PINS_OK", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
