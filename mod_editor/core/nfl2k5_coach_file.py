"""Export and import coaches in Flying Finn's own file format (b81 R2, parity row G5).

Finn's *Tools > Backup and Restore > Export Coaches / Import Coaches* writes and reads a Windows INI file (Delphi
``TIniFile``: ``key=value`` lines, CRLF, ANSI) with one section per club, named by the club's nickname string (team record
``+0x104``).  Finn saves it with the extension ``.Coaches`` (his open dialog lists ``*.2k5Coaches``; offer both).  The
key list, its order and the coach-record offsets are receipts of the reverse-engineered shipped program
(``finn-r2/re/RE_FACTS.md`` section 5, ``coach-io.json``).

Where this differs from Finn, on purpose
----------------------------------------
* Finn pairs section ``i`` with "coach list item ``i``".  That is wrong as soon as a coach has moved (SOFTDRINK's coach
  carousel, Fire and hire, Swap).  Here a section belongs to the club's actual head coach, the record the club's coach pointer
  (team ``+0x14C``) aims at (``FranchiseSave.head_coach_index``).
* Missing sections and missing keys leave the field as it is (Finn's rule: every key is read with the current value as its
  default).  A section that names no club is listed, not an error.
* A value that is not a whole number or is outside the field's range refuses the whole import, naming the key and the section;
  nothing is written.  Finn's setters take any integer.
* A record that more than one league club leads is never changed through one club; it is listed (the Studio's Fire and hire
  refuses the same way).
* ``First`` and ``Last`` go through the Studio's one coach-text writer (``_rewrite_coach_text``, the writer behind Fire and
  hire).  Text the game cannot show (not plain ASCII, empty, over 24 characters) refuses the import like any bad value.  When
  the save's coach text cannot be rewritten safely (``coach_text_problem``) or the region has no room, the numbers are still
  applied, the names are skipped and listed.
* If two league clubs share a nickname the section for each is written ``[Nickname (ABBR)]``, and a section that is just the
  shared nickname is listed as ambiguous instead of guessed.

Studio field names against Finn's keys (offsets are the same; checked at import time below)
------------------------------------------------------------------------------------------
``Body`` is the low byte of ``+0x18`` (the Studio calls the whole word ``body`` and edits ``<H``; only the low byte is
written here, the high byte stays).  ``SuperBowlAppearances`` is the Studio's ``super_bowls`` (``+0x32``), ``LeaderShip`` is
``leadership``, ``STRating`` is ``special_teams`` (``+0x51``), ``Rushing*`` are the five ``run_*`` formation weights
(``+0x83..+0x87``, the formation of a CPU run call) and ``Passing*`` the five ``pass_*`` weights (``+0x88..+0x8C``); Finn's
names for them are as he wrote them (``LoneBack`` = the Studio's ``one_back``, ``Empty`` = ``no_back``, ``Shotgun`` =
``gun``).  Nothing here has been watched in the game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import struct
from typing import Any, Sequence

from . import nfl2k5_franchise_save as fs
from . import nfl2k5_roster_records as rr

EXTENSION = ".Coaches"
OPEN_EXTENSIONS = (".Coaches", ".2k5Coaches")
FILE_FILTER = "Finn coach files (*.Coaches *.2k5Coaches);;All files (*)"
NEWLINE = "\r\n"


@dataclass(frozen=True)
class CoachKey:
    """One key of Finn's file: its name, what it is in the Studio, the record offset and the allowed range."""

    key: str
    kind: str                # "text", "number"
    field: str               # the Studio's coach field name (``body``, ``wins``, ``overall``, ``run_gun``; ``first``/``last``)
    offset: int              # byte offset in the 0xA8-byte coach record (the Finn object holds the record at +4)
    width: int               # 1 or 2 bytes written
    high: int                # the largest value written


_U16 = 0xFFFF


def _build() -> tuple[CoachKey, ...]:
    keys = [CoachKey("First", "text", "first", 0x00, 0, 0), CoachKey("Last", "text", "last", 0x04, 0, 0),
            CoachKey("Body", "number", "body", fs.COACH_FIELDS["body"][0], 1, 0xFF),
            CoachKey("Photo", "number", "photo", fs.COACH_FIELDS["photo"][0], 2, _U16)]
    for key, name in (("Wins", "wins"), ("Losses", "losses"), ("Ties", "ties"), ("SeasonsWithTeam", "seasons_with_team"),
                      ("TotalSeasons", "total_seasons"), ("WinningSeasons", "winning_seasons"),
                      ("SuperBowlAppearances", "super_bowls"), ("PlayOffWins", "playoff_wins"),
                      ("PlayOffLosses", "playoff_losses"), ("SuperBowlWins", "super_bowl_wins"),
                      ("SuperBowlLosses", "super_bowl_losses")):
        keys.append(CoachKey(key, "number", name, fs.COACH_FIELDS[name][0], 2, _U16))
    for key, name in (("OverallRating", "overall"), ("OffenseOverallRating", "offense"), ("RushForRating", "rush_for"),
                      ("PassForRating", "pass_for"), ("DefenseOverallRating", "defense"), ("PassRushRating", "pass_rush"),
                      ("PassCoverageRating", "pass_coverage"), ("QBRating", "qb"), ("RBRating", "rb"), ("TERating", "te"),
                      ("WRRating", "wr"), ("OLRating", "ol"), ("DLRating", "dl"), ("LBRating", "lb"), ("DBRating", "db"),
                      ("STRating", "special_teams"), ("Professionalism", "professionalism"),
                      ("Preparation", "preparation"), ("Conditioning", "conditioning"), ("Motivation", "motivation"),
                      ("LeaderShip", "leadership"), ("Discipline", "discipline"), ("Respect", "respect")):
        keys.append(CoachKey(key, "number", name, fs.COACH_RATINGS_OFFSET + fs.COACH_RATINGS.index(name), 1, 99))
    for call, prefix in (("run", "Rushing"), ("pass", "Passing")):
        for formation, suffix in zip(fs.COACH_FORMATION_CLASSES, ("Shotgun", "SplitBacks", "IForm", "LoneBack", "Empty")):
            name = f"{call}_{formation}"
            keys.append(CoachKey(prefix + suffix, "number", name,
                                 fs.COACH_TENDENCIES_OFFSET + fs.COACH_TENDENCIES.index(name), 1, 100))
    return tuple(keys)


KEYS: tuple[CoachKey, ...] = _build()
BY_KEY = {k.key.lower(): k for k in KEYS}

# Finn's offsets (RE_FACTS section 5, coach-io.json), in his order: the Studio's map has to agree byte for byte
_FINN_OFFSETS = (0x00, 0x04, 0x18, 0x40, 0x20, 0x22, 0x24, 0x1C, 0x1E, 0x30, 0x32, 0x34, 0x36, 0x38, 0x3A,
                 *range(0x42, 0x59), *range(0x83, 0x88), *range(0x88, 0x8D))
assert tuple(k.offset for k in KEYS) == _FINN_OFFSETS and len(KEYS) == 2 + 2 + 11 + 23 + 10 == 48, "Finn's coach key map"


# --------------------------------------------------------------------------------------------- reading the save
def _club_names(save: fs.FranchiseSave) -> dict[int, tuple[str, str]]:
    """League club -> (section name, nickname).  A shared nickname becomes ``Nickname (ABBR)``."""

    count = save.league_team_count
    nicknames = {}
    for team in range(count):
        text = " ".join(save.wstr(save.team_offset(team) + rr.TEAM_NICKNAME).split())
        nicknames[team] = text or save.team_abbreviation(team)
    seen: dict[str, int] = {}
    for text in nicknames.values():
        seen[text.lower()] = seen.get(text.lower(), 0) + 1
    return {team: ((f"{text} ({save.team_abbreviation(team)})" if seen[text.lower()] > 1 else text), text)
            for team, text in nicknames.items()}


def _read_value(save: fs.FranchiseSave, coach_offset: int, key: CoachKey) -> int | str:
    if key.kind == "text":
        return save.wstr(coach_offset + key.offset)
    if key.width == 2:
        return struct.unpack_from("<H", save.buffer, coach_offset + key.offset)[0]
    return save.buffer[coach_offset + key.offset]


def _head_coaches(save: fs.FranchiseSave) -> dict[int, tuple[int, int]]:
    """League club -> (coach index, coach record offset) of its actual head coach; clubs without one are left out."""

    out: dict[int, tuple[int, int]] = {}
    for team in range(save.league_team_count):
        index = save.head_coach_index(team)
        if index is not None:
            out[team] = (index, save._coach_offset(index))
    return out


# --------------------------------------------------------------------------------------------- export
def export_coaches(save: fs.FranchiseSave) -> str:
    """Finn's coach file for ``save``: one section per club (its nickname), that club's head coach, CRLF lines."""

    names = _club_names(save)
    lines: list[str] = []
    for team, (_index, offset) in _head_coaches(save).items():
        lines.append(f"[{names[team][0]}]")
        for key in KEYS:
            value = _read_value(save, offset, key)
            lines.append(f"{key.key}={value}")
        lines.append("")
    return NEWLINE.join(lines) + (NEWLINE if lines else "")


def decode_file(raw: bytes) -> str:
    """Finn writes ANSI; a UTF-8 file (with or without a mark) reads too."""

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def encode_file(text: str) -> bytes:
    """The bytes Finn writes: ANSI (a character cp1252 lacks becomes ``?``; coach names are plain ASCII anyway)."""

    return text.encode("cp1252", errors="replace")


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """Sections (lower-cased name -> {"": original name, key lower -> value}), the way a Windows INI reads: names are not
    case sensitive, the first of a repeated key wins, ``;`` starts a comment line, one pair of quotes round a value goes."""

    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and "]" in line:
            name = line[1:line.index("]")].strip()
            current = sections.setdefault(name.lower(), {"": name})
            continue
        if current is None or "=" not in line:
            continue
        key, _eq, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        current.setdefault(key.strip().lower(), value)
    return sections


# --------------------------------------------------------------------------------------------- import: plan
@dataclass(frozen=True)
class CoachChange:
    team: int
    club: str                # the section name (the club's nickname)
    coach: int               # coach record index
    coach_name: str          # his name now
    key: str                 # Finn's key
    field: str               # the Studio's field name
    old: int | str
    new: int | str

    @property
    def is_name(self) -> bool:
        return self.field in ("first", "last")

    def line(self) -> str:
        return f"{self.club}: {self.coach_name}: {self.key} {self.old} -> {self.new}"


@dataclass
class ImportPlan:
    changes: list[CoachChange] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)      # any one of these stops the import; nothing is written
    skipped: list[str] = field(default_factory=list)       # listed, not applied (shared records, unmatched sections)
    name_problem: str = ""                                 # why names cannot be written in this save ("" when they can)
    sections: int = 0                                      # sections in the file
    matched: int = 0                                       # sections that matched a club with a head coach

    @property
    def ok(self) -> bool:
        return not self.refusals

    @property
    def number_changes(self) -> list[CoachChange]:
        return [c for c in self.changes if not c.is_name]

    @property
    def name_changes(self) -> list[CoachChange]:
        return [c for c in self.changes if c.is_name]

    @property
    def writable_names(self) -> bool:
        return not self.name_problem

    def summary(self) -> str:
        if self.refusals:
            return f"Refused, nothing changes: {self.refusals[0]}"
        if not self.changes:
            return "Nothing in the file differs from this save."
        clubs = len({c.team for c in self.changes})
        whose = "club's" if clubs == 1 else "clubs'"
        return f"{len(self.changes)} change{'s' if len(self.changes) != 1 else ''} to {clubs} {whose} coach{'es' if clubs != 1 else ''}"


def _whole_number(text: str) -> int | None:
    return int(text) if re.fullmatch(r"[+-]?\d+", text.strip()) else None


def plan_import(save: fs.FranchiseSave, text: str) -> ImportPlan:
    """What importing ``text`` would change in ``save``; reads only, writes nothing."""

    plan = ImportPlan()
    sections = parse_ini(text)
    plan.sections = len(sections)
    names = _club_names(save)
    heads = _head_coaches(save)
    # which league clubs lead each coach record (shared records are never changed through one club)
    leaders: dict[int, list[int]] = {}
    for team, (index, _offset) in heads.items():
        leaders.setdefault(index, []).append(team)
    lookup: dict[str, list[int]] = {}
    for team, (section, nickname) in names.items():
        lookup.setdefault(section.lower(), []).append(team)
        if nickname.lower() != section.lower():
            lookup.setdefault(nickname.lower(), []).append(team)        # the plain nickname of a shared one: ambiguous
    taken: set[int] = set()
    for lower, body in sections.items():
        original = body[""]
        clubs = lookup.get(lower, [])
        if not clubs:
            plan.skipped.append(f"[{original}] names no club in this save")
            continue
        if len(clubs) > 1:
            plan.skipped.append(f"[{original}] is the nickname of more than one club "
                                f"({', '.join(save.team_abbreviation(t) for t in clubs)}); name the section "
                                f"[{names[clubs[0]][0]}] to pick one")
            continue
        team = clubs[0]
        if team in taken:
            continue
        taken.add(team)
        if team not in heads:
            plan.skipped.append(f"[{original}]: {save.team_abbreviation(team)} has no head coach record")
            continue
        plan.matched += 1
        index, offset = heads[team]
        coach_name = " ".join(f"{_read_value(save, offset, BY_KEY['first'])} {_read_value(save, offset, BY_KEY['last'])}".split())
        pending: list[CoachChange] = []
        for key in KEYS:
            raw = body.get(key.key.lower())
            if raw is None:
                continue
            old = _read_value(save, offset, key)
            if key.kind == "text":
                new = " ".join(raw.split())
                label = "first name" if key.field == "first" else "last name"
                problem = _text_problem(new, label)
                if problem:
                    plan.refusals.append(f"[{original}] {key.key}: {problem}")
                    continue
                if new != old:
                    pending.append(CoachChange(team, names[team][0], index, coach_name, key.key, key.field, old, new))
                continue
            number = _whole_number(raw)
            if number is None:
                plan.refusals.append(f"[{original}] {key.key}={raw!r} is not a whole number")
                continue
            if not 0 <= number <= key.high:
                plan.refusals.append(f"[{original}] {key.key}={number} is outside 0..{key.high}")
                continue
            if number != old:
                pending.append(CoachChange(team, names[team][0], index, coach_name, key.key, key.field, int(old), number))
        if pending and len(leaders[index]) > 1:
            others = ", ".join(save.team_abbreviation(t) for t in leaders[index] if t != team)
            plan.skipped.append(f"[{original}]: {coach_name} also leads {others} with the same coach record, so "
                                f"{len(pending)} change{'s' if len(pending) != 1 else ''} would change them too; "
                                "not applied (give each club its own coach first)")
            continue
        plan.changes.extend(pending)
    if plan.name_changes and not plan.refusals:
        plan.name_problem = save.coach_text_problem()
    return plan


def _text_problem(text: str, label: str) -> str:
    if not text:
        return f"the coach's {label} is empty"
    if len(text) > fs.COACH_NAME_MAX:
        return f"the coach's {label} is longer than {fs.COACH_NAME_MAX} characters"
    if not all(32 <= ord(ch) < 127 for ch in text):
        return (f"the coach's {label} uses a character the game cannot show; "
                "use letters, numbers and plain punctuation")
    return ""


# --------------------------------------------------------------------------------------------- import: apply
def apply_import(save: fs.FranchiseSave, plan: ImportPlan) -> dict[str, Any]:
    """Write a plan that ``plan_import`` made on this same save.  A refused plan, or any failure, changes nothing.

    Numbers are written into the coach records (the byte diff is inside those records).  Names go through the Studio's
    coach-text writer; when that cannot be done safely the numbers still apply and the names come back in
    ``names_skipped``."""

    if plan.refusals:
        raise fs.FranchiseSaveError("; ".join(plan.refusals[:3]))
    written = 0
    names_skipped: list[str] = []
    with save._transaction():
        for change in plan.number_changes:
            key = BY_KEY[change.key.lower()]
            offset = save._coach_offset(change.coach) + key.offset
            fs._require(int(change.old) == (struct.unpack_from("<H", save.buffer, offset)[0] if key.width == 2
                                            else save.buffer[offset]),
                        f"{change.club}: {change.key} is no longer {change.old}; plan the import again")
            if key.width == 2:
                struct.pack_into("<H", save.buffer, offset, int(change.new))
            else:
                save.buffer[offset] = int(change.new)          # Body: the low byte only; +0x19 stays
            written += 1
        wanted: dict[int, dict[int, str]] = {}
        for change in plan.name_changes:
            wanted.setdefault(change.coach, {})[BY_KEY[change.key.lower()].offset] = str(change.new)
        if wanted:
            reason = plan.name_problem
            if not reason:
                try:
                    with save._transaction():                  # a failed rewrite puts the numbers' state back as it was
                        save._rewrite_coach_text(wanted)
                        fresh = {c.index: c for c in save.coaches()}
                        for change in plan.name_changes:
                            fs._require((fresh[change.coach].first if change.field == "first" else fresh[change.coach].last)
                                        == change.new, f"{change.club}: the new {change.key} did not read back")
                except fs.FranchiseSaveError as exc:
                    reason = str(exc)
            if reason:
                names_skipped = [f"{c.club}: {c.key} {c.old} -> {c.new} ({reason})" for c in plan.name_changes]
            else:
                written += len(plan.name_changes)
    return {"operation": "import_coaches", "changes_written": written,
            "numbers": len(plan.number_changes), "names": 0 if names_skipped else len(plan.name_changes),
            "names_skipped": names_skipped, "listed": list(plan.skipped)}


def import_coaches(save: fs.FranchiseSave, text: str) -> dict[str, Any]:
    """Plan and apply in one step (the journaled edit and the tests use this)."""

    return apply_import(save, plan_import(save, text))


def preview_lines(plan: ImportPlan, limit: int = 0) -> list[str]:
    """The plan in plain words, one line a change: ``club, coach, field, old -> new``."""

    lines = [c.line() for c in plan.changes]
    return lines[:limit] if limit else lines


__all__ = ["CoachChange", "ImportPlan", "KEYS", "apply_import", "decode_file", "encode_file", "export_coaches",
           "import_coaches", "parse_ini", "plan_import", "preview_lines", "EXTENSION", "OPEN_EXTENSIONS", "FILE_FILTER"]
