#!/usr/bin/env python3
"""b77 / a2: apply sourced handedness and Noah's twelve default-right decisions (collects no data).

The data swarm answers the player list (tools/b77/a2_player_list.py -> reports/a2_PLAYER_LIST.json) in one file:

    {"schema": "b77/a2_answers/v1",
     "answers": [{"id": "main:primary:715", "hand": "Right", "sources": ["https://..."], "note": "..."}, ...]}

An answer needs the list's id, "Left" or "Right", and at least one https source URL. The sole exception is the exact
twelve noah_default_right rows authorized by Noah 2026-10-08, with that decision source recorded explicitly.
Every function refuses a stale list (the record no longer holds the player or the bit the list recorded).

Three routes write the same bit (record byte +0x18, bit 1, mask 0x02; 0 = Left, 1 = Right), nothing else:

  * native, on the disc's resources: apply_to_resource(raw, rows, answers) for main.ROST (outer 5) and for each moment
    team file; bytes change only at the listed hand bytes, and only that bit;
  * Studio, main roster: main_roster_edits(...) is a 2k5_mod_studio_roster_edits/v1 document the build applies with the
    league project's other edits (merge_roster_edits adds it to an existing document);
  * Studio, the 26 authored moments: authored_csv_updates(...) rewrites only the `hand` cell of
    data/nfl2k5_espn25_more_teams/<team>.csv; the compiler (nfl2k5_espn25_more_moments.compile_team) writes it as it
    already does. The 35 retail historic moment files are rewritten by the ESPN25 exact-roster option from
    data/nfl2k5_espn25_moment_rosters/*.csv. Sparse hand cells apply the nine historic default-right rows; blank cells
    keep the template hand. The earlier sourced historic changes still use the native route.

  python3 tools/b77/a2_handedness.py check  --player-list LIST.json --answers ANSWERS.json
  python3 tools/b77/a2_handedness.py repair --player-list LIST.json --answers ANSWERS.json --input-dir DIR --output-dir NEW_DIR

The repair reads main.ROST and the team files by name from --input-dir (v0.5 hashes, or those named in
--accepted-input-hashes), writes fixed copies of only the files an answer changes plus a2_receipt.json.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

LIST_SCHEMA = "b77/a2_player_list/v1"
ANSWERS_SCHEMA = "b77/a2_answers/v1"
HANDS = {"Left": 0, "Right": 1}
MASK = 0x02
WRAPPER = 32
URL = re.compile(r"https://[^\s]+")
DEFAULT_RIGHT = "noah_default_right"
DECISION_SOURCE = "Noah 2026-10-08"
# The twelve leftover LEFT rows Noah authorized, not a general permission to guess.
DEFAULT_RIGHT_ROWS = {
    "main:primary:1196": ("Cameron Johnston", "P"),
    "main:primary:456": ("Jeremy Crawshaw", "P"),
    "main:primary:136": ("Ryan Eckley", "P"),
    "team:h-17-1991-saints-4:31": ("Benny Ricardo", "K"),
    "team:h-30-1986-browns-1:28": ("Matt Bahr", "K"),
    "team:h-22-1975-steelers-1:33": ("Bobby Walden", "P"),
    "team:h-19-1968-jets-4:36": ("Curley Johnson", "P"),
    "team:h-07-1977-cowboys-3:32": ("Danny White", "P"),
    "team:h-13-1969-chiefs-4:35": ("Jerrel Wilson", "P"),
    "team:h-13-1969-chiefs-4:36": ("Jim McCann", "P"),
    "team:h-16-2001-patriots-0:36": ("Lee Johnson", "P"),
    "team:h-23-1999-rams-2:35": ("Rick Tuten", "P"),
}


class HandednessError(ValueError):
    """An answer, a list or a resource that cannot be applied exactly."""


def require(condition, message):
    if not condition:
        raise HandednessError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------------------------------------ the list and answers

def read_player_list(source):
    doc = source if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    require(doc.get("schema") == LIST_SCHEMA and isinstance(doc.get("players"), list), "not a b77 a2 player list")
    rows = {}
    for row in doc["players"]:
        require(row["id"] not in rows, f"duplicate id {row['id']}")
        require(row["hand"] == rr.HANDS[row["hand_bit"]], f"{row['id']}: hand and hand_bit disagree")
        rows[row["id"]] = row
    return doc, rows


def read_answers(source, rows):
    """{id: (bit, sources, note)}; a known id, once, with URLs or the exact authorized Noah decision."""
    doc = source if isinstance(source, dict) else json.loads(Path(source).read_text(encoding="utf-8"))
    require(doc.get("schema") == ANSWERS_SCHEMA and isinstance(doc.get("answers"), list), "not a b77 a2 answers file")
    out = {}
    for item in doc["answers"]:
        ident = item.get("id")
        require(ident in rows, f"unknown player id {ident!r}")
        require(ident not in out, f"two answers for {ident}")
        require(item.get("hand") in HANDS, f"{ident}: hand must be 'Left' or 'Right', not {item.get('hand')!r}")
        sources = item.get("sources")
        if item.get("basis") == DEFAULT_RIGHT:
            require(ident in DEFAULT_RIGHT_ROWS and
                    (rows[ident]["name"], rows[ident]["position"]) == DEFAULT_RIGHT_ROWS[ident] and
                    rows[ident]["hand_bit"] == 0 and item["hand"] == "Right" and
                    item.get("decision_source") == DECISION_SOURCE and sources == [DECISION_SOURCE],
                    f"{ident}: not one of Noah's twelve authorized default-right rows")
        else:
            require("basis" not in item and "decision_source" not in item,
                    f"{ident}: unknown decision basis")
            require(isinstance(sources, list) and sources and all(isinstance(u, str) and URL.fullmatch(u) for u in sources),
                    f"{ident}: every answer needs at least one https source URL")
        for field in ("name", "team", "position"):                     # optional guards against answering another list
            if field in item:
                require(item[field] == rows[ident][field], f"{ident}: {field} {item[field]!r} is not the list's "
                                                           f"{rows[ident][field]!r}")
        out[ident] = (HANDS[item["hand"]], list(sources), item.get("note", ""))
    return out


def changes(rows, answers):
    """The answers that differ from what the list says the game holds: [(row, new bit)]."""
    return [(rows[ident], bit) for ident, (bit, _s, _n) in answers.items() if rows[ident]["hand_bit"] != bit]


# ------------------------------------------------------------------------------------------------ native route

def set_hand_bit(buffer, byte_offset, bit):
    """Set bit 1 of buffer[byte_offset] to `bit` and touch nothing else; True when the byte changed."""
    require(bit in (0, 1), "the hand bit is 0 or 1")
    before = buffer[byte_offset]
    buffer[byte_offset] = (before & ~MASK & 0xFF) | (MASK if bit else 0)
    return buffer[byte_offset] != before


def apply_to_resource(raw, rows, answers):
    """Write the answers for `rows` (all from one ROST resource: main.ROST or one team file) into a copy of `raw`.
    Returns (new bytes, receipt). The resource must still hold the player the list names and the bit it recorded."""
    require(raw[:4] == b"ROST", "not a ROST resource")
    body_length = struct.unpack_from("<I", raw, 4)[0]
    doc = rr.RosterDocument(raw[WRAPPER:WRAPPER + body_length])
    players = {p.offset: p for p in doc.players}
    out = bytearray(raw)
    done = []
    for row in (r for r in rows if r["id"] in answers):       # every answered row is checked, changed or not
        bit = answers[row["id"]][0]
        location = row["record"]
        player = players.get(location["record_offset"])
        require(player is not None, f"{row['id']}: no player record at body offset {location['record_offset']}")
        require((player.first, player.last, player.record.position_name) == (row["first"], row["last"], row["position"]),
                f"{row['id']}: the record holds {player.first} {player.last} ({player.record.position_name}), "
                f"the list says {row['name']} ({row['position']})")
        current = player.record.values["hand"]
        require(current in (row["hand_bit"], bit),                # the list's value, or already the sourced value
                f"{row['id']}: the record's hand is {rr.HANDS[current]}, the list says {row['hand']}")
        at = WRAPPER + location["record_offset"] + rr.FIELD_BY_NAME["hand"].offset
        require(at == location["hand_byte_offset"] and location["mask"] == MASK, f"{row['id']}: hand location")
        if bit == current:
            continue                                            # the disc already holds the sourced value
        before = out[at]
        set_hand_bit(out, at, bit)
        done.append(dict(id=row["id"], name=row["name"], from_hand=row["hand"], to_hand=rr.HANDS[bit], byte_offset=at,
                         before_byte=before, after_byte=out[at]))
    result = bytes(out)
    diff = [i for i in range(len(raw)) if raw[i] != result[i]]
    require(sorted(diff) == sorted(d["byte_offset"] for d in done) and all(raw[i] ^ result[i] == MASK for i in diff),
            "the write changed bytes beyond the hand bits")
    return result, dict(before_sha256=sha(raw), after_sha256=sha(result), changed=done, bytes_changed=len(diff),
                        only_bit_1_of_the_hand_byte=True)


# ------------------------------------------------------------------------------------------------ native repair (files)

SCHEMA = "b77/a2_native_repair/v1"
MAIN_RESOURCE = "main.ROST"
V05_MAIN_ROST_SHA256 = "b3dd88e2b51824b368e78f99f17d7aea7d64b26316c60fee5c0767f31261f501"   # outer 5 of the v0.5 disc
MAX_RESOURCE = 8 * 1024 * 1024


def read_file(path):
    import os
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read(MAX_RESOURCE + 1)


def write_new(path, raw):
    """New files only: an identical existing file is accepted (replay), a different one is never replaced."""
    import os
    path = Path(path)
    if path.exists():
        require(read_file(path) == raw, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def accepted_input_hashes(path, doc):
    """{resource name: set of accepted sha256}: the v0.5 hashes (the list's team files, the v0.5 main roster) plus,
    when given, a manifest {"files": {name: sha256 | {"sha256"|"after_sha256": ...}}} (a stacked input or a receipt)."""
    out = {f["file"]: {f["sha256"]} for f in doc["team_files"]}
    out[MAIN_RESOURCE] = {V05_MAIN_ROST_SHA256}
    if path is not None:
        manifest = json.loads(read_file(path))
        files = manifest.get("files", manifest)
        require(isinstance(files, dict), "accepted input manifest must be an object")
        for name, row in files.items():
            if isinstance(row, dict):
                row = row.get("sha256") or row.get("after_sha256")
            require(isinstance(row, str) and re.fullmatch(r"[0-9a-f]{64}", row), f"{name}: invalid accepted sha256")
            out.setdefault(name, set()).add(row)
    return out


def native_repair(input_dir, output_dir, doc, rows, answers, accepted=None):
    """Write fixed copies of the resources that hold a changed answer; returns the receipt.

    Touches only the hand bit (mask 0x02 of record byte +0x18) of the answered players; refuses a resource whose hash is
    not accepted, a stale record, and any output that exists with other bytes. Resources without a change are not written."""
    input_dir, output_dir = Path(input_dir).resolve(), Path(output_dir).resolve()
    require(input_dir != output_dir, "output directory must differ from the read-only input")
    todo = changes(rows, answers)
    by_resource = {}
    for row, _bit in todo:
        by_resource.setdefault(row["record"]["resource"], []).append(row)
    accepted = accepted or accepted_input_hashes(None, doc)
    results, files = {}, {}
    for name, resource_rows in sorted(by_resource.items()):
        raw = read_file(input_dir / name)
        require(sha(raw) in accepted.get(name, set()), f"unexpected input hash for {name}")
        new, receipt = apply_to_resource(raw, resource_rows, answers)
        again, _ = apply_to_resource(new, resource_rows, answers)
        require(again == new, f"{name}: not idempotent")
        results[name] = new
        files[name] = dict(before_sha256=receipt["before_sha256"], after_sha256=receipt["after_sha256"], size=len(raw),
                           bytes_changed=receipt["bytes_changed"], outside_scope_identical=True,
                           changed=[dict(id=c["id"], name=c["name"], byte_offset=c["byte_offset"], from_hand=c["from_hand"],
                                         to_hand=c["to_hand"], before_byte=c["before_byte"], after_byte=c["after_byte"])
                                    for c in receipt["changed"]])
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in results.items():
        write_new(output_dir / name, raw)
    receipt = dict(schema=SCHEMA, runtime_witnessed=False, idempotent=True, files=files,
                   answers=len(answers), rows_changed=len(todo), resources_written=sorted(results),
                   only_bit_1_of_the_hand_byte=True)
    write_new(output_dir / "a2_receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    return receipt


# ------------------------------------------------------------------------------------------------ Studio routes

def main_roster_edits(rows, answers, *, name="b77 a2 handedness", only_changes=True):
    """A 2k5_mod_studio_roster_edits/v1 document for the main roster rows whose answer differs from the disc
    (only_changes=False: every answered main-roster row, so the document is right on any base roster)."""
    edits = []
    pairs = changes(rows, answers) if only_changes else [(rows[i], b) for i, (b, _s, _n) in answers.items()]
    for row, bit in pairs:
        if row["scope"] != "main_roster_2026":
            continue
        edits.append(dict(pool=row["record"]["pool"], index=row["record"]["index"], first=row["first"], last=row["last"],
                          fields=dict(hand=bit)))
    return dict(schema=rr.EDITS_SCHEMA, name=name, author="b77 a2", edits=edits)


def merge_roster_edits(existing, extra):
    """The league project's edits plus `extra`: an entry for the same (pool, index) gets the hand field added."""
    merged = json.loads(json.dumps(existing))
    index = {(e.get("pool", "primary"), e["index"]): e for e in merged["edits"]}
    for edit in extra["edits"]:
        key = (edit["pool"], edit["index"])
        if key in index:
            require(index[key].get("last") in (None, "", edit["last"]), f"{key}: the project's edit is for another player")
            index[key].setdefault("fields", {}).update(edit["fields"])
        else:
            merged["edits"].append(edit)
    return merged


def authored_csv_updates(rows, answers, data_dir):
    """{path: new text} for the data/nfl2k5_espn25_more_teams/*.csv files an answer changes: only the hand cell moves."""
    wanted = {}
    for row, bit in changes(rows, answers):
        if row["scope"] == "moment_roster" and row.get("team_key"):                    # an authored team-season
            wanted.setdefault(row["team_key"], []).append((row["record"]["index"], row, bit))
    updates = {}
    for key, items in wanted.items():
        path = Path(data_dir) / f"{key}.csv"
        text = path.read_bytes().decode("utf-8")
        lines = text.splitlines(keepends=True)
        header = next(csv.reader([lines[0]]))
        column = header.index("hand")
        for index, row, bit in items:
            cells = next(csv.reader([lines[index + 1]]))
            require((cells[2], cells[3]) == (row["first"], row["last"]) and cells[4] == row["position"],
                    f"{row['id']}: the CSV row {index} holds {cells[2]} {cells[3]}, not {row['name']}")
            cells[column] = rr.HANDS[bit]
            buffer = io.StringIO()
            csv.writer(buffer, lineterminator="").writerow(cells)
            ending = lines[index + 1][len(lines[index + 1].rstrip("\r\n")):]
            lines[index + 1] = buffer.getvalue() + ending
        updates[path] = "".join(lines)
    return updates


# ------------------------------------------------------------------------------------------------ source change

SPEC_PATH = "tools/nfl2k5_espn25_more_moments_spec.json"
EDITS_PATH = "data/nfl2k5_handedness_2026_roster_edits.json"
TEAMS_DIR = "data/nfl2k5_espn25_more_teams"
MANIFEST_PATH = "data/nfl2k5_espn25_unc_bowl.json"


def hand_key(first, last, position):
    return f"{first} {last}|{position}"


def authored_answers(rows, answers):
    """{'First Last|POS': 'Left'|'Right'} for the QB, K and P of the authored moment teams (one hand per person)."""
    out = {}
    for ident, (bit, _sources, _note) in answers.items():
        row = rows[ident]
        if row["scope"] == "moment_roster" and row.get("team_key"):
            key = hand_key(row["first"], row["last"], row["position"])
            require(out.setdefault(key, rr.HANDS[bit]) == rr.HANDS[bit], f"{key}: two answers disagree")
    return dict(sorted(out.items()))


def _json_text(doc):
    return json.dumps(doc, indent=2) + "\n"


def apply_source(root, rows, answers):
    """Write the Studio-side source change under `root` (a repo checkout): the spec's `handedness` block the builder reads,
    the `hand` cells of the authored team CSVs, and the 2026 main-roster edits document. Returns {path: new text}."""
    root = Path(root)
    spec = json.loads((root / SPEC_PATH).read_text(encoding="utf-8"))
    defaults = {i: dict(name=rows[i]["name"], hand="Right", basis=DEFAULT_RIGHT,
                        decision_source=DECISION_SOURCE) for i, (_bit, sources, _note) in answers.items()
                if i in DEFAULT_RIGHT_ROWS and sources == [DECISION_SOURCE]}
    authored = authored_answers(rows, answers)
    authored.update({hand_key(rows[i]["first"], rows[i]["last"], rows[i]["position"]): "Right" for i in defaults})
    spec["handedness"] = dict(
        source="data/HANDEDNESS_FINAL.json: tiers A and B are sourced; noah_default_right is Noah 2026-10-08's "
               "decision for twelve leftover LEFT rows. QB throwing hand and K/P kicking foot.",
        answers=dict(sorted(authored.items())), decisions=defaults)
    out = {root / SPEC_PATH: _json_text(spec)}
    out.update({Path(path): text for path, text in authored_csv_updates(rows, answers, root / TEAMS_DIR).items()})
    edits = main_roster_edits(rows, answers, only_changes=False)
    edits["handedness_decisions"] = {i: d for i, d in defaults.items() if rows[i]["scope"] == "main_roster_2026"}
    out[root / EDITS_PATH] = _json_text(edits)
    # Historic teams have sparse hand cells. Blank cells retain the template bit.
    for resource in sorted({rows[i]["record"]["resource"] for i in defaults if rows[i]["scope"] == "moment_roster"}):
        path = root / "data/nfl2k5_espn25_moment_rosters" / (resource[:-4] + ".csv")
        reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
        fields = list(reader.fieldnames)
        cells = list(reader)
        if "hand" not in fields:
            fields.append("hand")
        for i in defaults:
            row = rows[i]
            if row["record"]["resource"] != resource:
                continue
            cell = cells[row["record"]["index"]]
            require((cell["first"], cell["last"], cell["position"]) ==
                    (row["first"], row["last"], row["position"]), f"{i}: historic CSV identity changed")
            cell["hand"] = "Right"
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(cells)
        out[path] = buffer.getvalue()
    return out


# ------------------------------------------------------------------------------------------------ command line

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate an answers file against the list and count what would change")
    check.add_argument("--player-list", required=True, type=Path)
    check.add_argument("--answers", required=True, type=Path)
    fix = sub.add_parser("repair", help="write fixed copies of the roster resources an answers file changes")
    fix.add_argument("--player-list", required=True, type=Path)
    fix.add_argument("--answers", required=True, type=Path)
    fix.add_argument("--input-dir", required=True, type=Path, help="folder holding main.ROST and the team files, by name")
    fix.add_argument("--output-dir", required=True, type=Path)
    fix.add_argument("--accepted-input-hashes", type=Path)
    src = sub.add_parser("apply-source", help="write the Studio-side source change (spec, team CSVs, 2026 edits) into a checkout")
    src.add_argument("--player-list", required=True, type=Path)
    src.add_argument("--answers", required=True, type=Path)
    src.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    doc, rows = read_player_list(args.player_list)
    answers = read_answers(args.answers, rows)
    if args.command == "apply-source":
        files = apply_source(args.root, rows, answers)
        for path, text in sorted(files.items()):
            old = path.read_bytes().decode("utf-8") if path.exists() else None
            if old != text:
                path.write_bytes(text.encode("utf-8"))
                print("wrote", path)
        return 0
    if args.command == "repair":
        accepted = accepted_input_hashes(args.accepted_input_hashes, doc)
        receipt = native_repair(args.input_dir, args.output_dir, doc, rows, answers, accepted)
        print(json.dumps(dict(status="DONE", output=str(args.output_dir), rows_changed=receipt["rows_changed"],
                              resources_written=receipt["resources_written"]), sort_keys=True))
        return 0
    todo = changes(rows, answers)
    print(json.dumps(dict(answers=len(answers), unchanged=len(answers) - len(todo), would_change=len(todo),
                          by_scope={s: sum(1 for r, _b in todo if r["scope"] == s)
                                    for s in sorted({r["scope"] for r, _b in todo})}), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
