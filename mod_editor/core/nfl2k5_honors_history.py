"""Sourced award history for the Player Card honors page (job F5, beta 77): honors into the career-stat pool.

The honors page (``nfl2k5_honors``) reads one history field per honor from a player's career-stat stream: field 96
MVP, 97 OPOY, 98 DPOY, 99 OROY, 100 DROY, 101 Super Bowl champion, 102 Super Bowl MVP, 103 Pro Bowl, 104 All-Pro,
105 rushing title; value 1 in the season slot the honor was won, regular-season class. The game adds new seasons'
winners itself; this module writes the real history of the players already on a roster.

Data: ``data/nfl2k5_honors_2026.json`` (schema ``nfl2k5_honors_history/v1``): players pinned by pool, index, name and
birth date, each honor with its season and a source key; every source is listed with its URL (a fixed Wikipedia
revision or the nflverse release file), the SHA-256 of the exact text read and the counting rule. A user edit is the
same document (or a CSV through ``tools/nfl2k5_honors.py``).

Slots follow the roster's own convention: a player's season ``y`` lives in slot ``years_pro - (base_year - y)``
(``years_pro`` = ``player+0x24`` bits 8..12, the slot of the current season), so the words stay consistent whether
years pro counts the rookie season as 0 (v0.5) or 1 (beta 77 F12): F12's slot shift moves these words with the
stats. Only completed seasons (slot below years pro) are written. Existing words are never changed; a word already
present (same field, slot, regular class, live) is skipped, so applying the same data twice changes nothing.

The pool is rewritten through ``nfl2k5_franchise_history.repack`` (ownership, capacity and read-back checks); bytes
outside the pool, the ``+0x2C`` stream pointers and the used count are untouched.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
from typing import Iterable, Mapping

from . import nfl2k5_franchise_history as fh
from . import nfl2k5_roster_records as records
from . import nfl2k5_save_rost as sr

SCHEMA = "nfl2k5_honors_history/v1"
FIELD0 = 96
HONORS = ("mvp", "opoy", "dpoy", "oroy", "droy", "super_bowl", "super_bowl_mvp", "pro_bowl", "all_pro",
          "rushing_title")
FIELDS = {name: FIELD0 + i for i, name in enumerate(HONORS)}
DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "nfl2k5_honors_2026.json"
CSV_COLUMNS = ("pool", "index", "first", "last", "birth_date", "season", "honor", "source")
LIVE_REGULAR = 0x70000000          # deleted, postseason or folded words are not live regular-season words


class HonorsHistoryError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise HonorsHistoryError(message)


def word(field: int, slot: int, value: int = 1) -> int:
    return (value & 0xFFFF) | (field << 16) | (slot << 23)


def load(path: Path | str = DEFAULT_DATA) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: Mapping) -> None:
    _require(data.get("schema") == SCHEMA, "unknown honors history schema")
    year = data.get("base_year")
    _require(type(year) is int and 1901 <= year <= 2100, "invalid base year")
    sources = data.get("sources", {})
    _require(isinstance(sources, dict), "sources must be a mapping")
    for key, pin in sources.items():
        _require(isinstance(pin, dict) and pin.get("url") and re.fullmatch("[0-9a-f]{64}", pin.get("sha256", "")),
                 f"source {key} needs a URL and the SHA-256 of the text read")
    seen = set()
    for p in data.get("players", []):
        _require(p.get("pool") in ("primary", "secondary") and type(p.get("index")) is int and p["index"] >= 0,
                 "each player needs a pool and an index")
        _require(bool(str(p.get("first", "")).strip()) and bool(str(p.get("last", "")).strip()), "each player needs a name")
        _require(p.get("birth_date") is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["birth_date"]), "bad birth date")
        for h in p.get("honors", []):
            _require(h.get("honor") in FIELDS, f"unknown honor {h.get('honor')!r}")
            _require(type(h.get("season")) is int and 1920 <= h["season"] < year, "honors are for completed seasons")
            _require(h.get("source") in sources, f"honor source {h.get('source')!r} is not listed")
            key = (p["pool"], p["index"], h["honor"], h["season"])
            _require(key not in seen, f"duplicate honor {key}")
            seen.add(key)


def _decode(body: bytes, base_year: int) -> sr.SaveRost:
    _require(len(body) == records.BODY_SIZE, "honors history needs the bare 0x90F60 disc ROST body")
    try:
        document = sr.decode(body, preamble=0, reference_year=base_year)
    except sr.SaveRostError as exc:
        raise HonorsHistoryError(str(exc)) from exc
    _require(document.layout.version == 17, "honors history accepts disc version 17 only")
    _require(document.pool is not None, "history pool pointer is missing")
    return document


def _years_pro(body: bytes, player) -> int:
    return (struct.unpack_from("<I", body, player.offset + 0x24)[0] >> 8) & 31


def plan(body: bytes, data: Mapping, *, strict: bool = True) -> tuple[dict, dict]:
    """-> ({player key: new words to add}, receipt). A player whose record is missing or whose name or birth date
    differs is refused (strict, user data) or skipped and listed (the built-in data on a roster it was not made for)."""

    validate(data)
    year = data["base_year"]
    document = _decode(body, year)
    additions, rows, skipped, present, mismatched = {}, [], [], 0, []
    for p in data.get("players", []):
        player = document.by_key.get((p["pool"], p["index"]))
        born = player.record.birth_date.isoformat() if player is not None and player.record.birth_date else None
        same = (player is not None
                and " ".join(player.first.split()).casefold() == " ".join(p["first"].split()).casefold()
                and " ".join(player.last.split()).casefold() == " ".join(p["last"].split()).casefold()
                and (p.get("birth_date") is None or born == p["birth_date"]))
        if not same:
            message = (f"no {p['pool']} player {p['index']}" if player is None else
                       f"player {p['pool']}:{p['index']} is {player.first} {player.last} ({born}), not {p['first']} {p['last']}")
            _require(not strict, message)
            mismatched.append({"index": p["index"], "expected": f"{p['first']} {p['last']}", "reason": message})
            continue
        count = _years_pro(body, player)
        words = document.history_words[player.key]
        live = {(w >> 16 & 0x7F, w >> 23 & 31) for w in words if not w & LIVE_REGULAR}
        for h in sorted(p.get("honors", []), key=lambda h: (h["season"], h["honor"])):
            slot = count - (year - h["season"])
            field = FIELDS[h["honor"]]
            if not 0 <= slot < count:
                skipped.append({"player": f"{player.first} {player.last}", "index": player.index, "honor": h["honor"],
                                "season": h["season"], "reason": f"no completed season slot (years pro {count})"})
                continue
            if (field, slot) in live:
                present += 1
                continue
            additions.setdefault(player.key, []).append(word(field, slot))
            live.add((field, slot))
            rows.append({"index": player.index, "player": f"{player.first} {player.last}", "honor": h["honor"],
                         "season": h["season"], "slot": slot, "field": field, "source": h["source"]})
    receipt = {"schema": SCHEMA, "base_year": year, "added": len(rows), "already_present": present,
               "skipped": skipped, "players": len(additions), "identity_mismatches": mismatched, "rows": rows}
    return additions, receipt


def apply_body(body: bytes, data: Mapping, *, strict: bool = True) -> tuple[bytes, dict]:
    """Return a new ROST body with the honors inserted at each player's stream head (as the game inserts)."""

    additions, receipt = plan(body, data, strict=strict)
    document = _decode(body, data["base_year"])
    if not additions:
        return bytes(body), {**receipt, "changed": False, "source_body_sha256": hashlib.sha256(body).hexdigest(),
                             "output_body_sha256": hashlib.sha256(body).hexdigest()}
    replacements = {}
    for key, new in additions.items():
        old = list(document.history_words[key])
        if old:
            replacements[key] = sorted(new, key=lambda w: (w >> 23 & 31, w >> 16 & 0x7F)) + old
        else:
            new = sorted(new, key=lambda w: (w >> 23 & 31, w >> 16 & 0x7F))
            new[-1] |= 0x80000000
            replacements[key] = new
    result, pool = fh.repack(body, document, replacements)
    check = _decode(result, data["base_year"])
    for key, words in replacements.items():
        _require(check.history_words[key] == tuple(words), "honors read-back differs")
    allowed = bytearray(len(body))
    allowed[document.pool:document.pool + max(pool["used_after"], pool["used_before"]) * 4] = b"\1" * (
        max(pool["used_after"], pool["used_before"]) * 4)
    root = document.layout.root
    allowed[root + 0x40:root + 0x44] = b"\1" * 4
    for player in document.players:
        allowed[player.offset + 0x2C:player.offset + 0x30] = b"\1" * 4
    _require(all(a == b or allowed[i] for i, (a, b) in enumerate(zip(body, result))), "write outside the pool")
    return result, {**receipt, **pool, "changed": True, "source_body_sha256": hashlib.sha256(body).hexdigest(),
                    "output_body_sha256": hashlib.sha256(result).hexdigest()}


def read_body(body: bytes, base_year: int) -> list[dict]:
    """Every live regular-season honor word in a ROST body, as (player, season, honor) rows."""

    document = _decode(body, base_year)
    honors = {v: k for k, v in FIELDS.items()}
    out = []
    for player in document.players:
        count = _years_pro(body, player)
        for w in document.history_words[player.key]:
            field, slot = w >> 16 & 0x7F, w >> 23 & 31
            if field in honors and not w & 0x30000000:
                out.append({"pool": player.pool, "index": player.index, "first": player.first, "last": player.last,
                            "birth_date": player.record.birth_date.isoformat() if player.record.birth_date else "",
                            "season": base_year - count + slot, "honor": honors[field], "value": w & 0xFFFF,
                            "folded": bool(w & 0x40000000)})
    return out


def to_csv(rows: Iterable[Mapping]) -> str:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({**r, "source": r.get("source", "roster")})
    return out.getvalue()


def from_csv(text: str, base_year: int, sources: Mapping[str, Mapping]) -> dict:
    """A user CSV (one honor per row) as a data document; every row's source must be listed in ``sources``."""

    players = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        key = (row["pool"].strip(), int(row["index"]))
        p = players.setdefault(key, {"pool": key[0], "index": key[1], "first": row["first"].strip(),
                                     "last": row["last"].strip(), "birth_date": row["birth_date"].strip() or None,
                                     "honors": []})
        p["honors"].append({"season": int(row["season"]), "honor": row["honor"].strip(), "source": row["source"].strip()})
    data = {"schema": SCHEMA, "base_year": base_year, "sources": dict(sources), "players": list(players.values())}
    validate(data)
    return data


def resolve(spec: str, base_year: int = 2026) -> dict:
    """The data document a build setting names: "builtin" (the shipped data), a .json document or a .csv export."""

    _require(isinstance(spec, str) and spec.strip(), "no honors history selected")
    if spec.strip() == "builtin":
        data = load(DEFAULT_DATA)
    else:
        path = Path(spec).expanduser()
        _require(path.is_file(), f"honors history file not found: {path}")
        if path.suffix.lower() == ".csv":
            text = path.read_bytes().decode("utf-8-sig")
            pin = {"url": path.resolve().as_uri(), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "title": "user honors CSV"}
            sources = dict(load(DEFAULT_DATA)["sources"])
            sources.setdefault("user", pin)
            data = from_csv(text, base_year, sources)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            validate(data)
    _require(data["base_year"] == base_year, f"the honors history is for {data['base_year']}, the build is {base_year}")
    return data


def apply(path, spec: str = "builtin", *, base_year: int = 2026, progress=None) -> dict:
    """Write the selected honors into the main roster of the disc image (or pack folder) at ``path`` -- a COPY."""

    from . import nfl2k5_team_history as history
    say = progress or (lambda _m: None)
    builtin = spec.strip() == "builtin"
    if builtin and base_year != load(DEFAULT_DATA)["base_year"]:
        return {"status": "skipped", "spec": spec, "reason": f"the built-in award history is for the 2026 rosters; "
                                                             f"this build is {base_year}"}
    data = resolve(spec, base_year)
    with history._outer_image()(path, writable=True) as archive:
        entry = history._entry(archive)
        before = archive.read(entry.virtual_offset, entry.size)
        header, body = before[:history.RESOURCE_HEADER_SIZE], before[history.RESOURCE_HEADER_SIZE:]
        _require(header[:4] == b"ROST" and len(body) == records.BODY_SIZE, "the roster resource is foreign")
        say("Writing the award history into the career-stat pool")
        new_body, receipt = apply_body(body, data, strict=not builtin)
        summary = {k: v for k, v in receipt.items() if k not in ("rows",)}
        summary["skipped"] = len(receipt["skipped"])
        summary["identity_mismatches"] = len(receipt["identity_mismatches"])
        if new_body == body:
            return {"status": "unchanged", "spec": spec, **summary}
        replacement = header + new_body
        count = archive.write(entry.virtual_offset, replacement)
        _require(count == len(replacement), "short write of the roster resource")
        _require(archive.read(entry.virtual_offset, entry.size) == replacement, "read-back of the roster resource differs")
    return {"status": "applied", "spec": spec, "virtual_offset": f"0x{entry.virtual_offset:x}", **summary}


__all__ = ["SCHEMA", "resolve", "apply", "FIELDS", "HONORS", "DEFAULT_DATA", "HonorsHistoryError", "load", "validate", "plan",
           "apply_body", "read_body", "to_csv", "from_csv", "word"]
