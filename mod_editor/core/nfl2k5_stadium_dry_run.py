"""Stadium and colour dry run (b791 h4, Check my project v2): the refits Build would make, tried in minutes.

Coach Edwards' beta-79 builds stopped four to five hours in on one stadium texture that could not be refit into its
fixed slot with his own Modern colour values ("cannot keep the retail scratch word:"). Every such refit depends only on
the source disc's retail stadium bundles, the project's options and its Modern colour values, so it can be tried
before the long build. This module runs the same per-bundle functions Build runs, in Build's order, on the source
disc's bundles in memory, on a process pool, and says for every stadium, time of day and weather which field, bump map
(detail normal) and divot layer would be refit, which would be kept as they are, and which refit fails:

1. Modern colour (``nfl2k5_modern_color.modern_bundle``, with the refits of ``_refit_fields``: Build's own on-disk
   refit cache, so a later Build with the same values replays them in seconds),
2. the one stadium writer that owns the bundle: Modern Arrowhead (``combined_bundle`` / ``modern_bundle``), Modern
   MetLife (``combined_bundle`` / ``modern_bundle``), the field of each modern stadium model (its ``field_span``, as its
   ``_compose`` worker places it), the practice facility (``_compose``),
3. Modern playing surfaces (``_job``), 4. Broadcast greens (``_bundle_job``).

Nothing is written to the disc or the project. The stadium models' buildings, cameras, cityscapes and shadows are
geometry compiled from the retail bundles alone: the same on every PC and every option set, so they are proved by the
release builds that include them and are skipped here unless ``stadium_models=True`` (the full ``_compose`` of every
model bundle, about ten times slower). Steps this module does not model are listed by name in ``not_covered``.

A refit that raises is recorded as ``failed`` with its reason and the bundle goes on with its bytes from before that
step (what a build that keeps the stadium as it was would do). A span a step keeps as it was (Modern colour's own
"no room in its fixed slot", and the notes of the later fixes that keep spans instead of stopping) is ``kept``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import os
import time
import traceback
from typing import Callable

SCHEMA = "nfl2k5_stadium_dry_run/v1"

TIMES = {"d": "day", "a": "afternoon", "n": "night"}
WEATHERS = {"d": "dry", "r": "rain", "s": "snow"}

#: (plan attribute, module, the label Build's progress uses) of the stadium models, in Build's order.
MODELS = (
    ("modern_sofi", "nfl2k5_sofi_model", "SoFi Stadium"),
    ("modern_highmark", "nfl2k5_highmark_model", "Highmark Stadium"),
    ("modern_att", "nfl2k5_att_model", "AT&T Stadium"),
    ("modern_levis", "nfl2k5_levis_model", "Levi's Stadium"),
    ("modern_allegiant", "nfl2k5_allegiant_model", "Allegiant Stadium"),
    ("modern_mercedes_benz", "nfl2k5_mercedes_benz_model", "Mercedes-Benz Stadium"),
    ("modern_usbank", "nfl2k5_usbank_model", "U.S. Bank Stadium"),
    ("modern_lucas_oil", "nfl2k5_lucas_oil_model", "Lucas Oil Stadium"),
    ("modern_state_farm", "nfl2k5_state_farm_model", "State Farm Stadium"),
    ("modern_hard_rock", "nfl2k5_hard_rock_model", "Hard Rock Stadium"),
    ("modern_gillette", "nfl2k5_gillette_model", "Gillette Stadium"),
    ("modern_lambeau", "nfl2k5_lambeau_model", "Lambeau Field"),
    ("modern_everbank", "nfl2k5_everbank_model", "EverBank Stadium"),
)

#: step id -> the option label people see on the Build tab (and Build's progress line)
STEP_LABELS = {
    "colour": "Modern colour and lighting",
    "arrowhead": "Modern Arrowhead",
    "metlife": "Modern MetLife Stadium",
    "practice": "Modern practice facility",
    "surfaces": "Modern playing surfaces",
    "greens": "Broadcast greens (part of Modern playing surfaces)",
    **{module: label for _attr, module, label in MODELS},
}

#: the Build tab option each step belongs to (what to untick)
STEP_OPTIONS = {
    "colour": "modern_color", "arrowhead": "modern_arrowhead", "metlife": "modern_metlife",
    "practice": "modern_practice_field", "surfaces": "modern_surfaces", "greens": "modern_surfaces",
    **{module: attr for attr, module, _label in MODELS},
}

#: receipt keys a step uses to say a span stayed as it was instead of being refit (Modern colour's ``unfit``; the
#: b791 fixes that keep a span instead of stopping the build add their own)
KEPT_KEYS = ("unfit", "kept", "kept_reason", "kept_retail", "left_out", "not_refit")


def sha(data) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def bundle_words(name: str) -> str:
    """'s13ad.iff' -> 'afternoon, dry'."""
    return f"{TIMES.get(name[3:4], name[3:4])}, {WEATHERS.get(name[4:5], name[4:5])}"


@dataclass
class DryRun:
    """What the stadium dry run found. ``rows``: one dict per refit tried (bundle, venue, step, status, part, reason);
    ``status`` is ``refit``, ``unchanged``, ``kept`` or ``failed``."""
    rows: list = field(default_factory=list)
    steps: list = field(default_factory=list)          # the step ids that ran, in Build's order
    not_covered: list = field(default_factory=list)    # [(option label, why)] selected but not modelled here
    skipped_bundles: dict = field(default_factory=dict)  # {bundle: why} bundles not tried at all
    bundles: int = 0
    workers: int = 0
    seconds: float = 0.0
    cached_colour_refits: int = 0
    platform: str = ""
    cpu_seconds: float = 0.0        # the bundle jobs' own processor time (what an idle machine needs, divided by workers)
    digests: dict = field(default_factory=dict)  # {bundle: {step: sha256 of its bytes after that step}}

    def by_status(self, status):
        return [row for row in self.rows if row["status"] == status]

    @property
    def failed(self):
        return self.by_status("failed")

    @property
    def kept(self):
        return self.by_status("kept")

    def counts(self) -> dict:
        out = {}
        for row in self.rows:
            key = (row["step"], row["status"])
            out[key] = out.get(key, 0) + 1
        return out

    def as_dict(self) -> dict:
        return dict(schema=SCHEMA, steps=list(self.steps), bundles=self.bundles, workers=self.workers,
                    seconds=round(self.seconds, 1), cpu_seconds=round(self.cpu_seconds, 1),
                    cached_colour_refits=self.cached_colour_refits, digests=dict(self.digests),
                    platform=self.platform, not_covered=[list(row) for row in self.not_covered],
                    skipped_bundles=dict(self.skipped_bundles),
                    counts={f"{step}/{status}": count for (step, status), count in sorted(self.counts().items())},
                    rows=[dict(row) for row in self.rows])


# ------------------------------------------------------------------------------------------------- which steps

def _plan_value(plan, name, default=False):
    return getattr(plan, name, default)


def selected_steps(plan) -> list:
    """The step ids of ``plan`` this dry run models, in Build's order."""
    steps = []
    if _plan_value(plan, "modern_color"):
        steps.append("colour")
    if _plan_value(plan, "modern_arrowhead"):
        steps.append("arrowhead")
    if _plan_value(plan, "modern_metlife"):
        steps.append("metlife")
    steps.extend(module for attr, module, _label in MODELS if _plan_value(plan, attr))
    if _plan_value(plan, "modern_practice_field"):
        steps.append("practice")
    if _plan_value(plan, "modern_surfaces"):
        steps.extend(("surfaces", "greens"))
    return steps


def not_covered(plan, *, stadium_models=False) -> list:
    """[(option label, why)] of the selected stadium steps whose refits this dry run does not try."""
    out = []
    if _plan_value(plan, "modern_venues_2026", ""):
        out.append(("2026 venue art", "the field art comes from your venue art folder; Build checks each field when it "
                    "composes it"))
    if _plan_value(plan, "modern_metlife_model"):
        out.append(("Modern MetLife model", "the stadium building and cameras only (no field refit)"))
    if not stadium_models and any(_plan_value(plan, attr) for attr, _m, _l in MODELS):
        out.append(("the modern stadium buildings", "their fields are tried here; the buildings, cameras and "
                    "cityscapes are made from the retail disc alone, the same for everyone, so they are proved by the "
                    "release builds that include them (see the untested options list)"))
    if _plan_value(plan, "modern_board_kit"):
        out.append(("Modern stadium boards", "stadium geometry only (every texture keeps its bytes)"))
    if any(_plan_value(plan, attr) for attr, _m, _l in MODELS):
        out.append(("Stadium shadows", "cast from the stadium geometry, the same for everyone"))
    if _plan_value(plan, "espn25_named_previews"):
        out.append(("Period Anniversary fields", "made from the retail fields, the same for everyone"))
    if _plan_value(plan, "season_2026"):
        out.append(("Super Bowl hosts for the franchise", "the Super Bowl fields are painted on copies of the finished "
                    "host bundles late in the build; not tried here yet"))
    if _plan_value(plan, "classic_teams") and _plan_value(plan, "historic_teams_quick_game"):
        out.append(("Classic teams' field", "the nine s48 bundles take the classic field before the colour grade and "
                    "are left out of it"))
    return out


def _owner(name: str, plan) -> tuple | None:
    """The one stadium writer of ``plan`` that rewrites bundle ``name`` (Build's order: Arrowhead, MetLife, the models,
    the practice facility), as (step id, module name or None)."""
    from . import nfl2k5_modern_arrowhead as ah
    from . import nfl2k5_modern_metlife as mt
    if _plan_value(plan, "modern_arrowhead") and name in ah.VARIANTS:
        return "arrowhead", None
    if _plan_value(plan, "modern_metlife") and name in mt.VARIANTS:
        return "metlife", None
    import importlib
    for attr, module_name, _label in MODELS:
        if _plan_value(plan, attr):
            module = importlib.import_module(f"{__package__}.{module_name}")
            if name in module.VARIANTS:
                return module_name, module_name
    if _plan_value(plan, "modern_practice_field"):
        from . import nfl2k5_practice_field_model as pf
        if name in pf.VARIANTS:
            return "practice", None
    return None


# ------------------------------------------------------------------------------------------------- the worker

def _reason(exc_or_text) -> str:
    """The reason as one plain sentence; an empty fitter list is named, never shown as nothing after a colon."""
    if isinstance(exc_or_text, BaseException):
        text = str(exc_or_text).strip()
        kind = type(exc_or_text).__name__
    else:
        text, kind = str(exc_or_text).strip(), ""
    if not text:
        text = f"{kind or 'error'} with no message"
    if text.endswith(":"):
        text += " (no candidate was recorded: every encoder candidate failed the in-place decoder check)"
    return text[:900]


def _kept_items(receipt, limit=12) -> list:
    """[(part or None, plain reason)] of the spans one step's receipt says it kept as they were: Modern colour's
    ``unfit``, and the b791 keep records (job h1: ``kept=[{site, reason, user_note}]``), or any ``user_notes``."""
    found = []

    def text_of(value):
        if isinstance(value, str):
            return None, value
        if isinstance(value, dict):
            site = value.get("site") or value.get("kind") or value.get("part")
            words = value.get("user_note") or value.get("reason") or value.get("why")
            return (str(site) if site else None), str(words or value)
        return None, str(value)

    def walk(node, depth=0):
        if depth > 6 or len(found) >= limit:
            return
        if isinstance(node, dict):
            for key in KEPT_KEYS:
                value = node.get(key)
                if not value:
                    continue
                for item in (value if isinstance(value, (list, tuple)) else [value]):
                    site, words = text_of(item)
                    found.append((site or node.get("kind") or node.get("site"), words))
            notes = node.get("user_notes")
            if isinstance(notes, (list, tuple)):
                found.extend((None, str(n)) for n in notes if n)
            for key, value in node.items():
                if key not in KEPT_KEYS and key != "user_notes" and isinstance(value, (dict, list, tuple)):
                    walk(value, depth + 1)
        elif isinstance(node, (list, tuple)):
            for value in node:
                if isinstance(value, (dict, list, tuple)):
                    walk(value, depth + 1)

    walk(receipt)
    seen, out = set(), []
    for site, words in found:
        key = (site, words[:600])
        if key not in seen:
            seen.add(key)
            out.append((site, words[:600]))
    return out[:limit]


def _kept_notes(receipt, limit=8) -> list:
    """The kept-span reasons inside one step's receipt, as plain sentences."""
    return [words for _site, words in _kept_items(receipt, limit)]


def _field_offset(bundle):
    from . import nfl2k5_modern_metlife as ml
    return ml.bundle_scenes(bundle)["field"]


def _model_field(module, job, current):
    """The stadium model's field, placed exactly as its ``_compose`` worker places it (the building stretch is
    skipped: geometry from retail bytes, the same for everyone)."""
    name, retail, settings, outer = job["name"], job["retail"], job["settings"], job["outer"]
    if job["writer"][1] == "nfl2k5_sofi_model":
        field_bytes, info = module.field_span(retail, name, dry_bundle=job.get("dry"), turf_bundle=job.get("turf"),
                                              colour_settings=settings, outer_index=outer)
    else:
        field_bytes, info = module.field_span(retail, name, team=job.get("team"), colour_settings=settings,
                                              outer_index=outer)
    chunk = _field_offset(retail)
    out = bytearray(current)
    out[chunk.offset:chunk.offset + len(field_bytes)] = field_bytes
    normal = job.get("turf_normal")
    if normal is not None:
        at, span = module.normal_span(current)
        if len(span) != len(normal) or span[4:16] != normal[4:16]:
            raise ValueError(f"{name}: the detail normal map's layout differs from the turf's")
        out[at:at + len(normal)] = normal
    return bytes(out), info


def _model_compose(module, job, current):
    """The full ``_compose`` worker of a stadium model (building, cameras and field), with the job Build builds."""
    name, retail, settings, outer = job["name"], job["retail"], job["settings"], job["outer"]
    if job["writer"][1] == "nfl2k5_sofi_model":
        _n, out, info = module._compose((name, retail, job.get("dry"), current, settings, outer, job.get("turf"),
                                         job.get("turf_normal")))
    elif job["writer"][1] == "nfl2k5_everbank_model":
        _n, out, info = module._compose((name, retail, current, settings, outer, job.get("team"), job.get("dry_model"),
                                         bool(job.get("construction", True))))
    else:
        _n, out, info = module._compose((name, retail, current, settings, outer, job.get("team"), job.get("dry_model")))
    return out, info


def chain(job) -> dict:
    """Worker: one bundle through every selected stadium writer, in Build's order. A plain picklable job dict in, a
    dict of rows and output digests out (never bundle bytes)."""
    import importlib
    from . import nfl2k5_modern_color as colour
    started, cpu = time.monotonic(), time.process_time()
    job = _load(job)
    name, retail, outer, settings = job["name"], job["retail"], job["outer"], job["settings"]
    rows, digests = [], {}

    clock = [time.process_time()]

    def record(step, status, part="bundle", reason="", **extra):
        now = time.process_time()
        rows.append(dict(bundle=name, step=step, status=status, part=part, reason=reason,
                         cpu=round(now - clock[0], 2), **extra))
        clock[0] = now

    def record_step(step, receipt, before, after, part, **extra):
        """One row for the step (refit / unchanged), plus one ``kept`` row per span its receipt says it kept."""
        kept = _kept_items(receipt)
        record(step, "refit" if after != before else "unchanged", part, "", **extra)
        for site, words in kept:
            record(step, "kept", site or part, words)

    def failed(step, exc, part="bundle"):
        record(step, "failed", part, _reason(exc), error=type(exc).__name__,
               trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-4:])[-1500:])

    current = retail
    if job["colour"]:
        try:
            graded, edits = colour.modern_bundle(retail, outer_index=outer, field_cache=job.get("refits"),
                                                 settings=settings)
            for edit in edits:
                if edit.get("unfit"):
                    record("colour", "kept", edit["kind"], _reason(edit["unfit"]))
                elif edit["kind"] != "tint":
                    record("colour", "refit" if edit.get("refit") else "unchanged", edit["kind"])
            current = graded
            digests["colour"] = sha(current)
        except Exception as exc:  # noqa: BLE001 - every failure is a finding, never a crash of the check
            failed("colour", exc)
    writer = job.get("writer")
    if writer is not None:
        step = writer[0]
        before = current
        try:
            if step == "arrowhead":
                from . import nfl2k5_modern_arrowhead as ah
                if job["colour"]:
                    current, receipt = ah.combined_bundle(retail, current, outer_index=outer, settings=settings)
                else:
                    current, receipt = ah.modern_bundle(retail)
            elif step == "metlife":
                from . import nfl2k5_modern_metlife as mt
                if job["colour"]:
                    current, receipt = mt.combined_bundle(retail, current, name, job["dry_retail"], outer_index=outer,
                                                          settings=settings)
                else:
                    current, receipt = mt.modern_bundle(retail, name, job["dry_retail"])
            elif step == "practice":
                from . import nfl2k5_practice_field_model as pf
                _n, current, receipt = pf._compose((name, retail, current, settings, bool(job.get("team_logo")), outer,
                                                    job.get("shield")))
            else:
                module = importlib.import_module(f"{__package__}.{writer[1]}")
                current, receipt = (_model_compose if job.get("stadium_models") else _model_field)(module, job, current)
            if len(current) != len(before):
                raise ValueError(f"{name}: the bundle changed size ({len(before)} to {len(current)} bytes)")
            record_step(step, receipt, before, current, "field")
            digests[step] = sha(current)
        except Exception as exc:  # noqa: BLE001
            failed(step, exc, "field")
            current = before
    if job.get("surfaces"):
        from . import nfl2k5_modern_surfaces as ms
        before = current
        try:
            _n, current, receipt = ms._job((name, current, job["indoor"], settings, None))
            parts = sorted({edit["kind"] for edit in receipt.get("edits", ())})
            record_step("surfaces", receipt, before, current, "+".join(parts) or "bundle", normal=receipt.get("normal"),
                        palette_cap=(receipt.get("field") or {}).get("palette_cap"))
            digests["surfaces"] = sha(current)
        except Exception as exc:  # noqa: BLE001
            failed("surfaces", exc)
            current = before
    if job.get("greens") is not None:
        from . import nfl2k5_broadcast_greens as gr
        before = current
        try:
            _n, current, receipt = gr._bundle_job((name, job["greens"], current))
            parts = sorted({str(edit.get("scene")) for edit in receipt.get("edits", ())})
            record_step("greens", receipt, before, current, "+".join(parts) or "bundle")
            digests["greens"] = sha(current)
        except Exception as exc:  # noqa: BLE001
            failed("greens", exc)
            current = before
    return dict(name=name, rows=rows, digests=digests, seconds=round(time.monotonic() - started, 2),
                cpu_seconds=round(time.process_time() - cpu, 2))


def _load(job):
    """The job with its bundles: a worker reads its own bundle and the retail ones its writer needs from the disc
    (``job["reads"]``: {job key: outer index}), so the main process never holds 477 bundles at once."""
    reads = job.get("reads")
    if not reads:
        return job
    from . import nfl2k5_modern_color as colour
    job = dict(job)
    with colour._outer_image()(str(job["source"])) as archive:
        for key, outer in reads.items():
            entry = archive.entries[outer]
            job[key] = archive.read(entry.virtual_offset, entry.size)
    if sha(job["retail"]) != job["retail_sha256"]:
        raise ValueError(f"{job['name']}: the disc changed while it was being checked")
    return job


def _run_chain(job):
    """Pool entry point: the official marks pack follows the job into fork, forkserver and spawn workers."""
    from . import nfl2k5_official_marks as official
    return official.run_with_pack(chain, job, job.get("marks_root"))


# ------------------------------------------------------------------------------------------------- the main run

def _greens_families(archive, plan):
    """Broadcast greens' surface family per venue prefix, as Build will see the roster when greens runs (SoFi's
    stadium rows are written before it)."""
    from types import SimpleNamespace
    from . import nfl2k5_broadcast_greens as gr
    from . import nfl2k5_modern_surfaces as ms
    entry = archive.entries[ms.ROST_OUTER_INDEX]
    rost = archive.read(entry.virtual_offset, entry.size)
    if _plan_value(plan, "modern_sofi"):
        from . import nfl2k5_sofi_venue as sv
        try:
            rost = sv.rost_sofi(rost)[0]
        except (ValueError, KeyError):
            pass

    class _Rost:
        entries = {ms.ROST_OUTER_INDEX: SimpleNamespace(virtual_offset=0, size=len(rost))}

        @staticmethod
        def read(offset, size):
            return rost[offset:offset + size]

    return gr.families(_Rost())


def venue_names(archive) -> dict:
    """{prefix: plain venue name} (the 2026 home venues by their current names, the rest by the retail roster)."""
    from . import nfl2k5_modern_metlife as ml
    from . import nfl2k5_modern_surfaces as ms
    out = {}
    try:
        entry = archive.entries[ms.ROST_OUTER_INDEX]
        body = archive.read(entry.virtual_offset, entry.size)[32:]
        for _at, fields in ml._stadium_records(body):
            prefix = fields["asset_code"][1]
            out.setdefault(prefix, fields["name"][1].strip())
    except (ValueError, KeyError, IndexError):
        pass
    for prefix, row in ms.venues().items():
        out[prefix] = f"{row.get('venue') or out.get(prefix, prefix)} ({row.get('team', '')})".replace(" ()", "")
    return out


def run(plan, source, *, progress: Callable | None = None, workers: int | None = None, stadium_models: bool = False,
        use_cache: bool = True, names=None) -> DryRun:
    """Try every stadium refit ``plan`` selects on the retail bundles of ``source`` (only read). ``names`` limits the
    run to some bundles (tests). ``workers``: process count (default: the cores less one, at most 8)."""
    import importlib
    import sys
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_modern_surfaces as ms
    from . import nfl2k5_official_marks as official
    say = progress or (lambda *_: None)
    started = time.monotonic()
    result = DryRun(steps=selected_steps(plan), not_covered=not_covered(plan, stadium_models=stadium_models),
                    platform=f"{sys.platform}, Python {sys.version.split()[0]}")
    if not result.steps:
        return result
    settings = colour.normalize_settings(_plan_value(plan, "modern_color_settings", None)) \
        if _plan_value(plan, "modern_color") else None
    marks_root = official.selected_root(_plan_value(plan, "official_marks_pack", "") or None) or None
    excluded = set()
    if _plan_value(plan, "classic_teams") and _plan_value(plan, "historic_teams_quick_game"):
        from . import nfl2k5_classic_field as classic_field
        excluded = set(classic_field.BUNDLES)
    pins = {pin["name"]: pin for pin in colour._pins()["bundles"]}
    home = set(ms.HOME_BUNDLES)
    wanted = sorted(set(pins) - excluded) if names is None else sorted(set(names) & (set(pins) - excluded))
    say("Stadium dry run: reading the stadium bundles of your disc", 0, 0)
    present, owners, spans, extra_outer, bundle_spans = {}, {}, {}, {}, {}
    turf_bundle = None
    with colour._outer_image()(str(source)) as archive:
        indoor = ms.indoor_flags(archive)
        families = _greens_families(archive, plan) if "greens" in result.steps else {}
        names_by_prefix = venue_names(archive)
        for name in wanted:
            pin = pins[name]
            entry = archive.entries[pin["outer"]]
            data = archive.read(entry.virtual_offset, entry.size)
            if sha(data) != pin["retail_sha256"]:
                result.skipped_bundles[name] = "not the retail bundle on this disc (an earlier mod or edit changed it)"
                continue
            present[name] = pin["outer"]
            owners[name] = _owner(name, plan)
            if settings is not None:
                for kind, at, size in colour.bundle_plan(data):
                    if kind in ("field", "normal", "divots"):
                        span = data[at:at + size]
                        spans.setdefault((kind, sha(span)), (kind, pin["outer"], span))
                        bundle_spans.setdefault(name, []).append((kind, sha(span)))
        # the retail bundles a writer reads besides the bundle itself (dry variants, SoFi's turf source)
        for name, owner in owners.items():
            if owner is None:
                continue
            step, module_name = owner
            needed = []
            if step == "metlife":
                from . import nfl2k5_modern_metlife as mt
                needed.append(mt.dry_name(name))
            elif module_name is not None:
                module = importlib.import_module(f"{__package__}.{module_name}")
                needed.append(module.dry_of(name))
                if module_name == "nfl2k5_sofi_model":
                    needed.append(module.TURF_SOURCE)
            for other in needed:
                if other in pins:
                    extra_outer[other] = pins[other]["outer"]
        sofi_turf = None
        if any(o and o[1] == "nfl2k5_sofi_model" for o in owners.values()):
            from . import nfl2k5_sofi_model as sofi_module
            sofi_turf = sofi_module.TURF_SOURCE
            entry = archive.entries[pins[sofi_turf]["outer"]]
            turf_bundle = archive.read(entry.virtual_offset, entry.size)
    for name in sorted(excluded & set(pins)):
        if names is None or name in names:
            result.skipped_bundles[name] = "the classic teams' field goes here before the colour grade, which leaves it out"
    todo = [n for n in wanted if n in present]
    result.bundles = len(todo)
    count = max(1, workers or min(8, max(1, (os.cpu_count() or 2) - 1)))
    result.workers = count
    refits = {}
    if settings is not None and spans:
        say(f"Stadium dry run: Modern colour refits ({len(spans)} distinct fields, bump maps and divot layers)", 0,
            len(spans))
        previous = os.environ.get("NFL2K5_DISABLE_MODERN_COLOR_CACHE")
        try:
            if not use_cache:
                os.environ["NFL2K5_DISABLE_MODERN_COLOR_CACHE"] = "1"
            refits = colour._refit_fields(spans, progress=say, workers=count, settings=settings)
        finally:
            if not use_cache:
                if previous is None:
                    os.environ.pop("NFL2K5_DISABLE_MODERN_COLOR_CACHE", None)
                else:
                    os.environ["NFL2K5_DISABLE_MODERN_COLOR_CACHE"] = previous
        result.cached_colour_refits = int(getattr(colour._refit_fields, "last_hits", 0) or 0)
    sid = colour.settings_id(settings) if settings is not None else None
    spans = None
    turf_normal = None
    if turf_bundle is not None:
        from . import nfl2k5_sofi_model as sofi_module
        turf_normal = _graded_normal(sofi_module, turf_bundle, pins[sofi_turf]["outer"], settings, refits, sid)
        turf_bundle = None
    jobs = []
    for name in todo:
        outer = pins[name]["outer"]
        owner = owners.get(name)
        job = dict(name=name, source=str(source), outer=outer, retail_sha256=pins[name]["retail_sha256"],
                   reads={"retail": outer}, settings=settings, colour=settings is not None, writer=owner,
                   marks_root=marks_root, stadium_models=stadium_models,
                   surfaces="surfaces" in result.steps and name in home, indoor=indoor.get(name[:3], False),
                   greens=families.get(name[:3]) if "greens" in result.steps else None)
        if settings is not None:
            job["refits"] = {(sid, kind, span_sha): refits[(sid, kind, span_sha)]
                             for kind, span_sha in bundle_spans.get(name, ()) if (sid, kind, span_sha) in refits}
        if owner is not None:
            step, module_name = owner
            art_root = _plan_value(plan, "modern_venues_2026", "") or None
            if step == "metlife":
                from . import nfl2k5_modern_metlife as mt
                job["reads"]["dry_retail"] = extra_outer[mt.dry_name(name)]
            elif step == "practice":
                from . import nfl2k5_practice_field_model as pf
                job["team_logo"] = bool(_plan_value(plan, "modern_practice_field_team_logo"))
                job["shield"] = pf.league_shield(art_root) if art_root else None
            elif module_name is not None:
                module = importlib.import_module(f"{__package__}.{module_name}")
                if module_name == "nfl2k5_sofi_model":
                    if name[4] != "d":
                        job["reads"]["dry"] = extra_outer[f"{name[:4]}d.iff"]
                    if name[:3] != module.TURF_SOURCE[:3]:
                        job["reads"]["turf"] = extra_outer[module.TURF_SOURCE]
                        job["turf_normal"] = turf_normal
                else:
                    job["team"] = (module.team_field_art(art_root) or None) if art_root else None
                    job["reads"]["dry_model"] = extra_outer[module.dry_of(name)]
                    if module_name == "nfl2k5_everbank_model":
                        job["construction"] = bool(_plan_value(plan, "modern_everbank_construction", True))
        jobs.append(job)
    # the slow ones first (stadium model fields, then Arrowhead, MetLife and the practice field), so the pool's last
    # minutes are not one long job
    jobs.sort(key=lambda j: (0 if j["writer"] and j["writer"][1] else 1 if j["writer"] else 2, j["name"]))
    say(f"Stadium dry run: {len(jobs)} stadium bundles on {count} worker{'s' if count != 1 else ''}", 0, len(jobs))
    done = 0
    if count == 1 or len(jobs) < 2:
        for job in jobs:
            out = _run_chain(job)
            result.rows.extend(out["rows"])
            result.cpu_seconds += out.get("cpu_seconds", 0.0)
            result.digests[out["name"]] = out.get("digests", {})
            done += 1
            say(f"Stadium dry run: {out['name']} ({done} of {len(jobs)})", done, len(jobs))
    else:
        pool = ProcessPoolExecutor(max_workers=count)
        try:
            futures = [pool.submit(_run_chain, job) for job in jobs]
            for future in as_completed(futures):
                out = future.result()
                result.rows.extend(out["rows"])
                result.cpu_seconds += out.get("cpu_seconds", 0.0)
                result.digests[out["name"]] = out.get("digests", {})
                done += 1
                say(f"Stadium dry run: {out['name']} ({done} of {len(jobs)})", done, len(jobs))
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)
    for row in result.rows:
        row["venue"] = names_by_prefix.get(row["bundle"][:3], row["bundle"][:3])
        row["label"] = STEP_LABELS.get(row["step"], row["step"])
    result.rows.sort(key=lambda r: (r["bundle"], list(STEP_LABELS).index(r["step"]) if r["step"] in STEP_LABELS else 99))
    result.seconds = time.monotonic() - started
    return result


def _graded_normal(module, bundle, outer, settings, refits, sid):
    """SoFi's turf normal loan: the detail normal map of the turf source bundle as Modern colour leaves it."""
    from . import nfl2k5_modern_color as colour
    if settings is not None:
        cache = {key: value for key, value in refits.items() if key[0] == sid}
        bundle, _edits = colour.modern_bundle(bundle, outer_index=outer, field_cache=cache, settings=settings)
    return module.normal_span(bundle)[1]


# ------------------------------------------------------------------------------------------------- plain words

def describe(row) -> str:
    """One plain sentence for a kept or failed row."""
    where = f"{row.get('venue', row['bundle'][:3])} ({row['bundle']}, {bundle_words(row['bundle'])})"
    part = {"field": "field", "normal": "bump map (detail normal)", "divots": "divot layer"}.get(row["part"], row["part"])
    label = row.get("label") or STEP_LABELS.get(row["step"], row["step"])
    if row["status"] == "kept":
        return f"{label}: {where} keeps its {part} as it was: {row['reason'] or 'no room in its fixed slot'}"
    return f"{label}: {where}: the {part} refit fails: {row['reason']}"
