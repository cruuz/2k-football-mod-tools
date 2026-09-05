"""Seven-seed franchise presentation, dependent on ``nfl2k5_playoffs14``.

Fixed-size XBE patch; no new caves, flags, sections, or save fields. The shared
tree has 42 state records. Its franchise layout now uses records 0..12 instead
of 31..41. Thirteen 0x70-byte widgets replace the old eleven widgets and seven
column headings. Three conference/final headings reuse the old game-binding
table, whose two consumers are replaced. All these tables remain in .data.

SportsCenter keeps its retail eight-entry conference buffers: seven qualifiers
and the eighth team for the bubble comparison. Its seeder already sorts four
division winners and four other teams with the retail comparator. No recorded
speech is edited.

See ASTRA_PLAYOFF_PICTURE_REPORT.md for addresses, evidence and display checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct

from . import nfl2k5_playoffs14 as bracket
from . import nfl2k5_season_length as season
from .nfl2k5_bump_strength import _sections, _section_for_offset, section_digest

RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
WIDGET_REGION = 0xAEF3D0
WIDGET_VA = WIDGET_REGION + 0x20
WIDGET_SIZE = 0x70
WIDGET_COUNT = 13
HEADINGS_VA = 0xAF0C88
STATE_VA = 0xCC1E40
STATE_SIZE = 0x1C
GRID_VA = 0xE57C40
FLAGS_VA = 0xE57954
TREE_UPDATE_VA = 0x372BB0
TREE_UPDATE_SIZE = 0x70
ROW_HELPER_VA = 0x372C11
TREE_SCORES_VA = 0x372C60
TREE_SCORES_SIZE = 0x70

# (round offset, slot, x, y, left, right, up, down). Wild-card winners
# are reseeded, so no fixed WC-to-DIV connector is drawn.
NODES = (
    (0, 0, 42, 151, -1, 6, -1, 1),
    (0, 1, 42, 231, -1, 6, 0, 2),
    (0, 2, 42, 311, -1, 7, 1, -1),
    (0, 3, 1500, 151, 8, -1, -1, 4),
    (0, 4, 1500, 231, 8, -1, 3, 5),
    (0, 5, 1500, 311, 9, -1, 4, -1),
    (1, 0, 285, 171, 0, 10, -1, 7),
    (1, 1, 285, 291, 2, 10, 6, -1),
    (1, 2, 1257, 171, 11, 3, -1, 9),
    (1, 3, 1257, 291, 11, 5, 8, -1),
    (2, 0, 528, 231, 6, 12, -1, -1),
    (2, 1, 1014, 231, 12, 8, -1, -1),
    (3, 0, 771, 231, 10, 11, -1, -1),
)


class PlayoffPictureError(ValueError):
    pass


def _require(value: bool, message: str) -> None:
    if not value:
        raise PlayoffPictureError(message)


def widget_bytes() -> bytes:
    out = bytearray(0x20 + WIDGET_COUNT * WIDGET_SIZE)
    for index, (row, slot, x, y, left, right, up, down) in enumerate(NODES):
        at = 0x20 + index * WIDGET_SIZE
        struct.pack_into("<4fI4bIII", out, at, x, y, 2, 0, index,
                         left, right, up, down, row, slot, 0)
        # Retail horizontal pan keeps the selected 210-pixel box in view.
        struct.pack_into("<2f", out, at + 0x24, max(0, x - 215), 0)
        struct.pack_into("<f", out, at + 0x34, 25)
        struct.pack_into("<f", out, at + 0x54, 25)
    return bytes(out)


def heading_bytes() -> bytes:
    out = bytearray(11 * 12)
    for index, (x, label) in enumerate(((147, 0xEB9054), (876, 0xEB90AC),
                                      (1605, 0xEB90FC))):
        struct.pack_into("<4fI", out, index * 0x20, x, 99, 0, 0, label)
    return bytes(out)  # fourth 0x20-byte entry terminates the renderer's loop


def tree_code() -> tuple[bytes, bytes]:
    """Rewrite the two franchise callbacks within their original boundaries."""
    a = bracket._Asm(TREE_UPDATE_VA)
    a.b("53565755be" + bracket._imm(WIDGET_VA) + "bf" + bracket._imm(STATE_VA))
    a.label("node")
    a.b("0fb62d" + bracket._imm(bracket.STAGE_SEASON_WEEKS_VA))
    a.b("036e186bed11036e1c33db")          # ebp = grid index; ebx = side
    a.label("side")
    a.b("33c080bc6b" + bracket._imm(FLAGS_VA) + "00")
    a.j8("74", "unknown")
    a.b("0fb68ceb" + bracket._imm(GRID_VA + 1))
    a.call(bracket.FN_TEAM_AT)
    a.b("85c0")
    a.j8("74", "unknown")
    a.b("8b8008010000")                   # team abbreviation, as in retail
    a.label("unknown")
    a.b("890783c70c4383fb02")             # name at state+0 / state+12
    a.j8("72", "side")
    a.b("83c70483c67081fe" + bracket._imm(WIDGET_VA + WIDGET_COUNT * WIDGET_SIZE))
    a.j8("72", "node")
    a.b("5d5f5e5bc3")
    names = a.assemble()
    _require(TREE_UPDATE_VA + len(names) == ROW_HELPER_VA, "row-helper address drift")
    # Callable helper in the rewritten updater's remaining bytes. No retail
    # entry or pointer reaches it. Only the score callback calls this helper.
    names += bytes.fromhex("0fb60d") + struct.pack("<I", bracket.STAGE_SEASON_WEEKS_VA)
    names += bytes.fromhex("034e188b561cc3") # ecx = row, edx = slot, esi preserved

    a = bracket._Asm(TREE_SCORES_VA)
    a.b("5356578bf1")
    a.call(0x6E2D0)
    a.b("8bce")
    a.call(0x6C080)
    a.call(0x3649A0)                      # retail rendering; no renderer changes
    a.b("be" + bracket._imm(WIDGET_VA))
    a.label("node")
    a.call(ROW_HELPER_VA)
    a.call(bracket.FN_GAME_TYPE)
    a.b("83f803")
    a.j8("75", "unknown")
    a.call(ROW_HELPER_VA)
    a.call(0xC5110)
    a.b("8bf8")
    a.call(ROW_HELPER_VA)
    a.call(0xC5150)
    a.b("8bd8")
    a.j8("eb", "store")
    a.label("unknown")
    a.b("83cfff8bdf")                    # -1 for unplayed scores
    a.label("store")
    a.b("8b4e108bd7")
    a.call(0x3644E0)
    a.b("8b4e108bd3")
    a.call(0x3644F0)
    a.b("83c67081fe" + bracket._imm(WIDGET_VA + WIDGET_COUNT * WIDGET_SIZE))
    a.j8("72", "node")
    a.b("5f5e5bc3")
    scores = a.assemble()
    _require(len(names) <= TREE_UPDATE_SIZE and len(scores) <= TREE_SCORES_SIZE,
             "presentation code exceeds its replaced routines")
    return names.ljust(TREE_UPDATE_SIZE, b"\x90"), scores.ljust(TREE_SCORES_SIZE, b"\x90")


@dataclass(frozen=True)
class Site:
    label: str
    va: int
    patched: bytes
    retail: bytes | None = None
    digest: str | None = None

    @property
    def size(self) -> int:
        return len(self.patched)


# SHA-256 pins for whole replaced retail tables/routine, including their owned
# padding. Small instruction/string sites carry exact preimages below.
PINS = {
    TREE_UPDATE_VA: "60071a96899cf5ee9d267a61dd566df731184356776c97b28fed9877a488bfa3",
    TREE_SCORES_VA: "3595ec3e5deab215a5f170aa17aef8d9ca3697a3d2d1647a6c18921c594a2992",
    WIDGET_REGION: "c80a2ff76208682582d33b8776093ae49e616a88379153a7885abc01a5ced0e1",
    HEADINGS_VA: "d61e73d93973113350cd0f9ef1b3f9b82331f9d0271c4274f4cd1f74cf62e3c9",
}


def _text(label: str, va: int, before: str, after: str) -> Site:
    old = (before + "\0").encode("utf-16le")
    new = (after + "\0").encode("utf-16le")
    _require(len(new) <= len(old), f"{label}: text exceeds its fixed allocation")
    return Site(label, va, new.ljust(len(old), b"\0"), old)


def sites() -> tuple[Site, ...]:
    return (
        Site("tree_names", TREE_UPDATE_VA, tree_code()[0], digest=PINS[TREE_UPDATE_VA]),
        Site("tree_scores", TREE_SCORES_VA, tree_code()[1], digest=PINS[TREE_SCORES_VA]),
        Site("thirteen_widgets", WIDGET_REGION, widget_bytes(), digest=PINS.get(WIDGET_REGION)),
        Site("conference_headings", HEADINGS_VA, heading_bytes(), digest=PINS.get(HEADINGS_VA)),
        Site("widget_pointer", 0xAEF9B8, struct.pack("<I", WIDGET_VA), struct.pack("<I", 0xAEF4D0)),
        Site("widget_count", 0x584168, struct.pack("<I", WIDGET_COUNT), struct.pack("<I", 11)),
        Site("heading_pointer", 0x5841FC, struct.pack("<I", HEADINGS_VA), struct.pack("<I", 0xAEF3D0)),
        Site("picture_seven_rows", 0x36848A, b"\x90\x90", bytes.fromhex("7e07")),
        Site("picture_seventh_rank", 0x368821, bytes.fromhex("83f907"), bytes.fromhex("83f906")),
        Site("recap_seventh_status", 0x220D83, bytes.fromhex("83ff07"), bytes.fromhex("83ff06")),
        Site("recap_bubble_in", 0x221229, bytes.fromhex("8b7018"), bytes.fromhex("8b7014")),
        Site("recap_bubble_out", 0x22122D, bytes.fromhex("8b781c"), bytes.fromhex("8b7818")),
        # Level 3 is obsolete. Older saves may still carry its byte at team+1EC.
        Site("picture_obsolete_bye", 0x3687E8, bytes.fromhex("eb06"), bytes.fromhex("7606")),
        Site("recap_obsolete_bye_label", 0x220DD6, bytes.fromhex("eb36"), bytes.fromhex("7636")),
        Site("recap_obsolete_bye_script", 0x221001, bytes.fromhex("eb5b"), bytes.fromhex("745b")),
        _text("picture_rule_banner", 0xEAEA9C, "If the playoffs started today:", "7 seeds: #1 bye; 2v7 3v6 4v5"),
        _text("picture_only_bye", 0xEB997C, "Home Field Adv.", "#1 Seed / Bye"),
        _text("recap_only_bye", 0xE87D9C, "Home Field Adv.", "#1 Seed / Bye"),
        _text("afc_seeds", 0xEB9054, "AFC Wild Card", "AFC: 7 Seeds"),
        _text("nfc_seeds", 0xEB90FC, "NFC Wild Card", "NFC: 7 Seeds"),
    )


def _state(xbe: bytes, site: Site, sections) -> str:
    off = season._offset(xbe, site.va, sections)
    got = xbe[off:off + site.size]
    if got == site.patched:
        return "applied"
    if got == site.retail or (site.digest and hashlib.sha256(got).hexdigest() == site.digest):
        return "retail"
    return "foreign"


def status(xbe: bytes) -> str:
    """Retail/applied/foreign; a partial presentation patch fails closed."""
    try:
        sections = _sections(xbe)
        states = {_state(xbe, site, sections) for site in sites()}
        result = states.pop() if len(states) == 1 else "foreign"
        if result == "applied" and season.group_status(xbe, "playoffs_14") != "applied":
            return "foreign"
        return result
    except (ValueError, IndexError, struct.error):
        return "foreign"


def apply(xbe: bytes) -> tuple[bytes, dict[str, object]]:
    """Atomic in-memory, idempotent patch; requires the matching bracket first."""
    _require(season.group_status(xbe, "playoffs_14") == "applied",
             "apply playoffs_14 before playoff presentation")
    state = status(xbe)
    _require(state != "foreign", "presentation sites are foreign or partially patched")
    receipt: dict[str, object] = {"status": "applied", "seeds_per_conference": 7,
        "wild_card_games": 6, "tree_games": 13, "changed_bytes": 0,
        "sections_repinned": [], "runtime_verified": False, "audio_modified": False}
    if state == "applied":
        return bytes(xbe), receipt
    sections = _sections(xbe)
    out = bytearray(xbe)
    touched = set()
    for site in sites():
        off = season._offset(xbe, site.va, sections)
        section = _section_for_offset(sections, off)
        _require(off + site.size <= section.raw_offset + section.raw_size, "site crosses section")
        out[off:off + site.size] = site.patched
        touched.add(section.index)
    for section in sections:
        if section.index in touched:
            at = section.header_offset + 36
            out[at:at + 20] = section_digest(bytes(out), section)
    patched = bytes(out)
    _require(status(patched) == "applied", "presentation post-apply verification failed")
    receipt["changed_bytes"] = sum(a != b for a, b in zip(xbe, patched))
    receipt["sections_repinned"] = sorted(touched)
    receipt["sites"] = [{"label": s.label, "va": hex(s.va), "size": s.size} for s in sites()]
    return patched, receipt


def main(argv=None) -> int:
    """Headless, copy-only CLI. Input must already carry the bracket patch."""
    import argparse
    import json
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "apply"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        source = args.input.read_bytes()
        if args.command == "status":
            result = {"status": status(source), "playoffs_14": season.group_status(source, "playoffs_14")}
        else:
            _require(args.output is not None, "apply requires --output (a new file)")
            patched, result = apply(source)
            # O_EXCL preserves existing inputs/outputs; O_BINARY matters on Windows.
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(patched)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                args.output.unlink(missing_ok=True)
                raise
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
