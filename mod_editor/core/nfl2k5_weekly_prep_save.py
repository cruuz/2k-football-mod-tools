"""Inspect and author native Franchise prep plans. EXPERIMENTAL / UNWITNESSED.

No footer or spare bit is claimed. Persistence is the existing 500-word plan
per team, native repeat bit, state and seed. Build options live in the XBE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

from . import nfl2k5_franchise_save as fs
from . import nfl2k5_roster_records as rr
from . import nfl2k5_weekly_prep as patch
from .nfl2k5_cave_oracle import XbeImage

PLAN_OFFSET, STATE_OFFSET, SEED_OFFSET, SNAPSHOT_OFFSET = 0x5250, 0x14C50, 0x14CD0, 0x14D50
MASTER_OFFSET = 0x19C
PLAN_VA, STATE_VA, SEED_VA, SNAPSHOT_VA = 0xE42460, 0xE51E60, 0xE51EE0, 0xE51F60
WORDS = 500
EMPTY = 0x01000000
POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
CATEGORIES = ("weights", "aerobic", "alternative", "rehab", "film", "coaching",
              "position drill", "seven on seven", "full drill", "day off", "conference", "meeting", "blank")


def decode(word):
    patch.require(type(word) is int and 0 <= word <= 0xFFFFFFFF, "plan words must be unsigned 32-bit integers")
    return dict(activity=word & 511, target=(word >> 9) & 32767,
                hours=(word >> 24) & 15, day=(word >> 28) & 7, repeat=bool(word >> 31))


def encode(*, activity, hours=1, day=0, target=0, repeat=False):
    patch.require(all(type(v) is int for v in (activity, hours, day, target)) and
                  type(repeat) is bool and 0 <= activity < 173 and 1 <= hours <= 8 and
                  0 <= day < 7 and 0 <= target < 32768, "invalid native prep activity/hours/day/target/repeat")
    return activity | target << 9 | hours << 24 | day << 28 | int(repeat) << 31


def default_plan():
    """Ten low full-drill hours per player, Monday-Friday, two rest days.

    Each day's three two-hour entries target 1st/2nd/3rd team at the same
    intensity. Native rank selection gives each player one entry per day.
    """
    rows = [encode(activity=activity, hours=2, day=day, repeat=True)
            for day in range(5) for activity in (93, 96, 99)]
    rows += [encode(activity=103, day=day, repeat=True) for day in (5, 6)]
    return tuple(rows + [EMPTY] * (WORDS - len(rows)))


def validate_plan(words, *, player_count=None):
    patch.require(len(words) == WORDS, "a native prep plan contains exactly 500 words")
    active = []
    for index, word in enumerate(words):
        row = decode(word)
        if row["activity"] == 0:
            continue
        patch.require(row["activity"] < 173 and 1 <= row["hours"] <= 8 and row["day"] < 7,
                      f"unsupported prep row {index}: activity/hours/day")
        target = row["target"]
        patch.require(target <= 18 or player_count is None or target - 18 < player_count,
                      f"prep row {index} points outside the saved player pool")
        active.append(dict(index=index, **row))
    return active


def _document(payload, team):
    patch.require(type(team) is int and 0 <= team < 32, "team must be a league ordinal 0..31")
    return fs.FranchiseSave(payload)


def read_plan(payload, team):
    doc = _document(payload, team)
    base = doc.front_office_block
    words = struct.unpack_from("<500I", payload, base + PLAN_OFFSET + team * 2000)
    state = doc.u32(base + STATE_OFFSET + team * 4)
    patch.require(state in (0, 1, 2), "unknown native prep state; refusing to describe it as remembered")
    master = doc.u32(MASTER_OFFSET)
    patch.require(master in (0, 1), "unknown native Weekly Preparation setting")
    rows = validate_plan(words, player_count=doc.u32(fs.ARENA_ROOT))
    return dict(team=team, weekly_preparation=bool(master), state=state,
                state_text=("not applied", "editing", "applied for this game")[state],
                seed=doc.u32(base + SEED_OFFSET + team * 4), rows=rows,
                plan_offset=base + PLAN_OFFSET + team * 2000,
                plan_sha256=hashlib.sha256(struct.pack("<500I", *words)).hexdigest(),
                automatic_options="Build settings in default.xbe; no option flags are saved here",
                experimental=True, runtime_witnessed=False)


def replace_plan(payload, team, words):
    """Author a fixed-size native plan. Refuse an applied plan before mutation.

    Changing the plan while its bonuses are active would make native inverse
    cleanup subtract a different result. Editing resumes after the game.
    """
    doc = _document(payload, team)
    before = read_plan(payload, team)
    patch.require(before["state"] != 2, "finish this team's game before changing its applied prep plan")
    rows = validate_plan(words, player_count=doc.u32(fs.ARENA_ROOT))
    at = before["plan_offset"]
    doc.buffer[at:at + 2000] = struct.pack("<500I", *words)
    state_at = doc.front_office_block + STATE_OFFSET + team * 4
    struct.pack_into("<I", doc.buffer, state_at, 1 if rows else 0)
    result = doc.to_bytes()
    return result, dict(owner=patch.OWNER, team=team, status="changed" if result != payload else "unchanged",
                        experimental=True, runtime_witnessed=False, signed=False, save_growth=0,
                        changed_ranges=doc.changed_ranges(), plan=read_plan(result, team))


def audit_tables(payload):
    patch._recognize(payload)
    image = XbeImage(payload)
    attributes = []
    for bit in range(28):
        setter, getter = struct.unpack("<II", image.read(0xACD760 + bit * 8, 8))
        raw = image.read(getter, 5)
        patch.require(raw[:3] == bytes.fromhex("0fbe41") and raw[4] == 0xC3 and
                      0x36 <= raw[3] <= 0x51, "foreign prep attribute getter")
        attributes.append(dict(bit=bit, field=rr.RATING_BYTE_ORDER[raw[3] - 0x36],
                               offset=raw[3], setter=hex(setter), getter=hex(getter)))
    rows = []
    for index in range(173):
        raw = image.read(0x51D358 + index * 32, 32)
        key, category, subtype, intensity, injury_mask, mask, flags, injury_flags = struct.unpack("<IIIfIIII", raw)
        rows.append(dict(id=index, string_key=hex(key), category=CATEGORIES[category], category_id=category,
                         subtype=subtype, intensity=intensity, injury_mask=hex(injury_mask),
                         attribute_mask=hex(mask), attributes=[a["field"] for a in attributes if mask & 1 << a["bit"]],
                         flags=hex(flags), injury_flags=hex(injury_flags)))
    masks = struct.unpack("<17I", image.read(0x51E8F8, 68))
    return dict(experimental=True, runtime_witnessed=False, attributes=attributes, activities=rows,
                position_masks={p: hex(mask) for p, mask in zip(POSITIONS, masks)},
                native_forward="0x2ab8f0", native_inverse="0x2abe60",
                cause="DB drills test only CB, excluding FS and SS; TE's valid row matches HB/FB and its reported deficit is not root-caused.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "set-plan"))
    parser.add_argument("source", type=Path, help="loose SAVEGAME.DAT with sibling EXTRA")
    parser.add_argument("--team", type=int, required=True)
    parser.add_argument("--plan", type=Path, help="JSON array of 500 native words")
    parser.add_argument("--output", type=Path, help="new signed-copy directory")
    args = parser.parse_args(argv)
    patch.require(args.source.is_file() and args.source.name.upper() == "SAVEGAME.DAT" and
                  args.source.stat().st_size <= 1024 * 1024, "choose a loose franchise SAVEGAME.DAT, at most 1 MiB")
    container = rr.SaveContainer.load(args.source, require_signature=True)
    if args.command == "inspect":
        receipt = dict(read_plan(container.savegame, args.team), signature_verified=True)
    else:
        patch.require(args.plan is not None and args.output is not None, "set-plan requires --plan and --output")
        patch.require(args.plan.stat().st_size <= 32768, "plan JSON exceeds 32 KiB")
        payload, receipt = replace_plan(container.savegame, args.team, json.loads(args.plan.read_text()))
        receipt["signed_copy"] = container.write(args.output, payload)
        receipt["signed"] = True
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
