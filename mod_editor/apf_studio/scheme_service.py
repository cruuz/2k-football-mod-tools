"""Stage authored recipes; compose them after existing CPU-book selectors."""
from __future__ import annotations

import hashlib
import json

from mod_editor.core import apf2k8_scheme_presets as presets
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_offensive_schemes as schemes
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core.apf2k8_book_identity import filename_id, read_resource
from mod_editor.core.apf2k8_book_clone import rebuild_resource, clone_body
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body, playbook_inventory
from mod_editor.core.errors import ValidationError
from .models import Modification

PROVIDER_KIND = "apf_scheme_presets"
SCHEMA = "apf2k8_staged_scheme_presets/v1"
SELECTOR = "apf:playbooks:scheme-presets"
REPLACEMENT_SCHEMA = "apf2k8_stock_scheme_content/v1"
STOCK_TARGETS = tuple(name for name in splb.BOOK_SIDES
                     if name.startswith("O-") or name == "USER-o")
# Starting content, not a claim of newly authored routes/blocking. Retain each
# donor's complete special-call tail and use the existing membership recipes.
SCHEME_CONTENT = {
    "air_coryell": ("O-TwoBack", None),
    "erhardt_perkins": ("USER-o", None),
    "west_coast": ("O-WestCoast", None),
    "west_coast_spread": ("O-Shotgun", None),
    "spread_to_run": ("O-Shotgun", "spread-to-run"),
    "wide_zone": ("O-ZoneBlock", "wide-zone"),
    "power_gap": ("O-ManBlock", "pro-power"),
    "pro_spread": ("O-Singleback3WR", None),
}


def replacement_recipe(book_type, scheme_id):
    if book_type not in STOCK_TARGETS or scheme_id not in SCHEME_CONTENT:
        raise ValidationError("Choose one of the eight stock offensive books and eight schemes")
    return {"schema": REPLACEMENT_SCHEMA, "book_type": book_type, "scheme_id": scheme_id}


def replace_starting_content(original, donor, master_body, recipe):
    """Replace a whole book from a named donor, never merge old target plays.

    The donor supplies coherent special records/tails. Existing writers own
    membership, rating fields, header renaming and derived cache rebuilding.
    """
    scheme = schemes.get_scheme(recipe["scheme_id"])
    donor_name, preset_id = SCHEME_CONTENT[scheme.id]
    if original.name != recipe["book_type"] or donor.name != donor_name:
        raise ValidationError("Recipe book names changed; reload the game and review again")
    if len(original.body) != len(donor.body):
        raise ValidationError(f"{original.name} cannot hold this recipe's decoded book; choose another book")
    output = donor.body
    preset_report = None
    if preset_id:
        master = playbook_inventory.parse_apf_body(master_body, 180, 0)
        output, preset_report = presets.apply_preset(donor, presets.load_preset(preset_id), master)
    categories = {c.id: c for c in model.category_table(master_body)}
    ratings = []
    deltas = dict(scheme.category_rating_deltas)
    parsed = splb.parse_book(output, donor.outer_index)
    for form in dict.fromkeys(r.formation_index for r in parsed.records if r.populated and r.formation_index < 151):
        record = next(r for r in parsed.records if r.populated and r.formation_index == form)
        group = schemes.personnel_group(categories[record.category_index])
        before = splb.formation_ratings(output, form)
        after = tuple(max(1, min(7, n + deltas.get(group, 1) + delta))
                      for n, delta in zip(before, scheme.formation_rating_deltas))
        output = splb.set_formation_ratings(output, form, after)
        ratings.append({"formation": form, "personnel": group, "before": before, "after": after})
    output = clone_body(splb._compact_normalize(output), original.name)
    final = splb.parse_book(output, original.outer_index)
    if final.name != original.name or splb._compact_normalize(output) != output:
        raise ValidationError("Replacement book name or rebuilt caches failed reparse")
    # Independent record census checks membership, tags and personnel against
    # the recipe donor; only its three rating fields may differ.
    expected = [r for r in parsed.records if r.populated]
    actual = [r for r in final.records if r.populated]
    rating_mask = (7 << 14) | (7 << 11) | (7 << 8)
    if not actual or len(expected) != len(actual):
        raise ValidationError("Replacement formation count failed reparse")
    for a, b in zip(expected, actual):
        if (a.entries != b.entries or a.formation_index != b.formation_index
                or a.trailer[4:] != b.trailer[4:]
                or (int.from_bytes(a.trailer[:4], 'big') & ~rating_mask)
                != (int.from_bytes(b.trailer[:4], 'big') & ~rating_mask)):
            raise ValidationError("Replacement donor membership/personnel failed reparse")
    for row in ratings:
        if splb.formation_ratings(output, row["formation"]) != row["after"]:
            raise ValidationError("Replacement scheme ratings failed reparse")
    # Both category coverage and special-tail retention remain mandatory.
    missing = [row for row, supply in splb.row_coverage(output, master_body).items()
               if 0 <= row <= 10 and not supply]
    if missing:
        raise ValidationError(f"{original.name} recipe leaves personnel rows {missing} empty; choose another scheme")
    if output[splb.ARRAY_END:0x7D98] != donor.body[splb.ARRAY_END:0x7D98]:
        raise ValidationError("Replacement changed the donor's special-call tail")
    def census(book):
        return [{"formation": r.formation_index, "category": r.category_index,
                 "plays": [e.play_index for e in r.entries],
                 "audibles": {str(e.y): e.play_index for e in r.entries if e.tagged}}
                for r in book.records if r.populated]
    return output, {"schema": REPLACEMENT_SCHEMA, "book_type": original.name,
        "scheme_id": scheme.id, "name": scheme.name, "donor": donor.name,
        "starting_recipe": preset_id, "preset_receipt": preset_report, "ratings": ratings,
        "source_sha256": hashlib.sha256(original.body).hexdigest(),
        "donor_sha256": hashlib.sha256(donor.body).hexdigest(),
        "output_sha256": hashlib.sha256(output).hexdigest(),
        "before_content": census(original), "after_content": census(final),
        "verification": {"replaced_entire_content": True, "donor_membership_reparsed": True,
                         "special_tail_preserved": True, "ordinary_rows_covered": True},
        "classification": "ADVANCED", "runtime_status": "UNWITNESSED",
        "limitations": "Authored starting content from the named donor, with beta-69 preferences. "
                       "No new routes, blocking, motion or team tendency is installed. "
                       "Every user of this shared stock book receives the replacement."}


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
        if not isinstance(recipes, list) or not 1 <= len(recipes) <= 8:
            raise ValidationError("Choose one to eight distinct stock books")
        for recipe in recipes:
            if isinstance(recipe, dict) and recipe.get("schema") == REPLACEMENT_SCHEMA:
                if recipe != replacement_recipe(recipe.get("book_type"), recipe.get("scheme_id")):
                    raise ValidationError("Stock replacement recipe fields changed")
                continue
            presets.validate_recipe(recipe)
            if recipe != presets.load_preset(recipe["id"]):
                raise ValidationError("Scheme Presets recipe differs from the reviewed product recipe")
        if len({r["book_type"] for r in recipes}) != len(recipes):
            raise ValidationError("Duplicate scheme preset target book")
        return recipes
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ValidationError(f"Invalid Scheme Presets payload: {exc}") from exc


def read_profile(modification):
    payload = modification.replacement_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != modification.replacement_sha256:
        raise ValidationError("Scheme Presets payload changed after staging")
    return validate_payload(payload, modification.asset_id, dict(modification.metadata))


def compile_recipes(index, recipes, changes=(), *, encode=True):
    master_body = read_master_play_body(index)
    master = playbook_inventory.parse_apf_body(master_body, 180, 0)
    results = []
    for recipe in recipes:
        source = read_resource(index, filename_id(recipe["book_type"]), "spb", "SPLB")
        outer = source[1].table_index
        original = splb.parse_book(source[3], outer)
        selected = tuple(c for c in changes if c.outer_index == outer)
        legacy = splb.compile_book(original, selected) if selected else None
        current = splb.parse_book(legacy.replacement, outer) if legacy else original
        replacing = recipe.get("schema") == REPLACEMENT_SCHEMA
        if replacing:
            if selected:
                raise ValidationError(f"{original.name} has Fine-tune edits. Build those first or revert them before replacing its content")
            donor_name = SCHEME_CONTENT[recipe["scheme_id"]][0]
            donor_source = read_resource(index, filename_id(donor_name), "spb", "SPLB")
            donor = splb.parse_book(donor_source[3], donor_source[1].table_index)
            replacement, report = replace_starting_content(original, donor, master_body, recipe)
        else:
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
        repeated, _ = (replace_starting_content(final, donor, master_body, recipe) if replacing
                       else presets.apply_preset(final, recipe, master))
        if repeated != replacement:
            raise ValidationError("Scheme Presets reapply is not idempotent")
        if encode:
            try:
                entry, transport = rebuild_resource(source, replacement)
            except ValidationError as exc:
                raise ValidationError(f"{original.name} cannot hold the selected recipe: {exc}. "
                                      "Choose another stock book or use an independent copy.") from exc
            report["transport"] = transport
        else:
            entry = b""
        results.append((outer, entry, report))
    return results


def stage_presets(session, preset_ids):
    return _stage_recipes(session, [presets.load_preset(i) for i in preset_ids])


def stage_replacement(session, book_type, scheme_id):
    recipe = replacement_recipe(book_type, scheme_id)
    current = session._modifications.get(SELECTOR)
    recipes = read_profile(current) if current else []
    return _stage_recipes(session, [r for r in recipes if r["book_type"] != book_type] + [recipe])


def _stage_recipes(session, recipes):
    updated = dict(session._modifications)
    updated.pop(SELECTOR, None)
    if not recipes:
        if updated != session._modifications:
            session._record_undo()
            session._modifications = updated
        return []
    payload = (json.dumps({"schema": SCHEMA, "presets": recipes},
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
