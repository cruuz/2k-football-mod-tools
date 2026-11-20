"""Copy / Paste Team and Export / Import Team (b81 wave 3, Finn's team right-click menu).

A team package is plain JSON (``.2k5team``): the club's active list and reserves in order, each player's record values,
names, college and birth year, the depth chart (rows and the SOFTDRINK depth and returner locks), the six special-teams
slot bytes, and, when the source is an Xbox save, the five team settings and the head coach.

Pasting a package onto a club puts source player ``i`` into the club's record ``i`` (active list, then reserves), so
the depth rows, locks and special-teams slot bytes keep their meaning without any re-ranking. The guards are the player
Paste's (b81 R7) applied to a whole club:

* The club keeps each record's slot state: player kind and pool (+0x08, +0x34), injury and IR marker, and the studio's
  star tag. Nothing duplicates an IR marker or a star tag; a club with a player on IR on either side is refused (an IR
  place lives in the club's IR list, which a paste does not rewrite).
* Locks travel only as the source club's complete set, onto the club's whole list, so each lock keeps one owner per club;
  ``check_depth_locks`` must pass afterwards or nothing changes.
* The lists must match: the same number of active players and of reserves. A different count is refused with both
  counts (release or sign players first); a package with reserves cannot land on a roster without reserve lists.
* Shapes convert or refuse: a position code the target scheme retires is replaced the way the scheme does (OLB 10 ->
  LB 11 on a one-pool roster); a birth year is carried as a year and re-encoded for the target's season window (a year
  outside it refuses); a college missing from the target's table keeps the club record's college and says so; names
  that do not fit the name pool refuse the whole paste.
* Team settings are matched by what they mean, not by offset: the stadium by its asset id, the playbook by its key,
  the team play-by-play id only if a club of the target carries it, the default jersey only if the club owns that
  style, the defensive front as is. The head coach's ratings, play-calling and sideline body are copied onto the
  club's own head coach record; a different name is a new person (``replace_head_coach``), so the record's career
  totals are then copied too. A coach record shared by two league clubs is refused.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import nfl2k5_roster_records as rr
from .nfl2k5_depth_locks import LOCK_BITS

SCHEMA = "nfl2k5_studio_team/v1"
SUFFIX = ".2k5team"
LISTS = ("active", "reserve")
#: the club keeps these per record (R7's slot state, minus the depth rows and locks a whole-club paste carries)
KEPT_BY_CLUB = ("player_type", "injured_reserve", "unknown_29_low", "pool_kind", "star_tag")
_SKIPPED = frozenset(rr.POINTER_FIELDS) | frozenset(KEPT_BY_CLUB) | {"birth_year_low", "birth_year_high"}
CARRIED_FIELDS = tuple(f.name for f in rr.FIELDS if f.name not in _SKIPPED)
SETTINGS = ("stadium_id", "playbook_key", "jersey", "pbp", "front")


class TeamTransferError(rr.RosterRecordError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TeamTransferError(message)


# ------------------------------------------------------------------------------------------------ reading a club
def club_lists(document: rr.RosterDocument, team_index: int) -> dict[str, list[rr.Player]]:
    _require(0 <= team_index < len(document.teams) and document.teams[team_index].is_club,
             f"team {team_index} is not a club")
    team = document.teams[team_index]
    return {"active": [document.by_offset[offset] for offset in team.slots],
            "reserve": document.reserve_players(team_index)}


def _settings(save, team_index: int) -> dict[str, Any] | None:
    if save is None:
        return None
    options = save.team_options(team_index)
    return {"stadium_id": options["stadium"]["id"] if options["stadium"] else None,
            "stadium_label": f"s{options['stadium']['id']:02d}" if options["stadium"] else "",
            "playbook_key": options["playbook"]["key"] if options["playbook"] else None,
            "playbook_name": options["playbook"]["name"] if options["playbook"] else "",
            "jersey": options["jersey"], "pbp": options["pbp"], "front": options["front"]}


def _coach(save, team_index: int) -> dict[str, Any] | None:
    if save is None:
        return None
    coach = save.coach_for_team(team_index)
    if coach is None or getattr(coach, "placeholder", False):
        return None
    return {"first": coach.first, "last": coach.last, "bio": list(coach.info), "fields": dict(coach.fields),
            "ratings": dict(coach.ratings), "tendencies": dict(coach.tendencies)}


def team_package(document: rr.RosterDocument, team_index: int, *, save=None) -> dict[str, Any]:
    """The club as a package. ``save`` (a FranchiseSave over the same bytes, roster or franchise mode) adds the team
    settings and the head coach."""

    lists = club_lists(document, team_index)
    team = document.teams[team_index]
    players = []
    for list_name in LISTS:
        for player in lists[list_name]:
            record = player.record
            players.append({"list": list_name, "first": player.first, "last": player.last, "college": player.college,
                            "birth_year": record.birth_year if record.birth_date is not None else None,
                            "on_ir": bool(record.on_injured_reserve),
                            "fields": {name: int(record.values[name]) for name in CARRIED_FIELDS}})
    return {"schema": SCHEMA,
            "source": {"abbreviation": team.abbreviation, "display": team.display, "scheme": document.scheme,
                       "reference_year": document.reference_year, "reserve_lists": team_index in document.reserves,
                       "kind": "save" if save is not None else "roster"},
            "counts": {name: len(lists[name]) for name in LISTS},
            "players": players,
            "specialists": document._specialists(team),
            "settings": _settings(save, team_index),
            "coach": _coach(save, team_index)}


def write_package(path: Path | str, package: Mapping[str, Any]) -> Path:
    target = Path(path)
    if target.suffix.lower() != SUFFIX:
        target = target.with_name(target.name + SUFFIX)
    target.write_text(json.dumps(package, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return target


def read_package(path: Path | str) -> dict[str, Any]:
    try:
        package = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TeamTransferError(f"{Path(path).name} is not a team file ({exc})") from exc
    validate_package(package)
    return package


def validate_package(package: Any) -> None:
    _require(isinstance(package, dict) and package.get("schema") == SCHEMA,
             f"not a Studio team file (schema {package.get('schema') if isinstance(package, dict) else None!r})")
    players = package.get("players")
    _require(isinstance(players, list) and players, "the team file lists no players")
    for index, entry in enumerate(players):
        _require(isinstance(entry, dict) and entry.get("list") in LISTS and isinstance(entry.get("fields"), dict),
                 f"player {index}: malformed entry")
        for name, value in entry["fields"].items():
            _require(name in CARRIED_FIELDS, f"player {index}: {name!r} is not a field a team file carries")
            _require(type(value) is int and 0 <= value <= rr.FIELD_BY_NAME[name].maximum,
                     f"player {index}: {name} {value!r} is out of range")
        for key in ("first", "last", "college"):
            _require(isinstance(entry.get(key, ""), str), f"player {index}: {key} must be text")
        _require(entry.get("birth_year") is None or type(entry.get("birth_year")) is int,
                 f"player {index}: birth_year must be a whole year")
    specialists = package.get("specialists")
    _require(isinstance(specialists, list) and len(specialists) == len(rr.SPECIAL_TEAM_OFFSETS)
             and all(type(v) is int and 0 <= v <= 0xFF for v in specialists), "the special-teams slots are malformed")


# ------------------------------------------------------------------------------------------------ planning
def plan(document: rr.RosterDocument, team_index: int, package: Mapping[str, Any], *, save=None,
         settings: bool = True, coach: bool = True) -> dict[str, Any]:
    """What a paste would do: ``refusals`` (any one stops the paste), ``notes`` (conversions) and the pairs."""

    validate_package(package)
    refusals: list[str] = []
    notes: list[str] = []
    lists = club_lists(document, team_index)
    team = document.teams[team_index]
    source = package.get("source") or {}
    name = source.get("abbreviation") or "the package"
    entries = {lst: [e for e in package["players"] if e["list"] == lst] for lst in LISTS}
    if entries["reserve"] and team_index not in document.reserves:
        refusals.append(f"{name} has {len(entries['reserve'])} reserves and this roster keeps no reserve list for "
                        f"{team.abbreviation}; a SOFTDRINK club with reserves goes onto a SOFTDRINK roster")
    for lst, words in (("active", "active players"), ("reserve", "reserves")):
        have, want = len(lists[lst]), len(entries[lst])
        if have != want:
            refusals.append(f"{team.abbreviation} has {have} {words} and {name} {want}. A team paste puts player for "
                            f"player into {team.abbreviation}'s records, so the counts must match: "
                            + (f"release {have - want} {team.abbreviation} player{'s' if have - want != 1 else ''} first"
                               if have > want else f"sign {want - have} more to {team.abbreviation} first"))
    on_ir = [p.display for lst in LISTS for p in lists[lst] if p.record.on_injured_reserve]
    if on_ir:
        refusals.append(f"{team.abbreviation} has {', '.join(on_ir[:3])}{' …' if len(on_ir) > 3 else ''} on injured "
                        "reserve; activate them first (an IR place lives in the club's IR list, which a paste keeps)")
    ir_in = [f"{e['first']} {e['last']}".strip() for e in package["players"] if e.get("on_ir")]
    if ir_in:
        refusals.append(f"{name} has {', '.join(ir_in[:3])} on injured reserve; activate them in the source and copy "
                        "again")
    scheme = document.scheme
    from_scheme = source.get("scheme") or "retail"
    converted: dict[int, int] = {}
    for entry in package["players"]:
        code = entry["fields"].get("position")
        if code is not None and rr.is_retired_position(code, scheme):
            converted[code] = rr.replacement_position_code(code, scheme)
    for code, instead in converted.items():
        notes.append(f"{rr.position_name(code, from_scheme)} (code {code}) is retired on this "
                     f"{rr.SCHEME_TITLES[scheme]} roster; those players become {rr.position_name(instead, scheme)} "
                     f"(code {instead})")
    if from_scheme != scheme:
        renamed = sorted({c for e in package["players"] for c in [e["fields"].get("position")]
                          if c is not None and c not in converted
                          and rr.position_name(c, from_scheme) != rr.position_name(c, scheme)})
        for code in renamed:
            notes.append(f"code {code} reads {rr.position_name(code, from_scheme)} on {name}'s roster and "
                         f"{rr.position_name(code, scheme)} here (the same pool, its name differs)")
    for entry in package["players"]:
        year = entry.get("birth_year")
        if year is None:
            continue
        try:
            rr.encode_birth_year(year, document.reference_year)
        except (ValueError, rr.RosterRecordError):
            refusals.append(f"{entry['first']} {entry['last']}: born {year}, outside this roster's birth-year window "
                            f"around {document.reference_year}")
    missing = sorted({e.get("college", "") for e in package["players"]
                      if e.get("college") and e["college"] not in document.colleges})
    if missing:
        notes.append(f"{len(missing)} college{'s' if len(missing) != 1 else ''} not in this roster's college table "
                     f"({', '.join(missing[:4])}{' …' if len(missing) > 4 else ''}): those players keep the record's "
                     "college")
    if not any(e["fields"].get("unknown_52", 0) & rr.PASTE_LOCK_MASK for e in package["players"]):
        notes.append(f"{name} carries no depth or returner locks; on SOFTDRINK the weekly roster pass orders "
                     f"{team.abbreviation}'s chart from the ratings")
    parts = {"settings": False, "coach": False}
    if settings:
        if package.get("settings") is None:
            notes.append("the package has no team settings (it was copied from a disc roster)")
        elif save is None:
            notes.append("team settings are not changed on a disc roster (Build sets stadiums and uniforms)")
        else:
            parts["settings"] = True
    if coach:
        if package.get("coach") is None:
            notes.append("no head coach in the package")
        elif save is None:
            notes.append("the head coach is not changed on a disc roster")
        else:
            current = save.coach_for_team(team_index)
            if current is None or getattr(current, "placeholder", False):
                notes.append(f"{team.abbreviation} has no head coach record to copy onto; the coach is skipped")
            elif len(current.teams) > 1:
                refusals.append(f"{', '.join(save.team_abbreviation(t) for t in current.teams)} share one head coach "
                                "record, so a copied coach would change both; give one of them another coach first, "
                                "or leave Head coach unticked")
            else:
                parts["coach"] = True
    return {"refusals": refusals, "notes": notes, "converted": converted, "parts": parts,
            "pairs": [(entry, player) for lst in LISTS for entry, player in zip(entries[lst], lists[lst])]}


# ------------------------------------------------------------------------------------------------ applying
def apply_players(document: rr.RosterDocument, team_index: int, package: Mapping[str, Any],
                  plan_: Mapping[str, Any]) -> dict[str, Any]:
    """Write the players, depth chart and special-teams slots. The caller holds ``document.to_body()`` from before and
    ``adopt_body``s it back on any error (names and colleges are written into the pools as they go)."""

    _require(not plan_["refusals"], "; ".join(plan_["refusals"]))
    team = document.teams[team_index]
    converted = plan_["converted"]
    targets = {player.offset for _entry, player in plan_["pairs"]}
    views = [t.index for t in document.teams if t.index != team_index and targets & set(t.slots)]
    had = {index: {_conflict_key(c) for c in document.depth_lock_conflicts(index)} for index in views}
    changed = 0
    for entry, player in plan_["pairs"]:
        values = player.record.values
        before = dict(values)
        for name in CARRIED_FIELDS:
            value = int(entry["fields"].get(name, values[name]))
            if name == "position":
                value = converted.get(value, value)
            values[name] = value
        if entry.get("birth_year") is not None:
            player.record.birth_year = int(entry["birth_year"])
        for which in ("first", "last"):
            text = str(entry.get(which, ""))
            if getattr(player, which) != text:
                document.set_name(player, which, text)
        college = entry.get("college", "")
        if college and college != player.college and college in document.colleges:
            document.set_college(player, document.colleges.index(college))
        changed += values != before
    document._set_specialists(team, [int(v) for v in package["specialists"]])
    # The Pro Bowl and other exhibition squads list club records too. A copied lock that now collides there with the
    # source club's own player (the original and his copy on one squad) is left off the copy: a lock keeps one owner.
    dropped: list[str] = []
    for index in views:
        for conflict in document.depth_lock_conflicts(index):
            if _conflict_key(conflict) in had[index]:
                continue
            bit = LOCK_BITS[conflict["role"]]
            for offset in conflict["players"]:
                if offset in targets:
                    player = document.by_offset[offset]
                    player.record.values["unknown_52"] &= ~bit
                    dropped.append(f"{player.display} ({conflict['role'].upper() if conflict['role'] not in ('rank', 'side') else conflict['role']} lock, also on {document.teams[index].abbreviation})")
    document.check_depth_locks()
    return {"players": len(plan_["pairs"]), "changed": changed, "locks_dropped": dropped}


def _conflict_key(conflict: Mapping[str, Any]) -> tuple:
    return (conflict["role"], conflict["position"], conflict["row"])


def apply_team_parts(save, team_index: int, package: Mapping[str, Any], plan_: Mapping[str, Any]) -> list[str]:
    """Team settings and head coach onto ``save`` (a FranchiseSave); returns what was set or skipped, in words."""

    done: list[str] = []
    parts = plan_["parts"]
    if parts.get("settings"):
        wanted = package["settings"]
        stadiums = [s for s in save.stadium_choices() if s["id"] == wanted.get("stadium_id")]
        if stadiums:
            save.set_team_option(team_index, "stadium", stadiums[0]["index"])
            done.append(f"stadium s{wanted['stadium_id']:02d}")
        else:
            done.append(f"stadium s{wanted.get('stadium_id')} kept: this save has no such stadium")
        books = [b for b in save.playbook_choices() if b["key"] == wanted.get("playbook_key")]
        if books:
            save.set_team_option(team_index, "playbook", books[0]["index"])
            done.append(f"playbook {wanted['playbook_key']}")
        else:
            done.append(f"playbook {wanted.get('playbook_key')} kept: this save has no such playbook")
        if wanted.get("jersey") in save.jersey_styles(team_index):
            save.set_team_option(team_index, "jersey", int(wanted["jersey"]))
            done.append(f"default jersey style {wanted['jersey']}")
        else:
            done.append(f"default jersey kept: the club has no style {wanted.get('jersey')}")
        if wanted.get("pbp") in [c["id"] for c in save.pbp_choices()]:
            save.set_team_option(team_index, "pbp", int(wanted["pbp"]))
            done.append(f"team play-by-play id {wanted['pbp']}")
        else:
            done.append(f"team play-by-play kept: no club here carries id {wanted.get('pbp')}")
        if wanted.get("front") in (0, 1, 2):
            save.set_team_option(team_index, "front", int(wanted["front"]))
            done.append(f"defensive front {save.FRONTS[int(wanted['front'])]}")
    if parts.get("coach"):
        from . import nfl2k5_franchise_save as fs
        coach = package["coach"]
        current = save.coach_for_team(team_index)
        assert current is not None
        if (current.first, current.last) != (coach["first"], coach["last"]):
            save.replace_head_coach(team_index, coach["first"], coach["last"], coach.get("bio") or ())
            current = save.coach_for_team(team_index)
            assert current is not None
            names = list(fs.COACH_CAREER) + ["photo"]
        else:
            names = []
        for name in ["body", "playcalling_run"] + names:
            if name in coach["fields"]:
                save.set_coach_field(current.index, name, int(coach["fields"][name]))
        for name, value in list(coach["ratings"].items()) + list(coach["tendencies"].items()):
            save.set_coach_field(current.index, name, int(value))
        done.append(f"head coach {coach['first']} {coach['last']}")
    return done


__all__ = ["SCHEMA", "SUFFIX", "CARRIED_FIELDS", "KEPT_BY_CLUB", "TeamTransferError", "club_lists", "team_package",
           "write_package", "read_package", "validate_package", "plan", "apply_players", "apply_team_parts"]
