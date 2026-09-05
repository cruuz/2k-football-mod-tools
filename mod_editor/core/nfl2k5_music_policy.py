"""EXPERIMENTAL / UNWITNESSED, data-only retail music policies.

No instructions, purchase bits, caves or runtime storage are changed. Options
are independent monotonic additions; ``retail`` does not uninstall a patch.
UserList redirection requires the Frontend redirect. Random order is retail's
count-minus-two algorithm, not a shuffle bag; the initial track is index zero.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest
from .nfl2k5_cave_oracle import XbeImage

MENU_TEXT = ("Menus play the 59 jukebox songs in the game's random order. "
             "The 7 menu tracks are not included yet. "
             "Twelve jukebox tracks are spoken outtakes.")
POLICIES = ("retail", "jukebox_menus")
MENU_VA = 0xAC9ECC
USERLIST_VA = 0xAC9ED4
UNLOCK_IDS = (0x102, 0x103, 0x104, 0x105, 0x106, 0xFF, 0x100,
              0x101, 0x108, 0x109, 0x10A, 0x10B, 0x10C, 0x10D)
CONTEXT_VA, CONTEXT_SIZE = 0xAC9C80, 0x260
CONTEXT_SHA256 = "2349b4b02e707cbfa1e9fce4e296a804b0b7ccf04a367590d8cd687dde7023fa"
CAVES = ()
RUNTIME_GLOBALS = ()


class MusicPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Site:
    option: str
    va: int
    before: bytes
    after: bytes


SITES = (Site("music_policy", MENU_VA, struct.pack("<I", 0xE92D4C),
              struct.pack("<I", 0xE92A34)),
         *(Site("music_unlock", 0xAC9C94 + c * 0x20, struct.pack("<I", key), bytes(4))
           for c, key in enumerate(UNLOCK_IDS)),
         Site("music_userlist", USERLIST_VA, bytes(12), struct.pack("<3I", 1, 1, 0xE92A34)))


def _context(payload: bytes) -> XbeImage:
    image = XbeImage(payload)
    context = bytearray(image.read(CONTEXT_VA, CONTEXT_SIZE))
    for site in SITES:
        section = image.section(site.va, len(site.before))
        if section is None or section.name != ".data" or section.flags != 7:
            raise MusicPolicyError("Music fields require the retail writable .data mapping")
        at = site.va - CONTEXT_VA
        context[at:at + len(site.before)] = bytes(len(site.before))
    if hashlib.sha256(context).hexdigest() != CONTEXT_SHA256:
        raise MusicPolicyError("Music collection/context records differ from the retail pins")
    for va, name in ((0xE92D4C, "femusic"), (0xE92A34, "cribmusic")):
        expected = (name + "\0").encode("utf-16le")
        if image.read(va, len(expected)) != expected:
            raise MusicPolicyError("Music bank name pointer target differs from retail")
    return image


def read_any(payload: bytes) -> dict:
    try:
        image = _context(payload)
        options = {}
        for option in ("music_policy", "music_unlock", "music_userlist"):
            states = set()
            for site in SITES:
                if site.option == option:
                    actual = image.read(site.va, len(site.before))
                    states.add("retail" if actual == site.before else
                               "applied" if actual == site.after else "foreign")
            options[option] = states.pop() if len(states) == 1 else "foreign"
        illegal = options["music_userlist"] == "applied" and options["music_policy"] != "applied"
        state = ("foreign" if illegal or "foreign" in options.values() else
                 "applied" if "applied" in options.values() else "retail")
        return {"status": state, **options, "runtime_witnessed": False}
    except (ValueError, struct.error, IndexError, OverflowError) as exc:
        return {"status": "foreign", "reason": str(exc)}


def status(payload: bytes) -> str:
    return read_any(payload)["status"]


@dataclass(frozen=True)
class Selection:
    """Dispatcher adapter: an already-enabled independent option must not skip
    another requested option. Aggregate status alone cannot make that choice.
    """
    music_policy: str = "retail"
    music_unlock: bool = False
    music_userlist: bool = False

    def __post_init__(self):
        if (self.music_policy not in POLICIES or type(self.music_unlock) is not bool or
            type(self.music_userlist) is not bool or
            (self.music_userlist and self.music_policy != "jukebox_menus")):
            raise MusicPolicyError("Invalid selected music policy options")

    def status(self, payload):
        state = read_any(payload)
        if state["status"] == "foreign":
            return "foreign"
        selected = {"music_policy": self.music_policy == "jukebox_menus",
                    "music_unlock": self.music_unlock, "music_userlist": self.music_userlist}
        return "applied" if all(not enabled or state[key] == "applied"
                                for key, enabled in selected.items()) else "retail"

    def apply(self, payload):
        return apply(payload, music_policy=self.music_policy, music_unlock=self.music_unlock,
                     music_userlist=self.music_userlist)


def apply(payload: bytes, *, music_policy: str = "jukebox_menus",
          music_unlock: bool = False, music_userlist: bool = False) -> tuple[bytes, dict]:
    if music_policy not in POLICIES or type(music_policy) is not str:
        raise MusicPolicyError("music_policy must be retail or jukebox_menus")
    if type(music_unlock) is not bool or type(music_userlist) is not bool:
        raise MusicPolicyError("Music switches must be booleans")
    before = read_any(payload)
    if before["status"] == "foreign":
        raise MusicPolicyError(f"Music fields are foreign or mixed; refusing: {before}")
    if music_userlist and music_policy != "jukebox_menus" and before["music_policy"] != "applied":
        raise MusicPolicyError("Direct UserList music requires jukebox menus")
    selected = {"music_policy": music_policy == "jukebox_menus",
                "music_unlock": music_unlock, "music_userlist": music_userlist}
    image = _context(payload)
    sections = _sections(payload)
    result, edits, touched = bytearray(payload), [], set()
    for site in SITES:
        if not selected[site.option] or before[site.option] == "applied":
            continue
        at = image.offset(site.va, len(site.before))
        result[at:at + len(site.after)] = site.after
        touched.add(_section_for_offset(sections, at).index)
        edits.append({"option": site.option, "va": hex(site.va), "file_offset": hex(at),
                      "size": len(site.after), "before": site.before.hex(), "after": site.after.hex()})
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            result[at:at + 20] = section_digest(bytes(result), section)
    result = bytes(result)
    after = read_any(result)
    if after["status"] == "foreign" or any(enabled and after[key] != "applied"
                                           for key, enabled in selected.items()):
        raise MusicPolicyError("Music post-apply verification failed")
    changed_count = sum(a != b for a, b in zip(payload, result))
    return result, {**after, "before": before, "already_applied": not edits,
                    "edits": edits, "sections_repinned": sorted(touched),
                    "changed_bytes": changed_count, "changed_byte_count": changed_count,
                    "field_bytes": sum(edit["size"] for edit in edits),
                    "new_caves": [], "runtime_globals": [], "scope": MENU_TEXT}
