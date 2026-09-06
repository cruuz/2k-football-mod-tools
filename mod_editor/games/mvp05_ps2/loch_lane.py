"""The UI strings: every ``LOCH`` string on the disc, exported and replaced inside its span.

Three loose files, 7,977 strings [M].  A replacement is UTF-16LE plus its
terminator, no longer than the span the string already owns, NUL-padded to
it; the file goes back inside its own ISO9660 extent through the shared
writer, and the verifier re-parses the destination with :mod:`.loch_text`,
compares every string, and checks the image outside the declared ranges.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games.contract import (
    Catalogue, Edit, Field, Plan, Receipt, Refusal, Target, Verdict, require,
)

from . import containers, disc_write, loch_text

CAPABILITY_ID = "mvp05ps2.identity.ui_strings"
LANE_ID = "identity.ui_strings"
RECIPE_SCHEMA = "mvp05_ps2_ui_strings_recipe/v1"
CATALOGUE_SCHEMA = "mvp05_ps2_ui_strings_catalogue/v1"
WRITE_SCHEMA = "mvp05_ps2_ui_strings_write/v1"
MAX_TARGETS = 4000


def parse_key(key: str) -> Tuple[str, int]:
    match = re.match(r"^(.+)#(\d+)$", str(key))
    if match is None:
        raise Refusal(f"{key!r} does not name a string: a key is <file>#<index>, as the "
                      f"catalogue writes it.")
    return match.group(1), int(match.group(2))


class UiStringsLane:
    lane_id = LANE_ID
    capability_id = CAPABILITY_ID
    surface = "menus"
    page = "identity"
    title = "Menu and in-game strings (LOCH)"
    classification = "offline-writer-proved"
    recipe_schema = RECIPE_SCHEMA
    validators = ("tools/validate_mvp05_ps2_strings.sh", "tools/validate_mvp05_ps2_strings.bat")
    fixed_allocation = True

    def _files(self, disc: containers.Disc) -> List[Tuple[str, Any]]:
        return containers.archives_named(disc, containers.LOCH_FILES)

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        files: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        total = 0
        with containers.Disc(Path(source)) as disc:
            for name, entry in self._files(disc):
                if progress is not None:
                    progress(f"{name}…")
                try:
                    parsed = loch_text.parse(disc.file_bytes(entry), name)
                except (containers.DiscError, loch_text.LochError) as exc:
                    refusals.append({"where": name, "sentence": str(exc)})
                    continue
                summary = dict(parsed.summary(), path=entry.path, listed=0)
                total += len(parsed.strings)
                for item in parsed.strings:
                    if len(targets) >= MAX_TARGETS:
                        break
                    targets.append(self._target(name, entry.path, item))
                    summary["listed"] += 1
                files.append(summary)
        document = {"schema": CATALOGUE_SCHEMA, "source": str(source), "files": files,
                    "strings": total, "targets_listed": len(targets), "targets_cap": MAX_TARGETS,
                    "refusals": refusals, "runtime_note": disc_write.NOT_BOOTED}
        return Catalogue(CATALOGUE_SCHEMA, self.lane_id, str(source), tuple(targets), document)

    @staticmethod
    def _target(name: str, path: str, item: loch_text.LochString) -> Target:
        room = max(0, item.span // 2 - 1)
        preview = item.text if len(item.text) <= 48 else item.text[:45] + "…"
        return Target(
            key=f"{name}#{item.index}",
            label=f"{name} #{item.index}: {preview}",
            detail=f"{len(item.text)} character(s) · room for {room} · ids {', '.join(map(str, item.ids)) or '-'}",
            budget=f"Up to {room} UTF-16 characters; the string goes back inside its own span.",
            searchable=f"{name} {item.index} {item.text}",
            raw={"file": name, "path": path, "index": item.index, "offset": item.offset,
                 "span": item.span, "text": item.text, "ids": list(item.ids)},
            fields=(Field("text", "text", "Text",
                          f"Up to {room} character(s). Blank keeps what is there."),),
        )

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        unknown = sorted(set(values) - {"text"})
        if unknown:
            return f"{target.key}: {', '.join(unknown)} is not something this lane takes; give text."
        text = values.get("text")
        if text in (None, ""):
            return None
        text = str(text)
        if "\x00" in text:
            return f"{target.key}: a string cannot contain NUL; it ends the string."
        need = len(text.encode("utf-16-le")) + 2
        span = int(target.raw.get("span", 0))
        if need > span:
            return (f"{target.key}: that text is {need} byte(s) of UTF-16 plus its terminator and "
                    f"this string has {span} to give; shorten it by "
                    f"{-(-(need - span) // 2)} character(s).")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"string": edit.target_key, "text": str(edit.values.get("text", ""))}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": RECIPE_SCHEMA, "strings": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == RECIPE_SCHEMA,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {RECIPE_SCHEMA}")
        rows = recipe.get("strings")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'strings' list; choose at least one string")
        out = []
        seen = set()
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("string"), str),
                    f"string {number} must name the string it replaces")
            require(set(row) <= {"string", "text", "note"}, f"string {number} carries unknown keys")
            require(isinstance(row.get("text"), str) and row["text"] != "",
                    f"string {number} ({row['string']}) gives no text; this lane writes a disc, "
                    f"so every string in the recipe must say what replaces it")
            require(row["string"] not in seen, f"{row['string']} appears twice")
            seen.add(row["string"])
            out.append({"string": row["string"], "text": row["text"], "note": row.get("note")})
        return out

    def _compose(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Dict[str, Any]:
        entries = self._entries(recipe)
        grouped: Dict[str, List[Tuple[int, str, str]]] = {}
        for entry in entries:
            target = catalogue.target(entry["string"])
            problem = self.check_edit(target, {"text": entry["text"]})
            require(problem is None, str(problem))
            name, index = parse_key(entry["string"])
            grouped.setdefault(name, []).append((index, entry["text"], entry["string"]))
        written: Dict[str, bytes] = {}
        paths: Dict[str, str] = {}
        rows: List[Dict[str, Any]] = []
        with containers.Disc(Path(source)) as disc:
            for name, items in grouped.items():
                entry = disc.find(name)
                current = disc.file_bytes(entry)
                for index, text, key in items:
                    parsed = loch_text.parse(current, name)
                    try:
                        current, (offset, span) = parsed.replace(index, text)
                    except loch_text.LochError as exc:
                        raise Refusal(str(exc)) from exc
                    rows.append({"string": key, "file": name, "path": entry.path, "index": index,
                                 "offset": offset, "span": span, "text": text})
                written[name] = current
                paths[name] = entry.path
        return {"edits": entries, "strings": rows, "written": written, "paths": paths}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        composed = self._compose(Path(source), recipe, catalogue)
        replacements = {composed["paths"][n]: b for n, b in composed["written"].items()}
        ranges = disc_write.plan_ranges(Path(source), replacements)
        return Plan(self.lane_id, tuple(e["string"] for e in composed["edits"]), ranges,
                    {"schema": RECIPE_SCHEMA, "strings": composed["strings"],
                     "declared_bytes": sum(r.length for r in ranges),
                     "runtime_note": disc_write.NOT_BOOTED})

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        disc_write.check_destination(source, destination)
        composed = self._compose(source, recipe, catalogue)
        replacements = {composed["paths"][n]: b for n, b in composed["written"].items()}
        report, ranges = disc_write.replace_files(source, destination, replacements)
        document = {"schema": WRITE_SCHEMA, "source": str(source), "destination": str(destination),
                    "edits": composed["edits"], "strings": composed["strings"],
                    "files": [{"name": n, "path": composed["paths"][n], "bytes": len(b),
                               "sha256": disc_write.sha256(b)}
                              for n, b in sorted(composed["written"].items())],
                    "iso_report": report, "runtime_note": disc_write.NOT_BOOTED}
        return Receipt(WRITE_SCHEMA, self.lane_id, str(source), str(destination), ranges, document)

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        source, destination = Path(source), Path(destination)
        problem = disc_write.verify_image(source, destination, receipt.document.get("iso_report"))
        if problem:
            return Verdict(False, f"Verification failed {problem}")
        edits = receipt.document.get("edits") or []
        if not edits:
            return Verdict(False, "Verification failed: the receipt declares no strings.")
        wanted: Dict[str, Dict[int, str]] = {}
        for entry in edits:
            name, index = parse_key(entry["string"])
            wanted.setdefault(name, {})[index] = entry["text"]
        checked = 0
        try:
            with containers.Disc(source) as before, containers.Disc(destination) as after:
                for name, cells in wanted.items():
                    old = loch_text.parse(before.file_bytes(before.find(name)), name)
                    new = loch_text.parse(after.file_bytes(after.find(name)), name)
                    if len(old.strings) != len(new.strings):
                        return Verdict(False, f"Verification failed: {name} changed its string count.")
                    for a, b in zip(old.strings, new.strings):
                        if a.offset != b.offset or a.span != b.span:
                            return Verdict(False, f"Verification failed: {name} string {a.index} moved.")
                        expected = cells.get(a.index, a.text)
                        if b.text != expected:
                            return Verdict(False, f"Verification failed: {name} string {a.index} "
                                                  f"reads {b.text!r}, not {expected!r}.")
                        checked += 1
        except (containers.DiscError, loch_text.LochError, Refusal) as exc:
            return Verdict(False, f"Verification failed: {exc}")
        return Verdict(True, f"{len(wanted)} file(s) re-parsed from both images, {checked} string(s) "
                             f"compared, the edited ones read as the recipe says and the image-level "
                             f"ranges hold.", {"result": "PASS", "strings": checked})

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / "mvp05-ps2-strings-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            if int(target.raw.get("span", 0)) >= 12:
                return (Edit(target.key, {"text": "EDIT"}, note="conformance: one string"),)
        raise Refusal("this catalogue lists no string with room for an edit")


LANE = UiStringsLane()


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mod_editor.games.mvp05_ps2.loch_lane",
                                     description="Catalogue the LOCH strings of an MVP Baseball 2005 (PS2) disc.")
    parser.add_argument("--source")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                src = LANE.synthetic_source(Path(room))
                catalogue = LANE.build_catalogue(src)
                recipe = LANE.compose_recipe(LANE.conformance_edits(catalogue))
                dest = Path(room) / "out.iso"
                receipt = LANE.build(src, dest, recipe, catalogue)
                verdict = LANE.verify(src, dest, receipt)
                require(verdict.passed, verdict.summary)
                print(f"SELFTEST ok: {verdict.summary}")
                return 0
        catalogue = LANE.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("STRINGS files=%d strings=%d" % (len(document["files"]), document["strings"]))
    return 0


__all__ = ["CAPABILITY_ID", "LANE", "LANE_ID", "MAX_TARGETS", "UiStringsLane", "parse_key"]


if __name__ == "__main__":
    raise SystemExit(_main())
