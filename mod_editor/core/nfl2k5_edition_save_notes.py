"""64 MB edition: save messages that explain a save made by the 128 MB edition.

A franchise saved by the standard (128 MB) SOFTDRINK edition is larger than the compact (64 MB) game can read. The
compact game lists it as "Damaged", says "Unable to load %s on %s." when it is chosen, and its Delete screen asks
the usual "You are about to delete %s from %s. This process cannot be undone. Continue?". A player who switched
edition could delete a healthy franchise that still loads on the standard edition.

This owner changes text only, in place, on the compact edition (on by default only in the 64 MB profile):

* the delete confirmation (0xE82888, one reference: ``mov edx`` at 0x16CB06) warns that a 128 MB save shows as
  Damaged here and still loads there;
* the load failure (0xE82678, two references in the one load-error routine: 0x16C5A9 and 0x16C654) says the save may
  be a 128 MB save.

Each new string keeps the format arguments of the original in the same order (save name, then device), keeps the
button token ``|CROSS|`` where the original had it, and fits inside the original string's own slot: the bytes up to
the next string, which no pointer in the retail, v0.10 128 MB or v0.10 64 MB executable references. The row label
"Damaged" (0xE82CAC, used by the browser's damaged flag 0x16B1F6 and type 0 of the label table 0xAA33D0) has room
for seven characters only, so it stays as it is. No code changes.
"""
from __future__ import annotations

import struct

from . import nfl2k5_rdata_sites as rdata

OWNER = "nfl2k5_edition_save_notes"
REVISION = 1
BUILD_CAPTION = "64 MB: warn before deleting a 128 MB save"
HELP_TEXT = ("A franchise saved on the standard 128 MB edition shows as Damaged on the compact 64 MB edition and will "
             "not load there, but it is not damaged. This changes the compact game's Delete confirmation and its "
             "load error to say so, so a player does not delete a save that still loads on the standard edition. "
             "Text only; for the 64 MB edition.")

DELETE_VA, DELETE_ROOM = 0x00E82888, 160          # string slot: up to the next string (8-byte aligned)
LOAD_VA, LOAD_ROOM = 0x00E82678, 112
RETAIL_DELETE = "You are about to delete %s from %s. This process cannot be undone. Continue?"
RETAIL_LOAD = "Unable to load %s on %s.\n Press |CROSS| to continue."
DELETE_TEXT = "Delete %s from %s? A 128 MB save shows Damaged here but loads there. Continue?"
LOAD_TEXT = "Can't load %s. 128 MB save?\nPress |CROSS| to continue."
# (the instruction that loads the string, its bytes): mov edx, imm32
REFERENCES = (("delete confirmation", 0x0016CB06, DELETE_VA), ("load failure", 0x0016C5A9, LOAD_VA),
              ("load failure (second path)", 0x0016C654, LOAD_VA))


def _slot(text: str, room: int) -> bytes:
    raw = (text + "\0").encode("utf-16-le")
    if len(raw) > room:
        raise ValueError(f"{text!r} does not fit its {room}-byte slot")
    return raw.ljust(room, b"\0")


SITES = (("delete confirmation text", DELETE_VA, _slot(RETAIL_DELETE, DELETE_ROOM), _slot(DELETE_TEXT, DELETE_ROOM)),
         ("load failure text", LOAD_VA, _slot(RETAIL_LOAD, LOAD_ROOM), _slot(LOAD_TEXT, LOAD_ROOM)))
DEPENDENCIES = tuple((label, va, b"\xba" + struct.pack("<I", target)) for label, va, target in REFERENCES)


def status(payload: bytes) -> str:
    """``retail`` | ``applied`` | ``foreign`` (a string reference moved, or the text is neither)."""
    if rdata.status(payload, [(label, va, raw, raw) for label, va, raw in DEPENDENCIES]) != "retail":
        return "foreign"
    return rdata.status(payload, SITES)


def read_settings(payload: bytes) -> dict:
    state = status(payload)
    return {"status": state, "edition_save_notes": state == "applied"}


def apply(payload: bytes):
    """(patched payload, receipt). Idempotent; anything neither retail nor applied is refused."""
    if status(payload) == "foreign":
        raise ValueError("the 64 MB save messages: a message or its reference is not retail")
    patched, receipt = rdata.apply(payload, SITES, "64 MB save messages")
    return patched, {**receipt, "revision": REVISION}


def verify(payload: bytes) -> dict:
    return {"owner": OWNER, "status": status(payload),
            "sites": [{"label": s[0], "va": f"0x{s[1]:x}"} for s in SITES],
            "experimental": False, "runtime_witnessed": False}


__all__ = ["OWNER", "REVISION", "SITES", "DEPENDENCIES", "DELETE_TEXT", "LOAD_TEXT", "BUILD_CAPTION", "HELP_TEXT",
           "status", "read_settings", "apply", "verify"]
