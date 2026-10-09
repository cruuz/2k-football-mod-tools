"""QB Throw Power, all quarterbacks at once (b77 q1: "qb throw power all around should go up a bit").

What the number is
------------------
The roster record's byte ``+0x38`` is ``pass_arm_strength`` (``rr.RATING_OFFSETS``), the game's Throw Power.
The retail getter at ``0x179AE0`` reads exactly that byte and returns ``byte * 0.01`` (a byte of 100 or more reads
1.0), so the arm the throw curves see is ``rating / 100``.  Both max-distance curves (``0x50BDC0`` bullet,
``0x50BD8C`` lob), the throw-animation selector and the arm -> power-fraction table (``0x50BCE4``) are functions of
that arm value, so a QB's Throw Power rating is the one lever on how far and how hard he can throw.

Where a QB the player can meet keeps it
---------------------------------------
* every ROST resource of the disc: the main roster (outer entry 5: the 32 clubs, free agents, the draft class and the
  68 secondary records) and every one-team ROST file (the Anniversary moments' rosters and the historic teams);
* the rookie generator ``FUN_002BE6F0`` -> ``0xE6780`` rolls each of a new prospect's ratings between two secondary
  records of his position, ``pos*4 + v`` and ``pos*4 + v + 2``.  For QB those are arm 95/53 and 96/50, so a generated
  class draws its Throw Power from [53, 95] or [50, 96].  Raising both template bytes by the same step moves the whole
  rolled range by that step, which is what this module does to the secondary records (they are QB records too).

What it writes
--------------
One byte per quarterback record, nothing else: ``new = min(cap, old + add)`` and never below ``old`` (a byte already
past the cap is left alone).  The map is monotone, so a better arm stays at least as good; only QBs rated within
``add`` of the cap tie at the cap.  Position is the record's own code (0 = QB in every scheme).

The directive travels in a ``2k5_mod_studio_roster_edits/v1`` document as

    "qb_throw_power": {"add": 4, "cap": 99, "scope": "all"}        # scope "main" = the main roster only

and the Studio build applies it last of all, after the free agents, the Anniversary imports and every other roster
writer, to the disposable copy of the disc.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any, Mapping

from . import nfl2k5_roster_records as rr

OWNER = "nfl2k5_qb_throw_power"
DIRECTIVE_KEY = "qb_throw_power"
FIELD = "pass_arm_strength"
BYTE_IN_RECORD = rr.RATING_OFFSETS[FIELD]          # 0x38
QB_CODE = 0
WRAPPER = rr.RESOURCE_HEADER_SIZE                  # 0x20 bytes before the ROST body
DEFAULT_ADD = 4
DEFAULT_CAP = rr.RATING_MAX                        # 99, the editor's maximum
MAX_ADD = 30
SCOPES = ("all", "main")
MAIN_OUTER_INDEX = rr.ROST_OUTER_INDEX             # 5
DEFAULT_DIRECTIVE = {"add": DEFAULT_ADD, "cap": DEFAULT_CAP, "scope": "all"}


class QbThrowPowerError(ValueError):
    """A directive, a resource or a baseline that cannot be applied exactly."""


def _require(condition: object, message: str) -> None:
    if not condition:
        raise QbThrowPowerError(message)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------------------------------------ directive
def normalise_directive(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate a ``qb_throw_power`` directive; missing keys take the defaults (+4, cap 99, every roster)."""
    _require(isinstance(value, Mapping), "qb_throw_power must be an object like {'add': 4, 'cap': 99, 'scope': 'all'}")
    unknown = set(value) - set(DEFAULT_DIRECTIVE)
    _require(not unknown, f"unknown qb_throw_power keys {sorted(unknown)}")
    out = {**DEFAULT_DIRECTIVE, **dict(value)}
    for key in ("add", "cap"):
        _require(type(out[key]) is int, f"qb_throw_power {key} must be a whole number")
    _require(0 <= out["add"] <= MAX_ADD, f"qb_throw_power add must be 0..{MAX_ADD}")
    _require(1 <= out["cap"] <= rr.RATING_MAX_LARGE, f"qb_throw_power cap must be 1..{rr.RATING_MAX_LARGE}")
    _require(out["scope"] in SCOPES, f"qb_throw_power scope must be one of {SCOPES}")
    return out


def raised(value: int, add: int, cap: int) -> int:
    """The new rating: ``min(cap, value + add)``, never lower than ``value``."""
    return max(value, min(cap, value + add))


# ------------------------------------------------------------------------------------------------ one resource
def is_rost(raw: bytes) -> bool:
    return len(raw) > WRAPPER + 0x100 and raw[:4] == b"ROST" and raw[WRAPPER + 0x0C: WRAPPER + 0x10] == b"ROST"


def quarterbacks(raw: bytes) -> list[dict[str, Any]]:
    """Every QB record of one ROST resource (wrapper + body): where its Throw Power byte is and what it holds.

    A blank spare (all 28 rating bytes zero: the main roster's 27 empty draft-class slots) is not a player yet; the
    rookie generator overwrites the whole 0x54 record from the secondary templates, so it is skipped here."""
    _require(is_rost(raw), "not a ROST resource")
    body_length = struct.unpack_from("<I", raw, 4)[0]
    _require(WRAPPER + 0x100 < WRAPPER + body_length <= len(raw), "the ROST wrapper length is wrong")
    document = rr.RosterDocument(raw[WRAPPER: WRAPPER + body_length])
    rows = []
    for player in document.players:
        values = player.record.values
        if values["position"] != QB_CODE:
            continue
        if not any(values[name] for name in rr.RATING_BYTE_ORDER):
            continue
        at = WRAPPER + player.offset + BYTE_IN_RECORD
        _require(raw[at] == values[FIELD], f"{player.display}: the codec and the raw byte disagree")
        rows.append({"pool": player.pool, "index": player.index, "first": player.first, "last": player.last,
                     "group": player.group, "teams": list(player.teams), "offset": at, "value": raw[at]})
    return rows


def apply_resource(raw: bytes, add: int, cap: int = DEFAULT_CAP) -> tuple[bytes, list[dict[str, Any]]]:
    """A copy of ``raw`` with every QB's Throw Power raised; returns (new bytes, one row per changed byte)."""
    out = bytearray(raw)
    changes = []
    for row in quarterbacks(raw):
        new = raised(row["value"], add, cap)
        if new != row["value"]:
            out[row["offset"]] = new
            changes.append({**row, "before": row["value"], "after": new})
    return bytes(out), changes


# ------------------------------------------------------------------------------------------------ a disc image
def apply_image(path, directive: Mapping[str, Any] | None = None, *, progress=None) -> dict[str, Any]:
    """Apply the directive to every ROST resource of the disc image at ``path`` (a COPY), in place and same size."""
    say = progress or (lambda _m: None)
    plan = normalise_directive(directive if directive is not None else DEFAULT_DIRECTIVE)
    files, changed_bytes, qbs = [], 0, 0
    with rr._outer_image()(path, writable=True) as archive:
        for entry in archive.entries:
            if plan["scope"] == "main" and entry.index != MAIN_OUTER_INDEX:
                continue
            if entry.size <= WRAPPER + 0x100:
                continue
            before = archive.read(entry.virtual_offset, entry.size)
            if not is_rost(before):
                continue
            try:
                after, changes = apply_resource(before, plan["add"], plan["cap"])
            except (rr.RosterRecordError, QbThrowPowerError, struct.error):
                _require(entry.index != MAIN_OUTER_INDEX, "the main roster could not be read")
                continue            # a ROST-tagged entry this codec does not parse is left exactly as it is
            qbs += len(quarterbacks(before))
            if after == before:
                continue
            say(f"Raising QB Throw Power in outer entry {entry.index}")
            _require(len(after) == len(before), "the resource size changed")
            written = archive.write(entry.virtual_offset, after)
            _require(written == len(after), "short write of a roster resource")
            _require(archive.read(entry.virtual_offset, entry.size) == after, "read-back of a roster resource differs")
            changed_bytes += len(changes)
            files.append({"outer_index": entry.index, "bytes_changed": len(changes),
                          "sha256_before": sha256(before), "sha256_after": sha256(after)})
    return {"status": "applied" if files else "nothing_to_change", "directive": plan, "files_changed": len(files),
            "quarterbacks_seen": qbs, "bytes_changed": changed_bytes, "files": files}


def directive_of(edits_document: Mapping[str, Any]) -> dict[str, Any] | None:
    """The normalised directive of a roster-edits document, or None when it carries none."""
    if DIRECTIVE_KEY not in edits_document:
        return None
    return normalise_directive(edits_document[DIRECTIVE_KEY])


def merge_into_edits(existing: Mapping[str, Any], directive: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A copy of a roster-edits document (the league project's) that also carries the directive."""
    _require(isinstance(existing, Mapping) and existing.get("schema") == rr.EDITS_SCHEMA,
             "not a 2k5_mod_studio_roster_edits/v1 document")
    merged = {key: (list(value) if isinstance(value, list) else value) for key, value in existing.items()}
    merged[DIRECTIVE_KEY] = normalise_directive(directive if directive is not None else DEFAULT_DIRECTIVE)
    return merged


__all__ = ["merge_into_edits", "DEFAULT_ADD", "DEFAULT_CAP", "DEFAULT_DIRECTIVE", "DIRECTIVE_KEY", "OWNER", "QbThrowPowerError", "SCOPES",
           "apply_image", "apply_resource", "directive_of", "is_rost", "normalise_directive", "quarterbacks", "raised"]
