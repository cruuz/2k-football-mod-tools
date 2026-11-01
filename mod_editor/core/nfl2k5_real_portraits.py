"""Real Player Card portraits for the created real free agents (job b779-pt1, Noah 2026-10-28).

Noah: "is it possible to add player images for Kaepernick in these free agents? I noticed none of them have images.
Only if accurate."  And, about the coaches and the free agents alike: "take a look at the NFL roster. That's just a
bunch of real pictures of everyone."

Cause
-----
The created real free agents (the dated pool, the 533 depth players, Colin Kaepernick) carry a no-photo selector in
the player record's portrait id (+0x06: 22324.., 21696.. or, for the 90 players the dated refresh creates, 7100).
No portrait slot exists under those names, so the Player Card draws the stock ``nophoto`` silhouette.

What this module ships
----------------------
* ``data/nfl2k5_real_portraits/``: the official NFL.com headshot of every accepted player, cropped to the retail
  portrait framing (eye line at y = 48, eye to mouth 30 px of 128, transparent cutout, soft alpha) and reduced to the
  game's own 128 x 128 P8 format (256 RGBA palette entries).  The pictures are the real photographs, not paintings or
  renders; the original files are never stored (``portraits.json`` keeps each source URL, size and sha256).
* The portraits ride the rookie-faces record: ``Portrai2.iff`` / ``portrai2.cdf`` already hold every retail slot plus
  the rookie bank, and ``nfl2k5_rookie_faces.apply_to_image(extra_faces=...)`` adds more.  This module's faces take the
  ids ``ID_BASE`` .. ``ID_BASE + count - 1`` (30000..30999 reserved), a five-digit run far above every retail,
  coach, alien (1947) and rookie-bank id (1000..21695) and below the 65535 limit of the record's u16.
* After the last roster writer, :func:`apply_assignments` writes each player's id into the main roster (record
  +0x06, two bytes, nothing else), matching him by first name, surname and birth month/day (not by slot, so a
  capacity growth that moves records cannot misdirect a face) and only when his record still holds the no-photo
  selector, so a portrait a user or another option gave him is never replaced.

Without the rookie-faces option the slots are not written and the cards stay on ``nophoto`` exactly as before.
A rejected player (no photo, placeholder, obscured, wrong person) keeps the no-photo card rather than a wrong face.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OWNER = "nfl2k5_real_portraits"
DATA_DIR = ROOT / "data" / "nfl2k5_real_portraits"
MANIFEST = DATA_DIR / "portraits.json"
SCHEMA = "nfl2k5.real_portraits.v1"
ID_BASE = 30000
ID_LIMIT = 31000                     # reserved window 30000..30999
NO_PHOTO_REFRESH = 7100              # the dated refresh's created players
NO_PHOTO_FLOOR = 21696               # every free-agent selector (21696..23086 on v0.7)
PHOTO_FIELD = 0x06                   # record +0x06, u16


class RealPortraitsError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RealPortraitsError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key(text: str) -> str:
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    return "".join(c for c in rr.commentary_surname(text).lower() if c.isalnum())


def _first_key(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


# ------------------------------------------------------------------------------------------------ data
def load_manifest(path: Path | None = None) -> dict[str, Any]:
    doc = json.loads(Path(path or MANIFEST).read_text(encoding="utf-8"))
    require(doc.get("schema") == SCHEMA, "unknown real portraits manifest")
    rows = doc["portraits"]
    ids = [r["id"] for r in rows]
    require(len(ids) == len(set(ids)), "duplicate portrait ids")
    require(all(ID_BASE <= i < ID_LIMIT for i in ids), f"portrait ids must stay in {ID_BASE}..{ID_LIMIT - 1}")
    gsis = [r["gsis_id"] for r in rows]
    require(len(gsis) == len(set(gsis)), "a player has two portraits")
    return doc


def portrait_ids(doc: Mapping[str, Any] | None = None) -> list[int]:
    return [r["id"] for r in (doc or load_manifest())["portraits"]]


def faces(doc: Mapping[str, Any] | None = None) -> list[tuple[int, tuple[bytes, bytes]]]:
    """[(portrait id, (128 x 128 palette indices, 1024-byte RGBA palette))] for ``rookie_faces.apply_to_image``'s
    ``extra_faces``: the second element is a tuple, which tells the portrait writer the face is already P8."""
    from PIL import Image  # noqa: PLC0415
    doc = doc or load_manifest()
    files = {}
    for sheet in doc["atlases"]:
        data = (DATA_DIR / sheet["file"]).read_bytes()
        require(sha(data) == sheet["sha256"], f"{sheet['file']} does not match its pin")
        files[sheet["file"]] = Image.open(io.BytesIO(data))
    out = []
    for row in doc["portraits"]:
        index = files[row["atlas"]]
        palette = files[row["atlas"][:-4] + "_pal.png"]
        require(index.mode == "L" and palette.mode == "RGBA", "a portrait atlas has the wrong mode")
        col, line = row["cell"]
        cell = index.crop((col * 128, line * 128, col * 128 + 128, line * 128 + 128)).tobytes()
        pal = palette.crop((0, line * 16 + col, 256, line * 16 + col + 1)).tobytes()
        out.append((row["id"], (cell, pal)))
    return out


# ------------------------------------------------------------------------------------------------ roster
def _selector(photo: int) -> bool:
    return photo == NO_PHOTO_REFRESH or photo >= NO_PHOTO_FLOOR


def plan_assignments(document, doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Which listed players the main roster holds and the id each gets. A name that matches nobody is ``missing``
    (a later roster growth or a user's own league); two matches are ``ambiguous`` and skipped; a record that already
    holds a real portrait id is ``kept``."""
    doc = doc or load_manifest()
    index: dict[tuple[str, str, int, int], list] = {}
    for p in document.players:
        if p.pool != "primary":
            continue
        rec = p.record
        index.setdefault((_first_key(p.first), _key(p.last), int(rec.get("birth_month") or 0),
                          int(rec.get("birth_day") or 0)), []).append(p)
    writes, missing, ambiguous, kept = [], [], [], []
    for row in doc["portraits"]:
        name = f"{row['first']} {row['last']}"
        found = index.get((_first_key(row["first"]), _key(row["last"]), row["birth_month"], row["birth_day"]), [])
        if not found:
            missing.append(name)
        elif len(found) > 1:
            ambiguous.append(name)
        else:
            player = found[0]
            current = int(player.record.values["photo_id"])
            if current == row["id"]:
                kept.append(name)
            elif not _selector(current):
                kept.append(name)
            else:
                writes.append((player.offset + PHOTO_FIELD, row["id"], name))
    return {"writes": writes, "missing": missing, "ambiguous": ambiguous, "kept": kept, "listed": len(doc["portraits"])}


def prepare(path: Path | str) -> list[tuple[int, tuple[bytes, bytes]]]:
    """The faces to add for the players the image's main roster actually holds (read only): a user's own league that
    lacks these players gets none, so no unused slots are written."""
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    doc = load_manifest()
    with rr._outer_image()(str(path), writable=False) as archive:
        entry = rr._entry(archive)
        resource = archive.read(entry.virtual_offset, entry.size)
    document = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="image",
                                 resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
    plan = plan_assignments(document, doc)
    wanted = {pid for _off, pid, _name in plan["writes"]}
    return [(pid, face) for pid, face in faces(doc) if pid in wanted]


def apply_assignments(path: Path | str) -> dict[str, Any]:
    """Write the portrait ids into the image's main roster (record +0x06 only)."""
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    with rr._outer_image()(str(path), writable=True) as archive:
        entry = rr._entry(archive)
        resource = archive.read(entry.virtual_offset, entry.size)
        document = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="image",
                                     resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
        plan = plan_assignments(document)
        base = entry.virtual_offset + rr.RESOURCE_HEADER_SIZE
        for offset, pid, _name in plan["writes"]:
            require(archive.write(base + offset, struct.pack("<H", pid)) == 2, "short portrait id write")
        after = archive.read(entry.virtual_offset, entry.size)
        allowed = {rr.RESOURCE_HEADER_SIZE + off + k for off, _pid, _n in plan["writes"] for k in (0, 1)}
        changed = [i for i in range(len(after)) if after[i] != resource[i]]
        require(set(changed) <= allowed, "a portrait id write touched a byte other than record +0x06")
    return {"status": "applied", "written": len(plan["writes"]), "listed": plan["listed"],
            "missing": len(plan["missing"]), "ambiguous": len(plan["ambiguous"]), "kept": len(plan["kept"])}


def roster_status(resource: bytes, doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from . import nfl2k5_roster_records as rr  # noqa: PLC0415
    document = rr.RosterDocument(resource[rr.RESOURCE_HEADER_SIZE:], base=0, source="image",
                                 resource_header=resource[:rr.RESOURCE_HEADER_SIZE])
    plan = plan_assignments(document, doc)
    return {"pending": len(plan["writes"]), "missing": len(plan["missing"]), "listed": plan["listed"]}
