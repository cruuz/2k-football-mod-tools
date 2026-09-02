"""Throw distance and pass-arc tuning for the NFL 2K5 retail XBE.

What the game does (reverse-engineered 2026-09-02, witnessed in xemu with gdb):

* A human throw is targeted by ``FUN_002da8e0`` and launched by ``FUN_001cbdb0``
  as an exact ballistic solve from the target point and a flight time.  Nothing
  caps the ball's velocity.
* The target is clamped to a maximum distance that is a piecewise-linear
  function of the passer's *effective* arm strength (0..1).  Two curves exist:
  ``bullet`` (button held past half) and ``lob``.  Every throw past 20 yards is
  forced to a lob, and the accuracy pass (``FUN_002d9700``) then re-clamps the
  final target to ``max(bullet_curve, lob_curve / 2)``.  With retail tables that
  makes the **bullet** curve the real deep ceiling: 55 yards at arm 1.0.
* Flight time is distance divided by a speed that is itself a curve of distance
  (``lobspeed`` for lobs, blended toward ``bulletspeed`` by hold).  The lob speed
  is flat at 20 yd/s past 40 yards, so a longer throw is not a taller one.

All five curves are plain ``u32 count; (float x, float y) * count`` tables in
``.rdata`` (x and y in centimetres where they are distances; 1 yd = 91.44 cm)
read through one shared interpolator (``FUN_001b0ae0``: clamp at both ends,
linear between).  This module finds the tables by their exact retail bytes
cross-checked against the section table, rewrites point values on a COPY of the
XBE (or of a disc image, patching ``default.xbe`` in place inside the copy),
recomputes the touched section digest, and verifies by read-back and byte diff.
Tables never grow, move, or change their point count.

Two "sliders" sit on top of the raw curves:

* ``max_deep_yards`` (55 = retail .. 100): the deep-ball ceiling at arm 1.0.  The
  bullet curve is re-spaced as a scale (mid-league arms gain a few yards, only
  elite arms reach the ceiling) and the lob curve is kept at or above it so the
  bullet curve stays the one that decides.
* ``arc`` (0 = retail .. 1): lowers the lob speed at the ceiling distance so
  long balls hang longer and climb higher.  0 leaves the retail speed table
  untouched.

Patched output is xemu-only (the RSA signature stays stale), exactly like the
bump-strength route.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat
import struct
from typing import Callable, Iterable, Mapping, Sequence

from . import platform_compat
from .nfl2k5_bump_strength import (
    RETAIL_XBE_SHA256,
    _Section,
    _sections,
    _section_for_offset,
    section_digest,
)

READ_SCHEMA = "nfl2k5_throw_tuning_read/v1"
WRITE_SCHEMA = "nfl2k5_throw_tuning_write/v1"

YD_CM = 91.44
GRAVITY_YD_S2 = 980.664 / YD_CM  # the game's own constant (cm/s^2) in yards

RETAIL_MAX_DEEP_YARDS = 55.0
MIN_MAX_DEEP_YARDS = 55.0
MAX_MAX_DEEP_YARDS = 100.0
RETAIL_LOB_SPEED_YD_S = 20.0
MIN_ARC_LOB_SPEED_YD_S = 10.0

EXPECTED_XBE_SIZE = 11_948_032

ProgressSink = Callable[[str, int, int], None]


class ThrowTuningError(ValueError):
    """The requested throw-tuning operation is unsafe or impossible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ThrowTuningError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------
# Curve tables
@dataclass(frozen=True)
class Curve:
    name: str
    va: int                                     # VA of the count dword
    retail: tuple[tuple[float, float], ...]     # (x, y) in the units below
    x_unit: str                                  # "arm" (raw 0..1) or "yd"
    y_unit: str                                  # "yd" or "yd/s" (both cm-scaled)
    role: str

    @property
    def count(self) -> int:
        return len(self.retail)

    @property
    def size(self) -> int:
        return 4 + 8 * self.count

    @property
    def x_scale(self) -> float:
        return YD_CM if self.x_unit == "yd" else 1.0

    def encode(self, pairs: Sequence[tuple[float, float]]) -> bytes:
        _require(len(pairs) == self.count,
                 f"{self.name}: {len(pairs)} points given, table holds {self.count}")
        out = struct.pack("<I", self.count)
        for x, y in pairs:
            out += struct.pack("<ff", float(x) * self.x_scale, float(y) * YD_CM)
        return out

    def decode(self, blob: bytes) -> tuple[tuple[float, float], ...]:
        _require(len(blob) >= self.size, f"{self.name}: short table")
        count = struct.unpack_from("<I", blob, 0)[0]
        _require(count == self.count,
                 f"{self.name}: count word {count} != {self.count}")
        # float32 holds yards*91.44 to ~1e-4 yd; round to what the game can
        # distinguish so a decode(encode(x)) round trip is the identity.
        x_digits = 6 if self.x_unit == "arm" else 3
        return tuple(
            (
                round(struct.unpack_from("<f", blob, 4 + 8 * i)[0] / self.x_scale, x_digits),
                round(struct.unpack_from("<f", blob, 8 + 8 * i)[0] / YD_CM, 3),
            )
            for i in range(count)
        )

    @property
    def retail_bytes(self) -> bytes:
        return self.encode(self.retail)


CURVES: dict[str, Curve] = {
    "bullet": Curve(
        "bullet", 0x50BDC0,
        ((0.0, 25.0), (0.65, 35.0), (0.85, 45.0), (0.95, 50.0), (1.0, 55.0)),
        "arm", "yd", "max target distance, button held (and the deep re-clamp)",
    ),
    "lob": Curve(
        "lob", 0x50BD8C,
        ((0.0, 20.0), (0.5, 35.0), (0.65, 50.0), (0.85, 60.0), (0.95, 65.0), (1.0, 75.0)),
        "arm", "yd", "max target distance, lob",
    ),
    "anim": Curve(
        "anim", 0x50BD58,
        ((0.0, 20.0), (0.2, 30.0), (0.3, 50.0), (0.5, 60.0), (0.9, 70.0), (1.0, 80.0)),
        "arm", "yd", "throw-animation selector threshold (not edited)",
    ),
    "lobspeed": Curve(
        "lobspeed", 0x50BCB8,
        ((6.0, 6.0), (10.0, 12.0), (20.0, 16.0), (35.0, 18.0), (40.0, 20.0)),
        "yd", "yd/s", "horizontal ball speed by distance, lob",
    ),
    "bulletspeed": Curve(
        "bulletspeed", 0x50BC8C,
        ((4.0, 13.0), (10.0, 18.0), (15.0, 24.0), (25.0, 28.0), (35.0, 30.0)),
        "yd", "yd/s", "horizontal ball speed by distance, full hold (not edited)",
    ),
}
EDITABLE_CURVES = ("bullet", "lob", "lobspeed")


def interpolate(pairs: Sequence[tuple[float, float]], x: float) -> float:
    """The game's lookup: clamp at both ends, linear between points."""

    _require(len(pairs) >= 1, "empty curve")
    if x <= pairs[0][0]:
        return float(pairs[0][1])
    if x >= pairs[-1][0]:
        return float(pairs[-1][1])
    for (xa, ya), (xb, yb) in zip(pairs, pairs[1:]):
        if xa <= x <= xb:
            if xb == xa:
                return float(yb)
            return float(ya) + (float(yb) - float(ya)) * (x - xa) / (xb - xa)
    return float(pairs[-1][1])


def validate_pairs(curve: Curve, pairs: Sequence[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    _require(len(pairs) == curve.count,
             f"{curve.name}: table holds {curve.count} points, {len(pairs)} given; "
             "tables cannot grow or shrink in place")
    out: list[tuple[float, float]] = []
    for x, y in pairs:
        x = float(x)
        y = float(y)
        _require(x == x and y == y and abs(x) != float("inf") and abs(y) != float("inf"),
                 f"{curve.name}: non-finite point")
        if curve.x_unit == "arm":
            _require(0.0 <= x <= 1.0, f"{curve.name}: x {x} outside 0..1")
        else:
            _require(0.0 < x <= 150.0, f"{curve.name}: x {x} yd is not sane")
        _require(0.0 < y <= 150.0, f"{curve.name}: {y} {curve.y_unit} is not sane")
        out.append((x, y))
    for (xa, _ya), (xb, _yb) in zip(out, out[1:]):
        _require(xa < xb, f"{curve.name}: x must be strictly ascending")
    return tuple(out)


# --------------------------------------------------------------------------
# Slider model
@dataclass(frozen=True)
class TuningSettings:
    max_deep_yards: float = RETAIL_MAX_DEEP_YARDS
    arc: float = 0.0

    def validated(self) -> "TuningSettings":
        _require(MIN_MAX_DEEP_YARDS <= self.max_deep_yards <= MAX_MAX_DEEP_YARDS,
                 f"max deep distance {self.max_deep_yards} outside "
                 f"{MIN_MAX_DEEP_YARDS:g}..{MAX_MAX_DEEP_YARDS:g} yards")
        _require(0.0 <= self.arc <= 1.0, f"arc {self.arc} outside 0..1")
        return self


_BULLET_AT_80 = (25.0, 38.0, 52.0, 66.0, 80.0)
_LOB_AT_80 = (20.0, 35.0, 50.0, 60.0, 72.0, 80.0)


def curves_for(settings: TuningSettings) -> dict[str, tuple[tuple[float, float], ...]]:
    """Map the two sliders onto the three editable curves.

    The shape between retail (55) and the witnessed 80-yard scale is linear in
    the ceiling and extrapolates the same way to 100.  The lob curve is held at
    or above the bullet curve at every shared x so the bullet curve remains the
    deciding deep clamp (``FUN_002d9700`` takes ``max(bullet, lob/2)`` after
    ``FUN_002da8e0`` clamps to lob for forced-lob deep throws).
    """

    settings = settings.validated()
    t = (settings.max_deep_yards - RETAIL_MAX_DEEP_YARDS) / (80.0 - RETAIL_MAX_DEEP_YARDS)
    bullet_retail = CURVES["bullet"].retail
    bullet = tuple(
        (x, round(y + (y80 - y) * t, 3))
        for (x, y), y80 in zip(bullet_retail, _BULLET_AT_80)
    )
    lob_retail = CURVES["lob"].retail
    lob_scaled = [
        (x, round(y + (y80 - y) * t, 3))
        for (x, y), y80 in zip(lob_retail, _LOB_AT_80)
    ]
    lob: list[tuple[float, float]] = []
    for x, y in lob_scaled:
        # Retail already keeps lob >= bullet from arm 0.5 upward (the only
        # region a real passer occupies); hold that invariant there against the
        # interpolated bullet value, and leave the arm-0 point alone so retail
        # settings reproduce retail bytes.
        if x >= 0.5:
            y = max(y, math.ceil(interpolate(bullet, x) * 1000.0) / 1000.0)
        lob.append((x, round(y, 3)))
    # The very top of the lob curve must be the ceiling itself.
    lob[-1] = (lob[-1][0], max(lob[-1][1], settings.max_deep_yards))
    if settings.arc <= 0.0:
        lobspeed = CURVES["lobspeed"].retail
    else:
        knee = max(40.0, settings.max_deep_yards - 25.0)
        end_speed = RETAIL_LOB_SPEED_YD_S - (RETAIL_LOB_SPEED_YD_S - MIN_ARC_LOB_SPEED_YD_S) * settings.arc
        lobspeed = (
            (6.0, 6.0), (10.0, 12.0), (20.0, 16.0),
            (knee, RETAIL_LOB_SPEED_YD_S),
            (settings.max_deep_yards, round(end_speed, 3)),
        )
    result = {
        "bullet": validate_pairs(CURVES["bullet"], bullet),
        "lob": validate_pairs(CURVES["lob"], tuple(lob)),
        "lobspeed": validate_pairs(CURVES["lobspeed"], lobspeed),
    }
    for x_b, y_b in result["bullet"]:
        if x_b >= 0.5:
            _require(interpolate(result["lob"], x_b) >= y_b - 1e-6,
                     "internal: lob curve fell below the bullet curve")
    return result


@dataclass(frozen=True)
class PreviewRow:
    arm: float
    deep_cap_yards: float
    hang_seconds: float
    apex_yards: float


PREVIEW_ARMS = (0.70, 0.80, 0.85, 0.90, 0.95, 0.99, 1.00)


def preview(curves: Mapping[str, Sequence[tuple[float, float]]],
            arms: Iterable[float] = PREVIEW_ARMS) -> tuple[PreviewRow, ...]:
    """Deep-ball ceiling, hang time and apex height per effective arm.

    Deep throws are forced lobs, so the ceiling is ``max(bullet, lob/2)`` with
    ``lob >= bullet`` in every curve set this module writes; the flight time is
    ``distance / lobspeed(distance)`` and the launch is ballistic, so the apex
    is ``g * t^2 / 8``.
    """

    rows = []
    for arm in arms:
        cap = max(interpolate(curves["bullet"], arm), interpolate(curves["lob"], arm) / 2.0)
        cap = min(cap, interpolate(curves["lob"], arm))
        speed = interpolate(curves["lobspeed"], cap)
        hang = cap / speed if speed > 0 else 0.0
        apex = GRAVITY_YD_S2 * hang * hang / 8.0
        rows.append(PreviewRow(arm, round(cap, 2), round(hang, 2), round(apex, 1)))
    return tuple(rows)


# --------------------------------------------------------------------------
# Locating and reading
def _regular_non_link(path: Path) -> os.stat_result:
    info = path.lstat()
    _require(not stat.S_ISLNK(info.st_mode), f"refusing a symlink: {path}")
    _require(stat.S_ISREG(info.st_mode), f"not a regular file: {path}")
    return info


def _resolve_source(path: Path | str) -> Path:
    """Refuse symlinks on the path as given, then resolve it."""

    given = Path(path).expanduser()
    _require(given.exists(), f"source does not exist: {given}")
    _regular_non_link(given)
    return given.resolve(strict=True)


def locate_curve(payload: bytes, curve: Curve) -> int:
    """File offset of ``curve``: its exact retail bytes must sit where the section
    table says the VA lives; an already-edited table is accepted only at that
    same offset and only if the count word still matches."""

    sections = _sections(payload)
    expected: int | None = None
    for section in sections:
        if section.virtual_address <= curve.va < section.virtual_address + section.raw_size:
            expected = section.raw_offset + (curve.va - section.virtual_address)
            break
    _require(expected is not None, f"{curve.name}: VA 0x{curve.va:x} is in no section")
    _require(expected + curve.size <= len(payload), f"{curve.name}: table runs past the file")
    hits: list[int] = []
    start = payload.find(curve.retail_bytes)
    while start >= 0:
        hits.append(start)
        start = payload.find(curve.retail_bytes, start + 1)
    if hits:
        _require(hits == [expected],
                 f"{curve.name}: retail bytes found at {[hex(h) for h in hits]} but the "
                 f"section table places the table at 0x{expected:x}")
    else:
        count = struct.unpack_from("<I", payload, expected)[0]
        _require(count == curve.count,
                 f"{curve.name}: table at 0x{expected:x} is neither retail nor a "
                 "same-count edit; refusing to guess")
    return expected


def read_curves(payload: bytes) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for name, curve in CURVES.items():
        offset = locate_curve(payload, curve)
        blob = payload[offset: offset + curve.size]
        out[name] = {
            "va": f"0x{curve.va:x}",
            "file_offset": f"0x{offset:x}",
            "retail": blob == curve.retail_bytes,
            "points": curve.decode(blob),
            "x_unit": curve.x_unit,
            "y_unit": curve.y_unit,
            "role": curve.role,
            "editable": name in EDITABLE_CURVES,
        }
    return out


def infer_settings(curves: Mapping[str, Mapping[str, object]]) -> TuningSettings:
    """Best-effort slider positions for a set of read curves (for display)."""

    bullet = curves["bullet"]["points"]  # type: ignore[index]
    ceiling = float(bullet[-1][1])  # type: ignore[index]
    ceiling = min(max(ceiling, MIN_MAX_DEEP_YARDS), MAX_MAX_DEEP_YARDS)
    speed = curves["lobspeed"]["points"]  # type: ignore[index]
    end_speed = float(speed[-1][1])  # type: ignore[index]
    if end_speed >= RETAIL_LOB_SPEED_YD_S - 1e-6:
        arc = 0.0
    else:
        arc = (RETAIL_LOB_SPEED_YD_S - end_speed) / (RETAIL_LOB_SPEED_YD_S - MIN_ARC_LOB_SPEED_YD_S)
        arc = min(max(arc, 0.0), 1.0)
    return TuningSettings(round(ceiling, 2), round(arc, 3))


def read_xbe(xbe_path: Path | str) -> dict[str, object]:
    path = _resolve_source(xbe_path)
    payload = path.read_bytes()
    curves = read_curves(payload)
    return {
        "schema": READ_SCHEMA,
        "container": "xbe",
        "path": str(path),
        "xbe_sha256": _digest(payload),
        "matches_retail_sha256": _digest(payload) == RETAIL_XBE_SHA256,
        "curves": curves,
        "settings": infer_settings(curves),
    }


# --------------------------------------------------------------------------
# Disc images: find default.xbe inside an XDVDFS image
def _xdvdfs_module():
    """The proven XDVDFS reader lives in tools/; import it lazily so the core
    module has no import-time dependency on the tools directory layout."""

    try:
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc
    except ImportError:
        import sys
        tools = Path(__file__).resolve().parents[2] / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        import nfl_uniform_color_xiso_direct_patch as xc  # type: ignore
        return xc


def _open_binary(path: Path, flags: int) -> int:
    return os.open(
        path,
        flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )


def image_xbe_extent(descriptor: int, size: int) -> tuple[int, int]:
    """(byte offset, size) of default.xbe inside an XDVDFS image."""

    xc = _xdvdfs_module()
    entries, _directory = xc.parse_xdvdfs(descriptor, size)
    xbe = entries.get("default.xbe")
    _require(xbe is not None, "disc image has no default.xbe")
    _require(xbe.size == EXPECTED_XBE_SIZE,
             f"default.xbe inside the image is {xbe.size} bytes, not the retail "
             f"{EXPECTED_XBE_SIZE}")
    return int(xbe.byte_offset), int(xbe.size)


def read_image(image_path: Path | str) -> dict[str, object]:
    path = _resolve_source(image_path)
    descriptor = _open_binary(path, os.O_RDONLY)
    try:
        size = os.fstat(descriptor).st_size
        offset, length = image_xbe_extent(descriptor, size)
        payload = platform_compat.pread(descriptor, length, offset) if hasattr(platform_compat, "pread") else os.pread(descriptor, length, offset)
    finally:
        os.close(descriptor)
    _require(len(payload) == length, "short read of default.xbe from the image")
    curves = read_curves(payload)
    return {
        "schema": READ_SCHEMA,
        "container": "xiso",
        "path": str(path),
        "xbe_byte_offset": offset,
        "xbe_sha256": _digest(payload),
        "matches_retail_sha256": _digest(payload) == RETAIL_XBE_SHA256,
        "curves": curves,
        "settings": infer_settings(curves),
    }


def is_disc_image(path: Path | str) -> bool:
    """True when the file looks like an XDVDFS image rather than an XBE."""

    path = Path(path)
    try:
        with path.open("rb") as stream:
            head = stream.read(4)
            if head == b"XBEH":
                return False
            stream.seek(0x10000)
            return stream.read(20) == b"MICROSOFT*XBOX*MEDIA"
    except OSError:
        return False


def read_any(path: Path | str) -> dict[str, object]:
    return read_image(path) if is_disc_image(path) else read_xbe(path)


# --------------------------------------------------------------------------
# Patching
def plan_patch(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]]) -> tuple[bytes, dict[str, object]]:
    """Apply ``wanted`` curves to ``payload`` (an XBE) and return the patched
    bytes plus a receipt.  Curves already equal to the request are skipped; if
    nothing changes the request is refused."""

    _require(bool(wanted), "no curve changes were requested")
    for name in wanted:
        _require(name in EDITABLE_CURVES,
                 f"{name} is not an editable curve ({', '.join(EDITABLE_CURVES)})")
    buf = bytearray(payload)
    sections = _sections(payload)
    changes: list[dict[str, object]] = []
    touched: set[int] = set()
    expected_changed: set[int] = set()
    for name, pairs in wanted.items():
        curve = CURVES[name]
        pairs = validate_pairs(curve, pairs)
        offset = locate_curve(payload, curve)
        before = payload[offset: offset + curve.size]
        after = curve.encode(pairs)
        _require(before[:4] == after[:4], f"{name}: count word would change")
        if before == after:
            continue
        buf[offset: offset + curve.size] = after
        section = _section_for_offset(sections, offset)
        touched.add(section.index)
        expected_changed.update(offset + i for i, (a, b) in enumerate(zip(before, after)) if a != b)
        changes.append({
            "curve": name,
            "va": f"0x{curve.va:x}",
            "file_offset": f"0x{offset:x}",
            "before": curve.decode(before),
            "after": curve.decode(after),
            "before_hex": before.hex(),
            "after_hex": after.hex(),
        })
    _require(bool(changes), "the requested curves already match the file")
    digests: list[dict[str, object]] = []
    for section in sections:
        if section.index not in touched:
            continue
        digest_offset = section.header_offset + 36
        old = bytes(buf[digest_offset: digest_offset + 20])
        new = section_digest(bytes(buf), section)
        buf[digest_offset: digest_offset + 20] = new
        expected_changed.update(digest_offset + i for i, (a, b) in enumerate(zip(old, new)) if a != b)
        digests.append({
            "section_index": section.index,
            "digest_offset": f"0x{digest_offset:x}",
            "before": old.hex(),
            "after": new.hex(),
        })
    patched = bytes(buf)
    actual_changed = {i for i, (a, b) in enumerate(zip(payload, patched)) if a != b}
    _require(len(patched) == len(payload), "patched XBE changed size")
    _require(actual_changed == expected_changed,
             "patched XBE differs outside the requested tables and their section digests")
    receipt = {
        "changes": changes,
        "section_digests": digests,
        "changed_byte_count": len(actual_changed),
    }
    return patched, receipt


def _verify_written(payload: bytes, wanted: Mapping[str, Sequence[tuple[float, float]]]) -> dict[str, object]:
    curves = read_curves(payload)
    for name, pairs in wanted.items():
        got = CURVES[name].decode(CURVES[name].encode(validate_pairs(CURVES[name], pairs)))
        _require(curves[name]["points"] == got, f"post-write read-back disagrees for {name}")
    sections = _sections(payload)
    for section in sections:
        if section.raw_size and any(
            section.raw_offset <= locate_curve(payload, CURVES[n]) < section.raw_offset + section.raw_size
            for n in wanted
        ):
            _require(section_digest(payload, section) == section.stored_digest,
                     f"section {section.index} digest does not match after patching")
    return {name: curves[name]["points"] for name in CURVES}


def _resolve_wanted(settings: TuningSettings | None,
                    curves: Mapping[str, Sequence[tuple[float, float]]] | None) -> dict[str, tuple[tuple[float, float], ...]]:
    _require((settings is None) != (curves is None), "pass exactly one of settings or curves")
    if settings is not None:
        return curves_for(settings)
    assert curves is not None
    return {name: validate_pairs(CURVES[name], pairs) for name, pairs in curves.items()}


def _prepare_target(source: Path, target: Path, overwrite: bool) -> None:
    if target.exists():
        _require(overwrite, f"target already exists; pass overwrite=True to replace it: {target}")
        info = target.lstat()
        _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                 f"target is not a regular file: {target}")
        source_info = source.stat()
        _require((source_info.st_dev, source_info.st_ino) != (info.st_dev, info.st_ino),
                 "source and target are the same file; the target must be a copy")
        target.unlink()
    _require(str(source) != str(target.resolve()), "source and target are the same path")


def write_xbe_copy(
    source_xbe: Path | str,
    target_xbe: Path | str,
    *,
    settings: TuningSettings | None = None,
    curves: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    overwrite: bool = False,
) -> dict[str, object]:
    """Write a patched COPY of ``source_xbe`` to ``target_xbe``."""

    wanted = _resolve_wanted(settings, curves)
    source = _resolve_source(source_xbe)
    target = Path(target_xbe).expanduser()
    _prepare_target(source, target, overwrite)
    original = source.read_bytes()
    patched, receipt = plan_patch(original, wanted)
    descriptor = _open_binary(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        view = memoryview(patched)
        written = 0
        while written < len(patched):
            written += os.write(descriptor, view[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    result = target.read_bytes()
    _require(result == patched, "target read-back differs from the patched bytes")
    verified = _verify_written(result, wanted)
    return {
        "schema": WRITE_SCHEMA,
        "container": "xbe",
        "source": {"path": str(source), "sha256": _digest(original),
                   "matches_retail_sha256": _digest(original) == RETAIL_XBE_SHA256},
        "target": {"path": str(target), "sha256": _digest(result)},
        "settings": None if settings is None else {"max_deep_yards": settings.max_deep_yards, "arc": settings.arc},
        "curves_requested": {name: list(pairs) for name, pairs in wanted.items()},
        **receipt,
        "verified_curves": verified,
        "preview": [row.__dict__ for row in preview({n: verified[n] for n in EDITABLE_CURVES})],
        "signature_status": (
            "RSA signature left stale; patched XBE is xemu-only (xemu enforces no "
            "XBE integrity). Real hardware needs a resign this tool cannot produce."
        ),
    }


_COPY_CHUNK = 32 * 1024 * 1024


def write_image_copy(
    source_image: Path | str,
    target_image: Path | str,
    *,
    settings: TuningSettings | None = None,
    curves: Mapping[str, Sequence[tuple[float, float]]] | None = None,
    overwrite: bool = False,
    progress: ProgressSink | None = None,
) -> dict[str, object]:
    """Copy a disc image and patch ``default.xbe`` inside the COPY.

    The source is opened read-only and never written.  The copy is byte-exact
    except for the curve tables and the touched section digest of the embedded
    XBE; the receipt lists every changed range.
    """

    wanted = _resolve_wanted(settings, curves)
    source = _resolve_source(source_image)
    target = Path(target_image).expanduser()
    _prepare_target(source, target, overwrite)
    report: ProgressSink = progress or (lambda stage, done, total: None)

    src = _open_binary(source, os.O_RDONLY)
    try:
        size = os.fstat(src).st_size
        offset, length = image_xbe_extent(src, size)
        original = os.pread(src, length, offset)
        _require(len(original) == length, "short read of default.xbe from the source image")
        patched, receipt = plan_patch(original, wanted)
        dst = _open_binary(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            copied = 0
            while copied < size:
                chunk = os.pread(src, min(_COPY_CHUNK, size - copied), copied)
                _require(bool(chunk), "source image shrank during the copy")
                view = memoryview(chunk)
                done = 0
                while done < len(chunk):
                    done += os.write(dst, view[done:])
                copied += len(chunk)
                report("Copying disc image", copied, size)
            ranges: list[tuple[int, int]] = []
            i = 0
            while i < len(original):
                if original[i] != patched[i]:
                    j = i
                    while j < len(original) and original[j] != patched[j]:
                        j += 1
                    ranges.append((i, j))
                    i = j
                else:
                    i += 1
            for a, b in ranges:
                written = platform_compat.pwrite(dst, patched[a:b], offset + a)
                _require(written == b - a, "short write while patching the copy")
            os.fsync(dst)
        finally:
            os.close(dst)
    finally:
        os.close(src)
    report("Verifying the patched copy", 0, 0)
    check = _open_binary(target, os.O_RDONLY)
    try:
        _require(os.fstat(check).st_size == size, "copied image has the wrong size")
        after = os.pread(check, length, offset)
    finally:
        os.close(check)
    _require(after == patched, "patched default.xbe read-back differs inside the copy")
    verified = _verify_written(after, wanted)
    return {
        "schema": WRITE_SCHEMA,
        "container": "xiso",
        "source": {"path": str(source), "size": size, "xbe_sha256": _digest(original),
                   "xbe_matches_retail_sha256": _digest(original) == RETAIL_XBE_SHA256},
        "target": {"path": str(target), "size": size, "xbe_sha256": _digest(after)},
        "xbe_byte_offset": offset,
        "written_ranges": [{"xbe_offset": f"0x{a:x}", "image_offset": f"0x{offset + a:x}", "length": b - a}
                           for a, b in ranges],
        "settings": None if settings is None else {"max_deep_yards": settings.max_deep_yards, "arc": settings.arc},
        "curves_requested": {name: list(pairs) for name, pairs in wanted.items()},
        **receipt,
        "verified_curves": verified,
        "preview": [row.__dict__ for row in preview({n: verified[n] for n in EDITABLE_CURVES})],
        "signature_status": (
            "RSA signature left stale; the patched image is xemu-only (xemu enforces "
            "no XBE integrity). Real hardware needs a resign this tool cannot produce."
        ),
    }


def write_copy(source: Path | str, target: Path | str, **kwargs) -> dict[str, object]:
    """Dispatch on the source container (XBE or disc image)."""

    if is_disc_image(source):
        return write_image_copy(source, target, **kwargs)
    kwargs.pop("progress", None)
    return write_xbe_copy(source, target, **kwargs)


__all__ = [
    "CURVES",
    "Curve",
    "EDITABLE_CURVES",
    "EXPECTED_XBE_SIZE",
    "GRAVITY_YD_S2",
    "MAX_MAX_DEEP_YARDS",
    "MIN_MAX_DEEP_YARDS",
    "PREVIEW_ARMS",
    "PreviewRow",
    "READ_SCHEMA",
    "RETAIL_MAX_DEEP_YARDS",
    "RETAIL_XBE_SHA256",
    "ThrowTuningError",
    "TuningSettings",
    "WRITE_SCHEMA",
    "YD_CM",
    "curves_for",
    "infer_settings",
    "interpolate",
    "is_disc_image",
    "locate_curve",
    "plan_patch",
    "preview",
    "read_any",
    "read_curves",
    "read_image",
    "read_xbe",
    "validate_pairs",
    "write_copy",
    "write_image_copy",
    "write_xbe_copy",
]
