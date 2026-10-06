"""Dated real free-agent identities and conservative native appearance.

No record/table growth. The 380 native draft records and every team pointer
stay intact. New identities consume the explicitly audited trailing create-
player slots; unsupported rosters or occupied slots refuse transactionally.
The supplied ratings are r1-ratings-v2.4 estimates, not official 2K ratings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "nfl2k5.modern_free_agents.v1"
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_free_agents_2026.v1.json"
APPEARANCE_FIELDS = frozenset(("skin", "face", "body", "dreads", "headless", "photo_id"))
FIRST_TRAILING_SLOT = 2324
LAST_TRAILING_SLOT = 2478


def load_data(path=DEFAULT_DATA):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA or data.get("as_of") != "2026-10-05":
        raise ValueError("Unsupported dated free-agent data.")
    return data


def is_pack_input(edits):
    """Recognize the shipped SOFTDRINK authoring pool, never arbitrary rosters."""
    meta = edits.get("fr_free_agents") or {}
    return (meta.get("date") == "2026-09-29" and meta.get("selected") == 236
            and meta.get("source") == "roster_2026.csv"
            and len(edits.get("free_agent_pool", ())) == 239)


def apply_body(body, data=None):
    """Return new bytes and a scope receipt; never mutate the caller's data."""
    from . import nfl2k5_roster_records as rr
    data = load_data() if data is None else data
    rr._require(data.get("schema") == SCHEMA and data.get("as_of") == "2026-10-05",
                "Unsupported free-agent plan.")
    doc = rr.RosterDocument(bytes(body), scheme="one_pool", reference_year=2026)
    primary_count = len(doc.by_pool("primary"))
    if primary_count == 2619:
        from . import nfl2k5_spare_capacity
        nfl2k5_spare_capacity.extended_layout(body)
    rr._require(primary_count in (2479, 2619) and len(doc.by_pool("secondary")) == 68,
                "Free-agent plan requires the audited 2479/68 tables or their exact 2619 spare-capacity extension.")
    by = {(p.pool, p.index): p for p in doc.players}
    old = data["existing"]
    new = data["added"]
    removed_keys = {(r.get("pool", "primary"), r["index"]) for r in data.get("removed", ())}
    old_keys = {(r.get("pool", "primary"), r["index"]) for r in old}
    rr._require(removed_keys <= old_keys and all(r.get("sources") for r in data.get("removed", ())),
                "Removed free agents need dated signing evidence.")
    rr._require(len(old) == 239 and len(new) <= LAST_TRAILING_SLOT-FIRST_TRAILING_SLOT+1,
                "Invalid free-agent plan capacity.")
    seen_names = set()
    indices = set()
    for row in old + new:
        key = (row.get("pool", "primary"), row["index"])
        rr._require(key in by and key not in indices, "Duplicate or absent free-agent slot.")
        indices.add(key)
        identity = (row["first"], row["last"])
        rr._require(identity not in seen_names, "Duplicate free-agent identity.")
        seen_names.add(identity)
        p = by[key]
        rr._require(not p.teams and key not in doc.reserve_owner,
                    f"{p.display}: free-agent slot has a team/reserve owner.")
        if row in old:
            rr._require((p.first, p.last) == identity and
                        (p.offset in doc.free_agents or key in removed_keys),
                        f"Existing free-agent identity changed at {key}.")
            rr._require(set(row["appearance"]) == APPEARANCE_FIELDS,
                        "Existing free-agent plan exceeds appearance ownership.")
        else:
            rr._require(p.pool == "primary" and FIRST_TRAILING_SLOT <= p.index <= LAST_TRAILING_SLOT,
                        "New free agent would consume a draft or historic slot.")
            same = (p.first, p.last) == identity and p.offset in doc.free_agents
            vacant = (p.record.get("player_type") == 1 and p.group == "pool"
                      and p.first == "****************" and p.last == "****************")
            rr._require(same or vacant, f"Trailing slot {p.index} is occupied; no player was replaced.")
            rr._require(row["status"] == "unsigned_not_retired" and row.get("sources"),
                        "New free-agent identity needs unsigned/nonretirement evidence.")
            rr._require(0 <= row["jersey"] <= 99 and row["commentary_number"] == row["jersey"],
                        "Commentary number must equal the real jersey number.")
            rr._require(set(row["ratings"]) == set(rr.RATING_BYTE_ORDER),
                        "New free agent needs every rating from the documented model.")
    expected_old = {by[(r.get("pool", "primary"), r["index"])].offset for r in old}
    expected_new = {by[(r.get("pool", "primary"), r["index"])].offset for r in new}
    removed_offsets = {by[key].offset for key in removed_keys}
    expected_final = (expected_old - removed_offsets) | expected_new
    rr._require(set(doc.free_agents) in (expected_old, expected_final),
                "Free-agent membership differs from the dated source; refuse to drop other players.")
    rr._require(len(expected_final) <= doc.free_agent_capacity,
                "Free-agent pointer buffer is full.")
    # The first non-NFL records are the generator's window. Appended NFL flags
    # after this complete window cannot be overwritten by native class creation.
    rr._require([p.index for p in doc.by_pool("primary") if p.group == "draft_class"]
                == list(range(1944, 2324)), "Native draft window changed.")
    for row in old:
        p = by[(row.get("pool", "primary"), row["index"])]
        for field, value in row["appearance"].items():
            p.record.set(field, value)
    doc.free_agents = [offset for offset in doc.free_agents if offset not in removed_offsets]
    doc._reindex_membership()
    # Allocate the longest names first, independent of pool ordering.
    for row in sorted(new, key=lambda r: (-len(r["first"])-len(r["last"]), r["index"])):
        p = by[(row.get("pool", "primary"), row["index"])]
        if p.offset in doc.free_agents:
            # Idempotent replay preserves peer-owned commentary and any contract
            # written after creation; it does not reset a player's identity.
            for field, value in row["appearance"].items(): p.record.set(field, value)
            continue
        # New record from zero, with only its existing name pointers kept until
        # the pool allocator releases them. Never borrow a real player's face,
        # history, abilities, injury, contract or unknown packed fields.
        names = {k: p.record.values[k] for k in ("first_name_pointer", "last_name_pointer")}
        p.record = rr.PlayerRecord.decode(bytes(rr.PLAYER_SIZE), scheme="one_pool", reference_year=2026)
        p.record.values.update(names)
        for field, value in {**row["fields"], **row["ratings"], **row["appearance"]}.items():
            rr._require(field not in rr.POINTER_FIELDS, "Free-agent plan contains a raw pointer.")
            p.record.set(field, value)
        p.record.set("player_type", rr.FLAG_NFL_PLAYER)
        p.record.set("jersey", row["jersey"])
        # c1 normalizes pbp_id after all additions; this correct native number
        # fallback also makes the standalone writer safe without c1.
        p.record.set("pbp_id", 9000 + row["commentary_number"])
        doc.set_name(p, "first", row["first"])
        doc.set_name(p, "last", row["last"])
        if row.get("college") in doc.colleges:
            doc.set_college(p, doc.colleges.index(row["college"]))
        doc.free_agents.append(p.offset)
    doc._reindex_membership()
    # This writer owns appearance, new records and FA membership. Preserve
    # existing pbp words until the final commentary pass, including on replay.
    after = doc.to_body(normalise_commentary=False)
    rr._require(len(after) == len(body), "Free-agent writer changed roster geometry.")
    readback = rr.RosterDocument(after, scheme="one_pool", reference_year=2026)
    counts = {}
    for offset in readback.free_agents:
        name = readback.by_offset[offset].record.position_name
        counts[name] = counts.get(name, 0) + 1
    return after, {"schema": SCHEMA, "as_of": data["as_of"], "added": len(new),
                   "removed": len(removed_keys), "removed_indices": sorted(k[1] for k in removed_keys),
                   "free_agents": len(readback.free_agents), "by_position": dict(sorted(counts.items())),
                   "before_sha256": hashlib.sha256(body).hexdigest(),
                   "after_sha256": hashlib.sha256(after).hexdigest(),
                   "new_indices": [r["index"] for r in new],
                   "names_free_bytes": readback.names.free_bytes,
                   "commentary_rule": "jersey number; c1 owns final pbp writer"}
