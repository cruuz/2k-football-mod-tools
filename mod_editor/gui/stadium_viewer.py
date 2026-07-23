"""Dependency-free glTF stadium viewport for the Linux desktop product.

Qt WebEngine/OpenGL are optional packages on many Linux Mint installs.  This
viewer therefore renders a bounded, interactive triangle projection with
QPainter: drag to orbit, Shift-drag to pan, wheel to zoom, and click a surface
to report its mesh/primitive ownership.  It consumes only glTF files derived
privately from the user's game.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterable

from PyQt5.QtCore import QPointF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)
from PyQt5.QtWidgets import QWidget

from mod_editor.core.errors import ValidationError


MAX_VIEW_TRIANGLES = 12_000
DEFAULT_STADIUM_YAW = -0.55
DEFAULT_STADIUM_PITCH = 0.48
STADIUM_FIT_SCALE = 1.25


@dataclass(frozen=True, slots=True)
class WireTriangle:
    a: tuple[float, float, float]
    b: tuple[float, float, float]
    c: tuple[float, float, float]
    mesh_index: int
    primitive_index: int


@dataclass(frozen=True, slots=True)
class SurfaceIdentity:
    """Stable glTF/source identity retained for one clickable surface."""

    mesh_index: int
    primitive_index: int
    mesh_name: str
    gltf_node_indices: tuple[int, ...]
    node_names: tuple[str, ...]
    apf_scene_node_indices: tuple[int, ...]
    apf_source_mesh_index: int | None
    material_index: int | None


@dataclass(frozen=True)
class GltfWireframeModel:
    triangles: tuple[WireTriangle, ...]
    center: tuple[float, float, float]
    radius: float
    source_triangle_count: int
    mesh_count: int
    surfaces: tuple[SurfaceIdentity, ...]

    def surface_identity(
        self, mesh_index: int, primitive_index: int
    ) -> SurfaceIdentity | None:
        return next(
            (
                item
                for item in self.surfaces
                if item.mesh_index == mesh_index
                and item.primitive_index == primitive_index
            ),
            None,
        )

    @classmethod
    def load(
        cls,
        gltf_path: Path,
        bin_path: Path,
        *,
        maximum_triangles: int = MAX_VIEW_TRIANGLES,
    ) -> "GltfWireframeModel":
        if not 100 <= maximum_triangles <= 100_000:
            raise ValidationError("Stadium preview triangle limit is unsupported.")
        try:
            document = json.loads(gltf_path.read_text(encoding="utf-8"))
            binary = bin_path.read_bytes()
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not open the stadium glTF: {exc}") from exc
        if not isinstance(document, dict):
            raise ValidationError("Stadium glTF root is not an object.")
        buffers = document.get("buffers")
        meshes = document.get("meshes")
        nodes = document.get("nodes")
        accessors = document.get("accessors")
        views = document.get("bufferViews")
        if not all(isinstance(value, list) for value in (
            buffers, meshes, nodes, accessors, views,
        )) or len(buffers) != 1:
            raise ValidationError("Stadium glTF uses an unsupported layout.")
        buffer = buffers[0]
        if not isinstance(buffer, dict) or buffer.get("uri") != bin_path.name \
                or buffer.get("byteLength") != len(binary):
            raise ValidationError("Stadium glTF binary identity does not match.")

        world_matrices = _world_matrices(nodes)
        mesh_nodes: dict[
            int, list[tuple[tuple[float, ...], int, str, dict[str, Any]]]
        ] = {}
        for node_index, node in enumerate(nodes):
            if not isinstance(node, dict) or "mesh" not in node:
                continue
            mesh_index = node.get("mesh")
            if isinstance(mesh_index, bool) or not isinstance(mesh_index, int) \
                    or not 0 <= mesh_index < len(meshes):
                raise ValidationError("Stadium glTF node has an invalid mesh index.")
            node_name = node.get("name")
            node_extras = node.get("extras")
            mesh_nodes.setdefault(mesh_index, []).append(
                (
                    world_matrices[node_index],
                    node_index,
                    node_name if isinstance(node_name, str) else f"Node {node_index}",
                    node_extras if isinstance(node_extras, dict) else {},
                )
            )

        primitive_specs: list[tuple[int, int, dict[str, Any], tuple[float, ...]]] = []
        surface_identities: list[SurfaceIdentity] = []
        source_triangle_count = 0
        for mesh_index, mesh in enumerate(meshes):
            if not isinstance(mesh, dict) or not isinstance(mesh.get("primitives"), list):
                raise ValidationError("Stadium glTF mesh is malformed.")
            node_rows = mesh_nodes.get(
                mesh_index,
                [(_identity_matrix(), -1, "Unattached mesh", {})],
            )
            transforms = [row[0] for row in node_rows]
            mesh_name = mesh.get("name")
            mesh_extras = mesh.get("extras")
            extras = mesh_extras if isinstance(mesh_extras, dict) else {}
            apf_nodes = {
                value
                for value in (
                    extras.get("apf_scene_node_index"),
                    *(row[3].get("apf_scene_node_index") for row in node_rows),
                )
                if isinstance(value, int) and not isinstance(value, bool)
            }
            source_mesh = extras.get("apf_source_mesh_index")
            if isinstance(source_mesh, bool) or not isinstance(source_mesh, int):
                source_mesh = None
            for primitive_index, primitive in enumerate(mesh["primitives"]):
                if not isinstance(primitive, dict):
                    raise ValidationError("Stadium glTF primitive is malformed.")
                mode = primitive.get("mode", 4)
                if mode not in {4, 5}:
                    continue
                material = primitive.get("material")
                if isinstance(material, bool) or not isinstance(material, int):
                    material = None
                surface_identities.append(
                    SurfaceIdentity(
                        mesh_index=mesh_index,
                        primitive_index=primitive_index,
                        mesh_name=(
                            mesh_name
                            if isinstance(mesh_name, str) and mesh_name
                            else f"Mesh {mesh_index}"
                        ),
                        gltf_node_indices=tuple(
                            row[1] for row in node_rows if row[1] >= 0
                        ),
                        node_names=tuple(row[2] for row in node_rows),
                        apf_scene_node_indices=tuple(sorted(apf_nodes)),
                        apf_source_mesh_index=source_mesh,
                        material_index=material,
                    )
                )
                count = _primitive_index_count(primitive, accessors)
                triangle_count = count // 3 if mode == 4 else max(0, count - 2)
                source_triangle_count += triangle_count * len(transforms)
                for transform in transforms:
                    primitive_specs.append(
                        (mesh_index, primitive_index, primitive, transform)
                    )
        if source_triangle_count <= 0:
            raise ValidationError("Stadium glTF has no supported triangles.")
        sample_step = max(1, math.ceil(source_triangle_count / maximum_triangles))

        triangles: list[WireTriangle] = []
        represented_surfaces: set[tuple[int, int]] = set()
        bounds: list[tuple[float, float, float]] = []
        source_cursor = 0
        position_cache: dict[tuple[int, tuple[float, ...]], tuple[tuple[float, float, float], ...]] = {}
        index_cache: dict[int, tuple[int, ...]] = {}
        for mesh_index, primitive_index, primitive, transform in primitive_specs:
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or not isinstance(attributes.get("POSITION"), int):
                raise ValidationError("Stadium primitive has no POSITION accessor.")
            position_accessor = attributes["POSITION"]
            cache_key = (position_accessor, transform)
            positions = position_cache.get(cache_key)
            if positions is None:
                local = _read_positions(
                    position_accessor, accessors, views, binary
                )
                positions = tuple(_transform_point(transform, value) for value in local)
                position_cache[cache_key] = positions
                bounds.extend(positions)
            raw_index = primitive.get("indices")
            if raw_index is None:
                indices = tuple(range(len(positions)))
            elif isinstance(raw_index, int) and not isinstance(raw_index, bool):
                indices = index_cache.get(raw_index)
                if indices is None:
                    indices = _read_indices(raw_index, accessors, views, binary)
                    index_cache[raw_index] = indices
            else:
                raise ValidationError("Stadium primitive has an invalid index accessor.")
            mode = int(primitive.get("mode", 4))
            for ia, ib, ic in _triangles(indices, mode):
                surface = (mesh_index, primitive_index)
                include = (
                    surface not in represented_surfaces
                    or source_cursor % sample_step == 0
                )
                source_cursor += 1
                if ia == ib or ib == ic or ia == ic:
                    continue
                if max(ia, ib, ic) >= len(positions):
                    raise ValidationError("Stadium primitive index exceeds POSITION data.")
                if include and len(triangles) < maximum_triangles:
                    triangles.append(WireTriangle(
                        positions[ia], positions[ib], positions[ic],
                        mesh_index, primitive_index,
                    ))
                    represented_surfaces.add(surface)
        if not triangles or not bounds:
            raise ValidationError("Stadium preview could not retain any triangles.")
        minimum = tuple(min(point[axis] for point in bounds) for axis in range(3))
        maximum = tuple(max(point[axis] for point in bounds) for axis in range(3))
        center = tuple((minimum[axis] + maximum[axis]) / 2 for axis in range(3))
        radius = max(maximum[axis] - minimum[axis] for axis in range(3)) / 2
        if not math.isfinite(radius) or radius <= 0:
            raise ValidationError("Stadium preview bounds are degenerate.")
        return cls(
            tuple(triangles),
            (float(center[0]), float(center[1]), float(center[2])),
            float(radius),
            source_triangle_count,
            len(meshes),
            tuple(surface_identities),
        )


def _accessor(
    index: int, accessors: list[Any], views: list[Any], binary: bytes,
    *, expected_type: str,
) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    if not 0 <= index < len(accessors) or not isinstance(accessors[index], dict):
        raise ValidationError("Stadium glTF accessor index is invalid.")
    accessor = accessors[index]
    view_index = accessor.get("bufferView")
    if isinstance(view_index, bool) or not isinstance(view_index, int) \
            or not 0 <= view_index < len(views) or not isinstance(views[view_index], dict):
        raise ValidationError("Stadium glTF accessor has an invalid buffer view.")
    view = views[view_index]
    if accessor.get("type") != expected_type:
        raise ValidationError("Stadium glTF accessor has an unsupported shape.")
    count = accessor.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValidationError("Stadium glTF accessor has an invalid count.")
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    if offset < 0 or offset > len(binary):
        raise ValidationError("Stadium glTF accessor offset is outside its binary.")
    return accessor, view, count, offset


def _read_positions(
    index: int, accessors: list[Any], views: list[Any], binary: bytes,
) -> tuple[tuple[float, float, float], ...]:
    accessor, view, count, offset = _accessor(
        index, accessors, views, binary, expected_type="VEC3"
    )
    if accessor.get("componentType") != 5126:
        raise ValidationError("Stadium POSITION accessor is not FLOAT3.")
    stride = int(view.get("byteStride", 12))
    if stride < 12 or offset + max(0, count - 1) * stride + 12 > len(binary):
        raise ValidationError("Stadium POSITION accessor exceeds its binary.")
    result = tuple(
        tuple(float(value) for value in struct.unpack_from("<3f", binary, offset + i * stride))
        for i in range(count)
    )
    if any(not all(math.isfinite(value) for value in point) for point in result):
        raise ValidationError("Stadium POSITION accessor contains non-finite coordinates.")
    return result


def _read_indices(
    index: int, accessors: list[Any], views: list[Any], binary: bytes,
) -> tuple[int, ...]:
    accessor, view, count, offset = _accessor(
        index, accessors, views, binary, expected_type="SCALAR"
    )
    profile = {5121: (1, "<B"), 5123: (2, "<H"), 5125: (4, "<I")}.get(
        accessor.get("componentType")
    )
    if profile is None:
        raise ValidationError("Stadium index accessor has an unsupported component type.")
    size, fmt = profile
    stride = int(view.get("byteStride", size))
    if stride < size or offset + max(0, count - 1) * stride + size > len(binary):
        raise ValidationError("Stadium index accessor exceeds its binary.")
    return tuple(
        int(struct.unpack_from(fmt, binary, offset + i * stride)[0])
        for i in range(count)
    )


def _primitive_index_count(primitive: dict[str, Any], accessors: list[Any]) -> int:
    index = primitive.get("indices")
    if isinstance(index, int) and not isinstance(index, bool) \
            and 0 <= index < len(accessors) and isinstance(accessors[index], dict):
        count = accessors[index].get("count")
    else:
        attributes = primitive.get("attributes", {})
        position = attributes.get("POSITION") if isinstance(attributes, dict) else None
        count = (
            accessors[position].get("count")
            if isinstance(position, int) and 0 <= position < len(accessors)
            and isinstance(accessors[position], dict) else None
        )
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValidationError("Stadium primitive has an invalid element count.")
    return count


def _triangles(indices: tuple[int, ...], mode: int) -> Iterable[tuple[int, int, int]]:
    if mode == 4:
        for index in range(0, len(indices) - 2, 3):
            yield indices[index], indices[index + 1], indices[index + 2]
    elif mode == 5:
        for index in range(len(indices) - 2):
            if index & 1:
                yield indices[index + 1], indices[index], indices[index + 2]
            else:
                yield indices[index], indices[index + 1], indices[index + 2]


def _identity_matrix() -> tuple[float, ...]:
    return (
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
    )


def _matrix_multiply(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(
        sum(a[row + k * 4] * b[k + column * 4] for k in range(4))
        for column in range(4) for row in range(4)
    )


def _local_matrix(node: dict[str, Any]) -> tuple[float, ...]:
    raw = node.get("matrix")
    if isinstance(raw, list) and len(raw) == 16 \
            and all(isinstance(value, (int, float)) for value in raw):
        return tuple(float(value) for value in raw)
    translation = node.get("translation", [0, 0, 0])
    rotation = node.get("rotation", [0, 0, 0, 1])
    scale = node.get("scale", [1, 1, 1])
    if not (
        isinstance(translation, list) and len(translation) == 3
        and isinstance(rotation, list) and len(rotation) == 4
        and isinstance(scale, list) and len(scale) == 3
        and all(isinstance(value, (int, float)) for value in (*translation, *rotation, *scale))
    ):
        raise ValidationError("Stadium glTF node transform is malformed.")
    x, y, z, w = (float(value) for value in rotation)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 0:
        raise ValidationError("Stadium glTF node quaternion is degenerate.")
    x, y, z, w = x / length, y / length, z / length, w / length
    sx, sy, sz = (float(value) for value in scale)
    tx, ty, tz = (float(value) for value in translation)
    return (
        (1 - 2 * (y * y + z * z)) * sx,
        (2 * (x * y + z * w)) * sx,
        (2 * (x * z - y * w)) * sx,
        0,
        (2 * (x * y - z * w)) * sy,
        (1 - 2 * (x * x + z * z)) * sy,
        (2 * (y * z + x * w)) * sy,
        0,
        (2 * (x * z + y * w)) * sz,
        (2 * (y * z - x * w)) * sz,
        (1 - 2 * (x * x + y * y)) * sz,
        0,
        tx, ty, tz, 1,
    )


def _world_matrices(nodes: list[Any]) -> tuple[tuple[float, ...], ...]:
    parents: dict[int, int] = {}
    for parent, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            raise ValidationError("Stadium glTF node is malformed.")
        children = raw.get("children", [])
        if not isinstance(children, list):
            raise ValidationError("Stadium glTF node children are malformed.")
        for child in children:
            if isinstance(child, bool) or not isinstance(child, int) \
                    or not 0 <= child < len(nodes) or child in parents:
                raise ValidationError("Stadium glTF node hierarchy is invalid.")
            parents[child] = parent
    cache: dict[int, tuple[float, ...]] = {}
    visiting: set[int] = set()

    def world(index: int) -> tuple[float, ...]:
        if index in cache:
            return cache[index]
        if index in visiting:
            raise ValidationError("Stadium glTF node hierarchy contains a cycle.")
        visiting.add(index)
        local = _local_matrix(nodes[index])
        result = (
            _matrix_multiply(world(parents[index]), local)
            if index in parents else local
        )
        visiting.remove(index)
        cache[index] = result
        return result

    return tuple(world(index) for index in range(len(nodes)))


def _transform_point(
    matrix: tuple[float, ...], point: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def _view_coordinates(
    point: tuple[float, float, float],
    center: tuple[float, float, float],
    radius: float,
    yaw: float,
    pitch: float,
) -> tuple[float, float, float]:
    """Normalize a y-up stadium point into camera-space coordinates.

    NFL 2K5 stadium exports use X/Z for the field plane and Y for height.  The
    first viewport implementation accidentally yawed around Z, mixing stadium
    height into the horizontal axis.  Keeping this transform pure makes that
    axis contract independently testable and gives the software viewport the
    same familiar orbit convention as a normal 3D editor.
    """

    x = (point[0] - center[0]) / radius
    y = (point[1] - center[1]) / radius
    z = (point[2] - center[2]) / radius
    cosine_yaw, sine_yaw = math.cos(yaw), math.sin(yaw)
    rotated_x = cosine_yaw * x - sine_yaw * z
    rotated_z = sine_yaw * x + cosine_yaw * z
    cosine_pitch, sine_pitch = math.cos(pitch), math.sin(pitch)
    projected_y = cosine_pitch * y - sine_pitch * rotated_z
    depth = sine_pitch * y + cosine_pitch * rotated_z
    return rotated_x, projected_y, depth


class StadiumViewport(QWidget):
    """Interactive software stadium viewport with surface picking."""

    surfaceSelected = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.model: GltfWireframeModel | None = None
        self.yaw = DEFAULT_STADIUM_YAW
        self.pitch = DEFAULT_STADIUM_PITCH
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.selected_surface: tuple[int, int] | None = None
        self._last_mouse: QPointF | None = None
        self._dragged = False
        self._projected: list[tuple[float, QPolygonF, WireTriangle]] = []
        self.setToolTip(
            "Drag to orbit • Shift-drag or middle-drag to pan • wheel to zoom • click a surface"
        )

    def set_model(self, model: GltfWireframeModel | None) -> None:
        self.model = model
        self.reset_view()

    def reset_view(self) -> None:
        self.yaw = DEFAULT_STADIUM_YAW
        self.pitch = DEFAULT_STADIUM_PITCH
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.selected_surface = None
        self.update()

    def set_selected_surface(self, mesh_index: int, primitive_index: int) -> None:
        self.selected_surface = (mesh_index, primitive_index)
        self.update()

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#07101e"))
        gradient.setColorAt(1, QColor("#101d2b"))
        painter.fillRect(self.rect(), gradient)
        model = self.model
        if model is None:
            painter.setPen(QColor("#8292aa"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Choose a stadium scene to open its 3D preview")
            painter.end()
            return
        projected: list[tuple[float, QPolygonF, WireTriangle]] = []
        for triangle in model.triangles:
            points = [self._project(value) for value in (triangle.a, triangle.b, triangle.c)]
            polygon = QPolygonF([QPointF(x, y) for x, y, _z in points])
            depth = sum(value[2] for value in points) / 3
            projected.append((depth, polygon, triangle))
        projected.sort(key=lambda item: item[0])
        self._projected = projected
        for _depth, polygon, triangle in projected:
            selected = self.selected_surface == (
                triangle.mesh_index, triangle.primitive_index
            )
            seed = (triangle.mesh_index * 37 + triangle.primitive_index * 17) % 80
            fill = QColor.fromHsv(186 + seed, 125, 175, 45 if not selected else 155)
            line = QColor("#50f1de") if selected else QColor(88, 125, 157, 72)
            painter.setBrush(fill)
            painter.setPen(QPen(line, 1.7 if selected else 0.55))
            painter.drawPolygon(polygon)
        painter.setPen(QColor("#8ea1b8"))
        painter.drawText(
            14,
            self.height() - 14,
            f"{len(model.triangles):,} preview triangles / "
            f"{model.source_triangle_count:,} source • drag orbit • wheel zoom • click surface",
        )
        painter.end()

    def _project(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        assert self.model is not None
        rx, py, pz = _view_coordinates(
            point,
            self.model.center,
            self.model.radius,
            self.yaw,
            self.pitch,
        )
        perspective = max(0.65, 3.2 - pz)
        scale = (
            min(self.width(), self.height())
            * STADIUM_FIT_SCALE
            * self.zoom
            / perspective
        )
        return (
            self.width() / 2 + self.pan_x + rx * scale,
            self.height() / 2 + self.pan_y - py * scale,
            pz,
        )

    def mousePressEvent(self, event: object) -> None:  # type: ignore[override]
        self._last_mouse = QPointF(event.pos())  # type: ignore[attr-defined]
        self._dragged = False

    def mouseMoveEvent(self, event: object) -> None:  # type: ignore[override]
        if self._last_mouse is None or not event.buttons():  # type: ignore[attr-defined]
            return
        current = QPointF(event.pos())  # type: ignore[attr-defined]
        delta = current - self._last_mouse
        if abs(delta.x()) + abs(delta.y()) > 1:
            self._dragged = True
        pan = bool(event.modifiers() & Qt.ShiftModifier) \
            or bool(event.buttons() & Qt.MiddleButton)  # type: ignore[attr-defined]
        if pan:
            self.pan_x += delta.x()
            self.pan_y += delta.y()
        else:
            self.yaw += delta.x() * 0.008
            self.pitch = max(-1.45, min(1.45, self.pitch + delta.y() * 0.008))
        self._last_mouse = current
        self.update()

    def mouseReleaseEvent(self, event: object) -> None:  # type: ignore[override]
        if not self._dragged and event.button() == Qt.LeftButton:  # type: ignore[attr-defined]
            point = QPointF(event.pos())  # type: ignore[attr-defined]
            for _depth, polygon, triangle in reversed(self._projected):
                if polygon.containsPoint(point, Qt.OddEvenFill):
                    self.selected_surface = (
                        triangle.mesh_index, triangle.primitive_index
                    )
                    self.surfaceSelected.emit(*self.selected_surface)
                    self.update()
                    break
        self._last_mouse = None

    def wheelEvent(self, event: object) -> None:  # type: ignore[override]
        steps = event.angleDelta().y() / 120  # type: ignore[attr-defined]
        self.zoom = max(0.35, min(6.0, self.zoom * (1.12 ** steps)))
        self.update()


__all__ = [
    "GltfWireframeModel",
    "MAX_VIEW_TRIANGLES",
    "StadiumViewport",
    "SurfaceIdentity",
    "WireTriangle",
]
