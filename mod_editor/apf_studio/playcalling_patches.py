"""Canonical curve presets accepted by the existing consent-based installer."""
from __future__ import annotations

import importlib
import tomllib

from mod_editor.core.errors import ValidationError
from .playcalling_service import CURVE_PRESETS

FILENAME = "54540807 - Studio personnel curves.patch.toml"


def module():
    return importlib.import_module("mod_editor.core.apf2k8_playcall_curves_patch")


def prepare(profile_name, side, *, curves=None):
    curves = curves if curves is not None else module()
    if side not in CURVE_PRESETS or profile_name not in {"base", "tu1"}:
        raise ValidationError("Choose offense or defense and a supported game version")
    profile = next((p for p in curves.PROFILES if (p.name == "base") == (profile_name == "base")), None)
    if profile is None:
        raise ValidationError("This game version has no verified personnel curve patch")
    document = curves.build_curve_patch(profile,
        offense_category_curve=CURVE_PRESETS[side] if side == "offense" else None,
        defense_category_curve=CURVE_PRESETS[side] if side == "defense" else None)
    payload = document.as_toml().encode("utf-8")
    validate(payload, curves=curves)
    return payload


def validate(payload, *, curves=None):
    curves = curves if curves is not None else module()
    parsed = tomllib.loads(payload.decode("utf-8"))
    for profile in curves.PROFILES:
        for side, values in CURVE_PRESETS.items():
            document = curves.build_curve_patch(profile,
                offense_category_curve=values if side == "offense" else None,
                defense_category_curve=values if side == "defense" else None)
            if parsed == tomllib.loads(document.as_toml()):
                rows = parsed.get("patch", [])
                if not rows or any(row.get("is_enabled") is not True for row in rows):
                    raise ValidationError("The personnel curve patch must be enabled")
                return profile, True
    raise ValidationError("Choose the Studio's unchanged personnel curve preset for BASE or Title Update 1.1")


def main(argv=None):
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Export an experimental personnel curve preset; gameplay UNWITNESSED")
    parser.add_argument("--profile", choices=("base", "tu1"), required=True)
    parser.add_argument("--side", choices=("offense", "defense"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = prepare(args.profile, args.side)
    if not args.output.name.endswith(".patch.toml"):
        raise ValidationError("Choose a new .patch.toml export file")
    with args.output.open("xb") as stream:
        stream.write(payload)
    validate(args.output.read_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
