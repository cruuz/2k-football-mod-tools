"""Check my project: what a long build will refuse or change, found in minutes (b779-ce1, Coach Edwards' report).

A project with thousands of texture replacements builds for 3 to 6 hours, and the built-in features that dress the
disc afterwards (Anniversary moment kits, the 2026 kit repairs, the classic teams' kits) used to discover only at the
end that a replaced kit was unusable. They now fall back on their own (``nfl2k5_moment_kits``), and this module says
beforehand, in plain words, what Build will do with the user's replacements and what, if anything, must be changed or
unticked first:

* ``stop``: Build would refuse. The finding says what to untick or change.
* ``note``: Build goes on; it says what happens to a named piece of the user's work. Nothing to untick.

It runs the checks the long build already runs first (option conflicts, the artwork recipe, equipment that needs a
refit, the source-disc preflights of ``mod_build.preflight_plan``) plus a read-only map of which of the user's edited
kit packages the built-in kit features read. It never writes a disc and never changes the project.

Command line (no Studio window; the archive is only read)::

    python3 -m mod_editor.core.nfl2k5_project_check PROJECT.2k5mod --source "ESPN NFL 2K5 (USA).xiso.iso" [--json out.json]
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
            where = "; ".join(f"{selector} chunk{'s' if len(c) > 1 else ''} {', '.join(str(i) for i in sorted(c))}"
                              for selector, c in sorted(hit.items()))
            notes.append(Finding(
                NOTE, feature,
                f"The new {kit.get('team', kit['code'])} kit {kit['id']} is built from kits you edited.",
                f"It reads {where}. Build keeps your edited artwork in it when it fits; if it does not fit the kit "
                "(more video memory than any game kit, or a sock whose clean and mud copies no longer share their "
                "image), Build uses the retail version of that piece in this new kit only and names it in the build "
                "log. Your own kits keep your artwork either way.",
                ""))
    return notes


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


# ------------------------------------------------------------------------------------------------- the whole check

def check(plan, *, asset_ids: Iterable[str] = (), document: dict | None = None, fit_rows: Iterable[dict] = (),
          progress: Callable[..., None] | None = None, run_preflight: bool = True) -> Report:
    """Run every quick check for ``plan`` and the project's replacements; never writes anything.

    ``asset_ids``: the replaced asset ids of the project. ``document``: its artwork recipe (``{"edits": [{"kind",
    "target"...}]}``) for the option-conflict check. ``fit_rows``: the equipment fit receipts the project carries.
    ``run_preflight``: also run the source-disc preflights Build runs first (a few minutes on a full option set)."""
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
    documents = []
    if getattr(plan, "espn25_more_moments", False):
        from . import nfl2k5_moment_kits as kits
        documents.append(("Anniversary moment kits", kits.document()))
    if getattr(plan, "classic_teams", False) and getattr(plan, "historic_teams_quick_game", False):
        from . import nfl2k5_classic_teams as classic
        documents.append(("Classic teams' kits", classic.authored_kits()))
    report.findings.extend(moment_kit_notes(documents, chunks))
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
                settings=manifest.get("build_settings") or {})


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Check a 2K5 Mod Studio project before a long build.")
    parser.add_argument("project", type=Path, help="the .2k5mod project file (only read)")
    parser.add_argument("--source", type=Path, required=True, help="your USA retail NFL 2K5 disc image")
    parser.add_argument("--json", type=Path, help="also write the report here")
    parser.add_argument("--no-source-preflight", action="store_true",
                        help="skip the disc preflights (the quick checks only)")
    args = parser.parse_args(argv)
    from . import nfl2k5_build_settings as saved
    data = read_archive(args.project)
    plan = saved.to_plan(data["settings"], str(args.source), str(args.source.with_name("project-check-never-written.iso")))
    report = check(plan, asset_ids=data["asset_ids"], document=data["document"], fit_rows=data["fit_rows"],
                   progress=lambda message, *_: print(message, file=sys.stderr, flush=True),
                   run_preflight=not args.no_source_preflight)
    print(report.text())
    if args.json:
        args.json.write_text(json.dumps(report.as_dict(), indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
