"""Project/session adapter for the APF designer's single atomic logical plan."""
from __future__ import annotations

from mod_editor.core.apf2k8_play_designer import (
    PROVIDER_KIND, SCHEMA, SELECTOR, decode_plan, encode_plan, normalize_plan, sha,
)
from mod_editor.core.apf2k8_play_design_build import build_design
from mod_editor.core.errors import ValidationError
from .models import Modification


def metadata(plan: dict) -> dict:
    return {"schema": SCHEMA, "source_sha256": plan["source_sha256"]}


def validate_metadata(asset_id: str, value: dict) -> dict:
    if asset_id != SELECTOR or not isinstance(value, dict) or set(value) != {"schema", "source_sha256"} or value["schema"] != SCHEMA:
        raise ValidationError("APF design target metadata changed.")
    digest = value["source_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValidationError("APF design source pin is malformed.")
    return value


def validate_payload(data: bytes, asset_id: str, value: dict) -> dict:
    validate_metadata(asset_id, value)
    plan = decode_plan(data)
    if metadata(plan) != value:
        raise ValidationError("APF design payload and metadata source pins differ.")
    return plan


def read_modification(modification: Modification) -> dict:
    if modification.kind != PROVIDER_KIND:
        raise ValidationError("This replacement is not an APF design plan.")
    payload = modification.replacement_path.read_bytes()
    if sha(payload) != modification.replacement_sha256:
        raise ValidationError("The APF design payload changed after staging.")
    return validate_payload(payload, modification.asset_id, dict(modification.metadata))


def check_composition(modifications) -> None:
    items = tuple(modifications)
    designs = [m for m in items if m.kind == PROVIDER_KIND]
    if len(designs) > 1:
        raise ValidationError("Only one atomic APF design plan may be staged.")
    conflicts = {
        "formation_package_map": "Who lines up (formation_package_map)",
        "play_assignment_route": "Assignment Routes (play_assignment_route)",
        "formation_alignment": "Formation Alignment (formation_alignment)",
        "splb_book_membership": "Fine-tune Plays / CPU Audibles (splb_book_membership)",
        "coverage_geometry": "Coverage Geometry (coverage_geometry)",
        "apf_scheme_presets": "Scheme Presets (apf_scheme_presets)",
    }
    if designs:
        for item in items:
            if item.kind in conflicts:
                raise ValidationError(
                    "Design Play/Formation (apf_play_design) conflicts with "
                    + conflicts[item.kind]
                    + ". Build them separately or revert one before staging; "
                    "a common MASTER/CPU compiler is required.")



def stage_plan(session, plan: dict) -> dict:
    plan = normalize_plan(plan)
    payload = encode_plan(plan)
    digest = sha(payload)
    previous = session._modifications.get(SELECTOR)
    prospective = [m for m in session.modifications if m.asset_id != SELECTOR]
    probe = Modification(SELECTOR, PROVIDER_KIND, session.replacements_root / (digest + ".json"), digest, metadata(plan))
    check_composition([*prospective, probe])
    result = build_design(session.source.index_0a, plan)
    if previous is not None and previous.replacement_sha256 == digest:
        return result.report
    stored = session._store_payload(digest, payload, ".json")
    modification = Modification(SELECTOR, PROVIDER_KIND, stored, digest, metadata(plan))
    session._record_undo()
    session._modifications[SELECTOR] = modification
    return result.report


def staged_plan(session) -> dict | None:
    modification = session._modifications.get(SELECTOR)
    return None if modification is None else read_modification(modification)


def compile_modification(index, modification: Modification):
    return build_design(index, read_modification(modification))
