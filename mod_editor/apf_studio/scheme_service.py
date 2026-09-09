"""Stage authored recipes; compose them after existing CPU-book selectors."""
from __future__ import annotations

import hashlib
import json

from mod_editor.core import apf2k8_scheme_presets as presets
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_book_identity import filename_id, read_resource
from mod_editor.core.apf2k8_book_clone import rebuild_resource
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body, playbook_inventory
from mod_editor.core.errors import ValidationError
from .models import Modification

PROVIDER_KIND = "apf_scheme_presets"
SCHEMA = "apf2k8_staged_scheme_presets/v1"
SELECTOR = "apf:playbooks:scheme-presets"


def validate_metadata(asset_id, value):
    if asset_id != SELECTOR or value != {"schema": SCHEMA}:
        raise ValidationError("Scheme Presets identity or metadata changed")
    return value


def validate_payload(data, asset_id, metadata):
    validate_metadata(asset_id, metadata)
    if len(data) > 131072:
        raise ValidationError("Scheme Presets payload exceeds its bound")
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError("Duplicate Scheme Presets JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict) or set(value) != {"schema", "presets"} or value["schema"] != SCHEMA:
            raise ValidationError("Scheme Presets schema changed")
        recipes = value["presets"]
        if not isinstance(recipes, list) or not 1 <= len(recipes) <= 3:
            raise ValidationError("Choose one to three scheme presets")
        for recipe in recipes:
            presets.validate_recipe(recipe)
            if recipe != presets.load_preset(recipe["id"]):
                raise ValidationError("Scheme Presets recipe differs from the reviewed product recipe")
        if len({r["id"] for r in recipes}) != len(recipes):
            raise ValidationError("Duplicate scheme preset")
        return recipes
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ValidationError(f"Invalid Scheme Presets payload: {exc}") from exc


def read_profile(modification):
    payload = modification.replacement_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != modification.replacement_sha256:
        raise ValidationError("Scheme Presets payload changed after staging")
    return validate_payload(payload, modification.asset_id, dict(modification.metadata))


def compile_recipes(index, recipes, changes=(), *, encode=True):
    master = playbook_inventory.parse_apf_body(read_master_play_body(index), 180, 0)
    results = []
    for recipe in recipes:
        source = read_resource(index, filename_id(recipe["book_type"]), "spb", "SPLB")
        outer = source[1].table_index
        original = splb.parse_book(source[3], outer)
        selected = tuple(c for c in changes if c.outer_index == outer)
        legacy = splb.compile_book(original, selected) if selected else None
        current = splb.parse_book(legacy.replacement, outer) if legacy else original
        replacement, report = presets.apply_preset(current, recipe, master)
        final = splb.parse_book(replacement, outer)
        report["composition"] = {
            "order": ["fine_tune_and_audible_selectors", "scheme_preset"],
            "prior_selectors": [c.selector for c in selected],
            "precedence": "The selected preset owns membership and tags in its recipe records.",
            "prior_verification": legacy.report if legacy else None,
        }
        report["personnel_availability"] = {
            "before": splb.personnel_availability(original),
            "after": splb.personnel_availability(final),
        }
        repeated, _ = presets.apply_preset(final, recipe, master)
        if repeated != replacement:
            raise ValidationError("Scheme Presets reapply is not idempotent")
        if encode:
            entry, transport = rebuild_resource(source, replacement)
            report["transport"] = transport
        else:
            entry = b""
        results.append((outer, entry, report))
    return results


def stage_presets(session, preset_ids):
    ids = tuple(preset_ids)
    updated = dict(session._modifications)
    updated.pop(SELECTOR, None)
    if not ids:
        if updated != session._modifications:
            session._record_undo()
            session._modifications = updated
        return []
    payload = (json.dumps({"schema": SCHEMA, "presets": [presets.load_preset(i) for i in ids]},
                          sort_keys=True, separators=(",", ":")) + "\n").encode()
    recipes = validate_payload(payload, SELECTOR, {"schema": SCHEMA})
    digest = hashlib.sha256(payload).hexdigest()
    modification = Modification(SELECTOR, PROVIDER_KIND,
                                session.replacements_root / (digest + ".json"), digest,
                                {"schema": SCHEMA})
    from . import play_design_service
    play_design_service.check_composition([*updated.values(), modification])
    results = compile_recipes(session.source.index_0a, recipes, session._active_splb_changes())
    session._store_payload(digest, payload, ".json")
    updated[SELECTOR] = modification
    if updated != session._modifications:
        session._record_undo()
        session._modifications = updated
    return [row[2] for row in results]
