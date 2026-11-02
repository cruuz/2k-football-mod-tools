"""Check my project: what a long build will refuse or change, found in minutes (b779-ce1, Coach Edwards' report).

A project with thousands of texture replacements builds for 3 to 6 hours, and the built-in features that dress the
disc afterwards (Anniversary moment kits, the 2026 kit repairs, the classic teams' kits) used to discover only at the
end that a replaced kit was unusable. They now fall back on their own (``nfl2k5_moment_kits``), and this module says
beforehand, in plain words, what Build will do with the user's replacements and what, if anything, must be changed or
unticked first:

* ``stop``: Build would refuse. The finding says what to untick or change.
* ``note``: Build goes on; it says what happens to a named piece of the user's work. Nothing to untick.

``check`` runs the checks the long build already runs first (option conflicts, the artwork recipe, equipment that needs
a refit, the source-disc preflights of ``mod_build.preflight_plan``) plus a read-only map of which of the user's edited
kit packages the built-in kit features read. Build runs it itself before the long work (``build_with_project``).

``doctor`` (b791 h4, "Check my project" v2, the whole dive on a project after Coach Edwards' 11/01 build stopped five
hours in on a stadium texture) runs everything ``check`` does and then tries the long build's risky steps on the
project's own options and bytes, in minutes: every stadium, colour, surface and practice-field refit with the
project's Modern colour values (``nfl2k5_stadium_dry_run``), the Anniversary and classic kits on the project's own
donors, the options and settings no release build ever tried, and an inventory of the project against every known
limit. Its report is plain text, JSON and a short summary (``DoctorReport.write``); the Build tab shows the summary and
saves the rest. It never writes a disc and never changes the project.

Command line (no Studio window; the archive is only read)::

    python3 -m mod_editor.core.nfl2k5_project_check PROJECT.2k5mod --source "ESPN NFL 2K5 (USA).xiso.iso"
        [--report OUT_DIR] [--json [OUT.json]] [--quick] [--workers N] [--stadium-models]
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = "nfl2k5_project_check/v1"
DOCTOR_SCHEMA = "nfl2k5_project_doctor/v1"
STOP = "stop"
NOTE = "note"
MAX_LISTED = 12


@dataclass
class Finding:
    severity: str          # "stop" or "note"
    area: str              # the part of Build it concerns
    title: str             # one sentence
    detail: str = ""       # what was found, by name
    fix: str = ""          # what to change or untick (stop findings always have one)
    code: str = ""         # a stable id for the JSON report (doctor findings)


@dataclass
class Report:
    findings: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    seconds: float = 0.0

    @property
    def stops(self):
        return [f for f in self.findings if f.severity == STOP]

    @property
    def notes(self):
        return [f for f in self.findings if f.severity == NOTE]

    @property
    def ok(self) -> bool:
        return not self.stops

    def as_dict(self) -> dict:
        return dict(schema=SCHEMA, ok=self.ok, seconds=round(self.seconds, 1), steps=list(self.steps),
                    findings=[asdict(f) for f in self.findings])

    def text(self) -> str:
        """The plain report shown in the Build tab and printed by the command line."""
        lines = []
        if self.ok:
            lines.append("Your project passed the check: nothing has to be changed or unticked before Build.")
        else:
            lines.append(f"Change or untick {len(self.stops)} thing{'s' if len(self.stops) != 1 else ''} before "
                         "Build, or it will stop partway through:")
        for number, finding in enumerate(self.stops, 1):
            lines.append("")
            lines.append(f"{number}. {finding.title}")
            if finding.detail:
                lines.append(f"   {finding.detail}")
            lines.append(f"   What to do: {finding.fix}")
        if self.notes:
            lines.append("")
            lines.append("What Build will do with your work (no action needed):")
            for finding in self.notes:
                lines.append(f"- {finding.title}")
                if finding.detail:
                    lines.append(f"  {finding.detail}")
        lines.append("")
        lines.append("Checked: " + "; ".join(self.steps) + f". ({self.seconds:.0f} s, nothing was written.)")
        return "\n".join(lines)


def _step(report: Report, name: str, started: float) -> None:
    report.steps.append(name)


def _named(items: Iterable[str], limit: int = MAX_LISTED) -> str:
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


# ------------------------------------------------------------------------------------------ the edited kit packages

_TSET = re.compile(r"^tset:(\d+):(\d+):(\d+):([A-Za-z0-9_]+)$", re.ASCII)
_UNIFORM = re.compile(r"^nfl2k5\.uniform\.([0-9]{2}[ha](?:[0-9]|[1-9][0-9]))\.", re.ASCII)


def edited_kit_chunks(asset_ids: Iterable[str]) -> tuple[dict, set]:
    """({(selector, chunk): [asset ids]} for sock, glove and shoe replacements, {selector} of every kit package with
    any replacement). Selectors are upper case, like the kit files (``14H8``)."""
    from .nfl2k5_uniform_equipment_writer import load_targets
    targets, _physical = load_targets()
    chunks: dict = {}
    packages: set = set()
    for asset_id in asset_ids:
        match = _TSET.match(asset_id)
        if match:
            target = targets.get(asset_id)
            if target is not None:
                chunks.setdefault((target.set_selector.upper(), target.chunk_index), []).append(asset_id)
                packages.add(target.set_selector.upper())
            continue
        match = _UNIFORM.match(asset_id)
        if match:
            packages.add(match.group(1).upper())
    return chunks, packages


def _side_sources(side: dict) -> dict:
    """{chunk index: donor selector} of one composed kit side (chunk 0 and the unlisted chunks come from its base)."""
    from . import nfl2k5_moment_kits as kits
    sources = {index: side["base"] for index in range(53)}
    sources.update(kits._expand(side.get("chunks", {})))
    return sources


def moment_kit_notes(documents: Iterable[tuple[str, dict]], chunks: dict) -> list:
    """One note per new Anniversary / classic kit that reads a donor chunk the user replaced."""
    notes = []
    for feature, doc in documents:
        for kit in doc["kits"]:
            hit = {}
            for letter, side in sorted(kit["sides"].items()):
                for index, selector in _side_sources(side).items():
                    ids = chunks.get((selector, index))
                    if ids:
                        hit.setdefault(selector, set()).add(index)
            if not hit:
                continue
            from . import nfl2k5_moment_kits as kits
            where = "; ".join(
                f"{selector} chunk{'s' if len(c) > 1 else ''} {', '.join(str(i) for i in sorted(c))} "
                f"({kits._chunk_words(sorted(c))})" for selector, c in sorted(hit.items()))
            notes.append(Finding(
                NOTE, feature,
                f"The new {kit.get('team', kit['code'])} kit {kit['id']} is built from kits you edited.",
                f"It reads {where}. If your version cannot be used in the new kit (it needs more video memory than any "
                "game kit, or a sock whose clean and mud copies no longer share their image), Build uses the retail piece "
                "in the new kit only and names it in the build log. Your own kits keep your artwork either way.",
                ""))
    return notes


def historic_kit_note(plan, packages: set) -> list:
    """The historic teams' retail Eagles look needs one Eagles set (they use all 15); era set 9 unless it is edited."""
    if not getattr(plan, "espn25_more_moments", False):
        return []
    from . import nfl2k5_historic_styles as styles
    edited = sorted(f"{styles.EAGLES}{side}{styles.EAGLES_SPARE}" for side in "HA"
                    if f"{styles.EAGLES}{side}{styles.EAGLES_SPARE}" in packages)
    if not edited:
        return []
    both = " and ".join(edited)
    return [Finding(NOTE, "Historic teams",
                    f"Your edits to the Eagles' set {styles.EAGLES_SPARE} ({both}) are kept.",
                    "The Eagles use all 15 uniform sets, and the historic Eagles teams need one for their retail look "
                    f"(usually set {styles.EAGLES_SPARE}). Because you edited it, Build puts that look on another Eagles set "
                    "nobody edited or wears and names it in the build log; if there is none, it leaves that look out. "
                    "Nothing of yours is replaced.")]


def kit_fix_note(packages: set) -> list:
    """One note: how many of the user's edited kits the 2026 kit repairs would otherwise rewrite."""
    from . import nfl2k5_kit_fixes_2026 as fixes
    repaired = set()
    for document in (fixes.spec(), fixes.alternates(), fixes.finish(), fixes.seattle(), fixes.overlaps(),
                     fixes.chiefs(), fixes.swooshes(), fixes.nameplates()):
        repaired |= {s.upper() for s in fixes.selectors(document)}
    both = sorted(packages & repaired)
    if not both:
        return []
    return [Finding(NOTE, "2026 kit repairs",
                    f"{len(both)} of your edited kit packages are also on the built-in 2026 repair list.",
                    "The repairs only change a texture that is still the retail one, so a texture you replaced keeps "
                    "your artwork. Kits: " + _named(both) + ".")]


def _feature_documents(plan) -> list:
    documents = []
    if getattr(plan, "espn25_more_moments", False):
        from . import nfl2k5_moment_kits as kits
        documents.append(("Anniversary moment kits", kits.document()))
    if getattr(plan, "classic_teams", False) and getattr(plan, "historic_teams_quick_game", False):
        from . import nfl2k5_classic_teams as classic
        documents.append(("Classic teams' kits", classic.authored_kits()))
    return documents


def donors_with_edits(documents, chunks: dict, asset_paths: dict, index, retail, progress=None) -> dict:
    """{selector: kit package bytes} of every donor the kit features read: the retail package with the user's sock,
    glove and shoe replacements compiled in by the same writer Build uses (read-only; the compile result is the same
    fixed TSET span Build would write). Uniform-art replacements are not modelled here: they never change a kit's
    allocation or its clean/mud pairing."""
    from nfl_txtr import parse_chunks
    from . import nfl2k5_moment_kits as kits
    from .nfl2k5_uniform_equipment_writer import build_unified_uniform_equipment_imports, load_targets
    retail_packages = kits.RetailPackages(retail)
    donors = {}
    for _feature, doc in documents:
        for selector in kits.donors(doc):
            # a historic spare style does not exist on the retail disc: Build makes it from the retail style-0 kit
            donors[selector] = bytes(retail_packages[selector if selector in retail_packages else selector[:3] + "0"])
    targets, _physical = load_targets()
    todo = sorted((key, ids) for key, ids in chunks.items() if key[0] in donors)
    for number, ((selector, chunk_index), ids) in enumerate(todo, 1):
        if progress:
            progress(f"Compiling your edited {selector} chunk {chunk_index} for the kit check", number, len(todo))
        paths = [(asset_id, asset_paths[asset_id]) for asset_id in ids if asset_id in asset_paths]
        if not paths:
            continue
        compiled = build_unified_uniform_equipment_imports(Path(index), paths, preflight_only=True)
        package = bytearray(donors[selector])
        chunk = next(c for c in parse_chunks(bytes(package), allow_trailing=True) if c.index == chunk_index)
        if len(compiled.rebuilt_span) != chunk.end_offset - chunk.offset:
            raise ValueError(f"{selector} chunk {chunk_index}: the compiled span changed size")
        package[chunk.offset:chunk.end_offset] = compiled.rebuilt_span
        donors[selector] = bytes(package)
    return donors


def kit_dry_run(plan, chunks: dict, asset_paths: dict, index, retail, progress=None) -> list:
    """Compose the new Anniversary / classic kits from the user's edited donors exactly as Build will (retail chunks
    where an edited one cannot be used), and report each swap and each left-out kit by name.

    The donors here are the retail kits plus the user's equipment, not the disc as Build will have it after the
    2026 kit repairs. A new kit whose art rows already fail on the plain retail donors depends on those repairs,
    so it is not judged here (it is checked when Build composes it) and is said to be unchecked, never blamed."""
    from . import nfl2k5_moment_kits as kits
    documents = _feature_documents(plan)
    if not documents or not chunks:
        return []
    donors = donors_with_edits(documents, chunks, asset_paths, index, retail, progress)
    plain = donors_with_edits(documents, {}, {}, index, retail)
    retail_packages = kits.RetailPackages(retail)
    findings, unchecked = [], []
    for feature, doc in documents:
        receipt, baseline = compose_receipt(doc, donors, retail_packages), compose_receipt(doc, plain, retail_packages)
        skipped = dict(receipt["skipped_kits"])
        for kit_id in sorted(baseline["skipped_kits"]):
            unchecked.append(kit_id)
            skipped.pop(kit_id, None)
        mine = lambda rows: [row for row in rows if row["side"].split(" ", 1)[0] not in baseline["skipped_kits"]]  # noqa: E731
        receipt = dict(receipt, substitutions=mine(receipt["substitutions"]), skipped_kits=skipped,
                       unchanged_art=mine(receipt.get("unchanged_art", ())),
                       dropped_defaults=[d for d in receipt.get("dropped_defaults", ()) if d.get("kit") in skipped])
        for note in kits.user_notes(receipt, feature):
            findings.append(Finding(NOTE, feature, note.removeprefix(feature + ": "), code="kits.dry_run"))
    if unchecked:
        findings.append(Finding(NOTE, "Kit check",
                                f"{len(unchecked)} new kit{'s' if len(unchecked) != 1 else ''} cannot be tried before "
                                "Build: " + _named(unchecked) + ".",
                                "They are built from kits that the 2026 repairs change first, so Build checks them "
                                "when it composes them and names any swap in its log."))
    return findings


def compose_receipt(doc, packages, retail_packages) -> dict:
    """What the kit stage would do with these donors: {substitutions, skipped_kits, unchanged_art, dropped_defaults}.
    Uses the stage's own ``dry_run`` (b791 h2: art steps with nothing to change, defaults that go with a left-out kit)
    when this Studio has it, else its ``compose`` (swaps and left-out kits only)."""
    from . import nfl2k5_moment_kits as kits
    if callable(getattr(kits, "dry_run", None)):
        receipt = kits.dry_run(doc, packages, retail_packages)
        return dict(substitutions=list(receipt.get("substitutions", ())), skipped_kits=dict(receipt.get("skipped_kits", {})),
                    unchanged_art=list(receipt.get("unchanged_art", ())),
                    dropped_defaults=list(receipt.get("dropped_defaults", ())))
    report, skipped = [], {}
    kits.compose(doc, packages, retail_packages, report, skipped)
    return dict(substitutions=report, skipped_kits=skipped, unchanged_art=[], dropped_defaults=[])


# ------------------------------------------------------------------------------------------------- the whole check

def check(plan, *, asset_ids: Iterable[str] = (), document: dict | None = None, fit_rows: Iterable[dict] = (),
          progress: Callable[..., None] | None = None, run_preflight: bool = True,
          asset_paths: dict | None = None, source_index=None) -> Report:
    """Run every quick check for ``plan`` and the project's replacements; never writes anything.

    ``asset_ids``: the replaced asset ids of the project. ``document``: its artwork recipe (``{"edits": [{"kind",
    "target"...}]}``) for the option-conflict check. ``fit_rows``: the equipment fit receipts the project carries.
    ``run_preflight``: also run the source-disc preflights Build runs first (a few minutes on a full option set).
    ``asset_paths`` ({asset id: replacement PNG}) and ``source_index`` (the Studio source cache's pack 0): also
    compile the user's edited sock, glove and shoe chunks of the kit features' donors and compose the new kits from
    them, exactly as Build will (a minute or two), so each swap and each left-out kit is named before Build starts."""
    from . import mod_build
    started = time.monotonic()
    report = Report()
    say = progress or (lambda *_: None)
    asset_ids = list(asset_ids)

    say("Checking the chosen Build options", 0, 0)
    for blocker in mod_build.validate_plan(plan):
        report.findings.append(Finding(STOP, "Build options", blocker, "",
                                       "Untick or change the option this names on the Build tab."))
    _step(report, "Build options", started)

    if document is not None:
        say("Checking the artwork recipe against the options", 0, 0)
        try:
            mod_build.preflight_project_options(plan, document)
        except ValueError as exc:
            message = str(exc)
            head, _, rest = message.partition(". ")
            report.findings.append(Finding(STOP, "Stadium boards", head + ".", "", rest or
                                           "Untick Modern stadium boards or remove those stadium edits."))
        _step(report, "artwork recipe", started)

    refits = [r for r in fit_rows if r.get("fit_status") == "needs refit"]
    if refits:
        names = [str(r.get("asset_id")) for r in refits]
        report.findings.append(Finding(
            NOTE, "Equipment", f"{len(refits)} sock, glove or shoe replacement{'s' if len(refits) != 1 else ''} "
            "do not fit their slot as drawn.",
            _named(names) + ". Make my disc refits them itself (fewer colours, then a smaller image) and lists what it "
            "changed; to choose the trade-off yourself, press Refit equipment first or simplify the artwork."))
    _step(report, "equipment fit receipts", started)

    say("Mapping your edited kits to the built-in kit features", 0, 0)
    chunks, packages = edited_kit_chunks(asset_ids)
    documents = _feature_documents(plan)
    if asset_paths and source_index is not None and plan.source and documents and chunks:
        try:
            report.findings.extend(kit_dry_run(plan, chunks, asset_paths, source_index, plan.source, progress))
            _step(report, "new kits composed from your edited kits", started)
        except (ValueError, OSError) as exc:
            report.findings.append(Finding(NOTE, "Kit check", "The new kits could not be tried on your edited kits.",
                                           str(exc)[:600]))
            report.findings.extend(moment_kit_notes(documents, chunks))
    else:
        report.findings.extend(moment_kit_notes(documents, chunks))
    report.findings.extend(historic_kit_note(plan, packages))
    report.findings.extend(kit_fix_note(packages))
    _step(report, "kit features", started)

    if run_preflight and plan.source:
        say("Checking the disc and the options against it (several minutes)", 0, 0)
        try:
            mod_build.preflight_plan(plan, progress)
        except ValueError as exc:
            report.findings.append(Finding(STOP, "Disc and options", str(exc).strip().splitlines()[0][:400],
                                           str(exc).strip()[:1200],
                                           "Follow the sentence above: it names the option or the file."))
        _step(report, "disc and option preflights", started)
    report.seconds = time.monotonic() - started
    return report


def assets_from_session(session) -> list:
    """The replaced asset ids of an open Studio session."""
    return [edit.asset_id for edit in session.iter_project_png_edits()]


def paths_from_session(session) -> dict:
    """{asset id: staged replacement PNG} of an open Studio session."""
    return {edit.asset_id: Path(edit.replacement_path) for edit in session.iter_project_png_edits()}


# ------------------------------------------------------------------------------------------------- a .2k5mod on disk

def read_archive(path) -> dict:
    """{"asset_ids", "document", "fit_rows", "settings"} of a project archive; the file is only read."""
    import zipfile
    from mod_editor.studio.project_archive import read_project_manifest
    with zipfile.ZipFile(path) as archive:
        manifest, _notes = read_project_manifest(archive)
    edits = manifest.get("edits", [])
    document = {"edits": [dict(kind=("stadium_texture" if str(e["asset_id"]).startswith("nfl2k5.stadium.") else "texture"),
                               target=str(e["asset_id"])) for e in edits]}
    rows = [row for group in (manifest.get("fit_receipts") or {}).values() for row in group]
    return dict(asset_ids=[e["asset_id"] for e in edits], document=document, fit_rows=rows,
                settings=manifest.get("build_settings") or {},
                members={e["asset_id"]: e.get("file") for e in edits if e.get("file")})


def extract_assets(path, members: dict, wanted: Iterable[str], folder) -> dict:
    """Copy the named replacement PNGs of an archive into ``folder`` (a private temporary folder) and return
    {asset id: path}. Archive member names are never used as paths."""
    import zipfile
    out = {}
    with zipfile.ZipFile(path) as archive:
        for number, asset_id in enumerate(sorted(set(wanted))):
            member = members.get(asset_id)
            if member is None:
                continue
            target = Path(folder) / f"{number:05d}.png"
            target.write_bytes(archive.read(member))
            out[asset_id] = target
    return out


# ===================================================================================== the project doctor (b791 h4)
#
# Noah, 2026-11-02: "really make it foolproof. So if he does get another error the next time we do it, we'll know
# exactly why, and it'll end up doing a whole dive on his file". ``doctor`` is that dive.

DOCTOR_CHECKS = ("options", "preflight", "kits", "stadiums", "untested", "inventory")
QUICK_CHECKS = ("options", "kits", "untested", "inventory")
MAX_TEXT_ROWS = 40

#: the dry run's step ids -> the receipt step name Build gives the same writer (``mod_build._build``)
BUILD_STEP_NAMES = {
    "colour": "modern_color_bundles", "arrowhead": "modern_arrowhead", "metlife": "modern_metlife",
    "practice": "modern_practice_field", "surfaces": "modern_surfaces", "greens": "broadcast_greens",
    "nfl2k5_sofi_model": "modern_sofi", "nfl2k5_highmark_model": "modern_highmark", "nfl2k5_att_model": "modern_att",
    "nfl2k5_levis_model": "modern_levis", "nfl2k5_allegiant_model": "modern_allegiant",
    "nfl2k5_mercedes_benz_model": "modern_mercedes_benz", "nfl2k5_usbank_model": "modern_usbank",
    "nfl2k5_lucas_oil_model": "modern_lucas_oil", "nfl2k5_state_farm_model": "modern_state_farm",
    "nfl2k5_hard_rock_model": "modern_hard_rock", "nfl2k5_gillette_model": "modern_gillette",
    "nfl2k5_lambeau_model": "modern_lambeau", "nfl2k5_everbank_model": "modern_everbank",
}

#: plain names of the options the doctor talks about most (the Build tab's own words); anything else is spelled
#: from its key, or from the stadium module's BUILD_CAPTION
OPTION_LABELS = {
    "modern_color": "Modern colour and lighting", "modern_color_settings": "Modern colour values",
    "modern_arrowhead": "Modern Arrowhead", "modern_metlife": "Modern MetLife Stadium",
    "modern_metlife_model": "Modern MetLife model", "modern_venues_2026": "2026 venue art folder",
    "modern_board_kit": "Modern stadium boards", "modern_practice_field": "Modern practice facility",
    "modern_practice_field_team_logo": "Team logo at the practice field's midfield",
    "modern_surfaces": "Modern playing surfaces", "modern_everbank_construction": "EverBank 2026 construction",
    "espn25_more_moments": "25 more Anniversary moments", "espn25_named_previews": "Named Anniversary previews",
    "classic_teams": "Classic teams", "historic_teams_quick_game": "Historic teams in Quick Game",
    "season_2026": "2026 season", "official_marks_pack": "Official marks pack",
    "custom_intro": "Custom intro video", "playbook_packs": "Playbook packs", "roster_edits": "Roster edits",
    "weather_plan": "Stadium climate edits", "hires_pack": "High-resolution pack",
}

#: option pairs that share a code path in Build (one writer composes the other's bytes); each is listed when the two
#: values are each built by some release build but never together
INTERACTING_PAIRS = (
    ("modern_arrowhead", "modern_color", "Modern Arrowhead composes its field with the colour grade"),
    ("modern_metlife", "modern_color", "Modern MetLife composes its field with the colour grade"),
    ("modern_arrowhead", "modern_board_kit", "the stadium boards leave Kansas City to Modern Arrowhead"),
    ("modern_lambeau", "modern_surfaces", "Lambeau's field is surfaced after the model"),
    ("modern_lambeau", "modern_color", "Lambeau's field is composed with the colour grade"),
    ("espn25_more_moments", "classic_teams", "the moment kits and the classic teams' kit share one stage"),
    ("modern_practice_field_team_logo", "modern_venues_2026", "the practice field's midfield art"),
)


@dataclass
class Section:
    key: str
    title: str
    status: str = "ran"          # ran | skipped | failed
    summary: str = ""
    seconds: float = 0.0
    data: dict = field(default_factory=dict)


@dataclass
class DoctorReport(Report):
    """Everything the doctor found: the findings (stops and notes, as ``check`` reports them) plus one section per
    check with its structured data, and what was checked (project, disc, Studio, options). Never holds retail bytes
    or the user's textures: names, counts, sizes and SHA-256 digests only."""
    sections: list = field(default_factory=list)
    project: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)
    studio: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)

    def section(self, key):
        return next((s for s in self.sections if s.key == key), None)

    def as_dict(self) -> dict:
        return dict(schema=DOCTOR_SCHEMA, ok=self.ok, seconds=round(self.seconds, 1), steps=list(self.steps),
                    stops=len(self.stops), notes=len(self.notes), studio=dict(self.studio), project=dict(self.project),
                    source=dict(self.source), options=dict(self.options),
                    findings=[asdict(f) for f in self.findings],
                    sections=[dict(key=s.key, title=s.title, status=s.status, summary=s.summary,
                                   seconds=round(s.seconds, 1), data=s.data) for s in self.sections])

    def headline(self) -> str:
        if self.ok:
            return "Your project passed the check: nothing has to be changed or unticked before Build."
        return (f"Change or untick {len(self.stops)} thing{'s' if len(self.stops) != 1 else ''} before Build, or it "
                "will stop partway through.")

    def summary(self) -> str:
        """A few lines for the Build tab: the result, each stop, and one line per check."""
        lines = [self.headline()]
        for number, finding in enumerate(self.stops[:6], 1):
            lines.append(f"{number}. {finding.title}")
            if finding.fix:
                lines.append(f"   What to do: {finding.fix}")
        if len(self.stops) > 6:
            lines.append(f"   ... and {len(self.stops) - 6} more (see the saved report).")
        lines.append("")
        for section in self.sections:
            if section.summary:
                lines.append(f"{section.title}: {section.summary}")
        lines.append("")
        lines.append(f"{len(self.notes)} note{'s' if len(self.notes) != 1 else ''} on what Build will do with your work. "
                     f"Checked in {_duration(self.seconds)}; nothing was written.")
        return "\n".join(lines)

    def text(self) -> str:
        """The whole report in plain words (what Save report writes and the command line prints)."""
        lines = [f"2K5 Mod Studio project check ({self.studio.get('version', 'unknown version')}, "
                 f"{self.studio.get('platform', '')})"]
        if self.project.get("name"):
            lines.append(f"Project: {self.project['name']} ({self.project.get('edits', 0):,} edits)")
        if self.source.get("name"):
            lines.append(f"Disc: {self.source['name']} ({self.source.get('identity') or 'not read'})")
        lines.append(f"Took {_duration(self.seconds)}. Nothing was written to your project or your disc.")
        lines.append("")
        lines.append(self.headline())
        for number, finding in enumerate(self.stops, 1):
            lines.append("")
            lines.append(f"{number}. {finding.title}")
            if finding.detail:
                lines.append(f"   {finding.detail}")
            lines.append(f"   What to do: {finding.fix}")
        if self.notes:
            lines.append("")
            lines.append("What Build will do with your work (no action needed):")
            for finding in self.notes:
                lines.append(f"- {finding.title}")
                if finding.detail:
                    lines.append(f"  {finding.detail}")
        for section in self.sections:
            lines.append("")
            lines.append(f"== {section.title} ({section.status}, {_duration(section.seconds)})")
            if section.summary:
                lines.append(section.summary)
            lines.extend(section.data.get("lines", ()))
        lines.append("")
        lines.append("Checked: " + "; ".join(self.steps) + ".")
        return "\n".join(lines)

    def write(self, folder, stem="project-check") -> dict:
        """Write ``<stem>.txt`` (the whole report), ``<stem>.json`` and ``<stem>-summary.txt`` into ``folder``;
        return {kind: path}. The files hold names, counts and digests only."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        out = {}
        for kind, name, body in (("text", f"{stem}.txt", self.text() + "\n"),
                                 ("json", f"{stem}.json", json.dumps(self.as_dict(), indent=1, sort_keys=False,
                                                                     default=str) + "\n"),
                                 ("summary", f"{stem}-summary.txt", self.summary() + "\n")):
            path = folder / name
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(scrub(body))
            out[kind] = path
        return out


def scrub(text: str) -> str:
    """A report is shared on Discord: the person's home folder (their account name) becomes ``~`` in every path."""
    try:
        home = str(Path.home())
    except (RuntimeError, OSError):
        return text
    if len(home) < 4:
        return text
    for form in sorted({home, home.replace("\\", "/"), home.replace("\\", "\\\\"), home.replace("/", "\\")},
                       key=len, reverse=True):
        text = text.replace(form, "~")
    return text


def _duration(seconds) -> str:
    seconds = int(round(seconds or 0))
    return f"{seconds // 60} min {seconds % 60} s" if seconds >= 60 else f"{seconds} s"


# ------------------------------------------------------------------------------------------------- the project

@dataclass
class ProjectInputs:
    """What the doctor reads of a project: the replaced asset ids, the artwork recipe, the fit receipts, the saved
    Build options and, when the PNGs are needed (the kit compile, the equipment import choices), a way to read them.
    From a ``.2k5mod`` archive (only read; untrusted data, never executed) or an open Studio session."""
    name: str = ""
    asset_ids: list = field(default_factory=list)
    document: dict | None = None
    fit_rows: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    archive: Path | None = None
    members: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)
    manifest_bytes: int = 0
    archive_bytes: int = 0
    fit_receipt_bytes: int = 0
    uniform_colors: int = 0
    manifest_sha256: str = ""

    def png(self, asset_id) -> bytes | None:
        """The replacement PNG's bytes (never written anywhere by the doctor except a private temporary folder)."""
        if asset_id in self.paths:
            try:
                return Path(self.paths[asset_id]).read_bytes()
            except OSError:
                return None
        member = self.members.get(asset_id)
        if self.archive is None or member is None:
            return None
        import zipfile
        with zipfile.ZipFile(self.archive) as archive:
            return archive.read(member)

    def stage(self, wanted, folder) -> dict:
        """{asset id: PNG path} for ``wanted``: the session's staged files, or copies from the archive in ``folder``."""
        wanted = sorted(set(wanted))
        out = {a: Path(self.paths[a]) for a in wanted if a in self.paths}
        missing = [a for a in wanted if a not in out]
        if missing and self.archive is not None:
            out.update(extract_assets(self.archive, self.members, missing, folder))
        return out


def project_inputs(project, *, document=None, fit_rows=None) -> ProjectInputs:
    """``project``: a ``.2k5mod`` path, an open Studio session (``iter_project_png_edits``), a ``read_archive`` dict,
    a ProjectInputs, or None (options only)."""
    import hashlib
    if project is None:
        return ProjectInputs(document=document, fit_rows=list(fit_rows or ()))
    if isinstance(project, ProjectInputs):
        return project
    if isinstance(project, (str, Path)):
        import zipfile
        path = Path(project)
        data = read_archive(path)
        inputs = ProjectInputs(name=path.name, asset_ids=list(data["asset_ids"]), document=document or data["document"],
                               fit_rows=list(fit_rows if fit_rows is not None else data["fit_rows"]),
                               settings=dict(data["settings"]), archive=path, members=dict(data["members"]),
                               archive_bytes=path.stat().st_size)
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo("project.json")
                inputs.manifest_bytes = info.file_size
                raw = archive.read(info)
                inputs.manifest_sha256 = hashlib.sha256(raw).hexdigest()
                manifest = json.loads(raw)
                inputs.uniform_colors = len(manifest.get("uniform_colors") or ())
                inputs.fit_receipt_bytes = len(json.dumps(manifest.get("fit_receipts") or {}, separators=(",", ":")))
            except (KeyError, ValueError):
                pass
        return inputs
    if isinstance(project, dict):
        return ProjectInputs(asset_ids=list(project.get("asset_ids", ())), document=document or project.get("document"),
                             fit_rows=list(fit_rows if fit_rows is not None else project.get("fit_rows", ())),
                             settings=dict(project.get("settings") or {}), members=dict(project.get("members") or {}))
    if callable(getattr(project, "iter_project_png_edits", None)):
        if fit_rows is None:
            try:
                from .equipment_staging import cached_equipment_fit_rows
                fit_rows = list(cached_equipment_fit_rows(project))
            except Exception:  # noqa: BLE001 - the receipts are a nicety; the check runs without them
                fit_rows = []
        return ProjectInputs(name=str(getattr(project, "name", "") or "open project"),
                             asset_ids=assets_from_session(project), document=document, fit_rows=list(fit_rows),
                             paths=paths_from_session(project))
    raise TypeError("project must be a .2k5mod path, an open Studio session, or None")


def _doctor_plan(settings, inputs, source):
    """The BuildPlan the doctor checks: the given saved options (or plan), else the project's own saved Build options,
    always with ``source`` as the disc and a target that is never written."""
    from dataclasses import replace
    from . import mod_build
    from . import nfl2k5_build_settings as saved
    source = str(source) if source else ""
    target = str(Path(source).with_name("project-check-never-written.iso")) if source else "project-check-never-written.iso"
    if isinstance(settings, mod_build.BuildPlan):
        return replace(settings, source=source or settings.source, target=target, overwrite=False)
    return saved.to_plan(dict(settings if settings is not None else inputs.settings or {}), source, target)


def _source_identity(source) -> dict:
    """Name, size and the disc preflight's identity sentence (no hashing of the whole 6 GB image)."""
    out = dict(name=Path(source).name if source else "", size=0, identity="", present=False)
    try:
        path = Path(source)
        out["size"] = path.stat().st_size
        out["present"] = path.is_file()
    except (OSError, TypeError, ValueError):
        return out
    try:
        from . import mod_build
        out["identity"] = mod_build._identity_note(path)
    except Exception:  # noqa: BLE001 - identity is descriptive only
        out["identity"] = f"{out['size']:,} bytes"
    return out


def _studio() -> dict:
    import platform
    try:
        from mod_editor import __version__ as version
    except ImportError:
        version = "unknown"
    return dict(version=f"2K5 Mod Studio {version}", platform=f"{platform.system()} {platform.release()}",
                python=sys.version.split()[0], machine=platform.machine())


# ------------------------------------------------------------------------------------------------- option words

def option_label(key: str, labels: dict | None = None) -> str:
    if labels and key in labels:
        return str(labels[key])
    if key in OPTION_LABELS:
        return OPTION_LABELS[key]
    from . import nfl2k5_stadium_dry_run as dry
    for attr, _module, label in dry.MODELS:
        if attr == key:
            return label
    return key.replace("_", " ").capitalize()


def _plain_value(value) -> str:
    if value is True:
        return "on"
    if value is False or value is None:
        return "off"
    if isinstance(value, dict) and set(value) == {"given"}:
        return "given" if value["given"] else "not given"
    if isinstance(value, str):
        return value
    text = json.dumps(value, default=str, sort_keys=True)
    return text if len(text) <= 80 else text[:77] + "..."


def _dict_difference(mine, theirs) -> str:
    """'touchback_yard 35 (release builds 25), ...' for two option dicts; the keys whose values differ."""
    if not isinstance(mine, dict) or not isinstance(theirs, dict):
        return ""
    keys = sorted(k for k in set(mine) | set(theirs) if mine.get(k) != theirs.get(k))
    return ", ".join(f"{k} {_plain_value(mine.get(k))} (release builds {_plain_value(theirs.get(k))})"
                     for k in keys[:6]) + (", ..." if len(keys) > 6 else "")


def _comparable(key, value):
    """An option value as the release gates record it: files and folders are only given or not."""
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str) and ("/" in value or "\\" in value):
        return {"given": True}
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, (str, Path)) and ("/" in str(v) or "\\" in str(v))
                                                         for v in value):
        return {"given": True}
    if isinstance(value, (tuple, list, dict)) and key != "modern_color_settings":
        try:   # nested tuples and lists compare equal, as the saved settings file stores them
            return json.loads(json.dumps(value, default=str))
        except (TypeError, ValueError):
            return value
    if key == "modern_color_settings":
        from . import nfl2k5_modern_color as colour
        try:
            return "custom" if colour.is_custom(colour.normalize_settings(value or None)) else "default"
        except (ValueError, TypeError):
            return "custom"
    return value


def _plan_options(plan) -> dict:
    import dataclasses
    return {f.name: getattr(plan, f.name) for f in dataclasses.fields(plan)
            if f.name not in ("source", "target", "overwrite")}


def release_gates() -> list:
    """[{id, label, platforms, options}] of the full builds this release's checks ran (data/nfl2k5_release_gates.json;
    the presets come from this code's mod_build.PRESETS)."""
    from . import mod_build
    path = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_release_gates.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_release_gates/v1":
        raise ValueError("unsupported release gate list")
    out = []
    for gate in document["gates"]:
        plan = mod_build.apply_preset(mod_build.BuildPlan("gate.iso", "gate-out.iso"), gate["preset"])
        options = {key: _comparable(key, value) for key, value in _plan_options(plan).items()}
        for key, value in (gate.get("overrides") or {}).items():
            options[key] = _comparable(key, value) if not (isinstance(value, dict) and set(value) == {"given"}) else value
        out.append(dict(id=gate["id"], label=gate["label"], platforms=list(gate.get("platforms", ())), options=options,
                        release=document.get("release", "")))
    return out


def colour_lever_changes(settings) -> list:
    """[(lever, default, yours)] of every Modern colour value that differs from the default."""
    from . import nfl2k5_modern_color as colour
    try:
        mine = colour.normalize_settings(settings or None)
    except (ValueError, TypeError):
        return []
    default = colour.default_settings()
    out = []
    for key in sorted(set(mine.get("values", {})) | set(default.get("values", {}))):
        a, b = default.get("values", {}).get(key), mine.get("values", {}).get(key)
        if a != b:
            out.append((key, a, b))
    for group in ("enabled", "linked"):
        for key in sorted(set(mine.get(group, {})) | set(default.get(group, {}))):
            a, b = default.get(group, {}).get(key), mine.get(group, {}).get(key)
            if a != b:
                out.append((f"{group}.{key}", a, b))
    return out


def untested_options(plan, *, labels=None, platform=None) -> dict:
    """What in ``plan`` no release build of this Studio version ever built: single option values, the known
    interacting pairs, and the platform. {"options": [...], "pairs": [...], "platform": str|None, "gates": [...]}"""
    from . import mod_build
    from . import nfl2k5_stadium_dry_run as dry
    gates = release_gates()
    defaults = _plan_options(mod_build.BuildPlan("x.iso", "y.iso"))
    mine = _plan_options(plan)
    items = []
    for key, value in sorted(mine.items()):
        if value == defaults.get(key):
            continue
        comparable = _comparable(key, value)
        built = [g for g in gates if g["options"].get(key, _comparable(key, defaults.get(key))) == comparable]
        if built:
            continue
        seen = sorted({_plain_value(g["options"].get(key)) for g in gates})
        item = dict(option=key, label=option_label(key, labels), yours=_plain_value(comparable),
                    release_builds=", ".join(seen))
        nearest = next((g["options"].get(key) for g in gates if isinstance(g["options"].get(key), dict)), None)
        if isinstance(comparable, dict) and isinstance(nearest, dict) and set(comparable) != {"given"}:
            item["yours"] = _dict_difference(comparable, nearest) or item["yours"]
            item["release_builds"] = "the values in brackets"
        if key == "modern_color_settings":
            item["levers"] = [dict(lever=l, default=a, yours=b) for l, a, b in colour_lever_changes(value)]
        items.append(item)
    pairs = []
    for a, b, why in INTERACTING_PAIRS:
        va, vb = _comparable(a, mine.get(a)), _comparable(b, mine.get(b))
        if va in (False, None, "default", "") or vb in (False, None, "default", ""):
            continue
        if not any(g["options"].get(a) == va for g in gates) or not any(g["options"].get(b) == vb for g in gates):
            continue   # already listed as a single option no release build tried
        if any(g["options"].get(a) == va and g["options"].get(b) == vb for g in gates):
            continue
        pairs.append(dict(options=[a, b], labels=[option_label(a, labels), option_label(b, labels)], why=why))
    if _comparable("modern_color_settings", mine.get("modern_color_settings")) == "custom" and mine.get("modern_color"):
        writers = [option_label(step_option, labels) for step_option in
                   ("modern_arrowhead", "modern_metlife", "modern_practice_field", "modern_surfaces",
                    *[attr for attr, _m, _l in dry.MODELS]) if mine.get(step_option)]
        if writers:
            pairs.append(dict(options=["modern_color_settings"], labels=["your own Modern colour values"],
                              why="no release build grades the stadiums with values other than the defaults, and these "
                                  "stadium writers refit their fields with them: " + ", ".join(writers)))
    platform = platform or sys.platform
    platform_note = None
    if platform.startswith("win") and dry.selected_steps(plan):
        windows = [g["label"] for g in gates if "windows" in g["platforms"]
                   and any(g["options"].get(option) for option in ("modern_color", "modern_surfaces"))]
        if not windows:
            platform_note = ("No release build ran the stadium, colour or surface steps under Windows Python (the "
                             "Windows check built the Experimental preset, which has none of them).")
    return dict(options=items, pairs=pairs, platform=platform_note,
                gates=[dict(id=g["id"], label=g["label"], platforms=g["platforms"]) for g in gates],
                release=gates[0]["release"] if gates else "")


# ------------------------------------------------------------------------------------------------- inventory

#: the kit package pieces (chunk index -> words), from a retail kit file's chunk list
KIT_PIECES = {0: "uniform header", 1: "jersey (torso)", 2: "pants", 3: "sleeves", 4: "socks", 5: "elbow pads",
              6: "gloves", 7: "long sleeves", 8: "shoes", 9: "shoes", 10: "wristbands", 11: "helmet (model A)",
              12: "helmet (model C)", **{13 + d: f"jersey digit {d}" for d in range(10)},
              **{23 + d: f"helmet digit {d}" for d in range(10)}, **{33 + d: f"arm digit {d}" for d in range(10)},
              43: "nameplate letters", 44: "name table", 45: "jersey bump map", 46: "sleeve bump map",
              47: "pants bump map", 48: "sock bump map", 49: "team logo", 50: "chiclet", 51: "small player",
              52: "flip chip"}

_UNIFORM_PART = re.compile(r"^nfl2k5\.uniform\.([0-9]{2}[ha](?:[0-9]|[1-9][0-9]))\.(.+)$", re.ASCII)


def uniform_chunk(asset_id: str):
    """(kit selector, chunk index) of a uniform asset id, or None for parts outside the kit file (Team Select cards)."""
    match = _UNIFORM_PART.match(asset_id)
    if not match:
        return None
    selector, part = match.group(1).upper(), match.group(2)
    fixed = {"torso": 1, "pants": 2, "sleeve": 3, "helmet.helmet00": 11, "helmet.helmet02": 12, "nameplate": 43}
    if part in fixed:
        return selector, fixed[part]
    digit = re.fullmatch(r"digit\.(jersey|helmet|arm)\.([0-9])", part)
    if digit:
        return selector, {"jersey": 13, "helmet": 23, "arm": 33}[digit.group(1)] + int(digit.group(2))
    return None


def _family(asset_id: str) -> str:
    if asset_id.startswith("tset:"):
        return "equipment"
    parts = asset_id.split(".")
    if len(parts) >= 2 and parts[0] == "nfl2k5":
        return parts[1]
    return parts[0] or "other"


def equipment_choice(png: bytes | None, asset_id: str) -> str:
    """'own texture' (an explicit own-texture import), 'shared colours' (an explicit palette-only import) or
    'automatic' (an ordinary PNG: Build decides), from the PNG's private import-choice chunk."""
    if not png:
        return "unknown"
    try:
        from .nfl2k5_equipment_import_intent import OWN_TEXTURE, has_import_choice, import_settings
        if not has_import_choice(png):
            return "automatic"
        from PIL import Image
        import io
        with Image.open(io.BytesIO(png)) as image:
            rgba = image.convert("RGBA").tobytes()
        return "own texture" if import_settings(png, asset_id, rgba)[0] == OWN_TEXTURE else "shared colours"
    except Exception:  # noqa: BLE001 - a malformed or stale choice is reported, never executed
        return "stale choice"


def inventory(inputs: ProjectInputs, plan, *, read_pngs=True, progress=None) -> dict:
    """The project in numbers and against every known limit (project_archive's limits, the largest game kit)."""
    from collections import Counter
    from mod_editor.studio import project_archive as pa
    say = progress or (lambda *_: None)
    families = Counter(_family(a) for a in inputs.asset_ids)
    uniform_parts, packages, teams = Counter(), set(), set()
    for asset_id in inputs.asset_ids:
        match = _UNIFORM_PART.match(asset_id)
        if match:
            part = match.group(2)
            uniform_parts["digits" if part.startswith("digit.") else "Team Select cards"
                           if part.startswith("team-select") else part.split(".")[0]] += 1
            packages.add(match.group(1).upper())
            teams.add(match.group(1)[:2])
    chunks, kit_packages = edited_kit_chunks(inputs.asset_ids)
    equipment_parts = Counter(KIT_PIECES.get(chunk, f"piece {chunk}") for (_s, chunk), ids in chunks.items()
                              for _ in ids)
    choices = Counter()
    equipment = [a for a in inputs.asset_ids if a.startswith("tset:")]
    if read_pngs and equipment and (inputs.archive is not None or inputs.paths):
        import zipfile
        archive = zipfile.ZipFile(inputs.archive) if inputs.archive is not None else None
        try:
            for number, asset_id in enumerate(equipment, 1):
                if number % 500 == 0:
                    say(f"Reading your equipment import choices ({number:,} of {len(equipment):,})", number,
                        len(equipment))
                if asset_id in inputs.paths or archive is None or asset_id not in inputs.members:
                    png = inputs.png(asset_id)
                else:
                    info = archive.getinfo(inputs.members[asset_id])
                    png = archive.read(info) if info.file_size <= 64 * 1024 * 1024 else None
                choices["automatic" if png and b"npTC" not in png else equipment_choice(png, asset_id)] += 1
        finally:
            if archive is not None:
                archive.close()
    limits = []

    def limit(name, value, maximum, unit=""):
        share = value / maximum if maximum else 0
        limits.append(dict(name=name, value=value, limit=maximum, share=round(share, 3), unit=unit,
                           state="over" if value > maximum else "close" if share >= 0.8 else "ok"))

    limit("project edits", len(inputs.asset_ids), pa.MAX_PROJECT_EDITS)
    if inputs.manifest_bytes:
        limit("project manifest (project.json)", inputs.manifest_bytes, pa.MAX_MANIFEST_BYTES, "bytes")
    if inputs.fit_receipt_bytes:
        limit("equipment fit receipts", inputs.fit_receipt_bytes, pa.MAX_FIT_RECEIPTS_BYTES, "bytes")
    if inputs.archive_bytes:
        limit("project file", inputs.archive_bytes, pa.MAX_PROJECT_BYTES, "bytes")
    if inputs.uniform_colors:
        limit("uniform colour edits", inputs.uniform_colors, pa.MAX_UNIFORM_COLOR_EDITS)
    if inputs.archive is not None:
        import zipfile
        with zipfile.ZipFile(inputs.archive) as archive:
            sizes = [info.file_size for info in archive.infolist() if info.filename != "project.json"]
        if sizes:
            limit("largest replacement PNG", max(sizes), pa.MAX_REPLACEMENT_BYTES, "bytes")
            limit("all replacement PNGs", sum(sizes), pa.MAX_PROJECT_REPLACEMENT_BYTES, "bytes")
    stadium = sorted(a for a in inputs.asset_ids if a.startswith("nfl2k5.stadium."))
    return dict(edits=len(inputs.asset_ids), families=dict(families.most_common()), uniform_parts=dict(uniform_parts),
                kit_packages=len(packages | kit_packages), teams=len(teams), equipment_parts=dict(equipment_parts),
                equipment_choices=dict(choices), stadium_edits=len(stadium), stadium_examples=stadium[:8],
                limits=limits)


def _inventory_lines(data) -> list:
    lines = [f"{data['edits']:,} edits: " + ", ".join(f"{count:,} {family}" for family, count in data["families"].items())
             + f"; {data['kit_packages']:,} kit files of {data['teams']} teams."]
    if data["uniform_parts"]:
        lines.append("Uniform art: " + ", ".join(f"{count:,} {part}" for part, count in
                                                  sorted(data["uniform_parts"].items(), key=lambda kv: -kv[1])) + ".")
    if data["equipment_parts"]:
        lines.append("Equipment: " + ", ".join(f"{count:,} {part}" for part, count in
                                                sorted(data["equipment_parts"].items(), key=lambda kv: -kv[1])) + ".")
    if data["equipment_choices"]:
        lines.append("Equipment import choices: " + ", ".join(f"{count:,} {kind}" for kind, count in
                                                             sorted(data["equipment_choices"].items())) +
                     " (own texture = a private image chain that grows the kit file; automatic = Build decides).")
    for row in data["limits"]:
        unit = " bytes" if row["unit"] == "bytes" else ""
        lines.append(f"{row['name']}: {row['value']:,}{unit} of {row['limit']:,}{unit} ({row['share'] * 100:.0f} percent)"
                     + (" OVER THE LIMIT" if row["state"] == "over" else " (close to the limit)" if row["state"] == "close"
                        else ""))
    return lines


# ------------------------------------------------------------------------------------------------- the kits

def _repairs_change(selector, raw) -> bool:
    """True when one of the 2026 kit repairs (which run before the new kits are composed) would rewrite a chunk of
    this donor package: it holds a pinned pre-repair SOFTDRINK texture. A retail kit holds none."""
    from . import nfl2k5_kit_fixes_2026 as fixes
    for document in (fixes.spec(), fixes.alternates(), fixes.finish(), fixes.seattle(), fixes.overlaps(),
                     fixes.chiefs(), fixes.swooshes(), fixes.nameplates()):
        for row in document.get("textures", ()):
            if row.get("selector", "").upper() != selector.upper():
                continue
            try:
                chunk = fixes._chunk_for(raw, row["chunk"])
            except (ValueError, KeyError, IndexError):
                continue
            if sha(raw[chunk.offset:chunk.end_offset]) == row.get("before_sha256"):
                return True
    return False


def sha(data) -> str:
    import hashlib
    return hashlib.sha256(bytes(data)).hexdigest()


def _art_rows(kit):
    """[(side letter, art row, donor selector)] of one new kit: which donor piece each art step paints on."""
    from . import nfl2k5_moment_kits as kits
    out = []
    for letter, side in sorted(kit["sides"].items()):
        sources = kits._expand(side.get("chunks", {}))
        for art in side.get("art", ()):
            chunk = int(art.get("chunk", -1))
            out.append((letter, art, sources.get(chunk, side["base"])))
    return out


def _poly_paint_changes(png: bytes, art) -> bool | None:
    """Whether the solid-colour ``poly`` ops of one art row would change any pixel of the user's PNG (True/False), or
    None when the row has other kinds of steps or the image cannot be read (then only Build can tell)."""
    ops = art.get("ops") or ()
    if not ops or any(op.get("op") != "poly" or not op.get("color") or not op.get("points") for op in ops):
        return None
    try:
        import io
        from PIL import Image, ImageDraw
        with Image.open(io.BytesIO(png)) as image:
            rgba = image.convert("RGBA")
        width, height = art.get("size", [rgba.width, rgba.height])[:2]
        sx, sy = rgba.width / float(width), rgba.height / float(height)
        for op in ops:
            mask = Image.new("L", rgba.size, 0)
            ImageDraw.Draw(mask).polygon([(x * sx, y * sy) for x, y in op["points"]], fill=255)
            colour = op["color"].lstrip("#")
            target = tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))
            for (r, g, b, _a), inside in zip(rgba.getdata(), mask.getdata()):
                if inside and (r, g, b) != target:
                    return True
        return False
    except Exception:  # noqa: BLE001 - an unreadable image is left to Build
        return None


def kit_dependencies(plan, retail, inputs: "ProjectInputs | None" = None, *, progress=None) -> dict:
    """What happens to each new Anniversary and classic kit on this project's donors, as far as it can be told before
    Build, and which classic team files would lose the kit their classic uniform needs.

    A kit whose art changes nothing on the plain retail donors (K1 on a retail Giants sleeve: "the art changed no
    texel") is left out by Build when its donor is still retail at that step (the 2026 repairs only touch SOFTDRINK
    kits); a donor piece the project replaced with its own uniform art is composed from that art instead, which the
    check can tell only for solid-colour paint steps (it reads the PNG). Studio beta 79 then stops at a classic team
    whose default uniform is a left-out kit ("classic default N has no year pair in its team file").

    {"left_out": {kit: reason}, "uncertain": {kit: why}, "paints_your_art": [{kit, side, piece, selector, changes}],
     "repaired_first": [kit], "orphans": [{file, style, kit, sure}], "documents": [feature]}"""
    from . import nfl2k5_moment_kits as kits
    documents = _feature_documents(plan)
    out = dict(left_out={}, uncertain={}, paints_your_art=[], repaired_first=[], orphans=[],
               documents=[f for f, _d in documents])
    if not documents or not retail:
        return out
    plain = donors_with_edits(documents, {}, {}, None, retail)
    retail_packages = kits.RetailPackages(retail)
    uniform_pieces = {}
    for asset_id in (inputs.asset_ids if inputs is not None else ()):
        place = uniform_chunk(str(asset_id))
        if place is not None:
            uniform_pieces[place] = str(asset_id)
    out["defaults_follow_kits"] = callable(getattr(kits, "dropped_defaults", None))
    for feature, doc in documents:
        skipped = dict(compose_receipt(doc, plain, retail_packages)["skipped_kits"])
        for kit in doc["kits"]:
            on_user_art = []
            for letter, art, selector in _art_rows(kit):
                asset_id = uniform_pieces.get((selector.upper(), int(art.get("chunk", -1))))
                if asset_id is None:
                    continue
                png = inputs.png(asset_id) if inputs is not None else None
                changes = _poly_paint_changes(png, art) if png else None
                on_user_art.append(changes)
                out["paints_your_art"].append(dict(kit=kit["id"], side=letter, selector=selector.upper(),
                                                   piece=KIT_PIECES.get(int(art.get("chunk", -1)), "piece"),
                                                   asset_id=asset_id, changes=changes, note=art.get("note", "")))
            if kit["id"] not in skipped:
                continue
            donors = {side["base"] for side in kit["sides"].values()} | {
                s for side in kit["sides"].values() for s in kits._expand(side.get("chunks", {})).values()}
            if any(_repairs_change(s, plain.get(s) or retail_packages[s]) for s in donors if s in plain):
                out["repaired_first"].append(kit["id"])
            elif on_user_art and any(c is True for c in on_user_art):
                out["uncertain"][kit["id"]] = ("its art step paints over your own art, so Build composes it from "
                                               "your art (it would be left out on the retail art)")
            elif on_user_art and any(c is None for c in on_user_art):
                out["uncertain"][kit["id"]] = "its art step works on your own art; only Build can tell"
            else:
                out["left_out"][kit["id"]] = skipped[kit["id"]]
        dropped = set(out["left_out"]) | set(out["uncertain"])
        kept = kits.without_kits(doc, {k: v for k, v in skipped.items() if k in dropped})
        provided = {}
        for selection in kept.get("selections", ()):
            if "kit" in selection:
                provided.setdefault(selection["file"], set()).add(selection["style"])
        by_code_style = {(k["code"], k["style"]): k["id"] for k in doc["kits"] if k["id"] in dropped}
        for default in kept.get("classic_defaults", ()):
            kit_id = by_code_style.get((default["file"][2:4], default["style"]))
            if kit_id is not None and default["style"] not in provided.get(default["file"], set()):
                out["orphans"].append(dict(file=default["file"], style=default["style"], kit=kit_id,
                                           sure=kit_id in out["left_out"], why=default.get("why", ""),
                                           stops_build=not out["defaults_follow_kits"]))
    return out


# ------------------------------------------------------------------------------------------------- the dive

def doctor(project, source, settings=None, *, progress: Callable[..., None] | None = None, workers: int | None = None,
           checks: Iterable[str] | None = None, stadium_models: bool = False, source_index=None, source_cache=None,
           document: dict | None = None, fit_rows=None, labels: dict | None = None, use_cache: bool = True,
           read_pngs: bool = True, compile_kits: bool | None = None) -> DoctorReport:
    """The whole dive on a project before (or after) a long build. Writes nothing to the project or the disc.

    ``project``: a ``.2k5mod`` path, an open Studio session, a ``read_archive`` dict, or None (options only).
    ``source``: the disc the build starts from (the user's retail image). ``settings``: None (the project's own saved
    Build options), a saved-settings dict (``nfl2k5_build_settings``) or a ``mod_build.BuildPlan`` (its options).
    ``checks``: a subset of DOCTOR_CHECKS (default all; QUICK_CHECKS skips the disc preflight and the stadium dry run).
    ``workers``: processes for the stadium dry run (default: the cores less one, at most 8). ``source_index``: Studio's
    source cache pack 0, for compiling the project's equipment into the kit donors (``source_cache``: the cache folder
    to read the disc into when no index is given). ``document``/``fit_rows``: the artwork recipe and fit receipts of a
    session (an archive carries its own). ``labels``: {option key: Build tab words}. ``compile_kits``: compile the
    project's sock, glove and shoe edits into the kit donors (default: yes for the full check, or when an index is
    given; reading a disc into the source cache the first time takes minutes).

    Every check that cannot run says so in its section (status "skipped" or "failed", with the reason); a check that
    raises never stops the others. Build failures can call this to put the report in their diagnostic bundle
    (job h3): ``doctor(session_or_path, plan.source, plan, checks=QUICK_CHECKS)`` takes seconds."""
    import tempfile
    started = time.monotonic()
    say = progress or (lambda *_: None)
    wanted = tuple(DOCTOR_CHECKS if checks is None else [c for c in DOCTOR_CHECKS if c in set(checks)])
    inputs = project_inputs(project, document=document, fit_rows=fit_rows)
    plan = _doctor_plan(settings, inputs, source)
    report = DoctorReport(studio=_studio(), source=_source_identity(source))
    report.project = dict(name=inputs.name, edits=len(inputs.asset_ids), manifest_bytes=inputs.manifest_bytes,
                          manifest_sha256=inputs.manifest_sha256, archive_bytes=inputs.archive_bytes)
    selected = [key for key, value in _plan_options(plan).items() if value is True]
    report.options = dict(selected=selected, colour_changes=[list(row) for row in colour_lever_changes(
        plan.modern_color_settings)] if getattr(plan, "modern_color", False) else [])
    have_source = bool(report.source.get("present"))

    def run(key, title, body):
        section = Section(key, title)
        began = time.monotonic()
        try:
            body(section)
        except Exception as exc:  # noqa: BLE001 - one check failing never hides the others
            from .nfl2k5_project_fit import BuildCancelled
            if isinstance(exc, BuildCancelled):
                raise
            section.status = "failed"
            section.summary = f"could not finish: {str(exc).strip()[:300] or type(exc).__name__}"
            import traceback
            section.data["error"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-6:])[-3000:]
        section.seconds = time.monotonic() - began
        report.sections.append(section)
        report.steps.append(title)

    with tempfile.TemporaryDirectory(prefix="2k5-project-check-") as folder:
        index = source_index
        paths = None

        def options(section):
            nonlocal index, paths
            chunks, _packages = edited_kit_chunks(inputs.asset_ids)
            documents = _feature_documents(plan)
            wanted_compile = compile_kits if compile_kits is not None else (
                index is not None or "stadiums" in wanted or "preflight" in wanted)
            do_compile = bool(wanted_compile and "kits" in wanted and chunks and documents and have_source and (
                inputs.archive is not None or inputs.paths))
            if do_compile:
                from . import nfl2k5_moment_kits as kits
                donors = {s for _f, doc in documents for s in kits.donors(doc)}
                needed = [a for (selector, _c), ids in chunks.items() if selector in donors for a in ids]
                if index is None:
                    say("Reading your disc into Studio's private cache (the first time takes a few minutes)", 0, 0)
                    from .nfl2k5_source_cache import Nfl2k5SourceCache
                    index = Nfl2k5SourceCache(source_cache).index(Path(source)).pack0
                paths = inputs.stage(needed, folder)
            quick = check(plan, asset_ids=inputs.asset_ids, document=inputs.document, fit_rows=inputs.fit_rows,
                          progress=progress, run_preflight=("preflight" in wanted and have_source),
                          asset_paths=paths if do_compile else None, source_index=index if do_compile else None)
            for finding in quick.findings:
                finding.code = finding.code or f"check.{re.sub(r'[^a-z0-9]+', '_', finding.area.lower()).strip('_')}"
            report.findings.extend(quick.findings)
            section.summary = (f"{len(quick.stops)} to change, {len(quick.notes)} notes; checked "
                               + "; ".join(quick.steps) + ".")
            if "preflight" in wanted and not have_source:
                section.summary += " The disc preflights did not run: the disc is not there."
            section.data["lines"] = [f"Options on: {len(selected)}."] + (
                [f"Your Modern colour values differ from the defaults in {len(report.options['colour_changes'])} "
                 "places: " + ", ".join(f"{lever} {a} -> {b}" for lever, a, b in report.options["colour_changes"][:20])
                 + ("." if len(report.options["colour_changes"]) <= 20 else ", ...")]
                if report.options["colour_changes"] else [])

        def kit_section(section):
            if not _feature_documents(plan):
                section.status = "skipped"
                section.summary = "no Anniversary moment kits or classic teams' kit selected."
                return
            if not have_source:
                section.status = "skipped"
                section.summary = "the disc is not there, so the kits could not be tried."
                return
            say("Trying the new Anniversary and classic kits on your disc's kits", 0, 0)
            found = kit_dependencies(plan, str(source), inputs)
            section.data.update(found)
            lines = []
            for kit_id, reason in sorted(found["left_out"].items()):
                lines.append(f"- {kit_id} will be left out: {reason.split(': ', 1)[-1]}.")
                report.findings.append(Finding(NOTE, "Anniversary moment kits",
                                               f"The new kit {kit_id} cannot be made from the kits on your disc and "
                                               "will be left out.",
                                               f"Reason: {reason.split(': ', 1)[-1]}. Its moment sides keep the kit they "
                                               "had.", code="kits.left_out"))
            for kit_id, why in sorted(found["uncertain"].items()):
                lines.append(f"- {kit_id}: {why}.")
            for row in found["paints_your_art"]:
                state = ("paints over it" if row["changes"] is True else "changes nothing on it" if row["changes"] is False
                         else "cannot be tried before Build")
                lines.append(f"- {row['kit']} ({'away' if row['side'] == 'A' else 'home'}) takes your {row['selector']} "
                             f"{row['piece']} ({row['asset_id']}): its art step ({row['note'] or 'paint'}) {state}.")
            painted = [r for r in found["paints_your_art"] if r["changes"] is True]
            if painted:
                report.findings.append(Finding(
                    NOTE, "Anniversary moment kits",
                    f"{len(painted)} new kit piece{'s are' if len(painted) != 1 else ' is'} made from your own art and "
                    "painted over: " + _named(f"{r['kit']} {r['selector']} {r['piece']}" for r in painted) + ".",
                    "These art steps were drawn for the SOFTDRINK kits (for example K1 paints two white boxes where the "
                    "2026 maker marks sit on the sleeve). On your art they paint the same boxes over your design in that "
                    "new kit only; your own kits keep your art.", code="kits.paints_your_art"))
            followed = [o for o in found["orphans"] if not o.get("stops_build", True)]
            if followed:
                report.findings.append(Finding(
                    NOTE, "Anniversary moment kits",
                    "The classic team file" + ("s " if len({o["file"] for o in followed}) > 1 else " ")
                    + _named(sorted({o["file"] for o in followed})) + " keep the default uniform they have, because "
                    "the new kit " + _named(sorted({o["kit"] for o in followed})) + " they would open on "
                    + ("is" if len({o["kit"] for o in followed}) == 1 else "are") + " left out.",
                    "", code="kits.default_kept"))
            sure = [o for o in found["orphans"] if o["sure"] and o.get("stops_build", True)]
            unsure = [o for o in found["orphans"] if not o["sure"] and o.get("stops_build", True)]
            if sure:
                files = sorted({o["file"] for o in sure})
                report.findings.append(Finding(
                    STOP, "Anniversary moment kits",
                    f"The classic team file{'s' if len(files) > 1 else ''} {_named(files)} need"
                    f"{'' if len(files) > 1 else 's'} the left-out kit {_named(sorted({o['kit'] for o in sure}))}: Studio "
                    f"beta 79 stops about 6 minutes into the build with \"classic default {sure[0]['style']} has no year "
                    "pair in its team file\".",
                    "Studio beta 79.1 fixes this (a left-out kit takes its classic defaults with it).",
                    "Untick 25 more Anniversary moments until you have beta 79.1.", code="kits.orphan_default"))
            if unsure:
                report.findings.append(Finding(
                    NOTE, "Anniversary moment kits",
                    "Whether the new kit " + _named(sorted({o["kit"] for o in unsure})) + " is made depends on your own "
                    "art; if it is left out, Studio beta 79 stops at the classic team file "
                    + _named(sorted({o["file"] for o in unsure})) + ".",
                    "Studio beta 79.1 fixes this. With beta 79, untick 25 more Anniversary moments if the build stops "
                    "with \"classic default ... has no year pair\".", code="kits.orphan_maybe"))
            section.data["lines"] = lines
            section.summary = (f"{len(found['left_out'])} new kit{'s' if len(found['left_out']) != 1 else ''} left out, "
                               f"{len(found['uncertain'])} depending on your art, {len(painted)} pieces painted over "
                               f"your art, {len(sure)} classic default{'s' if len(sure) != 1 else ''} without a kit"
                               + (f", {len(found['repaired_first'])} checked only during Build (the 2026 repairs change "
                                  "their donors first)" if found["repaired_first"] else "") + ".")

        def stadium_section(section):
            from . import nfl2k5_stadium_dry_run as dry
            steps = dry.selected_steps(plan)
            if not steps:
                section.status = "skipped"
                section.summary = "no stadium, colour or surface option selected."
                return
            if not have_source:
                section.status = "skipped"
                section.summary = "the disc is not there, so the stadium refits could not be tried."
                return
            result = dry.run(plan, source, progress=progress, workers=workers, stadium_models=stadium_models,
                             use_cache=use_cache)
            section.data.update(result.as_dict())
            optional = optional_build_steps()
            counts = result.counts()
            per_step = []
            for step in result.steps:
                refit = counts.get((step, "refit"), 0)
                kept = counts.get((step, "kept"), 0)
                failed = counts.get((step, "failed"), 0)
                per_step.append(f"{dry.STEP_LABELS.get(step, step)}: {refit} refit, {kept} kept as they were, "
                                f"{failed} failed")
            lines = list(per_step)
            for row in (result.failed + result.kept)[:MAX_TEXT_ROWS]:
                lines.append(("FAILS: " if row["status"] == "failed" else "kept: ") + dry.describe(row))
            if len(result.failed) + len(result.kept) > MAX_TEXT_ROWS:
                lines.append(f"... and {len(result.failed) + len(result.kept) - MAX_TEXT_ROWS} more in the JSON report.")
            for label, why in result.not_covered:
                lines.append(f"Not tried here: {label} ({why}).")
            for name, why in sorted(result.skipped_bundles.items())[:12]:
                lines.append(f"Not tried: {name}: {why}.")
            section.data["lines"] = lines
            by_step = {}
            for row in result.failed:
                by_step.setdefault(row["step"], []).append(row)
            for step, rows in by_step.items():
                label = dry.STEP_LABELS.get(step, step)
                left_out = BUILD_STEP_NAMES.get(step) in optional
                where = _named(f"{r['venue']} ({r['bundle']})" for r in rows)
                report.findings.append(Finding(
                    NOTE if left_out else STOP, "Stadiums and colour",
                    f"{label} cannot refit {len(rows)} stadium bundle{'s' if len(rows) != 1 else ''} with your options: "
                    f"{where}.",
                    f"First reason: {rows[0]['reason']}. Studio beta 79 stopped the whole build at this point."
                    + (" This version leaves that step out of your disc instead and names it in the build log."
                       if left_out else ""),
                    f"Untick {option_label(dry.STEP_OPTIONS.get(step, step), labels)}, or set the Modern colour values "
                    "back toward the defaults, then check again. Send this report to the SOFTDRINK Discord so the "
                    "refit can be fixed.", code=f"stadiums.failed.{step}"))
            kept_groups = {}
            for row in result.kept:
                kept_groups.setdefault((row["step"], row["part"]), []).append(row)
            for (step, part), rows in sorted(kept_groups.items()):
                label = dry.STEP_LABELS.get(step, step)
                words = {"field": "field", "normal": "bump map", "divots": "divot layer"}.get(part, part)
                report.findings.append(Finding(
                    NOTE, "Stadiums and colour",
                    f"{label} keeps {len(rows)} {words}{'s' if len(rows) != 1 else ''} as they are "
                    f"(no room to refit them in their fixed slot): "
                    + _named(f"{r['venue']} {r['bundle'][3:5]}" for r in rows) + ".",
                    f"Reason: {rows[0]['reason'][:300]}. Those stadiums still get the rest of the option.",
                    code=f"stadiums.kept.{step}.{part}"))
            total_refit = sum(1 for r in result.rows if r["status"] == "refit")
            section.summary = (f"{result.bundles} bundles on {result.workers} workers: {total_refit} refits, "
                               f"{len(result.kept)} kept as they were, {len(result.failed)} failed"
                               + (f" ({result.cached_colour_refits} colour refits from the cache)"
                                  if result.cached_colour_refits else "") + ".")

        def untested_section(section):
            found = untested_options(plan, labels=labels)
            section.data.update(found)
            lines = [f"Release builds of {found['release']}: " + "; ".join(
                f"{g['label']} ({', '.join(g['platforms'])})" for g in found["gates"]) + "."]
            for item in found["options"]:
                lines.append(f"- {item['label']}: yours {item['yours']}; release builds {item['release_builds']}.")
                for lever in item.get("levers", ())[:30]:
                    lines.append(f"    {lever['lever']}: default {lever['default']}, yours {lever['yours']}")
            for pair in found["pairs"]:
                lines.append(f"- together: {' + '.join(pair['labels'])} ({pair['why']}).")
            if found["platform"]:
                lines.append(found["platform"])
            section.data["lines"] = lines
            from . import nfl2k5_stadium_dry_run as dry
            stadium_keys = {"modern_color", "modern_color_settings", "modern_arrowhead", "modern_metlife",
                            "modern_metlife_model", "modern_board_kit", "modern_practice_field", "modern_surfaces",
                            "modern_practice_field_team_logo", "modern_everbank_construction",
                            *[attr for attr, _m, _l in dry.MODELS]}
            risky = [i for i in found["options"] if i["option"] in stadium_keys or i["option"].startswith("espn25")
                     or i["option"] in ("classic_teams", "historic_teams_quick_game")]
            if risky or found["pairs"] or found["platform"]:
                report.findings.append(Finding(
                    NOTE, "Untested options",
                    f"{len(found['options'])} of your options or settings were never in a release build of this "
                    f"Studio version ({len(risky)} of them stadium, colour or Anniversary options).",
                    "Most risky first: " + _named([i["label"] for i in risky] + [" + ".join(p["labels"])
                                                                                 for p in found["pairs"]], 8)
                    + ". Build may be the first to run them; the stadium and kit dry runs above tried what they "
                    "could.", code="untested.options"))
            section.summary = (f"{len(found['options'])} option{'s' if len(found['options']) != 1 else ''} or "
                               f"setting{'s' if len(found['options']) != 1 else ''} no release build tried, "
                               f"{len(found['pairs'])} combination{'s' if len(found['pairs']) != 1 else ''}"
                               + ("; Windows Python never ran the stadium steps" if found["platform"] else "") + ".")

        def inventory_section(section):
            say("Counting your project's edits", 0, 0)
            data = inventory(inputs, plan, read_pngs=read_pngs, progress=progress)
            section.data.update(data)
            section.data["lines"] = _inventory_lines(data)
            over = [row for row in data["limits"] if row["state"] == "over"]
            close = [row for row in data["limits"] if row["state"] == "close"]
            for row in over:
                report.findings.append(Finding(STOP, "Project size", f"Your {row['name']} is over Studio's limit.",
                                               f"{row['value']:,} of {row['limit']:,}.",
                                               "Split the project or remove edits you do not use.", code="inventory.over"))
            if close:
                report.findings.append(Finding(NOTE, "Project size",
                                               "Your project is close to a Studio limit: " + _named(r["name"] for r in close)
                                               + ".", "; ".join(f"{r['value']:,} of {r['limit']:,}" for r in close),
                                               code="inventory.close"))
            stadium_edits = data["stadium_edits"]
            if stadium_edits:
                conflicts = stadium_edit_conflicts(inputs.asset_ids, plan)
                section.data["stadium_conflicts"] = conflicts
                if conflicts:
                    report.findings.append(Finding(
                        STOP, "Stadium edits", f"{len(conflicts)} of your stadium edits are in bundles a selected "
                        "stadium option rebuilds from the retail disc.",
                        "Build would stop after the long texture stage (the stadium bundles are not the retail ones "
                        "any more): " + _named(f"{c['asset_id']} ({c['bundle']}, {c['option']})" for c in conflicts) + ".",
                        "Untick the option named for each, or remove those stadium edits.", code="inventory.stadium_conflict"))
            section.summary = (f"{data['edits']:,} edits in {data['kit_packages']:,} kit files; "
                               f"{len(over)} over a limit, {len(close)} close.")

        bodies = dict(options=("options", "Options, artwork and disc checks", options),
                      kits=("kits", "Anniversary and classic kits", kit_section),
                      stadiums=("stadiums", "Stadium and colour dry run", stadium_section),
                      untested=("untested", "Options no release build tried", untested_section),
                      inventory=("inventory", "Your project in numbers", inventory_section))
        if "options" in wanted or "preflight" in wanted:
            run(*bodies["options"])
        for key in ("kits", "stadiums", "untested", "inventory"):
            if key in wanted:
                run(*bodies[key])
    report.seconds = time.monotonic() - started
    return report


def optional_build_steps() -> set:
    """The receipt step names Build leaves out (restoring what they wrote) instead of stopping when they fail: job h3's
    list (``build_steps.OPTIONAL_STEP_IDS`` or ``mod_build.OPTIONAL_STEPS``); empty on a Build without it, where every
    stadium refit that raises stops the whole build."""
    import importlib
    found = set()
    for module_name, attribute in (("build_steps", "OPTIONAL_STEP_IDS"), ("mod_build", "OPTIONAL_STEPS")):
        try:
            module = importlib.import_module(f"{__package__}.{module_name}")
        except ImportError:
            continue
        found |= set(getattr(module, attribute, ()) or ())
    return found


def stadium_edit_conflicts(asset_ids, plan) -> list:
    """The project's stadium edits inside bundles a selected stadium writer requires to be retail (Modern colour's
    pins, the stadium options' own bundles, Modern surfaces' home fields)."""
    from . import nfl2k5_modern_color as colour
    from . import nfl2k5_modern_surfaces as ms
    from . import nfl2k5_stadium_dry_run as dry
    try:
        pins = colour._pins()["bundles"]
    except (OSError, ValueError):
        pins = []
    by_outer = {pin["outer"]: pin["name"] for pin in pins}
    steps = dry.selected_steps(plan)
    out = []
    for asset_id in asset_ids:
        match = re.match(r"^nfl2k5\.stadium\.o(\d+)\.", str(asset_id))
        if not match:
            continue
        name = by_outer.get(int(match.group(1)))
        if name is None:
            continue
        owner = dry._owner(name, plan)
        option = None
        if "colour" in steps:
            option = "Modern colour and lighting"
        elif owner is not None:
            option = dry.STEP_LABELS.get(owner[0], owner[0])
        elif "surfaces" in steps and name in ms.HOME_BUNDLES:
            option = "Modern playing surfaces"
        if option:
            out.append(dict(asset_id=str(asset_id), bundle=name, option=option))
    return out


# ------------------------------------------------------------------------------------------------- command line

def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check a 2K5 Mod Studio project before a long build: the whole dive "
                                                 "(options, disc, kits, every stadium refit, untested options, sizes).")
    parser.add_argument("project", type=Path, help="the .2k5mod project file (only read)")
    parser.add_argument("--source", type=Path, required=True, help="your USA retail NFL 2K5 disc image")
    parser.add_argument("--report", type=Path, help="write project-check.txt, .json and -summary.txt into this folder")
    parser.add_argument("--json", nargs="?", const="-", help="print the JSON report (or write it to this file)")
    parser.add_argument("--quick", action="store_true", help="the quick checks only: no disc preflight and no stadium "
                        "dry run (seconds instead of minutes)")
    parser.add_argument("--checks", help="comma-separated subset of " + ",".join(DOCTOR_CHECKS))
    parser.add_argument("--workers", type=int, help="processes for the stadium dry run (default: cores less one, at most 8)")
    parser.add_argument("--stadium-models", action="store_true", help="also build every modern stadium's building in the "
                        "dry run (much slower; the buildings are the same for everyone)")
    parser.add_argument("--settings", type=Path, help="check these saved Build options (JSON) instead of the project's own")
    parser.add_argument("--no-source-preflight", action="store_true", help="skip the disc preflights")
    parser.add_argument("--source-cache", type=Path, help="Studio's private source cache folder (default: the usual one); "
                        "with it the check also tries your edited kits in the new Anniversary kits. The first read of "
                        "a disc takes a few minutes")
    parser.add_argument("--no-kit-compile", action="store_true", help="map the edited kits only, do not compile them")
    parser.add_argument("--no-cache", action="store_true", help="do not reuse or fill Build's colour refit cache")
    args = parser.parse_args(argv)
    checks = list(QUICK_CHECKS if args.quick else DOCTOR_CHECKS)
    if args.checks:
        checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    if args.no_source_preflight and "preflight" in checks:
        checks.remove("preflight")
    settings = json.loads(args.settings.read_text(encoding="utf-8")) if args.settings else None
    progress = lambda message, *_: print(message, file=sys.stderr, flush=True)  # noqa: E731
    inputs = project_inputs(args.project)
    if args.no_kit_compile:
        inputs.members, inputs.paths = {}, {}
    report = doctor(inputs, args.source, settings, progress=progress, workers=args.workers, checks=checks,
                    stadium_models=args.stadium_models, source_cache=args.source_cache, use_cache=not args.no_cache)
    if args.report:
        written = report.write(args.report)
        print("Report written: " + ", ".join(str(p) for p in written.values()), file=sys.stderr, flush=True)
    if args.json == "-":
        print(json.dumps(report.as_dict(), indent=1, default=str))
    else:
        print(report.text())
        if args.json:
            Path(args.json).write_text(json.dumps(report.as_dict(), indent=2, default=str) + "\n", encoding="utf-8",
                                       newline="\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
