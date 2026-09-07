"""Read-only deep-zone tier evidence audit, EXPERIMENTAL / UNWITNESSED.

The September 5 CB memo certifies the shipped initial-drop cap. Its sustained
facing policy and bail donor remain hypotheses, pending callback/target and
played traces. This module verifies the known instruction dependencies and
reports that boundary. It is not a patch owner and exposes no apply/REQUESTS.
No import of a disassembler, instruction emulator, GUI or private data is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from . import nfl2k5_catch_slider as catch
from . import nfl2k5_coverage_slider as coverage
from . import nfl2k5_qb_spy_runtime as spy
from . import nfl2k5_xbe_space as space
from . import nfl2k5_zone_drop as drop
from .nfl2k5_cave_oracle import XbeImage

SCHEMA = "nfl2k5_deep_zone_evidence/v1"
# Full reached routines, plus their immutable geometry inputs. Coverage pins
# the reaction routine, both context curves and ReadFactor. Spy pins both
# callbacks and the fast-movement helper, accepting only its exact detours.
GUARDS = (
    (0x217AB0, 44, "4d3c3bdcb144bf55dc294d97a10c45d4c9cadbbc31d014cac5e1ee104bf339d5"),
    (0x217AE0, 24, "d27adf50607c6c2430191a95caf26879b44e238e499907c559db076cf77451a9"),
    (0x3CA1E0, 142, "082823e17edd283a9b7e5e8de394ef095643489f498205e5c14686b510f9c2da"),
    (0x3CA150, 140, "76343d475ba9c89963bf42f9a1951e8b20183759dd8e05e72ab4b288ec06f945"),
    (0x210B0, 215, "992f601ec2f53fa33bbb4b5f0bad2c0e16b1efd5be83a5693710bdbf17990734"),
    (0x48B50, 105, "27476b10d12effcb7ebcdc155d01e15fdaf28b0d4a566b6e1c5bf1ac3f64959a"),
    (0x50F530, 12, "caccb9a8fbd2401135207066c4b53d6e88467839318ea2f1e8bfadf8fef6844e"),
    (0x4E5C4C, 24, "42926ab80cd65ed293839faa3cd1229a5e729c3e92f9e9ed132db7599c90fb14"),
)
# Native float-to-int leaf used by the bearing approximation.
CONVERSION_VA = 0x20B20
CONVERSION_BYTES = bytes.fromhex("f30f2c442404c20400")


def _assess(payload: bytes) -> dict:
    """Verify local evidence without treating byte identity as gameplay proof.

    Reject foreign/mixed prerequisites before producing an affirmative audit.
    Known Coverage and QB-spy edits are validated by their actual owners; no
    blind prologue/operand normalization can disguise a foreign installation.
    """
    if not isinstance(payload, bytes) or not 4096 <= len(payload) <= space.SCALE_FILE_SIZE:
        raise ValueError("Expected bounded default.xbe bytes, not a disc or archive")
    image = XbeImage(payload)
    states = {}
    for name, module in (("initial_drop", drop), ("qb_spy", spy),
                         ("coverage", coverage), ("catch", catch)):
        state = module.status(payload)
        if state not in ("retail", "applied"):
            raise ValueError(f"Foreign or mixed {name} prerequisites")
        states[name] = state
    for va, size, digest in GUARDS:
        if hashlib.sha256(image.read(va, size)).hexdigest() != digest:
            raise ValueError(f"Foreign facing dependency at {va:#x}")
    if image.read(CONVERSION_VA, len(CONVERSION_BYTES)) != CONVERSION_BYTES:
        raise ValueError("Foreign bearing conversion leaf")
    callbacks = []
    for name in ("zone_first", "zone_later"):
        va, retail = spy.HOOKS[name]
        hook = image.read(va, len(retail))
        callbacks.append(dict(va=hex(va), bytes=hook.hex(),
                              owner=spy.OWNER if states["qb_spy"] == "applied" else "retail",
                              target=hex(va + 5 + struct.unpack_from("<i", hook, 1)[0])
                              if states["qb_spy"] == "applied" else None))
    knots = [struct.unpack("<2f", image.read(0x50B330 + i * 8, 8)) for i in range(5)]
    return dict(
        schema=SCHEMA, experimental=True, runtime_witnessed=False,
        evidence_verified=True, patch_available=False, changed_bytes=0,
        input_sha256=hashlib.sha256(payload).hexdigest(), input_bytes=len(payload),
        states=states, callbacks=callbacks, requests=[],
        effective_facing=dict(
            routine="0x217ae0", body_heading="[P+0x18]+0x50",
            rotation="[[P+0x14]+0x34]", rotation_routine="0x3ca1e0",
            note="The native quaternion rotation contributes to facing; AI heading alone is insufficient."),
        reaction=dict(
            routine="0x1f4250", coverage_factor_index=6,
            angle_knots=[dict(angle_units=int(x), contribution=y) for x, y in knots],
            coverage_formula="C * patch_slope" if states["coverage"] == "applied" else "(C + 0.25) * 0.15",
            patch_slope=coverage.PATCH_SLOPE if states["coverage"] == "applied" else None,
            catch_hook=hex(catch.HOOK_VA),
            note="Facing is already counted here. The Interception catch roll is a separate later stage."),
        tiers=[
            dict(id="initial_drop", implementation="shipped", evidence="PROVED bounded initializer",
                 owner=drop.OWNER, limitation="Later facing, receiver pickup and ball response are unchanged."),
            dict(id="sustained_facing", implementation="deferred", evidence="HYPOTHESIS",
                 blockers=["Relevant receiver identity and crossing/release trace in both callbacks",
                           "Effective-facing control through animation and movement hysteresis",
                           "Assignment, snap, user takeover and exceptional pursuit lifecycle",
                           "Shared callback detour contract with the existing QB-spy owner"]),
            dict(id="press_bail", implementation="deferred", evidence="HYPOTHESIS",
                 blockers=["Validated press classification after alignment adjustments",
                           "A proved bail donor and transition, including a receiver already beyond the corner",
                           "Thirds versus four-deep assignment identity; modes 9/10 occur in both"]),
            dict(id="ball_reaction_adjustment", implementation="deferred", evidence="HYPOTHESIS",
                 blockers=["A scoped adjustment justified beyond the existing native facing contribution",
                           "Matched movement and reaction traces with Coverage and catch options controlled"]),
        ],
    )


def assess(payload: bytes) -> dict:
    """Return verified read-only evidence, or ValueError for unsupported input."""
    try:
        return _assess(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError) as exc:
        raise ValueError(f"Deep-zone evidence unavailable: {exc}") from exc


def read_xbe(path: Path) -> bytes:
    """Bounded descriptor read even if a caller supplies a growing/non-XBE file."""
    with path.open("rb") as stream:
        payload = stream.read(space.SCALE_FILE_SIZE + 1)
    if len(payload) > space.SCALE_FILE_SIZE:
        raise ValueError("Input exceeds the supported default.xbe size; no disc/archive reads")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", required=True, type=Path, help="extracted default.xbe, read only")
    args = parser.parse_args(argv)
    try:
        report = assess(read_xbe(args.xbe))
    except (OSError, ValueError, TypeError, KeyError, IndexError, struct.error) as exc:
        print(f"Deep-zone evidence refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
