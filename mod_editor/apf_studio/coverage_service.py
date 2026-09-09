"""Logical coverage profiles shared by project, preview and Build."""
from __future__ import annotations

import hashlib

from mod_editor.core import apf2k8_coverage_tuning as coverage
from mod_editor.core.errors import ValidationError
from .models import Modification


def validate_metadata(asset_id, value):
    if asset_id != coverage.PROFILE_ASSET_ID:
        raise ValidationError("Coverage Geometry asset identity changed")
    if value != {"schema": coverage.PROFILE_SCHEMA}:
        raise ValidationError("Coverage Geometry metadata changed")
    return value


def validate_payload(data, asset_id, metadata):
    validate_metadata(asset_id, metadata)
    return coverage.decode_profile(data)


def read_profile(modification):
    data = modification.replacement_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != modification.replacement_sha256:
        raise ValidationError("Coverage Geometry payload changed after staging")
    return validate_payload(data, modification.asset_id, dict(modification.metadata))


def stage_profile(session, edits):
    payload = coverage.encode_profile(edits)
    normalized = coverage.decode_profile(payload)
    digest = hashlib.sha256(payload).hexdigest()
    updated = dict(session._modifications)
    updated.pop(coverage.PROFILE_ASSET_ID, None)
    probe = Modification(coverage.PROFILE_ASSET_ID, coverage.PROVIDER_KIND,
                         session.replacements_root / (digest + ".json"), digest,
                         {"schema": coverage.PROFILE_SCHEMA})
    # Validate the full composition before writing a payload or recording Undo.
    from . import play_design_service
    play_design_service.check_composition([*updated.values(), *([probe] if normalized else [])])
    preview, report = coverage.compose_geometry(
        session._master_play_body(), normalized,
        package_maps=session._active_package_maps(updated),
        routes=session._active_route_requests(updated))
    if normalized:
        session._store_payload(digest, payload, ".json")
        updated[probe.asset_id] = probe
    if updated != session._modifications:
        session._record_undo()
        session._modifications = updated
    return report


def context(session):
    canonical = session._master_play_body()
    modification = session._modifications.get(coverage.PROFILE_ASSET_ID)
    edits = () if modification is None else read_profile(modification)
    preview, report = coverage.compose_geometry(
        canonical, edits, package_maps=session._active_package_maps(),
        routes=session._active_route_requests())
    # Inspect source defaults with the pin; parse the already-verified composed
    # body separately so route clones update every shared assignment use.
    defaults = coverage.inspect_zones(canonical)
    _, zones = coverage._parsed(preview)
    return defaults, tuple(zones.values()), edits, report


def main(argv=None):
    """Validate an authored profile and emit a derived receipt, not game data."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Verify Coverage Geometry; gameplay UNWITNESSED")
    parser.add_argument("index_0a", type=Path)
    parser.add_argument("profile", type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    edits = coverage.decode_profile(args.profile.read_bytes())
    _entry, report = coverage.compile_outer_entry(args.index_0a, edits)
    with args.receipt.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
