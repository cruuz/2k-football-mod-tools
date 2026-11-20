"""Portable frozen authoring inputs for the full Studio builder, never executed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
import zipfile

from . import modpack as m, modpack_files as f

TOKEN = "@pack/"


def compose_project(document):
    """Resolve layered digit art by native target, with the last layer winning.

    The importer accepts aliases such as jersey and jersey_digit. Comparing
    author dictionaries instead of normalized selectors let both layers into
    v0.6. Keep each winning edit whole and in its original order, so every
    selection of the resulting edits has at most one writer for each digit.
    Frozen originals are retained separately for provenance.
    """
    from tools.nfl_live_numbers_nameplate_targets import normalize_selector

    edits = document.get("edits", [])
    winners = {}
    for index, edit in enumerate(edits):
        if edit.get("kind") == "live_number_nameplate":
            key = normalize_selector(edit["asset_code"], edit["side"], edit["variant"],
                                     edit["family"], edit["digit"])
            winners[key] = index
    result = []
    for index, edit in enumerate(edits):
        if edit.get("kind") == "live_number_nameplate":
            code, side, variant, family, digit = normalize_selector(
                edit["asset_code"], edit["side"], edit["variant"], edit["family"], edit["digit"])
            if winners[(code, side, variant, family, digit)] != index:
                continue
            # Product edit families use the short names, including the quality
            # fallback path for tiny digit slots.
            family = {"jersey_digit": "jersey", "helmet_digit": "helmet",
                      "arm_digit": "arm", "nameplate_atlas": "nameplate"}[family]
            edit = dict(edit, asset_code=code, side=side, family=family)
        result.append(edit)
    return dict(document, edits=result)


def prepare(recipe_path, work, *, stack=None, marks_pack=None, patched_image=None):
    """Capture effective overrides and every referenced league PNG, preserving originals."""
    recipe_path, work = f._path(recipe_path), f._output_path(work)
    stack = f._path(stack or Path(m.platform_compat.absolute_path(__file__)).parents[2])
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    m._require(isinstance(recipe, dict) and isinstance(recipe.get("overrides"), dict)
               and isinstance(recipe.get("preset"), str), "Expected a frozen Studio recipe with preset and overrides")
    frozen = recipe.get("freeze", {})
    project_info = frozen.get("project") or {}
    project_path = f._path(project_info.get("path") or recipe["inputs"]["teams_2026"]["project"])
    original_project = project_path.read_bytes()
    if project_info.get("sha256"):
        m._require(hashlib.sha256(original_project).hexdigest() == project_info["sha256"], "Frozen league project SHA-256 differs")
    assets, paths = {}, {}

    def capture(path):
        path = f._path(m.platform_compat.absolute_path(str(path).replace("<stack>/", str(stack) + "/")))
        key = m.platform_compat.path_key(path)
        if key in paths:
            return TOKEN + paths[key]
        m._require(path.exists(), f"Missing authoring source: {path}")
        identity = hashlib.sha256(key.encode()).hexdigest()[:20]
        if path.is_dir():
            member = f"assets/trees/{identity}"
            paths[key] = member
            pending = [(path, member)]
            while pending:
                directory, prefix = pending.pop()
                for entry in sorted(directory.iterdir()):
                    child = f._path(entry)
                    info = child.lstat()
                    m._require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_reparse_tag", 0),
                               f"Source tree contains a symlink or reparse point: {child}")
                    name = prefix + "/" + child.name
                    f._asset_name(name)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append((child, name))
                    elif stat.S_ISREG(info.st_mode):
                        assets[name] = child
                        paths[m.platform_compat.path_key(child)] = name
        else:
            basename = re.sub(r"[^A-Za-z0-9._-]", "_", path.name).rstrip(". ") or "source"
            member = f"assets/files/{identity}_{basename}"
            f._asset_name(member)
            assets[member], paths[key] = path, member
        return TOKEN + member

    def relocate(value):
        if isinstance(value, dict):
            return {k: relocate(v) for k, v in value.items()}
        if isinstance(value, list):
            return [relocate(v) for v in value]
        if isinstance(value, str) and (value.startswith(("/", "~/", "<stack>/", "\\\\")) or re.match(r"^[A-Za-z]:[\\/]", value)):
            return capture(value)
        return value

    effective = dict(recipe["overrides"])
    if patched_image is not None:
        from . import mod_build, nfl2k5_backfield_cards
        try:
            payload = mod_build._xbe_bytes(Path(patched_image))
            card_state = nfl2k5_backfield_cards.status(payload)
        except (OSError, ValueError):
            payload = None
            card_state = "unavailable"
        if card_state in ("retail", "applied"):
            effective["backfield_cards"] = card_state == "applied"
        qb = mod_build._core_module("nfl2k5_sim_qb_injuries")
        if effective.get("sim_qb_injuries") is not None or (qb is not None and payload is not None):
            m._require(qb is not None and payload is not None, "Cannot verify the disc's simulated quarterback injury setting")
            state = qb.read_settings(payload)
            mode = effective.get("sim_qb_injuries")
            if mode is not None:
                m._require(state.get("mode") == mode and (mode != "custom" or
                           state["custom_rate"] == effective.get("sim_qb_injury_rate", mod_build.BuildPlan.sim_qb_injury_rate)),
                           "The disc and source recipe select different simulated quarterback injury settings")
            if state["status"] == "applied":
                effective.update(sim_qb_injuries=state["mode"], sim_realism=True, k128_memory=True)
                if state["mode"] == "custom":
                    effective["sim_qb_injury_rate"] = state["custom_rate"]
        room = mod_build._core_module("nfl2k5_qb_room")  # b81 qb34: record the disc's quarterback room rules
        if effective.get("qb_room") is not None or (room is not None and payload is not None):
            from .nfl2k5_build_settings import qb_room_level
            m._require(room is not None and payload is not None, "Cannot verify the disc's quarterback room setting")
            room_state = room.read_settings(payload)
            m._require(room_state["status"] in ("retail", "applied"), "Cannot verify the disc's quarterback room setting")
            installed = "realistic" if room_state["status"] == "applied" else "retail"
            named = effective.get("qb_room")
            if named is not None:
                m._require(named == installed, "The disc and source recipe select different quarterback room settings")
            else:
                # What a rebuild of this recipe would install without the key (the rule needs the preset's fields).
                try:
                    follows = mod_build._qb_room_level(build_plan(
                        {"preset": recipe["preset"], "overrides": {k: v for k, v in effective.items() if k != "qb_room"}}))
                except (KeyError, ValueError):
                    follows = qb_room_level(None, effective.get("sim_qb_injuries"))
                if follows != installed and not (follows is None and installed == "retail"):
                    effective["qb_room"] = installed
    if marks_pack:
        effective["official_marks_pack"] = str(marks_pack)
    from . import nfl2k5_official_marks as marks
    marked_features = {"espn_marks_2026", "espn_wipes_boards_2026"} | {row["feature"] for row in marks.CATALOG.values()}
    if effective.get("official_marks_pack") or any(effective.get(feature) for feature in marked_features):
        root = effective.get("official_marks_pack")
        m._require(root, "The source recipe needs the complete official marks pack. Supply --marks-pack DIR.")
        try:
            for name in marks.ASSETS:
                marks.asset_path(name, root)
        except ValueError as exc:
            raise m.ModpackError(f"Cannot bundle incomplete official marks sources: {exc} Supply --marks-pack with the complete reviewed pack.") from exc
    overrides = relocate(effective)
    roster = frozen.get("roster_edits", {})
    if isinstance(roster, dict) and roster.get("sha256") and roster.get("path") == effective.get("roster_edits"):
        m._require(m.hash_file(roster["path"]) == roster["sha256"], "Frozen roster SHA-256 differs")
    project = compose_project(relocate(json.loads(original_project)))
    work.mkdir(parents=True, exist_ok=True)
    portable_project = f._path(work / "league-project.json")
    with f._transaction(portable_project, (recipe_path, project_path, *assets.values()), overwrite=True) as part:
        part.write_text(json.dumps(project, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    assets.update({"assets/documents/frozen-recipe.json": recipe_path,
                   "assets/documents/frozen-project.json": project_path,
                   "assets/documents/league-project.json": portable_project})
    portable = dict(schema="softdrink_sources/v1", preset=recipe["preset"], overrides=overrides,
                    project=TOKEN + "assets/documents/league-project.json",
                    original_recipe=TOKEN + "assets/documents/frozen-recipe.json",
                    original_project=TOKEN + "assets/documents/frozen-project.json")
    return portable, assets


def resolve(document, root):
    root = f._path(m.platform_compat.absolute_path(root))
    if isinstance(document, dict):
        return {k: resolve(v, root) for k, v in document.items()}
    if isinstance(document, list):
        return [resolve(v, root) for v in document]
    if isinstance(document, str) and document.startswith(TOKEN):
        member = document[len(TOKEN):]
        f._asset_name(member)
        path = f._contained_path(root, member)
        m._require(path.exists(), f"Missing or escaping source: {member}")
        return str(path)
    if isinstance(document, str):
        m._require(not document.startswith(("/", "~/", "\\\\")) and not re.match(r"^[A-Za-z]:[\\/]", document),
                   "Portable source document contains an external absolute path")
    return document


def materialize(recipe, directory, *, resume=False, console_target=None):
    """Create editable absolute-path working copies; frozen assets remain intact."""
    m._require(recipe.get("schema") == "softdrink_sources/v1", "Pack has no portable Studio sources")
    root = f._path(m.platform_compat.absolute_path(f._output_path(directory)))
    local = resolve(recipe, root)
    project = compose_project(resolve(json.loads(Path(local["project"]).read_text(encoding="utf-8")), root))
    project_path = f._contained_path(root, "SOFTDRINK-league-project.json")
    recipe_path = f._contained_path(root, "SOFTDRINK-build-recipe.json")
    local["project"] = str(project_path)

    def matches(path, data):
        return path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data

    if console_target is not None:
        from . import nfl2k5_console_memory as memory
        value = memory.normalize(console_target)
        original_memory = memory.of(recipe)
        overrides = dict(local.get("overrides", {}))
        if value == 64 and original_memory != 64:
            # The builder installs the calendar and 128-season cap together when either is enabled.
            source_plan = build_plan(local)
            source_plan.calendar_engine = source_plan.season_cap or source_plan.calendar_engine
            profile = memory.recommended_profile(source_plan)
            if profile.get("calendar_engine") is False:
                profile["season_cap"] = False
            overrides.update(profile)
        elif value == 128 and original_memory == 64:
            # A compact game's save warning would direct a player on standard back to standard.
            overrides.pop("edition_save_notes", None)
        # A CLI extraction already has the authored target, without the GUI's extra target field.
        from_cli = value == original_memory and resume and matches(recipe_path, json.dumps(local, indent=2).encode("utf-8"))
        if not from_cli:
            local[memory.FIELD] = value
            local["overrides"] = {**overrides, memory.FIELD: value}
    files = ((project_path, (json.dumps(project, indent=2, sort_keys=True) + "\n").encode("utf-8")),
             (recipe_path, json.dumps(local, indent=2).encode("utf-8")))
    # Verify both destinations before writing. An interruption between files is resumable.
    for path, data in files:
        if path.exists():
            m._require(resume and matches(path, data),
                       f"Choose a new source folder to preserve your edits in {path.name}")
    for path, data in files:
        if not path.exists():
            with f._transaction(path) as part:
                part.write_bytes(data)
    return local


def write_bundle(output, recipe, assets, *, overwrite=False):
    """Optional source-only ZIP when distributing sources separately is preferable."""
    output = f._output_path(output)
    with f._transaction(output, tuple(assets.values()), overwrite) as part:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            rows = []
            for name, path in assets.items():
                f._asset_name(name)
                with f._path(path).open("rb") as stream:
                    rows.append(f._member(z, name, iter(lambda: stream.read(f.BLOCK), b"")))
            z.writestr("sources.json", json.dumps(dict(schema="softdrink_source_bundle/v1", recipe=recipe, assets=rows)))
    return dict(name=Path(output).name, size=Path(output).stat().st_size, sha256=m.hash_file(output),
                asset_count=len(rows), assets_bytes=sum(r["length"] for r in rows), compressed_bytes=sum(r["compressed_bytes"] for r in rows))


def extract_bundle(bundle, directory, expected, *, resume=False, progress=None):
    bundle = f._path(bundle)
    m._require(isinstance(expected, dict) and {"size", "sha256"} <= expected.keys(), "The pack does not declare an optional sources file")
    m._require(Path(bundle).stat().st_size == expected["size"] and m.hash_file(bundle, progress=progress) == expected["sha256"],
               "This sources file does not match the finished pack")
    m._zip_directory_guard(f._path(bundle))
    with zipfile.ZipFile(bundle) as z:
        m._require(len(z.namelist()) == len(set(z.namelist())), "Duplicate source ZIP members")
        m._require(z.getinfo("sources.json").file_size <= m.MAX_MANIFEST_BYTES, "Sources manifest is too large")
        doc = json.loads(z.read("sources.json"))
        m._require(doc.get("schema") == "softdrink_source_bundle/v1", "Unknown sources bundle")
        for asset in doc["assets"]:
            f._asset_name(asset["member"])
            m._int(asset["length"], "asset.length")
            m._hex64(asset["sha256"], "asset.sha256")
        m._require(sum(a["length"] for a in doc["assets"]) <= 8 * 1024**3, "Sources exceed 8 GiB")
    # Same streamed SHA-256 and safe-path extractor as embedded sources.
    manifest = m.Manifest("sources", "", "", "", "", {}, {}, {}, {}, (), recipe=doc["recipe"], raw=doc)
    f.extract_assets(m.Pack(Path(bundle), manifest, Path(bundle).stat().st_size), directory, resume=resume, progress=progress)
    return doc["recipe"]


def build_plan(recipe, source="", target=""):
    from dataclasses import fields
    from . import mod_build, nfl2k5_build_settings
    initial = mod_build.BuildPlan(str(source), str(target), console_memory=recipe["overrides"].get("console_memory", 128))
    plan = mod_build.apply_preset(initial, recipe["preset"])
    if "sim_qb_injuries" not in recipe["overrides"]:
        # Older source recipes predate the quarterback setting and the experimental preset's heap default.
        plan.sim_qb_injuries = None
        plan.k128_memory = initial.k128_memory
    if "qb_room" not in recipe["overrides"]:
        # b81 qb34 (DESIGN_CHANGES C1): a recipe that does not name the room follows its quarterback injury setting.
        plan.qb_room = None
    known = {field.name for field in fields(plan)} - {"source", "target", "overwrite"}
    for key, value in recipe["overrides"].items():
        m._require(key in known, f"Recipe requires an unknown Studio option: {key}")
        setattr(plan, key, tuple(value) if isinstance(getattr(plan, key), tuple) and isinstance(value, list) else value)
    nfl2k5_build_settings.validate_sim_qb_injuries(plan.sim_qb_injuries, plan.sim_qb_injury_rate)
    nfl2k5_build_settings.validate_qb_room(plan.qb_room)
    return plan


def build_project(plan, project, progress):
    """Full Studio authoring path, deliberately separate from fast installation."""
    from . import mod_build
    if isinstance(plan, mod_build._ReleasedV09Update):
        raise ValueError("Use your retail disc to include league artwork with these v0.9 updates.")
    from .nfl2k5_source_cache import Nfl2k5SourceCache
    from .nfl2k5_build_service import Nfl2k5BuildService
    service = Nfl2k5BuildService()
    progress = progress or (lambda *_: None)
    progress("Checking the SOFTDRINK artwork recipe", 0, 0)
    document = service.preflight_project(Path(project))
    mod_build.preflight_project_options(plan, document)
    mod_build.preflight_board_source(plan, progress)
    if not document["edits"]:
        return mod_build.build(plan, progress, require_change=True)
    cache = Nfl2k5SourceCache().index(Path(plan.source), progress=progress)
    def project_progress(event):
        progress(getattr(event, "message", str(event)), getattr(event, "completed", 0), getattr(event, "total", 0))
    return mod_build.build(plan, progress, require_change=True,
                           _project_builder=lambda output: service.build(cache, Path(project), output, project_progress))
