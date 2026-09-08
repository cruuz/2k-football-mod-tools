"""Compare a signed Xbox save with the CURRENT disc, exporting ordinary roster edits.

EXPERIMENTAL / UNWITNESSED. No source writes or executable changes. Names are
matched within their pool, with play-by-play ID, star tag and team membership
as disambiguators. A renamed player needs a unique nonzero play-by-play ID plus
unchanged birth bits. Ordinals alone and star bits alone never establish identity.
Reserve ownership and franchise state cannot travel through the v1 edits lane.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

from . import nfl2k5_roster_records as rr

RECEIPT_SCHEMA = "2k5_mod_studio_roster_save_to_disc_receipt/v1"
MAX_SAVE_BYTES = 32 * 1024 * 1024
# Unknown bits stay with the target, except the codec's decoded locks/abilities.
CARRIED_FIELDS = tuple(f.name for f in rr.FIELDS if f.name not in rr.POINTER_FIELDS
                      and f.name != "star_tag"
                      and (not f.name.startswith("unknown_")
                           or f.name in ("unknown_52", "unknown_53_high")))
DEPTH_FIELDS = ("depth_rank", "depth_side", "unknown_52")


class SaveToDiscError(rr.RosterRecordError):
    """The comparison cannot produce an honest, replayable roster edits file."""


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _key(player: rr.Player) -> tuple[str, int]:
    return player.pool, player.index


def _identity(player: rr.Player) -> dict[str, Any]:
    return {"pool": player.pool, "index": player.index,
            "first": player.first, "last": player.last}


def _name(player: rr.Player) -> tuple[str, str, str]:
    return player.pool, player.first.casefold(), player.last.casefold()


def _rename_key(player: rr.Player) -> tuple[Any, ...] | None:
    v = player.record.values
    if not v["pbp_id"] or not (1 <= v["birth_month"] <= 12 and 1 <= v["birth_day"] <= 31):
        return None
    return (player.pool, *(v[k] for k in ("pbp_id", "birth_month", "birth_day",
                                        "birth_year_low", "birth_year_high")))


def _free_slot(doc: rr.RosterDocument, player: rr.Player) -> bool:
    # Zero-type records are the game's regenerating draft window, not free slots.
    v = player.record.values
    return (player.pool == "primary" and not player.first and not player.last
            and not player.teams and player.offset not in doc.free_agents
            and _key(player) not in doc.reserve_owner
            and bool(v["player_type"] & rr.FLAG_NFL_PLAYER)
            and not (v["player_type"] & rr.FLAG_PROSPECT)
            and not any(v[k] for k in ("history_pointer", "pbp_id", "photo_id", "star_tag")))


def _check_structure(doc: rr.RosterDocument, label: str) -> None:
    for team in doc.teams:
        if (not team.clean_parse or len(set(team.slots)) != len(team.slots)
                or len(team.slots) > rr.TEAM_SLOTS):
            raise SaveToDiscError(f"{label}: {team.display} has an invalid active list "
                                  f"({team.player_count} players; at most 65 pointer slots).")
    if len(doc.original_free_agents) != doc.free_agent_count_field or len(set(doc.free_agents)) != len(doc.free_agents):
        raise SaveToDiscError(f"{label}: the free-agent list did not parse cleanly.")
    for p in doc.players:
        if len([t for t in p.teams if doc.teams[t].is_club]) > 1:
            raise SaveToDiscError(f"{label}: {p.display} belongs to two clubs.")
        if p.offset in doc.free_agents and any(doc.teams[t].is_club for t in p.teams):
            raise SaveToDiscError(f"{label}: {p.display} is both rostered and a free agent.")


def load_save(source: Path | str) -> rr.RosterDocument:
    """Bound containers before the existing signature-verifying reader allocates them."""
    path = Path(source).expanduser()
    if path.is_file() and path.stat().st_size > MAX_SAVE_BYTES:
        raise SaveToDiscError("Xbox save exceeds the 32 MiB read limit; choose SAVEGAME.DAT, not a disc.")
    if path.is_dir():
        total = 0
        count = 0
        for item in path.rglob("*"):
            if item.is_file():
                count += 1
                total += item.stat().st_size
                if total > MAX_SAVE_BYTES or count > 4096:
                    raise SaveToDiscError("Xbox save container exceeds the 32 MiB / 4096 member read limit.")
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            if len(infos) > 4096 or sum(i.file_size for i in infos) > MAX_SAVE_BYTES:
                raise SaveToDiscError("Xbox save container exceeds the 32 MiB / 4096 member read limit.")
            names = [i.filename.casefold() for i in infos]
            if len(names) != len(set(names)):
                raise SaveToDiscError("Xbox save container has duplicate member names.")
    doc = rr.load_save(path)
    doc.set_scheme(str(rr.detect_scheme_from_data(doc)["scheme"]))
    return doc


@dataclass(frozen=True)
class ExportResult:
    edits: dict[str, Any]
    receipt: dict[str, Any]

    @property
    def summary(self) -> str:
        r = self.receipt
        return (f"Matched: {r['matched']}. Added in free slots: {r['added']}. "
                f"Changed: {r['changed']}. Unmatched: {r['unmatched']}. "
                f"Skipped items: {len(r['skipped'])}.\n"
                "EXPERIMENTAL / UNWITNESSED. Build with Include exported Rosters edits.")

    @property
    def details(self) -> str:
        return json_text(self.receipt)

    def write_receipt(self, edits_path: Path | str) -> Path:
        path = Path(edits_path).with_suffix(".receipt.json")
        path.write_text(self.details, encoding="utf-8", newline="\n")
        return path


def compare(disc: rr.RosterDocument, save: rr.RosterDocument, *,
            name: str = "Xbox save roster for disc") -> ExportResult:
    """Return v1 edits and an exact receipt without mutating either input.

    The source must come from SaveContainer (signature verified). In-session
    edits are included. The target's current bytes, rather than its original
    load snapshot, are the baseline. Export twice with identical inputs to get
    identical JSON, including its receipt. Every result passes actual v1 replay
    and a full target-body comparison before it is returned.
    """
    if save.container is None or not save.container.verified:
        raise SaveToDiscError("Open a signature-verified Xbox save (SAVEGAME.DAT with its EXTRA).")
    if sum(Path(k).name.casefold() == "savegame.dat" for k in save.container.members) != 1:
        raise SaveToDiscError("Choose a container holding exactly one Xbox SAVEGAME.DAT.")
    if not rr.verify_extra(save.container.savegame, save.container.members[save.container.extra_name]):
        raise SaveToDiscError("The source save signature no longer verifies.")
    if disc.version not in (17, 18) or disc.container is not None:
        raise SaveToDiscError("The comparison target must be the current disc ROST resource (version 17 or 18).")
    if (disc.scheme == "one_pool") != (save.scheme == "one_pool"):
        raise SaveToDiscError(
            f"Position scheme mismatch: disc uses {disc.scheme}; Xbox save uses {save.scheme}. "
            "A pooled disc uses 11 for LB, 15 for interior and 16 for EDGE; retail save code 10 "
            "is OLB. The roster edits lane would remap code 10 and change its meaning. "
            "Use a save and disc with the same position scheme; no conversion was exported.")
    _check_structure(disc, "Disc")
    _check_structure(save, "Xbox save")
    from .nfl2k5_franchise_save import FranchiseSave, is_franchise_save
    save_bytes = save.to_body()
    franchise = is_franchise_save(save_bytes)
    ir_players = ({e.player_index for e in FranchiseSave(save_bytes).injured_reserve()}
                  if franchise else set())
    before = disc.to_body()
    work = rr.RosterDocument(before, scheme=disc.scheme, reference_year=disc.reference_year)
    targets = {_key(p): p for p in work.players}
    baseline = {_key(p): p for p in disc.players}
    sources = [p for p in save.players if p.first or p.last]
    skipped: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    mapping: dict[int, rr.Player] = {}
    used: set[tuple[str, int]] = set()
    unresolved: dict[int, str] = {}

    def skip(p: rr.Player, field: str, reason: str, **extra: Any) -> None:
        skipped.append({"save": _identity(p), "field": field, "reason": reason, **extra})

    # Stable team ordinals survive NFL renames; asset ID and kind guard added teams.
    team_map: dict[int, int] = {}
    for team in save.teams:
        candidates = [t for t in work.teams if t.index == team.index
                      and t.asset_id == team.asset_id and t.kind == team.kind]
        if len(candidates) == 1:
            team_map[team.index] = candidates[0].index

    def select(p: rr.Player, candidates: list[rr.Player]) -> rr.Player | None:
        for predicate in (
            lambda t: t.record.values["pbp_id"] == p.record.values["pbp_id"],
            lambda t: t.record.values["star_tag"] == p.record.values["star_tag"],
            lambda t: bool(set(t.teams) & {team_map[i] for i in p.teams if i in team_map}),
        ):
            if len(candidates) <= 1:
                break
            narrowed = [t for t in candidates if predicate(t)]
            if narrowed:
                candidates = narrowed
        return candidates[0] if len(candidates) == 1 else None

    # Match all unchanged names before attempting renames or allocating anything.
    for phase in ("name", "rename"):
        proposals: dict[tuple[str, int], list[rr.Player]] = {}
        for p in sources:
            if p.offset in mapping:
                continue
            candidates = [t for t in work.players if _key(t) not in used and (t.first or t.last)
                          and (_name(t) == _name(p) if phase == "name" else
                               _rename_key(p) is not None and _rename_key(t) == _rename_key(p))]
            target = select(p, candidates)
            if target is not None:
                proposals.setdefault(_key(target), []).append(p)
            elif candidates:
                unresolved[p.offset] = "Ambiguous player identity; multiple disc records match."
        for key, owners in sorted(proposals.items()):
            if len(owners) != 1:
                for p in owners:
                    unresolved[p.offset] = "Ambiguous player identity; multiple save players claim one disc record."
                continue
            p = owners[0]
            mapping[p.offset] = targets[key]
            used.add(key)
            matches.append({"save": _identity(p), "disc": _identity(baseline[key]), "method": phase})

    added: set[int] = set()
    slots = [p for p in work.players if _key(p) not in used and _free_slot(work, p)]
    for p in sources:
        if p.offset in mapping:
            continue
        if p.offset in unresolved:
            skip(p, "player", unresolved[p.offset])
            continue
        if p.pool == "primary" and (p.teams or save.is_free_agent(p)) and slots:
            target = slots.pop(0)
            mapping[p.offset] = target
            used.add(_key(target))
            added.add(p.offset)
            matches.append({"save": _identity(p), "disc": _identity(baseline[_key(target)]),
                            "method": "free_slot"})
        else:
            skip(p, "player", "No matching disc identity and no eligible free player slot. "
                 "A free slot must be an unnamed, unowned NFL record with no history, photo or "
                 "play-by-play ID. Draft-class and template records cannot be reused.")

    # Plan name edits in the same target order used by the ordinary replay.
    ordered = sorted((p for p in sources if p.offset in mapping), key=lambda p: _key(mapping[p.offset]))
    rejected_added: set[int] = set()
    for p in ordered:
        t = mapping[p.offset]
        old = None
        if p.offset in added:
            # Added players need BOTH names. Roll back their entire allocation on failure.
            old = copy.deepcopy(work)
        failed = False
        for which in ("first", "last"):
            value = getattr(p, which)
            if value == getattr(t, which):
                continue
            try:
                if rr.validate_name(value) != value:
                    raise rr.RosterRecordError("Name would be normalized; exact source text must be preserved.")
                work.set_name(t, which, value)
            except rr.RosterRecordError as exc:
                skip(p, which, f"Name skipped, never truncated: {exc}", value=value)
                failed = True
        if failed and old is not None:
            work = old
            targets = {_key(t): t for t in work.players}
            mapping = {s: targets[_key(t)] for s, t in mapping.items()}
            rejected_added.add(p.offset)
            skip(p, "player", "Free player slot exists, but both names could not fit; added player skipped.")
            continue
        for field in CARRIED_FIELDS:
            value = p.record.values[field]
            if field == "injured_reserve" and value != t.record.values[field] and (
                    p.record.on_injured_reserve or p.index in ir_players):
                skip(p, field, "Injured-reserve status needs ownership in the save's front-office table; "
                     "disc status retained.", value=value)
                continue
            if field == "position":
                try:
                    rr.check_position_code(value, work.scheme)
                except rr.RosterRecordError as exc:
                    skip(p, field, str(exc), value=value)
                    continue
            t.record.set(field, value)
        for field in (f.name for f in rr.FIELDS if f.name not in CARRIED_FIELDS and f.name not in rr.POINTER_FIELDS):
            if p.record.values[field] != t.record.values[field]:
                skip(p, field, "Disc identity tag or undecoded bits retained.", value=p.record.values[field])
        if p.college != t.college:
            if p.college in work.colleges:
                work.set_college(t, work.colleges.index(p.college))
            else:
                skip(p, "college", "College is absent from the disc's fixed table.", value=p.college)
    for off in rejected_added:
        del mapping[off]
        added.remove(off)
    matches = [m for m in matches if (m["save"]["pool"], m["save"]["index"]) not in
               {_key(save.by_offset[off]) for off in rejected_added}]

    # Preserve reserve ownership. The v1 format has no reserve move operation.
    mobile: dict[int, rr.Player] = {}
    for p in sources:
        if p.offset not in mapping:
            continue
        t = mapping[p.offset]
        source_reserve = save.reserve_owner.get(_key(p))
        target_reserve = work.reserve_owner.get(_key(t))
        if p.record.on_injured_reserve or (p.pool == "primary" and p.index in ir_players):
            skip(p, "membership", "Injured-reserve ownership lives in the Xbox save, outside its roster arena; "
                 "existing disc membership retained.")
            continue
        if source_reserve is not None or target_reserve is not None:
            if (source_reserve is None or target_reserve is None
                    or team_map.get(source_reserve) != target_reserve):
                skip(p, "membership", "Reserve ownership changes require a signed Xbox save copy; "
                     "roster edits cannot carry them.")
            continue
        if work.is_draft_class(t) or save.is_draft_class(p):
            if p.teams or save.is_free_agent(p) or t.teams or work.is_free_agent(t):
                skip(p, "membership", rr.DRAFT_CLASS_WHY)
            continue
        if any(i not in team_map for i in p.teams):
            skip(p, "membership", "Save team has no matching disc team slot; existing membership retained.")
            continue
        mobile[p.offset] = t
    moving_offsets = {t.offset for t in mobile.values()}
    desired_teams = {}
    for s, i in team_map.items():
        slots = [o for o in work.teams[i].slots if o not in moving_offsets]
        for rank, off in enumerate(save.teams[s].slots):
            if off in mobile:
                slots.insert(min(rank, len(slots)), mobile[off].offset)
        desired_teams[i] = slots
    desired_free = [o for o in work.free_agents if o not in moving_offsets or
                    any(t.offset == o and s in save.free_agents for s, t in mobile.items())]
    desired_free += [mobile[o].offset for o in save.free_agents if o in mobile
                     and mobile[o].offset not in desired_free]
    desired_slots = {t.index: desired_teams.get(t.index, list(t.slots)) for t in work.teams}
    moves = []
    for t in work.players:
        old_teams = [(i, work.teams[i].slots.index(t.offset)) for i in t.teams]
        new_teams = [(i, slots.index(t.offset)) for i, slots in desired_slots.items() if t.offset in slots]
        if old_teams == new_teams and (t.offset in work.free_agents) == (t.offset in desired_free):
            continue
        b = baseline[_key(t)]
        moves.append({**_identity(b),
                      "from_teams": [{"team_index": i, "slot": s} for i, s in old_teams],
                      "to_teams": [{"team_index": i, "slot": s} for i, s in new_teams],
                      "free_agent": t.offset in desired_free,
                      "free_agent_slot": desired_free.index(t.offset) if t.offset in desired_free else None})
    # Exercise the exact batch rules BEFORE attaching the intended lists to work.
    probe = rr.RosterDocument(before, scheme=disc.scheme)
    move_log: list[str] = []
    rr.replay_moves(probe, moves, move_log)
    if move_log or any(probe.teams[i].slots != rows for i, rows in desired_slots.items()) or probe.free_agents != desired_free:
        reason = "; ".join(move_log) or "The existing roster edits writer could not carry the complete membership batch."
        for p in sources:
            if p.offset in mobile and any(m["pool"] == mobile[p.offset].pool and
                                         m["index"] == mobile[p.offset].index for m in moves):
                skip(p, "membership", reason)
        moves = []
    else:
        for team in work.teams:
            team.slots = list(desired_slots[team.index])
        work.free_agents = desired_free
        work._reindex_membership()
    # Export normal fields/texts, then include explicit moves for pure depth rotations.
    edits = rr.edits_document(work, name=name)
    edits.pop("moves", None)
    if moves:
        edits["moves"] = moves
        by_key = {(e["pool"], e["index"]): e for e in edits["edits"]}
        for m in moves:
            key = (m["pool"], m["index"])
            e = by_key.setdefault(key, {**_identity(baseline[key]), "fields": {}})
            for field in DEPTH_FIELDS:
                e["fields"][field] = targets[key].record.values[field]
        edits["edits"] = [by_key[k] for k in sorted(by_key)]
    expected = work.to_body()
    replayed, replay = rr.apply_body(before, edits, scheme=disc.scheme)
    if replay["log"] or replayed != expected:
        raise SaveToDiscError("Roster export did not round-trip through the Build roster edits writer: "
                              + ("; ".join(replay["log"]) or "target bytes differ"))
    changed_keys = {(e["pool"], e["index"]) for e in edits["edits"]}
    changed_keys.update((m["pool"], m["index"]) for m in moves)
    mapped_keys = {_key(t) for t in mapping.values()}
    receipt = {"schema": RECEIPT_SCHEMA, "experimental": True, "witnessed": False,
               "source_kind": "franchise save" if franchise else "roster save",
               "source_note": "The save's roster arena is used. Franchise progress, schedule, stats, "
                              "IR ownership and history streams are not disc roster edits. "
                              "Existing disc-only players and reserve ownership are retained; "
                              "existing free-agent list order is retained.",
               "disc_body_sha256": _hash(before), "save_sha256": _hash(save_bytes),
               "result_body_sha256": _hash(expected), "edits_sha256": _hash(json_text(edits).encode("utf-8")),
               "disc_scheme": disc.scheme, "save_scheme": save.scheme,
               "source_players": len(sources), "source_records": len(save.players),
               "unnamed_records": len(save.players) - len(sources),
               "matched": len(mapping) - len(added), "added": len(added),
               "changed": len(changed_keys & mapped_keys), "unmatched": len(sources) - len(mapping),
               "disc_players_affected": len(changed_keys),
               "retained_players_reordered": [_identity(baseline[k]) for k in sorted(changed_keys - mapped_keys)],
               "matches": sorted(matches, key=lambda m: (m["save"]["pool"], m["save"]["index"])),
               "skipped": skipped, "replay": replay,
               "teams": [{"index": t.index, "team": t.abbreviation,
                          "disc_before": len(disc.teams[t.index].slots), "disc_after": len(t.slots),
                          "save_active": len(save.teams[t.index].slots) if t.index in team_map else None,
                          "disc_reserves": len(work.reserves[t.index]),
                          "save_reserves": len(save.reserves[t.index]) if t.index in team_map else None,
                          "matched": sum(p.offset in mapping and p.offset not in added for p in sources
                                         if t.index in p.teams or save.reserve_owner.get(_key(p)) == t.index),
                          "added": sum(p.offset in added for p in sources if t.index in p.teams),
                          "unmatched": sum(p.offset not in mapping for p in sources
                                           if t.index in p.teams or save.reserve_owner.get(_key(p)) == t.index),
                          "active_limit": work.membership_limit(t.index)} for t in work.teams],
               "free_agents": {"disc_before": len(disc.free_agents), "disc_after": len(work.free_agents),
                               "save": len(save.free_agents), "capacity": work.free_agent_capacity}}
    return ExportResult(edits, receipt)


def from_file(disc: Path | str | rr.RosterDocument, source: Path | str) -> ExportResult:
    target = disc if isinstance(disc, rr.RosterDocument) else rr.load_image(disc, detect=True)
    return compare(target, load_save(source))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc", required=True, type=Path)
    parser.add_argument("--save", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = from_file(args.disc, args.save)
    output = args.output.expanduser().resolve()
    receipt_path = output.with_suffix(".receipt.json")
    if (output.suffix.lower() != ".json" or receipt_path == output
            or {output, receipt_path} & {args.disc.resolve(), args.save.resolve()}):
        raise SaveToDiscError("Choose a separate .json output path.")
    # Never overwrite an existing artifact from this command-line entry point.
    if output.exists() or receipt_path.exists():
        raise SaveToDiscError("Output or receipt already exists; choose a new output name.")
    output.write_text(json_text(result.edits), encoding="utf-8", newline="\n")
    result.write_receipt(output)
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
