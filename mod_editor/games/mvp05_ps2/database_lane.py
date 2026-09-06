"""The CSV tables: rosters, team identity and tuning, edited a cell at a time and written back.

MVP Baseball 2005 ships its players, teams and tuning as text
(:mod:`mod_editor.games._formats.ea_csv_db`) inside EA ``BIG`` archives
(:mod:`~mod_editor.games._formats.ea_big`).  A cell edit changes one line of
one table; the table is re-packed with RefPack when the disc packed it and put
back **inside the slot the entry already owns**; the archive goes back inside
its own ISO9660 extent; the image keeps its length.  Every refusal is one
sentence naming the fix -- a value with a comma, a table that no longer fits
its slot once re-packed (the slot is the entry's own stored size plus at most
three bytes [M], so a table that grows can only go back if it packs at least
as well as EA packed it; the encoder beat EA's on every table measured [M]).

One class, three rows:

* ``rosters.database_tables`` -- every table of ``DATABASE.BIG`` (players,
  pitchers, stats, rosters, teams), on the Names, Numbers & Faces page;
* ``identity.team_tables`` -- the four team tables, on Text & Team Identity;
* ``playbooks.tuning_tables`` -- ``PROGRESS``, ``ROOKIE``, ``SCHEDULE`` and the
  two audio event-table archives, on the page baseball has no playbook for.

**Evidence tags.**  **[M]** measured on the retail disc.  Retail-free: the
catalogue a user builds carries their own disc's values; nothing here does.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from mod_editor.games._formats import ea_big, ea_csv_db
from mod_editor.games.contract import (
    Catalogue, DeclaredRange, Edit, Field, Plan, Receipt, Refusal, Target, Verdict, require,
)

from . import containers, disc_write

MAX_TARGETS = 3000
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def _key(archive: str, table: str, line: int) -> str:
    return f"{archive}!{table}#{line}"


def parse_key(key: str) -> Tuple[str, str, int]:
    match = re.match(r"^([^!]+)!([^#]+)#(\d+)$", str(key))
    if match is None:
        raise Refusal(f"{key!r} does not name a table row: a key is "
                      f"<archive>!<table>#<line>, as the catalogue writes it.")
    return match.group(1), match.group(2), int(match.group(3))


class CsvTableLane:
    """A cell-at-a-time writer over the CSV tables of a set of archives."""

    fixed_allocation = True

    def __init__(self, *, lane_id: str, capability_id: str, surface: str, page: str, title: str,
                 archives: Sequence[str], tables: Optional[Mapping[str, Sequence[str]]] = None,
                 validators: Sequence[str], classification: str = "offline-writer-proved",
                 max_targets: int = MAX_TARGETS) -> None:
        self.lane_id = lane_id
        self.capability_id = capability_id
        self.surface = surface
        self.page = page
        self.title = title
        self.archives = tuple(archives)
        self.tables = {k: tuple(v) for k, v in (tables or {}).items()}
        self.validators = tuple(validators)
        self.classification = classification
        self.recipe_schema = f"mvp05_ps2_{lane_id.replace('.', '_')}_recipe/v1"
        self.catalogue_schema = f"mvp05_ps2_{lane_id.replace('.', '_')}_catalogue/v1"
        self.write_schema = f"mvp05_ps2_{lane_id.replace('.', '_')}_write/v1"
        self.max_targets = max_targets

    # -- catalogue -----------------------------------------------------------

    def _wanted(self, archive: str, table: str) -> bool:
        allowed = self.tables.get(archive)
        return allowed is None or table in allowed

    def build_catalogue(self, source: Path, *,
                        progress: Optional[Callable[[str], None]] = None) -> Catalogue:
        targets: List[Target] = []
        tables: List[Dict[str, Any]] = []
        refusals: List[Dict[str, str]] = []
        total_rows = 0
        with containers.Disc(Path(source)) as disc:
            for archive_name in self.archives:
                try:
                    entry = disc.find(archive_name)
                    archive = disc.archive(entry)
                except containers.DiscError as exc:
                    refusals.append({"where": archive_name, "sentence": str(exc)})
                    continue
                for row in archive.entries:
                    if row.size == 0 or not self._wanted(archive_name, row.name):
                        continue
                    if archive.entry_format(row.index) != ea_big.FORMAT_TEXT:
                        continue
                    if progress is not None:
                        progress(f"{archive_name}!{row.name}…")
                    try:
                        table = ea_csv_db.parse_table(archive.member(row.index), row.name)
                    except (ea_big.BigError, ea_csv_db.CsvError) as exc:
                        refusals.append({"where": f"{archive_name}!{row.name}",
                                         "sentence": str(exc)})
                        continue
                    columns = table.columns()
                    lines = table.data_line_numbers()
                    total_rows += len(lines)
                    summary = {
                        "archive": archive_name, "path": entry.path, "table": row.name,
                        "entry": row.index, "rows": len(lines), "columns": len(columns),
                        "column_names": columns, "indexed": table.indexed,
                        "plain_bytes": len(table.render()), "stored_bytes": row.size,
                        "slot_bytes": archive.slot_bytes(row.index),
                        "packed": archive.is_compressed(row.index),
                        "rows_listed": 0,
                    }
                    keys = self._field_keys(columns)
                    for line in lines:
                        if len(targets) >= self.max_targets:
                            break
                        values = table.values(line)
                        targets.append(self._target(summary, line, table.row_id(line),
                                                    keys, values))
                        summary["rows_listed"] += 1
                    tables.append(summary)
        document = {
            "schema": self.catalogue_schema, "source": str(source),
            "archives": list(self.archives), "tables": tables, "rows": total_rows,
            "targets_listed": len(targets), "targets_cap": self.max_targets,
            "refusals": refusals, "runtime_note": disc_write.NOT_BOOTED,
            "slot_rule": ("A re-packed table must fit the entry's own slot -- its stored size "
                          "plus at most three bytes on this disc -- or the build refuses "
                          "naming the byte count."),
        }
        return Catalogue(self.catalogue_schema, self.lane_id, str(source), tuple(targets),
                         document)

    @staticmethod
    def _field_keys(columns: Sequence[str]) -> List[str]:
        keys: List[str] = []
        for number, name in enumerate(columns):
            key = re.sub(r"[^A-Za-z0-9_]", "_", name) or f"col{number}"
            if key in keys or key[0].isdigit():
                key = f"col{number}_{key}"
            keys.append(key)
        return keys

    def _target(self, summary: Mapping[str, Any], line: int, row_id: str,
                keys: Sequence[str], values: Sequence[str]) -> Target:
        columns = summary["column_names"]
        # A plain CSV may carry an empty column name (the tuning curves do [M]);
        # the key is never empty, so it stands in for the label.
        fields = tuple(
            Field(key, "text", name or key,
                  f"column {number} ({'number' if _NUMBER.match(value or '') else 'text'}); "
                  f"currently {value!r}. Blank keeps it.")
            for number, (key, name, value) in enumerate(zip(keys, columns, values)))
        preview = ", ".join(v for v in values[:2] if v) or row_id
        return Target(
            key=_key(summary["archive"], summary["table"], line),
            label=f"{summary['table']} · {preview}",
            detail=f"row {row_id} · {len(columns)} column(s) · line {line}",
            budget=("The table goes back inside the slot its entry already owns; a table "
                    "that no longer fits once re-packed is refused naming the byte count."),
            searchable=f"{summary['table']} {row_id} {' '.join(values[:4])}",
            raw={"archive": summary["archive"], "path": summary["path"],
                 "table": summary["table"], "line": line, "row_id": row_id,
                 "keys": list(keys), "columns": list(columns), "values": list(values),
                 "packed": summary["packed"], "slot_bytes": summary["slot_bytes"],
                 "stored_bytes": summary["stored_bytes"]},
            fields=fields,
        )

    # -- the edit rule ---------------------------------------------------------

    def check_edit(self, target: Target, values: Mapping[str, Any]) -> Optional[str]:
        keys = list(target.raw.get("keys", []))
        current = list(target.raw.get("values", []))
        unknown = sorted(set(values) - set(keys))
        if unknown:
            return (f"{target.key}: {', '.join(unknown)} is not a column of this table; the "
                    f"columns are {', '.join(keys[:8])}{'…' if len(keys) > 8 else ''}.")
        for key, value in values.items():
            text = str(value)
            if "," in text:
                return f"{target.key}: {key} cannot contain a comma; it would become another field."
            if "\r" in text or "\n" in text:
                return f"{target.key}: {key} cannot contain a line break; it would become another row."
            try:
                text.encode("latin-1")
            except UnicodeEncodeError:
                return f"{target.key}: {key} must be Latin-1 text; the disc's tables are single-byte."
            was = current[keys.index(key)] if key in keys and keys.index(key) < len(current) else ""
            if _NUMBER.match(was) and text != "" and not _NUMBER.match(text):
                return (f"{target.key}: {key} holds the number {was} and {text!r} is not one; "
                        f"keep the column's kind.")
        return None

    def compose_recipe(self, edits: Sequence[Edit]) -> Mapping[str, Any]:
        rows = []
        for edit in edits:
            row: Dict[str, Any] = {"row": edit.target_key, "cells": dict(edit.values)}
            if edit.note:
                row["note"] = edit.note
            rows.append(row)
        return {"schema": self.recipe_schema, "edits": rows}

    def _entries(self, recipe: Mapping[str, Any]) -> List[Dict[str, Any]]:
        require(isinstance(recipe, Mapping) and recipe.get("schema") == self.recipe_schema,
                f"recipe schema is {recipe.get('schema') if isinstance(recipe, Mapping) else recipe!r}, "
                f"expected {self.recipe_schema}")
        rows = recipe.get("edits")
        require(isinstance(rows, list) and rows,
                "a recipe must carry a non-empty 'edits' list; choose at least one row to edit")
        out = []
        for number, row in enumerate(rows):
            require(isinstance(row, Mapping) and isinstance(row.get("row"), str),
                    f"edit {number} must name the row it edits")
            require(set(row) <= {"row", "cells", "note"}, f"edit {number} carries unknown keys")
            cells = row.get("cells")
            require(isinstance(cells, Mapping) and cells,
                    f"edit {number} ({row['row']}) names no cell to change")
            out.append({"row": row["row"], "cells": {str(k): str(v) for k, v in cells.items()},
                        "note": row.get("note")})
        return out

    # -- compose ---------------------------------------------------------------

    def _compose(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue
                 ) -> Dict[str, Any]:
        entries = self._entries(recipe)
        grouped: Dict[Tuple[str, str], List[Tuple[Dict[str, Any], Target]]] = {}
        for entry in entries:
            target = catalogue.target(entry["row"])
            problem = self.check_edit(target, entry["cells"])
            require(problem is None, str(problem))
            archive_name, table_name, _line = parse_key(entry["row"])
            grouped.setdefault((archive_name, table_name), []).append((entry, target))
        written: Dict[str, bytes] = {}
        paths: Dict[str, str] = {}
        tables_out: List[Dict[str, Any]] = []
        cells_out: List[Dict[str, Any]] = []
        with containers.Disc(Path(source)) as disc:
            by_archive: Dict[str, List[Tuple[str, List[Tuple[Dict[str, Any], Target]]]]] = {}
            for (archive_name, table_name), items in grouped.items():
                by_archive.setdefault(archive_name, []).append((table_name, items))
            for archive_name, table_groups in by_archive.items():
                iso_entry = disc.find(archive_name)
                archive = disc.archive(iso_entry)
                current_bytes: Optional[bytes] = None
                for table_name, items in table_groups:
                    table = ea_csv_db.parse_table(archive.member(table_name), table_name)
                    keys = self._field_keys(table.columns())
                    for entry, target in items:
                        _a, _t, line = parse_key(entry["row"])
                        require(line in table.data_line_numbers(),
                                f"{entry['row']}: line {line} is not a data row of {table_name} "
                                f"on this image; rebuild the catalogue.")
                        for key, value in entry["cells"].items():
                            require(key in keys, f"{entry['row']}: {key} is not a column of {table_name}.")
                            column = keys.index(key)
                            before = table.cell(line, column)
                            table.set_cell(line, column, value)
                            cells_out.append({"row": entry["row"], "column": table.columns()[column],
                                              "line": line, "before": before, "after": value})
                    rendered = table.render()
                    try:
                        result = ea_big.rewrite_entry(archive, table_name, rendered)
                    except ea_big.BigError as exc:
                        raise Refusal(str(exc)) from exc
                    tables_out.append({"archive": archive_name, "path": iso_entry.path,
                                       "table": table_name, **result.as_dict(),
                                       "plain_sha256": disc_write.sha256(rendered)})
                    current_bytes = result.archive
                    archive = ea_big.parse_big(current_bytes, name=iso_entry.path)
                assert current_bytes is not None
                written[archive_name] = current_bytes
                paths[archive_name] = iso_entry.path
        return {"edits": entries, "tables": tables_out, "cells": cells_out,
                "written": written, "paths": paths}

    def plan(self, source: Path, recipe: Mapping[str, Any], catalogue: Catalogue) -> Plan:
        composed = self._compose(Path(source), recipe, catalogue)
        replacements = {composed["paths"][name]: blob for name, blob in composed["written"].items()}
        ranges = disc_write.plan_ranges(Path(source), replacements)
        return Plan(self.lane_id, tuple(entry["row"] for entry in composed["edits"]), ranges, {
            "schema": self.recipe_schema, "tables": composed["tables"], "cells": composed["cells"],
            "archives": [{"name": name, "path": composed["paths"][name], "bytes": len(blob)}
                         for name, blob in sorted(composed["written"].items())],
            "declared_bytes": sum(item.length for item in ranges),
            "runtime_note": disc_write.NOT_BOOTED,
        })

    def build(self, source: Path, destination: Path, recipe: Mapping[str, Any],
              catalogue: Catalogue, *, work_dir: Optional[Path] = None) -> Receipt:
        source, destination = Path(source), Path(destination)
        disc_write.check_destination(source, destination)
        composed = self._compose(source, recipe, catalogue)
        replacements = {composed["paths"][name]: blob for name, blob in composed["written"].items()}
        report, ranges = disc_write.replace_files(source, destination, replacements)
        document = {
            "schema": self.write_schema, "source": str(source), "destination": str(destination),
            "edits": composed["edits"], "tables": composed["tables"], "cells": composed["cells"],
            "archives": [{"name": name, "path": composed["paths"][name], "bytes": len(blob),
                          "sha256": disc_write.sha256(blob)}
                         for name, blob in sorted(composed["written"].items())],
            "iso_report": report, "runtime_note": disc_write.NOT_BOOTED,
        }
        return Receipt(self.write_schema, self.lane_id, str(source), str(destination), ranges,
                       document)

    # -- verify: re-derive everything from the two images ---------------------

    def verify(self, source: Path, destination: Path, receipt: Receipt) -> Verdict:
        source, destination = Path(source), Path(destination)
        problem = disc_write.verify_image(source, destination, receipt.document.get("iso_report"))
        if problem:
            return Verdict(False, f"Verification failed {problem}")
        edits = receipt.document.get("edits") or []
        if not edits:
            return Verdict(False, "Verification failed: the receipt declares no edits.")
        edited: Dict[Tuple[str, str], Dict[int, Dict[str, str]]] = {}
        for entry in edits:
            archive_name, table_name, line = parse_key(entry["row"])
            edited.setdefault((archive_name, table_name), {}).setdefault(line, {}).update(entry["cells"])
        archives = sorted({name for name, _table in edited})
        checked_entries = 0
        checked_cells = 0
        try:
            with containers.Disc(source) as before, containers.Disc(destination) as after:
                for archive_name in archives:
                    old = before.archive(before.find(archive_name))
                    new = after.archive(after.find(archive_name))
                    if len(old) != len(new) or old.length != new.length:
                        return Verdict(False, f"Verification failed: {archive_name} changed shape "
                                              f"({len(old)} -> {len(new)} entries).")
                    touched = {table for (arc, table) in edited if arc == archive_name}
                    for row in old.entries:
                        fresh = new.entry(row.index)
                        if row.name != fresh.name or row.offset != fresh.offset:
                            return Verdict(False, f"Verification failed: {archive_name} entry "
                                                  f"{row.index} moved or was renamed.")
                        if row.name not in touched:
                            if row.size != fresh.size or old.stored(row.index) != new.stored(row.index):
                                return Verdict(False, f"Verification failed: {archive_name}!{row.name} "
                                                      f"was not part of the recipe and changed.")
                            checked_entries += 1
                            continue
                        if old.is_compressed(row.index) != new.is_compressed(row.index):
                            return Verdict(False, f"Verification failed: {archive_name}!{row.name} "
                                                  f"changed packing.")
                        if fresh.size > old.slot_bytes(row.index):
                            return Verdict(False, f"Verification failed: {archive_name}!{row.name} "
                                                  f"outgrew its slot.")
                        old_table = ea_csv_db.parse_table(old.member(row.index), row.name)
                        new_table = ea_csv_db.parse_table(new.member(row.index), row.name)
                        if len(old_table.lines) != len(new_table.lines):
                            return Verdict(False, f"Verification failed: {archive_name}!{row.name} "
                                                  f"changed its line count.")
                        cells = edited[(archive_name, row.name)]
                        keys = self._field_keys(old_table.columns())
                        for number, (a, b) in enumerate(zip(old_table.lines, new_table.lines)):
                            if number not in cells:
                                if a.render() != b.render():
                                    return Verdict(False, f"Verification failed: {archive_name}!"
                                                          f"{row.name} line {number} changed and was "
                                                          f"not in the recipe.")
                                continue
                            wanted = cells[number]
                            for column, key in enumerate(keys):
                                expected = wanted.get(key, old_table.cell(number, column))
                                if new_table.cell(number, column) != expected:
                                    return Verdict(False, f"Verification failed: {archive_name}!"
                                                          f"{row.name} line {number} column {key} holds "
                                                          f"{new_table.cell(number, column)!r}, not "
                                                          f"{expected!r}.")
                                checked_cells += 1
                        checked_entries += 1
        except (containers.DiscError, ea_big.BigError, ea_csv_db.CsvError, Refusal) as exc:
            return Verdict(False, f"Verification failed: {exc}")
        return Verdict(True, f"{len(archives)} archive(s) re-read from both images: {checked_entries} "
                             f"entr(ies) compared, {checked_cells} cell(s) match the recipe, every "
                             f"other line byte-identical, and the image-level ranges hold.",
                       {"result": "PASS", "archives": archives, "entries": checked_entries,
                        "cells": checked_cells})

    # -- what CI proves it on --------------------------------------------------

    def synthetic_source(self, work_dir: Path) -> Path:
        path = Path(work_dir) / f"mvp05-ps2-{self.lane_id.replace('.', '-')}-synthetic.iso"
        if not path.exists():
            path.write_bytes(containers.build_synthetic_disc())
        return path

    def conformance_edits(self, catalogue: Catalogue) -> Tuple[Edit, ...]:
        for target in catalogue.targets:
            keys = target.raw.get("keys") or []
            values = target.raw.get("values") or []
            for key, value in zip(keys, values):
                if not _NUMBER.match(value or "") and value:
                    return (Edit(target.key, {key: "Edited"}, note="conformance: one text cell"),)
            for key, value in zip(keys, values):
                if _NUMBER.match(value or "") and "." not in value:
                    return (Edit(target.key, {key: str(int(value) + 1)},
                                 note="conformance: one number cell"),)
        raise Refusal("this catalogue lists no editable row, so there is no edit to prove")


VALIDATORS = ("tools/validate_mvp05_ps2_tables.sh", "tools/validate_mvp05_ps2_tables.bat")

ROSTER_LANE = CsvTableLane(
    lane_id="rosters.database_tables", capability_id="mvp05ps2.rosters.database_tables",
    surface="players_rosters", page="rosters",
    title="Players, pitchers, rosters and stats: the 18 database tables",
    archives=(containers.DATABASE_ARCHIVE,), validators=VALIDATORS)

IDENTITY_LANE = CsvTableLane(
    lane_id="identity.team_tables", capability_id="mvp05ps2.identity.team_tables",
    surface="colors", page="identity", title="Teams, organisations and managers",
    archives=(containers.DATABASE_ARCHIVE,),
    tables={containers.DATABASE_ARCHIVE: containers.IDENTITY_TABLES}, validators=VALIDATORS)

TUNING_LANE = CsvTableLane(
    lane_id="playbooks.tuning_tables", capability_id="mvp05ps2.playbooks.tuning_tables",
    surface="scripts_config", page="playbooks",
    title="Progression, contracts, draft classes, schedules and audio event tables",
    archives=containers.TUNING_ARCHIVES, validators=VALIDATORS)


def _main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mod_editor.games.mvp05_ps2.database_lane",
        description="Catalogue the CSV tables of an MVP Baseball 2005 (PS2) disc. Read-only.")
    parser.add_argument("--source")
    parser.add_argument("--lane", default="rosters", choices=("rosters", "identity", "tuning"))
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    lane = {"rosters": ROSTER_LANE, "identity": IDENTITY_LANE, "tuning": TUNING_LANE}[arguments.lane]
    if not arguments.selftest and not arguments.source:
        parser.error("give --source a disc image, or --selftest")
    try:
        if arguments.selftest:
            import tempfile

            with tempfile.TemporaryDirectory() as room:
                src = lane.synthetic_source(Path(room))
                catalogue = lane.build_catalogue(src)
                edits = lane.conformance_edits(catalogue)
                recipe = lane.compose_recipe(edits)
                dest = Path(room) / "out.iso"
                receipt = lane.build(src, dest, recipe, catalogue)
                verdict = lane.verify(src, dest, receipt)
                require(verdict.passed, verdict.summary)
                print(f"SELFTEST ok: {verdict.summary}")
                return 0
        catalogue = lane.build_catalogue(Path(arguments.source),
                                         progress=lambda line: print(line, file=sys.stderr))
    except Refusal as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    document = dict(catalogue.document)
    if arguments.out:
        Path(arguments.out).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    print("TABLES tables=%d rows=%d listed=%d" % (len(document["tables"]), document["rows"],
                                                  document["targets_listed"]))
    return 0


__all__ = ["CsvTableLane", "IDENTITY_LANE", "MAX_TARGETS", "ROSTER_LANE", "TUNING_LANE",
           "VALIDATORS", "parse_key"]


if __name__ == "__main__":
    raise SystemExit(_main())
