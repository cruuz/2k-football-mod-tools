"""EXPERIMENTAL / UNWITNESSED flatter deep-flight option, fixed speed table.

The first four lob-speed knots stay retail (all throws <=35 yd). The 40-yard
knot rises from 20 to 25 yd/s; the native lookup clamps beyond it. At 80 yd,
the equal-height ballistic preview is 3.2 s / 13.7 yd apex, versus retail
speed's 4 s / 21.4 yd. Arm-to-distance, accuracy and bullet-speed math remain
owned by nfl2k5_throw_tuning. No extra cave or hook is needed.
"""
from __future__ import annotations

from pathlib import Path
import os
import tempfile

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_throw_tuning as tt
from . import platform_compat as io

OWNER = "nfl2k5_throw_arc"
FLAT_LOBSPEED = ((6.0, 6.0), (10.0, 12.0), (20.0, 16.0), (35.0, 18.0), (40.0, 25.0))
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Flatter deep flight speeds up lobs beyond 35 yards. "
    "At an 80-yard reach, the preview falls from 4.00 seconds and a 21.4-yard apex "
    "to 3.20 seconds and 13.7 yards. Throws through 35 yards keep their original "
    "speeds. Distance and accuracy settings remain separate. Preview assumes equal release and landing height."
)
# Literal pins also allow the protected dispatcher to import this module before
# it finishes defining its own Curve class. No access to tt during module load.
SITES = (("flatter_lob_speed", 0x50BCB8,
          bytes.fromhex("05000000f6280944f62809449a996444f62889449a99e44448e1b6446606484571bdcd449a9964459a99e444"),
          bytes.fromhex("05000000f6280944f62809449a996444f62889449a99e44448e1b6446606484571bdcd449a99644500e00e45")),)
READER_PINS = ((0x2D898B, bytes.fromhex("8b15b8bc5000")),
               (0x2D8992, bytes.fromhex("b9bcbc5000")))


def status(payload: bytes) -> str:
    try:
        for va, pin in READER_PINS:
            off = rdata.offset_of(payload, va)
            if payload[off:off + len(pin)] != pin:
                return "foreign"  # relocated speed table would make this edit a no-op
        return rdata.status(payload, SITES)
    except (ValueError, TypeError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Change flight only, keeping the source's chosen arm-to-distance curves."""
    if status(payload) == "foreign":
        raise tt.ThrowTuningError("foreign/mixed flight table or relocated reader; rebuild from the original source")
    result, receipt = rdata.apply(payload, SITES, "Flatter deep flight")
    return result, {**receipt, "owner": OWNER, "experimental": True, "runtime_witnessed": False,
                    "flight_arc": "flatter", "distance_curves_changed": False,
                    "speed_points_yards_per_second": FLAT_LOBSPEED,
                    "site_bytes": [{"va": hex(va), "file_offset": hex(rdata.offset_of(payload, va)),
                                    "before": before.hex(), "after": after.hex()}
                                   for _, va, before, after in SITES]}


def curves_for(settings: tt.TuningSettings) -> dict:
    if settings.arc_by_distance or settings.realistic_flight or settings.arc != 0:
        raise tt.ThrowTuningError("Flatter flight must be selected on its own; choose one flight option")
    return {**tt.curves_for(settings), "lobspeed": FLAT_LOBSPEED}


def flight_points(distance: float, speed: float, samples: int = 41) -> tuple:
    """Equal-height ballistic guide in yards, not an animation/gameplay witness."""
    if not 0 < distance <= 100 or not 0 < speed <= 150 or type(samples) is not int or not 2 <= samples <= 501:
        raise ValueError("bounded positive flight dimensions and 2..501 samples required")
    duration = distance / speed
    return tuple((distance * i / (samples - 1),
                  tt.GRAVITY_YD_S2 * duration ** 2 * (i / (samples - 1)) * (1 - i / (samples - 1)) / 2)
                 for i in range(samples))


def _payload(source) -> bytes:
    """Read only default.xbe, including when the source is a multi-GB image."""
    path = Path(source)
    with path.open("rb") as stream:
        if tt.is_disc_image(path):
            stream.seek(0, 2)
            offset, length = tt.image_xbe_extent(stream.fileno(), stream.tell())
        else:
            stream.seek(0, 2)
            offset, length = 0, stream.tell()
        if not 0 < length <= 32 * 1024 * 1024:
            raise tt.ThrowTuningError("default.xbe exceeds the bounded reader limit")
        result = io.pread(stream.fileno(), length, offset)
    if len(result) != length:
        raise tt.ThrowTuningError("short read of default.xbe")
    return result


def read_any(source) -> dict:
    report = tt.read_any(source)
    report["flight_arc"] = status(_payload(source))
    if report["flight_arc"] == "applied":
        report["settings"] = tt.TuningSettings(report["settings"].max_deep_yards)
    return report


def write_copy(source, target, *, settings=None, **kwargs) -> dict:
    """Use the existing transactional, streaming writer with explicit curves.

    Selecting this option defaults to the shipped 80-yard distance scale.
    The protected dispatcher can instead call apply after its distance pass.
    """
    wanted = curves_for(settings or tt.TuningSettings(80))
    source = tt._resolve_source(source)
    target = Path(target).expanduser().absolute()
    if target.is_symlink() or target.resolve() == source or (target.exists() and os.path.samefile(source, target)):
        raise tt.ThrowTuningError("source and target must be different regular files")
    if target.exists() and (not kwargs.get("overwrite", False) or not target.is_file()):
        raise tt.ThrowTuningError("target exists; choose a new copy or enable overwrite")
    original = _payload(source)
    if status(original) == "foreign":
        raise tt.ThrowTuningError("Flatter flight needs original or already-flatter speed bytes; rebuild from the original source")
    # Preflight every writer input before its existing copy transaction begins.
    change_curves = tt._curves_differ(original, wanted)
    if change_curves:
        tt.plan_patch(original, wanted)
    flight_receipt = apply(original)[1]
    with tempfile.TemporaryDirectory(prefix=".flat-flight-", dir=target.parent) as folder:
        stage = Path(folder).resolve() / target.name
        curve_options = {"curves": wanted} if change_curves else {}
        report = tt.write_copy(source, stage, **curve_options, **{**kwargs, "overwrite": False})
        after = _payload(stage)
        if status(after) != "applied":
            raise tt.ThrowTuningError("flatter speed table did not read back")
        report.update({"flight_arc": "flatter", "experimental": True, "runtime_witnessed": False,
                       "preview": [row.__dict__ for row in tt.preview(wanted)],
                       "flatter_flight_patch": flight_receipt})
        os.replace(stage, target)
        report["target"]["path"] = str(target)
    return report
